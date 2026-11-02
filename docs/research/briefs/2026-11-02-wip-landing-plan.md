# Brief：E: 的 6 檔 WIP 怎麼進 main（規劃）

- 日期：2026-11-02
- repo：`C:\Users\kirit\projects\ai-comic-drama-repo`（本目錄，branch `main` = `59f85e0` = origin/main，VERSION 0.10.1）
- WIP 來源（唯讀）：`E:\MinimaxH3\ai-comic-drama`，HEAD `277c62e`（= PR #123 合併，VERSION 0.10.0），6 檔未提交
- 你要做的事：**只回計畫，不要改任何檔**。這份 brief 的事實都已經實測過，不用重跑對帳。

## 目標

把三個獨立議題的 WIP 安全地送進 main。要你定案：PR 切法、rebase 策略、資料形狀、文件與 schema 同步範圍、端到端驗證清單。

## 已知事實（實測，可直接採信）

E: 那份 clone 落後 main 5 個 commit（PR #124–#128，0.10.0→0.10.1）。已用 `git merge-file -p --diff3 main base wip`（base＝E: HEAD）逐檔試合併，結果：

| 檔案 | WIP 變更 | 對 main 試合併 | 內容 |
|---|---|---|---|
| `tests/test_audit_stage0_3.py` | 2 hunk +3/-1 | exit 0（乾淨） | `import os`；`run()` 加 `PYTHONIOENCODING=utf-8` 的 env 與 `errors="replace"`。main 此檔與 base **完全相同** |
| `tests/test_ejindao_ep01_findings.py` | 2 hunk +3/-1 | exit 0（乾淨） | 同上（`ShortLineDensity` 的 subprocess） |
| `scripts/build_stage_review.py` | 1 hunk +2 | **exit 1（衝突）** | `build_stage_5` 內：新增 `_backend = str((seg.get("metadata") or {}).get("video_backend") or "ref2va")`，並在 `lint_h3_prompt(...)` 呼叫加 `backend=_backend,`。main 同一呼叫已加 `submit_endpoint=submit_endpoint,` → 同位置插入。`lint_h3_prompt` 簽名在兩邊都有 `backend`、只有 main 有 `submit_endpoint`，兩個 kwarg 可共存 |
| `scripts/storyboard/prompt_authoring.py` | 1 hunk +1 | exit 0（乾淨） | `COMPILER_BOILERPLATE` 加 `re.compile(r"the figure seen from behind matches ", re.I)`。main 同清單已新增 `^Forbidden:`、`^(?:Camera law\|Cast rule\|Environment lock):`（不同位置）。**對 main 仍必要**：main 的 `compile_layer2_to_h3.py:2834` 還在吐 `The figure seen from behind matches {panel_label_en} in <Picture n>`，而 boilerplate 清單 grep 該句＝0 |
| `scripts/storyboard/compile_layer2_to_h3.py` | 4 hunk +20/-2 | exit 0（乾淨） | ① `SHOT_OVERRIDE_KEYS` 加 `five_part_en`／`offscreen_subject_ids`／`accepted_unbound_subject_ids` ② `apply_stage5_binding` 把 stage5 綁定裡的兩個 id 清單複製進 shot ③ `_apply_en_shot` 支援 `en_overlay.shots.<gsid>.five_part_en`（逐小節 update；**同時寫 `action_and_performance.five_part_en` 與既有的 `shot.five_part_en`**）與兩個 id 清單 ④ `_apply_en_segment` 加 `en_overlay.style_anchor_en` 覆寫 `style_lock.anchor` |
| `CHANGELOG.md` | 1 hunk +2 | **exit 1（衝突）** | 兩行要塞進「未發布」；main 已把「未發布」清空並發成 `## [0.10.1] - 2026-11-02`（`4caf7ab chore: 發版 v0.10.1`） |

判定「沒進 main」時已全樹 `git grep`：`offscreen_subject_ids`／`accepted_unbound_subject_ids` 在 main 只出現在 `scripts/storyboard/prompt_authoring.py`（3／1 次）與 `tests/test_subject_coverage_gate.py`，**編譯器端為 0**；`five_part_en` 在 main 的 11 次出現都是既有欄位用法，沒有 overlay 覆寫路徑。

main 側 v0.10.1（PR #126）在同檔新增了：`physical_camera.py`＋`action_marks.py`、R2 物理機位總則 `Camera law:`、R4 人數／環境鎖（`physical_camera.classify_cast`、`cast_lock_wanted`、`cast_environment_lock`、`absent_objects_en`）、`Forbidden:` 失敗模式句、`--submit-endpoint`。WIP 的 4 個 hunk 與它們**文字上不重疊**。

## 鐵律（`AGENTS.md`／`comic-drama-repo` 技能）

- 全程繁中（註解、commit、PR）。`python -m unittest discover -s tests -q` 必須全過；新功能附單元測試。
- `h3d.py` 只做路由，規則留在 `project_state.py`／`decisions.py`／`verdicts.py` 等模組。
- PR 標題 Conventional Commits；**每個 PR** 在 `CHANGELOG.md`「未發布」加一行。
- **資料格式改動**要同步 `scripts/skill_version.py:SCHEMA_VERSIONS`，並更新 `references/schemas/` 的 JSON Schema 與 `references/tooling.md`。
- 升版照 `docs/RELEASING.md`（不要自己跳版號）。絕對不動使用者的專案產出（`review/`、`prompts/`、`storyboard/`）。
- 現況：`SCHEMA_VERSIONS` 只有 `project_state:2`／`decisions:1`／`deps:2`／`failure_catalog:2`；`references/schemas/` 只有 `decisions.schema.json`、`verdicts.schema.json`（**stage5 binding 沒有 schema 檔、沒有 schema_version**）。`references/tooling.md` §2.3（第 130–151 行）有 `en_overlay` 的 key 範例，目前列 `movement_en`／`blocking_en`／`anchor_objects_en`／`lips`＋`continuity_anchors_en`／`lighting_lock_line_en`／`end_state_en`／`voice_4d_spec_en`／`secondary_desc_en`，**沒有** WIP 新增的 4 個 key。

## 要你定案的問題

1. **PR 切法**：我初步想 3 個 PR（① 兩支測試的 Windows 編碼 ② `build_stage_review` 帶 backend ③ `en_overlay` 覆寫五小節／可見度／風格錨）。請批判這個切法，給定案：分支名、PR 標題（繁中）、每個 PR 的檔案清單、每個 PR 的 CHANGELOG 行文字。若你認為該合併或再拆，說明理由。
2. **資料形狀**：`five_part_en` 同時寫 `action_and_performance.five_part_en` 與 `shot.five_part_en`（後者只在原本就存在時才寫）——這是對的形狀嗎？應該只留一處、由單一 helper 決定，還是保留雙寫？請給明確結論與理由（`h3d` 只路由、規則要在模組裡的鐵律也要考慮）。
3. **語意風險**：`offscreen_subject_ids`／`accepted_unbound_subject_ids` 是「畫面裡不該出現誰」，main 的 `physical_camera` 環境鎖是「畫面只能有誰」——同一段提示詞是否會同時出現矛盾句？該用哪個最小實測組合驗（哪些指令、看哪幾行輸出）？
4. **schema 判定**：這批改動算不算「資料格式改動」→ 要不要動 `SCHEMA_VERSIONS`？stage5 binding 目前完全沒有 schema_version。給 yes／no 與具體做法（若要，加哪個 key、值多少、`references/schemas/` 要不要新增檔案）。
5. **文件同步清單**：`references/tooling.md` §2.3 要不要補 4 個新 key 與 `shot_overrides` 說明？`SKILL.md` 要不要動？還有哪些 references（`pipeline.md`、`prompt-authoring.md`、`storyboard/shot-intent.md`…）必須同步才不會讓 agent 讀到舊規格？
6. **rebase 策略**：同意「兩處衝突都兩邊都留」嗎？CHANGELOG 應該是把兩行放回空的「未發布」；`build_stage_review` 合併後是 `authored_shots=…, backend=_backend, submit_endpoint=submit_endpoint,`。有沒有更好的落地順序（例如先送零衝突的 PR 讓 main 往前，再 rebase 後兩個）？

## 輸出格式

1. 定案 PR 切法（表格：順序／分支名／PR 標題／檔案清單／CHANGELOG 行）
2. 每個 PR 的實作步驟（要改哪個檔、哪個函式、關鍵程式碼片段）
3. 資料形狀結論（`five_part_en` 雙寫留不留、理由）
4. schema／文件同步清單（逐檔逐節）
5. 驗證清單（可照抄的指令＋要肉眼確認的輸出片段）
6. 風險與回滾方式

再次提醒：**不要動任何檔案**，只回計畫。
