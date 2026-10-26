#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
export_asset_prompts.py — 核心資產提示詞自動組裝器與生圖引擎門禁工具
(Core Asset Prompt Exporter & Generator Engine Gate v1.0)

功能：
1. 自動讀取專案之 bible.json 或 assets.md，提取角色、生物、場景等資產設定。
2. 自動組裝符合標準規格之生圖 Prompt：
   - 角色（Character）：純中性淺灰底四格轉面圖（左起微距面部特寫、正視全身、側視全身、背視全身）。
   - 生物（Creature）：純中性灰底三視圖（正視、側視、頭部特寫）。
   - 場景（Scene）：無前景人物空景底圖（16:9，真實體積光，景深透視）。
   - 畫風鎖（Style Lock）：嚴格沿用 3D 國漫（STYLE-3d-donghua）或自訂風格錨。
3. 核心資產生圖引擎確認門禁（跨章節畫風一致性保護）：
   - 引擎讀自專案定案 `decisions.json` 的 `design_engine`（`h3d decide design_engine ...`），
     其次 `adapt/bible.json` 的 `design_engine`，可用 `--engine` 覆寫；都沒有時沿用 codex（舊行為）。
   - 一經定案全集鎖定：同一專案內不得中途換引擎；換引擎必須重生全部核心資產並重新審核。
4. 支援匯出為 JSON、Markdown；引擎為 grok 時另輸出「生圖清單」（manifest JSON＋md），
   每張圖列出 id、目標輸出路徑、prompt、比例與要附的參考圖，交由 Grok 內建 GenerateImage 逐張生成。

零外部依賴，純 Python 標準庫。全程繁體中文輸出。
"""

from __future__ import annotations

import argparse
import io
import json
import os
import pathlib
import re
import sys
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import style_rules  # noqa: E402

# 確保 Windows 終端輸出 UTF-8
if sys.platform.startswith("win"):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")


# ==============================================================================
# 門禁常數與預設風格錨
# ==============================================================================

ENGINE_CONSISTENCY_GATE = """
================================================================================
🚨【核心資產圖生圖引擎確認門禁（跨章節畫風一致性鐵律）】
1. 核心彩色資產設定圖（角色設定板、場景空景底圖、怪物三視圖）決定全片基本視覺風格。
2. 跨章節製作時，必須嚴格沿用專案定案的設定圖引擎（decisions.json 的 design_engine，
   如 codex 或 grok）；嚴禁本章私自改用其他圖片模型生成彩色核心資產！
3. 圖片模型之間的筆觸、材質與膚色渲染（SSS）存在顯著割裂，一旦混用將導致片中角色換臉與風格跳變！
4. 畫風語義漂移防禦（Anti-Pixar 鐵律）：
   - 角色 Prompt 必須嚴格指定「東亞五官骨相與比例（realistic East Asian facial proportions）」；
   - 嚴格負向/排他詞：STRICTLY NO Pixar style, NO Disney cartoon style, NO Western cartoon proportions, NO exaggerated oversized eyes, NO freckles；
   - 嚴格禁止使用「wide bright eyes + wide grin」等會誘導歐美卡通大眼雀斑笑臉的詞彙組合。
5. 生圖後必須以 view_file 進行親眼視覺驗收，禁止僅憑檔案大小與解析度交件！
6. Qwen-Image 僅限用於階段 4 的黑白鉛筆分鏡草圖分鏡總覽圖構圖審核。
================================================================================
"""

DEFAULT_STYLE_LOCK_3D = (
    "Photorealistic-stylized East Asian 3D CG cinematic render, Unreal Engine 5 aesthetic, "
    "realistic East Asian facial bone structure and eye proportions, delicate subsurface-scattering skin texture, "
    "cinematic volumetric lighting, shallow depth of field, detailed hair and fabric, 16:9; "
    "STRICTLY NO Pixar style, NO Disney cartoon style, NO exaggerated oversized cartoon eyes, NO freckles"
)

# 角色設定板以 ai-image-prompt「3D 漫劇寫實厚涂四視圖母版」為準（段 1 構圖一字不改）。
# 風格選擇：預設 14 號「古風寫實厚塗・電影感」（xianxia-cinematic-semireal）；`--style master` 用母版 3D 厚塗；
# `--style N` 改用 references/styles.md 第 N 套錨（取代母版渲染與膚質句）。
DEFAULT_STYLE_KEY = style_rules.DEFAULT_STYLE_KEY
STYLES_MD = pathlib.Path(__file__).resolve().parents[2] / "references" / "styles.md"

MASTER_COMPOSITION = (
    "16:9横版人物设定图，画面左侧为超大人物脸部胸像正面特写，占据画面约40%，"
    "画面右侧水平并排3张完整全身立绘，依次为正面全身、45°侧面全身、背面全身。"
    "三张全身立绘身高比例一致，头顶及脚底统一对齐，完整展示人物服装、身材与鞋履，统一浅灰色摄影棚背景。"
)
# 母版「最容易崩的五處」與四視圖專屬坑的防呆句
MASTER_GUARDS = (
    "胸像只画头到肩，右缘与右侧三格之间留一条窄缝、互不重叠。"
    "正面全身脸朝镜头；侧面全身脸朝画面右侧约45°，鼻尖越过脸颊轮廓线、能看到一侧耳朵；背面全身完全背对镜头。"
    "中性站姿，双臂自然下垂、略微离开身体，三个全身视图站姿相同。"
    "四格共用同一个浅灰色纯色背景，没有环境、没有道具、没有投影；均匀平光，四格照度一致。"
    "所有视图在同一焦平面，全部清晰，没有景深虚化。"
)
MASTER_STYLE_3D = (
    "高级3D漫剧写实厚涂，电影级CG渲染。冷白皮瓷白水光肌，皮肤细腻通透、有真实次表面散射与自然高光，"
    "精致立体的东方五官；不要皮克斯／迪士尼卡通风、不要夸张大眼、不要雀斑。"
)
MASTER_BACK_RULE = "背面视图至少清楚呈现三项可辨识特征（后领、露背范围或后背剪裁、发型背影、腰带结构、裙摆走向）。"
MASTER_QUALITY_3D = "8K超高清，电影级3D漫剧写实厚涂渲染，皮肤细腻通透，具有真实次表面散射与自然高光。"
MASTER_QUALITY_TAIL = "所有人物视图清晰锐利，服饰细节一致，完整全身构图，无文字，无水印。四格画的都是同一个角色，画面里没有其他人物。"


def load_style_anchor(index: int, styles_md: pathlib.Path = STYLES_MD) -> Dict[str, str]:
    """從 styles.md 讀第 index 套風格的鎖定錨與負面錨。"""
    text = styles_md.read_text(encoding="utf-8")
    m = re.search(rf"^## {index}\.\s*(.+?)\n(.*?)(?=^## \d+\.|\Z)", text, re.DOTALL | re.MULTILINE)
    if not m:
        raise ValueError(f"styles.md 找不到第 {index} 套風格")
    anchor = re.search(r"\*\*風格鎖定錨\*\*：`([^`]+)`", m.group(2))
    negative = re.search(r"\*\*負面錨\*\*：`([^`]+)`", m.group(2))
    if not anchor:
        raise ValueError(f"styles.md 第 {index} 套缺少風格鎖定錨")
    return {"name": m.group(1).strip(), "anchor": anchor.group(1), "negative": negative.group(1) if negative else ""}


STYLE_PRESETS = {
    style_rules.STYLE14_KEY: {
        "name": f"14 號 {style_rules.STYLE14_NAME}（預設）",
        "line": (
            f"{style_rules.SHEET_STYLE_LINE}。真人骨相＋厚涂质地的半写实，冷灰低对比平光。"
        ),
        "quality": f"所有视图都是手绘厚涂质地的半写实插画。避免：{style_rules.SHEET_NEGATIVE}。",
    },
    "master": {
        "name": "3D 漫劇寫實厚塗（母版預設）",
        "line": MASTER_STYLE_3D,
        "quality": MASTER_QUALITY_3D,
    },
    "semi-real": {
        "name": "UE5 半寫實東亞 CG",
        "line": (
            "Stylized East Asian 3D CG character concept sheet, a Unreal Engine 5 real-time 3D render, "
            "NOT a photograph, NOT a real-person photo shoot (Korean-Chinese next-gen CG cinema aesthetic, "
            "realistic East Asian facial bone structure and eye proportions, delicate subsurface-scattering skin "
            "with visible CG material feel; STRICTLY NO Pixar style, NO Disney cartoon style, NO Western "
            "cartoon proportions, NO exaggerated oversized eyes, NO freckles, NO photographic portrait look)。"
            "一般人／配角要依角色描述畫出真實年齡、胖瘦與不完美的臉，不要一律畫成偶像臉。"
        ),
        "quality": "8K超高清，电影级半写实3D CG渲染（UE5即时渲染质感，不是照片），皮肤细腻带次表面散射。",
        "needs_reference": "assets/styles/sheet-13-semi-real-ue5.jpg",
    },
}
STYLE_CHOICES = (f"{style_rules.STYLE14_KEY} 或 14（古風寫實厚塗・電影感，預設）／master（母版3D厚塗）／"
                 "semi-real（UE5半寫實）／1–11（styles.md 編號）")
NUMBERED_STYLE_NOTE = "背景以上述四格共用的浅灰纯色背景为准，忽略风格词里的场景背景、粒子与氛围元素。"


def resolve_style(token: Optional[str]) -> Dict[str, str]:
    """把風格選擇（master／semi-real／styles.md 編號）解析成 {name, line, quality}。"""
    key = (str(token).strip().lower() if token else "") or style_rules.DEFAULT_STYLE_KEY
    if style_rules.is_style14(key):
        key = style_rules.STYLE14_KEY
    if key in STYLE_PRESETS:
        return {**STYLE_PRESETS[key], "key": key}
    if key.isdigit():
        a = load_style_anchor(int(key))
        neg = f" 避免：{a['negative']}。" if a["negative"] else ""
        return {"key": key, "name": a["name"], "line": f"{a['anchor']}。{NUMBERED_STYLE_NOTE}",
                "quality": neg.strip()}
    raise ValueError(f"未知風格 {token!r}；可選：{STYLE_CHOICES}")


def build_character_prompt(subject_desc: str, style: Optional[Dict[str, str]] = None, project_lock: str = "") -> str:
    """母版五段式角色設定板提示詞：構圖與防呆不變，風格句與畫質句依所選風格替換。"""
    style = style or resolve_style(None)
    quality = (style["quality"] + MASTER_QUALITY_TAIL) if style["quality"] else MASTER_QUALITY_TAIL
    if style.get("key") == "master" and project_lock and project_lock != DEFAULT_STYLE_LOCK_3D:
        quality += f" 专案风格锁：{project_lock}"
    back_rule = "" if "背面特徵" in subject_desc else f"背面：{MASTER_BACK_RULE}\n"
    return (
        f"构图：{MASTER_COMPOSITION}{MASTER_GUARDS}\n"
        f"风格：{style['line']}\n"
        f"角色：{subject_desc}\n"
        f"{back_rule}"
        f"画质：{quality}"
    )

def env_style_line(style: Optional[Dict[str, str]] = None) -> str:
    """生物／場景／道具共用的風格句：跟角色同一個 --style，避免風格不一致。"""
    style = style or resolve_style(None)
    line = style.get("line", "")
    if style.get("key") == "master" or style.get("key") == "semi-real":
        return "Stylized 3D CG render, not a photograph, " + (
            "Unreal Engine 5 real-time render" if style.get("key") == "semi-real" else "cinematic 3D CG")
    return line.rstrip("。")


CREATURE_TURNAROUND_TEMPLATE = (
    "{style_line}, creature concept sheet, cinematic creature design, "
    "realistic textures and volume, neutral studio lighting, 16:9 aspect ratio. "
    "Creature turnaround model sheet against a seamless flat neutral medium-grey background showing "
    "front view, side profile view, and head close-up. "
    "Subject: {subject_desc}"
)

SCENE_PLATE_TEMPLATE = (
    "{style_line}, environment plate, realistic architectural and environmental rendering, "
    "cinematic volumetric lighting, deep perspective view, 16:9 aspect ratio. "
    "{subject_desc}, completely empty of people, cinematic establishing plate."
)


# ==============================================================================
# 解析模組 (從 assets.md 或 bible.json 讀取)
# ==============================================================================

def parse_assets_markdown(assets_path: pathlib.Path) -> List[Dict[str, Any]]:
    """解析 assets.md 提取資產區塊與固定描述片段。"""
    if not assets_path.exists():
        return []

    text = assets_path.read_text(encoding="utf-8", errors="ignore")
    assets: List[Dict[str, Any]] = []

    # 提取 style_lock
    style_lock = DEFAULT_STYLE_LOCK_3D
    m_style = re.search(r"##\s*一、畫風鎖.*?\n```text\s*\n(.*?)\n```", text, re.DOTALL)
    if m_style:
        style_lock = m_style.group(1).strip()

    # 正則匹配標題與固定描述片段
    # 格式如：### C-ye-weishan 葉瑋珊 或 ### 葉瑋珊
    section_pattern = re.compile(
        r"###\s+([^\n]+)\n(.*?)(?=\n###|\n##|\Z)", re.DOTALL
    )
    for m in section_pattern.finditer(text):
        title_line = m.group(1).strip()
        body = m.group(2)

        # 提取英文固定描述片段
        prompt_block_m = re.search(r"```text\s*\n(.*?)\n```", body, re.DOTALL)
        if not prompt_block_m:
            continue
        desc_raw = prompt_block_m.group(1).strip()

        # 依據 ID 前綴或關鍵字精準判斷類別
        title_lower = title_line.lower()
        if title_line.startswith("C-") or "角色" in title_line or "少年" in title_line or "少女" in title_line or "女" in title_line:
            asset_type = "character"
        elif title_line.startswith("CREATURE-") or any(k in title_lower for k in ["妖", "怪", "鼠", "蛇", "蟲", "slime"]):
            asset_type = "creature"
        elif title_line.startswith("S-") or any(k in title_lower for k in ["場景", "巷", "店", "廳", "校園"]):
            asset_type = "scene"
        elif title_line.startswith("P-") or any(k in title_lower for k in ["道具", "槍", "棍"]):
            asset_type = "prop"
        else:
            asset_type = "character"

        # 推導輸出檔名：優先採用「參考圖：`images/...`」欄位
        ref_m = re.search(r"參考圖[：:]\s*`?([^\s`\n]+)`?", body)
        if ref_m:
            ref_path = ref_m.group(1).strip()
            filename = pathlib.Path(ref_path).name
        else:
            # 依 ID slug 產生乾淨檔名
            clean_id_m = re.search(r"^(C-[a-z0-9-]+|CREATURE-[a-z0-9-]+|S-[a-z0-9-]+|P-[a-z0-9-]+)", title_line)
            if clean_id_m:
                slug = clean_id_m.group(1)
                # 轉為慣用前綴檔名
                if slug.startswith("C-"):
                    slug_core = "".join(part.capitalize() for part in slug[2:].split("-"))
                    filename = f"char-{slug_core}.png"
                elif slug.startswith("CREATURE-"):
                    filename = f"creature-{slug[9:]}.png"
                elif slug.startswith("S-"):
                    filename = f"scene-{slug[2:]}.png"
                else:
                    filename = f"prop-{slug[2:]}.png"
            else:
                slug = re.sub(r"[^A-Za-z0-9_-]+", "", title_line.replace(" ", "-"))
                filename = f"{asset_type}-{slug}.png"

        anti_m = re.search(r"(?:反美化|禁止特徵|禁止特征)[：:]\s*([^\n]+)", body)
        assets.append({
            "name": title_line,
            "type": asset_type,
            "filename": filename,
            "description": desc_raw,
            "style_lock": style_lock,
            "avoid": anti_m.group(1).strip().strip("`") if anti_m else "",
        })

    if not assets:
        return parse_card_assets(text, style_lock)
    # #15：兩種格式混寫時，不悄悄掉卡片資產——補上卡片格式裡舊格式沒有的 ID，並警告
    def _key(a):
        m = re.match(r"[\w-]+", a["name"])
        return m.group(0) if m else a["name"]
    have = {_key(a) for a in assets}
    extra = [c for c in parse_card_assets(text, style_lock) if _key(c) not in have]
    if extra:
        import sys
        print(f"⚠ assets.md 混用兩種格式（```text 區塊與卡片欄位）：已補入卡片格式資產 "
              f"{', '.join(c['name'] for c in extra)}；建議統一一種格式。", file=sys.stderr)
        assets.extend(extra)
    return assets


CARD_LABEL = re.compile(r"^-\s*\*\*(.+?)\*\*[：:]\s*(.*)$")
CARD_TYPES = (("C-", "character"), ("CREATURE-", "creature"), ("EXTRAS-", "extras"), ("S-", "scene"), ("P-", "prop"))
TEMPLATE_VERSION = "master-4view-v1"


def parse_card_assets(text: str, style_lock: str = DEFAULT_STYLE_LOCK_3D) -> List[Dict[str, Any]]:
    """解析 repo assets.md 範本的卡片格式（### C-xxx 加「- **欄位**：值」條列）。

    角色描述優先取 **設定板描述**（母版中文槽位），其次 **固定描述片段**；**背面特徵** 併入描述。
    """
    assets: List[Dict[str, Any]] = []
    for m in re.finditer(r"^###\s+((?:C|CREATURE|EXTRAS|S|P)-[\w-]+)[　 ]*(.*?)\s*$(.*?)(?=^#{1,3}\s|\Z)", text, re.MULTILINE | re.DOTALL):
        aid, name, body = m.group(1), m.group(2).strip(), m.group(3)
        fields: Dict[str, str] = {}
        for line in body.splitlines():
            lm = CARD_LABEL.match(line.strip())
            if lm:
                tick = re.search(r"`([^`]+)`", lm.group(2))
                fields.setdefault(lm.group(1), tick.group(1).strip() if tick else lm.group(2).strip())
        desc = fields.get("設定板描述") or next((v for k, v in fields.items() if k.startswith("固定描述")), "")
        if not desc or desc.startswith("<"):
            continue
        if fields.get("背面特徵") and not fields["背面特徵"].startswith("<"):
            desc += f"；背面特徵：{fields['背面特徵']}"
        atype = next(t for prefix, t in CARD_TYPES if aid.startswith(prefix))
        ref = next((v for k, v in fields.items() if k.startswith(("設定圖", "母版圖"))), "")
        filename = pathlib.Path(ref).name if ref.endswith((".png", ".jpg")) else f"{atype}-{aid.split('-', 1)[1]}.png"
        assets.append({"name": f"{aid} {name}".strip(), "type": atype, "filename": filename,
                       "description": desc, "style_lock": style_lock})
        # #14：一個角色多套服裝——欄位標籤 W-<slug>-NN 各出一張服裝設定板
        for k, v in fields.items():
            if atype == "character" and re.fullmatch(r"W-[\w-]+-\d+", k) and v and not v.startswith("<"):
                wref = fields.get(f"設定圖 {k}", "")
                wfile = pathlib.Path(wref).name if wref.endswith((".png", ".jpg")) else f"wardrobe-{k[2:]}.png"
                assets.append({"name": f"{k} {name}".strip(), "type": "character", "filename": wfile,
                               "description": f"{desc}；本套服裝：{v}", "style_lock": style_lock})
    return assets


def read_style_index(assets_path: pathlib.Path) -> Optional[str]:
    """讀 assets.md「風格錨點」區的 `style_index`（master／semi-real／styles.md 編號）；沒寫回 None。"""
    m = re.search(r"^-\s*\*\*style_index\*\*[：:]\s*`?([\w-]+)`?", assets_path.read_text(encoding="utf-8"), re.MULTILINE)
    return m.group(1) if m else None


def compile_full_prompt(asset: Dict[str, Any], style: Optional[Dict[str, str]] = None) -> str:
    """根據資產類型編譯完整標準 Prompt；assets.md 的「反美化／禁止特徵」(#18) 併入負面約束。"""
    base = _compile_base_prompt(asset, style)
    avoid = (asset.get("avoid") or "").strip()
    if avoid:
        base += f"\n負面約束（不得出現／不得美化）：{avoid}"
    return base


def _compile_base_prompt(asset: Dict[str, Any], style: Optional[Dict[str, str]] = None) -> str:
    atype = asset.get("type", "character")
    desc = asset.get("description", "")

    if atype == "character":
        return build_character_prompt(desc, style, asset.get("style_lock", ""))
    elif atype == "creature":
        return CREATURE_TURNAROUND_TEMPLATE.format(style_line=env_style_line(style), subject_desc=desc)
    elif atype == "scene":
        return SCENE_PLATE_TEMPLATE.format(style_line=env_style_line(style), subject_desc=desc)
    else:
        # 道具或其他
        return (
            f"{env_style_line(style)}, prop concept sheet, "
            f"neutral studio lighting, seamless flat neutral medium-grey background, 16:9. "
            f"Subject: {desc}"
        )


# ==============================================================================
# CLI 主程式
# ==============================================================================

ENGINE_ALIASES = {
    "codex": "codex", "codex_cli": "codex", "gpt_image": "codex",
    "grok": "grok", "grok_generate_image": "grok", "grok_builtin": "grok", "generateimage": "grok",
}
DEFAULT_ENGINE = "codex"


def normalize_engine(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    key = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    return ENGINE_ALIASES.get(key, key)


def resolve_engine(cli_value: Optional[str], project_dir: Optional[pathlib.Path]) -> Dict[str, str]:
    """依序：--engine → decisions.json design_engine → adapt/bible.json design_engine → 預設 codex。"""
    if cli_value:
        return {"engine": normalize_engine(cli_value), "source": "--engine"}
    if project_dir:
        dec = project_dir / "decisions.json"
        if dec.exists():
            try:
                for d in json.loads(dec.read_text(encoding="utf-8")).get("decisions", []):
                    if d.get("id") == "design_engine" and d.get("value"):
                        return {"engine": normalize_engine(d["value"]), "source": "decisions.json"}
            except (OSError, ValueError):
                pass
        bible = project_dir / "adapt" / "bible.json"
        if bible.exists():
            try:
                v = json.loads(bible.read_text(encoding="utf-8")).get("design_engine")
                if v:
                    return {"engine": normalize_engine(v), "source": "adapt/bible.json"}
            except (OSError, ValueError):
                pass
    return {"engine": DEFAULT_ENGINE, "source": "default"}


ASPECT_BY_TYPE = {"character": "16:9", "creature": "16:9", "scene": "16:9", "prop": "16:9", "extras": "16:9"}


def asset_id(item: Dict[str, Any]) -> str:
    m = re.match(r"[A-Za-z][\w-]*", item["name"])
    return m.group(0) if m else pathlib.Path(item["filename"]).stem


def build_manifest(compiled: List[Dict[str, Any]], style: Dict[str, str], project_dir: pathlib.Path,
                   images_dir: str = "images", aspect: Optional[str] = None) -> Dict[str, Any]:
    """Grok 內建 GenerateImage 生圖清單：角色先、場景後；場景附角色設定圖以外的風格參考。"""
    style_refs = [style["needs_reference"]] if style.get("needs_reference") else []
    items = []
    order = {"character": 0, "creature": 1, "extras": 2, "prop": 3, "scene": 4}
    for c in sorted(compiled, key=lambda c: order.get(c["type"], 9)):
        refs = list(style_refs)
        items.append({
            "id": asset_id(c),
            "name": c["name"],
            "type": c["type"],
            "output_path": f"{images_dir}/{c['filename']}",
            "prompt": c["full_prompt"],
            "aspect_ratio": aspect or ASPECT_BY_TYPE.get(c["type"], "16:9"),
            "reference_images": refs,
            "status": "pending",
        })
    return {
        "engine": "grok",
        "tool": "GenerateImage",
        "project_dir": str(project_dir),
        "style": style.get("key"),
        "note": "只列清單，不生圖。使用者核准設定後才逐張以 Grok 內建 GenerateImage 生成，"
                "存到 output_path，生成後把 status 改為 done 並親眼驗收。",
        "count": len(items),
        "items": items,
    }


def manifest_markdown(m: Dict[str, Any]) -> str:
    lines = [f"# Grok 生圖清單（{m['count']} 張）\n", f"- 引擎：Grok 內建 `{m['tool']}`", f"- 風格：`{m['style']}`",
             f"- {m['note']}\n"]
    for i, it in enumerate(m["items"], 1):
        refs = "、".join(f"`{r}`" for r in it["reference_images"]) or "（無）"
        lines += [f"## {i:02d}. {it['id']}（{it['type']}）", f"- 輸出：`{it['output_path']}`",
                  f"- 比例：{it['aspect_ratio']}", f"- 參考圖：{refs}", "- Prompt：", "```text", it["prompt"], "```", ""]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(
        description="核心資產提示詞自動組裝器與生圖引擎門禁工具 (export_asset_prompts.py)"
    )
    parser.add_argument("--assets-md", type=str, default=None, help="assets.md 檔案路徑")
    parser.add_argument("--bible-json", type=str, default=None, help="bible.json 檔案路徑")
    parser.add_argument("--out-json", type=str, default=None, help="匯出組裝好的 Prompt 清單為 JSON")
    parser.add_argument("--out-md", type=str, default=None, help="匯出組裝好的 Prompt 清單為 Markdown")
    parser.add_argument("--filter", type=str, default=None, help="過濾特定名稱或類別 (如 character, scene, ye-weishan)")
    parser.add_argument("--style", type=str, default=None, help=f"角色設定板風格：{STYLE_CHOICES}；不給則讀 assets.md 的 style_index，再不然用預設 {style_rules.STYLE14_KEY}")
    parser.add_argument("--no-gate", action="store_true", help="略過門禁警告輸出 (僅回傳純數據)")
    parser.add_argument("--project-dir", type=str, default=None, help="專案根目錄（讀 decisions.json 的 design_engine；預設為 assets.md 所在目錄）")
    parser.add_argument("--engine", type=str, default=None, help="覆寫設定圖引擎（codex｜grok）；正常應以 h3d decide design_engine 定案")
    parser.add_argument("--manifest-out", type=str, default=None, help="引擎為 grok 時的生圖清單 JSON 路徑（同名 .md 一併輸出；預設 <專案>/images/grok-manifest.json）")
    parser.add_argument("--images-dir", type=str, default="images", help="清單內輸出路徑的資料夾（相對專案根）")

    args = parser.parse_args()

    if not args.no_gate:
        print(ENGINE_CONSISTENCY_GATE)

    # 1. 尋找與載入資產檔案
    assets: List[Dict[str, Any]] = []
    used_assets_md: Optional[pathlib.Path] = None
    if args.assets_md:
        p_assets = pathlib.Path(args.assets_md).resolve()
        used_assets_md = p_assets
        assets = parse_assets_markdown(p_assets)
    elif args.bible_json:
        # 若傳入 bible.json，檢查同層或上層是否有 assets.md
        p_bible = pathlib.Path(args.bible_json).resolve()
        cand = p_bible.parent.parent / "assets.md"
        if not cand.exists():
            cand = p_bible.parent / "assets.md"
        if cand.exists():
            used_assets_md = cand
            assets = parse_assets_markdown(cand)
    else:
        # 自動尋找「當前目錄」或專案常見位置的 assets.md。
        # 這裡刻意不列任何使用者本機的絕對路徑：skill 要能換機器、換專案直接跑。
        defaults = [
            pathlib.Path("assets.md"),
            pathlib.Path("ch02/assets.md"),
        ]
        for d in defaults:
            if d.exists():
                used_assets_md = d.resolve()
                assets = parse_assets_markdown(used_assets_md)
                break

    if not assets:
        if args.bible_json:
            print("[錯誤] --bible-json 目前只用來尋找關聯的 assets.md，不直接解析資產；請提供 assets.md 或使用 --assets-md 指定。", file=sys.stderr)
        else:
            print("[警告] 未能解析到任何資產設定！請提供 assets.md 或使用 --assets-md 指定。", file=sys.stderr)
        sys.exit(1)

    # 2. 過濾
    if args.filter:
        flt = args.filter.lower()
        assets = [
            a for a in assets
            if flt in a["name"].lower() or flt in a["type"].lower() or flt in a["filename"].lower()
        ]

    # 3. 組裝標準提示詞
    try:
        style_index = args.style or (read_style_index(used_assets_md) if used_assets_md else None)
        if not style_index and any(a["type"] == "character" for a in assets):
            # 預設 14 號「古風寫實厚塗・電影感」；仍提醒與使用者確認（可改選）。
            style_index = style_rules.DEFAULT_STYLE_KEY
            print(f"[提醒] assets.md 尚未寫 style_index，使用預設風格 14 號「{style_rules.STYLE14_NAME}」"
                  f"（{style_rules.STYLE14_KEY}）。請在階段 0 與使用者確認；要改選請寫入 style_index 或加 --style。"
                  f"可選：{STYLE_CHOICES}", file=sys.stderr)
        style = resolve_style(style_index)
    except (OSError, ValueError) as exc:
        print(f"[錯誤] --style {style_index}：{exc}", file=sys.stderr)
        sys.exit(1)
    compiled_results = []
    for item in assets:
        full_prompt = compile_full_prompt(item, style)
        compiled_results.append({
            "name": item["name"],
            "type": item["type"],
            "filename": item["filename"],
            "raw_description": item["description"],
            "full_prompt": full_prompt,
            "template": TEMPLATE_VERSION if item["type"] == "character" else None,
            "style": style["key"] if item["type"] == "character" else None,
        })

    project_dir = pathlib.Path(args.project_dir).resolve() if args.project_dir else (
        used_assets_md.parent if used_assets_md else pathlib.Path.cwd())
    engine = resolve_engine(args.engine, project_dir)
    print(f"[引擎] 設定圖引擎：{engine['engine']}（來源：{engine['source']}）")
    if engine["engine"] == "grok":
        manifest = build_manifest(compiled_results, style, project_dir, args.images_dir)
        mpath = pathlib.Path(args.manifest_out).resolve() if args.manifest_out else project_dir / args.images_dir / "grok-manifest.json"
        mpath.parent.mkdir(parents=True, exist_ok=True)
        mpath.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        mpath.with_suffix(".md").write_text(manifest_markdown(manifest), encoding="utf-8")
        print(f"[Grok 生圖清單] {mpath}（{manifest['count']} 張；只列清單，未生圖）")

    # 4. 輸出列印或儲存
    if style.get("needs_reference"):
        print(f"[提醒] {style['name']} 純提示詞容易滑向照片寫實：出圖時請附 repo 樣圖 {style['needs_reference']} 當風格參考。")
    print(f"✅ 成功解析並組裝 {len(compiled_results)} 項核心資產提示詞：\n")
    for idx, c in enumerate(compiled_results, 1):
        print(f"[{idx:02d}] 【{c['type'].upper()}】{c['name']}")
        print(f"     目標檔名: {c['filename']}")
        print(f"     規格類型: {'四格橫排純灰底轉面圖' if c['type'] == 'character' else ('三視圖純灰底' if c['type'] == 'creature' else ('純灰底道具設定圖' if c['type'] == 'prop' else '無人空景底圖'))}")
        print(f"     標準 Prompt:\n     {c['full_prompt']}\n")

    if args.out_json:
        out_p = pathlib.Path(args.out_json).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)
        with out_p.open("w", encoding="utf-8") as f:
            json.dump(compiled_results, f, ensure_ascii=False, indent=2)
        print(f"[JSON 已匯出] {out_p}")

    if args.out_md:
        out_p = pathlib.Path(args.out_md).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)
        lines = ["# 核心資產標準提示詞清單 (Core Asset Prompts)\n\n"]
        for c in compiled_results:
            lines.append(f"## {c['name']} (`{c['filename']}`)\n\n")
            lines.append(f"- **類型**：{c['type']}\n")
            lines.append(f"- **完整 Prompt**：\n```text\n{c['full_prompt']}\n```\n\n---\n\n")
        out_p.write_text("".join(lines), encoding="utf-8")
        print(f"[Markdown 已匯出] {out_p}")


if __name__ == "__main__":
    main()
