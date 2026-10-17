#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sync_script.py — 漫劇劇本與 Handoff JSON 局部同步與人工審核（HITL）工具

功能：
1. 將 human-edited script-epNN.md 的對白與 △ 動作行局部同步更新至 handoff-epNN.json。
2. 保護機制：若場景已鎖定 (locked=True 或 review_status='approved') 且內容有變動，預設拒絕同步並報錯退出（除非帶 --unlock 或 --force）。
3. 自動更新版號 (revision +1)、source_hash (SHA256 前 8 碼)、updated_at，並重設為 pending_review。
4. 提供 CLI 人工審核簽核指令：--scene <id> --set-status {draft,pending_review,approved,rejected} --note <text>。
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


def sync_scene_content(
    hs: Dict[str, Any],
    sc: Dict[str, Any],
    speaker_map: Dict[str, str],
    unlock: bool = False,
    force: bool = False,
) -> Tuple[bool, str]:
    """
    同步單個場景內容。
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

    # 檢測是否有變更
    actions_changed = (old_actions != new_actions)
    dialogues_changed = False
    if len(old_dialogues) != len(new_script_dialogues):
        dialogues_changed = True
    else:
        for od, nd in zip(old_dialogues, new_script_dialogues):
            if od.get("text") != nd.get("text"):
                dialogues_changed = True
                break

    if not actions_changed and not dialogues_changed:
        return False, f"[{scene_id}] 內容未變更，略過同步"

    # 檢查保護機制
    is_locked = review.get("locked", False) or review.get("review_status") == "approved"
    if is_locked and not (unlock or force):
        raise PermissionError(
            f"[鎖定攔截] 場景 {scene_id} 處於核准或鎖定狀態 "
            f"(status={review.get('review_status')}, locked={review.get('locked')})，"
            f"劇本同步被拒絕！若確定修改請加上 --unlock 或 --force。"
        )

    # 執行更新
    hs["action_beats"] = new_actions
    if "storyboard_handoff" in hs and "required_visual_beats" in hs["storyboard_handoff"]:
        hs["storyboard_handoff"]["required_visual_beats"] = list(new_actions)

    # 更新 dialogue 陣列
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

    # 更新版本資訊與審核狀態
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
    parser.add_argument("--scene", type=str, default=None, help="指定單一場景 ID（例如 EP01-S01）；未指定時處理全劇本")
    parser.add_argument("--set-status", choices=["draft", "pending_review", "approved", "rejected"], help="設定審核狀態")
    parser.add_argument("--note", type=str, default=None, help="審核人員備註 (reviewer_note)")
    parser.add_argument("--lock", action="store_true", help="強制鎖定場景")
    parser.add_argument("--unlock", action="store_true", help="解除場景鎖定")
    parser.add_argument("--force", action="store_true", help="忽略鎖定強制覆蓋修改")
    args = parser.parse_args()

    if not args.handoff.exists():
        print(f"[錯誤] 找不到 handoff 檔案：{args.handoff}", file=sys.stderr)
        return 1

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
        if not target_scenes:
            print(f"[錯誤] 在 Handoff 中找不到指定的場景 ID: {args.scene}", file=sys.stderr)
            return 1

    # 1. 處理純審核指令
    review_changed = False
    if args.set_status or args.note is not None or args.lock or args.unlock:
        for s in target_scenes:
            if update_scene_review_status(s, args.set_status, args.note, args.lock, args.unlock):
                review_changed = True
                sid = s.get("scene_id")
                rev_st = s["review"].get("review_status")
                lck = s["review"].get("locked")
                print(f"[審核更新] {sid}: 狀態={rev_st}, locked={lck}, note={s['review'].get('reviewer_note')}")

    # 2. 處理劇本同步
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
        speaker_map = build_speaker_map(script_scenes, all_scenes)

        for idx, hs in enumerate(all_scenes):
            if args.scene and hs.get("scene_id") != args.scene:
                continue

            sc = match_script_scene(script_scenes, hs, idx)
            if not sc:
                print(f"[警告] 找不到與 {hs.get('scene_id')} 相符的劇本段落，略過", file=sys.stderr)
                continue

            try:
                changed, msg = sync_scene_content(hs, sc, speaker_map, unlock=args.unlock, force=args.force)
                print(msg)
                if changed:
                    sync_performed = True
            except PermissionError as p_err:
                print(str(p_err), file=sys.stderr)
                return 1

    if review_changed or sync_performed:
        args.handoff.write_text(json.dumps(handoff_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"已成功將變更寫回 {args.handoff}")
    else:
        print("未進行任何檔案變更。")

    return 0


if __name__ == "__main__":
    sys.exit(main())
