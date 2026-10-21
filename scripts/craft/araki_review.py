#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""araki-manga-craft lens: advisory checks for stage 2 (character sheets) and stage 3 (plus/minus arc).

Never blocks: exits 0 unless the CLI is misused.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

LENS = "araki"
FIELDS: Dict[str, List[str]] = {
    "動機": ["動機", "动机", "想要", "目標", "目标", "motive", "goal", "want"],
    "弱點": ["弱點", "弱点", "缺點", "缺点", "軟肋", "软肋", "weakness", "flaw"],
    "過去": ["過去", "过去", "背景", "經歷", "经历", "身世", "backstory"],
}
VILLAIN_MARKERS = ["反派", "敵", "敌", "對手", "对手", "villain", "antagonist", "系統", "系统"]
PHILOSOPHY_KEYS = ["哲學", "哲学", "信念", "理念", "信條", "信条", "世界觀", "世界观", "philosophy", "creed"]
VISUAL_KEYS = ["髮", "发型", "眉", "眼", "服", "袍", "衣", "配飾", "配饰", "hair", "robe"]
CHAR_HEADING = re.compile(r"^(\d+\s*[.、]|角色|人物)|歲|岁|主角|反派|配角")

Finding = Tuple[str, str, str]


def split_sections(md: str) -> List[Tuple[str, str]]:
    sections: List[Tuple[str, str]] = []
    title, buf = None, []
    for line in md.splitlines():
        m = re.match(r"^#{2,3}\s+(.+)$", line)
        if m:
            if title is not None:
                sections.append((title, "\n".join(buf)))
            title, buf = m.group(1).strip(), []
        elif title is not None:
            buf.append(line)
    if title is not None:
        sections.append((title, "\n".join(buf)))
    return [(t, b) for t, b in sections if CHAR_HEADING.search(t)]


def has_any(text: str, keys: List[str]) -> bool:
    low = text.lower()
    return any(k.lower() in low for k in keys)


def review_stage2(bible: Path) -> List[Finding]:
    if not bible.exists():
        return [("⚠️", "輸入", f"找不到角色文件 {bible}，略過")]
    sections = split_sections(bible.read_text(encoding="utf-8"))
    if not sections:
        return [("⚠️", "輸入", "沒有辨識到角色段落（標題需含編號、歲數或角色定位）")]
    out: List[Finding] = []
    for title, body in sections:
        name = re.sub(r"\s+", " ", title)[:40]
        missing = [f for f, keys in FIELDS.items() if not has_any(title + body, keys)]
        visual_only = has_any(body, VISUAL_KEYS) and len(missing) == len(FIELDS)
        if visual_only:
            out.append(("⚠️", "身上調査書", f"{name}：只有外觀描述，沒有動機、弱點、過去"))
        elif missing:
            out.append(("⚠️", "身上調査書", f"{name}：缺少 {'、'.join(missing)}"))
        else:
            out.append(("✅", "身上調査書", f"{name}：動機、弱點、過去都有"))
        if has_any(title, VILLAIN_MARKERS) and not has_any(body, PHILOSOPHY_KEYS):
            out.append(("⚠️", "反派哲學", f"{name}：是反派或對手，但沒寫他貫徹的哲學或信念"))
    return out


def review_stage3(handoff: Dict[str, Any], episode: str) -> List[Finding]:
    ep = next((e for e in handoff.get("episodes", []) if str(e.get("episode_id", "")).upper() == episode.upper()), None)
    if ep is None:
        return [("⚠️", "輸入", f"handoff 裡沒有 {episode}")]
    scenes = ep.get("scenes", [])
    charges = [sc.get("protagonist_charge") for sc in scenes]
    if not any(c in ("+", "-", "0") for c in charges):
        return [("ℹ️", "正負曲線", f"{len(scenes)} 場都沒有 protagonist_charge（+/-/0），請由 Agent 逐場標註後重跑")]
    out: List[Finding] = []
    total, run_neg, worst = 0, 0, 0
    for c in charges:
        total += {"+": 1, "-": -1}.get(c or "0", 0)
        run_neg = run_neg + 1 if c == "-" else 0
        worst = max(worst, run_neg)
    out.append(("✅" if total > 0 else "⚠️", "常にプラス", f"整集淨值 {total:+d}（荒木：主角整體要收在正的一側）"))
    out.append(("✅" if worst < 3 else "⚠️", "連續負面", f"最多連續 {worst} 場為負"))
    last = charges[-1] if charges else None
    out.append(("✅" if last == "+" else "ℹ️", "集尾", f"最後一場 protagonist_charge={last or '未標'}"))
    return out


def render(stage: int, episode: str, findings: List[Finding]) -> str:
    rows = "\n".join(f"| {m} | {k} | {d} |" for m, k, d in findings)
    return (f"# 荒木漫畫術 lens：Stage {stage} · {episode}\n\n"
            "> 只給建議、不擋關。由 `scripts/craft/araki_review.py` 產生；判斷規則見 "
            "`references/craft/araki-manga-craft/SKILL.md`。\n\n"
            "## 確定性檢查\n\n| 結果 | 項目 | 說明 |\n|---|---|---|\n" + rows + "\n\n"
            "## Agent 審查\n\n（請 Agent 依 SKILL.md 的心智模型 1–6 補上發現、證據、修法）\n")


def default_bible(project_dir: Path) -> Path:
    for cand in (project_dir / "adapt" / "character-bible.md", project_dir / "assets.md"):
        if cand.exists():
            return cand
    return project_dir / "adapt" / "character-bible.md"


def run(project_dir: Path, stage: int, episode: str, bible: Optional[Path] = None,
        handoff: Optional[Path] = None, out: Optional[Path] = None) -> Path:
    if stage == 2:
        findings = review_stage2(bible or default_bible(project_dir))
    else:
        hp = handoff or project_dir / f"handoff-{episode.lower()}.json"
        findings = (review_stage3(json.loads(hp.read_text(encoding="utf-8")), episode) if hp.exists()
                    else [("⚠️", "輸入", f"找不到 {hp.name}，略過")])
    target = out or project_dir / "review" / "craft" / f"stage-{stage}-{LENS}-{episode.lower()}.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render(stage, episode, findings), encoding="utf-8")
    return target


def self_test() -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp)
        (p / "assets.md").write_text(
            "## 1. 主角甲（20歲）\n黑髮、藍袍。\n## 2. 反派乙（30歲）\n動機：奪權。弱點：怕水。過去：棄子。\n## 共用風格\n無\n",
            encoding="utf-8")
        t2 = run(p, 2, "EP01").read_text(encoding="utf-8")
        h = {"episodes": [{"episode_id": "EP01", "scenes": [{"protagonist_charge": c} for c in "---+"]}]}
        (p / "handoff-ep01.json").write_text(json.dumps(h), encoding="utf-8")
        t3 = run(p, 3, "EP01").read_text(encoding="utf-8")
        ok = ("主角甲（20歲）：只有外觀描述" in t2 and "反派乙（30歲）：動機、弱點、過去都有" in t2
              and "沒寫他貫徹的哲學" in t2 and "共用風格" not in t2
              and "淨值 -2" in t3 and "最多連續 3 場" in t3)
    print("araki_review self-test:", "PASS" if ok else "FAIL")
    return ok


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="araki-manga-craft 建議性審查（不擋關）")
    ap.add_argument("--project-dir", type=Path)
    ap.add_argument("--stage", type=int, choices=[2, 3])
    ap.add_argument("--episode", default="EP01")
    ap.add_argument("--bible", type=Path, help="角色文件（預設 adapt/character-bible.md 或 assets.md）")
    ap.add_argument("--handoff", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if a.self_test:
        return 0 if self_test() else 1
    if not a.project_dir or a.stage is None:
        ap.error("需要 --project-dir 與 --stage")
    print(run(a.project_dir, a.stage, a.episode, a.bible, a.handoff, a.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
