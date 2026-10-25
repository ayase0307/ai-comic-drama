#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""h3d bind：從已核准的 bible／assets／Layer 2 產生階段 5 的 video-bible.json 與 video-bindings.json。

為什麼要有：沒有 bindings 時編譯器走 AssetRegistry，直接拿角色聖經的四視圖整板當參考圖，
只掛一張角色圖，其餘在場角色沒有身分錨 → audit E20（整板）與 E19（未錨定在場人物）必擋。

選圖規則（每段每個角色只掛一張圖，官方序對 <Subject k> ↔ <Picture k+1>）：
  - 逐鏡判讀（assets/face-visibility.json）聚合到段：任一鏡看得到正臉 → face；否則有背面 → back；否則 profile。
    沒有判讀時預設 face（最保守：要求單視角正面裁切）。
  - face：單視角正面裁切（計畫表 face_crop；沒有計畫且原圖不是整板時用原圖）。
  - back／profile：整板查表（sheet ＋ reference_view=panel ＋ panel_label_en ＋ panel_role）；原圖不是整板時直接當單視角錨點。
  - 生物：整板時一律整板查表（panel_role=creature）。
缺圖不猜：任何缺口都列出來並給 `h3d crop` 指令，不寫任何檔案。

不改階段 1／2 檔案；重產時保留既有 bindings 裡手寫的欄位（en_overlay、shot_overrides、audio_references…）。

計畫表 assets/character-reference-plans.json（選填）：
  {"characters": {"C-x": {"default": {"face_crop": "assets/crops/C-x-face.png", "sheet": "images/char-x.png",
                                      "panel_labels_en": {"back": "...", "profile": "..."}},
                          "costumes": {"W-x-02": {...同上}}}},
   "creatures": {"CREATURE-x": {"sheet": "images/creature-x.png", "panel_label_en": "..."}}}
逐鏡判讀 assets/face-visibility.json（選填）：
  {"shots": {"<global_shot_id 或 segment_id/shot_id>": {"C-x": "face|profile|back"}}}
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from audit_refs_and_segments import looks_like_multi_view_board  # noqa: E402
from compile_layer2_to_h3 import AssetRegistry, ensure_global_shot_ids  # noqa: E402

# 技能標準四視圖板：左起面部特寫，右側三格為正／側／背全身（references/consistency.md）。
DEFAULT_PANEL_LABELS = {
    "profile": "the full-body three-quarter side view, the middle of the three standing full-body figures",
    "back": "the full-body back view, the rightmost of the three standing full-body figures",
    "creature": "the full-body side view, the middle of the three standing full-body figures",
}
FACE_PANEL_BOX = "0,0,0.25,1"  # 標準板第一格（面部特寫）


def _load_json(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _rel(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _ids(values: Any) -> List[str]:
    out = []
    for value in values or []:
        cid = value.get("id") or value.get("character_id") if isinstance(value, dict) else value
        if cid and str(cid) not in out:
            out.append(str(cid))
    return out


def segment_states(seg_id: str, shots: List[Dict[str, Any]], visibility: Dict[str, Any]) -> Dict[str, str]:
    """逐鏡判讀聚合成段：face 優先，其次 back，再其次 profile。"""
    found: Dict[str, set] = {}
    for shot in shots:
        gid = str(shot.get("global_shot_id") or "")
        row = visibility.get(f"{seg_id}/{gid}") or visibility.get(gid) or {}
        for cid, state in row.items():
            found.setdefault(cid, set()).add(state)
    return {cid: ("face" if "face" in s else "back" if "back" in s else "profile") for cid, s in found.items()}


def video_bible(registry: AssetRegistry, raw_bible: Dict[str, Any]) -> Dict[str, Any]:
    names = {str(c.get("character_id") or c.get("id")): c.get("canonical_name") or c.get("name")
             for c in raw_bible.get("characters", []) or [] if isinstance(c, dict)}
    characters = []
    for cid in registry.characters:
        rec = registry.get_character(cid)
        characters.append({
            "id": cid, "name": names.get(cid) or rec.get("name") or cid,
            "visual_prompt_en": rec.get("desc_en", ""), "short_en": rec.get("short_en", ""),
            "reference_image": rec.get("ref_img") if registry.path_exists(rec.get("ref_img", "")) else None,
            "is_creature": bool(rec.get("is_creature")), "is_group": bool(rec.get("is_group")),
            "voice_only": bool(rec.get("voice_only")), "no_visual_reference": bool(rec.get("no_visual_reference")),
            "wardrobe_states": rec.get("wardrobe_states") or {}, "variants": rec.get("variants") or {},
        })
    locations = []
    for lid in registry.locations:
        rec = registry.get_location(lid)
        locations.append({"id": lid, "name": rec.get("name", lid), "visual_prompt_en": rec.get("desc_en", ""),
                          "reference_image": rec.get("ref_img") if registry.path_exists(rec.get("ref_img", "")) else None})
    props = [{"id": pid, "name": p.get("name", pid), "visual_prompt_en": p.get("desc_en", ""),
              "reference_image": p.get("ref_img") or None} for pid, p in registry.props.items()]
    style = {key: registry.style[src] for key, src in (("anchor", "style_anchor"), ("negative", "style_negative"),
                                                     ("lighting_lock_line", "lighting_lock_line")) if registry.style.get(src)}
    return {"schema_version": "1.0-stage5-derived", "derived_for": "Stage 5 compiler input only (h3d bind)",
            "style": style, "characters": characters, "locations": locations, "props": props,
            "bodydetails": [{"id": d, "name": rec.get("name", d), "desc_en": rec.get("desc_en", ""),
                             "reference_image": rec.get("ref_img"), "source_id": rec.get("source_id", "")}
                            for d, rec in registry.bodydetails.items()],
            "id_aliases": dict(registry.id_aliases)}


def _crop_hint(sheet: str, cid: str) -> str:
    return (f"python scripts/h3d.py crop --root . --image {sheet} --box {FACE_PANEL_BOX} "
            f"--out-dir assets/crops --prefix {cid}-face，再把產出檔寫進 assets/character-reference-plans.json "
            f"的 characters.{cid}.default.face_crop")


def choose_reference(root: Path, registry: AssetRegistry, plans: Dict[str, Any], cid: str, state: str,
                     costume: Optional[str], gaps: List[str], where: str) -> Optional[Dict[str, Any]]:
    """回傳 reference_paths 條目（含 group）；缺圖寫進 gaps 回 None。"""
    rec = registry.get_character(cid, wardrobe_state=costume)
    sheet_default = rec.get("ref_img") or ""
    if rec.get("is_group"):
        if not sheet_default or not (root / sheet_default).is_file():
            gaps.append(f"{where} 群眾 {cid}：找不到群眾參考圖 {sheet_default or '（未登記）'}")
            return None
        return {"group": "extras", "id": cid, "reference_image": sheet_default}
    if rec.get("is_creature"):
        plan = (plans.get("creatures") or {}).get(cid) or {}
        sheet = plan.get("sheet") or sheet_default
        if not sheet or not (root / sheet).is_file():
            gaps.append(f"{where} 生物 {cid}：找不到設定圖 {sheet or '（未登記）'}")
            return None
        entry = {"group": "creatures", "id": cid, "reference_image": sheet}
        if plan or looks_like_multi_view_board(root, sheet):
            entry.update(reference_view="panel", panel_role="creature",
                         panel_label_en=plan.get("panel_label_en") or DEFAULT_PANEL_LABELS["creature"])
        return entry
    char_plan = (plans.get("characters") or {}).get(cid) or {}
    plan = (char_plan.get("costumes") or {}).get(costume or "") or char_plan.get("default") or {}
    sheet = plan.get("sheet") or sheet_default
    entry: Dict[str, Any] = {"group": "characters", "id": cid}
    if costume:
        entry["costume_id"] = costume
    is_board = bool(sheet) and (root / sheet).is_file() and looks_like_multi_view_board(root, sheet)
    if state == "face":
        crop = plan.get("face_crop") or ("" if is_board else sheet)
        if not crop or not (root / crop).is_file():
            gaps.append(f"{where} 角色 {cid} 看得到正臉，需要單視角正面裁切"
                        + (f"（計畫表寫的 {crop} 不存在）" if plan.get("face_crop") else f"：{_crop_hint(sheet, cid) if sheet else '先登記設定圖'}"))
            return None
        entry["reference_image"] = crop
        return entry
    if not sheet or not (root / sheet).is_file():
        gaps.append(f"{where} 角色 {cid}（{state}）：找不到設定圖 {sheet or '（未登記）'}")
        return None
    entry["reference_image"] = sheet
    if is_board:
        labels = plan.get("panel_labels_en") or {}
        entry.update(reference_view="panel", panel_role=state,
                     panel_label_en=labels.get(state) or DEFAULT_PANEL_LABELS[state])
    return entry


def build_segment(root: Path, registry: AssetRegistry, plans: Dict[str, Any], visibility: Dict[str, Any],
                  path: Path, gaps: List[str]) -> Dict[str, Any]:
    raw = path.read_bytes()
    data = ensure_global_shot_ids(json.loads(raw.decode("utf-8-sig")))
    seg_id = str(data.get("segment_id") or data.get("scene_id") or path.stem)
    refs = data.get("asset_refs") or {}
    costume_by_id = {str(e["id"]): e.get("costume_id") for e in refs.get("characters", []) or []
                     if isinstance(e, dict) and e.get("id") and e.get("costume_id")}
    shots = data.get("shots", []) or []
    states = segment_states(seg_id, shots, visibility)
    chosen: Dict[str, Optional[Dict[str, Any]]] = {}  # 一段一角色一張圖
    shot_bindings = []
    for shot in shots:
        gid = str(shot.get("global_shot_id") or "")
        visible, no_visual = [], []
        grouped: Dict[str, List[Dict[str, Any]]] = {"characters": [], "creatures": [], "extras": []}
        for raw_id in _ids(shot.get("character_ids") or shot.get("characters")):
            cid = registry.id_aliases.get(raw_id, raw_id)
            if cid not in registry.characters:
                gaps.append(f"{seg_id}/{gid} 角色 {cid} 未在 bible.json／assets.md 登記")
                continue
            rec = registry.characters[cid]
            if rec.get("no_visual_reference") or rec.get("voice_only"):
                no_visual.append(cid)
                continue
            visible.append(cid)
            if cid not in chosen:
                chosen[cid] = choose_reference(root, registry, plans, cid, states.get(cid, "face"),
                                               costume_by_id.get(cid), gaps, seg_id)
            entry = chosen[cid]
            if entry:
                grouped[entry["group"]].append({k: v for k, v in entry.items() if k != "group"})
        binding: Dict[str, Any] = {"global_shot_id": gid, "reference_paths": grouped,
                                   "visual_subject_ids": visible, "no_visual_reference_ids": no_visual}
        humans = [e["id"] for e in grouped["characters"]]
        face_ids = [cid for cid in humans if states.get(cid, "face") == "face"]
        anchor_ids = [cid for cid in humans if cid not in face_ids]
        if face_ids:
            binding["face_subject_ids"] = face_ids
        if anchor_ids:
            binding["identity_anchor_ids"] = anchor_ids
        shot_bindings.append(binding)
    segment: Dict[str, Any] = {
        "segment_id": seg_id, "source_layer2_path": _rel(root, path),
        "source_sha256": hashlib.sha256(raw).hexdigest(), "shots": shot_bindings,
    }
    scene_id = refs.get("scene_id")
    if scene_id and scene_id in registry.locations:
        scene = registry.get_location(scene_id)
        if scene.get("ref_img") and (root / scene["ref_img"]).is_file():
            segment["scene_reference"] = scene["ref_img"]
    return segment


def merge_existing(generated: Dict[str, Any], old: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """保留手寫欄位：段層與鏡層都是「舊值為底、產生器擁有的欄位覆蓋」。"""
    if not old:
        return generated
    old_shots = {s.get("global_shot_id"): s for s in old.get("shots", []) or [] if isinstance(s, dict)}
    merged = {**old, **generated}
    merged["shots"] = [{**old_shots.get(s["global_shot_id"], {}), **s} for s in generated["shots"]]
    return merged


def bindings_stale(root: Path) -> Optional[str]:
    """next_step 用：沒有 bindings、或某段 layer2 已改（sha 不符）／多出未綁的段 → 回原因。"""
    bindings_path = root / "video-bindings.json"
    layer2 = sorted((root / "layer2").glob("layer2-*.json"))
    if not layer2:
        return None
    if not bindings_path.is_file() or not (root / "video-bible.json").is_file():
        return "還沒有 video-bindings.json／video-bible.json"
    try:
        segments = json.loads(bindings_path.read_text(encoding="utf-8-sig")).get("segments", [])
    except (OSError, json.JSONDecodeError, AttributeError):
        return "video-bindings.json 無法解析"
    known = {s.get("source_layer2_path"): s.get("source_sha256") for s in segments if isinstance(s, dict)}
    for path in layer2:
        rel = _rel(root, path)
        if known.get(rel) != hashlib.sha256(path.read_bytes()).hexdigest():
            return f"{rel} 沒有綁定或已在綁定後修改"
    return None


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="產生階段 5 video-bible.json／video-bindings.json（h3d bind）")
    ap.add_argument("--root", type=Path, default=Path("."))
    ap.add_argument("--bible", type=Path, default=None, help="預設 <root>/adapt/bible.json")
    ap.add_argument("--assets", type=Path, default=None, help="預設 <root>/assets.md")
    ap.add_argument("--plans", type=Path, default=None, help="預設 <root>/assets/character-reference-plans.json")
    ap.add_argument("--visibility", type=Path, default=None, help="預設 <root>/assets/face-visibility.json")
    args = ap.parse_args(argv)
    root = args.root.resolve()
    bible_path = args.bible or root / "adapt" / "bible.json"
    assets_path = args.assets or root / "assets.md"
    registry = AssetRegistry(bible_path=bible_path, assets_path=assets_path, project_root=root)
    plans = _load_json(args.plans or root / "assets" / "character-reference-plans.json", {})
    visibility = _load_json(args.visibility or root / "assets" / "face-visibility.json", {}).get("shots", {})
    layer2 = sorted((root / "layer2").glob("layer2-*.json"))
    if not layer2:
        print("❌ 找不到 layer2/layer2-*.json", file=sys.stderr)
        return 1
    old_bindings = _load_json(root / "video-bindings.json", {})
    old_by_id = {s.get("segment_id"): s for s in old_bindings.get("segments", []) or [] if isinstance(s, dict)}
    gaps: List[str] = []
    segments = [build_segment(root, registry, plans, visibility, p, gaps) for p in layer2]
    if gaps:
        print(f"❌ 綁定缺 {len(gaps)} 項，未寫入任何檔案：", file=sys.stderr)
        for gap in dict.fromkeys(gaps):
            print(f"  - {gap}", file=sys.stderr)
        return 1
    segments = [merge_existing(seg, old_by_id.get(seg["segment_id"])) for seg in segments]
    bible = video_bible(registry, _load_json(bible_path, {}))
    (root / "video-bible.json").write_text(json.dumps(bible, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    payload = {**{k: v for k, v in old_bindings.items() if k != "segments"},
               "schema_version": "1.0-stage5-bindings", "derived_for": "Stage 5 compiler binding sidecar (h3d bind)",
               "segments": segments}
    (root / "video-bindings.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    panels = sum(1 for s in segments for b in s["shots"] for g in b["reference_paths"].values()
                 for e in g if e.get("reference_view") == "panel")
    print(f"✅ 已寫 video-bible.json 與 video-bindings.json：{len(segments)} 段、"
          f"{sum(len(s['shots']) for s in segments)} 鏡、整板查表 {panels} 筆")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
