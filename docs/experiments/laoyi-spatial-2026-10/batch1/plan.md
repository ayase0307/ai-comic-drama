# 老易「文戲空間邏輯不穿幫」A/B/C/D/E 實驗規劃（含武戲延伸臂）

Hark 2026-10-27 晚（台北）。依老大 18:58 定案「可以，進行規劃，但其實我覺得武戲也可能可以通用」。
來源：`incoming/laoyi-spatial-logic-exp/`（distilled.md、experiment-plan.md）。
**只做規劃與素材：沒有送任何影片 job、沒有連家機佇列、沒有建任何角色包、沒有改 ai-comic-drama main。**

## 0. 檔案

| 路徑（work/exp-laoyi/） | 內容 |
|---|---|
| `plan.md` | 本檔 |
| `shots_src.py` | 文戲 EP90 劇本＋逐鏡五小節原稿；武戲物理規則區塊 |
| `build_exp.py` | 原稿 → 每臂每組一個 repo 格式迷你專案（`repo/<臂>_<組>/`）→ `h3d bind`（remix）→ `compile_layer2_to_h3.py --check` → `prompts/`＋`jobs.json` |
| `checks.py` → `checks.md`／`checks.json` | 自檢報告（repo refcheck／staging_lint／prompt_authoring＋h3-combat-impact validate_prompt＋自家檢查） |
| `prompts/<wenxi|combat>/<組>/<段>.txt` | 每組每段 REMIX 三欄提示詞（可直接送） |
| `jobs.json` | 124 個 job（110 必做＋14 選配）＋25 個要先建的 prop 包；**未送** |
| `submit.sh` | 送件腳本（`dry`／`packs`／`jobs`），**未執行**；沒設 `LAOYI_CONFIRM=老大同意送件` 會拒絕 |
| `assets/` | 全部素材圖（＋`.takeN.png` 重抽紀錄、`prompts/` 生圖提示詞、`logs/gen_ledger.jsonl`） |
| `repo/` | 編譯用迷你專案（bible、character-packs、layer2、segments、build.log） |

重編：`cd work && python3 exp-laoyi/build_exp.py && python3 exp-laoyi/checks.py`。

## 1. 文戲主場：EP90〈角落那一桌〉（實驗專用，非 EP05 正片）

約 29 秒，4 段 × 2 鏡 = 8 鏡，每段 7.29 s（175 幀，17n+5）。沈洛年用 `ejin3_shenluonian`（乾淨 W02 制服；進店時還沒打鬥）。
固定地理沿用 EP05 `blocking.md` §1–2：**玻璃大門畫右、菜檯畫左、木隔間牆＋廚房門洞在後方偏左；機位一律在用餐區南側往北拍。**

座位（平面圖座標 x 西→東 0–10 m、y 南→北 0–7 m，面積 70 m²、七張小方桌、店內總人數 4）：
- 沈洛年：左後角小桌（約 1.8, 5.9）北側凳，背靠隔間牆、身體斜向畫左；**坐下後不再移動**
- 廚師：菜檯中段後方；**沈坐下後才舀湯**，再從菜檯北端繞出送到桌子左側
- 婦人：右後角靠玻璃的小桌（約 7.9, 5.8）北側凳；孩子：同桌東側凳、臉朝畫左
- 為避免三人同框：沈與婦人／孩子永遠不同鏡（老易「店小二趴櫃檯」同款）

| 段 | 鏡 | 秒 | 景別｜運鏡 | 觀眾要看懂 | 台詞 | 包（場景第一） |
|---|---|---|---|---|---|---|
| S01-a | 1 | 0–4.0 | 中遠景 35mm｜緩推 | 沈從畫右玻璃門進店、往畫左走 | — | 場景＋沈＋廚師（3） |
| | 2 | 4.0–7.29 | 中景 50mm｜固定 | 廚師在菜檯後聽到門鈴抬眼點頭、又低頭擦檯（不離開菜檯） | — | |
| S01-b | 1 | 0–4.2 | 中遠景 28mm｜左搖 | 他走到左後角靠隔間牆的小桌坐下（座位從此固定） | — | 場景＋沈＋廚師（3） |
| | 2 | 4.2–7.29 | 中近景 50mm｜固定 | 廚師看到他坐下才停手舀湯（觸發點） | — | |
| S01-c | 1 | 0–4.2 | 雙人中景 35mm｜固定 | 廚師從畫左繞出菜檯，把湯放到他面前（遞物） | 廚師：同學，你的湯。（約 2.2 s，碗放下後才說） | 場景＋廚師＋沈（3） |
| | 2 | 4.2–7.29 | 特寫 85mm｜固定 | 沈抬頭看畫左的廚師點頭道謝（反應鏡） | 沈：謝謝。（約 5.2 s） | |
| S01-d | 1 | 0–4.0 | 雙人中遠景 35mm｜固定 | 另一桌的孩子轉頭往畫左（沈的方向）看，婦人敲碗叫他吃 | 婦人：看什麼，快吃。（約 2.0 s，孩子轉頭後才說） | 場景＋婦人＋孩子（3） |
| | 2 | 4.0–7.29 | 特寫 85mm｜緩推 | 孩子再偷看一眼畫左、低頭扒飯（反應鏡） | — | |

## 2. 武戲延伸臂：EP91 = EP05 S02-b～S02-d（同店、同平面圖）

**選段：S02-b～S02-d**（不選 S01-c～S01-d）。理由：
1. 只有沈洛年＋巨鼠 2 個演員包（3 包含場景）→ 加 2 張圖參考後最多 5 包，仍在 8 GB 可行範圍；S01-c～d 有孩子＝4 包起跳，E 組會到 6 包（實測爆顯存）。
2. 三段合起來恰好測到三種空間事件：彈撲→命中（S02-b，接觸點）、後退→腳跟碰到側倒桌（S02-c，**地標物件的位置記憶**）、撲擊架爪→**位置互換**（S02-d，本集唯一一次互換，blocking.md §2 要求「畫面上有過程」）。
3. 打鬥地標明確（兩張側倒桌、隔間牆破洞），平面圖能畫、評分能數。
4. 原稿五小節逐字沿用 EP05 `shots.json`（段號改 EP91），A 組＝EP05 正片稿，可直接對照。

段長 5.875／6.58／5.875 s（141／158／141 幀），每段 3 鏡（打鬥短鏡例外，末鏡 ≤30%）。

## 3. 五組（＋選配 D9）的差異與參考清單

每段 refmods：**場景包 `ejin3_scene_buffet` 永遠第一（`<Picture 1>`）**，演員／生物包 `<Video N>`，實驗圖包排在後面 `<Picture 2>`、`<Picture 3>`（單圖包 tag＝Picture，各自編號）。8 GB 上限：本實驗最多 5 包（E 組），沒有 6 包段。

| 組 | 提示詞 | 額外參考（prop 包，單圖） | 文戲每段包數 | 武戲每段包數 |
|---|---|---|---|---|
| A 基準 | 現行 repo 寫法（場景句＋固定地理句＋五小節） | — | 3 | 3 |
| B 物理規則 | A＋**物理規則區塊**（面積 70 m²／10×7 m、七張桌、本段人數＋全店人數、座位、配角位置、互動觸發時機），插在場景句後、`<Picture 1>` 句前 | — | 3 | 3 |
| C 平面圖 | B＋平面圖 | `ejin3_exp_w_plan`（文戲）／`ejin3_exp_c_plan`（武戲，打鬥後狀態） | 4 | 4 |
| D 分鏡板 | B＋**本段四格分鏡板**（取代 C 的平面圖；老易原法的「分鏡圖當參考」） | `ejin3_exp_w_board_<段>`／`ejin3_exp_c_board_<段>` | 4 | 4 |
| E 逐鏡單格 | B＋本段每鏡一張單格（避開整板拼貼外洩） | 文戲：Shot 1、Shot 2 兩格；武戲：S02-b／d 取 Shot 1–2、S02-c 取 Shot 1＋3（腳跟碰桌＝空間地標） | 5 | 5 |
| D9（選配） | B＋**整場九宮格**（老易影片原法：一張九宮格對應約 30 秒；本段只對其中 2／3 格） | `ejin3_exp_w_grid9`（8 鏡＋座位圖）／`ejin3_exp_c_grid9`（9 鏡） | 4 | 4 |

圖參考的介紹句（每組都只說「它管什麼」，並明說每鏡是單一全幅實景，防止把格線畫進畫面）：
- C：`<Picture 2> is the floor plan, a top-down layout drawing of this same restaurant that fixes the counter, the partition, the kitchen doorway, the glass door and every table; it guides the spatial layout only, and every shot shows the real room as one full-frame live image.`
- D：`<Picture 2> is the storyboard of clip N, a four-panel storyboard of this clip, read row by row from the top, in which …; it guides blocking, framing and screen direction only, and every shot fills the whole frame as one live image.`
- E：`<Picture 2> is the Shot 1 frame of clip N, a storyboard frame of the opening of Shot 1 in this clip; it guides … of Shot 1 only …`
- D9：`… a nine-panel storyboard of the whole scene … this clip covers panels 3 and 4 only …`

**REMIX 無法表達／替代說明**
- REMIX 沒有「首幀」或「控制圖」輸入（能力表 first_frame：無），分鏡板、平面圖、單格都只能當 refmod 參考圖（prop 包，skip_8view）。這正是老易的用法（第 4 張參考），但影片原法是 ComfyUI ref2va 直接吃整張九宮格；REMIX 先萃取成 RefMod 再用，**萃取後是否還保留空間資訊未知**——這本身就是 D／D9 要測的。
- 老易「角色1–3＋九宮格（第 4 張最重要）」的順序，在 REMIX 會違反「場景包第一」（E53）。本實驗**保留場景第一**（風格錨靠它），九宮格排在演員之後；若 D9 明顯輸 D，再考慮另開一臂「九宮格取代場景包」（違反 E53，需要 --skip 與老大同意）。
- E 組用的單格是**從已驗收的四格板裁切**（老易「2×2 裁切、跨張重組」），D9 九宮格同樣由四格板格子＋座位圖重組；所以 D／E／D9 三組的畫面內容一致，差別只在「整板 vs 單格 vs 整場」——比較乾淨。
- 武戲每段 3 鏡、四格板第 4 格是「本段結尾狀態」，四格與三鏡不是一對一（介紹句已寫明）。

## 4. 素材（assets/，全部 Codex gpt-6-luna 生成、外部取圖，每張都看過）

| 檔 | 用途 | 用在哪 | 抽數 | 殘留問題 |
|---|---|---|---|---|
| `scene_back.png` 背面（反打） | 三視圖：補母片看不到的前牆 | 生圖參考、人審 | 1 | 店看起來比 7 m 深一點（狹長） |
| `scene_pano.png` 全景（娃娃屋斜俯視） | 三視圖 | 人審 | 3 | **三抽都只畫 6 張桌**（要 7 張），其餘地理對；只給人看、不進 job |
| `scene_flat.png` 平鋪（垂直俯視渲染） | 三視圖；平面圖、座位圖、武戲錨點圖的底 | 生圖參考 | 2 | 第 1 抽桌面材質錯（木紋）→ 重抽 |
| 正面＝既有母片 `ejindao/images/S-buffet-restaurant_plate_v1.png` | 場景包 `ejin3_scene_buffet` 本身 | 全部 job | — | — |
| `wenxi_plan.png` 裝修設計平面圖 | C 組參考；寫「面積 約 70 m²（約 21 坪）」「店內總人數 4 人」 | C | 1 | 圖內有標籤字（廚房、菜檯、大門、尺寸、標題框）——**格線／文字外洩風險就是要測的變數**，評分要記 |
| `combat_plan.png` 打鬥後平面圖 | 武戲 C 組：破洞、側倒桌 1／2、「店內總人數 2」 | C | 1 | 同上 |
| `wenxi_seatmap.png` 座位錨點圖（俯視渲染，四人就位） | 老易「人物空間關係圖」；四格板 s01b–d 的生圖參考；九宮格第 9 格 | D9、生圖 | 2 | 第 1 抽沈坐到桌子右側、婦人坐左側 → 重抽 |
| `combat_anchor.png` 打鬥站位錨點圖 | 武戲四格板的生圖參考 | 生圖 | 1 | 巨鼠畫得偏大（含尾約 2.5 m） |
| `wenxi_board_s01a…d.png` 文戲四格板 | D 組；E／D9 的裁切來源 | D、E、D9 | a 1／b 3／c 1／d 3 | b：第 1 抽角落桌畫到門洞右邊（會和婦人桌撞位）、第 2 抽走位朝右後方 → 第 3 抽對；廚師「抬眼」三抽都畫成驚嚇表情（只影響表情參考）。d：前兩抽孩子都看窗外（畫右）→ 第 3 抽對；第 3 抽光線偏暖橘、孩子 T 恤胸口有小色塊 |
| `combat_board_s02b…d.png` 武戲四格板 | 同上 | D、E、D9 | b 1／c 2／d 2 | c：第 1 抽用鞋尖踢桌（應是倒退鞋跟碰桌）→ 重抽；d：第 1 抽拋飛方向朝大門（畫右）→ 重抽成朝店內深處。三張的沈洛年褲子偏黑、髮型略尖 |

**生圖總數 24 次，定稿 14 張，重抽 10 次**（紀錄 `assets/logs/gen_ledger.jsonl`；每抽另存 `<名>.takeN.png`）。全部檢查過：門都在畫右、沒有多餘人物、分鏡板沒有字幕／編號／格線字（平面圖的標籤字是刻意的）。
| `wenxi_cell_*`、`combat_cell_*` | E 組單格（裁切自四格板，1280×720） | E | 0（裁切） | — |
| `wenxi_grid9.png`、`combat_grid9.png` | D9 九宮格（重組，1920×1080） | D9 | 0（重組） | — |

畫風錨：所有生圖都附母片＋角色設定圖，指定與 `stage5/build_video_bible.py` STYLE 同一套 UE5 semi-real 3D CG。

## 5. Seed 集與抽數

- 每組同 seed 集（組間唯一變數＝提示詞／參考）：文戲 `20261101, 20261102, 20261103, 20261104`；武戲 `20261201, 20261202`。
- 抽數：文戲 A–E 每段 4 抽、武戲 A–E 每段 2 抽；D9 選配文戲／武戲各 2 抽。
- 模式：`pdd480`・4 步、16:9、無 LoRA（與 EP04 一致；武戲 LoRA 另測，不混入本實驗）、`project: 噩盡島`、`shot = EXP-LY-<臂>-<段>-<組>`（家機放映廳同段五組並排）。

## 6. Job 數與家機時間（估）

| | job 數 | 估時 |
|---|---|---|
| 文戲 A–E（5 組 × 4 段 × 4 抽） | 80 | 約 5.4 h |
| 武戲 A–E（5 組 × 3 段 × 2 抽） | 30 | 約 1.9 h |
| **必做合計** | **110** | **約 7.7 h** |
| 選配 D9（文戲 8＋武戲 6） | 14 | 約 1.0 h |
| 先建 prop 包 25 個（skip_8view，每包約 3–20 s） | — | 約 5 分 |

估時公式（`build_exp.py est_sec`，**inferred**）：以 pdd480 實測 1 人 8 s＝237 s、3 人＝277 s 為基準，每多 1 包 +20 s、依幀數線性、每支 +15 s 排隊載入。5 包段在 pdd480 沒實測過（draft 5 包很慢），E 組可能更慢。
**建議分兩階段**：第 1 階段只送每組 take 1＋take 2（55 支、約 3.9 h），先看是否有一組明顯失敗（例如格線外洩），再決定送 take 3–4。`jobs.json` 已依 take 交錯排序（先跑完所有組的 take 1）。

## 7. 盲評

**盲化**：收件後把檔名換成隨機碼（`blind_map.json` 只有我和腳本知道），審核頁不顯示組別；同段五組＋選配的版本打亂順序並排。老大評完才揭盲。

**逐鏡評分表**（每抽每鏡一列；CSV `scores.csv`）：

| 欄 | 型別 | 說明 |
|---|---|---|
| code | 字串 | 盲碼 |
| shot | 1–3 | 鏡號 |
| seat_swap | 次數 | 座位／左右互換（例：沈換到另一張桌、婦人孩子換邊） |
| teleport | 次數 | 瞬移（同一鏡內位置跳動、無過程） |
| set_wall | 0/1 | 門／窗／菜檯／隔間牆換牆或消失（門不在畫右＝1） |
| extra_people | 人數 | 多餘人物（含背景路人、分身） |
| grid_leak | 0/1 | 畫面出現拼貼、格線、分格、字幕、平面圖文字 |
| eyeline_axis | 0/1/2 | 視線與 180° 線：0 錯、1 小偏、2 對 |
| face_id | 0/1/2 | 角色臉一致 |
| lipsync | 0/1/2／NA | 嘴型與台詞（H3 原生聲；說錯人＝0） |
| trigger | 0/1／NA | 互動觸發時機對（廚師在沈坐下後才舀湯、婦人在孩子轉頭後才說話） |
| usable | 0/1 | 整段可直接剪用（逐段一個值，寫在 Shot 1 列） |
| **武戲加項** contact | 0/1/2 | 接觸點：凳／爪／尾有沒有真的碰到、碰在對的位置 |
| physics | 0/1/2 | 力學：施力→傳導→受擊反應是否連貫（被打的有被打開、反震有方向） |
| swap_process | 0/1/2／NA | 位置互換是否有過程（S02-d：撲→架爪→拋飛看得到；S02-c：退到桌邊的距離合理） |
| note | 文字 | 自由描述 |

**每組指標**：可用率＝usable 段數／總段數；平均達到可用所需抽數（每段第幾抽第一次 usable）；格線外洩率＝grid_leak=1 的段數／總段數；穿幫數＝seat_swap＋teleport＋set_wall＋extra_people 的每段平均。

**判定門檻**（照 experiment-plan.md）：
- **D 或 E 的可用率比 A 高 ≥ 25 個百分點，且格線外洩 ≤ 10%** → 建議併入 repo：開放「分鏡板／平面圖當參考」為選項（文戲預設），寫入 D47。
- 只有 B／C 有效（B 或 C 比 A 高 ≥ 25 個百分點、D／E 沒有再多）→ 只併入物理規則區塊＋平面圖，分鏡板維持只給人看。
- 都無效 → 記成反證，不改。
- 武戲另判：武戲臂只有 6 抽／組（樣本小），**只能給「方向」**，不單獨觸發 repo 改動；若武戲方向與文戲一致，才把「武戲通用」寫進 D47 的適用範圍。
- 樣本量提醒：文戲每組 16 段次，±25 個百分點約等於 4 段次差異；結果接近門檻時，建議補抽而不是硬判。

## 8. 與 repo 的衝突與處理（不改 main）

| 衝突 | repo 現行規則 | 本實驗處理 |
|---|---|---|
| 俯視圖／平面圖當生成參考 | continuity-ledger／pipeline：佔位圖只給人看 | 只在實驗目錄的迷你專案用 prop 包帶入；正片 EP05 不動 |
| 整板參考（E20） | ref2va 禁多視圖板 | E20 在 remix 分支本來就跳過；D／D9 照送，E 組是「避開整板」的對照 |
| 分鏡 panel 只做逐鏡審核 | 不送進影片 | 同上，只在實驗目錄 |
| 階段 4 門禁 | 編譯要 stage-4 核准 | 實驗專案沒有 project-state → `--skip-stage-gate`（compile log 有「繞過未留紀錄」提示） |
| 武戲短鏡（<2 s 切點） | `compile_layer2_to_h3` 拒收（cut bounds）；h3-combat-impact 短鏡例外還沒進 compile | 武戲臂**不走 compile**：用 EP05 手工 build 的送件文字當 A 組，B 起只在固定位置插入物理規則句＋圖參考介紹句；再用 repo refcheck／staging／prompt_authoring＋validate_prompt 審 |
| 演員 `speech_window` | 編譯器把「Speech window: segment_seconds …」原樣寫進提示詞 | 文戲不填 speech_window，改在五小節寫「at about 2.2 s」（避免把內部欄位文字送進 H3）——可回報 repo 當 bug |
| 每段包數 | 能力表 6 包＝fail（inferred） | 實驗定案 `remix_pack_cap 5`（只在實驗專案 decisions.json） |

## 9. 自檢結果（`checks.md`）

- 文戲 6 組 × 4 段：`h3d compile --check` **錯誤 0**（A–D、D9 各 10 警告、E 14 警告）；獨立再跑 refcheck 4/4、staging 4/4、prompt_authoring PASS（錯誤 0、警告 0）。
- 武戲 6 組 × 3 段：refcheck 3/3、staging 3/3、prompt_authoring PASS（錯誤 0、警告 1＝W30 無編譯指紋，手工稿必然）、validate_prompt 合計 FAIL 0。
- 自家檢查（全部 42 份 prompt）：標籤與 refmods 一一對應、無 slow 字、無 `segment_seconds`／TODO：**0 錯誤**。
- 殘留警告（不改）：W11 字數 >700（文戲 A 約 740–760，B 起 880–990，E 最多；武戲沿用 EP05 的 713–814＋插入）；D13 S01-c 全段固定機位（對白鏡刻意固定）；W10 兩鏡同為 static（S01-c）；E54 5 包慢。字數超過是 B 組「物理規則區塊」本身的代價，**組間差異的一部分**，不壓縮。

## 10. 需要老大決定

1. **送不送、怎麼送**：建議分兩階段（先 take 1–2 共 55 支約 3.9 h；看完再送 take 3–4 共 55 支）。要不要連 D9 選配（14 支約 1 h）？
2. **25 個 prop 包**要在家機建（`ejin3_exp_*`，project 噩盡島、kind prop）；實驗結束後要不要刪？（建議保留到判定完成後刪）
3. 平面圖上有標籤文字（廚房／菜檯／大門／面積／總人數）。保留＝照老易做法（「寫面積」「寫總人數」）且能測文字外洩；拿掉＝更乾淨但少了面積人數資訊。**建議保留**，C 組外洩就記成 C 的缺點。
4. 是否另開「九宮格取代場景包」臂（老易原順序、違反 E53）——建議先不開，D9 結果出來再說。
5. 武戲 LoRA（melee 0.6＋motion_repair 0.3）本實驗**不加**，保持單一變數；同意嗎？
