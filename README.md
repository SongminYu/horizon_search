# Horizon Search

Semantic search across EU Horizon 2020 + Horizon Europe research funding — projects, organisations, researchers, and papers in one place.

**[horizonsearch.eu](https://horizonsearch.eu)** · live site, no account required

---

## What it is

A structured dataset and search interface covering **15 thematic programme blocks**:

| Framework | Blocks |
|---|---|
| Horizon Europe (2021–2027) | CL1 · CL2 · CL3 · CL4 · CL5 · CL6 · Missions |
| Horizon 2020 (2014–2020) | SC1 · SC2 · SC3 · SC4 · SC5 · SC6 · SC7 · JTI |

Out of scope: ERC, MSCA, EIC, LEIT, Joint Undertakings, LIFE, Innovation Fund.

**Data sources:**
- **CORDIS** — projects and funded participants (bulk export, CC-BY)
- **OpenAlex** — linked papers and researchers, matched by grant ID

**Search** uses a four-stage LLM pipeline (route → screen → score → re-rank) driven by DeepSeek V4 by default. The webapp also has a **Browse** tab for exact filtering by block, status, country, funding range, and date.

---

## Local usage

```bash
git clone https://github.com/SongminYu/horizon_search
cd horizon_search

# Download the database (~190 MB) — distributed as a GitHub Release asset, not stored in git:
curl -L -o horizon.sqlite \
  https://github.com/SongminYu/horizon_search/releases/download/data/horizon.sqlite
```

`horizon.sqlite` is the single source of truth — a standard SQLite file with everything (projects, organisations, researchers, papers, topics). From it you can:

**Run the webapp locally**

```bash
python3 pipeline/scripts/export_webapp.py     # sqlite → webapp/data/*.json (stdlib only, ~5s)
cd webapp && python3 -m http.server 8742      # open http://localhost:8742
```

Browse and entity pages work immediately. Semantic search needs an LLM key — open the settings panel (ⓘ icon → Models tab) and paste a DeepSeek / Gemini / OpenAI / Claude key (stored in your browser only).

**Or query from the CLI** (no webapp build needed)

```bash
export DEEPSEEK_API_KEY=sk-...                # key from platform.deepseek.com
python3 pipeline/scripts/horizon_search.py "offshore wind turbine decommissioning" --out-dir .
```

This writes `horizon_search_<slug>/results.json` — the full ranked result set, readable by any downstream tool or agent.

**Or just query the SQLite directly** with `sqlite3` / pandas for your own analysis.

---

## MCP server (AI agent integration)

Register the search tool with Claude Code (or any MCP-compatible client):

```bash
pip install mcp
claude mcp add -s user horizon_search -- python3 $(pwd)/pipeline/scripts/horizon_mcp.py
```

The tool `mcp__horizon_search__search_horizon` then runs the full four-stage search and writes results to disk. You can also point your AI coding agent at the cloned repo directly: once `horizon.sqlite` is downloaded it can query the database (standard SQLite), run the search scripts, and explore the pipeline on its own.

---

## Data pipeline

The pipeline builds `horizon.sqlite` (the master database) from CORDIS bulk exports and OpenAlex, then generates `webapp/data/*.json` for the static site.

```
CORDIS bulk + OpenAlex
   │  collection scripts (pipeline/scripts/)
   ▼
data/<block>_Topics_and_Projects.xlsx   (transient)
   │  build_database.py
   ▼
horizon.sqlite                          ★ master database
   │  export_webapp.py
   ▼
webapp/data/*.json                      static site data
```

`horizon.sqlite` (~190 MB) and the derived `webapp/data/*.json` are not stored in git — the database is published as a GitHub Release asset (tag `data`), and the JSON layers are regenerated from it by `export_webapp.py` (and uploaded straight to the CDN at deploy time). See `DEPLOY.md` for the full deployment setup.

---

## Repository layout

```
webapp/
  index.html            single-file SPA
  data/*.json           static site data (generated, not in git)
  search_spec.json      shared LLM search config (models, prompts, thresholds)
pipeline/
  scripts/
    horizon_search.py   CLI search (same 4-stage pipeline as the webapp)
    horizon_mcp.py      MCP server wrapping horizon_search.py
    build_database.py   builds horizon.sqlite from workbooks + OpenAlex cache
    export_webapp.py    exports horizon.sqlite → webapp/data/*.json
    he_*.py / h2020_*.py / cl*_*.py / miss_*.py   block-specific collection scripts
DEPLOY.md               Netlify deployment guide
```

---

Independent data product · not affiliated with the European Commission.
