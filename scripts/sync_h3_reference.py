#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""同步 `references/h3/` 與上游 `h3-video-prompting` 的 `references/`。

背景：SKILL.md 曾寫「與上游同名同步」，但實際上有 15 個檔案落後、還缺
`shot-five-part.md`——因為同步是人工的，沒有紀錄也沒有檢查。
這支工具把同步變成可驗證的動作：

- `--check`：拿本機的上游 clone 逐檔比對（含 local_annotations），有漂移回 1
- `--sync`：把落後／缺漏的檔案補上（local_only 不動）
- `--write-manifest`：把目前同步狀態（commit＋逐檔 sha256）寫進 UPSTREAM.json

`UPSTREAM.json` 是「已經同步到哪裡」的可稽核紀錄；測試
`tests/test_h3_reference_sync.py` 只驗這個紀錄與本地檔案一致（不需要網路），
所以 CI 能擋住「本地被偷改」與「檔案被刪」，真正的上游更新則由 `--check` 發現。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
H3_DIR = ROOT / "references" / "h3"
MANIFEST_PATH = H3_DIR / "UPSTREAM.json"
DEFAULT_CLONE = Path(r"E:\MinimaxH3\h3-video-prompting")  # 作者家機路徑（保留相容）
UPSTREAM_ENV = "AICD_H3_UPSTREAM"


def upstream_candidates() -> list[Path]:
    """上游 clone 的搜尋順序（未給 --upstream 時）。

    1. 環境變數 AICD_H3_UPSTREAM；
    2. 作者家機 E:/MinimaxH3/h3-video-prompting（只在 Windows 才是絕對路徑）；
    3. 與本 repo 同層的 ../h3-video-prompting（一般人 clone 兩個 repo 的位置）。
    """
    import os

    candidates: list[Path] = []
    env = os.environ.get(UPSTREAM_ENV, "").strip()
    if env:
        candidates.append(Path(env).expanduser())
    if DEFAULT_CLONE.is_absolute():
        candidates.append(DEFAULT_CLONE)
    candidates.append(ROOT.parent / "h3-video-prompting")
    return candidates


def resolve_upstream(explicit: Path | None) -> tuple[Path | None, list[Path]]:
    """回傳 (找到的上游 clone, 試過的路徑)。explicit 有給就只看它。"""
    tried = [explicit] if explicit is not None else upstream_candidates()
    for candidate in tried:
        if candidate.is_dir():
            return candidate, tried
    return None, tried


def normalize(data: bytes) -> bytes:
    return data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def sha(data: bytes) -> str:
    return hashlib.sha256(normalize(data)).hexdigest()


def load_manifest() -> dict:
    if not MANIFEST_PATH.is_file():
        return {"upstream_repo": "https://github.com/ayase0307/h3-video-prompting",
                "local_only": [], "local_annotations": {}, "files": {}}
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def save_manifest(manifest: dict) -> None:
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8")


def apply_annotations(name: str, text: str, manifest: dict) -> str:
    for old, new in (manifest.get("local_annotations") or {}).get(name, []):
        text = text.replace(old, new)
    return text


def upstream_files(upstream: Path) -> dict[str, bytes]:
    ref = upstream / "references"
    if not ref.is_dir():
        raise SystemExit(f"❌ 找不到上游 references/：{ref}")
    return {p.name: p.read_bytes() for p in sorted(ref.glob("*.md"))}


def upstream_commit(upstream: Path) -> str:
    try:
        out = subprocess.run(["git", "-C", str(upstream), "rev-parse", "HEAD"],
                             capture_output=True, text=True, check=True)
        return out.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def cmd_check(upstream: Path) -> int:
    manifest = load_manifest()
    files = upstream_files(upstream)
    local_only = set(manifest.get("local_only") or [])
    drifted, missing, extra = [], [], []
    for name, blob in files.items():
        expected = apply_annotations(name, blob.decode("utf-8"), manifest).encode("utf-8")
        path = H3_DIR / name
        if not path.is_file():
            missing.append(name)
        elif sha(path.read_bytes()) != sha(expected):
            drifted.append(name)
    for path in sorted(H3_DIR.glob("*.md")):
        if path.name not in files and path.name not in local_only:
            extra.append(path.name)

    commit = upstream_commit(upstream) or "unknown"
    pinned = manifest.get("upstream_synced_commit") or "unrecorded"
    print(f"上游：{upstream} @ {commit[:12]}（紀錄：{pinned[:12]}）")
    print(f"上游檔案 {len(files)} 個；落後 {len(drifted)}；缺漏 {len(missing)}；未宣告 {len(extra)}")
    for label, items in (("落後", drifted), ("缺漏", missing), ("未宣告", extra)):
        if items:
            print(f"  {label}: {', '.join(items)}")
    if missing or extra:
        return 1
    if drifted and commit and commit != pinned:
        print("→ 上游有新 commit，跑 `--sync` 再 `--write-manifest`")
        return 1
    if drifted:
        print("→ 有檔案內容不同（可能是本地手改），先確認再 sync")
        return 1
    print("✅ references/h3 與上游一致")
    return 0


def cmd_sync(upstream: Path, quiet: bool = False) -> int:
    manifest = load_manifest()
    files = upstream_files(upstream)
    local_only = set(manifest.get("local_only") or [])
    changed, added = [], []
    for name, blob in files.items():
        text = apply_annotations(name, blob.decode("utf-8"), manifest)
        data = text.encode("utf-8")
        path = H3_DIR / name
        if not path.is_file():
            path.write_bytes(data)
            added.append(name)
        elif sha(path.read_bytes()) != sha(data):
            path.write_bytes(data)
            changed.append(name)
    if not quiet:
        print(f"新增 {len(added)}：{', '.join(added) or '無'}")
        print(f"更新 {len(changed)}：{', '.join(changed) or '無'}")
        if local_only:
            print(f"保留 local_only：{', '.join(sorted(local_only))}")
    return 0


def cmd_write_manifest(upstream: Path) -> int:
    manifest = load_manifest()
    files = upstream_files(upstream)
    entries = {}
    excluded = []
    for name, blob in files.items():
        text = apply_annotations(name, blob.decode("utf-8"), manifest)
        path = H3_DIR / name
        expected = sha(text.encode("utf-8"))
        if path.is_file() and sha(path.read_bytes()) == expected:
            entries[name] = sha(path.read_bytes())
        else:
            excluded.append(name)
    manifest.update({
        "upstream_repo": manifest.get("upstream_repo") or
        "https://github.com/ayase0307/h3-video-prompting",
        "local_clone": str(upstream),
        "upstream_synced_commit": upstream_commit(upstream),
        "upstream_synced_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "files": entries,
    })
    save_manifest(manifest)
    print(f"✅ 已寫入 {MANIFEST_PATH.relative_to(ROOT)}：{len(entries)} 個檔案")
    if excluded:
        print(f"⚠️ 未同步（本地內容不同，未納入紀錄）：{', '.join(excluded)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="同步 references/h3 與上游 h3-video-prompting")
    parser.add_argument("--upstream", type=Path, default=None,
                        help=f"上游 clone 路徑（未給時依序找 ${UPSTREAM_ENV}、E:\\MinimaxH3\\h3-video-prompting、"
                             "與本 repo 同層的 ../h3-video-prompting）")
    parser.add_argument("--check", action="store_true", help="只檢查漂移（CI／日常用）")
    parser.add_argument("--sync", action="store_true", help="補上落後與缺漏的檔案")
    parser.add_argument("--write-manifest", action="store_true", help="同步後更新 UPSTREAM.json")
    args = parser.parse_args(argv)

    upstream, tried = resolve_upstream(args.upstream)
    if upstream is None:
        suggestion = args.upstream or (ROOT.parent / "h3-video-prompting")
        print("❌ 找不到上游 clone；試過：" + "、".join(str(p) for p in tried) + "\n"
              f"   git clone https://github.com/ayase0307/h3-video-prompting \"{suggestion}\"\n"
              f"   或用 --upstream <路徑>／環境變數 {UPSTREAM_ENV} 指定",
              file=sys.stderr)
        return 2
    args.upstream = upstream

    if args.check:
        return cmd_check(args.upstream)
    if args.sync:
        code = cmd_sync(args.upstream)
        return cmd_write_manifest(args.upstream) if code == 0 and args.write_manifest else code
    if args.write_manifest:
        return cmd_write_manifest(args.upstream)
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
