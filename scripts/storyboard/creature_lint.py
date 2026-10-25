"""#97 #101 #121：生物外觀的文字／參考圖矛盾檢查與色彩 QA（純離線）。"""
from __future__ import annotations

import re
from typing import Dict, List, Sequence, Tuple

# 蛇的動作先驗：文字寫蚯蚓／無牙，卻又寫 tongue／hiss／fangs，模型以蛇為準（#97）
SNAKE_NOUN_RE = re.compile(r"\b(serpent|snake|python|cobra|viper)\b", re.I)
SNAKE_PRIOR_RE = re.compile(r"\b(flicking|forked|flicks?|tongue|hiss(?:es|ing)?|fangs?|slither(?:s|ing)?)\b", re.I)
WORM_RE = re.compile(r"\b(worm|earthworm|toothless|legless boneless)\b", re.I)
NO_TONGUE_TEETH_RE = re.compile(r"\b(toothless|no (?:teeth|tongue)|without (?:teeth|a tongue)|gums)\b", re.I)
HEAD_CLAIM_RE = re.compile(r"\b(toothless|no (?:teeth|tongue)|without (?:teeth|a tongue)|worm|earthworm|"
                           r"fleshy folds?|round (?:toothless )?mouth)\b", re.I)


def head_retention_clause(desc_en: str, index: int) -> str:
    """生物保留句：文字設定有口型／牙／舌特徵時，頭部細節以文字為準，不寫死「頭部特徵來自圖」。"""
    if desc_en and HEAD_CLAIM_RE.search(desc_en):
        return (f"the body shape, surface texture and colour from <Picture {index}> are retained; "
                f"the head and mouth details follow the written description of this subject")
    return f"the body shape, skin or surface texture, and head features from <Picture {index}> are retained"


def lint_creature_text(creature_id: str, desc_en: str, action_texts: Sequence[str]) -> List[str]:
    """回傳警告字串。desc_en＝固定英文描述；action_texts＝各鏡含該生物的 Action／Expression。"""
    out: List[str] = []
    desc = desc_en or ""
    actions = " ".join(a for a in action_texts if a)
    if SNAKE_NOUN_RE.search(desc) and NO_TONGUE_TEETH_RE.search(desc):
        out.append(f"{creature_id}：定義同時寫蛇名詞與無牙／無舌；蛇名詞會帶蛇的外觀先驗，"
                   f"建議主體名詞改成設定實際想要的形體（如 giant worm／earthworm）(#97)")
    if (WORM_RE.search(desc) or NO_TONGUE_TEETH_RE.search(desc)) and SNAKE_PRIOR_RE.search(actions):
        m = SNAKE_PRIOR_RE.search(actions)
        out.append(f"{creature_id}：設定為無牙／蚯蚓類，但動作含蛇的典型動作「{m.group(0)}」；"
                   f"模型會補上蛇牙或分叉舌，請刪除或改成肉環口收縮等寫法 (#97)")
    if SNAKE_NOUN_RE.search(desc) and SNAKE_PRIOR_RE.search(actions) is None and WORM_RE.search(actions):
        out.append(f"{creature_id}：定義用蛇名詞、動作卻用蚯蚓名詞，主體名稱前後不一 (#97)")
    return out


def hsv_median(pixels: Sequence[Tuple[int, int, int]]) -> Dict[str, float]:
    """RGB 像素 → 色相（度）、彩度、明度的中位數（#121）。"""
    import colorsys
    import statistics
    if not pixels:
        raise ValueError("no pixels")
    hs, ss, vs = [], [], []
    for r, g, b in pixels:
        h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        hs.append(h * 360)
        ss.append(s)
        vs.append(v)
    return {"hue": statistics.median(hs), "sat": statistics.median(ss), "val": statistics.median(vs)}


def compare_hsv(ref: Dict[str, float], got: Dict[str, float], *, hue_tol: float = 8.0,
                sat_tol: float = 0.10) -> Dict[str, object]:
    """色相、彩度分開報；超過容許就 flag。"""
    dh = abs(got["hue"] - ref["hue"])
    dh = min(dh, 360 - dh)
    ds = got["sat"] - ref["sat"]
    return {"hue_delta": round(dh, 1), "sat_delta": round(ds, 3),
            "hue_ok": dh <= hue_tol, "sat_ok": abs(ds) <= sat_tol,
            "ok": dh <= hue_tol and abs(ds) <= sat_tol}
