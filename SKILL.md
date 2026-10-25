---
name: ai-comic-drama
description: 協助製作 AI 漫劇／動態漫／短劇，從小說改編、劇本與分鏡到提示詞和可選媒體生成。內建確定性驗收（時長量子、證據分級、segment 級依賴帳本、失敗目錄）與單一入口 h3d；圖片或影片生成取決於目前 Agent 工具及已連線的相容後端，本技能不假設 Agent 內建影片生成能力，也可只交付文字劇本、分鏡或提示詞 draft。
agent_created: true
---

# AI 漫劇製作（純 Agent 版）

## 開工規則（每次都照做，沒有例外）

1. **先跑 `python scripts/h3d.py next --root <專案>`**，照它印的「唯一一條指令」做，並先讀它指定的 reference。不要自己排流程或跳步。
2. **使用者定案一律 `h3d decide <id> <值> --quote "<使用者原話>"`** 寫進 `decisions.json`（畫風、比例、台詞政策、設定圖引擎、驗收政策、剪輯方式…）。不要只寫在筆記裡，也不要替使用者決定。
3. **不准手改 `review/project-state.json`。** 狀態只能由 `build_stage_review.py` 寫；手改會被 `h3d next` 判為阻斷。階段 6 技術 QA 為 PARTIAL、使用者看過仍核准時，用 `--approve-stage 6 --override --reason "<使用者理由>"`。
4. **階段 6 逐段結論一律 `h3d verdict`** 寫進 `review/verdicts.json`（pass／warn／fail＋一句原因＋證據圖），依 `acceptance_policy` 分類。
4a. **要使用者決定的事用 `h3d inbox` 產生決策收件匣交給使用者**（只列例外）；使用者授權過的階段照 `h3d next` 跑 `h3d approve --auto`。階段 0、角色設定圖、每個角色的音色永遠要人決定（見 `references/tooling.md` §2.6）。
5. **不同時跑兩個影片 runner**；ledger 有 waiting／running 的工作時只收件（`h3d collect`），不送新件。
6. **遇到 `PARTIAL`、`duration_drift` 就停下**，照 `references/tooling.md` §4 處置並回報使用者，不要自行繞過。
7. **成片形式預設＝長篇漫劇**：把故事講清楚是第一優先，每個原著關鍵事件都要交代起因→經過→結果（含動機、時地轉換），
   不以每集秒數壓縮事件；預設不分集，整部一支連續長片。短劇／竪屏爆款短集（1–2 分鐘、強鉤子）只有使用者明確要求才用
   （`h3d decide series_format short`）。被壓縮、跳過或交代不全的事件一律在階段 1 交使用者決定（`event_coverage.py`），不自己砍。

## Overview

依使用者指定的交付範圍，完成小說改編、劇本、導演分鏡、提示詞，或使用實際可用的圖片／影片工具生成媒體。
文字規劃可獨立交付；媒體生成需要相應工具或已連線的後端（FreeVideo 是可選 adapter，不代表每個 Agent 都內建影片生成）。
**沒有實際呼叫生成工具，就不得聲稱已產出圖片或影片。** 小說不得直接當劇本用，一律先走階段 1 改編。

這一頁是**操作首頁**：每階段做什麼、不准做什麼、跑哪個指令。原理、模板、實戰定案與完整工具清單在
`references/skill-guide.md`（原 SKILL.md 全文，章節不變），由 `h3d next` 指到該讀的那一份。

## 何時使用

- 「把這篇小說／故事做成漫劇、動態漫、短劇」「把小說改編成漫劇劇本」
- 「寫分鏡／鏡頭表／影片提示詞」「設計角色設定／角色聖經」「把商品素材做成帶貨短片」

## 每階段操作首頁

| 階段 | 做什麼 | 不准做什麼 | 跑哪個指令 | 先讀 |
|---|---|---|---|---|
| 0 定調 | 一次問完定調題（題材、載體、畫風、比例、台詞政策），每題附推薦值；**成片形式預設長篇漫劇**（不問集數秒數；使用者主動要短劇才 `h3d decide series_format short`）；**畫風預設推 14 號「古風寫實厚塗・電影感」**（附樣圖，可改選） | 不替使用者決定；不跳過體量反推；不預設切短集 | `init_project.py`、`h3d decide style/aspect_ratio/dialogue_policy` | `references/pipeline.md`、`references/styles.md` |
| 1 改編 | 保留分級、**事件交代完整性**（每個事件起因→經過→結果，壓縮／跳過清單交使用者決定）、依事件估總長、A/B/C 方案、段落架構（使用者要求才分集）、因果債務 | 小說直接當劇本；為秒數壓縮事件；自行砍事件交代 | `event_coverage.py`、`estimate_duration.py --events`、`h3d next` | `references/adapt/novel-to-manju.md`、`references/adapt/structure-and-pacing.md` §零 |
| 2 設定圖 | 主角優先出圖、自檢後重生；引擎定案後全集鎖定 | 換生圖引擎不並排比對；自動核准（永遠要人看臉和服裝） | `h3d decide design_engine`、審核頁 | `references/consistency.md`、`references/styles.md` |
| 3 劇本 | 場景化改寫、台詞預算（4 字/秒、說話 ≤ 60%）、改編差異 | 超預算照送 | `estimate_duration.py --h3`、`sync_script.py` | `references/adapt/screenplay-format.md` |
| 4 分鏡 | **每鏡先寫 `shot_intent`（觀眾要看懂什麼）再定技術值，每項選擇在 `choice_why` 寫理由**；一鏡一張臉、遠景不放人、焦距物距成對寫 | 沒有對應構圖 PNG 就進編譯；按警告類型批量改、為過關改核准內容（人群換空座、補 empty background）；分鏡圖換人或漏關鍵道具 | `h3d sketch`、`validate_storyboard.py` | `references/storyboard/shot-intent.md`、`references/storyboard/cinematic-director.md` |
| 5 提示詞 | **逐鏡親手寫** Layer 2 `five_part_en`（Camera／Motion／Performance／Light／Sound，Motion 與 Performance 必須詳寫；每句要對應看得到或聽得到的結果，不重寫參考圖已有的外貌，寫站位、視線、起訖姿勢、關鍵道具），讀分鏡、構圖與前一鏡狀態後再寫；編譯器只負責組成六段式 | 寫程式產生五小節；編譯後覆寫 segments；用後設詞（authored／approved）或禁止句堆疊交差；沒 ack 就放過警告 | `h3d author`、`h3d compile --check`、`h3d catalog --check` | `references/prompt-authoring.md`、`references/h3/prompt-formats.md`、`references/tooling.md` |
| 6 影片 | 送件 → 收件 → QA → 動態 QA（光流量凍結／定住，自動提案變速清單）→ 逐段結論 → 收件匣 | 兩個 runner 同時跑；碰別人的 job；漂移片拿去 QA | `h3d probe`、`h3d run --plan`、`h3d qa`、`h3d motion`、`h3d verdict`、`h3d inbox` | `references/tooling.md` §2.5–2.8、`references/speed-ramp.md`、`references/skill-guide.md`「階段 6 生成」 |
| 7 配音剪輯 | 已核准的動作段後製變速（原片不動、台詞原速）、ASR 對位、畫外句壓原聲、響度、每角色音色一次定案、全集單一剪輯專案 | 長旁白交給 H3 念（短畫外句與短旁白預設留 H3，長旁白才外部化）；替使用者定音色；覆寫原片；變速台詞區 | `h3d ramp`、`h3d voice align`、`h3d concat plan/build`、`h3d assemble`；剪輯 lens（只給建議）`scripts/craft/edit_review.py` | `references/tooling.md` §2.7、`references/skill-guide.md`「階段 7」、`references/edit/manju-editing-playbook.md`（剪點／轉場／特效／字幕／登場卡／配樂 ducking／響度）、`references/craft/murch-cut`、`references/craft/hamilton-action` |

**正式階段核准以 `review/project-state.json` 為準**，只能走 `build_stage_review.py --approve-stage`（使用者原話）或 `h3d approve --auto`（使用者授權過的階段）。
純文字草稿可按指定範圍交付，不必推進到媒體生成：用 `h3d decide delivery_scope script-only|storyboard-only|prompts-only|full --quote "<使用者原話>"` 定案交付終點（沒定案＝全流程），`h3d next` 到終點就回報 done；`no_image` 時階段 2 只要求文字設定卡。注意：`no_image` 只解除階段 2，階段 4 以後仍要求構圖圖，終點要在階段 3 以前或另行決定。八階段的產出與 HTML 審核頁對照見 `references/skill-guide.md`「八階段流程與 HTML 斷點」，
詳細模板見 `references/pipeline.md`。

## 四道確定性檢查（交付的一部分）

時長量子（17n+5，用 `metadata.frames` 送件）、證據分級（階段 6 要 `VERIFIED`）、segment 級依賴帳本（`h3d deps`）、
失敗目錄（`h3d catalog --check`／`h3d ack`）。`duration_drift`、`PARTIAL`、`已有 waiting 的 job` 都代表「現在不能繼續」，
處置見 `references/tooling.md` §4。

## 資源（索引）

- `references/tooling.md` — **h3d 全部指令與檢查**（跑任何指令前先讀）；§2.5 定案／逐段結論、§2.6 收件匣與自動核准、§2.7 runner／probe／配音／剪輯。
- `references/skill-guide.md` — 原 SKILL.md 全文：核心原則 0–14、專案結構、階段 6 實戰定案、階段 7 配音分層、完整腳本清單。
- `references/pipeline.md` — 八階段詳細流程、提問清單、模板；聲音三層決策與響度標準。
- `references/adapt/`（改編）、`references/storyboard/`（導演分鏡）、`references/consistency.md`（資產一致性）、
  `references/styles.md`（風格鎖定錨）、`references/freevideo.md`、`references/model-profiles.md`、
  `references/minimax-h3.md` 與 `references/h3/`（H3 細部參考，同步自上游 h3-video-prompting）、`references/prompt-playbook.md`、
  `references/craft/`（創作 lens，只給建議不改門禁）、`references/edit/`（階段 7 漫劇剪輯手冊、Concat／剪映草稿調查）。
- 格式：`references/schemas/`（decisions、verdicts）。給 agent 的硬規則另見 `AGENTS.md`。
