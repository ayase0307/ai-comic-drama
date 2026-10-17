#!/usr/bin/env python3
"""handoff JSON 轉 Layer 2 分鏡骨架。

用法：
    python scripts/storyboard/handoff_to_skeleton.py <handoff.json> --out-dir <目錄> [--scene EP01-S01] [--force]

每個場景輸出 <目錄>/layer2-<segment_id>.json，結構符合
references/storyboard/templates/layer2-storyboard.schema.json。

這是「骨架」，供導演細化，不是成品分鏡：
- 每句對白、每個動作拍各一個鏡頭（每段上限 8 鏡），對白逐字複製，絕不丟棄。
- 鏡頭秒數由文字推算：對白 = 字數 ÷ 3.8（至少 1.5 秒），動作拍預設 2.5 秒。
- 單鏡估時超過 15 秒（H3 單鏡上限）的對白，依標點切成多鏡（找不到標點就切中間字），串接後與原文相同。
- 場景依序切段，每段 ≤ 8 鏡且估時 ≤ 60 秒；段名 <scene_id>-a…-z、-aa、-ab…，後段 SEAMLESS_CONTINUATION 接前段。
- 鏡頭語言、動作階段、光線鎖、風格鎖等標 TODO，導演須依情節重寫；
  validate_storyboard.py 與 layer2_to_table.py --check 遇到 TODO 一律失敗。
- 動作拍的順序為先動作後對白（handoff 未提供兩者的先後關係）。
- 已存在的檔案不會被覆蓋，除非加 --force。
只使用標準庫。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from speech_utils import count_speech_chars  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
LAYER2_SCHEMA = ROOT / "references/storyboard/templates/layer2-storyboard.schema.json"
HANDOFF_SCHEMA = ROOT / "references/adapt/templates/handoff.schema.json"

MAX_SHOTS = 8
MAX_SEGMENT_SEC = 60.0
CHARS_PER_SEC = 3.8
MIN_DIALOGUE_SEC = 1.5
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
    return f"{prefix}-{slugify(raw) or f'item{index + 1}'}"


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
    """對白鏡秒數 = 字數 ÷ 3.8，至少 1.5 秒。"""
    return round(max(MIN_DIALOGUE_SEC, count_speech_chars(text) / CHARS_PER_SEC), 2)


def split_long_line(text: str) -> list[str]:
    """估時超過 MAX_SHOT_SEC 的對白切成多鏡：優先切在最接近中間的標點後（兩側都要有字），否則切中間字。
    遞迴直到每段 ≤ 上限；串接結果與原文逐字相同。"""
    if dialogue_seconds(text) <= MAX_SHOT_SEC or len(text) < 2:
        return [text]
    mid = len(text) // 2
    cuts = [
        i + 1 for i, ch in enumerate(text[:-1])
        if not ch.isspace() and count_speech_chars(ch) == 0
        and count_speech_chars(text[: i + 1]) > 0 and count_speech_chars(text[i + 1:]) > 0
    ]
    cut = min(cuts, key=lambda c: abs(c - mid)) if cuts else mid
    return split_long_line(text[:cut]) + split_long_line(text[cut:])


def build_items(scene: dict) -> list[dict]:
    """先動作拍、後對白（對白為必保留項目，動作拍是段落的填充物）。超長對白會切成多個對白鏡。"""
    beats = scene.get("action_beats") or scene["storyboard_handoff"].get("required_visual_beats") or []
    items: list[dict] = [{"kind": "beat", "text": text, "duration": ACTION_SHOT_SEC} for text in beats]
    for line in scene["dialogue"]:
        for piece in split_long_line(line["text"]):
            items.append({
                "kind": "dialogue",
                "speaker": line["speaker"],
                "text": piece,
                "note": line.get("delivery_note", ""),
                "audio_type": line["audio_type"],
                "duration": dialogue_seconds(piece),
            })
    return items


def pack_items(items: list[dict], scene_id: str) -> list[list[dict]]:
    """依序裝段：每段 ≤ MAX_SHOTS 鏡且估時 ≤ MAX_SEGMENT_SEC。只換段，不丟任何項目。"""
    segments: list[list[dict]] = []
    current: list[dict] = []
    current_sec = 0.0
    for item in items:
        if item["duration"] > MAX_SEGMENT_SEC:
            raise DialogueOverflowError(
                f"{scene_id} 有一句台詞估時 {item['duration']} 秒，超過單段 {MAX_SEGMENT_SEC:.0f} 秒上限，"
                f"無法切段又不丟台詞：{item['text']!r}。請拆句後重跑。"
            )
        if current and (len(current) >= MAX_SHOTS or current_sec + item["duration"] > MAX_SEGMENT_SEC):
            segments.append(current)
            current, current_sec = [], 0.0
        current.append(item)
        current_sec += item["duration"]
    if current:
        segments.append(current)
    return segments


def scene_chunks(scene: dict) -> list[list[dict]]:
    """場景切段（純計算，不發警告，供計算銜接關係時重複呼叫）。"""
    placeholder = {"kind": "beat", "text": f"{TODO}：補動作", "duration": ACTION_SHOT_SEC}
    return pack_items(build_items(scene) or [placeholder], scene["scene_id"])


def segment_target(chunk: list[dict]) -> float:
    return max(1.0, round(sum(item["duration"] for item in chunk), 2))


def build_char_map(scene: dict) -> dict[str, str]:
    raws = list(scene.get("characters", []))
    for line in scene["dialogue"]:
        if line["speaker"] not in raws:
            raws.append(line["speaker"])
    return {raw: make_id("C", raw, i) for i, raw in enumerate(raws)}


def make_shot(item: dict, shot_id: str, start: float, duration: float,
              scene: dict, char_map: dict[str, str]) -> dict:
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
        stages = [f"{TODO}：補動作階段"]
        character_ids = [speaker_id]
    else:
        audio = {
            "has_dialogue": False,
            "speaker": None,
            "line_verbatim": None,
            "lips_closed_lock": True,
            "audio_bridge": "NONE",
            "foley_and_ambience": TODO,
        }
        stages = [item["text"]]
        character_ids = [char_map[c] for c in scene.get("characters", [])]
    return {
        "shot_id": shot_id,
        "start_time": start,
        "end_time": end,
        "duration": duration,
        "character_ids": character_ids,
        "reference_refs": [],
        "status": "pending",
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
            "observable_expression": TODO,
        },
        "dialogue_and_audio": audio,
    }


def build_shots(chunk: list[dict], seg_id: str, scene: dict, char_map: dict[str, str]) -> list[dict]:
    shots, start = [], 0.0
    for i, item in enumerate(chunk, start=1):
        shot = make_shot(item, f"{seg_id}-SH{i:02d}", round(start, 2), item["duration"], scene, char_map)
        shots.append(shot)
        start = shot["end_time"]
    return shots


def build_asset_refs(scene: dict, char_map: dict[str, str]) -> dict:
    """char_map 已含場景角色與說話者（說話者不在 scene.characters 時也會補入）。"""
    location = scene["setting"].get("location", "")
    speakers: list[str] = []
    for line in scene["dialogue"]:
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
        "persistent_world_state": [f"{k}: {v}" for k, v in scene["continuity_final"].items()],
    }
    return {
        "project_id": handoff["project_id"],
        "scene_id": scene["scene_id"],
        "segment_id": seg_id,
        "source_scene_id": scene["scene_id"],
        "style_lock": {"anchor": TODO, "negative": TODO, "lighting_lock_line": TODO},
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
                prev_last_id: str | None) -> list[tuple[str, dict]]:
    """prev_last_id 為 None 代表該集第一場，採 HARD_CUT_ESTABLISH。"""
    ids = segment_ids(scene["scene_id"], len(chunks))
    if len(chunks) > 1:
        warn(f"{scene['scene_id']} 切成 {len(chunks)} 段（每段 ≤ {MAX_SHOTS} 鏡、≤ {MAX_SEGMENT_SEC:.0f} 秒），請導演確認切點")
    char_map = build_char_map(scene)
    out = []
    for i, (seg_id, chunk) in enumerate(zip(ids, chunks)):
        if i == 0 and prev_last_id is None:
            handshake = {"mode": "HARD_CUT_ESTABLISH", "inherited_from_segment": None}
        else:
            inherited = prev_last_id if i == 0 else ids[i - 1]
            handshake = {"mode": "SEAMLESS_CONTINUATION", "inherited_from_segment": inherited}
        planned = scene["continuity_final"] if i == len(chunks) - 1 else {}
        out.append((seg_id, build_layer2(handoff, scene, seg_id, chunk, handshake, planned, char_map)))
    return out


def convert_handoff(handoff: dict, scene_filter: str | None) -> list[tuple[str, dict]]:
    """回傳 [(segment_id, layer2 dict)]，依集與場順序。"""
    if handoff["aspect_ratio"] == "other":
        warn("handoff aspect_ratio 為 other，Layer 2 對應為 16:9，請導演確認")
    results: list[tuple[str, dict]] = []
    matched = False
    for episode in handoff["episodes"]:
        prev_last_id: str | None = None
        for scene in episode["scenes"]:
            chunks = scene_chunks(scene)
            ids = segment_ids(scene["scene_id"], len(chunks))
            if scene_filter is None or scene_filter == scene["scene_id"]:
                matched = matched or scene_filter == scene["scene_id"]
                results += build_scene(handoff, scene, chunks, prev_last_id)
            prev_last_id = ids[-1]
    if scene_filter and not matched:
        raise ValueError(f"找不到場景 {scene_filter}")
    return results


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

    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for seg_id, layer2, path, content, errors in planned:
        if path.exists() and not force:
            status = "略過（已存在）"
        else:
            path.write_text(content, encoding="utf-8")
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
    ap = argparse.ArgumentParser(description="handoff JSON 轉 Layer 2 分鏡骨架（僅供導演細化）")
    ap.add_argument("handoff", type=Path, help="handoff JSON 路徑")
    ap.add_argument("--out-dir", type=Path, required=True, help="輸出目錄")
    ap.add_argument("--scene", help="只輸出指定場景，例如 EP01-S01")
    ap.add_argument("--force", action="store_true", help="覆寫已存在的骨架檔")
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
        results = convert_handoff(handoff, args.scene)
    except DialogueOverflowError as exc:
        print(f"[錯誤] {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"[錯誤] {exc}", file=sys.stderr)
        return 2

    rows = write_skeletons(results, args.out_dir, args.force)
    print_summary(rows)
    return 1 if any(r["errors"] for r in rows) else 0


if __name__ == "__main__":
    sys.exit(main())
