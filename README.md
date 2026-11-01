# 企业知识问答 Agent

> 小影科技 2027 校招 · AI Agent 笔试题 **题目三**
>
> 项目状态：**已实现，Mock 与真实模型均跑通；检索支持 FAISS 向量 + 关键词混合**。
> 实测：`pytest` **51 项通过 / 1 项跳过**；
> Mock `--all-cases` **8/8**；真实模型 `--all-cases` **8/8**（DeepSeek 的 Anthropic 兼容端点，`deepseek-v4-flash`）；
> 检索评测：BM25+查询改写、离线/在线向量在本评测集上均 Recall@5 **1.000** / MRR **1.000**；历史关键词基线 MRR **0.974**。
> 实际输出与 Trace 位于 `examples/outputs*/` 与 `examples/traces*/`；逐项验收审计见 `docs/06-verification.md`。
> 文件/文件夹职责说明见 [SUBMISSION.md](SUBMISSION.md)。
> 真实模型与检索结果受采样/模型分布影响，单次全绿不等于稳定；Claude 端点在本次环境中未实测。

---

## 两种运行模式

| 模式 | 对话模型 | Embedding | 需要什么 | 适用 |
| --- | --- | --- | --- | --- |
| **离线 Mock（默认）** | `MockLLM` 确定性策略 | 仓库内 `data/offline_embeddings.json` + BM25 | **不需要任何 Key** | 评审验收、离线演示、流程与护栏验证 |
| **API 模式** | 真实 Claude 或兼容端点 | 在线 Embedding（火山方舟 / OpenAI / Voyage） | **评审自备** `ANTHROPIC_API_KEY` + `EMBEDDING_API_KEY` | 真实模型与真实语义检索效果 |

> 仓库**不包含、也不会长期提供作者的 API Key**。评审如需 API 模式，请使用自己的账号和 Key；只做验收请直接使用离线 Mock。
>
> API 模式也可以只配置对话 Key；Embedding 不配置时会自动使用仓库内离线向量。

## 快速开始

评审无需任何 API Key：默认使用仓库内离线向量 + BM25。环境要求 Python 3.10+（本机实测 3.14.7）。

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m src.main --all-cases --mock
.venv\Scripts\python -m src.main --interactive --mock
```

macOS / Linux 把 `.venv\Scripts\` 换成 `.venv/bin/`。

交互示例：

```text
Q> 云剪辑支持导出哪些格式？
  A: 根据 D04《云剪辑产品 FAQ》D04-1：云剪辑支持导出 MP4、MOV 等常见视频格式。
  citations: D04/D04-1
```

API 模式需**使用你自己的 Key**：在 `.env` 填入 `ANTHROPIC_API_KEY`（可选 `ANTHROPIC_BASE_URL` / `MODEL_ID`）和 `EMBEDDING_API_KEY`；仓库不提供作者的 Key，未配置时自动回退 Mock + 离线向量。

---

## 目录

- [两种运行模式](#两种运行模式)
- [快速开始](#快速开始)
- [提交说明（文件职责）](SUBMISSION.md)
- [一、项目概述](#一项目概述)
- [二、需求拆解](#二需求拆解)
- [三、硬契约](#三硬契约)
- [四、实现方案](#四实现方案)
- [五、测试与验收](#五测试与验收)
- [六、交付物清单](#六交付物清单)
- [七、风险与避坑](#七风险与避坑)
- [八、3 小时排期](#八3-小时排期)
- [九、提交信息](#九提交信息)
- [附录 A：示例知识库](#附录-a示例知识库)
- [附录 B：硬契约自检表](#附录-b硬契约自检表)

---

## 一、项目概述

### 1.1 选题

**题目三：企业知识问答 Agent**

### 1.2 用户与目标

- **用户**：需要查询公司制度、流程或产品问题的企业员工。
- **目标**：基于带文档 ID 与版本日期的合成 FAQ / 制度，给出**有依据、可核验、能识别冲突与资料缺口**的答案。
- **范围**：单轮问答 + 简单上下文追问；本地知识库；CLI 运行。
- **不做的部分**：不接入真实企业知识库、不做线上部署、不做复杂权限体系、不做多 Agent。

### 1.3 成功标准

1. 六类验收场景（明确答案、文档冲突、资料外问题、改写问题、上下文追问、工具失败）均有可运行用例。
2. 每个回答都能追溯到 **文档 ID + 原文片段**，引用可被程序校验。
3. 资料冲突时**不擅自裁决**，能列出冲突并请求确认。
4. 模型不可用时，离线 Mock 能跑通完整决策流程（并明确其边界）。
5. 至少两条不同决策路径的 Trace 可复现：工具结果不同，模型的下一步动作随之改变。
6. 达到步数上限时返回明确的未完成状态。

### 1.4 实测摘要

| 项 | 结果 |
| --- | --- |
| Mock 环境 | 算力云 AutoDL，Ubuntu 22.04.1，Python 3.10.8，anthropic 2.3.0，pytest 9.2.0 |
| 真实模型环境 | Windows 11，Python 3.14.7，anthropic 2.3.0；DeepSeek Anthropic 兼容端点，`deepseek-v4-flash` |
| 自动测试 | `51 passed, 1 skipped`（跳过项为真实 Embedding API 连通性用例） |
| Mock 全量用例 | `8/8 passed`（`examples/outputs/_summary.json`） |
| 真实模型全量用例 | `8/8 passed`（`examples/outputs_real/_summary.json`） |
| 检索评测 | BM25+改写、离线/在线向量均 Recall@5=1.000/MRR=1.000；历史关键词基线 MRR=0.974 |
| 50 题端到端（真实模型） | **48/50 = 96%**；日常 20/20 拒答；分节检索召回 19/19 |
| 50 题端到端（无 Key Mock） | **50/50**，日常 20/20，引用命中 19/19；离线向量 + BM25 |
| 正常路径 | `search → read → answer`，引用 D04-1 |
| 冲突路径 | `search → read D02/D01/D03 → ask_user`，返回 `NEED_CONFIRMATION` |
| 缺口路径 | 3 次检索未命中 → `INSUFFICIENT_INFO` |
| 失败路径 | 检索失败 → 重试 1 次 → `TOOL_ERROR`；一次失败后恢复则 `ANSWERED` |
| 步数上限 | `max_steps=1` → `INCOMPLETE` |
| 真实模型 | DeepSeek 兼容端点 8/8；Claude 端点未实测，边界见 `docs/03-evaluation.md` |

> 复现命令与逐用例结果见 [5.1](#51-验收矩阵) 与 [5.3](#53-运行方式已验证)。

---

## 二、需求拆解

### 2.1 输入与材料

| 输入 | 说明 |
| --- | --- |
| `question` | 用户问题，必填 |
| `history` | 可选对话历史，用于上下文追问 |
| 知识库 | 合成 FAQ / 制度文档，每篇带 `doc_id`、`version_date`，可含 `scope`（适用范围）、`priority`（优先级）与分节内容 |
| 同义词表 | 可选，用于改写查询（如「报销期限」≈「报销时限」≈「多久内提交」） |

### 2.2 提供的工具

题目只要求两个业务工具：

| 工具 | 输入 | 输出 |
| --- | --- | --- |
| **文档检索** `search_docs` | `query`、`top_k` | 候选文档列表：`doc_id`、标题、版本日期、命中分节、片段、得分 |
| **片段读取** `read_document` | `doc_id`、可选 `section_id` | 指定文档/分节的完整原文 |

> 冲突检测、引用校验属于**代码层护栏**，不暴露为 Agent 工具，避免模型自行"裁决"冲突。

### 2.3 交付结果

每次运行的输出必须包含：

- `answer`：回答正文（无答案时为空）
- `citations`：`[{doc_id, section_id, quote}]`
- `gaps`：资料缺口说明（无则为空）
- `status`：任务状态
- `steps`：执行步骤与工具结果摘要（Trace）

状态枚举：

| 状态 | 含义 |
| --- | --- |
| `ANSWERED` | 已给出有引用的明确答案 |
| `NEED_CONFIRMATION` | 资料冲突或信息不足，需用户确认 |
| `INSUFFICIENT_INFO` | 知识库无相关资料，说明缺口 |
| `TOOL_ERROR` | 工具失败且无法恢复 |
| `INCOMPLETE` | 达到步数/调用上限，未完成 |

### 2.4 动态决策

模型根据检索结果选择：

- **补充检索**：改写查询、扩展同义词、拆分关键词
- **读取原文**：候选片段不足以判断时读取完整分节
- **追问 / 请求确认**：资料冲突无法裁决，或缺少关键信息
- **停止并回答**：引用充分且无冲突

**资料冲突时必须说明冲突并查证，不得凭空选一个答案。**

### 2.5 必须验收的六类场景

| # | 场景 | 期望行为 |
| --- | --- | --- |
| A1 | **明确答案** | 命中唯一相关文档 → 读取 → 回答并引用 |
| A2 | **文档冲突** | 两篇文档给出不同值且无范围/优先级 → 列出冲突 + 双引用 + 请求确认 |
| A3 | **资料外问题** | 检索无命中，改写后仍无 → 说明资料缺口，不编造 |
| A4 | **改写后的相似问题** | 同义改写能命中同一文档并给出相同结论 |
| A5 | **上下文追问** | 结合历史补全指代（如「那期限呢？」）后检索 |
| A6 | **工具失败** | 观察失败结果 → 有限重试/改写 → 仍失败则明确报错或未完成 |

> 额外加分：步数上限（A7）触发 `INCOMPLETE` 并说明卡点。

### 2.6 官方参考实例

- 规则 D01 写明「报销期限 30 天」，D02 写明「15 天」，**未给适用范围与优先级**。
- 问「报销期限多久」时，应**列出冲突与引用，并请求确认适用制度**；**不能擅自回答 15 天**。
- 只检索到 D01 且无冲突时，可依据 D01 回答。

### 2.7 通用考核要求（本题适用）

- 至少一个完整循环：**模型选择动作 → 执行工具 → 观察结果 → 模型调整下一步或结束**。
- 固定条件分支、自动重试或预设决策日志**不算** ReAct。
- 至少**两条执行路径**的运行记录，体现工具结果驱动不同后续动作。
- 执行记录含：步骤、工具参数、返回摘要、后续动作、简要决策依据（不提交模型内部思维过程）。
- 设置**步数或工具调用次数上限**，达到上限返回明确未完成状态。
- 运行方式 CLI / HTTP API / Notebook 三选一，给出可复制命令。
- 模型不可用须提供离线 Mock 入口并标明边界。
- 至少 3 组输入、实际输出与运行记录，覆盖正常、信息不足、工具失败，并覆盖全部验收点。
- 不提交真实密钥或隐私数据；所有材料放同一仓库。

---

## 三、硬契约

> 硬契约 = 做错即判缺陷的不可协商约束。分业务契约与工程契约。

### 3.1 业务硬契约

| # | 契约 | 说明 |
| --- | --- | --- |
| B1 | **引用强制** | 每个结论必须附 `doc_id` + 原文片段，不能只给文档名 |
| B2 | **引用支持结论** | 引用片段必须能直接支持回答，不能"引用 A、回答 B" |
| B3 | **引用真实** | 引用的 `quote` 必须真实存在于对应文档分节中，可被程序校验 |
| B4 | **冲突不裁决** | 资料冲突且无适用范围/优先级时，列出冲突并请求确认，不得擅自选一个 |
| B5 | **缺口不编造** | 资料外问题或资料不足时，明确说明缺口，不得无依据回答 |
| B6 | **版本日期 ≠ 优先级** | 仅凭版本新旧不能自动裁决冲突；除非资料中明确声明优先级规则 |
| B7 | **失败不伪装** | 工具失败必须被观察并处理；不能把失败步骤当作成功，不能编造检索结果 |
| B8 | **上下文有效** | 追问须结合历史补全语义；改写后的相似问题应命中同一知识 |

### 3.2 工程硬契约

| # | 契约 | 对应要求 | 实现/验证 |
| --- | --- | --- | --- |
| E1 | 完整 ReAct 循环 | Agent 决策要求 | `AgentLoop` 每步读取观察结果再决策 |
| E2 | 非固定分支 | 同上 | 决策函数消费 `state.observations`，两条路径 Trace 对比 |
| E3 | 两条以上决策路径记录 | 同上 | `examples/traces/` 至少 normal + conflict 两条 |
| E4 | 步数/工具调用上限 | 同上 | `MAX_STEPS=8`、失败重试上限 1 |
| E5 | 达上限返回未完成 | 同上 | `status=INCOMPLETE` + 卡点说明 |
| E6 | Trace 字段完整 | 同上 | 步骤、参数、返回摘要、下一步、决策依据 |
| E7 | 3+ 组输入输出记录 | 验证材料 | `examples/inputs|outputs|traces` |
| E8 | 覆盖全部验收点 | 验证材料 | 测试矩阵逐条映射 |
| E9 | 可复制运行命令 | 运行方式 | README + CLI |
| E10 | 离线 Mock 入口 + 边界说明 | 模型与工具 | `--mock`，文档标注边界 |
| E11 | 不提交密钥/隐私 | 提交规范 | `.env.example` 仅占位符 |
| E12 | 提交题号、GitHub URL、commit SHA | 提交规范 | 见第九节 |
| E13 | 记录实际用时与未完成部分 | 完成范围 | retrospective |

### 3.3 契约 → 实现 → 验证 对照

| 契约 | 实现位置（规划） | 验证方式 |
| --- | --- | --- |
| B1/B2/B3 | `src/citation.py` 引用组装与校验 | `tests/test_citation.py` + 答案输出检查 |
| B4/B6 | `src/conflict.py` 冲突检测与裁决策略 | `tests/test_conflict.py` |
| B5 | `Agent` 的 `INSUFFICIENT_INFO` 分支 | `tests/test_gap.py` |
| B7 | 工具返回 `ok=false`，循环观察后重试/终止 | `tests/test_tool_failure.py` |
| B8 | `src/agent/context.py` 历史合并 + 同义词改写 | `tests/test_followup.py`、`test_paraphrase.py` |
| E1/E2/E4/E5 | `src/agent/loop.py` | 两条 Trace + `test_limits.py` |
| E6 | `src/trace.py` | Trace 文件字段检查 |
| E10 | `src/agent/mock_llm.py` | `--mock` 全流程运行 |

---

## 四、实现方案

### 4.1 技术选型与取舍

| 项 | 选择 | 理由 |
| --- | --- | --- |
| 语言 | Python 3.10+ | 生态成熟，便于 Mock、测试与快速迭代 |
| 模型 | Anthropic 兼容接口；默认 `claude-opus-5-5`，可用 `MODEL_ID` / `ANTHROPIC_BASE_URL` 覆盖 | 官方 SDK 与 tool-use 循环；本次实测使用 DeepSeek 兼容端点 |
| SDK | 官方 `anthropic` Python SDK | 不手写 HTTP；便于类型化工具定义与错误处理 |
| Agent 框架 | **原生实现 ReAct 循环**，不使用 LangGraph/ADK | 考核明确「框架名称不加分」；原生循环更易解释决策与修改 |
| 检索 | 关键词 + 中文 bigram + 同义词表；可选 FAISS 向量混合（RRF 融合） | 默认关键词保证确定性与可测试；配置 `EMBEDDING_PROVIDER` 后启用 FAISS 混合检索 |
| 存储 | JSON 文件 | 便于审阅与版本管理 |
| 测试 | `pytest` | 标准、可执行 |
| 运行 | CLI（`argparse`） | 最省时，命令可复制 |
| 输出 | JSON（stdout + 文件） | 便于比对与引用 |

**取舍说明**：

- 默认不启用向量检索：题目知识库为合成小规模数据，关键词 + 同义词已能覆盖「改写相似问题」；向量模型会引入不可控因素，不利于确定性测试。代码保留可选混合检索（`src/embeddings.py`、`src/vector_store.py`）：向量用 FAISS `IndexFlatIP`（L2 归一化后等价余弦），关键词与向量按 RRF 融合；本次验收运行 `EMBEDDING_PROVIDER=none`，走纯关键词路径。
- 嵌入缓存写在 `data/.embedding_cache.json`，向量索引在内存中构建，不写入 C 盘。
- 原生循环：虽然代码量略高于框架，但每步决策、观察与 Trace 完全可控，便于证明 ReAct 真实性。

### 4.2 总体架构

```
            ┌──────────────────────────────┐
            │            CLI               │
            │  --question / --case / --mock│
            └──────────────┬───────────────┘
                           │
                    ┌──────▼───────┐
                    │  AgentLoop   │  ← 状态机 + 步数上限
                    └──┬────┬──────┘
                       │    │
          ┌────────────▼┐  ┌▼─────────────┐
          │  LLMClient   │  │   Tools      │
          │ real / mock  │  │ search/read  │
          └──────┬───────┘  └──────┬───────┘
                 │                 │
        ┌────────▼────────┐  ┌─────▼────────┐
        │ Anthropic SDK   │  │ KnowledgeBase│
        │ claude-opus-5-5 │  │  data/*.json │
        └─────────────────┘  └──────────────┘
                 │
          ┌──────▼───────┐
          │  TraceWriter │ → examples/traces/*.jsonl
          └──────────────┘
```

### 4.3 知识库与数据设计

文档格式（`data/docs.json`）：

```json
{
  "doc_id": "D01",
  "title": "财务报销管理制度",
  "version_date": "2024-01-01",
  "scope": null,
  "priority": null,
  "sections": [
    {
      "section_id": "D01-3.2",
      "heading": "报销时限",
      "content": "员工应在费用发生之日起 30 天内提交报销申请。"
    }
  ]
}
```

字段约定：

- `doc_id`：稳定唯一标识，引用与校验的主键。
- `version_date`：版本日期；**不等于优先级**，只在资料声明了版本规则时才参与裁决。
- `scope`：适用范围（如「差旅」「国内」）；为空表示未声明。
- `priority`：显式优先级；仅在知识库明确给出时才使用。
- `sections`：分节内容，引用定位到 `section_id`，片段必须逐字可匹配。

### 4.4 工具接口定义

```python
@dataclass
class ToolResult:
    ok: bool
    data: Any = None
    error: str | None = None
    summary: str = ""

def search_docs(query: str, top_k: int = 5) -> ToolResult: ...
def read_document(doc_id: str, section_id: str | None = None) -> ToolResult: ...
```

约定：

- 工具失败**不抛异常穿透到模型**，返回 `ok=false` + `error` + `summary`，让模型观察到失败后再决策。
- `summary` 为给模型看的一句话摘要（如「命中 2 篇：D01、D02，数值不一致」）。
- 失败注入：环境变量 `MOCK_FAIL_TOOL=search_docs`，或测试中直接替换工具实现。

### 4.5 ReAct 决策循环

状态对象：

```python
@dataclass
class AgentState:
    question: str
    history: list[dict]
    observations: list[dict]   # 每步工具结果
    candidate_docs: list[dict]
    read_sections: dict        # doc_id/section_id -> 原文
    conflicts: list[dict]
    steps: int
    status: str = "RUNNING"
```

循环伪代码：

```python
for step in range(MAX_STEPS):
    action = llm.decide(state, tools_schema)   # 模型选择动作
    if action.type == "answer":
        return finalize_answer(state, action)
    if action.type == "ask_user":
        return finalize_confirmation(state, action)
    if action.type == "report_incomplete":
        return finalize_incomplete(state, action)

    result = run_tool(action.tool, action.args)  # 执行工具
    state.observe(action, result)                # 观察结果
    trace.log(step, action, result, action.reason)

return finalize_incomplete(state, "达到步数上限")
```

- 模型可选动作：`search_docs`、`read_document`、`answer`、`ask_user`、`report_incomplete`。
- 每次决策必须基于当前 `observations`，而不是预设顺序。
- 步数上限 `MAX_STEPS = 8`；工具失败重试上限 1 次。

### 4.6 六类场景的处理策略

| 场景 | 观察到的信号 | 模型决策 | 期望状态 |
| --- | --- | --- | --- |
| 明确答案 | 检索命中 1 篇高相关文档 | 读取分节 → 引用回答 | `ANSWERED` |
| 文档冲突 | 命中多篇，同一字段数值不同 | 读取两篇原文 → 确认无 scope/priority → 列出冲突并请求确认 | `NEED_CONFIRMATION` |
| 资料外问题 | 首轮无命中 | 改写查询再检索 → 仍无 → 说明缺口 | `INSUFFICIENT_INFO` |
| 改写相似问题 | 原查询无命中或低分 | 同义词/关键词改写 → 命中同一文档 → 回答 | `ANSWERED` |
| 上下文追问 | 问题含指代或省略 | 合并历史问题 → 检索 → 回答 | `ANSWERED` |
| 工具失败 | `ok=false` | 重试 1 次 → 仍失败 → 报告工具错误/未完成，不编造 | `TOOL_ERROR` 或 `INCOMPLETE` |
| 步数上限 | `steps == MAX_STEPS` | 停止并返回卡点 | `INCOMPLETE` |

### 4.7 冲突检测与裁决

**检测**（`src/conflict.py`）：

1. 从问题中识别目标字段（如「报销期限」）。
2. 从命中分节中抽取数值/日期/百分比等关键值。
3. 同一字段出现不同值 → 标记冲突，记录 `{field, values: [{doc_id, section_id, quote, value}]}`。

**裁决顺序**（严格按序，任一步不满足即进入下一层）：

1. **适用范围匹配**：若文档声明 `scope` 且问题可明确归入该范围 → 使用该文档。
2. **显式优先级**：若知识库声明 `priority` 或版本规则 → 按声明执行。
3. **版本日期**：**不单独作为裁决依据**（B6），除非资料明确写了「以最新版本为准」。
4. **无法裁决** → `NEED_CONFIRMATION`：列出所有冲突项、引用原文、说明缺失的判定依据，请用户确认适用制度。

> 关键点：不得因为 D02 版本更新就默认回答 15 天；这属于 B4/B6 的违规。

### 4.8 引用与防幻觉校验

回答生成后，由**代码**执行校验（不依赖模型自觉）：

1. 每个 citation 的 `doc_id` 必须存在于知识库。
2. `section_id` 必须存在于该文档。
3. `quote` 必须是该分节原文的**逐字子串**（去除首尾空白后比较）。
4. 回答中出现的数值必须能在引用片段中找到（数值白名单）。
5. 任一校验失败 → 不返回该答案，降级为 `NEED_CONFIRMATION` 或 `INSUFFICIENT_INFO`。

### 4.9 上下文与查询改写

- 保留最近 3 轮对话；追问时把历史问题与当前问题合并为检索查询。
- 指代解析：如「那期限呢？」结合上一轮主题补全为「差旅报销期限」。
- 查询改写策略：同义词表替换、去掉疑问词、提取核心名词短语。
- 改写次数上限 2 次，避免无意义循环。

### 4.10 步数上限与未完成状态

```python
MAX_STEPS = 8
MAX_TOOL_RETRIES = 1
```

- 达到 `MAX_STEPS` 或重试上限 → `INCOMPLETE`。
- 输出必须包含：已执行步骤、最后的工具结果摘要、卡点原因、已获得的候选资料（若有）。
- 不得在未完成时输出看似完整的答案。

### 4.11 离线 Mock 模式

`LLMClient` 接口统一为：

```python
class LLMClient(Protocol):
    def decide(self, state: AgentState, tools: list[dict]) -> Action: ...
```

- **真实模式**：官方 `anthropic` SDK，默认模型 `claude-opus-5-5`，`thinking={"type": "adaptive"}`，通过 tool-use 让模型选择动作；检查 `stop_reason`，异常按工具错误处理。
- **Mock 模式**：`MockLLM` 基于 `state.observations` 的确定性策略模拟「观察 → 决策」，用于离线跑通全流程。
- **Mock 边界（必须写入文档）**：Mock 只验证流程、状态与护栏，**不证明真实模型的决策质量**；真实效果需用真实模型运行 `examples/` 用例。
- **无 Key 自动回退**：未配置 `ANTHROPIC_API_KEY` / `ANTHROPIC_AUTH_TOKEN` 时，程序打印警告并自动切换到 Mock，评审无需任何 Key 即可运行；作者的 Key 不会随仓库提供。
- **离线向量（默认）**：无 Embedding Key 时加载仓库内 `data/offline_embeddings.json`（火山方舟预计算的 42 条文档/问题向量）；新查询用字符相似度映射到最接近的问题样例并复用其向量，映射失败时回退 BM25. 不下载模型、不调用 API、不需要 GPU。
- CLI：`--mock` 或 `LLM_PROVIDER=mock`；`EMBEDDING_PROVIDER=offline|none` 控制离线向量/纯关键词。

### 4.12 Trace 记录格式

每次运行写 `examples/traces/<run_id>.jsonl`，每步一行：

```json
{
  "run_id": "20261101-001",
  "step": 1,
  "action": {"type": "tool", "tool": "search_docs", "args": {"query": "报销期限多久", "top_k": 5}},
  "observation": {"ok": true, "summary": "命中 D01、D02，均含报销期限但数值不同"},
  "next_action": "read_document",
  "reason": "存在两篇候选且数值可能冲突，先读取原文核实"
}
```

要求：

- 记录步骤、工具参数、返回摘要、后续动作、决策依据。
- **不记录模型内部思维过程**，只记录可审计的决策依据。
- 最终写入一条 `final` 记录：`status`、`citations`、`gaps`、`steps`。

---

## 五、测试与验收

### 5.1 验收矩阵（实际结果）

| 用例 | 输入 | 期望 | 实际（Mock / 真实） | 关键结果 | 材料文件 |
| --- | --- | --- | --- | --- | --- |
| answer | 云剪辑支持导出哪些格式？ | `ANSWERED` | `ANSWERED` / `ANSWERED` | 引用 D04-1，回答含 MP4/MOV | `examples/inputs/answer.json` |
| conflict | 报销期限是多久？ | `NEED_CONFIRMATION` | `NEED_CONFIRMATION` / `NEED_CONFIRMATION` | 列出 D01=30 天 / D02=15 天 / D03=15 天（scope=差旅），请求确认 | `examples/inputs/conflict.json` |
| gap | 公司食堂几点开饭？ | `INSUFFICIENT_INFO` | `INSUFFICIENT_INFO` / `INSUFFICIENT_INFO` | 多次检索未命中，说明知识库无资料 | `examples/inputs/gap.json` |
| paraphrase | 费用报销最晚多久内提交？ | `NEED_CONFIRMATION` | `NEED_CONFIRMATION` / `NEED_CONFIRMATION` | 与 conflict 命中同一知识，动作一致 | `examples/inputs/paraphrase.json` |
| followup | 历史：差旅报销要哪些材料？→ 那期限呢？ | `ANSWERED` | `ANSWERED` / `ANSWERED` | 结合历史与 D03 的 scope 回答 | `examples/inputs/followup.json` |
| retry_success | 云剪辑导出格式 + 首次检索失败 | `ANSWERED` | `ANSWERED` / `ANSWERED` | 失败一次后重试成功 | `examples/inputs/retry_success.json` |
| step_limit | 报销期限 + `max_steps=1` | `INCOMPLETE` | `INCOMPLETE` / `INCOMPLETE` | 返回步数上限与卡点 | `examples/inputs/step_limit.json` |
| tool_failure | 云剪辑导出格式 + 持续检索失败 | `TOOL_ERROR` | `TOOL_ERROR` / `TOOL_ERROR` | 观察失败、重试 1 次后明确报错 | `examples/inputs/tool_failure.json` |

> Mock 汇总：`examples/outputs/_summary.json`（8/8）。
> 真实模型汇总：`examples/outputs_real/_summary.json`（8/8）。
> Mock 输出与 Trace：`examples/outputs/`、`examples/traces/`；真实模型：`examples/outputs_real/`、`examples/traces_real/`。
> 真实模型单次结果受采样随机性影响，重复运行可能得到不同措辞或步数。

### 5.2 测试设计（实际 51 通过 / 1 跳过）

| 测试文件 | 覆盖 |
| --- | --- |
| `test_acceptance.py` | 明确答案、冲突、缺口、改写、追问、工具失败、重试成功、步数上限、材料问题不被期限冲突劫持、短问题不被误判为追问 |
| `test_context.py` | 追问标记识别：短的新问题不合并历史，显式追问才合并 |
| `test_conflict.py` | 冲突检测、裁决顺序、版本日期不越权、scope 裁决 |
| `test_citation.py` | 引用存在性、逐字匹配、错误文档、引用外数值、中文数字与对比性数值 |
| `test_tool_failure.py` | 失败重试、连续失败 |
| `test_limits.py` | 步数上限、未完成输出 |
| `test_mock_loop.py` | 两条路径动作不同、Trace 字段完整、观察驱动决策 |
| `test_vector_store.py` | 向量索引构建、检索与融合（使用假嵌入器，无需外部 API） |
| `test_cached_embedder.py` | 离线向量加载、查询映射、无 Key 默认模式、离线混合检索 |
| `test_semantic_api.py` | 真实 Embedding API 连通性（未配置时跳过） |

### 5.3 运行方式（已验证）

```bash
# 1. 安装
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS / Linux:
source .venv/bin/activate
pip install -r requirements.txt

# 2. 离线运行（无需 API Key；默认使用仓库内离线向量 + BM25）
python -m src.main --question "报销期限是多久？" --mock
python -m src.main --case examples/inputs/conflict.json
python -m src.main --all-cases --mock

# 2.1 交互模式（连续提问，保留上下文）
python -m src.main --interactive --mock
# 命令：reset 清空历史，help 帮助，exit 退出

# 3. 真实模型（需 ANTHROPIC_API_KEY）
cp .env.example .env        # 填入 Key；如用兼容端点，同时设置 ANTHROPIC_BASE_URL / MODEL_ID
python -m src.main --question "报销期限是多久？"

# 3.1 真实模型跑全量用例，结果单独落盘，不覆盖 Mock 产物
python -m src.main --all-cases --out-dir examples/outputs_real --trace-dir examples/traces_real

# 4. 测试
pytest -q

# 5. 检索评测（配置 Embedding 后自动对比关键词 vs FAISS 混合）
python scripts/eval_retrieval.py
python scripts/eval_retrieval.py --keyword-only

# 6. 50 题端到端评测（真实模型 + 混合检索）
python scripts/eval_agent.py
python scripts/eval_agent.py --category daily
python scripts/eval_agent.py --category kb

# 6.1 无 Key 离线 Mock 评测（评审默认）
EMBEDDING_PROVIDER=offline python scripts/eval_agent.py --trace-dir examples/traces_agent_eval_offline --output examples/agent_eval_results_offline_mock.json
```

算力云上的实际执行方式（已验证）：

```bash
cd /root/agent-qa
/root/miniconda3/bin/python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest -q                 # 当前 51 passed / 1 skipped
.venv/bin/python -m src.main --all-cases --mock  # 8/8 passed
```

> 日志已按当前结果刷新：`examples/logs/pytest.txt`、`examples/logs/all_cases.txt`（Windows 本机执行）。
> 当前真实模型结果：`examples/outputs_real/`、`examples/traces_real/`。

---

## 六、交付物清单

### 6.1 目录结构（实际）

```
.
├── README.md
├── SUBMISSION.md              # 文件/文件夹职责说明
├── requirements.txt
├── .env.example
├── .gitignore
├── src/
│   ├── __init__.py
│   ├── main.py                 # CLI 入口
│   ├── models.py               # Action / Observation / AgentState
│   ├── kb.py                   # 知识库加载、检索、分节读取
│   ├── embeddings.py           # 可选 Embedding 客户端（OpenAI/Voyage 兼容）
│   ├── vector_store.py         # 可选向量索引与混合检索
│   ├── citation.py             # 引用逐字校验、数值白名单
│   ├── conflict.py             # 冲突检测与裁决顺序
│   ├── trace.py                # JSONL Trace 落盘
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── loop.py             # ReAct 主循环 + 步数上限
│   │   ├── llm.py              # Anthropic 真实模型客户端
│   │   ├── mock_llm.py         # 离线 Mock 策略
│   │   ├── context.py          # 历史合并、查询改写
│   │   └── prompts.py          # 系统提示词与观察组装
│   └── tools/
│       ├── __init__.py
│       ├── search.py           # 文档检索工具
│       ├── read.py             # 片段读取工具
│       └── runtime.py          # 工具执行器 + 故障注入
├── tests/
│   ├── conftest.py
│   ├── helpers.py
│   ├── fake_embedder.py
│   ├── test_acceptance.py
│   ├── test_context.py
│   ├── test_conflict.py
│   ├── test_citation.py
│   ├── test_tool_failure.py
│   ├── test_limits.py
│   ├── test_mock_loop.py
│   ├── test_vector_store.py
│   ├── test_cached_embedder.py
│   └── test_semantic_api.py
├── scripts/
│   ├── eval_retrieval.py        # 关键词 vs FAISS 混合检索评测
│   ├── eval_agent.py            # 50 题 Agent 端到端评测
│   └── build_offline_embeddings.py  # 重新生成离线向量缓存（需 Key）
├── examples/
│   ├── retrieval_eval.json      # 检索评测集（Recall@k / MRR）
│   ├── agent_eval.json          # 50 题端到端评测集（20 日常 + 30 知识库）
│   ├── inputs/
│   │   ├── answer.json
│   │   ├── conflict.json
│   │   ├── gap.json
│   │   ├── paraphrase.json
│   │   ├── followup.json
│   │   ├── retry_success.json
│   │   ├── step_limit.json
│   │   └── tool_failure.json
│   ├── outputs/                # Mock 输出 + _summary.json
│   ├── traces/                 # Mock Trace（JSONL）
│   ├── outputs_real/           # 真实模型输出 + _summary.json
│   ├── traces_real/            # 真实模型 Trace（JSONL）
│   ├── agent_eval_results.json # 真实模型 50 题结果
│   ├── agent_eval_results_offline_mock.json # 无 Key Mock 50 题结果
│   ├── traces_agent_eval_real/    # 真实模型 50 题 Trace
│   ├── traces_agent_eval_offline/ # 离线 Mock 50 题 Trace
│   └── logs/                      # pytest、全量用例与评测日志
├── data/
│   ├── docs.json               # 5 篇合成文档
│   ├── synonyms.json           # 同义词表
│   └── offline_embeddings.json # 预计算离线向量（42 条，约 1.5MB）
└── docs/
    ├── 01-requirements.md
    ├── 02-solution.md
    ├── 03-evaluation.md
    ├── 04-ai-usage.md
    ├── 05-retrospective.md
    └── 06-verification.md      # 交付前逐项验收审计
```

### 6.2 文档分工

| 文档 | 内容 |
| --- | --- |
| `01-requirements.md` | 用户、目标、范围、成功标准（可由本 README 第一、二节展开） |
| `02-solution.md` | 调用流程、动态决策、技术取舍、模型与框架说明 |
| `03-evaluation.md` | 测试预期 vs 实际结果、失败与限制，引用 `examples/` 具体文件 |
| `04-ai-usage.md` | AI 辅助了哪些内容、个人修改了什么、如何验证 |
| `05-retrospective.md` | 最难的问题、学习收获、下一步 |
| `06-verification.md` | 六类场景、引用逐字审计、替换文档实验、已知限制 |

### 6.3 `.env.example`

```dotenv
# 两种模式：
# 1) 离线 Mock（默认）：无需任何变量；MockLLM + data/offline_embeddings.json
# 2) API 模式：使用你自己的 ANTHROPIC_API_KEY（对话）与 EMBEDDING_API_KEY（在线向量）
# 仓库不包含、也不会长期提供作者的 Key。
ANTHROPIC_API_KEY=your_api_key_here
# 官方 Anthropic 端点留空；兼容端点可指向对应服务
# ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic

# anthropic | mock
LLM_PROVIDER=anthropic

# 默认 claude-opus-5-5；兼容端点需改成对方模型名
MODEL_ID=claude-opus-5-5

# 语义检索；offline = 仓库内预计算向量（无 Key 默认）
# openai | voyage | ark | offline | none
EMBEDDING_PROVIDER=offline
EMBEDDING_API_KEY=your_embedding_key_here
EMBEDDING_BASE_URL=https://api.openai.com/v1
EMBEDDING_MODEL=text-embedding-3-small
# 低于该余弦相似度的向量命中会被丢弃
EMBEDDING_MIN_SCORE=0.4

# 本次实测使用火山方舟多模态 embedding：
# EMBEDDING_PROVIDER=ark
# EMBEDDING_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
# EMBEDDING_MODEL=doubao-embedding-vision-251215

# 可选：故障注入（验证工具失败路径）
# MOCK_FAIL_TOOL=search_docs
```

---

## 七、风险与避坑

| 风险 | 后果 | 应对 |
| --- | --- | --- |
| 模型在冲突时擅自选答案 | 违反 B4，关键缺陷 | 代码层冲突检测 + 强制 `NEED_CONFIRMATION`，引用校验兜底 |
| 模型编造引用片段 | 违反 B3/B5，关键缺陷 | 逐字子串校验，失败即降级 |
| 固定 `if/else` 冒充 ReAct | 不满足 E1/E2 | 决策函数必须读取 observations；两条 Trace 证明路径不同 |
| Mock 被误认为真实效果 | 评估失真 | 文档与输出中明确标注 Mock 边界 |
| 版本日期被当作优先级 | 违反 B6 | `conflict.py` 显式禁止，测试覆盖 |
| 工具失败被吞掉 | 违反 B7 | 工具返回 `ok=false`，循环观察并记录 |
| 上下文追问丢失主题 | 答非所问 | 历史合并 + 指代补全测试 |
| 超过步数仍输出答案 | 违反 E5 | 循环结束统一走 `INCOMPLETE` |
| Windows 命令不兼容 | 评审无法运行 | README 同时给 Windows 与 Unix 命令 |
| 提交真实密钥 | 违规 | `.env` 不入库，`.env.example` 仅占位符 |

---

## 八、3 小时排期

| 时间 | 任务 | 产出 |
| --- | --- | --- |
| 0:00–0:15 | 确认需求与契约，建目录与数据 | `data/docs.json`、`docs/01` 初稿 |
| 0:15–0:45 | 实现知识库、检索、读取工具 | `src/kb.py`、`src/tools/` |
| 0:45–1:30 | 实现 ReAct 循环 + 真实/Mock 客户端 | `src/agent/` |
| 1:30–2:00 | 实现冲突检测、引用校验、状态收口 | `src/conflict.py`、`src/citation.py` |
| 2:00–2:30 | 跑 8 个用例，生成 outputs 与 traces | `examples/` |
| 2:30–2:50 | 写 pytest 并跑通 | `tests/`、测试输出 |
| 2:50–3:00 | 补 `docs/03`~`05`、更新 README 实测结果 | 完整交付 |

> 实际用时与未完成部分在 `docs/05-retrospective.md` 与提交说明中如实记录。

---

## 九、提交信息

提交时需在答卷中提供：

| 项 | 内容 |
| --- | --- |
| 题号 | 3（企业知识问答 Agent） |
| GitHub URL | `https://github.com/shiwuing/-agent` |
| 最终 commit SHA | 见仓库最新提交（本文件更新后推送） |
| 评审可读 | 若为私有仓库，需授权指定评审账号 |
| 实际用时 | 实现与云上验证约 50 分钟；收尾（真实模型复测、离线 RAG、50 题评测、文档与提交）另约 2 小时；累计约 3 小时（不含前期选题） |
| 未完成部分 | Claude 官方端点实测、更大规模知识库 / reranker 验证、更复杂多轮消歧 |

---

## 附录 A：示例知识库

> 合成数据，用于覆盖六类验收场景；已写入 `data/docs.json`。

| 文档 | 标题 | 版本日期 | 关键内容 | 用途 |
| --- | --- | --- | --- | --- |
| D01 | 财务报销管理制度 | 2024-01-01 | 报销期限 30 天（自费用发生日起） | 冲突一方 / 单文档答案 |
| D02 | 费用报销常见问题 | 2025-06-01 | 报销期限 15 天 | 冲突另一方 |
| D03 | 差旅报销说明 | 2025-03-01 | 差旅报销材料清单；`scope=差旅` | 上下文追问、范围匹配 |
| D04 | 云剪辑产品 FAQ | 2025-02-01 | 支持导出 MP4/MOV 等格式 | 明确答案 |
| D05 | 员工手册（节选） | 2023-09-01 | 年假天数与跨年规则 | 改写问题、追问 |

**冲突用例设定**：D01 与 D02 均未声明 `scope`/`priority`，因此「报销期限」问题必须返回冲突并请求确认。

**范围裁决扩展（可选）**：若某文档声明 `scope=差旅` 且问题明确限定「差旅」，则按 B4 的裁决顺序第 1 条使用该文档；需在测试中单独覆盖。

---

## 附录 B：硬契约自检表

提交前逐条打勾（除 E12 外，均已由代码、测试或云上运行验证）：

- [x] B1 每个结论都有 `doc_id` + 原文片段
- [x] B2 引用片段能直接支持结论
- [x] B3 引用片段逐字存在于文档中
- [x] B4 冲突时列出双方并请求确认，未擅自选择
- [x] B5 资料外问题明确说明缺口，未编造
- [x] B6 未用版本日期擅自裁决冲突
- [x] B7 工具失败被观察并处理，未伪装成功
- [x] B8 追问结合历史，改写问题命中同一知识
- [x] E1 存在完整 ReAct 循环
- [x] E2 决策基于工具结果，非固定分支
- [x] E3 至少两条不同路径的 Trace
- [x] E4 步数/调用上限已设置
- [x] E5 达上限返回 `INCOMPLETE`
- [x] E6 Trace 字段完整（步骤/参数/摘要/后续动作/依据）
- [x] E7 至少 3 组输入、输出、Trace
- [x] E8 六类验收点全覆盖
- [x] E9 运行命令可复制执行
- [x] E10 离线 Mock 可运行且边界已说明
- [x] E11 仓库无真实密钥/隐私
- [x] E12 提交题号、URL、commit SHA（URL 已填写，SHA 见仓库最新提交）
- [x] E13 记录实际用时与未完成部分
