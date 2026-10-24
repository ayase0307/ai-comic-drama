#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
compare_adaptation.py — 原著改編差異審計、四大強制退稿閘門檢查與 100 分制 A/B 對照評分器
支援單章拆多集合併總驗收與單集過濾驗收模式。
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from check_continuity import audit_continuity
from estimate_duration import estimate_script_duration
from event_coverage import analyze_event_coverage
from series_format import LONGFORM, SHORT_EPISODE_DEFAULT_SECONDS, project_format
from validate_structure import parse_and_validate_script

# 非爽文題材中禁止強行植入的狗血打臉套路黑名單詞彙
FORCED_SHUANGWEN_CLICHES = [
    "下跪求饒", "扇耳光", "抽爛你的嘴", "百億神豪", "仙帝附體",
    "拉出去餵狗", "你算什麼東西也配", "三年之期已到"
]


def _episode_key(value: Any) -> str:
    """EP01／ep1／1（整數）都正規化成 EP01；階段 1 的 source.json 常寫整數。"""
    text = str(value if value is not None else "").strip().upper()
    if not text:
        return ""
    digits = text[2:] if text.startswith("EP") else text
    return f"EP{int(digits):02d}" if digits.isdigit() else text


def evaluate_adaptation(
    source_data: Dict[str, Any],
    handoff_data: Dict[str, Any],
    script_text: str,
    bible_data: Optional[Dict[str, Any]] = None,
    target_episode: Optional[str] = None,
    h3_mode: bool = False,
    series_format: str = LONGFORM,
) -> Dict[str, Any]:
    """對改編成果執行原著對帳、四大退稿閘門檢測與 100 分制量化評分。支援多集合併與單集過濾。"""
    errors: List[str] = []
    warnings: List[str] = []
    gate_failures: List[str] = []

    struct_res = parse_and_validate_script(script_text)
    genre_mode = handoff_data.get("genre_mode", source_data.get("genre_mode", "mystery_thriller"))

    episodes = handoff_data.get("episodes", [])
    if target_episode:
        matched_eps = [ep for ep in episodes if _episode_key(ep.get("episode_id")) == _episode_key(target_episode)]
        if matched_eps:
            episodes = matched_eps

    # 長篇漫劇（預設）沒有單集秒數：只有 handoff 明寫了目標／已接受秒數才做預算比對。
    # 短劇短集（使用者明確選擇）缺目標時沿用 90 秒單集預設。
    target_sec = None
    if episodes:
        default_ep = SHORT_EPISODE_DEFAULT_SECONDS if series_format == "short" else None
        per_ep = [ep.get("accepted_duration_seconds") or ep.get("target_duration_seconds") or default_ep for ep in episodes]
        if all(per_ep):
            target_sec = sum(per_ep)

    dur_res = estimate_script_duration(script_text, genre_mode=genre_mode, target_seconds=target_sec,
                                       h3_mode=h3_mode, series_format=series_format)
    cont_res = (
        audit_continuity(bible_data, handoff_data, script_text)
        if bible_data
        else {"status": "PASS", "errors": [], "warnings": [], "gate_failures": []}
    )

    for g in struct_res["gate_failures"] + cont_res["gate_failures"]:
        if g not in gate_failures:
            gate_failures.append(g)

    errors.extend(struct_res["errors"])
    errors.extend(dur_res["errors"])
    errors.extend(cont_res["errors"])
    warnings.extend(struct_res["warnings"])
    warnings.extend(dur_res["warnings"])
    warnings.extend(cont_res["warnings"])

    # 收集 Handoff 中所有場景涵蓋的 source_refs 與 adaptation_changes
    covered_refs: Set[str] = set()
    tracked_change_refs: Set[str] = set()
    all_scenes: List[Dict[str, Any]] = []

    for ep in episodes:
        for sc in ep.get("scenes", []):
            all_scenes.append(sc)
            for ref in sc.get("source_refs", []):
                covered_refs.add(ref)
            for chg in sc.get("adaptation_changes", []):
                if chg.get("source_ref"):
                    tracked_change_refs.add(chg["source_ref"])

    # 1. 檢查原著 MUST_KEEP 事件是否遺失 & 是否存在 UNTRACKED_MAJOR_CHANGE
    raw_source_units = source_data.get("story_units", [])
    if target_episode:
        ep_filter = _episode_key(target_episode)
        source_units = [u for u in raw_source_units if not u.get("episode") or _episode_key(u.get("episode")) == ep_filter]
    else:
        source_units = raw_source_units

    must_keep_total = 0
    must_keep_kept = 0

    for unit in source_units:
        uref = unit["unit_id"]
        grade = unit.get("expected_grade", "KEEP_IF_POSSIBLE")
        if grade == "MUST_KEEP":
            must_keep_total += 1
            if uref in covered_refs:
                must_keep_kept += 1
            else:
                errors.append(
                    f"[MISSING_MUST_KEEP_EVENT] 原著核心必保事件 '{uref}' ({unit.get('summary', '')}) 被刪除，導致因果斷裂"
                )
                if "FATAL_CAUSAL_BREAK" not in gate_failures:
                    gate_failures.append("FATAL_CAUSAL_BREAK")
                if uref not in tracked_change_refs and "UNTRACKED_MAJOR_CHANGE" not in gate_failures:
                    gate_failures.append("UNTRACKED_MAJOR_CHANGE")
        else:
            if uref not in covered_refs and uref not in tracked_change_refs:
                errors.append(
                    f"[UNTRACKED_UNIT_OMISSION] 原著單元 '{uref}' 未出現在劇本中，且未在 adaptation_changes 記錄刪減/合併理由"
                )
                if "UNTRACKED_MAJOR_CHANGE" not in gate_failures:
                    gate_failures.append("UNTRACKED_MAJOR_CHANGE")

    # 2. 檢查跨章伏筆是否提前洩底（Premature Spoiler Check）
    for clue in source_data.get("foreshadowing", []):
        clue_id = clue.get("clue_id")
        reveal_after_scene_idx = clue.get("min_reveal_scene_index", 0)
        spoiler_keywords = clue.get("forbidden_early_spoiler_phrases", [])
        for idx, sc in enumerate(all_scenes):
            if idx < reveal_after_scene_idx:
                audience_visible_blob = json.dumps(
                    {
                        "dialogue": sc.get("dialogue", []),
                        "action_beats": sc.get("action_beats", []),
                        "scene_goal": sc.get("scene_goal", ""),
                    },
                    ensure_ascii=False,
                )
                for kw in spoiler_keywords:
                    if kw and (kw in audience_visible_blob or (reveal_after_scene_idx > len(all_scenes) and kw in script_text)):
                        errors.append(
                            f"[PREMATURE_FORESHADOW_SPOILER] 伏筆 '{clue_id}' 的真相詞 '{kw}' 在場景 {sc.get('scene_id')} 被提前洩底"
                        )
                        if "FATAL_CAUSAL_BREAK" not in gate_failures:
                            gate_failures.append("FATAL_CAUSAL_BREAK")

    # 3. 檢查原著缺口與刻意矛盾是否誠實登記
    reported_issues = handoff_data.get("source_gaps_or_contradictions", [])
    reported_types = {item.get("type") for item in reported_issues}

    if source_data.get("is_incomplete", False):
        if "incomplete_source" not in reported_types:
            errors.append(
                "[UNREPORTED_SOURCE_GAP] 原著資料不完整（殘稿），但 Handoff 未在 source_gaps_or_contradictions 標明缺口，涉嫌擅自虛構結局"
            )
            if "UNTRACKED_MAJOR_CHANGE" not in gate_failures:
                gate_failures.append("UNTRACKED_MAJOR_CHANGE")

    expected_contradictions = source_data.get("known_contradictions", [])
    if len(expected_contradictions) > 0:
        if "canon_contradiction" not in reported_types:
            errors.append(
                "[UNREPORTED_SOURCE_CONTRADICTION] 原著含有內部設定矛盾，但改編未主動提出矛盾清單，涉嫌悄悄掩蓋或照抄矛盾"
            )
            if "CANON_CONTRADICTION" not in gate_failures:
                gate_failures.append("CANON_CONTRADICTION")

    # 4. 檢查非爽文題材是否強行塞入狗血打臉詞彙
    cliche_hits = []
    if genre_mode in ("romance_emotional", "mystery_thriller", "healing_literary", "comedy_slice_of_life"):
        for cliche in FORCED_SHUANGWEN_CLICHES:
            if cliche in script_text:
                cliche_hits.append(cliche)
                errors.append(
                    f"[GENRE_MISMATCH_FORCED_CLICHE] 當前題材為 '{genre_mode}'，劇本卻出現強迫打臉套路詞 '{cliche}'"
                )

    # 5. 計算 100 分制 9 維度得分
    scores: Dict[str, float] = {
        "core_story_and_causality_18": 18.0,
        "character_consistency_and_arc_14": 14.0,
        "visualization_and_actability_14": 14.0,
        "pacing_episode_and_duration_12": 12.0,
        "genre_fit_and_emotional_payoff_10": 10.0,
        "canon_spirit_and_settings_10": 10.0,
        "dialogue_naturalness_and_audio_8": 8.0,
        "filmability_and_handoff_8": 8.0,
        "foreshadowing_and_continuity_6": 6.0,
    }

    if "FATAL_CAUSAL_BREAK" in gate_failures:
        scores["core_story_and_causality_18"] -= 10.0
    if must_keep_total > 0 and must_keep_kept < must_keep_total:
        scores["core_story_and_causality_18"] -= 6.0 * (1.0 - must_keep_kept / must_keep_total)

    if any("ALIAS" in e or "UNREGISTERED" in e for e in cont_res["errors"]):
        scores["character_consistency_and_arc_14"] -= 6.0

    if "CRITICAL_SCENE_UNFILMABLE" in gate_failures or struct_res["vo_ratio"] > 0.30:
        scores["visualization_and_actability_14"] -= 8.0
    elif struct_res["vo_ratio"] > 0.15:
        scores["visualization_and_actability_14"] -= 2.5

    if dur_res["budget_status"] != "PASS":
        scores["pacing_episode_and_duration_12"] -= 4.5
    if dur_res["errors"]:
        scores["pacing_episode_and_duration_12"] -= 4.0

    if cliche_hits:
        scores["genre_fit_and_emotional_payoff_10"] -= min(8.0, len(cliche_hits) * 3.0)

    if "UNTRACKED_MAJOR_CHANGE" in gate_failures:
        scores["canon_spirit_and_settings_10"] -= 6.0

    if dur_res["errors"]:
        scores["dialogue_naturalness_and_audio_8"] -= 3.5

    if not episodes or any("SCHEMA" in e for e in struct_res["errors"]):
        scores["filmability_and_handoff_8"] -= 6.0

    if "CANON_CONTRADICTION" in gate_failures:
        scores["foreshadowing_and_continuity_6"] -= 5.0

    for k in scores:
        scores[k] = round(max(0.0, scores[k]), 1)

    total_score = round(sum(scores.values()), 1)
    overall_pass = (total_score >= 80.0) and (len(gate_failures) == 0) and (len(errors) == 0)

    return {
        "status": "PASS" if overall_pass else "FAIL",
        "total_score_100": total_score,
        "dimension_scores": scores,
        "gate_failures": gate_failures,
        "must_keep_coverage": f"{must_keep_kept}/{must_keep_total}",
        "duration_summary": dur_res["estimated_total_seconds"],
        "vo_ratio": struct_res["vo_ratio"],
        "error_count": len(errors),
        "warning_count": len(warnings),
        "errors": errors,
        "warnings": warnings,
        "h3_audit": dur_res.get("h3_audit"),
        "series_format": series_format,
        # 事件交代完整性（只給審核看，不改變上面的分數與閘門）
        "event_coverage": analyze_event_coverage(
            {**source_data, "story_units": source_units}, [{"episodes": episodes}]),
    }


def _project_root(path: Path) -> Optional[Path]:
    for parent in path.resolve().parents:
        if (parent / "decisions.json").exists() or (parent / "project.md").exists():
            return parent
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="評估小說改編品質、檢查四大退稿閘門並支援 A/B 對照與單章拆多集合併驗收")
    parser.add_argument("--source", type=str, required=True, help="原著結構化分析 JSON 路徑")
    parser.add_argument(
        "--handoff",
        type=str,
        nargs="+",
        required=True,
        help="改編後 Handoff JSON 路徑（支援多檔案或逗號分隔，進行多集合併全章驗收）",
    )
    parser.add_argument(
        "--script",
        type=str,
        nargs="+",
        required=True,
        help="改編後劇本路徑（支援多檔案或逗號分隔，進行多集合併全章驗收）",
    )
    parser.add_argument("--bible", type=str, default=None, help="選填：Story Bible JSON 路徑")
    parser.add_argument("--episode", type=str, default=None, help="選填：指定單集代號（例如 EP01）以進行單集過濾驗收")
    parser.add_argument("--h3", action="store_true", help="開啟 H3 漫劇台詞預算嚴格檢查（4字/秒、單句≤15字、說話秒數佔比≤60%%）")
    parser.add_argument("--format", choices=["longform", "short"], default=None, dest="series_format",
                        help="成片形式（預設讀專案 decisions.json 的 series_format，沒有就是 longform 長篇漫劇）")
    parser.add_argument("--json", action="store_true", help="輸出 JSON 格式")
    args = parser.parse_args()

    # 扁平化展開多路徑參數
    handoff_paths: List[Path] = []
    for h in args.handoff:
        for p in h.split(","):
            p_clean = p.strip()
            if p_clean:
                handoff_paths.append(Path(p_clean))

    script_paths: List[Path] = []
    for s in args.script:
        for p in s.split(","):
            p_clean = p.strip()
            if p_clean:
                script_paths.append(Path(p_clean))

    source_path = Path(args.source)
    if not source_path.exists():
        print(f"[錯誤] 找不到原著 source 檔案：{source_path}", file=sys.stderr)
        return 1
    source_data = json.loads(source_path.read_text(encoding="utf-8"))

    # 讀取並合併多集 handoff
    base_handoff: Dict[str, Any] = {}
    all_episodes = []
    for hp in handoff_paths:
        if not hp.exists():
            print(f"[錯誤] 找不到 Handoff 檔案：{hp}", file=sys.stderr)
            return 1
        hdata = json.loads(hp.read_text(encoding="utf-8"))
        if not base_handoff:
            base_handoff = dict(hdata)
            base_handoff["episodes"] = []
        for ep in hdata.get("episodes", []):
            all_episodes.append(ep)

    base_handoff["episodes"] = all_episodes
    handoff_data = base_handoff

    # 讀取並合併多集劇本文字
    script_text_parts = []
    for sp in script_paths:
        if not sp.exists():
            print(f"[錯誤] 找不到劇本檔案：{sp}", file=sys.stderr)
            return 1
        script_text_parts.append(sp.read_text(encoding="utf-8"))
    script_text = "\n\n".join(script_text_parts)

    bible_data = json.loads(Path(args.bible).read_text(encoding="utf-8")) if args.bible else None

    res = evaluate_adaptation(
        source_data,
        handoff_data,
        script_text,
        bible_data=bible_data,
        target_episode=args.episode,
        h3_mode=args.h3,
        series_format=args.series_format or project_format(_project_root(Path(args.source))),
    )

    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        if len(handoff_paths) > 1:
            scope_str = f"多集合併全章驗收 ({len(handoff_paths)} 集)"
        elif args.episode:
            scope_str = f"單集驗收: {args.episode}"
        else:
            scope_str = script_paths[0].name

        print(f"=== 改編品質 100 分制與四大閘門審計報告 ({scope_str}) ===")
        print(
            f"總評狀態: {res['status']} | 總分: {res['total_score_100']}/100 | "
            f"MUST_KEEP 保留: {res['must_keep_coverage']} | 錯誤數: {res['error_count']}"
        )
        if res["gate_failures"]:
            print(f"🚨 觸發一票否決退稿閘門: {', '.join(res['gate_failures'])}")
        else:
            print("✅ 四大強制退稿閘門: 全部通過 (0 觸發)")

        if res.get("h3_audit") and res["h3_audit"].get("h3_mode"):
            h3 = res["h3_audit"]
            pass_str = "✅ 符合預算" if h3["passed"] else "⚠️ 建議調整"
            print(
                f"【H3 台詞預算審計】{pass_str} | 純說話秒數: {h3['speech_seconds']}s (4.0字/秒) | "
                f"說話時長佔比: {h3['speech_ratio']:.1%} (上限 60.0%) | 最長單句: {h3['max_line_chars']} 字 (上限 15 字)"
            )

        cov = res["event_coverage"]
        if cov["needs_decision"]:
            print(f"【事件交代完整性】{len(cov['needs_decision'])}/{cov['event_count']} 個事件未確認完整交代（交代不全／未標註／被壓縮／被跳過），"
                  f"需使用者決定：{', '.join(cov['needs_decision'])}（詳見 event_coverage.py）")
        else:
            print(f"【事件交代完整性】{cov['event_count']} 個事件都已完整交代或依分級處理")
        print("各維度得分明細:")
        for k, v in res["dimension_scores"].items():
            print(f"  - {k}: {v}")
        for err in res["errors"]:
            print(f"  [ERROR] {err}")
        for warn in res["warnings"]:
            print(f"  [WARN]  {warn}")

    return 0 if res["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
