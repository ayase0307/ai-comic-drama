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
   - **阻斷門禁**：若估算片長 $> \text{目標片長} \times 2$，**強制在階段 0 停下，嚴禁擅自動筆！** 拋出三選一供使用者抉擇：
     - **方案 A（改編壓縮）**：採用台詞政策 ②，大刀改編壓縮原著台詞至目標容量；
     - **方案 B（拆集推進）**：將當前場次拆分為多集或上下篇製作；
     - **方案 C（接受片長）**：使用者調高目標時長預算，接受成片大幅拉長。
3. **工作紀律鐵律**：
   - **「先講秒數規劃 → 寫進檔案 → 跑完確定性自檢（E 0）→ 等使用者說『跑』才送 FreeVideo」**，嚴禁邊想邊送件燒時間。

沒說就採預設並明告：單集 90 秒、3D 國漫、9:16、繁體中文、台詞政策 ②、交付到分鏡圖。產出 `project.md`（欄位見 `scripts/init_project.py` 模板）。

---

## 階段 1：改編（小說 → 可拍的漫劇結構）

**原稿是小說時必走。** 規範全文：`references/adapt/novel-to-manju.md`（對應其 Phase 0–5）。做什麼：

1. **全文解析與故事地圖**：logline、主衝突、因果鏈、時間線、人物關係、世界規則、伏筆、原著內部矛盾（列出，不私自掩蓋）。長篇分批讀，不假裝讀完沒看過的章節。模板 `adapt/templates/source-analysis.md`。
2. **保留分級**：每個事件標 `MUST_KEEP`／`KEEP_IF_POSSIBLE`／`MERGE`／`COMPRESS`／`REMOVE`／`REORDER`，記原文引用與理由。
3. **A／B／C 三方案停靠**：忠於原著／節奏優先／成本優先，比較後推薦，**交使用者選**。
4. **分集架構**：`Arc → Episode → Sequence → Scene → Beat`；每集寫目標、阻礙、選擇、變化、結果、下集動機與因果債務。模板 `series-outline.md`、`episode-outline.md`。

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
5. 出設定圖（見階段 6.1），**通過 `consistency.md` §10 驗收門**才算完成。

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
- 劇本定稿後鎖定場景防誤改：
  ```bash
  python scripts/adapt/sync_script.py --handoff handoff-ep01.json --scene EP01-S01 --set-status approved --note "導演審核通過"
  ```
- 當在 Markdown 劇本（`script-ep01.md`）修改對白或動作時，一鍵同步至 handoff（未鎖定場景自動增版更新，已鎖定場景自動攔截防覆蓋）：
  ```bash
  python scripts/adapt/sync_script.py --handoff handoff-ep01.json --script script-ep01.md
  # 若需強制解鎖再改：
  python scripts/adapt/sync_script.py --handoff handoff-ep01.json --scene EP01-S01 --unlock
  ```

**必跑驗證**（任一閘門觸發即退稿重寫，≥ 80 分且 0 閘門才過）：

```bash
python scripts/adapt/validate_structure.py --script script-ep01.md --handoff handoff-ep01.json
python scripts/adapt/estimate_duration.py --script script-ep01.md --genre xuanhuan_revenge --target-seconds 90
python scripts/adapt/check_continuity.py --bible bible.json --handoff handoff-ep01.json
python scripts/adapt/compare_adaptation.py --source source.json --script script-ep01.md --handoff handoff-ep01.json
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
# 產生 Layer 2 骨架並進行靜態驗證
python scripts/storyboard/handoff_to_skeleton.py handoff-ep01.json --out-dir layer2/
python scripts/storyboard/validate_storyboard.py --file layer2/layer2-EP01-*.json --handoff handoff-ep01.json
python scripts/storyboard/layer2_to_table.py layer2/layer2-EP01-*.json --check --md storyboard-ep01.md --timeline timeline-ep01.csv

# 視覺化黑白鉛筆九宮格構圖審核（支援 --no-arrows 生成純淨底稿）
python scripts/storyboard/qwen_storyboard_grid.py --layer2 layer2/layer2-EP01-S01-a.json --generate-all --assemble-grid

# 單鏡修改與重抽（相鄰鏡頭吸收秒數，已審核鏡頭鎖定保護）
python scripts/storyboard/patch_shot.py --file layer2/layer2-EP01-S01-a.json --shot SH03 --shot-size CU --duration 3.5 --absorb-from SH04
python scripts/storyboard/qwen_storyboard_grid.py --layer2 layer2/layer2-EP01-S01-a.json --redraw-shot SH03 --assemble-grid
```

---

## 階段 5：提示詞包（Layer 3 編譯）

把 Layer 2 逐段逐鏡編譯成目標模型語法，寫進 `prompts-epNN.md`。

- H3 Ref2VA 採用官方六段式結構（`subject_definitions` / `summary` / `retention_analysis` / `detailed_description` / `overall_soundscape` / `non_diegetic_music`）。
- **強制執行程式對帳（P0）**：`reference_images` ↔ `subject_definitions` ↔ `retention_analysis` ↔ 說話者 `(Sx)` 必須由同一支程式（`audit_refs_and_segments.py`）一次產生並逐條稽核。
- 嚴禁負面詞，改用正面描述（見 `references/minimax-h3.md`）。

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

### 6.2 影片自動審查門禁（`verify_video_shot.py`）

```bash
python scripts/storyboard/verify_video_shot.py --videos-dir videos/ --layer2 layer2/layer2-EP01-S01-a.json --write-back
```
四大自動攔截檢驗：
1. **時長與規格**：實際秒數與規劃誤差 $\le 0.5\text{s}$。
2. **彩度防灰階滲透**：$C^* \ge 10.0$，防止鉛筆草圖滲漏成黑白片。
3. **九宮格分屏線殘留**：抽樣影格 $1/3, 2/3$ 無暗黑格線分割。
4. **跨鏡色彩連貫性**：相鄰鏡頭色盤 $dE_{76} \le 25.0$。

---

## 階段 7：組裝交付與配音決策

### 7.1 配音分層決策（實戰關鍵）

實測 MiniMax H3 原生中文配音之語音辨識（ASR）置信度僅在 **0.43–0.54**，普遍存在字音模糊、發音吞字、急促搶跑或偶發 -40dB 靜音。
提示詞中保留 `<d>` 標籤，是為了提供影片生成時**嘴部開合與時間點的物理對齊錨點**。在階段 7 組裝時，提供以下三選一決策：

- **方案 A（推薦）**：**抽離 H3 人聲軌，使用高品質外部 TTS（如 Edge-TTS、CosyVoice）重配中文台詞，再用 ffmpeg 混回環境音效軌**。口型與語義兼得。
- **方案 B**：保留 H3 原生配音，透過 ffmpeg 強制燒錄清晰中文字幕。
- **方案 C**：全片去台詞化，改為純旁白講解。

### 7.2 交付檔案清單
1. **旁白與字幕稿**（`narration-ep01.md`）：時間碼精確標註。
2. **剪輯時間線**（`timeline-ep01.csv`）：由 `layer2_to_table.py --timeline` 產生。
3. **拼接成片**：ffmpeg 串接、混音與字幕壓制。
4. **交付清單**：列出已生成檔案、規格核驗結果與未完成鏡號。
