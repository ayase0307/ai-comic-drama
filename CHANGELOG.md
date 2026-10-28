# 更新紀錄（CHANGELOG）

格式參考 [Keep a Changelog](https://keepachangelog.com/zh-TW/1.1.0/)，版號遵循 [語意化版本 SemVer](https://semver.org/lang/zh-TW/)。
升版規則與發版步驟見 [docs/RELEASING.md](docs/RELEASING.md)。

每個 PR 都要在「未發布」區塊加一行；發版時把「未發布」改成新版號。
`h3d next` 會讀這份檔案：專案版本章比目前技能舊時，列出中間各版標題提醒重驗。

## [未發布]

### 新增
- 抖音蒸餾 A 批（2026-10，外部，未經 H3 實測）：同場配樂不跟生成段走（剪輯手冊 §8.1）、三人以上按當下那一對畫軸線（continuity-ledger §4／§5）、音色母帶挑平穩句且固定聲音描述只寫身份（consistency §6）、場景多角度分步生成（consistency §4）、動作中段反覆失敗改用省略（revision-and-retry §2）。
- 空間一致性規則（老易空間實驗 2026-10，第二批 86 支實測、方向性證據、未達原定 +25 門檻）：場景母片照平面圖畫且含所有座位、牆面分配層、構圖板以母片為底重畫、只拍生物的鏡頭綁店內參考（`references/storyboard/spatial-consistency.md`）；可選工具 `scripts/storyboard/wall_map.py`（不改預設編譯）；實驗數據 `docs/experiments/laoyi-spatial-2026-10/`。
- 連戲警告 C4「同場配樂跟著生成段走」：同一場相鄰段的 `non_diegetic_music` 不同或非 N/A 就警告，不擋（`continuity_lint.lint_scene_music`，`compile --check` 會印）。
- 收件匣八階段閱讀視圖（`scripts/review/stage_views.py`）：每關固定六區塊（問題、待決、摘要、文件、問題與處理、紀錄），文字產物可頁內展開全文，狀態分開顯示「尚未產出／製作中／等你核准／已核准／內容已變更待重審／局部重審」。
- 收件匣階段 5 段級重審卡（`D5-rereview`）。
- 階段文件標準格式（`references/document-standard.md`）：每份給人讀的文件最上面一張狀態卡（狀態｜版本｜更新、一句話、先看、要你決定、本次改動），最後修訂紀錄；外框用 `>` 行，不影響劇本解析與門禁。
- `h3d doc`（`scripts/doc_card.py`）：`stamp`／`resolve`／`check`／`show` 寫狀態卡與修訂紀錄；`init_project.py` 建案的模板、`layer2_to_table.py` 與 `compile_layer2_to_h3.py` 產出的 Markdown 自動帶狀態卡（重產時本體有變才升版，已核准的改成「已變更待重審」）。
- 狀態卡的「要你決定」每條自動變成收件匣卡（`blocking=2`，選項＝建議／或／先放著）。
- 收件匣閱讀視圖排版（`scripts/review/doc_render.py`）：狀態卡排成卡片、Markdown 排成閱讀頁（標題、表格、條列、引言）、劇本用劇本版型（場次列、△動作、角色｜台詞）、CSV 排成表格；手機寬度不溢出。
- 決策收件匣改版成「簽核牌組」（`scripts/review/inbox_page.py`）：一次一張決策卡、點選項＝簽下（蓋章＋卡片游走）、進度點可回頭改答、結尾頁「複製全部回覆」成功才放鯨魚娘慶祝動畫，底部常駐已簽數與複製鈕；視覺沿用鯨工坊海洋主題（亮／暗）與鯨魚娘吉祥物；閱讀視圖的寫死深色改用色彩變數。

### 修正
- 收件匣合併卡保留每張子卡（頁內逐件展開問題與選項），待決數改計原始件數。

### 變更
- `consistency.md` §7.1 改寫：「一段一張角色參考圖／一段一張臉」已撤銷（D3），新流程用 remix 角色卡維持人物一致；如實記 ref2va 程式預設（單人裁切、`--max-char-refs` 1、混臉只警告）與 remix 送件 adapter 尚未完成。skill-guide、pipeline、minimax-h3、anime-drama-grid、README 同步。

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
