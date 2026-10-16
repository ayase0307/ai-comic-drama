# H3 動作品質與節奏

## 一、動作弧線：起手 → 執行 → 接觸 → 收勢

一個「動作」有四段。**只寫中間那段，模型會自己補前後，常補錯。**

| 段 | 寫什麼 | 範例 |
|---|---|---|
| 起手 anticipation | 重心轉移、蓄力、視線先到 | `she plants her left foot and drops her weight before the swing` |
| 執行 commitment | 肢體路徑、方向、速度形容詞 | `the right arm sweeps across her body at explosive speed` |
| 接觸 impact | 碰到什麼、反作用 | `the flat of the blade meets the knife with a sharp ring; her wrist absorbs the shock` |
| 收勢 settle | 多餘動量怎麼消、回到什麼姿勢 | `the momentum carries her half a step forward before she resets her stance` |

**動作意圖詞彙**：`setup, anticipation, commitment, impact, brake, settle`
**動畫表演詞彙**：`squash-and-stretch, anticipation, overshoot, follow-through, overlap, arcs, clear silhouette`

## 二、重量與動量

- **寫重心**：`weight drops onto the left knee`、`leans into the wind`、`shifts his weight forward, then jumps`
- **寫慣性**：`lands with bent knees, rolls over one shoulder, and rises into a sprint without pausing`
- **車輛**：`real weight in the lean`、`tires smoking`、`continuous forward velocity throughout`；轉向寫 `drifts through the final bend`，不要寫「帥氣過彎」
- **動物**：寫步態與觸地順序 — `steps cautiously onto a wet rock, shifts its weight forward, then jumps`

## 三、環境與材質要「回應」動作

每個主動作配**一個**環境反應，**寫因果不寫形容詞**。

| 材質 | 可寫的回應 |
|---|---|
| 水／液體 | `water sheets down the faceted sides and splits at each edge`、`condensation streaks down the glass` |
| 布料 | `the jacket rides up`、`coat and scarf stream behind him`、`heavy wool snaps once as it is shaken open` |
| 頭髮 | `wind lifts her hair once`、`a strand shifts near her temple` |
| 粒子 | `dust lifts where the foot pivots`、`powder drifts down through the frame` |
| 光 | `a narrow highlight travels across the brushed metal` |
| 硬物 | `the chocolate bar snaps cleanly along a scored line`、`cracks spread as fragments slide outward` |

> 不要堆疊無關效果來「顯得細」。**一個主動作 + 一到兩個回應。**

## 四、手與物件互動（最容易壞）

規則：**哪隻手、握哪裡、動到哪、放哪裡。**

```text
✅ She reaches forward with her right hand, grips the bottle around the upper third,
   lifts it to chest height, and rotates it until the label faces camera.
❌ she picks up the bottle / she opens the box
```

- **精細手指動作**（穿針、打字、彈琴）是弱項 → 改中景 + 短時間，或用參考影片遷移。
- 產品在手上：`preserve hands/product contact`、`keeps the label square to camera`。
- 不要讓產品做變形動作（除非是賣點），並要求「部件對齊、數量守恆、最終復位」。

## 五、臉部表演：寫意圖，不寫情緒清單

- 「nervous」不如「**試圖掩飾緊張**」：`Daniel tries to sound casual, but hesitates before replying`。
- 一句話配 **2–3 個相關線索**，不要五種情緒疊一起。
- 微表情用具體動作：`a brief eyebrow lift`、`eyes drop, then meet the camera again`、`starts to answer, then stops`。
- **聽的人也要演**：`holding or breaking eye contact, a quiet breath, tightening a grip`。
- **靜止也是表演**：緊張戲少動作比大動作可信。

## 六、口型與說話品質

- 說話時鏡頭少動：`locked camera, no head turns while speaking`
- 防橡皮嘴：`realistic lip articulation, no exaggerated mouth opening`
- 說完要收：`exactly as his voice stops, his lips settle closed and he exhales through his nose`
- **每個 shot 都要有事做，尤其最後一個**——對白會擠在 shot 開頭，最後一個 shot 沒動作就變 dead air

## 七、時間軸是 prompt 的骨架

- **沒寫時間軸 ＝ 一個動作被拉長到整段時長，第 7 秒模型沒事做。**
- 本地／開源格式：`[Shot N] At MM:SS.mmm`（嚴格遞增、落在時長內）。
- 平台自然語言可用 `[0–3s]` 區塊。兩者都是「編輯大綱」，H3 對切點遵從度高但**不保證幀精確**。
- **時間依資訊量分配，不平均分**：10 s → 0–3.3 建立 / 3.3–6.9 衝突 / 6.9–10 落點。
- 15 s 建議 3 段（0–5 / 5–10 / 10–15），每段一個動作一個運鏡；短片 5–6 s 只放一拍。

### 每個 shot 的最短長度

- 最常見的結構失敗：**timestamps spaced too tightly** 與**對白塞不進 shot**。
- 經驗值：非對白 shot **≥ 2 s**；有台詞的 shot ＝ 把台詞用預期語速唸出來的秒數 **+ 前後反應**。
- 12 個英文字約 5 秒。**一個 3 s shot 講一大段話，口型必壞。**

## 八、卡點要寫觸發物

「energetic editing」不可審查；「cut on the downbeat at 3.0 s」可以。

| 想要的效果 | 寫法 |
|---|---|
| 隨節拍硬切 | `每次 bass hit 觸發場景硬切或景別硬切` |
| 文字跟拍 | `每個 snare 時文字突然放大、抖動、掃描錯位` |
| 微顫 | `hi-hat roll 時字母邊緣高速細碎震動` |
| 重音壓屏 | `808 bass 砸下，文字瞬間縱向壓縮後回彈` |
| 收尾 | `最後一拍所有場景碎片同步凍結，hard cut to black` |
| 無音樂的動作片 | `每次刀刃接觸的金屬聲當下切到下一個景別` |

**對應關係**：hi-hat roll → 微抖／跳幀；snare → 放大／硬切／肩膀下沉；808 bass hit → 低頻壓縮／拉伸／位移。切點落在 1/4 或 1/8 拍格。

## 九、速度：形容詞優於數字

- 模型不解讀「3 秒 pan」「5 mph」；解讀 `leisurely / steady / brisk / languid / explosive`。
- **一個主時間形容詞 + 一個運鏡動詞**：`a leisurely crane up` 比 `crane up slowly` 穩。
- **Contradiction Trap**：同一 shot 不混 slow 與 rapid（「慢推鏡 + 快速流雲」會卡頓）。
- H3 開源格式的速度詞是 `at slow speed`／`at fast speed`，幅度是 `with small/large amplitude`。

## 十、慢動作

- 慢動作**獨立 shot**，背景**降熵**（大雨→細雨、狂風→微風、拿掉人群）。
- 慢動作 shot 內的聲音也要慢：`the rain and metal contact stretch into a low, drawn-out scrape`
- 一個 shot 內**不寫**「先慢後快」；真正的 speed ramp 用兩次生成 + 剪輯 optical flow。
- 高速用有方向感的詞：`streaking, motion blur, dynamic thrust`；低速用 `leisurely, languid, steady`。

## 十一、動畫風格的動作規律

| 風格 | 動作要求 | 禁止 |
|---|---|---|
| 3D 卡通 | 誇張彈性：squash/stretch、anticipation、overshoot、快速換 pose、清楚剪影 | 寫實肌肉感 |
| 2D anime | 一個 shot 一個 held beat；描述繪製方式 `flat cel shading, two-tone shadows, clean dark linework, limited animation timing` | `volumetric god rays, shallow depth of field`（會拉向 3D） |
| 黏土／定格 | 手指痕、霧面、微縮景深；關節動作有限 | 流暢寫實動作 |
| 紙藝／拼貼 | 層次紙邊、切痕、翻摺；動作是放置、撕、滑、疊 | 3D 立體感 |
| 手繪＋實拍融合 | 說清哪層是實拍、哪層是線條；線條要與實體表面互動 | 恐怖化、撲咬、憑空切鏡 |

## 十二、身份與臉在動作中不掉

- **臉越小越難保持**；關鍵情緒拍轉中景／特寫，或「wide shots use back view / rear three-quarter; never a distant frontal face」。
- 有參考圖時，**全局宣告一次不變量**，分鏡內只寫新變化；每個 shot 重述外觀會讓文字與圖片互搶。
- **快速動作讓幾何解析變差**；臉部要清楚的 beat 不要同時是最快的 beat。
- 多角色：**每個角色一個穩定稱呼**（名字或「the man in the grey henley」），全篇不換說法。

## 十三、多段拼接（> 15 s）

1. 鎖一條 master audio。
2. 拆成 2–5 s 的 4–8 個 shot，對齊歌詞時間戳與鼓點。
3. 同場景用**上一段尾幀當下一段首幀**；硬切則用同方向運動或遮擋接。
4. 剪輯時全部對回 beat grid，必要時 speed ramp。

**Hero Template**：先生成最重要的 hero clip，抽出它有效的節奏詞（如 `languid tracking shot`），後續每個 clip 保留同樣節奏詞只換主體與場景，避免拼接後 tonal whiplash。
