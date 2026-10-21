#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Segment 級依賴帳本（v2）：哪裡改了、哪裡就失效——但帳本自己不能把證據抹平。

v1 的致命錯誤（2026-10-20 對抗式審查抓到）：`record()` 是快照覆寫，compile
成功後立刻把新 prompt 寫進去，video 欄位仍指舊檔 → 影片沒重跑也被蓋章成 clean。
真實專案第一次 record 就把 11 支「舊 prompt 產的影片」判成乾淨。

v2 的三個原則：

1. **merge，不是覆寫**：record 只更新真的有變的節點；video 的記錄不會因為
   prompt 更新而被順手刷新。
2. **prompt 記 provenance**：`built_from_layer2_sha256` 記「這份提示詞是從哪個
   分鏡版本編出來的」。status 比的是它對現在的 layer2，所以「重編譯過」與
   「只改分鏡沒重編」可以分開。
3. **用時間當第二證據**：影片檔 mtime 早於提示詞的 built_at，就是
   `video_older_than_prompt`——這是真實專案唯一能回溯判定的客觀訊號。

只認 `segments-(ep\\d+|all).json`，備份檔（`.bak`、`-backup`）不會被當成新基準。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

LEDGER_NAME = ".h3d-deps.json"
SCHEMA_VERSION = 2
SEGMENTS_PATTERN = re.compile(r"^segments-(ep\d+|all)\.json$")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> Optional[str]:
    try:
        digest = hashlib.sha256()
        with Path(path).open("rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(timespec="seconds")


def _mtime(path: Path) -> Optional[str]:
    try:
        return _iso(Path(path).stat().st_mtime)
    except OSError:
        return None


def _load_json(path: Path) -> Optional[Any]:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None


def _segments_kind(name: str) -> str:
    match = SEGMENTS_PATTERN.match(name)
    return "episode" if match and match.group(1) != "all" else "all"


def scan(root: Path) -> Dict[str, Any]:
    """掃描專案，回傳 {"segments": {...}, "ignored_videos": [...]}（不寫檔）。"""
    root = Path(root)
    entries: Dict[str, Dict[str, Any]] = {}
    ignored_videos: List[str] = []

    def entry_for(segment_id: str) -> Dict[str, Any]:
        return entries.setdefault(segment_id, {
            "layer2": {"path": None, "sha256": None},
            "prompts": [],
            "video": {"path": None, "sha256": None, "mtime": None},
        })

    # 1) Layer 2
    for layer2_path in sorted(root.glob("layer2/layer2-*.json")):
        data = _load_json(layer2_path)
        if not isinstance(data, dict):
            continue
        segment_id = str(data.get("segment_id") or layer2_path.stem.replace("layer2-", ""))
        entry = entry_for(segment_id)
        entry["layer2"] = {
            "path": layer2_path.relative_to(root).as_posix(),
            "sha256": sha256_file(layer2_path),
        }

    # 2) 編譯產物（只認 canonical 檔名；備份不會變成新基準）
    for segments_path in sorted(root.glob("segments-*.json")):
        if not SEGMENTS_PATTERN.match(segments_path.name):
            continue
        payload = _load_json(segments_path)
        if payload is None:
            continue
        items = payload if isinstance(payload, list) else payload.get("segments", [])
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            segment_id = item.get("segment_id") or item.get("group") or item.get("id")
            if not segment_id:
                continue
            prompt = item.get("h3_prompt") or item.get("prompt") or ""
            entry = entry_for(str(segment_id))
            entry["prompts"].append({
                "segments_file": segments_path.relative_to(root).as_posix(),
                "kind": _segments_kind(segments_path.name),
                "sha256": sha256_text(str(prompt)) if prompt else None,
                "frames": (item.get("metadata") or {}).get("frames"),
            })

    # 3) 影片（只收 id 已經存在的檔，其餘列 ignored，避免 `-v2` 之類生假段）
    known = set(entries)
    for video_path in sorted(root.glob("videos/*.mp4")):
        stem = video_path.stem
        if stem.endswith(".drift") or stem.endswith(".unverified"):
            continue
        if stem.startswith("_"):
            continue
        if stem not in known:
            ignored_videos.append(video_path.relative_to(root).as_posix())
            continue
        entry = entry_for(stem)
        entry["video"] = {
            "path": video_path.relative_to(root).as_posix(),
            "sha256": sha256_file(video_path),
            "mtime": _mtime(video_path),
        }

    # 每段挑一份權威 prompt：episode 優先於 all；同類多份 → ambiguous
    for entry in entries.values():
        prompts = entry.pop("prompts")
        chosen = None
        ambiguous = []
        for kind in ("episode", "all"):
            same = [item for item in prompts if item["kind"] == kind]
            if len({item["sha256"] for item in same}) > 1:
                ambiguous.append(f"{kind}:{len(same)}")
            elif same:
                chosen = same[0]
                break
        entry["prompt"] = dict(chosen) if chosen else {"segments_file": None, "sha256": None}
        entry["prompt_ambiguous"] = ambiguous

    return {"segments": dict(sorted(entries.items())), "ignored_videos": ignored_videos}


def record(root: Path, ledger_path: Optional[Path] = None) -> Path:
    """merge 現況與舊帳本；不把沒重跑的影片洗成 clean。"""
    root = Path(root)
    ledger_path = Path(ledger_path) if ledger_path else root / LEDGER_NAME
    snapshot = scan(root)
    current = snapshot["segments"]
    if not current:
        raise ValueError(f"{root} 掃不到任何分段；請確認 --root 是專案根目錄（含 layer2/ 與 segments-*.json）")
    previous = (_load_json(ledger_path) or {}).get("segments") or {}
    merged: Dict[str, Any] = {}

    for segment_id, now in current.items():
        was = previous.get(segment_id) or {}
        entry: Dict[str, Any] = {}
        entry["layer2"] = now["layer2"]
        prompt = dict(now["prompt"])
        if prompt.get("sha256"):
            prompt["built_from_layer2_sha256"] = now["layer2"]["sha256"]
            prompt["built_at"] = _mtime(root / (prompt.get("segments_file") or ""))
            if prompt["built_from_layer2_sha256"] != (was.get("prompt") or {}).get("built_from_layer2_sha256"):
                prompt["recompiled_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        entry["prompt"] = prompt
        entry["prompt_ambiguous"] = now["prompt_ambiguous"]
        # video：只有檔案本身變了才更新記錄；不因為 prompt 更新而刷新
        old_video = was.get("video") or {}
        new_video = now["video"]
        if new_video.get("sha256"):
            if old_video.get("sha256") == new_video.get("sha256"):
                # 同樣內容但重跑過（mtime 更新）→ 更新時間，讓 stale 可以清掉
                merged_video = dict(old_video)
                if old_video.get("mtime") != new_video.get("mtime"):
                    merged_video["mtime"] = new_video.get("mtime")
                entry["video"] = merged_video
            else:
                entry["video"] = new_video
        else:
            entry["video"] = old_video
        merged[segment_id] = entry

    # 保留已從磁碟移除的分段（status 要用它來報 removed）
    for segment_id, was in previous.items():
        if segment_id not in merged:
            merged[segment_id] = was

    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "root": str(root),
        "ignored_videos": snapshot["ignored_videos"],
        "segments": dict(sorted(merged.items())),
    }
    ledger_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return ledger_path


def status(root: Path, ledger_path: Optional[Path] = None) -> Dict[str, Any]:
    root = Path(root)
    ledger_path = Path(ledger_path) if ledger_path else root / LEDGER_NAME
    if not ledger_path.is_file():
        return {"ledger": str(ledger_path), "recorded": False, "segments": {},
                "stale": [], "unproduced": [], "removed": []}
    old = _load_json(ledger_path) or {}
    if old.get("schema_version") != SCHEMA_VERSION:
        return {"ledger": str(ledger_path), "recorded": True, "schema_mismatch": True,
                "segments": {}, "stale": [], "unproduced": [], "removed": [],
                "note": f"帳本 schema {old.get('schema_version')} 與程式 {SCHEMA_VERSION} 不符，請重跑 --record"}
    previous = old.get("segments") or {}
    current = scan(root)["segments"]
    report: Dict[str, Any] = {}
    stale: List[Dict[str, Any]] = []
    unproduced: List[str] = []
    removed: List[str] = []

    for segment_id in sorted(set(previous) | set(current)):
        was = previous.get(segment_id) or {}
        now = current.get(segment_id)
        reasons: List[str] = []
        if now is None:
            removed.append(segment_id)
            reasons.append("removed")
        elif not was:
            reasons.append("new")
        else:
            current_layer2 = (now.get("layer2") or {}).get("sha256")
            prompt = was.get("prompt") or {}
            if (was.get("layer2") or {}).get("sha256") != current_layer2:
                reasons.append("layer2_changed")
            if prompt.get("sha256"):
                if prompt.get("built_from_layer2_sha256") != current_layer2:
                    reasons.append("prompt_stale")
                elif (now.get("prompt") or {}).get("sha256") != prompt.get("sha256"):
                    reasons.append("prompt_changed_elsewhere")
            elif (now.get("prompt") or {}).get("sha256"):
                reasons.append("prompt_new")
            video = was.get("video") or {}
            now_video = now.get("video") or {}
            if video.get("sha256") and not now_video.get("sha256"):
                reasons.append("video_missing")
            elif video.get("sha256") and video.get("sha256") != now_video.get("sha256"):
                reasons.append("video_changed")
            elif video.get("sha256") and prompt.get("built_at") and video.get("mtime"):
                if str(video["mtime"]) < str(prompt["built_at"]):
                    reasons.append("video_older_than_prompt")
            if was.get("prompt_ambiguous") or now.get("prompt_ambiguous"):
                reasons.append("prompt_ambiguous")
        has_video = bool((was.get("video") or {}).get("sha256"))
        if reasons:
            if has_video:
                stale.append({"segment_id": segment_id, "reasons": reasons})
            else:
                unproduced.append(segment_id)
        report[segment_id] = {"reasons": reasons, "has_video": has_video}

    return {
        "ledger": str(ledger_path),
        "recorded": True,
        "generated_at": old.get("generated_at"),
        "ignored_videos": old.get("ignored_videos") or [],
        "segments": report,
        "stale": stale,
        "unproduced": unproduced,
        "removed": removed,
    }


def render(report: Dict[str, Any]) -> str:
    if not report.get("recorded"):
        return f"（尚未建立依賴帳本：{report['ledger']}；先跑 --record）"
    if report.get("schema_mismatch"):
        return f"⚠️ {report.get('note')}"
    lines = [f"依賴帳本：{report['ledger']}（記錄於 {report.get('generated_at')}）"]
    stale = report["stale"]
    unproduced = report["unproduced"]
    if not stale and not unproduced and not report["removed"]:
        lines.append("✅ 沒有 stale 的分段")
        return "\n".join(lines)
    if stale:
        lines.append(f"⚠️ {len(stale)} 段需要重跑（已有影片，但提示詞或分鏡已變）：")
        for item in stale:
            lines.append(f"  - {item['segment_id']}: {', '.join(item['reasons'])}")
    if unproduced:
        lines.append(f"ℹ️ {len(unproduced)} 段從未產出影片（不算 stale，但也不是完成）：")
        lines.append("  " + ", ".join(unproduced[:20]) + (" …" if len(unproduced) > 20 else ""))
    if report["removed"]:
        lines.append(f"🗑️ {len(report['removed'])} 段已從磁碟移除：{', '.join(report['removed'][:10])}")
    if report.get("ignored_videos"):
        lines.append(f"（另有 {len(report['ignored_videos'])} 個影片檔名對不上任何分鏡，已忽略）")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Segment 級依賴帳本（record / status）")
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--record", action="store_true", help="建立或合併 .h3d-deps.json")
    parser.add_argument("--status", action="store_true", help="比對現況並列出 stale 分段")
    parser.add_argument("--ledger", type=Path, default=None, help="帳本路徑（預設 <root>/.h3d-deps.json）")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true", help="有 stale 時回非 0")
    args = parser.parse_args(argv)
    root = args.root.resolve()

    if args.record:
        try:
            path = record(root, args.ledger)
        except ValueError as exc:
            print(f"[deps] ❌ {exc}", file=sys.stderr)
            return 2
        print(f"[deps] 已合併寫入 {path}")
        if not args.status:
            return 0
    report = status(root, args.ledger)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render(report))
    if args.strict and (report.get("stale") or report.get("schema_mismatch")):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
