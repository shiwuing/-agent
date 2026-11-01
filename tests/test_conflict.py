from __future__ import annotations

from src.conflict import detect_conflicts, resolve_conflict


def test_detect_conflict(kb):
    hits = kb.search("报销期限是多久？", top_k=8)
    conflict = detect_conflicts(hits)
    assert conflict is not None
    assert conflict["field"] == "报销期限"
    assert {"D01", "D02"} <= {item["doc_id"] for item in conflict["items"]}


def test_version_date_alone_does_not_resolve(kb):
    hits = kb.search("报销期限是多久？", top_k=8)
    conflict = detect_conflicts(hits)
    assert resolve_conflict(conflict, "报销期限是多久？", kb.synonyms) is None


def test_unrelated_field_conflict_ignored(kb):
    question = "差旅报销需要哪些材料？"
    hits = kb.search(question, top_k=8)
    assert detect_conflicts(hits, query=question) is None


def test_scope_resolves(kb):
    question = "差旅报销期限是多久？"
    hits = kb.search(question, top_k=8)
    conflict = detect_conflicts(hits)
    resolved = resolve_conflict(conflict, question, kb.synonyms)
    assert resolved is not None
    assert resolved["doc_id"] == "D03"
    assert resolved["value"] == "15"


def test_explicit_doc_id_resolves(kb):
    question = "按 D01，报销期限是多久？"
    hits = kb.search(question, top_k=8)
    conflict = detect_conflicts(hits)
    resolved = resolve_conflict(conflict, question, kb.synonyms)
    assert resolved is not None
    assert resolved["doc_id"] == "D01"
    assert resolved["value"] == "30"


def test_generic_time_word_does_not_hijack_annual_leave(kb):
    question = "员工入职满一年有几天年假？"
    hits = kb.search(question, top_k=8)
    assert detect_conflicts(hits, query=question) is None
