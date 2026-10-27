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

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "storyboard"))
from speech_utils import normalize_speech  # noqa: E402
from audio_keywords import classify_note  # noqa: E402

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


ADAPTATION_CHANGE_TYPES = ("must_keep", "keep_if_possible", "merge", "compress", "remove", "reorder", "addition")  # 與 handoff.schema.json enum 一致
_CHANGE_KEYWORDS = (
    ("merge", ("合併", "併為", "併入", "merge")),
    ("remove", ("刪", "移除", "拿掉", "省略", "remove")),
    ("reorder", ("調換", "提前", "挪後", "倒敘", "順序", "reorder")),
    ("addition", ("新增", "加入", "補一", "addition", "add ")),
    ("compress", ("壓縮", "壓成", "濃縮", "改為", "改成", "改", "compress")),
)
_ID_RE = re.compile(r"\b[A-Z]{1,4}-?\d{1,4}[a-z]?\b")


def _extract_ids(text: str) -> List[str]:
    """只抽出 U01 / MK02 / S03 這類 ID，忽略註解裡的說明文字（修正空格切分把中文說明當 ID 的問題）。"""
    ids = _ID_RE.findall(text)
    if ids:
        return list(dict.fromkeys(ids))
    return [r.strip() for r in re.split(r"[,，、]+", text) if r.strip()]


def _parse_change_comment(body: str) -> Dict[str, Any]:
    """解析 <!-- change: ... -->。
    支援兩種寫法：
      1. 結構化：change: MERGE | U01 | 理由
      2. 自由文字：change: "路遇與帶回合併為一場"（依關鍵字推斷類型，原文放進 description）
    """
    parts = [p.strip().strip('"“”「」') for p in body.split("|")]
    first = parts[0] if parts else ""
    if first.lower() in ADAPTATION_CHANGE_TYPES:
        chg_type = first.lower()
        chg_ref = parts[1] if len(parts) > 1 and parts[1] else None
        chg_desc = " | ".join(parts[2:]) if len(parts) > 2 else ""
    else:
        text = " | ".join(p for p in parts if p)
        chg_type = "compress"
        low = text.lower()
        for t, kws in _CHANGE_KEYWORDS:
            if any(k in low for k in kws):
                chg_type = t
                break
        ids = _ID_RE.findall(text)
        chg_ref = ids[0] if ids else None
        chg_desc = text
    return {"type": chg_type, "source_ref": chg_ref, "description": chg_desc}



def parse_and_validate_script(script_text: str) -> Dict[str, Any]:
    """解析人類可讀劇本並執行結構、黑名單與可拍性驗證。"""
    # Windows 記事本存的 UTF-8 BOM 會黏在第一行，集標題被當成 ORPHAN_LINE
    lines = script_text.lstrip("\ufeff").splitlines()
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

        # 略過 Markdown code fence
        if line.startswith("```"):
            continue

        # 支援 HTML 註解元數據 (例如 <!-- source: U01, U02 -->)
        comment_match = re.match(r"^<!--\s*(.*?)\s*-->$", line)
        if comment_match:
            if current_scene is not None:
                c_text = comment_match.group(1).strip()
                current_scene.setdefault("comments", []).append(c_text)
                s_m = re.match(r"^source[：:]\s*(.+)$", c_text, re.IGNORECASE)
                if s_m:
                    refs = _extract_ids(s_m.group(1))
                    current_scene.setdefault("source_refs", []).extend(refs)
                mk_m = re.match(r"^must_keep[：:]\s*(.+)$", c_text, re.IGNORECASE)
                if mk_m:
                    mks = _extract_ids(mk_m.group(1))
                    current_scene.setdefault("must_keep_ids", []).extend(mks)
                # 事件交代要素：<!-- exposition: U01 起因 經過 結果 -->（供 event_coverage.py 對帳）
                ex_m = re.match(r"^exposition[：:]\s*(\S+)\s*[|｜]?\s*(.*)$", c_text, re.IGNORECASE)
                if ex_m:
                    beats = [b for b in re.split(r"[\s,，、/／|｜]+", ex_m.group(2)) if b]
                    expo = current_scene.setdefault("event_exposition", {})
                    expo.setdefault(ex_m.group(1), [])
                    expo[ex_m.group(1)].extend(b for b in beats if b not in expo[ex_m.group(1)])
                chg_m = re.match(r"^change[：:]\s*(.+)$", c_text, re.IGNORECASE)
                if chg_m:
                    current_scene.setdefault("adaptation_changes", []).append(
                        _parse_change_comment(chg_m.group(1))
                    )
            continue

        clean_line = re.sub(r"^#+\s*", "", line)

        ep_match = EPISODE_HEADER_RE.match(clean_line)
        if ep_match:
            continue

        scene_match = SCENE_HEADER_RE.match(clean_line)
        if not scene_match and line.startswith("#"):
            # 一般 Markdown 註解或非場景章節標題，略過
            continue
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
                "source_refs": [],
                "must_keep_ids": [],
                "adaptation_changes": [],
                "comments": [],
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
            if classify_note(note_str) == "voiceover":
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
        hand_lines = [line.get("text", "") if isinstance(line, dict) else "" for line in hs.get("dialogue", [])]
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

    script_text = script_path.read_text(encoding="utf-8-sig")
    result = parse_and_validate_script(script_text)

    if args.handoff:
        handoff_path = Path(args.handoff)
        schema_path = Path(args.schema)
        if not handoff_path.exists():
            result["errors"].append(f"[HANDOFF_NOT_FOUND] 找不到交接檔案: {handoff_path}")
        else:
            try:
                handoff_data = json.loads(handoff_path.read_text(encoding="utf-8-sig"))
                if schema_path.exists():
                    schema_data = json.loads(schema_path.read_text(encoding="utf-8-sig"))
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
