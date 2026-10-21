# AI 影片「複製臉 / 克隆臉」失效模式：文獻、緩解對策與管線規則集

> 研究日期：2026-09（來源查閱日以各連結頁面標示為準）
> 研究範圍：MiniMax H3 / 海螺、Wan 2.2 / 2.7、Kling、Seedance、Veo、Runway、Sora 2，以及開源 S2V/多主體模型
> 標籤約定：**【官方】**＝模型商或論文作者的官方文件／原論文；**【社群實測】**＝實務部落格、論壇、GitHub issue 等第一手實測；**【推測】**＝由官方文件與文獻機制推導，本次未找到直接實測佐證

---

## 0. 摘要（TL;DR）

1. **這個失效模式有文獻可對應，但沒有一份文件用「複製臉」這個名字直接描述「1 張參考圖 + 提示詞提到第二人 → 第二人長成參考圖那張臉」。** 最接近、最直接的權威描述是快手＋中科院＋清華的 **Vera** 論文：多人 S2V 會出現 *subject confusion（主體混淆）、attribute swapping（屬性互換）、excessive copying of reference-specific appearance cues（過度複製參考圖外觀線索）*——這正是你觀察到的複製臉的**機制層級描述**。【官方/論文】
2. **複製臉的成因可以從官方文件直接推出。** Wan 2.7 官方 API 參考明確寫著「**參考素材為主體角色時，僅包含單一角色**」；也就是說，只有一張角色參考圖時，模型手裡只有 **一個**身分可用，提示詞裡冒出第二個人，模型只能從這唯一的身分「複寫」出第二張臉。【官方】
3. **實務上最有效的三招**（皆有實測或官方文件支撐）：(a) **一個 clip 只放一個有參考圖的角色**，第二人改用「先合成含兩人的乾淨首幀 → 走 I2V / 分鏡板」；(b) **否定提示詞固定加 `duplicate faces` / `重複的臉`**；(c) **用三視圖（含背面）裁切當參考圖**，並在提示詞裡用「圖1 / Image 1」這類明確指代鎖定每張參考圖。【社群實測＋官方】
4. **背景路人畫風不一致是另一個獨立問題**，文獻與實務一致支持的路線是：不要在提示詞裡描述路人 → 用景深／剪影／虛化處理 → 或在後期用固定背景板 + 調色統一。【社群實測】
5. **身分鎖定的天花板很低。** OpenS2V-Eval 基準上，FaceSim（身分相似度）最高的商用模型 Kling 1.6 只有 **40.1%**，開源最好的 VACE-14B 為 **55.09%**——「一次鎖幾個身分」目前沒有任何模型做到可靠。【官方/基準】
6. **換管線模式是有效的退路**：目前唯一「一等公民」級的多主體參考是 **Wan 2.7 R2V（≤5 個媒體、逐項指代、每個主體單一角色）**、**Kling Elements（1–4 張）**、**Veo 3.1 Ingredients to Video**、**Phantom（≤4 張）**、**BindWeave**；而 **H3 的官方範例本身就是「把男女主角放進同一張參考圖」**。【官方】

---

## 1. 失效模式是否被記錄在案？

### 1.1 最直接的一份論文：Vera（快手 + 中科院 + 清華）

> Vera: Identity-Faithful Human Subject-to-Video Generation, arXiv:2607.20247v1（2026-07-22）
> 來源：[arXiv 全文](https://arxiv.org/html/2607.20247v1) ｜ [arXiv 摘要](https://arxiv.org/abs/2607.20247)

Vera 摘要與引言逐字點名了三個與你的觀察完全對應的失效模式 【官方/論文】：

- 「in multi-person scenarios, where **incorrect identity-role binding** leads to **subject confusion, attribute swapping, and excessive copying of reference-specific appearance cues**」
  → 多人場景下，參考身分與提示詞角色綁錯，會造成主體混淆、屬性互換、**以及過度複製參考圖的外觀線索**。你的「第二人長成參考圖那張臉」就是 "excessive copying of reference-specific appearance cues" 的教科書表現。
- 「multi-person S2V requires not only identity preservation, but also **identity-role-trajectory binding**: multiple reference identities must be correctly associated with multiple textual roles and generated trajectories.」
  → 模型需要的是「身分→角色→軌跡」的綁定。當你只給 1 個身分卻寫了 2 個角色，綁定在數學上不可能成立。
- 「**Naively injecting reference images** into the video backbone can cause the model to treat reference views as static templates, leading to **pose locking, view collapse, and over-preservation of reference-specific pose and appearance cues**」
  → 參考圖注入過強會「視角塌陷」（view collapse）。這解釋了為什麼「主角背對鏡頭」時，模型傾向把參考圖的正臉硬貼上去。

Vera 的定性評測段落也直接描述了基準模型的行為 【官方/論文】：

- 「Baseline methods often focus on only part of the scene, **confuse character roles, or blend identities across subjects**, especially in the birthday-party and wedding examples.」
  → 基準模型會「**在多個主體間混合身分**」，在派對與婚禮這類多人場景特別明顯。

**對應你的觀察**：「參考圖只給一人，提示詞提到另一人」→ 模型只有一個身分 token 可分配 → 第二人只能用同一份身分特徵複寫。**【推測】**（本次未找到直接以「複製臉／clone face」命名的實測貼文，但機制在論文中被明文描述，且與你 4/4 的觀測一致）

### 1.2 基準測試層面的佐證：OpenS2V-Eval / OpenS2V-Nexus

> OpenS2V-Nexus: A Detailed Benchmark and Million-Scale Dataset for Subject-to-Video Generation, arXiv:2505.20292（北大 + 羅切斯特大學 + Rabbitpre AI）
> 來源：[專案頁](https://pku-yuangroup.github.io/OpenS2V-Nexus/) ｜ [論文](https://arxiv.org/abs/2505.20292) ｜ [排行榜](https://huggingface.co/spaces/BestWishYsh/OpenS2V-Eval)

- 基準把 S2V 拆成 **七大類**，其中 **multi-face-to-video（多人臉）與 multi-body-to-video（多人身體）是獨立類別**，與單人分類開。【官方/基準】 → 官方承認「多人參考」是一個**獨立的、更高難度的任務**，不是單人任務的延伸。
- 論文列出的三大挑戰裡，第 3 條是「**Inadequate human fidelity: Current models often struggle to preserve human identity as effectively as they do non-human entities**」——人類身分保真度本身就遠低於非人物主體。【官方/基準】
- 第 2 條挑戰是「**Copy-paste issue**: The model tends to directly transfer the pose, lighting, and contours from the reference image to the video」。【官方/基準】 → 這是「參考圖臉被複寫到不該出現的人身上」的近親現象。

### 1.3 中文社群的既有紀錄

| 來源 | 內容 | 等級 |
|---|---|---|
| [B 站：AI 漫劇多人場景總翻車？撞臉、崩壞、站位亂？](https://www.bilibili.com/video/BV1V5EC6tEzK/) | 影片標題直接把「**撞臉**」列為 AI 漫劇多人場景三大翻車原因之一（另兩項為崩壞、站位亂），並宣稱提供「AI 視頻控制人物站位方法」 | 【社群實測】 |
| [知乎：生成100張臉，90張是同一張——AI「撞脸」怎么破](https://zhuanlan.zhihu.com/p/2046171615092909849) | 「撞臉」在中文圈的標準用語在此定型：不同角色出來是同一張臉，**骨相一模一樣**，只換髮型衣服。文章同時列出 Midjourney `--cref`、SD 的 IP-Adapter FaceID / InstantID / PuLID、正負面提示詞控骨相、多 seed 挑選、LoRA 臉模、**後期換臉**六種解法 | 【社群實測】 |
| [CSDN：AI 動漫短劇全流程實操（wudi416）](https://blog.csdn.net/wudi416/blog/article/details/158233761) | 以「**固定背景模板和畫風關鍵詞**維持場景統一」＋「種子值鎖定、LoRA、**局部重繪**」三招處理角色一致性 | 【社群實測】 |
| [CSDN：AI 短劇製作全流程（llooyyuu）](https://blog.csdn.net/llooyyuu/article/details/162750388) | 內含「常見翻車場景及應對策略」表，明列「**多人鏡頭中角色錯亂** → 原因『參考圖未被 AI 正確識別』→ 對策『**分別上傳多人參考圖，提示詞明確標註位置**』」 | 【社群實測】 |
| [知乎：解決 AI 短劇角色、場景、聲音一致性，3 個關鍵方案](https://zhuanlan.zhihu.com/p/2050534732618905039) | 「給角色檔案」＋「拆解角色資訊為四類（不可變身分特徵／可小幅變化的表情／隨鏡頭變化的動作／絕不可變的服裝配飾）」 | 【社群實測】 |

> ⚠️ **檢索限制（誠實揭露）**：
> - **Reddit（r/StableDiffusion、r/AI_Video、r/LocalLLaMA）本次無法取得**——`agent-reach doctor` 回報本機未安裝任何 Reddit 後端（Reddit 無零配置路徑，需登入態），OpenCLI / rdt-cli 皆為 `status: off`。
> - **Discord 摘要**同樣無法取得（無登入態）。
> - **X（Twitter）**依指示未使用。
> - GitHub Issue 檢索可透過公開 API 執行，但以「duplicate face / same face / two characters」等關鍵字搜尋 ComfyUI-WanVideoWrapper 只命中 5 筆且多為無關（模型發布、動畫 workflow 討論），**未找到直接描述「第二人複製主體臉」的 issue**。結論：這個症狀在 GitHub issue 系統裡**沒有被正式登記成 bug**，這本身就是一個可寫進管線文件的「未被社群充分記錄的失效模式」事實。【推測】

### 1.4 為什麼「1 張參考圖 + 提示詞提到第二人」幾乎必然出事（機制推導）

把官方規格與論文明說放在一起，機制是封閉的 【官方＋推測】：

1. **模型手裡只有一個身分 token。** 參考槽位有限且每個主體只能綁一個身分。Wan 2.7 官方：「**參考素材為主體角色時，僅包含單一角色**」。【官方】
2. **提示詞提到第二人 = 產生了第二個「角色需求」。** 但沒有第二份身分可分配。
3. **模型被迫在「不生成這個人」與「複寫唯一的身分」之間選。** 生成太少人會違反提示詞遵循（prompt following 會掉分），複寫身分則保留提示詞遵循與畫面可辨識度。**從基準的 X-CLIP / GmeScore 權重來看，複寫是更划算的策略。** 【推測】
4. **面對「背對鏡頭」時更糟。** 參考注入過強會造成 **view collapse（視角塌陷）**（Vera 引言）＋ **pose locking**；模型傾向把參考圖的正臉特徵貼到本該看不到正臉的人身上。【官方/論文】
5. **H3 特有的額外放大器：提示詞擴寫預設開啟。** H3 Max 的 `extra.prompt_expansion_mode` 預設為 `balanced`（即自動改寫提示詞），H3 雲端也有 **H3-Context-IR** 端點可做「深度多模態解讀並產生強化提示詞」。**自動擴寫可能自行補出第二個人物。** 【官方】
6. **H3 還有「參考與首尾幀互斥」的硬限制**：一旦出現 `reference_image` / `reference_video` / `reference_audio`，`first_frame` / `last_frame` 必須缺席。**所以「既想用參考圖鎖臉、又想用首幀控制構圖」在 H3 裡是做不到的**——這直接決定了管線必須在 R2V 與 I2V 之間擇一。【官方】

---

## 2. 已知緩解對策（逐項附來源與等級）

### 2.1 結構面：單一主體 per clip（最核心）

| # | 對策 | 說明 | 來源 | 等級 |
|---|---|---|---|---|
| M1 | **一個 clip 只放一個有參考圖的角色** | 第二人若必須出現，改用「合成首幀 → I2V」或「分鏡板」路徑，**不要**在同一個 R2V 請求裡只給一人參考圖卻在文字裡寫第二人 | [黃果製片](https://huangguo.design/blog/ai-short-drama-character-consistency)：「單人鏡頭用『角色一致 (r2v)』綁定對應主角的參考圖；雙人同框鏡頭可以先合成或選定包含兩位角色的乾淨首幀圖，再用『圖生視頻 (i2v)』或『分鏡 (board)』推進動作」 | 【社群實測】 |
| M2 | **把兩人合成進同一張參考圖** | 這正是 H3 官方的做法 | [MiniMax H3 Feature Highlights](https://platform.minimax.io/docs/guides/video-prompt)：短劇案例提示詞寫「**Image 1: male and female leads. Image 2: setting.**」；眼鏡廣告案例寫「**Image 1: two full-body female models. Image 2: facial details.**」 | 【官方】 |
| M3 | **參考槽位 per-actor 分配 + 空間遮罩** | 「多人鏡頭中角色錯亂」的標準解 | [PixMind 角色一致性指南](https://www.pixmind.io/posts/ai-video-character-consistency-guide)：「**Dedicate a reference slot per actor and use spatial masks** (Seedance R2V, Runway region tools)」 | 【社群實測】 |
| M4 | **分別上傳多人參考圖 + 提示詞標註位置** | 中文實務的標準寫法 | [CSDN AI 短劇全流程](https://blog.csdn.net/llooyyuu/article/details/162750388)：「畫面左側為林悅，畫面右側為張組長，兩人隔著會議桌站立」 | 【社群實測】 |
| M5 | **用多宮格（故事板）參考圖一次載入多角色** | 官方支援單張多宮格，官方範例就含兩個角色 | [萬相 2.7 參考生影片使用指南](https://help.aliyun.com/zh/model-studio/video-to-video-guide)：多宮格範例提示詞寫「角色： 小男孩探險家：圓帽、背包、短斗篷。**小伙伴：會飛的小機器人**，圓形身體，藍色發光眼。」並建議「**單次僅輸入一張多宮格圖**」 | 【官方】 |
| M6 | **把「背對鏡頭」的正臉債還清** | 主體轉身／背對時最容易丟臉 | [PixMind H3 指南](https://www.pixmind.io/posts/minimax-h3-character-consistency)：「Fast spins, occlusion (a hand passing in front of the face), and **extreme head turns can cause the model to lose the face mid-clip and reconstruct a slightly different one** when the face reappears.」對策：「plan shots so the face stays at least partially visible through the motion」，且「**if a shot must break identity through motion, cut around the break in the edit**」 | 【社群實測】 |
| M7 | **臉太小就會退化** | 臉佔畫面 < ~20% 時模型會補一張泛用臉 | [PixMind 角色一致性指南](https://www.pixmind.io/posts/ai-video-character-consistency-guide)：「the face drops below about 20 percent of the frame and the model fills the gap with a generic face」；對策：「crop the reference tighter, or **shoot medium and close-up for identity-critical beats and reserve wide shots for establishing context**」 | 【社群實測】 |

### 2.2 參考圖面：裁切、分槽、明確指代

| # | 對策 | 說明 | 來源 | 等級 |
|---|---|---|---|---|
| R1 | **三視圖轉身圖（正面／四分之三／側面／背面／臉部細節）** | 給模型所有可能切到的角度，**包含背面**——這是「背視角」最直接的緩解 | [PixMind 角色一致性指南](https://www.pixmind.io/posts/ai-video-character-consistency-guide)：「A front, three-quarter, profile, **back** and face-detail sheet gives the model every angle it might cut to.」 | 【社群實測】 |
| R2 | **中文實務的「正面/側面/背面三視圖 + 裁切分餵」** | 先做三視圖，再裁成單張分別餵 | [知乎：即夢＋可靈輕鬆實現 AI 影片主體人物和風格的一致性](https://zhuanlan.zhihu.com/p/1887821957254329621)：「生成**正面，側面，背面三視圖**，然後把不同角色的女孩**分別裁剪出來**備用」 | 【社群實測】 |
| R3 | **提示詞用「圖1 / Image 1」逐一指代每張參考圖** | 順序 = media 陣列順序；圖與視頻分別計數 | [萬相 2.7 API 參考](https://help.aliyun.com/zh/model-studio/wan-video-to-video-api-reference)：「使用『圖1、圖2』指代 reference_image，『視頻1、視頻2』指代 reference_video，英文寫為『Image 1』『Video 1』……順序與 media 陣列順序一致」 | 【官方】 |
| R4 | **H3 用 "reference images 1 and 2" / "reference video 1" 的語法** | 官方範例提示詞：「the character's appearance follows **reference images 1 and 2**」、「following the motion in **reference video 1**」、「Voice timbre follows **reference audio 1**」 | [MiniMax H3 Video Generation](https://platform.minimax.io/docs/guides/video-generation) | 【官方】 |
| R5 | **每張參考圖只負責一件事** | 兩張不同臉的參考圖會逼模型「仲裁」，表現為閃爍與漂移 | [PixMind H3 指南](https://www.pixmind.io/posts/minimax-h3-character-consistency)：「Two character images with different faces, or a character reference whose wardrobe conflicts with an outfit reference, **force the model to arbitrate**」 | 【社群實測】 |
| R6 | **在提示詞裡精確描述每張參考圖的內容** | 開源 S2V 模型的官方建議 | [Phantom README](https://github.com/Phantom-video/Phantom)：「we recommend that you **describe the visual content of the reference image as accurately as possible** when writing `--prompt`. For example, "examples/ref1.png" can be described as "a toy camera in yellow and red with blue buttons"」 | 【官方】 |
| R7 | **主參考圖的技術條件** | 均勻光、視線高度正面、純色背景、無遮擋；主體佔畫面有意義比例 | [PixMind H3 指南](https://www.pixmind.io/posts/minimax-h3-character-consistency) | 【社群實測】 |
| R8 | **一張黃金母圖（Master Reference）永不更換** | 跨集、跨鏡一律同一張；不要用上一集生成圖的截圖接力 | [黃果製片](https://huangguo.design/blog/ai-short-drama-character-consistency)：「**禁止跨集換參考圖**……不要拿上一集生成的模糊影片截圖當下一集的參考圖，否則誤差會像複印機一樣逐集放大」；同時要求母圖為「正側 30 度以內」的靜態高清圖 | 【社群實測】 |
| R9 | **參考影響力 65–75% 甜蜜點** | 太高＝動作僵硬；太低＝身分漂移 | [PixMind H3 指南](https://www.pixmind.io/posts/minimax-h3-character-consistency)：「Community group tips for MiniMax H3-style subject reference consistently land this setting in the **65 to 75 percent** range」 | 【社群實測】 |

### 2.3 提示詞面：身分區塊、否定提示詞、消歧

| # | 對策 | 說明 | 來源 | 等級 |
|---|---|---|---|---|
| P1 | **否定提示詞加入 `duplicate faces` / `duplicate faces, deformed hands` 等** | 這是文獻與實務中**唯一直接針對「複製臉」的否定詞** | [PixMind 角色一致性指南](https://www.pixmind.io/posts/ai-video-character-consistency-guide)：「Add a negative prompt that bans wrong age, unwanted accessories and **"duplicate faces."**」並給出範例 `wrong age, beard, glasses, hat, duplicate faces, deformed hands`；同文指出 PixVerse V6 建議「run negative prompts against **wrong-age and duplicate-face** outputs」 | 【社群實測】 |
| P2 | **身分區塊（identity block）逐字複製，不改寫同義詞** | 同義詞會被切成不同 token，模型視為不同人 | [PixMind 角色一致性指南](https://www.pixmind.io/posts/ai-video-character-consistency-guide)：「*"Brunette"* and *"shoulder-length dark brown hair"* tokenize differently, and the model treats them as different people. Treat your identity block like source code」；30 鏡實測：同時鎖母圖與身分區塊 **24/30**，純提示詞只有 **9/30** | 【社群實測】 |
| P3 | **不要在提示詞裡重述角色的臉** | 已經有參考圖時再重述＝邀請模型重新詮釋 | [PixMind H3 指南](https://www.pixmind.io/posts/minimax-h3-character-consistency)：「Re-describing the character in the prompt … invites reinterpretation, which is the exact failure mode the reference is supposed to prevent」 | 【社群實測】 |
| P4 | **四要素身分錨點前綴** | 年齡合規宣告＋骨相膚色＋髮型定式＋核心服裝配飾 | [黃果製片](https://huangguo.design/blog/ai-short-drama-character-consistency) | 【社群實測】 |
| P5 | **在提示詞裡為每個主體標註位置關係** | 「左／右」「隔著桌子」等空間錨點 | [CSDN AI 短劇全流程](https://blog.csdn.net/llooyyuu/article/details/162750388) | 【社群實測】 |
| P6 | **提示詞改寫公式：主體動作＋環境變化＋鏡頭運動＋風格限定＋時長＋負面排除** | 「風格限定」與「負面排除」是固定槽位 | [CSDN AI 短劇全流程](https://blog.csdn.net/llooyyuu/article/details/162750388) | 【社群實測】 |
| P7 | **正負面提示詞都寫臉部特徵** | 針對「所有人都長同一張臉」而非「複製臉」 | [知乎：AI 撞臉怎麼破](https://zhuanlan.zhihu.com/p/2046171615092909849) | 【社群實測】 |

### 2.4 生成模式切換（換管線模式 = 有效退路）

| # | 對策 | 說明 | 來源 | 等級 |
|---|---|---|---|---|
| G1 | **Chain Continuity 首幀錨定法** | ① 用 AI 生成一個**同時含兩位角色**的主鏡頭（這是唯一一次「創造世界」）→ ② 鎖定第一幀 → ③ 對主關鍵幀下指令「**凍結角色和場景，把相機移動到［新角度］**」生出各 OTS setup frames → ④ 對每張 setup frame 生成表演。**因為所有鏡頭的起點是同一幀，兩人的臉天然鎖死** | [CSDN：AI 影片全流程實戰](https://blog.csdn.net/chajinglong/article/details/161870403) | 【社群實測】 |
| G2 | **不要用「放大」假裝特寫** | 中景裁切放大會造成透視錯亂；每個鏡頭都要是獨立 setup frame | 同上 | 【社群實測】 |
| G3 | **首幀鏈接（first-frame chaining）** | 第 N 段的最後一幀當作第 N+1 段的 I2V 首幀 | [PixMind 角色一致性指南](https://www.pixmind.io/posts/ai-video-character-consistency-guide) | 【社群實測】 |
| G4 | **單次多鏡生成優於拼接** | 一鏡到底能避免拼接漂移 | [PixMind 角色一致性指南](https://www.pixmind.io/posts/ai-video-character-consistency-guide)（Seedance 2.5 單次約 30 秒、PixVerse V6 約 15 秒，**來源為預覽資訊、未經官方證實**） | 社群實測（數字為第三方預覽） |
| G5 | **影片到影片 / 風格轉移** | 固定一張風格分鏡圖作為影片輸入，讓模型只負責動作 | [VACE](https://arxiv.org/abs/2503.07598)（reference-to-video + video-to-video + masked video-to-video 統一框架） | 【官方/論文】 |
| G6 | **Wan 2.2-Animate / Wan-Animate-2（動作遷移 + 身分保留 + 視角控制）** | 從「生成」轉成「動作遷移」：身分由參考圖決定，動作由驅動影片決定，幾乎不會憑空生出第二人。Wan-Animate-2 額外加入 **text-driven viewpoint control**，可解耦輸出視角與驅動影片 | [Wan-Animate-2 README](https://github.com/Wan-Video/Wan-Animate-2)：「achieves high-fidelity motion generation and **strong identity preservation** … adds **text-driven viewpoint control to decouple the output camera perspective from the driving video**」；[Wan2.2 README](https://github.com/Wan-Video/Wan2.2) | 【官方】 |
| G7 | **口型／配音與畫面同 pass 生成** | 避免後期配音造成嘴型不同步（這也是「分鏡切點」被迫硬切的來源） | [PixMind 角色一致性指南](https://www.pixmind.io/posts/ai-video-character-consistency-guide) | 【社群實測】 |
| G8 | **分割鏡頭、把「提及第二人」從提示詞刪掉** | 若該段其實不需要第二人可見（只有聲音／畫外音），就**刪掉這個人物描述**改用畫外音 | — | **推測**（但與 M1 同源，邏輯必然） |

### 2.5 後期面

| # | 對策 | 說明 | 來源 | 等級 |
|---|---|---|---|---|
| P1 | **剪掉／移除多餘的路人** | 後期用遮罩＋修補把路人擦掉 | [百度文庫：影片裡多餘的人怎麼去掉](https://wenku.baidu.com/view/08d95741826fb84ae45c3b3567ec102de3bddf52.html) | 【社群實測】 |
| P2 | **局部重繪修掉漂移的臉** | 不必整段重跑 | [CSDN AI 動漫短劇全流程](https://blog.csdn.net/wudi416/blog/article/details/158233761)：「**局部重繪**確保角色一致性」 | 【社群實測】 |
| P3 | **後期統一調色** | 把不同段的色調拉齊，可部分掩蓋畫風落差 | [CSDN AI 短劇全流程](https://blog.csdn.net/llooyyuu/article/details/162750388)：「點擊調節，對第一個鏡頭調色後點擊**應用到全部**，統一所有鏡頭的色調」 | 【社群實測】 |
| P4 | **後期換臉** | 以最終定裝照／母圖做 face-swap，保證身分 | [知乎：AI 撞臉怎麼破](https://zhuanlan.zhihu.com/p/2046171615092909849)（「先出圖，再換臉」）；[搜狐：AI 短劇角色一致性的 7 種方案](https://www.sohu.com/a/1038316934_121123989) | 【社群實測】 |
| P5 | **剪輯時把切點藏在動作裡** | 轉身、開門、路人走過等遮蔽接縫 | [PixMind 角色一致性指南](https://www.pixmind.io/posts/ai-video-character-consistency-guide)：「Hide cuts inside motion, like a turn, a door opening, or a passing object」 | 【社群實測】 |
| P6 | **用 LoRA / Soul ID 訓練身分層** | 20 張以上近期照片訓練 | [PixMind 角色一致性指南](https://www.pixmind.io/posts/ai-video-character-consistency-guide)：「train an identity layer like a LoRA on Stable Diffusion or Soul ID on Higgsfield on 20 or more recent photos」 | 【社群實測】 |

---

## 3. 哪些模型／功能有一等公民級的多主體參考？

### 3.1 官方文件對照表

| 模型／功能 | 多主體參考 | 硬性上限 | 官方指代語法 | 來源 |
|---|---|---|---|---|
| **Wan 2.7 參考生影片（wan2.7-r2v）** | ✅ 一等公民：「多主體參考＋音色定制」，明確支援「多角色同框互動與音色區分」 | **參考圖＋參考影片 ≤ 5**；首幀 ≤ 1；每個主體參考素材**僅含單一角色** | 「圖1／圖2」「視頻1／視頻2」／"Image 1"/"Video 1"；順序＝media 陣列順序；圖與影片分別計數；只有一張時可簡化為「參考圖片」 | [使用指南](https://help.aliyun.com/zh/model-studio/video-to-video-guide) · [API 參考](https://help.aliyun.com/zh/model-studio/wan-video-to-video-api-reference) · [ComfyUI Wan2.7 教學](https://docs.comfy.org/tutorials/partner-nodes/wan/wan2-7) |
| **Kling Elements** | ✅ 一等公民：「select the subjects (people, animals, objects, or **scenes**) in the images as elements, and describe their actions and interactions」 | **1–4 張圖** | 把圖中的主體挑出來當 element；場景與服裝也可當 element | [Kling 官方 Characters/Elements 指南](https://kling.ai/quickstart/ai-video-character-consistency) · [Element Library 指南](https://kling.ai/quickstart/klingai-element-library-3-user-guide) |
| **Veo 3.1 Ingredients to Video** | ✅ 一等公民：可混合 characters、objects、textures、stylized backgrounds | **官方未公布 ingredient 數量上限**（第三方稱 3 張，未經官方證實） | 官方 pro tip：先用 Nano Banana Pro 製作 ingredient 圖，再餵 Veo | [Google 官方部落格（2026-01-13）](https://blog.google/innovation-and-ai/technology/ai/veo-3-1-ingredients-to-video/) |
| **MiniMax H3 / H3 Max** | ✅ 有多模態參考槽，但**官方範例把兩位主角放進同一張參考圖** | 參考圖 ≤ 9、參考影片 ≤ 3、參考音訊 ≤ 3，**混合總數 ≤ 12 個檔案**；提示詞 ≤ 7000 字元 | "reference images 1 and 2" / "reference video 1" / "reference audio 1"；role 分 first_frame / last_frame / reference_image / reference_video / reference_audio；**首尾幀與參考互斥** | [Video Generation 指南](https://platform.minimax.io/docs/guides/video-generation) · [H3 Feature Highlights](https://platform.minimax.io/docs/guides/video-prompt) · [Create API](https://platform.minimax.io/docs/api-reference/video-generation-v2-create) |
| **Sora 2 Characters（原 Cameo）** | ✅ 一等公民（條件式 on character、style、setting 參考） | 官方未公布 API 上限 | — | [OpenAI Sora 2 發表頁](https://openai.com/index/sora-2/)；第三方彙整指出為 **App-only、尚未開放 API**（[PixMind](https://www.pixmind.io/posts/ai-video-character-consistency-guide)） |
| **Seedance 2.0 / 2.5** | ✅ 支援多模態參考槽＋區域編輯；第三方稱參考槽由 12 增至 50（**預覽資訊、未經官方證實**） | 官方未在行銷頁公布 | 官方：「集成了目前業界最全面的多模態內容參考和編輯能力」 | [Seedance 2.0 官方頁](https://seed.bytedance.com/zh/seedance2_0) · [Seedance 1.0 官方頁](https://seed.bytedance.com/zh/seedance) |
| **Runway Act-Two** | ⚠️ **官方明講：Act-Two 目前只支援單一角色輸入**；官方另給了一篇「用 Gen-4 Image + Gen-4 Video 合成多角色對話」的教學 | 單角色 | — | [Runway 官方：Creating Multi-Character Dialogues with Act-Two](https://help.runwayml.com/hc/en-us/articles/41748090660499-Creating-Multi-Character-Dialogues-with-Act-Two)（頁面 Cloudflare 保護，內容依官方搜尋摘要；本報告未能直接讀取正文） · [Act-Two 說明](https://help.runwayml.com/hc/en-us/articles/42311337895827-Performance-Capture-with-Act-Two) |
| **Phantom（開源 S2V）** | ✅ 「a unified video generation framework for **single and multi-subject references**」 | **≤ 4 張** `--ref_image` | 官方建議在 prompt 描述每張參考圖的視覺內容 | [Phantom README](https://github.com/Phantom-video/Phantom) · [專案頁](https://phantom-video.github.io/Phantom/) |
| **BindWeave（ByteDance，ICLR 2026）** | ✅ MLLM-DiT 架構，**entity grounding**（用 MLLM 解析複雜提示詞並輸出 subject-aware hidden states） | 官方未在 README 給出硬上限 | 內建可選的 MLLM 提示詞改寫（prompt refinement）步驟 | [BindWeave README](https://github.com/bytedance/BindWeave) |
| **VACE** | ✅ reference-to-video + video-to-video + masked video-to-video 統一框架 | — | — | [arXiv 2503.07598](https://arxiv.org/abs/2503.07598) |
| **Wan 2.2-S2V-14B / Wan-Animate-14B / Wan-Animate-2** | ❌ **單主體**：S2V 只吃一張 `--image`；Animate 只吃一張角色圖＋一段驅動影片 | 1 個角色 | — | [Wan2.2 README](https://github.com/Wan-Video/Wan2.2) · [Wan-Animate-2 README](https://github.com/Wan-Video/Wan-Animate-2) |
| **Vidu** | 第三方頁面稱可上傳至多 7 張參考圖 | 7（未經官方文件二次確認） | — | [Vidu 官方行銷頁](https://www.vidu.com/ai-reference-to-video) |

### 3.2 「主體背對鏡頭 + 另一角色正面」誰處理得最好？

| 方案 | 判斷 | 依據 |
|---|---|---|
| **Wan 2.7 R2V（給兩個主體各一張參考圖，其中一人用背面／全身裁切）** | ✅ **最推薦**。官方支援「圖1／圖2」逐一指代，每個主體參考素材限單一角色，且提供 `reference_voice` 為每個主體分別指定音色。背面裁切能提供「這個人的背影／體型／服裝」線索，避免模型複寫正臉 | [萬相 2.7 使用指南](https://help.aliyun.com/zh/model-studio/video-to-video-guide) |
| **H3 走 I2V（先合成含兩人的首幀）** | ✅ 推薦。H3 官方範例本身就是「兩人放同一張圖」；走 I2V 時兩人的臉完全由首幀決定，模型沒有「第二張臉」的自由度 | [MiniMax H3 Feature Highlights](https://platform.minimax.io/docs/guides/video-prompt) · [Create API（首尾幀與參考互斥）](https://platform.minimax.io/docs/api-reference/video-generation-v2-create) |
| **Wan-Animate-2（動作遷移）** | ✅ 若第二人只需要「有動作的背影」，可先以 Animate 生成主角動作，再以分層合成加入背影 | [Wan-Animate-2 README](https://github.com/Wan-Video/Wan-Animate-2) |
| **Runway Act-Two** | ⚠️ 官方明講只支援單一角色，**多角色需自己用 Gen-4 Image + Gen-4 Video 合成** | [Runway 官方教學](https://help.runwayml.com/hc/en-us/articles/41748090660499-Creating-Multi-Character-Dialogues-with-Act-Two) |
| **Sora 2 Characters** | ⚠️ 功能是一等公民，但**社群彙整指出為 App-only、尚未開放 API**，做管線化受限 | [OpenAI Sora 2](https://openai.com/index/sora-2/) · [PixMind](https://www.pixmind.io/posts/ai-video-character-consistency-guide) |
| **純 R2V、只給一張參考圖卻在提示詞寫兩人** | ❌ **必然落入本報告描述的失效模式** | [Vera 論文](https://arxiv.org/html/2607.20247v1)（身分角色綁定機制） + [萬相 2.7 API 參考](https://help.aliyun.com/zh/model-studio/wan-video-to-video-api-reference)（單一角色限制） |

---

## 4. 背景路人（未參考的路人群眾）畫風一致性

### 4.1 為什麼會畫風不一致？

- 參考圖／參考影片是**唯一**攜帶「畫風」資訊的通道。未被參考的背景人，模型只能從訓練分布裡取「最常見的人」——而真實人群的訓練素材遠多於特定動畫風格，所以背景人傾向回到**寫實**。【推測，但與「撞臉＝模型退回預設值」的機制一致】(<https://zhuanlan.zhihu.com/p/2046171615092909849>)
- 實務上對「風格參考」的已知限制：**「對超寫實攝影風格效果稍弱」**，且「**不要指望一張參考圖能解決所有風格的漂移——它是錨點，不是萬能膠**」。【社群實測】(<https://ai-pulse-lab.com/tips/%E5%8D%B3%E6%A2%A6%E5%8F%82%E8%80%83%E5%9B%BE%E5%8A%9F%E8%83%BD%E6%B7%B1%E5%BA%A6%E7%94%A8%E6%B3%95-%E6%8E%A7%E5%88%B6%E9%A3%8E%E6%A0%BC%E4%B8%80%E8%87%B4%E6%80%A7>)
- 多數影片模型在「**人物數量增多時容易邏輯變形**」（多足、手指錯亂）。【社群實測】(<https://ai-pulse-lab.com/tips/%E5%8D%B3%E6%A2%A6%E5%8F%82%E8%80%83%E5%9B%BE%E5%8A%9F%E8%83%BD%E6%B7%B1%E5%BA%A6%E7%94%A8%E6%B3%95-%E6%8E%A7%E5%88%B6%E9%A3%8E%E6%A0%BC%E4%B8%80%E8%87%B4%E6%80%A7>)

### 4.2 六個選項的文獻支持度

| 選項 | 支持度 | 依據 |
|---|---|---|
| **(a) 把路人整個從鏡頭裡拿掉**（改成空鏡、景深外、或純畫外音） | ⭐⭐⭐ **文獻支持最強** | 這是唯一能從根上消除「未參考主體」的作法，與 M1「單一主體 per clip」同源；且「多人鏡頭中角色錯亂」的標準解就是「**分別上傳多人參考圖**」——不給參考圖就等於放任模型複寫 | [CSDN AI 短劇全流程](https://blog.csdn.net/llooyyuu/article/details/162750388) · [黃果製片](https://huangguo.design/blog/ai-short-drama-character-consistency) |
| **(b) 給路人／群眾自己的參考圖** | ⭐⭐ **可行但昂貴** | Wan 2.7 最多 5 個媒體、Kling 最多 4 張、H3 最多 9 張參考圖，且「每個主體參考素材僅含單一角色」，意味著一個路人也要佔一個槽位。實際上多數團隊會放棄 | [萬相 2.7 API](https://help.aliyun.com/zh/model-studio/wan-video-to-video-api-reference) · [Kling Elements](https://kling.ai/quickstart/ai-video-character-consistency) · [MiniMax H3 指南](https://platform.minimax.io/docs/guides/video-generation) |
| **(c) 把群眾處理成剪影／失焦／景深** | ⭐⭐⭐ **文獻／攝影語法支持強** | 這是影視語言的既有解法：把群眾推到焦外既解決一致性，也解決「不該被注意」的分鏡意圖。PixMind 對 wide shot 的建議也一致：「**reserve wide shots for establishing context**」，並指出臉 < 20% 畫面就會退化。【攝影語法部分為推測】；臉佔比的部分為【社群實測】 | [PixMind 角色一致性指南](https://www.pixmind.io/posts/ai-video-character-consistency-guide) |
| **(d) 後期合成 AI／繪製的群眾板（crowd plate）** | ⭐⭐ **可行，屬後期段** | 前期先做「乾淨底板」（無路人）→ 影片生成 → 後期把群眾層疊上去。AI 動漫短劇全流程文獻即主張「**固定背景模板**」＋「種子值鎖定」＋「局部重繪」 | [CSDN AI 動漫短劇全流程](https://blog.csdn.net/wudi416/blog/article/details/158233761) |
| **(e) Inpainting / outpainting 工作流** | ⭐⭐ **可行** | Wan 2.7 官方即提供 `first_frame` ＋ 參考圖的混合模式；VACE 提供 masked video-to-video，可用遮罩局部重生 | [萬相 2.7 使用指南](https://help.aliyun.com/zh/model-studio/video-to-video-guide) · [VACE](https://arxiv.org/abs/2503.07598) |
| **(f) 純文字 style-lock 描述** | ⭐ **最弱，只能當輔助** | 中文實務的一致對策是「**預先固定場景描述模板**」＋「**固定每個場景的光線描述詞**」，但那是為了讓各段場景彼此一致，**不是**為了讓未參考的路人變成同一畫風。即夢風格參考的實測也直接點出其極限 | [CSDN AI 短劇全流程](https://blog.csdn.net/llooyyuu/article/details/162750388) · [AI Pulse 即夢參考圖](https://ai-pulse-lab.com/tips/%E5%8D%B3%E6%A2%A6%E5%8F%82%E8%80%83%E5%9B%BE%E5%8A%9F%E8%83%BD%E6%B7%B1%E5%BA%A6%E7%94%A8%E6%B3%95-%E6%8E%A7%E5%88%B6%E9%A3%8E%E6%A0%BC%E4%B8%80%E8%87%B4%E6%80%A7) |

### 4.3 綜合建議順序（最有效 → 最省事）

1. **先問：這個鏡頭真的需要看見路人嗎？** 不需要就刪掉（改成空鏡／畫外音／焦外）。
2. **需要 → 用景深或剪影把路人處理成不可辨識的塊面**（同時消滅「複製臉」風險，因為沒有臉可複製）。
3. **需要看見 → 走 I2V：先做一張含路人的乾淨分鏡圖（固定背景模板＋固定光線描述），再圖生影片。** 這讓路人也在「同一張圖」裡、由同一個模型同一次生成，畫風自然一致。
4. **仍不一致 → 後期合成**（群眾板貼圖 / 遮罩修補 / 統一調色）。
5. **永遠不要**在 R2V 提示詞裡單獨描述一個沒有參考圖的路人——那正好是本報告要根除的失效模式。

---

## 5. 一個影片模型能鎖幾個身分？基準數據

### 5.1 OpenS2V-Eval 排行榜（FaceSim = 身分相似度）

> 來源：[BindWeave README 內嵌的 OpenS2V-Eval 榜單](https://github.com/bytedance/BindWeave) · [排行榜](https://huggingface.co/spaces/BestWishYsh/OpenS2V-Eval) · [基準說明](https://pku-yuangroup.github.io/OpenS2V-Nexus/)

| 模型 | TotalScore↑ | **FaceSim↑** | 備註 |
|---|---|---|---|
| VACE-14B | 57.55% | **55.09%** | 開源最佳 |
| BindWeave | 57.61% | **53.71%** | 榜單 TotalScore 第一 |
| Phantom-14B | 56.77% | 51.46% | |
| Phantom-1.3B | 54.89% | 48.56% | |
| SkyReels-A2-P14B | 52.25% | 45.95% | |
| **Kling 1.6**（商用） | 56.23% | **40.10%** | 商用模型中偏低 |
| Vidu 2.0 | 51.95% | 35.11% | |
| MAGREF-480P | 52.51% | 30.83% | |
| Pika 2.1 | 51.88% | 30.38% | |
| VACE-1.3B | 49.89% | 20.57% | |
| VACE-P1.3B | 48.98% | 16.59% | |

### 5.2 Vera 論文的自建人類 S2V 基準（100 個身分、600 支影片）

> 來源：[Vera 論文 §4](https://arxiv.org/html/2607.20247v1)

| 方法 | FaceSim-Arc↑ | FaceSim-Cur↑ | X-CLIP↑ |
|---|---|---|---|
| VACE-1.3B | 0.487 | 0.468 | 0.307 |
| VACE-14B | 0.531 | 0.507 | 0.311 |
| BindWeave | 0.512 | 0.488 | 0.343 |
| Phantom-1.3B | 0.488 | 0.461 | 0.333 |
| Phantom-14B | 0.495 | 0.472 | 0.329 |
| **Vera** | **0.571** | **0.529** | 0.340 |

### 5.3 這張表告訴我們的事

- **身分相似度的天花板是 0.5–0.6（ArcFace／CurricularFace）**。連 SOTA 都只有 0.53–0.57，代表「角色完全鎖死」在數學上還沒發生。【官方/基準】
- **商用模型不一定比開源強**：Kling 1.6 的 FaceSim 40.1% 明顯低於 VACE-14B 的 55.09%。【官方/基準】
- **官方分類把「多人臉 / 多人身體」列為獨立類別**，代表「一個 clip 多於一個身分」是公認的 harder task。【官方/基準】
- **「一次幾個身分」的實務答案：1 個（安全）到 2 個（有條件）；3 個以上不建議。** OpenS2V-Eval 的 multi-face 類別本身就是分開的，而 2 人同框在主流工具鏈裡已經需要走「合成首幀 → I2V」或「動作遷移 + 合成」了。【社群實測＋推測】
- **⚠️ 但要小心：2026 年並不存在「AI 影片角色一致性」的 Tier-1 公開基準**。社群一致的共識是「都是實務經驗排序」；任何宣稱「基準證明某模型最佳」的說法都應被打問號。【社群實測】(<https://www.pixmind.io/posts/ai-video-character-consistency-guide>)
- 可用來做自動化驗收的量化指標：ArcFace / CurricularFace 臉部相似度、X-CLIP（提示詞遵循）、MotionSmoothness、NaturalScore（OpenS2V-Eval 的 GmeScore / NexusScore / NaturalScore）。【官方/基準】

---

## 6. 建議規則集（pipeline skill 可強制執行）

> 標記：🔴 = 硬性阻擋（不滿足就拒跑／退回改寫）；🟠 = 自動改寫；🟡 = 警告並記錄。

### A. 參考槽位與身分配置

| ID | 規則 | 級別 |
|---|---|---|
| A1 | **每個 R2V 請求中，「有參考圖的具名角色」數量 ≥ 提示詞中出現的具名角色數量。** 不足即視為必然失效，**改走 I2V（合成首幀）或拆段**。 | 🔴 |
| A2 | 若提示詞提到 2 名具名角色，必須滿足下列任一：(a) 兩人各有自己的參考圖；(b) 兩人被合成在同一張參考圖內；(c) 走 I2V 且首幀含兩人。 | 🔴 |
| A3 | **每張角色參考素材只能包含一名角色**（Wan 2.7 官方規則），推廣為全管線通則。 | 🔴 |
| A4 | 角色參考圖優先使用**正面／四分之三／側面／背面／臉部細節**的轉身圖組；需要背影時，**必須提供背面裁切**。 | 🟠 |
| A5 | 角色參考圖須為：均勻光、視線高度正面、純色或極簡背景、無遮擋（無墨鏡／無手擋臉／無硬陰影）。 | 🟠 |
| A6 | 全案使用**同一張黃金母圖**，禁止跨鏡／跨集更換；禁止用上一集生成截圖當參考圖。 | 🔴 |
| A7 | H3 專用：參考圖 ≤ 9、參考影片 ≤ 3、參考音訊 ≤ 3、混合總檔案 ≤ 12；提示詞 ≤ 7000 字元；`first_frame/last_frame` 與 `reference_*` **互斥**，不得混用。 | 🔴 |
| A8 | Wan 2.7 專用：參考圖＋參考影片 ≤ 5；首幀 ≤ 1；提示詞以「圖N／視頻N」指代，順序必須與 `media` 陣列一致。 | 🔴 |
| A9 | Kling 專用：Elements 圖 1–4 張；場景／服裝也可設為 element 以鎖定畫風。 | 🟠 |

### B. 提示詞規則

| ID | 規則 | 級別 |
|---|---|---|
| B1 | **否定提示詞固定包含 `duplicate faces`**，並視專案追加 `identical twins, cloned face, same face twice` 等同義詞。 | 🔴 |
| B2 | 建立**身分區塊（identity block）**並**逐字複製**到每一條提示詞開頭；任何同義詞替換視為 regression。區塊含：合規年齡宣告＋骨相膚色＋髮型定式＋核心服裝＋標誌配飾。 | 🔴 |
| B3 | **參考圖已存在時，提示詞不得重述角色的臉部特徵**（年齡／膚色／臉型／眼型）——重述會邀請模型重新詮釋。 | 🔴 |
| B4 | 提示詞中每個角色都要有**空間錨點**（畫面左／右、靠桌、近景遠景）。 | 🟠 |
| B5 | 固定使用完整提示詞槽位順序：**主體動作＋環境變化＋鏡頭運動＋風格限定＋時長＋負面排除**。 | 🟠 |
| B6 | 固定「場景描述模板」與「光線描述詞」，全案不得改寫（這是中文實務的一致對策）。 | 🟠 |
| B7 | **禁止在 R2V 提示詞中描述沒有參考圖的具名人**。若該角色必須可見 → 觸發 A2；若只需聲音 → 改寫為畫外音並從視覺描述中刪除該人。 | 🔴 |
| B8 | 開啟提示詞擴寫時（`prompt_expansion_mode` / H3-Context-IR），**擴寫後的提示詞必須重新過一次 A1/A2/B7 檢查**，因為擴寫可能自行補出人物。 | 🟠 |
| B9 | 每段提示詞必須能被「身分區塊 + 空間錨點 + 風格限定」三段式完全覆蓋；做不到就代表這段的角色約束不足。 | 🟡 |

### C. 分鏡與鏡頭規則

| ID | 規則 | 級別 |
|---|---|---|
| C1 | 單段時長 **3–6 秒**（Seedance 2.0 穩定區間；H3 4–15 秒但建議 5–6 秒測試）。 | 🟠 |
| C2 | 單段只執行**一種**運鏡（推／拉／搖／跟其中一）。 | 🟠 |
| C3 | **身分關鍵鏡頭用中景／近景**；臉佔畫面 < 20% 的遠景只用作交代環境，不承擔身分。 | 🔴 |
| C4 | 主角「轉身／背對／遮擋」的鏡頭，**臉在動作中至少部分可見**；若一定要完全背對，**在編輯上把身分斷點切掉**（cut around the break）。 | 🔴 |
| C5 | 多人對話鏡頭走 **Chain Continuity**：先生成含兩人的主鏡頭 → 鎖第一幀 → 用「凍結角色和場景、把相機移動到［角度］」生 setup frames → 逐鏡生成表演。**不得用「放大」假裝特寫。** | 🟠 |
| C6 | 需要拼接時一律走**首幀鏈接**；若模型支援單次多鏡，優先單次多鏡。 | 🟠 |
| C7 | 切點藏在動作裡（轉身、開門、物件遮擋），並在剪輯時裁掉頭尾不穩定幀。 | 🟠 |

### D. 風格與背景人群

| ID | 規則 | 級別 |
|---|---|---|
| D1 | 背景路人優先策略依序：**(a) 拿掉 → (c) 景深／剪影 → (d) 後期群眾板 → (e) 遮罩修補 → (b) 給路人參考圖**。 | 🔴 |
| D2 | 若畫面必須出現可辨識的群眾 → **走 I2V**，把群眾畫進分鏡圖（固定背景模板），再圖生影片。**禁止**在 R2V 文字裡描述無參考圖的路人。 | 🔴 |
| D3 | 每一段都必帶**風格限定詞**（媒體風格＋渲染質感＋著色方式），全案一致。 | 🟠 |
| D4 | 固定「場景描述模板」＋「光線描述詞」；全案統一調色在剪映／Resolve 以「套用到全部」達成。 | 🟠 |
| D5 | 若模型支援「風格參考」（如即夢「風格參考」模式、Veo Ingredients 的 texture 項），提供一張**風格原型圖**；但注意官方實測指出其對寫實攝影較弱、不能單獨解決漂移。 | 🟡 |

### E. 品管與驗收

| ID | 規則 | 級別 |
|---|---|---|
| E1 | 每段生成 **3–5 個 take** 再挑；不要接受第一個輸出。 | 🟠 |
| E2 | 先用 **768P 迭代**、鎖定後再用 **2K 收尾**（H3 2K $0.13/s、768P $0.09/s）。 | 🟡 |
| E3 | 自動化驗收（可寫成腳本）：**ArcFace 臉部相似度**（角色 vs 母圖）、**X-CLIP**（提示詞遵循）、**運動平滑度**；判斷閾值建議以 OpenS2V-Eval 榜單為參照基線（注意 SOTA 僅 0.53–0.57，**不要設成 0.9**）。 | 🟠 |
| E4 | **重點人工檢查：畫面中每一張人臉，必須能對應到一個已定義的身分。** 任何「多出來的一張臉」＝ 觸發 A1／A2／B7。 | 🔴 |
| E5 | 重點人工檢查：**畫風**——把每段縮圖並排，確認背景人群與主角的渲染質感一致；不一致走 D1 順序處理。 | 🔴 |
| E6 | 逐鏡記錄：提示詞全文、參考圖檔名、模型、seed、參數（供重現）。 | 🟠 |
| E7 | 同一場景的鏡頭盡量在**同一 session 內依序生成**（模型與設定會隨時間漂移）。 | 🟠 |

### F. 模式切換決策樹（快速查表）

```
段落的具名角色數 = N
│
├─ N = 1 ──► R2V（母圖 + 角色參考）
│            ├─ 臉需要轉身/背對 → 提供背面裁切 + 提早切掉身分斷點 (C4)
│            └─ 有背景路人 → 先做含路人的分鏡圖走 I2V (D2)
│
├─ N = 2 ──► 【預設】合成含兩人的乾淨分鏡圖 → I2V（首幀鎖定）
│            ├─ 需要真實動作遷移 → Wan-Animate-2 + 合成
│            └─ 需要每人一張參考 → 改用 Wan2.7-R2V（≤5 媒體）或 Kling Elements（≤4 張）
│
├─ N ≥ 3 ──► 不建議單 clip 生成。改為：多宮格分鏡板參考 (M5) 或 拆成多個 clip 後剪輯合成
│
└─ 任何 N，若只聞其聲不見其人 ──► 從視覺描述中刪除該人，改畫外音 (B7)
```

---

## 7. 完整來源清單

### 官方文件／論文
1. [MiniMax H3 — Video Generation 指南](https://platform.minimax.io/docs/guides/video-generation) — 參考槽位上限、role、互斥規則、輸出規格
2. [MiniMax H3 — H3 Feature Highlights](https://platform.minimax.io/docs/guides/video-prompt) — 官方多模態參考範例（兩位主角同圖、facial details 細分）
3. [MiniMax — Create Video Generation Task API](https://platform.minimax.io/docs/api-reference/video-generation-v2-create) — role enum、媒體限制、`prompt_expansion_mode`
4. [萬相 2.7 參考生影片 — 使用指南（阿里雲百煉）](https://help.aliyun.com/zh/model-studio/video-to-video-guide) — 多主體參考＋音色、多宮格、素材限制
5. [萬相 2.7 參考生影片 — API 參考](https://help.aliyun.com/zh/model-studio/wan-video-to-video-api-reference) — 「參考素材為主體角色時，僅包含單一角色」、圖N／視頻N 指代規則
6. [ComfyUI — Wan2.7 教學](https://docs.comfy.org/tutorials/partner-nodes/wan/wan2-7) — 「supports up to 5 real-person inputs and multi-character interactions」
7. [ComfyUI — Wan2ReferenceVideoApi 節點文件](https://docs.comfy.org/built-in-nodes/Wan2ReferenceVideoApi) — 「single-character performances and multi-character interactions」
8. [Kling — Elements（角色一致性官方指南）](https://kling.ai/quickstart/ai-video-character-consistency) — 1–4 張、主體挑選、場景／服裝 element
9. [Kling — Element Library 使用指南](https://kling.ai/quickstart/klingai-element-library-3-user-guide)
10. [Google — Veo 3.1 Ingredients to Video（2026-01-13）](https://blog.google/innovation-and-ai/technology/ai/veo-3-1-ingredients-to-video/) — 身分／背景／物件一致性、Nano Banana Pro pro tip
11. [OpenAI — Sora 2 is here](https://openai.com/index/sora-2/) — Cameo／Characters
12. [Runway — Creating Multi-Character Dialogues with Act-Two](https://help.runwayml.com/hc/en-us/articles/41748090660499-Creating-Multi-Character-Dialogues-with-Act-Two) — Act-Two 單角色限制（頁面受 Cloudflare 保護，依官方搜尋摘要）
13. [Runway — Performance Capture with Act-Two](https://help.runwayml.com/hc/en-us/articles/42311337895827-Performance-Capture-with-Act-Two)
14. [ByteDance — Seedance 2.0 官方頁](https://seed.bytedance.com/zh/seedance2_0) · [Seedance 1.0 官方頁](https://seed.bytedance.com/zh/seedance)
15. [Vidu — Reference to Video](https://www.vidu.com/ai-reference-to-video) — 宣稱最多 7 張參考圖
16. [Vera: Identity-Faithful Human Subject-to-Video Generation（arXiv 2607.20247）](https://arxiv.org/html/2607.20247v1) — 主體混淆／屬性互換／過度複製參考特徵；view collapse；多人基準
17. [OpenS2V-Nexus / OpenS2V-Eval（arXiv 2505.20292）](https://pku-yuangroup.github.io/OpenS2V-Nexus/) — 七大類含 multi-face/multi-body；三大挑戰；18 模型評測
18. [VACE（arXiv 2503.07598）](https://arxiv.org/abs/2503.07598) — reference-to-video / video-to-video / masked video-to-video
19. [Phantom README](https://github.com/Phantom-video/Phantom) — ≤4 張參考、單／多主體、prompt 描述參考圖的官方建議
20. [BindWeave README（ICLR 2026）](https://github.com/bytedance/BindWeave) — MLLM-DiT entity grounding；OpenS2V-Eval 榜單
21. [Wan2.2 README](https://github.com/Wan-Video/Wan2.2) — S2V-14B / Animate-14B 單主體
22. [Wan-Animate-2 README](https://github.com/Wan-Video/Wan-Animate-2) — 身分保留 + text-driven viewpoint control
23. [OpenS2V-Eval 排行榜](https://huggingface.co/spaces/BestWishYsh/OpenS2V-Eval)

### 社群實測
24. [PixMind — How to Keep Character Consistency Across AI Video Shots](https://www.pixmind.io/posts/ai-video-character-consistency-guide) — `duplicate faces` 否定詞、per-actor 參考槽、臉 < 20% 閾值、轉身圖、30 鏡實測 24/30 vs 9/30
25. [PixMind — MiniMax H3 Character Consistency 完整指南](https://www.pixmind.io/posts/minimax-h3-character-consistency) — 12 檔預算分配、master-character 法、65–75% 影響力、衝突參考、動態斷臉
26. [黃果製片 — AI 短劇角色一致性与多集连续工作流](https://huangguo.design/blog/ai-short-drama-character-consistency) — 黃金母圖、四要素身分錨點、單人 r2v / 雙人 i2v・board
27. [CSDN — AI 影片全流程實戰：解決角色一致性＋後期合成難題](https://blog.csdn.net/chajinglong/article/details/161870403) — Chain Continuity 首幀錨定法、OTS setup frame
28. [CSDN — AI 短劇製作全流程（DeepSeek＋豆包＋即夢＋剪映）](https://blog.csdn.net/llooyyuu/article/details/162750388) — 翻車對策表、分別上傳多人參考圖、固定場景／光線模板、剪映統一調色
29. [CSDN — AI 動漫短劇全流程工程化實操](https://blog.csdn.net/wudi416/blog/article/details/158233761) — 固定背景模板＋畫風關鍵詞、種子值鎖定、局部重繪
30. [知乎 — 即夢＋可靈輕鬆實現 AI 影片主體人物和風格的一致性](https://zhuanlan.zhihu.com/p/1887821957254329621) — 三視圖（正/側/背）裁切分餵、先統一風格再整組餵多圖參考
31. [知乎 — 生成100張臉，90張是同一張：AI「撞臉」怎麼破](https://zhuanlan.zhihu.com/p/2046171615092909849) — 撞臉術語、cref/InstantID/LoRA/換臉
32. [AI Pulse — 即夢參考圖功能深度用法：控制風格一致性](https://ai-pulse-lab.com/tips/%E5%8D%B3%E6%A2%A6%E5%8F%82%E8%80%83%E5%9B%BE%E5%8A%9F%E8%83%BD%E6%B7%B1%E5%BA%A6%E7%94%A8%E6%B3%95-%E6%8E%A7%E5%88%B6%E9%A3%8E%E6%A0%BC%E4%B8%80%E8%87%B4%E6%80%A7) — 風格原型錨點、模式選擇（風格參考 vs 結構參考）、已知極限
33. [B 站 — AI 漫劇多人場景總翻車？撞臉、崩壞、站位亂？](https://www.bilibili.com/video/BV1V5EC6tEzK/)
34. [百度文庫 — 影片裡多餘的人怎麼去掉](https://wenku.baidu.com/view/08d95741826fb84ae45c3b3567ec102de3bddf52.html)
35. [搜狐 — AI 短劇角色一致性的 7 種方案](https://www.sohu.com/a/1038316934_121123989)
36. [知乎 — 解決 AI 短劇角色、場景、聲音一致性，3 個關鍵方案](https://zhuanlan.zhihu.com/p/2050534732618905039)
37. [Zopia — 如何保持 AI 角色一致：參考與跨鏡頭指南](https://zopia.ai/zh/blog/consistent-ai-characters-guide)
38. [CocoLoop — AI 影片角色一致性檢查清單](https://www.cocoloop.cn/topic/22580)
39. [Google Discuss — Major Identity Drift and Character Consistency Failure in Video-to-Video (Flow)](https://discuss.ai.google.dev/t/major-identity-drift-and-character-consistency-failure-in-video-to-video-generation/173742)

### 檢索限制
- Reddit（r/StableDiffusion / r/AI_Video / r/LocalLLaMA）與 Discord 摘要**本次無法取得**：本機 `agent-reach doctor` 回報 Reddit 無任何可用後端（`status: off`，Reddit 無零配置路徑，需登入態），Discord 同理。X（Twitter）依指示未使用。
- Runway 官方說明中心（help.runwayml.com）有 Cloudflare 保護，僅能取得搜尋摘要，正文未能讀取。
- 知乎頁面以 Jina Reader 讀取成功；小紅書無可用後端（`status: off`）。
