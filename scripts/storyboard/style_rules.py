#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""14 號風格「古風寫實厚塗・電影感」（key: xianxia-cinematic-semireal）的固定配方與檢查。

來源：《我修的是遺忘課》10 集 115 段實戰（設定圖當時用 Codex 內建生圖；引擎現由 decisions.json design_engine 決定、影片 H3 Ref2VA）。
翻車教訓：沒有角色參考圖的段（純物件／空景）會漂成平塗 cel 卡通——
EP04-S02-a、EP09-S02-a、EP05-S02-a、EP09-S01-c 都發生過；原因是畫面只剩文字風格句可依，
而當時模板句「Hand-painted 2D… soft cel-like shading… non-photorealistic」本身就在叫 H3 畫平塗。
所以這個風格下：
  * 每段至少綁一張設定圖或場景圖（<Picture N>），沒有就報錯（audit E28）；
  * 風格錨一律用下面的影片錨，並刪掉任何「hand-painted 2D／cel-like／non-photorealistic」句子。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

STYLE14_INDEX = "14"
STYLE14_KEY = "xianxia-cinematic-semireal"
STYLE14_NAME = "古風寫實厚塗・電影感"
DEFAULT_STYLE_KEY = STYLE14_KEY

# 設定圖（四視圖母版；引擎依 design_engine，codex 或 grok）的風格句
SHEET_STYLE_LINE = (
    "painterly xianxia illustration, thick painterly brush strokes on hair, skin and fabric, "
    "NOT 3D render/CGI/photograph, no glossy plastic skin; "
    "realistic East Asian bone structure and eye proportions, NOT Pixar/Disney cartoon face, no oversized eyes"
)
SHEET_NEGATIVE = "photorealism, Unreal Engine look, 3D render, CGI, plastic skin, Pixar/Disney cartoon face, oversized eyes"
# 影片（H3 Ref2VA）風格錨與負面錨
VIDEO_ANCHOR = ("semi-realistic cinematic painting exactly like <Picture 1>, realistic proportions, "
                "never cel-shaded anime, no outlines, muted jade and vermilion palette")
VIDEO_NEGATIVE = ("3D render, CGI, plastic skin, overexposed glow, cluttered pattern, distorted face, text, "
                  "cel shading, outlines")
PALETTE_PRESET = "grey-brown hemp, cold stone grey, jade teal, a touch of cinnabar"
LIGHTING_HINT = "one motivated light source, about 6000K cold grey daylight or warm oil-lamp glow, low contrast"

# 會把 H3 推向平塗 cel 的模板句（出現就刪；出現在已編譯 prompt 裡就報錯）
FORBIDDEN_PATTERNS = (
    r"hand-painted\s+2d",
    r"cel-like",
    r"soft\s+cel",
    r"non-photorealistic",
)
_FORBIDDEN_RE = re.compile("|".join(FORBIDDEN_PATTERNS), re.IGNORECASE)


def normalize(value: Any) -> str:
    return str(value or "").strip().lower().lstrip("#").replace("號", "").replace("号", "")


def is_style14(value: Any) -> bool:
    text = normalize(value)
    if not text or text.startswith("<"):  # 範本佔位字（<角色設定板風格…>）不算定案
        return False
    return (text in (STYLE14_INDEX, STYLE14_KEY) or text.startswith(STYLE14_KEY)
            or str(value).strip().startswith(STYLE14_NAME) or re.match(r"^14(\D|$)", text) is not None)


def project_style(root: Optional[Path]) -> str:
    """專案定案的畫風：先看 decisions.json 的 style，再看 assets.md 的 style_index；都沒有回空字串。"""
    if not root:
        return ""
    root = Path(root)
    path = root / "decisions.json"
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            for item in data.get("decisions", []):
                if item.get("id") == "style":
                    value = item.get("value")
                    if isinstance(value, dict):
                        value = value.get("key") or value.get("index") or json.dumps(value, ensure_ascii=False)
                    return str(value)
        except (OSError, json.JSONDecodeError, AttributeError):
            pass
    assets = root / "assets.md"
    if assets.is_file():
        m = re.search(r"^-\s*\*\*style_index\*\*[：:]\s*`?([\w-]+)`?", assets.read_text(encoding="utf-8"), re.MULTILINE)
        if m:
            return m.group(1)
    return ""


def strip_forbidden(text: str) -> str:
    """刪掉含平塗 cel 模板詞的句子／片段（以句號、分號、逗號切）。"""
    if not text:
        return text
    sentences = re.split(r"(?<=[.;。；])\s+", text)
    kept = []
    for sentence in sentences:
        if not _FORBIDDEN_RE.search(sentence):
            kept.append(sentence)
            continue
        parts = [p for p in re.split(r",\s*", sentence) if not _FORBIDDEN_RE.search(p)]
        if parts:
            kept.append(", ".join(parts))
    return " ".join(k.strip() for k in kept if k.strip())


def video_anchor(current: str = "") -> str:
    """14 號風格的影片錨：固定錨＋（清掉禁用句後）專案自己的補充。"""
    extra = strip_forbidden(current or "")
    if not extra or extra.strip().lower() in VIDEO_ANCHOR.lower():
        return VIDEO_ANCHOR
    if VIDEO_ANCHOR.lower() in extra.lower():
        return extra
    return f"{VIDEO_ANCHOR}; {extra}"


def forbidden_hits(text: str) -> List[str]:
    return sorted({m.group(0) for m in _FORBIDDEN_RE.finditer(text or "")})


def segment_errors(seg: Dict[str, Any], prompt_text: str = "", backend: str = "ref2va") -> List[str]:
    """style=14 下的段落檢查（audit E28）。

    backend=remix（PR-R3）：參考看 refmods（角色包），提示詞引用 <Picture N> 或 <Video N> 都算。
    """
    errors: List[str] = []
    if backend == "remix":
        refs = [r for r in seg.get("refmods") or [] if isinstance(r, dict) and str(r.get("pack") or "").strip()]
        has_picture = bool(refs) and (("<Picture" in prompt_text or "<Video" in prompt_text) if prompt_text else True)
    else:
        refs = [r for r in seg.get("reference_images") or []
                if (isinstance(r, dict) and str(r.get("path") or "").strip()) or (isinstance(r, str) and r.strip())]
        has_picture = bool(refs) and ("<Picture" in prompt_text if prompt_text else True)
    if not has_picture:
        errors.append(
            "[E28: 14 號風格段落沒有參考圖] 「古風寫實厚塗・電影感」下每段至少要綁一張設定圖或場景圖（<Picture N>）；"
            "沒有參考圖的純物件／空景段會漂成平塗 cel（EP04-S02-a、EP09-S02-a、EP05-S02-a、EP09-S01-c 實例）。"
            "請在 stage5 綁定場景母版或角色設定圖。")
    hits = forbidden_hits(prompt_text)
    if hits:
        errors.append(
            f"[E28: 14 號風格出現平塗模板句] 提示詞含 {', '.join(hits)}；這類句子會把 H3 推向平塗 cel，"
            f"風格錨請改用：{VIDEO_ANCHOR}")
    return errors
