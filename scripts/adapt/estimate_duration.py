#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
estimate_duration.py — 漫劇劇本片長區間與小說原文體量反推片長審計器

成片形式（`series_format`，見 series_format.py）：
- 長篇漫劇（預設）：整部一支連續長片，以「把故事講清楚」為先；總片長依事件數與交代需求估算，
  沒有「單集秒數」預設，也不因秒數超出而建議壓縮事件。
- 短劇短集（使用者明確選擇 `--format short` 或 `h3d decide series_format short`）：沿用單集目標秒數
  （預設 90s）±15% 對帳與「預估片長 > 單集目標 × 2」的階段 0 阻斷門禁。

支援三種模式：
1. 劇本模式（預設）：
   - 估算劇本每場與總體時長區間（分題材語速區間、句間氣口、情緒停頓、動作節拍與換場建立時間）；
   - 審計單句 TTS 字數限制（>28 字警告，>35 字錯誤）；
   - 有給目標時長時驗證 ±15% 區間（短劇模式預設 90s；長篇模式只有使用者給了才比）。
2. 小說模式（--novel）：
   - 原文體量反推片長（純念秒數 = 台詞字數 / 4，總片長 = 純念秒數 * 1.6）；
   - 短劇模式：若預估片長 > 單集目標 * 2，觸發 [STAGE0_VOLUME_GATE_BLOCK] 阻斷提示；
     長篇模式：只報總長（分鐘），使用者給了整部目標秒數才比對；
   - 自動試算四大台詞政策（① 逐字保留、② 重點句 20%、③ 影視改寫預算上限、④ 純旁白）。
3. 事件模式（--events adapt/source.json）：
   - 依原著事件數與每個事件的交代需求（起因／經過／結果＋動機＋時地轉換）估算總片長，
     而不是「集數 × 固定秒數」。

僅使用 Python 標準庫。
"""

from __future__ import annotations

import argparse
import io
import json
import math
import os
from pathlib import Path
import re
import string
import sys
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

# 確保 Windows 終端輸出 UTF-8
# 用 reconfigure 而不是換掉 sys.stdout／sys.stderr：被別的腳本 import（例如門禁在同一個行程裡
# 呼叫 compare_adaptation → estimate_duration）時，換掉的舊物件被回收會關掉底層 buffer，
# Windows 上會出現「lost sys.stderr」整個行程掛掉。
if sys.platform.startswith("win"):
    for _stream in (sys.stdout, sys.stderr):
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="replace")

from validate_structure import parse_and_validate_script
from series_format import LONGFORM, SHORT, SHORT_EPISODE_DEFAULT_SECONDS, project_format
from event_coverage import required_beats

# 各題材預設語速區間（字/秒）：[慢速/沉澱 R_min, 快速/緊湊 R_max]
GENRE_SPEECH_RATES: Dict[str, Tuple[float, float]] = {
    "xuanhuan_revenge": (4.2, 5.2),
    "romance_emotional": (4.3, 5.5),
    "mystery_thriller": (4.0, 5.0),
    "comedy_slice_of_life": (3.8, 4.5),
    "wuxia_action": (4.2, 5.2),
    "healing_literary": (3.8, 4.5),
}

# v2 依角色估時（出處 references/pacing-dialogue-evidence.md）
ROLE_CHARS_PER_SEC: Dict[str, float] = {"male_lead": 4.0, "female": 4.5, "narration": 5.5}
_NARRATION_MARKS = ("VO", "V.O", "O.S", "旁白", "內心", "OS")


def speaker_rate(speaker: str, male_leads: Optional[set] = None) -> float:
    """男主（--male-lead 指定）4.0；旁白／畫外／內心 5.5；其餘 4.5。"""
    sp = speaker or ""
    if any(m in sp.upper() for m in _NARRATION_MARKS):
        return ROLE_CHARS_PER_SEC["narration"]
    if male_leads and any(n and n in sp for n in male_leads):
        return ROLE_CHARS_PER_SEC["male_lead"]
    return ROLE_CHARS_PER_SEC["female"]


_ASCII_PUNCT = frozenset(string.punctuation)


def count_spoken_chars(text: str) -> int:
    """計算實際發音之非空白、非標點字元數（與 speech_utils.py 完全一致）。"""
    return len([
        ch
        for ch in text
        if not (ch.isspace() or ch in _ASCII_PUNCT or unicodedata.category(ch).startswith("P"))
    ])


def estimate_action_seconds(action_text: str) -> Tuple[float, float]:
    """依動作行字數與複合動作動詞估算所需視覺秒數區間 [min_s, max_s]。"""
    char_len = len(action_text)
    if char_len <= 18:
        return (1.6, 2.8)
    elif char_len <= 40:
        return (2.2, 4.0)
    else:
        return (3.2, 5.5)


def estimate_script_duration(
    script_text: str,
    genre_mode: str = "mystery_thriller",
    target_seconds: Optional[float] = None,
    h3_mode: bool = False,
    series_format: str = LONGFORM,
    male_leads: Optional[set] = None,
) -> Dict[str, Any]:
    """計算劇本每場與總體時長區間，並檢查單句 TTS 字數限制與 H3 實戰台詞預算。"""
    parsed = parse_and_validate_script(script_text)
    r_min, r_max = GENRE_SPEECH_RATES.get(genre_mode, (3.2, 4.0))

    errors: List[str] = []
    warnings: List[str] = []
    scene_estimates: List[Dict[str, Any]] = []

    total_min = 0.0
    total_max = 0.0
    total_spoken_chars = 0
    h3_speech_raw = 0.0
    max_single_line_chars = 0

    for sc in parsed["scenes"]:
        sc_min = 1.5  # 場景建立與轉場最小時間
        sc_max = 2.5  # 場景建立與轉場最大時間
        sc_chars = 0

        for act in sc["actions"]:
            a_min, a_max = estimate_action_seconds(act["text"])
            sc_min += a_min
            sc_max += a_max

        for dlg in sc["dialogues"]:
            c_count = count_spoken_chars(dlg["text"])
            sc_chars += c_count
            total_spoken_chars += c_count
            h3_speech_raw += c_count / speaker_rate(dlg.get("speaker", ""), male_leads)
            if c_count > max_single_line_chars:
                max_single_line_chars = c_count

            # 檢查單句字數上限（28字警告，35字錯誤）
            if c_count > 35:
                errors.append(
                    f"[DIALOGUE_OVER_35_CHARS] 第 {dlg['line_no']} 行 ({sc['scene_num']} {dlg['speaker']}): "
                    f"單句發音字數達 {c_count} 字（超過 35 字硬上限，TTS 韻律與單鏡對嘴易崩壞）"
                )
            elif c_count > 28:
                warnings.append(
                    f"[DIALOGUE_OVER_28_CHARS] 第 {dlg['line_no']} 行 ({sc['scene_num']} {dlg['speaker']}): "
                    f"單句發音字數為 {c_count} 字（超過 28 字 10 秒單鏡安全線，建議拆句或切反應鏡頭）"
                )

            # H3 實戰台詞預算檢查（v2）：單氣口建議 ≤18 字，硬上限 25 字
            if h3_mode and c_count > 35:
                errors.append(
                    f"[H3_LINE_HARD_LIMIT] 第 {dlg['line_no']} 行 ({sc['scene_num']} {dlg['speaker']}): "
                    f"單句發音字數為 {c_count} 字（超過硬上限 35 字，必須拆句）"
                )
            elif h3_mode and c_count > 18:
                warnings.append(
                    f"[H3_LINE_TOO_LONG] 第 {dlg['line_no']} 行 ({sc['scene_num']} {dlg['speaker']}): "
                    f"單句發音字數為 {c_count} 字（超過建議 18 字，建議拆為短句或切特寫反應）"
                )

            # 發音時間 + 基礎氣口
            speech_min = (c_count / r_max) + 0.35
            speech_max = (c_count / r_min) + 0.65

            # 若包含省略號或情緒停頓提示，增加表演停頓
            if "……" in dlg["text"] or "..." in dlg["text"] or dlg["note"]:
                speech_min += 0.35
                speech_max += 0.80

            sc_min += speech_min
            sc_max += speech_max

        sc_min = round(sc_min, 1)
        sc_max = round(sc_max, 1)
        total_min += sc_min
        total_max += sc_max

        scene_estimates.append(
            {
                "scene_num": sc["scene_num"],
                "location": sc["location"],
                "spoken_chars": sc_chars,
                "action_beats": len(sc["actions"]),
                "dialogue_lines": len(sc["dialogues"]),
                "estimated_seconds": {"min": sc_min, "max": sc_max},
            }
        )

    total_min = round(total_min, 1)
    total_max = round(total_max, 1)
    mid_seconds = round((total_min + total_max) / 2.0, 1)

    # H3 實戰台詞預算指標計算
    h3_speech_seconds = round(h3_speech_raw, 1)  # v2：依角色語速（男主 4.0／女角 4.5／旁白 5.5）
    base_dur = target_seconds if (target_seconds and target_seconds > 0) else mid_seconds
    h3_speech_ratio = round(h3_speech_seconds / base_dur, 3) if base_dur > 0 else 0.0

    # v2：文戲說話佔比目標 60–75%；>80% 才 WARN（只警告不擋）；過低也警告
    if h3_mode and h3_speech_ratio > 0.80:
        warnings.append(
            f"[H3_SPEECH_RATIO_EXCEEDED] H3 純說話秒數佔比達 {h3_speech_ratio:.1%} "
            f"({h3_speech_seconds}s/{base_dur}s)，超過 80%（目標 60–75%；建議切反應鏡或插動作拍）"
        )
    elif h3_mode and h3_speech_ratio < 0.60:
        warnings.append(
            f"[H3_SPEECH_RATIO_LOW] H3 純說話秒數佔比僅 {h3_speech_ratio:.1%} "
            f"({h3_speech_seconds}s/{base_dur}s)，低於目標 60–75%（畫面可能大量無人說話，檢查空白與無台詞鏡）"
        )

    budget_status = "PASS"
    compression_advice: List[str] = []

    if target_seconds is not None and target_seconds > 0:
        allowed_low = round(target_seconds * 0.85, 1)
        allowed_high = round(target_seconds * 1.15, 1)
        if total_min > allowed_high:
            budget_status = "OVER_BUDGET"
            warnings.append(
                f"[DURATION_OVER_BUDGET] 預估時長區間 [{total_min}s, {total_max}s] 超出目標 {target_seconds}s (+15% 上限 {allowed_high}s)"
            )
            if series_format == SHORT:
                compression_advice = [
                    "先判斷超出的是「因果必要」還是「冗餘」，再三選一：",
                    "A. 冗餘 → 刪重複解說、合併重複反應節拍、精簡長句（嚴禁刪 MUST_KEEP 核心因果事件）",
                    "B. 因果必要 → 於場次邊界拆成上下集（每集都要有自己的目標、阻礙與結尾鉤子），不要壓縮分鏡",
                    "C. 因果必要且不宜拆 → 接受實際長度，並在 handoff 該集寫入 accepted_duration_seconds",
                ]
            else:
                compression_advice = [
                    "長篇漫劇模式：把故事講清楚優先，不為了秒數壓縮事件。",
                    "A. 多出的是事件交代（起因／經過／結果、動機、時地轉換）→ 接受實際長度，在 handoff 寫入 accepted_duration_seconds",
                    "B. 多出的是冗餘（重複解說、重複反應節拍）→ 只刪冗餘，不刪任何事件的交代鏡頭",
                    "C. 使用者明確要求分集時，才於完整劇情單元的邊界切集",
                ]
        elif total_max < allowed_low:
            budget_status = "UNDER_BUDGET"
            warnings.append(
                f"[DURATION_UNDER_BUDGET] 預估時長區間 [{total_min}s, {total_max}s] 低於目標 {target_seconds}s (-15% 下限 {allowed_low}s)"
            )

    passed = len(errors) == 0 and budget_status == "PASS"

    return {
        "status": "PASS" if passed else ("WARN" if len(errors) == 0 else "FAIL"),
        "series_format": series_format,
        "genre_mode": genre_mode,
        "speech_rate_assumption_chars_per_sec": {"min": r_min, "max": r_max},
        "target_seconds": target_seconds,
        "total_spoken_chars": total_spoken_chars,
        "estimated_total_seconds": {"min": total_min, "max": total_max, "mid": mid_seconds},
        "budget_status": budget_status,
        "h3_speech_seconds": h3_speech_seconds,
        "h3_speech_ratio": h3_speech_ratio,
        "h3_audit": {
            "h3_mode": h3_mode,
            "spoken_chars": total_spoken_chars,
            "speech_seconds": h3_speech_seconds,
            "speech_ratio": h3_speech_ratio,
            "max_line_chars": max_single_line_chars,
            "passed": (h3_speech_ratio <= 0.80 and max_single_line_chars <= 35),
        },
        "scenes": scene_estimates,
        "compression_advice": compression_advice,
        "errors": errors,
        "warnings": warnings,
    }


def extract_novel_dialogues(text: str) -> List[str]:
    """提取小說中的所有引號對白。支援「...」、『...』、“...”、\"...\"。"""
    pattern = re.compile(r"「([^」]+)」|『([^』]+)』|“([^”]+)”|\"([^\"]+)\"")
    results = []
    for m in pattern.finditer(text):
        for g in m.groups():
            if g:
                results.append(g)
    return results


def estimate_novel_duration(
    novel_text: str,
    target_seconds: Optional[float] = None,
    genre_mode: str = "xuanhuan_revenge",
    series_format: str = LONGFORM,
) -> Dict[str, Any]:
    """執行階段 0 原文體量反推片長與四大台詞政策試算。

    短劇模式：target_seconds＝單集目標（省略用 90s），超過 2 倍觸發阻斷門禁並換算集數。
    長篇模式（預設）：target_seconds＝整部目標（選填）；沒給就只報總長，不換算集數、不阻斷。"""
    if series_format == SHORT and not target_seconds:
        target_seconds = SHORT_EPISODE_DEFAULT_SECONDS
    # 略過可能的標題行
    lines = novel_text.splitlines()
    body_lines = [l for l in lines if not l.strip().startswith("#")]
    body_text = "\n".join(body_lines)

    total_chars = count_spoken_chars(body_text)
    dialogues = extract_novel_dialogues(body_text)
    dialogue_chars = sum(count_spoken_chars(d) for d in dialogues)
    narrative_chars = max(0, total_chars - dialogue_chars)
    dialogue_ratio = round((dialogue_chars / total_chars * 100), 1) if total_chars > 0 else 0.0

    # 階段 0 核心公式：
    # 純念台詞秒數 = 台詞字數 / 4.0
    # 總片長估算 = 純念台詞秒數 * 1.6
    speech_rate = 4.0
    action_factor = 1.6
    speech_seconds = round(dialogue_chars / speech_rate, 1)
    estimated_total_seconds = round(speech_seconds * action_factor, 1)

    # 阻斷門禁判定：估算片長 > 目標片長 * 2（長篇模式沒有目標時不判定）
    is_blocked = bool(target_seconds) and estimated_total_seconds > (target_seconds * 2.0)
    gate_status = "BLOCKED" if is_blocked else "PASS"
    scope = "單集" if series_format == SHORT else "整部"

    gate_messages: List[str] = []
    if is_blocked:
        gate_messages.append(
            f"[STAGE0_VOLUME_GATE_BLOCK] 原始小說台詞推算總片長 {estimated_total_seconds}s "
            f"超過目標{scope}時長 {target_seconds}s 的 2 倍（門檻 {target_seconds * 2.0}s）！"
            f"依規範強制在階段 0 停下，嚴禁擅自動筆直接分鏡！"
        )

    def _episodes(total: float) -> int:
        # 只有短劇模式（或使用者明確給了單集目標）才換算集數；長篇模式整部是一支連續長片。
        if series_format != SHORT or not target_seconds:
            return 1
        return max(1, math.ceil(total / target_seconds))

    # 四大台詞政策試算
    # 政策 ①：100% 逐字保留
    p1_episodes = _episodes(estimated_total_seconds)
    policy_1 = {
        "policy_id": "policy_1_verbatim_100",
        "name": "① 原文逐字保留 (100%)",
        "dialogue_retention_ratio": 1.0,
        "retained_dialogue_chars": dialogue_chars,
        "speech_seconds": speech_seconds,
        "estimated_total_seconds": estimated_total_seconds,
        "episodes_needed": p1_episodes,
        "avg_episode_seconds": round(estimated_total_seconds / p1_episodes, 1),
        "evaluation": "❌ 嚴重撞死 H3 對白預算；每 15 秒需塞大量台詞導致口型崩壞與 ASR 吞字；片長會大幅拉長。",
    }

    # 政策 ②：只留重點句 (保留 20% 原著對白，推薦)
    p2_chars = round(dialogue_chars * 0.20)
    p2_speech_sec = round(p2_chars / speech_rate, 1)
    p2_total_sec = round(p2_speech_sec * action_factor, 1)
    p2_episodes = _episodes(p2_total_sec)
    policy_2 = {
        "policy_id": "policy_2_key_lines_20",
        "name": "② 只留重點句，其餘可刪 (約 20% 對白，推薦)",
        "dialogue_retention_ratio": 0.20,
        "retained_dialogue_chars": p2_chars,
        "speech_seconds": p2_speech_sec,
        "estimated_total_seconds": p2_total_sec,
        "episodes_needed": p2_episodes,
        "avg_episode_seconds": round(p2_total_sec / p2_episodes, 1),
        "evaluation": "✅ 推薦方案！大刀砍去冗長鋪墊與功能性寒暄，保留推動情節之金句；節奏緊湊且在 H3 對白預算安全線內。",
    }

    # 政策 ③：全部改寫為影視對白（短劇：依單集目標反推；長篇：依體量估算的整部片長反推）
    # 安全說話時長上限 = 片長 * 60%；對白字數上限 = (片長 * 60%) * 4.0
    budget_base = target_seconds or estimated_total_seconds
    safe_speech_sec_per_ep = round(budget_base * 0.60, 1)
    safe_dialogue_chars_per_ep = round(safe_speech_sec_per_ep * speech_rate)
    policy_3 = {
        "policy_id": "policy_3_cinematic_rewrite",
        "name": "③ 全部改寫為影視對白 (重構口語短句)",
        "single_episode_dialogue_char_budget_max": safe_dialogue_chars_per_ep,
        "single_episode_speech_sec_max": safe_speech_sec_per_ep,
        "dialogue_time_ratio_cap": "≤ 60% 片長",
        "budget_scope": scope,
        "evaluation": f"✅ 自由度最高；打破原著長句重構為視聽語言，{scope}對白上限約 {safe_dialogue_chars_per_ep} 字（說話 ≤ 60% 片長），留足動作與環境特效時間。",
    }

    # 政策 ④：無台詞純旁白
    policy_4 = {
        "policy_id": "policy_4_narration_only",
        "name": "④ 無台詞純旁白 (默片/畫面推進)",
        "dialogue_retention_ratio": 0.0,
        "retained_dialogue_chars": 0,
        "evaluation": "✅ 角色閉唇不語；完全規避 H3 人物嘴型對齊與 ASR 模糊問題，依畫面解說與音效推進。",
    }

    return {
        "status": gate_status,
        "series_format": series_format,
        "genre_mode": genre_mode,
        "target_seconds": target_seconds,
        "target_seconds_per_episode": target_seconds if series_format == SHORT else None,
        "metrics": {
            "total_chars": total_chars,
            "dialogue_count": len(dialogues),
            "dialogue_chars": dialogue_chars,
            "narrative_chars": narrative_chars,
            "dialogue_ratio": dialogue_ratio,
        },
        "stage0_formula": {
            "speech_rate_chars_per_sec": speech_rate,
            "action_expansion_factor": action_factor,
            "pure_speech_seconds": speech_seconds,
            "estimated_total_seconds": estimated_total_seconds,
            "block_threshold_seconds": (target_seconds * 2.0) if target_seconds else None,
        },
        "gate_messages": gate_messages,
        "policies_projection": {
            "policy_1": policy_1,
            "policy_2": policy_2,
            "policy_3": policy_3,
            "policy_4": policy_4,
        },
    }


# 事件模式：每個交代要素（起因／經過／結果／動機）大約需要一個 H3 片段的戲（8–15 秒，H3 單段上限 15 秒）；
# 時間／地點轉換另需建立鏡頭（3–6 秒）。分級決定這個事件在改編裡要演幾個要素。
EVENT_BEAT_SECONDS: Tuple[float, float] = (8.0, 15.0)
EVENT_TRANSITION_SECONDS: Tuple[float, float] = (3.0, 6.0)


def estimate_event_based_duration(
    source_data: Dict[str, Any],
    episodes: Optional[int] = None,
    series_format: str = LONGFORM,
) -> Dict[str, Any]:
    """依原著事件數與交代需求估算總片長（不是集數 × 固定秒數）。

    - MUST_KEEP／KEEP_IF_POSSIBLE／REORDER：所有需交代要素都要演（預設起因、經過、結果，外加動機／時地）。
    - MERGE：併入其他事件，只算 1 個要素；COMPRESS：只演結果，算 1 個要素；REMOVE：0。
    - 事件若標了 dialogue_chars（保留台詞字數），以「字數 ÷ 4 × 1.6」與要素秒數取大者。
    episodes 只有使用者明確要求分集（或短劇模式）時才用來換算平均每集秒數。"""
    units = [u for u in source_data.get("story_units", []) or [] if isinstance(u, dict)]
    must_keep_ids = {str(x) for x in source_data.get("must_keep", []) or []}
    rows: List[Dict[str, Any]] = []
    total_min = total_max = 0.0
    total_beats = 0
    for u in units:
        uid = str(u.get("unit_id", ""))
        grade = "MUST_KEEP" if uid in must_keep_ids else str(u.get("expected_grade") or "KEEP_IF_POSSIBLE").upper()
        beats = required_beats(u)
        transition = "時地" in beats
        story_beats = [b for b in beats if b != "時地"]
        if grade == "REMOVE":
            n_beats, transition = 0, False
        elif grade in ("MERGE", "COMPRESS"):
            n_beats = 1
        else:
            n_beats = len(story_beats)
        lo = n_beats * EVENT_BEAT_SECONDS[0] + (EVENT_TRANSITION_SECONDS[0] if transition else 0.0)
        hi = n_beats * EVENT_BEAT_SECONDS[1] + (EVENT_TRANSITION_SECONDS[1] if transition else 0.0)
        chars = u.get("dialogue_chars")
        if isinstance(chars, (int, float)) and chars > 0 and grade != "REMOVE":
            speech_total = chars / 4.0 * 1.6
            lo, hi = max(lo, speech_total * 0.85), max(hi, speech_total * 1.15)
        lo, hi = round(lo, 1), round(hi, 1)
        total_min += lo
        total_max += hi
        total_beats += n_beats
        rows.append({
            "unit_id": uid, "summary": u.get("summary", ""), "grade": grade,
            "exposition_beats": story_beats if n_beats == len(story_beats) else story_beats[-1:] if n_beats else [],
            "time_place_shift": transition, "estimated_seconds": {"min": lo, "max": hi},
        })
    total_min, total_max = round(total_min, 1), round(total_max, 1)
    mid = round((total_min + total_max) / 2.0, 1)
    res: Dict[str, Any] = {
        "status": "PASS",
        "mode": "events",
        "series_format": series_format,
        "event_count": len(units),
        "kept_event_count": sum(1 for r in rows if r["grade"] != "REMOVE"),
        "exposition_beats_total": total_beats,
        "beat_seconds_assumption": {"min": EVENT_BEAT_SECONDS[0], "max": EVENT_BEAT_SECONDS[1]},
        "estimated_total_seconds": {"min": total_min, "max": total_max, "mid": mid},
        "estimated_total_minutes": round(mid / 60.0, 1),
        "events": rows,
    }
    if episodes and episodes > 1:
        res["episodes"] = episodes
        res["avg_episode_seconds"] = round(mid / episodes, 1)
        res["episode_note"] = "集數由使用者指定；每集應在完整劇情單元的邊界切，秒數只是平均值、不是上限。"
    return res


def find_project_root(path: Path) -> Optional[Path]:
    for parent in Path(path).resolve().parents:
        if (parent / "decisions.json").exists() or (parent / "project.md").exists():
            return parent
    return None


def project_genre(root: Optional[Path]) -> Optional[str]:
    if root is None:
        return None
    try:
        m = re.search(r"genre_mode[：:]\s*([a-z_]+)", (root / "project.md").read_text(encoding="utf-8"))
        if m and m.group(1) in GENRE_SPEECH_RATES:
            return m.group(1)
    except OSError:
        pass
    for cand in (root / "adapt" / "source.json", root / "adapt" / "bible.json"):
        try:
            g = json.loads(cand.read_text(encoding="utf-8")).get("genre_mode")
            if g in GENRE_SPEECH_RATES:
                return g
        except (OSError, ValueError):
            pass
    return None


def genre_unconfirmed(root: Optional[Path]) -> bool:
    """project.md 的 genre_mode 還是範本佔位符（<a | b | …>）時，source.json 裡的值只是 init 骨架預設，不算定案。"""
    if root is None:
        return False
    try:
        text = (root / "project.md").read_text(encoding="utf-8")
    except OSError:
        return False
    m = re.search(r"genre_mode[：:]\s*(\S.*)", text)
    return bool(m and m.group(1).lstrip().startswith("<"))


def dialogue_policy_decided(root: Optional[Path]) -> bool:
    if root is None:
        return False
    try:
        data = json.loads((root / "decisions.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return any(d.get("id") == "dialogue_policy" and d.get("value") for d in data.get("decisions", []))


def main() -> int:
    parser = argparse.ArgumentParser(description="估算漫劇劇本時長區間或小說原文體量反推片長")
    parser.add_argument("--script", type=str, default=None, help="漫劇劇本路徑（或在 --novel 下作為小說路徑）")
    parser.add_argument("--novel-file", type=str, default=None, help="小說章節檔案路徑（開啟小說體量反推）")
    parser.add_argument("--novel", action="store_true", help="開啟小說原文體量反推片長與階段 0 阻斷檢查")
    parser.add_argument("--genre", type=str, default=None, help="題材模式代碼（省略時讀專案 project.md／source.json 的 genre_mode，都沒有才用 xuanhuan_revenge）")
    parser.add_argument("--events", type=str, default=None, help="原著事件清單 source.json：依事件數與交代需求估算總片長")
    parser.add_argument("--episodes", type=int, default=None, help="事件模式：使用者明確要求分集時的集數（只換算平均，不設上限）")
    parser.add_argument("--format", choices=[LONGFORM, SHORT], default=None, dest="series_format",
                        help="成片形式：longform 長篇漫劇（預設，讀 decisions.json 的 series_format）｜short 短劇短集（使用者明確選擇才用）")
    parser.add_argument("--target-seconds", type=float, default=None,
                        help="目標秒數：短劇模式＝單集目標（省略用 90s）；長篇模式＝整部目標（選填，不給就不做預算比對）")
    parser.add_argument("--h3", action="store_true", help="開啟 H3 漫劇台詞預算嚴格檢查（4字/秒、單句≤15字、說話秒數佔比≤60%%）")
    parser.add_argument("--h3-strict", action="store_true", dest="h3", help="同 --h3")
    parser.add_argument("--male-lead", action="append", default=[], dest="male_leads",
                        help="男主角色名（可重複）；其台詞以 4.0 字/秒估時，其餘 4.5、旁白 5.5")
    parser.add_argument("--json", action="store_true", help="輸出 JSON 格式")
    args = parser.parse_args()

    # 事件模式：依事件數與交代需求估總長
    if args.events:
        ev_path = Path(args.events)
        if not ev_path.exists():
            print(f"[錯誤] 找不到檔案：{ev_path}", file=sys.stderr)
            return 1
        fmt = args.series_format or project_format(find_project_root(ev_path))
        res = estimate_event_based_duration(json.loads(ev_path.read_text(encoding="utf-8")),
                                            episodes=args.episodes, series_format=fmt)
        if args.json:
            print(json.dumps(res, ensure_ascii=False, indent=2))
        else:
            est = res["estimated_total_seconds"]
            print(f"=== 依事件交代需求估算總片長 ({ev_path.name}) ===")
            print(f"成片形式: {fmt} | 原著事件 {res['event_count']} 個（保留 {res['kept_event_count']} 個）| "
                  f"交代要素 {res['exposition_beats_total']} 個 | 預估總長 {est['min']}s – {est['max']}s "
                  f"(中位 {est['mid']}s，約 {res['estimated_total_minutes']} 分鐘)")
            if res.get("episodes"):
                print(f"使用者指定 {res['episodes']} 集：平均每集約 {res['avg_episode_seconds']}s（{res['episode_note']}）")
            for r in res["events"]:
                e = r["estimated_seconds"]
                beats = "、".join(r["exposition_beats"]) or "—"
                shift = "＋時地轉換" if r["time_place_shift"] else ""
                print(f"  - {r['unit_id']} [{r['grade']}] {r['summary']}：{beats}{shift} → {e['min']}s–{e['max']}s")
        return 0

    # 判斷是否為小說模式
    is_novel_mode = args.novel or (args.novel_file is not None)
    target_path = Path(args.novel_file) if args.novel_file else (Path(args.script) if args.script else None)

    if not target_path:
        print("[錯誤] 請指定檔案路徑（--script 或 --novel-file）", file=sys.stderr)
        return 1

    if not target_path.exists():
        print(f"[錯誤] 找不到檔案：{target_path}", file=sys.stderr)
        return 1

    if is_novel_mode:
        from novel_text import read_novel_text
        file_text, _enc = read_novel_text(target_path)
    else:
        file_text = target_path.read_text(encoding="utf-8")
    project_root = find_project_root(target_path)
    if args.genre is None:
        args.genre = project_genre(project_root) or "xuanhuan_revenge"
        genre_note = (
            f"⚠️ genre_mode 尚未定案（project.md 仍是範本佔位符），暫用 {args.genre}；語速區間會跟著題材變，"
            "定調後請重跑或用 --genre 指定。"
        ) if genre_unconfirmed(project_root) else None
    else:
        genre_note = None
    policy_decided = dialogue_policy_decided(project_root)
    fmt = args.series_format or project_format(project_root)
    if fmt == SHORT and args.target_seconds is None:
        args.target_seconds = SHORT_EPISODE_DEFAULT_SECONDS

    # 1. 小說模式
    if is_novel_mode:
        res = estimate_novel_duration(
            file_text,
            target_seconds=args.target_seconds,
            genre_mode=args.genre,
            series_format=fmt,
        )

        if genre_note:
            res["genre_unconfirmed"] = True
            print(genre_note, file=sys.stderr)
        if args.json:
            print(json.dumps(res, ensure_ascii=False, indent=2))
        else:
            m = res["metrics"]
            f = res["stage0_formula"]
            p = res["policies_projection"]
            print(f"=== 階段 0 原文小說體量反推片長與門禁報告 ({target_path.name}) ===")
            tgt = (f"單集目標: {res['target_seconds']}s" if fmt == SHORT
                   else (f"整部目標: {res['target_seconds']}s" if res["target_seconds"] else "整部目標: 未設定（長篇模式只報總長）"))
            print(
                f"狀態: {res['status']} | 成片形式: {fmt} | 題材: {res['genre_mode']} | {tgt}\n"
                f"原著體量: 純字數 {m['total_chars']} 字 | 對白: {m['dialogue_count']} 句 ({m['dialogue_chars']} 字, 佔 {m['dialogue_ratio']}%)\n"
                f"體量反推: 純念台詞需 {f['pure_speech_seconds']}s | 含動作呼吸總長約 {f['estimated_total_seconds']}s (約 {f['estimated_total_seconds']/60:.1f} 分鐘)"
            )
            if res["gate_messages"]:
                print("\n🚨 【觸發階段 0 阻斷閘門】")
                for msg in res["gate_messages"]:
                    print(f"  {msg}")
                if policy_decided:
                    print("  ✅ 台詞政策已在 decisions.json 定案；以下試算僅供核對，不需再選。")
                else:
                    print("  👉 解決方案：必須在進入階段 1 前選定以下四大台詞政策之一！")

            print("\n【四大台詞政策試算】")
            print(f"  {p['policy_1']['name']}:")
            def _len_line(pol: Dict[str, Any]) -> str:
                sec = pol["estimated_total_seconds"]
                if fmt == SHORT:
                    return f"總長約 {sec}s，需拆 {pol['episodes_needed']} 集 (每集約 {pol['avg_episode_seconds']}s)"
                return f"整部約 {sec}s（約 {sec / 60:.1f} 分鐘，一支連續長片）"
            print(f"    - {_len_line(p['policy_1'])}")
            print(f"    - 評價: {p['policy_1']['evaluation']}")

            print(f"\n  {p['policy_2']['name']}:")
            print(f"    - 保留約 {p['policy_2']['retained_dialogue_chars']} 字對白，{_len_line(p['policy_2'])}")
            print(f"    - 評價: {p['policy_2']['evaluation']}")

            print(f"\n  {p['policy_3']['name']}:")
            print(f"    - {p['policy_3']['budget_scope']}對白預算上限: {p['policy_3']['single_episode_dialogue_char_budget_max']} 字 (說話時長上限 {p['policy_3']['single_episode_speech_sec_max']}s)")
            print(f"    - 評價: {p['policy_3']['evaluation']}")

            print(f"\n  {p['policy_4']['name']}:")
            print(f"    - 評價: {p['policy_4']['evaluation']}")

        return 0 if res["status"] == "PASS" else 2

    # 2. 劇本模式
    res = estimate_script_duration(
        file_text,
        male_leads=set(args.male_leads) or None,
        genre_mode=args.genre,
        target_seconds=args.target_seconds,
        h3_mode=args.h3,
        series_format=fmt,
    )
    if genre_note:
        res["genre_unconfirmed"] = True
        print(genre_note, file=sys.stderr)

    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        est = res["estimated_total_seconds"]
        print(f"=== 片長區間與密度審計報告 ({target_path.name}) ===")
        print(
            f"狀態: {res['status']} | 成片形式: {fmt} | 題材: {res['genre_mode']} | "
            f"總發音字數: {res['total_spoken_chars']} 字 | "
            f"預估總時長: {est['min']}s – {est['max']}s (中位 {est['mid']}s)"
        )
        if args.h3 or res.get("h3_audit", {}).get("h3_mode"):
            h3 = res["h3_audit"]
            pass_str = "✅ 符合預算" if h3["passed"] else "⚠️ 建議調整"
            print(
                f"【H3 台詞預算審計】{pass_str} | 純說話秒數: {h3['speech_seconds']}s (4.0字/秒) | "
                f"說話時長佔比: {h3['speech_ratio']:.1%} (上限 60.0%) | 最長單句: {h3['max_line_chars']} 字 (上限 15 字)"
            )
        for sc in res["scenes"]:
            s_est = sc["estimated_seconds"]
            print(
                f"  - 場景 {sc['scene_num']} ({sc['location']}): "
                f"{s_est['min']}s–{s_est['max']}s (動作 {sc['action_beats']} 拍, 對白 {sc['dialogue_lines']} 句/{sc['spoken_chars']} 字)"
            )
        for err in res["errors"]:
            print(f"  [ERROR] {err}")
        for warn in res["warnings"]:
            print(f"  [WARN]  {warn}")

    return 0 if len(res["errors"]) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
