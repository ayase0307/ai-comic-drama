# Concat 與剪映／CapCut 草稿程式化產生：查證報告

查證時間：2026-10-24（Asia/Taipei）。星數、更新時間皆為當日 GitHub API 讀值（時間已換成台北時間）。
標記：**【已證實】** 有來源原文支持；**【推論】** 由來源推得、未直接寫明；**【查不到】** 找過但沒有證據。

---

## 1. Concat 是什麼

| 項目 | 結論 | 來源 |
|---|---|---|
| 是什麼 | 【已證實】免費、開源、本地優先、跨平台的影片剪輯器，自我定位「The truly free, open-source, local-first, cross-platform **CapCut replacement**」。Rust 引擎＋GPU 合成器，Slint 視窗；FFmpeg 靜態連結、whisper.cpp／sherpa-onnx 內建。目前 **beta**。 | https://github.com/jub0t/Concat ；https://github.com/jub0t/Concat/blob/main/ARCHITECTURE.md |
| 開發者 | 【已證實】GitHub 帳號 `jub0t`（顯示名 Jareer A.，blog standalones.org）。repo 建立於 2026-08-26。 | https://api.github.com/users/jub0t |
| 官網 | 【已證實】repo homepage 欄位為 https://concat.standalones.org ；README 內連結與開發者文件用 https://concatenate.pages.dev （兩者內容相同）。concat.fun、concatvideoeditor.com 是另外的鏡像／第三方指南（後者自稱 independent）。 | GitHub API repo `homepage`；README；https://concatvideoeditor.com/llms.txt |
| 開源／授權 | 【已證實】AGPL-3.0。11,255 星，最近 push 2026-10-24 17:47。最新版 v0.2.8（2026-10-20）。 | GitHub API |
| headless MCP | 【已證實】自 0.2.8 起每個桌面版都是 MCP server：`concat --mcp`；模式 `--mcp auto`（預設）／`--mcp window`／`--mcp headless`。headless＝不開視窗、自己跑引擎；專案資料夾以 `concat.lock` 互斥；只能寫家目錄，其他資料夾需設 `CONCAT_MCP_ROOTS`。Windows 安裝路徑 `%LOCALAPPDATA%\Programs\Concat\concat.exe`（與 adapter 的 `DEFAULT_EXE` 一致）。stdio、換行分隔 JSON-RPC 2.0。 | https://github.com/jub0t/Concat/blob/main/docs/MCP.md ；https://concat.standalones.org/docs/transports/mcp/ |
| 工具名 | 【已證實】`clips_add_sequence`、`captions_add`、`clip_add` 都存在（另有 project_create/open/save/close、media_import/probe、timeline_read、title_add、keyframe_set、effect_layer_add、edit_apply、template_instantiate、export_start/wait、preview_frame 等）。原始碼在 `src/crates/concat-mcp/src/tools.rs`。時間單位秒，keyframe 位置為片段 0–1 比例。 | docs/MCP.md；GitHub code search |
| 其他介面 | 【已證實】JSON-RPC（視窗 Settings › Automation 開啟時）；gRPC 與 `concat-cli` 只在自行從原始碼編譯時有。 | https://concatenate.pages.dev/docs/ |

### Concat 跟剪映的關係（使用者記憶「Concat 是逆向剪映的軟體」）

- 【已證實】**不是逆向剪映**。Concat 是自寫的 Rust 引擎，用自己的專案格式 `concat.json`（ARCHITECTURE.md：「One document format, one command set, one renderer」）。官方說法是「CapCut **替代品**」，對標的是 CapCut 的功能（自動字幕、TTS、去背、關鍵幀…），不是相容它的檔案。
- 【已證實】**目前正式版不讀寫剪映／CapCut 草稿**。讀 CapCut `draft_content.json` 轉成 `concat.json` 是社群提的功能：issue #477（2026-10-21 開，open，標 important）與 PR #508（2026-10-22 開，**未合併**，狀態 being-reviewed）。PR 自述是「單向、一次性」轉換，不會回寫 CapCut，轉場只能近似對應。
  - https://github.com/jub0t/Concat/issues/477
  - https://github.com/jub0t/Concat/pull/508
- 【已證實】GitHub code search 在 jub0t/Concat 搜 `draft_content`、`jianying` 皆 0 筆（索引可能稍落後，但與 PR 未合併一致）。
- 【推論】使用者的記憶很可能把兩件事混在一起：(a) Concat＝「CapCut 替代品」；(b) 同一時期很紅、真的直接讀寫剪映草稿的 `capcut-cli`（renezander030）。有一支 Instagram 短片標題就是「edit CapCut and JianYing projects from the terminal」，內文又提到 Concat，容易混淆（https://www.instagram.com/reel/DbqUcZtDZyt ）。
- 【已證實】repo 內 `concat_adapter.py` 與 `references/tooling.md §2.7` 只寫了 `concat.exe --mcp headless` 與工具名，**沒有任何 URL**，也沒提剪映；adapter 已處理 `CONCAT_MCP_ROOTS`（第 256、273 行）。

---

## 2. 剪映／CapCut 草稿能否用程式產生

### 2.1 加密與版本：最關鍵的事實

- 【已證實】剪映（國內版，`app_source=lv`）**6.0 起**草稿主檔加密；**5.9.x** 是最後廣泛使用的明文版。CapCut 國際版**不加密**。（capcut-cli 文件）https://github.com/renezander030/capcut-cli/blob/master/docs/jianying-encryption.md
- 【已證實】**加密擋的是「讀」既有草稿，不是「寫」新草稿**：剪映 11.4（macOS）會打開工具寫的**明文** `draft_info.json`，就地升級成加密格式並補上 `Timelines/` 與封面；剪映 9.0.0（Windows）也接受工具寫的明文主檔。常見的「草稿內容已損壞」來自寫成舊檔名 `draft_content.json`（新版只在「草稿包匯入」流程才會改名）。https://github.com/renezander030/capcut-cli/blob/master/docs/version-support.md ；pyJianYingDraft PR #198 https://github.com/GuanYixuan/pyJianYingDraft/issues/198
- 【已證實但有矛盾】pyJianYingDraft 上游 README 標「新版剪映 10.8 ✅」生成大多數功能，但 #177（10.3.0 Mac 打開提示內容已損壞）、#194（10.8 生成後無法二次修改）仍 open，修檔名的 PR #198 **未合併**。→ 上游在 Windows 10.8 可用、在 Mac 新版可能需要 #198 的修正，以實測為準。
- 【已證實】剪映 7 起 UI 控件隱藏，pyJianYingDraft 的「自動匯出」只支援剪映 6 以下；Linux／Mac 可產草稿，但**仍需 Windows 版剪映開啟並匯出**。
- 【已證實】CapCut 國際版 10.x 也有「工具寫的草稿被判損壞」的回報，capcut-cli 對 CapCut >9.x 預設拒寫。
- 【已證實】剪映會**自動更新**，把 5.9 釘版打破（pyJianYingDraft #115）；新版開啟舊草稿會就地遷移。

### 2.2 開源專案盤點

| 專案 | 星 | 最近 push | 授權 | 剪映版本 | 能做什麼 | 需要 Windows／剪映？ |
|---|---|---|---|---|---|---|
| **GuanYixuan/pyJianYingDraft** https://github.com/GuanYixuan/pyJianYingDraft | 4,662 | 2026-10-14（v0.3.1，PyPI） | Apache-2.0 | 5.9 全功能；README 標 10.8 多數 ✅；模板讀取在新版需 `fallback_loader`（即加密讀取要另接） | 影片／圖片軌、變速、關鍵幀、蒙版、色度摳圖、混合模式；音訊＋淡入淡出、音色；多軌；片段動畫、特效、濾鏡、獨立特效軌、**轉場**；文字樣式、描邊陰影、**氣泡／花字**、文字動畫、**SRT 匯入**；模板替換素材／文字 | 產生：任何 OS。開啟／匯出：Windows 剪映；自動匯出僅剪映 ≤6 |
| aoguai/pyJianYingDraft（fork） https://github.com/aoguai/pyJianYingDraft | 25 | 2026-10-14 | Apache-2.0 | 加「可逆 content_codec」讀寫**加密草稿**，驗證 10.3.0–10.6.5；移植自 jy-draftc | 上游功能＋加密草稿讀寫、草稿資料夾自動註冊、雲端曲庫、美顏、花字富文本 | 加密功能需 Windows 64 位 Python＋本機剪映 |
| GuanYixuan/pyCapCut https://github.com/GuanYixuan/pyCapCut | 720 | 2026-10-16 | **無授權欄位**（GitHub API license=null） | CapCut 國際版，部分功能驗證到 8.2.0／9.5.0 | 與 pyJianYingDraft 同源的 CapCut 版 | 需 Windows CapCut 手動匯出；無自動匯出 |
| **Hommy-master/capcut-mate** https://github.com/Hommy-master/capcut-mate | 2,017 | 2026-10-20 | Apache-2.0 | 【推論】內嵌一份 `src/pyJianYingDraft`，版本相容性跟著它走；README 未寫版本 | FastAPI REST：建草稿、加影片／圖片／音訊／貼紙／字幕（關鍵字高亮）／特效／關鍵幀／蒙版／美顏；`gen_video` 雲端渲染（走 jcaigc.cn 服務、需 apiKey）；Coze／n8n 插件、MCP（另 repo capcut-mate-mcp） | 產草稿不必；本機匯出用 Windows extras（pywin32、uiautomation） |
| **sun-guannan/VectCutAPI**（原 CapCutAPI，已轉址） https://github.com/sun-guannan/VectCutAPI | 2,327 | 2026-10-24 | Apache-2.0 | 剪映與 CapCut 皆可；repo 內有 `template_jianying_10_2` 模板 → 【推論】有對應剪映 10.2 | HTTP API＋MCP（stdio）：草稿、影片／音訊／圖片／文字／SRT／特效／貼紙／關鍵幀；雲端預覽與雲端渲染（商業服務 vectcut.com） | 需 Python 3.10+、FFmpeg、剪映或 CapCut 開啟草稿；repo 內嵌 `pyJianYingDraft` |
| renezander030/capcut-cli https://github.com/renezander030/capcut-cli | 949 | 2026-10-24 | MIT | CapCut 6.2.8 fixture 測過、8.7／9.x 回報可用；剪映 5.9 預期相容，≥6.0 預設**拒寫**（`--force-write` 可強制） | 讀寫既有草稿：字幕、時間、變速、音量、模板、長片切短片；`--jianying` 剪映轉場／蒙版枚舉；版本護欄、自動更新偵測 | Node CLI、零依賴；不需剪映即可改檔，但驗證要在 App 開 |
| wenshui330/jy-draftc https://github.com/wenshui330/jy-draftc | 161 | 2026-10-13 | NOASSERTION | 對應剪映 11.5／11.6（逐版發行） | 剪映 Windows 草稿**加解密**、結構版本升降級、**無頭匯出** | Windows amd64、需對應版本剪映 |
| HTWMedia/JyDraft（HDraft） https://github.com/HTWMedia/JyDraft | 89 | 2026-10-23 | Apache-2.0 | 自動解密加密草稿 | 批量**雲端渲染**草稿成片；附 C# 草稿生成庫 | 不需剪映；需 AuthKey（雲端服務，首月免費） |
| hey-jian-wei/jianying-mcp https://github.com/hey-jian-wei/jianying-mcp | 313 | 2025-08-22（停更一年多） | 無 | 未寫 | MCP：草稿、軌道、影片／音訊／文字、轉場、濾鏡、關鍵幀 | — |
| fancyboi999/capcut-mcp https://github.com/fancyboi999/capcut-mcp | 96 | 2025-08-21 | 無 | — | — | **已封存（archived）** |
| JianYing-Automation/JianYingApi https://github.com/JianYing-Automation/JianYingApi | 262 | 2024-05-08（停更） | MIT | 作者自述 App 更新太快、常跟不上 | 用 uiautomation 操作剪映 UI＋手寫草稿 JSON | Windows＋剪映 |
| ArcReel/ArcReel https://github.com/ArcReel/ArcReel | 5,702 | 2026-10-24 | AGPL-3.0 | 依賴 `pyjianyingdraft>=0.3.0`（pyproject） | 小說→分鏡→影片→**剪映草稿匯出**的整套工作台（我們 M23／I13 原本參考的來源） | — |

【查不到】各專案在**剪映 11.x Windows** 上大量實戰的系統性測試報告；只有零星 issue 與 capcut-cli 的回報表。

### 2.3 CapCut 國際版狀況
- 【已證實】草稿不加密，讀寫門檻比剪映低；pyCapCut、VectCutAPI、capcut-cli 都支援。
- 【已證實】新版（CapCut 8.7+／9.x）實際讀的是 `template-2.tmp`／`Timelines/<id>/draft_info.json`，只寫根目錄 `draft_content.json` 可能被忽略；10.x 有拒開工具草稿的回報。
- 【推論】CapCut 國際版在台灣可正常下載使用，對守富而言是「剪映加密」問題的備案；但素材庫（花字、特效 resource_id）與剪映是兩套命名空間，草稿不能互通。

---

## 3. 結論：ai-comic-drama 階段 7 加「輸出剪映草稿給人工精修」

**可行，建議做成第三條輸出（`h3d assemble` 成片／`h3d concat build`／新增 `h3d jianying draft`），只做一次性匯出、不做雙向同步。**

推薦：**pyJianYingDraft（上游，pip `pyJianYingDraft`，Apache-2.0）**。
- 理由：星數最多、持續維護（10 月有版本）、授權寬鬆；capcut-mate、VectCutAPI、ArcReel 本身都是包它，直接用源頭最少一層；純 Python、可在 Linux／Colab 產草稿，跟現有 `edit/full-plan.json`（segments／captions／voices 秒數）幾乎一一對應：T1 影片段、T2 文字（可直接帶花字／描邊）、T3 畫外音。
- 不推薦 capcut-mate／VectCutAPI 當主路線：多一層 HTTP 服務，雲端渲染綁商業服務；我們要的只是本機草稿。
- capcut-cli 適合當**檢查工具**（`capcut version`／`diagnose` 看草稿版本與加密狀態），不適合產新稿（剪映 ≥6.0 預設拒寫）。

風險與對策：
1. **版本漂移**（最大風險）：剪映自動更新後格式可能改；新版主檔名是 `draft_info.json`，上游 PR #198 未合併。→ 匯出後在家機剪映實測「能開、片段順序正確、字幕在」作為驗收（與 I13 原驗收一致）；記下測過的剪映版本；必要時自己補檔名相容（寫 `draft_info.json`）。
2. **草稿只能寫、不能回讀**：剪映開過一次就把檔案加密，之後程式改不了（#194）。→ 只做一次性輸出；要重產就新建一份草稿，不改舊的。
3. **匯出成片仍要人點**：剪映 7+ 無法自動匯出。→ 定位就是「給人精修」，成片仍由 ffmpeg／Concat 路線產；需要無頭匯出才考慮 jy-draftc（版本綁死、授權 NOASSERTION）。
4. **素材路徑**：草稿記絕對路徑，Colab／沙箱產的稿到 Windows 家機要重寫路徑。→ 在家機產、或匯出時用 `--media-root` 換成家機路徑。
5. **特效／花字 resource_id 需線上下載**，剪映開稿可能「xx 載入失敗」，字型未快取要開兩次。→ 預設只用基本字幕樣式。
6. **加密讀取 fork（aoguai、jy-draftc）**屬逆向解密，有法律與維護風險（capcut-cli 明確不做）。→ 不採用。

與 Concat 的分工（推論）：Concat 是開源、可 headless 自動化的「機器剪」路線；剪映草稿是「人精修」路線。兩者互不相容（Concat 目前不讀寫剪映草稿），所以 `full-plan.json` 應作為共同中介，兩個 adapter 各自轉出。
