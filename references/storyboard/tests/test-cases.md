# 導演分鏡與鏡頭光學驗收測試用例庫 (Test Cases)

本文件定義針對「導演分鏡三步法」與「焦距景深物理控制」的標準驗收測試案例，包含對照組與實驗組設定、評估維度與驗收標準。

---

## 測試用例 1：流水帳敘事 vs 導演分鏡三步法 (Narrative vs Director Craft)

### 1. 測試目標
驗證在相同敘事目標（「殺手走進破舊旅館房間，發現目標已經被捷足先登」）下，常規流水帳拍法與導演三步法在**戲劇張力、懸念營造與空間立體感**上的差異。

### 2. 測試對照組 (Baseline - 平庸流水帳拍法)
- **提示詞**：
  > Wide shot, a hitman walking into a dimly lit motel room, opening the door, stepping inside, looking around, seeing a dead body on the floor, cinematic lighting, photorealistic.
- **預期缺陷**：
  - AI 產生一個遠處全身走進來的平庸視角，像監控錄影。
  - 毫無緊張感，毫無焦點，缺乏主觀帶入感。

### 3. 測試實驗組 (Experimental - 導演三步法)
- **六要素結構化提示詞**：
  ```markdown
  【鏡頭本質與光學物理】
  - 鏡頭規格：50mm 客觀紀實鏡頭，物理物距 1.8 公尺，光圈 f/2.8。
  - 景深焦點：精準鎖定在殺手緊握消音手槍且指節泛白的右手特寫。

  【構圖層次與前景遮擋 (Dirty Frame)】
  - 前景層：破舊旅館剝落生鏽的鐵門框與斑駁的鎖孔邊緣，佔據畫面左側 30%，劇烈失焦模糊。
  - 中景層：殺手戴著黑色皮手套的手正緩緩推開房門，手背青筋微凸。
  - 背景層：昏暗房間深處，一盞搖晃的鎢絲吊燈，地面上隱約倒映著一灘暗紅色的反光。

  【動態演化與心理節奏延遲】
  - 開幅狀態（0~1.5秒）：鏡頭靜止於門框陰影後，房門微啟一條縫隙，只有微弱風聲與吊燈吱呀聲。
  - 心理延遲（1.5~3秒）：殺手動作突然定格停頓，手電筒微光擦過地板上的血跡倒影，觀眾心跳懸停。
  - 關鍵引爆（3~5秒）：鏡頭緩慢向右側微平移，透過門縫死角驟然揭露倒在陰影中的目標。

  【色卡光影空間綁定】
  - 最深暗部（#0A0E17）：門後未被照亮的走廊死角。
  - 環境基底（#18233C）：房間內部冷冽的陰暗氛圍。
  - 關鍵高光（#D4AF37）：鎢絲吊燈微弱的暖金色邊緣光，勾勒門鎖金屬質感。

  【微表情與角色肢體】
  - 殺手下顎緊咬，瞳孔在微光中微微縮小，呼吸極度放緩，槍口始終壓低保持戒備。

  【四維配音與聲音聯動】
  - 聲音配置：聯動《四維配音法》「沉穩內斂（胸腔低沉）」音色，無台詞，僅有壓抑到極致的微弱氣息吞嚥聲。
  ```

---

## 測試用例 2：廣角空間透視極限對比 (24mm Wide-Angle Physics)

### 1. 測試目標
驗證 AI 模型在接受純文字「24mm wide angle」與接受「24mm + 物理物距 <0.5m + 透視匯聚線」時的光學透視差異。

### 2. 測試對照組 (Baseline)
- **提示詞**：
  > 24mm wide angle lens, a lone traveler standing in a desert ruin, epic scale, 8k, photorealistic.
- **預期缺陷**：畫面只是普通廣闊的風景照，人物很小，空間深度平淡，毫無近大遠小的視覺衝擊。

### 3. 測試實驗組 (Experimental)
- **提示詞**：
  > Ultra-wide 24mm optical lens, camera placed at ground level extremely close (<0.4m) to the dusty tactical boots of the traveler. Extreme near-far perspective exaggeration: massive weathered boot texture in the sharp foreground, leading converging lines of cracked desert ground rushing into the far distance. Deep depth of field f/11, distant ancient monoliths towering on the horizon yet appearing tiny and remote. High psychological isolation, majestic vertical scale.

---

## 測試用例 3：長焦空間壓縮與情緒窒息 (100mm Telephoto Compression)

### 1. 測試目標
驗證 100mm 遠距長焦（物距 >6m）對空間深度的物理壓扁效果，以及對角色緊迫心理的視覺傳遞。

### 2. 測試對照組 (Baseline)
- **提示詞**：
  > 100mm telephoto close up of an anxious detective talking on the phone in a crowded cafe, blurry background, cinematic.
- **預期缺陷**：背景只是標準的 AI 均勻模糊，人物與背景依然有距離感，缺乏背景被「拉平貼在主角臉頰」的壓迫窒息感。

### 3. 測試實驗組 (Experimental)
- **提示詞**：
  > 100mm prime telephoto lens, camera positioned 8 meters away across the cafe. Extreme spatial compression: busy cafe patrons and background neon signs flattened directly against the detective's tense profile with zero perceived depth. Razor-thin depth of field at f/1.4, knife-edge focus only on the sweat bead rolling down the detective's temple. Foreground dirty frame with an out-of-focus coffee cup edge. Massive circular bokeh orbs crowding the frame, conveying inescapable psychological claustrophobia.

---

## 測試用例 4：三位一體全要素融合 (Director Storyboard + Palette v3.0 + 4D Voice)

### 1. 測試場景
「香港 1990 年代昏暗茶餐廳雨夜，兩位舊情人多年後狹路相逢的無聲對峙」。

### 2. 三位一體全要素規格
- **導演分鏡**：100mm 遠距望遠（物距 6m）+ 隔著帶雨滴的窗櫺（Dirty Frame）偷窺 + 倒茶水滿溢而出的延遲節奏。
- **光影色卡**：王家衛復古綠金（暗綠基底 #0D2818 + 琥珀金高光 #E5A93C + 陰影墨黑 #050B08）。
- **四維配音**：女主角台詞「你還記得這裡？」，採用「細膩羞怯/壓抑隱忍」音色，語速偏慢、停頓多、氣息帶顫，字尾微弱上挑帶嘆息。
