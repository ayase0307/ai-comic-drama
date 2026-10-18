# -*- coding: utf-8 -*-
import os
import glob
import sys
import re

if sys.platform.startswith("win"):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ch02_dir = r"C:\Users\kirit\OneDrive\文件\噩盡島\噩盡島-漫劇\ch02"

target_patterns = [
    r"assets\.md$",
    r"adapt[/\\]bible\.json$",
    r"adapt[/\\]ch02-adaptation-plan\.md$",
    r"script-ep03\.md$",
    r"handoff-ep03\.json$",
    r"storyboard-ep03\.md$",
    r"prompts-ep03\.md$",
    r"segments-ep03\.json$",
    r"layer2[/\\]layer2-EP03-.*\.json$",
]

matches_found = {}
for root, dirs, files in os.walk(ch02_dir):
    for f in files:
        full_path = os.path.join(root, f)
        rel_path = os.path.relpath(full_path, ch02_dir)
        matched = False
        for pat in target_patterns:
            if re.search(pat, rel_path):
                matched = True
                break
        if not matched:
            continue
        try:
            with open(full_path, "r", encoding="utf-8") as fp:
                content = fp.read()
            count_dichun = len(re.findall(r"狄純|Di Chun|di-chun", content, re.IGNORECASE))
            count_zhang = len(re.findall(r"張如鴻|Zhang Ruhong|zhang-ruhong", content, re.IGNORECASE))
            if count_dichun > 0 or count_zhang > 0:
                matches_found[rel_path] = (count_dichun, count_zhang)
        except Exception as e:
            pass

print("=== 誤用狄純與張如鴻檔案統計 ===")
for path, (cd, cz) in sorted(matches_found.items()):
    print(f"  {path:40} | 狄純相關: {cd:2d} 處 | 張如鴻相關: {cz:2d} 處")
