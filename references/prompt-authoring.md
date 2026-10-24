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

警告（不擋，但要看）：W40 沒有視覺線索的氣氛詞（cinematic、dramatic、tense atmosphere…，同句沒有光、手、眼、動作等具體線索）；W30 舊產物沒有編譯指紋；W33 零星重複句；W39 八成以上是固定鏡（運鏡是階段 4 的決定，確認是刻意的）。

## 動作鏡怎麼寫才不慢（打擊、追逐、被炸飛）

H3 是 24 fps 原生，慢動作感來自「動作只佔鏡頭的一小段」：3 秒打擊鏡真正高速的時間中位數只有 0.62 秒，其餘是起手前發呆與打完定住（《噩盡島》實測，`references/speed-ramp.md`）。Motion 與 Camera 這樣寫：

| 要點 | 寫法 |
|---|---|
| **一鏡一個動作，2–2.5 秒** | 打擊鏡不要塞三步（揮→中→倒）在 3 秒裡平均分配；拆成兩鏡，每鏡一個動作從頭做到尾。分鏡階段就要切好（Combat 段用 2–2.5 s 的鏡）。 |
| **速度詞** | `at explosive speed`、`in a split second`、`snaps`、`slams`、`whips`；不要 slowly／gently／drifts／floats。 |
| **第一幀就在動** | `already in motion in the first frame`：切進來時拳頭已經在半路，不要從靜止起手。 |
| **動作撐到切點** | 最後一個動作寫成 `still … at the cut`（still tumbling at the cut、still skidding at the cut），不要寫「然後停住」。 |
| **騰空寫下墜曲線** | 被炸飛／甩飛：`thrown upward, then dropping fast along a falling curve`，落地另起一鏡。**用 curve，不要用 arc**：E5 會把 arc 當成運鏡詞（camera arc）擋掉。 |
| **打擊鏡固定機位** | 打擊、撞擊、被打飛的鏡 Camera 寫 locked-off／static；跟拍會把畫面上的位移抵掉，看起來更慢。運鏡放在撞擊前後的鋪陳鏡。 |

已經產出的片子有定住、蓄力、飄浮的問題，先用後製變速（`h3d motion` → `h3d ramp`），不用整段重跑。

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

## 處理警告

逐鏡回到該鏡的 `shot_intent` 決定改法，不准按警告類型一次套用（全部 2 m→1.5 m、全部補 empty）；不准為了過關改核准內容（人群改空坐墊）；交給使用者的每條警告都附「哪一鏡、怎麼改、為什麼、取捨」。詳見 `references/storyboard/shot-intent.md` §四。

## 五、檢查器本身的規矩

- 不准為了過關修改 `prompt_authoring.py` 的門檻或詞表；要調整請開 issue／PR 並附實戰證據。
- 檢查只看文字，抓不到「寫得具體但寫錯」。分鏡與成片仍要人審（階段 4、6）。
