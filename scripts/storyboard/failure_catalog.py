#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""失敗目錄（failure catalog）：把「跑過的片」變成「下一次的規則」。

為什麼要有它：

《噩盡島》第一章的失敗（無邊界紅光被讀成全域色調、裂紋變貼紙、`<d>` 吃時間、
多人混臉、否定句反效果）目前散在 `技能實作問題與待改.md`、repair briefs 與
幾個 markdown 表格裡。下次遇到同一個症狀，靠的是「有人記得」。

這支程式把它們變成資料：每條失敗有 symptom / root_cause / minimal_fix /
evidence / confidence，還有一個**確定性 detector**（純 regex，不呼叫模型）。
`lint_text()` 會拿它去掃提示詞，`enforce=error` 的條目才阻擋，其餘只警告。

三級 confidence 與 `evidence.py` 同一套：
  measured  本機實測（有段號或影格）
  sourced   官方文件或競品實作
  inferred  推論
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_PATH = Path(__file__).resolve().parent / "failure-catalog.json"
PROJECT_OVERRIDE = "failure-catalog.json"
ACKS_RELATIVE = Path("review") / "catalog-acks.json"
SEGMENTS_LIKE = re.compile(r"^segments-(ep\d+|all)\.json$")
ALLOWED_TYPES = ("any", "all", "any_without")
ALLOWED_CONFIDENCE = ("measured", "sourced", "inferred")
ALLOWED_ENFORCE = ("error", "warning")


class CatalogError(ValueError):
    """目錄本身有問題（缺檔、格式壞、detector 型別不認得）。"""


def _load_file(path: Path) -> Dict[str, Any]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CatalogError(f"{path} 無法解析：{exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("entries"), list):
        raise CatalogError(f"{path} 必須是 {{entries: [...]}} 結構")
    return data


def _validate(entry: Dict[str, Any], where: str) -> None:
    for field in ("id", "title", "detector"):
        if not entry.get(field):
            raise CatalogError(f"{where} 缺少必要欄位 {field}")
    detector = entry["detector"]
    if not isinstance(detector, dict):
        raise CatalogError(f"{where}.detector 必須是物件")
    if detector.get("type") not in ALLOWED_TYPES:
        raise CatalogError(f"{where}.detector.type 必須是 {ALLOWED_TYPES}")
    patterns = detector.get("patterns")
    if not isinstance(patterns, list) or not patterns:
        raise CatalogError(f"{where}.detector.patterns 必須是非空陣列")
    for index, pattern in enumerate(patterns):
        if not isinstance(pattern, str) or not pattern.strip():
            raise CatalogError(f"{where}.detector.patterns[{index}] 必須是非空字串")
        try:
            re.compile(pattern)
        except re.error as exc:
            raise CatalogError(f"{where}.detector.patterns[{index}] regex 無效：{exc}") from exc
    excludes = detector.get("exclude") or []
    if not isinstance(excludes, list):
        raise CatalogError(f"{where}.detector.exclude 必須是字串陣列（不可寫成單一字串）")
    for index, pattern in enumerate(excludes):
        if not isinstance(pattern, str) or not pattern.strip():
            raise CatalogError(f"{where}.detector.exclude[{index}] 必須是非空字串")
        try:
            re.compile(pattern)
        except re.error as exc:
            raise CatalogError(f"{where}.detector.exclude[{index}] regex 無效：{exc}") from exc
    confidence = entry.get("confidence", "inferred")
    if confidence not in ALLOWED_CONFIDENCE:
        raise CatalogError(f"{where}.confidence 必須是 {ALLOWED_CONFIDENCE}")
    enforce = entry.get("enforce", "warning")
    if enforce not in ALLOWED_ENFORCE:
        raise CatalogError(f"{where}.enforce 必須是 {ALLOWED_ENFORCE}")


def _dedupe(entries: List[Dict[str, Any]], where: str) -> Dict[str, Dict[str, Any]]:
    seen: Dict[str, Dict[str, Any]] = {}
    for entry in entries:
        entry_id = entry.get("id")
        if not entry_id:
            raise CatalogError(f"{where} 有條目缺少 id")
        if entry_id in seen:
            raise CatalogError(f"{where} 有重複 id：{entry_id}")
        seen[entry_id] = entry
    return seen


def load_catalog(root: Optional[Path] = None, path: Optional[Path] = None) -> Dict[str, Any]:
    """載入內建目錄；專案根目錄的覆寫檔**只能加嚴，不能降級或停用**。

    覆寫檔會納入階段 5 的快照，但真正的防線是這條規則：
    把 `enforce=error` 改成 warning、或把條目停用，等於在沒有紀錄的情況下拆掉硬錯誤。
    """
    base = _load_file(Path(path) if path else DEFAULT_PATH)
    entries = _dedupe(base["entries"], str(path or DEFAULT_PATH))
    base_ids = set(entries)

    if root:
        override_path = Path(root) / PROJECT_OVERRIDE
        if override_path.is_file():
            override = _load_file(override_path)
            for entry in override["entries"]:
                entry_id = entry.get("id")
                if not entry_id:
                    raise CatalogError(f"{override_path.name} 有條目缺少 id")
                if not entry.get("enabled", True) or entry.get("disabled"):
                    if entry_id in base_ids:
                        raise CatalogError(
                            f"{override_path.name} 不可停用內建條目 {entry_id}（只能加嚴）"
                        )
                    entries.pop(entry_id, None)
                    continue
                merged = dict(entries.get(entry_id, {}))
                merged.update(entry)
                if entry_id in base_ids:
                    base_enforce = str(entries[entry_id].get("enforce", "warning"))
                    if base_enforce == "error" and str(merged.get("enforce", "warning")) != "error":
                        raise CatalogError(
                            f"{override_path.name} 不可把 {entry_id} 從 error 降級為 warning（只能加嚴）"
                        )
                entries[entry_id] = merged

    for entry_id, entry in entries.items():
        _validate(entry, entry_id)
    return {
        "schema_version": base.get("schema_version", 1),
        "updated": base.get("updated"),
        "entries": list(entries.values()),
    }


def catalog_rev(catalog: Dict[str, Any]) -> str:
    """目錄指紋：規則內容（id／型別／樣式／enforce）一改，舊 ack 就失效。"""
    fingerprint = [
        {
            "id": entry.get("id"),
            "type": (entry.get("detector") or {}).get("type"),
            "patterns": (entry.get("detector") or {}).get("patterns"),
            "exclude": (entry.get("detector") or {}).get("exclude"),
            "enforce": entry.get("enforce", "warning"),
        }
        for entry in sorted(catalog.get("entries", []), key=lambda item: str(item.get("id")))
    ]
    return hashlib.sha256(json.dumps(fingerprint, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:16]


_SENTENCE_BREAKS = ".!?;\n"


def _sentences(text: str) -> List[str]:
    return [chunk.strip() for chunk in re.split(r"(?<=[.!?;])\s+|\n+", text) if chunk.strip()]


def _sentence_around(text: str, start: int, end: int) -> str:
    """回傳命中片段所在的那一句（含句末標點），用來做「同句才互相赦免」。"""
    left = max(text.rfind(ch, 0, start) for ch in _SENTENCE_BREAKS)
    right_candidates = [text.find(ch, end) for ch in _SENTENCE_BREAKS]
    right_candidates = [idx for idx in right_candidates if idx != -1]
    right = min(right_candidates) if right_candidates else len(text)
    return text[left + 1:right + 1]


def _match(entry: Dict[str, Any], text: str) -> bool:
    detector = entry["detector"]
    flags = re.IGNORECASE if detector.get("ignore_case", True) else 0
    patterns = [re.compile(item, flags) for item in detector.get("patterns", [])]
    excludes = [re.compile(item, flags) for item in detector.get("exclude", []) or []]
    kind = detector["type"]
    if kind == "any":
        return any(pattern.search(text) for pattern in patterns)
    if kind == "all":
        # 交集必須在同一句內成立；否則「檔案某處提到 red、另一處提到 no visible source」
        # 會被誤判成一條完整症狀。
        for sentence in _sentences(text):
            if all(pattern.search(sentence) for pattern in patterns):
                return True
        return False
    # any_without：每一處命中只看它自己那句話有沒有 exclude。
    # 用整份文件判斷會讓「別處出現 neutral daylight」赦免掉真正的紅光句。
    for pattern in patterns:
        for match in pattern.finditer(text):
            sentence = _sentence_around(text, match.start(), match.end())
            if not any(rule.search(sentence) for rule in excludes):
                return True
    return False


def lint_text(text: str, catalog: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """回傳 {"errors": [...], "warnings": [...]}；每項帶 id/title/fix/evidence。"""
    if not isinstance(text, str) or not text.strip():
        return {"errors": [], "warnings": []}
    result: Dict[str, List[Dict[str, Any]]] = {"errors": [], "warnings": []}
    for entry in catalog.get("entries", []):
        try:
            hit = _match(entry, text)
        except re.error as exc:
            raise CatalogError(f"{entry.get('id')}: regex 無效：{exc}") from exc
        if not hit:
            continue
        item = {
            "id": entry["id"],
            "title": entry.get("title", ""),
            "severity": entry.get("severity", "medium"),
            "confidence": entry.get("confidence", "inferred"),
            "minimal_fix": entry.get("minimal_fix", ""),
            "evidence": entry.get("evidence", []),
        }
        bucket = "errors" if entry.get("enforce") == "error" else "warnings"
        result[bucket].append(item)
    return result


def format_hit(item: Dict[str, Any]) -> str:
    return (f"[{item['id']}] {item['title']}"
            f"（{item['confidence']}／{item['severity']}）：{item['minimal_fix']}")


# ==============================================================================
# ack 紀錄：讓「我接受這條警告」變成檔案，而不是終端裡的一行字
# ==============================================================================

def acks_path(root: Path) -> Path:
    return Path(root) / ACKS_RELATIVE


def load_acks(root: Path, strict: bool = True) -> Dict[str, Dict[str, Any]]:
    """回傳 {id: {...}}；檔案不存在回空字典，**壞檔預設報錯**（不要靜默當成沒有 ack）。"""
    path = acks_path(root)
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        if strict:
            raise CatalogError(f"{path} 無法解析：{exc}（ack 檔壞掉時一律停止，不要當成沒 ack）") from exc
        return {}
    result: Dict[str, Dict[str, Any]] = {}
    for item in payload.get("acks", []) or []:
        if isinstance(item, dict) and item.get("id"):
            result[str(item["id"]).strip().upper()] = item
    return result


def record_acks(root: Path, ids: List[str], note: str = "",
                covers: Optional[Dict[str, str]] = None,
                catalog: Optional[Dict[str, Any]] = None,
                rev: Optional[str] = None) -> Path:
    """把 ack 寫成 `review/catalog-acks.json`（合併、保留首次時間）。

    - `covers` 是 {segment_id: prompt_sha256}：ack 綁在**當時那份提示詞**上。
    - `rev` 是目錄指紋：規則改寫後，舊 ack 自動失效。
    """
    root = Path(root)
    path = acks_path(root)
    existing = load_acks(root)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    revision = rev or (catalog_rev(catalog) if catalog else None)
    for raw in ids:
        entry_id = str(raw).strip().upper()
        if not entry_id:
            continue
        entry = existing.get(entry_id) or {"id": entry_id, "acknowledged_at": now}
        entry["updated_at"] = now
        if note:
            entry["note"] = note
        if revision:
            entry["catalog_rev"] = revision
        if covers:
            merged_covers = dict(entry.get("covers") or {})
            merged_covers.update(covers)
            entry["covers"] = merged_covers
        existing[entry_id] = entry
    payload = {
        "schema_version": 2,
        "updated_at": now,
        "acks": [existing[key] for key in sorted(existing)],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        backup = path.with_name(path.name + ".bak")
        try:
            backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        except OSError:
            pass
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def ack_is_valid(entry: Optional[Dict[str, Any]], segment_id: str, prompt_sha256: str,
                 rev: Optional[str] = None) -> bool:
    """ack 是否仍涵蓋這一段的**現在**這份提示詞，且規則版本沒變。"""
    if not entry:
        return False
    covers = entry.get("covers")
    if not covers:
        return False
    if rev and entry.get("catalog_rev") and entry.get("catalog_rev") != rev:
        return False
    return str(covers.get(str(segment_id))) == str(prompt_sha256)


def authoritative_prompts(root: Path) -> Dict[str, str]:
    """每個段落「現在」的權威提示詞文字（segments-all.json 優先於逐集檔，與階段 6 送件同一來源）。"""
    root = Path(root)
    latest: Dict[str, tuple] = {}
    paths = sorted(
        (path for path in root.glob("segments-*.json") if SEGMENTS_LIKE.match(path.name)),
        key=lambda path: (1 if path.name == "segments-all.json" else 0, path.name),
    )
    for path in paths:
        rank = 1 if path.name == "segments-all.json" else 0
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            continue
        items = payload if isinstance(payload, list) else payload.get("segments", [])
        for item in items if isinstance(items, list) else []:
            if not isinstance(item, dict):
                continue
            sid = item.get("segment_id") or item.get("group") or item.get("id")
            text = item.get("h3_prompt") or item.get("prompt") or ""
            if not sid or not text:
                continue
            previous = latest.get(str(sid))
            if previous is None or rank >= previous[0]:
                latest[str(sid)] = (rank, str(text))
    return {sid: value[1] for sid, value in latest.items()}


def covers_from_segments(root: Path, ids: List[str],
                         catalog: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
    """從專案的 segments-*.json 算出「哪些段的提示詞命中這些規則」→ 寫 ack 用。"""
    wanted = {str(item).strip().upper() for item in ids if str(item).strip()}
    if not wanted:
        return {}
    catalog = catalog or load_catalog(root)
    covers: Dict[str, str] = {}
    for sid, text in authoritative_prompts(root).items():
        hits = lint_text(text, catalog)
        hit_ids = {hit["id"] for hit in hits["warnings"] + hits["errors"]}
        if hit_ids & wanted:
            covers[sid] = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return covers


def prune_acks(root: Path, catalog: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """移除已無效的 ack：covers 中對不到現行稿件（或稿件已刪）的段落。

    條目的 covers 清空後整條移除。回傳保留／移除的統計，供 CLI 與報告引用。
    """
    root = Path(root)
    path = acks_path(root)
    acks = load_acks(root)
    if not acks:
        return {"path": str(path), "kept": 0, "removed": [], "pruned_segments": 0}
    prompts = authoritative_prompts(root)
    kept: Dict[str, Dict[str, Any]] = {}
    removed: List[str] = []
    pruned_segments = 0
    for entry_id, entry in acks.items():
        covers = entry.get("covers") or {}
        fresh = {}
        for sid, digest in covers.items():
            text = prompts.get(str(sid))
            if text is not None and hashlib.sha256(text.encode("utf-8")).hexdigest() == digest:
                fresh[str(sid)] = digest
        pruned_segments += len(covers) - len(fresh)
        if not fresh:
            removed.append(entry_id)
            continue
        updated = dict(entry)
        updated["covers"] = fresh
        kept[entry_id] = updated
    if removed or pruned_segments:
        payload = {
            "schema_version": 2,
            "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "acks": [kept[key] for key in sorted(kept)],
        }
        if path.is_file():
            try:
                path.with_name(path.name + ".bak").write_text(
                    path.read_text(encoding="utf-8"), encoding="utf-8")
            except OSError:
                pass
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"path": str(path), "kept": len(kept), "removed": removed,
            "pruned_segments": pruned_segments}


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="失敗目錄：列出條目或掃描提示詞")
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--catalog", type=Path, default=None)
    parser.add_argument("--check", type=Path, help="要掃描的提示詞文字檔")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--acks", action="store_true", help="列出已記錄的 ack（review/catalog-acks.json）")
    parser.add_argument("--ack", nargs="*", metavar="ID", default=None,
                        help="寫入 ack：綁定目前 segments-*.json 中命中該規則的段與提示詞 hash")
    parser.add_argument("--prune-acks", action="store_true",
                        help="清掉已失效的 ack（covers 對不到現行稿件即移除）")
    parser.add_argument("--note", default="", help="寫入 ack 時附註（誰／為什麼）")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        catalog = load_catalog(args.root, args.catalog)
    except CatalogError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 2

    if args.ack is not None:
        ids = [str(item) for item in args.ack if str(item).strip()]
        if not ids:
            print("❌ --ack 需要至少一個 id（例如 --ack F-STILL-ENDING）", file=sys.stderr)
            return 2
        known = {str(entry["id"]).upper() for entry in catalog["entries"]}
        unknown = [item for item in ids if item.upper() not in known]
        if unknown:
            print(f"❌ 目錄裡沒有這些 id：{', '.join(unknown)}", file=sys.stderr)
            return 2
        covers = covers_from_segments(args.root, ids, catalog)
        if not covers:
            print("❌ 目前沒有任何分段的提示詞命中這些規則；ack 不會綁定任何稿件，拒絕寫入。",
                  file=sys.stderr)
            return 1
        path = record_acks(args.root, ids, note=args.note or "recorded via failure_catalog CLI",
                           covers=covers, catalog=catalog)
        print(f"🧾 已寫入 ack：{path}（{', '.join(ids)}；綁定 {len(covers)} 段、"
              f"目錄版本 {catalog_rev(catalog)}）")
        print("   提醒：ack 檔已納入階段 5 快照，請重新核准 stage-5。")
        return 0

    if args.prune_acks:
        try:
            report = prune_acks(args.root, catalog)
        except CatalogError as exc:
            print(f"❌ {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            print(f"[prune] 保留 {report['kept']} 條；移除整條：{', '.join(report['removed']) or '無'}；"
                  f"清掉失效 covers：{report['pruned_segments']} 段")
        return 0

    if args.acks:
        try:
            recorded = load_acks(args.root)
        except CatalogError as exc:
            print(f"❌ {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(recorded, ensure_ascii=False, indent=2))
        elif recorded:
            print(f"已記錄的 ack（{acks_path(args.root)}）：")
            for key, entry in sorted(recorded.items()):
                covers = entry.get("covers") or {}
                print(f"  [{key}] {entry.get('acknowledged_at')}　"
                      f"{len(covers)} 段　catalog_rev={entry.get('catalog_rev', '無')}　"
                      f"{entry.get('note', '')}")
        else:
            print("（沒有任何 ack 紀錄）")
        return 0

    if args.list or not args.check:
        if args.json:
            print(json.dumps(catalog, ensure_ascii=False, indent=2))
        else:
            print(f"失敗目錄（{len(catalog['entries'])} 條，schema {catalog['schema_version']}）")
            for entry in catalog["entries"]:
                print(f"  [{entry['id']}] {entry.get('title')}（{entry.get('confidence')}／{entry.get('severity')}）")
        return 0

    text = args.check.read_text(encoding="utf-8-sig")
    result = lint_text(text, catalog)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for item in result["errors"]:
            print(f"❌ {format_hit(item)}")
        for item in result["warnings"]:
            print(f"⚠️ {format_hit(item)}")
        if not result["errors"] and not result["warnings"]:
            print("✅ 沒有命中任何已知失敗模式")
    return 1 if result["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
