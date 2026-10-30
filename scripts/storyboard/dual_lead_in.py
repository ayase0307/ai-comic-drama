#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""雙人引子（E3）：段縫硬切後、本段第 1 鏡是單人近景時，先拍 2 秒雙人鏡，組裝時自動剪掉。

規則全文與證據：`references/storyboard/spatial-consistency.md` §7。

寫法（Layer 2；編譯器不用改，引子就是一顆普通的第 1 鏡，五小節照 prompt-authoring 親手寫）：
  shots[0].dual_lead_in = true
  shots[0] 兩名角色（本段第一個單人鏡的主體＋畫外對戲那位）、≥2.0 s（編譯器每鏡下限）、無台詞、固定機位雙人 MLS
  後面每一鏡的 start/end 與 speech_window 一起往後挪；段長多 2 s（frames 由 compile 依 17n+5 向上取）

本模組只做三件事：
  lead_in_seconds(seg)      → 要剪掉的秒數（引子鏡的 end_time）；沒標或格式不對＝0
  check(seg)                → 標了 dual_lead_in 但格式不對的問題清單（`h3d staging` W48、`h3d assemble` 直接擋）
  suggest(seg, prev)        → 這段適不適合加引子（`h3d staging` W47，只建議）
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

MIN_LEAD_S = 2.0          # 編譯器 H3 切點下限：每鏡 ≥2 s（T4 原計畫 1.5 s 放不進）
RECOMMENDED_LEAD_S = 2.0
NO_LINE = {"", "（無台詞）", "(無台詞)", "無台詞", "n/a", "none"}

# 景別：MS 或更近才算「單人近景」（遠一點的單人鏡本來就看得到環境，T4 沒測）
_COMBAT_HINTS = ("combat", "impact", "fight", "punch", "kick", "slash", "打鬥", "武戲", "出拳")


def _shots(seg: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [s for s in (seg.get("shots") or []) if isinstance(s, dict)]


def _f(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _ids(shot: Dict[str, Any]) -> List[str]:
    ids = shot.get("visual_subject_ids") or shot.get("character_ids") or []
    return [str(x) for x in ids if x]


def _line_of(shot: Dict[str, Any]) -> str:
    dlg = shot.get("dialogue_and_audio") or {}
    for value in (dlg.get("line_verbatim"), shot.get("subtitle"), shot.get("narration"), shot.get("line_verbatim")):
        text = str(value or "").strip()
        if text.casefold() not in NO_LINE:
            return text
    return ""


def has_dialogue(shot: Dict[str, Any]) -> bool:
    dlg = shot.get("dialogue_and_audio") or {}
    return dlg.get("has_dialogue") is True or bool(_line_of(shot))


def marked(seg: Dict[str, Any]) -> bool:
    return any(s.get("dual_lead_in") is True for s in _shots(seg))


def _bounds(shot: Dict[str, Any]) -> tuple:
    st = _f(shot.get("start_time", shot.get("start")))
    et = _f(shot.get("end_time", shot.get("end")))
    if st is None:
        st = 0.0
    if et is None:
        dur = _f(shot.get("duration"))
        et = st + dur if dur is not None else None
    return st, et


def check(seg: Dict[str, Any]) -> List[str]:
    """標了 dual_lead_in 時的格式問題；沒標回傳空清單（舊專案零影響）。"""
    shots = _shots(seg)
    flagged = [i for i, s in enumerate(shots) if s.get("dual_lead_in") is True]
    if not flagged:
        return []
    problems: List[str] = []
    if flagged != [0]:
        where = "、".join(f"第 {i + 1} 鏡" for i in flagged if i != 0)
        if where:
            problems.append(f"dual_lead_in 只能標在第 1 鏡（現在在{where}）；組裝只會剪片頭")
    if len(shots) < 2:
        problems.append("整段只有引子一鏡；引子後面要接本段真正的鏡頭")
    lead = shots[0]
    if lead.get("dual_lead_in") is not True:
        return problems
    st, et = _bounds(lead)
    if st and abs(st) > 1e-6:
        problems.append(f"引子要從 0.0 s 開始（現在 {st:g} s）")
    if et is None:
        problems.append("引子缺 end_time／duration，組裝不知道要剪多長")
    elif et - (st or 0.0) < MIN_LEAD_S - 1e-6:
        problems.append(f"引子 {et - (st or 0.0):.2f} s，短於 {MIN_LEAD_S:g} s（編譯器每鏡下限；T4 用 2.0 s）")
    n = len(_ids(lead))
    if n != 2:
        problems.append(f"引子要剛好兩名角色同框（character_ids 現在 {n} 個）")
    if has_dialogue(lead):
        problems.append("引子裡有台詞；引子整段會被剪掉，台詞放到第 2 鏡之後")
    dlg = lead.get("dialogue_and_audio") or {}
    if isinstance(dlg.get("speech_window"), dict):
        problems.append("引子不可有 speech_window")
    if et is not None:
        for k, shot in enumerate(shots[1:], start=2):
            win = (shot.get("dialogue_and_audio") or {}).get("speech_window")
            if isinstance(win, dict) and _f(win.get("start")) is not None and _f(win.get("start")) < et - 1e-6:
                problems.append(f"第 {k} 鏡 speech_window 從 {_f(win.get('start')):g} s 開始，落在引子（0–{et:g} s）裡；"
                                f"引子後的時間要整段往後挪")
        if len(shots) > 1:
            nst, _ = _bounds(shots[1])
            if nst is not None and abs(nst - et) > 0.05:
                problems.append(f"第 2 鏡從 {nst:g} s 開始，和引子結束 {et:g} s 對不上")
    return problems


def lead_in_seconds(seg: Dict[str, Any]) -> float:
    """要在組裝時剪掉的片頭秒數；沒標＝0。格式不對時也回 0，呼叫端應先看 check()。"""
    shots = _shots(seg)
    if not shots or shots[0].get("dual_lead_in") is not True:
        return 0.0
    _, et = _bounds(shots[0])
    return float(et) if et and et > 0 else 0.0


def _size(shot: Dict[str, Any]) -> str:
    optics = shot.get("camera_optics") or {}
    return str(optics.get("shot_size") or shot.get("shot_size") or "").strip().lower()


def _is_close(size: str) -> bool:
    s = size.lower()
    if not s or any(w in s for w in ("wide", "long", "full", "establishing", "遠景", "全景")):
        return False
    tokens = set(re.split(r"[^a-z]+", s))
    if tokens & {"mls", "ls", "ws", "els", "fs"}:
        return False
    if tokens & {"mcu", "cu", "ecu", "bcu", "ms", "ots"}:
        return True
    return any(h in s for h in ("close", "medium", "over-the-shoulder", "over the shoulder", "近景", "特寫", "中景", "過肩"))


def _is_combat(seg: Dict[str, Any]) -> bool:
    if seg.get("impact_plan") or (seg.get("metadata") or {}).get("impact_plan"):
        return True
    for lora in list(seg.get("h3_loras") or []) + list(seg.get("loras_proposed") or []):
        if any(h in str(lora).lower() for h in _COMBAT_HINTS):
            return True
    return False


def _same_scene(seg: Dict[str, Any], prev: Optional[Dict[str, Any]]) -> bool:
    if not prev:
        return False
    a = seg.get("narrative_scene_id") or seg.get("scene_id")
    b = prev.get("narrative_scene_id") or prev.get("scene_id")
    return not a or not b or a == b


def suggest(seg: Dict[str, Any], prev: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """回傳建議訊息或 None。條件（全部符合才建議）：
    同場上一段存在、本段段縫不是同機位續接（seam_in≠cont，且上一段末鏡不是同主體同景別）、不是武戲、
    本段第 1 鏡是單人且 MS 或更近、
    本段有台詞、本段＋同場上一段合計 ≥2 名具名角色、還沒標 dual_lead_in。"""
    shots = _shots(seg)
    if not shots or marked(seg) or not _same_scene(seg, prev):
        return None
    if str(seg.get("seam_in") or "").lower() == "cont":
        return None
    if _is_combat(seg):
        return None
    first = shots[0]
    ids = _ids(first)
    if len(ids) != 1 or not _is_close(_size(first)):
        return None
    if not any(has_dialogue(s) for s in shots):
        return None
    prev_shots = _shots(prev)
    if prev_shots and _ids(prev_shots[-1]) == ids and _size(prev_shots[-1]) == _size(first):
        return None  # 同主體同景別接過來＝同一顆鏡頭拆兩段（續接），不是硬切
    partners: List[str] = []  # 對戲那位：先找本段後面鏡頭出現的人，再找同場上一段最後出現的人
    for s in shots[1:] + list(reversed(prev_shots)):
        for cid in _ids(s):
            if cid not in ids and cid not in partners:
                partners.append(cid)
    if not partners:
        return None
    return (f"本段段縫硬切、第 1 鏡是 {ids[0]} 的單人近景；建議在前面加 2.0 s 雙人引子（{ids[0]}＋{partners[0]} 同框、"
            f"固定機位 MLS、無台詞，shots[0].dual_lead_in=true），組裝自動剪掉。T4 實測同段同種子跑位／重演 "
            f"0/12（現流程 4/12、新流程 5/12）；只一場戲、REMIX，見 spatial-consistency.md §7")
