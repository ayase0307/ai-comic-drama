# memory.md — 跨 agent 交接記憶

每次收工更新，最新的在上面。進場規範見 `agent.md`。

## 現況（2026-10-17 初始化）

- repo：https://github.com/ayase0307/ai-comic-drama（main，MIT，public）
- 本機：`E:\MinimaxH3\ai-comic-drama`
- 性質：AI 漫劇端到端製作 Agent Skill（七階段：定調→分集→角色→劇本→分鏡→提示詞→生成→交付），影片提示詞走 MiniMax H3
- README 圖片：`assets/` 四張（banner、characters、pipeline 由 Codex 生成，storyboard 由 Gemini 生成）。storyboard 仍是舊風格，尚未改用 3D 國漫風
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

- [x] 整合上游 `2bddf6b`（2026-10-17）
- [ ] `SKILL.md` 核心原則 5 與階段 6 仍寫「生成前必須告知 credits 成本」；使用者說本技能本機運行不需成本提醒，待確認是否也要從 SKILL.md 移除
- [ ] `assets/storyboard.jpg` 改用 Codex 重生，統一 3D 國漫風
- [ ] 若要讓 Claude Code 自動讀到 `agent.md`，可加 `CLAUDE.md`（內容 `@agent.md`、`@memory.md`），使用者尚未要求

## 使用者偏好

- 每次修改本專案前，都要自動掃 `h3-video-prompting` 有沒有新 commit 並整合；衝突時以該 repo 為主（2026-10-17）
- README 要用高星數 repo 常見格式，頂部有設計圖，圖文並茂（2026-10-17）
- 圖片：橫幅與角色圖用 Codex 生成；風格 3D 國漫，女性角色身形姣好但穿著得體（2026-10-17）
- 授權 MIT；不需要成本提醒（2026-10-17）

## 決策紀錄

- 2026-10-17：整合上游採「以上游為準、整檔採用」而非逐句合併：抽查關鍵概念（對齊句、`<d>` 標籤、長片路線與幀數網格、808 卡點、一拍五件事等）上游都有，本機舊檔應是較早的快照；沒有逐句核對，若發現漏掉的本機內容可從 git 歷史（commit 7378828）取回；舊檔名（skin-block、official-format、motion-and-rhythm、references-and-longform、scenarios-visual）已刪除，改用上游檔名。官方格式細節（對齊句、`<d>`／`<scenetrans>`／`<cutoff>`、Ref2VA 六段）現由 `prompt-formats.md` 與 `audio-and-dialogue.md` 承接，欄位原文以官方 repo 為準

- 2026-10-17：公開 repo 建立；README 頂圖與角色圖最初用 Gemini，因畫面不佳改 Codex
- 2026-10-17：角色圖曾生成過暴露版，因為是公開 repo 捨棄，改用高領貼身漢服版
- 2026-10-17：`agent.md`／`memory.md` 放根目錄（使用者指定外層），沿用 `h3-video-prompting/workspace/` 的格式
