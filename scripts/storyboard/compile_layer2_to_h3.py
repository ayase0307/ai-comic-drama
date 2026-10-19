#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
compile_layer2_to_h3.py — Layer 2 分鏡轉 H3 官方六段式 Prompt 與分段對帳 JSON 批次編譯器
（支援《噩盡島》實戰五大定案：7–10s 分段、獨立 Ref2VA、防角色同質化混臉、H3 官方六段式與 P0 確定性對帳）

功能：
1. 讀取一至多個 Layer 2 分鏡 JSON（支援目錄或多檔案），依集與場序批次編譯。
2. 結合 bible.json 與/或 assets.md 解析角色、妖物、場景底圖的圖片路徑與中英文外貌錨點。
3. 嚴格輸出符合 audit_refs_and_segments.py 13 條規則的 H3 官方六段式結構：
   - subject_definitions: (<Picture 1> 為場景，<Subject k> 嚴格對應 <Picture k+1>)
   - summary: (時長、鏡數、主體動作與情緒)
   - retention_analysis: (四大連戲錨點、妖物純灰底三視圖防染色聲明)
   - detailed_description: (無時間戳首鏡、官方運鏡詞、then/as 時間推進、光源名詞、動作力學、台詞與閉唇鎖)
   - overall_soundscape: (環境音與擬音)
   - non_diegetic_music: (氛圍配樂)
4. 僅在含 Combat_Impact 鏡頭的段落呼叫 auto_adapt_h3_loras 推導 FreeVideo LoRA（文戲不掛 LoRA）。
   畫風取自 style_lock.anchor / assets.md style_anchor；動作優先讀 action_stages_en / observable_expression_en。
5. 輸出 prompts-epXX.md（Markdown 提示詞包）與 segments-epXX.json（供 P0 稽核對帳）。
6. 支援 --check 自動執行雙重審查（--audit-refs + --lint-h3）。

零外部依賴，僅使用 Python 標準庫。全程使用繁體中文。
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import os
import pathlib
import re
import sys
from typing import Any, Dict, List, Optional, Tuple

# 確保 Windows 終端輸出 UTF-8
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

CURRENT_DIR = pathlib.Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))
SCRIPTS_DIR = CURRENT_DIR.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
from project_state import require_approved, stage4_artifacts, stage_snapshot

from audit_refs_and_segments import (
    COMPOUND_CAMERA_MOTIONS,
    LIGHT_SOURCE_TERMS,
    OFFICIAL_CAMERA_MOTIONS,
    REQUIRED_SECTIONS,
    audit_refs_and_subjects,
    effective_duration,
    frames_for,
    lint_h3_prompt,
)
from director_storyboard_assistant import (
    auto_adapt_h3_loras,
    palette_names,
    strip_hex,
)
from handoff_to_skeleton import segment_sort_key
from speech_utils import count_speech_chars, normalize_speech


# ==============================================================================
# 官方運鏡動詞標準庫與智慧映射
# ==============================================================================

MOTION_SYNONYMS = {
    "static": "holds a steady static shot",
    "固定": "holds a steady static shot",
    "靜態": "holds a steady static shot",
    "pan_left": "camera pans left",
    "pans left": "camera pans left",
    "pan left": "camera pans left",
    "左搖": "camera pans left",
    "pan_right": "camera pans right",
    "pans right": "camera pans right",
    "pan right": "camera pans right",
    "右搖": "camera pans right",
    "tilt_up": "camera tilts up",
    "tilts up": "camera tilts up",
    "tilt up": "camera tilts up",
    "上仰": "camera tilts up",
    "tilt_down": "camera tilts down",
    "tilts down": "camera tilts down",
    "tilt down": "camera tilts down",
    "下俯": "camera tilts down",
    "dolly_in": "camera dollies in",
    "dollies in": "camera dollies in",
    "dolly in": "camera dollies in",
    "push": "camera dollies in",
    "推鏡": "camera dollies in",
    "dolly_out": "camera dollies out",
    "dollies out": "camera dollies out",
    "dolly out": "camera dollies out",
    "pull": "camera dollies out",
    "拉鏡": "camera dollies out",
    "truck_left": "camera trucks left",
    "trucks left": "camera trucks left",
    "truck left": "camera trucks left",
    "左移": "camera trucks left",
    "truck_right": "camera trucks right",
    "trucks right": "camera trucks right",
    "truck right": "camera trucks right",
    "右移": "camera trucks right",
    "orbit": "camera trucks left while panning right",
    "環繞": "camera trucks left while panning right",
    "360": "camera trucks left while panning right",
}

# Exact natural-language phrases already used in approved Layer 2 files.
# These map only their stated camera intent to the nearest supported H3 verb;
# unrecognized phrases still fail closed below.
SOURCE_CAMERA_MOTION_ALIASES = {
    "locked tripod": "static",
    "locked side camera": "static",
    "locked camera as frame falls to black": "static",
    "locked side camera with downward follow": "tilts down",
    "slow pan following uncle's turn": "pans right",
    "tilt from sun to luo": "tilts down",
    "tilt up with the rising glow": "tilts up",
    "tilt with beast's head movement": "tilts up",
    "輕微穩定推近，保持單一主體": "dollies in",
    "穩定的小幅推近，保持床軸同側": "dollies in",
    "固定機位或沿南側短距離平移，禁止越過走廊軸線": "static",
    "固定機位，僅微幅跟隨手部動作": "static",
    "固定建立鏡位後小幅推近說話者": "dollies in",
    "固定貼近牆面，不越過南側機位": "static",
    "固定中景，留出字卡與空桌椅": "static",
    "車內固定機位，隨車身可見地微震": "static",
    "後座視點固定，輕微前移": "dollies in",
    "穩定短推或定鏡，依台詞視線切主體": "static",
    "穩定側向滑移，將右側海景留在視線方向": "trucks right",
    "由右向左短跟拍洛年，保持南側軸線": "trucks left",
    "由司機背影緩慢移向遠海，保持橋欄水平": "pans right",
}

DEFAULT_LIGHT_SOURCES = [
    "natural warm daylight and soft ambient illumination",
    "cold moonlight and dim fluorescent light",
    "ambient streetlamp glow and soft rim light",
    "dim interior lantern light and shadows",
]


# ==============================================================================
# 資產解析模組（Bible / Assets）
# ==============================================================================

NARRATOR_IDS = {"旁白", "narrator", "narration", "v.o.", "vo", "os", "o.s.", "畫外音", "旁白（v.o.）"}
CJK_RE = re.compile(r"[\u4e00-\u9fff]")
TODO_RE = re.compile(r"^\[?TODO\]?[:：]?")
CAMERA_HOLD_ACTION_RE = re.compile(
    r"^(\s*(?:Stage\s+\d+\s*:\s*)?)The camera holds on (.+?)[.!]?$",
    re.IGNORECASE,
)


def normalize_authored_camera_hold_action(stage: str) -> str:
    """Keep a stated held composition without duplicating the camera clause."""
    match = CAMERA_HOLD_ACTION_RE.match(stage.strip())
    if not match:
        return stage
    prefix, subject = match.groups()
    subject = subject.rstrip(" .!")
    return f"{prefix}The view remains on {subject}."


SHEET_PHRASES_RE = re.compile(
    r",?\s*(?:on\s+)?(?:a\s+)?(?:neutral\s+)?(?:pure\s+)?(?:grey|gray|white)?\s*(?:studio\s+)?background"
    r"(?:\s+three-view)?(?:\s+(?:creature|character)\s+(?:sheet|turnaround))?"
    r"|,?\s*(?:three-view|turnaround|model sheet|character sheet|creature sheet)[^,]*",
    re.IGNORECASE,
)


def strip_sheet_phrases(desc: str) -> str:
    """設定板用語（純灰底、三視圖）只屬於出圖，不該進影片提示詞。"""
    return re.sub(r"\s*,\s*,", ",", SHEET_PHRASES_RE.sub("", desc or "")).strip(" ,")


def is_narrator(cid: Optional[str]) -> bool:
    if not cid:
        return True
    return cid.strip().lower() in NARRATOR_IDS or cid.strip().startswith("旁白")


def _clean(text: Optional[str]) -> str:
    if not text or "TODO" in str(text):
        return ""
    return str(text).strip()


class AssetRegistry:
    """角色／場景／道具登記簿。來源：bible.json（visual_prompt_en 等欄位）與 assets.md。

    assets.md 支援兩種寫法：
    1. 表格行：| C-xxx | 名字 | 英文描述 |
    2. repo 範本的卡片格式：
         ### C-xxx　名字
         - **固定描述片段**：`english prompt`
         - **服裝**：`W-xxx-01` `desc`；`W-xxx-02` `desc`
         - **服裝設定圖**：`W-xxx-02` `images/char-xxx-variant.png`
         - **設定圖**：`images/char-xxx.png`
       場景清單行：- `S-xxx` 名稱：`english prompt`　`images/S-xxx.png`
    圖片路徑一律相對於專案根目錄（project_root）。
    """

    def __init__(self, bible_path: Optional[pathlib.Path] = None, assets_path: Optional[pathlib.Path] = None,
                 project_root: Optional[pathlib.Path] = None):
        self.characters: Dict[str, Dict[str, Any]] = {}
        self.locations: Dict[str, Dict[str, Any]] = {}
        self.props: Dict[str, Dict[str, Any]] = {}
        self.bodydetails: Dict[str, Dict[str, Any]] = {}
        self.style: Dict[str, str] = {}
        self.id_aliases: Dict[str, str] = {}
        bible_path = pathlib.Path(bible_path) if bible_path else None
        assets_path = pathlib.Path(assets_path) if assets_path else None
        if project_root:
            self.project_root = pathlib.Path(project_root)
        elif assets_path:
            self.project_root = assets_path.resolve().parent
        else:
            self.project_root = pathlib.Path(".")

        if bible_path and bible_path.exists():
            self._load_bible(bible_path)
        if assets_path and assets_path.exists():
            self._load_assets_md(assets_path)

    # ---------- 路徑 ----------
    def _guess_img(self, kind: str, aid: str) -> str:
        base = aid[2:] if aid[:2] in ("C-", "S-", "P-") else aid
        candidates = {
            "character": [f"images/char-{base}.png", f"images/{aid}.png", f"images/creature-{base}.png",
                          f"assets/characters/{aid}.png"],
            "scene": [f"images/{aid}.png", f"images/scene-{base}.png", f"assets/scenes/{aid}.png"],
        }[kind]
        for c in candidates:
            if (self.project_root / c).exists():
                return c
        return candidates[0]

    def path_exists(self, rel: str) -> bool:
        return bool(rel) and (self.project_root / rel).exists()

    # ---------- bible ----------
    def _load_bible(self, path: pathlib.Path) -> None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"[警告] 讀取 bible.json 失敗: {exc}", file=sys.stderr)
            return
        for char in data.get("characters", []) or []:
            if not isinstance(char, dict):
                continue
            cid = char.get("id") or char.get("character_id") or char.get("name", "")
            if not cid:
                continue
            wardrobes = char.get("wardrobe_states") or char.get("wardrobes") or {}
            desc_en = char.get("visual_prompt_en") or char.get("appearance_en") or ""
            if desc_en and CJK_RE.search(desc_en):
                desc_en = ""
            self.characters[cid] = {
                "id": cid,
                "name": char.get("name", cid),
                "desc_en": desc_en,
                "short_en": char.get("short_en", ""),
                "desc_zh": char.get("appearance_zh") or char.get("description", ""),
                "ref_img": char.get("reference_image") or char.get("image_path") or "",
                "wardrobe_states": wardrobes if isinstance(wardrobes, dict) else {},
                "is_creature": bool(char.get("is_creature", False)) or cid.startswith("CREATURE"),
                "voice_only": bool(char.get("voice_only", False)),
                "no_visual_reference": bool(char.get("no_visual_reference", False)) or bool(char.get("voice_only", False)),
                "variants": char.get("variants") or char.get("visual_variants") or {},
            }
        for loc in data.get("locations", []) or []:
            if not isinstance(loc, dict):
                continue
            lid = loc.get("id") or loc.get("location_id") or loc.get("name", "")
            if not lid:
                continue
            desc_en = loc.get("visual_prompt_en") or loc.get("description_en") or ""
            self.locations[lid] = {
                "id": lid,
                "name": loc.get("name", lid),
                "desc_en": "" if CJK_RE.search(desc_en or "") else desc_en,
                "desc_zh": loc.get("description_zh") or loc.get("description", ""),
                "ref_img": loc.get("reference_image") or loc.get("image_path") or "",
            }
        aliases = data.get("id_aliases", {}) or {}
        if isinstance(aliases, dict):
            self.id_aliases = {str(alias): str(canonical) for alias, canonical in aliases.items()}
        for prop in data.get("props", []) or []:
            if not isinstance(prop, dict):
                continue
            pid = prop.get("id") or prop.get("prop_id")
            if pid:
                desc_en = prop.get("visual_prompt_en") or prop.get("desc_en") or prop.get("description_en") or ""
                self.props[pid] = {
                    "id": pid,
                    "name": prop.get("name", pid),
                    "desc_en": "" if CJK_RE.search(desc_en or "") else desc_en,
                    "ref_img": prop.get("reference_image") or prop.get("image_path") or "",
                }
        for detail in data.get("bodydetails", []) or []:
            if not isinstance(detail, dict):
                continue
            did = detail.get("id")
            if did:
                self.bodydetails[did] = {
                    "id": did, "name": detail.get("name", did),
                    "desc_en": detail.get("desc_en") or detail.get("visual_prompt_en") or "",
                    "ref_img": detail.get("reference_image") or detail.get("image_path") or "",
                    "source_id": detail.get("source_id", ""),
                }
        style = data.get("style", {}) or {}
        if isinstance(style, dict):
            for key in ("anchor", "negative", "lighting_lock_line"):
                value = style.get(key)
                if value:
                    mapped_key = {"anchor": "style_anchor", "negative": "style_negative"}.get(key, key)
                    self.style[mapped_key] = str(value)

    # ---------- assets.md ----------
    def _load_assets_md(self, path: pathlib.Path) -> None:
        try:
            content = path.read_text(encoding="utf-8")
        except Exception as exc:
            print(f"[警告] 讀取 assets.md 失敗: {exc}", file=sys.stderr)
            return
        tick = re.compile(r"`([^`]+)`")
        current: Optional[Dict[str, Any]] = None
        for raw in content.splitlines():
            line = raw.strip()
            # 風格錨點
            m = re.match(r"^-\s*\*\*(style_anchor|style_negative|lighting_lock_line)\*\*[：:]\s*`([^`]+)`", line)
            if m:
                self.style[m.group(1)] = m.group(2).strip()
                continue
            # 卡片標題
            m = re.match(r"^#{2,4}\s*((?:C|CREATURE)-[\w-]+|CREATURE-\d+)\s*[　\s]*(.*)$", line)
            if m:
                aid, name = m.group(1), re.sub(r"[（(].*?[)）]", "", m.group(2)).strip() or m.group(1)
                rec = self.characters.setdefault(aid, {
                    "id": aid, "name": name, "desc_en": "", "short_en": "", "desc_zh": "",
                    "ref_img": "", "wardrobe_states": {}, "is_creature": aid.startswith("CREATURE"),
                })
                rec.setdefault("name", name)
                current = rec
                continue
            if line.startswith("#"):
                current = None
            if current is not None and line.startswith("-"):
                label = re.match(r"^-\s*\*\*(.+?)\*\*[：:]", line)
                label = label.group(1) if label else ""
                ticks = tick.findall(line)
                if label.startswith("固定描述") and ticks and not current["desc_en"]:
                    current["desc_en"] = ticks[0].strip()
                elif label == "服裝" and ticks:
                    for i in range(0, len(ticks) - 1, 2):
                        if ticks[i].startswith("W-"):
                            current["wardrobe_states"].setdefault(ticks[i], {})["desc_en"] = ticks[i + 1]
                elif label.startswith("服裝設定圖") and ticks:
                    for i in range(0, len(ticks) - 1, 2):
                        if ticks[i].startswith("W-"):
                            current["wardrobe_states"].setdefault(ticks[i], {})["ref_img"] = ticks[i + 1]
                elif label.startswith("設定圖") and ticks and not current["ref_img"]:
                    current["ref_img"] = ticks[0].strip()
                elif label.startswith("簡稱") and ticks:
                    current["short_en"] = ticks[0].strip()
                continue
            # 場景清單行
            m = re.match(r"^-\s*`(S-[\w-]+)`\s*([^：:`]*)[：:]?\s*(.*)$", line)
            if m:
                lid, name, rest = m.group(1), m.group(2).strip(), m.group(3)
                ticks = tick.findall(rest)
                desc = next((t for t in ticks if not t.startswith("images/") and not t.endswith(".png")), "")
                img = next((t for t in ticks if t.endswith((".png", ".jpg", ".webp"))), "")
                rec = self.locations.setdefault(lid, {"id": lid, "name": name or lid, "desc_en": "", "desc_zh": "", "ref_img": ""})
                rec["desc_en"] = rec["desc_en"] or desc
                rec["ref_img"] = rec["ref_img"] or img
                continue
            # 表格行
            if line.startswith("|"):
                parts = [p.strip() for p in line.strip("|").split("|")]
                if len(parts) >= 3 and re.match(r"^(C|S|P|CREATURE)-", parts[0]):
                    aid, name, desc = parts[0], parts[1], parts[2].strip("`")
                    if aid.startswith(("C-", "CREATURE")):
                        rec = self.characters.setdefault(aid, {"id": aid, "name": name, "desc_en": "", "short_en": "",
                                                               "desc_zh": "", "ref_img": "", "wardrobe_states": {},
                                                               "is_creature": aid.startswith("CREATURE")})
                        rec["desc_en"] = rec["desc_en"] or desc
                    elif aid.startswith("S-"):
                        rec = self.locations.setdefault(aid, {"id": aid, "name": name, "desc_en": "", "desc_zh": "", "ref_img": ""})
                        rec["desc_en"] = rec["desc_en"] or desc
                    else:
                        self.props[aid] = {"id": aid, "name": name, "desc_en": desc}

    # ---------- 查詢 ----------
    def get_character(self, cid_or_name: str, wardrobe_state: Optional[str] = None) -> Dict[str, Any]:
        cid_or_name = self.id_aliases.get(cid_or_name, cid_or_name)
        found = None
        if cid_or_name in self.characters:
            found = dict(self.characters[cid_or_name])
        else:
            for k, v in self.characters.items():
                if cid_or_name.lower() == k.lower() or cid_or_name == v.get("name", ""):
                    found = dict(v)
                    break
        if not found:
            print(f"[警告] 角色 {cid_or_name} 未在 bible.json / assets.md 登記，提示詞將缺少外觀描述。", file=sys.stderr)
            found = {"id": cid_or_name, "name": cid_or_name, "desc_en": "", "short_en": "", "desc_zh": "",
                     "ref_img": "", "wardrobe_states": {}, "is_creature": False, "unregistered": True}
        found["wardrobe_states"] = dict(found.get("wardrobe_states") or {})
        if not found.get("ref_img") and not found.get("no_visual_reference"):
            found["ref_img"] = self._guess_img("character", found["id"])
        if wardrobe_state and wardrobe_state in found["wardrobe_states"]:
            w_val = found["wardrobe_states"][wardrobe_state]
            if isinstance(w_val, dict):
                if w_val.get("ref_img"):
                    found["ref_img"] = w_val["ref_img"]
                    found["wardrobe_has_own_image"] = True
                if w_val.get("desc_en"):
                    found["desc_en"] = f"{found['desc_en']}, wearing {w_val['desc_en']}" if found["desc_en"] else w_val["desc_en"]
            elif isinstance(w_val, str):
                found["ref_img"] = w_val
                found["wardrobe_has_own_image"] = True
        found["desc_en"] = strip_sheet_phrases(found.get("desc_en", ""))
        if not found.get("short_en"):
            # 從固定描述抽前段當作次要角色的短稱
            found["short_en"] = ", ".join((found.get("desc_en") or found["name"]).split(", ")[:3])
        return found

    def get_location(self, lid_or_name: str) -> Dict[str, Any]:
        rec = self.locations.get(lid_or_name)
        if not rec:
            for k, v in self.locations.items():
                if lid_or_name.lower() == k.lower() or lid_or_name == v.get("name", ""):
                    rec = v
                    break
        if not rec:
            print(f"[警告] 場景 {lid_or_name} 未登記，提示詞將缺少場景描述。", file=sys.stderr)
            rec = {"id": lid_or_name, "name": lid_or_name, "desc_en": "", "desc_zh": "", "ref_img": "", "unregistered": True}
        rec = dict(rec)
        if not rec.get("ref_img"):
            rec["ref_img"] = self._guess_img("scene", rec["id"])
        if not rec.get("desc_en"):
            rec["desc_en"] = "the location shown in the reference plate"
        return rec

    def get_prop(self, pid: str) -> Dict[str, Any]:
        pid = self.id_aliases.get(pid, pid)
        rec = self.props.get(pid)
        if not rec:
            raise ValueError(f"Stage5 binding prop {pid!r} is not registered in the normalized Bible")
        result = dict(rec)
        if not result.get("ref_img"):
            raise ValueError(f"Stage5 binding prop {pid!r} has no approved reference_image")
        if not result.get("desc_en"):
            raise ValueError(f"Stage5 binding prop {pid!r} has no English visual description")
        return result

    def get_bodydetail(self, did: str) -> Dict[str, Any]:
        did = self.id_aliases.get(did, did)
        rec = self.bodydetails.get(did)
        if not rec:
            raise ValueError(f"Stage5 binding bodydetail {did!r} is not registered in the normalized Bible")
        result = dict(rec)
        if not result.get("ref_img"):
            raise ValueError(f"Stage5 binding bodydetail {did!r} has no approved reference_image")
        return result


def validate_stage5_binding(
    layer2_data: Dict[str, Any], binding: Dict[str, Any], layer2_path: pathlib.Path,
    project_root: pathlib.Path,
) -> Dict[str, Any]:
    """Verify a derived Stage5 binding against one immutable Layer2 source file."""
    if not isinstance(binding, dict):
        raise ValueError("Stage5 segment binding must be an object")
    segment_id = str(layer2_data.get("segment_id") or layer2_data.get("scene_id") or "")
    if binding.get("segment_id") != segment_id:
        raise ValueError(f"Stage5 segment_id mismatch: {binding.get('segment_id')!r} != {segment_id!r}")
    source = binding.get("source_layer2_path")
    if not isinstance(source, str) or not source:
        raise ValueError(f"Stage5 binding {segment_id} is missing source_layer2_path")
    source_path = pathlib.Path(source)
    if source_path.is_absolute():
        raise ValueError(f"Stage5 source_layer2_path must be project-relative: {source}")
    try:
        expected = (pathlib.Path(project_root) / source_path).resolve().relative_to(pathlib.Path(project_root).resolve()).as_posix()
        actual = pathlib.Path(layer2_path).resolve().relative_to(pathlib.Path(project_root).resolve()).as_posix()
    except ValueError as exc:
        raise ValueError(f"Stage5 Layer2 source path escapes project root: {source}") from exc
    if os.path.normcase(expected) != os.path.normcase(actual):
        raise ValueError(f"Stage5 source path mismatch: binding={expected!r}, input={actual!r}")
    expected_sha = str(binding.get("source_sha256") or "").lower()
    actual_sha = hashlib.sha256(pathlib.Path(layer2_path).read_bytes()).hexdigest()
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha) or expected_sha != actual_sha:
        raise ValueError(f"Stage5 source SHA256 mismatch for {segment_id}: expected {expected_sha or '<missing>'}, got {actual_sha}")
    shot_ids = [str(shot.get("global_shot_id") or "") for shot in (layer2_data.get("shots", []) or [])]
    if any(not sid for sid in shot_ids):
        raise ValueError(f"Stage5 binding requires global_shot_id on every shot in {segment_id}")
    if len(shot_ids) != len(set(shot_ids)):
        raise ValueError(f"Layer2 contains duplicate global_shot_id in {segment_id}")
    known = set(shot_ids)
    for sid, override in (binding.get("shot_overrides", {}) or {}).items():
        if sid not in known:
            raise ValueError(f"Stage5 shot override does not resolve uniquely: {sid}")
        if not isinstance(override, dict) or set(override) - {"action_stages_en", "observable_expression_en"}:
            raise ValueError(f"Stage5 shot override {sid} may override only action_stages_en and observable_expression_en")
    seen_refs = set()
    for shot_binding in binding.get("shots", []) or []:
        if not isinstance(shot_binding, dict):
            raise ValueError(f"Stage5 shot binding in {segment_id} must be an object")
        sid = shot_binding.get("global_shot_id")
        if sid not in known or sid in seen_refs:
            raise ValueError(f"Stage5 reference binding global_shot_id is missing, unknown, or duplicated: {sid!r}")
        seen_refs.add(sid)
        if not isinstance(shot_binding.get("reference_paths", {}), dict):
            raise ValueError(f"Stage5 reference_paths for {sid} must be an object")
    if seen_refs != known:
        missing = sorted(known - seen_refs)
        raise ValueError(f"Stage5 bindings are missing per-shot reference mapping(s): {', '.join(missing)}")
    return binding


def apply_stage5_binding(layer2_data: Dict[str, Any], binding: Dict[str, Any]) -> Dict[str, Any]:
    """Apply permitted derived asset and English translation bindings in memory."""
    data = json.loads(json.dumps(layer2_data, ensure_ascii=False))
    refs = data.setdefault("asset_refs", {})
    overrides = binding.get("asset_refs_override", {}) or {}
    if not isinstance(overrides, dict):
        raise ValueError("Stage5 asset_refs_override must be an object")
    refs.update(json.loads(json.dumps(overrides, ensure_ascii=False)))
    metadata_override = binding.get("metadata_override", {}) or {}
    allowed_metadata = {"soundscape_en", "music_en", "lighting_lock_line"}
    if not isinstance(metadata_override, dict) or set(metadata_override) - allowed_metadata:
        raise ValueError("Stage5 metadata_override may contain only soundscape_en, music_en, and lighting_lock_line")
    if any(not isinstance(value, str) for value in metadata_override.values()):
        raise ValueError("Stage5 metadata_override values must be strings")
    data.setdefault("metadata", {}).update(metadata_override)
    if binding.get("scene_id"):
        refs["scene_id"] = binding["scene_id"]
    if binding.get("primary_character"):
        refs["primary_character"] = binding["primary_character"]
    shot_override_by_id = binding.get("shot_overrides", {}) or {}
    shot_ref_by_id = {s["global_shot_id"]: s for s in (binding.get("shots", []) or [])}
    source_shot_ids = [shot.get("global_shot_id") for shot in data.get("shots", []) or []]
    if len(source_shot_ids) != len(set(source_shot_ids)):
        raise ValueError("Layer2 has duplicate global_shot_id values")
    unknown_override_ids = set(shot_override_by_id) - set(source_shot_ids)
    unknown_ref_ids = set(shot_ref_by_id) - set(source_shot_ids)
    if unknown_override_ids or unknown_ref_ids:
        bad = sorted(unknown_override_ids | unknown_ref_ids)
        raise ValueError(f"Stage5 global_shot_id does not resolve uniquely: {', '.join(bad)}")
    for shot in data.get("shots", []) or []:
        sid = shot.get("global_shot_id")
        override = shot_override_by_id.get(sid, {})
        if set(override) - {"action_stages_en", "observable_expression_en"}:
            raise ValueError(f"Stage5 shot override {sid} may override only action_stages_en and observable_expression_en")
        if override:
            action = shot.setdefault("action_and_performance", {})
            for key, value in override.items():
                if key == "action_stages_en" and (not isinstance(value, list) or not all(isinstance(v, str) and v.strip() for v in value)):
                    raise ValueError(f"Stage5 {sid}.action_stages_en must be a nonempty string list")
                if key == "observable_expression_en" and not isinstance(value, str):
                    raise ValueError(f"Stage5 {sid}.observable_expression_en must be a string")
                action[key] = value
        if sid in shot_ref_by_id:
            shot["_stage5_reference_binding"] = shot_ref_by_id[sid]
    data["_stage5_binding"] = binding
    return data


def _stage5_reference_path_map(binding: Dict[str, Any]) -> Tuple[Dict[str, str], Optional[str], List[Dict[str, Any]], Optional[str]]:
    """Collect explicit per-shot paths; creature morphology variants remain shot-scoped."""
    paths: Dict[str, str] = {}
    scene_path: Optional[str] = None
    scene_description: Optional[str] = binding.get("scene_description_en")
    if binding.get("scene_reference"):
        scene_path = str(binding["scene_reference"])
    variants: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for shot_binding in binding.get("shots", []) or []:
        grouped = shot_binding.get("reference_paths", {}) or {}
        scene = grouped.get("scene")
        if isinstance(scene, str):
            candidate = scene
            if scene_path and scene_path != candidate:
                raise ValueError("Stage5 segment binds more than one scene reference path")
            scene_path = candidate
        elif isinstance(scene, list):
            for entry in scene:
                if isinstance(entry, dict) and entry.get("reference_image"):
                    candidate = entry["reference_image"]
                    if scene_path and scene_path != candidate:
                        raise ValueError("Stage5 segment binds more than one scene reference path")
                    scene_path = candidate
                    desc = entry.get("desc_en") or entry.get("description_en")
                    if desc:
                        if scene_description and scene_description != desc:
                            raise ValueError("Stage5 segment binds conflicting scene descriptions")
                        scene_description = desc
        for group in ("characters", "creatures", "props", "bodydetails"):
            entries = grouped.get(group, []) or []
            if isinstance(entries, dict):
                entries = [{"id": key, "reference_image": value} for key, value in entries.items()]
            elif isinstance(entries, str):
                raise ValueError(f"Stage5 reference_paths.{group} must be an ID map or list")
            for entry in entries:
                if not isinstance(entry, dict):
                    raise ValueError(f"Stage5 reference_paths.{group} entries must be objects")
                aid = entry.get("id")
                image = entry.get("reference_image") or entry.get("path")
                if not aid or not image:
                    raise ValueError(f"Stage5 reference_paths.{group} entry requires id and reference_image")
                variant = str(entry.get("variant") or "").strip() if group == "creatures" else ""
                if variant:
                    key = (str(aid), variant)
                    current = variants.get(key)
                    if current and current["path"] != image:
                        raise ValueError(f"Stage5 creature {aid} variant {variant} has conflicting paths")
                    if not current:
                        current = {
                            "id": str(aid), "variant": variant, "path": image,
                            "description": entry.get("desc_en") or entry.get("description_en") or "",
                            "shot_ids": [],
                        }
                        variants[key] = current
                    sid = shot_binding.get("global_shot_id")
                    if sid and sid not in current["shot_ids"]:
                        current["shot_ids"].append(sid)
                    if aid not in paths:
                        paths[aid] = image
                    continue
                if aid in paths and paths[aid] != image:
                    raise ValueError(f"Stage5 asset {aid} has conflicting bound reference paths")
                paths[aid] = image
    return paths, scene_path, list(variants.values()), scene_description


# ==============================================================================
# H3 六段式 Prompt 編譯核心
# ==============================================================================

def format_timestamp(seconds: float) -> str:
    """將秒數格式化為 mm:ss.000 切點字串。"""
    mm = int(seconds // 60)
    ss = seconds % 60
    return f"{mm:02d}:{ss:06.3f}"


def map_camera_motion(raw_movement: str, shot_index: int = 0) -> str:
    """確保提取並映射為符合 H3 官方合法運鏡詞。"""
    raw_lower = (raw_movement or "").lower().strip().replace("’", "'")

    if raw_lower in SOURCE_CAMERA_MOTION_ALIASES:
        return SOURCE_CAMERA_MOTION_ALIASES[raw_lower]

    # 1. 直接匹配複合運鏡
    for cm in COMPOUND_CAMERA_MOTIONS:
        if cm in raw_lower:
            return cm

    # 2. 匹配同義詞庫
    for syn, mapped in MOTION_SYNONYMS.items():
        if syn in raw_lower:
            # 提取官方動詞詞首
            for om in OFFICIAL_CAMERA_MOTIONS:
                if om in mapped.lower():
                    return om

    # 3. 匹配官方動詞庫
    for om in OFFICIAL_CAMERA_MOTIONS:
        if re.search(rf"\b{om}\b", raw_lower):
            return om

    # 4. Unknown movement is rejected; never substitute an unrelated motion.
    if not raw_lower or raw_lower in {"unknown", "n/a", "none"}:
        return "static"
    raise ValueError(f"不支援的 camera movement: {raw_movement!r}")


def sanitize_english_text(text: str) -> str:
    """清理多餘空白與符號。"""
    return re.sub(r"\s+", " ", text).strip()


SHOT_SIZE_WEIGHT = {"ECU": 3, "CU": 3, "MCU": 2, "MS": 1, "MLS": 1, "LS": 0.5, "WS": 0.5, "EWS": 0.3}


def _shot_speaker(s: Dict[str, Any]) -> Optional[str]:
    dlg = s.get("dialogue_and_audio", {}) or {}
    return dlg.get("speaker") or None


def _is_voiceover(s: Dict[str, Any]) -> bool:
    dlg = s.get("dialogue_and_audio", {}) or {}
    spec = " ".join(str(dlg.get(key) or "") for key in ("voice_4d_spec", "audio_type")).lower()
    return (
        is_narrator(dlg.get("speaker"))
        or "voiceover" in spec
        or "v.o" in spec
        or any(term in spec for term in ("inner voice", "unseen voice", "off-screen voice", "offscreen voice", "腦內聲", "內心聲"))
    )


def _dialogue_visibility(s: Dict[str, Any]) -> str:
    """Classify how authored dialogue may appear without inventing a speaking face."""
    dlg = s.get("dialogue_and_audio", {}) or {}
    if _is_voiceover(s):
        return "offscreen"
    searchable = [s.get("composition_start", "")]
    for key in ("action_stages", "action_stages_en", "observable_expression", "observable_expression_en"):
        value = (s.get("action_and_performance", {}) or {}).get(key, [])
        searchable.extend(value if isinstance(value, list) else [value])
    searchable.extend([dlg.get("voice_4d_spec", ""), dlg.get("audio_type", "")])
    text = " ".join(str(part or "") for part in searchable).lower()
    offscreen_terms = (
        "offscreen", "off-screen", "beyond frame", "out of frame", "outside the frame",
        "never appears", "no speaking mouth", "mouth is out of view", "mouth out of view",
        "mouth remains unseen", "嘴部不可見", "不顯示聲源嘴部", "畫外", "鏡外", "不露臉",
    )
    if any(term in text for term in offscreen_terms):
        return "offscreen"
    # A locked mouth may still be in frame (for example, a back-only driver).
    return "mouth_hidden" if dlg.get("lips_closed_lock") else "visible"


def _dialogue_speaker_label(speaker: Optional[str], registry: AssetRegistry) -> str:
    if not speaker:
        return "the authored speaker"
    if is_narrator(speaker):
        return f"the narrator (speaker ID {speaker})"
    normalized = speaker.lower()
    special_labels = {
        "e-unknown-voice": "the unseen inner voice",
        "c-guide": "the guide",
        "c-doctor": "the doctor",
        "c-nurse": "the nurse",
        "c-driver": "the driver",
    }
    label = special_labels.get(normalized)
    if not label:
        info = registry.characters.get(speaker, {})
        label = str(info.get("name") or speaker)
    return f"{label} (speaker ID {speaker})"


def _speech_window_clause(dlg: Dict[str, Any]) -> str:
    window = dlg.get("speech_window")
    if not isinstance(window, dict) or window.get("start") is None or window.get("end") is None:
        return ""
    unit = str(window.get("unit") or "segment_seconds")
    try:
        start = float(window["start"])
        end = float(window["end"])
    except (TypeError, ValueError):
        return ""
    return f"Speech window: {unit} {start:.3f}–{end:.3f}. "


def _focal_char(s: Dict[str, Any]) -> Optional[str]:
    for c in s.get("character_ids", []) or []:
        if not is_narrator(c):
            return c
    return None


def _english_or_empty(text: str) -> str:
    text = _clean(text)
    return text


def compile_segment_h3(
    layer2_data: Dict[str, Any],
    registry: AssetRegistry,
    max_char_refs: int = 1,
    auto_lora: bool = True,
    rounding_mode: str = "floor",
    stage5_binding: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """將單個 Layer 2 JSON 分鏡檔編譯為符合 H3 官方六段式規範的資料結構。

    主角參考圖：asset_refs.primary_character / metadata.primary_character 優先；
    否則取臉戲權重（景別越近權重越高）最重的角色。旁白與畫外音永不成為主體。
    """
    if stage5_binding is not None and layer2_data.get("_stage5_binding") is not stage5_binding:
        layer2_data = apply_stage5_binding(layer2_data, stage5_binding)
    if stage5_binding is None:
        stage5_binding = layer2_data.get("_stage5_binding")
    seg_id = layer2_data.get("segment_id") or layer2_data.get("scene_id", "SEG01")
    scene_id = layer2_data.get("scene_id", "SC01")
    metadata = layer2_data.get("metadata", {}) or {}
    style_lock = layer2_data.get("style_lock", {}) or {}
    target_dur = float(metadata.get("target_duration_sec", 7.0))
    aspect = metadata.get("aspect_ratio", "16:9")
    shots = layer2_data.get("shots", []) or []
    if not shots:
        raise ValueError(f"分鏡 {seg_id} 未包含任何 shots！")
    contains_dialogue = any(
        bool(
            (shot.get("dialogue_and_audio", {}) or {}).get("has_dialogue")
            or (shot.get("dialogue_and_audio", {}) or {}).get("line_verbatim")
            or (shot.get("dialogue_and_audio", {}) or {}).get("speech_window")
        )
        for shot in shots
    )
    selected_rounding_mode = "ceil" if contains_dialogue else rounding_mode
    eff_d = effective_duration(target_dur, rounding=selected_rounding_mode)
    # Treat authored shot timings as one continuous source timeline, then
    # adjust only the final shot to the effective H3 duration.
    shots = [dict(shot) for shot in shots]
    if len(shots) == 1 and not ("start_time" in shots[0] and "end_time" in shots[0]):
        shots[0].update(start_time=0.0, end_time=target_dur, duration=target_dur)
    tolerance = 1e-3
    cursor = 0.0
    for index, shot in enumerate(shots, start=1):
        start, end, duration = (float(shot.get(key, 0)) for key in ("start_time", "end_time", "duration"))
        if abs(start - cursor) > tolerance:
            raise ValueError(f"shot timeline gap/overlap at shot {index}: expected {cursor:.3f}, got {start:.3f}")
        if end <= start or abs((end - start) - duration) > tolerance:
            raise ValueError(f"shot {index} has inconsistent start/end/duration")
        cursor = end
    if abs(cursor - target_dur) > tolerance:
        raise ValueError(f"source shot duration {cursor:.3f}s does not match target {target_dur:.3f}s")
    shots[-1]["end_time"] = round(eff_d, 3)
    shots[-1]["duration"] = round(eff_d - float(shots[-1]["start_time"]), 3)
    if shots[-1]["duration"] < 0.5:
        raise ValueError("effective duration leaves the final shot below 0.5s")
    cuts = [float(shot["end_time"]) for shot in shots[:-1]]
    if cuts and (cuts[0] < 2.0 or any(b - a < 2.0 for a, b in zip(cuts, cuts[1:])) or eff_d - cuts[-1] < 2.0):
        raise ValueError("source timeline cannot satisfy H3 cut bounds; revise the storyboard cuts")
    notes: List[str] = []

    # ---------- 角色與服裝 ----------
    asset_refs = layer2_data.get("asset_refs", {}) or {}
    costume_of: Dict[str, Optional[str]] = {}
    for c in (asset_refs.get("characters", []) or []) + (asset_refs.get("creatures", []) or []):
        if isinstance(c, dict) and c.get("id"):
            costume_of[c["id"]] = c.get("costume_id") or c.get("wardrobe_state")
        elif isinstance(c, str):
            costume_of.setdefault(c, None)
    seg_wardrobe = metadata.get("wardrobe_state") or layer2_data.get("wardrobe_state") or style_lock.get("wardrobe_state")

    weight: Dict[str, float] = {}
    order: List[str] = []
    for s in shots:
        size = (s.get("camera_optics", {}) or {}).get("shot_size", "MS")
        for k, c in enumerate(s.get("character_ids", []) or []):
            if is_narrator(c):
                continue
            if c not in order:
                order.append(c)
            weight[c] = weight.get(c, 0) + SHOT_SIZE_WEIGHT.get(size, 1) * (1.0 if k == 0 else 0.3)
        speaker = _shot_speaker(s)
        speaker_record = registry.characters.get(speaker, {}) if speaker else {}
        speaker_is_visual = not (speaker_record.get("no_visual_reference") or speaker_record.get("voice_only"))
        if speaker and speaker_is_visual and not _is_voiceover(s):
            if speaker not in order:
                order.append(speaker)
            weight[speaker] = weight.get(speaker, 0) + SHOT_SIZE_WEIGHT.get(size, 1)
    for c in costume_of:
        if not is_narrator(c) and c not in order:
            order.append(c)
            weight.setdefault(c, 0)

    primary = asset_refs.get("primary_character") or metadata.get("primary_character")
    ranked = sorted(order, key=lambda c: (-weight.get(c, 0), order.index(c)))
    if primary and primary in ranked:
        ranked.remove(primary)
        ranked.insert(0, primary)
    elif primary:
        ranked.insert(0, primary)
    no_visual_ids = set(asset_refs.get("no_visual_reference_ids", []) or [])
    ref_path_map: Dict[str, str] = {}
    bound_scene_path = None
    bound_scene_description = None
    creature_variants: List[Dict[str, Any]] = []
    if stage5_binding:
        ref_path_map, bound_scene_path, creature_variants, bound_scene_description = _stage5_reference_path_map(stage5_binding)
        for shot_binding in stage5_binding.get("shots", []) or []:
            paths = shot_binding.get("reference_paths", {}) or {}
            chars = paths.get("characters", []) or []
            if isinstance(chars, dict):
                chars = [{"id": key, "reference_image": value} for key, value in chars.items()]
            for entry in chars:
                if isinstance(entry, dict) and entry.get("id") and entry.get("costume_id"):
                    cid, costume_id = entry["id"], entry["costume_id"]
                    current = costume_of.get(cid)
                    if current and current != costume_id:
                        raise ValueError(f"Stage5 character {cid} has conflicting costume bindings in one segment")
                    costume_of[cid] = costume_id
        variant_paths = [variant["path"] for variant in creature_variants]
        for rel in ([bound_scene_path] if bound_scene_path else []) + list(ref_path_map.values()) + variant_paths:
            path = pathlib.Path(rel)
            if path.is_absolute():
                raise ValueError(f"Stage5 reference image path must be project-relative: {rel}")
            try:
                (registry.project_root / path).resolve().relative_to(registry.project_root.resolve())
            except ValueError as exc:
                raise ValueError(f"Stage5 reference image path escapes project root: {rel}") from exc
            if not registry.path_exists(rel):
                raise ValueError(f"Stage5 bound reference image does not exist: {rel}")
        for shot_binding in stage5_binding.get("shots", []) or []:
            no_visual_ids.update(shot_binding.get("no_visual_reference_ids", []) or [])
        # Stage5 refs are explicit, per-shot production bindings. Keep every image-bearing
        # visible cast member and creature; the legacy one-image default is not applied.
        visual_order: List[str] = []
        explicit_visual_ids = {
            cid for b in (stage5_binding.get("shots", []) or [])
            for cid in (b.get("visual_subject_ids", []) or [])
        }
        for shot in shots:
            bound_shot = next((b for b in stage5_binding.get("shots", []) or []
                               if b.get("global_shot_id") == shot.get("global_shot_id")), {})
            ids = bound_shot.get("visual_subject_ids") or shot.get("character_ids", []) or []
            for cid in ids:
                if not cid or cid in no_visual_ids or cid in visual_order:
                    continue
                info = registry.get_character(cid, wardrobe_state=costume_of.get(cid) or seg_wardrobe)
                if info.get("no_visual_reference") or info.get("voice_only"):
                    if cid in explicit_visual_ids or cid in ref_path_map:
                        raise ValueError(f"Stage5 marks {cid} as visually present but the normalized Bible forbids a visual reference")
                    continue
                if cid:
                    visual_order.append(cid)
        for group in (asset_refs.get("characters", []) or [], asset_refs.get("creatures", []) or []):
            for entry in group:
                cid = entry.get("id") if isinstance(entry, dict) else entry
                if cid and cid not in no_visual_ids and cid not in visual_order:
                    visual_order.append(cid)
        for cid in ref_path_map:
            if cid in registry.characters and cid not in no_visual_ids and cid not in visual_order:
                visual_order.append(cid)
        if primary and primary in visual_order:
            visual_order.remove(primary)
            visual_order.insert(0, primary)
        for cid in visual_order:
            info = registry.get_character(cid, wardrobe_state=costume_of.get(cid) or seg_wardrobe)
            if info.get("no_visual_reference") or info.get("voice_only"):
                raise ValueError(f"Stage5 marks {cid} as visually present but the normalized Bible forbids a visual reference")
            if not (ref_path_map.get(cid) or info.get("ref_img")):
                raise ValueError(f"Stage5 visible character/creature {cid} has no approved reference image")
        selected = visual_order
        secondary = [cid for cid in ranked if cid not in selected]
    else:
        selected = [cid for cid in ranked if cid not in no_visual_ids][:max(1, max_char_refs)]
        secondary = [cid for cid in ranked if cid not in selected]

    first_variant_by_id: Dict[str, Dict[str, Any]] = {}
    for variant in creature_variants:
        first_variant_by_id.setdefault(variant["id"], variant)

    def char_info(cid: str) -> Dict[str, Any]:
        info = registry.get_character(cid, wardrobe_state=costume_of.get(cid) or seg_wardrobe)
        if cid in ref_path_map:
            info["ref_img"] = ref_path_map[cid]
        first_variant = first_variant_by_id.get(cid)
        if first_variant:
            variant_desc = first_variant.get("description")
            if not variant_desc:
                variants = info.get("variants", {}) or {}
                variant_info = variants.get(first_variant["variant"], {}) if isinstance(variants, dict) else {}
                if isinstance(variant_info, str):
                    variant_desc = variant_info
                elif isinstance(variant_info, dict):
                    variant_desc = variant_info.get("desc_en") or variant_info.get("visual_prompt_en") or variant_info.get("description_en")
            info["desc_en"] = variant_desc or f"the same {info.get('name', cid)} in its {first_variant['variant']} stage, matching the stage-specific reference"
        return info

    # ---------- 場景 ----------
    location_id = asset_refs.get("scene_id", scene_id)
    loc_info = registry.get_location(location_id)
    if stage5_binding and bound_scene_path:
        loc_info["ref_img"] = bound_scene_path
    if stage5_binding and bound_scene_description:
        loc_info["desc_en"] = bound_scene_description
    ref2va = str((layer2_data.get("continuity_handshake", {}) or {}).get("mode", "")).upper() == "INDEPENDENT_REF2VA"

    reference_images: List[Dict[str, Any]] = [{
        "id": loc_info["id"], "type": "scene", "description": loc_info["desc_en"], "path": loc_info["ref_img"],
    }]
    subject_def_lines = [
        f"<Picture 1> is a scene/style reference for {loc_info['desc_en']}; use it as visual guidance."
        if ref2va else f"<Picture 1> is the establishing background plate of {loc_info['desc_en']}."
    ]
    retention_lines = [
        "<Picture 1> (scene reference): retain relevant architectural layout, spatial perspective, and lighting atmosphere as visual guidance."
        if ref2va else "<Picture 1> (first frame): fully_preserved - the architectural layout, spatial perspective, and lighting atmosphere are retained."
    ]

    tag_of: Dict[str, str] = {}
    subject_picture_no: Dict[str, int] = {}
    for k, cid in enumerate(selected, start=1):
        info = char_info(cid)
        tag_of[cid] = f"<Subject {k}>"
        subject_picture_no[cid] = k + 1
        reference_images.append({
            "id": info["id"], "type": "creature" if info.get("is_creature") else "character",
            "description": info["desc_en"], "path": info["ref_img"],
            "is_primary_character": k == 1,
            **({"costume_id": costume_of.get(cid)} if costume_of.get(cid) else {}),
        })
        desc = info["desc_en"] or info["name"]
        subject_def_lines.append(f"<Subject {k}> is the character in <Picture {k + 1}>, {desc}.")
        ret = f"<Subject {k}> (appears across shots): fully_preserved - the facial identity, hairstyle, and wardrobe from <Picture {k + 1}> are retained."
        if info.get("is_creature"):
            ret += " Ignore neutral gray/white studio background of creature turnaround sheet."
        retention_lines.append(ret)
        if not info["desc_en"]:
            notes.append(f"{cid} 缺英文固定描述片段")

    secondary_short: Dict[str, str] = {}
    for cid in secondary:
        info = char_info(cid)
        desc = info["desc_en"] or info["name"]
        retention_lines.append(f"Secondary character appears as pure text description without reference image: {desc}.")
        w = (info.get("wardrobe_states", {}).get(costume_of.get(cid) or "", {}) or {})
        w_desc = w.get("desc_en") if isinstance(w, dict) else ""
        secondary_short[cid] = info["short_en"] + (f", {w_desc}" if w_desc else "")

    # Stage5 supplementary props/body details are Pictures after the subject sequence.
    # They inform object or localized-detail appearance without becoming face Subjects.
    variant_picture_by_shot: Dict[str, List[Tuple[int, str]]] = {}
    if stage5_binding:
        supplementary: List[Tuple[str, Dict[str, Any]]] = []
        prop_ids: List[str] = []
        detail_ids: List[str] = []
        for entry in asset_refs.get("props", []) or []:
            aid = entry.get("id") if isinstance(entry, dict) else entry
            if aid and aid not in prop_ids:
                prop_ids.append(aid)
        for entry in asset_refs.get("bodydetails", []) or []:
            aid = entry.get("id") if isinstance(entry, dict) else entry
            if aid and aid not in detail_ids:
                detail_ids.append(aid)
        for aid in ref_path_map:
            if aid in registry.props and aid not in prop_ids:
                prop_ids.append(aid)
            if aid in registry.bodydetails and aid not in detail_ids:
                detail_ids.append(aid)
        for aid in prop_ids:
            info = registry.get_prop(aid)
            info["ref_img"] = ref_path_map.get(aid, info["ref_img"])
            supplementary.append(("prop", info))
        for aid in detail_ids:
            info = registry.get_bodydetail(aid)
            info["ref_img"] = ref_path_map.get(aid, info["ref_img"])
            supplementary.append(("bodydetail", info))
        for kind, info in supplementary:
            reference_images.append({
                "id": info["id"], "type": kind, "description": info.get("desc_en") or info.get("name", info["id"]),
                "path": info["ref_img"],
            })
            if not info.get("desc_en"):
                notes.append(f"{info['id']} 缺英文固定描述片段")
            else:
                pic_no = len(reference_images)
                subject_def_lines.append(f"<Picture {pic_no}> is a supplementary {kind} reference for {info['desc_en']}; use only for that object/detail.")
                retention_lines.append(f"<Picture {pic_no}> ({kind} reference): preserve only the registered visual details of {info['id']}.")
        for variant in creature_variants:
            info = registry.get_character(variant["id"])
            desc = variant.get("description")
            if not desc:
                variants = info.get("variants", {}) or {}
                variant_info = variants.get(variant["variant"], {}) if isinstance(variants, dict) else {}
                if isinstance(variant_info, str):
                    desc = variant_info
                elif isinstance(variant_info, dict):
                    desc = variant_info.get("desc_en") or variant_info.get("visual_prompt_en") or variant_info.get("description_en")
            desc = desc or f"{info.get('name', variant['id'])} in the {variant['variant']} stage"
            if first_variant_by_id.get(variant["id"]) is variant:
                pic_no = subject_picture_no.get(variant["id"])
                if pic_no is None:
                    raise ValueError(f"Stage5 creature variant {variant['id']} has no canonical Subject reference")
                targets = ", ".join(variant["shot_ids"])
                subject_def_lines.append(
                    f"The canonical creature Subject uses <Picture {pic_no}> for its {variant['variant']} stage only "
                    f"in {targets}; switch to the explicitly scoped stage Picture for other listed forms."
                )
                retention_lines.append(
                    f"<Picture {pic_no}> is the {variant['variant']} morphology of {variant['id']}; preserve it only in {targets}."
                )
                for sid in variant["shot_ids"]:
                    variant_picture_by_shot.setdefault(sid, []).append((pic_no, variant["variant"]))
                continue
            reference_images.append({
                "id": f"{variant['id']}@{variant['variant']}", "type": "creature_variant",
                "description": desc, "path": variant["path"], "canonical_id": variant["id"],
                "variant": variant["variant"], "shot_ids": list(variant["shot_ids"]),
            })
            pic_no = len(reference_images)
            targets = ", ".join(variant["shot_ids"])
            subject_def_lines.append(
                f"<Picture {pic_no}> is the {variant['variant']} stage of {info.get('name', variant['id'])}: {desc}. "
                f"Use it only for the listed shots ({targets}); do not apply it to other stages."
            )
            retention_lines.append(
                f"<Picture {pic_no}> (shot-scoped creature stage reference): preserve this morphology only in {targets}."
            )
            for sid in variant["shot_ids"]:
                variant_picture_by_shot.setdefault(sid, []).append((pic_no, variant["variant"]))

    # ---------- 風格與光線 ----------
    if stage5_binding:
        anchor = registry.style.get("style_anchor", "") or "cinematic film look"
    else:
        anchor = _clean(style_lock.get("anchor")) or registry.style.get("style_anchor", "") or "cinematic film look"
    lighting_line = (_clean(metadata.get("lighting_lock_line")) or _clean(style_lock.get("lighting_lock_line"))
                     or registry.style.get("lighting_lock_line", "") or "natural ambient light")
    lighting_line_clean, _ = strip_hex(palette_names(lighting_line))
    if not any(re.search(rf"\b{lt}\b", lighting_line_clean, re.IGNORECASE) for lt in LIGHT_SOURCE_TERMS):
        lighting_line_clean += " with soft ambient light"

    continuity = style_lock.get("continuity_anchors", {}) or {}
    authored_anchors = [f"{key}: {continuity[key]}" for key in ("lighting", "axis", "blocking", "texture") if continuity.get(key)]
    if anchor:
        authored_anchors.insert(0, f"style anchor: {anchor}")
    negative = (_clean(registry.style.get("style_negative")) if stage5_binding
                else (_clean(style_lock.get("negative")) or _clean(registry.style.get("style_negative"))))
    # Asset-design exclusions belong to editorial QA, not an SD-style negative
    # prompt block inside H3's generated prose. The positive style anchor above
    # describes the desired rendered appearance.
    authored_anchors.append(f"lighting lock: {lighting_line_clean}")
    retention_lines.append("Continuity anchors: " + "; ".join(authored_anchors))

    effective_style_lock = dict(style_lock)
    effective_style_lock["negative"] = ""
    if stage5_binding:
        effective_style_lock.update({
            "anchor": anchor,
            "negative": "",
            "lighting_lock_line": lighting_line_clean,
        })

    mood = _clean(metadata.get("mood_en")) or _clean(metadata.get("summary_en"))
    focus = "<Subject 1>" if selected else "the scene"
    summary_block = (
        f"summary:\n[reference generation] A {target_dur:.1f}s {aspect} segment ({eff_d:.3f}s effective from {target_dur:.3f}s target) "
        f"in {len(shots)} shots opening on <Picture 1>"
        + (f", {mood}." if mood else f", centred on {focus}.")
    )
    retention_block = "retention_analysis:\n" + "\n".join(retention_lines)

    # ---------- 切點 ----------
    n_shots = len(shots)
    # Keep authored cut points exactly; only the final shot end is quantized.
    cut_timestamps = [round(float(shot["end_time"]), 3) for shot in shots[:-1]]

    # ---------- 逐鏡 ----------
    det_header = f"The target video follows the authored visual style ({aspect}), illuminated by {lighting_line_clean}."
    if metadata.get("palette_preset"):
        det_header += f" Color palette: {metadata['palette_preset']}."
    det_lines = [det_header]
    tail_hold = style_lock.get("tail_freeze_hold", True)
    final_shot_start = float(shots[-1].get("start_time", 0))
    final_second_start = max(final_shot_start, eff_d - 1.0)
    final_second_has_dialogue = False
    for shot in shots:
        dlg = shot.get("dialogue_and_audio", {}) or {}
        window = dlg.get("speech_window")
        if not window:
            if dlg.get("has_dialogue") and shot is shots[-1]:
                final_second_has_dialogue = True
            continue
        try:
            speech_start = float(window.get("start", 0))
            speech_end = float(window.get("end", 0))
        except (TypeError, ValueError):
            continue
        if speech_start < eff_d and speech_end > final_second_start:
            final_second_has_dialogue = True
            break
    tail_hold = tail_hold and not final_second_has_dialogue
    used_motion: set = set()
    for idx, s in enumerate(shots, start=1):
        cam = s.get("camera_optics", {}) or {}
        shot_size = cam.get("shot_size", "MS")
        focal_len = _clean(cam.get("focal_length")) or "35mm"
        dist = _clean(cam.get("physical_distance"))
        if dist and CJK_RE.search(dist):
            m = re.search(r"([\d.]+)\s*(?:公尺|米|m)", dist)
            dist = f"{m.group(1)}m" if m else ""
        optics = f" ({focal_len}, {dist})" if dist else f" ({focal_len})"

        fc = _focal_char(s)
        if fc in tag_of:
            focal = tag_of[fc]
        elif fc:
            focal = secondary_short.get(fc) or char_info(fc)["short_en"]
        else:
            focal = "the scene"

        motion = map_camera_motion(cam.get("movement", "static"), idx).replace("camera ", "").strip()
        mclause = "the camera holds a static shot" if ("static" in motion or "steady" in motion) else f"the camera {motion}"
        if mclause in used_motion and "static" not in mclause:
            mclause += " slowly"
        used_motion.add(mclause)

        act = s.get("action_and_performance", {}) or {}
        raw_fields = list(act.get("action_stages_en") or act.get("action_stages") or []) + [
            act.get("observable_expression_en") or act.get("observable_expression") or ""]
        if any("TODO" in str(x) for x in raw_fields):
            notes.append(f"未完成：{s.get('shot_id')} 的動作或表情仍有 TODO")
        stages = [normalize_authored_camera_hold_action(TODO_RE.sub("", x).strip())
                  for x in (act.get("action_stages_en") or act.get("action_stages") or []) if isinstance(x, str)]
        stages = [x for x in stages if x]
        if len(stages) >= 3:
            action = ", then ".join(stages)
        elif len(stages) == 2:
            action = f"{stages[0]}, then {stages[1]}"
        elif stages:
            action = stages[0]
        else:
            notes.append(f"{s.get('shot_id')} 缺動作力學三要素")
            raise ValueError(f"shot {s.get('shot_id', idx)} is missing authored action stages")
        expr = TODO_RE.sub("", act.get("observable_expression_en") or act.get("observable_expression") or "").strip()

        dlg = s.get("dialogue_and_audio", {}) or {}
        if dlg.get("has_dialogue") and dlg.get("line_verbatim"):
            line = dlg["line_verbatim"].strip()
            spk = dlg.get("speaker")
            identity = _dialogue_speaker_label(spk, registry)
            window = _speech_window_clause(dlg)
            speaker_record = registry.characters.get(spk, {}) if spk else {}
            visibility = "offscreen" if (speaker_record.get("no_visual_reference") or speaker_record.get("voice_only")) else _dialogue_visibility(s)
            if visibility == "offscreen":
                delivery = f"The line is heard from {identity}; do not show the speaker, no visible lip movement, and visible characters' mouths stay closed. "
            elif visibility == "mouth_hidden":
                delivery = f"{identity} delivers the line with no visible lip movement. "
            else:
                who = tag_of.get(spk) or (secondary_short.get(spk) if spk else None) or focal
                delivery = f"{identity} is the visible speaking character ({who}). "
            speech = f"; {window}{delivery}<d>[Chinese] {line}</d>"
        else:
            speech = "; lips stay closed"

        blocking = s.get("spatial_blocking", {}) or {}
        blocking_bits = [blocking.get("blocking_desc", "")]
        if blocking.get("anchor_objects"):
            blocking_bits.append("anchor objects: " + ", ".join(blocking["anchor_objects"]))
        blocking_clause = f" Blocking: {'; '.join(bit for bit in blocking_bits if bit)}." if any(blocking_bits) else ""
        stage_refs = ""
        global_shot_id = s.get("global_shot_id")
        for picture_no, variant_name in variant_picture_by_shot.get(global_shot_id, []):
            stage_refs += f" Stage-specific reference: use <Picture {picture_no}> for the creature's {variant_name} morphology in this shot only."

        if idx == 1 and ref2va:
            head = f"[Shot 1] The scene opens with <Picture 1> as a scene/style reference for spatial guidance: {shot_size}{optics} of {focal}, as {mclause}."
        elif idx == 1:
            head = f"[Shot 1] The shot begins from <Picture 1>: {shot_size}{optics} of {focal}, as {mclause}."
        else:
            head = (f"[Shot {idx}] At {format_timestamp(cut_timestamps[idx - 2])}, the shot cuts to a "
                    f"{shot_size}{optics} of {focal}, as {mclause}.")
        tail = " The final second holds still before the cut." if (idx == n_shots and tail_hold) else ""
        if idx == n_shots and layer2_data.get("segment_end_state"):
            final_state = layer2_data["segment_end_state"].get("planned_final_state") or {}
            if final_state:
                tail += " End state: " + json.dumps(final_state, ensure_ascii=False, sort_keys=True) + "."
        action = action[:1].upper() + action[1:]
        body = f"{head} {action}." + (f" Expression: {expr}" if expr else "") + blocking_clause + stage_refs + f"{speech}.{tail}"
        det_lines.append(sanitize_english_text(body))

    detailed_block = "detailed_description:\n" + "\n".join(det_lines)

    # ---------- 音效與配樂 ----------
    foley = _clean(layer2_data.get("overall_soundscape")) or _clean(metadata.get("soundscape_en"))
    if not foley:
        parts = []
        for s in shots:
            d = s.get("dialogue_and_audio", {}) or {}
            f = _clean(d.get("foley_and_ambience_en")) or _clean(d.get("foley_and_ambience"))
            if f:
                parts.append(f)
        foley = "; ".join(parts)
    soundscape_block = "overall_soundscape:\n" + foley

    music = _clean(layer2_data.get("non_diegetic_music")) or _clean(metadata.get("music_en"))
    if not music:
        music = ""
    music_block = "non_diegetic_music:\n" + music

    full_h3_prompt = (
        "subject_definitions:\n" + "\n".join(subject_def_lines) + "\n\n"
        f"{summary_block}\n\n{retention_block}\n\n{detailed_block}\n\n{soundscape_block}\n\n{music_block}\n"
    )

    # ---------- LoRA：只有 Combat_Impact 段才推導 ----------
    loras: List[Dict[str, Any]] = []
    if auto_lora and any(s.get("dramatic_beat_type") == "Combat_Impact" for s in shots):
        combined_spec = {
            "focal": shots[0].get("camera_optics", {}).get("focal_length", "35mm"),
            "pov": shots[0].get("camera_optics", {}).get("pov_routing", "objective"),
            "action": " ".join(" ".join(s.get("action_and_performance", {}).get("action_stages_en")
                                        or s.get("action_and_performance", {}).get("action_stages", [])) for s in shots),
            "expression": " ".join(s.get("action_and_performance", {}).get("observable_expression", "") or "" for s in shots),
            "dialogue": " ".join(s.get("dialogue_and_audio", {}).get("line_verbatim", "") or "" for s in shots),
            "anchor_obj": " ".join(" ".join(s.get("spatial_blocking", {}).get("anchor_objects", [])) for s in shots),
        }
        loras = auto_adapt_h3_loras(combined_spec)["loras"]
        if not re.search(r"photoreal|realistic|live[- ]action|寫實", anchor, re.IGNORECASE):
            # 皮膚寫實 LoRA 只給寫實／半寫實風格，3D 國漫、2D 動畫會被拉成真人質感
            loras = [l for l in loras if "realism" not in l.get("name", "").lower()]

    missing = [r["path"] for r in reference_images if not registry.path_exists(r["path"])]
    if stage5_binding and missing:
        raise ValueError(f"Stage5 has missing bound reference image(s): {', '.join(missing)}")
    return {
        "segment_id": seg_id,
        "scene_id": scene_id,
        "metadata": {
            **metadata,
            "aspect_ratio": aspect,
            "target_duration_sec": target_dur,
            "effective_duration_sec": round(eff_d, 3),
            "rounding_mode": selected_rounding_mode,
            "rounding_reason": "dialogue-preserving" if contains_dialogue else metadata.get("rounding_reason", "configured"),
            "shots_count": n_shots,
            "style_lock": effective_style_lock,
            "qa_exclusions": negative,
            "palette_preset": metadata.get("palette_preset", ""),
        },
        "reference_images": reference_images,
        "h3_prompt": full_h3_prompt,
        "h3_loras": loras,
        "shots": shots,
        "segment_end_state": layer2_data.get("segment_end_state"),
        "compile_notes": notes + [f"參考圖不存在: {p}" for p in missing],
    }


# ==============================================================================
# 批次編譯與輸出模組
# ==============================================================================

def load_layer2_files(sources: List[str]) -> List[pathlib.Path]:
    """收集並依照段落順序排序所有 Layer 2 分鏡檔案。"""
    import glob
    found: List[pathlib.Path] = []
    for s in sources:
        if any(c in s for c in ("*", "?", "[")):
            matched = sorted(glob.glob(s))
            found.extend(pathlib.Path(m) for m in matched)
        else:
            p = pathlib.Path(s)
            if p.is_dir():
                found.extend(p.glob("layer2-*.json"))
            elif p.is_file():
                found.append(p)

    def sort_key(path: pathlib.Path) -> tuple:
        name = path.stem.replace("layer2-", "")
        return segment_sort_key(name)

    return sorted(list(set(found)), key=sort_key)


def load_stage5_bindings(path: pathlib.Path) -> Dict[str, Dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"Cannot read Stage5 bindings {path}: {exc}") from exc
    segments = payload.get("segments") if isinstance(payload, dict) else None
    if not isinstance(segments, list):
        raise ValueError("Stage5 bindings must contain a segments array")
    result: Dict[str, Dict[str, Any]] = {}
    for binding in segments:
        if not isinstance(binding, dict) or not binding.get("segment_id"):
            raise ValueError("Each Stage5 binding must be an object with segment_id")
        sid = str(binding["segment_id"])
        if sid in result:
            raise ValueError(f"Duplicate Stage5 binding segment_id: {sid}")
        result[sid] = binding
    return result


def render_markdown_package(
    compiled_segments: List[Dict[str, Any]],
    episode: Optional[str] = None
) -> str:
    """渲染人類可讀、可交付之 prompts-epXX.md 提示詞包。"""
    ep_title = episode or (compiled_segments[0]["segment_id"].split("-")[0] if compiled_segments else "EP01")
    md_lines: List[str] = [
        f"# {ep_title} MiniMax H3 官方六段式提示詞包",
        "",
        f"> 本提示詞包由 `compile_layer2_to_h3.py` 自動編譯自 Layer 2 分鏡檔，"
        f"全面對齊《噩盡島》實戰定案（7–10s 分段、獨立 Ref2VA、防混臉序對與動作力學）。",
        "",
        "## 分段提示詞清單",
        ""
    ]

    for idx, seg in enumerate(compiled_segments, start=1):
        sid = seg["segment_id"]
        sc_id = seg["scene_id"]
        meta = seg["metadata"]
        refs = seg["reference_images"]
        prompt = seg["h3_prompt"]
        loras = seg["h3_loras"]

        md_lines.append(f"### Segment {idx}: `{sid}` (場景: `{sc_id}` | 目標: `{meta['target_duration_sec']}s` | 真實有效: `{meta['effective_duration_sec']}s`)")
        md_lines.append("")
        md_lines.append(f"**參考圖清單（共 {len(refs)} 張）：**")
        for r_idx, r in enumerate(refs, start=1):
            md_lines.append(f"- `<Picture {r_idx}>` ({r['type']}): `{r['id']}` — {r['description']}")
        md_lines.append("")
        md_lines.append("```text")
        md_lines.append(prompt.strip())
        md_lines.append("```")
        md_lines.append("")

        if loras:
            md_lines.append("**FreeVideo 掛載 LoRA：**")
            md_lines.append("```json")
            md_lines.append(json.dumps({"loras": loras}, ensure_ascii=False, indent=2))
            md_lines.append("```")
            md_lines.append("")

    return "\n".join(md_lines) + "\n"


def verify_stage4_gate(project_root: pathlib.Path, skip_gate: bool = False, layer2_files: Optional[List[pathlib.Path]] = None) -> bool:
    """要求有效 stage-4 人工核准，且核准快照涵蓋目前分鏡與對應草圖。"""
    if skip_gate:
        print("⚠️ [警告] 已顯式指定 --skip-stage-gate，跳過階段 4 九宮格門禁檢查。")
        return True
    try:
        matched, errors = stage4_artifacts(project_root)
        ok, detail = require_approved(project_root, 4)
        snapshot = stage_snapshot(project_root, 4)
        approved_paths = {item["path"] for item in snapshot["artifacts"]}
    except Exception as exc:
        matched, errors, ok, detail, approved_paths = [], [f"核准快照無法驗證: {exc}"], False, str(exc), set()

    unapproved_input = []
    if layer2_files is not None:
        for path in layer2_files:
            try:
                rel = path.resolve().relative_to(project_root.resolve()).as_posix()
            except ValueError:
                unapproved_input.append(str(path))
                continue
            if rel not in approved_paths:
                unapproved_input.append(rel)

    if errors or not matched or not ok or unapproved_input:
        print("\n" + "=" * 78, file=sys.stderr)
        print("❌ [Fatal Gate Error - 階段 4 九宮格分鏡門禁阻斷]", file=sys.stderr)
        print("=" * 78, file=sys.stderr)
        print("stage-4 必須完成人工核准，且目前 Layer 2 與其有效對應構圖圖檔須和核准快照一致。", file=sys.stderr)
        print(f"狀態：{detail}", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        for path in unapproved_input:
            print(f"  - 編譯輸入不在 stage-4 快照中: {path}", file=sys.stderr)
        print("請重建並審核 stage-4。compile debug 可顯式 --skip-stage-gate。\n", file=sys.stderr)
        print("=" * 78 + "\n", file=sys.stderr)
        return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Layer 2 分鏡轉 H3 官方六段式 Prompt 與分段對帳 JSON 批次編譯器"
    )
    parser.add_argument("--layer2", nargs="+", required=True, help="Layer 2 分鏡 JSON 檔案路徑或目錄（支援傳入多檔）")
    parser.add_argument("--bible", type=pathlib.Path, default=None, help="Story Bible JSON 路徑（選填）")
    parser.add_argument("--bindings", type=pathlib.Path, default=None, help="核准原 Layer2 的 Stage5 video-bindings.json（選填）")
    parser.add_argument("--assets", type=pathlib.Path, default=None, help="assets.md 路徑（選填）")
    parser.add_argument("--episode", type=str, default=None, help="集號（例如 EP01，選填）")
    parser.add_argument("--output-md", type=pathlib.Path, default=None, help="輸出 Markdown 提示詞包路徑（例如 prompts-ep01.md）")
    parser.add_argument("--output-segments", type=pathlib.Path, default=None, help="輸出分段對帳 JSON 路徑（例如 segments-ep01.json）或目錄")
    parser.add_argument("--auto-lora", action="store_true", default=True, help="自動推導並掛載 H3 LoRA（預設啟用）")
    parser.add_argument("--no-auto-lora", action="store_false", dest="auto_lora", help="停用自動推導 LoRA")
    parser.add_argument("--max-char-refs", type=int, default=1, help="每段最多掛載角色參考圖張數（預設 1 張，防止混臉）")
    parser.add_argument("--check", action="store_true", help="編譯完成後立即自動執行 audit_refs_and_segments 雙重審查")
    parser.add_argument("--project-root", type=pathlib.Path, default=pathlib.Path("."), help="專案根目錄（預設當前目錄）")
    parser.add_argument("--skip-stage-gate", action="store_true", help="強制跳過階段 4 九宮格門禁檢查（僅限測試或除錯）")

    args = parser.parse_args()

    layer2_files = load_layer2_files(args.layer2)
    if not layer2_files:
        print(f"[錯誤] 找不到任何 Layer 2 分鏡檔案: {args.layer2}", file=sys.stderr)
        return 1
    # 執行階段 4 審核快照與構圖檔門禁
    if not verify_stage4_gate(args.project_root, skip_gate=args.skip_stage_gate, layer2_files=layer2_files):
        return 1

    registry = AssetRegistry(bible_path=args.bible, assets_path=args.assets, project_root=args.project_root)
    bindings_by_segment: Dict[str, Dict[str, Any]] = {}
    if args.bindings:
        if not args.bible:
            print("[錯誤] 使用 --bindings 時必須同時以 --bible 指定 normalized video-bible.json", file=sys.stderr)
            return 1
        try:
            bindings_by_segment = load_stage5_bindings(args.bindings)
            input_ids = []
            parsed_inputs: Dict[pathlib.Path, Dict[str, Any]] = {}
            for path in layer2_files:
                data = json.loads(path.read_text(encoding="utf-8"))
                sid = str(data.get("segment_id") or data.get("scene_id") or "")
                if sid in input_ids:
                    raise ValueError(f"Duplicate input segment_id: {sid}")
                input_ids.append(sid)
                parsed_inputs[path] = data
                if sid not in bindings_by_segment:
                    raise ValueError(f"No Stage5 binding for input segment {sid}")
                validate_stage5_binding(data, bindings_by_segment[sid], path, args.project_root)
            extras = set(bindings_by_segment) - set(input_ids)
            if extras:
                raise ValueError(f"Stage5 bindings contain segments outside this compile input: {', '.join(sorted(extras))}")
        except Exception as exc:
            print(f"[錯誤] Stage5 bindings rejected: {exc}", file=sys.stderr)
            return 1
    else:
        parsed_inputs = {}

    print("=" * 75)
    print(f"🎬 正在執行 Layer 2 ➔ H3 官方六段式批次編譯器")
    print(f"輸入檔案數: {len(layer2_files)} 個分鏡段落")
    print("=" * 75)

    compiled_results: List[Dict[str, Any]] = []
    for p in layer2_files:
        try:
            if args.bindings:
                l2_data = parsed_inputs[p]
                stage5_binding = bindings_by_segment[str(l2_data.get("segment_id") or l2_data.get("scene_id") or "")]
                l2_data = apply_stage5_binding(l2_data, stage5_binding)
            else:
                with p.open("r", encoding="utf-8") as f:
                    l2_data = json.load(f)
                stage5_binding = None
            seg_res = compile_segment_h3(
                l2_data,
                registry=registry,
                max_char_refs=args.max_char_refs,
                auto_lora=args.auto_lora,
                stage5_binding=stage5_binding,
            )
            compiled_results.append(seg_res)
            print(f"  ✅ 成功編譯段落: {seg_res['segment_id']} ({len(seg_res['shots'])} 鏡, {seg_res['metadata']['target_duration_sec']}s)")
        except Exception as exc:
            print(f"  ❌ 編譯分鏡失敗 {p.name}: {exc}", file=sys.stderr)
            return 1

    # 輸出 Markdown 提示詞包
    if args.output_md:
        args.output_md.parent.mkdir(parents=True, exist_ok=True)
        md_text = render_markdown_package(compiled_results, episode=args.episode)
        args.output_md.write_text(md_text, encoding="utf-8")
        print(f"\n📄 已輸出 Markdown 提示詞包: {args.output_md}")

    # 輸出分段對帳 JSON
    if args.output_segments:
        if args.output_segments.suffix == ".json":
            args.output_segments.parent.mkdir(parents=True, exist_ok=True)
            export_payload = {
                "episode": args.episode or compiled_results[0]["segment_id"].split("-")[0],
                "total_segments": len(compiled_results),
                "segments": compiled_results,
            }
            with args.output_segments.open("w", encoding="utf-8") as f:
                json.dump(export_payload, f, ensure_ascii=False, indent=2)
                f.write("\n")
            print(f"📦 已輸出分段對帳 JSON 集合: {args.output_segments}")
        else:
            # 作為目錄輸出各分段
            args.output_segments.mkdir(parents=True, exist_ok=True)
            for seg in compiled_results:
                out_p = args.output_segments / f"segment-{seg['segment_id']}.json"
                with out_p.open("w", encoding="utf-8") as f:
                    json.dump(seg, f, ensure_ascii=False, indent=2)
                    f.write("\n")
            print(f"📦 已輸出各分段 JSON 於目錄: {args.output_segments}")

    # 執行雙重審查 (--check)
    if args.check:
        print("\n" + "=" * 75)
        print("🔍 立即執行 audit_refs_and_segments 雙重確定性審查 (--check)")
        print("=" * 75)
        total_errors = 0
        total_warnings = 0

        for seg in compiled_results:
            sid = seg["segment_id"]
            dur = seg["metadata"]["target_duration_sec"]
            # 模式 A: 參考圖序對
            refs_res = audit_refs_and_subjects(seg)
            # 模式 B: H3 提示詞 13 條自檢
            lint_res = lint_h3_prompt(
                seg["h3_prompt"],
                nominal_duration=dur,
                rounding_mode=seg.get("metadata", {}).get("rounding_mode", "floor"),
                authored_shots=seg.get("shots"),
            )

            passed = refs_res["passed"] and lint_res["passed"]
            status_label = "✅ PASS" if passed else "❌ FAIL"
            print(f"\n▶ [{sid}] 審查結果: {status_label}")

            if not refs_res["passed"]:
                for e in refs_res["errors"]:
                    print(f"    [模式A錯誤] {e}")
                total_errors += len(refs_res["errors"])
            else:
                print(f"    [模式A通過] 參考圖與主體定義序對完全合規 (共 {len(seg['reference_images'])} 張圖)")

            if not lint_res["passed"]:
                for e in lint_res["errors"]:
                    print(f"    [模式B錯誤] {e}")
                total_errors += len(lint_res["errors"])
            else:
                print(f"    [模式B通過] 13 條 H3 自檢全部通過 (真實秒數 D={lint_res['details']['effective_duration_sec']}s)")

            for w in refs_res["warnings"] + lint_res["warnings"]:
                print(f"    [警告] {w}")
            total_warnings += len(refs_res["warnings"]) + len(lint_res["warnings"])
            for note in seg.get("compile_notes", []):
                print(f"    [編譯提醒] {note}")
                total_warnings += 1

        print("\n" + "=" * 75)
        print(f"📊 雙重審查總結: 錯誤數: {total_errors} | 警告數: {total_warnings}")
        print("=" * 75)
        if total_errors > 0:
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
