"""Build a person-level layer for a workbook from OpenAlex.

For each project's Grant Agreement ID, query OpenAlex for works funded by that
grant, extract the authors, and aggregate one row per person:
  author -> ORCID, main institution, # works / lead works, which projects, topics.

"Lead" = first / last / corresponding author. We track it separately so the
webapp can rank genuine PIs above the middle authors of 100-author mega-papers
(e.g. Global Carbon Budget), which otherwise inflate a person's project count.

Usage:
  python3 pipeline/scripts/fetch_people.py <workbook.xlsx>
  e.g. python3 pipeline/scripts/fetch_people.py CL5_Topics_and_Projects.xlsx

Input  : data/<workbook>  (Projects sheet: Grant Agreement ID, Project Acronym)
Cache  : raw/people/<grant>.json   (shared across workbooks; re-runs skip fetched)
Output : parsed/<stem>_people.pkl  (stem = workbook prefix, e.g. cl5, h2020_sc3)

Net: stdlib urllib only, OpenAlex polite pool (mailto). No API key.
"""
import sys
import json
import time
import http.client
import urllib.request
import urllib.error
from collections import defaultdict
from pathlib import Path
import pandas as pd
import warnings
warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "raw" / "people"
PARSED = ROOT / "parsed"
CACHE.mkdir(parents=True, exist_ok=True)

MAILTO = "yu.ceepcas@gmail.com"
SELECT = "id,display_name,publication_year,authorships,topics"
BASE = ("https://api.openalex.org/works?filter=awards.funder_award_id:{gid}"
        f"&select={SELECT}&per-page=200&mailto={MAILTO}")


def load_openalex_key():
    """API key 顺序：环境变量 OPENALEX_API_KEY → pipeline/openalex_api_key.local（首条非#非空行）。
    有 key 则计入你的 OpenAlex 账户、用你充的额度；没有则走免费 polite pool（~1000/天）。"""
    import os
    env = (os.environ.get("OPENALEX_API_KEY") or "").strip()
    if env:
        return env
    f = ROOT / "openalex_api_key.local"
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            if "=" in s:
                s = s.split("=", 1)[1]
            return s.strip().strip('"').strip("'") or None
    return None


OPENALEX_KEY = load_openalex_key()


class BudgetExhausted(Exception):
    """OpenAlex daily free budget is gone (429 with a long retry-after)."""

class FetchIncomplete(Exception):
    """A grant could not be fully fetched — caller must NOT cache it."""

def fetch_works(gid: int):
    """All works for one grant, cursor-paged, file-cached.

    Only writes the cache on a FULLY successful paged fetch. On a long-retry 429
    (daily budget exhausted) it raises BudgetExhausted so the run stops cleanly
    without poisoning the cache; on other persistent failures it raises
    FetchIncomplete so the grant stays uncached and is retried on the next run.
    """
    cache = CACHE / f"{gid}.json"
    if cache.exists():
        return json.loads(cache.read_text())
    works, cursor = [], "*"
    while cursor:
        url = BASE.format(gid=gid) + f"&cursor={cursor}"
        if OPENALEX_KEY:
            url += "&api_key=" + OPENALEX_KEY
        req = urllib.request.Request(url, headers={"User-Agent": f"horizon-people-bot ({MAILTO})"})
        for attempt in range(6):
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    d = json.load(r)
                break
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    ra = int(e.headers.get("retry-after") or 0)
                    if ra > 120:                       # daily budget gone -> stop, don't cache
                        raise BudgetExhausted(ra)
                    time.sleep(min(ra or 2 ** attempt, 60)); continue
                if e.code in (500, 502, 503): time.sleep(2 ** attempt); continue
                raise
            except (urllib.error.URLError, TimeoutError,
                    http.client.IncompleteRead, http.client.HTTPException,
                    ConnectionError, OSError):
                time.sleep(2 ** attempt)
        else:
            raise FetchIncomplete(gid)                  # never cache a partial result
        works.extend(d["results"])
        cursor = d["meta"].get("next_cursor")
        if not d["results"]: break
        time.sleep(0.15)
    cache.write_text(json.dumps(works))
    return works


def is_lead(authorship) -> bool:
    return authorship.get("author_position") in ("first", "last") or bool(authorship.get("is_corresponding"))


def main():
    wb_name = sys.argv[1]
    stem = wb_name.split("_Topics")[0].lower()
    proj = pd.read_excel(ROOT.parent / "data" / wb_name, sheet_name="Projects")
    gid2acr = dict(zip(proj["Grant Agreement ID"], proj["Project Acronym"]))
    gids = [int(g) for g in proj["Grant Agreement ID"].dropna()]
    print(f"{stem}: {len(gids)} projects -> OpenAlex by grant id")

    matched = 0
    works_total = 0
    # author_id -> aggregate
    P = lambda: {"name": "", "orcid": None, "works": 0, "lead": 0,
                 "grants": set(), "lead_grants": set(),
                 "insts": defaultdict(int), "ctry": defaultdict(int),
                 "topics": defaultdict(int)}
    people = defaultdict(P)

    stopped = False
    for i, gid in enumerate(gids, 1):
        try:
            works = fetch_works(gid)
        except BudgetExhausted as e:
            hrs = e.args[0] / 3600 if e.args else 0
            print(f"  ! OpenAlex daily budget exhausted at grant {i}/{len(gids)} "
                  f"(resets in ~{hrs:.1f}h). Stopping; re-run later to resume.", flush=True)
            stopped = True
            break
        except FetchIncomplete:
            continue                                   # leave uncached; retried next run
        works_total += len(works)
        if works: matched += 1
        for w in works:
            wtopics = [t["display_name"] for t in (w.get("topics") or [])[:2]]
            for a in w.get("authorships") or []:
                au = a.get("author") or {}
                aid = au.get("id")
                if not aid: continue
                lead = is_lead(a)
                p = people[aid]
                p["name"] = au.get("display_name") or p["name"]
                if au.get("orcid"): p["orcid"] = au["orcid"]
                p["works"] += 1
                p["grants"].add(gid)
                if lead:
                    p["lead"] += 1
                    p["lead_grants"].add(gid)
                for inst in a.get("institutions") or []:
                    nm = inst.get("display_name")
                    if nm:
                        p["insts"][nm] += 1
                        if inst.get("country_code"): p["ctry"][inst["country_code"]] += 1
                for t in wtopics:
                    p["topics"][t] += 1
        if i % 100 == 0:
            print(f"  {i}/{len(gids)} grants | people {len(people):,}", flush=True)

    rows = []
    for aid, p in people.items():
        top_inst = max(p["insts"].items(), key=lambda x: x[1])[0] if p["insts"] else ""
        top_ctry = max(p["ctry"].items(), key=lambda x: x[1])[0] if p["ctry"] else ""
        top_topics = ", ".join(t for t, _ in sorted(p["topics"].items(), key=lambda x: -x[1])[:3])
        gids_sorted = sorted(p["grants"])
        rows.append({
            "Author ID": aid.rsplit("/", 1)[-1],
            "Name": p["name"],
            "ORCID": p["orcid"].rsplit("/", 1)[-1] if p["orcid"] else None,
            "Country": top_ctry,
            "Main Institution": top_inst,
            "Works": p["works"],
            "Lead Works": p["lead"],
            "Projects": len(p["grants"]),
            "Lead Projects": len(p["lead_grants"]),
            "Top Topics": top_topics,
            "Project Acronyms": "; ".join(gid2acr.get(g, str(g)) for g in gids_sorted),
            "Project Grant IDs": "; ".join(str(g) for g in gids_sorted),
        })
    df = (pd.DataFrame(rows)
          .sort_values(["Lead Works", "Works"], ascending=False)
          .reset_index(drop=True))
    df.to_pickle(PARSED / f"{stem}_people.pkl")

    n = len(gids)
    print(f"  match rate {matched}/{n} = {matched/n:.0%} | works {works_total:,} | "
          f"people {len(df):,} | ORCID {df['ORCID'].notna().mean():.0%} | "
          f">=2 projects {int((df['Projects']>=2).sum()):,}")
    print(f"  saved {PARSED / f'{stem}_people.pkl'}")
    if stopped:
        print("  RESUME-NEEDED: not all grants fetched (budget). Re-run after reset.", flush=True)
        sys.exit(3)


if __name__ == "__main__":
    main()
