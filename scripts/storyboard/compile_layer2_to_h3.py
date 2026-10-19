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
        self.style: Dict[str, str] = {}
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
        if not found.get("ref_img"):
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
    raw_lower = (raw_movement or "").lower().strip()

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
    spec = str(dlg.get("voice_4d_spec") or "") + str(dlg.get("audio_type") or "")
    return is_narrator(dlg.get("speaker")) or "voiceover" in spec.lower() or "v.o" in spec.lower()


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
) -> Dict[str, Any]:
    """將單個 Layer 2 JSON 分鏡檔編譯為符合 H3 官方六段式規範的資料結構。

    主角參考圖：asset_refs.primary_character / metadata.primary_character 優先；
    否則取臉戲權重（景別越近權重越高）最重的角色。旁白與畫外音永不成為主體。
    """
    seg_id = layer2_data.get("segment_id") or layer2_data.get("scene_id", "SEG01")
    scene_id = layer2_data.get("scene_id", "SC01")
    metadata = layer2_data.get("metadata", {}) or {}
    style_lock = layer2_data.get("style_lock", {}) or {}
    target_dur = float(metadata.get("target_duration_sec", 7.0))
    aspect = metadata.get("aspect_ratio", "16:9")
    shots = layer2_data.get("shots", []) or []
    if not shots:
        raise ValueError(f"分鏡 {seg_id} 未包含任何 shots！")
    eff_d = effective_duration(target_dur, rounding=rounding_mode)
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
    for c in asset_refs.get("characters", []) or []:
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
        if speaker and not is_narrator(speaker):
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
    selected = ranked[:max(1, max_char_refs)]
    secondary = ranked[max(1, max_char_refs):]

    def char_info(cid: str) -> Dict[str, Any]:
        return registry.get_character(cid, wardrobe_state=costume_of.get(cid) or seg_wardrobe)

    # ---------- 場景 ----------
    location_id = asset_refs.get("scene_id", scene_id)
    loc_info = registry.get_location(location_id)
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
    for k, cid in enumerate(selected, start=1):
        info = char_info(cid)
        tag_of[cid] = f"<Subject {k}>"
        reference_images.append({
            "id": info["id"], "type": "character", "description": info["desc_en"], "path": info["ref_img"],
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

    # ---------- 風格與光線 ----------
    anchor = _clean(style_lock.get("anchor")) or registry.style.get("style_anchor", "") or "cinematic film look"
    lighting_line = (_clean(metadata.get("lighting_lock_line")) or _clean(style_lock.get("lighting_lock_line"))
                     or registry.style.get("lighting_lock_line", "") or "natural ambient light")
    lighting_line_clean, _ = strip_hex(palette_names(lighting_line))
    if not any(re.search(rf"\b{lt}\b", lighting_line_clean, re.IGNORECASE) for lt in LIGHT_SOURCE_TERMS):
        lighting_line_clean += " with soft ambient light"

    continuity = style_lock.get("continuity_anchors", {}) or {}
    authored_anchors = [f"{key}: {continuity[key]}" for key in ("lighting", "axis", "blocking", "texture") if continuity.get(key)]
    if style_lock.get("anchor"):
        authored_anchors.insert(0, f"style anchor: {style_lock['anchor']}")
    negative = _clean(style_lock.get("negative")) or _clean(registry.style.get("style_negative"))
    if negative:
        authored_anchors.append(f"negative constraints: {negative}")
    authored_anchors.append(f"lighting lock: {lighting_line_clean}")
    retention_lines.append("Continuity anchors: " + "; ".join(authored_anchors))

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
        stages = [TODO_RE.sub("", x).strip() for x in (act.get("action_stages_en") or act.get("action_stages") or []) if isinstance(x, str)]
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
            if _is_voiceover(s):
                speech = f"; an off-screen narrator says <d>[Chinese] {line}</d> while lips on screen stay closed"
            else:
                spk = dlg.get("speaker")
                who = tag_of.get(spk) or (secondary_short.get(spk) if spk else None) or focal
                speech = f"; then {who} speaks <d>[Chinese] {line}</d>"
        else:
            speech = "; lips stay closed"

        blocking = s.get("spatial_blocking", {}) or {}
        blocking_bits = [blocking.get("blocking_desc", "")]
        if blocking.get("anchor_objects"):
            blocking_bits.append("anchor objects: " + ", ".join(blocking["anchor_objects"]))
        blocking_clause = f" Blocking: {'; '.join(bit for bit in blocking_bits if bit)}." if any(blocking_bits) else ""

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
        body = f"{head} {action}." + (f" Expression: {expr}" if expr else "") + blocking_clause + f"{speech}.{tail}"
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
    return {
        "segment_id": seg_id,
        "scene_id": scene_id,
        "metadata": {
            **metadata,
            "aspect_ratio": aspect,
            "target_duration_sec": target_dur,
            "effective_duration_sec": round(eff_d, 3),
            "shots_count": n_shots,
            "style_lock": style_lock,
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

    print("=" * 75)
    print(f"🎬 正在執行 Layer 2 ➔ H3 官方六段式批次編譯器")
    print(f"輸入檔案數: {len(layer2_files)} 個分鏡段落")
    print("=" * 75)

    compiled_results: List[Dict[str, Any]] = []
    for p in layer2_files:
        try:
            with p.open("r", encoding="utf-8") as f:
                l2_data = json.load(f)
            seg_res = compile_segment_h3(
                l2_data,
                registry=registry,
                max_char_refs=args.max_char_refs,
                auto_lora=args.auto_lora,
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
            lint_res = lint_h3_prompt(seg["h3_prompt"], nominal_duration=dur)

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
