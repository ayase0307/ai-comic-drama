#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
adapt_gate.py — 台詞優先改編自檢門（dialogue-first adaptation gate）

規格：references/adapt/dialogue-first-adaptation.md §自檢門。不詢問使用者；全部 FAIL 清零才可交稿。

硬門（FAIL）：
  G1 原著對白覆蓋率 100%（依抽出的原著台詞逐句比對；補寫台詞 `<!-- invented -->` 不算覆蓋）
  G3 密度 3.0–3.6 字/秒（<2.8 或 >3.9 FAIL，其餘區間外 WARN）
  G5 單行 ≤35 字
  G7 連續無台詞 ≤10 秒（>5 秒 WARN）
  G9 場次標題 `N-M 地點 日|夜|晨|昏/內|外`；集尾不加鉤子旁白（集長不設上下限）
  G13 分集斷點：集尾有 `<!-- episode-end: 「原著錨點」 | 理由 -->`；錨點 2–30 字、在原著段落逐字出現，理由非空
  G12 原著出處範圍已填（`<!-- source: 卷X Ln-Lm -->`）
  G10 內容安全：全員成年、不性化（關鍵詞掃描＋人物表聲明）
警告（WARN）：平均行長 >13、旁白／內心 VO >30%、補寫台詞數（記帳）、無結尾鉤子旁白檢查、
  刻意停頓每集 >3 處、建立鏡每場 >1 處。
備註（NOTE，不影響狀態）：--source-text 略過的疑似專有名詞引號；原著對白全保留時密度 3.6–3.9（可接受）。
僅使用 Python 標準庫。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dialogue_budget import (  # noqa: E402
    ANCHOR_LEN, DENSITY_MAX, DENSITY_MIN, HEADING_RE, LINE_HARD_MAX, LINE_TARGET,
    SPACE_WORDS, TIME_WORDS, VO_MAX_SHARE, Script, parse_script, split_episodes, scene_stats, speech_chars,
)

QUOTE_RE = re.compile(r"「([^「」]+)」")
COVERAGE_MIN_RATIO = 0.85  # 允許脫水（拆句、去語助詞），不允許刪句
DENSITY_FAIL = (2.8, 3.9)
PAUSE_PER_EPISODE_MAX = 3      # references/adapt/dialogue-first-adaptation.md：刻意停頓每集 ≤3 處
ESTABLISH_PER_SCENE_MAX = 1    # 建立鏡每場 ≤1 處
SILENCE_WARN, SILENCE_FAIL = 5.0, 10.0
# 內容安全：未成年描寫或性化描寫的關鍵詞（命中即 FAIL，需人工改寫後重跑）
MINOR_TERMS = ("未成年", "幼女", "蘿莉", "女童", "男童", "小學生", "國中生", "初中生", "高中生", "童顏")
SEXUAL_TERMS = ("裸體", "裸露", "全裸", "胸部特寫", "性感", "情色", "色情", "誘惑地", "曲線畢露", "走光", "內衣特寫", "床戲")
HOOK_NARRATION_RE = re.compile(r"(下集|欲知後事|敬請期待|究竟.*[？?]$)")


def normalize(text: str) -> str:
    return "".join(ch for ch in text if speech_chars(ch))


# v118 #7：「」也用來標專有名詞（旅館名、招式名…）。沒有句讀、不在段首或冒號後、後面也沒接說話動詞的
# 引號視為名詞，不算台詞（例：「蛙仙大旅社」）。不確定時用 --source-quotes 給人工清單。
_SENTENCE_PUNCT_RE = re.compile(r"[。！？!?…,，、～~—.；;：:]")
_SPEECH_LEAD_RE = re.compile(r"(?:[：:]\s*|^\s*|\n\s*)$")
_SPEECH_TAIL_RE = re.compile(r"^\s*(?:他|她|我|你|牠|它)?(?:說|道|問|喊|叫|答|笑|嘆|嚷)")


def _is_dialogue_quote(text: str, start: int, end: int, body: str) -> bool:
    if _SENTENCE_PUNCT_RE.search(body):
        return True
    if _SPEECH_LEAD_RE.search(text[max(0, start - 8):start]):
        return True
    return bool(_SPEECH_TAIL_RE.match(text[end:end + 4]))


def source_quotes(novel_text: str, skipped: Optional[List[str]] = None) -> List[str]:
    """從原著段落抽出「」內台詞（巢狀引號以外層為單位）；疑似專有名詞的引號放進 skipped。"""
    out: List[str] = []
    for m in QUOTE_RE.finditer(novel_text):
        q = m.group(1).strip()
        if not normalize(q):
            continue
        if _is_dialogue_quote(novel_text, m.start(), m.end(), q):
            out.append(q)
        elif skipped is not None:
            skipped.append(q)
    return out


def coverage(quotes: List[str], script: Script) -> Dict[str, object]:
    stream = normalize("".join(ln.text for s in script.scenes for ln in s.dialogue if not ln.invented))
    missing = []
    for q in quotes:
        nq = normalize(q)
        if not nq or nq in stream:
            continue
        sm = SequenceMatcher(None, nq, stream, autojunk=False)
        got = sum(b.size for b in sm.get_matching_blocks())
        if got / len(nq) < COVERAGE_MIN_RATIO:
            missing.append(q)
    total = len(quotes)
    return {"total": total, "covered": total - len(missing), "missing": missing,
            "ratio": round((total - len(missing)) / total, 3) if total else 1.0}


def safety_hits(text: str) -> List[str]:
    return [t for t in MINOR_TERMS + SEXUAL_TERMS if t in text]


def run_gate(script_text: str, novel_text: Optional[str] = None, quotes: Optional[List[str]] = None,
             male_leads: List[str] = (), target_seconds: Optional[float] = None) -> Dict[str, object]:
    sc = parse_script(script_text, male_leads)
    st = scene_stats(sc.scenes)
    fails: List[str] = []
    warns: List[str] = []

    skipped_terms: List[str] = []
    if quotes is None and novel_text is not None:
        quotes = source_quotes(novel_text, skipped_terms)
    cov = coverage(quotes, sc) if quotes is not None else None
    if cov is None:
        fails.append("G1 未提供原著段落／台詞清單，無法核對對白覆蓋（--source-text 或 --source-quotes）")
    elif cov["missing"]:
        fails.append(f"G1 原著對白覆蓋 {cov['covered']}/{cov['total']}，缺：" + "｜".join(cov["missing"][:5]))

    notes: List[str] = []
    if skipped_terms:
        notes.append("G1 「」內疑似專有名詞、未計入原著對白：" + "、".join(skipped_terms[:8])
                     + "（若其實是台詞，改用 --source-quotes）")
    d = st["density"]
    full_source = bool(cov) and not cov["missing"] and cov["total"] > 0
    if d < DENSITY_FAIL[0] or d > DENSITY_FAIL[1]:
        fails.append(f"G3 密度 {d} 字/秒 超出 {DENSITY_FAIL[0]}–{DENSITY_FAIL[1]}（目標 {DENSITY_MIN}–{DENSITY_MAX}）")
    elif d > DENSITY_MAX and full_source:
        # v118 #8：原著對白全保留時密度偏高（≤3.9）是台詞優先的結果；不刪原著對白、也不為壓密度多加停頓秒數
        notes.append(f"G3 密度 {d} 字/秒 高於目標 {DENSITY_MAX}，但原著對白全保留且未超過 {DENSITY_FAIL[1]}：可接受，"
                     "不刪原著對白、不為壓密度多加停頓／建立秒數")
    elif d < DENSITY_MIN or d > DENSITY_MAX:
        warns.append(f"G3 密度 {d} 字/秒 不在目標 {DENSITY_MIN}–{DENSITY_MAX}")
    for ep_i, ep in enumerate(split_episodes(sc), start=1):
        pauses = [ln for s in ep for ln in s.lines if ln.kind == "action" and ln.note == "停頓"]
        if len(pauses) > PAUSE_PER_EPISODE_MAX:
            warns.append(f"G3 第 {ep_i} 集刻意停頓 {len(pauses)} 處 > {PAUSE_PER_EPISODE_MAX}（每集上限；多的改成和說話並行）")
        for s in ep:
            est = [ln for ln in s.lines if ln.kind == "action" and ln.note == "建立"]
            if len(est) > ESTABLISH_PER_SCENE_MAX:
                warns.append(f"G3 L{s.lineno} 本場建立鏡 {len(est)} 處 > {ESTABLISH_PER_SCENE_MAX}（每場上限）")

    for s in sc.scenes:
        m = HEADING_RE.match(s.heading)
        if not m or m.group("time") not in TIME_WORDS or m.group("space") not in SPACE_WORDS:
            fails.append(f"G9 L{s.lineno} 場次標題格式錯：{s.heading!r}（時段只用 日/夜/晨/昏，內外只用 內/外）")
        for ln in s.dialogue:
            if ln.chars > LINE_HARD_MAX:
                fails.append(f"G5 L{ln.lineno} 單行 {ln.chars} 字 > {LINE_HARD_MAX}：{ln.text[:20]}…")
    if not sc.scenes:
        fails.append("G9 找不到任何場次標題")
    if not sc.breaks:
        fails.append("G13 缺分集斷點：集尾加 `<!-- episode-end: 「原著逐字錨點」 | 這集為什麼停在這 -->`")
    norm_src = normalize(novel_text) if novel_text else None
    for b in sc.breaks:
        n = len(normalize(b["anchor"]))
        if not ANCHOR_LEN[0] <= n <= ANCHOR_LEN[1]:
            fails.append(f"G13 L{b['lineno']} 斷點錨點 {n} 字，需 {ANCHOR_LEN[0]}–{ANCHOR_LEN[1]} 字")
        elif norm_src is not None and normalize(b["anchor"]) not in norm_src:
            fails.append(f"G13 L{b['lineno']} 斷點錨點不在原著段落：「{b['anchor']}」")
        if not b["reason"]:
            fails.append(f"G13 L{b['lineno']} 斷點缺理由（這集為什麼停在這）")
    if sc.breaks and norm_src is None:
        warns.append("G13 未提供原著段落，斷點錨點未逐字核對（--source-text）")
    if st["longest_silence"] > SILENCE_FAIL:
        fails.append(f"G7 連續無台詞 {st['longest_silence']}s > {SILENCE_FAIL:g}s")
    elif st["longest_silence"] > SILENCE_WARN:
        warns.append(f"G7 連續無台詞 {st['longest_silence']}s > {SILENCE_WARN:g}s")
    if not sc.sources:
        fails.append("G12 缺原著出處範圍（加 `<!-- source: 卷X Ln-Lm -->`）")

    hits = safety_hits(script_text)
    if hits:
        fails.append("G10 內容安全：命中未成年／性化詞 " + "、".join(hits) + "（全員成年、不性化）")

    if st["avg_line_chars"] > LINE_TARGET[1]:
        warns.append(f"G5 平均行長 {st['avg_line_chars']} 字 > {LINE_TARGET[1]}（目標 {LINE_TARGET[0]}–{LINE_TARGET[1]}）")
    if st["vo_share"] > VO_MAX_SHARE:
        warns.append(f"G6 旁白／內心 VO 佔 {st['vo_share']:.0%} > {VO_MAX_SHARE:.0%}")
    for ep in split_episodes(sc):
        last = next((ln for s in reversed(ep) for ln in reversed(s.dialogue)), None)
        if last and last.is_vo and HOOK_NARRATION_RE.search(last.text):
            fails.append(f"G9 L{last.lineno} 集尾加了鉤子旁白：{last.text}")
    if st["invented_lines"]:
        warns.append(f"記帳：補寫台詞 {st['invented_lines']} 行（須寫入 adaptation-diff.md）")

    info = {"target_seconds": target_seconds, "seconds": st["seconds"]} if target_seconds else None
    return {"status": "FAIL" if fails else ("WARN" if warns else "PASS"), "fails": fails, "warns": warns,
            "notes": notes,
            "stats": st, "breaks": sc.breaks, "length_info": info, "coverage": cov, "sources": sc.sources,
            "invented": [ln.raw for s in sc.scenes for ln in s.dialogue if ln.invented]}


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="台詞優先改編自檢門")
    ap.add_argument("script")
    ap.add_argument("--source-text", help="本集對應的原著段落（自動抽「」台詞）")
    ap.add_argument("--source-quotes", help="JSON 陣列：抽好的原著台詞")
    ap.add_argument("--male-lead", action="append", default=[])
    ap.add_argument("--target-seconds", type=float, default=None, help="參考秒數，只回報不擋")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    novel = Path(a.source_text).read_text(encoding="utf-8") if a.source_text else None
    quotes = json.loads(Path(a.source_quotes).read_text(encoding="utf-8")) if a.source_quotes else None
    res = run_gate(Path(a.script).read_text(encoding="utf-8"), novel, quotes, a.male_lead, a.target_seconds)
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        print(f"[{res['status']}] {json.dumps(res['stats'], ensure_ascii=False)}")
        for f in res["fails"]:
            print("  FAIL", f)
        for w in res["warns"]:
            print("  WARN", w)
        for n in res.get("notes") or []:
            print("  NOTE", n)
    return 1 if res["fails"] else 0


if __name__ == "__main__":
    sys.exit(main())
