# AI 漫劇九宮格鎖臉、首尾幀接龍與跨片段連戲狀態機 (v2.0)

本手冊融合全網成熟 AI 漫劇/動態漫實戰工程、GitHub 高星專案（`HKUDS/ViMax`、`HVision-NKU/StoryDiffusion`、`ToonCrafter`）與 Lyra 場記清算體系，補齊 `cinematic-director-storyboard` 在**長序列連戲、多宮格資產鎖定與防禦性藏拙調度**上的工業管線。

---

## 一、兩階段資產管線：破解「禁止四宮格」與「多宮格鎖臉」的矛盾

在 AI 影視與漫劇製作中，「多宮格（Grid）」在不同階段具有完全相反的工程意義，必須嚴格區分：

```mermaid
flowchart LR
    subgraph StageA["Stage A：前置資產與構圖審核階段 (T2I)"]
        S1["1. 角色/生物純底三視圖資產卡<br/>(純灰/純白背景，嚴禁帶場景背景)"] --> S2["2. Qwen 鉛筆草圖九宮格構圖審核<br/>(確認焦距透視、走位與動勢箭頭)"]
        S2 --> S3["3. 單格零污染局部重繪與審核鎖定<br/>(patch_shot.py + --redraw-shot)"]
    end

    subgraph StageB["Stage B：最終影片動態生成階段 (Ref2VA / 實戰定案)"]
        S3 --> S4["4. 分段級獨立 Ref2VA 提示詞編譯<br/>(一段一張角色圖，P0 程式稽核)"]
        S4 --> S5["5. 跨段四大連戲錨點與收尾交接格<br/>(光線、軸線、站位、材質，不走尾幀續接)"]
        S5 --> S6["6. verify_video_shot.py 自動審查門禁<br/>(檢驗時長、彩度、分屏線殘留與色盤連貫性)"]
    end
```

> **本技能實戰定案**：
> 1. **主力定案為每段獨立 `Ref2VA`**：不走首尾幀接龍 `continue_from`（FreeVideo API 中 `references` 與 `first/last` 互斥報 422，且續接段無角色圖會退化為通用塑膠臉）。跨段連戲靠**四大錨點（光線、軸線、站位、材質）**與**收尾交接格**。
> 2. **一段一張角色圖防平均化**：多位體型相近角色同框會被 H3 融合平均化，反應戲拆單人特寫；P0 程式稽核對齊說話者與素材 ID。
> 3. **生物純色三視圖（Creature Sheet）**：純灰/純白底，嚴禁帶背景劇照；演員表按主角重要性排序。

### 1. Stage A：九宮格構圖審核與資產鎖定法
- **適用場景**：分鏡走位視覺化、焦距透視驗收、防止直接生影片盲抽翻車。
- **角色與生物特異性視覺錨點（Unique Visual Anchors）**：
  - 禁用泛化詞（如「英俊青年、漂亮女孩」）。
  - 強制綁定 3 個高抗噪幾何/色彩特徵：例如 `銀白高馬尾配暗紅髮帶 + 左眼角下緋紅淚痣 + 玄黑窄袖勁裝鑲嵌青銅雲紋護腕`。
- **生物純底三視圖鐵律**：巨蟒、妖獸等生物必須生成純灰/白底三視圖，嚴禁帶有巷子或自然背景，否則場景會殘留染色到成片各處。

### 2. Stage B：分段級獨立 Ref2VA 與連戲四大錨點（實戰主力定案）
- **核心操作**：每段 7–10 秒獨立生成，攜帶「1 場景圖 ＋ 對應角色設定圖」，不依賴上一鏡尾幀。
- **四大連戲錨點**：
  1. **光線錨點**：整場共用同一句全域光色句（主光向、色溫、反差）。
  2. **軸線錨點**：遵循 180° 軸線，越軸前必有騎軸過渡鏡。
  3. **站位錨點**：錨定在實體家具/幾何標誌（如「站在紅木桌右角」）。
  4. **材質錨點**：地面與牆面紋理名詞逐字保持一致。
- **收尾交接格**：每段最後 1–2 秒設計「靜止、夠寬、留白」的動作收勢，方便下段自然無縫銜接。

---

## 二、動態漫與真人短劇「防禦性藏拙調度」（Defensive Cinematography）

當劇本包含長句對白，或目標模型不具備高精準原生對嘴能力時，嚴禁讓角色「正面大特寫（Frontal ECU）長篇大論說話」，必須自動啟動以下四種藏拙調度：

| 藏拙策略代號 | 鏡頭調度手法 | 視覺與心理效果 | 適用時機 |
|---|---|---|---|
| **1. 反應鏡頭借代**<br/>(`Reaction_OTS`) | 說話者背對鏡頭或處於前景虛化過肩位（佔比 25%），焦點鎖定在**聽者的面部微表情反應**（瞳孔收縮、下頜緊繃、指尖收緊）。 | 既完全避開說話者複雜口型，又透過聽者的震驚/隱忍把戲劇張力拉滿。 | 長句威脅、揭露秘密、質問對峙 |
| **2. 器物與光影遮嘴**<br/>(`Prop_Shadow_Mask`) | 利用前景或隨身道具（舉起的茶杯、展開的摺扇、高立領、面具、百葉窗暗部切片陰影）自然遮擋下半張臉，僅露雙眼。 | 眼神殺聚焦度極高，完全免除嘴部渲染風險。 | 密謀、冷笑、古風/懸疑漫劇 |
| **3. 極遠景環境留白**<br/>(`Atmospheric_EWS`) | 採用 24mm/100mm 遠景，人物在畫面中佔比 `<15%`，搭配大面積環境動態（暴雨、飄雪、落葉、車流）。 | 觀眾注意力集中在環境宿命感與底部字幕，無需看清嘴唇開合。 | 孤獨獨白、哲學感嘆、場次收尾 |
| **4. 呼吸感微動態 + 2.5D 運鏡**<br/>(`Micro_Idle_2.5D`) | 限定角色僅做微小生理動態（`胸口隨呼吸微伏、眨眼、髮絲與衣角隨風微動`），依靠攝影機急推（Snap Zoom）、震屏或焦點切換製造動感。 | 根治 AI 漫劇「人物像木頭貼紙」或「大幅度動作崩臉」的兩極病態。 | 動態漫內心獨白、殺氣釋放瞬間 |

> **【同框非主體人物保活鐵律（Background Idle Life Rule）】**：  
> 在雙人或多人同框鏡頭中，未說話或非主動作的角色**嚴禁完全靜止凍結**！必須在提示詞中為其分配一個低強度保活微動作（如：`前景的 A 保持輕微呼吸起伏，目光隨 B 的步伐微移，雙唇完全閉合`）。

---

## 三、連戲相依狀態圖與跨分段握手 (Continuity State Machine)

為解決多切片長篇劇本連戲崩潰，確立以下規則：

### 1. 台詞政策與四維配音氣口順延
- **台詞政策核准制**：階段 0 依使用者選定政策（①原文逐字 / ②只留重點句 / ③影視改寫 / ④無台詞純旁白）執行。
- **氣口順延計算公式**：
  - 常規對話語速上限：$\le 3.8$ 字/秒；極限安全值 $\le 4.0$ 字/秒。
  - 當單段台詞超出容量時，在標點符號或氣口處切斷，將後半句寫入 `overflow_dialogue_out`，由下段首鏡無縫接續。

### 2. 獨立 Ref2VA 跨段握手協議
- **同場續接**：以「四大連戲錨點」與「收尾交接格」承接，首鏡動作不發生 180° 瞬移。
- **時空跳躍**：首鏡強制使用廣角/全景 Establishing Shot 交代新空間，重錨空間幾何。

### 3. 不可逆狀態傳遞（`persistent_world_state`）
- 一旦某鏡頭發生不可逆物理改變（如水杯被打翻碎裂、衣角燒焦、刀傷流血），寫入狀態機，後續同場景所有鏡頭自動繼承，嚴禁自動復原！

---

## 四、Qwen-Image 2.1 電影級黑白鉛筆分鏡草圖：成熟提示詞手冊與逐格拼版規範

本專節正式收錄經實測驗證（評分 **8.86/10 分**）的「Qwen-Image 2.1 Turbo 電影黑白鉛筆分鏡草圖成熟體系」，解決影視前期「文字分鏡過於抽象、直接抽卡生影片成本過高、角色走位與景別無法低成本預覽」的痛點。

### 1. Qwen-Image 2.1 Turbo 鉛筆草圖萬用骨架（5 段式英文觀察者語法）

針對本機 Qwen-Image 2.1 Turbo 引擎特性（**CFG=1.0、無負向詞、純英文第三人稱現在式客觀描述**），Prompt 必須採用五段式結構化組裝：

```text
[段落 1：媒材錨點 (Medium Anchor)]
A monochrome graphite pencil storyboard sketch on off-white paper, cinematic blocking and composition diagram.

[段落 2：景別焦段光學 (Framing & Optics)]
Cinematic framing: {framing_desc}, {lens_desc}, camera distance: {distance}.

[段落 3：空間透視滅點線 (Perspective Guidelines)]
Camera angle & blocking: {pov_desc}. Camera movement: {movement}. Spatial environment & perspective: Architectural perspective construction lines and visible vanishing point guidelines showing {anchor_objects}. Spatial layout: {blocking_desc}.

[段落 4：主體姿勢與粗黑動勢箭頭 (Kinetic Arrows & Acting)]
Character action & pose: {action_str}. Character expression: {expression}. Directional annotation: Bold black hand-drawn directional arrows indicating subject motion, action trajectory, and camera movement.

[段落 5：排線光影與純淨鎖 (Pencil Hatching & Purity Lock)]
Artistic technique: Pure grayscale pencil cross-hatching, hatching line shading, rough animatic concept art, crisp hand-drawn sketch lines, no speech bubbles, no colored elements, no text overlays, no watermarks.
```

- **焦距透視轉譯表 (Lens Optics Mapping)**：
  - `14mm`：`14mm ultra-wide perspective, strong peripheral barrel expansion and dramatic depth stretch`
  - `24mm`：`24mm wide angle perspective, exaggerated near-to-far spatial scaling and rapid linear convergence`
  - `35mm`：`35mm natural environmental wide perspective, balanced human-to-space spatial relationship`
  - `50mm`：`50mm true-to-life standard prime perspective, zero geometric distortion, human eye natural depth`
  - `85mm`：`85mm portrait telephoto compression, shallow depth of field isolating subject from soft blurred background`
  - `100mm`：`100mm telephoto macro compression, background heavily flattened and stacked against subject profile`
  - `135mm`：`135mm extreme telephoto compression, razor-thin focal plane and monumental background stacking`

---

### 2. 9 大標準分鏡鏡位即抄即用 Prompt 模板庫

本庫收錄 9 種最核心的電影級分鏡鏡位，Agent 為任何新場景建立九宮格分鏡表（`panel-01` 至 `panel-09`）時可直接套用並填入具體走位與角色名：

#### 鏡位 1：大遠景空間建立 (ELS 24mm Establishing Shot)
> **適用**：場景開端、世界觀震撼交代、環境壓迫感。  
> **Prompt 模板**：  
> `A monochrome graphite pencil storyboard sketch on off-white paper, cinematic blocking and composition diagram. Cinematic framing: Extreme Long Shot (ELS), environmental scale establishing shot, 24mm wide angle perspective, exaggerated near-to-far spatial scaling and rapid linear convergence, camera distance: >10m distant overview. Camera angle & blocking: High-angle objective overview looking down at the environment, establishing spatial geometry. Camera movement: Slow drifting crane shot. Spatial environment & perspective: Architectural perspective construction lines and two distinct visible vanishing point guidelines showing the expansive courtyard, fortress gates, and distant mountain ridges. Character action & pose: Tiny silhouettes of characters standing near the central gateway, establishing scale relative to architecture. Character expression: Distant figures without detailed facial features. Directional annotation: Bold black hand-drawn directional arrows indicating the wind vector blowing across the courtyard and the forward marching trajectory of approaching riders. Artistic technique: Pure grayscale pencil cross-hatching, atmospheric perspective shading, rough animatic concept art, crisp hand-drawn sketch lines, no speech bubbles, no colored elements, no text overlays, no watermarks.`

#### 鏡位 2：中景橫移跟拍 (MS 35mm Tracking Shot)
> **適用**：角色行進、空間過渡、自然對白。  
> **Prompt 模板**：  
> `A monochrome graphite pencil storyboard sketch on off-white paper, cinematic blocking and composition diagram. Cinematic framing: Medium Shot (MS), character framed from waist up in spatial context, 35mm natural environmental wide perspective, balanced human-to-space spatial relationship, camera distance: 2.5m medium distance. Camera angle & blocking: Eye-level lateral tracking shot adhering strictly to 180-degree axis line, subject moving parallel to film plane. Camera movement: Dynamic lateral tracking dolly moving synchronously left-to-right. Spatial environment & perspective: One-point perspective corridor guidelines receding towards frame right, vertical columns creating natural depth slats. Spatial layout: Subject moving past recurring structural pillars. Character action & pose: Walking forward with brisk determined stride, cloak trailing backwards, right hand hovering near concealed blade. Character expression: Resolute expression, sharp forward-fixed gaze, tight jawline. Directional annotation: Bold black hand-drawn directional arrows indicating subject's linear walking path from left to right, with double horizontal arrows tracking camera dolly movement. Artistic technique: Pure grayscale pencil cross-hatching, hatching line shading on side shadows, rough animatic concept art, crisp hand-drawn sketch lines, no speech bubbles, no colored elements, no text overlays, no watermarks.`

#### 鏡位 3：過肩對峙 (OTS 50mm Confrontation)
> **適用**：雙人言詞交鋒、談判、壓抑對峙。  
> **Prompt 模板**：  
> `A monochrome graphite pencil storyboard sketch on off-white paper, cinematic blocking and composition diagram. Cinematic framing: Over-The-Shoulder Medium Shot (OTS_MS), 50mm true-to-life standard prime perspective, zero geometric distortion, human eye natural depth, camera distance: 1.8m dialogic distance. Camera angle & blocking: Defensive OTS composition past the dark out-of-focus silhouette of Foreground Speaker A's shoulder occupying 25% of left frame; sharp focal plane locked on Opposite Speaker B positioned on the right third line. Camera movement: Static locked frame maintaining tense standoff. Spatial environment & perspective: Background interior room perspective grid converging behind Speaker B, soft tonal hatching isolating characters. Spatial layout: Strict 180-degree axis placement across a long wooden table. Character action & pose: Foreground A remains rigid in dark silhouette; Background B leans slightly forward, palms flat against table surface. Character expression: Speaker B exhibiting piercing suspicious squint, tight contemptuous mouth posture. Directional annotation: Bold black hand-drawn double-ended directional arrow between both heads indicating intense unbroken eyeline tension; curved arrow showing B's subtle forward torso lean. Artistic technique: Pure grayscale pencil cross-hatching, foreground silhouette shading in dense graphite tone, crisp hand-drawn sketch lines, no speech bubbles, no colored elements, no text overlays, no watermarks.`

#### 鏡位 4：情緒眼神特寫 (CU 85mm Emotional Close-Up)
> **適用**：內心震驚、隱忍咬牙、情感決裂。  
> **Prompt 模板**：  
> `A monochrome graphite pencil storyboard sketch on off-white paper, cinematic blocking and composition diagram. Cinematic framing: Close-Up (CU), tight framing from collarbone to crown, 85mm portrait telephoto compression, shallow depth of field isolating subject from soft blurred background, camera distance: 1.0m intimate distance. Camera angle & blocking: Slight three-quarter angle at subject's eye level, subject placed off-center following rule-of-thirds. Camera movement: Imperceptible micro-creep zoom into subject's eye plane. Spatial environment & perspective: Heavily out-of-focus background with minimal faint perspective hints, emphasizing subject psychological isolation. Character action & pose: Head held upright, throat swallowing in repressed tension, fingers brushing against lower jaw. Character expression: Intense emotional conflict, dilated pupils with pencil highlight reflection, trembling lower eyelids, teeth clenching under closed lips. Directional annotation: Bold black hand-drawn directional arrows indicating slight upward tilt of chin and downward eye dart, small circular arrow highlighting temple tension. Artistic technique: Fine graphite pencil hatching, delicate skin texture cross-hatching, expressive linework around eyes and lips, rough animatic concept art, crisp hand-drawn sketch lines, no speech bubbles, no colored elements, no text overlays, no watermarks.`

#### 鏡位 5：極端特寫局部推進 (ECU 85mm Dramatic Macro Push)
> **適用**：瞳孔收縮、殺氣爆發、秘密線索瞬間聚焦。  
> **Prompt 模板**：  
> `A monochrome graphite pencil storyboard sketch on off-white paper, cinematic blocking and composition diagram. Cinematic framing: Extreme Close-Up (ECU), macro horizontal framing cropped closely across eyes and nose bridge, 85mm portrait telephoto compression with razor-thin depth of field, camera distance: 0.4m macro proximity. Camera angle & blocking: Frontal direct eye level, subject's gaze breaking cinematic tension by piercing into lens axis. Camera movement: Rapid snap push-in towards the right pupil. Spatial environment & perspective: Completely obliterated background bokeh, pure focus on optical textures. Character action & pose: Sudden widening of eyelids revealing shock and sudden realization, faint sweat bead pencil stippling on brow. Character expression: Sudden psychological breakthrough, intense dilated pupil with sharp graphite reflection catchlight. Directional annotation: Bold black hand-drawn converging arrows pointing symmetrically into the pupil center indicating sudden focus snap. Artistic technique: High-contrast graphite pencil rendering, razor-sharp iris linework, soft tonal skin shading, rough animatic concept art, crisp hand-drawn sketch lines, no speech bubbles, no colored elements, no text overlays, no watermarks.`

#### 鏡位 6：武戲 90° 側面無遮擋交鋒 (MS 50mm Perpendicular Impact)
> **適用**：刀劍碰撞、重拳擊中、瞬間打擊（強制 90° 無遮擋，嚴禁 Dirty Frame）。  
> **Prompt 模板**：  
> `A monochrome graphite pencil storyboard sketch on off-white paper, cinematic blocking and composition diagram. Cinematic framing: Medium Shot (MS), two combating figures framed from knees to head, 50mm true-to-life standard prime perspective, zero geometric distortion, camera distance: 3.5m combat safe zone. Camera angle & blocking: Strict 90-degree perpendicular side profile view (clear_impact_90deg), completely unobstructed line of action exposing exact contact point between weapon blade and defensive forearm guard. Camera movement: Dynamic micro-shake at impact instant. Spatial environment & perspective: Horizontal ground line perspective grid with radiating impact shockwave guidelines along the floor. Spatial layout: Left fighter lunging forward, right fighter bracing back in defensive parry. Character action & pose: Left attacker delivering a high overhead diagonal saber strike; right defender crossing bracers to deflect the blow at chest level, muscles taut. Character expression: Straining battle grimaces, bared teeth under breath exertion, focused combat glare. Directional annotation: Bold black hand-drawn high-velocity motion arrows along the saber trajectory path; radiating starburst impact arrows erupting from the contact point; backward recoil vector arrow beneath defender's heel. Artistic technique: Dynamic gestural pencil strokes, aggressive kinetic speed lines, dense graphite hatching on strained musculature, crisp hand-drawn sketch lines, no speech bubbles, no colored elements, no text overlays, no watermarks.`

#### 鏡位 7：低角度壓迫仰拍 (CU 24mm Low-Angle Oppression)
> **適用**：反派登場、絕對支配、威壓恐嚇。  
> **Prompt 模板**：  
> `A monochrome graphite pencil storyboard sketch on off-white paper, cinematic blocking and composition diagram. Cinematic framing: Close-Up (CU), towering torso and head framing, 24mm wide angle perspective, exaggerated upward geometric convergence and dominant near-to-far distortion, camera distance: 0.8m low proximity. Camera angle & blocking: Extreme low-angle worm's-eye perspective looking steeply upwards at the towering antagonist, head framed against the ceiling vault. Camera movement: Slow intimidating upward tilt. Spatial environment & perspective: Vaulted ceiling ribs converging steeply upwards into a high vanishing point, creating an oppressive pyramidal composition. Spatial layout: Dominant figure looming directly over the camera lens. Character action & pose: Shoulders squared, chin tilted downward while looking down upon the viewer with cold condescension, one hand raised clasping a ceremonial token. Character expression: Arrogant ruthless half-smile, heavy lidded eyes looking downwards with supreme disdain. Directional annotation: Bold black hand-drawn upward expansion arrows along the shoulders emphasizing towering dominance; downward pointing gaze arrow bearing down on the viewer. Artistic technique: Bold sculptural graphite pencil shading, strong chiaroscuro contrast between lighted face plane and deep hatched neck shadow, crisp hand-drawn sketch lines, no speech bubbles, no colored elements, no text overlays, no watermarks.`

#### 鏡位 8：微距道具細節 (ECU 100mm Prop Focus)
> **適用**：信封拆封、鑰匙插入、握緊玉佩、微觀物理反應。  
> **Prompt 模板**：  
> `A monochrome graphite pencil storyboard sketch on off-white paper, cinematic blocking and composition diagram. Cinematic framing: Extreme Close-Up (ECU), macro prop detail framing, 100mm telephoto macro compression, paper-thin depth of field, camera distance: 0.3m macro proximity. Camera angle & blocking: High 45-degree top-down angled close view centered on a hand interacting with a critical narrative object. Camera movement: Static locked macro shot with minute focus rack. Spatial environment & perspective: Blurred desktop wood grain receding in shallow diagonal lines. Spatial layout: An ancient stamped wax seal on a folded parchment letter held by trembling gloved fingers. Character action & pose: Right gloved thumb peeling back the cracked red wax seal, paper fiber tearing along the crease line. Character expression: Non-facial shot; performance expressed entirely through the trembling hesitation of finger knuckles. Directional annotation: Bold black hand-drawn curved arrow indicating the upward peeling motion of the thumb; dashed circle highlighting the fractured seal emblem. Artistic technique: Highly detailed graphite pencil texturing, delicate paper crease shading, sharp tactile cross-hatching on wax fragments, crisp hand-drawn sketch lines, no speech bubbles, no colored elements, no text overlays, no watermarks.`

#### 鏡位 9：遠景背影留白收尾 (LS 35mm Lingering Outro)
> **適用**：片段結尾、轉場空鏡、餘韻收尾。  
> **Prompt 模板**：  
> `A monochrome graphite pencil storyboard sketch on off-white paper, cinematic blocking and composition diagram. Cinematic framing: Long Shot (LS), full solitary figure framed from behind in vast environment, 35mm natural environmental wide perspective, balanced human-to-space spatial relationship, camera distance: 7.0m distant framing. Camera angle & blocking: Eye-level central back-view perspective (subject back to camera), strictly centered along the vanishing perspective line. Camera movement: Slow pulling-back dolly lingering as distance increases. Spatial environment & perspective: Single central vanishing point grid on an endless desolate road extending to the horizon; barren trees framing the left and right borders. Spatial layout: Solitary figure walking directly away from camera into the distant horizon. Character action & pose: Solitary figure walking away with slow measured paces, long coat billowing gently in the wind, hands buried in pockets. Character expression: Back to camera; posture conveying profound solitude, weight of consequence, and quiet acceptance. Directional annotation: Bold black hand-drawn straight directional arrow pointing directly forward along the road towards the horizon vanishing point; subtle wavy arrows showing coat hem movement. Artistic technique: Atmospheric graphite pencil wash shading, soft horizon blending, textured pencil strokes on road ruts, crisp hand-drawn sketch lines, no speech bubbles, no colored elements, no text overlays, no watermarks.`

---

### 3. 分鏡至影片生成轉換管線：主力定案 Ref2VA vs 選用首幀 I2VA

在 AI 動態漫與影視工業管線中，分鏡至影片的生成**嚴格區分主力定案與實驗功能**：

```mermaid
flowchart TD
    Step1["步驟 1：Layer 2 SSoT 分鏡規範<br/>(validate_storyboard.py 靜態驗證通過)"] --> Step2["步驟 2：Qwen 鉛筆草圖 3x3 九宮格構圖審核<br/>(qwen_storyboard_grid.py 鎖死構圖與箭頭)"]
    
    Step2 --> PathA["【✅ 主力定案】分段級獨立 Ref2VA<br/>(每段獨立 7~10s，各自帶場景+單角色純底圖)"]
    Step2 -.-> PathB["【⚠️ 選用實驗】Qwen 轉繪全彩關鍵幀首幀<br/>(需全片統一生圖模型，並排對照畫風)"]
    
    PathA --> Step4A["步驟 4A：MiniMax H3 獨立 Ref2VA 生成<br/>(四大連戲錨點 + 收尾交接格)"]
    PathB -.-> Step4B["步驟 4B：MiniMax H3 I2VA 生成<br/>(注入單鏡禁分屏鎖)"]
    
    Step4A & Step4B --> Step5["步驟 5：verify_video_shot.py 自動審查門禁<br/>(檢驗時長、彩度、九宮格殘留與相鄰色盤連貫性)"]
```

1. **步驟 1：Layer 2 SSoT 規格鎖定**：
   - 導演編寫並通過 `scripts/storyboard/validate_storyboard.py` 檢查，確認時長守恆、台詞預算（$\le 4$ 字/秒）、無醫學解剖黑名單、無遮擋衝突。
2. **步驟 2：Qwen 鉛筆草圖逐格生成與九宮格審核（✅ 已驗證構圖工具）**：
   - 使用 `scripts/storyboard/qwen_storyboard_grid.py` 逐格生成 `panel-0{1..9}-{shot_id}.png`，拼合成 `grid-{segment_id}.png`。
   - 導演/人工審查員（HITL）簽核走位、焦距透視滅點與動態粗黑箭頭；未通過者使用 `patch_shot.py` 搭配 `--redraw-shot` 單格局部重抽。
3. **步驟 3A：【✅ 主力定案】獨立 Ref2VA 提示詞編譯與程式對帳**：
   - 每段 7–10 秒獨立生成，帶場景主圖與單角色純色設定圖。
   - 執行 `scripts/storyboard/audit_refs_and_segments.py` 完成 P0 程式稽核，確保素材 ID、主體定義與說話者代號完全對齊。
4. **步驟 3B：【⚠️ 選用實驗】Qwen 轉繪全彩關鍵幀首幀（擦除黑箭頭）**：
   - 若要採用首幀 I2VA 流程，執行 `qwen_storyboard_grid.py --to-color-keyframe` 輸出全彩首幀。
   - **重大門禁限制**：必須整部片全部統一用同一生圖模型生成首幀，且產出影片後必須與既有片段**並排對照畫風**！
5. **步驟 4：MiniMax H3 動態生成**：
   - Ref2VA：注入六段式結構，嚴格鎖定四大連戲錨點與收尾交接格；
   - I2VA：以全彩關鍵幀為 `first_frame`，提示詞強制加入禁分屏鎖：`single continuous shot, no split screen, no multi-panel grid, no watermark, no text overlay`。
6. **步驟 5：影片自動審查門禁 (`verify_video_shot.py`)**：
   - 自動檢驗影片時長（誤差 $\le 0.5\text{s}$）、平均彩度（$C^* \ge 10.0$）、九宮格邊界殘留（$1/3, 2/3$ 無暗黑格線）、相鄰鏡頭色盤連貫性（$dE_{76} \le 25.0$）。
   - 檢驗通過自動寫入 `shots[].review` 並鎖定；未通過自動退稿。

> [!WARNING]
> #### ⚠️ 實戰慘痛教訓：第五輪首幀流程連續兩次誤判成功！
> 在《噩盡島》實戰第五輪中，外部生圖模型（Qwen-Image / GPT-Image）轉繪出的全彩首幀靜態圖極其精美，導致 Agent 連續兩次誤判流程成功。
> 但送進 H3 生成並混入既有 Ref2VA 成片時，**生圖模型渲染的人物材質與 H3 底層原生畫風產生巨大割裂，被使用者當場判定為失敗（「畫風跟其他片段差距過大」）**！
> **鐵律**：
> 1. **絕不可單看首幀漂亮就宣稱成功！驗證新流程必須與既有已過審的 H3 片段並排對照畫風！**
> 2. 除非全片統一用同一個生圖模型產出所有鏡頭首幀，否則主力一律走**分段級獨立 `Ref2VA`**。

> [!CAUTION]
> #### ⛔ 工業管線絕對禁忌：嚴禁黑白鉛筆九宮格直餵 H3！
> 絕對禁止將「黑白鉛筆草圖」或「3x3 九宮格拼版圖」直接作為參考圖或首幀餵入 MiniMax H3（`I2VA` / `Ref2VA`）！
> 1. **黑白污染慘劇**：直接餵黑白草圖會導致 H3 生成全片灰階褪色，平均彩度 $C^* < 10.0$，喪失全部色彩動態。
> 2. **分屏魔幻動畫**：直接餵九宮格會導致 H3 將九宮格當作分屏畫布，在畫面中留下明顯的 $1/3, 2/3$ 黑線隔線，並在各小格子內獨立跳動。
> 
> 此兩種違規行為均已被 `verify_video_shot.py` 納入確定性攔截規則（`STYLE_BLEED_GRAYSCALE` 與 `GRID_PANEL_BORDER_DETECTED`），一旦檢出將立即自動觸發退稿！

