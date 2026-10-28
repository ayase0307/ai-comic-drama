#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read-only, offline inventory of dependencies by production capability.

This command reports executable/package presence only. It never checks a service,
network endpoint, account, token, model entitlement, or generation capability.
"""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import shutil
import subprocess
import sys
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def _command_version(name: str) -> dict[str, Any]:
    executable = shutil.which(name)
    if not executable:
        return {"available": False, "version": None}
    try:
        result = subprocess.run(
            [executable, "-version" if name == "ffmpeg" else "-version"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5,
        )
        first = (result.stdout or result.stderr).splitlines()
        return {"available": result.returncode == 0, "version": first[0] if first else "unknown"}
    except (OSError, subprocess.TimeoutExpired):
        return {"available": False, "version": None}


def _package_version(name: str) -> dict[str, Any]:
    try:
        return {"available": True, "version": importlib.metadata.version(name)}
    except importlib.metadata.PackageNotFoundError:
        return {"available": False, "version": None}


def build_report() -> dict[str, Any]:
    python_ok = sys.version_info >= (3, 10)
    pillow = _package_version("Pillow")
    numpy = _package_version("numpy")
    opencv = _package_version("opencv-python-headless")
    if not opencv["available"]:
        opencv = _package_version("opencv-python")
    ffmpeg = _command_version("ffmpeg")
    ffprobe = _command_version("ffprobe")

    def capability(name: str, dependencies: list[str], available: bool, note: str) -> dict[str, Any]:
        return {
            "name": name,
            "status": "ready" if available else "needs_setup",
            "dependencies": dependencies,
            "note": note,
        }

    return {
        "schema_version": 1,
        "inspection": "local executable/package presence only; no network, service, token, account, or model checks",
        "runtime": {"python": sys.version.split()[0], "minimum": "3.10", "available": python_ok},
        "dependencies": {"Pillow": pillow, "numpy": numpy, "opencv": opencv, "ffmpeg": ffmpeg, "ffprobe": ffprobe},
        "capabilities": [
            capability("企劃與文本改編", ["Python >= 3.10", "Python standard library"], python_ok,
                       "此能力不需要 jsonschema；專案含標準庫 schema validator。"),
            capability("構圖與圖片檔檢查", ["Python >= 3.10", "Pillow"], python_ok and pillow["available"],
                       "此結果只代表本機圖片工具依賴可用，不代表圖片已生成或已審核。"),
            capability("影片片段技術審查", ["ffmpeg", "ffprobe"], ffmpeg["available"] and ffprobe["available"],
                       "需提供本機影片；本檢查不產生影片。"),
            capability("動態 QA 與後製變速（選用）", ["opencv-python-headless", "numpy", "ffmpeg", "ffprobe"],
                       opencv["available"] and numpy["available"] and ffmpeg["available"] and ffprobe["available"],
                       "h3d motion 量光流需要 OpenCV；h3d ramp 只需要 ffmpeg＋numpy（音訊相關驗證）。"),
            capability("影片組裝與交付驗證", ["ffmpeg", "ffprobe"], ffmpeg["available"] and ffprobe["available"],
                       "需提供本機片段；實際輸出仍須通過交付 manifest 與解碼檢查。"),
        ],
        "generation": {
            "status": "not_checked",
            "note": "內建生成能力、Codex CLI 模型權限與選配 FreeVideo 服務不由離線依賴盤點判定；未連線、未讀取 token。",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="按製作能力盤點本機依賴（唯讀、離線）")
    parser.add_argument("--json", action="store_true", help="輸出機器可讀 JSON")
    args = parser.parse_args()
    report = build_report()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    print("本機依賴盤點（只檢查套件與執行檔；未連線服務或讀取 token）")
    for dependency, details in report["dependencies"].items():
        value = details["version"] if details["available"] else "未安裝/不可用"
        print(f"- {dependency}: {value}")
    for item in report["capabilities"]:
        print(f"- {item['name']}: {'可用' if item['status'] == 'ready' else '缺依賴'} — {item['note']}")
    print(f"- 圖像/影片生成服務: 未檢查 — {report['generation']['note']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
