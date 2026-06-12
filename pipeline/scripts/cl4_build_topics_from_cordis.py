"""CL4 (Digital, Industry & Space), SCOPED to the two energy/environment-relevant
destinations: TWIN-TRANSITION (industrial decarbonisation, clean steel, P4Planet)
and RESILIENCE (materials, critical raw materials, circular industry).

Destination tokens are multi-word (TWIN-TRANSITION), so the destination regex
allows hyphens and stops at the first numeric segment.

Outputs: parsed/cl4_projects.pkl (scoped), parsed/cl4_topic_titles.pkl,
         parsed/cl4_topics_from_cordis.pkl/.csv, parsed/cl4_all_topic_ids.json
Requires: raw/wp_2025_cl4.pdf, raw/wp_2026_cl4.pdf
"""
import json
import re
import subprocess
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw" / "cordis_he"
PARSED = ROOT / "parsed"

# the industry/materials lineage across WP renamings:
#   2021-2024: TWIN-TRANSITION + RESILIENCE
#   2025:      TWIN-TRANSITION + MATERIALS
#   2026-27:   MAT-PROD (merged)
SCOPE = {"TWIN-TRANSITION", "RESILIENCE", "MATERIALS", "MAT-PROD"}

DEST_SEG = r"[A-Z]+(?:-[A-Z]+)*?"
pat_old = re.compile(rf"^HORIZON-CL4-(\d{{4}})-({DEST_SEG})-(\d+)-(\d+)(?:-(.+))?$", re.IGNORECASE)
pat_new = re.compile(rf"^HORIZON-CL4-(\d{{4}})-(\d+)-({DEST_SEG})-(\d+)(?:-(.+))?$", re.IGNORECASE)

def parse(t):
    """-> (year, destination, suffix) or (None, None, None); IBA etc. -> dest None"""
    m = pat_old.match(t)
    if m:
        return m.group(1), m.group(2).upper(), m.group(5)
    m = pat_new.match(t)
    if m:
        return m.group(1), m.group(3).upper(), m.group(5)
    return None, None, None

proj_all = pd.read_excel(RAW / "project.xlsx")
mask = proj_all["topics"].astype(str).str.upper().str.startswith("HORIZON-CL4-")
cl4 = proj_all[mask].copy()
cl4[["_year", "_dest", "_sfx"]] = cl4["topics"].apply(lambda t: pd.Series(parse(t)))
proj = cl4[cl4["_dest"].isin(SCOPE)].copy()
proj.to_pickle(PARSED / "cl4_projects.pkl")
print(f"CL4 all: {len(cl4)} | scoped to {sorted(SCOPE)}: {len(proj)}")

tt = pd.read_excel(RAW / "topics.xlsx")
tt4 = tt[tt["topic"].astype(str).apply(lambda x: parse(x)[1] in SCOPE)][["topic", "title"]].drop_duplicates("topic")
tt4.to_pickle(PARSED / "cl4_topic_titles.pkl")
print(f"Scoped unique topics in CORDIS: {len(tt4)}")

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

parts = agg["topic_id"].apply(lambda t: pd.Series(parse(t), index=["year", "destination", "suffix"]))
agg = pd.concat([agg, parts], axis=1)
agg = agg.merge(tt4.rename(columns={"topic": "topic_id", "title": "topic_title"}),
                on="topic_id", how="left")

SCHEME_MAP = {"HORIZON-RIA": "RIA", "HORIZON-IA": "IA", "HORIZON-CSA": "CSA", "HORIZON-COFUND": "COFUND"}
agg["topic_type"] = agg["dominant_scheme"].map(SCHEME_MAP)

print(f"Derived topics rows: {len(agg)}")
print(agg.groupby(["destination"]).size().to_string())
print(f"Missing title: {agg['topic_title'].isna().sum()} | missing type: {agg['topic_type'].isna().sum()}")
agg.to_pickle(PARSED / "cl4_topics_from_cordis.pkl")
agg.to_csv(PARSED / "cl4_topics_from_cordis.csv", index=False)

# ---- WP PDF candidates (2025/2026, scoped destinations only) ----
def wp_candidates(pdf):
    txt = subprocess.run(["pdftotext", str(pdf), "-"], capture_output=True, text=True).stdout
    txt = re.sub(r"-\s*\n\s*", "-", txt)
    raw = set(re.findall(r"HORIZON-CL4-[A-Za-z0-9][A-Za-z0-9-]*", txt))
    out = set()
    for i in (x.rstrip("-") for x in raw):
        m = re.match(rf"^(HORIZON-CL4-(2025|2026)-\d{{1,2}}-(TWIN-TRANSITION|RESILIENCE|MATERIALS|MAT-PROD)-\d{{1,2}})(-two-stage)?", i, re.IGNORECASE)
        if m:
            out.add(m.group(1) + (m.group(4) or ""))
            continue
        m = re.match(rf"^(HORIZON-CL4-(2025|2026)-(TWIN-TRANSITION|RESILIENCE|MATERIALS|MAT-PROD)-\d{{1,2}}-\d{{1,2}})(-two-stage)?", i, re.IGNORECASE)
        if m:
            out.add(m.group(1) + (m.group(4) or ""))
    return out

cands = wp_candidates(ROOT / "raw" / "wp_2025_cl4.pdf") | wp_candidates(ROOT / "raw" / "wp_2026_cl4.pdf")
print(f"WP candidate IDs (2025/2026, scoped): {len(cands)}")
json.dump(sorted(cands), open(PARSED / "cl4_all_topic_ids.json", "w"), indent=1)
print(f"Saved {PARSED / 'cl4_all_topic_ids.json'}")
