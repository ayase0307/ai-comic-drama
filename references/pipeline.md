# 八階段詳細流程

依使用者指定的交付範圍選擇階段；只要文字劇本、分鏡或提示詞時，可停在該階段並交付 draft，不要求圖片或影片生成。小說改編依使用者要求進入改編流程，不把完整八階段當成每項任務的必經步驟。

文字規劃、Python 本機檢查、圖片生成與影片生成是不同能力層。先以 `python scripts/check_environment.py` 檢查本機工具；`python scripts/run_offline_checks.py` 執行離線檢查。這些命令不檢查 provider 帳戶、token 或模型生成能力。FreeVideo 是可選 adapter，影片生成要以當前 Agent 或已連線後端實際可用為準。

階段狀態只記錄於 `review/project-state.json`，每次核准綁定輸入 hash，修改後必須重審。stage 4 review 核准是 H3 compiler 前置條件；實際 submit 要求 stage 5 核准。QA 技術通過不會自動成為人工核准。

---

## 階段 0：定調（Intake）

只詢問當前交付所缺少且會阻礙工作的項目；沿用使用者已給的 brief、模型與參數，不重複詢問。純文本或分鏡交付不要求先收齊出片參數。

| 項目 | 選項／說明 |
|---|---|
| 集數與每集時長 | 單集 60–120 秒最常見；小說改編預設 90–120 秒 |
| 原稿類型與用途 | 小說／網文／故事梗概／已有劇本；依當前任務確認需要的來源與處理方式 |
| `genre_mode` | `xuanhuan_revenge`／`romance_emotional`／`mystery_thriller`／`comedy_slice_of_life`／`wuxia_action`／`healing_literary` |
| `target_medium` | `motion_comic` 動態漫／`ai_animation` AI 動畫漫劇／`live_action_short_drama` 真人短劇 |
| 畫風 | 從 `references/styles.md` 選一套風格鎖定錨（整部只用一套） |
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
6. **產出階段 2 HTML 並排審核頁面與斷點停下（P0 鐵律）**：
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
- 對白單句 > 28 字警告、> 35 字阻斷（字幕可讀性）；整集時長在目標 ±15%。
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
#    單集時自動讀 handoff 的 target_duration_seconds 把總長壓到目標（對白鏡保留字數÷4，只縮放動作鏡），
#    並保證每段秒數 >= 2×鏡數+0.5，避免階段 5 才爆 E4 切點錯誤。--target-total-sec 0 可關閉。
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

### 7.1 配音分層決策（實戰關鍵）

實測 MiniMax H3 原生中文配音之語音辨識（ASR）置信度僅在 **0.43–0.54**，普遍存在字音模糊、發音吞字、急促搶跑或偶發 -40dB 靜音。
提示詞中保留 `<d>` 標籤，是為了提供影片生成時**嘴部開合與時間點的物理對齊錨點**。在階段 7 組裝時，提供以下三選一決策：

- **方案 A（推薦）**：**抽離 H3 人聲軌，使用高品質外部 TTS（如 Edge-TTS、CosyVoice、Windows SAPI）重配中文台詞，再用 ffmpeg 混回環境音效軌**。口型與語義兼得。
- **方案 B**：保留 H3 原生配音，透過 ffmpeg 強制燒錄清晰中文字幕。
- **方案 C**：全片去台詞化，改為純旁白講解。

### 7.2 自動化配音、字幕與成片拼接（`assemble_episode.py`）

使用者要求組裝且素材與依賴可用時，可執行後期交付：

```bash
# 智慧 TTS 配音、字幕燒錄與無縫拼接成片
python scripts/storyboard/assemble_episode.py \
  --segments segments-ep01.json \
  --videos-dir videos/ \
  --output final/ep01_final.mp4 \
  --delivery-report final/delivery-ep01.md

# 全鏈路閉環自檢
python scripts/storyboard/assemble_episode.py --self-test
```

- **語音能力依環境而定**：TTS engine 可選 `auto`、`edge` 或 `sapi`；需檢查當前安裝、平台及服務連線，不承諾每個環境都能無縫離線降級。
- 外部 `narration-epNN.md` 目前不會被組裝器解析。旁白稿可作為文字交付；要合成旁白時，先轉成組裝器支援的 inline line/narration 欄位，或交給其他剪輯工具處理。`--narration` 目前會明確回報不支援，不代表可讀取該 Markdown。
- **Windows FFmpeg 冒號轉義**：自動將 Windows 絕對路徑中的磁碟機冒號轉義為 `C\:/...`，避免 FFmpeg 字幕濾鏡語法解析崩潰。
- **音訊多軌精細混音**：利用 `adelay` 精確對齊分鏡對白起始秒數，配合 `amix` 將 H3 原生背景音壓低至 0.15 混音，確保人聲清晰乾淨。
- **無縫拼接**：依據分段時間順序自動生成 Concat 協議列表，一鍵封裝最終交付成片。

### 7.3 交付檔案清單
1. **成品影片**（`final/ep01_final.mp4`）：配音、混音、字幕燒錄無縫拼接成片。
2. **旁白與字幕稿**（`narration-ep01.md`）：可獨立交付；組裝器不會直接讀取外部 Markdown 旁白稿。
3. **剪輯時間線**（`timeline-ep01.csv`）：從編譯後 `segments-ep01.json` 執行 `layer2_to_table.py --timeline`，使用有效片長與量化後末鏡時間。Layer 2 直接匯出的表格只代表企劃名義秒數。
4. **品質審查報告**（`videos/qa-report.json`）：分段規格、色差與畫風審查報告。
5. **交付清單**：列出已生成檔案、規格核驗結果與各鏡狀態。
