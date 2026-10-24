# 原著解析與故事地圖模板（Source Analysis & Story Map）

## 0. 專案授權與路由參數（Phase 0）
- **專案 ID（`project_id`）**：`{{project_id}}`
- **原著名稱与來源**：`{{source_title}}`
- **授權狀態（`rights_status`）**：`[ ] owned_original  [ ] licensed_adaptation  [ ] public_domain  [ ] personal_study_only  [ ] unconfirmed（待確認）`
- **目標題材模式（`genre_mode`）**：`{{genre_mode}}`
- **畫幅比例（`aspect_ratio`）**：`[ ] 9:16  [ ] 16:9  [ ] other`
- **目標載體（`target_medium`）**：`[ ] motion_comic  [ ] ai_animation  [ ] live_action_short_drama`
- **成片形式**：`[x] 長篇漫劇（預設：整部一支連續長片，不設單集秒數）  [ ] 長篇・使用者要求分集（每集＝完整劇情單元）  [ ] 短劇短集（使用者明確選擇：共 N 集、每集約 90 秒 ±15%）`
- **預估總片長**：依事件數與交代需求估算（`python scripts/adapt/estimate_duration.py --events adapt/source.json`），不是集數 × 固定秒數

---

## 1. 核心戲核與主題（Phase 1）
- **一句話梗概（Logline）**：當 `{{觸發事件}}` 發生時，`{{主角身份與缺陷}}` 必須在 `{{時限/規則限制}}` 下完成 `{{核心目標}}`，否則將面臨 `{{致命代價}}`。
- **主題對立命題（Controlling Idea）**：`{{正面價值 vs 反面價值，禁止單詞主題}}`
- **主衝突（Central Conflict）**：`{{主角 vs 核心對抗力量}}`

---

## 2. 原著章節索引與有向因果鏈（Causal Chain）

| 原著引用 ID (`source_ref`) | 原著事件摘要 | 戲劇功能（選擇／資訊／關係／權力） | 直接前置原因 (`caused_by`) | 直接引發後果 (`leads_to`) | 保留分級 (`MUST_KEEP` / `MERGE` / `COMPRESS` / `REMOVE` / `REORDER`) | 交代需求（起因／經過／結果＋動機／時地） |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `chapter-001:p01` | | | | | | 起因、經過、結果 |

> 每列對應 `source.json` 的一個 `story_units` 項目；交代需求寫進 `exposition_needs`（省略＝起因、經過、結果），
> 角色抉擇需要讓觀眾懂動機時加 `needs_motivation: true`，事件前換了時間／地點時加 `time_place_shift: "三日後・書院"`。
> 改編稿完成後用 `scripts/adapt/event_coverage.py` 逐條對帳，被壓縮／跳過／交代不全的事件在階段 1 交使用者決定。

---

## 3. 伏筆埋設與回收追蹤表（Foreshadowing Map）

| 伏筆 ID (`clue_id`) | 埋設位置 (`planted_in`) | 表面呈現形式（視覺／對白） | 真實隱含真相 | 回收位置 (`payoff_in`) | 改編保護要求（嚴禁提前洩底事項） |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `clue-01` | | | | | |

---

## 4. 原著缺口與內部矛盾診斷清單（Gaps & Canon Contradictions）
> **紀律**：若原著資料不完整或前後自相矛盾，必須在此顯式列出並提出處理建議，**嚴禁悄悄虛構後續故事或掩蓋矛盾**。

- **資料完整性狀態**：`[ ] 完整  [ ] 局部殘缺（標明缺口位置）`
- **發現之原著矛盾清單**：
  1. `{{矛盾編號}}`：`{{位置 A 內容}}` vs `{{位置 B 內容}}` $\to$ **建議處置方案**：`{{保留 A / 保留 B / 設為角色說謊}}`
