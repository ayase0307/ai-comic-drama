#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""decisions.json：把使用者定案變成機器讀得到的規則。

為什麼要有這個檔：畫風、比例、台詞政策、驗收標準這類「老大拍板過」的事，
過去只寫在 NOTES.md，換一個 agent 就忘了，或被編譯器的模板句悄悄蓋掉。
這裡把每條定案存成結構化紀錄（id、規則、值、使用者原話＋日期、適用階段），
`h3d next`、QA 分類與審核頁都從這裡讀。

寫入只能走 `h3d decide <id> <value> --quote "<原話>"`，不要手改。
格式見 references/schemas/decisions.schema.json。
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

DECISIONS_NAME = "decisions.json"
SCHEMA_VERSION = 1

# 驗收政策的問題代碼。verdicts.json 的 issues、acceptance_policy 的
# rerun_on／accept 都只能用這些代碼，避免「多人」「多出人物」「路人亂入」各寫各的。
ISSUE_CODES: Dict[str, str] = {
    "extra_person": "多出人（不該出現的人物）",
    "burned_subtitle": "畫面燒進字幕",
    "face_mix": "混臉／身份錯亂／同框露臉",
    "wardrobe_wrong": "服裝錯",
    "style_shift": "畫風突變（例如半寫實變平塗卡通）",
    "composition_broken": "構圖嚴重問題",
    "grid_leak": "九宮格框線殘留",
    "paper_text": "紙面／道具出字（後製處理）",
    "aged_face": "人物稍老",
    "low_chroma": "技術 QA 低彩度（低彩度場景常誤判）",
    "color_jump": "相鄰段色調跳躍",
    "no_audio": "缺音軌",
    "other": "其他（需人工判斷）",
}

# 《我修的是遺忘課》2026-10-22 定下的標準，作為建議值。
RECOMMENDED_ACCEPTANCE_POLICY: Dict[str, Any] = {
    "rerun_on": ["extra_person", "burned_subtitle", "face_mix", "wardrobe_wrong",
                 "style_shift", "composition_broken", "grid_leak"],
    "accept": ["paper_text", "aged_face", "low_chroma", "color_jump"],
    "note": "只有真的不該出現的東西才重跑；紙面出字後製處理、人物稍老可接受。",
}

# 已知定案：說明、預設適用階段、h3d next 在哪個階段前要求它存在、該讀的 reference。
KNOWN_DECISIONS: Dict[str, Dict[str, Any]] = {
    "style": {"label": "畫風", "stages": [2, 4, 5, 6], "required_by": 2,
              "reference": "references/styles.md"},
    "aspect_ratio": {"label": "畫面比例", "stages": [2, 4, 5, 6, 7], "required_by": 2,
                     "reference": "references/model-profiles.md"},
    "dialogue_policy": {"label": "台詞政策（哪些台詞上畫、哪些走旁白／TTS）", "stages": [3, 5, 7],
                        "required_by": 3, "reference": "references/adapt/dialogue-and-audio.md"},
    "design_engine": {"label": "設定圖引擎（一經定案全集鎖定）", "stages": [2], "required_by": 2,
                      "reference": "references/consistency.md"},
    "acceptance_policy": {"label": "階段 6 驗收政策（哪些問題才重跑）", "stages": [6], "required_by": 6,
                          "reference": "references/tooling.md"},
    "edit_method": {"label": "剪輯方式（例如全集單一剪輯專案）", "stages": [7], "required_by": 7,
                    "reference": "references/tooling.md"},
    # 選填：使用者授權哪些階段可以「沒有未決卡就自動核准」（h3d approve --auto）。
    # required_by=99：永遠不會因為沒定案而擋路。
    "auto_approve": {"label": "自動核准授權（哪些階段沒有未決卡就自動過）", "stages": [1, 3, 4, 5, 6, 7],
                     "required_by": 99, "reference": "references/tooling.md"},
}

# 這些階段永遠要人決定，auto_approve 不能涵蓋：
# 階段 0（定調五題）、階段 2（角色設定圖：看臉和服裝）。
NEVER_AUTO_STAGES = (0, 2)
# 每個角色的音色定案：id 為 voice:<角色 id>，只能由使用者本人（by=user）定。
VOICE_PREFIX = "voice:"


class DecisionError(ValueError):
    pass


def decisions_path(root: Path) -> Path:
    return Path(root) / DECISIONS_NAME


def empty_decisions() -> Dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "decisions": []}


def load(root: Path) -> Dict[str, Any]:
    """讀 decisions.json；不存在回傳空結構，格式錯誤丟 DecisionError。"""
    path = decisions_path(root)
    if not path.is_file():
        return empty_decisions()
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DecisionError(f"decisions.json 無法解析：{exc}") from exc
    errors = validate(data)
    if errors:
        raise DecisionError("decisions.json 格式錯誤：" + "；".join(errors[:5]))
    return data


def save(root: Path, data: Dict[str, Any]) -> Path:
    errors = validate(data)
    if errors:
        raise DecisionError("拒絕寫入不合格的 decisions.json：" + "；".join(errors[:5]))
    path = decisions_path(root)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
    return path


def validate_acceptance_policy(value: Any) -> List[str]:
    if not isinstance(value, dict):
        return ["acceptance_policy 的值必須是物件 {rerun_on: [...], accept: [...]}"]
    errors: List[str] = []
    seen: Dict[str, str] = {}
    for key in ("rerun_on", "accept"):
        items = value.get(key)
        if not isinstance(items, list) or not all(isinstance(i, str) for i in items):
            errors.append(f"acceptance_policy.{key} 必須是字串陣列")
            continue
        for code in items:
            if code not in ISSUE_CODES:
                errors.append(f"acceptance_policy.{key} 含未知問題代碼 {code}（可用：{', '.join(ISSUE_CODES)}）")
            if code in seen and seen[code] != key:
                errors.append(f"問題代碼 {code} 同時出現在 rerun_on 與 accept")
            seen[code] = key
    return errors


def validate(data: Any) -> List[str]:
    """不依賴 jsonschema 套件的最小驗證；規則與 decisions.schema.json 一致。"""
    if not isinstance(data, dict):
        return ["根節點必須是物件"]
    errors: List[str] = []
    if data.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version 必須是 {SCHEMA_VERSION}")
    items = data.get("decisions")
    if not isinstance(items, list):
        return errors + ["decisions 必須是陣列"]
    ids = set()
    for index, item in enumerate(items):
        where = f"decisions[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{where} 必須是物件")
            continue
        did = item.get("id")
        if not isinstance(did, str) or not did.strip():
            errors.append(f"{where}.id 必填")
        elif did in ids:
            errors.append(f"{where}.id 重複：{did}")
        else:
            ids.add(did)
        if not isinstance(item.get("rule"), str) or not item["rule"].strip():
            errors.append(f"{where}.rule 必填（一句話規則）")
        if "value" not in item:
            errors.append(f"{where}.value 必填")
        source = item.get("source")
        if not isinstance(source, dict):
            errors.append(f"{where}.source 必填")
        else:
            if not isinstance(source.get("quote"), str) or not source["quote"].strip():
                errors.append(f"{where}.source.quote 必須是使用者原話")
            if not isinstance(source.get("date"), str) or not source["date"].strip():
                errors.append(f"{where}.source.date 必填")
        stages = item.get("stages")
        if not isinstance(stages, list) or not stages or not all(
                isinstance(s, int) and not isinstance(s, bool) and 0 <= s <= 7 for s in stages):
            errors.append(f"{where}.stages 必須是 0–7 的整數陣列（至少一個）")
        if did == "acceptance_policy" and "value" in item:
            errors.extend(validate_acceptance_policy(item["value"]))
        if did == "auto_approve" and "value" in item:
            errors.extend(validate_auto_approve(item["value"]))
        if isinstance(did, str) and did.startswith(VOICE_PREFIX) and isinstance(source, dict) \
                and source.get("by", "user") != "user":
            errors.append(f"{where}: 音色定案 {did} 只能由使用者本人決定（source.by 必須是 user）")
    return errors


def validate_auto_approve(value: Any) -> List[str]:
    if not isinstance(value, dict) or not isinstance(value.get("stages"), list):
        return ["auto_approve 的值必須是物件 {\"stages\": [1, 3, ...]}"]
    errors: List[str] = []
    for stage in value["stages"]:
        if not isinstance(stage, int) or isinstance(stage, bool) or not 0 <= stage <= 7:
            errors.append(f"auto_approve.stages 只能是 0–7 的整數（收到 {stage!r}）")
        elif stage in NEVER_AUTO_STAGES:
            errors.append(f"auto_approve 不能涵蓋階段 {stage}（定調與角色設定圖永遠要人決定）")
    return errors


def auto_approve_stages(data: Dict[str, Any]) -> Tuple[List[int], Optional[Dict[str, Any]]]:
    """回傳 (使用者授權自動核准的階段, 該條定案)。沒有定案回傳 ([], None)。"""
    item = get(data, "auto_approve")
    if not item or not isinstance(item.get("value"), dict):
        return [], None
    stages = [s for s in item["value"].get("stages", []) if isinstance(s, int) and s not in NEVER_AUTO_STAGES]
    return sorted(set(stages)), item


def voice_decisions(data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """角色 id → 音色定案（只算使用者本人定的）。"""
    out: Dict[str, Dict[str, Any]] = {}
    for item in data.get("decisions", []):
        did = str(item.get("id") or "")
        if did.startswith(VOICE_PREFIX) and (item.get("source") or {}).get("by", "user") == "user":
            out[did[len(VOICE_PREFIX):]] = item
    return out


def get(data: Dict[str, Any], decision_id: str) -> Optional[Dict[str, Any]]:
    for item in data.get("decisions", []):
        if item.get("id") == decision_id:
            return item
    return None


def acceptance_policy(root: Path) -> Tuple[Dict[str, Any], bool]:
    """回傳 (政策, 是否為使用者定案)。沒有定案時回傳建議值，但標示 False。"""
    try:
        item = get(load(root), "acceptance_policy")
    except DecisionError:
        item = None
    if item and isinstance(item.get("value"), dict):
        return item["value"], True
    return dict(RECOMMENDED_ACCEPTANCE_POLICY), False


def parse_value(decision_id: str, raw: str) -> Any:
    """值先試 JSON（物件、陣列、數字），失敗就當字串。acceptance_policy 支援 `recommended`。"""
    if decision_id == "acceptance_policy" and raw.strip().lower() in ("recommended", "建議", "照建議"):
        return dict(RECOMMENDED_ACCEPTANCE_POLICY)
    if decision_id == "auto_approve":
        text = raw.strip()
        if text[:1] not in ("{", "["):
            # 允許 `h3d decide auto_approve 1,3,4,5,6`
            try:
                return {"stages": [int(x) for x in text.replace("，", ",").split(",") if x.strip()]}
            except ValueError as exc:
                raise DecisionError(f"auto_approve 的值應為階段清單，例如 1,3,4,5,6（收到 {raw}）") from exc
        if text[:1] == "[":
            return {"stages": json.loads(text)}
    text = raw.strip()
    if text[:1] in ("{", "[") or text in ("true", "false", "null"):
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise DecisionError(f"值看起來是 JSON 但無法解析：{exc}") from exc
    return raw


def default_rule(decision_id: str, value: Any) -> str:
    label = KNOWN_DECISIONS.get(decision_id, {}).get("label", decision_id)
    if decision_id == "acceptance_policy" and isinstance(value, dict):
        rerun = "、".join(ISSUE_CODES.get(c, c) for c in value.get("rerun_on", []))
        accept = "、".join(ISSUE_CODES.get(c, c) for c in value.get("accept", []))
        return f"{label}：只有「{rerun}」才重跑；「{accept}」可接受"
    if decision_id == "auto_approve" and isinstance(value, dict):
        return f"{label}：階段 {'、'.join(str(x) for x in value.get('stages', []))} 沒有未決卡且符合政策時自動核准"
    shown = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return f"{label}：{shown}"


def decide(root: Path, decision_id: str, raw_value: str, quote: str, *,
           date: Optional[str] = None, stages: Optional[List[int]] = None,
           rule: Optional[str] = None, by: str = "user") -> Dict[str, Any]:
    """新增或更新一條定案；舊值保留在 history，不會默默消失。"""
    decision_id = decision_id.strip()
    if not decision_id:
        raise DecisionError("id 不可為空")
    if not quote or not quote.strip():
        raise DecisionError("必須用 --quote 附上使用者原話；沒有原話就不是定案")
    value = parse_value(decision_id, raw_value)
    known = KNOWN_DECISIONS.get(decision_id)
    if decision_id.startswith(VOICE_PREFIX):
        if by != "user":
            raise DecisionError("音色定案只能由使用者本人決定（不能 --by user_delegated）")
        if stages is None:
            stages = [7]
        if rule is None:
            rule = f"角色 {decision_id[len(VOICE_PREFIX):]} 的音色：{raw_value}"
    if stages is None:
        if not known:
            raise DecisionError(f"自訂定案 {decision_id} 必須用 --stages 指定適用階段（例如 --stages 5,6）")
        stages = list(known["stages"])
    data = load(root)
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    entry = {
        "id": decision_id,
        "rule": rule or default_rule(decision_id, value),
        "value": value,
        "source": {"quote": quote.strip(), "date": date or datetime.now().astimezone().date().isoformat(), "by": by},
        "stages": sorted(set(int(s) for s in stages)),
        "updated_at": now,
    }
    previous = get(data, decision_id)
    if previous is not None:
        history = list(previous.get("history") or [])
        snapshot = {k: v for k, v in previous.items() if k != "history"}
        history.append(snapshot)
        entry["history"] = history
        data["decisions"] = [entry if item.get("id") == decision_id else item for item in data["decisions"]]
    else:
        data["decisions"].append(entry)
    save(root, data)
    return entry


def missing_for_stage(root: Path, stage: int) -> List[str]:
    """回傳在進入／完成 stage 前應已定案、卻還沒寫進 decisions.json 的 id。"""
    try:
        data = load(root)
    except DecisionError:
        return []
    return [did for did, meta in KNOWN_DECISIONS.items()
            if meta["required_by"] <= stage and get(data, did) is None]


def _parse_stages(text: Optional[str]) -> Optional[List[int]]:
    if text is None:
        return None
    try:
        values = [int(part) for part in text.replace("，", ",").split(",") if part.strip()]
    except ValueError as exc:
        raise DecisionError(f"--stages 格式錯誤：{text}") from exc
    if not values or any(v < 0 or v > 7 for v in values):
        raise DecisionError("--stages 只能是 0–7")
    return values


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="h3d decide",
        description="把使用者定案寫進 decisions.json（不要手改該檔）",
        epilog="例：h3d decide aspect_ratio 16:9 --quote \"比例用 16:9\" --root <專案>；"
               "h3d decide acceptance_policy recommended --quote \"照建議\"",
    )
    parser.add_argument("id", nargs="?", help=f"定案 id（已知：{', '.join(KNOWN_DECISIONS)}；"
                                              f"角色音色用 voice:<角色id>；也可自訂）")
    parser.add_argument("value", nargs="?", help="定案值；JSON 物件／陣列會被解析，其餘當字串")
    parser.add_argument("--quote", help="使用者原話（必填）")
    parser.add_argument("--date", help="原話日期，預設今天（YYYY-MM-DD）")
    parser.add_argument("--stages", help="適用階段，逗號分隔；已知 id 可省略")
    parser.add_argument("--rule", help="一句話規則；省略時自動產生")
    parser.add_argument("--by", default="user", choices=["user", "user_delegated"],
                        help="定案者：user＝使用者本人；user_delegated＝使用者明確授權代為決定")
    parser.add_argument("--root", type=Path, default=Path("."), help="專案根目錄")
    parser.add_argument("--list", action="store_true", help="列出目前所有定案")
    parser.add_argument("--json", action="store_true", help="--list 以 JSON 輸出")
    args = parser.parse_args(argv)
    root = args.root.expanduser().resolve()

    try:
        if args.list:
            data = load(root)
            if args.json:
                print(json.dumps(data, ensure_ascii=False, indent=2))
            elif not data["decisions"]:
                print("（尚無定案）")
            else:
                for item in data["decisions"]:
                    src = item["source"]
                    print(f"- {item['id']}：{item['rule']}（{src['date']}「{src['quote']}」；階段 {item['stages']}）")
            return 0
        if not args.id or args.value is None:
            parser.error("需要 <id> <value>，或用 --list")
        entry = decide(root, args.id, args.value, args.quote or "", date=args.date,
                       stages=_parse_stages(args.stages), rule=args.rule, by=args.by)
    except DecisionError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 2
    print(f"✅ 已記錄定案 {entry['id']}：{entry['rule']}")
    if entry.get("history"):
        print(f"   （取代舊值，歷史保留 {len(entry['history'])} 筆）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
