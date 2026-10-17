#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
estimate_duration.py — 漫劇劇本片長區間與對白字數密度審計器
支援分題材語速區間、句間氣口、情緒停頓、動作節拍與換場建立時間估算。
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from validate_structure import parse_and_validate_script

# 各題材預設語速區間（字/秒）：[慢速/沉澱 R_min, 快速/緊湊 R_max]
GENRE_SPEECH_RATES: Dict[str, Tuple[float, float]] = {
    "xuanhuan_revenge": (3.6, 4.4),
    "romance_emotional": (3.0, 3.8),
    "mystery_thriller": (3.1, 3.9),
    "comedy_slice_of_life": (3.8, 4.5),
    "wuxia_action": (3.4, 4.2),
    "healing_literary": (2.8, 3.5),
}

NON_WHITESPACE_RE = re.compile(r"[^\s，。！？、；：「」『』（）()…—\-\.,!\?;:\"'~]")


def count_spoken_chars(text: str) -> int:
    """計算實際發音之非空白、非標點字元數。"""
    return len(NON_WHITESPACE_RE.findall(text))


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
) -> Dict[str, Any]:
    """計算劇本每場與總體時長區間，並檢查單句 TTS 字數限制。"""
    parsed = parse_and_validate_script(script_text)
    r_min, r_max = GENRE_SPEECH_RATES.get(genre_mode, (3.2, 4.0))

    errors: List[str] = []
    warnings: List[str] = []
    scene_estimates: List[Dict[str, Any]] = []

    total_min = 0.0
    total_max = 0.0
    total_spoken_chars = 0

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

    budget_status = "PASS"
    compression_advice: List[str] = []

    if target_seconds is not None and target_seconds > 0:
        allowed_low = round(target_seconds * 0.85, 1)
        allowed_high = round(target_seconds * 1.15, 1)
        # 若預估區間 [total_min, total_max] 與目標允許區間 [allowed_low, allowed_high] 完全無交集
        if total_min > allowed_high:
            budget_status = "OVER_BUDGET"
            warnings.append(
                f"[DURATION_OVER_BUDGET] 預估時長區間 [{total_min}s, {total_max}s] 超出目標 {target_seconds}s (+15% 上限 {allowed_high}s)"
            )
            compression_advice = [
                "1. 優先刪除重複解說與背景重述台詞",
                "2. 合併重複的旁觀震驚反應節拍",
                "3. 壓縮非核心過場支線",
                "4. 將長句對白精簡為短句（嚴禁刪除 MUST_KEEP 核心因果事件）",
            ]
        elif total_max < allowed_low:
            budget_status = "UNDER_BUDGET"
            warnings.append(
                f"[DURATION_UNDER_BUDGET] 預估時長區間 [{total_min}s, {total_max}s] 低於目標 {target_seconds}s (-15% 下限 {allowed_low}s)"
            )

    passed = len(errors) == 0 and budget_status == "PASS"

    return {
        "status": "PASS" if passed else ("WARN" if len(errors) == 0 else "FAIL"),
        "genre_mode": genre_mode,
        "speech_rate_assumption_chars_per_sec": {"min": r_min, "max": r_max},
        "target_seconds": target_seconds,
        "total_spoken_chars": total_spoken_chars,
        "estimated_total_seconds": {"min": total_min, "max": total_max, "mid": mid_seconds},
        "budget_status": budget_status,
        "scenes": scene_estimates,
        "compression_advice": compression_advice,
        "errors": errors,
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="估算漫劇劇本時長區間並審計對白字數密度")
    parser.add_argument("--script", type=str, required=True, help="漫劇劇本路徑")
    parser.add_argument("--genre", type=str, default="mystery_thriller", help="題材模式代碼")
    parser.add_argument("--target-seconds", type=float, default=None, help="選填：目標秒數（驗證 ±15%% 區間）")
    parser.add_argument("--json", action="store_true", help="輸出 JSON 格式")
    args = parser.parse_args()

    script_path = Path(args.script)
    if not script_path.exists():
        print(f"錯誤：找不到劇本檔案 {script_path}", file=sys.stderr)
        return 1

    res = estimate_script_duration(
        script_path.read_text(encoding="utf-8"),
        genre_mode=args.genre,
        target_seconds=args.target_seconds,
    )

    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        est = res["estimated_total_seconds"]
        print(f"=== 片長區間與密度審計報告 ({script_path.name}) ===")
        print(
            f"狀態: {res['status']} | 題材: {res['genre_mode']} | "
            f"總發音字數: {res['total_spoken_chars']} 字 | "
            f"預估總時長: {est['min']}s – {est['max']}s (中位 {est['mid']}s)"
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
