#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
event_coverage.py — 改編「事件交代完整性」檢查

長篇漫劇（預設）以「把故事講清楚」為第一優先：原著每個關鍵事件都要有足夠鏡頭交代
起因 → 經過 → 結果，必要時再交代人物動機與時間／地點轉換。這支腳本把 adapt/source.json
的原著事件清單（story_units）和改編稿（handoff-ep*.json 的 scenes）逐一對帳，標出：

  full        完整交代（所需交代要素都有場景負責）
  partial     交代不全（有場景，但缺少某些交代要素，例如只演了結果、沒交代起因）
  unverified  有場景引用，但場景沒標註 event_exposition，無法確認交代了什麼
  compressed  被壓縮／合併（adaptation_changes 記為 compress／merge）
  skipped     被刪除／跳過（adaptation_changes 記為 remove，或未出現但有登記理由）
  missing     未交代且未登記（改編稿完全沒有這個事件）

凡是「沒有完整交代、且不是原著分級本來就預期的處理」的事件，都列入 needs_decision，
在階段 1 審核頁呈現給使用者逐條決定（補鏡頭交代／接受壓縮／接受刪除）。

資料約定（皆為選填，向下相容既有專案）：
- source.json story_units[*]：
    exposition_needs: ["起因", "經過", "結果"]   # 這個事件需要交代的要素；省略時用預設三項
    needs_motivation: true                        # 另需交代人物動機 → 加「動機」
    time_place_shift: true | "三天後・書院"       # 事件發生前有時間／地點轉換 → 加「時地」
- handoff scenes[*]：
    event_exposition: {"U01": ["起因", "經過"]}   # 這場戲替哪個事件交代了哪些要素

用法：
    python scripts/adapt/event_coverage.py --source adapt/source.json --handoff handoff-ep*.json
    python scripts/adapt/event_coverage.py --project-dir . --out adapt/event-coverage.md

結束碼：0＝無 MUST_KEEP 事件遺失；2＝有 MUST_KEEP 事件完全沒交代（missing）。
僅使用 Python 標準庫。
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

if sys.platform.startswith("win"):
    for _stream in (sys.stdout, sys.stderr):
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="replace")

DEFAULT_EXPOSITION = ["起因", "經過", "結果"]
MOTIVATION = "動機"
TRANSITION = "時地"

# 交代要素的同義詞（handoff 用英文或簡體寫也認得）
_BEAT_ALIASES = {
    "cause": "起因", "起因": "起因", "原因": "起因", "起": "起因",
    "process": "經過", "經過": "經過", "经过": "經過", "過程": "經過", "过程": "經過",
    "result": "結果", "結果": "結果", "结果": "結果", "後果": "結果",
    "motivation": MOTIVATION, "動機": MOTIVATION, "动机": MOTIVATION,
    "transition": TRANSITION, "time_place": TRANSITION, "時地": TRANSITION, "时地": TRANSITION,
    "時間地點": TRANSITION, "时间地点": TRANSITION, "轉場交代": TRANSITION,
}

STATUS_LABELS = {
    "full": "✅ 完整交代",
    "partial": "⚠️ 交代不全",
    "unverified": "❔ 未標註交代要素",
    "compressed": "🟧 被壓縮／合併",
    "skipped": "⛔ 被刪除／跳過",
    "missing": "❌ 未交代（未登記）",
}

# 原著分級本來就預期的處理：這些組合不需要再問使用者
_PLANNED = {("COMPRESS", "compressed"), ("MERGE", "compressed"), ("REMOVE", "skipped")}


def canonical_beat(name: Any) -> str:
    text = str(name or "").strip()
    return _BEAT_ALIASES.get(text.lower(), _BEAT_ALIASES.get(text, text))


def required_beats(unit: Dict[str, Any]) -> List[str]:
    """這個原著事件需要交代的要素（起因／經過／結果＋動機＋時地）。"""
    raw = unit.get("exposition_needs")
    beats = [canonical_beat(b) for b in raw] if isinstance(raw, list) and raw else list(DEFAULT_EXPOSITION)
    if unit.get("needs_motivation") and MOTIVATION not in beats:
        beats.append(MOTIVATION)
    if unit.get("time_place_shift") and TRANSITION not in beats:
        beats.append(TRANSITION)
    out: List[str] = []
    for b in beats:
        if b and b not in out:
            out.append(b)
    return out


def _mid(value: Any) -> float:
    if isinstance(value, dict):
        nums = [float(v) for v in (value.get("min"), value.get("max")) if isinstance(v, (int, float))]
        return sum(nums) / len(nums) if nums else 0.0
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _iter_scenes(handoffs: Iterable[Dict[str, Any]]):
    for h in handoffs:
        for ep in h.get("episodes", []) or []:
            for sc in ep.get("scenes", []) or []:
                yield ep, sc


def analyze_event_coverage(source_data: Dict[str, Any], handoffs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """逐一比對原著事件清單與改編稿，回傳每個事件的交代狀態與需要使用者決定的清單。"""
    units = [u for u in source_data.get("story_units", []) or [] if isinstance(u, dict) and u.get("unit_id")]
    must_keep_ids = {str(x) for x in source_data.get("must_keep", []) or []}

    scenes_by_ref: Dict[str, List[str]] = {}
    beats_by_ref: Dict[str, set] = {}
    declared_by_ref: Dict[str, bool] = {}
    seconds_by_ref: Dict[str, float] = {}
    changes_by_ref: Dict[str, List[str]] = {}

    for ep, sc in _iter_scenes(handoffs):
        sid = str(sc.get("scene_id") or ep.get("episode_id") or "?")
        refs = [str(r) for r in sc.get("source_refs", []) or []]
        expo = sc.get("event_exposition") if isinstance(sc.get("event_exposition"), dict) else {}
        share = _mid(sc.get("estimated_duration_seconds")) / len(refs) if refs else 0.0
        for r in refs:
            scenes_by_ref.setdefault(r, []).append(sid)
            seconds_by_ref[r] = seconds_by_ref.get(r, 0.0) + share
            if r in expo:
                declared_by_ref[r] = True
                beats_by_ref.setdefault(r, set()).update(canonical_beat(b) for b in expo.get(r) or [])
        for chg in sc.get("adaptation_changes", []) or []:
            ref = chg.get("source_ref")
            if ref:
                changes_by_ref.setdefault(str(ref), []).append(str(chg.get("type", "")).lower())

    events: List[Dict[str, Any]] = []
    for idx, u in enumerate(units, 1):
        uid = str(u["unit_id"])
        grade = str(u.get("expected_grade") or "KEEP_IF_POSSIBLE").upper()
        if uid in must_keep_ids:
            grade = "MUST_KEEP"
        need = required_beats(u)
        scenes = scenes_by_ref.get(uid, [])
        changes = changes_by_ref.get(uid, [])
        have = sorted(beats_by_ref.get(uid, set()) & set(need), key=need.index)
        lacking = [b for b in need if b not in have]

        if "remove" in changes and not scenes:
            status = "skipped"
        elif any(c in ("compress", "merge") for c in changes):
            status = "compressed"
        elif not scenes:
            status = "skipped" if changes else "missing"
        elif not declared_by_ref.get(uid):
            status = "unverified"
        elif lacking:
            status = "partial"
        else:
            status = "full"

        planned = (grade, status) in _PLANNED
        needs_decision = status != "full" and not planned
        reason = ""
        if status == "partial":
            reason = f"缺少交代：{'、'.join(lacking)}"
        elif status == "unverified":
            reason = "場景有引用，但沒標註 event_exposition，請確認起因／經過／結果是否都演到"
        elif status == "compressed":
            reason = "改編稿把這個事件壓縮或合併" + ("（原著分級即為壓縮／合併）" if planned else "；長篇模式預設要交代清楚，請使用者決定是否接受")
        elif status == "skipped":
            reason = "改編稿刪除／跳過這個事件" + ("（原著分級即為刪除）" if planned else "；請使用者決定是否接受")
        elif status == "missing":
            reason = "改編稿完全沒有這個事件，也沒在 adaptation_changes 登記理由"

        events.append({
            "order": idx,
            "unit_id": uid,
            "summary": u.get("summary", ""),
            "grade": grade,
            "required_beats": need,
            "covered_beats": have,
            "missing_beats": lacking if scenes else need,
            "scenes": scenes,
            "estimated_seconds": round(seconds_by_ref.get(uid, 0.0), 1),
            "changes": changes,
            "status": status,
            "status_label": STATUS_LABELS[status],
            "planned_by_grade": planned,
            "needs_decision": needs_decision,
            "reason": reason,
        })

    counts = {k: sum(1 for e in events if e["status"] == k) for k in STATUS_LABELS}
    must_keep_missing = [e["unit_id"] for e in events if e["grade"] == "MUST_KEEP" and e["status"] == "missing"]
    needs = [e for e in events if e["needs_decision"]]
    has_adaptation = any(True for _ in _iter_scenes(handoffs))
    return {
        "status": "FAIL" if must_keep_missing else ("WARN" if needs else "PASS"),
        "event_count": len(events),
        "has_adaptation": has_adaptation,
        "counts": counts,
        "must_keep_missing": must_keep_missing,
        "needs_decision": [e["unit_id"] for e in needs],
        "events": events,
    }


def render_markdown(res: Dict[str, Any], title: str = "事件交代完整性檢查") -> str:
    c = res["counts"]
    lines = [
        f"# {title}",
        "",
        "> 長篇漫劇預設以「把故事講清楚」為先：每個原著關鍵事件都要交代起因 → 經過 → 結果"
        "（需要時加人物動機、時間地點轉換）。下表由 `scripts/adapt/event_coverage.py` 產生，"
        "被壓縮、跳過或交代不全的事件要在階段 1 審核時由使用者決定。",
        "",
        f"- 原著事件數：{res['event_count']}",
        f"- 完整交代 {c['full']}｜交代不全 {c['partial']}｜未標註 {c['unverified']}｜"
        f"被壓縮 {c['compressed']}｜被跳過 {c['skipped']}｜未交代 {c['missing']}",
        f"- 待使用者決定：{len(res['needs_decision'])} 條",
    ]
    if not res.get("has_adaptation"):
        lines.append("- ℹ️ 尚無改編稿場景（handoff 沒有 scenes）；下表只列出原著事件與所需交代要素。")
    lines += [
        "",
        "| # | 事件 | 原著摘要 | 分級 | 需交代 | 已交代 | 對應場景 | 估計秒數 | 狀態 | 待決定 |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for e in res["events"]:
        lines.append(
            f"| {e['order']} | `{e['unit_id']}` | {e['summary']} | {e['grade']} | {'、'.join(e['required_beats'])} | "
            f"{'、'.join(e['covered_beats']) or '—'} | {'、'.join(e['scenes']) or '—'} | {e['estimated_seconds']:g} | "
            f"{e['status_label']} | {'**要**：' + e['reason'] if e['needs_decision'] else '—'} |"
        )
    if res["needs_decision"]:
        lines += ["", "## 請使用者逐條決定", ""]
        for e in res["events"]:
            if e["needs_decision"]:
                lines.append(f"- [ ] `{e['unit_id']}` {e['summary']} — {e['reason']}（補鏡頭交代／接受壓縮／接受刪除）")
    return "\n".join(lines) + "\n"


def load_inputs(project_dir: Optional[Path], source: Optional[Path], handoffs: List[str]):
    if project_dir is not None:
        source = source or project_dir / "adapt" / "source.json"
        if not handoffs:
            handoffs = sorted(str(p) for p in project_dir.glob("handoff-ep*.json"))
    if source is None:
        raise SystemExit("[錯誤] 需要 --source 或 --project-dir")
    source_data = json.loads(Path(source).read_text(encoding="utf-8"))
    paths: List[str] = []
    for h in handoffs:
        paths.extend(sorted(glob.glob(h)) or [h])
    handoff_data = [json.loads(Path(p).read_text(encoding="utf-8")) for p in paths]
    return source_data, handoff_data


def project_coverage(project_dir: Path) -> Optional[Dict[str, Any]]:
    """給審核頁用：讀專案的 source.json 與全部 handoff；讀不到回 None。"""
    try:
        source_data, handoff_data = load_inputs(project_dir, None, [])
    except (OSError, ValueError, SystemExit):
        return None
    return analyze_event_coverage(source_data, handoff_data)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="改編事件交代完整性檢查（長篇漫劇預設）")
    ap.add_argument("--project-dir", type=Path, default=None, help="專案根目錄（自動讀 adapt/source.json 與 handoff-ep*.json）")
    ap.add_argument("--source", type=Path, default=None, help="原著事件清單 source.json")
    ap.add_argument("--handoff", nargs="*", default=[], help="改編稿 handoff JSON（可多檔／萬用字元）")
    ap.add_argument("--out", type=Path, default=None, help="另存 Markdown 報告（例：adapt/event-coverage.md）")
    ap.add_argument("--json", action="store_true", help="輸出 JSON")
    a = ap.parse_args(argv)

    source_data, handoff_data = load_inputs(a.project_dir, a.source, a.handoff)
    res = analyze_event_coverage(source_data, handoff_data)
    md = render_markdown(res)
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(md, encoding="utf-8")
    print(json.dumps(res, ensure_ascii=False, indent=2) if a.json else md)
    return 2 if res["must_keep_missing"] else 0


if __name__ == "__main__":
    sys.exit(main())
