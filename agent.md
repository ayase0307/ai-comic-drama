# agent.md — 進場規範

所有 agent（Claude、Codex、其他）要修改本技能前，先讀完本檔，再讀 `memory.md`。本技能在本機運行，不需考慮對外使用者的成本提示或帳號門檻。

- repo：https://github.com/ayase0307/ai-comic-drama（public，MIT）
- 本機：`E:\MinimaxH3\ai-comic-drama`
- 上游：https://github.com/ayase0307/h3-video-prompting（本機 `E:\MinimaxH3\h3-video-prompting`）

## 1. 開工前（依序，每次都做）

1. `git pull --rebase origin main`（別的 agent 可能剛推過）。
2. **掃上游**：`git -C E:\MinimaxH3\h3-video-prompting fetch origin`，再比對 `git -C E:\MinimaxH3\h3-video-prompting log --oneline <memory.md 記的已整合 commit>..origin/main`。有新 commit 就先整合（見 §3），整合完才做原本的任務；沒有就在 `memory.md` 記「已掃，無新 commit」與日期。
3. 讀 `memory.md`：現況、待辦、進行中、決策紀錄。
4. 讀 `SKILL.md`，再只讀要改的 `references/*.md`，不要整包灌。

## 2. 檔案分區

| 區域 | 內容 | 規則 |
|---|---|---|
| 技能本體 | `SKILL.md`、`references/`、`scripts/` | Agent 實際讀取的內容，改動要保守、要有依據 |
| 對外門面 | `README.md`、`assets/`、`LICENSE` | GitHub 展示用；圖片見 §5 |
| 維護紀錄 | `agent.md`、`memory.md` | 只給維護者，不被 `SKILL.md` 引用 |

## 3. 整合上游 h3-video-prompting

- 以上游 repo 為準：`references/h3/` 與上游衝突時，改成上游的說法。
- 上游檔名與本技能不同，整合時不要整個覆蓋，要對照內容再合併。對照（上游 → 本技能）：
  - `skin-realism-block.md` → `skin-block.md`
  - `motion-quality.md`、`rhythm-and-pacing.md` → `motion-and-rhythm.md`
  - `prompt-formats.md` → `official-format.md`
  - `references-and-editing.md`、`long-form-planning.md` → `references-and-longform.md`
  - `scenarios-world-and-styles.md` → `scenarios-visual.md`
  - 其餘同名（`audio-and-dialogue`、`camera-and-transitions`、`failure-triage`、`scenarios-people`、`scenarios-commercial`、`example-fight-10s`）
  - 本技能尚無對應的上游新檔（`audio-pipeline`、`lighting-and-color`、`action-choreography`、`shot-variety-and-staging`、`community-sources`、兩個 `example-*`）：評估後新增並在 `SKILL.md` 資源索引補一行
- 上游標為「方法主張／未在 H3 驗證」的規則，整合時保留該標註，不升格成確定規則。
- 整合完把上游 commit hash 寫進 `memory.md`「上游同步」。

## 4. 自動記錄（每個 agent 都要做）

- 開工時在 `memory.md`「進行中」寫下要動的檔案；收工清掉。看到別人佔用就換別的做或在待辦留言。
- 收工時在 `memory.md` 更新：做了什麼、沒做完什麼、下一位要注意什麼；重要取捨寫進「決策紀錄」（日期 + 一句話 + 為什麼）。
- 使用者說「之後都要…」「以後…」這類長期偏好，立刻寫進 `memory.md`「使用者偏好」。
- 不確定、沒驗證的主張寫進 `memory.md` 待辦，不要直接寫進 `SKILL.md`。

## 5. 寫作與素材約定

- 文件用繁體中文；提示詞範例、欄位名、`<d>` 標籤保持英文。
- 每條規則寫「怎麼做 + 為什麼／壞掉長怎樣」，不寫形容詞口號。
- 新增 reference 檔：`SKILL.md` 資源索引與 `README.md` 文件索引各補一行。
- README 圖片：橫幅、角色設定圖、流程圖、分鏡圖放 `assets/`，單張 ≤ 約 500KB。使用者偏好 **3D 國漫風**、角色身形姣好但穿著得體（公開 repo，不放暴露圖），用 Codex imagegen 生成；人物圖要固定同一組角色設定。
- 一次提交只做一件事。

## 6. Commit / Push

- 格式：`<type>: <description>`，type ∈ feat / fix / refactor / docs / test / chore。
- 技能本體、對外門面、維護紀錄的變更盡量分開 commit。
- 推送前 `git pull --rebase origin main`；有衝突解完再推，**不 force push**。
- 不 commit 暫存檔、生成的影片、金鑰。

## 7. 收工清單

- [ ] 已掃上游並在 `memory.md` 記錄結果
- [ ] `memory.md` 已更新（做了什麼 / 沒做完 / 注意事項 / 進行中已清）
- [ ] 新增或改名的 reference 已同步 `SKILL.md` 與 `README.md` 索引
- [ ] `git status` 乾淨、已 push
