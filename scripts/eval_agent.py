from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent.loop import AgentLoop  # noqa: E402
from src.embeddings import build_embedder_from_env  # noqa: E402
from src.kb import KnowledgeBase  # noqa: E402
from src.main import load_env_file, make_llm  # noqa: E402
from src.tools.runtime import ToolRuntime  # noqa: E402


def load_cases(path: Path, category: str | None) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    cases = payload["cases"] if isinstance(payload, dict) else payload
    if category:
        cases = [case for case in cases if case.get("category") == category]
    return cases


def trace_sections(path: Path) -> tuple[set[str], set[str], list[str]]:
    retrieved: set[str] = set()
    read: set[str] = set()
    modes: list[str] = []
    if not path.exists():
        return retrieved, read, modes
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        data = (record.get("observation") or {}).get("data")
        if not isinstance(data, dict):
            continue
        hits = data.get("hits")
        if isinstance(hits, list):
            for hit in hits:
                if isinstance(hit, dict) and hit.get("section_id"):
                    retrieved.add(hit["section_id"])
            mode = data.get("retrieval_mode")
            if mode and mode not in modes:
                modes.append(mode)
        elif data.get("section_id"):
            retrieved.add(data["section_id"])
            read.add(data["section_id"])
    return retrieved, read, modes


def evaluate_case(case: dict, result: dict, trace_path: Path) -> dict:
    expected_status = case["expected_status"]
    cited = [citation.get("section_id") for citation in result.get("citations", [])]
    retrieved, read, modes = trace_sections(trace_path)
    expected_section = case.get("expected_section")

    status_ok = result["status"] == expected_status
    section_cited = (
        expected_section in cited if expected_section else None
    )
    section_retrieved = (
        expected_section in retrieved if expected_section else None
    )
    if case["category"] == "daily":
        grounded = result["status"] == "INSUFFICIENT_INFO"
    else:
        grounded = None

    return {
        "id": case["id"],
        "category": case["category"],
        "question": case["question"],
        "expected_status": expected_status,
        "actual_status": result["status"],
        "status_ok": status_ok,
        "expected_section": expected_section,
        "section_cited": section_cited,
        "section_retrieved": section_retrieved,
        "cited_sections": cited,
        "retrieved_sections": sorted(retrieved),
        "read_sections": sorted(read),
        "retrieval_modes": modes,
        "grounded": grounded,
        "answer": result.get("answer", ""),
        "citations": result.get("citations", []),
        "gaps": result.get("gaps", []),
        "steps": result.get("steps"),
        "tool_calls": result.get("tool_calls"),
        "trace": str(trace_path.relative_to(ROOT)).replace("\\", "/"),
    }


def summarize(results: list[dict]) -> dict:
    total = len(results)
    status_ok = sum(1 for item in results if item["status_ok"])

    daily = [item for item in results if item["category"] == "daily"]
    kb = [item for item in results if item["category"] == "kb"]
    daily_grounded = sum(1 for item in daily if item["grounded"])
    daily_violations = [
        item["id"]
        for item in daily
        if item["actual_status"] != "INSUFFICIENT_INFO"
    ]

    section_cases = [item for item in kb if item["expected_section"]]
    cited_ok = sum(1 for item in section_cases if item["section_cited"])
    retrieved_ok = sum(1 for item in section_cases if item["section_retrieved"])

    return {
        "total": total,
        "status_accuracy": status_ok / total if total else 0.0,
        "daily_total": len(daily),
        "daily_grounded": daily_grounded,
        "daily_grounded_rate": daily_grounded / len(daily) if daily else 0.0,
        "daily_violations": daily_violations,
        "kb_total": len(kb),
        "kb_status_accuracy": (
            sum(1 for item in kb if item["status_ok"]) / len(kb) if kb else 0.0
        ),
        "section_cases": len(section_cases),
        "section_cited_accuracy": (
            cited_ok / len(section_cases) if section_cases else 0.0
        ),
        "section_retrieval_recall": (
            retrieved_ok / len(section_cases) if section_cases else 0.0
        ),
    }


def print_progress(index: int, total: int, item: dict) -> None:
    mark = "OK" if item["status_ok"] else "FAIL"
    extra = ""
    if item["expected_section"]:
        extra = (
            f" section_cited={item['section_cited']}"
            f" retrieved={item['section_retrieved']}"
        )
    print(
        f"[{index:02d}/{total}] {item['id']:<9} {item['actual_status']:<18} "
        f"{mark}{extra} | {item['question']}",
        flush=True,
    )
    if not item["status_ok"]:
        snippet = (item["answer"] or "; ".join(item["gaps"]))[:160].replace("\n", " ")
        print(f"    -> {snippet}", flush=True)


def main(argv=None) -> int:
    load_env_file(ROOT / ".env")

    parser = argparse.ArgumentParser(description="Agent 端到端评测")
    parser.add_argument(
        "--cases", default=str(ROOT / "examples" / "agent_eval.json")
    )
    parser.add_argument("--category", choices=["daily", "kb"], default=None)
    parser.add_argument("--ids", default=None, help="逗号分隔的用例 ID")
    parser.add_argument("--max-steps", type=int, default=8)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--output", default=None, help="结果写入路径")
    parser.add_argument("--trace-dir", default=None, help="逐题 Trace 目录")
    args = parser.parse_args(argv)

    cases = load_cases(Path(args.cases), args.category)
    if args.ids:
        wanted = {item.strip() for item in args.ids.split(",") if item.strip()}
        cases = [case for case in cases if case["id"] in wanted]
    if args.limit:
        cases = cases[: args.limit]
    if not cases:
        print("没有匹配的用例。", file=sys.stderr)
        return 1

    embedder = build_embedder_from_env()
    kb = KnowledgeBase.load(ROOT / "data", embedder=embedder)
    if kb.vector_error:
        print(f"[warn] 向量索引不可用：{kb.vector_error}", file=sys.stderr)
    if kb.vector_index is not None:
        print(f"retrieval=hybrid backend={kb.vector_index.backend}", flush=True)
    else:
        print("retrieval=keyword（未启用 Embedding）", flush=True)

    llm = make_llm("anthropic", kb)
    runtime = ToolRuntime(kb)
    traces_dir = (
        Path(args.trace_dir)
        if args.trace_dir
        else ROOT / "examples" / "traces_agent_eval"
    )
    if not traces_dir.is_absolute():
        traces_dir = ROOT / traces_dir
    traces_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict] = []
    started = time.time()
    for index, case in enumerate(cases, start=1):
        trace_path = traces_dir / f"{case['id']}.jsonl"
        loop = AgentLoop(
            kb=kb,
            llm=llm,
            runtime=runtime,
            max_steps=args.max_steps,
            trace_path=trace_path,
        )
        result = loop.run(case["question"], history=case.get("history", []))
        item = evaluate_case(case, result, trace_path)
        results.append(item)
        print_progress(index, len(cases), item)

    summary = summarize(results)
    suffix = f"_{args.category}" if args.category else ""
    output_path = (
        Path(args.output)
        if args.output
        else ROOT / "examples" / f"agent_eval_results{suffix}.json"
    )
    output_path.write_text(
        json.dumps(
            {
                "summary": summary,
                "results": results,
                "elapsed_seconds": round(time.time() - started, 1),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("\n== SUMMARY ==")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"\n结果已写入 {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
