#!/usr/bin/env python3
"""把分鏡 JSON 轉成 Markdown 分鏡表與剪輯時間線 CSV。

用法：
    python storyboard_to_table.py storyboard-ep01.json --md storyboard-ep01.md --timeline timeline-ep01.csv
    python storyboard_to_table.py storyboard-ep01.json --check     # 只做欄位校驗
    python storyboard_to_table.py storyboard-ep01.json             # 直接印出 Markdown
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

REQUIRED = [
    "shot_id", "scene", "location", "shot_size", "camera",
    "duration_sec", "description", "characters",
    "image_prompt", "video_prompt",
]


def load(path: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    shots = data.get("shots")
    if not isinstance(shots, list):
        raise SystemExit("錯誤：JSON 缺少 shots 陣列")
    return data, shots


def validate(shots: list[dict[str, Any]]) -> list[str]:
    problems: list[str] = []
    seen: set[str] = set()
    for i, s in enumerate(shots, 1):
        sid = s.get("shot_id") or f"#{i}"
        for key in REQUIRED:
            if key not in s:
                problems.append(f"{sid}: 缺少欄位 {key}")
        if sid in seen:
            problems.append(f"{sid}: shot_id 重複")
        seen.add(sid)
        dur = s.get("duration_sec")
        if not isinstance(dur, (int, float)) or isinstance(dur, bool) or dur <= 0:
            problems.append(f"{sid}: duration_sec 必須為正數")
        if not isinstance(s.get("characters"), list):
            problems.append(f"{sid}: characters 必須為陣列（可為空）")
    return problems


def fmt_time(sec: float) -> str:
    total = int(round(sec))
    return f"{total // 60:02d}:{total % 60:02d}"


def _cell(value: Any) -> str:
    return str(value or "").replace("|", "／").replace("\n", " ").strip()


def to_markdown(data: dict[str, Any], shots: list[dict[str, Any]]) -> str:
    total = sum(float(s.get("duration_sec", 0) or 0) for s in shots)
    out = [
        f"# 分鏡表 ｜ {data.get('project', '')} 第 {data.get('episode', '?')} 集 {data.get('title', '')}",
        "",
        f"- 畫面比例：{data.get('aspect_ratio', '')}",
        f"- 畫風鎖：`{data.get('style_lock', '')}`",
        f"- 鏡頭數：{len(shots)}　總時長：{fmt_time(total)}",
        "",
        "| 鏡號 | 場次 | 地點 | 景別 | 運鏡 | 時長 | 畫面 | 角色 | 對白 | 旁白 |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for s in shots:
        out.append(
            "| {sid} | {sc} | {loc} | {size} | {cam} | {dur}s | {desc} | {chars} | {dlg} | {nar} |".format(
                sid=_cell(s.get("shot_id")),
                sc=_cell(s.get("scene")),
                loc=_cell(s.get("location")),
                size=_cell(s.get("shot_size")),
                cam=_cell(s.get("camera")),
                dur=s.get("duration_sec", ""),
                desc=_cell(s.get("description")),
                chars="、".join(s.get("characters") or []),
                dlg=_cell(s.get("dialogue")),
                nar=_cell(s.get("narration")),
            )
        )

    out += ["", "## 逐鏡提示詞", ""]
    for s in shots:
        out.append(
            f"### {s.get('shot_id', '')} ｜ {s.get('shot_size', '')} ｜ "
            f"{s.get('camera', '')} ｜ {s.get('duration_sec', '')}s"
        )
        out.append(f"- **圖像提示詞**：{s.get('image_prompt', '')}")
        out.append(f"- **影片提示詞**：{s.get('video_prompt', '')}")
        if s.get("negative_prompt"):
            out.append(f"- **負面提示詞**：{s['negative_prompt']}")
        out.append("")
    return "\n".join(out)


def to_timeline(shots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    t = 0.0
    for s in shots:
        dur = float(s.get("duration_sec", 0) or 0)
        sid = s.get("shot_id", "")
        rows.append(
            {
                "shot_id": sid,
                "start": fmt_time(t),
                "end": fmt_time(t + dur),
                "duration_sec": dur,
                "video_file": f"videos/{sid}.mp4",
                "subtitle": _cell(s.get("narration") or s.get("dialogue")),
                "narration": _cell(s.get("narration")),
                "status": s.get("status", "pending"),
            }
        )
        t += dur
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description="分鏡 JSON → Markdown / CSV")
    ap.add_argument("storyboard_json", help="分鏡 JSON 路徑")
    ap.add_argument("--md", help="輸出 Markdown 分鏡表路徑")
    ap.add_argument("--timeline", help="輸出剪輯時間線 CSV 路徑")
    ap.add_argument("--check", action="store_true", help="只做欄位校驗")
    args = ap.parse_args()

    data, shots = load(args.storyboard_json)
    problems = validate(shots)
    if problems:
        print("校驗發現問題：", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
    else:
        print(f"校驗通過：{len(shots)} 個鏡頭")

    if args.check:
        sys.exit(1 if problems else 0)

    if args.md:
        Path(args.md).write_text(to_markdown(data, shots), encoding="utf-8")
        print(f"已輸出 Markdown：{args.md}")

    if args.timeline:
        rows = to_timeline(shots)
        fieldnames = list(rows[0].keys()) if rows else ["shot_id"]
        with open(args.timeline, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        print(f"已輸出時間線：{args.timeline}")

    if not args.md and not args.timeline and not args.check:
        print(to_markdown(data, shots))


if __name__ == "__main__":
    main()
