# E: 6 檔 WIP 進 main 的計畫

**結論：** 切成 3 個 PR。從 main 開新分支，把 E: 的 diff 搬過來套用，不在 E: 那份 clone 上 rebase。你的切法有三處要改：
- `prompt_authoring.py` 歸進 PR②。
- PR② 不要自己判斷 backend，改用 main 現成的 `resolve_backend`。
- PR③ 要補一個人數鎖的矛盾修正。

E: 的檔案我沒有讀取權限（被擋），以下的 WIP 內容以 brief 為準。我實際看過的是 main 的程式碼，都附了行號。

## 1. PR 切法定案

| 順序 | 分支 | PR 標題 | 檔案 | CHANGELOG「未發布」那一行 |
|---|---|---|---|---|
| ① | `test/windows-subprocess-utf8` | `test: 子程序測試在 Windows cp950 下改用 UTF-8 解碼` | `tests/test_audit_stage0_3.py`、`tests/test_ejindao_ep01_findings.py`、`CHANGELOG.md` | `- 測試：test_audit_stage0_3、test_ejindao_ep01_findings 的子程序加 PYTHONIOENCODING=utf-8 與 errors="replace"，Windows（cp950）不再因解碼失敗而測試失敗。` |
| ② | `fix/stage5-review-backend-lint` | `fix: 階段 5 審查依段落路線 lint，並排除編譯器背影句` | `scripts/build_stage_review.py`、`scripts/storyboard/prompt_authoring.py`、`tests/test_remix_backend.py`、`tests/test_prompt_authoring*.py`（用現有的那支）、`CHANGELOG.md` | `- 修正：build_stage_review 階段 5 改用 resolve_backend 決定 lint 路線（段落 metadata → refmods → decisions.json），REMIX 段不再被 Ref2VA 規則誤報；COMPILER_BOILERPLATE 收「the figure seen from behind matches」編譯器句，不再算成手寫句。` |
| ③ | `feat/en-overlay-five-part-visibility` | `feat: 階段 5 en_overlay 可逐節覆寫五小節、宣告可見度豁免與風格錨` | `scripts/storyboard/compile_layer2_to_h3.py`、`tests/test_stage5_en_layer.py`、`references/tooling.md`、`references/prompt-authoring.md`、`CHANGELOG.md` | `- 新增：stage5 binding 的 en_overlay.shots.<gsid>／shot_overrides 可帶 five_part_en（逐節合併）、offscreen_subject_ids、accepted_unbound_subject_ids，en_overlay.style_anchor_en 可覆寫 style_lock.anchor（只作用於 Ref2VA）；人數鎖不再把該鏡宣告不入鏡的角色算進去。舊版編譯器讀到這些 key 會拒收（SHOT_OVERRIDE_KEYS 白名單）。` |

**為什麼 `prompt_authoring.py` 不放進 PR③：** 那一行修的是 main 既有的誤報。`compile_layer2_to_h3.py:2834` 已經在輸出這一句，跟 overlay 功能無關，性質和 PR② 一樣，都是「階段 5 審查誤報」。

**為什麼不再拆細或合併：** 三個 PR 的主題互相獨立、可以各自回滾。再拆就只剩一行一個 PR，不值得。

## 2. 各 PR 實作步驟

### PR①
直接套用 WIP 的改動：`import os`，再改成 `subprocess.run(..., env={**os.environ, "PYTHONIOENCODING": "utf-8"}, encoding="utf-8", errors="replace")`。不需要另外加測試。

### PR②
`build_stage_review.py:2382` 的 import 加上 `resolve_backend`，2399 行的呼叫改成：

```python
l_res = lint_h3_prompt(
    prompt_str,
    ...
    authored_shots=seg.get("shots"),
    backend=resolve_backend(seg, project_root=project_dir),
    submit_endpoint=submit_endpoint,
)
```

不採用 WIP 的 `metadata.video_backend or "ref2va"`。原因：`h3d bind` 產出的 REMIX 段可能只帶 `refmods`、沒有 `metadata.video_backend`，WIP 的寫法會退回 ref2va，又踩回「REMIX 被 E1 誤報」的老坑。`resolve_backend`（`audit_refs_and_segments.py:246`）已經照「metadata → refmods → decisions.json → ref2va」的順序處理。

`prompt_authoring.py` 直接套用那一行。

要加的測試：
- 一個帶 `refmods`、但沒有 `metadata.video_backend` 的段，跑 `build_stage_5` 不出 ref2va 專屬錯誤。
- 含 `The figure seen from behind matches X in <Picture 2>;` 的提示詞，不被算成手寫句。

### PR③（都在 `compile_layer2_to_h3.py`）
1. **白名單**：`SHOT_OVERRIDE_KEYS`（535 行）加入三個 key。`apply_stage5_binding:788` 已經會把非 action 的 override 轉交給 `_apply_en_shot`，所以 `shot_overrides` 這條路自動通。
2. **`_apply_en_shot` 加入口驗證**（binding 是手改檔，算信任邊界）：
   - `five_part_en` 必須是 dict，key 必須在 `FIVE_PART_KEYS` 之內，值是非空字串。
   - 兩個 id 清單必須是字串陣列。
   - 不合格就 `ValueError`。
3. **`five_part_en` 寫法**：見第 3 節，用單一 helper。
4. **WIP hunk ② 先確認再決定**：如果它是從 `binding["shots"][]` 複製 id 清單，就刪掉。main 沒有任何程式寫那裡（全樹 grep 為 0），那會成為沒人寫入的第三個入口。只保留 `en_overlay.shots` 和 `shot_overrides` 兩個入口。
5. **`style_anchor_en`**：`_apply_en_segment` 寫入 `style_lock["anchor"]`。REMIX 路徑讀的是 `style_lock_tail_en`（2944 行），不讀 anchor，所以 REMIX 段帶了這個 key 時記一條 compile note，比照 2853 行處理 `show` 的方式，不要讓它默默失效。
6. **人數鎖修正（第 3 題的答案）**，改 2507 行：
   ```python
   [c for _s in shots for c in (_s.get("character_ids") or [])
    if c not in (_s.get("offscreen_subject_ids") or [])]
   ```
7. **測試**（放在 `tests/test_stage5_en_layer.py`）：
   - overlay 只改 `motion`，其餘四節保留原值。
   - 不合法的 key 會報錯。
   - binding 宣告 offscreen 後，對編譯產物跑 `audit_subject_coverage` 不出 E40。
   - 三名人類加一名宣告 offscreen 時，`Cast rule` 寫 `exactly two people`，而且不出現該角色。
   - `style_anchor_en` 在 ref2va 段會生效；在 remix 段只多一條 note。

## 3. 資料形狀：`five_part_en` 不雙寫，改單一 helper

**結論：** 寫回讀取時用的那個位置，只寫一處。

讀取端 `_five_part_en`（977 行）的順序是「`shot.five_part_en` 優先，否則 `action_and_performance.five_part_en`」。WIP 的雙寫在 `shot.five_part_en` 存在時固然有效，但編譯產物裡會留下兩份內容不同的五小節（產物的 `shots` 會原樣輸出，見 3050 行），人審和 `audit_inherited_project.py:127` 讀到的可能是舊的那份。

做法：抽一個 `_five_part_slot(shot) -> (容器 dict, 原值)`，套用和讀取端相同的優先順序。`_five_part_en` 和 overlay 寫入都用它，合併成 `{**原值, **overlay}` 後寫回同一個容器。兩處都沒有值時，寫進 `action_and_performance`。

這樣優先順序只定義在一個地方，而且留在編譯器模組裡，`h3d` 不碰，符合鐵律。

## 4. schema 與文件同步

- **`SCHEMA_VERSIONS`：不動。** 這次只是在一個本來就沒有版號的檔案上新增可選 key，舊資料照樣能讀。只為這三個 key 新開 `stage5_binding` 版號，等於要另外做「寫入方蓋版號、讀取方檢查」整套機制，超出範圍。唯一的反向不相容是「新 binding 給舊編譯器讀會被拒」，這點寫進 CHANGELOG，讓 `h3d next` 的版本提醒去處理。
- **`references/schemas/`：不新增檔案。**
- **`references/tooling.md` §2.3**：
  - 在 JSON 範例的 shot 物件加上 `"five_part_en": {"motion": "..."}`、`"offscreen_subject_ids": ["C-x"]`、`"accepted_unbound_subject_ids": ["C-y"]`，段層加 `"style_anchor_en": "..."`。
  - 146 行的 `shot_overrides` 那句補上這三個 key。
  - 新增三條 bullet：五小節逐節合併、寫回優先位置；兩個 id 清單是 E40 豁免，offscreen 同時會從人數鎖扣掉；`style_anchor_en` 只作用於 Ref2VA。
- **`references/prompt-authoring.md:30`**：在「同樣寫在 Layer 2 `five_part_en`」後面補「或階段 5 `en_overlay.shots.<gsid>.five_part_en`（Layer 2 已核准不能改時）」。
- **不用動**：`SKILL.md`、`pipeline.md`（367 行只講 `h3_voice`）、`shot-intent.md`。`next_step.py:142` 的提示文字已經寫「Layer 2 five_part_en 或 bindings en_overlay」，PR③ 合併後就名實相符。

## 5. 驗證清單

```powershell
# 每個 PR 在自己的分支上
python -m unittest discover -s tests -q          # 必須全過
python -m unittest tests.test_stage5_en_layer tests.test_remix_backend tests.test_physical_camera tests.test_subject_coverage_gate -v
# PR③：確認編譯器背影句仍存在、且已在 boilerplate 清單
git grep -n "seen from behind matches" scripts/
```

需要親眼確認的地方：
- PR③ 測試印出的 `det_lines[0]` 含 `Cast rule: exactly two people, A and B;`，而且該行沒有被宣告 offscreen 的名字。
- 3 名以上人類的 REMIX golden（`test_physical_camera`）不變。
- PR② 的 REMIX 段卡片沒有 E1。

## 6. 落地順序、rebase 與回滾

1. **順序**：①、②、③ 依序開，前一個合併後下一個再 `git rebase origin/main`。三個 PR 都會在 CHANGELOG 同一位置衝突，解法都是兩行都留，放在 `## [未發布]` 和 `## [0.10.1]` 之間。
2. **兩處衝突都兩邊都留，同意。** `build_stage_review` 的參數順序是 `authored_shots=…, backend=…, submit_endpoint=…,`。
3. **搬 diff 的方式**：在 E: 跑 `git diff > wip.patch`，這邊用 `git apply -3 --include=<檔案> wip.patch` 按檔挑。E: 那份 clone 不要動，等三個 PR 都合併後再整個 reset 掉。
4. **回滾**：每個 PR 都能單獨 `git revert` 合併 commit。PR③ 回滾後，用了新 key 的 binding 會被白名單拒收，報錯訊息是明確的，不會默默產出錯的提示詞。

## 我沒查到、或要你決定的事
- E: 讀不到，所以 WIP hunk ② 的來源欄位沒親眼看過，第 2 節第 4 步要你在 E: 上確認。
- 其他測試檔還有沒有同樣的 cp950 問題，我沒有逐一 grep。
- **E40 編號撞號**（main 既有問題，不在這三個 PR 範圍）：`prompt_authoring.py` 的 E40 是「畫面實體未綁參考圖」，`references/prompt-authoring.md:55` 的 E40 卻是「抹背景」，agent 會讀到兩種意思。建議另開 PR 修。
