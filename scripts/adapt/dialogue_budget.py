#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dialogue_budget.py — 台詞優先（dialogue-first）片長估算與依台詞預算分集

規格：references/adapt/dialogue-first-adaptation.md（出處：references/adapt/adaptation-evidence.md）

片長 L = Σ(字數 ÷ 角色語速) ＋ 0.3 s ×(行數−1) ＋ Σ刻意停頓 ＋ Σ建立鏡
- 角色語速沿用 PR #116（pacing-dialogue-density）：男主 4.0、女角／其他 4.5、旁白／畫外／內心 5.5 字/秒。
- 一般動作行（△）與說話並行，不另計時間；只有標記的動作行計時：
  △【停頓0.8】…   刻意停頓（0.6–1.2 s，每集最多 3 處）
  △【建立2.0】…   無聲建立鏡（≤2.5 s，每場最多 1 處）
- 密度 D = 可發聲字數 ÷ L，目標 3.0–3.6 字/秒；150 秒集 ＝ 450–540 字，其他長度等比例換算。
- 分集：依序累加整場；未達下限（3.0 × 目標秒數）就把下一場接進來；
  接進來會超過目標秒數時才在場次邊界切。

台詞行格式：`名（註）：台詞`；旁白行 `旁白：…`；內心獨白 `名（內心）：…` 或 `名（OS）：…`。
行尾 `<!-- invented -->` 標記原著沒有、依規則補寫的台詞（記帳用）。
僅使用 Python 標準庫。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional

ROLE_RATES: Dict[str, float] = {"male_lead": 4.0, "female": 4.5, "narration": 5.5}  # 同 PR #116
LINE_GAP_SEC = 0.3
DENSITY_MIN, DENSITY_MAX = 3.0, 3.6
DEFAULT_EPISODE_SECONDS = 150.0
LINE_HARD_MAX = 35
LINE_TARGET = (9, 13)
VO_MAX_SHARE = 0.30
PAUSE_RANGE = (0.6, 1.2)
ESTABLISH_MAX = 2.5

TIME_WORDS = ("日", "夜", "晨", "昏")
SPACE_WORDS = ("內", "外")
HEADING_RE = re.compile(r"^(?P<id>\d+-\d+)\s+(?P<place>\S.*?)\s+(?P<time>\S+)/(?P<space>\S+)\s*$")
HEADING_LOOSE_RE = re.compile(r"^\d+-\d+\s+\S")
DIALOGUE_RE = re.compile(r"^(?P<speaker>[^：△（()\s<]{1,12})(?:[（(](?P<note>[^）)]*)[）)])?：(?P<text>.+)$")
COMMENT_RE = re.compile(r"<!--(.*?)-->", re.S)
MARK_RE = re.compile(r"【(停頓|建立)\s*([\d.]+)?\s*(?:s|秒)?】")
NARRATOR_NAMES = ("旁白", "畫外音", "VO", "OS")
VO_NOTES = ("內心", "畫外", "畫外音", "OS", "VO", "旁白")


def speech_chars(text: str) -> int:
    """只算會唸出來的字：排除標點、空白與符號（Unicode P／Z／S 類）。"""
    return sum(1 for ch in text if not unicodedata.category(ch)[0] in "PZS")


@dataclass
class Line:
    kind: str  # dialogue / action
    raw: str
    speaker: str = ""
    note: str = ""
    text: str = ""
    invented: bool = False
    is_vo: bool = False
    seconds: float = 0.0
    chars: int = 0
    lineno: int = 0


@dataclass
class Scene:
    heading: str
    lineno: int
    lines: List[Line] = field(default_factory=list)

    @property
    def dialogue(self) -> List[Line]:
        return [ln for ln in self.lines if ln.kind == "dialogue"]


@dataclass
class Script:
    title: str = ""
    sources: List[str] = field(default_factory=list)
    scenes: List[Scene] = field(default_factory=list)
    stray: List[Line] = field(default_factory=list)


def role_rate(speaker: str, note: str, male_leads: Iterable[str]) -> float:
    if speaker in NARRATOR_NAMES or any(v in note for v in VO_NOTES):
        return ROLE_RATES["narration"]
    if speaker in set(male_leads):
        return ROLE_RATES["male_lead"]
    return ROLE_RATES["female"]


def parse_script(text: str, male_leads: Iterable[str] = ()) -> Script:
    male_leads = list(male_leads)
    sc = Script()
    cur: Optional[Scene] = None
    for i, raw in enumerate(text.splitlines(), 1):
        comments = " ".join(c.strip() for c in COMMENT_RE.findall(raw))
        for m in re.finditer(r"source\s*[:：]\s*([^;；]+)", comments):
            sc.sources.append(m.group(1).strip())
        line = COMMENT_RE.sub("", raw).strip()
        if not line:
            continue
        if not sc.title and line.startswith("第") and "集" in line[:8]:
            sc.title = line
            continue
        if HEADING_LOOSE_RE.match(line) and "：" not in line:
            cur = Scene(heading=line, lineno=i)
            sc.scenes.append(cur)
            continue
        if line.startswith("人物："):
            continue
        if line.startswith("△"):
            ln = Line(kind="action", raw=line, lineno=i)
            for kind, val in MARK_RE.findall(line):
                v = float(val) if val else (0.9 if kind == "停頓" else 2.0)
                ln.seconds += v
                ln.note = kind
        else:
            m = DIALOGUE_RE.match(line)
            if not m:
                continue
            speaker, note, body = m.group("speaker"), m.group("note") or "", m.group("text").strip()
            rate = role_rate(speaker, note, male_leads)
            n = speech_chars(body)
            ln = Line(kind="dialogue", raw=line, speaker=speaker, note=note, text=body,
                      invented="invented" in comments, is_vo=rate == ROLE_RATES["narration"],
                      chars=n, seconds=n / rate, lineno=i)
        (cur.lines if cur else sc.stray).append(ln)
    return sc


def scene_stats(scenes: List[Scene]) -> Dict[str, float]:
    lines = [ln for s in scenes for ln in s.lines]
    dlg = [ln for ln in lines if ln.kind == "dialogue"]
    speak = sum(ln.seconds for ln in dlg)
    gaps = LINE_GAP_SEC * max(len(dlg) - 1, 0)
    marked = sum(ln.seconds for ln in lines if ln.kind == "action")
    total = speak + gaps + marked
    chars = sum(ln.chars for ln in dlg)
    vo = sum(ln.chars for ln in dlg if ln.is_vo)
    # 最長無台詞區間：連續標記動作秒數＋前後句間空白
    longest, run = 0.0, 0.0
    for ln in lines:
        if ln.kind == "action":
            run += ln.seconds
        else:
            longest = max(longest, run + (LINE_GAP_SEC if run else 0))
            run = 0.0
    longest = max(longest, run)
    return {
        "lines": len(dlg), "chars": chars, "speak_seconds": round(speak, 2),
        "seconds": round(total, 2), "density": round(chars / total, 2) if total else 0.0,
        "vo_share": round(vo / chars, 3) if chars else 0.0,
        "avg_line_chars": round(chars / len(dlg), 1) if dlg else 0.0,
        "invented_lines": sum(1 for ln in dlg if ln.invented),
        "longest_silence": round(longest, 2),
    }


def budget(seconds: float = DEFAULT_EPISODE_SECONDS) -> Dict[str, float]:
    """目標秒數對應的可發聲字數區間與行數區間（以每行 11 字估）。"""
    lo, hi = DENSITY_MIN * seconds, DENSITY_MAX * seconds
    return {"seconds": seconds, "chars_min": round(lo), "chars_max": round(hi),
            "lines_min": round(lo / 11), "lines_max": round(hi / 11)}


def split_episodes(scenes: List[Scene], episode_seconds: float = DEFAULT_EPISODE_SECONDS) -> List[List[Scene]]:
    """依台詞預算在場次邊界分集：未達字數下限就接下一場；接了會超過秒數上限才切。"""
    floor = DENSITY_MIN * episode_seconds
    episodes: List[List[Scene]] = []
    cur: List[Scene] = []
    for s in scenes:
        if cur:
            st_now = scene_stats(cur)
            st_next = scene_stats(cur + [s])
            if st_next["seconds"] > episode_seconds or st_now["chars"] >= floor:
                episodes.append(cur)
                cur = []
        cur.append(s)
    if cur:
        episodes.append(cur)
    return episodes


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="台詞優先片長估算與依台詞預算分集")
    ap.add_argument("script", nargs="?", help="劇本 .md（不給則只印預算表）")
    ap.add_argument("--male-lead", action="append", default=[], help="男主角色名（4.0 字/秒，可重複）")
    ap.add_argument("--episode-seconds", type=float, default=DEFAULT_EPISODE_SECONDS)
    ap.add_argument("--split", action="store_true", help="依台詞預算重新分集並列出各集場次")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if not a.script:
        print(json.dumps(budget(a.episode_seconds), ensure_ascii=False))
        return 0
    sc = parse_script(Path(a.script).read_text(encoding="utf-8"), a.male_lead)
    out: Dict[str, object] = {"budget": budget(a.episode_seconds), "stats": scene_stats(sc.scenes)}
    if a.split:
        out["episodes"] = [{"scenes": [s.heading for s in ep], **scene_stats(ep)}
                           for ep in split_episodes(sc.scenes, a.episode_seconds)]
    print(json.dumps(out, ensure_ascii=False, indent=None if a.json else 2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
