#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_video_shot.py — AI 電影與漫劇影片自動審查與分鏡規格差異檢驗工具
(Video Shot Verifier & Review Gatekeeper v1.0)

用途：
作為「影片審查 Agent」的確定性檢驗核心，比對「實際生成的影片 (MP4)」與「原定 Layer 2 分鏡規格 (layer2/*.json)」，
產出結構化審查報告 (Markdown + JSON) 並可回寫 Layer 2 JSON。

核心檢驗功能（基於 ffmpeg / ffprobe 與 Python 標準庫，零外部依賴）：
1. 時長與技術規格檢驗 (Duration & Specs Check)：
   - 使用 ffprobe 讀取實際時長 (duration)、解析度 (width x height)、FPS、音訊流是否存在。
   - 比對 Layer 2 的 duration (秒數誤差 > 0.5s 觸發 DURATION_MISMATCH 告警)。
   - 比對寬高比 aspect_ratio (16:9, 9:16, 2.39:1, 1:1)。
   - 檢驗台詞與音訊一致性 (has_dialogue 為 true 但缺少音訊流時提醒)。
2. 畫風污染／黑白線稿滲透偵測 (Style Bleed & Grayscale Check)：
   - 抽取首、中、尾 3 幀像素，轉為 CIELAB 空間 (復用 color_qa.py 演算法)。
   - 計算平均彩度 Chroma C* = sqrt(a*^2 + b*^2)。
   - 若非黑白水墨風格但實測 C* < 10.0，自動觸發 STYLE_BLEED_GRAYSCALE 退稿警告！
3. 九宮格分屏殘留偵測 (Grid Split-Screen Check)：
   - 檢查抽樣影格在水平 1/3, 2/3 與垂直 1/3, 2/3 處是否出現低變異度直線分割帶。
   - 若檢測到格線特徵，自動觸發 GRID_PANEL_BORDER_DETECTED 退稿警告！
4. 跨鏡色彩連貫性檢驗 (Inter-shot Color Continuity)：
   - 多鏡審查時計算相鄰鏡頭的色盤距離 pal_dist (dE76)。
   - 若同場景相鄰鏡頭 dE76 > 25.0，發出 COLOR_CONTINUITY_WARNING 光影跳戲警告。
5. VLM / 影片審查 Agent 對照清單生成：
   - 匯出首中尾 Contact Sheet 關鍵幀拼圖。
   - 打包 shot 原定鏡位參數 (shot_size, focal_length, movement, blocking_desc, action_stages, observable_expression, line_verbatim)。
   - 支援 --write-back 回寫 shots[].review 與 segment_end_state.observed_final_state。
6. 自檢模式 (--self-test)：
   - 用 ffmpeg 合成彩色、灰階、九宮格、時長異常等測試假影片，驗證檢驗器 100% 準確攔截與放行。
"""

from __future__ import annotations

import argparse
import collections
from datetime import datetime, timezone
import hashlib
import io
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any, Dict, List, Optional, Tuple

# 確保 Windows 終端以 UTF-8 輸出，避免繁體中文字元編碼異常
if sys.platform.startswith("win"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


# ==============================================================================
# 顏色空間與色盤分析 (復用 color_qa.py CIELAB 演算法)
# ==============================================================================

def to_lab(p: Tuple[int, int, int]) -> Tuple[float, float, float]:
    """sRGB (D65) 轉 CIELAB 空間，回傳 (L*, a*, b*)。"""
    def lin(c: float) -> float:
        c /= 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (lin(x) for x in p)
    X = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    Y = (0.2126 * r + 0.7152 * g + 0.0722 * b)
    Z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883

    def f(t: float) -> float:
        return t ** (1.0 / 3.0) if t > 0.008856 else 7.787 * t + 16.0 / 116.0

    fx, fy, fz = f(X), f(Y), f(Z)
    return (116.0 * fy - 16.0, 500.0 * (fx - fy), 200.0 * (fy - fz))


def get_chroma(lab: Tuple[float, float, float]) -> float:
    """計算 CIELAB 彩度 Chroma C* = sqrt(a*^2 + b*^2)。"""
    return math.sqrt(lab[1] ** 2 + lab[2] ** 2)


def extract_palette(px: List[Tuple[int, int, int]], k: int = 5) -> List[Tuple[float, float, float]]:
    """提取 16-level-per-channel 直方圖前 k 個主要色彩中心並轉為 CIELAB。"""
    if not px:
        return []
    cnt = collections.Counter((r >> 4, g >> 4, b >> 4) for r, g, b in px)
    return [to_lab(tuple((c << 4) + 8 for c in key)) for key, _ in cnt.most_common(k)]


def pal_dist(p: List[Tuple[float, float, float]], q: List[Tuple[float, float, float]]) -> float:
    """計算兩個色盤間的對稱平均最近鄰 dE76 距離。"""
    if not p or not q:
        return 0.0
    a = sum(min(math.dist(x, y) for y in q) for x in p) / len(p)
    b = sum(min(math.dist(x, y) for y in p) for x in q) / len(q)
    return (a + b) / 2.0


# ==============================================================================
# FFprobe / FFmpeg 工具與影格解析
# ==============================================================================

def probe_video_specs(video_path: Path) -> Dict[str, Any]:
    """使用 ffprobe 讀取影片規格（時長、寬高、FPS、音訊等）。"""
    if not video_path.exists():
        raise FileNotFoundError(f"影片檔案不存在: {video_path}")

    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration,size,bit_rate:stream=width,height,r_frame_rate,codec_type,codec_name,duration",
        "-of", "json",
        str(video_path)
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"ffprobe 解析失敗: {res.stderr}")

    info = json.loads(res.stdout)
    streams = info.get("streams", [])
    fmt = info.get("format", {})

    v_stream = next((s for s in streams if s.get("codec_type") == "video"), {})
    a_stream = next((s for s in streams if s.get("codec_type") == "audio"), {})

    width = int(v_stream.get("width", 0))
    height = int(v_stream.get("height", 0))

    # FPS 計算
    fps = 24.0
    r_fps = v_stream.get("r_frame_rate", "24/1")
    if "/" in r_fps:
        try:
            num, den = map(float, r_fps.split("/"))
            if den > 0:
                fps = round(num / den, 2)
        except Exception:
            pass

    # 時長計算 (優先 format.duration，次之 stream.duration)
    duration = 0.0
    if fmt.get("duration"):
        try:
            duration = float(fmt["duration"])
        except ValueError:
            pass
    if duration <= 0.0 and v_stream.get("duration"):
        try:
            duration = float(v_stream["duration"])
        except ValueError:
            pass

    aspect_ratio_val = (width / height) if height > 0 else 0.0

    return {
        "duration": duration,
        "width": width,
        "height": height,
        "fps": fps,
        "aspect_ratio_val": aspect_ratio_val,
        "video_codec": v_stream.get("codec_name", "unknown"),
        "has_audio": bool(a_stream),
        "audio_codec": a_stream.get("codec_name") if a_stream else None,
        "file_size": int(fmt.get("size", 0)),
    }


def extract_frame_rgb(video_path: Path, timestamp: float, w: int = 360, h: int = 202) -> bytes:
    """使用 ffmpeg 抽取指定時間點的縮放 RGB24 影格資料。"""
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel", "error",
        "-ss", f"{timestamp:.3f}",
        "-i", str(video_path),
        "-vframes", "1",
        "-vf", f"scale={w}:{h}",
        "-f", "rawvideo",
        "-pix_fmt", "rgb24",
        "-"
    ]
    res = subprocess.run(cmd, capture_output=True)
    if res.returncode != 0 or len(res.stdout) < w * h * 3:
        raise RuntimeError(f"ffmpeg 抽取影格失敗 (t={timestamp:.3f}s): {res.stderr.decode('utf-8', errors='ignore')}")
    return res.stdout[:w * h * 3]


def generate_contact_sheet(video_path: Path, duration: float, out_path: Path, width: int = 960) -> bool:
    """使用 ffmpeg 抽取首、中、尾 3 幀拼成一張 Contact Sheet 檢驗拼圖。"""
    t1 = min(0.1, duration * 0.1) if duration > 0.3 else 0.0
    t2 = duration / 2.0 if duration > 0.0 else 0.0
    t3 = max(0.0, duration - 0.1) if duration > 0.3 else duration

    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel", "error",
        "-ss", f"{t1:.3f}", "-i", str(video_path),
        "-ss", f"{t2:.3f}", "-i", str(video_path),
        "-ss", f"{t3:.3f}", "-i", str(video_path),
        "-filter_complex", f"[0:v][1:v][2:v]hstack=inputs=3,scale={width}:-1",
        "-vframes", "1",
        str(out_path)
    ]
    res = subprocess.run(cmd, capture_output=True)
    return res.returncode == 0 and out_path.exists()


# ==============================================================================
# 核心檢驗器 (Detectors)
# ==============================================================================

def check_grid_split_screen(raw_rgb: bytes, w: int, h: int) -> Tuple[bool, List[str]]:
    """九宮格分屏殘留偵測 (Grid Split-Screen Check)

    檢查影格在水平 1/3, 2/3 與垂直 1/3, 2/3 處是否出現低變異度的直線分割帶。
    (抓出誤將 3x3 九宮格草圖作為首幀餵入 H3 產生的分屏動畫)。
    """
    detected_borders: List[str] = []

    # 計算明度矩陣 (Y = 0.299R + 0.587G + 0.114B)
    lum_matrix: List[List[float]] = []
    for y in range(h):
        row: List[float] = []
        row_offset = y * w * 3
        for x in range(w):
            idx = row_offset + x * 3
            r, g, b = raw_rgb[idx], raw_rgb[idx + 1], raw_rgb[idx + 2]
            lum = 0.299 * r + 0.587 * g + 0.114 * b
            row.append(lum)
        lum_matrix.append(row)

    # 1. 垂直候選分割線檢查 (x ≈ W/3, 2W/3)
    v_candidates = [
        (round(w / 3.0), "垂直 1/3"),
        (round(2.0 * w / 3.0), "垂直 2/3"),
    ]

    for center_x, label in v_candidates:
        # 在 center_x 左右 4 像素內搜尋是否存在整列方差極低且為深色/隔線的列
        for offset in range(-4, 5):
            cand_x = center_x + offset
            if not (0 <= cand_x < w):
                continue
            col_vals = [lum_matrix[y][cand_x] for y in range(h)]
            col_mean = sum(col_vals) / h
            col_var = sum((v - col_mean) ** 2 for v in col_vals) / h
            col_std = math.sqrt(col_var)

            # 計算左鄰與右鄰列的明度，比對階躍差與凹槽特徵
            left_x = max(0, cand_x - 3)
            right_x = min(w - 1, cand_x + 3)
            left_mean = sum(lum_matrix[y][left_x] for y in range(h)) / h
            right_mean = sum(lum_matrix[y][right_x] for y in range(h)) / h
            edge_diff = max(left_mean - col_mean, right_mean - col_mean)
            is_dip = (left_mean - col_mean > 15.0) and (right_mean - col_mean > 15.0)

            # 判定條件：
            # A) 兩側明顯高於當前列的深色凹槽 (is_dip 且 edge_diff > 15.0)
            # B) 整列為深暗色實線且有階躍 (col_mean < 45.0 且 edge_diff > 12.0)
            # C) 整列高度均質低變異且與兩側有對比 (col_std < 8.0 且 edge_diff > 15.0)
            if (is_dip and edge_diff > 15.0) or (col_mean < 45.0 and edge_diff > 12.0) or (col_std < 8.0 and edge_diff > 15.0):
                detected_borders.append(
                    f"{label} (x={cand_x}/{w}, 均值={col_mean:.1f}, 標準差={col_std:.2f}, 邊緣階躍={edge_diff:.1f})"
                )
                break

    # 2. 水平候選分割線檢查 (y ≈ H/3, 2H/3)
    h_candidates = [
        (round(h / 3.0), "水平 1/3"),
        (round(2.0 * h / 3.0), "水平 2/3"),
    ]

    for center_y, label in h_candidates:
        for offset in range(-4, 5):
            cand_y = center_y + offset
            if not (0 <= cand_y < h):
                continue
            row_vals = lum_matrix[cand_y]
            row_mean = sum(row_vals) / w
            row_var = sum((v - row_mean) ** 2 for v in row_vals) / w
            row_std = math.sqrt(row_var)

            up_y = max(0, cand_y - 3)
            down_y = min(h - 1, cand_y + 3)
            up_mean = sum(lum_matrix[up_y]) / w
            down_mean = sum(lum_matrix[down_y]) / w
            edge_diff = max(up_mean - row_mean, down_mean - row_mean)
            is_dip = (up_mean - row_mean > 15.0) and (down_mean - row_mean > 15.0)

            if (is_dip and edge_diff > 15.0) or (row_mean < 45.0 and edge_diff > 12.0) or (row_std < 8.0 and edge_diff > 15.0):
                detected_borders.append(
                    f"{label} (y={cand_y}/{h}, 均值={row_mean:.1f}, 標準差={row_std:.2f}, 邊緣階躍={edge_diff:.1f})"
                )
                break

    has_grid = len(detected_borders) > 0
    return has_grid, detected_borders


def compute_frame_chroma(raw_rgb: bytes) -> float:
    """計算影格全部像素在 CIELAB 下的平均彩度 Chroma C*。"""
    n_pixels = len(raw_rgb) // 3
    if n_pixels == 0:
        return 0.0

    total_chroma = 0.0
    # 為提升運算效率，快取重複出現的色彩
    cache: Dict[Tuple[int, int, int], float] = {}

    for i in range(0, len(raw_rgb), 3):
        color = (raw_rgb[i], raw_rgb[i + 1], raw_rgb[i + 2])
        if color in cache:
            c_val = cache[color]
        else:
            lab = to_lab(color)
            c_val = get_chroma(lab)
            cache[color] = c_val
        total_chroma += c_val

    return total_chroma / n_pixels


def compute_file_sha256(path: Path) -> str:
    """計算檔案 SHA256 雜湊值。"""
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


# ==============================================================================
# 單鏡影片審查主程序
# ==============================================================================

def verify_single_shot(
    shot_spec: Dict[str, Any],
    video_path: Path,
    segment_meta: Optional[Dict[str, Any]] = None,
    contact_sheet_dir: Optional[Path] = None,
    expected_duration: Optional[float] = None,
) -> Dict[str, Any]:
    """針對單顆鏡頭執行規格與畫質審查，比對 Layer 2 規範。"""
    shot_id = shot_spec.get("shot_id", "UNKNOWN_SHOT")
    if expected_duration is None:
        expected_duration = float(shot_spec.get("duration", 3.0))
    expected_aspect = (segment_meta or {}).get("aspect_ratio", "16:9")
    dlg = shot_spec.get("dialogue_and_audio", {})
    has_dialogue = bool(dlg.get("has_dialogue", False))

    aspect_map = {
        "16:9": 16.0 / 9.0,
        "9:16": 9.0 / 16.0,
        "2.39:1": 2.39,
        "1:1": 1.0,
        "4:3": 4.0 / 3.0,
    }
    target_aspect_val = aspect_map.get(expected_aspect, 16.0 / 9.0)

    # 1. 讀取真實影片規格
    specs = probe_video_specs(video_path)
    actual_duration = specs["duration"]
    actual_aspect_val = specs["aspect_ratio_val"]
    actual_fps = specs["fps"]
    has_audio = specs["has_audio"]

    # 2. 檢驗 1：時長誤差 (大於 0.5s 告警/退稿)
    duration_diff = abs(actual_duration - expected_duration)
    duration_ok = duration_diff <= 0.5
    duration_note = f"預期 {expected_duration:.2f}s, 實際 {actual_duration:.2f}s (差額 {duration_diff:.2f}s)"

    # 寬高比誤差 (相對誤差 > 5% 告警)
    aspect_diff = abs(actual_aspect_val - target_aspect_val) / target_aspect_val if target_aspect_val > 0 else 0
    aspect_ok = aspect_diff <= 0.05
    aspect_note = f"預期 {expected_aspect} ({target_aspect_val:.3f}), 實際 {specs['width']}x{specs['height']} ({actual_aspect_val:.3f})"

    # 音訊流檢驗
    audio_warning = None
    if has_dialogue and not has_audio:
        audio_warning = "分鏡註記包含台詞 (has_dialogue=True)，但影片無音訊軌道 (NO_AUDIO_STREAM_FOR_DIALOGUE)"

    # 3. 抽取首、中、尾 3 幀進行深入分析
    t_head = min(0.1, actual_duration * 0.1) if actual_duration > 0.3 else 0.0
    t_mid = actual_duration / 2.0 if actual_duration > 0.0 else 0.0
    t_tail = max(0.0, actual_duration - 0.1) if actual_duration > 0.3 else actual_duration

    raw_head = extract_frame_rgb(video_path, t_head, w=360, h=202)
    raw_mid = extract_frame_rgb(video_path, t_mid, w=360, h=202)
    raw_tail = extract_frame_rgb(video_path, t_tail, w=360, h=202)

    # 4. 檢驗 2：畫風污染／黑白線稿滲透 (Style Bleed & Grayscale Check)
    c_head = compute_frame_chroma(raw_head)
    c_mid = compute_frame_chroma(raw_mid)
    c_tail = compute_frame_chroma(raw_tail)
    mean_chroma = (c_head + c_mid + c_tail) / 3.0

    # 判斷是否為預設彩色作品 (除非明確指定墨水/黑白風格)
    style_lock = (segment_meta or {}).get("style_lock", {})
    palette_preset = (segment_meta or {}).get("palette_preset", "")
    is_intended_monochrome = any(
        term in str(style_lock).lower() or term in palette_preset.lower()
        for term in ["monochrome", "ink", "grayscale", "black and white", "水墨", "黑白"]
    )

    chroma_ok = True
    chroma_warning = None
    if not is_intended_monochrome and mean_chroma < 10.0:
        chroma_ok = False
        chroma_warning = (
            f"STYLE_BLEED_GRAYSCALE: 影片平均彩度 Chroma C*={mean_chroma:.2f} (< 10.0)，"
            "檢測到嚴重黑白線稿污染！請勿將黑白鉛筆草圖直接餵入 H3。"
        )

    # 5. 檢驗 3：九宮格分屏殘留 (Grid Split-Screen Check)
    grid_detected_mid, border_details_mid = check_grid_split_screen(raw_mid, 360, 202)
    grid_detected_head, border_details_head = check_grid_split_screen(raw_head, 360, 202)
    grid_detected = grid_detected_mid or grid_detected_head
    all_borders = list(set(border_details_mid + border_details_head))

    grid_warning = None
    if grid_detected:
        grid_warning = (
            f"GRID_PANEL_BORDER_DETECTED: 在畫面 1/3 或 2/3 處檢測到低變異度直線分割帶！"
            f"位置: {', '.join(all_borders)}。疑似直接誤將九宮格當作首幀引發分屏動畫。"
        )

    # 6. 色盤與代表色彩提取 (用於跨鏡連貫性檢驗)
    px_tail = [tuple(raw_tail[i:i + 3]) for i in range(0, len(raw_tail), 3)]
    tail_palette = extract_palette(px_tail, k=5)
    mean_tail_lab = to_lab(tuple(sum(p[i] for p in px_tail) // len(px_tail) for i in range(3)))

    # 7. 生成 Contact Sheet 拼圖
    contact_sheet_file = None
    if contact_sheet_dir:
        cs_path = contact_sheet_dir / f"contact_sheet_{shot_id}.jpg"
        if generate_contact_sheet(video_path, actual_duration, cs_path):
            contact_sheet_file = str(cs_path)

    # 總體判定：時長符合、彩度未污染、無九宮格殘留
    passed = duration_ok and chroma_ok and not grid_detected

    issues: List[str] = []
    if not duration_ok:
        issues.append(f"DURATION_MISMATCH: {duration_note}")
    if not aspect_ok:
        issues.append(f"ASPECT_RATIO_MISMATCH: {aspect_note}")
    if chroma_warning:
        issues.append(chroma_warning)
    if grid_warning:
        issues.append(grid_warning)
    if audio_warning:
        issues.append(audio_warning)

    video_sha256 = compute_file_sha256(video_path)

    return {
        "shot_id": shot_id,
        "video_file": str(video_path),
        "video_sha256": video_sha256,
        "passed": passed,
        "review_status": "approved" if passed else "rejected",
        "specs": {
            "duration": actual_duration,
            "expected_duration": expected_duration,
            "duration_diff": round(duration_diff, 3),
            "width": specs["width"],
            "height": specs["height"],
            "fps": actual_fps,
            "aspect_ratio": specs["aspect_ratio_val"],
            "has_audio": has_audio,
        },
        "color_analysis": {
            "c_head": round(c_head, 2),
            "c_mid": round(c_mid, 2),
            "c_tail": round(c_tail, 2),
            "mean_chroma": round(mean_chroma, 2),
            "tail_mean_lab": [round(x, 2) for x in mean_tail_lab],
            "tail_palette_lab": [[round(x, 2) for x in swatch] for swatch in tail_palette],
        },
        "grid_check": {
            "detected": grid_detected,
            "border_details": all_borders,
        },
        "contact_sheet_file": contact_sheet_file,
        "issues": issues,
        "shot_spec_snapshot": {
            "camera_optics": shot_spec.get("camera_optics", {}),
            "spatial_blocking": shot_spec.get("spatial_blocking", {}),
            "action_and_performance": shot_spec.get("action_and_performance", {}),
            "dialogue_and_audio": shot_spec.get("dialogue_and_audio", {}),
        }
    }

def verify_single_segment(
    segment_spec: Dict[str, Any],
    video_path: Path,
    metadata: Optional[Dict[str, Any]] = None,
    contact_sheet_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """針對整個分段 (Segment) 影片執行時長規格、畫質與防污染審查。"""
    sid = segment_spec.get("segment_id") or segment_spec.get("group") or segment_spec.get("id") or "UNKNOWN_SEGMENT"

    # 1. 預期時長計算 (優先取 metadata 總秒數，次之 shots 總和，次之頂層 seconds)
    seg_meta = segment_spec.get("metadata") or metadata or {}
    expected_duration = float(
        seg_meta.get("effective_duration_sec")
        or seg_meta.get("target_duration_sec")
        or 0.0
    )
    if expected_duration <= 0.0 and "shots" in segment_spec:
        expected_duration = sum(float(s.get("duration", 0.0)) for s in segment_spec["shots"])
    if expected_duration <= 0.0:
        expected_duration = float(segment_spec.get("seconds", 8.0))

    expected_aspect = seg_meta.get("aspect_ratio") or segment_spec.get("aspect", "16:9")

    aspect_map = {
        "16:9": 16.0 / 9.0,
        "9:16": 9.0 / 16.0,
        "2.39:1": 2.39,
        "1:1": 1.0,
        "4:3": 4.0 / 3.0,
    }
    target_aspect_val = aspect_map.get(expected_aspect, 16.0 / 9.0)

    # 2. 讀取真實影片規格
    specs = probe_video_specs(video_path)
    actual_duration = specs["duration"]
    actual_aspect_val = specs["aspect_ratio_val"]
    actual_fps = specs["fps"]
    has_audio = specs["has_audio"]

    # 3. 檢驗時長誤差 (大於 0.5s 告警/退稿)
    duration_diff = abs(actual_duration - expected_duration)
    duration_ok = duration_diff <= 0.5
    duration_note = f"預期 {expected_duration:.2f}s, 實際 {actual_duration:.2f}s (差額 {duration_diff:.2f}s)"

    aspect_diff = abs(actual_aspect_val - target_aspect_val) / target_aspect_val if target_aspect_val > 0 else 0
    aspect_ok = aspect_diff <= 0.05
    aspect_note = f"預期 {expected_aspect} ({target_aspect_val:.3f}), 實際 {specs['width']}x{specs['height']} ({actual_aspect_val:.3f})"

    # 4. 抽取影格
    t_head = min(0.1, actual_duration * 0.1) if actual_duration > 0.3 else 0.0
    t_mid = actual_duration / 2.0 if actual_duration > 0.0 else 0.0
    t_tail = max(0.0, actual_duration - 0.1) if actual_duration > 0.3 else actual_duration

    raw_head = extract_frame_rgb(video_path, t_head, w=360, h=202)
    raw_mid = extract_frame_rgb(video_path, t_mid, w=360, h=202)
    raw_tail = extract_frame_rgb(video_path, t_tail, w=360, h=202)

    # 5. 彩度檢驗
    c_head = compute_frame_chroma(raw_head)
    c_mid = compute_frame_chroma(raw_mid)
    c_tail = compute_frame_chroma(raw_tail)
    mean_chroma = (c_head + c_mid + c_tail) / 3.0

    style_lock = seg_meta.get("style_lock", {})
    palette_preset = seg_meta.get("palette_preset", "")
    is_intended_monochrome = any(
        term in str(style_lock).lower() or term in palette_preset.lower()
        for term in ["monochrome", "ink", "grayscale", "black and white", "水墨", "黑白"]
    )

    chroma_ok = True
    chroma_warning = None
    if not is_intended_monochrome and mean_chroma < 10.0:
        chroma_ok = False
        chroma_warning = (
            f"STYLE_BLEED_GRAYSCALE: 分段平均彩度 Chroma C*={mean_chroma:.2f} (< 10.0)，"
            "檢測到嚴重黑白線稿污染！"
        )

    # 6. 九宮格殘留檢驗
    grid_detected_mid, border_details_mid = check_grid_split_screen(raw_mid, 360, 202)
    grid_detected_head, border_details_head = check_grid_split_screen(raw_head, 360, 202)
    grid_detected = grid_detected_mid or grid_detected_head
    all_borders = list(set(border_details_mid + border_details_head))

    grid_warning = None
    if grid_detected:
        grid_warning = (
            f"GRID_PANEL_BORDER_DETECTED: 在畫面檢測到低變異度直線分割帶！位置: {', '.join(all_borders)}"
        )

    # 7. 色盤提取
    px_tail = [tuple(raw_tail[i:i + 3]) for i in range(0, len(raw_tail), 3)]
    tail_palette = extract_palette(px_tail, k=5)
    mean_tail_lab = to_lab(tuple(sum(p[i] for p in px_tail) // len(px_tail) for i in range(3)))

    contact_sheet_file = None
    if contact_sheet_dir:
        cs_path = contact_sheet_dir / f"contact_sheet_{sid}.jpg"
        if generate_contact_sheet(video_path, actual_duration, cs_path):
            contact_sheet_file = str(cs_path)

    passed = duration_ok and chroma_ok and not grid_detected

    issues: List[str] = []
    if not duration_ok:
        issues.append(f"DURATION_MISMATCH: {duration_note}")
    if not aspect_ok:
        issues.append(f"ASPECT_RATIO_MISMATCH: {aspect_note}")
    if chroma_warning:
        issues.append(chroma_warning)
    if grid_warning:
        issues.append(grid_warning)

    sha_hash = compute_file_sha256(video_path)
    return {
        "shot_id": sid,
        "segment_id": sid,
        "is_segment": True,
        "video_file": str(video_path),
        "video_sha256": sha_hash,
        "file_hash_sha256": sha_hash,
        "passed": passed,
        "review_status": "approved" if passed else "rejected",
        "specs": {
            "expected_duration": expected_duration,
            "duration": actual_duration,
            "width": specs["width"],
            "height": specs["height"],
            "fps": specs["fps"],
            "has_audio": specs["has_audio"],
            "aspect_ratio": specs["aspect_ratio_val"],
        },
        "duration_check": {
            "expected_sec": expected_duration,
            "actual_sec": actual_duration,
            "diff_sec": round(duration_diff, 2),
            "ok": duration_ok,
            "note": duration_note,
        },
        "aspect_ratio_check": {
            "expected": expected_aspect,
            "actual_dimensions": f"{specs['width']}x{specs['height']}",
            "actual_ratio": round(actual_aspect_val, 3),
            "ok": aspect_ok,
            "note": aspect_note,
        },
        "technical_specs": specs,
        "color_analysis": {
            "c_head": round(c_head, 2),
            "c_mid": round(c_mid, 2),
            "c_tail": round(c_tail, 2),
            "mean_chroma": round(mean_chroma, 2),
            "tail_mean_lab": [round(x, 2) for x in mean_tail_lab],
            "tail_palette_lab": [[round(x, 2) for x in swatch] for swatch in tail_palette],
        },
        "grid_check": {
            "detected": grid_detected,
            "border_details": all_borders,
        },
        "contact_sheet_file": contact_sheet_file,
        "issues": issues,
    }


# ==============================================================================
# 跨鏡連貫性檢驗
# ==============================================================================

def check_inter_shot_continuity(results: List[Dict[str, Any]]) -> List[str]:
    """檢驗相鄰鏡頭間的色盤距離 pal_dist (dE76)。若大於 25.0 則觸發光影跳戲警告。"""
    warnings: List[str] = []
    if len(results) < 2:
        return warnings

    for i in range(len(results) - 1):
        cur = results[i]
        nxt = results[i + 1]
        p_cur = cur.get("color_analysis", {}).get("tail_palette_lab", [])
        p_nxt = nxt.get("color_analysis", {}).get("tail_palette_lab", [])
        if not p_cur or not p_nxt:
            continue

        p1 = [tuple(c) for c in p_cur]
        p2 = [tuple(c) for c in p_nxt]
        dist = pal_dist(p1, p2)

        if dist > 25.0:
            msg = (
                f"COLOR_CONTINUITY_WARNING: 鏡頭 {cur['shot_id']} 與 {nxt['shot_id']} 色盤距離 dE76={dist:.2f} (> 25.0)！"
                "相鄰鏡頭光影色調跳躍過大，可能發生跳戲。"
            )
            warnings.append(msg)

    return warnings


# ==============================================================================
# 審查報告生成 (Markdown + JSON)
# ==============================================================================

def render_markdown_report(
    results: List[Dict[str, Any]],
    segment_data: Optional[Dict[str, Any]] = None,
    continuity_warnings: Optional[List[str]] = None,
) -> str:
    """產出包含規格、色度、九宮格、分鏡對照與 VLM 審核指引的 Markdown 審查報表。"""
    segment_id = (segment_data or {}).get("segment_id", "UNKNOWN_SEGMENT")
    project_id = (segment_data or {}).get("project_id", "UNKNOWN_PROJECT")
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    total_count = len(results)
    passed_count = sum(1 for r in results if r["passed"])
    rejected_count = total_count - passed_count
    overall_status = "APPROVED (通過)" if rejected_count == 0 else "REJECTED (退稿)"

    lines: List[str] = [
        f"# 影片自動審查與分鏡差異檢驗報告",
        f"",
        f"- **專案編號**：`{project_id}`",
        f"- **片段編號**：`{segment_id}`",
        f"- **審查時間**：`{now_str}`",
        f"- **總體結論**：**{overall_status}**（通過: {passed_count} / 退稿: {rejected_count} / 總鏡數: {total_count}）",
        f"",
        f"---",
        f"",
        f"## 一、鏡頭自動驗收摘要清單",
        f"",
        f"| 鏡頭 ID | 審查狀態 | 時長 (預期/實際) | 解析度/FPS | 平均彩度 C* | 九宮格殘留 | 審查意見摘要 |",
        f"|---|---|---|---|---|---|---|",
    ]

    for r in results:
        status_tag = "✅ APPROVED" if r["passed"] else "❌ REJECTED"
        dur_str = f"{r['specs']['expected_duration']:.1f}s / {r['specs']['duration']:.1f}s"
        res_str = f"{r['specs']['width']}x{r['specs']['height']} @ {r['specs']['fps']}fps"
        chroma_str = f"{r['color_analysis']['mean_chroma']:.1f}"
        grid_str = "⚠️ 檢出邊界" if r["grid_check"]["detected"] else "無殘留"
        issues_summary = "; ".join(r["issues"]) if r["issues"] else "規格全數通過"

        lines.append(
            f"| `{r['shot_id']}` | **{status_tag}** | {dur_str} | {res_str} | {chroma_str} | {grid_str} | {issues_summary} |"
        )

    lines.append("")

    # 跨鏡色彩連貫性
    if continuity_warnings:
        lines.extend([
            f"## 二、跨鏡色彩連貫性警告",
            f"",
        ])
        for w in continuity_warnings:
            lines.append(f"> ⚠️ **{w}**")
        lines.append("")
    else:
        lines.extend([
            f"## 二、跨鏡色彩連貫性檢驗",
            f"",
            f"> ✅ 相鄰鏡頭色盤距離 dE76 均在安全閾值內 (≤ 25.0)，光影連貫無跳戲。",
            f"",
        ])

    # 逐鏡詳細審查與 VLM 對照指引
    lines.extend([
        f"## 三、逐鏡分鏡規格對照與 VLM 語意審查清單",
        f"",
    ])

    for r in results:
        shot_id = r["shot_id"]
        snap = r.get("shot_spec_snapshot", {})
        cam = snap.get("camera_optics", {})
        blocking = snap.get("spatial_blocking", {})
        act = snap.get("action_and_performance", {})
        dlg = snap.get("dialogue_and_audio", {})

        lines.extend([
            f"### 鏡頭 `{shot_id}` 審查詳情",
            f"",
            f"- **影片檔案**：`{r['video_file']}` (SHA256: `{r['video_sha256'][:16]}...`)",
            f"- **Contact Sheet 關鍵幀拼圖**：`{r.get('contact_sheet_file') or '未生成'}`",
            f"- **判定結果**：{'✅ 審核通過' if r['passed'] else '❌ 退稿，需重抽'}",
            f"",
            f"#### 1. 原定 Layer 2 分鏡規格 (SSoT Specification)",
            f"- **光學景別**：`{cam.get('shot_size')}` / 焦距 `{cam.get('focal_length')}` / 運鏡 `{cam.get('movement')}` / 視角 `{cam.get('pov_routing')}`",
            f"- **空間走位**：{blocking.get('blocking_desc')}",
            f"- **動作階段**：{'; '.join(act.get('action_stages', [])) if act.get('action_stages') else '無'}",
            f"- **眼神表情**：{act.get('observable_expression')}",
            f"- **對白內容**：`{dlg.get('line_verbatim') or '（無台詞）'}`",
            f"",
            f"#### 2. VLM / 人工審查員視覺驗收指引",
            f"- [ ] **主體動作還原**：影片是否完整呈現動作階段？（是否有肢體融化、AI 抽搐變形？）",
            f"- [ ] **眼神與神態對齊**：角色的觀察眼神是否符合「{act.get('observable_expression')}」？",
            f"- [ ] **台詞開閉唇守恆**：若無台詞，角色嘴唇是否全程閉合？若有台詞，口型起伏節奏是否吻合？",
            f"- [ ] **道具與背景不可逆狀態**：是否有道具憑空消失或背景融化？",
            f"",
        ])
        if r["issues"]:
            lines.append(f"**退稿原因詳情**：")
            for iss in r["issues"]:
                lines.append(f"- ❌ {iss}")
            lines.append("")

    return "\n".join(lines)


# ==============================================================================
# Layer 2 JSON 回寫功能 (--write-back)
# ==============================================================================

def write_back_review_to_layer2(
    layer2_path: Path,
    results: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """將審查結果更新寫回 Layer 2 JSON (shots[].review 與 segment_end_state.observed_final_state)。"""
    with layer2_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    shots = data.get("shots", [])
    result_map = {r["shot_id"]: r for r in results}
    now_iso = datetime.now(timezone.utc).isoformat()

    last_inspected_result = None

    for shot in shots:
        sid = shot.get("shot_id")
        # 支援完全比對或後綴比對
        matched_res = result_map.get(sid)
        if not matched_res:
            for rid, r in result_map.items():
                if sid.endswith("-" + rid) or sid.endswith("_" + rid):
                    matched_res = r
                    break

        if not matched_res:
            continue

        last_inspected_result = matched_res

        # 1. 更新影片路徑與狀態
        shot["video_file"] = matched_res["video_file"]
        shot["status"] = "video_done"

        # 2. 更新 review 區塊
        rev = shot.get("review") or {}
        old_revision = rev.get("revision", 0)
        passed = matched_res["passed"]

        note_parts = [
            f"時長 {matched_res['specs']['duration']:.2f}s",
            f"彩度 {matched_res['color_analysis']['mean_chroma']:.1f}",
            "九宮格分屏無殘留" if not matched_res['grid_check']['detected'] else "九宮格分屏殘留",
        ]
        if matched_res["issues"]:
            note_parts.append(f"退稿原因: {'; '.join(matched_res['issues'])}")

        shot["review"] = {
            "review_status": "approved" if passed else "rejected",
            "revision": old_revision + 1,
            "locked": bool(passed),
            "reviewer_note": f"[verify_video_shot 自動審核] {'; '.join(note_parts)}",
            "updated_at": now_iso,
            "shot_hash": matched_res["video_sha256"][:8],
        }

    # 3. 更新 segment_end_state.observed_final_state (落實 Observed > Planned 覆蓋鐵律)
    if last_inspected_result:
        end_state = data.get("segment_end_state", {})
        obs_state = end_state.get("observed_final_state") or {}
        obs_state.update({
            "verified_at": now_iso,
            "last_shot_id": last_inspected_result["shot_id"],
            "video_file": last_inspected_result["video_file"],
            "tail_chroma": last_inspected_result["color_analysis"]["c_tail"],
            "tail_mean_lab": last_inspected_result["color_analysis"]["tail_mean_lab"],
            "video_sha256": last_inspected_result["video_sha256"],
            "status": "APPROVED" if last_inspected_result["passed"] else "REJECTED",
        })
        end_state["observed_final_state"] = obs_state
        data["segment_end_state"] = end_state

    # 安全覆寫檔案
    with layer2_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return data


# ==============================================================================
# 自檢模式 (--self-test)
# ==============================================================================

def run_self_test() -> bool:
    """自檢模式：使用 ffmpeg 合成測試色塊/灰階/九宮格假影片，驗證 4 大偵測器能 100% 準確攔截與放行。"""
    print("=" * 70)
    print("【verify_video_shot】啟動自動審核器單元測試與自檢模式 (Self-Test)")
    print("=" * 70)

    with tempfile.TemporaryDirectory() as tmp_dir_str:
        tmp_dir = Path(tmp_dir_str)
        print(f"[*] 建立測試暫存目錄: {tmp_dir}")

        # 1. 建立假 Layer 2 分鏡規範
        fake_layer2 = {
            "project_id": "TEST-PROJ",
            "scene_id": "SC01",
            "segment_id": "SEG01",
            "metadata": {
                "aspect_ratio": "16:9",
                "target_duration_sec": 3.0,
                "pacing_profile": "Standard_Narrative",
                "lighting_lock_line": "Daylight sunlight"
            },
            "continuity_handshake": {"mode": "SEAMLESS_CONTINUATION"},
            "shots": [
                {
                    "shot_id": "SH01_NORMAL",
                    "duration": 3.0,
                    "camera_optics": {"shot_size": "MS", "focal_length": "35mm", "movement": "Pan", "pov_routing": "objective"},
                    "spatial_blocking": {"blocking_desc": "Center standing"},
                    "action_and_performance": {"action_stages": ["Stand still"], "observable_expression": "Neutral"},
                    "dialogue_and_audio": {"has_dialogue": True, "line_verbatim": "測試台詞", "lips_closed_lock": False}
                },
                {
                    "shot_id": "SH02_GRAYSCALE",
                    "duration": 3.0,
                    "camera_optics": {"shot_size": "CU", "focal_length": "50mm", "movement": "Static", "pov_routing": "objective"},
                    "spatial_blocking": {"blocking_desc": "Close frame"},
                    "action_and_performance": {"action_stages": ["Stare"], "observable_expression": "Serious"},
                    "dialogue_and_audio": {"has_dialogue": False, "lips_closed_lock": True}
                },
                {
                    "shot_id": "SH03_GRID",
                    "duration": 3.0,
                    "camera_optics": {"shot_size": "LS", "focal_length": "24mm", "movement": "Static", "pov_routing": "objective"},
                    "spatial_blocking": {"blocking_desc": "Wide view"},
                    "action_and_performance": {"action_stages": ["Walk"], "observable_expression": "Calm"},
                    "dialogue_and_audio": {"has_dialogue": False, "lips_closed_lock": True}
                },
                {
                    "shot_id": "SH04_BADDUR",
                    "duration": 3.0,
                    "camera_optics": {"shot_size": "MS", "focal_length": "35mm", "movement": "Static", "pov_routing": "objective"},
                    "spatial_blocking": {"blocking_desc": "Standing"},
                    "action_and_performance": {"action_stages": ["Pose"], "observable_expression": "Smirk"},
                    "dialogue_and_audio": {"has_dialogue": False, "lips_closed_lock": True}
                }
            ],
            "segment_end_state": {"planned_final_state": {"pos": "center"}}
        }
        layer2_file = tmp_dir / "test_layer2.json"
        with layer2_file.open("w", encoding="utf-8") as f:
            json.dump(fake_layer2, f, ensure_ascii=False, indent=2)

        # 2. 合成 4 個測試假影片
        # A: 正常彩色影片 (3.0s, 16:9, 彩色, 帶音訊)
        p_normal = tmp_dir / "normal_color.mp4"
        cmd_a = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "testsrc=duration=3.0:size=1280x720:rate=24",
            "-f", "lavfi", "-i", "sine=frequency=1000:duration=3.0",
            "-c:v", "libx264", "-c:a", "aac", "-pix_fmt", "yuv420p",
            str(p_normal)
        ]
        subprocess.run(cmd_a, check=True)

        # B: 灰階黑白污染影片 (3.0s, 16:9, 灰階)
        p_gray = tmp_dir / "grayscale_bleed.mp4"
        cmd_b = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "testsrc=duration=3.0:size=1280x720:rate=24",
            "-vf", "format=gray,format=yuv420p",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            str(p_gray)
        ]
        subprocess.run(cmd_b, check=True)

        # C: 九宮格分屏殘留影片 (3.0s, 16:9, 帶 1/3, 2/3 黑線)
        p_grid = tmp_dir / "grid_splitscreen.mp4"
        # 1280x720 (16:9), 1/3≈427, 2/3≈853, y: 1/3=240, 2/3=480
        grid_filter = (
            "drawbox=x=426:y=0:w=3:h=720:color=black@1.0:t=fill,"
            "drawbox=x=852:y=0:w=3:h=720:color=black@1.0:t=fill,"
            "drawbox=x=0:y=239:w=1280:h=3:color=black@1.0:t=fill,"
            "drawbox=x=0:y=479:w=1280:h=3:color=black@1.0:t=fill"
        )
        cmd_c = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "testsrc=duration=3.0:size=1280x720:rate=24",
            "-vf", grid_filter,
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            str(p_grid)
        ]
        subprocess.run(cmd_c, check=True)

        # D: 時長不符影片 (1.5s vs 預期 3.0s)
        p_baddur = tmp_dir / "bad_duration.mp4"
        cmd_d = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "testsrc=duration=1.5:size=1280x720:rate=24",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            str(p_baddur)
        ]
        subprocess.run(cmd_d, check=True)

        print("[*] 4 種測試影片合成完畢，開始執行各檢驗器驗證...")

        all_tests_passed = True

        # 測試 1：正常彩色影片審查 -> 預期 PASS
        res1 = verify_single_shot(fake_layer2["shots"][0], p_normal, fake_layer2["metadata"], contact_sheet_dir=tmp_dir)
        print(f"\n[Test 1] 正常彩色影片審查:")
        print(f"  - 通過狀態: {res1['passed']} (預期: True)")
        print(f"  - 時長誤差: {res1['specs']['duration_diff']}s")
        print(f"  - 平均彩度: {res1['color_analysis']['mean_chroma']}")
        print(f"  - 九宮格殘留: {res1['grid_check']['detected']}")
        if not (res1["passed"] and res1["color_analysis"]["mean_chroma"] > 10.0 and not res1["grid_check"]["detected"]):
            print("  ❌ 失敗: 正常影片未獲批准！")
            all_tests_passed = False
        else:
            print("  ✅ 成功放行正常彩色影片！")

        # 測試 2：灰階線稿滲透審查 -> 預期 觸發 STYLE_BLEED_GRAYSCALE 退稿
        res2 = verify_single_shot(fake_layer2["shots"][1], p_gray, fake_layer2["metadata"], contact_sheet_dir=tmp_dir)
        print(f"\n[Test 2] 灰階黑白污染影片審查:")
        print(f"  - 通過狀態: {res2['passed']} (預期: False)")
        print(f"  - 平均彩度: {res2['color_analysis']['mean_chroma']} (預期 < 10.0)")
        has_gray_warning = any("STYLE_BLEED_GRAYSCALE" in iss for iss in res2["issues"])
        print(f"  - 觸發 STYLE_BLEED_GRAYSCALE: {has_gray_warning}")
        if not (not res2["passed"] and has_gray_warning):
            print("  ❌ 失敗: 未能攔截灰階污染！")
            all_tests_passed = False
        else:
            print("  ✅ 成功精確攔截灰階線稿滲透！")

        # 測試 3：九宮格分屏殘留審查 -> 預期 觸發 GRID_PANEL_BORDER_DETECTED 退稿
        res3 = verify_single_shot(fake_layer2["shots"][2], p_grid, fake_layer2["metadata"], contact_sheet_dir=tmp_dir)
        print(f"\n[Test 3] 九宮格分屏殘留影片審查:")
        print(f"  - 通過狀態: {res3['passed']} (預期: False)")
        print(f"  - 九宮格檢測: {res3['grid_check']['detected']} (預期: True)")
        has_grid_warning = any("GRID_PANEL_BORDER_DETECTED" in iss for iss in res3["issues"])
        print(f"  - 觸發 GRID_PANEL_BORDER_DETECTED: {has_grid_warning}")
        if not (not res3["passed"] and has_grid_warning):
            print("  ❌ 失敗: 未能攔截九宮格分屏殘留！")
            all_tests_passed = False
        else:
            print("  ✅ 成功精確攔截九宮格分屏殘留！")

        # 測試 4：時長誤差審查 -> 預期 觸發 DURATION_MISMATCH 退稿
        res4 = verify_single_shot(fake_layer2["shots"][3], p_baddur, fake_layer2["metadata"], contact_sheet_dir=tmp_dir)
        print(f"\n[Test 4] 時長嚴重偏差影片審查:")
        print(f"  - 通過狀態: {res4['passed']} (預期: False)")
        print(f"  - 時長誤差: {res4['specs']['duration_diff']}s (預期 > 0.5s)")
        has_dur_warning = any("DURATION_MISMATCH" in iss for iss in res4["issues"])
        print(f"  - 觸發 DURATION_MISMATCH: {has_dur_warning}")
        if not (not res4["passed"] and has_dur_warning):
            print("  ❌ 失敗: 未能攔截時長異常！")
            all_tests_passed = False
        else:
            print("  ✅ 成功精確攔截時長不符！")

        # 測試 5：回寫至 Layer 2 JSON
        print(f"\n[Test 5] 回寫至 Layer 2 JSON (--write-back):")
        updated_data = write_back_review_to_layer2(layer2_file, [res1, res2, res3, res4])
        s0_rev = updated_data["shots"][0].get("review", {})
        end_obs = updated_data.get("segment_end_state", {}).get("observed_final_state", {})
        print(f"  - Shot 0 review_status: {s0_rev.get('review_status')} (預期: approved)")
        print(f"  - Shot 0 revision: {s0_rev.get('revision')} (預期: 1)")
        print(f"  - observed_final_state tail_chroma: {end_obs.get('tail_chroma')}")
        if s0_rev.get("review_status") != "approved" or not end_obs.get("tail_chroma") is not None:
            print("  ❌ 失敗: 回寫 Layer 2 結構不正確！")
            all_tests_passed = False
        else:
            print("  ✅ 成功回寫 Layer 2 shots[].review 與 segment_end_state.observed_final_state！")

        # 測試 6：Contact Sheet 拼圖生成驗證
        cs_file = Path(res1["contact_sheet_file"]) if res1.get("contact_sheet_file") else None
        if cs_file and cs_file.exists() and cs_file.stat().st_size > 1000:
            print(f"  ✅ 成功產出 Contact Sheet 拼圖: {cs_file.name} (大小: {cs_file.stat().st_size} bytes)")
        else:
            print("  ❌ 失敗: Contact Sheet 拼圖未生成或檔案為空！")
            all_tests_passed = False

        print("\n" + "=" * 70)
        if all_tests_passed:
            print("🎉 【verify_video_shot】所有自檢測試 100% 通過！4 大偵測器與回寫機制全部驗證完畢！")
            print("=" * 70)
            return True
        else:
            print("❌ 【verify_video_shot】自檢測試有項目未通過，請檢查邏輯！")
            print("=" * 70)
            return False


# ==============================================================================
# CLI 入口
# ==============================================================================

def main() -> int:
    parser = argparse.ArgumentParser(
        description="verify_video_shot.py — AI 影片自動審核與分鏡差異檢驗工具 (v2.0 支援批次分段與色差整合)"
    )
    parser.add_argument("--layer2", type=Path, help="Layer 2 分鏡規格 JSON 路徑 (e.g. layer2/segment-01.json)")
    parser.add_argument("--layer2-dir", type=Path, help="批次審查整個目錄下的 layer2-*.json 檔案")
    parser.add_argument("--segments", type=Path, help="compile_layer2_to_h3 產出的 segments-epXX.json 批次分段檔")
    parser.add_argument("--videos-dir", type=Path, help="影片所在目錄 (搭配 --segments 或 --layer2-dir 批次尋找 mp4)")
    parser.add_argument("--shot", type=str, help="指定審查的單個 shot_id (如 SH01 或 EP01-S01-a-SH01)")
    parser.add_argument("--video", type=Path, help="指定要審查的 MP4 影片路徑")
    parser.add_argument("--segment-mode", action="store_true", help="強制以分段 (Segment) 總時長而非單鏡時長比對影片")
    parser.add_argument("--all-shots", action="store_true", help="審查 Layer 2 中所有已設定 video_file 的鏡頭")
    parser.add_argument("--contact-dir", type=Path, help="Contact Sheet 拼圖儲存目錄 (預設為影片同目錄)")
    parser.add_argument("--out-report", type=Path, help="輸出 Markdown 審查報表路徑")
    parser.add_argument("--out-json", type=Path, help="輸出結構化 JSON 審查報告路徑")
    parser.add_argument("--write-back", action="store_true", help="將審查結果回寫至 Layer 2 JSON")
    parser.add_argument("--self-test", action="store_true", help="執行合成影片自檢單元測試")

    args = parser.parse_args()

    if args.self_test:
        success = run_self_test()
        return 0 if success else 1

    # =========================================================================
    # 模式 1：--segments 批次分段審查
    # =========================================================================
    if args.segments:
        if not args.segments.exists():
            sys.exit(f"❌ 錯誤: 分段檔不存在: {args.segments}")
        with args.segments.open("r", encoding="utf-8") as f:
            seg_data = json.load(f)

        raw_list = seg_data if isinstance(seg_data, list) else seg_data.get("segments", [seg_data])
        v_dir = args.videos_dir or args.segments.parent / "videos"
        contact_dir = args.contact_dir or (v_dir / "reviews")
        contact_dir.mkdir(parents=True, exist_ok=True)

        results: List[Dict[str, Any]] = []
        unproduced: List[str] = []

        for seg in raw_list:
            sid = seg.get("segment_id") or seg.get("group") or seg.get("id")
            if not sid:
                continue
            # 尋找對應的影片檔
            cand_files = [
                v_dir / f"{sid}.mp4",
                v_dir / f"{sid.lower()}.mp4",
                v_dir / f"seg-{sid}.mp4",
            ]
            found_v = next((p for p in cand_files if p.exists()), None)
            if not found_v:
                # 模糊比對
                found_v = next((p for p in v_dir.glob("*.mp4") if sid.lower() in p.stem.lower()), None)

            if found_v and found_v.exists():
                res = verify_single_segment(seg, found_v, contact_sheet_dir=contact_dir)
                results.append(res)
            else:
                unproduced.append(sid)

        continuity_warnings = check_inter_shot_continuity(results)
        report_md = render_markdown_report(results, {"project_id": args.segments.stem, "segment_id": "BATCH"}, continuity_warnings)

        if unproduced:
            report_md += f"\n\n### ⚠️ 尚未生成影片之分段 ({len(unproduced)} 段)\n"
            report_md += ", ".join(f"`{u}`" for u in unproduced) + "\n"

        if args.out_report:
            args.out_report.parent.mkdir(parents=True, exist_ok=True)
            args.out_report.write_text(report_md, encoding="utf-8")
            print(f"[+] Markdown 審查報表已寫入: {args.out_report}")
        else:
            print("\n" + report_md + "\n")

        if args.out_json:
            args.out_json.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "results": results,
                "unproduced_segments": unproduced,
                "continuity_warnings": continuity_warnings,
                "generated_at": datetime.now(timezone.utc).isoformat()
            }
            with args.out_json.open("w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            print(f"[+] 結構化 JSON 審查報告已寫入: {args.out_json}")

        has_rejected = any(not r["passed"] for r in results)
        return 1 if (has_rejected or not results) else 0

    # =========================================================================
    # 模式 2：--layer2-dir 批次目錄審查
    # =========================================================================
    if args.layer2_dir:
        if not args.layer2_dir.exists():
            sys.exit(f"❌ 錯誤: Layer 2 目錄不存在: {args.layer2_dir}")
        l2_files = sorted(args.layer2_dir.glob("layer2-*.json"))
        if not l2_files:
            sys.exit(f"❌ 錯誤: 在 {args.layer2_dir} 中找不到任何 layer2-*.json 檔案！")

        v_dir = args.videos_dir or args.layer2_dir.parent / "videos"
        contact_dir = args.contact_dir or (v_dir / "reviews")
        contact_dir.mkdir(parents=True, exist_ok=True)

        results: List[Dict[str, Any]] = []
        unproduced: List[str] = []

        for lf in l2_files:
            with lf.open("r", encoding="utf-8") as f:
                ldata = json.load(f)
            sid = ldata.get("metadata", {}).get("segment_id") or lf.stem.replace("layer2-", "")
            cand_files = [v_dir / f"{sid}.mp4", v_dir / f"{sid.lower()}.mp4"]
            found_v = next((p for p in cand_files if p.exists()), None)
            if not found_v:
                found_v = next((p for p in v_dir.glob("*.mp4") if sid.lower() in p.stem.lower()), None)

            if found_v and found_v.exists():
                res = verify_single_segment(ldata, found_v, ldata.get("metadata"), contact_sheet_dir=contact_dir)
                results.append(res)
            else:
                unproduced.append(sid)

        continuity_warnings = check_inter_shot_continuity(results)
        report_md = render_markdown_report(results, {"project_id": args.layer2_dir.parent.name, "segment_id": "BATCH"}, continuity_warnings)

        if unproduced:
            report_md += f"\n\n### ⚠️ 尚未生成影片之分段 ({len(unproduced)} 段)\n"
            report_md += ", ".join(f"`{u}`" for u in unproduced) + "\n"

        if args.out_report:
            args.out_report.parent.mkdir(parents=True, exist_ok=True)
            args.out_report.write_text(report_md, encoding="utf-8")
            print(f"[+] Markdown 審查報表已寫入: {args.out_report}")
        else:
            print("\n" + report_md + "\n")

        if args.out_json:
            args.out_json.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "results": results,
                "unproduced_segments": unproduced,
                "continuity_warnings": continuity_warnings,
                "generated_at": datetime.now(timezone.utc).isoformat()
            }
            with args.out_json.open("w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            print(f"[+] 結構化 JSON 審查報告已寫入: {args.out_json}")

        has_rejected = any(not r["passed"] for r in results)
        return 1 if (has_rejected or not results) else 0

    # =========================================================================
    # 模式 3：單個 --layer2 審查模式 (向後相容)
    # =========================================================================
    if not args.layer2:
        parser.error("請提供 --layer2, --layer2-dir, --segments 或使用 --self-test。")

    if not args.layer2.exists():
        sys.exit(f"錯誤: Layer 2 檔案不存在: {args.layer2}")

    with args.layer2.open("r", encoding="utf-8") as f:
        layer2_data = json.load(f)

    shots: List[Dict[str, Any]] = layer2_data.get("shots", [])
    if not shots:
        sys.exit(f"錯誤: {args.layer2} 中未包含任何 shots 鏡頭資料！")

    contact_dir = args.contact_dir or (args.layer2.parent / "reviews")
    contact_dir.mkdir(parents=True, exist_ok=True)

    results: List[Dict[str, Any]] = []

    # 決定要審查的鏡頭與影片列表
    if args.shot:
        target_shot = next((s for s in shots if s.get("shot_id") == args.shot or s.get("shot_id", "").endswith(args.shot)), None)
        if not target_shot:
            sys.exit(f"錯誤: 在 Layer 2 中找不到鏡頭 ID: {args.shot}")

        video_path = args.video or Path(target_shot.get("video_file", ""))
        if not video_path or not video_path.exists():
            sys.exit(f"錯誤: 找不到鏡頭 {args.shot} 的影片檔案 (請透過 --video 指定或先在 Layer 2 填入 video_file)")

        res = verify_single_shot(target_shot, video_path, layer2_data.get("metadata"), contact_sheet_dir=contact_dir)
        results.append(res)

    elif args.video:
        if args.segment_mode or len(shots) > 1:
            # 支援分段時長比對模式
            res = verify_single_segment(layer2_data, args.video, layer2_data.get("metadata"), contact_sheet_dir=contact_dir)
            results.append(res)
        else:
            target_shot = shots[0]
            res = verify_single_shot(target_shot, args.video, layer2_data.get("metadata"), contact_sheet_dir=contact_dir)
            results.append(res)

    else:
        # 審查所有有 video_file 的鏡頭
        checked_count = 0
        for s in shots:
            vf = s.get("video_file")
            if vf:
                v_path = Path(vf)
                if not v_path.is_absolute():
                    v_path = (args.layer2.parent / v_path).resolve()
                if v_path.exists():
                    res = verify_single_shot(s, v_path, layer2_data.get("metadata"), contact_sheet_dir=contact_dir)
                    results.append(res)
                    checked_count += 1
        if checked_count == 0:
            sys.exit("錯誤: 未指定 --shot 或 --video，且 Layer 2 中所有 shots 均無有效的 video_file！")

    # 跨鏡連貫性檢驗
    continuity_warnings = check_inter_shot_continuity(results)

    # 產生 Markdown 報表
    report_md = render_markdown_report(results, layer2_data, continuity_warnings)

    if args.out_report:
        args.out_report.parent.mkdir(parents=True, exist_ok=True)
        args.out_report.write_text(report_md, encoding="utf-8")
        print(f"[+] Markdown 審查報表已寫入: {args.out_report}")
    else:
        print("\n" + report_md + "\n")

    if args.out_json:
        args.out_json.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "results": results,
            "continuity_warnings": continuity_warnings,
            "generated_at": datetime.now(timezone.utc).isoformat()
        }
        with args.out_json.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(f"[+] 結構化 JSON 審查報告已寫入: {args.out_json}")

    # 回寫功能
    if args.write_back:
        write_back_review_to_layer2(args.layer2, results)
        print(f"[+] 審查結果已成功回寫至 Layer 2: {args.layer2}")

    # 若有任一鏡頭未通過，返回退出碼 1
    has_rejected = any(not r["passed"] for r in results)
    return 1 if has_rejected else 0


if __name__ == "__main__":
    sys.exit(main())
