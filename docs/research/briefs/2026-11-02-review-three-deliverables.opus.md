# 審查結論：PR③ 要改一處 bug、補一處 REMIX 缺口、補兩支測試，其餘照現況可以合

我沒有改任何檔，也沒有重跑測試（你那邊是 1487 支全過）。

## 1. 交付一：逐項判定

| # | 判定 | 說明 |
|---|---|---|
| 1 | **通過** | 容器不存在就回 None，由寫入端決定放 `action_and_performance`。這樣做對：讀取路徑不會改到 Layer 2。邊角情況是 `shot.five_part_en = {}` 而 action 裡沒有值，這時會寫進 action，下一次讀也讀 action，前後一致。 |
| 2 | **通過** | 原本的錯誤訊息留住了，非 dict 的值會在 `_five_part_merge` 擋下。 |
| 3 | **通過（可簡化）** | 讀取端 `_clean()`（`compile_layer2_to_h3.py:235`）本來就會對值做 `str()`，所以合併時先轉字串，不會比原本多出新的靜默轉換。不過 `references/audit-inherited-project.md:123` 記錄過有專案的 five_part 值是 `{en, text}` 物件，兩條路徑都會把它編成 `"{'en': …}"`，這是既有問題，不是這次造成的。可以把合併改成 `container["five_part_en"] = {**current, **overlay}`，轉換只留在讀取端一處。 |
| 4 | **通過** | 缺節時 `_five_part_en` 會報錯並帶出 shot_id，不必在 overlay 階段再驗一次是否齊全。 |
| 5 | **通過，就是這個意思** | 人數鎖算的是全段，只要角色在任何一鏡出現就要算進去。所以 A 鏡宣告 offscreen、B 鏡沒宣告，照樣計數才對。 |
| 6 | **通過** | |
| 7 | **要改（bug）** | 見下面 A 點。 |

### A. `style_anchor_en`
- **核准 hash 不受影響。** `validate_stage5_binding` 是對 Layer 2 檔案的 bytes 算 sha256（`:684`），在記憶體裡改不會碰到。階段 4 的各個顯示畫面（board_advisor、layer2_to_table）讀的都是檔案，本來就該顯示核准原值。`continuity_anchors_en` 和 `lighting_lock_line_en` 早就用同樣方式寫進 `style_lock`，所以寫入位置照現況即可。
- **bug：** `:1767-1769` 的 note 和 `:871` 的註解寫錯了欄位。
  - REMIX 的風格錨（E55，提示詞開頭那一句）讀的是 `metadata.style_anchor_en`（`remix_style_anchor`，`:1607`）。
  - `style_lock_tail_en`（`:3014`）是結尾的 Style lock 句，是另一件事。
  - 即使改成指向正確欄位，那條路也走不通：Layer 2 核准後不能改，而 `metadata_override` 的白名單（`:766`）不收這個 key。
- **建議修法：** 在 `_apply_en_segment` 多寫一行 `data.setdefault("metadata", {})["style_anchor_en"] = anchor`，然後刪掉 note 和註解。
  - 這樣 REMIX 也會生效；`remix_style_anchor` 本身已經會擋中文（`:1622`），E55 比對的是 `:3129` 寫進產物的同一個值。
  - 要同步修正 `references/tooling.md:152`、`references/prompt-authoring.md:32` 和 CHANGELOG 那一行的說法。

### B. E40 豁免夠不夠
- **Ref2VA：夠。** 編譯產物的 `shots` 就是套過 binding 的 Layer 2 shots（`:1686` → `:1740` → `:3120`），所以 key 會一路帶到 `audit_subject_coverage`。
- **REMIX：有缺口，要改。**
  - REMIX 產物會用 binding 的 `visual_subject_ids` 蓋掉（`:3136-3140`）。下游三處都優先讀這個欄位，沒有扣掉 offscreen：
    - E50 具名角色沒有包：`audit_refs_and_segments.py:313`，接著 `:355` 報錯
    - 站位檢查 `_onscreen_count`：`staging_lint.py:224`
    - D08 多人鏡缺左到右站位句：`staging_lint.py:323`
  - 結果是人數鎖說「兩人」，E50 卻還要 Ben 的包，D08 也還要求寫三人站位句。
  - **修法（只動一處）：** 在 `:3140` 複製 `visual_subject_ids` 時，扣掉該鏡的 `offscreen_subject_ids`。三個下游會一起修好，不用分別去改 lint。
  - `accepted_unbound_subject_ids` 不要扣，因為人還在畫面裡。E50 對 REMIX 照樣要求附使用者原話，這道把關不受影響。
- **validate_storyboard：** 是階段 4 的檢查，跑在 Layer 2 原檔上，跟 overlay 無關，不用改。
- **未查證的風險：** 如果角色在 Ref2VA 每一鏡都是 offscreen，但仍掛著參考圖和 `<Subject N>`，H3 可能還是會把他畫出來。這次先在文件註明即可。

## 2. 必補的測試

1. **REMIX 帶 `style_anchor_en`。** `tests/test_remix_compile.py` 已經有現成的 REMIX fixture（`:121`、`:275`），不必另外建整套包。照 A 點修完後，斷言提示詞開頭就是這句錨。
2. **端到端走 binding。** 目前 `test_offscreen_override_exempts_subject_coverage_e40` 是直接對編譯產物呼叫 `_apply_en_shot`，`test_cast_lock_drops_offscreen_actor` 是把 key 直接寫在 Layer 2 上，都繞過了 `apply_stage5_binding`。應該補一支從 `stage5_binding.en_overlay.shots.<gsid>` 一路編譯下去的測試，同時驗 E40 和人數鎖。如果 B 點的 REMIX 修法有做，再加一個 REMIX 案例，驗 E50 不報 offscreen 的角色。

## 3. 交付二：要進 main

測試的 docstring（`test_stage5_en_layer.py`，`EnOverlayOverrideTests`）把 `docs/research/briefs/2026-11-02-wip-landing-plan.opus.md` 標為規格來源，這份檔不在 main 上，引用就會失效；PR #127 也有同樣的前例。建議開一個 `docs:` PR，順便決定兩份還沒進版控的 review brief 要不要一起帶進去。

## 4. 交付三：拿來查「誰依賴誰」夠用，不用再花錢補跑

「誰依賴誰」靠的是 5,603 個 AST 節點。缺節點的那兩份 md 和被縮減的 `04-external-views.md` 都是文件，不影響程式的依賴邊。這個 repo 另外已經有 tokensave 的程式圖可以交叉比對。

用這三個查詢驗收，都答對就算合格：
1. **誰讀或寫 `five_part_en`？** 必須同時找到 `_five_part_slot`、`_five_part_en`、`_five_part_merge`，以及 `codex_storyboard_panels`、`prompt_authoring` 裡各自讀單一位置的路徑。
2. **`audit_subject_coverage` 的上游呼叫鏈？** 必須出現 `audit_segments`（`prompt_authoring.py:648`），再往上到 compile `--check` 或階段 5 審核。
3. **`lint_h3_prompt` 的 backend 從哪來？** 必須連到 `build_stage_5` → `resolve_backend`（`audit_refs_and_segments.py`）。

加分題：問「E40 在哪定義」時，如果能同時找出程式裡「實體未綁參考」和文件裡「抹背景」兩種意思，代表 semantic 層有在運作。

## 5. bug 位置

- **確定是 bug：** `scripts/storyboard/compile_layer2_to_h3.py:1767-1769`（REMIX note 指錯欄位）和 `:871`（註解同樣寫錯）。
- **REMIX 缺口：** `scripts/storyboard/compile_layer2_to_h3.py:3136-3140`（`visual_subject_ids` 沒扣 offscreen），影響 `audit_refs_and_segments.py:313` 和 `staging_lint.py:224`、`:323`。

我沒有跑過 graphify 的查詢，也沒驗證 offscreen 角色在 Ref2VA 仍帶 `<Subject N>` 時 H3 實際會怎麼畫。
