from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from .agent.loop import AgentLoop
from .agent.mock_llm import MockLLM
from .kb import KnowledgeBase
from .tools.runtime import ToolRuntime

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = ROOT / "data"
DEFAULT_EXAMPLES = ROOT / "examples"


def load_case(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


_mock_fallback_warned = False


def make_llm(provider: str, kb):
    if provider == "mock":
        return MockLLM(kb)
    if provider == "anthropic":
        if not (
            os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN")
        ):
            global _mock_fallback_warned
            if not _mock_fallback_warned:
                print(
                    "[warn] 未配置 ANTHROPIC_API_KEY / ANTHROPIC_AUTH_TOKEN，"
                    "自动切换到 Mock 模式（仅验证流程，不代表真实模型效果）",
                    file=sys.stderr,
                )
                _mock_fallback_warned = True
            return MockLLM(kb)
        from .agent.llm import AnthropicLLM

        return AnthropicLLM()
    raise ValueError(f"未知 provider: {provider}")


def make_kb(args) -> KnowledgeBase:
    """按环境变量构建知识库；无 Key 时使用离线预计算向量。"""
    embedder = None
    embedding_provider = os.getenv("EMBEDDING_PROVIDER", "").strip().lower()
    if not getattr(args, "keyword_only", False):
        from .embeddings import build_embedder_from_env

        try:
            embedder = build_embedder_from_env()
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] Embedding 初始化失败：{exc}", file=sys.stderr)
        if embedder is None and embedding_provider not in {
            "", "none", "keyword", "off", "auto", "cached", "offline"
        }:
            print(
                "[warn] 已设置 EMBEDDING_PROVIDER 但未能启用，回退关键词检索",
                file=sys.stderr,
            )

    kb = KnowledgeBase.load(Path(args.data_dir), embedder=embedder)
    if kb.vector_error:
        print(
            f"[warn] 向量索引不可用，回退关键词检索：{kb.vector_error}",
            file=sys.stderr,
        )
    return kb


def run_one(
    question: str,
    history: list[dict],
    provider: str,
    fail_tool: str | None,
    fail_times: int,
    max_steps: int,
    kb: KnowledgeBase,
    trace_path: Path,
) -> dict:
    llm = make_llm(provider, kb)
    runtime = ToolRuntime(kb, fail_tool=fail_tool, fail_times=fail_times)
    loop = AgentLoop(
        kb=kb,
        llm=llm,
        runtime=runtime,
        max_steps=max_steps,
        trace_path=trace_path,
    )
    return loop.run(question, history=history)


def print_answer(result: dict) -> None:
    if result["answer"]:
        print(f"  A: {result['answer']}")
    else:
        print("  A: （无回答）")
    if result["citations"]:
        joined = ", ".join(
            f"{c['doc_id']}/{c['section_id']}" for c in result["citations"]
        )
        print(f"  citations: {joined}")
    if result["gaps"]:
        print("  gaps: " + "; ".join(result["gaps"]))
    if result["conflicts"]:
        print("  conflicts: " + json.dumps(result["conflicts"], ensure_ascii=False))
    print(f"  trace: {result['trace_file']}")


def print_result(case_name: str, result: dict) -> None:
    print(f"Q: {result['question']}")
    print(
        f"  [{case_name}] status={result['status']} "
        f"steps={result['steps']} tool_calls={result['tool_calls']}"
    )
    print_answer(result)


def run_interactive(args, provider: str) -> int:
    kb = make_kb(args)
    llm = make_llm(provider, kb)
    runtime = ToolRuntime(kb, fail_tool=args.fail_tool, fail_times=args.fail_times)
    traces_dir = DEFAULT_EXAMPLES / "traces"
    traces_dir.mkdir(parents=True, exist_ok=True)
    history: list[dict] = []
    count = 0

    retrieval = "hybrid(keyword+vector)" if kb.vector_index else "keyword"
    actual_provider = getattr(llm, "provider", provider)
    print("企业知识问答 Agent · 交互模式")
    print(
        f"provider={actual_provider}  model={getattr(llm, 'model', 'unknown')}  "
        f"retrieval={retrieval}"
    )
    if kb.embedder is not None:
        print(
            f"embedding={getattr(kb.embedder, 'display_provider', getattr(kb.embedder, 'provider', '?'))}/"
            f"{getattr(kb.embedder, 'model', '?')}"
        )
    print("直接输入问题回车；命令：reset 清空历史，help 帮助，exit 退出。")

    while True:
        try:
            question = input("\nQ> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见。")
            break

        if not question:
            continue
        lowered = question.lower()
        if lowered in {"exit", "quit", "q"}:
            print("再见。")
            break
        if lowered == "reset":
            history.clear()
            print("已清空对话历史。")
            continue
        if lowered == "help":
            print("命令：reset 清空历史，exit 退出；直接输入问题即可。")
            continue

        count += 1
        stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
        trace_path = traces_dir / f"interactive_{stamp}_{count:02d}.jsonl"
        loop = AgentLoop(
            kb=kb,
            llm=llm,
            runtime=runtime,
            max_steps=args.max_steps,
            trace_path=trace_path,
        )
        result = loop.run(question, history=history)
        print(
            f"  status={result['status']} steps={result['steps']} "
            f"tool_calls={result['tool_calls']}"
        )
        print_answer(result)
        history.append({"role": "user", "content": question})
        history.append({
            "role": "assistant",
            "content": result["answer"] or f"[{result['status']}] " + "; ".join(result["gaps"]),
        })
    return 0


def load_env_file(path: Path = ROOT / ".env") -> None:
    """极简 .env 加载器，避免本地 Mock 模式依赖 python-dotenv。"""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def main(argv=None) -> int:
    load_env_file(ROOT / ".env")
    try:
        from dotenv import load_dotenv

        load_dotenv(override=False)
    except Exception:  # noqa: BLE001
        pass

    parser = argparse.ArgumentParser(description="企业知识问答 Agent")
    parser.add_argument("--question", help="用户问题")
    parser.add_argument("--history", help="对话历史 JSON 数组字符串")
    parser.add_argument("--case", help="用例 JSON 路径")
    parser.add_argument("--all-cases", action="store_true", help="运行全部用例")
    parser.add_argument("--interactive", action="store_true", help="进入连续问答模式")
    parser.add_argument("--keyword-only", action="store_true", help="强制只用关键词检索")
    parser.add_argument("--mock", action="store_true", help="强制使用离线 Mock")
    parser.add_argument("--provider", choices=["mock", "anthropic"], default=None)
    parser.add_argument("--max-steps", type=int, default=8)
    parser.add_argument("--fail-tool", default=None, help="故障注入的工具名")
    parser.add_argument("--fail-times", type=int, default=0)
    parser.add_argument("--data-dir", default=str(DEFAULT_DATA))
    parser.add_argument("--out", default=None)
    parser.add_argument("--trace", default=None)
    parser.add_argument("--out-dir", default=None, help="批量/单例输出目录")
    parser.add_argument("--trace-dir", default=None, help="批量/单例 Trace 目录")
    args = parser.parse_args(argv)

    provider = (
        "mock"
        if args.mock
        else (args.provider or os.getenv("LLM_PROVIDER", "anthropic"))
    )

    if args.interactive:
        return run_interactive(args, provider)

    kb = make_kb(args)

    if args.all_cases:
        inputs = sorted((DEFAULT_EXAMPLES / "inputs").glob("*.json"))
        outputs_dir = (
            Path(args.out_dir) if args.out_dir else DEFAULT_EXAMPLES / "outputs"
        )
        traces_dir = (
            Path(args.trace_dir) if args.trace_dir else DEFAULT_EXAMPLES / "traces"
        )
        outputs_dir.mkdir(parents=True, exist_ok=True)
        traces_dir.mkdir(parents=True, exist_ok=True)

        summary: list[dict] = []
        failed = 0
        for case_path in inputs:
            case = load_case(case_path)
            name = case.get("name", case_path.stem)
            case_provider = (
                "mock" if case.get("provider", "mock") == "mock" else provider
            )
            if args.mock:
                case_provider = "mock"

            result = run_one(
                question=case["question"],
                history=case.get("history", []),
                provider=case_provider,
                fail_tool=case.get("fail_tool"),
                fail_times=case.get("fail_times", 0),
                max_steps=case.get("max_steps", args.max_steps),
                kb=kb,
                trace_path=traces_dir / f"{name}.jsonl",
            )
            (outputs_dir / f"{name}.json").write_text(
                json.dumps(result, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print_result(name, result)

            expected = case.get("expected_status")
            passed = expected is None or result["status"] == expected
            if not passed:
                failed += 1
            try:
                trace_ref = str((traces_dir / f"{name}.jsonl").relative_to(ROOT))
            except ValueError:
                trace_ref = str(traces_dir / f"{name}.jsonl")
            summary.append({
                "name": name,
                "expected_status": expected,
                "actual_status": result["status"],
                "passed": passed,
                "trace": trace_ref.replace("\\", "/"),
            })

        (outputs_dir / "_summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\nSummary: {len(summary) - failed}/{len(summary)} passed")
        return 0 if failed == 0 else 1

    if args.case:
        case_path = Path(args.case)
        case = load_case(case_path)
        name = case.get("name", case_path.stem)
        case_provider = (
            "mock" if case.get("provider", "mock") == "mock" else provider
        )
        if args.mock:
            case_provider = "mock"

        out_base = Path(args.out_dir) if args.out_dir else DEFAULT_EXAMPLES / "outputs"
        trace_base = (
            Path(args.trace_dir) if args.trace_dir else DEFAULT_EXAMPLES / "traces"
        )
        out_path = Path(args.out) if args.out else out_base / f"{name}.json"
        trace_path = (
            Path(args.trace) if args.trace else trace_base / f"{name}.jsonl"
        )
        out_path.parent.mkdir(parents=True, exist_ok=True)
        trace_path.parent.mkdir(parents=True, exist_ok=True)

        result = run_one(
            question=case["question"],
            history=case.get("history", []),
            provider=case_provider,
            fail_tool=case.get("fail_tool"),
            fail_times=case.get("fail_times", 0),
            max_steps=case.get("max_steps", args.max_steps),
            kb=kb,
            trace_path=trace_path,
        )
        out_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print_result(name, result)
        expected = case.get("expected_status")
        return 0 if expected is None or result["status"] == expected else 1

    if not args.question:
        parser.error("需要 --question 或 --case 或 --all-cases")

    history = json.loads(args.history) if args.history else []
    trace_path = (
        Path(args.trace)
        if args.trace
        else DEFAULT_EXAMPLES / "traces" / "manual.jsonl"
    )
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    result = run_one(
        question=args.question,
        history=history,
        provider=provider,
        fail_tool=args.fail_tool,
        fail_times=args.fail_times,
        max_steps=args.max_steps,
        kb=kb,
        trace_path=trace_path,
    )
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    print_result("manual", result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
