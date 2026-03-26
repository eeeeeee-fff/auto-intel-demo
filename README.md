# Auto Intel Demo

面向汽车零部件企业的情报日报系统 demo。每日自动采集 9 个中英文来源，经 AI 分析、翻译后生成结构化早报，展示战略研判、重大事件、持续跟踪和信号摘要。

## 功能概览

- 多源采集（中英文，9 个来源）
- 规则 + AI 双重过滤与重要度评分
- DeepSeek 结构化分析（简体中文输出）
- 非中文资讯 AI 中文翻译
- 今日早报仪表盘（战略研判 / 三件大事 / 持续跟踪 / 信号）
- 情报池（全量文章，支持多维筛选）
- 采集中心（来源管理、运行日志、手动触发）
- 定时调度（每日 05:00 Asia/Shanghai 自动执行）

## 接入来源

| 类型 | 来源 |
|------|------|
| 国内 | 中国汽车报、盖世汽车、新华网汽车 |
| 境外 | IEA、EIA、Just Auto、Autoweek、OICA、MarkLines（index-only）|

---

## 快速启动

### 前置要求

- Python 3.11+
- DeepSeek API Key（[申请地址](https://platform.deepseek.com)）

### 1. 克隆并安装依赖

```bash
git clone <repo-url>
cd auto-intel-demo
pip install -e .[dev]
```

> 推荐使用 conda 隔离环境：
> ```bash
> conda create -n yapu python=3.13
> conda activate yapu
> pip install -e .[dev]
> ```

### 2. 配置环境变量

```bash
cp .env.example .env   # Windows: copy .env.example .env
```

编辑 `.env`，至少填写：

```env
DEEPSEEK_API_KEY=你的密钥
```

其余配置保持默认即可启动。

### 3. 启动服务

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8018
```

或使用脚本：

```bash
python scripts/run_api.py
```

开发时加热重载：

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8018
```

### 4. 首次采集（生成今日早报）

服务启动后，数据库为空，需手动触发一次完整流水线：

```bash
# 方式 A：curl
curl -X POST http://127.0.0.1:8018/v1/pipeline/collect \
  -H "Content-Type: application/json" \
  -d '{"analyze": true, "translate": true, "build_digest": true}'

# 方式 B：直接在采集中心页面点击"立即采集"
```

采集完成后刷新首页即可看到今日早报。

### 5. 访问页面

| 页面 | 地址 | 说明 |
|------|------|------|
| 今日早报 | http://127.0.0.1:8018/ | 仪表盘，战略研判 + 三件大事 |
| 情报池 | http://127.0.0.1:8018/intel | 全量文章，支持筛选和详情查看 |
| 采集中心 | http://127.0.0.1:8018/ops | 来源管理、手动触发、运行日志 |

---

## 主要配置项（.env）

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DEEPSEEK_API_KEY` | — | **必填**，DeepSeek API 密钥 |
| `DEEPSEEK_MODEL` | `deepseek-chat` | 模型名称 |
| `LLM_TIMEOUT_SECONDS` | `120` | LLM API 超时（秒） |
| `COLLECT_LIMIT_PER_SOURCE` | `12` | 每次每源最多采集条数 |
| `SCHEDULER_ENABLED` | `true` | 是否启用定时任务 |
| `SCHEDULER_CRON_HOUR` | `5` | 定时执行小时（Asia/Shanghai） |
| `DATABASE_URL` | `sqlite:///./data/demo.db` | 数据库路径 |

---

## 主要 API

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/health` | 健康检查 |
| `GET` | `/v1/sources` | 来源列表 |
| `POST` | `/v1/pipeline/collect` | 触发采集（含分析/翻译/构建早报） |
| `POST` | `/v1/pipeline/analyze` | 单独触发 AI 分析 |
| `GET` | `/v1/articles` | 文章列表（支持分页/筛选） |
| `GET` | `/v1/articles/{id}` | 文章详情 |
| `POST` | `/v1/articles/{id}/translate` | 单篇翻译 |
| `GET` | `/v1/runs` | 运行历史 |

完整接口文档：启动后访问 http://127.0.0.1:8018/docs

---

## 技术栈

- **后端**：FastAPI + SQLAlchemy + SQLite
- **调度**：APScheduler（内嵌，无需独立 worker）
- **AI**：DeepSeek API（OpenAI 兼容接口）
- **前端**：Jinja2 模板 + 纯 HTML/CSS

## 说明

- `MarkLines` 采用 index-only 模式，只抓标题/摘要/标签，不抓正文详情页
- LLM 分析结果（`core_summary`）强制简体中文输出
- 定时任务默认每日 05:00（Asia/Shanghai）自动执行完整流水线
