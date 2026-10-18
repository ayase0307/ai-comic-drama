#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sync_script.py — 漫劇劇本與 Handoff JSON 局部同步與人工審核（HITL）工具

功能：
1. 將 human-edited script-epNN.md 的場頭、人物行、對白與 △ 動作行局部同步更新至 handoff-epNN.json。
2. 從零建立 Handoff：當指定之 handoff 檔案不存在時，自動初始化建立合法的 handoff 結構並由劇本生成場景。
3. 劇本元數據解析：自動讀取劇本內之 HTML 註解元數據（<!-- source: U01, U02 -->、<!-- must_keep: MK01 -->、<!-- change: must_keep | U01 | 原因 -->）。
4. 自動配對 Source：若指定 --source <source.json>，自動比對對白/動作關鍵字或為未標註場景綁定合規之原著單元。
5. 多場景擴展：當劇本場景多於 handoff 時，自動於 handoff["scenes"] 中新增符合 handoff.schema.json 規範之場景物件。
6. 清理支援：若劇本場景少於 handoff，支援 --prune-extra 自動移除未鎖定之多餘舊場景，避免 validate_structure 報 SCENE_COUNT_MISMATCH。
7. 保護機制：若場景已鎖定 (locked=True 或 review_status='approved') 且內容有變動，預設拒絕同步並報錯退出（除非帶 --unlock 或 --force）。
8. 自動更新版號 (revision +1)、source_hash (SHA256 前 8 碼)、updated_at，並重設為 pending_review。
9. 提供 CLI 人工審核簽核指令：--scene <id> --set-status {draft,pending_review,approved,rejected} --note <text>。
   - approved 自動鎖定 (locked=True)
   - rejected/draft/pending_review 自動解鎖 (locked=False)

僅使用 Python 標準庫。
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate_structure import parse_and_validate_script  # noqa: E402


def compute_content_hash(actions: List[str], dialogues: List[Dict[str, Any]]) -> str:
    """計算場景動作與對白的 SHA256 前 8 碼雜湊值。"""
    payload = {
        "actions": actions,
        "dialogues": [{"speaker": d.get("speaker", ""), "text": d.get("text", "")} for d in dialogues],
    }
    dumped = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(dumped.encode("utf-8")).hexdigest()[:8]


def get_scene_number_from_id(scene_id: str) -> Optional[Tuple[int, int]]:
    """解析 EP01-S02 -> (1, 2) 或 1-2 -> (1, 2)。"""
    m = re.match(r"^EP(\d+)-S(\d+)$", scene_id)
    if m:
        return int(m.group(1)), int(m.group(2))
    m2 = re.match(r"^(\d+)-(\d+)$", scene_id)
    if m2:
        return int(m2.group(1)), int(m2.group(2))
    return None


def match_script_scene(script_scenes: List[Dict[str, Any]], handoff_scene: Dict[str, Any], scene_index: int) -> Optional[Dict[str, Any]]:
    """將 handoff 中的 scene 與解析後的劇本場景配對。"""
    target_id = handoff_scene.get("scene_id", "")
    target_pair = get_scene_number_from_id(target_id)

    # 1. 精確以 scene_num 比對 (如 "1-1")
    for sc in script_scenes:
        sc_num = sc.get("scene_num", "")
        if sc_num == target_id:
            return sc
        sc_pair = get_scene_number_from_id(sc_num)
        if target_pair and sc_pair and target_pair == sc_pair:
            return sc

    # 2. 若索引相符且數量相同，以順序對齊
    if scene_index < len(script_scenes):
        return script_scenes[scene_index]

    return None


def build_speaker_map(script_scenes: List[Dict[str, Any]], handoff_scenes: List[Dict[str, Any]]) -> Dict[str, str]:
    """建立劇本角色中文名與 handoff speaker id 的映射對照表。"""
    mapping: Dict[str, str] = {}
    for sc, hs in zip(script_scenes, handoff_scenes):
        script_dlgs = sc.get("dialogues", [])
        hs_dlgs = hs.get("dialogue", [])
        for sd, hd in zip(script_dlgs, hs_dlgs):
            s_spk = sd.get("speaker")
            h_spk = hd.get("speaker")
            if s_spk and h_spk:
                mapping[s_spk] = h_spk
    return mapping


def detect_audio_type(note: str, current_type: str = "onscreen") -> str:
    """依據括注提示推斷音訊類型。"""
    if not note:
        return current_type or "onscreen"
    if any(k in note for k in ["畫外音", "画外音", "OS", "O.S."]):
        return "offscreen"
    if any(k in note for k in ["內心獨白", "内心独白", "VO", "V.O."]):
        return "voiceover"
    if any(k in note for k in ["電話", "电话", "手機", "手机"]):
        return "phone"
    return current_type or "onscreen"


def time_to_en(time_str: str) -> str:
    """中文時間詞轉英文 enum。"""
    mapping = {
        "日": "day",
        "夜": "night",
        "晨": "dawn",
        "昏": "dusk",
        "不明": "unknown",
    }
    return mapping.get(time_str, "unknown")


def auto_match_source_units(
    script_scenes: List[Dict[str, Any]],
    source_data: Dict[str, Any],
) -> None:
    """若劇本場景未明確標註 <!-- source: ... -->，嘗試根據劇本動作/對白關鍵字自動配對 source.json 的 story_units。"""
    story_units = source_data.get("story_units", [])
    if not story_units:
        return

    assigned_units = set()
    for sc in script_scenes:
        for r in sc.get("source_refs", []):
            assigned_units.add(r)

    for sc in script_scenes:
        if sc.get("source_refs"):
            continue

        full_scene_text = " ".join(
            [sc.get("location", "")] +
            [a["text"] for a in sc.get("actions", [])] +
            [d["text"] for d in sc.get("dialogues", [])]
        )

        matched_refs = []
        matched_must_keeps = []
        for u in story_units:
            uid = u.get("unit_id")
            if not uid:
                continue
            summary = u.get("summary", "")
            keywords = [w for w in re.split(r"[\s,，、。！？]+", summary) if len(w) >= 2]
            hit_count = sum(1 for kw in keywords if kw in full_scene_text)
            if (hit_count >= 2) or (keywords and hit_count == len(keywords)):
                matched_refs.append(uid)
                if u.get("expected_grade") == "MUST_KEEP":
                    matched_must_keeps.append(uid)
                assigned_units.add(uid)

        if matched_refs:
            sc["source_refs"] = matched_refs
            sc["must_keep_ids"] = matched_must_keeps
            sc["adaptation_changes"] = [
                {
                    "type": "must_keep" if r in matched_must_keeps else "keep_if_possible",
                    "source_ref": r,
                    "description": f"依文本關鍵字自動關聯原著單元 {r}",
                    "is_adaptation_addition": False,
                }
                for r in matched_refs
            ]

    unassigned_must_keeps = [
        u["unit_id"] for u in story_units
        if u.get("expected_grade") == "MUST_KEEP" and u["unit_id"] not in assigned_units
    ]
    if script_scenes and unassigned_must_keeps and not any(sc.get("source_refs") for sc in script_scenes):
        first_sc = script_scenes[0]
        first_sc["source_refs"] = [unassigned_must_keeps[0]]
        first_sc["must_keep_ids"] = [unassigned_must_keeps[0]]
        first_sc["adaptation_changes"] = [{
            "type": "must_keep",
            "source_ref": unassigned_must_keeps[0],
            "description": f"預設關聯核心開場單元 {unassigned_must_keeps[0]}",
            "is_adaptation_addition": False,
        }]


def create_handoff_scene_from_script(
    sc: Dict[str, Any],
    project_id: str,
    episode_id: str,
    scene_id: str,
    speaker_map: Dict[str, str],
    adaptation_mode: str = "balanced",
) -> Dict[str, Any]:
    """根據劇本解析結果建立符合 handoff.schema.json 的全新場景物件。"""
    time_en = time_to_en(sc.get("time", ""))
    int_ext_str = sc.get("int_ext", "")
    interior = ("內" in int_ext_str or "内" in int_ext_str)

    tl_tag = sc.get("timeline_tag", "")
    timeline_tag = "flashback" if any(k in tl_tag for k in ["閃回", "回憶", "flashback"]) else "present"

    action_texts = [a["text"] for a in sc.get("actions", [])]

    dialogue_list: List[Dict[str, Any]] = []
    for nd in sc.get("dialogues", []):
        speaker_name = nd.get("speaker", "")
        spk = speaker_map.get(speaker_name, speaker_name)
        audio_t = detect_audio_type(nd.get("note", ""), "onscreen")
        item: Dict[str, Any] = {
            "speaker": spk,
            "text": nd.get("text", ""),
            "audio_type": audio_t,
        }
        if nd.get("note"):
            item["delivery_note"] = nd["note"]
        dialogue_list.append(item)

    char_names = sc.get("characters", [])
    mapped_chars = [speaker_map.get(c, c) for c in char_names if c]
    if not mapped_chars:
        seen = set()
        for d in dialogue_list:
            sp = d["speaker"]
            if sp and sp not in seen:
                seen.add(sp)
                mapped_chars.append(sp)

    # 估算秒數 (約 4 字/秒 + 動作行 2.5 秒)
    dlg_chars = sum(len(d["text"]) for d in dialogue_list)
    est_dur = max(10.0, round(dlg_chars / 4.0 + len(action_texts) * 2.5, 1))
    dur_min = max(5, round(est_dur * 0.8))
    dur_max = max(10, round(est_dur * 1.2))

    now_iso = datetime.now(timezone.utc).isoformat()
    content_hash = compute_content_hash(action_texts, dialogue_list)

    heading_str = f"{sc.get('scene_num', '')} {sc.get('location', '')} {sc.get('time', '')}/{sc.get('int_ext', '')}".strip()

    # 提取劇本中的 source_refs, must_keep_ids, adaptation_changes
    sc_source_refs = list(sc.get("source_refs", []))
    sc_must_keeps = list(sc.get("must_keep_ids", []))
    sc_adaptation_changes = list(sc.get("adaptation_changes", []))

    if not sc_adaptation_changes and sc_source_refs:
        for ref in sc_source_refs:
            sc_adaptation_changes.append({
                "type": "must_keep" if ref in sc_must_keeps else "keep_if_possible",
                "source_ref": ref,
                "description": f"場景保留原著單元 {ref}",
                "is_adaptation_addition": False,
            })

    return {
        "project_id": project_id,
        "episode_id": episode_id,
        "scene_id": scene_id,
        "heading": heading_str,
        "location": sc.get("location", ""),
        "time_of_day": sc.get("time", ""),
        "int_ext": sc.get("int_ext", ""),
        "characters_present": list(mapped_chars),
        "source_refs": sc_source_refs,
        "source_unit_ids": list(sc_source_refs),
        "must_keep_ids": sc_must_keeps,
        "adaptation_mode": adaptation_mode,
        "setting": {
            "location": sc.get("location", ""),
            "time": time_en,
            "interior": interior,
            "timeline_tag": timeline_tag,
        },
        "characters": list(mapped_chars),
        "scene_goal": "TODO",
        "dramatic_turn": "TODO",
        "action_beats": action_texts,
        "dialogue": dialogue_list,
        "dialogue_blocks": list(dialogue_list),
        "props": [],
        "continuity_initial": {},
        "continuity_final": {},
        "estimated_duration_seconds": {"min": dur_min, "max": dur_max},
        "estimated_duration_s": est_dur,
        "adaptation_changes": sc_adaptation_changes,
        "storyboard_handoff": {
            "required_visual_beats": list(action_texts),
            "required_audio_beats": [],
            "must_preserve": [],
        },
        "review": {
            "review_status": "draft",
            "revision": 1,
            "locked": False,
            "reviewer_note": None,
            "updated_at": now_iso,
            "source_hash": content_hash,
        },
    }


def sync_scene_content(
    hs: Dict[str, Any],
    sc: Dict[str, Any],
    speaker_map: Dict[str, str],
    unlock: bool = False,
    force: bool = False,
) -> Tuple[bool, str]:
    """
    同步單個場景內容（動作、對白、場頭、角色與改編元數據）。
    回傳 (has_changed, message)。若因鎖定被攔截則拋出 PermissionError。
    """
    scene_id = hs.get("scene_id", "未知場景")
    review = hs.setdefault("review", {
        "review_status": "draft",
        "revision": 1,
        "locked": False,
        "reviewer_note": None,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "source_hash": "",
    })

    old_actions = list(hs.get("action_beats") or [])
    new_actions = [a["text"] for a in sc.get("actions", [])]

    old_dialogues = list(hs.get("dialogue") or [])
    new_script_dialogues = sc.get("dialogues", [])

    actions_changed = (old_actions != new_actions)
    dialogues_changed = False
    if len(old_dialogues) != len(new_script_dialogues):
        dialogues_changed = True
    else:
        for od, nd in zip(old_dialogues, new_script_dialogues):
            if od.get("text") != nd.get("text"):
                dialogues_changed = True
                break

    setting = hs.setdefault("setting", {})
    setting_changed = False
    new_loc = sc.get("location", "")
    if new_loc and setting.get("location") in ("TODO", "<場景名>", "", None) and setting.get("location") != new_loc:
        setting_changed = True
    new_time_en = time_to_en(sc.get("time", ""))
    if new_time_en != "unknown" and setting.get("time") != new_time_en:
        setting_changed = True

    char_names = sc.get("characters", [])
    mapped_chars = [speaker_map.get(c, c) for c in char_names if c]
    old_chars = hs.get("characters", [])
    chars_changed = False
    if mapped_chars and old_chars != mapped_chars:
        chars_changed = True

    meta_changed = False
    if sc.get("source_refs") and hs.get("source_refs") != sc["source_refs"]:
        meta_changed = True
    if sc.get("must_keep_ids") and hs.get("must_keep_ids") != sc["must_keep_ids"]:
        meta_changed = True
    if sc.get("adaptation_changes") and hs.get("adaptation_changes") != sc["adaptation_changes"]:
        meta_changed = True

    if not actions_changed and not dialogues_changed and not setting_changed and not chars_changed and not meta_changed:
        return False, f"[{scene_id}] 內容未變更，略過同步"

    is_locked = review.get("locked", False) or review.get("review_status") == "approved"
    if is_locked and not (unlock or force):
        raise PermissionError(
            f"[鎖定攔截] 場景 {scene_id} 處於核准或鎖定狀態 "
            f"(status={review.get('review_status')}, locked={review.get('locked')})，"
            f"劇本同步被拒絕！若確定修改請加上 --unlock 或 --force。"
        )

    hs["action_beats"] = new_actions
    if "storyboard_handoff" in hs and "required_visual_beats" in hs["storyboard_handoff"]:
        hs["storyboard_handoff"]["required_visual_beats"] = list(new_actions)

    synced_dialogues: List[Dict[str, Any]] = []
    for idx, nd in enumerate(new_script_dialogues):
        speaker_name = nd.get("speaker", "")
        mapped_speaker = speaker_map.get(speaker_name, speaker_name)
        existing_dlg = old_dialogues[idx] if idx < len(old_dialogues) else {}
        spk = existing_dlg.get("speaker") or mapped_speaker
        audio_t = detect_audio_type(nd.get("note", ""), existing_dlg.get("audio_type", "onscreen"))
        item: Dict[str, Any] = {
            "speaker": spk,
            "text": nd.get("text", ""),
            "audio_type": audio_t,
        }
        if nd.get("note"):
            item["delivery_note"] = nd["note"]
        elif "delivery_note" in existing_dlg:
            item["delivery_note"] = existing_dlg["delivery_note"]
        synced_dialogues.append(item)

    hs["dialogue"] = synced_dialogues
    hs["dialogue_blocks"] = list(synced_dialogues)

    if new_loc:
        setting["location"] = new_loc
        hs["location"] = new_loc
    if new_time_en != "unknown":
        setting["time"] = new_time_en
        hs["time_of_day"] = sc.get("time", "")
    if sc.get("int_ext"):
        setting["interior"] = ("內" in sc["int_ext"] or "内" in sc["int_ext"])
        hs["int_ext"] = sc["int_ext"]
    if sc.get("timeline_tag"):
        setting["timeline_tag"] = "flashback" if any(k in sc["timeline_tag"] for k in ["閃回", "回憶", "flashback"]) else "present"

    heading_str = f"{sc.get('scene_num', '')} {sc.get('location', '')} {sc.get('time', '')}/{sc.get('int_ext', '')}".strip()
    hs["heading"] = heading_str

    if mapped_chars:
        hs["characters"] = list(mapped_chars)
        hs["characters_present"] = list(mapped_chars)

    # 注入元數據
    if sc.get("source_refs"):
        hs["source_refs"] = list(sc["source_refs"])
        hs["source_unit_ids"] = list(sc["source_refs"])
    if sc.get("must_keep_ids"):
        hs["must_keep_ids"] = list(sc["must_keep_ids"])
    if sc.get("adaptation_changes"):
        hs["adaptation_changes"] = list(sc["adaptation_changes"])
    elif sc.get("source_refs") and not hs.get("adaptation_changes"):
        hs["adaptation_changes"] = [
            {
                "type": "must_keep" if r in hs.get("must_keep_ids", []) else "keep_if_possible",
                "source_ref": r,
                "description": f"場景保留原著單元 {r}",
                "is_adaptation_addition": False,
            }
            for r in sc["source_refs"]
        ]

    dlg_chars = sum(len(d["text"]) for d in synced_dialogues)
    est_dur = max(10.0, round(dlg_chars / 4.0 + len(new_actions) * 2.5, 1))
    hs["estimated_duration_seconds"] = {"min": max(5, round(est_dur * 0.8)), "max": max(10, round(est_dur * 1.2))}
    hs["estimated_duration_s"] = est_dur

    hs.setdefault("source_unit_ids", hs.get("source_refs", []))
    hs.setdefault("must_keep_ids", [])

    current_rev = review.get("revision", 1)
    review["revision"] = current_rev + 1
    review["review_status"] = "pending_review"
    review["locked"] = False
    review["updated_at"] = datetime.now(timezone.utc).isoformat()
    review["source_hash"] = compute_content_hash(new_actions, synced_dialogues)

    return True, f"[{scene_id}] 成功同步（版號升至 rev {review['revision']}，狀態設為 pending_review）"


def update_scene_review_status(
    hs: Dict[str, Any],
    set_status: Optional[str] = None,
    note: Optional[str] = None,
    lock: bool = False,
    unlock: bool = False,
) -> bool:
    """更新場景審核簽核狀態。"""
    review = hs.setdefault("review", {
        "review_status": "draft",
        "revision": 1,
        "locked": False,
        "reviewer_note": None,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "source_hash": "",
    })

    changed = False
    if set_status:
        review["review_status"] = set_status
        changed = True
        if set_status == "approved":
            review["locked"] = True
        elif set_status in ("rejected", "draft", "pending_review"):
            review["locked"] = False

    if lock:
        review["locked"] = True
        changed = True
    elif unlock:
        review["locked"] = False
        changed = True

    if note is not None:
        review["reviewer_note"] = note
        changed = True

    if changed:
        review["updated_at"] = datetime.now(timezone.utc).isoformat()
        if "revision" not in review or review["revision"] < 1:
            review["revision"] = 1

    return changed


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="劇本與 Handoff JSON 局部同步與人工審核工具")
    parser.add_argument("--handoff", type=Path, required=True, help="Handoff JSON 檔案路徑")
    parser.add_argument("--script", type=Path, default=None, help="Markdown 劇本檔案路徑 (script-epNN.md)")
    parser.add_argument("--source", type=Path, default=None, help="選填：原著結構化分析 JSON (source.json)，用於自動配對未標註單元")
    parser.add_argument("--episode", type=str, default=None, help="選填：指定集數代號（例如 EP01, EP02）；若 handoff 檔案不存在時用於初始化")
    parser.add_argument("--scene", type=str, default=None, help="指定單一場景 ID（例如 EP01-S01）；未指定時處理全劇本")
    parser.add_argument("--set-status", choices=["draft", "pending_review", "approved", "rejected"], help="設定審核狀態")
    parser.add_argument("--note", type=str, default=None, help="審核人員備註 (reviewer_note)")
    parser.add_argument("--lock", action="store_true", help="強制鎖定場景")
    parser.add_argument("--unlock", action="store_true", help="解除場景鎖定")
    parser.add_argument("--force", action="store_true", help="忽略鎖定強制覆蓋修改")
    parser.add_argument("--prune-extra", action="store_true", help="若劇本場景數少於 Handoff，自動清理多出的未鎖定場景")
    args = parser.parse_args()

    # 1. 處理 handoff 檔案是否存在或需要從零初始化
    handoff_data: Dict[str, Any] = {}
    if not args.handoff.exists():
        if not args.script:
            print(f"[錯誤] 找不到 handoff 檔案：{args.handoff}，且未提供 --script 無法從零建立", file=sys.stderr)
            return 1
        print(f"[提示] 目標 Handoff 檔案不存在：{args.handoff}，將依據劇本從零自動建立！")
        ep_id = args.episode
        if not ep_id:
            m = re.search(r"ep(\d+)", args.handoff.name, re.IGNORECASE)
            if not m and args.script:
                m = re.search(r"ep(\d+)", args.script.name, re.IGNORECASE)
            if m:
                ep_id = f"EP{int(m.group(1)):02d}"
            else:
                ep_id = "EP01"
        else:
            if not ep_id.upper().startswith("EP"):
                ep_id = f"EP{int(re.sub(r'[^0-9]', '', ep_id) or '1'):02d}"
            else:
                ep_id = ep_id.upper()

        parent_dir = args.handoff.parent
        proj_id = "project"
        for sibling in parent_dir.glob("handoff-*.json"):
            try:
                sib_data = json.loads(sibling.read_text(encoding="utf-8"))
                if sib_data.get("project_id"):
                    proj_id = sib_data["project_id"]
                    break
            except Exception:
                pass
        if proj_id == "project" and parent_dir.name:
            proj_id = re.sub(r"[^a-z0-9]+", "-", parent_dir.name.lower()).strip("-") or "project"

        ep_num_int = int(re.sub(r"[^0-9]", "", ep_id) or "1")
        handoff_data = {
            "project_id": proj_id,
            "rights_status": "unconfirmed",
            "adaptation_mode": "balanced",
            "genre_mode": "healing_literary",
            "aspect_ratio": "9:16",
            "target_medium": "ai_animation",
            "episodes": [{
                "episode_id": ep_id,
                "title": f"第{ep_num_int:02d}集",
                "target_duration_seconds": 90,
                "episode_goal": "TODO",
                "act_out_type": "jeopardy_cliffhanger",
                "scenes": [],
            }],
        }
    else:
        try:
            handoff_data = json.loads(args.handoff.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"[錯誤] Handoff JSON 解析失敗：{exc}", file=sys.stderr)
            return 1

    all_scenes: List[Dict[str, Any]] = [
        s for ep in handoff_data.get("episodes", []) for s in ep.get("scenes", [])
    ]

    target_scenes = all_scenes
    if args.scene:
        target_scenes = [s for s in all_scenes if s.get("scene_id") == args.scene]
        if not target_scenes and args.handoff.exists():
            print(f"[錯誤] 在 Handoff 中找不到指定的場景 ID: {args.scene}", file=sys.stderr)
            return 1

    # 2. 處理純審核指令
    review_changed = False
    if args.set_status or args.note is not None or args.lock or args.unlock:
        for s in target_scenes:
            if update_scene_review_status(s, args.set_status, args.note, args.lock, args.unlock):
                review_changed = True
                sid = s.get("scene_id")
                rev_st = s["review"].get("review_status")
                lck = s["review"].get("locked")
                print(f"[審核更新] {sid}: 狀態={rev_st}, locked={lck}, note={s['review'].get('reviewer_note')}")

    # 3. 處理劇本同步
    sync_performed = False
    if args.script:
        if not args.script.exists():
            print(f"[錯誤] 找不到劇本檔案：{args.script}", file=sys.stderr)
            return 1

        script_text = args.script.read_text(encoding="utf-8")
        parsed = parse_and_validate_script(script_text)
        if parsed.get("errors"):
            print(f"[警告] 劇本包含格式問題，但仍嘗試解析：{len(parsed['errors'])} 項錯誤", file=sys.stderr)
            for err in parsed["errors"]:
                print(f"  - {err}", file=sys.stderr)

        script_scenes = parsed.get("scenes", [])

        # 若指定了 --source，執行自動配對未標註之單元
        if args.source and args.source.exists():
            try:
                s_data = json.loads(args.source.read_text(encoding="utf-8"))
                auto_match_source_units(script_scenes, s_data)
            except Exception as s_err:
                print(f"[警告] 讀取 --source 檔案失敗：{s_err}", file=sys.stderr)

        # 讀取 Story Bible 建立角色映射
        bible_char_map: Dict[str, str] = {}
        for bp in [args.handoff.parent / "adapt" / "bible.json", args.handoff.parent / "bible.json"]:
            if bp.exists():
                try:
                    bdata = json.loads(bp.read_text(encoding="utf-8"))
                    for ch in bdata.get("characters", []):
                        cid = ch.get("character_id")
                        cname = ch.get("canonical_name")
                        if cid and cname:
                            bible_char_map[cname] = cid
                        for alias in ch.get("aliases", []):
                            if cid:
                                bible_char_map[alias] = cid
                except Exception:
                    pass

        speaker_map = build_speaker_map(script_scenes, all_scenes)
        for k, v in bible_char_map.items():
            if k not in speaker_map:
                speaker_map[k] = v

        episodes = handoff_data.setdefault("episodes", [])
        if not episodes:
            episodes.append({
                "episode_id": "EP01",
                "title": "第01集",
                "target_duration_seconds": 90,
                "episode_goal": "TODO",
                "act_out_type": "jeopardy_cliffhanger",
                "scenes": [],
            })
        current_ep = episodes[0]
        if args.episode:
            for ep in episodes:
                if ep.get("episode_id", "").upper() == args.episode.upper():
                    current_ep = ep
                    break

        if args.scene:
            # 單一場景模式
            hs = target_scenes[0]
            sc = match_script_scene(script_scenes, hs, 0)
            if not sc:
                print(f"[錯誤] 找不到與 {args.scene} 相符的劇本段落", file=sys.stderr)
                return 1
            try:
                changed, msg = sync_scene_content(hs, sc, speaker_map, unlock=args.unlock, force=args.force)
                print(msg)
                if changed:
                    sync_performed = True
            except PermissionError as p_err:
                print(str(p_err), file=sys.stderr)
                return 1
        else:
            # 全集同步模式（支援場景擴展、從零建立與清理）
            current_ep_scenes = current_ep.setdefault("scenes", [])
            matched_pairs: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []
            unmatched_script_scenes: List[Dict[str, Any]] = []
            used_handoff_scene_ids = set()

            for sc_idx, sc in enumerate(script_scenes):
                sc_num = sc.get("scene_num", "")
                sc_pair = get_scene_number_from_id(sc_num)

                found_hs = None
                for hs in current_ep_scenes:
                    if hs.get("scene_id") in used_handoff_scene_ids:
                        continue
                    hs_pair = get_scene_number_from_id(hs.get("scene_id", ""))
                    if sc_pair and hs_pair and sc_pair == hs_pair:
                        found_hs = hs
                        break
                    if hs.get("scene_id") == sc_num:
                        found_hs = hs
                        break

                if not found_hs and sc_idx < len(current_ep_scenes):
                    cand = current_ep_scenes[sc_idx]
                    if cand.get("scene_id") not in used_handoff_scene_ids:
                        found_hs = cand

                if found_hs:
                    matched_pairs.append((found_hs, sc))
                    used_handoff_scene_ids.add(found_hs.get("scene_id"))
                else:
                    unmatched_script_scenes.append(sc)

            # 1. 同步已配對場景
            for hs, sc in matched_pairs:
                try:
                    changed, msg = sync_scene_content(hs, sc, speaker_map, unlock=args.unlock, force=args.force)
                    print(msg)
                    if changed:
                        sync_performed = True
                except PermissionError as p_err:
                    print(str(p_err), file=sys.stderr)
                    return 1

            # 2. 自動為多出的劇本場景新增 handoff 場景物件
            project_id = handoff_data.get("project_id", "project")
            ep_tag = current_ep.get("episode_id", "EP01")
            adaptation_mode = handoff_data.get("adaptation_mode", "balanced")

            existing_scene_ids = {s.get("scene_id") for s in current_ep_scenes}
            for sc in unmatched_script_scenes:
                sc_pair = get_scene_number_from_id(sc.get("scene_num", ""))
                if sc_pair:
                    target_sid = f"EP{sc_pair[0]:02d}-S{sc_pair[1]:02d}"
                else:
                    target_sid = f"{ep_tag}-S{len(current_ep_scenes) + 1:02d}"

                seq = 1
                base_sid = target_sid
                while target_sid in existing_scene_ids:
                    target_sid = f"{base_sid}_{seq}"
                    seq += 1

                new_hs = create_handoff_scene_from_script(
                    sc, project_id, ep_tag, target_sid, speaker_map, adaptation_mode
                )
                current_ep_scenes.append(new_hs)
                existing_scene_ids.add(target_sid)
                print(f"[新增場景] {target_sid} ({sc.get('scene_num')} {sc.get('location')}) 成功自劇本建立並加入 Handoff")
                sync_performed = True

            # 3. 檢查並處理劇本場景少於 handoff 場景的情況
            extra_old_scenes = [
                hs for hs in list(current_ep_scenes)
                if hs.get("scene_id") not in used_handoff_scene_ids
                and hs not in [p[0] for p in matched_pairs]
                and hs not in [s for s in current_ep_scenes if s.get("scene_id") in existing_scene_ids and s not in all_scenes]
            ]
            if extra_old_scenes:
                extra_ids = [s.get("scene_id", "未知") for s in extra_old_scenes]
                if args.prune_extra:
                    for s in extra_old_scenes:
                        r = s.get("review", {})
                        if r.get("locked") or r.get("review_status") == "approved":
                            print(
                                f"[鎖定攔截] 多餘場景 {s.get('scene_id')} 已鎖定或已審核通過 (status={r.get('review_status')})，"
                                f"拒絕自動清理！若確定刪除請先解除鎖定或手動調整劇本。",
                                file=sys.stderr,
                            )
                            return 1
                    for s in extra_old_scenes:
                        current_ep_scenes.remove(s)
                        print(f"[清理多餘場景] 已自 Handoff 移除多餘場景 {s.get('scene_id')}")
                        sync_performed = True
                else:
                    print(
                        f"[提示] 劇本場景數 ({len(script_scenes)}) 少於 Handoff 場景數 ({len(current_ep_scenes)})。"
                        f"多出場景：{', '.join(extra_ids)}。若需自動清理未鎖定的多餘場景，請加上 --prune-extra 參數。"
                    )

    if review_changed or sync_performed:
        args.handoff.write_text(json.dumps(handoff_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"已成功將變更寫回 {args.handoff}")
    else:
        print("未進行任何檔案變更。")

    return 0


if __name__ == "__main__":
    sys.exit(main())
