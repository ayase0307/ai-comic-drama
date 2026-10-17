#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
audit_refs_and_segments.py — 確定性產線稽核工具
（移植自《噩盡島》實戰工具鏈：refs_tool3.py + lint-seg.py + h3-lint.py）

功能：
1. 模式 A (--audit-refs / --fix-refs)：
   - 審查每段 JSON 的 reference_images 與 H3 提示詞中 subject_definitions、retention_analysis 序對一致性。
   - 確保 <Picture 1> 為場景，<Subject k> 嚴格對應 <Picture k+1>。
   - 檢查主角是否在前 5 名，同段掛多張角色圖時發出同質化混臉警告。
   - 支援 --fix-refs 由演員設定自動確定性生成並覆寫一致的資產定義。
2. 模式 B (--lint-h3)：
   - H3 分段提示詞 13 條確定性自檢（FreeVideo 17n+5 幀數取整真實有效秒數 D、
     6 大必填區塊、鏡頭數量連續性、禁止時間戳於 Shot 1、切點 >=2s、末切點空間、
     禁用運鏡詞、每鏡官方運鏡詞、時間推進詞 then/as、光源名詞、負面詞轉正面改寫、台詞語速等）。
3. 模式 C (--self-test)：
   - 內建 4 大記憶體回歸自檢測試，驗證 100% 確定性檢測與修復。

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
if sys.platform.startswith("win"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


# ==============================================================================
# 常數與規則庫
# ==============================================================================

# 1. 必填 6 大區塊標籤
REQUIRED_SECTIONS = [
    "subject_definitions",
    "summary",
    "retention_analysis",
    "detailed_description",
    "overall_soundscape",
    "non_diegetic_music",
]

# 2. 官方合法運鏡動詞（大小寫不敏感，單鏡必須剛好 1 個主要運鏡語義）
OFFICIAL_CAMERA_MOTIONS = [
    "static",
    "trucks left", "truck left", "trucking left",
    "trucks right", "truck right", "trucking right",
    "dollies in", "dolly in", "dollying in", "dolly-in",
    "dollies out", "dolly out", "dollying out", "dolly-out",
    "pans left", "pan left", "panning left",
    "pans right", "pan right", "panning right",
    "tilts up", "tilt up", "tilting up",
    "tilts down", "tilt down", "tilting down",
    "pedestals up", "pedestal up", "pedestaling up",
    "pedestals down", "pedestal down", "pedestaling down",
    "zooms in", "zoom in", "zooming in",
    "zooms out", "zoom out", "zooming out",
    "rolls clockwise", "rolling clockwise",
    "rolls counter-clockwise", "rolling counter-clockwise",
]

# 複合運鏡白名單（例如 trucks left while panning right）
COMPOUND_CAMERA_MOTIONS = [
    "trucks left while panning right", "truck left while panning right",
    "trucks right while panning left", "truck right while panning left",
    "pans left while trucking right", "pans right while trucking left",
    "pedestals up while tilting down", "pedestals down while tilting up",
]

# 3. 禁用運鏡詞
FORBIDDEN_CAMERA_MOTIONS = [
    "orbit", "arc", "circles around", "360-degree", "circle around"
]

# 4. 矛盾角度詞組（同鏡頭內不可同時出現）
CONFLICTING_ANGLE_PAIRS = [
    (r"\bhigh-angle\b", r"\blow-angle\b"),
    (r"\bbird'?s-eye\b", r"\bworm'?s-eye\b"),
    (r"\boverhead\b", r"\blow-angle\b"),
    (r"\beye-level\b", r"\bhigh-angle\b"),
    (r"\beye-level\b", r"\blow-angle\b"),
]

# 5. 光源名詞（整段提示詞中必須至少包含 1 個光源名詞）
LIGHT_SOURCE_TERMS = [
    "light", "lighting", "sunlight", "moonlight", "sun", "moon",
    "lamp", "lantern", "candle", "neon", "spotlight", "rim light",
    "backlight", "ambient light", "dusk light", "dawn light", "key light",
    "fill light", "flashlight", "torch", "shafts of light", "glow",
]

# 6. 負面詞與建議正面替換詞庫
REWRITE_NEGATIVE_PHRASES = {
    r"\bno blood\b": "the surface is smooth and dry / the skin remains intact",
    r"\bwithout blood\b": "the surface is smooth and dry / the skin remains intact",
    r"\bno visible text\b": "plain unmarked surface",
    r"\bwithout text\b": "plain unmarked surface",
    r"\bwithout injury\b": "unharmed, intact appearance",
    r"\bno teeth\b": "lips sealed / closed mouth",
    r"\bmust not\b": "remains calm and steady / avoid",
}


# ==============================================================================
# 幀數計算與真實有效秒數 (17n+5 規則)
# ==============================================================================

def frames_for(s: float, rounding: str = "floor") -> int:
    """計算 FreeVideo / MiniMax H3 遵循的 17n+5 幀數規格。
    rounding:
      - 'floor': 保守向下取整（如 7.0s -> 9 steps -> 158 幀），真實反映有效秒數可能縮水
      - 'round': 傳統四捨五入（如 7.0s -> 10 steps -> 175 幀）
    """
    raw_steps = (s * 24.0 - 5.0) / 17.0
    if rounding == "round":
        n = max(1, round(raw_steps))
    else:
        n = max(1, int(math.floor(raw_steps)))
    return 17 * n + 5


def effective_duration(s: float, rounding: str = "floor") -> float:
    """計算 FreeVideo 取整後的真實有效秒數 D = frames_for(s) / 24.0。"""
    return frames_for(s, rounding=rounding) / 24.0


# ==============================================================================
# 模式 A：參考圖與 subject_definitions 稽核與修復
# ==============================================================================

def extract_prompt_from_seg(seg_data: Dict[str, Any]) -> str:
    """自各種常見分鏡與分段 JSON 結構中提取 H3 提示詞文本。"""
    if "h3_prompt" in seg_data and isinstance(seg_data["h3_prompt"], str):
        return seg_data["h3_prompt"]
    if "prompt" in seg_data and isinstance(seg_data["prompt"], str):
        return seg_data["prompt"]
    if "compiled_prompts" in seg_data and isinstance(seg_data["compiled_prompts"], dict):
        if "minimax-h3" in seg_data["compiled_prompts"]:
            return seg_data["compiled_prompts"]["minimax-h3"]
    if "outputs" in seg_data and isinstance(seg_data["outputs"], dict):
        if "minimax-h3" in seg_data["outputs"]:
            return seg_data["outputs"]["minimax-h3"]
    return ""


def audit_refs_and_subjects(seg_data: Dict[str, Any]) -> Dict[str, Any]:
    """模式 A 審查：
    1. 檢查 reference_images 與 subject_definitions / retention_analysis 的對應關係。
    2. 驗證 <Picture 1> 為場景，<Subject k> 嚴格對應 <Picture k+1>。
    3. 檢查是否有缺圖、多餘圖、生物主角是否在前 5 名。
    4. 檢查同段是否掛載超過 1 張角色圖（混臉警告）。
    """
    errors: List[str] = []
    warnings: List[str] = []
    passed = True

    ref_images = seg_data.get("reference_images", [])
    if not isinstance(ref_images, list):
        errors.append("[E] JSON 中 reference_images 欄位應為陣列清單")
        return {"passed": False, "errors": errors, "warnings": warnings}

    prompt_text = extract_prompt_from_seg(seg_data)

    # 1. 參考圖數量與主角名次檢查
    total_refs = len(ref_images)
    if total_refs > 9:
        errors.append(f"[E] reference_images 數量為 {total_refs} 張，超出 H3 上限 9 張！")

    char_refs = [r for r in ref_images if isinstance(r, dict) and r.get("type") in ("character", "role", "actor")]
    if len(char_refs) > 1:
        warnings.append(
            f"[W: 混臉風險] 同段掛載了 {len(char_refs)} 張角色參考圖！"
            f"多張角色圖同段可能被模型平均成同一張臉，保守建議一段一張角色圖（其餘角色用文字描述）。"
        )

    # 檢查主要生物角色是否在前 5 名
    for idx, ref in enumerate(ref_images):
        if isinstance(ref, dict) and ref.get("is_primary_character"):
            if idx >= 5:
                errors.append(
                    f"[E: 主角被擠出前5名] 主要角色 {ref.get('id', idx)} 位於第 {idx+1} 張參考圖（<Picture {idx+1}>），"
                    f"H3 注意力在第 5 張之後急遽衰退，主要角色必須放在前 5 名！"
                )

    # 2. 若有 H3 提示詞，進行語義標籤序對逐條對帳
    if prompt_text:
        # 解析 subject_definitions 區塊
        sub_def_match = re.search(r"subject_definitions:(.*?)(?:\n\n[a-z_]+:|\Z)", prompt_text, re.DOTALL)
        if sub_def_match:
            sub_def_body = sub_def_match.group(1)

            # 檢查 <Picture 1> 是否為場景
            pic1_match = re.search(r"<Picture\s*1>(.*?)(?:\n|$)", sub_def_body)
            if pic1_match:
                pic1_line = pic1_match.group(1).lower()
                non_scene_cues = ["character", "woman", "man", "girl", "boy", "young", "person"]
                scene_cues = ["scene", "background", "layout", "first frame", "shot begins", "rooftop", "room", "plate"]
                if any(nc in pic1_line for nc in non_scene_cues) and not any(sc in pic1_line for sc in scene_cues):
                    warnings.append(
                        f"[W: 首幀/場景慣例] <Picture 1> 定義偏向人物而非場景底圖或開場幀，"
                        f"實測建議 <Picture 1> 作為場景/首幀構圖錨點，人物從 <Picture 2> 起編。"
                    )

            # 檢查 <Subject k> 是否對應 <Picture k+1>
            subject_lines = re.findall(r"<Subject\s*(\d+)>.*?<Picture\s*(\d+)>", sub_def_body)
            for s_num_str, p_num_str in subject_lines:
                s_num, p_num = int(s_num_str), int(p_num_str)
                expected_pic = s_num + 1
                if p_num != expected_pic:
                    errors.append(
                        f"[E: 序對脫節] <Subject {s_num}> 定義引用了 <Picture {p_num}>！"
                        f"標準規範應嚴格對應 <Picture {expected_pic}>（<Picture 1> 為場景，角色從 2 遞增）。"
                    )

            # 檢查是否存在未定義的 Picture 引用
            all_pics_in_prompt = set(int(m) for m in re.findall(r"<Picture\s*(\d+)>", prompt_text))
            for p in all_pics_in_prompt:
                if p > total_refs and total_refs > 0:
                    errors.append(f"[E: 缺圖錯誤] Prompt 中引用了 <Picture {p}>，但 reference_images 僅有 {total_refs} 張！")
        else:
            warnings.append("[W] 提示詞中缺少 subject_definitions 區塊，無法執行逐條序對對帳。")

    passed = len(errors) == 0
    return {
        "passed": passed,
        "errors": errors,
        "warnings": warnings,
        "total_references": total_refs,
        "character_references": len(char_refs),
    }


def fix_refs_and_subjects(seg_data: Dict[str, Any]) -> Dict[str, Any]:
    """模式 A 自動修復：
    1. 依據演員表重整 reference_images：第一張為場景（若無則保留空或預設），角色依序排列。
    2. 重新產生 100% 序對一致的 subject_definitions 與 retention_analysis。
    3. 自動同步置換 prompt 文本中的相關標籤。
    """
    fixed = dict(seg_data)
    refs = list(fixed.get("reference_images", []))
    characters = fixed.get("characters", []) or fixed.get("cast", [])

    scene_refs = [r for r in refs if isinstance(r, dict) and r.get("type") in ("scene", "plate", "background", "keyframe")]
    char_refs = [r for r in refs if isinstance(r, dict) and r.get("type") in ("character", "role", "actor")]
    other_refs = [r for r in refs if r not in scene_refs and r not in char_refs]

    # 若無場景參考圖，但有設定 scene_id，則建立預設場景參考
    if not scene_refs:
        scene_name = fixed.get("scene_name", fixed.get("scene_id", "scene_plate"))
        scene_refs = [{
            "id": f"{scene_name}_plate",
            "type": "scene",
            "path": f"assets/scenes/{scene_name}.png",
            "description": f"Scene environment background plate for {scene_name}",
        }]

    # 重新編排 reference_images：<Picture 1> 場景，接續角色
    reordered_refs = scene_refs[:1] + char_refs + other_refs
    fixed["reference_images"] = reordered_refs

    # 重建 subject_definitions
    sub_def_lines = [
        f"<Picture 1> is the establishing background plate and opening frame for the scene."
    ]
    retention_lines = [
        f"<Picture 1> (first frame environment): fully_preserved - the spatial geometry, architecture, and lighting are retained."
    ]

    for k, c_ref in enumerate(char_refs, start=1):
        pic_no = k + 1
        char_desc = c_ref.get("description") or f"character {c_ref.get('id', k)}"
        sub_def_lines.append(f"<Subject {k}> is the character in <Picture {pic_no}>, {char_desc}.")
        retention_lines.append(
            f"<Subject {k}> (appears across shots): fully_preserved - the facial identity, hairstyle, and wardrobe from <Picture {pic_no}> are retained."
        )

    new_sub_def_block = "subject_definitions:\n" + "\n".join(sub_def_lines) + "\n"
    new_retention_block = "retention_analysis:\n" + "\n".join(retention_lines) + "\n"

    # 若已有 prompt，覆寫或注入該區塊
    prompt_text = extract_prompt_from_seg(fixed)
    if prompt_text:
        # 置換 subject_definitions
        if "subject_definitions:" in prompt_text:
            prompt_text = re.sub(
                r"subject_definitions:(.*?)(?:\n\n(?=[a-z_]+:)|\Z)",
                new_sub_def_block + "\n",
                prompt_text,
                flags=re.DOTALL
            )
        else:
            prompt_text = new_sub_def_block + "\n" + prompt_text

        # 置換 retention_analysis
        if "retention_analysis:" in prompt_text:
            prompt_text = re.sub(
                r"retention_analysis:(.*?)(?:\n\n(?=[a-z_]+:)|\Z)",
                new_retention_block + "\n",
                prompt_text,
                flags=re.DOTALL
            )
        else:
            # 插入在 summary 之後或開頭
            if "summary:" in prompt_text:
                prompt_text = re.sub(
                    r"(summary:.*?\n\n)",
                    r"\1" + new_retention_block + "\n",
                    prompt_text,
                    flags=re.DOTALL
                )
            else:
                prompt_text += "\n\n" + new_retention_block

        if "h3_prompt" in fixed:
            fixed["h3_prompt"] = prompt_text
        elif "prompt" in fixed:
            fixed["prompt"] = prompt_text
        else:
            fixed["h3_prompt"] = prompt_text

    return fixed


# ==============================================================================
# 模式 B：H3 分段提示詞 13 條確定性自檢 (--lint-h3)
# ==============================================================================

def lint_h3_prompt(
    prompt_text: str,
    nominal_duration: float = 7.0,
    rounding_mode: str = "floor",
) -> Dict[str, Any]:
    """對 H3 分段提示詞執行 13 條確定性工程自檢。
    支援 5–10 秒短分段與 15 秒段，動態計算 FreeVideo 取整有效秒數 D。
    """
    errors: List[str] = []
    warnings: List[str] = []

    clean_prompt = prompt_text.strip()
    if not clean_prompt:
        errors.append("[E: 空文本] 提示詞內容為空！")
        return {"passed": False, "errors": errors, "warnings": warnings, "details": {}}

    # 計算真實有效時長 D
    eff_d = effective_duration(nominal_duration, rounding=rounding_mode)
    details: Dict[str, Any] = {
        "nominal_duration": nominal_duration,
        "effective_duration_sec": round(eff_d, 3),
        "rounding_mode": rounding_mode,
        "frames": frames_for(nominal_duration, rounding=rounding_mode),
    }

    # --------------------------------------------------------------------------
    # 規則 1 (E): 6 大必填區塊缺漏檢查
    # --------------------------------------------------------------------------
    missing_sections = []
    for sec in REQUIRED_SECTIONS:
        # 匹配 sec: 開頭的區塊
        if not re.search(rf"\b{sec}:", clean_prompt, re.IGNORECASE):
            missing_sections.append(sec)
    if missing_sections:
        errors.append(f"[E1: 必填區塊缺漏] 缺少以下必填區塊標籤: {', '.join(missing_sections)}")

    # 提取 detailed_description 內容以供進一步檢查
    det_match = re.search(r"detailed_description:(.*?)(?:\n\n[a-z_]+:|\Z)", clean_prompt, re.DOTALL | re.IGNORECASE)
    detailed_desc = det_match.group(1).strip() if det_match else clean_prompt

    # --------------------------------------------------------------------------
    # 規則 2 (E): [Shot 1..N] 數量與編號連續性
    # --------------------------------------------------------------------------
    shot_headers = re.findall(r"\[Shot\s+(\d+)\](?:\s+At\s+(\d{2}):(\d{2}(?:\.\d+)?))?", detailed_desc, re.IGNORECASE)
    n_shots = len(shot_headers)
    details["shot_count"] = n_shots

    if n_shots == 0:
        errors.append("[E2: 缺少鏡頭標籤] 未找到任何 [Shot N] 格式的鏡頭宣告！")
    else:
        # 檢查編號連續性 (1, 2, ..., N)
        shot_indices = [int(h[0]) for h in shot_headers]
        expected_indices = list(range(1, n_shots + 1))
        if shot_indices != expected_indices:
            errors.append(f"[E2: 鏡頭序號不連續] 實際序號為 {shot_indices}，期望為 {expected_indices}")

        # 檢查鏡頭數量與有效時長匹配
        if eff_d < 10.0:
            if not (2 <= n_shots <= 6):
                errors.append(f"[E2: 鏡頭數量不符] 時長 D={eff_d:.2f}s (<10s) 應為 2–6 鏡，實際為 {n_shots} 鏡！")
        else:
            if not (4 <= n_shots <= 6):
                errors.append(f"[E2: 鏡頭數量不符] 時長 D={eff_d:.2f}s (>=10s) 應為 4–6 鏡，實際為 {n_shots} 鏡！")

    # --------------------------------------------------------------------------
    # 規則 3 (E): [Shot 1] 嚴禁帶 At 00:00.000 時間戳
    # --------------------------------------------------------------------------
    shot1_match = re.search(r"\[Shot\s+1\](?:\s+At\s+[0-9:\.]+)?", detailed_desc, re.IGNORECASE)
    if shot1_match and "At " in shot1_match.group(0):
        errors.append(f"[E3: 首鏡時間戳違規] [Shot 1] 嚴禁帶 At 時間戳（語法強制由第一格自動開場）: '{shot1_match.group(0)}'")

    # --------------------------------------------------------------------------
    # 規則 4 (E): 切點數 = N-1、嚴格遞增、相鄰 >=2s、取整後 D - 末切點 >= 2s
    # --------------------------------------------------------------------------
    cut_timestamps: List[float] = []
    for h in shot_headers[1:]:
        mm_str, ss_str = h[1], h[2]
        if mm_str and ss_str:
            t = float(mm_str) * 60.0 + float(ss_str)
            cut_timestamps.append(t)

    details["cut_timestamps"] = cut_timestamps

    if n_shots > 1:
        if len(cut_timestamps) != n_shots - 1:
            errors.append(
                f"[E4: 切點數不匹配] 共 {n_shots} 鏡，應有 {n_shots - 1} 個切點時間戳，"
                f"實際解析到 {len(cut_timestamps)} 個！"
            )
        else:
            # 首切點 >= 2.0s
            if cut_timestamps[0] < 2.0:
                errors.append(f"[E4: 首切點太短] 首個切點時間為 {cut_timestamps[0]:.2f}s < 2.0s，第 1 鏡曝光不足！")

            # 嚴格遞增且相鄰切點差 >= 2.0s
            for i in range(len(cut_timestamps) - 1):
                diff = cut_timestamps[i + 1] - cut_timestamps[i]
                if diff < 1.999:  # 容許微小浮點誤差
                    errors.append(
                        f"[E4: 切點間隔過短] 切點 {cut_timestamps[i]:.2f}s 到 {cut_timestamps[i+1]:.2f}s 間隔僅 {diff:.2f}s (<2.0s)！"
                    )

            # 末切點留白：D - 末切點 >= 2.0s (抓出 7.0s 取整為 6.583s 後末切點 5.0s 的崩潰 Bug)
            last_cut = cut_timestamps[-1]
            tail_room = eff_d - last_cut
            if tail_room < 1.999:
                errors.append(
                    f"[E4: 末切點空間不足（隱藏Bug攔截）] 取整後真實秒數 D={eff_d:.3f}s，末切點為 {last_cut:.3f}s，"
                    f"收尾剩餘僅 {tail_room:.3f}s (<2.0s)！請將末切點提前或縮減鏡頭數。"
                )

    # --------------------------------------------------------------------------
    # 規則 5 (E): 禁用運鏡詞攔截
    # --------------------------------------------------------------------------
    for f_term in FORBIDDEN_CAMERA_MOTIONS:
        if re.search(rf"\b{f_term}\b", detailed_desc, re.IGNORECASE):
            errors.append(
                f"[E5: 禁用運鏡詞] 檢測到禁止運鏡詞 '{f_term}'！"
                f"H3 不支援真實環繞，建議改為 'trucks left while panning right'。"
            )

    # --------------------------------------------------------------------------
    # 規則 6 (E): 每鏡必須剛好 1 個官方運鏡語義
    # 規則 7 (E): 必含 then 或 as 時間推進連接詞
    # 規則 8 (E): 同鏡無矛盾角度詞
    # --------------------------------------------------------------------------
    shot_blocks = re.split(r"\[Shot\s+\d+\]", detailed_desc, flags=re.IGNORECASE)[1:]
    shot_motions: List[str] = []

    for idx, block in enumerate(shot_blocks, start=1):
        b_lower = block.lower()

        # 運鏡匹配
        found_motion: Optional[str] = None
        # 先檢查複合運鏡
        for cm in COMPOUND_CAMERA_MOTIONS:
            if cm in b_lower:
                found_motion = cm
                break
        if not found_motion:
            # 再檢查單一官方運鏡詞
            for om in OFFICIAL_CAMERA_MOTIONS:
                if re.search(rf"\b{om}\b", b_lower):
                    found_motion = om
                    break

        if not found_motion:
            errors.append(f"[E6: 缺少官方運鏡詞] [Shot {idx}] 未包含合規的官方運鏡詞（如 static, trucks left, dollies in 等）！")
        else:
            shot_motions.append(found_motion)

        # 時間推進詞 then 或 as
        has_time_connector = bool(re.search(r"\b(then|as)\b", b_lower))
        if not has_time_connector:
            errors.append(f"[E7: 缺少時間推進詞] [Shot {idx}] 缺少 'then' 或 'as' 連接詞，可能導致動作凍結！")

        # 角度矛盾詞
        for p1, p2 in CONFLICTING_ANGLE_PAIRS:
            if re.search(p1, b_lower) and re.search(p2, b_lower):
                errors.append(f"[E8: 角度矛盾] [Shot {idx}] 同鏡內同時出現矛盾角度描述 ({p1} 與 {p2})！")

    details["shot_motions"] = shot_motions

    # --------------------------------------------------------------------------
    # 規則 9 (E): 全段至少 1 個光源名詞 (防 OOM 拆段後跳光)
    # --------------------------------------------------------------------------
    has_light_source = any(re.search(rf"\b{lt}\b", clean_prompt, re.IGNORECASE) for lt in LIGHT_SOURCE_TERMS)
    if not has_light_source:
        errors.append(
            "[E9: 缺失光源名詞] 全段提示詞未找到任何具體光源名詞（如 light, sunlight, lamp, rim light 等）！"
            "OOM 拆段後後半段若遺失光源名詞必然導致跳色跳光。"
        )

    # --------------------------------------------------------------------------
    # 規則 10 (W): 相鄰鏡頭運鏡同款警告
    # --------------------------------------------------------------------------
    for i in range(len(shot_motions) - 1):
        if shot_motions[i] == shot_motions[i + 1]:
            warnings.append(
                f"[W10: 運鏡重複] [Shot {i+1}] 與 [Shot {i+2}] 均使用相同運鏡 '{shot_motions[i]}'，缺乏鏡頭動態節奏變化。"
            )

    # --------------------------------------------------------------------------
    # 規則 11 (W): 英文字數密度 (23.2 * D ~ 33.1 * D)
    # --------------------------------------------------------------------------
    words = re.findall(r"\b[A-Za-z0-9_-]+\b", detailed_desc)
    word_count = len(words)
    min_words = int(23.2 * eff_d)
    max_words = int(33.1 * eff_d)
    details["detailed_desc_word_count"] = word_count
    details["recommended_word_range"] = (min_words, max_words)

    if word_count < min_words:
        warnings.append(
            f"[W11: 描述偏短] detailed_description 英文字數僅 {word_count} 字，"
            f"低於推薦密度下限 {min_words} 字（時長 {eff_d:.1f}s）。"
        )
    elif word_count > max_words:
        warnings.append(
            f"[W11: 描述過長] detailed_description 英文字數達 {word_count} 字，"
            f"超出推薦密度上限 {max_words} 字（時長 {eff_d:.1f}s）。"
        )

    # --------------------------------------------------------------------------
    # 規則 12 (W): 負面詞警告 (no blood, without, must not 等)
    # --------------------------------------------------------------------------
    for neg_pat, rep_suggestion in REWRITE_NEGATIVE_PHRASES.items():
        if re.search(neg_pat, clean_prompt, re.IGNORECASE):
            clean_term = neg_pat.replace(r"\b", "")
            warnings.append(
                f"[W12: 負面詞警告] 提示詞包含負面描述 '{clean_term}'！"
                f"建議正面改寫為: '{rep_suggestion}'。"
            )

    # --------------------------------------------------------------------------
    # 規則 13 (W): 台詞密度與語速警告 (4 字/秒法則與 60% 片長上限)
    # --------------------------------------------------------------------------
    dialogue_matches = re.findall(r"<d>(?:\[[A-Za-z]+\])?(.*?)</d>", clean_prompt, re.DOTALL)
    total_dlg_chars = 0
    for dlg_text in dialogue_matches:
        # 去除標點符號計算中文字數
        clean_chinese = re.findall(r"[\u4e00-\u9fff]", dlg_text)
        total_dlg_chars += len(clean_chinese)
        if len(clean_chinese) > 15:
            warnings.append(
                f"[W13: 單句過長] 台詞單句長度達 {len(clean_chinese)} 字 (>15字)，容易造成 H3 加速嘴瓢！"
            )

    details["total_dialogue_chars"] = total_dlg_chars
    if total_dlg_chars > 0:
        speech_sec = total_dlg_chars / 4.0
        details["estimated_speech_seconds"] = round(speech_sec, 2)
        speech_ratio = speech_sec / max(eff_d, 0.5)
        details["speech_ratio"] = round(speech_ratio, 3)
        if speech_ratio > 0.60:
            warnings.append(
                f"[W13: 台詞佔比過載] 台詞預估耗時 {speech_sec:.1f}s ({total_dlg_chars}字 / 4字/秒)，"
                f"佔真實時長 {eff_d:.1f}s 之 {speech_ratio:.1%} (>60%)，角色表演將缺乏氣口與留白！"
            )

    passed = len(errors) == 0
    return {
        "passed": passed,
        "errors": errors,
        "warnings": warnings,
        "details": details,
    }


# ==============================================================================
# 模式 C：內建自檢單元測試 (--self-test)
# ==============================================================================

def run_self_tests() -> bool:
    """執行模式 C 內建自檢回歸測試：
    案例 1: 正常 7.0s 分段提示詞（全部通過，0 錯誤）
    案例 2: 7.0s 因 17n+5 取整為 6.58s 導致末切點 5.0s 違規案例（精準攔截末切點不足 2.0s）
    案例 3: 含 orbit、no blood 與缺光源名詞的違規案例（精準攔截並警告）
    案例 4: subject_definitions 與 reference_images 順序脫節案例（精準攔截並修復）
    """
    print("=" * 75)
    print("🧪 啟動 audit_refs_and_segments 確定性稽核工具內建自檢套件 (--self-test)")
    print("=" * 75)

    all_passed = True

    # --------------------------------------------------------------------------
    # 測試案例 1：正常合規 7.0s 短分段（切點在 00:03.000，取整後 6.58s，6.58 - 3.0 = 3.58s >= 2.0s）
    # --------------------------------------------------------------------------
    valid_prompt_7s = """subject_definitions:
<Picture 1> is the establishing rooftop background plate at dusk.
<Subject 1> is the young woman in <Picture 2>, with shoulder-length black hair in a long beige trench coat.

summary:
[keyframe completion + reference generation] The video begins from <Picture 1> and follows <Subject 1> across two shots.

retention_analysis:
<Picture 1> (first frame): fully_preserved - the concrete floor and railings are retained.
<Subject 1> (appears across shots): fully_preserved - the facial features from <Picture 2> are retained.

detailed_description:
The target video is live-action cinematic, with natural warm dusk sunlight.
[Shot 1] The shot begins from <Picture 1>: eye-level medium shot of <Subject 1> standing on the concrete rooftop. First she turns slowly to her right toward the skyline, then the wind lifts the hem of her trench coat as the camera trucks left while panning right to keep her centered.
[Shot 2] At 00:03.000, the shot cuts to a close-up of <Subject 1> facing forward: first her eyes narrow slightly with steady focus, then she takes a deep breath as the camera holds a static shot.

overall_soundscape:
Low hum of wind blowing across the concrete roof.

non_diegetic_music:
A soft piano melody begins at 00:03.000.
"""
    res1 = lint_h3_prompt(valid_prompt_7s, nominal_duration=7.0, rounding_mode="floor")
    print(f"\n[Test 1] 正常合規 7.0s 分段提示詞自檢:")
    print(f"  - 通過狀態: {res1['passed']} (預期: True)")
    print(f"  - 錯誤數量: {len(res1['errors'])} (預期: 0)")
    if res1["errors"]:
        print(f"  ❌ 意外報錯: {res1['errors']}")
        all_passed = False
    else:
        print("  ✅ 成功通過合規分段檢查！")

    # --------------------------------------------------------------------------
    # 測試案例 2: 7.0s 取整為 6.583s 後末切點 5.0s 空間不足案例
    # --------------------------------------------------------------------------
    flawed_cut_prompt = """subject_definitions:
<Picture 1> is the establishing plate.
<Subject 1> is the woman in <Picture 2>.

summary:
[reference generation] Two shots sequence.

retention_analysis:
<Subject 1>: fully_preserved.

detailed_description:
Live-action cinematic, illuminated by soft dusk sunlight.
[Shot 1] Medium shot, first she moves then the camera trucks left.
[Shot 2] At 00:05.000, close up shot, first she looks then as the camera holds a static shot.

overall_soundscape:
Wind blows.

non_diegetic_music:
N/A
"""
    res2 = lint_h3_prompt(flawed_cut_prompt, nominal_duration=7.0, rounding_mode="floor")
    has_tail_err = any("末切點空間不足" in e or "E4" in e for e in res2["errors"])
    print(f"\n[Test 2] 7.0s 經 17n+5 取整為 6.58s 後末切點 5.0s 空間不足隱藏 Bug 攔截:")
    print(f"  - 通過狀態: {res2['passed']} (預期: False)")
    print(f"  - 攔截末切點錯誤: {has_tail_err} (預期: True)")
    if not res2["passed"] and has_tail_err:
        print(f"  ✅ 成功精確攔截末切點空間不足隱藏 Bug: {res2['errors'][0]}")
    else:
        print(f"  ❌ 攔截失敗: {res2['errors']}")
        all_passed = False

    # --------------------------------------------------------------------------
    # 測試案例 3: 含 orbit 禁用運鏡、no blood 負面詞與缺少光源名詞案例
    # --------------------------------------------------------------------------
    bad_motion_prompt = """subject_definitions:
<Picture 1> is the plate.
<Subject 1> is the fighter in <Picture 2>.

summary:
[reference generation] A quick fight scene.

retention_analysis:
<Subject 1>: fully_preserved.

detailed_description:
A dark room with zero illumination.
[Shot 1] The camera orbit around the fighter, first he punches then as he recovers with no blood on his knuckles.
[Shot 2] At 00:02.500, he turns then as the camera holds a static shot.

overall_soundscape:
Footsteps.

non_diegetic_music:
N/A
"""
    res3 = lint_h3_prompt(bad_motion_prompt, nominal_duration=7.0, rounding_mode="floor")
    has_orbit_err = any("禁用運鏡詞" in e or "orbit" in e for e in res3["errors"])
    has_light_err = any("缺失光源名詞" in e or "E9" in e for e in res3["errors"])
    has_blood_warn = any("no blood" in w for w in res3["warnings"])
    print(f"\n[Test 3] 禁用運鏡詞 (orbit)、缺光源名詞與負面詞 (no blood) 綜合自檢:")
    print(f"  - orbit 攔截: {has_orbit_err} (預期: True)")
    print(f"  - 缺光源攔截: {has_light_err} (預期: True)")
    print(f"  - no blood 警告: {has_blood_warn} (預期: True)")
    if has_orbit_err and has_light_err and has_blood_warn:
        print("  ✅ 成功精確攔截禁用運鏡、缺光源詞與發出負面詞改寫警告！")
    else:
        print(f"  ❌ 攔截不完整: errors={res3['errors']}, warnings={res3['warnings']}")
        all_passed = False

    # --------------------------------------------------------------------------
    # 測試案例 4: reference_images 與 subject_definitions 序對脫節與自動修復
    # --------------------------------------------------------------------------
    seg_unaligned = {
        "segment_id": "SEG01",
        "scene_name": "rooftop_night",
        "reference_images": [
            {"id": "char_A", "type": "character", "description": "hero with sword"},
            {"id": "scene_plate", "type": "scene", "description": "rooftop night plate"},
        ],
        "h3_prompt": """subject_definitions:
<Subject 1> is the hero in <Picture 1>.
<Subject 2> is another person in <Picture 3>.

summary:
Test summary.

retention_analysis:
<Subject 1>: fully_preserved.

detailed_description:
Lit by cold moonlight.
[Shot 1] First he stands then as the camera trucks left.
[Shot 2] At 00:03.000, first he walks then as the camera holds a static shot.

overall_soundscape:
Wind.

non_diegetic_music:
N/A
"""
    }
    audit_res4 = audit_refs_and_subjects(seg_unaligned)
    has_seq_err = any("序對脫節" in e or "Picture 1" in e for e in audit_res4["errors"])
    print(f"\n[Test 4] 參考圖與 subject_definitions 脫節稽核與 --fix-refs 確定性修復測試:")
    print(f"  - 脫節攔截: {has_seq_err} (預期: True)")

    fixed_seg = fix_refs_and_subjects(seg_unaligned)
    re_audit = audit_refs_and_subjects(fixed_seg)
    print(f"  - 修復後通過狀態: {re_audit['passed']} (預期: True)")
    print(f"  - 修復後參考圖首張類型: {fixed_seg['reference_images'][0]['type']} (預期: scene)")
    if has_seq_err and re_audit["passed"] and fixed_seg["reference_images"][0]["type"] == "scene":
        print("  ✅ 成功精確攔截脫節並藉由 --fix-refs 確定性修復至 100% 合規！")
    else:
        print(f"  ❌ 修復驗證失敗: errors={re_audit['errors']}")
        all_passed = False

    print("\n" + "=" * 75)
    if all_passed:
        print("🎉 【audit_refs_and_segments】所有自檢測試 100% 通過！確定性工具鏈已完全驗證！")
    else:
        print("❌ 自檢測試未全部通過，請檢查邏輯。")
    print("=" * 75)
    return all_passed


# ==============================================================================
# CLI 主程式
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="確定性產線稽核工具 (移植自《噩盡島》refs_tool3 + lint-seg + h3-lint)"
    )
    parser.add_argument("--self-test", action="store_true", help="執行內建完整單元自檢回歸測試")
    parser.add_argument("--audit-refs", metavar="FILE_OR_DIR", help="審查指定分段 JSON 檔或目錄的參考圖與語義定義序對")
    parser.add_argument("--fix-refs", action="store_true", help="搭配 --audit-refs，自動以演員表重寫並修復至 100%% 合規")
    parser.add_argument("--lint-h3", metavar="FILE_OR_DIR", help="對指定分段 JSON 或提示詞文本執行 13 條 H3 確定性自檢")
    parser.add_argument("--duration", type=float, default=7.0, help="分段目標名義秒數（預設: 7.0s）")
    parser.add_argument("--rounding", choices=["floor", "round"], default="floor", help="17n+5 取整模式（預設 floor: 保守檢驗真實秒數縮水）")

    args = parser.parse_args()

    if args.self_test:
        success = run_self_tests()
        sys.exit(0 if success else 1)

    if not args.audit_refs and not args.lint_h3:
        # 未帶參數預設執行自檢
        run_self_tests()
        return

    # 收集待檢查的 JSON 檔案
    target_path = pathlib.Path(args.audit_refs or args.lint_h3)
    json_files: List[pathlib.Path] = []
    if target_path.is_file():
        json_files.append(target_path)
    elif target_path.is_dir():
        json_files.extend(sorted(target_path.glob("*.json")))

    if not json_files:
        print(f"[錯誤] 找不到任何目標檔案: {target_path}", file=sys.stderr)
        sys.exit(1)

    total_files = len(json_files)
    total_errors = 0
    total_warnings = 0

    print("=" * 75)
    print(f"🎬 正在執行產線確定性稽核: {target_path} (共 {total_files} 個檔案)")
    print("=" * 75)

    for p in json_files:
        print(f"\n▶ 檔案: {p.name}")
        try:
            with p.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as exc:
            print(f"  ❌ JSON 讀取失敗: {exc}")
            total_errors += 1
            continue

        # 模式 A: 審查與修復參考圖
        if args.audit_refs:
            if args.fix_refs:
                data = fix_refs_and_subjects(data)
                with p.open("w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                    f.write("\n")
                print(f"  🔧 已自動覆寫修復 reference_images 與 subject_definitions！")

            refs_res = audit_refs_and_subjects(data)
            if refs_res["passed"]:
                print("  [PASS] 參考圖與主體定義序對稽核通過")
            else:
                for e in refs_res["errors"]:
                    print(f"  ❌ {e}")
                total_errors += len(refs_res["errors"])
            for w in refs_res["warnings"]:
                print(f"  ⚠️ {w}")
            total_warnings += len(refs_res["warnings"])

        # 模式 B: H3 提示詞 13 條自檢
        if args.lint_h3:
            prompt_str = extract_prompt_from_seg(data)
            dur = float(data.get("metadata", {}).get("target_duration_sec", args.duration))
            lint_res = lint_h3_prompt(prompt_str, nominal_duration=dur, rounding_mode=args.rounding)
            if lint_res["passed"]:
                print(f"  [PASS] H3 提示詞 13 條自檢通過 (名義 {dur}s -> 真實有效 {lint_res['details']['effective_duration_sec']}s)")
            else:
                for e in lint_res["errors"]:
                    print(f"  ❌ {e}")
                total_errors += len(lint_res["errors"])
            for w in lint_res["warnings"]:
                print(f"  ⚠️ {w}")
            total_warnings += len(lint_res["warnings"])

    print("\n" + "=" * 75)
    print(f"📊 稽核總結: 檢查 {total_files} 個檔案 | 錯誤 (Errors): {total_errors} | 警告 (Warnings): {total_warnings}")
    print("=" * 75)
    sys.exit(0 if total_errors == 0 else 1)


if __name__ == "__main__":
    main()
