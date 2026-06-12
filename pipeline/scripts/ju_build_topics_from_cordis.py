"""Energy/environment Joint Undertakings: filter CORDIS, derive topic skeleton.

Covers five JUs (signed projects only -- each JU has its own work programme,
so no not-yet-signed topic list is collected here):
  CLEANH2        Clean Hydrogen JU        (HORIZON-JTI-CLEANH2-*, HORIZON-JU-CLEANH2-*)
  CBE            Circular Bio-based Europe JU (HORIZON-JU-CBE-*)
  CLEAN-AVIATION Clean Aviation JU        (HORIZON-JU-CLEAN-AVIATION-*)
  ER             Europe's Rail JU         (HORIZON-ER-JU-*)
  SESAR          SESAR 3 JU               (HORIZON-SESAR-*)

JU topic IDs have heterogeneous grammars (types/work-areas inside the ID),
so only Year (first 20xx) and JU membership are parsed; the JU code goes to
the Destination column in the merged workbook.

Outputs: parsed/ju_projects.pkl, parsed/ju_topic_titles.pkl,
         parsed/ju_topics_from_cordis.pkl/.csv
"""
import re
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw" / "cordis_he"
PARSED = ROOT / "parsed"

JU_PREFIXES = {
    "CLEANH2": ("HORIZON-JTI-CLEANH2", "HORIZON-JU-CLEANH2"),
    "CBE": ("HORIZON-JU-CBE",),
    "CLEAN-AVIATION": ("HORIZON-JU-CLEAN-AVIATION",),
    "ER": ("HORIZON-ER-JU",),
    "SESAR": ("HORIZON-SESAR",),
}

def which_ju(topic):
    t = str(topic).upper()
    for ju, pfxs in JU_PREFIXES.items():
        if t.startswith(pfxs):
            return ju
    return None

proj_all = pd.read_excel(RAW / "project.xlsx")
proj_all["_ju"] = proj_all["topics"].apply(which_ju)
proj = proj_all[proj_all["_ju"].notna()].copy()
proj.to_pickle(PARSED / "ju_projects.pkl")
print(f"JU projects: {len(proj)}")
print(proj["_ju"].value_counts().to_string())

tt = pd.read_excel(RAW / "topics.xlsx")
ttj = tt[tt["topic"].apply(which_ju).notna()][["topic", "title"]].drop_duplicates("topic")
ttj.to_pickle(PARSED / "ju_topic_titles.pkl")
print(f"JU unique topics in CORDIS: {len(ttj)}")

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

agg["ju"] = agg["topic_id"].apply(which_ju)
agg["year"] = agg["topic_id"].str.extract(r"(20\d\d)")

def scheme_short(s):
    if not isinstance(s, str):
        return None
    u = s.upper()
    if "COFUND" in u: return "COFUND"
    if "CSA" in u: return "CSA"
    if "RIA" in u: return "RIA"
    if re.search(r"\bIA\b|[-_]IA\b|IA$", u): return "IA"
    if "IBA" in u: return "IBA"
    return None

agg["topic_type"] = agg["dominant_scheme"].apply(scheme_short)
agg = agg.merge(ttj.rename(columns={"topic": "topic_id", "title": "topic_title"}),
                on="topic_id", how="left")

print(f"Derived topics rows: {len(agg)}")
print(f"By JU:\n{agg['ju'].value_counts().to_string()}")
print(f"Year range: {sorted(agg['year'].dropna().unique())}")
print(f"Missing title: {agg['topic_title'].isna().sum()} | missing type: {agg['topic_type'].isna().sum()}")

agg.to_pickle(PARSED / "ju_topics_from_cordis.pkl")
agg.to_csv(PARSED / "ju_topics_from_cordis.csv", index=False)
print(f"Saved {PARSED / 'ju_topics_from_cordis.pkl'}")
