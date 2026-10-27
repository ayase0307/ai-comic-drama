# 更新紀錄（CHANGELOG）

格式參考 [Keep a Changelog](https://keepachangelog.com/zh-TW/1.1.0/)，版號遵循 [語意化版本 SemVer](https://semver.org/lang/zh-TW/)。
升版規則與發版步驟見 [docs/RELEASING.md](docs/RELEASING.md)。

每個 PR 都要在「未發布」區塊加一行；發版時把「未發布」改成新版號。
`h3d next` 會讀這份檔案：專案版本章比目前技能舊時，列出中間各版標題提醒重驗。

## [未發布]

## [0.9.0] - 2026-10-27

第一個正式版本。之前 107 個合併 PR（#1–#105）沒有版號，視為 0.9.0 之前的開發期；
用舊版建立的製作專案沒有版本章，`h3d next` 會提示用 `h3d version --root . --accept` 補蓋。

### 新增
- 版本管理：`VERSION` 為唯一版號來源；`h3d --version`、`h3d version`（`--root` 比對、`--accept` 更新版本章）。
- 製作專案版本章：`init_project.py` 建案時把技能版本與資料格式版本寫進 `review/project-state.json` 的 `skill_version`；`h3d next` 比對並提示規則變更或資料格式遷移。
- 資料格式版本集中表 `scripts/skill_version.py:SCHEMA_VERSIONS`（project_state 2、decisions 1、deps 2、failure_catalog 2）。
- 自動發版：合併到 main 且 `VERSION` 沒有對應 tag 時，CI 自動打 `vX.Y.Z` tag 並以 CHANGELOG 該版內容建立 GitHub Release；PR 標題檢查 Conventional Commits 前綴。
- REMIX 角色卡後端（#96、#97、#105）：`video_backend: remix`、remix 能力表與綁定、`h3d refcheck`（E50／E51）、`h3d staging`（D06–D14，`staging_gate=strict` 升 D06–D08）、REMIX 三欄提示詞輸出。
- 外部技能蒸餾 A 批（#95）：人物連戲帳、玄幻武戲合同、特效設計卡、改稿復驗流程文件。
- Foyege 寫法審查 W41–W45（#98）。

### 變更
- 接線體檢（#104）：H3 運鏡手冊同步；階段 5 審核頁對 ref2va 段補跑 refcheck／staging（只提示）；創作 lens 未跑時在審核頁列出可執行指令。
- README 重新設計（#103）。

### 修正
- 階段 0–3、4–5、6–7 全面體檢修正（#99、#100、#101）：中文與空白路徑、BOM／CRLF、`--bible`、SVG 依比例、裁切 950×910＋face_crop_box、stage-5 strict 新檢查、環境變數覆寫 ffmpeg／ffprobe／服務位址。
- Windows CI：測試改用平台路徑比對（#102）。
