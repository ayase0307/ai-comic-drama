# -*- coding: utf-8 -*-
"""PR-15c：導演層 lint（階段 4，全部是 warning）。

參考 24frames.art 的鏡頭語言判斷（自己的話改寫，未整段照搬），規則只看分鏡已有欄位，缺欄位就略過：
  D01 新地點缺建立鏡：shot.location（或 camera_optics.location）與上一鏡不同，且該鏡景別不是遠景／全景。
  D02 對白越軸：連續對白鏡同一說話者的畫面側（camera_optics.screen_side=left|right）翻面。
  D03 反轉／壞消息後缺反應鏡：shot_intent 含反轉類詞，下一鏡不是 CU／MCU／OTS 反應鏡。
  D04 視線匹配缺被看物：shot_intent 寫「看向／盯著」，但是本段最後一鏡，或下一鏡沒有交代被看物。
  D05 段間接縫（lint_segment_seam）：上一段尾鏡與下一段首鏡景別相同且都是固定，建議動作剪輯或遮擋轉場。
"""
from __future__ import annotations

import re
from typing import List

WIDE_SIZES = {"ELS", "EWS", "XLS", "LS", "WS", "MLS"}
REACTION_SIZES = {"CU", "MCU", "ECU", "OTS", "OTS_CU", "BCU"}
_TWIST = re.compile(r"反轉|揭穿|噩耗|壞消息|死訊|真相|背叛|twist|bad news|betray", re.I)
_LOOK = re.compile(r"看向|望向|盯著|注視|看見|looks? (?:at|toward)|stares? at", re.I)
_REACT = re.compile(r"反應|reaction|聽到|得知")
_OBJECT = re.compile(r"被看|所見|畫面內容|插入|insert|pov|主觀|看到的是|物件|object", re.I)


def _cam(s: dict) -> dict:
    return s.get("camera_optics") or {}


def _size(s: dict) -> str:
    return str(_cam(s).get("shot_size", "")).strip().upper()


def _loc(s: dict) -> str:
    return str(s.get("location") or _cam(s).get("location") or "").strip()


def _text(s: dict) -> str:
    it = s.get("shot_intent") or {}
    return " ".join(str(it.get(k, "")) for k in ("audience", "story_beat", "emotional_shift", "pov"))


def _speaker(s: dict) -> str:
    da = s.get("dialogue_and_audio") or {}
    d = da.get("dialogue")
    if isinstance(d, dict):
        return str(d.get("speaker", "")).strip()
    return str(da.get("speaker", "")).strip()


def lint_director(shots: List[dict]) -> List[str]:
    out: List[str] = []
    for i, s in enumerate(shots):
        sid = s.get("shot_id", f"SH{i + 1:02d}")
        prev = shots[i - 1] if i else None
        nxt = shots[i + 1] if i + 1 < len(shots) else None
        loc = _loc(s)
        if prev is not None and loc and _loc(prev) and loc != _loc(prev) and _size(s) not in WIDE_SIZES:
            out.append(f"[{sid} 新地點缺建立鏡] 地點由「{_loc(prev)}」換到「{loc}」，首鏡景別 {_size(s) or '未填'} 不是遠景／全景；"
                       "建議先給一個建立鏡，或確認觀眾看得懂換景（D01）")
        side, pside = _cam(s).get("screen_side"), _cam(prev).get("screen_side") if prev else None
        if prev is not None and side and pside and side != pside and _speaker(s) and _speaker(s) == _speaker(prev):
            out.append(f"[{sid} 對白越軸] 說話者 {_speaker(s)} 畫面側由 {pside} 翻到 {side}，疑似跨 180 度軸線；"
                       "中間插入中立鏡或改回同側（D02）")
        text = _text(s)
        if nxt is not None and _TWIST.search(text) and _size(nxt) not in REACTION_SIZES and not _REACT.search(_text(nxt)):
            out.append(f"[{sid} 反轉後缺反應鏡] 本鏡是反轉／壞消息，下一鏡 {nxt.get('shot_id', '')} 不是 CU／MCU／OTS 反應鏡；"
                       "建議補聽者反應（D03）")
        if _LOOK.search(text):
            if nxt is None:
                out.append(f"[{sid} 視線匹配缺被看物] 角色在看某物但這是本段最後一鏡，被看物沒有交代（D04）")
            elif not _OBJECT.search(_text(nxt)) and _size(nxt) in REACTION_SIZES | {""} and not nxt.get("shot_intent"):
                out.append(f"[{sid} 視線匹配缺被看物] 下一鏡沒有說明被看物（D04）")
    return out


def lint_segment_seam(prev_last: dict, next_first: dict) -> List[str]:
    """D05：兩段接縫。回傳 warning 清單。"""
    if not prev_last or not next_first:
        return []
    a, b = _cam(prev_last), _cam(next_first)
    static = ("static", "固定", "", "fixed")
    if _size(prev_last) and _size(prev_last) == _size(next_first) \
            and str(a.get("movement", "static")).strip().lower() in static \
            and str(b.get("movement", "static")).strip().lower() in static \
            and not a.get("move_preset") and not b.get("move_preset"):
        return [f"[段間接縫] 上一段尾鏡與下一段首鏡景別同為 {_size(prev_last)} 且都固定，接縫會像跳切；"
                "建議動作剪輯（動作跨段延續）或前景遮擋轉場（D05）"]
    return []
