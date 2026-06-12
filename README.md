# EU 能源·环境·气候研究资助数据库（2014-2026）

欧盟在**能源、环境、气候、食物农业、交通**领域研究资助的结构化全量数据集 + 交互查询网站。覆盖 Horizon 2020 与 Horizon Europe 两个框架期的相关板块、EU Missions、能源环境五家产业伙伴关系（JU/JTI）及其前身，以及 LIFE 和 Innovation Fund 的 topic 层。

**规模**：12 个数据板块 ｜ 3,677 个 topic ｜ 7,601 个已签约项目 ｜ 97,102 条机构×项目参与记录 ｜ 28,802 家机构（去重）｜ **€35.2B 已签约 EU 资助** ｜ 时间跨度 2014-2026。

## 仓库结构

```
.
├── README.md          # 本文档（入口）
├── WORKLOG.md         # 完整工作日志（采集过程、口径决策、踩坑记录）
├── data/              # 12 个 Excel 工作簿（核心数据产品，列结构跨文件一致）
├── docs/              # landscape_overview.html 欧盟资助全景参照系
│                      # webapp_demo.html 早期设计 demo（含正式版未搬的两个视图）
├── webapp/            # 交互查询网站（纯静态 SPA + JSON 数据）
└── pipeline/          # 数据管道（更新数据时才需要）
    ├── scripts/       # 全部采集/构建脚本
    ├── raw/           # 原始下载（412MB，不进 git，可按 WORKLOG 重新下载）
    └── parsed/        # 中间产物（不进 git，可由脚本重新生成）
```

## 快速开始

**交互网站**（推荐入口）：

```bash
cd webapp && python3 -m http.server 8742    # 浏览器开 http://localhost:8742
```

首页 Sankey 资金流 + 12 板块卡片 → 板块页（Destination/年度图点击联动筛选 topic 表）→ 点 topic 展开项目 → 项目详情页（全部 partner 及各自资金、摘要）。综合检索页支持关键词/机构名搜索、板块与状态筛选、列头排序。ECharts 走 CDN，需联网。

**全景参照系**：浏览器直接打开 `docs/landscape_overview.html`，欧盟主要科研资金来源的领域结构全图（所有 cluster × destination、全部 JU、Pillar I/III、Horizon 之外渠道），标注本数据集的覆盖范围。

**直接用 Excel / pandas**：`data/` 下所有工作簿列结构一致，跨文件 `pd.concat` 即可做全库分析。"资金已落地"口径取 `Award Status = Signed`；"政策意图/题目布局"口径用全部行 + Indicative Budget。

## 数据板块一览（`data/`）

| 文件 | 范围 | 跨度 | Topics | Projects | 已签约 EU |
|---|---|---|---|---|---|
| `CL5_Topics_and_Projects.xlsx` | HE Cluster 5 气候·能源·交通（D1-D6） | 2021-2026 | 508 | 932 | €5.51B |
| `CL6_Topics_and_Projects.xlsx` | HE Cluster 6 食物·农业·生物经济·环境 | 2021-2026 | 474 | 653 | €3.72B |
| `MISS_Topics_and_Projects.xlsx` | EU Missions 全部五任务 + NEB | 2021-2026 | 216 | 322 | €2.48B |
| `JU_Topics_and_Projects.xlsx` | 能源环境五 JU（CleanH2/CBE/Clean Aviation/ER/SESAR3） | 2021-2025 | 246 | 359 | €3.13B |
| `CL4_Topics_and_Projects.xlsx` | HE Cluster 4 工业/材料谱系 | 2021-2026 | 146 | 396 | €2.75B |
| `H2020_SC3_Topics_and_Projects.xlsx` | H2020 能源（CL5 D3/D4 前身） | 2014-2020 | 264 | 1,390 | €4.65B |
| `H2020_SC4_Topics_and_Projects.xlsx` | H2020 交通（CL5 D5/D6 前身） | 2014-2020 | 199 | 920 | €2.87B |
| `H2020_SC2_Topics_and_Projects.xlsx` | H2020 食物农业生物经济（CL6 前身） | 2014-2020 | 245 | 801 | €2.79B |
| `H2020_SC5_Topics_and_Projects.xlsx` | H2020 气候环境资源（CL5 D1/D2 + CL6 前身） | 2014-2020 | 191 | 749 | €3.12B |
| `H2020_JTI_Topics_and_Projects.xlsx` | H2020 五 JTI（五 JU 前身） | 2014-2020 | 965 | 1,079 | €4.17B |
| `LIFE_Topics.xlsx` | LIFE 计划（仅 topic 层） | 2021-2026 | 196 | — | 指示 €3.76B |
| `INNOVFUND_Topics.xlsx` | Innovation Fund（仅 topic 层） | 2021-2025 | 27 | — | 指示 €56.8B |

### 工作簿 schema（四张表，跨文件一致）

* **Topics**（25 列，蓝头）：Framework / Year / **Destination**（统一的领域分析层）/ Call / Topic ID / 标题 / 类型（RIA/IA/CSA）/ TRL / 指示预算 / 开闭日期 / Keywords / **Call Status** / **Award Status** / 已签约项目数与金额
* **Projects**（18 列，绿头）：Topic ID / 项目名 / Grant Agreement ID / Coordinator（+国别）/ 参与方数与参与国 / 起止日期 / EU Contribution / Total Cost / 状态 / 链接 / 摘要
* **Participants**（15 列，橙头）：一行 = 一家机构在一个项目中的参与——角色、国家、城市、机构类型（高校/科研/企业/公共）、SME 标记、**该机构分到的 EC Contribution**
* **Organisations**（12 列，紫头）：机构聚合——参与项目数、coordinator 次数、累计 EC Contribution，按金额降序

### Destination 列的语义（按板块）

CL5 = D1-D6；CL6 = 命名 destination（FARM2FORK 等）；MISS = 任务代码（CLIMA/OCEAN/CIT/SOIL/…）；JU = JU 代码；CL4 = TWIN-TRANSITION 谱系（跨 WP 更名）；H2020 各 SC = topic 编号前缀族（LCE、SFS、MG 等，H2020 无正式 destination 层）；LIFE = 子计划（NAT/ENV/CLIMA/CET）；INNOVFUND = call 类别。

## 数据更新（`pipeline/`）

每个板块三段式：`*_build_topics_from_cordis.py`（CORDIS 过滤 + topic 骨架）→ `*_fetch_details.py`（F&T Portal 详情，带缓存与限速）→ `*_merge_to_excel.py`（合并写 Excel）；再用 `add_participants_sheet.py` / `add_organisations_sheet.py` 补第三、四张表。**xlsx 更新后必跑** `webapp_export_data.py` 刷新网站数据。

例：CORDIS 月度更新后刷新 CL6：

```bash
# 1. 重新下载 cordis-HORIZONprojects-xlsx.zip 解压覆盖 pipeline/raw/cordis_he/
python3 pipeline/scripts/cl6_build_topics_from_cordis.py
python3 pipeline/scripts/cl6_fetch_details.py          # 缓存命中跳过，只拉新 topic
python3 pipeline/scripts/cl6_merge_to_excel.py
python3 pipeline/scripts/add_participants_sheet.py cl6_projects CL6_Topics_and_Projects.xlsx
python3 pipeline/scripts/add_organisations_sheet.py cl6_projects CL6_Topics_and_Projects.xlsx
python3 pipeline/scripts/webapp_export_data.py
```

其他入口：`h2020_build_workbooks.py`（H2020 五工作簿一键构建）；`life_collect_topics.py` / `innovfund_collect_topics.py` + `topics_only_merge.py`（两个 topic 层工作簿）。完整脚本说明见 [WORKLOG.md](./WORKLOG.md)。

依赖：`pandas`、`openpyxl`、系统 `pdftotext`（poppler）；网络请求全部用标准库完成。`pipeline/raw/` 不进 git，首次重跑需按 WORKLOG 下载 CORDIS bulk zip 与工作计划 PDF。

## 口径与已知边界（分析前必读）

* **金额双口径**：`Signed EU Contribution` = CORDIS 已签约实际资助（基本覆盖 2021-2024 签约；2025 起多数 call 未签约）；`Indicative Budget` = 工作计划指示预算。两者不可混加；`Closed + Not yet signed` = call 已截止、评审签约中
* **2027 topic 未纳入**（2026-27 WP 含 2027 题目，按约定收到 2026）
* **LIFE / Innovation Fund 无项目层**：获资项目只在 CINEA Qlik dashboard（无 API、不在 CORDIS）
* **H2020 侧**：topic 级指示预算/日期/TRL/Keywords 未采集（F&T Portal 对 H2020 覆盖不全）；Destination 为前缀族非官方结构
* **零散缺口**：HE 侧 14 个 IBA topic 无详情页；TRL 覆盖 CL5 65%、CL6 32%（数据源固有）；Project Website 覆盖率 ~4%（CORDIS 系统性问题）
* **范围取舍**：CL4 只收工业/材料谱系；JU 只收能源环境五家且仅已签约；CL1/CL2/CL3、ERC/MSCA/EIC 等未采集（可按管道模式随时扩展）

## 数据来源

* [CORDIS bulk datasets](https://cordis.europa.eu/data/)（HE + H2020 项目与参与方，每月更新，CC-BY）
* F&T Portal `topicDetails` JSON 端点与 SEDIA 搜索 API（topic 详情、LIFE/IF 清单）
* Horizon Europe 工作计划 PDF（2025、2026-27，各 cluster 与 Missions）
* 候选扩展（未做）：Kohesio、FTS 财务透明系统、CORDIS FP7（上溯到 2007）、Social Climate Fund
