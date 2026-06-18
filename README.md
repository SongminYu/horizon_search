# EU Horizon 能源·环境·气候研究资助数据库（2014-2026）

欧盟 **Horizon 2020 + Horizon Europe** 在能源、环境、气候、食物农业、交通领域研究资助的结构化数据集 + 交互查询网站（**资助图谱 / Pivot Explorer**）。

**范围**：仅 Horizon——9 个项目板块（CL4、CL5、CL6、EU Missions，以及 H2020 的 SC2/SC3/SC4/SC5/JTI）。已剔除 JU、LIFE、Innovation Fund；"机构"只指 CORDIS 受资助的参与方（不建模论文署名机构）。

**规模**：3,208 个 topic ｜ 7,242 个已签约项目 ｜ 27,822 家参与单位（去重）｜ 91,517 条单位×项目参与记录 ｜ 91,926 名可检索研究者（OpenAlex 论文署名）｜ 53,217 篇论文（97% 带 DOI）｜ **€32.1B 已签约 EU 资助** ｜ 2014-2026。

## 架构：一个 SQLite 主库

```
raw/ (CORDIS bulk + OpenAlex 缓存)         不进 git，可重新下载
   │  采集脚本（每板块）
   ▼
data/<block>_Topics_and_Projects.xlsx     不进 git，临时构建中间物
   │  build_database.py
   ▼
eu3e.sqlite                               ★ 提交进 git 的主数据库（唯一真源）
   │  export_webapp.py
   ▼
webapp/data/*.json                        静态网站数据（提交进 git）
   │
   ▼  webapp/index.html （纯 JS 资助图谱）
```

**`eu3e.sqlite`（93MB）是主库、唯一真源**，网站由它生成。两条更新路径：
- **日常 / 增量**：直接改 `eu3e.sqlite`（普通 SQLite 文件，网站用到的字段全在里面）→ 跑 `export_webapp.py`，不碰 `data/`。
- **完整重采**（CORDIS/OpenAlex 出新 bulk）：重下 `raw/` → 采集脚本重建 `data/`（临时）→ `build_database.py` 重建 `eu3e.sqlite` → `export_webapp.py`。

`data/`、`pipeline/raw/`、`pipeline/parsed/` 都不进 git，内容已全部进 `eu3e.sqlite`。

### SQLite 表结构（5 个实体 + 关系）

* `topic`(id, title, destination, block, type, budget_eur_m, status) · `topic_keyword`(topic_id, keyword)
* `project`(grant_id, acronym, title, block, eu_contribution_eur, start_date, end_date, status, coordinator, coordinator_country, topic_id, objective)
* `unit`(org_id, name, country, activity_type, sme, total_ec_eur, n_projects, coordinator_count) — CORDIS 受资助 partner
* `project_unit`(grant_id, org_id, ec_eur) — 参与关系 + 该单位分到的 EU 经费
* `researcher`(author_id, name, orcid, country, main_institution, works_total, lead_works, topics) — 过滤到 ≥1 lead 或 ≥2 篇
* `project_researcher`(grant_id, author_id)
* `work`(work_id, title, year, doi, url) · `work_project`(work_id, grant_id) · `work_author`(work_id, author_id)
* `meta`(key, value) — blocks JSON + doi_pct

## 快速开始

```bash
cd webapp && python3 -m http.server 8742    # 浏览器开 http://localhost:8742（纯静态，无后端）
```

**资助图谱（Pivot Explorer）有三种用法：**

1. **关键词全景（语义检索）**：首页搜一段自然语言描述（如"和 power-to-x 有关、且涉及能源与农业系统耦合的项目"），由 **Gemini 两段式语义检索**得到相关项目集 → 下方三个 tab 大表：**项目**（带相关度 0–100 分 + 一句理由）、**参与单位**、**人**；卡片右下角两个 icon 打开**合作网络**（参与单位共参网络 / 共同作者网络，零依赖力导向图）。
2. **实体逐层跳转**：下拉直接进某个 topic / 项目 / 参与单位 / 研究者 / 论文，落地后点邻居 pivot；论文带 DOI、摘要实时取自 OpenAlex。
3. **检索历史**：每次检索自动存浏览器（localStorage），顶栏"历史"icon 打开历史表，可一键回到任意一次结果（不重新调用 Gemini）或删除。

### 启用语义检索（需要 Gemini key）

关键词全景由 Gemini 驱动，需先填 key（仅本地用）：

1. 到 [aistudio.google.com/apikey](https://aistudio.google.com/apikey) 申请（免费）。
2. 打开 `webapp/apikey.local.js`，把 key 粘进引号里。该文件已 gitignore。
3. 刷新页面即可搜。**不要把带 key 的版本公开部署**（key 会暴露在前端）。

检索流程（全在浏览器，无后端）：**第 1 段**把全部 7,242 个项目的"标题 + 300 字摘要片段"（`proj_catalog.json`，约 0.6M tokens）发给 Gemini 2.5 Flash 粗筛出 ≤100 个候选；**第 2 段**取这些候选的完整 objective，按 0–100 rubric 打分，取前 50 排序展示。单次约 30–60 秒、付费档约 $0.2。无 key 时全景页给出填 key 指引。

**直接用 SQLite / pandas**：`eu3e.sqlite` 是标准 SQLite，可直接 `sqlite3` 查询或 `pd.read_sql` 做全库分析。"资金已落地"口径取 `project.eu_contribution_eur`；"政策意图"口径用 `topic.budget_eur_m`（仅 HE 板块有）。

## 数据板块一览

| 板块 | 范围 | 跨度 | Topics | Projects | 已签约 EU |
|---|---|---|---|---|---|
| CL5 | HE Cluster 5 气候·能源·交通 | 2021-2026 | 508 | 932 | €5.51B |
| CL6 | HE Cluster 6 食物·农业·生物经济·环境 | 2021-2026 | 474 | 653 | €3.72B |
| CL4 | HE Cluster 4 工业/材料谱系 | 2021-2026 | 146 | 396 | €2.75B |
| MISS | EU Missions 全部五任务 + NEB | 2021-2026 | 216 | 322 | €2.48B |
| H2020-SC3 | H2020 能源（CL5 D3/D4 前身） | 2014-2020 | 264 | 1,390 | €4.65B |
| H2020-SC4 | H2020 交通（CL5 D5/D6 前身） | 2014-2020 | 199 | 920 | €2.87B |
| H2020-SC2 | H2020 食物农业生物经济（CL6 前身） | 2014-2020 | 245 | 801 | €2.79B |
| H2020-SC5 | H2020 气候环境资源（CL5 D1/D2 + CL6 前身） | 2014-2020 | 191 | 749 | €3.12B |
| H2020-JTI | H2020 五 JTI（能源环境产业伙伴关系前身） | 2014-2020 | 965 | 1,079 | €4.17B |

## 数据更新（`pipeline/`）

每个板块三段式建工作簿：`*_build_topics_from_cordis.py`（CORDIS 过滤 + topic 骨架）→ `*_fetch_details.py`（F&T Portal 详情，带缓存与限速）→ `*_merge_to_excel.py`（写 Topics + Projects 表）。`h2020_build_workbooks.py` 一键建五个 H2020 工作簿。再补三张表：

```bash
python3 pipeline/scripts/add_participants_sheet.py <stem> <workbook.xlsx> [raw_subdir]
python3 pipeline/scripts/add_organisations_sheet.py <stem> <workbook.xlsx>
python3 pipeline/scripts/fetch_people.py <workbook.xlsx>      # 按 Grant ID 查 OpenAlex，缓存 raw/people/，跨板块共享
python3 pipeline/scripts/add_people_sheet.py <workbook.xlsx>
python3 pipeline/scripts/enrich_works_doi.py                  # 论文 DOI 链接 → raw/works_doi.json
```

然后建库 + 出网站数据：

```bash
python3 pipeline/scripts/build_database.py    # data/*.xlsx + raw/people 缓存 + works_doi → eu3e.sqlite
python3 pipeline/scripts/export_webapp.py     # eu3e.sqlite → webapp/data/*.json（含 proj_catalog.json）
```

`build_database.py` 持有 9 个 Horizon 板块的 `PROGS` 注册表与研究者合并/过滤；`export_webapp.py` 只读 SQLite。依赖：`pandas`、`openpyxl`、采集阶段需系统 `pdftotext`（poppler）；网络请求全用标准库，无需 key。`pipeline/raw/` 不进 git，从零重跑需按 WORKLOG 下载 CORDIS bulk zip 与工作计划 PDF。

## 口径与已知边界（分析前必读）

* **金额双口径，不可混加**：`project.eu_contribution_eur` = CORDIS 已签约实际资助（基本覆盖 2021-2024 签约，2025 起多数 call 未签约）；`topic.budget_eur_m` = 工作计划指示预算。
* **H2020 侧**：topic 级指示预算 / 日期 / TRL / Keywords 未采集（F&T Portal 对 H2020 覆盖不全，相应字段为空）；Destination 为编号前缀族，非官方结构。
* **人员 / 论文层是署名代理**：研究者按项目 Grant ID 在 OpenAlex 匹配受资助论文的作者——是"共同作者"代理，**不是**官方项目角色（拿不到 WP/task 分工，机构可能与 partner 不一致）。论文覆盖随项目成熟度呈梯度：约 44–70% 的项目有关联论文（RIA/IA 研究类高，CSA/支持类与刚开始的新项目接近 0）。**已结题项目论文/研究者为零通常是对的（多为 CSA 协调类），不是数据缺口。** 按 Lead Works（一作/末位/通讯）排序压噪，隐去仅挂名一次的中间作者。
* **范围取舍**：仅收能源·环境·气候相关板块；CL1/CL2/CL3、ERC/MSCA/EIC、JU/LIFE/Innovation Fund 未纳入（可按管道模式随时扩展）。2027 topic 未纳入。

## 数据来源

* [CORDIS bulk datasets](https://cordis.europa.eu/data/)（HE + H2020 项目与参与方，每月更新，CC-BY）
* F&T Portal `topicDetails` JSON 端点（topic 详情）
* [OpenAlex](https://openalex.org)（按 `awards.funder_award_id` = Grant ID 匹配受资助论文 → 作者/ORCID/机构/主题，构建研究者与论文层；免费 API，无需 key）
* Horizon Europe 工作计划 PDF（2025、2026-27，各 cluster 与 Missions）
* 检索：网站关键词全景用 Google Gemini API（`gemini-2.5-flash`，仅本地填 key）

更详细的采集过程、口径决策与踩坑记录见 [WORKLOG.md](./WORKLOG.md)（注：WORKLOG 写于剔除 JU/LIFE/IF 之前，部分范围描述偏旧）。
