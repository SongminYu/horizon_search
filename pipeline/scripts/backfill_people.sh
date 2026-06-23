#!/bin/bash
# Daily resumable backfill of the OpenAlex people/works layer for the 6 new blocks
# (CL1/CL2/CL3 + H2020-SC1/SC6/SC7), within OpenAlex's free 1000-requests/day budget
# (resets midnight UTC). Run once per day; it resumes from the raw/people cache and
# stops cleanly when the budget is exhausted, then rebuilds the DB + webapp data so
# the site reflects whatever has been fetched so far.
#
#   bash pipeline/scripts/backfill_people.sh
#
# Safe to run repeatedly: fetch_people skips already-cached grants and never caches a
# failed/partial result; the DB is always rebuilt by restoring horizon.sqlite.bak (the
# untouched 9-block original) and re-running the additive merge.
set -u
cd "$(dirname "$0")/../.." || exit 1
S=pipeline/scripts
BLOCKS=(CL1 CL2 CL3 H2020_SC1 H2020_SC6 H2020_SC7)

if [ ! -f horizon.sqlite.bak ]; then
  echo "ERROR: horizon.sqlite.bak (the 9-block baseline) is missing — cannot rebuild safely." >&2
  exit 1
fi

budget_hit=0
for B in "${BLOCKS[@]}"; do
  echo "==== fetch_people $B ===="
  python3 "$S/fetch_people.py" "${B}_Topics_and_Projects.xlsx"
  rc=$?
  if [ "$rc" -eq 3 ]; then budget_hit=1; echo "==== daily budget reached at $B; stopping fetch ===="; break; fi
  if [ "$rc" -ne 0 ]; then echo "WARN: fetch_people $B exited $rc" >&2; fi
done

echo "==== rebuilding DB from baseline + current cache ===="
cp horizon.sqlite.bak horizon.sqlite
python3 "$S/merge_new_blocks.py" | grep -v "UserWarning\|warn(" | tail -8
python3 "$S/export_webapp.py"   | grep -v "UserWarning\|warn(" | tail -3

# how many new-block grants still need fetching?
python3 - <<'PY'
import pandas as pd, os, warnings; warnings.filterwarnings('ignore')
need=have=0
for s in ['CL1','CL2','CL3','H2020_SC1','H2020_SC6','H2020_SC7']:
    for g in pd.read_excel(f'data/{s}_Topics_and_Projects.xlsx',sheet_name='Projects')['Grant Agreement ID'].dropna():
        if os.path.exists(f'pipeline/raw/people/{int(g)}.json'): have+=1
        else: need+=1
print(f"==== new-block grants cached: {have} | still to fetch: {need} ====")
print("All fetched — run enrich_works_doi.py once for DOI links, then commit." if need==0
      else "Re-run this script after the next midnight-UTC reset to continue.")
PY
echo "==== backfill cycle done (budget_hit=$budget_hit) ===="
