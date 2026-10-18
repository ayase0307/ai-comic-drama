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
1. **先定調，再動筆。** 開工前先鎖定：集數與每集時長、題材模式與載體、畫風（從 `references/styles.md` 選一套風格鎖定錨）、畫面比例、語言、旁白或對白、交付到哪一步。**階段 0 必問兩項門禁：台詞政策（4 選 1）與原文體量反推片長公式**。缺的先問使用者，**一次問完，不要擠牙膏**。
2. **一致性靠登記、參考鏈與驗收。** 角色／服裝／場景／道具／音色各有 ID、設定圖與固定描述片段；生物/怪獸設定圖（Creature Sheet）同等規格純底出圖；演員表依該場主角重要性排序。**階段 2 核心資產圖生成前必須詢問指定工具（推薦 Codex CLI），跨章節強制鎖定同一生圖引擎，嚴禁混用；本機 Qwen-Image 2.1 嚴格限定階段 4 鉛筆九宮格構圖審核**。有參考圖時外觀只在首次出現寫一次，沒有時逐字貼片段。設定板版面、驗收門、漂移修復見 `references/consistency.md`。
3. **先分鏡，後生成。** 分鏡走導演分鏡體系（`references/storyboard/cinematic-director.md`），導入「分段級分鏡（7–10 秒/段）」；焦距與物距成對寫；分鏡表未驗證通過不出圖；出圖後先確認角色長相，再拿去生成影片。
4. **生成前先問清楚，再動手。** 圖像與影片**都要**先問使用者：用哪個模型／工具、參數怎麼設、提示詞用中文還英文、先做幾鏡。**提示詞會隨模型不同而變**，確認後才依該模型改寫。詳見 `references/model-profiles.md`。
5. **影片生成優先走 FreeVideo。** 本技能在使用者本機運行，建議搭配 FreeVideo（`http://127.0.0.1:8189`）讓 Agent 直接出片；連線與用法見 `references/freevideo.md`。FreeVideo 連不上才退回問模型的流程。
6. **不假裝生成。** 沒有實際呼叫生成工具，就不得聲稱已產出圖片或影片。
7. **H3 寫實／半寫實走守富定版骨架。** 用 MiniMax H3 且風格為寫實或半寫實（如 `styles.md` 的第 8 種、3D 真人感）時，影片提示詞一律 `【鏡頭——賣點】` → `【光線——色調】` → `【皮膚——通透白皙有真實肌理】` 三段，**皮膚段整段照抄**，只微調光色字眼。原文見 `references/h3/skin-realism-block.md`。**2D、水墨、Q 版、美漫等非寫實風格不用皮膚段**（它含 photorealistic skin，與這些風格的負面錨衝突），改照 `references/h3/scenarios-world-and-styles.md` 的對應風格寫法，畫面風格以設定板參考圖鎖定。FreeVideo 送官方三欄格式（`h3/prompt-formats.md`）。
8. **工作紀律鐵律（先算先定再動手）**：**「先講秒數規劃 → 寫進檔案 → 跑完確定性自檢（E 0）→ 等使用者說『跑』才送 FreeVideo」**，嚴禁邊想邊送件燒時間。

---

## 八階段流程

| 階段 | 做什麼 | 產出 |
|---|---|---|
| 0 定調 | 鎖定題材、載體、畫風錨、比例、**台詞政策（4選1）與體量反推秒數門禁**（`estimate_duration.py --novel`、`init_project.py`） | `project.md`、`adapt/source.json`、`adapt/bible.json` |
| 1 改編 | 小說目錄掃描與單章清洗抽取（`extract_chapter.py`）、保留分級、A/B/C 方案、分集架構、跨集驗收（`compare_adaptation.py --episode`） | 故事地圖、`series-outline`、併入 `project.md` |
| 2 資產與設定圖 | 故事聖經→`assets.md`、**生圖工具詢問推薦（Codex CLI）與跨章節鎖定**、**生物純底設定圖**、**演員表主角優先排序** | `assets.md`、`images/` 設定板 |
| 3 漫劇劇本 | 場景化改寫、時長與台詞預算審計（`estimate_duration.py --h3`）、HTML 註解元數據注入、交接 JSON、人工審核鎖（`sync_script.py`） | `script-ep01.md`、`handoff-ep01.json`、`adaptation-diff.md` |
| 4 導演分鏡 | **分段級分鏡（預設 10s/3 鏡，`handoff_to_skeleton.py`）**、焦距物距、**動作力學三要素**、`INDEPENDENT_REF2VA` 四大錨點、Qwen 鉛筆九宮格構圖審核 | `layer2/*.json`、`storyboard-ep01.md`、`grid-*.png` |
| 5 提示詞包 | **H3 官方六段式批次編譯（`compile_layer2_to_h3.py`）**、防混臉參考圖排序、切點時間保護、LoRA 適配、`--check` 雙重對帳 | `prompts-ep01.md`、`segments-ep01.json` |
| 6 生成 | **主力定案：獨立 Ref2VA（四錨點連戲、一段一張角色圖防平均化）**；`submit_h3_segments.py`（4.20 GiB 顯存臨界點保護）；`verify_video_shot.py` 影片批次審查 | `images/`、`videos/`、`qa-report.json` |
| 7 組裝交付 | **`assemble_episode.py` 智慧配音、字幕燒錄與無縫拼接成片**、旁白稿、字幕、時間線、交付清單 | `final/ep01_final.mp4`、`narration-ep01.md`、`timeline-ep01.csv` |

**詳細做法、每階段模板與檢查點見 `references/pipeline.md`。** 階段 3、4 各有確定性驗證腳本（`scripts/adapt/`、`scripts/storyboard/`），**通過才進下一階段**。

### 建議專案結構

```
<專案名>/
├── project.md              # 定調 + 分集規劃
├── source/                 # 原著小說（不外洩）
├── adapt/                  # 改編中間產物（source.json、bible.json、故事地圖、保留分級、方案）
├── assets.md               # 風格錨 + 角色 / 場景 / 道具 / 音色聖經（ID、固定片段）
├── script-ep01.md          # 漫劇劇本（△ 場號制，無攝影機術語）
├── handoff-ep01.json       # 劇本→分鏡交接
├── adaptation-diff.md      # 改編差異對帳
├── layer2/                 # 分鏡 Layer 2 JSON（機器可讀 SSoT）
├── storyboard-ep01.md      # 分鏡表（人可讀）
├── prompts-ep01.md         # 逐鏡圖像 / 影片提示詞
├── segments-ep01.json       # FreeVideo 批次分段檔（H3 官方六段式結構）
├── panels/                 # Qwen 單格黑白鉛筆手繪草圖（panel-*.png）
├── keyframes/              # Qwen 轉繪全彩關鍵幀首幀（keyframe-*.png，去黑箭頭）
├── narration-ep01.md       # 旁白與字幕稿
├── timeline-ep01.csv       # 剪輯時間線
├── images/                 # 生成圖（設定板、場景主圖、九宮格總覽 grid-*.png）
└── videos/                 # 生成影片片段與審查報告
```

用 `scripts/init_project.py` 一鍵建立骨架（自動初始化 `adapt/source.json`、`adapt/bible.json` 與 `project.md` 門禁欄位）。

---

## 階段 6 生成：怎麼做才穩

**6.0 先確認工具（不可跳過）**

先試連 FreeVideo（`references/freevideo.md`）；連得上，影片就走它，只需確認比例、時長、鏡數與提示詞語言。連不上或使用者指定別的工具，才用一張表問完：模型／工具、關鍵參數（比例、時長、解析度、音訊）、提示詞語言、生成範圍。問完才動工。

> **提示詞依模型而異**——自然語言型、標籤堆疊型、中文原生型寫法完全不同。先寫一版模型無關的主提示詞，再依目標模型改寫。對照表見 `references/model-profiles.md`；**若用 MiniMax H3，改用 `references/minimax-h3.md` 的官方結構**（通用公式套不上去）。

### 實戰驗證結論與使用者 5 條糾正定案（影視漫劇鐵律）

在《噩盡島》實戰全流程生成中，歷經多輪驗證與使用者連續糾正，確立以下三大原則與五大定案：

#### 核心原則與教訓
1. **嚴格區分「✅ 已驗證有效」與「❌ 已驗證失敗／⚠️ 尚未驗證」**，絕不可把試過但失敗的做法寫成規則。
2. **完整寫入「第五輪首幀流程連續兩次誤判成功」的慘痛教訓**：驗證新流程（如生圖模型轉繪首幀）絕不能單看靜態首幀漂亮就宣稱成功！必須與既有已過審的 H3 片段**並排對照畫風**。混用生圖模型首幀會造成風格割裂、從整部片「跳」出來。

#### 定案 1【分段長度：15 秒不是硬規則】（✅ 已驗證有效）
> **使用者原話**：「如果 15 秒塞不下就不要硬塞，**沒有一定要每個片段都 15 秒**，這個請列入重點，因為 15 秒對於人物/場景/佔位的保持度很考驗」
- 15 秒只是 H3 單次時長上限，絕不是創作單位。分段長度由「內容有幾個獨立節拍」決定，**每段建議 2–4 個節拍、7–10 秒**。
- **三層顆粒度轉換**：劇本微鏡（剪輯單位 1–3 秒）→ **分段計畫表（每段 7–10 秒、2–3 鏡，標明自足開場、連戲錨點與收尾交接格，先交人類審核）** → H3 `[Shot N]`（生成單位）。

#### 定案 2【獨立 Ref2VA 定案 vs 首幀 I2VA 適用邊界】
> **使用者原話 1**：「我是說這個劇情就直接重新寫分鏡，所謂的重新寫，**就是不考慮接續首幀的意思，每一個片段都是獨立去寫 ref2va**，頂多考慮站位以及角度等等，而不是像你這樣硬改」  
> **使用者原話 2**：「這種開場基本上算是靜幀的背面，就可以使用首幀動畫，去維持畫風……但如果是剛剛那種一開始是風景的，因為我們本來就有場景參考圖，所以還是用 ref2va」  
> **使用者原話 3（第五輪首幀失敗判定）**：「多人背影段也算失敗，那個畫風跟其他片段差距過大」
- **✅ 已驗證有效（主力定案）**：**每段獨立走 `Ref2VA`**（各自帶場景＋角色設定圖），不使用尾幀續接 `continue_from`（因 FreeVideo API `references` 與 `first/last` 互斥報 422，續接段 0 張角色參考圖會退化為通用塑膠卡通臉）。連戲靠企劃階段寫死四大錨點（**光線、軸線、站位、材質**）與設計「靜止、夠寬、留白」的收尾交接格。
- **❌ 已驗證失敗／⚠️ 尚未驗證（重要警示）**：**「用外部圖片模型（GPT Image / Qwen-Image）先生成彩色首幀再送 H3 I2VA」混在純 Ref2VA 片段中已驗證失敗**，因為兩個引擎兩種畫風，會造成嚴重畫風割裂（使用者亦明確不採用「先用 Qwen-Image-Edit 做 still 再進 H3」）。若要嘗試首幀流程，必須「整部片全部統一用同一個圖片模型生首幀」或「先與既有 H3 片段並排對照畫風通過」，嚴禁單看首幀漂亮就誤判成功！因此階段 6 的 `--to-color-keyframe` 標註為「⚠️ 選用實驗功能（需全片統一畫風並排驗證）」，而將 Qwen 黑白鉛筆九宮格定位為「✅ 階段 4 視覺化構圖與佔位審核工具」。

#### 定案 3【參考圖張數與角色平均化現象】
> **使用者原話**：「這可能跟提示詞品質、以及 FreeVideo 模型訓練有關，走量化版模型可能就能多參考，之後可以嘗試」
- **實測現象**：單段同時掛多張體型相近的角色設定圖（如三個年輕男學生）會被 H3 平均融合成同一張臉；視覺特徵差異極大者（如胖子＋黑框眼鏡）能存活。
- **建議做法**：**保守預設為「一段一張角色參考圖」（要拍 4 個人的反應就拆成 4 段特寫）**；群戲需要時可給到 1 場景 + 最多 5 角色 = 6 張，但需注意融合風險（留待量化版模型再試，不寫成死規則）。
- **強制程式對帳（P0）**：`reference_images` ↔ `subject_definitions` ↔ `retention_analysis` ↔ 說話者 `(Sx)` 必須由同一支程式（`audit_refs_and_segments.py`）一次產生並逐條稽核。

#### 定案 4【遠景人物不可靠 & 正面特寫景深陷阱】（✅ 已驗證有效）
> **使用者原話**：「應該要避免人物在遠景，這是 minimax h3 的弱項……應該要從分鏡面去解決，四人近距離呈現面部微表情，依照人物性格出現冷靜、驚訝、害怕、興奮等等的情緒，可以不用一定要呈現出四人看到蛇，全部都塞在一起的畫面」
1. 用**「一顆鏡頭一張臉」的特寫**演反應（寫明眼眉嘴下顎肌群變化）。
2. 用**「背影（不露臉）」**演群戲走位與「聽到聲音而回頭」的過場連結（背影無五官辨識問題）。
3. **正面特寫段絕不要寫「遠處的那個東西」**（實測兩次都會把遠處的蛇塞到角色肩後景深裡），地理由前導背影段建立。
4. 交代怪物巨大：用景深邊緣失焦色塊、地面長影、前景遮擋，或貼地近景拍局部（蛇頭衝鏡、纏住腳踝）。
5. 3 人以上＋大型生物同場時，先畫一張**俯視佔位圖（blocking map）**。

#### 定案 5【台詞字數預算與動作力學三要素】（✅ 已驗證有效）
> **使用者原話（台詞）**：「這個台詞字數明顯超過秒數限制，變成加速講話，你應該要精簡台詞」  
> **使用者原話（動作）**：「蛇的動作明顯不足且不自然，像是玩具，比方說他被打應該要強烈掙扎及反抗、攻擊的時候要有環境特效（揚起灰塵或是風切等等），戰鬥要有強烈的打擊感及環境/視覺特效」
- **台詞預算**：**4 字／秒**，單句 ≤ 12–15 字，窗口 ≥ 2.5 秒，兩句間隔 ≥ 3 秒，**總說話秒數 ≤ 片長 60%**；猛烈動作拍不排台詞（喘息放 `overall_soundscape`）。
- **動作力學三要素**：分鏡表「動作」欄必填 **① 施力點（從哪發起）→ ② 傳導路徑（經身體哪裡、肌肉/鱗片變形與重量轉移）→ ③ 受擊反應與環境反饋（退後距離、結構折疊、立刻反擊、揚塵/塵環/風切位移空氣）**。

---

### 6.1 生成操作流

1. **分鏡 Layer 2 鎖定與分段表審核**：每段 7–10 秒，確定四大連戲錨點與收尾交接格。
2. **Qwen 鉛筆草圖九宮格（✅ 構圖審核工具）**：執行 `qwen_storyboard_grid.py` 輸出 3x3 九宮格黑白構圖，審核走位與滅點，單格有問題以 `patch_shot.py` 搭配 `--redraw-shot` 重抽，通過者鎖定保護。
3. **出資產設定圖**：角色設定板、場景主圖、**生物/怪獸純色三視圖（Creature Sheet，嚴禁帶背景劇照）**，過驗收門。
4. **【主力定案】獨立 Ref2VA 影片生成**：每段獨立給予對應的場景與角色圖，嚴禁尾幀續接；以 `audit_refs_and_segments.py` 跑通 P0 程式對帳。
5. **【⚠️ 選用實驗功能】Qwen 轉繪全彩首幀 + I2VA**：若要採用首幀流程，**必須整部片統一使用同一圖片模型生成首幀**，並先與已生成的 H3 片段**並排對照畫風無割裂感**後，方可送 I2VA。
6. **`verify_video_shot.py` 自動審查**：審驗時長、彩度防黑白污染、九宮格殘留與相鄰色盤連貫性。

---

## 階段 7 組裝交付與配音決策

### 7.1 配音分層決策（新增重要規範）
實測 MiniMax H3 原生中文配音 ASR 置信度僅在 0.43–0.54 之間，存在發音含糊、語速搶跑或偶發 -40dB 靜音。分鏡與 prompt 中的 `<d>` 標籤依然保留，作為生成時口型與時間點的物理錨點。階段 7 提供三種決策：
- **方案 A（推薦）**：**抽掉 H3 人聲軌，使用外部 TTS（如 Edge-TTS / CosyVoice）重配清晰中文台詞，再以 ffmpeg 混回環境音效軌**。
- **方案 B**：接受 H3 原生配音，透過 ffmpeg 強制燒錄高對比中文字幕補充可讀性。
- **方案 C**：全片去台詞化，改採全域純旁白解說。

### 7.2 後期交付檔案
- **旁白與字幕稿**（`narration-ep01.md`）：時間碼對齊。
- **剪輯時間線**（`timeline-ep01.csv`）：由 `layer2_to_table.py --timeline` 產生。
- **拼接成片**：使用 ffmpeg 拼接影片片段、燒錄字幕與混音。
- **交付清單**：列出已生成檔案、未完成鏡號。

---

## 資源

- `references/pipeline.md` — 八階段詳細流程、提問清單與各階段模板。
- `references/adapt/` — **小說改編（階段 1、3）**：`novel-to-manju.md` 為總規範（10 階段、6 題材模式、四道退稿閘門、100 分制），其餘為原則、故事聖經、結構節奏、劇本格式、視覺寫作、對白、可拍性、分鏡交接、授權證據各篇，`templates/` 含交接 JSON Schema。腳本在 `scripts/adapt/`（附 10 個測試案例）。
- `references/storyboard/` — **導演分鏡（階段 4）**：`cinematic-director.md` 為總規範（v2.0），含三步法、焦距物距光學、漫劇九宮格與連戲狀態機、武戲 90° 與多模型編譯；`combat-and-vfx-library.md`（高階武戲連招、玄幻大招五段鏈與 11 大戰場拓撲）；`acting-and-emotion-library.md`（邁斯納行為表演法、言行反差、10 大景別句型與 4D 配音）；`templates/` 含 Layer 2 JSON Schema。腳本在 `scripts/storyboard/`。
- `references/consistency.md` — **資產與一致性規範**：ID、角色設定板（洋子鎖臉規範）、生物怪獸三視圖規範、場景、道具、音色、多模態素材職責表、漂移偵測與修復、驗收門。階段 2、6 必讀。
- `references/styles.md` — **漫劇風格鎖定錨**：十餘種主流風格的錨定詞、負面錨、色盤與同角色樣圖。階段 0 選風格時讀。
- `references/freevideo.md` — **建議搭配 FreeVideo**：連線步驟、規則、與八階段的對應。階段 6 先讀這份。
- `references/model-profiles.md` — **生成前必問清單**，以及各圖像／影片模型的提示詞風格對照與改寫流程。
- `references/minimax-h3.md` — **MiniMax H3 專章（入口）**：規格、五種模式、預算表、十條速查、Red Flags、負面轉正面詞表、8GB 顯存 OOM 拆段公式、Windows 七大工程坑。用 H3 前必讀。
- `references/h3/` — H3 細部參考（與上游 [h3-video-prompting](https://github.com/ayase0307/h3-video-prompting) 的 `references/` 同名同步；詳見 `memory.md`）：
  - `lora-guide.md` — **MiniMax H3 專用 LoRA 實戰與自動適配指南**：核心 LoRA 實測校準（停用 camera_motion、驗證速度滑桿與 Bunny 武戲）、正負權重滑塊、疊加預算鐵則與 FreeVideo API 掛載格式。
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
- `scripts/init_project.py` — 一鍵建立專案骨架與模板檔，自動初始化 `adapt/source.json`、`adapt/bible.json` 與 `project.md` 兩大門禁欄位（台詞政策與體量秒數反推）。
- `scripts/adapt/extract_chapter.py` — 小說大檔目錄掃描（`--list`）、單章抽取（`--volume`、`--chapter`）與 Pandoc 6 重自動清洗工具。
- `scripts/adapt/estimate_duration.py` — Unicode P 類別統一計字、`--novel` 階段 0 體量反推門禁（四大台詞政策試算）與 `--h3` 實戰台詞預算審計（4字/秒、單句 ≤15 字警告、說話時長佔比 ≤60% 警告）。
- `scripts/adapt/sync_script.py` — 人工審核鎖定、從零建立 handoff、多場景自動擴展、劇本 HTML 註解元數據（`<!-- source / must_keep / change -->`）自動解析注入與 `--prune-extra` 未鎖定多餘場景修剪工具。
- `scripts/adapt/compare_adaptation.py` — 原著與改編差異比對，支援 `--episode` 單集過濾驗收與多檔合併（`--handoff`、`--script` 傳多檔）全章總體驗收，連動 `--h3`。
- `scripts/adapt/*.py` — 劇本結構、時長、連戲、改編差異完整驗證套件。
- `scripts/storyboard/handoff_to_skeleton.py` — 交接 JSON → Layer 2 骨架，預設每段 10.0s / 3 鏡（支援 `--max-segment-sec`、`--max-shots`）、統一 4.0 字/秒、窗口 $\ge 2.5s$、動作力學三要素結構模板（施力點 ➔ 傳導路徑 ➔ 受擊反饋）、`INDEPENDENT_REF2VA` 握手與四大連戲錨點（lighting/axis/blocking/texture）。
- `scripts/storyboard/compile_layer2_to_h3.py` — Layer 2 批次編譯為 H3 官方六段式提示詞（`prompts-epXX.md`）與 FreeVideo 批次分段檔（`segments-epXX.json`），支援防混臉參考圖排序（一段一張角色圖）、切點時間軸保護（$D - \text{末切點} \ge 2.05s$）、光源名詞映射、官方運鏡詞微交替、LoRA 自動適配與 `--check` 雙重對帳。
- `scripts/storyboard/audit_refs_and_segments.py` — 分段參考圖、主體定義、說話者與字數預算多維程式對帳工具（支援雙重審查：模式 A 序對 + 模式 B 13 條自檢）。
- `scripts/storyboard/patch_shot.py` — 單鏡局部修改與審核鎖定工具（支援秒數吸收、自動重算時間軸）。
- `scripts/storyboard/qwen_storyboard_grid.py` — Qwen-Image 2.1 電影分鏡鉛筆草圖、單格局部重繪、九宮格拼版與去黑箭頭轉全彩首幀工具。
- `scripts/storyboard/submit_h3_segments.py` — 階段 6 FreeVideo H3 批次提交與顯存保護工具（4.20 GiB 顯存臨界點安全保護、不足時差額診斷、--dry-run 乾跑檢查、參考圖 SHA256 快取、LoRA 自動適配與任務輪詢下載）。
- `scripts/storyboard/verify_video_shot.py` — AI 影片自動審查與分鏡規格差異檢驗門禁工具（分段總時長精確對齊、彩度防黑白污染、九宮格分屏殘留、串聯 `color_qa.py` 輸出 `qa-report.json`）。
- `scripts/storyboard/assemble_episode.py` — 階段 7 配音分層、字幕燒錄與成片拼接交付工具（智慧 TTS 雙重保障：Edge-TTS 遇 403 自動降級 SAPI、Windows 字幕冒號轉義、`adelay`+`amix` 背景音分層混音、FFmpeg Concat 無縫拼接成片，附 `--self-test`）。
- `scripts/storyboard/layer2_to_table.py` — Layer 2 → 人可讀 Markdown 分鏡表與時間線 CSV 匯出工具。
- `scripts/storyboard/validate_storyboard.py` — 分鏡 Layer 2 JSON 靜態驗證工具。
- `scripts/storyboard/director_storyboard_assistant.py` — 預設配置與多模型提示詞編譯輔助工具。
- `scripts/color_qa.py` — 跨鏡頭色彩一致性檢查（同步自上游，用法見 `references/h3/lighting-and-color.md`）。

