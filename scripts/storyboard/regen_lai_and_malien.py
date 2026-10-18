# -*- coding: utf-8 -*-
"""
regen_lai_and_malien.py — 依原著精確重新生成賴一心與瑪蓮
嚴格遵守原著設定、UE5 寫實東亞 CG、16:9 純中性灰底四格轉面圖、Anti-Pixar 鐵律
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

TARGET_DIR = r"C:\Users\kirit\OneDrive\文件\噩盡島\噩盡島-漫劇\ch02\images"

PROMPT_LAI = (
    "Photorealistic-stylized East Asian 3D CG character concept sheet (Unreal Engine 5 / Korean-Chinese next-gen CG cinema aesthetic, "
    "realistic East Asian facial bone structure and eye proportions, delicate subsurface-scattering pore skin texture; "
    "STRICTLY NO Pixar style, NO Disney cartoon style, NO Western cartoon proportions, NO exaggerated oversized eyes, NO freckles). "
    "Character turn-around model sheet showing 4 views horizontally aligned against a seamless flat neutral medium-grey background: "
    "from left to right, extreme close-up of face, full-body front view, full-body 90-degree profile side view, full-body back view. "
    "Subject: Lai Yixin, a 17-year-old Taiwanese high-school boy with a round handsome boyish baby-face (charming youthful facial features), "
    "bright enthusiastic dark eyes, a warm sunny confident smile, neat short spiky black hair, tall sturdy muscular athletic build (broad shoulders, strong frame), "
    "wearing a clean white private-high-school short-sleeved uniform shirt with rolled cuffs, dark navy school trousers, clean black casual sneakers, "
    "a sleek long white leather weapon backpack strapped diagonally across his back (clearly visible in side and back views), "
    "holding in his right hand a sleek slender silver metal spear with segmented interlocking joints convertible into a three-section staff"
)

PROMPT_MALIEN = (
    "Photorealistic-stylized East Asian 3D CG character concept sheet (Unreal Engine 5 / Korean-Chinese next-gen CG cinema aesthetic, "
    "realistic East Asian facial bone structure and eye proportions, delicate subsurface-scattering pore skin texture; "
    "STRICTLY NO Pixar style, NO Disney cartoon style, NO Western cartoon proportions, NO exaggerated oversized eyes, NO freckles). "
    "Character turn-around model sheet showing 4 views horizontally aligned against a seamless flat neutral medium-grey background: "
    "from left to right, extreme close-up of face, full-body front view, full-body 90-degree profile side view, full-body back view. "
    "Subject: Malien (Brown-haired Slayer), a 20-year-old Taiwanese woman with realistic East Asian features, fair smooth skin, "
    "dyed golden-brown honey-brown layered short hair cut neatly just past her ears, sharp confident clear East Asian eyes, "
    "a cheerful spirited confident smile with closed lips, athletic toned build, "
    "wearing a slightly oversized beige crewneck short-sleeve T-shirt, fitted black athletic cycling shorts just above her knees, high-top sneakers, "
    "carrying a huge oversized heavy-duty canvas travel backpack on her back (very prominent in side and back views), "
    "holding in her right hand a heavy cyan-tinged steel Chinese broad-backed saber / machete with a single-edged curved blade and intricate engraved dragon patterns along its thick spine (STRICTLY single-edged Chinese saber, NOT a double-edged Western broadsword)"
)

TASKS = [
    {
        "name": "賴一心 (Lai Yixin)",
        "file": "char-LaiYixin.png",
        "aliases": ["char-lai-yixin.png", "char-SpearYouth.png", "lai-yixin.png"],
        "prompt": PROMPT_LAI,
    },
    {
        "name": "瑪蓮 (Malien)",
        "file": "char-Malien.png",
        "aliases": ["char-BrownHairSlayer.png", "char-brown-hair-slayer.png", "brown-hair-slayer.png", "malien.png"],
        "prompt": PROMPT_MALIEN,
    },
]

def generate_one(task):
    fname = task["file"]
    dest = os.path.join(TARGET_DIR, fname)
    prompt = task["prompt"]

    print("\n" + "=" * 80)
    print(f"🎨 [開始生成] {task['name']} -> {fname}")
    print(f"   Prompt 長度: {len(prompt)} 字元")
    print("=" * 80)

    # 備份舊檔
    if os.path.exists(dest):
        bak = dest + ".bak-old"
        if os.path.exists(bak):
            os.remove(bak)
        os.rename(dest, bak)
        print(f"   📦 已備份現有檔案至: {os.path.basename(bak)}")

    instruction = (
        f"Generate a 16:9 high-resolution image using the built-in image generation tool following this prompt:\n\n"
        f"\"{prompt}\"\n\n"
        f"Important: Save the generated image file strictly as '{fname}' in the current working directory ({TARGET_DIR}). "
        f"Verify the file exists and is not empty."
    )

    cmd = [
        "codex", "exec",
        "-m", "gpt-5.6-sol",
        "--dangerously-bypass-approvals-and-sandbox",
        "-C", TARGET_DIR,
        instruction
    ]

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
        print(f"❌ [超時] {fname} 生成超過 180s 終止！")
        return False

    elapsed = time.time() - t0
    print(f"   Codex 進程返回碼: {proc.returncode} (耗時 {elapsed:.1f}s)")

    if os.path.exists(dest):
        sz = os.path.getsize(dest)
        if sz > 20480:
            with Image.open(dest) as im:
                print(f"✅ [成功生成] {fname}: {sz:,} bytes | 解析度: {im.size} | 模式: {im.mode}")
            # 同步別名
            for alias in task.get("aliases", []):
                ap = os.path.join(TARGET_DIR, alias)
                with open(dest, "rb") as src, open(ap, "wb") as dst:
                    dst.write(src.read())
                print(f"   🔗 已同步建立別名: {alias}")
            return True
        else:
            print(f"⚠️ [檔案過小] {fname} 僅 {sz} bytes")
            return False
    else:
        print(f"❌ [未找到檔案] {fname}")
        if stdout:
            print("stdout:\n", stdout[-500:])
        if stderr:
            print("stderr:\n", stderr[-300:])
        return False

def main():
    print("🚀 啟動 Codex CLI 生成賴一心（娃娃臉+白背包+三節棍）與瑪蓮（黃褐短髮+超大背包+中式單刃厚背刀）...")
    success = 0
    for t in TASKS:
        ok = generate_one(t)
        if ok:
            success += 1
        time.sleep(3)
    print(f"\n🏁 完成狀態: 成功 {success} / {len(TASKS)}")

if __name__ == "__main__":
    main()
