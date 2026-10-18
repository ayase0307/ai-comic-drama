#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json
import os
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

CH02_DIR = Path(r"C:\Users\kirit\OneDrive\文件\噩盡島\噩盡島-漫劇\ch02")
IMAGES_DIR = CH02_DIR / "images"

print(f"=== 現有實體圖片清單 ({IMAGES_DIR}) ===")
existing_images = set()
if IMAGES_DIR.exists():
    for f in IMAGES_DIR.glob("*.*"):
        if f.suffix.lower() in [".png", ".jpg", ".jpeg"]:
            existing_images.add(f.name)
            print(f"  - {f.name} ({f.stat().st_size:,} bytes)")
else:
    print("  ❌ images 目錄不存在")

for ep in ["ep01", "ep02", "ep03"]:
    seg_file = CH02_DIR / f"segments-{ep}.json"
    print(f"\n=======================================================")
    print(f"📊 分析 {seg_file.name}")
    print(f"=======================================================")
    if not seg_file.exists():
        print(f"  ❌ 找不到檔案: {seg_file}")
        continue
    with open(seg_file, "r", encoding="utf-8") as fp:
        data = json.load(fp)

    segs = data.get("segments", data) if isinstance(data, dict) else data
    print(f"總分段數: {len(segs)}")

    ready_segs = []
    waiting_segs = []

    for seg in segs:
        seg_id = seg.get("segment_id")
        refs = seg.get("reference_images", [])
        
        missing_refs = []
        found_refs = []
        for ref in refs:
            p = ref.get("path", "")
            fname = Path(p).name
            # 檢查在 images/ 下是否存在
            target_path = IMAGES_DIR / fname
            # 也檢查原路徑直接是否存在
            direct_path = CH02_DIR / p
            if target_path.exists():
                found_refs.append(f"{ref.get('id')} -> images/{fname} [OK]")
            elif direct_path.exists():
                found_refs.append(f"{ref.get('id')} -> {p} [OK]")
            else:
                missing_refs.append(f"{ref.get('id')} (path: {p}, file: {fname})")

        if not missing_refs:
            ready_segs.append((seg_id, found_refs))
        else:
            waiting_segs.append((seg_id, found_refs, missing_refs))

    print(f"\n✅ 100% 具備參考圖可立即送件 ({len(ready_segs)} 段):")
    for sid, found in ready_segs:
        print(f"  - [{sid}]")
        for fr in found:
            print(f"      + {fr}")

    print(f"\n⏳ 等待補齊資產圖的分段 ({len(waiting_segs)} 段):")
    for sid, found, missing in waiting_segs:
        print(f"  - [{sid}]")
        for mr in missing:
            print(f"      ❌ 缺少: {mr}")
        for fr in found:
            print(f"      ✓ 現有: {fr}")

print(f"\n=======================================================")
print(f"🔍 直接分析 ch02/layer2/ 下的 30 個原始 Layer 2 JSON")
print(f"=======================================================")
layer2_dir = CH02_DIR / "layer2"
for ep in ["EP01", "EP02", "EP03"]:
    files = sorted(layer2_dir.glob(f"layer2-{ep}-*.json"))
    print(f"\n--- {ep} ({len(files)} 段) ---")
    ready_count = 0
    waiting_count = 0
    for f in files:
        with open(f, "r", encoding="utf-8") as fp:
            d = json.load(fp)
        sid = d.get("segment_id", f.stem)
        refs = d.get("reference_images", [])
        missing = []
        found = []
        for r in refs:
            p = r.get("path", "")
            fname = Path(p).name
            target = IMAGES_DIR / fname
            if target.exists():
                found.append(f"{r.get('id')} -> images/{fname}")
            else:
                missing.append(f"{r.get('id')} ({p})")
        if not missing:
            ready_count += 1
            print(f"  ✅ [{sid}] 齊全: {found}")
        else:
            waiting_count += 1
            print(f"  ⏳ [{sid}] 缺圖: {missing} | 現有: {found}")
    print(f"  小計 {ep}: 齊全可送件={ready_count}, 等待補圖={waiting_count}")
