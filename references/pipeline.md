# 八階段詳細流程

依使用者指定的交付範圍選擇階段；只要文字劇本、分鏡或提示詞時，可停在該階段並交付 draft，不要求圖片或影片生成。小說改編依使用者要求進入改編流程，不把完整八階段當成每項任務的必經步驟。

文字規劃、Python 本機檢查、圖片生成與影片生成是不同能力層。先以 `python scripts/check_environment.py` 檢查本機工具；`python scripts/run_offline_checks.py` 執行離線檢查。這些命令不檢查 provider 帳戶、token 或模型生成能力。FreeVideo 是可選 adapter，影片生成要以當前 Agent 或已連線後端實際可用為準。

階段狀態只記錄於 `review/project-state.json`，每次核准綁定輸入 hash，修改後必須重審。stage 4 review 核准是 H3 compiler 前置條件；實際 submit 要求 stage 5 核准。QA 技術通過不會自動成為人工核准。

**每個階段的斷點都是同一套做法**：產物齊了先跑 `build_stage_review.py --project-dir . --stage N` 綁定審核快照（同時寫出 `review/stage-N-*.html` 除錯頁），再用 `h3d inbox --root .` 產生決策收件匣 `review/inbox.html` 交給使用者並停下；使用者回覆「通過」後才 `--approve-stage N`。階段 0、2 把舊頁當附錄一起給（要人看設定與臉）。

- 審查頁規格（版面順序、卡片欄位、禁止事項）：`references/review-page-spec.md`。

---

## 階段 0：定調（Intake）

只詢問當前交付所缺少且會阻礙工作的項目；沿用使用者已給的 brief、模型與參數，不重複詢問。純文本或分鏡交付不要求先收齊出片參數。

| 項目 | 選項／說明 |
|---|---|
| 成片形式（`series_format`） | **預設＝長篇漫劇**：整部一支連續長片，把故事講清楚優先，每個原著關鍵事件交代起因→經過→結果（含動機、時地轉換），**沒有單集秒數、不以秒數壓縮事件**；總長依事件數與交代需求估（`estimate_duration.py --events`）。使用者明確要求分集時，每集＝完整劇情單元，長度由要交代的事件決定。**短劇短集（opt-in）**：使用者明確選擇才用（`h3d decide series_format short`），每集 1–2 分鐘（預設 90 秒 ±15%）、強鉤子；超出時走「接受（寫入 `accepted_duration_seconds`）／於場次邊界拆集／刪非因果內容」三選一。不必主動問集數秒數 |
| 原稿類型與用途 | 小說／網文／故事梗概／已有劇本；依當前任務確認需要的來源與處理方式 |
| `genre_mode` | `xuanhuan_revenge`／`romance_emotional`／`mystery_thriller`／`comedy_slice_of_life`／`wuxia_action`／`healing_literary` |
| `target_medium` | `motion_comic` 動態漫／`ai_animation` AI 動畫漫劇／`live_action_short_drama` 真人短劇 |
| 畫風 | **預設推 14 號「古風寫實厚塗・電影感」（`xianxia-cinematic-semireal`，附樣圖）**，使用者可改選 `references/styles.md` 任一套（整部只用一套）；角色設定板選項 `xianxia-cinematic-semireal`／`master`（3D 漫劇寫實厚塗）／`semi-real`（UE5 半寫實）／styles 編號，寫入 `assets.md` 的 `style_index`，並 `h3d decide style` 定案 |
| `aspect_ratio` | 9:16（預設）／16:9／1:1 |
| 語言與聲音形式 | 旁白解說／角色對白／混合／默片字幕 |
| 台詞政策（**固定，不詢問**） | **原著對白優先**：原著對白全保留、脫水不刪事件；只轉述的對話可補寫並標 `invented`；旁白＝主角內心聲（VO ≤30%）。規格見 `references/adapt/dialogue-first-adaptation.md`。不再出①–④四選一；舊專案已定案的 ①–④ 仍可讀（④ 編譯時仍等同 `--narration-policy external`） |
| 交付深度 | 只到分鏡／到設定圖／到分鏡圖／到影片 |
| 交付範圍（`delivery_scope`，選填） | `h3d decide delivery_scope <預設值> --quote "<使用者原話>"`：`script-only`（終點階段 3）／`storyboard-only`（4）／`prompts-only`（5）／`full`（7，沒定案就是全流程）；另可加 `no_image`（階段 2 改檢文字設定卡，不要求設定圖檔）、`no_video`（終點壓到 5，不送件）、`trial_segments`／`max_segments`（只送指定段）。值可直接給 JSON 物件，例如 `'{"end_stage": 4, "no_image": true}'`。`h3d next` 到終點階段就回報 done。 |

### 階段 0 按需求選用的台詞與體量檢查

1. **台詞政策（固定，不詢問）**：一律走「原著對白優先」（`references/adapt/dialogue-first-adaptation.md`）。開案與執行中都不問改寫方式；新增事件、合併事件、改視角、提前揭懸念預設禁止並記帳，不提案。每集長度用台詞預算排（`dialogue_budget.py`：150 秒＝450–540 字，未達下限就接下一場），交稿前跑 `adapt_gate.py`。
2. **原文體量反推片長公式（先算再動工）**：
   - 實測中文口播極限安全值為 **4 字／秒**（常速 3.8 字/秒）：
     $$\text{純念台詞秒數} = \frac{\text{台詞字數}}{4}$$
     $$\text{總片長估算} \approx \text{純念台詞秒數} \times 1.6 \quad \text{（含動作反應、氣口與鏡頭呼吸）}$$
   - **命令列確定性試算**：
     ```bash
     python scripts/adapt/estimate_duration.py --novel --novel-file source/ch01.txt
     # 短劇短集模式（使用者明確選擇）才加單集目標：--format short --target-seconds 90
     ```
     該命令使用 Unicode P 類別統一排除標點符號，精確統計有效漢字數，並一次輸出四大台詞政策下的預估片長。長篇模式只報整部總長（分鐘），不換算集數、不做單集門禁；短劇模式才輸出集數建議與「> 單集目標 × 2」阻斷。
   - **體量提示**：估算結果只用來核對原著體量；不據此詢問改寫方式，也不據此刪台詞。
     - **方案 B（接受片長，長篇預設）**：事件都要講清楚，接受成片拉長；
     - **方案 C（分集）**：只有使用者明確要求時才拆成多集（每集＝完整劇情單元）或改走短劇短集模式。
3. **工作紀律鐵律**：
   - 生成任務先確認交付、當前可用後端與需要的參數；沒有生成要求時停在文字交付。

**一鍵初始化骨架**：
```bash
python scripts/init_project.py my-drama --title "我的漫劇"
# 使用者要求分集：--episodes 3（每集＝完整劇情單元）；短劇短集（使用者明確選擇）：--format short --episodes 12 --episode-seconds 90
```
一鍵自動建立完整專案目錄，並產生包含成片形式（預設長篇漫劇）、台詞政策門禁、體量反推欄位與事件清單的 `project.md`，以及 `adapt/source.json`、`adapt/bible.json` 等初始規格骨架。

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
     python scripts/adapt/validate_character_bible.py --bible-md adapt/character-bible.md --bible-json adapt/bible.json
     ```
   - **綁定階段 1 審核快照、交收件匣並停下**：
     ```bash
     python scripts/build_stage_review.py --project-dir . --stage 1
     h3d inbox --root .
     ```
     Agent 必須主動停下，把 `review/inbox.html` 交給使用者，取得核准後才可進入階段 2；`review/stage-1-adaptation.html` 只作除錯／對帳。
2. **全文解析與故事地圖**：logline、主衝突、因果鏈、時間線、人物關係、世界規則、伏筆、原著內部矛盾（列出，不私自掩蓋）。長篇分批讀，不假裝讀完沒看過的章節。模板 `adapt/templates/source-analysis.md`。
3. **保留分級＋交代需求**：每個事件標 `MUST_KEEP`／`KEEP_IF_POSSIBLE`／`MERGE`／`COMPRESS`／`REMOVE`／`REORDER`，記原文引用與理由；並在 `source.json` 每個事件標要交代的要素（`exposition_needs`，省略＝起因、經過、結果；`needs_motivation`、`time_place_shift`）。依事件估總長：
   ```bash
   python scripts/adapt/estimate_duration.py --events adapt/source.json
   ```
4. **改編方案固定為忠於原著**（不再出 A／B／C 讓使用者選）：原著對白全保留、事件不刪不併；節奏靠台詞密度與分集，不靠刪內容。
5. **全劇架構（預設不分集）**：長篇預設 `Arc → Sequence → Scene → Beat`，整部一支連續長片；使用者要求分集才加 `Episode` 層，每集＝完整劇情單元。每段（或每集）寫目標、阻礙、選擇、變化、結果、下一段動機與因果債務。模板 `series-outline.md`、`episode-outline.md`。
6. **事件交代完整性檢查（必做）**：改編稿每場用 `event_exposition` 標明替哪個事件交代了哪些要素，再逐條對帳：
   ```bash
   python scripts/adapt/event_coverage.py --project-dir . --out adapt/event-coverage.md
   ```
   被壓縮（compressed）、被跳過（skipped）、交代不全（partial）、未標註（unverified）的事件**由 Agent 依原著補回並重跑**（不問使用者；收件匣的「事件交代」卡只作知會，明細在 `review/stage-1-adaptation.html`）；MUST_KEEP 事件完全沒交代（missing）時結束碼 2。
7. **（使用者要求分集時）跨集驗收**：原著單章拆成多集時（如 1 章拆為 Ep01–Ep03），支援單集驗收與多集合併全章驗收：
   ```bash
   # 單集過濾驗收：
   python scripts/adapt/compare_adaptation.py --source adapt/source.json --script script-ep01.md --handoff handoff-ep01.json --episode 1 --h3
   # 多集多檔合併總體驗收：
   python scripts/adapt/compare_adaptation.py --source adapt/source.json --script script-ep01.md script-ep02.md --handoff handoff-ep01.json handoff-ep02.json --h3
   ```

**產出兩份 JSON 供階段 3 驗證使用**：`source.json`（原著事件與保留分級，格式見 `scripts/adapt/tests/fixtures/*/source.json`）與階段 2 的 `bible.json`（故事聖經，格式見 `scripts/adapt/tests/fixtures/story_bible.json`）。

**檢查點**：使用者選定方案、確認事件交代完整性表（及使用者要求的分集表）才往下。題材細則看 `adapt/genre-modes.md`，結構節奏看 `adapt/structure-and-pacing.md`。原稿已是劇本、或是原創梗概時，跳過 1–2 步，直接做分集。

---

## 階段 2：資產聖經與設定圖（左右並排審核斷點）

一致性的根基。規範全文：**`references/consistency.md`**（ID、設定板版面、表情集、服裝、場景主圖、道具、音色、參考鏈、驗收門）。

1. 用小說改編技能的**故事聖經**（`adapt/character-and-world-bible.md`、`templates/story-bible.md`）當角色資料來源；改編新增設定標【改編新增】。
2. 寫 `assets.md`：先寫全域鎖（風格錨、負面錨、光色句、五色色票），再寫角色／服裝／場景／道具／特效／音色條目，每條有 ID 與固定描述片段。
   - **每個劇本寫到的特效都要有自己的特效卡**（id 以 `B-` 開頭，明寫 `類型：特效` 或 `類型：光效`，並補 `光源：…`／`source_en` 與 `設定圖`）。特效沒有已審核參考圖就不得進階段 5（audit **E56**），`pack_waivers` 不能豁免特效。
3. **非人生物／怪獸設定圖（Creature Sheet）規格升級（實戰教訓）**：
   - 奇幻、玄幻或科幻中的巨獸、妖物、坐騎（如巨蟒、白獸、魔狼）享有與人類角色同等的規格。
   - **必須生成純灰/純白單色背景的三視圖**（左側頭部特寫／右側全身姿態／皮膚花紋鱗片細節）。
   - **⛔ 嚴禁拿帶場景背景的劇照或畫作當生物參考圖**！實測證明，帶背景的生物參考圖會把背景巷子、森林殘留強行染色並黏著帶進成片的所有其他場次，破壞空間一致性。
4. **演員表排序鐵律（實戰教訓）**：
   - 填寫每段分鏡與提示詞的演員表時，**嚴格按「這一場誰是主角/核心」排序**，而非按誰先想到或人類先於生物。
   - 生物（巨蟒、白獸等）在誕生、威脅或主戰場次往往是核心，必須排在第一位（`subject 1`），避免被 H3 參考圖上限或注意力機制稀釋擠掉。
5. **核心資產生圖工具詢問與跨章節鎖定鐵律**：
   - **偵測後詢問，不自行預設**：出核心資產圖前先跑 `h3d imagegen --detect --stage 2 --root .`（`h3d next` 缺 `design_engine` 時也會帶出偵測結果），把偵測到可用的工具（Codex CLI／Grok GenerateImage／手繪上傳；不可用的附原因）交給使用者選，**只偵測到一個可用也要問**；使用者回覆後 `h3d imagegen --set <後端> --stage 2 --quote "<使用者原話>" --root .` 寫進 `design_engine`。選了但之後不可用時 `h3d next` 會警告並重新詢問（`references/tooling.md` §2.4.1）。
   - **跨章節工具選擇**：若使用者要求跨章節風格一致，記錄已選工具及可重用的風格參考；依每個工具實際能力安排工作，不強制使用特定引擎。
   - Qwen、手繪或其他可用圖像工具可依任務製作設定圖或分鏡構圖圖；同一張圖是否可用於後續生成依目標模型能力判斷。
6. **組裝角色設定板提示詞再生圖**：角色卡填好 `設定板描述`、`背面特徵`（`init_project.py` 範本已含），**問風格的方式（P0）**：依題材從 `references/styles.md`「角色設定板預設風格」的推薦挑 2–3 個，附上樣圖（`assets/styles/sheet-*.jpg`）與一句話差別，一次問一個問題；**全片風格鎖與設定板風格合併成同一個選擇**，不要分開問。預設推 14 號「古風寫實厚塗・電影感」；沒有選定時 `export_asset_prompts.py` 會用 14 號並在 stderr 提醒，開工前仍要讓使用者確認。
   **風格要在階段 0 與使用者確認後**寫進「風格錨點」區的 `style_index`：`14`／`xianxia-cinematic-semireal`（**預設**，古風寫實厚塗・電影感）／`master`（母版 3D 漫劇寫實厚塗，偏插畫感）／`semi-real`（UE5 半寫實東亞，更接近真人質感）／`1`–`11`（`styles.md` 編號）。沒寫時匯出用預設 14 號並提醒，開工前仍先問。選 14 號時每段都要綁設定圖或場景圖（audit E28）。然後：
   ```bash
   python scripts/storyboard/export_asset_prompts.py --assets-md assets.md --out-json images/asset_prompts.json --out-md images/asset_prompts.md
   # 使用者選 codex 時（design_engine=codex）；選 grok 時匯出會另產 images/grok-manifest.json，選手繪則請使用者上傳到登記路徑
   python scripts/storyboard/run_codex_asset_gen.py --prompts images/asset_prompts.json --output-dir images --model <使用者指定模型>
   ```
   角色提示詞用 ai-image-prompt 四視圖母版（構圖不改、含防呆句）；`--style <選項>` 可臨時覆蓋 `style_index`。舊版匯出檔（缺 `template` 標記）runner 會警告，需重跑匯出。
7. **綁定階段 2 審核快照、交收件匣與附錄並停下（P0 鐵律）**：
   - 生成資產圖後，**必須執行**：
     ```bash
     python scripts/build_stage_review.py --project-dir . --stage 2
     h3d inbox --root .
     ```
   - `review/inbox.html` 的「階段 2 等你核准」卡內嵌本批設定圖；`review/stage-2-assets.html` 是**附錄**（左側角色設定表格、右側設定圖，可全螢幕放大，缺圖紅框），階段 2 永遠要人看臉，所以兩者一起給。
   - **Agent 必須立即停下**，請使用者確認每位角色臉型、服裝無誤，使用者發出明確核准指令方可進入階段 3！嚴禁未經確認私自往下推進！

---

## 階段 3：漫劇劇本（改寫成可拍劇本；長篇預設整部一份連續劇本，分集時才每集一份）

規範：`adapt/screenplay-format.md`、`visual-writing.md`、`dialogue-and-audio.md`、`filmability-and-cost.md`（對應 Phase 6–9）。重點：

- **劇本管戲，分鏡管拍**：劇本用中文場號制（`第XX集｜標題`、`M-N 場景名 時/內外`、`人物：`、`△` 動作行、`角色名（括注）：對白`），**正文不出現攝影機術語**與模型提示詞。
- **100% 視聽外化**：心理活動轉成動作、道具、空間位階、言行不一；內心獨白 ≤ 單集對白行的 15%。
- 每場寫清「進場極性 → 衝突行動 → 資訊變化 → 出場極性」。單場核心互動角色預設 ≤ 3 人；多人混戰、複雜物理給「原版／AI 簡化」雙案。
- 對白單句 > 28 字警告、> 35 字阻斷（字幕可讀性）；時長與目標（或 `accepted_duration_seconds`）的偏差在審核頁「時長對帳」呈現；階段 3 就要核准偏差，不要拖到階段 4。長篇模式（預設）片長跟著事件交代需求走：多出的若是交代鏡頭就接受實際長度，只刪冗餘，不刪事件交代。
- 每場用 `<!-- exposition: U01 起因 經過 -->` 標出替哪個事件交代了什麼，改完重跑 `event_coverage.py`，確認沒有新的交代缺口。
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
  <!-- exposition: U01 起因 經過 結果 -->
  人物：洛年、沈凡
  △ 狂風席捲，黑影破土而出。
  ```
- **事件交代註解**：`<!-- exposition: U01 起因 經過 -->` 表示這場戲替事件 U01 交代了哪些要素（起因／經過／結果／動機／時地），同步後寫入 handoff 的 `event_exposition`，供 `event_coverage.py` 檢查事件交代完整性。
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

# 2. H3 實戰台詞預算與時長審計（角色語速、單句 ≤18 字建議、說話佔比 75–90%，>90% 警告）
python scripts/adapt/estimate_duration.py --script script-ep01.md --genre xuanhuan_revenge --h3
# 短劇短集模式（使用者明確選擇）才帶單集目標：--format short --target-seconds 90

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
  - 估時依角色：**男主 4.0、女角 4.5、旁白／畫外 5.5 字／秒**（對嘴上限 4.7；`estimate_duration.py --male-lead 名字`、分鏡交接 `voice_role`）；單句建議 $\le 18$ 字、硬上限 35 字；說話窗口＝字數÷角色語速＋0.3 秒（最低 1.2 秒）；同場兩句空隙 **0.1–0.9 秒**（情緒落點 `beat_pause` 0.6–1.2 秒），切鏡後 **0.5 秒內開口**。
  - **文戲說話秒數目標 75–90%（#118），>90% 才 WARN**；對話段整段密度（字數÷片長）目標 **3.0–3.6 字／秒**，<2.8 或 >3.9或每 15 秒開口 <6 次 → WARN；猛烈動作碰撞鏡頭嚴禁排台詞（喘息放 `overall_soundscape`）。
  - **無台詞鏡**：單鏡 >5 秒、連續無台詞 >10 秒 → WARN（禁拉伸湊時）。
  - **v118 實測對齊（舊規則改成和上面一致）**：
    - 鏡長：每鏡（含首切點、相鄰切點、17n+5 取整後的末鏡）≥1.2 秒合規（`h3_spec.MIN_SHOT_SEC`）；1.2–2.0 秒只在 `compile_notes`／audit `W:E4 短鏡` 提醒（上游 H3 指南 ≥2 秒，未實測）。
    - 取整收尾：對話段預設往上取 17n+5；若往下取一格仍能念完末句（句後 ≥0.1 秒）且更接近分鏡寫的句後留白（≥0.3 秒），改往下取（`rounding_reason: tail-fit`；`metadata.disable_tail_fit: true` 關閉）。
    - 同鏡接話：`dialogue_and_audio.extra_lines[]`（`speaker`、`line_verbatim`、`speech_window`、`voice_4d_spec_en`），編譯器逐句給 `<d>`、前一位說話人閉嘴；D2 密度與語速閘門都把接話算進去。
    - 分鏡語速閘門（validate）：畫內 >4.7 字/秒 FAIL、>4.5 WARN；旁白／內心 VO >5.8 FAIL、>5.5 WARN（以鏡長計；舊 4.2 一律線取消）。
    - `pacing_gate`：給了 `shots` 時密度分母扣段首／段尾連續無台詞鏡（最多 5 秒，同 D2）；原著無台詞動作鏡標 `source_action: true` 不計入有人聲鏡比例；`beat_pause` 句的切鏡後開口可到 1.2 秒（同 D4）。
    - **原著無台詞動作鏡**（劇本 `△【動作】`，一個標記＝一個主要動作）：骨架獨立成鏡、鏡長＝標記秒數，台詞估時不壓縮；`pacing_gate`（`source_action` 鏡拿掉後再算空隙／開口／密度／有人聲鏡比例）、validate D1–D4 不計；validate D5 核對標記數／合併／截短，D6 擋一鏡塞 ≥3 個動作（`references/storyboard/cinematic-director.md`）。
    - **無廢片**（不生成之後要剪掉的秒數：`tail_freeze_hold` 預設關、收尾在末句後 0.3 秒）的**唯一例外是 E3 雙人引子**（`shots[0].dual_lead_in`，`references/storyboard/spatial-consistency.md` §7）：段縫硬切到單人近景時多生成 2.0 秒雙人鏡、組裝剪掉。依據：T4 同段同種子 12 個樣本跑位／重演 0/12（不加引子 4/12），2 秒引子比整段重生便宜。節奏閘門（`pacing_gate` 密度／有人聲鏡比例／切鏡後開口／開口次數、validate D1–D4、說話佔比、段長提醒、audit W13）都不計引子那一鏡，段長扣掉引子秒數。
  - **硬門禁（FAIL）**：句間空隙 >1.5 秒、單句 >35 字、提示詞含 `slow`（含 `slow motion`、`no slow motion`、`at slow speed`、`slow push`；揭露／定格鏡標 `allow_slow` 例外）。機檢見 `scripts/storyboard/pacing_gate.py`。
  - **提示詞寫法保留**：動作鏈（施力點→傳導→受擊反應）＋逐句時間錨點（`[0.0–1.8s]` 開口時間），正向寫 `real-time speed, natural brisk motion`。
- **動作力學三要素（分鏡「動作」欄必填）**：
  1. **① 施力點**：動作從何處發起（手腕下壓、腳跟蹬地、蛇尾蓄力捲縮）；
  2. **② 傳導路徑**：力量如何經身體傳遞、肌肉/鱗片變形與重心轉移（肩胛後縮、腰部擰轉、鱗片緊繃反光）；
  3. **③ 受擊反應與環境反饋**：受力後退距離、結構折疊挫傷、立刻反擊或掙扎，以及環境特效（碎石揚塵、環形氣浪、風切位移空氣、撞擊火花）。

### 4.4 分鏡工具鏈操作與分鏡總覽圖審核斷點（P0 強制斷點）

> **構圖規格（2026-10 定案）**：階段 4 不再硬性要求 3×3 九宮格。做法是逐鏡一張 panel（`panels/panel-*.png`），再依段拼成總覽 `images/grid-<seg>.png`，格數跟段內鏡數（1→1×1、2→2×1、3→3×1、4→2×2、5–6→3×2、7–9→3×3）。影片分屏黑線偵測（verify_video_shot）照舊保留。


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

# 3. 構圖：生圖工具由使用者選，不自行預設。先偵測、把可用的（不可用的附原因）交給使用者選，只有一個可用也要問
python scripts/h3d.py imagegen --detect --stage 4 --root .
python scripts/h3d.py imagegen --set <codex|qwen|manual> --stage 4 --quote "<使用者原話>" --root .   # 寫進 storyboard_engine
#   codex：Codex 分鏡，每鏡綁定已核准參考圖，--model 必填（使用者指定的模型）；單鏡重畫 --shots EP01-S03-a-SH02
python scripts/storyboard/codex_storyboard_panels.py --root . --episode EP01 --model <使用者指定模型> --parallel 3
#   qwen：經本機 FreeVideo 的 Qwen-Image 黑白鉛筆分鏡總覽圖
python scripts/storyboard/qwen_storyboard_grid.py --layer2 layer2/layer2-EP01-S01-a.json --generate-all --assemble-grid
#   manual：使用者手繪或其他已授權工具提供對應 shot 的 PNG，並在 Layer 2 設定 sketch_file
# 已選的工具之後不可用時，h3d next 會警告並重新詢問

# 4. 單鏡修改與重抽（若構圖不佳，微調秒數或重新繪製）
python scripts/storyboard/patch_shot.py --file layer2/layer2-EP01-S01-a.json --shot SH03 --shot-size CU --duration 3.5 --absorb-from SH04
python scripts/storyboard/qwen_storyboard_grid.py --layer2 layer2/layer2-EP01-S01-a.json --redraw-shot SH03 --assemble-grid

# 5. 綁定 stage 4 審核快照、交收件匣並停下；只有使用者確認後才記錄核准
python scripts/build_stage_review.py --project-dir . --stage 4
h3d inbox --root .
python scripts/build_stage_review.py --project-dir . --approve-stage 4
```

> **自動建議：母片底四格構圖板（W46，只建議）**：分鏡定稿後跑 `python scripts/h3d.py staging --root . --layer2`（階段 4 審核頁也會列在「💡 自動建議」）。室內固定場景、已驗收場景母片、≥2 名角色有固定座位／站位、段內有近景或特寫（景別看不到門洞／桌位這類定位結構）、有台詞的文戲段，會建議把該段構圖改成「以場景母片為底重畫的四格構圖板」；武戲、單人、戶外與判不了的段不建議。採用時照 `references/storyboard/spatial-consistency.md` §3：板一律以已驗收母片為底重畫＋店感鎖，整板當參考須 `reference_view: "panel"`＋`panel_label_en`。證據是方向性（老易實驗 D′ 15/16 vs 單用母片 6/8，未達 +25 門檻），所以不擋核准、不改預設編譯；逐鏡 panel＋grid 總覽仍是給人審的，不因建議而改送件流程。

> **stage 4 審核門**：要進入 H3 編譯，每鏡須有對應的有效分鏡總覽圖／單格 PNG，並通過人工 review。圖可由 Qwen、手繪或其他工具製作，需遵循相同 shot 對應與 hash 審核。文字分鏡 draft 可以先交付，不必生成圖或影片。

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
1. **`subject_definitions`**：定義參考素材與角色對應標籤（`<Picture 1>` 場景圖、`<Picture 2>` 核心角色圖）。Ref2VA 預設**防混臉單圖排序**（只為 `face_subject_ids` 掛臉部參考圖，沒有綁定時 `--max-char-refs` 預設 1），同場其他次要角色轉為純外觀文字描述。「一段一張臉」已不是通則（D3）：新流程用 remix 角色卡維持多人一致，見 `references/consistency.md` §7.1。
2. **`summary`**：整段秒數、情境氛圍與核心戲劇主旨概述。
3. **`retention_analysis`**：精確聲明各參考圖的繼承層級（如「保留 Picture 2 面部五官與服裝，服裝顏色嚴格依照設定圖」）。
4. **`detailed_description`**：`[Shot 1]` ～ `[Shot N]` 逐鏡細節，整合焦距物距、光源名詞映射、官方運鏡詞多樣化子句（**杜絕重複運鏡句與語法錯誤**）、動作力學三要素與角色表情，台詞精確封裝於 `<d>角色：台詞</d>`。**徹底消滅「Then the motion transitions smoothly.」等罐頭廢話**。
5. **`overall_soundscape`**：環境音效、動作打擊音、喘息與擬音（Foley）。
6. **`non_diegetic_music`**：非附隨性配樂、BGM 風格與情緒走向。**同一場戲有多段時一律寫 `N/A`**，配樂到後製統一鋪；相鄰段各寫配樂會被 `--check` 的 C4 提醒（見 `references/edit/manju-editing-playbook.md` §8.1）。

### 5.2 服裝狀態機（`wardrobe_states`）解析
編譯器依 Layer 2 `asset_refs.characters[].costume_id` 綁定服裝圖，來源為 `bible.json` 的 `wardrobe_states`，或 `assets.md` 角色卡的：
```markdown
- **服裝**：`W-chenshi-01` `pale lotus-pink jacket`；`W-chenshi-02` `same outfit smeared with mud`
- **服裝設定圖**：`W-chenshi-02` `images/char-chenshi-street.png`
```
參考圖路徑相對專案根目錄（`--project-root`），`--check` 會檢查檔案是否存在。設定板用語（純灰底、three-view）會自動從影片提示詞剔除。

### 5.3 物理門禁與雙重程式對帳
- **stage 4 gate**：編譯前要求 stage 4 有效核准，且輸入 Layer 2 與對應構圖 PNG 仍符合核准 hash；編譯不支援跳過 gate。
- **雙重程式對帳（`--check`）**：調用 `audit_refs_and_segments.py` 執行 18 條自檢與參考圖對帳，達成 **0 Errors** 方可放行出片。

### 5.4 旁白與畫外句（唯一政策：`h3-native`）

H3 的聲音與畫面在同一次 forward 生成，輸出是**單一 32 kHz 立體聲混音軌，沒有分軌，也沒有關閉音訊的參數**【官方，[MiniMax-H3 官方 repo](https://github.com/MiniMax-AI/MiniMax-H3)】。使用者已定案：**每一句音訊——對白、旁白、畫外音、內心獨白、謎之聲——都由 H3 原生生成，不使用任何外部 TTS。**

編譯器只有一個政策 `h3-native`（`--narration-policy` 也只接受這個值）。沒有可見嘴的台詞（畫外 O.S.、旁白／內心 V.O.、旁白者、謎之聲、背影／遮嘴）全部留給 H3，用官方畫外句式＋逐字 `<d>`。舊專案若還寫 `voice_route: "external"`，或呼叫 `--narration-policy external`／`short-offscreen-h3`，編譯器會直接報錯：

> 外部 TTS 已移除：請把 voice_route 改成 h3（或刪除該欄位），旁白一律由 H3 原生生成

**旁白聲線必須刻意設計**（不能讓 H3 自由發揮，否則每段換人、還可能配到畫面角色的嘴上）：

1. **綁定說話人自己的 `<Subject N>` (Sx)，但沒有 `<Picture>`**。旁白者、voice-only、謎之聲接在已選 Subject 之後編號；`subject_definitions` 會明寫「voice-only、沒有參考圖、永不入鏡」。
2. **固定英文聲線描述**：優先用該句的 `offscreen_voice_en`（來自階段 5 `en_overlay.shots.<gsid>.h3_voice.voice`）或 `voice_4d_spec_en`／`voice_profile_en`。跨段要一致，就每一段都用同一句描述。若都沒填，編譯器套用預設旁白描述：
   `a disembodied voice with no source in the frame, clearly a different person from anyone on screen: older and much deeper than any visible character, low and unhurried, slower than normal speech with clear pauses between phrases, close-miked with a faint airy reverb, it fills the air rather than coming from anyone`

   自己寫聲線時，要寫**具體的年齡、性別與音高，並跟畫面人物對比**（如 `clearly NOT the young man's voice: an old man's very deep, rough bass voice`），不要只寫 `genderless`、`disembodied` 這類抽象詞。為什麼：噩盡島 EP01 S02-b、S02-d 畫面只有洛年一人，抽象描述 2/2 被唱成洛年的年輕男聲（嘴是閉的，聽起來像他的內心獨白）；改成具體對比後 2 個 seed 中各 1 個成功。所以**旁白段至少跑 2 個 seed，逐支聽音色再選**。
3. **明說畫面中沒人說話**：每一句旁白後面固定加
   `No one in frame speaks during this line; every visible mouth stays closed and still.`
   這是防止 H3 把旁白配到在場角色嘴上的關鍵句。

**H3 句式（實測有效，噩盡島 EP01 S02-b「氣已極淡……等久了？」、S02-d「如你所願。」、S03-e「人生用這種方式結束，也算得上別緻。」拼音相似度 1.00）**：

- **O.S.（在場但未入鏡、不具形的聲音）**：
  `; the line is heard from <Subject N> (Sn) off-screen[, <位置>], <聲線描述>: <d>[Chinese] 逐字台詞</d> while <Subject k>'s lips remain completely closed. No one in frame speaks during this line; every visible mouth stays closed and still.`
- **V.O.（旁白、內心獨白）**：
  `; <Subject N> (Sn) says in an off-screen voiceover, <聲線描述>: <d>[Chinese] …</d> while no face is on screen, so all lips remain completely closed. No one in frame speaks during this line; every visible mouth stays closed and still.`
- **細節**：
  - 聲線描述放 `<d>` **外面**；`<d>` 裡只放逐字台詞。
  - 只對**露臉者**寫嘴閉合；沒有臉時 V.O. 寫 `no face is on screen`。
  - 同鏡 Expression 不可寫 mouth open／gasping／lips parted（#123）：H3 會讓露臉者跟著開口。改寫 `lips pressed tightly shut`。
  - 旁白長度以 **3.0 字／秒**估時；旁白窗（`speech_window`，沒有就用鏡長）短於 `字數 ÷ 3.0` 會出 compile warning。超過 18 字提醒「旁白過長：請拆到多鏡」（只是 warning，不是錯誤）。
  - 同鏡接話用 `dialogue_and_audio.extra_lines[]`（每句 `speaker`、`line_verbatim`、`speech_window`、`voice_4d_spec_en`），編譯器逐句給 `<d>`；畫外接話照同一套旁白句式。

**舊版 `external_narration` 已不再輸出**；`audit_refs_and_segments.py` 的 E24 會把任何殘留的 `external_narration` 或 `voice_route=external` 當成錯誤（訊息：「外部 TTS 已移除」）。

**指令**：

```bash
python scripts/storyboard/compile_layer2_to_h3.py   --layer2 layer2/layer2-EP01-*.json   --project-root .   --episode EP01   --output-md prompts-ep01.md   --output-segments segments-ep01.json   --assets assets.md   --bible adapt/bible.json   --narration-policy h3-native   --check
```

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
  - Qwen 黑白鉛筆分鏡總覽圖：**「✅ 階段 4 視覺化構圖與佔位審核工具」**。
  - Qwen 轉繪全彩首幀（`--to-color-keyframe`）：**「⚠️ 選用實驗功能（需整部片全部統一用同一圖片模型生首幀並排驗證）」**。一般情況下，一律走主力定案獨立 Ref2VA。

### 6.1 送件前確定性自檢與顯存保護（`submit_h3_segments.py`）

FreeVideo 可用時，可透過 adapter 提交 MiniMax H3 工作。可用模型、服務與 GPU 資源會依設備和版本變動：

```bash
# 1. 乾跑驗證（安全檢查分鏡總覽圖門禁、18 條 audit 自檢、參考圖 SHA256 與顯存狀態）
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
| **E24** 外部 TTS 已移除 | 段落還有 `external_narration[]` 或 `voice_route=external` | 全部改成 `h3`／刪除欄位，重編提示詞 |
| **E43** 有說話動詞卻沒給台詞（strict 才擋） | 一鏡寫了 says／speaks／narrates／the line is heard，卻沒有 `<d>` → H3 自編亂語（#122） | 要 H3 念就用 §5.4 的 O.S.／V.O. 句式＋`<d>`；沒有台詞的鏡不要寫說話動詞，只留嘴閉合與環境音 |
| **E44** 畫外句同鏡張嘴（strict 才擋） | O.S.／V.O. 鏡的表情寫 mouth open／gasping／lips parted → 露臉者跟著開口（#123） | 改成 `lips pressed tightly shut` |
| **E56** 特效缺參考圖 | 段落用到特效資產（shot／asset_refs 的 `B-` id），但 FreeVideo 沒有 `reference_paths.effects`、REMIX 沒有 `kind=effect` 的包；`pack_waivers` 寫了也沒用 | 在 assets.md 建特效卡（`B-` id、`類型：特效`、`設定圖`、`光源`／`source_en`）後 `h3d bind`；特效沒有圖不得進階段 5 |
| **E58** 提示詞洩漏 JSON／dict | 提示詞含 `{`、`}` 或 `": "`，把 raw dict／JSON 送進 H3 | 把終態／連戲狀態改成英文散文：`Luonian is back against the stone, chin lifted; the red sky is spreading overhead.`；不得出現大括號或 `": "` |
| **E57** 鏡頭寫了特效但沒有綁特效資產 | 單鏡的動作／表演／走位／描述文字出現 glow／beam／aura／energy／火焰／紅芒／光幕…等特效詞，卻沒有 `effect_ids` 或任何 `B-`／effect id。陽光、日光、光線、lighting 這類燈光詞已排除；`light`／`lighting` 欄位不讀 | 建特效卡＋參考圖並在該鏡 `effect_ids` 列出；若只是陽光／環境光，在該鏡寫 `"effect_ids": []` 與 `"no_effect_reason": "<原因>"` |
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
3. **分屏線殘留**：抽樣影格 $1/3, 2/3$ 無暗黑格線分割。
4. **跨鏡色彩連貫性**：串聯 `color_qa.py`，相鄰鏡頭色盤 $dE_{76} \le 25.0$。

**階段 6 必做：`--continuity-pairs <out_dir>`**（人審連戲）

```bash
python scripts/storyboard/verify_video_shot.py --segments segments-ep01.json --videos-dir videos/   --continuity-pairs videos/continuity
```

- 抽每段最後一格＋下一段第一格（段縫），以及每段 ffmpeg 場景偵測（threshold 約 0.3）找到的每個段內硬切左右兩格；Pillow 併排、Pillow 加字（不用 ffmpeg drawtext，這台機器會 segfault）。
- 產出 `pairs-N.jpg`（每張最多 8 對）與 `continuity-checklist.md`；每對列 dE76 與固定六列：location layout／prop shape & state／character screen side & facing／costume／light direction & colour／effect state。
- **階段 6 核准前，審查者必須逐對回答這六列**；任一列 break → 重拍其中一段，不要用調色或剪接掩蓋。pair 的 dE76 只做提示，不是通過標準。

---

## 階段 7：字幕剪輯與成片交付

本階段的順序是：**先定聲音三層（§7.1）→ 配音先行、再回頭定鏡頭長度（§7.2）→ 盤點本機 TTS 能力（§7.3）→ 混音與響度照交付標準（§7.4）→ 用組裝器執行（§7.5）→ 核對交付清單（§7.6）**。

### 7.1 聲音策略：全部 H3 原生

H3-Omni-Transformer *"jointly predicts video and audio latents, which are then decoded into video and stereo audio"*【官方】；輸出是**單一 32 kHz 立體聲混音軌，沒有分軌**。使用者定案：**所有台詞、旁白、畫外音、內心獨白都由 H3 原生生成，不使用外部 TTS、不做外部配音軌。**

| 情況 | 怎麼做 | 為什麼 / 壞掉長怎樣 |
|---|---|---|
| **畫內有可見嘴的對白** | 留給 H3：寫 `<d>` 逐字台詞，掛 `<Audio N>` 音色參考＋`voice_4d_spec_en` | 嘴型跟著 `<d>` 走；音色參考只給方向、不鎖口型 |
| **畫外音／旁白／內心聲／背影說話** | 同樣由 H3 生成：用 §5.4 的旁白句式、固定聲線描述、自己的 `<Subject N>`（無 `<Picture>`），並固定寫「No one in frame speaks…」 | 沒有這句時 H3 會把旁白配到畫面角色的嘴上；聲線沒固定時每段換人 |
| **事後改稿** | 改一個字就要重生成該段影片 | H3 把聲音烤在同一條混音裡，沒有分軌可單獨換句 |

**跨段聲線一致怎麼做**：每一段都用**同一句英文聲線描述**（`voice_4d_spec_en` 或階段 5 `h3_voice.voice`），有母帶時再掛 **`<Audio N>` 音色參考**。不需要、也不再用外部 TTS 軌道。

- **`voice_4d_spec_en`（或 `voice_profile_en`）必須用英文寫**：H3 提示詞正文是英文，只給中文 `voice_4d_spec` 編譯器**不會**貼進提示詞，只在 `compile_notes` 回報提醒。
- **不要靠「H3 會記住」**：每段都重新生成；一致性來自每段都貼同一句描述＋同一條 `<Audio N>`（有就用）。
- **官方沒有推薦外部 TTS**；本專案也不再用。舊文件的「A／B／C 三層」與 TTS 引擎選擇已作廢。

### 7.2 旁白先行與時長對軸（H3 原生）

**順序：先寫定旁白聲線與句子 → 依 3.0 字／秒配旁白窗 → 才定鏡頭／分段長度 → 生成。**

- **旁白估時 3.0 字／秒**：`speech_window` 至少要有 `字數 ÷ 3.0` 秒；比這個短，編譯器出 warning，請拉長或拆鏡。
- **對白估時 4 字／秒＋起音**：沿用原本的對白預算。
- **>18 字旁白**：編譯器提醒「旁白過長：請拆到多鏡」，不阻擋；H3 仍會念，但長句容易吞字。
- **H3 硬上限 15 秒**【官方】：單段不能超過 15 秒；加上句尾留白後超過就拆段，不要壓語速硬塞。
- **落地欄位**：字幕與段層對白錨定都用 authored `speech_window`（段內秒），不是 shot 起始時間。

### 7.3 旁白聲線設計與音色參考

**旁白不是「找一條外部聲音念」**，而是要把聲線寫進提示詞，讓 H3 每次生成都往同一個方向靠：

- **固定描述詞**：每個角色（含旁白者、謎之聲）在 Layer 2 `dialogue_and_audio.voice_4d_spec_en` 或階段 5 `en_overlay.shots.<gsid>.h3_voice.voice` 寫同一句英文。只寫「這個聲音是誰」（年齡感、音色、口音、語速習慣），不寫本場狀態（哭過、喘、壓嗓子寫在該句表演）。
- **沒有描述時的預設旁白**：編譯器會用「無實體、慢、乾、貼麥、空氣感」的預設描述（見 §5.4），並在 `compile_notes` 提醒補定案。
- **`h3_voice` 覆寫**：`en_overlay.shots.<gsid>.h3_voice = {"form": "voiceover"|"offscreen", "voice": "<英文聲線>", "where": "<英文位置，選填>"}`，等於指定旁白句式＋聲線／位置。
- **音色母帶（可選）**：`extract_voice_master.py` 可從已生成的 H3 片段抽出某角色的乾淨台詞，產出 `.wav`＋`.provenance.json`，貼進階段 5 `audio_references`，編譯器就會產出 `<Audio N>` 音色參考。**有就掛，沒有也不會退回外部 TTS。**

```bash
# 列出可當母帶的段落（畫內有可見嘴、2–15 秒）
python scripts/storyboard/extract_voice_master.py --segments segments-ep01.json --list

# 抽母帶（切點取自 Layer 2 speech_window）
python scripts/storyboard/extract_voice_master.py   --segments segments-ep01.json --segment-id EP01-S01-c --character C-luonien   --videos-dir videos/ --output assets/voices/V-luonien-master-v1.wav
```

**`<Audio N>` 綁定**（有母帶時；畫內對白與旁白都適用）：

```text
<Audio 1> is the voice-timbre reference for <Subject 1> (S1), containing a single teenage boy's Mandarin line recorded dry with no music.
<Audio 1>: reference - <Subject 1> (S1) follows <Audio 1>'s voice timbre and measured delivery without copying the original signal; the words in <Audio 1> are not spoken in the target video.
```

- 音色參考是**參考，不是保證**；官方標註 *Experimental; does not lock the output soundtrack or lip sync*。
- 母帶原句不會被念出來；不要把母帶台詞再放進 `<d>`。
- 參考順序是「圖 → 影片 → 獨立音訊」；`<Audio N>` 各自從 1 編號。

### 7.4 混音與響度交付標準

**量測演算法**是 ITU-R BS.1770-5；交付目標另外有各自的規範。

| 標準 | 整合響度 | True peak | 適用 |
|---|---|---|---|
| **EBU R128 v5.0** | **−23 LUFS ±0.5 LU** | ≤ −1 dBTP | 戲劇交付預設；本專案 `--target-lufs -23 --true-peak -1.5` |
| **ATSC A/85:2026-07** | −24 LKFS ±2 dB | < −2 dBTP | 對白錨定（CALM Act），美國廣播路徑 |
| **Netflix** | −27 LKFS（dialog-gated） | — | 串流平台；對白閘門取樣，不是整體平均 |
| Spotify −14 LUFS | −14 LUFS | — | **音樂／串流值，不是戲劇交付值**；不要套在劇集成片上 |

**順序：先做整合響度正規化，再套 true-peak 上限。**

**兩層：段層以對白為錨，整片兩遍 loudnorm**（`assemble_episode.py` 預設，`dialogue_loudness.py`）：

1. **段層「以對白為錨」增益**：H3 每支 clip 各自生成原生音、電平隨機；整片單遍 loudnorm 修不了段間落差。組裝器在每段 PCM 上：
   - 只量**對白區段**（`speech_window`；缺了用鏡頭時間）的 integrated loudness；
   - 錨點＝有對白段人聲響度的**中位數**（`--dialogue-anchor <LUFS>` 可指定），每個有對白的段算一個**固定增益**對齊錨點（±12 dB，`--dialogue-max-gain`），整段一起搬、段內動態不動；
   - **無台詞段不拉到錨點**；只有比錨點響超過 6 LU 時才壓到上限；
   - TP 保護：增益後預估峰值超過門檻的段在 192 kHz 下過 `alimiter`；需要壓超過 9 dB 就把增益收小（報告標 `tp_capped`）。
   - `--no-dialogue-align` 關掉（仍量測、列報告）。
2. **整片兩遍 loudnorm**：第一遍量 PCM，第二遍帶 `measured_*`＋`linear=true`，接 192 kHz `alimiter`（目標 TP −0.5 dB）、`aresample=48000`、`atrim` 回原長，AAC **256k**、`-ar 48000`。`--no-loudnorm` 關掉整片這一層（不建議交付時用）。

**舊規則「不要逐段正規化」仍成立**：逐段各自 loudnorm 到同一目標會把段與段之間的動態對比壓平；段層對白錨定只讓「對白」在各段一樣大，無台詞段維持相對電平。

**組裝報告**（`delivery-*.md`「響度」段、manifest `loudness`）：錨點、整片 I／TP／LRA、逐段處理前後的對白／整段 LUFS 與 TP、增益與旗標、**段間對白電平落差**；成片落差 > 6 LU（`--loudness-spread-warn`）出 **W49** 警告。

**實作坑（都已處理）**：ffmpeg 原生 aac 在 192k 遇密集低頻會過衝 → 段與成片一律 256k；逐段重編 AAC 尾巴會多一個 frame → 增益套在 #168 的 PCM 串接路徑上，成片再 `atrim` 回原長；JuiceFS 上 `-movflags +faststart` 改寫 trailer 會 I/O error → 組裝器不加 faststart。

**音訊處理鏈（沒有 TTS 混音）**：每段解成 48 kHz 立體聲 PCM → 可選段層增益／限幅 → 鎖成影片長度 → 串接成單一 wav → 整片兩遍 loudnorm → 編回 AAC 256k。

### 7.5 字幕與成片拼接（`assemble_episode.py`）

```bash
# 1. 組裝：音訊一律 H3 原生，沒有 TTS 引擎／沒有 --audio-mode
python scripts/storyboard/assemble_episode.py   --segments segments-ep01.json   --videos-dir videos/   --output final/ep01_final.mp4   --target-lufs -23   --true-peak -1.5   --delivery-report final/delivery-ep01.md

# 2. 全鏈路閉環自檢
python scripts/storyboard/assemble_episode.py --self-test
```

- **字幕來源**：`shots[].dialogue_and_audio.line_verbatim`（或 `subtitle`／`narration`）＋ `extra_lines[]`；時間窗優先 `speech_window`，沒有才退回鏡頭時間。字幕會燒進畫面，聲音不動。
- **沒有 `--audio-mode`、`--tts-engine`、`--tts-config`、`--bg-volume`、`--narration`**：外部 TTS 已移除；舊旗標會直接被 argparse 拒絕。
- **Windows FFmpeg 冒號轉義**：自動把磁碟機冒號轉成 `C\:/...`。
- **雙人引子**：`dual_lead_in` 會在組裝時自動剪掉片頭，字幕時間窗一起前移。
- **響度**：段層對白錨定＋整片兩遍 `loudnorm`，細節見 §7.4。

### 7.6 交付檔案清單
1. **成品影片**（`final/ep01_final.mp4`）：配音、混音、字幕燒錄無縫拼接成片，並已套段層對白錨定＋整片兩遍 `loudnorm`。
2. **旁白與字幕稿**（`narration-ep01.md`）：可獨立交付；組裝器不會直接讀取外部 Markdown 旁白稿。
3. **剪輯時間線**（`timeline-ep01.csv`）：從編譯後 `segments-ep01.json` 執行 `layer2_to_table.py --timeline`，使用有效片長與量化後末鏡時間。Layer 2 直接匯出的表格只代表企劃名義秒數。
4. **品質審查報告**（`videos/qa-report.json`）：分段規格、色差與畫風審查報告。
5. **交付清單**：列出已生成檔案、規格核驗結果與各鏡狀態；**交付前用 `ffprobe` 複核輸出取樣率與響度**（見 §7.4 的兩遍 loudnorm）。
