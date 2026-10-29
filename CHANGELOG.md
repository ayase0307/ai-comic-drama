# 更新紀錄（CHANGELOG）

格式參考 [Keep a Changelog](https://keepachangelog.com/zh-TW/1.1.0/)，版號遵循 [語意化版本 SemVer](https://semver.org/lang/zh-TW/)。
升版規則與發版步驟見 [docs/RELEASING.md](docs/RELEASING.md)。

每個 PR 都要在「未發布」區塊加一行；發版時把「未發布」改成新版號。
`h3d next` 會讀這份檔案：專案版本章比目前技能舊時，列出中間各版標題提醒重驗。

## [未發布]

### 新增
- 鏡間銜接與佔位延續（文件、分鏡欄位、D15–D21 警告）：新增單一入口 `references/storyboard/shot-transitions.md`（接點分類段內切／段縫 CUT／CONT、段內切規則、CUT 三選一閘門、CONT 交接塊、逐鏡站位與背景錨點、剪輯剪點、E1–E3 待 H3 驗證；每條標外部證據等級 A–D 與來源）；Layer 2 選填欄位 `seam_in`（cut／cont）、`entry_state`／`entry_state_en`／`exit_state`、`shots[].cut_in {type, motivation}`、逐鏡 `shots[].positions`（`order_lr`、`facing`、`background_anchor`、`world`、`screen_x`、`move`）、`camera_optics.azimuth_deg`；`handoff_to_skeleton.py` 產空欄、`layer2_to_table.py` 有值才多一欄「接點／站位」與段縫列；`compile` 只在 `seam_in=cont` 時把英文 `entry_state` 寫成第 1 鏡開頭交接塊（ref2va／remix 都支援，取代該段的前段終態句；中文或「同上」類指代只留 compile note）；新 lint `scripts/storyboard/transition_lint.py` D15 CUT 段縫差異不足、D16 同主體相鄰鏡差異不足、D17 連 3 鏡同景別、D18 CONT 段縫不符、D19 台詞跨切點沒有 `<scenetrans>`、D20 相鄰鏡站位對調或漂移沒寫走位、D21 多人鏡缺背景錨點，併入 `h3d staging` 與 `compile --check`，全部警告（strict 不升級）、可用 `staging_waivers` 豁免；欄位缺時不跑，舊專案零新警告。
- 鏡間銜接第二輪（T1 回溯驗證後；PR #115 同分支）：新 lint **D22 重演／狀態倒退**（同場相鄰段與段內相鄰鏡：事件帳選填欄位 `beats_done`／`beats_new`／`shots[].beats_new` 的 beat ID 重複、上段已完成的一次性事件本段首鏡又演一次、入口退回事件之前、回原點；中英關鍵詞，「已／仍／still／already」寫成靜止狀態不報）、**D23 朝向和站位矛盾**（「朝畫左看 X」而 X 在畫右；角度差 <90° 時朝向對調沒寫轉身）、**D24 反打沒換邊**（方位角差 >90° 共同角色左右沒換、沒寫走位）；新欄位 `narrative_scene_id`（敘事場景，同場判斷優先）、`lead_in_s`（拋棄式前導，選用、預設關：compile 在第 1 鏡寫前導靜止句，`h3d assemble` 自動剪掉片頭並前移台詞／字幕）、`positions[].toward`；新子命令 **`h3d seamcheck`**（`scripts/storyboard/seam_check.py`）：每個段縫／段內切點一張首末幀對照圖＋`videos/qa/seamcheck/seamcheck.json` 檢查清單（人數、左右、錨點、是否重演、是否照分鏡景別，預設 null，給人或視覺模型判讀；不自動判定、不呼叫模型 API、不改門禁）。

### 修正
- `transition_lint`：D15「人→空鏡」（一側 `character_ids` 空）算主體不同；景別解析支援英文自由文字（extreme close-up／close-up／medium close-up／medium／medium-wide／wide／extreme wide，含 shot、連字號、大小寫、OTS 變體）與中文（大特寫…大遠景），D15–D18 不再因 "medium shot" 這類寫法靜默；同場判斷依序看 `narrative_scene_id` → `source_scene_id` → `scene_id`（一段一個場景包時段縫規則不再整個跳過；`h3d staging`、`compile --check` 都改，D10 不變）；走位詞表補中文（經過、向東西南北、繞、退、跨、走到、移到、穿過…）與英文（passes、backs away、retreats…）；D16 遇插入鏡（前後任一鏡）與 `match_action` 跳過。

### 變更
- 鏡間銜接降級：D20 畫面位置 ≤15% 子規則只在 `cut_in=match_action` 且景別差 ≤1 級時查（硬切不查），左右對調在方位角差 >90° 的反打不報；**D21 改成建議**（level＝suggestion，💡，不算警告數）；D16 過肩豁免收緊（OTS↔非 OTS 只在兩鏡都沒填角度時算換角度）。`shot-transitions.md` 補 azimuth 0°＝本場主機位的定義與例子、畫外發話者不放 `character_ids`、第 1 鏡 `cut_in` 不用寫、§4.4 拋棄式前導、§4.5 事件帳寫法（已發生寫成靜止狀態）、§6.1 seamcheck 用法、E4；`tooling.md`（staging 表加 D22–D24、§2.8.2 seamcheck）、`pipeline.md`、`skill-guide.md`、`SKILL.md`、schema、`docs/skill-roadmap.html` 同步。舊專案（沒有新欄位）仍零新警告。
- `continuity-ledger.md` §6、`anime-drama-grid-and-continuity.md` 三.2、`consistency.md` 收尾交接格、`spatial-consistency.md`、`edit/manju-editing-playbook.md` §2 改成短摘要並指向 `shot-transitions.md`；`SKILL.md`、`skill-guide.md`、`pipeline.md` 階段 4（新 4.1b）、`tooling.md`（staging 檢查表加 D15–D21 與證據等級）加入口。「每段獨立、不用尾幀」定案不變，外部尾幀實測衝突並列待 E1。`references/h3/` 上游同步檔未動。

## [0.10.0] - 2026-10-28

移除免生圖 SVG 構圖（破壞性）；生圖後端改由使用者選擇；新增構圖板自動建議 W46。

### 新增
- 構圖板自動建議 W46（只建議）：`h3d staging` 判斷室內固定場景＋已驗收母片＋≥2 角色固定座位＋近景＋文戲的段，建議改用「以場景母片為底重畫的四格構圖板」（武戲、單人、戶外與判不了的不建議）；`--layer2` 可在階段 4 跑，階段 4／5 審核頁列「💡 自動建議」；不擋送件、不改預設編譯（`scripts/storyboard/board_advisor.py`，證據為方向性，見 `spatial-consistency.md` §3.1）。
- 生圖工具自動偵測、由使用者選擇後端（`h3d imagegen`，`scripts/image_backends.py`）：`--detect` 偵測 Codex CLI（PATH＋CODEX_HOME 登入）、Qwen-Image（經本機 FreeVideo，短 timeout 狀態探測）、Grok（Agent 宣告）、手繪上傳（ComfyUI 只回報），不生圖、不花錢、不讀 token 值；`--set <後端> --quote` 寫進 `decisions.json` 的 `design_engine`（階段 2）／新定案 `storyboard_engine`（階段 4）。`h3d next`／`h3d inbox` 在缺設定圖、缺構圖時：沒選→列出可用與不可用（含原因）請使用者選（只有一個可用也要問），已選→給該後端指令，選了但不可用→警告並重問；`check_environment.py` 生圖能力列改用同一偵測；收件匣卡支援灰掉的選項（`unavailable_options`）與不標建議（`no_recommendation`）。

### 變更
- 不再寫死預設生圖工具：`h3d next` 缺構圖時不再直接給 Codex 分鏡指令，改由使用者選的 `storyboard_engine` 決定；`h3d sketch` 殼改指 `h3d imagegen --detect`；`qwen_storyboard_grid.py` 改讀 `FREEVIDEO_API_URL`（預設仍是 127.0.0.1:8189）。
- 階段 4 預設構圖來源改為 Codex 分鏡（`scripts/storyboard/codex_storyboard_panels.py`）：`h3d next` 缺構圖時建議 `codex_storyboard_panels.py --root . [--episode EPxx] --model <使用者指定模型>`（`--model` 必填）；skill-guide、tooling、pipeline、SKILL.md、README、`docs/cli-walkthrough.md`、`docs/skill-roadmap.html` 同步。
- `codex_storyboard_panels.py` 註解改寫為自己的輸出契約；總覽圖字型環境變數新增 `STORYBOARD_FONT`，舊名 `SVG_GRID_FONT` 仍相容。
- 「白模分工與精度三檔」（Foyege，H3 未實測）搬到 `references/storyboard/spatial-consistency.md` §6；`continuity-ledger.md` 世界層改指 `spatial-consistency.md` §2 牆面分配表＋REMIX `positions`。

### 移除
- **破壞性**：免生圖 SVG 構圖 `h3d sketch` 整套移除：`scripts/storyboard/svg_storyboard_grid.py`、`svg_rig_actions.json`、`references/storyboard/svg-rig-grid.md`、`examples/svg-grid-minimal/`、`assets/svg-grid/`、`tests/test_svg_storyboard_grid.py` 與 `test_audit_stage4_5.py` 的 SvgAspectTests。`h3d sketch` 只保留一個殼：印「SVG 構圖已移除，改用 Codex 分鏡：<指令>」後 exit 2。
- `check_environment.py` 的「免生圖 SVG 構圖分鏡總覽圖（選用）」能力列與 `resvg-py` 依賴；CI 安裝清單拿掉 `resvg-py`。
- 不受影響：Layer 2 `sketch_file`／`sketch_sha256` 與 stage-4 hash 門禁（任何構圖來源都用），既有專案用 SVG 產的 `sketch_file` 仍有效、不需重畫；`h3d staging`（D06–D14）、W46 不變。

## [0.9.1] - 2026-10-28

### 新增
- 抖音蒸餾 A 批（2026-10，外部，未經 H3 實測）：同場配樂不跟生成段走（剪輯手冊 §8.1）、三人以上按當下那一對畫軸線（continuity-ledger §4／§5）、音色母帶挑平穩句且固定聲音描述只寫身份（consistency §6）、場景多角度分步生成（consistency §4）、動作中段反覆失敗改用省略（revision-and-retry §2）。
- 空間一致性規則（老易空間實驗 2026-10，第二批 86 支實測、方向性證據、未達原定 +25 門檻）：場景母片照平面圖畫且含所有座位、牆面分配層、構圖板以母片為底重畫、只拍生物的鏡頭綁店內參考（`references/storyboard/spatial-consistency.md`）；可選工具 `scripts/storyboard/wall_map.py`（不改預設編譯）；實驗數據 `docs/experiments/laoyi-spatial-2026-10/`。
- 連戲警告 C4「同場配樂跟著生成段走」：同一場相鄰段的 `non_diegetic_music` 不同或非 N/A 就警告，不擋（`continuity_lint.lint_scene_music`，`compile --check` 會印）。
- 動態技能路線圖 `docs/skill-roadmap.html`：八階段可播放片盤、每個動作的意義／指令／產出／決策者、交付範圍切換、三條回頭路、停車訊號、h3d 指令速查；`tests/test_skill_roadmap.py` 與真實 CLI 對帳。
- 收件匣八階段閱讀視圖（`scripts/review/stage_views.py`）：每關固定六區塊（問題、待決、摘要、文件、問題與處理、紀錄），文字產物可頁內展開全文，狀態分開顯示「尚未產出／製作中／等你核准／已核准／內容已變更待重審／局部重審」。
- 收件匣階段 5 段級重審卡（`D5-rereview`）。
- 階段文件標準格式（`references/document-standard.md`）：每份給人讀的文件最上面一張狀態卡（狀態｜版本｜更新、一句話、先看、要你決定、本次改動），最後修訂紀錄；外框用 `>` 行，不影響劇本解析與門禁。
- `h3d doc`（`scripts/doc_card.py`）：`stamp`／`resolve`／`check`／`show` 寫狀態卡與修訂紀錄；`init_project.py` 建案的模板、`layer2_to_table.py` 與 `compile_layer2_to_h3.py` 產出的 Markdown 自動帶狀態卡（重產時本體有變才升版，已核准的改成「已變更待重審」）。
- 狀態卡的「要你決定」每條自動變成收件匣卡（`blocking=2`，選項＝建議／或／先放著）。
- 收件匣閱讀視圖排版（`scripts/review/doc_render.py`）：狀態卡排成卡片、Markdown 排成閱讀頁（標題、表格、條列、引言）、劇本用劇本版型（場次列、△動作、角色｜台詞）、CSV 排成表格；手機寬度不溢出。
- 決策收件匣改版成「簽核牌組」（`scripts/review/inbox_page.py`）：一次一張決策卡、點選項＝簽下（蓋章＋卡片游走）、進度點可回頭改答、結尾頁「複製全部回覆」成功才放鯨魚娘慶祝動畫，底部常駐已簽數與複製鈕；視覺沿用鯨工坊海洋主題（亮／暗）與鯨魚娘吉祥物；閱讀視圖的寫死深色改用色彩變數。

### 變更
- `consistency.md` §7.1 改寫：「一段一張角色參考圖／一段一張臉」已撤銷（D3），新流程用 remix 角色卡維持人物一致；如實記 ref2va 程式預設（單人裁切、`--max-char-refs` 1、混臉只警告）與 remix 送件 adapter 尚未完成。skill-guide、pipeline、minimax-h3、anime-drama-grid、README 同步。

### 修正
- 收件匣合併卡保留每張子卡（頁內逐件展開問題與選項），待決數改計原始件數。

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
