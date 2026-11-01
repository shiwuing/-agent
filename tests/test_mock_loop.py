from __future__ import annotations

import json

from helpers import run_question


def _read_trace(path):
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def _actions(trace):
    return [
        entry["action"].get("tool") or entry["action"]["type"]
        for entry in trace
        if entry.get("step")
    ]


def test_two_paths_differ_and_trace_complete(kb, tmp_path):
    run_question(
        kb, "云剪辑支持导出哪些格式？", trace_path=tmp_path / "answer.jsonl"
    )
    run_question(kb, "报销期限是多久？", trace_path=tmp_path / "conflict.jsonl")

    answer_trace = _read_trace(tmp_path / "answer.jsonl")
    conflict_trace = _read_trace(tmp_path / "conflict.jsonl")

    assert _actions(answer_trace) == ["search_docs", "read_document", "answer"]
    assert _actions(conflict_trace)[:4] == [
        "search_docs",
        "read_document",
        "read_document",
        "read_document",
    ]
    assert _actions(conflict_trace)[-1] == "ask_user"
    assert _actions(answer_trace) != _actions(conflict_trace)

    for entry in answer_trace[:-1]:
        assert entry["step"] >= 1
        assert entry["observation"]["summary"]
        assert entry["reason"]
        assert entry["next_action"] is not None


def test_observation_drives_next_action(kb, tmp_path):
    run_question(kb, "报销期限是多久？", trace_path=tmp_path / "conflict.jsonl")
    trace = _read_trace(tmp_path / "conflict.jsonl")
    search_entry = trace[0]
    assert search_entry["action"]["tool"] == "search_docs"
    assert "存在不一致" in search_entry["observation"]["summary"]
    assert search_entry["next_action"] == "read_document"
