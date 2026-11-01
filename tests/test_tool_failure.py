from __future__ import annotations

from helpers import run_question


def test_search_failure_retries_once_then_fails(kb, tmp_path):
    result = run_question(
        kb,
        "云剪辑支持导出哪些格式？",
        fail_tool="search_docs",
        fail_times=999,
        trace_path=tmp_path / "trace.jsonl",
    )
    assert result["status"] == "TOOL_ERROR"
    assert result["tool_calls"] == 2


def test_search_failure_then_success(kb, tmp_path):
    result = run_question(
        kb,
        "云剪辑支持导出哪些格式？",
        fail_tool="search_docs",
        fail_times=1,
        trace_path=tmp_path / "trace.jsonl",
    )
    assert result["status"] == "ANSWERED"
    assert result["tool_calls"] == 3
