---
name: mccloud-panels
description: Scott McCloud 分鏡轉場 lens（薄版）。用 McCloud 的 6 種格間轉場、closure 與五個選擇（moment、frame、image、word、flow），檢查階段 4 分鏡的轉場分布、景別單調與時間感。觸發語：「用 McCloud 看分鏡」「轉場夠不夠變化」「mccloud review」。只給建議、不擋關，一般問題不自動觸發。
---

# Scott McCloud · 分鏡轉場 lens（薄版）

> 本 lens 由 [女媧 · Skill造人術](https://github.com/alchaincyf/nuwa-skill) 生成（人物路徑的薄版）。
> 創建者：[花叔](https://x.com/AlchainHust)。調研時間：2026-10-21。
> 底稿見 `references/research/`，限制見 `FIDELITY.md`。

## 規則
- 用顧問口吻，不假扮本人，不引用書中原句（沒有取得可核對的原文）。
- **漫畫的「格」對應影片的「shot」，「gutter」對應剪接點**。這個對應是本 lens 的【推論】，不是 McCloud 本人針對 AI 影片的說法。

## 回答工作流
1. 跑 `python scripts/craft/mccloud_review.py --project-dir <P> --episode EP01`。它會讀 `layer2/layer2-*.json`，把相鄰 shot 的轉場分類並統計，輸出 `review/craft/stage-4-mccloud-<ep>.md`。
2. Agent 確認自動分類有沒有誤判，再照下方 4 個模型給建議。

## 核心心智模型

### 1. Closure：觀眾在剪接點補完
- 兩個 shot 之間沒拍出來的東西，由觀眾自己補上。**讓觀眾補得越多，參與感越強；但補不起來，就會看不懂。**
- 應用：H3 每段只有 2 到 3 個 shot，動作中段可以交給剪接點，不必每一步都生成。每段只做一個主要動作的規則，和這一點相容。

### 2. 6 種轉場是節奏的調色盤
| 類型 | 效果（轉述） | 在 AI 漫劇裡的用途【推論】 |
|---|---|---|
| moment-to-moment | 時間放慢、懸念 | 反應、停頓、喜劇的「冷場一拍」 |
| action-to-action | 俐落推進 | 主線動作 |
| subject-to-subject | 同一場景切到另一個主體 | 對話的正反打、角色的反應 |
| scene-to-scene | 跨時空 | 段落轉場，要有聲音或畫面的錨點 |
| aspect-to-aspect | 漫遊於場景的不同面向，營造氛圍與地點感 | 空鏡、環境、情緒的留白，是日漫和國漫味道的來源 |
| non-sequitur | 無邏輯關聯 | 幾乎不用，惡搞時才用 |
- 應用：如果某一種轉場超過 60%，就算單調；全集沒有 aspect-to-aspect，代表缺少情緒的留白。

### 3. 五個選擇與「清晰優先」
- 每一格都在做五個選擇：moment（選哪一刻）、frame（距離與角度）、image（畫什麼）、word（文字）、flow（視線動線）。**先求清晰，再加強度**，強度不能犧牲清晰。
- 應用：同一景別連續 3 個 shot 以上，frame 的選擇就沒有在工作；戲點要放在最清楚的景別。

### 4. Masking：角色簡化、背景寫實
- 角色越 iconic，讀者越容易代入。
- 應用【推論】：系統光球這種極簡角色天生適合 masking；但 H3 寫實厚塗風格的角色無法套用，這條只用在非人類角色。

## 誠實邊界
- **薄版**：沒有原書，6 種轉場清單是二手轉述，原頁本次無法開啟核對。五個選擇只有章節名稱（來自 Wikipedia），沒有內文細節。
- 轉場分類是描述工具，不是規範（Neil Cohn 等人的批評）；比例門檻是本 lens 自訂的。
- 自動分類靠 `character_ids` 和景別推估，會誤判，所以 Agent 必須確認。
