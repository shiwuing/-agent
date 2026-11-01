# 01 · 需求说明

> 题目三：企业知识问答 Agent
> 本文说明用户、目标、范围与成功标准，是后续设计与验收的依据。

## 1. 用户与场景

- **主要用户**：需要查询公司制度、流程或产品问题的企业员工。
- **典型场景**：
  - 员工询问「报销期限是多久？」
  - 员工询问「云剪辑支持导出哪些格式？」
  - 员工先问「差旅报销需要哪些材料？」，再追问「那期限呢？」
- **使用方式**：命令行（CLI）输入问题，获得带引用的回答、资料缺口或待确认项。

## 2. 目标

基于带文档 ID 与版本日期的合成 FAQ / 制度知识库，给出：

1. **有引用的回答**：每个结论都能追溯到文档 ID 与原文片段。
2. **可核验的冲突处理**：资料冲突时列出双方、说明缺失的判定依据，并请求用户确认，不擅自裁决。
3. **明确的资料缺口**：知识库无相关资料时直接说明，不编造答案。
4. **可复现的决策过程**：记录每步动作、工具参数、观察摘要与后续动作。

## 3. 范围

### 3.1 包含

- 文档检索（关键词 + 同义词）
- 片段读取（按文档/分节）
- ReAct 决策循环（模型选择动作 → 执行工具 → 观察 → 调整/结束）
- 冲突检测与裁决顺序（适用范围 → 显式优先级 → 文档声明的版本规则）
- 引用逐字校验与数值白名单校验
- 简单上下文追问（合并上一轮用户问题）
- 步数与重试上限
- 离线 Mock 与真实模型两种入口
- CLI 运行、pytest 测试、Trace 落盘

### 3.2 不包含

- 真实企业知识库接入
- 线上部署、账号体系、权限控制
- 多 Agent 协作
- 复杂多轮对话管理（仅保留最近 3 轮上下文）
- 向量检索与重排（数据规模小，关键词方案已足够）
- 真实发布/写入型副作用（本题不需要）

## 4. 成功标准

| # | 标准 | 验证方式 |
| --- | --- | --- |
| S1 | 六类验收场景全部有可运行用例 | `examples/inputs/` + `tests/` |
| S2 | 回答带 `doc_id` + `section_id` + 原文片段，且片段逐字存在 | `tests/test_citation.py` |
| S3 | 冲突时返回 `NEED_CONFIRMATION`，列出冲突项与引用，不擅自选一个 | `examples/outputs/conflict.json` |
| S4 | 资料外问题返回 `INSUFFICIENT_INFO` 并说明缺口 | `examples/outputs/gap.json` |
| S5 | 工具失败被观察、重试一次后明确报错 | `examples/outputs/tool_failure.json` |
| S6 | 达到步数上限返回 `INCOMPLETE` | `examples/outputs/step_limit.json` |
| S7 | 至少两条不同决策路径的 Trace | `examples/traces/answer.jsonl`、`conflict.jsonl` |
| S8 | Mock 模式可离线跑通全流程 | `examples/logs/all_cases.txt` |

## 5. 输入与输出契约

### 5.1 输入

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `question` | 是 | 用户问题 |
| `history` | 否 | 对话历史，`[{role, content}]`，用于上下文追问 |
| 知识库 | 是 | `data/docs.json`，文档含 `doc_id`、`version_date`、可选 `scope`/`priority`、分节内容 |
| 同义词表 | 否 | `data/synonyms.json`，用于查询改写 |

### 5.2 输出

| 字段 | 说明 |
| --- | --- |
| `status` | `ANSWERED` / `NEED_CONFIRMATION` / `INSUFFICIENT_INFO` / `TOOL_ERROR` / `INCOMPLETE` |
| `answer` | 回答正文；请求确认时为确认问题；未完成时为空 |
| `citations` | `[{doc_id, section_id, quote}]` |
| `gaps` | 资料缺口或未完成原因 |
| `conflicts` | 冲突字段、冲突项与取值 |
| `steps` / `tool_calls` | 执行步数与工具调用次数 |
| `trace_file` | 相对路径的 Trace 文件 |
| `provider` / `model` | 运行模式与模型标识 |

### 5.3 状态枚举

| 状态 | 含义 |
| --- | --- |
| `ANSWERED` | 有充分引用，给出明确答案 |
| `NEED_CONFIRMATION` | 资料冲突或引用校验失败，需要用户确认 |
| `INSUFFICIENT_INFO` | 知识库无相关资料 |
| `TOOL_ERROR` | 工具连续失败，无法继续 |
| `INCOMPLETE` | 达到步数上限或模型未完成 |

## 6. 验收场景

| 编号 | 场景 | 输入示例 | 期望状态 |
| --- | --- | --- | --- |
| A1 | 明确答案 | 云剪辑支持导出哪些格式？ | `ANSWERED` |
| A2 | 文档冲突 | 报销期限是多久？ | `NEED_CONFIRMATION` |
| A3 | 资料外问题 | 公司食堂几点开饭？ | `INSUFFICIENT_INFO` |
| A4 | 改写后的相似问题 | 费用报销最晚多久内提交？ | `NEED_CONFIRMATION`（与 A2 同一知识） |
| A5 | 上下文追问 | 历史：差旅报销需要哪些材料？→ 当前：那期限呢？ | `ANSWERED`（D03-2） |
| A6 | 工具失败 | 任意问题 + 注入 `search_docs` 失败 | `TOOL_ERROR` |
| A7 | 步数上限 | 冲突问题 + `max_steps=1` | `INCOMPLETE` |

补充用例：

- **重试成功**：`search_docs` 第一次失败、第二次成功 → `ANSWERED`，验证失败恢复路径。

## 7. 非功能要求

1. **可运行**：`python -m src.main --all-cases --mock` 可离线执行。
2. **可测试**：`pytest -q` 全绿。
3. **可审计**：每次运行生成 JSONL Trace，包含步骤、参数、观察摘要、后续动作与决策依据。
4. **安全**：不提交真实 API Key；`.env` 被忽略，仅保留 `.env.example` 占位符。
5. **可移植**：Linux / Windows 均可运行；运行环境只需 Python 3.10+。
6. **诚实边界**：Mock 只验证流程，不声称代表真实模型效果；真实模型未配置 Key 时提供 Mock 入口并标注边界，真实模型结果按实际运行环境记录。
