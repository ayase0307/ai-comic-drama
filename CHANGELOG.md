# 更新紀錄（CHANGELOG）

格式參考 [Keep a Changelog](https://keepachangelog.com/zh-TW/1.1.0/)，版號遵循 [語意化版本 SemVer](https://semver.org/lang/zh-TW/)。
升版規則與發版步驟見 [docs/RELEASING.md](docs/RELEASING.md)。

每個 PR 都要在「未發布」區塊加一行；發版時把「未發布」改成新版號。
`h3d next` 會讀這份檔案：專案版本章比目前技能舊時，列出中間各版標題提醒重驗。

## [未發布]
- 新增：Base 三字段編譯分流與送件（**P1-1 第二片**，導演大師對照）——`compile_segment_h3_base`：`t2v／i2v／fl2v` 段改產官方 Base 結構（對齊指令 instruction＋`integrated_multimodal_description`（風格句＋逐鏈 beats）＋`overall_soundscape`＋`non_diegetic_music`；**沒有** subject_definitions／summary／retention_analysis，也不掛任何參考素材），i2v/fl2v 幀來源記 `metadata.frame_sources`（缺圖 compile 直接擋）；對齊指令照官方模板（i2v `For the target video, at 0.00 seconds…`、fl2v `Picture 2 … aligns with the S.SS-second mark`，S.SS＝有效時長兩位小數、多鏡段 Shot 號換成真實末鏡）。送件端：FreeVideo 走 `media.first`／`media.last`（官方 generation_media schema 與 references 互斥）、REMIX i2v 自動改走 pikaff 模式帶 `first_frame`（pika480→pikaff480、pika768→pikaff768）、**fl2v 僅 FreeVideo**（REMIX pikaff 沒有尾幀欄位，compile 與送件端都擋）；lint／audit 對 Base 段改驗三欄（單鏡放行、無 summary 時長照 authored 對帳、remix 包機制 E50/E52/E53/E54 跳過）。時間軸正規化抽成 `_normalize_segment_timeline`（r2v 與 Base 同一套）。`tests/test_generation_mode.py` 重寫（validate 8 測＋compile 14 測＋門禁 5 測＋送件 9 測）。
- 新增：特寫／過肩鏡的編譯器背景錨（**P1-7**，11-03 #5b）——CU/MCU/ECU/OTS 鏡固定帶一句「The background behind the figures is the bound scene itself (＜場景卡英文描述＞) — with its own sky, ground and props, never the plain studio backdrop of the character reference sheet」；H3 不再把角色設定圖的純灰底當背景（S01-d 兩次實測）。檢查片 W:B1 已在 validate。`tests/test_background_anchor.py` 3 測。
- 新增：風格查表（**P1-4**，11-03 #1）——`assets/styles/styles.json`（1–11＋14 號：name／anchor／negative，逐字取自 `references/styles.md`；face_bias 欄留給有實測依據的風格）；`style_rules.load_style_table／table_anchor／table_negative`；remix 風格錨解析順序變成「段落錨 > 定案 style_anchor > 14 號固定錨 > **查表**」——任何在表內的風格都有影片錨，模型不得改寫（E55 照舊逐字比對）。`tests/test_style_table.py` 5 測（含與 styles.md 逐字對帳）。
- 修正：前段終態帶入改寫成第 1 鏡的**開頭第一句**（**P1-9**，11-03 #30）——`carry_sentence` 改產 `At the very first frame, <who> <state> — carried over from the previous segment.`，編譯器把它插在 `[Shot 1]` 之後、鏡頭描述之前（舊寫法接在鏡頭描述後面，模型忽略、角色先站回參考圖站姿：S03-d 兩個 seed 實測）；`continuity_lint._first_shot_text` 的 strip regex 同步。相關測試改斷新句與「姿勢在第 1 鏡開頭」。
- 新增：特效參考圖紀律（**P1-8**，11-03 #18／#19／#26／#27）——`compile` 對特效 `source_en` 寫身體部位（chest／eyes／胸口…）出 note（光源句會擴散成胸口亮點／紅眼；只寫特效本體位置，角色反光另寫被照亮）；`vfx-design-and-review.md` 新增 §7：參考圖只含特效本體（純天空／純黑底）、完整形狀不裁半、生圖模型不吃否定詞、送件前人工勾選「已去背景」「含完整形狀」。`tests/test_effect_light_discipline.py` 4 測。
- 新增：REMIX Studio 美術室生圖後端（**P1-12**，11-03 #8）——`scripts/storyboard/imagegen_remix.py`（`POST /images` → 輪詢 → 成品落檔到 assets.md 登記的路徑；engine=qwen 預設／moss 要 --style、moss 拒 ref_image）＋`image_backends` 新增 `remix` 後端（階段 2 可選；`detect` 探 8190 `/status` ready；`command_for` 給匯出提示詞＋逐張生成指令）。`h3d imagegen --detect` 現在認得 REMIX 美術室。`tests/test_imagegen_remix.py` 6 測。
- 新增：閉唇衝突與背景錨警告（11-03 噩盡島 #4／#5b，全部只警告）——`prompt_authoring` 新增 **W53**（同鏡同時出現「嘴唇張開」與「lips remain closed」：兩個不同人各說各話合法、同一人衝突，列出兩句讓審查者判斷）；`validate_storyboard` 新增 **W:B1**（CU/MCU/ECU/OTS 鏡的 `spatial_blocking.anchor_objects` 為空：H3 可能拿角色設定圖的純灰底當背景）。
- 新增：adapt_gate 劇本格式衛生 **G15–G21**（**P1-2**，導演大師 12 條劇本檢查的缺項；全部只警告、啟發式）——G15 非人主體（系統／儀器／讀數…）寫成對白、G16 整句括號動作寫成台詞、G18 引號內「他心想」第三人稱心理敘述、G19 引號後接動作（一行疊兩件事）與 crowd speaker（眾人／大家）、G21 鏡號／場記用語（特寫／淡入／切至…）寫進正文。`tests/test_script_hygiene.py` 7 測。
- 新增：段級生成方式 `metadata.generation_mode`（**P1-1 第一片**，導演大師對照）——`t2v／i2v／fl2v／r2v`（預設 r2v）進 schema 與 `validate_storyboard`（枚舉錯誤、i2v/fl2v 幀來源缺 sketch_file 擋、t2v 掛角色 W:G1、非 r2v 未實作 W:G2）；`compile_segment_h3` 對非 r2v **fail closed**（Base 三字段編譯與送件尚未實作，不靜默產出錯誤結構）。`tests/test_generation_mode.py` 11 測。
- 新增：`extract_chapter.py --input` 直接吃 **.epub**（**P1-11**）——標準庫 zipfile＋html.parser：container.xml → OPF spine 順序讀 XHTML，標題轉 `## 標題` 餵章節掃描，script/style 丟棄；不再要操作員自己找 pandoc。`tests/test_epub_input.py` 4 測。
- 新增：景別節奏與持續動作警告（11-03 噩盡島 #5／#29／#31，全部只警告）——`validate_storyboard` 新增 **W:R1**（同一主體連續 ≥3 鏡同景別級，CU/ECU 算一級）與 **W:R2**（≥6 鏡完全沒有 ELS/LS）；`prompt_authoring` 新增 **W51**（≥2.5s 的【動作】鏡 Motion 沒有持續動詞／進行式動作）與 **W52**（有 `<d>` 且 ≥2.5s 的鏡 Motion 沒有持續中的動作；keeps／still／all the while 與 starts pushing 這類進行式都算持續）。`tests/test_rhythm_and_sustain.py` 14 測。
- 文件：`references/revision-and-retry.md` 新增 §1.1「修復回聲驗證」——為修某條檢查而改稿時，交稿前重跑原檢查、逐碼確認原碼消失且無新碼、並確認不是把警告藏掉（來源：導演大師 `_issueStillVisible` 模式，2026-11-07 併入）。
- 維護：`docs/skill-roadmap.html` 的 roadmap-data 補 `h3d pack` 指令、submit 說明加 `--backend remix`（`test_skill_roadmap` 對帳）。
- 新增：REMIX 包對帳（**PR-R8**）——`scripts/storyboard/remix_pack.py`＋`h3d pack check --root . --project <studio專案>`：計畫表 `assets/character-packs.json`（含服裝變體）逐包對家機 `GET /packs`，缺包／kind／tag 不一致 exit 1；`--json` 機器可讀。建包仍在家機做，本指令是「回讀確認」。
- 新增：REMIX 抽卡重送（**PR-R9**）——`h3d submit --backend remix --reroll-failed` 只重送帳本裡 failed／timeout／unverified 的段（抽卡失敗自動重抽）；`--mode pika480 --seed N` 抽卡、`--mode pika768` 定稿照舊。
- 新增：REMIX QA 報告（**PR-R10**）——`h3d collect --backend remix --report` 收件後寫 `videos/remix-qa.json`：每段 `frames_requested／frames_actual／frames_drift／duration_actual／identity／file`，作為階段 6 verdict 證據；identity fail 先重抽、warn 逐格人工、no_face 不算過。
- 新增：REMIX 送件 adapter（**PR-R7**）——`scripts/storyboard/submit_remix.py`＋`h3d submit/collect/resume --backend remix`：只送 remix 段，送件前照跑 stage-5 門禁、audit remix 分支、lint(backend="remix")、失敗目錄、撰寫審查、編譯指紋（E38）與能力表校驗；`POST /jobs` 帶 `prompt=h3_prompt`／`refmods`／`seconds=frames/24`／`shot=segment_id`／`plan{title_zh,start_state,end_state}`；帳本 `videos/remix-jobs.json`，收件記**後端實際影格數**（16g）並查 identity；`--mode`（新定案 `remix_mode`，預設 pika768）／`--seed`／`--reroll`／`--dry-run`。令牌永不印出。`tests/test_submit_remix.py`（假 REMIX server 六測）。
- 新增：REMIX 能力表對齊 5070 Ti＋REMIX v0.8（Pika H3 Flex 家族）——`providers/remix.json` 全表重寫（modes 改 draft/refine/long＋pika480/768/1440/pikaff480/768、秒數 2–15 s、包數分級改 16GB ok 4、新增 audio_refs／identity／upscale／extend／storyboard_import／plan_fields 欄位與 recheck 清單）；`h3_spec` remix 改 **56–362 幀、往上取**（2026-11-07 本機 probe 實測：2 s → 56 幀、15 s → 362 幀；舊 V1.3 引擎的 floor 量測標註退役、draft/refine/long 未重測）；`test_remix_backend` 對帳更新。
- 修正：`test_action_shot_allocation`／`test_dual_lead_in_pacing`／`test_v118_rule_conflicts` 的子程序改 UTF-8 解碼＋`PYTHONIOENCODING=utf-8`（Windows cp950 下 stdout 解碼失敗回 None，10 個測試 ERROR）。
- 新增：特效資產必須有參考圖（audit **E56**）——`assets.md` 的 `B-` 卡片若文字有特效／光效／VFX／effect／light form 或明寫 `類型：特效`，登錄為特效；FreeVideo 要有 `reference_paths.effects`、REMIX 要有 `kind=effect` 的包，`pack_waivers` 不能豁免。編譯器產出「copy only its shape, feather-like light streaks, colour and translucency…」與局部光源句（缺 `source_en` 出「特效缺光源位置」warning）；整片調色句（bathes the scene in red 等）出 **W56** 警告。
- 新增：audit **E57**——單鏡動作／表演／走位／描述出現 glow／beam／aura／energy／火焰／紅芒／光幕等特效詞，卻沒有 `effect_ids` 或 `B-` 特效 id 就擋（陽光／日光／光線／lighting 與 `light` 欄位排除；可用 `effect_ids: []`＋`no_effect_reason` 單鏡宣告）。文件同步列在 E56 旁。
- 新增：階段 6 連戲檢查——`verify_video_shot.py --continuity-pairs <out_dir>` 抽段縫與段內硬切左右影格，Pillow 併排成 `pairs-N.jpg`（每張最多 8 對）並產出 `continuity-checklist.md`（location／prop／screen side／costume／light／effect 六列＋每對 dE76）；`continuity_lint` 新增 **C5**，同場相鄰段終態與下一段連戲錨點 key 不同且沒有 `continuity_changes`／`state_change` 標記時出 warning。
- 修正：`End state`／`Starting state` 不再把 raw dict／JSON 印進提示詞，改成英文散文；`lint_h3_prompt` 新增 **E58**，提示詞含 `{`、`}` 或 `": "` 即硬錯誤（自檢條數 18）。
- 修正：真實專案回饋——`B-baishou` 這類「有生物設定板描述／三視圖、沒有類型」的 `B-` 卡不再被當特效（E56 不再誤報）；顯式 `類型：` 優先，關鍵詞只搜固定描述／設定板描述／類型說明。`prompt_authoring` 把編譯器固定旁白句、預設旁白聲線、特效參考句與局部光源句列為 boilerplate（不觸發 E33／W33／E35）。E57 排除 highlight／glint／reflection／sheen／catchlight 與 反光／高光／微光／光澤／眼神光。
- 維護：移除 `doctor.py` 的 VoiceStudio 8001 探測；`decisions` 無外部 TTS 專用定案可移除；`verify_video_shot.py` 不再重建 `sys.stdout` wrapper（避免 GC 關掉共用 buffer 造成後續 import「closed file」）。
- 變更（破壞性）：外部 TTS 全面移除，所有台詞、旁白、畫外音、內心獨白改由 MiniMax H3 原生生成。`compile_layer2_to_h3.py` 只剩 `--narration-policy h3-native`；`voice_route: "external"` 與舊政策 `external`／`short-offscreen-h3` 會報錯「外部 TTS 已移除」；不再輸出 `external_narration`。旁白改用沒有 `<Picture>` 的 `<Subject N>` (Sx) 綁定、固定英文聲線（`voice_4d_spec_en`／`h3_voice.voice`，缺省用預設旁白描述），並固定加「No one in frame speaks during this line; every visible mouth stays closed and still.」；旁白以 3.0 字／秒估時，>18 字提醒拆鏡。`decisions.py` 的 ④ 與舊值都映射 `h3-native`；audit E24 改成「殘留外部 TTS 標記即錯誤」；`assemble_episode.py` 移除 TTS 合成與 `--audio-mode`／`--tts-*`／`--bg-volume`／`--narration`，只燒字幕、做響度對齊與拼接；刪除 `tts_engine.py`、`tts_doctor.py`、`config/tts.example.json`，移除 `h3d voice align`（`voice_align.py` 保留給 Concat 剪輯 adapter 的非 TTS 對齊工具）。文件同步改寫（SKILL、pipeline、consistency 等）。
- 修正：成片兩遍 loudnorm 後明確固定取樣率與立體聲聲道，避免 FFmpeg 5.1 在 `aresample` 到 `atrim` 間無法協商聲道配置而使組裝失敗。
- 測試：`test_audit_stage0_3`、`test_ejindao_ep01_findings` 執行子程序時加 `PYTHONIOENCODING=utf-8` 與 `errors="replace"`，Windows（cp950／ANSI OEM）不再因解碼失敗讓斷言拿到 `NoneType`。（與 main 其他測試的 `{**os.environ, ...}` 寫法一致）
- 維護：`.gitignore` 忽略 `graphify-out/`（graphify 本機索引產物，不進版控）。
- 文件：`docs/research/briefs/` 加入 WIP 落地規劃（3 PR 切法、`five_part_en` 單一 helper、schema 判定）與三件交付審查的 brief／Opus 回覆，實作決策可追溯。
- 修正：`build_stage_review` 階段 5 改用 `resolve_backend` 決定 lint 路線（段落 `metadata.video_backend` → 頂層 `video_backend` → `refmods` → `decisions.json` → ref2va），只帶 `refmods` 的 REMIX 段不再被 Ref2VA 規則誤報；`COMPILER_BOILERPLATE` 收「the figure seen from behind matches …」編譯器句，跨鏡重複不再算手寫套句（E33／W33）。
- 新增：階段 5 綁定可逐鏡覆寫五小節與可見度——`en_overlay.shots.<gsid>.five_part_en` 只寫要改的節（key 限 `camera`／`motion`／`performance`／`light`／`sound`，值必非空字串），其餘節保留 Layer 2 原值，且寫回讀取端的同一個容器（不再兩處各留一份）；`offscreen_subject_ids` 宣告該鏡看不到誰（不算進 R4 人數鎖、也豁免 E40），`accepted_unbound_subject_ids` 只豁免參考圖、仍算人數；段落級 `en_overlay.style_anchor_en` 同時覆寫 Ref2VA 的 `style_lock.anchor` 與 REMIX 的 `metadata.style_anchor_en`（階段 4 核准後不必改 Layer 2）；REMIX 段另會把 `offscreen_subject_ids` 從 `visual_subject_ids` 扣掉，E50／D08／站位句才不會又要那個人的包。`shot_overrides` 同步接受這三個 key，舊綁定行為不變（`tests/test_stage5_en_layer.py::EnOverlayOverrideTests`、`references/tooling.md` §2.3）。

## [0.10.1] - 2026-11-02
- 新增：技能原則 9–12（開工前版本對帳、批次修＋REMIX 分鏡表同步＋抽卡自主、參考包壓過提示詞、核准版與定稿版分開放），Overview 新增「接手既有專案先稽核再推進」，並帶入 `references/audit-inherited-project.md`、`references/remix-draft-loop.md`、`scripts/audit_inherited_project.py`（本機 bot 副本已在使用、未回流 repo 的規則集）。原則 10 補「批次＝逐鏡對回 `shot_intent`，不是按警告類型批量改；階段 5 段級核准走 `--segments`，不得 `--auto`」，以免與階段 4／5 既有規則牴觸。
- 新增／修正：X @LoveUolanda H3 寫法中實測有效的規則收進編譯器（《噩盡島》EP01 家機 REMIX 盲評 E1-29／E1-03 各 2 seed）：R2 物理機位預設開——每段一次 `Camera law:` 總則（真實機位、禁數位裁切／模擬變焦、禁遠距旁觀與大空繞、重音前框好、釋放時才動），每鏡 Camera 節與標頭重複的焦段距離句換成實體機位句（可選 `camera_optics.rig_en`／`rig`，不寫就從角度字推）；R3 施力因果鏈預設開——可選 `action_and_performance.force_chain_en` 把 Motion 換成 `Force chain: …`，動作鏡與只露手的插入鏡自動接一行 `Forbidden:` 失敗模式（可選 `forbidden_en`，明寫 `[]` 關預設），新增 W50（【動作】鏡缺施力鏈，只警告），`Forbidden`／總則句不算 E32／E33／E35；R4 CAST RULE＋ENVIRONMENT LOCK 改可選、自動觸發（≥3 名人類、有 `absent_objects` 或 `metadata.cast_lock: true`）；R1 不收、R5 遮擋接力只進 `references/h3/camera-and-transitions.md` §6（待驗）。送件端：新增定案 `submit_endpoint`（local 預設＝家機 FreeVideo／REMIX／ComfyUI，無字元上限；hosted＝平台 API），audit 的 7000 字元 E 只在 hosted 報，本地改為估計 token 超過官方 tokenizer 262144 才 `[W11: 可能超過文字編碼器長度]`（家機伺服器端截斷待實測），lint details 記 `prompt_char_count`／`prompt_token_estimate`；`COMPILER_RULES_VERSION` 2026-11-02，REMIX golden 因多出總則、三人人數鎖與機位句更新（新模組 `scripts/storyboard/physical_camera.py`，`tests/test_physical_camera.py`）。（合併 #124 後：【動作】鏡判定改用 `action_marks.is_action_shot`——`source_action`＋`action_mark`、無台詞，與 validate D5／D1–D4、pacing_gate 一致；只標 source_action 的【建立】【停頓】鏡不加預設 Forbidden、不出 W50；施力鏈警告因 #125 佔用 W49 改為 W50）
- 修正：`h3d assemble` 缺跨段對白電平對齊——H3 每支 clip 原生音電平隨機（《噩盡島》EP01 重跑 30 支 integrated −9.94～−28.71 LUFS），整片單遍 loudnorm 後段間仍差 13.53 LU。新增段層「以對白為錨」增益（預設開，`--no-dialogue-align` 關；新模組 `scripts/storyboard/dialogue_loudness.py`）：每段只量對白區段（`speech_window`→鏡頭時間→整段 gated integrated）響度，固定增益對齊有對白段中位數（±12 dB，`--dialogue-anchor`／`--dialogue-max-gain`），無台詞段增益 0 保持相對電平（比錨點響 >6 LU 才壓），增益後峰值超門檻的段過 192 kHz `alimiter`；增益套在 PCM 串接路徑上（音畫同長、不累積 AAC 尾 frame）。整片改兩遍 loudnorm（`measured_*`＋`linear=true`）＋192 kHz 限幅、`-ar 48000`、`atrim` 回原長，段與成片 AAC 改 256k（192k 遇密集低頻會過衝），不加 `+faststart`（JuiceFS 會 I/O error）。交付報告／manifest 列逐段處理前後 LUFS／TP、增益與段間對白落差，>6 LU 出新警告 **W49**（`--loudness-spread-warn`）。EP01 重跑 30 段實測（`--target-lufs -16`）：段間對白落差 13.73 → 0.48 LU（整段 13.53 → 1.90 LU），成片 −16.02 LUFS／TP −1.84／LRA 4.0、第二遍維持 linear，總長 213.125 s 與原片同、音軌與影像同長（原成片音軌 213.187 s、96 kHz）；pipeline.md §7.4「不要逐段正規化」改寫為兩層做法並說明為何不違反（`tests/test_dialogue_loudness.py`）。
- 新增：原著無台詞動作 beat 強制給時間（噩盡島 EP01 吞鳥鏡：片長照台詞反推，咬／甩／落喉三動作只分到 2.2 s，成片沒被吞）。劇本【動作】標記改為必標、一個標記＝一個主要動作（多步動作拆多行）；`adapt_gate` G14a（一行塞 ≥3 個動作）／G14b（`--source-text` 時原著兩句台詞間有動作敘述卻沒標）只警告；`sync_script` 在有標記的場寫 handoff `script_sequence`；`handoff_to_skeleton` 每個標記獨立一鏡（`source_action`／`action_mark`）、鏡長＝標記秒數、依劇本先後排、fit 不壓縮、裝不下另開段；`validate_storyboard` 新增 D5（標記遺失／合併／截短，FAIL）、D6（無台詞鏡 ≥3 個主要動作且 < 1.5 s×動作數 FAIL、< 2.0 s×動作數 WARN）；D1–D4 與 `pacing_gate` 台詞類檢查不計動作鏡；編譯器末鏡是動作鏡時不 tail-fit。不加標記的舊專案行為不變（新模組 `scripts/storyboard/action_marks.py`，`tests/test_action_shot_allocation.py`）。噩盡島 ep01r 實測修正：動作鏡判定改為 `source_action`＋`action_mark`（v118 #9 的【建立】【停頓】鏡只標 source_action，以前被 D5 誤報整場 FAIL；D1–D4、pacing_gate、tail-fit 同一判定）；D6 對未標記舊鏡另數 `blocking_desc`（舊咬甩鏡 2.2 s 以前漏報，仍只 WARN）；D5 認鏡上 `source_scene_id`（跨場段動作鏡）；G14b 原著無引號的內心獨白用原文片段定位、短引號不再錯對到長句、錨點跨場延續（實測只拆吞食時 1 處 → 6 處）；動作詞表補「刮／沉／走／摸／騰／回頭／展翅…」，「下落」只排除「下落不明／的下落」（「頭上腳下落進喉嚨」以前算 0）、排除「刺眼／拍片／碎石…」；骨架連續【動作】鏈剛好滿 max-shots 且秒數裝得下時不從中間切段（最多 max+1 鏡）。
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
