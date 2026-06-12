"""Derive Sheet 1 (Topics) skeleton from CORDIS data alone.

Output: parsed/topics_from_cordis.pkl

Fields produced here (the rest comes from F&T Portal / WP PDFs):
  - Framework  = "Horizon Europe" (constant)
  - Year       = extracted from topic ID
  - Cluster    = "CL5"
  - Destination
  - Call ID    = masterCall (dominant)
  - Topic ID
  - Topic Title
  - Topic Type = dominant fundingScheme (RIA/IA/CSA/COFUND)
  - Number of Funded Projects
  - Sum EU Contribution across awarded projects (proxy for actual budget spent)
  - EU Portal Link (constructed)
"""
import pandas as pd
import re
from pathlib import Path

RAW = Path(__file__).resolve().parent.parent / "raw" / "cordis_he"
PARSED = Path(__file__).resolve().parent.parent / "parsed"

proj = pd.read_pickle(PARSED / "cl5_projects.pkl")
topic_titles = pd.read_pickle(PARSED / "cl5_topic_titles.pkl")

# Convert ecMaxContribution: numbers are stored as strings with comma decimal sep
def to_float(x):
    if pd.isna(x):
        return None
    s = str(x).replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None

proj["ecMaxContribution_num"] = proj["ecMaxContribution"].apply(to_float)
proj["totalCost_num"] = proj["totalCost"].apply(to_float)

# topic-level aggregation
agg = proj.groupby("topics").agg(
    funded_projects=("id", "count"),
    sum_ec=("ecMaxContribution_num", "sum"),
    sum_total=("totalCost_num", "sum"),
    master_call=("masterCall", lambda s: s.mode().iat[0] if len(s.mode()) else None),
    dominant_scheme=("fundingScheme", lambda s: s.mode().iat[0] if len(s.mode()) else None),
).reset_index().rename(columns={"topics": "topic_id"})

# parse pieces from topic ID. Three known shapes:
#  old (2021-2024): HORIZON-CL5-YYYY-Dx-CC-NN[-suffix]   (e.g., -two-stage)
#  new (2025+):     HORIZON-CL5-YYYY-CC-Dx-NN[-suffix]   (call & destination swapped)
#  IBA pre-allocations: HORIZON-CL5-YYYY-{NAME}-IBA[-N]  (no destination)
pat_old = re.compile(r"^HORIZON-CL5-(\d{4})-(D\d)-(\d+)-(\d+)(?:-(.+))?$")
pat_new = re.compile(r"^HORIZON-CL5-(\d{4})-(\d+)-(D\d)-(\d+)(?:-(.+))?$")
pat_iba = re.compile(r"^HORIZON-CL5-(\d{4})-([A-Z0-9]+)-IBA(?:-(\d+))?$")

def parse(t):
    m = pat_old.match(t)
    if m:
        return pd.Series([m.group(1), m.group(2), m.group(3), m.group(4), m.group(5), "standard"],
                         index=["year", "destination", "call_num", "topic_num", "suffix", "kind"])
    m = pat_new.match(t)
    if m:
        return pd.Series([m.group(1), m.group(3), m.group(2), m.group(4), m.group(5), "standard"],
                         index=["year", "destination", "call_num", "topic_num", "suffix", "kind"])
    m = pat_iba.match(t)
    if m:
        return pd.Series([m.group(1), None, m.group(2), m.group(3), None, "IBA"],
                         index=["year", "destination", "call_num", "topic_num", "suffix", "kind"])
    return pd.Series([None]*6, index=["year", "destination", "call_num", "topic_num", "suffix", "kind"])

parts = agg["topic_id"].apply(parse)
agg = pd.concat([agg, parts], axis=1)

# join titles
agg = agg.merge(topic_titles.rename(columns={"topic": "topic_id", "title": "topic_title"}),
                on="topic_id", how="left")

# map funding scheme -> topic type
SCHEME_MAP = {
    "HORIZON-RIA": "RIA",
    "HORIZON-IA": "IA",
    "HORIZON-CSA": "CSA",
    "HORIZON-COFUND": "COFUND",
}
agg["topic_type"] = agg["dominant_scheme"].map(SCHEME_MAP)

# Destination short -> full name (Horizon Europe CL5 WP 2021-2027)
DEST_MAP = {
    "D1": "Climate sciences and responses",
    "D2": "Cross-sectoral solutions for the climate transition",
    "D3": "Sustainable, secure and competitive energy supply",
    "D4": "Efficient, sustainable and inclusive energy use",
    "D5": "Clean and competitive solutions for all transport modes",
    "D6": "Safe, resilient transport and smart mobility services for passengers and goods",
}
agg["destination_name"] = agg["destination"].map(DEST_MAP)

# F&T Portal topic page URL (canonical)
PORTAL_TPL = "https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/opportunities/topic-details/{tid}"
agg["portal_link"] = agg["topic_id"].apply(lambda t: PORTAL_TPL.format(tid=t))

agg["framework"] = "Horizon Europe"
agg["cluster"] = "CL5"

# For IBA topics, override topic_type to "IBA"
agg.loc[agg["kind"] == "IBA", "topic_type"] = "IBA"

# tidy column order
cols = ["framework", "year", "cluster", "destination", "destination_name",
        "master_call", "topic_id", "topic_title", "topic_type", "kind",
        "funded_projects", "sum_ec", "sum_total",
        "portal_link", "dominant_scheme", "suffix"]
agg = agg[cols].sort_values(["year", "destination", "topic_id"]).reset_index(drop=True)

print(f"Derived topics rows: {len(agg)}")
print(f"Year coverage: {sorted(agg['year'].dropna().unique())}")
print(f"Topics missing title: {agg['topic_title'].isna().sum()}")
print(f"Topics missing topic_type: {agg['topic_type'].isna().sum()}")

agg.to_pickle(PARSED / "topics_from_cordis.pkl")
agg.to_csv(PARSED / "topics_from_cordis.csv", index=False)
print(f"Saved to {PARSED / 'topics_from_cordis.pkl'}")
