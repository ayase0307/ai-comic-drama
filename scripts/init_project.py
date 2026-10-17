#!/usr/bin/env python3
"""建立 AI 漫劇專案骨架（新流程：改編 → 資產 → 劇本 → 分鏡）。

用法：
    python init_project.py <專案目錄> [--title 專案名] [--episodes 集數]

目錄結構：
    project.md、assets.md
    source/            原著素材
    adapt/             改編 stage 產物
    script-epNN.md     劇本（只寫戲，不寫鏡頭術語）
    handoff-epNN.json  改編交接 JSON 的最小 stub（符合 handoff.schema.json 結構）
    narration-epNN.md  旁白與字幕稿
    layer2/            分鏡 Layer 2 骨架輸出目錄
    images/ videos/

已存在的檔案與目錄不會被覆蓋，可重複執行。
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

PROJECT_TEMPLATE = """# {title}

## 設定
- 集數 / 每集時長：{episodes} 集 / 90 秒
- 畫風：
- aspect_ratio：9:16
- 語言：繁體中文
- 聲音形式：旁白解說
- 交付深度：到分鏡圖
- genre_mode：<xuanhuan_revenge | romance_emotional | mystery_thriller | comedy_slice_of_life | wuxia_action | healing_literary>
- target_medium：<motion_comic | ai_animation | live_action_short_drama>
- rights_status：<owned_original | licensed_adaptation | public_domain | personal_study_only | unconfirmed>
- source_type：<小說／網文／故事梗概／劇本>
- source_rights：<原著版權來源與授權說明，未確認就寫 unconfirmed 與待辦>
- 風格錨點 ID：STYLE-<slug>（對應 assets.md 的 style_anchor 行）

## 一句話賣點
<主角 + 目標 + 阻礙>

## 分集規劃
| 集 | 標題 | 集內主事件 | 結尾鉤子 |
|---|---|---|---|
{episode_rows}
"""

ASSETS_TEMPLATE = """# 資產聖經

> 固定描述片段要具體到可畫，且每次生成**逐字複製**，不改寫。
> ID 規則：角色 `C-<slug>`、服裝 `W-<slug>-NN`、場景 `S-<slug>`、道具 `P-<slug>`、聲音 `V-<slug>`。slug 用小寫英數與連字號。
> 固定片段逐字複用；有參考圖時外觀只在首次出現寫一次，見 references/consistency.md §0

## 風格錨點
- **style_anchor**：`<全片共用風格，例：3D donghua, cel-shaded, soft rim light>`
- **style_negative**：`<不要出現的特徵>`
- **lighting_lock_line**：`<全片光線鎖，一句話>`

## 色票
| 部位 | 色名＋HEX | 用途 |
|---|---|---|
| 膚 | <色名> #RRGGBB | |
| 髮 | <色名> #RRGGBB | |
| 主服 | <色名> #RRGGBB | |
| 輔服 | <色名> #RRGGBB | |
| 點綴 | <色名> #RRGGBB | |

## 表情集（6）
每位主要角色各一張，同一張臉：中性｜微笑｜怒｜哭｜驚｜冷峻（規範見 references/consistency.md）

## 角色

### C-<slug>　<角色名>（主角）
- **固定描述片段**：`<性別年齡>, <髮型髮色>, <瞳色>, <體型>, <氣質關鍵詞>`
- **服裝**：`W-<slug>-01`　<描述>　固定片段：`<服裝描述，逐字複製>`
- **表情集**：見下方「表情集（6）」
- **設定圖**：`images/C-<slug>_W01_sheet_v1.png`
- **聲音**：`V-<slug>`
- **版本**：`v1`
- **性格與口頭禪**：
- **人物弧線**：

## 場景

### S-<slug>　<場景名>
- **固定描述片段**：`<空間類型>, <環境特徵>, <主要色調>, <光源>, <時間與天氣>`
- **母版圖**：`images/scene-<slug>-master.png`
- **日景變體**：`images/scene-<slug>-day.png`
- **夜景變體**：`images/scene-<slug>-night.png`
- **出現集數**：

## 道具

### P-<slug>　<道具名>
- **固定描述片段**：`<材質>, <顏色>, <標誌細節>`
- **尺寸參照**：`<例：與手掌等長，約 30 cm>`
- **狀態表**：

| 狀態 | 描述 | 出現集／場 |
|---|---|---|
| 完好 | | |
| 損壞 | | |

- **敘事功能**：
"""

SCRIPT_TEMPLATE = """第{episode:02d}集｜<標題>

1-1 <場景名> 夜/內
人物：<角色名>、<角色名>
△<動作，一行一個動作>
<角色名>（<括注，可省略>）：<對白>
<角色名>：<對白>
"""

NARRATION_TEMPLATE = """# 第 {episode} 集 旁白與字幕稿

| shot_id | 旁白 / 字幕 |
|---|---|
"""

ADAPT_README = "改編 stage 的產物（handoff JSON 與改編紀錄）放這裡。\n"

SCRIPTS_DIR = Path(__file__).resolve().parent  # 技能的 scripts 目錄（絕對路徑，指令可在任何位置執行）


def flow_hint(root: Path) -> str:
    """下一步指引；指令中的專案檔案與腳本都用絕對路徑。"""
    storyboard = SCRIPTS_DIR / "storyboard"
    handoff = root / "handoff-ep01.json"
    layer2 = root / "layer2"
    return f"""下一步（新流程：改編 → 資產 → 劇本 → 分鏡）：
  1. 原稿是小說：讀 references/adapt/novel-to-manju.md，把原著放進 source/，完成故事地圖、保留分級、A/B/C 方案選定與分集表（寫入 adapt/ 與 project.md），不得直接把小說當劇本
  2. 資產與設定圖：填 assets.md（風格錨點、色盤、角色／場景／道具），設定圖流程見 references/consistency.md
  3. 劇本與 handoff：寫 script-epNN.md（只寫戲，不寫鏡頭術語）並產出 handoff-epNN.json；跑 scripts/adapt 驗證
  4. 分鏡骨架：
     python "{storyboard / 'handoff_to_skeleton.py'}" "{handoff}" --out-dir "{layer2}"
     → 單段場景的檔名沒有字尾，例如 layer2-EP01-S01.json；分段場景為 layer2-EP01-S01-a.json、-b…（單鏡超過 15 秒的對白自動切鏡）
  5. 導演精修 layer2/ 內所有 TODO 後驗證（萬用字元 bash 會展開；PowerShell 請改成逐一列出檔名）：
     python "{storyboard / 'validate_storyboard.py'}" --handoff "{handoff}" --file "{layer2}"/layer2-EP01-*.json
     同一場的 -a、-b… 段落要一起給；EP02 起照樣改集號（layer2/layer2-EP02-*.json、handoff-ep02.json）"""


def slugify_project(name: str) -> str:
    """把資料夾名轉成 handoff 的 project_id（kebab-case）。"""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "project"


def handoff_stub(project_id: str, episode: int) -> dict:
    """最小結構 stub：必要欄位齊全、enum 取合法值，但內容皆為待填。"""
    tag = f"EP{episode:02d}"
    scene = {
        "project_id": project_id,
        "episode_id": tag,
        "scene_id": f"{tag}-S01",
        "source_refs": [],
        "adaptation_mode": "balanced",
        "setting": {"location": "TODO", "time": "unknown", "interior": True},
        "characters": [],
        "scene_goal": "TODO",
        "dramatic_turn": "TODO",
        "dialogue": [],
        "props": [],
        "continuity_initial": {},
        "continuity_final": {},
        "estimated_duration_seconds": {"min": 10, "max": 20},
        "adaptation_changes": [],
        "storyboard_handoff": {
            "required_visual_beats": [],
            "required_audio_beats": [],
            "must_preserve": [],
        },
    }
    return {
        "project_id": project_id,
        "rights_status": "unconfirmed",
        "adaptation_mode": "balanced",
        "genre_mode": "healing_literary",
        "aspect_ratio": "9:16",
        "target_medium": "ai_animation",
        "episodes": [{
            "episode_id": tag,
            "title": "TODO",
            "target_duration_seconds": 90,
            "episode_goal": "TODO",
            "act_out_type": "jeopardy_cliffhanger",
            "scenes": [scene],
        }],
    }


def build_files(title: str, episodes: int, project_id: str) -> dict[str, str]:
    rows = "\n".join(f"| {i} | | | |" for i in range(1, episodes + 1))
    files: dict[str, str] = {
        "project.md": PROJECT_TEMPLATE.format(title=title, episodes=episodes, episode_rows=rows),
        "assets.md": ASSETS_TEMPLATE,
        "adapt/README.md": ADAPT_README,
    }
    for ep in range(1, episodes + 1):
        tag = f"ep{ep:02d}"
        files[f"script-{tag}.md"] = SCRIPT_TEMPLATE.format(episode=ep)
        files[f"handoff-{tag}.json"] = json.dumps(
            handoff_stub(project_id, ep), ensure_ascii=False, indent=2
        ) + "\n"
        files[f"narration-{tag}.md"] = NARRATION_TEMPLATE.format(episode=ep)
    return files


DIRS = ["source", "adapt", "layer2", "images", "videos"]


def main() -> None:
    ap = argparse.ArgumentParser(description="建立 AI 漫劇專案骨架")
    ap.add_argument("project_dir", help="專案目錄（不存在會建立）")
    ap.add_argument("--title", default="未命名漫劇", help="專案名稱")
    ap.add_argument("--episodes", type=int, default=1, help="集數（預設 1）")
    args = ap.parse_args()

    root = Path(args.project_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    for d in DIRS:
        (root / d).mkdir(exist_ok=True)

    files = build_files(args.title, args.episodes, slugify_project(root.name))
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
    print(flow_hint(root))


if __name__ == "__main__":
    main()
