#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""`h3d seamcheck`：階段 6 接點自檢包（給人或視覺模型判讀，工具本身不判定）。

`transition_lint`（D15–D24）只看分鏡文字；畫面有沒有照做要看影片。這支工具對每個接點產兩樣東西：

1. **接點對照圖**（一個接點一張 PNG）：
   - 段縫：上段最後一格｜本段第一格（本段有 `lead_in_s` 拋棄式前導時，改抽前導結束後的第一格，和成片一致）；
   - 段內切：切前一格｜切後一格。切點用 `continuity_qa` 同一套方法在規劃切點 ±window 內找實際切點，
     找不到就用規劃秒數，並在清單標 `cut_found: false`。
2. **檢查清單 JSON**（`seamcheck.json`）：每個接點列出分鏡寫的預期值（兩側景別、人數、左到右、背景錨點、
   cut_in／seam_in、exit_state／entry_state、beats）與待填欄位 `checks`（人數、左右、錨點、是否重演、
   是否照分鏡景別），全部預設 `null`，由人或視覺模型看圖後填 `true／false／"unsure"`。

工具**不做自動判定、不呼叫任何模型 API**，也不改門禁：不寫 qa-report.json、verdicts、核准快照；
結束碼只反映執行錯誤。輸出：`videos/qa/seamcheck/seamcheck.json`＋`videos/qa/seamcheck/<接點>.png`。
接點 ID：段縫 `<上段>|<本段>`，段內 `<段>#<前鏡>><後鏡>`（與 `transition_lint` 的 scope／shot 對得上）。

依賴：ffmpeg／ffprobe、numpy、Pillow（同 `h3d qa --continuity`）。
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import continuity_qa as cq  # noqa: E402
import transition_lint as tl  # noqa: E402

REPORT_REL = Path("videos") / "qa" / "seamcheck"
REPORT_NAME = "seamcheck.json"
FRAME_WIDTH = 480
CHECK_KEYS = ("people_count", "left_right", "background_anchor", "no_repeat", "shot_size_as_planned")
QUESTIONS = {
    "people_count": "兩側可見人數是否等於預期（expected.people_a／people_b）？多人、少人或換人都算不符",
    "left_right": "兩側共同角色的畫面左右是否符合預期（expected.order_lr_a／order_lr_b）？反打時左右互換才是對的",
    "background_anchor": "每人身後的背景物是否和預期錨點一致、沒有無過程跳換？",
    "no_repeat": "B 側是否沒有把 A 側（或上段）已完成的動作再演一次、也沒有退回之前的狀態？（是＝沒重演）",
    "shot_size_as_planned": "B 側景別是否照分鏡（expected.size_b），沒有被渲成別的景別？",
}
INSTRUCTIONS = ("看每個接點的 PNG（左＝A 切前、右＝B 切後），依 expected 逐項填 checks：true＝符合、false＝不符、"
                "\"unsure\"＝看不出來；不符時在 notes 寫看到什麼。本工具不判定，checks 預設全是 null。")


def _label(text: str) -> str:
    """預設字型只有 ASCII：中文角色 ID 等改成 ?，免得拼貼標籤變方塊。"""
    return re.sub(r"[^\x20-\x7e]", "?", text)


def _expected_side(shot: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not shot:
        return {}
    pos = tl.shot_positions(shot)
    ordered = sorted(pos, key=lambda p: (p.get("order_lr") if isinstance(p.get("order_lr"), int) else 99,
                                         p.get("screen_x") if isinstance(p.get("screen_x"), (int, float)) else 9))
    return {
        "shot_id": shot.get("shot_id"),
        "size": (shot.get("camera_optics") or {}).get("shot_size"),
        "size_code": tl.size_code((shot.get("camera_optics") or {}).get("shot_size")),
        "people": len(shot.get("visual_subject_ids") or shot.get("character_ids") or []),
        "character_ids": list(shot.get("visual_subject_ids") or shot.get("character_ids") or []),
        "order_lr": [str(p["id"]) for p in ordered if isinstance(p.get("order_lr"), int)],
        "facing": {str(p["id"]): p.get("facing") for p in pos if p.get("facing")},
        "background_anchor": {str(p["id"]): p.get("background_anchor") for p in pos if p.get("background_anchor")},
        "azimuth_deg": (shot.get("camera_optics") or {}).get("azimuth_deg"),
    }


def _expected(a_shot, b_shot, extra: Dict[str, Any]) -> Dict[str, Any]:
    ea, eb = _expected_side(a_shot), _expected_side(b_shot)
    out = {"size_a": ea.get("size"), "size_b": eb.get("size"), "size_code_a": ea.get("size_code"),
           "size_code_b": eb.get("size_code"), "people_a": ea.get("people"), "people_b": eb.get("people"),
           "character_ids_a": ea.get("character_ids"), "character_ids_b": eb.get("character_ids"),
           "order_lr_a": ea.get("order_lr"), "order_lr_b": eb.get("order_lr"),
           "facing_a": ea.get("facing"), "facing_b": eb.get("facing"),
           "background_anchor_a": ea.get("background_anchor"), "background_anchor_b": eb.get("background_anchor"),
           "azimuth_a": ea.get("azimuth_deg"), "azimuth_b": eb.get("azimuth_deg"),
           "cut_in": (b_shot or {}).get("cut_in")}
    out.update({k: v for k, v in extra.items() if v not in (None, "", [], {})})
    return out


def _entry(jid: str, kind: str, a: Dict[str, Any], b: Dict[str, Any], expected: Dict[str, Any]) -> Dict[str, Any]:
    return {"id": jid, "kind": kind, "a": a, "b": b, "expected": expected,
            "checks": {k: None for k in CHECK_KEYS}, "notes": "", "questions": QUESTIONS}


def _save_pair(left, right, out: Path, title: str) -> Path:
    return cq.build_montage([(_label(title), left, right)], out, _label(title.split("  ")[0]))


def _rel(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)


def build_checklist(root: Path, segment_files: Optional[Sequence[Path]] = None, videos_dir: Optional[Path] = None,
                    out_dir: Optional[Path] = None, only: Optional[Sequence[str]] = None,
                    window: float = cq.DEFAULT_WINDOW) -> Dict[str, Any]:
    cq._need_numpy()
    root = Path(root).resolve()
    files = [Path(p) if Path(p).is_absolute() else root / p for p in (segment_files or cq.default_segment_files(root))]
    if not files:
        raise ValueError("找不到 segments-all.json 或 segments-ep*.json")
    videos_dir = Path(videos_dir) if videos_dir else root / "videos"
    if not videos_dir.is_absolute():
        videos_dir = root / videos_dir
    out_dir = Path(out_dir) if out_dir else root / REPORT_REL
    if not out_dir.is_absolute():
        out_dir = root / out_dir
    wanted = set(only or [])
    ordered = cq.load_ordered_segments(files)
    by_id = {str(s["segment_id"]): s for s in ordered}
    cache: Dict[str, Tuple[Any, float]] = {}

    def frames_of(sid: str):
        if sid not in cache:
            video = cq._video_for(root, videos_dir, sid)
            cache[sid] = cq.decode_frames(video, FRAME_WIDTH) if video else (None, 0.0)
        return cache[sid]

    junctions: List[Dict[str, Any]] = []
    skipped: List[Dict[str, str]] = []
    for seg in ordered:
        sid = str(seg["segment_id"])
        if wanted and sid not in wanted:
            continue
        frames, fps = frames_of(sid)
        if frames is None:
            skipped.append({"segment_id": sid, "reason": "no_video"})
            continue
        shots = tl._shots(seg)
        lead = tl.lead_in_seconds(seg)
        first_idx = min(len(frames) - 1, int(round(lead * fps))) if lead else 0
        # 段縫：上段末格｜本段首格（有前導就取前導後第一格）
        prev_sid = seg.get("_prev")
        if prev_sid and prev_sid in by_id:
            pframes, pfps = frames_of(prev_sid)
            prev = by_id[prev_sid]
            if pframes is not None:
                jid = f"{prev_sid}|{sid}"
                img = _save_pair(pframes[-1], frames[first_idx], out_dir / f"{jid.replace('|', '__')}.png",
                                 f"{jid}  A=prev last frame | B=this first frame" + (f" (after lead_in {lead:g}s)" if lead else ""))
                extra = {"seam_in": seg.get("seam_in"), "same_scene": tl.same_scene(prev, seg),
                         "exit_state_a": prev.get("exit_state") or (prev.get("segment_end_state") or {}),
                         "entry_state_b": seg.get("entry_state"), "beats_new_a": prev.get("beats_new"),
                         "beats_done_b": seg.get("beats_done"), "beats_new_b": seg.get("beats_new"),
                         "lead_in_s_b": lead or None}
                entry = _entry(jid, "seam",
                               {"segment_id": prev_sid, "shot": len(tl._shots(prev)), "time": round(len(pframes) / pfps, 3)},
                               {"segment_id": sid, "shot": 1, "time": round(first_idx / fps, 3)},
                               _expected((tl._shots(prev) or [None])[-1], (shots or [None])[0], extra))
                entry["image"] = _rel(img, root)
                junctions.append(entry)
        # 段內切
        gray = cq.to_gray(frames)
        diffs = cq.adjacent_dissimilarities(gray)
        for k, planned in enumerate(cq.planned_cuts(seg), start=1):
            cut = cq.find_cut(diffs, fps, planned, window)
            found = bool(cut.get("frame")) and bool(cut.get("confident"))
            fidx = cut["frame"] if cut.get("frame") else min(len(frames) - 1, max(1, int(round(planned * fps))))
            a_shot = shots[k - 1] if k - 1 < len(shots) else None
            b_shot = shots[k] if k < len(shots) else None
            jid = f"{sid}#{k}>{k + 1}"
            img = _save_pair(frames[fidx - 1], frames[fidx], out_dir / f"{jid.replace('#', '__').replace('>', '-')}.png",
                             f"{jid}  planned {planned:.2f}s -> {'actual' if found else 'planned (cut not found)'} "
                             f"{fidx / fps:.2f}s")
            entry = _entry(jid, "within", {"segment_id": sid, "shot": k, "time": round((fidx - 1) / fps, 3)},
                           {"segment_id": sid, "shot": k + 1, "time": round(fidx / fps, 3)},
                           _expected(a_shot, b_shot, {"beats_new_a": (a_shot or {}).get("beats_new"),
                                                      "beats_new_b": (b_shot or {}).get("beats_new")}))
            entry.update(image=_rel(img, root), planned_cut=round(planned, 3), cut_found=found)
            junctions.append(entry)
        keep = {sid, seg.get("_next")}
        for key in list(cache):
            if key not in keep:
                cache.pop(key, None)
    report = {"tool": "seam_check", "gate": "none_human_or_vlm_review",
              "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
              "instructions": INSTRUCTIONS, "check_keys": list(CHECK_KEYS),
              "segments_files": [p.name for p in files], "junctions": junctions, "skipped": skipped,
              "summary": {"junctions": len(junctions), "seams": sum(1 for j in junctions if j["kind"] == "seam"),
                          "within": sum(1 for j in junctions if j["kind"] == "within"),
                          "cuts_not_found": sum(1 for j in junctions if j.get("cut_found") is False),
                          "skipped_segments": len(skipped)}}
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / REPORT_NAME).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report["report_path"] = str(out_dir / REPORT_NAME)
    return report


def render(report: Dict[str, Any]) -> str:
    s = report["summary"]
    return "\n".join([
        f"接點自檢包（不判定，給人或視覺模型填 checks）：{report.get('report_path')}",
        f"  接點 {s['junctions']}（段縫 {s['seams']}、段內 {s['within']}；切點沒找到 {s['cuts_not_found']}）；"
        f"沒影片略過 {s['skipped_segments']} 段",
        f"  {INSTRUCTIONS}",
    ])


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="h3d seamcheck",
                                     description="階段 6 接點自檢包：每段首末幀與段內切點幀的對照圖＋檢查清單 JSON"
                                                 "（人數、左右、錨點、是否重演、是否照分鏡景別；預設 null，由人或視覺模型判讀，不自動判定）")
    parser.add_argument("--root", type=Path, default=Path("."), help="專案根目錄")
    parser.add_argument("--segments", type=Path, nargs="*", default=None,
                        help="分段檔（預設 segments-all.json，沒有就 segments-ep*.json）")
    parser.add_argument("--videos-dir", type=Path, default=None, help="影片目錄（預設 <root>/videos，檔名 <段>.mp4）")
    parser.add_argument("--out-dir", type=Path, default=None, help=f"輸出目錄（預設 <root>/{REPORT_REL.as_posix()}）")
    parser.add_argument("--segment-id", nargs="*", default=None, help="只跑這些段（段縫算在後一段）")
    parser.add_argument("--window", type=float, default=cq.DEFAULT_WINDOW, help="規劃切點前後搜尋秒數（預設 0.9）")
    parser.add_argument("--json", action="store_true", help="以 JSON 輸出")
    args = parser.parse_args(argv)
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        print("❌ seamcheck 需要 ffmpeg／ffprobe", file=sys.stderr)
        return 2
    if cq.np is None:
        print("❌ seamcheck 需要 numpy（pip install numpy）", file=sys.stderr)
        return 2
    try:
        report = build_checklist(args.root, args.segments, args.videos_dir, args.out_dir, args.segment_id, args.window)
    except (ValueError, OSError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2) if args.json else render(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
