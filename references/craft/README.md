# 創作 lens（craft lenses）

這個資料夾放的是用[女媧 nuwa-skill](https://github.com/alchaincyf/nuwa-skill)方法蒸餾出來的創作視角。每個 lens 是一個獨立的子技能，自帶 `SKILL.md`、`FIDELITY.md`（保真度與限制），以及 `references/research/`（調研底稿，附來源網址）。

**所有 lens 都只給建議，不擋關。** 它們不會改 `review/project-state.json`，也不會改變任何門禁，只會把報告寫到 `review/craft/stage-<N>-<lens>-<ep>.md`。`build_stage_review.py` 會把這些報告顯示在對應階段的審查頁上。

| lens | 類型 | 接入的階段 | 腳本 |
|---|---|---|---|
| `ai-drama-hit-method` | 主題（AI 漫劇爆款方法論） | 0 定調、1 改編、3 劇本 | `scripts/craft/hit_review.py` |
| `araki-manga-craft` | 人物（荒木飛呂彥） | 2 資產、3 劇本 | `scripts/craft/araki_review.py` |
| `mckee-scene` | 人物（Robert McKee） | 3 劇本（`script-review-epXX.md`） | `scripts/craft/mckee_review.py` |
| `mccloud-panels` | 人物，薄版（Scott McCloud） | 4 分鏡 | `scripts/craft/mccloud_review.py` |

（後三個 lens 各自用獨立的 PR 加入；還沒合併的話，對應的資料夾不會存在。）

腳本只做確定性的檢查，例如結構、時間、合規字詞。需要判斷的部分，由 Agent 讀對應 lens 的 `SKILL.md` 後補寫到同一份報告的「Agent 審查」段落。
