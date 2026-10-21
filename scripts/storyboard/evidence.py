#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""證據分級：讓「通過」只代表真的量過。

背景：本專案在《噩盡島》第一章踩過兩次同一種錯——
把「格式／hash 檢查通過」當成「可以整批開拍」，結果 11 段裡有 5 段紅光、
首 4 段出現複製人與日夜跳變。根因不是規則不夠，是**報告沒說清楚它憑什麼通過**。

三級（與 phileiny 的 SOURCES.md、Acheng 的 UNVERIFIED 制同構）：
  measured  本機實測：跑過、讀回檔案、有欄位或影格證據
  sourced   取證：照官方文件或競品實作，未經本機驗證
  inferred  推論：合理但沒驗證過

任何「沒有生成的媒體」的分段，狀態只能是 UNVERIFIED，不得顯示 PASS。
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

MEASURED = "measured"
SOURCED = "sourced"
INFERRED = "inferred"
LEVELS = (MEASURED, SOURCED, INFERRED)

LEVEL_LABELS = {
    MEASURED: "實測（本機跑過／讀回檔案）",
    SOURCED: "取證（官方文件或競品實作）",
    INFERRED: "推論（未經本機驗證）",
}

VERIFIED = "VERIFIED"
PARTIAL = "PARTIAL"
UNVERIFIED = "UNVERIFIED"

# 等級越低越不可信；media_evidence 會取最低者參與判定
LEVEL_RANK = {INFERRED: 0, SOURCED: 1, MEASURED: 2}


def label(level: str) -> str:
    return LEVEL_LABELS.get(level, level)


def grade_results(results: Iterable[Dict[str, Any]], default: str = MEASURED) -> List[Dict[str, Any]]:
    """為每筆結果補上 evidence_level（已有者不覆蓋）。

    QA 的每一項（時長／解析度／彩度／九宮格）都是從實際檔案量出來的，
    所以預設 measured；若某條規則其實只來自文件，呼叫端應自行標 sourced。
    """
    out = list(results)
    for item in out:
        if isinstance(item, dict):
            item.setdefault("evidence_level", default)
    return out


def media_evidence(
    results: List[Dict[str, Any]],
    unproduced: Optional[List[str]] = None,
    structural_issues: Optional[List[str]] = None,
    expected_total: Optional[int] = None,
    continuity_warnings: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """把「有多少東西真的被量過」變成一個明確的結論。

    規則（刻意保守）：
      - 一筆結果都沒有 → UNVERIFIED（就算退出碼是 0 也一樣）
      - 有未產出／結構異常／連續性警告／技術失敗 → PARTIAL
      - 有任何一項檢查只是 inferred（推論）→ 不得 VERIFIED
      - 全部產出、全部通過、且最低等級不是推論 → VERIFIED
    """
    unproduced = list(unproduced or [])
    structural_issues = list(structural_issues or [])
    continuity_warnings = list(continuity_warnings or [])
    if continuity_warnings:
        structural_issues += [f"continuity:{item}" for item in continuity_warnings]
    produced = len(results)
    failed = [r for r in results if not r.get("passed", False)]
    total = expected_total if expected_total is not None else produced + len(unproduced)
    unmeasured = max(0, total - produced)
    levels = [r.get("evidence_level", MEASURED) for r in results]
    lowest = min(levels, key=lambda value: LEVEL_RANK.get(value, 0)) if levels else None

    if produced == 0:
        verdict = UNVERIFIED
        note = "沒有任何已生成的影片被量測；本報告不得作為通過依據。"
    elif unproduced or structural_issues or failed or unmeasured or lowest == INFERRED:
        verdict = PARTIAL
        parts = []
        if unproduced:
            parts.append(f"{len(unproduced)} 段未產出")
        elif unmeasured:
            parts.append(f"{unmeasured} 段未進入量測")
        if failed:
            parts.append(f"{len(failed)} 段技術未通過")
        if continuity_warnings:
            parts.append(f"{len(continuity_warnings)} 項跨鏡連續性警告")
        if structural_issues:
            parts.append(f"{len(structural_issues)} 項結構異常")
        if lowest == INFERRED:
            parts.append("含未驗證(inferred)的檢查項")
        note = "部分驗證：" + "、".join(parts) + "。未產出的分段狀態為 UNVERIFIED。"
    else:
        verdict = VERIFIED
        note = "已產出的分段全部量測通過；人工審查仍為 pending。"

    return {
        "verdict": verdict,
        "produced": produced,
        "expected": total,
        "unmeasured": unmeasured,
        "failed": len(failed),
        "lowest_level": lowest,
        "unproduced": unproduced,
        "structural_issues": structural_issues,
        "unverified_segments": unproduced,
        "note": note,
        "levels": {level: label(level) for level in LEVELS},
    }


def render_line(evidence: Dict[str, Any]) -> str:
    """給 Markdown 報告用的一行結論。"""
    return (
        f"- **證據等級**：**{evidence['verdict']}** — "
        f"已量測 {evidence['produced']}/{evidence['expected']}，"
        f"技術失敗 {evidence['failed']}，未產出 {len(evidence['unverified_segments'])}。"
        f"{evidence['note']}"
    )
