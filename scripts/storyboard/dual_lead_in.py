#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""雙人引子（E3）：段縫硬切後、本段第 1 鏡是單人近景時，先拍 2 秒雙人鏡，組裝時自動剪掉。

規則全文與證據：`references/storyboard/spatial-consistency.md` §7。

寫法（Layer 2；編譯器不用改，引子就是一顆普通的第 1 鏡，五小節照 prompt-authoring 親手寫）：
  shots[0].dual_lead_in = true
  shots[0] 兩名角色（本段第一個單人鏡的主體＋畫外對戲那位）、≥2.0 s（T4 實測長度）、無台詞、固定機位雙人 MLS
  後面每一鏡的 start/end 與 speech_window 一起往後挪；段長多 2 s（frames 由 compile 依 17n+5 向上取）

本模組：
  lead_in_seconds(seg)      → 要剪掉的秒數（引子鏡的 end_time）；沒標或格式不對＝0
  check(seg)                → 標了 dual_lead_in 但格式不對的問題清單（`h3d staging` W48、`h3d assemble` 直接擋）
  suggest(seg, prev)        → 這段適不適合加引子（`h3d staging` W47，只建議）
  strip_layer2(seg)         → 拿掉引子、時間整段前移的 Layer 2 副本（節奏／密度閘門用：引子會被剪掉，不算進成片）
  strip_pacing(seg)         → 同上，給 pacing_gate 的輸入格式（shots/lines 的 start/end、duration）
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

# 引子長度維持 2.0 s：這是 T4 實測（0/12 跑位重演）用的長度。#120 把編譯器硬下限降到 1.2 s，但 1.2–2.0 s
# 仍出「短鏡未實測」提醒（h3_spec.SHOT_SOFT_MIN_SEC），H3 切點誤差約 0.12 s；更短的引子沒有證據，不放寬。
# （T4 當時原計畫 1.5 s，是被那時的 2 s 編譯下限擋掉才改 2.0 s；之後實測的就是 2.0 s。）
MIN_LEAD_S = 2.0
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


def has_onscreen_dialogue(shot: Dict[str, Any]) -> bool:
    """這鏡有沒有畫內對話（看得到嘴在說）：主句或 extra_lines 任一句不是旁白／畫外／內心 VO。

    EP01 findings #7：純內心 VO 段沒有對戲的人在畫外等著接話，W47 不該建議引子。"""
    if not has_dialogue(shot):
        return False
    try:
        from dialogue_density import is_voiceover_line
    except ImportError:  # pragma: no cover - 套件匯入路徑
        from .dialogue_density import is_voiceover_line
    dlg = shot.get("dialogue_and_audio") or {}
    if not dlg:
        return True  # 舊格式只有 subtitle／line_verbatim：維持原判斷
    if dlg.get("voice_only") is not True and not is_voiceover_line(dlg) and _line_of(shot):
        return True
    for ex in dlg.get("extra_lines") or []:
        if isinstance(ex, dict) and str(ex.get("line_verbatim") or "").strip() \
                and ex.get("voice_only") is not True and not is_voiceover_line(ex):
            return True
    return False


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


def _windows(shot: Dict[str, Any]) -> List[tuple]:
    """這鏡所有段內秒數的台詞時間窗：speech_window、line_timecodes、extra_lines[].speech_window（#120 同鏡接話）。"""
    dlg = shot.get("dialogue_and_audio") or {}
    out = []
    if isinstance(dlg.get("speech_window"), dict):
        out.append(("speech_window", dlg["speech_window"]))
    for i, tc in enumerate(dlg.get("line_timecodes") or [], start=1):
        if isinstance(tc, dict):
            out.append((f"line_timecodes[{i}]", tc))
    for i, ex in enumerate(dlg.get("extra_lines") or [], start=1):
        if isinstance(ex, dict) and isinstance(ex.get("speech_window"), dict):
            out.append((f"extra_lines[{i}].speech_window", ex["speech_window"]))
    return out


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
        problems.append(f"引子 {et - (st or 0.0):.2f} s，短於 {MIN_LEAD_S:g} s（T4 實測長度；更短的引子沒有證據）")
    n = len(_ids(lead))
    if n != 2:
        problems.append(f"引子要剛好兩名角色同框（character_ids 現在 {n} 個）")
    if has_dialogue(lead):
        problems.append("引子裡有台詞；引子整段會被剪掉，台詞放到第 2 鏡之後")
    if _windows(lead):
        problems.append("引子不可有 speech_window／line_timecodes／extra_lines")
    if et is not None:
        for k, shot in enumerate(shots[1:], start=2):
            for label, win in _windows(shot):
                if _f(win.get("start")) is not None and _f(win.get("start")) < et - 1e-6:
                    problems.append(f"第 {k} 鏡 {label} 從 {_f(win.get('start')):g} s 開始，落在引子（0–{et:g} s）裡；"
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


def _shift_window(win: Dict[str, Any], lead: float) -> Dict[str, Any]:
    out = dict(win)
    for key in ("start", "end"):
        v = _f(out.get(key))
        if v is not None:
            out[key] = round(v - lead, 6)
    return out


def strip_layer2(seg: Dict[str, Any]) -> Dict[str, Any]:
    """拿掉 dual_lead_in 引子、其後時間整段前移 lead 秒的 Layer 2 副本；沒標（或整段只有引子）原樣回傳。

    節奏與密度閘門（validate_storyboard D1–D4、說話佔比、段長提醒）用它：引子在組裝時剪掉，
    不是成片的一部分，不該吃掉蒙太奇額度、拉低密度或拉長段長。編譯與送件照舊用原段（引子要生成）。"""
    shots = _shots(seg)
    lead = lead_in_seconds(seg)
    if not lead or len(shots) < 2:
        return seg
    out = dict(seg)
    new_shots = []
    for shot in shots[1:]:
        s2 = dict(shot)
        for key in ("start_time", "end_time", "start", "end"):
            v = _f(s2.get(key))
            if v is not None:
                s2[key] = round(v - lead, 6)
        dlg = dict(s2.get("dialogue_and_audio") or {})
        if isinstance(dlg.get("speech_window"), dict):
            dlg["speech_window"] = _shift_window(dlg["speech_window"], lead)
        if dlg.get("line_timecodes"):
            dlg["line_timecodes"] = [_shift_window(t, lead) if isinstance(t, dict) else t for t in dlg["line_timecodes"]]
        if dlg.get("extra_lines"):
            dlg["extra_lines"] = [{**x, "speech_window": _shift_window(x["speech_window"], lead)}
                                  if isinstance(x, dict) and isinstance(x.get("speech_window"), dict) else x
                                  for x in dlg["extra_lines"]]
        if "dialogue_and_audio" in s2:
            s2["dialogue_and_audio"] = dlg
        new_shots.append(s2)
    out["shots"] = new_shots
    meta = dict(seg.get("metadata") or {})
    t = _f(meta.get("target_duration_sec"))
    if t is not None:
        meta["target_duration_sec"] = round(t - lead, 6)
    if "metadata" in seg or t is not None:
        out["metadata"] = meta
    out["_dual_lead_in_stripped_sec"] = lead
    return out


def strip_pacing(seg: Dict[str, Any]) -> Dict[str, Any]:
    """pacing_gate 輸入格式版：shots[0].dual_lead_in 時拿掉該鏡，shots／lines 的 start/end 與 duration 扣掉引子。"""
    shots = _shots(seg)
    lead = lead_in_seconds(seg)
    if not lead or len(shots) < 2:
        return seg
    out = dict(seg)
    out["shots"] = [{**s, "start": round(float(s.get("start", 0)) - lead, 6),
                     "end": round(float(s.get("end", 0)) - lead, 6)} for s in shots[1:]]
    out["lines"] = [{**l, "start": round(float(l["start"]) - lead, 6), "end": round(float(l["end"]) - lead, 6)}
                    for l in (seg.get("lines") or [])]
    if _f(seg.get("duration")) is not None:
        out["duration"] = round(float(seg["duration"]) - lead, 6)
    out["_dual_lead_in_stripped_sec"] = lead
    return out


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
    本段有畫內台詞（純旁白／內心 VO 段不算）、本段＋同場上一段合計 ≥2 名具名角色、還沒標 dual_lead_in。"""
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
    if not any(has_onscreen_dialogue(s) for s in shots):
        return None  # 沒有畫內對話（純內心／旁白 VO 段）：沒有畫外對戲的人，不建議引子
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
