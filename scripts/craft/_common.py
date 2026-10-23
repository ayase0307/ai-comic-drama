# -*- coding: utf-8 -*-
"""craft 腳本共用：時長讀取與保留 Agent 審查段。"""
from __future__ import annotations

from typing import Any

AGENT_HEADING = "## Agent 審查"


def duration_seconds(value: Any) -> float:
    """estimated_duration_seconds 可能是數字或 {min,max}（handoff schema）；回中位數秒數。"""
    if isinstance(value, dict):
        lo, hi = value.get("min"), value.get("max")
        nums = [float(x) for x in (lo, hi) if isinstance(x, (int, float))]
        return sum(nums) / len(nums) if nums else 0.0
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def keep_agent_section(new_text: str, target) -> str:
    """報告重跑時保留既有檔案裡 Agent 已寫的「## Agent 審查」段（不是預設提示佔位時才保留）。"""
    try:
        old = target.read_text(encoding="utf-8")
    except OSError:
        return new_text
    i = old.find(AGENT_HEADING)
    j = new_text.find(AGENT_HEADING)
    if i < 0 or j < 0:
        return new_text
    old_body = old[i:]
    if "（請 Agent" in old_body:  # 還是預設佔位，沒有 Agent 內容要保留
        return new_text
    return new_text[:j] + old_body
