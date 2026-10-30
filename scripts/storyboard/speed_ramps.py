#!/usr/bin/env python3
"""階段 6／7 後製變速：清單格式、time_map 換算、合併寫入（不依賴 ffmpeg／OpenCV）。

清單檔 `videos/speed-ramps.json`（schema ai-comic-drama/speed-ramps/1）：

    {"schema": "ai-comic-drama/speed-ramps/1",
     "rules": {...},                          # 這次採用的倍率規則（見 DEFAULT_RULES）
     "segments": {
       "EP01-S03-b": {
         "status": "proposed|approved|rendered|skip",
         "source": "videos/EP01-S03-b.mp4", "source_sha256": "...",
         "fps": 24, "frames": 209, "orig_duration_s": 8.708,
         "protect": [{"start": 5.92, "end": 9.42, "why": "台詞"}],   # 台詞保護區（秒），一律 1×
         "sections": [{"start_frame": 0, "end_frame": 16, "start": 0.0, "end": 0.667,
                       "speed": 0, "shot": "SH01", "kind": "frozen_head", "reason": "..."}],
         # speed_ramp.py 產檔後寫入：
         "output": "videos/ramped/EP01-S03-b.mp4", "output_sha256": "...",
         "new_duration_s": 6.125, "delta_s": -2.583,
         "time_map": [{"src": [0.0, 0.667], "out": null, "speed": 0}, {"src": [...], "out": [...], "speed": 1.0}],
         "verify": {"protect_corr_min": 0.999, "threshold": 0.98}
       }}}

規則（老大 2026-10-24 在噩盡島定案）：開頭凍結剪掉；定住／蓄力 2–3×；飄浮 1.8–2×；撞擊與台詞原速。
原片不覆寫，變速版輸出 `videos/ramped/<段>.mp4`。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

SCHEMA = "ai-comic-drama/speed-ramps/1"
SPEC_REL = "videos/speed-ramps.json"
RAMPED_DIR = "videos/ramped"

DEFAULT_RULES: Dict[str, Any] = {
    "frozen_head": 0,          # 0＝剪掉
    "windup": 2.5,             # 起手延遲／蓄力
    "hold": [2.0, 3.0],        # 定住：短的 2×、超過 hold_long_s 的 3×
    "hold_long_s": 1.2,
    "float": [1.8, 2.0],       # 騰空水平飄浮（光流抓不到，人工標）
    "impact": 1.0,
    "dialogue": 1.0,
    "talk_tail": 2.0,          # v2：最後一句說完、主體動作<峰值20%且≥0.5s → 剪到0.3s或2×
    "talk_tail_keep_s": 0.3,
    "general": [1.1, 1.3],     # v2：非對嘴鏡整段可加速；對嘴特寫≤1.1
    "max_speed": 3.0,
    "protect_corr_min": 0.98,  # 台詞保護區變速前後音訊相關係數下限
}

# 會被保留的人工／產檔欄位：重跑 motion_qa 不可覆寫（finding #124）
RENDER_FIELDS = ("output", "output_sha256", "output_frames", "new_duration_s", "output_audio_s",
                 "planned_duration_s", "delta_s", "time_map", "verify", "rendered_at")
LOCKED_STATUSES = {"approved", "rendered", "skip"}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def spec_path(root: Path) -> Path:
    return Path(root) / SPEC_REL


def empty_spec(rules: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {"schema": SCHEMA, "rules": dict(rules or DEFAULT_RULES), "segments": {}}


def load_spec(path: Path) -> Dict[str, Any]:
    path = Path(path)
    if not path.is_file():
        return empty_spec()
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    data.setdefault("schema", SCHEMA)
    data.setdefault("rules", dict(DEFAULT_RULES))
    data.setdefault("segments", {})
    return data


def save_spec(path: Path, data: Dict[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    tmp.replace(path)


def merge_segment(data: Dict[str, Any], sid: str, proposal: Dict[str, Any], force: bool = False) -> str:
    """把 motion_qa 的新提案併進清單，回傳動作（added／replaced／kept）。

    - 已 approved／rendered／skip 且來源 sha 沒變 → 保留人工區段與產檔欄位（kept），除非 force。
    - 來源 sha 變了（重跑 take 會改動作結構）→ 換成新提案，舊產檔欄位清掉並標 stale_from。
    - 其他 → 換成新提案，但沿用舊的 protect 人工補充。
    """
    segs = data.setdefault("segments", {})
    old = segs.get(sid)
    if old is None:
        segs[sid] = proposal
        return "added"
    same_source = old.get("source_sha256") and old.get("source_sha256") == proposal.get("source_sha256")
    if not force and same_source and old.get("status") in LOCKED_STATUSES:
        return "kept"
    new = dict(proposal)
    if same_source:
        manual = [p for p in old.get("protect") or [] if p.get("manual")]
        new["protect"] = _merge_windows(list(new.get("protect") or []) + manual)
    else:
        if old.get("source_sha256"):
            new["stale_from"] = {"source_sha256": old.get("source_sha256"), "status": old.get("status")}
    segs[sid] = new
    return "replaced"


def update_render_fields(path: Path, sid: str, fields: Dict[str, Any]) -> None:
    """只更新單一段的產檔欄位（重新讀檔再寫，避免洗掉別段或別的 agent 的修改）。"""
    data = load_spec(path)
    seg = data["segments"].setdefault(sid, {})
    for key in RENDER_FIELDS:
        if key in fields:
            seg[key] = fields[key]
    if "status" in fields:
        seg["status"] = fields["status"]
    save_spec(path, data)


# ------------------------------------------------------------------ time_map

def build_time_map(sections: List[Dict[str, Any]], fps: float) -> Tuple[List[Dict[str, Any]], float]:
    tmap: List[Dict[str, Any]] = []
    t_out = 0.0
    for s in sections:
        a, b, sp = s["start_frame"] / fps, s["end_frame"] / fps, float(s["speed"])
        if sp == 0:
            tmap.append({"src": [round(a, 4), round(b, 4)], "out": None, "speed": 0})
            continue
        d = (b - a) / sp
        tmap.append({"src": [round(a, 4), round(b, 4)], "out": [round(t_out, 4), round(t_out + d, 4)], "speed": sp})
        t_out += d
    return tmap, t_out


def map_time(t: float, time_map: List[Dict[str, Any]]) -> float:
    """原片秒數 → 變速版秒數。落在剪掉區段的時間點對到該區段在新片的位置（下一段的起點）。"""
    t = float(t)
    last_out = 0.0
    for item in time_map:
        a, b = item["src"]
        out = item.get("out")
        if t < a:
            return last_out
        if a <= t <= b:
            if not out:
                return last_out
            sp = float(item["speed"]) or 1.0
            return round(out[0] + (t - a) / sp, 4)
        if out:
            last_out = out[1]
    return round(last_out + max(0.0, t - (time_map[-1]["src"][1] if time_map else 0.0)), 4)


def map_window(start: float, end: float, time_map: List[Dict[str, Any]]) -> Tuple[float, float]:
    return map_time(start, time_map), map_time(end, time_map)


def ramped_source(root: Path, sid: str, spec: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """這段要不要改用變速版：rendered、輸出檔存在、原片 sha 跟清單一致才算。

    回傳 {path, rel, time_map, duration, delta}；不符合回傳 None（呼叫端用原片）。
    原片被重跑覆寫（sha 不同）時回傳 None 並在 `stale` 欄位說明，避免拿舊的 time_map 套新影片。
    """
    root = Path(root)
    data = spec if spec is not None else load_spec(spec_path(root))
    seg = (data.get("segments") or {}).get(sid)
    if not seg or seg.get("status") != "rendered" or not seg.get("output") or not seg.get("time_map"):
        return None
    out = root / seg["output"]
    src = root / (seg.get("source") or f"videos/{sid}.mp4")
    if not out.is_file() or not src.is_file():
        return None
    if seg.get("source_sha256") and sha256_file(src) != seg["source_sha256"]:
        return {"stale": f"{sid} 原片已被覆寫（sha 不符），變速版作廢，請重跑 h3d motion／h3d ramp"}
    return {"path": out, "rel": seg["output"], "time_map": seg["time_map"],
            "duration": float(seg.get("new_duration_s") or 0.0), "delta": float(seg.get("delta_s") or 0.0)}


# ------------------------------------------------------------------ 區段工具

def _merge_windows(windows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    items = sorted((dict(w) for w in windows if w.get("end", 0) > w.get("start", 0)), key=lambda w: w["start"])
    merged: List[Dict[str, Any]] = []
    for w in items:
        if merged and w["start"] <= merged[-1]["end"] + 1e-6:
            merged[-1]["end"] = max(merged[-1]["end"], w["end"])
            whys = [x for x in (merged[-1].get("why"), w.get("why")) if x]
            merged[-1]["why"] = "；".join(dict.fromkeys(whys))
            merged[-1]["manual"] = bool(merged[-1].get("manual") or w.get("manual"))
        else:
            merged.append(w)
    return merged


def validate_sections(seg: Dict[str, Any], rules: Optional[Dict[str, Any]] = None) -> List[str]:
    """產檔前的斷言：連續覆蓋整段、倍率在範圍內、台詞保護區 1×。"""
    rules = rules or DEFAULT_RULES
    errors: List[str] = []
    secs = seg.get("sections") or []
    fps = float(seg.get("fps") or 24)
    if not secs:
        return ["沒有任何區段"]
    if secs[0]["start_frame"] != 0:
        errors.append("第一個區段不是從第 0 幀開始")
    if seg.get("frames") and secs[-1]["end_frame"] != seg["frames"]:
        errors.append(f"最後一個區段沒有結束在第 {seg['frames']} 幀")
    for a, b in zip(secs, secs[1:]):
        if a["end_frame"] != b["start_frame"]:
            errors.append(f"區段不連續：{a['end_frame']} → {b['start_frame']}")
    max_speed = float(rules.get("max_speed", 3.0))
    for s in secs:
        sp = float(s.get("speed", 1.0))
        if sp != 0 and not (1.0 <= sp <= max_speed):
            errors.append(f"區段 {s.get('start')}–{s.get('end')} 倍率 {sp} 不在 1–{max_speed}×")
        if s["end_frame"] <= s["start_frame"]:
            errors.append(f"區段 {s.get('start_frame')}–{s.get('end_frame')} 長度為 0")
    for p in seg.get("protect") or []:
        for s in secs:
            s0, s1 = s["start_frame"] / fps, s["end_frame"] / fps
            if s0 < p["end"] - 1e-6 and s1 > p["start"] + 1e-6 and float(s["speed"]) != 1.0:
                errors.append(f"台詞保護區 {p['start']:.2f}–{p['end']:.2f}s 被變速（區段 {s0:.2f}–{s1:.2f}s ×{s['speed']}）")
    return errors
