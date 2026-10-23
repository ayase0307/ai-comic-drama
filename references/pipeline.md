# 八階段詳細流程

依使用者指定的交付範圍選擇階段；只要文字劇本、分鏡或提示詞時，可停在該階段並交付 draft，不要求圖片或影片生成。小說改編依使用者要求進入改編流程，不把完整八階段當成每項任務的必經步驟。

文字規劃、Python 本機檢查、圖片生成與影片生成是不同能力層。先以 `python scripts/check_environment.py` 檢查本機工具；`python scripts/run_offline_checks.py` 執行離線檢查。這些命令不檢查 provider 帳戶、token 或模型生成能力。FreeVideo 是可選 adapter，影片生成要以當前 Agent 或已連線後端實際可用為準。

階段狀態只記錄於 `review/project-state.json`，每次核准綁定輸入 hash，修改後必須重審。stage 4 review 核准是 H3 compiler 前置條件；實際 submit 要求 stage 5 核准。QA 技術通過不會自動成為人工核准。

---

## 階段 0：定調（Intake）

只詢問當前交付所缺少且會阻礙工作的項目；沿用使用者已給的 brief、模型與參數，不重複詢問。純文本或分鏡交付不要求先收齊出片參數。

| 項目 | 選項／說明 |
|---|---|
| 集數與每集時長 | 單集 60–120 秒最常見；小說改編預設 90–120 秒。**秒數是預估起點、不是硬上限**：集數依因果單元（目標／阻礙／選擇／代價／鉤子）切，每集可在目標 ±15% 內視為正常；超出時走「接受（寫入 `accepted_duration_seconds`）／於場次邊界拆集／刪非因果內容」三選一，不用壓縮分鏡硬塞 |
| 原稿類型與用途 | 小說／網文／故事梗概／已有劇本；依當前任務確認需要的來源與處理方式 |
| `genre_mode` | `xuanhuan_revenge`／`romance_emotional`／`mystery_thriller`／`comedy_slice_of_life`／`wuxia_action`／`healing_literary` |
| `target_medium` | `motion_comic` 動態漫／`ai_animation` AI 動畫漫劇／`live_action_short_drama` 真人短劇 |
| 畫風 | **預設推 14 號「古風寫實厚塗・電影感」（`xianxia-cinematic-semireal`，附樣圖）**，使用者可改選 `references/styles.md` 任一套（整部只用一套）；角色設定板選項 `xianxia-cinematic-semireal`／`master`（3D 漫劇寫實厚塗）／`semi-real`（UE5 半寫實）／styles 編號，寫入 `assets.md` 的 `style_index`，並 `h3d decide style` 定案 |
| `aspect_ratio` | 9:16（預設）／16:9／1:1 |
| 語言與聲音形式 | 旁白解說／角色對白／混合／默片字幕 |
| 台詞政策（需要改寫或估算時） | `① 原文逐字保留` / `② 只留重點句` / `③ 影視化改寫` / `④ 無台詞純旁白`；已在 brief 中交代則沿用 |
| 交付深度 | 只到分鏡／到設定圖／到分鏡圖／到影片 |

### 階段 0 按需求選用的台詞與體量檢查

1. **台詞政策（只在當前改編需要決策時）**：
   - 區分「外部框架規則」與「使用者真實需求」；沿用已給政策，不重複詢問。若台詞政策缺失且會影響改編，才詢問：
     - `① 原文逐字保留`：忠於原著字句，但需嚴格遵守下述片長與氣口順延；
     - `② 只留重點句，其餘可刪（推薦）`：去蕪存菁，留下推動情節之戲劇金句，大幅提升成片節奏；
     - `③ 全部改寫為影視對白`：重構為影視化口語短句；
     - `④ 無台詞純旁白`：角色閉唇不語，靠畫面與解說推進。
2. **原文體量反推片長公式（先算再動工）**：
   - 實測中文口播極限安全值為 **4 字／秒**（常速 3.8 字/秒）：
     $$\text{純念台詞秒數} = \frac{\text{台詞字數}}{4}$$
     $$\text{總片長估算} \approx \text{純念台詞秒數} \times 1.6 \quad \text{（含動作反應、氣口與鏡頭呼吸）}$$
   - **命令列確定性試算**：
     ```bash
     python scripts/adapt/estimate_duration.py --novel --novel-file source/ch01.txt --target-seconds 90
     ```
     該命令使用 Unicode P 類別統一排除標點符號，精確統計有效漢字數，並一次輸出四大台詞政策下的預估片長、壓縮比與分集建議。
   - **體量提示**：需要長度估算時，可用估算結果提示拆分、精簡或保留原文等選項；不把單一工作流的數值門檻套用到所有任務。缺少會影響當前目標的選擇時再詢問。
     - **方案 A（改編壓縮）**：採用台詞政策 ②，大刀改編壓縮原著台詞至目標容量；
     - **方案 B（拆集推進）**：將當前場次拆分為多集或上下篇製作；
     - **方案 C（接受片長）**：使用者調高目標時長預算，接受成片大幅拉長。
3. **工作紀律鐵律**：
   - 生成任務先確認交付、當前可用後端與需要的參數；沒有生成要求時停在文字交付。

**一鍵初始化骨架**：
```bash
python scripts/init_project.py my-drama --title "我的漫劇" --episodes 12
```
一鍵自動建立完整專案目錄，並產生包含台詞政策門禁與體量秒數反推欄位的 `project.md`，以及 `adapt/source.json`、`adapt/bible.json` 等初始規格骨架。

---

## 階段 1：改編（小說 → 可拍的漫劇結構與角色設定 v4）

**原稿是小說時必走。** 規範全文：`references/adapt/novel-to-manju.md`（對應其 Phase 0–5）。做什麼：

0. **小說大檔目錄掃描與單章清洗抽取（`extract_chapter.py`）**：
   - 若原稿為整本長篇小說大檔（幾十萬至百萬字），先掃描章節目錄結構：
     ```bash
     python scripts/adapt/extract_chapter.py --input source/novel.txt --list
     ```
   - 精確抽取指定卷指定章，並自動執行 Pandoc 6 重清洗（移除 Gutenberg/版權頁眉頁腳、統一破折號與省略號、縮進清理、空行壓縮、繁簡標點正規化與標題抽取）：
     ```bash
     python scripts/adapt/extract_chapter.py --input source/novel.txt --volume 1 --chapter 1 --output source/ch01.txt
     ```
1. **《完整角色設定文件 v4.0》（P0 強制門禁，對標《反派擺爛指南》）**：
   - 在改寫劇本前，**必須先產出詳細角色設定 `adapt/character-bible.md`**，包含完整十一大章節：
     - 一、角色總覽
     - 二、核心角色（基本資料、外貌、武器/隨身道具、表深層性格、核心能力與戰力、人物弧光與命運走勢、角色金句）
     - 三、重要配角
     - 四、功能性角色與異獸生物設定（純底三視圖規格）
     - 五、背景角色與路人收斂策略（嚴禁無圖路人單獨佔據中近景）
     - 六、角色關係圖（ASCII/Mermaid 網絡）
     - 七、角色狀態與能力演進表
     - 八、角色戲劇與喜劇功能分配
     - 九、角色命名與視覺象徵邏輯（**跨章節真名查證，嚴禁自創英文假名如 `BrownHairSlayer`**）
     - 十、角色登場章節與場次服裝索引（**服裝狀態機 `wardrobe_states`**）
     - 附錄：角色設定速查表
   - **原著行號依據**：所有外貌、武器、年齡與能力描述必須附帶 `(Lxxx)` 行號依據，非原著內容標註 `【改編新增】`。
   - **確定性驗證器**：
     ```bash
     python scripts/adapt/validate_character_bible.py --bible adapt/character-bible.md --json adapt/bible.json
     ```
   - **產出階段 1 HTML 審核頁並停下**：
     ```bash
     python scripts/build_stage_review.py --stage 1
     ```
     Agent 必須主動停下，提示使用者查閱 `review/stage-1-adapt.html`，取得核准後才可進入階段 2！
2. **全文解析與故事地圖**：logline、主衝突、因果鏈、時間線、人物關係、世界規則、伏筆、原著內部矛盾（列出，不私自掩蓋）。長篇分批讀，不假裝讀完沒看過的章節。模板 `adapt/templates/source-analysis.md`。
3. **保留分級**：每個事件標 `MUST_KEEP`／`KEEP_IF_POSSIBLE`／`MERGE`／`COMPRESS`／`REMOVE`／`REORDER`，記原文引用與理由。
4. **A／B／C 三方案停靠**：忠於原著／節奏優先／成本優先，比較後推薦，**交使用者選**。
5. **分集架構**：`Arc → Episode → Sequence → Scene → Beat`；每集寫目標、阻礙、選擇、變化、結果、下集動機與因果債務。模板 `series-outline.md`、`episode-outline.md`。
6. **單章拆多集跨集驗收**：原著單章往往需要拆編為多集漫劇（如 1 章拆為 Ep01–Ep03），支援單集驗收與多集合併全章驗收：
   ```bash
   # 單集過濾驗收：
   python scripts/adapt/compare_adaptation.py --source adapt/source.json --script script-ep01.md --handoff handoff-ep01.json --episode 1 --h3
   # 多集多檔合併總體驗收：
   python scripts/adapt/compare_adaptation.py --source adapt/source.json --script script-ep01.md script-ep02.md --handoff handoff-ep01.json handoff-ep02.json --h3
   ```

**產出兩份 JSON 供階段 3 驗證使用**：`source.json`（原著事件與保留分級，格式見 `scripts/adapt/tests/fixtures/*/source.json`）與階段 2 的 `bible.json`（故事聖經，格式見 `scripts/adapt/tests/fixtures/story_bible.json`）。

**檢查點**：使用者選定方案、確認分集表才往下。題材細則看 `adapt/genre-modes.md`，結構節奏看 `adapt/structure-and-pacing.md`。原稿已是劇本、或是原創梗概時，跳過 1–2 步，直接做分集。

---

## 階段 2：資產聖經與設定圖（左右並排審核斷點）

一致性的根基。規範全文：**`references/consistency.md`**（ID、設定板版面、表情集、服裝、場景主圖、道具、音色、參考鏈、驗收門）。

1. 用小說改編技能的**故事聖經**（`adapt/character-and-world-bible.md`、`templates/story-bible.md`）當角色資料來源；改編新增設定標【改編新增】。
2. 寫 `assets.md`：先寫全域鎖（風格錨、負面錨、光色句、五色色票），再寫角色／服裝／場景／道具／音色條目，每條有 ID 與固定描述片段。
3. **非人生物／怪獸設定圖（Creature Sheet）規格升級（實戰教訓）**：
   - 奇幻、玄幻或科幻中的巨獸、妖物、坐騎（如巨蟒、白獸、魔狼）享有與人類角色同等的規格。
   - **必須生成純灰/純白單色背景的三視圖**（左側頭部特寫／右側全身姿態／皮膚花紋鱗片細節）。
   - **⛔ 嚴禁拿帶場景背景的劇照或畫作當生物參考圖**！實測證明，帶背景的生物參考圖會把背景巷子、森林殘留強行染色並黏著帶進成片的所有其他場次，破壞空間一致性。
4. **演員表排序鐵律（實戰教訓）**：
   - 填寫每段分鏡與提示詞的演員表時，**嚴格按「這一場誰是主角/核心」排序**，而非按誰先想到或人類先於生物。
   - 生物（巨蟒、白獸等）在誕生、威脅或主戰場次往往是核心，必須排在第一位（`subject 1`），避免被 H3 參考圖上限或注意力機制稀釋擠掉。
5. **核心資產生圖工具詢問與跨章節鎖定鐵律**：
   - **詢問指定工具（推薦 Codex CLI）**：在出核心資產圖前，必須詢問使用者指定生圖工具（推薦本機 Codex CLI 或使用者授權之工具）。
   - **跨章節工具選擇**：若使用者要求跨章節風格一致，記錄已選工具及可重用的風格參考；依每個工具實際能力安排工作，不強制使用特定引擎。
   - Qwen、手繪或其他可用圖像工具可依任務製作設定圖或分鏡構圖圖；同一張圖是否可用於後續生成依目標模型能力判斷。
6. **組裝角色設定板提示詞再生圖**：角色卡填好 `設定板描述`、`背面特徵`（`init_project.py` 範本已含），**問風格的方式（P0）**：依題材從 `references/styles.md`「角色設定板預設風格」的推薦挑 2–3 個，附上樣圖（`assets/styles/sheet-*.jpg`）與一句話差別，一次問一個問題；**全片風格鎖與設定板風格合併成同一個選擇**，不要分開問。預設推 14 號「古風寫實厚塗・電影感」；沒有選定時 `export_asset_prompts.py` 會用 14 號並在 stderr 提醒，開工前仍要讓使用者確認。
   **風格要在階段 0 與使用者確認後**寫進「風格錨點」區的 `style_index`：`14`／`xianxia-cinematic-semireal`（**預設**，古風寫實厚塗・電影感）／`master`（母版 3D 漫劇寫實厚塗，偏插畫感）／`semi-real`（UE5 半寫實東亞，更接近真人質感）／`1`–`11`（`styles.md` 編號）。沒寫時匯出用預設 14 號並提醒，開工前仍先問。選 14 號時每段都要綁設定圖或場景圖（audit E28）。然後：
   ```bash
   python scripts/storyboard/export_asset_prompts.py --assets-md assets.md --out-json images/asset_prompts.json --out-md images/asset_prompts.md
   python scripts/storyboard/run_codex_asset_gen.py --prompts images/asset_prompts.json --output-dir images
   ```
   角色提示詞用 ai-image-prompt 四視圖母版（構圖不改、含防呆句）；`--style <選項>` 可臨時覆蓋 `style_index`。舊版匯出檔（缺 `template` 標記）runner 會警告，需重跑匯出。
7. **產出階段 2 HTML 並排審核頁面與斷點停下（P0 鐵律）**：
   - 生成資產圖後，**必須執行**：
     ```bash
     python scripts/build_stage_review.py --stage 2
     ```
   - 產出 `review/stage-2-assets.html`：**左側展示角色設定表格（姓名、年齡、外貌、服裝、武器、原著行號依據），右側展示生成的設定圖（支援全螢幕 Lightbox 放大，缺圖紅框攔截警示）**。
   - **Agent 必須立即停下**，提示使用者打開 `review/stage-2-assets.html` 進行外貌與畫風審核，確認每位角色臉型、服裝無誤後，使用者發出明確核准指令方可進入階段 3！嚴禁未經確認私自往下推進！

---

## 階段 3：分集劇本（改寫成漫劇劇本）

規範：`adapt/screenplay-format.md`、`visual-writing.md`、`dialogue-and-audio.md`、`filmability-and-cost.md`（對應 Phase 6–9）。重點：

- **劇本管戲，分鏡管拍**：劇本用中文場號制（`第XX集｜標題`、`M-N 場景名 時/內外`、`人物：`、`△` 動作行、`角色名（括注）：對白`），**正文不出現攝影機術語**與模型提示詞。
- **100% 視聽外化**：心理活動轉成動作、道具、空間位階、言行不一；內心獨白 ≤ 單集對白行的 15%。
- 每場寫清「進場極性 → 衝突行動 → 資訊變化 → 出場極性」。單場核心互動角色預設 ≤ 3 人；多人混戰、複雜物理給「原版／AI 簡化」雙案。
- 對白單句 > 28 字警告、> 35 字阻斷（字幕可讀性）；整集時長與目標（或 `accepted_duration_seconds`）的偏差在審核頁「時長對帳」呈現；階段 3 就要核准偏差，不要拖到階段 4。
- 產出：`script-epNN.md`、`handoff-epNN.json`（符合 `adapt/templates/handoff.schema.json`）、`adaptation-diff.md`（改編差異對帳）。

**人工審核鎖與劇本雙向同步（`sync_script.py`）**：
- **從零自動建立或擴展**：若 handoff 不存在，直接執行一鍵從 Markdown 產生初始 handoff；新增場景自動識別併入。
- **HTML 註解元數據自動注入**：在劇本場景標題下方寫入 HTML 註解，同步時自動注入 handoff 的改編對帳元數據：
  ```markdown
  第1集｜噩夢初醒
  
  M-1 後山荒林 日/外
  <!-- source: U01, U02 -->
  <!-- must_keep: MK01 -->
  <!-- change: compress | U02 | 精簡原著長對白，強化動作打擊與巨蟒受擊反饋 -->
  人物：洛年、沈凡
  △ 狂風席捲，黑影破土而出。
  ```
- **註解寫法**：`source` / `must_keep` 只抽取 `U01`、`MK01` 這類 ID，其餘說明文字會被忽略；`change` 建議寫成 `類型 | 單元ID | 理由`，類型為 `must_keep`／`keep_if_possible`／`merge`／`compress`／`remove`／`reorder`／`addition`（與 handoff schema 一致）。只寫自由文字時，依關鍵字推斷類型（「合併」→ merge、「刪」→ remove…），但沒有單元 ID 就無法抵銷 `UNTRACKED_UNIT_OMISSION`，被合併或刪掉的單元請務必寫 ID。
- **多餘場景修剪（`--prune-extra`）**：若 Markdown 中刪除了未鎖定場景，加入 `--prune-extra` 自動自 handoff 移除同步。
- **審核鎖定防誤改**：
  ```bash
  python scripts/adapt/sync_script.py --handoff handoff-ep01.json --scene EP01-S01 --set-status approved --note "導演審核通過"
  ```
- **Markdown 修改同步回寫**（未鎖定場景自動增版更新，已鎖定場景自動攔截保護）：
  ```bash
  python scripts/adapt/sync_script.py --handoff handoff-ep01.json --script script-ep01.md --prune-extra
  # 若需強制解鎖再改：
  python scripts/adapt/sync_script.py --handoff handoff-ep01.json --scene EP01-S01 --unlock
  ```

**必跑驗證套件**（任一閘門觸發即退稿重寫，≥ 80 分且 0 閘門才過）：

```bash
# 1. 結構與格式校驗
python scripts/adapt/validate_structure.py --script script-ep01.md --handoff handoff-ep01.json

# 2. H3 實戰台詞預算與時長審計（4字/秒、單句≤15字警告、說話佔比≤60%警告）
python scripts/adapt/estimate_duration.py --script script-ep01.md --genre xuanhuan_revenge --target-seconds 90 --h3

# 3. 連戲與資產一致性檢查
python scripts/adapt/check_continuity.py --bible adapt/bible.json --handoff handoff-ep01.json

# 4. 改編差異與保留分級對帳（支援 --episode 與 --h3）
python scripts/adapt/compare_adaptation.py --source adapt/source.json --script script-ep01.md --handoff handoff-ep01.json --episode 1 --h3
```

---

## 階段 4：分鏡（導演分鏡體系與分段級編排）

規範全文：`references/storyboard/cinematic-director.md`（v2.0）。輸入是階段 3 的 `handoff-epNN.json` 與階段 2 的 `assets.md`。做什麼：

### 4.1 分段級分鏡（Segment-Level Storyboarding）與顆粒度轉換

> **【定案 1 核心引用】使用者原話**：  
> 「如果 15 秒塞不下就不要硬塞，**沒有一定要每個片段都 15 秒**，這個請列入重點，因為 15 秒對於人物/場景/佔位的保持度很考驗」

- **✅ 已驗證有效**：15 秒只是 H3 單次時長上限，絕不是創作單位。分段長度由「內容有幾個獨立節拍」決定，**每段建議 2–4 個節拍、7–10 秒**。
- **三層顆粒度轉換鏈**：
  1. **劇本微鏡**（剪輯單位，1–3 秒）：記錄純粹的戲劇動作與台詞氣口；
  2. **分段計畫表**（生成調度單位，每段 7–10 秒、2–3 鏡）：標明自足開場、連戲四大錨點與收尾交接格，**先交人類審核通過**；
  3. **H3 `[Shot N]`**（生成單位）：編譯為符合 H3 時間網格之 prompt。

### 4.2 鏡頭調度防禦性規範（避開 H3 弱項陷阱）

> **【定案 4 核心引用】使用者原話**：  
> 「應該要避免人物在遠景，這是 minimax h3 的弱項……應該要從分鏡面去解決，四人近距離呈現面部微表情，依照人物性格出現冷靜、驚訝、害怕、興奮等等的情緒，可以不用一定要呈現出四人看到蛇，全部都塞在一起的畫面」

1. **「一顆鏡頭一張臉」演反應**（✅ 已驗證有效）：近距離特寫（CU/MCU）呈現面部微表情，明確寫出眼、眉、嘴、下顎肌群變化。
2. **用「背影（不露臉）」演群戲走位與過場**（✅ 已驗證有效）：聽到聲音而回頭、集體站位與走向，用背影交代，完全避開遠景面部五官融化問題。
3. **⛔ 正面特寫段絕不要寫「遠處的那個東西」**：實測兩次均發現，特寫若描寫「遠處有巨蟒」，H3 會強行把巨蟒塞進角色肩後的景深中！地理環境由前導背影段建立，正面特寫純拍角色反應。
4. **巨獸/大型生物的巨大感交代手法**：利用景深邊緣失焦色塊、地面巨大投射長影、前景局部遮擋，或貼地近景拍局部（蛇頭衝鏡、蛇鱗碾過地面、纏住腳踝）。
5. **俯視佔位圖（Blocking Map）**：凡 3 人以上＋大型生物同場，分鏡前先畫一張俯視站位圖，標明機位、角色與朝向。

### 4.3 台詞字數預算與動作力學三要素

> **【定案 5 核心引用】使用者原話**：  
> （台詞）「這個台詞字數明顯超過秒數限制，變成加速講話，你應該要精簡台詞」  
> （動作）「蛇的動作明顯不足且不自然，像是玩具，比方說他被打應該要強烈掙扎及反抗、攻擊的時候要有環境特效（揚起灰塵或是風切等等），戰鬥要有強烈的打擊感及環境/視覺特效」

- **台詞預算鐵律**：
  - 語速上限 **4 字／秒**；單句 $\le 12\text{–}15$ 字；說話窗口 $\ge 2.5$ 秒；兩句間隔 $\ge 3$ 秒。
  - **總說話秒數 $\le$ 片長 60%**，猛烈動作碰撞鏡頭嚴禁排台詞（喘息放 `overall_soundscape`）。
- **動作力學三要素（分鏡「動作」欄必填）**：
  1. **① 施力點**：動作從何處發起（手腕下壓、腳跟蹬地、蛇尾蓄力捲縮）；
  2. **② 傳導路徑**：力量如何經身體傳遞、肌肉/鱗片變形與重心轉移（肩胛後縮、腰部擰轉、鱗片緊繃反光）；
  3. **③ 受擊反應與環境反饋**：受力後退距離、結構折疊挫傷、立刻反擊或掙扎，以及環境特效（碎石揚塵、環形氣浪、風切位移空氣、撞擊火花）。

### 4.4 分鏡工具鏈操作與九宮格審核斷點（P0 強制斷點）

```bash
# 1. 產生 Layer 2 骨架（預設 10s/3 鏡、動作力學三要素模板、INDEPENDENT_REF2VA 四大連戲錨點）
#    預設（--duration-policy report）只回報自然總長與目標（優先讀 accepted_duration_seconds）的偏差，不改鏡頭秒數，
#    並把壓縮前秒數寫進 metadata.natural_duration_sec 供審核頁對帳。
#    使用者明確要求硬性片長時才加 --duration-policy fit：把總長壓/拉到目標（對白鏡保留字數÷4，只縮放動作鏡，
#    單鏡 ≤ 15s，每段 >= 2×鏡數+0.5 以免階段 5 爆 E4 切點錯誤）；fit 會讓動作鏡變短，易有預告片節奏。
python scripts/storyboard/handoff_to_skeleton.py handoff-ep01.json --out-dir layer2/ --max-segment-sec 10.0 --max-shots 3

# 2. 靜態校驗與企劃時間表匯出
python scripts/storyboard/validate_storyboard.py --file layer2/layer2-EP01-*.json --handoff handoff-ep01.json
python scripts/storyboard/layer2_to_table.py layer2/layer2-EP01-*.json --check --md storyboard-ep01.md --timeline timeline-plan-ep01.csv

# 3. 可選：若 Qwen 圖像工具已可用，生成黑白鉛筆九宮格構圖
python scripts/storyboard/qwen_storyboard_grid.py --layer2 layer2/layer2-EP01-S01-a.json --generate-all --assemble-grid

# 若 Qwen 不可用，可用手繪或其他已授權的圖像工具提供對應 shot 的 PNG，並在 Layer 2 設定 sketch_file

# 4. 單鏡修改與重抽（若構圖不佳，微調秒數或重新繪製）
python scripts/storyboard/patch_shot.py --file layer2/layer2-EP01-S01-a.json --shot SH03 --shot-size CU --duration 3.5 --absorb-from SH04
python scripts/storyboard/qwen_storyboard_grid.py --layer2 layer2/layer2-EP01-S01-a.json --redraw-shot SH03 --assemble-grid

# 5. 產出 stage 4 HTML review；只有使用者確認後才記錄核准
python scripts/build_stage_review.py --project-dir . --stage 4
python scripts/build_stage_review.py --project-dir . --approve-stage 4
```

> **stage 4 審核門**：要進入 H3 編譯，每鏡須有對應的有效九宮格／單格 PNG，並通過人工 review。圖可由 Qwen、手繪或其他工具製作，需遵循相同 shot 對應與 hash 審核。文字分鏡 draft 可以先交付，不必生成圖或影片。

---

## 階段 5：提示詞包（Layer 3 編譯與 H3 官方六段式）

將 Layer 2 分鏡 JSON 結合 `assets.md` 與 `bible.json`，一鍵批次編譯為符合 MiniMax H3 官方規範的提示詞包與批次分段檔：

```bash
python scripts/storyboard/compile_layer2_to_h3.py \
  --layer2 layer2/layer2-EP01-*.json \
  --project-root . \
  --episode EP01 \
  --output-md prompts-ep01.md \
  --output-segments segments-ep01.json \
  --assets assets.md \
  --bible adapt/bible.json \
  --check
```

### 5.1 H3 官方六段式架構與防偷懶重構
編譯器輸出的提示詞嚴格遵照官方六段式語法結構（英文提示詞，只有 `<d>` 台詞保留原文；嚴禁負面詞）：

> **Layer 2 英文欄位**：`action_stages` / `observable_expression` 寫中文給人審，`action_stages_en` / `observable_expression_en` 寫英文給 H3（lint E15 會擋中文動作）。骨架會預留 `TODO` 英文欄位；`--check` 遇到 TODO 直接算錯誤。
>
> **階段 5 逐鏡五小節**：每鏡在 `action_and_performance.five_part_en` 親手寫 `camera`／`motion`／`performance`／`light`／`sound`（英文），編譯器原樣編成五小節。必寫、必寫詳細與禁止偷懶的規則見 `references/prompt-authoring.md`；不准用腳本產生、不准編譯後覆寫 segments。
> **段落選填欄位**：`asset_refs.primary_character`（指定綁圖主角）、`metadata.mood_en` / `music_en` / `soundscape_en`（英文摘要、配樂、音效）。
> **畫風**：取自 `style_lock.anchor`，其次 `assets.md` 的 `style_anchor`，不再寫死 live-action。寫實皮膚 LoRA 只在寫實風格才掛；LoRA 只在含 `Combat_Impact` 鏡頭的段落推導。
> **旁白**：`speaker` 為旁白／V.O. 時寫成 off-screen narrator，永不成為參考圖主體。
1. **`subject_definitions`**：定義參考素材與角色對應標籤（`<Picture 1>` 場景圖、`<Picture 2>` 核心角色圖）。嚴格落實**防混臉單圖排序（一段一張角色圖）**，同場其他次要角色轉為純外觀文字描述，防止多角色特徵平均化。
2. **`summary`**：整段秒數、情境氛圍與核心戲劇主旨概述。
3. **`retention_analysis`**：精確聲明各參考圖的繼承層級（如「保留 Picture 2 面部五官與服裝，服裝顏色嚴格依照設定圖」）。
4. **`detailed_description`**：`[Shot 1]` ～ `[Shot N]` 逐鏡細節，整合焦距物距、光源名詞映射、官方運鏡詞多樣化子句（**杜絕重複運鏡句與語法錯誤**）、動作力學三要素與角色表情，台詞精確封裝於 `<d>角色：台詞</d>`。**徹底消滅「Then the motion transitions smoothly.」等罐頭廢話**。
5. **`overall_soundscape`**：環境音效、動作打擊音、喘息與擬音（Foley）。
6. **`non_diegetic_music`**：非附隨性配樂、BGM 風格與情緒走向。

### 5.2 服裝狀態機（`wardrobe_states`）解析
編譯器依 Layer 2 `asset_refs.characters[].costume_id` 綁定服裝圖，來源為 `bible.json` 的 `wardrobe_states`，或 `assets.md` 角色卡的：
```markdown
- **服裝**：`W-chenshi-01` `pale lotus-pink jacket`；`W-chenshi-02` `same outfit smeared with mud`
- **服裝設定圖**：`W-chenshi-02` `images/char-chenshi-street.png`
```
參考圖路徑相對專案根目錄（`--project-root`），`--check` 會檢查檔案是否存在。設定板用語（純灰底、three-view）會自動從影片提示詞剔除。

### 5.3 物理門禁與雙重程式對帳
- **stage 4 gate**：編譯前要求 stage 4 有效核准，且輸入 Layer 2 與對應構圖 PNG 仍符合核准 hash；編譯不支援跳過 gate。
- **雙重程式對帳（`--check`）**：調用 `audit_refs_and_segments.py` 執行 17 條自檢與參考圖對帳，達成 **0 Errors** 方可放行出片。

### 5.4 旁白政策與外部化台詞（`--narration-policy`）

H3 的聲音與畫面在同一次 forward 生成，輸出是**單一 32 kHz 立體聲混音軌，沒有分軌，也沒有關閉音訊的參數**【官方，[MiniMax-H3 官方 repo](https://github.com/MiniMax-AI/MiniMax-H3)】。因此「這一段沒有台詞」不能用否定詞表達，官方給的是**欄位分離**——官方 §4.6：*"Dialogue, singing, and diegetic music already belong in the multimodal description and should not be repeated here. Use `N/A` only when the user explicitly requests complete silence throughout the video."*【官方】也就是說：外部化之後，提示詞裡**不出現 `<d>` 區塊**、`overall_soundscape` 只留環境與動作音即可，不必寫任何「no dialogue」字樣。

- **預設 `--narration-policy external`（`h3-native` 保留舊行為）**：**沒有可見嘴的台詞一律外部化**——畫外音、旁白、內心聲、背影／遮嘴說話都不再寫進 H3 的 `<d>` 區塊，改由外部 TTS 合成後於階段 7 混入。
  - **為什麼**：H3 的內建中文語音實測 ASR 置信度只有 0.43–0.54【社群實測】（字音模糊、吞字、偶發 −40 dB 靜音）；而且外部化之後 H3 這段本來就沒有人聲，環境音床乾淨、可直接當混音底。
  - **壞掉長怎樣**：把旁白留在 `<d>` 裡，H3 會把它念進同一條混音；之後想改用外部 TTS，就只能整軌丟掉重做聲場，等於白生成一次。
- **有可見嘴的畫內對白保留 `<d>`**：留給 H3 當嘴部開合與時間點的物理對齊錨點；組裝器仍可用外部 TTS 覆蓋（此時需要 lipsync，見 §7.1）。
- **指令**（`--narration-policy external` 為預設，寫出來是為了讓讀者知道這條路徑存在）：
  ```bash
  python scripts/storyboard/compile_layer2_to_h3.py \
    --layer2 layer2/layer2-EP01-*.json \
    --project-root . \
    --episode EP01 \
    --output-md prompts-ep01.md \
    --output-segments segments-ep01.json \
    --assets assets.md \
    --bible adapt/bible.json \
    --narration-policy external \
    --check
  ```
  `--narration-policy h3-native` 會走回舊行為，並沿用官方畫外音句式：`says in an off-screen voiceover` 加上 `<d>` 之後的 `while <Subject N>'s lips remain completely closed`【官方】。
- **`segments-epXX.json` 新增三個欄位**：

  | 欄位 | 內容 | 誰在用 |
  |---|---|---|
  | `external_narration[]` | `shot_id`、`global_shot_id`、`speaker`、`speaker_id`、`line`、`language`、`is_voiceover`、`start`、`end` | 階段 7 組裝器逐句送外部 TTS，並依 `speech_window` 排回時間軸 |
  | `speaker_ids` | 說話人 → 穩定代號 `(Sx)` 對照 | 官方 base §4.4；跨鏡鎖音色與 E22 閘門都要用 |
  | `metadata.narration_policy` | 本段採用的政策（`external` / `h3-native`） | E24 閘門判定 |

  編譯器另外會在 `compile_notes` 寫明「畫外音／旁白 N 句已改為外部 TTS（未寫入 `<d>`）」，方便審核頁對帳。

---

## 階段 6：生成（實戰定案與驗收）

### 6.0 特定 H3/FreeVideo 實測：Ref2VA 與首幀流程

下列結論來自特定模型與 adapter 版本，作為該環境的操作經驗；其他模型、provider 或生成模式需依當前接口和實際需求判斷。此 repo 的 H3 編譯器輸出 Ref2VA 六段式。

> **【定案 2 核心引用】使用者原話**：  
> 原話 1：「我是說這個劇情就直接重新寫分鏡，所謂的重新寫，**就是不考慮接續首幀的意思，每一個片段都是獨立去寫 ref2va**，頂多考慮站位以及角度等等，而不是像你這樣硬改」  
> 原話 2：「這種開場基本上算是靜幀的背面，就可以使用首幀動畫，去維持畫風……但如果是剛剛那種一開始是風景的，因為我們本來就有場景參考圖，所以還是用 ref2va」  
> 原話 3（第五輪首幀失敗判定）：「多人背影段也算失敗，那個畫風跟其他片段差距過大」

#### ✅ 已驗證有效（主力定案）：每段獨立走 `Ref2VA`
- 每段獨立帶「1 場景圖 ＋ 對應角色設定圖」，**絕不使用尾幀續接 `continue_from`**。
  - 原因：FreeVideo API 中 `references`（參考素材）與 `first_frame / last_frame` 互斥，混合傳入必報 `422 Unprocessable Entity`；若走純續接，後續片段因無角色參考圖，人臉將立即退化為泛化塑膠卡通臉。
- **四大連戲錨點**：跨片段連戲靠企劃期寫死 **① 光線**（主光向與色溫）、**② 軸線**（180° 關係）、**③ 站位**（實體家具/幾何參照）、**④ 材質**（地面與牆面紋理）。
- **收尾交接格設計**：每段最後 1–2 秒設計「靜止、景別夠寬、留白」的動作收勢，方便下段自然切入。

#### ❌ 已驗證失敗／⚠️ 尚未驗證（重要警示）：生圖模型首幀混用
- **慘痛教訓（第五輪首幀流程連續兩次誤判成功）**：
  使用外部生圖模型（Qwen-Image / GPT-Image）轉繪彩色首幀再送 H3 I2VA，若穿插在純 Ref2VA 片段中，由於生圖模型與 H3 底層風格渲染差異極大，成片畫風嚴重割裂、強烈跳戲！
  **嚴禁單看生成的首幀圖片精美就判定流程成功！必須與已生成的 H3 片段並排對照畫風！**
- **定案歸位**：
  - Qwen 黑白鉛筆九宮格：**「✅ 階段 4 視覺化構圖與佔位審核工具」**。
  - Qwen 轉繪全彩首幀（`--to-color-keyframe`）：**「⚠️ 選用實驗功能（需整部片全部統一用同一圖片模型生首幀並排驗證）」**。一般情況下，一律走主力定案獨立 Ref2VA。

### 6.1 送件前確定性自檢與顯存保護（`submit_h3_segments.py`）

FreeVideo 可用時，可透過 adapter 提交 MiniMax H3 工作。可用模型、服務與 GPU 資源會依設備和版本變動：

```bash
# 1. 乾跑驗證（安全檢查九宮格門禁、17 條 audit 自檢、參考圖 SHA256 與顯存狀態）
python scripts/storyboard/submit_h3_segments.py --segments segments-ep01.json --root-dir . --output-dir videos/ --dry-run

# 2. 正式批次提交（自動上傳參考圖 SHA256 快取、掛載 LoRA、輪詢進度並下載成品）
python scripts/storyboard/submit_h3_segments.py --segments segments-ep01.json --root-dir . --output-dir videos/
```

- 實際送件要求有效 stage 5 核准；hash 改變會失效。`--skip-stage-gate` 僅供 dry-run 除錯，實際送件仍必須通過 gate。
- Dry-run 可檢查本機參考圖、提示詞與送件前條件，不證明 provider/model 端生成會成功。
- GPU 預檢是即時診斷；不要把舊設備的顯存數值當成所有模型的固定硬門檻。

### 6.2 送件前確定性閘門（E19–E27）

`scripts/storyboard/audit_refs_and_segments.py` 模式 A 的第二組閘門，專門擋「複製人」與「旁白欄位分工」兩類壞掉。`compile_layer2_to_h3.py --check` 會自動跑，**Errors 未清零不得送件**。

| 閘門 | 擋什麼 | 怎麼修 |
|---|---|---|
| **E19** 未錨定在場人物 | 角色出現在畫面中卻沒有自己的參考圖 → H3 把唯一那張臉複製給他們（2026-10-19 實測 4/4 段出現複製人） | 掛該角色自己的單視角裁切參考圖並在 stage5 綁定 `identity_anchor_ids`，或把該角色移出畫面 |
| **E20** 疑似多視圖板 | 角色參考圖 ≥ 1600×900 且長寬比 ≥ 1.5（四視圖／表情板）→ 版面被複製進成片、長出背景人海；**未宣告 `reference_view: "panel"` ＋ `panel_label_en` 時一律擋** | 改成單一視角裁切（正面頭像 950×910 或背面全身裁切）；要用整板就宣告整板查表並指定格位（見 E27） |
| **E21** 無參考圖的群眾／路人 | `detailed_description` 出現 crowd／onlookers／bystanders 這類無參考圖人群 → 群眾被套上主角造型 | 把人群移出畫面、改寫成不可辨識的失焦剪影，或改走「分鏡圖 → I2V」把人群畫進首幀 |
| **E22** 缺少說話人代號 | 提示詞有 `<d>` 台詞卻沒有任何 `(S1)` 形式的說話人代號 → 聲音掛到畫面上唯一那張臉、長出複製人 | 補穩定 `(Sx)` 綁定（官方 base §4.4：發聲者，含畫外音，都要有代號） |
| **E23** 畫外音缺嘴閉合聲明 | 寫了 `off-screen voiceover` 卻沒說明嘴唇閉合 | 在 `<d>` 區塊之後立刻寫明 on-screen character's lips remain closed |
| **E24** 旁白政策衝突 | `narration_policy=external` 但畫外音台詞仍以 `<d>` 出現在提示詞 → H3 會把旁白一起念出來 | 改由外部 TTS 合成、於階段 7 混入；H3 這段只出環境音 |
| **E25** 環境音重複台詞 | `overall_soundscape` 重複了 `<d>` 內的台詞 → H3 在環境音軌再念一次 | 對白只寫在 `detailed_description` 的 `<d>` 區塊，環境音欄只留環境與動作音（官方 §4.6） |
| **E26** 身份錨點缺參考圖 | 標記為無臉身份錨點（`reference_view=non_face`）卻沒有自己的參考圖路徑 | 補上該角色自己的裁切參考圖路徑 |
| **E27** 整板查表缺格位說明 | 宣告 `reference_view: "panel"`（多格板查表）卻沒有 `panel_label_en` → 沒指定用哪一格，模型會把整張板複製進成片 | 補 `panel_label_en`（如 `"the fourth figure from the left, a full-body back view"`）；編譯器也會直接丟 `ValueError`（訊息含「必須同時提供 panel_label_en」） |

### 6.3 影片自動審查門禁（`verify_video_shot.py`）

支援單鏡審查與分段級（Segment-Level）批次審查，自動校驗規格並產出報告：

```bash
# 批次審查整個 Episode 的所有分段並輸出 JSON/Markdown 報告
python scripts/storyboard/verify_video_shot.py --segments segments-ep01.json --videos-dir videos/ --out-report videos/qa-report.md --out-json videos/qa-report.json

# 單鏡/單場審查並回寫 Layer 2
python scripts/storyboard/verify_video_shot.py --video videos/EP01-S01-seg01.mp4 --layer2 layer2/layer2-EP01-S01-a.json --write-back
```
四大自動攔截檢驗：
1. **時長與規格**：精確以分段規劃總秒數為基準比對，誤差 $\le 0.5\text{s}$（徹底解決分段 vs 單鏡時長粒度錯位誤判）。
2. **彩度防灰階滲透**：$C^* \ge 10.0$，防止鉛筆草圖滲漏成黑白片。
3. **九宮格分屏線殘留**：抽樣影格 $1/3, 2/3$ 無暗黑格線分割。
4. **跨鏡色彩連貫性**：串聯 `color_qa.py`，相鄰鏡頭色盤 $dE_{76} \le 25.0$。

---

## 階段 7：組裝交付與配音決策

本階段的順序是：**先定聲音三層（§7.1）→ 配音先行、再回頭定鏡頭長度（§7.2）→ 盤點本機 TTS 能力（§7.3）→ 混音與響度照交付標準（§7.4）→ 用組裝器執行（§7.5）→ 核對交付清單（§7.6）**。

### 7.1 聲音三層決策（新增）

H3-Omni-Transformer *"jointly predicts video and audio latents, which are then decoded into video and stereo audio"*【官方，[MiniMax-H3 官方 repo](https://github.com/MiniMax-AI/MiniMax-H3)】；輸出是**單一 32 kHz 立體聲混音軌，沒有分軌，也沒有關閉音訊的參數**【官方】。所以「畫面要靜、聲音另做」在 H3 上不是一個開關，而是**要把那一層拆出來自己重建**。競品在這件事上乾淨得多：Kling Video 2.6 有官方 Native Audio Toggle（關閉 ⇒ 影片不含音軌），Veo 3.1 在 Vertex AI 上有 `generate_audio=False`；H3 兩者都沒有。

| 層 | 什麼時候用 | 怎麼做 | 為什麼 / 壞掉長怎樣 |
|---|---|---|---|
| **A. 畫內有可見嘴的對白** | 角色正臉說話、嘴型是重點 | **留給 H3 內建語音**（`<d>` 區塊照寫），當成口型錨點；**掛上音色母帶（`<Audio N>`）時，H3 會照母帶音色重新合成**，這就是跨段「像同一個人」的來源；要每段完全一致或更清晰的聲音時，用外部 TTS 覆蓋 ＋ lipsync（[MuseTalk 1.5](https://github.com/TMElyralab/MuseTalk)） | H3 內建中文語音實測 ASR 置信度只有 0.43–0.54【社群實測】（字音模糊、吞字、偶發 −40 dB 靜音），但嘴型是跟著 `<d>` 走的；音色參考只給音色方向、**不鎖口型**。**壞掉長怎樣**：直接抽掉 H3 音軌，會看到嘴還在動、聲音卻沒了，必須補 lipsync 才對得上 |
| **B. 畫外音／旁白／內心聲／背影說話** | 旁白解說、內心獨白、背影或遮嘴說話 | **必須外部 TTS**：H3 這段只出環境音床，語音另生成後於階段 7 混入 | 這些句子本來就沒有「可見嘴」，硬塞回 H3 只會得到一條混在環境音裡的喃喃聲，還要另外把環境音重導一次。**壞掉長怎樣**：H3 把旁白念進同一條混音，之後想改用外部 TTS 就只能整軌丟掉重做聲場，等於白生成一次 |
| **C. 全片外部聲景** | ambience ＋ SFX ＋ TTS ＋ BGM 全部外部重建 | 產出「無內建語音」的 H3 片段，聲場整條自己搭 | **只在要做多語配音版時才需要**：H3 的對白與畫面同批生成、已烤在同一條混音裡，換語言等於要重生成整支影片，之後聲場才能完全外部化。**壞掉長怎樣**：為了「乾淨」而全片外部化卻沒有多語需求，等於多花一輪重建成本卻沒有收益 |

**音色怎麼鎖（同一個 `V-<slug>` 驅動兩條軌道）**：跨片段音色一致**不是**靠影片模型「記住」誰的聲音——社群說的「直出影片、每段聲音都一致且富有感情」，拆開看是**同一份音色被每一句重新合成**：掛音色母帶時是 **H3 自己照 `<Audio N>` 的音色重新發聲**（官方只保證「參考音色與語氣」，原訊號不複製），走外部 TTS 時則是**同一條複製音色重合成每一句**。本專案因此用**同一個 `V-<slug>` 當兩邊的 join key**：

| 軌道 | 怎麼做 | 保證程度 |
|---|---|---|
| **H3 音色參考** | stage5 `audio_references` 綁母帶 → 編譯器產出 `<Audio N>` 綁定句 ＋ `reference` 保留標記 ＋ 固定描述詞 `voice_4d_spec_en` | **是參考，不是保證**【官方】；本機 FreeVideo **送得進**音訊參考（見 §7.3），但官方標註 **Experimental; does not lock the output soundtrack or lip sync**——只給音色方向，不鎖輸出音軌與口型 |
| **外部 TTS** | `config/tts.json` 的 `voice_map["V-<slug>"]` → 供應商音色 id（VoiceStudio profile 名稱／Fish Audio voice id／OpenAI 相容端點的 voice） | **完全確定的選項**（H3 音色參考是「像同一個人」，這裡是「每段一模一樣」） |

- **`voice_4d_spec_en`（或 `voice_profile_en`）是插進說話那一句的穩定音色描述詞**，必須用英文寫：H3 提示詞正文是英文，只給中文 `voice_4d_spec` 編譯器**不會**貼進提示詞（會變成未翻譯噪音），只在 `compile_notes` 回報提醒。
- **兩軌可以同時開**：H3 負責畫面與口型錨點，最後用外部 TTS 覆蓋（要 lipsync）。細節與完整提示詞片段見 `references/consistency.md` §6。

**本專案預設 ＝ A ＋ B 混合**（`--narration-policy external` ＋ `--audio-mode auto`）：**畫內對白保留 H3 口型、畫外音與旁白走外部 TTS**。C 不預設，只有使用者提出多語配音版需求時才升級。

- **官方有沒有這樣建議？沒有。** MiniMax 官方文件並未推薦以外部 TTS 取代 H3 音訊；上表是**本專案自己的工程決策**，不是官方口徑。官方最接近的一句在 ComfyUI 文件：*"If needed, generate per-speaker audio externally and reference with the right marker (fully_copy vs partially_copy)."*【官方／[docs.comfy.org](https://docs.comfy.org)】——`fully_copy`／`partially_copy` 是 ComfyUI 的音訊參考標記，不是 MiniMax 的欄位。
- **「這段沒有台詞」的正寫法是欄位分離，不是加否定詞。** 官方 §4.6：*"Dialogue, singing, and diegetic music already belong in the multimodal description and should not be repeated here. Use `N/A` only when the user explicitly requests complete silence throughout the video."*【官方】因此外部化之後，提示詞裡**不出現 `<d>` 區塊**、`overall_soundscape` 只留環境與動作音即可，不必寫「no dialogue」；寫了反而變成罐頭詞。
- **為什麼是「畫外音」而不是「所有台詞」都要外部化**：畫外音沒有嘴型要對，外部化零成本；畫內對白有嘴型錨點，外部化還要補 lipsync，兩者不是同一個成本級別。

### 7.2 配音先行（TTS-first）與時長對軸

**順序：TTS 產音 → 量測時長 → 鏡頭定長（建議 ×1.2 緩衝）→ 生成 → 修剪 → 混音。**

- **怎麼做**：先把每一句台詞送外部 TTS 產出音檔，用 ffprobe 量到實際秒數，再回頭把鏡頭長度定成 `實測時長 × 1.2`，最後才生成影片。
- **為什麼**：先出畫面、之後才發現旁白比鏡頭長，就等於白跑一次 render——H3 一段的算力成本不低，而且改長度要重生成。社群實踐的說法是 *"write and time the voice before generating the visuals"*、*"narration sets the spine; visuals fill it"*【社群】。
- **20 % 緩衝**：鏡頭長度取實測時長 × 1.2，留兩成給停頓、氣口與反應鏡頭。**壞掉長怎樣**：完全貼齊，語氣一頓就掉字；留太多則節奏鬆垮、剪輯點無處落。
- **0.3–0.5 s 尾端留白**：每句尾端留 0.3–0.5 s 靜音，讓切點有呼吸。**壞掉長怎樣**：句尾黏到下一句，聽起來像搶話。
- **H3 硬上限 15 秒**【官方】：單段不能超過 15 秒。**壞掉長怎樣**：×1.2 之後超過 15 秒就必須拆成兩段或改寫縮稿，**不要壓語速硬塞**——壓速的後果是台詞含糊，正是要避免的問題。
- **落地欄位**：組裝器以 authored `speech_window`（段內秒）作為 TTS 落點，不用 shot 起始時間；所以先量時長、再回填 `speech_window`，組裝時語音才會落在畫面實際的嘴型動作上。

### 7.3 TTS 引擎選擇與環境探查

**先盤點，再選引擎。** 這台機器上到底有哪個語音後端，要用唯讀工具查，不要靠猜：

```bash
python scripts/storyboard/tts_doctor.py          # 人類可讀表格
python scripts/storyboard/tts_doctor.py --json   # 機器可讀 JSON

# 看本機 VoiceStudio 有哪些音色（profile 與 preset）
python scripts/storyboard/tts_engine.py --list-voices --engine voicestudio
```

`tts_doctor.py` 會回報：ffmpeg／ffprobe 在不在、讀到哪一份設定檔與 `voice_map`、每個引擎可不可用與具體下一步、VoiceStudio `/health` 摘要、GPU／VRAM 衝突警告、edge-tts 棄用提醒、Fish Audio 授權提醒，以及建議的 `--tts-engine`。**它是唯讀的**：不寫檔、不上傳、不呼叫生成端點、**不印出任何金鑰**（API 金鑰只顯示「有／無」與環境變數名稱）。

**音色母帶從哪來**（`extract_voice_master.py`）：母帶不必事前就有，**角色第一次出場的那一句就是最自然的母帶來源**。

```bash
# 1) 看哪些角色、在哪些段落有「畫內有可見嘴」且長度 2–15 秒的台詞可以當母帶
python scripts/storyboard/extract_voice_master.py --segments segments-ep01.json --list

# 2) 從第一次出場那一段抽出母帶（切點直接取自 Layer 2 的 speech_window，不靠 ASR 反推）
python scripts/storyboard/extract_voice_master.py \
  --segments segments-ep01.json --segment-id EP01-S01-c --character C-luonien \
  --videos-dir videos/ --output assets/voices/V-luonien-master-v1.wav
```

- 產出 48 kHz／單聲道／16-bit PCM 的母帶與同名 `.provenance.json`（來源 SHA256、時間窗、原句、輸出 SHA256），並直接印出可貼進 stage5 綁定檔的 `audio_references` 片段。
- **兩條來源路線**：事前用 TTS 克隆做一條（最乾淨）vs 事後從生成片抽出（省事，但母帶帶著該場景的環境音）。抽完若不滿意那個音色，**重抽那一段**，不要拿來當母帶。
- FreeVideo 導演台的 cast 卡片本來就有同樣的機制（`voice` 欄位可從 `from_job` 取音軌），走導演台時這個閉環已經內建。

**引擎選項**（`assemble_episode.py --tts-engine`）：

| 值 | 用途 | 注意事項 |
|---|---|---|
| `auto` | 依序挑第一個可用者：**voicestudio → fish → openai_compat → sapi** | 預設；實際呼叫失敗會自動往下一順位補 |
| `voicestudio` | **本專案預設**：本機 VoiceStudio／OmniVoice voicebox API（`http://127.0.0.1:8001`） | 本機、免費、中文與日文都支援；但要吃 3～4 GB 顯存 |
| `fish` | Fish Audio 雲端（`fish_cloud`）或本機 OpenAI 相容 fish-speech（`fish_local`） | 授權有條件，見下 |
| `openai_compat` | **自帶 API**：任何 OpenAI 相容的 `/v1/audio/speech` 端點 | `base_url` 尾端的 `/v1` 會自動去掉，不會變成 `/v1/v1/audio/speech` |
| `sapi` | Windows 原生 SAPI，完全離線 | 機械味重，只當離線備援 |
| `edge` | edge-tts | **只保留給離線除錯，不得用於交付**，見下 |

**設定檔 `config/tts.json`**（已被 `.gitignore` 排除；`config/tts.example.json` 是可提交的範例）：

| 欄位 | 說明 |
|---|---|
| `default_engine` | 未指定時的預設引擎 |
| `engines.<id>.base_url` | 端點位址 |
| `engines.<id>.api_key` / `api_key_env` | 金鑰；建議用 `api_key_env` 指向環境變數，**不要把金鑰寫進檔案** |
| `engines.<id>.model` / `voice` / `voice_id` / `reference_id` | 模型與音色 |
| `engines.<id>.response_format` | 供應商回傳格式（`wav` / `mp3`） |
| `engines.<id>.auth_header` / `auth_prefix` | 認證標頭名與前綴（預設 `Authorization` / `Bearer `） |
| `engines.<id>.headers` | 自訂標頭 |
| `engines.<id>.extra_body` | 額外請求欄位 |
| `voice_map` | 資產音色 ID（`V-<slug>`）→ 供應商音色／profile 名稱 |

**金鑰鐵律**：金鑰只從 `api_key` 或 `api_key_env` 指定的環境變數讀取，**永不寫進磁碟、永不印出**；所有錯誤訊息一律遮罩成 `***REDACTED***`。`tts_doctor.py` 與 `tts_engine.py` 都遵守這條，`--json` 輸出裡的 `api_key` 也只有布林值。

**音色對映**：資產表的音色 ID 形如 `V-narrator`、`V-lin-zhao`；`voice_map` 把它們對到供應商端的音色（VoiceStudio 是 profile 名稱，例如 `角色A｜冷面上班族內心旁白 V2`）。解析順序是**明確指定的 `voice` → `voice_map[speaker]` → speaker 原文 → `engines.voicestudio.default_profile`**，而且在**任何供應商呼叫之前**就完成；解析不到就會拿 speaker 原文當音色名去送，結果是拿到不對的聲線。

**VoiceStudio（本機預設）**：VoiceStudio 是開源 Electron app（AGPL-3.0，[github.com/debpalash/VoiceStudio](https://github.com/debpalash/VoiceStudio)），內附的後端是 OmniVoice（k2-fsa）。本機 voicebox API 由 `E:\OmniVoice\啟動-OmniVoice.bat` 啟動、`停止-OmniVoice.bat` 停止。
- 引擎可選 `qwen`（Qwen3-TTS 1.7B）、`qwen_custom_voice`、`luxtts`、`chatterbox`、`chatterbox_turbo`、`tada`、`kokoro`；語言含 `zh`、`ja`。
- `POST /speak` 收 profile **名稱**（中文名如 `角色A｜冷面上班族內心旁白 V2` 可直接用），`POST /generate` 收 profile **id**；`GET /profiles` 回一個裸陣列。
- **合約陷阱**：`/speak` 是非同步的（要輪詢 `GET /generate/{id}/status`，該端點宣告為 JSON 但行為像 SSE）；`GET /audio/{id}` 宣告為 JSON 但實際回二進位音訊；**亂塞 `engine` 會破壞 preset profile**——profile 自己的 `default_engine` 必須優先。
- **硬體限制**：OmniVoice 需要 3～4 GB 顯存，而 ComfyUI 已經吃掉同一張 8 GB RTX 4060 Ti 的 5～7 GB，**兩者不能同時跑**（使用者自己的 `E:\OmniVoice\使用說明.txt` 記錄同時跑會讓聲音品質劣化）。`tts_doctor.py` 只警告，不會自動關閉任何程式——**配音前先手動關掉 ComfyUI**。

**H3 音色參考（`<Audio N>`）與本機路徑的送法**：stage5 綁定檔可以掛音色母帶，讓 H3 **自己生成**的那把聲音「聽起來像同一個角色」：

```json
"audio_references": [
  {"id": "V-HERO", "path": "audio/V-HERO-master.wav", "character_id": "C-HERO",
   "role": "voice-timbre",
   "description_en": "a single teenage boy's Mandarin line recorded dry with no music"}
]
```

編譯器**只**把音色參考掛給**本段真的有可見嘴在說話**的角色（畫外音／旁白已外部化成 TTS，不掛，並在 `compile_notes` 記一條說明），輸出（英文，逐字）：

```text
<Audio 1> is the voice-timbre reference for <Subject 1> (S1), containing a single teenage boy's Mandarin line recorded dry with no music.
```

```text
<Audio 1>: reference - <Subject 1> (S1) follows <Audio 1>'s voice timbre and measured delivery without copying the original signal; the words in <Audio 1> are not spoken in the target video.
```

- **✅ 本機 FreeVideo 路徑帶得動音訊參考（媒體型態看副檔名，不看 `role`）**：官方 ComfyUI 節點 `MiniMaxH3ReferenceToVideo` 有獨立的音訊參考槽 `ref_audios` → `io.Audio.Input("ref_audio", "Standalone reference audio")`；FreeVideo 操作面板 `FreeVideo · Media` 也有對應的 **`Reference audio`** 上傳／連接槽（可接 `Load Audio` 等 AUDIO 輸出）。**怎麼做**：把音色母帶（`.wav` / `.mp3` / `.flac` / `.ogg` / `.m4a` / `.aac` / `.opus`）放進 `media.references`——**媒體型態由副檔名判定**（`EXTENSIONS` 的 `image` / `video` / `audio`），`resolve_assets()` 收成 `{'kind': kind, 'path': str(path)}`，`submit_h3_segments.py` 的 `upload_reference_media()` 照圖片方式 POST `/media`；**不需要** `role: reference_audio` 欄位（先前的說法是把媒體項目的修飾欄位 `file` / `from_job` / `library` / `frame` / `edit` 誤當成媒體型態）。**壞掉長怎樣**：副檔名不在支援清單內時 `media_kind()` 判不支援而送不進去，dry-run 就會用 `SUPPORTED_AUDIO_SUFFIXES` 印 ❌ 訊息。
- **參考順序是「圖 → 影片 → 獨立音訊」**：官方節點說明 *"References enter the presentation in fixed order: images, then videos (each soundtrack's `<Audio j>` label right before its `<Video k>`), then standalone audio. Ordinals are 1-based per type, so the prompt refers to them as `<Picture i>` / `<Video k>` / `<Audio j>`."*；`compile_layer2_to_h3.py` 已把音訊項目排在**所有圖像之後**（`<Audio N>` 各自從 1 編號）。音訊也佔 32 個參考名額（`connect_assets()` 把連接的 `reference_audio` 算進去）。
- **兩種音色綁定寫法並存（來源不同）**：官方 ref-en §2.4 的獨立綁定式 `<Audio 1> is the voice-timbre reference for <Subject 1> (S1), containing a single teenage boy's Mandarin line recorded dry with no music.`；FreeVideo 導演台 `freevideo_engine/agent/drama.py` 的 `subject_definitions()` 則把綁定寫在**主體那一行**、與 `<Picture N> shows its appearance` 對稱：`<Subject 1> is the character in <Picture 2>, a teenage boy in a light short-sleeved shirt. <Audio 1> is its voice.`（導演台 cast 卡片本來就有 `voice` 欄位 `card['voice']['clip']`，會連同角色一起送成參考並編成 `<Audio j>`）。**怎麼做**：兩種可同時出現在同一份提示詞——官方那行說明音色是誰的、導演台那行把主體與音檔序號綁起來。**壞掉長怎樣**：兩邊的 `<Audio j>` 對不上（導演台寫 `<Audio 2>`、官方行卻綁 `<Subject 1>`），角色就會發出**別人的音色**。
- **每段音色參考上限 3 個、參考總數上限 32 個**：導演台 `MAX_VOICES = 3`（模型限制）、`MAX_REFERENCES = 32`；FreeVideo 引擎端 `comfy_assets` 同樣是 32 個媒體項目上限（圖片＋影片＋音訊合計）。**壞掉長怎樣**：塞不下時導演台**不報錯**，而是把角色降級成 `voice_omitted`（有圖無聲）或 `omitted`（整個不帶參考），成片會突然換一把聲音。
- **⚠️ 官方把音訊參考標成實驗性**：FreeVideo 面板註明 *"Experimental; does not lock the output soundtrack or lip sync."*——音色參考是讓 H3 **重新合成**一把像母帶的聲音，**不是音軌複製**，也**不鎖**輸出音軌與口型；跨片段一致性官方不保證（社群有 voice crossover 報告，`h3/audio-pipeline.md` 已記）。**壞掉長怎樣**：期待母帶原音被搬進成片（會聽到母帶原句），或期待音色參考順便鎖住口型（聲音對得上、嘴型對不上）。
- **要「每段一模一樣」的確定性就走外部 TTS（軌道 2）**：本機 FreeVideo 也送得進音色參考（軌道 1），但那是「聽起來像同一個人」的參考，不保證跨段一致；需要完全確定（例如多語配音那一行）時，用 `voice_map["V-<slug>"]` 固定同一條複製音色，每句重新合成。`tts_doctor.py` 會回報哪些引擎真的可用。
- **母帶原句不會被念出來**：官方要求只參考音色時不得把母帶對白帶進目標影片，編譯器照這句寫成 `the words in <Audio 1> are not spoken in the target video.`【官方】**壞掉長怎樣**：母帶原句也放進 `<d>`，觀眾會聽到同一句話出現兩次。

**Fish Audio（雲端備援）**：[github.com/fishaudio/fish-speech](https://github.com/fishaudio/fish-speech) 的程式與權重採 Fish Audio Community License：年營收 50 萬美元以下可免費使用，但**把 TTS 對外提供成託管服務需要另簽協議**。交付前先確認自己的使用情境落在哪一邊。

**自帶 API（`openai_compat`）**：任何 OpenAI 相容的 `/v1/audio/speech` 都能接進來——使用者已有商用 TTS 帳號、或要走雲端大廠時走這條，設定檔填 `base_url` 與 `model` 即可。

**edge-tts 只能除錯**：**自 2026-10-10 起壞掉**（微軟的 Edge 朗讀改要 v2 `Sec-MS-GEC` token，edge-tts 7.2.8 直接吃 403），**而且沒有商用授權**（微軟的商業 TTS 指向 Azure AI Speech）【官方】。保留這個引擎只是為了離線除錯能跑通流程，**交付一律不准用**。

### 7.4 混音與響度交付標準

**量測演算法**是 ITU-R BS.1770-5；交付目標另外有各自的規範。

| 標準 | 整合響度 | True peak | 適用 |
|---|---|---|---|
| **EBU R128 v5.0** | **−23 LUFS ±0.5 LU** | ≤ −1 dBTP | 戲劇交付預設；本專案 `--target-lufs -23 --true-peak -1.5` |
| **ATSC A/85:2026-07** | −24 LKFS ±2 dB | < −2 dBTP | 對白錨定（CALM Act），美國廣播路徑 |
| **Netflix** | −27 LKFS（dialog-gated） | — | 串流平台；對白閘門取樣，不是整體平均 |
| Spotify −14 LUFS | −14 LUFS | — | **音樂／串流值，不是戲劇交付值**；不要套在劇集成片上 |

**順序：先做整合響度正規化，再套 true-peak 上限。** 反過來會在壓峰值時把響度又拉回來，最後量到的整合響度就偏了。

**正規化要在整片做，不要逐段做**：逐段正規化會把段與段之間的動態對比壓平（安靜的環境音段被拉成和對白段一樣大），成片聽起來像一條被壓扁的動態線。組裝器的做法是：分段只做混音，**Concat 完再對整條節目做 `loudnorm`**。`--no-loudnorm` 會關掉它（不建議交付時用）。

**修正後的 ffmpeg 混音鏈**（三個關鍵字都別動）：

```bash
ffmpeg -i video.mp4 -i tts.wav -filter_complex \
  "[0:a]aresample=48000,volume=0.15[native];[1:a]aresample=48000,adelay=2000:all=1[v1];[native][v1]amix=inputs=2:duration=first:normalize=0:dropout_transition=0[mixed];[mixed]apad,atrim=duration=10.0[aout]" \
  -map 0:v -map "[aout]" -c:v copy -c:a aac -b:a 192k -ar 48000 out.mp4
```

- **`aresample=48000`**：每條軌都先統一到 48 kHz。`loudnorm` 預設輸出 192 kHz，忘了補 `-ar 48000` 會得到一支取樣率怪怪的成片。
- **`adelay=2000:all=1`**：`all=1` 才是單聲道來源的安全寫法；`2000|2000` 只對真正的雙聲道有效，單聲道 TTS 會被忽略。**壞掉長怎樣**：語音沒有延遲、字幕卻有時差。
- **`amix ...:normalize=0`**：預設 `normalize=1` 會把輸出除以輸入數，等於把 TTS 人聲壓低約 3 dB【社群實測：兩軌 440/880 Hz、來源 −21.1 dB，`normalize=1` 混成 −24.1 dB，`normalize=0` 混成 −18.1 dB】。峰值交給後段的 `loudnorm` 處理。
- **`dropout_transition=0`**：避免音軌長短不同時，`amix` 在切換點做淡入淡出而產生「呼吸感」雜訊。

**兩遍 loudnorm（正式交付用）**：

```bash
# 第一遍：量測
ffmpeg -i final_ep01.mp4 -af loudnorm=I=-23:TP=-1.5:LRA=11:print_format=json -f null -

# 第二遍：帶入第一遍的 measured_* 值重跑
ffmpeg -i final_ep01.mp4 -af loudnorm=I=-23:TP=-1.5:LRA=11:measured_I=-23.1:measured_TP=-1.2:measured_LRA=7.4:measured_thresh=-33.6:offset=-0.2:linear=true:print_format=summary -c:v copy -c:a aac -b:a 192k -ar 48000 final_ep01_norm.mp4
```

單遍 loudnorm 約有 ±0.5 LU 誤差【官方／ffmpeg `loudnorm` 文件】；要交付就跑兩遍，並用 `ffprobe` 驗輸出取樣率是 48000。

### 7.5 自動化配音、字幕與成片拼接（`assemble_episode.py`）

使用者要求組裝且素材與依賴可用時，可執行後期交付：

```bash
# 1. 先盤點本機 TTS 能力（唯讀；不寫檔、不上傳、不印金鑰）
python scripts/storyboard/tts_doctor.py
python scripts/storyboard/tts_doctor.py --json

# 2. 組裝：--audio-mode auto 逐段裁決（畫內對白留 H3 口型、旁白由外部 TTS 產生）
python scripts/storyboard/assemble_episode.py \
  --segments segments-ep01.json \
  --videos-dir videos/ \
  --output final/ep01_final.mp4 \
  --audio-mode auto \
  --tts-engine voicestudio \
  --tts-config config/tts.json \
  --target-lufs -23 \
  --true-peak -1.5 \
  --delivery-report final/delivery-ep01.md

# 3. 全鏈路閉環自檢
python scripts/storyboard/assemble_episode.py --self-test
```

- **`--audio-mode` 預設 `auto`，逐段裁決**：有可見嘴的畫內對白 → `native_sub`（保留 H3 的語音做口型）；整段說話都被外部化 → `tts_replace`（把外部 TTS 混在 H3 已無語音的環境音床上）。仍可手動指定 `tts_replace`／`native_sub`／`narration_only`。
- **語音能力依環境而定**：TTS engine 可選 `auto`、`voicestudio`、`fish`、`openai_compat`、`sapi`、`edge`；不承諾每個環境都能離線降級，先跑 `tts_doctor.py` 才知道實際有哪個。
- **TTS 落點用 authored `speech_window`**（段內秒），不是 shot 起始時間：合成的語音才會落在畫面實際的嘴型動作上。
- 外部 `narration-epNN.md` 目前不會被組裝器解析。旁白稿可作為文字交付；要合成旁白時，先轉成組裝器支援的 inline line/narration 欄位，或交給其他剪輯工具處理。`--narration` 目前會明確回報不支援，不代表可讀取該 Markdown。
- **Windows FFmpeg 冒號轉義**：自動將 Windows 絕對路徑中的磁碟機冒號轉義為 `C\:/...`，避免 FFmpeg 字幕濾鏡語法解析崩潰。
- **音訊多軌精細混音**：`aresample=48000` → `adelay ...:all=1` → `amix ...:normalize=0:dropout_transition=0`；混完才做整片 `loudnorm`（細節見 §7.4）。
- **無縫拼接**：依據分段時間順序自動生成 Concat 協議列表，一鍵封裝最終交付成片。

### 7.6 交付檔案清單
1. **成品影片**（`final/ep01_final.mp4`）：配音、混音、字幕燒錄無縫拼接成片，並已套整片 `loudnorm`。
2. **旁白與字幕稿**（`narration-ep01.md`）：可獨立交付；組裝器不會直接讀取外部 Markdown 旁白稿。
3. **剪輯時間線**（`timeline-ep01.csv`）：從編譯後 `segments-ep01.json` 執行 `layer2_to_table.py --timeline`，使用有效片長與量化後末鏡時間。Layer 2 直接匯出的表格只代表企劃名義秒數。
4. **品質審查報告**（`videos/qa-report.json`）：分段規格、色差與畫風審查報告。
5. **交付清單**：列出已生成檔案、規格核驗結果與各鏡狀態；**交付前用 `ffprobe` 複核輸出取樣率與響度**（見 §7.4 的兩遍 loudnorm）。
