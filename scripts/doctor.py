#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""本機產線自檢（read-only）。

比 `check_environment.py` 多做三件事：
  1. 量 GPU 剩餘顯存，並對照本機經驗值（4.20 GiB）。
  2. 探測產線三個服務的 port 是否在聽（FreeVideo 8189 / ComfyUI 8188 / VoiceStudio 8001）。
  3. 實測 ffmpeg 是否還吃 `-vsync`（9.0 起移除，須改用 `-fps_mode`）。

紀律：不寫檔、不讀 token、不上傳、不呼叫任何生成端點。
沒探測到的東西一律標 `unknown`，不得回報成通過。
"""
from __future__ import annotations

import argparse
import json
import platform
import shutil
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

SAFE_VRAM_MB = 4300  # 本機 RTX 4060 Ti 8GB 的經驗門檻，不是 H3 官方規格
SERVICE_PORTS = {
    "freevideo_8189": 8189,
    "comfyui_8188": 8188,
    "voicestudio_8001": 8001,
}


def _run(command: list, timeout: int = 20) -> Optional[subprocess.CompletedProcess]:
    try:
        return subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return None


def check_tool(name: str, version_command: list) -> Dict[str, Any]:
    result = _run(version_command)
    if result is None:
        return {"status": "unknown", "version": None,
                "note": "執行逾時或無法啟動；狀態未知（不是 missing）"}
    if result.returncode != 0:
        return {"status": "missing", "version": None}
    first_line = (result.stdout or result.stderr or "").strip().splitlines()
    return {"status": "ready", "version": first_line[0][:120] if first_line else None}


def check_gpu() -> Dict[str, Any]:
    result = _run([
        "nvidia-smi", "--query-gpu=memory.free,memory.total,name",
        "--format=csv,noheader,nounits",
    ])
    if result is None or result.returncode != 0 or not result.stdout.strip():
        return {"status": "unknown", "note": "nvidia-smi 不可用；顯存未檢查"}
    parts = [part.strip() for part in result.stdout.strip().splitlines()[0].split(",")]
    try:
        free_mb, total_mb = int(parts[0]), int(parts[1])
    except (IndexError, ValueError):
        return {"status": "unknown", "note": "nvidia-smi 輸出無法解析"}
    return {
        "status": "ready",
        "name": parts[2] if len(parts) > 2 else "",
        "free_mb": free_mb,
        "total_mb": total_mb,
        "free_gib": round(free_mb / 1024.0, 2),
        "below_experience_threshold": free_mb < SAFE_VRAM_MB,
        "note": (
            f"低於本機經驗值 {SAFE_VRAM_MB} MB（差 {SAFE_VRAM_MB - free_mb} MB）"
            if free_mb < SAFE_VRAM_MB else "高於本機經驗值"
        ),
    }


def check_port(port: int, timeout: float = 0.4) -> Dict[str, Any]:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            listening = sock.connect_ex(("127.0.0.1", port)) == 0
    except OSError:
        return {"status": "unknown", "port": port, "listening": None}
    return {"status": "ready" if listening else "closed", "port": port, "listening": listening}


def check_ffmpeg_vsync() -> Dict[str, Any]:
    """實測 -vsync 是否仍被接受；9.0 起移除。

    只有「錯誤訊息明確指向 -vsync 不被辨識」才判 False。
    其他任何失敗（缺 lavfi、編碼器問題、逾時）都回 unknown——
    把不確定的失敗講成「你的 ffmpeg 太新」是另一種假資訊。
    """
    if not shutil.which("ffmpeg"):
        return {"status": "unknown", "accepts_vsync": None}
    result = _run([
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "testsrc=duration=0.10:size=64x64:rate=24",
        "-vf", "fps=24", "-vsync", "0", "-f", "null", "-",
    ], timeout=30)
    if result is None:
        return {"status": "unknown", "accepts_vsync": None, "note": "實測逾時；狀態未知"}
    if result.returncode == 0:
        return {"status": "ready", "accepts_vsync": True, "note": "可接受 -vsync"}
    stderr = (result.stderr or "") + (result.stdout or "")
    lowered = stderr.lower()
    if "vsync" in lowered and ("unrecognized" in lowered or "unknown" in lowered
                               or "not found" in lowered or "invalid" in lowered):
        return {"status": "ready", "accepts_vsync": False,
                "note": "不支援 -vsync（ffmpeg 9+），請改用 -fps_mode"}
    return {"status": "unknown", "accepts_vsync": None,
            "note": f"實測失敗但非 -vsync 問題：{stderr.strip().splitlines()[0][:120] if stderr.strip() else '無訊息'}"}


def check_disk(path: Path) -> Dict[str, Any]:
    try:
        usage = shutil.disk_usage(str(path))
    except OSError as exc:
        return {"status": "unknown", "note": str(exc)}
    return {
        "status": "ready",
        "free_gib": round(usage.free / (1024 ** 3), 1),
        "total_gib": round(usage.total / (1024 ** 3), 1),
    }


def build_report(root: Path) -> Dict[str, Any]:
    tools = {
        "ffmpeg": check_tool("ffmpeg", ["ffmpeg", "-version"]),
        "ffprobe": check_tool("ffprobe", ["ffprobe", "-version"]),
        "nvidia_smi": check_tool("nvidia-smi", ["nvidia-smi", "--version"]),
    }
    gpu = check_gpu()
    services = {name: check_port(port) for name, port in SERVICE_PORTS.items()}
    ffmpeg_vsync = check_ffmpeg_vsync()
    disk = check_disk(root)

    blocked, warn, ready = [], [], []
    for name, info in tools.items():
        if info["status"] == "ready":
            ready.append(f"工具 {name}")
        elif info["status"] == "unknown":
            warn.append(f"工具 {name} 狀態未知（{info.get('note') or '逾時'}）")
        else:
            blocked.append(f"工具 {name}")
    (ready if gpu.get("status") == "ready" else warn).append("GPU 顯存")
    if gpu.get("below_experience_threshold"):
        warn.append(f"GPU 剩餘 {gpu['free_gib']} GiB 低於經驗值 {SAFE_VRAM_MB} MB")
    for name, info in services.items():
        (ready if info.get("listening") else warn).append(f"服務 {name}")
    if ffmpeg_vsync.get("accepts_vsync") is False:
        warn.append("ffmpeg 不支援 -vsync（腳本若仍使用需改 -fps_mode）")
    if disk.get("status") == "ready" and disk["free_gib"] < 20:
        warn.append(f"工作槽剩餘 {disk['free_gib']} GiB，產線可能不足")

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "platform": f"{platform.system()} {platform.release()}",
        "python": platform.python_version(),
        "root": str(root),
        "scope": "local only；不讀 token、不呼叫生成端點、不寫檔",
        "tools": tools,
        "gpu": gpu,
        "services": services,
        "ffmpeg_vsync": ffmpeg_vsync,
        "disk": disk,
        "verdict": {"ready": ready, "warn": warn, "blocked": blocked},
    }


def print_human(report: Dict[str, Any]) -> None:
    print("本機產線自檢（read-only）")
    print(f"- 平台: {report['platform']} / Python {report['python']}")
    for name, info in report["tools"].items():
        print(f"- 工具 {name}: {info['status']} — {info.get('version') or '未取得'}")
    gpu = report["gpu"]
    if gpu.get("status") == "ready":
        print(f"- GPU: {gpu.get('name')} 剩餘 {gpu['free_mb']} MB / {gpu['total_mb']} MB — {gpu['note']}")
    else:
        print(f"- GPU: {gpu.get('note')}")
    for name, info in report["services"].items():
        state = "在聽" if info.get("listening") else ("未開" if info.get("listening") is False else "未知")
        print(f"- 服務 {name}: {state}")
    vsync = report["ffmpeg_vsync"]
    print(f"- ffmpeg -vsync: {vsync.get('note') or '未測'}")
    print(f"- 磁碟: {report['disk'].get('free_gib')} GiB 可用")
    verdict = report["verdict"]
    for label in ("blocked", "warn"):
        for item in verdict[label]:
            print(f"  [{'BLOCKED' if label == 'blocked' else 'WARN'}] {item}")


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description="本機 ai-comic-drama 產線自檢（read-only）")
    parser.add_argument("--root", default=".", help="專案或工作目錄（只用于磁碟檢查）")
    parser.add_argument("--json", action="store_true", help="輸出 JSON")
    parser.add_argument("--strict", action="store_true", help="有 BLOCKED 或缺 ffmpeg 時回非 0")
    args = parser.parse_args(argv)

    report = build_report(Path(args.root).resolve())
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_human(report)
    if args.strict:
        missing_ffmpeg = report["tools"]["ffmpeg"]["status"] != "ready"
        ffmpeg_regression = report["ffmpeg_vsync"].get("accepts_vsync") is False
        return 1 if (report["verdict"]["blocked"] or missing_ffmpeg or ffmpeg_regression) else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
