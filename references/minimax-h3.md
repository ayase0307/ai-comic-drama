# MiniMax H3 提示詞專章（入口）

MiniMax H3（即 Hailuo 3）是**全模態影視生成模型**，有官方規定的提示詞格式，**不能套用通用公式**。

> 核心觀念：**H3 prompt 是隨時間變化的規格，不是畫面描述。** 每句話對應看得到或聽得到的事件，並說清楚在第幾秒。

## 規格

| 項目 | 值 |
|---|---|
| 時長 | 4–15 秒 |
| 解析度 | 最高 2K |
| 音訊 | 原生立體聲，音畫同步（口型對上台詞） |
| 幀數 | 15 秒 ＝ 362 幀、8 秒 ＝ 192 幀（只有 8 秒落在整秒），需符合 `17k+5` 幀網格 |
| 解析器 | prompt 由 **Qwen3-VL-32B** 解析，**不是 CLIP** → SD 風 `(token:1.2)` 權重語法無效，要改寫成敘述句 |
| 參考素材上限 | ≤ 9 圖 / ≤ 3 影片 / ≤ 3 音檔，**總數 ≤ 12**；影片與音檔各 2–15 s、總 ≤ 15 s；音檔不能單獨使用 |

## 四種模式

| 模式 | 素材 | 說明 |
|---|---|---|
| `T2VA` | 無圖 | 純文字建構完整影音時間線 |
| `I2VA` | 首幀 1 張 | 從首幀向前發展 |
| `FL2VA` | 首 + 尾 | 描述首尾之間的連續路徑（**偏好單一 shot**） |
| `L2VA` | 僅尾幀 | 推導合理的前序狀態，收束到尾幀 |
| `Ref2VA` | 全能參考 | 圖片／影片／音訊混合，**六段式** |

**模式選錯，提示詞再精緻也失效。** 寫之前先確定模式。

## 兩個格式家族

- **基礎模式（T2VA / I2VA / FL2VA / L2VA）**：對齊指令（圖生類才有）＋ **三欄** `integrated_multimodal_description` / `overall_soundscape` / `non_diegetic_music`。
- **全能參考（Ref2VA）**：**六段式** `subject_definitions` / `summary` / `retention_analysis` / `detailed_description` / `overall_soundscape` / `non_diegetic_music`。

**完整格式（欄位原文、運鏡詞表、`<d>`／`<scenetrans>`／`<cutoff>` 標籤、畫內文字寫法）見 `h3/prompt-formats.md`（四種格式決策表）；欄位原文以官方 repo 為準。**

## 預算表（社群實測上限）

| 項目 | 上限 | 超過會怎樣 |
|---|---|---|
| 每個 shot 主動作 | 1 個（含起手→接觸→收勢） | 動作被壓縮、糊成一團 |
| 每個 shot 長度 | ≥ 2 s；對白 shot ＝ 台詞朗讀秒數 + 反應 | timestamp 太密是最常見的結構失敗 |
| 10 s 內 shot 數 | 3–4；15 s 內 4–6 | 幻燈片感、動作沒做完 |
| 每個 shot 運鏡 | 1 個（類型 + 幅度 + 速度 + 落點） | 鏡頭亂飄或幾乎不動 |
| 對白 | 15 s 約 20 英文字；每句約 10 字；**一個 `<d>` 一句** | 語速趕、口型壞、亂語 |
| 重要角色 | ≤ 3 | 身份漂移、錯人說話 |
| 慢動作 | 獨立 shot，背景動態元素減到最少 | 抖動、閃爍 |
| 純文字 prompt | 300–700 英文字（社群經驗值，官方無此數字） | 太短＝沒東西可參考 |
| 有參考素材時 | 字數要縮，**只寫新變化** | 文字與圖片互搶，臉會變 |

## 十條速查

1. **動作寫軌跡**：起始狀態 → 哪隻手／哪個方向／多快 → 結束狀態。
2. `first / then / as / finally` **鎖順序**；沒連接詞 H3 當同時發生。
3. **每個素材一個職責**，並寫它**不**負責什麼。
4. **卡點寫觸發物**（bass hit、刀刃接觸聲、落地），不寫 energetic。
5. **運鏡用官方詞 + 落點**，寫在動作句裡；環繞寫 `truck left + pan right`。
6. **速度用形容詞**；同一 shot 不混 slow 與 rapid；慢動作獨立降熵。
7. **聲音三層各歸其位**；音效寫兩次；配樂寫進出時間；不要就 `non_diegetic_music: N/A` 且全文無音樂情緒詞。
8. **不說話用正向句 + 持續動作**；不寫「看鏡頭」；**不要在 prompt 裡寫「不要字幕」**。
9. **要可讀的字逐字打出加引號**；沒打的字會變噪音。
10. **一鏡到底就沒有 `[Shot 2]`**；切鏡每次帶新資訊；**轉場寫成事件**。

## Red Flags：看到就停下重寫

- 兩個 shot 差不到 2 秒；一個 shot 三個以上動作
- `cinematic / epic / dynamic / high quality` 沒有物理描述
- 慢動作 shot 裡有大雨、飛葉、群眾
- 寫了 orbit／環繞；一個 shot 兩個運鏡
- 上傳素材沒寫職責；或每個 shot 重述參考圖外觀
- 同時要一鏡到底和切鏡；同時要配樂和不要 BGM
- 台詞兩句塞一個 `<d>`；3 秒 shot 講一段話
- 代名詞或場景與照片不符（會中途換人）
- 「HUD elements」「some labels」沒逐字打出

## 本專案既有定版（優先套用）

**守富定版三段式骨架**：`【鏡頭——賣點】` → `【光線——色調】` → `【皮膚——通透白皙有真實肌理】`（**皮膚段整段照抄**）。

> 適用範圍：**寫實／半寫實風格**。2D、水墨、Q 版、美漫等非寫實風格不用皮膚段（見 `SKILL.md` 原則 7），改照 `h3/scenarios-world-and-styles.md`。

- 完整原文（含 H3 散文版）見 **`h3/skin-realism-block.md`**。
- 前兩段依場景改寫；皮膚段只微調光色字眼。
- 搭 fal `MiniMax-H3-Realism-People-LoRA` 時，`r34l1sm` 放 prompt 最開頭。

## 檔案索引

### 核心（每次都會用到）

| 你要做的 | 讀 |
|---|---|
| 選格式：官方三欄／六段式／中文三段／社群區塊式；對齊句、參考檔上限 | `h3/prompt-formats.md` |
| 套用**守富定版**皮膚段骨架 | `h3/skin-realism-block.md` |
| 讓動作有重量、材質有回應、表情有意圖（含慢動作、動畫風格規律） | `h3/motion-quality.md` |
| 排節奏、卡點、時間軸、速度詞 | `h3/rhythm-and-pacing.md` |
| 人物動作拆解、打鬥一拍公式、多對一 | `h3/action-choreography.md` |
| 生成結果不對，查症狀與修法；送出前 8 問、迭代策略 | `h3/failure-triage.md` |
| **寫完 prompt 必跑**：跨 shot 變化四軸、spec 卡、能量曲線、送出前自檢（每個 shot 都對卻整支單調） | `h3/shot-variety-and-staging.md` §10 |

### 情境庫（挑最接近的一到兩個來讀）

| 你要做的 | 讀 |
|---|---|
| 對白短劇★、UGC 口播、唱歌 MV、舞蹈、**打鬥**★、跑酷追逐、喜劇、情感特寫、懸疑偽紀實、vlog、POV/FPS、**旁白數位人**★、真人照片動畫（★＝漫劇常用） | `h3/scenarios-people.md` |
| 空鏡 B-roll、自然天氣、動物、車輛追逐空拍、手機偽紀實、**2D anime**、3D 卡通、黏土紙藝、手繪實拍融合、動態圖形、變身 VFX、無縫循環、角色設定板、綠幕重打光、多素材混剪 | `h3/scenarios-world-and-styles.md` |
| 產品 hero、開箱示範、液體食物、品牌片、時尚美妝、logo 片頭字卡、UI/遊戲選單、電商帶貨、工業機器人、建築旅遊 | `h3/scenarios-commercial.md` |

### 進階

| 你要做的 | 讀 |
|---|---|
| 鏡頭語言：運鏡詞表、景別鏡頭角度、各類型預設鏡頭、切鏡、轉場寫成事件、手持感、運鏡動機、rack focus | `h3/camera-and-transitions.md` |
| 聲音：三層音軌、對白預算、speaker 格式、表演方向、聲音參考、字幕、音效同步、配樂（含音訊規則索引） | `h3/audio-and-dialogue.md` |
| 聲音一次到位、跨片段鎖音色、情緒表演 vs 外部 TTS、必須配音時避開口型、Openverse 後製音效與 ffmpeg 混音 | `h3/audio-pipeline.md` |
| 光影配色、跨鏡頭色彩一致、角色重打光防貼紙；色彩 QA 腳本 `scripts/color_qa.py` | `h3/lighting-and-color.md` |
| 素材分工、動作／運鏡／表演遷移、影片編輯、續接、首尾幀與循環、真人照片 | `h3/references-and-editing.md` |
| **長片分段規劃**（30–60 秒以上、路線選擇、幀數網格、接點載體、分鏡表模板） | `h3/long-form-planning.md` |
| 完整改寫範例：10 秒打鬥、spec 卡→三欄 prompt、Seedance 時間碼→H3 Ref2VA | `h3/example-fight-10s.md`、`h3/example-spec-to-prompt-10s.md`、`h3/example-seedance-to-h3.md` |
| 各條規則的來源與可信度（官方／社群實測／方法主張） | `h3/community-sources.md` |

## 放進漫劇流程

1. **分鏡階段**：`integrated_multimodal_description` 幾乎就是分鏡表的「畫面＋運鏡＋台詞」欄位，可直接對應。
2. **生成階段**：
   - 已有分鏡圖 → `I2VA`（首幀）或 `FL2VA`（首尾幀）。
   - 尚無圖、想快速試片 → `T2VA`。
   - 有角色參考圖 + 運鏡參考片 → `Ref2VA`，逐一交代素材分工。
3. **聲音**：`sfx` → `overall_soundscape`；BGM → `non_diegetic_music`；旁白／對白用 `<d>` 寫進 `integrated_multimodal_description`。
4. **時長**：H3 支援 4–15 秒，比分鏡表預設的 2–6 秒寬鬆——可把相鄰短鏡合併成一段生成，再剪開。
5. **生成後不對 → 先查 `h3/failure-triage.md` 再改**，不要盲目重抽；寫完整集 prompt 後跑 `h3/shot-variety-and-staging.md` §10 自檢。

## 回寫欄位

```json
{
  "shot_id": "S01-001",
  "video_model": "MiniMax H3",
  "video_params": { "mode": "I2VA", "seconds": 8, "resolution": "2K", "aspect_ratio": "9:16" }
}
```

## 來源與致謝

- **官方**：`MiniMax-AI/MiniMax-H3` → `skills/h3-prompt-writing`（欄位名、對齊指令、`<d>` 標籤、Ref2VA 六段式）。**格式以官方為準。**
- **實戰整理（以此為準）**：[`ayase0307/h3-video-prompting`](https://github.com/ayase0307/h3-video-prompting)（MIT）— `references/h3/` 即其 `references/` 的同步版，檔名一致；兩邊有出入以該 repo 為準。同步紀錄見根目錄 `memory.md`。
- 本專案僅整理規則與寫法，範例為重寫；第三方 prompt 與文章版權屬原作者。
