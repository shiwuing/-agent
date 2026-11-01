# 04 · AI 使用说明

> 按笔试题要求，如实记录 AI 辅助范围、个人贡献与验证结果。

## 1. 使用的 AI 工具

- **Claude Code**（Anthropic 官方 CLI）
- 使用日期：2026-11-01

## 2. AI 辅助范围

| 环节 | AI 参与内容 | 人工/候选人参与内容 |
| --- | --- | --- |
| 需求整理 | 将试卷题目三整理为 README 中的需求、硬契约与验收矩阵 | 候选人确定选题、确认范围与硬契约 |
| 方案设计 | 提出原生 ReAct、关键词检索、冲突裁决顺序、引用校验等方案 | 候选人确认技术路线与目录结构 |
| 代码实现 | 生成 `src/`、`tests/`、`examples/inputs/` 初稿 | 候选人提供算力云环境并授权运行 |
| 测试与验证 | 编写 pytest 用例、执行云端测试、整理 Trace | 候选人审阅运行结果 |
| 文档 | 生成 `docs/01`–`05` 初稿与 README 更新 | 候选人最终校对与提交 |

## 3. AI 生成的具体文件

- `src/`：Agent 循环、Mock、Anthropic 客户端、知识库、冲突检测、引用校验、Trace、CLI。
- `tests/`：51 个测试用例 + 1 个需 Embedding API 的跳过项（含交互回归：材料问题不被期限冲突劫持、短问题不被误判为追问、对比性数值不被误判）。
- `data/`：5 篇合成文档、同义词表、42 条离线向量。
- `scripts/`：检索评测、50 题端到端评测、离线向量生成。
- `examples/`：8 组输入、Mock/真实输出、Trace 与评测日志。
- `docs/01`–`06`：需求、方案、评估、AI 使用、复盘、验收审计。
- `SUBMISSION.md`：逐文件说明。
- `README.md`：项目说明与实测结果。

## 4. 未由 AI 完成或未验证的部分

1. **真实模型调用**：收尾阶段已通过 DeepSeek 的 Anthropic 兼容端点实际运行（`deepseek-v4-flash`，8/8）；Claude 官方端点未实测。早期算力云阶段未配置 Key，当时的实测结果均为 Mock 模式。
2. **真实企业数据**：全部为合成 FAQ/制度，不含任何真实公司或个人信息。
3. **GitHub 提交**：已上传至 `https://github.com/shiwuing/-agent`；最终 commit SHA 见仓库最新提交。
4. **业务规则确认**：冲突裁决顺序、哪些字段算冲突、哪些问题应转人工，仍是候选人的业务判断，AI 只实现了候选人在 README 中确认的方案。

## 5. 验证方式与结果

| 验证 | 命令/文件 | 结果 |
| --- | --- | --- |
| 语法编译 | `python -m compileall -q src tests` | 通过 |
| 自动测试 | `pytest -q` | 51 passed, 1 skipped |
| Mock 全量用例 | `python -m src.main --all-cases --mock` | 8/8 passed |
| 真实模型全量用例 | `python -m src.main --all-cases --out-dir examples/outputs_real --trace-dir examples/traces_real` | 8/8 passed |
| 检索评测 | `python scripts/eval_retrieval.py` | 历史关键词 MRR 0.974 → BM25+改写/混合 1.000 |
| 离线 Mock 50 题 | 无 Key，`EMBEDDING_PROVIDER=offline` | 50/50 |
| 手工命令行 | `--question` / `--case` | 均返回预期状态 |
| Trace 审计 | `examples/traces/*.jsonl` | 步骤、参数、观察摘要、后续动作、决策依据完整 |
| 引用校验 | `tests/test_citation.py` | 伪造引用、错误文档、引用外数值均被拒绝 |

## 6. 诚实性声明

- 本文档所列测试结果均来自实际执行：早期 Mock 日志见 `examples/logs/`，当前结果见 `examples/outputs/` 与 `examples/outputs_real/`。
- Mock 结果只代表流程正确，不代表真实模型效果；真实模型结果为 DeepSeek 兼容端点的单次运行，受采样随机性影响。
- 未将 AI 生成的结论当作事实；所有业务事实均来自 `data/docs.json` 中的合成文档。
- 未提交任何真实密钥、隐私数据或公司内部资料。

## 7. 候选人提交前建议复核

- [x] 冲突裁决顺序已实现并由 `tests/test_conflict.py` 覆盖。
- [x] 「版本日期不单独裁决」已由测试锁定。
- [x] Mock 与真实模型的边界已在 README 与 `docs/06-verification.md` 说明。
- [x] 已配置真实模型端点并跑通全量用例（结果见 `examples/outputs_real/`）。
- [ ] 如需 Claude 官方端点结果，补充 `ANTHROPIC_BASE_URL` / `MODEL_ID` 后复跑。
- [x] 已补充 GitHub URL；最终 commit SHA 见仓库最新提交；实际用时已记录。
