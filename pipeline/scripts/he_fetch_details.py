"""Fetch F&T Portal topicDetails JSON for one HE cluster's topic IDs.

    python3 he_fetch_details.py <CLUSTER_KEY>     e.g. he_fetch_details.py CL1

ID sources (union):
  - parsed/<key>_topics_from_cordis.pkl   (CORDIS-known, signed topics)
  - parsed/<key>_all_topic_ids.json       (optional extra list; usually absent)

Reuses fetch_topic / parse_topic / cache dir from fetch_topic_details.py
(cache is shared at raw/topic_details/, so re-runs only fetch new IDs).
Output: parsed/<key>_topics_ft_details.pkl/.csv
"""
import json
import sys
import time
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_topic_details import fetch_topic, parse_topic, RAW_DIR

if len(sys.argv) < 2:
    sys.exit("usage: he_fetch_details.py <CLUSTER_KEY>  e.g. CL1")
key = sys.argv[1].lower()

ROOT = Path(__file__).resolve().parent.parent
PARSED = ROOT / "parsed"

ids = set(pd.read_pickle(PARSED / f"{key}_topics_from_cordis.pkl")["topic_id"])
extra = PARSED / f"{key}_all_topic_ids.json"
if extra.exists():
    ids |= set(json.loads(extra.read_text()))
    print(f"Including grantsTenders ID list: total {len(ids)} unique IDs")
else:
    print(f"grantsTenders ID list not found; fetching {len(ids)} CORDIS-known IDs only")
ids = sorted(ids)

rows = []
n_new = 0
for i, tid in enumerate(ids, 1):
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
print(f"\nFetched {len(df)} topics. found={df['found'].sum()} / not found={len(df) - df['found'].sum()}")
for col in ["ft_title", "ft_type", "opening_date", "deadline_date",
            "budget_per_project_M", "budget_total_M", "expected_grants", "trl"]:
    print(f"  {col}: {df[col].notna().sum()}")

df.to_pickle(PARSED / f"{key}_topics_ft_details.pkl")
df.to_csv(PARSED / f"{key}_topics_ft_details.csv", index=False)
print(f"Saved {PARSED / f'{key}_topics_ft_details.pkl'}")
