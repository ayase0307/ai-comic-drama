#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate_structure.py — 漫劇劇本格式、鏡頭術語黑名單與 Handoff JSON Schema 驗證器
僅使用 Python 標準庫，執行確定性結構檢查。
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "storyboard"))
from speech_utils import normalize_speech  # noqa: E402

# 場景標題正規表達式：支援「1-1 舊公寓 夜/內（閃回）」或緊湊格式「1-1卧室日/内」
SCENE_HEADER_RE = re.compile(
    r"^(\d+-\d+)\s*([^\s]+?)\s*(日|夜|晨|昏|不明)/(內|外|內/外|内|外|内/外)(?:[（(]([^）)]+)[）)])?\s*$"
)
EPISODE_HEADER_RE = re.compile(r"^第\s*(\d+)\s*集[｜|：:\s]*(.*)$")
CHAR_LINE_RE = re.compile(r"^人物[：:]\s*(.+)$")
DIALOGUE_LINE_RE = re.compile(r"^([^：:△\s（(]+)(?:[（(]([^）)]+)[）)])?[：:]\s*(.+)$")

# 劇本管戲、分鏡管拍：禁止出現在劇本正文的攝影機術語
CAMERA_BLACKWORDS = [
    "特寫鏡頭", "大特寫", "推鏡頭", "拉鏡頭", "搖鏡頭", "移鏡頭", "跟鏡頭",
    "甩鏡頭", "切至", "疊化", "鏡頭給到", "鏡頭轉向", "畫面一轉",
    "我們看到", "我們聽到", "Camera", "Zoom in", "Zoom out", "POV鏡頭"
]

# 不可直接拍攝的純抽象心理黑名單詞彙（CRITICAL_SCENE_UNFILMABLE 風險）
UNFILMABLE_BLACKWORDS = [
    "心裡想著", "心中暗想", "暗暗發誓", "百感交集", "五味雜陳",
    "意識到自己", "回憶起過去的點點滴滴", "腦海中浮現出三年前的往事"
]


def validate_json_against_schema(
    data: Any, schema: Dict[str, Any], path: str = "$"
) -> List[str]:
    """輕量級零依賴 JSON Schema 驗證器（支援 type, required, enum, pattern, minItems, minimum, items, properties）。"""
    errors: List[str] = []
    expected_type = schema.get("type")

    if expected_type:
        allowed_types = expected_type if isinstance(expected_type, list) else [expected_type]
        type_ok = False
        for t in allowed_types:
            if t == "object" and isinstance(data, dict):
                type_ok = True
            elif t == "array" and isinstance(data, list):
                type_ok = True
            elif t == "string" and isinstance(data, str):
                type_ok = True
            elif t == "integer" and isinstance(data, int) and not isinstance(data, bool):
                type_ok = True
            elif t == "number" and isinstance(data, (int, float)) and not isinstance(data, bool):
                type_ok = True
            elif t == "boolean" and isinstance(data, bool):
                type_ok = True
            elif t == "null" and data is None:
                type_ok = True
        if not type_ok:
            errors.append(f"[SCHEMA_TYPE_ERROR] {path}: 預期型別 {allowed_types}，實際為 {type(data).__name__}")
            return errors

    if "enum" in schema and data not in schema["enum"]:
        errors.append(f"[SCHEMA_ENUM_ERROR] {path}: 值 '{data}' 不在允許清單 {schema['enum']} 中")

    if isinstance(data, str) and "pattern" in schema:
        if not re.match(schema["pattern"], data):
            errors.append(f"[SCHEMA_PATTERN_ERROR] {path}: 字串 '{data}' 不符合格式 {schema['pattern']}")

    if isinstance(data, (int, float)) and not isinstance(data, bool) and "minimum" in schema:
        if data < schema["minimum"]:
            errors.append(f"[SCHEMA_MIN_ERROR] {path}: 數值 {data} 小於最小值 {schema['minimum']}")

    if isinstance(data, list):
        if "minItems" in schema and len(data) < schema["minItems"]:
            errors.append(f"[SCHEMA_MIN_ITEMS_ERROR] {path}: 陣列長度 {len(data)} 小於最小要求 {schema['minItems']}")
        if "items" in schema:
            for idx, item in enumerate(data):
                errors.extend(validate_json_against_schema(item, schema["items"], f"{path}[{idx}]"))

    if isinstance(data, dict):
        for req_key in schema.get("required", []):
            if req_key not in data:
                errors.append(f"[SCHEMA_REQUIRED_ERROR] {path}: 缺少必填欄位 '{req_key}'")
        props = schema.get("properties", {})
        for k, v in data.items():
            if k in props:
                errors.extend(validate_json_against_schema(v, props[k], f"{path}.{k}"))
            elif isinstance(schema.get("additionalProperties"), dict):
                errors.extend(
                    validate_json_against_schema(v, schema["additionalProperties"], f"{path}.{k}")
                )

    return errors


def parse_and_validate_script(script_text: str) -> Dict[str, Any]:
    """解析人類可讀劇本並執行結構、黑名單與可拍性驗證。"""
    lines = script_text.splitlines()
    errors: List[str] = []
    warnings: List[str] = []
    gate_failures: List[str] = []

    scenes: List[Dict[str, Any]] = []
    seen_scene_ids = set()
    current_scene: Optional[Dict[str, Any]] = None
    total_dialogues = 0
    total_vo_dialogues = 0

    for line_no, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line:
            continue

        # 略過 Markdown code fence 或標題註解
        if line.startswith("```") or line.startswith("#"):
            continue

        ep_match = EPISODE_HEADER_RE.match(line)
        if ep_match:
            continue

        scene_match = SCENE_HEADER_RE.match(line)
        if scene_match:
            scene_num, loc_name, time_of_day, int_ext, timeline_tag = scene_match.groups()
            if scene_num in seen_scene_ids:
                errors.append(f"[DUPLICATE_SCENE_ID] 第 {line_no} 行: 場景編號 '{scene_num}' 重複出現")
            seen_scene_ids.add(scene_num)

            if current_scene is not None:
                if len(current_scene["actions"]) == 0:
                    errors.append(
                        f"[NO_ACTION_BEAT] 場景 {current_scene['scene_num']}: 缺乏任何 '△' 動作描寫行（淪為純廣播劇）"
                    )
                    gate_failures.append("CRITICAL_SCENE_UNFILMABLE")
                scenes.append(current_scene)

            current_scene = {
                "scene_num": scene_num,
                "location": loc_name,
                "time": time_of_day,
                "int_ext": int_ext,
                "timeline_tag": timeline_tag or "正敘",
                "line_no": line_no,
                "characters": [],
                "actions": [],
                "dialogues": [],
            }
            continue

        if current_scene is None:
            warnings.append(f"[ORPHAN_LINE] 第 {line_no} 行位於任何場景標題之前: '{line[:30]}'")
            continue

        char_match = CHAR_LINE_RE.match(line)
        if char_match:
            raw_chars = re.split(r"[、，,\s]+", char_match.group(1).strip())
            current_scene["characters"] = [c for c in raw_chars if c]
            continue

        if line.startswith("△"):
            action_content = line[1:].strip()
            if not action_content:
                errors.append(f"[EMPTY_ACTION] 第 {line_no} 行: '△' 動作行內容為空")
            for bw in CAMERA_BLACKWORDS:
                if bw in action_content:
                    errors.append(
                        f"[CAMERA_JARGON_VIOLATION] 第 {line_no} 行 ({current_scene['scene_num']}): "
                        f"動作行出現分鏡攝影術語 '{bw}'（違反『劇本管戲，分鏡管拍』）"
                    )
            for ubw in UNFILMABLE_BLACKWORDS:
                if ubw in action_content:
                    errors.append(
                        f"[UNFILMABLE_ACTION] 第 {line_no} 行 ({current_scene['scene_num']}): "
                        f"動作行包含不可直接拍攝的抽象心理詞彙 '{ubw}'"
                    )
                    if "CRITICAL_SCENE_UNFILMABLE" not in gate_failures:
                        gate_failures.append("CRITICAL_SCENE_UNFILMABLE")
            current_scene["actions"].append({"line_no": line_no, "text": action_content})
            continue

        dlg_match = DIALOGUE_LINE_RE.match(line)
        if dlg_match:
            speaker, note, text = dlg_match.groups()
            total_dialogues += 1
            note_str = note or ""
            if any(k in note_str for k in ["畫外音", "画外音", "內心獨白", "内心独白", "VO", "V.O."]):
                total_vo_dialogues += 1
            if len(note_str) > 12:
                warnings.append(
                    f"[LONG_PARENTHETICAL] 第 {line_no} 行: 角色 '{speaker}' 的括注提示過長（{len(note_str)} 字），建議轉為 △ 動作行"
                )
            current_scene["dialogues"].append(
                {"line_no": line_no, "speaker": speaker, "note": note_str, "text": text}
            )
            continue

        errors.append(
            f"[INVALID_LINE_FORMAT] 第 {line_no} 行 ({current_scene['scene_num']}): "
            f"無法識別為場景標題、人物行、△動作行或『角色：對白』格式 -> '{line[:40]}'"
        )

    if current_scene is not None:
        if len(current_scene["actions"]) == 0:
            errors.append(
                f"[NO_ACTION_BEAT] 場景 {current_scene['scene_num']}: 缺乏任何 '△' 動作描寫行"
            )
            if "CRITICAL_SCENE_UNFILMABLE" not in gate_failures:
                gate_failures.append("CRITICAL_SCENE_UNFILMABLE")
        scenes.append(current_scene)

    if len(scenes) == 0:
        errors.append("[NO_SCENES_FOUND] 劇本中未解析到任何合規場景標題（如 '1-1 舊公寓 夜/內'）")
        gate_failures.append("CRITICAL_SCENE_UNFILMABLE")

    vo_ratio = (total_vo_dialogues / total_dialogues) if total_dialogues > 0 else 0.0
    if vo_ratio > 0.30 and total_dialogues >= 4:
        errors.append(
            f"[EXCESSIVE_VOICEOVER] 純畫外音／內心獨白佔比過高 ({total_vo_dialogues}/{total_dialogues} = {vo_ratio:.1%})，超過 30% 硬上限"
        )
    elif vo_ratio > 0.15 and total_voiceover_check_needed(total_vo_dialogues, total_dialogues):
        warnings.append(
            f"[HIGH_VOICEOVER_RATIO] 畫外音佔比為 {vo_ratio:.1%} ({total_vo_dialogues}/{total_dialogues})，高於建議值 15%"
        )

    return {
        "scene_count": len(scenes),
        "total_dialogues": total_dialogues,
        "total_vo_dialogues": total_vo_dialogues,
        "vo_ratio": round(vo_ratio, 3),
        "scenes": scenes,
        "errors": errors,
        "warnings": warnings,
        "gate_failures": gate_failures,
    }


def check_script_handoff_dialogue(scenes: List[Dict[str, Any]], handoff_data: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    """劇本各場對白與 handoff 同序場景的 dialogue[].text 逐場比對（去標點與空白後串接）。回傳 (errors, warnings)。
    handoff 該場 dialogue 為空時只警告；非空且不一致才是 ERROR 閘門。"""
    errors: List[str] = []
    warnings: List[str] = []
    handoff_scenes = [s for ep in handoff_data.get("episodes", []) for s in ep.get("scenes", [])]
    for script_scene, hs in zip(scenes, handoff_scenes):
        sid = hs.get("scene_id", script_scene["scene_num"])
        script_lines = [d["text"] for d in script_scene["dialogues"]]
        hand_lines = [line["text"] for line in hs.get("dialogue", [])]
        if not hand_lines:
            if script_lines:
                warnings.append(f"[HANDOFF_DIALOGUE_EMPTY] 場景 {sid}：劇本有 {len(script_lines)} 句對白，"
                                f"但 handoff 的 dialogue 為空，請補齊")
            continue
        exp = normalize_speech("".join(hand_lines))
        act = normalize_speech("".join(script_lines))
        if exp != act:
            i = next((k for k, (a, b) in enumerate(zip(exp, act)) if a != b), min(len(exp), len(act)))
            errors.append(f"[SCRIPT_HANDOFF_DIALOGUE_MISMATCH] 場景 {sid}：劇本對白與 handoff dialogue 不一致"
                          f"（去標點後第 {i + 1} 字起）：劇本「…{act[max(0, i - 6):i + 10]}…」"
                          f"→ handoff「…{exp[max(0, i - 6):i + 10]}…」")
    return errors, warnings


def total_voiceover_check_needed(vo_count: int, total_count: int) -> bool:
    return total_count >= 5 and vo_count > 1


def main() -> int:
    parser = argparse.ArgumentParser(description="驗證漫劇劇本格式與 Handoff JSON Schema")
    parser.add_argument("--script", type=str, required=True, help="漫劇劇本檔案路徑 (.md / .txt)")
    parser.add_argument("--handoff", type=str, default=None, help="選填：交接 JSON 檔案路徑")
    parser.add_argument(
        "--schema",
        type=str,
        default=str(Path(__file__).resolve().parent.parent.parent / "references" / "adapt" / "templates" / "handoff.schema.json"),
        help="Handoff JSON Schema 路徑",
    )
    parser.add_argument("--json", action="store_true", help="以 JSON 格式輸出結果")
    args = parser.parse_args()

    script_path = Path(args.script)
    if not script_path.exists():
        print(f"錯誤：找不到劇本檔案 {script_path}", file=sys.stderr)
        return 1

    script_text = script_path.read_text(encoding="utf-8")
    result = parse_and_validate_script(script_text)

    if args.handoff:
        handoff_path = Path(args.handoff)
        schema_path = Path(args.schema)
        if not handoff_path.exists():
            result["errors"].append(f"[HANDOFF_NOT_FOUND] 找不到交接檔案: {handoff_path}")
        else:
            try:
                handoff_data = json.loads(handoff_path.read_text(encoding="utf-8"))
                if schema_path.exists():
                    schema_data = json.loads(schema_path.read_text(encoding="utf-8"))
                    schema_errors = validate_json_against_schema(handoff_data, schema_data)
                    result["errors"].extend(schema_errors)

                # 檢查場景數量對齊
                json_scenes = [
                    s
                    for ep in handoff_data.get("episodes", [])
                    for s in ep.get("scenes", [])
                ]
                if len(json_scenes) != result["scene_count"]:
                    result["errors"].append(
                        f"[SCENE_COUNT_MISMATCH] 劇本場景數 ({result['scene_count']}) 與 Handoff JSON 場景數 ({len(json_scenes)}) 不一致"
                    )
                dlg_errors, dlg_warnings = check_script_handoff_dialogue(result["scenes"], handoff_data)
                result["errors"].extend(dlg_errors)
                result["warnings"].extend(dlg_warnings)
                # 檢查單場識別碼唯一性
                seen_json_ids = set()
                for s in json_scenes:
                    sid = s.get("scene_id")
                    if sid in seen_json_ids:
                        result["errors"].append(f"[DUPLICATE_JSON_SCENE_ID] Handoff JSON 中重複的 scene_id: {sid}")
                    seen_json_ids.add(sid)
            except Exception as exc:
                result["errors"].append(f"[HANDOFF_JSON_PARSE_ERROR] 無法解析 JSON: {exc}")

    passed = len(result["errors"]) == 0 and len(result["gate_failures"]) == 0
    result["status"] = "PASS" if passed else "FAIL"

    if args.json:
        # 輸出精簡結果（省略完整 scenes 細節以免過長）
        out = {k: v for k, v in result.items() if k != "scenes"}
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(f"=== 劇本結構與格式驗證報告 ({script_path.name}) ===")
        print(f"狀態: {result['status']} | 場景數: {result['scene_count']} | 對白行數: {result['total_dialogues']} | 畫外音佔比: {result['vo_ratio']:.1%}")
        if result["gate_failures"]:
            print(f"觸發強制退稿閘門: {', '.join(result['gate_failures'])}")
        for err in result["errors"]:
            print(f"  [ERROR] {err}")
        for warn in result["warnings"]:
            print(f"  [WARN]  {warn}")

    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
