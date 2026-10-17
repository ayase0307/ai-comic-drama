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
| 交付深度 | 只到分鏡／到設定圖／到分鏡圖／到影片 |

沒說就採預設並明告：單集 90 秒、3D 國漫、9:16、繁體中文、對白＋少量旁白、交付到分鏡圖。產出 `project.md`（欄位見 `scripts/init_project.py` 模板）。

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
3. 出設定圖（見階段 6.1），**通過 `consistency.md` §10 驗收門**才算完成。

固定描述片段要具體到可畫：「黑色短髮、左眉尾一道疤、藏青立領風衣、右手銀戒」。避免「很帥」「氣質高雅」這類不可視化的詞。

---

## 階段 3：分集劇本（改寫成漫劇劇本）

規範：`adapt/screenplay-format.md`、`visual-writing.md`、`dialogue-and-audio.md`、`filmability-and-cost.md`（對應 Phase 6–9）。重點：

- **劇本管戲，分鏡管拍**：劇本用中文場號制（`第XX集｜標題`、`M-N 場景名 時/內外`、`人物：`、`△` 動作行、`角色名（括注）：對白`），**正文不出現攝影機術語**與模型提示詞。
- **100% 視聽外化**：心理活動轉成動作、道具、空間位階、言行不一；內心獨白 ≤ 單集對白行的 15%。
- 每場寫清「進場極性 → 衝突行動 → 資訊變化 → 出場極性」。單場核心互動角色預設 ≤ 3 人；多人混戰、複雜物理給「原版／AI 簡化」雙案。
- 對白單句 > 28 字警告、> 35 字阻斷（字幕可讀性）；整集時長在目標 ±15%。
- 產出：`script-epNN.md`、`handoff-epNN.json`（符合 `adapt/templates/handoff.schema.json`）、`adaptation-diff.md`（改編差異對帳）。

**必跑驗證**（任一閘門觸發即退稿重寫，≥ 80 分且 0 閘門才過）：

```bash
python scripts/adapt/validate_structure.py --script script-ep01.md --handoff handoff-ep01.json
python scripts/adapt/estimate_duration.py --script script-ep01.md --genre xuanhuan_revenge --target-seconds 90
python scripts/adapt/check_continuity.py --bible bible.json --handoff handoff-ep01.json
python scripts/adapt/compare_adaptation.py --source source.json --script script-ep01.md --handoff handoff-ep01.json
```

---

## 階段 4：分鏡（導演分鏡體系）

規範全文：`references/storyboard/cinematic-director.md`（v2.0）。輸入是階段 3 的 `handoff-epNN.json` 與階段 2 的 `assets.md`，**劇本台詞一字不改**。做什麼：

1. 以 `python scripts/storyboard/handoff_to_skeleton.py handoff-ep01.json --out-dir layer2/` 產生 Layer 2 骨架（只填結構，鏡頭欄位是 TODO，由導演精修）。
2. **分鏡三步法**（`storyboard/director-three-step-method.md`）：找重點做減法、找節奏（屏息延遲）、找關係（懸疑 Dirty Frame／武戲 90° 無遮擋／對白過肩藏拙）。依節奏檔位分配鏡數，不做等長碎剪。
3. **焦距＋物距成對寫**（`lens-optics-physics.md`）：不得只寫毫米數。
4. **連戲**（`anime-drama-grid-and-continuity.md`）：同場連續或時空跳躍二選一握手；不可逆狀態寫進 `persistent_world_state`；影片實測尾幀覆蓋規劃尾幀。
5. 武戲與模型編譯：`combat-physics-and-model-adapters.md`。
6. 三層產物：Layer 1 導演表（人看）、Layer 2 JSON（SSoT，有 `asset_refs`、`style_lock`、`character_ids`）、Layer 3 目標模型原生提示詞（階段 5）。

```bash
python scripts/storyboard/validate_storyboard.py --file layer2/layer2-EP01-*.json --handoff handoff-ep01.json   # 或 --demo 看範例
python scripts/storyboard/layer2_to_table.py layer2/layer2-EP01-*.json --check --md storyboard-ep01.md --timeline timeline-ep01.csv
```

**骨架不是成品**：`handoff_to_skeleton.py` 依「字數 ÷ 語速」估秒、單段 ≤ 8 鏡 ≤ 60 秒自動分段，鏡頭欄位與光色句、風格鎖留 `TODO`；驗證器與 `--check` 遇到 `TODO` 一律判失敗，導演精修完才過。

**長對白怎麼處理**（改編技能允許單句到 35 字，分鏡以語速為準）：單句字數 ÷ 語速超過該鏡可用秒數時，(1) 先拆成兩鏡（反應鏡夾在中間）、(2) 仍超過則在氣口（標點或關鍵詞前停頓）切斷，後半順延到下一段首鏡用 J-Cut 接續（`overflow_dialogue_out`／`_in`）。**不得刪字、不得倍速。** 分鏡端的骨架與驗證器共用 `scripts/storyboard/speech_utils.py`（去標點與空白後計字；建議常速 ≤ 3.8 字/秒，驗證閘門放寬到 4.2）；改編端 `estimate_duration.py` 另有自己的計字法（含標點），兩邊數字不會完全相同，以分鏡端為準。骨架分段檔名為 `layer2-EP01-S01-a.json`、`-b`…，一場台詞切到下一段時兩段檔案都要帶上。

**鏡長依模型**：H3 單段 4–15 秒（可把相鄰短鏡合成一段生成再剪開）；一般影片模型 4–8 秒，超過就拆鏡；FreeVideo 單段可到 60 秒，但單鏡動作仍 ≤ 5 階段。

**檢查點**：驗證通過（含 `--handoff` 的台詞核對）、使用者確認分鏡表，才進階段 5。沒定稿不出圖。

---

## 階段 5：提示詞包（Layer 3 編譯）

把 Layer 2 逐鏡編譯成目標模型的原生語法，寫進 `prompts-epNN.md`。

```markdown
### EP01-S01-003 ｜MS ｜35mm / 2m ｜4s
- **圖像提示詞**：<角色／場景（依 consistency.md §0 規則）>, <本鏡畫面>, <景別>, <光線>, <風格鎖定錨>
- **影片提示詞**：<運鏡>, <主體動作與時序>, <環境動態>, <物理連續感>
- **負面提示詞**：<負面錨 + 本鏡要避免的>
```

- 圖像提示詞結尾一律貼 `assets.md` 的風格鎖定錨；負面詞帶負面錨。
- 剔除審計標籤、解剖詞、毫米級偽精確數值（`combat-physics-and-model-adapters.md`）。
- 用 H3：走 `references/minimax-h3.md` 的官方三段式與守富骨架，不套通用公式。方法見 `prompt-playbook.md`。

---

## 階段 6：生成

### 6.0 先問使用者要怎麼生成（圖像、影片各一次）

**這一步不可跳過。** 提示詞依模型而異，先確認再改寫。

| # | 問什麼 |
|---|---|
| 1 | 圖像用哪個模型／工具？影片用哪個？ |
| 2 | 關鍵參數：比例、單段時長、解析度、是否帶音訊 |
| 3 | 提示詞用中文還是英文？ |
| 4 | 先做前幾鏡試水，還是整集跑？ |

拿到答案後：把 Layer 2 分鏡編譯出的模型無關主提示詞，**依目標模型改寫**（語法、語言、長度）。對照表與改寫流程見 `references/model-profiles.md`。

### 6.1 資產設定圖（先於分鏡圖）

依 `references/consistency.md` §3–§6 出：角色設定板（面部特寫＋正／側／背、6 表情、五色色票、身高對照、每套服裝一張）、場景主圖（母片＋三角度＋日夜變體）、道具（比例參照＋狀態表）、音色母帶。提示詞＝固定描述片段＋**風格鎖定錨**。每項過 §10 驗收門，**角色長相與音色交使用者確認後才繼續**。需要同圖鎖臉時可用九宮格出關鍵幀，但分鏡圖仍逐鏡生成。

### 6.2 分鏡圖

逐鏡生成。參考鏈：角色板＋場景主圖（＋道具）→ 分鏡圖（`consistency.md` §7）；有參考圖時外觀只在首次出現寫一次。每鏡生成後跑 §8 漂移清單，fail 不得當下一鏡參考。結果寫回 Layer 2 的 `status`、`image_file`、`reference_refs`。

### 6.3 影片片段

優先**圖生視頻**：以分鏡圖為首幀，提示詞只寫運動。

- 需要「同一個鏡頭內的轉折」時，可同時給首幀與末幀圖。
- 單段建議 4–8 秒；超過就拆鏡。
- 生成需 1–3 分鐘，逐段做、逐段驗。

### 範圍對齊

生成前跟使用者對齊數量：「本集 24 鏡，要不要先做前 6 鏡試水？」

---

## 階段 7：組裝與交付

1. **旁白稿**（`narration-ep01.md`）：逐鏡的旁白／字幕文字，標明時間碼。
2. **時間線**（`timeline-ep01.csv`）：由 `layer2_to_table.py --timeline` 產生，欄位 `shot_id, start, end, duration, video_file, subtitle, narration, speaker, foley`。
3. **拼接**：可用 ffmpeg 合併影片片段、燒字幕、混 BGM 與配音。
4. **交付清單**：列出已生成檔案、未完成鏡號。

```bash
# 範例：合併片段並燒入字幕
ffmpeg -f concat -safe 0 -i list.txt -c copy merged.mp4
ffmpeg -i merged.mp4 -vf "subtitles=sub.srt" -c:a copy final.mp4
```
