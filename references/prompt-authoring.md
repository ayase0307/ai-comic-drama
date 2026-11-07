# 逐鏡提示詞撰寫規範（階段 5，強制）

> 目的：每一鏡的提示詞都由 agent **看著這一鏡的分鏡親手想、親手寫**，把畫面要的東西寫具體，減少抽卡次數。
> 由 `scripts/storyboard/prompt_authoring.py` 對**最終送件文字**做確定性檢查；`h3d compile --check`、階段 5 審核頁與 `h3d submit` 都會跑，錯誤會擋核准與送件。
> 五小節的格式與句型見 `references/h3/shot-five-part.md`；本文件規定「哪些一定要寫、哪些一定要寫詳細、什麼算偷懶」。

## 為什麼要這份規範（實戰教訓）

2026-10 《噩盡島》EP01：agent 寫了一支腳本，把 139 鏡的五小節自動填成同一組句子，並在編譯**之後**才覆寫進 `segments-ep*.json`。結果：

- 每鏡都有「Hold the authored support and end pose; only an expressly named breath… with no added step or prop contact」這類句子，全是**叫模型別動**，沒有一句寫這一鏡實際發生什麼。
- `authored`、`approved plate`、`the specified partner` 這些詞只有流程看得懂，H3 看不到核准紀錄，等於空轉。
- 分鏡標「嘴部可見」的導遊台詞被寫成畫外音、嘴閉著，H3 失去口型。
- 原本 17 條自檢**全部通過**，因為它們只抓固定罐頭句，而套句在編譯後才出現。

同一組參考圖、同一個 H3，只換成逐鏡親手寫的提示詞，畫面就有了推鏡、跟拍、表演與光的變化（A/B 試片，2026-10-23）。差別在寫提示詞的 agent，不在影片模型。

## 一、每鏡一定要寫（缺一擋：E30）

每個 `[Shot N]` 在編譯器頭句之後，依序寫齊五節：

| 小節 | 一定要有的內容 |
|---|---|
| **Camera** | 焦距＋物距＋機位高度／方位；運鏡幅度、速度、時長；起幅與落幅（主體在畫面哪裡）。固定鏡寫 `locked off for 2.0 s` 與構圖位置。 |
| **Motion** | 這一鏡**實際發生的動作過程**：起始狀態 → 施力點與方向 → 重心／支撐的轉移 → 結束狀態。用 `First … then … as … finally …` 串起來。 |
| **Performance** | 看得到的表演：眉、眼、嘴、下顎、肩、呼吸的變化與轉折；聽者也要演。無臉鏡寫手、背、姿態；空鏡寫物件或環境怎麼「演」。 |
| **Light** | 光源方向與色溫；光落在哪個材質上、怎麼反應（濕石、布紋、水面、灰塵）；與前後鏡同一光源。 |
| **Sound** | 鏡內聲音與大約秒數（`at about 0.8 s`）、環境音；有台詞寫起口時間。台詞的 `<d>`／畫外音說明由編譯器接在最後。 |

**REMIX（`video_backend: remix`，PR-R5）也一樣**：五小節同一套、同樣寫在 Layer 2 `five_part_en`，編譯器只換外殼——提示詞變成三欄、`{C-id}` 換成角色英文名（不是 `<Subject N>`）、第 1 鏡前面多了場景句與每個包一句「`<Video N> is 名字, 外觀`」。介紹句只管身份，**站位、坐站、誰在畫面哪一側照樣寫在各鏡的 Motion／Camera**（三人同框寫 `From left to right: A, B, C.`，`h3d staging` D08）。上述檢查（E30–E40、W41–W45）對 REMIX 三欄照跑。格式細節見 `references/tooling.md` §2.3.1c。

階段 4 已經核准、Layer 2 不能改時，五小節也可以只改要改的那幾節：`en_overlay.shots.<gsid>.five_part_en`（只認 `camera`／`motion`／`performance`／`light`／`sound`，沒寫的節保留原值）。同一鏡宣告「看不到誰」用 `offscreen_subject_ids`（不算人數鎖、也不算未綁參考圖），只要豁免參考圖、仍算人數用 `accepted_unbound_subject_ids`；段落級風格錨用 `en_overlay.style_anchor_en`（Ref2VA 與 REMIX 都生效）。

## 二、一定要寫詳細（過薄擋：E31、E32）

| 小節 | 下限（英文字） | 說明 |
|---|---|---|
| Motion | 18 | 必須是**過程**，要有時間順序詞；一半以上的句子在叫人別動（hold／stay／no added…）就擋。 |
| Performance | 8（空鏡 6） | 寫可見變化，不寫情緒形容詞清單（`sad, tense` 不算表演）。 |
| Camera | 8 | |
| Light | 8 | |
| Sound | 6 | 台詞說明不算字數。 |

下限只是「不准空交」的地板，不是目標。Motion 與 Performance 是決定抽卡次數的兩節，寫到審稿的人不看分鏡也能想像畫面。

## 三、不准偷懶（擋：E33–E38）

| 碼 | 禁止 | 改法 |
|---|---|---|
| **E33** 套句 | 同段 ≥3 組重複句、單鏡 ≥2 句和別鏡一樣；跨段同一句出現在 ≥5 鏡、≥3 段。只比 Motion／Performance／Light／Sound（頭句與 Camera 規格本來就會相似）。 | 每鏡回到自己的分鏡重寫。零星一兩句刻意的連戲／防混臉錨只會警告（W33）。 |
| **E34** 後設詞 | `authored`、`approved plate/crop`、`expressly named`、`source-described`、`as specified`、`the specified partner`、`the visible subject`、`stage 5`、`layer 2`… | 模型看不到流程。直接寫畫面裡的東西：誰、在哪、做什麼。 |
| **E35** 禁止句堆疊 | 單鏡 ≥4 句防禦性禁止句（否定詞＋畫面元素：no added step、no new gesture、no particles appear…），或超過四成。描寫用的否定（no tremble、without tears）不算。 | 把要的畫面正向寫出來。全段共用的排除項放 `qa_exclusions`，不要逐鏡重貼。 |
| **E36** 違背分鏡運鏡 | 分鏡寫推、拉、搖、跟、升降、環繞，提示詞卻是 static。 | 照分鏡寫；分鏡改了就回階段 4 重審。 |
| **E37** 對白路由矛盾 | 分鏡標嘴部可見的對白（`visible_mouth_dialogue`），提示詞卻寫畫外音、嘴閉著。 | 畫內對白留 `<d>` 讓 H3 對口型；真的要外部配音就回分鏡改 visibility。 |
| **E38** 編譯後改寫 | `detailed_description` 和編譯器留下的指紋（`metadata.compiled_prompt_sha256`）不符。 | 五小節只能寫在 Layer 2 的 `five_part_en`，再重新編譯。不准在編譯後用腳本或手動覆寫。`subject_definitions`／`retention_analysis` 的自動修正不受影響。 |

| **E40** 抹背景 | `the background is empty`、`blank/plain background`、`empty backdrop`：為了消「背景未鎖」把背景整個抹掉。 | 照綁定的場景圖寫出看得到的東西（vine-wrapped pillars behind her）；只是不要路人就寫 `no one else behind her`。 |

警告（不擋，但要看）：W40 沒有視覺線索的氣氛詞（cinematic、dramatic、tense atmosphere…，同句沒有光、手、眼、動作等具體線索）；W30 舊產物沒有編譯指紋；W32 演完就定格（≥2.5 秒鏡頭用 first…then…finally 寫三步結果、沒有 keeps／still／all the while／at the cut 這類持續詞：模型 1 秒內演完三步，剩下全是靜止。噩盡島 EP01 咬人段因此出現 2–4.5 秒的頓點。改成持續過程，寫一句「切點時還在做什麼」；被攻擊的一方要寫看得見的反應，例如慘叫、弓背、另一隻手反抗）；W33 零星重複句；W39 八成以上是固定鏡（運鏡是階段 4 的決定，確認是刻意的）。
Foyege 導演法的警告（D40–D46，來源 Foyege、H3 0 實測，**只警告不擋**）：W41 台詞鏡有視線句卻沒寫螢幕方向（整段完全沒有視線句由 `h3d staging` D07 報，不重複）；W42 `subject_definitions` 寫了位置或姿態；W43 寫實畫風的全身／遠景鏡另外寫毛孔、絨毛（定版皮膚段豁免）；W44 Performance 只有情緒詞、或出現 AU 代碼；W45 第 2 鏡以後同一句把 ≥3 個主體各配一個世界位置。
LoveUolanda 寫法（噩盡島 EP01 A/B 2 seed，**只警告**）：W50 【動作】鏡（`source_action`＋`action_mark`、無台詞，`action_marks.is_action_shot`）的 Motion 沒有 `Force chain:`。編譯器自己加的 `Forbidden: …` 一行與段首 `Camera law:`／`Cast rule:`／`Environment lock:` 是固定句，不算套句（E33）、不算叫人別動（E32）、不算禁止句堆疊（E35）。

## 動作鏡怎麼寫才不慢（打擊、追逐、被炸飛）

H3 是 24 fps 原生，慢動作感來自「動作只佔鏡頭的一小段」：3 秒打擊鏡真正高速的時間中位數只有 0.62 秒，其餘是起手前發呆與打完定住（《噩盡島》實測，`references/speed-ramp.md`）。Motion 與 Camera 這樣寫：

| 要點 | 寫法 |
|---|---|
| **一鏡一個動作，2–2.5 秒** | 打擊鏡不要塞三步（揮→中→倒）在 3 秒裡平均分配；拆成兩鏡，每鏡一個動作從頭做到尾。分鏡階段就要切好（Combat 段用 2–2.5 s 的鏡）。 |
| **速度詞** | `at explosive speed`、`in a split second`、`snaps`、`slams`、`whips`；不要 slowly／gently／drifts／floats。 |
| **第一幀就在動** | `already in motion in the first frame`：切進來時拳頭已經在半路，不要從靜止起手。 |
| **動作撐到切點** | 最後一個動作寫成 `still … at the cut`（still tumbling at the cut、still skidding at the cut），不要寫「然後停住」。 |
| **騰空寫下墜曲線** | 被炸飛／甩飛：`thrown upward, then dropping fast along a falling curve`，落地另起一鏡。**用 curve，不要用 arc**：E5 會把 arc 當成運鏡詞（camera arc）擋掉。 |
| **施力因果鏈（R3，預設）** | 動作鏡在 Layer 2 `action_and_performance.force_chain_en` 寫「誰的哪個部位先動 → 力量傳到哪 → 結果」：`the beast's neck lowers first, then its jaws drop the last half metre, then its fangs clamp shut around his forearm`；要排除的失敗寫在 `forbidden_en`（`he does not rise by himself`）。編譯器把 Motion 換成 `Force chain: …` 並接一行 `Forbidden:`（含預設的 self-levitating／unmotivated displacement／repeating the same action）。噩盡島 E1-29 甩出 1/2→2/2。 |
| **實體機位（R2，預設）** | 機位寫在 `camera_optics.rig_en`：鏡頭在誰的哪一側、多遠、多高、光軸對哪裡、怎麼移動（`lens 20 cm above the gravel at his left side, 1.5 m from his raised forearm, optical axis level toward the upper right`）；沒寫時編譯器只從角度字推高度與光軸。只露手的插入鏡寫明哪隻手從哪個角入鏡、身體不入鏡。 |
| **打擊鏡固定機位** | 打擊、撞擊、被打飛的鏡 Camera 寫 locked-off／static；跟拍會把畫面上的位移抵掉，看起來更慢。運鏡放在撞擊前後的鋪陳鏡。 |

已經產出的片子有定住、蓄力、飄浮的問題，先用後製變速（`h3d motion` → `h3d ramp`），不用整段重跑。

## 群戲反應鏡：先後序與首幀姿勢（Eian 2026-11-05 對照）

多人同框的反應鏡最容易「所有人同一秒一起動」——模型把同一姿勢的群眾當成同步開關。寫法：

| 要點 | 寫法 |
|---|---|
| **反應要有先後** | Motion 用時間點排順序：`the innkeeper freezes first, a beat later the maid steps back, the child last`；不准寫 everyone simultaneously／all at once。 |
| **首幀姿勢錯開** | 構圖圖裡就不要擺同一姿勢（有人舉杯、有人轉頭、有人後縮）；同一姿勢＝模型讓所有人同時動。這是階段 4 構圖的責任，提示詞端照圖寫。 |
| **身體反應要真** | 吃驚是身體先動：`recoils half a step before his face changes`；不要只寫表情形容詞。 |
| **外力做的事，手沒碰** | 該風／水流做的事寫明手沒碰：`the wind lifts the tarp; his hands never touch it`（不寫這句，模型會讓人自己動手）。 |
| **雲、火、霧不要給臉** | 不寫卡通雲／擬人火；寫材質與運動：`billowing grey-white cumulus with cotton texture only, drifting right`。 |

站位與左右仍照 `h3d staging` D08（`From left to right: …`）；本節只管「誰先動、怎麼動」。

## 提示詞端修法對照（Eian 2026-11-05 錯誤表節錄）

文章的「模型易犯的錯 → 有用寫法」表，只收本 repo 尚未成文的行；已涵蓋的不重複（同時動作見上節、否定失效見 `continuity-ledger.md` §5、憑空出現見 `h3d refcheck`／包母片、嘴動見 E25／W53、段內越來越暗見 `color_jump` QA）。來源是 Seedance 實操經驗，H3 對應欄標註本 repo 的等價機制：

| 模型易犯的錯 | 提示詞端寫法 | 本 repo 對應 |
|---|---|---|
| 東西的數量中途變了 | 數量直接寫死，並寫轉換：`only one yellow envelope in his hand; afterwards his arms are full of white ones` | 送件前核對「道具」項 |
| 一句話兩種意思（「窗戶後面的老人」→車裡冒出人） | 位置寫具體＋把不要的讀法正面排除：`the old man in the window of the stone house at the upper left; the driver's seat stays empty` | `h3d staging` D08 左右、核對「位置」項 |
| 模型自己聯想道具用法（壺總是被倒水） | 乾脆不讓該道具出現在有動作的鏡；要留就寫 `the kettle stays cold on the stove, untouched` | 道具 `absent_objects`（v118 SB-6） |
| 閃電畫得太寫實（整段天打雷） | 寫 `a brief white flicker inside the clouds`，後期把開頭幾幀剪掉 | 打擊四件套（playbook §3.1 閃白） |
| 鏡頭推近沒有寫的那麼明顯 | fl2v：尾幀＝首幀裁一塊放大（`tooling.md` §2.3.2）；r2v：後期再推一點（playbook §3.3 Ken Burns） | `frame_pair_qa.py`、playbook §3.3 |
| 結尾幾幀突然跳回尾幀的樣子 | 後期選一張沒問題的畫面，結尾都停在那張（凍結） | 交界 QA「一側靜止候選」 |
| 第一幀特別銳、和後面不接 | 直接把第一張剪掉再接 | Base i2v 首幀對齊指令（`at 0.00 seconds`） |

## 送件前逐句核對：提示詞 ↔ 構圖圖（Eian 2026-11-05 對照）

文字檢查（E30–E40、W 系列）只看提示詞本身，抓不到「寫得具體但和圖不一致」。送件前把提示詞的每句話和構圖圖**放大**核對——實測能查出「杯子差 13%、帽檐一張有一張沒有、左右寫反」這類錯，是低抽卡率的主要來源。

```
python scripts/storyboard/prompt_sketch_audit.py --root <專案> [--episode EP01]
```

產出 `review/prompt-sketch-audit-<EP>.md`：逐鏡列構圖圖路徑與八項核對（位置、左右、人數、道具、服裝、表情、光影、動線）。agent 逐項看圖勾選；發現不符 → 回 Layer 2 改句或重出構圖，改完重跑。只產清單、不擋關。REMIX 段同時看「包母片裡不該在場的物件」（包壓過提示詞，見 `references/remix-draft-loop.md`）；fl2v 段先跑 `frame_pair_qa.py` 疊圖檢查（`references/tooling.md` §2.3.2）。

## 四、怎麼寫：逐鏡作業流程

**不准寫程式產生五小節內容。** 腳本可以搬運、編譯、檢查，但每鏡五節的文字必須是 agent 讀完這一鏡的資料後自己寫的。

每一鏡依序做：

1. **讀這一鏡的資料**：Layer 2 shot（景別、焦距物距、運鏡、`action_stages`、`observable_expression`、對白與 `speech_events`）、這一鏡的構圖圖（`sketch_file`／分鏡總覽圖那一格）、劇本裡對應的 beat、上一鏡結束時的狀態。
2. **先想清楚四件事**（不用寫出來）：
   - 這一鏡**和上一鏡比，什麼變了**？（位置、視線、光、情緒）只寫變化，不重述不變的外觀。
   - 主動作的**施力點、方向、重心轉移、結束姿勢**是什麼？
   - 觀眾要從臉或身體讀到什麼？用哪兩三個可見的細節表現？
   - 這一鏡有哪個材質會被光或動作影響（衣角、水、灰、紙、皮膚汗光）？
3. **寫進 Layer 2**：`shots[].action_and_performance.five_part_en = {camera, motion, performance, light, sound}`（英文）。五節缺一，編譯器直接報錯，不會退回自動拼句。
4. **寫完一段就編譯檢查**：`python scripts/h3d.py compile … --check`。撰寫審查錯誤要逐條改稿，不准用改寫檢查器、刪規則或手改 segments 的方式過關。
5. **字數**：寫完整版；超過 700 英文字照 `references/h3/shot-five-part.md` 的流程交使用者決定，不擅自壓縮。

### 好壞對照（同一鏡：導遊介紹蛙仙石，MCU）

❌ 套模板（E33／E34／E35）：

```text
Motion: After the guide's opening line, he indicates the stone with an open hand. Hold the authored support and end pose; only an expressly named breath, eyeline, or small gesture may shift, with no added step or prop contact. Performance: Keep the eyes on the specified partner or object; a small breath and one restrained brow change carry the beat without adding a new gesture.
```

✅ 逐鏡親手寫：

```text
Motion: First he walks backward two steps along the rim, then he turns his torso toward the boulder, as his right arm sweeps open with the palm up, finally his hand stops level with the stone's flat top. Performance: A practised tour-guide grin, eyebrows lifted on the name of the stone; he glances back at the group once to check they are following, and the grin widens.
```

## 嚴謹度：每句都要對生成有幫助

寫每一句前問：刪掉這句，影片會不一樣嗎？不會就刪。要寫的是站位（frame left third）、視線、起始與**結束姿勢**、關鍵道具英文名與位置、場景圖裡看得到的背景；不要寫參考圖已有的髮型服裝、沒有線索的氣氛詞。一鏡只放一個主要動作，塞不下回階段 4 拆鏡。每鏡的寫法從 `shot_intent` 推（`references/storyboard/shot-intent.md` §三）。

**每種資訊只寫在一層**（2026-10 Foyege 併入，D41；來源 Foyege，H3 0 實測）：
- 先依鏡頭分，再在鏡頭內切子時間碼：一段先切成 `[Shot N]`，表演要更細的時間點就寫在該鏡五小節裡（`at about 0.8 s`、`on the word "你"`），不另開一套跨鏡的時間軸（`h3/shot-five-part.md` 的 shot 結構本來就是這樣）。
- `subject_definitions` 只寫「<Subject N> 是 <Picture N> 裡的誰」，不寫 frame left、in the foreground、seated、standing by the door（W42）。站位、坐站姿態寫在那個人真正入鏡的 `[Shot N]`。
- 全場站位在第 1 鏡（或站位附表）交代一次；第 2 鏡起只寫這一鏡的變化（誰動了、往哪裡），不再把三個以上的人各配一個世界位置重列一遍（W45）。畫面左右順序照 `h3d staging` D08 寫 `left to right: A, B, C` 一句即可。
- 外貌、皮膚不重寫：參考圖已有的不寫（見上）。守富 2026-09-16 定版皮膚段照舊整段照抄（`h3/skin-realism-block.md`）；景別小的鏡不要**另外**加毛孔、絨毛（W43）。
- Performance 寫看得到的線索，不寫情緒清單、不寫 AU 代碼（W44；AU 只當中文規劃用語，見 `storyboard/acting-and-emotion-library.md` §0.1）。
- 台詞鏡的視線要寫螢幕方向（W41；`storyboard/continuity-ledger.md` §5）。

## 處理警告

逐鏡回到該鏡的 `shot_intent` 決定改法，不准按警告類型一次套用（全部 2 m→1.5 m、全部補 empty）；不准為了過關改核准內容（人群改空坐墊）；交給使用者的每條警告都附「哪一鏡、怎麼改、為什麼、取捨」。詳見 `references/storyboard/shot-intent.md` §四。

## 五、檢查器本身的規矩

- 不准為了過關修改 `prompt_authoring.py` 的門檻或詞表；要調整請開 issue／PR 並附實戰證據。
- 檢查只看文字，抓不到「寫得具體但寫錯」。分鏡與成片仍要人審（階段 4、6）。
