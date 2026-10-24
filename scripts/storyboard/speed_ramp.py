#!/usr/bin/env python3
"""依 videos/speed-ramps.json 產出變速版 videos/ramped/<段>.mp4（h3d ramp）。原片永遠不覆寫。

- 只處理 status=approved 的段（--segment 指定時也要 approved；rendered 段加 --rerender 才重產）。
- 影像：依幀號 trim，setpts 除以倍率，最後 fps=<原 fps>（加速區丟幀，不補幀）；speed=0 的區段剪掉。
- 音訊：1× 原音；加速區 atempo（WSOLA，不變調，>2× 串接）；剪掉區段音畫一起剪；接縫各 8 ms 淡入淡出。
- 產檔前斷言：原片 sha 與清單一致、區段連續、倍率 1–3×、台詞保護區全是 1×。
- 產檔後驗證：回讀幀數／長度；台詞保護區變速前後音訊相關係數 ≥ rules.protect_corr_min（預設 0.98），
  不過就刪掉輸出、段落標 verify_failed。
- 結果（output、output_sha256、new_duration_s、delta_s、time_map、verify）只寫回該段（合併寫入，不洗掉別段）。

用法：h3d ramp --root . [--segment EP01-S03-b ...] [--rerender] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import speed_ramps as SR  # noqa: E402

FADE = 0.008
CORR_RATE = 16000


def atempo_chain(speed: float) -> str:
    if abs(speed - 1.0) < 1e-6:
        return "anull"
    parts = []
    while speed > 2.0:
        parts.append("atempo=2.0")
        speed /= 2.0
    parts.append(f"atempo={speed:.5f}")
    return ",".join(parts)


def _probe(path: Path) -> Dict[str, Any]:
    out = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-show_entries",
                          "stream=codec_type,nb_read_frames,duration", "-of", "json", str(path)],
                         capture_output=True, text=True, check=True).stdout
    streams = json.loads(out).get("streams", [])
    v = next(s for s in streams if s["codec_type"] == "video")
    a = [s for s in streams if s["codec_type"] == "audio"]
    return {"frames": int(v.get("nb_read_frames") or 0), "duration": float(v.get("duration") or 0.0),
            "audio": float(a[0]["duration"]) if a and a[0].get("duration") else None, "has_audio": bool(a)}


def build_filter(seg: Dict[str, Any], has_audio: bool) -> str:
    fps = float(seg["fps"])
    parts: List[str] = []
    labels: List[str] = []
    k = 0
    for s in seg["sections"]:
        sp = float(s["speed"])
        if sp == 0:
            continue
        f0, f1 = int(s["start_frame"]), int(s["end_frame"])
        ta, tb = f0 / fps, f1 / fps
        d_out = (tb - ta) / sp
        parts.append(f"[0:v]trim=start_frame={f0}:end_frame={f1},setpts=(PTS-STARTPTS)/{sp:.5f}[v{k}]")
        if has_audio:
            parts.append(f"[0:a]atrim=start={ta:.5f}:end={tb:.5f},asetpts=PTS-STARTPTS,{atempo_chain(sp)},"
                         f"afade=t=in:d={FADE:.3f},afade=t=out:st={max(0.0, d_out - FADE):.5f}:d={FADE:.3f}[a{k}]")
            labels.append(f"[v{k}][a{k}]")
        else:
            labels.append(f"[v{k}]")
        k += 1
    audio_flag = 1 if has_audio else 0
    parts.append(f"{''.join(labels)}concat=n={k}:v=1:a={audio_flag}[vc]" + ("[ac]" if has_audio else ""))
    parts.append(f"[vc]fps={fps:g}[vo]")
    return ";".join(parts)


def _pcm(path: Path, start: float, dur: float):
    import numpy as np  # type: ignore
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{start:.4f}", "-t", f"{dur:.4f}", "-i", str(path),
                          "-ac", "1", "-ar", str(CORR_RATE), "-f", "s16le", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.int16).astype("float32")


def protect_correlation(src: Path, out: Path, protect: List[Dict[str, Any]], time_map: List[Dict[str, Any]],
                        max_lag_s: float = 0.05) -> Optional[float]:
    """台詞保護區：原片與變速版對應區間的音訊相關係數（允許 ±50 ms 偏移），回傳最低值。"""
    try:
        import numpy as np  # type: ignore
    except ImportError:  # pragma: no cover
        return None
    worst: Optional[float] = None
    for p in protect:
        dur = p["end"] - p["start"]
        if dur < 0.2:
            continue
        a = _pcm(src, p["start"], dur)
        b = _pcm(out, SR.map_time(p["start"], time_map), dur)
        n = min(len(a), len(b))
        if n < CORR_RATE * 0.1 or float(np.std(a[:n])) < 1e-3:
            continue
        lag = int(max_lag_s * CORR_RATE)
        best = -1.0
        for shift in range(-lag, lag + 1, 16):
            x = a[max(0, shift):n + min(0, shift)]
            y = b[max(0, -shift):n - max(0, shift)]
            m = min(len(x), len(y))
            if m < CORR_RATE * 0.1 or float(np.std(y[:m])) < 1e-3:
                continue
            best = max(best, float(np.corrcoef(x[:m], y[:m])[0, 1]))
        worst = best if worst is None else min(worst, best)
    return worst


def render(root: Path, sid: str, seg: Dict[str, Any], rules: Dict[str, Any], dry_run: bool = False) -> Dict[str, Any]:
    root = Path(root)
    src = root / (seg.get("source") or f"videos/{sid}.mp4")
    if not src.is_file():
        raise RuntimeError(f"{sid}: 找不到原片 {src}")
    if seg.get("source_sha256") and SR.sha256_file(src) != seg["source_sha256"]:
        raise RuntimeError(f"{sid}: 原片 sha 與清單不符（可能被重跑覆寫），請重跑 h3d motion 重提區段")
    errors = SR.validate_sections(seg, rules)
    if errors:
        raise RuntimeError(f"{sid}: " + "；".join(errors))
    tmap, planned = SR.build_time_map(seg["sections"], float(seg["fps"]))
    if dry_run:
        return {"planned_duration_s": round(planned, 3), "time_map": tmap}
    info = _probe(src)
    out = root / SR.RAMPED_DIR / f"{sid}.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", str(src), "-filter_complex", build_filter(seg, info["has_audio"]),
           "-map", "[vo]"]
    if info["has_audio"]:
        cmd += ["-map", "[ac]", "-c:a", "aac", "-b:a", "160k", "-ar", "48000"]
    cmd += ["-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out)]
    subprocess.run(cmd, check=True, capture_output=True)
    got = _probe(out)
    corr = protect_correlation(src, out, seg.get("protect") or [], tmap) if info["has_audio"] else None
    threshold = float(rules.get("protect_corr_min", 0.98))
    fields: Dict[str, Any] = {
        "output": f"{SR.RAMPED_DIR}/{sid}.mp4", "output_sha256": SR.sha256_file(out),
        "output_frames": got["frames"], "new_duration_s": round(got["duration"], 3),
        "output_audio_s": round(got["audio"], 3) if got["audio"] else None,
        "planned_duration_s": round(planned, 3),
        "delta_s": round(got["duration"] - float(seg.get("orig_duration_s") or info["duration"]), 3),
        "time_map": tmap, "verify": {"protect_corr_min": corr, "threshold": threshold},
        "rendered_at": datetime.now().astimezone().isoformat(timespec="seconds"), "status": "rendered",
    }
    if abs(got["duration"] - planned) > 2.0 / float(seg["fps"]):
        fields["status"] = "verify_failed"
        fields["verify"]["duration_error"] = f"輸出 {got['duration']:.3f}s 與規劃 {planned:.3f}s 差超過 2 幀"
    if corr is not None and corr < threshold:
        fields["status"] = "verify_failed"
        fields["verify"]["error"] = f"台詞保護區音訊相關係數 {corr:.3f} < {threshold}"
    if fields["status"] != "rendered":
        out.unlink(missing_ok=True)
        fields["output"] = None
    return fields


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="依 videos/speed-ramps.json 產出變速版 videos/ramped/<段>.mp4")
    ap.add_argument("--root", type=Path, default=Path("."))
    ap.add_argument("--segment", action="append", help="只處理這些段（可重複）")
    ap.add_argument("--rerender", action="store_true", help="已 rendered 的段也重產")
    ap.add_argument("--dry-run", action="store_true", help="只檢查區段與印出 time_map，不產檔")
    args = ap.parse_args(argv)
    root = args.root.resolve()
    spec_file = SR.spec_path(root)
    data = SR.load_spec(spec_file)
    rules = {**SR.DEFAULT_RULES, **(data.get("rules") or {})}
    todo = []
    for sid, seg in (data.get("segments") or {}).items():
        if args.segment and sid not in args.segment:
            continue
        status = seg.get("status")
        if status == "approved" or (args.rerender and status in ("rendered", "verify_failed")):
            todo.append(sid)
        elif args.segment:
            print(f"⚠️ {sid} 狀態是 {status}，要先人工確認區段並改成 approved")
    if not todo:
        print("沒有 approved 的段可產檔。")
        return 0
    rc = 0
    for sid in todo:
        try:
            fields = render(root, sid, data["segments"][sid], rules, dry_run=args.dry_run)
        except (RuntimeError, subprocess.CalledProcessError) as exc:
            print(f"❌ {exc}")
            rc = 1
            continue
        if args.dry_run:
            print(f"{sid}: 規劃 {data['segments'][sid].get('orig_duration_s')}s → {fields['planned_duration_s']}s")
            continue
        SR.update_render_fields(spec_file, sid, fields)
        mark = "✅" if fields["status"] == "rendered" else "❌"
        corr = fields["verify"].get("protect_corr_min")
        print(f"{mark} {sid}: → {fields['new_duration_s']}s（{fields['delta_s']:+.3f}）"
              + (f"，台詞區相關 {corr:.3f}" if corr is not None else "")
              + (f"；{fields['verify'].get('error') or fields['verify'].get('duration_error')}" if fields["status"] != "rendered" else ""))
        if fields["status"] != "rendered":
            rc = 1
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
