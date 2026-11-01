# 06 · 交付前验收审计

> 本文件按题目要求逐项核对，所有结论均来自实际运行，不是设计描述。
> 复现命令见文末。

## 1. 六类必验场景

| 场景 | 用例 | 实际状态 | 关键证据 |
| --- | --- | --- | --- |
| 明确答案 | `answer` | `ANSWERED` | 引用 D04-1，回答含 MP4/MOV |
| 文档冲突 | `conflict` | `NEED_CONFIRMATION` | D01=30 天 / D02=15 天 / D03=15 天（scope=差旅），引用三条原文并请求确认 |
| 资料外问题 | `gap` | `INSUFFICIENT_INFO` | 多次检索未命中，明确说明知识库无食堂资料 |
| 改写相似问题 | `paraphrase` | `NEED_CONFIRMATION` | 与 conflict 命中同一组知识，动作一致 |
| 上下文追问 | `followup` | `ANSWERED` | 结合历史，按 D03 的差旅 scope 回答 15 天 |
| 工具失败 | `tool_failure` / `retry_success` | `TOOL_ERROR` / `ANSWERED` | 失败被观察并重试 1 次；持续失败明确报错，不编造 |

补充：`step_limit` 在 `max_steps=1` 下返回 `INCOMPLETE`，并说明卡点。

Mock 与真实模型均为 **8/8**：

- `examples/outputs/_summary.json`
- `examples/outputs_real/_summary.json`

## 2. 参考实例：D01 / D02 冲突

真实模型 `conflict` 输出：

- 状态：`NEED_CONFIRMATION`
- 引用：D01/D01-2、D02/D02-1、D03/D03-2
- 回答列出 30 天、15 天与 D03 的差旅 scope，并请求用户确认
- 没有擅自选择 15 天

真实模型 Trace（`examples/traces_real/conflict.jsonl`）：

```text
search_docs → read_document(D02) → read_document(D01) → read_document(D03) → ask_user
```

满足「列出冲突、引用原文、请求确认、不擅自裁决」。

## 3. 只检索到 D01 且无冲突

用临时知识库（仅保留 D01）验证：

| 文档内容 | 模式 | 结果 |
| --- | --- | --- |
| D01-2 写 30 天 | Mock | `ANSWERED`，引用 D01-2，回答 30 天 |
| D01-2 写 30 天 | 真实模型 | `ANSWERED`，引用 D01-2，回答 30 天 |
| D01-2 改成 45 天 | Mock | `ANSWERED`，回答 45 天 |
| D01-2 改成 45 天 | 真实模型 | `ANSWERED`，回答 45 天 |

对应题目要求「只检索到 D01 且无冲突时可依据 D01 回答」。

## 4. 替换文档内容，核对答案与动作是否改变

在 `.tmp/submission_check/` 下构造临时知识库，不改主数据：

| 改动 | 模式 | 实际结果 | 说明 |
| --- | --- | --- | --- |
| D01=30，D02=30 | Mock | `ANSWERED`，回答 30 天 | 数值一致，不再触发冲突 |
| D01=30，D02=15 | Mock | `NEED_CONFIRMATION` | 数值不一致，动作变为请求确认 |
| D01 仅 30 → 仅 45 | Mock / 真实 | 回答从 30 天变为 45 天 | 答案跟随文档内容 |
| D04 导出格式改成 AVI/MKV | 真实 | `ANSWERED`，回答 AVI/MKV，并说明 MP4 未确认 | 答案跟随文档内容 |

结论：答案与动作由工具返回的文档内容决定，不是硬编码。

## 5. 引用原文支持回答

对所有输出做程序化审计：

- 每个 citation 的 `doc_id` / `section_id` 必须存在；
- `quote` 必须是该分节原文的逐字子串；
- 每个 conflict 项的 `quote` 同样逐字校验；
- `ANSWERED` 必须有非空 `answer` 与 `citations`。

审计范围：`examples/outputs/*.json` 与 `examples/outputs_real/*.json`，共 20 个输出文件。

结果：**0 个问题**。

冲突结果现在也会把逐字原文写入 `citations`（D01/D02/D03），不再只放在 `conflicts` 里。

## 6. Trace 完整性

审计范围：`examples/traces/*.jsonl`、`examples/traces_real/*.jsonl`（共 20 条，排除交互记录）。

每条 Trace 均包含：

- 每步：`step`、`action`（含工具与参数）、`observation`（ok/摘要/数据）、`reason`、`next_action`；
- 末尾：`final` 记录，含 `status`、`citations`、`gaps`、`steps`。

字段缺失数：**0**。

两条不同决策路径可直接对比：

```text
answer:   search_docs → read_document → answer
conflict: search_docs → read_document ×3 → ask_user
gap:      search_docs → search_docs → report_incomplete
failure:  search_docs(失败) → search_docs(重试失败) → report_incomplete
```

## 7. 无依据回答与错误引用

- 20 个知识库外日常问题：**20/20 返回 `INSUFFICIENT_INFO`**，没有拿通用知识硬答（见 `examples/agent_eval_results.json`）。
- 引用逐字校验：覆盖伪造引用、错误文档、引用外数值、中文数字、对比性数值、派生计数等测试（`tests/test_citation.py`）。
- 数值断言只核对带单位的时间/金额/比例/分辨率等；派生计数与明确的假设示例不误杀。
- 更早的一次真实模型运行中曾出现改写引用原文（kb-13），校验器拦截并降级为 `NEED_CONFIRMATION`，没有输出错误引用。

### 7.1 无 Key 离线 Mock

模拟评审环境（不配置对话 Key 与 Embedding Key，`EMBEDDING_PROVIDER=offline`）：

- 启动自动回退 Mock，头部显示 `provider=mock`、`embedding=cached/...`、`retrieval=hybrid`；
- 8 题验收 **8/8**；
- 50 题端到端 **50/50**，日常 20/20，分节引用命中 19/19，检索召回 19/19；
- 结果文件：`examples/agent_eval_results_offline_mock.json`；Trace：`examples/traces_agent_eval_offline/`。

说明：离线模式使用仓库内预计算向量 + 问题样例映射，查询映射失败时回退 BM25；不需要下载模型或调用 API。

## 8. 已知限制

1. 真实模型存在采样波动：50 题严格状态准确率在多次运行中为 **90%–98%**；日常问题始终 20/20。
2. 50 题中有 3 题标注存在歧义（到账时间、字幕指代、适用范围口径），严格口径会低估效果。
3. 引用校验失败后目前直接降级，未让模型重新生成 quote；这是下一步可改进点。
4. Claude 官方端点未实测；当前为 DeepSeek 对话 + 火山方舟嵌入。
5. 已上传至 GitHub：`https://github.com/shiwuing/-agent`；最终 commit SHA 见仓库最新提交。
6. 未配置对话模型 Key 时程序会自动回退 Mock 并打印警告；评审无需 Key 即可运行，但结果只代表流程与护栏。
7. 离线查询映射是近似的：完全没见过的新表达可能映射失败并回退 BM25；知识库变更后需用 `scripts/build_offline_embeddings.py` 重新生成缓存（需 Key）。

## 9. 复现命令

```bash
.venv\Scripts\python -m pytest -q
.venv\Scripts\python -m src.main --all-cases --mock
.venv\Scripts\python -m src.main --all-cases --out-dir examples/outputs_real --trace-dir examples/traces_real
.venv\Scripts\python scripts/eval_retrieval.py
.venv\Scripts\python scripts/eval_agent.py
```
