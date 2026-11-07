"""adapt_policy.py — 改編政策（P2-5，導演大師對照）：faithful／extract／shell 三檔。

來源：導演大師拆解 skills-pack/017_drama-04-script-from-script.md §改編幅度——
`faithful` 忠實（只整理成場次、不刪關鍵情節、對白盡量保留）／`extract` 抽核（壓到
單集目標秒數、刪不推動情節的枝節、留下的對白照抄原文）／`shell` 借殼（場面可換、
人物關係與轉折保留、對白仍原文原句）。只吸收三檔的形狀，全部重寫。

本 repo 的預設（沒定案）＝dialogue-first 現狀：原著對白全保留＋事件交代不打折
（比 faithful 更嚴），行為完全不變。三檔是 opt-in（`h3d decide adapt_policy <值>`）：

- `faithful`：與預設同一套門檻（G1 對白覆蓋照舊），只是把政策明示記帳。
- `extract`：壓到單集目標秒數——G1 覆蓋率門檻放寬到 0.50，低於 0.85 的刪句列清單
  記帳（WARN）；整體覆蓋低於 0.50 仍 FAIL。**只有 series_format=short 可定案**
  （長篇模式的事件交代不打折是本技能的根契約，decisions.decide 會擋）。
- `shell`：對白仍原文（G1 照舊）；場面可換——放寬的是場景對照，由作者在 handoff
  的 `adaptation_changes` 記理由，門禁不因 shell 放寬對白。

覆蓋率數值標記：0.85＝dialogue-first 既有門檻；0.50＝docs 值（導演大師形狀，未實測）。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

POLICIES = ("faithful", "extract", "shell")
#: dialogue-first 既有門檻：允許脫水（拆句、去語助詞），不允許刪句。
DEFAULT_COVERAGE_MIN = 0.85
#: 抽核（extract）的覆蓋下限：低於此就不是「保留關鍵對白」而是重寫（docs 值，未實測）。
EXTRACT_COVERAGE_MIN = 0.50
DECISION_ID = "adapt_policy"


def normalize_policy(value: Any) -> Optional[str]:
    """正規化政策值；未知／空值回 None（＝沒定案，dialogue-first 現狀）。"""
    text = str(value or "").strip().lower()
    return text if text in POLICIES else None


def coverage_floor(policy: Optional[str]) -> float:
    """G1 逐句覆蓋門檻：extract＝0.50，其餘（含沒定案）＝0.85。"""
    return EXTRACT_COVERAGE_MIN if normalize_policy(policy) == "extract" else DEFAULT_COVERAGE_MIN


def _policy_from_data(data: Dict[str, Any]) -> Optional[str]:
    for item in (data or {}).get("decisions", []) or []:
        if isinstance(item, dict) and item.get("id") == DECISION_ID:
            return normalize_policy(item.get("value"))
    return None


def policy_from_decisions(root: Path) -> Optional[str]:
    """讀專案 decisions.json 的 adapt_policy；沒有檔或沒定案回 None。"""
    path = Path(root) / "decisions.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return _policy_from_data(data)


def policy_from_script_path(script_path: Path) -> Optional[str]:
    """從劇本檔往上找 decisions.json 讀 adapt_policy（adapt_gate 的自動讀取）。"""
    p = Path(script_path).resolve()
    for base in p.parents:
        policy = policy_from_decisions(base)
        if policy is not None:
            return policy
        if (base / "decisions.json").exists():
            return None  # 找到最近的 decisions.json 就停：政策沒定案＝None
    return None
