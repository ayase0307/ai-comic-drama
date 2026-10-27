#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mckee-scene lens: advisory stage-3 script review (script-review-epXX). Never blocks."""
from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import duration_seconds, keep_agent_section  # noqa: E402,F401

LENS = "mckee"
SIGNS = {"+", "-", "+/-", "0"}
ON_THE_NOSE = re.compile(r"我(很|好|真的|非常|太)(生氣|生气|難過|难过|開心|开心|傷心|伤心|害怕|緊張|紧张|失望|愛你|爱你)|我的意思是|我想告訴你|我想告诉你")
EXPOSITION = re.compile(r"你也知道|你知道的|眾所周知|众所周知|我們認識|我们认识|還記得.*嗎|还记得.*吗|話說|话说")
SHORT_DRAMA_SCENE_MAX_S = 60

Finding = Tuple[str, str, str]


def scene_rows(ep: Dict[str, Any]) -> List[Dict[str, Any]]:
    return list(ep.get("scenes", []))


def review(handoff: Dict[str, Any], episode: str) -> Tuple[List[Finding], List[str]]:
    ep = next((e for e in handoff.get("episodes", []) if str(e.get("episode_id", "")).upper() == episode.upper()), None)
    if ep is None:
        return [("⚠️", "輸入", f"handoff 裡沒有 {episode}")], []
    out: List[Finding] = []
    table: List[str] = []
    scenes = scene_rows(ep)
    annotated = [s for s in scenes if s.get("value_open") in SIGNS and s.get("value_close") in SIGNS]
    if not annotated:
        out.append(("ℹ️", "價值轉折", f"{len(scenes)} 場都沒有 value_at_stake/value_open/value_close，請 Agent 先逐場標註（這是 McKee 審查的第一步）"))
    closes: List[str] = []
    for sc in scenes:
        sid = sc.get("scene_id", "?")
        vo, vc, val = sc.get("value_open"), sc.get("value_close"), sc.get("value_at_stake", "")
        if vo in SIGNS and vc in SIGNS:
            if vo == vc:
                out.append(("⚠️", "Nonevent", f"{sid}：價值「{val}」從 {vo} 到 {vc} 沒有變化，建議刪掉、合併，或補一個轉折"))
            closes.append(vc)
        dur = duration_seconds(sc.get("estimated_duration_seconds"))
        if dur > SHORT_DRAMA_SCENE_MAX_S:
            out.append(("ℹ️", "場長", f"{sid}：{dur:.0f}s，超過短劇建議的 {SHORT_DRAMA_SCENE_MAX_S}s【推論】，請確認裡面有不止一個轉折"))
        for d in sc.get("dialogue", []):
            t = str(d.get("text", ""))
            if ON_THE_NOSE.search(t):
                out.append(("⚠️", "On-the-nose 候選", f"{sid}：「{t[:30]}」直接說出情緒，請考慮改成動作或選擇"))
            if EXPOSITION.search(t):
                out.append(("⚠️", "Exposition 候選", f"{sid}：「{t[:30]}」像是在交代雙方都知道的事，請考慮改成彈藥"))
        table.append(f"| {sid} | {val or '—'} | {vo or '—'} | {vc or '—'} | {str(sc.get('dramatic_turn', ''))[:40] or '—'} |")
    streak, worst, prev = 0, 0, None
    for c in closes:
        streak = streak + 1 if c == prev else 1
        worst, prev = max(worst, streak), c
    if closes:
        out.append(("✅" if worst < 3 else "⚠️", "正負交替", f"收場正負號最多連續 {worst} 場相同（McKee：重複是節奏的敵人）"))
    debts = [d for d in handoff.get("debt_ledger", []) if d.get("status") == "open" and (not d.get("payoff_ep") or str(d.get("payoff_ep")).upper() in ("TBD", "UNSCHEDULED"))]
    if debts:
        out.append(("⚠️", "Setup/Payoff", f"{len(debts)} 個鋪梗還沒排定回收集數：{', '.join(d.get('debt_id', '?') for d in debts)}"))
    if not any(f[0] == "⚠️" for f in out):
        out.append(("✅", "總結", "確定性檢查沒有發現問題"))
    return out, table


def render(episode: str, findings: List[Finding], table: List[str]) -> str:
    rows = "\n".join(f"| {m} | {k} | {d} |" for m, k, d in findings)
    scene_tbl = ("\n## 場次價值表\n\n| 場 | 價值 | 開場 | 收場 | 轉折 |\n|---|---|---|---|---|\n" + "\n".join(table) + "\n") if table else ""
    return (f"# McKee 劇本審查（script-review）：Stage 3 · {episode}\n\n"
            "> 只給建議、不擋關。由 `scripts/craft/mckee_review.py` 產生；判斷規則見 "
            "`references/craft/mckee-scene/SKILL.md`。\n\n"
            "## 確定性檢查\n\n| 結果 | 項目 | 說明 |\n|---|---|---|\n" + rows + "\n" + scene_tbl +
            "\n## Agent 審查\n\n（請 Agent 依 SKILL.md 的模型 1–6 逐場補上：價值與正負、轉折點、Gap、問題台詞、修法）\n")


def run(project_dir: Path, episode: str, handoff: Optional[Path] = None, out: Optional[Path] = None) -> Path:
    hp = handoff or project_dir / f"handoff-{episode.lower()}.json"
    if hp.exists():
        findings, table = review(json.loads(hp.read_text(encoding="utf-8-sig")), episode)
    else:
        findings, table = [("⚠️", "輸入", f"找不到 {hp.name}，略過")], []
    target = out or project_dir / "review" / "craft" / f"stage-3-{LENS}-script-review-{episode.lower()}.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(keep_agent_section(render(episode, findings, table), target), encoding="utf-8")
    return target


def self_test() -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp)
        h = {"debt_ledger": [{"debt_id": "d1", "status": "open"}],
             "episodes": [{"episode_id": "EP01", "scenes": [
                 {"scene_id": "S1", "value_at_stake": "自由", "value_open": "-", "value_close": "-",
                  "estimated_duration_seconds": 90, "dialogue": [{"text": "我很生氣！"}]},
                 {"scene_id": "S2", "value_open": "+", "value_close": "-", "dialogue": [{"text": "你也知道我們認識二十年了"}]},
                 {"scene_id": "S3", "value_open": "+", "value_close": "-"}]}]}
        (p / "handoff-ep01.json").write_text(json.dumps(h, ensure_ascii=False), encoding="utf-8")
        t = run(p, "EP01").read_text(encoding="utf-8-sig")
        ok = all(k in t for k in ["S1：價值「自由」", "S1：90s", "On-the-nose 候選", "Exposition 候選",
                                   "最多連續 3 場相同", "d1", "| S2 |"])
    print("mckee_review self-test:", "PASS" if ok else "FAIL")
    return ok


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="mckee-scene 階段 3 劇本審查（建議性，不擋關）")
    ap.add_argument("--project-dir", type=Path)
    ap.add_argument("--episode", default="EP01")
    ap.add_argument("--handoff", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if a.self_test:
        return 0 if self_test() else 1
    if not a.project_dir:
        ap.error("需要 --project-dir")
    print(run(a.project_dir, a.episode, a.handoff, a.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
