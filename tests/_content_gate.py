"""測試輔助：階段 0–3 內容門禁的開關。

下游階段（4–7、收件匣、自動核准）的測試用極簡 fixture 走過階段 0–3，
它們要測的不是階段 0–3 的內容，所以在模組層級把 stage_content_checks 關掉。
階段 0–3 內容門禁本身由 tests/test_stage_content_checks.py 覆蓋。
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import stage_content_checks  # noqa: E402

_patcher = mock.patch.object(stage_content_checks, "content_errors", return_value=[])


def disable() -> None:
    _patcher.start()


def enable() -> None:
    _patcher.stop()
