"""CL6: filter CORDIS to HORIZON-CL6-* and derive Sheet 1 (Topics) skeleton.

Mirrors build_topics_from_cordis.py (CL5) with CL6 specifics:
  - destinations are NAMED (FARM2FORK, BIODIV, ...) not D1-D6, and case is
    inconsistent in CORDIS (CIRCBIO vs CircBio) -> normalise to upper
  - IBA variants are messier: HORIZON-CL6-2025-IBA-01, HORIZON-CL6-2024-SYNERGY-IBA,
    HORIZON-CL6-2023-2025-BIOEAST-IBA-02, HORIZON-CL6-OA01-2022-IBA, ...
    -> anything containing "-IBA" is kind=IBA, year = first 20xx in the ID

Outputs: parsed/cl6_projects.pkl, parsed/cl6_topic_titles.pkl,
         parsed/cl6_topics_from_cordis.pkl/.csv
"""
import pandas as pd
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw" / "cordis_he"
PARSED = ROOT / "parsed"

# ---- Step 5 equivalent: filter projects & titles to CL6 main WP ----
proj_all = pd.read_excel(RAW / "project.xlsx")
mask = proj_all["topics"].astype(str).str.upper().str.startswith("HORIZON-CL6-")
proj = proj_all[mask].copy()
proj.to_pickle(PARSED / "cl6_projects.pkl")
print(f"CL6 projects: {len(proj)}")

tt = pd.read_excel(RAW / "topics.xlsx")
tt6 = (tt[tt["topic"].astype(str).str.upper().str.startswith("HORIZON-CL6-")]
       [["topic", "title"]].drop_duplicates("topic"))
tt6.to_pickle(PARSED / "cl6_topic_titles.pkl")
print(f"CL6 unique topics in CORDIS: {len(tt6)}")

# ---- Step 6/7 equivalent: parse IDs, aggregate ----
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

# old (2021-2024): HORIZON-CL6-YYYY-{DEST}-CC-NN[-suffix]
# new (2025+):     HORIZON-CL6-YYYY-CC-{DEST}-NN[-suffix]  (mirrors CL5 swap; verify on real IDs)
pat_old = re.compile(r"^HORIZON-CL6-(\d{4})-([A-Za-z][A-Za-z0-9]*)-(\d+)-(\d+)(?:-(.+))?$")
pat_new = re.compile(r"^HORIZON-CL6-(\d{4})-(\d+)-([A-Za-z][A-Za-z0-9]*)-(\d+)(?:-(.+))?$")
YEAR_PAT = re.compile(r"(20\d\d)")
COLS = ["year", "destination", "call_num", "topic_num", "suffix", "kind"]

def parse(t):
    if "-IBA" in t.upper():
        m = YEAR_PAT.search(t)
        return pd.Series([m.group(1) if m else None, None, None, None, None, "IBA"], index=COLS)
    m = pat_old.match(t)
    if m:
        return pd.Series([m.group(1), m.group(2).upper(), m.group(3), m.group(4), m.group(5), "standard"], index=COLS)
    m = pat_new.match(t)
    if m:
        return pd.Series([m.group(1), m.group(3).upper(), m.group(2), m.group(4), m.group(5), "standard"], index=COLS)
    return pd.Series([None] * 6, index=COLS)

parts = agg["topic_id"].apply(parse)
agg = pd.concat([agg, parts], axis=1)

unparsed = agg[agg["kind"].isna()]
if len(unparsed):
    print("UNPARSED topic IDs:")
    for t in unparsed["topic_id"]:
        print("  ", t)

agg = agg.merge(tt6.rename(columns={"topic": "topic_id", "title": "topic_title"}),
                on="topic_id", how="left")

SCHEME_MAP = {
    "HORIZON-RIA": "RIA",
    "HORIZON-IA": "IA",
    "HORIZON-CSA": "CSA",
    "HORIZON-COFUND": "COFUND",
}
agg["topic_type"] = agg["dominant_scheme"].map(SCHEME_MAP)
agg.loc[agg["kind"] == "IBA", "topic_type"] = "IBA"

# Official CL6 WP destination names
DEST_MAP = {
    "FARM2FORK": "Fair, healthy and environment-friendly food systems from primary production to consumption",
    "BIODIV": "Biodiversity and ecosystem services",
    "CIRCBIO": "Circular economy and bioeconomy sectors",
    "ZEROPOLLUTION": "Clean environment and zero pollution",
    "CLIMATE": "Land, ocean and water for climate action",
    "COMMUNITIES": "Resilient, inclusive, healthy and green rural, coastal and urban communities",
    "GOVERNANCE": "Innovative governance, environmental observations and digital solutions in support of the Green Deal",
}
agg["destination_name"] = agg["destination"].map(DEST_MAP)
unknown_dest = sorted(set(agg["destination"].dropna()) - set(DEST_MAP))
if unknown_dest:
    print("Destinations without name mapping:", unknown_dest)

PORTAL_TPL = "https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/opportunities/topic-details/{tid}"
agg["portal_link"] = agg["topic_id"].apply(lambda t: PORTAL_TPL.format(tid=t))
agg["framework"] = "Horizon Europe"
agg["cluster"] = "CL6"

cols = ["framework", "year", "cluster", "destination", "destination_name",
        "master_call", "topic_id", "topic_title", "topic_type", "kind",
        "funded_projects", "sum_ec", "sum_total",
        "portal_link", "dominant_scheme", "suffix"]
agg = agg[cols].sort_values(["year", "destination", "topic_id"]).reset_index(drop=True)

print(f"Derived topics rows: {len(agg)}")
print(f"Year coverage: {sorted(agg['year'].dropna().unique())}")
print(f"By destination:\n{agg['destination'].value_counts(dropna=False)}")
print(f"Topics missing title: {agg['topic_title'].isna().sum()}")
print(f"Topics missing topic_type: {agg['topic_type'].isna().sum()}")

agg.to_pickle(PARSED / "cl6_topics_from_cordis.pkl")
agg.to_csv(PARSED / "cl6_topics_from_cordis.csv", index=False)
print(f"Saved to {PARSED / 'cl6_topics_from_cordis.pkl'}")
