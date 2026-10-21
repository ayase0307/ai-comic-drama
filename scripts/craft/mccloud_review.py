#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mccloud-panels lens: advisory stage-4 shot-transition analysis over layer2/*.json. Never blocks."""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

LENS = "mccloud"
WIDE = ("全景", "遠景", "远景", "大全景", "establishing", "wide", "extreme long", "long shot")
MONOTONE_RATIO = 0.6
SAME_SIZE_RUN = 3

Finding = Tuple[str, str, str]


def load_shots(project_dir: Path, episode: str, layer2_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    d = layer2_dir or project_dir / "layer2"
    shots: List[Dict[str, Any]] = []
    for p in sorted(d.glob("layer2-*.json")) if d.exists() else []:
        try:
            seg = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        sid = str(seg.get("segment_id") or p.stem.replace("layer2-", ""))
        if episode and episode.upper() not in sid.upper() and episode.upper() not in p.stem.upper():
            continue
        for sh in seg.get("shots", []):
            shots.append({
                "segment": sid,
                "scene": str(seg.get("scene_id", sid)),
                "shot_id": sh.get("shot_id", "?"),
                "chars": tuple(sorted(sh.get("character_ids") or [])),
                "size": str((sh.get("camera_optics") or {}).get("shot_size", "")).strip(),
                "beat": sh.get("dramatic_beat_type", ""),
                "duration": float(sh.get("duration") or 0),
            })
    return shots


def is_wide(size: str) -> bool:
    low = size.lower()
    return any(w in low for w in WIDE)


def classify(a: Dict[str, Any], b: Dict[str, Any]) -> str:
    if a["scene"] != b["scene"]:
        return "scene-to-scene"
    if not b["chars"] and is_wide(b["size"]):
        return "aspect-to-aspect"
    if a["chars"] and b["chars"] and a["chars"] != b["chars"]:
        return "subject-to-subject"
    if a["size"] and a["size"] == b["size"]:
        return "moment-to-moment"
    return "action-to-action"


def review(shots: List[Dict[str, Any]]) -> Tuple[List[Finding], List[str]]:
    if len(shots) < 2:
        return [("⚠️", "輸入", f"只找到 {len(shots)} 個 shot，無法分析轉場")], []
    trans = [classify(a, b) for a, b in zip(shots, shots[1:])]
    cnt = Counter(trans)
    total = len(trans)
    out: List[Finding] = []
    dist = "、".join(f"{k} {v}（{v / total:.0%}）" for k, v in cnt.most_common())
    out.append(("ℹ️", "轉場分布", dist))
    top, n = cnt.most_common(1)[0]
    out.append(("⚠️" if n / total > MONOTONE_RATIO else "✅", "單調度",
                f"最多的是 {top}，佔 {n / total:.0%}（門檻 {MONOTONE_RATIO:.0%}）"))
    if "aspect-to-aspect" not in cnt:
        out.append(("⚠️", "情緒留白", "全集沒有 aspect-to-aspect（無角色的空鏡、環境），建議在情緒點或段落之間加 1 到 2 個"))
    run, worst, where, prev = 0, 0, "", None
    for sh in shots:
        run = run + 1 if sh["size"] and sh["size"] == prev else 1
        if run > worst:
            worst, where = run, f"{sh['segment']}/{sh['shot_id']}"
        prev = sh["size"]
    out.append(("⚠️" if worst >= SAME_SIZE_RUN else "✅", "景別變化",
                f"同一景別最多連續 {worst} 個 shot（到 {where} 為止；門檻 {SAME_SIZE_RUN}）"))
    sizes = Counter(s["size"] or "未填" for s in shots)
    out.append(("ℹ️", "景別分布", "、".join(f"{k} {v}" for k, v in sizes.most_common())))
    rows = [f"| {a['segment']}/{a['shot_id']} → {b['segment']}/{b['shot_id']} | {a['size'] or '—'} → {b['size'] or '—'} | {t} |"
            for (a, b), t in zip(zip(shots, shots[1:]), trans)]
    return out, rows


def render(episode: str, findings: List[Finding], rows: List[str]) -> str:
    body = "\n".join(f"| {m} | {k} | {d} |" for m, k, d in findings)
    table = ("\n## 轉場明細（自動分類，請 Agent 確認）\n\n| 剪接點 | 景別 | 推定轉場 |\n|---|---|---|\n" + "\n".join(rows) + "\n") if rows else ""
    return (f"# McCloud 分鏡轉場 lens：Stage 4 · {episode}\n\n"
            "> 只給建議、不擋關。由 `scripts/craft/mccloud_review.py` 產生；判斷規則見 "
            "`references/craft/mccloud-panels/SKILL.md`。\n\n"
            "## 確定性檢查\n\n| 結果 | 項目 | 說明 |\n|---|---|---|\n" + body + "\n" + table +
            "\n## Agent 審查\n\n（請 Agent 確認誤判，並依模型 1–4 補建議）\n")


def run(project_dir: Path, episode: str, layer2_dir: Optional[Path] = None, out: Optional[Path] = None) -> Path:
    findings, rows = review(load_shots(project_dir, episode, layer2_dir))
    target = out or project_dir / "review" / "craft" / f"stage-4-{LENS}-{episode.lower()}.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render(episode, findings, rows), encoding="utf-8")
    return target


def self_test() -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp)
        (p / "layer2").mkdir()
        def shot(i: int, chars: List[str], size: str) -> Dict[str, Any]:
            return {"shot_id": f"SH{i}", "character_ids": chars, "camera_optics": {"shot_size": size}, "duration": 3}
        seg1 = {"segment_id": "EP01-S01-A", "scene_id": "EP01-S01",
                "shots": [shot(1, ["a"], "中景"), shot(2, ["a"], "中景"), shot(3, ["a"], "中景"), shot(4, ["b"], "近景")]}
        seg2 = {"segment_id": "EP01-S02-A", "scene_id": "EP01-S02", "shots": [shot(1, ["a"], "近景")]}
        for s in (seg1, seg2):
            (p / "layer2" / f"layer2-{s['segment_id']}.json").write_text(json.dumps(s, ensure_ascii=False), encoding="utf-8")
        t = run(p, "EP01").read_text(encoding="utf-8")
        ok = all(k in t for k in ["moment-to-moment 2", "subject-to-subject 1", "scene-to-scene 1",
                                   "最多連續 3 個 shot", "沒有 aspect-to-aspect"])
    print("mccloud_review self-test:", "PASS" if ok else "FAIL")
    return ok


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="mccloud-panels 階段 4 轉場分析（建議性，不擋關）")
    ap.add_argument("--project-dir", type=Path)
    ap.add_argument("--episode", default="EP01")
    ap.add_argument("--layer2-dir", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if a.self_test:
        return 0 if self_test() else 1
    if not a.project_dir:
        ap.error("需要 --project-dir")
    print(run(a.project_dir, a.episode, a.layer2_dir, a.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
