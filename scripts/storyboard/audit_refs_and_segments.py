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
   - H3 分段提示詞 17 條確定性自檢（FreeVideo 17n+5 幀數取整真實有效秒數 D、
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

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import style_rules  # noqa: E402
from pathlib import Path

try:  # 以 scripts/storyboard 為 sys.path 執行（CLI 慣例）
    import h3_spec
except ImportError:  # pragma: no cover - 套件匯入路徑
    from . import h3_spec

# 確保 Windows 終端輸出 UTF-8
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


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
      - 'ceil': 向上取整，保留完整台詞窗與原編排停頓

    實作已集中到 `h3_spec.py`（單一真值來源）；這裡只保留向後相容的入口。
    """
    return h3_spec.frames_for(s, rounding=rounding)


def effective_duration(s: float, rounding: str = "floor") -> float:
    """計算 FreeVideo 取整後的真實有效秒數 D = frames_for(s) / 24.0。"""
    return h3_spec.seconds_for_frames(h3_spec.frames_for(s, rounding=rounding))


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


def _image_size(project_root: pathlib.Path, rel_path: str) -> Optional[Tuple[int, int]]:
    """讀取圖片像素尺寸；讀不到就回 None（不阻擋流程）。"""
    try:
        from PIL import Image  # Pillow 為選用依賴，缺少時跳過尺寸檢查
    except Exception:
        return None
    candidate = pathlib.Path(rel_path)
    if not candidate.is_absolute():
        candidate = pathlib.Path(project_root) / candidate
    try:
        with Image.open(candidate) as img:
            return int(img.width), int(img.height)
    except Exception:
        return None


# 群眾／路人類描述：這些人沒有參考圖，H3 會用唯一一張臉的造型去補，
# 造成背景長出穿同款衣服的複製人（本專案 EP01-S01-a 實測：火山島上長出整群白襯衫學生）。
_CROWD_CUES = (
    "tourists", "visitors", "crowd", "onlookers", "pedestrians", "passersby",
    "bystanders", "commuters", "shoppers", "people in the background",
    "群眾", "路人", "遊客", "人潮", "圍觀", "行人", "人群", "群演", "觀光客",
)
# 可接受的人群寫法：不可辨識、沒有臉、剪影、失焦——這些不會被補成複製臉。
_NON_IDENTIFIABLE_CUES = (
    "out of focus", "blurred", "indistinct", "no facial detail",
    "without facial detail", "unrecognizable", "unrecognisable", "silhouette",
    "silhouetted", "背景虛化", "失焦", "剪影", "不辨識", "看不清臉",
    "不見臉", "看不到臉", "無臉", "看不清楚五官", "不可辨識", "個體無法分辨",
)


def audit_refs_and_subjects(seg_data: Dict[str, Any], project_root: Optional[Path] = None) -> Dict[str, Any]:
    """模式 A 審查：
    1. 檢查 reference_images 與 subject_definitions / retention_analysis 的對應關係。
    2. 驗證 <Picture 1> 為場景，<Subject k> 嚴格對應 <Picture k+1>。
    3. 檢查是否有缺圖、多餘圖、生物主角是否在前 5 名。
    4. 檢查同段是否掛載超過 1 張角色圖（混臉警告）。
    5. E19–E26：複製人防線、官方 (Sx) 綁定、旁白外部化與環境音欄位分工。
    """
    errors: List[str] = []
    warnings: List[str] = []
    passed = True

    ref_images = seg_data.get("reference_images", [])
    if not isinstance(ref_images, list):
        errors.append("[E] JSON 中 reference_images 欄位應為陣列清單")
        return {"passed": False, "errors": errors, "warnings": warnings}

    prompt_text = extract_prompt_from_seg(seg_data)

    # ---------- E19：未錨定的在場人物（複製人主因） ----------
    unanchored = [str(c) for c in (seg_data.get("unanchored_in_frame_characters") or [])]
    if unanchored:
        errors.append(
            f"[E19: 未錨定在場人物] 下列角色出現在畫面中，卻沒有自己的參考圖："
            f"{', '.join(unanchored)}。H3 只有一張臉可用時，會把這張臉複製給他們"
            f"（本專案 2026-10-19 實測 4/4 段出現複製人）。"
            f"請改掛該角色自己的單視角裁切參考圖（背面／側身）並在 stage5 綁定 "
            f"identity_anchor_ids，或把該角色移出畫面。"
        )

    # ---------- E20：多視圖板參考圖（會被複製成背景人海） ----------
    for ref in ref_images:
        if not isinstance(ref, dict) or ref.get("type") not in ("character", "creature"):
            continue
        is_panel_lookup = ref.get("reference_view") == "panel"
        panel_label = str(ref.get("panel_label_en") or "").strip()
        if is_panel_lookup:
            # 整板查表是官方 ComfyUI 允許的用法：獨立編號、逐格描述、鏡頭指向某一格。
            # 但必須真的指定格位，且該角色只能是「不露臉的身份錨點」。
            if not panel_label:
                errors.append(
                    f"[E27: 整板查表缺格位說明] {ref.get('id')} 宣告 reference_view=panel，"
                    f"但沒有 panel_label_en（要寫明用哪一格，例如「the fourth figure from the left, "
                    f"a full-body back view」）。沒有指定格位的整板會被模型整張複製進成片。"
                )
            continue
        path = str(ref.get("path") or "")
        if not path or project_root is None:
            continue
        size = _image_size(project_root, path)
        if not size:
            continue
        width, height = size
        if width >= 1600 and height >= 900 and width / max(height, 1) >= 1.5:
            errors.append(
                f"[E20: 疑似多視圖板] 角色參考圖 {path} 尺寸 {width}×{height} 像四視圖／表情板，"
                f"影片模型會把版面複製進成片（本專案 2026-10-19 實測背景長出多個同款角色）。"
                f"請改成單一視角裁切（正面頭像 950×910 或背面全身裁切），"
                f"或宣告 reference_view=panel 並用 panel_label_en 指定要用的那一格。"
            )

    # 1. 參考圖數量與主角名次檢查
    # 官方上限是分項的：圖 ≤9、影片 ≤3、音訊 ≤3、混合合計 ≤12。
    total_refs = len(ref_images)
    image_refs = [r for r in ref_images if isinstance(r, dict) and r.get("type") != "audio"]
    audio_refs = [r for r in ref_images if isinstance(r, dict) and r.get("type") == "audio"]
    if len(image_refs) > 9:
        errors.append(f"[E] 圖像參考素材數量為 {len(image_refs)} 張，超出 H3 上限 9 張！")
    if len(audio_refs) > 3:
        errors.append(f"[E] 音訊參考素材數量為 {len(audio_refs)} 個，超出 H3 上限 3 個！")
    if total_refs > 12:
        errors.append(f"[E] 混合參考素材總數為 {total_refs} 個，超出 H3 上限 12 個！")

    char_refs = [r for r in ref_images if isinstance(r, dict) and r.get("type") in ("character", "role", "actor")]
    if len(char_refs) > 1:
        face_refs = [r for r in char_refs if r.get("reference_view") != "non_face"]
        if len(face_refs) > 1:
            warnings.append(
                f"[W: 混臉風險] 同段掛載了 {len(face_refs)} 張「可辨識人臉」角色參考圖！"
                f"H3 會把多張角色圖平均成同一張臉，保守建議一段一張臉部參考圖；"
                f"背影／側身角色可另掛無臉裁切（reference_view=non_face），不會被平均。"
            )
        else:
            warnings.append(
                f"[W: 單段多張角色參考圖] 同段掛載 {len(char_refs)} 張角色參考圖，"
                f"其中只有 {len(face_refs)} 張含可辨識人臉；請確認無臉裁切不會帶入正面臉。"
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
            # 音色參考 <Audio N>：官方獨立編號，必須有對應的音訊參考素材
            all_audios_in_prompt = set(int(m) for m in re.findall(r"<Audio\s*(\d+)>", prompt_text))
            audio_ids = {r.get("audio_tag") for r in audio_refs if isinstance(r, dict) and r.get("audio_tag")}
            for a in sorted(all_audios_in_prompt):
                if f"<Audio {a}>" not in audio_ids:
                    errors.append(
                        f"[E: 缺音訊參考] Prompt 中引用了 <Audio {a}>，但 reference_images 沒有對應的 "
                        f"type=audio 參考素材；官方 ref-en §2.4 規定 <Audio N> 的編號要對得到實際掛上的音訊。"
                    )
            for r in audio_refs:
                if isinstance(r, dict) and not str(r.get("path") or "").strip():
                    errors.append(f"[E: 缺音訊檔] 音色參考 {r.get('id')} 沒有音訊路徑。")
        else:
            warnings.append("[W] 提示詞中缺少 subject_definitions 區塊，無法執行逐條序對對帳。")

        # ---------- E21：無參考圖的群眾／路人 ----------
        detail_match = re.search(r"detailed_description:(.*?)(?:\n\n[a-z_]+:|\Z)", prompt_text, re.DOTALL)
        detail_body = detail_match.group(1) if detail_match else prompt_text
        # 逐鏡判斷：同一鏡裡若出現沒有參考圖的人群，而這一鏡沒有任何
        # 「不可辨識／失焦／剪影」的寫法，就是會被補成複製臉的風險。
        # 逐鏡而非逐句：避免中英混排的同一段內容被拆成兩半而誤判。
        for block in re.split(r"(?=\[Shot \d+\])", detail_body):
            if not block.strip():
                continue
            low = block.lower()
            hits = [cue for cue in _CROWD_CUES if cue in low]
            if not hits:
                continue
            if any(nc in low for nc in _NON_IDENTIFIABLE_CUES):
                # 這一鏡已明確寫成不可辨識／失焦／剪影的人群：可接受，不會被補成複製臉
                continue
            errors.append(
                f"[E21: 無參考圖的群眾／路人] detailed_description 出現「{hits[0]}」這類沒有參考圖的人群描述。"
                f"H3 沒有第二個身分可用，會把唯一一張臉的造型套給他們，造成背景出現穿同款衣服的複製人。"
                f"處理方式：把人群移出畫面、改寫成不可辨識的失焦剪影、或改走「分鏡圖 → I2V」把人群畫進首幀。"
            )
            break

        # ---------- E22：說話人必須有官方 (Sx) 綁定 ----------
        if "<d>" in prompt_text and not re.search(r"\(S\d+\)", prompt_text):
            errors.append(
                "[E22: 缺少說話人代號] 提示詞含 <d> 台詞但沒有任何 (S1) 形式的說話人代號。"
                "官方 base 指南 §4.4 要求發聲者（含畫外音）都要有穩定 (Sx) 代號；"
                "缺了綁定，H3 會把聲音掛到畫面上唯一的那張臉上，長出複製人。"
            )

        # ---------- E22b：<Subject k> 的代號必須是 (Sk)（#66） ----------
        for _m in re.finditer(r"<Subject (\d+)> \(S(\d+)\)", prompt_text):
            if _m.group(1) != _m.group(2):
                errors.append(
                    f"[E22: 說話者代號不一致] <Subject {_m.group(1)}> 被標成 (S{_m.group(2)})；"
                    f"Subject k 的代號必須是 (Sk)，否則聲音會掛錯人。")
                break

        # ---------- E23：畫外音必須用官方句式並說明嘴閉合 ----------
        if re.search(r"off-screen voiceover|off-screen voice over", prompt_text.lower()):
            if "lips remain completely closed" not in prompt_text.lower():
                errors.append(
                    "[E23: 畫外音缺嘴閉合聲明] 提示詞寫了 off-screen voiceover，"
                    "但沒有在 <d> 之後說明嘴唇保持閉合。官方要求："
                    "Immediately after every voiceover <d> block, state that the on-screen character's lips remain closed."
                )

        # ---------- E24：旁白政策（external 時不得有畫外音 <d>） ----------
        narration_policy = str((seg_data.get("metadata") or {}).get("narration_policy") or "external")
        external_narration = seg_data.get("external_narration") or []
        if narration_policy == "external" and external_narration:
            for entry in external_narration:
                line = str(entry.get("line") or "").strip()
                if line and f"<d>[{entry.get('language') or 'Chinese'}] {line}</d>" in prompt_text:
                    errors.append(
                        f"[E24: 旁白政策衝突] narration_policy=external，但畫外音台詞仍以 <d> 出現在提示詞中：{line!r}。"
                        f"請改由外部 TTS 合成後於階段 7 混入，H3 這段只出環境音。"
                    )

        # ---------- E25：overall_soundscape 不得重複台詞 ----------
        sound_match = re.search(r"overall_soundscape:(.*?)(?:\n\n[a-z_]+:|\Z)", prompt_text, re.DOTALL)
        sound_body = (sound_match.group(1) if sound_match else "").strip()
        if sound_body:
            for line in re.findall(r"<d>\[[^\]]*\]\s*(.*?)\s*</d>", prompt_text):
                if line and len(line) >= 4 and line in sound_body:
                    errors.append(
                        f"[E25: 環境音重複台詞] overall_soundscape 內重複了台詞 {line!r}。"
                        f"官方 §4.6：對白只寫在 detailed_description 的 <d> 區塊，"
                        f"環境音欄只留環境與動作音，否則 H3 會在環境音軌再念一次。"
                    )
                    break

    # ---------- E26：身份錨點必須真的掛上自己的參考圖 ----------
    for ref in ref_images:
        if not isinstance(ref, dict):
            continue
        if ref.get("reference_view") == "non_face" and not str(ref.get("path") or "").strip():
            errors.append(
                f"[E26: 身份錨點缺參考圖] {ref.get('id')} 標記為無臉身份錨點，卻沒有自己的參考圖路徑。"
            )

    # ---------- E28：14 號風格（古風寫實厚塗・電影感）每段要有參考圖、不得含平塗模板句 ----------
    style_value = (seg_data.get("metadata") or {}).get("style_key") or (
        style_rules.project_style(project_root) if project_root else "")
    if style_rules.is_style14(style_value):
        errors.extend(style_rules.segment_errors(seg_data, prompt_text))

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
# 模式 B：H3 分段提示詞 17 條確定性自檢 (--lint-h3)
# ==============================================================================

def lint_h3_prompt(
    prompt_text: str,
    nominal_duration: float = 7.0,
    rounding_mode: str = "floor",
    authored_shots: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """對 H3 分段提示詞執行 17 條確定性工程自檢。
    支援 5–10 秒短分段與 15 秒段，動態計算 FreeVideo 取整有效秒數 D。
    """
    errors: List[str] = []
    warnings: List[str] = []

    clean_prompt = prompt_text.strip()
    if not clean_prompt:
        errors.append("[E: 空文本] 提示詞內容為空！")
        return {"passed": False, "errors": errors, "warnings": warnings, "details": {}}

    # This adapter provides H3's six-section prose, not an independent negative
    # prompt channel. A copied exclusion block must be rewritten before sending.
    if re.search(r"\bnegative(?:[_\s]+prompt|\s+constraints)\s*:", clean_prompt, re.IGNORECASE):
        errors.append("[E18: unsupported negative prompt block] 將負面清單改寫為正向可見狀態；不得把 negative constraints / negative_prompt 區塊送入 H3 正文。")

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
    authored_exception = False
    authored_reason = ""
    authored_timeline_end: Optional[float] = None
    if authored_shots is not None:
        if not isinstance(authored_shots, list) or not 1 <= len(authored_shots) <= 8:
            authored_reason = "authored shot context must contain 1–8 shot objects"
        elif len(authored_shots) != n_shots:
            authored_reason = f"prompt has {n_shots} shots but authored context has {len(authored_shots)}"
        else:
            cursor = 0.0
            try:
                for index, shot in enumerate(authored_shots, start=1):
                    if not isinstance(shot, dict):
                        raise ValueError(f"shot {index} is not an object")
                    start, end, duration = (float(shot[key]) for key in ("start_time", "end_time", "duration"))
                    if not all(math.isfinite(value) for value in (start, end, duration)):
                        raise ValueError(f"shot {index} has non-finite timing")
                    if abs(start - cursor) > 1e-3:
                        raise ValueError(f"shot {index} is not continuous (expected {cursor:.3f}s, got {start:.3f}s)")
                    if end <= start or abs((end - start) - duration) > 1e-3:
                        raise ValueError(f"shot {index} has inconsistent start/end/duration")
                    cursor = end
                authored_timeline_end = cursor
                if abs(cursor - nominal_duration) > 1e-3 and abs(cursor - eff_d) > 1e-3:
                    raise ValueError(
                        f"authored timeline ends at {cursor:.3f}s, expected nominal {nominal_duration:.3f}s "
                        f"or quantized {eff_d:.3f}s"
                    )
                declared = re.search(
                    r"([0-9]+(?:\.[0-9]+)?)s\s+effective\s+from\s+([0-9]+(?:\.[0-9]+)?)s\s+target",
                    clean_prompt,
                    re.IGNORECASE,
                )
                if not declared:
                    raise ValueError("prompt summary does not state effective and target durations")
                declared_effective, declared_target = map(float, declared.groups())
                if abs(declared_target - nominal_duration) > 1e-3 or abs(declared_effective - eff_d) > 1e-3:
                    raise ValueError(
                        f"prompt summary duration {declared_target:.3f}s target/{declared_effective:.3f}s effective "
                        f"does not match expected {nominal_duration:.3f}s/{eff_d:.3f}s"
                    )
                prompt_cuts: List[float] = []
                for header in shot_headers[1:]:
                    if not header[1] or not header[2]:
                        raise ValueError("prompt is missing a timestamp for an authored cut")
                    prompt_cuts.append(float(header[1]) * 60.0 + float(header[2]))
                authored_cuts = [float(shot["end_time"]) for shot in authored_shots[:-1]]
                if len(prompt_cuts) != len(authored_cuts) or any(
                    abs(prompt_time - authored_time) > 1e-3
                    for prompt_time, authored_time in zip(prompt_cuts, authored_cuts)
                ):
                    raise ValueError("prompt cut timestamps do not match authored shot end times")
                authored_exception = True
            except (KeyError, TypeError, ValueError) as exc:
                authored_reason = str(exc)

    details["authored_shot_count_exception"] = authored_exception
    if authored_timeline_end is not None:
        details["authored_timeline_end_sec"] = round(authored_timeline_end, 3)
    if authored_shots is not None and not authored_exception:
        warnings.append(f"[W:E2 authored shots ignored] {authored_reason}; legacy shot-count limits remain in force.")

    if n_shots == 0:
        errors.append("[E2: 缺少鏡頭標籤] 未找到任何 [Shot N] 格式的鏡頭宣告！")
    else:
        # 檢查編號連續性 (1, 2, ..., N)
        shot_indices = [int(h[0]) for h in shot_headers]
        expected_indices = list(range(1, n_shots + 1))
        if shot_indices != expected_indices:
            errors.append(f"[E2: 鏡頭序號不連續] 實際序號為 {shot_indices}，期望為 {expected_indices}")

        # Preserve a complete authored timeline only when its shot count and
        # nominal/quantized duration can be verified against the compiled prompt.
        if authored_exception:
            warnings.append(
                f"[W:E2 authored shot count] Preserving {n_shots} authored shots; "
                f"continuous timeline ends at {authored_timeline_end:.3f}s and prompt effective duration is {eff_d:.3f}s."
            )
        elif eff_d < 10.0:
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
    # 規則 14 (E): 同鏡重複運鏡詞句與罐頭模板句攔截 (抓出子代理每句前後重複貼 static shot)
    # --------------------------------------------------------------------------
    canned_patterns = [
        r"then the motion transitions smoothly",
        r"executes deliberate physical blocking with natural body movement",
        r"executing choreographed actions with emotional continuity",
    ]
    for idx, block in enumerate(shot_blocks, start=1):
        b_lower = block.lower()
        # 檢查同鏡內是否有重複出現的 "as the camera" 或 "the camera"
        cam_mentions = len(re.findall(r"\b(?:as\s+)?the\s+camera\s+[a-z\s]+?(?:to\s+frame|holds|\.)", b_lower))
        if cam_mentions > 1 or b_lower.count("as the camera") > 1 or b_lower.count("holds a static shot") > 1:
            errors.append(
                f"[E14: 同鏡重複運鏡句違規] [Shot {idx}] 出現多次重複運鏡句或模板拼接（如重複貼上 'as the camera holds a static shot'）！"
                f"單鏡必須只有一次連貫的運鏡動機與鏡頭運動。"
            )
        for cp in canned_patterns:
            if re.search(cp, b_lower):
                errors.append(
                    f"[E14: 罐頭模板違規] [Shot {idx}] 含有未具象化的機械式模板句 '{cp}'！"
                    f"必須依實際劇情與物理力學描繪具體動作。"
                )

    # --------------------------------------------------------------------------
    # 規則 15 (E): 未翻譯中文混雜攔截 (防 compile_layer2_to_h3 丟失中文動作直接硬拼)
    # --------------------------------------------------------------------------
    # 舊版只在含 "the target video is" 時才檢查，但編譯器的開頭是 "The target video follows"，
    # 等於永遠不觸發；英文提示詞一律檢查（<d> 台詞除外）。
    if detailed_desc.strip():
        # 移除 <d>...</d> 中的中文台詞後，檢查是否仍有未翻譯的中文動作句
        non_dlg_desc = re.sub(r"<d>.*?</d>", "", detailed_desc, flags=re.DOTALL)
        raw_chinese_chars = re.findall(r"[\u4e00-\u9fff]", non_dlg_desc)
        if len(raw_chinese_chars) > 6:
            errors.append(
                f"[E15: 動作描述未完整翻譯] detailed_description 含有 {len(raw_chinese_chars)} 個未編譯為英文的中文動作文字！"
                f"英文提示詞模式下，除 `<d>` 台詞外所有動作力學三要素必須完整英譯。"
            )

    # --------------------------------------------------------------------------
    # 規則 16 (E): 戰鬥衝擊鏡頭缺少物理反饋
    # --------------------------------------------------------------------------
    combat_patterns = (
        r"\bwhips?\b", r"\bstrikes?\b", r"\bswings?\b", r"\bsmashes?\b",
        r"\bpunch(?:es)?\b", r"\bslashes?\b", r"\bcrashes?\b", r"\btumbles?\b",
        r"\bcollides?\b", r"\bshatters?\b",
    )
    impact_feedback_cues = (
        r"\bsparks?\b", r"\bdebris\b", r"\brecoils?(?:ed|ing)?\b",
        r"\bflinches?(?:ed|ing)?\b", r"\bdust\b", r"\bsmoke\b",
        r"\bshatters?(?:ed|ing)?\b", r"\bknocked back\b",
        r"\btumbles?(?:ed|ing)?\b", r"\bshockwave\b", r"\bblasts?\b",
        r"\b(?:wrist|arm|hand|head|body)\s+jerks?\s+back\b",
        r"\bhead\s+thrusts?\s+back\b",
        r"\bdrives?\b.{0,100}\binto\s+(?:the\s+)?(?:.{0,40}\s+)?(?:wall|ground|floor)\b",
        r"\bdrops?\s+to\s+(?:the\s+)?(?:ground|floor)\b",
    )
    executed_combat_desc = detailed_desc
    non_executed_combat_patterns = (
        r"\bchecks?\s+(?:his|her|their|the)\s+swing\b",
        r"\b(?:finds?|has|sees?)\s+no\s+safe\s+path\s+to\s+strike\b",
        r"\bno\s+safe\s+path\s+to\s+strike\b",
        r"\b(?:does\s+not|doesn't|never)\s+(?:swing|strike|hit|smash|punch|slash|whip)\b",
        r"\bwithout\s+(?:swinging|striking|hitting|smashing|punching|slashing|whipping)\b",
        r"\bavoids?\s+(?:swinging|striking|hitting|smashing|punching|slashing|whipping)\b",
    )
    for pattern in non_executed_combat_patterns:
        executed_combat_desc = re.sub(pattern, "", executed_combat_desc, flags=re.IGNORECASE)
    if any(re.search(pattern, executed_combat_desc, re.IGNORECASE) for pattern in combat_patterns):
        has_impact_feedback = any(re.search(cue, detailed_desc, re.IGNORECASE) for cue in impact_feedback_cues)
        if not has_impact_feedback:
            errors.append(
                "[E16: 戰鬥衝擊缺少物理反饋] 檢測到戰鬥打擊動作，但未描述任何受擊反饋（如 sparks, dust, recoil, tumbles, shockwave 等）！"
                "缺乏環境物理反饋必然導致武器/道具懸空吸附在怪獸身上。"
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
    # #70：標註句（On screen: …）另計，不占描述密度
    _counted = re.sub(r" On screen: [^\n]*?\.(?= |$|\n)", "", detailed_desc)
    words = re.findall(r"\b[A-Za-z0-9_-]+\b", _counted)
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
    parser.add_argument("--lint-h3", metavar="FILE_OR_DIR", help="對指定分段 JSON 或提示詞文本執行 17 條 H3 確定性自檢")
    parser.add_argument("--duration", type=float, default=7.0, help="分段目標名義秒數（預設: 7.0s）")
    parser.add_argument("--rounding", choices=["floor", "round", "ceil"], default="floor", help="17n+5 取整模式；JSON分段優先採 metadata.rounding_mode")

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
        if p.suffix.lower() == ".md":
            try:
                content = p.read_text(encoding="utf-8")
                sections = re.split(r"(?=^#{2,3}\s+)", content, flags=re.MULTILINE)
                items_to_check = []
                for sec in sections:
                    sec = sec.strip()
                    if not sec or not re.match(r"^#{2,3}\s+", sec):
                        continue
                    m_title = re.search(r"^#{2,3}\s+(?:Segment\s+\d+:\s*`?)?([A-Za-z0-9_-]+)", sec)
                    seg_id = m_title.group(1) if m_title else "segment"
                    m_dur = re.search(r"(?:時長|Duration|目標|真實有效)[：:\s`]*([0-9.]+)\s*s?", sec, re.IGNORECASE)
                    dur = float(m_dur.group(1)) if m_dur else args.duration
                    m_code = re.findall(r"```(?:text|prompt)?\s*\n(.*?)\n```", sec, re.DOTALL)
                    prompt_cand = ""
                    for cb in m_code:
                        if "subject_definitions:" in cb or "detailed_description:" in cb:
                            prompt_cand = cb.strip()
                            break
                    if not prompt_cand:
                        m_sub = re.search(r"(subject_definitions:.*?)(?=(?:\n##|\Z))", sec, re.DOTALL)
                        if m_sub:
                            prompt_cand = m_sub.group(1).strip()
                    if prompt_cand:
                        items_to_check.append({
                            "segment_id": seg_id,
                            "metadata": {"target_duration_sec": dur},
                            "h3_prompt": prompt_cand
                        })
                if not items_to_check and ("subject_definitions:" in content or "detailed_description:" in content):
                    items_to_check = [{
                        "segment_id": p.stem,
                        "metadata": {"target_duration_sec": args.duration},
                        "h3_prompt": content.strip()
                    }]
            except Exception as exc:
                print(f"  ❌ Markdown 讀取失敗: {exc}")
                total_errors += 1
                continue
        else:
            try:
                with p.open("r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception as exc:
                print(f"  ❌ JSON 讀取失敗: {exc}")
                total_errors += 1
                continue

            items_to_check = []
            if isinstance(data, list):
                items_to_check = data
            elif isinstance(data, dict) and "segments" in data and isinstance(data["segments"], list):
                items_to_check = data["segments"]
            elif isinstance(data, dict):
                items_to_check = [data]
            else:
                print(f"  ❌ 資料格式應為物件或陣列: {type(data)}")
                total_errors += 1
                continue

        for seg_idx, seg_data in enumerate(items_to_check, start=1):
            seg_id_label = seg_data.get("segment_id", f"item_{seg_idx}")
            if len(items_to_check) > 1:
                print(f"  --- [分段 {seg_id_label}] ---")

            # 模式 A: 審查與修復參考圖
            if args.audit_refs:
                if args.fix_refs:
                    seg_data = fix_refs_and_subjects(seg_data)
                    with p.open("w", encoding="utf-8") as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                        f.write("\n")
                    print(f"  🔧 已自動覆寫修復 reference_images 與 subject_definitions！")

                refs_res = audit_refs_and_subjects(seg_data, project_root=p.parent)
                if refs_res["passed"]:
                    print(f"  [PASS] 參考圖與主體定義序對稽核通過 ({seg_id_label})")
                else:
                    for e in refs_res["errors"]:
                        print(f"  ❌ {e}")
                    total_errors += len(refs_res["errors"])
                for w in refs_res["warnings"]:
                    print(f"  ⚠️ {w}")
                total_warnings += len(refs_res["warnings"])

            # 模式 B: H3 提示詞 17 條自檢
            if args.lint_h3:
                prompt_str = extract_prompt_from_seg(seg_data)
                dur = float(seg_data.get("metadata", {}).get("target_duration_sec", args.duration))
                rounding_mode = (seg_data.get("metadata", {}) or {}).get("rounding_mode", args.rounding)
                lint_res = lint_h3_prompt(prompt_str, nominal_duration=dur, rounding_mode=rounding_mode, authored_shots=seg_data.get("shots"))
                if lint_res["passed"]:
                    print(f"  [PASS] H3 提示詞 17 條自檢通過 ({seg_id_label}: 名義 {dur}s -> 真實有效 {lint_res['details']['effective_duration_sec']}s)")
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
