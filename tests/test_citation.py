from __future__ import annotations

from src.citation import validate_citations


def test_valid_citation(kb):
    quote = "云剪辑支持导出 MP4、MOV 等常见视频格式。"
    ok, errors = validate_citations(
        f"根据 D04《云剪辑产品 FAQ》D04-1：{quote}",
        [{"doc_id": "D04", "section_id": "D04-1", "quote": quote}],
        kb,
    )
    assert ok, errors


def test_fabricated_quote_rejected(kb):
    ok, errors = validate_citations(
        "云剪辑支持导出 AVI 格式。",
        [{
            "doc_id": "D04",
            "section_id": "D04-1",
            "quote": "云剪辑支持导出 AVI 格式。",
        }],
        kb,
    )
    assert not ok
    assert errors


def test_wrong_doc_rejected(kb):
    ok, _ = validate_citations(
        "内容",
        [{"doc_id": "D04", "section_id": "D99-1", "quote": "内容"}],
        kb,
    )
    assert not ok


def test_iso_date_in_answer_allowed(kb):
    """回答里提到文档的版本日期，不应被拆成 2025/02/01 三个伪数值。"""
    quote = "云剪辑支持导出 MP4、MOV 等常见视频格式。"
    ok, errors = validate_citations(
        "根据《云剪辑产品 FAQ》（D04-1，版本日期 2025-02-01）：" + quote,
        [{"doc_id": "D04", "section_id": "D04-1", "quote": quote}],
        kb,
    )
    assert ok, errors


def test_chinese_date_in_answer_allowed(kb):
    quote = "云剪辑支持导出 MP4、MOV 等常见视频格式。"
    ok, errors = validate_citations(
        "根据 D04-1（2025年2月1日版本）：" + quote,
        [{"doc_id": "D04", "section_id": "D04-1", "quote": quote}],
        kb,
    )
    assert ok, errors


def test_numbered_list_markers_allowed(kb):
    """回答用编号列表分点时，序号（1./2）不应被当成数值断言。"""
    quote = "云剪辑支持导出 MP4、MOV 等常见视频格式。"
    answer = (
        "根据 D04-1：云剪辑支持导出 MP4、MOV 等常见视频格式。\n"
        "补充说明：\n"
        "1. 原文只给出概括表述，未列完整清单。\n"
        "2. 未说明分辨率等规格。\n"
        "3. 如需更多格式请向产品团队确认。"
    )
    ok, errors = validate_citations(
        answer,
        [{"doc_id": "D04", "section_id": "D04-1", "quote": quote}],
        kb,
    )
    assert ok, errors


def test_bracket_and_ordinal_markers_allowed(kb):
    quote = "云剪辑支持导出 MP4、MOV 等常见视频格式。"
    answer = f"（1）{quote}（2）未列完整清单；第 3 点：需向产品团队确认。"
    ok, errors = validate_citations(
        answer,
        [{"doc_id": "D04", "section_id": "D04-1", "quote": quote}],
        kb,
    )
    assert ok, errors


def test_observed_conflicting_number_allowed_when_doc_mentioned(kb):
    """回答对比提到本轮检索到的 D02 数值时，不应被判为编造。"""
    quote = "员工应在费用发生之日起 30 天内提交报销申请。"
    answer = "按 D01，应在 30 天内提交；此前 D02 的 15 天规定不再适用。"
    observed = [
        {"doc_id": "D01", "section_id": "D01-2", "content": quote},
        {
            "doc_id": "D02",
            "section_id": "D02-1",
            "content": "费用报销期限为 15 天，请及时提交。",
        },
    ]
    ok, errors = validate_citations(
        answer,
        [{"doc_id": "D01", "section_id": "D01-2", "quote": quote}],
        kb,
        observed_sections=observed,
    )
    assert ok, errors


def test_observed_number_without_doc_mention_allowed(kb):
    """只要数值来自本轮工具结果，对比性表述就不应被判为编造。"""
    quote = "员工应在费用发生之日起 30 天内提交报销申请。"
    answer = "按 D01，应在 30 天内提交；另一个制度写的是 15 天。"
    observed = [
        {"doc_id": "D01", "section_id": "D01-2", "content": quote},
        {
            "doc_id": "D02",
            "section_id": "D02-1",
            "content": "费用报销期限为 15 天，请及时提交。",
        },
    ]
    ok, errors = validate_citations(
        answer,
        [{"doc_id": "D01", "section_id": "D01-2", "quote": quote}],
        kb,
        observed_sections=observed,
    )
    assert ok, errors


def test_chinese_numeral_matches_arabic_digit(kb):
    """原文「一次」与回答「1 次」应视为同一个数值。"""
    quote = "年假原则上不跨年结转，确因工作需要可申请延期一次。"
    ok, errors = validate_citations(
        "最多可以申请 1 次延期。",
        [{"doc_id": "D05", "section_id": "D05-2", "quote": quote}],
        kb,
    )
    assert ok, errors


def test_derived_item_count_allowed(kb):
    """「共 3 项」是对引用内容的计数，不是新的数值断言。"""
    quote = "差旅报销需提交行程单、发票和审批单。"
    ok, errors = validate_citations(
        "差旅报销需提交行程单、发票和审批单（共 3 项）。",
        [{"doc_id": "D03", "section_id": "D03-1", "quote": quote}],
        kb,
    )
    assert ok, errors


def test_hypothetical_example_numbers_allowed(kb):
    """说明缺口时的假设数字（例如满 10 年）不应被当成事实断言。"""
    quote = "员工入职满一年后享有 5 天带薪年假。"
    answer = (
        "员工入职满一年后享有 5 天带薪年假。"
        "知识库未提供随工龄递增的阶梯规定（如 10 天、15 天）。"
    )
    ok, errors = validate_citations(
        answer,
        [{"doc_id": "D05", "section_id": "D05-1", "quote": quote}],
        kb,
    )
    assert ok, errors


def test_unquoted_time_claim_still_rejected(kb):
    quote = "员工入职满一年后享有 5 天带薪年假。"
    ok, errors = validate_citations(
        "员工入职满一年后享有 10 天带薪年假。",
        [{"doc_id": "D05", "section_id": "D05-1", "quote": quote}],
        kb,
    )
    assert not ok
    assert any("10" in error for error in errors)


def test_number_not_in_quote_rejected(kb):
    quote = "云剪辑支持导出 MP4、MOV 等常见视频格式。"
    ok, errors = validate_citations(
        "云剪辑支持导出 8K 视频。",
        [{"doc_id": "D04", "section_id": "D04-1", "quote": quote}],
        kb,
    )
    assert not ok
    assert any("8" in error for error in errors)
