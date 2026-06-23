#!/usr/bin/env python3
"""
horizon_mcp.py — exposes horizon_search as an MCP tool so MCP clients
(Claude Code / Claude Desktop, etc.) can call it as a native tool.

It thinly wraps run_search: the client passes a search description (and an
optional output directory); the tool writes JSON + Markdown into that
directory and returns a short summary (absolute file paths + top hits),
keeping the bulk of the data in files instead of the conversation context.

Deps: mcp (pip install mcp) + the standard library. The Gemini key is
resolved by horizon_search.

Register (Claude Code, user scope):
    claude mcp add -s user horizon_search -- python3 /abs/path/pipeline/scripts/horizon_mcp.py
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

# 允许以 `python3 .../horizon_mcp.py` 直接启动时导入同目录的 horizon_search
sys.path.insert(0, str(Path(__file__).resolve().parent))
from horizon_search import run_search, SearchError, DEFAULT_DB, CFG  # noqa: E402

try:
    from mcp.server.fastmcp import FastMCP
    from pydantic import Field
except ImportError:
    sys.stderr.write(
        "Missing the 'mcp' package. Install it first: pip install mcp\n"
        "(Only needed for MCP mode; the plain CLI horizon_search.py does not require it.)\n"
    )
    raise

mcp = FastMCP("horizon_search")


@mcp.tool()
def search_horizon(
    query: Annotated[
        str,
        Field(description=(
            "Natural-language description of the research direction to search for. "
            "The more specific it is, the fewer high-scoring projects come back. "
            'e.g. "fatigue and decommissioning / recycling of offshore wind foundations".'
        )),
    ],
    out_dir: Annotated[
        str,
        Field(description=(
            "Output root directory. Pass your current session's working directory as an "
            "absolute path, so the result folder is created under the project you're "
            "calling from. Defaults to the current directory."
        )),
    ] = ".",
    top: Annotated[
        int,
        Field(description="Maximum number of projects to return (default 50)."),
    ] = CFG["final_top"],
    fast: Annotated[
        bool,
        Field(description=(
            "If true, skip the final Pro-model re-rank — faster and cheaper; ordering "
            "then uses only the fast-model fine scores."
        )),
    ] = False,
) -> str:
    """Run a four-stage semantic search over the EU Horizon project database; write results to files and return a summary.

    Searches horizon.sqlite (Horizon 2020 + Horizon Europe, 15 thematic blocks:
    CL1–CL6 / EU Missions / H2020 SC1–SC7 / JTI) by a natural-language
    description: route to the relevant domains, adaptively shard and screen,
    score, then a final Pro-model re-rank, taking the most relevant projects
    with full coordinator / participant / linked-researcher info, written as
    JSON + Markdown.

    The tool creates a **new dedicated folder** `horizon_search_<slug>/` under
    out_dir, containing:
      - `results.json` — the full result data
      - `README.md`    — a guide: where the data comes from, the JSON structure
                          and field meanings, and how to read it

    Returns a text summary: hit count, absolute paths to the output folder and
    README / JSON, and the top hits. **Read README.md first** to understand the
    structure, then read results.json as needed.
    """
    try:
        res = run_search(query, out_dir, top=top, use_pro=not fast)
    except SearchError as e:
        return f"Search failed: {e}"

    lines = [
        f"{res['count']} projects matched · query “{res['query']}”",
        f"Output folder: {res['folder']}",
        f"  README (read this first — structure & definitions): {res['md_path']}",
        f"  results.json (full data): {res['json_path']}",
        "",
        "Top hits (full info in results.json):",
    ]
    for r in res["results"][:15]:
        lines.append(f"  [{r['score']:>3}] {r['acronym'] or '—'} — {(r['title'] or '')[:80]}")
        if r["reason"]:
            lines.append(f"        reason: {r['reason']}")
    if res["count"] > 15:
        lines.append(f"  …{res['count'] - 15} more in the JSON file")
    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run()
