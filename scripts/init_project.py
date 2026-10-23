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
    decisions.json     使用者定案（空檔；只能用 `h3d decide` 寫入）
    layer2/            分鏡 Layer 2 骨架輸出目錄
    images/ videos/

已存在的檔案與目錄不會被覆蓋，可重複執行。
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from decisions import empty_decisions
from project_state import initial_state

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
- **style_index**：`<角色設定板風格，階段 0 與使用者確認：master 母版3D漫劇寫實厚塗｜semi-real UE5半寫實東亞｜1–11 styles.md 編號>`（export_asset_prompts.py 自動讀取）
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
- **設定板描述**：`<中文，給設定板生圖用：年齡與身份、身高 cm、頭身比、體型、瞳色、眼妝、唇色、表情氣質、髮色髮長、配飾、唯一辨識細節；服裝按 頸→胸→腰→下身→鞋 逐件寫，含材質與金屬件>`
- **背面特徵**：`<至少 3 項：後領／露背範圍／髮型背影／腰帶結構／裙擺走向>`
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
    """Generate a stage-targeted workflow using parser-verified CLI options."""
    storyboard = SCRIPTS_DIR / "storyboard"
    adapt = SCRIPTS_DIR / "adapt"
    build_review = SCRIPTS_DIR / "build_stage_review.py"
    handoff = root / "handoff-ep01.json"
    layer2 = root / "layer2"

    return f"""使用方式（從指定交付目標開始，不要求跑完整出片流程）：
  專案目錄：Set-Location -LiteralPath "{root}"
  開工規則：每次開工先跑 python "{SCRIPTS_DIR / 'h3d.py'}" next --root "{root}"，照它印的唯一一條指令做；使用者定案一律用 h3d decide 寫進 decisions.json；不准手改 review/project-state.json。
  先依使用者要求選擇要交付的階段。若使用者只要文字劇本或分鏡，可交付 draft，不必生成圖片/影片；已提供的 brief、模型、參數沿用，不重問。文字規劃、圖片生成、影片生成是不同能力層，只有目前 Agent/本機後端確實提供相應工具時才執行媒體生成。

  完整生成路徑前置（stage 0–3；逐階段審核，不可跳過未完成的前置核准）：
    - Stage 0 定調：完成 project.md；產生 review 頁：python "{build_review}" --project-dir "{root}" --stage 0
    - 使用者核准 stage 0 後記錄：python "{build_review}" --project-dir "{root}" --approve-stage 0
    - Stage 1 改編：準備 adapt/source.json、adapt/bible.json、角色設定與故事大綱（適用時）；產生 review 頁：python "{build_review}" --project-dir "{root}" --stage 1
    - 使用者核准 stage 1 後記錄：python "{build_review}" --project-dir "{root}" --approve-stage 1
    - Stage 2 資產：準備 assets.md 與所需角色/場景設定圖；產生 review 頁：python "{build_review}" --project-dir "{root}" --stage 2
    - 使用者核准 stage 2 後記錄：python "{build_review}" --project-dir "{root}" --approve-stage 2
    - Stage 3 劇本：準備 script-ep01.md、handoff-ep01.json 與 adaptation-diff.md；產生 review 頁：python "{build_review}" --project-dir "{root}" --stage 3
    - 使用者核准 stage 3 後記錄：python "{build_review}" --project-dir "{root}" --approve-stage 3
    - 只要求文字 draft 時，可在指定交付階段停止；不得代替使用者記錄核准，也不必為了完整流程生成圖片/影片。

  分鏡（stage 4）：
    - 建立/整理 Layer 2：python "{storyboard / 'handoff_to_skeleton.py'}" "{handoff}" --out-dir "{layer2}"
    - 結構檢查與企劃時間表：python "{storyboard / 'layer2_to_table.py'}" "{layer2}" --check --md storyboard-ep01.md --timeline timeline-plan-ep01.csv
    - 構圖圖可用已連線的 Qwen 工具、手繪或其他可用圖像工具；每張圖需對應 shot_id，放在該鏡 sketch_file 或 panels/panel-NN-SHOT.png，再由 review 頁檢查。Qwen 3x3 可選：python "{storyboard / 'qwen_storyboard_grid.py'}" --layer2-dir "{layer2}" --generate-all --assemble-grid
    - 產生審核頁：python "{build_review}" --project-dir "{root}" --stage 4
    - 只有使用者明確核准該 review 後才記錄：python "{build_review}" --project-dir "{root}" --approve-stage 4
    - 分鏡文字 draft 可在此交付，不需為了取得分鏡而送生成任務。

  H3 提示詞（stage 5）：
    - 僅在 stage 4 有效核准且對應 Layer 2/構圖圖未變更時編譯。Ref2VA 使用 H3 六段式；場景圖是場景/畫風參考，不自動視為首幀。
    - python "{storyboard / 'compile_layer2_to_h3.py'}" --layer2 "{layer2}" --bible "{root / 'adapt' / 'bible.json'}" --project-root "{root}" --episode EP01 --output-md "{root / 'prompts-ep01.md'}" --output-segments "{root / 'segments-ep01.json'}" --check
    - 審核及核准：python "{build_review}" --project-dir "{root}" --stage 5；使用者明確核准後執行 `--approve-stage 5`。修改輸入會使核准失效並要求重審。

  影片生成（stage 6，可選）：
    - FreeVideo 是可用 adapter，不代表目前環境一定有影片生成能力。先確認使用者要求出片且相容工具可用；FreeVideo 本機連線可用時先 dry-run：python "{storyboard / 'submit_h3_segments.py'}" --segments "{root / 'segments-ep01.json'}" --root-dir "{root}" --output-dir "{root / 'videos'}" --dry-run
    - 真正送件要求有效 stage 5 核准；`--skip-stage-gate` 只供 dry-run 除錯，不可用於實際送件。
    - QA：python "{storyboard / 'verify_video_shot.py'}" --segments "{root / 'segments-ep01.json'}" --videos-dir "{root / 'videos'}" --out-report "{root / 'videos' / 'qa-report.md'}" --out-json "{root / 'videos' / 'qa-report.json'}"
    - QA 技術通過不等於人工核准；在 stage 6 review 核准前不可當作已通過交付。

  組裝交付（stage 7，可選）：
    - 由編譯後 segments 檢查並匯出實際時間線：python "{storyboard / 'layer2_to_table.py'}" "{root / 'segments-ep01.json'}" --check --timeline "{root / 'timeline-ep01.csv'}"
    - python "{storyboard / 'assemble_episode.py'}" --segments "{root / 'segments-ep01.json'}" --videos-dir "{root / 'videos'}" --output "{root / 'final' / 'ep01_final.mp4'}" --delivery-report "{root / 'final' / 'delivery-ep01.md'}"

  審核狀態唯一存於 review/project-state.json。每階段核准綁定輸入 hash；輸入改變即需重新審核。"""


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
    state = initial_state(title, project_id)
    for i in range(8):
        state["stages"][f"stage-{i}"].update({
            "review_html": f"review/stage-{i}.html",
            "notes": "尚未執行",
        })
    return state


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
        "decisions.json": json.dumps(empty_decisions(), ensure_ascii=False, indent=2) + "\n",
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
