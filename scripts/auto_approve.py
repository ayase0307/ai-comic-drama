#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""`h3d approve --auto`：沒有未決卡、且符合使用者定案的政策時，自動核准一個階段並記錄依據。

為什麼：實際案子裡，使用者真正要拍板的事很少；其他階段 agent 依「使用者定好的政策」就能判斷。
但「能不能自動過」本身必須是使用者授權的，而且有些事永遠要人看：

  * 階段 0（定調五題）與階段 2（角色設定圖：臉和服裝）永遠要人決定，不能自動核准。
  * 階段 7 要求每個有畫外台詞的角色都有使用者本人定的音色（decisions.json 的 voice:<角色>）。
  * 授權來源：decisions.json 的 `auto_approve`（例如 `h3d decide auto_approve 1,3,4,5,6 --quote "..."`）。
  * 該階段在收件匣（scripts/review/inbox.py）裡不能有任何未決卡。
  * 階段 6 另外要求：驗收政策已由使用者定案、沒有未驗收段、沒有判重跑的段；
    技術 QA 的量化問題必須全部屬於政策的 accept 清單，才會自動帶覆寫理由。

核准一律走 project_state.approve_stage_detailed（正門），依據（哪條政策、原話、哪些 verdicts）
寫進該階段的 `auto_approval` 與 `auto_approval_history`，永遠留著。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

SCRIPTS_DIR = Path(__file__).resolve().parent
for candidate in (str(SCRIPTS_DIR), str(SCRIPTS_DIR / "storyboard"), str(SCRIPTS_DIR / "review")):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

import decisions as decisions_mod  # noqa: E402
import project_state as ps  # noqa: E402
import verdicts as verdicts_mod  # noqa: E402


def _policy_ref(item: Dict[str, Any]) -> Dict[str, Any]:
    src = item.get("source") or {}
    return {"id": item.get("id"), "rule": item.get("rule"), "quote": src.get("quote"), "date": src.get("date"),
            "by": src.get("by", "user")}


def evaluate(root: Path, stage: Optional[int] = None) -> Dict[str, Any]:
    """判斷能否自動核准；回傳 {stage, eligible, blockers, basis, override_reason}（不寫檔）。"""
    import inbox  # scripts/review/inbox.py

    root = Path(root).expanduser().resolve()
    result: Dict[str, Any] = {"stage": stage, "eligible": False, "blockers": [], "basis": {}, "override_reason": None}
    if not ps.state_path(root).is_file():
        result["blockers"].append("沒有 review/project-state.json")
        return result
    if stage is None:
        stage, _ = ps.first_unapproved(root)
        result["stage"] = stage
        if stage is None:
            result["blockers"].append("所有階段都已有效核准")
            return result
    blockers: List[str] = result["blockers"]
    if stage in decisions_mod.NEVER_AUTO_STAGES:
        blockers.append(f"階段 {stage} 永遠要人決定（定調／角色設定圖），不能自動核准")
        return result
    try:
        data = decisions_mod.load(root)
    except decisions_mod.DecisionError as exc:
        blockers.append(str(exc))
        return result
    auto_stages, auto_item = decisions_mod.auto_approve_stages(data)
    if stage not in auto_stages:
        blockers.append(f"使用者沒有授權階段 {stage} 自動核准（h3d decide auto_approve <階段清單> --quote \"<使用者原話>\"）")
    missing = decisions_mod.missing_for_stage(root, stage)
    if missing:
        blockers.append("尚未定案：" + "、".join(missing))
    state = ps.load_state(root)
    if stage > 0:
        ok, detail = ps.require_approved(root, stage - 1)
        if not ok:
            blockers.append(f"前置階段未有效核准：{detail}")

    policies = [_policy_ref(auto_item)] if auto_item else []
    basis: Dict[str, Any] = {"policy": policies}
    cards = inbox.open_cards_for_stage(root, stage)
    if cards:
        blockers.append(f"收件匣還有 {len(cards)} 張未決卡（例如 {cards[0]['id']}：{cards[0]['title']}）")
    basis["open_cards"] = len(cards)

    if stage == 6:
        classified = verdicts_mod.classify(root)
        counts = classified["counts"]
        if not classified["policy_is_decided"]:
            blockers.append("驗收政策還沒由使用者定案（h3d decide acceptance_policy ...）")
        else:
            policies.append(_policy_ref(decisions_mod.get(data, "acceptance_policy")))
        if counts.get("unreviewed"):
            blockers.append(f"還有 {counts['unreviewed']} 段沒有目視結論")
        if counts.get("fail"):
            blockers.append(f"有 {counts['fail']} 段依政策要重跑")
        hard, technical = ps.stage6_issues(root)
        if hard:
            blockers.append(f"階段 6 有不可覆寫的錯誤：{hard[0]}")
        accept = set(classified["policy"].get("accept", []))
        tech_codes = sorted({c for r in classified["segments"].values() if r.get("qa_passed") is False
                             for c in r.get("qa_codes", [])})
        outside = [c for c in tech_codes if c not in accept]
        if technical and outside:
            blockers.append(f"技術 QA 問題 {', '.join(outside)} 不在驗收政策的 accept 清單，要人決定")
        if technical and not outside:
            result["override_reason"] = (f"自動核准：技術 QA 問題（{', '.join(tech_codes)}）屬驗收政策 accept，"
                                         "依 decisions.json acceptance_policy 放行")
        basis["verdicts"] = {
            "counts": counts,
            "segments": {sid: {"effective": r["effective"], "source": r.get("source")}
                         for sid, r in classified["segments"].items()},
        }
        basis["technical_overridden"] = technical[:50]
    if stage == 7:
        import inbox as inbox_mod
        speakers = inbox_mod.narration_speakers(root)
        voiced = decisions_mod.voice_decisions(data)
        lacking = [c for c in speakers if c not in voiced]
        if lacking:
            blockers.append("這些角色的音色還沒由使用者定案：" + "、".join(lacking))
        basis["voices"] = {c: _policy_ref(voiced[c]) for c in speakers if c in voiced}
        policies.extend(_policy_ref(voiced[c]) for c in speakers if c in voiced)

    entry = state["stages"][ps.stage_key(stage)]
    if not blockers:
        errors = (ps.stage_validation_errors(root, stage, allow_technical=True) if stage == 6
                  else ps.stage_validation_errors(root, stage))
        if errors:
            blockers.append(f"產物檢查失敗：{errors[0]}")
    counts_txt = ""
    if stage == 6 and "verdicts" in basis:
        c = basis["verdicts"]["counts"]
        counts_txt = f"；逐段結論 pass {c.get('pass', 0)}／warn {c.get('warn', 0)}"
    basis["summary"] = (f"依 {('、'.join(p['id'] for p in policies if p.get('id')) or '（無）')} 自動核准"
                        f"；收件匣未決卡 {len(cards)}{counts_txt}")
    basis["previous_status"] = entry.get("status")
    result["basis"] = basis
    result["eligible"] = not blockers
    return result


def run(root: Path, stage: Optional[int] = None, dry_run: bool = False) -> Dict[str, Any]:
    root = Path(root).expanduser().resolve()
    result = evaluate(root, stage)
    if not result["eligible"] or dry_run:
        return result
    stage = result["stage"]
    state = ps.load_state(root)
    entry = state["stages"][ps.stage_key(stage)]
    if entry.get("status") != "awaiting_user_approval" or entry.get("review_snapshot") != ps.stage_snapshot(root, stage):
        # 收件匣就是審核依據：把本階段標成待核並綁當下快照，再走正門核准。
        ps.mark_awaiting_review(root, state, stage)
    quote = next((p.get("quote") for p in result["basis"]["policy"] if p.get("id") == "auto_approve"), "")
    note = f"自動核准（h3d approve --auto）：依使用者授權「{quote}」；{result['basis']['summary']}"
    ok, detail = ps.approve_stage_detailed(root, stage, note, result["override_reason"],
                                           auto_approval=result["basis"])
    result["approved"] = ok
    if not ok:
        result["eligible"] = False
        result["blockers"].append(detail)
    return result


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="h3d approve",
        description="自動核准：沒有未決卡且符合 decisions.json 政策時核准並記錄依據（只支援 --auto）",
        epilog="人工核准請照 h3d next 指示用 build_stage_review.py --approve-stage N --user-note \"<使用者原話>\"",
    )
    parser.add_argument("--auto", action="store_true", help="自動核准（必填；人工核准不走這裡）")
    parser.add_argument("--stage", type=int, choices=range(8), help="指定階段；預設為第一個未有效核准的階段")
    parser.add_argument("--dry-run", action="store_true", help="只判斷能不能自動核准，不寫檔")
    parser.add_argument("--root", type=Path, default=Path("."), help="專案根目錄")
    parser.add_argument("--json", action="store_true", help="以 JSON 輸出")
    args = parser.parse_args(argv)
    if not args.auto:
        print("❌ h3d approve 只做自動核准（--auto）。人工核准：照 h3d next 用 build_stage_review.py --approve-stage。",
              file=sys.stderr)
        return 2
    result = run(args.root, args.stage, dry_run=args.dry_run)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["eligible"] else 1
    stage = result["stage"]
    if result["eligible"]:
        verb = "可以自動核准（乾跑）" if args.dry_run else "已自動核准"
        print(f"✅ 階段 {stage} {verb}：{result['basis'].get('summary', '')}")
        if result.get("override_reason"):
            print(f"   技術 QA 覆寫理由：{result['override_reason']}")
        return 0
    print(f"⛔ 階段 {stage} 不能自動核准：")
    for item in result["blockers"]:
        print(f"  - {item}")
    print("要人決定的事請用 h3d inbox 產生收件匣交給使用者。")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
