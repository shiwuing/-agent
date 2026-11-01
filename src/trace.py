from __future__ import annotations

import json
from pathlib import Path


class TraceWriter:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.entries: list[dict] = []

    def log(self, step: int, action, observation, reason: str) -> None:
        self.entries.append({
            "step": step,
            "action": action.to_trace(),
            "observation": observation.to_trace(),
            "reason": reason,
            "next_action": None,
        })

    def write(self, final: dict) -> None:
        for index, entry in enumerate(self.entries):
            if index + 1 < len(self.entries):
                next_action = self.entries[index + 1]["action"]
                entry["next_action"] = next_action.get("tool") or next_action.get("type")
            else:
                entry["next_action"] = "finish"

        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as handle:
            for entry in self.entries:
                handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
            handle.write(json.dumps({"type": "final", **final}, ensure_ascii=False) + "\n")
