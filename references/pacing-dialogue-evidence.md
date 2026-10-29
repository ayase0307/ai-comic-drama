# 語速與台詞量分配：數據出處

本檔只管語速與台詞量。鏡頭銜接不在範圍內。每個數字都附來源。查不到來源的數字一律標「未知」。

路徑縮寫：
- `R/` 指 `C:\Users\kirit\Videos\熱門影片分析\AI_Manju_Research\`，box 副本在 `/workspace/manju/research/AI_Manju_Research/`。
- `W08/` 指 `R/02_Work_Analysis/Work_08_Divorce_Daughter_DemonRealm/`，box 副本在 `/workspace/manju/research/other_film/Work_08/`。
- `ET/` 指 `/workspace/manju/validation/event_test/`。
- `GT/` 指 `/workspace/manju/validation/ab_h3/gen_test/`。

## 參考作品

| 指標 | Work_01 無盡之塔 | Work_08 和離後我帶女兒橫掃魔域 | 來源 |
|---|---|---|---|
| 男主語速（只算說話時） | 3.8–4.2 字/s | 3.6–4.0 字/s | `R/02_Work_Analysis/Work_01_Endless_Tower_S6/Audio_Dialogue.md:19`；`W08/Audio_Dialogue.md` §二 |
| 女角語速 | 4.5–5.0 | 前妻 4.2–4.8、師尊 4.8–5.2 | 同上 |
| 旁白／解說語速 | 5.2–5.8 | 未知 | `Work_01/Audio_Dialogue.md:21` |
| 句間停頓 | 男主 0.65–1.20s、女主 0.40–0.70s | 男主 0.80–1.40s、前妻 0.50–0.90s、師尊 0.30–0.60s | 同上 |
| 單句平均字數 | 9.4 字（爆款平均 9.2） | 男主約 11 字 | `Work_01/Audio_Dialogue.md:7`、`R/03_Cross_Work_Insights/Comparative_Report.md:14`；`W08/Audio_Dialogue.md` §一 |
| 平均鏡長（ASL，取樣段） | 5.0s（17 鏡，由 Shot_Timeline.csv 算出）；報告寫爆款平均 3.24s、目標 3.0–3.8s | 8.85s（13 鏡／115s，由 CSV 算出）；7 鏡超過 8s | 兩部的 `Shot_Timeline.csv`；`Comparative_Report.md:10`；`R/05_AI_Production_Skills/Skill_Modules/Pacing_and_Editing.md:7` |
| 有台詞鏡的比例 | 17/17 | 13/13 | 兩部的 `Shot_Timeline.csv` |
| 整段台詞密度（字數÷片長） | 2.64 字/s | 2.23 字/s（逐鏡 0.92–5.17） | 兩部的 `Shot_Timeline.csv` |
| 預停頓靜默 | 0.6–1.2s；超過 1.5s 觀眾會以為壞掉 | 和離台詞中段停 0.65–0.90s | `R/04_Technique_Library/Technique_Cards/TC_07_Sound_Drop_Silence_Before_Boom.md:23`；`W08/Audio_Dialogue.md` §三 |
| 開場鉤子 | ≤2.5s | 0–1.96s 快閃 | `TC_01_Visual_Hook_Opener.md:23`；`W08/Shot_Timeline.csv` S08-01 |

「約 80% 鏡頭有台詞」這個數字在報告裡找不到出處，標為未知。兩部取樣段實際都是 100%。

Work_08 的鏡頭偏長，但每鏡都有台詞。所以它不算「空跑」，是靠長句加上停頓撐滿。這個寫法和報告「超過 8 秒是死鏡」的說法互相矛盾。本 PR 不訂鏡長上限，只管台詞密度與空隙。

## 本專案實測

| 測試 | 片長 | 字數 | 整段密度 | 最大空隙 | 使用者評語 | 來源 |
|---|---|---|---|---|---|---|
| 事件 V0 | 23.33s | 61 | 2.61 | 1.20s | 太慢 | `ET/metrics_trial.csv` |
| 事件 V1 | 18.37s | 61 | 3.32 | 0.93s | **最舒服** | 同上 |
| 事件 V2 | 14.83s | 61 | 4.11 | 1.48s | 有跳感 | 同上 |
| R2-03（時間碼提前） | 7.29s | 27 | 4.10（只算說話時） | 0.66s | 未評 | `GT/metrics_round2.csv` |
| R2-01／02（只換 seed） | 7.29s | 27 | 3.91／3.83 | 1.82／1.24s | 未評 | 同上 |
| B（第一輪） | 7.29s | 27 | 4.43 | 1.30s | 未評 | `GT/metrics.csv` |

結論：空隙大是時間碼寫得太鬆造成的，換 seed 沒有用（R2-01／02 對照 R2-03）。

## 門檻怎麼來的

- **整段密度目標 3.0–3.6 字/s**：V1 是 3.32。WARN 線設在 V0（2.61）以上的 2.8，以及 V1 和 V2（4.11）之間的 3.9。
- **句間空隙**：WARN 設在 1.0s，因為 V1 的 0.93s 已被接受。FAIL 設在 1.5s，依據 TC_07，V2 的 1.48s 也已被評為會跳。
- **`beat_pause`**：0.6–1.2s，依據 TC_07。
- **單句長度**：建議 ≤18 字，依據 Work_01 最長 18 字。硬上限 35 字是專案規則。
- **未經本專案驗證的數字**：估時 4.5 字/s、TTS speed 1.1、說話佔比 60–75%，都沿用前一版補丁的社群數字。說話時的語速 4.5 落在 Work_01 和 Work_08 女角的區間內，但比兩部男主都快，所以男主估時建議改用 4.0。
