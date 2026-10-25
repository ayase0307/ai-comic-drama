#!/usr/bin/env python3
"""生物色彩 QA（#121）：以參考圖 HSV 中位數比對影片抽格，色相、彩度分開報。

用法：creature_color_qa.py --ref ref.png --frame f1.png [--frame f2.png ...] [--hue-tol 8] [--sat-tol 0.1]
只統計非灰、非近黑／近白像素（略過攝影棚灰底）。退出碼 1＝有超標。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "storyboard"))
import creature_lint  # noqa: E402


def _pixels(path: str):
    from PIL import Image
    img = Image.open(path).convert("RGB")
    img.thumbnail((256, 256))
    px = []
    for r, g, b in img.getdata():
        mx, mn = max(r, g, b), min(r, g, b)
        if mx < 30 or mn > 225 or (mx - mn) < 25:
            continue
        px.append((r, g, b))
    return px


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ref", required=True)
    ap.add_argument("--frame", action="append", required=True)
    ap.add_argument("--hue-tol", type=float, default=8.0)
    ap.add_argument("--sat-tol", type=float, default=0.10)
    a = ap.parse_args(argv)
    ref = creature_lint.hsv_median(_pixels(a.ref))
    rows, bad = [], False
    for f in a.frame:
        px = _pixels(f)
        if not px:
            rows.append({"frame": f, "error": "no colourful pixels"})
            bad = True
            continue
        got = creature_lint.hsv_median(px)
        cmp_ = creature_lint.compare_hsv(ref, got, hue_tol=a.hue_tol, sat_tol=a.sat_tol)
        bad = bad or not cmp_["ok"]
        rows.append({"frame": f, "hsv": got, **cmp_})
    print(json.dumps({"ref": ref, "frames": rows}, ensure_ascii=False, indent=2))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
