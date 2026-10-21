# 產線工具（h3d）與四道確定性檢查

> 這一頁給「要跑這個 skill 的人／agent」看：有哪些指令、每個檢查在擋什麼、看到錯誤訊息怎麼處理。
> 規則的來源與理由寫在 `pipeline.md`／`consistency.md`／`minimax-h3.md`；這裡只講操作。

## 1. 一個入口

```bash
python scripts/h3d.py --list          # 所有子命令
python scripts/h3d.py status --root . # 全局狀態（階段／依賴／送件／失敗目錄）
```

| 子命令 | 做什麼 | 何時用 |
|---|---|---|
| `doctor` | GPU 顯存、ffmpeg（含 `-vsync` 回歸）、服務 port、磁碟 | 開工前、換機器後 |
| `compile` | Layer 2 → H3 六段式提示詞＋`segments-*.json`；`--check` 同時跑 17 條自檢與失敗目錄 | 每次改完分鏡 |
| `audit` | 參考圖／主體定義／台詞預算對帳 | 編譯後單獨重驗 |
| `submit` | 送 FreeVideo：能力表＋時長斷言＋ledger 去重 | 使用者要求生成時 |
| `collect` | 只把「已完成但沒下載」的工作收回來 | 批次中斷後 |
| `resume` | collect 後補送未產出的段 | 中斷後續跑 |
| `qa` | 影片驗收＋**證據分級** | 拿到影片後 |
| `assemble` | 配音、字幕、響度、拼接 | 交付前 |
| `deps` | segment 級依賴帳本（`--record`／`--status`） | 改動後查「哪幾段要重跑」 |
| `catalog` | 失敗目錄（`--list`／`--check`／`--acks`／`--prune-acks`） | 想知道「這句為什麼會被擋」 |
| `ack` | 記錄「我接受這條警告」的憑證 | 確認是誤報、但不想改稿時 |

每個子命令都保留原本的 `--help`，`h3d` 只是路由，沒有第二套邏輯。

## 2. 四道檢查在擋什麼

### (a) 時長量子（17n+5）

FreeVideo 會把秒數向上取到最近的 `17n+5` 影格。**送 `frames/24` 的精確值**，不要送四捨五入後的秒數
（`11.542` 會被推到 294 幀＝12.25s）。編譯器寫 `metadata.frames`，送件端回讀服務端 `frames` 與
下載後的 ffprobe 長度；不符就取消並隔離成 `.drift.mp4`。

看到 `duration_drift`：代表服務端或檔案長度與要求不符，**不要拿去 QA**，先查是不是手改過 segments。

### (b) 證據分級（qa）

`measured`（本機量過）／`sourced`（文件或競品）／`inferred`（推論）。報告結論只有三種：

- `VERIFIED`：所有分段都產出且量測通過
- `PARTIAL`：有缺段、失敗、跨鏡連續性警告，或含 `inferred` 檢查
- `UNVERIFIED`：一段都沒量到

**階段 6 閘門要求 `VERIFIED`**；舊報告（沒有 `evidence` 欄位）會被要求重跑。標題出現
`TECHNICAL CHECK PARTIAL · NOT READY TO SHOOT` 就是「不要開拍」。

### (c) 依賴帳本（deps）

每段記 `layer2`／`prompt`（含 `built_from_layer2_sha256`）／`video`（含 mtime）。

```bash
python scripts/h3d.py deps --root . --record
python scripts/h3d.py deps --root . --status --strict
```

- `prompt_stale`：分鏡改了但提示詞沒重編
- `video_older_than_prompt`：影片比提示詞舊（改了稿沒重跑）
- `video_missing`：記過影片、現在不見了

只報「哪幾段要重跑」，**不會自動重簽核准**。

### (d) 失敗目錄（catalog）

每條失敗有症狀／根因／最小修法／證據／信心等級，以及純 regex 的 detector。`enforce=error`
直接擋送件，其餘只警告——但**警告也要處置**：

1. 改稿（首選）
2. 或 `h3d ack <ID> --root .` 明確接受 → 寫入 `review/catalog-acks.json`
   （綁定命中段的 prompt hash 與目錄版本；改稿或改規則就失效）
3. ack 檔已納入 **stage-5 核准快照** → 記得重新核准 stage-5

`--prune-acks` 清掉 covers 對不到現行稿件的 ack。

> ack 的定位是「人看過並接受」，不是「讓 gate 閉嘴」。沒有 ack 就送不出去，這是刻意的。

### (e) 階段 6 的「影片 × 九宮格 × 設定圖 × QA」頁

`review/stage-6-videos.html` 每張卡左邊是影片，右邊由上而下是階段 4 構圖（`grid-*` 或逐鏡 `panel-*`）、階段 2 角色設定圖（`adapt/bible.json` 或 `assets/reference-manifest.json` 對映）、以及 `qa-report.json` 的量化欄位。缺圖只顯示紅框，**不阻擋核准**。

### (f) 切點標記（選用，非官方語法）

`h3d compile ... --embed-cut-markers` 會在提示詞寫入：

- `<cutoff>`：段落末鏡（表示這是最後一個可截斷點）
- `<scenetrans>`：跨場景的首鏡

同時在 `metadata.cut_marker_tokens` 記下是否嵌入與規格。**預設關閉**，因為這是本專案約定
（官方對這兩個 token 的語義我沒有可核對的來源）；要交給剪輯／拼接工具時再開。
結構化的切點時間一直都在 `metadata.cut_markers`，不需要開這個旗標也能用。

## 3. Provider 能力表

`scripts/storyboard/providers/freevideo.json` 宣告 fps、frames 區間、支援比例、參考圖／音訊／LoRA 上限，
每個欄位都標 `source`：

- `measured`：本機真的量過 → 違反是**硬錯誤**
- `docs`：官方文件或考證 → 只警告
- `assumed`：未驗證 → 只警告

送件前會印出能力摘要；與 `h3_spec.py` 常數不一致時會提醒更新。**專案覆寫只能加嚴、不能降級**
（把 `enforce=error` 改成 warning 會直接報錯）。

## 4. 常見訊息 → 處置

| 訊息 | 意思 | 怎麼做 |
|---|---|---|
| `17n+5 量子` / `frames 超出支援區間` | 分段長度不是合法量子或不在 124–362 | 改分段長度；真的知道自己在做什麼才加 `--allow-out-of-range` |
| `失敗目錄: [F-...]` | 命中已知失敗模式且該條 `enforce=error` | 依 `minimal_fix` 改稿 |
| `需明確確認：... --ack-warnings` | 命中警告，尚未 ack | 改稿，或改用 `h3d ack` |
| `已有 waiting 的 job` | 服務端還有活著的工作 | 先 `collect`，不要重送（會重複計費） |
| `QA 證據等級為 PARTIAL` | 缺段或未達 VERIFIED | 補跑缺段後重驗 |
| `影片 hash 缺失或不相符` | 影片被動過 | 重跑該段或重新產 QA 報告 |
