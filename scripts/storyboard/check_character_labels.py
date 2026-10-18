# -*- coding: utf-8 -*-
import os
import sys
import re

if sys.platform.startswith("win"):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ch02_dir = r"C:\Users\kirit\OneDrive\文件\噩盡島\噩盡島-漫劇\ch02"

for root, dirs, files in os.walk(ch02_dir):
    for f in files:
        if f.endswith((".md", ".json")):
            p = os.path.join(root, f)
            rel = os.path.relpath(p, ch02_dir)
            try:
                with open(p, "r", encoding="utf-8") as fp:
                    text = fp.read()
                found = []
                for kw in ["褐髮", "黑髮", "持刀女", "道術女", "BrownHair", "BlackHair", "狄純", "張如鴻", "瑪蓮", "奇雅"]:
                    if kw in text:
                        found.append(kw)
                if found:
                    print(f"{rel:35} -> {found}")
            except Exception:
                pass
