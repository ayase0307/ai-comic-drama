#!/usr/bin/env python3
"""handoff JSON 轉 Layer 2 分鏡骨架（已全面升級對齊《噩盡島》實戰定案）。

用法：
    python scripts/storyboard/handoff_to_skeleton.py <handoff.json> --out-dir <目錄> [--scene EP01-S01] [--max-segment-sec 10.0] [--max-shots 3] [--force]

每個場景輸出 <目錄>/layer2-<segment_id>.json，結構符合
references/storyboard/templates/layer2-storyboard.schema.json。

這是「骨架」，供導演細化，不是成品分鏡：
- 每句對白、每個動作拍各一個鏡頭（預設每段 2–3 節拍/鏡，時長 7–10 秒），對白逐字複製，絕不丟棄。
- 鏡頭秒數由文字推算：對白 = 字數 ÷ 4.0（至少 2.5 秒，確保窗口足夠），動作拍預設 2.5 秒。
- 單鏡估時超過 10~15 秒（H3 單鏡上限）的對白，依標點切成多鏡（找不到標點就切中間字），串接後與原文相同。
- 場景依序切段，每段預設 ≤ 3 鏡且估時 ≤ 10 秒；段名 <scene_id>-a…-z、-aa、-ab…，跨段預設採 INDEPENDENT_REF2VA 獨立分段。
- 動作階段預填【施力點 ➔ 傳導路徑 ➔ 受擊與環境反饋】三要素模板，連戲預填四大錨點（lighting/axis/blocking/texture）。
- 鏡頭語言、動作階段、光線鎖、風格鎖等標 TODO，導演須依情節重寫；
  validate_storyboard.py 與 layer2_to_table.py --check 遇到 TODO 一律失敗。
- 動作拍的順序為先動作後對白（handoff 未提供兩者的先後關係）。
- 已存在的檔案不會被覆蓋，除非加 --force。
只使用標準庫。
"""
from __future__ import annotations

import argparse
import json
import os
import hashlib
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from speech_utils import count_speech_chars  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
LAYER2_SCHEMA = ROOT / "references/storyboard/templates/layer2-storyboard.schema.json"
HANDOFF_SCHEMA = ROOT / "references/adapt/templates/handoff.schema.json"

DEFAULT_MAX_SHOTS = 3
DEFAULT_MAX_SEGMENT_SEC = 10.0
CHARS_PER_SEC = 4.5
MIN_DIALOGUE_SEC = 1.2  # v2：實際窗口＝字數/CHARS_PER_SEC＋DIALOGUE_PAD_SEC，下限 1.2
DIALOGUE_PAD_SEC = 0.3
MAX_SHOT_SEC = 15.0  # H3 單鏡上限
ACTION_SHOT_SEC = 2.5
ASPECT_MAP = {"9:16": "9:16", "16:9": "16:9", "other": "16:9"}
TODO = "TODO"

_TYPE_MAP = {"string": str, "object": dict, "array": list, "null": type(None)}


class DialogueOverflowError(ValueError):
    """單句對白估時超過單段上限，無法切段而又不丟台詞。"""


def warn(msg: str) -> None:
    print(f"[警告] {msg}", file=sys.stderr)


def load_schema(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _type_ok(data: Any, expected: Any) -> bool:
    names = expected if isinstance(expected, list) else [expected]
    for name in names:
        if name == "boolean" and isinstance(data, bool):
            return True
        if name == "number" and isinstance(data, (int, float)) and not isinstance(data, bool):
            return True
        if name == "integer" and isinstance(data, int) and not isinstance(data, bool):
            return True
        if name in _TYPE_MAP and isinstance(data, _TYPE_MAP[name]) and not isinstance(data, bool):
            return True
    return False


def check_schema(data: Any, schema: dict, path: str = "$") -> list[str]:
    """極簡 JSON Schema 檢查（不依賴 jsonschema）：type、required、properties、items、enum、
    pattern、minimum/maximum、minItems/maxItems。回傳錯誤訊息清單，空清單代表通過。"""
    if "type" in schema and not _type_ok(data, schema["type"]):
        return [f"{path}: 型別應為 {schema['type']}，實際為 {type(data).__name__}"]
    errors: list[str] = []
    if "enum" in schema and data not in schema["enum"]:
        errors.append(f"{path}: 值 {data!r} 不在允許清單 {schema['enum']} 內")
    if isinstance(data, str) and "pattern" in schema and not re.search(schema["pattern"], data):
        errors.append(f"{path}: 值 {data!r} 不符合格式 {schema['pattern']}")
    if isinstance(data, (int, float)) and not isinstance(data, bool):
        if "minimum" in schema and data < schema["minimum"]:
            errors.append(f"{path}: {data} 小於最小值 {schema['minimum']}")
        if "maximum" in schema and data > schema["maximum"]:
            errors.append(f"{path}: {data} 大於最大值 {schema['maximum']}")
    if isinstance(data, list):
        if "minItems" in schema and len(data) < schema["minItems"]:
            errors.append(f"{path}: 項目數 {len(data)} 少於 {schema['minItems']}")
        if "maxItems" in schema and len(data) > schema["maxItems"]:
            errors.append(f"{path}: 項目數 {len(data)} 超過 {schema['maxItems']}")
        for i, item in enumerate(data):
            errors += check_schema(item, schema.get("items", {}), f"{path}[{i}]")
    if isinstance(data, dict):
        for key in schema.get("required", []):
            if key not in data:
                errors.append(f"{path}: 缺少必要欄位 `{key}`")
        for key, sub in schema.get("properties", {}).items():
            if key in data:
                errors += check_schema(data[key], sub, f"{path}.{key}")
    return errors


def check_layer2(data: Any) -> list[str]:
    """對照 Layer 2 schema 做結構檢查，供 layer2_to_table.py 共用。"""
    return check_schema(data, load_schema(LAYER2_SCHEMA))


def find_todo(data: Any, path: str = "$") -> list[str]:
    """回傳所有含 TODO 的字串值（區分大小寫），訊息帶 JSON 路徑。驗證器與 --check 共用。"""
    if isinstance(data, str):
        if TODO in data:
            return [f"[TODO 未完成] {path}：{data!r} 仍含 TODO，導演須精修後才能通過"]
        return []
    if isinstance(data, list):
        return [e for i, item in enumerate(data) for e in find_todo(item, f"{path}[{i}]")]
    if isinstance(data, dict):
        return [e for k, v in data.items() for e in find_todo(v, f"{path}.{k}")]
    return []


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def make_id(prefix: str, raw: str, index: int) -> str:
    """把名稱轉成 PREFIX-slug；已是 PREFIX- 格式就原樣保留；無法轉 ASCII（如純中文）時用序號。"""
    if re.fullmatch(rf"{prefix}-[a-z0-9-]+", raw):
        return raw
    slug = slugify(raw)
    if not slug:  # 純中文名：用名稱雜湊，穩定且不會變 item1／item2（#37）
        slug = "x" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:6]
    return f"{prefix}-{slug}"


def segment_suffix(index: int) -> str:
    """0→a … 25→z、26→aa、27→ab …（bijective base-26，無上限、不會溢出字母表）。"""
    letters, n = "", index + 1
    while n:
        n, rem = divmod(n - 1, 26)
        letters = chr(ord("a") + rem) + letters
    return letters


def segment_ids(scene_id: str, count: int) -> list[str]:
    if count == 1:
        return [scene_id]
    return [f"{scene_id}-{segment_suffix(i)}" for i in range(count)]


def segment_sort_key(segment_id: str) -> tuple:
    """段落排序鍵：先比場景前綴，再比段尾長度與字母（aa 排在 z 之後）。"""
    m = re.fullmatch(r"(.*)-([a-z]+)", segment_id)
    return (m.group(1), len(m.group(2)), m.group(2)) if m else (segment_id, 0, "")


def dialogue_seconds(text: str) -> float:
    """對白鏡秒數 = 字數 ÷ 4.5 ＋ 0.3 秒，至少 1.2 秒（v2）。"""
    return round(max(MIN_DIALOGUE_SEC, count_speech_chars(text) / CHARS_PER_SEC + DIALOGUE_PAD_SEC), 2)


def split_long_line(text: str, max_sec: float = MAX_SHOT_SEC) -> list[str]:
    """估時超過 max_sec 的對白切成多鏡：優先切在最接近中間的標點後（兩側都要有字），否則切中間字。
    遞迴直到每段 ≤ 上限；串接結果與原文逐字相同。"""
    if dialogue_seconds(text) <= max_sec or len(text) < 2:
        return [text]
    mid = len(text) // 2
    cuts = [
        i + 1 for i, ch in enumerate(text[:-1])
        if not ch.isspace() and count_speech_chars(ch) == 0
        and count_speech_chars(text[: i + 1]) > 0 and count_speech_chars(text[i + 1:]) > 0
    ]
    cut = min(cuts, key=lambda c: abs(c - mid)) if cuts else mid
    return split_long_line(text[:cut], max_sec=max_sec) + split_long_line(text[cut:], max_sec=max_sec)


MERGE_BEAT_TARGET_SEC = 5.0


def merge_beats(beats: list[str]) -> list[dict]:
    """相鄰的 △ 動作合成同一拍（累積到 5 秒為止），避免「一行 △＝一鏡 2.5 秒」把同一拍拆碎（#37）。"""
    items: list[dict] = []
    for text in beats:
        if items and items[-1]["duration"] + ACTION_SHOT_SEC <= MERGE_BEAT_TARGET_SEC:
            items[-1]["text"] += "；" + text
            items[-1]["duration"] = round(items[-1]["duration"] + ACTION_SHOT_SEC, 2)
        else:
            items.append({"kind": "beat", "text": text, "duration": ACTION_SHOT_SEC})
    return items


def build_items(scene: dict, max_sec: float = DEFAULT_MAX_SEGMENT_SEC) -> list[dict]:
    """先動作拍、後對白（對白為必保留項目，動作拍是段落的填充物）。超長對白會切成多個對白鏡。"""
    beats = scene.get("action_beats") or scene.get("storyboard_handoff", {}).get("required_visual_beats") or []
    items = merge_beats(beats)
    split_threshold = min(max_sec, MAX_SHOT_SEC)
    for line in scene.get("dialogue", []):
        speech_len = count_speech_chars(line["text"])
        if speech_len > 15:
            warn(f"{scene.get('scene_id')} 單句台詞超過 15 字（{speech_len} 字）：「{line['text']}」，建議拆短以符合 H3 實戰台詞預算")
        for piece in split_long_line(line["text"], max_sec=split_threshold):
            items.append({
                "kind": "dialogue",
                "speaker": line["speaker"],
                "text": piece,
                "note": line.get("delivery_note", ""),
                "audio_type": line.get("audio_type", "dialogue"),
                "duration": dialogue_seconds(piece),
            })
    return items


def pack_items(items: list[dict], scene_id: str,
               max_shots: int = DEFAULT_MAX_SHOTS,
               max_segment_sec: float = DEFAULT_MAX_SEGMENT_SEC) -> list[list[dict]]:
    """依序裝段：每段 ≤ max_shots 鏡且估時 ≤ max_segment_sec。只換段，不丟任何項目。"""
    segments: list[list[dict]] = []
    current: list[dict] = []
    current_sec = 0.0
    for item in items:
        if item["duration"] > MAX_SHOT_SEC:
            raise DialogueOverflowError(
                f"{scene_id} 有一句台詞估時 {item['duration']} 秒，超過 H3 單鏡 {MAX_SHOT_SEC:.0f} 秒上限，"
                f"無法切段又不丟台詞：{item['text']!r}。請拆句後重跑。"
            )
        # 若當前段已滿 max_shots，或加入後超過 max_segment_sec（且當前段已有鏡頭），則切段
        if current and (len(current) >= max_shots or current_sec + item["duration"] > max_segment_sec):
            segments.append(current)
            current, current_sec = [], 0.0
        current.append(item)
        current_sec += item["duration"]
    if current:
        segments.append(current)
    return segments


def scene_chunks(scene: dict, max_shots: int = DEFAULT_MAX_SHOTS,
                 max_segment_sec: float = DEFAULT_MAX_SEGMENT_SEC) -> list[list[dict]]:
    """場景切段（純計算，不發警告，供計算銜接關係時重複呼叫）。"""
    placeholder = {"kind": "beat", "text": f"{TODO}：補動作", "duration": ACTION_SHOT_SEC}
    items = build_items(scene, max_sec=max_segment_sec) or [placeholder]
    return pack_items(items, scene["scene_id"], max_shots=max_shots, max_segment_sec=max_segment_sec)


def segment_target(chunk: list[dict]) -> float:
    return max(1.0, round(sum(item["duration"] for item in chunk), 2))


def build_char_map(scene: dict) -> dict[str, str]:
    raws = list(scene.get("characters", []))
    for line in scene.get("dialogue", []):
        if line["speaker"] not in raws:
            raws.append(line["speaker"])
    return {raw: make_id("C", raw, i) for i, raw in enumerate(raws)}


def make_shot(item: dict, shot_id: str, start: float, duration: float,
              scene: dict, char_map: dict[str, str], is_last_shot: bool = False) -> dict:
    end = round(start + duration, 2)
    if item["kind"] == "dialogue":
        speaker_id = char_map[item["speaker"]]
        voice_note = f"{TODO}；audio_type: {item['audio_type']}"
        if item["note"]:
            voice_note += f"；delivery: {item['note']}"
        audio = {
            "has_dialogue": True,
            "speaker": speaker_id,
            "line_verbatim": item["text"],
            "voice_4d_spec": voice_note,
            "delivery_timing_anchor": None,
            "lips_closed_lock": False,
            "audio_bridge": "NONE",
            "foley_and_ambience": TODO,
        }
        # 動作力學三要素引導結構（說話鏡頭）
        stages = [
            f"{TODO}：【施力點】說話起手姿態與神態反應",
            f"{TODO}：【傳導路徑】重心微移與肢體呼吸起伏",
            f"{TODO}：【受擊與環境反饋】神態定格與環境氛圍呼應",
        ]
        character_ids = [speaker_id]
    else:
        audio = {
            "has_dialogue": False,
            "speaker": None,
            "line_verbatim": None,
            "lips_closed_lock": False,  # 只在露臉不說話鏡由人工／validate 建議後再鎖（#37 #38）
            "audio_bridge": "NONE",
            "foley_and_ambience": TODO,
        }
        beat_text = item["text"]
        # 動作力學三要素引導結構（動作拍）
        stages = [
            f"{TODO}：【施力點】{beat_text}（發力部位與起手動作）",
            f"{TODO}：【傳導路徑】重心轉移與肢體/武器運動軌跡",
            f"{TODO}：【受擊與環境反饋】形變/位移與揚塵/氣浪特效",
        ]
        named = [char_map[c] for c in scene.get("characters", []) if c and c in beat_text]
        character_ids = named or [char_map[c] for c in scene.get("characters", [])]  # 動作文字點名者優先，沒點名才退回全場

    stages_en = [
        f"{TODO}: force origin in English",
        f"{TODO}: transfer path in English",
        f"{TODO}: reaction and environment feedback in English",
    ]
    tail_note = "末鏡收尾靜止留白" if is_last_shot else "動作與視線延伸"
    return {
        "shot_id": shot_id,
        "start_time": start,
        "end_time": end,
        "duration": duration,
        "character_ids": character_ids,
        "reference_refs": [],
        "status": "pending",
        # 鏡頭意圖先於技術欄位：先想這一鏡要讓觀眾懂什麼，再推出景別與運鏡（references/storyboard/shot-intent.md）
        "shot_intent": {
            "audience": f"{TODO}：觀眾看完這一鏡必須看懂／感受到什麼",
            "story_beat": f"{TODO}：這一鏡推進的劇情節拍",
            "pov": f"{TODO}：誰的視角，觀眾站在誰那邊",
            "emotional_shift": f"{TODO}：情緒從哪裡變到哪裡",
        },
        "choice_why": {
            "shot_size": f"{TODO}：為什麼是這個景別（扣回意圖）",
            "lens_distance": f"{TODO}：為什麼是這個焦距與物距",
            "movement": f"{TODO}：為什麼這樣動（或固定）",
            "blocking": f"{TODO}：人物在畫面哪裡、看向哪裡、為什麼",
            "background": f"{TODO}：背景要露出場景圖裡的什麼、為什麼",
            **({"line_timing": f"{TODO}：台詞在動作前、中、後哪一刻開口，為什麼"} if audio.get("has_dialogue") else {}),
        },
        "camera_optics": {
            "shot_size": "MS",
            "focal_length": "35mm",
            "physical_distance": TODO,
            "pov_routing": "objective",
            "movement": "static",
        },
        "spatial_blocking": {
            "anchor_objects": list(scene.get("props", [])),
            "blocking_desc": TODO,
        },
        "action_and_performance": {
            "action_stages": stages,
            "observable_expression": f"{TODO}：五官神態微表演（{tail_note}）",
            "action_stages_en": stages_en,
            "observable_expression_en": f"{TODO}: observable expression in English",
        },
        "dialogue_and_audio": audio,
    }


def build_shots(chunk: list[dict], seg_id: str, scene: dict, char_map: dict[str, str]) -> list[dict]:
    shots, start = [], 0.0
    total = len(chunk)
    for i, item in enumerate(chunk, start=1):
        is_last = (i == total)
        shot = make_shot(item, f"{seg_id}-SH{i:02d}", round(start, 2), item["duration"],
                         scene, char_map, is_last_shot=is_last)
        shots.append(shot)
        start = shot["end_time"]
    return shots


def build_asset_refs(scene: dict, char_map: dict[str, str]) -> dict:
    """char_map 已含場景角色與說話者（說話者不在 scene.characters 時也會補入）。"""
    location = scene.get("setting", {}).get("location", "")
    speakers: list[str] = []
    for line in scene.get("dialogue", []):
        if line["speaker"] not in speakers:
            speakers.append(line["speaker"])
    return {
        "characters": [
            {"id": char_id, "costume_id": TODO, "version": TODO}
            for char_id in char_map.values()
        ],
        "scene_id": make_id("S", location, 0) if location else TODO,
        "props": [make_id("P", p, i) for i, p in enumerate(scene.get("props", []))],
        "voices": [
            {"character_id": char_map[s], "voice_id": "V-" + char_map[s][2:]}
            for s in speakers
        ],
    }


def build_layer2(handoff: dict, scene: dict, seg_id: str, chunk: list[dict],
                 handshake: dict, planned: dict, char_map: dict[str, str]) -> dict:
    handshake = {
        **handshake,
        "overflow_dialogue_in": None,
        "overflow_dialogue_out": None,
        "persistent_world_state": [f"{k}: {v}" for k, v in scene.get("continuity_final", {}).items()],
    }
    return {
        "project_id": handoff["project_id"],
        "scene_id": scene["scene_id"],
        "segment_id": seg_id,
        "source_scene_id": scene["scene_id"],
        "style_lock": {
            "anchor": TODO,
            "negative": TODO,
            "lighting_lock_line": TODO,
            "continuity_anchors": {
                "lighting": f"{TODO}：光線錨點（光源方向、色溫與主影位置）",
                "axis": f"{TODO}：軸線錨點（180度水平視線軸與攝影機安全側）",
                "blocking": f"{TODO}：站位錨點（主體與實體家具之相對空間坐標）",
                "texture": f"{TODO}：材質錨點（服裝布料、皮膚質感與環境材質）",
            },
            "tail_freeze_hold": True,
        },
        "asset_refs": build_asset_refs(scene, char_map),
        "metadata": {
            "aspect_ratio": ASPECT_MAP[handoff["aspect_ratio"]],
            "target_duration_sec": segment_target(chunk),
            "pacing_profile": "Standard_Narrative",
            "lighting_lock_line": TODO,
        },
        "continuity_handshake": handshake,
        "shots": build_shots(chunk, seg_id, scene, char_map),
        "segment_end_state": {"planned_final_state": planned},
    }


def build_scene(handoff: dict, scene: dict, chunks: list[list[dict]],
                prev_last_id: str | None,
                max_shots: int = DEFAULT_MAX_SHOTS,
                max_segment_sec: float = DEFAULT_MAX_SEGMENT_SEC) -> list[tuple[str, dict]]:
    """prev_last_id 為 None 代表該集第一場，採 HARD_CUT_ESTABLISH；後續段落預設走 INDEPENDENT_REF2VA 獨立分段。"""
    ids = segment_ids(scene["scene_id"], len(chunks))
    if len(chunks) > 1:
        warn(f"{scene['scene_id']} 切成 {len(chunks)} 段（每段 ≤ {max_shots} 鏡、≤ {max_segment_sec:.1f} 秒），請導演確認切點")
    char_map = build_char_map(scene)
    out = []
    for i, (seg_id, chunk) in enumerate(zip(ids, chunks)):
        if i == 0 and prev_last_id is None:
            handshake = {"mode": "HARD_CUT_ESTABLISH", "inherited_from_segment": None}
        else:
            inherited = prev_last_id if i == 0 else ids[i - 1]
            handshake = {"mode": "INDEPENDENT_REF2VA", "inherited_from_segment": inherited}
        planned = scene.get("continuity_final", {}) if i == len(chunks) - 1 else {}
        out.append((seg_id, build_layer2(handoff, scene, seg_id, chunk, handshake, planned, char_map)))
    return out


def convert_handoff(handoff: dict, scene_filter: str | None,
                    max_shots: int = DEFAULT_MAX_SHOTS,
                    max_segment_sec: float = DEFAULT_MAX_SEGMENT_SEC) -> list[tuple[str, dict]]:
    """回傳 [(segment_id, layer2 dict)]，依集與場順序。"""
    if handoff.get("aspect_ratio") == "other":
        warn("handoff aspect_ratio 為 other，Layer 2 對應為 16:9，請導演確認")
    results: list[tuple[str, dict]] = []
    matched = False
    for episode in handoff.get("episodes", []):
        prev_last_id: str | None = None
        for scene in episode.get("scenes", []):
            chunks = scene_chunks(scene, max_shots=max_shots, max_segment_sec=max_segment_sec)
            ids = segment_ids(scene["scene_id"], len(chunks))
            if scene_filter is None or scene_filter == scene["scene_id"]:
                matched = matched or scene_filter == scene["scene_id"]
                results += build_scene(handoff, scene, chunks, prev_last_id,
                                       max_shots=max_shots, max_segment_sec=max_segment_sec)
            prev_last_id = ids[-1]
    if scene_filter and not matched:
        raise ValueError(f"找不到場景 {scene_filter}")
    return results


MIN_ACTION_SHOT_SEC = 1.5
MIN_CUT_GAP_SEC = 2.0  # 與 audit_refs_and_segments E4 一致：首切、間隔、末段都要 >= 2 秒


def _round_half(x: float) -> float:
    return round(x * 2) / 2


def min_segment_sec(n_shots: int) -> float:
    """n 鏡分段在 FreeVideo 取整（17n+5 floor）後仍能滿足 E4 切點規則的最短名義秒數。"""
    if n_shots <= 1:
        return 2.0
    return MIN_CUT_GAP_SEC * n_shots + 0.5


def fit_total_duration(results: list[tuple[str, dict]], target_total: float,
                       max_segment_sec: float = DEFAULT_MAX_SEGMENT_SEC) -> list[str]:
    """（僅 --duration-policy fit 使用，會改變敘事節奏）把骨架總長壓到 target_total（不拉長）：對白鏡維持字數 ÷ 4 的下限，只縮放動作鏡；
    以 0.5 秒為單位取整，並確保每段鏡數符合 E4 切點最短秒數。回傳警告訊息。"""
    notes: list[str] = []
    shots = [(seg, sh) for _, seg in results for sh in seg["shots"]]
    if not shots:
        return notes

    def floor_of(sh: dict) -> float:
        dlg = sh.get("dialogue_and_audio", {})
        if dlg.get("has_dialogue") and dlg.get("line_verbatim"):
            return max(MIN_ACTION_SHOT_SEC, _round_half(count_speech_chars(dlg["line_verbatim"]) / CHARS_PER_SEC + 0.25))
        return MIN_ACTION_SHOT_SEC

    fixed = sum(floor_of(sh) for _, sh in shots)
    current = sum(float(sh["duration"]) for _, sh in shots)
    if target_total >= current:
        notes.append(f"目標 {target_total}s 不低於自然總長 {current:.1f}s：fit 只壓縮不拉長"
                     "（拉長會讓段落超過 H3 單次上限與 E2 鏡數規則），未調整。")
        return notes
    if target_total < fixed:
        notes.append(f"目標總長 {target_total}s 低於對白與最短動作鏡下限 {fixed}s，請刪減台詞或鏡頭。")
    flex_cur = sum(float(sh["duration"]) - floor_of(sh) for _, sh in shots)
    flex_tgt = max(0.0, target_total - fixed)
    ratio = (flex_tgt / flex_cur) if flex_cur > 0 else 0.0
    for _, sh in shots:
        f = floor_of(sh)
        sh["duration"] = min(MAX_SHOT_SEC, max(f, _round_half(f + (float(sh["duration"]) - f) * ratio)))

    # 段落 E4 最短秒數：不足就從最長鏡借秒
    for seg_id, seg in results:
        need = min_segment_sec(len(seg["shots"]))
        tot = sum(sh["duration"] for sh in seg["shots"])
        if tot < need:
            seg["shots"][-1]["duration"] += _round_half(need - tot + 0.25)
            notes.append(f"{seg_id}: {len(seg['shots'])} 鏡至少需 {need}s 才過 E4 切點規則，已延長末鏡。")

    # 0.5 秒取整造成的殘差，用最長動作鏡吸收
    diff = _round_half(target_total - sum(sh["duration"] for _, sh in shots))
    if diff:
        cand = sorted(((seg, sh) for seg, sh in shots if not sh.get("dialogue_and_audio", {}).get("has_dialogue")),
                      key=lambda x: -x[1]["duration"]) or list(shots)
        step = 0.5 if diff > 0 else -0.5
        i = 0
        while abs(diff) >= 0.5 and i < len(cand) * 4:
            seg, sh = cand[i % len(cand)]
            seg_tot = sum(x["duration"] for x in seg["shots"])
            if (step > 0 and sh["duration"] + step <= MAX_SHOT_SEC) or (step < 0 and sh["duration"] - 0.5 >= floor_of(sh)
                            and seg_tot - 0.5 >= min_segment_sec(len(seg["shots"]))):
                sh["duration"] += step
                diff -= step
            i += 1

    for seg_id, seg in results:
        t = 0.0
        for sh in seg["shots"]:
            sh["start_time"] = round(t, 2)
            t += sh["duration"]
            sh["end_time"] = round(t, 2)
        seg["metadata"]["target_duration_sec"] = round(t, 2)
        if t > max_segment_sec + 1e-6:
            notes.append(f"{seg_id}: 拉長後 {t:g}s 超過單段建議上限 {max_segment_sec:g}s，請拆段或改用 report 模式。")
    total = sum(seg["metadata"]["target_duration_sec"] for _, seg in results)
    notes.append(f"骨架總長由 {current:.1f}s 調整為 {total:.1f}s（目標 {target_total}s）。")
    return notes



def write_skeletons(results: list[tuple[str, dict]], out_dir: Path, force: bool) -> list[dict]:
    """先算完所有路徑、內容與結構檢查，確認沒有重複檔名後才開始寫檔，避免寫到一半留下殘缺骨架。"""
    planned = []
    for seg_id, layer2 in results:
        path = out_dir / f"layer2-{seg_id}.json"
        content = json.dumps(layer2, ensure_ascii=False, indent=2) + "\n"
        planned.append((seg_id, layer2, path, content, check_layer2(layer2)))
    names = [item[2].name for item in planned]
    duplicates = sorted({n for n in names if names.count(n) > 1})
    if duplicates:
        raise ValueError(f"段落檔名重複，未寫入任何檔案：{duplicates}")

    rows = []
    pending: list[tuple[Path, Path]] = []  # (暫存檔, 正式檔)，全部寫成功後才改名
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        for seg_id, layer2, path, content, errors in planned:
            if path.exists() and not force:
                status = "略過（已存在）"
            else:
                tmp = path.with_name(path.name + ".tmp")
                tmp.write_text(content, encoding="utf-8")
                pending.append((tmp, path))
                status = "寫入"
            rows.append({
                "segment_id": seg_id,
                "scene_id": layer2["scene_id"],
                "shots": len(layer2["shots"]),
                "target": layer2["metadata"]["target_duration_sec"],
                "mode": layer2["continuity_handshake"]["mode"],
                "characters": len(layer2["asset_refs"]["characters"]),
                "file": path.name,
                "status": status,
                "errors": errors,
            })
        for tmp, path in pending:
            os.replace(tmp, path)
    except OSError:
        for tmp, _ in pending:
            try:
                tmp.unlink()
            except OSError:
                pass  # 已改名或本來就沒寫成，無殘留
        raise
    return rows


def print_summary(rows: list[dict]) -> None:
    print("| 段落 | 場景 | 鏡數 | 秒數 | 銜接 | 角色 | 檔案 | 狀態 | 結構檢查 |")
    print("|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        check = "通過" if not r["errors"] else f"失敗 {len(r['errors'])} 項"
        print(f"| {r['segment_id']} | {r['scene_id']} | {r['shots']} | {r['target']} | "
              f"{r['mode']} | {r['characters']} | {r['file']} | {r['status']} | {check} |")
    for r in rows:
        for err in r["errors"]:
            print(f"[結構錯誤] {r['segment_id']}: {err}", file=sys.stderr)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="handoff JSON 轉 Layer 2 分鏡骨架（已全面升級對齊《噩盡島》實戰定案）")
    ap.add_argument("handoff", type=Path, help="handoff JSON 路徑")
    ap.add_argument("--out-dir", type=Path, required=True, help="輸出目錄")
    ap.add_argument("--scene", help="只輸出指定場景，例如 EP01-S01")
    ap.add_argument("--max-segment-sec", type=float, default=DEFAULT_MAX_SEGMENT_SEC,
                    help="單段最大目標時長秒數（預設 10.0s，每段建議 7–10s）")
    ap.add_argument("--max-shots", type=int, default=DEFAULT_MAX_SHOTS,
                    help="單段最大鏡頭數（預設 3 鏡，每段建議 2–3 節拍）")
    ap.add_argument("--force", action="store_true", help="覆寫已存在的骨架檔")
    ap.add_argument("--duration-policy", choices=("report", "fit"), default="report",
                    help="report（預設）：只回報自然總長與目標的偏差，不改鏡頭秒數；"
                         "fit：把總長壓/拉到目標（會把動作鏡擠成預告片節奏，僅在使用者明確要求硬性片長時用）")
    ap.add_argument("--target-total-sec", type=float, default=None,
                    help="整集目標總秒數；預設讀 handoff episodes[].accepted_duration_seconds，沒有再讀 target_duration_seconds"
                         "（單集且未用 --scene 時）。report 模式只用來算偏差；fit 模式才縮放動作鏡（對白鏡保留字數÷4 下限）")
    args = ap.parse_args()

    try:
        handoff = json.loads(args.handoff.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"[錯誤] 讀取 handoff 失敗：{exc}", file=sys.stderr)
        return 2
    schema_errors = check_schema(handoff, load_schema(HANDOFF_SCHEMA))
    if schema_errors:
        for err in schema_errors:
            print(f"[handoff 錯誤] {err}", file=sys.stderr)
        return 1

    try:
        results = convert_handoff(handoff, args.scene,
                                  max_shots=args.max_shots,
                                  max_segment_sec=args.max_segment_sec)
    except DialogueOverflowError as exc:
        print(f"[錯誤] {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"[錯誤] {exc}", file=sys.stderr)
        return 2

    target_total = args.target_total_sec
    episodes = handoff.get("episodes", [])
    if target_total is None and not args.scene and len(episodes) == 1:
        ep0 = episodes[0]
        target_total = ep0.get("accepted_duration_seconds") or ep0.get("target_duration_seconds")
    natural = sum(float(sh["duration"]) for _, seg in results for sh in seg["shots"])
    for _, seg in results:  # 保留壓縮前的自然秒數，審核頁才看得到真實偏差
        seg["metadata"]["natural_duration_sec"] = seg["metadata"]["target_duration_sec"]
    if target_total:
        drift = (natural - float(target_total)) / float(target_total)
        if args.duration_policy == "fit":
            for note in fit_total_duration(results, float(target_total), args.max_segment_sec):
                warn(note)
        elif abs(drift) > 0.15:
            warn(f"自然總長 {natural:g}s，對目標 {float(target_total):g}s 偏差 {drift:+.0%}（未壓縮）。"
                 "請在階段 3/4 決定：接受並寫入 accepted_duration_seconds、於場次邊界拆集，或刪去非因果鏡頭。")

    try:
        rows = write_skeletons(results, args.out_dir, args.force)
    except OSError as exc:
        print(f"[錯誤] 寫入分鏡骨架失敗：{exc.filename or args.out_dir}（{exc.strerror or exc}）。"
              f"暫存檔已清除；若部分 layer2 檔已寫入，請檢查輸出目錄。", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"[錯誤] {exc}", file=sys.stderr)
        return 2
    print_summary(rows)
    return 1 if any(r["errors"] for r in rows) else 0


if __name__ == "__main__":
    sys.exit(main())
