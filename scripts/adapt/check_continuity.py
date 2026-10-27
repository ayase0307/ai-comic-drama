#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_continuity.py — 跨集人物別名消歧、道具狀態流轉、時間線與記帳式因果（Debt Ledger）審計器
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from validate_structure import parse_and_validate_script


def audit_continuity(
    bible_data: Dict[str, Any],
    handoff_data: Dict[str, Any],
    script_text: Optional[str] = None,
) -> Dict[str, Any]:
    """執行角色名稱/別名一致性、道具狀態連戲、同框人數上限與時間線檢查。"""
    errors: List[str] = []
    warnings: List[str] = []
    gate_failures: List[str] = []

    # 1. 建立角色註冊表與別名映射
    char_registry: Dict[str, Dict[str, Any]] = {}
    canonical_to_id: Dict[str, str] = {}
    alias_to_canonical: Dict[str, str] = {}

    for ch in bible_data.get("characters", []):
        cid = ch["character_id"]
        cname = ch["canonical_name"]
        char_registry[cid] = ch
        canonical_to_id[cname] = cid
        for alias in ch.get("aliases", []):
            alias_to_canonical[alias] = cname

    # 生物（bible.json 的 creatures）與角色同樣視為已註冊（議題 #31）
    for cr in bible_data.get("creatures", []) or []:
        cid = cr.get("creature_id") or cr.get("character_id") or cr.get("id")
        cname = cr.get("canonical_name") or cr.get("name")
        if not cid:
            continue
        char_registry[cid] = cr
        if cname:
            canonical_to_id[cname] = cid
        for alias in cr.get("aliases", []) or []:
            if cname:
                alias_to_canonical[alias] = cname

    # 2. 若提供劇本文字，檢查發言人與人物行是否誤用別名或未註冊角色
    if script_text:
        parsed_script = parse_and_validate_script(script_text)
        for sc in parsed_script["scenes"]:
            for cname in sc["characters"]:
                if cname in alias_to_canonical:
                    errors.append(
                        f"[ALIAS_USED_AS_CANONICAL] 場景 {sc['scene_num']} 人物行使用了別名 '{cname}'，"
                        f"應統一使用標準名 '{alias_to_canonical[cname]}'"
                    )
                elif cname not in canonical_to_id and len(canonical_to_id) > 0:
                    errors.append(
                        f"[UNREGISTERED_CHARACTER_IN_SCRIPT] 場景 {sc['scene_num']} 出現未在 Story Bible 註冊的角色 '{cname}'"
                    )
            for dlg in sc["dialogues"]:
                sp = dlg["speaker"]
                if sp in alias_to_canonical:
                    errors.append(
                        f"[ALIAS_USED_AS_SPEAKER] 第 {dlg['line_no']} 行 ({sc['scene_num']}): "
                        f"對白發言人使用了別名 '{sp}'，應使用標準名 '{alias_to_canonical[sp]}'"
                    )
                elif (sp not in canonical_to_id and len(canonical_to_id) > 0
                      and not re.match(r"^(旁白|畫外音|字幕|narrator|narration|v\.?o\.?)", sp.strip(), re.IGNORECASE)):
                    # 旁白／畫外音不是角色，不需要在 Story Bible 註冊
                    errors.append(
                        f"[UNREGISTERED_SPEAKER] 第 {dlg['line_no']} 行 ({sc['scene_num']}): "
                        f"發言人 '{sp}' 未在 Story Bible 中註冊"
                    )

    # 3. 遍歷 Handoff JSON 中的場景，檢查道具/服裝狀態流轉與同框人數
    tracked_state: Dict[str, str] = {}
    tracked_last_scene: Dict[str, str] = {}
    irreversible_states: Set[str] = set(bible_data.get("irreversible_states", ["destroyed", "burned", "dead"]))

    all_episodes = handoff_data.get("episodes", [])
    seen_ep_ids: Set[str] = set()

    for ep in all_episodes:
        ep_id = ep.get("episode_id", "UNKNOWN_EP")
        seen_ep_ids.add(ep_id)
        for sc in ep.get("scenes", []):
            sid = sc.get("scene_id", "UNKNOWN_SCENE")
            setting = sc.get("setting", {})
            timeline_tag = setting.get("timeline_tag", "present")

            # 檢查角色 ID 是否註冊
            scene_chars = sc.get("characters", [])
            for cid in scene_chars:
                if char_registry and cid not in char_registry:
                    errors.append(f"[UNREGISTERED_CHAR_ID] {sid}: 角色 ID '{cid}' 未在 Story Bible 中註冊")

            # 檢查單場同框人數（扣除純畫外音/電話音角色）
            offscreen_speakers = {
                d.get("speaker")
                for d in sc.get("dialogue", [])
                if d.get("audio_type") in ("offscreen", "phone", "voiceover")
            }
            onscreen_speakers = {
                d.get("speaker")
                for d in sc.get("dialogue", [])
                if d.get("audio_type") == "onscreen"
            }
            onscreen_chars = [
                c for c in scene_chars if c not in offscreen_speakers or c in onscreen_speakers
            ]
            risk_obj = sc.get("storyboard_handoff", {}).get("production_risk", {})
            if len(onscreen_chars) > 3 and not risk_obj.get("simplified_alternative"):
                warnings.append(
                    f"[CROWD_RISK_UNMITIGATED] {sid}: 單場同框角色達 {len(onscreen_chars)} 人 (>3)，"
                    f"易引發 AI 多主體特徵滲漏，建議在 production_risk.simplified_alternative 提供簡化分鏡方案"
                )

            # 連戲狀態機檢查（僅對 present 正敘時間線執行嚴格傳遞）
            if timeline_tag == "present":
                c_init = sc.get("continuity_initial", {})
                c_final = sc.get("continuity_final", {})
                transition_note = sc.get("state_transition_note", "")

                for item_key, init_val in c_init.items():
                    if item_key in tracked_state:
                        prev_val = tracked_state[item_key]
                        prev_sid = tracked_last_scene[item_key]
                        if prev_val != init_val and not transition_note:
                            errors.append(
                                f"[CONTINUITY_STATE_MISMATCH] {sid}: 物件/狀態 '{item_key}' 的初始狀態為 '{init_val}'，"
                                f"但上一場 ({prev_sid}) 結束狀態為 '{prev_val}'，且無 state_transition_note 說明轉移原因"
                            )
                            if "CANON_CONTRADICTION" not in gate_failures:
                                gate_failures.append("CANON_CONTRADICTION")
                        if prev_val in irreversible_states and init_val not in irreversible_states:
                            errors.append(
                                f"[IRREVERSIBLE_STATE_VIOLATION] {sid}: '{item_key}' 在 {prev_sid} 已處於不可逆狀態 '{prev_val}'，"
                                f"卻在正敘場景 {sid} 恢復為 '{init_val}'"
                            )
                            if "CANON_CONTRADICTION" not in gate_failures:
                                gate_failures.append("CANON_CONTRADICTION")

                for item_key, final_val in c_final.items():
                    tracked_state[item_key] = final_val
                    tracked_last_scene[item_key] = sid

    # 4. 檢查記帳式因果債務帳本（Debt Ledger）
    debt_ledger = handoff_data.get("debt_ledger", [])
    if len(all_episodes) >= 2 and len(debt_ledger) == 0:
        warnings.append("[EMPTY_DEBT_LEDGER] 多集劇本未建立任何跨集因果債務（debt_ledger 為空），存在單元清零風險")
    for debt in debt_ledger:
        payoff = debt.get("payoff_ep")
        # 未償還（status=open）的債務可以用 payoff_ep="TBD" 或留空，表示還沒排回收集數；已償還的才要求明確集數。
        unscheduled_ok = debt.get("status", "open") == "open" and (not payoff or str(payoff).upper() in ("TBD", "UNSCHEDULED"))
        if not debt.get("origin_ep") or (not payoff and not unscheduled_ok):
            errors.append(f"[INVALID_DEBT_ENTRY] 債務 '{debt.get('debt_id')}' 缺少明確的 origin_ep 或 payoff_ep（未償還的可填 TBD）")

    passed = len(errors) == 0 and len(gate_failures) == 0
    return {
        "status": "PASS" if passed else "FAIL",
        "tracked_items_final_state": tracked_state,
        "gate_failures": gate_failures,
        "errors": errors,
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="檢查漫劇跨集連戲、人物別名消歧與因果帳本")
    parser.add_argument("--bible", type=str, required=True, help="Story Bible JSON 檔案路徑")
    parser.add_argument("--handoff", type=str, required=True, help="Handoff JSON 檔案路徑")
    parser.add_argument("--script", type=str, default=None, help="選填：人類劇本路徑 (.md / .txt)")
    parser.add_argument("--json", action="store_true", help="輸出 JSON 格式")
    args = parser.parse_args()

    bible_path = Path(args.bible)
    handoff_path = Path(args.handoff)
    if not bible_path.exists() or not handoff_path.exists():
        print("錯誤：找不到指定的 Bible 或 Handoff JSON 檔案", file=sys.stderr)
        return 1

    bible_data = json.loads(bible_path.read_text(encoding="utf-8-sig"))
    handoff_data = json.loads(handoff_path.read_text(encoding="utf-8-sig"))
    script_text = Path(args.script).read_text(encoding="utf-8-sig") if args.script else None

    res = audit_continuity(bible_data, handoff_data, script_text)

    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        print(f"=== 跨集連戲與設定一致性報告 ({handoff_path.name}) ===")
        print(f"狀態: {res['status']} | 追蹤狀態項數: {len(res['tracked_items_final_state'])}")
        if res["gate_failures"]:
            print(f"觸發強制退稿閘門: {', '.join(res['gate_failures'])}")
        for err in res["errors"]:
            print(f"  [ERROR] {err}")
        for warn in res["warnings"]:
            print(f"  [WARN]  {warn}")

    return 0 if res["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
