# 八階段詳細流程

全程在 Agent 內部完成。每階段都有產出物，落成檔案、過驗收門才進下一階段。**小說、故事梗概一律先走階段 1 改編，不得直接當劇本用。**

---

## 階段 0：定調（Intake）

一次問完，缺哪項問哪項：

| 項目 | 選項／說明 |
|---|---|
| 集數與每集時長 | 單集 60–120 秒最常見；小說改編預設 90–120 秒 |
| 原稿類型與授權 | 小說／網文／故事梗概／已有劇本；授權狀態與用途（私人文本不外洩） |
| `genre_mode` | `xuanhuan_revenge`／`romance_emotional`／`mystery_thriller`／`comedy_slice_of_life`／`wuxia_action`／`healing_literary` |
| `target_medium` | `motion_comic` 動態漫／`ai_animation` AI 動畫漫劇／`live_action_short_drama` 真人短劇 |
| 畫風 | 從 `references/styles.md` 選一套風格鎖定錨（整部只用一套） |
| `aspect_ratio` | 9:16（預設）／16:9／1:1 |
| 語言與聲音形式 | 旁白解說／角色對白／混合／默片字幕 |
| **台詞政策（必選門禁）** | **4 選 1**：`① 原文逐字保留` / `② 只留重點句，其餘可刪（推薦）` / `③ 全部改寫為影視對白` / `④ 無台詞純旁白` |
| 交付深度 | 只到分鏡／到設定圖／到分鏡圖／到影片 |

### 階段 0 兩項必問門禁與工作紀律鐵律

1. **台詞政策門禁（4 選 1）**：
   - Agent 必須清楚區分「外部框架規則（如 Lyra 的台詞 100% 一字不差）」與「使用者真實需求」。
   - 開工前必須向使用者確認台詞政策：
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
     python scripts/adapt/estimate_duration.py --novel source/ch01.txt --target-seconds 90
     ```
     該命令使用 Unicode P 類別統一排除標點符號，精確統計有效漢字數，並一次輸出四大台詞政策下的預估片長、壓縮比與分集建議。
   - **阻斷門禁**：若估算片長 $> \text{目標片長} \times 2$，**強制在階段 0 停下，嚴禁擅自動筆！** 拋出三選一供使用者抉擇：
     - **方案 A（改編壓縮）**：採用台詞政策 ②，大刀改編壓縮原著台詞至目標容量；
     - **方案 B（拆集推進）**：將當前場次拆分為多集或上下篇製作；
     - **方案 C（接受片長）**：使用者調高目標時長預算，接受成片大幅拉長。
3. **工作紀律鐵律**：
   - **「先講秒數規劃 → 寫進檔案 → 跑完確定性自檢（E 0）→ 等使用者說『跑』才送 FreeVideo」**，嚴禁邊想邊送件燒時間。

**一鍵初始化骨架**：
```bash
python scripts/init_project.py my-drama --title "我的漫劇" --episodes 12
```
一鍵自動建立完整專案目錄，並產生包含台詞政策門禁與體量秒數反推欄位的 `project.md`，以及 `adapt/source.json`、`adapt/bible.json` 等初始規格骨架。

---

## 階段 1：改編（小說 → 可拍的漫劇結構）

**原稿是小說時必走。** 規範全文：`references/adapt/novel-to-manju.md`（對應其 Phase 0–5）。做什麼：

0. **小說大檔目錄掃描與單章清洗抽取（`extract_chapter.py`）**：
   - 若原稿為整本長篇小說大檔（幾十萬至百萬字），先掃描章節目錄結構：
     ```bash
     python scripts/adapt/extract_chapter.py source/novel.txt --list
     ```
   - 精確抽取指定卷指定章，並自動執行 Pandoc 6 重清洗（移除 Gutenberg/版權頁眉頁腳、統一破折號與省略號、縮進清理、空行壓縮、繁簡標點正規化與標題抽取）：
     ```bash
     python scripts/adapt/extract_chapter.py source/novel.txt --volume 1 --chapter 1 --out source/ch01.txt
     ```
1. **全文解析與故事地圖**：logline、主衝突、因果鏈、時間線、人物關係、世界規則、伏筆、原著內部矛盾（列出，不私自掩蓋）。長篇分批讀，不假裝讀完沒看過的章節。模板 `adapt/templates/source-analysis.md`。
2. **保留分級**：每個事件標 `MUST_KEEP`／`KEEP_IF_POSSIBLE`／`MERGE`／`COMPRESS`／`REMOVE`／`REORDER`，記原文引用與理由。
3. **A／B／C 三方案停靠**：忠於原著／節奏優先／成本優先，比較後推薦，**交使用者選**。
4. **分集架構**：`Arc → Episode → Sequence → Scene → Beat`；每集寫目標、阻礙、選擇、變化、結果、下集動機與因果債務。模板 `series-outline.md`、`episode-outline.md`。
5. **單章拆多集跨集驗收**：原著單章往往需要拆編為多集漫劇（如 1 章拆為 Ep01–Ep03），支援單集驗收與多集合併全章驗收：
   ```bash
   # 單集過濾驗收：
   python scripts/adapt/compare_adaptation.py --source adapt/source.json --script script-ep01.md --handoff handoff-ep01.json --episode 1 --h3
   # 多集多檔合併總體驗收：
   python scripts/adapt/compare_adaptation.py --source adapt/source.json --script script-ep01.md script-ep02.md --handoff handoff-ep01.json handoff-ep02.json --h3
   ```

**產出兩份 JSON 供階段 3 驗證使用**：`source.json`（原著事件與保留分級，格式見 `scripts/adapt/tests/fixtures/*/source.json`）與階段 2 的 `bible.json`（故事聖經，格式見 `scripts/adapt/tests/fixtures/story_bible.json`）。

**檢查點**：使用者選定方案、確認分集表才往下。題材細則看 `adapt/genre-modes.md`，結構節奏看 `adapt/structure-and-pacing.md`。原稿已是劇本、或是原創梗概時，跳過 1–2 步，直接做分集。

---

## 階段 2：資產聖經與設定圖

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
   - **跨章節強制鎖定同一生圖引擎**：全劇各章節（Ch01、Ch02…）的所有角色設定板、服裝三視圖與場景母片，必須強制鎖定同一個生圖工具，嚴禁混用造成畫風撕裂。
   - **Qwen-Image 2.1 嚴格限制範圍**：本機 Qwen-Image 2.1 **僅限用於階段 4 鉛筆分鏡九宮格構圖審核**，嚴禁用於階段 2 核心資產圖。
6. 出設定圖（見階段 6.1），**通過 `consistency.md` §10 驗收門**才算完成。

固定描述片段要具體到可畫：「黑色短髮、左眉尾一道疤、藏青立領風衣、右手銀戒」。避免「很帥」「氣質高雅」這類不可視化的詞。

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
  <!-- source: "第 1 章 蛇口餘生" -->
  <!-- must_keep: true -->
  <!-- change: "精簡原著長對白，強化動作打擊與巨蟒受擊反饋" -->
  人物：洛年、沈凡
  △ 狂風席捲，黑影破土而出。
  ```
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

### 4.4 分鏡工具鏈操作

```bash
# 產生 Layer 2 骨架（預設 10s/3 鏡、動作力學三要素模板、INDEPENDENT_REF2VA 四大連戲錨點）
python scripts/storyboard/handoff_to_skeleton.py handoff-ep01.json --out-dir layer2/ --max-segment-sec 10.0 --max-shots 3

# 靜態校驗與時間線表格匯出
python scripts/storyboard/validate_storyboard.py --file layer2/layer2-EP01-*.json --handoff handoff-ep01.json
python scripts/storyboard/layer2_to_table.py layer2/layer2-EP01-*.json --check --md storyboard-ep01.md --timeline timeline-ep01.csv

# 視覺化黑白鉛筆九宮格構圖審核（支援 --no-arrows 生成純淨底稿）
python scripts/storyboard/qwen_storyboard_grid.py --layer2 layer2/layer2-EP01-S01-a.json --generate-all --assemble-grid

# 單鏡修改與重抽（相鄰鏡頭吸收秒數，已審核鏡頭鎖定保護）
python scripts/storyboard/patch_shot.py --file layer2/layer2-EP01-S01-a.json --shot SH03 --shot-size CU --duration 3.5 --absorb-from SH04
python scripts/storyboard/qwen_storyboard_grid.py --layer2 layer2/layer2-EP01-S01-a.json --redraw-shot SH03 --assemble-grid
```

---

## 階段 5：提示詞包（Layer 3 編譯與 H3 官方六段式）

將 Layer 2 分鏡 JSON 結合 `assets.md` 與 `bible.json`，一鍵批次編譯為符合 MiniMax H3 官方規範的提示詞包與批次分段檔：

```bash
python scripts/storyboard/compile_layer2_to_h3.py \
  --layer2-dir layer2/ \
  --ep 1 \
  --out-md prompts-ep01.md \
  --out-json segments-ep01.json \
  --assets assets.md \
  --bible adapt/bible.json \
  --check
```

### 5.1 H3 官方六段式架構

編譯器輸出的提示詞嚴格遵照官方六段式語法結構（全中文自然語言，嚴禁任何負面詞）：
1. **`subject_definitions`**：定義參考素材與角色對應標籤（`<Picture 1>` 場景圖、`<Picture 2>` 核心角色圖）。嚴格落實**防混臉單圖排序（一段一張角色圖）**，同場其他次要角色轉為純外觀文字描述，防止多角色特徵平均化。
2. **`summary`**：整段秒數、情境氛圍與核心戲劇主旨概述。
3. **`retention_analysis`**：精確聲明各參考圖的繼承層級（如「保留 Picture 2 面部五官與服裝，服裝顏色嚴格依照設定圖」）。
4. **`detailed_description`**：`[Shot 1]` ～ `[Shot N]` 逐鏡細節，整合焦距物距、光源名詞映射、官方運鏡詞微交替、動作力學三要素與角色表情，台詞精確封裝於 `<d>角色：台詞</d>`。
5. **`overall_soundscape`**：環境音效、動作打擊音、喘息與擬音（Foley）。
6. **`non_diegetic_music`**：非附隨性配樂、BGM 風格與情緒走向。

### 5.2 切點時間軸保護與自動調諧

H3 以 24fps 影格網格為基礎，整段總時長以畫格下取整公式計算：
$$D = \frac{\text{frames\_for}(T, \text{"floor"})}{24.0}$$
若最後一鏡切點距離 $D$ 不足 2.0 秒，將觸發 H3 切點過密或末鏡渲染異常。`compile_layer2_to_h3.py` 內建自動調諧，保證：
$$D - \text{末切點} \ge 2.05s$$
確保生成時所有鏡頭皆有充裕的物理展開時長。

### 5.3 LoRA 自動適配與雙重程式對帳

- **LoRA 自動適配**：根據分鏡中的動作類型與風格標記（如劇烈打鬥、奔跑追逐），自動掛載相應的 LoRA 配置（如 Bunny 武戲滑桿、速度滑桿，停用易造成視角漂移的 camera_motion），並輸出 FreeVideo API 相容之掛載欄位。
- **雙重程式對帳（`--check`）**：在編譯完成後，自動啟動 `audit_refs_and_segments.py` 進行全流程閉環稽核：
  - **模式 A（序對對照）**：Layer 2 ↔ `prompts-epNN.md` 逐段比對參考圖、主體定義、說話者與字數預算；
  - **模式 B（13 條規則自檢）**：檢查參考圖數量、單句字數（$\le 15$ 字）、說話秒數佔比（$\le 60\%$）、切點邊界、台詞標籤對齊。雙重對帳達成 **0 Errors** 方可放行出片。

---

## 階段 6：生成（實戰定案與驗收）

### 6.0 實戰定案：獨立 Ref2VA vs 首幀流程之界限

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

### 6.1 參考圖張數與角色平均化風險防範

> **【定案 3 核心引用】使用者原話**：  
> 「這可能跟提示詞品質、以及 FreeVideo 模型訓練有關，走量化版模型可能就能多參考，之後可以嘗試」

- **實測現象**：單段若同時掛 3 張以上年齡/身形相近的角色圖（如三名普通男高中生），H3 會發生特徵融合，平均化成同一張臉；視覺差異極大者（如大胖子配黑框眼鏡）能存活。
- **建議做法**：
  - **保守預設：「一段一張角色參考圖」**。若要拍多人反應，拆成多段各自單人特寫。
  - 群戲需要時可給到 1 場景 + 最多 5 角色 = 6 張，但需認知融合風險（留待未來量化模型嘗試，不寫死為硬限制）。
  - **P0 程式稽核**：執行 `audit_refs_and_segments.py`，嚴查參考圖陣列、主體定義與說話者代號完全對齊。

### 6.2 顯存安全檢查與批次提交（`submit_h3_segments.py`）

MiniMax H3 本機出片核心工具，內建 **4.20 GiB 顯存臨界點安全保護** 與 FreeVideo 非同步任務排程：

```bash
# 1. 乾跑驗證（安全檢查 segments-ep01.json、參考圖實體路徑與當前顯存）
python scripts/storyboard/submit_h3_segments.py --segments segments-ep01.json --out-dir videos/ --dry-run

# 2. 正式批次提交（自動上傳參考圖 SHA256 快取、掛載 LoRA、輪詢進度並下載成品）
python scripts/storyboard/submit_h3_segments.py --segments segments-ep01.json --out-dir videos/
```

- **4.20 GiB (4300 MB) 顯存門禁**：提交前自動透過 `nvidia-smi` 查詢剩餘可用顯存，若不足 4300 MB 立即發出醒目警報並計算差額（避免 CUDA OOM 導致崩潰）。
- **參考圖 SHA256 快取**：同圖不重複上傳 FreeVideo，顯著加速多分段批次生成。
- **LoRA 自動適配**：直接讀取 segment 中的 `h3_loras` 參數注入請求體。
- **令牌安全**：嚴格禁止在任何終端輸出、日誌或檔案中印出 FreeVideo Token。

### 6.3 影片自動審查門禁（`verify_video_shot.py`）

支援單鏡審查與分段級（Segment-Level）批次審查，自動校驗規格並產出報告：

```bash
# 批次審查整個 Episode 的所有分段，自動串聯 color_qa.py 並輸出 qa-report.json
python scripts/storyboard/verify_video_shot.py --segments segments-ep01.json --videos-dir videos/ --qa-report videos/qa-report.json

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

一鍵執行階段 7 全鏈路後期交付：

```bash
# 智慧 TTS 配音、字幕燒錄與無縫拼接成片
python scripts/storyboard/assemble_episode.py \
  --segments segments-ep01.json \
  --videos-dir videos/ \
  --out-dir final/ \
  --output final/ep01_final.mp4

# 全鏈路閉環自檢
python scripts/storyboard/assemble_episode.py --self-test
```

- **智慧 TTS 雙重保障**：預設採用微軟 Edge-TTS 雲端高擬真人聲；遇 403 網路受阻自動無縫降級為 Windows 原生 SAPI（`System.Speech.Synthesis`），100% 離線可用。
- **Windows FFmpeg 冒號轉義**：自動將 Windows 絕對路徑中的磁碟機冒號轉義為 `C\:/...`，避免 FFmpeg 字幕濾鏡語法解析崩潰。
- **音訊多軌精細混音**：利用 `adelay` 精確對齊分鏡對白起始秒數，配合 `amix` 將 H3 原生背景音壓低至 0.15 混音，確保人聲清晰乾淨。
- **無縫拼接**：依據分段時間順序自動生成 Concat 協議列表，一鍵封裝最終交付成片。

### 7.3 交付檔案清單
1. **成品影片**（`final/ep01_final.mp4`）：配音、混音、字幕燒錄無縫拼接成片。
2. **旁白與字幕稿**（`narration-ep01.md`）：時間碼精確標註。
3. **剪輯時間線**（`timeline-ep01.csv`）：由 `layer2_to_table.py --timeline` 產生。
4. **品質審查報告**（`videos/qa-report.json`）：分段規格、色差與畫風審查報告。
5. **交付清單**：列出已生成檔案、規格核驗結果與各鏡狀態。
