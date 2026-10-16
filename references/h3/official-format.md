# H3 官方格式（權威）

來源：MiniMax 官方 repo `MiniMax-AI/MiniMax-H3` → `skills/h3-prompt-writing/references/base-en.txt`、`ref-en.txt`。
**欄位名、段落順序、標籤寫法、時間標記一律照抄，不要自創。**

## 一、四種模式與對齊指令

| 模式 | 素材 | 對齊指令 |
|---|---|---|
| `T2VA` | 無圖 | **無對齊指令**，直接從三個核心欄位開始 |
| `I2VA` | 首幀 1 張 | `For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.` |
| `FL2VA` | 首 + 尾 | `How the reference pictures align with the target video — Picture 1 (from Shot 1) aligns with the 0.00-second mark of the target video; Picture 2 (from Shot N) aligns with the S.SS-second mark of the target video.` |
| `L2VA` | 僅尾幀 | `How the reference pictures align with the target video — <Picture 1> (from [Shot N]) aligns with the S.SS-second mark of the target video.` |

- `N` ＝ 實際最後一個 shot 的編號；`S.SS` ＝ 有效時長，**固定兩位小數**。
- 對齊指令必須是**第一行**，之後**空一行**才進核心欄位。

## 二、三個核心欄位（順序固定）

```text
integrated_multimodal_description: [Shot 1] ...

overall_soundscape: ...

non_diegetic_music: ...
```

| 欄位 | 寫什麼 |
|---|---|
| `integrated_multimodal_description` | 沿時間線描述：畫面、動作、鏡頭、說話者、對白、歌唱、**同期聲**。主體。 |
| `overall_soundscape` | 1–4 句英文，概括全片環境聲、物理動作聲、非語音人聲。**對白／歌唱／畫內音樂不重複寫這裡。** 全片靜音才寫 `N/A`。 |
| `non_diegetic_music` | 1–3 句英文，只寫**劇中人聽不見、只有觀眾聽得見**的配樂。寫樂器、速度、節奏、動態變化；**禁用抽象情緒詞**，也不要解釋配樂的情感功能。無則 `N/A`。 |

> 歌唱、樂器、收音機／電視／手機發出的音樂屬於**畫內事件**，寫進 `integrated_multimodal_description`，不是 `non_diegetic_music`。

## 三、integrated_multimodal_description 寫法

### 3.1 開頭先定風格與初始構圖

`[Shot 1]` 開頭就寫整體風格與初始構圖。官方常見風格詞：`Cinematic`、`live-action`、`2D-animated`、`3D CG`、`claymation`、`watercolor`、`vintage film`。

- 關鍵幀模式：風格**從參考圖推導**。
- T2VA：風格**從使用者文字選定**。

```text
[Shot 1] Live-action, cinematic, a medium-wide shot frames...
```

### 3.2 Shot 與切點

- **第一個 shot 不加時間戳。**
- 後續 shot 用遞增編號，並以**嚴格遞增、落在時長內**的切點時間開頭：

```text
[Shot 2] At 00:03.500, the camera cuts to...
```

- 一般切鏡用：`the camera cuts to` / `the shot cuts to` / `the shot transitions to` / `the shot changes to` / `the shot switches to`。
- 使用者明確要求時才用 cross-dissolve / fade / wipe。
- **切鏡必須帶新資訊**（主體、空間、狀態、視角或時間）。只是遠近或輕微角度變化 → 優先用運鏡，不要切。

### 3.3 運鏡：類型 + 幅度 + 速度

| 維度 | 官方用詞 |
|---|---|
| 類型 | `Zoom In / Zoom Out`（焦距變、機身不動）、`Push In / Pull Out`（機身前後移）、`Pan Left / Pan Right`（原地水平轉）、`Truck Left / Truck Right`（水平平移）、`Tilt Up / Tilt Down`（原地垂直轉）、`Pedestal Up / Pedestal Down`（整機升降）、`Arc Shot`（繞主體弧線）、`Tracking Shot`（跟隨移動物）、`Static Shot`（完全靜止）、`Shake Slightly / Shake Strongly`、`POV`、`Roll Clockwise / Roll Counterclockwise` |
| 幅度 | `with small amplitude` / `with large amplitude` |
| 速度 | `at slow speed` / `at fast speed` |

中等幅度與正常速度通常**省略不寫**。

**寫法**：當成句子裡的自然動作，**不要**在句尾堆標籤。

```text
The camera pushes in with small amplitude at slow speed toward the folded letter in her hands.
The camera pans right with large amplitude at fast speed, revealing the open doorway.
The camera holds a static shot as the runner exits the frame.
```

### 3.4 說話者、對白與歌唱

- 會說話／唱歌／發出畫外人聲的主體，用穩定 ID：`(S1)`、`(S2)`。多人齊說用複合 ID `(S1,S2)`。
- **同一說話者跨 shot 保持同一 ID**；從不發聲的角色**不給** speaker ID。
- 說話者首次出現時，先用視覺與聽覺線索建立穩定身份：角色類型、年齡、性別、是否在畫面內、音高、音色、語速、口音。
- **辨識語、ID、動作、表演方式寫在 `<d>` 外面**；`<d>` 內**只放語言標籤與使用者原話**。
- 原文**逐字保留，含標點**，不翻譯、不改寫。

```text
The young woman with a quiet, breathy voice (S1) says: <d>[English] I get off at the next station.</d>
The two children (S1,S2) shout together, <d>[English] Wait for us!</d>
```

**畫外音**：用固定片語 `says in an off-screen voiceover`，並在每個畫外音 `<d>` 之後**立刻**聲明對應的畫內角色**嘴唇保持閉合**：

```text
The man (S1) says in an off-screen voiceover: <d>[English] I still remember that road.</d> while his lips remain completely closed.
```

**跨切點的台詞**：在兩側連接點加 `<scenetrans>`，並明說音訊跨切點延續。可用的延續表述：`continues seamlessly across the cut`、`continues uninterrupted into the next shot`、`carries over from the previous shot`、`remains audible across the transition`。
被片尾截斷用 `<cutoff>`。

### 3.5 畫內文字

畫面上實際可見的橫幅、招牌、標籤、字幕、霓虹字，用**英文雙引號**包住，原文與標點逐字保留、不翻譯。

```text
A red neon sign reading "营业中" glows above the doorway.
```

## 四、Ref2VA（全能參考）六段式

Ref2VA 依序使用六個段落，**參考標籤在所有段落中保持一致**：

```text
subject_definitions:
summary:
retention_analysis:
detailed_description:
overall_soundscape:
non_diegetic_music:
```

參考標籤格式：`<Picture 1>`、`<Video 1>`、`<Audio 1>`（**保留英文與尖括號**）。

完整標籤規則、retention analysis 與範例見官方 `references/ref-en.txt`。

## 五、輸出規則（官方）

- 改寫段落用**英文**寫；對白、歌詞、畫內文字**保留原語言**。
- 每個 shot 要描述：構圖、主體、環境、動作、鏡頭、聲音，以及**被參考內容出現的確切時間點**。
- **避免**：劇情摘要、未解析的參考標籤、與請求時長不符的時間標記。
- 描述的總時長必須**對上請求的影片長度（4–15 秒）**。
- 用具體的視覺與聽覺細節，**不要**用 `cinematic`、`beautiful` 這類抽象詞。
- 用關鍵幀（I2VA / FL2VA / L2VA）時，明確說明首幀／尾幀**如何對應到時間線**。
