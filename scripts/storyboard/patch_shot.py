#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_shot.py — Layer 2 分鏡單鏡局部修改與人工審核（HITL）簽核工具

功能：
1. 針對 layer2/*.json 中的指定鏡頭進行局部精準修改（景別、焦段、運鏡、動作階段、台詞、秒數、草圖檔等）。
2. 核心保護機制：已鎖定鏡頭（locked=True 或 review_status='approved'）禁止修改，未帶 --unlock 立即拒絕並回傳非 0 退出碼。
3. 未修改鏡頭 100% 原封不動保留（包括其 review 狀態、sketch_file、image_file、video_file）。
4. 修改秒數時自動重算整段鏡頭的 start_time 與 end_time（保持連續性），可選擇 --absorb-from 從指定未鎖定鏡頭吸收差額。
5. 修改後自動升版號 (revision +1)、重算 shot_hash、將 review_status 設為 pending_review、重設 status 為 pending。
6. 支援單鏡簽核與全段簽核 (--approve-all)。
7. 支援 --out-md 同步更新 Markdown 分鏡表。

僅使用 Python 標準庫。
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
from layer2_to_table import check_one, render_md  # noqa: E402


def compute_shot_hash(shot: Dict[str, Any]) -> str:
    """計算單鏡核心內容的 SHA256 前 8 碼雜湊值。"""
    payload = {
        "duration": shot.get("duration"),
        "camera_optics": shot.get("camera_optics"),
        "spatial_blocking": shot.get("spatial_blocking"),
        "action_and_performance": shot.get("action_and_performance"),
        "dialogue_and_audio": shot.get("dialogue_and_audio"),
    }
    dumped = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(dumped.encode("utf-8")).hexdigest()[:8]


def find_target_shot(shots: List[Dict[str, Any]], target_id: str) -> Optional[Dict[str, Any]]:
    """比對目標鏡頭：優先全等比對，次之比對後綴（如 target='SH01' 匹配 'EP01-S01-a-SH01'）。"""
    for s in shots:
        sid = s.get("shot_id", "")
        if sid == target_id:
            return s
    for s in shots:
        sid = s.get("shot_id", "")
        if sid.endswith("-" + target_id) or sid.endswith("_" + target_id):
            return s
    return None


def recalculate_timeline(shots: List[Dict[str, Any]]) -> None:
    """從 0.0 起重新計算各鏡頭的 start_time 與 end_time，確保時間軸精確連續無縫。"""
    cur_time = 0.0
    for s in shots:
        dur = round(float(s["duration"]), 2)
        s["start_time"] = round(cur_time, 2)
        s["end_time"] = round(cur_time + dur, 2)
        cur_time = s["end_time"]


def parse_action_stages(raw: str) -> List[str]:
    """解析動作階段：支援 JSON 陣列或以 '|' 分隔字串。"""
    raw = raw.strip()
    if raw.startswith("[") and raw.endswith("]"):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(x) for x in parsed]
        except Exception:
            pass
    return [s.strip() for s in raw.split("|") if s.strip()]


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Layer 2 單鏡局部修改與人工審核工具")
    parser.add_argument("file", type=Path, help="待修改的 Layer 2 分鏡 JSON 檔案")
    parser.add_argument("--shot", type=str, help="目標鏡頭 ID（例如 SH01 或 EP01-S01-a-SH01）")

    # 審核簽核參數
    parser.add_argument("--set-status", choices=["draft", "pending_review", "approved", "rejected"], help="設定審核狀態")
    parser.add_argument("--note", type=str, default=None, help="審核人員備註")
    parser.add_argument("--lock", action="store_true", help="強制鎖定目標鏡頭")
    parser.add_argument("--unlock", action="store_true", help="解除目標鏡頭鎖定")
    parser.add_argument("--approve-all", action="store_true", help="整段全部鏡頭核准簽核並鎖定")

    # 單鏡內容局部修改參數
    parser.add_argument("--duration", type=float, help="修改單鏡秒數（float，需 >= 0.5）")
    parser.add_argument("--absorb-from", type=str, help="從指定鏡頭吸收秒數差額以維持總時長不變")
    parser.add_argument("--shot-size", type=str, help="修改景別 (ELS/LS/MLS/MS/MCU/CU/ECU/OTS_MS/OTS_CU)")
    parser.add_argument("--focal-length", type=str, help="修改焦段 (14mm/24mm/35mm/50mm/85mm/100mm/135mm)")
    parser.add_argument("--distance", type=str, help="修改物理物距描述 (physical_distance)")
    parser.add_argument("--movement", type=str, help="修改運鏡描述 (movement)")
    parser.add_argument("--pov-routing", type=str, help="修改視角規劃 (pov_routing)")
    parser.add_argument("--blocking", type=str, help="修改走位描述 (blocking_desc)")
    parser.add_argument("--action-stages", type=str, help="修改動作階段 (JSON 陣列或以 '|' 分隔)")
    parser.add_argument("--expression", type=str, help="修改可見神情外顯 (observable_expression)")
    parser.add_argument("--dialogue", type=str, help="修改對白原文 (line_verbatim)")
    parser.add_argument("--sketch-file", type=str, help="指定該鏡 1:1 鉛筆草圖檔案路徑")

    # 輸出參數
    parser.add_argument("--out-md", type=Path, help="同步輸出 Markdown 分鏡表至指定路徑")
    parser.add_argument("--check", action="store_true", help="修改後執行 layer2 結構與秒數驗證")

    args = parser.parse_args()

    if not args.file.exists():
        print(f"[錯誤] 找不到檔案：{args.file}", file=sys.stderr)
        return 1

    try:
        data = json.loads(args.file.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"[錯誤] JSON 解析失敗：{exc}", file=sys.stderr)
        return 1

    shots: List[Dict[str, Any]] = data.get("shots", [])
    if not shots:
        print("[錯誤] 分鏡資料中無 shots 陣列", file=sys.stderr)
        return 1

    # 判斷是否為整段簽核
    if args.approve_all:
        now_iso = datetime.now(timezone.utc).isoformat()
        for s in shots:
            rev = s.setdefault("review", {})
            rev["review_status"] = "approved"
            rev["locked"] = True
            rev["updated_at"] = now_iso
            if args.note:
                rev["reviewer_note"] = args.note
            if "revision" not in rev or rev["revision"] < 1:
                rev["revision"] = 1
            if "shot_hash" not in rev:
                rev["shot_hash"] = compute_shot_hash(s)

        top_rev = data.setdefault("review", {})
        top_rev["review_status"] = "approved"
        top_rev["locked"] = True
        top_rev["updated_at"] = now_iso
        if args.note:
            top_rev["reviewer_note"] = args.note
        if "revision" not in top_rev or top_rev["revision"] < 1:
            top_rev["revision"] = 1

        args.file.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"[簽核完成] 已將 {args.file.name} 整段共 {len(shots)} 顆鏡頭設為 approved (已鎖定)")

        if args.out_md:
            args.out_md.write_text(render_md(data), encoding="utf-8")
            print(f"已同步寫入 Markdown 分鏡表：{args.out_md}")
        return 0

    if not args.shot:
        print("[錯誤] 請指定 --shot <shot_id> 或使用 --approve-all", file=sys.stderr)
        return 1

    target_shot = find_target_shot(shots, args.shot)
    if not target_shot:
        print(f"[錯誤] 在 {args.file.name} 中找不到鏡頭 {args.shot}", file=sys.stderr)
        return 1

    sid = target_shot.get("shot_id", args.shot)
    review = target_shot.setdefault("review", {
        "review_status": "draft",
        "revision": 1,
        "locked": False,
        "reviewer_note": None,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "shot_hash": compute_shot_hash(target_shot),
    })

    # 檢測是否有修改內容
    content_change_requested = any([
        args.duration is not None,
        args.shot_size is not None,
        args.focal_length is not None,
        args.distance is not None,
        args.movement is not None,
        args.pov_routing is not None,
        args.blocking is not None,
        args.action_stages is not None,
        args.expression is not None,
        args.dialogue is not None,
        args.sketch_file is not None,
    ])

    # 核心保護機制：已鎖定或 approved 狀態下修改內容，必須帶 --unlock
    is_locked = review.get("locked", False) or review.get("review_status") == "approved"
    if content_change_requested and is_locked and not args.unlock:
        print(
            f"[鎖定攔截] 鏡頭 {sid} 處於鎖定/核准狀態 "
            f"(status={review.get('review_status')}, locked={review.get('locked')})！"
            f"嚴禁修改已核准內容。若確定修改，請帶上 --unlock 參數解鎖。",
            file=sys.stderr,
        )
        return 1

    modified_fields: List[str] = []

    # 執行內容修改
    if args.duration is not None:
        new_dur = round(args.duration, 2)
        if new_dur < 0.5:
            print(f"[錯誤] 鏡頭秒數 {new_dur} 低於最小值 0.5s", file=sys.stderr)
            return 1

        old_dur = float(target_shot.get("duration", 0.0))
        delta = round(new_dur - old_dur, 2)

        if args.absorb_from:
            absorb_shot = find_target_shot(shots, args.absorb_from)
            if not absorb_shot:
                print(f"[錯誤] 找不到指定吸收秒數的鏡頭：{args.absorb_from}", file=sys.stderr)
                return 1
            if absorb_shot is target_shot:
                print("[錯誤] 不能指定目標鏡頭自己作為吸收鏡頭", file=sys.stderr)
                return 1

            absorb_rev = absorb_shot.get("review", {})
            if absorb_rev.get("locked") and not args.unlock:
                print(f"[錯誤] 吸收鏡頭 {absorb_shot['shot_id']} 已鎖定，無法調整其秒數", file=sys.stderr)
                return 1

            absorb_cur_dur = float(absorb_shot["duration"])
            absorb_new_dur = round(absorb_cur_dur - delta, 2)
            if absorb_new_dur < 0.5:
                print(
                    f"[錯誤] 吸收鏡頭 {absorb_shot['shot_id']} 扣除差額 ({delta}s) 後秒數為 {absorb_new_dur}s (<0.5s)，無法吸收",
                    file=sys.stderr,
                )
                return 1

            absorb_shot["duration"] = absorb_new_dur
            target_shot["duration"] = new_dur
            recalculate_timeline(shots)
            modified_fields.append(f"duration ({old_dur}s -> {new_dur}s，由 {absorb_shot['shot_id']} 吸收)")
        else:
            target_shot["duration"] = new_dur
            recalculate_timeline(shots)
            new_total = round(sum(s["duration"] for s in shots), 2)
            data["metadata"]["target_duration_sec"] = new_total
            modified_fields.append(f"duration ({old_dur}s -> {new_dur}s，總時長更新為 {new_total}s)")

    if args.shot_size is not None:
        target_shot["camera_optics"]["shot_size"] = args.shot_size
        modified_fields.append(f"shot_size={args.shot_size}")

    if args.focal_length is not None:
        target_shot["camera_optics"]["focal_length"] = args.focal_length
        modified_fields.append(f"focal_length={args.focal_length}")

    if args.distance is not None:
        target_shot["camera_optics"]["physical_distance"] = args.distance
        modified_fields.append(f"distance={args.distance}")

    if args.movement is not None:
        target_shot["camera_optics"]["movement"] = args.movement
        modified_fields.append(f"movement={args.movement}")

    if args.pov_routing is not None:
        target_shot["camera_optics"]["pov_routing"] = args.pov_routing
        modified_fields.append(f"pov_routing={args.pov_routing}")

    if args.blocking is not None:
        target_shot["spatial_blocking"]["blocking_desc"] = args.blocking
        modified_fields.append("blocking")

    if args.action_stages is not None:
        stages = parse_action_stages(args.action_stages)
        if len(stages) > 5:
            print(f"[錯誤] 單鏡動作拆解達 {len(stages)} 階段，超過上限 5 階段！", file=sys.stderr)
            return 1
        target_shot["action_and_performance"]["action_stages"] = stages
        modified_fields.append(f"action_stages (共 {len(stages)} 階段)")

    if args.expression is not None:
        target_shot["action_and_performance"]["observable_expression"] = args.expression
        modified_fields.append(f"expression={args.expression}")

    if args.dialogue is not None:
        dlg = target_shot.setdefault("dialogue_and_audio", {})
        if args.dialogue.lower() in ("—", "none", "", "null", "false"):
            dlg["has_dialogue"] = False
            dlg["line_verbatim"] = None
            dlg["lips_closed_lock"] = True
            modified_fields.append("dialogue (清除台詞)")
        else:
            dlg["has_dialogue"] = True
            dlg["line_verbatim"] = args.dialogue
            dlg["lips_closed_lock"] = False
            modified_fields.append(f"dialogue=「{args.dialogue}」")

    if args.sketch_file is not None:
        target_shot["sketch_file"] = args.sketch_file
        modified_fields.append(f"sketch_file={args.sketch_file}")

    # 若內容有修改，自動更新版號與狀態
    if content_change_requested:
        review["revision"] = review.get("revision", 1) + 1
        review["review_status"] = "pending_review"
        review["locked"] = False
        review["updated_at"] = datetime.now(timezone.utc).isoformat()
        review["shot_hash"] = compute_shot_hash(target_shot)
        target_shot["status"] = "pending"  # 重置生成進度

        # 頂層 review 同步標記為待審
        top_rev = data.setdefault("review", {})
        top_rev["review_status"] = "pending_review"
        top_rev["locked"] = False
        top_rev["updated_at"] = datetime.now(timezone.utc).isoformat()

    # 處理審核簽核指令
    if args.set_status:
        review["review_status"] = args.set_status
        if args.set_status == "approved":
            review["locked"] = True
        elif args.set_status in ("rejected", "draft", "pending_review"):
            review["locked"] = False
        modified_fields.append(f"review_status={args.set_status}")

    if args.lock:
        review["locked"] = True
        modified_fields.append("locked=True")
    elif args.unlock and not content_change_requested:
        review["locked"] = False
        modified_fields.append("locked=False")

    if args.note is not None:
        review["reviewer_note"] = args.note
        modified_fields.append("reviewer_note")

    if modified_fields:
        review["updated_at"] = datetime.now(timezone.utc).isoformat()

    # 執行檢查
    if args.check:
        errors = check_one(data)
        if errors:
            print("[驗證失敗] 修改後的資料未通過驗證：", file=sys.stderr)
            for err in errors:
                print(f"  - {err}", file=sys.stderr)
            return 1

    # 寫入檔案
    args.file.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[成功更新] 鏡頭 {sid}: {', '.join(modified_fields) if modified_fields else '無變更'}")
    print(f"目前狀態: review_status={review.get('review_status')}, rev={review.get('revision')}, locked={review.get('locked')}")

    if args.out_md:
        args.out_md.write_text(render_md(data), encoding="utf-8")
        print(f"已同步更新 Markdown 分鏡表：{args.out_md}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
