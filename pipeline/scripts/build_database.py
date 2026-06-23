"""Build horizon.sqlite — the single master database behind the Pivot Explorer.

Scope: Horizon 2020 + Horizon Europe only (CL4/5/6, EU Missions, H2020-SC2/3/4/5,
H2020-JTI). Sources:
  data/<block>_Topics_and_Projects.xlsx   curated 5-sheet workbooks (Topics/Projects/
                                          Participants/Organisations/People)
  raw/people/<grant>.json                 OpenAlex works per grant (authorships)
  raw/works_doi.json                      DOI / landing-page links per work

Schema (one file, fully relational):
  topic, topic_keyword, project, unit, project_unit,
  researcher, project_researcher, work, work_project, work_author

Refresh cycle: re-collect (raw → workbooks) → build_database.py → export_webapp.py.
Stdlib + pandas only.
"""
import sqlite3, json, re, html as _html
from pathlib import Path
from collections import defaultdict
import pandas as pd, warnings
warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT.parent / "data"
CACHE = ROOT / "raw" / "people"
DOIJSON = ROOT / "raw" / "works_doi.json"
OAJSON = ROOT / "raw" / "works_oa.json"
DB = ROOT.parent / "horizon.sqlite"

PROGS = {"CL5": "CL5", "CL6": "CL6", "MISS": "MISS", "CL4": "CL4",
         "CL1": "CL1", "CL2": "CL2", "CL3": "CL3",
         "H2020_SC3": "H2020-SC3", "H2020_SC4": "H2020-SC4", "H2020_SC2": "H2020-SC2",
         "H2020_SC5": "H2020-SC5", "H2020_JTI": "H2020-JTI",
         "H2020_SC1": "H2020-SC1", "H2020_SC6": "H2020-SC6", "H2020_SC7": "H2020-SC7"}
FW = {b: ("Horizon 2020" if b.startswith("H2020") else "Horizon Europe") for b in PROGS.values()}

_TAG = re.compile(r"<[^>]+>")
def clean(v):
    if v is None or (isinstance(v, float) and pd.isna(v)): return None
    s = _TAG.sub("", _html.unescape(str(v)))
    return re.sub(r"\s+", " ", s).strip() or None
def nz(v):
    return None if v is None or (isinstance(v, float) and pd.isna(v)) or (isinstance(v, str) and not v.strip()) else v
def s10(v):
    return str(v)[:10] if pd.notna(v) else None
def eur(x):
    if pd.isna(x): return 0
    try: return round(float(str(x).replace(",", ".")))
    except ValueError: return 0
def numM(x):
    v = nz(x)
    try: return round(float(v), 3) if v is not None else None
    except (ValueError, TypeError): return None

topics, topic_kw = [], []          # topic rows; (topic_id, keyword)
projects = []                      # project rows
units = {}                         # org_id -> dict
project_unit = []                  # (grant, org_id, ec)
people_acc = {}                    # author_id -> merged researcher
proj_research = set()             # (grant, author_id)
seen_topic, seen_grant = set(), set()

for f in sorted(DATA.glob("*_Topics_and_Projects.xlsx")):
    stem = f.name.split("_Topics")[0]
    if stem not in PROGS:          # skip JU and any non-Horizon block
        continue
    blk = PROGS[stem]
    xl = pd.ExcelFile(f)

    t = pd.read_excel(f, sheet_name="Topics")
    for _, r in t.iterrows():
        tid = nz(r.get("Topic ID"))
        if not tid or tid in seen_topic: continue
        seen_topic.add(tid)
        topics.append((tid, clean(r.get("Topic Title")), nz(r.get("Destination")), blk,
                       nz(r.get("Topic Type")), numM(r.get("Indicative Budget (EUR M)")), nz(r.get("Call Status"))))
        for k in str(nz(r.get("Keywords")) or "").split(";"):
            k = k.strip()
            if k: topic_kw.append((tid, k))

    p = pd.read_excel(f, sheet_name="Projects")
    for _, r in p.iterrows():
        if pd.isna(r.get("Grant Agreement ID")): continue
        gid = int(r["Grant Agreement ID"])
        if gid in seen_grant: continue
        seen_grant.add(gid)
        projects.append((gid, clean(r.get("Project Acronym")), clean(r.get("Project Full Name")), blk,
                         (None if pd.isna(r.get("EU Contribution (EUR)")) else round(float(r["EU Contribution (EUR)"]))),
                         s10(r.get("Start Date")), s10(r.get("End Date")), nz(r.get("Status")),
                         clean(r.get("Coordinator")), nz(r.get("Coordinator Country")),
                         nz(r.get("Topic ID")), clean(r.get("Objective"))))

    pa = pd.read_excel(f, sheet_name="Participants")
    for _, r in pa.iterrows():
        if pd.isna(r.get("Grant Agreement ID")) or pd.isna(r.get("Organisation ID")): continue
        gid = int(r["Grant Agreement ID"]); oid = str(int(r["Organisation ID"]))
        ec = eur(r.get("EC Contribution (EUR)"))
        u = units.get(oid)
        if u is None:
            u = units[oid] = {"name": clean(r.get("Organisation Name")), "country": nz(r.get("Country")),
                              "activity_type": nz(r.get("Activity Type")), "sme": 1 if r.get("SME") in (True, "true", "True") else 0,
                              "total_ec": 0, "projects": set(), "coord": 0}
        u["total_ec"] += ec; u["projects"].add(gid)
        if str(r.get("Role", "")).lower() == "coordinator": u["coord"] += 1
        project_unit.append((gid, oid, ec))

    if "People" in xl.sheet_names:
        pe = pd.read_excel(f, sheet_name="People")
        for _, r in pe.iterrows():
            aid = nz(r.get("Author ID"))
            if not aid: continue
            a = people_acc.get(aid)
            if a is None:
                a = people_acc[aid] = {"name": clean(r.get("Name")), "orcid": nz(r.get("ORCID")),
                                       "works": 0, "lead": 0, "inst": defaultdict(int), "ctry": defaultdict(int),
                                       "topics": defaultdict(int)}
            w = int(r["Works"]) if pd.notna(r.get("Works")) else 0
            a["works"] += w
            a["lead"] += int(r["Lead Works"]) if pd.notna(r.get("Lead Works")) else 0
            if nz(r.get("Main Institution")): a["inst"][clean(r.get("Main Institution"))] += w
            if nz(r.get("Country")): a["ctry"][r["Country"]] += w
            for tp in str(nz(r.get("Top Topics")) or "").split(", "):
                if tp.strip(): a["topics"][tp.strip()] += w
            for g in str(nz(r.get("Project Grant IDs")) or "").split("; "):
                if g.strip().isdigit() and int(g) in seen_grant: proj_research.add((int(g), aid))

print(f"topics {len(topics)} | projects {len(projects)} | units {len(units)}")

# researchers: keep those with real output (>=1 lead OR >=2 works), like the website set
def top(d): return max(d.items(), key=lambda x: x[1])[0] if d else None
researchers, keep_auth = [], set()
for aid, a in people_acc.items():
    if a["lead"] < 1 and a["works"] < 2: continue
    keep_auth.add(aid)
    researchers.append((aid, a["name"], a["orcid"], top(a["ctry"]), top(a["inst"]), a["works"], a["lead"],
                        ", ".join(t for t, _ in sorted(a["topics"].items(), key=lambda x: -x[1])[:5]) or None))
proj_research = [(g, aid) for (g, aid) in proj_research if aid in keep_auth]
print(f"researchers {len(researchers)} (filtered) | project-researcher links {len(proj_research)}")

# works from the OpenAlex cache (Horizon grants only)
doi_map = json.loads(DOIJSON.read_text()) if DOIJSON.exists() else {}
oa_map = json.loads(OAJSON.read_text()) if OAJSON.exists() else {}
works, seen_work = [], set()
work_project, work_author = set(), set()
for cf in CACHE.glob("*.json"):
    gid = int(cf.stem)
    if gid not in seen_grant: continue
    for w in json.loads(cf.read_text()):
        wid = w["id"].rsplit("/", 1)[-1]
        if wid not in seen_work:
            seen_work.add(wid)
            link = doi_map.get(wid, {})
            doi = (link.get("doi") or "").replace("https://doi.org/", "") or None
            oa = oa_map.get(wid)
            is_oa = (1 if oa.get("is_oa") else 0) if oa else None
            oa_status = oa.get("oa_status") if oa else None
            works.append((wid, clean(w.get("display_name")) or "(untitled)", w.get("publication_year"),
                          doi, link.get("url") or link.get("doi") or w["id"], is_oa, oa_status))
        work_project.add((wid, gid))
        for au in w.get("authorships") or []:
            aid = ((au.get("author") or {}).get("id") or "").rsplit("/", 1)[-1]
            if aid in keep_auth: work_author.add((wid, aid))
work_project, work_author = sorted(work_project), sorted(work_author)
print(f"works {len(works)} | work-project {len(work_project)} | work-author {len(work_author)}")

# ---- write sqlite ----
DB.unlink(missing_ok=True)
con = sqlite3.connect(DB); cur = con.cursor()
cur.executescript("""
CREATE TABLE topic(id TEXT PRIMARY KEY, title TEXT, destination TEXT, block TEXT, type TEXT, budget_eur_m REAL, status TEXT);
CREATE TABLE topic_keyword(topic_id TEXT, keyword TEXT);
CREATE TABLE project(grant_id INTEGER PRIMARY KEY, acronym TEXT, title TEXT, block TEXT, eu_contribution_eur INTEGER,
  start_date TEXT, end_date TEXT, status TEXT, coordinator TEXT, coordinator_country TEXT, topic_id TEXT, objective TEXT);
CREATE TABLE unit(org_id TEXT PRIMARY KEY, name TEXT, country TEXT, activity_type TEXT, sme INTEGER,
  total_ec_eur INTEGER, n_projects INTEGER, coordinator_count INTEGER);
CREATE TABLE project_unit(grant_id INTEGER, org_id TEXT, ec_eur INTEGER);
CREATE TABLE researcher(author_id TEXT PRIMARY KEY, name TEXT, orcid TEXT, country TEXT, main_institution TEXT,
  works_total INTEGER, lead_works INTEGER, topics TEXT);
CREATE TABLE project_researcher(grant_id INTEGER, author_id TEXT);
CREATE TABLE work(work_id TEXT PRIMARY KEY, title TEXT, year INTEGER, doi TEXT, url TEXT, is_oa INTEGER, oa_status TEXT);
CREATE TABLE work_project(work_id TEXT, grant_id INTEGER);
CREATE TABLE work_author(work_id TEXT, author_id TEXT);
CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT);
""")
cur.executemany("INSERT INTO topic VALUES (?,?,?,?,?,?,?)", topics)
cur.executemany("INSERT INTO topic_keyword VALUES (?,?)", topic_kw)
cur.executemany("INSERT INTO project VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", projects)
cur.executemany("INSERT INTO unit VALUES (?,?,?,?,?,?,?,?)",
                [(oid, u["name"], u["country"], u["activity_type"], u["sme"], u["total_ec"], len(u["projects"]), u["coord"]) for oid, u in units.items()])
cur.executemany("INSERT INTO project_unit VALUES (?,?,?)", project_unit)
cur.executemany("INSERT INTO researcher VALUES (?,?,?,?,?,?,?,?)", researchers)
cur.executemany("INSERT INTO project_researcher VALUES (?,?)", proj_research)
cur.executemany("INSERT INTO work VALUES (?,?,?,?,?,?,?)", works)
cur.executemany("INSERT INTO work_project VALUES (?,?)", work_project)
cur.executemany("INSERT INTO work_author VALUES (?,?)", work_author)
cur.executemany("INSERT INTO meta VALUES (?,?)", [
    ("blocks", json.dumps([{"k": k, "fw": FW[k]} for k in sorted(set(PROGS.values()))], ensure_ascii=False)),
    ("doi_pct", str(round(sum(1 for w in works if w[3]) / max(1, len(works)) * 100)))])
for s in ["CREATE INDEX i_tk ON topic_keyword(topic_id)", "CREATE INDEX i_pu ON project_unit(grant_id)",
          "CREATE INDEX i_pu2 ON project_unit(org_id)", "CREATE INDEX i_pr ON project_researcher(grant_id)",
          "CREATE INDEX i_pr2 ON project_researcher(author_id)", "CREATE INDEX i_wp ON work_project(grant_id)",
          "CREATE INDEX i_wp2 ON work_project(work_id)", "CREATE INDEX i_wa ON work_author(work_id)",
          "CREATE INDEX i_wa2 ON work_author(author_id)", "CREATE INDEX i_proj_topic ON project(topic_id)"]:
    cur.execute(s)
con.commit(); con.close()
import os
print(f"\nhorizon.sqlite written: {os.path.getsize(DB)//1024//1024} MB at {DB}")
