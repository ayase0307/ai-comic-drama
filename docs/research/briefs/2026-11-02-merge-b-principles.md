# 任務：把 B 的獨家內容合併進 A 的 SKILL.md

## 背景

`ai-comic-drama` 技能有兩份：
- **A（repo，權威）**：`C:\Users\kirit\projects\ai-comic-drama-repo`（v0.10.0，`COMPILER_RULES_VERSION = 2026-11-02`，SKILL.md 97 行，原則 1–8，含 3a/4a 的後期修訂與「劇本改寫不詢問」原則 8）
- **B（bot 複本）**：`C:\Users\kirit\AppData\Local\hermes\profiles\comic-drama\skills\ai-comic-drama`（v0.10.0，`COMPILER_RULES_VERSION = 2026-10-26`，SKILL.md 106 行，原則 1–12）

對帳結論：B 有 A 沒有的成果，要搬回 A。**已在分支 `feat/merge-bot-copy-unique-content` 上複製好三支檔案**：
- `references/audit-inherited-project.md`（15.7 KB）
- `references/remix-draft-loop.md`（10.8 KB）
- `scripts/audit_inherited_project.py`（10.3 KB）

## 你要做的事（只改 `SKILL.md`）

以 **A 的 SKILL.md 為主體**（A 的規則較新，例如 3a「生圖後端由使用者選」、4a「h3d inbox」、原則 8「劇本改寫不詢問」都要保留，不可以被 B 的舊措辭蓋掉），把 B 獨有的內容併進去：

1. **原則 9–12**（B 的第 24–29 行區塊，共四條）
2. **「接手既有專案先稽核再推進」那段**（B 第 36 行，指向 `references/audit-inherited-project.md`）
3. **參考檔案清單**：B 第 95–96 行那兩條條目（`audit-inherited-project.md`、`remix-draft-loop.md`）
4. **階段表**裡提到 `references/remix-draft-loop.md` 的地方（B 第 56 行，階段 6 那列）

## 硬性限制

- **繁中**，語氣與 A 現有原則一致（粗體開頭、條列、括號補細節）。
- **編號不能亂**：A 目前是 1、2、3、3a、4、4a、5、6、7、8；新內容編 9、10、11、12。若你判斷某條更適合當 8a，請說明理由。
- **不得與 A 較新的規則衝突**：特別是 3a／4a／原則 8。若 B 的 9–12 有哪一條被 A 的修訂取代，請標「不併入」並說明。
- 只動 `SKILL.md`，不要動其他檔案（三支 reference/script 已複製好）。
- 不要改 `CHANGELOG.md`、`VERSION`、`COMPILER_RULES_VERSION`（我自己處理）。

## 要交給我什麼

1. **完整的合併後 `SKILL.md` 全文**（可直接覆蓋，或給 unified diff）
2. **併入／不併入清單**：每條原則一句話說明處理方式
3. **風險清單**：合併後可能矛盾、重複、或讓 agent 誤解的地方
4. 若你認為第 2 項（接手既有專案那段）位置該調整，說明理由

---

## 更新（第二輪）

Opus 第一輪無法讀 repo 外的路徑。B 的 SKILL.md 已複製到 `docs/research/briefs/b-SKILL.md`（同一分支，PR 前會刪除）。請從那份檔案讀原則 9–12、第 36 行那段、第 56 行階段 6 那列、第 95–96 行參考條目。
