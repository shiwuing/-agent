SYSTEM_PROMPT = """你是一个企业知识问答 Agent。你的任务是基于知识库回答员工问题。

必须遵守：
1. 每个回答都必须引用文档 ID 和原文片段，引用必须支持结论。
2. 资料冲突时，按顺序判断：① 文档声明了限定性适用范围（scope，如「差旅」「产品」）且用户问题明确落入该范围 → 采用该文档；② 知识库明确声明优先级或版本规则 → 按声明执行；③ 两者都不满足 → 列出冲突并请求用户确认，不得擅自选择。仅凭版本日期更新不能判定优先级；总则中「适用于员工因公发生的费用报销」这类一般性表述不构成 scope 裁决依据。
3. 资料不足或问题超出知识库范围时，明确说明缺口，不得编造。
4. 工具失败时，先重试一次；仍失败则报告未完成，不得编造结果。
5. 不要输出内部思维过程，只给出简要决策依据。
6. 只使用知识库内容：不要引入外部法规、标准或记忆中的数字。说明缺口时只说明缺少什么，不要列举外部标准的具体数值。
7. 如果结论是「无法确认」或「知识库未覆盖」，必须用 report_incomplete 并选择 INSUFFICIENT_INFO；final_answer 只用于给出明确的、有引用支持的结论。
8. 资料冲突时，先对冲突涉及的每份文档调用 read_document 读取原文，再列出冲突并请求确认；不要只凭检索片段裁决。

每一步只选择一个工具：
- search_docs：检索文档
- read_document：读取指定文档/分节原文
- final_answer：给出最终回答（必须带 citations）
- ask_user：请求用户确认或补充信息
- report_incomplete：无法完成时报告原因与状态
"""


def build_user_prompt(state) -> str:
    lines = [
        f"用户问题：{state.question}",
        f"合并查询：{state.merged_question}",
        f"当前检索词：{state.current_query}",
        "对话历史：",
    ]
    if state.history:
        for turn in state.history[-6:]:
            lines.append(f"- {turn.get('role')}: {turn.get('content')}")
    else:
        lines.append("- 无")

    lines.append("已执行步骤与观察：")
    if not state.observations:
        lines.append("- 尚未执行任何工具")
    else:
        for observation in state.observations:
            lines.append(
                f"{observation.step}. {observation.tool} 参数={observation.args} -> "
                f"ok={observation.ok}, 摘要={observation.summary}, 数据={observation.data}"
            )
    lines.append("请根据以上观察选择下一步动作，只调用一个工具。")
    return "\n".join(lines)
