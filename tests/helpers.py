from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent.loop import AgentLoop  # noqa: E402
from src.agent.mock_llm import MockLLM  # noqa: E402
from src.tools.runtime import ToolRuntime  # noqa: E402


def run_question(
    kb,
    question: str,
    history: list[dict] | None = None,
    fail_tool: str | None = None,
    fail_times: int = 0,
    max_steps: int = 8,
    trace_path=None,
) -> dict:
    llm = MockLLM(kb)
    runtime = ToolRuntime(kb, fail_tool=fail_tool, fail_times=fail_times)
    trace = trace_path or (Path(tempfile.gettempdir()) / "agent_qa_trace.jsonl")
    loop = AgentLoop(
        kb=kb,
        llm=llm,
        runtime=runtime,
        max_steps=max_steps,
        trace_path=trace,
    )
    return loop.run(question, history=history or [])
