#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate asset prompts from an explicit JSON list through Codex CLI."""

from __future__ import annotations

import argparse
import json
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
            command.extend(["-C", work, instruction])
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
                return False

            scratch = pathlib.Path(work)
            candidates = [p for p in scratch.glob("*.png") if _valid_png(p)]
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
            candidate.replace(destination)
            for alias in target.get("aliases", []):
                alias_name = safe_filename(alias)
                alias_path = output_dir / alias_name
                temporary_alias = alias_path.with_name(alias_path.name + ".tmp")
                temporary_alias.write_bytes(destination.read_bytes())
                temporary_alias.replace(alias_path)
            return True
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
    for index, item in enumerate(prompts, 1):
        prompt = str(item.get("full_prompt", "")).strip()
        name = safe_filename(item.get("filename") or item.get("name", ""))
        print(f"[{index}/{len(prompts)}] {name}")
        if generate_single_asset_codex(item, prompt, args.output_dir, model=args.model,
                                       timeout_sec=args.timeout, codex_bin=executable):
            completed.append(name)
        else:
            failed.append(name)
            break
        if index < len(prompts):
            time.sleep(3)
    print(f"完成 {len(completed)} / {len(prompts)}; failed={failed}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
