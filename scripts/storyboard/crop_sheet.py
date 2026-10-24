#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""h3d crop：依比例裁設定板（頭像／格位），不寫死像素。輸出預設在 <root>/tmp/crops，
不放 images/，避免階段 2 核准快照（綁 images/ hash）失效。"""
from __future__ import annotations

import argparse
import pathlib
import sys
from typing import List, Tuple

from PIL import Image


def grid_boxes(width: int, height: int, cols: int, rows: int) -> List[Tuple[int, int, int, int]]:
    return [(c * width // cols, r * height // rows, (c + 1) * width // cols, (r + 1) * height // rows)
            for r in range(rows) for c in range(cols)]


def ratio_box(width: int, height: int, ratio: Tuple[float, float, float, float]) -> Tuple[int, int, int, int]:
    x0, y0, x1, y1 = ratio
    if not (0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1):
        raise ValueError("--box 需為 0~1 的 x0,y0,x1,y1 且 x0<x1、y0<y1")
    return round(x0 * width), round(y0 * height), round(x1 * width), round(y1 * height)


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="依比例或格位裁圖（輸出在 images/ 之外）")
    ap.add_argument("--image", type=pathlib.Path, required=True)
    ap.add_argument("--root", type=pathlib.Path, default=pathlib.Path("."))
    ap.add_argument("--out-dir", type=pathlib.Path, default=None, help="預設 <root>/tmp/crops")
    ap.add_argument("--grid", help="COLSxROWS，例如 3x1 把整張切成等分格")
    ap.add_argument("--cell", help="只輸出 --grid 的第幾格（1 起算，逗號可多個）")
    ap.add_argument("--box", help="x0,y0,x1,y1（0~1 比例），例如 0.05,0.0,0.35,0.5")
    ap.add_argument("--prefix", default=None)
    args = ap.parse_args(argv)
    if bool(args.grid) == bool(args.box):
        print("需指定 --grid 或 --box 其中之一", file=sys.stderr)
        return 2
    out_dir = (args.out_dir or args.root / "tmp" / "crops").resolve()
    if "images" in out_dir.relative_to(out_dir.anchor).parts[-1:]:
        print("輸出不可放在 images/ 內（會使階段 2 快照失效）", file=sys.stderr)
        return 2
    try:
        with Image.open(args.image) as im:
            im.load()
            w, h = im.size
            if args.box:
                boxes = [ratio_box(w, h, tuple(float(v) for v in args.box.split(",")))]  # type: ignore[arg-type]
            else:
                cols, rows = (int(v) for v in args.grid.lower().split("x"))
                boxes = grid_boxes(w, h, cols, rows)
                if args.cell:
                    pick = [int(v) for v in args.cell.split(",")]
                    boxes = [boxes[i - 1] for i in pick]
            out_dir.mkdir(parents=True, exist_ok=True)
            prefix = args.prefix or args.image.stem
            for n, box in enumerate(boxes, 1):
                target = out_dir / f"{prefix}-crop{n}.png"
                im.crop(box).save(target)
                print(f"{target} {box} {box[2]-box[0]}x{box[3]-box[1]}")
    except (OSError, ValueError, IndexError) as exc:
        print(f"裁切失敗: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
