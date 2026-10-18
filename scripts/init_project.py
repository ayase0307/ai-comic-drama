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
- 台詞政策：<① 100%逐字保留／② 只留重點句／③ 全改影視對白／④ 無台詞純旁白>
- 原文體量反推試算：<原著對白字數 ÷ 4 × 1.6 = 預估總秒數，例：300 字 ÷ 4 × 1.6 = 120 秒（約 1.3 集）>

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
    """下一步指引：八階段嚴格斷點與 HTML 審核流程；指令與路徑均使用絕對路徑。"""
    storyboard = SCRIPTS_DIR / "storyboard"
    adapt = SCRIPTS_DIR / "adapt"
    build_review = SCRIPTS_DIR / "build_stage_review.py"
    handoff = root / "handoff-ep01.json"
    layer2 = root / "layer2"

    return f"""下一步（八階段流程與 HTML 斷點審核機制）：
  【重要鐵律】每完成一個階段，必須執行 python "{build_review}" 產出該階段 HTML 審核頁（位於 review/）供確認，取得使用者明確核准後才可推進至下一階段！
  
  階段 0 定調：
    - 填寫 project.md，確定台詞政策（4選1）與原文秒數反推門禁。
    - 生成審核頁：python "{build_review}" --stage 0
  
  階段 1 改編（角色設定 v4 門禁）：
    - 依原著改寫 adapt/character-bible.md（遵循十一大章節，外貌/武器/能力均附 Lxxx 行號依據，跨章節查證真名嚴禁英文假名）。
    - 跑確定性驗證：python "{adapt / 'validate_character_bible.py'}" --bible adapt/character-bible.md --json adapt/bible.json
    - 生成審核頁：python "{build_review}" --stage 1
  
  階段 2 資產與設定圖：
    - 詢問推薦生圖工具（推薦 Codex CLI），出齊角色設定板、場景母版圖與生物純底三視圖。
    - 生成審核頁（左側角色表格＋右側產出圖片並排對照）：python "{build_review}" --stage 2
    - 【斷點】開啟 review/stage-2-assets.html 供審核，確認畫風與臉型完全一致後才推進！
  
  階段 3 漫劇劇本：
    - 撰寫劇本（只寫戲，不寫鏡頭術語）並產出 handoff-ep01.json。
    - 執行驗證：python "{adapt / 'check_continuity.py'}" adapt/bible.json handoff-ep01.json
    - 生成審核頁：python "{build_review}" --stage 3
  
  階段 4 導演分鏡與九宮格構圖：
    - 生成分鏡骨架：python "{storyboard / 'handoff_to_skeleton.py'}" "{handoff}" --out-dir "{layer2}"
    - 精修分鏡並執行 validate_storyboard.py 驗證（防範罐頭詞與多主體穿模）。
    - 產出鉛筆手繪九宮格草圖：python "{storyboard / 'qwen_storyboard_grid.py'}"
    - 生成審核頁：python "{build_review}" --stage 4
    - 【斷點】開啟 review/stage-4-storyboard.html 審核構圖走位與滅點，確認無誤後才允許編譯！
  
  階段 5 提示詞包：
    - 編譯 H3 六段式 Prompt：python "{storyboard / 'compile_layer2_to_h3.py'}" --layer2 "{layer2}" --bible adapt/bible.json --check
  
  階段 6 生成：
    - 送件至 FreeVideo：python "{storyboard / 'submit_h3_segments.py'}" --segments segments-ep01.json --dry-run
    - 生成審核頁：python "{build_review}" --stage 6
  
  階段 7 組裝交付：
    - 語音合成、字幕燒錄與最終成片：python "{storyboard / 'assemble_episode.py'}" --episode EP01
    - 生成最終驗收頁：python "{build_review}" --stage 7"""


def slugify_project(name: str) -> str:
    """把資料夾名轉成 handoff 的 project_id（kebab-case）。"""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "project"


def source_stub(title: str) -> dict:
    """提供符合 compare_adaptation.py 檢驗標準的初始原著分析骨架。"""
    return {
        "work_title": title,
        "segment_id": "seg-01",
        "genre_mode": "healing_literary",
        "is_incomplete": False,
        "known_contradictions": [],
        "must_keep": ["U01"],
        "story_units": [
            {
                "unit_id": "U01",
                "summary": "開場核心原著事件",
                "expected_grade": "MUST_KEEP",
            }
        ],
        "foreshadowing": [],
    }


def bible_stub(project_id: str) -> dict:
    """提供符合 check_continuity.py 與 compare_adaptation.py 檢驗標準的初始世界觀與角色聖經骨架。"""
    return {
        "project_id": project_id,
        "style_mode": "healing_literary",
        "irreversible_states": [
            "destroyed",
            "burned",
            "dead",
        ],
        "characters": [
            {
                "character_id": "C-protagonist",
                "canonical_name": "<角色名>",
                "aliases": ["<主角別名>"],
                "role": "star",
            }
        ],
        "props": [
            {
                "prop_id": "P-sample",
                "name": "<道具名>",
                "initial_state": "intact",
                "description": "<道具描述與狀態>",
            }
        ],
        "locations": [
            {
                "location_id": "S-sample",
                "name": "<場景名>",
                "description": "<空間類型、環境特徵與光影>",
            }
        ],
    }


def handoff_stub(project_id: str, episode: int) -> dict:
    """最小結構 stub：必要欄位齊全、enum 取合法值，但內容皆為待填。"""
    tag = f"EP{episode:02d}"
    scene = {
        "project_id": project_id,
        "episode_id": tag,
        "scene_id": f"{tag}-S01",
        "source_refs": ["U01"],
        "adaptation_mode": "balanced",
        "setting": {"location": "<場景名>", "time": "unknown", "interior": True},
        "characters": ["C-protagonist"],
        "scene_goal": "TODO",
        "dramatic_turn": "TODO",
        "dialogue": [],
        "props": [],
        "continuity_initial": {},
        "continuity_final": {},
        "estimated_duration_seconds": {"min": 10, "max": 20},
        "adaptation_changes": [
            {
                "type": "must_keep",
                "description": "保留核心開場事件",
                "source_ref": "U01",
                "is_adaptation_addition": False,
            }
        ],
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


def initial_project_state(title: str, project_id: str) -> dict:
    """初始化 8 個階段之狀態檔，供 build_stage_review.py 驅動斷點審核。"""
    stage_titles = {
        0: "階段 0：專案定調與門禁",
        1: "階段 1：改編與角色設定 v4",
        2: "階段 2：資產與設定圖審核",
        3: "階段 3：漫劇劇本與交接",
        4: "階段 4：分鏡與鉛筆九宮格構圖",
        5: "階段 5：H3 六段式提示詞包",
        6: "階段 6：影片片段生成審查",
        7: "階段 7：配音字幕與成片驗收",
    }
    stage_files = {
        0: "stage-0-pitch.html",
        1: "stage-1-adapt.html",
        2: "stage-2-assets.html",
        3: "stage-3-script.html",
        4: "stage-4-storyboard.html",
        5: "stage-5-prompts.html",
        6: "stage-6-generation.html",
        7: "stage-7-assembly.html",
    }
    return {
        "project_id": project_id,
        "title": title,
        "current_stage": 0,
        "stages": {
            f"stage-{i}": {
                "id": f"stage-{i}",
                "title": stage_titles.get(i, f"階段 {i}"),
                "status": "pending",
                "review_html": f"review/{stage_files.get(i, f'stage-{i}.html')}",
                "notes": "尚未執行"
            }
            for i in range(8)
        }
    }


def load_character_bible_template(title: str) -> str:
    """讀取 character-bible-v4.md 模板並填入專案名。"""
    tpl_path = SCRIPTS_DIR.parent / "references" / "adapt" / "templates" / "character-bible-v4.md"
    if tpl_path.exists():
        content = tpl_path.read_text(encoding="utf-8")
        return content.replace("{{work_title}}", title).replace("{{source_path}}", "source/input.md")
    return f"# 《{title}》完整角色設定文件 v4.0\n\n## 一、角色總覽\n\n待填寫（遵循角色設定 v4 十一大章節規範）\n"


def build_files(title: str, episodes: int, project_id: str) -> dict[str, str]:
    rows = "\n".join(f"| {i} | | | |" for i in range(1, episodes + 1))
    files: dict[str, str] = {
        "project.md": PROJECT_TEMPLATE.format(title=title, episodes=episodes, episode_rows=rows),
        "assets.md": ASSETS_TEMPLATE,
        "adapt/README.md": ADAPT_README,
        "adapt/source.json": json.dumps(source_stub(title), ensure_ascii=False, indent=2) + "\n",
        "adapt/bible.json": json.dumps(bible_stub(project_id), ensure_ascii=False, indent=2) + "\n",
        "adapt/character-bible.md": load_character_bible_template(title),
        "review/project-state.json": json.dumps(initial_project_state(title, project_id), ensure_ascii=False, indent=2) + "\n",
    }
    for ep in range(1, episodes + 1):
        tag = f"ep{ep:02d}"
        files[f"script-{tag}.md"] = SCRIPT_TEMPLATE.format(episode=ep)
        files[f"handoff-{tag}.json"] = json.dumps(
            handoff_stub(project_id, ep), ensure_ascii=False, indent=2
        ) + "\n"
        files[f"narration-{tag}.md"] = NARRATION_TEMPLATE.format(episode=ep)
    return files


DIRS = ["source", "adapt", "layer2", "images", "videos", "review", "panels"]


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
