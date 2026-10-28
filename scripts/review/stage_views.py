#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""收件匣的八階段閱讀視圖：每一關用同一個六區塊格式呈現，讓使用者在同一頁讀完再決定。

固定六區塊（references/review-page-spec.md §6）：
  1. 進度列：階段名、狀態（尚未產出／製作中／等你核准／已核准／內容已變更待重審／局部重審）、更新時間
  2. 需要你決定：本階段的決策卡（只放連結到收件匣上方的卡，不重複一份）
  3. 本次成果摘要：最多 3 個帶單位的數字
  4. 成果閱讀區：本階段文件清單（有／沒有、更新時間、連結）；有狀態卡的文件先顯示狀態卡，全文排版後收合（doc_render.py）
  5. 問題與處理：程式門禁檢查結果，最多列 3 條，其餘收合計數
  6. 紀錄與附錄：本階段已決定的事、除錯頁連結

只讀專案檔案與 project_state 的結果，不寫任何狀態；`h3d inbox` 每次重產就是最新內容。
"""
from __future__ import annotations

import html
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import doc_render
import project_state as ps

E = html.escape
TEXT_SUFFIXES = (".md", ".csv", ".txt")
PREVIEW_CAP = 24_000           # 單一文字檔內嵌上限（字元）
PREVIEW_BUDGET = 400_000       # 八個視圖合計內嵌文字上限（字元）
GROUP_AT = 6                   # 同一個 glob 超過這個數量就收成一列「N 個檔」
MAX_ISSUES = 3

# 每關要回答的問題與要讀的文件（glob, 中文名, 這份文件讓你看什麼）
STAGE_GUIDE: List[Tuple[str, List[Tuple[str, str, str]]]] = [
    ("這部作品要做成什麼樣子？", [
        ("project.md", "定調單", "作品方向、成片形式、畫風比例、體量估算"),
        ("decisions.json", "定案紀錄", "你每一個定案與原話")]),
    ("保留了哪些故事？改了哪些地方？", [
        ("adapt/character-bible.md", "角色設定", "外貌、動機、關係、服裝狀態（十一章）"),
        ("adapt/series-outline.md", "段落架構", "故事主線與段落／分集"),
        ("adapt/episode-outline.md", "分集大綱", "每集事件與鉤子"),
        ("adapt/adaptation.md", "改編方案", "A／B／C 方案與取捨"),
        ("adapt/source.json", "原著事件表", "機器讀；事件與保留分級"),
        ("adapt/bible.json", "故事聖經", "機器讀；角色與世界設定")]),
    ("這是不是我想要的角色與世界？", [
        ("assets.md", "資產聖經", "風格錨、角色／場景／道具／音色的固定描述"),
        ("assets/character-design-v2.md", "角色設計稿", "每個角色的設計說明"),
        ("assets/reference-manifest.json", "設定圖清單", "每張圖的版本與自檢結果"),
        ("images/*.png", "設定圖", "角色板、場景、道具、生物"),
        ("images/*.jpg", "設定圖", "角色板、場景、道具、生物")]),
    ("故事順不順？台詞對不對？節奏夠不夠？", [
        ("script-ep*.md", "漫劇劇本", "場號、人物、△動作行、台詞"),
        ("adaptation-diff.md", "改編差異對帳", "每一處刪減、合併、新增的理由與影響"),
        ("handoff-ep*.json", "劇本交接", "機器讀；給分鏡用")]),
    ("觀眾要看懂什麼？畫面做不做得到？", [
        ("storyboard-ep*.md", "分鏡表", "逐鏡意圖、景別、運鏡、台詞"),
        ("layer2/layer2-*.json", "分鏡資料", "機器讀；分鏡唯一真相"),
        ("panels/*.png", "構圖圖", "每鏡的構圖草圖"),
        ("images/grid-*.png", "分鏡總覽圖", "一段一張的九宮格")]),
    ("要送出的是哪個版本？這次改了哪些段？", [
        ("prompts-ep*.md", "提示詞包", "逐段 H3 六段式提示詞"),
        ("segments-ep*.json", "送件分段檔", "機器讀；每段時長、參考圖、提示詞"),
        ("segments-all.json", "全集分段檔", "多集合併的送件檔"),
        ("review/catalog-acks.json", "失敗目錄確認", "你接受過的警告")]),
    ("生成的影片符不符合這一鏡的要求？", [
        ("videos/*.mp4", "影片片段", "每段生成結果"),
        ("videos/qa-report.json", "技術 QA", "時長、色彩、證據等級"),
        ("review/verdicts.json", "逐段結論", "pass／warn／fail 與原因"),
        ("videos/speed-ramps.json", "變速提案", "動態 QA 自動提出的變速清單")]),
    ("這部成片可以交付了嗎？", [
        ("narration-ep*.md", "旁白與字幕稿", "每句旁白、說話者、時間"),
        ("timeline-ep*.csv", "剪輯時間線", "實際剪點"),
        ("final/*.mp4", "成片", "交付影片"),
        ("final/delivery-*.json", "交付清單", "格式、時長、版本")]),
]


def _time(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime).astimezone().strftime("%Y-%m-%d %H:%M")


def _read_text(path: Path) -> Optional[str]:
    try:
        return path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return None


def _segment_count(root: Path) -> int:
    ids = set()
    for path in root.glob("segments-ep*.json"):
        try:
            raw = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            continue
        items = raw if isinstance(raw, list) else raw.get("segments", [])
        ids.update(str(s.get("segment_id") or s.get("id")) for s in items if isinstance(s, dict))
    return len(ids)


def _shot_count(root: Path) -> Tuple[int, int]:
    segments = shots = 0
    for path in (root / "layer2").glob("layer2-*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            continue
        segments += 1
        shots += len(data.get("shots") or [])
    return segments, shots


def summary_facts(root: Path, n: int, counts: Dict[str, Any], decided_here: int) -> List[str]:
    """每關最多 3 個帶單位的數字；沒有資料就不列，不編造。"""
    facts: List[str] = []
    if n == 0 and decided_here:
        facts.append(f"已定案 {decided_here} 項")
    if n == 2:
        images = [p for p in (root / "images").glob("*") if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp")
                  and not p.name.startswith("grid-")]
        if images:
            facts.append(f"設定圖 {len(images)} 張")
    if n == 3:
        scripts = list(root.glob("script-ep*.md"))
        if scripts:
            chars = sum(len(_read_text(p) or "") for p in scripts)
            facts.append(f"劇本 {len(scripts)} 集・約 {chars:,} 字")
    if n == 4:
        segments, shots = _shot_count(root)
        if segments:
            facts.append(f"{segments} 段・{shots} 鏡")
        panels = len(list((root / "panels").glob("*.png")))
        if panels:
            facts.append(f"構圖圖 {panels} 張")
    if n == 5:
        total = _segment_count(root)
        if total:
            facts.append(f"送件分段 {total} 段")
    if n == 6:
        videos = [p for p in (root / "videos").glob("*.mp4") if p.name != "final_assembled.mp4"]
        total = _segment_count(root)
        if videos:
            facts.append(f"影片 {len(videos)}／{total} 段" if total else f"影片 {len(videos)} 段")
        if any(counts.get(k) for k in ("pass", "warn", "fail")):
            facts.append(f"通過 {counts.get('pass', 0)}・附註 {counts.get('warn', 0)}・重跑 {counts.get('fail', 0)}")
    if n == 7:
        finals = list((root / "final").glob("*.mp4"))
        if finals:
            facts.append(f"成片 {len(finals)} 支")
    return facts[:3]


def _docs(root: Path, n: int, rel_link: Callable[[str], str], budget: Dict[str, int]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    seen: set = set()
    for pattern, label, hint in STAGE_GUIDE[n][1]:
        matches = sorted((p for p in root.glob(pattern) if p.is_file() and p not in seen),
                         key=lambda p: p.name.casefold())
        seen.update(matches)
        if not matches:
            if label not in {r["label"] for r in rows}:
                rows.append({"label": label, "hint": hint, "path": pattern, "state": "missing"})
            continue
        rows[:] = [r for r in rows if not (r["label"] == label and r["state"] == "missing")]
        if len(matches) > GROUP_AT:
            newest = max(matches, key=lambda p: p.stat().st_mtime)
            folder = Path(pattern).parent.as_posix()
            rows.append({"label": label, "hint": hint, "path": f"{pattern}（{len(matches)} 個檔）",
                         "state": "ok", "time": _time(newest), "href": rel_link(folder if folder != "." else "")})
            continue
        for path in matches:
            rel = path.relative_to(root).as_posix()
            row = {"label": label, "hint": hint, "path": rel, "state": "ok", "time": _time(path), "href": rel_link(rel)}
            if path.suffix.lower() in TEXT_SUFFIXES:
                text = _read_text(path)
                if text is None:
                    row["state"] = "unreadable"
                elif budget["left"] > 0:
                    clip = text[:min(PREVIEW_CAP, budget["left"])]
                    budget["left"] -= len(clip)
                    row["preview"] = clip
                    row["clipped"] = len(clip) < len(text)
            rows.append(row)
    return rows


def _status(root: Path, n: int, entry: Dict[str, Any], has_docs: bool) -> Tuple[str, str]:
    """回傳（狀態代碼, 中文標籤）。製作狀態與正式核准分開，只信 project_state 的判斷。"""
    status = entry.get("status")
    if n == 5 and status == "approved":
        review = ps.stage5_segment_review(root)
        if review["mode"] == "partial":
            return "partial", f"局部重審：{len(review['pending'])} 段待你重審，{len(review['approved'])} 段仍有效"
        if review["mode"] == "invalid":
            return "stale", "內容已變更，待整份重審"
    if status == "approved":
        return ("approved", "已核准") if ps.is_approved(root, n) else ("stale", "內容已變更，待重審")
    if not has_docs:
        return "empty", "尚未產出"
    if status == "awaiting_user_approval":
        return "awaiting", "等你核准"
    return "working", "製作中"


def _issues(root: Path, n: int, code: str) -> List[str]:
    if code in ("empty", "approved"):
        return []
    try:
        return list(ps.stage_validation_errors(root, n))
    except Exception as exc:  # 門禁本身讀檔失敗也要讓使用者看到，而不是整頁產不出來
        return [f"門禁檢查讀取失敗：{exc}"]


def collect(root: Path, state: Dict[str, Any], cards: List[Dict[str, Any]], decided: List[Dict[str, Any]],
            counts: Dict[str, Any], rel_link: Callable[[str], str]) -> List[Dict[str, Any]]:
    budget = {"left": PREVIEW_BUDGET}
    views = []
    for n in range(8):
        entry = state["stages"][ps.stage_key(n)]
        docs = _docs(root, n, rel_link, budget)
        has_docs = any(d["state"] != "missing" for d in docs)
        try:
            code, label = _status(root, n, entry, has_docs)
        except Exception as exc:
            code, label = "error", f"狀態讀取失敗：{exc}"
        here = [c for c in cards if c["stage"] == n]
        decided_here = [d for d in decided if d.get("stage") == n]
        pages = sorted((root / "review").glob(f"stage-{n}-*.html")) if (root / "review").is_dir() else []
        views.append({
            "n": n, "title": ps.STAGE_TITLES[n], "ask": STAGE_GUIDE[n][0],
            "status": code, "status_label": label, "updated": str(entry.get("updated_at") or entry.get("approved_at") or "")[:16].replace("T", " "),
            "cards": [{"id": c["id"], "title": c["title"], "blocking": c["blocking"],
                       "blocking_label": c.get("blocking_label", "")} for c in here],
            "facts": summary_facts(root, n, counts if n == 6 else {}, len(decided_here)),
            "docs": docs, "issues": _issues(root, n, code),
            "decided": [{"time": d.get("time", ""), "title": d.get("title", ""), "decision": d.get("decision", "")}
                        for d in decided_here],
            "debug_pages": [{"label": p.stem, "href": rel_link(f"review/{p.name}")} for p in pages],
        })
    return views


# ------------------------------------------------------------------ HTML
CSS = """
.svnav{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 14px}
.svnav a{color:var(--mut);text-decoration:none;font-size:14px;padding:4px 11px;border-radius:99px;border:1px solid var(--line);background:var(--panel2)}
.svnav a:hover,.svnav a:focus-visible{color:var(--tx);border-color:var(--acc);outline:none}
.svnav a.s-approved{color:var(--ok);border-color:color-mix(in srgb,var(--ok) 45%,transparent)}.svnav a.s-awaiting,.svnav a.s-partial,.svnav a.s-stale{color:var(--hot);border-color:color-mix(in srgb,var(--hot) 45%,transparent)}
.sv{scroll-margin-top:12px}
.sv>summary .stt{font-size:13px;font-weight:600;padding:1px 9px;border-radius:99px;border:1px solid var(--line);color:var(--mut);white-space:nowrap}
.stt.s-approved{color:var(--ok);border-color:color-mix(in srgb,var(--ok) 45%,transparent)}.stt.s-awaiting,.stt.s-partial,.stt.s-stale,.stt.s-error{color:var(--hot);border-color:color-mix(in srgb,var(--hot) 45%,transparent)}
.svb{padding:0 16px 16px;display:grid;grid-template-columns:minmax(0,1fr);gap:14px}
.svb h4{margin:0 0 6px;font-size:14px;color:var(--dim);font-weight:600;letter-spacing:.06em}
.svq{margin:0;font-size:17px;font-weight:700}
.facts{display:flex;flex-wrap:wrap;gap:8px;margin:0;padding:0;list-style:none}
.facts li{background:var(--panel2);border:1px solid var(--line);border-radius:8px;padding:4px 10px;font-size:14.5px;font-variant-numeric:tabular-nums}
.svcards{margin:0;padding-left:1.2em}.svcards a{color:var(--acc)}
.docs{display:grid;grid-template-columns:minmax(0,1fr);gap:2px}
.doc{border-top:1px solid var(--line);padding:8px 0}
.doc .dh{display:flex;flex-wrap:wrap;gap:4px 12px;align-items:baseline}
.doc b{font-size:15.5px}.doc .dp{font-size:13px;color:var(--dim);word-break:break-all}.doc .dt{font-size:13px;color:var(--dim);font-variant-numeric:tabular-nums}
.doc .di{margin:2px 0 0;font-size:14px;color:var(--mut)}
.doc.missing b{color:var(--dim)}.doc.missing .dt{color:var(--dim);font-style:italic}
.doc details{margin-top:6px}.doc details>summary{cursor:pointer;color:var(--acc);font-size:14px}
.issues{margin:0;padding-left:1.2em;font-size:14.5px;color:var(--hot)}.issues.none{list-style:none;padding:0;color:var(--mut)}
.svrec{margin:0;padding:0;list-style:none;font-size:14px;color:var(--mut)}.svrec li+li{margin-top:2px}
"""


def _doc_html(d: Dict[str, Any], approval: str = "") -> str:
    state = {"ok": "", "missing": "尚未產出", "unreadable": "讀取失敗"}[d["state"]]
    when = d.get("time") or state
    name = (f'<a class="lnk" href="{E(d["href"])}" target="_blank" rel="noopener">{E(d["label"])}</a>'
            if d.get("href") else E(d["label"]))
    body = ""
    if d.get("preview") is not None:
        more = "（只顯示前段，全文請開檔）" if d.get("clipped") else ""
        doc = doc_render.render_document(d["path"], d["preview"], approval)
        body = f'{doc["card"]}<details><summary>閱讀全文{more}</summary>{doc["body"]}</details>'
    return (f'<div class="doc{" missing" if d["state"] != "ok" else ""}"><div class="dh"><b>{name}</b>'
            f'<span class="dp">{E(d["path"])}</span><span class="dt">{E(when)}</span></div>'
            f'<p class="di">{E(d["hint"])}</p>{body}</div>')


def _view_html(v: Dict[str, Any], current: int) -> str:
    cards = "".join(f'<li><a href="#{E(c["id"])}">{E(c["title"])}</a>（{E(c["blocking_label"])}）</li>' for c in v["cards"])
    facts = "".join(f"<li>{E(f)}</li>" for f in v["facts"])
    shown, rest = v["issues"][:MAX_ISSUES], len(v["issues"]) - MAX_ISSUES
    issues = ("".join(f"<li>{E(i)}</li>" for i in shown) + (f"<li>其餘 {rest} 條，見除錯頁</li>" if rest > 0 else "")
              if shown else "")
    rec = "".join(f'<li>{E(d["time"])}・{E(d["title"])}：{E(d["decision"])}</li>' for d in v["decided"][:5])
    debug = "".join(f'<a class="lnk" href="{E(p["href"])}" target="_blank" rel="noopener">{E(p["label"])}（除錯用）</a>'
                    for p in v["debug_pages"])
    updated = f"・更新 {E(v['updated'])}" if v["updated"] else ""
    return f'''
<details class="fold sv" id="stage-{v["n"]}"{" open" if v["n"] == current else ""}>
  <summary><span class="ft">階段 {v["n"]}　{E(v["title"])}<small>{len(v["cards"])} 件待決{updated}</small></span><span class="stt s-{E(v["status"])}">{E(v["status_label"])}</span></summary>
  <div class="svb">
    <p class="svq">{E(v["ask"])}</p>
    <div><h4>需要你決定</h4>{f'<ol class="svcards">{cards}</ol>' if cards else '<p class="empty" style="padding:0">這關沒有待決卡</p>'}</div>
    <div><h4>本次成果摘要</h4>{f'<ul class="facts">{facts}</ul>' if facts else '<p class="empty" style="padding:0">還沒有可統計的成果</p>'}</div>
    <div><h4>成果閱讀區</h4><div class="docs">{"".join(_doc_html(d, v["status"]) for d in v["docs"]) or '<p class="empty" style="padding:0">這關還沒有文件</p>'}</div></div>
    <div><h4>問題與處理</h4>{f'<ul class="issues">{issues}</ul>' if issues else '<ul class="issues none"><li>程式門禁沒有擋這關的問題</li></ul>'}</div>
    <div><h4>紀錄與附錄</h4><ul class="svrec">{rec or "<li>這關還沒有定案或核准紀錄</li>"}</ul>{f'<div class="links">{debug}</div>' if debug else ""}</div>
  </div>
</details>'''


def render(views: List[Dict[str, Any]], current: int) -> str:
    if not views:
        return ""
    nav = "".join(f'<a class="s-{E(v["status"])}" href="#stage-{v["n"]}">{v["n"]} {E(v["title"])}</a>' for v in views)
    return (f'<h2 id="stages">各階段成果<span class="n">每關同一個格式：要回答的問題、待決、摘要、文件、問題、紀錄</span></h2>'
            f'<nav class="svnav" aria-label="階段成果">{nav}</nav>'
            + "".join(_view_html(v, current) for v in views))


JS = """
function openTarget(){if(!location.hash)return;let el;try{el=document.getElementById(decodeURIComponent(location.hash.slice(1)))}catch(_){return}
 if(!el)return;for(let d=el;d;d=d.parentElement){if(d.tagName==='DETAILS')d.open=true}el.scrollIntoView({block:'start'})}
addEventListener('hashchange',openTarget);openTarget();
"""
