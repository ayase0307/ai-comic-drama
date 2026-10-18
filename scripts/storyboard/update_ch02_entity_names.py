# -*- coding: utf-8 -*-
"""
update_ch02_entity_names.py — 全面修正第二章角色聖經中誤用的名稱
將「狄純 / Di Chun」修正為「瑪蓮 / Malien」
將「張如鴻 / Zhang Ruhong」修正為「奇雅 / Qiya」
並在相關分鏡、腳本、Layer 2、Handoff 中標註真名。
"""
import os
import sys
import re

if sys.platform.startswith("win"):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CH02_DIR = r"C:\Users\kirit\OneDrive\文件\噩盡島\噩盡島-漫劇\ch02"

REPLACEMENTS = [
    # 狄純 -> 瑪蓮
    ("狄純", "瑪蓮"),
    ("Di Chun", "Malien"),
    ("di-chun", "malien"),
    ("DiChun", "Malien"),
    ("Di chun", "Malien"),
    # 張如鴻 -> 奇雅
    ("張如鴻", "奇雅"),
    ("Zhang Ruhong", "Qiya"),
    ("zhang-ruhong", "qiya"),
    ("ZhangRuhong", "Qiya"),
    ("Zhang ruhong", "Qiya"),
]

TARGET_FILES = [
    os.path.join(CH02_DIR, "assets.md"),
    os.path.join(CH02_DIR, "script-ep03.md"),
    os.path.join(CH02_DIR, "handoff-ep03.json"),
    os.path.join(CH02_DIR, "storyboard-ep03.md"),
    os.path.join(CH02_DIR, "prompts-ep03.md"),
    os.path.join(CH02_DIR, "segments-ep03.json"),
    os.path.join(CH02_DIR, "adapt", "bible.json"),
    os.path.join(CH02_DIR, "adapt", "ch02-adaptation-plan.md"),
]

# 加上所有 layer2-EP03-*.json
layer2_dir = os.path.join(CH02_DIR, "layer2")
if os.path.exists(layer2_dir):
    for f in os.listdir(layer2_dir):
        if f.startswith("layer2-EP03-") and f.endswith(".json"):
            TARGET_FILES.append(os.path.join(layer2_dir, f))

# 加上 images/ 下的 asset_prompts
TARGET_FILES.append(os.path.join(CH02_DIR, "images", "asset_prompts.json"))
TARGET_FILES.append(os.path.join(CH02_DIR, "images", "asset_prompts.md"))

print("🚀 開始全面校正角色聖經與關聯文件（狄純->瑪蓮、張如鴻->奇雅）...")
for p in TARGET_FILES:
    if not os.path.exists(p):
        print(f"  ⚠️ 跳過不存在檔案: {os.path.basename(p)}")
        continue
    try:
        with open(p, "r", encoding="utf-8") as fp:
            orig = fp.read()
        updated = orig
        for old, new in REPLACEMENTS:
            updated = updated.replace(old, new)
        if updated != orig:
            with open(p, "w", encoding="utf-8") as fp:
                fp.write(updated)
            print(f"  ✅ [已更新] {os.path.relpath(p, CH02_DIR)}")
        else:
            print(f"  ℹ️ [無需變更] {os.path.relpath(p, CH02_DIR)}")
    except Exception as e:
        print(f"  ❌ 更新失敗 {p}: {e}")

print("🏁 實體名稱校正完畢！")
