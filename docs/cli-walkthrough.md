# 命令列逐步範例

> 這份文件保留重新設計前 README 的完整命令列內容（各階段腳本的直接呼叫方式、Windows PowerShell 寫法、依賴能力表、階段 4 構圖（Codex 分鏡）與 FreeVideo 說明）。日常操作請優先用單一入口 `h3d`，見 [`../references/tooling.md`](../references/tooling.md)。

## 安裝與第一步

把本 repo 放進 Claude 的 skills 目錄即可：

```bash
git clone https://github.com/ayase0307/ai-comic-drama.git ~/.claude/skills/ai-comic-drama
# 或用 skills CLI（支援 Claude Code / Codex / OpenClaw 等）
npx skills add ayase0307/ai-comic-drama
```

> 需求：**Python 3.10+**；影片 QA／組裝另需 FFmpeg。純文字規劃與提示詞編譯只需要標準庫。

裝好後先跑一次自檢，確認這台機器能做什麼：

```bash
python scripts/h3d.py doctor          # GPU 顯存、ffmpeg（含 -vsync 回歸）、服務 port
python scripts/h3d.py status --root . # 階段門禁／依賴帳本／送件帳本／失敗目錄
```

把要處理的原稿放入新專案的 `source/` 後，再對 Agent 說：

> 「幫我把這篇小說改編成長篇漫劇，每個事件都要講清楚，畫風 3D 國漫，16:9，到分鏡圖。」

預設就是長篇漫劇（整部一支連續長片）；想做短劇／竪屏爆款短集時要明講，例如「做成 12 集、每集 90 秒的竪屏短劇」。

Agent 會依你指定的交付範圍開始工作，沿用已提供的 brief、工具與參數；只詢問會阻礙當前工作的必要缺項。純文字劇本或分鏡可獨立交付，不必生成圖片或影片。

也可單獨使用命令列工具。先檢查本機支援的能力，再跑可離線驗證的流程：

下面是各階段命令索引，不可整段連跑。先依 `init_project.py` 產生的 `FLOW_HINT.md` 按目標完成階段 0–3 的 review 與人工核准；只有需要 H3 編譯時，才進入 stage 4。

```powershell
# 1. 建立專案骨架（自動產生 adapt/source.json 與 adapt/bible.json）
python scripts/init_project.py my-drama --title "我的漫劇"
# 預設長篇漫劇（不分集）；短劇短集要明確選：--format short --episodes 12 --episode-seconds 90
# 在 repo 根目錄執行；init_project 只建立專案資料夾，不會把 scripts 複製進去
$skillRoot = (Resolve-Path .).Path
Set-Location my-drama
python "$skillRoot/scripts/check_environment.py"
python "$skillRoot/scripts/run_offline_checks.py"
# 先把原稿放入專案 source/；再掃描目錄並抽取所需章節
python "$skillRoot/scripts/adapt/extract_chapter.py" --input source/novel.txt --list
python "$skillRoot/scripts/adapt/extract_chapter.py" --input source/novel.txt --volume 1 --chapter 1 --output source/ch01.txt
python "$skillRoot/scripts/adapt/estimate_duration.py" --novel --novel-file source/ch01.txt
python "$skillRoot/scripts/adapt/estimate_duration.py" --events adapt/source.json   # 依事件交代需求估總片長
python "$skillRoot/scripts/adapt/event_coverage.py" --project-dir . --out adapt/event-coverage.md   # 事件交代完整性

# 2. 劇本 HTML 註解同步回寫 handoff 與 H3 台詞審計
python "$skillRoot/scripts/adapt/sync_script.py" --handoff handoff-ep01.json --script script-ep01.md --prune-extra
python "$skillRoot/scripts/adapt/estimate_duration.py" --script script-ep01.md --genre xuanhuan_revenge --h3
python "$skillRoot/scripts/adapt/compare_adaptation.py" --source adapt/source.json --script script-ep01.md --handoff handoff-ep01.json --episode 1 --h3

# 3. 交接 JSON → 分鏡 Layer 2 骨架（預設 10s/3 鏡、動作力學模板），再轉表格與時間線
python "$skillRoot/scripts/storyboard/handoff_to_skeleton.py" handoff-ep01.json --out-dir layer2/
python "$skillRoot/scripts/storyboard/validate_storyboard.py" --file layer2/layer2-EP01-*.json --handoff handoff-ep01.json
python "$skillRoot/scripts/storyboard/layer2_to_table.py" layer2/layer2-EP01-*.json --check --md storyboard-ep01.md --timeline timeline-ep01.csv

# 4. 生成 Qwen 黑白鉛筆分鏡 分鏡總覽圖圖（支援 --no-arrows 生成純淨底稿）
python "$skillRoot/scripts/storyboard/qwen_storyboard_grid.py" --layer2 layer2/layer2-EP01-S01-a.json --generate-all --assemble-grid

# 5. 人工審核與單鏡局部修改（調整景別時長並由相鄰鏡頭吸收，零污染單格局部重抽）
python "$skillRoot/scripts/storyboard/patch_shot.py" --file layer2/layer2-EP01-S01-a.json --shot SH03 --shot-size CU --duration 3.5 --absorb-from SH04
python "$skillRoot/scripts/storyboard/qwen_storyboard_grid.py" --layer2 layer2/layer2-EP01-S01-a.json --redraw-shot SH03 --assemble-grid

# 6. 若需 H3 編譯，先審核 stage 4 構圖圖（Qwen、手繪或其他工具皆可）
python "$skillRoot/scripts/build_stage_review.py" --project-dir . --stage 4
# 使用者審核通過後才記錄核准，之後才能編譯
python "$skillRoot/scripts/build_stage_review.py" --project-dir . --approve-stage 4
# 編譯為 H3 官方六段式提示詞與 segments
python "$skillRoot/scripts/storyboard/compile_layer2_to_h3.py" --layer2 layer2/ --episode EP01 --project-root . --output-md prompts-ep01.md --output-segments segments-ep01.json --assets assets.md --bible adapt/bible.json --check
python "$skillRoot/scripts/build_stage_review.py" --project-dir . --stage 5
# 使用者審核通過後才記錄核准
python "$skillRoot/scripts/build_stage_review.py" --project-dir . --approve-stage 5

# 7. 僅在使用者要求生成且 FreeVideo adapter 當前可用時乾跑
python "$skillRoot/scripts/storyboard/submit_h3_segments.py" --segments segments-ep01.json --root-dir . --output-dir videos/ --dry-run
# 真正送件需有效 stage 5 核准且使用者要求生成；FreeVideo 只在本機 adapter 可用時使用
python "$skillRoot/scripts/storyboard/submit_h3_segments.py" --segments segments-ep01.json --root-dir . --output-dir videos/


# 8. 階段 6 批次影片審查（分段總時長精確比對、黑白防漏、分鏡總覽圖邊框檢驗、串聯 color_qa.py 輸出報告）
python "$skillRoot/scripts/storyboard/verify_video_shot.py" --segments segments-ep01.json --videos-dir videos/ --out-report videos/qa-report.md --out-json videos/qa-report.json

# 9. 階段 7 選用組裝（需實際可用的影片／音訊工具）（外部 TTS 盤點與配音、Windows 冒號轉義、多軌混音、Concat 拼接）
python "$skillRoot/scripts/storyboard/tts_doctor.py"
python "$skillRoot/scripts/storyboard/layer2_to_table.py" segments-ep01.json --check --timeline timeline-ep01.csv
python "$skillRoot/scripts/storyboard/assemble_episode.py" --segments segments-ep01.json --videos-dir videos/ --output final/ep01_final.mp4 --audio-mode auto --tts-engine auto --tts-config config/tts.json --target-lufs -23 --delivery-report final/delivery-ep01.md
# 外部 narration-ep01.md 不會由組裝器解析；將旁白轉為支援的 inline 欄位，或交由剪輯工具處理
```

`review/project-state.json` 是唯一階段狀態來源；核准會綁定輸入 hash，內容變更後須重審。Compiler 要求 stage 4 核准，實際提交要求 stage 5 核准；dry-run 可用於預檢。影片 QA 的技術通過結果不會自動成為人工核准。

> 上面這串長指令都有單一入口版本：`h3d compile／submit／collect／resume／qa／assemble／deps／catalog／status`，對照表與錯誤訊息處置見 [`references/tooling.md`](../references/tooling.md)。

### 依賴能力

| 工作 | 需要的能力 |
|---|---|
| 文字規劃、JSON/提示詞檢查 | Python 標準庫 |
| review 頁與分鏡總覽圖 | Python；圖片操作需 Pillow |
| 影片 QA 與組裝 | FFmpeg、ffprobe；部分輸入檢查使用 Python/Pillow |
| 圖片/影片生成 | Agent 當前可用的相容工具或連線後端；FreeVideo 是可選 adapter |

`scripts/check_environment.py` 檢查本機依賴，不探測 provider、帳戶或模型；`scripts/run_offline_checks.py` 執行離線測試。生成能力仍需依當前工具介面確認。


## 先分鏡，後生成

<div align="center">
<img src="../assets/storyboard.jpg" alt="Storyboard grid" width="90%">
<br><sub>分鏡表未驗證通過不出圖；出圖後先確認角色長相，再拿去生成影片。</sub>
</div>

分鏡走[導演分鏡體系](../references/storyboard/cinematic-director.md)：台詞一字不改、焦距與物距成對寫、同場連續與時空跳躍二選一握手、武戲接觸瞬間 90° 無遮擋。逐鏡生成、逐鏡檢查，不要一次丟十幾鏡。


## 階段 4 構圖：Codex 分鏡

進 H3 編譯前，每鏡都要有對應的構圖 PNG 並通過 stage-4 審核。用哪個生圖工具由使用者選（`h3d imagegen --detect --stage 4` 列出可用的，`h3d imagegen --set <後端> --stage 4 --quote "<原話>"` 寫入；只偵測到一個也要問）。以下以 Codex 分鏡為例：讀 Layer 2，每鏡出一張彩色分鏡圖、每段拼一張總覽圖，並自動綁定已核准的參考圖（角色正面裁切、異獸設定圖、段落場景母版，依序為 `<Picture N>`）。

```bash
# 先看提示詞與參考圖計畫（不生圖）
python scripts/storyboard/codex_storyboard_panels.py --root <專案> --episode EP04 --model <使用者指定模型> --dry-run
# 實際出圖（--model 必填，不會靜默改用預設模型）
python scripts/storyboard/codex_storyboard_panels.py --root <專案> --episode EP04 --model <使用者指定模型> --parallel 3
# 單鏡重畫
python scripts/storyboard/codex_storyboard_panels.py --root <專案> --shots EP04-S03-a-SH02 --model <使用者指定模型> --force
python scripts/build_stage_review.py --project-dir <專案> --stage 4
```

每鏡輸出到 `panels/panel-NN-<shot_id>.png`、每段分鏡總覽圖到 `images/grid-<segment_id>.png`，並回寫 `sketch_file`／`sketch_sha256`／`sketch_generation`（`backend: codex`）。`sketch_status` 為 `locked`／`approved`／`manual` 的格子不會被覆蓋。總覽圖標籤字型可用環境變數 `STORYBOARD_FONT=<字型檔>` 指定（舊名 `SVG_GRID_FONT` 仍相容）。Qwen 鉛筆九宮格、手繪或其他工具的 PNG 也可以，照同一組欄位回寫即可。

> 舊的 `h3d sketch` 子命令已移除，執行只會印替代指令並 exit 2；既有專案已回寫的 `sketch_file` 仍有效，不需重畫。


## 搭配 FreeVideo

**[FreeVideo](https://github.com/FlashML-org/FreeVideo)** 是跑在你自己電腦上的 AI 影片生成工具，內建 MiniMax H3，並提供 Agent 專用接口（含 MCP）。

**它能做什麼**
- 文字生影片，也能帶首幀圖、首尾幀或參考圖（人物、影片、音檔）
- 角色庫：建立角色／場景卡片，跨鏡頭沿用同一張臉
- 多鏡影片：先預覽劇本與鏡數，逐鏡看畫面、選片、重拍，最後自動拼接成片
- 單段最長約 60 秒，更長的自動接續；也能生成圖片、抽影格、問視覺模型畫面內容

**為什麼要搭配它**
- 本技能負責「想清楚」：改編與事件交代、角色、分鏡、提示詞；FreeVideo 負責「做出來」。接上之後 Agent 能從分鏡一路做到成片，不必你手動搬提示詞、下載、剪接。
- 吃官方 H3 提示詞格式，`prompts-ep01.md` 寫好就能直接送，不用再轉寫。
- 在本機跑，沒有額度與排隊費用，素材不離開你的電腦。
- 角色卡讓「角色一致」從靠貼描述片段，升級成直接沿用角色圖。

連線與用法見 [`references/freevideo.md`](../references/freevideo.md)；FreeVideo 沒開時，技能會退回「先問模型再生成」的流程。

## 搭配的專案

小說改編與導演分鏡兩個子體系分別整併自作者另開發的 novel-to-manju、cinematic-director-storyboard。本技能的影片提示詞（MiniMax H3）部分，以 **[ayase0307/h3-video-prompting](https://github.com/ayase0307/h3-video-prompting)**（MIT）為準：動作品質、節奏卡點、光影配色、音訊流程、失敗分診與情境 playbook 都在那邊持續更新。`references/h3/` 是該 repo `references/` 的同步副本（釘在 commit `1db923b`，逐檔紀錄在 [`references/h3/UPSTREAM.json`](../references/h3/UPSTREAM.json)）；本專案只額外加了 `lora-guide.md` 與幾個 ★ 標註。兩邊有出入時以該 repo 為主，並跑 `python scripts/sync_h3_reference.py --check` 找出漂移。

