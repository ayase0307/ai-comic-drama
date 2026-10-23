# 免生圖 SVG 構圖分鏡總覽圖（階段 4 構圖來源）

`scripts/storyboard/svg_storyboard_grid.py` 讀 Layer 2，用 2.5D 針孔相機＋3D 骨架人偶算出每鏡構圖，輸出逐鏡 PNG 與每段分鏡總覽圖，**不呼叫任何生圖 API**。它和 Qwen 分鏡總覽圖、手繪一樣只是階段 4 的構圖來源：圖會回寫到 Layer 2，走同一個 stage-4 審核頁與 hash 門禁。

構圖圖只拿來審走位、景別、180 度線，**不送 H3**（不放進 `reference_images`）。

## 什麼時候用

| 情境 | 建議 |
|---|---|
| 想省圖片額度、先審走位 | ✅ 先跑 SVG 構圖，過了再決定要不要用 Qwen 精修個別鏡頭 |
| 動作、站位、過肩、正反打多 | ✅ 幾何算出來的左右與 180 度線最穩 |
| 要看光影、表情、服裝細節 | ❌ 用 Qwen 分鏡總覽圖或手繪 |
| 3 人以上＋巨獸、特效大場面 | ⚠️ 能出站位，但人偶與道具很簡化 |

## 安裝（選用依賴）

```bash
pip install numpy resvg-py Pillow
python scripts/check_environment.py   # 「免生圖 SVG 構圖分鏡總覽圖（選用）」顯示 ready 即可
```

中文標籤字型會自動找 Windows 的微軟正黑／雅黑、Linux 的 Noto Sans CJK、macOS 的蘋方；都沒有時用環境變數 `SVG_GRID_FONT=<字型檔>` 指定。

## 用法

```bash
# 整集
python scripts/h3d.py sketch --root <專案> --episode EP04
# 指定場或段
python scripts/storyboard/svg_storyboard_grid.py --root <專案> --segment EP04-S04 EP04-S05-a
# 先看會產生哪些檔
python scripts/storyboard/svg_storyboard_grid.py --root <專案> --episode EP04 --dry-run
```

產出與回寫：

| 產出 | 位置 | Layer 2 欄位 |
|---|---|---|
| 逐鏡構圖 | `panels/panel-NN-<shot_id>.png` | `sketch_file`、`sketch_sha256`、`sketch_status: generated` |
| 每段分鏡總覽圖 | `images/grid-<segment_id>.png` | `sketch_generation.grid_file`、`grid_preview_file`、`storyboard_panels` |
| 來源標記 | — | `sketch_generation.backend: svg-rig`、`api_calls: 0` |

`sketch_status` 為 `locked`／`approved`／`manual` 的鏡頭不會被覆蓋（例如手繪替換過的格子），要重畫加 `--force`。重畫後 hash 改變，stage-4 核准會自動失效、需重審。

接著照原流程：

```bash
python scripts/build_stage_review.py --project-dir <專案> --stage 4
# 使用者看過後
python scripts/build_stage_review.py --project-dir <專案> --approve-stage 4 --user-note "走位 OK"
```

## 零設定時它怎麼搭景

只要有 Layer 2 就能跑。程式依序讀：

1. **站位與相機側**：`style_lock.continuity_anchors.axis` 裡「名字（畫左／畫右）」決定誰在哪側；整組站位依相機側旋轉，所以畫左／畫右不會反。
2. **姿勢**：名字後面的「站／坐／跪」；有人站著時桌高 0.75m，否則 0.32m。
3. **場景物件**：`blocking_desc` 關鍵字長出窗、門、床、書架、桌、燈、碗／杯、書／紙，戶外詞（石階、庭院、街…）改用戶外場。
4. **取景**：依 `shot_size`（ECU／CU／MCU／MS／WS／OTS_*）反推物距；OTS 相機貼前景肩後、前景頭不遮主體臉；「畫左三分之一前景」決定前景在哪側。
5. **角色名字**：先找 Layer 2 上層的 `assets*.md` 對照表（`| \`C-id\` | 名字 |`），找不到再從單人鏡描述開頭推。
6. **外觀**：沒登記的角色用預設人偶，衣服顏色依 id 固定，跨鏡一致。

## 進階設定（都可省略）

放在 `<專案>/staging/`（或用 `--staging` 指定）。

### 角色外觀 `staging/cast.json`

```json
{
  "characters": {
    "C-lin": {
      "name": "林小雨", "robe": "#9fb0c2", "robe_dk": "#7a8a9b", "hair": "#2b2b2b",
      "bun": "high", "robe_len": "knee", "scale": 0.95,
      "marks": [{"side": "r", "finger": "middle", "color": "#7a1f1f"}]
    }
  }
}
```

可用欄位：`name`、`robe`、`robe_dk`、`trousers`、`skin`、`hair`、`bun`（low／high／half／cloth）、`strands`、`sash`、`scale`、`brow_w`、`under_eye`、`marks`。

### 場景與站位 `staging/<場景>.json`

`scene_id` 對到 Layer 2 的 `asset_refs.scene_id`：

```json
{
  "scene_id": "S-cafe",
  "room": {
    "x0": -2, "x1": 2, "z0": -3, "z1": 2, "h": 2.8,
    "door": {"wall": "left", "z": [-0.5, 0.5], "h": 2.0},
    "features": ["window"],
    "wall_fill": "#c9bfae", "wall_side_fill": "#b8ad9a", "floor_fill": "#a89274"
  },
  "auto_anchor": {"pos": [0, 0, 0], "axis_side": [0, 0, -1]},
  "stagings": {
    "EP01-S02": {
      "axis_side": [0, 0, -1],
      "actors": [
        {"id": "C-lin",  "pos": [-0.5, 0, 0], "facing": 90,  "pose": "kneel"},
        {"id": "C-zhou", "pos": [0.5, 0, 0],  "facing": -90, "pose": "kneel"}
      ],
      "props": [{"type": "table", "pos": [0, 0, 0], "h": 0.75, "w": 1.0, "d": 0.6}]
    }
  }
}
```

| 欄位 | 說明 |
|---|---|
| 座標 | 公尺，y 朝上 |
| `facing` | 度數：0＝+z、90＝+x、180＝−z |
| `axis_side` | 相機所在側的單位向量 |
| staging 鍵優先序 | 單鏡 id ＞ 段（`EP01-S02-a`）＞ 場（`EP01-S02`）＞ `auto_anchor` 自動站位 |
| `pose` | stand／kneel／walk_down／walk_up |
| 道具 `type` | table／book／bowl／lamp／brush |

### 動作與關鍵字 `scripts/storyboard/svg_rig_actions.json`

`actions`（關鍵字→手臂與頭部姿勢）、`props`、`room_features`、`poses` 都在這個檔。新專案有特殊動詞就加字，不用改程式；也可以用 `--rules` 指向專案自己的一份。

## 檢查與除錯

- 跑完印「⚠ 方向」：Layer 2 寫「面向／朝／看向畫左右」，但算出來的構圖相反。通常是 staging 的 `facing` 或 `axis_side` 寫反；也可能是 Layer 2 本身前後矛盾。
- `RIG_DEBUG=1`：印出 OTS 機位搜尋表。
- 驗收方式：拿成片中段影格和構圖並排比（README 的對照圖就是這樣做的），不要只看構圖本身漂不漂亮。

## 已知限制

- 臉是簡筆、服裝只有長袍一型；現代椅子坐姿目前畫成跪坐。
- 門下縫這類低角度空鏡看不太出門。
- 俯拍手部特寫時，頭有時會擋到手。
- 道具幾何（桌、碗、書）仍在程式內，尺寸可由 staging 覆寫。
