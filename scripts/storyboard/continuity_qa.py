#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""`h3d qa --continuity`：階段 6 交界連續性 QA（R3-16 方案 B，只警告、不擋任何關卡）。

現有 qa（時長／色彩／motion／定格）只看段內整體，抓不到「鏡交界跳接」「段交界跳接」「一方靜止」。
這支工具對每段影片：

1. **找實際切點**：模型常提早／延後 0.1–0.5 s 切鏡，用規劃秒數抽格會抽到錯的鏡。
   在每個規劃切點（`metadata.cut_markers[].at_seconds`，沒有就用 `shots[1:].start_time`）
   ±0.9 s 內，算相鄰兩格的 1−相關係數，取最大者為實際切點（新鏡第一格）。
   峰值不夠高（< 0.12）或不比窗內中位數明顯高 → 記「切點不明」警告（可能沒切、或切成溶接）。
2. **拼貼圖**（一段一張 PNG）：
   「上段末格｜本段首格」、每個鏡交界「切前一格｜切後一格」、「本段末格｜下段首格」。
   上／下段依分段檔內順序（同一個分段檔內相鄰），沒有影片就略過那一列。
3. **左中右三欄幀差**：每個鏡（實際切點之間，排除切點那一對）各欄的平均絕對幀差；
   某欄 < 最大欄 25%（且最大欄有明顯動態）→「一側靜止候選」（例如對打時一方定住）。

輸出：`videos/qa/continuity/continuity-report.json`＋`videos/qa/continuity/<段>.png`。
階段 6 審核頁（build_stage_review.py --stage 6）有報告時，每段附拼貼與警告。
這裡**不改任何門禁**：不寫 qa-report.json、不寫 verdicts、不進核准快照；結束碼只反映執行錯誤。
人工 9 項判定（cut_pos、cut_state、seg_in、seg_out、identity、all_move、reaction、causality、smooth）不在這次範圍。

依賴：ffmpeg（解碼）、numpy、Pillow。
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

try:  # numpy 只在真的分析時需要；審核頁讀報告（load_report）不依賴它
    import numpy as np
except ImportError:  # pragma: no cover - Windows CI 沒裝 numpy
    np = None  # type: ignore[assignment]

REPORT_REL = Path("videos") / "qa" / "continuity"
REPORT_NAME = "continuity-report.json"
DEFAULT_WINDOW = 0.9
CUT_MIN_SCORE = 0.12          # 1−相關係數峰值低於此值 → 切點不明
CUT_MIN_RATIO = 2.0           # 峰值 / 窗內中位數 低於此值 → 切點不明
ONE_SIDE_RATIO = 0.25         # 最小欄 < 最大欄 25% → 一側靜止候選
MOTION_FLOOR = 1.0            # 最大欄平均幀差（0–255）低於此值視為整鏡靜止，不判一側靜止
ANALYSIS_WIDTH = 320
SEGMENTS_RE = re.compile(r"^segments-(ep\d+|all)\.json$")


# ---------------------------------------------------------------------------
# 純計算（不需要 ffmpeg，測試直接餵 numpy 陣列）
# ---------------------------------------------------------------------------

def frame_dissimilarity(a: np.ndarray, b: np.ndarray) -> float:
    """1 − 皮爾森相關係數（灰階）；兩格都幾乎是平面色時用平均亮度差判斷。"""
    x = a.astype(np.float64).ravel()
    y = b.astype(np.float64).ravel()
    x -= x.mean()
    y -= y.mean()
    denom = float(np.sqrt((x * x).sum() * (y * y).sum()))
    if denom < 1e-6:
        # 平面色：亮度差 > 8 視為切換
        return 1.0 if abs(float(a.mean()) - float(b.mean())) > 8.0 else 0.0
    return float(1.0 - (x * y).sum() / denom)


def adjacent_dissimilarities(gray: np.ndarray) -> np.ndarray:
    """gray: (N, H, W) → 長度 N−1，第 i 個是第 i 與 i+1 格的 1−相關係數。"""
    return np.array([frame_dissimilarity(gray[i], gray[i + 1]) for i in range(len(gray) - 1)], dtype=np.float64)


def find_cut(diffs: np.ndarray, fps: float, planned: float, window: float = DEFAULT_WINDOW) -> Dict[str, Any]:
    """在 planned ± window 秒內找實際切點；回傳新鏡第一格的索引與秒數。"""
    n = len(diffs)
    lo = max(0, int(np.floor((planned - window) * fps)) - 1)
    hi = min(n - 1, int(np.ceil((planned + window) * fps)))
    result: Dict[str, Any] = {"planned": round(float(planned), 3), "actual": None, "offset": None,
                              "frame": None, "score": None, "ratio": None, "confident": False}
    if n == 0 or hi < lo:
        result["note"] = "規劃切點超出影片長度"
        return result
    win = diffs[lo:hi + 1]
    i = int(lo + int(np.argmax(win)))
    peak = float(diffs[i])
    median = float(np.median(win)) if len(win) else 0.0
    ratio = peak / max(median, 1e-3)
    frame = i + 1  # 新鏡第一格
    actual = frame / fps
    result.update(actual=round(actual, 3), offset=round(actual - planned, 3), frame=frame,
                  score=round(peak, 4), ratio=round(ratio, 2),
                  confident=bool(peak >= CUT_MIN_SCORE and ratio >= CUT_MIN_RATIO))
    return result


def column_motion(gray: np.ndarray, start: int, end: int, skip_pairs: Sequence[int] = ()) -> Dict[str, Any]:
    """[start, end) 格範圍內，左中右三欄的平均絕對幀差；skip_pairs 是要排除的 (i, i+1) 的 i。"""
    w = gray.shape[2]
    bounds = [(0, w // 3), (w // 3, 2 * w // 3), (2 * w // 3, w)]
    sums = np.zeros(3)
    count = 0
    skip = set(skip_pairs)
    for i in range(start, max(start, end - 1)):
        if i in skip or i + 1 >= len(gray):
            continue
        delta = np.abs(gray[i + 1].astype(np.int16) - gray[i].astype(np.int16))
        for k, (a, b) in enumerate(bounds):
            sums[k] += float(delta[:, a:b].mean())
        count += 1
    values = (sums / count) if count else sums
    left, mid, right = (round(float(v), 3) for v in values)
    peak = max(left, mid, right)
    still: Optional[str] = None
    if count and peak >= MOTION_FLOOR:
        names = ("left", "mid", "right")
        low = min(range(3), key=lambda k: values[k])
        if values[low] < ONE_SIDE_RATIO * peak:
            still = names[low]
    return {"left": left, "mid": mid, "right": right, "pairs": count, "one_side_static": still}


# ---------------------------------------------------------------------------
# 影片解碼
# ---------------------------------------------------------------------------

def _probe(video: Path) -> Tuple[int, int, float]:
    probe = shutil.which("ffprobe")
    if not probe:
        raise RuntimeError("找不到 ffprobe")
    out = subprocess.run([probe, "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height,r_frame_rate,avg_frame_rate", "-of", "json", str(video)],
                         capture_output=True, text=True, timeout=60)
    if out.returncode != 0:
        raise RuntimeError(f"ffprobe 失敗：{out.stderr.strip()[:200]}")
    stream = json.loads(out.stdout)["streams"][0]
    rate = stream.get("avg_frame_rate") or stream.get("r_frame_rate") or "24/1"
    num, _, den = rate.partition("/")
    fps = float(num) / float(den or 1) if float(den or 1) else 24.0
    if not fps or fps != fps:
        fps = 24.0
    return int(stream["width"]), int(stream["height"]), fps


def _need_numpy() -> None:
    if np is None:
        raise RuntimeError("交界連續性 QA 需要 numpy（pip install numpy）")


def decode_frames(video: Path, width: int = ANALYSIS_WIDTH) -> Tuple[np.ndarray, float]:
    """回傳 (RGB 影格 (N,H,W,3) uint8, fps)。縮到 width 寬以節省記憶體。"""
    _need_numpy()
    exe = shutil.which("ffmpeg")
    if not exe:
        raise RuntimeError("找不到 ffmpeg")
    src_w, src_h, fps = _probe(video)
    height = max(2, int(round(src_h * width / src_w / 2)) * 2)
    cmd = [exe, "-v", "error", "-i", str(video), "-vf", f"scale={width}:{height}",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    out = subprocess.run(cmd, capture_output=True, timeout=600)
    if out.returncode != 0:
        raise RuntimeError(f"ffmpeg 解碼失敗：{out.stderr.decode('utf-8', 'replace').strip()[:200]}")
    frame_size = width * height * 3
    count = len(out.stdout) // frame_size
    if count < 2:
        raise RuntimeError("影片影格不足 2 格")
    frames = np.frombuffer(out.stdout[:count * frame_size], dtype=np.uint8).reshape(count, height, width, 3)
    return frames, fps


def to_gray(frames: np.ndarray) -> np.ndarray:
    return (frames[..., 0] * 0.299 + frames[..., 1] * 0.587 + frames[..., 2] * 0.114).astype(np.uint8)


# ---------------------------------------------------------------------------
# 分段與規劃切點
# ---------------------------------------------------------------------------

def planned_cuts(seg: Dict[str, Any]) -> List[float]:
    meta = seg.get("metadata") if isinstance(seg.get("metadata"), dict) else {}
    markers = meta.get("cut_markers") or []
    cuts = [float(m["at_seconds"]) for m in markers
            if isinstance(m, dict) and isinstance(m.get("at_seconds"), (int, float)) and m["at_seconds"] > 0]
    if not cuts:
        shots = seg.get("shots") or []
        cuts = [float(s["start_time"]) for s in shots[1:]
                if isinstance(s, dict) and isinstance(s.get("start_time"), (int, float)) and s["start_time"] > 0]
    return sorted(set(round(c, 3) for c in cuts))


def default_segment_files(root: Path) -> List[Path]:
    combined = root / "segments-all.json"
    if combined.is_file():
        return [combined]
    return sorted(p for p in root.glob("segments-ep*.json") if SEGMENTS_RE.match(p.name))


def load_ordered_segments(files: Sequence[Path]) -> List[Dict[str, Any]]:
    """依檔案、檔內順序列出段；每段帶 `_file` 與相鄰段 id（同一個檔內）。"""
    ordered: List[Dict[str, Any]] = []
    seen = set()
    for path in files:
        raw = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        items = raw if isinstance(raw, list) else raw.get("segments", [raw]) if isinstance(raw, dict) else []
        items = [s for s in items if isinstance(s, dict) and s.get("segment_id")]
        for idx, seg in enumerate(items):
            sid = str(seg["segment_id"])
            if sid in seen:
                continue
            seen.add(sid)
            ordered.append({**seg, "_file": Path(path).name,
                            "_prev": str(items[idx - 1]["segment_id"]) if idx > 0 else None,
                            "_next": str(items[idx + 1]["segment_id"]) if idx + 1 < len(items) else None})
    return ordered


# ---------------------------------------------------------------------------
# 拼貼
# ---------------------------------------------------------------------------

def _label_font(size: int):
    from PIL import ImageFont
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow < 10.1
        return ImageFont.load_default()


def build_montage(rows: List[Tuple[str, np.ndarray, np.ndarray]], out: Path, title: str) -> Path:
    """rows: [(標籤, 左格, 右格)]；標籤只用 ASCII（預設字型不含中文）。"""
    from PIL import Image, ImageDraw
    if not rows:
        raise ValueError("沒有可拼貼的列")
    h, w = rows[0][1].shape[:2]
    gap, label_h, head_h = 6, 22, 28
    canvas_w = w * 2 + gap * 3
    canvas_h = head_h + len(rows) * (label_h + h + gap) + gap
    canvas = Image.new("RGB", (canvas_w, canvas_h), (24, 24, 28))
    draw = ImageDraw.Draw(canvas)
    font = _label_font(14)
    draw.text((gap, 6), title, fill=(240, 240, 240), font=font)
    y = head_h
    for label, left, right in rows:
        draw.text((gap, y + 3), label, fill=(255, 210, 120), font=font)
        y += label_h
        for k, frame in enumerate((left, right)):
            img = Image.fromarray(frame)
            if img.size != (w, h):
                img = img.resize((w, h))
            canvas.paste(img, (gap + k * (w + gap), y))
        y += h + gap
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out, format="PNG")
    return out


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def _video_for(root: Path, videos_dir: Path, sid: str) -> Optional[Path]:
    path = videos_dir / f"{sid}.mp4"
    return path if path.is_file() else None


def analyze_segment(root: Path, seg: Dict[str, Any], videos_dir: Path, out_dir: Path,
                    window: float = DEFAULT_WINDOW,
                    cache: Optional[Dict[str, Tuple[np.ndarray, float]]] = None) -> Dict[str, Any]:
    sid = str(seg["segment_id"])
    cache = cache if cache is not None else {}
    entry: Dict[str, Any] = {"segment_id": sid, "segments_file": seg.get("_file"), "warnings": []}
    video = _video_for(root, videos_dir, sid)
    if video is None:
        entry["status"] = "no_video"
        return entry

    def load(path: Path, key: str) -> Tuple[np.ndarray, float]:
        if key not in cache:
            cache[key] = decode_frames(path)
        return cache[key]

    frames, fps = load(video, sid)
    gray = to_gray(frames)
    diffs = adjacent_dissimilarities(gray)
    try:
        entry["video"] = video.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        entry["video"] = str(video)
    entry.update(status="analyzed", fps=round(fps, 3), frames=int(len(frames)),
                 duration=round(len(frames) / fps, 3))
    cuts = []
    for planned in planned_cuts(seg):
        cut = find_cut(diffs, fps, planned, window)
        cuts.append(cut)
        if cut["actual"] is None:
            entry["warnings"].append(f"規劃切點 {planned:.2f}s：{cut.get('note', '找不到')}")
        elif not cut["confident"]:
            entry["warnings"].append(
                f"規劃切點 {planned:.2f}s ±{window}s 內切點不明（峰值 {cut['score']}，倍數 {cut['ratio']}）：可能沒切鏡或切成溶接")
        elif abs(cut["offset"]) > 0.5:
            entry["warnings"].append(f"切點偏離規劃 {cut['offset']:+.2f}s（{planned:.2f}s → {cut['actual']:.2f}s）")
    entry["cuts"] = cuts

    # 每個鏡（實際切點之間）的三欄幀差
    boundaries = [0] + [c["frame"] for c in cuts if c.get("frame")] + [len(frames)]
    cut_pairs = [c["frame"] - 1 for c in cuts if c.get("frame")]
    shots = []
    for k in range(len(boundaries) - 1):
        motion = column_motion(gray, boundaries[k], boundaries[k + 1], cut_pairs)
        motion["shot"] = k + 1
        motion["start"] = round(boundaries[k] / fps, 3)
        motion["end"] = round(boundaries[k + 1] / fps, 3)
        shots.append(motion)
        if motion["one_side_static"]:
            entry["warnings"].append(
                f"第 {k + 1} 鏡一側靜止候選：{motion['one_side_static']} 欄幀差 < 最大欄 {int(ONE_SIDE_RATIO * 100)}%"
                f"（左 {motion['left']}／中 {motion['mid']}／右 {motion['right']}）")
    entry["columns"] = shots

    rows: List[Tuple[str, np.ndarray, np.ndarray]] = []
    neighbours: Dict[str, Optional[str]] = {"prev": None, "next": None}
    prev_sid = seg.get("_prev")
    if prev_sid:
        prev_video = _video_for(root, videos_dir, prev_sid)
        if prev_video is not None:
            pframes, _ = load(prev_video, prev_sid)
            rows.append((f"prev end | this start   ({prev_sid} -> {sid})", pframes[-1], frames[0]))
            neighbours["prev"] = prev_sid
    for idx, cut in enumerate(cuts, start=1):
        if cut.get("frame"):
            f = cut["frame"]
            flag = "" if cut["confident"] else "  [unclear]"
            rows.append((f"cut {idx}: planned {cut['planned']:.2f}s -> actual {cut['actual']:.2f}s "
                         f"({cut['offset']:+.2f}s){flag}", frames[f - 1], frames[f]))
    next_sid = seg.get("_next")
    if next_sid:
        next_video = _video_for(root, videos_dir, next_sid)
        if next_video is not None:
            nframes, _ = load(next_video, next_sid)
            rows.append((f"this end | next start   ({sid} -> {next_sid})", frames[-1], nframes[0]))
            neighbours["next"] = next_sid
    if not rows:
        rows.append(("first | last (no cuts, no neighbours)", frames[0], frames[-1]))
    entry["neighbours"] = neighbours
    montage = build_montage(rows, out_dir / f"{sid}.png", f"{sid}  continuity QA (warning only)")
    try:
        entry["montage"] = montage.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        entry["montage"] = str(montage)
    return entry


def run(root: Path, segment_files: Optional[Sequence[Path]] = None, videos_dir: Optional[Path] = None,
        out_dir: Optional[Path] = None, only: Optional[Sequence[str]] = None,
        window: float = DEFAULT_WINDOW) -> Dict[str, Any]:
    root = Path(root).resolve()
    files = [Path(p) if Path(p).is_absolute() else root / p for p in (segment_files or default_segment_files(root))]
    if not files:
        raise ValueError("找不到 segments-all.json 或 segments-ep*.json")
    videos_dir = Path(videos_dir) if videos_dir else root / "videos"
    if not videos_dir.is_absolute():
        videos_dir = root / videos_dir
    out_dir = Path(out_dir) if out_dir else root / REPORT_REL
    if not out_dir.is_absolute():
        out_dir = root / out_dir
    wanted = set(only or [])
    report: Dict[str, Any] = {
        "tool": "continuity_qa", "gate": "warning_only",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "window_sec": window, "thresholds": {"cut_min_score": CUT_MIN_SCORE, "cut_min_ratio": CUT_MIN_RATIO,
                                             "one_side_ratio": ONE_SIDE_RATIO, "motion_floor": MOTION_FLOOR},
        "segments_files": [p.name for p in files], "segments": [],
    }
    cache: Dict[str, Tuple[np.ndarray, float]] = {}
    ordered = load_ordered_segments(files)
    for seg in ordered:
        sid = str(seg["segment_id"])
        if wanted and sid not in wanted:
            continue
        try:
            entry = analyze_segment(root, seg, videos_dir, out_dir, window, cache)
        except Exception as exc:  # 一段壞掉不影響其他段；照樣只是警告
            entry = {"segment_id": sid, "status": "error", "warnings": [f"分析失敗：{exc}"]}
        report["segments"].append(entry)
        # 只保留相鄰段需要的解碼結果，避免整集影格常駐記憶體
        keep = {sid, seg.get("_next")}
        for key in list(cache):
            if key not in keep:
                cache.pop(key, None)
    analyzed = [s for s in report["segments"] if s.get("status") == "analyzed"]
    report["summary"] = {
        "segments": len(report["segments"]), "analyzed": len(analyzed),
        "no_video": sum(1 for s in report["segments"] if s.get("status") == "no_video"),
        "errors": sum(1 for s in report["segments"] if s.get("status") == "error"),
        "with_warnings": sum(1 for s in report["segments"] if s.get("warnings")),
        "unclear_cuts": sum(1 for s in analyzed for c in s.get("cuts", []) if not c.get("confident")),
        "one_side_static": sum(1 for s in analyzed for c in s.get("columns", []) if c.get("one_side_static")),
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / REPORT_NAME).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report["report_path"] = str(out_dir / REPORT_NAME)
    return report


def load_report(root: Path) -> Dict[str, Dict[str, Any]]:
    """審核頁用：{segment_id: entry}；沒有報告回空 dict。"""
    path = Path(root) / REPORT_REL / REPORT_NAME
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {str(s.get("segment_id")): s for s in data.get("segments", []) if isinstance(s, dict)}


def render(report: Dict[str, Any]) -> str:
    s = report["summary"]
    lines = [f"交界連續性 QA（只警告、不擋關卡）：{report.get('report_path')}",
             f"  分析 {s['analyzed']}/{s['segments']} 段；無影片 {s['no_video']}；失敗 {s['errors']}；"
             f"有警告 {s['with_warnings']} 段（切點不明 {s['unclear_cuts']}、一側靜止候選 {s['one_side_static']}）"]
    for seg in report["segments"]:
        if seg.get("warnings"):
            lines.append(f"  ⚠️ {seg['segment_id']}：" + "；".join(seg["warnings"][:4])
                         + (" …" if len(seg["warnings"]) > 4 else ""))
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="h3d qa --continuity",
                                     description="階段 6 交界連續性 QA：實際切點、交界拼貼、一側靜止候選（只警告）")
    parser.add_argument("--root", type=Path, default=Path("."), help="專案根目錄")
    parser.add_argument("--segments", type=Path, nargs="*", default=None,
                        help="分段檔（預設 segments-all.json，沒有就 segments-ep*.json）")
    parser.add_argument("--videos-dir", type=Path, default=None, help="影片目錄（預設 <root>/videos）")
    parser.add_argument("--out-dir", type=Path, default=None, help=f"輸出目錄（預設 <root>/{REPORT_REL.as_posix()}）")
    parser.add_argument("--segment-id", nargs="*", default=None, help="只跑這些段")
    parser.add_argument("--window", type=float, default=DEFAULT_WINDOW, help="規劃切點前後搜尋秒數（預設 0.9）")
    parser.add_argument("--json", action="store_true", help="以 JSON 輸出")
    args = parser.parse_args(argv)
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        print("❌ 交界連續性 QA 需要 ffmpeg／ffprobe", file=sys.stderr)
        return 2
    if np is None:
        print("❌ 交界連續性 QA 需要 numpy（pip install numpy）", file=sys.stderr)
        return 2
    try:
        report = run(args.root, args.segments, args.videos_dir, args.out_dir, args.segment_id, args.window)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
