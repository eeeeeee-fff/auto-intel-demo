# Auto Intel Demo 重构实施蓝图

## 1. 目标与结论

本次重构的目标不是把现有单页预览继续堆功能，而是把产品收敛成 3 个职责明确的页面：

1. 首页：`今日战情`
2. 数据页：`情报池`
3. 采集中心：`任务与来源`

核心产品口径同步调整为：

- 首页只看今天，按 `Asia/Shanghai` 自然日统计。
- 首页是一屏战情摘要，不是长日报。
- 所有非中文文章默认自动翻译为中文后再展示。
- 页面默认显示中文；详情中提供 `查看原文`。
- 所有外文内容必须明确标注 `原文非中文`。
- 采集中心必须绑定真实脚本与真实任务记录，不能只做动画。

## 2. 当前基线

### 2.1 当前已有能力

- 后端框架：`FastAPI`
- 数据库：`SQLite`
- 定时能力：`APScheduler`
- 已接入来源：9 个
- 已有页面：
  - `/preview`
  - `/preview/report/{report_id}`
- 已有数据：
  - 原文抓取数据
  - AI 重大事件判定
  - AI 中文翻译
  - run / source_run_logs 运行记录

### 2.2 当前已有脚本

项目根目录下的 [scripts/run_api.py](/C:/work/yapu/auto-intel-demo/scripts/run_api.py) 和 [scripts/demo_collect.py](/C:/work/yapu/auto-intel-demo/scripts/demo_collect.py) 已存在。

现状问题不在“完全没有脚本”，而在“脚本体系不够支撑采集中心”：

- `run_api.py` 只负责启动服务
- `demo_collect.py` 偏演示，不够细分
- 缺少单源采集、今日摘要生成、独立调度启动、批量翻译补跑等正式脚本

## 3. 目标信息架构

### 3.1 首页：今日战情

定位：一屏内让客户看懂“今天汽车行业发生了什么”。

首页只展示“结论层”，不展示长文，不展示全量明细。

#### 首页模块

1. 顶部状态栏
- 今日日期
- 最近更新时间
- 今日采集数
- 今日候选数
- 今日重大事件数
- 今日来源数
- 境内/境外来源占比

2. 今日判断主卡
- 基于客户提示词生成 1 段中文判断
- 长度控制在 120 到 180 字
- 内容结构建议：
  - 今日主线
  - 最重要变化
  - 对 OEM / 供应链 / 新能源的含义

3. 头部事件区
- 展示 3 到 5 条
- 每条字段：
  - 中文标题
  - 来源
  - 发布时间
  - 事件分类
  - 重要度
  - 一句话摘要
  - `原文非中文` 标识

4. 风险与机会
- 风险信号 2 到 3 条
- 机会信号 2 到 3 条
- 用短句，不写成长段

5. 系统状态条
- 今日任务轮次
- 成功源数
- 失败源数
- 运行中源数

#### 首页一屏约束

- 不使用长表格
- 不展示超过 5 条事件
- 不出现滚动式长日报
- 主信息全部在首屏完成

#### 首页布局建议

上半屏：

- 左：今日判断主卡
- 右：6 个关键数字卡

下半屏：

- 左：头部事件 3 条
- 中：风险 / 机会
- 右：系统状态与来源覆盖

### 3.2 数据页：情报池

定位：提供完整数据查看、筛选、追溯和原文对照。

#### 数据页模块

1. 筛选区
- 日期
- 来源
- 类别
- 仅候选
- 仅重大事件
- 中文来源 / 外文来源
- `full_text` / `index_only`

2. 列表区
- 默认展示中文标题和中文摘要
- 外文来源默认显示译文，不直接显示英文
- 每条文章显示：
  - 标题
  - 来源
  - 发布时间
  - 类别
  - 重要度
  - 语言标识
  - `原文非中文`

3. 详情抽屉
- 默认 tab：`中文译文`
- 次级 tab：`查看原文`
- 展示内容：
  - 中文标题 / 原文标题
  - 中文摘要 / 原文摘要
  - 分类
  - 重要度
  - 是否进入首页
  - 是否进入今日摘要
  - 来源链接
  - 标签
  - `Index-only` 标识

### 3.3 采集中心：任务与来源

定位：展示系统真的在跑，且能定位问题。

#### 采集中心模块

1. 来源总览
- 每个来源一张卡片
- 字段：
  - 来源名
  - 国家/语言
  - 抓取方式
  - 调度频率
  - 最近运行时间
  - 当前状态

2. 今日任务时间线
- 今日跑了几轮
- 每轮任务开始时间、结束时间、状态
- 每轮总抓取数、候选数、分析数、翻译数

3. Source 级运行明细
- 每个来源本轮：
  - 抓取数
  - 候选数
  - 分析数
  - 翻译数
  - 耗时
  - 错误信息

4. 动态状态展示
- `running` 状态的来源卡片有脉冲或流动动画
- `success` 静态高亮
- `failed` 明确告警色

说明：动态效果只能附着真实状态，不单独做“装饰动画页”。

## 4. 页面之间的关系

- 首页看结论
- 数据页看证据
- 采集中心看可信度

页面跳转关系建议：

- 首页头部事件 -> 数据页详情定位
- 首页系统状态条 -> 采集中心
- 数据页详情 -> 原文外链
- 采集中心失败来源 -> 数据页按来源筛选

## 5. 时间与统计口径

### 5.1 时间口径

全部页面默认按 `Asia/Shanghai` 统计“今天”：

- 起点：`00:00:00`
- 终点：`23:59:59`

不再沿用当前近 72 小时的首页/日报展示逻辑。

### 5.2 首页统计口径

首页所有数字只取“今天”的数据：

- 今日采集数：今天抓到并入库的文章数
- 今日候选数：今天被规则或模型识别为候选的文章数
- 今日重大事件数：今天进入重大事件的文章数
- 今日来源数：今天有数据的来源数
- 境内外占比：今天重大事件按来源归属划分

## 6. 翻译策略

### 6.1 展示规则

- 默认展示中文
- 外文内容统一显示 `原文非中文`
- 详情里提供 `查看原文`
- 原文永久保留，不被译文覆盖

### 6.2 翻译时机

翻译不再以“按钮临时触发”为主，而应进入正式流水线：

1. 文章采集入库
2. 规则筛选
3. AI 重大事件分析
4. 外文自动翻译
5. 生成今日首页摘要

### 6.3 术语保留原则

以下术语默认保留原文：

- `PHEV`
- `EREV`
- `BEV`
- `OEM`
- `ADAS`
- `LFP`
- `BMS`
- `Tier 1`
- `Tier 2`
- `SiC`
- `IGBT`

页面展示时，译文标题/摘要保留这些术语的英文写法，不做生硬中文化。

## 7. 脚本体系改造

## 7.1 目标

让采集中心展示基于真实脚本运行，而不是只靠 API 页面手动触发。

### 7.2 现有脚本

- [scripts/run_api.py](/C:/work/yapu/auto-intel-demo/scripts/run_api.py)
- [scripts/demo_collect.py](/C:/work/yapu/auto-intel-demo/scripts/demo_collect.py)

### 7.3 新增脚本建议

1. `scripts/collect_once.py`
- 全量采集一次
- 自动分析
- 自动翻译外文
- 更新今日首页摘要

2. `scripts/collect_source.py`
- 指定单源采集
- 支持快速调试与失败重试
- 可用于采集中心“重跑单源”

3. `scripts/build_today_digest.py`
- 只基于今天的数据重建首页摘要
- 不重复采集

4. `scripts/run_scheduler.py`
- 独立运行调度器
- 与 API 进程解耦

5. `scripts/backfill_translate.py`
- 对已有外文历史数据补翻译
- 支持 limit 和 source_key

### 7.4 脚本职责分工

- API 负责展示与查询
- 脚本负责执行与更新
- 采集中心读取真实脚本执行结果

## 8. API 改造蓝图

### 8.1 首页接口

新增：

- `GET /v1/dashboard/today`

返回建议字段：

- `date`
- `updated_at`
- `today_totals`
- `top_events`
- `risk_signals`
- `opportunity_signals`
- `today_judgement`
- `source_distribution`
- `run_status`

### 8.2 数据页接口

保留并增强：

- `GET /v1/articles`
- `GET /v1/articles/{article_id}`

新增建议字段：

- `display_title`
- `display_summary`
- `original_language`
- `is_foreign_original`
- `included_in_today_digest`

### 8.3 采集中心接口

新增：

- `GET /v1/runs/today`
- `GET /v1/sources/status`
- `GET /v1/sources/{source_key}/runs`

可选新增：

- `POST /v1/pipeline/run-today`
- `POST /v1/pipeline/run-source/{source_key}`

### 8.4 翻译状态接口

如果仍保留单篇重译能力：

- `POST /v1/articles/{article_id}/translate?force=true`

但产品默认逻辑不依赖这个入口，应该由流水线自动完成。

## 9. 数据结构改造蓝图

### 9.1 新增表建议

1. `today_digests`
- `id`
- `digest_date`
- `timezone`
- `summary_payload`
- `generated_at`
- `run_id`

用途：存首页一屏摘要结果。

2. `run_stage_logs`
- `id`
- `run_id`
- `stage_name`
- `status`
- `started_at`
- `finished_at`
- `processed_count`
- `error_message`

用途：把一次任务拆成采集、分析、翻译、摘要四段。

### 9.2 现有表扩展建议

`source_run_logs` 增加：

- `translated_count`
- `stage_status_json`

`articles` 增加：

- `included_in_today_digest`
- `digest_rank`

说明：已有翻译字段可以继续复用，不需要推翻。

## 10. 后端服务改造点

### 10.1 首页摘要生成服务

新增服务建议：

- `app/services/dashboard.py`

职责：

- 读取今天的数据
- 聚合今日指标
- 计算头部事件
- 基于客户提示词生成“今日判断 / 风险 / 机会”
- 回写 `today_digests`

### 10.2 时间窗口统一

新增公共时间工具建议：

- `app/services/time_windows.py`

职责：

- 统一处理 `Asia/Shanghai` 的 today window
- 避免首页、数据页、采集中心各自算日期

### 10.3 流水线拆段

当前 `run_collection_pipeline` 应拆成明确阶段：

1. collect
2. analyze
3. translate
4. build_digest

每段都写入 stage log，供采集中心读取。

## 11. 前端改造蓝图

### 11.1 路由建议

- `/` -> 今日战情
- `/intel` -> 情报池
- `/ops` -> 采集中心

旧的 `/preview` 可保留为兼容入口，后续重定向到 `/intel` 或直接废弃。

### 11.2 视觉方向

建议风格：中文商业情报驾驶舱，不做泛科技风大屏。

设计原则：

- 中文优先排版
- 强信息密度，但避免数据墙
- 首页大字结论 + 小卡片证据
- 外文事件统一中文化展示
- 用颜色区分：
  - 战略 / 政策 / 技术 / 销量 / 供应链

### 11.3 首页交互

- 点击头部事件 -> 打开数据页该事件详情
- 点击系统状态 -> 跳到采集中心
- 首页不出现复杂筛选

### 11.4 数据页交互

- 左侧筛选，右侧列表
- 点击文章打开抽屉
- 抽屉内切换：
  - `中文译文`
  - `查看原文`

### 11.5 采集中心交互

- 来源卡可点击
- 点击来源显示最近几次运行
- 失败来源高亮并展示错误信息

## 12. 实施顺序

### Phase 1：口径与脚本

目标：先把“今天”和“真实任务”定住。

任务：

- 新增 today window 统一工具
- 新增 `collect_once.py`
- 新增 `collect_source.py`
- 新增 `build_today_digest.py`
- 新增 `run_scheduler.py`
- 新增 `backfill_translate.py`
- 补 run stage logs

产出：

- 采集中心有真实任务支撑
- 首页开始按“今天”算

### Phase 2：首页

目标：先做一屏今日战情。

任务：

- 新增 dashboard 服务
- 新增 `GET /v1/dashboard/today`
- 重构首页模板
- 接入今日判断 / 风险 / 机会

产出：

- 首页可独立演示

### Phase 3：数据页

目标：把现有 preview 拆成正式情报池。

任务：

- 改造 `/preview` 为 `/intel`
- 增强筛选与详情抽屉
- 默认显示中文译文
- 增加 `查看原文`

产出：

- 全量数据可追溯

### Phase 4：采集中心

目标：把任务和来源状态做成可信控制台。

任务：

- 新增来源状态接口
- 新增今日任务时间线
- 增加动态状态展示
- 接 source_run_logs / run_stage_logs

产出：

- 客户可直接看到系统在真实运行

## 13. 验收标准

### 首页验收

- 进入首页后不滚动即可看到完整摘要
- 首页只显示今天的数据
- 首页外文事件默认显示中文
- 每条外文事件都标注 `原文非中文`

### 数据页验收

- 所有文章默认显示中文标题与摘要
- 可切换查看原文
- 可以按来源、类别、重大事件、语言筛选

### 采集中心验收

- 每个来源都有真实运行状态
- 可以看到今天的任务时间线
- 失败来源能看到错误信息
- 动态效果与真实状态一致

### 脚本验收

- 能跑一次全量采集
- 能跑单源采集
- 能重建今日摘要
- 能独立启动调度
- 能对历史外文文章补翻译

## 14. 第一批落地文件建议

建议优先改这些文件：

- `app/services/ingestion.py`
- `app/services/reporting.py`
- `app/services/translation.py`
- `app/api.py`
- `app/models.py`
- `app/schemas.py`
- `app/templates/preview/index.html`
- `app/templates/reports/daily.html`
- `scripts/demo_collect.py`

建议新增这些文件：

- `app/services/dashboard.py`
- `app/services/time_windows.py`
- `scripts/collect_once.py`
- `scripts/collect_source.py`
- `scripts/build_today_digest.py`
- `scripts/run_scheduler.py`
- `scripts/backfill_translate.py`

## 15. 本方案的核心判断

这次重构最重要的不是“从单页改成三页”，而是把产品逻辑彻底切开：

- 首页负责判断
- 数据页负责证据
- 采集中心负责可信度

如果不这样切，首页会变成详情页，数据页会变成重复页，采集中心会变成装饰页。

本蓝图的目标就是避免这三种退化。
