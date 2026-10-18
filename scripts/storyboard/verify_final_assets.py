# -*- coding: utf-8 -*-
import json
import os
import sys
import glob
from PIL import Image

if sys.platform.startswith("win"):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ch02_dir = r"C:\Users\kirit\OneDrive\文件\噩盡島\噩盡島-漫劇\ch02"
img_dir = os.path.join(ch02_dir, "images")

seg_files = glob.glob(os.path.join(ch02_dir, "segments-ep*.json"))

referenced_paths = set()
for sfile in sorted(seg_files):
    with open(sfile, "r", encoding="utf-8") as f:
        data = json.load(f)
    segments = data if isinstance(data, list) else data.get("segments", [])
    for seg in segments:
        for ref in seg.get("reference_images", []):
            p = ref.get("path")
            if p:
                referenced_paths.add(p)

print(f"=== segments-ep01~03.json 引用實體檢查 (共 {len(referenced_paths)} 個唯一圖檔引用) ===")
all_ok = True
for ref_path in sorted(referenced_paths):
    # ref_path 可能是 images/xxx.png 或 xxx.png
    base = os.path.basename(ref_path)
    actual_path = os.path.join(img_dir, base)
    if os.path.exists(actual_path):
        sz = os.path.getsize(actual_path)
        im = Image.open(actual_path)
        print(f"PASS | [{ref_path:35}] -> {base:30} | {sz:>10} bytes ({sz/1024/1024:.2f} MB) | {im.size} | {im.mode}")
    else:
        print(f"FAIL | [{ref_path:35}] -> 實體檔案缺失: {actual_path}")
        all_ok = False

print("\n=== 本次 7 張核心設定圖產物規格表 ===")
target_7 = [
    ("葉瑋珊 (四格轉面圖)", "char-YeWeishan.png"),
    ("快餐店 (夜景空景底圖)", "scene-fast-food.png"),
    ("食人巨鼠 (純灰底三視圖)", "creature-giant-rat.png"),
    ("板橋車站大廳 (夜間空景底圖)", "scene-banqiao-station.png"),
    ("果凍妖史萊姆 (純灰底三視圖)", "creature-jelly-slime.png"),
    ("褐髮持刀女 (四格轉面圖)", "char-BrownHairSlayer.png"),
    ("黑髮道術女 (四格轉面圖)", "char-BlackHairDaoist.png"),
]
for desc, fname in target_7:
    p = os.path.join(img_dir, fname)
    if os.path.exists(p):
        sz = os.path.getsize(p)
        im = Image.open(p)
        print(f"  * {desc:22} : {fname:28} | {sz:>10} bytes ({sz/1024/1024:.2f} MB) | {im.size} | {im.mode}")
    else:
        print(f"  * {desc:22} : {fname:28} | ❌ 未找到！")
        all_ok = False

print(f"\n==========================================")
print(f"全項目驗證結論: {'全部 100% PASS！零缺失！' if all_ok else '存在未通過項目！'}")
print(f"==========================================")
