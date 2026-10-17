# Novel-to-Manju 自動化測試套件與 A/B 基準實驗說明

本測試目錄涵蓋【11｜MVP、測試與實測決策】規定的 **10 大邊界測試案例（Boundary Test Cases）** 以及 **原始滿血版提示詞 vs. Novel-to-Manju Skill 的 A/B 對照實驗**。

---

## 一、10 大邊界測試案例清單（`fixtures/` & `expected/`）

| 測試編號 | 測試場景名稱 | 驗證目標 | 對應測試的驗證腳本與閘門 |
| :--- | :--- | :--- | :--- |
| **`case01_high_density_low_event`** | 高資訊密度但事件少的小說片段 | 確認能將大段背景與心理描寫壓縮為道具外化，而不亂加無關狗血劇情。 | `validate_structure.py`, `compare_adaptation.py` |
| **`case02_main_plot_vs_subplots`** | 重要事件與大量支線交錯 | 確認 `MUST_KEEP` 核心因果 100% 保留，冗餘支線合規記錄於 `MERGE`/`REMOVE`。 | `compare_adaptation.py` (`FATAL_CAUSAL_BREAK`, `UNTRACKED_MAJOR_CHANGE`) |
| **`case03_cross_chapter_foreshadow`** | 跨章伏筆後續揭露 | 確認改編在早期場次保留視覺線索，但絕不提前在對白／旁白洩露最終真相。 | `compare_adaptation.py` (`PREMATURE_FORESHADOW_SPOILER`) |
| **`case04_character_aliases`** | 多角色同名或別名 | 確認原著中多種稱謂（林澈／阿澈／七師兄）在劇本發言人欄統一收斂為 `canonical_name`。 | `check_continuity.py` (`ALIAS_USED_AS_SPEAKER`) |
| **`case05_emotional_no_combat`** | 無戰鬥的慢熱情緒戲 | 確認在溫情／傷感戲中不會強迫植入「扇耳光、下跪求饒、80字一爽點」，且閃回時間線明確標記。 | `compare_adaptation.py` (`GENRE_MISMATCH_FORCED_CLICHE`), `validate_structure.py` |
| **`case06_intense_combat`** | 激烈武俠／玄幻戰鬥 | 確認戰鬥具備明確目標、戰術變化與代價，並提供 AI 低碰撞可製作性簡化方案。 | `validate_structure.py`, `check_continuity.py` |
| **`case07_aspect_ratio_9x16_vs_16x9`** | `9:16` 與 `16:9` 相同情節雙版本 | 確認底層故事因果不變，但 `9:16` 與 `16:9` 的構圖重心與分鏡交接要求隨畫幅動態調整。 | `validate_structure.py`, `compare_adaptation.py` |
| **`case08_incomplete_source`** | 來源資料不完整（殘稿） | 確認能主動在 `source_gaps_or_contradictions` 標明原著缺口，嚴禁擅自捏造後續結局。 | `compare_adaptation.py` (`UNREPORTED_SOURCE_GAP`) |
| **`case09_multi_episode_continuity`** | 長篇多集跨集連戲 | 驗證跨集世界規則、角色傷勢、道具位置（`wet_letter`）與記帳式因果（`debt_ledger`）連貫。 | `check_continuity.py` (`CONTINUITY_STATE_MISMATCH`) |
| **`case10_contradictory_source`** | 刻意矛盾原文 | 確認當原著前後設定矛盾時，主動列出矛盾清單與修復方案，而非悄悄掩蓋或照抄矛盾。 | `compare_adaptation.py` (`UNREPORTED_SOURCE_CONTRADICTION`) |

---

## 二、執行測試指令

```bash
python scripts/adapt/tests/run_all_tests.py
```

執行後將自動驗證全部 10 組正向案例（預期全部 `PASS` 且得分 `≥ 90`）與負向／舊版對照案例（預期準確攔截並觸發對應 Gatekeeper），並將詳細測試報表輸出至 `scripts/adapt/tests/expected/ab_test_results.json`。
