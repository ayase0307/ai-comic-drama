#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""構圖板自動建議（W46，只建議）：判斷哪些段適合「以場景母片為底重畫的四格構圖板」，建議改用。

來源：老易空間邏輯實驗 2026-10 第二批（`docs/experiments/laoyi-spatial-2026-10/`），規則全文
`references/storyboard/spatial-consistency.md` §3。

證據等級（照實寫，**方向性、未達原定 +25 門檻**）：
  - 室內多人文戲、固定場景：以新母片為底重畫的四格板 D′ 可用 15/16（94%）vs 單用母片 A′ 6/8（75%）；
    座位錯、換牆、場景漂移皆 0；全部比 +19、同 seed 比 +25 壓線，正式判「未過」。
  - 近景看不到空間關係的鏡（S01-c：角落桌在門洞西側）只有 D′ 拉對（3/4），A′ 0/2。
  - 不以母片為底、自由畫風的板（第一批 D／E）：座位拉對，但把畫風帶進成片（深木牆、大理石、換牆）。
  - 武戲：沒有 D′ 的證據 → 不建議。單人、戶外長直線性鏡頭：實驗沒涵蓋 → 不建議。
  評分只有一人、每組文戲 8 段次、單一場景（自助餐店）、單一模型（H3 via REMIX）。

所以這裡只產「建議」（level＝suggestion）：**不擋送件、不擋核准、不改預設編譯**。資料不夠判斷時一律不建議（保守）。

觸發條件（全部成立才建議；判斷依據都是 Layer 2／segments 既有欄位）：
  1. 不是武戲：沒有任何鏡 `dramatic_beat_type == "Combat_Impact"`、段落沒有自動推導的 `h3_loras`、
     動作欄（action_stages／action_stages_en）沒有明確打鬥詞。
  2. 段落綁在已驗收的場景母片：
     - 已編譯段（segments）：`reference_images` 有 `type: scene`（remix：`refmods` 有 `kind: scene`）——能編譯代表
       階段 4 已核准、母片已綁；給了專案根時另查圖檔存在。
     - Layer 2（階段 4，未編譯）：`asset_refs.scene_id` 找得到母片圖，且階段 2 已核准（`project_state.is_approved(root, 2)`）；
       沒有專案根或沒有狀態檔 → 判不了，不建議。
  3. 室內：段落 `metadata.interior`，否則從 `handoff*.json` 的場景 `setting.interior`／`int_ext`（內／外、INT／EXT）找；
     判不出內外景 → 不建議；戶外 → 不建議。
  4. 畫面上 ≥2 名具名角色（各鏡 `character_ids`／`visual_subject_ids` 聯集，排除 S-／P-／EXTRAS-／V- 前綴）。
  5. 有固定座位／站位：段落 `positions`、任一鏡 `spatial_blocking.anchor_objects` 非空，或
     `style_lock.continuity_anchors.blocking`／`axis`、各鏡 `blocking_desc` 寫到座位／桌／櫃檯／站在…。
  6. 段內有近景或特寫（`camera_optics.shot_size` ∈ MCU／CU／ECU／OTS_CU）——景別裝不下門洞、桌位這類定位結構
     （這是代理判斷：近景鏡頭若其實看得到定位結構，寫 `staging_waivers` 豁免即可）。
  7. 文戲：至少一鏡有台詞（`dialogue_and_audio.has_dialogue` 或 `line_verbatim` 非空）。
  8. 沒有已經在用的板：場景參考沒有宣告 `reference_view: "panel"`。

擴充：每條建議是 `RULES` 裡的一個 `BoardRule`（代碼、標題、證據、`check(features)`、`message(features)`）。
九宮格（3×3）規則另案測試中，**這裡刻意不寫**；有數據後新增一個 BoardRule、配新的 W 代碼即可，特徵抽取共用。

豁免／不採用：段落 `metadata.staging_waivers`（或段層 `staging_waivers`）寫 `{"code": "W46", "reason": "…", "quote": "<使用者原話>"}`。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

HERE = Path(__file__).resolve().parent
for _p in (str(HERE), str(HERE.parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

SPEC_REF = "references/storyboard/spatial-consistency.md §3"
CLOSE_SIZES = ("MCU", "CU", "ECU", "OTS_CU")
NON_CHARACTER_PREFIXES = ("S-", "P-", "EXTRAS-", "V-", "SC-", "PROP-")

COMBAT_WORDS = re.compile(
    r"\b(?:punch\w*|kick\w*|strik\w*|slash\w*|stab\w*|parr\w*|dodg\w*|fight\w*|combat|brawl\w*|grappl\w*|"
    r"swings?\s+(?:a|the|his|her|their)\s+(?:sword|blade|fist|stool|chair|club|bat|axe)|"
    r"blocks?\s+the\s+(?:blow|strike|punch)|lunges?\s+at|tackl\w*|uppercut|headbutt\w*)\b"
    r"|打鬥|搏鬥|出拳|揮拳|飛踢|踢向|揮刀|砍向|劈向|格擋|閃躲|撲殺|撲向|鬥毆|過招|交手",
    re.I)
SEAT_WORDS = re.compile(
    r"坐|座位|桌|櫃檯|吧檯|檯前|站在|站於|窗邊|角落|門邊|靠牆"
    r"|\b(?:seated|sits?|sitting|table|booth|counter|bar\s+stool|stool|desk|stands?\s+(?:at|by|behind|beside)|"
    r"standing\s+(?:at|by|behind|beside))\b",
    re.I)


# ---------------------------------------------------------------------------
# 特徵
# ---------------------------------------------------------------------------
@dataclass
class Features:
    segment_id: str
    source: str  # "segment"（已編譯）或 "layer2"
    scene_id: str = ""
    combat: bool = False
    combat_why: List[str] = field(default_factory=list)
    scene_master: Optional[bool] = None  # 有綁／找得到母片
    master_accepted: Optional[bool] = None  # 母片已驗收；None＝判不了
    interior: Optional[bool] = None
    characters: List[str] = field(default_factory=list)
    fixed_positions: bool = False
    fixed_why: str = ""
    close_shots: List[Tuple[str, str]] = field(default_factory=list)  # (shot_id, shot_size)
    dialogue: bool = False
    board_in_use: bool = False
    n_shots: int = 0

    def as_dict(self) -> Dict[str, Any]:
        return {k: (list(v) if isinstance(v, tuple) else v) for k, v in self.__dict__.items()}


def _meta(seg: Dict[str, Any]) -> Dict[str, Any]:
    return seg.get("metadata") or {}


def _shots(seg: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [s for s in seg.get("shots") or [] if isinstance(s, dict)]


def _is_character_id(asset_id: str) -> bool:
    up = asset_id.upper()
    return bool(asset_id) and not any(up.startswith(p) for p in NON_CHARACTER_PREFIXES)


def _texts(value: Any) -> List[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value if isinstance(v, (str, int, float))]
    return []


def _interior_from_setting(rec: Dict[str, Any]) -> Optional[bool]:
    setting = rec.get("setting") if isinstance(rec.get("setting"), dict) else {}
    if isinstance(setting.get("interior"), bool):
        return setting["interior"]
    if isinstance(rec.get("interior"), bool):
        return rec["interior"]
    ie = str(rec.get("int_ext") or setting.get("int_ext") or "").strip()
    if not ie:
        return None
    has_in = bool(re.search(r"內|内|\bINT\b", ie, re.I))
    has_out = bool(re.search(r"外|\bEXT\b", ie, re.I))
    if has_in and not has_out:
        return True
    if has_out and not has_in:
        return False
    return None  # 內外景混合（INT/EXT）→ 判不了


# ---------------------------------------------------------------------------
# 專案脈絡（只讀；判不了的就留 None）
# ---------------------------------------------------------------------------
def load_context(root: Optional[Path]) -> Dict[str, Any]:
    """{"root", "stage2_approved": bool|None, "scenes_interior": {scene_id: bool}, "master_paths": {scene_id: Path|None}}。"""
    ctx: Dict[str, Any] = {"root": None, "stage2_approved": None, "scenes_interior": {}, "master_paths": {}}
    if root is None:
        return ctx
    root = Path(root)
    ctx["root"] = root
    try:
        import project_state as ps
        if ps.state_path(root).is_file():
            ctx["stage2_approved"] = bool(ps.is_approved(root, 2))
    except Exception:  # pragma: no cover - 狀態檔壞掉就當判不了
        ctx["stage2_approved"] = None
    for path in sorted(list(root.glob("handoff*.json")) + list(root.glob("adapt/handoff*.json"))):
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception:
            continue
        stack = [data]
        while stack:
            obj = stack.pop()
            if isinstance(obj, dict):
                sid = obj.get("scene_id")
                if isinstance(sid, str) and ("setting" in obj or "int_ext" in obj or "interior" in obj):
                    val = _interior_from_setting(obj)
                    if val is not None:
                        ctx["scenes_interior"].setdefault(sid, val)
                stack.extend(v for v in obj.values() if isinstance(v, (dict, list)))
            elif isinstance(obj, list):
                stack.extend(v for v in obj if isinstance(v, (dict, list)))
    return ctx


def _master_path(ctx: Dict[str, Any], location_id: str) -> Optional[Path]:
    root = ctx.get("root")
    if root is None or not location_id:
        return None
    cache = ctx.setdefault("master_paths", {})
    if location_id in cache:
        return cache[location_id]
    found: Optional[Path] = None
    loc: Dict[str, Any] = {}
    bp = Path(root) / "adapt" / "bible.json"
    if bp.is_file():
        try:
            bible = json.loads(bp.read_text(encoding="utf-8-sig"))
            for rec in bible.get("locations") or []:
                if isinstance(rec, dict) and str(rec.get("location_id") or rec.get("id") or "") == location_id:
                    loc = rec
                    break
        except Exception:
            loc = {}
    rel = None
    try:
        import build_stage_review as bsr  # 與階段 2／4 審核頁同一套母片路徑判斷
        rel = bsr.scene_master_image(Path(root), loc, location_id)
    except Exception:
        explicit = loc.get("reference_image") or loc.get("image_path") or loc.get("image_file")
        rel = explicit or f"images/{location_id}.png"
    cand = Path(rel) if Path(rel).is_absolute() else Path(root) / str(rel)
    if cand.is_file():
        found = cand
    cache[location_id] = found
    return found


# ---------------------------------------------------------------------------
# 抽特徵
# ---------------------------------------------------------------------------
def extract_features(seg: Dict[str, Any], ctx: Optional[Dict[str, Any]] = None) -> Features:
    ctx = ctx or load_context(None)
    meta = _meta(seg)
    shots = _shots(seg)
    compiled = bool(seg.get("h3_prompt") or seg.get("reference_images") is not None or seg.get("refmods") is not None)
    f = Features(segment_id=str(seg.get("segment_id") or seg.get("id") or "segment"),
                 source="segment" if compiled else "layer2", scene_id=str(seg.get("scene_id") or ""),
                 n_shots=len(shots))

    # 1. 武戲
    for sh in shots:
        if sh.get("dramatic_beat_type") == "Combat_Impact":
            f.combat_why.append(f"{sh.get('shot_id') or '?'} Combat_Impact")
        ap = sh.get("action_and_performance") or {}
        text = " ".join(_texts(ap.get("action_stages_en")) + _texts(ap.get("action_stages")))
        m = COMBAT_WORDS.search(text)
        if m:
            f.combat_why.append(f"{sh.get('shot_id') or '?'} 動作欄「{m.group(0)}」")
    if seg.get("h3_loras"):
        f.combat_why.append("段落有自動推導的 h3_loras（只有 Combat_Impact 段會推導）")
    f.combat = bool(f.combat_why)

    # 2. 場景母片
    scene_refs = [r for r in seg.get("reference_images") or [] if isinstance(r, dict) and r.get("type") == "scene"]
    scene_refs += [r for r in seg.get("refmods") or [] if isinstance(r, dict) and r.get("kind") == "scene"]
    f.board_in_use = any(r.get("reference_view") == "panel" for r in scene_refs)
    root = ctx.get("root")
    if compiled:
        if scene_refs:
            exists = True
            if root is not None:
                paths = [r.get("path") for r in scene_refs if r.get("path")]
                if paths:
                    exists = any((Path(p) if Path(p).is_absolute() else Path(root) / p).is_file() for p in paths)
            f.scene_master = exists
            # 能編譯＝階段 4 已核准（其前提是母片已綁）；有狀態檔且階段 2 明確未核准時以狀態檔為準
            f.master_accepted = exists and ctx.get("stage2_approved") is not False
        else:
            f.scene_master = False
            f.master_accepted = False
    else:
        loc_id = str((seg.get("asset_refs") or {}).get("scene_id") or "")
        if root is None or not loc_id:
            f.scene_master = None
            f.master_accepted = None
        else:
            f.scene_master = _master_path(ctx, loc_id) is not None
            approved = ctx.get("stage2_approved")
            f.master_accepted = (f.scene_master and approved) if approved is not None else None

    # 3. 室內
    if isinstance(meta.get("interior"), bool):
        f.interior = meta["interior"]
    else:
        interiors = ctx.get("scenes_interior") or {}
        for key in (seg.get("source_scene_id"), seg.get("scene_id"), meta.get("source_scene_id")):
            if key and key in interiors:
                f.interior = interiors[key]
                break

    # 4. 角色
    chars: List[str] = []
    for sh in shots:
        for cid in list(sh.get("visual_subject_ids") or []) + list(sh.get("character_ids") or []):
            cid = str(cid)
            if _is_character_id(cid) and cid not in chars:
                chars.append(cid)
    f.characters = chars

    # 5. 固定座位／站位
    if seg.get("positions"):
        f.fixed_positions, f.fixed_why = True, "positions"
    else:
        for sh in shots:
            if (sh.get("spatial_blocking") or {}).get("anchor_objects"):
                f.fixed_positions, f.fixed_why = True, f"{sh.get('shot_id') or '?'} anchor_objects"
                break
    if not f.fixed_positions:
        anchors = ((seg.get("style_lock") or {}).get("continuity_anchors") or {})
        if not anchors:
            anchors = ((meta.get("style_lock") or {}).get("continuity_anchors") or {}) if isinstance(meta.get("style_lock"), dict) else {}
        pool = [("continuity_anchors.blocking", anchors.get("blocking")), ("continuity_anchors.axis", anchors.get("axis"))]
        pool += [(f"{sh.get('shot_id') or '?'} blocking_desc", (sh.get("spatial_blocking") or {}).get("blocking_desc"))
                 for sh in shots]
        for where, text in pool:
            if isinstance(text, str) and SEAT_WORDS.search(text):
                f.fixed_positions, f.fixed_why = True, where
                break

    # 6. 近景／特寫
    for sh in shots:
        size = str((sh.get("camera_optics") or {}).get("shot_size") or "").strip().upper().replace("-", "_")
        if size in CLOSE_SIZES:
            f.close_shots.append((str(sh.get("shot_id") or "?"), size))

    # 7. 文戲（有台詞）
    for sh in shots:
        da = sh.get("dialogue_and_audio") or {}
        if da.get("has_dialogue") or str(da.get("line_verbatim") or "").strip():
            f.dialogue = True
            break
    return f


# ---------------------------------------------------------------------------
# 規則
# ---------------------------------------------------------------------------
@dataclass
class BoardRule:
    rule_id: str
    code: str
    title: str
    evidence: str
    check: Callable[[Features], Tuple[bool, List[str]]]  # (命中, 未命中原因)
    message: Callable[[Features], str]


def _check_master_four_panel(f: Features) -> Tuple[bool, List[str]]:
    why: List[str] = []
    if f.combat:
        why.append("武戲（" + "；".join(f.combat_why[:2]) + "）：四格板沒有武戲證據")
    if f.master_accepted is None:
        why.append("判不了場景母片是否已驗收（Layer 2 需專案根＋階段 2 核准狀態）")
    elif not f.master_accepted:
        why.append("沒有已驗收的場景母片" if not f.scene_master else "場景母片未驗收（階段 2 未核准）")
    if f.interior is None:
        why.append("判不了內外景（metadata.interior 或 handoff setting.interior／int_ext）")
    elif not f.interior:
        why.append("戶外場景：實驗只涵蓋室內固定場景")
    if len(f.characters) < 2:
        why.append(f"畫面上具名角色 {len(f.characters)} 名（需 ≥2）")
    if not f.fixed_positions:
        why.append("看不出固定座位／站位（positions、anchor_objects、blocking 都沒有）")
    if not f.close_shots:
        why.append("沒有近景／特寫鏡（MCU／CU／ECU／OTS_CU）")
    if not f.dialogue:
        why.append("沒有台詞（不是文戲）")
    if f.board_in_use:
        why.append("場景參考已宣告 reference_view: panel（已在用板）")
    return (not why), why


def _message_master_four_panel(f: Features) -> str:
    shots = "、".join(f"{sid}（{size}）" for sid, size in f.close_shots[:4])
    return (
        f"室內固定場景 {f.scene_id or '—'}、已驗收母片、{len(f.characters)} 名角色有固定座位／站位（{f.fixed_why}）、"
        f"近景 {shots} 看不到門洞／桌位這類定位結構、文戲 → 建議本段改用「以場景母片為底重畫的四格構圖板」。"
        f"理由（老易實驗第二批，方向性、未達 +25 門檻）：D′ 可用 15/16（94%）vs 單用母片 A′ 6/8（75%），座位錯／換牆／場景漂移 0；"
        f"近景看不到空間關係的鏡（S01-c）只有 D′ 拉對。做法：板一律以已驗收母片（＋派生視角）為底重畫，板提示詞寫店感鎖"
        f"（牆面材質／顏色、桌面材質、整體色溫各一句正面＋一句不要什麼）；不要讓生圖模型自由畫，自由畫風會把畫風帶進成片"
        f"（換牆、深木、大理石）。整板當參考時須宣告 reference_view: \"panel\"＋panel_label_en（consistency.md §7.4）。"
        f"見 {SPEC_REF}。只建議，不擋送件；不採用請寫 staging_waivers（code W46＋使用者原話）。"
    )


MASTER_FOUR_PANEL = BoardRule(
    rule_id="master_four_panel",
    code="W46",
    title="建議改用母片底四格構圖板",
    evidence="老易空間實驗第二批 D′ 15/16 vs A′ 6/8（方向性、未達 +25 門檻；武戲無證據）",
    check=_check_master_four_panel,
    message=_message_master_four_panel,
)

# 新規則（例如九宮格，另案測試中）有數據後加在這裡，配新的 W 代碼；本檔其他地方不用改。
RULES: List[BoardRule] = [MASTER_FOUR_PANEL]
CODES = tuple(r.code for r in RULES)
TITLES = {r.code: r.title for r in RULES}


def _waived(seg: Dict[str, Any]) -> set:
    out = set()
    for item in list(_meta(seg).get("staging_waivers") or []) + list(seg.get("staging_waivers") or []):
        if isinstance(item, dict) and item.get("code") and str(item.get("quote") or "").strip():
            out.add(str(item["code"]).upper())
    return out


def advise_segment(seg: Dict[str, Any], ctx: Optional[Dict[str, Any]] = None, root: Optional[Path] = None,
                   explain: bool = False, honor_waivers: bool = True) -> List[Dict[str, Any]]:
    """回傳建議：[{code, level: "suggestion", rule, segment_id, message, features?, misses?}]。

    explain=True 時連沒命中的規則也回傳（`hit: False`＋misses），方便除錯；預設只回傳命中的。"""
    if ctx is None:
        ctx = load_context(root)
    feats = extract_features(seg, ctx)
    waived = _waived(seg) if honor_waivers else set()
    out: List[Dict[str, Any]] = []
    for rule in RULES:
        hit, misses = rule.check(feats)
        if hit and rule.code in waived:
            continue
        if not hit and not explain:
            continue
        item: Dict[str, Any] = {"code": rule.code, "level": "suggestion", "rule": rule.rule_id, "hit": hit,
                                "segment_id": feats.segment_id, "title": rule.title}
        if hit:
            item["message"] = f"[{rule.code}: {rule.title}] {feats.segment_id}：{rule.message(feats)}"
        if explain:
            item["misses"] = misses
            item["features"] = feats.as_dict()
        out.append(item)
    return out


def advise_layer2_files(root: Path, files: Optional[Iterable[Path]] = None,
                        explain: bool = False) -> List[Dict[str, Any]]:
    """階段 4 用：對 layer2/layer2-*.json 跑建議（審核頁與 `h3d staging --layer2`）。"""
    root = Path(root)
    paths = list(files) if files is not None else sorted((root / "layer2").glob("layer2-*.json"))
    ctx = load_context(root)
    rows: List[Dict[str, Any]] = []
    for path in paths:
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        except Exception:
            continue
        segs = data if isinstance(data, list) else data.get("segments", [data]) if isinstance(data, dict) else []
        for seg in segs:
            if not isinstance(seg, dict):
                continue
            seg.setdefault("segment_id", Path(path).stem.replace("layer2-", ""))
            rows.extend(advise_segment(seg, ctx, explain=explain))
    return rows


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="構圖板自動建議（W46，只建議、不擋）：哪些段適合以場景母片為底重畫的四格構圖板")
    ap.add_argument("files", nargs="*", type=Path, help="layer2 或 segments JSON（預設 <root>/layer2/layer2-*.json）")
    ap.add_argument("--root", type=Path, default=Path("."))
    ap.add_argument("--explain", action="store_true", help="連沒命中的段也列出未命中原因")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    root = args.root.resolve()
    rows = advise_layer2_files(root, [p if p.is_absolute() else root / p for p in args.files] or None, args.explain)
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        for r in rows:
            if r["hit"]:
                print(f"💡 {r['message']}")
            else:
                print(f"·  {r['segment_id']}：不建議（{'；'.join(r.get('misses') or [])}）")
        print(f"構圖板建議：{sum(1 for r in rows if r['hit'])} 段")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
