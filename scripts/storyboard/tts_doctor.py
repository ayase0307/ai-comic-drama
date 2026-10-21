#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tts_doctor.py — TTS 能力盤點工具 (v1.0)

用途：
在正式配音前，先用這支唯讀工具檢查「這台機器現在能不能配音、該用哪個後端」。

規則：
  * 唯讀：不寫任何檔案、不上傳任何資料、不呼叫任何生成端點（只讀 health / profiles / models/status）。
  * 不洩漏密鑰：API 金鑰只顯示「有／無」與環境變數名稱，絕不印出值。
  * 離線可用：沒有設定檔、沒有伺服器、沒有 GPU 都要能正常輸出報告。

用法：
  python scripts/storyboard/tts_doctor.py            # 人類可讀表格
  python scripts/storyboard/tts_doctor.py --json     # 機器可讀 JSON
  python scripts/storyboard/tts_doctor.py --config config/tts.json
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import tts_engine  # noqa: E402  （需先補 sys.path）

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


# ==============================================================================
# 資料收集
# ==============================================================================

def _tool_report(name: str) -> Dict[str, Any]:
    """外部工具（ffmpeg / ffprobe）的存在性與版本。"""
    path = tts_engine._find_tool(name)
    if not path:
        return {"present": False, "path": None, "version": ""}
    return {"present": True, "path": path, "version": tts_engine._tool_version(path)}


def _config_summary(config: Dict[str, Any], config_path: Optional[Path]) -> Dict[str, Any]:
    """設定檔摘要；金鑰一律只呈現「有無」。"""
    engines: Dict[str, Any] = {}
    for engine_id, section in (config.get("engines") or {}).items():
        if not isinstance(section, dict):
            continue
        summary: Dict[str, Any] = {}
        for key, value in section.items():
            if key in {"api_key", "token", "secret"}:
                summary[key] = {"present": bool(str(value or "").strip())}
            elif key == "api_key_env":
                summary[key] = {"env_name": str(value or ""),
                                "present": bool(str(value or "") and bool(
                                    os.environ.get(str(value))))}
            elif key == "headers":
                summary[key] = {"names": sorted(str(k) for k in (value or {}))}
            elif key == "extra_body":
                summary[key] = {"keys": sorted(str(k) for k in (value or {}))}
            else:
                summary[key] = value
        engines[engine_id] = summary
    return {
        "path": str(config_path) if config_path else None,
        "present": bool(config_path),
        "default_engine": str(config.get("default_engine") or "voicestudio"),
        "voice_map": dict(config.get("voice_map") or {}),
        "engines": engines,
    }


def _voicestudio_report(config: Dict[str, Any]) -> Dict[str, Any]:
    """VoiceStudio 專屬細節：連線狀態、/health 重點、已下載模型、顯存衝突。"""
    health = tts_engine.engine_health("voicestudio", config)
    engine_cfg = tts_engine._engine_config(config, "voicestudio")
    raw_health = health.get("health") or {}
    summary = {
        "base_url": tts_engine._vs_base_url(engine_cfg),
        "server_reachable": bool(health.get("available")),
        "status": raw_health.get("status"),
        "model_loaded": raw_health.get("model_loaded"),
        "model_downloaded": raw_health.get("model_downloaded"),
        "model_size": raw_health.get("model_size"),
        "gpu_available": raw_health.get("gpu_available"),
        "gpu_type": raw_health.get("gpu_type"),
        "vram_used_mb": raw_health.get("vram_used_mb"),
        "backend_type": raw_health.get("backend_type"),
        "backend_variant": raw_health.get("backend_variant"),
        "gpu_compatibility_warning": raw_health.get("gpu_compatibility_warning"),
        "downloaded_models": list(health.get("downloaded_models") or []),
        "models": [
            {
                "model_name": item.get("model_name"),
                "display_name": item.get("display_name"),
                "downloaded": bool(item.get("downloaded")),
                "loaded": bool(item.get("loaded")),
            }
            for item in (health.get("models") or [])
        ],
        "gpu": health.get("gpu") or {},
        "warnings": list(health.get("warnings") or []),
    }
    return summary


def collect_report(config_path: Optional[str] = None) -> Dict[str, Any]:
    """收集完整盤點資料（唯讀）。"""
    config = tts_engine.load_config(config_path)
    located = tts_engine.locate_config(config_path)

    engines = tts_engine.discover_engines(config)
    for entry in engines:
        detail = tts_engine.engine_health(entry["id"], config)
        entry["next_steps"] = detail.get("next_steps", "")
        entry["warnings"] = list(detail.get("warnings") or [])

    available = [item["id"] for item in engines if item["available"]]
    recommended = ""
    for engine_id in tts_engine.AUTO_ENGINE_ORDER:
        if engine_id in available:
            recommended = engine_id
            break
    if not recommended and available:
        recommended = available[0]

    warnings: List[str] = []
    for entry in engines:
        warnings.extend(entry.get("warnings") or [])

    edge_entry = next((item for item in engines if item["id"] == "edge"), None)
    sapi_entry = next((item for item in engines if item["id"] == "sapi"), None)
    fish_entry = next((item for item in engines if item["id"] == "fish"), None)
    compat_entry = next((item for item in engines if item["id"] == "openai_compat"), None)

    return {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "python": {
            "version": platform.python_version(),
            "implementation": platform.python_implementation(),
            "executable": sys.executable,
        },
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
        "tools": {
            "ffmpeg": _tool_report("ffmpeg"),
            "ffprobe": _tool_report("ffprobe"),
        },
        "config": _config_summary(config, located),
        "engines": engines,
        "voicestudio": _voicestudio_report(config),
        "edge_tts": {
            "package_installed": bool(edge_entry.get("package_installed")) if edge_entry else False,
            "available": False,
            "broken": True,
            "note": "edge-tts 自 2026-10-10 起回 403（微軟要求 Sec-MS-GEC v2 token），且僅限非商用授權。",
        },
        "sapi": {
            "available": bool(sapi_entry and sapi_entry["available"]),
            "note": "Windows 原生 System.Speech，完全離線；輸出會再轉 48 kHz 單聲道 WAV。",
        },
        "fish": {
            "dialect": str((fish_entry or {}).get("dialect") or "fish_cloud"),
            "api_key_present": bool(
                (config.get("engines") or {}).get("fish", {}).get("api_key")
                or tts_engine._resolve_api_key(tts_engine._engine_config(config, "fish"))
            ),            "available": bool(fish_entry and fish_entry["available"]),
            "license_warning": (
                "Fish Speech 程式與權重採 Fish Audio Community License：年營收 50 萬美元以下可免費使用；"
                "若將 TTS 對外提供為託管服務，需另簽協議。"
            ),
        },
        "openai_compat": {
            "configured": bool(compat_entry and compat_entry["available"]),
            "base_url": str((config.get("engines") or {}).get("openai_compat", {}).get("base_url") or ""),
            "model": str((config.get("engines") or {}).get("openai_compat", {}).get("model") or ""),
        },
        "voice_map": dict(config.get("voice_map") or {}),
        "available_engines": available,
        "recommended_engine": recommended,
        "recommendation_reason": (
            f"依優先序 {' → '.join(tts_engine.AUTO_ENGINE_ORDER)}，第一個可用的是 {recommended}"
            if recommended else "目前沒有任何可用引擎，請先依各引擎的 next_steps 處理"
        ),
        "warnings": warnings,
    }


# ==============================================================================
# 人類可讀輸出
# ==============================================================================

_STATUS_ICON = {True: "✅", False: "⚠️"}


def print_human(report: Dict[str, Any]) -> None:
    """印出人類可讀的盤點表格。"""
    line = "=" * 70
    print(line)
    print("🩺 TTS 能力盤點 (tts_doctor)")
    print(line)
    print(f"產生時間：{report['generated_at']}")
    print(f"Python：{report['python']['implementation']} {report['python']['version']}")
    print(f"系統：{report['platform']['system']} {report['platform']['release']} ({report['platform']['machine']})")

    print("\n── 外部工具 ──")
    for name in ("ffmpeg", "ffprobe"):
        tool = report["tools"][name]
        version = tool.get("version") or "（版本未知）"
        print(f"  {_STATUS_ICON[bool(tool['present'])]} {name:8s} {'可用' if tool['present'] else '缺少'}"
              f"：{version}")
        if tool.get("path"):
            print(f"             路徑：{tool['path']}")
    if not report["tools"]["ffmpeg"]["present"]:
        print("     ⚠️ 沒有 ffmpeg 就無法把 mp3/aac/opus 正規化成 48 kHz 單聲道 WAV。")

    print("\n── 設定檔 ──")
    config = report["config"]
    if config["present"]:
        print(f"  ✅ 設定檔：{config['path']}")
        print(f"     default_engine：{config['default_engine']}")
    else:
        print("  ⚠️ 找不到 config/tts.json（將使用內建預設值）")
    if report["voice_map"]:
        print("     voice_map：")
        for key, value in report["voice_map"].items():
            print(f"       {key} → {value}")
    else:
        print("     voice_map：空（會直接用說話者 id 當音色名稱）")

    print("\n── 引擎 ──")
    for entry in report["engines"]:
        icon = "✅" if entry["available"] else "⚠️"
        print(f"  {icon} {entry['id']:14s} {entry['label']}")
        print(f"       狀態：{'可用' if entry['available'] else '不可用'} — {entry['reason']}")
        if entry.get("detail"):
            print(f"       說明：{entry['detail']}")
        for warning in entry.get("warnings") or []:
            print(f"       ⚠️ {warning}")
        if entry.get("next_steps"):
            print(f"       下一步：{entry['next_steps']}")

    print("\n── VoiceStudio / OmniVoice ──")
    vs = report["voicestudio"]
    print(f"  伺服器：{vs['base_url']} — {'可連線' if vs['server_reachable'] else '無法連線'}")
    if vs["server_reachable"]:
        print(f"     status={vs.get('status')}  model_loaded={vs.get('model_loaded')}  "
              f"model_size={vs.get('model_size')}")
        print(f"     gpu_type={vs.get('gpu_type')}  vram_used_mb={vs.get('vram_used_mb')}  "
              f"backend_type={vs.get('backend_type')}")
    if vs.get("downloaded_models"):
        print(f"     已下載模型：{', '.join(vs['downloaded_models'])}")
    else:
        print("     已下載模型：（無）")
    gpu = vs.get("gpu") or {}
    for item in gpu.get("gpus") or []:
        print(f"     GPU：{item.get('name')}  已用 {item.get('used_mb')} MB／共 {item.get('total_mb')} MB")
    for warning in vs.get("warnings") or []:
        print(f"  ⚠️ {warning}")

    print("\n── 其他注意 ──")
    print(f"  edge-tts：{'已安裝' if report['edge_tts']['package_installed'] else '未安裝'} — "
          f"{report['edge_tts']['note']}")
    print(f"  Windows SAPI：{'可用' if report['sapi']['available'] else '不可用'}")
    print(f"  Fish Audio：dialect={report['fish']['dialect']}  "
          f"API 金鑰：{'已設定' if report['fish']['api_key_present'] else '未設定'}")
    print(f"     ⚠️ {report['fish']['license_warning']}")
    print(f"  openai_compat：{'已設定' if report['openai_compat']['configured'] else '未設定'} "
          f"（{report['openai_compat']['base_url'] or 'base_url 未設定'}）")

    print("\n── 結論 ──")
    print(f"  建議 --tts-engine：{report['recommended_engine'] or '（無）'}")
    print(f"  理由：{report['recommendation_reason']}")
    print(line)


# ==============================================================================
# CLI 入口
# ==============================================================================

def main() -> int:
    """命令列入口；--json 輸出機器可讀 JSON。"""
    parser = argparse.ArgumentParser(description="tts_doctor.py — TTS 能力唯讀盤點工具")
    parser.add_argument("--json", action="store_true", help="輸出機器可讀 JSON")
    parser.add_argument("--config", type=str, default=None, help="指定 TTS 設定檔路徑")
    args = parser.parse_args()

    report = collect_report(args.config)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_human(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
