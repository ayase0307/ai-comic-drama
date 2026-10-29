#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把階段文件排版成好讀的 HTML（收件匣閱讀視圖用，references/review-page-spec.md §6）。

- 狀態卡（references/document-standard.md）排成卡片放最上面，修訂紀錄收在最後。
- 劇本（script-ep*.md）用劇本版型：場次標題列、△動作行、角色｜台詞兩欄。
- 其他 Markdown 只認常用語法：標題、段落、條列、表格、引言、程式碼、粗體、行內碼、分隔線。
- CSV 排成表格。

安全：一律先跳脫再套樣式，不放任何原始 HTML（文件裡的 <details>、註解只當文字或略過）。
"""
from __future__ import annotations

import csv
import html
import io
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

for extra in (Path(__file__).resolve().parents[1], Path(__file__).resolve().parents[1] / "adapt"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

import doc_card  # noqa: E402
from validate_structure import (CHAR_LINE_RE, DIALOGUE_LINE_RE, EPISODE_HEADER_RE,  # noqa: E402
                                SCENE_HEADER_RE)

E = html.escape
CSV_ROWS = 200
STATUS_CLASS = {"草稿": "draft", "等你核准": "await", "退回修改": "back", "已核准": "ok", "已變更待重審": "stale"}
COMMENT_RE = re.compile(r"^<!--\s*(.*?)\s*-->$")
META_LABEL = {"source": "原著", "must_keep": "必留", "exposition": "交代", "change": "改編"}


def inline(text: str) -> str:
    """行內語法：先跳脫，再把 `碼`、**粗體**、[文字](連結) 換成標籤（連結只留文字，相對路徑在收件匣裡會斷）。"""
    parts = re.split(r"(`[^`]+`)", text)
    out = []
    for part in parts:
        if len(part) > 1 and part.startswith("`") and part.endswith("`"):
            out.append(f"<code>{E(part[1:-1])}</code>")
            continue
        s = E(part)
        s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
        s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)
        s = re.sub(r"&lt;br\s*/?&gt;", "<br>", s, flags=re.I)  # 表格儲存格常用 <br> 換行
        out.append(s)
    return "".join(out)


def _cells(line: str) -> List[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _table(rows: List[List[str]], head: bool = True) -> str:
    if not rows:
        return ""
    thead = "<thead><tr>" + "".join(f"<th>{inline(c)}</th>" for c in rows[0]) + "</tr></thead>" if head else ""
    body = rows[1:] if head else rows
    tbody = "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in body)
    return f'<div class="rtw"><table>{thead}<tbody>{tbody}</tbody></table></div>'


FOLD_RE = re.compile(r"^<(/?)details>$|^<summary>(.*)</summary>$", re.I)


def markdown(text: str) -> str:
    lines = text.splitlines()
    out: List[str] = []
    depth = 0
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        s = line.strip()
        if not s:
            i += 1
            continue
        if s.startswith("```"):
            j = i + 1
            while j < len(lines) and not lines[j].strip().startswith("```"):
                j += 1
            out.append(f"<pre>{E(chr(10).join(lines[i + 1:j]))}</pre>")
            i = j + 1
            continue
        if COMMENT_RE.match(s) or s.startswith("<!--"):
            while i < len(lines) and "-->" not in lines[i]:
                i += 1
            i += 1
            continue
        fold = FOLD_RE.match(s)
        if fold:  # 只放行獨立成行的 <details>／<summary>／</details>（document-standard.md §3 的收合），其餘 HTML 一律跳脫
            if fold.group(2) is not None:
                out.append(f"<summary>{inline(fold.group(2))}</summary>")
            elif fold.group(1):
                if depth:
                    depth -= 1
                    out.append("</details>")
            else:
                depth += 1
                out.append('<details class="rfold">')
            i += 1
            continue
        heading = re.match(r"^(#{1,4})\s+(.*)$", s)
        if heading:
            level = min(len(heading.group(1)) + 1, 5)
            out.append(f"<h{level}>{inline(heading.group(2))}</h{level}>")
            i += 1
            continue
        if re.match(r"^(-{3,}|\*{3,})$", s):
            out.append("<hr>")
            i += 1
            continue
        if s.startswith("|"):
            block = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                block.append(lines[i])
                i += 1
            rows = [_cells(b) for b in block if not re.match(r"^\|?[\s:|-]+\|?$", b.strip())]
            has_sep = len(block) > 1 and re.match(r"^\|?[\s:|-]+\|?$", block[1].strip())
            out.append(_table(rows, head=bool(has_sep)))
            continue
        if s.startswith(">"):
            block = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                block.append(re.sub(r"^\s*>\s?", "", lines[i]))
                i += 1
            out.append(f"<blockquote>{markdown(chr(10).join(block))}</blockquote>")
            continue
        if re.match(r"^([-*+]|\d+[.)])\s+", s):
            ordered = bool(re.match(r"^\d", s))
            items = []
            while i < len(lines) and re.match(r"^\s*([-*+]|\d+[.)])\s+", lines[i]):
                item = re.sub(r"^\s*([-*+]|\d+[.)])\s+", "", lines[i])
                items.append(f"<li>{inline(item)}</li>")
                i += 1
            tag = "ol" if ordered else "ul"
            out.append(f"<{tag}>{''.join(items)}</{tag}>")
            continue
        para = []
        while i < len(lines) and lines[i].strip() and not FOLD_RE.match(lines[i].strip()) and not re.match(r"^(#{1,4}\s|\||>|```|[-*+]\s|\d+[.)]\s|<!--)", lines[i].strip()):
            para.append(inline(lines[i].strip()))
            i += 1
        out.append(f"<p>{'<br>'.join(para)}</p>")
    return "".join(out) + "</details>" * depth


def screenplay(text: str) -> str:
    """劇本版型；行的分類跟 validate_structure 用同一組正規表達式，排版和門禁看到的一樣。"""
    out: List[str] = []
    scene_open = False
    for raw in text.splitlines():
        s = raw.strip()
        if not s:
            continue
        if s.startswith("#"):
            s = s.lstrip("#").strip()
        ep = EPISODE_HEADER_RE.match(s)
        scene = SCENE_HEADER_RE.match(s)
        if ep:
            out.append(f'<h2 class="sp-ep"><span>第 {E(ep.group(1))} 集</span>{E(ep.group(2))}</h2>')
        elif scene:
            if scene_open:
                out.append("</section>")
            num, place, time, inout, note = scene.groups()
            extra = f"・{E(note)}" if note else ""
            out.append(f'<section class="sp-sc"><div class="sp-h"><b>{E(num)}</b><span class="sp-pl">{E(place)}</span>'
                       f'<span class="sp-tm">{E(time)}／{E(inout)}{extra}</span></div>')
            scene_open = True
        elif CHAR_LINE_RE.match(s):
            out.append(f'<p class="sp-cast">人物　{E(CHAR_LINE_RE.match(s).group(1))}</p>')
        elif COMMENT_RE.match(s):
            key, _, value = COMMENT_RE.match(s).group(1).partition(":")
            label = META_LABEL.get(key.strip().lower())
            if label:
                out.append(f'<span class="sp-meta">{label}　{E(value.strip())}</span>')
        elif s.startswith("△"):
            out.append(f'<p class="sp-act">{inline(s[1:].strip())}</p>')
        elif DIALOGUE_LINE_RE.match(s):
            who, note, line = DIALOGUE_LINE_RE.match(s).groups()
            paren = f'<i>（{E(note)}）</i>' if note else ""
            out.append(f'<div class="sp-dl"><b>{E(who)}</b><p>{paren}{inline(line)}</p></div>')
        else:
            out.append(f"<p>{inline(s)}</p>")
    if scene_open:
        out.append("</section>")
    return f'<div class="sp">{"".join(out)}</div>'


def csv_table(text: str) -> str:
    rows = list(csv.reader(io.StringIO(text)))
    more = len(rows) - 1 - CSV_ROWS
    note = f'<p class="rd-note">只顯示前 {CSV_ROWS} 列，另有 {more} 列請開檔</p>' if more > 0 else ""
    return _table(rows[:CSV_ROWS + 1]) + note


def card_html(card: Dict[str, Any], approval: str = "") -> str:
    """approval＝階段正式狀態（approved／stale）：核准只記在 project-state.json、不寫進文件，以它覆蓋卡上的狀態。"""
    card = dict(card, status={"approved": "已核准", "stale": "已變更待重審"}.get(approval, card.get("status", "")))
    cls = STATUS_CLASS.get(card["status"], "draft")
    meta = "・".join(x for x in (f"v{card['version']}" if card.get("version") else "", card.get("updated", "")) if x)
    rows = []
    if card.get("look"):
        rows.append(f"<dt>先看</dt><dd>{inline(card['look'])}</dd>")
    if card.get("decisions"):
        items = []
        for d in card["decisions"]:
            alts = "".join(f'<span class="dc-alt">或：{E(a)}</span>' for a in d.get("alternatives", []))
            rec = f'<span class="dc-rec">建議：{E(d["recommend"])}</span>' if d.get("recommend") else ""
            items.append(f'<li><span class="dc-q">{E(d["question"])}</span>{rec}{alts}</li>')
        rows.append(f'<dt>要你決定</dt><dd><ol class="dc">{"".join(items)}</ol></dd>')
    else:
        rows.append('<dt>要你決定</dt><dd class="dc-none">無</dd>')
    if card.get("change"):
        rows.append(f"<dt>本次改動</dt><dd>{inline(card['change'])}</dd>")
    return (f'<div class="dcard c-{cls}"><div class="dcard-h"><span class="dst">{E(card.get("status") or "未標狀態")}</span>'
            f'<span class="dmeta">{E(meta)}</span></div>'
            f'<p class="dsum">{inline(card.get("summary") or "（狀態卡缺一句話）")}</p><dl>{"".join(rows)}</dl></div>')


def log_html(log: List[Dict[str, str]]) -> str:
    if not log:
        return ""
    rows = "".join(f"<tr><td>{E(r.get('version', ''))}</td><td>{E(r.get('time', ''))}</td>"
                   f"<td>{inline(r.get('change', ''))}</td><td>{inline(r.get('by', ''))}</td></tr>" for r in log)
    return (f'<details class="dlog"><summary>修訂紀錄（{len(log)} 筆）</summary><div class="rtw"><table>'
            f"<thead><tr><th>版本</th><th>時間</th><th>改了什麼</th><th>依據</th></tr></thead><tbody>{rows}</tbody></table></div></details>")


def render_document(path: str, text: str, approval: str = "") -> Dict[str, str]:
    """回傳 {"card": 狀態卡 HTML（可能空）, "body": 本體＋修訂紀錄 HTML}。"""
    name = Path(path).name.lower()
    if name.endswith(".csv"):
        return {"card": "", "body": f'<article class="rd">{csv_table(text)}</article>'}
    if name.endswith(".txt"):
        return {"card": "", "body": f'<article class="rd"><pre>{E(text)}</pre></article>'}
    doc = doc_card.parse(text)
    body = screenplay(doc["body"]) if name.startswith("script-ep") else markdown(doc["body"])
    return {"card": card_html(doc["card"], approval) if doc["card"] else "",
            "body": f'<article class="rd">{body}{log_html(doc["log"])}</article>'}


CSS = """
.dcard{margin:8px 0 0;border:1px solid var(--line);border-left:4px solid var(--dim);border-radius:10px;background:var(--panel2);padding:10px 14px 12px}
.dcard.c-await,.dcard.c-back,.dcard.c-stale{border-left-color:var(--hot)}.dcard.c-ok{border-left-color:var(--ok)}
.dcard-h{display:flex;flex-wrap:wrap;gap:4px 10px;align-items:baseline}
.dst{font-size:13px;font-weight:700;letter-spacing:.04em;color:var(--mut)}
.c-await .dst,.c-back .dst,.c-stale .dst{color:var(--hot)}.c-ok .dst{color:var(--ok)}
.dmeta{font-size:12.5px;color:var(--dim);font-variant-numeric:tabular-nums}
.dsum{margin:4px 0 8px;font-size:17px;font-weight:700;line-height:1.55;color:var(--tx)}
.dcard dl{margin:0;display:grid;grid-template-columns:5.2em 1fr;gap:6px 10px;font-size:14.5px;line-height:1.65}
.dcard dt{color:var(--dim);font-weight:600}.dcard dd{margin:0;color:var(--mut)}.dc-none{color:var(--dim)}
.dc{margin:0;padding-left:1.2em}.dc li+li{margin-top:6px}.dc-q{color:var(--tx);font-weight:600;margin-right:6px}
.dc-rec,.dc-alt{display:inline-block;margin:2px 6px 0 0;padding:0 8px;border-radius:99px;font-size:13px;border:1px solid var(--line)}
.dc-rec{color:var(--acc);border-color:color-mix(in srgb,var(--acc) 45%,transparent);background:var(--accbg)}.dc-alt{color:var(--mut)}
.rd{max-width:40em;margin:10px 0 0;font-size:16px;line-height:1.85;color:var(--tx)}
.rd>*:first-child{margin-top:0}
.rd h2,.rd h3,.rd h4,.rd h5{line-height:1.4;margin:1.6em 0 .5em;font-weight:700}
.rd h2{font-size:21px;padding-bottom:6px;border-bottom:1px solid var(--line)}.rd h3{font-size:18px}
.rd h3::before{content:"";display:inline-block;width:4px;height:.9em;margin-right:8px;vertical-align:-1px;border-radius:2px;background:var(--acc)}
.rd h4,.rd h5{font-size:16px;color:var(--mut)}
.rd p{margin:.6em 0}.rd ul,.rd ol{margin:.5em 0;padding-left:1.4em}.rd li{margin:.2em 0}.rd li::marker{color:var(--dim)}
.rd strong{color:var(--tx);font-weight:800}
.rd code{font-family:ui-monospace,Consolas,monospace;font-size:.86em;padding:1px 5px;border-radius:5px;background:var(--panel2);border:1px solid var(--line);color:var(--acc);word-break:break-all}
.rd pre{white-space:pre-wrap;word-break:break-word;background:var(--panel2);border:1px solid var(--line);border-radius:8px;padding:10px 12px;font-size:13.5px;line-height:1.6}
.rd blockquote{margin:.8em 0;padding:2px 0 2px 14px;border-left:3px solid var(--line);color:var(--mut)}
.rd hr{border:0;border-top:1px dashed var(--line);margin:1.6em 0}
.rtw{overflow-x:auto;margin:.8em 0;border:1px solid var(--line);border-radius:8px}
.rd table{border-collapse:collapse;width:100%;font-size:14.5px;line-height:1.6}
.rd th{position:sticky;top:0;background:var(--panel2);color:var(--mut);font-weight:600;text-align:left;white-space:nowrap}
.rd th,.rd td{padding:7px 10px;border-bottom:1px solid var(--line);vertical-align:top}
.rd tbody tr:nth-child(even){background:color-mix(in srgb,var(--acc) 4%,transparent)}.rd tbody tr:last-child td{border-bottom:0}
.rd-note{font-size:13px;color:var(--dim)}
.sp-ep{display:flex;align-items:baseline;gap:12px;font-size:22px;margin:0 0 .8em;border:0}
.sp-ep span{font-size:14px;font-weight:600;color:var(--acc);letter-spacing:.08em}
.sp-sc{margin:1.4em 0 0;padding:0 0 .4em}
.sp-h{display:flex;flex-wrap:wrap;align-items:baseline;gap:4px 12px;padding:8px 12px;border-radius:8px;background:var(--panel2);border:1px solid var(--line)}
.sp-h b{font-variant-numeric:tabular-nums;color:var(--acc);font-size:15px}.sp-pl{font-weight:700;font-size:16.5px}.sp-tm{font-size:13.5px;color:var(--dim)}
.sp-cast{margin:.5em 0 .3em;font-size:14px;color:var(--mut)}
.sp-meta{display:inline-block;margin:0 6px 4px 0;padding:0 8px;border-radius:99px;font-size:12px;color:var(--dim);border:1px dashed var(--line)}
.sp-act{margin:.55em 0;padding-left:1.1em;position:relative;color:var(--mut)}
.sp-act::before{content:"△";position:absolute;left:0;color:var(--dim);font-size:.8em;top:.2em}
.sp-dl{display:grid;grid-template-columns:6em 1fr;gap:0 12px;margin:.45em 0}
.sp-dl b{color:var(--acc);text-align:right;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.sp-dl p{margin:0}.sp-dl i{font-style:normal;color:var(--dim);font-size:.9em}
@media (max-width:560px){.sp-dl{grid-template-columns:1fr}.sp-dl b{text-align:left}.dcard dl{grid-template-columns:1fr;gap:0}.dcard dd{margin-bottom:6px}.rd{font-size:15.5px}}
.rfold{margin:.8em 0;border:1px solid var(--line);border-radius:8px;padding:6px 12px}.rfold>summary{cursor:pointer;color:var(--mut);font-size:14.5px}
.dlog{margin:2em 0 0;font-size:14px}.dlog>summary{cursor:pointer;color:var(--dim)}
"""


if __name__ == "__main__":
    # 自檢：跳脫、表格、劇本分類
    out = markdown("# 標\n\n| a | b |\n|---|---|\n| <x> | **粗** |\n\n- 一\n- 二")
    assert "&lt;x&gt;" in out and "<strong>粗</strong>" in out and "<th>a</th>" in out and "<ul>" in out
    sp = screenplay("第01集｜霧起\n\n1-1 燈塔 夜/外\n人物：林霧\n<!-- source: U01 -->\n△霧。\n林霧（低聲）：走。")
    fold = markdown("<details>\n<summary>原始 JSON</summary>\n\n```\n{}\n```\n</details>\n\n<d>台詞</d>\n\n| a<br>b |")
    assert '<details class="rfold"><summary>原始 JSON</summary><pre>' in fold and "&lt;d&gt;" in fold and "a<br>b" in fold
    assert card_html({"status": "等你核准", "summary": "x"}, "approved").count("已核准") == 1
    assert "sp-sc" in sp and "sp-act" in sp and "sp-dl" in sp and "原著　U01" in sp
    print("OK")
