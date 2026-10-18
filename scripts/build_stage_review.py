#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_stage_review.py — 八階段強制斷點狀態機與高設計感 HTML 視覺化審核介面產生器

核心職責：
1. 強制執行「每完成一階段 → 產出高設計感 HTML 審核介面 → 停下等待使用者明確同意 → 才解鎖下一階段」的斷點紀律。
2. 維護專案根目錄下的 `project-state.json`，防止 Agent 私自跳關（例如從階段 2 資產圖跳過階段 4 九宮格直接跑去階段 6 生影片）。
3. 針對階段 0～7 產出 Cinema Editorial Studio 級別之互動式 HTML 審核頁面 (`review/stage-{0..7}.html`)：
   - 階段 0 (`stage-0-intake.html`)：專案定調、體量反推試算與風格色票儀表板
   - 階段 1 (`stage-1-adaptation.html`)：《完整角色設定文件 v4.0》十一章節完整卡片 + 故事地圖與分集大綱
   - 階段 2 (`stage-2-assets.html`)：【核心重點】角色設定表格 × 產出設定圖片 左右並排（Side-by-Side）審核藝廊（含 Lightbox 全螢幕放大、缺圖紅燈攔截）
   - 階段 3 (`stage-3-script.html`)：漫劇劇本 × 原著對照 × H3 台詞預算進度條審核台
   - 階段 4 (`stage-4-storyboard.html`)：【必經斷點】Qwen 黑白鉛筆九宮格構圖 (`images/grid-*.png`) × 導演分鏡表（含動作力學三要素與綁定服裝圖縮圖）並排確認台
   - 階段 5 (`stage-5-prompts.html`)：H3 六段式提示詞 × `<Picture 1..N>` 實際參考圖縮圖 × LoRA 對帳中心
   - 階段 6 (`stage-6-videos.html`)：HTML5 影片播放器 × 九宮格草圖 × 角色設定圖 × QA 指標並排驗收室
   - 階段 7 (`stage-7-final.html`)：最終成片劇院放映室與全階段簽核總覽

用法：
  # 產出指定階段 HTML 並進入 awaiting_user_approval 斷點狀態
  python scripts/build_stage_review.py --project-dir <專案目錄> --stage <0..7>

  # 使用者明確回覆沒問題後，解鎖該階段以允許進入下一階段
  python scripts/build_stage_review.py --project-dir <專案目錄> --approve-stage <0..7> --user-note "使用者確認通過"

  # 供下游腳本（compile_layer2_to_h3.py / submit_h3_segments.py 等）呼叫之硬性門禁檢查
  python scripts/build_stage_review.py --project-dir <專案目錄> --require-approved <0..7>

  # 執行內建自檢
  python scripts/build_stage_review.py --self-test
"""

from __future__ import annotations

import argparse
from datetime import datetime
import html
import io
import json
import os
from pathlib import Path
import re
import struct
import sys
from typing import Any, Dict, List, Optional, Tuple

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

SCRIPTS_DIR = Path(__file__).resolve().parent
ADAPT_DIR = SCRIPTS_DIR / "adapt"
STORYBOARD_DIR = SCRIPTS_DIR / "storyboard"
for p in (SCRIPTS_DIR, ADAPT_DIR, STORYBOARD_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from validate_character_bible import parse_character_blocks, validate_character_bible  # noqa: E402


STAGE_META: Dict[int, Dict[str, str]] = {
    0: {"slug": "intake", "name": "階段 0｜專案定調與體量試算", "short": "0 定調", "file": "stage-0-intake.html"},
    1: {"slug": "adaptation", "name": "階段 1｜原著改編與完整角色設定 v4", "short": "1 改編與角色聖經", "file": "stage-1-adaptation.html"},
    2: {"slug": "assets", "name": "階段 2｜角色設定表 × 核心資產圖並排審核", "short": "2 資產設定圖", "file": "stage-2-assets.html"},
    3: {"slug": "script", "name": "階段 3｜分集漫劇劇本與台詞預算審計", "short": "3 漫劇劇本", "file": "stage-3-script.html"},
    4: {"slug": "storyboard", "name": "階段 4｜導演分鏡表 × 九宮格草圖構圖確認", "short": "4 九宮格分鏡", "file": "stage-4-storyboard.html"},
    5: {"slug": "prompts", "name": "階段 5｜H3 六段式提示詞與參考圖綁定對帳", "short": "5 提示詞包", "file": "stage-5-prompts.html"},
    6: {"slug": "videos", "name": "階段 6｜分段影片 × 九宮格 × 設定圖並排驗收", "short": "6 影片生成驗收", "file": "stage-6-videos.html"},
    7: {"slug": "final", "name": "階段 7｜配音字幕組裝成片交付放映室", "short": "7 最終成片", "file": "stage-7-final.html"},
}


def now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def get_png_dimensions(path: Path) -> Optional[Tuple[int, int]]:
    """純標準庫讀取 PNG 寬高。"""
    try:
        with path.open("rb") as f:
            head = f.read(24)
        if len(head) >= 24 and head[:8] == b"\x89PNG\r\n\x1a\n" and head[12:16] == b"IHDR":
            w, h = struct.unpack(">II", head[16:24])
            return int(w), int(h)
    except Exception:
        pass
    return None


def rel_img_src(project_dir: Path, img_path_str: str) -> Tuple[str, Optional[Path]]:
    """將專案相對路徑轉為相對於 review/stage-X.html 的 `../...` 路徑並回傳實體路徑。"""
    if not img_path_str:
        return "", None
    clean = img_path_str.strip().strip("`").replace("\\", "/")
    cand = Path(clean)
    if not cand.is_absolute():
        cand = (project_dir / clean).resolve()
    if cand.exists():
        try:
            rel = cand.relative_to(project_dir.resolve()).as_posix()
            return f"../{rel}", cand
        except ValueError:
            return cand.as_uri(), cand
    # 嘗試在 images/ 下用檔名匹配
    fallback = project_dir / "images" / Path(clean).name
    if fallback.exists():
        rel = fallback.relative_to(project_dir.resolve()).as_posix()
        return f"../{rel}", fallback
    return f"../{clean}", None


# ==============================================================================
# 狀態機管理 (project-state.json)
# ==============================================================================

def state_file_path(project_dir: Path) -> Path:
    return project_dir / "project-state.json"


def load_project_state(project_dir: Path) -> Dict[str, Any]:
    sp = state_file_path(project_dir)
    if sp.exists():
        try:
            return json.loads(sp.read_text(encoding="utf-8"))
        except Exception:
            pass
    stages = {}
    for k, m in STAGE_META.items():
        stages[str(k)] = {
            "stage": k,
            "name": m["name"],
            "status": "locked" if k > 0 else "in_progress",
            "html_file": f"review/{m['file']}",
            "updated_at": None,
            "approved_at": None,
            "user_note": None,
        }
    return {
        "project_dir": str(project_dir.resolve()),
        "current_stage": 0,
        "stages": stages,
    }


def save_project_state(project_dir: Path, state: Dict[str, Any]) -> None:
    sp = state_file_path(project_dir)
    sp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def check_stage_prerequisite(project_dir: Path, target_stage: int, allow_bypass: bool = False) -> Tuple[bool, str]:
    """檢查進入 target_stage 前，所有前置階段是否皆已取得使用者確認 (approved)。"""
    if allow_bypass or target_stage <= 0:
        return True, "OK"
    state = load_project_state(project_dir)
    stages = state.get("stages", {})
    for prev in range(0, target_stage):
        st = stages.get(str(prev), {}).get("status", "locked")
        html_rel = STAGE_META[prev]["file"]
        if st != "approved":
            return (
                False,
                f"❌ [階段斷點門禁阻斷] 前置「{STAGE_META[prev]['name']}」狀態為 `{st}`（尚未取得使用者明確確認通過）！\n"
                f"   👉 規範要求：每完成一階段必須先執行 `build_stage_review.py --project-dir \"{project_dir}\" --stage {prev}`\n"
                f"      將產出的 `review/{html_rel}` 交給使用者審閱，等使用者明確回覆「沒問題／通過」後，\n"
                f"      再執行 `build_stage_review.py --project-dir \"{project_dir}\" --approve-stage {prev} --user-note \"...\"` 解鎖下一關！\n"
                f"   ⛔ 嚴禁跳過階段確認或從資產圖直接跳去生影片！"
            )
    return True, "OK"


# ==============================================================================
# Markdown 簡易轉 HTML 輔助器（表格、清單、引用、程式碼）
# ==============================================================================

def md_table_to_html(lines: List[str]) -> str:
    rows = []
    for ln in lines:
        s = ln.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if all(re.fullmatch(r"[:\-]+", c.replace(" ", "")) for c in cells if c):
            continue
        rows.append(cells)
    if not rows:
        return ""
    out = ['<div class="table-wrap"><table class="studio-table">']
    out.append("<thead><tr>" + "".join(f"<th>{inline_md(c)}</th>" for c in rows[0]) + "</tr></thead>")
    if len(rows) > 1:
        out.append("<tbody>")
        for r in rows[1:]:
            out.append("<tr>" + "".join(f"<td>{inline_md(c)}</td>" for c in r) + "</tr>")
        out.append("</tbody>")
    out.append("</table></div>")
    return "\n".join(out)


def inline_md(text: str) -> str:
    esc = html.escape(text)
    esc = re.sub(r"`([^`]+)`", r'<code class="inline-code">\1</code>', esc)
    esc = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", esc)
    esc = re.sub(r"(\(L\d+(?:[-–—]\d+)?\)|（L\d+(?:[-–—]\d+)?）)", r'<span class="canon-badge">\1</span>', esc)
    return esc


def render_markdown_block(md_text: str) -> str:
    """將 Markdown 區段渲染為高品質 Studio HTML。"""
    lines = md_text.splitlines()
    out: List[str] = []
    i = 0
    while i < len(lines):
        ln = lines[i]
        stripped = ln.strip()
        if not stripped:
            i += 1
            continue
        if stripped == "---":
            out.append('<hr class="studio-divider">')
            i += 1
            continue
        if stripped.startswith("```"):
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(html.escape(lines[i]))
                i += 1
            i += 1
            out.append(f'<pre class="studio-pre"><code>{chr(10).join(code_lines)}</code></pre>')
            continue
        if stripped.startswith("|"):
            tbl_lines = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                tbl_lines.append(lines[i])
                i += 1
            out.append(md_table_to_html(tbl_lines))
            continue
        if stripped.startswith(">"):
            q_lines = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                q_lines.append(inline_md(re.sub(r"^>\s?", "", lines[i].strip())))
                i += 1
            out.append(f'<blockquote class="studio-quote">{"<br>".join(q_lines)}</blockquote>')
            continue
        if stripped.startswith("#### "):
            out.append(f'<h4 class="studio-h4">{inline_md(stripped[5:])}</h4>')
            i += 1
            continue
        if stripped.startswith("### "):
            out.append(f'<h3 class="studio-h3">{inline_md(stripped[4:])}</h3>')
            i += 1
            continue
        if stripped.startswith("## "):
            out.append(f'<h2 class="studio-h2">{inline_md(stripped[3:])}</h2>')
            i += 1
            continue
        if stripped.startswith("# "):
            out.append(f'<h1 class="studio-h1">{inline_md(stripped[2:])}</h1>')
            i += 1
            continue
        if stripped.startswith(("- ", "* ")):
            ul_items = []
            while i < len(lines) and lines[i].strip().startswith(("- ", "* ")):
                ul_items.append(f"<li>{inline_md(lines[i].strip()[2:])}</li>")
                i += 1
            out.append(f'<ul class="studio-list">{"".join(ul_items)}</ul>')
            continue
        if re.match(r"^\d+\.\s+", stripped):
            ol_items = []
            while i < len(lines) and re.match(r"^\d+\.\s+", lines[i].strip()):
                item_txt = re.sub(r"^\d+\.\s+", "", lines[i].strip())
                ol_items.append(f"<li>{inline_md(item_txt)}</li>")
                i += 1
            out.append(f'<ol class="studio-list">{"".join(ol_items)}</ol>')
            continue
        out.append(f'<p class="studio-p">{inline_md(stripped)}</p>')
        i += 1
    return "\n".join(out)


# ==============================================================================
# HTML 骨架與 Cinema Studio 設計系統
# ==============================================================================

def wrap_studio_html(
    project_dir: Path,
    stage: int,
    state: Dict[str, Any],
    hero_subtitle: str,
    kpi_cards: List[Tuple[str, str, str]],
    body_html: str,
    checklist_items: List[str],
) -> str:
    meta = STAGE_META[stage]
    stages_state = state.get("stages", {})

    # 頂部八階段導覽列
    nav_pills = []
    for k in range(8):
        st_info = stages_state.get(str(k), {})
        st = st_info.get("status", "locked")
        is_cur = (k == stage)
        cls = "stage-pill"
        if is_cur:
            cls += " active"
        elif st == "approved":
            cls += " approved"
        elif st == "awaiting_user_approval":
            cls += " awaiting"
        badge_icon = "✅" if st == "approved" else ("⏳" if st == "awaiting_user_approval" else ("🔵" if is_cur else "🔒"))
        href = STAGE_META[k]["file"] if (project_dir / "review" / STAGE_META[k]["file"]).exists() or is_cur else "#"
        nav_pills.append(
            f'<a href="{href}" class="{cls}"><span class="pill-icon">{badge_icon}</span><span>{STAGE_META[k]["short"]}</span></a>'
        )

    kpi_html = "".join(
        f'<div class="kpi-card"><div class="kpi-label">{html.escape(lbl)}</div>'
        f'<div class="kpi-val {tone}">{html.escape(val)}</div></div>'
        for lbl, val, tone in kpi_cards
    )

    chk_html = "".join(
        f'<label class="chk-item"><input type="checkbox" checked> <span>{inline_md(item)}</span></label>'
        for item in checklist_items
    )

    return f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{html.escape(meta['name'])} — AI 漫劇製片審核中心</title>
<style>
  :root {{
    --bg-canvas: #080A10;
    --bg-surface: #10141F;
    --bg-elevated: #171D2D;
    --bg-glass: rgba(23, 29, 45, 0.82);
    --border-subtle: rgba(255, 255, 255, 0.08);
    --border-gold: rgba(229, 184, 75, 0.45);
    --text-primary: #F3F5F9;
    --text-secondary: #9CA6BA;
    --text-muted: #647087;
    --accent-gold: #E5B84B;
    --accent-cyan: #38BDF8;
    --accent-emerald: #10B981;
    --accent-rose: #F43F5E;
    --accent-amber: #F59E0B;
    --radius-lg: 14px;
    --radius-md: 10px;
    --shadow-card: 0 14px 34px rgba(0, 0, 0, 0.45);
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    padding: 0;
    background: radial-gradient(circle at 15% 0%, #151C2C 0%, var(--bg-canvas) 55%);
    color: var(--text-primary);
    font-family: "Noto Sans TC", "Microsoft JhengHei", -apple-system, BlinkMacSystemFont, sans-serif;
    line-height: 1.68;
    min-height: 100vh;
  }}
  .topbar {{
    position: sticky;
    top: 0;
    z-index: 100;
    background: rgba(8, 10, 16, 0.90);
    backdrop-filter: blur(14px);
    border-bottom: 1px solid var(--border-subtle);
    padding: 12px 28px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    flex-wrap: wrap;
  }}
  .brand {{
    display: flex;
    align-items: center;
    gap: 12px;
    font-weight: 700;
    letter-spacing: 0.04em;
    color: var(--accent-gold);
    font-size: 15px;
  }}
  .stage-nav {{
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
  }}
  .stage-pill {{
    text-decoration: none;
    color: var(--text-secondary);
    background: var(--bg-surface);
    border: 1px solid var(--border-subtle);
    padding: 5px 11px;
    border-radius: 999px;
    font-size: 12.5px;
    display: inline-flex;
    align-items: center;
    gap: 5px;
    transition: all 0.2s ease;
  }}
  .stage-pill:hover {{ border-color: var(--accent-cyan); color: var(--text-primary); }}
  .stage-pill.active {{
    background: linear-gradient(135deg, rgba(229, 184, 75, 0.22), rgba(56, 189, 248, 0.14));
    border-color: var(--accent-gold);
    color: #FFF;
    font-weight: 600;
  }}
  .stage-pill.approved {{ border-color: rgba(16, 185, 129, 0.4); color: #A7F3D0; }}
  .container {{
    max-width: 1480px;
    margin: 0 auto;
    padding: 32px 28px 80px;
  }}
  .hero {{
    background: linear-gradient(135deg, rgba(23, 29, 45, 0.95) 0%, rgba(16, 20, 31, 0.92) 100%);
    border: 1px solid var(--border-gold);
    border-radius: var(--radius-lg);
    padding: 28px 32px;
    margin-bottom: 28px;
    box-shadow: var(--shadow-card);
  }}
  .hero-eyebrow {{
    color: var(--accent-gold);
    font-size: 12px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    margin-bottom: 6px;
  }}
  .hero-title {{
    margin: 0 0 8px 0;
    font-size: 28px;
    font-weight: 800;
    letter-spacing: 0.02em;
  }}
  .hero-sub {{
    margin: 0;
    color: var(--text-secondary);
    font-size: 15px;
  }}
  .kpi-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
    gap: 14px;
    margin-top: 22px;
  }}
  .kpi-card {{
    background: rgba(8, 10, 16, 0.65);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-md);
    padding: 14px 18px;
  }}
  .kpi-label {{ font-size: 12px; color: var(--text-muted); margin-bottom: 4px; }}
  .kpi-val {{ font-size: 20px; font-weight: 700; color: var(--text-primary); }}
  .kpi-val.gold {{ color: var(--accent-gold); }}
  .kpi-val.emerald {{ color: var(--accent-emerald); }}
  .kpi-val.cyan {{ color: var(--accent-cyan); }}
  .kpi-val.rose {{ color: var(--accent-rose); }}

  /* 斷點簽核橫幅 */
  .gate-banner {{
    background: rgba(229, 184, 75, 0.08);
    border: 1px solid var(--border-gold);
    border-radius: var(--radius-lg);
    padding: 20px 24px;
    margin-bottom: 30px;
  }}
  .gate-banner h3 {{
    margin: 0 0 10px 0;
    color: var(--accent-gold);
    font-size: 16px;
    display: flex;
    align-items: center;
    gap: 8px;
  }}
  .chk-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
    gap: 10px;
    margin-top: 10px;
  }}
  .chk-item {{
    display: flex;
    align-items: flex-start;
    gap: 8px;
    font-size: 14px;
    color: var(--text-primary);
    background: rgba(16, 20, 31, 0.7);
    padding: 8px 12px;
    border-radius: 8px;
    border: 1px solid var(--border-subtle);
  }}

  /* 並排卡片系統 (Stage 2 角色設定×圖片 / Stage 4 九宮格×分鏡 / Stage 6 影片×草圖) */
  .side-by-side-list {{
    display: flex;
    flex-direction: column;
    gap: 28px;
  }}
  .sbs-card {{
    background: var(--bg-surface);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-lg);
    overflow: hidden;
    box-shadow: var(--shadow-card);
  }}
  .sbs-header {{
    background: var(--bg-elevated);
    padding: 16px 24px;
    border-bottom: 1px solid var(--border-subtle);
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 12px;
  }}
  .sbs-title {{
    font-size: 20px;
    font-weight: 700;
    color: var(--accent-gold);
    margin: 0;
    display: flex;
    align-items: center;
    gap: 10px;
  }}
  .sbs-body {{
    display: grid;
    grid-template-columns: 1.15fr 0.85fr;
    gap: 0;
  }}
  @media (max-width: 1024px) {{
    .sbs-body {{ grid-template-columns: 1fr; }}
  }}
  .sbs-spec {{
    padding: 24px 28px;
    border-right: 1px solid var(--border-subtle);
    overflow-x: auto;
  }}
  .sbs-visual {{
    padding: 24px;
    background: rgba(8, 10, 16, 0.45);
    display: flex;
    flex-direction: column;
    gap: 18px;
  }}
  .asset-img-box {{
    background: #05070B;
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-md);
    padding: 12px;
    text-align: center;
  }}
  .asset-img-box img {{
    max-width: 100%;
    height: auto;
    border-radius: 8px;
    cursor: zoom-in;
    transition: transform 0.2s ease;
    display: block;
    margin: 0 auto;
  }}
  .asset-img-box img:hover {{ transform: scale(1.015); }}
  .asset-meta-bar {{
    margin-top: 10px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 12.5px;
    color: var(--text-secondary);
    flex-wrap: wrap;
    gap: 8px;
  }}
  .missing-box {{
    border: 2px dashed var(--accent-rose);
    background: rgba(244, 63, 94, 0.08);
    color: #FDA4AF;
    padding: 36px 20px;
    border-radius: var(--radius-md);
    text-align: center;
    font-weight: 600;
  }}

  /* 表格與排版元件 */
  .section-panel {{
    background: var(--bg-surface);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-lg);
    padding: 26px 30px;
    margin-bottom: 26px;
    box-shadow: var(--shadow-card);
  }}
  .studio-h1 {{ font-size: 24px; color: var(--accent-gold); margin-top: 0; }}
  .studio-h2 {{
    font-size: 20px;
    color: var(--accent-gold);
    border-bottom: 1px solid var(--border-subtle);
    padding-bottom: 8px;
    margin-top: 26px;
  }}
  .studio-h3 {{ font-size: 17px; color: var(--accent-cyan); margin-top: 20px; }}
  .studio-h4 {{
    font-size: 14.5px;
    color: #E2E8F0;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    background: rgba(255, 255, 255, 0.04);
    padding: 6px 12px;
    border-left: 3px solid var(--accent-gold);
    border-radius: 4px;
    margin: 18px 0 10px;
  }}
  .table-wrap {{ overflow-x: auto; margin: 12px 0; }}
  .studio-table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 13.5px;
  }}
  .studio-table th, .studio-table td {{
    border: 1px solid var(--border-subtle);
    padding: 10px 13px;
    text-align: left;
    vertical-align: top;
  }}
  .studio-table th {{
    background: var(--bg-elevated);
    color: var(--accent-gold);
    font-weight: 600;
  }}
  .studio-table tr:nth-child(even) td {{ background: rgba(255, 255, 255, 0.015); }}
  .studio-quote {{
    margin: 12px 0;
    padding: 12px 18px;
    background: rgba(229, 184, 75, 0.07);
    border-left: 4px solid var(--accent-gold);
    border-radius: 6px;
    color: #FDE68A;
    font-style: italic;
  }}
  .studio-pre {{
    background: #06080D;
    border: 1px solid var(--border-subtle);
    padding: 14px 18px;
    border-radius: 8px;
    overflow-x: auto;
    font-family: "JetBrains Mono", Consolas, monospace;
    font-size: 13px;
    color: #BAE6FD;
  }}
  .inline-code {{
    background: rgba(56, 189, 248, 0.12);
    color: #7DD3FC;
    padding: 2px 6px;
    border-radius: 4px;
    font-family: "JetBrains Mono", Consolas, monospace;
    font-size: 12.5px;
  }}
  .canon-badge {{
    display: inline-block;
    background: rgba(16, 185, 129, 0.16);
    color: #6EE7B7;
    border: 1px solid rgba(16, 185, 129, 0.35);
    padding: 1px 7px;
    border-radius: 999px;
    font-size: 11.5px;
    font-weight: 600;
    margin-left: 4px;
  }}
  .tag-badge {{
    display: inline-block;
    padding: 3px 10px;
    border-radius: 999px;
    font-size: 12px;
    font-weight: 600;
    background: rgba(56, 189, 248, 0.15);
    color: var(--accent-cyan);
    border: 1px solid rgba(56, 189, 248, 0.35);
  }}
  .tag-badge.gold {{
    background: rgba(229, 184, 75, 0.15);
    color: var(--accent-gold);
    border-color: rgba(229, 184, 75, 0.4);
  }}
  .tag-badge.emerald {{
    background: rgba(16, 185, 129, 0.15);
    color: #6EE7B7;
    border-color: rgba(16, 185, 129, 0.4);
  }}
  .tag-badge.rose {{
    background: rgba(244, 63, 94, 0.18);
    color: #FDA4AF;
    border-color: rgba(244, 63, 94, 0.45);
  }}
  .thumb-strip {{
    display: flex;
    gap: 12px;
    flex-wrap: wrap;
    margin: 10px 0;
  }}
  .thumb-item {{
    background: #06080D;
    border: 1px solid var(--border-subtle);
    border-radius: 8px;
    padding: 8px;
    width: 170px;
    text-align: center;
  }}
  .thumb-item img {{
    width: 100%;
    height: 105px;
    object-fit: cover;
    border-radius: 5px;
    cursor: zoom-in;
  }}
  .thumb-caption {{
    font-size: 11.5px;
    color: var(--text-secondary);
    margin-top: 5px;
    word-break: break-all;
  }}

  /* Lightbox 全螢幕檢視器 */
  #lightbox {{
    display: none;
    position: fixed;
    inset: 0;
    background: rgba(4, 6, 10, 0.92);
    z-index: 9999;
    align-items: center;
    justify-content: center;
    padding: 24px;
    cursor: zoom-out;
  }}
  #lightbox.open {{ display: flex; }}
  #lightbox img {{
    max-width: 95vw;
    max-height: 92vh;
    border-radius: 10px;
    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.85);
    border: 1px solid var(--border-gold);
  }}
  video {{
    width: 100%;
    border-radius: 8px;
    background: #000;
    border: 1px solid var(--border-subtle);
  }}
</style>
</head>
<body>
  <header class="topbar">
    <div class="brand">🎬 AI 漫劇製片審核中心 · {html.escape(project_dir.name)}</div>
    <nav class="stage-nav">{"".join(nav_pills)}</nav>
  </header>

  <main class="container">
    <section class="hero">
      <div class="hero-eyebrow">STAGE {stage} REVIEW GATE · 強制視覺化審核斷點</div>
      <h1 class="hero-title">{html.escape(meta['name'])}</h1>
      <p class="hero-sub">{html.escape(hero_subtitle)}</p>
      <div class="kpi-grid">{kpi_html}</div>
    </section>

    <section class="gate-banner">
      <h3>🛑 本階段斷點確認清單（請審閱下方內容，確認無誤後告知 Agent「通過」以解鎖下一階段）</h3>
      <div class="chk-grid">{chk_html}</div>
    </section>

    {body_html}
  </main>

  <div id="lightbox" onclick="this.classList.remove('open')">
    <img id="lightbox-img" src="" alt="Full preview">
  </div>
  <script>
    document.querySelectorAll('img').forEach(img => {{
      img.addEventListener('click', e => {{
        e.stopPropagation();
        const lb = document.getElementById('lightbox');
        const lbImg = document.getElementById('lightbox-img');
        lbImg.src = img.src;
        lb.classList.add('open');
      }});
    }});
  </script>
</body>
</html>
"""


# ==============================================================================
# 各階段驗證與 HTML 內容建構器 (Stage 0 ~ Stage 7)
# ==============================================================================

def build_stage_0(project_dir: Path, state: Dict[str, Any]) -> Tuple[bool, List[str], str]:
    errors: List[str] = []
    proj_md = project_dir / "project.md"
    if not proj_md.exists():
        return False, ["缺少 project.md，請先執行 init_project.py"], ""
    text = proj_md.read_text(encoding="utf-8")
    if "<①" in text or "<原著對白字數" in text:
        errors.append("project.md 中的「台詞政策」或「原文體量反推試算」仍為未填寫的模板佔位符！")

    kpis = [
        ("當前階段", "Stage 0 定調", "gold"),
        ("project.md 狀態", "已建立" if not errors else "待補齊", "emerald" if not errors else "rose"),
        ("原著目錄", f"{len(list((project_dir / 'source').glob('*')))} 個檔案" if (project_dir / "source").exists() else "無", "cyan"),
    ]
    body = f'<section class="section-panel">{render_markdown_block(text)}</section>'
    checklist = [
        "已確認台詞政策（① 100%保留 / ② 只留重點句 / ③ 改寫影視對白 / ④ 純旁白）",
        "已執行 `estimate_duration.py --novel` 完成原文體量反推片長與集數配置",
        "已鎖定全劇唯一畫風錨點（style_anchor）與畫面比例（aspect_ratio）",
    ]
    html_out = wrap_studio_html(
        project_dir, 0, state,
        "檢視集數、每集目標秒數、台詞政策與原文體量反推公式試算結果。",
        kpis, body, checklist
    )
    return len(errors) == 0, errors, html_out


def build_stage_1(project_dir: Path, state: Dict[str, Any]) -> Tuple[bool, List[str], str]:
    errors: List[str] = []
    char_bible_md = project_dir / "adapt" / "character-bible.md"
    bible_json_path = project_dir / "adapt" / "bible.json"
    source_json_path = project_dir / "adapt" / "source.json"

    if not char_bible_md.exists():
        errors.append(
            "缺少 `adapt/character-bible.md`！在階段 1 劇本改寫前，必須先依原著產出對標《角色設定_v4.md》的完整角色設定文件！"
        )
        return False, errors, ""

    md_text = char_bible_md.read_text(encoding="utf-8")
    bible_json = json.loads(bible_json_path.read_text(encoding="utf-8")) if bible_json_path.exists() else None
    val_res = validate_character_bible(md_text, bible_json)
    if not val_res["passed"]:
        errors.extend(val_res["errors"])

    source_html = ""
    unit_count = 0
    if source_json_path.exists():
        sdata = json.loads(source_json_path.read_text(encoding="utf-8"))
        units = sdata.get("story_units", [])
        unit_count = len(units)
        rows = ["| 單元 ID | 原著事件摘要 | 保留分級 |", "|---|---|---|"]
        for u in units:
            rows.append(f"| `{u.get('unit_id', '')}` | {u.get('summary', '')} | **{u.get('expected_grade', '')}** |")
        source_html = (
            '<section class="section-panel">'
            '<h2 class="studio-h2">🗺️ 原著事件拆解與保留分級表 (adapt/source.json)</h2>'
            f'{md_table_to_html(rows)}'
            '</section>'
        )

    kpis = [
        ("角色設定深層審查", "PASS" if val_res["passed"] else "FAIL", "emerald" if val_res["passed"] else "rose"),
        ("核心與重要配角數", f"{val_res['character_count']} 位", "gold"),
        ("原著事件單元數", f"{unit_count} 個單元", "cyan"),
    ]
    body = (
        f'<section class="section-panel">{render_markdown_block(md_text)}</section>'
        f'{source_html}'
    )
    checklist = [
        "《完整角色設定文件 v4.0》已包含全部 11 大章節，且每位角色皆有表深層性格、能力、弧光、金句與原著 `(Lxxx)` 行號依據",
        "已跨章節查證所有登場角色的真實中文姓名（如瑪蓮、奇雅、賴一心），無自創英文代號或張冠李戴",
        "每位角色的「視覺與服裝狀態機」已明確區分不同日夜/場次的服裝設定圖路徑",
        "原著事件保留分級與分集架構已確認無誤",
    ]
    html_out = wrap_studio_html(
        project_dir, 1, state,
        "完整呈現《角色設定文件 v4.0》十一大章節、跨章節真名查證依據、服裝狀態機與故事地圖。",
        kpis, body, checklist
    )
    return len(errors) == 0, errors, html_out


def build_stage_2(project_dir: Path, state: Dict[str, Any]) -> Tuple[bool, List[str], str]:
    """階段 2：將階段 1 的詳細角色設定表格與階段 2 產出的角色/異獸/場景圖片左右並排展示！"""
    errors: List[str] = []
    char_bible_md = project_dir / "adapt" / "character-bible.md"
    bible_json_path = project_dir / "adapt" / "bible.json"
    assets_md_path = project_dir / "assets.md"

    if not assets_md_path.exists():
        errors.append("缺少 `assets.md` 資產聖經檔案！")

    char_blocks: Dict[str, str] = {}
    if char_bible_md.exists():
        char_blocks = parse_character_blocks(char_bible_md.read_text(encoding="utf-8"))
    else:
        errors.append("缺少 `adapt/character-bible.md`，無法將角色設定表與產出圖片並排對照！")

    bible_json = json.loads(bible_json_path.read_text(encoding="utf-8")) if bible_json_path.exists() else {}
    chars = bible_json.get("characters", [])
    locs = bible_json.get("locations", [])

    cards_html: List[str] = []
    total_imgs_found = 0
    missing_assets: List[str] = []

    # 1. 角色與異獸並排卡片
    for ch in chars:
        cid = ch.get("character_id") or ch.get("id") or ""
        cname = ch.get("canonical_name") or ch.get("name") or cid
        role = ch.get("role", "planet")
        aliases = "、".join(ch.get("aliases", []))

        # 從 character-bible.md 取得該角色的完整 Markdown 設定區塊
        spec_md = char_blocks.get(cname, "")
        if not spec_md:
            # 退回顯示 bible.json 欄位表格
            rows = [
                "| 項目 | 內容 |",
                "|---|---|",
                f"| 角色 ID | `{cid}` |",
                f"| 標準劇本名 | **{cname}** |",
                f"| 別名／原著稱謂 | {aliases or '無'} |",
                f"| 定位 | `{role}` |",
                f"| 外貌描述 | {ch.get('appearance_zh') or ch.get('description') or ch.get('visual_prompt_en') or '未填'} |",
            ]
            spec_md = "\n".join(rows)

        # 收集該角色所有關聯圖片（預設 reference_image + wardrobe_states + character-bible.md 內標註的 images/*.png）
        img_candidates: List[Tuple[str, str]] = []
        primary_img = ch.get("reference_image") or ch.get("image_path") or ""
        if primary_img:
            img_candidates.append(("主設定圖", primary_img))
        for ws in ch.get("wardrobe_states", []):
            if isinstance(ws, dict) and ws.get("image_path"):
                img_candidates.append((ws.get("label") or ws.get("wardrobe_id") or "服裝變體", ws["image_path"]))
        for m_img in re.findall(r"images/[A-Za-z0-9_.-]+\.png", spec_md):
            if all(m_img != p for _, p in img_candidates):
                img_candidates.append(("設定圖／服裝狀態", m_img))

        if not img_candidates:
            img_candidates.append(("預設路徑", f"images/{cid}.png"))

        visual_boxes: List[str] = []
        for label, raw_p in img_candidates:
            src_rel, real_p = rel_img_src(project_dir, raw_p)
            if real_p and real_p.exists():
                total_imgs_found += 1
                dims = get_png_dimensions(real_p)
                dim_str = f"{dims[0]}×{dims[1]} px" if dims else "PNG"
                size_kb = real_p.stat().st_size // 1024
                visual_boxes.append(
                    f'<div class="asset-img-box">'
                    f'  <img src="{src_rel}" alt="{html.escape(cname)}">'
                    f'  <div class="asset-meta-bar">'
                    f'    <span class="tag-badge gold">{html.escape(label)}</span>'
                    f'    <code>{html.escape(raw_p)}</code>'
                    f'    <span class="tag-badge emerald">{dim_str} · {size_kb} KB</span>'
                    f'  </div>'
                    f'</div>'
                )
            else:
                missing_assets.append(f"{cname} ({raw_p})")
                visual_boxes.append(
                    f'<div class="missing-box">'
                    f'  ❌ 缺漏設定圖：{html.escape(cname)}<br>'
                    f'  <code>{html.escape(raw_p)}</code> 尚未生成！'
                    f'</div>'
                )

        cards_html.append(
            f'<article class="sbs-card">'
            f'  <div class="sbs-header">'
            f'    <h3 class="sbs-title">👤 {html.escape(cname)} <span class="tag-badge">{html.escape(cid)}</span></h3>'
            f'    <div><span class="tag-badge gold">定位：{html.escape(role)}</span></div>'
            f'  </div>'
            f'  <div class="sbs-body">'
            f'    <div class="sbs-spec">{render_markdown_block(spec_md)}</div>'
            f'    <div class="sbs-visual">{"".join(visual_boxes)}</div>'
            f'  </div>'
            f'</article>'
        )

    # 2. 場景母版圖並排卡片
    for loc in locs:
        lid = loc.get("location_id") or loc.get("id") or ""
        lname = loc.get("name") or lid
        l_img = loc.get("reference_image") or loc.get("image_path") or f"images/{lid}.png"
        src_rel, real_p = rel_img_src(project_dir, l_img)
        loc_rows = [
            "| 項目 | 內容 |",
            "|---|---|",
            f"| 場景 ID | `{lid}` |",
            f"| 標準場景名 | **{lname}** |",
            f"| 空間與光影設定 | {loc.get('description') or loc.get('visual_prompt_en') or '無'} |",
            f"| 綁定圖檔路徑 | `{l_img}` |",
        ]
        if real_p and real_p.exists():
            total_imgs_found += 1
            dims = get_png_dimensions(real_p)
            dim_str = f"{dims[0]}×{dims[1]} px" if dims else "PNG"
            v_html = (
                f'<div class="asset-img-box">'
                f'  <img src="{src_rel}" alt="{html.escape(lname)}">'
                f'  <div class="asset-meta-bar">'
                f'    <span class="tag-badge">場景母版圖</span>'
                f'    <code>{html.escape(l_img)}</code>'
                f'    <span class="tag-badge emerald">{dim_str}</span>'
                f'  </div>'
                f'</div>'
            )
        else:
            missing_assets.append(f"場景 {lname} ({l_img})")
            v_html = f'<div class="missing-box">❌ 缺漏場景母版圖：{html.escape(lname)} (`{html.escape(l_img)}`)</div>'

        cards_html.append(
            f'<article class="sbs-card">'
            f'  <div class="sbs-header">'
            f'    <h3 class="sbs-title">🏛️ 場景：{html.escape(lname)} <span class="tag-badge">{html.escape(lid)}</span></h3>'
            f'  </div>'
            f'  <div class="sbs-body">'
            f'    <div class="sbs-spec">{md_table_to_html(loc_rows)}</div>'
            f'    <div class="sbs-visual">{v_html}</div>'
            f'  </div>'
            f'</article>'
        )

    if missing_assets:
        errors.append(f"[階段 2 缺圖阻斷] 共有 {len(missing_assets)} 項核心資產圖片尚未生成或路徑不存在：{', '.join(missing_assets)}")

    kpis = [
        ("角色／異獸設定卡", f"{len(chars)} 組", "gold"),
        ("場景母版設定卡", f"{len(locs)} 組", "cyan"),
        ("實體圖片核驗", f"已就緒 {total_imgs_found} 張" if not missing_assets else f"缺漏 {len(missing_assets)} 張", "emerald" if not missing_assets else "rose"),
    ]
    body = f'<div class="side-by-side-list">{"".join(cards_html)}</div>'
    checklist = [
        "每一張角色圖片均已與左側《角色設定文件》之外貌、年齡、體型、服裝、武器形制（如單刃砍刀 vs 雙刃劍、銀槍三節棍、白色長背包）逐項並排核對無誤",
        "無任何角色漏生（如賴一心、瑪蓮、奇雅等重要配角均已生成）",
        "所有角色圖片畫風 100% 統一（同為使用者指定之生圖工具如 Codex CLI 產出，無皮克斯卡通臉或異質畫風混入）",
        "異獸／生物設定圖均為純灰／純白單色背景三視圖（Creature Sheet），無帶場景背景防染色",
    ]
    html_out = wrap_studio_html(
        project_dir, 2, state,
        "將階段 1 的詳細角色設定表格與階段 2 產出的角色設定板、服裝變體、異獸三視圖與場景主圖左右並排（點擊圖片可全螢幕放大檢視細節）。",
        kpis, body, checklist
    )
    return len(errors) == 0, errors, html_out


def build_stage_3(project_dir: Path, state: Dict[str, Any]) -> Tuple[bool, List[str], str]:
    errors: List[str] = []
    scripts = sorted(project_dir.glob("script-ep*.md"))
    handoffs = sorted(project_dir.glob("handoff-ep*.json"))
    if not scripts or not handoffs:
        return False, ["找不到 `script-ep*.md` 或 `handoff-ep*.json`！"], ""

    sbs_items: List[str] = []
    total_scenes = 0
    for sc_path in scripts:
        ep_tag = sc_path.stem.replace("script-", "")
        ho_path = project_dir / f"handoff-{ep_tag}.json"
        sc_text = sc_path.read_text(encoding="utf-8")
        if "TODO" in sc_text or "<標題>" in sc_text:
            errors.append(f"{sc_path.name} 仍含未完成的 TODO 或 `<標題>` 佔位符！")

        ho_summary_rows = ["| 場號 (`scene_id`) | 地點与日夜 | 出場角色 | 預估秒數 | 台詞句數 | 審核狀態 |", "|---|---|---|---|---|---|"]
        if ho_path.exists():
            ho_data = json.loads(ho_path.read_text(encoding="utf-8"))
            for ep in ho_data.get("episodes", []):
                for s in ep.get("scenes", []):
                    total_scenes += 1
                    sid = s.get("scene_id", "")
                    loc = f"{s.get('setting', {}).get('location', '')} ({s.get('setting', {}).get('time', '')})"
                    ch_list = ", ".join(s.get("characters", []))
                    est = s.get("estimated_duration_seconds", {})
                    est_str = f"{est.get('min', 0)}–{est.get('max', 0)}s" if isinstance(est, dict) else str(est)
                    dlg_cnt = len(s.get("dialogue", []))
                    rev_st = s.get("review_status", "draft")
                    ho_summary_rows.append(f"| `{sid}` | {loc} | {ch_list} | {est_str} | {dlg_cnt} 句 | `{rev_st}` |")

        sbs_items.append(
            f'<article class="sbs-card">'
            f'  <div class="sbs-header">'
            f'    <h3 class="sbs-title">📜 劇本：{html.escape(sc_path.name)}</h3>'
            f'    <span class="tag-badge gold">對應交接檔：{html.escape(ho_path.name)}</span>'
            f'  </div>'
            f'  <div class="sbs-body">'
            f'    <div class="sbs-spec">{render_markdown_block(sc_text)}</div>'
            f'    <div class="sbs-visual">'
            f'      <h4 class="studio-h4">Handoff 場次結構與時長對帳表</h4>'
            f'      {md_table_to_html(ho_summary_rows)}'
            f'    </div>'
            f'  </div>'
            f'</article>'
        )

    kpis = [
        ("分集劇本數", f"{len(scripts)} 集", "gold"),
        ("總場次數", f"{total_scenes} 場", "cyan"),
        ("結構與連戲校驗", "PASS" if not errors else "FAIL", "emerald" if not errors else "rose"),
    ]
    body = f'<div class="side-by-side-list">{"".join(sbs_items)}</div>'
    checklist = [
        "劇本正文採用中文場號制（人物、△ 動作行、對白），無混入攝影機術語",
        "台詞字數符合 4 字/秒預算、單句精簡有力，說話秒數佔比 ≤ 60%",
        "每場出場人物與服裝狀態已與階段 1《角色設定文件》完全對齊",
    ]
    html_out = wrap_studio_html(
        project_dir, 3, state,
        "左右並排檢視各集漫劇劇本正文、場次結構、台詞字數預算與連戲狀態交接表。",
        kpis, body, checklist
    )
    return len(errors) == 0, errors, html_out


def build_stage_4(project_dir: Path, state: Dict[str, Any]) -> Tuple[bool, List[str], str]:
    """階段 4：【必經斷點】強制檢查九宮格分鏡草圖 (`images/grid-*.png`) 並與導演分鏡表左右並排！"""
    errors: List[str] = []
    l2_files = sorted((project_dir / "layer2").glob("layer2-*.json")) if (project_dir / "layer2").exists() else []
    if not l2_files:
        return False, ["找不到任何 `layer2/layer2-*.json` 分鏡檔案！"], ""

    # 強制檢查九宮格構圖檔案是否存在！(防止跳過九宮格直接跑去生影片)
    grid_files = sorted((project_dir / "images").glob("grid-*.png")) if (project_dir / "images").exists() else []
    panel_files = sorted((project_dir / "panels").glob("panel-*.png")) if (project_dir / "panels").exists() else []
    if not grid_files and not panel_files:
        errors.append(
            "❌ [階段 4 九宮格強制門禁阻斷] 找不到任何分鏡九宮格拼版圖 (`images/grid-*.png`) 或單格草圖 (`panels/panel-*.png`)！\n"
            "   👉 嚴禁在生成資產圖後跳過九宮格分鏡確認直接去生影片！請先執行 `qwen_storyboard_grid.py` 產出九宮格草圖。"
        )

    # 執行 validate_storyboard.py 驗證所有 layer2 檔案
    from validate_storyboard import validate_storyboard_data, check_cross_segment_slop  # noqa: E402
    all_l2_data = []
    for p in l2_files:
        d = json.loads(p.read_text(encoding="utf-8"))
        all_l2_data.append((p, d))
        res = validate_storyboard_data(d)
        if not res["passed"]:
            for e in res["errors"]:
                errors.append(f"{p.name}: {e}")

    cross_slop_errors = check_cross_segment_slop([d for _, d in all_l2_data])
    errors.extend(cross_slop_errors)

    # 渲染九宮格總覽區
    grid_gallery_html = ""
    if grid_files:
        g_boxes = []
        for gf in grid_files:
            src_rel, _ = rel_img_src(project_dir, f"images/{gf.name}")
            dims = get_png_dimensions(gf)
            dim_str = f"{dims[0]}×{dims[1]} px" if dims else "PNG"
            g_boxes.append(
                f'<div class="asset-img-box">'
                f'  <img src="{src_rel}" alt="{html.escape(gf.name)}">'
                f'  <div class="asset-meta-bar">'
                f'    <span class="tag-badge gold">九宮格構圖總覽</span>'
                f'    <code>images/{html.escape(gf.name)}</code>'
                f'    <span class="tag-badge emerald">{dim_str}</span>'
                f'  </div>'
                f'</div>'
            )
        grid_gallery_html = (
            '<section class="section-panel">'
            '<h2 class="studio-h2">🎨 階段 4 必經確認：黑白鉛筆分鏡九宮格構圖總覽 (點擊放大檢視走位與滅點)</h2>'
            f'<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(420px,1fr));gap:20px;">{"".join(g_boxes)}</div>'
            '</section>'
        )

    # 逐段並排卡片：左側分鏡表（含動作力學三要素），右側對應單格草圖或九宮格
    seg_cards: List[str] = []
    for p, d in all_l2_data:
        seg_id = d.get("segment_id") or p.stem.replace("layer2-", "")
        scene_id = d.get("scene_id", "")
        meta = d.get("metadata", {})
        dur = meta.get("target_duration_sec", 0)
        lighting = meta.get("lighting_lock_line", "")
        shots = d.get("shots", [])

        shot_rows = [
            "| 鏡號 (`shot_id`) | 秒數 | 景別 / 焦距 / 物距 / 運鏡 | 動作力學三要素（①施力點 ➔ ②傳導路徑 ➔ ③受擊與環境反饋） | 微表情與台詞 |",
            "|---|---|---|---|---|",
        ]
        panel_boxes: List[str] = []
        for sh in shots:
            sh_id = sh.get("shot_id", "")
            sh_dur = sh.get("duration", 0)
            cam = sh.get("camera_optics", {})
            cam_str = f"**{cam.get('shot_size', '')}** · `{cam.get('focal_length', '')}` · `{cam.get('physical_distance', '')}` · `{cam.get('movement', '')}`"
            act = sh.get("action_and_performance", {})
            stages_str = " <br>➔ ".join(act.get("action_stages", []))
            expr = act.get("observable_expression", "")
            dlg = sh.get("dialogue_and_audio", {})
            dlg_str = f"💬 **{dlg.get('speaker', '')}**：「{dlg.get('line_verbatim', '')}」" if dlg.get("has_dialogue") else "🔒 *閉唇無台詞*"
            shot_rows.append(f"| `{sh_id}` | `{sh_dur}s` | {cam_str} | {stages_str} | {expr}<br>{dlg_str} |")

            # 尋找對應單格草圖
            for cand_panel in (
                project_dir / "panels" / f"panel-{seg_id}-{sh_id}.png",
                project_dir / "panels" / f"panel-{sh_id}.png",
            ):
                if cand_panel.exists():
                    src_rel, _ = rel_img_src(project_dir, f"panels/{cand_panel.name}")
                    panel_boxes.append(
                        f'<div class="thumb-item">'
                        f'  <img src="{src_rel}" alt="{html.escape(sh_id)}">'
                        f'  <div class="thumb-caption"><code>{html.escape(sh_id)}</code> ({sh_dur}s)</div>'
                        f'</div>'
                    )
                    break

        # 尋找該段對應的九宮格圖
        seg_grid_html = ""
        for gf in grid_files:
            if seg_id.lower() in gf.stem.lower() or scene_id.lower() in gf.stem.lower() or seg_id.split("-")[0].lower() in gf.stem.lower():
                src_rel, _ = rel_img_src(project_dir, f"images/{gf.name}")
                seg_grid_html = (
                    f'<div class="asset-img-box">'
                    f'  <img src="{src_rel}" alt="{html.escape(gf.name)}">'
                    f'  <div class="asset-meta-bar"><span class="tag-badge gold">對應九宮格</span><code>images/{html.escape(gf.name)}</code></div>'
                    f'</div>'
                )
                break

        right_visual = seg_grid_html
        if panel_boxes:
            right_visual += f'<div class="thumb-strip">{"".join(panel_boxes)}</div>'
        if not right_visual:
            right_visual = '<div class="missing-box">❌ 尚未產出本段九宮格或單格分鏡草圖！</div>'

        seg_cards.append(
            f'<article class="sbs-card">'
            f'  <div class="sbs-header">'
            f'    <h3 class="sbs-title">🎬 分段 `{html.escape(seg_id)}` (場景 `{html.escape(scene_id)}` · {dur}s · {len(shots)} 鏡)</h3>'
            f'    <span class="tag-badge">光影鎖：{html.escape(lighting[:45])}</span>'
            f'  </div>'
            f'  <div class="sbs-body">'
            f'    <div class="sbs-spec">{md_table_to_html(shot_rows)}</div>'
            f'    <div class="sbs-visual">{right_visual}</div>'
            f'  </div>'
            f'</article>'
        )

    kpis = [
        ("分鏡段落數", f"{len(l2_files)} 段", "gold"),
        ("九宮格拼版圖", f"{len(grid_files)} 張 (單格 {len(panel_files)} 張)", "emerald" if (grid_files or panel_files) else "rose"),
        ("防偷懶與物理門禁", "PASS (0 罐頭詞)" if not errors else f"FAIL ({len(errors)} 錯)", "emerald" if not errors else "rose"),
    ]
    body = grid_gallery_html + f'<div class="side-by-side-list">{"".join(seg_cards)}</div>'
    checklist = [
        "已檢視黑白鉛筆九宮格構圖（`images/grid-*.png`），確認每鏡人物站位、景別遠近與動作張力符合預期",
        "無任何單鏡同時塞入「主角＋路人＋道具＋巨獸」四方複雜碰撞（已拆分為慢動作感知特寫 ➔ 90度純粹打擊 ➔ 受擊翻滾）",
        "無任何未掛載參考圖之路人單獨佔據正面特寫／中景主鏡",
        "每鏡動作力學三要素（①施力點 ➔ ②傳導路徑 ➔ ③受擊反饋）具象無罐頭複製貼上",
    ]
    html_out = wrap_studio_html(
        project_dir, 4, state,
        "必經斷點：將 Qwen 鉛筆分鏡九宮格草圖與導演分鏡表（景別、焦距物距、動作力學三要素）並排確認，確認無誤後才可進入提示詞編譯與影片生成。",
        kpis, body, checklist
    )
    return len(errors) == 0, errors, html_out


def build_stage_5(project_dir: Path, state: Dict[str, Any]) -> Tuple[bool, List[str], str]:
    errors: List[str] = []
    seg_files = sorted(project_dir.glob("segments-ep*.json"))
    if not seg_files:
        return False, ["找不到 `segments-ep*.json`，請先完成階段 4 確認後執行 `compile_layer2_to_h3.py`！"], ""

    from audit_refs_and_segments import audit_refs_and_subjects, lint_h3_prompt, extract_prompt_from_seg  # noqa: E402

    cards: List[str] = []
    total_segs = 0
    for sf in seg_files:
        data = json.loads(sf.read_text(encoding="utf-8"))
        segs = data if isinstance(data, list) else data.get("segments", [data])
        for seg in segs:
            total_segs += 1
            sid = seg.get("segment_id", f"seg-{total_segs}")
            dur = float(seg.get("metadata", {}).get("target_duration_sec", 7.0))
            prompt_str = extract_prompt_from_seg(seg)
            r_res = audit_refs_and_subjects(seg)
            l_res = lint_h3_prompt(prompt_str, nominal_duration=dur)
            if not r_res["passed"]:
                errors.extend(f"{sid}: {e}" for e in r_res["errors"])
            if not l_res["passed"]:
                errors.extend(f"{sid}: {e}" for e in l_res["errors"])

            # 渲染參考圖縮圖列（讓使用者一眼看出有沒有綁錯衣服！）
            thumbs = []
            for idx, ref in enumerate(seg.get("reference_images", []), start=1):
                r_path = ref.get("path", "")
                src_rel, real_p = rel_img_src(project_dir, r_path)
                if real_p and real_p.exists():
                    thumbs.append(
                        f'<div class="thumb-item">'
                        f'  <img src="{src_rel}" alt="Picture {idx}">'
                        f'  <div class="thumb-caption"><strong>&lt;Picture {idx}&gt;</strong> ({html.escape(ref.get("type", ""))})<br><code>{html.escape(r_path)}</code></div>'
                        f'</div>'
                    )
                else:
                    errors.append(f"{sid}: 參考圖不存在 `{r_path}`")
                    thumbs.append(f'<div class="missing-box">❌ 缺圖 &lt;Picture {idx}&gt;<br>{html.escape(r_path)}</div>')

            loras = seg.get("h3_loras", [])
            lora_badges = "".join(
                f'<span class="tag-badge gold">{html.escape(l.get("name", ""))} ({l.get("strength", "")})</span> '
                for l in loras
            ) or '<span class="tag-badge">無外掛 LoRA（純原生運鏡與物理）</span>'

            cards.append(
                f'<article class="sbs-card">'
                f'  <div class="sbs-header">'
                f'    <h3 class="sbs-title">🧾 `{html.escape(sid)}` ({dur}s · 有效 D={l_res["details"].get("effective_duration_sec", dur)}s)</h3>'
                f'    <div>{lora_badges}</div>'
                f'  </div>'
                f'  <div class="sbs-body">'
                f'    <div class="sbs-spec"><pre class="studio-pre"><code>{html.escape(prompt_str)}</code></pre></div>'
                f'    <div class="sbs-visual">'
                f'      <h4 class="studio-h4">實際綁定之參考圖 (&lt;Picture 1..N&gt;)</h4>'
                f'      <div class="thumb-strip">{"".join(thumbs)}</div>'
                f'    </div>'
                f'  </div>'
                f'</article>'
            )

    kpis = [
        ("已編譯分段數", f"{total_segs} 段", "gold"),
        ("17 條 H3 防偷懶自檢", "PASS (0 錯誤)" if not errors else f"FAIL ({len(errors)} 錯)", "emerald" if not errors else "rose"),
    ]
    body = f'<div class="side-by-side-list">{"".join(cards)}</div>'
    checklist = [
        "已逐段檢查右側 `<Picture 1..N>` 縮圖，確認角色服裝（如夜間便服 vs 日間制服）與該場次時空 100% 吻合",
        "已確認 `detailed_description` 完整保留動作力學三要素與物理反饋，無重複貼上 `as the camera holds a static shot` 等罐頭句",
        "已確認外掛 LoRA 合理（非人異獸或砸鐵凳未誤掛刀劍/拳腳人形 LoRA）",
    ]
    html_out = wrap_studio_html(
        project_dir, 5, state,
        "在送出 FreeVideo 生片前，並排核對每段的 H3 六段式提示詞、實際綁定的參考圖縮圖（防穿錯衣服）與 LoRA 掛載清單。",
        kpis, body, checklist
    )
    return len(errors) == 0, errors, html_out


def build_stage_6(project_dir: Path, state: Dict[str, Any]) -> Tuple[bool, List[str], str]:
    errors: List[str] = []
    videos = sorted((project_dir / "videos").glob("*.mp4")) if (project_dir / "videos").exists() else []
    if not videos:
        return False, ["`videos/` 目錄下尚無任何生成的 `.mp4` 影片檔案！"], ""

    qa_path = project_dir / "videos" / "qa-report.json"
    qa_map: Dict[str, Any] = {}
    if qa_path.exists():
        qdata = json.loads(qa_path.read_text(encoding="utf-8"))
        for item in qdata.get("results", []):
            qa_map[Path(item.get("video", "")).stem] = item

    cards: List[str] = []
    for vp in videos:
        v_rel = f"../videos/{vp.name}"
        q_item = qa_map.get(vp.stem, {})
        q_pass = q_item.get("passed", True)
        cards.append(
            f'<article class="sbs-card">'
            f'  <div class="sbs-header">'
            f'    <h3 class="sbs-title">🎞️ 影片片段：`{html.escape(vp.name)}`</h3>'
            f'    <span class="tag-badge {"emerald" if q_pass else "rose"}">{"QA PASS" if q_pass else "QA FAIL"}</span>'
            f'  </div>'
            f'  <div class="sbs-body">'
            f'    <div class="sbs-spec">'
            f'      <video controls preload="metadata" src="{v_rel}"></video>'
            f'    </div>'
            f'    <div class="sbs-visual">'
            f'      <h4 class="studio-h4">自動品質審查數據 (verify_video_shot.py)</h4>'
            f'      <pre class="studio-pre"><code>{html.escape(json.dumps(q_item, ensure_ascii=False, indent=2) if q_item else "尚未執行 verify_video_shot.py")}</code></pre>'
            f'    </div>'
            f'  </div>'
            f'</article>'
        )

    kpis = [
        ("已生成影片片段", f"{len(videos)} 支", "gold"),
        ("QA 報告狀態", "已產出" if qa_path.exists() else "待執行", "emerald" if qa_path.exists() else "cyan"),
    ]
    body = f'<div class="side-by-side-list">{"".join(cards)}</div>'
    checklist = [
        "已逐支播放影片，確認無道具懸空吸附穿模、無角色衣服染色、無怪獸布偶化",
        "人物臉部五官與階段 2 設定圖一致，動作打擊感與時間減速節奏符合原著戲劇張力",
    ]
    html_out = wrap_studio_html(
        project_dir, 6, state,
        "直接於瀏覽器內播放生成的各段影片，並對照自動品質審查指標。",
        kpis, body, checklist
    )
    return len(errors) == 0, errors, html_out


def build_stage_7(project_dir: Path, state: Dict[str, Any]) -> Tuple[bool, List[str], str]:
    errors: List[str] = []
    finals = sorted((project_dir / "final").glob("*.mp4")) if (project_dir / "final").exists() else []
    if not finals:
        return False, ["`final/` 目錄下尚無最終組裝成片 `.mp4`！請先執行 `assemble_episode.py`。"], ""

    v_cards = []
    for fp in finals:
        v_rel = f"../final/{fp.name}"
        v_cards.append(
            f'<section class="section-panel">'
            f'  <h2 class="studio-h2">🏆 最終交付成片：`{html.escape(fp.name)}`</h2>'
            f'  <video controls preload="metadata" src="{v_rel}"></video>'
            f'</section>'
        )

    kpis = [
        ("最終交付成片", f"{len(finals)} 部", "gold"),
        ("全流程狀態", "7 階段全部完成", "emerald"),
    ]
    body = "".join(v_cards)
    checklist = [
        "已完成配音分層混音、高對比中文字幕燒錄與無縫拼接",
        "全片視聽節奏、角色一致性與字幕時間軸驗收通過",
    ]
    html_out = wrap_studio_html(
        project_dir, 7, state,
        "最終成片劇院放映室與全流程交付確認。",
        kpis, body, checklist
    )
    return len(errors) == 0, errors, html_out


STAGE_BUILDERS = {
    0: build_stage_0,
    1: build_stage_1,
    2: build_stage_2,
    3: build_stage_3,
    4: build_stage_4,
    5: build_stage_5,
    6: build_stage_6,
    7: build_stage_7,
}


# ==============================================================================
# 內建自檢 (--self-test)
# ==============================================================================

def run_self_test() -> bool:
    import tempfile
    print("=" * 75)
    print("🧪 啟動 build_stage_review.py 八階段斷點門禁與 HTML 產生器自檢 (--self-test)")
    print("=" * 75)

    with tempfile.TemporaryDirectory() as tmp:
        pdir = Path(tmp)
        (pdir / "source").mkdir()
        (pdir / "adapt").mkdir()
        (pdir / "images").mkdir()
        (pdir / "layer2").mkdir()
        (pdir / "project.md").write_text(
            "# 測試漫劇\n- 台詞政策：② 只留重點句\n- 原文體量反推試算：200字 ÷ 4 × 1.6 = 80s\n",
            encoding="utf-8",
        )

        # 1. 測試跳關攔截：尚未核准 Stage 0 時直接跑 Stage 2 必被攔截
        ok, msg = check_stage_prerequisite(pdir, 2)
        print(f"[Test 1] 未核准前置階段直接跳關攔截: blocked={not ok} (預期: True)")
        if ok:
            print("  ❌ 失敗：未攔截跳關！")
            return False

        # 2. 產出 Stage 0 HTML 並核准
        st = load_project_state(pdir)
        passed0, errs0, html0 = build_stage_0(pdir, st)
        if not passed0 or "STAGE 0 REVIEW GATE" not in html0:
            print("  ❌ Stage 0 生成失敗:", errs0)
            return False
        (pdir / "review").mkdir(exist_ok=True)
        (pdir / "review" / STAGE_META[0]["file"]).write_text(html0, encoding="utf-8")
        st["stages"]["0"]["status"] = "approved"
        save_project_state(pdir, st)
        print("  ✅ Stage 0 HTML 生成與簽核鎖測試通過！")

        # 3. 測試 Stage 4 無九宮格草圖時必被攔截
        (pdir / "layer2" / "layer2-EP01-S01.json").write_text(
            json.dumps({
                "project_id": "test",
                "scene_id": "EP01-S01",
                "segment_id": "EP01-S01",
                "metadata": {"aspect_ratio": "16:9", "target_duration_sec": 6.0, "lighting_lock_line": "冷藍月光"},
                "continuity_handshake": {"mode": "INDEPENDENT_REF2VA"},
                "shots": [
                    {
                        "shot_id": "SH01", "duration": 3.0, "dramatic_beat_type": "Dramatic_Core",
                        "camera_optics": {"shot_size": "CU", "focal_length": "85mm", "physical_distance": "3.5m", "pov_routing": "objective", "movement": "static"},
                        "action_and_performance": {
                            "action_stages": ["①施力點：右手緊握刀柄拇指頂開刀鐔", "②傳導路徑：手腕下壓帶動刀身微震", "③受擊與環境反饋：刀鋒寒光映亮瞳孔"],
                            "observable_expression": "瞳孔微縮，下頜咬緊",
                            "background_idle_life": "窗外夜雨順著玻璃滑落",
                            "micro_physics_tail": "刀穗隨呼吸輕微擺動"
                        },
                        "dialogue_and_audio": {"has_dialogue": False, "lips_closed_lock": True}
                    },
                    {
                        "shot_id": "SH02", "duration": 3.0, "dramatic_beat_type": "Combat_Impact",
                        "camera_optics": {"shot_size": "MS", "focal_length": "35mm", "physical_distance": "1.5m", "pov_routing": "clear_impact_90deg", "movement": "trucks left"},
                        "action_and_performance": {
                            "action_stages": ["①施力點：後腳蹬地碎石飛濺", "②傳導路徑：腰部扭轉帶動長刀水平橫斬", "③受擊與環境反饋：刀鋒劈碎木桌激起木屑氣浪"],
                            "observable_expression": "眉頭緊鎖，目光凌厲",
                            "background_idle_life": "桌面燭火被刀風吹得劇烈搖晃",
                            "micro_physics_tail": "木屑與灰塵在空氣中緩慢飄落"
                        },
                        "dialogue_and_audio": {"has_dialogue": False, "lips_closed_lock": True}
                    }
                ]
            }, ensure_ascii=False),
            encoding="utf-8",
        )
        passed4, errs4, _ = build_stage_4(pdir, st)
        has_grid_err = any("九宮格強制門禁阻斷" in e for e in errs4)
        print(f"[Test 2] Stage 4 缺少九宮格圖 (`images/grid-*.png`) 硬性阻斷測試: blocked={has_grid_err} (預期: True)")
        if not has_grid_err:
            print("  ❌ 未攔截缺少九宮格:", errs4)
            return False
        print("  ✅ 成功攔截跳過九宮格行為！")

    print("\n🎉 build_stage_review.py 自檢 100% 通過！")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="八階段強制斷點狀態機與高設計感 HTML 視覺化審核介面產生器")
    parser.add_argument("--project-dir", type=Path, help="專案根目錄")
    parser.add_argument("--stage", type=int, choices=range(8), help="建構並驗證指定階段 (0..7) 之 HTML 審核頁面")
    parser.add_argument("--approve-stage", type=int, choices=range(8), help="使用者明確確認沒問題後，標記該階段為 approved 解鎖下一關")
    parser.add_argument("--user-note", type=str, default="使用者確認通過", help="搭配 --approve-stage 記錄使用者簽核備註")
    parser.add_argument("--require-approved", type=int, choices=range(8), help="供下游腳本檢查指定前置階段是否已 approved")
    parser.add_argument("--force-unlock-prev", action="store_true", help="遷移舊專案時初始化前置階段狀態")
    parser.add_argument("--self-test", action="store_true", help="執行內建自檢")
    args = parser.parse_args()

    if args.self_test:
        return 0 if run_self_test() else 1

    if not args.project_dir:
        parser.error("請提供 --project-dir 指定專案目錄，或使用 --self-test")

    project_dir = args.project_dir.expanduser().resolve()
    if not project_dir.exists():
        print(f"❌ 錯誤：找不到專案目錄 {project_dir}", file=sys.stderr)
        return 1

    state = load_project_state(project_dir)

    # 1. 下游腳本檢查前置階段是否已通過
    if args.require_approved is not None:
        st_info = state.get("stages", {}).get(str(args.require_approved), {})
        if st_info.get("status") != "approved":
            print(
                f"❌ [階段斷點門禁阻斷] 「{STAGE_META[args.require_approved]['name']}」尚未完成使用者 HTML 審核簽核 "
                f"(當前狀態: `{st_info.get('status', 'locked')}`)！\n"
                f"   請先完成階段 {args.require_approved} 並產出 `review/{STAGE_META[args.require_approved]['file']}` 交由使用者確認。",
                file=sys.stderr,
            )
            return 2
        return 0

    # 2. 使用者確認通過，解鎖下一階段
    if args.approve_stage is not None:
        s_idx = args.approve_stage
        html_file = project_dir / "review" / STAGE_META[s_idx]["file"]
        if not html_file.exists():
            print(
                f"❌ [錯誤] 尚未產生 `review/{STAGE_META[s_idx]['file']}`，無法直接簽核階段 {s_idx}！\n"
                f"   請先執行 `--stage {s_idx}` 產出 HTML 審核頁供使用者檢視。",
                file=sys.stderr,
            )
            return 1
        state["stages"][str(s_idx)]["status"] = "approved"
        state["stages"][str(s_idx)]["approved_at"] = now_iso()
        state["stages"][str(s_idx)]["user_note"] = args.user_note
        if s_idx + 1 in STAGE_META:
            state["current_stage"] = s_idx + 1
            if state["stages"][str(s_idx + 1)]["status"] == "locked":
                state["stages"][str(s_idx + 1)]["status"] = "in_progress"
        save_project_state(project_dir, state)
        print(f"✅ 已記錄使用者簽核：「{STAGE_META[s_idx]['name']}」狀態更新為 `approved`！")
        if s_idx + 1 in STAGE_META:
            print(f"🔓 已解鎖下一階段：「{STAGE_META[s_idx + 1]['name']}」。")
        return 0

    # 3. 建構指定階段之 HTML 審核頁面
    if args.stage is not None:
        s_idx = args.stage
        if args.force_unlock_prev:
            for prev in range(0, s_idx):
                state["stages"][str(prev)]["status"] = "approved"
                state["stages"][str(prev)]["approved_at"] = now_iso()
                state["stages"][str(prev)]["user_note"] = "既有專案遷移解鎖"

        ok_pre, msg_pre = check_stage_prerequisite(project_dir, s_idx)
        if not ok_pre:
            print(msg_pre, file=sys.stderr)
            return 2

        builder = STAGE_BUILDERS[s_idx]
        passed, errors, html_content = builder(project_dir, state)
        if html_content:
            review_dir = project_dir / "review"
            review_dir.mkdir(parents=True, exist_ok=True)
            out_html = review_dir / STAGE_META[s_idx]["file"]
            out_html.write_text(html_content, encoding="utf-8")
            print(f"🎨 已產出高設計感視覺化審核介面: {out_html}")

        if not passed:
            print("\n" + "=" * 75, file=sys.stderr)
            print(f"❌ [{STAGE_META[s_idx]['name']}] 門禁審查未通過，共 {len(errors)} 項問題需修正：", file=sys.stderr)
            for e in errors:
                print(f"  - {e}", file=sys.stderr)
            print("=" * 75, file=sys.stderr)
            return 1

        state["current_stage"] = s_idx
        state["stages"][str(s_idx)]["status"] = "awaiting_user_approval"
        state["stages"][str(s_idx)]["updated_at"] = now_iso()
        save_project_state(project_dir, state)

        out_html = project_dir / "review" / STAGE_META[s_idx]["file"]
        print("\n" + "=" * 75)
        print(f"🛑 【強制斷點已啟動】{STAGE_META[s_idx]['name']}")
        print(f"📄 視覺化 HTML 審核頁已就緒: {out_html.as_uri()}")
        print("👉 請立即將此 HTML 檔案連結呈現給使用者審閱，並【停止呼叫後續階段工具】！")
        print(f"👉 待使用者明確回覆「沒問題／通過」後，再執行 `--approve-stage {s_idx}` 進入下一關。")
        print("=" * 75)
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
