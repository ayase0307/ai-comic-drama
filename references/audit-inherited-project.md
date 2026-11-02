# 接手他人專案的稽核（Takeover Audit）

> 用在：使用者把一個已經有人做過的專案丟過來（「你接手」「前一個 agent 做的很爛」「看看有甚麼建議」），
> 或你自己要接著推進一個不是自己生的分鏡／提示詞包。
> **先稽核、再推進。** 不要沿著現有分鏡往下寫，壞掉的上游會讓每一鏡都重做一次。

## 0. 三個一定要先破的錯誤假設

| 假設 | 事實 | 怎麼破 |
|---|---|---|
| 「`h3d next` 說 done，所以做完了」 | `delivery_scope.end_stage` 到 5 = **階段 5 的產物被核准**，不代表每一集都有分鏡。10 集裡做完 1 集也會印 done | 數檔案：`segments-*.json`、`layer2/*.json`、`panels/`、`videos/` 各覆蓋哪幾集 |
| 「`adaptation-diff` 寫 100% 覆蓋，所以對白都保留了」 | coverage 算的是**引號句有沒有被碰到**；把一句切成 8 段碎片、或整句塞進別人的台詞裡，照樣 100% | 看「平均行長」欄位與 `<d>` 行長中位數 |
| 「`refcheck` / `staging` 全過，所以能送」 | 兩者都是**包與站位**檢查，不檢查台詞是不是一個人講的、鏡位是不是輪播、格式是不是當前後端要的 | 跑 `scripts/audit_inherited_project.py` ＋抽驗成片 |

## 1. 稽核順序（照這個順序，前一步不通就不用往下）

1. **專案結構與覆蓋範圍**：`segments-*` / `layer2/` / `panels/` / `images/` / `videos/` 各幾集、幾段、幾鏡、總秒數；
   跟事件對帳表（`adapt/event-coverage.md`）的規劃秒數比。完成率 = 實作秒數 ÷ 規劃秒數，直接寫進報告第一段。
2. **文字層抽驗（最省時、殺傷力最大）**：抽一場戲，把劇本台詞與原著的引號句並排看三件事——
   說話者是誰、是不是原文（子字串）、一句有沒有被切碎。
3. **重複與機械化訊號**：跑 `python scripts/audit_inherited_project.py --root <專案>`。
4. **後端格式**：`decisions.json` 有沒有 `video_backend`；`segments` 的 `refmods` 是否為空；
   `h3_prompt` 開頭是 `subject_definitions`（六段式／ref2va）還是 `integrated_multimodal_description`（REMIX 三欄）。
5. **實際成品**：若已有生成，抽 3–4 幀看圖（人是不是同一個人、身上有沒有不該有的道具、有沒有燒字），
   再跑後端的身份檢查（REMIX：`GET /jobs/{id}/identity`，`state=done` 後看 `status` 與 `runner_up`）。
6. **資產對帳**：同一角色在不同命名前綴下是不是有多個包。**先查 `adapt/bible.json` 的 `wardrobe_states`／`costume_note` 與原著行號，再判定是不是重複**：同一角色多包多半是不同服裝或不同年齡狀態（乾淨臉的少年 vs 蓄鬚的同一人），照圖或照檔名判定會誤刪真資產。只有兩包畫的是**同一個狀態**才算重複；是不同狀態就補 `variant_of` 登記（介面才不會看起來像兩個不同角色），不要刪。

## 2. 判定門檻（實測過的機械生成指紋）

| 訊號 | 正常長相 | 機械生成長相 | 意義 |
|---|---|---|---|
| 鏡位分佈 | 依節拍偏斜（對話多 MCU/CU，建立鏡才有 MLS/WS） | 六種鏡位各佔 1/6，最大／最小 < 1.25 | 迴圈輪播，不是導演選擇 |
| 運鏡分佈 | 偏斜 | 8 種各佔 1/8 | 同上 |
| `five_part_en.performance` 去重率 | 幾乎全不重複 | < 60%（287 鏡只有 84 種） | 模板套字 |
| `shot_intent.audience` 句式 | 每鏡不同 | 去掉引號內容後只有 1–2 種句式 | mail-merge，不是真的 shot intent |
| 有台詞鏡頭比例 | 40–70%，反應／建立／空鏡佔相當比例 | ≥ 95%（287/287） | 分鏡由台詞片段驅動，沒有導演層 |
| 台詞行長中位數 | 15–30 字（一句話） | < 12 字、且分佈集中在 10–16 | 為字幕長度硬切句 |
| 跨角色合併 | 0 | 一條 `<d>` 裡有 2 個以上角色的話 | 一個聲音念完全場 |
| 語速 | ≤ 4 字/秒 | > 4.6 字/秒的比例 > 20% | 鏡長先定、台詞硬塞 |
| `<!--` 標記 | 只在劇本註解 | 出現在 `<d>`／`external_narration.line` 裡 | 標記漏進 TTS |
| `OTS` 鏡頭 | 畫面至少 2 人 | 過肩鏡只有 1 人 | 鏡位與構圖沒對帳 |
| 道具注入 | 逐鏡綁定持有者 | 「A prop without a reference image appears in this segment」全域出現 | 道具會長在錯的人身上 |
| `refmods` | 每段有 | 全空 | 沒有走 remix 編譯，是 ref2va 六段式 |

門檻不是法律，是**引導你去抽驗的線索**。任何一項命中，就要打開那一鏡看文字／看圖確認，
報告裡只寫確認過的（並標 measured／inferred）。

## 3. 台詞管線的三個致命壞法（遇到就整段重做，不要局部修）

1. **碎片化**：為了字幕友好把一句切成 9 字一行，逗號換句號。
   下游會把碎片當獨立台詞配鏡，於是每 3 秒切一次、每鏡一句半句，語氣全碎。
2. **跨角色合併**：分鏡把連續碎片併回一條 `<d>` 時不看 `speaker`，兩個角色的話掛在同一個聲音上。
   H3 會用同一張嘴念完，對嘴與角色辨識同時崩。
3. **說話者漂移**：用「段落順序」而不是「Ｘ說：『…』」的敘述句判定說話者，
   上一個出現的人物會拿走下一句台詞。抽驗方法：隨機 20 行，逐行回原著找引號前的動詞主語。

正確形狀：**一行＝一個角色的一個完整句子（以原著的引號句為界），不做長度切分，不合併不同角色**。
音量和語速靠鏡長與留白解決，不靠切句。

## 4. REMIX 後端專屬稽核

- `GET /projects` → 確認專案 id；`GET /jobs?project=<id>` 的狀態欄位是 **`status`**（不是 `state`），
  影片工作看 `params.mode`（`pika480`/`pika768`/`draft`/`refine`/`long`），沒有 `mode` 又沒有 `params.prompt` 的多半是建包工作。
- **單一工作回傳多包一層**：`GET /jobs/{id}` 與 `GET /jobs/{id}?wait=25` 回的是 `{"job": {...}}`。
  直接 `d["status"]` 會拿到 `None` 並誤判「還在跑」——要取 `d["job"]["status"]`；完成後影片在 `result.video.path`，
  實際長度與幀數在 `result.video.meta.duration`／`.frames`（用它核對 17n+5，不要用規劃秒數）。
- **送件（技能沒有 adapter，自己打 API）**：`POST /jobs {kind:"generate", project, prompt: 該段的 h3_prompt,
  refmods: [段內 refmods 的 pack 名，照順序], mode:"pika480", seconds: metadata.effective_duration_sec,
  aspect, shot: segment_id, label, plan:{title_zh, storyboard_zh, start_state, end_state}, ref: 每次唯一}`。
  秒數用 `effective_duration_sec`（已對齊 17n+5），不要用 `target_duration_sec`，否則會多送或截掉尾巴。
- **場景母片決定成品外觀，提示詞壓不住**：影片會直接繼承場景包 `00_src` 的內容與光線。
  抽卡前先看一眼 `GET /packs/{name}/img/00_src`——母片是「夜景＋發光樓閣」的仙俠要塞，
  拿去拍「文明崩毀後的晨光空鏡」就會長出發光仙宮、天空還切成一半星空。母片不對就換包（同專案的 `*_scene_suiansky` 之類），
  或先重出母片；靠提示詞寫「daylight only, no glowing buildings」只能壓掉一部分。
- 已生成鏡頭要看 `GET /jobs/{id}/identity`：`state=done` 之後逐幀看 `status`，`warn` 幀連 `runner_up` 一起看——
  「最像的是別的角色」就是換臉，不用再抽圖判斷。
- 包標籤：`tag: Video` 才有 RefMod；`tag: Picture` 的角色／生物（單張圖）每鏡都會漂，要使用者決定要不要補訓練。
- 同一專案裡出現兩套命名前綴（各自有一套角色＋場景）＝ 同角色兩個包，**不代表重複**：先 `GET /packs/{name}/images` 對圖、再對 bible 的 `wardrobe_states` 與原著行號；不同服裝／年齡狀態就用 `POST /packs/{name}/meta {"variant_of": "<本體>", "display_name": "<中文名（狀態）>"}` 登記成變體，同一狀態才刪。跨集換裝（少年樣→蓄鬚樣）最容易被誤判成「兩張臉」。
- 包的 `00_src` 抓不到（404 或 14 bytes 的空檔）＝ 空包，該角色等於沒有參考圖，影片階段每鏡都會漂；先補圖或改用別的包，不要假設 `GET /packs` 列出來就能用。
- 分鏡拼圖／九宮格若燒了鏡號與秒數（`01 SH01 MCU · 2.84s`），**不可**當首幀／尾幀／關鍵幀送件，會直接變成燒字驗收失敗。

## 5. 報告長相（使用者要的是判斷，不是清單）

照這個順序寫，一段一件事：

1. **一句話結論**（能用／不能用／哪一層能用哪一層不能用）。
2. **實際狀態表**：檔案覆蓋、段／鏡／秒、規劃量與完成率、已生成鏡頭數、身份檢查結果。全部標 measured。
3. **P0（會讓成片不能用）**：每條都要能指到具體檔案、鏡號或數字，附一行重現指令或抽樣例。
4. **P1（會拖垮品質／工期）**：文件不同步、事件秒數放不下、缺視線句、缺包、接受混臉風險等。
5. **路線 A／B／C**：重建到某階段、只做 pilot、照現況硬送（並說明硬送會得到什麼）。
6. **要使用者決定的事**：路線、台詞粒度、成片體量、要補的道具／場景包、互相重疊的角色包怎麼收（先對狀態，再決定登記變體或刪）。每一項都给選項與推薦值。

寫檔案到專案根目錄 `AUDIT-<日期>.md`，不要寫進 `review/`（那裡是門禁產物）。
**稽核階段不送任何生成工作**；要送件先取得使用者同意，並先跑 `h3d refcheck`。

## 6. 收尾

稽核完先問路線再動手。動手的順序固定是：台詞管線 → 分鏡（事件驅動）→ 後端格式與綁定 → pilot 一鏡 → 放大。
反過來做（先修提示詞）會白做，因為提示詞是從壞掉的台詞與分鏡編出來的。

## 7. 重建時的實作順序與地雷

按「台詞 → 分鏡 → 綁定 → 編譯 → pilot 一鏡」走，每一步都會被下一步的門禁驗證。

**綁定／編譯**

- **每次改完 `layer2/*.json` 都要重跑 `h3d bind`**：bindings 檔記著 layer2 的 `sha256`，沒重綁就編譯會以 `Stage5 source SHA256 mismatch` 拒編。改了 `adapt/bible.json` 也一樣（bindings 同時記 bible 指紋）。
- `h3d compile --bindings …` **必須同時 `--bible video-bible.json`**（normalized 版），少給直接報錯。
- remix 綁定時，角色包若「預設包穿的就是這套服裝」，要在 `assets/character-packs.json` 該角色寫 `"default_costume": "W-…"`；不寫會被列成「缺變體包」擋住 bind。真的缺包才寫 waiver（必附使用者原話）。
- **新的場景包要同時登記進 `adapt/bible.json` 的 `locations`**（`location_id`＋`name`＋`visual_prompt_en`＋`reference_image`）：只寫 `assets/character-packs.json` 不夠，編譯會警告「場景 X 未登記，提示詞將缺少場景描述」，該段逐鏡提示詞就沒有場景，模型只能自由發揮。三段命名要對齊：`scene_id`（`S-…`）→ `packs.S-…` → 實際包名（`ej2_scene_…`）。
- `camera_optics.movement_en` 只收官方動詞：`static`／`trucks left|right`／`dollies in|out`／`pans left|right`／`tilts up|down`／`pedestals up|down`／`zooms in|out`。自創片語（「slow forward glide」「locked off」「handheld lateral drift」）會讓編譯直接失敗——寫完先想一次「這是哪個官方動詞」，改完 layer2 記得重 bind。
- 提示詞內不要重複寫「the camera …」：鏡頭標頭已經寫了運鏡，五小節的 Camera／Motion 再寫一次會被 audit 判 `E14 重複運鏡句`。Camera 小節寫機位與景別，Motion 小節只寫主體動作。

**重建 layer2 會清掉構圖綁定**

- 用自己的產生器重寫 `layer2/*.json` 時，`sketch_file`／`sketch_sha256`／`sketch_status`／`sketch_prompt`／`sketch_generation` 會一起被清掉，階段 4 門禁立刻變成 14 個紅框。重建前先按 `shot_id` 存一份快照，重建後比對 `shot_id` 補回（sha 仍相符才算）。`handoff_to_skeleton.py --force` 與 `scripts/storyboard/sketch_bindings.py` 會自動保留，手寫的產生器不會。

**構圖圖用支援清單外的後端出圖**

- `h3d imagegen --detect` 只認 repo 內建 adapter（Codex／經 FreeVideo 的 Qwen／手繪上傳）；直連本機 ComfyUI 跑自己的模型會顯示「不可選」。這條路可以走，但要用 `h3d imagegen --set manual --stage 4 --quote "<使用者原話>"` 登記成「外部上傳」，否則 `h3d next` 會一直叫你回去選後端。
- 帶參考圖的圖生圖模型（實測 Qwen-Image 2.1 經 ComfyUI `TextEncodeQwenImage21`）會**整張照抄參考圖的版面**：丟角色設定圖進去會回一張四視圖設定板，丟「空景母版」進去會把要畫的人也一起清空。逐鏡構圖要**純文字**出圖（把角色外觀、場景、光線、鏡位寫進 prompt），身分一致交給角色包在影片階段解決；帶圖只適合「以場景母版為底重畫構圖板」那類用途。
- 出完圖要回寫 `sketch_file`／`sketch_sha256`／`sketch_generation`（backend 寫實際用的那一套），並用 `sha256` 覆核一次；門禁比對的是磁碟上的真實檔案。
- 從 `five_part_en` 取欄位拼構圖 prompt 前先做型別收斂：同一個鍵在不同段可能是字串，也可能是 `{en, text, …}` 物件，直接切片會炸 `KeyError: slice(None, …, None)`。寫一個 `_txt(v)`（str 直取、dict 找 `en`／`text`、其餘 `str()`）統一處理。

**階段 5 的假錯誤（remix）**

- REMIX 三欄提示詞在階段 5 被報 `E1 必填區塊缺漏：subject_definitions／summary／retention_analysis／detailed_description`，
  通常不是提示詞錯：階段 5 頁面（`build_stage_review.py`）呼叫 `lint_h3_prompt()` 時沒把 `backend` 傳進去，
  就會拿 ref2va 六段式規則驗三欄提示詞。同一個字串手動加 `backend="remix"` 就是 0 error。
  修法是讓它讀段落 `metadata.video_backend` 再傳下去；修完重建階段頁，別去改提示詞迎合 ref2va。
- 若同一次還報 `E2 鏡頭數量不符（≥10 秒要 4–6 鏡）` 或 `E32 Motion 沒有過程`，那才是真的：
  拆鏡，或把 Motion 改寫成 first／then／as／finally 的時序句（靜態空鏡最容易漏時序詞）。

**加雙人引子的落地步驟**（設計見 `storyboard/spatial-consistency.md` §7）

- 第 1 鏡插 2.0 秒雙人鏡並標 `dual_lead_in: true` 之後：後面每一鏡的 `start_time`／`end_time`、`speech_window`、
  `line_timecodes` 全部 +2.0，`target_duration_sec` +2（frames 由 compile 自己算）。漏挪時間碼會被 assemble 擋。
- **那顆引子也要出一張構圖圖**：引言新增了 shot，沒補 PNG 會直接跳「缺少有效且對應的構圖 PNG」。
- 做完跑 `h3d staging --layer2`：原本的 W47 建議要消失、且沒有 W48 警告，才代表格式對
  （在第 1 鏡、剛好兩人、引子裡沒台詞、後面時間碼有往後挪）。

**階段頁與收件匣的先後順序**

- 每改一次 bible／劇本／分鏡，已產出的階段頁就作廢（`h3d next` 會說「審核頁產出後產物又改了」）。此時 `h3d inbox` 可能印「待決 0」——**不是沒事，是沒有有效階段頁可以產卡**。順序固定：先 `build_stage_review.py --project-dir . --stage <N>` 重建，再 `h3d inbox`，最後才交給使用者；任一環節跳過，使用者會拿到一張沒有決策項的空收件匣。
