from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.kb import KnowledgeBase  # noqa: E402


@pytest.fixture(scope="session")
def kb():
    return KnowledgeBase.load(ROOT / "data")
