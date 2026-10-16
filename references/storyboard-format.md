# 分鏡表格式與一致性機制

## 一、欄位定義

| 欄位 | 必填 | 說明 |
|---|---|---|
| `shot_id` | ✅ | `S<集>-<序號>`，例 `S01-003` |
| `scene` | ✅ | 場次代號，對應劇本的 `SC01` |
| `location` | ✅ | `地點-空間-時間`，例 `老宅-客廳-夜` |
| `shot_size` | ✅ | 景別：大遠景／遠景／全景／中景／中近景／特寫／大特寫 |
| `camera` | ✅ | 運鏡：固定／推近／拉遠／橫移／搖／升降／環繞／手持／跟拍 |
| `duration_sec` | ✅ | 建議 2–6 秒 |
| `description` | ✅ | 畫面內容：誰在哪、做什麼、朝哪 |
| `characters` | ✅ | 本鏡出現的角色名陣列（無則空陣列） |
| `dialogue` | | 對白原文（無則空字串） |
| `narration` | | 旁白文字（無則空字串） |
| `sfx` | | 音效提示 |
| `image_prompt` | ✅ | 圖像提示詞（模型無關的主版本，見 `prompt-playbook.md`） |
| `video_prompt` | ✅ | 影片提示詞（只寫運動） |
| `negative_prompt` | | 負面提示詞 |
| `image_model` | | 實際使用的圖像模型（生成前問使用者後填入） |
| `image_params` | | 圖像參數，如 `{ "aspect_ratio": "9:16" }` |
| `video_model` | | 實際使用的影片模型 |
| `video_params` | | 影片參數，如 `{ "seconds": 5, "resolution": "1080P", "enable_audio": false }` |
| `status` | | `pending` / `image_done` / `video_done` / `skipped` |

> `image_prompt` / `video_prompt` 存的是**模型無關的主提示詞**。實際送生成工具前，先問使用者用哪個模型，再依該模型改寫（見 `references/model-profiles.md`），並把模型與參數回寫到 `image_model` / `image_params` / `video_model` / `video_params`。

## 二、JSON Schema

```json
{
  "project": "專案名",
  "episode": 1,
  "title": "第一集標題",
  "aspect_ratio": "9:16",
  "style_lock": "anime screencap, cel shading, clean lineart, flat colors, vibrant",
  "shots": [
    {
      "shot_id": "S01-001",
      "scene": "SC01",
      "location": "老宅-客廳-夜",
      "shot_size": "中景",
      "camera": "緩慢推近",
      "duration_sec": 4,
      "description": "林昭坐在舊沙發上，面前茶几放著一只木盒",
      "characters": ["林昭"],
      "dialogue": "",
      "narration": "二十五歲生日那天，她收到了父親留下的最後一件東西。",
      "sfx": "老鐘滴答",
      "image_prompt": "17-year-old girl, black short hair, scar on left eyebrow, navy stand-collar trench coat, silver ring on right hand, sitting on old sofa, wooden box on tea table, medium shot, dim indoor tungsten light, anime screencap, cel shading, clean lineart, flat colors, vibrant",
      "video_prompt": "鏡頭由中景緩慢推近；她先是靜止不動，兩秒後視線下移到木盒；窗外霓虹光在臉上掃過一次；風衣領口隨呼吸起伏",
      "negative_prompt": "多餘手指, 面部扭曲, 文字水印, 換臉",
      "status": "pending"
    }
  ]
}
```

> `style_lock` 是**全片畫風鎖**：所有 `image_prompt` 都必須以它結尾。改畫風＝改這裡，不要逐鏡改。

## 三、一致性機制（核心）

一致性的唯一保證是**複用固定片段**，不是靠模型記憶。

### 三層鎖

| 層級 | 存放位置 | 作用 |
|---|---|---|
| **畫風鎖** | `storyboard.style_lock` | 全片統一畫風詞，每個圖像提示詞結尾都貼 |
| **角色鎖** | `assets.md` 的「固定描述片段」 | 角色外貌，逐字複用；換裝只換服裝段 |
| **場景鎖** | `assets.md` 的「固定描述片段」 | 場景特徵與色調 |

### 組合規則

```
image_prompt = 角色固定片段(全部在場角色) + 場景固定片段 + 本鏡畫面描述 + 景別 + 光線 + style_lock
```

- **在場角色全部要列**，順序固定（主角在前），避免模型混淆。
- **不修改固定片段的任何一個詞**，包含標點與順序。
- 同一角色跨集出現時，仍用同一份片段。

### 跨鏡連續性檢查

出圖前確認：

- [ ] 同一場次的鏡頭，場景片段完全一致
- [ ] 同一角色的鏡頭，角色片段完全一致
- [ ] 服裝切換有明確的劇本依據（不能莫名換裝）
- [ ] 光線與時間在同場次內一致（除非劇情有時間推進）

## 四、Markdown 表格輸出

人可讀版本由 `scripts/storyboard_to_table.py` 產生：

```bash
python scripts/storyboard_to_table.py storyboard-ep01.json --md storyboard-ep01.md --timeline timeline-ep01.csv
```

產出：
- `storyboard-ep01.md`：分鏡表 + 逐鏡提示詞
- `timeline-ep01.csv`：`shot_id, start, end, duration, video_file, subtitle, narration`

## 五、狀態維護

每完成一個生成步驟就更新對應鏡頭的 `status`，這樣中斷後能準確知道從哪續做：

| status | 含義 |
|---|---|
| `pending` | 尚未生成 |
| `image_done` | 分鏡圖已出，影片未出 |
| `video_done` | 影片片段已出 |
| `skipped` | 使用者明確跳過 |

**不要**把失敗的鏡頭標成 `pending` 後重跑——記下失敗原因再決定是改提示詞重試還是跳過。
