# 更新紀錄（CHANGELOG）

格式參考 [Keep a Changelog](https://keepachangelog.com/zh-TW/1.1.0/)，版號遵循 [語意化版本 SemVer](https://semver.org/lang/zh-TW/)。
升版規則與發版步驟見 [docs/RELEASING.md](docs/RELEASING.md)。

每個 PR 都要在「未發布」區塊加一行；發版時把「未發布」改成新版號。
`h3d next` 會讀這份檔案：專案版本章比目前技能舊時，列出中間各版標題提醒重驗。

## [未發布]
- 修正／新增：噩盡島 EP01 重跑尾項（不新增生成或後處理步驟）：Codex 構圖單人中近景（MS／MCU／CU／ECU）依構圖文字的臉朝向自動加英文方向句（「face turned toward the LEFT edge of the image — nose pointing left ←」，右邊同理；中文「朝圖片左邊緣」常被畫反，實測加英文句 5 張修好 3 張）；階段 4／5 審核頁自動建議改列全部 staging 提醒（W46 構圖板＋W47 雙人引子建議＋W48 引子格式警告，以前只列 W46）；`handoff_to_skeleton.py --force` 重建既有段時保留構圖綁定欄位（`sketch_file`／`sketch_sha256`／`sketch_status`／`sketch_prompt`／`sketch_generation`／`sketch_qc`，以 shot_id 對應、構圖檔 sha256 仍相符才保留；新模組 `scripts/storyboard/sketch_bindings.py` 可給專案自己的重建腳本呼叫）；新增可選劇本標記 `△【動作】`／`△【動作2.5】`（原著無台詞動作鏡）只算進「分鏡後預估片長」（預設 2.0 s、最短 MIN_SHOT_SEC），不算台詞、不進 L／G3／G7，不加標記行為不變（`tests/test_composition_facing_review_marker.py`）。
- 修正：《噩盡島》EP01 重跑與 v118 整集分鏡發現的規則衝突（以 #116–#120 為準、不新增生成或後處理步驟）：劇本估時句間 0.3 s 改依句數（句末標點）不依行數，#120 合併同一人連句不再把 G3 推過 3.9；`adapt_gate` 另報「分鏡後預估片長」（MIN_SHOT_SEC、#116 說話窗口、17n+5，只回報）；`extra_lines` 認內心 VO／畫外／`voice_only`，編譯成畫外句式、閉唇句只給看得到臉的人（不再出現「a soundless voice's lips」）；`refcheck`／audit E50 跳過 `voice_only`／`no_visual_reference` 角色；`pacing_profile` 新增 `Fast_Dialogue`；W47 純內心 VO 段不建議雙人引子；D2 與 `pacing_gate` 密度對 ≤4 字短句鏡只算 max(1.2 s, 字數÷4＋0.5 s)、多出的另出 WARN；validate 新 6e 以角色包／設定圖清單比對中近景主鏡（`--root`，只警告）；Codex 構圖左右一律觀眾視角、`absent_objects` 從構圖文字拿掉並明寫「畫面中沒有」、鏡層 `scene_master_disabled` 不附母版（`tests/test_ejindao_ep01_findings.py`）。
- 修正：`h3d assemble` 只讀每鏡主句、漏掉 #120 同鏡接話——`dialogue_and_audio.extra_lines[]` 每句依自己的 `speech_window` 一起燒進字幕與時間軸（speaker 用該句的；接話缺 `speech_window` 直接擋該段、不猜位置；`narration_only` 不收接話），與 #119 雙人引子剪片頭／前移相容（引子內的接話照樣擋）；`validate_storyboard` 的「E4 切點不可行」改用與編譯器／audit E4 共用的 `h3_spec.MIN_SHOT_SEC`（1.2 s）擋、`SHOT_SOFT_MIN_SEC`（2.0 s）以下只出 `W:E4 短鏡` 提醒；`tests/test_pacing_gate.py`、`tests/test_dialogue_density.py` 由 pytest 風格改成 unittest，CI 的 unittest discover 現在會跑到；SB-2：`h3_spec.frames_for` 秒數換幀先吸附離整數幀 <0.05 幀的浮點誤差（4.4583 s 以前 floor 成 90 幀、現為 107 幀，ceil 方向同理），validate E4 有合法 `metadata.frames` 時直接用它（`tests/test_assemble_extra_lines.py`）。
- v118 實測規則衝突修正（疊在 #116＋#117＋#118 上）：鏡長下限 2.0→1.2 秒（編譯器與 audit E4，<2 秒只提醒）、對話段 17n+5 取整 tail-fit（末句後就近 0.3 秒）、同鏡接話 `extra_lines` 逐句 `<d>`、分鏡語速閘門分畫內 4.7／VO 5.8 字/秒、說話佔比警告改 >90%（#118 75–90%）、單句建議 ≤18 字、VO 16–18 字預設留 H3、`pacing_gate` 密度同 D2 扣段首／段尾無台詞鏡、`source_action` 動作鏡不計入有人聲鏡比例、`beat_pause` 切鏡後開口同 D4、`adapt_gate --source-text` 略過專有名詞引號、原著對白全保留時密度 3.6–3.9 只備註並檢查停頓／建立標記上限；不新增生成或後處理步驟（`tests/test_v118_rule_conflicts.py`）。
- 無廢片生成（疊在 #116 上）：`style_lock.tail_freeze_hold` 預設改 false（`compile` 沒寫時不加、`handoff_to_skeleton` 產 false），不再生成每段末 1 秒要剪掉的靜止；`pacing_gate` 新 WARN：有人聲鏡比例 <80%（爆款 Work_01／Work_08 幾乎每鏡有人聲，反應鏡用 L-cut 或旁白）、提示詞含末 1 秒靜止句。舊專案檔案裡明寫 true 的照舊。
- 雙人引子（E3）：段縫硬切到單人近景的文戲段，第 1 鏡前先拍 2.0 s 固定機位雙人鏡（`shots[0].dual_lead_in: true`，同一次 H3 生成、不另外出片），`h3d assemble` 自動剪掉片頭並前移台詞／字幕；`h3d staging` 新增 💡 W47 建議（同場硬切＋單人 MS 以內＋有台詞＋有畫外對戲角色，只建議）與 ⚠️ W48 格式檢查，assemble 遇格式不符直接擋該段；規則與寫法見 `spatial-consistency.md` §7（PR #115 T4 實測：同 3 段同種子 12 個樣本跑位／重演 0/12，現流程 4/12、新流程 5/12；一場戲、REMIX，屬小樣本）。編譯器不變；沒標 `dual_lead_in` 的段編譯與組裝結果不變（W47 只是建議）。配套 #116／#117／#118／#120：引子是「無廢片」原則唯一例外（12/12 無跑位，比整段重生便宜）；`pacing_gate` 密度／有人聲鏡比例／切鏡後開口／開口次數、validate D1–D4／說話佔比／段長提醒／9:16 景別比例、audit W13 說話佔比都不計引子那一鏡、段長扣 2.0 s；W48 與 assemble 也檢查 `line_timecodes`、`extra_lines[].speech_window` 沒落在引子裡；引子維持 2.0 s（T4 實測長度；#120 的 1.2 s 硬下限之下 1.2–2.0 s 仍屬未實測短鏡），tail-fit／17n+5 相容（`tests/test_dual_lead_in_pacing.py`）。

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
