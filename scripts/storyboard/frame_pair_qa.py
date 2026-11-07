# frame_pair_qa.py - fl2v 送件前「首尾幀疊圖」差異檢查（stdlib + ffmpeg，無第三方依賴）。
# 用法: python scripts/storyboard/frame_pair_qa.py first.png last.png [--grid 8x5] [--json]
#
# 為什麼要有這支（Eian 2026-11-05 文章對照）：fl2v 的首尾幀若在「不該變的地方」不一致，
# 影片裡那個東西就會慢慢變——牆的顏色不一樣→牆慢慢變色；杯子大了一點→杯子慢慢變大。
# 文章的做法是把兩張圖疊在一起放大看；這支把它變成可重跑的格點量化：
#   - 全圖平均 dE76 與每格平均 dE76（CIE76，與 color_qa.py 同一口徑）
#   - 差異最大的格子列出來
# 判讀（人做，腳本不擋關）：
#   - 高差格子應對應分鏡寫的動作（誰在動、往畫面哪邊動）；對不上的就是疊圖錯位，改圖再送。
#   - 推近（dolly in）鏡的尾幀＝首幀裁一塊放大：全圖都會有差，看格子是否呈「整體位移」而非局部突變。
import argparse
import json
import math
import subprocess
import sys

SAMPLE_W, SAMPLE_H = 160, 90


def pixels(path: str, w: int = SAMPLE_W, h: int = SAMPLE_H):
    """ffmpeg 解碼成 rgb24 像素串列（與 color_qa.py 同一套取樣口徑）。"""
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", path,
           "-vf", f"scale={w}:{h}", "-frames:v", "1",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    if not raw:
        sys.exit(f"no pixels decoded from {path}")
    return [tuple(raw[i:i + 3]) for i in range(0, len(raw), 3)]


def to_lab(p):
    def lin(c):
        c /= 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(x) for x in p)
    X = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    Y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    Z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883
    f = lambda t: t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116
    fx, fy, fz = f(X), f(Y), f(Z)
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def pair_report(a_path: str, b_path: str, cols: int, rows: int) -> dict:
    a, b = pixels(a_path), pixels(b_path)
    lut_a = {c: to_lab(c) for c in set(a)}
    lut_b = {c: to_lab(c) for c in set(b)}
    w, h = SAMPLE_W, SAMPLE_H
    cw, ch = w / cols, h / rows
    grid = [[0.0] * cols for _ in range(rows)]
    total = 0.0
    for y in range(h):
        row = min(rows - 1, int(y / ch))
        for x in range(w):
            col = min(cols - 1, int(x / cw))
            i = y * w + x
            d = math.dist(lut_a[a[i]], lut_b[b[i]])
            grid[row][col] += d
            total += d
    n_cell = (w // cols + 1) * (h // rows + 1)  # 近似每格像素數，供平均
    for r in range(rows):
        for c in range(cols):
            grid[r][c] = round(grid[r][c] / max(1, n_cell), 2)
    cells = [(grid[r][c], c + 1, r + 1) for r in range(rows) for c in range(cols)]
    top = sorted(cells, reverse=True)[:3]
    return {
        "global_mean_dE76": round(total / (w * h), 2),
        "grid_cols": cols, "grid_rows": rows,
        "grid": grid,
        "top_cells": [{"col": c, "row": r, "mean_dE76": v} for v, c, r in top],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="fl2v 首尾幀疊圖差異檢查（只量化，不擋關）")
    parser.add_argument("first", help="首幀圖")
    parser.add_argument("last", help="尾幀圖")
    parser.add_argument("--grid", default="8x5", help="格點數 COLSxROWS（預設 8x5）")
    parser.add_argument("--json", action="store_true", help="輸出 JSON（給審核頁／腳本串接）")
    args = parser.parse_args()
    try:
        cols, rows = (int(x) for x in args.grid.lower().split("x", 1))
    except ValueError:
        sys.exit(f"--grid 格式要 COLSxROWS，收到：{args.grid}")
    rep = pair_report(args.first, args.last, cols, rows)
    if args.json:
        print(json.dumps(rep, ensure_ascii=False))
        return 0
    print(f"{args.first} vs {args.last}")
    print(f"全圖平均 dE76：{rep['global_mean_dE76']}")
    print("每格平均 dE76（列＝由上到下，欄＝由左到右）：")
    for r, rowvals in enumerate(rep["grid"], 1):
        print("  " + " ".join(f"{v:6.1f}" for v in rowvals) + f"   ← 第 {r} 列")
    tops = "、".join(f"(欄{c},列{r}) {v}" for v, c, r in
                     [(t["mean_dE76"], t["col"], t["row"]) for t in rep["top_cells"]])
    print(f"差異最大：{tops}")
    print("判讀：高差格子應對應分鏡寫的動作；對不上的＝疊圖錯位（不該變的地方變了），改圖再送。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
