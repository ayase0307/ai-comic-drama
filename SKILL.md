---
name: ai-comic-drama
description: 在 Agent 內部端到端製作 AI 漫劇／動態漫／短劇，不需任何外部服務、自託管平台或 MCP。當使用者要把小說、故事、劇本或商品素材做成角色一致的漫劇影片，或要改編小說成漫劇劇本、寫分鏡、鏡頭表、角色設定圖、風格設定、圖像提示詞、影片提示詞、旁白文案時，使用本技能。涵蓋小說改編（保留分級、A/B/C 方案、分集、可拍劇本）、資產與一致性規範、導演分鏡（焦距物距、連戲）、風格鎖定錨、提示詞包，並以內建圖像與影片生成能力出圖、出片。
agent_created: true
---

# AI 漫劇製作（純 Agent 版）

## Overview

在 Agent 內部把「小說／故事 → 改編分集 → 資產與設定圖 → 漫劇劇本 → 導演分鏡 → 提示詞 → 圖 → 片」整條線跑完。

**零外部依賴**：核心流程不需要自託管平台、MCP、API Key 或資料庫（FreeVideo 是選配，不裝也能走完）。寫作與分鏡由 Agent 完成；出圖、出片直接用內建的圖像與影片生成能力。所有中間產物落成檔案，存在專案目錄裡，可隨時續做或改稿。

## 何時使用

- 「幫我把這篇小說／這個故事做成漫劇、動態漫、短劇」「幫我把小說改編成漫劇劇本」
- 「幫我寫分鏡」「幫我寫鏡頭表」「幫我寫影片提示詞」
- 「幫我設計角色設定／角色聖經」
- 「把這個商品素材做成帶貨短片」

## 核心原則

0. **小說不得直接當劇本用。** 吃進小說一律先走階段 1 改編（保留分級、A/B/C 方案、分集、因果債務），再改寫成漫劇劇本；原稿已是劇本或原創梗概才可略過解析。規範見 `references/adapt/novel-to-manju.md`。
1. **先定調，再動筆。** 開工前先鎖定：集數與每集時長、題材模式與載體、畫風（從 `references/styles.md` 選一套風格鎖定錨）、畫面比例、語言、旁白或對白、交付到哪一步。缺的先問使用者，**一次問完，不要擠牙膏**。
2. **一致性靠登記、參考鏈與驗收。** 角色／服裝／場景／道具／音色各有 ID、設定圖與固定描述片段；有參考圖時外觀只在首次出現寫一次，沒有時逐字貼片段。設定板版面、驗收門、漂移修復見 `references/consistency.md`。
3. **先分鏡，後生成。** 分鏡走導演分鏡體系（`references/storyboard/cinematic-director.md`），台詞一字不改、焦距與物距成對寫；分鏡表未驗證通過不出圖；出圖後先確認角色長相，再拿去生成影片。
4. **生成前先問清楚，再動手。** 圖像與影片**都要**先問使用者：用哪個模型／工具、參數怎麼設、提示詞用中文還英文、先做幾鏡。**提示詞會隨模型不同而變**，確認後才依該模型改寫。詳見 `references/model-profiles.md`。
5. **影片生成優先走 FreeVideo。** 本技能在使用者本機運行，建議搭配 FreeVideo（`http://127.0.0.1:8189`）讓 Agent 直接出片；連線與用法見 `references/freevideo.md`。FreeVideo 連不上才退回問模型的流程。
6. **不假裝生成。** 沒有實際呼叫生成工具，就不得聲稱已產出圖片或影片。
7. **H3 寫實／半寫實走守富定版骨架。** 用 MiniMax H3 且風格為寫實或半寫實（如 `styles.md` 的第 8 種、3D 真人感）時，影片提示詞一律 `【鏡頭——賣點】` → `【光線——色調】` → `【皮膚——通透白皙有真實肌理】` 三段，**皮膚段整段照抄**，只微調光色字眼。原文見 `references/h3/skin-realism-block.md`。**2D、水墨、Q 版、美漫等非寫實風格不用皮膚段**（它含 photorealistic skin，與這些風格的負面錨衝突），改照 `references/h3/scenarios-world-and-styles.md` 的對應風格寫法，畫面風格以設定板參考圖鎖定。FreeVideo 送官方三欄格式（`h3/prompt-formats.md`）。

---

## 八階段流程

| 階段 | 做什麼 | 產出 |
|---|---|---|
| 0 定調 | 鎖定題材、載體、畫風錨、比例等設定 | `project.md` |
| 1 改編 | 小說解析、保留分級、A/B/C 方案、分集架構（原稿是小說必走） | 故事地圖、`series-outline`、併入 `project.md` |
| 2 資產與設定圖 | 故事聖經→`assets.md`（ID、風格錨、色票、固定片段）、設定板 | `assets.md`、`images/` 設定板 |
| 3 漫劇劇本 | 場景化改寫、時長與可製作性審計、交接 JSON、人工審核鎖（`sync_script.py`） | `script-ep01.md`、`handoff-ep01.json`、`adaptation-diff.md` |
| 4 導演分鏡 | 三步法、焦距物距、連戲握手、單鏡局部修改（`patch_shot.py`）、Qwen 鉛筆九宮格（`qwen_storyboard_grid.py`） | `layer2/*.json`、`storyboard-ep01.md`、`grid-*.png` |
| 5 提示詞包 | Layer 3 編譯成目標模型語法 | `prompts-ep01.md` |
| 6 生成 | 兩段式轉換鏈：鉛筆九宮格審核 → 轉全彩關鍵幀首幀 → H3 逐鏡生成 → `verify_video_shot.py` 影片審查 | `keyframes/`、`images/`、`videos/`、審查報告 |
| 7 組裝交付 | 旁白稿、字幕、剪輯時間線、交付清單 | `narration-ep01.md`、`timeline-ep01.csv` |

**詳細做法、每階段模板與檢查點見 `references/pipeline.md`。** 階段 3、4 各有確定性驗證腳本（`scripts/adapt/`、`scripts/storyboard/`），**通過才進下一階段**。

### 建議專案結構

```
<專案名>/
├── project.md              # 定調 + 分集規劃
├── source/                 # 原著小說（不外洩）
├── adapt/                  # 改編中間產物（故事地圖、保留分級、方案）
├── assets.md               # 風格錨 + 角色 / 場景 / 道具 / 音色聖經（ID、固定片段）
├── script-ep01.md          # 漫劇劇本（△ 場號制，無攝影機術語）
├── handoff-ep01.json       # 劇本→分鏡交接
├── adaptation-diff.md      # 改編差異對帳
├── layer2/                 # 分鏡 Layer 2 JSON（機器可讀 SSoT）
├── storyboard-ep01.md      # 分鏡表（人可讀）
├── prompts-ep01.md         # 逐鏡圖像 / 影片提示詞
├── panels/                 # Qwen 單格黑白鉛筆手繪草圖（panel-*.png）
├── keyframes/              # Qwen 轉繪全彩關鍵幀首幀（keyframe-*.png，去黑箭頭）
├── narration-ep01.md       # 旁白與字幕稿
├── timeline-ep01.csv       # 剪輯時間線
├── images/                 # 生成圖（設定板、場景主圖、九宮格總覽 grid-*.png）
└── videos/                 # 生成影片片段與審查報告
```

用 `scripts/init_project.py` 一鍵建立骨架。

---

## 階段 6 生成：怎麼做才穩

**6.0 先確認工具（不可跳過）**

先試連 FreeVideo（`references/freevideo.md`）；連得上，影片就走它，只需確認比例、時長、鏡數與提示詞語言。連不上或使用者指定別的工具，才用一張表問完：模型／工具、關鍵參數（比例、時長、解析度、音訊）、提示詞語言、生成範圍。問完才動工。

> **提示詞依模型而異**——自然語言型、標籤堆疊型、中文原生型寫法完全不同。先寫一版模型無關的主提示詞，再依目標模型改寫。對照表見 `references/model-profiles.md`；**若用 MiniMax H3，改用 `references/minimax-h3.md` 的官方三段式結構**（通用公式套不上去）。

**6.1 標準轉換鏈（實驗驗證標準實踐）**：
1. **分鏡 Layer 2 鎖定**：完成焦距物距、走位遮擋與連戲狀態檢查。
2. **Qwen 鉛筆草圖九宮格（人工審核與單格零污染重繪）**：執行 `qwen_storyboard_grid.py` 輸出 3x3 九宮格黑白構圖（支援 `--no-arrows` 純淨底稿）。導演人工審核；未過審鏡頭透過 `patch_shot.py` 微調參數，以 `--redraw-shot` 單格重抽，其餘通過之格子 100% 鎖定保護。
3. **Qwen 轉繪全彩關鍵幀首幀（自動擦除黑箭頭）**：執行 `qwen_storyboard_grid.py --to-color-keyframe <shot_id_or_all>`，將單格草圖送入 Qwen-Image 2.1 Turbo 圖生圖，強制注入屬性解耦擦除指令，保留構圖透視與姿態，擦除粗黑動向箭頭與透視輔助線，輸出至 `keyframes/keyframe-{shot_id}.png`。
4. **H3 逐鏡圖生視頻（I2VA）**：以全彩關鍵幀為首幀（image 1），影片提示詞只寫運動與物理連續感，輸出至 `videos/`。
5. **`verify_video_shot.py` 影片自動審查**：審驗時長誤差（≤ 0.5s）、彩度（防灰階線稿滲透 C* ≥ 10.0）、九宮格分屏線殘留偵測與色彩連貫性（dE76 ≤ 25.0），產出審查報告並回寫 Layer 2。

**6.2 先出資產設定圖**：角色設定板（面部特寫＋正／側／背、6 表情、色票、身高對照、每套服裝一張）、場景主圖、道具、音色母帶，規格與驗收門見 `references/consistency.md`。提示詞＝固定描述片段＋風格鎖定錨。給使用者確認長相與音色。

**6.3 確認後才出分鏡圖與全彩關鍵幀**。參考鏈：角色板＋場景主圖作圖生圖輸入；有參考圖時外觀只在首次出現寫一次，沒有時逐字貼固定片段。每鏡出完跑漂移清單。

**6.4 影片優先用圖生視頻**：拿已確認的全彩關鍵幀當首幀，提示詞只寫**運動**（運鏡、主體動作、時序、物理連續感），不重複描述靜態外觀。

**6.5 逐鏡生成、逐鏡檢查**。不要一次丟十幾鏡；出問題先修提示詞再重試。

> 影片生成需 1–3 分鐘。批次生成前先跟使用者對齊數量與模型選擇。

## 階段 7 交付

- 影片片段之間的**拼接與轉場**、字幕燒錄、配音混音屬於後期；可用 ffmpeg 完成，或匯出時間線 CSV 讓使用者進剪映等工具處理。
- 交付時附**清單**：生成了哪些檔、哪些鏡尚未生成。

---

## 資源

- `references/pipeline.md` — 八階段詳細流程、提問清單與各階段模板。
- `references/adapt/` — **小說改編（階段 1、3）**：`novel-to-manju.md` 為總規範（10 階段、6 題材模式、四道退稿閘門、100 分制），其餘為原則、故事聖經、結構節奏、劇本格式、視覺寫作、對白、可拍性、分鏡交接、授權證據各篇，`templates/` 含交接 JSON Schema。腳本在 `scripts/adapt/`（附 10 個測試案例）。
- `references/storyboard/` — **導演分鏡（階段 4）**：`cinematic-director.md` 為總規範（v2.0），含三步法、焦距物距光學、漫劇九宮格與連戲狀態機、武戲 90° 與多模型編譯；`templates/` 含 Layer 2 JSON Schema。腳本在 `scripts/storyboard/`。
- `references/consistency.md` — **資產與一致性規範**：ID、角色設定板、場景、道具、音色、參考鏈、漂移偵測與修復、驗收門。階段 2、6 必讀。
- `references/styles.md` — **漫劇風格鎖定錨**：十餘種主流風格的錨定詞、負面錨、色盤與同角色樣圖。階段 0 選風格時讀。
- `references/freevideo.md` — **建議搭配 FreeVideo**：連線步驟、規則、與八階段的對應。階段 6 先讀這份。
- `references/model-profiles.md` — **生成前必問清單**，以及各圖像／影片模型的提示詞風格對照與改寫流程。
- `references/minimax-h3.md` — **MiniMax H3 專章（入口）**：規格、五種模式、預算表、十條速查、Red Flags。用 H3 前必讀。
- `references/h3/` — H3 細部參考（與上游 [h3-video-prompting](https://github.com/ayase0307/h3-video-prompting) 的 `references/` 同名同步；詳見 `memory.md`）：
  - `prompt-formats.md` — 四種 prompt 格式決策（官方三欄／六段式／中文三段／社群區塊）、對齊句、參考檔上限。
  - `skin-realism-block.md` — **守富定版**三段式骨架與皮膚段原文（整段照抄）。
  - `motion-quality.md`、`action-choreography.md`、`rhythm-and-pacing.md` — 動作品質、動作拆解與打鬥一拍、節奏卡點與時間軸。
  - `shot-variety-and-staging.md` — 跨 shot 變化四軸、spec 卡、送出前自檢（寫完 prompt 必跑 §10）。
  - `failure-triage.md` — 症狀→原因→最小修正對照表、送出前 8 問、迭代策略。
  - `scenarios-people.md` — 情境庫 A：對白短劇★、UGC、唱歌、舞蹈、打鬥★、跑酷、喜劇、情感、懸疑、vlog、POV、旁白數位人★、真人照片（★＝漫劇常用）。
  - `scenarios-world-and-styles.md` — 情境庫 C：空鏡、自然、動物、車輛、2D anime、3D 卡通、黏土紙藝、手繪融合、動態圖形、VFX、循環、設定板、綠幕、混剪。
  - `scenarios-commercial.md` — 情境庫 B：產品 hero、開箱、液體食物、品牌片、時尚美妝、logo 片頭、UI、電商、工業、建築。
  - `camera-and-transitions.md` — 運鏡詞表、景別鏡頭角度、各類型預設鏡頭、切鏡、轉場寫成事件、手持感、運鏡動機、rack focus。
  - `audio-and-dialogue.md`、`audio-pipeline.md` — 三層音軌、對白預算、speaker 格式；聲音一次到位、跨片段鎖音色、外部 TTS、Openverse 後製。
  - `lighting-and-color.md` — 光影配色與跨鏡頭色彩一致；腳本 `scripts/color_qa.py`。
  - `references-and-editing.md`、`long-form-planning.md` — 素材分工、遷移、影片編輯、續接；長片分段規劃。
  - `example-fight-10s.md`、`example-spec-to-prompt-10s.md`、`example-seedance-to-h3.md` — 完整改寫範例。
  - `community-sources.md` — 規則來源與可信度。
- `references/prompt-playbook.md` — 圖像／影片提示詞撰寫手冊（景別、運鏡、光線、風格鎖、負面提示詞）。
- `scripts/init_project.py` — 建立專案骨架與模板檔。
- `scripts/adapt/*.py` — 劇本結構、時長、連戲、改編差異驗證。
- `scripts/adapt/sync_script.py` — 人工審核鎖定與 Markdown 劇本修改同步回寫 `handoff-epNN.json` 工具。
- `scripts/storyboard/handoff_to_skeleton.py` — 交接 JSON → Layer 2 骨架；`layer2_to_table.py` — Layer 2 → 表格／時間線；`validate_storyboard.py` — 分鏡靜態驗證；`director_storyboard_assistant.py` — 預設配置與多模型提示詞編譯。
- `scripts/storyboard/patch_shot.py` — 單鏡局部修改與審核鎖定工具（支援秒數吸收、自動重算時間軸）。
- `scripts/storyboard/qwen_storyboard_grid.py` — Qwen-Image 2.1 電影分鏡鉛筆草圖、單格局部重繪、九宮格拼版與去黑箭頭轉全彩首幀工具。
- `scripts/storyboard/verify_video_shot.py` — AI 影片自動審查與分鏡規格差異檢驗門禁工具（時長、彩度防黑白污染、九宮格分屏殘留、色彩連貫性）。
- `scripts/color_qa.py` — 跨鏡頭色彩一致性檢查（同步自上游，用法見 `references/h3/lighting-and-color.md`）。
