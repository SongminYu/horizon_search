"""Export the website data from horizon.sqlite (the master DB) → webapp/data/*.json.

This is the only step between the database and the static site. Run after
build_database.py. Produces the integer-indexed graph the Pivot Explorer loads:
  nodes_topics / nodes_projects / nodes_units / nodes_people / nodes_works .json
  graph_meta.json      programmes + layer counts
  proj_index.json      TF-IDF over project text (incl. objectives) for keyword search
  objectives_<BLOCK>.json   {grant_id: objective}   (project-page abstract, lazy)
Stdlib only.
"""
import sqlite3, json, os
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT.parent / "horizon.sqlite"
OUT = ROOT.parent / "webapp" / "data"
OUT.mkdir(parents=True, exist_ok=True)
COLOR = {"Horizon Europe": "#2c5d99", "Horizon 2020": "#7fa6d9"}

con = sqlite3.connect(DB); con.row_factory = sqlite3.Row; cur = con.cursor()
def rows(q): return cur.execute(q).fetchall()

# ---- nodes + id->index maps ----
topics, tid2i = [], {}
for r in rows("SELECT * FROM topic"):
    tid2i[r["id"]] = len(topics)
    topics.append({"id": r["id"], "ti": r["title"] or "", "d": r["destination"] or "", "bk": r["block"],
                   "ty": r["type"] or "", "bud": r["budget_eur_m"], "cs": r["status"] or "", "kw": [], "P": []})
for r in rows("SELECT topic_id,keyword FROM topic_keyword"):
    if r["topic_id"] in tid2i: topics[tid2i[r["topic_id"]]]["kw"].append(r["keyword"])

projects, gid2i = [], {}
for r in rows("SELECT * FROM project"):
    gid2i[r["grant_id"]] = len(projects)
    projects.append({"id": r["grant_id"], "ac": r["acronym"] or "", "ti": r["title"] or "", "bk": r["block"],
                     "eu": r["eu_contribution_eur"], "sd": r["start_date"], "ed": r["end_date"], "st": r["status"] or "",
                     "co": r["coordinator"] or "", "cc": r["coordinator_country"] or "",
                     "T": tid2i.get(r["topic_id"]), "U": [], "W": [], "R": []})

units, oid2i = [], {}
for r in rows("SELECT * FROM unit"):
    oid2i[r["org_id"]] = len(units)
    units.append({"id": r["org_id"], "nm": r["name"] or "", "c": r["country"] or "", "ty": r["activity_type"] or "",
                  "sme": bool(r["sme"]), "ec": r["total_ec_eur"], "coord": r["coordinator_count"], "P": []})

people, aid2i = [], {}
for r in rows("SELECT * FROM researcher"):
    aid2i[r["author_id"]] = len(people)
    people.append({"id": r["author_id"], "nm": r["name"] or "", "or": r["orcid"], "c": r["country"] or "",
                   "i": r["main_institution"] or "", "w": r["works_total"], "lw": r["lead_works"], "t": r["topics"] or "", "P": [], "W": []})

works, wid2i = [], {}
for r in rows("SELECT * FROM work"):
    wid2i[r["work_id"]] = len(works)
    works.append({"id": r["work_id"], "ti": r["title"] or "(untitled)", "y": r["year"], "doi": r["doi"],
                  "url": r["url"], "oa": r["oa_status"], "P": [], "R": []})

# ---- edges (resolve to indices) ----
for r in rows("SELECT grant_id,topic_id FROM project"):
    if r["topic_id"] in tid2i and r["grant_id"] in gid2i: topics[tid2i[r["topic_id"]]]["P"].append(gid2i[r["grant_id"]])
for r in rows("SELECT grant_id,org_id,ec_eur FROM project_unit"):
    gi, oi = gid2i.get(r["grant_id"]), oid2i.get(r["org_id"])
    if gi is not None and oi is not None:
        projects[gi]["U"].append([oi, r["ec_eur"]]); units[oi]["P"].append(gi)
for r in rows("SELECT grant_id,author_id FROM project_researcher"):
    gi, ai = gid2i.get(r["grant_id"]), aid2i.get(r["author_id"])
    if gi is not None and ai is not None:
        projects[gi]["R"].append(ai); people[ai]["P"].append(gi)
for r in rows("SELECT work_id,grant_id FROM work_project"):
    wi, gi = wid2i.get(r["work_id"]), gid2i.get(r["grant_id"])
    if wi is not None and gi is not None:
        works[wi]["P"].append(gi); projects[gi]["W"].append(wi)
for r in rows("SELECT work_id,author_id FROM work_author"):
    wi, ai = wid2i.get(r["work_id"]), aid2i.get(r["author_id"])
    if wi is not None and ai is not None:
        works[wi]["R"].append(ai); people[ai]["W"].append(wi)
for p in projects: p["U"].sort(key=lambda x: -x[1])

def dump(name, arr):
    json.dump(arr, open(OUT / name, "w"), ensure_ascii=False, separators=(",", ":"))
    print(f"  {name}: {len(arr):,} nodes, {os.path.getsize(OUT/name)//1024} KB")
for n, a in [("nodes_topics.json", topics), ("nodes_projects.json", projects), ("nodes_units.json", units),
             ("nodes_people.json", people), ("nodes_works.json", works)]:
    dump(n, a)

# ---- objectives_<BLOCK>.json (project-page abstract, lazy) ----
obj = defaultdict(dict)
for r in rows("SELECT grant_id,block,objective FROM project WHERE objective IS NOT NULL"):
    obj[r["block"]][str(r["grant_id"])] = r["objective"]
for blk, d in obj.items():
    json.dump(d, open(OUT / f"objectives_{blk}.json", "w"), ensure_ascii=False, separators=(",", ":"))

# ---- proj_catalog.json: [grant_id, acronym, title, objective[:300], block] for ALL projects ----
# The coarse stage reads this whole catalog (~0.77M tokens). The block field lets the
# server-side search (Netlify background fn) compute per-block route counts and filter
# candidates without loading nodes_projects.json. The browser ignores the 5th field.
cat = []
for r in rows("SELECT grant_id,acronym,title,objective,block FROM project"):
    cat.append([r["grant_id"], r["acronym"] or "", r["title"] or "", (r["objective"] or "")[:300], r["block"] or ""])
json.dump(cat, open(OUT / "proj_catalog.json", "w"), ensure_ascii=False, separators=(",", ":"))
print(f"  proj_catalog.json: {len(cat):,} projects, {os.path.getsize(OUT/'proj_catalog.json')//1024} KB")

# ---- graph_meta.json ----
blocks = json.loads(cur.execute("SELECT value FROM meta WHERE key='blocks'").fetchone()[0])
doi_pct = int(cur.execute("SELECT value FROM meta WHERE key='doi_pct'").fetchone()[0])
eu_total = cur.execute("SELECT COALESCE(SUM(eu_contribution_eur),0) FROM project").fetchone()[0]
meta = {"blocks": [{"k": b["k"], "fw": b["fw"], "color": COLOR.get(b["fw"], "#888")} for b in blocks],
        "counts": {"topics": len(topics), "projects": len(projects), "units": len(units), "people": len(people), "works": len(works)},
        "eu_total": eu_total, "doi_pct": doi_pct}
json.dump(meta, open(OUT / "graph_meta.json", "w"), ensure_ascii=False)
con.close()
print("done.")
