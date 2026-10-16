<div align="center">

<img src="assets/banner.jpg" alt="AI Comic Drama — from story to short drama" width="100%">

# 🎬 AI Comic Drama

**一個 Agent Skill：把小說、故事或劇本，端到端做成角色一致的 AI 漫劇／動態漫／短劇。**

故事 → 分集 → 角色設定 → 劇本 → 分鏡 → 提示詞 → 圖 → 片，全程在 Agent 內完成。

![Claude Skill](https://img.shields.io/badge/Claude-Agent%20Skill-7c3aed?logo=anthropic&logoColor=white)
![MiniMax H3](https://img.shields.io/badge/MiniMax-H3%20ready-f59e0b)
![Python](https://img.shields.io/badge/Python-3.8%2B-3776ab?logo=python&logoColor=white)
![Zero dependency](https://img.shields.io/badge/dependencies-zero-22c55e)
![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)
![PRs welcome](https://img.shields.io/badge/PRs-welcome-ec4899)

[特色](#-特色) · [快速開始](#-快速開始) · [七階段流程](#-七階段流程) · [角色一致性](#-角色一致性靠複用不靠重寫) · [專案結構](#-專案結構) · [文件索引](#-文件索引)

</div>

---

## ✨ 特色

| | |
|---|---|
| 🧩 **零外部依賴** | 不需要自託管平台、MCP、資料庫。寫作與分鏡由 Agent 完成，出圖出片用內建生成能力。 |
| 🎭 **角色一致** | 角色／場景／道具各有一份固定描述片段，每次原樣貼上，不臨場改寫。 |
| 🗂️ **全程落檔** | 每個階段的產物都是檔案，隨時續做、改稿、交接。 |
| 🛑 **生成前先確認** | 工具、參數、提示詞語言與鏡數，確認後才動工；絕不假裝生成。 |
| 🎞️ **MiniMax H3 專章** | 官方三段式骨架、情境庫、失敗診斷表，附完整 10 秒打鬥範例。 |
| 🔧 **小工具** | 一鍵建立專案骨架、分鏡 JSON 轉表格與剪輯時間線。 |

## 🚀 快速開始

把本 repo 放進 Claude 的 skills 目錄即可：

```bash
git clone https://github.com/ayase0307/ai-comic-drama.git ~/.claude/skills/ai-comic-drama
```

然後對 Agent 說：

> 「幫我把這篇小說做成 12 集、每集 90 秒的漫劇，畫風古風國漫，9:16，到分鏡圖。」

Agent 會先一次問完六件事（集數與時長、畫風、比例、語言、旁白或對白、交付深度），再開始動工。

也可單獨使用腳本：

```bash
# 建立專案骨架
python scripts/init_project.py my-drama --title "我的漫劇" --episodes 12

# 分鏡 JSON → Markdown 分鏡表 + 剪輯時間線 CSV
python scripts/storyboard_to_table.py storyboard-ep01.json \
  --md storyboard-ep01.md --timeline timeline-ep01.csv

# 只做欄位校驗
python scripts/storyboard_to_table.py storyboard-ep01.json --check
```

## 🧭 七階段流程

<div align="center">
<img src="assets/pipeline.jpg" alt="Seven-stage pipeline" width="90%">
</div>

| 階段 | 做什麼 | 產出 |
|---|---|---|
| 0 定調 | 鎖定六項設定，必要時提問 | `project.md` |
| 1 內容分析與分集 | 拆主線、找切點、每集鉤子 | 併入 `project.md` |
| 2 角色／場景／道具設定 | 建立資產聖經與固定描述片段 | `assets.md` |
| 3 分集劇本 | 場次、時間、地點、人物、對白／旁白 | `script-ep01.md` |
| 4 分鏡表 | 鏡號、景別、運鏡、時長、畫面、台詞、音效 | `storyboard-ep01.json` + `.md` |
| 5 提示詞包 | 逐鏡圖像提示詞與影片提示詞 | `prompts-ep01.md` |
| 6 生成 | 先問模型與參數 → 角色參考圖 → 分鏡圖 → 影片片段 | `images/`、`videos/` |
| 7 組裝交付 | 旁白稿、字幕、剪輯時間線、交付清單 | `narration-ep01.md`、`timeline-ep01.csv` |

詳細模板與每階段檢查點見 [`references/pipeline.md`](references/pipeline.md)。

## 🧬 角色一致性：靠複用，不靠重寫

<div align="center">
<img src="assets/characters.jpg" alt="Character consistency sheet" width="90%">
<br><sub>角色參考圖：面部特寫 + 正／側／背全身，平光純色背景，作為後續所有鏡頭的圖生圖輸入。</sub>
</div>

1. 先為每個角色出一張乾淨的參考圖，**交給使用者確認長相**。
2. 把確認後的描述固定成片段，寫進 `assets.md`。
3. 每一鏡 = 固定片段 + 本鏡畫面描述，**原樣貼上**，不改寫。
4. 影片優先用圖生視頻：拿確認過的分鏡圖當首幀，提示詞只寫**運動**。

## 🎞️ 先分鏡，後生成

<div align="center">
<img src="assets/storyboard.jpg" alt="Storyboard grid" width="90%">
<br><sub>分鏡表未定稿不出圖；出圖後先確認角色長相，再拿去生成影片。</sub>
</div>

分鏡表欄位與 JSON schema 見 [`references/storyboard-format.md`](references/storyboard-format.md)。逐鏡生成、逐鏡檢查，不要一次丟十幾鏡。

## 📁 專案結構

Skill 本身：

```
ai-comic-drama/
├── SKILL.md                 # 技能入口（Agent 讀這個）
├── references/              # 流程、模型對照、提示詞手冊、H3 專章
└── scripts/
    ├── init_project.py          # 建立專案骨架
    └── storyboard_to_table.py   # 分鏡 JSON → 表格／時間線
```

用本技能產出的專案：

```
<專案名>/
├── project.md              # 定調 + 分集規劃
├── assets.md               # 角色 / 場景 / 道具聖經
├── script-ep01.md          # 分集劇本
├── storyboard-ep01.json    # 分鏡表（機器可讀）
├── storyboard-ep01.md      # 分鏡表（人可讀）
├── prompts-ep01.md         # 逐鏡圖像 / 影片提示詞
├── narration-ep01.md       # 旁白與字幕稿
├── timeline-ep01.csv       # 剪輯時間線
├── images/                 # 角色參考圖、分鏡圖
└── videos/                 # 影片片段
```

## 📚 文件索引

| 文件 | 內容 |
|---|---|
| [`SKILL.md`](SKILL.md) | 核心原則與七階段總覽 |
| [`references/pipeline.md`](references/pipeline.md) | 各階段詳細流程、提問清單、模板 |
| [`references/model-profiles.md`](references/model-profiles.md) | 生成前必問清單、各模型提示詞風格對照 |
| [`references/prompt-playbook.md`](references/prompt-playbook.md) | 景別、運鏡、光線、風格鎖、負面提示詞 |
| [`references/storyboard-format.md`](references/storyboard-format.md) | 分鏡欄位、JSON schema、一致性機制 |
| [`references/freevideo.md`](references/freevideo.md) | 搭配 FreeVideo 出片：連線、規則、階段對應 |
| [`agent.md`](agent.md) / [`memory.md`](memory.md) | 給維護本技能的 Agent：進場規範與跨 agent 交接記憶 |
| [`references/minimax-h3.md`](references/minimax-h3.md) | MiniMax H3 專章入口 |
| [`references/h3/`](references/h3/) | 官方格式、皮膚段骨架、動作節奏、失敗診斷、情境庫（人物／視覺／商業）、運鏡轉場、音訊對白、長片分段、10 秒打鬥範例 |

## 🎥 建議搭配 FreeVideo

**[FreeVideo](https://github.com/FlashML-org/FreeVideo)** 是跑在你自己電腦上的 AI 影片生成工具，內建 MiniMax H3，並提供 Agent 專用接口（含 MCP）。

**它能做什麼**
- 文字生影片，也能帶首幀圖、首尾幀或參考圖（人物、影片、音檔）
- 角色庫：建立角色／場景卡片，跨鏡頭沿用同一張臉
- 多鏡影片：先預覽劇本與鏡數，逐鏡看畫面、選片、重拍，最後自動拼接成片
- 單段最長約 60 秒，更長的自動接續；也能生成圖片、抽影格、問視覺模型畫面內容

**為什麼要搭配它**
- 本技能負責「想清楚」：分集、角色、分鏡、提示詞；FreeVideo 負責「做出來」。接上之後 Agent 能從分鏡一路做到成片，不必你手動搬提示詞、下載、剪接。
- 吃官方 H3 提示詞格式，`prompts-ep01.md` 寫好就能直接送，不用再轉寫。
- 在本機跑，沒有額度與排隊費用，素材不離開你的電腦。
- 角色卡讓「角色一致」從靠貼描述片段，升級成直接沿用角色圖。

連線與用法見 [`references/freevideo.md`](references/freevideo.md)；FreeVideo 沒開時，技能會退回「先問模型再生成」的流程。

## 🔗 搭配的專案

本技能的影片提示詞（MiniMax H3）部分，以 **[ayase0307/h3-video-prompting](https://github.com/ayase0307/h3-video-prompting)**（MIT）為準：動作品質、節奏卡點、光影配色、音訊流程、失敗分診與情境 playbook 都在那邊持續更新。`references/h3/` 是本技能內的整合版，兩邊有出入時以該 repo 為主。

## 📄 授權

[MIT](LICENSE)

## 🤝 貢獻

歡迎 Issue 與 PR：新增情境庫、其他模型的提示詞對照、更多範例都很有價值。

---

<div align="center">
<sub>橫幅與角色設定圖由 Codex（imagegen）生成，流程圖與分鏡圖由 Gemini（Nano Banana 2.1）生成。</sub>
</div>
