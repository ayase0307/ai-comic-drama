#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""階段文件的狀態卡與修訂紀錄（references/document-standard.md）。

每份給人讀的階段 Markdown：最上面一張狀態卡、中間本體、最後修訂紀錄，外框全用 `>` 引言行。
劇本解析、內容門禁都略過 `>` 行，所以外框不改變任何檢查結果。

  h3d doc stamp <檔> --stage 3 --status 等你核准 --summary ... [--look ...] [--decide ...] [--change ... --by ...]
  h3d doc resolve <檔> <第幾條> --answer ... --quote ...
  h3d doc check --root .
  h3d doc show <檔>
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

STATUSES = ("草稿", "等你核准", "退回修改", "已核准", "已變更待重審")
STAGE_NAMES = ["定調", "改編", "設定圖", "劇本", "分鏡", "提示詞", "影片", "配音剪輯"]
MAX_DECISIONS = 3
LOG_HEAD = "> **修訂紀錄**"
LOG_COLUMNS = ("> | 版本 | 時間 | 改了什麼 | 依據 |", "> |---|---|---|---|")
CARD_SCAN_LINES = 12
# 各關要有狀態卡的文件（glob → 階段）
STAGE_DOCS: List[Tuple[str, int]] = [
    ("project.md", 0), ("adapt/character-bible.md", 1), ("adapt/series-outline.md", 1),
    ("assets.md", 2), ("script-ep*.md", 3), ("adaptation-diff.md", 3),
    ("storyboard-ep*.md", 4), ("prompts-ep*.md", 5), ("narration-ep*.md", 7),
]

_FIELD = re.compile(r"^>\s*(狀態|一句話|先看|要你決定|本次改動)[：:]\s*(.*)$")
_DECISION_ITEM = re.compile(r"^>\s*(\d+)[.、]\s*(.+)$")


def now_str() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")


# ------------------------------------------------------------------ 決定條目
def parse_decision(text: str) -> Dict[str, Any]:
    """`問題？ 建議：A；或：B` → {question, recommend, alternatives}。沒寫建議就只有問題。"""
    text = text.strip()
    match = re.search(r"\s*建議[：:]\s*", text)
    if not match:
        return {"question": text, "recommend": "", "alternatives": []}
    question, rest = text[:match.start()].strip(), text[match.end():]
    parts = [p.strip() for p in re.split(r"[；;]\s*或[：:]\s*", rest) if p.strip()]
    return {"question": question, "recommend": parts[0] if parts else "", "alternatives": parts[1:]}


def format_decision(item: Dict[str, Any]) -> str:
    out = item["question"]
    if item.get("recommend"):
        out += f" 建議：{item['recommend']}"
        out += "".join(f"；或：{alt}" for alt in item.get("alternatives", []))
    return out


# ------------------------------------------------------------------ 解析
def _blocks(lines: List[str]) -> List[Tuple[int, int]]:
    """連續 `>` 行組成的區塊（含頭不含尾的行號範圍）。"""
    spans, start = [], None
    for i, line in enumerate(lines + [""]):
        quoted = line.lstrip().startswith(">")
        if quoted and start is None:
            start = i
        elif not quoted and start is not None:
            spans.append((start, i))
            start = None
    return spans


def parse(text: str) -> Dict[str, Any]:
    lines = text.lstrip("﻿").splitlines()
    card_span = log_span = None
    for start, end in _blocks(lines):
        block = lines[start:end]
        if card_span is None and start < CARD_SCAN_LINES and any(_FIELD.match(l) and "狀態" in l for l in block):
            card_span = (start, end)
        if block[0].strip() == LOG_HEAD:
            log_span = (start, end)
    card = _parse_card(lines[card_span[0]:card_span[1]]) if card_span else None
    log = _parse_log(lines[log_span[0]:log_span[1]]) if log_span else []
    keep = [l for i, l in enumerate(lines)
            if not (card_span and card_span[0] <= i < card_span[1]) and not (log_span and log_span[0] <= i < log_span[1])]
    body = re.sub(r"\n{3,}", "\n\n", "\n".join(keep)).strip("\n")  # 拿掉外框留下的空行
    return {"card": card, "log": log, "body": body, "card_span": card_span, "log_span": log_span}


def _parse_card(block: List[str]) -> Dict[str, Any]:
    card: Dict[str, Any] = {"title": "", "status": "", "version": 0, "updated": "", "summary": "", "look": "",
                            "decisions": [], "change": ""}
    title = re.match(r"^>\s*\*\*(.+?)\*\*\s*$", block[0]) if block else None
    if title:
        card["title"] = title.group(1)
    for line in block:
        field = _FIELD.match(line)
        item = _DECISION_ITEM.match(line)
        if field:
            key, value = field.groups()
            if key == "狀態":
                for part in re.split(r"[｜|]", value):
                    k, _, v = part.partition("：") if "：" in part else part.partition(":")
                    k, v = k.strip(), v.strip()
                    if k == "版本":
                        card["version"] = int(re.sub(r"\D", "", v) or 0)
                    elif k == "更新":
                        card["updated"] = v
                    elif not v:
                        card["status"] = k
                card["status"] = card["status"] or value.split("｜")[0].strip()
            elif key == "一句話":
                card["summary"] = value
            elif key == "先看":
                card["look"] = value
            elif key == "本次改動":
                card["change"] = value
        elif item:
            card["decisions"].append(parse_decision(item.group(2)))
    return card


def _parse_log(block: List[str]) -> List[Dict[str, str]]:
    rows = []
    for line in block[3:]:
        cells = [c.strip() for c in line.lstrip("> ").strip().strip("|").split("|")]
        if len(cells) >= 4:
            rows.append({"version": cells[0], "time": cells[1], "change": cells[2], "by": cells[3]})
    return rows


# ------------------------------------------------------------------ 輸出
def render_card(card: Dict[str, Any]) -> List[str]:
    decisions = card.get("decisions") or []
    out = [f"> **{card['title']}**",
           f"> 狀態：{card['status']}｜版本：v{card['version']}｜更新：{card['updated']}",
           f"> 一句話：{card['summary']}"]
    if card.get("look"):
        out.append(f"> 先看：{card['look']}")
    if decisions:
        out.append("> 要你決定：")
        out += [f"> {i}. {format_decision(d)}" for i, d in enumerate(decisions, 1)]
    else:
        out.append("> 要你決定：無")
    out.append(f"> 本次改動：{card.get('change') or '初稿'}")
    return out


def _cell(text: str) -> str:
    return str(text).replace("|", "／").replace("\n", " ").strip()


def render_log(rows: List[Dict[str, str]]) -> List[str]:
    return [LOG_HEAD, *LOG_COLUMNS] + [
        f"> | {_cell(r['version'])} | {_cell(r['time'])} | {_cell(r['change'])} | {_cell(r['by'])} |" for r in rows]


def assemble(body: str, card: Dict[str, Any], log: List[Dict[str, str]]) -> str:
    """H1（若本體第一行是）→ 狀態卡 → 其餘本體 → 修訂紀錄。"""
    lines = body.splitlines()
    head: List[str] = []
    if lines and lines[0].startswith("# "):
        head, lines = [lines[0], ""], lines[1:]
    rest = "\n".join(lines).strip("\n")
    parts = ["\n".join(head + render_card(card)), rest]
    if log:
        parts.append("\n".join(render_log(log)))
    return "\n\n".join(p for p in parts if p) + "\n"


# ------------------------------------------------------------------ 操作
def default_title(path: Path, stage: int, project: str) -> str:
    match = re.search(r"-ep(\d+)", path.stem, re.I)
    scope = f"第 {match.group(1)} 集" if match else "全片"
    return f"{project}・階段 {stage} {STAGE_NAMES[stage]}・{scope}"


def stamp(text: str, *, title: str, status: Optional[str] = None, summary: Optional[str] = None,
          look: Optional[str] = None, decisions: Optional[List[str]] = None, change: Optional[str] = None,
          by: str = "Agent", when: Optional[str] = None) -> str:
    if status is not None and status not in STATUSES:
        raise ValueError(f"狀態只能是 {'／'.join(STATUSES)}，收到「{status}」")
    when = when or now_str()
    doc = parse(text)
    card = doc["card"] or {"title": title, "status": "草稿", "version": 1, "updated": when, "summary": "",
                           "look": "", "decisions": [], "change": "初稿"}
    log = list(doc["log"])
    card = dict(card, title=card.get("title") or title, updated=when)
    if status is not None:
        card["status"] = status
    if summary is not None:
        card["summary"] = summary
    if look is not None:
        card["look"] = look
    if decisions is not None:
        items = [] if decisions == ["無"] else [parse_decision(d) for d in decisions if d.strip()]
        if len(items) > MAX_DECISIONS:
            raise ValueError(f"「要你決定」最多 {MAX_DECISIONS} 條；其餘交給收件匣或拆到下一輪")
        card["decisions"] = items
    if change:
        if doc["card"]:
            card["version"] = int(card.get("version") or 0) + 1
        card["change"] = change
    if not doc["card"] or change:
        log.insert(0, {"version": f"v{card['version']}", "time": when, "change": card["change"], "by": by})
    if not card.get("summary"):
        raise ValueError("狀態卡必須有「一句話」（--summary）")
    return assemble(doc["body"], card, log)


def resolve(text: str, number: int, answer: str, quote: str, when: Optional[str] = None) -> str:
    when = when or now_str()
    doc = parse(text)
    if not doc["card"]:
        raise ValueError("這份文件還沒有狀態卡")
    items = list(doc["card"]["decisions"])
    if not 1 <= number <= len(items):
        raise ValueError(f"沒有第 {number} 條待決（目前 {len(items)} 條）")
    item = items.pop(number - 1)
    card = dict(doc["card"], decisions=items, updated=when)
    log = [{"version": f"v{card['version']}", "time": when, "change": f"決定：{item['question']} → {answer}",
            "by": f"使用者：「{quote}」"}] + doc["log"]
    return assemble(doc["body"], card, log)


def regenerate(old_text: Optional[str], new_body: str, *, title: str, summary: str, by: str = "產生器",
               when: Optional[str] = None) -> str:
    """產生器重寫本體時：保留原狀態卡；本體真的變了才升版、記一筆，並把狀態退回草稿／已變更待重審。"""
    when = when or now_str()
    old = parse(old_text) if old_text else None
    if not old or not old["card"]:
        return stamp(new_body, title=title, status="草稿", summary=summary, by=by, when=when)
    if old["body"].strip() == new_body.strip():
        return old_text if old_text.endswith("\n") else old_text + "\n"
    card = dict(old["card"])
    status = "已變更待重審" if card.get("status") == "已核准" else "草稿"
    text = assemble(new_body, card, old["log"])
    return stamp(text, title=title, status=status, change="重新產生（本體內容有變）", by=by, when=when)


def write_generated(path: Path, body: str, *, stage: int, summary: str, by: str) -> None:
    """產生器寫 Markdown 的單一入口：讀舊檔、套 regenerate、寫回。"""
    path = Path(path)
    old = path.read_text(encoding="utf-8-sig") if path.is_file() else None
    title = default_title(path, stage, _project_title(_find_root(path.resolve())))
    path.write_text(regenerate(old, body, title=title, summary=summary, by=by), encoding="utf-8")


def check(root: Path) -> List[str]:
    """只提醒：哪些階段文件沒有狀態卡、狀態不合規、待決超過上限。"""
    problems = []
    for pattern, stage in STAGE_DOCS:
        for path in sorted(root.glob(pattern)):
            rel = path.relative_to(root).as_posix()
            card = parse(path.read_text(encoding="utf-8-sig"))["card"]
            if not card:
                problems.append(f"{rel}：沒有狀態卡（h3d doc stamp {rel} --stage {stage} --status 草稿 --summary ...）")
            elif card["status"] not in STATUSES:
                problems.append(f"{rel}：狀態「{card['status']}」不在 {'／'.join(STATUSES)}")
            elif not card["summary"]:
                problems.append(f"{rel}：狀態卡缺「一句話」")
    return problems


def doc_decisions(root: Path) -> List[Dict[str, Any]]:
    """所有階段文件狀態卡裡的待決條目（給收件匣出卡）。"""
    out = []
    for pattern, stage in STAGE_DOCS:
        for path in sorted(root.glob(pattern)):
            try:
                card = parse(path.read_text(encoding="utf-8-sig"))["card"]
            except (OSError, UnicodeDecodeError):
                continue
            for i, item in enumerate((card or {}).get("decisions") or [], 1):
                out.append({"stage": stage, "path": path.relative_to(root).as_posix(), "number": i, **item})
    return out


def _project_title(root: Path) -> str:
    try:
        state = json.loads((root / "review" / "project-state.json").read_text(encoding="utf-8-sig"))
        return state.get("title") or root.name
    except (OSError, json.JSONDecodeError):
        return root.name


def _find_root(path: Path) -> Path:
    for parent in [path.parent, *path.parent.parents]:
        if (parent / "review").is_dir() or (parent / "project.md").is_file():
            return parent
    return path.parent


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="h3d doc", description="階段文件的狀態卡與修訂紀錄（references/document-standard.md）")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("stamp", help="建立或更新狀態卡；給 --change 會升版並寫修訂紀錄")
    p.add_argument("file", type=Path)
    p.add_argument("--stage", type=int, choices=range(8), help="階段 0–7（新卡必填）")
    p.add_argument("--status", choices=STATUSES)
    p.add_argument("--summary", help="一句話結論（30 字內）")
    p.add_argument("--look", help="先看哪裡")
    p.add_argument("--decide", action="append", help="要你決定（可重複，最多 3 條）：問題？ 建議：A；或：B；給「無」清空")
    p.add_argument("--change", help="這一版改了什麼（給了就升版並記修訂紀錄）")
    p.add_argument("--by", default="Agent", help="依據：誰決定的，使用者決定要附原話")
    p.add_argument("--title", help="卡片標題（預設：作品名・階段 N 中文名・範圍）")
    p = sub.add_parser("resolve", help="使用者回覆了某條待決：移進修訂紀錄")
    p.add_argument("file", type=Path)
    p.add_argument("number", type=int)
    p.add_argument("--answer", required=True)
    p.add_argument("--quote", required=True, help="使用者原話")
    p = sub.add_parser("check", help="列出缺卡或不合規的階段文件（只提醒）")
    p.add_argument("--root", type=Path, default=Path("."))
    p = sub.add_parser("show", help="印出狀態卡與修訂紀錄（JSON）")
    p.add_argument("file", type=Path)
    args = parser.parse_args(argv)

    if args.cmd == "check":
        problems = check(args.root.resolve())
        for item in problems:
            print(f"⚠️ {item}")
        print("✅ 階段文件外框都合規" if not problems else f"共 {len(problems)} 項（只提醒，不擋關）")
        return 0
    path = args.file.resolve()
    text = path.read_text(encoding="utf-8-sig") if path.is_file() else ""
    if args.cmd == "show":
        doc = parse(text)
        print(json.dumps({"card": doc["card"], "log": doc["log"]}, ensure_ascii=False, indent=2))
        return 0
    try:
        if args.cmd == "resolve":
            new = resolve(text, args.number, args.answer, args.quote)
        else:
            card = parse(text)["card"]
            if not card and args.stage is None:
                parser.error("新文件要給 --stage")
            title = args.title or (card or {}).get("title") or default_title(path, args.stage, _project_title(_find_root(path)))
            new = stamp(text, title=title, status=args.status, summary=args.summary, look=args.look,
                        decisions=args.decide, change=args.change, by=args.by)
    except ValueError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 1
    path.write_text(new, encoding="utf-8")
    card = parse(new)["card"]
    print(f"✅ {path.name}：{card['status']}｜v{card['version']}｜待決 {len(card['decisions'])} 條")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
