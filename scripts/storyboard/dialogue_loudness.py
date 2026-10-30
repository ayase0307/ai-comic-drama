#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dialogue_loudness.py — 階段 7 跨段「以對白為錨」電平對齊（h3d assemble 用）。

為什麼要有這一步：畫內對白與短旁白保留 H3 原生音（skill-guide 階段 7），而 H3 每支 clip 各自生成
原生音訊、電平隨機。《噩盡島》EP01 重跑 30 支實測 integrated −9.94～−28.71 LUFS（落差 18.77 LU），
只量人聲區段也差 18.82 LU；整片單遍 loudnorm 之後段與段之間仍差 13.53 LU。整片 loudnorm
只能搬整條節目的平均，修不了段間落差。

做法（不壓平動態，回應 pipeline.md §7.4「逐段正規化會壓平段間動態」的顧慮）：
  1. 每段只量**對白區段**（speech_window；缺了用鏡頭時間；都沒有就用整段的 gated integrated，
     BS.1770 閘門本身會略過靜音＝能量偵測退回）的 integrated loudness。
  2. 錨點＝有對白段的人聲響度中位數（或 --dialogue-anchor 指定的 LUFS）；每個有對白的段算一個
     **固定增益**對齊錨點（上下限 ±max_gain dB），整段一起搬，段內動態不變。
  3. 無台詞段**不拉到錨點**：增益 0（保持原本相對電平）；只有比錨點還響超過 ambient_ceiling_lu
     時才往下壓到上限（防止一支爆音 clip 蓋過全片）。
  4. TP 保護：增益後預估 true peak 超過 tp_ceiling 的段，在 192 kHz 下過 alimiter
     （192 kHz 取樣峰值近似 true peak）；需要的壓限量超過 limiter_headroom 就把增益收小。

這個模組只做量測與增益計畫；套用在 assemble_episode.build_pcm_audio_track（段先解成 PCM、
長度鎖成影片長度，所以不會有「每段重編 AAC 尾巴多一個 frame、串接後時間軸漂移」的問題）。
"""
from __future__ import annotations

import json
import math
import re
import statistics
import subprocess
from typing import Any, Dict, List, Optional, Sequence, Tuple

try:
    import media_tools
except ImportError:  # pragma: no cover - 套件匯入路徑
    from . import media_tools

DEFAULT_MAX_GAIN_DB = 12.0
DEFAULT_AMBIENT_CEILING_LU = 6.0
DEFAULT_TP_CEILING_DBTP = -1.0
DEFAULT_LIMITER_HEADROOM_DB = 9.0  # 段層限幅最多壓這麼多 dB；H3 clip 常有單發重擊（E1-13 crest 22.9 dB），6 dB 會把增益截住
DEFAULT_SPREAD_WARN_LU = 6.0
SEGMENT_TP_FLOOR_DBTP = -6.0  # 段層限幅門檻最低到這裡；整片還要大幅拉升時寧可讓 loudnorm 回退 dynamic，也不在段層重壓
AAC_TP_MARGIN_DB = 0.5     # 限幅後再編 AAC，解碼峰值會冒高一點；限幅器設在目標 TP 下方這麼多
MIN_MEASURE_SECONDS = 0.4  # BS.1770 一個閘門區塊 400 ms；更短量不出 integrated
INVALID_LUFS = -60.0       # loudnorm 量到 -70／-inf＝整段被閘門擋掉（幾乎沒聲音）

Window = Tuple[float, float]


def _num(value: Any) -> Optional[float]:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def clip_windows(windows: Sequence[Window], duration: float, offset: float = 0.0) -> List[Window]:
    """把時間窗平移 −offset、裁進 [0, duration]、合併重疊；太短（<50 ms）的丟掉。"""
    out: List[Window] = []
    for start, end in sorted((float(s) - offset, float(e) - offset) for s, e in windows):
        start, end = round(max(0.0, start), 6), round(min(float(duration), end), 6)
        if end - start < 0.05:
            continue
        if out and start <= out[-1][1] + 1e-6:
            out[-1] = (out[-1][0], max(out[-1][1], end))
        else:
            out.append((start, end))
    return out


def measure(path: str, windows: Optional[Sequence[Window]] = None, start: float = 0.0,
            duration: Optional[float] = None) -> Dict[str, float]:
    """量一個檔案（或其中 start..start+duration 一段、再取其中 windows 串起來）的響度。

    回傳 {"I","TP","LRA","thresh","seconds"}（loudnorm 第一遍的 input_*）；呼叫端要先確認有音軌。
    windows 是相對 start 的秒數。"""
    cmd = [media_tools.ffmpeg_bin(), "-hide_banner", "-nostats"]
    if start > 0:
        cmd += ["-ss", f"{start:.6f}"]
    if duration is not None:
        cmd += ["-t", f"{duration:.6f}"]
    cmd += ["-i", str(path), "-vn"]
    probe = "loudnorm=I=-23:TP=-1:LRA=11:print_format=json"
    seconds = duration
    if windows:
        wins = list(windows)
        seconds = sum(e - s for s, e in wins)
        n = len(wins)
        parts = [f"[0:a]asplit={n}" + "".join(f"[s{i}]" for i in range(n))]
        parts += [f"[s{i}]atrim=start={s:.6f}:end={e:.6f},asetpts=PTS-STARTPTS[w{i}]" for i, (s, e) in enumerate(wins)]
        parts.append("".join(f"[w{i}]" for i in range(n)) + f"concat=n={n}:v=0:a=1,{probe}[out]")
        cmd += ["-filter_complex", ";".join(parts), "-map", "[out]"]
    else:
        cmd += ["-af", probe]
    cmd += ["-f", "null", "-"]
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    found = re.findall(r"\{[^{}]*\"input_i\"[^{}]*\}", res.stderr, re.S)
    if not found:
        raise RuntimeError(f"響度量測失敗 {path}: {res.stderr[-400:]}")
    data = json.loads(found[-1])
    lufs = _num(data.get("input_i"))
    tp = _num(data.get("input_tp"))
    return {
        "I": lufs if lufs is not None else -70.0,
        "TP": tp if tp is not None else -70.0,
        "LRA": _num(data.get("input_lra")) or 0.0,
        "thresh": _num(data.get("input_thresh")) or -70.0,
        "seconds": round(float(seconds), 3) if seconds is not None else None,
    }


def measure_segment(path: str, windows: Sequence[Window], has_dialogue: bool, duration: float,
                    window_source: str = "speech_window", has_audio: bool = True) -> Dict[str, Any]:
    """量一段：整段 I/TP，以及對白區段 I（缺窗或量不出來時退回整段 gated integrated）。"""
    rec: Dict[str, Any] = {"has_dialogue": bool(has_dialogue), "duration": round(float(duration), 3)}
    if not has_audio:
        rec.update({"role": "silent", "whole": None, "speech": None, "speech_source": None})
        return rec
    whole = measure(path)
    rec["whole"] = whole
    if not has_dialogue:
        rec.update({"role": "ambient", "speech": None, "speech_source": None})
        return rec
    rec["role"] = "dialogue"
    wins = clip_windows(windows, duration)
    speech = None
    source = None
    if wins and sum(e - s for s, e in wins) >= MIN_MEASURE_SECONDS:
        speech = measure(path, wins)
        source = window_source
        if speech["I"] <= INVALID_LUFS:
            speech = None
    if speech is None:
        if whole["I"] > INVALID_LUFS:
            speech, source = dict(whole), "energy"  # BS.1770 閘門＝略過靜音的能量偵測
        else:
            rec.update({"role": "ambient", "speech": None, "speech_source": None,
                        "note": "有台詞但量不到人聲（整段近乎無聲），當無台詞段處理"})
            return rec
    rec["speech"] = speech
    rec["speech_source"] = source
    rec["windows"] = [[round(s, 3), round(e, 3)] for s, e in wins]
    return rec


def anchor_of(records: List[Dict[str, Any]], anchor_lufs: Optional[float] = None) -> Tuple[Optional[float], Optional[str]]:
    """對白錨點：使用者指定的 LUFS，否則有對白段人聲響度的中位數（沒有對白段＝None）。"""
    if anchor_lufs is not None:
        return float(anchor_lufs), "user"
    levels = [r["speech"]["I"] for r in records if r.get("role") == "dialogue" and r.get("speech")]
    if not levels:
        return None, None
    return statistics.median(levels), "median_of_dialogue_segments"


def segment_tp_ceiling(anchor: Optional[float], target_lufs: Optional[float], film_true_peak: float,
                       default: float = DEFAULT_TP_CEILING_DBTP) -> float:
    """段層限幅門檻：預估整片 loudnorm 還會再加 (target − anchor) dB，段層就先把峰值壓在
    film_true_peak − 那個增益 − AAC 餘量，讓整片第二遍能維持 linear（純增益、不動態壓縮）。
    沒有錨點或不做整片 loudnorm 時用 default；最低到 SEGMENT_TP_FLOOR_DBTP（整片要拉升超過約 4 LU 時，
    不在段層把峰值重壓，交給整片 loudnorm 自己回退 dynamic）。"""
    if anchor is None or target_lufs is None:
        return default
    wanted = float(film_true_peak) - (float(target_lufs) - float(anchor)) - AAC_TP_MARGIN_DB
    return max(SEGMENT_TP_FLOOR_DBTP, min(default, wanted))


def plan_gains(records: List[Dict[str, Any]], anchor_lufs: Optional[float] = None,
               max_gain_db: float = DEFAULT_MAX_GAIN_DB,
               ambient_ceiling_lu: float = DEFAULT_AMBIENT_CEILING_LU,
               tp_ceiling: float = DEFAULT_TP_CEILING_DBTP,
               limiter_headroom_db: float = DEFAULT_LIMITER_HEADROOM_DB) -> Dict[str, Any]:
    """依量測結果算每段增益（就地寫進 records[i]["gain_db"／"limit"／"flags"]），回傳摘要。"""
    speech_levels = [r["speech"]["I"] for r in records if r.get("role") == "dialogue" and r.get("speech")]
    anchor, anchor_source = anchor_of(records, anchor_lufs)
    for rec in records:
        rec["gain_db"], rec["limit"], rec["flags"] = 0.0, False, []
        whole = rec.get("whole")
        if anchor is None or not whole:
            continue
        if rec.get("role") == "dialogue" and rec.get("speech"):
            gain = anchor - rec["speech"]["I"]
            if gain > max_gain_db:
                gain = max_gain_db
                rec["flags"].append("clamped_boost")
            elif gain < -max_gain_db:
                gain = -max_gain_db
                rec["flags"].append("clamped_cut")
        elif rec.get("role") == "ambient":
            ceiling = anchor + ambient_ceiling_lu
            gain = min(0.0, ceiling - whole["I"]) if whole["I"] > INVALID_LUFS else 0.0
            if gain < 0:
                rec["flags"].append("ambient_ceiling")
        else:
            continue
        predicted_tp = whole["TP"] + gain
        if predicted_tp > tp_ceiling + limiter_headroom_db:
            gain = tp_ceiling + limiter_headroom_db - whole["TP"]
            rec["flags"].append("tp_capped")
            predicted_tp = whole["TP"] + gain
        if predicted_tp > tp_ceiling:
            rec["limit"] = True
        rec["gain_db"] = round(gain, 2)
    return {"anchor_lufs": None if anchor is None else round(anchor, 2), "anchor_source": anchor_source,
            "dialogue_segments": len(speech_levels), "max_gain_db": max_gain_db,
            "ambient_ceiling_lu": ambient_ceiling_lu, "tp_ceiling_dbtp": round(tp_ceiling, 2)}


def gain_filter(gain_db: float, limit: bool, tp_ceiling: float = DEFAULT_TP_CEILING_DBTP) -> str:
    """回傳要插在段 PCM 鏈裡的濾鏡（不含前後逗號）；增益 0 且不壓限時回傳空字串。"""
    parts = []
    if abs(gain_db) >= 0.01:
        parts.append(f"volume={gain_db:.2f}dB")
    if limit:
        lim = 10 ** (tp_ceiling / 20.0)
        parts.append(f"aresample=192000,alimiter=limit={lim:.4f}:attack=1:release=50:level=disabled,aresample=48000")
    return ",".join(parts)


def spread(levels: Sequence[Optional[float]]) -> Dict[str, Optional[float]]:
    """段間落差：最大－最小，以及相鄰兩段的最大差（只算量得到的）。"""
    vals = [v for v in levels if v is not None and v > INVALID_LUFS]
    if len(vals) < 2:
        return {"max_minus_min": 0.0 if vals else None, "max_adjacent": 0.0 if vals else None}
    adj = [abs(a - b) for a, b in zip(vals, vals[1:])]
    return {"max_minus_min": round(max(vals) - min(vals), 2), "max_adjacent": round(max(adj), 2)}
