# 02 · 方案设计

## 1. 技术选型与取舍

| 项 | 选择 | 理由 |
| --- | --- | --- |
| 语言 | Python 3.10+ | 生态成熟，测试与 Mock 成本低 |
| 模型 | Anthropic 兼容接口；默认 `claude-opus-5-5` | 工具调用与结构化约束稳定；`MODEL_ID` / `ANTHROPIC_BASE_URL` 可覆盖 |
| SDK | 官方 `anthropic` Python SDK | 不手写 HTTP，错误与响应结构清晰 |
| Agent | **原生 ReAct 循环** | 考核明确「框架名称不加分」；原生循环每步可解释、可测试 |
| 检索 | BM25 + 同义词 + FAISS 向量混合（在线或离线预计算） | 无 Key 默认用仓库内离线向量；有 Key 可在线编码 |
| 存储 | JSON | 便于审阅、版本管理和场景替换 |
| 运行 | CLI（argparse） | 命令可复制，最省时 |
| 测试 | pytest | 标准、可执行 |

### 关键取舍

1. **不引入 LangGraph / ADK**：框架会隐藏决策循环，不利于证明「模型根据工具结果调整动作」。原生循环约 100 行，逻辑完全可控。
2. **向量检索分在线/离线两种**：有 Key 时在线编码；无 Key 时加载 `data/offline_embeddings.json`，把查询映射到最接近的问题样例并复用其向量，映射失败则回退 BM25. 两种模式都用 FAISS `IndexFlatIP` + RRF 融合，并用 `EMBEDDING_MIN_SCORE` 过滤噪声。
3. **冲突检测放在代码层**：不把「裁决冲突」暴露成工具，避免模型自行选择一个答案；模型只能读取、检索、请求确认。
4. **引用校验放在代码层**：不依赖模型自觉；回答生成后逐字校验，失败即降级。

## 2. 总体架构

```
CLI (src/main.py)
   │
   ├── 输入解析（question / case / all-cases）
   │
   ▼
AgentLoop (src/agent/loop.py)
   │  状态：问题、历史、观察、已读分节、待处理冲突
   │  上限：MAX_STEPS=8，工具重试 1 次
   │
   ├── LLMClient
   │     ├── AnthropicLLM（真实模型，tool use）
   │     └── MockLLM（离线确定性策略）
   │
   ├── ToolRuntime (src/tools/runtime.py)
   │     ├── search_docs → KnowledgeBase.search
   │     └── read_document → KnowledgeBase.get_section
   │
   ├── 护栏
   │     ├── conflict.detect_conflicts / resolve_conflict
   │     └── citation.validate_citations
   │
   └── TraceWriter → examples/traces/*.jsonl
```

## 3. 知识库设计

`data/docs.json`：

```json
{
  "doc_id": "D01",
  "title": "财务报销管理制度",
  "version_date": "2024-01-01",
  "scope": null,
  "priority": null,
  "sections": [
    {
      "section_id": "D01-2",
      "heading": "报销时限",
      "content": "员工应在费用发生之日起 30 天内提交报销申请。"
    }
  ]
}
```

- `doc_id` / `section_id`：引用与校验主键。
- `version_date`：版本日期，**不等于优先级**。
- `scope`：适用范围（如「差旅」）；为空表示未声明。
- `priority`：显式优先级；仅在知识库明确给出时参与裁决。

示例数据覆盖：冲突（D01 30 天 vs D02 15 天）、范围裁决（D03 差旅 15 天）、明确答案（D04 导出格式）、资料外问题（食堂）。

## 4. 工具接口

```python
search_docs(query: str, top_k: int = 8) -> ToolResult
read_document(doc_id: str, section_id: str | None = None) -> ToolResult
```

`ToolResult = {ok, data, error, summary}`：

- 工具失败**不抛异常穿透给模型**，返回 `ok=false` + `error` + `summary`，让模型观察到失败后决策。
- `summary` 是给模型/ Trace 看的一句话，如「命中 7 个片段；检测到字段“报销期限”存在不一致」。
- 故障注入：`ToolRuntime(fail_tool=..., fail_times=...)`，用于测试工具失败与重试路径。

## 5. ReAct 决策循环

```text
state = init(question, history)
for step in 1..MAX_STEPS:
    action = llm.decide(state)         # 模型选择动作
    if action is terminal: break       # answer / ask_user / report_incomplete
    result = runtime.call(action)      # 执行工具
    state.observe(action, result)      # 观察
    trace.log(step, action, result)    # 记录
if not terminal:
    status = INCOMPLETE
```

模型可选动作：

| 动作 | 含义 |
| --- | --- |
| `search_docs` | 检索文档片段 |
| `read_document` | 读取指定文档/分节原文 |
| `final_answer` | 给出回答（必须带 citations） |
| `ask_user` | 请求确认或补充信息 |
| `report_incomplete` | 报告无法完成及原因 |

**关键点**：每次 `decide` 都读取 `state.observations`；下一动作由工具结果决定，而非预设顺序。

## 6. 六类场景的处理策略

| 场景 | 观察信号 | 决策 |
| --- | --- | --- |
| 明确答案 | 命中单一高相关片段 | 读取原文 → 引用回答 |
| 文档冲突 | 检索提示同字段不同值 | 依次读取冲突文档 → 无法裁决则请求确认 |
| 资料外问题 | 多轮改写仍无命中 | 返回 `INSUFFICIENT_INFO` + 缺口 |
| 改写问题 | 同义词扩展后命中同一知识 | 与正常路径一致 |
| 上下文追问 | 问题含指代/过短 | 合并上一轮用户问题后检索 |
| 工具失败 | `ok=false` | 重试 1 次 → 仍失败则 `TOOL_ERROR` |
| 步数上限 | 循环达到 `MAX_STEPS` | `INCOMPLETE` + 卡点说明 |

## 7. 冲突检测与裁决

### 7.1 检测

1. 按字段规则匹配分节（当前覆盖「报销期限」「年假天数」「导出格式」）。
2. 从分节原文抽取数值 + 单位（如 `30 天`、`15 天`）。
3. 同一字段出现不同数值 → 冲突。

### 7.2 裁决顺序

1. **适用范围匹配**：文档声明 `scope` 且问题可归入该范围 → 使用该文档。
2. **显式优先级**：知识库声明 `priority` → 取最高优先级且值唯一者。
3. **文档声明的版本规则**：仅当原文明确写「以最新版本为准」才按版本日期裁决。
4. **无法裁决** → `NEED_CONFIRMATION`，列出冲突项、引用原文、说明缺失依据，请用户确认。

**版本日期本身不参与裁决**：D02（2025-06-01，15 天）比 D01（2024-01-01，30 天）新，但泛问「报销期限」时仍必须请求确认，而不是默认 15 天。

### 7.3 示例

- 「报销期限是多久？」→ D01=30 天、D02=15 天、D03=15 天（scope=差旅，但问题未限定差旅）→ 无法裁决 → `NEED_CONFIRMATION`。
- 「差旅报销期限是多久？」→ D03 的 scope 命中 → 采用 D03-2 的 15 天 → `ANSWERED`。

## 8. 引用与防幻觉校验

回答生成后由 `citation.validate_citations` 执行：

1. `doc_id` 与 `section_id` 必须存在。
2. `quote` 必须是分节原文的逐字子串（去空白后比较）。
3. 回答中的数值必须出现在引用原文中（先剔除 `D01`、`D03-2` 等 ID）。
4. 无引用或任一校验失败 → 不返回该答案，降级为 `NEED_CONFIRMATION`。

## 9. 上下文与查询改写

- 保留最近 3 轮历史；问题 ≤12 字或含「那 / 它 / 这个 / 该」等指代时，把上一轮用户问题与当前问题合并。
- 无命中时改写查询：去掉疑问/口语词（请问、什么、多久、呢、吗等），第二轮追加同义词。
- 最多 3 次检索（首轮 + 2 次改写）；仍无命中则说明资料缺口。

## 10. 限额与未完成

- `MAX_STEPS = 8`：达到上限时返回 `INCOMPLETE`，输出已执行步骤与卡点。
- 工具失败重试 1 次；仍失败返回 `TOOL_ERROR`。
- 未完成时不输出看似完整的答案。

## 11. 模型接入

- **默认模型**：`claude-opus-5-5`（环境变量 `MODEL_ID` 可覆盖）。
- **SDK**：官方 `anthropic` Python SDK。
- **推理参数**：`thinking={"type": "adaptive"}`，`max_tokens=2048`，不设置 `temperature`。
- **工具调用**：每次 `decide` 调用一次 Messages API，使用 `tools` + `tool_choice={"type": "auto"}`，解析第一个 `tool_use` 块。
- **错误处理**：捕获 SDK 异常、检查 `stop_reason == "refusal"`，统一转为 `TOOL_ERROR` 或 `INCOMPLETE`，不编造结果。
- **运行条件**：真实模式需要 `ANTHROPIC_API_KEY`；`ANTHROPIC_BASE_URL` 可指向兼容端点，`MODEL_ID` 指定模型名。Mock 阶段未配置 Key；收尾阶段已通过 DeepSeek 兼容端点（`deepseek-v4-flash`）实际运行，Claude 官方端点未实测，详见 `docs/03-evaluation.md`。

## 12. Mock 模式

- `MockLLM.decide(state)` 读取 `state.observations`，根据检索命中、冲突提示、工具失败等信号选择下一步。
- 典型路径：
  - 正常：`search → read → answer`
  - 冲突：`search → read D01 → read D02 → read D03 → ask`
  - 缺口：`search → rewrite → search → rewrite → search → report`
  - 失败：`search(fail) → search(retry, fail) → report`
- **边界**：Mock 是确定性策略，只验证流程、状态机与护栏；不证明真实模型的检索改写、冲突判断或回答质量。

## 13. Trace 格式

`examples/traces/<case>.jsonl` 每行一个步骤：

```json
{
  "step": 1,
  "action": {"type": "tool", "tool": "search_docs", "args": {"query": "报销期限是多久？", "top_k": 8}},
  "observation": {"ok": true, "summary": "命中 7 个片段；检测到字段“报销期限”存在不一致"},
  "reason": "首轮检索",
  "next_action": "read_document"
}
```

末行为 `{"type": "final", ...}`，包含状态、回答、引用、缺口、冲突与步数。

## 14. 已知限制

1. 关键词检索依赖人工维护的同义词表；对完全不同的表达可能漏检。
2. 冲突字段规则当前为硬编码（报销期限、年假、导出格式）；新增业务字段需要扩展 `FIELD_RULES`。
3. 数值校验较严格：回答中出现引用外的数字会被拒绝，可能误杀合理的派生计算。
4. 上下文仅支持简单指代合并，不支持复杂多轮指代消解。
5. 真实模型模式未在本环境执行，Mock 结果不能替代真实模型评估。
6. 未做性能、并发与成本优化；单次运行同步执行。
