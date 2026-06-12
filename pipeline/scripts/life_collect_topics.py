"""LIFE programme (2021-2027): collect the full topic list via the SEDIA search
API, then fetch per-topic details from the same topicDetails endpoint used for
Horizon (works for LIFE-* IDs; frameworkProgramme id 43252405 = LIFE2027).

NOTE: LIFE awarded *projects/beneficiaries* have no open bulk dataset (the CINEA
LIFE dashboard is Qlik-only; LIFE is not in CORDIS), so this collects the TOPIC
layer only. Project layer is documented as a known gap.

Outputs: parsed/life_topic_ids.json   (id -> status abbreviation map)
         parsed/life_topics_ft_details.pkl/.csv
"""
import json
import re
import subprocess
import sys
import time
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_topic_details import fetch_topic, parse_topic, RAW_DIR

ROOT = Path(__file__).resolve().parent.parent
PARSED = ROOT / "parsed"

URL = ("https://api.tech.ec.europa.eu/search-api/prod/rest/search"
       "?apiKey=SEDIA&text=***&pageSize=100&pageNumber={page}")
QUERY = '{"bool":{"must":[{"terms":{"type":["1"]}},{"terms":{"frameworkProgramme":["43252405"]}}]}}'

ids = {}
page = 1
while True:
    r = subprocess.run(
        ["curl", "-s", "-X", "POST", URL.format(page=page),
         "-F", f"query={QUERY};type=application/json"],
        capture_output=True, text=True)
    try:
        d = json.loads(r.stdout)
    except json.JSONDecodeError:
        print(f"page {page}: bad response, retrying once"); time.sleep(2)
        continue
    results = d.get("results", [])
    if not results:
        break
    for res in results:
        md = res.get("metadata") or {}
        ident = md.get("identifier")
        if isinstance(ident, list):
            ident = ident[0] if ident else None
        if ident and re.match(r"^LIFE-20\d\d", ident):
            ids[ident] = None
    total = d.get("totalResults", 0)
    print(f"page {page}: cumulative unique LIFE ids = {len(ids)} (raw total {total})", flush=True)
    if page * 100 >= total:
        break
    page += 1
    time.sleep(0.3)

# keep 2021-2026 (consistent with the Horizon workbooks)
ids = {i: s for i, s in ids.items() if re.match(r"^LIFE-202[1-6]-", i)}
print(f"LIFE unique topic ids 2021-2026: {len(ids)}")
json.dump(sorted(ids), open(PARSED / "life_topic_ids.json", "w"), indent=1)

rows = []
n_new = 0
for i, tid in enumerate(sorted(ids), 1):
    cache = RAW_DIR / f"{tid}.json"
    was_cached = cache.exists()
    obj = fetch_topic(tid)
    rows.append(parse_topic(obj, tid))
    if not was_cached:
        n_new += 1
        time.sleep(0.3)
    if i % 25 == 0:
        print(f"  {i}/{len(ids)} (newly fetched: {n_new})", flush=True)

df = pd.DataFrame(rows)
print(f"\nFetched {len(df)}. found={df['found'].sum()}")
for col in ["ft_title", "opening_date", "deadline_date", "budget_per_project_M", "budget_total_M"]:
    print(f"  {col}: {df[col].notna().sum()}")
df.to_pickle(PARSED / "life_topics_ft_details.pkl")
df.to_csv(PARSED / "life_topics_ft_details.csv", index=False)
print(f"Saved {PARSED / 'life_topics_ft_details.pkl'}")
