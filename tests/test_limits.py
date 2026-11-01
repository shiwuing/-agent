from __future__ import annotations

from helpers import run_question


def test_step_limit_returns_incomplete(kb, tmp_path):
    result = run_question(
        kb, "报销期限是多久？", max_steps=2, trace_path=tmp_path / "trace.jsonl"
    )
    assert result["status"] == "INCOMPLETE"
    assert result["steps"] == 2
    assert "步数上限" in result["gaps"][0]


def test_step_limit_one(kb, tmp_path):
    result = run_question(
        kb, "云剪辑支持导出哪些格式？", max_steps=1, trace_path=tmp_path / "trace.jsonl"
    )
    assert result["status"] == "INCOMPLETE"
    assert result["steps"] == 1
