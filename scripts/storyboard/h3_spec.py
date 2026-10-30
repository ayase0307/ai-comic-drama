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

# 秒數換幀時的吸附容差（幀）：0.05 幀 ≈ 2 ms，遠小於 1 幀，足以吸收 3–4 位小數的手寫秒數誤差（SB-2）。
FRAME_SNAP_TOL = 0.05

# 鏡長下限（v118 規則衝突 #1／E4）：
#   MIN_SHOT_SEC＝#116 說話窗口下限（字數÷角色語速＋0.3 s，最低 1.2 s），低於它是硬錯誤；
#   SHOT_SOFT_MIN_SEC＝上游 H3 指南「shot ≥ 2 s」（切點誤差約 0.12 s，inferred），
#   1.2–2.0 s 的鏡只出提醒、不擋（未在 H3 實測）。首切點、相鄰切點、末切點留白都用同一組數字。
MIN_SHOT_SEC = 1.2
SHOT_SOFT_MIN_SEC = 2.0

# 伺服器端「秒數 → 影格」的取整方向依 provider 而定（PR-R1，video_backend）：
#   - freevideo（Ref2VA，VDN-H3）：往上取到 17n+5（2026-10-19 實測 11.542s → 294 幀）。
#   - remix（REMIX Studio＋RefMod 角色包，Singularity ref2va V1.3 int8）：往下取
#     （measured：5.5s → 124 幀＝5.17s，三人測試 job 1026155645-b9e8）。
#     秒數 2–10.125s 為家機指南（docs）；frames 區間 56–243 是「≥2s 的最小量子」到
#     10.125s×24=243 換算而來（推定），2s 往下取會得 39 幀，伺服器是否接受未驗證。
# 編譯器送的是 frames/24 的精確值（IEEE754 下 n/24*24 == n，對 22–362 全部量子成立），
# 所以兩種取整方向都會落在同一個量子；取整方向只影響「手寫秒數」時的預估。
DEFAULT_PROVIDER = "freevideo"
PROVIDER_FRAME_SPECS: Dict[str, Dict[str, Any]] = {
    "freevideo": {"min_frames": MIN_SUPPORTED_FRAMES, "max_frames": MAX_SUPPORTED_FRAMES,
                  "server_rounding": "ceil", "source": "measured"},
    "remix": {"min_frames": 56, "max_frames": 243, "server_rounding": "floor", "source": "measured"},
}


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
    raw_frames = seconds * FPS
    # SB-2：手寫秒數常是幀數÷24 的 4 位小數（107 幀寫 4.4583 s → 106.9992 幀），直接 floor 會整整少一個
    # 量子（90 幀）；離整數幀不到 FRAME_SNAP_TOL 就先吸附到該整數幀再取整（ceil 方向同理，107.0008 不會跳到 124）。
    nearest = round(raw_frames)
    if abs(raw_frames - nearest) < FRAME_SNAP_TOL:
        raw_frames = float(nearest)
    raw_steps = (raw_frames - FRAME_QUANTUM_OFFSET) / FRAME_QUANTUM_STEP
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


def provider_spec(provider: str = DEFAULT_PROVIDER) -> Dict[str, Any]:
    """provider 的影格規格；未知 provider 丟 ValueError（不假裝知道）。"""
    key = str(provider or DEFAULT_PROVIDER).strip().lower()
    if key not in PROVIDER_FRAME_SPECS:
        raise ValueError(f"unknown provider: {provider!r} (expected one of {tuple(PROVIDER_FRAME_SPECS)})")
    return PROVIDER_FRAME_SPECS[key]


def server_rounding(provider: str = DEFAULT_PROVIDER) -> str:
    """伺服器把請求秒數取到 17n+5 的方向：freevideo=ceil、remix=floor。"""
    return provider_spec(provider)["server_rounding"]


def server_frames(seconds: float, provider: str = DEFAULT_PROVIDER) -> int:
    """預估伺服器收到 `seconds` 後實際產出的影格數（依 provider 往上或往下取量子）。

    容許 1e-6 的浮點誤差，讓 wire_seconds(n) 送出的精確值永遠回到 n。
    """
    seconds = float(seconds)
    if not math.isfinite(seconds) or seconds <= 0:
        raise ValueError("seconds must be a finite number > 0")
    raw = seconds * FPS
    if server_rounding(provider) == "floor":
        return quantize_down(int(math.floor(raw + 1e-6)))
    return quantize_up(int(math.ceil(raw - 1e-6)))


def in_supported_range(frames: int, provider: str = DEFAULT_PROVIDER) -> bool:
    spec = provider_spec(provider)
    return spec["min_frames"] <= int(frames) <= spec["max_frames"]


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
