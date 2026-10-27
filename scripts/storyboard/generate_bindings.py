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

video_backend＝remix（decisions.json 定案，或 --backend remix；PR-R2）時改綁 REMIX 角色包，不綁圖檔：
  - 包計畫表 assets/character-packs.json（必填）：
      {"packs": {"C-x": {"default": "ejin3_x", "tag": "Video", "kind": "actor",
                         "costumes": {"W-x-02": {"pack": "ejin3_x_w02", "variant_of": "ejin3_x"}}},
                 "S-room": {"default": "ejin3_scene_room", "tag": "Picture", "kind": "scene"},
                 "P-spear": "ejin3_prop_spear"},
       "waivers": {"<段 ID>": [{"id": "P-spear", "reason": "6 包逾時，改文字", "quote": "<使用者原話>"}]}}
    值可以只寫包名字串。tag（Picture＝單圖包、Video＝多圖包）應由建包回讀寫入；沒寫時依 kind 推定並警告。
  - 段層產出 refmods（順序＝標籤順序：場景第一、演員、最後是生物／道具／群眾）、pack_waivers、positions（手寫保留）；
    逐鏡只記 visual_subject_ids／pack_ids，不產生 face_subject_ids／identity_anchor_ids／reference_view／panel_label_en
    （舊綁定或計畫表寫了只警告「remix 不使用」）。
  - 在場角色／生物／群眾、場景、asset_refs 登記的道具沒有包也沒有豁免 → 列出缺口、不寫任何檔案。
  - 包數（含場景）依 providers/remix.json 的顯存分級只警告；decisions 的 remix_pack_cap 超過才擋。

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

if str(HERE.parent) not in sys.path:
    sys.path.insert(0, str(HERE.parent))

from audit_refs_and_segments import looks_like_multi_view_board  # noqa: E402
from compile_layer2_to_h3 import AssetRegistry, ensure_global_shot_ids  # noqa: E402
import decisions as decisions_mod  # noqa: E402
import provider_caps  # noqa: E402

# 技能標準四視圖板：左起面部特寫，右側三格為正／側／背全身（references/consistency.md）。
DEFAULT_PANEL_LABELS = {
    "profile": "the full-body three-quarter side view, the middle of the three standing full-body figures",
    "back": "the full-body back view, the rightmost of the three standing full-body figures",
    "creature": "the full-body side view, the middle of the three standing full-body figures",
}
# 標準四視圖板（2560×1440）左側頭部特寫格＝像素 (0, 0, 950, 910)（references/skill-guide.md 單人身份裁切，
# 實測與 FreeVideo media API 裁切像素相同）；換算成比例，任何尺寸的同版面板都適用。
# 版面不同時在計畫表寫 face_crop_box（頂層＝全專案、characters.<id>.default／costumes.<W>＝單一角色）。
FACE_PANEL_BOX = "0,0,0.3711,0.6319"
H3D_CMD = f'python "{(HERE.parent / "h3d.py").as_posix()}"'


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
        sid = str(shot.get("shot_id") or "")
        # 文件寫的鍵是「global_shot_id 或 segment_id/shot_id」；global_shot_id 若是 EP01-S01-a-SH01，
        # 只查 segment_id/global_shot_id 會漏掉 segment_id/SH01 這種寫法。
        row = next((visibility[k] for k in (f"{seg_id}/{gid}", f"{seg_id}/{sid}", gid) if k and k in visibility), None)
        row = row or (visibility.get(sid) if sid and sid != gid else None) or {}
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


def face_crop_box(plans: Dict[str, Any], plan: Optional[Dict[str, Any]] = None) -> str:
    """裁切框：角色計畫 > 計畫表頂層 face_crop_box > 預設標準板頭部特寫格。"""
    for source in (plan or {}, plans or {}):
        box = source.get("face_crop_box") if isinstance(source, dict) else None
        if isinstance(box, str) and box.strip():
            return box.strip()
        if isinstance(box, (list, tuple)) and len(box) == 4:
            return ",".join(str(v) for v in box)
    return FACE_PANEL_BOX


def _crop_hint(sheet: str, cid: str, box: str = FACE_PANEL_BOX) -> str:
    return (f'{H3D_CMD} crop --root . --image "{sheet}" --box {box} '
            f"--out-dir assets/crops --prefix {cid}-face（--box 預設是標準四視圖板左側頭部特寫格 0,0,950,910 的比例；"
            f"裁完務必目視確認只剩一張臉，版面不同就改 --box 或在計畫表寫 face_crop_box），再把產出檔寫進 "
            f"assets/character-reference-plans.json 的 characters.{cid}.default.face_crop")


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
                        + (f"（計畫表寫的 {crop} 不存在）" if plan.get("face_crop") else
                           f"：{_crop_hint(sheet, cid, face_crop_box(plans, plan)) if sheet else '先登記設定圖'}"))
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


# ============================================================================
# video_backend＝remix：綁 REMIX 角色包（PR-R2）
# ============================================================================

PACK_TAGS = ("Picture", "Video")
# remix 不使用的 Ref2VA 欄位：寫了只警告，產出時一律不帶
REMIX_UNUSED_KEYS = ("face_subject_ids", "identity_anchor_ids", "reference_view", "panel_label_en")
# refmods 排序：場景第一、演員、生物、道具、群眾
_KIND_ORDER = {"scene": 0, "actor": 1, "creature": 2, "prop": 3, "extras": 4}


def _pack_record(asset_id: str, raw: Any, costume: Optional[str], warnings: List[str],
                 default_kind: str) -> Optional[Dict[str, Any]]:
    """把計畫表的一項（字串或物件，含服裝變體）正規化成 refmod 記錄。"""
    if raw is None:
        return None
    base: Dict[str, Any] = {"pack": raw} if isinstance(raw, str) else dict(raw)
    chosen = base
    default_costumes = base.get("default_costume") or base.get("default_costumes") or []
    if isinstance(default_costumes, str):
        default_costumes = [default_costumes]
    if costume and costume in default_costumes:
        # 預設包本身穿的就是這套（例如 W-x-01）：不用另建變體包
        costume_is_default = True
    else:
        costume_is_default = False
    if costume and not costume_is_default:
        variant = (base.get("costumes") or {}).get(costume)
        if variant is None:
            # 服裝變體在家機是獨立的包；沒登記就不能默默退回預設服裝的包
            return None
        variant = {"pack": variant} if isinstance(variant, str) else dict(variant)
        chosen = {**{k: v for k, v in base.items() if k in ("kind", "tag")}, **variant}
        chosen.setdefault("variant_of", base.get("pack") or base.get("default"))
    name = chosen.get("pack") or chosen.get("default")
    if not isinstance(name, str) or not name.strip():
        return None
    kind = str(chosen.get("kind") or default_kind)
    tag = chosen.get("tag")
    record: Dict[str, Any] = {"id": asset_id, "pack": name.strip(), "kind": kind}
    if tag in PACK_TAGS:
        record["tag"] = tag
    else:
        record["tag"] = "Picture" if kind == "scene" else "Video"
        record["tag_inferred"] = True
        warnings.append(f"包 {name}（{asset_id}）沒有 tag，依 kind={kind} 推定為 {record['tag']}；"
                        f"tag 看的是建包圖片張數（單圖 Picture／多圖 Video），請建包回讀後寫進計畫表")
    if costume:
        record["costume_id"] = costume
    for key in ("variant_of", "display_name", "source_images_sha"):
        if chosen.get(key):
            record[key] = chosen[key]
    return record


def normalize_packs(plan: Dict[str, Any]) -> Dict[str, Any]:
    """bindings 專案層 packs：計畫表原樣正規化（字串 → {"default": 名稱}）。"""
    out: Dict[str, Any] = {}
    for asset_id, raw in (plan.get("packs") or {}).items():
        out[str(asset_id)] = {"default": raw} if isinstance(raw, str) else dict(raw)
    return out


def _unused_key_hits(obj: Any, where: str, hits: List[str]) -> None:
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in REMIX_UNUSED_KEYS:
                hits.append(f"{where}.{key}")
            _unused_key_hits(value, f"{where}.{key}", hits)
    elif isinstance(obj, list):
        for index, value in enumerate(obj):
            _unused_key_hits(value, f"{where}[{index}]", hits)


def _strip_unused(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _strip_unused(v) for k, v in obj.items() if k not in REMIX_UNUSED_KEYS}
    if isinstance(obj, list):
        return [_strip_unused(v) for v in obj]
    return obj


def _pack_hint(asset_id: str, kind: str) -> str:
    how = ("設定圖四格裁切＋skip_8view" if kind == "actor" else
           "單張母片（kind scene，tag Picture）" if kind == "scene" else
           "設定圖裁切或三張獨立單圖＋skip_8view（生物／道具不要跑 8 視角）")
    return (f"在家機 REMIX Studio 建包（{how}，帶 project），回讀確認後寫進 assets/character-packs.json 的 "
            f"packs.{asset_id}（含 tag）；`h3d pack build` 尚未提供（PR-R8），或在 waivers.<段> 寫豁免並附使用者原話")


def validate_waivers(seg_id: str, waivers: Any, gaps: List[str]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if waivers in (None, []):
        return out
    if not isinstance(waivers, list):
        gaps.append(f"{seg_id} pack_waivers 必須是陣列")
        return out
    for index, item in enumerate(waivers):
        if not isinstance(item, dict) or not (item.get("id") or item.get("pack")):
            gaps.append(f"{seg_id} pack_waivers[{index}] 必須寫 id（或 pack）")
            continue
        if not str(item.get("quote") or "").strip():
            gaps.append(f"{seg_id} pack_waivers[{index}]（{item.get('id') or item.get('pack')}）缺使用者原話 quote；"
                        f"沒有原話不能豁免")
            continue
        out.append(dict(item))
    return out


def validate_positions(seg_id: str, positions: Any, warnings: List[str]) -> None:
    """positions（給 R6 站位閘門用）：只檢查格式，不擋。"""
    if positions in (None, []):
        return
    if not isinstance(positions, list):
        warnings.append(f"{seg_id} positions 應為陣列（[{{\"id\", \"order_lr\", \"axis_side\", \"facing\"}}]）")
        return
    for index, item in enumerate(positions):
        if not isinstance(item, dict) or not item.get("id"):
            warnings.append(f"{seg_id} positions[{index}] 缺 id")
            continue
        order = item.get("order_lr")
        if order is not None and (not isinstance(order, int) or isinstance(order, bool) or order < 1):
            warnings.append(f"{seg_id} positions[{index}].order_lr 應為 1 起算的整數（左到右）")
        if item.get("axis_side") not in (None, "left", "right"):
            warnings.append(f"{seg_id} positions[{index}].axis_side 應為 left／right")
        if item.get("facing") not in (None, "left", "right", "camera_left", "camera_right", "away", "toward"):
            warnings.append(f"{seg_id} positions[{index}].facing 不認得：{item.get('facing')!r}")


def build_segment_remix(root: Path, registry: AssetRegistry, pack_plan: Dict[str, Any], path: Path,
                        old: Optional[Dict[str, Any]], gaps: List[str], warnings: List[str],
                        caps: Dict[str, Any], pack_cap: Optional[int]) -> Dict[str, Any]:
    raw = path.read_bytes()
    data = ensure_global_shot_ids(json.loads(raw.decode("utf-8-sig")))
    seg_id = str(data.get("segment_id") or data.get("scene_id") or path.stem)
    refs = data.get("asset_refs") or {}
    packs = pack_plan.get("packs") or {}
    costume_by_id = {str(e["id"]): e.get("costume_id") for e in refs.get("characters", []) or []
                     if isinstance(e, dict) and e.get("id") and e.get("costume_id")}
    old = old or {}
    waiver_src = (pack_plan.get("waivers") or {}).get(seg_id)
    if waiver_src is None:
        waiver_src = old.get("pack_waivers")
    waivers = validate_waivers(seg_id, waiver_src, gaps)
    waived_ids = {str(w.get("id")) for w in waivers if w.get("id")}
    waived_packs = {str(w.get("pack")) for w in waivers if w.get("pack")}
    hits: List[str] = []
    _unused_key_hits(old, f"video-bindings.json[{seg_id}]", hits)
    for hit in hits:
        warnings.append(f"{hit}：remix 不使用（只在 ref2va 有意義），重產時已拿掉")

    chosen: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []

    def want(asset_id: str, kind: str, costume: Optional[str] = None) -> bool:
        """登記一個需要包的資產；回傳是否有包（豁免也算「不缺」）。"""
        if asset_id in chosen:
            return True
        if asset_id in waived_ids:
            return False
        record = _pack_record(asset_id, packs.get(asset_id), costume, warnings, kind)
        if record is None:
            if asset_id in packs and costume:
                gaps.append(f"{seg_id} {asset_id} 服裝 {costume} 沒有對應的變體包（換服裝＝換包）："
                            f"{_pack_hint(asset_id, kind)}；若預設包穿的就是這套，在 packs.{asset_id} 寫 "
                            f"\"default_costume\": \"{costume}\"")
            else:
                gaps.append(f"{seg_id} {asset_id}（{kind}）沒有 REMIX 包：{_pack_hint(asset_id, kind)}")
            return False
        if record["pack"] in waived_packs:
            return False
        chosen[asset_id] = record
        order.append(asset_id)
        return True

    scene_id = refs.get("scene_id") or data.get("scene_id")
    if scene_id and scene_id in registry.locations:
        want(str(scene_id), "scene")
    elif scene_id and scene_id in packs:
        want(str(scene_id), "scene")

    shot_bindings = []
    for shot in data.get("shots", []) or []:
        gid = str(shot.get("global_shot_id") or "")
        visible, no_visual, pack_ids = [], [], []
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
            kind = "extras" if rec.get("is_group") else "creature" if rec.get("is_creature") else "actor"
            if want(cid, kind, costume_by_id.get(cid)):
                pack_ids.append(cid)
        shot_bindings.append({"global_shot_id": gid, "visual_subject_ids": visible,
                              "no_visual_reference_ids": no_visual, "pack_ids": pack_ids})
    for entry in refs.get("props", []) or []:
        pid = entry.get("id") if isinstance(entry, dict) else entry
        if pid:
            want(str(pid), "prop")

    refmods = sorted((chosen[a] for a in order), key=lambda r: (_KIND_ORDER.get(r["kind"], 9), order.index(r["id"])))
    counters = {"Picture": 0, "Video": 0}
    for record in refmods:
        counters[record["tag"]] += 1
        record["label"] = f"<{record['tag']} {counters[record['tag']]}>"
    for level, message in provider_caps.pack_count_findings(caps, len(refmods), project_cap=pack_cap):
        (gaps if level == "error" else warnings).append(f"{seg_id} {message}")

    positions = data.get("positions") if data.get("positions") is not None else old.get("positions")
    validate_positions(seg_id, positions, warnings)
    segment: Dict[str, Any] = {
        "segment_id": seg_id, "source_layer2_path": _rel(root, path),
        "source_sha256": hashlib.sha256(raw).hexdigest(), "video_backend": "remix",
        "refmods": refmods, "shots": shot_bindings,
    }
    if waivers:
        segment["pack_waivers"] = waivers
    if positions is not None:
        segment["positions"] = positions
    return segment


def merge_existing_remix(generated: Dict[str, Any], old: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """remix 版保留手寫欄位，但拿掉 Ref2VA 專屬欄位（reference_paths 等）。"""
    if not old:
        return generated
    old = _strip_unused({k: v for k, v in old.items() if k not in REMIX_SEGMENT_DROP})
    old_shots = {s.get("global_shot_id"): s for s in old.get("shots", []) or [] if isinstance(s, dict)}
    merged = {**{k: v for k, v in old.items() if k not in REMIX_GENERATED_SEGMENT_KEYS}, **generated}
    merged["shots"] = [{**{k: v for k, v in old_shots.get(s["global_shot_id"], {}).items()
                           if k not in REMIX_GENERATED_SHOT_KEYS}, **s} for s in generated["shots"]]
    return merged


REMIX_GENERATED_SEGMENT_KEYS = {"segment_id", "source_layer2_path", "source_sha256", "video_backend",
                                "refmods", "pack_waivers", "positions", "shots"}
REMIX_GENERATED_SHOT_KEYS = {"global_shot_id", "visual_subject_ids", "no_visual_reference_ids", "pack_ids",
                             "reference_paths"}
# 從 ref2va 切到 remix 時，這些段層欄位沒有意義，直接丟掉
REMIX_SEGMENT_DROP = {"scene_reference"}


def merge_existing(generated: Dict[str, Any], old: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """保留手寫欄位：段層與鏡層都是「舊值為底、產生器擁有的欄位覆蓋」。"""
    if not old:
        return generated
    old_shots = {s.get("global_shot_id"): s for s in old.get("shots", []) or [] if isinstance(s, dict)}
    merged = {**{k: v for k, v in old.items() if k not in GENERATED_SEGMENT_KEYS and k not in REF2VA_SEGMENT_DROP},
              **generated}
    merged["shots"] = [{**{k: v for k, v in old_shots.get(s["global_shot_id"], {}).items()
                           if k not in GENERATED_SHOT_KEYS and k not in REF2VA_SHOT_DROP}, **s}
                       for s in generated["shots"]]
    return merged


# 從 remix 切回 ref2va 時，remix 專屬欄位要拿掉；留著的話編譯器看到 refmods 會當成 remix 綁定而拒絕編譯。
# positions 兩個 backend 的站位閘門都用，保留。
REF2VA_SEGMENT_DROP = {"video_backend", "refmods", "pack_waivers"}
REF2VA_SHOT_DROP = {"pack_ids"}
REF2VA_TOP_DROP = ("segments", "packs", "video_backend")


# 產生器擁有的欄位：重產時一律以新值為準（沒產出就是刪除），避免舊的 face／anchor 名單殘留互相衝突。
GENERATED_SEGMENT_KEYS = {"segment_id", "source_layer2_path", "source_sha256", "scene_reference", "shots"}
GENERATED_SHOT_KEYS = {"global_shot_id", "reference_paths", "visual_subject_ids", "no_visual_reference_ids",
                       "face_subject_ids", "identity_anchor_ids"}


def input_fingerprints(root: Path, paths: List[Path]) -> Dict[str, Optional[str]]:
    """綁定的輸入檔指紋（計畫表、逐鏡判讀、包計畫表、聖經）：改了這些也要重綁。檔案不存在記 None。"""
    out: Dict[str, Optional[str]] = {}
    for path in paths:
        try:
            key = path.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            key = str(path.resolve())
        out[key] = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
    return out


def inputs_stale(root: Path, recorded: Any) -> Optional[str]:
    if not isinstance(recorded, dict):
        return None  # 舊版綁定沒記輸入指紋：不追溯
    for key, sha in recorded.items():
        path = Path(key) if Path(key).is_absolute() else root / key
        now = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
        if now != sha:
            return f"{key} 在綁定後{'被刪除' if now is None else '新增' if sha is None else '修改'}"
    return None


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
    try:
        recorded = json.loads(bindings_path.read_text(encoding="utf-8-sig")).get("inputs_sha256")
    except (OSError, json.JSONDecodeError, AttributeError):
        recorded = None
    return inputs_stale(root, recorded)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="產生階段 5 video-bible.json／video-bindings.json（h3d bind）")
    ap.add_argument("--root", type=Path, default=Path("."))
    ap.add_argument("--bible", type=Path, default=None, help="預設 <root>/adapt/bible.json")
    ap.add_argument("--assets", type=Path, default=None, help="預設 <root>/assets.md")
    ap.add_argument("--plans", type=Path, default=None, help="預設 <root>/assets/character-reference-plans.json")
    ap.add_argument("--visibility", type=Path, default=None, help="預設 <root>/assets/face-visibility.json")
    ap.add_argument("--backend", choices=list(decisions_mod.VIDEO_BACKENDS), default=None,
                    help="影片生成路線；預設讀 decisions.json 的 video_backend（沒定案＝ref2va）")
    ap.add_argument("--packs", type=Path, default=None, help="remix 包計畫表，預設 <root>/assets/character-packs.json")
    args = ap.parse_args(argv)
    root = args.root.resolve()
    backend = args.backend or decisions_mod.video_backend(root)
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
    if backend == "remix":
        return _main_remix(args, root, registry, bible_path, layer2, old_bindings, old_by_id)
    gaps: List[str] = []
    segments = [build_segment(root, registry, plans, visibility, p, gaps) for p in layer2]
    if gaps:
        print(f"❌ 綁定缺 {len(dict.fromkeys(gaps))} 項，未寫入任何檔案：", file=sys.stderr)
        for gap in dict.fromkeys(gaps):
            print(f"  - {gap}", file=sys.stderr)
        return 1
    segments = [merge_existing(seg, old_by_id.get(seg["segment_id"])) for seg in segments]
    bible = video_bible(registry, _load_json(bible_path, {}))
    (root / "video-bible.json").write_text(json.dumps(bible, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    inputs = input_fingerprints(root, [bible_path, assets_path,
                                       args.plans or root / "assets" / "character-reference-plans.json",
                                       args.visibility or root / "assets" / "face-visibility.json"])
    payload = {**{k: v for k, v in old_bindings.items() if k not in REF2VA_TOP_DROP},
               "schema_version": "1.0-stage5-bindings", "derived_for": "Stage 5 compiler binding sidecar (h3d bind)",
               "inputs_sha256": inputs, "segments": segments}
    (root / "video-bindings.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    panels = sum(1 for s in segments for b in s["shots"] for g in b["reference_paths"].values()
                 for e in g if e.get("reference_view") == "panel")
    print(f"✅ 已寫 video-bible.json 與 video-bindings.json：{len(segments)} 段、"
          f"{sum(len(s['shots']) for s in segments)} 鏡、整板查表 {panels} 筆")
    return 0


def _main_remix(args: argparse.Namespace, root: Path, registry: AssetRegistry, bible_path: Path,
                layer2: List[Path], old_bindings: Dict[str, Any], old_by_id: Dict[str, Any]) -> int:
    pack_path = args.packs or root / "assets" / "character-packs.json"
    pack_plan = _load_json(pack_path, None)
    if not isinstance(pack_plan, dict):
        print(f"❌ video_backend=remix 需要包計畫表 {pack_path}"
              "（{\"packs\": {\"C-x\": {\"default\": \"<包名>\", \"tag\": \"Video\"}}}），未寫入任何檔案", file=sys.stderr)
        return 1
    caps = provider_caps.load_caps("remix")
    pack_cap = decisions_mod.remix_pack_cap(root)
    warnings: List[str] = []
    plan_hits: List[str] = []
    _unused_key_hits(pack_plan, pack_path.name, plan_hits)
    for hit in plan_hits:
        warnings.append(f"{hit}：remix 不使用（只在 ref2va 有意義）")
    gaps: List[str] = []
    segments = []
    for p in layer2:
        sid_guess = None
        try:
            raw_doc = json.loads(p.read_text(encoding="utf-8-sig"))
            # 與 build_segment_remix 同一規則，否則沒有 segment_id 的段找不到舊綁定、手寫欄位會遺失
            sid_guess = str(raw_doc.get("segment_id") or raw_doc.get("scene_id") or p.stem)
        except (OSError, json.JSONDecodeError, AttributeError):
            pass
        segments.append(build_segment_remix(root, registry, pack_plan, p, old_by_id.get(sid_guess), gaps,
                                            warnings, caps, pack_cap))
    for warning in dict.fromkeys(warnings):
        print(f"⚠️ {warning}", file=sys.stderr)
    if gaps:
        print(f"❌ remix 綁定缺 {len(dict.fromkeys(gaps))} 項，未寫入任何檔案：", file=sys.stderr)
        for gap in dict.fromkeys(gaps):
            print(f"  - {gap}", file=sys.stderr)
        return 1
    segments = [merge_existing_remix(seg, old_by_id.get(seg["segment_id"])) for seg in segments]
    bible = video_bible(registry, _load_json(bible_path, {}))
    (root / "video-bible.json").write_text(json.dumps(bible, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    payload = {**{k: v for k, v in old_bindings.items() if k not in ("segments", "packs", "video_backend")},
               "schema_version": "1.0-stage5-bindings", "derived_for": "Stage 5 compiler binding sidecar (h3d bind)",
               "video_backend": "remix", "packs": normalize_packs(pack_plan),
               "inputs_sha256": input_fingerprints(root, [bible_path, args.assets or root / "assets.md", pack_path]),
               "segments": segments}
    (root / "video-bindings.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"✅ 已寫 video-bible.json 與 video-bindings.json（remix）：{len(segments)} 段、"
          f"refmods 共 {sum(len(s['refmods']) for s in segments)} 個、豁免 {sum(len(s.get('pack_waivers') or []) for s in segments)} 筆")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
