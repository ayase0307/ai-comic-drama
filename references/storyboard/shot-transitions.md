# 鏡間銜接與佔位延續（單一入口）

> 鏡頭和鏡頭之間怎麼接、段和段之間怎麼縫、人物站位怎麼跨鏡維持，**以本檔為準**。其他文件只留短摘要並指回這裡。
> 研究依據：2026-10-29 外部調研（awesome-short-drama-skills 107 個 repo＋中英文平台與剪輯經典；彙整見本 repo 外的研究筆記，關鍵來源列在 §10）。
> 程式：`scripts/storyboard/transition_lint.py`（D15–D21，全部警告），併入 `h3d staging` 與 `compile --check`；欄位見 §7。

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
| **段內切**（within） | 同一次生成裡的 `[Shot N]` 切點 | 模型照提示詞切 | `shots[].cut_in` | D16、D17、D19、D20 |
| **段縫 CUT** | 兩次獨立生成之間，換機位硬切 | 讓模型**重建**畫面；剪輯直接硬接 | 下一段 `seam_in: "cut"` | D15 |
| **段縫 CONT** | 兩次獨立生成之間，同機位技術分段（長動作、一句長台詞、一鏡到底被拆開） | 剪輯把上段末 1 s 剪掉、下段從交接狀態起手 | 下一段 `seam_in: "cont"`＋`entry_state`，上一段 `exit_state` | D18 |

- 預設：同場段縫走 **CUT**（和既有「段縫換機位或換景別」一致，`continuity-ledger.md` §6）。CONT 只在動作或台詞真的被拆開時用。
- `shots[].cut_in.type`：`hard`（一般切）、`match_action`（動作中切）、`eyeline`（看→看到）、`reaction`（反應鏡）、`insert`（插入鏡）、`scene_change`（換場）、`cont`（同機位延續，段內罕用）。`motivation` 寫這刀帶來的新資訊或理由。第 1 鏡的 `cut_in` 可省略，段縫看 `seam_in`。
- `seam_in` 和既有 `continuity_handshake.mode`（`INDEPENDENT_REF2VA`…）是兩件事：mode 是生成路線，seam_in 是剪輯關係。程式**不從 mode 推 seam_in**（舊專案才不會冒出新警告）。

## 2. 段內切規則

| # | 規則 | 等級／來源 | lint |
|---|---|---|---|
| 2.1 | **切必帶新資訊**（主體、空間、狀態、視角、時間）；只是換距離或微調角度 → 用運鏡，不切 | B（`h3/camera-and-transitions.md` §5）；多 repo 共識（suihe1、zenstory、mini-yifan，D） | — |
| 2.2 | **同主體相鄰鏡：角度 ≥30° 或景別跳 ≥2 級**（跳 1 級要再配角度 ≥30°）。景別級：ELS0／LS1／MLS2／MS·OTS_MS3／MCU4／CU·OTS_CU5／ECU6；OTS 和非 OTS 互切算換角度 | A/B：30° 規則（Wikipedia、《Grammar of the Edit》、Dmytryk 同軸推近需極精準時機）；跳 2 級只有 Joel W. Smith 明寫（B）＋DirectorSKILL（D） | D16 |
| 2.3 | **不連 3 鏡同景別**；正反打主體輪替（A→B→A）不算 | C/D：Shanyin 拉片（同景別連 >4 要警惕）、DirectorSKILL／alchaincyf「不要連兩鏡同景別同角度」 | D17 |
| 2.4 | **時間只往前、不重演**：後一鏡第一格晚於前一鏡最後一格；換景別名稱不能把同一動作再演一次 | D：waoowaoo、Toonflow、xiaxia、djyy 共識 | —（文字判斷，Agent 審） |
| 2.5 | **Match on action**：前鏡收在動作中段，後鏡從同一動作後半開始；只放在**同一段內**，跨段讓前段做完 | A：Dmytryk；D：Toonflow §A7.4 | — |
| 2.6 | **視線接**：看→看到；眼神先定住再切，下一鏡交代被看物 | B：StudioBinder eyeline match；既有 D04 | D04 |
| 2.7 | **正反打先給 1.5 s 雙人引子**（後製剪掉），單人反角才拍得對；那一段要多給 1.5 s | C：phileiny §七之二④（H3，補引子後一次就對）；**本 repo 未驗，見 E3** | — |
| 2.8 | **台詞跨切點**：兩側都寫 `<scenetrans>`＋`continues seamlessly across the cut`，台詞只說一次（L-cut 延到聽者） | B/D：H3 開源格式（`h3/audio-and-dialogue.md`）、mini-yifan base-en.txt；本 repo 未實測 | D19 |
| 2.9 | **要切就整顆靜止，要運鏡就不放切點**（運鏡會把切點內插成連續推近）；例外：兩鏡主體和景別完全不同 | C：phileiny §七之二②（H3 失敗兩次） | —（`h3d staging` D13 只看整段固定） |
| 2.10 | 一段的切點數有預算：10 s 約 2–3 鏡；鏡數超過時長能承載，模型會在動作中亂切 | C：xixihhhh、zenstory；本 repo 定案「7–10 秒、2–4 拍」 | — |

寫法：第 2 鏡起的頭句已由編譯器寫成 `At mm:ss, the shot cuts to a <景別> …`；本檔只決定**切什麼**，句型不變。

## 3. 段縫 CUT：三選一閘門

只比**上段末鏡 vs 本段首鏡**，至少滿足一項：

1. **主體不同**（`character_ids` 集合不同：雙人→單人、人→局部、人→空鏡）；
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

## 5. 佔位延續

既有：`h3d staging` D02（對白越軸）、D08（多人左到右）、D09／D10（段層 positions）、站位附表（`continuity-ledger.md` §4）、牆面分配層（`spatial-consistency.md` §2）、W46 構圖板建議。本節補**逐鏡**的部分。

1. **逐鏡 positions**：多人鏡在 `shots[].positions` 寫每人 `order_lr`（本機位畫面左到右，1＝最左）、`facing`（視線所在邊／看誰）、`background_anchor`、選填 `world`（世界座標）、`screen_x`（0–1）、`move`（本鏡走位）。段內相鄰鏡共同角色左右對調、世界位置改變而沒寫走位 → D20。
2. **背景錨點鎖**：站位漂移的元凶常是「人物背後的東西變了」。每人寫身後**最可辨識的一個背景物**（「沈身後是菜檯北端的不鏽鋼湯桶」），不寫「背景不變」這種泛詞；切鏡後背景物不得無過程跳換。多人鏡缺 → D21（manju-laoli，C）。
3. **硬切同主體畫面位置差 ≤15% 畫寬**：A 末幀和 B 首幀主體位置、運動方向、光向、狀態、視線邊五項一致，故意破的是景別或角度（DirectorSKILL「5 同 1 破」，D）。`cut_in.type` 為 hard／match_action 且兩鏡都有 `screen_x` 時，差 >0.15 → D20。
4. **越軸**：先插**軸上中性鏡**（`camera_optics.axis_side: "on_axis"`）或寫**畫內轉折**（角色走位、攝影機在畫內連續繞過去），再到另一側；不靠切鏡跳軸（180° 規則，A/B；repos 共識）。理由寫進 `cut_in.motivation`／`choice_why`，D20 讀到走位或越軸字眼就不報。
5. **站位靠圖不靠字**：純文字空間描述（地標＋公尺＋180° 軸線）在同 seed 對照下**沒有改變任何左右配置**（phileiny，C）；老易實驗也是換母片才把座位拉對（本 repo，方向性）。空間要在圖上定（場景母片照平面圖畫、母片底構圖板），文字只寫方向（誰在畫左、看向哪邊、往哪走）。
6. **世界座標＋畫面座標雙層**：世界層（誰在房間哪裡）換機位不變；畫面層（誰在畫左）每個機位重算。合法換機位（越軸重建後的反打、對面機位）時畫面左右會互換，**先核世界座標再重算畫面座標**，不要為了「左右不變」去交換人物或鏡像場景（Toonflow §A5，D；`continuity-ledger.md` §3／§5）。

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
- `azimuth_deg`：世界座標的機位方位角（0＝本場主軸正面，順時針）。沒填時 D15／D16 只能看主體與景別，訊息會寫「角度未知」。
- `handoff_to_skeleton.py` 產空欄（`seam_in: null`、`entry_state`／`exit_state: {}`、`cut_in: {type: null}`、`positions: []`）；`layer2_to_table.py` 只在有值時多一欄「接點／站位」與段縫列。
- REMIX：逐鏡 `positions` 跟著 Layer 2 走；段層 `positions`（綁定既有欄位，D09／D10 用）不變。兩個 backend 都在第 1 鏡開頭寫交接塊，REMIX 的風格錨仍在最前（E55）。

## 8. lint 一覽（全部預設警告；strict 不升級；可用 `staging_waivers` 豁免，要附使用者原話）

| 碼 | 規則 | 何時跑 | 等級 |
|---|---|---|---|
| D15 | CUT 段縫三選一都證明不了 | 下一段 `seam_in: "cut"`，且上一段同場 | D |
| D16 | 同主體相鄰鏡：景別差 <2 級且角度差 <30°（或角度未填） | 段落已規劃銜接* | A/B |
| D17 | 段內連 3 鏡同景別（A→B→A 正反打除外） | 段落已規劃銜接* | C/D |
| D18 | CONT 段縫：缺 entry／exit、欄位不符、上段末 1 s 有台詞、首鏡景別不同、指代詞 | `seam_in: "cont"` | C/D |
| D19 | 台詞跨切點（L_CUT／J_CUT 或 speech_window 越過鏡頭邊界）兩側都沒有 `<scenetrans>` | 段落已規劃銜接* | B/D |
| D20 | 相鄰鏡共同角色左右對調、世界位置改變、硬切同主體 `screen_x` 差 >0.15，且沒寫走位／越軸理由 | 兩鏡都有 `positions` | A/B（≤15% 為 D） |
| D21 | 多人鏡 positions 有人沒寫 `background_anchor` | 有逐鏡 `positions`；段層 positions 只在已規劃時 | C |

\* 「已規劃銜接」＝段落有 `seam_in`／`entry_state`／`exit_state`，或任一鏡有 `cut_in.type`／`positions`。**舊專案沒有這些欄位時 D15–D21 一條都不報**（對《噩盡島》ejindao 40 段、ch02 EP05 r5 18 段、老易實驗、golden EP01 實跑皆 0）。

代號：`director_lint`／`staging_lint` 的 D 系列到 D14、W 系列到 W46，D15–D21 在程式裡未被占用（文件裡的「D19／D32」等是守富裁決編號，不同命名空間）。

## 9. 爭議與待 H3 驗證（需守富同意才跑；不生圖、不送 H3 就不能升級規則）

| 編號 | 問題 | 對照 | 判準 |
|---|---|---|---|
| **E1** | CONT 段縫：獨立生成＋交接塊 vs 上一段**真實尾幀**當參考 | 同一段縫各 3 抽 | 接縫 NCC／人工盲評景別、站位、臉；FreeVideo adapter 是否允許（422 歷史） |
| **E2** | 段內多切：只掛首張參考 vs **每切掛關鍵幀** | zenstory：每切掛 NCC 0.88／0.89／0.95，只掛首張 0.88／0.40／0.33（C） | 各切 NCC、切點落點誤差 |
| **E3** | 正反打**雙人引子** 1.5 s 有無 | phileiny：補引子一次就對（C） | 單人反角是否成立、引子後製可剪 |

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
