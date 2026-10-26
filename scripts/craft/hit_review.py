#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ai-drama-hit-method lens: advisory checks for stage 0/1/3. Never blocks (exit 0 unless bad CLI usage).

只適用「短劇短集」模式（使用者明確選擇 series_format=short）。長篇漫劇（預設）專案照樣可以跑，
但報告開頭會標明本 lens 的開場 5 秒鉤子、60 秒空窗、集尾鉤子等短劇標準不適用，不得據此把故事切短或壓縮事件。"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "adapt"))
from _common import duration_seconds, keep_agent_section  # noqa: E402,F401
from series_format import SHORT, project_format  # noqa: E402

LONGFORM_NOTICE = (
    "> ⚠️ **本專案是長篇漫劇（預設）**：爆款方法論 lens 只在短劇短集模式（使用者明確選擇）使用。"
    "以下開場鉤子、空窗秒數、集尾鉤子等短劇標準僅供參考，**不得據此把故事切成短集或壓縮事件交代**。\n\n"
)

LENS = "hit"
BANNED_TITLE_WORDS = ["熱播", "热播", "爆款", "強推", "强推"]
ALLOWED_TITLE_PUNCT = set("，,！!：:？?“”\"")
AUDIENCE_KEYS = ["受眾", "受众", "目標觀眾", "目标观众", "給誰看", "给谁看"]
CORE_KEYS = ["內核", "内核", "情緒缺口", "情绪缺口"]
SHELL_KEYS = ["外殼", "外壳", "世界觀", "世界观", "題材", "题材"]
HOOK_MARKERS = re.compile(r"[？?…]|……|——$|預言|预言|竟然|原來|原来|到底|誰|谁")
OPENING_LIMIT_S = 5.0
DEAD_ZONE_LIMIT_S = 60.0

Finding = Tuple[str, str, str]


def load_handoff(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def find_episode(handoff: Dict[str, Any], episode: str) -> Optional[Dict[str, Any]]:
    for ep in handoff.get("episodes", []):
        if str(ep.get("episode_id", "")).upper() == episode.upper():
            return ep
    return None


def scene_spans(ep: Dict[str, Any]) -> List[Tuple[float, float, Dict[str, Any]]]:
    spans, t = [], 0.0
    for sc in ep.get("scenes", []):
        dur = duration_seconds(sc.get("estimated_duration_seconds"))
        spans.append((t, t + dur, sc))
        t += dur
    return spans


def first_line_time(ep: Dict[str, Any]) -> Optional[float]:
    for start, _end, sc in scene_spans(ep):
        for d in sc.get("dialogue", []):
            if "start" in d:
                return float(d["start"])
            return start
    return None


def first_line_has_timestamp(ep: Dict[str, Any]) -> bool:
    """第一句台詞是否有真實時間戳（#33：沒有就只能退回場景起點，不能當證據）。"""
    for _s, _e, sc in scene_spans(ep):
        for d in sc.get("dialogue", []):
            return "start" in d
    return False


def check_title(title: str) -> List[Finding]:
    out: List[Finding] = []
    for w in BANNED_TITLE_WORDS:
        if w in title:
            out.append(("❌", "標題合規", f"標題含平台禁用行銷詞「{w}」"))
    odd = sorted({ch for ch in title if not ch.isalnum() and not ch.isspace() and ch not in ALLOWED_TITLE_PUNCT})
    if odd:
        out.append(("⚠️", "標題合規", f"標題含特殊符號 {''.join(odd)}（抖音漫劇規範只允許逗號、感嘆號、冒號、問號、雙引號）"))
    if not out:
        out.append(("✅", "標題合規", f"「{title}」沒有命中禁用詞或特殊符號"))
    return out


def review_stage0(project_dir: Path) -> List[Finding]:
    p = project_dir / "project.md"
    if not p.exists():
        return [("⚠️", "定位三行", "找不到 project.md，略過")]
    text = p.read_text(encoding="utf-8")
    out: List[Finding] = []
    for label, keys in (("受眾", AUDIENCE_KEYS), ("內核", CORE_KEYS), ("外殼", SHELL_KEYS)):
        hit = any(k in text for k in keys)
        out.append(("✅" if hit else "⚠️", "受眾→內核→外殼", f"{label}：{'已寫' if hit else '沒寫，建議補一行'}"))
    m = re.search(r"^#\s*(.+)$", text, re.M)
    if m:
        out += check_title(m.group(1).strip())
    return out


def review_stage1(handoff: Dict[str, Any]) -> List[Finding]:
    out: List[Finding] = []
    eps = handoff.get("episodes", [])
    for ep in eps:
        eid = ep.get("episode_id", "?")
        if not ep.get("act_out_type"):
            out.append(("⚠️", "集尾期待", f"{eid} 沒有 act_out_type（集尾的期待類型）"))
        if not ep.get("episode_goal"):
            out.append(("⚠️", "集目標", f"{eid} 沒有 episode_goal"))
    if eps and len(eps) >= 3:
        out.append(("ℹ️", "前三集", "請由 Agent 確認：主線走向與主要人設是否在前 3 集交代完畢"))
    if not out:
        out.append(("✅", "分集結構", f"{len(eps)} 集都有 episode_goal 和 act_out_type"))
    return out


def review_stage3(ep: Dict[str, Any]) -> List[Finding]:
    out: List[Finding] = []
    spans = scene_spans(ep)
    first = first_line_time(ep)
    if first is None:
        out.append(("⚠️", "開場鉤子", "整集沒有台詞，無法估算開場時間"))
    elif not first_line_has_timestamp(ep):
        out.append(("ℹ️", "開場鉤子", "台詞沒有時間戳（start），無法量秒數；請 Agent 讀開場內容判斷 5 秒內有無衝突或反常資訊"))
    else:
        mark = "✅" if first <= OPENING_LIMIT_S else "⚠️"
        out.append((mark, "開場鉤子", f"第一句台詞在 {first:.1f}s（建議 ≤ {OPENING_LIMIT_S:.0f}s 進入衝突或反常資訊）"))
    missing = [sc.get("scene_id", "?") for _s, _e, sc in spans if not str(sc.get("dramatic_turn", "")).strip()]
    if missing:
        out.append(("⚠️", "每場轉折", f"沒寫 dramatic_turn 的場次：{', '.join(missing)}"))
    else:
        out.append(("✅", "每場轉折", f"{len(spans)} 場都有 dramatic_turn"))
    longest, where = 0.0, ""
    for s, e, sc in spans:
        if (e - s) > longest:
            longest, where = e - s, sc.get("scene_id", "?")
    if longest > DEAD_ZONE_LIMIT_S:
        out.append(("⚠️", "空窗", f"{where} 長 {longest:.0f}s 卻只算一個轉折，建議拆成兩個以上的小反轉，或壓縮非戲點"))
    elif spans:
        out.append(("✅", "空窗", f"最長的單場是 {where}（{longest:.0f}s），在 {DEAD_ZONE_LIMIT_S:.0f}s 以內"))
    if spans:
        last = spans[-1][2]
        lines = last.get("dialogue", [])
        tail = lines[-1]["text"] if lines else ""
        hooky = bool(HOOK_MARKERS.search(tail)) or bool(ep.get("act_out_type"))
        out.append(("✅" if hooky else "⚠️", "集尾期待", f"最後一句「{tail[:30]}」；act_out_type={ep.get('act_out_type') or '未填'}"))
    title = str(ep.get("title", ""))
    if title:
        out += check_title(title)
    return out


def render(stage: int, episode: str, findings: List[Finding], longform: bool = False) -> str:
    rows = "\n".join(f"| {m} | {k} | {d} |" for m, k, d in findings)
    return (
        f"# 爆款方法論 lens：Stage {stage} · {episode}\n\n"
        + (LONGFORM_NOTICE if longform else "") +
        "> 只給建議、不擋關。由 `scripts/craft/hit_review.py` 產生；判斷規則見 "
        "`references/craft/ai-drama-hit-method/SKILL.md`。\n\n"
        "## 確定性檢查\n\n| 結果 | 項目 | 說明 |\n|---|---|---|\n" + rows + "\n\n"
        "## Agent 審查\n\n（請 Agent 依 SKILL.md 的「Agent 審查清單」逐項補上：✅／⚠️／❌、證據、一句修法）\n"
    )


def run(project_dir: Path, stage: int, episode: str, handoff_path: Optional[Path], out: Optional[Path]) -> Path:
    if stage == 0:
        findings = review_stage0(project_dir)
    else:
        hp = handoff_path or project_dir / f"handoff-{episode.lower()}.json"
        if not hp.exists():
            findings = [("⚠️", "輸入", f"找不到 {hp.name}，略過")]
        else:
            h = load_handoff(hp)
            if stage == 1:
                findings = review_stage1(h)
            else:
                ep = find_episode(h, episode)
                findings = review_stage3(ep) if ep else [("⚠️", "輸入", f"handoff 裡沒有 {episode}")]
    target = out or project_dir / "review" / "craft" / f"stage-{stage}-{LENS}-{episode.lower()}.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    longform = project_format(project_dir) != SHORT
    target.write_text(keep_agent_section(render(stage, episode, findings, longform), target), encoding="utf-8")
    return target


def self_test() -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp)
        (p / "project.md").write_text("# 熱播！【重生】\n受眾：25-35 女性\n", encoding="utf-8")
        h = {"episodes": [{"episode_id": "EP01", "title": "測試", "act_out_type": "",
                           "scenes": [{"scene_id": "S01", "estimated_duration_seconds": 70, "dramatic_turn": "",
                                       "dialogue": [{"text": "你好", "start": 8.0}]}]}]}
        (p / "handoff-ep01.json").write_text(json.dumps(h, ensure_ascii=False), encoding="utf-8")
        t0 = run(p, 0, "EP01", None, None).read_text(encoding="utf-8")
        t3 = run(p, 3, "EP01", None, None).read_text(encoding="utf-8")
        ok = ("禁用行銷詞「熱播」" in t0 and "【" in t0 and "內核：沒寫" in t0
              and "8.0s" in t3 and "沒寫 dramatic_turn" in t3 and "長 70s" in t3)
    print("hit_review self-test:", "PASS" if ok else "FAIL")
    return ok


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="ai-drama-hit-method 建議性審查（不擋關）")
    ap.add_argument("--project-dir", type=Path)
    ap.add_argument("--stage", type=int, choices=[0, 1, 3])
    ap.add_argument("--episode", default="EP01")
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
    print(run(a.project_dir, a.stage, a.episode, a.handoff, a.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
