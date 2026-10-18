# 搭配 FreeVideo：讓 Agent 直接在本機出片

[FreeVideo](https://github.com/FlashML-org/FreeVideo) 是使用者本機的 AI 影片生成工具，內建 MiniMax H3，並提供 Agent 專用的 HTTP 接口與 MCP。

**能做什麼**：文字生影片（可帶首幀、首尾幀、人物／影片／音檔參考）；角色與場景卡片庫；多鏡影片（預覽劇本、逐鏡選片與重拍、自動拼接）；單段最長約 60 秒、更長自動接續；圖片生成與影格抽取。

**為什麼搭配**：本技能把故事變成分鏡與提示詞，FreeVideo 把它們做成片，Agent 不必再靠使用者手動搬運。它吃官方 H3 格式，提示詞原樣可送；角色卡讓角色一致直接沿用角色圖，而不只是貼描述片段；全程在本機，素材不外流。

階段 6 一律先走 FreeVideo；**FreeVideo 沒開或連不上時，才退回 `references/model-profiles.md` 的詢問流程。**

## 連線（每個新 session 先做一次）

1. （預設位址）`GET http://127.0.0.1:8189/freevideo/agent`：回 `enabled: true` 才代表可用。
2. `GET http://127.0.0.1:8189/freevideo/agent/v1/connect?lang=zh`：讀純文字接入說明，**以該說明為準**（令牌檔位置、MCP 指令都寫在裡面，版本更新會變）。
3. 令牌讀取：從說明指定的令牌檔讀，放進 `Authorization: Bearer` 標頭。**不要印出令牌、不要展示給使用者、不要寫進任何檔案**（包含本 repo）。
4. `POST /connect/hello` 打招呼，再 `GET /` 看 `ready`、可用功能與未完成的影片。
5. 已設定 MCP（`claude mcp add freevideo …`，指令見接入說明）的 session 直接用 `freevideo_*` 工具；剛設定的 MCP 要到下個 session 才會出現，當下用 HTTP。

2026-10-17 實測：握手成功，`ready: true`，後端 CUDA，可用功能含文字生影片、首幀、多鏡影片、長片自動接續；圖片編輯與時間線編輯功能當時未開。

## 規則（以接入說明為準，摘要）

- 只在 FreeVideo 內工作，不改本機其他檔案；看到使用者自己的未完成影片（`unfinished`）不要動，除非使用者要求。
- 使用者提出要求後才開始任務，不要自行啟動；`ref` 每個新請求都用新名字（含日期時間），同一個 `ref` 只用來重送「回應遺失」的請求。
- 每個任務給 `label`（2–8 字，使用者的語言）、`seconds`、`aspect`。
- 先選角再拍：搜角色庫、沿用符合的卡片；找不到才新建，沒有照片就用 `/cast/{id}/generate` 生成參考圖。後續鏡頭用卡片當前的圖。
- 預設切鏡頭：新鏡頭直接用角色卡與場景圖生成，不接上一段；只有必須連貫的長鏡頭、動作或聲音才「接著生成」，一條最多 5 段。
- 每個錯誤有 `next` 欄位，先自己照做（降解析度、縮短、重拍、換寫法）；同一個要求不要反覆提交。
- 由使用者保管的操作（暫停、繼續、停止會話）Agent 會被拒絕，不要試。

## 對應本技能的八階段

| 本技能階段 | FreeVideo 做什麼 | 工具支援 |
|---|---|---|
| 2 角色／場景設定 | 角色庫搜尋與建卡；`assets.md` 的固定描述片段寫進卡片，沒有照片就生成參考圖 | 核心資產圖詢問指定工具（推薦 Codex CLI），跨章節強制鎖定同一生圖引擎 |
| 4 分鏡表 | 多鏡影片：先預覽劇本與各鏡拍攝條數，確認後開拍，逐鏡看畫面選片 | `qwen_storyboard_grid.py` 內建 Qwen 黑白九宮格構圖審核 |
| 5 提示詞包 | FreeVideo 吃官方 H3 格式（三欄／Ref2VA 六段式），所以 `prompts-ep01.md` 的影片提示詞照 `references/h3/prompt-formats.md` 寫，原樣可送 | `compile_layer2_to_h3.py` 產生 `prompts-epXX.md` 與 `segments-epXX.json` |
| 6 生成 | 單段 ≤ 60 秒（實戰推薦 7–10 秒）；首幀圖、參考圖、首尾幀都可帶；結果自動進 FreeVideo「作品」 | `submit_h3_segments.py` 批次提交與顯存保護；`verify_video_shot.py` 批次審查 |
| 7 交付 | 每鏡選定後提交拼接；影片可用接口下載到 `videos/` | `assemble_episode.py` 智慧配音、字幕燒錄與無縫拼接 |

## 實戰顯存臨界點保護（8GB VRAM 硬約束）

> [!IMPORTANT]
> **4.20 GiB (4300 MB) 顯存啟動門檻**：  
> 本機在 RTX 4060 Ti 8GB 等顯卡環境下，啟動 FreeVideo H3 模型生成影片需消耗約 4.20 GiB 專屬顯存。若當前系統剩餘顯存低於此臨界點，將直接觸發 CUDA Out of Memory (OOM) 導致 FreeVideo 背景進程崩潰中斷。

`scripts/storyboard/submit_h3_segments.py` 內建即時顯存安全檢查機制：
1. **即時查詢**：提交前透過 `nvidia-smi` 查詢當前 GPU 總顯存、已用顯存與剩餘可用顯存。
2. **自動差額診斷**：若剩餘顯存 $< 4300\text{ MB}$，立即發出醒目警示並精確計算差額（如「尚缺 162 MB」），提示使用者關閉瀏覽器硬體加速或高負載進程後重試。
3. **乾跑驗證（`--dry-run`）**：在不消耗 GPU 資源與不送出排程的情況下，完整驗證 `segments-epXX.json` 的參考圖是否存在、提示詞結構是否完備、顯存是否充足。

## 自動化工具鏈操作

### 1. 階段 6 批次提交（`submit_h3_segments.py`）
```bash
# 乾跑檢查（安全驗證參考圖路徑、提示詞、顯存預檢）
python scripts/storyboard/submit_h3_segments.py --segments segments-ep01.json --out-dir videos/ --dry-run

# 正式批次提交（自動上傳參考圖 SHA256 快取、掛載 LoRA、輪詢進度並下載）
python scripts/storyboard/submit_h3_segments.py --segments segments-ep01.json --out-dir videos/
```

### 2. 階段 6 批次自動審查（`verify_video_shot.py`）
```bash
# 對照 segments-ep01.json 批次審查已生成影片，自動串聯 color_qa.py 並輸出 qa-report.json
python scripts/storyboard/verify_video_shot.py --segments segments-ep01.json --videos-dir videos/ --qa-report videos/qa-report.json
```

### 3. 階段 7 配音、字幕與成片組裝（`assemble_episode.py`）
```bash
# 執行全鏈路智慧配音（Edge-TTS + SAPI 備案）、Windows 冒號轉義字幕燒錄與無縫拼接
python scripts/storyboard/assemble_episode.py \
  --segments segments-ep01.json \
  --videos-dir videos/ \
  --out-dir final/ \
  --output final/ep01_final.mp4

# 全鏈路閉環自檢
python scripts/storyboard/assemble_episode.py --self-test
```

## 注意

- **令牌保護鐵律**：嚴禁在任何終端輸出、日誌或持久化檔案中印出 FreeVideo 令牌（Token）。
- 不要把 FreeVideo 的字幕規則當成必然：H3 有時仍會把台詞渲染成字幕。不要字幕時在描述結尾寫 `No subtitles, no on-screen text.`，仍出現就換 seed 重拍。
- 生成任務共用一條佇列；忙碌時用 `?wait=25` 等待，不要連續輪詢。
- 連不上時如實告訴使用者「我連接不到你電腦上的 FreeVideo」，不要另裝程式繞過。
