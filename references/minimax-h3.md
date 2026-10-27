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
- 提示詞出現沒有參考圖的人群描述（tourists／crowd／群眾／路人）
- 提示詞出現第二個人，但該段只有一張臉參考圖
- 畫面出現多視圖板（四視圖板／表情板）當參考圖，且**沒有**宣告 `reference_view: "panel"` ＋ `panel_label_en`
- 提示詞提到音色參考卻沒掛 `<Audio N>`／沒綁音色母帶（`subject_definitions` 缺 `<Audio N> is the voice-timbre reference for <Subject N> (Sx).`）
- `<d>` 沒有 `(Sx)` 說話人代號

## 本專案既有定版（優先套用）

**守富定版三段式骨架**：`【鏡頭——賣點】` → `【光線——色調】` → `【皮膚——通透白皙有真實肌理】`（**皮膚段整段照抄**）。

> 適用範圍：**寫實／半寫實風格**。2D、水墨、Q 版、美漫等非寫實風格不用皮膚段（見 `SKILL.md` 原則 7），改照 `h3/scenarios-world-and-styles.md`。

- 完整原文（含 H3 散文版）見 **`h3/skin-realism-block.md`**。
- 前兩段依場景改寫；皮膚段只微調光色字眼。
- 搭 fal `MiniMax-H3-Realism-People-LoRA` 時，`r34l1sm` 放 prompt 最開頭。

---

## 負面詞 → 正面描述轉換表（H3 物理消除法）

MiniMax H3 的文字理解器為 **Qwen3-VL-32B**，不支援 Negative Prompt。若在 Prompt 中寫入否定詞（`no / without / avoid / non-`），會觸發大模型的先驗白熊效應（越說沒有越會畫出來）。所有禁止事項必須**改寫為對立的正面物理狀態**：

| 想要避免的事項 | ❌ 錯誤寫法（必激發噪點） | ✅ 正確改寫（正面描述物理狀態） | 物理原理解釋 |
|---|---|---|---|
| 不要流血、無傷 | `no blood, without injury, uninjured` | `the skin remains intact and clean, pristine complexion` | 描述完整、無瑕疵的皮膚肌理 |
| 武器不穿模、無形變 | `no clipping, weapon does not bend` | `the blade maintains a rigid straight steel line, solid metallic form` | 描述剛性、筆直的金屬實體幾何 |
| 衣服無破損 | `without tear, no ripped clothes` | `the fabric remains neat, smooth and perfectly intact` | 描述平整、連續的布料紋理 |
| 畫面無文字、無浮水印 | `no text, no visible text, no watermark` | `plain unmarked background, clean visual frame, empty pristine surface` | 描述純淨無標記的畫面材質 |
| 不要背景路人 | `no pedestrians, without background crowd` | `completely deserted empty alley, isolated solitary space` | 描述空曠荒蕪的場景環境屬性 |
| 嘴巴不要張開、閉嘴 | `no speaking, don't open mouth` | `lips remaining completely closed, jaw relaxed in silence` | 描述唇部緊閉與下顎閉合姿態 |
| 不要多餘手指 | `no extra fingers, normal hands` | `five distinct articulated fingers gripping firmly` | 具體描述五指分明的握持幾何 |

---

## 8GB VRAM OOM 拆段公式與 `17n+5` 幀格取整

在消費級顯卡（如 RTX 4060 Ti 8GB）本機運行 FreeVideo 時，顯存容量是物理硬邊界：

1. **OOM 處置鐵則**：**嚴禁降解析度**（降解析度會造成線條模糊與畫風坍塌退化）！唯一正確解法是**「在既有硬切點（Hard Cut）處拆成兩個獨立 Job」**。
2. **幀格整數約束（`17n + 5`）**：
   H3 的時空卷積層要求影格數嚴格符合 $F = 17n + 5$（24fps 下，4 秒 = 107 幀、8 秒 = 192 幀、15 秒 = 362 幀）。
   拆段秒數計算公式：
   $$F = \text{round\_to\_17n\_plus\_5}(s \times 24)$$
   $$s_{\text{actual}} = \frac{F}{24}$$
3. **拆段末切點安全公式**：
   若一段規劃總長度為 $D$ 秒，在第 $T_{\text{cut}}$ 秒處切開，**第二段長度必須滿足**：
   $$D - T_{\text{cut}} \ge 2.0\text{ 秒} \quad (\text{且取整後 } s_{\text{part2}} \ge 4.0\text{s})$$
   若 $D - T_{\text{cut}} < 2.0$s，該切點無效，必須往前一個鏡頭交接點切！
4. **拆段光照繼承鐵律**：
   拆成兩個獨立 Job 後，第二個 Job 開頭若缺失場景光源描述，H3 會重新隨機打光導致色溫突變！
   **拆段後第二段若缺光源名詞，必須強制補齊場次全域光源句（如 `Global lighting: cool moonlight from top-left`）**。

---

## Windows + FreeVideo 工程坑速查表（1–11）

| # | 陷阱名稱 | 症狀與報錯 | 根本原因 | 根治解法 |
|---|---|---|---|---|
| 1 | **References 與 First/Last 互斥坑** | HTTP 422 `Unprocessable Entity` | FreeVideo 後端不允許同時傳入 `references` 陣列與 `first_frame` 或 `continue_from` | **主力定案獨立 Ref2VA**：嚴禁傳入首尾幀；若走 I2VA 則 references 必須為空，二者絕不可共存！ |
| 2 | **Windows 路徑反斜線轉義坑** | 找不到檔案、路徑被截斷 | JSON payload 中包含 `E:\MinimaxH3\...`，`\` 遭 JSON 解析器轉義成無效字符 | 所有本地素材路徑一律使用正斜線 `/`（如 `E:/MinimaxH3/ai-comic-drama/...`），或以代碼規範化轉義 |
| 3 | **8GB VRAM OOM 崩潰** | `CUDA out of memory` / 進程瞬間退出 | 單次生成秒數過長（>10s 且帶多素材），或後台殘留顯存 | 嚴守「每段 7–10 秒」分段鐵律；OOM 時依上述公式在硬切點拆成兩個 Job，重啟後端釋放殘留 VRAM |
| 4 | **ASR 中文發音模糊吞字** | 人聲含糊不清、ASR 置信度僅 0.43–0.54、偶發 -40dB 靜音 | H3 原生中文語音模型權重較低 | 階段 7 啟動**配音分層方案 A**：保留 `<d>` 當口型時間錨，成片抽離 H3 人聲，改用外部 TTS 重配後混入 |
| 5 | **多角色平均化「撞臉」坑** | 三個角色同框全部長成同一張大眾臉 | 同時餵入多張體型相近的角色設定圖，模型自注意力特徵混淆 | Ref2VA：程式預設單人裁切（`face_subject_ids`／`--max-char-refs` 1），群戲時確保角色特異性視覺錨點極度鮮明；「一段一張臉」已不是通則（D3），多人同框改用 remix 角色卡（`references/consistency.md` §7.1） |
| 6 | **正面特寫「背後出怪」景深陷阱** | 角色大特寫時，肩膀後面突然長出怪物頭部 | 特寫鏡頭 Prompt 描寫了「遠處的怪物」 | 正面特寫 Prompt **絕不描寫遠處主體**！地理與空間由前導背影段建立，特寫純寫面部微表情 |
| 7 | **首幀與 H3 畫風割裂坑** | 影片畫面跟前後片段風格完全不搭、強烈塑膠感 | 誤用 Qwen/GPT 生成的首幀與 H3 Ref2VA 混剪（未並排對照） | 嚴禁混用！主力定案一律走獨立 Ref2VA；若要用首幀必須全片統一模型並排比對過審 |
| 8 | **無參考圖的第二張正臉（2026-10-19 實測，n=2，方向性）** | 單圖段落只要提示詞提到對方，4/4 段都會畫出第二人，且是唯一那張圖的複製臉；拆段後說話者還可能錯邊 | 每段預設只掛 1 張角色圖，配角只有文字描述 | 過肩鏡（只露配角肩背）最穩：2/2 只露一張臉、最像本人；要配角正臉就另開一段並掛其圖。外型差異大的兩人掛 2 圖同框未混臉（n=1）；「寫成正反打」不保證拍成單人 CU（2/3 拍成雙人側面），需逐支看片（三定律與門禁對照見 `references/consistency.md` §7.4） |
| 9 | **無參考圖的「第二個人」→ 複製臉（2026-10-19 實測 n=4，4/4 命中）** | 提示詞提到對方卻沒給對方參考圖，畫面就長出第二個人，而且那張臉是唯一那張參考圖主角的複製臉；刪掉參考圖等於把對方的身分送給主角 | 段內只有一張可辨識人臉參考圖，H3 沒有第二個身分可用，只能複寫唯一身分（Vera 論文：subject confusion／attribute swapping／excessive copying of reference-specific appearance cues【社群/論文】） | 每個重要角色（含背影、側身）都掛自己的參考圖（stage5 `identity_anchor_ids`）；純文字配角一律寫成不可辨識剪影或移出畫面；門禁 E19／E21，見 `references/consistency.md` §7.4 |
| 10 | **完整三視圖／表情板當參考圖 → 背景長出同款複製人** | 背景突然多出幾個穿著與參考板相同衣服、長著同一張臉的人，像「一個人在海邊走，身後跟著三個穿同款衣服的自己」 | 影片模型會把參考圖的**版面**一起複製進成片（官方 skill 明文禁止 4-panel sheet：「not one 4-panel sheet, because video models may copy panel layouts into the final film」【官方】）。**多格板本身不是違規**——ComfyUI 官方 H3 指引允許多格板，只要「獨立編號、逐格描述、鏡頭指向某一格」【官方】；違規的是**把整板當成扁平的身分來源**餵進去 | 角色參考圖**預設**改成單一視角裁切（正面身份裁切 950×910、背面全身裁切約 400×960）；2560×1440 整板**未經宣告不得送件**；門禁 E20（≥1600×900 且長寬比 ≥1.5 即擋）。官方允許的例外是**宣告式整板查表**：stage5 宣告 `reference_view: "panel"` ＋ 必填 `panel_label_en`（如 `"the fourth figure from the left, a full-body back view"`），且該角色只能是**不露臉的身份錨點**（不能同時是 `face_subject_ids`）；缺 `panel_label_en` → 編譯器丟 `ValueError`、送件前 E27 報錯。**但整板查表尚未在本專案 A/B 實測，仍有把其他格也畫進畫面的風險**，單視角裁切才是低風險預設（細節見 `references/consistency.md` §7.4） |
| 11 | **提示詞缺 `(Sx)` 說話人代號 → 畫外音長出第二個人（0/13 段合規）** | 寫了 `<d>` 台詞或畫外音卻沒有 `(S1)` 這類說話人代號，聲音被掛到畫面上唯一那張臉上，於是長出第二個人；有時還會「說話者錯邊」 | 官方要求發聲者（含畫外音）都要有穩定 ID；沒有 ID 時 H3 只能猜，而段內它只猜得到唯一那張臉（官方 base 指南 §4.4：發聲者使用 `(S1)`、`(S2)` 等穩定 ID【官方】） | 每個發聲者都要有 `(Sx)`，且說話人與 `<Subject N>` 綁定（`<Subject 2> (S1) turns toward the woman and says, <d>[English] …</d>`）；畫外音同形並標 `off-screen`；門禁 E22／E23，見 `references/consistency.md` §7.4 |

---

## 官方 Ref2VA 格式合規速查（本專案實作對照）

官方 Ref2VA 的 `retention_analysis` 對可見內容**只有四個固定標記**：`fully_preserved`、`partially_preserved`、`attribute_transfer`、`weak_reference`——**沒有「忽略」這個標記**；`weak_reference` 的語意是「只保留風格、類別、構圖或氛圍的廣泛相似」，用在人物身上會把對方降級成一個泛用人。下表把官方要求對到本專案的函式、欄位與旗標，以及不照做時的症狀。

| 官方要求 | 本專案實作（函式／欄位／旗標） | 未合規時的症狀 |
|---|---|---|
| 【官方】`<Subject N> (Sx)` 說話人綁定：physically speaks 要同時保留視覺參考標籤與說話人 ID | `compile_layer2_to_h3.py` 的 `_assign_speaker_ids()` 產生 `speaker_ids`，提示詞寫成 `<Subject 2> (S1) turns toward the woman and says, <d>[English] …</d>`；畫外音同形並標 `off-screen` | 聲音被掛到畫面上唯一那張臉上，長出第二個人（門禁 **E22**） |
| 【官方】畫外音用原句 `says in an off-screen voiceover`，且每個 voiceover `<d>` 之後要說明對應畫面角色的嘴唇保持閉合 | 編譯器在畫外音 `<d>` 之後直接產出官方句式；E23 檢查 `lips remain completely closed` 是否存在 | 畫面角色的嘴跟著旁白開合，成片像角色在自言自語（門禁 **E23**） |
| 【官方】`partially_preserved` 用於「保留服裝與體型、但不匯入臉」的身份錨點 | stage5 `identity_anchor_ids` → 編譯器輸出 `partially_preserved - the hairstyle, the headwear, the wardrobe and the body silhouette from <Picture N> are retained; the reference face is not imported and never appears in the target video.` | 用錯標記（`weak_reference` 會把角色降級成泛用人）或乾脆省略參考圖 → 主角的複製臉長在別人身上（門禁 **E19**／**E26**） |
| 【官方】`overall_soundscape` 不得重複台詞：對白、歌唱、情境音樂都已屬於多模態描述欄 | 編譯器把台詞只寫在 `detailed_description` 的 `<d>` 區塊，環境音欄只留環境與動作音 | H3 在環境音軌把台詞再念一次，觀眾聽到同一句說兩遍（門禁 **E25**） |
| 【官方】禁止多視圖板：不要一張 4-panel sheet，影片模型會把版面複製進成片；【官方 ComfyUI 指引】多格板可以用，但必須獨立編號、逐格描述、鏡頭指向某一格 | 送件前 E20 量參考圖像素（≥1600×900 且長寬比 ≥1.5 → 錯誤，**除非**宣告 `reference_view: "panel"` ＋ 非空 `panel_label_en`）；`submit_h3_segments.py` 傳 `project_root`，讓 audit 讀得到像素；宣告查表缺格位 → E27 | 背景長出多個穿同款衣服、長同一張臉的複製人（門禁 **E20**／**E27**） |
| 【官方】參考素材要逐一對應主體（`<Picture N>` ↔ `<Subject N>` 序對不可錯位），沒有參考圖的人不該被寫成具體人物 | stage5 `identity_anchor_ids` 必須對得到 `reference_paths.characters`（否則編譯器丟 `ValueError`）；編譯器把在場但無圖的角色寫進 `unanchored_in_frame_characters` | 提示詞裡的群眾／路人被補成主角造型，火山島上長出整群白襯衫學生（門禁 **E19**／**E21**） |
| 【官方】每張參考素材只對應一個主體；【Ref2VA 程式預設】一段最多一張「可辨識人臉」參考圖（無臉裁切不計；remix 不適用，D3） | 混臉警告只計算 `reference_view != "non_face"` 的角色參考圖；`reference_view: "non_face"` 的背影／側身裁切不計人臉 | 兩張可辨識臉同段會被平均成同一張臉（混臉）；無臉裁切本來就是為此設計的，本專案實測多張體型相近的角色圖會被融合成同一張臉 |
| 【官方】`<Audio N>` 是可單獨追蹤的參考音訊，用途之一是「參考說話人的音色與語氣」；綁定式為 `<Audio 1> is the voice-timbre reference for <Subject 1> (S1).`，音訊的保留標記用 `reference`（只參考音色與語氣、**不複製原訊號**），且只參考音色時**不得**把母帶原句帶進目標影片 | stage5 `audio_references[{id, path, character_id, role, description_en}]` → 編譯器產出 `<Audio N>` 綁定句、`reference` 保留標記與固定描述詞 `voice_4d_spec_en`；音訊素材排在**所有圖像素材之後**（`<Audio N>` 獨立編號，見官方 §2.5）；只掛給本段**真的有可見嘴**說話的角色，畫外音（已外部化 TTS）不掛；**本機 FreeVideo 路徑送得進音訊參考**（`FreeVideo · Media` 的 `Reference audio` 槽，媒體型態依副檔名分類，音訊檔由 `submit_h3_segments.py` 的 `upload_reference_media()` 上傳）；FreeVideo 導演台另有一種自動前綴寫法 `<Subject 1> is the character in <Picture 2>, a teenage boy in a light short-sleeved shirt. <Audio 1> is its voice.`（與 `<Picture N> shows its appearance` 對稱） | 同一角色在每一段是不同音色（跨片段不斷換人；音色參考不保證跨段一致）；或母帶原句被念出來，等於同一句話出現兩次【官方 ref-en §2.4／§4.1】；或音色參考送到了但**口型對不上**（音訊參考不鎖輸出音軌與口型）；或兩種綁定寫法的 `<Audio j>` 對不上帳（角色發出別人的音色） |

官方原文：[`skills/h3-prompt-writing/references/ref-en.txt`](https://github.com/MiniMax-AI/MiniMax-H3/blob/main/skills/h3-prompt-writing/references/ref-en.txt)（§5.4 說話人綁定與 `off-screen`；§2.2 `<Picture N>` 當分鏡／鏡頭規劃錨點；§2.4 `<Audio N>` 音訊參考與音色參考綁定式；§4.1 音訊保留標記 `reference`；§2.5 `<Video N>` 與 `<Audio N>` 各自獨立編號）｜[`skills/h3-prompt-writing/references/base-en.txt`](https://github.com/MiniMax-AI/MiniMax-H3/blob/main/skills/h3-prompt-writing/references/base-en.txt)（§4.4 說話人 ID 與 `says in an off-screen voiceover`、§4.6 `overall_soundscape` 分工）｜官方 skill [`minimalist-product-ad-generator/SKILL.md`](https://github.com/MiniMax-AI/MiniMax-H3/blob/main/skills/minimalist-product-ad-generator/SKILL.md)（禁止 4-panel sheet）｜多格板用法見 ComfyUI 官方文件 [docs.comfy.org](https://docs.comfy.org)（MiniMax H3 提示詞指引：多格板需獨立編號、逐格描述、鏡頭指向某一格）｜同一批文件也收在 [huggingface.co/MiniMaxAI/MiniMax-H3](https://huggingface.co/MiniMaxAI/MiniMax-H3) 的 `docs/`。中文手冊另見社群轉載 [h3skills.com/anthology](https://h3skills.com/anthology)：「人物露脸只能是近景或特写，远景只能是背影、侧背或环境空镜，不要正脸远景。」

---

## 檔案索引

### 核心（每次都會用到）

| 你要做的 | 讀 |
|---|---|
| 選格式：官方三欄／六段式／中文三段／社群區塊式；對齊句、參考檔上限 | `h3/prompt-formats.md` |
| MiniMax H3 專用 LoRA 實戰與自動適配：核心 8 大 LoRA 矩陣、速度滑塊、權重預算與 FreeVideo 掛載 | `h3/lora-guide.md` |
| 套用**守富定版**皮膚段骨架 | `h3/skin-realism-block.md` |
| 讓動作有重量、材質有回應、表情有意圖（含慢動作、動畫風格規律） | `h3/motion-quality.md` |
| 排節奏、卡點、時間軸、速度詞 | `h3/rhythm-and-pacing.md` |
| 人物動作拆解、打鬥一拍公式、多對一 | `h3/action-choreography.md` |
| 高階武戲編排、冷兵器連招、玄幻大招五段鏈與 11 大戰場拓撲 | `storyboard/combat-and-vfx-library.md` |
| 邁斯納壓力行為表演、潛台詞言行反差、10 大景別句型與 4D 配音 | `storyboard/acting-and-emotion-library.md` |
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
