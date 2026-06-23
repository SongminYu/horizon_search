"""Incrementally merge new project blocks into the existing horizon.sqlite.

Adds the 6 thematic-expansion blocks (CL1/CL2/CL3 + H2020-SC1/SC6/SC7) to the
committed master DB **without rebuilding the existing 9 blocks** — whose transient
workbooks are gone and which include the specially-curated CL5 (not reproducible).
Existing rows are preserved; only new blocks are inserted, and the global
aggregates that genuinely change are updated:
  - unit.total_ec_eur / n_projects : recomputed exactly from the full project_unit
  - unit.coordinator_count         : existing + new-block coordinator roles
  - researcher.works_total/lead_works for researchers who ALSO appear in a new block

Project / unit / topic data come from the new-block workbooks (CORDIS — complete,
no network). The people / works layer is computed DIRECTLY from the OpenAlex cache
(raw/people/<grant>.json), NOT from the workbook People sheet. This makes the
daily backfill clean and idempotent: as the cache fills (1000 req/day free budget),
just restore horizon.sqlite from backup and re-run this script — researchers/works grow
to match whatever is cached. With an empty cache, new blocks simply carry no
researchers/works yet (honest, like CSA projects).

Known limitation: an author sub-threshold in the OLD blocks (absent from the DB)
who also appears in a NEW block is evaluated on their new-block totals only.

Usage:  python3 pipeline/scripts/merge_new_blocks.py    (operates in place; back up horizon.sqlite first;
         to re-run, restore the backup first — this script only ADDS)
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
DB = ROOT.parent / "horizon.sqlite"

NEW = {"CL1": "CL1", "CL2": "CL2", "CL3": "CL3",
       "H2020_SC1": "H2020-SC1", "H2020_SC6": "H2020-SC6", "H2020_SC7": "H2020-SC7"}
def fw(b): return "Horizon 2020" if b.startswith("H2020") else "Horizon Europe"

# ---- helpers (identical to build_database.py) ----
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
def topkey(d): return max(d.items(), key=lambda x: x[1])[0] if d else None
def is_lead(a): return a.get("author_position") in ("first", "last") or bool(a.get("is_corresponding"))

con = sqlite3.connect(DB); cur = con.cursor()

# ---- existing state (preserved) ----
existing_grants = {g for (g,) in cur.execute("SELECT grant_id FROM project")}
existing_topics = {t for (t,) in cur.execute("SELECT id FROM topic")}
existing_units = {o for (o,) in cur.execute("SELECT org_id FROM unit")}
existing_res = {a for (a,) in cur.execute("SELECT author_id FROM researcher")}
existing_blocks = [b for (b,) in cur.execute("SELECT DISTINCT block FROM project")]
existing_works = {w for (w,) in cur.execute("SELECT work_id FROM work")}
existing_wp = set(cur.execute("SELECT work_id, grant_id FROM work_project"))
existing_wa = set(cur.execute("SELECT work_id, author_id FROM work_author"))
print(f"existing: {len(existing_grants)} projects | {len(existing_topics)} topics | "
      f"{len(existing_units)} units | {len(existing_res)} researchers | {len(existing_works)} works")

# ---- accumulate new-block CORDIS data (Topics / Projects / Participants) ----
seen_topic = set(existing_topics); seen_grant = set(existing_grants)
new_topics, new_topic_kw, new_projects, new_pu = [], [], [], []
unit_attr = {}; new_coord = defaultdict(int); new_grants = set()

for stem, blk in NEW.items():
    f = DATA / f"{stem}_Topics_and_Projects.xlsx"
    if not f.exists():
        raise SystemExit(f"missing workbook: {f}")
    t = pd.read_excel(f, sheet_name="Topics")
    for _, r in t.iterrows():
        tid = nz(r.get("Topic ID"))
        if not tid or tid in seen_topic: continue
        seen_topic.add(tid)
        new_topics.append((tid, clean(r.get("Topic Title")), nz(r.get("Destination")), blk,
                           nz(r.get("Topic Type")), numM(r.get("Indicative Budget (EUR M)")), nz(r.get("Call Status"))))
        for k in str(nz(r.get("Keywords")) or "").split(";"):
            k = k.strip()
            if k: new_topic_kw.append((tid, k))

    p = pd.read_excel(f, sheet_name="Projects")
    for _, r in p.iterrows():
        if pd.isna(r.get("Grant Agreement ID")): continue
        gid = int(r["Grant Agreement ID"])
        if gid in seen_grant: continue
        seen_grant.add(gid); new_grants.add(gid)
        new_projects.append((gid, clean(r.get("Project Acronym")), clean(r.get("Project Full Name")), blk,
                             (None if pd.isna(r.get("EU Contribution (EUR)")) else round(float(r["EU Contribution (EUR)"]))),
                             s10(r.get("Start Date")), s10(r.get("End Date")), nz(r.get("Status")),
                             clean(r.get("Coordinator")), nz(r.get("Coordinator Country")),
                             nz(r.get("Topic ID")), clean(r.get("Objective"))))

    pa = pd.read_excel(f, sheet_name="Participants")
    for _, r in pa.iterrows():
        if pd.isna(r.get("Grant Agreement ID")) or pd.isna(r.get("Organisation ID")): continue
        gid = int(r["Grant Agreement ID"]); oid = str(int(r["Organisation ID"]))
        if gid not in new_grants: continue
        new_pu.append((gid, oid, eur(r.get("EC Contribution (EUR)"))))
        if oid not in unit_attr:
            unit_attr[oid] = (clean(r.get("Organisation Name")), nz(r.get("Country")),
                              nz(r.get("Activity Type")), 1 if r.get("SME") in (True, "true", "True") else 0)
        if str(r.get("Role", "")).lower() == "coordinator": new_coord[oid] += 1

print(f"new: {len(new_projects)} projects | {len(new_topics)} topics | {len(new_pu)} participations | {len(unit_attr)} orgs")

# ---- people + works directly from the OpenAlex cache (new grants) ----
doi_map = json.loads(DOIJSON.read_text()) if DOIJSON.exists() else {}
acc = {}                                   # short author_id -> aggregate
new_works, seen_work = [], set(existing_works)
add_wp = []; wa_pairs = set(); pr_pairs = set()
cached = 0
for gid in new_grants:
    cf = CACHE / f"{gid}.json"
    if not cf.exists(): continue
    cached += 1
    for w in json.loads(cf.read_text()):
        wid = w["id"].rsplit("/", 1)[-1]
        if wid not in seen_work:
            seen_work.add(wid)
            link = doi_map.get(wid, {})
            doi = (link.get("doi") or "").replace("https://doi.org/", "") or None
            new_works.append((wid, clean(w.get("display_name")) or "(untitled)", w.get("publication_year"),
                              doi, link.get("url") or link.get("doi") or w["id"]))
        if (wid, gid) not in existing_wp:
            add_wp.append((wid, gid)); existing_wp.add((wid, gid))
        wtopics = [t["display_name"] for t in (w.get("topics") or [])[:2]]
        for a in w.get("authorships") or []:
            au = a.get("author") or {}
            full = au.get("id")
            if not full: continue
            aid = full.rsplit("/", 1)[-1]
            p = acc.get(aid)
            if p is None:
                p = acc[aid] = {"name": clean(au.get("display_name")) or aid,
                                "orcid": (au.get("orcid") or "").rsplit("/", 1)[-1] or None,
                                "works": 0, "lead": 0, "inst": defaultdict(int),
                                "ctry": defaultdict(int), "topics": defaultdict(int)}
            p["works"] += 1
            if is_lead(a): p["lead"] += 1
            for inst in a.get("institutions") or []:
                nm = inst.get("display_name")
                if nm:
                    p["inst"][nm] += 1
                    if inst.get("country_code"): p["ctry"][inst["country_code"]] += 1
            for tp in wtopics: p["topics"][tp] += 1
            pr_pairs.add((gid, aid)); wa_pairs.add((wid, aid))
print(f"cache: {cached}/{len(new_grants)} new grants cached | +{len(new_works)} works | {len(acc)} authors")

# researchers: existing incremented; new ones pass the same keep-filter (>=1 lead OR >=2 works)
keep = set(existing_res); ins_res, upd_res = [], []
for aid, p in acc.items():
    if aid in existing_res:
        upd_res.append((p["works"], p["lead"], aid))
    elif p["lead"] >= 1 or p["works"] >= 2:
        keep.add(aid)
        ins_res.append((aid, p["name"], p["orcid"], topkey(p["ctry"]), topkey(p["inst"]),
                        p["works"], p["lead"],
                        ", ".join(t for t, _ in sorted(p["topics"].items(), key=lambda x: -x[1])[:5]) or None))
proj_research = sorted({(g, aid) for (g, aid) in pr_pairs if aid in keep})
add_wa = sorted({(wid, aid) for (wid, aid) in wa_pairs if aid in keep and (wid, aid) not in existing_wa})
print(f"researchers: +{len(ins_res)} new, {len(upd_res)} existing updated | "
      f"+{len(proj_research)} links | +{len(add_wa)} work-author")

# ---- write (existing rows untouched) ----
cur.executemany("INSERT OR IGNORE INTO topic VALUES (?,?,?,?,?,?,?)", new_topics)
cur.executemany("INSERT INTO topic_keyword VALUES (?,?)", new_topic_kw)
cur.executemany("INSERT OR IGNORE INTO project VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", new_projects)
cur.executemany("INSERT INTO project_unit VALUES (?,?,?)", new_pu)
cur.executemany("INSERT OR IGNORE INTO unit VALUES (?,?,?,?,?,0,0,0)",
                [(oid, *unit_attr[oid]) for oid in unit_attr if oid not in existing_units])
cur.execute("""UPDATE unit SET
  total_ec_eur=(SELECT COALESCE(SUM(ec_eur),0) FROM project_unit WHERE project_unit.org_id=unit.org_id),
  n_projects =(SELECT COUNT(DISTINCT grant_id) FROM project_unit WHERE project_unit.org_id=unit.org_id)""")
cur.executemany("UPDATE unit SET coordinator_count=coordinator_count+? WHERE org_id=?",
                [(c, oid) for oid, c in new_coord.items()])
cur.executemany("INSERT INTO researcher VALUES (?,?,?,?,?,?,?,?)", ins_res)
cur.executemany("UPDATE researcher SET works_total=works_total+?, lead_works=lead_works+? WHERE author_id=?", upd_res)
cur.executemany("INSERT INTO project_researcher VALUES (?,?)", proj_research)
cur.executemany("INSERT INTO work VALUES (?,?,?,?,?)", new_works)
cur.executemany("INSERT INTO work_project VALUES (?,?)", add_wp)
cur.executemany("INSERT INTO work_author VALUES (?,?)", add_wa)

all_blocks = sorted(set(existing_blocks) | set(NEW.values()))
cur.execute("INSERT OR REPLACE INTO meta VALUES ('blocks', ?)",
            (json.dumps([{"k": b, "fw": fw(b)} for b in all_blocks], ensure_ascii=False),))
nw, nd = cur.execute("SELECT COUNT(*), COUNT(doi) FROM work").fetchone()
cur.execute("INSERT OR REPLACE INTO meta VALUES ('doi_pct', ?)", (str(round(nd / max(1, nw) * 100)),))

con.commit()
print("\n=== after merge ===")
for b, n in cur.execute("SELECT block, COUNT(*) FROM project GROUP BY block ORDER BY block"):
    print(f"  {b:12s} {n}")
print("  TOTAL projects:", cur.execute("SELECT COUNT(*) FROM project").fetchone()[0],
      "| units:", cur.execute("SELECT COUNT(*) FROM unit").fetchone()[0],
      "| researchers:", cur.execute("SELECT COUNT(*) FROM researcher").fetchone()[0],
      "| works:", cur.execute("SELECT COUNT(*) FROM work").fetchone()[0])
con.close()
