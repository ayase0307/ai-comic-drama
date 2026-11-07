"""short_rhythm.py — 短劇（series_format=short）的全季分集節奏預設（P2-7，導演大師對照）。

來源：導演大師拆解 skills-pack/000_drama-01-outline.md L35——「節奏參考：起勢~15% →
攀升~30% → 風暴~35% → 決戰~20%。付費卡點約佔全集 10–15%」。只吸收比例形狀與
「卡點放在鉤子集」的用法，全部重寫；長篇漫劇（預設）不用這份預設。

這是「預設」不是門禁：作者可以偏離，偏離時在 decisions.json 記原話說明。
`estimate_duration.py --novel`（短劇模式）會把 `rhythm_plan(建議集數)` 附在結果的
`short_rhythm` 欄位（以推薦政策②的集數為例）。
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

#: 四相位（key, 中文標籤, 佔全集比例）。比例來源見模組 docstring。
PHASES: Tuple[Tuple[str, str, float], ...] = (
    ("rising", "起勢", 0.15),
    ("climbing", "攀升", 0.30),
    ("storm", "風暴", 0.35),
    ("finale", "決戰", 0.20),
)
#: 付費卡點集數佔全集的比例區間（下限, 上限）；配額用中值 12.5%。
PAYWALL_RATIO: Tuple[float, float] = (0.10, 0.15)
PAYWALL_MID_RATIO = 0.125
SOURCE_NOTE = "導演大師拆解 000_drama-01-outline L35 的比例形狀（15/30/35/20＋卡點 10–15%），全部重寫"

# 少於四集時的合併相位（每項＝(相位 key 們, 起集, 末集)）；單集不適用（見 rhythm_plan）。
_MERGED_PLANS: Dict[int, List[Tuple[Tuple[str, ...], int, int]]] = {
    2: [(("rising", "climbing"), 1, 1), (("storm", "finale"), 2, 2)],
    3: [(("rising",), 1, 1), (("climbing", "storm"), 2, 2), (("finale",), 3, 3)],
}


def _allocate(total: int) -> List[int]:
    """最大餘額法把 total 集按 15/30/35/20 分配；total ≥ 4 時每相位至少一集。"""
    raw = [total * ratio for _, _, ratio in PHASES]
    counts = [int(x) for x in raw]
    remaining = total - sum(counts)
    order = sorted(range(len(PHASES)),
                   key=lambda i: (raw[i] - counts[i], PHASES[i][2], -i), reverse=True)
    for i in order[:max(0, remaining)]:
        counts[i] += 1
    # 保底：total ≥ 4 時任何相位不得為 0；從目前最多的相位挪一集過來。
    while total >= len(PHASES) and 0 in counts:
        empty = counts.index(0)
        donor = max(range(len(counts)), key=lambda i: (counts[i], -i))
        if counts[donor] <= 1:
            break
        counts[donor] -= 1
        counts[empty] += 1
    return counts


def _paywall_count(total: int) -> int:
    """付費卡點數量：總集數 × 12.5%（10–15% 中值），至少 1、不超過 total-1（末集後面沒有內容）。"""
    return max(1, min(int(round(total * PAYWALL_MID_RATIO)), total - 1))


def _paywall_positions(total: int, count: int, climbing_end: int, storm_end: int) -> List[int]:
    """付費卡點建議位置：均勻分布在整條集數線上（切成 count+1 段的每段末集），
    再把最接近相位交界的建議位置吸附過去——風暴末集（決戰前的鉤子）優先、
    攀升末集次之；同一格不會被兩個交界搶（卡點數不足以兩個都卡時，保證風暴末集）。
    交界本身是最後一集時不卡：後面沒有內容。"""
    count = max(1, min(int(count), total - 1))
    positions = [int(round(total * (i + 1) / (count + 1))) for i in range(count)]
    anchored: set = set()
    for anchor in (storm_end, climbing_end):
        if anchor >= total:
            continue
        candidates = [i for i in range(len(positions)) if i not in anchored]
        if not candidates:
            break
        best = min(candidates, key=lambda i: (abs(positions[i] - anchor), i))
        positions[best] = anchor
        anchored.add(best)
    return sorted(set(positions))


def rhythm_plan(total_episodes: int) -> Dict[str, Any]:
    """把總集數切成四相位（起勢／攀升／風暴／決戰），並給付費卡點建議位置。

    - total ≥ 4：四相位各自至少一集（最大餘額法，比例 15/30/35/20）。
    - total 2–3：合併相位（2 集＝起勢＋攀升／風暴＋決戰；3 集＝起勢／攀升＋風暴／決戰）。
    - total 1：單集短劇，四相位在同一集內以節拍呈現（structure-and-pacing.md §二），
      不給集數範圍與卡點。
    """
    total = int(total_episodes)
    if total <= 0:
        raise ValueError("total_episodes 必須 ≥ 1")
    if total == 1:
        return {
            "total_episodes": 1,
            "mode": "single_episode",
            "phases": [],
            "paywall_count": 0,
            "paywall_positions": [],
            "paywall_ratio": list(PAYWALL_RATIO),
            "note": "單集短劇：四相位在同一集內以節拍呈現（structure-and-pacing.md §二 微型五節拍容器）",
            "source": SOURCE_NOTE,
        }
    if total in _MERGED_PLANS:
        phase_rows: List[Dict[str, Any]] = []
        for keys, start, end in _MERGED_PLANS[total]:
            labels = "＋".join(label for key, label, _ in PHASES if key in keys)
            phase_rows.append({"phases": list(keys), "label": labels,
                               "start": start, "end": end, "episodes": end - start + 1})
        climbing_end = next(row["end"] for row in phase_rows if "climbing" in row["phases"])
        storm_end = next(row["end"] for row in phase_rows if "storm" in row["phases"])
        mode = "merged_phases"
    else:
        counts = _allocate(total)
        phase_rows = []
        cursor = 1
        for (key, label, ratio), count in zip(PHASES, counts):
            phase_rows.append({"phases": [key], "label": label, "ratio": ratio,
                               "start": cursor, "end": cursor + count - 1, "episodes": count})
            cursor += count
        climbing_end = next(row["end"] for row in phase_rows if row["phases"] == ["climbing"])
        storm_end = next(row["end"] for row in phase_rows if row["phases"] == ["storm"])
        mode = "four_phases"
    positions = _paywall_positions(total, _paywall_count(total), climbing_end, storm_end)
    return {
        "total_episodes": total,
        "mode": mode,
        "phases": phase_rows,
        "paywall_count": len(positions),
        "paywall_positions": positions,
        "paywall_ratio": list(PAYWALL_RATIO),
        "note": ("付費卡點是建議位置（攀升末集／風暴末集必卡）；每個卡點的 type 與 suspense 由作者填"
                 "（導演大師 paywalls 欄位形狀：episode／type／suspense）"),
        "source": SOURCE_NOTE,
    }
