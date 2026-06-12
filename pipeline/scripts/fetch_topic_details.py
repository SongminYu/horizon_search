"""Fetch per-topic JSON from the F&T Portal topicDetails endpoint.

Input  : parsed/topics_from_cordis.pkl (390 known topic IDs)
Output : raw/topic_details/<topic_id>.json
         parsed/topics_enriched.pkl (DataFrame with all metadata extracted)

Strategy:
1. For each topic in CORDIS list, GET https://ec.europa.eu/info/funding-tenders/opportunities/data/topicDetails/{topic_id_lower}.json
2. Parse: title, callIdentifier, callTitle, actions[0].types[0].typeOfAction, plannedOpeningDate,
   deadlineDates, deadlineModel, budget (per topic from budgetTopicActionMap), expectedGrants,
   minContribution, maxContribution, TRL hints from description
3. Cache responses to raw/topic_details/ so re-runs don't re-fetch
4. Polite rate-limit: 0.3s sleep between requests, retry on 5xx
"""
import json
import re
import time
import urllib.request
import urllib.error
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "raw" / "topic_details"
PARSED = ROOT / "parsed"
RAW_DIR.mkdir(parents=True, exist_ok=True)

TPL = "https://ec.europa.eu/info/funding-tenders/opportunities/data/topicDetails/{tid}.json"
HEADERS = {"Accept": "application/json", "User-Agent": "Mozilla/5.0 (data-collection-bot; contact: yu.ceepcas@gmail.com)"}


def fetch_topic(topic_id: str, force: bool = False) -> dict | None:
    cache = RAW_DIR / f"{topic_id}.json"
    if cache.exists() and not force:
        try:
            return json.loads(cache.read_text())
        except json.JSONDecodeError:
            cache.unlink()
    url = TPL.format(tid=topic_id.lower())
    req = urllib.request.Request(url, headers=HEADERS)
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read()
            obj = json.loads(data)
            cache.write_bytes(data)
            return obj
        except urllib.error.HTTPError as e:
            if e.code == 404:
                cache.write_text("{}")  # mark as missing
                return {}
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(2 ** attempt)
                continue
            print(f"  ! HTTP {e.code} on {topic_id}")
            return None
        except (urllib.error.URLError, TimeoutError) as e:
            time.sleep(2 ** attempt)
    print(f"  ! gave up on {topic_id}")
    return None


def ms_to_iso(ms) -> str | None:
    if ms is None or ms == "":
        return None
    try:
        ms = int(ms)
    except (TypeError, ValueError):
        return None
    import datetime
    return datetime.datetime.fromtimestamp(ms / 1000, tz=datetime.timezone.utc).date().isoformat()


TRL_PAT = re.compile(r"\bTRL[\s-]?(\d+)(?:\s*[-–]\s*(\d+))?", re.IGNORECASE)


def extract_trl(desc: str) -> str | None:
    if not desc:
        return None
    matches = TRL_PAT.findall(desc)
    if not matches:
        return None
    nums = []
    for a, b in matches:
        if a: nums.append(int(a))
        if b: nums.append(int(b))
    if not nums:
        return None
    lo, hi = min(nums), max(nums)
    return f"TRL {lo}" if lo == hi else f"TRL {lo}-{hi}"


def parse_topic(obj: dict, topic_id: str) -> dict:
    if not obj or "TopicDetails" not in obj:
        return {"topic_id": topic_id, "found": False}
    td = obj["TopicDetails"]
    title = td.get("title")
    call_id = td.get("callIdentifier")
    call_title = td.get("callTitle")
    actions = td.get("actions") or [{}]
    a0 = actions[0]
    types = a0.get("types") or []
    type_str = types[0].get("typeOfAction") if types else None
    type_short = None
    if type_str:
        if "HORIZON-RIA" in type_str: type_short = "RIA"
        elif "HORIZON-IA" in type_str: type_short = "IA"
        elif "HORIZON-CSA" in type_str: type_short = "CSA"
        elif "HORIZON-COFUND" in type_str: type_short = "COFUND"
        elif "IBA" in type_str.upper(): type_short = "IBA"

    opening = ms_to_iso(a0.get("plannedOpeningDate"))
    deadlines = a0.get("deadlineDates") or []
    deadline = ms_to_iso(deadlines[-1]) if deadlines else None

    # Budget: look up this topic in budgetTopicActionMap
    budget_per_proj = None
    budget_total = None
    expected_grants = None
    stage = None
    budget_map = td.get("budgetOverviewJSONItem", {}).get("budgetTopicActionMap", {}) or {}
    for key, entries in budget_map.items():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            action_str = entry.get("action", "")
            if action_str.startswith(topic_id):
                if entry.get("minContribution") is not None:
                    budget_per_proj = entry["minContribution"] / 1e6  # to EUR M
                if entry.get("maxContribution") is not None:
                    # use max if different from min; range
                    bmax = entry["maxContribution"] / 1e6
                    if budget_per_proj is not None and abs(bmax - budget_per_proj) > 1e-6:
                        budget_per_proj = f"{budget_per_proj:g}-{bmax:g}"
                bym = entry.get("budgetYearMap", {}) or {}
                if bym:
                    budget_total = sum(float(v) for v in bym.values() if v) / 1e6
                expected_grants = entry.get("expectedGrants")
                stage = entry.get("deadlineModel")
                break
        if budget_per_proj or budget_total:
            break

    desc = td.get("description", "")
    cond = td.get("conditions", "")
    full_text = (desc or "") + "\n" + (cond or "")
    trl = extract_trl(full_text)

    # Fallback: parse budget hints from description text if not in budget map
    if budget_per_proj is None:
        m = re.search(r"contribution\s+from\s+the\s+EU\s+of\s+(?:between\s+)?EUR\s*([\d.,]+)(?:\s*(?:and|-|to|–)\s*([\d.,]+))?\s*million",
                      full_text, re.IGNORECASE)
        if m:
            lo = float(m.group(1).replace(",", "."))
            if m.group(2):
                hi = float(m.group(2).replace(",", "."))
                budget_per_proj = f"{lo:g}-{hi:g}" if abs(hi - lo) > 1e-6 else lo
            else:
                budget_per_proj = lo
    if budget_total is None:
        m = re.search(r"[Ii]ndicative\s+budget[^.]*?EUR\s*([\d.,]+)\s*million",
                      full_text)
        if m:
            budget_total = float(m.group(1).replace(",", "."))

    # destination details
    dd = td.get("metadata", {}).get("destinationDetails", []) if isinstance(td.get("metadata"), dict) else []

    return {
        "topic_id": topic_id,
        "found": True,
        "ft_title": title,
        "ft_call_id": call_id,
        "ft_call_title": call_title,
        "ft_type": type_short,
        "ft_type_full": type_str,
        "opening_date": opening,
        "deadline_date": deadline,
        "stage": stage,
        "budget_per_project_M": budget_per_proj,
        "budget_total_M": budget_total,
        "expected_grants": expected_grants,
        "trl": trl,
    }


def main():
    src = pd.read_pickle(PARSED / "topics_from_cordis.pkl")
    topics = src["topic_id"].tolist()
    print(f"Fetching details for {len(topics)} CORDIS-known topics...")

    rows = []
    n_new = 0
    for i, tid in enumerate(topics, 1):
        cache = RAW_DIR / f"{tid}.json"
        was_cached = cache.exists()
        obj = fetch_topic(tid)
        rows.append(parse_topic(obj, tid))
        if not was_cached:
            n_new += 1
            time.sleep(0.3)
        if i % 25 == 0:
            print(f"  {i}/{len(topics)} (newly fetched: {n_new})")

    df = pd.DataFrame(rows)
    print(f"\nFetched {len(df)} topics. found={df['found'].sum()} / not found={len(df)-df['found'].sum()}")
    print(f"Fields filled (non-null counts):")
    for col in ["ft_title", "ft_type", "opening_date", "deadline_date",
                "budget_per_project_M", "budget_total_M", "expected_grants", "trl"]:
        print(f"  {col}: {df[col].notna().sum()}")

    df.to_pickle(PARSED / "topics_ft_details.pkl")
    df.to_csv(PARSED / "topics_ft_details.csv", index=False)
    print(f"Saved {PARSED / 'topics_ft_details.pkl'}")


if __name__ == "__main__":
    main()
