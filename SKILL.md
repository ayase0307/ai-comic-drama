---
name: ai-comic-drama
description: 協助製作 AI 漫劇／動態漫／短劇，從小說改編、劇本與分鏡到提示詞和可選媒體生成。內建確定性驗收（時長量子、證據分級、segment 級依賴帳本、失敗目錄）與單一入口 h3d；圖片或影片生成取決於目前 Agent 工具及已連線的相容後端，本技能不假設 Agent 內建影片生成能力，也可只交付文字劇本、分鏡或提示詞 draft。
agent_created: true
---

# AI 漫劇製作（純 Agent 版）

## 開工規則（每次都照做，沒有例外）

1. **先跑 `python scripts/h3d.py next --root <專案>`**，照它印的「唯一一條指令」做，並先讀它指定的 reference。不要自己排流程或跳步。
2. **使用者定案一律 `h3d decide <id> <值> --quote "<使用者原話>"`** 寫進 `decisions.json`（畫風、比例、台詞政策、設定圖引擎、驗收政策、剪輯方式…）。不要只寫在筆記裡，也不要替使用者決定。
3. **不准手改 `review/project-state.json`。** 狀態只能由 `build_stage_review.py` 寫；手改會被 `h3d next` 判為阻斷。階段 6 技術 QA 為 PARTIAL、使用者看過仍核准時，用 `--approve-stage 6 --override --reason "<使用者理由>"`。
4. **階段 6 逐段結論一律 `h3d verdict`** 寫進 `review/verdicts.json`（pass／warn／fail＋一句原因＋證據圖），依 `acceptance_policy` 分類。
4a. **要使用者決定的事用 `h3d inbox` 產生決策收件匣交給使用者**（只列例外）；使用者授權過的階段照 `h3d next` 跑 `h3d approve --auto`。階段 0、角色設定圖、每個角色的音色永遠要人決定（見 `references/tooling.md` §2.6）。
5. **不同時跑兩個影片 runner**；ledger 有 waiting／running 的工作時只收件（`h3d collect`），不送新件。
6. **遇到 `PARTIAL`、`duration_drift` 就停下**，照 `references/tooling.md` §4 處置並回報使用者，不要自行繞過。
7. **成片形式預設＝長篇漫劇**：把故事講清楚是第一優先，每個原著關鍵事件都要交代起因→經過→結果（含動機、時地轉換），
   不以每集秒數壓縮事件；預設不分集，整部一支連續長片。短劇／竪屏爆款短集（1–2 分鐘、強鉤子）只有使用者明確要求才用
   （`h3d decide series_format short`）。被壓縮、跳過或交代不全的事件一律在階段 1 交使用者決定（`event_coverage.py`），不自己砍。

## Overview

依使用者指定的交付範圍，完成小說改編、劇本、導演分鏡、提示詞，或使用實際可用的圖片／影片工具生成媒體。
文字規劃可獨立交付；媒體生成需要相應工具或已連線的後端（FreeVideo 是可選 adapter，不代表每個 Agent 都內建影片生成）。
**沒有實際呼叫生成工具，就不得聲稱已產出圖片或影片。** 小說不得直接當劇本用，一律先走階段 1 改編。

這一頁是**操作首頁**：每階段做什麼、不准做什麼、跑哪個指令。原理、模板、實戰定案與完整工具清單在
`references/skill-guide.md`（原 SKILL.md 全文，章節不變），由 `h3d next` 指到該讀的那一份。

## 何時使用

- 「把這篇小說／故事做成漫劇、動態漫、短劇」「把小說改編成漫劇劇本」
- 「寫分鏡／鏡頭表／影片提示詞」「設計角色設定／角色聖經」「把商品素材做成帶貨短片」

## 每階段操作首頁

| 階段 | 做什麼 | 不准做什麼 | 跑哪個指令 | 先讀 |
|---|---|---|---|---|
| 0 定調 | 一次問完定調題（題材、載體、畫風、比例、台詞政策），每題附推薦值；**成片形式預設長篇漫劇**（不問集數秒數；使用者主動要短劇才 `h3d decide series_format short`）；**畫風預設推 14 號「古風寫實厚塗・電影感」**（附樣圖，可改選） | 不替使用者決定；不跳過體量反推；不預設切短集 | `init_project.py`、`h3d decide style/aspect_ratio/dialogue_policy` | `references/pipeline.md`、`references/styles.md` |
| 1 改編 | 保留分級、**事件交代完整性**（每個事件起因→經過→結果，壓縮／跳過清單交使用者決定）、依事件估總長、A/B/C 方案、段落架構（使用者要求才分集）、因果債務 | 小說直接當劇本；為秒數壓縮事件；自行砍事件交代 | `event_coverage.py`、`estimate_duration.py --events`、`h3d next` | `references/adapt/novel-to-manju.md`、`references/adapt/structure-and-pacing.md` §零 |
| 2 設定圖 | 主角優先出圖、自檢後重生；引擎定案後全集鎖定 | 換生圖引擎不並排比對；自動核准（永遠要人看臉和服裝） | `h3d decide design_engine`、審核頁 | `references/consistency.md`、`references/styles.md` |
| 3 劇本 | 場景化改寫、台詞預算（4 字/秒、說話 ≤ 60%）、改編差異 | 超預算照送 | `estimate_duration.py --h3`、`sync_script.py` | `references/adapt/screenplay-format.md` |
| 4 分鏡 | **每鏡先寫 `shot_intent`（觀眾要看懂什麼）再定技術值，每項選擇在 `choice_why` 寫理由**；運鏡依 beat 情緒查 `references/camera-moves-guide.md` 選 `move_preset`（選用理由寫進分鏡表，編譯器展開、`move_lint` 警告）；每段附人物賬、台詞鏡寫視線、段縫寫末態並換機位（`continuity-ledger.md`）；Ref2VA 預設一鏡一張可辨識臉（單人裁切，走角色卡 remix 時不受此限）、遠景不放人、焦距物距成對寫 | 沒有對應構圖 PNG 就進編譯；按警告類型批量改、為過關改核准內容（人群換空座、補 empty background）；分鏡圖換人或漏關鍵道具 | `h3d sketch`、`validate_storyboard.py` | `references/storyboard/shot-intent.md`、`references/storyboard/cinematic-director.md`、`references/storyboard/continuity-ledger.md`；有打鬥／招式／特效另載 `h3-combat-impact`（見下節） |
| 5 提示詞 | **逐鏡親手寫** Layer 2 `five_part_en`（Camera／Motion／Performance／Light／Sound，Motion 與 Performance 必須詳寫；每句要對應看得到或聽得到的結果，不重寫參考圖已有的外貌，寫站位、視線、起訖姿勢、關鍵道具），讀分鏡、構圖與前一鏡狀態後再寫；編譯器只負責組成六段式 | 寫程式產生五小節；編譯後覆寫 segments；用後設詞（authored／approved）或禁止句堆疊交差；沒 ack 就放過警告 | `h3d bind`（先產參考圖綁定）、`h3d author`、`h3d compile --check`、`h3d catalog --check` | `references/prompt-authoring.md`、`references/h3/prompt-formats.md`、`references/tooling.md`；打鬥／大招段同時照 `h3-combat-impact` 寫 |
| 6 影片 | 送件 → 收件 → QA → 動態 QA（光流量凍結／定住，自動提案變速清單）→ 交界連續性 QA（實際切點＋交界拼貼＋一側靜止候選，只警告）→ 逐段結論 → 收件匣 | 兩個 runner 同時跑；碰別人的 job；漂移片拿去 QA；用規劃秒數抽格判交界（先看 `--continuity` 找到的實際切點） | `h3d probe`、`h3d run --plan`、`h3d qa`、`h3d motion`、`h3d qa --continuity`、`h3d verdict`、`h3d inbox` | `references/tooling.md` §2.5–2.8（交界 QA 見 §2.8.1）、`references/speed-ramp.md`、`references/skill-guide.md`「階段 6 生成」 |
| 7 配音剪輯 | 已核准的動作段後製變速（原片不動、台詞原速）、ASR 對位、畫外句壓原聲、響度、每角色音色一次定案、全集單一剪輯專案 | 長旁白交給 H3 念（短畫外句與短旁白預設留 H3，長旁白才外部化）；替使用者定音色；覆寫原片；變速台詞區 | `h3d ramp`、`h3d voice align`、`h3d concat plan/build`、`h3d assemble`；剪輯 lens（只給建議）`scripts/craft/edit_review.py` | `references/tooling.md` §2.7、`references/skill-guide.md`「階段 7」、`references/edit/manju-editing-playbook.md`（剪點／轉場／特效／字幕／登場卡／配樂 ducking／響度）、`references/craft/murch-cut`、`references/craft/hamilton-action` |

**正式階段核准以 `review/project-state.json` 為準**，只能走 `build_stage_review.py --approve-stage`（使用者原話）或 `h3d approve --auto`（使用者授權過的階段）。
**影片生成路線**：預設 Ref2VA（FreeVideo，單人裁切）；使用者改用家機 REMIX 角色包時定案 `h3d decide video_backend remix`，`h3d bind` 改綁角色包、audit 依 backend 分支（REMIX 提示詞輸出與送件尚未接上，見 `references/tooling.md` §2.3.1c）。

**階段 5 段級核准**：階段 5 核准會記每段指紋。核准後只改了部分段 → 只有改過的段（含新增／刪除的段）待重審，沒改的段保持核准、照樣可送件（`h3d submit`／`h3d run` 自動跳過或拒送待重審段）；改過的段一律人工重審：`build_stage_review.py --project-dir . --stage 5 --segments X,Y` 產重審頁 → 使用者通過後 `h3d approve --stage 5 --segments X,Y --user-note "<使用者原話>"`，**不得用 `--auto`**。已有影片的段被改會出現在 `h3d deps --status` 的 stale（`prompt_stale`）。舊快照或共用部分（分段檔外殼、未綁段的 ack、前置階段）變了仍要整份重審。詳見 `references/tooling.md` §2.6。
純文字草稿可按指定範圍交付，不必推進到媒體生成：用 `h3d decide delivery_scope script-only|storyboard-only|prompts-only|full --quote "<使用者原話>"` 定案交付終點（沒定案＝全流程），`h3d next` 到終點就回報 done；`no_image` 時階段 2 只要求文字設定卡。注意：`no_image` 只解除階段 2，階段 4 以後仍要求構圖圖，終點要在階段 3 以前或另行決定。八階段的產出與 HTML 審核頁對照見 `references/skill-guide.md`「八階段流程與 HTML 斷點」，
詳細模板見 `references/pipeline.md`。各階段的 HTML 審核頁現在是除錯頁（綁審核快照用）；交給使用者的是 `h3d inbox` 收件匣，規格見 `references/review-page-spec.md`。

## 打鬥／招式／特效段：同時載入 h3-combat-impact

分鏡或提示詞涉及**打鬥、對打、招式、必殺技／大招、一招秒殺、變身、法術爆炸、特效、衝擊幀、震屏**（或任何 L3 以上命中）時，
**同時載入 `h3-combat-impact`**（ayase0307/h3-combat-impact），兩者並用：

- **階段 4**：照它的必經流程設計角色招式、交手編排（交換／後果）、特效分層與運鏡，並列**衝擊點清單**、每點選衝擊幀路徑（P0–P3）。導演層 lint（`director_lint.py`，warning）會提醒：換新地點先給建立鏡、對白不越 180 度軸、反轉／壞消息後補反應鏡、視線匹配要交代被看物、段間接縫用動作剪輯或遮擋轉場（參考 24frames.art 鏡頭語言，改寫）。
- **階段 5**：打鬥段的 `five_part_en` 照它的決策卡寫——大招預設寫「衝擊幀串」段（模板 F），不寫 `near-freeze`／`hangs poised`／`like a meteor`／`for two frames` 這類 H3 慢詞與幀數控制；
  衝擊幀計畫表（時間碼、打擊點、力度、路徑、組裝倍率）寫進該段的分鏡備註／交付說明（segments 目前沒有專屬欄位）。
- **階段 7**：已核准的打鬥段依衝擊幀計畫做變速（`h3d ramp`，或該技能的 `impact_frame.py ramp`）或合成（`impact_frame.py composite`）；台詞區仍原速。
- 鏡長：衝擊幀串段、打擊短鏡可以短於 h3-video-prompting 的「每鏡 ≥2 s」，以 h3-combat-impact 為準。

本 repo 的配套寫法：`references/storyboard/xuanhuan-combat-contract.md`（戰鬥分支、動作成立條件、場地、衝擊三層、鏡頭速度用語、大招過程鏈）與 `references/storyboard/vfx-design-and-review.md`（特效設計卡、保臉防線、看圖驗收與返修、局部修正寫法）；兩份都是外部技能蒸餾、未經 H3 實測。

這是轉介，不改本技能的門禁：`validate_storyboard.py`、`h3d compile --check`、`h3d catalog --check` 照常要過。

## 四道確定性檢查（交付的一部分）

時長量子（17n+5，用 `metadata.frames` 送件）、證據分級（階段 6 要 `VERIFIED`）、segment 級依賴帳本（`h3d deps`）、
失敗目錄（`h3d catalog --check`／`h3d ack`）。`duration_drift`、`PARTIAL`、`已有 waiting 的 job` 都代表「現在不能繼續」，
處置見 `references/tooling.md` §4。

## 資源（索引）

- `references/tooling.md` — **h3d 全部指令與檢查**（跑任何指令前先讀）；§2.5 定案／逐段結論、§2.6 收件匣與自動核准、§2.7 runner／probe／配音／剪輯。
- `references/skill-guide.md` — 原 SKILL.md 全文：核心原則 0–14、專案結構、階段 6 實戰定案、階段 7 配音分層、完整腳本清單。
- `references/pipeline.md` — 八階段詳細流程、提問清單、模板；聲音三層決策與響度標準。
- `references/review-page-spec.md` — 審查頁規格：交給使用者的是決策收件匣（版面順序、卡片必備欄位、禁止事項），舊階段頁只作除錯。
- `references/adapt/`（改編）、`references/storyboard/`（導演分鏡）、`references/consistency.md`（資產一致性）、
  `references/styles.md`（風格鎖定錨）、`references/freevideo.md`、`references/model-profiles.md`、
  `references/minimax-h3.md` 與 `references/h3/`（H3 細部參考，同步自上游 h3-video-prompting）、`references/prompt-playbook.md`、
  `references/craft/`（創作 lens，只給建議不改門禁）、`references/edit/`（階段 7 漫劇剪輯手冊、Concat／剪映草稿調查）。
- 打鬥／招式／特效／衝擊幀：外部技能 `h3-combat-impact`（ayase0307/h3-combat-impact），見上方「打鬥／招式／特效段」。
- `references/revision-and-retry.md` — 改稿必附改動清單＋聯動結論、同鏡重抽最多 2 次後回層診斷、驗收比較原則。
- `references/storyboard/continuity-ledger.md` — 人物賬、分鏡審查清單、三種方位、站位附表、正反打、段縫末態、參考圖用途。
- 格式：`references/schemas/`（decisions、verdicts）。給 agent 的硬規則另見 `AGENTS.md`。
