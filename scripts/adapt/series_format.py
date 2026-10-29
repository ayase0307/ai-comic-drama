#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""series_format.py — 成片形式（長篇漫劇／短劇短集）的唯一判定來源。

預設＝長篇漫劇（longform）：以「把故事講清楚」為第一優先，整部作為一支連續長片，
每個原著關鍵事件都要交代起因→經過→結果，不以每集秒數上限去壓縮事件。
短劇短集（short）＝使用者**明確選擇**才啟用的選項（opt-in）：1–2 分鐘一集、強鉤子、
單集目標秒數 ±15% 對帳，ai-drama-hit-method lens 只在這個模式下適用。

判定順序：
1. decisions.json 的 `series_format` 定案（只能由 `h3d decide series_format ...` 寫入）；
2. project.md 的「成片形式」欄；
3. 都沒有 → longform。

僅使用 Python 標準庫，可被 scripts/、scripts/adapt/、scripts/craft/ 匯入。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

LONGFORM = "longform"
SHORT = "short"
DEFAULT_FORMAT = LONGFORM

# 短劇模式才用的單集目標秒數預設（1–2 分鐘短集的中位）。長篇模式沒有單集秒數預設。
SHORT_EPISODE_DEFAULT_SECONDS = 90.0

LABELS = {
    LONGFORM: "長篇漫劇（預設）：整部一支連續長片，每個事件交代清楚，不以單集秒數壓縮事件",
    SHORT: "短劇短集（使用者明確選擇）：每集 1–2 分鐘、強鉤子，單集目標秒數 ±15% 對帳",
}

_SHORT_WORDS = ("short", "短劇", "短集", "竪屏", "豎屏", "爆款", "微短劇")
_LONG_WORDS = ("longform", "long", "長篇", "长篇", "長片", "不分集", "連續")


def normalize(value: Any) -> Optional[str]:
    """把使用者定案的自由文字正規化成 longform／short；看不出來回 None。"""
    if value is None:
        return None
    text = str(value).strip().lower()
    if not text:
        return None
    if text in (LONGFORM, SHORT):
        return text
    if any(w in text for w in _LONG_WORDS):
        return LONGFORM
    if any(w in text for w in _SHORT_WORDS):
        return SHORT
    return None


def _decided(root: Path) -> Optional[str]:
    try:
        data = json.loads((Path(root) / "decisions.json").read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    for d in data.get("decisions", []) if isinstance(data, dict) else []:
        if isinstance(d, dict) and d.get("id") == "series_format":
            return normalize(d.get("value"))
    return None


def _project_md(root: Path) -> Optional[str]:
    try:
        text = (Path(root) / "project.md").read_text(encoding="utf-8-sig")
    except OSError:
        return None
    m = re.search(r"^-[ \t]*成片形式[ \t]*[：:][ \t]*(.*)$", text, flags=re.M)
    if not m or m.group(1).lstrip().startswith("<"):
        return None
    return normalize(m.group(1))


def project_format(root: Optional[Path]) -> str:
    """回傳專案的成片形式；沒有任何定案時回 longform（預設）。"""
    if root is None:
        return DEFAULT_FORMAT
    return _decided(root) or _project_md(root) or DEFAULT_FORMAT


def is_short(root: Optional[Path]) -> bool:
    return project_format(root) == SHORT
