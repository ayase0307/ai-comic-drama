# memory.md — 跨 agent 交接記憶

每次收工更新，最新的在上面。進場規範見 `agent.md`。

## 現況（2026-10-18 升級：視覺化九宮格審核、單鏡局部修改與 H3 實測驗收）

- repo：https://github.com/ayase0307/ai-comic-drama（main，MIT，public）
- 本機：`E:\MinimaxH3\ai-comic-drama`
- 性質：AI 漫劇端到端製作 Agent Skill（八階段：0 定調→1 改編→2 資產設定圖→3 漫劇劇本→4 導演分鏡→5 提示詞→6 生成→7 交付），影片提示詞走 MiniMax H3
- 2026-10-18 新增能力（五階段系統架構升級）：
  - **人工審核鎖（HITL）與單鏡局部修改**：擴充 `handoff.schema.json` 與 `layer2-storyboard.schema.json` 支援 `review` 狀態鎖（`draft / pending_review / approved / rejected`、版號、雜湊鎖）；新增 `scripts/adapt/sync_script.py`（劇本 Markdown 與 JSON 局部同步與防覆寫）與 `scripts/storyboard/patch_shot.py`（單鏡局部修改、時間軸自動重算/差額吸收、保護已核准鏡頭），並升級 `layer2_to_table.py`。
  - **Qwen-Image 2.1 Turbo 鉛筆分鏡九宮格與單格零污染重繪**：新增 `scripts/storyboard/qwen_storyboard_grid.py`，連線本機 FreeVideo 內建 Qwen-Image 2.1 Turbo 逐格生成 1:1 映射黑白鉛筆草圖、單格局部重繪（其餘 8 格 SHA256 零污染）、自動拼合帶規格條之 3x3 九宮格，並支援 `--to-color-keyframe`（屬性解耦去除方向黑箭頭轉繪全彩首幀）。
  - **九宮格鉛筆分鏡成熟提示詞手冊**：於 `references/storyboard/anime-drama-grid-and-continuity.md` §四 固化五段式萬用骨架、9 大標準鏡位即抄即用模板庫與四步轉換鐵律。
  - **影片審查 Agent 工具**：新增 `scripts/storyboard/verify_video_shot.py`，自動檢驗時長誤差、黑白線稿畫風污染（`STYLE_BLEED_GRAYSCALE`）、九宮格分屏殘留（`GRID_PANEL_BORDER_DETECTED`）與跨鏡色差 $dE76$。
- 2026-10-17 整併：`references/adapt/`＋`scripts/adapt/`（novel-to-manju v1.0.0）；`references/storyboard/`＋`scripts/storyboard/`（cinematic-director-storyboard v2.0）；新增 `references/consistency.md`、`references/styles.md`、`assets/styles/`（11 種風格樣圖）
- `references/h3/` 已同步上游 `2bddf6b`（見「上游同步」）

## 上游同步（h3-video-prompting）

- 上游 repo：https://github.com/ayase0307/h3-video-prompting（本機 `E:\MinimaxH3\h3-video-prompting`）
- **已整合上游 commit：`2bddf6b`（2026-10-17）**；2026-10-18 已掃，無新 commit
- `references/h3/` 現在是上游 `references/` 的同名同步版（20 個檔，檔名與上游一致，以後可直接 diff/複製）；`scripts/color_qa.py` 同步自上游 `scripts/`
- 本技能自有的調整（同步時要保留）：
  - `scenarios-people.md` 的 A1／A5／A12 標題加了 ★漫劇標記
  - `references/minimax-h3.md` 的檔案索引、預算表、「放進漫劇流程」、來源段（指向上游）
  - `SKILL.md` 的 `references/h3/` 資源索引
- 已知懸空引用：`audio-pipeline.md`、`lighting-and-color.md` 提到 `audio-ab-tests.md`、`lighting-ab-tests.md`，這兩份只在上游 `workspace/experiments/`，本技能不收

## 進行中（動檔案前先看、收工清掉）

（無）

## 待辦

- [x] FreeVideo 實機生圖（Qwen-Image 2.1 Turbo 9 鏡鉛筆分鏡與單格重繪）與 H3 實機出片（A/B/C/D 四模式對照實驗）均已端到端驗證通過（2026-10-18）
- [x] 實作人工審核鎖（HITL）、單鏡局部修改（`patch_shot.py`、`sync_script.py`）、Qwen 鉛筆九宮格（`qwen_storyboard_grid.py`）與影片審查工具（`verify_video_shot.py`）（2026-10-18）
- [x] `assets/pipeline.jpg` 已重生為八階段（2026-10-17，ChatGPT 網頁版）
- [x] 第一次 Opus 複審（2026-10-17）：3 個 CRITICAL 已確認修好
- [x] 第二輪腳本修正（Opus 實跑驗證 6 項 PASS；其後再修 J-Cut overflow 規則，commit 已含）
- [ ] 已知低階問題：`estimate_duration.py` 計字法（含標點）與 `speech_utils.py`（去標點）不同
- [ ] 風格錨定詞只在 Codex imagegen 驗證過；換即夢／可靈／Midjourney 要實測（styles.md 已標）
- [ ] 小說改編與分鏡兩個子體系「沒有逐句比對」原作者版本，只做路徑與連結改寫；原作者更新時以 `E:\MinimaxH3\劇本改寫大師\novel-to-manju`、`E:\MinimaxH3\影片分鏡大師\cinematic-director-storyboard` 為準手動同步
- [ ] 分鏡技能的 8 張教學關鍵幀（3.4MB）未收入，需要時從原目錄取
- [x] 整合上游 `2bddf6b`（2026-10-17）
- [x] SKILL.md／pipeline.md／model-profiles.md 的成本提醒已移除（2026-10-17，使用者同意）
- [x] `assets/storyboard.jpg` 已用 Codex 重生為 3D 國漫風（2026-10-17）
- [x] 已加 `CLAUDE.md`（`@agent.md`、`@memory.md`），Claude Code 進場自動讀取

## 使用者偏好

- 小事情、調查、測試與重複執行請善用 Gemini Flash 子代理，主模型負責架構決策與審查把關（2026-10-17）
- 這個專案的大改版：由主模型當審查整併者、Flash/Haiku 當調查與執行子代理（2026-10-17）
- 要有主流漫劇風格的「風格鎖定錨」，各自生圖、以表格放在 README；**樣圖必須是角色設定板（面部特寫＋正／側／背），因為風格錨是用來鎖設定板的**（2026-10-17）
- Codex 影像額度用完會卡住（log 停在 `Reading additional input from stdin`）；改用使用者授權的 ChatGPT 網頁版（Claude in Chrome），JS 單次 ≤45 秒要分段輪詢，下載檔會變成 GUID .tmp，用位元組大小對應
- 每次修改本專案前，都要自動掃 `h3-video-prompting` 有沒有新 commit 並整合；衝突時以該 repo 為主（2026-10-17）
- README 要用高星數 repo 常見格式，頂部有設計圖，圖文並茂（2026-10-17）
- 圖片：橫幅與角色圖用 Codex 生成；風格 3D 國漫，女性角色身形姣好但穿著得體（2026-10-17）
- 授權 MIT；不需要成本提醒（2026-10-17）
- 技能建議搭配 FreeVideo 讓 Agent 無障礙協助影片生成（2026-10-17）

## 決策紀錄

- 2026-10-18：**MiniMax H3 九宮格參考四模式（A/B/C/D）實機對照裁定**：
  1. **Mode B（單張九宮格餵 I2VA）嚴禁使用**：第 0 幀為 9 格縮圖，第 2 幀（0.08s）發生災難性崩解白閃（幀間差 142.6），且後續鏡頭無法依序解析。
  2. **Mode C（一次塞 9 張獨立鉛筆草圖餵 Ref2VA）不推薦**：雖 API 支援（上限 32 張）且能還原部分構圖，但 RTX 4060 Ti 8GB 推論耗時翻倍（748s vs 368s），且多張黑白圖壓抑色彩並稀釋中間鏡頭。
  3. **Mode D（兩段式正解：分鏡 Layer 2 → Qwen 逐格黑白鉛筆草圖審核 → Qwen 去黑箭頭轉繪 1344×768 全彩首幀 → H3 逐鏡生成拼接）為唯一工業級標準**：構圖 100% 繼承鉛筆草圖、支援單格零污染重繪（17.5s/格）與單鏡獨立重抽。
  4. **鉛筆草圖轉彩必去黑箭頭**：實測發現鉛筆分鏡圖地面上的粗黑動勢箭頭若直接轉彩，會被 Qwen 當成路面黑色標線保留並帶入 H3 影片；因此在 `qwen_storyboard_grid.py --to-color-keyframe` 中強制注入屬性解耦擦除指令（移除所有手繪方向黑箭頭與輔助透視網格線），或使用 `--no-arrows` 生成無箭頭構圖底稿。
- 2026-10-17：**一致性衝突裁定**（寫在 `consistency.md` §0）：(1) 有參考圖時外觀只在首次出現寫、沒參考圖逐字貼片段；(2) 九宮格只用於階段 2 關鍵幀鎖臉，階段 6 逐鏡生成；(3) HEX 只用於圖像模型與內部驗收，H3／影片改寫成「色名＋物體」。為什麼：H3 手冊建議與上游說法一致；九宮格不能個別重抽；H3 不吃 HEX。
- 2026-10-17：H3 守富皮膚段只用於寫實／半寫實風格，2D／水墨／Q 版／美漫不用（與其負面錨衝突）。
- 2026-10-17：風格調查摘要——11 種風格由 Haiku 子代理搜尋歸納；平台占比沒有公開數據；色盤與錨定詞為推斷，經 Codex 同角色樣圖校準（第一輪 3D 國漫出成半寫實、韓漫與日系電影感撞圖，已改寫錨）；第一輪 02、11 兩張因多執行緒搶輸出資料夾而空白，改為循序重生。未核實：DataEye 3D 漫劇占比、woshipm 沙雕 44%、紅果下架 1718 部（皆二手搜尋摘要）。
- 2026-10-17：Opus 首輪審查判 FAIL（骨架會靜默刪台詞、驗證器放行 TODO、台詞核對 CLI 跑不到、HEX 與 H3 衝突、語速規則不同），已派 Haiku 修腳本、文件由主 agent 修；複審見待辦。
- 2026-10-17：建議搭配 FreeVideo（本機 `http://127.0.0.1:8189`，安裝在 `E:FreeVideo`）；寫成 `references/freevideo.md`，階段 6 先試連它。令牌檔不得印出或寫進任何檔案。測試時機上有一部使用者未完成的影片（待選片），沒有動它
- 2026-10-17：整合上游採「以上游為準、整檔採用」而非逐句合併：抽查關鍵概念（對齊句、`<d>` 標籤、長片路線與幀數網格、808 卡點、一拍五件事等）上游都有，本機舊檔應是較早的快照；沒有逐句核對，若發現漏掉的本機內容可從 git 歷史（commit 7378828）取回；舊檔名（skin-block、official-format、motion-and-rhythm、references-and-longform、scenarios-visual）已刪除，改用上游檔名。官方格式細節（對齊句、`<d>`／`<scenetrans>`／`<cutoff>`、Ref2VA 六段）現由 `prompt-formats.md` 與 `audio-and-dialogue.md` 承接，欄位原文以官方 repo 為準
- 2026-10-17：公開 repo 建立；README 頂圖與角色圖最初用 Gemini，因畫面不佳改 Codex
- 2026-10-17：角色圖曾生成過暴露版，因為是公開 repo 捨棄，改用高領貼身漢服版
- 2026-10-17：`agent.md`／`memory.md` 放根目錄（使用者指定外層），沿用 `h3-video-prompting/workspace/` 的格式
