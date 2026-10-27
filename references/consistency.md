# 資產與一致性規範

角色設定圖、場景、道具、音色、風格與光色可用「登記 + 參考鏈 + 驗收」維持一致。實際先後順序依使用者交付範圍與可用工具安排；純文字分鏡不需先生成設定圖。

## 0. 先決定的四個衝突與實戰裁定（本技能的裁定）

| 衝突 | 裁定 | 原因與實戰驗證 |
|---|---|---|
| 有參考圖時，每鏡要不要重述外觀 | **有參考圖：外觀只在該角色首次出現的鏡頭寫一次，之後只寫新變化；沒有參考圖：逐字貼固定描述片段** | H3 帶參考圖時每鏡重述容易讓特徵漂移互搶；沒參考圖時文字是唯一錨 |
| 跨段連戲：尾幀續接 vs 獨立 Ref2VA | **依 CLI 的 Ref2VA 契約編譯獨立片段；其他模型模式需確認 adapter 支援** | FreeVideo 某些 API 曾回報 `references` 與 `first/last` 互斥；這是該 adapter 的歷史觀察，不推廣成所有模型的硬限制。可用四大錨點（光線、軸線、站位、材質）與收尾交接格維持連戲 |
| 分鏡總覽圖與逐鏡素材 | **需要構圖審核時可用分鏡總覽圖或單格圖；影片生成依使用者指定與當前工具能力** | 分鏡總覽圖可用於構圖與走位檢視，是否送入生成取決於該模型的媒體契約 |
| HEX 色票 vs H3「不用 HEX」 | **HEX 登記在 `assets.md` 當內部對照與 `color_qa.py` 驗收；餵 H3 時改寫成「色名＋物體」** | H3 對 HEX 數值不敏感，圖像模型與驗收工具仍需精確 HEX |
| 資產生成工具與一致性 | **先確認可用工具與使用者選擇；有已提供的模型參數就沿用。若使用者選擇跨場景／跨章節一致性要求，固定可行的資產參考與風格描述。** Qwen、手繪、其他圖片工具皆按能力選用，不把某個模型寫成唯一必需工具 | 工具輸出風格與能力有差異；用樣圖審核結果，不推定任何模型具備相同能力 |

### 分段級獨立 Ref2VA 連戲四大錨點（實戰定案）
在不走首尾幀續接的情況下，片段之間的視覺連戲靠以下四項硬約束鎖定：
1. **光線錨點（選用）**：需要跨段光線連續時，記錄主光向、色溫或反差等視覺錨點。
2. **軸線錨點**：嚴守 180° 攝影機軸線規則，鏡頭切換不發生越軸翻轉。
3. **站位錨點**：角色位置錨定在空間實體家具或幾何邊界（如「靠左側石柱」、「辦公桌右側邊角」）。
4. **材質錨點**：地面鋪裝與牆面紋理在每段 Prompt 保持相同名詞（如 `cracked gray stone pavement`）。
5. **收尾交接格**：每段末尾 1–2 秒保持「靜止、夠寬、留白」的動作收勢，方便下段自然無縫銜接。

---

## 1. 資產 ID

分鏡 JSON、提示詞、檔名一律用 ID，中文名只作顯示。

| 前綴 | 對象 | 例 |
|---|---|---|
| `C-<slug>` | 角色 | `C-lin-zhao` |
| `B-<slug>` | 非人生物／妖獸／坐騎 | `B-python-shadow` |
| `W-<slug>-NN` | 服裝（每套一個 ID） | `W-lin-zhao-01` |
| `E-<slug>-<表情>` | 表情（選用） | `E-lin-zhao-cold` |
| `S-<slug>` | 場景 | `S-old-house` |
| `P-<slug>` | 道具 | `P-wooden-box` |
| `V-<slug>` | 音色 | `V-lin-zhao` |

每個資產帶**版本號**（`v1`、`v2`…）。檔名：`images/C-lin-zhao_W01_sheet_v1.png`。改動就升版本，舊版不刪。劇本層的 `character_id`（小說改編技能的故事聖經）與 `C-` ID 一一對應，不另造一套。

## 2. 全域鎖（寫在 `assets.md` 最前面，所有資產共用）

1. **風格鎖定錨**：從 `references/styles.md` 選一套，原文貼入。整部只用這一套，一次最多疊兩個風格。
2. **負面錨**：同上。
3. **全域光色句**：一句話描述整部的主光向、色溫、反差，逐字重用（`h3/lighting-and-color.md`）。
4. **五色色票**：膚、髮、主服、輔服、點綴，每色寫「色名＋HEX」。
5. `storyboard` Layer 2 的 `style_lock` 與這裡**同步**，改風格只改這一處再同步。

### 2.1 資產生成與工具選擇

沿用使用者已選的生圖工具與參數。若必須換工具，先與已核准素材並排比較風格，再交使用者核准。以下實戰觀察供相似風格／模型條件參考，不把單一專案的設定或數值當成普遍硬規則。

圖片生成是可選能力，取決於當前 Agent 工具或使用者指定的本機／遠端服務。已提供工具與參數時不重問；缺少會阻礙生成的選擇時才詢問。跨場景／跨章節任務可固定模型、seed、參考圖或描述，但只有使用者接受且工具支援時才採用。Stage 4 構圖 PNG 可由 Qwen、手繪或其他工具提供；須對應到 Layer 2 shot 並進入同一人工 review 與 hash 檢查。

### 2.2 Anti-Pixar 語義漂移防護與生圖後親眼視覺驗收（實戰血淚鐵律）
1. **美式卡通語義漂移成因與教訓**：
   - 在 GPT Image / Codex CLI 等自然語言生圖模型中，若使用過於寬泛的「3D animated series」加上性格形容詞如「unruly hair, wide bright eyes, a wide fearless grin」，模型會極易觸發 **Pixar / Disney 美式 3D 卡通動畫風（誇張圓眼、雀斑、露齒誇張大笑、卡通頭身比）** 的強烈語義漂移，導致該角色與同劇其他細膩寫實東亞 CG / 3D 國漫角色徹底割裂！
2. **東亞骨相與排他負向詞硬性約束**：
   - 角色 Prompt 必須明確錨定：`Photorealistic-stylized East Asian 3D CG character concept sheet (Unreal Engine 5 / Korean-Chinese next-gen CG cinema aesthetic, realistic East Asian facial bone structure and eye proportions, delicate subsurface-scattering pore skin texture)`；
   - 嚴格加入排他約束：`STRICTLY NO Pixar style, NO Disney cartoon style, NO Western cartoon proportions, NO exaggerated oversized eyes, NO freckles`；
   - 嚴禁使用「wide bright eyes + wide grin」等極易被歐美模型解釋為迪士尼卡通臉的危險組合，改用「sharp confident East Asian eyes, a composed confident slight smile with closed lips」。
3. **生圖後禁止「只看檔案大小」盲驗，必須親眼視覺驗收**：
   - 生圖完成後，**嚴禁僅憑檔案大小（>20KB）或解析度（1672×941）就判定驗收通過**！
   - Agent 必須呼叫 `view_file` 或視覺工具親自渲染圖片，親眼審視五官骨相、眼睛大小、神態與材質，並與現有已驗收角色圖（如 `char-YeWeishan.png`、`char-BlackHairDaoist.png`）橫向比對，確認畫風與審美 100% 一致後方可宣告完工交付！

### 2.3 長篇來源的角色查證（適用時）

以下人名與武器只作長篇小說查證案例；依當前原著證據處理，不作其他作品的角色模板。
1. **嚴禁單章閉門造車或憑模糊記憶命名**：
   - 當改編小說單章出現尚未自報家門、但具備鮮明特徵的重要出場人物時（例如第二章板橋車站救場的「褐髮女子」「黑髮女子」、第一章的「銀槍少年」）；
   - 改編與資產建立時，**必須全面搜尋全書文字檔（如 `input.md`）的後續章節**，主動進行實體對齊（Entity Resolution），查明角色的真實本名（例如第四章明確揭曉為「瑪蓮」與「奇雅」）；
   - **嚴禁憑記憶隨意臆測張冠李戴**（如誤認作後文登場的狄純、張如鴻），避免造成全劇人設崩塌、武器與服裝錯置的毀滅性錯誤！
2. **角色聖經雙軌標註規範**：
   - 在角色正式揭曉名字前，角色 ID 可沿用特徵 slug（如 `C-brown-hair-slayer`），但角色聖經 `assets.md`、`bible.json` 之標準名稱必須規範標註為 `瑪蓮（褐髮持刀女）`；
   - 描述片段必須忠實遵循原著該角色的真實武器與特徵（如瑪蓮之「染黃褐短髮、超大旅行帆布背包、單刃中式厚背青鋼砍刀」，絕非雙刃西洋大劍；賴一心之「娃娃臉、健壯高大體魄、背後長條白色皮背包、折疊式三節棍銀長槍」，絕非西洋不可拆長矛）。

## 3. 角色與生物設定板（Character & Creature Sheet）

### 3.1 角色設定板（Character Sheet）
**版面**：16:9 單張，平光、純色背景。左側 1 格面部特寫，右側 3 格全身（正面／側面／背面）。要 3/4 面時改 5 格。
**必備項**（缺一不過關）：
- 面部特寫：看得清五官、膚質、髮際、耳飾。
- 正／側／背全身，同比例、同站姿，雙手可見。
- 表情集（獨立一張或加在板下）：中性、微笑、怒、哭、驚、冷峻，共 6 張，同一張臉。
- 色票：五色，色名＋HEX。
- 身高對照：與主角或標準人形並排的剪影，標明身高（cm）。
- 服裝：**每套服裝各出一張全身三視圖**，ID `W-<slug>-NN`，並標明適用集數與劇本依據；沒有劇本依據不得換裝。
- 辨識錨：寫出 3 個「別人沒有的」特徵（如左眉尾疤、右手銀戒、髮簪形狀），之後每個鏡頭都要看得到。
- 板下附**固定描述片段**（逐字、可複製）。

**提示詞母版**：`export_asset_prompts.py` 的角色設定板以 ai-image-prompt「3D 漫劇寫實厚塗四視圖母版」為準——構圖（胸像約 40%、正／45°側／背三全身、淺灰棚底）一字不改，並內建防呆句（同焦平面、四格共用背景、背面至少 3 項特徵）。**風格選擇**（階段 0 與使用者確認，寫入 `assets.md` 的 `style_index`，或用 `--style`）：`master` 母版 3D 漫劇寫實厚塗（偏插畫）／`semi-real` UE5 半寫實東亞（更像真人）／`1`–`11` 取 `styles.md` 該套鎖定錨。只替換風格句與畫質句，構圖與防呆不變。同一部片只用同一個 N，並與 `assets.md` 畫風鎖一致。
**年齡段**：同一角色的少年／成年各出一套設定板，ID 用 `C-<slug>` 加版本標註年齡段，不得只改提示詞年齡。
**膚色與模板**：寫實／半寫實 H3 可參考皮膚模板，但不得覆蓋原稿或角色設定中的膚色；依該角色已核准設定調整或略過此模板。
**寫實設定圖的皮膚寫法（選用，只用在階段 2 設定圖；D46）**：來源 Foyege（NZog-5vbTTA），H3 0 實測、設定圖靠人審。**與定版不衝突的範圍**：守富 2026-09-16 定版皮膚段（`h3/skin-realism-block.md`）管的是**影片提示詞**，照舊整段照抄、一字不改；下面六段只用在寫實／半寫實（`semi-real`、寫實真人類畫風）的**角色設定圖**生圖提示詞，預設 14 號古風寫實厚塗與非寫實畫風不用。不覆蓋已核准膚色，不指定生圖引擎（`design_engine` 由 `h3d decide` 定）。
1. 物理狀態一次只選一種（自然半啞光／剛運動過／帶灰塵擦傷），不要把乾燥、汗、淋雨、精緻底妝放在同一張臉。
2. 分區紋理：額頭毛孔較細、鼻翼略明顯、面頰大小不一、眼下是細紋不是粗毛孔、嘴唇有縱向唇紋。
3. 克制瑕疵：輕微膚色不勻、鼻翼泛紅、眼下細紋；不寫「完美無瑕」（會做成假人）。
4. 高光分布：細碎高光只在鼻樑上方、顴骨、下唇中央；兩頰與下顎保持低反射。
5. 光線或表情驅動的變化（例如逆光下耳廓透光）。
6. 同一角色各張設定圖的皮膚狀態一致。
- 理由：影片模型會放大參考圖，設定圖臉糊進影片會更糊更油；「8K、超高清、真人皮膚」這類詞容易變成油亮磨皮臉。
**全身格臉部一致性（專案經驗）**：若全身格的臉部細節不足以維持一致，可用特寫作為面部參考；依版面用途調整，不強制要求固定格數或排版。

### 3.2 非人生物／怪獸設定板（Creature Sheet，實戰升級）
奇幻、玄幻中的巨獸、妖物、坐騎（如巨蟒、白獸、魔狼、靈鳥）與人類角色同等規格：
1. **純色背景三視圖**：必須生成純灰/純白背景的特寫與全身姿態（左側頭部/獠牙特寫，右側全身比例、盤旋/站立姿態、皮膚鱗片/羽毛花紋細節）。
2. **⛔ 嚴禁使用帶場景背景的劇照**：實測證明，帶背景的生物參考圖會把原圖的巷道、建築殘留強行當作生物固有特徵，並帶進成片的所有其他場次！
3. **演員表主角優先排序鐵律**：
   填寫每段演員表時，**按「這一場誰是核心主角」排序**，而非按人類先於生物。生物在主戲場次必須排在第 1 位（`subject 1`），避免被 H3 參考名額上限稀釋擠掉。

## 4. 場景主圖

- **全景母片**：一張定空間（家具位置、出入口、窗、主光源）。
- **三角度**：正向、側向、反向各一，同一空間。對話場景補一張過肩可用的背景虛化圖。
- **多角度分步生成，不要一次生全部角度**（抖音蒸餾 2026-10 A 批）：
  1. 先定**正面**（全景母片）。
  2. 再**單獨生反打**（180°），人工逐項檢查模型補出來的門窗、家具背面和光源位置：門窗有沒有換牆、家具背面合不合理、主光方向和正面對不對得上。背面在正面看不到，補出來的東西是設計決策，定案後寫進板下的場景固定描述，不行就重生反打。
  3. 反打驗收過，**用正＋反兩張當參考**生側面和俯視。
  - 一次生多角度時，看不到的那一側最容易各自亂補；反打先驗收再當第二錨，後面的角度才有兩個方向可以對。
  - 來源：抖音蒸餾 2026-10，千尋 7690806399139417363（一次多角度 vs 分步的對照）、泡沫藝術家 7633770287040859427（全景取景＋接縫重繪）。證據強度：外部，未經 H3 實測（生圖階段做法，非 H3 影片）。
- **日夜／天氣變體**：同機位、同構圖，**只改光與色溫**，ID 加後綴 `-day`、`-night`。
- 板下附場景固定描述片段與**實體錨點家具**（如「站在紅木辦公桌右側邊角」），分鏡用它定站位。
- 場景的光色句要與全域光色句相容；不相容時場景句只能微調色溫。

## 5. 道具

- 正／側／細節各一，旁邊放**手掌或人物比例參照**。
- **狀態表**：完好／破損／已開啟…，每個狀態一張圖；寫明持有人與出現的鏡號。不可逆變化（杯子碎、信封皺）進 Layer 2 的 `persistent_world_state`，後續鏡頭一律承襲。

## 6. 音色鎖（雙軌：H3 音色參考 ＋ 外部 TTS 固定聲線）

- 每個有聲角色建 `V-<slug>`：**2–15 秒、單人、無配樂、無回聲**的**母帶**（master recording），附原句文字與語氣說明。
- 試聽驗收：無他人聲、無底噪、語氣符合人設，使用者確認。
- 情緒寫成文字（語速、停頓、氣息），不寫「聲帶閉合 45%」這類 H3 不吃的數值。
- **母帶挑語氣平穩的句子**（抖音蒸餾 2026-10 A 批）：選平常說話、情緒強度低的一句，不要拿哭喊、吼叫、喘著說的句子當母帶；挑的時候看五項：自然、乾淨、清楚、狀態平、夠長（2–15 秒）。極端語氣的母帶會把那個狀態帶進每一段。
- **聲音身份和本場狀態分開寫**：固定聲音描述（`voice_4d_spec_en`，見 §6.1）只寫「這個人是誰」（年齡感、音色、口音、說話習慣），每段都一樣；這一場哭過、受凍、喘、壓著嗓子這類狀態，寫在該句的表演描述（語速、停頓、氣息），不寫進固定描述。
- 來源：抖音蒸餾 2026-10，影核Ai 7698742787948154154、李一帆 7657924748714648049（口述＋示範：另做平常說話的取聲片段）。證據強度：外部，未經 H3 實測。

### 6.0 母帶從哪來：兩條路，先做的那段就是錨

母帶不必一開始就有。**角色第一次出場的那一句，就是最自然的母帶來源**——這也是 FreeVideo 導演台的做法（cast 卡片的 `voice` 欄位本來就能從 `from_job` 取已生成片段的音軌）。

| 來源 | 怎麼做 | 乾淨度 | 何時選它 |
|---|---|---|---|
| **A. 事前用 TTS 克隆做一條** | 用 VoiceStudio／Fish Audio 克隆出 2–15 秒乾淨人聲，存成 `assets/voices/V-<slug>-master-v1.wav` | **最乾淨**（無環境音、無其他聲音） | 角色有明確音色設定、要做多語版、或 H3 第一次生成的音色你不滿意 |
| **B. 事後從第一次出場的生成片抽出** | `scripts/storyboard/extract_voice_master.py`：用 Layer 2 的 `speech_window` 切出那一句 | **帶著該場景的環境音**（已知取捨，FreeVideo 自己也這樣做） | 已經生成過、而且那個音色你滿意 —— **不滿意就重抽那一段，不要拿來當母帶**；`--list` 有多句可選時，**優先挑語氣平穩的那一句**，不挑哭喊或吼叫（見 §6 開頭） |

**B 路線的指令**：

```bash
# 1) 先看哪些角色、在哪些段落有「畫內有可見嘴」且長度 2–15 秒的台詞可以當母帶
python scripts/storyboard/extract_voice_master.py --segments segments-ep01.json --list

# 2) 從第一次出場那一段抽出母帶（切點直接取自 Layer 2 的 speech_window，不猜、不靠 ASR）
python scripts/storyboard/extract_voice_master.py \
  --segments segments-ep01.json \
  --segment-id EP01-S01-c \
  --character C-luonien \
  --videos-dir videos/ \
  --output assets/voices/V-luonien-master-v1.wav
```

- 產出 `assets/voices/V-luonien-master-v1.wav`（48 kHz／單聲道／16-bit PCM）與同名 `.provenance.json`（來源檔 SHA256、切的時間窗、原句、輸出 SHA256），可稽核、可重跑。
- 工具會直接把可貼進 stage5 綁定檔的 `audio_references` 片段印出來。
- **壞掉長怎樣**：母帶太短（< 2 秒）不足以代表音色 → 工具直接擋下並請你挑同一角色更長的一句；畫外音／鎖嘴的台詞不能當母帶（H3 不會自己念，掛上去也不會被用到）→ `--list` 會標成 ✘。
- **取捨要講清楚**：B 路线的母帶會帶進該場景的環境音（例如海風、腳步）。H3 的音色參考是「參考音色與語氣」，多一層環境音通常不致命，但若要乾淨母帶就走 A 路線。

### 6.1 一個 `V-<slug>` 驅動兩條軌道

社群講的「直出影片、每段聲音都一致且富有感情」，拆開看其實是**同一份音色被每一句重新合成**——不是影片模型「記住」了誰的聲音：掛音色母帶時是 **H3 自己照 `<Audio N>` 的音色重新發聲**（官方只保證「參考音色與語氣」，原訊號不複製），走外部 TTS 時則是**同一條複製音色重合成每一句**。本專案把這件事拆成**兩條軌道**，兩邊共用**同一個 `V-<slug>` 作為 join key**：

| 軌道 | 怎麼做 | 產出 | 保證程度 |
|---|---|---|---|
| **軌道 1：H3 音色參考** | stage5 `audio_references` 把母帶掛到角色 → 編譯器產出 `<Audio N>` 綁定句 ＋ `reference` 保留標記 ＋ 固定描述詞 `voice_4d_spec_en` | H3 **自己生成**的那把聲音會「聽起來像同一個人」 | **是參考，不是保證**【官方】；本機 FreeVideo 路徑**送得進**音訊參考（見下），但官方標註 **Experimental; does not lock the output soundtrack or lip sync**——只給音色方向，不鎖輸出音軌與口型 |
| **軌道 2：外部 TTS** | `config/tts.json` 的 `voice_map["V-<slug>"]` → 供應商音色 id（VoiceStudio profile 名稱／Fish Audio voice id／OpenAI 相容端點的 voice） | 每一句台詞都由**同一條複製音色**重新合成 | **完全確定的選項**（軌道 1 是「像同一個人」，這裡是「每段一模一樣」） |

**軌道 1 怎麼做**（stage5 綁定檔）：

```json
"audio_references": [
  {"id": "V-HERO", "path": "audio/V-HERO-master.wav", "character_id": "C-HERO",
   "role": "voice-timbre",
   "description_en": "a single teenage boy's Mandarin line recorded dry with no music"}
]
```

編譯器**只**把音色參考掛給**本段真的有可見嘴在說話**的角色；畫外音／旁白已外部化成 TTS 的**不掛**（編譯器會在 `compile_notes` 記一條說明）。產出的提示詞片段（英文，逐字）：

```text
<Audio 1> is the voice-timbre reference for <Subject 1> (S1), containing a single teenage boy's Mandarin line recorded dry with no music.
```

```text
<Audio 1>: reference - <Subject 1> (S1) follows <Audio 1>'s voice timbre and measured delivery without copying the original signal; the words in <Audio 1> are not spoken in the target video.
```

說話那一句會多一段綁定（`voice_4d_spec_en` 描述詞在前、音色參考在後；`<d>` 內是台詞原文，逐字照錄）：

```text
<Subject 1> is the visible speaking character, a clear dry teenage boy voice, matching the voice timbre referenced from <Audio 1>, and says: <d>[Chinese] ……</d>
```

**兩種音色綁定寫法並存（來源不同，別搞混）**：

| 寫法 | 來源 | 長相（逐字） |
|---|---|---|
| **官方綁定式** | 官方 ref-en §2.4；本專案 `compile_layer2_to_h3.py` 產出 | `<Audio 1> is the voice-timbre reference for <Subject 1> (S1), containing a single teenage boy's Mandarin line recorded dry with no music.` |
| **導演台自動前綴** | FreeVideo 導演台 `freevideo_engine/agent/drama.py` 的 `subject_definitions()`：把「這個角色的聲音是第幾個音檔」寫在主體那一行，與 `<Picture N> shows its appearance` 對稱 | `<Subject 1> is the character in <Picture 2>, a teenage boy in a light short-sleeved shirt. <Audio 1> is its voice.` |

**怎麼做**：兩種寫法可以同時出現在同一份提示詞裡——官方那行負責說明**音色是誰的、來源是什麼**，導演台那行負責把**主體 ↔ 音檔序號**綁在主體身上（程式裡的標籤字串就是 `'<Audio %d> is its voice'`，旁邊是 `'<Picture %d> shows its appearance'`）。FreeVideo 導演台的 cast 卡片本來就有 `voice` 欄位（`card['voice']['clip']`），會**連同角色一起送成參考**，再由 `subject_definitions()` 編成 `<Audio j>`。
**為什麼／壞掉長怎樣**：兩種寫法來源不同，**`<Audio j>` 的編號規則卻必須一致**（`j` = 這一段的第幾個音檔）。壞掉長怎樣：導演台那行寫 `<Audio 2>`、官方那行卻綁 `<Subject 1>`，帳對不上，角色就會發出**別人的音色**。

**參考進入順序與編號規則（官方節點原文）**：官方 ComfyUI 節點 `MiniMaxH3ReferenceToVideo` 的說明寫著：*"References enter the presentation in fixed order: images, then videos (each soundtrack's `<Audio j>` label right before its `<Video k>`), then standalone audio. Ordinals are 1-based per type, so the prompt refers to them as `<Picture i>` / `<Video k>` / `<Audio j>`."*——**圖 → 影片 → 獨立音訊**，序號**各類型各自從 1 開始**。
**上限**：每段音色參考 **≤ 3**（導演台 `MAX_VOICES`，模型限制）、參考總數 **≤ 32**（`MAX_REFERENCES`；FreeVideo 引擎端 `comfy_assets` 同樣是 32 個媒體項目上限，圖片＋影片＋音訊合計）。**壞掉長怎樣**：塞不下時導演台**不報錯**，而是把角色降級——`voice_omitted`（有圖但聲音沒帶上）或 `omitted`（整個角色不帶參考），成片就會突然換一把聲音。

**為什麼／壞掉長怎樣**：

- **官方用語是「參考」，不是「保證一致」**。官方 ref-en §4.1 給音訊的保留標記是 `reference`：*"the target speaker follows <Audio 1>'s voice timbre and measured delivery without copying the original signal"*【官方】——**音色與語氣被參考，原訊號不被複製**。官方同時明令 *"When only timbre, rhythm, emotion, or delivery is referenced, do not carry the original dialogue from the reference audio into the target video."*【官方】所以母帶裡的原句**不會**被念出來（編譯器照這句寫成 `the words in <Audio 1> are not spoken in the target video.`）。**壞掉長怎樣**：把母帶原句也放進 `<d>`，觀眾會聽到同一句話出現兩次（一次母帶、一次角色台詞）。
- **上游實測有 voice crossover（聲音串到別人身上）**，且官方不保證跨片段一致【社群實測】（`h3/audio-pipeline.md` 已記）。**壞掉長怎樣**：段 A 的說話人音色被套到段 B 的角色身上。
- **本機 FreeVideo 路徑送得進音訊參考（媒體型態看副檔名，不看 `role`）**：官方 ComfyUI 節點 `MiniMaxH3ReferenceToVideo` 有四個參考槽，其中 `ref_audios` → `io.Audio.Input("ref_audio", "Standalone reference audio")` 就是**獨立的音訊參考槽**；FreeVideo 操作面板 `FreeVideo · Media` 也有對應的 **`Reference audio`** 上傳／連接槽（`io.Audio.Input('reference_audio', ...)`，可接 `Load Audio` 等 AUDIO 輸出），另有 `FreeVideo · Reference (experimental)` 節點的 `image` / `video` / `audio` 三合一槽（每節點接一個，最多 32 個有序參考）。**怎麼做**：把音色母帶（`.wav` / `.mp3` / `.flac` / `.ogg` / `.m4a` / `.aac` / `.opus`）放進 `media.references` 就送得出去——**媒體型態依副檔名判定**（`EXTENSIONS` 的 `image` / `video` / `audio` 三組副檔名），`resolve_assets()` 把非圖片檔收成 `{'kind': kind, 'path': str(path)}`，`submit_h3_segments.py` 的 `upload_reference_media()` 照圖片的方式 POST `/media`，並印 🎙️ 說明本段帶了幾個 `<Audio N>`。**不需要** `role: reference_audio` 這種欄位：先前「media 物件沒有 `reference_audio` 角色」的說法，是把*媒體項目的修飾欄位*（`file` / `from_job` / `library` / `frame` / `edit`）誤當成*媒體型態*。**為什麼／壞掉長怎樣**：副檔名不在 `EXTENSIONS['audio']` 內時，`media_kind()` 判成不支援而送不進去——`submit_h3_segments.py` 在 dry-run 就用 `SUPPORTED_AUDIO_SUFFIXES` 擋下並印 ❌ 訊息；參考順序必須是**圖 → 影片 → 獨立音訊**（官方節點原文與編號規則見本節上面的「參考進入順序與編號規則」），音訊項目排在所有圖像之後（`compile_layer2_to_h3.py` 已如此輸出，`<Audio N>` 各自從 1 編號）；音訊也佔 32 個參考名額（`connect_assets()` 把連接的 `reference_audio` 算進去），一張圖配一條母帶時別把名額用光。
- **但官方把音訊參考標成實驗性，不是「保證鎖音色」**：FreeVideo 面板註明 *"Experimental; does not lock the output soundtrack or lip sync."*——音色參考是讓 H3 **重新合成**一把像母帶的聲音，**不是音軌複製**，也**不鎖**輸出音軌與口型。**壞掉長怎樣**：期待母帶原音被搬進成片（會聽到母帶原句），或期待音色參考順便鎖住口型（聲音對得上、嘴型對不上）。
- **結論：跨片段音色「聽起來像同一個人」，軌道 1 就做得到（而且本機送得進去）；「每一段都一模一樣」才需要軌道 2**。軌道 1 讓 H3 每一段都照同一個母帶**重新合成**一把聲音，接近但不是位元相同，且官方不保證跨片段一致（社群已有 voice crossover 報告）；要**完全確定**的同一把聲線，就靠同一條複製音色（`voice_map` 固定音色 id）重合成每一句——這也是多語配音那一行的正解。兩軌可以同時開：H3 負責畫面與口型錨點，最後用外部 TTS 覆蓋（此時需要 lipsync，見 `references/pipeline.md` §7.1）。
- **`voice_4d_spec_en` 是必需的固定描述詞**：H3 提示詞正文是英文，所以描述詞也必須用英文寫在 Layer 2 的 `voice_4d_spec_en`（或 `voice_profile_en`）。編譯器會把它插進說話那一句，與 `<Audio N>` 一起固定「聽起來像誰」。**只寫身份、不寫本場狀態**：例如 `a clear dry teenage boy voice, slightly husky, Taipei Mandarin` 可以；`a sobbing, out-of-breath teenage boy voice` 不行——哭過、喘這類狀態寫在該句的表演描述，否則每一段都會帶著哭腔（抖音蒸餾 2026-10 A 批，外部，未經 H3 實測；見 §6 開頭）。**壞掉長怎樣**：只給中文 `voice_4d_spec`，編譯器**不會**把它貼進英文提示詞（會變成未翻譯的噪音），只在 `compile_notes` 回報提醒；於是同一角色在不同段的音色描述不一致。
- 細節見 `h3/audio-pipeline.md`（上游版）；`voice_map` 與引擎選擇見 `references/pipeline.md` §7.3。

**音色母帶與 TTS 聲線的映射（軌道 2 的落地）**：`V-<slug>` 是「音色基準」，不是可以直接播的對白音檔；兩者要靠 TTS 設定檔的 `voice_map` 接起來。**怎麼做**：在 TTS 設定檔（`config/tts.json`，範例見 `config/tts.example.json`）補一條 `voice_map` 對應（`V-<slug>` → 供應商音色／profile 名稱；語速、音高、情緒等引擎參數寫在 `engines.<engine>` 區段），階段 7 配音時依 `voice_map` 取聲線，並用同一句測試台詞跑一次、把輸出與 `V-<slug>` 母帶並排比對音色是否一致。**為什麼／壞掉長怎樣**：`voice_map` 缺一條時，解析會一路退到「拿 speaker 原文當音色名去送」，同一個角色在不同段落、甚至不同機器上就會換聲；而母帶與 TTS 輸出是兩件事，只聽母帶驗不出這個問題。**旁白與畫外音不得由 H3 內建語音生成**（H3 原生中文語音的 ASR 置信度只有 0.43–0.54，普遍吞字），一律外部 TTS 合成後於階段 7 混入：聲音三層的取捨見 `references/pipeline.md` §7.1，`voice_map` 與引擎選擇見 `references/pipeline.md` §7.3。

## 7. 參考鏈與多模態輸入（哪一步用哪些圖）

```
【主力定案：分段級獨立 Ref2VA】
場景主圖 ────────┐
角色設定板（1張）─┼→ 每段獨立 Ref2VA（7~10秒）→ verify_video_shot.py 審查
[可選道具/生物] ──┘
音色母帶 ──┬─→ 影片（Audio ref；本機 FreeVideo 送得進，但只是參考）
            └─→ 外部 TTS 固定音色 id（保證路徑）

【⚠️ 選用實驗：全片統一首幀流程】
Qwen/GPT 首幀（全彩）──→ I2VA 影片 ──→ 與既有 H3 片段【並排對照畫風】
```

### 7.1 參考圖張數與防角色平均化（2026-10 改寫：「一段一張臉」已撤銷，D3）
- **實測平均化現象（Ref2VA 獨立生成時）**：單段若同時餵入 3 張以上年齡/身形相近的角色圖（如三名普通男高中生），H3 會在 Latent 特徵融合中將其融合成同一張臉；視覺特徵極端懸殊者（如大胖子配黑框眼鏡）才能獨立存活。
- **舊規則「一段一張角色參考圖（1 鏡 1 臉）」已撤銷**（守富裁決 D3）：不再是通則，不要再為了它把多人戲拆成單人特寫。新流程改用 **remix 生成影片**，靠**角色卡（角色包 `refmods`）**維持多人同框的人物一致；同框人數上限、首鏡單一主體見 `references/storyboard/continuity-ledger.md` §2。
- **程式現況（照實寫，程式未改）**：
  - **`video_backend: remix`**（`h3d decide` 定案）：綁定改綁角色包 `refmods`；audit 跳過混臉警告、E19、E20，改查包涵蓋（E50）與包數（E54，依 `providers/remix.json` 顯存分級；8 GB 實測 4 包常態、5 包慢、6 包 draft 逾時，見 `references/tooling.md` §2.3.1c）。**送件 adapter（R7）尚未完成**：`h3d submit`／`h3d run` 會拒送 remix 段，目前要在家機 REMIX Studio 手動送 `h3_prompt`＋`refmods`。
  - **`video_backend: ref2va`**（沒定案時的預設，FreeVideo 獨立 Ref2VA）：單人裁切仍是預設行為。有 stage5 綁定時，編譯器只為 `face_subject_ids` 掛臉部參考圖，其餘角色降成文字描述；沒有綁定時每段最多掛 `--max-char-refs` 張角色圖（預設 1）。同段超過一張可辨識人臉，audit 發 `[W: 混臉風險]` 警告（不擋）。這是 Ref2VA 上平均化現象的實際防線，不是新流程的人物一致做法。
  - Ref2VA 群戲確實需要多張臉時，最多可給 1 場景圖 ＋ 5 角色圖 ＝ 6 張，但要認知融合風險。
- **強制程式對帳（P0 門禁）**：
  `reference_images` ↔ `subject_definitions` ↔ `retention_analysis` ↔ 說話者代號 `(Sx)` 必須由同一支程式（`scripts/storyboard/audit_refs_and_segments.py`）一次產生並逐條稽核，嚴禁人工手寫出現編號錯位！

### 7.2 首幀畫風並排對照警告（第五輪實戰慘痛教訓）
- **⛔ 嚴禁單看圖片精美就判定流程成功**！
- 實測教訓：在第五輪生成中，使用外部生圖模型轉繪全彩首幀再進 I2VA，因單幀圖片十分精緻曾連續兩次誤判成功；但組裝進成片後，其畫風、材質與色彩渲染與既有的 H3 Ref2VA 片段產生巨大割裂，強烈跳戲（使用者判定「失敗」）。
- **驗收門禁**：若要嘗試首幀流程，**必須整部片全部統一用同一個生圖模型出首幀**，且新片段產出後**必須與已過審的 H3 片段並排對照畫風無割裂感**，方可採納！

### 7.3 多模態素材職責表（防止交叉染色與特徵污染）

在多圖/多模態輸入（Ref2VA）時，嚴格遵循單一素材單一職責原則，禁止素材特徵溢出污染主體：

| 素材ID | 類型 | 唯一職責 | 必須保留 | 禁止影響 |
|---|---|---|---|---|
| `ref_image_1` | 核心主戲圖（角色或怪獸） | 鎖定主體五官/頭部特徵、身形與外觀精確剪裁 | 面部五官幾何、髮型髮色/鱗片紋理、專屬辨識錨 | 禁止將純色設定板背景帶入成片場景 |
| `ref_image_2` | 場景主圖 / 空間底圖 | 確立物理空間幾何、建築材質、家具錨點與全局光源走向 | 牆面/地面材質、家具陳設、主光向與環境色調 | 禁止將場景材質染色到主體表面 |
| `ref_image_3` | 配角或道具圖 | 鎖定配角外觀或關鍵道具比例與不可逆物理狀態 | 道具形狀、握把尺寸、刻紋或配角特異性錨點 | 禁止稀釋或融合第一主體特徵 |
| `ref_image_4` | 無臉身份錨點（背影／側身單視角裁切） | 鎖定體型、髮型、服裝與身體輪廓 | 髮型與頭飾、服裝款式與配色、體型輪廓、背面專屬辨識錨（如髮簪、披風縫線、背包位置） | 禁止匯入正面臉（裁切不得含正臉）；禁止與其他角色的臉被平均成同一張臉 |
| `ref_audio_1` | 乾淨音色母帶 | 鎖定單人聲線音色、基頻與共鳴腔體質地 | 角色說話音色本質 | 禁止帶入母帶背景噪音或干擾環境擬音 |
| `ref_panel_1` | 整板查表素材（四視圖板／多格板，宣告 `reference_view: "panel"`） | **查表取得指定格的體型／服裝／輪廓** | 指定格的髮型與頭飾、服裝款式與配色、體型輪廓、背面專屬辨識錨（如髮簪、披風縫線、背包位置） | **禁止整張板的其餘格與正面臉被匯入**；禁止當成扁平身分來源餵入（會長出同款複製人）；禁止與其他角色的臉被平均成同一張臉 |

### 7.4 複製人防線（Clone-Defense）三定律

**試拍證據（2026-10-19，EP01-S01-a 火山島片段）**：編譯後的提示詞裡寫著 "Tourists leave along the path on frame-right… The visitors' varied everyday clothes and different builds remain visible from behind"——也就是**描述了一整群完全沒有參考圖的遊客**；H3 卻把段內唯一錨定角色（白襯衫）的造型套給了他們，於是火山島上長出一整群穿白襯衫的學生。同一支片裡另一句 "A pointing hand enters from offscreen" 被 H3 渲染成**整個第二個人**（黑髮、與主角相似），而不是伸進畫面的一隻手。根因只有一句：**H3 只有一張臉可用時，提示詞裡的第二個人只會被補成那一張臉的複製**；**提示詞描述了沒有參考圖的人群，模型就會用主角的造型去補**。下面三定律就是把這兩種失效從「看片才發現」變成「送件前就擋掉」。

#### 定律一（未錨定人物禁令）

**怎麼做**：畫面裡出現的**每一個人**都必須有自己的參考圖，或者被明確寫成不可辨識（失焦／剪影／畫外）而且**不描述其長相**。**沒有第三種選擇**——不要寫「群眾穿著樸素」「路人背影經過」這種只給情緒不給身分的描述。

**壞掉長怎樣（EP01-S01-a 實測）**：提示詞寫 "The visitors' varied everyday clothes and different builds remain visible from behind" → 火山島上長出整群白襯衫學生，觀眾一眼看出那不是遊客，而是一群同一個模子刻出來的人；更糟的是這群人**搶走主角的造型**，把主角襯得像少數異類。處理順序（由省到貴）：① **從畫面移除**（改成空鏡／純畫外音）→ ② **寫成不可辨識的失焦剪影**（`out of focus`／`blurred`／`silhouette`，且同句不得描述其衣著長相）→ ③ **改走「分鏡圖 → I2V」**，把人群畫進首幀，讓模型在同一次生成裡連人群一起畫 → ④ **給人群自己的參考圖**（最不划算：H3 參考圖上限 9 張，每個路人要佔掉一個槽位，佔滿就沒位置給真正重要的角色了）。

**④ 的做法（群演參考圖）**：在 `assets.md` 開一張 `### EXTRAS-<slug>　<名稱>（群演）` 卡（固定描述片段＋設定圖，一張成年群像、臉各不相同），stage5 綁定檔用 `reference_paths.extras` 只綁需要人群的鏡頭。編譯器把它寫成 `type: extras` 的參考圖與一行 `partially_preserved` 群像主體，不計入可辨識人臉；該段掛了群演圖時 E21 不再阻擋。分鏡圖腳本遇到 `EXTRAS-` 會改成「背景群演照群演圖畫、臉各不相同」，不再寫 no background figures。

#### 定律二（重要角色必掛自己的參考圖，不因背影或側面而省略）

**使用者裁定（原話）**：「不能因為是背面或側面就省略參考圖，只要是重要人物就不能偏。」

**怎麼做**：任何**重要角色**（主角、對手、會說話或有劇情功能的角色），即使畫面裡只給背影或側身，也**必須**掛自己的參考圖，並在 stage5 綁定檔用 `identity_anchor_ids` 宣告。官方 Ref2VA 的 `retention_analysis` 對可見內容只有四個固定標記：`fully_preserved`、`partially_preserved`、`attribute_transfer`、`weak_reference`——**沒有「忽略臉部」這個標記**；`weak_reference` 的語意是「只保留風格、類別、構圖或氛圍的廣泛相似」，用在人物身上會把對方降級成一個泛用人，等於自己製造第二個沒有臉的假人【官方】（[ref-en.txt](https://github.com/MiniMax-AI/MiniMax-H3/blob/main/skills/h3-prompt-writing/references/ref-en.txt)）。正解是 `partially_preserved` ＋ 在破折號後的 free text 明列要保留的特徵；本專案編譯器產出的句子是：

```text
<Subject N> (appears across shots): partially_preserved - the hairstyle, the headwear, the wardrobe and the body silhouette from <Picture N> are retained; the reference face is not imported and never appears in the target video. Ignore the neutral gray studio background of the reference sheet.
```

可辨識正臉角色維持 `fully_preserved`，不動。

**壞掉長怎樣**：本專案 2026-10-19 A/B/C/D 實測中，「一張參考圖 ＋ 提示詞提到第二人」共 **4/4 段**都長出主角的複製臉。也就是說**省略背影角色的參考圖，等於主動把這個角色的身分讓給主角的臉**——觀眾看到的是「主角的背影＋主角的臉貼在別人身上」，比沒這個人更難看。

**參考圖怎麼裁**：背影／側身角色的參考圖要**從四視圖板裁出「背面全身單視角」**，不能餵整張板。本專案的板是 2560×1440，背面全身格約在 x 1660–2020、y 0–960，裁切約 400×960 即可用（實測尺寸）；**該裁切不得含正面臉**——一旦含臉，H3 會把它當成可辨識人臉匯入，變相變回「混臉」，等於沒裁。

#### 定律三（參考圖必須是單視角裁切，禁用多視圖板）

**官方逐字引文**（MiniMax 官方 skill `minimalist-product-ad-generator` / SKILL.md，Operating Principles #1）：「Generate three separate anchor photos by default, **not one 4-panel sheet, because video models may copy panel layouts into the final film**.」；同檔並明文禁止 "grid layouts, split screens, collage boards, framed panels, product walls, or storyboard sheets"【官方】（[minimalist-product-ad-generator/SKILL.md](https://github.com/MiniMax-AI/MiniMax-H3/blob/main/skills/minimalist-product-ad-generator/SKILL.md)）。

**怎麼做**：每張送進 Ref2VA 的角色參考圖**預設**都必須是**單一視角**的裁切。正面身份裁切（950×910）與背面裁切（約 400×960）**都可接受**；**2560×1440 的整張四視圖板預設不可接受**——唯一例外是下面「整板查表模式」的宣告用法（且只限不露臉的身份錨點）。

**壞掉長怎樣**：本專案實測，把完整四視圖板／表情板餵進 Ref2VA，背景長出與板上人物**相同衣服、相同臉**的多個副本（觀眾看到「一個人在海邊走，身後跟著三個穿同款衣服的自己」）。這不是隨機瑕疵，是**版面被整個複製進成片**。

#### 整板查表模式（`reference_view: "panel"`）——官方允許的例外用法

**官方依據**：ComfyUI 的 MiniMax H3 提示詞指引明載 *"One image can hold multiple panels. Give the sheet its own `<Picture N>` (not only inside `<Subject N>`), describe panels, and point shots at a panel (e.g. full front view of `<Picture 2>`). Label panels clearly"*【官方】（[docs.comfy.org](https://docs.comfy.org)）；官方 `ref-en.txt` §2.2 也允許 `<Picture N>` 當分鏡／鏡頭規劃的錨點。所以「多格板」本身不是違規——**違規的是把它當成扁平的身分來源餵進去**。

**怎麼做**（stage5 綁定檔，角色參考圖多兩個欄位）：

```json
"reference_paths": {
  "characters": [
    {"id": "C-HERO", "path": "images/C-HERO_sheet_v1.png",
     "reference_view": "panel",
     "panel_label_en": "the fourth figure from the left, a full-body back view"}
  ]
}
```

- `reference_view: "panel"`：宣告「這張多格板是拿來**查表**的，不是拿來當扁平身分來源」。
- `panel_label_en`：**必填**，寫明要用板上哪一格（例如 `"the full-body back view, the rightmost of the three standing full-body figures"`）。省略 → 編譯器丟 `ValueError`（訊息含「必須同時提供 panel_label_en」）。
- `panel_role`：**選填**，預設 `"back"`。填 `"profile"` 代表這一格是**四分之三側**而不是完全背影，編譯器會把「臉不出現」改寫成「只允許出現該格的側臉輪廓、正面臉不匯入」。
- 這個角色被視為**不露臉的身份錨點**（non-face identity anchor）：**永遠不能同時**是 `face_subject_ids` 的成員，兩者並存 → 編譯器丟 `ValueError`。**可辨識正臉角色一律仍走單視角裁切。**

**整張四視圖板可以覆蓋背面與側面兩種視角**，不一定要為它們另外產裁切圖：

| 這一鏡的角色 | 用哪一張 | `panel_role` | 該板的哪一格 |
|---|---|---|---|
| 可辨識正臉 | 單視角正面裁切（950×910） | —（走 `face_subject_ids`） | — |
| 側面／四分之三側 | **整張四視圖板** | `"profile"` | 三個站立全身像的**中間**那個 |
| 完全背影 | **整張四視圖板** | `"back"` | 三個站立全身像的**最右**那個 |

`panel_role: "profile"` 時編譯器輸出（與 `back` 只差在臉的措辭）：

```text
<Subject 3> is the full-body three-quarter side view, the middle of the three standing full-body figures, of <Picture 4>, a teenage boy in a white school uniform; that panel is the only part of the sheet used, and only the three-quarter profile from it may appear in the target video.
```

```text
<Subject 3> (appears across shots): partially_preserved - only the full-body three-quarter side view, the middle of the three standing full-body figures, of <Picture 4> is used: the hair, the headwear, the wardrobe and the body silhouette are retained; the other panels of that sheet and its neutral gray studio background are not imported, and the frontal face from that sheet is not imported.
```

編譯器輸出（`panel_role: "back"`，英文，逐字）：

```text
<Subject 3> is the fourth figure from the left, a full-body back view of <Picture 4>, a teenage boy in a white school uniform; that panel is the only part of the sheet used, and the face is never shown in the target video.
```

```text
<Subject 3> (appears across shots): partially_preserved - only the fourth figure from the left, a full-body back view of <Picture 4> is used: the hair, the headwear, the wardrobe and the body silhouette are retained; the other panels of that sheet and its neutral gray studio background are not imported, and no face appears in the target video.
```

鏡頭描述裡也會指明「用哪一格」：

```text
 The figure seen from behind matches the fourth figure from the left, a full-body back view in <Picture 4>; no other figure on that sheet appears in this shot.
```

**兩個門禁**：

- **E20（改成宣告制）**：板尺寸的角色參考圖（≥ 1600×900 且長寬比 ≥ 1.5）**仍然直接報錯**——除非它被宣告成 `reference_view: "panel"` **且** `panel_label_en` 非空。**沒宣告的板照樣被擋**，所以整板不可能被誤餵進去。
- **E27**：宣告了 `reference_view: "panel"` 卻沒有 `panel_label_en` → 錯誤。沒有格位的整板等於沒有宣告用途，模型會把整張板複製進成片。

**誠實的取捨（不要把它讀成「四視圖板可以放心用了」）**：

- **單視角裁切仍是低風險預設**。因為模型**仍有可能**把板上的其他格也一起畫進畫面——上面「壞掉長怎樣」描述的失效並沒有因為宣告而消失。整板查表是**比較便宜**的替代方案（不用另外出裁切圖），但它**帶著這個風險**。
- 目前的緩解手段就是上面那三段提示詞：`partially_preserved` 的明文「只用這一格」、鏡頭裡的 `no other figure on that sheet appears in this shot`、以及「不露臉」的身分錨點定位。
- **⚠️ 尚未在本專案做 A/B 實測**（見 §11 待驗證清單）。**壞掉長怎樣**：把整板宣告成查表就直接送出，觀眾在海邊看到「一個人走著，身後跟著三個穿同款衣服的自己」——正是定律三要擋的失效。

#### 三定律對應的程式門禁

| 定律 | 門禁 | 判定內容 | 執行位置 |
|---|---|---|---|
| 定律一 未錨定人物 | **E19** | 編譯段 JSON 的 `unanchored_in_frame_characters` 非空（有角色在畫面裡卻沒有自己的參考圖）→ 錯誤 | 編譯器寫入欄位（`compile_layer2_to_h3.py`）→ 送件前 `audit_refs_and_segments.py` 攔截 → `submit_h3_segments.py` fail-closed 不送件 |
| 定律一（提示詞層） | **E21** | `detailed_description` 出現群眾／路人 cue（tourists, visitors, crowd, onlookers, pedestrians, passersby, bystanders, commuters, shoppers, 群眾, 路人, 遊客, 人潮, 圍觀, 行人, 人群, 群演, 觀光客），且該句沒有同時出現不可辨識 cue（out of focus, blurred, indistinct, no facial detail, unrecognizable, silhouette, 失焦, 剪影, 背景虛化, 不辨識, 看不清臉）→ 錯誤 | 送件前 audit（`audit_refs_and_segments.py`） |
| 定律二 重要角色必掛自己的參考圖 | **E26** ＋ 編譯器硬錯誤 | `reference_view: "non_face"` 卻沒有 path → 錯誤；stage5 宣告 `identity_anchor_ids` 但 `reference_paths.characters` 沒有對應項 → 編譯器直接丟 `ValueError`；同一角色同時屬 `face_subject_ids` 與 `identity_anchor_ids` → 丟 `ValueError` | 編譯器（`compile_layer2_to_h3.py`）＋ 送件前 audit |
| 定律三 單視角裁切、禁多視圖板 | **E20**（宣告制） | 角色參考圖像素 ≥ 1600×900 且長寬比 ≥ 1.5 → **錯誤，除非**該素材宣告 `reference_view: "panel"` 且 `panel_label_en` 非空（2560×1440 整板**未宣告**時命中；950×910 正面裁切與約 400×960 背面裁切不命中） | 送件前 audit；需 `project_root` 讀圖像素，由 `submit_h3_segments.py` 傳入；宣告查表另見下一列 E27 |
| 定律三 整板查表缺格位說明 | **E27** | 宣告 `reference_view: "panel"` 卻沒有 `panel_label_en` → 錯誤（沒指定用哪一格，模型會把整張板複製進成片） | 送件前 audit（`audit_refs_and_segments.py`）；編譯器（`compile_layer2_to_h3.py`）也會直接丟 `ValueError`（訊息含「必須同時提供 panel_label_en」） |
| （附帶）說話人綁定與旁白 | **E22**／**E23**／**E24**／**E25**／**E43**／**E44** | 缺 `(Sx)`、畫外音缺嘴閉合聲明、外部化的句子仍以 `<d>` 出現、`overall_soundscape` 重複台詞 → 錯誤；有說話動詞卻沒 `<d>`（E43）、畫外句同鏡張嘴（E44）→ strict 才算錯誤 | 送件前 audit；格式對照見 `references/minimax-h3.md` §「官方 Ref2VA 格式合規速查」 |

**補充說明（為什麼門禁不能只擋一半）**：E19/E21 擋的是「提示詞裡憑空多出的人」，E20 擋的是「版面被複製」，E26 擋的是「宣告了身份錨點卻沒真的掛圖」，E27 擋的是「宣告了整板查表卻沒說用哪一格」。四者缺一，複製人還是會長出來——所以是**送件前全數通過**才允許送出，audit 本身是 fail-closed（審查依賴不可用時直接拒送，不放行）。

---

## 8. 漂移偵測清單（每鏡生成後逐項 pass/fail）

臉型五官｜髮型髮色｜服裝件數與配色｜膚色｜標誌辨識錨 3 項｜道具位置與狀態｜光向｜色溫｜身體比例｜場景家具位置。影片另跑 `scripts/color_qa.py` 量跨鏡色彩。**任何一項 fail 就不得當下一段的參考。**

## 9. 修復階梯（由輕到重，一次只改一個變數，並記錄）

1. 原樣貼回固定描述片段（確認沒被改寫）。
2. 補上或換更乾淨的純底參考圖。
3. 有參考圖時，縮減外觀字數，只寫新變化（見 §0 第一項）。
4. 單變數重抽（只換種子、或只改一句提示詞）。
5. 升版本號：修正設定板，重出受影響的資產。
6. 請使用者人工裁定。

## 10. 每資產驗收門

| 資產 | 通過條件 | 驗收者 |
|---|---|---|
| 角色設定板 | §3.1 必備項齊全；純底；使用者確認長相 | 使用者 |
| 生物設定板 | §3.2 純灰/純白背景三視圖，無任何場景殘留 | 使用者 |
| 場景 | 母片＋三角度＋所需日夜變體 | Agent 自檢＋使用者確認母片 |
| 道具 | 比例參照＋狀態表 | Agent |
| 音色 | 試聽通過，無他人聲與底噪 | 使用者 |
| 分鏡 | `scripts/storyboard/validate_storyboard.py` 通過；跨鏡 checklist（四大錨點一致、角色 ID 一致、換裝有依據、同場光線一致） | Agent |
| 分鏡圖／影片 | §8 清單全 pass；**首幀生成片段必須與既有 H3 片段並排對照畫風** | Agent，存疑交使用者 |

沒通過就不進下一階段；階段 6 絕不拿未通過的資產當參考。

## 11. 待驗證清單（尚未在本專案實測，不可當成已驗證規則）

這一節只放「規則已寫進工具鏈、但效果還沒有本專案的實測數據」的項目。**不要把它們寫進「已驗證有效」**。

| 項目 | 現況 | 要驗什麼 | 怎麼驗 | 壞掉長怎樣 |
|---|---|---|---|---|
| **整板查表模式**（`reference_view: "panel"` ＋ `panel_label_en`，見 §7.4 定律三） | 編譯器與兩個門禁（E20 宣告制、E27）**已實作**；**效果尚未 A/B 實測** | 宣告成查表的四視圖板，會不會仍把板上的其他格畫進畫面 | 同一角色、同一場景、同一段提示詞，跑兩支：一支餵單視角裁切（950×910 正面／約 400×960 背面），一支餵整板查表，**並排看片** | 背景長出與板上其他格同款衣服／同臉的複製人（正是定律三要擋的失效） |
| **H3 音色參考的跨片段一致性**（`<Audio N>`，見 §6.1 軌道 1） | 編譯器**已實作**；官方用語是「參考」不是「保證」【官方】；上游已記 voice crossover【社群實測】 | 音色會不會**串到別人身上**（上游的 voice crossover）；同一角色跨兩段的音色比較見下一列「本機 FreeVideo 送音訊參考」 | 同一段裡放兩位有聲角色、各掛自己的母帶，生成後**只聽音軌**（不靠畫面輔助判斷），確認兩把聲音沒有互換 | 段 A 的說話人音色被套到段 B 的角色身上（voice crossover） |
| **`voice_4d_spec_en` 描述詞的穩定度** | 編譯器**已實作**（中文 `voice_4d_spec` 不貼進英文提示詞，只回報 compile note） | 同一段內兩句台詞、跨段兩次生成，描述詞是否真的讓音色更接近 | 同角色兩段都用同一句 `voice_4d_spec_en`，並排聽 | 描述詞被當成無關文字忽略，音色每段都不同 |
| **本機 FreeVideo 送音訊參考** | **傳送鏈已確認可用**：媒體型態依副檔名分類（`EXTENSIONS['audio']`）、`submit_h3_segments.py` 的 `upload_reference_media()` 照圖片 POST `/media`、`compile_layer2_to_h3.py` 把音訊項目排在所有圖像之後（圖 → 影片 → 獨立音訊） | **音色參考跨段是否真的 hold 得住**（同一母帶、兩個不同場景，**只聽音軌**比較），以及輸出口型是否漂移 | 同一個 `V-<slug>` 母帶掛兩段**場景不同**的分段，生成後抽出兩段音軌**只聽聲音**（不看畫面、不靠字幕輔助），判斷是不是同一把聲音；再對照兩段嘴型與音軌的對位有沒有漂 | 兩段是兩把聲音（跨段不一致）；或聲音一致但口型對不上（音色參考不鎖口型）；或音軌根本沒送進去（副檔名不在 `SUPPORTED_AUDIO_SUFFIXES`，應在 dry-run 就被 ❌ 擋下） |
