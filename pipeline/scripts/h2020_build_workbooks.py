"""Horizon 2020 (2014-2020): build per-Societal-Challenge workbooks aligned to
the Horizon Europe ones.

Scopes (energy/environment/economy-relevant):
  SC2  Food, agriculture, forestry, marine, bioeconomy   (excl. BBI JTI)
  SC3  Secure, clean and efficient energy                (excl. FCH JTI)
  SC4  Smart, green and integrated transport             (excl. CS2/S2R/SESAR/FCH JTIs)
  SC5  Climate action, environment, resources, raw materials
  JTI  the five JTIs that became today's JUs: FCH(->CleanH2), CS2(->Clean Aviation),
       S2R(->Europe's Rail), SESAR(->SESAR3), BBI(->CBE)

Alignment notes vs HE workbooks (same 25/18/15/12 columns):
  - H2020 has no Destination layer; Destination = topic-prefix family
    (LCE, EE, LC-SC3-RES, MG, SFS, LC-CLA, ...), Destination Name from a map
  - Topic layer derived from CORDIS only: indicative budget / dates / TRL /
    keywords left blank (F&T Portal coverage for H2020 topics is partial);
    Call Status = Closed, Award Status = Signed for all rows
  - Year = first 20xx token in the topic ID (multi-year topics take first year)

Outputs: H2020_SC2/SC3/SC4/SC5/JTI_Topics_and_Projects.xlsx (+ parsed pkls)
"""
import re
import subprocess
import sys
from pathlib import Path
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw" / "cordis_h2020"
PARSED = ROOT / "parsed"

JTI_PAT = re.compile(r"^(FCH|JTI-CS2|CS2|S2R|SESAR|BBI)[-.]", re.IGNORECASE)

SCOPES = {
    "SC1": {"legal": "H2020-EU.3.1.", "jti": False,
            "label": "H2020 SC1 Health"},
    "SC2": {"legal": "H2020-EU.3.2.", "jti": False,
            "label": "H2020 SC2 Food/Agri/Bioeconomy"},
    "SC3": {"legal": "H2020-EU.3.3.", "jti": False,
            "label": "H2020 SC3 Energy"},
    "SC4": {"legal": "H2020-EU.3.4.", "jti": False,
            "label": "H2020 SC4 Transport"},
    "SC5": {"legal": "H2020-EU.3.5.", "jti": False,
            "label": "H2020 SC5 Climate/Environment/Resources"},
    "SC6": {"legal": "H2020-EU.3.6.", "jti": False,
            "label": "H2020 SC6 Europe in a changing world (inclusive societies)"},
    "SC7": {"legal": "H2020-EU.3.7.", "jti": False,
            "label": "H2020 SC7 Secure societies"},
    "JTI": {"legal": None, "jti": True,
            "label": "H2020 JTIs (FCH/CS2/S2R/SESAR/BBI)"},
}

DEST_NAME = {
    # SC3 energy
    "LCE": "Competitive Low-Carbon Energy (WP2014-17)",
    "EE": "Energy Efficiency",
    "SIE": "SME Instrument - Energy",
    "LC-SC3-RES": "Renewable energy technologies",
    "LC-SC3-EE": "Energy efficiency (WP2018-20)",
    "LC-SC3-ES": "Smart energy systems and grids",
    "LC-SC3-B4E": "Batteries for e-mobility (B4E)",
    "LC-SC3-EC": "Energy consumers / smart citizen-centred energy",
    "LC-SC3-CC": "Cross-cutting energy issues",
    "LC-SC3-NZE": "Near-zero emissions: CCS/CCU",
    "LC-SC3-JA": "Joint actions with Member States",
    "SCC": "Smart Cities and Communities",
    "LC-BAT": "Batteries",
    "LC-GD": "European Green Deal call (2020)",
    "SMEINST": "SME Instrument (allocated to this challenge)",
    "FTIPILOT": "Fast Track to Innovation pilot",
    # SC4 transport
    "MG": "Mobility for Growth",
    "LC-MG": "Low-carbon mobility (WP2018-20)",
    "GV": "Green Vehicles",
    "LC-GV": "Green Vehicles (WP2018-20)",
    "ART": "Automated Road Transport",
    "IT": "Inducement prizes / innovative transport",
    # SC2 food/bio
    "SFS": "Sustainable Food Security",
    "LC-SFS": "Sustainable Food Security (low-carbon)",
    "CE-SFS": "Sustainable Food Security (circular)",
    "BG": "Blue Growth (marine/maritime)",
    "RUR": "Rural Renaissance",
    "CE-RUR": "Rural Renaissance (circular)",
    "FNR": "Food and Natural Resources",
    "CE-FNR": "Food and Natural Resources (circular)",
    "LC-FNR": "Food and Natural Resources (low-carbon)",
    "ISIB": "Innovative, Sustainable and Inclusive Bioeconomy (WP2014-15)",
    "BB": "Bio-based innovation",
    # SC5 climate/env
    "LC-CLA": "Climate action in support of the Paris Agreement",
    "CE-SC5": "Circular economy and raw materials",
    "SC5": "Climate, environment, resource efficiency and raw materials (general)",
    "WATER": "Water innovation",
    "WASTE": "Waste: a resource to recycle, reuse, recover",
    "CIRC": "Circular economy (WP2016-17)",
    "DRS": "Disaster resilience",
    # JTI
    "FCH": "Fuel Cells and Hydrogen 2 JU (-> Clean Hydrogen)",
    "JTI-CS2": "Clean Sky 2 JU (-> Clean Aviation)",
    "S2R": "Shift2Rail JU (-> Europe's Rail)",
    "SESAR": "SESAR JU (-> SESAR 3)",
    "BBI": "Bio-based Industries JU (-> CBE)",
}

def to_float(x):
    if pd.isna(x):
        return None
    try:
        return float(str(x).replace(",", "."))
    except ValueError:
        return None

def family(tid):
    t = str(tid).upper()
    m = JTI_PAT.match(t)
    if m:
        return m.group(1)
    m = re.match(r"^([A-Z]+(?:-[A-Z0-9]+)*?)-\d", t)
    return m.group(1) if m else (t.split("-")[0] if "-" in t else t)

def year_of(tid):
    m = re.search(r"(20\d\d)", str(tid))
    return m.group(1) if m else None

print("Loading CORDIS H2020 bulk...")
proj_all = pd.read_excel(RAW / "project.xlsx")
proj_all["eu"] = proj_all["ecMaxContribution"].apply(to_float)
proj_all["total"] = proj_all["totalCost"].apply(to_float)
tt = pd.read_excel(RAW / "topics.xlsx")[["topic", "title"]].drop_duplicates("topic")
title_map = tt.set_index("topic")["title"].to_dict()
wl = pd.read_excel(RAW / "webLink.xlsx")
homepage = (wl[(wl["type"] == "relatedWebsite") & (wl["represents"] == "project")]
            .groupby("projectID")["physUrl"].first().to_dict())
org = pd.read_excel(RAW / "organization.xlsx", usecols=["projectID", "name", "country", "role"])
coords = org[org["role"] == "coordinator"].drop_duplicates("projectID").set_index("projectID")
counts = org.groupby("projectID").size().to_dict()
countries = org.groupby("projectID")["country"].apply(lambda s: ",".join(sorted(set(s.dropna())))).to_dict()

SCHEME_MAP = {"RIA": "RIA", "IA": "IA", "CSA": "CSA", "COFUND": "COFUND", "SME": "SME", "FTI": "FTI"}
def scheme_short(s):
    if not isinstance(s, str):
        return None
    u = s.upper()
    for k in ["COFUND", "CSA", "RIA", "FTI"]:
        if k in u:
            return k
    if "SME" in u:
        return "SME"
    if re.search(r"\bIA\b|-IA\b|IA$", u):
        return "IA"
    return None

TOPIC_WIDTHS = {
    "Framework": 22, "Year": 8, "Cluster/Pillar": 14, "Destination": 16, "Destination Name": 44,
    "Call ID": 34, "Call Title": 40, "Topic ID": 30, "Topic Title": 60, "Topic Type": 12,
    "TRL": 10, "EU Contribution per Project (EUR M)": 16, "Indicative Budget (EUR M)": 14,
    "Expected Number of Projects": 12, "Opening Date": 13, "Deadline": 13, "Stage": 14,
    "Keywords": 24, "EU Portal Link": 50, "Work Programme PDF": 24, "Notes": 50,
    "Call Status": 14, "Award Status": 14, "Funded Projects (signed)": 12,
    "Signed EU Contribution (EUR M)": 14,
}
PROJ_WIDTHS = {
    "Topic ID": 28, "Project Acronym": 18, "Project Full Name": 50, "Grant Agreement ID": 16,
    "Coordinator": 36, "Coordinator Country": 14, "Number of Participants": 12,
    "Participant Countries": 30, "Start Date": 12, "End Date": 12, "EU Contribution (EUR)": 16,
    "Total Cost (EUR)": 16, "Status": 12, "Project Website": 30, "CORDIS Link": 40,
    "EU Portal Link": 50, "Objective": 80, "Notes": 20,
}
PORTAL_TPL = "https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/opportunities/topic-details/{tid}"
PROJECT_PORTAL = "https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/how-to-participate/projects-results/project-details/{rcn}"
CORDIS_LINK = "https://cordis.europa.eu/project/id/{id}"

def write_sheet(wb, name, df, widths, header_rgb):
    ws = wb.create_sheet(name)
    header_font = Font(bold=True, color="FFFFFF", size=11)
    header_fill = PatternFill("solid", fgColor=header_rgb)
    for c_idx, h in enumerate(df.columns, start=1):
        cell = ws.cell(row=1, column=c_idx, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(vertical="center", wrap_text=True)
        ws.column_dimensions[cell.column_letter].width = widths.get(h, 16)
    for r_idx, rec in enumerate(df.to_dict("records"), start=2):
        for c_idx, h in enumerate(df.columns, start=1):
            v = rec.get(h)
            if v is not None and not isinstance(v, (list, dict)) and pd.isna(v):
                v = None
            ws.cell(row=r_idx, column=c_idx, value=v)
    ws.freeze_panes = "A2"

is_jti = proj_all["topics"].astype(str).str.upper().str.match(JTI_PAT)

for key, conf in SCOPES.items():
    if conf["jti"]:
        proj = proj_all[is_jti].copy()
    else:
        proj = proj_all[(proj_all["legalBasis"] == conf["legal"]) & (~is_jti)].copy()
    pkl = PARSED / f"h2020_{key.lower()}_projects.pkl"
    proj.to_pickle(pkl)

    agg = proj.groupby("topics").agg(
        funded=("id", "count"),
        sum_ec=("eu", "sum"),
        master_call=("masterCall", lambda s: s.mode().iat[0] if len(s.mode()) else None),
        dominant_scheme=("fundingScheme", lambda s: s.mode().iat[0] if len(s.mode()) else None),
    ).reset_index().rename(columns={"topics": "topic_id"})

    rows = []
    for _, r in agg.iterrows():
        tid = r["topic_id"]
        fam = family(tid)
        rows.append({
            "Framework": "Horizon 2020",
            "Year": year_of(tid),
            "Cluster/Pillar": f"H2020-{key}",
            "Destination": fam,
            "Destination Name": DEST_NAME.get(fam),
            "Call ID": r["master_call"],
            "Call Title": None,
            "Topic ID": tid,
            "Topic Title": title_map.get(tid),
            "Topic Type": scheme_short(r["dominant_scheme"]),
            "TRL": None,
            "EU Contribution per Project (EUR M)": None,
            "Indicative Budget (EUR M)": None,
            "Expected Number of Projects": None,
            "Opening Date": None,
            "Deadline": None,
            "Stage": None,
            "Keywords": None,
            "EU Portal Link": PORTAL_TPL.format(tid=str(tid).lower()),
            "Work Programme PDF": None,
            "Notes": "H2020 topic derived from CORDIS (indicative budget/dates not collected; F&T coverage partial for H2020)",
            "Call Status": "Closed",
            "Award Status": "Signed",
            "Funded Projects (signed)": int(r["funded"]),
            "Signed EU Contribution (EUR M)": round((r["sum_ec"] or 0) / 1e6, 3),
        })
    topics_df = pd.DataFrame(rows).sort_values(["Year", "Destination", "Topic ID"], na_position="last").reset_index(drop=True)

    proj_rows = []
    for _, r in proj.iterrows():
        pid = r["id"]
        proj_rows.append({
            "Topic ID": r["topics"],
            "Project Acronym": r["acronym"],
            "Project Full Name": r["title"],
            "Grant Agreement ID": pid,
            "Coordinator": coords.loc[pid]["name"] if pid in coords.index else None,
            "Coordinator Country": coords.loc[pid]["country"] if pid in coords.index else None,
            "Number of Participants": counts.get(pid),
            "Participant Countries": countries.get(pid),
            "Start Date": r["startDate"],
            "End Date": r["endDate"],
            "EU Contribution (EUR)": r["eu"],
            "Total Cost (EUR)": r["total"],
            "Status": r["status"],
            "Project Website": homepage.get(pid),
            "CORDIS Link": CORDIS_LINK.format(id=pid),
            "EU Portal Link": PROJECT_PORTAL.format(rcn=r["rcn"]),
            "Objective": r["objective"],
            "Notes": None,
        })
    projects_df = pd.DataFrame(proj_rows).sort_values(["Topic ID", "Project Acronym"]).reset_index(drop=True)

    out = ROOT.parent / "data" / f"H2020_{key}_Topics_and_Projects.xlsx"
    wb = Workbook()
    wb.remove(wb.active)
    write_sheet(wb, "Topics", topics_df, TOPIC_WIDTHS, "2C5D99")
    write_sheet(wb, "Projects", projects_df, PROJ_WIDTHS, "2F6B3D")
    wb.save(out)
    print(f"{key}: topics {len(topics_df)} | projects {len(projects_df)} | EU {proj['eu'].sum()/1e9:.2f}B -> {out.name}", flush=True)
    print(topics_df.groupby("Destination")["Signed EU Contribution (EUR M)"].agg(["count", "sum"]).sort_values("sum", ascending=False).head(8).to_string(float_format=lambda x: f"{x:.0f}"), flush=True)

    for script in ["add_participants_sheet.py", "add_organisations_sheet.py"]:
        r = subprocess.run([sys.executable, str(ROOT / "scripts" / script),
                            f"h2020_{key.lower()}_projects", out.name, "cordis_h2020"],
                           capture_output=True, text=True, cwd=ROOT)
        print("  " + (r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr.strip()[-200:]), flush=True)

print("ALL DONE")
