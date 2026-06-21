#!/usr/bin/env python3
"""
eu3e_mcp.py — 把 eu3e_search 暴露成 MCP 工具，供 Claude Code / Claude Desktop
等 MCP 客户端当原生工具调用。

它薄薄包了一层 run_search：客户端传入检索描述（和可选的输出目录），
工具在指定目录写 JSON + Markdown，并返回一段简短摘要（含文件绝对路径
与 top 命中），把大块数据留在文件里、不灌进对话 context。

依赖：mcp（pip install mcp）+ 标准库。Gemini key 由 eu3e_search 解析。

注册（Claude Code，项目级）：见仓库根的 .mcp.json，或运行
    claude mcp add eu3e -- python3 /绝对路径/pipeline/scripts/eu3e_mcp.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# 允许以 `python3 .../eu3e_mcp.py` 直接启动时导入同目录的 eu3e_search
sys.path.insert(0, str(Path(__file__).resolve().parent))
from eu3e_search import run_search, SearchError, DEFAULT_DB, CFG  # noqa: E402

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    sys.stderr.write(
        "缺少 mcp 包。请先安装：pip install mcp\n"
        "（仅 MCP 模式需要；纯命令行用 eu3e_search.py 无需它。）\n"
    )
    raise

mcp = FastMCP("eu3e")


@mcp.tool()
def search_eu3e(query: str, out_dir: str = ".", top: int = CFG["final_top"]) -> str:
    """对 EU Horizon 科研项目库做两段式语义检索，结果写文件并返回摘要。

    在 eu3e.sqlite（Horizon 2020 + Horizon Europe，能源/环境/气候/食农/交通）
    里按自然语言描述检索：先粗筛全部项目，再逐一打分排序，取最相关的若干个，
    带上协调方、参与单位、关联研究者等完整信息写成 JSON + Markdown。

    工具会在 out_dir 下**新建一个独立文件夹** `eu3e_search_<slug>/`，里面放：
      - `results.json` —— 完整结果数据
      - `README.md`    —— 说明书：数据怎么来的、JSON 结构与字段含义、怎么理解使用

    Args:
        query: 自然语言检索描述，越具体高分项目越少。
               例：「海上风电基础结构的疲劳与退役回收」。
        out_dir: 输出根目录。**请传入你当前会话的工作目录（绝对路径）**，
                 生成的文件夹就会建在你调用它的项目根目录下。默认当前目录。
        top: 最终返回的项目数上限（默认 50）。

    Returns:
        一段文本摘要：命中数、输出文件夹与 README/JSON 的绝对路径、以及 top 命中
        列表。**建议先读 README.md** 了解结构，再按需读 results.json。
    """
    try:
        res = run_search(query, out_dir, top=top)
    except SearchError as e:
        return f"检索失败：{e}"

    lines = [
        f"命中 {res['count']} 个项目 · 查询「{res['query']}」",
        f"输出文件夹: {res['folder']}",
        f"  README（先读这个，讲清结构与口径）: {res['md_path']}",
        f"  results.json（完整数据）: {res['json_path']}",
        "",
        "Top 命中（完整信息见 results.json）：",
    ]
    for r in res["results"][:15]:
        lines.append(f"  [{r['score']:>3}] {r['acronym'] or '—'} — {(r['title'] or '')[:80]}")
        if r["reason"]:
            lines.append(f"        理由：{r['reason']}")
    if res["count"] > 15:
        lines.append(f"  …其余 {res['count'] - 15} 个见 JSON 文件")
    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run()
