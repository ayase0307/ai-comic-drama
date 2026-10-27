# 產線工具（h3d）與四道確定性檢查

> 這一頁給「要跑這個 skill 的人／agent」看：有哪些指令、每個檢查在擋什麼、看到錯誤訊息怎麼處理。
> 規則的來源與理由寫在 `pipeline.md`／`consistency.md`／`minimax-h3.md`；這裡只講操作。

## 1. 一個入口

```bash
python scripts/h3d.py next --root .   # 開工第一步：目前階段、卡在哪、下一步唯一一條指令
python scripts/h3d.py --list          # 所有子命令
python scripts/h3d.py status --root . # 全局狀態（階段／依賴／送件／失敗目錄）
```

| 子命令 | 做什麼 | 何時用 |
|---|---|---|
| `next` | 讀 project-state（hash／依賴）、decisions、verdicts、QA、ledger，印**下一步唯一一條指令**＋該讀的 reference（`--json` 可機讀） | **每次開工、每做完一步** |
| `decide` | 把使用者定案寫進 `decisions.json`（必附 `--quote` 原話；`--list` 列出） | 使用者拍板任何畫風／比例／台詞／驗收／剪輯規則時 |
| `verdict` | 階段 6 逐段目視結論寫進 `review/verdicts.json`；`--summary` 依驗收政策分類；`verdict import` 轉舊格式 conclusions-*.json | 收件抽幀看完每一段後 |
| `inbox` | 決策收件匣 `review/inbox.html`：只列**需要使用者決定的事**（卡片＋選項複製回覆），已決定／自動處理收合 | 每次要使用者拍板之前；取代逐階段審核頁 |
| `approve --auto` | 沒有未決卡、且符合 `decisions.json` 政策（`auto_approve`）時自動核准並記錄依據 | `h3d next` 指示時 |
| `run` | 階段 6 送件 runner（`--plan`）：單例鎖、佇列檢查、`--pause`／續跑、`--status` 進度檔 | 送整批分段時（取代專案自寫 runner） |
| `probe` | 送件前查 API schema 與已安裝 LoRA，缺的直接擋並列替代 | 每次送件前（`run` 也會自動做） |
| `voice` | `voice align`：ASR 對位、畫外句區間壓原聲（−22 dB）、響度標準化（−16 LUFS） | 階段 7 配音完成後 |
| `concat` | `concat plan`／`concat build`：全集單一 Concat 剪輯專案（T1 影片、T2 字幕、T3 畫外音） | 剪輯方式定案為 Concat 時 |
| `doctor` | GPU 顯存、ffmpeg（含 `-vsync` 回歸）、服務 port、磁碟 | 開工前、換機器後 |
| `compile` | Layer 2 → H3 六段式提示詞＋`segments-*.json`（remix 綁定＝REMIX 三欄，§2.3.1c）；`--check` 同時跑 17 條自檢與失敗目錄 | 每次改完分鏡 |
| `audit` | 參考圖／主體定義／台詞預算對帳 | 編譯後單獨重驗 |
| `refcheck` | 參考包涵蓋檢查：提示詞寫到的具名角色／生物／道具／場景／群眾是否都有綁包（remix E50／E51 擋；ref2va 只提示），`--takes` 查已送出抽次的快照（§2.3.1d） | remix 每次改提示詞、送件前 |
| `staging` | 站位／視線／運鏡閘門 D06–D14（兩個 backend；預設全部警告，`staging_gate=strict` 時 D06–D08 擋，§2.3.1d） | 階段 5 寫完提示詞後 |
| `submit` | 送 FreeVideo：能力表＋時長斷言＋ledger 去重（`--output-dir` 預設 `<--root-dir>/videos`；`h3d submit --root X` 會轉成 `--root-dir X`） | 使用者要求生成時 |
| `collect` | 只把「已完成但沒下載」的工作收回來；影片已在但帳本仍記進行中的段，只查一次服務端並更新帳本 | 批次中斷後 |
| `resume` | collect 後補送未產出的段；collect 有失敗／漂移就停，處置後用 `--resume-past-failures` 續送其餘缺片段（漂移段要 `submit --segment-id` 明確重送） | 中斷後續跑 |
| `qa` | 影片驗收＋**證據分級** | 拿到影片後 |
| `assemble` | 配音、字幕、響度（整片 loudnorm，預設 EBU R128 −23 LUFS／TP −1.5）、拼接；`--output` 預設 `<videos-dir>/final-<集數>.mp4` | 交付前 |
| `deps` | segment 級依賴帳本（`--record`／`--status`） | 改動後查「哪幾段要重跑」 |
| `catalog` | 失敗目錄（`--list`／`--check`／`--acks`／`--prune-acks`） | 想知道「這句為什麼會被擋」 |
| `ack` | 記錄「我接受這條警告」的憑證 | 確認是誤報、但不想改稿時 |

每個子命令都保留原本的 `--help`，`h3d` 只是路由，沒有第二套邏輯。

## 2. 四道檢查在擋什麼

### (a) 時長量子（17n+5）

FreeVideo 會把秒數向上取到最近的 `17n+5` 影格。**送 `frames/24` 的精確值**，不要送四捨五入後的秒數
（`11.542` 會被推到 294 幀＝12.25s）。編譯器寫 `metadata.frames`，送件端回讀服務端 `frames` 與
下載後的 ffprobe 長度；不符就取消並隔離成 `.drift.mp4`。

看到 `duration_drift`：代表服務端或檔案長度與要求不符，**不要拿去 QA**，先查是不是手改過 segments。

### (b) 證據分級（qa）

`measured`（本機量過）／`sourced`（文件或競品）／`inferred`（推論）。報告結論只有三種：

- `VERIFIED`：所有分段都產出且量測通過
- `PARTIAL`：有缺段、失敗、跨鏡連續性警告，或含 `inferred` 檢查
- `UNVERIFIED`：一段都沒量到

**階段 6 閘門要求 `VERIFIED`**；舊報告（沒有 `evidence` 欄位）會被要求重跑。標題出現
`TECHNICAL CHECK PARTIAL · NOT READY TO SHOOT` 就是「不要開拍」。

### (c) 依賴帳本（deps）

每段記 `layer2`／`prompt`（含 `built_from_layer2_sha256`）／`video`（含 mtime）。

```bash
python scripts/h3d.py deps --root . --record
python scripts/h3d.py deps --root . --status --strict
```

- `prompt_stale`：分鏡改了但提示詞沒重編
- `video_older_than_prompt`：影片比提示詞舊（改了稿沒重跑）
- `video_missing`：記過影片、現在不見了
- `prompt_stale`＋`stage5_pending_review`：階段 5 段級核准後被改、已有影片的段（不需先 `--record`，見 §2.6 段級核准）

只報「哪幾段要重跑」，**不會自動重簽核准**。

### (d) 失敗目錄（catalog）

每條失敗有症狀／根因／最小修法／證據／信心等級，以及純 regex 的 detector。`enforce=error`
直接擋送件，其餘只警告——但**警告也要處置**：

1. 改稿（首選）
2. 或 `h3d ack <ID> --root .` 明確接受 → 寫入 `review/catalog-acks.json`
   （綁定命中段的 prompt hash 與目錄版本；改稿或改規則就失效）
3. ack 檔已納入 **stage-5 核准快照** → 記得重新核准 stage-5

`--prune-acks` 清掉 covers 對不到現行稿件的 ack。

> ack 的定位是「人看過並接受」，不是「讓 gate 閉嘴」。沒有 ack 就送不出去，這是刻意的。

### (e) 階段 6 的「影片 × 分鏡總覽圖 × 設定圖 × QA」頁

`review/stage-6-videos.html` 每張卡左邊是影片，右邊由上而下是階段 4 構圖（`grid-*` 或逐鏡 `panel-*`）、階段 2 角色設定圖（`adapt/bible.json` 或 `assets/reference-manifest.json` 對映）、以及 `qa-report.json` 的量化欄位。缺圖只顯示紅框，**不阻擋核准**。

### (f) 切點標記（選用，非官方語法）

`h3d compile ... --embed-cut-markers` 會在提示詞寫入：

- `<cutoff>`：段落末鏡（表示這是最後一個可截斷點）
- `<scenetrans>`：跨場景的首鏡

同時在 `metadata.cut_marker_tokens` 記下是否嵌入與規格。**預設關閉**，因為這是本專案約定
（官方對這兩個 token 的語義我沒有可核對的來源）；要交給剪輯／拼接工具時再開。
結構化的切點時間一直都在 `metadata.cut_markers`，不需要開這個旗標也能用。

### (g) 逐鏡撰寫審查（author，防偷懶）

`python scripts/h3d.py author --root <專案>`（或 `compile --check`、階段 5 審核頁、`submit` 自動跑）。只看**最終送件文字**，所以編譯後才套上的模板也逃不掉：

- E30／E31／E32：每鏡五小節要齊，Motion、Performance 不得過薄，Motion 要寫動作過程。
- E33／E34／E35：套句、後設詞（authored／approved…）、防禦性禁止句堆疊。
- E36／E37：違背分鏡運鏡、嘴部可見的對白被寫成畫外音。
- E38：`detailed_description`（REMIX 三欄：`integrated_multimodal_description`）與 `metadata.compiled_prompt_sha256` 不符＝編譯後被改寫。
- W41–W45（只警告，D40–D46，來源 Foyege、H3 0 實測）：W41 台詞鏡視線沒寫螢幕方向（和 `h3d staging` D07 共用 `staging_lint.find_gaze`：沒有視線句只由 D07 報）、W42 `subject_definitions` 寫位置或姿態、W43 寫實畫風全身／遠景寫毛孔（定版皮膚段豁免）、W44 Performance 只有情緒詞或 AU 代碼、W45 中段鏡重列全場世界站位（`left to right` 名單不算）。
- 處置：回 Layer 2 的 `five_part_en` 逐鏡改稿再編譯。不准改檢查器門檻、不准手改 segments 過關。規範見 `references/prompt-authoring.md`。

### (h) 鏡頭意圖（shot_intent／choice_why，I01–I06）

Layer 2 每鏡新增必填欄位 `shot_intent`（audience、story_beat、pov、emotional_shift）與 `choice_why`（shot_size、lens_distance、movement、blocking、background；有對白加 line_timing），schema 見 `references/storyboard/templates/layer2-storyboard.schema.json`。`handoff_to_skeleton.py` 會放 TODO 佔位；`validate_storyboard.py` 擋：I01 缺意圖、I02 缺理由、I03 佔位／過短、I04 同段意圖重複、I05 理由抄技術值或同段三鏡同一句、I06 跨段同一句 ≥5 鏡。邏輯在 `scripts/storyboard/shot_intent.py`。提示詞端另有 E40（抹背景）、W40（無線索氣氛詞）。

**骨架與構圖的 ID／比例**：
- `handoff_to_skeleton.py handoff-epXX.json --out-dir layer2 [--bible adapt/bible.json]`：用聖經的 `canonical_name`／`name`／`aliases`（及 ID 本身）把 handoff 的中文名對到聖經 ID（`C-`／`S-`／`P-`）；沒給 `--bible` 時自動找 `<handoff 所在目錄>/adapt/bible.json`，`--bible none` 關閉。查不到的名稱退回雜湊 ID 並逐一警告——不補 `aliases` 的話 `h3d bind` 會判成「未在 bible.json 登記」。
- `h3d sketch`（`svg_storyboard_grid.py`）畫布依每段 Layer 2 `metadata.aspect_ratio` 設定（長邊固定 768；16:9 仍是 768×432，9:16＝432×768），`--aspect 9:16` 可整批覆寫；看不懂的比例警告後退回 16:9。構圖必須和成片同比例，否則審核者會誤判景別與走位。

## 2.3 階段 5 英文層（stage5 binding 的 en_overlay）

階段 4 的 Layer 2 常用中文寫運鏡、走位、錨點物件、連戲錨與收尾狀態；Layer 2 綁著階段 4 核准 hash，不能為了英文去改。
英文版寫在 `--bindings` 檔每段的 `en_overlay`（舊名 `x_en_overlay` 也認），編譯器在記憶體裡寫進 `*_en` 欄位：

```json
"en_overlay": {
  "shots": {"EP01-S01-a-SH01": {"movement_en": "dolly in", "blocking_en": "...", "anchor_objects_en": ["..."], "lips": "closed|omit"}},
  "continuity_anchors_en": {"lighting": "...", "axis": "...", "blocking": "...", "texture": "..."},
  "lighting_lock_line_en": "...",
  "end_state_en": {"<who/what>": "<state>"},
  "voice_4d_spec_en": {"<speaker id>": "..."},
  "secondary_desc_en": {"<character id>": "這一段專用的英文描述（例如成形前只是一片紅光）"}
}
```

- `shot_overrides` 也接受 `movement_en`／`blocking_en`／`anchor_objects_en`／`lips`。Layer 2 本身寫了 `camera_optics.movement_en`、`spatial_blocking.blocking_desc_en`／`anchor_objects_en`、`style_lock.continuity_anchors_en`、`segment_end_state.planned_final_state_en` 也優先採用。
- 沒有 `global_shot_id` 的 Layer 2：編譯時以 `shot_id` 補（只在記憶體，不改檔、不影響階段 4 核准）。
- 中文運鏡會依關鍵字對到官方動詞（推近→dollies in、跟拍→tracks、手持→handheld…）；對不到就報錯並指向 `movement_en`。
- 仍是中文、沒有英文版的走位／錨點／連戲錨／收尾狀態**不會**寫進提示詞，改記一條 compile note；audit E15 對所有英文提示詞檢查（`<d>` 台詞除外）。
- 閉唇句只加在「看得到臉且不說話」的鏡：`lips`（en_overlay）→ `lips_closed_lock`（明寫 true／false）→ 鏡內有沒有可見角色。
- `no_visual_reference`／`voice_only` 的角色只寫「只聞其聲、畫面上不出現」，不寫外觀；`secondary_desc_en` 可為某段改寫次要角色描述。

### 2.3.1 缺圖、無圖道具、生物階段變體（#54 #55 #60）

- **沒有設定圖的道具**：`reference_paths.props` 的條目可以不寫 `reference_image`（或 `asset_refs.props` 登記了但 bible 沒圖）。只要 bible 有 `visual_prompt_en`，編譯器會把它以純文字寫進參考定義區、不占 `<Picture N>`，並記一條 compile note；沒有英文描述才報錯。補圖後重編即改走 Picture 參考。
- **缺場景母版先審稿**：binding 段落寫 `"pending_references": ["refs/scenes/xxx.png"]`（字串或清單；舊名 `pending_scene_plate`、`x_pending_scene_plate` 也認）。宣告過的路徑不會因檔案不存在而編譯失敗，`compile_notes` 與 `metadata.pending_references` 會留記錄。**這只放行審稿**：`submit` 看到 `pending_references` 或檔案不存在一律擋下，階段 5 驗證仍判缺圖，圖補齊重編後記錄自動消失。
- **同一生物同段有階段變體＋基本型**：基本型（沒寫 `variant` 的條目）當 Subject 的圖，所有 `variant` 條目都是逐鏡範圍的補充 Picture（`Stage-specific reference…this shot only`）。只有變體沒有基本型時，第一個變體當 Subject 的圖（舊行為）。
- 生物的 retention 寫「body shape, skin or surface texture, and head features」，不再沿用人類模板的臉／髮型／服裝。

### 2.3.1b 參考圖綁定產生器（`h3d bind`）

沒有 `video-bindings.json` 時，編譯器直接拿角色聖經的設定圖（通常是四視圖整板）、每段只掛一張角色圖，其餘在場角色沒有身分錨 → audit **E20（整板）與 E19（未錨定在場人物）必擋**（`tests/test_bindings_generator.py` 的對照組實測）。所以階段 5 先跑：

```
python scripts/h3d.py bind --root .
```

- 讀 `adapt/bible.json`＋`assets.md`（與編譯器同一個 AssetRegistry）與 `layer2/layer2-*.json`，在專案根目錄寫 `video-bible.json`、`video-bindings.json`。不改階段 1／2 檔案。
- **選圖規則（每段每角色一張圖）**：逐鏡判讀 `assets/face-visibility.json`（`{"shots": {"<global_shot_id 或 segment_id/shot_id>": {"C-x": "face|profile|back"}}}`）聚合到段，任一鏡看得到正臉 → `face`，否則 `back`，否則 `profile`；沒有判讀預設 `face`。
  - `face` → 單視角正面裁切（計畫表 `face_crop`；原圖本身不是整板時直接用原圖）。
  - `back`／`profile` → 整板查表 `reference_view: "panel"`＋`panel_role`＋`panel_label_en`（預設格位依技能標準四視圖板：側面＝三個全身像的中間、背面＝最右）；原圖不是整板時當單視角錨點。
  - 生物 → 整板時一律 `panel_role: "creature"`；群眾（`is_group`／`EXTRAS-`）→ 直接掛群眾參考圖。
- 計畫表 `assets/character-reference-plans.json`（選填）：`{"face_crop_box": "x0,y0,x1,y1", "characters": {"C-x": {"default": {"face_crop": "...", "face_crop_box": "...", "sheet": "...", "panel_labels_en": {"back": "...", "profile": "..."}}, "costumes": {"W-x": {...}}}}, "creatures": {"CREATURE-x": {"sheet": "...", "panel_label_en": "..."}}}`。
- 逐鏡判讀的鍵依序查 `segment_id/global_shot_id`、`segment_id/shot_id`、`global_shot_id`、`shot_id`（`EP01-S01-a/SH01` 這種寫法也認得）。
- **缺圖不猜**：任何缺口（看得到正臉卻沒有裁切、未登記角色、設定圖不存在）全部列出並附裁切指令（絕對路徑 `python "<skill>/scripts/h3d.py" crop --root . --image "<設定圖>" --box … --out-dir assets/crops --prefix C-x-face`），**不寫任何檔案**。裁切放 `assets/crops/`，不放 `images/`（會讓階段 2 快照失效）。
  - **`--box` 預設 `0,0,0.3711,0.6319`**＝標準四視圖板（2560×1440）左側頭部特寫格像素 `0,0,950,910` 換算的比例，同版面任何尺寸都適用（舊預設 `0,0,0.25,1` 會裁到半身＋邊欄，已棄用）。版面不同時寫 `face_crop_box`：計畫表頂層＝全專案、`characters.<id>.default`／`costumes.<W>`＝單一角色（角色層優先）；值可寫字串或四元素陣列。
  - `h3d crop` 三選一：`--grid`、`--box`（比例）、`--px x0,y0,x1,y1`（像素，超出圖片範圍直接報錯）。相對的 `--image`／`--out-dir` 以 `--root` 解析，不看目前工作目錄；輸出落在 `images/` 底下會被拒。裁完務必目視確認只剩一張臉。
- 重產時保留既有 bindings 的手寫欄位（`en_overlay`、`shot_overrides`、`audio_references`、`crop_note_en`…），只覆蓋產生器擁有的欄位（來源 hash、場景圖、逐鏡 `reference_paths`／`visual_subject_ids`／`face_subject_ids`／`identity_anchor_ids`）。從 remix 切回 ref2va 重綁時會拿掉 remix 專屬欄位（頂層 `video_backend`／`packs`、段層 `refmods`／`pack_waivers`、逐鏡 `pack_ids`；`positions` 保留），否則編譯器會把它當 remix 綁定拒編。
- **輸入指紋 `inputs_sha256`**：bindings 頂層記錄 `adapt/bible.json`、`assets.md`、計畫表、`face-visibility.json`（remix：bible、assets.md、`character-packs.json`）的 sha256（不存在記 null）。任一輸入在綁定後新增／修改／刪除，`h3d next` 視同綁定落後、先帶 `h3d bind`。舊版綁定沒有這個欄位就不追溯。
- `h3d next` 在階段 5 發現沒有 bindings、或任一 layer2 在綁定後被改（`source_sha256` 不符）時，會先帶出 `h3d bind`，之後才給 compile 指令。
- 尚未處理：道具、身體細節與音色母帶 `audio_references` 不自動綁，需要時手寫進 bindings（重產會保留）。

### 2.3.1c REMIX 角色包 backend（`video_backend: remix`，PR-R1～R3、R5）

> **量測範圍**：以下 measured 全部只在 **8 GB RTX 4060 Ti、H3 Singularity ref2va Pruned V1.3 int8＋4step turbo**（家機 REMIX Studio，《噩盡島》ch02 EP04）上量過；其他顯存、其他底模（含早期 v0.8）都沒量。證據等級：**measured**＝本專案實跑、**docs**＝家機指南或 `GET /capabilities`、**inferred**＝從量測推出。

**不刪、不改 Ref2VA。** 新增定案 `video_backend`（`ref2va`＝預設、現行門禁全部照舊；`remix`＝家機 REMIX Studio＋RefMod 角色包）：

```
python scripts/h3d.py decide video_backend remix --quote "<使用者原話>" --root .
python scripts/h3d.py decide remix_pack_cap 4 --quote "<原話>" --root .        # 選填：每段包數上限，只能加嚴（1–8）
python scripts/h3d.py decide style_anchor "<英文錨句>" --quote "<原話>" --root .  # remix 必要（E55）
```

**能力表 `scripts/storyboard/providers/remix.json`**（`provider_caps.py` 讀；與 `h3_spec.PROVIDER_FRAME_SPECS` 對帳）：

| 欄位 | 值 | 等級 |
|---|---|---|
| fps | 24（175 幀＝7.29 s） | measured |
| 秒數 → 幀 | 17n+5 **往下取**（5.5 s → 124 幀）；FreeVideo 是往上取 | measured |
| seconds／frames | 2–10.125 s；56–243 幀（56＝≥2 s 的最小量子，推定） | docs |
| aspects | 1:1、2:3、3:2、3:4、4:3、9:16、16:9、21:9（只量過 16:9） | docs |
| max_refmods | 8（`refmods_max`） | docs |
| 每段包數（含場景，8GB） | ok 4（measured）／slow 5（measured：draft 726–1924 s、1 抽 57 分逾時）／fail 6（**inferred**：只有 1 抽 draft 63 分逾時沒產出；逾時是 measured、OOM 是推定，fast／single480 沒試） | 分級各自標 |
| modes | draft／refine／detail／fast／standard／high／ultra／single480／single720；本專案只跑過 draft、fast、standard、single480、single720 | docs |
| steps | 2–10（預設 4），只限 single480／single720 | docs |
| continue_from | single 模式不支援 | docs |
| requires_project | 必帶 `project`（不帶回 400 `project_required`） | measured |
| negative_field | 沒有 negative 欄位 → 風格只能靠提示詞開頭錨句（E55） | docs |
| first_frame | 沒有首幀輸入（v0.8 時期紀錄，V1.3 沒查） | docs |
| ref_dedup | 同一個 `ref` 直接回舊 job | measured |
| tag | 單圖包 `<Picture N>`、多圖包 `<Video N>`，各自從 1 編號；tag 看圖片張數不看 kind（2 張圖的道具包是 Video） | docs＋measured |

`--check`／送件前：measured 違反就擋，其餘只警告。**6 包**刻意只給強烈警告（fail 證據只有一抽 draft 逾時、OOM 推定），要擋就定 `remix_pack_cap`；專案上限只會多擋、不會放行任何預設會擋的東西。`h3_spec.server_frames(seconds, provider)` 依 provider 往上／往下取；編譯器送 `frames/24` 精確值，兩邊都落在同一個量子。

**綁定（`h3d bind`，remix 分支）**：讀 `assets/character-packs.json`（必填）：

```json
{"packs": {"S-alley": {"default": "ejin3_scene_alley", "tag": "Picture", "kind": "scene"},
           "C-lai": {"default": "ejin3_laiyixin", "tag": "Video", "kind": "actor",
                     "costumes": {"W02dirty": {"pack": "ejin3_lai_w02dirty"}}},
           "P-spear": "ejin3_prop_spear"},
 "waivers": {"EP04-S01-a": [{"id": "P-spear", "reason": "6 包逾時，改文字", "quote": "<使用者原話>"}]}}
```

- 產出 `video-bindings.json`：頂層 `video_backend: "remix"`＋`packs`；段層 `refmods`（順序＝標籤順序：**場景第一**、演員、最後生物／道具／群眾，每項帶 `pack`／`tag`／`kind`／`label`／`costume_id`／`variant_of`…）、`pack_waivers`（必附使用者原話）、`positions`（`[{id, order_lr, axis_side, facing}]`，手寫保留，給 R6 站位閘門）；逐鏡只有 `visual_subject_ids`／`no_visual_reference_ids`／`pack_ids`。
- **不產生** `face_subject_ids`／`identity_anchor_ids`／`reference_view`／`panel_label_en`；舊綁定或計畫表寫了只警告「remix 不使用」，重產時拿掉。
- 在場角色／生物／群眾、場景、`asset_refs.props` 沒有包也沒有豁免 → 列出缺口（換服裝＝換包，沒登記變體不退回預設包；**預設包本身穿的就是這套服裝**時在 `packs.<id>` 寫 `"default_costume": "W-x-01"`（或陣列 `default_costumes`），該服裝直接用預設包、不算缺口）、**不寫任何檔案**。`h3d pack build` 尚未提供（PR-R8），先在家機建包、回讀確認後寫進計畫表。沒寫 `tag` 時依 kind 推定並警告。
- `--backend ref2va|remix` 可覆蓋定案。

**編譯（PR-R5，REMIX 三欄輸出）**：`--bindings` 是 remix 綁定（頂層或段落 `video_backend: remix`、段落帶 `refmods`）時，`compile_layer2_to_h3.py` 改產 REMIX 三欄；ref2va 綁定照舊產六段式，單臉模式、`<Subject k>`↔`<Picture k+1>` 序對只在 ref2va 執行。

```
python scripts/h3d.py bind --root .                                   # remix 分支：讀 assets/character-packs.json 產 refmods
python scripts/h3d.py compile --layer2 "layer2/layer2-EP04-*.json" --episode EP04 --project-root . \
    --bible video-bible.json --bindings video-bindings.json \
    --output-md prompts-ep04.md --output-segments segments-ep04.json --check
```

- **輸出格式**（實戰來源：《噩盡島》ch02 EP04 家機送件 `ch02/build.py`，measured 只在那一集）：
  `integrated_multimodal_description:` ＝ **風格錨**（E55，段落 `metadata.style_anchor_en` > 定案 `style_anchor` > 14 號固定錨；都沒有就報錯，不自己補）→ 畫幅與光線鎖一句 → `[Shot 1]` 場景句＋**每個包一句介紹**（`<Picture 1> is the location, keep its layout, lighting and render style.`、`<Video N> is <英文名>, <外觀錨>.`）→ 鏡頭句＋五小節 → `[Shot 2] At 00:04.300, …` → **Style lock** 句（`metadata.style_lock_tail_en` 可換）→ 無字句（預設開；`--no-lettering-guard` 或 `metadata.allow_lettering=true` 關）；接著 `overall_soundscape:`、`non_diegetic_music:`（空的寫 `N/A`）。**不輸出** `subject_definitions`／`summary`／`retention_analysis`。
- **標籤**：`<Picture N>`／`<Video N>` 依 refmods 的 `tag` **各自**從 1 編號、順序＝refmods 順序、場景包第一（綁定的 `label` 和順序不符、場景包不在第一、同包掛兩次都直接報錯，同 E52／E53）。介紹句**只寫是誰與外觀，不寫位置或姿態**（站位、坐站寫在各鏡五小節；W42 會對介紹句裡的位置／姿態詞提醒）。鏡內一律用英文名：五小節的 `{C-id}` 換成英文名（ref2va 是換成 `<Subject N>`）。
- **英文名**（介紹句、refcheck、站位閘門都靠它對人）：refmods `name_en` > 計畫表 `packs.<id>.name_en` > bible `name_en` > 英文的 `display_name`／`name`；演員／生物／群演找不到英文名就報錯。**外觀錨**：refmods `description_en` > 計畫表 `description_en`（服裝變體寫在 `costumes.<W-id>.description_en`）> bible `visual_prompt_en`（含服裝）；建包時的描述和 bible 不同時，把包的描述寫進計畫表，兩邊要一致。`h3d bind` 產的 `video-bible.json` 會帶上 `name_en`／`aliases_en`。
- **台詞與畫外音**：與 ref2va 同一套（`<d>[Chinese] …</d>`、`(Sx)`、畫外 O.S.／V.O. 官方句式＋閉唇、長句外部化、E22–E25、E43／E44）；說話者代號依第一次發聲順序 `(S1)`、`(S2)`（沒有 `<Subject k>` 可對齊）。remix 多人同框的可見台詞，同鏡其他演員另加 `while A's and B's lips remain completely closed`（ch02 寫法）。
- **其他**：秒數→影格照 ref2va（台詞段往上取，`metadata.frames` 送 `frames/24` 精確值，家機往下取也落在同一量子），超出 REMIX 區間 56–243 幀記 compile note；`audio_references`、`en_overlay.show` 不輸出（REMIX 沒有音訊參考；可見度寫進五小節）；Combat_Impact 段不自動掛 LoRA（FreeVideo LoRA 目錄在 V1.3 未驗證）。
- **segments 欄位**：`metadata.video_backend: "remix"`、`metadata.style_anchor_en`、`refmods`（含 `label`）、`pack_waivers`、`positions`、逐鏡 `visual_subject_ids`／`no_visual_reference_ids`／`pack_ids`、`reference_images: []`；編譯指紋 `compiled_prompt_sha256` 照舊（REMIX 取 `integrated_multimodal_description`，E38）。
- **`--check`**：audit 走 remix 分支（E50–E55＋refcheck 文字比對＋站位 D06–D14）、`lint_h3_prompt(backend="remix")`（三欄沒有 summary，時長改以 authored 時間軸與切點時間戳對帳）、失敗目錄、段間連戲、逐鏡撰寫審查（E30–E40、W41–W45；E40／E41 改看 refmods 與介紹句英文名，帶原話的 `pack_waivers` 視為已處置）。
- **backend 一致**：綁定是 remix 就產三欄；`--backend ref2va` 配 remix 綁定、或定案 remix 卻沒有 remix 綁定 → 報錯，先用同一個 backend 重跑 `h3d bind`。定案和綁定不同時照綁定編、印提示。
- **送件**：`h3d submit`／`h3d run`（FreeVideo）看到 remix 段一律拒送；remix 送件 adapter 是 PR-R7，完成前在家機 REMIX Studio 手動送 `h3_prompt`＋`refmods`（依順序）。

**審查（`audit_refs_and_segments.py`，依 backend 分支）**：backend 判定順序＝`--backend` > 段落 `metadata.video_backend` > 段落帶 `refmods` > `--project-root` 的 decisions > ref2va。

| 門禁 | ref2va（不動） | remix |
|---|---|---|
| E19 未錨定在場人物 | 擋 | 改 **E50 具名角色沒有包**（段落在場名單＋R4 refcheck 的提示詞文字比對，見 §2.3.1d） |
| E20 多視圖板、E26 non_face 缺圖、E27 panel 缺格位 | 擋 | 跳過 |
| E21 無參考群眾 | 擋 | 保留，cue 另加 students／people／classmates／others（`as tall as the others` 這類比例錨不算）；有 `kind: extras` 包才放行 |
| 混臉／單段多張角色圖警告 | 警告 | 關閉，改 **E54 包數**（能力表分級；`remix_pack_cap` 超過才擋） |
| `<Subject k>`↔`<Picture k+1>`、圖 ≤9／總 ≤12、主角前 5 名 | 擋 | 改 **E52**：`<Picture N>`／`<Video N>` 各自編號對 refmods tag；每個標籤都要有包、每個包都要被引用、`label` 要和順序一致；**E53** 場景包第一 |
| E22–E25、E43／E44 | 擋 | 照用（讀 `integrated_multimodal_description`） |
| E28 14 號風格 | 擋 | 照用（參考看 refmods） |
| — | — | **E55** `integrated_multimodal_description` 開頭≠風格錨（段落 `metadata.style_anchor_en` > 定案 `style_anchor` > 14 號固定錨；都沒有也擋） |

`lint_h3_prompt(..., backend="remix")` 的必填區塊改成三欄 `integrated_multimodal_description`／`overall_soundscape`／`non_diegetic_music`，其餘規則照用。refcheck（R4）與站位閘門（R6）見 §2.3.1d。REMIX 三欄輸出（R5）已接上（見上方「編譯」）。尚未做：送件 adapter（R7，含送件前自動跑 refcheck）、`h3d pack`（R8）、single480 抽卡流程（R9）、verdict／失敗目錄（R10）。

### 2.3.1d 參考包涵蓋 `h3d refcheck`（PR-R4）與站位／視線閘門 `h3d staging`（PR-R6）

> **證據範圍**：下列 measured 全部只來自《噩盡島》ch02 **EP04** 的有效抽（家機 REMIX，V1.3＋turbo）；其他專案、其他 backend 都沒量。規則的寫法規範見 `references/storyboard/continuity-ledger.md` §2／§4／§5，這一節是它的程式版。

**`h3d refcheck`**（`scripts/storyboard/refcheck.py`）：

```
python scripts/h3d.py refcheck --root .                               # 根目錄 segments*.json（缺 refmods 時用 video-bindings.json 同 ID 段補）
python scripts/h3d.py refcheck --root . --segments segments-ep04.json --json
python scripts/h3d.py refcheck --root . --takes videos/remix-queue.jsonl   # 已送出抽次：每行 key、prompt 或 prompt_file、packs 或 refmods
```

- **詞表不寫死**：從 `adapt/bible.json` 的 characters／creatures／extras／locations／props 與 `assets/character-packs.json` 的 packs 每項讀 `name_en`、`aliases_en`（字面詞，大小寫不分、整字、容許複數）、`alias_patterns_en`（正則）；中文 name 不參與比對。計畫表頂層可寫 `"refcheck": {"strip_patterns": [...], "generic_en": [...]}`：固定句（Style lock、NOTEXT 之類）剝掉不比，普通物件只列出給人看。只看畫面描述欄（`integrated_multimodal_description`／`detailed_description`），環境音與風格錨不算。
- **E50 具名資產沒有包**：提示詞命中某資產的詞、或段落在場名單有它，refmods 卻沒有它的包（看 `id`，或計畫表登記的包名＋服裝變體包名）。**E50 豁免缺原話**：`pack_waivers`／計畫表 `waivers.<段>` 沒有 `quote` 不算豁免。（measured：ch02 S01-a／c／d 寫了巨蟒、銀槍卻沒包，VOID-refs S01-d t1 槍沒有斷成三節棍、蛇骸像焦黑盤管；用同一份 queue 回測，結果和 ch02 refcheck 一致，差別只在 ch02 把銀槍豁免寫死在程式裡。）
- **E51 未綁包的人群字眼**：students／crowd／people／classmates／others／bystanders／onlookers／passers-by；有 `kind: extras` 包、句中有失焦／剪影寫法、`as tall as the others` 比例錨、`Only these … people` 宣告句都不算；也可 `{"id": "E51", "quote": …}` 豁免。audit 的 E21 已擋同類問題，所以 E51 只在 refcheck 報，不在 audit 重複。
- **backend**：remix＝錯誤（exit 1）；**ref2va 同樣檢查但只提示**（訊息標「ref2va 只提示」、exit 0；覆蓋看 `reference_images`／`identity_anchor_ids`／`face_subject_ids`），既有 ref2va 門禁一個都沒改。
- **audit 整合**：`audit_refs_and_segments.py --audit-refs … --project-root .` 在 remix 分支會把 refcheck 的文字比對併進 E50（專案詞表有英文名時才有作用；沒寫 `name_en`／`aliases_en` 時行為同 R3）。
- **還沒接**：送件前自動呼叫（R7 送件 adapter 才有 remix 送件）。

**`h3d staging`**（`scripts/storyboard/staging_lint.py`，兩個 backend 都適用；碼延續 `director_lint.py` 的 D 系列，D01–D05 是階段 4 分鏡層）：

```
python scripts/h3d.py staging --root .                 # 預設全部警告，exit 0
python scripts/h3d.py staging --root . --strict        # 本次把 D06–D08 當錯誤
python scripts/h3d.py decide staging_gate strict --quote "<使用者原話>" --root .   # 專案定案加嚴（warn＝預設）
```

| 碼 | 規則 | 預設 | strict | 證據 |
|---|---|---|---|---|
| D06 | 面向鏡頭：faces/looks/turns… at/toward the camera／lens／viewer、breaks the fourth wall、面向／直視鏡頭；`positions.facing=toward` 也算。否定句（never looking at the camera）、背對鏡頭不算 | 警告 | 擋 | measured（對鏡頭站著講 4 抽）；但 4 抽的提示詞都沒有字面「facing the camera」，文字 lint 抓不到那 4 抽，是防再犯 |
| D07 | 對話段（有 `<d>`／`(Sx)`）且畫面上 ≥2 個角色，整段沒有視線句（eyes on／looks at／glares at／turns to…；外觀介紹句的 cool gaze 不算） | 警告 | 擋 | measured；回測抓到 S04-b t1（兩人並肩對鏡），19 抽 pass 0 誤報；另 3 抽對鏡 fail 抓不到 |
| D08 | 同一鏡 ≥3 個具名角色沒寫「left to right: A, B, C」／rightmost／leftmost（每人都在動作句緊貼畫面側也算）；兩人鏡只在明寫 two-shot 卻沒交代兩人畫面側時提醒 | 警告 | 擋 | measured（左右對調 5 抽，全在三人段；補左到右後 S04-a t2、S01-c t2 一抽就過）。回測：5 抽對調抓到 4；**19 抽 pass 也有 10 抽被提醒**（點名不等於在畫面上），所以預設只警告 |
| D09 | 提示詞「left to right」名單順序和段落 `positions.order_lr` 相反 | 警告 | 警告 | inferred |
| D10 | 相鄰同場兩段 `positions` 的共同角色左右對調，且後段沒寫 `metadata.staging_reset`（原因） | 警告 | 警告 | inferred（continuity-ledger §5） |
| D11 | all three／both of them／in unison… 多人同步動作，建議逐人寫 | 警告 | 警告 | inferred（S06-b t1→t2 修法，1 抽） |
| D12 | 慢詞 slowly／gradually／near-freeze／hangs poised… | 警告 | 警告 | inferred（h3-video-prompting／h3-combat-impact 規範） |
| D13 | 每一鏡都是 static | 警告 | 警告 | inferred |
| D14 | remix 多人段沒有 `positions`（D09／D10 無從比對） | 警告（只 remix） | 警告 | — |

- **「每鏡剛好 1 個運鏡句」「鏡長 ≥2 s」不重做**：`--lint-h3` 的 E6（缺運鏡）、E14（同鏡重複運鏡句）、E4（切點間隔／首末鏡 <2 s）早就是錯誤，兩個 backend 共用；衝擊幀串段的短鏡例外照 h3-combat-impact。
- **嚴重度為什麼保守**：證據只有一個專案一集；D08 回測誤報率高、D06／D07 抓得到的只是失敗抽的一部分；其餘規則沒有對照組。專案要擋就 `h3d decide staging_gate strict`（只升 D06–D08，inferred 規則 strict 也只警告）。
- **豁免**：段落 `metadata.staging_waivers: [{"code": "D06", "reason": "…", "quote": "<使用者原話>"}]`（例如刻意讓角色對鏡頭說話）；沒有 `quote` 不算豁免，另列「豁免缺原話」。
- **remix audit 會帶上**：`audit_refs_and_segments.py --audit-refs` 的 remix 分支把 D06–D14 併進 warnings（strict 時 D06–D08 進 errors）；**ref2va 的 audit 輸出不變**，ref2va 專案請另跑 `h3d staging`。
- 角色名來源：`<Video N>／<Subject N> is 名字,` 介紹句、refmods 的 `display_name`、專案詞表（同 refcheck）。D10 只比相鄰且同 `scene_id` 的兩段。

### 2.3.2 全集 `segments-all.json` 怎麼產

多集專案要一份 `segments-all.json`（階段 5 快照納入，階段 6 門禁用它確認每集的片段都在）。產法：把**全部** layer2 一次編譯，輸出檔名指定為 `segments-all.json`：

```
python scripts/h3d.py compile --layer2 layer2/ --bible video-bible.json --bindings video-bindings.json \
  --project-root . --output-segments segments-all.json --check
```

**單一來源規則**：`segments-all.json` 存在時，階段 6 送件（`h3d next`）、`motion_qa`、QA／交付的預設全集、失敗目錄 ack 都以它為準；不存在才用 `segments-ep*.json`。所以它不能落後：strict 階段 5（`h3d next`、新核准、自動核准）會把它的段落 id 與每段內容 hash 和逐集檔聯集對帳，缺段、多段或內容不同都擋關，並印出上面的重產指令（不需要全集時也可直接刪掉它）。改了任何一集重編後，記得跟著重產全集。

**階段 5 strict 其他檢查**（`h3d next`、新核准、自動核准才跑；已核准段的重新驗證不追加）：
- **漏編**：每個 `layer2/layer2-*.json` 的 `segment_id` 都要出現在某個 `segments-ep*.json`，多集專案漏編一集不能進審核（不要的段請刪 layer2 檔並重審階段 4）。
- **提示詞落後**：段落 `metadata.source_layer2_sha256`（新版編譯器寫入）≠ 目前 Layer 2 → 分鏡改過沒重編；舊版編譯的段沒有此欄位不追溯。
- **綁定新鮮度**：有 `video-bindings.json` 時，每段 `source_sha256` 要等於目前 Layer 2，且 `inputs_sha256` 記錄的輸入沒變；否則先 `h3d bind` 再重編。
- **失敗目錄未處置**：權威提示詞命中 `enforce=error` 條目一律擋；命中警告而沒有涵蓋現稿（段＋提示詞 hash＋目錄版本）的 ack 也擋。首選改稿重編；使用者看過並接受才 `h3d ack <ID> --root . --note "<使用者原話>"`——要在**核准前**處置，因為 ack 檔在階段 5 快照內，核准後再 ack 會讓該段變成待重審。目錄或 ack 檔壞掉時 fail closed。
- **backend 一致**：定案 `video_backend=remix` 但段落是 Ref2VA 六段式（沒有 `refmods`）→ 擋；`h3d next` 在綁定不是 remix 或已落後時先給 `h3d bind`，remix 綁定新鮮時直接給帶 `--bindings` 的 compile 指令重編成 REMIX 三欄（PR-R5）；此判斷排在綁定新鮮度之前。
- `h3d next` 的優先序：backend 不符 → 綁定落後（`h3d bind`）→ 只剩失敗目錄命中時給 `h3d catalog --list` → 補編。核准已失效時先查產物本身，產物不齊就先給修正指令，不重建審核頁。

逐集 `segments-epXX.json` 則用 `--episode EPxx` 另編；`--bindings` 含其他集的段會自動略過。`--check` 的「17 條」是 `audit_refs_and_segments.py --lint-h3` 的 E1–E9、W10–W13、E14–E16、E18；E19 起是參考圖對帳與逐鏡撰寫審查。

### 2.3.3 段間連戲、無文字句、同場光線（#133 #138 #139）

- **前段終態自動帶入**：同一 `scene_id` 內依段號排序（`-a`、`-b`…`-z`、`-aa`），前一段有英文終態（`segment_end_state.planned_final_state_en` 或 binding `en_overlay.end_state_en`）時，本段第 1 鏡會加一句 `Starting state carried over from the previous segment: <who> <state>.`，人物從前段終態接起，不再回到參考圖站姿。只編部分段時，前一段從同目錄的 `layer2-*.json` 找。跨場景不帶入。關掉：`--no-carry-end-state`。前段終態只有中文 → 不寫，記 compile note。
- **終態要寫成姿勢**：例如 `{"Shen Luonian": "lies on his back at the bottom of the crater, pinned under the rock"}`；寫「結束」「同上」帶不出東西。
- **`--check` 連戲警告**（只警告不擋，已核准的包不受影響）：
  - `C1 前段無終態`：同場景前一段沒有英文終態，本段無從接起。
  - `C2 段間姿勢矛盾`：前段終態是躺／坐／跪／被吞，本段第 1 鏡卻寫站／走，且沒有 gets up／rises／pushes himself up 這類起身過程。
  - `C3 同場光線分裂`：同一場景的段落用了不同光線鎖（例如只為生物段改成中性白光）。改光線以整個場景為單位，或改用後製統一調色。劇情本來就換光（火光亮起）時可忽略。
- **無文字句**：角色描述、走位、動作或五小節出現 crest／badge／emblem／logo／taxi／bus／car door／sign／poster／banner／斑駁或水泥牆這類燒字來源時，逐鏡前的總述行自動補 `Badges, crests, vehicle doors, signs and wall surfaces stay plain and unmarked, with no lettering, no logos and no graffiti.`。需要可讀文字的段（招牌是劇情重點）在 Layer 2 `metadata.allow_lettering: true`；全專案關掉：`--no-lettering-guard`。物件描述本身也建議寫正向的 `plain embroidered badge with no lettering`。
- 編譯結果 `metadata` 會記 `lighting_lock_line`、`carried_end_state`、`no_lettering_added`，方便 QA 對照。

## 2.4 階段 0–3 產物內容門禁（stage_content_checks.py）

`h3d next`、`h3d approve --auto` 與 `build_stage_review.py --approve-stage` 判斷階段 0–3「產物齊了沒」時，會跑
`scripts/stage_content_checks.py`（也可手動：`python scripts/stage_content_checks.py --root . --stage N`）：

| 階段 | 擋什麼 |
|---|---|
| 0 | `project.md` 殘留 init 模板佔位符（`<…｜…>`、`<中文說明>`）、「畫風」空白、`aspect_ratio` 與 `decisions.json` 定案不一致 |
| 1 | `validate_character_bible.py` 的 ERROR、`bible.json` 佔位符、`source.json` 仍是 init 骨架或 `must_keep` 對不到 `story_units`、缺 `adapt/series-outline.md` 或它還殘留模板佔位符（`{{…}}`） |
| 2 | `assets.md` 卡片（標題、`- **欄位**：`、表格列）殘留佔位符、登記的設定圖／母版圖檔案不存在（反引號內的路徑可含空白與中文）；`delivery_scope.no_image` 時改檢文字設定卡，審核頁缺圖只畫紅框不阻斷 |
| 3 | 劇本佔位符、`validate_structure` 閘門與錯誤、handoff 的 `title`／`episode_goal` 還是 TODO、handoff 的 `aspect_ratio` 與 `decisions.json` 定案不一致（`sync_script.py` 每次同步會自動對齊，並在集名還是 TODO 時用劇本集標題補上）、`check_continuity` 閘門、`compare_adaptation` 原著對帳硬錯誤（漏 MUST_KEEP、未記錄刪減、未回報缺口或矛盾） |

已核准的階段不會因為之後新增的檢查失效：核准快照已綁定內容 hash，內容改了才需要重審。

## 2.5 使用者定案與逐段結論（decisions.json／verdicts.json）

- `decisions.json`（專案根目錄，格式 `references/schemas/decisions.schema.json`）：每條定案含 `id`、一句話 `rule`、`value`、`source`（使用者原話＋日期）、適用 `stages`。重新定案時舊值進 `history`。
  `h3d next` 會在需要的階段前要求定案存在（畫風／比例／設定圖引擎→階段 2、台詞政策→3、驗收政策→6、剪輯方式→7）。
- `acceptance_policy` 的值是 `{rerun_on: [...], accept: [...]}`，只能用固定問題代碼：
  `extra_person` 多出人、`burned_subtitle` 燒字幕、`face_mix` 混臉／同框露臉、`wardrobe_wrong` 服裝錯、`style_shift` 畫風突變、`composition_broken` 構圖嚴重問題、`grid_leak` 分鏡總覽圖殘留、`paper_text` 紙面出字、`aged_face` 人物稍老、`low_chroma` 低彩度、`color_jump` 色調跳躍、`no_audio` 缺音軌、`other`。
  `h3d decide acceptance_policy recommended --quote "照建議"` 會寫入建議值（前七項重跑；紙面出字、人物稍老、低彩度、色調跳躍可接受）。
- `review/verdicts.json`（格式 `references/schemas/verdicts.schema.json`）：segment_id → `verdict`（pass／warn／fail）、`reason`、`evidence`（證據圖）、`decided_by`（agent／user／policy）、`issues`。結論綁影片 hash，影片重生後自動過期。
  分類規則：技術硬錯誤（時長漂移、比例錯）一律 fail；`decided_by=user` 最大；其餘套政策（碰到 `rerun_on` → fail，fail 但問題全在 `accept` → warn）；沒有結論＝未驗收（技術綠燈也一樣）。
- 階段 6 閘門：有 verdicts.json 時，政策判 fail 的段落擋核准，**不能覆寫**；技術 QA 的量化指標未過可用 `--override --reason` 由使用者帶理由放行，覆寫紀錄（理由、時間、被覆寫的問題）永久留在 project-state。

## 2.6 決策收件匣與自動核准（h3d inbox／h3d approve --auto）

**原則：人只看例外。** 收件匣取代逐階段把所有資料攤開的審核頁（舊八頁保留給除錯；`--stage N` 仍負責綁審核快照）。版面、卡片欄位與禁止事項見 `references/review-page-spec.md`。

- `h3d inbox --root .`（或 `build_stage_review.py --project-dir . --inbox`）產生 `review/inbox.html`（standalone、手機優先、縮圖 webp 內嵌、目標 < 5 MB）與 `review/inbox.json`。
  資料只讀 `decisions.json`、`review/verdicts.json`、`review/project-state.json`，選用 `videos/qa-report.json` 與影片抽 10 幀條（`--strips all|recent|none`）；階段 7 的待定音色角色另讀 `segments-ep*.json` 的 `external_narration[].speaker`。
- 卡片來源（依會不會擋下一步排序）：
  1. 目前階段還沒定案的規則（`decisions.json` 缺項）
  2. verdicts 依政策判 fail（擋核准）／warn（不擋；超過 3 段併成一張）；`decided_by=user` 的結論列在「已決定」
  3. 技術 QA 量化指標未過、且不在政策 `accept` 內 → 問使用者要不要覆寫
  4. 有畫外台詞、但還沒有 `voice:<角色>` 定案的角色（一張卡列全部）
  5. 階段 2：`assets/reference-manifest.json` 的 `review_disposition` 寫「不通過／退回」或 `approval_status` 為 rejected → 「設定圖自檢不通過」卡；階段 2 核准卡內嵌本批設定圖縮圖（角色優先，最多 6 張），並列出自檢標「瑕疵」的圖
  6. 階段 4：缺構圖、`sketch_status: rejected` 的鏡 → 一張「還有 N 鏡缺構圖／M 鏡自檢退回」卡（退回圖放 `panels/_rejected/` 會當證據縮圖；退回的鏡不會被門禁認領，有 `sketch_file` 的鏡只認綁定檔）
  7. 階段 5：缺 `reference_images` 或檔案不存在、同段 >1 張可辨識人臉角色圖（混臉）→ 卡；使用者接受混臉就在 `acceptance_policy.accept` 加 `mixed_face_refs`，之後改列「自動處理」
  8. 階段等核准、且沒有其他卡也不在自動核准授權內 → 「階段 N 等你核准」
- 卡片的影響／建議／選項可以在寫結論時指定：`h3d verdict <段> warn --reason ... --evidence ... --impact "..." --recommend "..." --option "後製疊墨線=EP01-S04-d：後製疊九道墨線" --option "維持現狀=EP01-S04-d：不處理"`。
- 單獨把舊版階段審核頁傳給使用者時加 `--self-contained`（`build_stage_review.py --project-dir . --stage N --self-contained`）：`../images/…` 會內嵌成 webp，單檔不破圖。
- 使用者回覆卡片上的文字後：定案用 `h3d decide`、段落裁示用 `h3d verdict <段> <結論> --by user`、角色音色用 `h3d decide voice:<角色id> "<音色>" --quote "<原話>"`。

**自動核准**：`h3d approve --auto [--stage N] [--dry-run] --root .`

- 授權只能來自使用者：`h3d decide auto_approve 1,3,4,5,6 --quote "<原話>"`。**階段 0 與 2 永遠要人決定**，寫進去會被拒。
- 條件：該階段收件匣沒有未決卡、`h3d next` 要求的定案都在、前一階段有效核准、產物檢查通過。
  階段 6 另需：驗收政策已定案、沒有未驗收段、沒有判重跑的段；技術 QA 問題全部屬政策 `accept` 時自動帶覆寫理由，否則要人決定。
  階段 7 另需：每個有畫外台詞的角色都有使用者本人定的 `voice:<角色>`（`--by user_delegated` 會被拒）。
- 核准走 `project_state.approve_stage_detailed`（正門），依據（政策 id、原話、verdicts 分類）寫進該階段的 `auto_approval`／`auto_approval_history`。
- `h3d next` 在符合條件時會直接指示 `h3d approve --auto --stage N`。

**階段 5 段級核准（PR-19a）**

- 階段 5 核准（人工或自動）時，`project-state.json` 的 stage-5 另記 `approval_segments`：每段指紋＝段 JSON＋它掛的參考圖檔 hash＋涵蓋本段的 catalog ack；`shared`＝分段檔外殼（去掉段清單後的欄位）、檔案清單、未綁段的 ack、其他快照產物。
- 核准後只改了部分段，`h3d next`／`h3d status` 會列「stage-5 有 N 段核准後變了、待人工重審：…（其餘 M 段仍核准、可送件）」：
  - **送件閘門**：`h3d submit` 只送已核准且未變的段（批次自動跳過待重審段並列出；`--segment-id` 指到待重審段直接拒送）；`h3d run` 計畫含待重審段就停下（結束碼 1），用 `--only` 只跑已核准段。
  - **重審**：`build_stage_review.py --project-dir . --stage 5 --segments X,Y`（或 `all`）產 `review/stage-5-prompts-rereview.html`，只列這些段、綁當下段指紋，不改階段狀態；使用者明確通過後 `h3d approve --stage 5 --segments X,Y --user-note "<使用者原話>"`（也可寫 `h3d approve 5 --segments ...`）。重審頁產出後段又改了就要重產。新核准走 strict 檢查，但只看這些段自己的錯誤；全部待重審段都核准後，整個階段 5 回到有效核准（快照換成現況，下游階段 6 核准隨之需重審）。
  - **改過的段一律人工**：`h3d approve --auto` 遇到待重審段一律擋下；`--segments` 不能搭配 `--auto`。
  - **刪除的段**也列待重審（重審＝確認刪除）；把改動改回原樣就自動恢復核准。
  - **deps**：待重審段若已有 `videos/<段>.mp4`，`h3d deps --status` 一律列入 stale（`prompt_stale`、`stage5_pending_review`），不需先 `--record`。
- 退回整份重審的情況：舊快照沒有 `approval_segments`（行為照舊）、`shared` 變了、前置階段（0–4）核准失效或版本變了、不屬於任何待重審段的產物檢查錯誤。
- 已核准段的重新驗證不加新檢查（strict 只在 `h3d next`／新核准／自動核准）。

**舊結論轉換**：`h3d verdict import <conclusions-*.json…> --root . [--dry-run] [--keep-unknown] [--overwrite] [--no-issues]`
把「segment_id → 一句中文結論」轉成 verdicts.json：✅→pass、✅（附註）／⚠️→warn、❌→fail；`_老大裁示_*` 物件裡的段落記成 `decided_by=user`；
只看「原判：」之前的文字；pass 只推可接受類問題代碼；證據依序取 `videos/qa/tiles/<段>.jpg`→`videos/<段>.mp4`→原檔。

## 2.7 送件 runner、probe、階段 7 配音與 Concat 剪輯

**`h3d run --plan plan.json --root .`**（`scripts/runner/fv_runner.py`）

- 計畫檔是 JSON 陣列：`{"key", "segments", "segment_id", "out", "seed"}`；重抽用 `key` 加後綴（例如 `EP01-S04-b-take3`），避免與正式段的 ledger 互鎖。
- **單例鎖**：同一台機器只允許一個影片 runner（鎖檔 `~/.ai-comic-drama/video-runner.lock`，`AICD_RUNNER_LOCK` 可改）。偵測到外部 runner（專案自寫的 `fv_run_multi.py`、等待者、另一個 `h3d run`）就停下回報；`--wait-lock <秒>` 改成等待。只等不殺。
- **佇列**：`/queue` 有別人的工作就每 30 秒看一次，最多 `--blocked-wait` 秒（預設 900），仍忙就停下。
- **受保護 job**：`--protect-job <id>`（例如使用者自己的影片）絕不取消。
- **暫停／續跑**：`h3d run --pause --root .` → 目前這段收完就停（`paused_by_user`）；`--unpause` 後重跑同一指令續跑（已有輸出、ledger 進行中的段跳過）。
- **進度檔**：`videos/_runner-progress.json`；`h3d run --status --root .`。
- 結束碼：0 完成、1 審查失敗、2 無令牌、3 佇列／送件被擋、4 同錯兩次、5 輪詢逾時、6 暫停、7 有別的 runner、8 probe 擋下、9 例外。

**環境變數與路徑覆寫（預設值不變，換機器時才需要）**

| 變數 | 作用 | 預設 |
|---|---|---|
| `FREEVIDEO_API_URL` | submit／collect／resume／run／probe 的 API 位址，`h3d doctor` 也用它探測 port | `http://127.0.0.1:8189/freevideo/agent/v1` |
| `FREEVIDEO_TOKEN`／`FREEVIDEO_TOKEN_FILE` | 令牌本身／令牌檔路徑 | 依序找 `E:\FreeVideo\agent\token`、`~/.freevideo/agent/token`、`C:\FreeVideo\agent\token`（非 Windows 只看家目錄） |
| `AICD_FFMPEG`／`AICD_FFPROBE` | ffmpeg／ffprobe 完整路徑（只設 ffmpeg 時 ffprobe 取同目錄） | PATH |
| `COMFYUI_URL`／`VOICESTUDIO_URL` | `h3d doctor` 探測的 ComfyUI／VoiceStudio 位址 | `127.0.0.1:8188`／`127.0.0.1:8001`（TTS 位址另由 `config/tts.json` 的 `engines.voicestudio.base_url` 決定） |
| `AICD_OMNIVOICE_LAUNCHER` | tts_doctor 提示的 OmniVoice 啟動檔 | `E:\OmniVoice\啟動-OmniVoice.bat` |
| `AICD_H3_UPSTREAM` | `sync_h3_reference.py` 的上游 clone | 依序 `E:\MinimaxH3\h3-video-prompting`、本 repo 同層 `../h3-video-prompting` |

本機服務（127.x／localhost）的 HTTP 請求一律不走系統 `HTTP(S)_PROXY`（送件端與 TTS 都是）；設了代理的機器以前會把 VoiceStudio 健康檢查丟給代理，造成「沒開卻回報可用」。

**`h3d probe --segments segments-ep*.json`**（`scripts/runner/fv_probe.py`）：GET agent 根取已安裝 LoRA、GET `openapi.json` 取 JobSpec；
LoRA 沒裝 → error，附「拿掉 LoRA」與相近的已安裝名稱；多帶 `trigger`／`reason` → warning（送件端 `sanitize_loras` 只送 name＋strength）。
離線：`--installed a,b --schema openapi.json`。

**`h3d voice align --root .`**（`scripts/voice/voice_align.py`，階段 7 固定流程）

1. `asr`：faster-whisper 轉寫 `videos/<段>.mp4` → `voice/h3-asr.json`（已有的段跳過）。
2. `place`：畫內台詞（`timeline-plan-ep*.csv` 的 subtitle）對齊 ASR；畫外配音放在前一句畫內台詞結束後 0.15 秒、下一句前收，放不下加速 ≤ 1.2 倍，最後一句可溢入下一段開頭靜默；ASR 認不出的聲音＝亂語 → `mutes`（相鄰合併）。寫 `voice/placement.json`。人聽過的修正寫 `voice/placement-overrides.json`，重跑不會被蓋掉。
3. `duck`：`mutes` 區間原聲 −22 dB（`--duck-db`）→ `voice/muted/<段>.mp4`。
4. `loudnorm`：配音 −16 LUFS／TP −1.5（`--lufs`），套 tempo → `voice/final/<key>.wav`，寫回 `final`／`final_dur`。

輸入 `voice/manifest.json`：`{key: {segment, speaker, line, file, dur}}`。`--steps place,duck,loudnorm` 可跳過 ASR；`--dry-run` 只算放置。

**`h3d concat plan --name "<劇名> 全集粗剪" --root .`／`h3d concat build --location <資料夾> --root .`**（`scripts/edit/concat_adapter.py`）

- plan → `edit/full-plan.json`：每段影片（有 `voice/muted/` 就用壓過原聲的版本）、字幕（畫內台詞對齊 ASR 實際時間，對不到沿用分鏡；畫外台詞跟配音）、配音起點、`episode_starts`、`total`。
- build：Concat headless MCP（`concat.exe --mcp headless`）建**單一全集專案**：T1 影片（`clips_add_sequence`）、T2 字幕（`captions_add`）、T3 畫外音（`clip_add trackId=T3`）；專案已存在就停下不覆蓋。

## 2.8 階段 6 動態 QA 與後製變速（h3d motion／h3d ramp）

- `h3d motion --root . [--vad] [--segment <段>] [--force] [--report-only]`：光流量凍結、定住、起手延遲（需 opencv-python-headless、numpy），合併寫 `videos/speed-ramps.json`（status=proposed）；已 approved／rendered 且原片 sha 沒變的段不動。
- 人審清單、補 `float`（光流抓不到）、確認後 status 改 `approved`。
- `h3d ramp --root . [--segment <段>] [--rerender] [--dry-run]`：產 `videos/ramped/<段>.mp4`，原片不動；斷言台詞保護區 1×，驗證保護區音訊相關 ≥ 0.98。
- `h3d assemble`、`h3d concat plan` 自動改用變速版並以 `time_map` 換算字幕／旁白／配音時間（`--no-speed-ramps` 關掉）。
- 規則、清單格式與實測：`references/speed-ramp.md`。

### 2.8.1 交界連續性 QA（h3d qa --continuity，R3-16 方案 B，只警告）

`python scripts/h3d.py qa --continuity --root . [--segments segments-ep01.json ...] [--segment-id <段>...] [--window 0.9] [--out-dir ...]`（`scripts/storyboard/continuity_qa.py`，需 ffmpeg／ffprobe、numpy、Pillow）

- **實際切點**：模型常提早／延後 0.1–0.5 s 切鏡，用規劃秒數抽格會抽到錯的鏡。每個規劃切點（`metadata.cut_markers[].at_seconds`，沒有就 `shots[1:].start_time`）±0.9 s 內，取相鄰兩格 1−相關係數最大者為實際切點（新鏡第一格）；峰值 < 0.12 或不到窗內中位數 2 倍 → 「切點不明」（可能沒切或溶接）；偏離 > 0.5 s 另列警告。
- **拼貼圖**（每段一張 `videos/qa/continuity/<段>.png`）：「上段末格｜本段首格」、每個鏡交界「切前一格｜切後一格」、「本段末格｜下段首格」；上／下段取同一分段檔內相鄰段，沒影片的列略過。
- **三欄幀差**：每個鏡（實際切點之間，排除切點那一對）左中右三欄平均絕對幀差；某欄 < 最大欄 25%（最大欄 ≥ 1.0）→「一側靜止候選」（例如對打一方定住；單人置中構圖也會觸發，目視拼貼判斷）。
- 結果：`videos/qa/continuity/continuity-report.json`（`gate: warning_only`）。階段 6 審核頁（`build_stage_review.py --stage 6`）每段附拼貼、切點與警告。
- **只警告、不擋任何關卡**：不寫 `qa-report.json`／verdicts、不在任何核准快照內、結束碼只反映執行錯誤。人工 9 項判定（cut_pos、cut_state、seg_in、seg_out、identity、all_move、reaction、causality、smooth）尚未實作；目視問題照常用 `h3d verdict` 記結論。

## 3. 文件同步（references/h3）

`references/h3/` 是上游 `h3-video-prompting` 的 `references/` 同步副本，**不是手寫的**。

```bash
python scripts/sync_h3_reference.py --check            # 對本機 upstream clone 比對漂移
python scripts/sync_h3_reference.py --sync --write-manifest   # 同步並更新紀錄
```

- 紀錄檔：`references/h3/UPSTREAM.json`（上游 commit＋逐檔 sha256＋`local_only`＋`local_annotations`）
- CI：`tests/test_h3_reference_sync.py` 只驗「紀錄 vs 本地檔案」（不需網路），擋住偷改／漏檔／未宣告新檔
- 本專案追加：`lora-guide.md`（local_only）；`scenarios-people.md` 的三處 ★ 標註由 `local_annotations` 在同步時重套，不會被覆蓋

> 教訓：曾經只靠人工同步、SKILL 卻寫「同名同步」，結果落後 15 個檔案還缺 `shot-five-part.md`。
> 現在「同步狀態」是可稽核的紀錄，不是一句宣稱。

## 3. Provider 能力表

`scripts/storyboard/providers/freevideo.json` 宣告 fps、frames 區間、支援比例、參考圖／音訊／LoRA 上限，
每個欄位都標 `source`：

- `measured`：本機真的量過 → 違反是**硬錯誤**
- `docs`：官方文件或考證 → 只警告
- `assumed`：未驗證 → 只警告

另有 `providers/remix.json`（REMIX 角色包，見 §2.3.1c）：多了 `seconds`、`frames.rounding`（floor）、`max_refmods`、
`practical_pack_cap_by_vram`（ok／slow／fail 各自標等級）、`modes`、`steps`、`continue_from`、`requires_project`、
`negative_field`、`first_frame`、`loras`、`ref_dedup`、`tags`；`consistency_warnings` 依 `provider` 對照 `h3_spec.PROVIDER_FRAME_SPECS`。

送件前會印出能力摘要；與 `h3_spec.py` 常數不一致時會提醒更新。**專案覆寫只能加嚴、不能降級**
（把 `enforce=error` 改成 warning 會直接報錯）。

## 4. 常見訊息 → 處置

| 訊息 | 意思 | 怎麼做 |
|---|---|---|
| `17n+5 量子` / `frames 超出支援區間` | 分段長度不是合法量子或不在 124–362 | 改分段長度；真的知道自己在做什麼才加 `--allow-out-of-range` |
| `失敗目錄: [F-...]` | 命中已知失敗模式且該條 `enforce=error` | 依 `minimal_fix` 改稿 |
| `需明確確認：... --ack-warnings` | 命中警告，尚未 ack | 改稿，或改用 `h3d ack` |
| `已有 waiting 的 job` | 服務端還有活著的工作 | 先 `collect`，不要重送（會重複計費） |
| `duration_drift`／`.drift.mp4`／`.unverified.mp4` | 服務端回報或下載後量到的長度和要求的 `17n+5` 影格不符，片子已隔離 | 停下回報使用者（`h3d next` 也會停）；查是否手改過 segments。使用者決定重跑：`h3d submit --segments … --segment-id <段> --root-dir .`；其餘缺片段 `h3d resume … --resume-past-failures`。**不要用 `--force` 續跑**（會覆蓋既有影片、略過帳本去重） |
| `本機停止等待（timeout／interrupted）` | 本機輪詢逾時或被中斷；服務端工作沒有取消 | 不是失敗：稍後 `h3d collect`／`h3d resume` 收件，不要重送 |
| `QA 證據等級為 PARTIAL` | 缺段或未達 VERIFIED | 缺段：補跑後重驗。全段都有、只是彩度／分鏡總覽圖等量化指標未過：先 `h3d verdict` 逐段目視，使用者看過仍要核准時用 `--approve-stage 6 --override --reason "<使用者理由>"`（理由寫進 project-state） |
| `QA 含非預期分段` | QA 報告只對一集的 segments 檔，卻含其他集的結果 | 多集一次跑：`h3d qa --segments segments-ep01.json segments-ep02.json ... --videos-dir videos --out-json videos/qa-report.json` |
| `驗收結論需重跑` | `review/verdicts.json` 依 `acceptance_policy` 判為 fail | 改提示詞後只重跑這些段；不能用 `--override` 放行 |
| `project-state.json 在最後一次正式寫入後被手改過` | 有人手改狀態檔 | 停下回報；從備份還原或重建審核頁請使用者重核。**不准手改 project-state** |
| `影片 hash 缺失或不相符` | 影片被動過 | 重跑該段或重新產 QA 報告 |

## reference-manifest.json／bible 圖片欄位（schema 摘要）
- `assets/reference-manifest.json`：`{"<asset_id>": {"image_path": "images/x.png", "review_disposition": "...", "technical_review_notes": "...", "approval_status": "..."}}`；階段 2 審核頁與收件匣讀 `review_disposition`／`approval_status`。
- `adapt/bible.json` 角色／場景圖片欄位認 `reference_image`、`image_path`、`image_file`（含 `wardrobe_states[]`）。
- assets.md 每個資產區塊可加一行 `反美化：…` 或 `禁止特徵：…`（例：不帥、蠟黃、非偶像臉／無鱗無牙、不分叉舌），會併進該資產提示詞的負面約束。
- 劇本用到、但無場景母版圖的場景，階段 2 審核頁建置時會在 stderr 提醒（不阻斷）。

## 生物外觀檢查（#97 #101 #121）
- 編譯器對生物主體：固定描述含無牙／蚯蚓／肉褶口等口型特徵時，retention 不再寫死「頭部特徵來自參考圖」，改為頭口細節以文字為準；描述寫蛇名詞又寫無牙、或設定無牙卻在動作寫 tongue／hiss／fangs，compile 給警告（scripts/storyboard/creature_lint.py）。
- 生物階段（PR-17c，#142 #153 R3-2）：bible 角色 `variants.<階段>` 或 stage5 綁定的 `creatures[]` 條目可寫 `on_screen_en`（該階段逐鏡外觀句，編譯時只加在該階段的鏡頭）與 `banned_en`（前一型態詞，陣列或逗號分隔）；該鏡文字含禁用詞時 `compile_notes` 給 R3-2 警告，不中止；不寫則行為不變。動態詞庫與寫法見 references/h3/creature-motion.md。
- 參考圖與文字矛盾時模型以圖為準：生物外觀不符時先查參考圖（舌、牙、口型、顏色）再改文字。
- 色彩 QA：`python3 scripts/creature_color_qa.py --ref 參考圖 --frame 抽格.png ...`，色相、彩度分開報（預設容許 8°／0.10），超標 exit 1。
- 驗收（#134）：階段 6 verdict 建議 ≥4 fps 影格條，逐鏡回答「動作是否完成、終態是否成立、該不在鏡的人有沒有入鏡」。

## clip-map（#163）
`python scripts/edit/clip_map.py <專案根> [--cuts edit/cuts.json] [--write]` 產生 `edit/clip-map.json`（schema `ai-comic-drama/clip-map/1`）：每段的實際來源（原片或 videos/ramped/）、影格數（段長＝frames/fps）、time_map、cuts、變速＋剪鏡後的集內累積起點。只新增欄位，不改 speed-ramps.json／full-plan.json 既有欄位。`to_episode_time()` 把原片秒（台詞／ASR／配音）換成成片時間。voice_align／concat_adapter／assemble_episode 尚未改讀它（後續再接）。

## sync_script --resign（R3-15）
改已核准場景的劇本：`sync_script.py --handoff ... --script ... --resign`＝強制同步後把原本已核准的場景設回 approved＋locked，免手動 --force 再 --set-status。

## 小修（PR-17a：#147 #151 #154 #155）
- `verdicts.classify`：驗收結論是否過期只比影片 sha256；技術 QA 報告的 hash 與結論不符時，改以 `videos/<段>.mp4` 實檔 sha 複核，QA 報告比影片舊不會再誤報「影片已重生」（不看 mtime）。
- 自動 LoRA：英文 `kick` 只認踢人片語（roundhouse／spinning kick、kicks him／at／into…）；「his heels kick out」不再掛 H3_Combat_V2。
- E16：生物 `whips its neck／head` 單純甩頭不算打擊（`whips its tail at …` 仍檢查受擊反饋）。
- 逐鏡 lint 的景別解析把 `OTS_CU`／`OTS_MS` 當一個 token，不會被誤拆成 CU／MS；OTS 對白鏡不受 S3「太遠」警告。
- 第三輪打鬥／生物提示詞寫法（PR-17d）：references/h3/r3-prompting-lessons.md（節拍表、大招三拍、纏繞、因果重置、破音字等）。
