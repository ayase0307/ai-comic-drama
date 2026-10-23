#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""`h3d next`：讓程式決定下一步。

讀 review/project-state.json（含各階段核准快照的 hash 與依賴）、decisions.json、
review/verdicts.json、videos/qa-report.json、送件 ledger 與依賴帳本，回答四件事：

  1. 目前在哪個階段
  2. 卡在哪（阻斷項）
  3. 下一步「唯一一條」指令（或必須停下回報時，明講停下）
  4. 該讀哪一頁 reference

設計原則：
  * 只讀不寫。這裡不改任何檔案，也不重複門禁邏輯——判斷一律呼叫 project_state／
    decisions／verdicts 的既有函式。
  * 一次只給一條指令。agent 不用自己排流程，也就沒有空間跳步。
  * 需要使用者回答時（定案、核准），指令裡的使用者原話位置留成 <使用者原話>，
    不准 agent 自己填。
"""
from __future__ import annotations

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

H3D = f'python "{(SCRIPTS_DIR / "h3d.py").as_posix()}"'
REVIEW = f'python "{(SCRIPTS_DIR / "build_stage_review.py").as_posix()}"'
CHECK = f'python "{(SCRIPTS_DIR / "stage_content_checks.py").as_posix()}"'
INIT = f'python "{(SCRIPTS_DIR / "init_project.py").as_posix()}"'

STAGE_REFERENCES: Dict[int, List[str]] = {
    0: ["references/pipeline.md", "references/styles.md"],
    1: ["references/adapt/novel-to-manju.md"],
    2: ["references/consistency.md", "references/styles.md"],
    3: ["references/adapt/screenplay-format.md"],
    4: ["references/storyboard/cinematic-director.md"],
    5: ["references/h3/prompt-formats.md", "references/tooling.md"],
    6: ["references/tooling.md §2.5–2.7", "references/skill-guide.md「階段 6 生成：怎麼做才穩」"],
    7: ["references/tooling.md §2.7", "references/skill-guide.md「階段 7 組裝交付與配音決策」"],
}

SKELETON = f'python "{(SCRIPTS_DIR / "storyboard" / "handoff_to_skeleton.py").as_posix()}"'


def _episode_of(text: str) -> Optional[str]:
    import re
    m = re.search(r"\b(EP\d+)", text or "", re.I)
    return m.group(1).upper() if m else None


def _episodes(root: Path) -> List[str]:
    import re
    eps = set()
    for pattern in ("handoff-ep*.json", "layer2/layer2-EP*.json", "script-ep*.md"):
        for path in root.glob(pattern):
            m = re.search(r"ep(\d+)", path.name, re.I)
            if m:
                eps.add(f"EP{m.group(1)}")
    return sorted(eps, key=lambda e: int(e[2:]))


def stage4_producer(root: Path, errors: List[str]) -> tuple:
    """階段 4 下一步：還沒有 layer2 就先跑 handoff_to_skeleton（#36）；有了才補構圖，集號代換成真值（#44）。"""
    if not list((root / "layer2").glob("layer2-*.json")):
        handoffs = sorted(root.glob("handoff-ep*.json"))
        if not handoffs:
            return (f"{CHECK} --root . --stage 3",
                    "找不到 handoff-ep*.json：先回階段 3 跑 sync_script.py 產 handoff，再轉分鏡骨架。")
        return (f"{SKELETON} {handoffs[0].name} --out-dir layer2",
                f"先把 handoff 轉成 layer2 分鏡骨架（共 {len(handoffs)} 集，逐集執行），填實鏡頭內容後再補構圖。")
    rejected = [e for e in errors if "自檢退回" in e]
    episode = next((_episode_of(e) for e in errors if _episode_of(e)), None)
    ep_flag = f" --episode {episode}" if episode else ""
    action = f"補齊每一鏡對應的構圖 PNG（缺 {len(errors) - len(rejected)} 鏡"
    action += f"、自檢退回 {len(rejected)} 鏡要重畫）。" if rejected else "）。"
    return (f"{H3D} sketch --root .{ep_flag}", action)


def stage5_producer(root: Path, errors: List[str]) -> tuple:
    """階段 5 下一步：印完整 compile 參數，照抄就會寫出 prompts／segments（#56）。"""
    episodes = _episodes(root)
    missing = [e for e in episodes if not (root / f"segments-{e.lower()}.json").is_file()]
    episode = (missing[0] if missing else None) or next(
        (_episode_of(e) for e in errors if _episode_of(e)), None) or (episodes[0] if episodes else "EP01")
    parts = [f"{H3D} compile --layer2 \"layer2/layer2-{episode}-*.json\" --episode {episode} --project-root ."]
    if (root / "video-bible.json").is_file():
        parts.append("--bible video-bible.json")
        if (root / "video-bindings.json").is_file():
            parts.append("--bindings video-bindings.json")
    parts.append(f"--output-md prompts-{episode.lower()}.md --output-segments segments-{episode.lower()}.json --check")
    action = (f"編譯 {episode} 提示詞包並補齊參考圖" + (f"（還沒編的集：{'、'.join(missing)}）" if missing else "") + "。")
    return (" ".join(parts), action)


ACTIVE_JOB_STATUSES = {"waiting", "queued", "running"}


def _segment_files(root: Path) -> List[Path]:
    return sorted(root.glob("segments-ep*.json"))


def _segment_ids(path: Path) -> List[str]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return []
    items = raw if isinstance(raw, list) else raw.get("segments", [raw])
    return [str(i["segment_id"]) for i in items if isinstance(i, dict) and i.get("segment_id")]


def _active_jobs(root: Path) -> List[str]:
    found: List[str] = []
    for ledger in sorted(root.glob("videos/**/_fv-job-ledger.json")):
        try:
            payload = json.loads(ledger.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            continue
        for job in payload.get("jobs", []) or []:
            if str(job.get("status")) in ACTIVE_JOB_STATUSES:
                found.append(f"{job.get('segment_id', '?')}（{job.get('job_id', '?')}，{job.get('status')}）")
    return found


def _rel(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)


def _result(root: Path, stage: Optional[int], status: str) -> Dict[str, Any]:
    return {
        "root": str(root),
        "cwd": str(root),
        "stage": stage,
        "stage_title": ps.STAGE_TITLES.get(stage, "未初始化") if stage is not None else "未初始化",
        "status": status,
        "blocked_on": [],
        "action": "",
        "next_command": None,
        "read": [],
        "notes": [],
        "done": False,
    }


def _decision_step(res: Dict[str, Any], root: Path, missing: List[str]) -> Dict[str, Any]:
    did = missing[0]
    meta = decisions_mod.KNOWN_DECISIONS[did]
    res["blocked_on"].append("尚未定案：" + "、".join(decisions_mod.KNOWN_DECISIONS[m]["label"] for m in missing))
    hint = "recommended" if did in ("acceptance_policy", "style") else "<值>"
    res["action"] = (f"向使用者問「{meta['label']}」（附推薦值），拿到回覆後用使用者原話寫入。"
                     "不要自己替使用者決定。")
    if did == "style":
        res["action"] += (f" 預設推薦：{decisions_mod.RECOMMENDED_STYLE}，附樣圖 assets/styles/"
                          "sheet-14-xianxia-cinematic-semireal.jpg；使用者改選就寫他選的那套。")
    res["next_command"] = f'{H3D} decide {did} "{hint}" --quote "<使用者原話>" --root .'
    res["read"] = [meta["reference"]]
    return res


def _approve_command(stage: int, technical: List[str]) -> str:
    base = f'{REVIEW} --project-dir . --approve-stage {stage} --user-note "<使用者原話>"'
    if stage == 6 and technical:
        base += ' --override --reason "<使用者覆寫理由>"'
    return base


def _stage6_work(res: Dict[str, Any], root: Path) -> Optional[Dict[str, Any]]:
    """階段 6 的工作順序：送件 → 收件 → QA → 逐段結論 → 審核頁。回傳 None 表示可以建審核頁。"""
    seg_files = _segment_files(root)
    expected: List[str] = []
    for f in seg_files:
        expected.extend(_segment_ids(f))
    missing_videos = [sid for sid in expected if not (root / "videos" / f"{sid}.mp4").is_file()]
    if missing_videos:
        first_file = next((f for f in seg_files if missing_videos[0] in _segment_ids(f)), seg_files[0])
        res["blocked_on"].append(f"尚有 {len(missing_videos)} 段沒有影片（例如 {missing_videos[0]}）")
        res["action"] = "先收件、再補送尚未產出的分段（ledger 自動去重）。一次只跑一個 runner。"
        res["next_command"] = (f'{H3D} resume --segments {_rel(root, first_file)} '
                               f'--output-dir videos --root-dir .')
        return res

    hard, technical = ps.stage6_issues(root)
    drift = [h for h in hard if "DURATION_MISMATCH" in h or "duration_drift" in h]
    if drift:
        res["blocked_on"].append(drift[0])
        res["action"] = ("停下：出現時長漂移（duration_drift）。不要把漂移的片子拿去 QA 或重送，"
                         "照 references/tooling.md §4 處置並回報使用者。")
        res["next_command"] = None
        return res
    qa_stale = [h for h in hard if any(key in h for key in (
        "qa-report", "QA 報告", "QA 結果缺失", "hash", "非預期分段", "expected_segments", "source_segments", "來源分段檔"))]
    if qa_stale:
        res["blocked_on"].append(qa_stale[0])
        res["action"] = "QA 報告缺失或過期：一次對全部集數重跑技術 QA。"
        files = " ".join(_rel(root, f) for f in seg_files)
        res["next_command"] = f"{H3D} qa --segments {files} --videos-dir videos --out-json videos/qa-report.json"
        return res
    policy_fails = [h for h in hard if "驗收結論需重跑" in h]
    if policy_fails:
        res["blocked_on"].extend(policy_fails[:5])
        res["action"] = ("依驗收政策這些段要重跑：先改提示詞（不是只換 seed），重新核准階段 5 後只補送這些段。"
                         "照 references/h3/failure-triage.md 找原因。")
        res["next_command"] = f"{H3D} deps --root . --status"
        res["read"].append("references/h3/failure-triage.md")
        return res
    if hard:
        res["blocked_on"].append(hard[0])
        res["action"] = "先修正上面的錯誤；這類錯誤不能人工覆寫。"
        res["next_command"] = f"{H3D} status --root ."
        return res

    classified = verdicts_mod.classify(root)
    unreviewed = [sid for sid, row in classified["segments"].items() if row["effective"] == "unreviewed"]
    if unreviewed:
        sid = unreviewed[0]
        res["blocked_on"].append(f"尚有 {len(unreviewed)} 段沒有目視結論（例如 {sid}）")
        res["action"] = ("逐段看抽幀圖／並排對照圖，依驗收政策寫結論（pass／warn／fail＋一句原因＋證據圖）。"
                         "技術 QA 綠燈不等於看過。")
        res["next_command"] = (f'{H3D} verdict {sid} <pass|warn|fail> --reason "<一句話>" '
                               f'--evidence <證據圖路徑> --root .')
        return res
    if technical:
        res["notes"].append(f"技術 QA 有 {len(technical)} 項未過（PARTIAL）；核准時需使用者寫覆寫理由")
    return None


def _auto_step(res: Dict[str, Any], root: Path, stage: int) -> Optional[Dict[str, Any]]:
    """使用者授權了本階段自動核准、且收件匣沒有未決卡時，下一步就是 h3d approve --auto。"""
    try:
        data = decisions_mod.load(root)
        stages, _ = decisions_mod.auto_approve_stages(data)
        if stage not in stages:
            return None
        import auto_approve
        verdict = auto_approve.evaluate(root, stage)
    except Exception:
        return None
    if not verdict.get("eligible"):
        res["notes"].append("自動核准尚不符合：" + "；".join(verdict.get("blockers", [])[:2]))
        return None
    res["action"] = "本階段沒有未決卡，且符合使用者授權的自動核准政策：自動核准並記錄依據。"
    res["next_command"] = f"{H3D} approve --auto --stage {stage} --root ."
    return res


def plan(root: Path) -> Dict[str, Any]:
    root = Path(root).expanduser().resolve()
    if not ps.state_path(root).is_file():
        res = _result(root, None, "uninitialized")
        res["blocked_on"].append("沒有 review/project-state.json")
        res["action"] = "先建立專案骨架（會一併建立空的 decisions.json）。"
        res["next_command"] = f'{INIT} "{root.as_posix()}" --title "<劇名>" --episodes <集數>'
        res["read"] = ["references/pipeline.md"]
        return res

    try:
        state = ps.load_state(root)
    except ValueError as exc:
        res = _result(root, None, "broken_state")
        res["blocked_on"].append(str(exc))
        res["action"] = "project-state.json 壞了；不要手改修復，回報使用者並從備份還原。"
        return res

    integrity = ps.state_integrity(root)
    stage, first_failure = ps.first_unapproved(root)
    if stage is None:
        res = _result(root, 7, "done")
        res["done"] = True
        res["action"] = "八個階段都已有效核准；交付 final/ 下的成片與 delivery manifest。"
        return res

    entry = state["stages"][ps.stage_key(stage)]
    status = str(entry.get("status") or "draft")
    res = _result(root, stage, status)
    res["read"] = list(STAGE_REFERENCES.get(stage, []))

    if integrity == "tampered":
        res["blocked_on"].append("project-state.json 在最後一次正式寫入後被手改過")
        res["action"] = ("停下：不准手改 project-state。回報使用者，從備份還原，"
                         "或重建本階段審核頁並請使用者重新核准。")
        res["next_command"] = f"{REVIEW} --project-dir . --stage {stage}"
        return res
    if integrity == "missing":
        res["notes"].append("project-state.json 沒有寫入戳記（舊專案或曾手改）；下次正式核准後會補上")

    try:
        decisions_mod.load(root)
    except decisions_mod.DecisionError as exc:
        res["blocked_on"].append(str(exc))
        res["action"] = "decisions.json 格式錯誤；用 h3d decide 重寫有問題的定案，不要手改。"
        res["next_command"] = f"{H3D} decide --list --root ."
        return res
    if not decisions_mod.decisions_path(root).is_file():
        res["notes"].append("沒有 decisions.json；第一次 h3d decide 會自動建立")

    active = _active_jobs(root)
    if active:
        res["blocked_on"].append(f"有 {len(active)} 個影片工作還在跑：{active[0]}")
        res["action"] = "不要再開第二個 runner，也不要送新件；只收件。"
        res["next_command"] = f"{H3D} collect --segments <該批 segments 檔> --output-dir videos --root-dir ."
        return res

    missing = decisions_mod.missing_for_stage(root, stage)
    if missing:
        return _decision_step(res, root, missing)

    if stage >= 5:
        try:
            import deps
            report = deps.status(root)
            stale = report.get("stale") or []
            if stale:
                res["notes"].append(f"依賴帳本：{len(stale)} 段 prompt／影片過期（h3d deps --root . --status）")
        except Exception:
            pass

    if status == "approved":
        res["status"] = "approval_invalid"
        res["blocked_on"].append(f"核准已失效：{first_failure}")
        res["action"] = "內容在核准後變了：重建審核頁，請使用者重新核准（不要手改狀態）。"
        res["next_command"] = f"{REVIEW} --project-dir . --stage {stage}"
        return res

    auto = _auto_step(res, root, stage)
    if auto is not None and status in ("awaiting_user_approval", "draft", "in_progress", "locked"):
        return auto

    if status == "awaiting_user_approval":
        if entry.get("review_snapshot") != ps.stage_snapshot(root, stage):
            res["blocked_on"].append("審核頁產出後產物又改了，舊審核頁作廢")
            res["action"] = "重建審核頁，再交給使用者。"
            res["next_command"] = f"{REVIEW} --project-dir . --stage {stage}"
            return res
        technical = ps.stage6_issues(root)[1] if stage == 6 else []
        res["blocked_on"].append("等使用者在審核頁明確回覆通過")
        res["notes"].append(f"要使用者決定的事可用收件匣呈現：{H3D} inbox --root .（review/inbox.html）")
        res["action"] = ("把審核頁交給使用者並停下。只有使用者明確回覆「通過」後才執行下面指令，"
                         "--user-note 填使用者原話；不得代替使用者核准。")
        if technical:
            res["action"] += f" 技術 QA 有 {len(technical)} 項未過，核准必須帶使用者的覆寫理由。"
        res["next_command"] = _approve_command(stage, technical)
        return res

    # draft／in_progress／locked：做本階段的工作，產物齊了就建審核頁。
    if stage == 6:
        step = _stage6_work(res, root)
        if step is not None:
            return step
    else:
        errors = ps.stage_validation_errors(root, stage, strict=True)
        if errors:
            res["blocked_on"].append(errors[0])
            producers = {
                0: (f"{H3D} decide --list --root .",
                    "和使用者定調（h3d decide style／aspect_ratio／dialogue_policy），把 project.md 的模板欄位全部填實。"),
                1: (f"{CHECK} --root . --stage 1",
                    "依原著寫完 adapt/character-bible.md（validate_character_bible.py --bible-md --bible-json 要 PASS）、"
                    "bible.json、source.json 的 story_units 與 adapt/series-outline.md。"),
                2: (f"{CHECK} --root . --stage 2",
                    "把 assets.md 的模板卡片填實，並生成每張登記的設定圖。"),
                3: (f"{CHECK} --root . --stage 3",
                    "寫完 script-ep*.md，跑 sync_script.py 產 handoff，修到 validate_structure／check_continuity／compare_adaptation 沒有 FAIL。"),
                4: stage4_producer(root, errors) if stage == 4 else None,
                5: stage5_producer(root, errors) if stage == 5 else None,
                7: (f"{H3D} voice align --root .",
                    "先跑階段 7 固定流程（ASR 對位、畫外句壓原聲、響度），再 h3d concat plan／build 建全集剪輯專案，"
                    "或 h3d assemble 組裝成片並產出 delivery manifest。"),
            }
            command, action = producers.get(stage) or (f"{H3D} status --root .", "先修正上面的錯誤。")
            res["action"] = action
            res["next_command"] = command
            return res
    res["action"] = "產物已齊：產出本階段審核頁交給使用者，然後停下等回覆。"
    res["next_command"] = f"{REVIEW} --project-dir . --stage {stage}"
    return res


def render(res: Dict[str, Any]) -> str:
    lines = [f"專案：{res['root']}"]
    if res["stage"] is None:
        lines.append(f"目前階段：{res['stage_title']}（{res['status']}）")
    else:
        lines.append(f"目前階段：stage-{res['stage']} {res['stage_title']}（{res['status']}）")
    if res["done"]:
        lines.append(f"✅ {res['action']}")
        return "\n".join(lines)
    if res["blocked_on"]:
        lines.append("卡在：")
        lines.extend(f"  - {item}" for item in res["blocked_on"])
    if res["action"]:
        lines.append(f"要做的事：{res['action']}")
    if res["next_command"]:
        lines.append("下一步（唯一一條，在專案根目錄執行）：")
        lines.append(f"  {res['next_command']}")
    else:
        lines.append("下一步：停下，回報使用者。")
    if res["read"]:
        lines.append("先讀：" + "、".join(res["read"]))
    for note in res["notes"]:
        lines.append(f"附註：{note}")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(prog="h3d next", description="印出目前階段、卡在哪、下一步唯一一條指令與該讀的 reference")
    parser.add_argument("--root", type=Path, default=Path("."), help="專案根目錄")
    parser.add_argument("--json", action="store_true", help="以 JSON 輸出")
    args = parser.parse_args(argv)
    res = plan(args.root)
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        print(render(res))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
