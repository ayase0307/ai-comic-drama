# FreeVideo adapter（可選）

[FreeVideo](https://github.com/FlashML-org/FreeVideo) 是本 repo 支援的生成工具；可用模型、HTTP 介面與 MCP 能力依安裝版本而異。

FreeVideo 是本 repo 支援的本機 adapter。其可用能力依安裝與版本而異；文字生影片、參考素材、多鏡影片、拼接或圖片生成只在當前服務實際提供時可用。

本技能可產生分鏡與提示詞；FreeVideo 只有在本機服務可用且使用者選擇使用時才負責生成。資料處理位置依所選工具而定，不能承諾全程在本機；不同 provider 或 Agent 工具的隱私與執行方式也可能不同。

FreeVideo 不是必經流程。若使用者只要文字／分鏡，停在指定交付即可。若使用者要求生成，先檢查當前 Agent 是否有相容的影片工具，或本機 FreeVideo adapter 是否可連線；兩者都不可用時，回報可用的文字交付，不重問已提供的模型參數，也不假裝完成影片。

## 連線（每個新 session 先做一次）

1. （預設位址）`GET http://127.0.0.1:8189/freevideo/agent`：回 `enabled: true` 才代表可用。
2. `GET http://127.0.0.1:8189/freevideo/agent/v1/connect?lang=zh`：讀純文字接入說明，**以該說明為準**（令牌檔位置、MCP 指令都寫在裡面，版本更新會變）。
3. 令牌讀取：從說明指定的令牌檔讀，放進 `Authorization: Bearer` 標頭。**不要印出令牌、不要展示給使用者、不要寫進任何檔案**（包含本 repo）。
4. `POST /connect/hello` 打招呼，再 `GET /` 看 `ready`、可用功能與未完成的影片。
5. 已設定 MCP（`claude mcp add freevideo …`，指令見接入說明）的 session 直接用 `freevideo_*` 工具；剛設定的 MCP 要到下個 session 才會出現，當下用 HTTP。

歷史本機驗證（2026-10-17）：當時服務握手成功並回報 `ready: true`，後端為 CUDA。此記錄只代表當時的設備與版本，不保證目前可用；每次新工作檢查當前連線與能力。

## 規則（以接入說明為準，摘要）

- 只在 FreeVideo 內工作，不改本機其他檔案；看到使用者自己的未完成影片（`unfinished`）不要動，除非使用者要求。
- 使用者提出要求後才開始任務，不要自行啟動；`ref` 每個新請求都用新名字（含日期時間），同一個 `ref` 只用來重送「回應遺失」的請求。
- 每個任務給 `label`（2–8 字，使用者的語言）、`seconds`、`aspect`。
- 先選角再拍：搜角色庫、沿用符合的卡片；找不到才新建，沒有照片就用 `/cast/{id}/generate` 生成參考圖。後續鏡頭用卡片當前的圖。
- 預設切鏡頭：新鏡頭直接用角色卡與場景圖生成，不接上一段；只有必須連貫的長鏡頭、動作或聲音才「接著生成」，一條最多 5 段。
- 每個錯誤有 `next` 欄位，先自己照做（降解析度、縮短、重拍、換寫法）；同一個要求不要反覆提交。
- 由使用者保管的操作（暫停、繼續、停止會話）Agent 會被拒絕，不要試。

## 對應本技能的八階段

| 本技能階段 | FreeVideo 做什麼（若當前版本提供） | 工具支援 |
|---|---|---|
| 2 角色／場景設定 | 若本機服務提供角色卡／圖片能力，可用於參考資產 | 核心資產也可由其他已連線或手繪工具產生；遵循使用者提供的工具選擇 |
| 4 分鏡表 | 不要求使用 FreeVideo 生成構圖 | Stage-4 PNG 可由 Qwen、手繪或其他可用工具提供，需 shot 對應並通過同一審核 |
| 5 提示詞包 | 本 repo 的編譯器輸出 Ref2VA H3 六段式；FreeVideo 端支援以當前介面為準 | `compile_layer2_to_h3.py` 產生 `prompts-epXX.md` 與 `segments-epXX.json` |
| 6 生成 | 僅在 FreeVideo 目前提供相容端點且使用者要求時提交 | `submit_h3_segments.py` 支援本機 adapter；QA 工具與人工 review 分開 |
| 7 交付 | 視當前服務介面下載已生成影片；本 repo 組裝器是選用工具 | 旁白／畫外音由外部 TTS 產生、H3 這段只出環境音床；組裝器不解析外部 narration Markdown，旁白需轉成支援的 inline 欄位，或交由其他剪輯工具 |

## 本機 GPU 預檢

> [!IMPORTANT]
提交前的 GPU 預檢只代表工具讀取到的當前狀態。需求會隨模型、解析度、背景工作與服務版本變動；單一舊設備的數值不可作為所有使用環境的硬門檻。

`scripts/storyboard/submit_h3_segments.py` 內建即時顯存安全檢查機制：
1. 工具可嘗試使用 `nvidia-smi` 回報即時狀態；查詢失敗時以實際錯誤說明。
2. `--dry-run` 檢查送件前條件，但不證明 provider 或模型可以完成生成。

## 自動化工具鏈操作

### 1. 階段 6 批次提交（`submit_h3_segments.py`）
```bash
# 乾跑檢查（安全驗證參考圖路徑、提示詞、顯存預檢）
python scripts/storyboard/submit_h3_segments.py --segments segments-ep01.json --root-dir . --output-dir videos/ --dry-run

# 正式批次提交（自動上傳參考圖 SHA256 快取、掛載 LoRA、輪詢進度並下載）
python scripts/storyboard/submit_h3_segments.py --segments segments-ep01.json --root-dir . --output-dir videos/
```

### 2. 階段 6 批次自動審查（`verify_video_shot.py`）
```bash
# 對照 segments-ep01.json 批次審查已生成影片，自動串聯 color_qa.py 並輸出 qa-report.json
python scripts/storyboard/verify_video_shot.py --segments segments-ep01.json --videos-dir videos/ --out-report videos/qa-report.md --out-json videos/qa-report.json
```

### 3. 階段 7 配音、字幕與成片組裝（`assemble_episode.py`）
```bash
# 先盤點本機 TTS 能力（唯讀；不寫檔、不上傳、不印金鑰）
python scripts/storyboard/tts_doctor.py

# 選用組裝；旁白／畫外音由外部 TTS 產生，H3 這段只出環境音床
# --audio-mode auto 逐段裁決：畫內對白留 H3 口型、外部化旁白混外部 TTS
python scripts/storyboard/assemble_episode.py \
  --segments segments-ep01.json \
  --videos-dir videos/ \
  --output final/ep01_final.mp4 \
  --audio-mode auto \
  --tts-engine voicestudio \
  --tts-config config/tts.json \
  --target-lufs -23

# 全鏈路閉環自檢
python scripts/storyboard/assemble_episode.py --self-test
```

TTS 引擎、憑證與音色對映寫在 `config/tts.json`；交付標準與混音鏈見 `references/pipeline.md` §7。

## 注意

- **令牌保護鐵律**：嚴禁在任何終端輸出、日誌或持久化檔案中印出 FreeVideo 令牌（Token）。
- 不要把 FreeVideo 的字幕規則當成必然：H3 有時仍會把台詞渲染成字幕。不要字幕時在描述結尾寫 `No subtitles, no on-screen text.`，仍出現就換 seed 重拍。
- 生成任務共用一條佇列；忙碌時用 `?wait=25` 等待，不要連續輪詢。
- 連不上時如實回報 adapter 不可用；若使用者已選擇其他相容工具，可按其範圍繼續，否則交付停在提示詞或文字階段。
