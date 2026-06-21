#!/usr/bin/env python3
"""
eu3e_search.py — 命令行版"关键词全景"语义检索。

把 webapp 里那套两段式 Gemini 检索（index.html 的 llmSearch）搬到命令行，
直接读 eu3e.sqlite，结果写成 AI 可读的 JSON（+ Markdown 摘要），供另一个
AI（如 Claude Code）以 CLI / MCP 方式调用后再读取文件。

用法：
    python3 eu3e_search.py "氢能与农业系统耦合" --out-dir .
    python3 eu3e_search.py "海上风电退役与回收" --top 30 --json-only

Gemini key 解析顺序：环境变量 GEMINI_API_KEY → webapp/apikey.local.js。
依赖：仅标准库（urllib 调网络），与本项目约定一致。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

# ── 路径：脚本在 pipeline/scripts/ 下，仓库根 = parents[2] ──────────────────
ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = ROOT / "eu3e.sqlite"
APIKEY_JS = ROOT / "webapp" / "apikey.local.js"

# ── 检索配置（对应 index.html 的 SEARCH_CFG）────────────────────────────────
CFG = {
    "model": "gemini-2.5-flash",
    "stage1_max": 100,     # 第 1 段粗筛候选上限
    "final_top": 50,       # 第 2 段精排展示上限
    "max_out_1": 8192,     # 第 1 段输出 token 上限（grant_id 数组）
    "max_out_2": 32768,    # 第 2 段输出 token 上限（打分对象数组）
    "snippet": 300,        # 第 1 段摘要片段长度
    "timeout": 180,        # 单次 Gemini 请求超时（秒）
    "max_units": 20,       # 每个项目导出的参与单位上限
    "max_researchers": 20, # 每个项目导出的研究者上限
}

SCHEMA_IDS = {"type": "ARRAY", "maxItems": CFG["stage1_max"], "items": {"type": "INTEGER"}}
# 嵌套对象数组不能加 maxItems（Gemini 结构化输出会因状态机过大报 400）
SCHEMA_SCORES = {
    "type": "ARRAY",
    "items": {
        "type": "OBJECT",
        "propertyOrdering": ["g", "score", "reason"],
        "properties": {"g": {"type": "INTEGER"}, "score": {"type": "INTEGER"}, "reason": {"type": "STRING"}},
        "required": ["g", "score", "reason"],
    },
}


class SearchError(Exception):
    """检索过程中的可预期错误（缺 key / DB / Gemini 拒绝等）。"""


# ── Gemini key ──────────────────────────────────────────────────────────────
def load_api_key() -> str:
    import os
    key = (os.environ.get("GEMINI_API_KEY") or "").strip()
    if key:
        return key
    if APIKEY_JS.exists():
        m = re.search(r'GEMINI_API_KEY\s*=\s*["\']([^"\']+)["\']', APIKEY_JS.read_text(encoding="utf-8"))
        if m and m.group(1).strip():
            return m.group(1).strip()
    raise SearchError(
        "未找到 Gemini API key。请设置环境变量 GEMINI_API_KEY，"
        f"或在 {APIKEY_JS} 里填入 key。"
    )


# ── Gemini 调用 ──────────────────────────────────────────────────────────────
def gemini_call(prompt: str, schema: dict, max_out: int, key: str, model: str) -> tuple[str, bool]:
    """调 Gemini，强制 JSON 结构化输出。返回 (text, truncated)。"""
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{model}:generateContent?key={urllib.parse.quote(key)}")
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0,
            "responseMimeType": "application/json",
            "responseSchema": schema,
            "thinkingConfig": {"thinkingBudget": 0},  # 关思考 → 输出预算全留给答案
            "maxOutputTokens": max_out,
        },
    }
    req = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=CFG["timeout"]) as r:
            d = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        raise SearchError(f"Gemini HTTP {e.code}：{detail}")
    except urllib.error.URLError as e:
        raise SearchError(f"网络错误：{e.reason}")

    cand = (d.get("candidates") or [{}])[0]
    fr = cand.get("finishReason")
    if fr in ("SAFETY", "PROHIBITED_CONTENT", "RECITATION"):
        raise SearchError(f"Gemini 拒绝了请求（{fr}）")
    txt = "".join(p.get("text", "") for p in (cand.get("content", {}).get("parts") or []))
    if not txt:
        raise SearchError(f"Gemini 返回空（finishReason={fr or '?'}）")
    return txt, fr == "MAX_TOKENS"


# ── 容错解析（截断时尽量抠出结果，对应 JS 的 parseIdArray/parseObjArray）──────
def parse_id_array(txt: str) -> list[int]:
    try:
        a = json.loads(txt)
        if isinstance(a, list):
            return [int(x) for x in a if isinstance(x, (int, float))]
    except Exception:
        pass
    return [int(x) for x in re.findall(r"\d{5,}", txt)]  # grant_id 都是 5+ 位整数


def parse_obj_array(txt: str) -> list[dict]:
    try:
        a = json.loads(txt)
        if isinstance(a, list):
            return [x for x in a if isinstance(x, dict)]
    except Exception:
        pass
    out = []
    for m in re.finditer(r"\{[^{}]*\}", txt):
        try:
            out.append(json.loads(m.group(0)))
        except Exception:
            pass
    return out


# ── 提示词（对应 index.html 的 PROMPTS）─────────────────────────────────────
def prompt_stage1(query: str, count: int, lines: str) -> str:
    return f"""你是欧盟科研项目检索助手。
用户描述他要找的项目方向：
「{query}」

下面是全部 {count} 个项目，每行格式：[grant_id] 缩写 — 标题 :: 摘要片段
任务：挑出与描述最相关的项目，按相关度从高到低，**最多 {CFG['stage1_max']} 个**（宁可多挑，下一步会精筛，但绝不要超过 {CFG['stage1_max']} 个）。

只返回严格的 JSON 整数数组，元素是项目的 grant_id，示例：
[101056783, 101082232, 101081845]
不要输出数组以外的任何文字、解释或 ``` 代码块标记。

项目清单：
{lines}"""


def prompt_stage2(query: str, count: int, body: str) -> str:
    return f"""你是欧盟科研项目相关性评分助手。
用户描述他要找的项目方向：
「{query}」

下面是 {count} 个候选项目的完整标题与摘要。给每个项目按下列规则打 0–100 分（必须是 5 的倍数）：
- 90–100 完全命中：描述里每个关键点都满足
- 70–85 高度相关：核心方向一致，个别次要条件不满足
- 50–65 部分相关：主题沾边但侧重不同
- 25–45 弱相关
- 0–20 基本无关
描述越具体，高分项目应越少——只有实质满足要求的才给高分。

为每个候选各返回一个对象，只返回严格的 JSON 对象数组，每个对象：
{{"g": <grant_id 整数>, "score": <0-100 整数，5 的倍数>, "reason": "<一句中文理由>"}}
示例：[{{"g":101056783,"score":85,"reason":"直接研究氢能与农业系统耦合"}}]
不要输出数组以外的任何文字、解释或 ``` 代码块标记。

候选项目：
{body}"""


# ── 两段式检索 ───────────────────────────────────────────────────────────────
def two_stage(query: str, conn: sqlite3.Connection, key: str, model: str,
              stage1_max: int, top: int, log=lambda *_: None) -> list[dict]:
    """返回 [{grant_id, score, reason}]，按分数降序。"""
    rows = conn.execute(
        "SELECT grant_id, acronym, title, objective FROM project"
    ).fetchall()
    valid = {r[0] for r in rows}

    # 第 1 段：粗筛全部项目
    log(f"第 1/2 步：粗筛全部 {len(rows)} 个项目…")
    snip = CFG["snippet"]
    lines = "\n".join(
        f"[{g}] {ac or ''} — {ti or ''} :: {(ob or '')[:snip]}"
        for g, ac, ti, ob in rows
    )
    t1, trunc1 = gemini_call(prompt_stage1(query, len(rows), lines),
                             SCHEMA_IDS, CFG["max_out_1"], key, model)
    if trunc1:
        log("  （第 1 段输出被截断，已尽量抠取 grant_id）")
    seen, ids = set(), []
    for g in parse_id_array(t1):
        if g in valid and g not in seen:
            seen.add(g); ids.append(g)
        if len(ids) >= stage1_max:
            break
    if not ids:
        return []

    # 第 2 段：精排候选
    log(f"第 2/2 步：给 {len(ids)} 个候选打分排序…")
    qm = ",".join("?" * len(ids))
    objs = {g: (ti, ob) for g, ti, ob in conn.execute(
        f"SELECT grant_id, title, objective FROM project WHERE grant_id IN ({qm})", ids
    )}
    body = "\n\n".join(
        f"[{g}] {objs[g][0] or ''}\n摘要：{objs[g][1] or '（无摘要）'}" for g in ids
    )
    t2, trunc2 = gemini_call(prompt_stage2(query, len(ids), body),
                             SCHEMA_SCORES, CFG["max_out_2"], key, model)
    if trunc2:
        log("  （第 2 段输出被截断，已保留已完整的打分对象）")
    scored = []
    for s in parse_obj_array(t2):
        g = s.get("g")
        sc = s.get("score")
        if g in valid and isinstance(sc, (int, float)):
            scored.append({"grant_id": int(g), "score": int(sc), "reason": s.get("reason", "")})
    scored.sort(key=lambda x: x["score"], reverse=True)
    if not scored:
        raise SearchError("第 2 段未解析出有效打分（返回格式异常）")
    return scored[:top]


# ── 丰富化：把命中项目从库里 JOIN 出完整信息 ────────────────────────────────
def enrich(conn: sqlite3.Connection, scored: list[dict]) -> list[dict]:
    out = []
    for rank, s in enumerate(scored, 1):
        g = s["grant_id"]
        p = conn.execute(
            "SELECT grant_id, acronym, title, block, eu_contribution_eur, start_date, "
            "end_date, status, coordinator, coordinator_country, topic_id, objective "
            "FROM project WHERE grant_id=?", (g,)
        ).fetchone()
        if not p:
            continue
        rec = {
            "rank": rank, "score": s["score"], "reason": s["reason"],
            "grant_id": p[0], "acronym": p[1], "title": p[2], "block": p[3],
            "eu_contribution_eur": p[4], "start_date": p[5], "end_date": p[6],
            "status": p[7], "coordinator": p[8], "coordinator_country": p[9],
            "topic_id": p[10], "objective": p[11],
        }
        if p[10]:
            t = conn.execute(
                "SELECT title, destination, type, budget_eur_m FROM topic WHERE id=?", (p[10],)
            ).fetchone()
            if t:
                rec["topic"] = {"id": p[10], "title": t[0], "destination": t[1],
                                "type": t[2], "budget_eur_m": t[3]}
        rec["units"] = [
            {"org_id": u[0], "name": u[1], "country": u[2], "activity_type": u[3],
             "sme": bool(u[4]), "ec_eur": u[5]}
            for u in conn.execute(
                "SELECT u.org_id, u.name, u.country, u.activity_type, u.sme, pu.ec_eur "
                "FROM project_unit pu JOIN unit u ON u.org_id=pu.org_id "
                "WHERE pu.grant_id=? ORDER BY (pu.ec_eur IS NULL), pu.ec_eur DESC LIMIT ?",
                (g, CFG["max_units"]))
        ]
        rec["researchers"] = [
            {"author_id": r[0], "name": r[1], "country": r[2], "main_institution": r[3],
             "orcid": r[4], "works_total": r[5], "lead_works": r[6]}
            for r in conn.execute(
                "SELECT r.author_id, r.name, r.country, r.main_institution, r.orcid, "
                "r.works_total, r.lead_works FROM project_researcher pr "
                "JOIN researcher r ON r.author_id=pr.author_id "
                "WHERE pr.grant_id=? ORDER BY r.lead_works DESC, r.works_total DESC LIMIT ?",
                (g, CFG["max_researchers"]))
        ]
        out.append(rec)
    return out


# ── 输出文件 ─────────────────────────────────────────────────────────────────
def slugify(q: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "-", q).strip("-").lower()[:40]
    h = hashlib.md5(q.encode("utf-8")).hexdigest()[:6]
    return f"{s}-{h}" if s else f"eu3e-{h}"


def render_readme(query: str, records: list[dict], meta: dict, json_name: str) -> str:
    """生成 README.md —— 给 AI 看的说明书：数据怎么来、JSON 结构、怎么理解。"""
    def esc(x):
        return str(x or "").replace("|", "\\|").replace("\n", " ")
    n = len(records)
    L = [
        "# EU 3E 检索结果包",
        "",
        f"> 由 EU 3E 语义检索工具生成。这份 README 说明 **`{json_name}` 的数据怎么来的、"
        "结构是什么、该怎么理解**，方便 AI 直接拿结果继续工作。",
        "",
        "## 1. 这是什么",
        "",
        f"- **查询（用户的检索描述）**：{query}",
        f"- **命中**：{n} 个项目，已按相关度从高到低排序",
        f"- **生成时间**：{meta['generated_at']}",
        f"- **完整数据**：同目录的 `{json_name}`（UTF-8 JSON）",
        "",
        "## 2. 用什么工具、按什么步骤提取的",
        "",
        "工具：`eu3e_search.py`（也以 MCP 工具 `search_eu3e` 暴露），对一个本地的 "
        "EU Horizon 科研项目数据库做**两段式语义检索**——与该项目网页版「关键词全景」同一套逻辑：",
        "",
        f"1. **第 1 段·粗筛**：把数据库里**全部项目**（缩写+标题+摘要片段）连同查询交给 "
        f"`{meta['model']}`，让它挑出最相关的 ≤100 个候选。",
        "2. **第 2 段·精排**：取候选的**完整摘要**，让模型逐个打 0–100 分并给一句中文理由，"
        f"按分数降序取前 {n} 个。",
        "3. **丰富化**：对每个命中项目，从数据库 JOIN 出完整项目档案、所属 topic、"
        "参与单位（按各自 EU 出资降序）、关联研究者（按主导论文数降序）。",
        "",
        "## 3. 数据范围与口径（理解结果前必读）",
        "",
        f"- **来源**：`{Path(meta['database']).name}`，一个 **Horizon-only** 数据库——"
        "Horizon 2020 + Horizon Europe，覆盖能源 / 环境 / 气候 / 食品农业 / 交通，"
        "共 9 个项目区块（CL4、CL5、CL6、EU Missions、H2020-SC2/SC3/SC4/SC5/JTI）。"
        "不含 JU / LIFE / Innovation Fund。",
        "- **`score` 是模型对「与查询的相关度」的判断**（0–100，5 的倍数），"
        "不是项目本身的质量或资助额，也非官方标签；高分=描述里的关键点基本都命中。"
        "`reason` 是模型给的一句话依据。两者都建议对照 `objective` 复核。",
        "- **两种金额，切勿相加**：`eu_contribution_eur` 是 CORDIS 实际签约的欧盟出资（欧元）；"
        "`topic.budget_eur_m` 是工作计划的指示性预算（百万欧元）。H2020 的 topic 没有预算/关键词/TRL，"
        "这些字段会是 null。",
        "- **`units` = CORDIS 受资助参与方**（org），不是论文署名机构。",
        "- **`researchers` 是 OpenAlex 合著关系的代理**，按 `awards.funder_award_id`=Grant ID 关联，"
        "**不是官方项目角色**。覆盖率是梯度：研究型项目（RIA/IA）高，CSA/支持类或刚启动的项目可能为空——"
        "**空的研究者/论文通常是正常的，不是数据缺失。**",
        "",
        "## 4. JSON 结构（数据字典）",
        "",
        "顶层对象：",
        "",
        "```",
        "{",
        '  "query":        <str>   本次查询描述',
        '  "generated_at": <str>   生成时间（本地时区）',
        '  "model":        <str>   使用的 Gemini 模型',
        '  "database":     <str>   源数据库绝对路径',
        '  "count":        <int>   命中项目数（= results 长度）',
        '  "results":      [ <项目对象>, ... ]   按 score 降序',
        "}",
        "```",
        "",
        "每个 **项目对象**（`results[i]`）：",
        "",
        "```",
        "{",
        '  "rank":                 <int>   名次，从 1 起',
        '  "score":                <int>   相关度 0–100',
        '  "reason":               <str>   模型给的一句话理由',
        '  "grant_id":             <int>   CORDIS Grant ID（项目唯一键）',
        '  "acronym":              <str>   项目缩写',
        '  "title":                <str>   项目全称',
        '  "block":                <str>   所属区块（如 CL5、H2020-SC3）',
        '  "eu_contribution_eur":  <int>   欧盟实际出资（欧元），可能为 null',
        '  "start_date"/"end_date":<str>   起止日期 YYYY-MM-DD',
        '  "status":               <str>   SIGNED / CLOSED 等',
        '  "coordinator":          <str>   协调方机构名',
        '  "coordinator_country":  <str>   协调方国家代码',
        '  "topic_id":             <str>   所属 topic 的 id',
        '  "objective":            <str>   项目完整摘要（评分依据，最权威的文本）',
        '  "topic":   { "id","title","destination","type","budget_eur_m" }   可能缺省',
        '  "units":   [ { "org_id","name","country","activity_type","sme","ec_eur" } ]  按 ec_eur 降序，最多 20',
        '  "researchers": [ { "author_id","name","country","main_institution","orcid",',
        '                     "works_total","lead_works" } ]   按 lead_works 降序，最多 20',
        "}",
        "```",
        "",
        "## 5. 给 AI 的使用建议",
        "",
        f"- 直接读 `{json_name}`；每个项目对象是自包含的，无需再查别处。",
        "- 想了解项目「到底做什么」，看 `objective`（最权威）；`reason`/`score` 是相关度提示，不是结论。",
        "- 需要机构/合作网络分析时用 `units`（带各自 EU 出资）；需要人/团队时用 `researchers`（注意是合著代理）。",
        "- 谈钱时分清 `eu_contribution_eur`（实际）与 `topic.budget_eur_m`（指示性），不要相加或混用。",
        "- 列表已截断为最多 20 个单位/研究者；如需全量需回到源数据库 `eu3e.sqlite` 查 `grant_id`。",
        "",
        "## 6. 结果速览",
        "",
        "| # | 分数 | 缩写 | 标题 | 区块 | EU€(M) | 状态 | 协调方(国) | 理由 |",
        "|--:|--:|---|---|---|--:|---|---|---|",
    ]
    for r in records:
        eu = r["eu_contribution_eur"]
        eu_m = f"{eu/1e6:.2f}" if eu else "—"
        title = esc(r["title"])
        if len(title) > 80:
            title = title[:79] + "…"
        coord = esc(r["coordinator"])
        if len(coord) > 30:
            coord = coord[:29] + "…"
        cc = f" ({r['coordinator_country']})" if r.get("coordinator_country") else ""
        L.append(
            f"| {r['rank']} | {r['score']} | {esc(r['acronym'])} | {title} | "
            f"{esc(r['block'])} | {eu_m} | {esc(r['status'])} | {coord}{cc} | {esc(r['reason'])} |"
        )
    return "\n".join(L) + "\n"


def run_search(query: str, out_dir: str | Path = ".", *, db: str | Path = DEFAULT_DB,
               top: int = None, stage1_max: int = None, model: str = None,
               json_only: bool = False, log=lambda *_: None) -> dict:
    """执行检索并写文件。返回 {query, count, json_path, md_path, results(精简)}。"""
    top = top or CFG["final_top"]
    stage1_max = stage1_max or CFG["stage1_max"]
    model = model or CFG["model"]
    db = Path(db)
    if not db.exists():
        raise SearchError(f"找不到数据库：{db}")
    out_dir = Path(out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    key = load_api_key()
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        scored = two_stage(query, conn, key, model, stage1_max, top, log=log)
        records = enrich(conn, scored) if scored else []
    finally:
        conn.close()

    when = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    folder = out_dir / f"eu3e_search_{slugify(query)}"   # 每次检索独占一个新文件夹
    folder.mkdir(parents=True, exist_ok=True)
    json_path = folder / "results.json"
    payload = {
        "query": query, "generated_at": when, "model": model,
        "database": str(db), "count": len(records), "results": records,
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    md_path = None
    if not json_only:
        md_path = folder / "README.md"
        md_path.write_text(render_readme(query, records, payload, json_path.name), encoding="utf-8")

    return {
        "query": query, "count": len(records), "folder": str(folder),
        "json_path": str(json_path), "md_path": str(md_path) if md_path else None,
        "results": [
            {"rank": r["rank"], "score": r["score"], "grant_id": r["grant_id"],
             "acronym": r["acronym"], "title": r["title"], "reason": r["reason"]}
            for r in records
        ],
    }


# ── CLI ──────────────────────────────────────────────────────────────────────
def main(argv=None):
    ap = argparse.ArgumentParser(
        description="EU 3E 两段式语义检索（命令行版），结果写成 AI 可读的 JSON + Markdown。")
    ap.add_argument("query", help="自然语言的检索描述")
    ap.add_argument("--out-dir", default=".", help="输出文件目录（默认：当前目录）")
    ap.add_argument("--top", type=int, default=CFG["final_top"], help=f"最终结果上限（默认 {CFG['final_top']}）")
    ap.add_argument("--stage1-max", type=int, default=CFG["stage1_max"], help=f"第 1 段候选上限（默认 {CFG['stage1_max']}）")
    ap.add_argument("--db", default=str(DEFAULT_DB), help="eu3e.sqlite 路径")
    ap.add_argument("--model", default=CFG["model"], help=f"Gemini 模型（默认 {CFG['model']}）")
    ap.add_argument("--json-only", action="store_true", help="只写 JSON，不写 Markdown")
    ap.add_argument("--quiet", action="store_true", help="不打印进度")
    args = ap.parse_args(argv)

    log = (lambda *a: None) if args.quiet else (lambda *a: print(*a, file=sys.stderr, flush=True))
    try:
        res = run_search(args.query, args.out_dir, db=args.db, top=args.top,
                         stage1_max=args.stage1_max, model=args.model,
                         json_only=args.json_only, log=log)
    except SearchError as e:
        print(f"检索失败：{e}", file=sys.stderr)
        return 2

    print(f"命中 {res['count']} 个项目 · 查询「{res['query']}」")
    print(f"输出文件夹: {res['folder']}")
    print(f"  JSON: {res['json_path']}")
    if res["md_path"]:
        print(f"  README: {res['md_path']}")
    for r in res["results"][:10]:
        print(f"  [{r['score']:>3}] {r['acronym'] or '—'} — {(r['title'] or '')[:70]}")
    if res["count"] > 10:
        print(f"  …其余 {res['count'] - 10} 个见文件")
    return 0


if __name__ == "__main__":
    sys.exit(main())
