# 單集結構與節拍大綱模板（Episode & Scene Beat Sheet）

- **集數 ID**：`{{episode_id}}`｜`{{episode_title}}`
- **題材模式**：`{{genre_mode}}`｜**畫幅**：`{{aspect_ratio}}`｜**載體**：`{{target_medium}}`
- **長度**：長篇漫劇（預設）不設目標秒數，由本段／本集要交代的事件決定（`estimate_duration.py --events`）；
  短劇短集模式（使用者明確選擇）才填：`{{target_seconds}}` 秒（允許區間：`{{min_allowed}}`–`{{max_allowed}}` 秒）
- **本段／本集完整交代的事件**：`{{unit_ids}}`（每個都要有起因 → 經過 → 結果）

---

## 一、本集戲劇核心（Episode Dramatic Core）
- **本集角色目標（Goal）**：
- **核心阻礙（Obstacle）**：
- **兩難選擇與代價（Choice & Cost）**：
- **本集變化與結果（Change & Result）**：
- **下一集推進動機（Next Episode Hook）**：
- **因果債務對帳（Debt Ledger Link）**：
  - 承接舊債：`{{debt_id_in}}`
  - 新增新債：`{{debt_id_out}}`

---

## 二、單集微型五節拍配置（Micro-5-Beat Breakdown）

1. **Beat 1｜開場情境錨點（Hook Beat，前 3 拍內）**：
2. **Beat 2｜阻礙升級（Escalation）**：
3. **Beat 3｜戰術行動與抉擇（Action & Choice）**：
4. **Beat 4｜價值極性翻轉（Value Turn）**：
5. **Beat 5｜集尾推進點（Act-Out，類型：`{{act_out_type}}`）**：

---

## 三、分場狀態機與可製作性預審（Scene Cards）

### 場景 `{{scene_number}}`（`{{scene_id}}`）：`{{location_name}}` `{{time}}`/`{{interior_or_exterior}}`
- **對應原著**：`{{source_refs}}`
- **出場人物（≤ 3 人）**：`{{characters}}`
- **關鍵道具流轉**：`{{prop_id}}: {{initial_state}} -> {{final_state}}`
- **場景四步狀態機**：
  1. **進場狀態（極性 `{{entry_polarity}}`）**：
  2. **衝突與行動**：
  3. **資訊變化**：
  4. **出場狀態（極性 `{{exit_polarity}}`）**：
- **AI 可製作性風險評估**：
  - **風險等級**：`[ ] Low  [ ] Medium  [ ] High`
  - **原版視覺構想**：
  - **AI 簡化替代方案（若為 Medium/High 必填）**：
