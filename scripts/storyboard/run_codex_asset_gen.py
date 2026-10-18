#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_codex_asset_gen.py — Codex CLI 循序資產生圖控管腳本
嚴格遵循單線程循序生成、超時保護與圖檔非空校驗。
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import time
from typing import Dict, List

# 確保 Windows 終端輸出 UTF-8
if sys.platform.startswith("win"):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

TARGET_DIR = pathlib.Path(r"C:\Users\kirit\OneDrive\文件\噩盡島\噩盡島-漫劇\ch02\images").resolve()
ASSET_PROMPTS_JSON = TARGET_DIR / "asset_prompts.json"

# 需要生成的 7 張第二章核心資產清單 (比對 asset_prompts.json)
TARGET_ASSETS = [
    {
        "key": "char-YeWeishan",
        "primary_file": "char-YeWeishan.png",
        "aliases": ["char-ye-weishan.png"],
    },
    {
        "key": "scene-fast-food",
        "primary_file": "scene-fast-food.png",
        "aliases": ["scene-fast-food-restaurant.png"],
    },
    {
        "key": "creature-giant-rat",
        "primary_file": "creature-giant-rat.png",
        "aliases": ["creature-GiantRat.png"],
    },
    {
        "key": "scene-banqiao-station",
        "primary_file": "scene-banqiao-station.png",
        "aliases": ["scene-banqiao-station-hall.png"],
    },
    {
        "key": "creature-jelly-slime",
        "primary_file": "creature-jelly-slime.png",
        "aliases": ["creature-JellySlime.png"],
    },
    {
        "key": "char-BrownHairSlayer",
        "primary_file": "char-BrownHairSlayer.png",
        "aliases": ["char-brown-hair-slayer.png"],
    },
    {
        "key": "char-BlackHairDaoist",
        "primary_file": "char-BlackHairDaoist.png",
        "aliases": ["char-black-hair-daoist.png"],
    },
]


def load_prompts_map() -> Dict[str, str]:
    if not ASSET_PROMPTS_JSON.exists():
        raise FileNotFoundError(f"找不到資產提示詞定義檔: {ASSET_PROMPTS_JSON}")
    with ASSET_PROMPTS_JSON.open("r", encoding="utf-8") as f:
        data = json.load(f)
    mapping = {}
    for item in data:
        fname = item.get("filename", "")
        mapping[fname] = item.get("full_prompt", "")
        # 也以 slug 存
        name = item.get("name", "")
        mapping[name] = item.get("full_prompt", "")
    return mapping


def generate_single_asset_codex(target: Dict[str, Any], prompt: str, timeout_sec: int = 120) -> bool:
    primary_name = target["primary_file"]
    dest_path = TARGET_DIR / primary_name

    print(f"\n================================================================================")
    print(f"🎨 [開始生成] 目標: {primary_name}")
    print(f"   目標路徑: {dest_path}")
    print(f"   Prompt 長度: {len(prompt)} 字元")
    print(f"================================================================================")

    # 構造給 Codex CLI 的指令
    # 要求 Codex 使用其生圖工具產出檔案並命名為 primary_name
    codex_instruction = (
        f"Generate a 16:9 image using the built-in image generation tool with the following prompt:\n\n"
        f"\"{prompt}\"\n\n"
        f"Save the generated image strictly to the current working directory as '{primary_name}'."
    )

    cmd = [
        "codex", "exec",
        "--sandbox", "danger-full-access",
        "-C", str(TARGET_DIR),
        codex_instruction,
    ]

    t0 = time.time()
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        try:
            stdout, stderr = proc.communicate(timeout=timeout_sec)
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate()
            print(f"❌ [逾時警告] 生成 {primary_name} 超過 {timeout_sec} 秒無回應！進程已終止。")
            print(f"   stdout 末尾: {stdout[-500:] if stdout else '無'}")
            return False

        elapsed = time.time() - t0
        print(f"   Codex 進程返回碼: {proc.returncode} (耗時 {elapsed:.1f}s)")

        # 檢查產物檔案
        if dest_path.exists():
            size = dest_path.stat().st_size
            if size > 10240:  # 大於 10KB
                print(f"✅ [成功出圖] {primary_name} 生成完成！大小: {size:,} bytes")
                # 建立別名檔案
                for alias in target.get("aliases", []):
                    alias_path = TARGET_DIR / alias
                    if not alias_path.exists():
                        alias_path.write_bytes(dest_path.read_bytes())
                        print(f"   🔗 已建立別名檔案: {alias}")
                return True
            else:
                print(f"⚠️ [異常圖檔] {primary_name} 檔案過小 ({size} bytes)，可能為空圖！")
                return False
        else:
            # 檢查是否有同目錄下新產生的 png
            recent_pngs = [
                p for p in TARGET_DIR.glob("*.png")
                if p.stat().st_mtime >= t0 - 5 and p.name != primary_name
            ]
            if recent_pngs:
                latest = max(recent_pngs, key=lambda p: p.stat().st_mtime)
                print(f"ℹ️ 發現新生成的候選圖檔: {latest.name}，正在更名為 {primary_name}...")
                dest_path.write_bytes(latest.read_bytes())
                for alias in target.get("aliases", []):
                    (TARGET_DIR / alias).write_bytes(dest_path.read_bytes())
                return True

            print(f"❌ [找不到檔案] 未能在 {TARGET_DIR} 找到產出的 {primary_name}！")
            if stderr:
                print(f"   stderr: {stderr[:500]}")
            return False

    except Exception as e:
        print(f"❌ [執行異常] {e}")
        return False


def main():
    prompts_map = load_prompts_map()

    completed: List[str] = []
    failed: List[str] = []

    print("🚀 啟動 Codex CLI 循序生成第二章 7 張核心資產設定圖...")
    for idx, target in enumerate(TARGET_ASSETS, 1):
        pname = target["primary_file"]
        # 尋找 prompt
        prompt = ""
        for k, v in prompts_map.items():
            if target["key"] in k or pname in k:
                prompt = v
                break
        if not prompt:
            print(f"⚠️ 找不到 {pname} 的提示詞，跳過！")
            failed.append(pname)
            continue

        ok = generate_single_asset_codex(target, prompt, timeout_sec=120)
        if ok:
            completed.append(pname)
        else:
            failed.append(pname)
            print(f"⚠️ 生成中斷或失敗，停止後續生圖以免連續超時。")
            break

        # 短暫休眠 2 秒避免密集請求
        time.sleep(2)

    print("\n" + "=" * 80)
    print(f"🏁 資產生成進度總結：成功 {len(completed)} / 7 張，失敗/未完成 {len(failed)} 張")
    print(f"   已完成清單: {completed}")
    print(f"   失敗/未完成: {failed}")
    print("=" * 80)


if __name__ == "__main__":
    main()
