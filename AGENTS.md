# AGENTS.md（給在這個 repo 或用這個 skill 做專案的 agent）

全程使用繁體中文（程式註解、commit 訊息、PR 說明都一樣）。

## 做漫劇專案時的硬規則

1. **開工先跑 `python scripts/h3d.py next --root <專案>`**，照它印的唯一一條指令做；每做完一步再跑一次。
2. **使用者定案一律 `h3d decide <id> <值> --quote "<使用者原話>"`**，不要只寫在筆記裡，也不要替使用者決定。
3. **不准手改 `review/project-state.json`。** 狀態只能由 `scripts/build_stage_review.py`（`--stage`／`--approve-stage`）寫入；手改會被偵測（寫入戳記對不上）並由 `h3d next` 擋下。
   階段 6 技術 QA 為 PARTIAL 但使用者看過仍核准：`--approve-stage 6 --override --reason "<使用者理由>"`；不得代替使用者核准。
4. **階段 6 逐段結論一律 `h3d verdict`** 寫進 `review/verdicts.json`，依 `decisions.json` 的 `acceptance_policy` 分類；舊格式 conclusions-*.json 用 `h3d verdict import` 轉。
4a. **要使用者決定的事用 `h3d inbox` 交給使用者**（只列例外，不要把整頁資料攤開）；使用者授權過的階段照 `h3d next` 跑 `h3d approve --auto`。階段 0、角色設定圖（階段 2）、每個角色的音色永遠要使用者本人決定。
5. **不同時跑兩個影片 runner**，也不要碰不是自己送的 job；ledger 有 waiting／running 的工作時只收件。整批送件用 `h3d run --plan`（內建單例鎖、佇列檢查、暫停續跑），不要再自寫 runner；送件前 `h3d probe`。
5a. **階段 7 固定走 `h3d voice align`**（ASR 對位、畫外句壓原聲、響度），剪輯用 `h3d concat`；每個角色的音色由使用者定案（`h3d decide voice:<角色>`）。
5b. **先想鏡頭意思再寫技術值**：階段 4 每鏡先填 `shot_intent`（觀眾要看懂什麼、節拍、視角、情緒變化），每個技術選擇在 `choice_why` 寫理由（`validate_storyboard.py` I01–I06 擋）。處理警告逐鏡回到意圖，**不准為了過關改使用者核准過的內容**，報警告一定附解法。見 `references/storyboard/shot-intent.md`、`docs/retrospectives/2026-10-24-edj2-ep01.md`。
6. **遇到 `PARTIAL`、`duration_drift`、`已有 waiting 的 job` 就停下**，照 `references/tooling.md` §4 處置並回報使用者。

## 改這個 repo 時

- 測試：`python -m unittest discover -s tests -q` 必須全過；新功能要附單元測試。
- `h3d` 只做路由，規則留在原本的模組（`project_state.py`、`decisions.py`、`verdicts.py`…），不要在 `h3d.py` 寫第二套邏輯。
- 檔案格式改動要同步更新 `references/schemas/` 裡的 JSON Schema 與 `references/tooling.md`。
