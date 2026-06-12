> **目录说明（2026-06-12）**：仓库已两次整理，本文（历史工作日志）中的旧路径对照如下——`collection/` 即仓库根目录；`scripts/`、`raw/`、`parsed/` 现位于 `pipeline/` 下；12 个 xlsx 现位于 `data/`；`landscape_overview.html`、`webapp_demo.html` 现位于 `docs/`。项目总说明见 [README.md](./README.md)。

# HORIZON Cluster 5 Topics & Projects 数据采集

## 一、原始任务

整理出一个 Excel 文件 `CL5_Topics_and_Projects.xlsx`，包含两张 sheet：

* **Sheet 1（Topics）**：从 2021 年（按用户最终决定）到 2026 年目前为止，欧盟 Horizon Europe 第五工作集群（Cluster 5：Climate, Energy and Mobility）下出现过的**所有 call 和 topic**，精确到 topic 编号，包含 topic 当时的标题和基本信息（destination、call、type、TRL、预算、截止日期等）
* **Sheet 2（Projects）**：每一个 topic 当年资助的**具体项目**，第一列是 topic 编号，第二列是项目名，第三列是项目链接，等等。一个项目一行（不展开到 partner 级别）

### 任务背景

Horizon Europe（2021-2027，预算约 955 亿欧元）的所有 topic 编号都遵循一套层级化命名规则。以 `HORIZON-CL5-2023-D3-01-16` 为例：

| 段 | 例子 | 含义 |
|---|---|---|
| 1 | HORIZON | 计划名称 |
| 2 | CL5 | Cluster 5 |
| 3 | 2023 | 工作计划年份 |
| 4 | D3 | Destination 3 |
| 5 | 01 | 该年该 destination 下的 call 编号 |
| 6 | 16 | 该 call 下的 topic 编号 |

### 用户确认的关键决策

* **收集起始年份**：2021（不收 2020 的 H2020 SC3/SC4，避免框架混杂）
* **预算单位**：Sheet 1 用 €M（百万欧），Sheet 2 用 € 原值
* **项目粒度**：一个项目一行，不展开到 partner level
* **采集方式**：脚本批量抓取，处理缺失，最后人工抽样核对
* **作用域**：仅 `HORIZON-CL5-*` 主工作计划，不含 destination 下的 JU/JTI/Mission 项目（Clean H2、SESAR、Europe's Rail、Missions 各自有独立 work programme）

## 二、完成步骤

### Step 1 — 工作区搭建

```
collection/
├── CL5_Topics_and_Projects.xlsx   # 最终产出
├── README.md                       # 本文档
├── raw/                            # 原始下载
├── parsed/                         # 中间数据 (pkl/csv/json)
└── scripts/                        # 三个独立 Python 脚本
```

### Step 2 — 列结构设计与空模板

先生成只有表头的空 Excel，与用户确认两张 sheet 的列设计：

* **Topics**：21 列（Framework / Year / Cluster / Destination / Call ID / Topic ID / Topic Title / Type / TRL / Budget / Deadline 等）
* **Projects**：18 列（Topic ID / Acronym / Full Name / GA ID / Coordinator / EU Contribution / CORDIS Link 等）

### Step 3 — 数据源策略

无损优先，避免逐页爬虫：

* **项目层**：CORDIS 官方 bulk 数据集 `cordis-HORIZONprojects-xlsx.zip`（50MB，覆盖所有 HE 项目）
* **Topic 层**：F&T Portal topic details JSON 端点 + WP PDF 解析作补充

### Step 4 — 下载 CORDIS bulk 数据

从 `cordis.europa.eu/data/cordis-HORIZONprojects-xlsx.zip` 下载 50MB zip，解压得到：

* `project.xlsx` — 21,196 个 Horizon Europe 项目，含 topic、call、funding、coordinator、status 等 20 列
* `topics.xlsx` — projectID → topic → title 映射
* `organization.xlsx` — 参与机构（用于提取 coordinator 信息）
* `webLink.xlsx` — 项目相关网页链接

### Step 5 — 过滤到 CL5

* 全部 HE 项目 21,196 个
* 其中 `legalBasis=HORIZON.2.5` (Cluster 5 法律基础) 共 1,338 个，含 5 类前缀：
  * `HORIZON-CL5-` 932 个（主工作计划，**最终采纳**）
  * `HORIZON-MISS-` 131 个（EU Missions）
  * `HORIZON-JTI-CLEANH2-` 115 个（Clean Hydrogen JU）
  * `HORIZON-SESAR-` 68 个（SESAR JU）
  * `HORIZON-JU-` / `HORIZON-ER-` 92 个（Europe's Rail JU）
* 用户确认仅取 `HORIZON-CL5-*` 主工作计划

### Step 6 — Topic 编号解析

发现 3 种编号格式，写正则统一解析：

* **老格式（2021-2024）**：`HORIZON-CL5-YYYY-Dx-CC-NN[-suffix]`
* **新格式（2025+）**：`HORIZON-CL5-YYYY-CC-Dx-NN[-suffix]`（call 与 destination 调换顺序）
* **IBA**：`HORIZON-CL5-YYYY-{NAME}-IBA[-N]`（直接预拨款，无 destination）

### Step 7 — 从 CORDIS 直接派生 Sheet 1 骨架

390 个有过资助的 topic，从 CORDIS 直接派生出：

* Topic ID / Title / Year / Destination
* Topic Type（从 `fundingScheme` 推导：RIA / IA / CSA / COFUND）
* Call ID（来自 `masterCall`，按 topic 取众数）
* 已资助项目数、已发放 EU 资金合计（作为补充信息）

### Step 8 — F&T Portal API 探索

* 测试 `api.tech.ec.europa.eu/search-api/prod/rest/search` 搜索 API（multipart POST），但过滤功能受限
* 发现可直接 GET 的关键端点：
  ```
  https://ec.europa.eu/info/funding-tenders/opportunities/data/topicDetails/{topic-id-lowercase}.json
  ```
  返回完整 JSON，含 title、callIdentifier、callTitle、actions（type、opening date、deadline）、budgetOverviewJSONItem（budget map、expected grants、deadline model）、description（含 TRL 文字描述）

### Step 9 — 批量 fetch CORDIS 已知的 390 个 topic

* 写 `fetch_topic_details.py`：URL 缓存到 `raw/topic_details/`、polite rate-limit 0.3s、HTTP 5xx 指数退避、HTTP 404 标记为 missing
* 字段解析：从 budgetTopicActionMap 按 topic ID 前缀匹配抽取 budget；从 description 文本 regex 提取 TRL；时间戳从 Unix ms 转 ISO 日期
* 修复发现的 bug：
  * 两阶段 topic 的 budget map 值为 dict 而非 list
  * 老格式 budget entry 不带 topic ID 前缀（无法匹配，回退到 description regex）
  * IBA topic 没有公开详情页（404，可接受损失）
* 结果：382/390 fetch 成功，8 个 IBA 失败但已从 CORDIS 拿到标题

### Step 10 — 补全 2025/2026 未签约 topic

CORDIS 只有已签约项目，2025 部分 + 2026 全部 topic 还没在 CORDIS 出现。从 Work Programme PDF 提取 ID 列表：

* 下载 `wp-2025-cluster5-pre.pdf`（2.5MB）和 `wp-8-climate-energy-and-mobility_horizon-2026-2027_en.pdf`（2.4MB）
* 用 `pdftotext` / `pypdf` 抽文字，regex 匹配 `HORIZON-CL5-202[5-6]-*` 编号
* 从 2025 WP 得到 76 个 CORDIS 之外的新 ID（2025 后续 + 2026 Call 02）
* 从 2026-2027 WP 得到 42 个全新 2026 ID（2027 的 46 个按用户要求不纳入）
* 用同一个 fetcher 拉这 118 个 topic 的 JSON，加进 Sheet 1

### Step 11 — Merge 到最终 Excel

写 `merge_to_excel.py`：

* 合并 CORDIS 派生表 + F&T Portal 详情表，按 topic ID 去重
* 优先用 F&T Portal 字段，缺失时回退到 CORDIS
* 构建 Sheet 2：用 CORDIS project + organization + webLink 三个表 join，提取 coordinator/country/参与方数/参与国列表/项目主页
* 用 openpyxl 写入，保留 Step 2 已设好的表头与样式

### Step 12 — 抽样核对

随机抽 12 个 topic（每年 2 个）+ 5 个项目，对比 F&T Portal / CORDIS 原页面：

* HVDC-WISE (GA 101075424) — coordinator / funding / dates 全部匹配
* IKIGAI (GA 101202912) — 全部匹配
* HORIZON-CL5-2022-D6-02-05 — 标题 / 类型 / 预算 / 截止日匹配
* HORIZON-CL5-2026-09-D2-01 — 标题 / 预算 / grants / 截止日匹配

## 三、完成效果

### Sheet 1 — Topics

* **508 行 × 21 列，覆盖 2021-2026 全部 6 年**

| Year | D1 | D2 | D3 | D4 | D5 | D6 | IBA | 合计 |
|---|---|---|---|---|---|---|---|---|
| 2021 | 9 | 16 | 34 | 8 | 17 | 13 | 2 | 99 |
| 2022 | 8 | 10 | 31 | 11 | 14 | 15 | 2 | 91 |
| 2023 | 13 | 10 | 40 | 11 | 18 | 13 | 1 | 106 |
| 2024 | 7 | 8 | 30 | 8 | 18 | 12 | 2 | 85 |
| 2025 | 8 | 7 | 12 | 0 | 17 | 4 | 1 | 49 |
| 2026 | 5 | 8 | 29 | 11 | 7 | 18 | 0 | 78 |

* **Topic Type 分布**：RIA 252 / IA 184 / CSA 60 / IBA 8 / COFUND 3 / 其他 1

### Sheet 2 — Projects

* **932 行 × 18 列**
* 总 EU 资助：**€5.51B**
* 时间跨度：2021-2025 已签约项目（2026 calls 多数尚未签约，暂无项目）
* Status：SIGNED 921 / CLOSED 8 / TERMINATED 3

### 字段完成度

| Sheet 1 字段 | 完成率 |
|---|---|
| Framework / Year / Cluster / Topic ID / Portal Link | 100% |
| Destination / Destination Name | 98% |
| Call ID / Call Title | 98% |
| Topic Title / Type | 98-99% |
| Indicative Budget (€M) | 95% |
| EU Contribution per Project (€M) | 90% |
| Expected Number of Projects | 90% |
| Opening / Deadline / Stage | 94-95% |
| **TRL** | **65%**（老 topic 的 TRL 在 WP PDF 正文里没结构化） |
| Keywords / Work Programme PDF | 0%（Keywords 已于 2026-06-11 从缓存 JSON 回填 371/508，见第六节） |

| Sheet 2 字段 | 完成率 |
|---|---|
| 全部核心字段（Topic ID / Acronym / GA ID / Coordinator / Funding / Dates / Status / Links / Objective） | 100% |
| Participant Countries / Number of Participants | 100% |
| Project Website | 4%（CORDIS 本身收录率低，多数项目未登记外部主页） |

### 已知缺失与设计取舍

* **8 个 IBA topic**（OFFSHORE-IBA、SETPLAN-IBA、REDII-IBA、EUDSO-IBA-2）：没有 F&T Portal 详情页，仅有 CORDIS 提供的标题；Destination 列为空。这是直接预拨款，结构上没有 destination 归属
* **TRL 缺失 35%**：老 topic 的 TRL 写在 WP PDF 正文文字里没结构化字段。补救方案：可以再写一个 PDF 解析脚本回填
* **2027 topic 未纳入**：2026-2027 WP 已发布，包含 46 个 2027 topic，按用户要求"到 2026"暂不收
* **Project Website 缺失 96%**：CORDIS 系统性问题，与本采集流程无关

## 四、产出文件清单

```
collection/
├── CL5_Topics_and_Projects.xlsx        # 主产出 (508 topics + 932 projects)
├── README.md                            # 本文档
├── raw/
│   ├── cordis-HORIZONprojects-xlsx.zip  # CORDIS 原始 zip (50MB)
│   ├── cordis_he/                       # 解压后 9 个 xlsx
│   │   ├── project.xlsx
│   │   ├── topics.xlsx
│   │   ├── organization.xlsx
│   │   ├── webLink.xlsx
│   │   └── ...
│   ├── wp_2025_cl5.pdf                  # CL5 工作计划 2025
│   ├── wp_2026_cl5.pdf                  # CL5 工作计划 2026-2027
│   └── topic_details/                   # 508 个 topic 的原始 F&T Portal JSON
│       ├── HORIZON-CL5-2021-D1-01-01.json
│       └── ...
├── parsed/                              # Python pickle / csv / json 中间产物
│   ├── cl5_projects.pkl
│   ├── cl5_topic_titles.pkl
│   ├── topics_from_cordis.pkl/csv
│   ├── topics_ft_details.pkl/csv
│   ├── topics_ft_details_2025_2026.pkl/csv
│   ├── topics_ft_details_2026wp.pkl/csv
│   ├── wp_2025_topic_ids.json
│   ├── wp_new_topic_ids.json
│   └── wp_2026_new_ids.json
└── scripts/
    ├── build_topics_from_cordis.py      # Step 7：从 CORDIS 派生 topic 骨架
    ├── fetch_topic_details.py           # Step 9：从 F&T Portal 拉详情
    └── merge_to_excel.py                # Step 11：合并写入 Excel
```

## 五、可复现

所有数据源都是开放的：

* CORDIS bulk dataset 每月更新，可直接重新下载覆盖 `raw/cordis_he/`
* F&T Portal topic JSON 实时同步官方页面
* 重跑流程：

```bash
cd collection
python3 scripts/build_topics_from_cordis.py    # 重建 topic 骨架
python3 scripts/fetch_topic_details.py          # 增量拉取（缓存命中跳过）
python3 scripts/merge_to_excel.py               # 重新写 Excel
```

* fetch 脚本带 URL 缓存，重跑不会重复请求；改 2027 / 增 JTI / Mission 也只需改 filter 不动管道

## 六、扩展：CL6 采集与口径标记（2026-06-11）

向"土地/饮食/生物多样性/生态"方向扩展（背景见 [landscape_overview.html](./docs/landscape_overview.html)），新增 `CL6_Topics_and_Projects.xlsx`，并给 CL5/CL6 两个工作簿统一加上**已签约/未签约口径标记**。

### CL6 与 CL5 的管道差异

* **Destination 命名式**：CL6 用 FARM2FORK / BIODIV / CIRCBIO / ZEROPOLLUTION / CLIMATE / COMMUNITIES / GOVERNANCE 七个命名 destination（不是 D1-D6），且 CORDIS 中大小写不一致（`CIRCBIO` vs `CircBio`），解析时统一转大写
* **2025+ 新格式**与 CL5 同样调换顺序：`HORIZON-CL6-2025-01-BIODIV-01`（年-call-destination-序号）
* **IBA 变体更乱**：`HORIZON-CL6-OA01-2022-IBA`、`HORIZON-CL6-2023-2025-BIOEAST-IBA-02` 等，按"含 `-IBA` 即 IBA、年份取 ID 中第一个 20xx"处理
* **two-stage 的规范 ID 带后缀**：`...-01-two-stage` 才是 F&T Portal 的真实 ID，合并时若 base 与 two-stage 并存则保留 two-stage
* **未签约 topic 清单来源**：尝试过 F&T Portal 的 `referenceData/grantsTenders.json`（全量 topic+官方状态，123MB），但服务器对大文件限速严重弃用；改走与 CL5 相同的 WP PDF 路线（`raw/wp_2025_cl6.pdf`、`raw/wp_2026_cl6.pdf`，正则提取候选 ID 后用 fetcher 的 404 验证清洗，140 个候选全部有效）

### 口径标记（两个工作簿的 Topics sheet 通用）

| 列 | 含义 |
|---|---|
| Call Status | Open / Closed / Forthcoming，由 opening/deadline 与当天日期推导 |
| Award Status | Signed（CORDIS 有已签约项目）/ Not yet signed |
| Funded Projects (signed) | 该 topic 下已签约项目数 |
| Signed EU Contribution (EUR M) | 已签约项目的 EU 资助合计 |

注意 `Closed + Not yet signed` 组合（CL6 有 96 个）= call 已截止但 grant 还没出现在 CORDIS（评审/签约中），分析"资金已落地"口径时应只取 `Award Status = Signed`；分析"政策意图/题目设置"口径时用全部行 + Indicative Budget。

* CL6 工作簿这 4 列直接内建（25 列）；CL5 工作簿用 `cl5_add_status_columns.py` **原地追加在表尾**（不重写已有单元格，手动修改不受影响），同时回填了 Keywords 列（371/508，来源是缓存的 topicDetails JSON `keywords` 字段——CL6 的 Keywords 同样填充，91%）

### CL6 完成效果

* **Topics：474 行 × 25 列**（2021-2026；已签约口径 354 个 topic，未签约 120 个）
* **Projects：653 行 × 18 列**，总 EU 资助 €3.72B（2021-2024 已签约 + 2025 年 1 个）
* 字段完成度：Title / Type / Budget / Dates / Call Status 99%（缺的是 6 个无详情页的 IBA）；Keywords 91%；TRL 32%（CL6 偏研究型，多数 topic 本来就不写 TRL）
* 已签约金额按 destination：FARM2FORK €880M、BIODIV €714M、GOVERNANCE €638M、CIRCBIO €603M、CLIMATE €375M、ZEROPOLLUTION €287M、COMMUNITIES €211M

### 新增文件

```
collection/
├── CL6_Topics_and_Projects.xlsx        # CL6 主产出 (474 topics + 653 projects)
├── landscape_overview.html             # 欧盟资助全景（全部 cluster×destination + Horizon 之外渠道）
├── raw/
│   ├── wp_2025_cl6.pdf                 # CL6 工作计划 2025
│   └── wp_2026_cl6.pdf                 # CL6 工作计划 2026-2027
├── parsed/
│   ├── cl6_projects.pkl / cl6_topic_titles.pkl
│   ├── cl6_topics_from_cordis.pkl/csv
│   ├── cl6_topics_ft_details.pkl/csv
│   └── cl6_all_topic_ids.json          # WP PDF 提取的 2025/2026 候选 ID
└── scripts/
    ├── cl6_build_topics_from_cordis.py # CORDIS 过滤 + topic 骨架
    ├── cl6_fetch_details.py            # F&T Portal 详情（复用 fetch_topic_details 的缓存）
    ├── cl6_merge_to_excel.py           # 合并写入 CL6 Excel
    └── cl5_add_status_columns.py       # CL5 工作簿原地追加口径列 + 回填 Keywords
```

### CL6 重跑

```bash
cd collection
python3 scripts/cl6_build_topics_from_cordis.py   # CORDIS 重建（需 raw/cordis_he/ 最新数据）
python3 scripts/cl6_fetch_details.py               # 增量拉取（缓存命中跳过）
python3 scripts/cl6_merge_to_excel.py              # 重新写 Excel
```

## 七、扩展：EU Missions 采集 + Participants 表（2026-06-11）

### MISS_Topics_and_Projects.xlsx

覆盖**全部** EU Missions（环境四任务 CLIMA / OCEAN / CIT / SOIL + CANCER / NEB / 跨任务支持），按 Destination 列筛选即可取环境口径：

* **Topics：216 行 × 25 列**（2021-2026；已签约 153 + 未签约 63），列结构与 CL5/CL6 完全一致；Destination 列放任务代码、Destination Name 放任务全名
* **Projects：322 行 × 18 列**，总 EU 资助 €2.48B（环境四任务约 €2.0B，CANCER €0.48B）
* Mission ID 的特殊形态都已处理：SGA（城市/土壤平台专项拨款，Topic Type = SGA）、IBA、**跨任务联合 topic**（`CLIMA-OCEAN-SOIL` 等组合码原样保留在 Destination 列）
* 字段完成度低于 CL5/CL6（标题 94%、日期 84%、预算 ~75%）：SGA/IBA 类 topic 详情页本来就少这些字段，属数据源固有
* 未签约清单来源：`raw/wp_2025_miss.pdf`、`raw/wp_2026_miss.pdf`（WP part 12）
* 脚本：`miss_build_topics_from_cordis.py` / `miss_fetch_details.py` / `miss_merge_to_excel.py`，重跑方式与 CL6 相同

### Participants 表（三个工作簿都有）

回答"每个项目的 partner 列表 + 每个 partner 分多少钱"：CORDIS `organization.xlsx` 自带机构级 `ecContribution`，已整理成各工作簿的第三张 sheet（橙色表头）：

* 一行 = 一个机构在一个项目中的参与；列含机构名/ID、角色（coordinator/participant/...）、国家、城市、机构类型（HES 高校 / REC 科研机构 / PRC 企业 / PUB 公共部门）、SME 标记、**EC Contribution（该机构在该项目分到的 EU 资助）**、Net EC Contribution、Total Cost
* 规模与核对：CL5 14,360 行（€5.51B ✓）、CL6 11,878 行（€3.72B ✓）、MISS 6,987 行（€2.48B ✓）——partner 级金额加总与项目级完全一致
* 生成：`python3 scripts/add_participants_sheet.py <cl5_projects|cl6_projects|miss_projects> <对应 xlsx>`，只重写 Participants sheet，不碰 Topics/Projects（手动修改安全）

### 三个工作簿的对齐状态

* 时间范围：均为 2021-2026（2027 按约定不收）
* 列结构：Topics（25 列）/ Projects（18 列）/ Participants（15 列）三张表在三个文件中**列名列序完全一致**，可直接 concat 做跨 cluster 分析
* 已签约/未签约口径：统一用 Call Status + Award Status + Funded Projects (signed) + Signed EU Contribution (EUR M) 四列标记

### 顺手修的 bug

* `fetch_topic_details.py` 的 budgetYearMap 解析用 `int()`，遇到 Mission topic 的浮点预算值（如 `'2999999.9'`）会崩，已改 `float()`（CL5/CL6 数据不受影响，无需重跑）

## 八、Horizon Europe 全景参照系与采集覆盖

> 目的：把欧盟主要科研经费来源的领域结构列全、标出本项目的采集范围，做数据分析时统计口径统一对到 **destination 层**。
> 本节所有项目数与金额 = CORDIS 快照中**已签约项目的 EU 资助**（基本覆盖 2021-2024 签约年份，2025 起多数未签约），与工作计划的指示性预算是两个口径。

### 8.1 总体结构（Horizon Europe 2021-2027，预算约 €955 亿）

* **Pillar I 卓越科学**：ERC（前沿自由探索）、MSCA（人才流动）、Research Infrastructures —— 自下而上选题，**不按主题领域组织**
* **Pillar II 全球挑战与产业竞争力**：六大 Cluster（主题型工作计划，**本项目的核心采集对象**）+ JRC
* **Pillar III 创新欧洲**：EIC（深科技创业资助）、EIE（创新生态）、EIT（知识创新社区）
* **横向部分**：Widening（扩大参与）、ERA（科研体制改革）
* **跨切机制**：EU Missions（五大任务，独立工作计划）；制度化伙伴关系 Joint Undertakings（各自独立工作计划）
* Euratom 核研究为并行补充计划

### 8.2 六大 Cluster × Destination 明细

✅ = 已采集到本项目的结构化数据（topic + project + participant 三层）

**CL1 健康（topic 前缀 `HORIZON-HLTH`）— 429 项 / €3.76B　❌ 未采集（与能源环境无关）**

| Destination | 主题 | 项目 | EU €M |
|---|---|---|---|
| DISEASE | 疾病防治与疾病负担 | 153 | 1,372 |
| TOOL | 健康新工具/技术/数字方案 | 81 | 606 |
| ENVHLTH | 健康促进的生活工作环境（环境健康） | 46 | 504 |
| STAYHLTH | 快速变化社会中的健康维持 | 58 | 461 |
| CARE | 创新可持续的医疗服务可及性 | 36 | 387 |
| IND | 健康产业竞争力 | 31 | 166 |
| 其他（CEPI/CORONA 等专项） | 应急/联合资助 | 16 | 260 |

**CL2 文化·创造力·包容社会 — 333 项 / €1.04B　❌ 未采集（相关性低）**

| Destination | 主题 | 项目 | EU €M |
|---|---|---|---|
| TRANSFORMATIONS | 社会经济转型研究 | 115 | 336 |
| HERITAGE（含 ECCCH） | 文化遗产与文创产业 | 107 | 397 |
| DEMOCRACY | 民主与治理 | 105 | 306 |

**CL3 民事安全 — 192 项 / €0.82B　❌ 未采集（仅 DRS 灾害韧性略沾边）**

| Destination | 主题 | 项目 | EU €M |
|---|---|---|---|
| CS | 网络安全 | 55 | 269 |
| FCT | 打击犯罪与恐怖主义 | 41 | 163 |
| DRS | 灾害韧性社会（含气候相关灾害） | 37 | 160 |
| BM | 边境管理 | 28 | 123 |
| INFRA | 关键基础设施韧性 | 10 | 60 |
| SSRI | 安全研究与创新支撑 | 21 | 40 |

**CL4 数字·工业·空间 — 939 项 / €5.75B　❌ 未采集（TWIN-TRANSITION 与 RESILIENCE 两个 destination 与能源环境直接相关，列为候选扩展）**

| Destination | 主题 | 项目 | EU €M |
|---|---|---|---|
| TWIN-TRANSITION | 气候中和·循环·数字化生产（工业脱碳、清洁钢铁、Processes4Planet）⚠️ 候选 | 186 | 1,440 |
| RESILIENCE | 关键战略价值链自主（材料、关键原材料、循环工业）⚠️ 候选 | 210 | 1,313 |
| DIGITAL-EMERGING | 数字与新兴技术（AI、芯片、6G 方向） | 212 | 1,113 |
| HUMAN | 以人为本的数字与工业技术 | 134 | 713 |
| DATA | 数据与计算技术 | 70 | 496 |
| SPACE | 空间基础设施自主 | 93 | 388 |
| QUANTUM | 量子技术 | 8 | 168 |

**CL5 气候·能源·交通 — 932 项 / €5.51B　✅ 已采集（`CL5_Topics_and_Projects.xlsx`）**

| Destination | 主题 | 项目 | EU €M |
|---|---|---|---|
| D3 | 可持续、安全、有竞争力的能源供给（可再生、电网、储能、氢能） | 358 | 2,267 |
| D5 | 各种运输方式的清洁解决方案（电动化、电池、航空航运） | 158 | 955 |
| D2 | 气候转型的跨部门方案（含气候经济建模、碳定价研究） | 137 | 701 |
| D6 | 安全韧性交通与智慧出行 | 106 | 623 |
| D1 | 气候科学与响应路径（IPCC 支撑科学） | 84 | 498 |
| D4 | 高效、可持续、包容的能源使用（建筑、工业能效） | 81 | 460 |
| IBA | 直接预拨款（OFFSHORE/SETPLAN/REDII/EUDSO） | 8 | 7 |

**CL6 食物·生物经济·自然资源·农业·环境 — 653 项 / €3.72B　✅ 已采集（`CL6_Topics_and_Projects.xlsx`）**

| Destination | 主题 | 项目 | EU €M |
|---|---|---|---|
| FARM2FORK | 公平健康环境友好的食物系统 | 135 | 880 |
| BIODIV | 生物多样性与生态系统服务 | 108 | 714 |
| GOVERNANCE | 绿色转型治理（环境观测、数据、行为） | 130 | 638 |
| CIRCBIO | 循环经济与生物经济 | 120 | 603 |
| CLIMATE | 土地·海洋·水的气候行动（碳汇、农林气候） | 50 | 375 |
| ZEROPOLLUTION | 零污染（土壤、水、空气、化学品） | 64 | 287 |
| COMMUNITIES | 农村·沿海·城市社区韧性 | 40 | 211 |
| IBA | 直接预拨款 | 6 | 5 |

### 8.3 EU Missions — 322 项 / €2.48B　✅ 已采集（`MISS_Topics_and_Projects.xlsx`，含全部任务）

| Mission（=工作簿 Destination 列） | 主题 | 项目 | EU €M |
|---|---|---|---|
| CLIMA | 气候变化适应 | 61 | 536 |
| OCEAN | 海洋与水体修复 | 81 | 479 |
| CIT | 100 个气候中和智慧城市 | 37 | 468 |
| SOIL | 土壤健康（Soil Deal） | 60 | 438 |
| CANCER | 癌症任务（非能源环境，已含可筛除） | 59 | 483 |
| NEB / CROSS 等 | 新欧洲包豪斯、跨任务支持 | 24 | 74 |

### 8.4 制度化伙伴关系（Joint Undertakings）

能源环境五家 ✅ 已采集（`JU_Topics_and_Projects.xlsx`，=工作簿 Destination 列；**仅已签约**，JU 各自 WP 的未签约 topic 未收）：

| JU | 领域 | 项目 | EU €M |
|---|---|---|---|
| CLEAN-AVIATION | 清洁航空（机体/动力脱碳示范） | 40 | 1,177 |
| CLEANH2 | 清洁氢能（制储运用全链条） | 142 | 895 |
| CBE | 循环生物基产业 | 84 | 542 |
| ER | 铁路系统创新（Europe's Rail） | 25 | 287 |
| SESAR | 空管数字化（单一欧洲天空） | 68 | 229 |

其他 JU ❌ 未采集（与能源环境无关）：IHI 创新医药 56 项/€708M、SNS 6G 网络 79 项/€499M、GH-EDCTP3 全球健康 107 项/€435M、Chips 半导体 22 项/€1.05B、EuroHPC 高性能计算 16 项/€184M

### 8.5 非主题型 programme（均 ❌ 未采集——不按领域组织，无法对到 destination 层）

| Programme | 定位 | 项目 | 已签约 EU |
|---|---|---|---|
| ERC | 前沿自由探索（个人 PI 制） | 6,099 | €11.35B |
| MSCA | 博士/博后流动资助 | 7,831 | €4.27B |
| EIC | 深科技初创与突破技术（含大量清洁技术，但按企业不按主题） | 1,371 | €3.65B |
| EIT | 知识创新社区（含 EIT Climate-KIC、InnoEnergy） | 29 | €1.56B |
| Widening | 扩大参与（中东欧追赶） | 658 | €1.49B |
| Research Infrastructures | 大型科研基础设施 | 183 | €1.24B |
| Euratom | 核裂变/聚变研究 | 61 | €0.82B |
| EIE / ERA | 创新生态与科研体制 | 398 | €0.66B |

### 8.6 采集覆盖汇总

| 范围 | 文件 | Topics（含未签约） | Projects（已签约） | 已签约 EU | 状态 |
|---|---|---|---|---|---|
| CL5 气候能源交通 | CL5_Topics_and_Projects.xlsx | 508 | 932 | €5.51B | ✅ 2021-2026 |
| CL6 食物农业环境 | CL6_Topics_and_Projects.xlsx | 474 | 653 | €3.72B | ✅ 2021-2026 |
| EU Missions（全部） | MISS_Topics_and_Projects.xlsx | 216 | 322 | €2.48B | ✅ 2021-2026 |
| 能源环境五 JU | JU_Topics_and_Projects.xlsx | 246 | 359 | €3.13B | ✅ 仅已签约 |
| **合计** | 4 个工作簿 × 4 sheets | **1,444** | **2,266** | **€14.84B** | |

* 每个工作簿四张表：Topics / Projects / Participants（机构×项目级资金）/ Organisations（机构聚合排名），列结构跨文件一致，**Destination 列即统一的领域分析层**
* 候选扩展：CL4 的 TWIN-TRANSITION + RESILIENCE（合计 396 项 / €2.75B）；Horizon 之外的 LIFE、Innovation Fund 等见 [landscape_overview.html](./docs/landscape_overview.html)

## 九、扩展：JU 采集 + Organisations 机构聚合表（2026-06-11）

### JU_Topics_and_Projects.xlsx

能源环境五家 Joint Undertaking（CLEANH2 / CBE / CLEAN-AVIATION / ER / SESAR）：

* **Topics：246 行 × 25 列**（全部已签约口径——各 JU 工作计划独立、格式不一，未签约 topic 暂不收，Award Status 全为 Signed）
* **Projects：359 行 × 18 列**，€3.13B；Participants 5,585 行；Organisations 2,675 家
* JU 编号语法五花八门（CBE 把 RIA/IA 写进 ID、SESAR 有 work-area 层），所以只解析年份和 JU 归属：**Destination 列 = JU 代码**，call/destination 不强行拆
* 246 个 topic 在 F&T Portal 全部有详情页；Topic Type 主要靠 CORDIS fundingScheme 推导（F&T 的 JU action type 命名不规范）
* 注意 `HORIZON-ER` 前缀会误抓 `HORIZON-ERC-*`，过滤用 `HORIZON-ER-JU`
* 脚本：`ju_build_topics_from_cordis.py` / `ju_fetch_details.py` / `ju_merge_to_excel.py`

### Organisations 表（四个工作簿都有，紫色表头）

Participants 行聚合到**机构**层级（按 organisationID 去重），一行一家机构：参与项目数、当 coordinator 次数、累计 EC Contribution，按金额降序排列。各 scope 头部机构符合领域直觉：CL5 = Fraunhofer / CEA / CERTH，CL6 = Wageningen / INRAE / Aarhus，MISS = Climate-KIC / ICLEI，JU = Airbus / DLR / Safran。

* 生成：`python3 scripts/add_organisations_sheet.py <pkl_stem> <xlsx>`，只重写 Organisations sheet

### 最终结构：4 工作簿 × 4 sheets，列结构逐一对齐

| 工作簿 | Topics | Projects | Participants | Organisations |
|---|---|---|---|---|
| CL5 | 508 | 932 | 14,360 | 6,199 |
| CL6 | 474 | 653 | 11,878 | 5,403 |
| MISS | 216 | 322 | 6,987 | 3,847 |
| JU | 246 | 359 | 5,585 | 2,675 |

## 十、扩展：CL4 工业/材料谱系 + LIFE / Innovation Fund topic 层（2026-06-11）

### CL4_Topics_and_Projects.xlsx（完整四张表）

CL4 中与能源环境相关的工业/材料谱系：**146 topics（含 25 个未签约）/ 396 projects / €2.75B / Participants 6,366 / Organisations 3,485**（头部机构 Fraunhofer、SINTEF、VTT——典型材料工业画像）。

* **重要发现：该谱系在新 WP 中两次更名**——2021-2024 为 TWIN-TRANSITION + RESILIENCE，2025 WP 为 TWIN-TRANSITION + MATERIALS，2026-27 WP 合并为 MAT-PROD。四个 destination 代码都收进 scope，Destination Name 列注明所属 WP 年代
* CL4 destination 是多词命名（TWIN-TRANSITION），解析正则与 CL5/CL6 不同（非贪婪多段匹配到首个数字段）
* 脚本：`cl4_build_topics_from_cordis.py` / `cl4_fetch_details.py` / `cl4_merge_to_excel.py`

### LIFE_Topics.xlsx / INNOVFUND_Topics.xlsx（仅 Topics 一张表）

Horizon 之外两个最相关计划的 **topic 层**，列结构与其他工作簿的 Topics 表一致：

* **LIFE：196 topics（2021-2026 全覆盖）**，按子计划分 Destination：CET 90（清洁能源转型）/ CLIMA 31 / NAT 30（自然与生物多样性）/ ENV 24（循环经济）/ OTHER 21，指示预算合计 €3.76B
* **Innovation Fund：27 topics/calls（2021-2025）**：NZT 净零技术大额 call 15 个 + 氢能竞拍 8 + 早期 LSC/SSC，指示预算合计 €56.8B（ETS 收入，体量远超 Horizon 同领域）
* **采集方法**：两者的 call/topic 都在 F&T Portal 上——用 SEDIA 搜索 API 按 `frameworkProgramme` 过滤（LIFE2027=43252405，INNOVFUND=43089234）分页拉清单，再用同一 topicDetails 端点抓详情。脚本：`life_collect_topics.py` / `innovfund_collect_topics.py` / `topics_only_merge.py`
* **已知边界：项目/受益人层无公开 bulk 数据**——LIFE 和 IF 的获资项目只在 CINEA 的 Qlik dashboard 里（页面可手动导出但无 API；两者都不在 CORDIS），故 Award Status 等四列留空，Notes 列注明。若将来需要，可从 dashboard 手动导出或用 Financial Transparency System 年度受益人数据补
* Innovation Fund 2020 年首批 LSC/SSC call 早于 F&T Portal 体系，无 topic 页，未纳入

### 全部产出（7 个数据文件）

| 文件 | 范围 | Topics | Projects | 已签约 EU |
|---|---|---|---|---|
| CL5_Topics_and_Projects.xlsx | 气候能源交通 | 508 | 932 | €5.51B |
| CL6_Topics_and_Projects.xlsx | 食物农业环境 | 474 | 653 | €3.72B |
| MISS_Topics_and_Projects.xlsx | EU Missions 全部 | 216 | 322 | €2.48B |
| JU_Topics_and_Projects.xlsx | 能源环境五 JU | 246 | 359 | €3.13B |
| CL4_Topics_and_Projects.xlsx | 工业/材料谱系 | 146 | 396 | €2.75B |
| LIFE_Topics.xlsx | LIFE（topic 层） | 196 | — | 指示 €3.76B |
| INNOVFUND_Topics.xlsx | Innovation Fund（topic 层） | 27 | — | 指示 €56.8B |
| **合计** | | **1,813** | **2,662** | **€17.59B 已签约** |

## 十一、扩展：Horizon 2020（2014-2020）回溯（2026-06-11）

把时间轴拉回 2014：下载 CORDIS H2020 bulk（`raw/cordis-h2020projects-xlsx.zip`，35,389 个项目 / €68.3B，解压在 `raw/cordis_h2020/`），按 HE 同构产出 5 个工作簿（四张表齐全，列结构与 HE 工作簿逐列一致）：

| 文件 | 范围 | Topics | Projects | 已签约 EU |
|---|---|---|---|---|
| H2020_SC3_Topics_and_Projects.xlsx | SC3 能源（→ CL5 D3/D4 前身） | 264 | 1,390 | €4.65B |
| H2020_SC4_Topics_and_Projects.xlsx | SC4 交通（→ CL5 D5/D6 前身） | 199 | 920 | €2.87B |
| H2020_SC2_Topics_and_Projects.xlsx | SC2 食物农业生物经济（→ CL6 前身） | 245 | 801 | €2.79B |
| H2020_SC5_Topics_and_Projects.xlsx | SC5 气候环境资源（→ CL5 D1/D2 + CL6 + CL4 原材料前身） | 191 | 749 | €3.12B |
| H2020_JTI_Topics_and_Projects.xlsx | 五 JTI（FCH/CS2/S2R/SESAR/BBI → 当今五家 JU） | 965 | 1,079 | €4.17B |
| **小计** | | **1,864** | **4,939** | **€17.60B** |

### 对齐方式与口径差异（重要）

* **过滤口径**：SC 按 `legalBasis`（H2020-EU.3.2/3.3/3.4/3.5），JTI 按 topic 前缀（FCH/JTI-CS2/CS2/S2R/SESAR/BBI，含 `.` 分隔变体）从各 SC 中分离——注意 `CS2-*`（Clean Sky 2 主拨款 GAM，18 项 €1.27B）不带 JTI- 前缀，漏掉会错归 SC4
* **Destination 列 = topic 前缀族**（H2020 没有 destination 层）：LCE/EE/LC-SC3-RES（能源）、MG/GV（交通）、SFS/BG/RUR（食物）、LC-CLA/CE-SC5（气候环境）等，常见族的含义写在 Destination Name；前缀族即 H2020 侧的领域分析层
* **Topic 层只有 CORDIS 派生字段**：指示预算/开闭日期/TRL/Keywords 留空（F&T Portal 对 H2020 覆盖不全，未启用）；全部行 Call Status = Closed、Award Status = Signed
* SME Instrument 项目（EIC 前身）记在各 SC 预算下，保留并以 SMEINST 族标出（SC2 203 项 / SC3 238 / SC4 269 / SC5 152，金额都不大）；2020 绿色新政特别 call = LC-GD 族
* 脚本：`h2020_build_workbooks.py`（一次产出 5 个工作簿，内部调用 participants/organisations 脚本，新增第三参数指定 `cordis_h2020` 数据目录）

### 全部产出更新：12 个数据文件

HE 7 个（见第十节）+ H2020 5 个 = **3,677 topics / 7,601 projects / 97,102 机构×项目 / €35.19B 已签约，时间跨度 2014-2026**。landscape_overview.html 第 6 节为 H2020 回溯专章，第 7 节覆盖汇总已更新。

## 十二、数据库 Web 前端（2026-06-11）

`webapp/` 是全量数据的交互查询前端（纯静态 SPA，hash 路由）：

* **启动**：`cd collection/webapp && python3 -m http.server 8742`，浏览器开 `http://localhost:8742`（需要 http 服务因为数据走 fetch；图表库 ECharts 走 CDN 需联网）
* **结构**：首页（Sankey 资金流 + 12 板块卡片）→ 板块页（Destination treemap / 年度柱图点击联动筛选 topic 表 → 点 topic 展开项目列表）→ **项目详情页**（全字段 + 全部参与机构及各自 EC Contribution + 摘要；机构行点击跳综合检索）；**综合检索页**：关键词/机构名搜索（模式可选），结果一项目一行（板块/起始年/状态/EU 资助/总预算/coordinator），**列头点击排序**，状态由当前日期与起止日期推导（进行中/已结束/未开始/已终止）
* **数据**：`scripts/webapp_export_data.py` 把 12 个 xlsx 导出为 `webapp/data/*.json`——meta/topics/projects 首屏加载（~7MB），participants/objectives 按板块懒加载；xlsx 更新后重跑该脚本即可
* LIFE / Innovation Fund（无项目层）在板块页展示 topic 表（指示预算口径），不进入项目检索；首页 Sankey 只画已签约资金避免口径混置
* `webapp_demo.html` 是此前的设计确认 demo（含跨板块 topic 检索和机构 top 120 画像，正式版未覆盖的两个视图暂留此处）
