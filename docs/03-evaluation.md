# 03 · 评估与测试结果

> 所有结果由算力云上的实际运行产生，输入与输出文件位于 `examples/`，可直接复核。

## 1. 测试环境

| 项 | 值 |
| --- | --- |
| 机器 | AutoDL 算力云容器（RTX 4080 SUPER） |
| 系统 | Ubuntu 22.04.1 LTS（Linux 5.15） |
| Python | 3.10.8（`/root/miniconda3`） |
| 虚拟环境 | `/root/agent-qa/.venv` |
| anthropic | 2.3.0 |
| pytest | 9.2.0 |
| python-dotenv | 1.2.4 |
| 运行模式 | Mock 阶段；另有真实模型复测（见下） |
| 日期 | 2026-11-01 |

真实模型复测环境：

| 项 | 值 |
| --- | --- |
| 机器 | Windows 11 |
| Python | 3.14.7 |
| anthropic | 2.3.0 |
| pytest | 9.2.0 |
| 端点 | DeepSeek 的 Anthropic 兼容接口（`ANTHROPIC_BASE_URL`） |
| 模型 | `deepseek-v4-flash`（Claude 官方端点未实测） |
| 检索 | 关键词 + FAISS 混合（火山方舟 `doubao-embedding-vision-251215`，余弦阈值 0.4） |

### 复现命令

```bash
cd /root/agent-qa
/root/miniconda3/bin/python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest -q
.venv/bin/python -m src.main --all-cases --mock
.venv/bin/python -m src.main --interactive --mock
```

日志（收尾阶段已在 Windows 本机按当前结果刷新）：

- `examples/logs/pytest.txt`
- `examples/logs/all_cases.txt`

## 2. 自动测试结果

```text
...............................s........                                [100%]
51 passed, 1 skipped in 0.38s
```

> 跳过项：`tests/test_semantic_api.py`。`pytest` 不加载 `.env`，所以该用例跳过；
> 真实 Embedding 已通过 `scripts/eval_retrieval.py` 单独验证（见第 3 节）。
> `examples/logs/pytest.txt` 已按当前结果刷新。

测试覆盖：

| 文件 | 覆盖内容 |
| --- | --- |
| `tests/test_acceptance.py` | T1–T7 端到端 + 重试成功 + 材料问题不被期限冲突劫持 + 短问题不被误判为追问 |
| `tests/test_context.py` | 追问标记识别：短的新问题不合并历史，显式追问才合并 |
| `tests/test_conflict.py` | 冲突检测、版本日期不裁决、范围裁决 |
| `tests/test_citation.py` | 引用存在性、逐字匹配、错误文档、数值白名单、中文数字与对比性数值 |
| `tests/test_tool_failure.py` | 失败重试、连续失败 |
| `tests/test_limits.py` | 步数上限 |
| `tests/test_mock_loop.py` | 两条路径动作不同、Trace 字段完整、观察驱动决策 |
| `tests/test_vector_store.py` | 向量索引与混合检索（假嵌入器） |
| `tests/test_cached_embedder.py` | 离线向量加载、查询映射、无 Key 默认模式 |
| `tests/test_semantic_api.py` | 真实 Embedding API 连通性；未配置时跳过 |

## 3. 检索评测

评测集：`examples/retrieval_eval.json`（20 条，含 8 条无字面重合的口语化改写 + 1 条库外问题），
脚本：`scripts/eval_retrieval.py`，指标为分节级 Recall@5 与 MRR。

| 方案 | Recall@5 | MRR | 说明 |
| --- | --- | --- | --- |
| 关键词 + 同义词（未加查询改写，历史基线） | 1.000 | 0.974 | 早期版本 |
| BM25 + 查询改写 | 1.000 | **1.000** | 当前无 Key 基线 |
| 离线预计算向量 + BM25 + 改写 | 1.000 | **1.000** | **无 Key、无下载、Mock 默认** |
| 在线向量（火山方舟 API） | 1.000 | **1.000** | 配置 Key 时 |

关键观察：

- 在本评测集上各方案都已饱和（Recall/MRR 均为 1.000）；离线向量对「去年没休完的年假怎么办」这类排序有帮助，但查询改写也能达到同样效果；
- 库外问题「食堂几点开门」不会返回任何向量命中，避免把无关片段喂给模型；
- 语料规模很小，Recall 已无提升空间；真正的收益要等知识库变大后才能体现。

### 3.1 无 Key 的 50 题 Mock

模拟评审环境：不配置对话 Key 与 Embedding Key，设置 `EMBEDDING_PROVIDER=offline`，运行 `--mock`。

结果（`examples/agent_eval_results_offline_mock.json`）：

| 指标 | 结果 |
| --- | --- |
| 状态准确率 | **50/50 = 100%** |
| 日常问题正确拒答 | **20/20** |
| 知识库问题状态准确率 | **30/30** |
| 分节引用命中率 | **19/19** |
| 分节检索召回率 | **19/19** |
| 运行方式 | Mock + 离线向量 + BM25，无任何 API/模型下载 |

边界：这是手工构造的 50 题评测集；离线查询映射是近似的，完全没见过的新表达可能映射失败并回退 BM25。

## 4. 用例执行结果

| 用例 | 输入 | 期望状态 | 实际状态 | 结果 | Trace |
| --- | --- | --- | --- | --- | --- |
| answer | 云剪辑支持导出哪些格式？ | `ANSWERED` | `ANSWERED` | 通过 | `examples/traces/answer.jsonl` |
| conflict | 报销期限是多久？ | `NEED_CONFIRMATION` | `NEED_CONFIRMATION` | 通过 | `examples/traces/conflict.jsonl` |
| followup | 历史：差旅报销需要哪些材料？→ 那期限呢？ | `ANSWERED` | `ANSWERED` | 通过 | `examples/traces/followup.jsonl` |
| gap | 公司食堂几点开饭？ | `INSUFFICIENT_INFO` | `INSUFFICIENT_INFO` | 通过 | `examples/traces/gap.jsonl` |
| paraphrase | 费用报销最晚多久内提交？ | `NEED_CONFIRMATION` | `NEED_CONFIRMATION` | 通过 | `examples/traces/paraphrase.jsonl` |
| retry_success | 云剪辑导出格式 + 首次检索失败 | `ANSWERED` | `ANSWERED` | 通过 | `examples/traces/retry_success.jsonl` |
| step_limit | 报销期限 + `max_steps=1` | `INCOMPLETE` | `INCOMPLETE` | 通过 | `examples/traces/step_limit.jsonl` |
| tool_failure | 云剪辑导出格式 + 持续检索失败 | `TOOL_ERROR` | `TOOL_ERROR` | 通过 | `examples/traces/tool_failure.jsonl` |

汇总文件：`examples/outputs/_summary.json`，8/8 通过。

真实模型全量运行（DeepSeek 兼容端点）：

| 用例 | 期望状态 | 实际状态 | 结果 |
| --- | --- | --- | --- |
| answer | `ANSWERED` | `ANSWERED` | 通过 |
| conflict | `NEED_CONFIRMATION` | `NEED_CONFIRMATION` | 通过 |
| followup | `ANSWERED` | `ANSWERED` | 通过 |
| gap | `INSUFFICIENT_INFO` | `INSUFFICIENT_INFO` | 通过 |
| paraphrase | `NEED_CONFIRMATION` | `NEED_CONFIRMATION` | 通过 |
| retry_success | `ANSWERED` | `ANSWERED` | 通过 |
| step_limit | `INCOMPLETE` | `INCOMPLETE` | 通过 |
| tool_failure | `TOOL_ERROR` | `TOOL_ERROR` | 通过 |

汇总文件：`examples/outputs_real/_summary.json`，8/8 通过。
输出与 Trace：`examples/outputs_real/`、`examples/traces_real/`。

### 4.1 50 题端到端评测

评测集：`examples/agent_eval.json`（20 个知识库外日常问题 + 30 个知识库问题）；
脚本：`scripts/eval_agent.py`；逐题结果：`examples/agent_eval_results.json`；
Trace：`examples/traces_agent_eval_real/`。

最终全量运行（DeepSeek 对话 + 火山方舟嵌入 + FAISS，约 382 秒）：

| 指标 | 结果 |
| --- | --- |
| 状态准确率（严格标注） | **48/50 = 96%** |
| 日常问题正确拒答 | **20/20 = 100%** |
| 知识库问题状态准确率 | **28/30 = 93.3%** |
| 分节引用命中率 | **18/19 = 94.7%** |
| 分节检索召回率 | **19/19 = 100%** |

失败 2 题及性质：

| 用例 | 现象 | 性质 |
| --- | --- | --- |
| kb-19 垫付多久拿回 | 模型返回纯文本「我会先检索…」但没有发起工具调用，循环按 `INCOMPLETE` 收口 | **模型输出不稳定**，非检索/护栏问题 |
| kb-23 那字幕呢 | 模型理解为「字幕导出」，知识库未覆盖；标注期望是 D04-2 字幕功能 | 指代歧义 |

> 更早的运行中还出现过引用片段被改写（校验器拦截并降级）与状态口径偏保守的情况；这些属于模型采样波动，测试与护栏已覆盖。

多次全量运行的状态准确率在 **90%–98%** 之间波动，日常问题始终 **20/20**。
检索召回始终为 100%，说明剩余问题集中在**状态口径、指代消歧和引用纪律**，不是检索缺失。

## 5. 验收点覆盖

| 验收点 | 覆盖用例 | 证据 |
| --- | --- | --- |
| 明确答案 | answer、retry_success | 引用 D04-1，回答含 MP4/MOV |
| 文档冲突 | conflict、paraphrase | 列出 D01=30 天 / D02=15 天，返回 `NEED_CONFIRMATION` |
| 资料外问题 | gap | 3 次检索未命中，返回 `INSUFFICIENT_INFO` |
| 改写后的相似问题 | paraphrase | 「最晚多久内提交」命中同一知识，动作与 conflict 一致 |
| 上下文追问 | followup | 合并历史后按 D03 差旅范围回答 15 天 |
| 工具失败 | tool_failure、retry_success | 失败重试 1 次；持续失败返回 `TOOL_ERROR`；一次失败后恢复 |
| 步数上限 | step_limit | `max_steps=1` → `INCOMPLETE` |
| 两条决策路径 | answer vs conflict | Trace 动作序列不同，见 `test_mock_loop.py` |
| 引用可校验 | 全部 ANSWERED | `tests/test_citation.py` + 输出中的 `citations` 字段 |
| 不擅自裁决 | conflict、paraphrase | `citations=[]`，`conflicts` 完整，请求确认 |

## 6. 关键 Trace 摘录

### 5.1 正常路径（answer）

`examples/traces/answer.jsonl`：

1. `search_docs({"query":"云剪辑支持导出哪些格式？","top_k":8})` → 命中 D04-1 等
2. `read_document(D04, D04-1)` → 读取导出格式原文
3. `final_answer` → 引用 D04-1，状态 `ANSWERED`

输出：`examples/outputs/answer.json`

### 5.2 冲突路径（conflict）

`examples/traces/conflict.jsonl`：

1. `search_docs("报销期限是多久？")` → 命中 7 个片段，检测到「报销期限」不一致
2. `read_document(D02, D02-1)` → 15 天
3. `read_document(D01, D01-2)` → 30 天
4. `read_document(D03, D03-2)` → 15 天（scope=差旅）
5. `ask_user` → 列出三方取值，返回 `NEED_CONFIRMATION`

关键点：虽然 D02 的版本日期（2025-06-01）比 D01（2024-01-01）新，但没有用版本日期裁决；D03 的 scope 是「差旅」，而问题未限定差旅，因此也不适用。最终请求用户确认。

### 5.3 资料缺口（gap）

`examples/traces/gap.jsonl`：

1. `search_docs("公司食堂几点开饭？")` → 无命中
2. 改写查询 → 仍无命中
3. 再次改写 → 仍无命中
4. `report_incomplete(INSUFFICIENT_INFO)` → 说明知识库无相关资料

### 5.4 工具失败（tool_failure / retry_success）

`examples/traces/tool_failure.jsonl`：

1. `search_docs` → `ok=false`（故障注入）
2. `search_docs` 重试 → `ok=false`
3. `report_incomplete(TOOL_ERROR)` → 明确失败，未编造结果

`examples/traces/retry_success.jsonl`：

1. `search_docs` → 失败
2. `search_docs` 重试 → 成功
3. `read_document(D04, D04-1)` → 成功
4. `final_answer` → `ANSWERED`

### 5.5 上下文追问（followup）

`examples/traces/followup.jsonl`：

1. 合并历史：「差旅报销需要哪些材料？ 那期限呢？」
2. `search_docs` → 命中材料与期限相关片段
3. 依次读取冲突涉及文档
4. 因问题包含「差旅」，D03 的 scope 命中 → 采用 D03-2（15 天）
5. `final_answer` → 引用 D03-2，状态 `ANSWERED`

### 5.6 步数上限（step_limit）

`examples/traces/step_limit.jsonl`：

1. `search_docs("报销期限是多久？")`
2. 达到 `max_steps=1`，输出 `INCOMPLETE`，未给出未经验证的答案。

> 真实模型更"省步"：早期用 `max_steps=2` 时，它可能在第 2 步直接 `ask_user`，从而不触发上限；
> 因此用例改为 `max_steps=1`，保证两种 provider 都真正走到上限分支。

## 7. 重复运行

- Mock 是确定性策略：同一用例重复运行，状态、引用与冲突项保持一致；`run_id` 每次不同，便于区分运行实例。
- Mock 阶段在算力云上分别执行了两次全量用例（`--all-cases`），两次均为 8/8 通过。
- 真实模型受采样随机性影响：同一用例的措辞、步数可能变化。收尾阶段曾观察到 `answer` 用例因编号列表被误判为数值断言而失败，修正校验器后复跑为 8/8；因此真实模型结果应理解为「本次运行」而非稳定保证。
- 示例数据为只读，不涉及写入型副作用；因此重复执行不会产生重复草稿或状态污染。

## 8. 失败与限制

1. **Mock 边界**：Mock 是确定性策略，只验证流程、状态机与护栏，**不证明真实模型的检索改写、冲突判断与回答质量**。
2. **真实模型已执行，但非 Claude**：收尾阶段通过 DeepSeek 的 Anthropic 兼容端点（`deepseek-v4-flash`）跑通 8/8；Claude 官方端点（`claude-opus-5-5`）在本次环境未实测，模型间行为可能存在差异。
3. **真实模型结果不稳定**：单次 8/8 不能保证重复运行全绿；同一问题的步数、措辞与是否追问会随采样变化。
4. **检索局限**：关键词 + 同义词 + 查询改写依赖人工维护；离线/在线向量已接入，但语料只有 9 个分节，本评测集已饱和（Recall/MRR 1.000）。相似度阈值 0.4 是针对该模型调出来的，换模型需要重新校准；离线查询映射是近似的。
5. **冲突规则局限**：字段规则目前硬编码为「报销期限」「年假天数」「导出格式」，新增业务字段需扩展 `FIELD_RULES`。
6. **数值校验较严格**：回答中出现引用原文之外的数字会被拒绝，可能误杀合理的派生计算；编号列表/日期等排版数字已剔除。回答对比提到本轮工具返回过的文档数值时，会放行（需在回答中点名该文档）。
7. **上下文有限**：仅合并上一轮用户问题，不支持复杂指代消解。
8. **未做性能与成本评估**：未测量真实模型的延迟、token 消耗与费用。

## 9. 实际用时与未完成部分

- AI 辅助实现、算力云环境搭建、测试与文档约 **50 分钟**；收尾（真实模型复测、离线 RAG、50 题评测、文档与提交）另约 **2 小时**；累计约 **3 小时**（不含前期选题）。
- 未完成：
  - Claude 官方端点（`claude-opus-5-5`）的实际运行与效果对比。
  - 更大规模知识库与重排模型（reranker）的效果验证。
  - 更复杂的多轮对话与指代消解。
