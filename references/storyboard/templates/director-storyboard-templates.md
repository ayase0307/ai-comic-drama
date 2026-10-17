# 導演分鏡、鏡頭光學與多模型編譯：三層工程模板庫 (Templates v2.0)

本模板庫採用 **「三層產物分離架構（Layer 1 人類導演表 ➔ Layer 2 JSON SSoT ➔ Layer 3 多模型原生 Prompt）」**，將「萬能分鏡三步法」、「焦距×物距物理光學」、「漫劇九宮格鎖臉與首尾幀接龍」及「跨片段雙模式握手」參數化為可直接調用的標準模板。

---

## 一、Layer 1｜人類導演審閱層模板 (Human Director's Sheet)

### 1. 跨切片場記握手與 9 欄全景分鏡表（適合多鏡頭序列統籌）

```markdown
- **場次與切片**：`[Scene_ID / Clip_ID]` ｜ **總時長**：`[12.0s]` ｜ **畫幅**：`[16:9 / 9:16]` ｜ **節奏檔位**：`[Slow_Cinematic / Standard / Fast_ShortDrama]`
- **跨組握手協議**：`[SEAMLESS_CONTINUATION (同場動作順接 + J/L-Cut) / HARD_CUT_ESTABLISH (時空跳躍硬切重置)]`
- **上段實測尾態承接 (Observed End State)**：`[人物於實體參照物之位置 | 不可逆道具/傷痕狀態 | 待續溢出台詞]`
- **全域色卡與光影鎖定**：`[聯動 lighting-color-palette-card 五層 HEX 色階與主光源方向]`

| 鏡號 | 時長區間 | 景別 / 焦段與物理物距 | 視角路由與運鏡動機 | 前置關鍵幀描述 (T2I / 首尾幀錨點) | 畫面動態、心理延遲與可見表演 (含實體參照物) | 對白 (100%保真) | 四維配音與音效 (Audio) | 連戲與防呆檢查 |
|---|---|---|---|---|---|---|---|---|
| **SH01** | `0.0-3.0s` | 中遠景, 35mm (物距2m 自然透視) | `[Dirty Frame / 90°無遮擋 / OTS藏拙]` + 運鏡 | 靜態首幀構圖與光影色階分佈 | 開幅狀態 ➔ 屏息延遲/觸發 ➔ 核心動作 ➔ 尾韻微物理（衣角/髮絲） | 「原文台詞」（或無） | 聲帶狀態/停頓 + 物理擬音 + J/L-Cut | 180°軸線 / 閉唇鎖 / 9:16安全區 |
```

### 2. 單鏡深度光學六要素卡片（適合重點戲核鏡頭精雕）

```text
分鏡 [編號]（[時長秒數]，[畫幅 16:9/9:16]，[景別]，[光學焦段] + [物理物距特徵]，[運鏡方式]）：
【視角與遮擋路由】：{路線A: 前景遮擋偷窺 Dirty Frame (20%~35% 重度失焦) / 路線B: 武戲 90° 垂直軸線無遮擋 (Clear Impact) / 路線C: 對白過肩反應藏拙 (Reaction OTS)}
【光學與物距設定】：{焦段 mm}，{攝影機靠近主體 <0.5m / 遠離主體 >6m}，{背景空間拉伸/壓縮特徵}，{景深深淺與光斑色階保留}
【動態演化與心理節奏】：{1.開幅初態 (含實體家具參照物)} ➔ {2.心理屏息延遲 (水杯倒影/停頓) 或 武戲蓄力出擊} ➔ {3.核心引爆/接觸瞬間} ➔ {4.尾韻微物理 (衣擺下墜/呼吸起伏/非主體保活)}
【色卡光影空間綁定】：{最深暗部 HEX + 環境基底 HEX + 關鍵高光 HEX 物理空間分配}
【可見微表演（禁解剖學詞）】：{眼神焦點轉移、眼眶泛紅、下頜咬緊、指節泛白等外顯變化；非說話者強制閉唇鎖}
【四維配音與音畫定軌】：{音量聲線 + 語速 + 500ms氣口停頓 + 句尾語調} ｜ 台詞定軌：{前半句動作 + 後半句動作：「100%保真台詞」}
```

---

## 二、Layer 3｜多模型原生執行層模板 (Model-Compiled Prompts)

> **[!IMPORTANT] 編譯鐵律**  
> 進入 Layer 3 餵給影片模型時，**必須徹底剝離所有 `【光學設定】`、`[潛台詞]` 等分類標籤**，並清除所有醫學解剖詞與毫米數值，直接輸出目標模型最易解析的高信噪比文本！

### 模板 A：即夢 Seedance 2.0 終極自然流模板 (`seedance-v8`)
*(一段自然語言代表一鏡，空一行代表切鏡頭，零 Markdown 標籤)*

```text
100mm望遠長焦鏡頭退後至8米外進行遠距離窺視拍攝，將背景牆面與人物空間強烈壓縮在一起，極淺景深焦點死死鎖定在茶几旁。半掩的臥室木門框與暗部陰影在畫面右側形成30%的前景重度失焦遮擋（Dirty Frame），隔著幽暗門縫窺視站在【紅木茶几】前的 @女主角。前1.5秒鏡頭聚焦於茶几玻璃杯中微微震顫的水面，杯身琥珀色高光（#D4AF37）中赫然倒映出門後的陌生黑影；隨後焦點切向 @女主角，她翻找抽屜的雙手瞬間僵在半空，呼吸驟然停滯，瞳孔放大，說到前兩個字時下唇微顫，說完最後兩字時聲音壓在喉底帶哭腔說道：「誰在那裡……」注意全場光影嚴格鎖定深藍暗部（#0A0E17）與頂燈微弱暖金邊緣光，不要單獨加光，伴隨沉重的呼吸聲與木地板微響，她的裙擺與耳畔碎髮隨僵直動作輕微晃動後靜止。
```

### 模板 B：MiniMax H3 官方三欄結構模板 (`minimax-h3`)
*(嚴格遵循 `[Shot N] At MM:SS.mmm`、`<d>` 對白標記與非說話角色閉唇鎖)*

```text
integrated_multimodal_description:
In a dimly lit vintage apartment with deep midnight-blue shadows (#0A0E17) and warm amber tungsten rim light (#D4AF37).
[Shot 1] Medium close-up, 24mm wide-angle lens placed extremely close (<0.4m) to the mahogany coffee table, exaggerating near-far perspective while keeping the character's face within the center 60% safe zone. A young woman (A) urgently rummages through scattered papers on the table with trembling hands, her chest rising rapidly as she breathes, while her lips remain completely closed.
[Shot 2] At 00:02.000, extreme close-up, 85mm telephoto lens with razor-thin depth of field, slow dolly-in on a glass water cup on the table. The water surface quivers subtly, and a dark human silhouette slowly emerges in the amber reflection of the glass, creating a breath-holding suspense delay.
[Shot 3] At 00:05.000, medium shot, 100mm telephoto lens positioned 6 meters away behind a half-closed bedroom door. The dark blurred door frame obstructs 30% of the right foreground (dirty frame POV), compressing the background wall flat against A. A freezes beside the coffee table, her knuckles turning pale, her lower lip trembling as she whispers in a shivering, breathy female voice: <d>[Chinese] 誰……誰在那裡？</d> Her hair stirs faintly from her shallow breath.

overall_soundscape:
Frantic paper rustling that stops abruptly, a low ominous bass drone as the water glass vibrates, a sharp intake of breath, and a creaking wooden floorboard in the quiet room.

non_diegetic_music:
A single tense cello sustained low note with sparse, slow piano high-register drops, building claustrophobic suspense.
```

### 模板 C：AI 漫劇 Stage A「3x3 九宮格同空間鎖臉關鍵幀」模板 (`grid-9panel`)
*(用於 Midjourney / 即夢 / Nano Banana / GPT-Image 一次性生成 9 格連戲分鏡大圖)*

```text
3x3 grid cinematic anime storyboard sheet, 9 distinct sequential panels arranged in 3 rows by 3 columns (Panel 1 top-left to Panel 9 bottom-right), thin black panel borders, 16:9 aspect ratio per panel.
[CHARACTER IDENTITY LOCK]: Young swordsman with silver high ponytail tied with crimson ribbon, a red tear-mole under left eye, wearing dark cyan fitted martial arts robe with bronze cloud-patterned bracers.
[GLOBAL PALETTE LOCK]: Cold Steel Noir palette — abyssal shadow (#080C14), cold slate blue ambient (#1C2D42), sharp cyan blade highlight (#64E8FF), and crimson accent (#C92A2A).
- Panel 1 (Extreme Wide, 24mm low angle, camera 0.4m from wet stone ground): Rain-drenched bamboo forest, protagonist standing with hand on sword hilt, extreme perspective convergence.
- Panel 2 (Medium Shot, 50mm, Dirty Frame 30% bamboo leaves blurred in left foreground): Voyeuristic view through bamboo watching the assassin approaching from behind.
- Panel 3 (Extreme Close-Up, 85mm shallow DOF): Raindrop falling onto the bronze sword guard, reflecting the attacker's cold eyes in the water droplet (breath-holding delay).
- Panel 4 (Medium Close-Up, 24mm close distance): Protagonist's eyes snapping open, thumb pushing the sword guard up by an inch, water splashing off the scabbard.
- Panel 5 (Wide Profile Shot, 50mm, 90-degree perpendicular to action axis, ZERO foreground obstruction): Protagonist lunging forward, drawing the glowing cyan blade in a clean horizontal arc toward the attacker.
- Panel 6 (Close-Up Impact Shot, 90-degree side view, clear unobstructed contact point): Cyan sword blade clashing directly against the attacker's iron gauntlets, bright sparks and circular rain shockwave bursting outward.
- Panel 7 (Medium Shot, 35mm low angle): Attacker skidding backward across wet mud, boots carving two deep tracks in the ground under the impact force.
- Panel 8 (Over-the-Shoulder Close-Up, 85mm telephoto compression): Looking past attacker's blurred shoulder at protagonist lowering center of gravity, blade tip dripping water.
- Panel 9 (Extreme Wide Shot, 100mm telephoto compression): Both figures locked in a silent standoff amidst falling bamboo leaves.
No speech bubbles, no text overlays, no watermarks, consistent facial features and outfit across all 9 panels.
```

### 模板 D：Stage B「首尾幀接龍（FL2VA）」運動過渡模板 (`kling-fl2va`)
*(當上傳九宮格裁切出的 Panel 5 作為首幀、Panel 6 作為尾幀時使用)*

```text
Single continuous camera shot transitioning smoothly from First Frame to Last Frame, 90-degree perpendicular side view with zero foreground obstruction. Camera tracks rapidly rightward (Truck right) following the silver-ponytail swordsman as he shifts his center of gravity onto his front foot, rotates his torso, and swings the cyan-glowing sword horizontally into a direct, heavy collision with the opponent's raised iron gauntlets. Upon blade-to-gauntlet contact at the 1.5s mark, bright metallic sparks and a ring of rainwater mist burst outward, and the opponent's arms buckle backward slightly under the momentum while both characters' robes ripple naturally in the wind. Strictly maintain weapon geometry and character identity; no split screen, no multi-panel grid.
```
