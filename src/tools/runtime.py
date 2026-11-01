from __future__ import annotations

from ..models import ToolResult
from .read import read_document
from .search import search_docs


class ToolRuntime:
    """工具执行器，支持故障注入，异常统一转为 ToolResult。"""

    def __init__(self, kb, fail_tool: str | None = None, fail_times: int = 0):
        self.kb = kb
        self.fail_tool = fail_tool
        self.fail_times = fail_times
        self.failures = 0

    def call(self, name: str, args: dict) -> ToolResult:
        if self.fail_tool and name == self.fail_tool and self.failures < self.fail_times:
            self.failures += 1
            return ToolResult(
                ok=False,
                error=f"注入故障：{name} 模拟失败",
                summary=f"{name} 调用失败（故障注入）",
            )

        try:
            if name == "search_docs":
                return search_docs(self.kb, **args)
            if name == "read_document":
                return read_document(self.kb, **args)
            return ToolResult(ok=False, error=f"未知工具：{name}", summary="未知工具")
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, error=str(exc), summary=f"{name} 执行异常")
