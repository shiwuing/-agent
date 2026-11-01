from __future__ import annotations

from helpers import run_question


def test_clear_answer(kb, tmp_path):
    result = run_question(
        kb, "云剪辑支持导出哪些格式？", trace_path=tmp_path / "trace.jsonl"
    )
    assert result["status"] == "ANSWERED"
    assert result["citations"][0]["doc_id"] == "D04"
    assert "MP4" in result["answer"]


def test_conflict_asks_confirmation(kb, tmp_path):
    result = run_question(
        kb, "报销期限是多久？", trace_path=tmp_path / "trace.jsonl"
    )
    assert result["status"] == "NEED_CONFIRMATION"
    items = [item for conflict in result["conflicts"] for item in conflict["items"]]
    assert {"D01", "D02"} <= {item["doc_id"] for item in items}
    values = {
        item["display"]
        for item in items
        if item["doc_id"] in {"D01", "D02"}
    }
    assert values == {"30 天", "15 天"}
    assert {"D01", "D02"} <= {citation["doc_id"] for citation in result["citations"]}


def test_out_of_corpus(kb, tmp_path):
    result = run_question(
        kb, "公司食堂几点开饭？", trace_path=tmp_path / "trace.jsonl"
    )
    assert result["status"] == "INSUFFICIENT_INFO"
    assert result["gaps"]
    assert result["citations"] == []


def test_paraphrased_question(kb, tmp_path):
    result = run_question(
        kb, "费用报销最晚多久内提交？", trace_path=tmp_path / "trace.jsonl"
    )
    assert result["status"] == "NEED_CONFIRMATION"
    doc_ids = {
        item["doc_id"]
        for conflict in result["conflicts"]
        for item in conflict["items"]
    }
    assert {"D01", "D02"} <= doc_ids


def test_materials_question_not_hijacked_by_deadline_conflict(kb, tmp_path):
    result = run_question(
        kb, "差旅报销需要哪些材料？", trace_path=tmp_path / "trace.jsonl"
    )
    assert result["status"] == "ANSWERED"
    assert result["citations"][0]["section_id"] == "D03-1"
    assert "行程单" in result["answer"]


def test_followup_uses_history(kb, tmp_path):
    history = [
        {"role": "user", "content": "差旅报销需要哪些材料？"},
        {"role": "assistant", "content": "差旅报销需提交行程单、发票和审批单。"},
    ]
    result = run_question(
        kb, "那期限呢？", history=history, trace_path=tmp_path / "trace.jsonl"
    )
    assert result["status"] == "ANSWERED"
    assert result["citations"][0]["doc_id"] == "D03"
    assert "15 天" in result["answer"]


def test_unrelated_short_question_not_hijacked_by_history(kb, tmp_path):
    history = [
        {"role": "user", "content": "云剪辑支持导出哪些格式？"},
        {"role": "assistant", "content": "云剪辑支持导出 MP4、MOV 等常见视频格式。"},
    ]
    result = run_question(
        kb, "食堂几点开门", history=history, trace_path=tmp_path / "trace.jsonl"
    )
    assert result["status"] == "INSUFFICIENT_INFO"
    assert result["citations"] == []


def test_tool_failure(kb, tmp_path):
    result = run_question(
        kb,
        "云剪辑支持导出哪些格式？",
        fail_tool="search_docs",
        fail_times=999,
        trace_path=tmp_path / "trace.jsonl",
    )
    assert result["status"] == "TOOL_ERROR"
    assert result["citations"] == []


def test_retry_success(kb, tmp_path):
    result = run_question(
        kb,
        "云剪辑支持导出哪些格式？",
        fail_tool="search_docs",
        fail_times=1,
        trace_path=tmp_path / "trace.jsonl",
    )
    assert result["status"] == "ANSWERED"


def test_exception_scenario_returns_insufficient(kb, tmp_path):
    result = run_question(
        kb, "报销发票丢了怎么办？", trace_path=tmp_path / "trace.jsonl"
    )
    assert result["status"] == "INSUFFICIENT_INFO"
    assert result["gaps"]


def test_step_limit(kb, tmp_path):
    result = run_question(
        kb, "报销期限是多久？", max_steps=2, trace_path=tmp_path / "trace.jsonl"
    )
    assert result["status"] == "INCOMPLETE"
    assert result["steps"] == 2
