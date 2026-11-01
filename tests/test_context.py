from __future__ import annotations

from src.agent.context import merge_history


def test_short_unrelated_question_is_not_merged():
    history = [{"role": "user", "content": "云剪辑支持导出哪些格式？"}]
    assert merge_history("食堂几点开门", history) == "食堂几点开门"
    assert merge_history("食堂几点开", history) == "食堂几点开"


def test_explicit_followup_keeps_topic():
    history = [{"role": "user", "content": "差旅报销需要哪些材料？"}]
    merged = merge_history("那期限呢？", history)
    assert "差旅" in merged and "报销" in merged
    assert "材料" not in merged
    assert "那期限呢" in merged


def test_ellipsis_followup_keeps_topic():
    history = [{"role": "user", "content": "云剪辑支持导出哪些格式？"}]
    merged = merge_history("还有其他格式呢？", history)
    assert "云剪辑" in merged
    assert "还有其他格式呢" in merged
