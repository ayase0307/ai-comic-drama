# -*- coding: utf-8 -*-
import os
import shutil
import sys
from PIL import Image

if sys.platform.startswith("win"):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

src_dir = r"C:\Users\kirit\OneDrive\文件\噩盡島\噩盡島-漫劇\images"
dst_dir = r"C:\Users\kirit\OneDrive\文件\噩盡島\噩盡島-漫劇\ch02\images"

# 1. 複製巨蟒三視圖
src_python = os.path.join(src_dir, "creature-YellowPython-sheet.png")
dst_python = os.path.join(dst_dir, "creature-YellowPython.png")
if os.path.exists(dst_python):
    bak = dst_python + ".bak-scene"
    if os.path.exists(bak):
        os.remove(bak)
    shutil.copyfile(dst_python, bak)
shutil.copyfile(src_python, dst_python)
im1 = Image.open(dst_python)
print(f"[OK] 已覆蓋 creature-YellowPython.png 為純灰底三視圖，大小: {os.path.getsize(dst_python):,} bytes, 解析度: {im1.size}")

# 2. 複製沈洛年便服圖
src_casual = os.path.join(src_dir, "char-ShenLuonian-casual.png")
dst_casual = os.path.join(dst_dir, "char-ShenLuonian-casual.png")
if os.path.exists(src_casual):
    shutil.copyfile(src_casual, dst_casual)
    im2 = Image.open(dst_casual)
    print(f"[OK] 已複製 char-ShenLuonian-casual.png，大小: {os.path.getsize(dst_casual):,} bytes, 解析度: {im2.size}")
else:
    print(f"[WARN] 找不到 {src_casual}")
