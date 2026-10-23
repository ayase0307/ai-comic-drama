#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
estimate_duration.py — 漫劇劇本片長區間與小說原文體量反推片長審計器

支援兩種模式：
1. 劇本模式（預設）：
   - 估算劇本每場與總體時長區間（分題材語速區間、句間氣口、情緒停頓、動作節拍與換場建立時間）；
   - 審計單句 TTS 字數限制（>28 字警告，>35 字錯誤）；
   - 驗證目標時長 ±15% 區間。
2. 小說模式（--novel）：
   - 執行階段 0 原文體量反推片長阻斷門禁（純念秒數 = 台詞字數 / 4，總片長 = 純念秒數 * 1.6）；
   - 若預估片長 > 目標片長 * 2，觸發 [STAGE0_VOLUME_GATE_BLOCK] 阻斷提示；
   - 自動試算四大台詞政策（① 逐字保留、② 重點句 20%、③ 影視改寫預算上限、④ 純旁白）。

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

# 各題材預設語速區間（字/秒）：[慢速/沉澱 R_min, 快速/緊湊 R_max]
GENRE_SPEECH_RATES: Dict[str, Tuple[float, float]] = {
    "xuanhuan_revenge": (3.6, 4.4),
    "romance_emotional": (3.0, 3.8),
    "mystery_thriller": (3.1, 3.9),
    "comedy_slice_of_life": (3.8, 4.5),
    "wuxia_action": (3.4, 4.2),
    "healing_literary": (2.8, 3.5),
}

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

            # H3 實戰台詞預算檢查：單句發音字數 ≤ 15 字
            if h3_mode and c_count > 15:
                warnings.append(
                    f"[H3_LINE_TOO_LONG] 第 {dlg['line_no']} 行 ({sc['scene_num']} {dlg['speaker']}): "
                    f"單句發音字數為 {c_count} 字（超過 H3 建議上限 15 字，易引發加速講話或吞字，建議拆為短句或切特寫反應）"
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
    h3_speech_seconds = round(total_spoken_chars / 4.0, 1)
    base_dur = target_seconds if (target_seconds and target_seconds > 0) else mid_seconds
    h3_speech_ratio = round(h3_speech_seconds / base_dur, 3) if base_dur > 0 else 0.0

    if h3_mode and h3_speech_ratio > 0.60:
        warnings.append(
            f"[H3_SPEECH_RATIO_EXCEEDED] H3 純說話秒數佔比達 {h3_speech_ratio:.1%} "
            f"({h3_speech_seconds}s/{base_dur}s)，超過 H3 漫劇鐵律上限 60%（建議精簡台詞或增加畫面動作空白）"
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
            compression_advice = [
                "先判斷超出的是「因果必要」還是「冗餘」，再三選一：",
                "A. 冗餘 → 刪重複解說、合併重複反應節拍、精簡長句（嚴禁刪 MUST_KEEP 核心因果事件）",
                "B. 因果必要 → 於場次邊界拆成上下集（每集都要有自己的目標、阻礙與結尾鉤子），不要壓縮分鏡",
                "C. 因果必要且不宜拆 → 接受實際長度，並在 handoff 該集寫入 accepted_duration_seconds",
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
        "h3_speech_seconds": h3_speech_seconds,
        "h3_speech_ratio": h3_speech_ratio,
        "h3_audit": {
            "h3_mode": h3_mode,
            "spoken_chars": total_spoken_chars,
            "speech_seconds": h3_speech_seconds,
            "speech_ratio": h3_speech_ratio,
            "max_line_chars": max_single_line_chars,
            "passed": (h3_speech_ratio <= 0.60 and max_single_line_chars <= 15),
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
    target_seconds: float = 90.0,
    genre_mode: str = "xuanhuan_revenge",
) -> Dict[str, Any]:
    """執行階段 0 原文體量反推片長門禁與四大台詞政策試算。"""
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

    # 阻斷門禁判定：估算片長 > 目標片長 * 2
    is_blocked = estimated_total_seconds > (target_seconds * 2.0)
    gate_status = "BLOCKED" if is_blocked else "PASS"

    gate_messages: List[str] = []
    if is_blocked:
        gate_messages.append(
            f"[STAGE0_VOLUME_GATE_BLOCK] 原始小說台詞推算總片長 {estimated_total_seconds}s "
            f"超過目標單集時長 {target_seconds}s 的 2 倍（門檻 {target_seconds * 2.0}s）！"
            f"依規範強制在階段 0 停下，嚴禁擅自動筆直接分鏡！"
        )

    # 四大台詞政策試算
    # 政策 ①：100% 逐字保留
    p1_episodes = max(1, math.ceil(estimated_total_seconds / target_seconds))
    policy_1 = {
        "policy_id": "policy_1_verbatim_100",
        "name": "① 原文逐字保留 (100%)",
        "dialogue_retention_ratio": 1.0,
        "retained_dialogue_chars": dialogue_chars,
        "speech_seconds": speech_seconds,
        "estimated_total_seconds": estimated_total_seconds,
        "episodes_needed": p1_episodes,
        "avg_episode_seconds": round(estimated_total_seconds / p1_episodes, 1),
        "evaluation": "❌ 嚴重撞死 H3 對白預算；每 15 秒需塞大量台詞導致口型崩壞與 ASR 吞字；僅適合拆成極多超短集。",
    }

    # 政策 ②：只留重點句 (保留 20% 原著對白，推薦)
    p2_chars = round(dialogue_chars * 0.20)
    p2_speech_sec = round(p2_chars / speech_rate, 1)
    p2_total_sec = round(p2_speech_sec * action_factor, 1)
    p2_episodes = max(1, math.ceil(p2_total_sec / target_seconds))
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

    # 政策 ③：全部改寫為影視對白 (依目標單集反推預算上限)
    # 單集安全說話時長上限 = 目標時長 * 60%
    # 單集對白字數上限 = (目標時長 * 60%) * 4.0
    safe_speech_sec_per_ep = round(target_seconds * 0.60, 1)
    safe_dialogue_chars_per_ep = round(safe_speech_sec_per_ep * speech_rate)
    policy_3 = {
        "policy_id": "policy_3_cinematic_rewrite",
        "name": "③ 全部改寫為影視對白 (重構口語短句)",
        "single_episode_dialogue_char_budget_max": safe_dialogue_chars_per_ep,
        "single_episode_speech_sec_max": safe_speech_sec_per_ep,
        "dialogue_time_ratio_cap": "≤ 60% 片長",
        "evaluation": "✅ 自由度最高；打破原著長句重構為視聽語言，單集對白上限約 180~216 字，留足動作與環境特效時間。",
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
        "genre_mode": genre_mode,
        "target_seconds_per_episode": target_seconds,
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
            "block_threshold_seconds": target_seconds * 2.0,
        },
        "gate_messages": gate_messages,
        "policies_projection": {
            "policy_1": policy_1,
            "policy_2": policy_2,
            "policy_3": policy_3,
            "policy_4": policy_4,
        },
    }


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
    parser.add_argument("--target-seconds", type=float, default=90.0, help="單集目標秒數（預設 90s）")
    parser.add_argument("--h3", action="store_true", help="開啟 H3 漫劇台詞預算嚴格檢查（4字/秒、單句≤15字、說話秒數佔比≤60%%）")
    parser.add_argument("--h3-strict", action="store_true", dest="h3", help="同 --h3")
    parser.add_argument("--json", action="store_true", help="輸出 JSON 格式")
    args = parser.parse_args()

    # 判斷是否為小說模式
    is_novel_mode = args.novel or (args.novel_file is not None)
    target_path = Path(args.novel_file) if args.novel_file else (Path(args.script) if args.script else None)

    if not target_path:
        print("[錯誤] 請指定檔案路徑（--script 或 --novel-file）", file=sys.stderr)
        return 1

    if not target_path.exists():
        print(f"[錯誤] 找不到檔案：{target_path}", file=sys.stderr)
        return 1

    file_text = target_path.read_text(encoding="utf-8")
    project_root = find_project_root(target_path)
    if args.genre is None:
        args.genre = project_genre(project_root) or "xuanhuan_revenge"
    policy_decided = dialogue_policy_decided(project_root)

    # 1. 小說模式
    if is_novel_mode:
        res = estimate_novel_duration(
            file_text,
            target_seconds=args.target_seconds,
            genre_mode=args.genre,
        )

        if args.json:
            print(json.dumps(res, ensure_ascii=False, indent=2))
        else:
            m = res["metrics"]
            f = res["stage0_formula"]
            p = res["policies_projection"]
            print(f"=== 階段 0 原文小說體量反推片長與門禁報告 ({target_path.name}) ===")
            print(
                f"狀態: {res['status']} | 題材: {res['genre_mode']} | 單集目標: {res['target_seconds_per_episode']}s\n"
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
            print(f"    - 總時長約 {p['policy_1']['estimated_total_seconds']}s，需拆 {p['policy_1']['episodes_needed']} 集 (每集約 {p['policy_1']['avg_episode_seconds']}s)")
            print(f"    - 評價: {p['policy_1']['evaluation']}")

            print(f"\n  {p['policy_2']['name']}:")
            print(f"    - 保留約 {p['policy_2']['retained_dialogue_chars']} 字對白，總長約 {p['policy_2']['estimated_total_seconds']}s，建議拆 {p['policy_2']['episodes_needed']} 集 (每集約 {p['policy_2']['avg_episode_seconds']}s)")
            print(f"    - 評價: {p['policy_2']['evaluation']}")

            print(f"\n  {p['policy_3']['name']}:")
            print(f"    - 單集對白預算上限: {p['policy_3']['single_episode_dialogue_char_budget_max']} 字 (說話時長上限 {p['policy_3']['single_episode_speech_sec_max']}s)")
            print(f"    - 評價: {p['policy_3']['evaluation']}")

            print(f"\n  {p['policy_4']['name']}:")
            print(f"    - 評價: {p['policy_4']['evaluation']}")

        return 0 if res["status"] == "PASS" else 2

    # 2. 劇本模式
    res = estimate_script_duration(
        file_text,
        genre_mode=args.genre,
        target_seconds=args.target_seconds,
        h3_mode=args.h3,
    )

    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        est = res["estimated_total_seconds"]
        print(f"=== 片長區間與密度審計報告 ({target_path.name}) ===")
        print(
            f"狀態: {res['status']} | 題材: {res['genre_mode']} | "
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
