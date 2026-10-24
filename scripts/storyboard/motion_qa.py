#!/usr/bin/env python3
"""階段 6 收件後的動態 QA＋自動產變速清單（h3d motion）。

為什麼：H3／FreeVideo 是 24 fps 原生、沒有插幀，但動作戲常有「慢動作感」——
3 秒的打擊鏡真正高速的時間中位數只有約 0.6 秒，其餘是起手前發呆、打完定住、
騰空的人水平飄浮（《噩盡島》階段 6 實測）。這支工具：

1. 每段影片量光流（OpenCV Farneback，336×192 灰階，換算回原寬像素／幀）：
   全域鏡頭運動＝光流中位向量；主體運動＝扣掉鏡頭運動後殘差的 95 分位；重複幀＝幀差 < 0.3。
   結果寫 `videos/qa/motion/<段>.json`（逐幀）。
2. 依分鏡切出逐鏡指標：active_s（主體運動超過峰值 50% 的秒數）、longest_hold_s（低於
   max(峰值 20%, 6 px) 的最長連續秒數）、onset_s（起手延遲）、重複幀數。
3. 依規則提出變速區段，**合併**寫進 `videos/speed-ramps.json`（status=proposed）：
   開頭連續重複幀＝剪掉；起手延遲≥0.4 s＝2.5×；定住≥0.5 s＝2×（超過 1.2 s＝3×）；其餘 1×；
   台詞保護區（segments 的 speech_window／external_narration／有台詞的鏡，可加 --vad 用 ffmpeg 偵測人聲）一律 1×。
   **飄浮（騰空水平滑行）光流抓不到**，要人看影格標成 kind=float、speed 1.8–2。
   已 approved／rendered 的段、來源 sha 沒變就不覆寫（--force 才重提）。

人看過清單、調整區段後把 status 改 approved，再跑 `h3d ramp` 產檔（speed_ramp.py）。

用法：
  h3d motion --root . [--segments segments-all.json] [--segment EP01-S03-b ...] [--vad] [--force] [--report-only]
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import speed_ramps as SR  # noqa: E402

FLOW_W, FLOW_H = 336, 192
DUP_DIFF = 0.3
MIN_HOLD_S = 0.5
MIN_ONSET_S = 0.4
MIN_FROZEN_HEAD = 6  # 幀


# ------------------------------------------------------------------ 1. 量測

def measure(video: Path) -> Dict[str, Any]:
    try:
        import cv2  # type: ignore
        import numpy as np  # type: ignore
    except ImportError as exc:  # pragma: no cover - 依環境
        raise SystemExit("❌ 動態 QA 需要 opencv-python 與 numpy：pip install opencv-python-headless numpy") from exc
    cap = cv2.VideoCapture(str(video))
    fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
    width = cap.get(cv2.CAP_PROP_FRAME_WIDTH) or FLOW_W
    scale = float(width) / FLOW_W
    prev = None
    rows: List[Dict[str, Any]] = []
    i = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        g = cv2.cvtColor(cv2.resize(frame, (FLOW_W, FLOW_H), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
        if prev is not None:
            diff = float(np.mean(np.abs(g.astype(np.int16) - prev.astype(np.int16))))
            flow = cv2.calcOpticalFlowFarneback(prev, g, None, 0.5, 3, 15, 3, 5, 1.2, 0)
            med = np.median(flow.reshape(-1, 2), axis=0)
            resid = np.linalg.norm(flow - med, axis=2) * scale
            rows.append({"f": i, "t": round(i / fps, 4), "diff": round(diff, 3),
                         "cam": round(float(np.linalg.norm(med) * scale), 3),
                         "resid_p95": round(float(np.percentile(resid, 95)), 3)})
        prev = g
        i += 1
    cap.release()
    diffs = [r["diff"] for r in rows]
    cuts = []
    for k, r in enumerate(rows):
        lo, hi = max(0, k - 6), min(len(rows), k + 7)
        neigh = sorted(diffs[lo:k] + diffs[k + 1:hi])
        local = neigh[len(neigh) // 2] if neigh else 0
        if r["diff"] > 12 and r["diff"] > 4 * max(local, 1):
            cuts.append(r["t"])
    return {"fps": fps, "frames": i, "duplicates": sum(1 for d in diffs if d < DUP_DIFF), "cuts": cuts, "rows": rows}


# ------------------------------------------------------------------ 2. 逐鏡指標

def shot_bounds(segment: Dict[str, Any], flow: Dict[str, Any]) -> List[Tuple[str, float, float]]:
    dur = flow["frames"] / flow["fps"]
    shots = segment.get("shots") or []
    starts = []
    for k, sh in enumerate(shots):
        st = float(sh.get("start_time") or sh.get("start") or 0.0)
        near = [c for c in flow.get("cuts") or [] if abs(c - st) < 0.45]
        starts.append(near[0] if (near and k > 0) else st)
    if not starts:
        return [("SH01", 0.0, dur)]
    out = []
    for k, sh in enumerate(shots):
        name = str(sh.get("shot_id") or f"SH{k + 1:02d}")
        b = starts[k + 1] if k + 1 < len(starts) else dur
        out.append((name, starts[k], b))
    return out


def shot_stats(flow: Dict[str, Any], bounds: List[Tuple[str, float, float]]) -> List[Dict[str, Any]]:
    fps = flow["fps"]
    rows = flow["rows"]
    stats = []
    for name, a, b in bounds:
        rr = [r for r in rows if a <= r["t"] < b]
        if not rr:
            continue
        vals = [r["resid_p95"] for r in rr]
        peak = max(vals) if vals else 0.0
        hi = 0.5 * peak
        lo = max(0.2 * peak, 6.0)
        active = sum(1 for v in vals if v >= hi) / fps
        longest = run = 0
        for v in vals:
            run = run + 1 if v < lo else 0
            longest = max(longest, run)
        onset = next((r["t"] - a for r in rr if r["resid_p95"] >= hi), b - a)
        stats.append({"shot": name, "start": round(a, 3), "end": round(b, 3), "dur": round(b - a, 3),
                      "peak": round(peak, 2), "active_s": round(active, 3), "longest_hold_s": round(longest / fps, 3),
                      "onset_s": round(onset, 3), "dup_frames": sum(1 for r in rr if r["diff"] < DUP_DIFF)})
    return stats


# ------------------------------------------------------------------ 3. 提案區段

def protect_windows(segment: Dict[str, Any], vad: Optional[List[Tuple[float, float]]] = None) -> List[Dict[str, Any]]:
    """台詞保護區：speech_window、external_narration、有台詞的鏡；VAD 人聲區與它們重疊就併進來。"""
    wins: List[Dict[str, Any]] = []
    for sh in segment.get("shots") or []:
        dlg = sh.get("dialogue_and_audio") or {}
        line = dlg.get("line_verbatim") or sh.get("subtitle") or ""
        if not (dlg.get("has_dialogue") or str(line).strip()):
            continue
        win = dlg.get("speech_window") or {}
        if isinstance(win, dict) and win.get("start") is not None and win.get("end") is not None:
            wins.append({"start": float(win["start"]), "end": float(win["end"]), "why": f"{sh.get('shot_id')} 台詞窗"})
        else:
            st = float(sh.get("start_time") or 0.0)
            en = float(sh.get("end_time") or st + float(sh.get("duration") or 0.0))
            wins.append({"start": st, "end": en, "why": f"{sh.get('shot_id')} 有台詞（無 speech_window，整鏡保護）"})
    for e in segment.get("external_narration") or []:
        if e.get("start") is not None and e.get("end") is not None:
            wins.append({"start": float(e["start"]), "end": float(e["end"]), "why": "畫外台詞（external_narration）"})
    for a, b in vad or []:
        if any(a < w["end"] + 0.3 and b > w["start"] - 0.3 for w in wins):
            wins.append({"start": a, "end": b, "why": "VAD 人聲"})
    return SR._merge_windows(wins)


def detect_speech(video: Path, noise_db: float = -35.0, min_silence: float = 0.25) -> List[Tuple[float, float]]:
    """用 ffmpeg silencedetect 粗估人聲區（非靜音區）；沒有音軌回傳空清單。"""
    res = subprocess.run(["ffmpeg", "-v", "info", "-i", str(video), "-af",
                          f"silencedetect=noise={noise_db}dB:d={min_silence}", "-f", "null", "-"],
                         capture_output=True, text=True, encoding="utf-8", errors="replace")
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", res.stderr)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", res.stderr)]
    dur_m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", res.stderr)
    if not dur_m or "Audio:" not in res.stderr:
        return []
    total = int(dur_m.group(1)) * 3600 + int(dur_m.group(2)) * 60 + float(dur_m.group(3))
    speech, t = [], 0.0
    for s, e in zip(starts, ends + [total] * (len(starts) - len(ends))):
        if s - t > 0.1:
            speech.append((round(t, 3), round(s, 3)))
        t = e
    if total - t > 0.1:
        speech.append((round(t, 3), round(total, 3)))
    return speech


def propose_sections(flow: Dict[str, Any], stats: List[Dict[str, Any]], protect: List[Dict[str, Any]],
                     rules: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """依光流提出變速區段（幀號為準）。純函式，方便測試。"""
    rules = rules or SR.DEFAULT_RULES
    fps = float(flow["fps"])
    n = int(flow["frames"])
    rows = flow["rows"]
    speed = [1.0] * n
    kind = ["normal"] * n
    reason = [""] * n

    def mark(f0: int, f1: int, sp: float, k: str, why: str) -> None:
        for f in range(max(0, f0), min(n, f1)):
            speed[f], kind[f], reason[f] = sp, k, why

    # 定住／起手延遲（逐鏡）
    hold_lo, hold_hi = rules.get("hold", [2.0, 3.0])
    for st in stats:
        rr = [r for r in rows if st["start"] <= r["t"] < st["end"]]
        if not rr or st["peak"] <= 0:
            continue
        hi = 0.5 * st["peak"]
        lo = max(0.2 * st["peak"], 6.0)
        if st["onset_s"] >= MIN_ONSET_S and st["onset_s"] < st["dur"] - 1e-6:
            f0 = int(round(st["start"] * fps))
            mark(f0, f0 + int(round(st["onset_s"] * fps)), float(rules.get("windup", 2.5)), "windup",
                 f"{st['shot']} 起手延遲 {st['onset_s']:.2f}s（主體運動低於峰值 50%）")
        run: List[Dict[str, Any]] = []
        for r in rr + [{"f": None, "resid_p95": 1e9}]:
            if r["f"] is not None and r["resid_p95"] < lo:
                run.append(r)
                continue
            if run and len(run) / fps >= MIN_HOLD_S:
                length = len(run) / fps
                sp = float(hold_hi if length > float(rules.get("hold_long_s", 1.2)) else hold_lo)
                # rows 第 k 筆是第 k→k+1 幀的運動，區段取到 run 最後一筆的下一幀
                mark(run[0]["f"], run[-1]["f"] + 1, sp, "hold",
                     f"{st['shot']} 定住 {length:.2f}s（主體運動 < {lo:.1f} px/幀）")
            run = []

    # 開頭凍結：從第 0–2 幀開始連續重複幀
    dup_run = 0
    for r in rows:
        if r["diff"] < DUP_DIFF:
            dup_run += 1
        elif dup_run or r["f"] > 2:
            break
    if dup_run >= MIN_FROZEN_HEAD:
        mark(0, dup_run, float(rules.get("frozen_head", 0)), "frozen_head",
             f"開頭 {dup_run} 幀完全相同（幀差 < {DUP_DIFF}），剪掉")

    # 台詞保護區一律 1×
    for p in protect:
        mark(int(round(p["start"] * fps)) - 1, int(round(p["end"] * fps)) + 1, 1.0, "dialogue", p.get("why", "台詞保護區"))

    sections: List[Dict[str, Any]] = []
    for f in range(n):
        if sections and sections[-1]["speed"] == speed[f] and sections[-1]["kind"] == kind[f]:
            sections[-1]["end_frame"] = f + 1
            continue
        sections.append({"start_frame": f, "end_frame": f + 1, "speed": speed[f], "kind": kind[f], "reason": reason[f]})
    # 太短的變速區段（< 0.25 s）並回 1×，避免頻繁換速
    cleaned: List[Dict[str, Any]] = []
    for s in sections:
        if s["speed"] not in (1.0, 0) and (s["end_frame"] - s["start_frame"]) / fps < 0.25:
            s = dict(s, speed=1.0, kind="normal", reason="")
        if cleaned and cleaned[-1]["speed"] == s["speed"] and cleaned[-1]["kind"] == s["kind"]:
            cleaned[-1]["end_frame"] = s["end_frame"]
        else:
            cleaned.append(dict(s))
    for s in cleaned:
        s["start"] = round(s["start_frame"] / fps, 3)
        s["end"] = round(s["end_frame"] / fps, 3)
        s["shot"] = next((st["shot"] for st in stats if st["start"] <= s["start"] < st["end"]), "")
    return cleaned


# ------------------------------------------------------------------ CLI

def _segments(root: Path, segments_file: Optional[Path]) -> Dict[str, Dict[str, Any]]:
    files = [segments_file] if segments_file else (
        [root / "segments-all.json"] if (root / "segments-all.json").is_file() else sorted(root.glob("segments-ep*.json")))
    out: Dict[str, Dict[str, Any]] = {}
    for f in files:
        raw = json.loads(Path(f).read_text(encoding="utf-8-sig"))
        for seg in raw if isinstance(raw, list) else raw.get("segments", [raw]):
            if seg.get("segment_id"):
                out[str(seg["segment_id"])] = seg
    return out


def run(root: Path, *, segments_file: Optional[Path] = None, only: Optional[List[str]] = None,
        vad: bool = False, force: bool = False, report_only: bool = False) -> Dict[str, Any]:
    root = Path(root).resolve()
    segs = _segments(root, segments_file)
    spec_file = SR.spec_path(root)
    spec = SR.load_spec(spec_file)
    report: Dict[str, Any] = {"segments": {}, "actions": {}}
    qa_dir = root / "videos" / "qa" / "motion"
    qa_dir.mkdir(parents=True, exist_ok=True)
    for sid, seg in segs.items():
        if only and sid not in only:
            continue
        video = root / "videos" / f"{sid}.mp4"
        if not video.is_file():
            continue
        flow = measure(video)
        (qa_dir / f"{sid}.json").write_text(json.dumps(flow), encoding="utf-8")
        stats = shot_stats(flow, shot_bounds(seg, flow))
        protect = protect_windows(seg, detect_speech(video) if vad else None)
        sections = propose_sections(flow, stats, protect, spec.get("rules"))
        changes = [s for s in sections if s["speed"] != 1.0]
        report["segments"][sid] = {"shots": stats, "duplicates": flow["duplicates"], "ramp_sections": len(changes)}
        if report_only or not changes:
            continue
        tmap, new_dur = SR.build_time_map(sections, flow["fps"])
        proposal = {"status": "proposed", "source": f"videos/{sid}.mp4", "source_sha256": SR.sha256_file(video),
                    "fps": flow["fps"], "frames": flow["frames"], "orig_duration_s": round(flow["frames"] / flow["fps"], 3),
                    "est_duration_s": round(new_dur, 3), "protect": protect, "sections": sections,
                    "note": "自動提案：請看影格確認；騰空飄浮光流抓不到要人工標 kind=float、speed 1.8–2；確認後 status 改 approved"}
        report["actions"][sid] = SR.merge_segment(spec, sid, proposal, force=force)
    (qa_dir / "motion-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    if not report_only:
        SR.save_spec(spec_file, spec)
    return report


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="階段 6 動態 QA（光流）＋自動產變速清單 videos/speed-ramps.json")
    ap.add_argument("--root", type=Path, default=Path("."))
    ap.add_argument("--segments", type=Path, help="segments 檔（預設 segments-all.json 或 segments-ep*.json）")
    ap.add_argument("--segment", action="append", help="只量這些段（可重複）")
    ap.add_argument("--vad", action="store_true", help="用 ffmpeg silencedetect 補台詞保護區")
    ap.add_argument("--force", action="store_true", help="已 approved／rendered 的段也重新提案")
    ap.add_argument("--report-only", action="store_true", help="只寫動態報告，不動變速清單")
    args = ap.parse_args(argv)
    rep = run(args.root, segments_file=args.segments, only=args.segment, vad=args.vad,
              force=args.force, report_only=args.report_only)
    for sid, info in rep["segments"].items():
        worst = max(info["shots"], key=lambda s: s["longest_hold_s"], default=None)
        extra = f"；最長定住 {worst['shot']} {worst['longest_hold_s']:.2f}s" if worst else ""
        act = rep["actions"].get(sid, "—")
        print(f"{sid}: 重複幀 {info['duplicates']}、變速區段 {info['ramp_sections']}{extra}；清單 {act}")
    print(f"清單：{SR.SPEC_REL}（人看過、調整後把 status 改 approved，再跑 h3d ramp）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
