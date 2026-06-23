"""Generalised HE-cluster topic skeleton builder (parameterised).

    python3 he_build_topics.py <CLUSTER_KEY> <TOPIC_PREFIX>
    e.g. he_build_topics.py CL1 HORIZON-HLTH-
         he_build_topics.py CL2 HORIZON-CL2-
         he_build_topics.py CL3 HORIZON-CL3-

Mirrors cl6_build_topics_from_cordis.py but takes the cluster key and topic
prefix as args, so one script serves any HE cluster. Note CL1's key ("CL1")
differs from its topic prefix ("HORIZON-HLTH-") — handled by passing both.

Topic-ID grammar (verified identical across HLTH/CL2/CL3 and CL6):
  old (2021-2024): <PREFIX>YYYY-<DEST>-CC-NN[-suffix]
  new (2025+):     <PREFIX>YYYY-CC-<DEST>-NN[-suffix]
  anything containing "-IBA"  -> kind=IBA, year = first 20xx in the ID

Outputs: parsed/<key>_projects.pkl, parsed/<key>_topic_titles.pkl,
         parsed/<key>_topics_from_cordis.pkl/.csv   (<key> = CLUSTER_KEY.lower())
"""
import sys
import re
from pathlib import Path
import pandas as pd

if len(sys.argv) < 3:
    sys.exit("usage: he_build_topics.py <CLUSTER_KEY> <TOPIC_PREFIX>  e.g. CL1 HORIZON-HLTH-")
KEY = sys.argv[1].upper()
PREFIX = sys.argv[2].upper()
if not PREFIX.endswith("-"):
    PREFIX += "-"
key = KEY.lower()

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw" / "cordis_he"
PARSED = ROOT / "parsed"

# ---- filter projects & topic titles to this cluster ----
proj_all = pd.read_excel(RAW / "project.xlsx")
mask = proj_all["topics"].astype(str).str.upper().str.startswith(PREFIX)
proj = proj_all[mask].copy()
proj.to_pickle(PARSED / f"{key}_projects.pkl")
print(f"{KEY} projects: {len(proj)}")

tt = pd.read_excel(RAW / "topics.xlsx")
ttk = (tt[tt["topic"].astype(str).str.upper().str.startswith(PREFIX)]
       [["topic", "title"]].drop_duplicates("topic"))
ttk.to_pickle(PARSED / f"{key}_topic_titles.pkl")
print(f"{KEY} unique topics in CORDIS: {len(ttk)}")

# ---- parse IDs, aggregate ----
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

_p = re.escape(PREFIX)
pat_old = re.compile(rf"^{_p}(\d{{4}})-([A-Za-z][A-Za-z0-9]*)-(\d+)-(\d+)(?:-(.+))?$", re.IGNORECASE)
pat_new = re.compile(rf"^{_p}(\d{{4}})-(\d+)-([A-Za-z][A-Za-z0-9]*)-(\d+)(?:-(.+))?$", re.IGNORECASE)
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

agg = agg.merge(ttk.rename(columns={"topic": "topic_id", "title": "topic_title"}),
                on="topic_id", how="left")

SCHEME_MAP = {
    "HORIZON-RIA": "RIA",
    "HORIZON-IA": "IA",
    "HORIZON-CSA": "CSA",
    "HORIZON-COFUND": "COFUND",
}
agg["topic_type"] = agg["dominant_scheme"].map(SCHEME_MAP)
agg.loc[agg["kind"] == "IBA", "topic_type"] = "IBA"

# Destination names are cosmetic (display only); left unmapped for new clusters.
agg["destination_name"] = None
unknown_dest = sorted(set(agg["destination"].dropna()))
if unknown_dest:
    print(f"Destination codes (no name mapping): {unknown_dest}")

PORTAL_TPL = "https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/opportunities/topic-details/{tid}"
agg["portal_link"] = agg["topic_id"].apply(lambda t: PORTAL_TPL.format(tid=t))
agg["framework"] = "Horizon Europe"
agg["cluster"] = KEY

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

agg.to_pickle(PARSED / f"{key}_topics_from_cordis.pkl")
agg.to_csv(PARSED / f"{key}_topics_from_cordis.csv", index=False)
print(f"Saved to {PARSED / f'{key}_topics_from_cordis.pkl'}")
