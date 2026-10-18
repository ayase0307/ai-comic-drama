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
4. 整合 director_storyboard_assistant.auto_adapt_h3_loras 自動適配 FreeVideo LoRA JSON payload。
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

OFFICIAL_MOTION_FALLBACKS = [
    "static",
    "trucks left",
    "trucks right",
    "dollies in",
    "dollies out",
    "pans left",
    "pans right",
    "tilts up",
    "tilts down",
    "trucks left while panning right",
    "trucks right while panning left",
]

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

class AssetRegistry:
    """整合 bible.json 與 assets.md 的資產索引庫。"""

    def __init__(self, bible_path: Optional[pathlib.Path] = None, assets_path: Optional[pathlib.Path] = None):
        self.characters: Dict[str, Dict[str, Any]] = {}
        self.locations: Dict[str, Dict[str, Any]] = {}
        self.props: Dict[str, Dict[str, Any]] = {}

        if bible_path and bible_path.exists():
            self._load_bible(bible_path)
        if assets_path and assets_path.exists():
            self._load_assets_md(assets_path)

    def _load_bible(self, path: pathlib.Path) -> None:
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            # 解析角色
            for char in data.get("characters", []):
                cid = char.get("id") or char.get("character_id") or char.get("name", "")
                if cid:
                    self.characters[cid] = {
                        "id": cid,
                        "name": char.get("name", cid),
                        "desc_en": char.get("visual_prompt_en") or char.get("appearance_en") or char.get("description", ""),
                        "desc_zh": char.get("appearance_zh") or char.get("description", ""),
                        "ref_img": char.get("reference_image") or char.get("image_path") or f"assets/characters/{cid}.png",
                        "is_creature": char.get("is_creature", False) or "妖" in char.get("name", "") or "獸" in char.get("name", "")
                    }
            # 解析場景
            for loc in data.get("locations", []):
                lid = loc.get("id") or loc.get("location_id") or loc.get("name", "")
                if lid:
                    self.locations[lid] = {
                        "id": lid,
                        "name": loc.get("name", lid),
                        "desc_en": loc.get("visual_prompt_en") or loc.get("description_en") or loc.get("description", ""),
                        "desc_zh": loc.get("description_zh") or loc.get("description", ""),
                        "ref_img": loc.get("reference_image") or loc.get("image_path") or f"assets/scenes/{lid}.png",
                        "lighting": loc.get("lighting", "natural ambient light")
                    }
        except Exception as exc:
            print(f"[警告] 讀取 bible.json 失敗: {exc}", file=sys.stderr)

    def _load_assets_md(self, path: pathlib.Path) -> None:
        try:
            content = path.read_text(encoding="utf-8")
            # 尋找 Markdown 表格或卡片行（如 | C-shen-ye | 沈夜 | ... |）
            for line in content.splitlines():
                if "|" in line:
                    parts = [p.strip() for p in line.split("|") if p.strip()]
                    if len(parts) >= 3:
                        aid, name, desc = parts[0], parts[1], parts[2]
                        if aid.startswith("C-") or "char" in aid.lower():
                            self.characters[aid] = {
                                "id": aid,
                                "name": name,
                                "desc_en": desc,
                                "desc_zh": desc,
                                "ref_img": f"assets/characters/{aid}.png",
                                "is_creature": "妖" in name or "獸" in name or "蟒" in name
                            }
                        elif aid.startswith("S-") or "scene" in aid.lower() or "loc" in aid.lower():
                            self.locations[aid] = {
                                "id": aid,
                                "name": name,
                                "desc_en": desc,
                                "desc_zh": desc,
                                "ref_img": f"assets/scenes/{aid}.png",
                                "lighting": "natural daylight"
                            }
        except Exception as exc:
            print(f"[警告] 讀取 assets.md 失敗: {exc}", file=sys.stderr)

    def get_character(self, cid_or_name: str) -> Dict[str, Any]:
        """精確或模糊查找角色資產。"""
        if cid_or_name in self.characters:
            return self.characters[cid_or_name]
        for k, v in self.characters.items():
            if cid_or_name.lower() in k.lower() or cid_or_name in v.get("name", ""):
                return v
        # 預設自動推導
        clean_name = re.sub(r"^C-", "", cid_or_name).replace("-", " ").title()
        return {
            "id": cid_or_name,
            "name": clean_name,
            "desc_en": f"a young character named {clean_name} with focused demeanor and modern dark attire",
            "desc_zh": f"名為 {clean_name} 的角色，穿著深色便裝，神色專注",
            "ref_img": f"assets/characters/{cid_or_name}.png",
            "is_creature": False
        }

    def get_location(self, lid_or_name: str) -> Dict[str, Any]:
        """精確或模糊查找場景資產。"""
        if lid_or_name in self.locations:
            return self.locations[lid_or_name]
        for k, v in self.locations.items():
            if lid_or_name.lower() in k.lower() or lid_or_name in v.get("name", ""):
                return v
        clean_loc = re.sub(r"^S-", "", lid_or_name).replace("-", " ").title()
        return {
            "id": lid_or_name,
            "name": clean_loc,
            "desc_en": f"the establishing architectural setting of {clean_loc} under ambient lighting",
            "desc_zh": f"{clean_loc} 場景環境，具備自然環境光照",
            "ref_img": f"assets/scenes/{lid_or_name}.png",
            "lighting": "natural ambient light"
        }


# ==============================================================================
# H3 六段式 Prompt 編譯核心
# ==============================================================================

def format_timestamp(seconds: float) -> str:
    """將秒數格式化為 mm:ss.000 切點字串。"""
    mm = int(seconds // 60)
    ss = seconds % 60
    return f"{mm:02d}:{ss:06.3f}"


def map_camera_motion(raw_movement: str, shot_index: int) -> str:
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

    # 4. 輪流提供合規官方運鏡動詞（避免鏡頭重複運鏡）
    fallback = OFFICIAL_MOTION_FALLBACKS[shot_index % len(OFFICIAL_MOTION_FALLBACKS)]
    return fallback


def sanitize_english_text(text: str) -> str:
    """清理多餘空白與符號。"""
    return re.sub(r"\s+", " ", text).strip()


def compile_segment_h3(
    layer2_data: Dict[str, Any],
    registry: AssetRegistry,
    max_char_refs: int = 1,
    auto_lora: bool = True,
    rounding_mode: str = "floor",
) -> Dict[str, Any]:
    """將單個 Layer 2 JSON 分鏡檔編譯為符合 H3 官方六段式規範的資料結構。"""

    seg_id = layer2_data.get("segment_id") or layer2_data.get("scene_id", "SEG01")
    scene_id = layer2_data.get("scene_id", "SC01")
    metadata = layer2_data.get("metadata", {})
    target_dur = float(metadata.get("target_duration_sec", 7.0))
    aspect = metadata.get("aspect_ratio", "16:9")
    shots = layer2_data.get("shots", [])

    if not shots:
        raise ValueError(f"分鏡 {seg_id} 未包含任何 shots！")

    eff_d = effective_duration(target_dur, rounding=rounding_mode)

    # 1. 識別主要角色與場景
    asset_refs = layer2_data.get("asset_refs", {})
    char_list = asset_refs.get("characters", [])
    location_id = asset_refs.get("scene_id", scene_id)
    loc_info = registry.get_location(location_id)

    # 尋找該段主要說話者或第一順位角色
    primary_speaker = None
    for s in shots:
        dlg = s.get("dialogue_and_audio", {})
        if dlg.get("has_dialogue") and dlg.get("speaker"):
            primary_speaker = dlg["speaker"]
            break

    ordered_char_ids: List[str] = []
    if primary_speaker:
        ordered_char_ids.append(primary_speaker)
    for c in char_list:
        cid = c.get("id") if isinstance(c, dict) else str(c)
        if cid and cid not in ordered_char_ids:
            ordered_char_ids.append(cid)
    if not ordered_char_ids:
        ordered_char_ids.append("C-Protagonist")

    # 根據 max_char_refs 限制參考圖數量（防止同質化混臉）
    selected_char_ids = ordered_char_ids[:max(1, max_char_refs)]
    secondary_char_ids = ordered_char_ids[max(1, max_char_refs):]

    # 建立 reference_images 清單 (<Picture 1> 為場景，<Picture 2..> 為角色)
    reference_images: List[Dict[str, Any]] = [
        {
            "id": loc_info["id"],
            "type": "scene",
            "description": loc_info["desc_en"],
            "path": loc_info["ref_img"]
        }
    ]

    subject_def_lines: List[str] = [
        f"<Picture 1> is the establishing background plate of {loc_info['desc_en']}."
    ]
    retention_lines: List[str] = [
        f"<Picture 1> (first frame): fully_preserved - the architectural layout, spatial perspective, and lighting atmosphere are retained."
    ]

    has_creature = False
    for k, cid in enumerate(selected_char_ids, start=1):
        c_info = registry.get_character(cid)
        pic_no = k + 1
        reference_images.append({
            "id": c_info["id"],
            "type": "character",
            "description": c_info["desc_en"],
            "path": c_info["ref_img"],
            "is_primary_character": (k == 1)
        })
        subject_def_lines.append(
            f"<Subject {k}> is the character in <Picture {pic_no}>, {c_info['desc_en']}."
        )
        retention_text = (
            f"<Subject {k}> (appears across shots): fully_preserved - the facial identity, hairstyle, and wardrobe from <Picture {pic_no}> are retained."
        )
        if c_info.get("is_creature"):
            has_creature = True
            retention_text += " Ignore neutral gray/white studio background of creature turnaround sheet."
        retention_lines.append(retention_text)

    # 次要角色以純文字特徵補充
    for cid in secondary_char_ids:
        c_info = registry.get_character(cid)
        retention_lines.append(
            f"Secondary character {c_info['name']} appears with {c_info['desc_en']} as pure text description without reference image to avoid feature bleed."
        )

    # 2. summary
    summary_block = (
        f"summary:\n"
        f"[keyframe completion + reference generation] The video begins from <Picture 1> and follows <Subject 1> "
        f"across {len(shots)} shots ({target_dur:.1f}s, {aspect}), executing choreographed actions with emotional continuity."
    )

    # 3. retention_analysis
    style_lock = layer2_data.get("style_lock", {})
    lighting_line = metadata.get("lighting_lock_line") or style_lock.get("lighting_lock_line") or "natural ambient cinematic light"
    lighting_line_clean, _ = strip_hex(palette_names(lighting_line))

    retention_lines.append(
        f"Continuity anchors: lighting locked to '{lighting_line_clean}'; camera strictly maintains 180-degree axis; "
        f"subject coordinates follow clear blocking; clothing and surface textures are preserved throughout."
    )
    retention_block = "retention_analysis:\n" + "\n".join(retention_lines)

    # 4. detailed_description
    # 確保全段至少 1 個光源名詞 (E9)
    light_source_term = "natural ambient light"
    for lt in LIGHT_SOURCE_TERMS:
        if re.search(rf"\b{lt}\b", lighting_line_clean, re.IGNORECASE):
            light_source_term = lt
            break
    if light_source_term == "natural ambient light":
        lighting_line_clean += " with soft ambient sunlight and rim light"

    det_desc_header = f"The target video is live-action cinematic ({aspect}), illuminated by {lighting_line_clean}."
    shot_descriptions: List[str] = []

    # 計算切點時間戳 (E4: 切點數 = N-1、首切點 >= 2s、間隔 >= 2s、末切點空間 >= 2s)
    n_shots = len(shots)
    cut_timestamps: List[float] = []

    if n_shots > 1:
        # 初始依據各鏡頭 duration 計算累加時間
        cur_t = 0.0
        raw_cuts = []
        for s in shots[:-1]:
            cur_t += float(s.get("duration", 2.5))
            raw_cuts.append(cur_t)

        # 動態調整切點確保：首切點 >= 2.0s，相鄰 >= 2.0s，末切點 <= eff_d - 2.0s
        min_first = 2.0
        max_last = max(min_first + 2.0 * (n_shots - 2), eff_d - 2.05)

        # 均勻重新分佈以避開邊界死鎖
        if n_shots == 2:
            cut_timestamps = [round(min(max(raw_cuts[0], 2.0), eff_d - 2.05), 3)]
        else:
            step = (max_last - min_first) / max(1, n_shots - 2)
            cut_timestamps = [round(min_first + i * step, 3) for i in range(n_shots - 1)]

    last_motion = ""
    for idx, s in enumerate(shots, start=1):
        dur = float(s.get("duration", 2.5))
        cam = s.get("camera_optics", {})
        shot_size = cam.get("shot_size", "MS")
        optics_focal = cam.get("focal_length", "35mm")
        optics_dist = cam.get("physical_distance", "1.5m")
        raw_motion = cam.get("movement", "static")

        motion = map_camera_motion(raw_motion, idx)
        if motion == last_motion and motion in OFFICIAL_MOTION_FALLBACKS:
            # 輪換運鏡避免 W10 重複警告
            alt_idx = (OFFICIAL_MOTION_FALLBACKS.index(motion) + 1) % len(OFFICIAL_MOTION_FALLBACKS)
            motion = OFFICIAL_MOTION_FALLBACKS[alt_idx]
        last_motion = motion

        # 動作力學三要素整合
        act = s.get("action_and_performance", {})
        stages = act.get("action_stages", [])
        clean_stages = []
        for st in stages:
            st_clean = re.sub(r"^\[?TODO\]?[:：]?", "", st).strip()
            if st_clean:
                clean_stages.append(st_clean)

        if not clean_stages:
            action_clause = "executes deliberate physical blocking with natural body movement"
        else:
            action_clause = " -> ".join(clean_stages)

        expression = re.sub(r"^\[?TODO\]?[:：]?", "", act.get("observable_expression", "")).strip()
        expression_clause = f", expression: {expression}" if expression else ""

        # 台詞與閉唇鎖
        dlg = s.get("dialogue_and_audio", {})
        if dlg.get("has_dialogue") and dlg.get("line_verbatim"):
            line_text = dlg["line_verbatim"].strip()
            speech_chars = count_speech_chars(line_text)
            speaker_tag = "<Subject 1>"
            speech_clause = f", {speaker_tag} speaks: <d>[Chinese] {line_text}</d>"
        else:
            speech_clause = ", while their lips remain completely closed"

        # 連接詞 then / as 確保 (E7)
        if idx == 1:
            header_prefix = f"[Shot 1] The shot begins from <Picture 1>: {shot_size} ({optics_focal}, {optics_dist}) of <Subject 1>."
        else:
            cut_time_str = format_timestamp(cut_timestamps[idx - 2])
            header_prefix = f"[Shot {idx}] At {cut_time_str}, the shot transitions to a {shot_size} of <Subject 1>:"

        is_last = (idx == n_shots)
        tail_freeze = " Then the subject holds a steady static freeze to conclude the segment." if is_last else " Then the motion transitions smoothly."

        shot_body = (
            f"{header_prefix} First <Subject 1> initiates {action_clause}{expression_clause}{speech_clause}, "
            f"then as the camera {motion} to frame the subject.{tail_freeze}"
        )
        shot_descriptions.append(sanitize_english_text(shot_body))

    detailed_block = "detailed_description:\n" + det_desc_header + "\n" + "\n".join(shot_descriptions)

    # 5. overall_soundscape
    foley_list = []
    for s in shots:
        dlg = s.get("dialogue_and_audio", {})
        fol = dlg.get("foley_and_ambience")
        if fol and "TODO" not in fol:
            foley_list.append(fol)
    if not foley_list:
        foley_list = ["Atmospheric ambient environmental room tone, subtle clothing rustle and footsteps."]
    soundscape_block = "overall_soundscape:\n" + " ".join(foley_list)

    # 6. non_diegetic_music
    music_block = (
        "non_diegetic_music:\n"
        "Low atmospheric cinematic score matching the tension of the scene, with subtle string swells."
    )

    # 拼裝六段式 Prompt
    full_h3_prompt = (
        f"subject_definitions:\n" + "\n".join(subject_def_lines) + "\n\n"
        f"{summary_block}\n\n"
        f"{retention_block}\n\n"
        f"{detailed_block}\n\n"
        f"{soundscape_block}\n\n"
        f"{music_block}\n"
    )

    # 7. LoRA 適配
    lora_payload = {"loras": []}
    if auto_lora:
        # 綜合全段鏡頭特徵推導 LoRA
        combined_spec = {
            "focal": shots[0].get("camera_optics", {}).get("focal_length", "35mm"),
            "pov": shots[0].get("camera_optics", {}).get("pov_routing", "objective"),
            "action": " ".join(" ".join(s.get("action_and_performance", {}).get("action_stages", [])) for s in shots),
            "expression": " ".join(s.get("action_and_performance", {}).get("observable_expression", "") for s in shots),
            "dialogue": " ".join(s.get("dialogue_and_audio", {}).get("line_verbatim", "") or "" for s in shots),
            "anchor_obj": " ".join(" ".join(s.get("spatial_blocking", {}).get("anchor_objects", [])) for s in shots),
        }
        adapted = auto_adapt_h3_loras(combined_spec)
        lora_payload = {"loras": adapted["loras"]}

    return {
        "segment_id": seg_id,
        "scene_id": scene_id,
        "metadata": {
            "aspect_ratio": aspect,
            "target_duration_sec": target_dur,
            "effective_duration_sec": round(eff_d, 3),
            "shots_count": len(shots),
        },
        "reference_images": reference_images,
        "h3_prompt": full_h3_prompt,
        "h3_loras": lora_payload["loras"],
        "shots": shots,
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

    args = parser.parse_args()

    layer2_files = load_layer2_files(args.layer2)
    if not layer2_files:
        print(f"[錯誤] 找不到任何 Layer 2 分鏡檔案: {args.layer2}", file=sys.stderr)
        return 1

    registry = AssetRegistry(bible_path=args.bible, assets_path=args.assets)

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

        print("\n" + "=" * 75)
        print(f"📊 雙重審查總結: 錯誤數: {total_errors} | 警告數: {total_warnings}")
        print("=" * 75)
        if total_errors > 0:
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
