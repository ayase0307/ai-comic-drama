# -*- coding: utf-8 -*-
"""
regen_dichun.py — 重新生成狄純（褐髮持刀女），徹底杜絕皮克斯/迪士尼美式大眼卡通漂移
"""
import os
import subprocess
import sys
import time
from PIL import Image

if sys.platform.startswith("win"):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

prompt = (
    "Photorealistic-stylized East Asian 3D CG character concept sheet (Unreal Engine 5 / Korean-Chinese next-gen CG cinema aesthetic, "
    "realistic East Asian facial bone structure and eye proportions, delicate subsurface-scattering pore skin texture; "
    "STRICTLY NO Pixar style, NO Disney cartoon style, NO Western cartoon proportions, NO exaggerated oversized eyes, NO freckles). "
    "Character turn-around model sheet showing 4 views horizontally aligned against a seamless flat neutral medium-grey background: "
    "from left to right, extreme close-up of face showing fine East Asian eyes and smooth skin, full-body front view, full-body 90-degree profile side view, full-body back view. "
    "Subject: Di Chun (Brown-haired Slayer), a 20-year-old Taiwanese woman with realistic East Asian features, fair smooth skin, "
    "layered dark chestnut-brown short hair just past her ears, sharp confident East Asian eyes, a composed confident slight smile with closed lips, "
    "athletic slender build, wearing a loose beige crewneck short-sleeve top, knee-length black fitted shorts, high-top sneakers, "
    "holding a heavy carved cyan-steel broadsword at her side"
)

target_dir = r"C:\Users\kirit\OneDrive\文件\噩盡島\噩盡島-漫劇\ch02\images"
target_file = os.path.join(target_dir, "char-BrownHairSlayer.png")

# 備份舊圖
old_bak = target_file + ".bak-pixar"
if os.path.exists(target_file):
    if os.path.exists(old_bak):
        os.remove(old_bak)
    os.rename(target_file, old_bak)
    print("📦 已備份舊圖至:", old_bak)

instruction = (
    f"Generate a 16:9 high-resolution image using the built-in image generation tool following this prompt:\n\n"
    f"\"{prompt}\"\n\n"
    f"Important: Save the generated image file strictly as 'char-BrownHairSlayer.png' in the current working directory ({target_dir}). "
    f"Verify the file exists and is not empty."
)

cmd = [
    "codex", "exec",
    "-m", "gpt-5.6-sol",
    "--dangerously-bypass-approvals-and-sandbox",
    "-C", target_dir,
    instruction
]

print("🎨 [開始呼叫 Codex CLI 重新生成狄純 (Anti-Pixar 寫實東亞 CG)]...")
t0 = time.time()
proc = subprocess.Popen(
    cmd,
    stdin=subprocess.DEVNULL,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    encoding="utf-8",
    errors="replace"
)
try:
    stdout, stderr = proc.communicate(timeout=180)
except subprocess.TimeoutExpired:
    proc.kill()
    stdout, stderr = proc.communicate()
    print("❌ 超時終止！")
    sys.exit(1)

elapsed = time.time() - t0
print(f"進程結束，耗時: {elapsed:.1f}s, 返回碼: {proc.returncode}")

if os.path.exists(target_file):
    size = os.path.getsize(target_file)
    im = Image.open(target_file)
    print(f"✅ [成功產出] 大小: {size:,} bytes | 解析度: {im.size} | 模式: {im.mode}")
    # 同步別名
    for alias in ["char-brown-hair-slayer.png", "brown-hair-slayer.png"]:
        ap = os.path.join(target_dir, alias)
        with open(target_file, "rb") as src, open(ap, "wb") as dst:
            dst.write(src.read())
        print(f"  🔗 同步別名: {alias}")
else:
    print("❌ 產出失敗！")
    if stdout:
        print("stdout:\n", stdout[-600:])
    if stderr:
        print("stderr:\n", stderr[-400:])
    sys.exit(1)
