#!/usr/bin/env python3
"""建立 AI 漫劇專案骨架。

用法：
    python init_project.py <專案目錄> [--title 專案名] [--episodes 集數]

已存在的檔案不會被覆蓋。
"""
from __future__ import annotations

import argparse
from pathlib import Path

PROJECT_TEMPLATE = """# {title}

## 設定
- 集數 / 每集時長：{episodes} 集 / 90 秒
- 畫風：
- 畫面比例：9:16
- 語言：繁體中文
- 聲音形式：旁白解說
- 交付深度：到分鏡圖

## 一句話賣點
<主角 + 目標 + 阻礙>

## 分集規劃
| 集 | 標題 | 集內主事件 | 結尾鉤子 |
|---|---|---|---|
{episode_rows}
"""

ASSETS_TEMPLATE = """# 資產聖經

> 固定描述片段要具體到可畫，且每次生成**逐字複製**，不改寫。

## 角色

### <角色名>（主角）
- **固定描述片段**：`<性別年齡>, <髮型髮色>, <瞳色>, <體型>, <標誌服裝>, <標誌配件>, <氣質關鍵詞>`
- **外貌要點**：
- **服裝**：
- **性格與口頭禪**：
- **人物弧線**：
- **參考圖**：`images/char-<角色名>.png`

## 場景

### <場景名>
- **固定描述片段**：`<空間類型>, <環境特徵>, <主要色調>, <光源>, <時間與天氣>`
- **出現集數**：

## 道具

### <道具名>
- **固定描述片段**：`<材質>, <尺寸感>, <顏色>, <標誌細節>`
- **敘事功能**：
"""

STORYBOARD_TEMPLATE = """{{
  "project": "{title}",
  "episode": {episode},
  "title": "第 {episode} 集標題",
  "aspect_ratio": "9:16",
  "style_lock": "anime screencap, cel shading, clean lineart, flat colors, vibrant",
  "shots": []
}}
"""

SCRIPT_TEMPLATE = """# 第 {episode} 集《<標題>》

## SC01 <地點>・<時間>・<內/外>
**人物**：
**目的**：
**內容**：

**本場結尾情緒**：
"""

NARRATION_TEMPLATE = """# 第 {episode} 集 旁白與字幕稿

| shot_id | 旁白 / 字幕 |
|---|---|
"""


def main() -> None:
    ap = argparse.ArgumentParser(description="建立 AI 漫劇專案骨架")
    ap.add_argument("project_dir", help="專案目錄（不存在會建立）")
    ap.add_argument("--title", default="未命名漫劇", help="專案名稱")
    ap.add_argument("--episodes", type=int, default=1, help="集數（預設 1）")
    args = ap.parse_args()

    root = Path(args.project_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    (root / "images").mkdir(exist_ok=True)
    (root / "videos").mkdir(exist_ok=True)

    rows = "\n".join(f"| {i} | | | |" for i in range(1, args.episodes + 1))
    files: dict[str, str] = {
        "project.md": PROJECT_TEMPLATE.format(
            title=args.title, episodes=args.episodes, episode_rows=rows
        ),
        "assets.md": ASSETS_TEMPLATE,
    }
    for ep in range(1, args.episodes + 1):
        tag = f"ep{ep:02d}"
        files[f"script-{tag}.md"] = SCRIPT_TEMPLATE.format(episode=ep)
        files[f"storyboard-{tag}.json"] = STORYBOARD_TEMPLATE.format(
            title=args.title, episode=ep
        )
        files[f"narration-{tag}.md"] = NARRATION_TEMPLATE.format(episode=ep)

    created, skipped = [], []
    for name, content in files.items():
        p = root / name
        if p.exists():
            skipped.append(name)
            continue
        p.write_text(content, encoding="utf-8")
        created.append(name)

    print(f"專案目錄：{root}")
    for n in created:
        print(f"  建立            {n}")
    for n in skipped:
        print(f"  已存在，略過    {n}")
    print()
    print("下一步：編輯 project.md 完成定調，再填 assets.md 的資產聖經。")


if __name__ == "__main__":
    main()
