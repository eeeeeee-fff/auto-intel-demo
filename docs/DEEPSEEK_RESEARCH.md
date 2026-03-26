# DeepSeek 官方能力调研

调研日期：2026-03-17

## 1. 当前对 demo 最有用的能力

基于 DeepSeek 官方文档，这个 demo 首版最应该使用的是：

- OpenAI 兼容接口
- JSON Output

这样可以把集成复杂度压到最低，并把 LLM 输出限定为结构化 JSON，方便落库、复跑和调试。

## 2. 关键结论

### 2.1 OpenAI SDK 兼容

官方文档给出了用 OpenAI SDK 直连 DeepSeek API 的方式，核心做法是：

- `base_url` 指向 `https://api.deepseek.com`
- `api_key` 使用 DeepSeek 的 key

这意味着当前项目不需要单独写一套 DeepSeek HTTP SDK。

参考：

- https://api-docs.deepseek.com/
- https://api-docs.deepseek.com/guides/first_api_call

### 2.2 JSON Output 可直接用于结构化分析

官方文档说明 DeepSeek 支持 JSON Output。对本项目最直接的用途是：

- 重大事件判定
- 事件分类
- 重要度
- 核心摘要
- 去重 key

因此当前代码在 `app/services/llm.py` 里直接使用 JSON 输出模式。

参考：

- https://api-docs.deepseek.com/guides/json_mode

### 2.3 Function Calling 后续可考虑，但首版没必要

官方文档也提供了 Function Calling。它适合把模型和工具调用、外部服务联动起来。但对当前 demo 而言，首版目标只是稳定输出结构化结果，不需要先把复杂度拉到 tool-calling。

建议：

- Phase 1：只用 JSON Output
- Phase 2：如果要做自动复抓、人工审核流、报告分发，再考虑 Function Calling

参考：

- https://api-docs.deepseek.com/guides/function_calling

### 2.4 Thinking Mode 存在，但不是当前最优起点

官方文档显示新版模型支持 thinking mode，并给出了开启方式。文档搜索结果也显示 DeepSeek-V3.2-Exp 支持与 tool calls 配合。不过对于当前 demo，这不是第一优先级，因为：

- 规则已经能先完成第一层过滤
- thinking mode 会增加调试复杂度
- 当前最需要的是稳定、可控、可落库的结构化输出

建议当前先用：

- `deepseek-chat`
- `temperature=0.1`
- JSON Output

等你给出 key 后，再做真实测试和评估。

参考：

- https://api-docs.deepseek.com/guides/reasoning_model
- https://api-docs.deepseek.com/guides/thinking_mode

## 3. 对本项目的接入建议

### 3.1 首版调用方式

统一在后端调用，不在浏览器暴露 key。

### 3.2 首版输出 schema

建议固定为：

```json
{
  "is_major_event": true,
  "category": "supply_chain",
  "importance": 4,
  "core_summary": "......",
  "dedupe_key": "......"
}
```

### 3.3 测试顺序

1. 先用规则引擎跑通 3+2 源站
2. 拿到 DeepSeek key 后，对候选池做结构化输出测试
3. 对比规则结果和模型结果
4. 调整 category 和 importance 的 schema
