#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Layer 2 正規化層：把「同一件事的多種寫法」收斂成一種，並在缺資料時報錯。

為什麼要這一層（來自《噩盡島》第一章 11 類實際缺陷）：

  - 中央審閱器漏讀合法的 `camera_optics.composition_start` → 誤報缺構圖
  - `validate_structure` 找不到預設 schema 時**靜默略過**
  - 發話窗口同時存在「鏡內秒」與「段內秒」，彙整後 18 處越界
  - 服裝有時是 id 清單、有時是物件清單，編譯器只好猜
  - 參考圖 `reference_view: panel` 沒寫 `panel_label_en` 也能過

設計原則：
  1. 只做「位置與型別的收斂」，不改語意、不補內容。
  2. 缺必要資料一律丟 `NormalizationError`（strict）或記 warning（寬鬆），
     **絕不靜默略過**——那是上一輪最大的教訓。
  3. 所有被改寫的位置都記錄在 `_normalization.aliases_applied`，可回溯。
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

CANONICAL_TOP_KEYS = (
    "segment_id", "scene_id", "metadata", "style_lock", "shots",
    "reference_images", "segment_end_state",
)

# 同義欄位 → 正規位置。key 是「扁平化路徑」，value 是 canonical 路徑。
ALIASES: Dict[str, str] = {
    "composition": "camera_optics.composition_start",
    "camera_optics.composition": "camera_optics.composition_start",
    "camera_composition": "camera_optics.composition_start",
    "camera_optics.composition_start": "camera_optics.composition_start",
    "characters": "character_ids",
    "character_ids": "character_ids",
    "costume": "wardrobe",
    "wardrobe": "wardrobe",
    "props": "props",
    "dialogue": "dialogue_and_audio",
}

# 台詞窗口的時間基準。專案內實際出現過兩種寫法（`segment_seconds` 與
# `seconds_segment_relative`），舊檔不可因為命名不同而被判非法。
# 刻意只留三種可驗證語意；`absolute`／`auto` 之類模糊寫法一律報錯，
# 讓問題在入口就現形，而不是三個月後變成沒人敢刪的傾倒場。
SPEECH_UNIT_ALIASES: Dict[str, str] = {
    "segment_seconds": "segment_seconds",
    "seconds_segment_relative": "segment_seconds",
    "shot_seconds": "shot_seconds",
}
TIME_TOLERANCE = 1e-3


class NormalizationError(ValueError):
    """資料不足以進下一步——呼叫端應停下並修正來源，而不是繼續。"""


def _apply_alias(target: Dict[str, Any], flat_path: str, value: Any) -> None:
    """把 value 寫進 canonical 路徑（camera_optics.xxx 需建子物件）。"""
    if "." in flat_path:
        head, tail = flat_path.split(".", 1)
        node = target.setdefault(head, {})
        if not isinstance(node, dict):
            raise NormalizationError(f"{head} 必須是物件，實際是 {type(node).__name__}")
        node[tail] = value
    else:
        target[flat_path] = value


def _get_alias(shot: Dict[str, Any], flat_path: str) -> Tuple[bool, Any]:
    if "." in flat_path:
        head, tail = flat_path.split(".", 1)
        node = shot.get(head)
        if isinstance(node, dict) and tail in node:
            return True, node[tail]
        return False, None
    if flat_path in shot:
        return True, shot[flat_path]
    return False, None


def _id_set(value: Any) -> Optional[set]:
    """把 str / list[str] / list[{id}] 轉成可比對的 id 集合；無法解析回 None。"""
    if isinstance(value, str):
        return {value}
    if isinstance(value, list):
        out = set()
        for item in value:
            if isinstance(item, str):
                out.add(item)
            elif isinstance(item, dict) and item.get("id"):
                out.add(str(item["id"]))
            else:
                return None
        return out
    return None


def normalize_shot(shot: Dict[str, Any], index: int, warnings: List[str], notes: List[str],
                   aliases_applied: List[str], strict: bool = True,
                   strict_aliases: bool = True) -> Dict[str, Any]:
    # 深拷貝：normalize 不得就地改寫呼叫端的巢狀物件（window/audio/camera_optics）。
    shot = copy.deepcopy(shot)
    sid = shot.get("shot_id") or shot.get("id")
    if not sid:
        raise NormalizationError(f"shot[{index}] 缺少 shot_id")
    shot["shot_id"] = str(sid)

    # 1) 同義欄位收斂（先收斂再驗證，避免「合法欄位被誤報缺」）
    #    但若新舊兩欄並存且值不同，不可靜默挑一邊——那是最難查的一種錯。
    for old_key, new_key in (("characters", "character_ids"), ("costume", "wardrobe")):
        if old_key in shot and new_key in shot:
            old_ids, new_ids = _id_set(shot[old_key]), _id_set(shot[new_key])
            if old_ids is not None and new_ids is not None and old_ids != new_ids:
                if not old_ids or not new_ids:
                    # 一方是空清單（常見：canonical 被刻意清空）→ 以 canonical 為準，記 note。
                    notes.append(
                        f"{sid} {old_key} 與 {new_key} 不一致（一方為空），已採 {new_key} 並忽略 {old_key}"
                    )
                else:
                    message = (
                        f"{sid} {old_key} 與 {new_key} 並存且值不同"
                        f"（{sorted(old_ids)} vs {sorted(new_ids)}）"
                    )
                    if strict_aliases:
                        raise NormalizationError(message + "；請只保留一個")
                    notes.append(message + f"；已採 {new_key}，多出的請確認是否刻意")
    for flat, canonical in ALIASES.items():
        present, value = _get_alias(shot, flat)
        if not present or flat == canonical:
            continue
        if "." in canonical:
            _apply_alias(shot, canonical, value)
        elif canonical not in shot:
            shot[canonical] = value
        if "." not in flat and flat != canonical:
            shot.pop(flat, None)
        aliases_applied.append(f"{sid}: {flat} → {canonical}")

    # 2) 時間軸：至少要有 start/end 或 duration，且三者一致
    start, end, duration = shot.get("start_time"), shot.get("end_time"), shot.get("duration")
    if start is None and end is None and duration is None:
        raise NormalizationError(f"{sid} 沒有時間軸（start_time/end_time/duration 全缺）")
    if start is not None and end is not None:
        start, end = float(start), float(end)
        if end <= start:
            raise NormalizationError(f"{sid} end_time({end}) 必須大於 start_time({start})")
        derived = round(end - start, 6)
        if duration is not None and abs(float(duration) - derived) > TIME_TOLERANCE:
            message = f"{sid} duration({duration}) 與 end-start({derived}) 不一致"
            if strict:
                raise NormalizationError(message)
            warnings.append(message)
        shot["start_time"], shot["end_time"], shot["duration"] = start, end, derived
    elif duration is not None and start is not None:
        shot["end_time"] = round(float(start) + float(duration), 6)
        shot["start_time"], shot["duration"] = float(start), float(duration)
    else:
        raise NormalizationError(f"{sid} 時間軸不完整（需要 start+end 或 start+duration）")

    # 3) 台詞窗口統一到「段內秒」
    audio = shot.get("dialogue_and_audio")
    if isinstance(audio, dict):
        window = audio.get("speech_window")
        if isinstance(window, dict):
            window = dict(window)
            unit_raw = str(window.get("unit") or "segment_seconds")
            unit = SPEECH_UNIT_ALIASES.get(unit_raw)
            if unit is None:
                raise NormalizationError(
                    f"{sid} speech_window.unit 未知：{unit_raw}"
                    f"（可用：{', '.join(sorted(SPEECH_UNIT_ALIASES))}）"
                )
            try:
                w_start, w_end = float(window.get("start")), float(window.get("end"))
            except (TypeError, ValueError):
                raise NormalizationError(f"{sid} speech_window 的 start/end 必須是數字")
            if unit == "shot_seconds":
                w_start += shot["start_time"]
                w_end += shot["start_time"]
                aliases_applied.append(f"{sid}: speech_window(shot_seconds) → segment_seconds")
            if w_end <= w_start:
                raise NormalizationError(f"{sid} speech_window 結束({w_end}) 必須大於開始({w_start})")
            if w_start < shot["start_time"] - TIME_TOLERANCE or w_end > shot["end_time"] + TIME_TOLERANCE:
                message = (f"{sid} speech_window[{w_start:.3f},{w_end:.3f}] 超出鏡頭 "
                           f"[{shot['start_time']:.3f},{shot['end_time']:.3f}]")
                if strict:
                    raise NormalizationError(message)
                warnings.append(message)
            window["start"], window["end"], window["unit"] = round(w_start, 6), round(w_end, 6), "segment_seconds"
            audio["speech_window"] = window

    # 4) 服裝／道具／角色：一律收斂成 id 清單
    for key in ("wardrobe", "character_ids"):
        if key not in shot:
            continue
        value = shot[key]
        if isinstance(value, str):
            shot[key] = [value]
        elif isinstance(value, list):
            ids = []
            for item in value:
                if isinstance(item, str):
                    ids.append(item)
                elif isinstance(item, dict) and item.get("id"):
                    ids.append(str(item["id"]))
                else:
                    raise NormalizationError(f"{sid} {key} 內含無法識別的項目：{item!r}")
            shot[key] = ids
        elif isinstance(value, dict):
            raise NormalizationError(f"{sid} {key} 不可以是物件（應為 id 清單或 id 字串）")
        else:
            raise NormalizationError(f"{sid} {key} 型別不支援：{type(value).__name__}")

    if "props" in shot:
        if isinstance(shot["props"], dict):
            raise NormalizationError(f"{sid} props 不可以是物件（應為 id 清單）")
        if isinstance(shot["props"], list):
            normalized = []
            for item in shot["props"]:
                if isinstance(item, str):
                    normalized.append({"id": item})
                elif isinstance(item, dict) and item.get("id"):
                    normalized.append(dict(item))
                else:
                    raise NormalizationError(f"{sid} props 內含無法識別的項目：{item!r}")
            shot["props"] = normalized

    return shot


def normalize_layer2(data: Dict[str, Any], strict: bool = True,
                     strict_aliases: bool = True) -> Dict[str, Any]:
    """回傳正規化後的副本；所有改寫記在 `_normalization`。"""
    if not isinstance(data, dict):
        raise NormalizationError("Layer 2 根節點必須是物件")
    data = dict(data)
    warnings: List[str] = []
    notes: List[str] = []
    aliases_applied: List[str] = []

    seg_id = data.get("segment_id") or data.get("scene_id")
    if not seg_id:
        raise NormalizationError("Layer 2 缺少 segment_id")
    data["segment_id"] = str(seg_id)

    metadata = data.get("metadata")
    if metadata is None:
        data["metadata"] = {}
    elif not isinstance(metadata, dict):
        raise NormalizationError("metadata 必須是物件")
    target = data["metadata"].get("target_duration_sec")
    if target is None:
        raise NormalizationError(f"{data['segment_id']} metadata 缺少 target_duration_sec")
    if float(target) <= 0:
        raise NormalizationError(f"{data['segment_id']} target_duration_sec 必須 > 0")

    shots = data.get("shots")
    if not isinstance(shots, list) or not shots:
        raise NormalizationError(f"{data['segment_id']} 缺少 shots")
    seen: set = set()
    normalized_shots = []
    for index, shot in enumerate(shots):
        if not isinstance(shot, dict):
            raise NormalizationError(f"{data['segment_id']} shots[{index}] 必須是物件")
        item = normalize_shot(shot, index, warnings, notes, aliases_applied,
                              strict=strict, strict_aliases=strict_aliases)
        key = item["shot_id"].casefold()
        if key in seen:
            raise NormalizationError(f"{data['segment_id']} shot_id 重複：{item['shot_id']}")
        seen.add(key)
        normalized_shots.append(item)
    data["shots"] = normalized_shots

    # 全段時間軸連續性：只驗「段內每一鏡」是不夠的（上一輪的 18 處越界就是這樣漏掉的）
    cursor = 0.0
    for shot in normalized_shots:
        if abs(shot["start_time"] - cursor) > TIME_TOLERANCE:
            kind = "空隙" if shot["start_time"] > cursor else "重疊"
            warnings.append(f"{shot['shot_id']} 時間軸{kind}："
                            f"預期 {cursor:.3f}s，實際 {shot['start_time']:.3f}s（shot 級）")
        cursor = shot["end_time"]
    if abs(cursor - float(target)) > 0.05:
        warnings.append(f"分段時間軸總長 {cursor:.3f}s 與 target_duration_sec {float(target):.3f}s 不一致（shot 級）")

    # 參考圖：整板查表模式必須寫出格位
    refs = data.get("reference_images") or []
    if not isinstance(refs, list):
        raise NormalizationError("reference_images 必須是陣列")
    for index, ref in enumerate(refs):
        if not isinstance(ref, dict):
            continue
        if str(ref.get("reference_view") or "").lower() == "panel" and not ref.get("panel_label_en"):
            raise NormalizationError(
                f"reference_images[{index}] 宣告 reference_view=panel 但沒有 panel_label_en"
            )

    data["_normalization"] = {
        "warnings": warnings,
        "notes": notes,
        "aliases_applied": aliases_applied,
        "strict": strict,
        "strict_aliases": strict_aliases,
    }
    return data


def load_layer2(path: Path, strict: bool = True,
                strict_aliases: bool = True) -> Dict[str, Any]:
    """讀檔 → 正規化。schema 或格式問題一律報錯，不靜默略過。"""
    path = Path(path)
    if not path.is_file():
        raise NormalizationError(f"Layer 2 檔案不存在：{path}")
    try:
        raw = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise NormalizationError(f"無法讀取 {path}：{exc}") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise NormalizationError(f"{path.name} 不是合法 JSON：{exc}") from exc
    return normalize_layer2(data, strict=strict, strict_aliases=strict_aliases)
