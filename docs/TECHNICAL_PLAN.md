# Auto Intel Demo 技术方案

## 1. 目标

这个 demo 的目标不是做通用新闻聚合，而是做一条可控的汽车产业情报流水线，围绕：

- 多源日采集
- 重大事件过滤
- 结构化分析
- 非中文资讯 AI 中文译文
- 预览台
- HTML 日报

当前跑通的来源：

- 中国汽车报
- 盖世汽车
- 新华网汽车
- IEA
- EIA
- Just Auto
- Autoweek
- OICA
- MarkLines `index-only`

## 2. 架构选择

当前采用：

- `FastAPI` 作为统一控制面
- `APScheduler` 作为内置定时调度器
- `SQLAlchemy + SQLite` 作为 demo 数据存储
- `DeepSeek` 作为结构化分析模型

不采用独立 Celery worker 的原因：

- 首版更需要统一控制和统一状态，而不是拆成多套进程
- 站点适配与规则调优比高并发更关键
- 本地调试、手动触发、运行记录和预览页面需要放在同一后端内

## 3. 模块划分

### 3.1 采集层

- `app/collectors/base.py`
- `app/collectors/sources.py`

当前 source adapter：

- `ChinaAutoNewsCollector`
- `GasgooCollector`
- `XinhuaAutoCollector`
- `IEANewsCollector`
- `EIARssCollector`
- `JustAutoCollector`
- `AutoweekCollector`
- `OICANewsCollector`
- `MarkLinesCollector`

接入策略：

- `RSS + HTML`：盖世汽车、EIA、Autoweek
- `HTML 列表页 + 文章页`：中国汽车报、新华网汽车、IEA、Just Auto、OICA
- `Index-only`：MarkLines，只取列表页可见字段，不抓详情页正文

### 3.2 规则过滤层

- `app/services/rules.py`

规则层负责：

- 时间窗过滤
- 噪音稿过滤
- 事件类别初判
- 重要度打分
- 去重 key 归一化

并补充了 source-specific 规则：

- `autoweek` 过滤试驾、评测、消费向内容
- `just_auto` 过滤 webinar / podcast 噪音
- `oica` 支持摘要型页面的保底识别

### 3.3 LLM 分析层

- `app/services/llm.py`

当前策略：

- 使用 DeepSeek OpenAI-compatible API
- 输出格式为 `json_object`
- 固定枚举类别：
  - `policy_regulation`
  - `strategic_cooperation`
  - `technology_breakthrough`
  - `sales_data`
  - `supply_chain`
  - `executive_change`
  - `macro_policy`
  - `geopolitics`
  - `commodities_fx`
  - `incident`

额外策略：

- `MarkLines` 输入会显式标识 `index_only`
- `IEA / EIA / OICA` 会带 source profile，降低摘要类误判
- 非中文文章支持按需生成中文译文，并保留 PHEV、EREV、OEM、ADAS、LFP 等专业术语

### 3.4 预览与日报层

- `app/services/reporting.py`
- `app/templates/preview/index.html`
- `app/templates/reports/daily.html`

当前能力：

- 重大事件去重
- 来源覆盖统计
- 境外来源保留策略
- 最新运行明细
- 事件详情抽屉
- 一键刷新
- HTML 日报渲染

## 4. 数据模型

### 4.1 `source_configs`

记录来源配置、调度频率、是否启用、最近运行状态。

### 4.2 `articles`

记录统一后的文章实体：

- 标题
- 来源
- 链接
- 发布时间
- 正文或 teaser
- `content_access`：`full_text` / `index_only`
- 规则层结果
- LLM 结果
- 去重 key

### 4.3 `pipeline_runs`

记录每次采集/分析运行结果。

### 4.4 `source_run_logs`

记录“每次运行 / 每个来源”的明细：

- 状态
- 耗时
- 采集量
- 候选量
- 分析量
- 错误信息

### 4.5 `daily_reports`

记录按日期生成的 HTML 日报。

## 5. 接口

- `GET /health`
- `GET /v1/sources`
- `PATCH /v1/sources/{source_key}`
- `POST /v1/pipeline/collect`
- `POST /v1/pipeline/analyze`
- `GET /v1/articles`
- `GET /v1/articles/{article_id}`
- `GET /v1/runs`
- `GET /v1/runs/{run_id}`
- `POST /v1/reports/daily`
- `GET /preview`

默认端口：`8018`

## 6. 运行流程

1. 从列表页或 RSS 获取文章 URL
2. 进入文章页提取正文、标题、发布时间
3. `MarkLines` 仅抓 index 可见内容，不请求详情页
4. 入库并执行规则过滤
5. 调用 DeepSeek 做结构化判断
6. 生成重大事件池、来源覆盖和运行明细
7. 渲染 HTML 日报

## 7. 下一阶段建议

1. 增加人工审核写操作
2. 增加更细的运行日志和失败重试
3. 将 SQLite 平滑切换到 PostgreSQL
4. 接入更多高价值国际源
