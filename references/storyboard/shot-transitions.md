# 鏡間銜接與佔位延續（單一入口）

> 鏡頭和鏡頭之間怎麼接、段和段之間怎麼縫、人物站位怎麼跨鏡維持，**以本檔為準**。其他文件只留短摘要並指回這裡。
> 研究依據：2026-10-29 外部調研（awesome-short-drama-skills 107 個 repo＋中英文平台與剪輯經典；彙整見本 repo 外的研究筆記，關鍵來源列在 §10）。
> 程式：`scripts/storyboard/transition_lint.py`（D15–D24；D21 只建議，其餘警告），併入 `h3d staging` 與 `compile --check`；欄位見 §7；影片端接點自檢 `h3d seamcheck` 見 §6.1。
> 2026-10-29 第二輪：T1 回溯驗證（103 個接點盲判）後修正景別自由文字、同場判斷、D15 人→空鏡、D16／D20 誤報，D21 降為建議，新增 D22 重演／狀態延續、D23 朝向對站位、D24 反打換邊。

## 0. 先讀：證據等級與本檔的界線

| 等級 | 意思 | 例 |
|---|---|---|
| **A** | 經典原文、官方文件、有量測的研究 | Dmytryk《On Film Editing》、Barry Salt 對白剪點量測、火山方舟官方 PDF |
| **B** | 權威教學、體系化教學站 | 30° 規則教科書、StudioBinder、iamos.zone 剪輯環節 |
| **C** | 作者自報的 AI 實測（單模型、自評、樣本小，無獨立盲評） | zenstory 尾幀 NCC、phileiny 同 seed 對照、manju-laoli 粉絲回饋 |
| **D** | 規則或 validator，沒有生成證據 | Toonflow 段縫閘門、DirectorSKILL 15% 畫寬 |

- **本 repo 自己在 H3 上量過的**只有站位附表／左到右名單（`h3d staging` D06–D08，ch02 EP04）與老易空間實驗（`spatial-consistency.md`，方向性）。本檔其他規則**都沒在本 repo 實測**；要升級成錯誤，先跑 §9 的 E1–E3。
- `references/h3/` 是上游 h3-video-prompting 的同步檔（hash 釘住），本檔**不改**它們；`h3/camera-and-transitions.md` §5–6、`h3/shot-variety-and-staging.md` §3、`h3/action-choreography.md` §7 是 H3 寫法層的原文，本檔是分鏡層的規則與欄位，兩者衝突時以本檔為準並回報上游。
- **既有定案不改**：「每段獨立 Ref2VA／REMIX，不用尾幀續接」（`skill-guide.md`、`pipeline.md` 階段 6、`consistency.md` §0）照舊。外部實測與它衝突的地方在 §4.3、§9 並列，標「待 E1 驗證」。

## 1. 接點分類

| 接點 | 在哪 | 誰負責 | 欄位 | lint |
|---|---|---|---|---|
| **段內切**（within） | 同一次生成裡的 `[Shot N]` 切點 | 模型照提示詞切 | `shots[].cut_in` | D16、D17、D19、D20、D22、D23、D24 |
| **段縫 CUT** | 兩次獨立生成之間，換機位硬切 | 讓模型**重建**畫面；剪輯直接硬接 | 下一段 `seam_in: "cut"` | D15、D22、D23、D24 |
| **段縫 CONT** | 兩次獨立生成之間，同機位技術分段（長動作、一句長台詞、一鏡到底被拆開） | 剪輯把上段末 1 s 剪掉、下段從交接狀態起手 | 下一段 `seam_in: "cont"`＋`entry_state`，上一段 `exit_state` | D18、D22 |

- 預設：同場段縫走 **CUT**（和既有「段縫換機位或換景別」一致，`continuity-ledger.md` §6）。CONT 只在動作或台詞真的被拆開時用。
- `shots[].cut_in.type`：`hard`（一般切）、`match_action`（動作中切）、`eyeline`（看→看到）、`reaction`（反應鏡）、`insert`（插入鏡）、`scene_change`（換場）、`cont`（同機位延續，段內罕用）。`motivation` 寫這刀帶來的新資訊或理由。**第 1 鏡的 `cut_in` 不用寫**（寫了也不看）：段縫的接法看段層 `seam_in`。
- `seam_in` 和既有 `continuity_handshake.mode`（`INDEPENDENT_REF2VA`…）是兩件事：mode 是生成路線，seam_in 是剪輯關係。程式**不從 mode 推 seam_in**（舊專案才不會冒出新警告）。

## 2. 段內切規則

| # | 規則 | 等級／來源 | lint |
|---|---|---|---|
| 2.1 | **切必帶新資訊**（主體、空間、狀態、視角、時間）；只是換距離或微調角度 → 用運鏡，不切 | B（`h3/camera-and-transitions.md` §5）；多 repo 共識（suihe1、zenstory、mini-yifan，D） | — |
| 2.2 | **同主體相鄰鏡：角度 ≥30° 或景別跳 ≥2 級**（跳 1 級要再配角度 ≥30°）。景別級：ELS0／LS1／MLS2／MS·OTS_MS3／MCU4／CU·OTS_CU5／ECU6；OTS 和非 OTS 互切只在兩鏡都沒填角度時算換角度（有填就看角度）；插入鏡（手、傷口、道具）前後與動作匹配切不查 | A/B：30° 規則（Wikipedia、《Grammar of the Edit》、Dmytryk 同軸推近需極精準時機）；跳 2 級只有 Joel W. Smith 明寫（B）＋DirectorSKILL（D） | D16 |
| 2.3 | **不連 3 鏡同景別**；正反打主體輪替（A→B→A）不算 | C/D：Shanyin 拉片（同景別連 >4 要警惕）、DirectorSKILL／alchaincyf「不要連兩鏡同景別同角度」 | D17 |
| 2.4 | **時間只往前、不重演**：後一鏡第一格晚於前一鏡最後一格；換景別名稱不能把同一動作再演一次；段縫同理（見 §4.5 事件帳） | D：waoowaoo、Toonflow、xiaxia、djyy 共識；本 repo T1 盲判 18 個問題接點有 7 個屬此類（觀察） | D22（關鍵詞＋事件帳；動作匹配切不查） |
| 2.5 | **Match on action**：前鏡收在動作中段，後鏡從同一動作後半開始；只放在**同一段內**，跨段讓前段做完 | A：Dmytryk；D：Toonflow §A7.4 | — |
| 2.6 | **視線接**：看→看到；眼神先定住再切，下一鏡交代被看物 | B：StudioBinder eyeline match；既有 D04 | D04 |
| 2.7 | **正反打先給 1.5 s 雙人引子**（後製剪掉），單人反角才拍得對；那一段要多給 1.5 s | C：phileiny §七之二④（H3，補引子後一次就對）；**本 repo 未驗，見 E3** | — |
| 2.8 | **台詞跨切點**：兩側都寫 `<scenetrans>`＋`continues seamlessly across the cut`，台詞只說一次（L-cut 延到聽者） | B/D：H3 開源格式（`h3/audio-and-dialogue.md`）、mini-yifan base-en.txt；本 repo 未實測 | D19 |
| 2.9 | **要切就整顆靜止，要運鏡就不放切點**（運鏡會把切點內插成連續推近）；例外：兩鏡主體和景別完全不同 | C：phileiny §七之二②（H3 失敗兩次） | —（`h3d staging` D13 只看整段固定） |
| 2.10 | 一段的切點數有預算：10 s 約 2–3 鏡；鏡數超過時長能承載，模型會在動作中亂切 | C：xixihhhh、zenstory；本 repo 定案「7–10 秒、2–4 拍」 | — |

寫法：第 2 鏡起的頭句已由編譯器寫成 `At mm:ss, the shot cuts to a <景別> …`；本檔只決定**切什麼**，句型不變。

## 3. 段縫 CUT：三選一閘門

只比**上段末鏡 vs 本段首鏡**，至少滿足一項：

1. **主體不同**（`character_ids` 集合不同：雙人→單人、人→局部、人→空鏡；**一側 `character_ids` 為空＝空鏡或局部，算主體不同**；畫外說話的人不放 `character_ids`，見 §7）；
2. **景別差 ≥2 級**；
3. **機位角度差 ≥90°**（`camera_optics.azimuth_deg` 兩邊都有才算數）。

三項都證明不了 → D15。修法只改**本段首鏡的主體、景別、角度或構圖**，不改劇情，也不為了接戲新增原文沒有的橋接動作（Toonflow：禁止補「把筆放下又拿起來」）。

- 等級 D（HBAI-Ltd/Toonflow-app `packages/skills/workflow/SKILL.md` §A7.3，無實測）；方向和 2.2 的 30° 規則一致。高風險組合：同主體＋同景別＋近似角度跨段、同一手部動作跨兩次生成硬接。
- **上段結尾不定格，留 0.5 s 接口餘量**（manju-laoli，C：粉絲回饋；0.5 s ＝疊化 8–12 幀／閃白 6–10 幀／遮擋 10–15 幀的餘量）。⚠️ 這和本 repo 預設 `style_lock.tail_freeze_hold: true`（末 1 秒靜止）衝突：預設不改；CUT 段縫要留動作餘量時，該段設 `tail_freeze_hold: false` 並在 `choice_why` 寫理由。H3 片尾 1.2–1.7 s 常崩（phileiny，C），所以「不定格」不等於把動作排到最後一格。
- 既有 D05（上段尾鏡與下段首鏡同景別且都固定）照舊，沒寫 `seam_in` 也會跑；D15 只在 `seam_in: "cut"` 時跑。

## 4. 段縫 CONT：定格→真實末幀→同景別起手→交接塊

### 4.1 做法

1. **上段最後 1 s 定格、無台詞**（剪輯剪掉這 1 s）。本 repo 預設 `tail_freeze_hold` 已寫 `The final second holds still before the cut.`；要再確認 speech_window 不進最後 1 s。
2. **真實末幀**：上段生成後截最後一張乾淨畫面，人工核對 `exit_state`（位置、朝向、距離、動量、傷損、握持、背景錨點）；不一致就以畫面為準改 `exit_state`／`segment_end_state.observed_final_state`。
3. **下段同景別起手**：首鏡景別和上段末鏡相同（manju-laoli：走尾幀承接時段縫兩側同檔，靠視角或機位高度做剪輯關係，C）。要換景別就改成 CUT。
4. **交接塊**：下段 `entry_state` 逐項寫成**絕對狀態**，編譯器只在 `seam_in: "cont"` 時把它寫在第 1 鏡開頭：`Opening state at 0.0 s: <Subject 1>: position …, facing …, holding ….`（REMIX 用英文名）。**禁寫「承接上一段／同上／same as the previous segment」**——模型看不到上一段（Toonflow 核心前提，D）。中文值要另給 `entry_state_en`（或階段 5 `en_overlay.entry_state_en`），否則不寫進提示詞、只留 compile note。
5. 有交接塊時，#133 的「Starting state carried over from the previous segment」句不再另加（兩句會打架，且後者帶指代字眼）。

### 4.2 D18 查什麼

缺 `exit_state`／`entry_state`；兩者共同欄位不一致或入口漏寫出口有的欄位；上段最後 1 s 有台詞；首鏡景別和上段末鏡不同；`entry_state` 寫指代詞。上一段不在這次輸入時，`compile --check` 會到同目錄 `layer2-*.json` 找。

### 4.3 和既有定案的衝突（並列，不改定案）

| 說法 | 證據 | 現況 |
|---|---|---|
| 本 repo 定案：每段獨立 Ref2VA／REMIX，**不用尾幀**當下一段參考 | FreeVideo API `references` 與 `first/last` 互斥 422、續接段退化成塑膠臉（本 repo 歷史實測，限該 adapter）；外部模型首幀混 Ref2VA 失敗 | **維持**。CONT 只用「文字交接塊＋同景別起手」，不送尾幀 |
| zenstory：H3 用**上一段真實尾幀當參考**，3 次中 2 次接縫 NCC 0.94–0.97；只靠角色圖＋場景圖 0.01–0.41，景別站位都跳 | C（同一模型自評，n=3） | **待 E1** |
| Toonflow：明令禁止用上一段尾幀當站位參考，站位靠文字座標重建 | D（無實測） | 與定案同向 |
| phileiny：同視角鏡頭用同一張「構圖錨點格」當母版，**不要串接**（A 末格→B 母版→C…每接一次掉一次品質）；武打例外 | C（H3） | 參考，未採用 |
| Seedance 延長接縫：前段末刪 6 幀、後段頭刪 1 幀 | A（火山方舟官方 PDF，限 Seedance） | 不適用 H3，剪輯時可參考 |

### 4.4 拋棄式前導（選用，預設關）

- 做法：段頭先生成 0.5–1.5 s「照起始狀態靜止」的前導，讓模型暖機、萬一重演也發生在要丟掉的那段，剪輯時切掉。
- **預設關**：守富 10-29 決定不加後處理、不多花生成；只有對話反打或 CONT 段縫反覆出錯時才對該段開。
- 寫法：段層 `lead_in_s: 1.0`（或 `metadata.lead_in_s`），**段長要多留這段時間**（shots 的時間軸包含前導）。編譯器在第 1 鏡開頭加一句 `From 0.0 s to 1.0 s everyone holds still in the opening pose; the action of this shot starts after 1.0 s.`；沒寫 `lead_in_s` 時提示詞一個字都不變。
- 剪掉：階段 7 `h3d assemble` 讀 `lead_in_s` **自動剪掉片頭這段**、台詞與字幕時間一起前移，不用另外剪；`h3d seamcheck` 的段縫對照圖也改抽前導後第一格。前導裡不要排台詞（會被剪掉）。
- 證據：方向性想法（接力棒流程草案），本 repo 未在 H3 驗證（見 §9 E4）。

### 4.5 事件帳：不重演、狀態延續（D22）

- 劇本拆成 beat（一次性事件：站起、坐下、倒地、破牆、吞食、撞翻…），每個 beat 給一個 ID。每段只能**新做**還沒發生的 beat。
- 段層選填欄位：`beats_done`（本段開始前已完成的 beat ID）、`beats_new`（本段新做的 beat ID）；逐鏡也可寫 `shots[].beats_new`。
- **已發生的事寫成靜止狀態，不用動作詞重述**：寫「婦人已站起，手撐桌緣」「the table already lies on its side」，不寫「婦人站起來」「the table topples」。lint 看到「已／仍／still／already」開頭的狀態不報。
- D22 查：
  1. 事件帳：本段 `beats_new` 的 ID 已在同場前面各段新做過；同一 ID 同時在 `beats_done` 和 `beats_new`；上段新做的 ID 本段 `beats_done` 沒列（帳斷了）；段內兩鏡 `beats_new` 重複。
  2. 關鍵詞（沒寫事件帳也會跑）：上段結束狀態（`exit_state`、`segment_end_state`、`ledger_out`）＋上段末鏡動作已完成某事件，本段首鏡動作又演一次；或入口（`entry_state`、`ledger_in`，同一主詞的子句）退回事件之前（站起→仍坐著）。段內相鄰鏡同理（`cut_in` 是 `match_action`／`insert`／`cont` 時不查）。
  3. 結構化入口：同一角色上段 `exit_state` 是站／坐／倒其中一種、本段 `entry_state` 換成另一種又沒寫動作；或本段入口位置回到上段開頭的位置（回原點）。
- 關鍵詞判斷有誤報（不同角色做同一類事件也會報），看到時用事件帳標清楚，或用 `staging_waivers` 附原話豁免。

例：
```json
{"segment_id": "EP05-S01-c", "narrative_scene_id": "EP05-buffet", "seam_in": "cut",
 "beats_done": ["B01-cook-runs-out", "B02-wall-breaks", "B03-rat-pins-mother"],
 "beats_new": ["B04-shen-hits-rat"],
 "entry_state": {"C-shen": {"position": "two steps right of the mother's table", "holding": "a round steel stool in his right hand"}}}
```

## 5. 佔位延續

既有：`h3d staging` D02（對白越軸）、D08（多人左到右）、D09／D10（段層 positions）、站位附表（`continuity-ledger.md` §4）、牆面分配層（`spatial-consistency.md` §2）、W46 構圖板建議。本節補**逐鏡**的部分。

1. **逐鏡 positions**：多人鏡在 `shots[].positions` 寫每人 `order_lr`（本機位畫面左到右，1＝最左）、`facing`（視線所在邊／看誰）、`background_anchor`、選填 `world`（世界座標）、`screen_x`（0–1）、`move`（本鏡走位）。段內相鄰鏡共同角色左右對調（角度差 >90° 的反打不算）、世界位置改變而沒寫走位 → D20。`facing` 寫畫左／畫右又指名看誰（`frame_left toward C-02` 或另寫 `toward: "C-02"`）時，被看的人要在同一邊，否則 D23。
2. **背景錨點鎖**：站位漂移的元凶常是「人物背後的東西變了」。每人寫身後**最可辨識的一個背景物**（「沈身後是菜檯北端的不鏽鋼湯桶」），不寫「背景不變」這種泛詞；生物也要寫；切鏡後背景物不得無過程跳換。多人鏡缺 → D21（manju-laoli，C；**只建議**，不算警告數：T1 它只是在查欄位有沒有填，命中率 20%）。
3. **動作匹配同主體畫面位置差 ≤15% 畫寬**：A 末幀和 B 首幀主體位置、運動方向、光向、狀態、視線邊五項一致，故意破的是景別或角度（DirectorSKILL「5 同 1 破」，D）。只在 `cut_in.type: "match_action"`、景別差 ≤1 級、兩鏡都有 `screen_x` 時查，差 >0.15 → D20。一般硬切不查：打鬥中角色本來就在移動、景別跳 2 級以上位置必然改變（T1 第一輪 10 條 D20 有 7 條是硬切漂移誤報）。
4. **越軸**：先插**軸上中性鏡**（`camera_optics.axis_side: "on_axis"`）或寫**畫內轉折**（角色走位、攝影機在畫內連續繞過去），再到另一側；不靠切鏡跳軸（180° 規則，A/B；repos 共識）。理由寫進 `cut_in.motivation`／`choice_why`，D20 讀到走位或越軸字眼就不報。
5. **站位靠圖不靠字**：純文字空間描述（地標＋公尺＋180° 軸線）在同 seed 對照下**沒有改變任何左右配置**（phileiny，C）；老易實驗也是換母片才把座位拉對（本 repo，方向性）。空間要在圖上定（場景母片照平面圖畫、母片底構圖板），文字只寫方向（誰在畫左、看向哪邊、往哪走）。
6. **世界座標＋畫面座標雙層**：世界層（誰在房間哪裡）換機位不變；畫面層（誰在畫左）每個機位重算。合法換機位（越軸重建後的反打、對面機位）時畫面左右會互換，**先核世界座標再重算畫面座標**，不要為了「左右不變」去交換人物或鏡像場景（Toonflow §A5，D；`continuity-ledger.md` §3／§5）。相鄰鏡（含同場段縫）方位角差 >90°、共同角色（≥2 人）左右順序卻沒換、也沒寫走位 → D24；方位角差 <90° 時同一人朝向左右對調且沒寫轉身／回頭 → D23。

## 6. 剪輯（階段 7）

| 規則 | 等級／來源 |
|---|---|
| 硬切 ≥85%；疊化、閃白各一集 ≤1 次；正反打不加轉場 | B（iamos.zone S11，`edit/manju-editing-playbook.md` §2） |
| 對白剪點：上一句最後一個音結束後 **≤6 幀**下刀；下一位開口前留約 **8 幀**；差 2 幀以上要重判 | A（Barry Salt 2015，35 部片量測） |
| **L-cut**：台詞延到反應鏡（停在聽者），也用來縮短停頓；J-cut 聲音先到 | A/B（Salt；剪映教學） |
| 頭尾修剪：剪前盲刪頭約 8 幀、尾約 12 幀（首尾幀生成的核准靜幀除外，只檢查不盲刪）；H3 尾巴預留 1.3–1.5 s | D（DirectorSKILL）；C（phileiny） |
| **接點調色**：同一顆 H3 跨切點曝光會跳（YAVG 77→112，+45%），在提示詞寫「曝光一致」無效（76→108），只能剪前逐段套曲線 | C（phileiny §七之二⑨） |
| CONT 段縫剪掉上段最後 1 s 定格；CUT 段縫用上段 0.5 s 餘量吃轉場 | C（manju-laoli） |

`h3d qa --continuity`（`tooling.md` §2.8.1）在影片端量交界；本檔的 lint 只看分鏡欄位。

### 6.1 影片端接點自檢 `h3d seamcheck`（不自動判定）

```
python scripts/h3d.py seamcheck --root <專案> [--segments segments-ep05.json] [--videos-dir videos] [--segment-id EP05-S01-c]
```

- 每個接點一張對照圖（左＝切前、右＝切後）：段縫抽上段最後一格｜本段第一格（有 `lead_in_s` 就抽前導後第一格）；段內切點用和 `qa --continuity` 同一套方法找實際切點，找不到就用規劃秒數並標 `cut_found: false`。
- `videos/qa/seamcheck/seamcheck.json`：每個接點列分鏡寫的預期值（兩側景別、人數、左到右、朝向、背景錨點、`cut_in`／`seam_in`、`exit_state`／`entry_state`、beats、是否同場）與待填 `checks`：`people_count`（人數對不對）、`left_right`（左右）、`background_anchor`（錨點）、`no_repeat`（沒重演）、`shot_size_as_planned`（照分鏡景別），預設全是 `null`。
- 交給人或視覺模型看圖填 `true`／`false`／`"unsure"`，不符時寫 `notes`。**工具不判定、不呼叫任何模型 API**，也不改門禁、不寫 qa-report／verdicts。接點 ID：段縫 `<上段>|<本段>`、段內 `<段>#<前鏡>><後鏡>`。
- 用途：分鏡層 lint 抓不到「計畫沒問題、生成沒照做」（T1 有 5/18 屬這類，例：CU 被渲成中景、主觀鏡沒出現），這部分只能看影片。

## 7. 欄位速查（全部選填、向下相容）

```json
{
  "segment_id": "EP01-S02-b",
  "seam_in": "cont",
  "entry_state": {"C-SHEN": {"position": "east end of the counter", "facing": "frame left toward C-YE",
                             "distance": "an arm's length from C-YE", "momentum": "still", "damage": "torn right cuff",
                             "holding": "chopsticks in right hand", "background_anchor": "steel soup pot"}},
  "exit_state": {"C-SHEN": {"position": "east end of the counter", "...": "…"}},
  "shots": [
    {"shot_id": "EP01-S02-b-SH02",
     "camera_optics": {"shot_size": "MCU", "azimuth_deg": 40},
     "cut_in": {"type": "eyeline", "motivation": "沈抬眼看門口，切到門口的人"},
     "positions": [{"id": "C-SHEN", "order_lr": 1, "facing": "frame_right", "background_anchor": "steel soup pot",
                    "world": "counter east end", "screen_x": 0.3},
                   {"id": "C-YE", "order_lr": 2, "facing": "frame_left", "background_anchor": "kitchen doorway",
                    "world": "doorway", "screen_x": 0.72}]}
  ]
}
```

- `entry_state`／`exit_state`：扁平（`position`、`facing`、`distance`、`momentum`、`damage`、`holding`、`background_anchor`、`light`、`sound`）或 `{角色 id: {同欄位}}`。
- `azimuth_deg`：機位方位角（度）＝**攝影機鏡頭朝向**，俯視順時針量。**0° 的定義**：本場站位附表／`continuity_anchors.axis` 的**主機位**（建立鏡：攝影機在軸線一側、同時看到兩人或主體的那個方向）。其他機位都相對它量：
  - 主機位＝0；鏡頭往右轉 90°＝90、轉到對面（反打，畫面左右互換）＝180、往左轉 90°＝270；過肩鏡通常在主機位 ±30（30 或 330）。
  - 例（自助餐店，攝影機在南牆、鏡頭朝北拍整間店＝主機位 0）：朝東拍大門＝90、朝東北＝45、朝南拍回南牆（反打）＝180、朝西北＝315。
  - 每場重新定 0；同一場所有鏡都用同一個 0。
  - 沒有平面圖、說不準角度時只填**相對值**（同一場內一致就好），或乾脆不填；不填時 D15／D16／D23／D24 只看主體與景別，訊息會寫「角度未知」。
- `character_ids`（主體集合）只放**畫面裡看得到的**角色。畫外發話者（O.S.／V.O.）、看不見的生物（只有聲音或紅光）不放，否則 D15／D16 會把主體集合算錯；要標說話者用 `dialogue_and_audio.speaker`，要指定視覺主體可另寫 `visual_subject_ids`（優先於 `character_ids`）。
- `shot_size`：代碼（`MS`、`MCU`…）最好；英文自由文字（extreme close-up／close-up／medium close-up／medium／medium-wide／wide／extreme wide，含 shot 字樣、連字號、大小寫變體）與中文（大特寫／特寫／中近景／近景／中景／中遠景／遠景／大遠景）lint 也讀得懂；讀不懂時景別比對靜默。
- `narrative_scene_id`：敘事場景 ID。**一段一個場景包**（`scene_id` 是 `S-buffet-fight-a`／`-fight-b` 這種拍攝場景）時一定要寫，否則段縫規則把每一段都當成換場、一條都不跑。同場判斷順序：`narrative_scene_id` → `source_scene_id` → `scene_id`。
- `beats_done`／`beats_new`／`shots[].beats_new`：事件帳（§4.5）。
- `lead_in_s`：拋棄式前導秒數（§4.4，預設不寫＝關）。
- `positions[].toward`：這人看誰（角色 ID），D23 用；也可直接寫在 `facing`（`frame_left toward C-02`）。
- `handoff_to_skeleton.py` 產空欄（`seam_in: null`、`entry_state`／`exit_state: {}`、`cut_in: {type: null}`、`positions: []`）；`layer2_to_table.py` 只在有值時多一欄「接點／站位」與段縫列。
- REMIX：逐鏡 `positions` 跟著 Layer 2 走；段層 `positions`（綁定既有欄位，D09／D10 用）不變。兩個 backend 都在第 1 鏡開頭寫交接塊，REMIX 的風格錨仍在最前（E55）。

## 8. lint 一覽（D21 只建議，其餘預設警告；strict 不升級；可用 `staging_waivers` 豁免，要附使用者原話）

| 碼 | 規則 | 何時跑 | 等級 |
|---|---|---|---|
| D15 | CUT 段縫三選一都證明不了（一側 `character_ids` 空算主體不同） | 下一段 `seam_in: "cut"`，且上一段同場 | D |
| D16 | 同主體相鄰鏡：景別差 <2 級且角度差 <30°（或角度未填）；插入鏡前後、動作匹配切不查；OTS 豁免只在角度沒填時 | 段落已規劃銜接* | A/B |
| D17 | 段內連 3 鏡同景別（A→B→A 正反打除外） | 段落已規劃銜接* | C/D |
| D18 | CONT 段縫：缺 entry／exit、欄位不符、上段末 1 s 有台詞、首鏡景別不同、指代詞 | `seam_in: "cont"` | C/D |
| D19 | 台詞跨切點（L_CUT／J_CUT 或 speech_window 越過鏡頭邊界）兩側都沒有 `<scenetrans>` | 段落已規劃銜接* | B/D |
| D20 | 相鄰鏡共同角色左右對調（反打 >90° 除外）、世界位置改變，且沒寫走位／越軸理由；動作匹配＋景別差 ≤1 級時 `screen_x` 差 >0.15 | 兩鏡都有 `positions` | A/B（≤15% 為 D） |
| D21 | 多人鏡 positions 有人沒寫 `background_anchor`（**建議**，level＝suggestion，不算警告數） | 有逐鏡 `positions`；段層 positions 只在已規劃時 | C |
| D22 | 重演／狀態倒退：事件帳 beat 重複、上段已完成的事件本段又演、入口退回事件之前、回原點 | 段落已規劃銜接*；段縫要上一段同場 | D |
| D23 | 朝向和站位矛盾：「朝畫左看 X」而 X 在畫右；角度差 <90° 時同一人朝向左右對調且沒寫轉身／回頭 | 有逐鏡 `positions`（含 `facing`） | A/B |
| D24 | 反打沒換邊：相鄰鏡（含同場段縫）方位角差 >90°，共同角色（≥2 人）左右順序沒換、沒寫走位 | 兩鏡都有 `positions` 與 `azimuth_deg` | A/B |

\* 「已規劃銜接」＝段落有 `seam_in`／`entry_state`／`exit_state`／`beats_done`／`beats_new`，或任一鏡有 `cut_in.type`／`positions`／`beats_new`。**舊專案沒有這些欄位時 D15–D24 一條都不報**（對《噩盡島》ejindao 38 段、ch02 EP05 r5 18 段、golden EP01 實跑皆 0）。

代號：`director_lint`／`staging_lint` 的 D 系列到 D14、W 系列到 W46，D15–D24 在程式裡未被占用（文件裡的「D19／D32」等是守富裁決編號，不同命名空間）。

## 9. 爭議與待 H3 驗證（需守富同意才跑；不生圖、不送 H3 就不能升級規則）

| 編號 | 問題 | 對照 | 判準 |
|---|---|---|---|
| **E1** | CONT 段縫：獨立生成＋交接塊 vs 上一段**真實尾幀**當參考 | 同一段縫各 3 抽 | 接縫 NCC／人工盲評景別、站位、臉；FreeVideo adapter 是否允許（422 歷史） |
| **E2** | 段內多切：只掛首張參考 vs **每切掛關鍵幀** | zenstory：每切掛 NCC 0.88／0.89／0.95，只掛首張 0.88／0.40／0.33（C） | 各切 NCC、切點落點誤差 |
| **E3** | 正反打**雙人引子** 1.5 s 有無 | phileiny：補引子一次就對（C） | 單人反角是否成立、引子後製可剪 |
| **E4** | 拋棄式前導 `lead_in_s`（§4.4）有無 | 接力棒流程草案（方向性） | 重演是否落在被剪掉的前導裡、段長成本 |

其他沒有定論的：段縫景別同檔還是要換（manju-laoli 尾幀承接要同檔 vs 換機位硬切禁同景別同視角——本檔依 CONT／CUT 分流）；景別「隔級切」vs「相鄰級差 ≤1」（學派之爭，本檔採 30° 規則一側）；眨眼理論（Murch）有 Salt 引用的反證，只當直覺工具。

## 10. 來源

- Dmytryk《On Film Editing》（1984）：https://archive.org/download/edward-dmytryk-1984-on-film-editing/Edward%20Dmytryk%20-%20%5B1984%5D%20-%20On%20Film%20Editing_text.pdf（A）
- Barry Salt 對白剪點量測（2015）：https://ochre.lib.uchicago.edu/ochre?load&uuid=b3c2546c-f0d8-473f-a012-531171718682（A）
- 30° 規則：https://en.wikipedia.org/wiki/30-degree_rule ；《Grammar of the Edit》https://www.oreilly.com/library/view/grammar-of-the/9780240521213/Chapter04g.html（B）；景別跳 2 級 https://www.joelwsmith.com/camera-shot-sizes（B，單一作者）
- 180°／視線接／銀幕方向：https://www.studiobinder.com/blog/what-is-the-180-degree-rule-film ；https://www.studiobinder.com/blog/what-is-an-eyeline-match（B）
- HBAI-Ltd/Toonflow-app（段縫閘門、絕對初始狀態、世界＋畫面座標）：https://github.com/HBAI-Ltd/Toonflow-app（D）
- zenstory-ai/drama-skills（尾幀續接、每切關鍵幀 NCC）：https://github.com/zenstory-ai/drama-skills（C）
- phileiny/h3-storyboard-skill（雙人引子、要切就靜止、跨切點曝光、純文字空間無效、H3 片尾崩解）：https://github.com/phileiny/h3-storyboard-skill（C）
- lixiaoxiao9888-create/manju-laoli-skill（定格承接 vs 0.5 s 接口餘量、背景錨點鎖、末幀可截性）：https://github.com/lixiaoxiao9888-create/manju-laoli-skill（C）
- wuwangzhang1216/DirectorSKILL（5 同 1 破、≤15% 畫寬、頭 8f 尾 12f）：https://github.com/wuwangzhang1216/DirectorSKILL（D）
- waooAI/waoowaoo（時間只往前、入口／出口狀態）：https://github.com/waooAI/waoowaoo（D）
- mini-yifan/open-source-video-gen-skill（H3 `<scenetrans>`）：https://github.com/mini-yifan/open-source-video-gen-skill（D）
- iamos.zone《AI 漫劇製作》剪輯環節（硬切 ≥85%）：https://iamos.zone/comic/workflow/editing（B）
