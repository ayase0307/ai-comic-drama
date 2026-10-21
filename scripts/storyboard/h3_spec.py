#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MiniMax H3 / FreeVideo 幀量子規格：單一真值來源。

為什麼要有這支檔（2026-10-19 實測事故）：

    FreeVideo 會把請求秒數「向上」取到最近的 17n+5 影格量子。
    把 effective_duration_sec 四捨五入到小數 3 位再送（277/24 → 11.542），
    服務端算 11.542 * 24 = 277.008 → 往上 278 → 294 幀（12.25s），
    觀眾看到的是「時長漂移」，而送件紀錄看起來完全正常。

正解：送 frames / 24 的精確浮點值，並回讀服務端回報的 frames 做斷言。

所有需要「秒數 ↔ 影格」換算的模組（compile / audit / submit / verify）
都應 import 這裡，不要再各自複製一份 17n+5 公式。
"""
from __future__ import annotations

import math
from typing import Any, Dict

# 影片基準
FPS = 24

# 量子：frames = 17n + 5（n >= 1），也就是 22, 39, 56, ... 362
FRAME_QUANTUM_STEP = 17
FRAME_QUANTUM_OFFSET = 5
MIN_QUANTUM_FRAMES = FRAME_QUANTUM_STEP + FRAME_QUANTUM_OFFSET  # 22，n=1

# 官方訓練／支援區間（SlavaSexton 考證：length mod 17 == 5，區間 124–362）
MIN_SUPPORTED_FRAMES = 124
MAX_SUPPORTED_FRAMES = 362

ROUNDING_MODES = ("floor", "round", "ceil")


def _check_rounding(rounding: str) -> str:
    if rounding not in ROUNDING_MODES:
        raise ValueError(f"unknown rounding mode: {rounding!r} (expected one of {ROUNDING_MODES})")
    return rounding


def is_quantum(frames: int) -> bool:
    """是否為合法的 17n+5 影格數（n >= 1，最小 22 幀）。"""
    frames = int(frames)
    if frames < MIN_QUANTUM_FRAMES:
        return False
    return (frames - FRAME_QUANTUM_OFFSET) % FRAME_QUANTUM_STEP == 0


def _require_non_negative(frames: int, name: str) -> int:
    frames = int(frames)
    if frames < 0:
        raise ValueError(f"{name} 不接受負數：{frames}")
    return frames


def nearest_quantum(frames: float) -> int:
    """把一個「影格數」吸附到最近的 17n+5（同距時向上）。

    給 fallback 用：舊 segments 只留下 round(effective_seconds, 3)，
    直接換算回影格會落在量子旁邊（例如 6.583*24 = 157.992），
    必須吸附，不能 floor——floor 會整整少一個量子（158 → 141）。
    """
    value = float(frames)
    if not (value == value) or value in (float("inf"), float("-inf")):
        raise ValueError(f"nearest_quantum 收到非有限值：{frames!r}")
    if value < 0:
        raise ValueError(f"nearest_quantum 不接受負數：{frames}")
    rounded = int(round(value))
    if is_quantum(rounded):
        return rounded
    down = quantize_down(rounded)
    up = quantize_up(rounded) if rounded > FRAME_QUANTUM_OFFSET else MIN_QUANTUM_FRAMES
    if (rounded - down) < (up - rounded):
        return down
    return up


def quantize_up(frames: int) -> int:
    """向上取到最近的 17n+5（已是量子則原樣回傳）。"""
    frames = _require_non_negative(frames, "quantize_up")
    if frames <= FRAME_QUANTUM_OFFSET:
        return MIN_QUANTUM_FRAMES
    remainder = (frames - FRAME_QUANTUM_OFFSET) % FRAME_QUANTUM_STEP
    if remainder == 0:
        return frames
    return frames + (FRAME_QUANTUM_STEP - remainder)


def quantize_down(frames: int) -> int:
    """向下取到最近的 17n+5（最小 22 幀，即 n=1）。"""
    frames = _require_non_negative(frames, "quantize_down")
    if frames <= MIN_QUANTUM_FRAMES:
        return MIN_QUANTUM_FRAMES
    return FRAME_QUANTUM_OFFSET + ((frames - FRAME_QUANTUM_OFFSET) // FRAME_QUANTUM_STEP) * FRAME_QUANTUM_STEP


def frames_for(seconds: float, rounding: str = "floor") -> int:
    """把目標秒數換算成 17n+5 影格數。

    rounding：
      - 'floor'（預設，保守）：7.0s → 158 幀（6.58s），保留的台詞窗可能不足
      - 'round'：7.0s → 175 幀（7.29s）
      - 'ceil'：向上，含台詞的段落應採用，避免台詞被截
    """
    _check_rounding(rounding)
    seconds = float(seconds)
    if seconds <= 0:
        raise ValueError("seconds must be > 0")
    raw_steps = (seconds * FPS - FRAME_QUANTUM_OFFSET) / FRAME_QUANTUM_STEP
    if rounding == "ceil":
        steps = max(1, math.ceil(raw_steps))
    elif rounding == "round":
        steps = max(1, round(raw_steps))
    else:
        steps = max(1, int(math.floor(raw_steps)))
    return FRAME_QUANTUM_STEP * steps + FRAME_QUANTUM_OFFSET


def seconds_for_frames(frames: int) -> float:
    """影格數 → 精確秒數（送 API 用這個，不要用 round(..., 3)）。"""
    frames = int(frames)
    if frames <= 0:
        raise ValueError("frames must be > 0")
    return frames / float(FPS)


def effective_seconds(seconds: float, rounding: str = "floor") -> float:
    """量化後的真實有效秒數 D = frames_for(s) / FPS。"""
    return seconds_for_frames(frames_for(seconds, rounding=rounding))


def wire_seconds(frames: int) -> float:
    """送 FreeVideo 的秒數。

    直接送 frames / FPS 的精確值即可：實測 n/24*24 在 IEEE754 下會回到整數
    （277/24*24 == 277.0），所以服務端 ceil 之後正好落在同一個量子。
    **絕對不要**先 round 到 3 位小數再送——那正是時長漂移的成因。
    """
    return seconds_for_frames(frames)


def in_supported_range(frames: int) -> bool:
    return MIN_SUPPORTED_FRAMES <= int(frames) <= MAX_SUPPORTED_FRAMES


def plan(seconds: float, rounding: str = "floor") -> Dict[str, Any]:
    """一次算出「請求秒數 → 影格 → 實際秒數 → 誤差」的完整決策紀錄。

    這是給編譯器寫進 metadata、給 QA 報告引用的最小單位。
    """
    frames = frames_for(seconds, rounding=rounding)
    actual = seconds_for_frames(frames)
    return {
        "requested_seconds": round(float(seconds), 6),
        "rounding_mode": rounding,
        "frames": frames,
        "effective_seconds": actual,
        "drift_seconds": round(actual - float(seconds), 6),
        "is_quantum": is_quantum(frames),
        "in_supported_range": in_supported_range(frames),
    }


def validate_plan(seconds: float, rounding: str = "floor") -> list:
    """回傳人可讀的問題清單（空清單＝沒問題），給 CLI 直接印。"""
    problems = []
    info = plan(seconds, rounding=rounding)
    if info["drift_seconds"] < -1e-9:
        problems.append(
            f"量化後比要求短 {-info['drift_seconds']:.3f}s（{info['frames']} 幀）；"
            "含台詞的段落應改用 rounding='ceil'"
        )
    if not info["in_supported_range"]:
        problems.append(
            f"{info['frames']} 幀超出支援區間 {MIN_SUPPORTED_FRAMES}–{MAX_SUPPORTED_FRAMES}；"
            "請改分段長度或拆段"
        )
    return problems
