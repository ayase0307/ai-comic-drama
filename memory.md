# memory.md — 跨 agent 交接記憶

每次收工更新，最新的在上面。進場規範見 `agent.md`。

## 現況（2026-10-17 初始化）

- repo：https://github.com/ayase0307/ai-comic-drama（main，MIT，public）
- 本機：`E:\MinimaxH3\ai-comic-drama`
- 性質：AI 漫劇端到端製作 Agent Skill（七階段：定調→分集→角色→劇本→分鏡→提示詞→生成→交付），影片提示詞走 MiniMax H3
- README 圖片：`assets/` 四張（banner、characters、pipeline 由 Codex 生成，storyboard 由 Gemini 生成）。storyboard 仍是舊風格，尚未改用 3D 國漫風
- 本技能只在本機使用，README 已拿掉成本提醒

## 上游同步（h3-video-prompting）

- 上游 repo：https://github.com/ayase0307/h3-video-prompting
- 本機 `references/h3/` 是何時、同步到上游哪個 commit：**未記錄，視為未同步**
- 2026-10-17 掃描時上游 `main` 在 `2bddf6b`（含新增 `audio-pipeline`、`lighting-and-color`、`action-choreography`、`shot-variety-and-staging`、`community-sources`、兩個 `example-*`；`audio-and-dialogue`、`camera-and-transitions`、`failure-triage`、`scenarios-*`、`example-fight-10s` 與本機版本有差異）
- 已整合的上游 commit：（待填；完成 §待辦第 1 項後寫在這裡）

## 進行中（動檔案前先看、收工清掉）

（無）

## 待辦

- [ ] **整合上游 `2bddf6b`**：依 `agent.md` §3 對照合併 `references/h3/`，補新檔索引到 `SKILL.md`，把整合到的 commit 填回上面「已整合」
- [ ] `SKILL.md` 核心原則 5 與階段 6 仍寫「生成前必須告知 credits 成本」；使用者說本技能本機運行不需成本提醒，待確認是否也要從 SKILL.md 移除
- [ ] `assets/storyboard.jpg` 改用 Codex 重生，統一 3D 國漫風
- [ ] 若要讓 Claude Code 自動讀到 `agent.md`，可加 `CLAUDE.md`（內容 `@agent.md`、`@memory.md`），使用者尚未要求

## 使用者偏好

- 每次修改本專案前，都要自動掃 `h3-video-prompting` 有沒有新 commit 並整合；衝突時以該 repo 為主（2026-10-17）
- README 要用高星數 repo 常見格式，頂部有設計圖，圖文並茂（2026-10-17）
- 圖片：橫幅與角色圖用 Codex 生成；風格 3D 國漫，女性角色身形姣好但穿著得體（2026-10-17）
- 授權 MIT；不需要成本提醒（2026-10-17）

## 決策紀錄

- 2026-10-17：公開 repo 建立；README 頂圖與角色圖最初用 Gemini，因畫面不佳改 Codex
- 2026-10-17：角色圖曾生成過暴露版，因為是公開 repo 捨棄，改用高領貼身漢服版
- 2026-10-17：`agent.md`／`memory.md` 放根目錄（使用者指定外層），沿用 `h3-video-prompting/workspace/` 的格式
