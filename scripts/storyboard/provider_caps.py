#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Provider 能力宣告與提交前校驗。

為什麼要有這一層：

FreeVideo 的幾個限制是「用過才知道」的（時長 17n+5 量子、`/jobs` 沒有 `task`
欄位、比例只驗過 16:9／9:16、音色參考只有一個槽位）。這些知識原本散在
`references/freevideo.md` 與專案 helper 裡，改一次 provider 就要重讀一次文件。

現在把它變成機器可讀的 `providers/<name>.json`，送件前先驗：

  - `source=measured` 的欄位 → 違反就是**硬錯誤**（本機真的量過）
  - `source=docs` / `assumed` → 只警告（文件說可以，但我們沒驗到底）

這與 `evidence.py` 同一套哲學：不確定的事情不要假裝確定。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_DIR = Path(__file__).resolve().parent / "providers"
DEFAULT_PROVIDER = "freevideo"


class CapabilityError(ValueError):
    """能力表本身有問題（缺檔、格式壞），不是請求有問題。"""


def load_caps(name: str = DEFAULT_PROVIDER, directory: Optional[Path] = None) -> Dict[str, Any]:
    base = Path(directory) if directory else DEFAULT_DIR
    path = base / f"{name}.json"
    if not path.is_file():
        raise CapabilityError(f"找不到 provider 能力表：{path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CapabilityError(f"{path.name} 無法解析：{exc}") from exc
    if not isinstance(data, dict):
        raise CapabilityError(f"{path.name} 根節點必須是物件")
    data["_path"] = str(path)
    return data


def _value(caps: Dict[str, Any], key: str, default: Any = None) -> Any:
    entry = caps.get(key)
    if isinstance(entry, dict):
        return entry.get("value", default)
    return default if entry is None else entry


def _source(caps: Dict[str, Any], key: str) -> str:
    entry = caps.get(key)
    return str(entry.get("source", "assumed")) if isinstance(entry, dict) else "assumed"


def validate_segment(segment: Dict[str, Any], caps: Dict[str, Any],
                     aspect: Optional[str] = None, quality: Optional[str] = None,
                     frames: Optional[int] = None,
                     reference_count: Optional[int] = None,
                     audio_count: Optional[int] = None,
                     lora_count: Optional[int] = None) -> Dict[str, List[str]]:
    """回傳 {"errors": [...], "warnings": [...]}。

    呼叫端可只給已知欄位；未給的就跳過該項檢查（不假裝驗過）。
    """
    errors: List[str] = []
    warnings: List[str] = []
    sid = segment.get("segment_id") or segment.get("id") or "?"

    def report(source: str, message: str) -> None:
        (errors if source == "measured" else warnings).append(f"[{sid}] {message}")

    if frames is not None:
        bounds = caps.get("frames") or {}
        minimum = bounds.get("min")
        maximum = bounds.get("max")
        source = str(bounds.get("source", "assumed"))
        if isinstance(minimum, int) and frames < minimum:
            report(source, f"{frames} 幀低於支援下限 {minimum}")
        if isinstance(maximum, int) and frames > maximum:
            report(source, f"{frames} 幀高於支援上限 {maximum}")

    if aspect:
        allowed = _value(caps, "aspects", []) or []
        source = _source(caps, "aspects")
        if allowed and aspect not in allowed:
            report(source, f"比例 {aspect} 不在已驗證清單 {allowed}（{caps.get('aspects', {}).get('note', '')}）")

    if reference_count is not None:
        limit = _value(caps, "max_reference_images")
        if isinstance(limit, int) and reference_count > limit:
            report(_source(caps, "max_reference_images"),
                   f"參考圖 {reference_count} 張超過上限 {limit}")

    if audio_count is not None:
        limit = _value(caps, "max_audio_references")
        if isinstance(limit, int) and audio_count > limit:
            report(_source(caps, "max_audio_references"),
                   f"音訊參考 {audio_count} 個超過上限 {limit}（此上限未經本機完整驗證）")

    if lora_count is not None:
        limit = _value(caps, "max_loras")
        if isinstance(limit, int) and lora_count > limit:
            report(_source(caps, "max_loras"), f"LoRA {lora_count} 個超過上限 {limit}")

    return {"errors": errors, "warnings": warnings}


def consistency_warnings(caps: Dict[str, Any]) -> List[str]:
    """能力表必須與 `h3_spec` 的權威常數一致；不一致就是設定漂移。"""
    try:
        import h3_spec
    except ImportError:  # pragma: no cover - 套件匯入路徑
        from . import h3_spec
    bounds = caps.get("frames") or {}
    problems: List[str] = []
    if bounds.get("min") != h3_spec.MIN_SUPPORTED_FRAMES:
        problems.append(f"capacity.frames.min={bounds.get('min')} 與 h3_spec={h3_spec.MIN_SUPPORTED_FRAMES} 不一致")
    if bounds.get("max") != h3_spec.MAX_SUPPORTED_FRAMES:
        problems.append(f"capacity.frames.max={bounds.get('max')} 與 h3_spec={h3_spec.MAX_SUPPORTED_FRAMES} 不一致")
    fps = _value(caps, "fps")
    if fps != h3_spec.FPS:
        problems.append(f"capacity.fps={fps} 與 h3_spec={h3_spec.FPS} 不一致")
    return problems


def describe(caps: Dict[str, Any]) -> str:
    bounds = caps.get("frames") or {}
    aspects = _value(caps, "aspects", []) or []
    return (
        f"{caps.get('label', caps.get('provider'))}："
        f"{bounds.get('quantum', '?')} @ {_value(caps, 'fps', '?')}fps，"
        f"{bounds.get('min')}–{bounds.get('max')} 幀，"
        f"比例 {', '.join(aspects) or '未宣告'}"
    )
