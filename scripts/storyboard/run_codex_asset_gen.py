#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate asset prompts from an explicit JSON list through Codex CLI."""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any, Dict, List

from PIL import Image


def load_prompts_map(prompts_path: pathlib.Path) -> List[Dict[str, Any]]:
    if not prompts_path.is_file():
        raise FileNotFoundError(f"找不到提示詞 JSON: {prompts_path}")
    data = json.loads(prompts_path.read_text(encoding="utf-8"))
    if not isinstance(data, list) or not data:
        raise ValueError("提示詞 JSON 必須是非空 asset prompt 清單")
    return data


def safe_filename(value: str) -> str:
    # Treat both Windows and POSIX separators as path boundaries before sanitizing.
    leaf = str(value).replace("\\", "/").split("/")[-1]
    leaf = re.sub(r"[^A-Za-z0-9._-]+", "-", leaf).strip(".-_")
    if not leaf:
        raise ValueError("資產 filename 無有效安全檔名")
    if pathlib.Path(leaf).suffix.lower() != ".png":
        leaf = pathlib.Path(leaf).stem + ".png"
    return leaf


def validate_asset_list(items: List[Dict[str, Any]]) -> None:
    occupied: Dict[str, str] = {}
    for index, item in enumerate(items, 1):
        raw = item.get("filename") or item.get("name", "")
        filename = safe_filename(raw)
        if not str(item.get("full_prompt", "")).strip():
            raise ValueError(f"第 {index} 項 {filename} 缺少 full_prompt")
        for candidate in [filename, *(safe_filename(alias) for alias in item.get("aliases", []))]:
            key = candidate.casefold()
            if key in occupied:
                raise ValueError(f"資產輸出名稱碰撞: {occupied[key]} 與 {filename} -> {candidate}")
            occupied[key] = filename


def stale_character_prompts(items: List[Dict[str, Any]]) -> List[str]:
    """export_asset_prompts.py 的角色項會帶 template 標記；沒有的是母版改版前匯出的舊檔。"""
    return [str(i.get("filename") or i.get("name")) for i in items if i.get("type") == "character" and not i.get("template")]


def resolve_codex_executable(explicit: str | None = None) -> str:
    candidate = explicit or ("codex.exe" if sys.platform.startswith("win") else "codex")
    found = shutil.which(candidate)
    if not found:
        raise FileNotFoundError(f"找不到 Codex CLI executable: {candidate}")
    return str(pathlib.Path(found).resolve())


def validate_codex_cli(executable: str) -> None:
    """Read-only capability check. Never starts a generation request."""
    version = subprocess.run([executable, "--version"], capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=10)
    help_result = subprocess.run([executable, "exec", "--help"], capture_output=True, text=True,
                                 encoding="utf-8", errors="replace", timeout=10)
    if version.returncode != 0 or help_result.returncode != 0:
        raise RuntimeError("Codex CLI --version/exec --help 檢查失敗")
    help_text = help_result.stdout + help_result.stderr
    if "--sandbox" not in help_text or "--skip-git-repo-check" not in help_text:
        raise RuntimeError("此 Codex CLI 缺少 workspace sandbox 或 skip-git-repo-check 支援")


_LIMIT_RE = re.compile(r"usage limit|rate limit", re.I)
_RETRY_RE = re.compile(r"try again (?:at|in)\s+([^\n.]+)", re.I)


def parse_usage_limit(text: str) -> str | None:
    """Codex 撞用量上限時 log 才有訊息；回傳重試時間字串（沒寫時間回空字串），沒撞到回 None。"""
    if not _LIMIT_RE.search(text or ""):
        return None
    match = _RETRY_RE.search(text)
    return match.group(1).strip() if match else ""


def find_session_images(codex_home: pathlib.Path, session_id: str) -> List[pathlib.Path]:
    """依 session 目錄取圖（generated_images/<session>/），並行時不會抓到別的工作剛生成的圖。"""
    if not session_id:
        return []
    folder = codex_home / "generated_images" / session_id
    return sorted(p for p in folder.glob("*.png") if _valid_png(p)) if folder.is_dir() else []


def _session_id(text: str) -> str:
    match = re.search(r"session id:\s*([0-9a-fA-F-]{8,})", text or "")
    return match.group(1) if match else ""


class UsageLimitHit(Exception):
    def __init__(self, retry_at: str):
        super().__init__(retry_at)
        self.retry_at = retry_at


def _valid_png(path: pathlib.Path) -> bool:
    try:
        if not path.is_file() or path.stat().st_size == 0:
            return False
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            return image.width > 0 and image.height > 0
    except Exception:
        return False


def generate_single_asset_codex(
    target: Dict[str, Any], prompt: str, output_dir: pathlib.Path,
    model: str | None = None, timeout_sec: int = 180, codex_bin: str | None = None,
) -> bool:
    name = safe_filename(target.get("filename") or target.get("name", ""))
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / name
    instruction = (
        "Generate a high-resolution 16:9 image using the built-in image generation tool.\n\n"
        f"Prompt:\n{prompt}\n\nSave the newly generated PNG as {name} in the current working directory."
    )
    started = time.time()
    try:
        # A fresh per-call directory ensures no previous output can be mistaken
        # for an artifact produced by this invocation.
        with tempfile.TemporaryDirectory(prefix="codex-asset-", dir=output_dir) as work:
            executable = resolve_codex_executable(codex_bin)
            command = [executable, "exec", "--sandbox", "workspace-write", "--skip-git-repo-check"]
            if model:
                command.extend(["-m", model])
            command.extend(["-C", work])
            for ref in target.get("refs", []) or []:
                ref_path = pathlib.Path(ref)
                if not ref_path.is_file():
                    print(f"❌ {name} 參考圖不存在: {ref_path.name}")
                    return False
                command.extend(["-i", str(ref_path.resolve())])
            command.extend(["--", instruction])
            proc = subprocess.Popen(
                command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding="utf-8", errors="replace",
            )
            try:
                stdout, stderr = proc.communicate(timeout=timeout_sec)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.communicate()
                print(f"❌ 生成 {name} 逾時 ({timeout_sec}s)")
                return False

            print(f"Codex returncode={proc.returncode} elapsed={time.time() - started:.1f}s")
            if proc.returncode != 0:
                retry_at = parse_usage_limit((stdout or "") + (stderr or ""))
                if retry_at is not None:
                    raise UsageLimitHit(retry_at)
                return False

            scratch = pathlib.Path(work)
            candidates = [p for p in scratch.glob("*.png") if _valid_png(p)]
            if not candidates:
                home = pathlib.Path(os.environ.get("CODEX_HOME") or pathlib.Path.home() / ".codex")
                candidates = find_session_images(home, _session_id((stdout or "") + (stderr or "")))
                if len(candidates) > 1:
                    candidates = candidates[-1:]
            expected = scratch / name
            if _valid_png(expected):
                candidate = expected
            elif len(candidates) == 1:
                candidate = candidates[0]
            else:
                print(f"❌ 本次執行未產生唯一有效 PNG: {name}")
                return False

            # Atomic replacement keeps a prior valid artifact intact until a
            # complete new image has passed decoding checks.
            shutil.move(str(candidate), str(destination)) if candidate.parent != scratch else candidate.replace(destination)
            for alias in target.get("aliases", []):
                alias_name = safe_filename(alias)
                alias_path = output_dir / alias_name
                temporary_alias = alias_path.with_name(alias_path.name + ".tmp")
                temporary_alias.write_bytes(destination.read_bytes())
                temporary_alias.replace(alias_path)
            return True
    except UsageLimitHit:
        raise
    except Exception as exc:
        # Never print subprocess streams or command arguments; they may contain
        # prompts or environment-specific data.
        print(f"❌ 生成 {name} 失敗: {type(exc).__name__}")
        return False


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="依提示詞清單逐項產生資產圖片")
    parser.add_argument("--prompts", type=pathlib.Path, required=True, help="資產提示詞 JSON 清單")
    parser.add_argument("--output-dir", type=pathlib.Path, required=True, help="圖片輸出目錄")
    parser.add_argument("--model", default=None, help="可選 Codex 模型名稱")
    parser.add_argument("--codex-bin", default=None, help="可選 Codex CLI executable 路徑")
    parser.add_argument("--timeout", type=int, default=180, help="每張圖片逾時秒數")
    parser.add_argument("--parallel", type=int, default=1, help="並行張數（每張獨立暫存目錄、依 session 取圖，不會串圖）")
    args = parser.parse_args(argv)
    try:
        prompts = load_prompts_map(args.prompts)
        validate_asset_list(prompts)
        for stale in stale_character_prompts(prompts):
            print(f"[警告] {stale} 是舊版角色提示詞（缺 template 標記），請先重跑 export_asset_prompts.py", file=sys.stderr)
        executable = resolve_codex_executable(args.codex_bin)
        validate_codex_cli(executable)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"提示詞載入失敗: {exc}", file=sys.stderr)
        return 2

    completed: List[str] = []
    failed: List[str] = []
    limit_at: List[str] = []
    total = len(prompts)

    def work_one(index: int, item: Dict[str, Any]):
        name = safe_filename(item.get("filename") or item.get("name", ""))
        if limit_at:
            return name, None
        print(f"[{index}/{total}] {name}")
        try:
            ok = generate_single_asset_codex(item, str(item.get("full_prompt", "")).strip(), args.output_dir,
                                             model=args.model, timeout_sec=args.timeout, codex_bin=executable)
        except UsageLimitHit as hit:
            limit_at.append(hit.retry_at)
            return name, None
        return name, ok

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=max(1, args.parallel)) as pool:
        results = list(pool.map(lambda pair: work_one(*pair), enumerate(prompts, 1)))
    pending = []
    for (name, ok), item in zip(results, prompts):
        if ok is True:
            completed.append(name)
        elif ok is False:
            failed.append(name)
        else:
            pending.append(item)
    if limit_at:
        remaining = args.prompts.with_name(args.prompts.stem + ".remaining.json")
        remaining.write_text(json.dumps(pending, ensure_ascii=False, indent=2), encoding="utf-8")
        when = limit_at[0] or "（log 未寫時間）"
        print(f"⏸ Codex 用量上限，預計 {when} 後可重試；未做的 {len(pending)} 張已寫入 {remaining.name}，到時以 --prompts 該檔續跑")
        print(f"完成 {len(completed)} / {total}; failed={failed}")
        return 3
    print(f"完成 {len(completed)} / {len(prompts)}; failed={failed}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
