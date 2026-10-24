# 證據分級、開源授權義務與原著版權規範（Evidence & Licenses）

- **責任領域**：研究與改編過程中的證據等級標記、第三方開源技能授權合規清單、原著小說版權與隱私保護。
- **來源依據**：SPDX License List、`agentskills/agentskills`。

---

## 一、研究與審查證據四級確定性標記

在產出診斷報告、改編分析與審查意見時，必須區分事實與推測，強制使用以下四種確定性標記：

1. **`【已確認】`（Confirmed）**：
   - 有原始小說章節段落、劇本具體行號、官方文檔、可執行程式碼輸出或 GitHub 原始碼直接佐證的一手事實。
2. **`【推論】`（Inferred）**：
   - 基於原著上下文線索或編劇理論推導出的合理結論（例如：從角色前後行為推論其隱藏動機），需附推導依據。
3. **`【實作假設】`（Implementation Assumption）**：
   - 工程實作中採用的可配置預設參數（例如：預設常規語速區間為 `3.2–4.0` 字/秒、短劇短集模式的單集目標時長 `90` 秒；長篇漫劇預設沒有單集秒數，事件模式每個交代要素 `8–15` 秒），允許使用者依實際配音員或平台覆寫。
4. **`【待驗證】`（To Be Verified）**：
   - 缺乏公開實測數據支持、或依賴未來特定影片生成模型實機渲染才能確認的效果（例如：某特定新模型對 15 秒一鏡到底多人打鬥的穩定度），嚴禁冒充已證實的科學常數。

---

## 二、第三方高星開源專案方法借鑑與授權義務清單

本 `novel-to-manju` 技能之所有 Markdown 文檔、模板、JSON Schema 與 Python 驗證腳本均為**原創實作（Original Implementation）**，未直接複製粘贴任何第三方倉庫之受保護長段文本或原始碼。

對於在架構設計階段參考借鑑之開源專案，特此保留完整來源追溯與 SPDX 授權聲明：

| 來源倉庫 (Repository) | 查核日 Stars | SPDX License | 借鑑之方法論與設計概念 | 實作方式與合規狀態 |
| :--- | :---: | :---: | :--- | :--- |
| [`eternityspring/shuohao-skills`](https://github.com/eternityspring/shuohao-skills) | 4,684 | Apache-2.0 | 「劇本管戲、分鏡管拍」層級解耦、確定性品質門（時長偏差 ±15%、單句字數上限、前3拍鉤子認領）。 | 以 Python 標準庫獨立重寫 `validate_structure.py` 與 `estimate_duration.py`；保留來源致謝。 |
| [`zenstory-ai/drama-skills`](https://github.com/zenstory-ai/drama-skills) | 2,982 | MIT | 原著逐章戲劇功能提取流程、創作者停靠點（Checkpoints）、帶證據審查（Evidence-based Review）。 | 原創設計 10 階段工作流、A/B/C 方案停靠點與 `compare_adaptation.py`。 |
| [`jtydhr88/screenwriting-skills`](https://github.com/jtydhr88/screenwriting-skills) | 1,687 | MIT | 中文場號制規範、折算頁原理、記帳式因果（Debt Ledger）、麥基場景極性翻轉與梅峰價值檢驗。 | 整合於 `references/` 理論指南與 `check_continuity.py` 債務對帳邏輯。 |
| [`Shanyin-ai/shanyin-screenwriting-master`](https://github.com/Shanyin-ai/shanyin-screenwriting-master) | 1,339 | MIT | 微短片多時長顆粒度分級、不寫攝影機術語的「視覺動態暗示」寫法。 | 整合於 `screenplay-format.md` 與 `visual-writing.md`。 |
| [`google-deepmind/dramatron`](https://github.com/google-deepmind/dramatron) | 1,132 | Apache-2.0 | 層級式故事生成鏈（Logline → Bible → Outline → Scene）與人機協同防套路原則。 | 體現於 Phase 1 至 Phase 6 的嚴格遞進契約。 |
| [`obra/superpowers`](https://github.com/obra/superpowers) | 300,881 | MIT | 過程文檔 TDD 思想、「完成前必備即時驗證證據（Verification Before Completion）」鐵律。 | 落實為 `tests/` 下 10 個邊界測試集與自動化 CLI 驗收。 |
| [`anthropics/skills`](https://github.com/anthropics/skills) | 181,655 | Apache-2.0 | 漸進式揭露（Progressive Disclosure）與模組化按需載入架構。 | 落實為精簡 `SKILL.md` + 10 個獨立 `references/`。 |
| [`agentskills/agentskills`](https://github.com/agentskills/agentskills) | 26,221 | Apache-2.0 | Agent Skills YAML Frontmatter 標準與目錄結構規範。 | 100% 符合 `agentskills.io/specification`。 |

---

## 三、原著小說版權、授權與隱私保護規範（Phase 0 Mandate）

1. **授權狀態記錄**：在 `source-analysis.md` 與 `handoff.json` 中必須記錄 `rights_status`（`owned_original` 自有原創｜`licensed_adaptation` 已獲改編授權｜`public_domain` 公有領域｜`personal_study_only` 僅供個人學習研究｜`unconfirmed` 待確認）。
2. **待確認警示**：若使用者未說明商用授權狀態而要求公開發布或商業投放，必須標註 `【授權待確認】` 並提醒取得原著改編權。
3. **私人稿件保密**：使用者輸入之未公開小說原稿僅在當前專案目錄內進行結構分析與改編，嚴禁將私人原著全文上傳至外部公開倉庫或寫入通用技能示例庫。
