# REMIX 抽卡→審片→修訂 循環（階段 6 實作）

> 何時讀：`video_backend remix`、要用「先全部抽一輪草稿、再逐段修」的方式推進階段 6 時。
> 這一頁只管「提示詞已核准之後」的生成循環；上游接手稽核見 `audit-inherited-project.md`，綁定與編譯見 `tooling.md` §2.3.1c。

---

## 1. 抽卡設定（每次連線都重讀 `/guide`）

功能會改，別憑記憶。連上 REMIX 後先 `GET /guide` 與 `GET /capabilities`，用回傳的 mode 表決定設定，不要沿用上一輪的數字。

- **草稿一律 `mode: pika480`**，並顯式帶 `pika_steps`：**4**＝最快抽卡（單人／空鏡／場景段）；**6**＝鏡頭內有兩個以上角色包時用，4 步常直接掉掉其中一個人，抽十次也一樣。
- `pika_sparse` 在 480 預設 `off`（稀疏會掉身分），不要為了快而開。
- 段長上限 15 秒；`seconds` 用編譯後的 `metadata.effective_duration_sec`，不要用規劃值。
- 送件一定帶 `project`（伺服器會擋）、`shot`＝段 ID、`plan.title_zh`（審片室卡片標題）。
- 一個 `ref` 只代表一次送件；重送同一鏡要新的 `ref`，同一 `shot` 會自動併成版本。

跑一輪的順序：`h3d bind` → `h3d compile`（remix 三欄）→ 逐段送件 → 等收件 → 抽格審片 → 修 prompt → 再一輪。**不要邊抽邊改**：GPU 一次只跑一個工作，排隊時改檔案只會讓後面幾段用到舊提示詞。

---

## 2. 參考包會壓過提示詞（最常見的重抽原因）

REMIX 的參考圖是圖像條件，不是「風格提示」。**包的母片上有什麼，每一鏡都會有**；提示詞寫相反只會被部分拉回。

| 症狀 | 真正原因 | 處理 |
|---|---|---|
| 空鏡／廢墟段出現發光仙宮、夜空、魔法陣 | 場景包母片本身是夜景仙宮圖 | **重建場景包**（乾淨母片，明寫 no buildings / no stars / no moon），不要加「no magic」在提示詞裡硬拗 |
| 角色在課堂上背著大背包 | 角色包的設定圖就背著背包 | 用**無背包設定圖**重建角色包（四格切圖或 8 視角） |
| 提示詞寫「背包放在腳邊」，結果背包跑到背上 | 規則只認「有提到＝出現在畫面」，方位詞沒有約束力 | **整句刪掉**，不要寫「不在背上」這種否定句——否定詞會被當成名詞 |
| 反應鏡突然換到另一個房間／窗外變成湖景 | 單人近景沒有空間錨點，模型自己重建場景 | 改 **MCU**（不要 OTS 過肩），並在 camera 句寫死「in the same hall, vine-wrapped pillars and lattice windows behind her; no other room, no outdoor view」 |
| 站姿／坐姿不符（要求坐書案後卻站著） | 只寫景別，沒寫身體狀態 | performance／motion 第一句就寫 seated／standing；必要時把焦段物距一起改（CU 比 MCU 更不容許模型加桌子） |

**建包順序**：先用生圖工具出乾淨母片（空景或四格設定板）→ `POST /packs`（`kind: scene` 或 `kind: actor`）→ 回讀 `GET /packs/{name}/images` 確認切圖沒切到隔壁的人 → 寫進 `assets/character-packs.json` → `h3d bind`。
場景包只要一張圖（`skip_8view`）；角色包帶設定圖時伺服器自動切四張，切線要自己給（`cuts: [x1,x2,x3]`，像素座標），等寬四欄的版面最穩——只偵測到 1 條線或切到隔壁人物時，改母片版面比手動微調切線划算。

---

## 3. 審片：先跑機器、再看圖、再判政策

每段依序做三件事，任何一項沒過就修，不要只看圖：

1. **技術檢查**：`GET /jobs/{id}/identity` 看角色包命中的 `ok／warn／fail`；`h3d qa` 看時長／彩度／框線。
2. **自己看圖**：每段抽 4 格（0.10／0.30／0.60／0.90 位置）併成一張四格，逐格問「人數對不對、服裝對不對、是不是同一個房間、有沒有燒字」。一次只看一張四格，比逐格看省很多。
3. **套驗收政策**：`h3d verdict <段> pass|warn|fail --reason --evidence`。政策判重跑就修，政策判可接受就直接 pass 並在 reason 寫清楚是哪一條豁免。

### 三個常見假警報（都是「技術 QA 未過、但政策可接受」）

- **`STYLE_BLEED_GRAYSCALE`（低彩度）**：廢墟、雪景、灰調場景常被誤判成黑白線稿。→ 對照 `acceptance_policy.accept` 的 `low_chroma`，pass 並註明。
- **`GRID_PANEL_BORDER_DETECTED`（框線）**：桌面邊緣、門框、地板接縫這種長直線會被當成九宮格殘留。→ 先抽一幀確認是不是真的拼接線；是實物就把鏡頭改 CU／換角度避開，**不要為了一個誤判去重抽同一構圖**。
- **`COLOR_CONTINUITY_WARNING`（相鄰段 dE76 過大）**：灰調空鏡接暖色室內本來就會跳。→ 屬 `color_jump` 可接受；真要修是在剪輯端加過渡，不是重抽。

動態 QA（`h3d motion`）會列出每段最長定住秒數與變速提案，那是**階段 7 的輸入**，不是階段 6 的重抽理由。

它需要 numpy＋opencv；Hermes 內建 venv 沒有 pip，要裝進**同一個直譯器**（裝到別的 python 沒用）：
`uv pip install --python "$(python -c 'import sys;print(sys.executable)')" numpy opencv-python-headless`。

---

## 4. 修一輪只改必要欄位，然後一次重簽

- 一次把**同一類問題的所有段**改完（例如「所有 mention 背包的句子」），再 rebuild → bind → compile → 重簽階段 4／5。每改一句就重簽一次，會浪費掉整輪審核時間。
- 改完 layer2 一定要 **重新 bind＋compile**，否則還原的 `segments` 與 `layer2` 指紋不符，階段 5 會擋「提示詞落後於分鏡」。
- 用建置腳本重建 layer2 會**清掉 `sketch_file／sketch_sha256／sketch_generation`**：重建前把這四個欄位用 shot_id 做快照，重建後寫回；若插入新鏡導致 shot_id 位移（例如前面插雙人引子），要用檔名對應重新綁，不要靠舊 key 直接覆蓋。
- 同一個鏡頭最多重抽 2 次就回層診斷（`references/revision-and-retry.md`）：兩次都同一種錯＝是包或分鏡的問題，不是 seed 的問題。
- **建置腳本之間不要互相 import**：`import build_layer2_s01` 會執行對方模組最上層的寫檔，把你已修好的段重新產生一次，後處理（運鏡動詞正規化、提示詞壓縮）全部被還原，接著 `bind` 就會報 `Stage5 source SHA256 mismatch`。共用 helper 抽成獨立模組；若已經 import，任何一次建置後都要補跑後處理 → `h3d bind` → `h3d compile`，不要只看自己那幾段有沒有變。
- **編譯擋「正規化警告」時，三種時間軸錯先自己修**（錯誤訊息只給一行，細節被吞掉；要看見就跑 `normalize_layer2()`，或對單一檔案加 `--allow-normalize-warnings` 編譯一次）：
  1. `時間軸空隙：預期 A 實際 B`：上一鏡的 `end_time` 必須等於下一鏡的 `start_time`，中間不能留空也不能重疊。
  2. `分段時間軸總長 X 與 target_duration_sec Y 不一致`：宣告秒數要等於鏡頭加總，改其中一邊，不要用 `--allow-normalize-warnings` 混過去（下游 frames 會對不上）。
  3. 台詞窗超出所屬鏡頭範圍：`speech_window` 是**絕對時間**、必須落在該鏡的 `start_time`／`end_time` 內；新段最容易直接寫成鏡內相對秒數。

---

## 5. 收件與交付

收件後把通過的版本複製到 `videos/<段 ID>.mp4`（`h3d qa`、`h3d motion`、`h3d assemble` 都從這裡讀），再跑 `h3d qa` → `h3d motion` → `h3d qa --continuity` → `h3d verdict` → `h3d inbox`。
技術 QA 只到 PARTIAL（低彩度、色調跳躍這種量化項目）時，核准要帶使用者的覆寫理由：`--approve-stage 6 --override --reason "<使用者原話>"`；不要替使用者寫理由。

### 5.1 定稿：`pika768` 同 seed 重跑

草稿過關後再定稿；抽卡版本不要超分。做法是**複製已核准 job 的參數**重送，不要自己重打提示詞：

1. `GET /jobs/<已核准 job>` 取 `params.prompt／refmods／seconds／aspect／seed`。
2. 重送 `/jobs`，只改 `mode: pika768`、`pika_steps: 6`、新 `ref`、`label: <段>-final`、同一個 `shot`（同 shot 自動併成版本，審片室看得出草稿→定稿）。
3. 回讀 `GET /jobs/<新 id>` 的 `result.video.meta`，確認 `width/height` 與 `duration` **與草稿完全一致**（同 seed 同秒數下應逐幀對齊；不一致＝參數沒帶到）。
4. 定稿成品放 `videos/final-768/<段>.mp4`，不要直接蓋掉 `videos/<段>.mp4`（見 SKILL.md 規則 12）。

時間：768 約為 480 的 3–4 倍（10–14 秒段約 5–7 分鐘），一次排滿五段要留 25–35 分鐘，不要在中途改 prompt。

### 5.2 身份比對的兩個假警報

- **邊緣小臉被判定 fail**：`/identity` 對 16:9 畫面右緣被裁掉一半的背景人物也會建 face，box 只有 50×60 px 那種命中率極低。看到 fail 先抽那一格的原始時間點親眼看，確認不是主角換臉再決定重抽。
- **同一角色有多個包時分數互相競爭**：有背包版、課堂版、切壞的版本同時存在時，`best` 會在幾個包之間來回跳，warn 數量會暴增但畫面沒問題。切壞且沒在用的包直接刪；仍在用的用 `variant_of` 表達關係，不要留三份並列。

---

## 6. 審片室的分鏡表要跟著換，不然「預計 N 鏡」永遠是舊的

介面上的「預計 N 鏡」、章節與事件分組讀的是專案的分鏡表 doc，不是 `segments-*.json`。

- 讀 `GET /projects/{id}/storyboard`；整份覆寫 `PUT /projects/{id}/storyboard {"doc":{"chapters":[…]}}`；
  只改單鏡標題／秒數用 `PATCH /projects/{id}/storyboard/shots/{shot}`。
- 結構固定 `chapters → events → shots`，shot 物件是 `{shot, title_zh, seconds}`；同專案 shot 不可重複。
  event ＝ 場景分組，標題寫「第 N 場：地點」，介面才讀得懂。
- 重做分鏡後段數變少時，舊 shot 多半只是存在 doc 裡、**沒有工作掛著**：先 `GET /jobs?project=<id>` 逐鏡對一次，
  確認舊代號沒有任何 job 再整份覆寫；有 job 的先處理那幾支，不要直接刪規劃。
- 覆寫後用 `GET /review?project=<id>` 回讀，把各 event 的 shots 數加總，要等於現有段數（例：5＋13＝18）。
- 規劃歸規劃、資產歸資產：包清單裡「沒被目前綁定引用」的包不代表過期——後面的集數／場景會用到。
  只有**壞掉、切歪、或同一個狀態重複**的包才刪；跨專案的包（別的 project id）一律不動。


