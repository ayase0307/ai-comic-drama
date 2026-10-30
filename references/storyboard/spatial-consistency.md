# 空間一致性：場景母片、牆面分配層、構圖板店感鎖、雙人引子

> 來源：老易空間邏輯實驗 2026-10（第一批 70 支、第二批 86 支，REMIX／H3 本機實測；數據與限制見 `docs/experiments/laoyi-spatial-2026-10/README.md`）。
> 和 `continuity-ledger.md` §3（三種方位）、§4（站位附表）、`consistency.md` §4（場景主圖、多角度分步生成）搭配使用；本檔只補「場景圖和提示詞怎麼一起鎖住空間」。

## 證據等級（先讀）

| 規則 | 證據 | 等級 |
|---|---|---|
| §1 母片照平面圖畫、含所有座位 | 同提示詞同 seed，只換母片：文戲可用 62%→75%（5/8→6/8）；S01-b「走到角落桌坐下」座位錯 2→0，換母片後五組＋D′ 14/14 全對 | **實測、方向性**（樣本小、單人評分） |
| §2 牆面分配層 | 文戲 H 88% vs 基準 A′ 75%（+13，未達原定 +25）；換牆 0（但基準也 0）；武戲 H 50% vs A′ 0%（武戲另含動作方向句，非單一變數） | **實測、方向性**；未過門檻 |
| §3 構圖板以母片為底重畫 | 舊板（自畫風）D／E：座位錯 0 但場景質感漂 11 段次、換牆 4；以新母片為底重畫的 D′：94%（15/16）、座位錯 0、場景漂移 0、換牆 0，難鏡 S01-c 唯一拉對（3/4） | **實測、方向性**；同 seed 比 +25 壓線、全部比 +19，判未過 |
| §4 只拍生物的鏡頭綁店內實景參考 | 兩批一致：帶任何一張店內實景圖 0/10 外洩（第一批 D／E 0/4、第二批 F／G／I 0/6）；只靠文字或平面線稿會變灰棚（第一批 A／B／C 4/6、第二批 A′／H 3/4） | **實測**，兩批同方向（仍屬小樣本） |
| §7 雙人引子（段縫硬切到單人近景前先拍 2 s 雙人鏡，組裝剪掉） | PR #115 T4（2026-10-29，REMIX long 480P，同段同種子盲評）：同 3 段（S02／S04／S06）各 2 抽，單支＋進段接點共 12 個樣本，跑位／左右翻、重演、人數錯、需重生都是 **0/12**；同段同種子現流程 4/12（33%）、#115 新流程 5/12（42%）有跑位或重演，需重生單支現流程 3/6、新流程 4/6 | **實測**，小樣本（一場戲、一個後端、每段 2 抽）→ 只建議（W47） |
| §5 多視角場景表從同一母片逐張派生 | 第二批依此做出的 ①–④ 四張都 7 桌、門窗牆位一致（`consistency_v2_thumb.jpg`）；但「分張場景表」F 組在影片上 +0 | 生圖階段**實測可行**；對影片可用率**未證實** |

共同限制：評分只有 Hark 一人（看關鍵幀接觸表＋密集抽幀）、部分盲評；每組文戲 8 段次，±25 個百分點只等於 2 段次；兩批都**沒有任何一組正式通過原定門檻（≥+25 個百分點）**。以下規則是「改善方向一致、成本低」才採用，不是已證實的定律；有新數據時優先修本檔。

## §1 場景母片：先照平面圖／站位座標畫，包含劇本所有座位與走位目標

1. 先有世界層座標（`continuity-ledger.md` §4 站位附表、本檔 §2 牆面分配表 JSON），再畫母片。母片參考＝「店感參考圖＋依座標畫的無字配置示意圖」。
2. 母片要看得到、數得出**劇本會用到的每一個座位、桌、走位終點、出入口**（例：沈要坐的「左後角小桌，夾在菜檯北端與廚房門洞之間」必須畫在母片上）。模型會直接照抄母片的座位數與排法；母片沒有的座位，提示詞寫得再清楚也常被放到別張桌。
3. **母片和平面圖／站位附表矛盾時，改母片（重生），不要用提示詞覆蓋。** 第一批的座位錯，病根就是 `<Picture 1>` 本身沒有那張桌。
4. 驗收：Agent 逐項數（桌數、門窗在哪面牆、出入口數量、主光方向），和座標表一致才給使用者確認；不一致就重生。
5. 已知殘留：只有母片還不夠——機位看不到「角落桌在門洞西側」這種關係的近景（S01-c），A′ 仍 0/2；要靠 §3 的母片底構圖板。

## §2 提示詞「牆面分配層」（wall map）

每一鏡（`[Shot N]` 內、`Camera:` 之前；或五小節 camera 前）前置一小段，**每鏡重寫，不准寫「同上／same as above」**：

1. **Wall map**：每個場景常量逐一寫「只在哪一面世界牆」＋「本鏡在畫面哪裡」。只寫會出錯的硬地標（門、窗／玻璃、出入口、長檯、隔間牆、桌凳材質與數量）。
2. **三種方位分開寫**：世界方位（北牆）、人物自身左右（他的左手）、本機位畫面左右（畫右）——同一個東西三種說法可能都不同（沈面向西南，門洞在「他的左手邊」卻是「畫右」）。
3. **主光鎖世界位置**：「暖光只從東牆玻璃進來」，再寫它在本機位落在畫面哪一側。
4. **每鏡一句「不新增門窗」**：寫本鏡看得到的那面牆（`No glass or street appears in that doorway.`）。每鏡只一句、各鏡不同（避開跨段套句與否定句堆疊）。
5. 第 2 鏡起加配對句：同一時刻、同一側、不鏡像、不換位；近景寫「沿上一鏡方向收緊，不是新機位」。
6. 武戲另寫打鬥後場景狀態（破洞、側倒桌位置、碎盤）與拋飛的世界方向（「往西北、店內深處、遠離玻璃門」）。

模板（英文進提示詞；`{}` 逐鏡填）：

```
Wall map: the {長檯} is only on the {west} wall{, 本鏡位置}; the one {開口描述} is only in the {north} wall{, 本鏡位置}; the {門與玻璃} are only in the {east} wall{, 本鏡位置}; plain {south} wall; {N 張桌的材質與凳}{, 本鏡桌況}.
{本鏡一句不新增門窗：No {glass/door/window} appears in {本鏡看得到的那面牆}.}
{The camera is {世界位置}, facing {世界方向}; {人物} faces {世界方向}, {物件} on his own {左/右}, frame {left/right}; {主光} comes only from the {世界方向}, frame {left/right} here.}
{第 2 鏡起：Same moment, same {south} side, the room unmirrored; tightened along Shot 1's direction, not a new camera position.}
```

可選工具：`scripts/storyboard/wall_map.py` 把牆面分配表 JSON（範例 `templates/wall-map.example.json`）展開成每鏡句子，並檢查「同上」、缺否定句、否定句跨鏡重複、字數；四正向機位會自動換算世界方位→畫面左右。**不接進預設編譯**，要用時手動貼進 Layer 2 或提示詞。字數預算：hosted API 整段 7000 字元上限，每鏡前置約 400–550 字元。

## §3 構圖板／分鏡板必須以場景母片為底重畫（店感鎖）

- 構圖板、四格分鏡板若要當影片參考，**一律以已驗收的場景母片（＋派生視角）為底重畫**，並在板提示詞寫「店感鎖」：牆面材質／顏色、桌面材質、整體色溫，各寫一句正面描述＋一句不要什麼（淺木框奶油面板，不要深木；淺灰白石面，不要大理石；冷白，不要整片暖橘）。
- 不以母片為底、讓生圖模型自由畫的板：座位雖然拉對，但板子的畫風會被帶進成片（深木牆＋大理石桌、門洞變玻璃隔間＝換牆），淨效果被吃掉。
- 板上的牆面分配要和 §2 同一份表一致；板與劇本 Camera 矛盾時（例如要求畫右是玻璃門，但依座標那一鏡畫右是門洞），回去問使用者改機位或改要求，不要只改板。
- 這不改 `consistency.md` §7.4 定律三（整板當參考要宣告 `reference_view: "panel"`）；只規定板本身怎麼畫。

### §3.1 自動建議：哪些段該改用母片底四格板（W46）

`h3d staging` 會對符合下列**全部**條件的段印 💡 W46（階段 4 用 `--layer2`；階段 4／5 審核頁的「自動建議」區塊也會列）。只建議：不擋送件、不擋核准、不改預設編譯；判不了的條件一律當不符合（保守）。

| 條件 | 用哪個欄位判斷 | 為什麼 |
|---|---|---|
| 不是武戲 | 無 `dramatic_beat_type: Combat_Impact`、無自動 `h3_loras`、動作欄無打鬥詞 | D′ 只測了文戲，武戲沒有證據 |
| 同一已驗收場景母片 | 已編譯段：`reference_images` 有 `type: scene`（remix：`refmods` 有 `kind: scene`）；Layer 2：`asset_refs.scene_id` 找得到母片圖且階段 2 已核准 | 板要以母片為底重畫（本節第 1 條） |
| 室內 | `metadata.interior`，否則 handoff 場景 `setting.interior`／`int_ext` | 實驗只有室內固定場景；戶外長直線性鏡頭不適用 |
| ≥2 名角色有固定座位／站位 | 各鏡 `character_ids`／`visual_subject_ids`；`positions`、`anchor_objects`、blocking 的座位詞 | 要鎖的是「誰坐哪張桌」 |
| 段內有近景／特寫 | `shot_size` ∈ MCU／CU／ECU／OTS_CU（代理判斷：景別看不到定位結構） | S01-c 這類近景只有 D′ 拉對（3/4，A′ 0/2） |
| 文戲 | 至少一鏡有台詞 | 同上，證據來自對白段 |

已在用板（場景參考已宣告 `reference_view: "panel"`）不再建議；不採用就寫 `staging_waivers`（code W46＋使用者原話）。規則表在 `scripts/storyboard/board_advisor.py` 的 `RULES`，九宮格等其他板型另案測試，有數據再加新規則與新代碼。

## §4 只拍生物或無人物的鏡頭：綁一張店內實景參考

- 畫面裡只有生物（或沒有人物）時，生物設定圖的純色棚拍背景會蓋過場景，成片變灰色攝影棚。
- 這類鏡頭所在的段，**至少綁一張店內實景視角圖**（母片或派生視角，最好是最接近本鏡機位的那張），介紹句指名它對應哪一鏡（`<Picture 2> … for Shot 1`）。
- 只寫文字（`No plain studio backdrop replaces the room`）或只給俯視平面線稿都壓不住。
- 生物設定圖本身仍照 `consistency.md` §3.2 用純色背景，不要改成帶場景的劇照。

## §5 多視角場景表：從同一母片逐張派生

照 `consistency.md` §4「多角度分步生成」：① 正面母片 → ② 只用①生反打並逐項驗收（門窗有沒有換牆、家具背面、主光方向）→ ③ 側面、④ 高角度用「①＋②」生成。每張驗收時數桌數、對門窗牆位；不要一次生四宮格。

- 一張場景表一個視角，影片段只放本段鏡頭真正會看到的那 1–2 張（不要整張 2×2 拼圖送影片）。
- 證據提醒：照這個流程做出的四張圖一致性良好，但「把分張場景表當影片參考」本身在第二批沒有提升可用率（F +0、G 拼圖 +0）；它的主要價值是 §4 的店內參考與 §3 的構圖板底圖。

## §6 白模分工與精度三檔（空間預演，選用）

> 來源：2026-10 Foyege 併入（D46；Foyege ZTiUwLPAqkM、T4QqUf5i-OI），**H3 0 實測**，屬 `sourced` 等級。原本寫在已移除的 `h3d sketch` 構圖說明裡，2026-10-28 搬到這裡；規則本身與該工具無關。

- 分工：人物參考圖管長相與服裝；場景母片（§1）管環境外觀；白模（圓柱／雪人人偶、粗模）管**隨時間變化的空間**：誰站哪、誰擋誰、鏡頭從哪看。三者不互相代替。
- 精度依「動作精度」選，不只看幅度：
  1. 站位、粗略移動 → 圓柱／雪人極簡模；
  2. 特定姿態（跪地、後仰、手被吊起）→ 四肢清楚的人形粗模；
  3. 精準動作（拋接、高難打鬥）→ 綁骨骼逐輪調關鍵姿態或導入動作素材。**本 repo 不支援**，也不引入 Blender 依賴。
- Foyege 的觀察：白模越細，越需要提示詞約束（僵硬動作會被帶進成片）；越簡單，模型發揮空間越大。所以一般走位停在第 1 檔，把篇幅留給表演。
- 什麼時候需要連續運鏡預演：鏡頭要沿路線連續移動、依序揭示多人、遮擋與交接要準。人物靜態說話、轉頭、常規鏡頭用參考圖＋提示詞就夠。
- **白模渲染影片當 H3 `<Video N>` 運鏡參考：尚未支援、未實測**（T5）。構圖圖照舊只給人審，不送 H3（D19／D32／D34）。
- 本 repo 目前沒有內建白模工具；世界層座標用 `continuity-ledger.md` §4 站位附表＋§2 牆面分配表，REMIX 段落另有 `positions`（D09／D10）。

## §7 雙人引子：段縫硬切到單人近景前，先拍 2 秒雙人鏡（組裝自動剪掉）

> 來源：PR #115 T4 實測 E3 組（2026-10-29，噩盡島取材的一場自助餐店文戲，沈／賴／葉三人，REMIX 角色包，long 480P，`ejin3_*` 包；資料在該次測試的 `results.json`，盲評代號另存）。外部出處：phileiny/h3-storyboard-skill §七之二④（https://github.com/phileiny/h3-storyboard-skill ，H3 上補引子後一次就對，C 級）。
> T4 同時測的其他做法（逐鏡站位欄位、背景錨點句、CONT 交接塊、末 1 秒定格、E1 上一段真實末幀）**都沒有改善**：新流程跑位＋重演 18/26（69%）比現流程 16/26（62%）還高、E1 1/8 重演，所以只收這一條。

**問題**：段縫硬切後，本段第 1 鏡直接開在單人近景（正反打的反角、插入鏡後回到人物、切到剛進門的第三人），H3 看不到另一個人在哪，常把單人鏡拍成過肩鏡並多畫一顆錯高度的後腦、把坐地的人改成站在桌後、或換到錯的那面牆（T4 現流程／新流程在 S04、S06 反覆出現）。

**做法**：本段第 1 鏡前面先加一顆 2.0 s 的雙人鏡，兩人都在畫內、站位和本場一致，之後硬切到原本的單人鏡；組裝時把這 2 秒剪掉。引子和本段在**同一次 H3 生成**裡，不需要另外生成任何東西。

### 什麼時候加（`h3d staging` 會用 💡 W47 提醒，全部符合才提醒）

| 條件 | 判斷 |
|---|---|
| 同場、不是本場第一段 | 和上一段同 `scene_id`（或 `narrative_scene_id`） |
| 段縫是硬切 | 不是同一顆鏡頭拆兩段：`seam_in` 不是 `cont`，且上一段最後一鏡和本段第一鏡不是「同主體＋同景別」 |
| 第 1 鏡是單人近景 | `character_ids` 只有 1 人，景別 MS 或更近（MCU／CU／ECU／OTS） |
| 有對戲的人在畫外 | 本段後面的鏡頭或上一段裡有另一名具名角色 |
| 文戲 | 本段至少一句台詞；武戲沒有證據，不建議 |

T4 裡三種接點都有效：正反打換主體（S01 沈 MCU → S02 賴 MCU）、插入鏡後回同一人（S03 賴手 CU → S04 賴 MCU，一鏡到底的單人段）、雙人望門 → 第三人進門（S05 → S06 葉 MCU）。同機位續接（CONT）、第 1 鏡本來就是雙人或全景的段不加。不採用就寫 `staging_waivers`（code W47＋使用者原話）。

### 怎麼寫（Layer 2，階段 4 定分鏡時就加；五小節照 `prompt-authoring.md` 親手寫，不由程式產生）

1. **第 1 鏡＝引子**，標 `"dual_lead_in": true`（只能標在第 1 鏡）。
2. `character_ids` 剛好兩人：本段第一個單人鏡的主體＋他對戲／視線指向、此刻在畫外的那位（W47 訊息會點名）。兩人的 `positions`／左右要和本場站位附表一致。
3. **時長 2.0 s**（T4 實測的就是 2.0 s。#120 把編譯器鏡長硬下限降到 1.2 s，但 1.2–2.0 s 仍屬「短鏡未實測」只提醒、H3 切點誤差約 0.12 s，更短的引子沒有證據，所以引子維持 2.0 s；T4 當時原計畫 1.5 s，是被那時的 2 s 編譯下限擋掉才改 2.0 s）。其後每一鏡的 `start_time`／`end_time` 與 `speech_window`（含 `line_timecodes`、`extra_lines[].speech_window`）**整段往後挪 2.0 s**；`metadata.target_duration_sec` 加 2.0，`frames` 由 compile 照 17n+5 向上取（T4：7.29 s／175 幀 → 9.42 s／226 幀，多 51 幀）。
4. **鏡頭**：雙人 MLS（`medium-wide shot`），28mm、約 5 m，固定機位（`holds a static shot`／locked off），從本場主機位那一側、站立眼高；兩人分別在畫面左三分之一、右三分之一。Camera 句照 §2 寫牆面分配與兩人各自的背景錨點。
5. **Motion 只寫段開頭當下的姿勢＋一次小的視線交接**，逐人寫、先後分開（staging D11）：「左邊 A 坐在…；右邊 B 站在 A 東邊約兩公尺。先 A 抬頭看向畫右，再 B 低頭看向畫左」。**不演本段或上一段的事件**（不再進門、不再起身、不講台詞），否則就是把重演搬進引子。
6. **Performance**：`Both hold still for a breath; nobody speaks yet.` 這類；**Sound**：只有環境音。**引子不放台詞、不放 `speech_window`**（會被剪掉；組裝遇到會直接擋）。
7. 第 2 鏡（原第 1 鏡）照常寫，編譯器會在 2.0 s 處寫成硬切（`At 00:02.000, the shot cuts to …`），不用另外加欄位。

T4 實際送件的引子（S02，REMIX 三欄；牆面分配句略）：

```text
[Shot 1] … The shot opens on a medium-wide shot (28mm, 5m) of Shen Luonian, as the camera holds a static shot.
Camera: … Two-shot establishing the two of them from the south side at standing eye height, 28mm from about five metres,
locked off; Shen Luonian on the left third and Lai Yixin on the right third. Background anchors: behind Shen Luonian is the
steel steam counter with its glass sneeze guard; behind Lai Yixin is the tall glass door with the orange streetlamp outside.
Motion: On the left Shen Luonian is sitting on the tiles with his back against the edge of a toppled table top, knees up;
on the right Lai Yixin stands about two metres east of him. First Shen Luonian looks up toward frame right, then Lai Yixin
looks down toward frame left, his grin fading.
Performance: Both hold still for a breath; nobody speaks yet.
Light: In the opening two-shot the room is under steady white tube light with the orange street glow on the right.
Sound: Only the steady fluorescent hum fills the quiet room for a breath.
[Shot 2] At 00:02.000, the shot cuts to a medium close-up (50mm, 2m) of Lai Yixin, …
```

### 剪掉（不用另外後製）

- 階段 7 `h3d assemble` 讀到第 1 鏡 `dual_lead_in: true`，**自動剪掉片頭到該鏡 `end_time`**，台詞窗與字幕一起前移；後製變速段會先換算時間。成片長度＝段長 − 引子。
- 格式不對（不在第 1 鏡、不是兩人、短於 2 s、引子裡有台詞、後面的 `speech_window` 沒往後挪）時，`h3d staging` 報 ⚠️ W48，`h3d assemble` 直接擋該段，不會剪錯。
- 引子那 2 秒仍然要看：它是 QA 判斷「兩人左右／高度有沒有對」最快的一格。

### 成本與限制

- 每段多生成約 2.1 s（T4 每段 7.29 s → 9.42 s，約 +29%）。
- **這是「無廢片」原則（不生成要剪掉的秒數，`tail_freeze_hold` 預設關）唯一的例外**：引子的 2 秒一定會被剪掉，但 T4 12/12 沒有跑位或重演，而不加引子的段 4/12 要整段重生；多生成 2 秒比整段重生便宜。其他「生成後再剪」的做法（例如末 1 秒定格）照舊不收。
- 節奏閘門不計引子：`pacing_gate`（密度、有人聲鏡比例 ≥80%、切鏡後開口、開口次數、無台詞鏡）、`validate_storyboard` D1–D4、說話佔比、分段時長提醒、9:16 景別比例、audit W13 說話佔比，都先拿掉引子那一鏡、時間整段前移 2.0 s、段長扣 2.0 s 再算（`dual_lead_in.strip_layer2`／`strip_pacing`）。時長守恆、17n+5 取整、tail-fit 照含引子的生成長度算（末句後留白是相對段尾，與引子無關）。
- 證據只有一場戲、REMIX、480P long、每段 2 抽；E3 疊在 #115 新流程（背景錨點句）上跑，但新流程單獨跑更差（同段 5/12），所以把改善歸給引子。12 個樣本裡記了 1 次跳接（S06 第 1 抽第 3 鏡後場景／站位略變，判「尚可」、不需重生）。
- ref2va 後端、武戲、三人以上同框的段沒測；有新數據時優先修本節。
