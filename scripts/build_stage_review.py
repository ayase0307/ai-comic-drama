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
from project_state import (
    approve_stage as state_approve_stage,
    load_state as state_load,
    mark_awaiting_review,
    require_approved,
    save_state as state_save,
    stage4_artifacts,
    stage6_errors,
    stage7_errors,
    stage_key,
    stage_validation_errors,
)

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
    return project_dir / "review" / "project-state.json"


def load_project_state(project_dir: Path) -> Dict[str, Any]:
    state = state_load(project_dir)
    for k, meta in STAGE_META.items():
        entry = state["stages"][stage_key(k)]
        entry.setdefault("html_file", f"review/{meta['file']}")
        entry.setdefault("name", meta["name"])
    return state


def save_project_state(project_dir: Path, state: Dict[str, Any]) -> None:
    state_save(project_dir, state)


def check_stage_prerequisite(project_dir: Path, target_stage: int, allow_bypass: bool = False) -> Tuple[bool, str]:
    """檢查進入 target_stage 前，所有前置階段是否皆已取得使用者確認 (approved)。"""
    if allow_bypass or target_stage <= 0:
        return True, "OK"
    state = load_project_state(project_dir)
    ok, detail = require_approved(project_dir, target_stage - 1)
    if not ok:
        prev = next((i for i in range(target_stage) if not require_approved(project_dir, i)[0]), 0)
        st = state.get("stages", {}).get(stage_key(prev), {}).get("status", "locked")
        html_rel = STAGE_META[prev]["file"]
        return (False, f"❌ [階段斷點門禁阻斷] 前置「{STAGE_META[prev]['name']}」無有效核准（狀態 `{st}`）：{detail}\n"
                f"   請重建並審核 `review/{html_rel}`，再由使用者明確核准。")
    return True, "OK"


# ==============================================================================
# Markdown 轉 HTML（表格自動判型：兩欄→規格條目、多欄→資料表／手機卡片）
# ==============================================================================

_EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF\u2600-\u26FF\u2705\u274C\u274E\u2753-\u2757\u23E9-\u23FA\u2B50\u2B55\uFE0F\u200D]"
)


def strip_emoji(text: str) -> str:
    """移除當作圖示使用的 emoji（保留 ➔ ①② 等有語意的符號）。"""
    return re.sub(r"[ \t]{2,}", " ", _EMOJI_RE.sub("", text)).strip() if text else text


def _plain(text: str) -> str:
    """inline markdown → 純文字（給 data-label 屬性用）。"""
    t = re.sub(r"[`*]", "", strip_emoji(text))
    return html.escape(t, quote=True)


def inline_md(text: str) -> str:
    esc = html.escape(strip_emoji(text))
    esc = re.sub(r"`([^`]+)`", r'<code class="inline-code">\1</code>', esc)
    esc = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", esc)
    esc = re.sub(r"(?<![*\w])\*([^*\s][^*]*)\*(?![*\w])", r"<em>\1</em>", esc)
    esc = re.sub(r"(\(L\d+(?:[-–—]\d+)?\)|（L\d+(?:[-–—]\d+)?）)", r'<span class="canon-badge">\1</span>', esc)
    esc = esc.replace("&lt;br&gt;", "<br>")
    return esc


def _kv_html(pairs: List[Tuple[str, str]], caption: str = "") -> str:
    cap = f'<div class="kv-caption">{caption}</div>' if caption else ""
    rows = "".join(f'<div class="kv-row"><dt>{k}</dt><dd>{v}</dd></div>' for k, v in pairs)
    return f'<div class="kv-wrap">{cap}<dl class="kv">{rows}</dl></div>'


_GENERIC_KV_HEAD = re.compile(r"^(項目|欄位|屬性|名稱|key|field|item)", re.I)


def md_table_to_html(lines: List[str]) -> str:
    rows = []
    for ln in lines:
        s = ln.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip().strip("|").split("|")]
        if all(re.fullmatch(r"[:\-]+", c.replace(" ", "")) for c in cells if c):
            continue
        rows.append(cells)
    if not rows:
        return ""
    head, body = rows[0], rows[1:]
    ncol = len(head)

    # 兩欄表 → 規格條目（手機不會被擠成兩條細長欄）
    if ncol == 2 and body:
        caption = ""
        if not _GENERIC_KV_HEAD.match(re.sub(r"[`*]", "", head[0]).strip()):
            caption = f"{inline_md(head[0])}<span>／</span>{inline_md(head[1])}"
        pairs = [(inline_md(r[0]), inline_md(r[1] if len(r) > 1 else "")) for r in body]
        return _kv_html(pairs, caption)

    labels = [_plain(c) for c in head]
    wide = " wide" if ncol >= 6 else ""
    out = [f'<div class="table-wrap" data-cols="{ncol}"><div class="tw-in{wide}"><table class="data-table">']
    out.append("<thead><tr>" + "".join(f'<th scope="col">{inline_md(c)}</th>' for c in head) + "</tr></thead>")
    if body:
        out.append("<tbody>")
        for r in body:
            cells = []
            for idx, c in enumerate(r):
                lab = labels[idx] if idx < len(labels) else ""
                cells.append(f'<td data-label="{lab}"><div class="cv">{inline_md(c)}</div></td>')
            out.append("<tr>" + "".join(cells) + "</tr>")
        out.append("</tbody>")
    out.append("</table></div></div>")
    return "\n".join(out)


_KV_LINE = re.compile(r"^(?P<k>[^：:|`]{1,18}?)\s*[：:]\s*(?P<v>.+)$")


def render_markdown_block(
    md_text: str,
    fold: bool = False,
    toc: Optional[List[Tuple[int, str, str]]] = None,
    id_prefix: str = "sec",
) -> str:
    """將 Markdown 渲染為審核台 HTML。

    fold=True：每個 #### 小節包成可收合區塊（手機預設只展開第一個）。
    toc：傳入 list 會收集 h2/h3 錨點給目錄使用。
    """
    lines = md_text.splitlines()
    tokens: List[Tuple[int, str]] = []  # (heading level 或 0, html)
    i = 0
    hid = 0
    while i < len(lines):
        ln = lines[i]
        stripped = ln.strip()
        if not stripped:
            i += 1
            continue
        if stripped == "---":
            tokens.append((0, '<hr class="rule">'))
            i += 1
            continue
        if stripped.startswith("```"):
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(html.escape(lines[i]))
                i += 1
            i += 1
            tokens.append((0, f'<pre class="code-block"><code>{chr(10).join(code_lines)}</code></pre>'))
            continue
        if stripped.startswith("|"):
            tbl_lines = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                tbl_lines.append(lines[i])
                i += 1
            tokens.append((0, md_table_to_html(tbl_lines)))
            continue
        if stripped.startswith(">"):
            q_lines = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                q_lines.append(inline_md(re.sub(r"^>\s?", "", lines[i].strip())))
                i += 1
            tokens.append((0, f'<blockquote class="quote">{"<br>".join(q_lines)}</blockquote>'))
            continue
        m_h = re.match(r"^(#{1,4})\s+(.*)$", stripped)
        if m_h:
            level = len(m_h.group(1))
            text = m_h.group(2)
            hid += 1
            anchor = f"{id_prefix}-{hid}"
            if toc is not None and level in (2, 3):
                toc.append((level, anchor, re.sub(r"<[^>]+>", "", inline_md(text))))
            tokens.append((level, f'<h{level + 1} class="md-h{level}" id="{anchor}">{inline_md(text)}</h{level + 1}>'))
            i += 1
            continue
        if stripped.startswith(("- ", "* ")):
            items = []
            while i < len(lines) and lines[i].strip().startswith(("- ", "* ")):
                items.append(lines[i].strip()[2:])
                i += 1
            kv = [_KV_LINE.match(t) for t in items]
            if len(items) >= 2 and all(kv):
                tokens.append((0, _kv_html([(inline_md(m.group("k")), inline_md(m.group("v"))) for m in kv])))
            else:
                tokens.append((0, f'<ul class="md-list">{"".join(f"<li>{inline_md(t)}</li>" for t in items)}</ul>'))
            continue
        if re.match(r"^\d+\.\s+", stripped):
            ol_items = []
            while i < len(lines) and re.match(r"^\d+\.\s+", lines[i].strip()):
                ol_items.append(f"<li>{inline_md(re.sub(r'^[0-9]+[.]\s+', '', lines[i].strip()))}</li>")
                i += 1
            tokens.append((0, f'<ol class="md-list">{"".join(ol_items)}</ol>'))
            continue
        tokens.append((0, f'<p class="md-p">{inline_md(stripped)}</p>'))
        i += 1

    if not fold:
        return "\n".join(t for _, t in tokens)

    # 收合：#### 小節 → <details>
    out: List[str] = []
    open_fold = False
    for level, t in tokens:
        if level and level <= 4 and open_fold:
            out.append("</div></details>")
            open_fold = False
        if level == 4:
            title = re.sub(r"^<h5[^>]*>|</h5>$", "", t)
            out.append(f'<details class="fold" open><summary><span>{title}</span>{icon("chevron")}</summary><div class="fold-body">')
            open_fold = True
            continue
        out.append(t)
    if open_fold:
        out.append("</div></details>")
    return "\n".join(out)


def render_screenplay(md_text: str) -> str:
    """漫劇劇本專用排版：場號標頭、改編註記、人物行、△ 動作行、角色對白。"""
    out: List[str] = []
    notes: List[str] = []
    open_scene = False

    def flush_notes() -> None:
        if notes:
            out.append('<div class="sp-notes">' + "".join(notes) + "</div>")
            notes.clear()

    for raw in md_text.splitlines():
        ln = raw.strip()
        if not ln:
            continue
        m_c = re.fullmatch(r"<!--\s*(\w+)\s*:\s*(.*?)\s*-->", ln)
        if m_c:
            k, v = m_c.group(1), m_c.group(2).strip('"')
            lab = {"source": "原著單元", "must_keep": "必留", "change": "改編"}.get(k, k)
            if k == "must_keep":
                if v.lower() == "true":
                    notes.append('<span class="sp-note keep">必留場</span>')
                continue
            notes.append(f'<span class="sp-note"><b>{html.escape(lab)}</b>{inline_md(v)}</span>')
            continue
        if ln.startswith("<!--"):
            continue
        flush_notes() if not re.match(r"^\d+-\d+\s", ln) else None
        if re.match(r"^#{1,3}\s", ln) or (re.search(r"第\s*\d+\s*集", ln) and len(ln) < 40 and not out):
            out.append(f'<h3 class="sp-ep">{inline_md(re.sub(r"^#+\s*", "", ln))}</h3>')
            continue
        m_s = re.match(r"^(\d+-\d+)\s+(.*)$", ln)
        if m_s:
            if open_scene:
                out.append("</section>")
            out.append(f'<section class="sp-scene"><h4 class="sp-slug"><span class="num">{m_s.group(1)}</span>{inline_md(m_s.group(2))}</h4>')
            open_scene = True
            continue
        if ln.startswith("人物："):
            out.append(f'<p class="sp-cast"><b>人物</b>{inline_md(ln[3:])}</p>')
            continue
        if ln.startswith("△"):
            out.append(f'<p class="sp-action">{inline_md(ln[1:])}</p>')
            continue
        m_d = re.match(r"^([^\s：:（(]{1,8})(（[^）]{1,16}）|\([^)]{1,16}\))?[：:]\s*(.+)$", ln)
        if m_d:
            paren = f'<span class="sp-paren">{inline_md(m_d.group(2))}</span>' if m_d.group(2) else ""
            cls = "sp-line vo" if m_d.group(1) in ("旁白", "OS", "VO") else "sp-line"
            out.append(
                f'<div class="{cls}"><span class="sp-who">{inline_md(m_d.group(1))}{paren}</span>'
                f'<span class="sp-say">{inline_md(m_d.group(3))}</span></div>'
            )
            continue
        out.append(f'<p class="md-p">{inline_md(ln)}</p>')
    flush_notes()
    if open_scene:
        out.append("</section>")
    return "\n".join(out)


def render_prompt(prompt: str, pid: str = "") -> str:
    """H3 提示詞：依 `段名:` 拆成分節，標亮 <Picture N>、<Subject N>、[Shot N] 與時間碼，附複製鈕。"""
    sections: List[Tuple[str, List[str]]] = []
    for ln in prompt.splitlines():
        m = re.fullmatch(r"([a-z_]{3,40}):\s*", ln.strip())
        if m:
            sections.append((m.group(1), []))
        else:
            if not sections:
                sections.append(("", []))
            sections[-1][1].append(ln)

    def hl(t: str) -> str:
        e = html.escape(t)
        e = re.sub(r"&lt;(Picture|Subject) (\d+)&gt;", r'<span class="tok ref">&lt;\1 \2&gt;</span>', e)
        e = re.sub(r"\[Shot (\d+)\]", r'<span class="tok shot">Shot \1</span>', e)
        e = re.sub(r"\b(\d{2}:\d{2}\.\d{3})\b", r'<span class="tok tc">\1</span>', e)
        e = re.sub(r"&lt;d&gt;(.*?)&lt;/d&gt;", r'<span class="tok dlg">\1</span>', e)
        return e

    parts = []
    for name, body in sections:
        txt = "\n".join(body).strip("\n")
        if not txt and not name:
            continue
        head = f'<div class="ps-name">{html.escape(name.replace("_", " "))}</div>' if name else ""
        parts.append(f'<div class="ps">{head}<div class="ps-body">{hl(txt)}</div></div>')
    raw = html.escape(prompt, quote=True)
    return (
        f'<div class="prompt-doc">'
        f'<div class="prompt-tools"><span>H3 提示詞</span>'
        f'<button class="btn ghost copy-prompt" type="button" data-copy="{raw}">{icon("copy")}<span class="lab">複製全文</span></button></div>'
        f'{"".join(parts)}</div>'
    )


def toc_html(entries: List[Tuple[int, str, str]], title: str = "目錄") -> str:
    if not entries:
        return ""
    items = "".join(
        f'<li class="toc-l{lv}"><a href="#{a}">{t}</a></li>' for lv, a, t in entries
    )
    return (
        f'<details class="toc" open><summary>{title}{icon("chevron")}</summary>'
        f'<ol>{items}</ol></details>'
    )


# ==============================================================================
# 圖示（自繪 SVG，統一 1.75 線寬）
# ==============================================================================

_ICON_PATHS: Dict[str, str] = {
    "check": '<path d="M5 12.5l4.2 4.2L19 7"/>',
    "lock": '<rect x="5" y="11" width="14" height="9" rx="1.5"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>',
    "clock": '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
    "dot": '<circle cx="12" cy="12" r="3.5" fill="currentColor" stroke="none"/>',
    "alert": '<path d="M12 3.5l9.5 16.5h-19z"/><path d="M12 10v4.5"/><path d="M12 17.2v.3"/>',
    "image": '<rect x="3.5" y="5" width="17" height="14" rx="1.5"/><circle cx="9" cy="10" r="1.6"/><path d="M20.5 16l-5-5-8.5 8"/>',
    "film": '<rect x="3.5" y="4" width="17" height="16" rx="1.5"/><path d="M7.5 4v16M16.5 4v16M3.5 9h4M3.5 15h4M16.5 9h4M16.5 15h4"/>',
    "user": '<circle cx="12" cy="8.5" r="3.8"/><path d="M4.5 20c1.2-3.8 4-5.5 7.5-5.5s6.3 1.7 7.5 5.5"/>',
    "place": '<path d="M12 21s-6.5-6-6.5-11a6.5 6.5 0 0 1 13 0c0 5-6.5 11-6.5 11z"/><circle cx="12" cy="10" r="2.3"/>',
    "script": '<path d="M7 3.5h8l4 4v13H7z"/><path d="M15 3.5v4h4M10 12h6M10 15.5h6M10 8.5h2.5"/>',
    "grid": '<rect x="3.5" y="3.5" width="17" height="17" rx="1"/><path d="M9.2 3.5v17M14.8 3.5v17M3.5 9.2h17M3.5 14.8h17"/>',
    "prompt": '<path d="M4 6.5l5 5.5-5 5.5M11.5 18h8.5"/>',
    "copy": '<rect x="8.5" y="8.5" width="11" height="11" rx="1.5"/><path d="M15.5 8.5V5.5a1.5 1.5 0 0 0-1.5-1.5H5.5A1.5 1.5 0 0 0 4 5.5V14a1.5 1.5 0 0 0 1.5 1.5h3"/>',
    "chevron": '<path d="M6.5 9.5l5.5 5.5 5.5-5.5"/>',
    "arrow": '<path d="M5 12h14M13 6l6 6-6 6"/>',
    "close": '<path d="M6 6l12 12M18 6L6 18"/>',
    "stamp": '<path d="M9 3.5h6v5.5l2.5 3H6.5L9 9z"/><path d="M5 14.5h14v3H5zM6.5 20.5h11"/>',
    "layers": '<path d="M12 3.5l9 5-9 5-9-5z"/><path d="M3 13l9 5 9-5"/>',
}


def icon(name: str, cls: str = "") -> str:
    p = _ICON_PATHS.get(name, _ICON_PATHS["dot"])
    return (
        f'<svg class="ico {cls}" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" '
        f'stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{p}</svg>'
    )


_EMOJI_ICON_MAP = [
    ("👤", "user"), ("🏛️", "place"), ("🏛", "place"), ("📜", "script"), ("🎬", "film"), ("🧾", "prompt"),
    ("🎞️", "film"), ("🎞", "film"), ("🎨", "grid"), ("🗺️", "layers"), ("🗺", "layers"), ("🏆", "film"),
    ("❌", "alert"),
]


def iconize(fragment: str) -> str:
    """把各階段建構器裡殘留的 emoji 圖示換成 SVG，其餘 emoji 移除。"""
    for emo, name in _EMOJI_ICON_MAP:
        fragment = fragment.replace(emo, icon(name))
    # 只移除文字節點裡的 emoji（不碰標籤）
    def _txt(m: "re.Match[str]") -> str:
        t = _EMOJI_RE.sub("", m.group(1))
        t = re.sub(r"`([^`<>]+)`", r'<code class="inline-code">\1</code>', t)
        return ">" + t + "<"
    return re.sub(r">([^<]+)<", _txt, fragment)


def project_title(project_dir: Path) -> str:
    pm = project_dir / "project.md"
    if pm.exists():
        for ln in pm.read_text(encoding="utf-8").splitlines():
            if ln.startswith("# "):
                return ln[2:].strip()
    return project_dir.name


STATUS_LABEL = {
    "approved": ("已核准", "approved"),
    "awaiting_user_approval": ("待審核", "awaiting"),
    "in_progress": ("製作中", "progress"),
    "locked": ("未解鎖", "locked"),
}
TONE_MAP = {"gold": "ink", "emerald": "jade", "rose": "seal", "cyan": "indigo"}


# ==============================================================================
# 審核台設計系統：「場記板 × 墨青」
#   - 外殼：墨青色側欄（手機改為頂部捲動條 + 底部簽核列）
#   - 招牌：每頁頂端的場記板（斜紋拍板 + 手寫楷體欄位），核准時蓋朱印
#   - 圖片一律放在深色看片燈箱上，色彩判讀不被淺色底干擾
# ==============================================================================

STUDIO_FONTS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
    'family=IBM+Plex+Mono:wght@400;500;600&family=LXGW+WenKai+TC:wght@400;700&'
    'family=Noto+Sans+TC:wght@400;500;700;900&display=swap" media="print" onload="this.media=\'all\'">'
)

STUDIO_CSS = r"""
:root{
  --ground:#E8E9E5; --surface:#F8F8F6; --surface-2:#EFF0EC; --sunk:#DFE1DC;
  --ink:#121614; --ink-2:#3F4642; --ink-3:#5B635E; --rule:#CDD0CA; --rule-2:#B7BBB4;
  --shell:#0E2326; --shell-2:#14313A; --shell-ink:#E6ECEA; --shell-ink-2:#9DB0AC; --shell-rule:rgba(230,236,234,.12);
  --jade:#1F6B57; --jade-wash:#D5E5DD;
  --seal:#B42318; --seal-wash:#F4DAD6;
  --amber:#7F5300; --amber-fill:#C8901A; --amber-wash:#F1E2C0;
  --indigo:#2A4D7A; --indigo-wash:#DAE2EE;
  --table:#131513; --table-2:#1C1F1C; --table-ink:#C9CEC9;
  --sans:"Noto Sans TC","PingFang TC","Microsoft JhengHei",system-ui,sans-serif;
  --hand:"LXGW WenKai TC","Kaiti TC","STKaiti","DFKai-SB",var(--sans);
  --mono:"IBM Plex Mono",ui-monospace,"SF Mono",Menlo,Consolas,monospace;
  --rail-w:256px;
  --r:6px;
  --ease:cubic-bezier(.16,1,.3,1);
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%;scroll-behavior:smooth;scroll-padding-top:24px}
body{margin:0;background:var(--ground);color:var(--ink);font:400 15.5px/1.7 var(--sans);
  font-feature-settings:"palt" 0;text-rendering:optimizeLegibility;-webkit-font-smoothing:antialiased}
::selection{background:var(--shell);color:var(--shell-ink)}
:focus-visible{outline:2px solid var(--indigo);outline-offset:2px;border-radius:3px}
a{color:var(--indigo);text-underline-offset:3px;text-decoration-thickness:1px}
*{scrollbar-width:thin;scrollbar-color:var(--rule-2) transparent}
::-webkit-scrollbar{width:10px;height:10px}::-webkit-scrollbar-thumb{background:var(--rule-2);border-radius:10px;border:3px solid var(--ground)}
.ico{flex:none;vertical-align:-3px}
.num,.mono{font-family:var(--mono);font-variant-numeric:tabular-nums}

/* ---------- 外殼 ---------- */
.shell{display:grid;grid-template-columns:var(--rail-w) minmax(0,1fr);min-height:100vh}
.rail{position:sticky;top:0;height:100vh;overflow-y:auto;background:var(--shell);color:var(--shell-ink);
  display:flex;flex-direction:column;padding:22px 0 18px}
.rail-brand{padding:0 22px 18px;border-bottom:1px solid var(--shell-rule)}
.rail-brand .studio{font:500 11.5px/1.4 var(--sans);color:var(--shell-ink-2);letter-spacing:.06em}
.rail-brand .title{font:700 22px/1.25 var(--hand);margin-top:4px;color:#fff;overflow-wrap:anywhere}
.stages{list-style:none;margin:14px 0 0;padding:0 12px;display:flex;flex-direction:column;gap:2px}
.stage-link{display:grid;grid-template-columns:30px 1fr auto;align-items:center;gap:8px;padding:9px 10px;border-radius:var(--r);
  color:var(--shell-ink);text-decoration:none;transition:background .2s var(--ease)}
.stage-link:hover{background:var(--shell-2)}
.stage-link .n{font:500 13px/1 var(--mono);color:var(--shell-ink-2)}
.stage-link .t{font-size:14px;line-height:1.35}
.stage-link .s{font-size:11.5px;color:var(--shell-ink-2);display:inline-flex;align-items:center;gap:3px;white-space:nowrap}
.stage-link.is-locked{color:var(--shell-ink-2);pointer-events:none}
.stage-link.is-locked .t{opacity:.75}
.stage-link.is-current{background:var(--shell-ink);color:var(--shell)}
.stage-link.is-current .n,.stage-link.is-current .s{color:var(--shell)}
.mini-seal{display:inline-grid;place-items:center;width:20px;height:20px;border:1.5px solid #E2675C;color:#F08A80;
  font:700 11px/1 var(--hand);border-radius:3px;transform:rotate(-6deg)}
.stage-link.is-current .mini-seal{border-color:var(--seal);color:var(--seal)}
.rail-foot{margin-top:auto;padding:16px 22px 0;border-top:1px solid var(--shell-rule)}
.gate-mini{display:flex;align-items:center;justify-content:space-between;gap:10px;text-decoration:none;color:var(--shell-ink);
  background:var(--shell-2);padding:12px 14px;border-radius:var(--r);font-size:14px}
.gate-mini:hover{background:#1A3D47}
.gate-mini .count{font:600 15px/1 var(--mono)}
.bar{height:3px;background:var(--shell-rule);border-radius:3px;overflow:hidden;margin-top:10px}
.bar i{display:block;height:100%;width:0;background:var(--amber-fill);transition:width .5s var(--ease)}
.bar.done i{background:#4FB08F}

.main{min-width:0;padding:36px clamp(16px,3.2vw,48px) 120px;max-width:1600px}

/* ---------- 場記板 ---------- */
.slate{background:var(--surface);border:1.5px solid var(--ink);border-radius:var(--r);overflow:hidden;position:relative}
.clapper{height:26px;background:repeating-linear-gradient(-58deg,var(--ink) 0 22px,var(--surface) 22px 44px);border-bottom:1.5px solid var(--ink)}
.slate-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr))}
.cell{padding:10px 16px 12px;border-right:1px solid var(--rule);border-bottom:1px solid var(--rule);min-width:0}
.cell:last-child{border-right:0}
.cell .k{font-size:12px;color:var(--ink-3);letter-spacing:.04em}
.cell .v{font:700 20px/1.3 var(--hand);color:var(--ink);overflow-wrap:anywhere}
.cell .v.num{font:600 18px/1.4 var(--mono)}
.slate-title{padding:22px 18px 8px}
.slate-title h1{padding-right:96px;margin:0;font:900 clamp(26px,3.4vw,40px)/1.18 var(--sans);letter-spacing:-.01em;text-wrap:balance;max-width:28ch}
.slate-title p{margin:10px 0 0;color:var(--ink-2);max-width:72ch;font-size:15px}
.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));border-top:1px solid var(--rule);margin-top:18px}
.metric{padding:12px 18px 14px;border-right:1px solid var(--rule)}
.metric:last-child{border-right:0}
.metric .k{font-size:12.5px;color:var(--ink-3)}
.metric .v{font:700 19px/1.35 var(--sans);display:flex;align-items:center;gap:7px}
.metric .v::before{content:"";width:8px;height:8px;border-radius:2px;background:var(--ink);flex:none}
.metric.jade .v::before{background:var(--jade)} .metric.seal .v::before{background:var(--seal)}
.metric.indigo .v::before{background:var(--indigo)}
.metric.seal .v{color:var(--seal)}
.slate-title{position:relative}
.seal{position:absolute;right:22px;top:16px;width:78px;height:78px;border:3px solid var(--seal);color:var(--seal);border-radius:6px;
  display:grid;place-items:center;font:700 26px/1.05 var(--hand);text-align:center;transform:rotate(-9deg);opacity:.9;
  box-shadow:inset 0 0 0 2px var(--surface),inset 0 0 0 3.5px var(--seal);mix-blend-mode:multiply;letter-spacing:.08em}
.seal small{display:block;white-space:nowrap;font:500 9px/1.2 var(--mono);letter-spacing:0;margin-top:3px}

/* ---------- 問題清單 ---------- */
.issues{margin-top:20px;background:var(--seal-wash);border:1.5px solid var(--seal);border-radius:var(--r);padding:16px 18px}
.issues h2{margin:0 0 8px;font:700 16px/1.4 var(--sans);color:var(--seal);display:flex;align-items:center;gap:8px}
.issues ol{margin:0;padding-left:1.4em;color:#5E1610;font-size:14px}
.issues li+li{margin-top:4px}

/* ---------- 區塊標題 ---------- */
.block{margin-top:40px}
.block-head{display:flex;align-items:baseline;justify-content:space-between;gap:12px;flex-wrap:wrap;
  border-bottom:1.5px solid var(--ink);padding-bottom:8px;margin-bottom:18px}
.block-head h2{margin:0;font:900 22px/1.3 var(--sans);display:flex;align-items:center;gap:9px}
.block-head .aside{font-size:13px;color:var(--ink-3)}
.panel{background:var(--surface);border:1px solid var(--rule);border-radius:var(--r);padding:clamp(16px,2.4vw,30px)}
.section-panel{background:var(--surface);border:1px solid var(--rule);border-radius:var(--r);padding:clamp(16px,2.4vw,30px);margin-top:24px}
.section-panel > .md-h2:first-child,.section-panel > .md-h1:first-child{margin-top:0}

/* ---------- Markdown ---------- */
.md-h1{font:900 26px/1.3 var(--sans);margin:0 0 14px;text-wrap:balance}
.md-h2{font:900 21px/1.35 var(--sans);margin:40px 0 14px;padding-top:14px;border-top:1.5px solid var(--ink);text-wrap:balance}
.md-h3{font:700 18px/1.4 var(--sans);margin:28px 0 10px;color:var(--ink)}
.md-h4{font:700 15px/1.4 var(--sans);margin:22px 0 8px;color:var(--ink-2)}
.md-p{margin:0 0 12px;max-width:75ch}
.md-list{margin:0 0 14px;padding-left:1.3em;max-width:75ch}
.md-list li{margin:3px 0}
.md-list li::marker{color:var(--ink-3)}
.rule{border:0;border-top:1px solid var(--rule);margin:24px 0}
.quote{margin:12px 0 16px;padding:12px 16px;background:var(--surface-2);border-radius:var(--r);color:var(--ink-2);
  font:400 16px/1.75 var(--hand);border:1px solid var(--rule)}
.code-block,.prompt{background:var(--table);color:#DCE3DE;border-radius:var(--r);padding:14px 16px;overflow-x:auto;
  font:400 13px/1.7 var(--mono);margin:10px 0 14px}
.prompt{white-space:pre-wrap;overflow-wrap:anywhere}
.inline-code{font:500 .86em/1 var(--mono);background:var(--surface-2);border:1px solid var(--rule);padding:2px 5px;border-radius:4px;
  color:var(--ink);overflow-wrap:anywhere}
.canon-badge{font:500 11.5px/1 var(--mono);color:var(--jade);background:var(--jade-wash);padding:2px 5px;border-radius:3px;
  margin-left:3px;white-space:nowrap;vertical-align:1px}
strong{font-weight:700}

/* 規格條目（原兩欄表） */
.kv-wrap{margin:10px 0 16px}
.kv-caption{font-size:12.5px;color:var(--ink-3);margin-bottom:6px}
.kv-caption span{margin:0 4px;color:var(--rule-2)}
.kv{margin:0;border-top:1px solid var(--rule)}
.kv-row{display:grid;grid-template-columns:minmax(6.5em,9.5em) 1fr;gap:4px 18px;padding:9px 0;border-bottom:1px solid var(--rule)}
.kv dt{color:var(--ink-3);font-size:13.5px;line-height:1.6}
.kv dd{margin:0;min-width:0;overflow-wrap:anywhere}

/* 資料表 */
.cv{min-width:0;overflow-wrap:anywhere}
.table-wrap{margin:12px 0 18px;overflow-x:auto;container-type:inline-size}
.data-table{width:100%;border-collapse:separate;border-spacing:0;font-size:14px;font-variant-numeric:tabular-nums;
  background:var(--surface);border:1px solid var(--rule);border-radius:var(--r);overflow:hidden}
.data-table th{text-align:left;font:700 12.5px/1.4 var(--sans);color:var(--ink-2);background:var(--surface-2);
  padding:10px 12px;border-bottom:1.5px solid var(--ink);white-space:nowrap;position:sticky;top:0}
.data-table td{padding:10px 12px;border-bottom:1px solid var(--rule);vertical-align:top;line-height:1.6}
.data-table tbody tr:last-child td{border-bottom:0}
.data-table tbody tr:hover td{background:#F1F2EE}
.data-table td:first-child{font-weight:500}


/* 多欄資料表在窄容器自動轉為卡片（手機與桌機窄欄都適用） */
@container (max-width:600px){
.tw-in .data-table,.tw-in .data-table tbody,.tw-in .data-table tr,.tw-in .data-table td{display:block;width:100%}
.tw-in .data-table{border:0;background:transparent;border-radius:0}
.tw-in .data-table thead{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}
.tw-in .data-table tr{background:var(--surface);border:1px solid var(--rule);border-radius:var(--r);margin-bottom:10px;padding:4px 14px}
.tw-in .data-table td{display:grid;grid-template-columns:6.6em 1fr;gap:10px;padding:8px 0;border-bottom:1px solid var(--surface-2)}
.tw-in .data-table td::before{content:attr(data-label);font-size:12.5px;color:var(--ink-3);line-height:1.6}
.tw-in .data-table tr td:last-child{border-bottom:0}
.tw-in .data-table td:first-child{grid-template-columns:1fr;font:700 16px/1.45 var(--sans);border-bottom:1.5px solid var(--ink);padding:10px 0 8px}
.tw-in .data-table td:first-child::before{display:none}
.tw-in .data-table tbody tr:hover td{background:transparent}
}
@container (max-width:900px){
.tw-in.wide .data-table,.tw-in.wide .data-table tbody,.tw-in.wide .data-table tr,.tw-in.wide .data-table td{display:block;width:100%}
.tw-in.wide .data-table{border:0;background:transparent;border-radius:0}
.tw-in.wide .data-table thead{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}
.tw-in.wide .data-table tr{background:var(--surface);border:1px solid var(--rule);border-radius:var(--r);margin-bottom:10px;padding:4px 14px}
.tw-in.wide .data-table td{display:grid;grid-template-columns:6.6em 1fr;gap:10px;padding:8px 0;border-bottom:1px solid var(--surface-2)}
.tw-in.wide .data-table td::before{content:attr(data-label);font-size:12.5px;color:var(--ink-3);line-height:1.6}
.tw-in.wide .data-table tr td:last-child{border-bottom:0}
.tw-in.wide .data-table td:first-child{grid-template-columns:1fr;font:700 16px/1.45 var(--sans);border-bottom:1.5px solid var(--ink);padding:10px 0 8px}
.tw-in.wide .data-table td:first-child::before{display:none}
.tw-in.wide .data-table tbody tr:hover td{background:transparent}
}


/* 劇本排版 */
.screenplay{max-width:none}
.sp-ep{font:900 22px/1.35 var(--sans);margin:0 0 6px}
.sp-scene{padding:18px 0 8px;border-top:1px solid var(--rule)}
.sp-scene:first-of-type{border-top:0}
.sp-slug{display:flex;align-items:baseline;gap:12px;margin:0 0 8px;font:700 17px/1.4 var(--sans)}
.sp-slug .num{font:600 13px/1 var(--mono);color:#fff;background:var(--ink);padding:5px 7px;border-radius:4px}
.sp-notes{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 12px}
.sp-note{font-size:12.5px;line-height:1.5;color:var(--ink-2);background:var(--surface-2);border:1px solid var(--rule);border-radius:4px;padding:3px 8px}
.sp-note b{font-weight:700;margin-right:6px;color:var(--ink-3)}
.sp-note.keep{color:var(--jade);background:var(--jade-wash);border-color:#9CC4B4;font-weight:700}
.sp-cast{margin:0 0 10px;font-size:14px;color:var(--ink-2)}
.sp-cast b{font-weight:700;margin-right:10px;color:var(--ink-3)}
.sp-action{margin:0 0 8px;padding-left:16px;position:relative;color:var(--ink-2);max-width:72ch}
.sp-action::before{content:"△";position:absolute;left:0;top:0;color:var(--ink-3);font-size:11px;line-height:2.4}
.sp-line{display:grid;grid-template-columns:7em 1fr;gap:14px;margin:4px 0 10px;max-width:72ch}
.sp-who{font-weight:700;text-align:right;line-height:1.7}
.sp-paren{display:block;font-weight:400;font-size:12.5px;color:var(--ink-3)}
.sp-say{font:400 17px/1.7 var(--hand)}
.sp-line.vo .sp-who{color:var(--indigo)}
.sp-line.vo .sp-say{color:var(--indigo)}


/* 提示詞 */
.prompt-doc{border:1px solid var(--rule);border-radius:var(--r);background:var(--surface);overflow:hidden}
.prompt-tools{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:8px 8px 8px 14px;background:var(--surface-2);border-bottom:1px solid var(--rule);font-size:13px;color:var(--ink-3)}
.btn.ghost{background:transparent;color:var(--ink);border-color:var(--rule-2);min-height:40px;padding:0 12px;font-size:13.5px}
.btn.ghost:hover{background:var(--surface)}
.btn.ghost.ok{background:var(--jade);border-color:var(--jade);color:#fff}
.ps{padding:12px 14px;border-bottom:1px solid var(--rule)}
.ps:last-child{border-bottom:0}
.ps-name{font:700 12px/1.4 var(--sans);color:var(--ink-3);margin-bottom:4px;letter-spacing:.02em}
.ps-body{font:400 13.5px/1.75 var(--mono);white-space:pre-wrap;overflow-wrap:anywhere;color:var(--ink)}
.tok{border-radius:3px;padding:0 3px}
.tok.ref{background:var(--indigo-wash);color:var(--indigo);font-weight:600}
.tok.shot{background:var(--ink);color:#fff;font-weight:600;padding:1px 6px}
.tok.tc{color:var(--amber);font-weight:600}
.tok.dlg{background:var(--amber-wash);color:#4A3200;font-family:var(--hand);font-size:15px}

/* 收合小節 */
.fold{border-top:1px solid var(--rule)}
.fold:last-of-type{border-bottom:1px solid var(--rule)}
.fold summary{list-style:none;cursor:pointer;display:flex;align-items:center;justify-content:space-between;gap:10px;
  padding:12px 2px;font:700 15px/1.4 var(--sans);min-height:44px}
.fold summary::-webkit-details-marker{display:none}
.fold summary .ico{transition:transform .25s var(--ease);color:var(--ink-3)}
.fold:not([open]) summary .ico{transform:rotate(-90deg)}
.fold-body{padding:0 0 14px}
.fold-body > :first-child{margin-top:0}

/* 目錄 */
.doc-layout{display:grid;grid-template-columns:minmax(0,1fr) 230px;gap:28px;align-items:start}
.doc-layout .toc{position:sticky;top:20px;order:2}
.toc{background:var(--surface);border:1px solid var(--rule);border-radius:var(--r);padding:4px 14px 10px;font-size:13.5px}
.toc summary{list-style:none;cursor:pointer;display:flex;justify-content:space-between;align-items:center;padding:10px 0;font-weight:700;min-height:44px}
.toc summary::-webkit-details-marker{display:none}
.toc ol{list-style:none;margin:0;padding:0;max-height:70vh;overflow:auto}
.toc a{display:block;padding:5px 0;color:var(--ink-2);text-decoration:none;line-height:1.4}
.toc a:hover{color:var(--ink)}
.toc .toc-l3 a{padding-left:14px;color:var(--ink-3);font-size:13px}

/* ---------- 並排審核卡 ---------- */
.side-by-side-list{display:flex;flex-direction:column;gap:28px;margin-top:24px}
.sbs-card{background:var(--surface);border:1px solid var(--rule);border-radius:var(--r);overflow:clip}
.sbs-header{display:flex;align-items:center;justify-content:space-between;gap:10px 16px;flex-wrap:wrap;
  padding:16px 22px;border-bottom:1.5px solid var(--ink)}
.sbs-title{margin:0;font:900 21px/1.35 var(--sans);display:flex;align-items:center;gap:10px;flex-wrap:wrap;min-width:0;overflow-wrap:anywhere}
.sbs-title .ico{width:20px;height:20px;color:var(--ink-3)}
.sbs-title code,.sbs-title .inline-code{font:500 .62em/1 var(--mono)}
.sbs-body{display:grid;grid-template-columns:minmax(0,1.12fr) minmax(0,.88fr);align-items:start}
.sbs-spec{padding:18px 24px 22px;min-width:0}
.sbs-spec > :first-child{margin-top:0}
.sbs-spec > .md-h3:first-child{display:none}
.sbs-visual{position:sticky;top:0;align-self:start;background:var(--table);color:var(--table-ink);padding:18px;
  display:flex;flex-direction:column;gap:16px;max-height:100vh;overflow-y:auto}
.sbs-visual .md-h4,.sbs-visual h4{color:#fff;margin:0;font:700 14px/1.4 var(--sans)}
.sbs-visual .table-wrap{background:var(--surface);color:var(--ink)}
.asset-img-box{margin:0;background:var(--table-2);border-radius:var(--r);overflow:hidden}
.asset-img-box img{display:block;width:100%;height:auto;cursor:zoom-in;background:#0B0C0B}
.asset-meta-bar{display:flex;flex-wrap:wrap;align-items:center;gap:6px 10px;padding:9px 12px;font-size:12px;color:var(--table-ink)}
.asset-meta-bar code{font:400 11.5px/1.4 var(--mono);color:#9AA39C;overflow-wrap:anywhere;flex:1 1 140px}
.missing-box{display:flex;flex-direction:column;align-items:flex-start;gap:6px;padding:18px;border:1.5px dashed #E2675C;border-radius:var(--r);
  color:#F4B4AC;background:rgba(180,35,24,.12);font-weight:500;line-height:1.5}
.missing-box code{font:400 12px/1.4 var(--mono);color:#F7CBC5;overflow-wrap:anywhere}
.main > .missing-box,.section-panel .missing-box{color:var(--seal);background:var(--seal-wash);border-color:var(--seal)}

.tag-badge{display:inline-flex;align-items:center;gap:4px;font:500 12px/1.3 var(--sans);padding:3px 8px;border-radius:4px;
  border:1px solid var(--rule-2);color:var(--ink-2);background:var(--surface-2);white-space:nowrap}
.tag-badge.gold{border-color:#D8B76A;background:var(--amber-wash);color:var(--amber)}
.tag-badge.emerald{border-color:#9CC4B4;background:var(--jade-wash);color:var(--jade)}
.tag-badge.rose{border-color:#E5A79F;background:var(--seal-wash);color:var(--seal)}
.sbs-visual .tag-badge,.asset-meta-bar .tag-badge{background:transparent;border-color:rgba(201,206,201,.3);color:var(--table-ink)}
.sbs-visual .tag-badge.gold{color:#E8C27A;border-color:rgba(232,194,122,.4)}
.sbs-visual .tag-badge.emerald{color:#8FD1B5;border-color:rgba(143,209,181,.4)}
.sbs-visual .tag-badge.rose{color:#F4A39A;border-color:rgba(244,163,154,.45)}

.thumb-strip{display:grid;grid-template-columns:repeat(auto-fill,minmax(132px,1fr));gap:10px}
.thumb-item{background:var(--table-2);border-radius:var(--r);overflow:hidden}
.thumb-item img{display:block;width:100%;aspect-ratio:4/3;object-fit:cover;cursor:zoom-in}
.thumb-caption{padding:6px 8px 8px;font-size:11.5px;line-height:1.45;color:var(--table-ink);overflow-wrap:anywhere}
.thumb-caption code{font:400 10.5px/1.3 var(--mono);color:#9AA39C}
.grid-gallery{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,420px),1fr));gap:16px;background:var(--table);
  padding:16px;border-radius:var(--r)}
video{display:block;width:100%;border-radius:var(--r);background:#000}
.sbs-spec video{max-height:78vh}

/* ---------- 簽核 ---------- */
.gate{margin-top:48px;background:var(--surface);border:1.5px solid var(--ink);border-radius:var(--r);overflow:hidden;position:relative}
.gate-head{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;padding:16px 22px;border-bottom:1px solid var(--rule)}
.gate-head h2{margin:0;font:900 21px/1.35 var(--sans)}
.gate-head .count{font:600 15px/1 var(--mono);color:var(--ink-2)}
.gate .bar{background:var(--sunk);margin:0;height:4px;border-radius:0}
.chk-list{list-style:none;margin:0;padding:6px 22px}
.chk-item{display:grid;grid-template-columns:28px 1fr;gap:10px;align-items:start;padding:13px 0;border-bottom:1px solid var(--rule);cursor:pointer;min-height:44px}
.chk-list li:last-child .chk-item{border-bottom:0}
.chk-item input{appearance:none;-webkit-appearance:none;margin:2px 0 0;width:22px;height:22px;border:1.5px solid var(--ink-2);border-radius:4px;
  display:grid;place-items:center;background:var(--surface);cursor:pointer;transition:background .2s var(--ease)}
.chk-item input::after{content:"";width:11px;height:6px;border-left:2px solid #fff;border-bottom:2px solid #fff;transform:rotate(-45deg) translate(1px,-1px) scale(0);transition:transform .25s var(--ease)}
.chk-item input:checked{background:var(--jade);border-color:var(--jade)}
.chk-item input:checked::after{transform:rotate(-45deg) translate(1px,-1px) scale(1)}
.chk-item input:disabled{cursor:default}
.chk-item span{font-size:15px;line-height:1.65}
.chk-item input:checked + span{color:var(--ink-2)}
.gate-foot{display:flex;align-items:center;justify-content:space-between;gap:12px 18px;flex-wrap:wrap;padding:16px 22px;background:var(--surface-2);border-top:1px solid var(--rule)}
.gate-foot p{margin:0;color:var(--ink-2);font-size:14px;max-width:60ch}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;min-height:44px;padding:0 18px;border-radius:var(--r);
  border:1.5px solid var(--ink);background:var(--ink);color:#fff;font:700 15px/1 var(--sans);cursor:pointer;transition:background .2s var(--ease),transform .15s var(--ease)}
.btn:hover{background:#2A302D}
.btn:active{transform:translateY(1px)}
.btn:disabled{background:transparent;color:var(--ink-3);border-color:var(--rule-2);cursor:not-allowed}
.btn.ok{background:var(--jade);border-color:var(--jade)}
.gate.is-complete .gate-seal,.gate.is-approved .gate-seal{opacity:.92;transform:rotate(-9deg) scale(1)}
.gate-seal{position:absolute;right:20px;top:10px;width:64px;height:64px;border:2.5px solid var(--seal);color:var(--seal);border-radius:5px;
  display:grid;place-items:center;font:700 21px/1.05 var(--hand);text-align:center;opacity:0;transform:rotate(-9deg) scale(1.6);
  transition:opacity .35s var(--ease),transform .45s var(--ease);pointer-events:none;mix-blend-mode:multiply;
  box-shadow:inset 0 0 0 2px var(--surface),inset 0 0 0 3.5px var(--seal)}
.gate-head h2{padding-right:76px}

/* ---------- 手機底部簽核列 ---------- */
.mbar{display:none}

/* ---------- 燈箱 ---------- */
#lightbox{position:fixed;inset:0;z-index:9999;background:rgba(10,11,10,.94);display:none;flex-direction:column;align-items:center;justify-content:center;padding:56px 12px 24px}
#lightbox.open{display:flex}
#lightbox img{max-width:100%;max-height:calc(100vh - 110px);object-fit:contain;border-radius:4px}
#lightbox .cap{margin-top:12px;color:#B9C0BA;font:400 12.5px/1.4 var(--mono);text-align:center;overflow-wrap:anywhere;max-width:90vw}
#lightbox .x{position:absolute;top:10px;right:10px;width:44px;height:44px;border:0;border-radius:50%;background:rgba(255,255,255,.1);color:#fff;
  display:grid;place-items:center;cursor:pointer}

/* ---------- 響應式 ---------- */
@media (max-width:1180px){
  .doc-layout{grid-template-columns:1fr}
  .doc-layout .toc{position:static;order:0}
  .slate-grid{grid-template-columns:repeat(2,minmax(0,1fr))}
  .slate-grid .cell:nth-child(2n){border-right:0}
}
@media (max-width:1024px){
  .sbs-body{grid-template-columns:1fr}
  .sbs-visual{position:static;max-height:none;order:-1}
  .text-first .sbs-visual{order:0}
}
@media (max-width:980px){
  .shell{display:block}
  .rail{position:static;height:auto;padding:14px 0 0;overflow:visible}
  .rail-brand{display:flex;align-items:baseline;gap:10px;padding:0 16px 10px;border:0}
  .rail-brand .title{font-size:19px;margin:0}
  .stages{flex-direction:row;overflow-x:auto;scroll-snap-type:x mandatory;padding:0 12px 12px;margin:0;gap:6px;scrollbar-width:none}
  .stages::-webkit-scrollbar{display:none}
  .stages li{scroll-snap-align:center;flex:none}
  .stage-link{grid-template-columns:auto auto;grid-template-rows:auto auto;gap:0 6px;padding:8px 12px;background:var(--shell-2);min-height:44px}
  .stage-link .n{grid-row:1/3}
  .stage-link .t{font-size:13.5px;white-space:nowrap}
  .stage-link .s{grid-column:2;font-size:11px}
  .rail-foot{display:none}
  .main{padding:18px 14px 110px}
  .mbar{display:flex;position:fixed;left:0;right:0;bottom:0;z-index:50;align-items:center;gap:12px;
    padding:10px 14px calc(10px + env(safe-area-inset-bottom));background:var(--shell);color:var(--shell-ink);
    box-shadow:0 -6px 20px rgba(0,0,0,.18)}
  .mbar .where{flex:1;min-width:0;font-size:13px;line-height:1.35}
  .mbar .where b{display:block;font-size:14.5px;color:#fff;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .mbar .bar{margin-top:6px}
  .mbar a.btn{background:var(--shell-ink);color:var(--shell);border-color:var(--shell-ink);padding:0 14px;font-size:14px;white-space:nowrap}
}
@media (max-width:720px){
  body{font-size:16px}
  .slate-title{padding:18px 14px 4px}
  .slate-title h1{font-size:26px}
  .cell{padding:8px 12px 10px}
  .cell .v{font-size:17px}
  .seal{width:58px;height:58px;font-size:19px;right:12px;top:14px}
  .seal small{display:none}
  .slate-title h1{padding-right:64px}
  .metric:last-child:nth-child(odd){grid-column:1/-1;border-right:0}
  .metrics{grid-template-columns:1fr 1fr}
  .metric{border-bottom:1px solid var(--rule);padding:10px 14px 12px}
  .metric:nth-child(2n){border-right:0}
  .metric .v{font-size:16.5px}
  .sbs-header{padding:14px 14px}
  .sbs-title{font-size:19px}
  .sbs-spec{padding:6px 14px 16px}
  .sbs-visual{padding:12px}
  .section-panel,.panel{padding:16px 14px}
  .md-h2{font-size:19px;margin-top:30px}
  .kv-row{grid-template-columns:1fr;gap:1px}
  .sp-line{grid-template-columns:1fr;gap:0}
  .sp-who{text-align:left;font-size:14px}
  .sp-paren{display:inline;margin-left:6px}
  .kv dt{font-size:12.5px}
  .sbs-visual .data-table tr{background:var(--surface)}
  .sbs-visual:has(> .asset-img-box + .asset-img-box){flex-direction:row;overflow-x:auto;scroll-snap-type:x mandatory;gap:10px}
  .sbs-visual:has(> .asset-img-box + .asset-img-box) > .asset-img-box{flex:0 0 88%;scroll-snap-align:center}
  .thumb-strip{display:flex;overflow-x:auto;scroll-snap-type:x mandatory;gap:10px;padding-bottom:4px}
  .thumb-item{flex:0 0 62%;scroll-snap-align:start}
  .grid-gallery{padding:10px}
  .chk-list{padding:4px 14px}
  .gate-head,.gate-foot{padding:14px}
  .gate-foot .btn{width:100%}
}
@media (prefers-reduced-motion:reduce){*{transition:none!important;scroll-behavior:auto!important}}
@media print{.rail,.mbar{display:none}.shell{display:block}.sbs-visual{position:static;max-height:none}}
"""

STUDIO_JS = r"""
(function(){
  var gate=document.getElementById('gate');
  if(gate){
    var key='acd-review:'+gate.dataset.project+':'+gate.dataset.stage;
    var boxes=[].slice.call(gate.querySelectorAll('input[type=checkbox]'));
    var approved=gate.classList.contains('is-approved');
    var saved={};try{saved=JSON.parse(localStorage.getItem(key)||'{}')}catch(e){}
    boxes.forEach(function(b,i){ if(!approved && saved[i]) b.checked=true; });
    var copyBtn=document.getElementById('copy-reply');
    function sync(){
      var n=boxes.filter(function(b){return b.checked}).length, t=boxes.length, done=n===t;
      document.querySelectorAll('[data-gate-count]').forEach(function(el){el.textContent=n+' / '+t});
      document.querySelectorAll('[data-gate-bar]').forEach(function(el){el.querySelector('i').style.width=(t?n/t*100:0)+'%';el.classList.toggle('done',done)});
      gate.classList.toggle('is-complete',done);
      if(copyBtn){copyBtn.disabled=!done && !approved}
      if(!approved){var s={};boxes.forEach(function(b,i){if(b.checked)s[i]=1});try{localStorage.setItem(key,JSON.stringify(s))}catch(e){}}
    }
    boxes.forEach(function(b){b.addEventListener('change',sync)});
    sync();
    if(copyBtn){copyBtn.addEventListener('click',function(){
      var txt=copyBtn.dataset.reply, lab=copyBtn.querySelector('.lab'), old=lab.textContent;
      function ok(){lab.textContent='已複製，貼給 Agent 即可';copyBtn.classList.add('ok');setTimeout(function(){lab.textContent=old;copyBtn.classList.remove('ok')},2200)}
      if(navigator.clipboard&&window.isSecureContext){navigator.clipboard.writeText(txt).then(ok,fallback)}else{fallback()}
      function fallback(){var ta=document.createElement('textarea');ta.value=txt;document.body.appendChild(ta);ta.select();try{document.execCommand('copy')}catch(e){}ta.remove();ok()}
    })}
  }
  // 手機：收合小節只展開每張卡的第一節
  if(window.matchMedia('(max-width:720px)').matches){
    document.querySelectorAll('.sbs-spec, .doc-body').forEach(function(scope){
      scope.querySelectorAll('details.fold').forEach(function(d,i){ if(i>0) d.removeAttribute('open'); });
    });
    var toc=document.querySelector('details.toc'); if(toc) toc.removeAttribute('open');
  }
  // 目前階段捲到可見
  var cur=document.querySelector('.stage-link.is-current'); if(cur&&cur.scrollIntoView&&window.innerWidth<=980){cur.scrollIntoView({inline:'center',block:'nearest'})}
  document.querySelectorAll('.copy-prompt').forEach(function(b){b.addEventListener('click',function(){
    var lab=b.querySelector('.lab'),old=lab.textContent,t=b.dataset.copy;
    function ok(){lab.textContent='已複製';b.classList.add('ok');setTimeout(function(){lab.textContent=old;b.classList.remove('ok')},1800)}
    if(navigator.clipboard&&window.isSecureContext){navigator.clipboard.writeText(t).then(ok)}else{var ta=document.createElement('textarea');ta.value=t;document.body.appendChild(ta);ta.select();try{document.execCommand('copy')}catch(e){}ta.remove();ok()}
  })});
  // 燈箱
  var lb=document.getElementById('lightbox'), li=lb.querySelector('img'), cap=lb.querySelector('.cap');
  function close(){lb.classList.remove('open');li.removeAttribute('src')}
  document.querySelectorAll('main img').forEach(function(img){
    img.addEventListener('click',function(e){e.stopPropagation();li.src=img.src;cap.textContent=img.alt||'';lb.classList.add('open')});
  });
  lb.addEventListener('click',close);
  document.addEventListener('keydown',function(e){if(e.key==='Escape')close()});
})();
"""



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
    title = project_title(project_dir)
    cur_info = stages_state.get(stage_key(stage), {})
    cur_status = cur_info.get("status", "in_progress")
    is_approved = cur_status == "approved"
    stage_title = meta["name"].split("｜", 1)[-1]

    # 側欄：八階段
    nav_items = []
    for k in range(8):
        st_info = stages_state.get(stage_key(k), {})
        st = st_info.get("status", "locked")
        is_cur = k == stage
        exists = (project_dir / "review" / STAGE_META[k]["file"]).exists() or is_cur
        label, key = STATUS_LABEL.get(st, STATUS_LABEL["locked"])
        if is_cur and st not in ("approved",):
            label, key = STATUS_LABEL["awaiting_user_approval"]
        cls = f"stage-link is-{key}" + (" is-current" if is_cur else "")
        if not exists and not is_cur:
            cls += " is-locked"
        if st == "approved":
            mark = '<span class="mini-seal" title="已核准">核</span>'
        elif key == "awaiting":
            mark = f'<span class="s">{icon("clock")}待審</span>'
        elif key == "progress":
            mark = f'<span class="s">{icon("dot")}製作中</span>'
        else:
            mark = f'<span class="s">{icon("lock")}</span>'
        short = re.sub(r"^\d+\s*", "", STAGE_META[k]["short"])
        href = STAGE_META[k]["file"] if exists else "#"
        aria = ' aria-current="page"' if is_cur else ""
        nav_items.append(
            f'<li><a class="{cls}" href="{href}"{aria}><span class="n">{k:02d}</span>'
            f'<span class="t">{html.escape(short)}</span>{mark}</a></li>'
        )

    # 場記板欄位
    status_txt = "已核准" if is_approved else "待審核"
    updated = (cur_info.get("approved_at") if is_approved else now_iso()) or "—"
    updated = str(updated)[5:16] if len(str(updated)) >= 16 else updated
    slate_cells = [
        ("劇名", html.escape(title), ""),
        ("階段", f"{stage:02d} / 07", "num"),
        ("狀態", status_txt, ""),
        ("核准時間" if is_approved else "產出時間", html.escape(str(updated or "—")), "num"),
    ]
    cells_html = "".join(
        f'<div class="cell"><div class="k">{k}</div><div class="v {c}">{v}</div></div>' for k, v, c in slate_cells
    )
    metrics_html = "".join(
        f'<div class="metric {TONE_MAP.get(tone, "ink")}"><div class="k">{html.escape(strip_emoji(lbl))}</div>'
        f'<div class="v">{html.escape(strip_emoji(val))}</div></div>'
        for lbl, val, tone in kpi_cards
    )
    seal_html = (
        f'<div class="seal" aria-label="已核准">核准<small>{html.escape(str(cur_info.get("approved_at") or "")[:10])}</small></div>'
        if is_approved else ""
    )

    # 簽核清單
    n_items = len(checklist_items)
    chk_html = "".join(
        f'<li><label class="chk-item"><input type="checkbox"{" checked disabled" if is_approved else ""}>'
        f'<span>{inline_md(item)}</span></label></li>'
        for item in checklist_items
    )
    reply = f"階段 {stage} 通過"
    if is_approved:
        note = html.escape(cur_info.get("user_note") or "使用者確認通過")
        foot = (
            f'<p>本階段已於 <span class="num">{html.escape(str(cur_info.get("approved_at") or ""))}</span> 核准：{note}。</p>'
        )
    else:
        foot = (
            f'<p>逐項看完、全部勾選後，把回覆貼給 Agent，它才會解鎖下一階段。勾選只存在這台裝置。</p>'
            f'<button class="btn" id="copy-reply" type="button" data-reply="{html.escape(reply)}" disabled>'
            f'{icon("copy")}<span class="lab">複製回覆「{html.escape(reply)}」</span></button>'
        )
    gate_cls = "gate is-approved" if is_approved else "gate"
    gate_html = (
        f'<section class="{gate_cls}" id="gate" data-project="{html.escape(project_dir.name)}" data-stage="{stage}">'
        f'<div class="gate-seal" aria-hidden="true">{"核准" if is_approved else "可過"}</div>'
        f'<div class="gate-head"><h2>本階段簽核</h2><span class="count" data-gate-count>0 / {n_items}</span></div>'
        f'<div class="bar" data-gate-bar><i></i></div>'
        f'<ol class="chk-list">{chk_html}</ol>'
        f'<div class="gate-foot">{foot}</div>'
        f'</section>'
    )

    body_html = iconize(body_html)

    return f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#0E2326">
<title>{html.escape(stage_title)}｜{html.escape(title)} 審核台</title>
{STUDIO_FONTS}
<style>{STUDIO_CSS}</style>
</head>
<body data-stage="{stage}">
<div class="shell">
  <aside class="rail">
    <div class="rail-brand"><div class="studio">AI 漫劇審核台</div><div class="title">{html.escape(title)}</div></div>
    <ol class="stages">{"".join(nav_items)}</ol>
    <div class="rail-foot">
      <a class="gate-mini" href="#gate"><span>本階段簽核</span><span class="count" data-gate-count>0 / {n_items}</span></a>
      <div class="bar" data-gate-bar><i></i></div>
    </div>
  </aside>

  <main class="main" id="top">
    <header class="slate">
      <div class="clapper" aria-hidden="true"></div>
      <div class="slate-grid">{cells_html}</div>
      <div class="slate-title">
        {seal_html}
        <h1>{html.escape(stage_title)}</h1>
        <p>{html.escape(strip_emoji(hero_subtitle))}</p>
      </div>
      <div class="metrics">{metrics_html}</div>
    </header>
    <!--ISSUES-->
    {body_html}
    {gate_html}
  </main>
</div>

<nav class="mbar" aria-label="簽核進度">
  <div class="where"><b>{stage:02d}　{html.escape(stage_title)}</b><span data-gate-count>0 / {n_items}</span> 項已確認
    <div class="bar" data-gate-bar><i></i></div></div>
  <a class="btn" href="#gate">{"已核准" if is_approved else "去簽核"}</a>
</nav>

<div id="lightbox" role="dialog" aria-modal="true" aria-label="圖片檢視">
  <button class="x" type="button" aria-label="關閉">{icon("close")}</button>
  <img alt=""><div class="cap"></div>
</div>
<script>{STUDIO_JS}</script>
</body>
</html>
"""


def render_issues(errors: List[str]) -> str:
    """門禁未通過時，把問題直接列在頁面上（不再只印在終端機）。"""
    if not errors:
        return ""
    items = "".join(f"<li>{inline_md(strip_emoji(e).replace(chr(10), ' '))}</li>" for e in errors)
    return (
        f'<section class="issues" role="alert"><h2>{icon("alert")}門禁未通過，{len(errors)} 項需要修正</h2>'
        f'<ol>{items}</ol></section>'
    )



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
            '<h2 class="md-h2">🗺️ 原著事件拆解與保留分級表 (adapt/source.json)</h2>'
            f'{md_table_to_html(rows)}'
            '</section>'
        )

    kpis = [
        ("角色設定深層審查", "PASS" if val_res["passed"] else "FAIL", "emerald" if val_res["passed"] else "rose"),
        ("核心與重要配角數", f"{val_res['character_count']} 位", "gold"),
        ("原著事件單元數", f"{unit_count} 個單元", "cyan"),
    ]
    toc_entries: List[Tuple[int, str, str]] = []
    doc_html = render_markdown_block(md_text, fold=True, toc=toc_entries, id_prefix="bible")
    body = (
        f'<div class="doc-layout">{toc_html(toc_entries, "角色設定目錄")}'
        f'<section class="section-panel doc-body">{doc_html}</section></div>'
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
    manifest_path = project_dir / "assets" / "reference-manifest.json"
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("assets"):
            return build_manifest_asset_review(project_dir, state, manifest)
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
            f'    <div class="sbs-spec">{render_markdown_block(spec_md, fold=True, id_prefix="c-" + cid)}</div>'
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


def build_manifest_asset_review(project_dir: Path, state: Dict[str, Any], manifest: dict) -> Tuple[bool, List[str], str]:
    """Use the explicit production image list, including variants, props and optional assets."""
    errors = []
    if not (project_dir / "assets.md").is_file():
        errors.append("缺少 assets.md 資產聖經")
    cards = []
    ready = required = 0
    design_path = project_dir / "assets" / "character-design-v2.json"
    designs = json.loads(design_path.read_text(encoding="utf-8")).get("assets", []) if design_path.is_file() else []
    design_by_path = {item.get("target_path"): item for item in designs}
    for asset in manifest["assets"]:
        raw = asset.get("target_path", "")
        name = asset.get("display_name_zh") or asset.get("entry_id") or asset.get("stable_id") or raw
        needed = asset.get("required", asset.get("priority") != "optional")
        required += bool(needed)
        src, real = rel_img_src(project_dir, raw)
        valid = bool(raw and real and real.is_file() and get_png_dimensions(real))
        if valid:
            ready += 1
            dims = get_png_dimensions(real)
            approval_label = {
                "approved_by_user": "使用者已核准",
                "excluded_from_current_shots": "反向圖延後／本輪不用",
            }.get(asset.get("approval_status"), "已收到／待核准")
            visual = (f'<div class="asset-img-box"><img loading="lazy" src="{src}" alt="{html.escape(name)}">'
                      f'<div class="asset-meta-bar"><code>{html.escape(raw)}</code>'
                      f'<span class="tag-badge">{dims[0]}×{dims[1]} · {approval_label}</span></div></div>')
        else:
            visual = f'<div class="missing-box">{"缺少必需圖" if needed else "可選圖未提供"}：{html.escape(raw)}</div>'
            if needed:
                errors.append(f"缺少必需資產圖片：{raw}")
        source = asset.get("canonical_source_id") or asset.get("source_id") or ""
        requirements = asset.get("requirements") or asset.get("invariants") or []
        notes = asset.get("technical_review_notes") or []
        if isinstance(notes, str):
            notes = [notes]
        spec = (f'<p><strong>{html.escape(str(source))}</strong></p>'
                f'<p>{"必需" if needed else "可選"} · {html.escape(asset.get("review_disposition", "待審"))}</p>'
                + ''.join(f'<p>{html.escape(str(v))}</p>' for v in requirements + notes)
                + f'<p>原文依據：{html.escape(str(asset.get("source_refs", "見角色設定文件")))}</p>'
                + '<details><summary>完整外觀與造型提示</summary><p>'
                + html.escape(asset.get("prompt", asset.get("prompt_en", ""))) + '</p></details>')
        design = design_by_path.get(raw)
        if design:
            spec = md_table_to_html(["| 項目 | 設定 |", "|---|---|",
                                    f"| 原著年齡／外貌／性格 | {design.get('novel_facts_zh', '')} |",
                                    f"| 改編造型 | {design.get('adaptation_design_zh', '')} |",
                                    f"| 服裝狀態 | {design.get('wardrobe_state_id', '')} |",
                                    f"| 原著依據 | {design.get('source_refs', '')} |"])+spec
        cards.append(f'<article class="sbs-card"><div class="sbs-header"><h3 class="sbs-title">{html.escape(name)}</h3></div>'
                     f'<div class="sbs-body"><div class="sbs-spec">{spec}</div><div class="sbs-visual">{visual}</div></div></article>')
    intro = ('<p>圖片存在與人工核准分開記錄。無形體聲音不要求圖片；可選條目不造成缺圖阻斷。'
             '人物、服裝與原著依據另見 <a href="../assets/character-design-v2.md">人物設定</a>。'
             '檢查結論見 <a href="asset-intake-review.html">本批資產驗收</a>。</p>')
    page = wrap_studio_html(project_dir, 2, state, "逐項核對實際收到的角色、服裝、生物、場景與道具圖；點圖放大。",
                           [("圖單條目",str(len(manifest["assets"])),"gold"),("必需圖",str(required),"cyan"),
                            ("實際收到",str(ready),"emerald" if not errors else "rose")],
                           intro+'<div class="side-by-side-list">'+''.join(cards)+'</div>',
                           ["逐圖核對人物身份、外觀、服裝、表情與原著依據", "核對場景多角度幾何與光向，停用不一致角度", "生物與道具形態符合各段需要", "圖像須由使用者明確核准後才鎖定"])
    return not errors, errors, page


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
            f'<article class="sbs-card text-first">'
            f'  <div class="sbs-header">'
            f'    <h3 class="sbs-title">📜 劇本：{html.escape(sc_path.name)}</h3>'
            f'    <span class="tag-badge gold">對應交接檔：{html.escape(ho_path.name)}</span>'
            f'  </div>'
            f'  <div class="sbs-body">'
            f'    <div class="sbs-spec screenplay">{render_screenplay(sc_text)}</div>'
            f'    <div class="sbs-visual">'
            f'      <h4 class="md-h4">Handoff 場次結構與時長對帳表</h4>'
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

    matched_sketches, sketch_errors = stage4_artifacts(project_dir)
    errors.extend(sketch_errors)
    grid_files = [p for p in matched_sketches if p.name.startswith("grid-")]
    panel_files = [p for p in matched_sketches if p.name.startswith("panel-")]

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
            src_rel, _ = rel_img_src(project_dir, gf.relative_to(project_dir).as_posix())
            dims = get_png_dimensions(gf)
            dim_str = f"{dims[0]}×{dims[1]} px" if dims else "PNG"
            g_boxes.append(
                f'<div class="asset-img-box">'
                f'  <img src="{src_rel}" alt="{html.escape(gf.name)}">'
                f'  <div class="asset-meta-bar">'
                f'    <span class="tag-badge gold">九宮格構圖總覽</span>'
                    f'    <code>{html.escape(gf.relative_to(project_dir).as_posix())}</code>'
                f'    <span class="tag-badge emerald">{dim_str}</span>'
                f'  </div>'
                f'</div>'
            )
        grid_gallery_html = (
            '<section class="section-panel">'
            '<h2 class="md-h2">🎨 階段 4 必經確認：黑白鉛筆分鏡九宮格構圖總覽 (點擊放大檢視走位與滅點)</h2>'
            f'<div class="grid-gallery">{"".join(g_boxes)}</div>'
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
                f'    <div class="sbs-spec">{render_prompt(prompt_str, sid)}</div>'
                f'    <div class="sbs-visual">'
                f'      <h4 class="md-h4">實際綁定之參考圖 (&lt;Picture 1..N&gt;)</h4>'
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
    errors: List[str] = stage6_errors(project_dir)
    videos = sorted((project_dir / "videos").glob("*.mp4")) if (project_dir / "videos").exists() else []
    if not videos:
        errors.append("`videos/` 目錄下尚無任何生成的 `.mp4` 影片檔案！")
        return False, errors, ""

    qa_path = project_dir / "videos" / "qa-report.json"
    qa_map: Dict[str, Any] = {}
    if qa_path.exists():
        qdata = json.loads(qa_path.read_text(encoding="utf-8"))
        for item in qdata.get("results", []):
            video_name = item.get("video_file", "")
            if video_name:
                qa_map[Path(video_name).stem] = item
            if item.get("segment_id"):
                qa_map[str(item["segment_id"])] = item

    cards: List[str] = []
    for vp in videos:
        v_rel = f"../videos/{vp.name}"
        q_item = qa_map.get(vp.stem, {})
        q_pass = q_item.get("passed") is True
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
            f'      <h4 class="md-h4">自動品質審查數據 (verify_video_shot.py)</h4>'
            f'      <pre class="prompt"><code>{html.escape(json.dumps(q_item, ensure_ascii=False, indent=2) if q_item else "尚未執行 verify_video_shot.py")}</code></pre>'
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
    errors: List[str] = stage7_errors(project_dir)
    finals = sorted((project_dir / "final").glob("*.mp4")) if (project_dir / "final").exists() else []
    if not finals:
        errors.append("`final/` 目錄下尚無最終組裝成片 `.mp4`！請先執行 `assemble_episode.py`。")
        return False, errors, ""

    v_cards = []
    for fp in finals:
        v_rel = f"../final/{fp.name}"
        v_cards.append(
            f'<section class="section-panel">'
            f'  <h2 class="md-h2">🏆 最終交付成片：`{html.escape(fp.name)}`</h2>'
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

    test_tmp_root = SCRIPTS_DIR.parent / "tmp"
    test_tmp_root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=test_tmp_root) as tmp:
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
        if not passed0 or 'data-stage="0"' not in html0:
            print("  ❌ Stage 0 生成失敗:", errs0)
            return False
        (pdir / "review").mkdir(exist_ok=True)
        (pdir / "review" / STAGE_META[0]["file"]).write_text(html0, encoding="utf-8")
        mark_awaiting_review(pdir, st, 0)
        if not state_approve_stage(pdir, 0, "self-test"):
            print("  ❌ Stage 0 approval snapshot failed")
            return False
        st = load_project_state(pdir)
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
        has_grid_err = any("缺少有效且對應" in e for e in errs4)
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
    parser.add_argument("--force-unlock-prev", action="store_true", help="相容舊 CLI；不會授予核准，使用時明確拒絕並要求逐階段重審")
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
        ok, detail = require_approved(project_dir, args.require_approved)
        st_info = state.get("stages", {}).get(stage_key(args.require_approved), {})
        if not ok:
            print(
                f"❌ [階段斷點門禁阻斷] 「{STAGE_META[args.require_approved]['name']}」尚未完成有效使用者 HTML 審核簽核 "
                f"(當前狀態: `{st_info.get('status', 'locked')}`，{detail})！\n"
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
        if s_idx > 0:
            ok, msg = require_approved(project_dir, s_idx - 1)
            if not ok:
                print(f"❌ 無法簽核：前置階段已失效或未核准：{msg}", file=sys.stderr)
                return 2
        if not state_approve_stage(project_dir, s_idx, args.user_note):
            print("❌ 無法簽核：該階段尚未產生可用審核快照，或審核後輸入/產物已變更；請重建審核頁。", file=sys.stderr)
            return 2
        state = load_project_state(project_dir)
        if s_idx + 1 in STAGE_META:
            state["current_stage"] = s_idx + 1
            if state["stages"][stage_key(s_idx + 1)]["status"] == "locked":
                state["stages"][stage_key(s_idx + 1)]["status"] = "in_progress"
        save_project_state(project_dir, state)
        print(f"✅ 已記錄使用者簽核：「{STAGE_META[s_idx]['name']}」狀態更新為 `approved`！")
        if s_idx + 1 in STAGE_META:
            print(f"🔓 已解鎖下一階段：「{STAGE_META[s_idx + 1]['name']}」。")
        return 0

    # 3. 建構指定階段之 HTML 審核頁面
    if args.stage is not None:
        s_idx = args.stage
        if args.force_unlock_prev:
            print("❌ --force-unlock-prev 不再授予核准。請逐階段產生審核頁並由使用者核准；舊狀態會以 draft 遷移。", file=sys.stderr)
            return 2

        ok_pre, msg_pre = check_stage_prerequisite(project_dir, s_idx)
        if not ok_pre:
            print(msg_pre, file=sys.stderr)
            return 2

        builder = STAGE_BUILDERS[s_idx]
        passed, errors, html_content = builder(project_dir, state)
        if html_content:
            html_content = html_content.replace("<!--ISSUES-->", render_issues(errors if not passed else []))
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

        mark_awaiting_review(project_dir, state, s_idx)

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
