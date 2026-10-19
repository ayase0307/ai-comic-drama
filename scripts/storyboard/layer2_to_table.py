#!/usr/bin/env python3
"""Layer 2 分鏡 JSON 轉 Markdown 分鏡表與時間軸 CSV，可選做結構檢查。

用法：
    python scripts/storyboard/layer2_to_table.py <layer2.json | segments.json | 目錄 | 多個檔> [--md out.md] [--timeline out.csv] [--check]

未指定 --md、--timeline、--check 時，Markdown 印到標準輸出。
目錄會讀取其中的 layer2-*.json，找不到時讀取 segments-*.json；多個輸入會合併輸出。
編譯器 segments-*.json 會展開 segments[].shots，CSV 使用量化後有效時間；原 Layer 2 輸入仍輸出企劃名義時間。

--check 檢查項目：
- 必要欄位與型別（對照 layer2-storyboard.schema.json，含 action_stages 不超過 5 個）
- 鏡頭秒數總和與 metadata.target_duration_sec 相差不超過 0.5 秒
- 鏡頭時間連續：每鏡 start_time 與前一鏡 end_time 相差不超過 0.05 秒
- 無 TODO：任何字串欄位含 TODO（區分大小寫）即失敗，訊息附 JSON 路徑

任一檔案失敗時 exit 1。CSV 以 UTF-8 with BOM 寫出，Excel 直接開啟不亂碼。
時間線 CSV 欄位：shot_id, start, end, duration, video_file, subtitle, narration, speaker, foley；
subtitle 為對白原文（line_verbatim），narration 留空。
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from handoff_to_skeleton import check_layer2, find_todo  # noqa: E402

DURATION_TOLERANCE_SEC = 0.5
CONTINUITY_TOLERANCE_SEC = 0.05
TIMELINE_COLUMNS = ["shot_id", "start", "end", "duration", "video_file",
                    "subtitle", "narration", "speaker", "foley"]


def collect_files(inputs: list[str]) -> list[Path]:
    import glob
    files: list[Path] = []
    for raw in inputs:
        if any(c in raw for c in ("*", "?", "[")):
            matched = sorted(glob.glob(raw))
            files.extend(Path(p) for p in matched)
        else:
            path = Path(raw)
            if path.is_dir():
                found = sorted(path.glob("layer2-*.json"))
                if not found:
                    found = sorted(path.glob("segments-*.json"))
                if not found:
                    print(f"[警告] 目錄 {path} 內沒有 layer2-*.json 或 segments-*.json", file=sys.stderr)
                files.extend(found)
            else:
                files.append(path)
    return files


def check_numbers(data: dict) -> list[str]:
    """秒數總和與時間連續性。假設結構已大致正確，缺欄位時由呼叫端接住例外。"""
    errors: list[str] = []
    shots = data["shots"]
    target = data["metadata"]["target_duration_sec"]
    total = sum(shot["duration"] for shot in shots)
    if abs(total - target) > DURATION_TOLERANCE_SEC:
        errors.append(f"鏡頭秒數總和 {total:.2f} 與 target_duration_sec {target} 相差超過 {DURATION_TOLERANCE_SEC} 秒")
    for prev, cur in zip(shots, shots[1:]):
        gap = cur["start_time"] - prev["end_time"]
        if abs(gap) > CONTINUITY_TOLERANCE_SEC:
            errors.append(f"{cur['shot_id']} 起點 {cur['start_time']} 與 {prev['shot_id']} 終點 {prev['end_time']} 不連續")
    return errors


def check_one(data: Any) -> list[str]:
    """結構檢查（schema）加上數值檢查與 TODO 檢查；結構缺漏時數值檢查會回報無法進行，而不是直接略過。"""
    errors = check_layer2(data)
    try:
        errors += check_numbers(data)
    except (KeyError, TypeError, IndexError) as exc:
        errors.append(f"無法做秒數與時間檢查（結構缺漏）：{exc!r}")
    errors += find_todo(data)
    return errors


def expand_segments(data: Any) -> tuple[list[dict], bool]:
    """Return source Layer 2 documents or normalize compiled segment collections for delivery timelines."""
    if not isinstance(data, dict) or not isinstance(data.get("segments"), list):
        return [data], False
    compiled = []
    for segment in data["segments"]:
        if not isinstance(segment, dict) or not isinstance(segment.get("shots"), list):
            raise ValueError("compiled segments entry must contain a shots list")
        meta = dict(segment.get("metadata") or {})
        style_lock = meta.get("style_lock") or {}
        meta.setdefault("pacing_profile", "compiled")
        meta.setdefault("lighting_lock_line", style_lock.get("lighting_lock_line", ""))
        compiled.append({
            "project_id": data.get("project_id", "compiled"),
            "scene_id": segment.get("scene_id", segment.get("segment_id", "compiled")),
            "segment_id": segment.get("segment_id", "compiled"),
            "source_scene_id": segment.get("scene_id", ""),
            "metadata": meta,
            "style_lock": style_lock,
            "shots": segment["shots"],
            "continuity_handshake": {},
            "_compiled_timeline": True,
        })
    return compiled, True


def check_compiled_timeline(data: dict) -> list[str]:
    """Validate the timing contract of a compiled segments collection without Layer 2 schema rules."""
    errors = []
    segments = data.get("segments")
    if not isinstance(segments, list) or not segments:
        return ["compiled segments 集合不可為空"]
    for segment in segments:
        sid = segment.get("segment_id", "compiled")
        shots = segment.get("shots")
        meta = segment.get("metadata") or {}
        if not isinstance(shots, list) or not shots:
            errors.append(f"{sid}: shots 不可為空")
            continue
        try:
            effective = float(meta["effective_duration_sec"])
            cursor = 0.0
            for shot in shots:
                start = float(shot["start_time"])
                end = float(shot["end_time"])
                duration = float(shot["duration"])
                if abs(start - cursor) > CONTINUITY_TOLERANCE_SEC:
                    errors.append(f"{sid}: {shot.get('shot_id', '?')} 起點 {start} 與前鏡終點 {cursor} 不連續")
                if end <= start or abs((end - start) - duration) > CONTINUITY_TOLERANCE_SEC:
                    errors.append(f"{sid}: {shot.get('shot_id', '?')} start/end/duration 不一致")
                cursor = end
            if abs(cursor - effective) > CONTINUITY_TOLERANCE_SEC:
                errors.append(f"{sid}: 最後鏡頭終點 {cursor:.3f} 與有效時長 {effective:.3f} 不一致")
        except (KeyError, TypeError, ValueError) as exc:
            errors.append(f"{sid}: 無法檢查 compiled timeline：{exc!r}")
    return errors


def _cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


STATUS_BADGES = {
    "draft": "📝 draft",
    "pending_review": "⏳ pending_review",
    "approved": "✅ approved",
    "rejected": "❌ rejected",
}


def format_review_badge(review: dict | None) -> str:
    if not review:
        return "📝 draft"
    st = review.get("review_status", "draft")
    badge = STATUS_BADGES.get(st, f"📝 {st}")
    rev = review.get("revision")
    rev_str = f" (rev {rev})" if rev is not None else ""
    return f"{badge}{rev_str}"


def md_row(shot: dict) -> str:
    cam = shot["camera_optics"]
    act = shot["action_and_performance"]
    dia = shot["dialogue_and_audio"]
    dialogue = f"{dia.get('speaker')}：{dia.get('line_verbatim')}" if dia.get("has_dialogue") else "—"
    review_str = format_review_badge(shot.get("review"))
    sketch = shot.get("sketch_file")
    sketch_cell = f"![草圖]({sketch})" if sketch else "—"
    cells = [
        shot["shot_id"],
        review_str,
        sketch_cell,
        f"{shot['start_time']:.2f}–{shot['end_time']:.2f}s",
        cam["shot_size"],
        f"{cam['focal_length']} / {cam['physical_distance']}",
        cam["pov_routing"],
        cam["movement"],
        " → ".join(act["action_stages"]),
        dialogue,
    ]
    return "| " + " | ".join(_cell(c) for c in cells) + " |"


def overflow_lines(data: dict) -> list[str]:
    """J-Cut 順延註記（只是註記，台詞已逐字寫在鏡頭內）；沒有順延時回傳空清單。"""
    handshake = data.get("continuity_handshake") or {}
    lines = []
    if handshake.get("overflow_dialogue_in"):
        lines.append(f"- 順延入（上段台詞延續到本段）：{handshake['overflow_dialogue_in']}")
    if handshake.get("overflow_dialogue_out"):
        lines.append(f"- 順延出（本段台詞延續到下段）：{handshake['overflow_dialogue_out']}")
    return lines


def review_summary_lines(data: dict) -> list[str]:
    parts = []
    if "review" in data and data["review"]:
        parts.append(f"審核狀態：{format_review_badge(data['review'])}")
    if data.get("grid_preview_file"):
        parts.append(f"九宮格預覽：![九宮格預覽]({data['grid_preview_file']})")
    if parts:
        return [f"> {' | '.join(parts)}", ""]
    return []


def render_md(data: dict) -> str:
    meta = data["metadata"]
    style = data.get("style_lock") or {}
    source = data.get("source_scene_id", data["scene_id"])
    lines = [
        f"# {data['project_id']} · {data['scene_id']}",
        "",
        *review_summary_lines(data),
        f"- 段落：`{data['segment_id']}`（來源場景 `{source}`）",
        *overflow_lines(data),
        f"- 比例：{meta['aspect_ratio']}　時長：{meta['target_duration_sec']} 秒"
        + (f"（有效 {meta['effective_duration_sec']} 秒）" if data.get("_compiled_timeline") else "")
        + f"　節奏：{meta['pacing_profile']}",
        f"- 光線鎖：{meta['lighting_lock_line']}",
        f"- 風格錨點：{style.get('anchor', '—')}",
        f"- 負向：{style.get('negative', '—')}",
        "",
        "| 鏡 | 審核 | 草圖 | 時間 | 景別 | 焦段 / 距離 | POV | 運鏡 | 動作階段 | 對白 |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    lines += [md_row(shot) for shot in data["shots"]]
    return "\n".join(lines) + "\n"


def timeline_rows(data: dict) -> list[dict]:
    rows = []
    for shot in data["shots"]:
        dia = shot["dialogue_and_audio"]
        rows.append({
            "shot_id": shot["shot_id"],
            "start": shot["start_time"],
            "end": shot["end_time"],
            "duration": shot["duration"],
            "video_file": shot.get("video_file", ""),
            "subtitle": dia.get("line_verbatim") or "",
            "narration": "",
            "speaker": dia.get("speaker") or "",
            "foley": dia.get("foley_and_ambience", ""),
        })
    return rows


def write_timeline(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=TIMELINE_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Layer 2 分鏡 JSON 轉 Markdown 表 / 時間軸 CSV")
    ap.add_argument("inputs", nargs="+", help="layer2 JSON 檔、目錄或多個檔案")
    ap.add_argument("--md", type=Path, help="輸出 Markdown 分鏡表")
    ap.add_argument("--timeline", type=Path, help="輸出時間軸 CSV")
    ap.add_argument("--check", action="store_true", help="做結構與時間檢查，失敗 exit 1")
    args = ap.parse_args()

    files = collect_files(args.inputs)
    if not files:
        print("[錯誤] 沒有可處理的檔案", file=sys.stderr)
        return 2

    failed = False
    docs: list[dict] = []
    for path in files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            print(f"[錯誤] {path.name} 讀取失敗：{exc}", file=sys.stderr)
            failed = True
            continue
        try:
            expanded, is_compiled = expand_segments(data)
        except ValueError as exc:
            print(f"[錯誤] {path.name} compiled segments 格式錯誤：{exc}", file=sys.stderr)
            failed = True
            continue
        if args.check and not is_compiled:
            errors = check_one(data)
            if errors:
                failed = True
                print(f"[失敗] {path.name}")
                for err in errors:
                    print(f"  - {err}")
            else:
                print(f"[通過] {path.name}")
        elif args.check:
            errors = check_compiled_timeline(data)
            if errors:
                failed = True
                print(f"[失敗] {path.name}")
                for err in errors:
                    print(f"  - {err}")
            else:
                print(f"[通過] {path.name}: compiled timeline timing checks")
        docs.extend(expanded)

    renderable = []
    for data in docs:
        try:
            if args.md:
                render_md(data)
            timeline_rows(data)
            renderable.append(data)
        except (KeyError, TypeError) as exc:
            print(f"[錯誤] 缺少欄位，無法產出表格：{exc}（請先加 --check 查看）", file=sys.stderr)
            failed = True

    md_text = "\n---\n\n".join(render_md(d) for d in renderable) if args.md or not args.timeline else ""
    if args.md and renderable:
        args.md.write_text(md_text, encoding="utf-8")
        print(f"已寫入 {args.md}")
    if args.timeline and renderable:
        rows = [row for d in renderable for row in timeline_rows(d)]
        write_timeline(args.timeline, rows)
        print(f"已寫入 {args.timeline}（{len(rows)} 鏡）")
    if not (args.md or args.timeline or args.check):
        print(md_text)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
