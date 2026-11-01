# 提交说明：仓库里每个文件/文件夹具体是什么

> 小影科技 2027 校招 · AI Agent 笔试题 **题目三：企业知识问答 Agent**
>
> 验收默认 Mock + 离线向量，不需要任何 API Key。

## 快速验收

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m src.main --all-cases --mock
.venv\Scripts\python -m src.main --interactive --mock
```

## 两种运行模式

| 模式 | 对话模型 | Embedding | 需要什么 |
| --- | --- | --- | --- |
| **离线 Mock（默认）** | `MockLLM` 确定性策略 | 仓库内 `data/offline_embeddings.json` + BM25 | **不需要任何 Key** |
| **API 模式** | 真实 Claude 或兼容端点 | 在线 Embedding（火山方舟 / OpenAI / Voyage） | **评审自备** `ANTHROPIC_API_KEY` + `EMBEDDING_API_KEY` |

> 仓库不包含、也不会长期提供作者的 API Key。评审如需 API 模式，请使用自己的账号和 Key；只做验收请直接使用离线 Mock。
>
> API 模式也可以只配对话 Key；Embedding 不配置时自动使用仓库内离线向量。

## 根目录

| 路径 | 具体内容 |
| --- | --- |
| `README.md` | 题目拆解、硬契约表、实现方案、六类验收矩阵、51 项测试结果、50 题评测结果、无 Key 运行命令与提交信息 |
| `SUBMISSION.md` | 本文件：逐文件说明仓库里实际存放了什么 |
| `requirements.txt` | 5 个依赖：`anthropic>=0.40.0`、`python-dotenv>=1.0.0`、`pytest>=8.0.0`、`numpy>=1.24.0`、`faiss-cpu>=1.8.0` |
| `.env.example` | 真实模型/在线 Embedding 的可选变量模板；默认 `EMBEDDING_PROVIDER=offline`，不含真实 Key |
| `.gitignore` | 排除 `.env`、`.venv/`、`__pycache__/`、`.pytest_cache/`、`.idea/`、`_ops/`、`data/.embedding_cache.json`、`.tmp/`、`.cache/` |

## `src/`：Python 源码

| 路径 | 具体内容 |
| --- | --- |
| `src/main.py` | CLI 入口：`--interactive`（Q/A 交互）、`--question`、`--case`、`--all-cases`、`--data-dir`、`--out-dir/--trace-dir`、`--mock`、`--keyword-only`、`--max-steps`、故障注入参数；无对话 Key 时自动回退 Mock |
| `src/models.py` | `Action`、`Observation`、`AgentState`、`ToolResult` 四个 dataclass；`ANSWERED` / `NEED_CONFIRMATION` / `INSUFFICIENT_INFO` / `TOOL_ERROR` / `INCOMPLETE` 状态常量 |
| `src/kb.py` | 加载 `data/docs.json` 和 `data/synonyms.json`；BM25 打分；同义词扩展；查询改写（交上去→提交、批下来→审批等）；关键词/向量 RRF 融合；领域词与查询覆盖率门槛 |
| `src/embeddings.py` | 三个在线 embedder（OpenAI 兼容、Voyage、火山方舟多模态）＋ `CachedEmbedder`；后者读取离线向量，用字符相似度把新查询映射到最近的问题样例 |
| `src/vector_store.py` | `VectorIndex`：FAISS `IndexFlatIP` 余弦检索；缓存 fingerprint 校验；未安装 faiss 时回退 numpy；`EMBEDDING_MIN_SCORE` 过滤低分向量 |
| `src/conflict.py` | 检测「报销期限」「年假天数」「导出格式」三个字段的数值冲突；按显式文档、`scope`、`priority`、声明版本规则裁决 |
| `src/citation.py` | 校验 citation 的 doc_id/section_id 存在、quote 逐字出现在原文；数值白名单；中文数字、派生计数、假设示例、编号列表处理 |
| `src/trace.py` | `TraceWriter`：每步写 step/action/observation/reason/next_action，末尾写 final 记录 |

## `src/agent/`：Agent 决策

| 路径 | 具体内容 |
| --- | --- |
| `src/agent/loop.py` | ReAct 主循环：模型动作 → 工具执行 → 观察 → 下一步；步数上限；回答前引用校验；冲突 quote 同步进 citations |
| `src/agent/llm.py` | Anthropic 兼容客户端；5 个工具 schema（search_docs、read_document、final_answer、ask_user、report_incomplete）；解析 tool_use |
| `src/agent/mock_llm.py` | 离线确定性策略：按 observations 决定检索/读取/回答/追问/报错；重试 1 次；冲突读取与裁决；4K/例外场景过滤 |
| `src/agent/context.py` | 追问识别；从历史提取主题词（差旅、报销、年假等）；查询改写与停用词处理 |
| `src/agent/prompts.py` | 系统提示词 8 条：引用、冲突裁决顺序、缺口、工具失败、状态口径、先读原文再确认 |

## `src/tools/`：业务工具

| 路径 | 具体内容 |
| --- | --- |
| `src/tools/search.py` | `search_docs(query, top_k)`：调用 `kb.search`，附加冲突提示和检索模式 |
| `src/tools/read.py` | `read_document(doc_id, section_id)`：返回指定分节完整原文 |
| `src/tools/runtime.py` | `ToolRuntime`：执行工具；支持 `fail_tool` / `fail_times` 故障注入 |

## `data/`：知识库与离线向量

| 路径 | 具体内容 |
| --- | --- |
| `data/docs.json` | 5 篇合成文档、11 个分节：D01 财务报销管理制度（30 天时限）、D02 费用报销常见问题（15 天、审批 5 个工作日）、D03 差旅报销说明（scope=差旅、材料清单、15 天）、D04 云剪辑产品 FAQ（MP4/MOV、字幕）、D05 员工手册（5 天年假、跨年规则） |
| `data/synonyms.json` | 6 组同义词：报销期限、差旅、导出格式、年假、材料、跨年；例如「垫付/拿回/到账」归入报销期限，「输出」归入导出格式 |
| `data/offline_embeddings.json` | 42 条 2048 维向量：11 个分节正文 + 31 条问题样例；模型 `doubao-embedding-vision-251215`；无 Key 时 `CachedEmbedder` 使用 |

## `tests/`：51 项可执行测试

| 路径 | 具体内容 |
| --- | --- |
| `tests/conftest.py` | 会话级 `kb` fixture，加载主知识库 |
| `tests/helpers.py` | `run_question`：用 MockLLM + ToolRuntime 跑单题 |
| `tests/fake_embedder.py` | `ConceptEmbedder`：按概念映射的 5 维确定性测试向量 |
| `tests/test_acceptance.py` | 8 个端到端场景：明确答案、冲突、资料外、改写、追问、工具失败、重试成功、步数上限；另含例外场景 |
| `tests/test_conflict.py` | 冲突检测；scope 裁决；显式 D01 裁决；版本日期不单独裁决；年假问题不被期限冲突劫持 |
| `tests/test_citation.py` | 引用逐字匹配、错误文档、数值白名单、中文数字、派生计数、假设示例、编号列表 |
| `tests/test_context.py` | 追问主题提取；短问题不误合并 |
| `tests/test_limits.py` | 步数上限返回 `INCOMPLETE` |
| `tests/test_mock_loop.py` | 两条路径动作不同、Trace 字段、观察驱动决策 |
| `tests/test_tool_failure.py` | 失败重试 1 次、连续失败返回 `TOOL_ERROR` |
| `tests/test_vector_store.py` | FAISS/numpy 后端、查询改写召回、缓存复用、embedding 失败回退 |
| `tests/test_cached_embedder.py` | 离线向量精确命中、问题样例映射、库外问题不映射、无 Key 默认模式 |
| `tests/test_semantic_api.py` | 真实 Embedding API 连通性；pytest 不加载 `.env` 时跳过 |

## `scripts/`：评测与离线向量生成

| 路径 | 具体内容 |
| --- | --- |
| `scripts/eval_retrieval.py` | 跑 20 条检索查询，对比关键词/混合检索的 Recall@5 与 MRR |
| `scripts/eval_agent.py` | 跑 `examples/agent_eval.json` 的 50 题；支持 `--category`、`--ids`、`--limit`、`--trace-dir`、`--output` |
| `scripts/build_offline_embeddings.py` | 用真实 Embedding 服务重新计算向量，写入 `data/offline_embeddings.json` |

## `examples/`：输入、输出、Trace 与评测

| 路径 | 具体内容 |
| --- | --- |
| `examples/inputs/` | 8 个用例：`answer`、`conflict`、`gap`、`paraphrase`、`followup`、`retry_success`、`step_limit`、`tool_failure` |
| `examples/outputs/` | Mock 的 8 个用例输出 + `_summary.json`，另有 `confirm_d01`、`semantic_demo`、`manual_answer`、`real_answer` 四个演示输出 |
| `examples/outputs_real/` | 真实模型（DeepSeek 兼容端点）的 8 个用例输出 + `_summary.json` |
| `examples/traces/` | Mock 的 JSONL Trace：8 个用例 + `confirm_d01`、`semantic_demo`、`manual`、`manual_answer`、`real_answer` |
| `examples/traces_real/` | 真实模型 8 个用例的 JSONL Trace；冲突路径为 `search → read D02/D01/D03 → ask_user` |
| `examples/agent_eval.json` | 50 题评测集：20 个库外日常问题 + 30 个知识库问题（含冲突、改写、追问、缺口、4K、发票丢失） |
| `examples/agent_eval_results.json` | 真实模型 50 题逐题结果：状态、回答、引用、检索命中、Trace 路径；本次 48/50 |
| `examples/agent_eval_results_offline_mock.json` | 无 Key Mock 50 题逐题结果：50/50 |
| `examples/traces_agent_eval_real/` | 真实模型 50 题逐题 Trace |
| `examples/traces_agent_eval_offline/` | 离线 Mock 50 题逐题 Trace |
| `examples/retrieval_eval.json` | 20 条检索评测查询及期望 `section_id` |
| `examples/logs/pytest.txt` | pytest 实跑结果：51 passed, 1 skipped |
| `examples/logs/all_cases.txt` | Mock 8 用例的控制台输出 |
| `examples/logs/agent_eval_real.txt` | 真实模型 50 题评测的进度日志 |

## `docs/`：设计与验收文档

| 路径 | 具体内容 |
| --- | --- |
| `docs/01-requirements.md` | 用户、目标、范围、成功标准、六类验收点、非功能要求 |
| `docs/02-solution.md` | 总体架构、ReAct 循环、检索/冲突/引用/上下文方案、技术取舍 |
| `docs/03-evaluation.md` | 测试预期 vs 实际、检索评测、50 题评测、失败与限制、实际用时 |
| `docs/04-ai-usage.md` | AI 辅助了哪些文件、人工修改了什么、如何验证、提交前复核清单 |
| `docs/05-retrospective.md` | 最难的问题、学习收获、下一步、实际用时与未完成部分 |
| `docs/06-verification.md` | 六类场景、D01/D02 参考实例、替换文档实验、引用审计、离线模式验证 |

## 已验证结果

| 项 | 结果 |
| --- | --- |
| 自动测试 | 51 passed, 1 skipped |
| 无 Key Mock 8 项验收 | 8/8 |
| 无 Key Mock 50 题 | 50/50 |
| 真实模型 8 项验收 | 8/8 |
| 真实模型 50 题 | 48/50 = 96% |
| 引用逐字审计 | 20 个输出文件，0 问题 |

## 仓库

```text
https://github.com/shiwuing/-agent
```

分支 `main`；最新提交见仓库提交记录。

## 提交边界

- `.env` 不入库；仓库与上交包不含任何真实 Key，也不长期提供作者的 Key。
- API 模式需要评审自备对话 Key 与 Embedding Key；只做验收请用离线 Mock。
- 无 Key 时自动回退 Mock + 离线向量。
- 真实模型需要 `ANTHROPIC_API_KEY`（可选兼容端点）。
- 离线查询映射是近似的；知识库变更后需重新生成离线向量。
