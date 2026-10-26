#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
compile_layer2_to_h3.py — Layer 2 分鏡轉 H3 官方六段式 Prompt 與分段對帳 JSON 批次編譯器
（支援《噩盡島》實戰五大定案：7–10s 分段、獨立 Ref2VA、防角色同質化混臉、H3 官方六段式與 P0 確定性對帳）

功能：
1. 讀取一至多個 Layer 2 分鏡 JSON（支援目錄或多檔案），依集與場序批次編譯。
2. 結合 bible.json 與/或 assets.md 解析角色、妖物、場景底圖的圖片路徑與中英文外貌錨點。
3. 嚴格輸出符合 audit_refs_and_segments.py 17 條規則的 H3 官方六段式結構：
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
from project_state import record_gate_bypass, require_approved, stage4_artifacts, stage_snapshot

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
import style_rules
import camera_moves
from speech_utils import count_speech_chars, normalize_speech

try:  # 以 scripts/storyboard 為 sys.path 執行（CLI 慣例）
    import h3_spec
    import normalize as normalize_mod
    import failure_catalog
    import prompt_authoring
    import continuity_lint
    import voice_lint
    import creature_lint
except ImportError:  # pragma: no cover - 套件匯入路徑
    from . import h3_spec
    from . import normalize as normalize_mod
    from . import failure_catalog
    from . import prompt_authoring
    from . import continuity_lint
    from . import voice_lint
    from . import creature_lint


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


COMPILER_RULES_VERSION = "2026-10-26"  # 改編譯輸出規則時更新（#150）


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
                "is_group": bool(char.get("is_group", False)) or cid.startswith("EXTRAS"),
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
            m = re.match(r"^-\s*\*\*(style_anchor|style_negative|lighting_lock_line|style_index)\*\*[：:]\s*`([^`]+)`", line)
            if m:
                self.style[m.group(1)] = m.group(2).strip()
                continue
            # 卡片標題
            m = re.match(r"^#{2,4}\s*((?:C|CREATURE|EXTRAS)-[\w-]+|CREATURE-\d+)\s*[　\s]*(.*)$", line)
            if m:
                aid, name = m.group(1), re.sub(r"[（(].*?[)）]", "", m.group(2)).strip() or m.group(1)
                rec = self.characters.setdefault(aid, {
                    "id": aid, "name": name, "desc_en": "", "short_en": "", "desc_zh": "",
                    "ref_img": "", "wardrobe_states": {}, "is_creature": aid.startswith("CREATURE"),
                    "is_group": aid.startswith("EXTRAS"),
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
        if not result.get("desc_en"):
            raise ValueError(
                f"Stage5 binding prop {pid!r} has no English visual description"
                + ("" if result.get("ref_img") else "（也沒有參考圖；沒有圖的道具會以英文描述純文字注入，至少要有描述）")
            )
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


# Stage5 英文層：binding 的 `en_overlay`（舊名 `x_en_overlay`，噩盡島包裝用過）。
# 階段 4 的 Layer 2 常是中文（運鏡、走位、錨點物件、連戲錨、收尾狀態），layer2 檔案綁著階段 4 核准 hash 不能改，
# 所以英文版放在 stage5 binding，編譯時寫進記憶體中的 Layer 2 的 *_en 欄位。
SHOT_OVERRIDE_KEYS = {
    "action_stages_en", "observable_expression_en",
    "movement_en", "blocking_en", "anchor_objects_en", "lips", "show",
}
# 逐鏡可見度（#67）：en_overlay.shots.<gsid>.show = {角色 id: 模式}；未列出的 Subject 視為 absent。
SHOW_MODES = {
    "face": "{L}: face visible, from {P}",
    "profile": "{L}: side profile, face from {P}",
    "back": "{L}: back to camera, face hidden",
    "fg_soft": "{L}: soft out-of-focus foreground shoulder, face hidden",
    "silhouette": "{L}: backlit silhouette, no facial detail",
    "small": "{L}: tiny distant figure, features unreadable",
    "absent": "{L}: not in this shot",
    "visible": "{L}: in frame",
}


def _on_screen_sentence(show: Dict[str, Any], subjects: List[Tuple[int, str, int]]) -> str:
    """subjects = [(k, cid, picture_no)]；回傳 ' On screen: …' 句（沒有 show 就回空字串）。"""
    if not show:
        return ""
    bits: List[str] = []
    groups: Dict[str, List[str]] = {}
    order: List[Any] = []
    for k, cid, pic in subjects:
        mode = str(show.get(cid) or "absent")
        label = f"<Subject {k}>"
        if mode.startswith("part:"):
            bits.append(f"{label}: only {mode[5:].strip()}, face out of frame")
        elif mode not in SHOW_MODES:
            raise ValueError(f"show 模式 {mode!r}（{cid}）不在 {sorted(SHOW_MODES)} 或 part:<部位>")
        elif "{P}" in SHOW_MODES[mode]:
            bits.append(SHOW_MODES[mode].format(L=label, P=f"<Picture {pic}>"))
        else:
            if mode not in groups:
                groups[mode] = []
                bits.append(("@", mode))  # type: ignore[arg-type]
            groups[mode].append(label)
    out = [SHOW_MODES[b[1]].format(L=", ".join(groups[b[1]])) if isinstance(b, tuple) else b for b in bits]
    sentence = " On screen: " + "; ".join(out) + "."
    # #96：參考圖整段共用，遠景空鏡所有 Subject 都 absent 時，自動補空場景句，避免 H3 把人畫出來
    if subjects and all(str(show.get(cid) or "absent") == "absent" for _k, cid, _p in subjects):
        sentence += " The frame is completely empty of people; no person, figure or silhouette appears anywhere in it."
    return sentence
LIPS_MODES = {"closed", "omit"}
# 中文運鏡關鍵字 → H3 官方動詞（依序比對，先比較長、較具體的詞）。
CJK_CAMERA_KEYWORDS: List[Tuple[Tuple[str, ...], str]] = [
    (("環繞", "繞拍"), "camera trucks left while panning right"),
    (("升降", "上升", "升高", "升鏡", "搖臂上"), "cranes up"),
    (("下降", "降鏡", "搖臂下"), "cranes down"),
    (("推近", "推進", "推鏡", "前推", "前移", "短推", "推向", "貼近"), "dollies in"),
    (("拉遠", "拉開", "後拉", "拉鏡", "後退"), "dollies out"),
    (("左搖", "向左搖", "搖向左"), "pans left"),
    (("右搖", "向右搖", "搖向右", "搖攝", "橫搖", "移向"), "pans right"),
    (("上搖", "仰搖", "上仰", "向上搖", "往上搖"), "tilts up"),
    (("下搖", "俯搖", "下俯", "向下搖", "往下搖", "向下跟"), "tilts down"),
    (("由右向左", "向左平移", "左移", "向左滑"), "trucks left"),
    (("由左向右", "向右平移", "右移", "側向滑移", "向右滑", "平移"), "trucks right"),
    (("跟拍", "跟隨", "追拍", "背後跟"), "tracks"),
    (("手持", "晃動", "震動", "搖晃", "抖動"), "handheld"),
    (("固定", "定鏡", "靜止", "鎖定", "不動", "定格"), "static"),
]


def stage5_en_overlay(binding: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """回傳 binding 的英文層（`en_overlay`，相容舊名 `x_en_overlay`）。"""
    if not isinstance(binding, dict):
        return {}
    overlay = binding.get("en_overlay")
    if overlay is None:
        overlay = binding.get("x_en_overlay")
    return overlay if isinstance(overlay, dict) else {}


def ensure_global_shot_ids(layer2_data: Dict[str, Any]) -> Dict[str, Any]:
    """Layer 2 沒有 global_shot_id 時，在記憶體裡用 shot_id 補（段內唯一即可，綁定是逐段驗的）。

    不改檔案：stage5 綁定驗的是 layer2 檔案的 SHA256，補欄位只發生在已讀進來的 dict。
    """
    for shot in layer2_data.get("shots", []) or []:
        if isinstance(shot, dict) and not shot.get("global_shot_id") and shot.get("shot_id"):
            shot["global_shot_id"] = str(shot["shot_id"])
    return layer2_data


PENDING_REFERENCE_KEYS = ("pending_references", "pending_scene_plate", "x_pending_scene_plate")


def stage5_pending_references(binding: Optional[Dict[str, Any]]) -> List[str]:
    """binding 宣告「這張圖還沒出、先編提示詞給人審」的路徑（#55）。

    可以寫字串或字串清單；鍵名 `pending_references`（舊包裝用 `x_pending_scene_plate`）。
    宣告過的路徑編譯時不因「檔案不存在」失敗，但 compile_notes 與 metadata.pending_references 會留記錄，
    送件（submit）看到 pending_references 一律擋下，圖補齊後重編就會消失。
    """
    if not isinstance(binding, dict):
        return []
    out: List[str] = []
    for key in PENDING_REFERENCE_KEYS:
        raw = binding.get(key)
        if raw in (None, "", []):
            continue
        items = [raw] if isinstance(raw, str) else raw
        if not isinstance(items, list) or not all(isinstance(v, str) and v.strip() for v in items):
            raise ValueError(f"Stage5 {key} must be a project-relative path or a list of paths")
        for v in items:
            if pathlib.PurePosixPath(v).is_absolute() or pathlib.PureWindowsPath(v).is_absolute():
                raise ValueError(f"Stage5 {key} must be project-relative: {v}")
            if v not in out:
                out.append(v)
    return out


def _has_cjk(value: Any) -> bool:
    if isinstance(value, dict):
        return any(_has_cjk(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return any(_has_cjk(v) for v in value)
    return bool(CJK_RE.search(str(value or "")))


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
    ensure_global_shot_ids(layer2_data)
    shot_ids = [str(shot.get("global_shot_id") or "") for shot in (layer2_data.get("shots", []) or [])]
    if any(not sid for sid in shot_ids):
        raise ValueError(f"Stage5 binding requires global_shot_id (or shot_id) on every shot in {segment_id}")
    if len(shot_ids) != len(set(shot_ids)):
        raise ValueError(f"Layer2 contains duplicate global_shot_id in {segment_id}")
    known = set(shot_ids)
    for sid, override in (binding.get("shot_overrides", {}) or {}).items():
        if sid not in known:
            raise ValueError(f"Stage5 shot override does not resolve uniquely: {sid}")
        if not isinstance(override, dict) or set(override) - SHOT_OVERRIDE_KEYS:
            raise ValueError(f"Stage5 shot override {sid} may override only {', '.join(sorted(SHOT_OVERRIDE_KEYS))}")
    stage5_pending_references(binding)
    overlay = stage5_en_overlay(binding)
    for sid, entry in (overlay.get("shots") or {}).items():
        if sid not in known:
            raise ValueError(f"Stage5 en_overlay shot does not resolve uniquely: {sid}")
        if not isinstance(entry, dict):
            raise ValueError(f"Stage5 en_overlay.shots[{sid}] must be an object")
        if entry.get("lips") is not None and entry["lips"] not in LIPS_MODES:
            raise ValueError(f"Stage5 en_overlay.shots[{sid}].lips must be 'closed' or 'omit'")
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
        face_ids = shot_binding.get("face_subject_ids")
        if face_ids is not None:
            if not isinstance(face_ids, list) or not all(isinstance(v, str) and v.strip() for v in face_ids):
                raise ValueError(f"Stage5 face_subject_ids for {sid} must be a list of non-empty strings")
        crop_note = shot_binding.get("crop_note_en")
        if crop_note is not None and (not isinstance(crop_note, str) or not crop_note.strip()):
            raise ValueError(f"Stage5 crop_note_en for {sid} must be a non-empty string")
        anchor_ids = shot_binding.get("identity_anchor_ids")
        if anchor_ids is not None:
            if not isinstance(anchor_ids, list) or not all(isinstance(v, str) and v.strip() for v in anchor_ids):
                raise ValueError(f"Stage5 identity_anchor_ids for {sid} must be a list of non-empty strings")
            char_paths = (shot_binding.get("reference_paths", {}) or {}).get("characters", []) or []
            if isinstance(char_paths, dict):
                char_paths = [{"id": key, "reference_image": value} for key, value in char_paths.items()]
            path_ids = {
                entry.get("id") for entry in char_paths
                if isinstance(entry, dict) and entry.get("id")
            }
            visual_ids = set(shot_binding.get("visual_subject_ids") or [])
            for cid in anchor_ids:
                if visual_ids and cid not in visual_ids:
                    raise ValueError(
                        f"Stage5 identity_anchor_ids {cid} for {sid} is not in visual_subject_ids; "
                        f"an identity anchor must be a character that is actually in frame"
                    )
                if cid not in path_ids:
                    raise ValueError(
                        f"Stage5 identity_anchor_ids {cid} for {sid} has no reference_paths.characters entry; "
                        f"背影／側身的重要角色必須掛自己的單視角裁切參考圖，"
                        f"省略參考圖會讓 H3 把別人的臉複製給這個角色"
                    )
    if seen_refs != known:
        missing = sorted(known - seen_refs)
        raise ValueError(f"Stage5 bindings are missing per-shot reference mapping(s): {', '.join(missing)}")
    return binding


def apply_stage5_binding(layer2_data: Dict[str, Any], binding: Dict[str, Any]) -> Dict[str, Any]:
    """Apply permitted derived asset and English translation bindings in memory."""
    data = ensure_global_shot_ids(json.loads(json.dumps(layer2_data, ensure_ascii=False)))
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
        override = dict(shot_override_by_id.get(sid, {}) or {})
        if set(override) - SHOT_OVERRIDE_KEYS:
            raise ValueError(f"Stage5 shot override {sid} may override only {', '.join(sorted(SHOT_OVERRIDE_KEYS))}")
        en_shot = dict((stage5_en_overlay(binding).get("shots") or {}).get(sid) or {})
        en_shot.update({k: override.pop(k) for k in list(override) if k not in ("action_stages_en", "observable_expression_en")})
        _apply_en_shot(shot, en_shot)
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
    _apply_en_segment(data, stage5_en_overlay(binding))
    data["_stage5_binding"] = binding
    return data


def _apply_en_shot(shot: Dict[str, Any], en_shot: Dict[str, Any]) -> None:
    """把逐鏡英文層寫進記憶體中的 Layer 2（只寫 *_en 欄位，原中文保留給人審）。"""
    if en_shot.get("movement_en"):
        shot.setdefault("camera_optics", {})["movement_en"] = str(en_shot["movement_en"])
    blocking = shot.setdefault("spatial_blocking", {})
    if "blocking_en" in en_shot:
        blocking["blocking_desc_en"] = str(en_shot["blocking_en"] or "")
    if "anchor_objects_en" in en_shot:
        blocking["anchor_objects_en"] = [str(v) for v in (en_shot["anchor_objects_en"] or [])]
    if en_shot.get("lips") in LIPS_MODES:
        shot.setdefault("dialogue_and_audio", {})["lips_mode"] = en_shot["lips"]
    # PR-10c：畫外句交給 H3（噩盡島包裝層 G7 的 h3_voice 收進主線）。
    # h3_voice = {"form": "voiceover"|"offscreen", "voice": 英文聲線, "where": 英文位置（選填）}
    hv = en_shot.get("h3_voice")
    if isinstance(hv, dict):
        dlg = shot.setdefault("dialogue_and_audio", {})
        dlg["voice_route"] = "h3"
        if hv.get("voice"):
            dlg["offscreen_voice_en"] = str(hv["voice"])
        if hv.get("where"):
            dlg["offscreen_where_en"] = str(hv["where"])
        if hv.get("form") in ("voiceover", "offscreen"):
            dlg["offscreen_form"] = hv["form"]
    if en_shot.get("voice_route") in VOICE_ROUTES:
        shot.setdefault("dialogue_and_audio", {})["voice_route"] = en_shot["voice_route"]


def _apply_en_segment(data: Dict[str, Any], overlay: Dict[str, Any]) -> None:
    if not overlay:
        return
    style_lock = data.setdefault("style_lock", {})
    if isinstance(overlay.get("continuity_anchors_en"), dict):
        style_lock["continuity_anchors_en"] = dict(overlay["continuity_anchors_en"])
    if overlay.get("lighting_lock_line_en"):
        data.setdefault("metadata", {})["lighting_lock_line"] = str(overlay["lighting_lock_line_en"])
    if isinstance(overlay.get("end_state_en"), dict):
        end_state = data.get("segment_end_state") if isinstance(data.get("segment_end_state"), dict) else {}
        end_state = dict(end_state)
        end_state["planned_final_state_en"] = dict(overlay["end_state_en"])
        data["segment_end_state"] = end_state
    voices = overlay.get("voice_4d_spec_en") or {}
    if isinstance(voices, dict):
        for shot in data.get("shots", []) or []:
            dlg = shot.setdefault("dialogue_and_audio", {})
            spk = dlg.get("speaker")
            if spk and voices.get(spk):
                dlg["voice_4d_spec_en"] = str(voices[spk])
    if isinstance(overlay.get("secondary_desc_en"), dict):
        data["_secondary_desc_en"] = {str(k): str(v) for k, v in overlay["secondary_desc_en"].items() if v}


def _stage5_reference_path_map(binding: Dict[str, Any]) -> Tuple[Dict[str, str], Optional[str], List[Dict[str, Any]], Optional[str], Dict[str, Dict[str, Any]]]:
    """Collect explicit per-shot paths; creature morphology variants remain shot-scoped.

    同時回傳每個素材的綁定中繼資料（asset_meta）：`reference_view`（single_view／non_face／
    panel）、`panel_label_en`（整板查表時指定用哪一格）、`crop_status`。
    這些欄位決定該素材在官方六段式裡怎麼被描述，也決定送件前的門禁怎麼判定。
    """
    paths: Dict[str, str] = {}
    asset_meta: Dict[str, Dict[str, Any]] = {}
    scene_path: Optional[str] = None
    scene_description: Optional[str] = binding.get("scene_description_en")
    if binding.get("scene_reference"):
        scene_path = str(binding["scene_reference"])
    variants: Dict[Tuple[str, str], Dict[str, Any]] = {}
    variant_placeholder: set = set()
    base_creature_ids: set = set()
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
        for group in ("characters", "creatures", "extras", "props", "bodydetails"):
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
                if aid and not image and group == "props":
                    # 沒有設定圖的道具：以文字描述注入提示詞（#54），編譯端另行收集
                    continue
                if not aid or not image:
                    raise ValueError(f"Stage5 reference_paths.{group} entry requires id and reference_image")
                meta = {
                    k: entry[k] for k in ("reference_view", "panel_label_en", "panel_role", "crop_status")
                    if entry.get(k) not in (None, "")
                }
                if meta:
                    existing = asset_meta.get(str(aid), {})
                    merged = {**existing, **meta}
                    for key in ("reference_view", "crop_status"):
                        if key in existing and key in meta and existing[key] != meta[key]:
                            raise ValueError(f"Stage5 asset {aid} has conflicting {key} declarations")
                    asset_meta[str(aid)] = merged
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
                        variant_placeholder.add(aid)
                    continue
                if aid in variant_placeholder:
                    # 同一生物先出現階段變體、後出現基本型（#60）：基本型才是 Subject 的圖，
                    # 變體留在逐鏡範圍內另掛一張 Picture。
                    variant_placeholder.discard(aid)
                    paths[aid] = image
                    if group == "creatures":
                        base_creature_ids.add(str(aid))
                    continue
                if aid in paths and paths[aid] != image:
                    raise ValueError(f"Stage5 asset {aid} has conflicting bound reference paths")
                paths[aid] = image
                if group == "creatures":
                    base_creature_ids.add(str(aid))
    for variant in variants.values():
        variant["has_base"] = variant["id"] in base_creature_ids
    return paths, scene_path, list(variants.values()), scene_description, asset_meta


# ==============================================================================
# H3 六段式 Prompt 編譯核心
# ==============================================================================

FIVE_PART_KEYS = (("camera", "Camera"), ("motion", "Motion"), ("performance", "Performance"),
                  ("light", "Light"), ("sound", "Sound"))


def _five_part_en(shot: Dict[str, Any]) -> Optional[Dict[str, str]]:
    """讀 Layer 2 逐鏡五小節：shot.five_part_en 或 action_and_performance.five_part_en。

    五節必須齊全且非空；缺一節就報錯，不默默退回自動拼句（那正是要禁止的偷懶路徑）。
    """
    raw = shot.get("five_part_en") or (shot.get("action_and_performance") or {}).get("five_part_en")
    if not raw:
        return None
    if not isinstance(raw, dict):
        raise ValueError(f"{shot.get('shot_id')}: five_part_en 必須是物件（camera/motion/performance/light/sound）")
    out = {k: _clean(raw.get(k)) for k, _ in FIVE_PART_KEYS}
    missing = [k for k, v in out.items() if not v]
    if missing:
        raise ValueError(f"{shot.get('shot_id')}: five_part_en 缺 {', '.join(missing)}；每鏡五節都要依分鏡寫出")
    return out


_CAMERA_OPTICS_LEAD = re.compile(r"^\d+\s*mm from [^,;]+[,;]\s*", re.I)


def compact_five_part(five: Dict[str, str]) -> Dict[str, str]:
    """W11 編譯時壓縮：只刪重複資訊，不刪畫面內容。

    - Camera 開頭的「NNmm from X metres at …」與鏡頭標頭的「MCU (85mm, 2m)」重複 → 刪掉；
      後面的運鏡／固定機位／構圖／背景全部保留。
    - Sound 逐鏡只留第一個子句（不足 6 字則整節保留，E30／E31），完整聲音仍在 overall_soundscape。
    - Light／Motion／Performance 原樣保留（光線方向與關鍵細節不可被壓縮掉）。
    """
    out = dict(five)
    cam = _CAMERA_OPTICS_LEAD.sub("", out.get("camera", ""), count=1).strip()
    out["camera"] = (cam[:1].upper() + cam[1:]) if cam else out.get("camera", "")
    snd = re.split(r";\s*", out.get("sound", ""), maxsplit=1)[0].strip()
    if len(re.findall(r"[A-Za-z]+", snd)) >= 8:  # E31：太薄就保留整節
        out["sound"] = snd
    return out


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

    # 4. 中文運鏡：依關鍵字對到官方動詞（階段 4 的 validator 接受中文，編譯器不能只認寫死的逐字句）。
    if CJK_RE.search(raw_lower):
        for keywords, verb in CJK_CAMERA_KEYWORDS:
            if any(k in raw_lower for k in keywords):
                return verb

    # 5. Unknown movement is rejected; never substitute an unrelated motion.
    if not raw_lower or raw_lower in {"unknown", "n/a", "none"}:
        return "static"
    raise ValueError(
        f"不支援的 camera movement: {raw_movement!r}；請在 Layer 2 camera_optics.movement_en "
        f"或 stage5 binding en_overlay.shots[<鏡>].movement_en 寫官方英文運鏡動詞")


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
    # An explicit statement that the speaker's mouth is visible wins over generic
    # off-screen words, which often describe the *listener* ("looking at {C-x} off-screen").
    visible_terms = (
        "mouth is clearly visible", "mouth clearly visible", "mouth is visible", "mouth visible",
        "lips visible", "lips are visible", "嘴部可見", "看得到嘴", "露嘴",
    )
    hidden_terms = (
        "never appears", "no speaking mouth", "mouth is out of view", "mouth out of view",
        "mouth remains unseen", "嘴部不可見", "不顯示聲源嘴部", "不露臉",
    )
    negated = re.search(r"\b(?:no|not|never|without)\b[^.;,]{0,30}\b(?:mouth|lips)\b", text)
    if dlg.get("mouth_visible") is False or negated or any(term in text for term in hidden_terms):
        return "offscreen"
    if dlg.get("mouth_visible") is True or any(term in text for term in visible_terms):
        return "mouth_hidden" if dlg.get("lips_closed_lock") else "visible"
    # Drop "<target> off-screen" phrases that place someone else outside the frame.
    text = re.sub(r"\b(?:at|to|toward|towards)\s+\{?[\w\- <>]+\}?\s+off-?screen", " ", text)
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
    """回傳穩定的說話人稱呼（不含資產 ID）。

    官方格式要求說話人以 `<Subject N> (Sx)` 綁定；對應不到 Subject 的發聲者
    改用「穩定音色描述 + (Sx)」。因此本函式只負責產生描述，編號另外附加。
    """
    if not speaker:
        return "the authored speaker"
    if is_narrator(speaker):
        return "the narrator"
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
    return label


def _assign_speaker_ids(shots: List[Dict[str, Any]]) -> Dict[str, str]:
    """依第一次發聲順序，為每個發聲來源配發官方穩定代號 (S1)、(S2)…

    官方 base 指南 §4.4：「Subjects who speak, sing, or produce an off-screen
    human voice use stable IDs such as (S1) and (S2).」同一說話人跨鏡沿用同一代號。
    """
    ids: Dict[str, str] = {}
    for shot in shots:
        dlg = shot.get("dialogue_and_audio", {}) or {}
        if not (dlg.get("has_dialogue") or dlg.get("line_verbatim")):
            continue
        speaker = dlg.get("speaker")
        if not speaker:
            continue
        key = str(speaker)
        if key not in ids:
            ids[key] = f"S{len(ids) + 1}"
    return ids


def _align_speaker_ids(ids: Dict[str, str], selected: List[str]) -> Dict[str, str]:
    """說話者代號對齊 Subject 編號（#66）：<Subject k> 的代號一律 (Sk)，其餘發聲者接在最後一號之後。"""
    if not ids:
        return ids
    new: Dict[str, str] = {}
    for k, cid in enumerate(selected, start=1):
        if cid in ids:
            new[cid] = f"S{k}"
    nxt = len(selected) + 1
    for cid in ids:
        if cid not in new:
            new[cid] = f"S{nxt}"
            nxt += 1
    return new


def _strip_dialogue_from_soundscape(foley: str, spoken_lines: List[str]) -> str:
    """從環境音描述中移除逐字台詞。

    官方 §4.6 / ref-en §6：「Dialogue, singing, and diegetic music already belong
    in the multimodal description and should not be repeated here.」環境音欄只留
    環境與動作音，否則 H3 會在環境音軌再念一次台詞。
    """
    text = foley or ""
    for line in spoken_lines:
        stripped = (line or "").strip()
        if len(stripped) >= 4 and stripped in text:
            text = text.replace(stripped, "")
    # 移除殘留的 <d> 標記與其內容
    text = re.sub(r"<d>\[[^\]]*\][^<]*</d>", "", text)
    text = re.sub(r"\s{2,}", " ", text).strip()
    text = re.sub(r"\s+([,.;:])", r"\1", text)
    return text.strip()


# 畫外音／旁白政策（PR-10c，findings #104 #114 #122 #123）。
#   short-offscreen-h3（預設）：短畫外句（O.S.）與短旁白（V.O.）留給 H3 直接生成，用官方句式＋逐字 <d>；
#                              超過 SHORT_OFFSCREEN_MAX_CHARS 字或 voice_route=external 才改外部 TTS。
#   external：所有沒有可見嘴的台詞都改外部 TTS（H3 這鏡不提任何人說話，只留環境音）。
#   h3-native：所有沒有可見嘴的台詞都留 H3（不看長度）。
# 逐句可用 dialogue_and_audio.voice_route = "h3" | "external" 覆寫政策。
NARRATION_POLICIES = ("short-offscreen-h3", "external", "h3-native")
DEFAULT_NARRATION_POLICY = "short-offscreen-h3"
# 實測（噩盡島 EP01 S02-b／S02-d／S03-e，拼音相似度 1.00）都是 ≤15 字的短句；更長的句子未驗證。
SHORT_OFFSCREEN_MAX_CHARS = 15
VOICE_ROUTES = ("h3", "external")
# #123：畫外句同鏡的 Expression 寫張嘴／喘氣，H3 會讓露臉者跟著開口，像他在說話（與 voice_lint E44 同一條）。
MOUTH_OPEN_RE = voice_lint.MOUTH_OPEN_RE


def _spoken_char_count(line: str) -> int:
    """台詞字數：中日韓字＋英數字，不算標點與空白（「氣已極淡……等久了？」= 7）。"""
    return len(re.findall(r"[\u3040-\u30ff\u3400-\u9fff\uf900-\ufaffA-Za-z0-9]", line or ""))


def _offscreen_route(policy: str, dlg: Dict[str, Any], line: str) -> str:
    """回傳 "h3" 或 "external"：沒有可見嘴的這一句該由誰發聲。"""
    route = str(dlg.get("voice_route") or "").strip().lower()
    if route in VOICE_ROUTES:
        return route
    if policy == "external":
        return "external"
    if policy == "h3-native":
        return "h3"
    return "h3" if _spoken_char_count(line) <= SHORT_OFFSCREEN_MAX_CHARS else "external"


def _possessive_list(tags: List[str]) -> str:
    owners = [f"{t}'s" for t in tags]
    if len(owners) <= 2:
        return " and ".join(owners)
    return ", ".join(owners[:-1]) + ", and " + owners[-1]


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


def _shot_speaker_has_visible_mouth(shot: Dict[str, Any], registry: AssetRegistry) -> bool:
    """判斷這句台詞的說話人是否有「可見的嘴」。

    官方 base §4.4：發聲者（含畫外音）都要有穩定 (Sx) 代號；而沒有可見嘴的台詞
    不該由 H3 內建語音生成（見 --narration-policy external）。這個判斷同時決定
    「要不要掛音色參考 <Audio N>」：只有 H3 自己要念出來的台詞才需要音色參考。
    """
    dlg = shot.get("dialogue_and_audio", {}) or {}
    if not (dlg.get("has_dialogue") or dlg.get("line_verbatim")):
        return False
    speaker = dlg.get("speaker")
    if not speaker:
        return False
    if _is_voiceover(shot):
        return False
    record = registry.characters.get(speaker, {}) or {}
    if record.get("no_visual_reference") or record.get("voice_only"):
        return False
    return _dialogue_visibility(shot) == "visible"


def _english_voice_descriptor(dlg: Dict[str, Any], notes: Optional[List[str]] = None) -> str:
    """取出可直接放進英文提示詞的音色描述。

    優先用 voice_4d_spec_en；若只有中文的 voice_4d_spec，不直接塞進英文提示詞
    （H3 提示詞正文用英文，中文描述會變成未翻譯噪音），但會記進 compile_notes 提醒。
    """
    for key in ("voice_4d_spec_en", "voice_profile_en"):
        value = _clean(dlg.get(key))
        if value and not CJK_RE.search(value):
            return value.rstrip(".。 ")
    value = _clean(dlg.get("voice_4d_spec"))
    if value and not CJK_RE.search(value):
        return value.rstrip(".。 ")
    if value and notes is not None:
        notes.append(
            "voice_4d_spec 只有中文描述，未寫入英文提示詞（H3 提示詞正文是英文）；"
            "請改填 voice_4d_spec_en，否則同一角色在不同段的音色描述不一致。"
        )
    return ""


def _lips_closed_wanted(shot: Dict[str, Any], registry: "AssetRegistry", no_visual_ids: set) -> bool:
    """這鏡要不要加閉唇句：只有「看得到臉且不說話」的鏡需要。

    優先序：stage5 en_overlay 的 lips（closed／omit）→ Layer 2 `lips_closed_lock`（明寫 true／false）→
    鏡內有沒有看得到的角色（空景、只有只出聲角色的鏡不加）。
    """
    dlg = shot.get("dialogue_and_audio", {}) or {}
    mode = dlg.get("lips_mode")
    if mode in LIPS_MODES:
        return mode == "closed"
    if "lips_closed_lock" in dlg and dlg.get("lips_closed_lock") is not None:
        return bool(dlg.get("lips_closed_lock"))
    if "character_ids" not in shot:
        return True  # 舊格式沒標在場角色：維持舊行為
    for cid in shot.get("character_ids", []) or []:
        if not cid or is_narrator(cid) or cid in no_visual_ids:
            continue
        record = registry.characters.get(cid, {}) or {}
        if record.get("no_visual_reference") or record.get("voice_only"):
            continue
        return True
    return False


def _english_anchor_objects(values: Any, registry: "AssetRegistry", notes: List[str], shot_id: Any) -> List[str]:
    """錨點物件只輸出英文：道具 ID 換成道具英文描述，殘留中文的項目略過並記一條 note。"""
    out: List[str] = []
    dropped: List[str] = []
    for raw in values or []:
        text = str(raw or "").strip()
        if not text:
            continue
        if text in getattr(registry, "props", {}):
            desc = (registry.props[text].get("desc_en") or "").split(",")[0].strip()
            text = desc or ""
            if not text:
                dropped.append(str(raw))
                continue
        if _has_cjk(text):
            dropped.append(text)
            continue
        out.append(text)
    if dropped:
        notes.append(f"{shot_id} 錨點物件有中文或無英文描述的道具，未寫進英文提示詞：{'、'.join(dropped[:5])}；請補 anchor_objects_en")
    return out


def compile_segment_h3(
    layer2_data: Dict[str, Any],
    registry: AssetRegistry,
    max_char_refs: int = 1,
    auto_lora: bool = True,
    rounding_mode: str = "floor",
    stage5_binding: Optional[Dict[str, Any]] = None,
    narration_policy: str = DEFAULT_NARRATION_POLICY,
    allow_normalize_warnings: bool = False,
    embed_cut_markers: bool = False,
    previous_end_state: Optional[Dict[str, Any]] = None,
    no_lettering: bool = True,
    compact_description: bool = False,
) -> Dict[str, Any]:
    """將單個 Layer 2 JSON 分鏡檔編譯為符合 H3 官方六段式規範的資料結構。

    主角參考圖：asset_refs.primary_character / metadata.primary_character 優先；
    否則取臉戲權重（景別越近權重越高）最重的角色。旁白與畫外音永不成為主體。

    narration_policy（沒有可見嘴的台詞：畫外 O.S.、旁白／內心獨白 V.O.、背影／遮嘴）：
      - "short-offscreen-h3"（預設）：≤15 字的短句留給 H3，用官方句式寫逐字 <d>
        （O.S.：the line is heard from X (Sn) off-screen, <聲線>: <d>…</d>；
        V.O.：X (Sn) says in an off-screen voiceover, <聲線>: <d>…</d>），露臉者寫嘴閉合、
        沒有臉寫 no face is on screen；長句才改外部 TTS（external_narration）。
      - "external"：全部改外部 TTS，H3 這一鏡不提任何人說話，只留環境與動作音。
      - "h3-native"：全部留 H3（不看長度），句式同上。
      逐句 dialogue_and_audio.voice_route = "h3"／"external" 可覆寫。

    previous_end_state：同場景前一段的 segment_end_state（#133）。有英文終態時，
    寫成本段第 1 鏡的「Starting state carried over from the previous segment」句，
    讓人物從前段終態接起，而不是回到參考圖站姿。
    no_lettering：提示詞出現校徽、計程車、斑駁牆這類燒字來源時，自動補一句
    「表面素淨、無文字無塗鴉」（#138）；metadata.allow_lettering=true 的段不加。
    """
    if narration_policy not in NARRATION_POLICIES:
        raise ValueError(f"narration_policy 必須是 {'、'.join(NARRATION_POLICIES)} 之一，收到 {narration_policy!r}")
    # 正規化層（P3）：先把同義欄位與時間軸收斂，避免「合法欄位被誤報缺」
    # 或「duration 與 end-start 不一致卻照算」。strict=False 只把可自動修正的
    # 問題降級為 warning；結構性錯誤（缺時間軸、重複 shot_id、panel 缺格位）仍會拋錯。
    try:
        layer2_data = normalize_mod.normalize_layer2(layer2_data, strict=False, strict_aliases=False)
    except normalize_mod.NormalizationError as exc:
        raise ValueError(f"Layer 2 正規化失敗（{layer2_data.get('segment_id', 'unknown')}）：{exc}") from exc
    normalization = layer2_data.get("_normalization") or {}
    norm_warnings = list(normalization.get("warnings") or [])
    if norm_warnings and not allow_normalize_warnings:
        # 警告不是裝飾：時間軸（shot 級）不一致或台詞窗越界會直接產生錯片與錯字幕。
        raise ValueError(
            "Layer 2 正規化警告不得靜默通過（時間軸／台詞窗；如確認可接受請加 "
            "--allow-normalize-warnings）：\n- " + "\n- ".join(norm_warnings)
        )
    if stage5_binding is not None and layer2_data.get("_stage5_binding") is not stage5_binding:
        layer2_data = apply_stage5_binding(layer2_data, stage5_binding)
    if stage5_binding is None:
        stage5_binding = layer2_data.get("_stage5_binding")
    ensure_global_shot_ids(layer2_data)
    secondary_desc_en: Dict[str, str] = dict(layer2_data.get("_secondary_desc_en") or {})
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
    seg_frames = h3_spec.frames_for(target_dur, rounding=selected_rounding_mode)
    eff_d = effective_duration(target_dur, rounding=selected_rounding_mode)
    # Treat authored shot timings as one continuous source timeline, then
    # adjust only the final shot to the effective H3 duration.
    shots = [dict(shot) for shot in shots]
    # 官方 base §4.4：說話人要有穩定 (Sx) 代號，同一說話人跨鏡沿用同一代號。
    speaker_ids = _assign_speaker_ids(shots)
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
    normalization = layer2_data.get("_normalization") or {}
    for warning in normalization.get("warnings") or []:
        notes.append(f"[normalize] {warning}")
    for note in normalization.get("notes") or []:
        notes.append(f"[normalize] {note}")
    aliases = normalization.get("aliases_applied") or []
    if aliases:
        notes.append(f"[normalize] 已收斂 {len(aliases)} 處同義欄位（詳見 _normalization.aliases_applied）")

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
    # Single readable face (Stage5 face_subject_ids): see the bindings branch below.
    face_subject_ids: List[str] = []
    # Identity-anchored characters (Stage5 identity_anchor_ids): in frame but never
    # face-readable. They still carry their own single-view reference so H3 never
    # clones another character's face onto them.
    identity_anchor_ids: List[str] = []
    crop_notes: List[str] = []
    single_face_mode = False
    unanchored_stage5: List[str] = []
    asset_meta: Dict[str, Dict[str, Any]] = {}
    pending_refs = set(stage5_pending_references(stage5_binding))
    if stage5_binding:
        ref_path_map, bound_scene_path, creature_variants, bound_scene_description, asset_meta = _stage5_reference_path_map(stage5_binding)
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
            if not registry.path_exists(rel) and rel not in pending_refs:
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
        # Single readable face: a shot binding may name the characters whose faces are
        # actually readable (face_subject_ids). Everyone else who appears in the shot
        # stays in frame but is described rather than referenced, so H3 keeps one
        # identity instead of averaging several faces into one.
        face_subject_ids: List[str] = []
        crop_notes: List[str] = []
        for shot_binding in stage5_binding.get("shots", []) or []:
            for cid in (shot_binding.get("face_subject_ids", []) or []):
                if cid not in face_subject_ids:
                    face_subject_ids.append(cid)
            for cid in (shot_binding.get("identity_anchor_ids", []) or []):
                if cid not in identity_anchor_ids:
                    identity_anchor_ids.append(cid)
            note = _clean(shot_binding.get("crop_note_en") or "")
            if note and note not in crop_notes:
                crop_notes.append(note)
        single_face_mode = bool(face_subject_ids)
        # 整板查表模式（reference_view=panel）：允許直接餵四視圖板，但必須宣告用哪一格。
        # 官方 ComfyUI 指引允許多格板，只要「獨立編號、逐格描述、鏡頭指向某一格」；
        # 本技能把它限制在「不露臉的身份錨點」用途，並用 partially_preserved 明文
        # 宣告只用那一格、其餘格與正面臉都不匯入。
        panel_anchor_ids: List[str] = []
        bound_visual_ids = {
            cid for b in (stage5_binding.get("shots", []) or [])
            for cid in (b.get("visual_subject_ids") or [])
        }
        for cid, meta in asset_meta.items():
            if meta.get("reference_view") != "panel":
                continue
            if not str(meta.get("panel_label_en") or "").strip():
                raise ValueError(
                    f"Stage5 asset {cid} 宣告 reference_view=panel，必須同時提供 panel_label_en "
                    f"（說明用哪一格，例如「the fourth figure from the left, a full-body back view」）；"
                    f"沒有指定格位的整板會被模型整張複製進成片"
                )
            if cid in face_subject_ids:
                raise ValueError(
                    f"Stage5 asset {cid} 同時是可辨識人臉與整板查表；整板查表只能用於不露臉的身份錨點，"
                    f"可辨識正臉必須用單視角裁切"
                )
            if cid not in bound_visual_ids:
                # 沒有在場就不該變成 Subject；宣告與在場名單不一致要講清楚。
                notes.append(
                    f"整板查表素材 {cid} 沒有出現在任何一鏡的 visual_subject_ids，已略過（不會變成 Subject）"
                )
                continue
            if cid not in panel_anchor_ids:
                panel_anchor_ids.append(cid)
        for cid in panel_anchor_ids:
            if cid not in identity_anchor_ids:
                identity_anchor_ids.append(cid)
        # 背影／側身的重要角色不可省略自己的參考圖：官方 Ref2VA 只有四個保留標記，
        # 沒有「忽略」語意，唯一能表達「只留服裝與體型、不要臉」的是
        # partially_preserved 加上明文說明。省略參考圖會讓模型把唯一一張臉複製給他
        # （本專案 2026-10-19 實測 4/4 段出現複製人）。
        for cid in identity_anchor_ids:
            if cid in no_visual_ids:
                raise ValueError(f"Stage5 lists {cid} as an identity anchor but marks it as having no visual reference")
            if not ref_path_map.get(cid):
                raise ValueError(
                    f"Stage5 identity_anchor_ids 要求 {cid} 掛上自己的參考圖（背面／側身單視角裁切，"
                    f"或宣告 reference_view=panel 的整板查表），但 reference_paths.characters 沒有提供；"
                    f"省略參考圖會讓 H3 把別人的臉複製給這個角色"
                )
            if cid in face_subject_ids:
                raise ValueError(f"Stage5 lists {cid} as both a readable face and an identity anchor; a character is one or the other")
        for shot in shots:
            bound_shot = next((b for b in stage5_binding.get("shots", []) or []
                               if b.get("global_shot_id") == shot.get("global_shot_id")), {})
            ids = bound_shot.get("visual_subject_ids") or shot.get("character_ids", []) or []
            for cid in ids:
                if not cid or cid in no_visual_ids or cid in visual_order:
                    continue
                info = registry.get_character(cid, wardrobe_state=costume_of.get(cid) or seg_wardrobe)
                if (single_face_mode and not (info.get("is_creature") or info.get("is_group"))
                        and cid not in face_subject_ids and cid not in identity_anchor_ids):
                    # 在場但既不是可辨識人臉、也不是身份錨點：不得靜默退回角色聖經的
                    # 整板參考圖（那會讓背景長出同款複製人），也不得只留文字描述
                    # （那會讓模型把別人的臉複製給他）。交給 E19 門禁要求補圖或移出畫面。
                    # 生物／怪物不受這個分流影響：牠們沒有「臉」可讀，一律要有自己的參考。
                    unanchored_stage5.append(cid)
                    continue
                if info.get("no_visual_reference") or info.get("voice_only"):
                    if cid in explicit_visual_ids or cid in ref_path_map:
                        raise ValueError(f"Stage5 marks {cid} as visually present but the normalized Bible forbids a visual reference")
                    continue
                if cid:
                    visual_order.append(cid)
        if single_face_mode:
            for cid in face_subject_ids:
                if cid in no_visual_ids:
                    raise ValueError(f"Stage5 lists {cid} as a readable face but marks it as having no visual reference")
                if not ref_path_map.get(cid):
                    raise ValueError(
                        f"Stage5 face_subject_ids 要求 {cid} 掛上自己的參考圖（正面單視角裁切），"
                        f"但 reference_paths.characters 沒有提供"
                    )
                if cid not in visual_order:
                    visual_order.append(cid)
            for cid in identity_anchor_ids:
                if cid not in visual_order:
                    visual_order.append(cid)
            # 混臉風險只計算「可辨識人臉」；背影／側身的無臉裁切不會被平均成一張臉。
            human_faces = [cid for cid in face_subject_ids
                           if not registry.get_character(cid, wardrobe_state=costume_of.get(cid) or seg_wardrobe).get("is_creature")]
            if len(human_faces) > 1:
                notes.append(
                    "Stage5 face_subject_ids 宣告了多張可辨識人臉，H3 可能把不同角色平均成同一張臉（混臉風險）"
                )
        for group in (asset_refs.get("characters", []) or [], asset_refs.get("creatures", []) or [], asset_refs.get("extras", []) or []):
            for entry in group:
                cid = entry.get("id") if isinstance(entry, dict) else entry
                if cid and cid not in no_visual_ids and cid not in visual_order:
                    rec = registry.get_character(cid, wardrobe_state=costume_of.get(cid) or seg_wardrobe)
                    if (single_face_mode and not (rec.get("is_creature") or rec.get("is_group"))
                            and cid not in face_subject_ids and cid not in identity_anchor_ids):
                        # cropped out of frame: keep as a text-only secondary subject
                        continue
                    visual_order.append(cid)
        for cid in ref_path_map:
            if cid in registry.characters and cid not in no_visual_ids and cid not in visual_order:
                rec = registry.get_character(cid, wardrobe_state=costume_of.get(cid) or seg_wardrobe)
                if (single_face_mode and not (rec.get("is_creature") or rec.get("is_group"))
                        and cid not in face_subject_ids and cid not in identity_anchor_ids):
                    continue
                visual_order.append(cid)
        if primary and primary in visual_order:
            visual_order.remove(primary)
            visual_order.insert(0, primary)
        for cid in visual_order:
            info = registry.get_character(cid, wardrobe_state=costume_of.get(cid) or seg_wardrobe)
            if info.get("no_visual_reference") or info.get("voice_only"):
                raise ValueError(f"Stage5 marks {cid} as visually present but the normalized Bible forbids a visual reference")
            # Stage5 綁定是明確的量產指示：角色參考圖必須來自綁定的單視角裁切，
            # 不得靜默退回角色聖經的整張設定板（那會讓背景長出同款複製人）。
            if not ref_path_map.get(cid):
                raise ValueError(
                    f"Stage5 visible character/creature {cid} has no approved reference image；"
                    f"請在 reference_paths.characters 綁定單視角裁切（正面頭像或背面全身），"
                    f"不可沿用角色聖經的整張四視圖板"
                )
        selected = visual_order
        secondary = [cid for cid in ranked if cid not in selected]
    else:
        selected = [cid for cid in ranked if cid not in no_visual_ids][:max(1, max_char_refs)]
        secondary = [cid for cid in ranked if cid not in selected]
    # #66：<Subject k> 的說話者代號一律 (Sk)，其他發聲者接在後面
    speaker_ids = _align_speaker_ids(speaker_ids, selected)

    # ---------- 未錨定的在場人物（複製人主因，送件前由 E19 攔截） ----------
    in_frame_ids: List[str] = []
    for shot in shots:
        for cid in (shot.get("character_ids") or []):
            if cid and cid not in in_frame_ids:
                in_frame_ids.append(cid)
    if stage5_binding:
        for shot_binding in stage5_binding.get("shots", []) or []:
            for cid in (shot_binding.get("visual_subject_ids") or []):
                if cid and cid not in in_frame_ids:
                    in_frame_ids.append(cid)
    unanchored_in_frame: List[str] = []
    for cid in in_frame_ids:
        if cid in selected or cid in no_visual_ids:
            continue
        info = registry.get_character(cid, wardrobe_state=costume_of.get(cid) or seg_wardrobe)
        if info.get("no_visual_reference") or info.get("voice_only") or is_narrator(cid):
            continue
        unanchored_in_frame.append(cid)
    for cid in unanchored_stage5:
        if cid not in unanchored_in_frame:
            unanchored_in_frame.append(cid)
    if unanchored_in_frame:
        notes.append(
            f"未錨定在場人物（會被 H3 補成複製臉）：{', '.join(unanchored_in_frame)}。"
            f"請為其掛上自己的單視角裁切參考圖並在 stage5 綁定 identity_anchor_ids，或把該角色移出畫面。"
        )

    first_variant_by_id: Dict[str, Dict[str, Any]] = {}
    for variant in creature_variants:
        # 同段也綁了基本型（has_base）時，Subject 用基本型圖，所有變體都是逐鏡範圍的補充 Picture。
        if not variant.get("has_base"):
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
    # ---------- 音色參考 <Audio N>（官方獨立編號） ----------
    # 官方 ref-en §2.4：<Audio N> 是可單獨追蹤的參考音訊，用途之一是「參考說話人的音色與語氣」。
    # 綁定格式：stage5 的 audio_references[{id, path, character_id, role, description_en}]。
    # 只有「這一段 H3 真的要念出來」的說話人才需要音色參考；畫外音已外部化成 TTS，不需要。
    on_screen_speakers: List[str] = []
    for shot in shots:
        speaker = (shot.get("dialogue_and_audio", {}) or {}).get("speaker")
        if speaker and _shot_speaker_has_visible_mouth(shot, registry) and speaker not in on_screen_speakers:
            on_screen_speakers.append(speaker)
    audio_refs: List[Dict[str, Any]] = []
    for entry in (stage5_binding or {}).get("audio_references", []) or []:
        if not isinstance(entry, dict):
            raise ValueError("Stage5 audio_references entries must be objects")
        character_id = entry.get("character_id")
        if character_id and character_id not in on_screen_speakers:
            notes.append(
                f"音色參考 {entry.get('id')} 對應的角色 {character_id} 在本段沒有可見嘴的台詞，"
                f"已略過（畫外音由外部 TTS 負責，不需掛 H3 音色參考）"
            )
            continue
        if not entry.get("path"):
            raise ValueError(f"Stage5 audio_references entry {entry.get('id')} requires path")
        audio_refs.append({
            "id": str(entry.get("id") or ""),
            "path": str(entry.get("path")),
            "character_id": character_id,
            "description": _clean(entry.get("description_en") or entry.get("desc_en") or ""),
            "role": str(entry.get("role") or "voice-timbre"),
        })
    # <Audio N> 的編號在音訊類別內獨立從 1 開始（官方 ref-en §2.5），
    # 先於主體編號決定，才能在 <Subject N> 的定義句裡直接綁定。
    audio_tag_of: Dict[str, str] = {}
    audio_ref_entries: List[Tuple[Dict[str, Any], str, Optional[str]]] = []
    for idx, ref in enumerate(audio_refs, start=1):
        tag = f"<Audio {idx}>"
        audio_tag_of[str(ref.get("character_id") or "")] = tag
        audio_ref_entries.append((ref, tag, speaker_ids.get(str(ref.get("character_id") or ""))))
    for k, cid in enumerate(selected, start=1):
        info = char_info(cid)
        tag_of[cid] = f"<Subject {k}>"
        subject_picture_no[cid] = k + 1
        is_identity_anchor = cid in identity_anchor_ids
        meta = asset_meta.get(cid, {})
        is_panel_anchor = meta.get("reference_view") == "panel"
        panel_label = str(meta.get("panel_label_en") or "").strip()
        panel_role = str(meta.get("panel_role") or "back").strip() or "back"
        reference_images.append({
            "id": info["id"], "type": "extras" if info.get("is_group") else ("creature" if info.get("is_creature") else "character"),
            "description": info["desc_en"], "path": info["ref_img"],
            "is_primary_character": k == 1,
            **({"costume_id": costume_of.get(cid)} if costume_of.get(cid) else {}),
            **({
                "reference_view": "panel" if is_panel_anchor else ("non_face" if is_identity_anchor else "single_view"),
                **({"panel_label_en": panel_label} if is_panel_anchor else {}),
                **({"panel_role": panel_role} if is_panel_anchor else {}),
                **({"crop_status": "single_view"} if is_identity_anchor and not is_panel_anchor else {}),
            } if is_identity_anchor else {}),
        })
        desc = info["desc_en"] or info["name"]
        disp_name = str(info.get("name") or cid)
        if is_identity_anchor and not costume_of.get(cid) and not is_panel_anchor:
            notes.append(f"[背影錨點] {cid} 沒有 costume_id：背面全身圖的服裝不會寫進提示詞；"
                         f"請在 reference_paths.characters 為它登記 costume_id（或確認 asset_refs 已登記該錨點）")
        if is_panel_anchor:
            # 整板查表：官方 ComfyUI 指引允許多格板，但必須逐格描述、鏡頭指向某一格。
            # 這裡把「只用這一格、其餘格與正面臉都不匯入」寫進兩段式欄位。
            if panel_role == "creature":
                subject_tail = ("that panel is the only part of the sheet used, and the creature's other "
                                "panels are not imported into the target video.")
                retention_tail = ("the other panels of that sheet and its neutral gray studio background are "
                                  "not imported, and no duplicate creature appears in the target video.")
            elif panel_role == "profile":
                subject_tail = ("that panel is the only part of the sheet used, and only the three-quarter "
                                "profile from it may appear in the target video.")
                retention_tail = ("the other panels of that sheet and its neutral gray studio background are "
                                  "not imported, and the frontal face from that sheet is not imported.")
            else:
                subject_tail = ("that panel is the only part of the sheet used, and the face is never shown "
                                "in the target video.")
                retention_tail = ("the other panels of that sheet and its neutral gray studio background are "
                                  "not imported, and no face appears in the target video.")
            subject_def_lines.append(
                f"<Subject {k}> is {panel_label} of <Picture {k + 1}>, {desc}; {subject_tail}"
            )
            retention_lines.append(
                f"<Subject {k}> (appears across shots): partially_preserved - only {panel_label} of "
                f"<Picture {k + 1}> is used: the hair, the headwear, the wardrobe and the body silhouette are "
                f"retained; {retention_tail}"
            )
        elif is_identity_anchor:
            # 背影／側身角色的參考圖不含可見正臉；用官方 partially_preserved 說明
            # 保留哪些特徵，正面臉不匯入。
            subject_def_lines.append(
                f"<Subject {k}> is the figure in <Picture {k + 1}> (a full-body back-view reference of {disp_name}), "
                f"{(info.get('back_en') or desc)}; this reference shows the "
                f"character from behind, and the face is never shown in the target video."
            )
            ret = (
                f"<Subject {k}> (appears across shots): partially_preserved - the hairstyle, the headwear, "
                f"the wardrobe and the body silhouette from <Picture {k + 1}> are retained; the reference "
                f"face is not imported and never appears in the target video."
            )
            ret += " Ignore the neutral gray studio background of the reference sheet."
            retention_lines.append(ret)
        elif info.get("is_group"):
            # 群演參考圖（定律一第④條）：人群有自己的身分來源，不會被補成主角的複製臉。
            subject_def_lines.append(
                f"<Subject {k}> is the group of background extras in <Picture {k + 1}> ({disp_name}; "
                f"a crowd group reference), {desc}; they stay in the background as a group.")
            retention_lines.append(
                f"<Subject {k}> (appears across shots): partially_preserved - the wardrobe, palette, ages and "
                f"varied builds of the group in <Picture {k + 1}> are retained; the extras keep varied, "
                f"distinct ordinary faces and never take the face or wardrobe of any other subject.")
        else:
            kind_label = ("a single-view creature crop" if info.get("is_creature")
                          else "a head-and-shoulders face crop of this one person")
            subject_def_lines.append(
                f"<Subject {k}> is the character in <Picture {k + 1}> ({disp_name}; reference image "
                f"{k + 1}, {kind_label}), {desc}.")
            if info.get("is_creature"):
                # 生物沒有髮型與服裝；沿用人類模板會把 H3 引向「人臉」（#60）
                ret = (f"<Subject {k}> (appears across shots): fully_preserved - "
                       f"{creature_lint.head_retention_clause(info.get('desc_en') or '', k + 1)}.")
                for _w in creature_lint.lint_creature_text(info.get("id") or disp_name, info.get("desc_en") or "", []):
                    notes.append(_w)
                ret += " Ignore neutral gray/white studio background of creature turnaround sheet."
            else:
                ret = f"<Subject {k}> (appears across shots): fully_preserved - the facial identity, hairstyle, and wardrobe from <Picture {k + 1}> are retained."
            retention_lines.append(ret)
        # 音色綁定採用 FreeVideo 導演台自己的慣例（與 <Picture N> shows its appearance 對稱）：
        # 「<Audio N> is its voice」。主體與音色的關係寫在主體那一行，H3 較不容易錯配。
        voice_tag = audio_tag_of.get(cid)
        if voice_tag:
            subject_def_lines[-1] += f" {voice_tag} is its voice."
        if not info["desc_en"]:
            notes.append(f"{cid} 缺英文固定描述片段")

    secondary_short: Dict[str, str] = {}
    for cid in secondary:
        info = char_info(cid)
        voice_only = (cid in no_visual_ids or info.get("no_visual_reference") or info.get("voice_only"))
        if secondary_desc_en.get(cid):
            # 段落專用描述（例如巨鳥成形前只是一片紅光）：取代角色聖經的完整外觀。
            text = secondary_desc_en[cid].rstrip(" .")
            retention_lines.append(f"Secondary presence described in text only, without reference image: {text}.")
            secondary_short[cid] = text
            continue
        if voice_only:
            # 只出聲的角色：不寫外觀，否則 H3 會把它畫出來（畫外說話者被畫成在場的人）。
            retention_lines.append(
                "A voice-only presence is heard in this segment but never appears on screen; "
                "no figure, creature or face is drawn for it.")
            secondary_short[cid] = "the unseen voice"
            continue
        desc = info["desc_en"] or info["name"]
        retention_lines.append(f"Secondary character appears as pure text description without reference image: {desc}.")
        w = (info.get("wardrobe_states", {}).get(costume_of.get(cid) or "", {}) or {})
        w_desc = w.get("desc_en") if isinstance(w, dict) else ""
        secondary_short[cid] = info["short_en"] + (f", {w_desc}" if w_desc else "")

    if single_face_mode:
        holders = [cid for cid in face_subject_ids if cid in selected]
        if holders:
            names = ", ".join((registry.get_character(cid).get("name") or cid) for cid in holders)
            verb = "carries" if len(holders) == 1 else "carry"
            line = f"{names} {verb} the readable face in this segment"
            if crop_notes:
                line += ". " + " ".join(crop_notes)
            retention_lines.append(line)

    # ---------- 音色參考 <Audio N>：官方獨立編號，與 <Picture>/<Subject> 分開 ----------
    # 官方 ref-en §2.4：<Audio 1> is the voice-timbre reference for <Subject 1> (S1).
    # 官方 ref-en §4.1 音訊的保留標記是 reference：只參考音色與語氣，不複製原訊號。
    for ref, tag, speaker_id in audio_ref_entries:
        subject_tag = tag_of.get(str(ref.get("character_id") or ""))
        desc = ref.get("description") or "a single speaker's line recorded dry with no music"
        if subject_tag and speaker_id:
            subject_def_lines.append(
                f"{tag} is the voice-timbre reference for {subject_tag} ({speaker_id}), containing {desc}."
            )
            retention_lines.append(
                f"{tag}: reference - {subject_tag} ({speaker_id}) follows {tag}'s voice timbre and measured "
                f"delivery without copying the original signal; the words in {tag} are not spoken in the target video."
            )
        else:
            subject_def_lines.append(
                f"{tag} is a voice-timbre reference containing {desc}."
            )
            retention_lines.append(
                f"{tag}: reference - the target speaker follows {tag}'s voice timbre and measured delivery "
                f"without copying the original signal; the words in {tag} are not spoken in the target video."
            )
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
        for shot_binding in stage5_binding.get("shots", []) or []:
            bound_props = (shot_binding.get("reference_paths", {}) or {}).get("props", []) or []
            if isinstance(bound_props, dict):
                bound_props = [{"id": key, "reference_image": value} for key, value in bound_props.items()]
            for entry in bound_props:
                aid = entry.get("id") if isinstance(entry, dict) else None
                if aid and aid not in prop_ids:
                    prop_ids.append(aid)
        for aid in ref_path_map:
            if aid in registry.props and aid not in prop_ids:
                prop_ids.append(aid)
            if aid in registry.bodydetails and aid not in detail_ids:
                detail_ids.append(aid)
        for aid in prop_ids:
            info = registry.get_prop(aid)
            info["ref_img"] = ref_path_map.get(aid, info.get("ref_img") or "")
            supplementary.append(("prop", info))
        for aid in detail_ids:
            info = registry.get_bodydetail(aid)
            info["ref_img"] = ref_path_map.get(aid, info["ref_img"])
            supplementary.append(("bodydetail", info))
        for kind, info in supplementary:
            if kind == "prop" and not info.get("ref_img"):
                # 無設定圖的道具：不占 Picture 編號，描述寫進參考定義區（純文字）
                subject_def_lines.append(
                    f"A prop without a reference image appears in this segment, described in words only: {info['desc_en']}."
                )
                notes.append(f"道具 {info['id']} 沒有設定圖，以英文描述純文字注入；補圖後重編可改走 Picture 參考。")
                continue
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

    # 音色參考的音訊素材排在所有圖像素材之後：官方 ref-en §2.5 明載 <Video N> 與
    # <Audio N> 各自獨立編號，音訊不參與 <Picture N> 的序對。
    for ref, tag, speaker_id in audio_ref_entries:
        reference_images.append({
            "id": ref["id"], "type": "audio", "description": ref["description"], "path": ref["path"],
            "role": ref["role"], "character_id": ref.get("character_id"),
            "speaker_id": speaker_id, "audio_tag": tag,
        })

    # ---------- 風格與光線 ----------
    if stage5_binding:
        anchor = registry.style.get("style_anchor", "") or "cinematic film look"
    else:
        anchor = _clean(style_lock.get("anchor")) or registry.style.get("style_anchor", "") or "cinematic film look"
    if style_rules.is_style14(metadata.get("style_key") or registry.style.get("style_index")
                              or style_rules.project_style(registry.project_root)):
        # 14 號風格：固定影片錨，刪掉「hand-painted 2D／cel-like／non-photorealistic」這類平塗模板句
        anchor = style_rules.video_anchor(anchor)
    lighting_line = (_clean(metadata.get("lighting_lock_line")) or _clean(style_lock.get("lighting_lock_line"))
                     or registry.style.get("lighting_lock_line", "") or "natural ambient light")
    if _has_cjk(lighting_line):
        notes.append("光線鎖是中文，未寫進英文提示詞；請在 en_overlay.lighting_lock_line_en 或 metadata_override.lighting_lock_line 補英文")
        lighting_line = registry.style.get("lighting_lock_line", "") if not _has_cjk(registry.style.get("lighting_lock_line", "")) else ""
        lighting_line = lighting_line or "natural ambient light"
    lighting_line_clean, _ = strip_hex(palette_names(lighting_line))
    if not any(re.search(rf"\b{lt}\b", lighting_line_clean, re.IGNORECASE) for lt in LIGHT_SOURCE_TERMS):
        lighting_line_clean += " with soft ambient light"

    continuity = dict(style_lock.get("continuity_anchors", {}) or {})
    continuity.update(style_lock.get("continuity_anchors_en", {}) or {})
    authored_anchors = []
    for key in ("lighting", "axis", "blocking", "texture"):
        value = continuity.get(key)
        if not value:
            continue
        if _has_cjk(value):
            notes.append(f"連戲錨 {key} 是中文，未寫進英文提示詞；請在 en_overlay.continuity_anchors_en 補英文")
            continue
        if key == "blocking" and continuity_lint.FUTURE_BLOCKING_RE.search(str(value)):
            notes.append(f"連戲錨 blocking 含之後才發生的走位（{continuity_lint.FUTURE_BLOCKING_RE.search(str(value)).group(0)}）；"
                         f"錨點只寫段落開頭狀態，否則空鏡會畫出人物分身（#95）")
        authored_anchors.append(f"{key}: {value}")
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
    task_type = "reference generation + audio reference" if audio_refs else "reference generation"
    summary_block = (
        f"summary:\n[{task_type}] A {target_dur:.1f}s {aspect} segment ({eff_d:.3f}s effective from {target_dur:.3f}s target) "
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
    # #138 燒字來源可預測（校徽、車門、斑駁牆）：正向補一句素淨表面，放在逐鏡之前的總述行。
    lettering_texts = list(subject_def_lines) + [lighting_line_clean, anchor or ""]
    for _s in shots:
        _act = _s.get("action_and_performance", {}) or {}
        _blk = _s.get("spatial_blocking", {}) or {}
        lettering_texts += [str(x) for x in (_act.get("action_stages_en") or [])]
        lettering_texts += [str(_blk.get("blocking_desc_en") or ""), " ".join(str(x) for x in (_blk.get("anchor_objects_en") or []))]
        _five = _five_part_en(_s) or {}
        lettering_texts += [str(v) for v in _five.values()]
    added_no_lettering = bool(no_lettering and not metadata.get("allow_lettering")
                              and continuity_lint.needs_no_lettering(*lettering_texts))
    if added_no_lettering:
        det_header += continuity_lint.NO_LETTERING_SENTENCE
    carry_text = continuity_lint.carry_sentence(continuity_lint.english_end_state(previous_end_state)) if previous_end_state else ""
    if previous_end_state and not carry_text:
        notes.append("同場景前一段的 segment_end_state 沒有英文終態，未帶入本段第 1 鏡；請在前段 en_overlay.end_state_en 補英文")
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
    spoken_lines: List[str] = []
    external_narration: List[Dict[str, Any]] = []
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

        if cam.get("move_preset"):
            # PR-14b：運鏡預設展開成完整 Camera 子句（不加 slowly、不走動詞映射）
            # 第 3 輪：秒數不足（yo-yo、三格分割需 8 秒）、開場景別不符、掛了場景參考圖（運鏡砍半）都記 compile_notes
            try:
                _shot_secs = float(s.get("duration") or target_dur)
            except (TypeError, ValueError):
                _shot_secs = target_dur
            mclause, _preset_warn = camera_moves.expand_preset(
                cam["move_preset"], cam.get("move_slots"),
                seconds=_shot_secs, shot_size=shot_size, bg_plate=ref2va)
            notes.extend(f"{s.get('shot_id')} {w}" for w in _preset_warn)
        else:
            motion = map_camera_motion(cam.get("movement_en") or cam.get("movement", "static"), idx).replace("camera ", "").strip()
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
        lips_closed = _lips_closed_wanted(s, registry, no_visual_ids)
        if dlg.get("has_dialogue") and dlg.get("line_verbatim"):
            line = dlg["line_verbatim"].strip()
            spk = dlg.get("speaker")
            identity = _dialogue_speaker_label(spk, registry)
            speaker_tag = tag_of.get(spk)
            speaker_id = speaker_ids.get(str(spk)) if spk else None
            if speaker_tag and speaker_id:
                # 官方 ref-en §5.4：參考主體發聲時要同時保留視覺標籤與說話人代號
                subject_speaker = f"{speaker_tag} ({speaker_id})"
            elif speaker_id:
                # 官方：說話人不對應到任何 Subject 時，用穩定音色描述 + (Sx)
                subject_speaker = f"{identity} ({speaker_id})"
            else:
                subject_speaker = identity
            window = _speech_window_clause(dlg)
            speaker_record = registry.characters.get(spk, {}) if spk else {}
            visibility = "offscreen" if (speaker_record.get("no_visual_reference") or speaker_record.get("voice_only")) else _dialogue_visibility(s)
            is_vo = _is_voiceover(s)
            _form = str(dlg.get("offscreen_form") or "").lower()
            if _form == "voiceover":
                is_vo, visibility = True, "offscreen"
            elif _form == "offscreen":
                visibility = "offscreen"
            spoken_lines.append(line)
            # 外部化判準：這句話沒有「可見的嘴」就不該由 H3 內建語音發出。
            # 畫外音、旁白、背影／遮嘴說話全部改由外部 TTS 合成後於階段 7 混入；
            # 有可見嘴的畫內對白才留 <d> 給 H3 當口型錨點。
            no_visible_mouth = is_vo or visibility in ("offscreen", "mouth_hidden")
            route = _offscreen_route(narration_policy, dlg, line) if no_visible_mouth else "h3"
            if no_visible_mouth and route == "external":
                external_narration.append({
                    "shot_id": s.get("shot_id"),
                    "global_shot_id": s.get("global_shot_id"),
                    "speaker": spk,
                    "speaker_id": speaker_id,
                    "line": line,
                    "language": "Chinese",
                    "is_voiceover": is_vo,
                    "start": ((dlg.get("speech_window") or {}) or {}).get("start"),
                    "end": ((dlg.get("speech_window") or {}) or {}).get("end"),
                })
                # #122：外部化的句子不得在提示詞裡寫「某人在說話」卻不給 <d>（H3 會自編亂語）。
                # 這一鏡只寫畫面角色閉嘴與環境音；台詞由階段 7 混入。
                if lips_closed:
                    delivery = ("the visible characters keep their lips completely closed and continue their actions, "
                                "and the shot carries only the location ambience")
                else:
                    delivery = "the shot carries only the location ambience"
                if window:
                    delivery = delivery[:1].upper() + delivery[1:]
                speech = f"; {window}{delivery}"
            elif no_visible_mouth and (is_vo or visibility == "offscreen"):
                # 官方畫外句式（實測：噩盡島 EP01 S02-b／S02-d／S03-e 拼音相似度 1.00）：
                # 聲線描述放 <d> 外、<d> 內只放逐字台詞；只對露臉者寫嘴閉合。
                form_vo = is_vo
                voice = _clean(dlg.get("offscreen_voice_en")) or _english_voice_descriptor(dlg, notes)
                if voice and CJK_RE.search(voice):
                    voice = ""
                voice = voice.rstrip(".。 ")
                if voice.lower() in ("voiceover", "v.o.", "v.o", "offscreen", "off-screen", "inner voice"):
                    voice = ""
                if not voice:
                    notes.append(f"{s.get('shot_id')} 畫外句缺英文聲線描述（offscreen_voice_en 或 voice_4d_spec_en）；"
                                 f"H3 會自己猜聲音，跨段更難一致")
                where = _clean(dlg.get("offscreen_where_en"))
                if where and CJK_RE.search(where):
                    where = ""
                show_now = ((stage5_en_overlay(stage5_binding).get("shots") or {}).get(s.get("global_shot_id")) or {}).get("show") if stage5_binding else None
                if show_now:
                    faces = [tag_of[c] for c in selected
                             if c in tag_of and str(show_now.get(c) or "") in ("face", "profile")
                             and (form_vo or c != spk)]
                elif lips_closed:
                    faces = [tag_of[c] for c in (s.get("character_ids") or [])
                             if c in tag_of and not is_narrator(c) and c not in no_visual_ids and (form_vo or c != spk)]
                    faces = list(dict.fromkeys(faces)) or ["the visible characters"]
                else:
                    faces = []
                if faces == ["the visible characters"]:
                    lips = " while the visible characters' lips remain completely closed"
                elif faces:
                    lips = f" while {_possessive_list(faces)} lips remain completely closed"
                elif form_vo:
                    lips = " while no face is on screen, so all lips remain completely closed"
                else:
                    lips = ""
                voice_txt = f", {voice}" if voice else ""
                if form_vo:
                    delivery = f"{subject_speaker} says in an off-screen voiceover{voice_txt}: "
                else:
                    where_txt = f" {where}" if where else ""
                    delivery = f"the line is heard from {subject_speaker} off-screen{where_txt}{voice_txt}: "
                    if window:
                        delivery = delivery[:1].upper() + delivery[1:]
                speech = f"; {window}{delivery}<d>[Chinese] {line}</d>{lips}"
                n_chars = _spoken_char_count(line)
                if n_chars > SHORT_OFFSCREEN_MAX_CHARS:
                    notes.append(f"{s.get('shot_id')} 畫外句 {n_chars} 字，超過實測範圍（約 ≤{SHORT_OFFSCREEN_MAX_CHARS} 字）；"
                                 f"H3 可能念不全或亂語，考慮拆鏡或 voice_route=external")
                try:
                    shot_len = float(s.get("end_time")) - float(s.get("start_time"))
                except (TypeError, ValueError):
                    shot_len = None
                if shot_len is not None and shot_len < n_chars / 4.0 + 0.6:
                    notes.append(f"{s.get('shot_id')} 畫外句 {n_chars} 字只有 {shot_len:.1f}s，鏡長可能不夠念完（約每秒 4 字＋起音）")
                if faces and MOUTH_OPEN_RE.search(expr or ""):
                    notes.append(f"{s.get('shot_id')} 畫外句同鏡的 Expression 寫了張嘴／喘氣（{MOUTH_OPEN_RE.search(expr).group(0)}），"
                                 f"H3 會讓露臉者跟著開口；改成 lips pressed tightly shut（#123）")
            elif visibility == "mouth_hidden":
                delivery = f"{subject_speaker} speaks with lips remaining completely closed: "
                speech = f"; {window}{delivery}<d>[Chinese] {line}</d>"
            else:
                who = tag_of.get(spk) or (secondary_short.get(spk) if spk else None) or focal
                # 音色：穩定的描述詞（voice_4d_spec_en）＋ 官方音色參考 <Audio N>。
                # 兩者一起才跨段穩：描述詞固定「聽起來像誰」，<Audio N> 固定「音色是哪一條」。
                voice_bits: List[str] = []
                descriptor = _english_voice_descriptor(dlg, notes)
                if descriptor:
                    voice_bits.append(descriptor)
                audio_tag = audio_tag_of.get(str(spk)) if spk else None
                if audio_tag:
                    voice_bits.append(f"matching the voice timbre referenced from {audio_tag}")
                voice_clause = (", " + ", ".join(voice_bits)) if voice_bits else ""
                if speaker_tag and who == speaker_tag:
                    delivery = f"{subject_speaker} is the visible speaking character{voice_clause}, and says: "
                else:
                    delivery = f"{subject_speaker} is the visible speaking character ({who}){voice_clause}, and says: "
                speech = f"; {window}{delivery}<d>[Chinese] {line}</d>"
        else:
            speech = "; lips stay closed" if lips_closed else ""

        blocking = s.get("spatial_blocking", {}) or {}
        blocking_desc = blocking.get("blocking_desc_en") or blocking.get("blocking_desc", "")
        if blocking_desc and _has_cjk(blocking_desc):
            notes.append(f"{s.get('shot_id')} 走位 blocking_desc 是中文，未寫進英文提示詞；請補 blocking_desc_en 或 en_overlay blocking_en")
            blocking_desc = ""
        blocking_bits = [blocking_desc]
        anchor_objects = _english_anchor_objects(
            blocking.get("anchor_objects_en") if blocking.get("anchor_objects_en") is not None else blocking.get("anchor_objects"),
            registry, notes, s.get("shot_id"))
        if anchor_objects:
            blocking_bits.append("anchor objects: " + ", ".join(anchor_objects))
        blocking_clause = f" Blocking: {'; '.join(bit for bit in blocking_bits if bit)}." if any(blocking_bits) else ""
        stage_refs = ""
        global_shot_id = s.get("global_shot_id")
        for picture_no, variant_name in variant_picture_by_shot.get(global_shot_id, []):
            stage_refs += f" Stage-specific reference: use <Picture {picture_no}> for the creature's {variant_name} morphology in this shot only."
        # 整板查表角色：把「用哪一格」寫進鏡頭描述，讓模型知道該取板上的哪個人。
        bound_shot_refs = next((b for b in (stage5_binding or {}).get("shots", []) or []
                                if b.get("global_shot_id") == global_shot_id), {})
        for cid in bound_shot_refs.get("visual_subject_ids") or []:
            meta = asset_meta.get(cid, {})
            if meta.get("reference_view") != "panel":
                continue
            pic_no = subject_picture_no.get(cid)
            if not pic_no:
                continue
            if meta.get("panel_role") == "creature":
                # 異獸整板：Subject 定義已指定用哪一格；逐鏡再寫「背影」既錯又重複（W33），這裡不再加句。
                continue
            stage_refs += (
                f" The figure seen from behind matches {meta.get('panel_label_en')} in <Picture {pic_no}>; "
                f"no other figure on that sheet appears in this shot."
            )

        if idx == 1 and ref2va:
            head = f"[Shot 1] The scene opens with <Picture 1> as a scene/style reference for spatial guidance: {shot_size}{optics} of {focal}, as {mclause}."
        elif idx == 1:
            head = f"[Shot 1] The shot begins from <Picture 1>: {shot_size}{optics} of {focal}, as {mclause}."
        else:
            head = (f"[Shot {idx}] At {format_timestamp(cut_timestamps[idx - 2])}, the shot cuts to a "
                    f"{shot_size}{optics} of {focal}, as {mclause}.")
        # #67：逐鏡 On screen 句（en_overlay.shots.<gsid>.show）
        _show = ((stage5_en_overlay(stage5_binding).get("shots") or {}).get(global_shot_id) or {}).get("show") if stage5_binding else None
        if _show:
            head += _on_screen_sentence(_show, [(k, c, subject_picture_no[c]) for k, c in enumerate(selected, start=1)])
        if idx == 1 and carry_text:
            head += carry_text
        tail = " The final second holds still before the cut." if (idx == n_shots and tail_hold) else ""
        if idx == n_shots and layer2_data.get("segment_end_state"):
            end_state = layer2_data["segment_end_state"]
            final_state = end_state.get("planned_final_state_en") or end_state.get("planned_final_state") or {}
            if final_state and _has_cjk(final_state):
                notes.append("segment_end_state 是中文，未寫進英文提示詞；請在 en_overlay.end_state_en 補英文")
                final_state = {}
            if final_state:
                tail += " End state: " + json.dumps(final_state, ensure_ascii=False, sort_keys=True) + "."
        action = action[:1].upper() + action[1:]
        marker = ""
        if embed_cut_markers:
            # 本專案的約定（非官方語法）：<scenetrans> 標在新場景的第一鏡結尾、
            # <cutoff> 標在段落最後一鏡結尾，供剪輯與 QA 讀；只在 --embed-cut-markers 時寫入。
            previous_scene = shots[idx - 2].get("scene_id") if idx > 1 else None
            current_scene = s.get("scene_id")
            if idx > 1 and current_scene and previous_scene and current_scene != previous_scene:
                marker += " <scenetrans>"
            if idx == n_shots:
                marker += " <cutoff>"
        five = _five_part_en(s)
        if five and (compact_description or (layer2_data.get("metadata") or {}).get("compact_description")):
            five = compact_five_part(five)
        if five:
            # 五小節裡的 {C-id} 換成該角色的 <Subject N>（同框多人時把「那位年長女子」綁到參考圖）
            def _subject_token(m, _tags=tag_of):
                cid = m.group(1)
                return _tags.get(cid) or secondary_short.get(cid) or char_info(cid)["short_en"]
            five = {k: re.sub(r"\{((?:C|CREATURE|EXTRAS)-[A-Za-z0-9_-]+)\}", _subject_token, v or "") for k, v in five.items()}
            # 逐鏡五小節（references/prompt-authoring.md）：由 agent 依分鏡親手寫在 Layer 2，
            # 取代自動拼出的 action／Expression／Blocking；台詞說明仍由編譯器接在最後。
            speech_txt = speech.lstrip("; ").strip()
            if speech_txt.lower().startswith("lips stay closed"):
                speech_txt = "Lips stay closed."
            five_txt = " ".join(f"{label}: {five[key].rstrip()}" + ("" if five[key].rstrip().endswith((".", "!", "?")) else ".")
                                for key, label in FIVE_PART_KEYS if five[key])
            body = f"{head} {five_txt}{stage_refs} {speech_txt}".rstrip()
            if not body.endswith((".", "!", "?", ">")):
                body += "."
            body += f"{tail}{marker}"
        else:
            closing = f"{speech}." if speech else ("." if (expr and not blocking_clause and not stage_refs and not expr.rstrip().endswith((".", "!", "?"))) else "")
            body = f"{head} {action}." + (f" Expression: {expr}" if expr else "") + blocking_clause + stage_refs + f"{closing}{tail}{marker}"
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
    # 官方 §4.6 / ref-en §6：對白只寫在 detailed_description 的 <d> 區塊，
    # 不得在 overall_soundscape 重複，否則 H3 會在環境音軌再念一次。
    foley = _strip_dialogue_from_soundscape(foley, spoken_lines)
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
    pending_missing = [p for p in missing if p in pending_refs]
    missing = [p for p in missing if p not in pending_refs]
    if stage5_binding and missing:
        raise ValueError(f"Stage5 has missing bound reference image(s): {', '.join(missing)}")
    if pending_missing:
        notes.append(
            f"⏳ 待補參考圖（已宣告 pending_references，提示詞可審稿、不可送件）：{', '.join(pending_missing)}；"
            f"圖補齊後重編一次即可解除。"
        )
    if external_narration:
        notes.append(
            f"畫外音／旁白 {len(external_narration)} 句已改為外部 TTS（未寫入 <d>），"
            f"階段 7 需以 {narration_policy} 政策合成後混入"
        )
    if not h3_spec.in_supported_range(seg_frames):
        notes.append(
            f"⚠️ {seg_frames} 幀超出 H3 支援區間 "
            f"{h3_spec.MIN_SUPPORTED_FRAMES}–{h3_spec.MAX_SUPPORTED_FRAMES}；送件前請拆段"
        )
    cut_markers = [
        {
            "shot_id": shot.get("shot_id"),
            "at_seconds": round(float(shot.get("start_time", 0.0)), 3),
            "type": "cut",
        }
        for shot in shots
        if float(shot.get("start_time", 0.0)) > 0
    ]
    return {
        "segment_id": seg_id,
        "scene_id": scene_id,
        "metadata": {
            **metadata,
            # 編譯指紋：送件與階段 5 審查會比對，編譯後再被腳本或手動覆寫就擋下（E38）。
            "compiled_prompt_sha256": prompt_authoring.prompt_fingerprint(full_h3_prompt),
            # #150：編譯規則版本；規則改版時 deps 不因提示詞變新就把舊影片標過期
            "compiler_rules": COMPILER_RULES_VERSION,
            "aspect_ratio": aspect,
            "target_duration_sec": target_dur,
            "effective_duration_sec": round(eff_d, 3),
            "effective_duration_sec_exact": eff_d,
            "frames": seg_frames,
            "frame_spec": f"{h3_spec.FRAME_QUANTUM_STEP}n+{h3_spec.FRAME_QUANTUM_OFFSET}@{h3_spec.FPS}fps",
            "cut_markers": cut_markers,
            "cut_marker_spec": "shots[].start_time；結構化資料，不寫進提示詞",
            "cut_marker_tokens": {
                "embedded": embed_cut_markers,
                "spec": "<scenetrans> 標新場景首鏡、<cutoff> 標段落末鏡（本專案約定，非官方語法）",
            },
            "rounding_mode": selected_rounding_mode,
            "rounding_reason": "dialogue-preserving" if contains_dialogue else metadata.get("rounding_reason", "configured"),
            "shots_count": n_shots,
            "style_lock": effective_style_lock,
            "qa_exclusions": negative,
            "palette_preset": metadata.get("palette_preset", ""),
            "narration_policy": narration_policy,
            "lighting_lock_line": lighting_line_clean,
            **({"carried_end_state": True} if carry_text else {}),
            **({"no_lettering_added": True} if added_no_lettering else {}),
            **({"pending_references": pending_missing} if pending_missing else {}),
        },
        "reference_images": reference_images,
        "h3_prompt": full_h3_prompt,
        "h3_loras": loras,
        "shots": shots,
        "external_narration": external_narration,
        "speaker_ids": speaker_ids,
        "unanchored_in_frame_characters": unanchored_in_frame,
        "segment_end_state": layer2_data.get("segment_end_state"),
        "carry_previous_end_state": (layer2_data.get("metadata") or {}).get("carry_previous_end_state", True) is not False,
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
        print("⚠️ [警告] 已顯式指定 --skip-stage-gate，跳過階段 4 分鏡總覽圖門禁檢查。")
        if not record_gate_bypass(project_root, "stage-4", "compile_layer2_to_h3 --skip-stage-gate"):
            print("⚠️ [警告] 沒有 review/project-state.json，這次繞過未留紀錄。", file=sys.stderr)
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
        print("❌ [Fatal Gate Error - 階段 4 分鏡總覽圖門禁阻斷]", file=sys.stderr)
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


def collect_segment_end_states(
    layer2_files: List[pathlib.Path],
    bindings: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Tuple[Dict[str, str], Dict[str, Any]]:
    """#133：收集輸入段與同目錄其他 layer2 段的 scene_id 與 segment_end_state。

    只編部分段時，前一段可能不在這次輸入；從同目錄的 layer2-*.json 找回來。
    bindings 的 en_overlay.end_state_en 優先（階段 5 的英文終態）。
    """
    scenes: Dict[str, str] = {}
    end_states: Dict[str, Any] = {}
    pool: List[pathlib.Path] = []
    for path in layer2_files:
        if path not in pool:
            pool.append(path)
        for sib in sorted(path.parent.glob("layer2-*.json")):
            if sib not in pool:
                pool.append(sib)
    for path in pool:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        sid = str(data.get("segment_id") or data.get("scene_id") or "")
        if not sid:
            continue
        if data.get("scene_id"):
            scenes[sid] = str(data["scene_id"])
        state = data.get("segment_end_state") if isinstance(data.get("segment_end_state"), dict) else {}
        overlay = stage5_en_overlay((bindings or {}).get(sid))
        if isinstance(overlay.get("end_state_en"), dict) and overlay["end_state_en"]:
            state = dict(state)
            state["planned_final_state_en"] = dict(overlay["end_state_en"])
        end_states[sid] = state
    return scenes, end_states


def resolve_narration_policy(cli_value: Optional[str], project_root: pathlib.Path) -> str:
    """CLI 旗標與 decisions.json 的 dialogue_policy 定案必須一致；都沒有才用預設。"""
    scripts_dir = str(CURRENT_DIR.parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    import decisions as decisions_mod
    try:
        decided = decisions_mod.narration_policy_of(decisions_mod.load(project_root))
    except decisions_mod.DecisionError as exc:
        raise ValueError(f"decisions.json 讀取失敗：{exc}") from exc
    if cli_value and decided and cli_value != decided:
        raise ValueError(f"--narration-policy {cli_value} 與 decisions.json 的 dialogue_policy 定案 {decided} 衝突，請統一後再編譯")
    return cli_value or decided or DEFAULT_NARRATION_POLICY


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
    parser.add_argument("--allow-normalize-warnings", action="store_true",
                        help="允許 Layer 2 正規化警告通過（時間軸不一致／台詞窗越界）；預設是硬錯誤")
    parser.add_argument("--record-deps", action="store_true",
                        help="編譯成功後更新 <project-root>/.h3d-deps.json（segment 級 stale 帳本）")
    parser.add_argument("--embed-cut-markers", action="store_true",
                        help="在提示詞寫入 <scenetrans>／<cutoff> 標記（本專案約定，非官方語法）")
    parser.add_argument(
        "--narration-policy", type=str, default=None, choices=list(NARRATION_POLICIES),
        help=("畫外音／旁白政策：short-offscreen-h3=短畫外句與旁白（≤15 字）由 H3 用官方句式＋<d> 直接生成，長句才外部 TTS；"
              "external=全部外部 TTS，於階段 7 混入；h3-native=全部留 H3。"
              "省略時讀 <project-root>/decisions.json 的 dialogue_policy，都沒有才用 short-offscreen-h3（預設）；與定案衝突會報錯"),
    )
    parser.add_argument("--no-carry-end-state", action="store_false", dest="carry_end_state", default=True,
                        help="不把同場景前一段的英文終態帶入本段第 1 鏡（#133；預設帶入）")
    parser.add_argument("--no-lettering-guard", action="store_false", dest="lettering_guard", default=True,
                        help="不自動補「表面素淨、無文字無塗鴉」句（#138；預設遇到校徽／車門／斑駁牆等字詞時補）")
    parser.add_argument("--compact-description", action="store_true",
                        help="選用、預設關閉：只有使用者看過 W11 報告並同意壓縮時才開。壓縮內容：刪 Camera 開頭重複的鏡頭參數、逐鏡 Sound 改只寫在 overall_soundscape（也可在 Layer 2 metadata.compact_description=true）")
    parser.add_argument("--project-root", type=pathlib.Path, default=pathlib.Path("."), help="專案根目錄（預設當前目錄）")
    parser.add_argument("--skip-stage-gate", action="store_true", help="強制跳過階段 4 分鏡總覽圖門禁檢查（僅限測試或除錯）")

    args = parser.parse_args()
    try:
        args.narration_policy = resolve_narration_policy(args.narration_policy, args.project_root)
    except ValueError as exc:
        print(f"[錯誤] {exc}", file=sys.stderr)
        return 1

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
            all_bindings = dict(bindings_by_segment)
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
                # 全集 bindings 可以只編其中幾段（#56）：其他段的綁定與這次輸入無關，略過即可。
                print(f"[提示] bindings 另含 {len(extras)} 段不在這次輸入內，已略過（只編譯輸入的 {len(input_ids)} 段）")
                for sid in extras:
                    bindings_by_segment.pop(sid, None)
        except Exception as exc:
            print(f"[錯誤] Stage5 bindings rejected: {exc}", file=sys.stderr)
            return 1
    else:
        parsed_inputs = {}
        all_bindings = {}

    carry = getattr(args, "carry_end_state", True)
    neighbor_scenes, neighbor_end_states = collect_segment_end_states(layer2_files, all_bindings)
    previous_of = continuity_lint.previous_segment_map(neighbor_scenes.items())

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
            this_sid = str(l2_data.get("segment_id") or l2_data.get("scene_id") or "")
            prev_sid = previous_of.get(this_sid)
            seg_res = compile_segment_h3(
                l2_data,
                registry=registry,
                max_char_refs=args.max_char_refs,
                auto_lora=args.auto_lora,
                stage5_binding=stage5_binding,
                narration_policy=args.narration_policy,
                allow_normalize_warnings=getattr(args, "allow_normalize_warnings", False),
                embed_cut_markers=getattr(args, "embed_cut_markers", False),
                previous_end_state=(neighbor_end_states.get(prev_sid) if (carry and prev_sid and (l2_data.get('metadata') or {}).get('carry_previous_end_state', True) is not False) else None),
                no_lettering=getattr(args, "lettering_guard", True),
                compact_description=getattr(args, "compact_description", False),
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
            refs_res = audit_refs_and_subjects(seg, project_root=args.project_root)
            # 模式 B: H3 提示詞 17 條自檢
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
                print(f"    [模式B通過] 17 條 H3 自檢全部通過 (真實秒數 D={lint_res['details']['effective_duration_sec']}s)")

            for w in refs_res["warnings"] + lint_res["warnings"]:
                print(f"    [警告] {w}")

            # 失敗目錄（P6）：把已知失敗模式套到這份提示詞；目錄壞掉算錯誤，不靜默。
            try:
                catalog = failure_catalog.load_catalog(args.project_root)
                catalog_res = failure_catalog.lint_text(seg["h3_prompt"], catalog)
            except failure_catalog.CatalogError as exc:
                print(f"    [失敗目錄錯誤] 無法載入或執行：{exc}")
                total_errors += 1
                catalog_res = {"errors": [], "warnings": []}
            for item in catalog_res["warnings"]:
                print(f"    [失敗目錄] {failure_catalog.format_hit(item)}")
                total_warnings += 1
            for item in catalog_res["errors"]:
                print(f"    [失敗目錄錯誤] {failure_catalog.format_hit(item)}")
                total_errors += 1
            total_warnings += len(refs_res["warnings"]) + len(lint_res["warnings"])
            for note in seg.get("compile_notes", []):
                print(f"    [編譯提醒] {note}")
                total_warnings += 1

        # 段間連戲（#133 #139）：前段終態、相鄰段姿勢矛盾、同場光線鎖一致；只警告不擋
        cont_res = continuity_lint.lint_adjacent(compiled_results, neighbor_end_states, neighbor_scenes)
        if cont_res["warnings"]:
            print("\n🔗 段間連戲檢查")
        for w in cont_res["warnings"]:
            print(f"    [連戲警告] {w}")
        total_warnings += len(cont_res["warnings"])
        shot_res = continuity_lint.lint_shots(compiled_results)
        if shot_res["warnings"]:
            print("\n🎬 逐鏡畫面約束（動作／終態／對白鏡）")
        for w in shot_res["warnings"]:
            print(f"    [畫面警告] {w}")
        total_warnings += len(shot_res["warnings"])

        # 逐鏡撰寫審查（防偷懶，references/prompt-authoring.md）：E30–E38 擋、W 提醒
        author_res = prompt_authoring.audit_segments(compiled_results)
        if author_res["errors"] or author_res["warnings"]:
            print("\n✍️ 逐鏡撰寫審查（references/prompt-authoring.md）")
        for e in author_res["errors"]:
            print(f"    [撰寫錯誤] {e}")
        for w in author_res["warnings"]:
            print(f"    [撰寫警告] {w}")
        total_errors += len(author_res["errors"])
        total_warnings += len(author_res["warnings"])

        print("\n" + "=" * 75)
        print(f"📊 雙重審查總結: 錯誤數: {total_errors} | 警告數: {total_warnings}")
        print("=" * 75)
        if total_errors > 0:
            return 1

    # 更新 segment 級依賴帳本（選用）：只有在上面所有檢查都通過後才寫，
    # 否則壞掉的編譯會變成新的「乾淨基準」。merge 語義見 deps.py。
    if getattr(args, "record_deps", False):
        try:
            import deps as deps_mod
        except ImportError:  # pragma: no cover - 套件匯入路徑
            from . import deps as deps_mod
        try:
            ledger = deps_mod.record(args.project_root)
            print(f"🧾 已合併更新依賴帳本: {ledger}")
        except ValueError as exc:
            print(f"⚠️ 依賴帳本未更新：{exc}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
