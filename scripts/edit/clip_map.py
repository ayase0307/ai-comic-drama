#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""clip-map（#163）：階段 7 各工具共用的「段 → 實際用的影片版本」對照表。

`edit/clip-map.json`，schema `ai-comic-drama/clip-map/1`：
  segments[]：id、source（原片或 videos/ramped/<段>.mp4）、frames（影格數）、fps、
              dur（= frames/fps，段長一律由影格數推）、time_map（原片秒 → 該檔秒，沿用 speed-ramps 格式）、
              cuts（剪掉的區間，單位為 source 檔自己的秒）、start（集內累積起點，變速＋剪鏡後）、
              out_dur（剪鏡後長度）。
  total：全集長度。

只新增欄位、不改 speed-ramps.json／full-plan.json 既有欄位（PR #40 約定）。
用法：python scripts/edit/clip_map.py <專案根> [--cuts edit/cuts.json] [--write]
cuts.json：{"<段>": [[起秒, 終秒], ...]}（source 檔的秒）。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
for _c in (str(SCRIPTS_DIR), str(SCRIPTS_DIR / "voice"), str(SCRIPTS_DIR / "storyboard")):
    if _c not in sys.path:
        sys.path.insert(0, _c)

SCHEMA = "ai-comic-drama/clip-map/1"
CLIP_MAP_REL = "edit/clip-map.json"


def normalize_cuts(cuts: Optional[List[List[float]]], dur: float) -> List[Tuple[float, float]]:
    """排序、夾到 [0,dur]、合併重疊，丟掉空區間。"""
    out: List[List[float]] = []
    for a, b in sorted((min(x), max(x)) for x in (cuts or [])):
        a, b = max(0.0, float(a)), min(float(dur), float(b))
        if b - a <= 1e-6:
            continue
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return [(a, b) for a, b in out]


def apply_cuts(t: float, cuts: List[Tuple[float, float]]) -> float:
    """source 檔秒數 → 剪鏡後秒數；落在被剪區間內的對到剪點。"""
    removed = 0.0
    for a, b in cuts:
        if t >= b:
            removed += b - a
        elif t > a:
            removed += t - a
            break
        else:
            break
    return round(t - removed, 4)


def build_clip(sid: str, *, frames: int, fps: float = 24.0, source: Optional[str] = None,
               time_map: Optional[List[Dict[str, Any]]] = None,
               cuts: Optional[List[List[float]]] = None) -> Dict[str, Any]:
    if frames <= 0 or fps <= 0:
        raise ValueError(f"{sid}: frames/fps 必須為正")
    dur = frames / fps
    nc = normalize_cuts(cuts, dur)
    out_dur = dur - sum(b - a for a, b in nc)
    clip: Dict[str, Any] = {
        "id": sid, "source": source or f"videos/{sid}.mp4", "frames": int(frames), "fps": fps,
        "dur": round(dur, 4), "out_dur": round(out_dur, 4), "cuts": [[round(a, 4), round(b, 4)] for a, b in nc],
    }
    if time_map:
        clip["time_map"] = time_map
    return clip


def build_clip_map(clips: List[Dict[str, Any]]) -> Dict[str, Any]:
    """依序累積集內起點（start 是變速＋剪鏡後的成片時間）。"""
    t = 0.0
    segs = []
    for c in clips:
        c = dict(c)
        c["start"] = round(t, 4)
        t += float(c["out_dur"])
        segs.append(c)
    return {"schema": SCHEMA, "segments": segs, "total": round(t, 4)}


def map_original_time(clip: Dict[str, Any], t: float) -> float:
    """原片秒（台詞、ASR、配音落點）→ 該段成片內秒數（變速後再剪鏡）。"""
    import speed_ramps as SRM
    tm = clip.get("time_map")
    t2 = SRM.map_time(t, tm) if tm else float(t)
    return apply_cuts(t2, [tuple(x) for x in clip.get("cuts") or []])


def to_episode_time(cm: Dict[str, Any], sid: str, t: float) -> float:
    for c in cm["segments"]:
        if c["id"] == sid:
            return round(c["start"] + map_original_time(c, t), 4)
    raise KeyError(sid)


def validate(cm: Dict[str, Any]) -> List[str]:
    errs: List[str] = []
    if cm.get("schema") != SCHEMA:
        errs.append(f"schema 應為 {SCHEMA}")
    seen = set()
    prev_end = 0.0
    for c in cm.get("segments") or []:
        sid = c.get("id")
        if sid in seen:
            errs.append(f"{sid}: 重複的段")
        seen.add(sid)
        if abs(c["frames"] / c["fps"] - c["dur"]) > 0.001:
            errs.append(f"{sid}: dur 與 frames/fps 不符")
        if abs(c["start"] - prev_end) > 0.001:
            errs.append(f"{sid}: start 沒接上前一段（{c['start']} vs {prev_end}）")
        prev_end = c["start"] + c["out_dur"]
    if cm.get("segments") and abs(cm.get("total", 0) - prev_end) > 0.001:
        errs.append("total 與累積長度不符")
    return errs


def from_project(root: Path, cuts_file: Optional[Path] = None) -> Dict[str, Any]:
    import voice_align as V
    import speed_ramps as SRM
    root = Path(root).resolve()
    cuts = json.loads(cuts_file.read_text(encoding="utf-8")) if cuts_file and cuts_file.is_file() else {}
    spec = SRM.load_spec(SRM.spec_path(root))
    clips = []
    for sid in V.segment_order(root):
        info = SRM.ramped_source(root, sid, spec)
        if info and info.get("stale"):
            raise RuntimeError(info["stale"])
        rel = info["rel"] if info else f"videos/{sid}.mp4"
        dur = (info or {}).get("duration") or V.ffprobe_duration(root / rel) or 0.0
        frames = round(dur * 24)
        clips.append(build_clip(sid, frames=frames, source=rel,
                                time_map=info["time_map"] if info else None, cuts=cuts.get(sid)))
    return build_clip_map(clips)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("root", type=Path)
    ap.add_argument("--cuts", type=Path, default=None)
    ap.add_argument("--write", action="store_true", help=f"寫入 {CLIP_MAP_REL}")
    a = ap.parse_args(argv)
    cm = from_project(a.root, a.cuts or (a.root / "edit" / "cuts.json"))
    errs = validate(cm)
    for e in errs:
        print("ERROR", e)
    if a.write and not errs:
        p = a.root / CLIP_MAP_REL
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(cm, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"已寫入 {p}")
    print(f"{len(cm['segments'])} 段，總長 {cm['total']}s")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
