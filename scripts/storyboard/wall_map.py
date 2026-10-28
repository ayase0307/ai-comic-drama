#!/usr/bin/env python3
"""牆面分配層（wall map）產生器：可選工具，不接進預設編譯流程。

把一份「場景牆面分配表」JSON 展開成每一鏡要前置到 camera 段的英文句子：
  1. Wall map：每個場景常量逐一寫「只在哪面世界牆」＋「本鏡在畫面哪裡」（每鏡重寫，禁止「同上」）
  2. 本鏡一句「不新增門窗」否定句（每鏡只能一句，且各鏡不可相同）
  3. Directions：機位世界朝向、人物世界朝向／自身左右、本機位畫面左右；主光鎖世界位置
  4. （第 2 鏡起，可選）配對句：同一時刻、同一側、不鏡像

規則與證據等級見 references/storyboard/spatial-consistency.md；
實驗數據見 docs/experiments/laoyi-spatial-2026-10/。

用法：
  python scripts/storyboard/wall_map.py --map wall_map.json            # 印出全部鏡頭
  python scripts/storyboard/wall_map.py --map wall_map.json --shot S01-c#1
  python scripts/storyboard/wall_map.py --map wall_map.json --json     # 機器可讀
有錯誤（缺常量、同上、否定句重複…）時 exit 1；只有警告時 exit 0。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

WALLS = ("north", "east", "south", "west")
# 攝影機朝向 → 世界方位落在畫面哪一側（只處理四正向；斜向請在 place 文字裡自己寫）
_FRAME_SIDE = {
    "north": {"west": "frame left", "east": "frame right", "north": "background", "south": "behind the camera"},
    "south": {"east": "frame left", "west": "frame right", "south": "background", "north": "behind the camera"},
    "east": {"north": "frame left", "south": "frame right", "east": "background", "west": "behind the camera"},
    "west": {"south": "frame left", "north": "frame right", "west": "background", "east": "behind the camera"},
}
BANNED_PHRASES = ("同上", "同前", "same as above", "as above", "as before", "as in the previous shot", "ditto")
DEFAULT_CHAR_BUDGET = 800  # 單鏡前置句的建議上限；hosted API 整段 7000 字元，10 鏡左右要留給劇本本身


def frame_side(camera_facing: str, world_dir: str) -> str:
    """回傳世界方位 world_dir 在面向 camera_facing 的機位裡落在畫面哪一側。"""
    facing = (camera_facing or "").lower()
    if facing not in _FRAME_SIDE:
        raise ValueError(f"camera_facing 只支援 {WALLS}，收到 {camera_facing!r}")
    return _FRAME_SIDE[facing][world_dir.lower()]


def _element_clause(el: dict, place: str | None) -> str:
    wall = el["wall"]
    verb = el.get("verb", "is")
    only = "only " if el.get("only", True) else ""
    base = f"{el['text']} {verb} {only}on the {wall} wall"
    return base + (f", {place}" if place else "")


def render_shot(wall_map: dict, shot_id: str) -> dict:
    """回傳 {'shot', 'text', 'errors', 'warnings'}。"""
    errors: list[str] = []
    warnings: list[str] = []
    shots = wall_map.get("shots", {})
    if shot_id not in shots:
        return {"shot": shot_id, "text": "", "errors": [f"找不到鏡頭 {shot_id}"], "warnings": []}
    shot = shots[shot_id]
    elements = wall_map.get("elements", [])
    place = shot.get("place", {}) or {}
    facing = shot.get("camera_facing")

    for el in elements:
        if el.get("wall") not in WALLS:
            errors.append(f"元素 {el.get('id')} 的 wall 必須是 {WALLS} 之一")
    unknown = sorted(set(place) - {el.get("id") for el in elements})
    if unknown:
        errors.append(f"{shot_id}: place 有未定義的元素 {unknown}")

    clauses = []
    for el in elements:
        p = place.get(el["id"])
        if p is None and facing in _FRAME_SIDE and el.get("wall") in WALLS:
            p = frame_side(facing, el["wall"]) + " here"
        clauses.append(_element_clause(el, p))
    furniture = wall_map.get("furniture")
    if furniture:
        clauses.append(furniture + (f", {shot['furniture_here']}" if shot.get("furniture_here") else ""))
    parts = ["Wall map: " + "; ".join(clauses) + "."]

    neg = (shot.get("no_new_openings") or "").strip()
    if not neg:
        errors.append(f"{shot_id}: 缺 no_new_openings（每鏡一句不新增門窗）")
    elif neg.count(".") > 1:
        errors.append(f"{shot_id}: no_new_openings 只能一句")
    else:
        parts.append(neg)

    light = wall_map.get("key_light")
    if light:
        lw = light["from"]
        side = frame_side(facing, lw) if facing in _FRAME_SIDE else None
        parts.append(f"{light['text']} comes only from the {lw}" + (f", {side} in this shot." if side else "."))

    directions = (shot.get("directions") or "").strip()
    if not directions:
        warnings.append(f"{shot_id}: 沒寫 directions（機位世界朝向／人物自身左右／畫面左右）")
    else:
        parts.append(directions)
    if shot.get("pair"):
        parts.append(shot["pair"].strip())

    text = " ".join(parts)
    lowered = text.lower()
    for phrase in BANNED_PHRASES:
        if phrase.lower() in lowered:
            errors.append(f"{shot_id}: 出現「{phrase}」——場景常量每鏡要重寫，不准寫同上")
    budget = int(wall_map.get("char_budget", DEFAULT_CHAR_BUDGET))
    if len(text) > budget:
        warnings.append(f"{shot_id}: {len(text)} 字元，超過建議上限 {budget}")
    return {"shot": shot_id, "text": text, "errors": errors, "warnings": warnings}


def render_all(wall_map: dict) -> list[dict]:
    results = [render_shot(wall_map, sid) for sid in wall_map.get("shots", {})]
    seen: dict[str, str] = {}
    for sid, shot in wall_map.get("shots", {}).items():
        neg = (shot.get("no_new_openings") or "").strip().lower()
        if neg and neg in seen:
            for r in results:
                if r["shot"] == sid:
                    r["errors"].append(f"{sid}: 否定句和 {seen[neg]} 相同（各鏡要寫本鏡看得到的那面牆）")
        elif neg:
            seen[neg] = sid
    return results


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="牆面分配層：把場景牆面分配表展開成每鏡前置句（可選工具，不改編譯）")
    ap.add_argument("--map", required=True, help="牆面分配表 JSON")
    ap.add_argument("--shot", help="只印這一鏡（例 S01-c#1）")
    ap.add_argument("--json", action="store_true", help="輸出 JSON")
    args = ap.parse_args(argv)
    wall_map = json.loads(Path(args.map).read_text(encoding="utf-8"))
    results = [render_shot(wall_map, args.shot)] if args.shot else render_all(wall_map)
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        for r in results:
            print(f"[{r['shot']}]\n{r['text']}")
            for e in r["errors"]:
                print(f"  ❌ {e}")
            for w in r["warnings"]:
                print(f"  ⚠ {w}")
            print()
    return 1 if any(r["errors"] for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
