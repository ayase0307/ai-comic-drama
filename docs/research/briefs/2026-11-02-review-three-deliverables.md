# Brief：三件交付的審查（驗收，不要重寫）

- 日期：2026-11-02
- repo：`C:\Users\kirit\projects\ai-comic-drama-repo`
- 你要做的：**審查，不要改檔**。指出錯誤、風險與該補的東西，逐項給「通過／要改（怎麼改）」。
- 前情：這是 `docs/research/briefs/2026-11-02-wip-landing-plan.opus.md`（你上一輪的計畫）的實作驗收。PR①② 已合併進 main（#129、#130）。

## 交付一：PR③ `en_overlay` 覆寫（主要審查對象）

分支 `feat/en-overlay-five-part-visibility`，commit `f2f3041`，5 檔 +168/-5。請直接讀檔：

- `scripts/storyboard/compile_layer2_to_h3.py`（+76）：新增 `_five_part_slot`／`_five_part_merge`／`_apply_five_part_override`／`_apply_visibility_override`；`SHOT_OVERRIDE_KEYS` 加 3 key；`VISIBILITY_OVERRIDE_KEYS`；`_apply_en_segment` 加 `style_anchor_en`；`compile_segment_h3` 的 REMIX note；人數鎖加 offscreen 過濾
- `tests/test_stage5_en_layer.py`（+84）：`EnOverlayOverrideTests` 7 支
- `references/tooling.md` §2.3、`references/prompt-authoring.md`、`CHANGELOG.md`

### 跟你規格的差異（請確認我沒做錯）

1. **helper 拆成兩個**：`_five_part_slot(shot) -> (容器 or None, 現值)` ＋ `_five_part_merge(shot, overlay)`。`_five_part_en` 改成呼叫 `_five_part_slot`。你的規格是 `(容器 dict, 原值)` 一個；我讓「容器不存在時回 None」，由寫入端決定放 `action_and_performance`，避免讀取路徑 `setdefault` 弄髒 Layer 2。**這樣對嗎？**
2. **`_five_part_slot` 用 `if raw:` 判斷**：空 dict／空字串會視為「沒有」，落到 `action_and_performance`；非 dict 但 truthy 的值（例如字串）會原樣回傳，讓 `_five_part_en` 照舊拋「必須是物件」。這保留了原本的錯誤訊息。
3. **`_five_part_merge` 把現值全部 `str()`**：`{str(k): str(v) for k, v in current.items() if v is not None}`。若 Layer 2 的五小節有非字串值（不該有，但沒驗），會被靜靜轉成字串。要改成保留原值嗎？
4. **驗證時機**：overlay 只驗「key 在五節內、值非空字串」，**沒有**驗「合併後五節齊全」——缺節仍由 `_five_part_en` 在編譯時報錯。可接受還是應該在 overlay 階段就驗齊？
5. **人數鎖過濾**：`[c for _s in shots for c in (_s.get("character_ids") or []) if c not in (_s.get("offscreen_subject_ids") or [])]`——逐鏡宣告才排除；同一角色在 A 鏡宣告 offscreen、B 鏡沒宣告，仍會算進人數。**這是你說「改 2507 行」的意思嗎？**
6. **WIP hunk② 已刪**：不再從 `binding["shots"][]` 複製 id 清單（你判斷那是第三入口）。實際確認過 main 沒有任何程式寫那裡。
7. **新增的 REMIX note**：寫在 `notes` 初始化後（`if remix and stage5_binding and (stage5_en_overlay(stage5_binding) or {}).get("style_anchor_en")`）。

### 我特別擔心的兩點（請直接判）

- **A. `style_anchor_en` 覆寫 `style_lock.anchor`**：`style_lock` 是階段 4 核准快照的一部分。階段 5 在記憶體改它，會不會讓「Layer 2 與核准快照一致」的檢查或顯示對不上（階段 4 核准 hash 只在 Layer 2 檔案層級？）？如果會，應該改寫到別的欄位，還是照現況？
- **B. E40 豁免的來源**：我**沒有**改 `prompt_authoring.audit_subject_coverage`，因為它已經有 `_WAIVER_KEYS = ("offscreen_subject_ids", "accepted_unbound_subject_ids")` 給 `shot_entities()` 用。所以功能靠「編譯器把 key 寫進 shot」＋「既有豁免」接起來。這樣是否足夠？有沒有遺漏的檢查點（例如 `staging_lint`、`refcheck`、`validate_storyboard`）也該認這兩個 key？

### 測試（7 支，請看是否真的擋得住）

`test_overlay_replaces_only_the_named_part`、`test_single_container_when_shot_already_has_five_part`、`test_overlay_rejects_unknown_part_and_bad_values`、`test_visibility_override_lists_are_string_arrays`、`test_offscreen_override_exempts_subject_coverage_e40`、`test_cast_lock_drops_offscreen_actor`、`test_style_anchor_en_overrides_segment_anchor`。

缺哪個一定要補的？（我自己覺得少一支：REMIX 段帶 `style_anchor_en` 時真的會多一條 note——沒寫，因為 fixture 編 REMIX 要整套包。）
全套：`Ran 1487 tests in 130.631s / OK (skipped=4)`。

## 交付二：規劃 brief 要不要進 main

本地分支 `chore/wip-landing-plan`，commit `15b9051`，只含 `docs/research/briefs/2026-11-02-wip-landing-plan.md` 與 `.opus.md`（2 檔）。repo 有前例（PR #127 把 `2026-11-02-merge-b-principles.md`／`.opus.md` 帶進 main）。

問題：這種「一次性規劃紀錄」該進 main 還是留在本機？（影響我要不要開 `docs:` PR。）

## 交付三：graphify 索引（品質判定）

- `graphify-out/`（已進 `.gitignore`，不進 repo）：**7,888 nodes / 16,497 edges / 509 communities**，AST 5,603＋semantic。
- 花費：$1.3505（deepseek 預設模型，第一次不完整）＋ $0.0376（deepseek-chat 補跑）＝ 記錄到的 $1.3881。
- 已知缺陷：`speed-ramp.md` 等 2 檔無節點；`references/craft/murch-cut/.../04-external-views.md` 從 12 節點縮到 4（用了 `--allow-partial` 才寫入）。
- `GRAPH_REPORT.md` 正在跑 `cluster-only` 產生。

問題：這種覆蓋率對「用圖查架構／找誰依賴誰」夠不夠？有沒有建議的查詢驗收（幾個必答對的問題）？

## 輸出格式

1. 交付一：逐項「通過／要改」，A、B 兩點給明確結論
2. 必補的測試（若有）
3. 交付二：進 main／不進，一句話理由
4. 交付三：夠用／要補，以及 3 個用來驗收圖品質的查詢
5. 若你認為有 bug，指出檔案與行號

**不要改任何檔案。**
