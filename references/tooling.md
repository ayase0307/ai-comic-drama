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
| `compile` | Layer 2 → H3 六段式提示詞＋`segments-*.json`；`--check` 同時跑 17 條自檢與失敗目錄 | 每次改完分鏡 |
| `audit` | 參考圖／主體定義／台詞預算對帳 | 編譯後單獨重驗 |
| `submit` | 送 FreeVideo：能力表＋時長斷言＋ledger 去重 | 使用者要求生成時 |
| `collect` | 只把「已完成但沒下載」的工作收回來 | 批次中斷後 |
| `resume` | collect 後補送未產出的段 | 中斷後續跑 |
| `qa` | 影片驗收＋**證據分級** | 拿到影片後 |
| `assemble` | 配音、字幕、響度、拼接 | 交付前 |
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
- E38：`detailed_description` 與 `metadata.compiled_prompt_sha256` 不符＝編譯後被改寫。
- 處置：回 Layer 2 的 `five_part_en` 逐鏡改稿再編譯。不准改檢查器門檻、不准手改 segments 過關。規範見 `references/prompt-authoring.md`。

### (h) 鏡頭意圖（shot_intent／choice_why，I01–I06）

Layer 2 每鏡新增必填欄位 `shot_intent`（audience、story_beat、pov、emotional_shift）與 `choice_why`（shot_size、lens_distance、movement、blocking、background；有對白加 line_timing），schema 見 `references/storyboard/templates/layer2-storyboard.schema.json`。`handoff_to_skeleton.py` 會放 TODO 佔位；`validate_storyboard.py` 擋：I01 缺意圖、I02 缺理由、I03 佔位／過短、I04 同段意圖重複、I05 理由抄技術值或同段三鏡同一句、I06 跨段同一句 ≥5 鏡。邏輯在 `scripts/storyboard/shot_intent.py`。提示詞端另有 E40（抹背景）、W40（無線索氣氛詞）。

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

### 2.3.2 全集 `segments-all.json` 怎麼產

多集專案要一份 `segments-all.json`（階段 5 快照納入，階段 6 門禁用它確認每集的片段都在）。產法：把**全部** layer2 一次編譯，輸出檔名指定為 `segments-all.json`：

```
python scripts/h3d.py compile --layer2 layer2/ --bible video-bible.json --bindings video-bindings.json \
  --project-root . --output-segments segments-all.json --check
```

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
| 1 | `validate_character_bible.py` 的 ERROR、`bible.json` 佔位符、`source.json` 仍是 init 骨架或 `must_keep` 對不到 `story_units`、缺 `adapt/series-outline.md` |
| 2 | `assets.md` 卡片（標題、`- **欄位**：`、表格列）殘留佔位符、登記的設定圖／母版圖檔案不存在 |
| 3 | 劇本佔位符、`validate_structure` 閘門與錯誤、handoff 的 `title`／`episode_goal` 還是 TODO、`check_continuity` 閘門、`compare_adaptation` 原著對帳硬錯誤（漏 MUST_KEEP、未記錄刪減、未回報缺口或矛盾） |

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

送件前會印出能力摘要；與 `h3_spec.py` 常數不一致時會提醒更新。**專案覆寫只能加嚴、不能降級**
（把 `enforce=error` 改成 warning 會直接報錯）。

## 4. 常見訊息 → 處置

| 訊息 | 意思 | 怎麼做 |
|---|---|---|
| `17n+5 量子` / `frames 超出支援區間` | 分段長度不是合法量子或不在 124–362 | 改分段長度；真的知道自己在做什麼才加 `--allow-out-of-range` |
| `失敗目錄: [F-...]` | 命中已知失敗模式且該條 `enforce=error` | 依 `minimal_fix` 改稿 |
| `需明確確認：... --ack-warnings` | 命中警告，尚未 ack | 改稿，或改用 `h3d ack` |
| `已有 waiting 的 job` | 服務端還有活著的工作 | 先 `collect`，不要重送（會重複計費） |
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
