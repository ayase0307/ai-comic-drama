# 分鏡交接協定與跨集狀態合併規範（Storyboarding Handoff Protocol）

- **責任領域**：定義從 `novel-to-manju`（劇本改編層）到下游分鏡／AI 影片生成技能（如 `ai-director`、`h3-film-studio`、`seedance-20`）的結構化資料契約、ID 規則與跨集連戲合併策略。
- **對應 Schema**：[`templates/handoff.schema.json`](templates/handoff.schema.json)

---

## 一、為什麼需要結構化分鏡交接（Why Handoff JSON）？

人類可讀劇本（`△` 與對白）刻意隱藏了鏡頭術語、資產 ID、時長區間與連戲前後狀態，以維持文學與表演的純粹性。但下游 AI 分鏡師與生圖／生影片工具需要確定的結構化資訊，否則會發生：
1. **角色換場變臉或換衣**（缺乏 `character_id` 與服裝狀態綁定）；
2. **關鍵道具憑空消失或瞬移**（缺乏 `continuity_initial` 與 `continuity_final` 對帳）；
3. **把不可刪的伏筆細節當成普通背景裁掉**（缺乏 `must_preserve` 聲明）；
4. **不清楚哪些段落有高崩壞風險需要改用替代拍法**（缺乏 `production_risk` 與 `fallback_plan`）。

---

## 二、識別碼命名規範（Identifier Conventions）

所有識別碼在全劇範圍內必須唯一且可排序，由 `scripts/adapt/validate_structure.py` 自動校驗：
- **`project_id`**：小寫英文連字符（kebab-case），如 `return-letter-manju`。
- **`episode_id`**：`EP` + 兩位或三位數字，如 `EP01`、`EP02`。
- **`scene_id`**：`{episode_id}-S{兩位場號}`，如 `EP01-S01`、`EP01-S02`（對應劇本中的 `1-1`、`1-2`）。
- **`character_id`**：小寫英文連字符，如 `lin-che`、`shen-ning`（必須在 `story-bible` 中註冊）。
- **`prop_id`**：小寫英文底線或連字符，如 `wet_letter`、`cracked_jade_pendant`。
- **`source_refs`**：`chapter-{章號}:paragraph-{段號}` 或 `section-{節號}:line-{行號}`，確保每一場戲都能回溯至原著具體位置。

---

## 三、單場交接核心欄位說明（Scene Handoff Fields）

每個場景在 `handoff.json` 中必須包含以下結構：

1. **基礎元數據**：`project_id`, `episode_id`, `scene_id`, `source_refs`, `adaptation_mode` (`canon_first` | `balanced` | `feasibility_first`), `genre_mode`, `aspect_ratio`, `target_medium`。
2. **空間與時間設定（`setting`）**：
   - `location_id`（對應場景資產卡）、`location_name`、`time` (`day` | `night` | `dawn` | `dusk` | `unknown`)、`interior` (`true` | `false`)、`timeline_tag` (`present` | `flashback` | `flashforward` | `dream`)。
3. **戲劇功能（Dramatic Core）**：
   - `scene_goal`（本場核心目標）、`entry_polarity` (`+` | `-` | `neutral`)、`dramatic_turn`（本場核心轉折點）、`exit_polarity` (`+` | `-` | `mixed`)。
4. **對白與音源清單（`dialogue`）**：
   - 依序記錄每句對白的 `speaker` (`character_id`)、`canonical_name`、`text`、`char_count`、`audio_type` (`onscreen` | `offscreen` | `voiceover` | `phone`) 與 `delivery_note`。
5. **連戲狀態機（`props` & `continuity_initial` / `continuity_final`）**：
   - 以鍵值對記錄關鍵道具、角色服裝或傷勢在**進場瞬間**與**出場瞬間**的狀態（例如：`"wet_letter": "on_table"` $\to$ `"wet_letter": "in_lin_che_hand_flipped"`）。
6. **時長預算（`estimated_duration_seconds`）**：
   - `min`（最快語速與緊湊動作秒數）與 `max`（慢速沉澱秒數）。
7. **改編變更記錄（`adaptation_changes`）**：
   - 記錄本場使用了 `MUST_KEEP`、`MERGE`、`COMPRESS`、`REMOVE`、`REORDER` 或 `ADDITION` 中的哪一種操作、理由與原著對照。
8. **分鏡師交接包（`storyboard_handoff`）**：
   - `recommended_generation_modes`：建議採用的生成模式陣列（`T2V`, `I2V`, `FL2V`, `Ref2V`）。
   - `required_visual_beats`：分鏡必須拍出的視覺節拍清單。
   - `required_audio_beats`：必須包含的關鍵音效或畫外音節拍。
   - `must_preserve`：攸關後續伏筆回收、絕不可在分鏡中被省略的視覺細節。
   - `production_risk`：風險等級（`low` | `medium` | `high`）、風險原因與 `simplified_alternative`（簡化替代方案）。

---

## 四、跨集與跨場狀態合併策略（Cross-Episode State Merging）

`scripts/adapt/check_continuity.py` 按時間線順序（剔除 `timeline_tag == "flashback"` 的純歷史回憶場後）執行狀態傳遞驗證：
- 場景 $S_{k}$ 的 `continuity_final[item_id]` 成為下一正敘場景 $S_{k+1}$ 的預設預期狀態。
- 若 $S_{k+1}$ 的 `continuity_initial[item_id]` 與 $S_{k}$ 的 `continuity_final[item_id]` 不一致，且未在 `adaptation_changes` 或 `state_transition_note` 中聲明場間合理變更（如換裝、移動），驗證腳本將拋出 `CONTINUITY_MISMATCH`（若涉及核心設定矛盾則升級為 `CANON_CONTRADICTION`）。
