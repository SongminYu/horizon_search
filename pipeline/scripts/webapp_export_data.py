"""Export the 12 workbooks into webapp/data/*.json for the explorer web app.

Outputs (compact keys to keep payloads small):
  webapp/data/meta.json                 programme registry (span, counts, colors)
  webapp/data/topics.json               all topics, all programmes (~3.7k rows)
  webapp/data/projects.json             all projects core fields + participant-name
                                        array for org search (~7.6k rows)
  webapp/data/participants_{PROG}.json  {projectId: [[name,country,role,type,sme,ec],..]}
  webapp/data/objectives_{PROG}.json    {projectId: objective}     (lazy-loaded)
"""
import json
from pathlib import Path
import pandas as pd
import warnings
warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT.parent / "webapp" / "data"
OUT.mkdir(parents=True, exist_ok=True)

PROGS = {
    "CL5":       {"file": "CL5_Topics_and_Projects.xlsx",  "fw": "Horizon Europe", "name": "CL5 气候·能源·交通", "span": "2021-2026", "color": "#2c5d99"},
    "CL6":       {"file": "CL6_Topics_and_Projects.xlsx",  "fw": "Horizon Europe", "name": "CL6 食物·农业·环境", "span": "2021-2026", "color": "#2f6b3d"},
    "MISS":      {"file": "MISS_Topics_and_Projects.xlsx", "fw": "Horizon Europe", "name": "EU Missions", "span": "2021-2026", "color": "#6c3a85"},
    "JU":        {"file": "JU_Topics_and_Projects.xlsx",   "fw": "Horizon Europe", "name": "能源环境五 JU", "span": "2021-2025", "color": "#b66a1f"},
    "CL4":       {"file": "CL4_Topics_and_Projects.xlsx",  "fw": "Horizon Europe", "name": "CL4 工业/材料谱系", "span": "2021-2026", "color": "#5a7d9a"},
    "H2020-SC3": {"file": "H2020_SC3_Topics_and_Projects.xlsx", "fw": "Horizon 2020", "name": "H2020 SC3 能源", "span": "2014-2020", "color": "#7fa6d9"},
    "H2020-SC4": {"file": "H2020_SC4_Topics_and_Projects.xlsx", "fw": "Horizon 2020", "name": "H2020 SC4 交通", "span": "2014-2020", "color": "#9db8d9"},
    "H2020-SC2": {"file": "H2020_SC2_Topics_and_Projects.xlsx", "fw": "Horizon 2020", "name": "H2020 SC2 食物·农业·生物经济", "span": "2014-2020", "color": "#7fb08a"},
    "H2020-SC5": {"file": "H2020_SC5_Topics_and_Projects.xlsx", "fw": "Horizon 2020", "name": "H2020 SC5 气候·环境·资源", "span": "2014-2020", "color": "#a4c4ab"},
    "H2020-JTI": {"file": "H2020_JTI_Topics_and_Projects.xlsx", "fw": "Horizon 2020", "name": "H2020 五 JTI", "span": "2014-2020", "color": "#d9a45f"},
    "LIFE":      {"file": "LIFE_Topics.xlsx",      "fw": "LIFE", "name": "LIFE（topic 层）", "span": "2021-2026", "color": "#4d8c57", "topics_only": True},
    "INNOVFUND": {"file": "INNOVFUND_Topics.xlsx", "fw": "Innovation Fund", "name": "Innovation Fund（topic 层）", "span": "2021-2025", "color": "#8a5fb0", "topics_only": True},
}

def nz(v, d=None):
    return d if (v is None or (isinstance(v, float) and pd.isna(v)) or (isinstance(v, str) and not v.strip())) else v

def s10(v):
    return str(v)[:10] if pd.notna(v) else None

all_topics, all_projects, meta = [], [], []

for key, conf in PROGS.items():
    f = ROOT.parent / "data" / conf["file"]
    t = pd.read_excel(f, sheet_name="Topics")
    n_proj = 0
    money = 0.0

    for _, r in t.iterrows():
        all_topics.append({
            "k": key,
            "id": r["Topic ID"],
            "ti": nz(r["Topic Title"], ""),
            "d": nz(r["Destination"], ""),
            "y": str(r["Year"])[:4] if pd.notna(r["Year"]) else "",
            "ty": nz(r["Topic Type"]),
            "bud": nz(r["Indicative Budget (EUR M)"]),
            "dl": s10(r["Deadline"]),
            "cs": nz(r["Call Status"]),
            "p": int(r["Funded Projects (signed)"]) if pd.notna(r["Funded Projects (signed)"]) else 0,
            "m": round(float(r["Signed EU Contribution (EUR M)"]), 2) if pd.notna(r["Signed EU Contribution (EUR M)"]) else 0,
        })

    if not conf.get("topics_only"):
        p = pd.read_excel(f, sheet_name="Projects")
        part = pd.read_excel(f, sheet_name="Participants")
        n_proj = len(p)
        money = pd.to_numeric(p["EU Contribution (EUR)"], errors="coerce").sum() / 1e9

        pmap, objs = {}, {}
        for _, r in part.iterrows():
            pmap.setdefault(int(r["Grant Agreement ID"]), []).append([
                nz(r["Organisation Name"], ""), nz(r["Country"], ""), nz(r["Role"], ""),
                nz(r["Activity Type"], ""), nz(r["SME"], ""),
                round(float(r["EC Contribution (EUR)"]), 2) if pd.notna(r["EC Contribution (EUR)"]) else None,
            ])
        json.dump(pmap, open(OUT / f"participants_{key}.json", "w"), ensure_ascii=False, separators=(",", ":"))

        for _, r in p.iterrows():
            pid = int(r["Grant Agreement ID"])
            objs[pid] = nz(r["Objective"], "")
            orgs = sorted({x[0] for x in pmap.get(pid, []) if x[0]})
            all_projects.append({
                "k": key,
                "id": pid,
                "ac": nz(r["Project Acronym"], ""),
                "ti": nz(r["Project Full Name"], ""),
                "tp": nz(r["Topic ID"], ""),
                "sd": s10(r["Start Date"]),
                "ed": s10(r["End Date"]),
                "eu": round(float(r["EU Contribution (EUR)"]), 2) if pd.notna(r["EU Contribution (EUR)"]) else None,
                "tc": round(float(r["Total Cost (EUR)"]), 2) if pd.notna(r["Total Cost (EUR)"]) else None,
                "st": nz(r["Status"], ""),
                "co": nz(r["Coordinator"], ""),
                "cc": nz(r["Coordinator Country"], ""),
                "np": int(r["Number of Participants"]) if pd.notna(r["Number of Participants"]) else None,
                "web": nz(r["Project Website"]),
                "orgs": orgs,
            })
        json.dump(objs, open(OUT / f"objectives_{key}.json", "w"), ensure_ascii=False, separators=(",", ":"))

    meta.append({
        "k": key, "name": conf["name"], "fw": conf["fw"], "span": conf["span"],
        "color": conf["color"], "topicsOnly": bool(conf.get("topics_only")),
        "nTopics": len(t), "nProjects": n_proj, "eurB": round(float(money), 2),
        "indicB": round(pd.to_numeric(t["Indicative Budget (EUR M)"], errors="coerce").sum() / 1000, 2),
    })
    print(f"{key}: topics {len(t)}, projects {n_proj}", flush=True)

json.dump(meta, open(OUT / "meta.json", "w"), ensure_ascii=False)
json.dump(all_topics, open(OUT / "topics.json", "w"), ensure_ascii=False, separators=(",", ":"))
json.dump(all_projects, open(OUT / "projects.json", "w"), ensure_ascii=False, separators=(",", ":"))

import os
for f in sorted(OUT.iterdir()):
    print(f"  {f.name}: {os.path.getsize(f)//1024} KB")
