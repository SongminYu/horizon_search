"""EU Missions (HORIZON-MISS-*): filter CORDIS, derive topic skeleton, and
extract 2025/2026 candidate IDs from the Missions WP PDFs.

All missions are included (CLIMA / OCEAN / CIT / SOIL / CANCER / NEB / cross-mission);
filter by the Destination column later if only the environmental ones are needed.

ID shapes:
  standard old : HORIZON-MISS-YYYY-{MISS}-CC-NN[-suffix]   (MISS may be compound: CLIMA-OCEAN-SOIL)
  standard new : HORIZON-MISS-YYYY-CC-{MISS}-NN[-suffix]   (2025+)
  IBA          : contains -IBA
  SGA          : contains -SGA (specific grant agreements, e.g. cities platform)

Outputs: parsed/miss_projects.pkl, parsed/miss_topic_titles.pkl,
         parsed/miss_topics_from_cordis.pkl/.csv, parsed/miss_all_topic_ids.json
Requires: raw/wp_2025_miss.pdf, raw/wp_2026_miss.pdf (pdftotext on PATH)
"""
import json
import re
import subprocess
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw" / "cordis_he"
PARSED = ROOT / "parsed"

# ---- filter CORDIS ----
proj_all = pd.read_excel(RAW / "project.xlsx")
mask = proj_all["topics"].astype(str).str.upper().str.startswith("HORIZON-MISS-")
proj = proj_all[mask].copy()
proj.to_pickle(PARSED / "miss_projects.pkl")
print(f"MISS projects: {len(proj)}")

tt = pd.read_excel(RAW / "topics.xlsx")
ttm = (tt[tt["topic"].astype(str).str.upper().str.startswith("HORIZON-MISS-")]
       [["topic", "title"]].drop_duplicates("topic"))
ttm.to_pickle(PARSED / "miss_topic_titles.pkl")
print(f"MISS unique topics in CORDIS: {len(ttm)}")

# ---- ID parsing ----
MISS_SEG = r"[A-Z]+(?:-[A-Z]+)*"
pat_old = re.compile(rf"^HORIZON-MISS-(\d{{4}})-({MISS_SEG}?)-(\d+)-(\d+)(?:-(.+))?$")
pat_new = re.compile(rf"^HORIZON-MISS-(\d{{4}})-(\d+)-({MISS_SEG}?)-(\d+)(?:-(.+))?$")
pat_iba = re.compile(rf"^HORIZON-MISS-(\d{{4}})-(?:(\d+)-)?({MISS_SEG}?)-IBA(?:-(\d+))?$")
pat_sga = re.compile(rf"^HORIZON-MISS-(\d{{4}})-(?:(\d+)-)?({MISS_SEG}?)-SGA(?:-(\d+))?$")
COLS = ["year", "destination", "call_num", "topic_num", "suffix", "kind"]

def parse(t):
    m = pat_iba.match(t)
    if m:
        return pd.Series([m.group(1), m.group(3), m.group(2), m.group(4), None, "IBA"], index=COLS)
    m = pat_sga.match(t)
    if m:
        return pd.Series([m.group(1), m.group(3), m.group(2), m.group(4), None, "SGA"], index=COLS)
    m = pat_old.match(t)
    if m:
        return pd.Series([m.group(1), m.group(2), m.group(3), m.group(4), m.group(5), "standard"], index=COLS)
    m = pat_new.match(t)
    if m:
        return pd.Series([m.group(1), m.group(3), m.group(2), m.group(4), m.group(5), "standard"], index=COLS)
    return pd.Series([None] * 6, index=COLS)

def to_float(x):
    if pd.isna(x):
        return None
    try:
        return float(str(x).replace(",", "."))
    except ValueError:
        return None

proj["ecMaxContribution_num"] = proj["ecMaxContribution"].apply(to_float)
proj["totalCost_num"] = proj["totalCost"].apply(to_float)

agg = proj.groupby("topics").agg(
    funded_projects=("id", "count"),
    sum_ec=("ecMaxContribution_num", "sum"),
    sum_total=("totalCost_num", "sum"),
    master_call=("masterCall", lambda s: s.mode().iat[0] if len(s.mode()) else None),
    dominant_scheme=("fundingScheme", lambda s: s.mode().iat[0] if len(s.mode()) else None),
).reset_index().rename(columns={"topics": "topic_id"})

parts = agg["topic_id"].apply(parse)
agg = pd.concat([agg, parts], axis=1)
unparsed = agg[agg["kind"].isna()]
if len(unparsed):
    print("UNPARSED topic IDs:")
    for t in unparsed["topic_id"]:
        print("  ", t)

agg = agg.merge(ttm.rename(columns={"topic": "topic_id", "title": "topic_title"}),
                on="topic_id", how="left")

SCHEME_MAP = {"HORIZON-RIA": "RIA", "HORIZON-IA": "IA", "HORIZON-CSA": "CSA", "HORIZON-COFUND": "COFUND"}
agg["topic_type"] = agg["dominant_scheme"].map(SCHEME_MAP)
agg.loc[agg["kind"] == "IBA", "topic_type"] = "IBA"
agg.loc[agg["kind"] == "SGA", "topic_type"] = "SGA"

print(f"Derived topics rows: {len(agg)}")
print(f"By mission:\n{agg['destination'].value_counts(dropna=False)}")
print(f"Missing title: {agg['topic_title'].isna().sum()} | missing type: {agg['topic_type'].isna().sum()}")
agg.to_pickle(PARSED / "miss_topics_from_cordis.pkl")
agg.to_csv(PARSED / "miss_topics_from_cordis.csv", index=False)

# ---- WP PDF candidates for 2025/2026 ----
def wp_candidates(pdf):
    txt = subprocess.run(["pdftotext", str(pdf), "-"], capture_output=True, text=True).stdout
    txt = re.sub(r"-\s*\n\s*", "-", txt)
    raw = set(re.findall(r"HORIZON-MISS-[A-Za-z0-9][A-Za-z0-9-]*", txt))
    out = set()
    for i in (x.rstrip("-") for x in raw):
        m = re.match(rf"^(HORIZON-MISS-(2025|2026)-\d{{1,2}}-{MISS_SEG}-\d{{1,2}})(-two-stage)?", i)
        if m:
            out.add(m.group(1) + (m.group(3) or ""))
            continue
        m = re.match(rf"^(HORIZON-MISS-(2025|2026)-{MISS_SEG}-\d{{1,2}}-\d{{1,2}})(-two-stage)?", i)
        if m:
            out.add(m.group(1) + (m.group(3) or ""))
            continue
        if re.match(rf"^HORIZON-MISS-(2025|2026)-(?:\d{{1,2}}-)?{MISS_SEG}-(IBA|SGA)(-\d{{1,2}})?$", i):
            out.add(i)
    return out

cands = wp_candidates(ROOT / "raw" / "wp_2025_miss.pdf") | wp_candidates(ROOT / "raw" / "wp_2026_miss.pdf")
print(f"WP candidate IDs (2025/2026): {len(cands)}")
json.dump(sorted(cands), open(PARSED / "miss_all_topic_ids.json", "w"), indent=1)
print(f"Saved {PARSED / 'miss_all_topic_ids.json'}")
