#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""`h3d verdict import`：把舊格式 conclusions-*.json 轉成 review/verdicts.json。

舊格式（《我修的是遺忘課》stage6/conclusions-*.json）是「segment_id → 一句中文結論」：

    {"EP01-S01-a": "✅【08:47 新標準：暫時通過】原判：……",
     "EP01-S04-d": "✅（附註）【11:15 重跑收件】……",
     "EP02-S01-a": "❌【……】……",
     "_驗收標準_20261022": "老大 2026-10-22 08:47 新驗收標準：……",
     "_老大裁示_20261022": {"EP03-S01-a": "09:26 老大：先當通過（岑缺頭巾）"}}

轉換規則（保守，寧可少判也不要多判）：
  * 開頭 ✅ → pass；✅ 後面緊接「附註」→ warn；⚠️ → warn；❌ → fail；空字串略過。
  * `_` 開頭的字串鍵是說明（例如驗收標準原話），不轉成結論，只在報告裡提示可用 `h3d decide` 定案。
  * `_老大裁示_*`／`_使用者裁示_*` 這類物件：裡面每一段都是使用者親自裁示 → decided_by=user。
  * 只看「原判：」之前的文字（之後是舊結論的歷史）。
  * 問題代碼用關鍵字推：pass 只推「可接受」類代碼（paper_text／aged_face／low_chroma／color_jump），
    避免「由平塗卡通改回半寫實」這種描述把通過段誤推成 style_shift；warn／fail 才推全部代碼。
    `--no-issues` 可完全不推。
  * 證據：videos/qa/tiles/<id>.jpg → videos/<id>.mp4 → 原 conclusions 檔本身（依序取第一個存在的）。
  * 影片存在就綁 hash（影片重生後結論自動過期）。
  * 多個檔案依命令列順序套用，後面的覆蓋前面的；已存在且 decided_by=user 的結論不覆蓋（除非 --overwrite）。
  * 有 segments-ep*.json 時，不在其中的 id（例如 EP01-S04-b-take3 這類重抽）預設略過，`--keep-unknown` 保留。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import decisions as decisions_mod
import verdicts as verdicts_mod

ACCEPT_LIKE = ("paper_text", "aged_face", "low_chroma", "color_jump")

# 關鍵字 → 問題代碼（順序無關；同一段可命中多個）
ISSUE_KEYWORDS: List[Tuple[str, str]] = [
    (r"燒.{0,2}字幕|字幕燒|簡體字幕|出現字幕|燒字", "burned_subtitle"),
    (r"多出.{0,4}人|多一張.{0,2}臉|多.{0,2}女子|多.{0,2}男子|路人露臉|分身|多人", "extra_person"),
    (r"混臉|身份錯亂|身分錯亂|同框露臉|偏像|像陳硯|臉.{0,2}不對", "face_mix"),
    (r"服裝錯|頭巾|衣服不對|服裝不對|穿錯", "wardrobe_wrong"),
    (r"畫風突變|平塗|卡通|畫風錯|畫風不同", "style_shift"),
    (r"構圖嚴重|構圖錯|變遠景", "composition_broken"),
    (r"九宮格框|框線殘留|格線殘留", "grid_leak"),
    (r"出字|小字|假字|寫出成行字|紙面|簿頁.{0,4}字", "paper_text"),
    (r"顯老|偏老|稍老|略老|細紋", "aged_face"),
    (r"低彩度", "low_chroma"),
    (r"色調跳|色調不一", "color_jump"),
]

USER_RULING_KEY = re.compile(r"^_(老大|使用者|user)[^_]*裁示", re.IGNORECASE)


class ImportErrorReport(ValueError):
    pass


def parse_line(text: str) -> Optional[str]:
    """回傳 pass／warn／fail；無法判斷回傳 None。"""
    t = text.strip()
    if not t:
        return None
    if t.startswith("✅"):
        rest = t[1:].lstrip()
        return "warn" if rest.startswith(("（附註）", "(附註)", "附註")) else "pass"
    if t.startswith(("⚠️", "⚠")):
        return "warn"
    if t.startswith(("❌", "✖")):
        return "fail"
    return None


def parse_ruling(text: str) -> str:
    """使用者裁示的一句話 → 結論。"""
    if re.search(r"重跑|不採用|不行", text):
        return "fail"
    if re.search(r"通過|可以|採用|OK", text, re.IGNORECASE):
        return "pass"
    return "warn"


def current_part(text: str) -> str:
    """只取「原判：」之前（之後是被取代的舊結論）。"""
    return re.split(r"原判[:：]", text, maxsplit=1)[0].strip()


def _strip_marks(text: str) -> str:
    """去掉開頭的 ✅⚠️❌ 符號（結論已存在 verdict 欄位），保留【時間標籤】與內容。"""
    return re.sub(r"^[\s✅⚠️❌✖\ufe0f]+", "", text).strip()


def infer_issues(text: str, verdict: str) -> List[str]:
    found: List[str] = []
    for pattern, code in ISSUE_KEYWORDS:
        if re.search(pattern, text) and code not in found:
            found.append(code)
    if verdict == "pass":
        found = [c for c in found if c in ACCEPT_LIKE]
    return found


def _known_segment_ids(root: Path) -> List[str]:
    ids: List[str] = []
    for path in sorted(root.glob("segments-ep*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            continue
        items = raw if isinstance(raw, list) else raw.get("segments", [raw])
        ids.extend(str(i["segment_id"]) for i in items if isinstance(i, dict) and i.get("segment_id"))
    return ids


def _rel_or_abs(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _evidence_for(root: Path, sid: str, source_file: Path) -> str:
    for rel in (f"videos/qa/tiles/{sid}.jpg", f"videos/qa/tiles/{sid}.png", f"videos/{sid}.mp4"):
        if (root / rel).is_file():
            return rel
    return _rel_or_abs(root, source_file)


def convert(root: Path, files: List[Path], *, keep_unknown: bool = False, overwrite: bool = False,
            no_issues: bool = False) -> Dict[str, Any]:
    """回傳 {"data": 新 verdicts, "imported": [...], "skipped": [...], "policy_hints": [...]}（不寫檔）。"""
    root = Path(root)
    data = verdicts_mod.load(root)
    known = set(_known_segment_ids(root))
    imported: List[Dict[str, Any]] = []
    skipped: List[Dict[str, str]] = []
    hints: List[str] = []
    now = datetime.now().astimezone().isoformat(timespec="seconds")

    def put(sid: str, verdict: str, reason: str, by: str, source: Path, key: str, issues: List[str]) -> None:
        if known and sid not in known and not keep_unknown:
            skipped.append({"segment_id": sid, "why": "不在 segments-ep*.json（重抽／備用片，用 --keep-unknown 保留）"})
            return
        existing = data["segments"].get(sid)
        if existing and existing.get("decided_by") == "user" and by != "user" and not overwrite:
            skipped.append({"segment_id": sid, "why": "已有使用者結論，不覆蓋（--overwrite 可強制）"})
            return
        entry: Dict[str, Any] = {
            "verdict": verdict,
            "reason": (reason[:240] + "…") if len(reason) > 240 else reason,
            "evidence": _evidence_for(root, sid, source),
            "decided_by": by,
            "issues": [] if no_issues else issues,
            "decided_at": now,
            "imported_from": {"file": _rel_or_abs(root, source), "key": key},
        }
        video = root / "videos" / f"{sid}.mp4"
        if video.is_file():
            entry["video_sha256"] = verdicts_mod._sha256(video)
        data["segments"][sid] = entry
        imported.append({"segment_id": sid, "verdict": verdict, "decided_by": by, "issues": entry["issues"]})

    for source in files:
        source = Path(source)
        try:
            raw = json.loads(source.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ImportErrorReport(f"{source} 無法解析：{exc}") from exc
        if not isinstance(raw, dict):
            raise ImportErrorReport(f"{source} 不是 segment_id → 結論 的物件")
        rulings: List[Tuple[str, Dict[str, Any]]] = []
        for key, value in raw.items():
            if key.startswith("_"):
                if isinstance(value, dict) and USER_RULING_KEY.match(key):
                    rulings.append((key, value))
                elif isinstance(value, str) and re.search(r"驗收|標準", key):
                    hints.append(f"{source.name} 的 {key} 看起來是驗收政策原話；請用 "
                                 f"h3d decide acceptance_policy recommended --quote \"{value[:60]}…\" 定案")
                continue
            if not isinstance(value, str):
                skipped.append({"segment_id": key, "why": "值不是字串"})
                continue
            verdict = parse_line(value)
            if verdict is None:
                skipped.append({"segment_id": key, "why": "空白或開頭不是 ✅／⚠️／❌"})
                continue
            text = _strip_marks(current_part(value))
            put(key, verdict, text or value.strip(), "agent", source, key, infer_issues(text, verdict))
        # 使用者裁示最後套用：它比同檔的 agent 結論大
        for key, block in rulings:
            for sid, text in block.items():
                if not isinstance(text, str) or not text.strip():
                    continue
                verdict = parse_ruling(text)
                put(sid, verdict, text.strip(), "user", source, f"{key}.{sid}", infer_issues(text, verdict))
    errors = verdicts_mod.validate(data)
    if errors:
        raise ImportErrorReport("轉換結果不合格：" + "；".join(errors[:5]))
    return {"data": data, "imported": imported, "skipped": skipped, "policy_hints": hints}


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="h3d verdict import",
        description="把舊格式 conclusions-*.json（segment_id → 一句中文結論）轉成 review/verdicts.json",
        epilog="例：h3d verdict import ../stage6/conclusions-ep01.json ../stage6/conclusions-multi.json --root .",
    )
    parser.add_argument("files", nargs="+", type=Path, help="舊結論檔，依序套用（後者覆蓋前者）")
    parser.add_argument("--root", type=Path, default=Path("."), help="專案根目錄")
    parser.add_argument("--keep-unknown", action="store_true", help="保留不在 segments-ep*.json 的 id")
    parser.add_argument("--overwrite", action="store_true", help="連使用者結論也覆蓋")
    parser.add_argument("--no-issues", action="store_true", help="不從文字推問題代碼")
    parser.add_argument("--dry-run", action="store_true", help="只印轉換結果，不寫檔")
    parser.add_argument("--json", action="store_true", help="以 JSON 印報告")
    args = parser.parse_args(argv)
    root = args.root.expanduser().resolve()
    try:
        report = convert(root, args.files, keep_unknown=args.keep_unknown, overwrite=args.overwrite,
                         no_issues=args.no_issues)
        if not args.dry_run:
            verdicts_mod.save(root, report["data"])
    except (ImportErrorReport, verdicts_mod.VerdictError, decisions_mod.DecisionError) as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps({k: v for k, v in report.items() if k != "data"}, ensure_ascii=False, indent=2))
        return 0
    counts: Dict[str, int] = {}
    for item in report["imported"]:
        counts[item["verdict"]] = counts.get(item["verdict"], 0) + 1
    users = sum(1 for i in report["imported"] if i["decided_by"] == "user")
    head = "（乾跑，未寫檔）" if args.dry_run else f"→ {verdicts_mod.VERDICTS_REL.as_posix()}"
    print(f"✅ 匯入 {len(report['imported'])} 筆 {head}：pass {counts.get('pass', 0)}、warn {counts.get('warn', 0)}、"
          f"fail {counts.get('fail', 0)}（使用者裁示 {users}）")
    if report["skipped"]:
        print(f"略過 {len(report['skipped'])} 筆：")
        for item in report["skipped"][:20]:
            print(f"  - {item['segment_id']}：{item['why']}")
    for hint in report["policy_hints"]:
        print(f"提示：{hint}")
    print("下一步：h3d verdict --summary --root .（看依驗收政策的分類）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
