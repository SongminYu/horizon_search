"""Fetch F&T Portal topicDetails JSON for all CL6 topic IDs.

ID sources (union):
  - parsed/cl6_topics_from_cordis.pkl      (CORDIS-known, signed topics)
  - parsed/cl6_all_topic_ids.json          (full list from grantsTenders.json,
                                            incl. 2025/2026 not-yet-signed; optional)

Reuses fetch_topic / parse_topic / cache dir from fetch_topic_details.py.
Output: parsed/cl6_topics_ft_details.pkl/.csv
"""
import json
import sys
import time
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_topic_details import fetch_topic, parse_topic, RAW_DIR

ROOT = Path(__file__).resolve().parent.parent
PARSED = ROOT / "parsed"

ids = set(pd.read_pickle(PARSED / "cl6_topics_from_cordis.pkl")["topic_id"])
extra = PARSED / "cl6_all_topic_ids.json"
if extra.exists():
    ids |= set(json.loads(extra.read_text()))
    print(f"Including grantsTenders ID list: total {len(ids)} unique IDs")
else:
    print(f"grantsTenders ID list not found yet; fetching {len(ids)} CORDIS-known IDs only")
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

df.to_pickle(PARSED / "cl6_topics_ft_details.pkl")
df.to_csv(PARSED / "cl6_topics_ft_details.csv", index=False)
print(f"Saved {PARSED / 'cl6_topics_ft_details.pkl'}")
