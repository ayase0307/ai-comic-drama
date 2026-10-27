# -*- coding: utf-8 -*-
"""專案 ID（handoff 的 project_id，schema 要求 ^[a-z0-9-]+$）。

以前直接把資料夾名轉 kebab-case：中文資料夾（「霧港」「我修的是遺忘課」）全部變成 `project`，
不同專案的 handoff／Layer 2 撞同一個 ID。這裡保留 ASCII 名稱的舊結果（相容），
只有轉完是空的時候才改用「project-<名稱雜湊前 8 碼>」，同名同 ID、可重現。
"""
from __future__ import annotations

import hashlib
import re

_ID_RE = re.compile(r"^[a-z0-9-]+$")


def slugify_project(name: str) -> str:
    """把資料夾名或標題轉成 project_id。ASCII 名稱結果與舊版完全相同。"""
    slug = re.sub(r"[^a-z0-9]+", "-", str(name or "").lower()).strip("-")
    if slug:
        return slug
    raw = str(name or "").strip()
    if not raw:
        return "project"
    return "project-" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:8]


def is_valid_project_id(value: str) -> bool:
    return bool(_ID_RE.match(str(value or "")))
