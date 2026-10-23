#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""對白括注的音訊類型關鍵字表（sync_script 與 validate_structure 共用，議題 #28）。

- offscreen（O.S.）：角色在場但未入鏡說話；不是旁白，不算畫外音佔比，也不送 H3 對嘴。
- voiceover（V.O.）：旁白／內心獨白；計入 30% 硬上限。
- phone：電話／手機音。
"""
from __future__ import annotations

import re
from typing import Optional

OFFSCREEN_KEYWORDS = ("畫外音", "画外音", "畫外", "画外", "腦內", "脑内", "O.S.", "OS")
VOICEOVER_KEYWORDS = ("內心獨白", "内心独白", "內心", "内心", "旁白", "V.O.", "VO")
PHONE_KEYWORDS = ("電話", "电话", "手機", "手机")


def _has(note: str, keywords) -> bool:
    upper = note.upper()
    for k in keywords:
        if k.isascii():
            if re.search(r"(?<![A-Z])" + re.escape(k.upper()) + r"(?![A-Z])", upper):
                return True
        elif k in note:
            return True
    return False


def classify_note(note: str) -> Optional[str]:
    """回傳 offscreen／voiceover／phone；括注沒有關鍵字回 None。
    O.S. 優先於 V.O.（「腦內 O.S.」＝在場但看不見的角色）；明寫 V.O./旁白/內心獨白才算旁白。"""
    if not note:
        return None
    if _has(note, ("O.S.", "OS", "畫外音", "画外音", "畫外", "画外")):
        return "offscreen"
    if _has(note, VOICEOVER_KEYWORDS):
        return "voiceover"
    if _has(note, ("腦內", "脑内")):
        return "voiceover"
    if _has(note, PHONE_KEYWORDS):
        return "phone"
    return None
