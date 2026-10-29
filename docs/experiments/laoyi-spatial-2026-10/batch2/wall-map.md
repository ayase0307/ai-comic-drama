# 牆面分配清單（wall map）：自助餐店 EP90／EP91

Hark 2026-10-28 凌晨。來源：`ch02/ep05/blocking.md` §1 世界層座標＋場景母片 `ejindao/images/S-buffet-restaurant_plate_v1.png`＋已驗收反打 `assets/ls2_reverse_door.png`（南牆的樣子以它為正典）。
**2026-10-28 00:20 更新**：場景母片已換成 v3（`assets/ls1_main_plate.png`＝包 `ejin3_exp_ls_plate`），照本表／blocking 座標重生，南牆以新反打 v3 為準；舊母片 `S-buffet-restaurant_plate_v1.png`（窄長、桌只沿東側一列、無左後角小桌）和本表不一致，已在本批淘汰。本表元素位置不變。
用途：(1) H／I 組每鏡提示詞的「Wall map」句（`h_layer.py` 由本表產生，逐鏡重寫，不寫「同上」）；(2) 第二批盲評表的逐鏡核對欄（`scores_b2_template.csv` 的 `wm_*` 欄，見下方「評分欄」）。
座標：x＝西→東 0–10 m、y＝南→北 0–7 m。本劇本所有機位都在南側用餐區往北拍（blocking.md §2），所以**本劇本沒有 180° 反打鏡**：每一鏡都是 西＝畫左、東＝畫右、北＝背景。

| 元素 | 世界位置（只在這裡） | 數量 | 材質／顏色 | 不可以 | 評分欄 |
|---|---|---|---|---|---|
| 玻璃大門 | **只在東牆**，y 2.0–4.0（偏南），雙開、長鋼條把手 | 1 | 透明玻璃、細鋼框；門外暮色藍街道、矮水泥牆、行道樹、橘色路燈 | 出現在北牆／西牆／南牆；第二扇門 | `wm_door_east` |
| 玻璃店面（窗） | **只在東牆**，整面，與玻璃大門同一面 | 1 面 | 同上 | 任何其他牆出現窗或玻璃；北牆門洞後面出現玻璃 | （併入 `wm_door_east`） |
| 菜檯 | **只在西牆**，y 1.4–6.6，北端在角落桌旁 | 1 條 | 不鏽鋼檯身＋弧形玻璃防噴罩＋暖色保溫燈＋菜盤 | 出現在北牆或東牆；兩條菜檯 | `wm_counter_west` |
| 木隔間牆 | **北牆** x 1.0–6.0 | 1 | 淺木框＋奶油色面板、下半淺木護牆板（不是深木牆） | 變深色木牆／大理石 | `wm_partition_north` |
| 廚房門洞 | **只在北牆偏西**，x 3.0–3.9，在隔間牆上 | 1 | 無門扇、無玻璃的開口，裡面是亮白不鏽鋼廚房 | 門洞變玻璃門；門洞後變街景；第二個門洞；門洞出現在東牆 | `wm_doorway_north` |
| 北牆東段 | 北牆 x 6–10 | — | 素白牆 | 出現門窗 | （併入 `wm_partition_north`） |
| 南牆（前牆） | **南牆**（主機位背後，反打才看得到） | — | 素奶油色牆＋淺木護牆板 | 出現門、窗、菜檯 | `wm_south_plain`（多半 NA） |
| 小方桌＋圓凳 | 地板：角落桌 (1.8,5.9) 夾在菜檯北端與廚房門洞之間、貼隔間牆；T1 (3.8,5.6)｜T2 (5.6,4.6)｜T3 (7.6,3.9)｜T4 (7.9,5.8) 東北角靠玻璃｜T5 (5.4,2.0)｜T6 (3.0,2.6) | **7 張**；每張配圓鋼凳 | 淺灰白細點石面＋細深色鋼邊、單支黑色鋼柱腳；拉絲不鏽鋼圓凳 | 木桌、大理石桌、長桌；角落桌跑到門洞東側 | `wm_tables` |
| 主光 | 天花板（低白天花板）的冷白日光燈管，整間平均 | 多支 | 冷白（武戲：閃爍） | — | `wm_light` |
| 輔光 | **只從東牆玻璃進來**的暖橘路燈光 | 1 方向 | 暖橘 | 從西／北進來的暖光；北牆門洞透出街燈 | （併入 `wm_light`） |
| 地板 | 全室 | — | 奶油色亮面地磚 | — | — |
| 武戲狀態（EP91 S02-b～d） | 中央一張桌側倒（巨鼠起跳處）；靠東牆玻璃門附近一張桌側倒（S02-c 腳跟碰到） | 7 張中 2 張側倒 | 同上 | 側倒桌位置互換 | `wm_tables` |

武戲備註（2026-10-28 00:00 第一批揭盲後修訂）：EP05 故事裡北牆 x 4.0–4.8（廚房門洞**東側**）已有巨鼠破洞、地上有碎盤、兩張桌側倒（店中央一張、玻璃門邊一張）。H／I 武戲每鏡 wall map 都寫進這三項（老大指示）；A／B／F／G 武戲提示詞沒寫，盲評時破洞／碎盤在 A／B／F／G **不計分**、在 H／I 計入 `wm_partition_north`／`wm_tables`。

## 每鏡提示詞寫法（H／I 共用，`h_layer.py`）

每一鏡（`[Shot N]` 內、`Camera:` 之前）重寫一次，不用「同上」：
實際字串在 `h_layer.py`（每鏡 400–550 字元；hosted API 7000 字元上限逼出來的精簡版）：
- **Wall map**（R1＋本表＋R2 本機位位置）：`Wall map: the counter is only on the west wall{本鏡位置}; the one open, glassless kitchen doorway is only in the north partition, west of centre{本鏡位置}; the glass door and all glass are only in the east wall{本鏡位置}; plain south wall; seven pale-stone tables with steel stools{本鏡桌況／武戲：two on their sides (mid-room and by the door), broken plates on the tiles, a ragged hole in the partition east of the doorway}.`
- **本鏡否定一句**：寫本鏡看得到的那面牆（例 S01-c 鏡1：`No glass or street appears in that doorway.`）——每鏡不同（E33 跨段套句會擋同一句）、每鏡只一句（E35）。
- **Directions**（R2＋R3）：機位世界朝向 → 人物世界朝向／自身左右 → 本機位畫面左右；暖光只從東牆玻璃來＝本機位畫面哪側。
- **配對**（camera-view）：第 2 鏡起寫「同一時刻、同一側、不鏡像、不換位」；近景寫「沿上一鏡方向收緊，不是新機位」。
- **武戲 S02-d**：三鏡都寫拋飛方向「north-west, deeper into the room toward frame left, away from the glass door」（第一批 A–C 6 抽全被頂向玻璃門）。

## 評分欄（加進第二批盲評表，逐鏡；1＝對、0＝錯、NA＝本鏡看不到）

| 欄 | 核對 |
|---|---|
| `wm_door_east` | 玻璃門／玻璃只在畫右（東）；別的牆沒有玻璃或門 |
| `wm_counter_west` | 菜檯只在畫左（西），只有一條 |
| `wm_partition_north` | 背景是淺木框奶油面板隔間牆（不是深木牆／大理石），北牆東段素白 |
| `wm_doorway_north` | 廚房門洞只在北牆偏西、只有一個、無門扇無玻璃，後面是廚房（不是街景） |
| `wm_south_plain` | 南牆素面（本劇本多半 NA） |
| `wm_tables` | 桌面材質對（淺石面＋黑單柱腳）；看得到的桌數不超過 7；角落桌在門洞西側；武戲側倒桌位置對 |
| `wm_light` | 暖橘光只從畫右（東）進來 |
| `bg_leak` | （第一批新列）背景被角色／生物包的棚拍底取代＝1（武戲 S02-c 鏡1 重點） |

`set_wall`（第一批欄位）保留；`wm_*` 是它的展開版。換牆＝任一 `wm_*` 為 0。
