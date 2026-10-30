#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dialogue_budget.py — 台詞優先（dialogue-first）片長估算與依台詞預算分集

規格：references/adapt/dialogue-first-adaptation.md（出處：references/adapt/adaptation-evidence.md）

片長 L = Σ(字數 ÷ 角色語速) ＋ 0.3 s ×(句數−1) ＋ Σ刻意停頓 ＋ Σ建立鏡
- 句數依句末標點（。！？…；）計，不依台詞行數：同一人連續兩句合成一行（#120「單句 ≤18 字」）或拆成兩行，
  估時與密度都不變（EP01 實測：依行數算時，合併少掉句間 0.3 s，G3 3.88→4.02 FAIL）。
- 分鏡後預估片長（storyboard_seconds）：用分鏡閘門同一套數字再算一次——每句說話窗口＝字數÷角色語速＋0.3 s
  （#116，句內每多一句再加 0.3 s），最低 h3_spec.MIN_SHOT_SEC；每段（≤10 s）取 17n+5 平均多半個量子。
  只回報、不擋（adapt_gate 列 NOTE）；原著無台詞動作鏡沒標【停頓】【建立】【動作】的不計，分鏡時另加。
- 角色語速沿用 PR #116（pacing-dialogue-density）：男主 4.0、女角／其他 4.5、旁白／畫外／內心 5.5 字/秒。
- 一般動作行（△）與說話並行，不另計時間；只有標記的動作行計時：
  △【停頓0.8】…   刻意停頓（0.6–1.2 s，每集最多 3 處）
  △【建立2.0】…   無聲建立鏡（≤2.5 s，每場最多 1 處）
  △【動作】… 或 △【動作2.5】…   原著無台詞的動作 beat（巨鳥、爆炸、墜坡；原著有就必標，一個標記＝一個主要動作，
                  多步動作拆多行）：只進「分鏡後預估片長」（未給秒數用 ACTION_DEFAULT_SEC 2.0 s，最短 MIN_SHOT_SEC），
                  不算台詞、不進 L，所以不影響 G3 密度／G7。分鏡骨架把每個標記排成獨立一鏡、鏡長＝標記秒數（validate D5／D6）。
- 密度 D = 可發聲字數 ÷ L，目標 3.0–3.6 字/秒（是速率，不是每集字數額度）。
- 分集＝分鏡斷點（ArcReel 式，見 adaptation-evidence.md）：單集**沒有長度上下限**，最後全部串成一支。
  斷點選在自然的故事點（換場、揭曉、轉折），可落在任何一句之後，以註解記錄：
    <!-- episode-end: 「原著逐字錨點」 | 這集為什麼停在這 -->
  `--target-seconds` 只換算參考字數，純資訊，不擋、不據此切集。

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
BREAK_RE = re.compile(r"episode-end\s*[:：]\s*「(?P<anchor>[^」]*)」\s*[|｜]\s*(?P<reason>.*)$", re.S)
SENTENCE_END_RE = re.compile(r"[。！？!?…；;]+")
ANCHOR_LEN = (2, 30)  # ArcReel end_anchor 10–30 字元；中文原著句短，下限放到 2
NARRATOR_NAMES = ("旁白", "畫外音", "VO", "OS")
VO_NOTES = ("內心", "畫外", "畫外音", "OS", "VO", "旁白")


def speech_chars(text: str) -> int:
    """只算會唸出來的字：排除標點、空白與符號（Unicode P／Z／S 類）。"""
    return sum(1 for ch in text if not unicodedata.category(ch)[0] in "PZS")


def sentence_units(text: str) -> int:
    """一行台詞裡有幾句（依句末標點切；沒有標點＝1 句）。句間 0.3 s 依這個數，不依行數。"""
    return max(1, sum(1 for part in SENTENCE_END_RE.split(text) if speech_chars(part)))


# 分鏡層的數字（單一來源：scripts/storyboard/h3_spec.py 與 handoff_to_skeleton.DEFAULT_MAX_SEGMENT_SEC）
try:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "storyboard"))
    import h3_spec as _h3  # noqa: E402
    MIN_SHOT_SEC = _h3.MIN_SHOT_SEC
    QUANTUM_SEC = _h3.FRAME_QUANTUM_STEP / _h3.FPS
except ImportError:  # pragma: no cover - 單獨拷出 adapt/ 使用時
    MIN_SHOT_SEC, QUANTUM_SEC = 1.2, 17 / 24
# 【動作】標記的單一來源：scripts/storyboard/action_marks.py（分鏡骨架、validate D5／D6 共用）
try:
    from action_marks import ACTION_DEFAULT_SEC, ACTION_MARK_RE  # noqa: E402
except ImportError:  # pragma: no cover - 單獨拷出 adapt/ 使用時
    ACTION_MARK_RE = re.compile(r"【動作\s*([\d.]+)?\s*(?:s|秒)?】")
    ACTION_DEFAULT_SEC = 2.0  # 【動作】未給秒數時的分鏡鏡長
SEGMENT_MAX_SEC = 10.0  # 同 handoff_to_skeleton.DEFAULT_MAX_SEGMENT_SEC


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
    units: int = 1
    lineno: int = 0
    shot_seconds: float = 0.0  # 【動作】鏡：只進分鏡後預估片長，不進劇本公式 L


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
    breaks: List[Dict[str, object]] = field(default_factory=list)  # 分集斷點（episode-end 註解）


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
            if "episode-end" not in m.group(0):
                sc.sources.append(m.group(1).strip())
        for c in COMMENT_RE.findall(raw):
            bm = BREAK_RE.search(c.strip())
            if bm:
                sc.breaks.append({"lineno": i, "anchor": bm.group("anchor").strip(),
                                  "reason": bm.group("reason").strip(),
                                  "scene": len(sc.scenes) - 1,
                                  "pos": len(sc.scenes[-1].lines) if sc.scenes else 0})
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
            for val in ACTION_MARK_RE.findall(line):
                # 原著無台詞動作鏡：分鏡時一定會有一個鏡頭，但不和說話並行、也不算停頓（不進 L／G3／G7）
                ln.shot_seconds += max(MIN_SHOT_SEC, float(val) if val else ACTION_DEFAULT_SEC)
                ln.note = ln.note or "動作"
        else:
            m = DIALOGUE_RE.match(line)
            if not m:
                continue
            speaker, note, body = m.group("speaker"), m.group("note") or "", m.group("text").strip()
            rate = role_rate(speaker, note, male_leads)
            n = speech_chars(body)
            ln = Line(kind="dialogue", raw=line, speaker=speaker, note=note, text=body,
                      invented="invented" in comments, is_vo=rate == ROLE_RATES["narration"],
                      chars=n, seconds=n / rate, units=sentence_units(body), lineno=i)
        (cur.lines if cur else sc.stray).append(ln)
    return sc


def scene_stats(scenes: List[Scene]) -> Dict[str, float]:
    lines = [ln for s in scenes for ln in s.lines]
    dlg = [ln for ln in lines if ln.kind == "dialogue"]
    speak = sum(ln.seconds for ln in dlg)
    # #120 合併／拆行不改估時：句間 0.3 s 依句數（句末標點），不依台詞行數
    gaps = LINE_GAP_SEC * max(sum(ln.units for ln in dlg) - 1, 0)
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
        **storyboard_estimate(scenes),
    }


def _line_window(ln: "Line") -> float:
    """分鏡層一句的鏡長下限：字數÷角色語速＋0.3 s（#116 說話窗口；句內多句再各加 0.3 s），最低 MIN_SHOT_SEC。"""
    return max(MIN_SHOT_SEC, ln.seconds + LINE_GAP_SEC * ln.units)


def storyboard_estimate(scenes: List[Scene]) -> Dict[str, float]:
    """分鏡後預估片長：和 validate_storyboard／compile 同一套數字（MIN_SHOT_SEC、#116 窗口、17n+5 量子）。

    每場：Σ說話窗口＋Σ標記停頓／建立＋Σ【動作】鏡長；段數＝ceil(場長÷SEGMENT_MAX_SEC)，每段取整平均多半個量子
    （0.354 s，inferred：取整方向 ceil／tail-fit 各半）。原著無台詞動作鏡沒標【停頓】【建立】【動作】的不在內。"""
    total = 0.0
    segments = 0
    chars = 0
    actions = 0
    for s in scenes:
        t = sum(_line_window(ln) if ln.kind == "dialogue" else ln.seconds + ln.shot_seconds for ln in s.lines)
        actions += sum(1 for ln in s.lines if ln.kind == "action" and ln.shot_seconds)
        chars += sum(ln.chars for ln in s.lines if ln.kind == "dialogue")
        if t <= 0:
            continue
        n = max(1, -(-t // SEGMENT_MAX_SEC))
        segments += int(n)
        total += t + n * QUANTUM_SEC / 2
    return {"storyboard_seconds": round(total, 2), "storyboard_segments": segments,
            "storyboard_density": round(chars / total, 2) if total else 0.0, "storyboard_action_shots": actions}


def budget(seconds: float) -> Dict[str, float]:
    """參考用：某個秒數在 3.0–3.6 字/秒下對應的字數與行數（每行以 11 字估）。不是每集額度。"""
    lo, hi = DENSITY_MIN * seconds, DENSITY_MAX * seconds
    return {"seconds": seconds, "chars_min": round(lo), "chars_max": round(hi),
            "lines_min": round(lo / 11), "lines_max": round(hi / 11)}


def split_episodes(script: "Script") -> List[List[Scene]]:
    """依 episode-end 斷點切集；斷點可在場內任何一句之後（場被切開時，後半段沿用同一場次標題）。
    沒有斷點時整份是一集。不看秒數、不補場、不設上下限。"""
    cuts = {(b["scene"], b["pos"]) for b in script.breaks}
    episodes: List[List[Scene]] = []
    cur: List[Scene] = []
    for si, s in enumerate(script.scenes):
        part = Scene(heading=s.heading, lineno=s.lineno)
        for li in range(len(s.lines) + 1):
            if (si, li) in cuts and (part.lines or cur):
                if part.lines:
                    cur.append(part)
                episodes.append(cur)
                cur, part = [], Scene(heading=s.heading, lineno=s.lineno)
            if li < len(s.lines):
                part.lines.append(s.lines[li])
        if part.lines:
            cur.append(part)
    if cur:
        episodes.append(cur)
    return episodes


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="台詞優先片長估算；依 episode-end 斷點列出各集（集長不設限）")
    ap.add_argument("script", nargs="?", help="劇本 .md（不給則只印預算表）")
    ap.add_argument("--male-lead", action="append", default=[], help="男主角色名（4.0 字/秒，可重複）")
    ap.add_argument("--target-seconds", type=float, default=None, help="參考秒數（純資訊，不擋）")
    ap.add_argument("--split", action="store_true", help="依 episode-end 斷點列出各集與斷點理由")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if not a.script:
        print(json.dumps(budget(a.target_seconds or 60.0), ensure_ascii=False))
        return 0
    sc = parse_script(Path(a.script).read_text(encoding="utf-8"), a.male_lead)
    out: Dict[str, object] = {"stats": scene_stats(sc.scenes), "breaks": sc.breaks}
    if a.target_seconds:
        out["reference"] = budget(a.target_seconds)
    if a.split:
        eps = split_episodes(sc)
        out["episodes"] = [{"scenes": [s.heading for s in ep], **scene_stats(ep),
                            "end": sc.breaks[k] if k < len(sc.breaks) else None}
                           for k, ep in enumerate(eps)]
    print(json.dumps(out, ensure_ascii=False, indent=None if a.json else 2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
