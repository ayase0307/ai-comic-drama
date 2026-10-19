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
   - 強制警告：跨章節核心資產設定圖嚴禁隨意更換生圖引擎！
   - 若前章採用 Codex CLI (GPT Image)，本章必須沿用 Codex CLI，嚴禁改用 Qwen-Image 或其他模型，
     避免兩個圖片模型畫風割裂導致全片崩毀。
4. 支援匯出為 JSON、Markdown，或輸出為 Codex CLI / 外部工具生圖指令腳本。

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
2. 跨章節製作時，必須嚴格沿用前章相同的圖片生成引擎（如 Codex CLI / GPT Image 2.5）；
   嚴禁本章改用 Qwen-Image 或其他圖片模型生成彩色核心資產！
3. 圖片模型之間的筆觸、材質與膚色渲染（SSS）存在顯著割裂，一旦混用將導致片中角色換臉與風格跳變！
4. 畫風語義漂移防禦（Anti-Pixar 鐵律）：
   - 角色 Prompt 必須嚴格指定「東亞五官骨相與比例（realistic East Asian facial proportions）」；
   - 嚴格負向/排他詞：STRICTLY NO Pixar style, NO Disney cartoon style, NO Western cartoon proportions, NO exaggerated oversized eyes, NO freckles；
   - 嚴格禁止使用「wide bright eyes + wide grin」等會誘導歐美卡通大眼雀斑笑臉的詞彙組合。
5. 生圖後必須以 view_file 進行親眼視覺驗收，禁止僅憑檔案大小與解析度交件！
6. Qwen-Image 僅限用於階段 4 的黑白鉛筆分鏡草圖九宮格構圖審核。
================================================================================
"""

DEFAULT_STYLE_LOCK_3D = (
    "Photorealistic-stylized East Asian 3D CG cinematic render, Unreal Engine 5 aesthetic, "
    "realistic East Asian facial bone structure and eye proportions, delicate subsurface-scattering skin texture, "
    "cinematic volumetric lighting, shallow depth of field, detailed hair and fabric, 16:9; "
    "STRICTLY NO Pixar style, NO Disney cartoon style, NO exaggerated oversized cartoon eyes, NO freckles"
)

# 角色設定板以 ai-image-prompt「3D 漫劇寫實厚涂四視圖母版」為準（段 1 構圖一字不改）。
# 風格選擇：預設母版 3d-realistic；`--style N` 改用 references/styles.md 第 N 套錨（取代母版渲染與膚質句）。
DEFAULT_STYLE_KEY = "3d-realistic"
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


def build_character_prompt(subject_desc: str, style: Optional[Dict[str, str]] = None, project_lock: str = "") -> str:
    """母版五段式角色設定板提示詞。style=None 用母版 3D 寫實厚塗；否則用 styles.md 錨取代渲染與膚質句。"""
    if style:
        style_part = f"风格：{style['anchor']}。"
        quality = MASTER_QUALITY_TAIL + (f" 避免：{style['negative']}。" if style["negative"] else "")
    else:
        style_part = f"风格：{MASTER_STYLE_3D}"
        quality = MASTER_QUALITY_3D + MASTER_QUALITY_TAIL
        if project_lock and project_lock != DEFAULT_STYLE_LOCK_3D:
            quality += f" 专案风格锁：{project_lock}"
    return (
        f"构图：{MASTER_COMPOSITION}{MASTER_GUARDS}\n"
        f"{style_part}\n"
        f"角色：{subject_desc}\n"
        f"背面：{MASTER_BACK_RULE}\n"
        f"画质：{quality}"
    )

CREATURE_TURNAROUND_TEMPLATE = (
    "Photorealistic-stylized 3D CG creature concept sheet, cinematic creature design, "
    "realistic textures and volume, neutral studio lighting, 16:9 aspect ratio. "
    "Creature turnaround model sheet against a seamless flat neutral medium-grey background showing "
    "front view, side profile view, and head close-up. "
    "Subject: {subject_desc}"
)

SCENE_PLATE_TEMPLATE = (
    "Photorealistic-stylized 3D CG environment plate, realistic architectural and environmental rendering, "
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

        assets.append({
            "name": title_line,
            "type": asset_type,
            "filename": filename,
            "description": desc_raw,
            "style_lock": style_lock,
        })

    return assets


def compile_full_prompt(asset: Dict[str, Any], style: Optional[Dict[str, str]] = None) -> str:
    """根據資產類型編譯完整標準 Prompt。"""
    atype = asset.get("type", "character")
    desc = asset.get("description", "")

    if atype == "character":
        return build_character_prompt(desc, style, asset.get("style_lock", ""))
    elif atype == "creature":
        return CREATURE_TURNAROUND_TEMPLATE.format(subject_desc=desc)
    elif atype == "scene":
        return SCENE_PLATE_TEMPLATE.format(subject_desc=desc)
    else:
        # 道具或其他
        return (
            f"3D animated series prop concept sheet, stylized realistic CG render, "
            f"neutral studio lighting, seamless flat neutral medium-grey background, 16:9. "
            f"Subject: {desc}"
        )


# ==============================================================================
# CLI 主程式
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="核心資產提示詞自動組裝器與生圖引擎門禁工具 (export_asset_prompts.py)"
    )
    parser.add_argument("--assets-md", type=str, default=None, help="assets.md 檔案路徑")
    parser.add_argument("--bible-json", type=str, default=None, help="bible.json 檔案路徑")
    parser.add_argument("--out-json", type=str, default=None, help="匯出組裝好的 Prompt 清單為 JSON")
    parser.add_argument("--out-md", type=str, default=None, help="匯出組裝好的 Prompt 清單為 Markdown")
    parser.add_argument("--filter", type=str, default=None, help="過濾特定名稱或類別 (如 character, scene, ye-weishan)")
    parser.add_argument("--style", type=int, default=None, help="角色設定板風格：styles.md 的編號 1–11；不給則用母版 3D 漫劇寫實厚涂")
    parser.add_argument("--no-gate", action="store_true", help="略過門禁警告輸出 (僅回傳純數據)")

    args = parser.parse_args()

    if not args.no_gate:
        print(ENGINE_CONSISTENCY_GATE)

    # 1. 尋找與載入資產檔案
    assets: List[Dict[str, Any]] = []
    if args.assets_md:
        p_assets = pathlib.Path(args.assets_md).resolve()
        assets = parse_assets_markdown(p_assets)
    elif args.bible_json:
        # 若傳入 bible.json，檢查同層或上層是否有 assets.md
        p_bible = pathlib.Path(args.bible_json).resolve()
        cand = p_bible.parent.parent / "assets.md"
        if not cand.exists():
            cand = p_bible.parent / "assets.md"
        if cand.exists():
            assets = parse_assets_markdown(cand)
    else:
        # 自動尋找當前目錄或常規目錄下的 assets.md
        defaults = [
            pathlib.Path("assets.md"),
            pathlib.Path("ch02/assets.md"),
            pathlib.Path(r"C:\Users\kirit\OneDrive\文件\噩盡島\噩盡島-漫劇\ch02\assets.md"),
            pathlib.Path(r"C:\Users\kirit\OneDrive\文件\噩盡島\噩盡島-漫劇\assets.md"),
        ]
        for d in defaults:
            if d.exists():
                assets = parse_assets_markdown(d.resolve())
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
        style = load_style_anchor(args.style) if args.style else None
    except (OSError, ValueError) as exc:
        print(f"[錯誤] --style {args.style}：{exc}", file=sys.stderr)
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
        })

    # 4. 輸出列印或儲存
    print(f"✅ 成功解析並組裝 {len(compiled_results)} 項核心資產提示詞：\n")
    for idx, c in enumerate(compiled_results, 1):
        print(f"[{idx:02d}] 【{c['type'].upper()}】{c['name']}")
        print(f"     目標檔名: {c['filename']}")
        print(f"     規格類型: {'四格橫排純灰底轉面圖' if c['type'] == 'character' else ('三視圖純灰底' if c['type'] == 'creature' else '無人空景底圖')}")
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
