# 動作段後製變速（階段 6 動態 QA → 階段 7 組裝）

> 來源：《噩盡島》階段 6 實測（2026-10-24），老大 13:11 定案「剪掉開頭凍結；定住和蓄力 2–3×；飄浮 1.8–2×；撞擊和有台詞處原速」、13:12「後製變速也可以寫」。

## 為什麼要做

H3／FreeVideo 出的片是 **24 fps 原生、沒有插幀**，幀數＝送件 `metadata.frames`，時間也沒有被拉長。動作戲的「慢動作感」來自三件事疊在一起：

1. **鏡頭太長、動作太短**：3 秒的打擊鏡真正高速的時間中位數只有約 **0.62 秒**；剩下是起手前發呆（0.4–0.8 s）或打完定住（最長 0.9–1.8 s）。文戲說完停 ≤0.3 秒，接著切反應鏡或下一句（`talk_tail`），動作戲一停觀眾就覺得是慢動作。
2. **騰空的人水平飄浮**：被炸飛、甩上天的人同一個姿勢水平滑行 1.5–2 s，沒有往下掉的曲線；跟拍運鏡又把位移抵掉。
3. **提示詞沒有往快推**：打擊鏡沒有速度詞，還常帶運鏡。

不重跑就能改善的做法是**後製變速**：只動定住／蓄力／飄浮，撞擊瞬間與台詞維持原速。要根治就照下面〈提示詞面〉改寫後重跑。

## 規則（倍率）

| 類別（kind） | 倍率 | 怎麼判斷 |
|---|---|---|
| `frozen_head` 開頭凍結 | **剪掉**（speed 0） | 從第 0–2 幀起連續 ≥6 幀幀差 < 0.3（光流自動） |
| `windup` 起手延遲／蓄力 | 2–3×（預設 2.5×） | 主體運動第一次超過該鏡峰值 50% 前的時間 ≥ 0.4 s（自動） |
| `hold` 定住 | 2×；連續超過 1.2 s 用 3× | 主體運動 < max(峰值 20%, 6 px/幀) 連續 ≥ 0.5 s（自動） |
| `float` 騰空飄浮 | 1.8–2× | **光流抓不到**（主體與鏡頭一起移動），人看影格標 |
| `impact` 撞擊、`dialogue` 台詞 | 1× | 台詞保護區見下 |

- 倍率上限 3×；短於 0.25 s 的變速區段併回 1×，避免頻繁換速。
- **台詞保護區**一律 1×：segments 的 `speech_window`、`external_narration`、有台詞但沒有 speech_window 的整鏡；`--vad` 會再用 ffmpeg 偵測人聲，把與台詞窗重疊的人聲區併進來。人工補的保護區在 `protect[]` 加 `"manual": true`，重跑提案不會被洗掉。
- 音訊：1× 原音；加速區 `atempo`（WSOLA，不變調）；剪掉的區段音畫一起剪；接縫各 8 ms 淡入淡出。
- **原片永遠不覆寫**，變速版輸出 `videos/ramped/<段>.mp4`。

## 流程

1. **階段 6 收件、技術 QA 之後**：`python scripts/h3d.py motion --root . [--vad]`
   - 每段量光流（需 `opencv-python-headless`、`numpy`），逐幀寫 `videos/qa/motion/<段>.json`，逐鏡指標（active_s、longest_hold_s、onset_s、重複幀）寫 `videos/qa/motion/motion-report.json`。
   - 有變速區段的段**合併**寫進 `videos/speed-ramps.json`，`status: proposed`。
   - 已 `approved`／`rendered`／`skip` 的段、原片 sha 沒變就不動（`--force` 才重提）。原片換了（重跑 take）會整段換成新提案並記 `stale_from`——新 take 的動作結構可能完全不同，舊區段不能直接套。
2. **人審清單**（看影格條）：補 `float` 區段、修邊界、確認撞擊在 1×；確定後該段 `status` 改 `approved`。不要變速的段改 `skip`。
3. **產檔**：`python scripts/h3d.py ramp --root . [--segment <段>] [--dry-run]`
   - 只處理 `approved`；產檔前斷言原片 sha、區段連續、倍率 1–3×、台詞保護區 1×。
   - 產檔後驗證：回讀長度與規劃差 ≤ 2 幀；台詞保護區變速前後音訊相關係數 ≥ **0.98**（允許 ±50 ms 偏移）。不過就刪掉輸出、標 `verify_failed`。
   - 結果只寫回該段：`output`、`output_sha256`、`new_duration_s`、`delta_s`、`time_map`、`verify`，`status: rendered`。
4. **階段 7 組裝**自動吃變速版（清單在 `videos/speed-ramps.json` 時）：
   - `h3d assemble`（`assemble_episode.py`）：rendered 段改用 `videos/ramped/<段>.mp4`，台詞／旁白／外部配音的時間窗用 `time_map` 從原片秒換到變速版秒；段長改用變速版長度，後續段起點跟著平移。`--no-speed-ramps` 關掉、`--speed-ramps <檔>` 指定別的清單。
   - `h3d concat plan`（`concat_adapter.py`）：同樣換影片來源、換算字幕／ASR 對位／畫外配音落點，`total` 與 `episode_starts` 跟著縮短。`voice/muted/` 是從原片壓的，變速段不再使用；要壓原聲就對變速版重跑 duck。
   - 原片被覆寫（sha 和清單不符）時一律退回原片並警告，絕不拿舊 time_map 套新影片。

## 清單格式（`videos/speed-ramps.json`）

```json
{"schema": "ai-comic-drama/speed-ramps/1",
 "rules": {"frozen_head": 0, "windup": 2.5, "hold": [2.0, 3.0], "hold_long_s": 1.2, "float": [1.8, 2.0],
           "impact": 1.0, "dialogue": 1.0, "max_speed": 3.0, "protect_corr_min": 0.98},
 "segments": {"EP01-S03-b": {
   "status": "proposed|approved|rendered|verify_failed|skip",
   "source": "videos/EP01-S03-b.mp4", "source_sha256": "…", "fps": 24, "frames": 209, "orig_duration_s": 8.708,
   "protect": [{"start": 5.917, "end": 9.417, "why": "SH03 台詞", "manual": true}],
   "sections": [{"start_frame": 0, "end_frame": 16, "start": 0.0, "end": 0.667, "speed": 0,
                 "shot": "SH01", "kind": "frozen_head", "reason": "開頭 16 幀完全相同"}],
   "output": "videos/ramped/EP01-S03-b.mp4", "new_duration_s": 6.125, "delta_s": -2.583,
   "time_map": [{"src": [0.0, 0.667], "out": null, "speed": 0}, {"src": [0.667, 1.3], "out": [0.0, 0.633], "speed": 1.0}],
   "verify": {"protect_corr_min": 0.999, "threshold": 0.98}}}}
```

區段以**幀號**為準（秒數只是顯示）；`time_map` 由產檔腳本寫，不要手改。

## 提示詞面（重跑前就避免慢動作感）

寫在 `references/prompt-authoring.md`〈動作鏡怎麼寫才不慢〉：一鏡一個動作 2–2.5 s、速度詞、第一幀就在動、動作撐到切點、騰空寫下墜曲線（用 curve，不用 arc）、打擊鏡固定機位。

## 實測（《噩盡島》EP01–03，29 段）

- 7 段變速：266.1 s → 252.2 s（−13.9 s）；台詞保護區新舊音訊相關 0.979–1.000、偏移 ≤ 31 ms（< 1 幀）。
- 自動提案與人工清單對照：EP01-S03-b 自動抓到開頭 0–0.63 s 凍結（人工 0–0.67）與結尾 6.88 s 起定住 3×（人工 6.96）；1.3–3.0 s 飄浮要人工補。
- 光流量化方法與完整數據見噩盡島專案 `work/stage6/motion-audit.md`。
