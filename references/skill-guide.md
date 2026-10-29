# SKILL 詳細說明（由 SKILL.md 移出）

> SKILL.md 改成「操作首頁」（每階段做什麼／不准做什麼／跑哪個指令）。原本 SKILL.md 的完整內容原封不動移到這一頁，
> 章節標題不變；`h3d next` 會指到該讀的章節。路徑一律相對於 repo 根目錄（例如 `references/tooling.md`）。

## Overview

依使用者指定的交付範圍，完成小說改編、劇本、導演分鏡、提示詞，或使用實際可用的圖片／影片工具生成媒體。文字規劃可獨立交付；媒體生成與後期需要相應工具、連線、模型或本機可執行檔案。

### 能力與依賴層級

- **文字規劃**：Agent 可協助改編、劇本、分鏡與提示詞。按使用者目標停在相應 draft/approved 階段，不因完整 pipeline 而追加未要求的媒體。
- **本機檢查與編譯**：Python 標準庫執行主要 JSON/提示詞工具；部分審核頁和分鏡總覽圖工具需要 Pillow；影片檢查／組裝需要 FFmpeg/ffprobe。使用前依所跑命令檢查相應能力。
- **圖片生成**：需目前 Agent 暴露的圖片工具，或使用者指定且可用的本機／遠端圖片後端。
- **影片生成**：需目前 Agent 暴露的相容影片工具，或可連線的 provider/adapter。FreeVideo 是本 repo 支援的 adapter 選項，不代表每個 Agent 都內建影片生成。

原稿與生成媒體的處理位置依所選工具而定，不能承諾全程在本機處理。沿用使用者已選的工具與既有授權，不為同一決策重複確認。

## 何時使用

- 「幫我把這篇小說／這個故事做成漫劇、動態漫、短劇」「幫我把小說改編成漫劇劇本」
- 「幫我寫分鏡」「幫我寫鏡頭表」「幫我寫影片提示詞」
- 「幫我設計角色設定／角色聖經」
- 「把這個商品素材做成帶貨短片」

## 核心原則

> **成片形式預設＝長篇漫劇。** 把故事講清楚是第一優先：每個原著關鍵事件都要交代起因→經過→結果（含動機、因果、時地轉換），不以每集秒數壓縮事件；預設不分集，整部一支連續長片，使用者明確要求才分集（每集＝完整劇情單元）。短劇／竪屏爆款短集（1–2 分鐘、強鉤子）是 opt-in（`h3d decide series_format short`），`ai-drama-hit-method` lens 只在短劇模式使用。規範見 `references/adapt/structure-and-pacing.md` §零。

0. **小說不得直接當劇本用。** 吃進小說一律先走階段 1 改編（保留分級、事件交代完整性、A/B/C 方案、段落架構（使用者要求才分集）、因果債務），再改寫成漫劇劇本；原稿已是劇本或原創梗概才可略過解析。規範見 `references/adapt/novel-to-manju.md`。
1. **先確認交付範圍與已知資料。** 確認使用者要劇本、分鏡、提示詞、圖片或成片；沿用已提供的 brief、模型與參數，不重問。只有缺少且會阻礙當前交付的決策才詢問。台詞政策與原文體量估算依改編範圍選用，不強加到純分鏡請求。
2. **一致性靠登記、參考鏈與驗收。** 可用角色／服裝／場景／道具 ID、固定描述與設定圖追蹤資產。沿用已選的生圖工具；若需換工具，先將候選輸出與已核准素材並排比較風格，再交使用者核准。設定板與分鏡構圖可由已連線的 Qwen、手繪或其他圖像工具提供；逐格需能對應 shot，並通過同一 stage-4 review。
3. **先分鏡，後生成。** 分鏡走導演分鏡體系（`references/storyboard/cinematic-director.md`），焦距與物距成對寫。使用者只要文字分鏡時，分鏡 draft 本身即可交付，不要求出圖或影片；若要進入 H3 編譯，依 stage-4 gate 提供每鏡對應構圖圖並完成人工審核。
4. **工具與參數只問未提供的部分。** 生成工具不同，提示詞與參數需依其實際介面調整。詳見 `references/model-profiles.md`。
5. **FreeVideo 是可選 adapter。** 先確認目前工具有相容的影片能力；FreeVideo 在本機運行且已啟用時可用其 adapter，連線不可用時只能改用另一個實際可用且使用者接受的後端，否則交付停在文本／提示詞階段。
6. **不假裝生成。** 沒有實際呼叫生成工具，就不得聲稱已產出圖片或影片。
7. **依適用風格引用提示詞模板。** H3 寫實／半寫實可參考 `references/h3/skin-realism-block.md`；只在符合風格且不與原稿、角色設定或核准畫風衝突時採用，不能覆蓋角色已設定的膚色或外觀。2D、水墨、Q 版、美漫等依其風格指南撰寫。此 CLI 的 Ref2VA 輸出採六段式，見 `h3/prompt-formats.md`。
8. **先規劃再執行生成**：要生成媒體時，先確認素材、規格與工具可用，再依使用者要求送件；使用者只要求文字交付時，停在該交付階段。
9. **依範圍使用審核頁與狀態門禁**：需要正式跨階段或 H3 編譯／提交時使用 `review/project-state.json`。核准綁定輸入 hash；內容變更後須重審。每階段是否停下等待核准，依使用者要求與該交付的審核流程決定，不把完整製作流程強加給文字 draft。
10. **角色設定與改編檢查依來源選用**：改編小說且需保持原著依據時，記錄角色來源與改編差異；既有劇本、原創故事或純分鏡任務不需建立不適用的 v4 角色檔。
11. **階段 4 構圖審核**：要進入 H3 編譯，Layer 2 的每鏡須有可對應的有效構圖 PNG（分鏡總覽圖或 `sketch_file`/panel），並由 `review/stage-4-storyboard.html` 審核。圖可由免生圖 SVG 構圖（`h3d sketch`，0 次生圖 API，建議先用它審走位）、Qwen、手繪或其他工具製作；所有來源使用相同 shot 對應、review 與 hash gate。純文字分鏡 draft 不受媒體生成限制。編譯需有效 stage 4 核准；實際送件需有效 stage 5 核准。
12. **防偷懶物理穿模與罐頭詞禁令**：
    - **每鏡提示詞必須親手寫（強制，`references/prompt-authoring.md`）**：每個 `[Shot N]` 寫齊 Camera／Motion／Performance／Light／Sound，Motion 與 Performance 必須寫詳細；agent 要逐鏡讀分鏡、構圖圖與前一鏡狀態後自己寫進 Layer 2 的 `five_part_en`。**不准寫程式產生五小節內容、不准編譯後覆寫 segments、不准用後設詞（authored／approved）或一串禁止句交差。** `prompt_authoring.py` 對最終送件文字檢查 E30–E38，`compile --check`、階段 5 審核頁與送件都會擋。
    - **禁止同段/跨段複製貼上罐頭詞**（如「微風掠過衣擺，光影保持自然抖動」、「Then the motion transitions smoothly.」等，由 `validate_storyboard.py` 與 `audit_refs_and_segments.py` 確定性攔截）。
    - **禁止多主體碰撞擠壓**：單鏡嚴禁同時塞入主角＋路人＋道具＋巨獸等 4 方碰撞（實測會導致道具懸空吸附 3 秒、巨獸如布偶倒塌），必須拆解為主客觀分鏡。
    - **禁止無參考圖路人單獨佔據中近景或特寫主鏡**：防止 H3 失去風格鎖定而漂移至真人恐怖片。
    - **精確 LoRA 匹配**：LoRA 綁定採精確複合詞匹配，杜絕「刺耳火星」誤掛刀劍 LoRA 或「家具砸擊」誤掛拳擊 LoRA。
13. **四道確定性檢查是交付的一部分，不是可選建議**（操作細節見 `references/tooling.md`）：
    - **時長量子**：H3 把秒數向上取到 `17n+5` 影格。一律用 `metadata.frames` 送件，回讀服務端 `frames` 與下載後 ffprobe 長度；不符即取消並隔離，不得把漂移的片子拿去 QA。
    - **證據分級**：任何「通過」都要說明憑什麼——`measured`（本機量過）／`sourced`（文件或競品）／`inferred`（推論）。沒有成片只有 `UNVERIFIED`；階段 6 閘門要求 `VERIFIED`。禁止把 `TECHNICAL CHECK PASSED` 當成「可以開拍」。
    - **依賴帳本**：改動後跑 `h3d deps --record` 再 `--status`，以 segment 為單位列出 `prompt_stale`／`video_older_than_prompt`／`video_missing`；不要用「整個階段重簽」代替逐段判斷。
    - **失敗目錄**：`h3d catalog --check` 會用已實測的失敗模式掃提示詞；`enforce=error` 直接擋，其餘警告必須改稿或 `h3d ack` 明確接受（ack 綁提示詞 hash 與目錄版本，並納入 stage-5 快照）。
    - **訊息即證據**：`duration_drift`、`PARTIAL`、`已有 waiting 的 job` 這些字樣都代表「現在不能繼續」，處置方式寫在 `references/tooling.md` §4。

14. **創作 lens 只給建議**：`references/craft/` 下的爆款方法論、荒木、McKee、McCloud 等 lens 會把報告寫到 `review/craft/stage-N-*.md`，審查頁會顯示，但不會改變任何門禁或核准狀態。詳見 `references/craft/README.md`。

---

## 八階段流程與 HTML 斷點

| 階段 | 做什麼 | 產出與驗證門禁 | HTML 審核介面 |
|---|---|---|---|
| 0 定調 | 鎖定題材、載體、畫風錨、比例、**台詞政策（4選1）與體量反推秒數門禁**（`estimate_duration.py --novel`、`init_project.py`） | `project.md`、`adapt/source.json`、`adapt/bible.json` | `review/stage-0-intake.html` |
| 1 改編 | 小說目錄清洗（`extract_chapter.py`）、**角色設定 v4 十一大章節**（`validate_character_bible.py`）、保留分級、**事件交代完整性**（`event_coverage.py`）、段落架構（預設長篇不分集） | `adapt/character-bible.md`、故事地圖、`series-outline` | `review/stage-1-adaptation.html` |
| 2 資產與設定圖 | 故事聖經→`assets.md`、**生圖工具詢問推薦（Codex CLI）與跨章節鎖定**、**生物純底設定圖**、**演員表主角優先排序** | `assets.md`、`images/` 設定板、**缺圖紅框攔截** | `review/stage-2-assets.html`（表格與圖片左右並排對照） |
| 3 漫劇劇本 | 場景化改寫、時長與台詞預算審計（`estimate_duration.py --h3`）、HTML 註解元數據注入、交接 JSON、人工審核鎖（`sync_script.py`） | `script-ep01.md`、`handoff-ep01.json`、`adaptation-diff.md` | `review/stage-3-script.html` |
| 4 導演分鏡 | 依內容編排分段、焦距物距與動作；需要構圖審核時可用 Qwen 分鏡總覽圖、手繪或其他圖像工具 | `layer2/*.json`、`storyboard-ep01.md`、選用的對應 PNG | `review/stage-4-storyboard.html`（進 H3 編譯前需對應圖與人工核准） |
| 5 提示詞包 | **逐鏡親手寫五小節（Layer 2 `five_part_en`，規範見 `references/prompt-authoring.md`）**→ **H3 官方六段式批次編譯（`compile_layer2_to_h3.py`，含分鏡總覽圖門禁檢查）**、服裝狀態機解析、LoRA 精確適配、`--check` 雙重對帳＋逐鏡撰寫審查（E30–E38） | `prompts-ep01.md`、`segments-ep01.json` | `review/stage-5-prompts.html` |
| 6 生成（選用） | 僅在使用者要求且相容的影片工具／adapter 可用時生成；**審核頁為「影片 × 分鏡總覽圖 × 設定圖 × QA」四欄對照**（缺圖紅框不阻擋核准），QA 技術結果與人工核准分開；**收件後跑動態 QA（`h3d motion`）自動提案變速清單**（`references/speed-ramp.md`） | `videos/`、`qa-report.json`、`videos/speed-ramps.json` | `review/stage-6-videos.html` |
| 7 組裝（選用） | **短畫外句與短旁白由 H3 直接生成、長旁白走外部 TTS**（`--narration-policy short-offscreen-h3` 預設；`external` 全部外部化），**畫內對白保留 H3 口型**；**TTS 引擎由 `tts_doctor.py` 盤點後選擇**（`--tts-engine`／`--tts-config`）；整片 `loudnorm` 對齊 EBU R128；**已核准的變速段用 `videos/ramped/`，字幕／旁白／配音依 `time_map` 換算** | `final/`、`narration-ep01.md`、compiled segments 匯出的有效時間線 | `review/stage-7-final.html` |

**詳細做法、每階段模板與檢查點見 `references/pipeline.md`。** 正式階段核准以 `review/project-state.json` 為準；純文字草稿可按指定範圍交付，無需自動推進到媒體生成。

### 建議專案結構

```
<專案名>/
├── project.md              # 定調 + 成片形式 + 事件清單／段落規劃
├── source/                 # 專案原稿；送往外部工具時依工具資料處理方式確認
├── adapt/                  # 改編中間產物（character-bible.md、source.json、bible.json、故事地圖）
├── assets.md               # 風格錨 + 角色 / 場景 / 道具 / 音色聖經（ID、固定片段）
├── script-ep01.md          # 漫劇劇本（△ 場號制，無攝影機術語）
├── handoff-ep01.json       # 劇本→分鏡交接
├── adaptation-diff.md      # 改編差異對帳
├── layer2/                 # 分鏡 Layer 2 JSON（機器可讀 SSoT）
├── storyboard-ep01.md      # 分鏡表（人可讀）
├── prompts-ep01.md         # 逐鏡圖像 / 影片提示詞
├── segments-ep01.json       # FreeVideo 批次分段檔（H3 官方六段式結構）
├── panels/                 # Qwen 單格黑白鉛筆手繪草圖（panel-*.png）
├── keyframes/              # Qwen 轉繪全彩關鍵幀首幀（選用實驗，keyframe-*.png）
├── narration-ep01.md       # 旁白與字幕稿
├── timeline-ep01.csv       # 剪輯時間線
├── images/                 # 生成圖（設定板、場景主圖、分鏡總覽圖 grid-*.png）
├── videos/                 # 生成影片片段與審查報告
└── review/                 # 八階段 Cinema Editorial Studio HTML 審核頁面與狀態檔
    ├── project-state.json  # 狀態機 SSoT
    ├── stage-0-intake.html
    ├── stage-1-adaptation.html
    ├── stage-2-assets.html
    ├── stage-3-script.html
    ├── stage-4-storyboard.html
    ├── stage-5-prompts.html
    ├── stage-6-videos.html
    └── stage-7-final.html
```

用 `scripts/init_project.py` 一鍵建立骨架（自動初始化 `adapt/source.json`、`adapt/bible.json` 與 `project.md` 門禁欄位）。

---

## 階段 6 生成：怎麼做才穩

以下 Ref2VA／FreeVideo 做法來自特定 H3 專案與 adapter 實測，供相似環境參考；生成模式、參考圖限制與節奏依目標模型、當前 adapter 及使用者指定調整。本文的 Ref2VA CLI 本身輸出 H3 Ref2VA 格式，不代表其他工具都支援相同輸入。

**6.0 先確認工具（不可跳過）**

只有使用者要求影片生成時才確認可用工具。沿用已提供的模型與參數；只詢問會阻礙當前生成工作的缺項。FreeVideo 是可選 adapter，並非 Agent 普遍內建的影片能力。

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
- **❌ 已驗證失敗／⚠️ 尚未驗證（重要警示）**：**「用外部圖片模型（GPT Image / Qwen-Image）先生成彩色首幀再送 H3 I2VA」混在純 Ref2VA 片段中已驗證失敗**，因為兩個引擎兩種畫風，會造成嚴重畫風割裂（使用者亦明確不採用「先用 Qwen-Image-Edit 做 still 再進 H3」）。若要嘗試首幀流程，必須「整部片全部統一用同一個圖片模型生首幀」或「先與既有 H3 片段並排對照畫風通過」，嚴禁單看首幀漂亮就誤判成功！因此階段 6 的 `--to-color-keyframe` 標註為「⚠️ 選用實驗功能（需全片統一畫風並排驗證）」，而將 Qwen 黑白鉛筆分鏡總覽圖定位為「✅ 階段 4 視覺化構圖與佔位審核工具」。

#### 定案 3【參考圖張數與角色平均化現象】
> **使用者原話**：「這可能跟提示詞品質、以及 FreeVideo 模型訓練有關，走量化版模型可能就能多參考，之後可以嘗試」
- **實測現象**：單段同時掛多張體型相近的角色設定圖（如三個年輕男學生）會被 H3 平均融合成同一張臉；視覺特徵差異極大者（如胖子＋黑框眼鏡）能存活。
- **建議做法**：**保守預設為「一段一張角色參考圖」（要拍 4 個人的反應就拆成 4 段特寫）**；群戲需要時可給到 1 場景 + 最多 5 角色 = 6 張，但需注意融合風險（留待量化版模型再試，不寫成死規則）。
- **強制程式對帳（P0）**：`reference_images` ↔ `subject_definitions` ↔ `retention_analysis` ↔ 說話者 `(Sx)` 必須由同一支程式（`audit_refs_and_segments.py`）一次產生並逐條稽核。
- **✅ 單人裁切（單一可辨識臉）已於《噩盡島》第一章驗收通過**：一段**最多 1 張場景母版 + 1 張人物單人身份裁切**；其餘角色留在畫面但**不給參考圖**，改以文字描述為背影／近景肩背／頸部以下／畫面邊緣／畫外。可辨識臉超過一位時，H3 會把不同角色平均成同一張臉（混臉）。
  - **「單人身份裁切」定義**：2560×1440 四視圖角色板的**左側頭部特寫格**，裁切 `(0, 0, 950, 910)`。已實測與 FreeVideo media API 產出的裁切**像素完全相同**。
  - **程式化落地（階段 5 綁定檔）**：`video-bindings.json` 每個 shot 支援 `face_subject_ids`（該鏡真正露臉、可讀的角色）與選填 `crop_note_en`（其餘角色如何被裁掉的具體描述）。`compile_layer2_to_h3.py` 據此只為 `face_subject_ids` 掛角色參考圖，其餘可見角色降級為純文字次要主體，並在 `retention_analysis` 寫出「誰是唯一可辨識的臉 + 裁切說明」。未宣告 `face_subject_ids` 的舊綁定維持原行為（可見角色全部掛圖），以便相容既有專案。
  - **宣告多於一張可辨識人臉時**，編譯器會寫入混臉風險警告，不靜默放行。

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
- **台詞預算（v2，事件測試 V1 驗證；出處見 `references/pacing-dialogue-evidence.md`）**：估時依角色：**男主 4.0、女角 4.5、旁白／畫外 5.5 字／秒**（正臉對嘴 ≤4.7），單句建議 ≤18 字、硬上限 35 字，同場兩句空隙 **0.1–0.9 秒**（情緒落點 `beat_pause` 0.6–1.2 秒）、切鏡後 0.5 秒內開口（換場／反轉／情緒落點才留 ≥1 秒），文戲說話佔片長目標 60–75%（>80% WARN）、動作戲 ≤40%；對話段整段密度（字數÷片長）目標 3.0–3.6 字／秒，<2.8 或 >3.9 WARN；每 15 秒開口 <6 次 WARN；無台詞鏡 >5 秒、連續無台詞 >10 秒 WARN。**硬門禁**：句間 >1.5 秒、單句 >35 字、提示詞含 `slow` → FAIL（`pacing_gate.py`）。提示詞保留動作鏈＋逐句時間錨點寫法；猛烈動作拍不排台詞（喘息放 `overall_soundscape`）。
- **動作力學三要素**：分鏡表「動作」欄必填 **① 施力點（從哪發起）→ ② 傳導路徑（經身體哪裡、肌肉/鱗片變形與重量轉移）→ ③ 受擊反應與環境反饋（退後距離、結構折疊、立刻反擊、揚塵/塵環/風切位移空氣）**。

---

### 6.1 生成操作流

1. **分鏡 Layer 2 鎖定與分段表審核**：每段 7–10 秒，確定四大連戲錨點與收尾交接格。
2. **構圖分鏡總覽圖（✅ 構圖審核工具）**：預設先跑 `python scripts/h3d.py sketch --root <專案> --episode EPxx`（免生圖 SVG 構圖，見 `references/storyboard/svg-rig-grid.md`；跑完若印「⚠ 方向」先修 staging 或 Layer 2）；需要光影與細節時再用 Qwen 鉛筆草圖：執行 `qwen_storyboard_grid.py` 輸出 分鏡總覽圖黑白構圖，審核走位與滅點，單格有問題以 `patch_shot.py` 搭配 `--redraw-shot` 重抽，通過者鎖定保護。
3. **出資產設定圖**：角色設定板、場景主圖、**生物/怪獸純色三視圖（Creature Sheet，嚴禁帶背景劇照）**，過驗收門。
4. **【主力定案】獨立 Ref2VA 影片生成**：每段獨立給予對應的場景與角色圖，嚴禁尾幀續接；以 `audit_refs_and_segments.py` 跑通 P0 程式對帳。
5. **【⚠️ 選用實驗功能】Qwen 轉繪全彩首幀 + I2VA**：若要採用首幀流程，**必須整部片統一使用同一圖片模型生成首幀**，並先與已生成的 H3 片段**並排對照畫風無割裂感**後，方可送 I2VA。
6. **`verify_video_shot.py` 自動審查**：審驗時長、彩度防黑白污染、分鏡總覽圖殘留與相鄰色盤連貫性。

---

## 階段 7 組裝交付與配音決策

### 7.1 配音分層決策（新增重要規範）
H3 的聲音與畫面在同一次 forward 生成，輸出是**單一 32 kHz 立體聲混音軌，沒有分軌，也沒有關閉音訊的參數**；H3 內建中文語音實測 ASR 置信度只有 0.43–0.54【社群實測】。因此本專案的規則是：
- **短畫外句與旁白留 H3，長句才外部 TTS**：`--narration-policy short-offscreen-h3`（預設）把約 ≤15 字的畫外句（O.S.）與旁白（V.O.）用官方句式＋逐字 `<d>` 交給 H3（聲線放 `<d>` 外、露臉者嘴閉合、無臉寫 `no face is on screen`）；長句或需跨段統一聲線的句子移出 `<d>`、於階段 7 由外部 TTS 混入（`external` 政策則全部外部化）。限制：同說話者跨段聲線可能不一致（未量測）、H3 念的句子事後改稿要重跑整段。句式與門禁見 `references/pipeline.md` §5.4。
- **畫內有可見嘴的對白保留 H3 內建語音**：`<d>` 標籤留作生成時嘴部開合與時間點的物理錨點；**掛上音色母帶（`<Audio N>`）時，H3 會照母帶音色重新合成**（本機 FreeVideo 送得進音訊參考，但官方只保證「參考音色與語氣」，不鎖輸出音軌與口型）；要每段完全一致或更清晰的聲音時，再用外部 TTS 覆蓋並補 lipsync。
- **TTS 引擎由 `tts_doctor.py` 盤點後選擇**（`--tts-engine`）：本機 VoiceStudio／OmniVoice 為預設，另有 Fish Audio 與自帶 OpenAI 相容 API；`edge-tts` 自 2026-10-10 起 403 且非商用，只留離線除錯。
- **TTS 先行（v2）**：MiniMax Speech `speed` 預設 **1.1**（急的角色 1.15–1.2、長輩 1.0），先產音、量實長，鏡頭長＝語音實長＋0.3 秒（**不再 ×1.2**）再生成；整體超過 1.25 倍仍放不下就改寫台詞，避免旁白比鏡頭長而白跑一次 render。
- 完整決策表、混音鏈與響度交付標準（EBU R128 / ATSC A/85 / Netflix）見 `references/pipeline.md` §7。

### 7.2 後期交付檔案
- **旁白與字幕稿**（`narration-ep01.md`）：時間碼對齊。
- **剪輯時間線**（`timeline-ep01.csv`）：由 `layer2_to_table.py --timeline` 產生。
- **拼接成片**：使用 ffmpeg 拼接影片片段、燒錄字幕與混音，整片再套 `loudnorm` 對齊 EBU R128（−23 LUFS／−1.5 dBTP）。
- **交付清單**：列出已生成檔案、未完成鏡號。

### 7.3 剪輯技巧與剪輯 lens（只給建議）
- **技巧手冊**：`references/edit/manju-editing-playbook.md`——前 3 秒鉤子、鏡長與卡點、轉場紀律（硬切 ≥ 85%）、打擊感四件套（閃白／速度線／震屏／音效提前 1 幀）、靜圖運鏡與分層視差、字幕硬規則（≤ 15 字、≤ 9 字/秒、9:16 安全框）、角色專屬字幕色、角色登場介紹卡、調色、三層音效、配樂 ducking（6–12 dB）、片頭片尾、響度與匯出規格；每項附剪映對應功能與已實測的 ffmpeg 寫法。
- **剪輯 lens**：草剪或成片出來後跑 `python scripts/craft/edit_review.py --project-dir . --episode EP01 [--lens murch-cut|hamilton-action] [--video final/ep01_final.mp4]`，報告寫 `review/craft/stage-7-edit-ep01.md`；Agent 讀 `references/craft/murch-cut/SKILL.md`（剪點、念頭斷點、最後一格、聲音密度、留白）與 `references/craft/hamilton-action/SKILL.md`（觀眾跟得上、先壓再放 air、先裸剪再讓聲音說故事、蓄力、試映迭代）補「Agent 審查」段。不改任何門禁。
- **響度**：豎屏串流成片建議 −14～−16 LUFS、TP ≤ −1 dBTP；送審母帶另出 EBU −23（`assemble_episode.py --target-lufs`）。哪個當交付預設由使用者決定。
- **剪映草稿路線（未實作，調查見 `references/edit/concat-and-jianying-drafts.md`）**：Concat（jub0t/Concat，AGPL-3.0）是自有格式的獨立剪輯器，不讀寫剪映草稿；要交給剪映人工精修，可從 `edit/full-plan.json` 用 pyJianYingDraft（Apache-2.0）寫 `draft_info.json`，需家機實測剪映版本。

---

## 資源

- `references/tooling.md` — **產線工具（`h3d`）與四道確定性檢查**：一個入口、時長量子（17n+5）、證據分級（VERIFIED／PARTIAL／UNVERIFIED 與階段 6 閘門）、segment 級依賴帳本（`deps --record／--status`）、失敗目錄與 ack 憑證流程、provider 能力表、常見錯誤訊息 → 處置。**跑任何指令前先讀這頁。**
- `references/pipeline.md` — 八階段詳細流程、提問清單與各階段模板；階段 7 含聲音三層決策（畫內對白／畫外音／全片外部聲景）、配音先行與時長對軸、TTS 引擎盤點與混音響度交付標準（EBU R128 / ATSC A/85 / Netflix）。
- `references/adapt/` — **小說改編（階段 1、3）**：`novel-to-manju.md` 為總規範（10 階段、6 題材模式、四道退稿閘門、100 分制），其餘為原則、故事聖經、結構節奏、劇本格式、視覺寫作、對白、可拍性、分鏡交接、授權證據各篇，`templates/` 含交接 JSON Schema。腳本在 `scripts/adapt/`（附 10 個測試案例）。
- `references/storyboard/` — **導演分鏡（階段 4）**：`cinematic-director.md` 為總規範（v2.0），含三步法、焦距物距光學、漫劇分鏡總覽圖與連戲狀態機、武戲 90° 與多模型編譯；`combat-and-vfx-library.md`（高階武戲連招、玄幻大招五段鏈與 11 大戰場拓撲）；`acting-and-emotion-library.md`（邁斯納行為表演法、言行反差、10 大景別句型與 4D 配音）；`svg-rig-grid.md`（免生圖 SVG 構圖分鏡總覽圖）；`templates/` 含 Layer 2 JSON Schema。腳本在 `scripts/storyboard/`。
- `references/consistency.md` — **資產與一致性規範**：ID、角色設定板（洋子鎖臉規範）、生物怪獸三視圖規範、場景、道具、**音色鎖雙軌（`V-<slug>` ＋ 外部 TTS 固定聲線）**、多模態素材職責表（含**整板查表模式** `reference_view: "panel"` ＋ `panel_label_en`）、複製人防線三定律與門禁對照（E19–E27）、漂移偵測與修復、驗收門、待驗證清單。階段 2、6 必讀。
- `references/styles.md` — **漫劇風格鎖定錨**：十餘種主流風格的錨定詞、負面錨、色盤與同角色樣圖。階段 0 選風格時讀。
- `references/freevideo.md` — **建議搭配 FreeVideo**：連線步驟、規則、與八階段的對應。階段 6 先讀這份。
- `references/model-profiles.md` — **生成前必問清單**，以及各圖像／影片模型的提示詞風格對照與改寫流程。
- `references/minimax-h3.md` — **MiniMax H3 專章（入口）**：規格、五種模式、預算表、十條速查、Red Flags、負面轉正面詞表、8GB 顯存 OOM 拆段公式、Windows 工程坑速查（1–11，含多視圖板的宣告式例外）、官方 Ref2VA 格式合規速查（含**音色參考 `<Audio N>`**）。用 H3 前必讀。
- `references/h3/` — H3 細部參考（同步自上游 [h3-video-prompting](https://github.com/ayase0307/h3-video-prompting) 的 `references/`，釘在 commit `1db923b`（2026-10-21），紀錄在 `references/h3/UPSTREAM.json`；本專案另加 `lora-guide.md`、`scenarios-people.md` 有三處標註。漂移檢查：`python scripts/sync_h3_reference.py --check`，CI 由 `tests/test_h3_reference_sync.py` 守）：
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
- `scripts/storyboard/compile_layer2_to_h3.py` — Layer 2 批次編譯為 H3 官方六段式提示詞（`prompts-epXX.md`）與 FreeVideo 批次分段檔（`segments-epXX.json`），支援防混臉參考圖排序（一段一張角色圖）、切點時間軸保護（$D - \text{末切點} \ge 2.05s$）、光源名詞映射、官方運鏡詞微交替、LoRA 自動適配、`--narration-policy external`（畫外音／旁白移出 `<d>`、寫入 `external_narration` 與 `speaker_ids`）與 `--check` 雙重對帳。stage5 綁定檔支援 `identity_anchor_ids`（不露臉身份錨點）、`reference_view: "panel"` ＋ `panel_label_en`（**整板查表模式**，缺格位說明即丟 `ValueError`）、`audio_references`（**音色參考 `<Audio N>`** ＋ 固定描述詞 `voice_4d_spec_en`）。
- `scripts/storyboard/audit_refs_and_segments.py` — 分段參考圖、主體定義、說話者與字數預算多維程式對帳工具（支援雙重審查：模式 A 序對 + 模式 B 17 條自檢）。
- `scripts/storyboard/patch_shot.py` — 單鏡局部修改與審核鎖定工具（支援秒數吸收、自動重算時間軸）。
- `scripts/storyboard/svg_storyboard_grid.py` — 免生圖 SVG 構圖分鏡總覽圖（2.5D 相機＋3D 人偶，依景別取景、過肩貼肩、依 180 度線換算左右；回寫 `sketch_file`／`sketch_sha256`／`sketch_generation.grid_file`；鎖定格不覆蓋；外觀與站位走專案 `staging/`，動作關鍵字走 `svg_rig_actions.json`）。選用依賴 numpy、resvg-py。
- `scripts/storyboard/codex_storyboard_panels.py` — Codex CLI 內建生圖的彩色分鏡圖（每鏡一張、每段總覽圖），自動綁定已核准參考圖（角色正面裁切、異獸設定圖、場景母版，依序為 <Picture N>），`--model` 必填；角色關鍵字／逐鏡覆寫放 `staging/codex-panel-refs.json`；輸出與回寫契約同 SVG 構圖（backend=codex）。使用者指定「分鏡圖用 Codex」時走這條。
- `scripts/storyboard/qwen_storyboard_grid.py` — Qwen-Image 2.1 電影分鏡鉛筆草圖、單格局部重繪、分鏡總覽圖拼版與去黑箭頭轉全彩首幀工具。
- `scripts/storyboard/submit_h3_segments.py` — 階段 6 FreeVideo H3 批次提交與顯存保護工具（4.20 GiB 顯存臨界點安全保護、不足時差額診斷、--dry-run 乾跑檢查、參考圖 SHA256 快取、音色母帶（音訊參考）上傳與副檔名檢查、LoRA 自動適配與任務輪詢下載）。
- `scripts/storyboard/verify_video_shot.py` — AI 影片自動審查與分鏡規格差異檢驗門禁工具（分段總時長精確對齊、彩度防黑白污染、分屏殘留、串聯 `color_qa.py` 輸出 `qa-report.json`）。
- `scripts/storyboard/tts_engine.py` — 可插拔 TTS 後端封裝（標準函式庫）：本機 VoiceStudio／OmniVoice voicebox API、Fish Audio（雲端／本機）、自帶 OpenAI 相容 API、Windows SAPI、edge-tts（僅除錯）。音色解析（`voice` → `voice_map` → speaker → `default_profile`）在任何供應商呼叫前完成，產出一律正規化成 48 kHz 單聲道 WAV，失敗不留半成品，金鑰只從 `api_key`／`api_key_env` 讀取且永不外洩（錯誤訊息遮罩為 `***REDACTED***`）。
- `scripts/storyboard/tts_doctor.py` — TTS 能力**唯讀**盤點工具（`python scripts/storyboard/tts_doctor.py`、`--json`）：ffmpeg／ffprobe、設定檔與 `voice_map`、各引擎可用性與具體下一步、VoiceStudio `/health` 摘要、GPU／VRAM 衝突警告、edge-tts 棄用提醒、Fish Audio 授權提醒、建議的 `--tts-engine`；不寫檔、不上傳、不呼叫生成端點、不印金鑰。
- `scripts/storyboard/extract_voice_master.py` — 角色音色母帶（`V-<slug>`）產出工具：`--list` 列出可當母帶的畫內台詞（2–15 秒），再依 Layer 2 的 `speech_window` 從已生成影片切出該句、輸出 48 kHz 單聲道 WAV 與 `.provenance.json` 稽核紀錄，並印出可貼進 stage5 綁定檔的 `audio_references` 片段；母帶是「第一次出場那一句」，之後所有段落掛同一條 `<Audio N>` 達成跨段同聲。
- `scripts/storyboard/assemble_episode.py` — 階段 7 配音分層、字幕燒錄與成片拼接交付工具（`--audio-mode auto` 逐段裁決：畫內對白留 H3 口型、外部化旁白混外部 TTS；`--tts-engine`／`--tts-config` 選引擎與設定；`adelay ...:all=1`＋`amix ...:normalize=0` 分層混音、每軌 48 kHz；整片 `loudnorm`（`--target-lufs`／`--true-peak`／`--lra`）對齊 EBU R128；Windows 字幕冒號轉義；FFmpeg Concat 無縫拼接成片，附 `--self-test`）。
- `scripts/storyboard/layer2_to_table.py` — Layer 2 → 人可讀 Markdown 分鏡表與時間線 CSV 匯出工具。
- `scripts/storyboard/validate_storyboard.py` — 分鏡 Layer 2 JSON 靜態驗證工具。
- `scripts/storyboard/director_storyboard_assistant.py` — 預設配置與多模型提示詞編譯輔助工具。
- `scripts/color_qa.py` — 跨鏡頭色彩一致性檢查（同步自上游，用法見 `references/h3/lighting-and-color.md`）。

