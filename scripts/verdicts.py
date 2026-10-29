#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""review/verdicts.json：階段 6 逐段目視結論，以及依驗收政策的分類。

技術 QA（verify_video_shot）只量時長、比例、彩度、九宮格框線；
「有沒有多出人、有沒有燒字幕、畫風有沒有突變」只能靠看。
過去這些結論散在專案自寫的 conclusions-*.json，格式各異、審核頁讀不到。
這裡定一個格式：

    {"schema_version": 1,
     "segments": {
       "EP01-S01-a": {"verdict": "pass|warn|fail", "reason": "一句話",
                      "evidence": "videos/qa/tiles/EP01-S01-a.jpg"（或陣列）,
                      "decided_by": "agent|user|policy",
                      "issues": ["paper_text"], "video_sha256": "...", "decided_at": "..."}}}

寫入走 `h3d verdict <segment_id> <pass|warn|fail> --reason ... --evidence ...`，不要手改。
分類規則（classify）：
  * 技術硬錯誤（時長漂移、比例錯、QA 例外）一律 fail，不能用政策或覆寫放行。
  * decided_by=user 的結論最大，政策不改它。
  * 其餘結論套 decisions.json 的 acceptance_policy：issues 碰到 rerun_on → fail；
    標 fail 但 issues 全在 accept 內 → 降為 warn。
  * 沒有結論的段落是 unreviewed（技術 QA 綠燈也一樣，綠燈不等於看過）。
格式見 references/schemas/verdicts.schema.json。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import decisions as decisions_mod

VERDICTS_REL = Path("review") / "verdicts.json"
SCHEMA_VERSION = 1
VERDICTS = ("pass", "warn", "fail")
DECIDED_BY = ("agent", "user", "policy")

# 技術 QA 的 issue 前綴 → 驗收政策代碼。HARD 類不受政策與覆寫影響。
QA_HARD_PREFIXES = ("DURATION_MISMATCH", "ASPECT_RATIO_MISMATCH", "QA_ERROR")
QA_SOFT_MAP = {
    "STYLE_BLEED_GRAYSCALE": "low_chroma",
    "GRID_PANEL_BORDER_DETECTED": "grid_leak",
    "NO_AUDIO_STREAM_FOR_DIALOGUE": "no_audio",
}


class VerdictError(ValueError):
    pass


def verdicts_path(root: Path) -> Path:
    return Path(root) / VERDICTS_REL


def empty() -> Dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "segments": {}}


def validate(data: Any) -> List[str]:
    if not isinstance(data, dict):
        return ["根節點必須是物件"]
    errors: List[str] = []
    if data.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version 必須是 {SCHEMA_VERSION}")
    segments = data.get("segments")
    if not isinstance(segments, dict):
        return errors + ["segments 必須是物件（segment_id → 結論）"]
    for sid, item in segments.items():
        if not isinstance(item, dict):
            errors.append(f"{sid}: 結論必須是物件")
            continue
        if item.get("verdict") not in VERDICTS:
            errors.append(f"{sid}: verdict 必須是 pass／warn／fail")
        reason = item.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            errors.append(f"{sid}: reason 必填（一句話）")
        evidence = item.get("evidence")
        ok_evidence = (isinstance(evidence, str) and evidence.strip()) or (
            isinstance(evidence, list) and evidence and all(isinstance(e, str) and e.strip() for e in evidence))
        if not ok_evidence:
            errors.append(f"{sid}: evidence 必須是證據圖路徑（字串或字串陣列）")
        if item.get("decided_by") not in DECIDED_BY:
            errors.append(f"{sid}: decided_by 必須是 agent／user／policy")
        issues = item.get("issues", [])
        if not isinstance(issues, list) or any(i not in decisions_mod.ISSUE_CODES for i in issues):
            errors.append(f"{sid}: issues 只能用驗收政策代碼（{', '.join(decisions_mod.ISSUE_CODES)}）")
        errors.extend(_card_field_errors(sid, item))
    return errors


def _card_field_errors(sid: str, item: Dict[str, Any]) -> List[str]:
    """選用的決策卡欄位（impact／recommendation／options）：給收件匣用，讓卡片寫得比通用模板準。"""
    errors: List[str] = []
    for key in ("impact", "recommendation"):
        if key in item and (not isinstance(item[key], str) or not item[key].strip()):
            errors.append(f"{sid}: {key} 若有填必須是非空字串")
    if "options" in item:
        options = item["options"]
        if not isinstance(options, list) or not 2 <= len(options) <= 3:
            errors.append(f"{sid}: options 必須是 2–3 個選項")
        else:
            for opt in options:
                if not isinstance(opt, dict) or not all(
                        isinstance(opt.get(k), str) and opt[k].strip() for k in ("label", "reply")):
                    errors.append(f"{sid}: options 每項都要有 label 與 reply 字串")
                    break
    imported = item.get("imported_from")
    if imported is not None and not (isinstance(imported, dict) and isinstance(imported.get("file"), str)):
        errors.append(f"{sid}: imported_from 必須是 {{file, key}} 物件")
    return errors


def parse_option(raw: str) -> Dict[str, str]:
    """`--option "後製裁掉=EP03-S02-d：後製裁掉最後 1 秒"` → {label, reply}；沒有 = 時兩者相同。"""
    label, sep, reply = raw.partition("=")
    label = label.strip()
    reply = reply.strip() if sep else label
    if not label or not reply:
        raise VerdictError(f"--option 格式錯誤：{raw}（應為 \"選項=回覆文字\"）")
    return {"label": label, "reply": reply}


def load(root: Path) -> Dict[str, Any]:
    path = verdicts_path(root)
    if not path.is_file():
        return empty()
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VerdictError(f"verdicts.json 無法解析：{exc}") from exc
    errors = validate(data)
    if errors:
        raise VerdictError("verdicts.json 格式錯誤：" + "；".join(errors[:5]))
    return data


def save(root: Path, data: Dict[str, Any]) -> Path:
    errors = validate(data)
    if errors:
        raise VerdictError("拒絕寫入不合格的 verdicts.json：" + "；".join(errors[:5]))
    path = verdicts_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    tmp.replace(path)
    return path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve(root: Path, raw: str) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else Path(root) / path


def set_verdict(root: Path, segment_id: str, verdict: str, reason: str, evidence: List[str], *,
                decided_by: str = "agent", issues: Optional[List[str]] = None,
                video: Optional[str] = None, impact: Optional[str] = None,
                recommendation: Optional[str] = None,
                options: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
    if verdict not in VERDICTS:
        raise VerdictError("verdict 必須是 pass／warn／fail")
    if not evidence:
        raise VerdictError("必須用 --evidence 附至少一張證據圖（抽幀九宮格、並排對照圖等）")
    root = Path(root)
    for raw in evidence:
        if not _resolve(root, raw).is_file():
            raise VerdictError(f"證據圖不存在：{raw}")
    entry: Dict[str, Any] = {
        "verdict": verdict,
        "reason": reason.strip(),
        "evidence": evidence[0] if len(evidence) == 1 else list(evidence),
        "decided_by": decided_by,
        "issues": list(issues or []),
        "decided_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    if impact:
        entry["impact"] = impact.strip()
    if recommendation:
        entry["recommendation"] = recommendation.strip()
    if options:
        entry["options"] = list(options)
    video_path = _resolve(root, video) if video else root / "videos" / f"{segment_id}.mp4"
    if video_path.is_file():
        # 結論綁影片 hash：影片重生後舊結論自動過期，不會被當成新片的驗收。
        entry["video_sha256"] = _sha256(video_path)
    data = load(root)
    data["segments"][segment_id] = entry
    save(root, data)
    return entry


def qa_codes(item: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    """把技術 QA 的 issues 拆成 (硬錯誤原文, 政策代碼)。"""
    hard: List[str] = []
    soft: List[str] = []
    for issue in item.get("issues", []) or []:
        text = str(issue)
        if any(text.startswith(prefix) for prefix in QA_HARD_PREFIXES):
            hard.append(text)
            continue
        code = next((c for key, c in QA_SOFT_MAP.items() if key in text), "other")
        if code not in soft:
            soft.append(code)
    if item.get("passed") is not True and not hard and not soft:
        soft.append("other")
    return hard, soft


def load_qa_report(root: Path) -> Optional[Dict[str, Any]]:
    path = Path(root) / "videos" / "qa-report.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None


def classify(root: Path, qa_report: Optional[Dict[str, Any]] = None,
             verdict_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """依 verdicts＋技術 QA＋acceptance_policy 算出每段的有效結論。"""
    root = Path(root)
    qa_report = qa_report if qa_report is not None else load_qa_report(root)
    verdict_data = verdict_data if verdict_data is not None else load(root)
    policy, policy_is_decided = decisions_mod.acceptance_policy(root)
    rerun_on = set(policy.get("rerun_on", []))
    accept = set(policy.get("accept", []))

    qa_items: Dict[str, Dict[str, Any]] = {}
    expected: List[str] = []
    if qa_report:
        expected = [str(s) for s in qa_report.get("expected_segments", []) or []]
        for item in qa_report.get("results", []) or []:
            if item.get("segment_id"):
                qa_items[str(item["segment_id"])] = item
    recorded = verdict_data.get("segments", {})
    order = list(dict.fromkeys(expected + sorted(qa_items) + sorted(recorded)))

    rows: Dict[str, Dict[str, Any]] = {}
    for sid in order:
        qa_item = qa_items.get(sid, {})
        hard, soft = qa_codes(qa_item) if qa_item else ([], [])
        verdict = recorded.get(sid)
        row: Dict[str, Any] = {"segment_id": sid, "qa_passed": qa_item.get("passed") is True if qa_item else None,
                               "qa_codes": soft, "qa_hard": hard}
        if hard:
            row.update(effective="fail", source="qa", reason="技術硬錯誤：" + hard[0][:80])
            rows[sid] = row
            continue
        stale = False
        if verdict and verdict.get("video_sha256"):
            current = qa_item.get("video_sha256") or qa_item.get("file_hash_sha256")
            if not current:
                vp = root / "videos" / f"{sid}.mp4"
                current = _sha256(vp) if vp.is_file() else None
            want = str(verdict["video_sha256"]).lower().removeprefix("sha256:")
            stale = bool(current) and str(current).lower().removeprefix("sha256:") != want
            if stale:
                # 技術 QA 報告可能比影片舊；以磁碟上實際檔案的 sha 為準，只比 sha、不看 mtime（#147）
                vp = root / "videos" / f"{sid}.mp4"
                if vp.is_file():
                    stale = _sha256(vp).lower().removeprefix("sha256:") != want
        if not verdict or stale:
            if set(soft) & rerun_on:
                hit = sorted(set(soft) & rerun_on)
                row.update(effective="fail", source="policy",
                           reason="技術 QA 偵測到驗收政策要重跑的問題：" + "、".join(hit))
            else:
                row.update(effective="unreviewed", source="none",
                           reason="影片已重生，舊結論過期" if stale else "尚未目視驗收")
            row["stale"] = stale
            rows[sid] = row
            continue
        issues = list(dict.fromkeys(list(verdict.get("issues", [])) + soft))
        row["issues"] = issues
        row["evidence"] = verdict.get("evidence")
        if verdict.get("decided_by") == "user":
            row.update(effective=verdict["verdict"], source="user", reason=verdict["reason"])
        elif set(issues) & rerun_on and verdict["verdict"] != "fail":
            hit = sorted(set(issues) & rerun_on)
            row.update(effective="fail", source="policy",
                       reason=f"驗收政策：{'、'.join(hit)} 需重跑（原判 {verdict['verdict']}：{verdict['reason']}）")
        elif verdict["verdict"] == "fail" and issues and set(issues) <= accept:
            row.update(effective="warn", source="policy",
                       reason=f"驗收政策：{'、'.join(issues)} 可接受（原判 fail：{verdict['reason']}）")
        else:
            row.update(effective=verdict["verdict"], source=verdict.get("decided_by", "agent"),
                       reason=verdict["reason"])
        rows[sid] = row

    counts = {key: 0 for key in ("pass", "warn", "fail", "unreviewed")}
    for row in rows.values():
        counts[row["effective"]] += 1
    return {"policy": policy, "policy_is_decided": policy_is_decided, "counts": counts, "segments": rows}


def accept_all(root: Path, quote: str) -> List[str]:
    """使用者整批接受現有段：把「已有結論、非技術硬錯誤」的 warn／被政策判重跑的段，逐段轉成 user warn。"""
    if not quote or not quote.strip():
        raise VerdictError("--quote 必填（貼使用者原話）")
    root = Path(root)
    report = classify(root)
    data = load(root)
    done: List[str] = []
    for sid, row in report["segments"].items():
        old = data["segments"].get(sid)
        if not old or row.get("stale") or row["effective"] not in ("warn", "fail"):
            continue
        if row.get("source") in ("qa", "user"):
            continue
        entry = dict(old)
        entry.update(verdict="warn" if old.get("verdict") != "pass" else "pass",
                     reason=f"使用者整批接受：{quote.strip()}（原：{old.get('reason', '')}）",
                     decided_by="user",
                     decided_at=datetime.now().astimezone().isoformat(timespec="seconds"))
        data["segments"][sid] = entry
        done.append(sid)
    if done:
        save(root, data)
    return done


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "accept-all":
        ap = argparse.ArgumentParser(prog="h3d verdict accept-all",
                                     description="使用者整批接受現有段：把 warn／政策判重跑的段轉成 user warn")
        ap.add_argument("--quote", required=True, help="使用者原話")
        ap.add_argument("--root", type=Path, default=Path("."))
        a = ap.parse_args(argv[1:])
        try:
            done = accept_all(a.root.expanduser().resolve(), a.quote)
        except (VerdictError, decisions_mod.DecisionError) as exc:
            print(f"❌ {exc}", file=sys.stderr)
            return 2
        print(f"✅ 已轉 {len(done)} 段為使用者接受：{'、'.join(done) or '（無）'}")
        return 0
    if argv and argv[0] == "import":
        import verdict_import
        return verdict_import.main(argv[1:])
    parser = argparse.ArgumentParser(
        prog="h3d verdict",
        description="寫入階段 6 逐段目視結論（review/verdicts.json），或列出依驗收政策的分類",
        epilog="例：h3d verdict EP01-S01-a pass --reason \"人物一致、無多人\" "
               "--evidence videos/qa/tiles/EP01-S01-a.jpg --root <專案>；h3d verdict --summary --root <專案>；"
               "舊格式轉換：h3d verdict import conclusions-*.json --root <專案>",
    )
    parser.add_argument("segment_id", nargs="?")
    parser.add_argument("verdict", nargs="?", choices=VERDICTS)
    parser.add_argument("--reason", help="一句話原因（必填）")
    parser.add_argument("--evidence", action="append", default=[], help="證據圖路徑，可重複")
    parser.add_argument("--issues", default="", help=f"問題代碼，逗號分隔（{', '.join(decisions_mod.ISSUE_CODES)}）")
    parser.add_argument("--by", default="agent", choices=DECIDED_BY, help="誰判的：agent／user／policy")
    parser.add_argument("--video", help="影片路徑（預設 videos/<segment_id>.mp4），用來綁 hash")
    parser.add_argument("--impact", help="（選填，給收件匣）會影響什麼，一句話")
    parser.add_argument("--recommend", help="（選填，給收件匣）你的建議，一句話")
    parser.add_argument("--option", action="append", default=[],
                        help="（選填，給收件匣）選項，格式 \"選項=回覆文字\"，可重複 2–3 次")
    parser.add_argument("--root", type=Path, default=Path("."), help="專案根目錄")
    parser.add_argument("--summary", action="store_true", help="列出依驗收政策的分類")
    parser.add_argument("--json", action="store_true", help="--summary 以 JSON 輸出")
    args = parser.parse_args(argv)
    root = args.root.expanduser().resolve()
    try:
        if args.summary:
            report = classify(root)
            if args.json:
                print(json.dumps(report, ensure_ascii=False, indent=2))
                return 0
            c = report["counts"]
            tag = "使用者定案" if report["policy_is_decided"] else "建議值（尚未定案，請 h3d decide acceptance_policy）"
            print(f"驗收政策：{tag}")
            print(f"✅ {c['pass']}　⚠️ {c['warn']}　❌ {c['fail']}　未驗收 {c['unreviewed']}")
            for row in report["segments"].values():
                if row["effective"] in ("fail", "warn", "unreviewed"):
                    mark = {"fail": "❌", "warn": "⚠️", "unreviewed": "…"}[row["effective"]]
                    print(f"  {mark} {row['segment_id']}：{row['reason']}")
            return 0
        if not args.segment_id or not args.verdict:
            parser.error("需要 <segment_id> <pass|warn|fail>，或用 --summary")
        if not args.reason or not args.reason.strip():
            parser.error("--reason 必填")
        issues = [i.strip() for i in args.issues.replace("，", ",").split(",") if i.strip()]
        unknown = [i for i in issues if i not in decisions_mod.ISSUE_CODES]
        if unknown:
            raise VerdictError(f"未知問題代碼：{', '.join(unknown)}")
        options = [parse_option(o) for o in args.option]
        if options and not 2 <= len(options) <= 3:
            raise VerdictError("--option 要 2–3 個")
        entry = set_verdict(root, args.segment_id, args.verdict, args.reason, args.evidence,
                            decided_by=args.by, issues=issues, video=args.video,
                            impact=args.impact, recommendation=args.recommend, options=options or None)
    except (VerdictError, decisions_mod.DecisionError) as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 2
    print(f"✅ {args.segment_id} → {entry['verdict']}（{entry['decided_by']}）：{entry['reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
