# 版本與發版規則

## 版號（SemVer：主.次.修）

唯一來源是 repo 根目錄的 `VERSION`。`SKILL.md` 標頭的 `version` 必須與它一致（測試會對帳）。

目前在 **0.x 開發期**，規則還在快速演進：

| 改動 | 升哪一碼 | 例 |
|---|---|---|
| 門禁變嚴（新的 error、原本警告升成擋）、`h3d` 子命令或旗標移除／改名、資料格式不相容（`SCHEMA_VERSIONS` 有數字變動） | 次版 | 0.9.3 → 0.10.0 |
| 新功能但不影響既有專案（新警告、新子命令、新文件）、bug 修正、文件 | 修訂版 | 0.9.0 → 0.9.1 |

穩定到願意承諾相容後才發 1.0.0；之後不相容改動升主版。

## 資料格式版本

`scripts/skill_version.py` 的 `SCHEMA_VERSIONS` 集中列出各 JSON 產物的 `schema_version`。
改格式時：同步改對應模組常數與這張表 → `references/schemas/` → CHANGELOG 寫「遷移」小節（舊專案要跑什麼）→ 升次版。

## 製作專案版本章

- `init_project.py` 建案時寫入 `review/project-state.json` 的 `skill_version`（技能版本＋資料格式版本）。
- `h3d next` 每次比對：技能較新 → 列出 CHANGELOG 中間各版，建議重跑本階段 audit／審查；資料格式不同 → 提示遷移；專案比技能新 → 要求先 `git pull`。
- 看過變更後：`h3d version --root . --accept` 更新版本章。

## PR 規範

- 標題用 Conventional Commits 前綴，內容照寫繁體中文：
  `feat:` 新功能、`fix:` 修正、`docs:` 文件、`refactor:`、`test:`、`ci:`、`chore:`；不相容改動加 `!`（例 `feat!: 階段 5 新增 E52 擋件`）。可加範圍：`fix(stage5): …`。
- 每個 PR 在 `CHANGELOG.md` 的「未發布」加一行（新增／變更／修正／移除）。

## 發版（自動）

1. 開一個 `chore: 發版 vX.Y.Z` PR：改 `VERSION`、`SKILL.md` 的 `version`，把 CHANGELOG「未發布」內容移到 `## [X.Y.Z] - 日期`。
2. CI 全綠後合併。
3. `.github/workflows/release.yml` 偵測到 `VERSION` 沒有對應 tag，自動打 `vX.Y.Z` 並用 CHANGELOG 該版內容建立 GitHub Release。

退回某版：`git checkout vX.Y.Z`；製作專案可在 Release 頁下載該版 zip。
