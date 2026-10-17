# memory.md — 跨 agent 交接記憶

每次收工更新，最新的在上面。進場規範見 `agent.md`。

## 現況（2026-10-17 初始化）

- repo：https://github.com/ayase0307/ai-comic-drama（main，MIT，public）
- 本機：`E:\MinimaxH3\ai-comic-drama`
- 性質：AI 漫劇端到端製作 Agent Skill（八階段：0 定調→1 改編→2 資產設定圖→3 漫劇劇本→4 導演分鏡→5 提示詞→6 生成→7 交付），影片提示詞走 MiniMax H3
- 2026-10-17 整併：`references/adapt/`＋`scripts/adapt/`（作者的 novel-to-manju v1.0.0，小說必須先改編，不得直接當劇本）；`references/storyboard/`＋`scripts/storyboard/`（作者的 cinematic-director-storyboard v2.0，取代舊分鏡格式）；新增 `references/consistency.md`、`references/styles.md`、`assets/styles/`（11 種風格樣圖）
- README 圖片：`assets/` 四張皆 Codex 生成；**`pipeline.jpg` 仍是七階段舊圖，待重生為八階段**
- 本技能只在本機使用，README 已拿掉成本提醒
- `references/h3/` 已同步上游 `2bddf6b`（見「上游同步」）

## 上游同步（h3-video-prompting）

- 上游 repo：https://github.com/ayase0307/h3-video-prompting（本機 `E:\MinimaxH3\h3-video-prompting`）
- **已整合上游 commit：`2bddf6b`（2026-10-17）**，掃描日期 2026-10-17，之後上游有新 commit 就從這個 hash 往後整合
- `references/h3/` 現在是上游 `references/` 的同名同步版（20 個檔，檔名與上游一致，以後可直接 diff/複製）；`scripts/color_qa.py` 同步自上游 `scripts/`
- 本技能自有的調整（同步時要保留）：
  - `scenarios-people.md` 的 A1／A5／A12 標題加了 ★漫劇標記
  - `references/minimax-h3.md` 的檔案索引、預算表、「放進漫劇流程」、來源段（指向上游）
  - `SKILL.md` 的 `references/h3/` 資源索引
- 已知懸空引用：`audio-pipeline.md`、`lighting-and-color.md` 提到 `audio-ab-tests.md`、`lighting-ab-tests.md`，這兩份只在上游 `workspace/experiments/`，本技能不收

## 進行中（動檔案前先看、收工清掉）

（無）

## 待辦

- [ ] 重生 `assets/pipeline.jpg` 為八階段（改編、資產設定圖兩格為新增）
- [x] 第一次 Opus 複審（2026-10-17）：3 個 CRITICAL 已確認修好
- [ ] 第二輪腳本修正（J-Cut 跨段台詞不被判違規、分段 >26 不壞檔、>15 秒單鏡拆分、格式錯誤 JSON 不噴 traceback、`--palette` HEX 過濾、劇本↔handoff 台詞比對、init 提示）由 Haiku 完成但**最終報告未送達**；主 agent 只抽查：語法編譯、10/10 改編測試、TODO 閘門 rc=1、壞 JSON 可讀訊息、H3 輸出無 HEX、單段台詞核對通過。**跨段 J-Cut 切句的情境沒有親自驗證**，下一位請用 Opus 複審實跑
- [ ] 已知低階問題：`estimate_duration.py` 計字法（含標點）與 `speech_utils.py`（去標點）不同；`references/h3/` 以外的 README 快速開始缺 validate_storyboard 一步
- [ ] 風格錨定詞只在 Codex imagegen 驗證過；換即夢／可靈／Midjourney 要實測（styles.md 已標）
- [ ] 小說改編與分鏡兩個子體系「沒有逐句比對」原作者版本，只做路徑與連結改寫；原作者更新時以 `E:\MinimaxH3\劇本改寫大師\novel-to-manju`、`E:\MinimaxH3\影片分鏡大師\cinematic-director-storyboard` 為準手動同步（本 repo 已改動：adapt/ 與 storyboard/ 檔內路徑、`validate_structure.py` 與 `run_all_tests.py` 的路徑、Layer 2 schema 新增選填欄位、`director_storyboard_assistant.py` 與 `validate_storyboard.py` 的 HEX／聲帶數值／--handoff 修改）
- [ ] 分鏡技能的 8 張教學關鍵幀（3.4MB）未收入，需要時從原目錄取

- [x] 整合上游 `2bddf6b`（2026-10-17）
- [x] SKILL.md／pipeline.md／model-profiles.md 的成本提醒已移除（2026-10-17，使用者同意）
- [x] `assets/storyboard.jpg` 已用 Codex 重生為 3D 國漫風（2026-10-17）
- [x] 已加 `CLAUDE.md`（`@agent.md`、`@memory.md`），Claude Code 進場自動讀取
- [ ] FreeVideo 只實測了握手與狀態查詢，**尚未實際提交過生成任務**；第一次真的出片時驗證 `references/freevideo.md` 的流程並回寫

## 使用者偏好

- 這個專案的大改版：由 Opus 當審查整併者、Haiku 當調查與執行子代理（2026-10-17）
- 要有主流漫劇風格的「風格鎖定錨」，用 Codex 各自生圖、以表格放在 README（2026-10-17）

- 每次修改本專案前，都要自動掃 `h3-video-prompting` 有沒有新 commit 並整合；衝突時以該 repo 為主（2026-10-17）
- README 要用高星數 repo 常見格式，頂部有設計圖，圖文並茂（2026-10-17）
- 圖片：橫幅與角色圖用 Codex 生成；風格 3D 國漫，女性角色身形姣好但穿著得體（2026-10-17）
- 授權 MIT；不需要成本提醒（2026-10-17）
- 技能建議搭配 FreeVideo 讓 Agent 無障礙協助影片生成（2026-10-17）

## 決策紀錄

- 2026-10-17：**一致性衝突裁定**（寫在 `consistency.md` §0）：(1) 有參考圖時外觀只在首次出現寫、沒參考圖逐字貼片段；(2) 九宮格只用於階段 2 關鍵幀鎖臉，階段 6 逐鏡生成；(3) HEX 只用於圖像模型與內部驗收，H3／影片改寫成「色名＋物體」。為什麼：H3 手冊建議與上游說法一致；九宮格不能個別重抽；H3 不吃 HEX。
- 2026-10-17：H3 守富皮膚段只用於寫實／半寫實風格，2D／水墨／Q 版／美漫不用（與其負面錨衝突）。
- 2026-10-17：風格調查摘要——11 種風格由 Haiku 子代理搜尋歸納；平台占比沒有公開數據；色盤與錨定詞為推斷，經 Codex 同角色樣圖校準（第一輪 3D 國漫出成半寫實、韓漫與日系電影感撞圖，已改寫錨）；第一輪 02、11 兩張因多執行緒搶輸出資料夾而空白，改為循序重生。未核實：DataEye 3D 漫劇占比、woshipm 沙雕 44%、紅果下架 1718 部（皆二手搜尋摘要）。
- 2026-10-17：Opus 首輪審查判 FAIL（骨架會靜默刪台詞、驗證器放行 TODO、台詞核對 CLI 跑不到、HEX 與 H3 衝突、語速規則不同），已派 Haiku 修腳本、文件由主 agent 修；複審見待辦。

- 2026-10-17：建議搭配 FreeVideo（本機 `http://127.0.0.1:8189`，安裝在 `E:FreeVideo`）；寫成 `references/freevideo.md`，階段 6 先試連它。令牌檔不得印出或寫進任何檔案。測試時機上有一部使用者未完成的影片（待選片），沒有動它

- 2026-10-17：整合上游採「以上游為準、整檔採用」而非逐句合併：抽查關鍵概念（對齊句、`<d>` 標籤、長片路線與幀數網格、808 卡點、一拍五件事等）上游都有，本機舊檔應是較早的快照；沒有逐句核對，若發現漏掉的本機內容可從 git 歷史（commit 7378828）取回；舊檔名（skin-block、official-format、motion-and-rhythm、references-and-longform、scenarios-visual）已刪除，改用上游檔名。官方格式細節（對齊句、`<d>`／`<scenetrans>`／`<cutoff>`、Ref2VA 六段）現由 `prompt-formats.md` 與 `audio-and-dialogue.md` 承接，欄位原文以官方 repo 為準

- 2026-10-17：公開 repo 建立；README 頂圖與角色圖最初用 Gemini，因畫面不佳改 Codex
- 2026-10-17：角色圖曾生成過暴露版，因為是公開 repo 捨棄，改用高領貼身漢服版
- 2026-10-17：`agent.md`／`memory.md` 放根目錄（使用者指定外層），沿用 `h3-video-prompting/workspace/` 的格式
