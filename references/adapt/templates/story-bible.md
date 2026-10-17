# 故事聖經模板（Story Bible Template）

- **專案 ID**：`{{project_id}}`
- **版本**：`v1.0`

---

## 一、角色聖經與別名消歧表（Character Bible）

> **強制規範**：劇本之 `人物：` 行與對白冒號前，必須 100% 使用下表之 `canonical_name`；`aliases` 僅可出現在角色對白文本內。

| 角色 ID (`character_id`) | 標準劇本名 (`canonical_name`) | 原著別名／稱謂 (`aliases`) | 太陽系層級 (`star`/`planet`/`satellite`) | 年齡段與身份 | 外在渴望 (`Want`) | 內在誤信／創傷 (`Misbelief`) | 核心弧線 (`Arc`) |
| :--- | :--- | :--- | :---: | :--- | :--- | :--- | :--- |
| `lin-che` | 林澈 | 阿澈、林小友、七師兄 | `star` | | | | |

### 角色視覺錨點與聲音指紋卡（Per-Character Detail）

#### 1. `{{canonical_name}}` (`{{character_id}}`)
- **視覺不變錨點（Visual Invariant Anchor）**：`{{臉型、髮型髮色、標誌性特徵、主服裝款式與色調}}`
- **服裝與傷痕狀態機（Costume & Injury States）**：
  - `state_default`：`{{預設服裝狀態}}`
  - `state_damaged`：`{{受損或換裝狀態，標明適用集數}}`
- **台詞語氣指紋（Voice & Diction）**：`{{句長、口頭禪、情緒表達方式、TTS 語速傾向}}`
- **是否僅聲音出場（`voice_only`）**：`false`

---

## 二、關鍵做功道具清單（Working Props Registry）

| 道具 ID (`prop_id`) | 道具名稱 | 視覺外觀錨點 | 戲劇做功功能（資訊／關係／衝突） | 初始持有者／位置 | 狀態變化軌跡 | 是否改編新增 |
| :--- | :--- | :--- | :--- | :--- | :--- | :---: |
| `wet_letter` | 被浸濕的信 | 邊緣水漬暈開、封口裂開、背面有隱藏字跡 | 觸發敲門危機與身份懷疑 | `old_apartment_table` | 桌上 $\to$ 林澈手中翻面 | `否` |

---

## 三、常駐場景資產清單（Bottle Locations Registry）

| 場景 ID (`location_id`) | 標準場景名 | 內/外 (`interior`) | 空間結構與固定地標（供分鏡連戲） | 光照基線 | 空間禁忌（如無窗、單一出口） |
| :--- | :--- | :---: | :--- | :--- | :--- |
| `old_apartment` | 舊公寓客廳 | `內` | 走廊木門（有門縫）、舊木桌、單盞吊燈 | 昏黃走廊燈透入 | |

---

## 四、世界觀硬規則與時間基準（World Rules & Timeline）

1. **核心能力／社會／物理規則**：
   - `rule-01`：`{{規則內容與不可違反之代價}}`
2. **改編新增設定登記（必須標註 `【改編新增】`）**：
   - `addition-01`：`【改編新增】{{新增設定內容與新增理由}}`
3. **主時間線基準（Master Timeline）**：
   - `T-3d`：`{{三日前事件}}`
   - `T0`：`{{第01集正敘起點}}`
