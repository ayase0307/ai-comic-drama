# -*- coding: utf-8 -*-
"""鏡頭意圖（shot_intent）與技術選擇理由（choice_why）檢查：validate_storyboard.py 共用。

每一鏡在寫景別、焦距、運鏡之前，必須先寫「這一鏡要讓觀眾看懂或感受到什麼」，
再為每個技術選擇寫一句「為什麼」，而且要扣回意圖。規範見 references/storyboard/shot-intent.md。

錯誤碼：
  I01 缺 shot_intent 或缺必填子欄位
  I02 缺 choice_why 或缺必填理由（有台詞時 line_timing 也必填）
  I03 佔位／空話（TODO、待補、同上、N/A、純標點、太短）
  I04 同段兩鏡以上 shot_intent.audience 完全相同
  I05 同段同一個理由欄位在 ≥3 鏡一字不差（套句），或理由只是把技術值抄一遍
  I06 跨段同一句理由出現在 ≥5 鏡（cross-segment）
"""
from __future__ import annotations

import re
from typing import Dict, List

INTENT_FIELDS = {
    "audience": "觀眾必須看懂／感受到什麼",
    "story_beat": "這一鏡推進的劇情節拍",
    "pov": "誰的視角／觀眾站在誰那邊",
    "emotional_shift": "這一鏡情緒從哪裡變到哪裡",
}
WHY_FIELDS = {
    "shot_size": "景別",
    "lens_distance": "焦距與物距",
    "movement": "運鏡（含固定）",
    "blocking": "人物佔位、畫面位置、視線",
    "background": "背景要露什麼",
}
WHY_DIALOGUE_FIELD = ("line_timing", "台詞與動作的時間關係")

MIN_INTENT_CHARS = 6
MIN_WHY_CHARS = 6

_PLACEHOLDER = re.compile(
    r"^\s*(todo|tbd|n/?a|none|null|-+|—+|待補|待定|同上|同前|略|無|暫無|見上|見前|xxx+|\.+|…+)\s*[。.!！]?\s*$",
    re.IGNORECASE,
)
_HAS_TODO = re.compile(r"TODO|待補|待定", re.IGNORECASE)
_PUNCT = re.compile(r"[\s，。、；：！？,.;:!?\"'「」『』（）()\-—…]+")


def _visible_len(text: str) -> int:
    """中文一字算一，英文一詞算二（約等於一個中文詞的資訊量）。"""
    t = _PUNCT.sub(" ", text or "").strip()
    cjk = len(re.findall(r"[\u3400-\u9fff]", t))
    words = len(re.findall(r"[A-Za-z0-9]+", t))
    return cjk + 2 * words


def _norm(text: str) -> str:
    return _PUNCT.sub("", (text or "").strip().lower())


def _hollow(text, min_chars: int) -> str:
    if not isinstance(text, str) or not text.strip():
        return "空白"
    if _PLACEHOLDER.match(text) or _HAS_TODO.search(text):
        return "佔位字"
    if _visible_len(text) < min_chars:
        return f"太短（少於 {min_chars} 字）"
    return ""


def _has_dialogue(shot: dict) -> bool:
    dlg = shot.get("dialogue_and_audio") or {}
    return bool(dlg.get("has_dialogue") and (dlg.get("line_verbatim") or "").strip())


def _tech_values(shot: dict) -> Dict[str, str]:
    cam = shot.get("camera_optics") or {}
    return {
        "shot_size": str(cam.get("shot_size") or ""),
        "lens_distance": f"{cam.get('focal_length') or ''}{cam.get('physical_distance') or ''}",
        "movement": str(cam.get("movement") or ""),
    }


def shot_intent_errors(shot: dict, sid: str) -> List[str]:
    """單鏡：I01–I03，以及理由只是抄技術值（I05）。"""
    errors: List[str] = []
    intent = shot.get("shot_intent")
    if not isinstance(intent, dict):
        errors.append(f"[{sid} I01 缺鏡頭意圖] 沒有 shot_intent。先寫這一鏡要讓觀眾看懂／感受到什麼，"
                      "再決定景別與運鏡（references/storyboard/shot-intent.md）。")
    else:
        for key, label in INTENT_FIELDS.items():
            why = _hollow(intent.get(key), MIN_INTENT_CHARS)
            if why:
                code = "I01 缺鏡頭意圖" if why == "空白" else "I03 意圖是空話"
                errors.append(f"[{sid} {code}] shot_intent.{key}（{label}）{why}。")
    reasons = shot.get("choice_why")
    required = dict(WHY_FIELDS)
    if _has_dialogue(shot):
        required[WHY_DIALOGUE_FIELD[0]] = WHY_DIALOGUE_FIELD[1]
    if not isinstance(reasons, dict):
        errors.append(f"[{sid} I02 缺選擇理由] 沒有 choice_why。景別、焦距物距、運鏡、佔位、背景"
                      f"{'、台詞時機' if _has_dialogue(shot) else ''}都要各寫一句為什麼，且要扣回鏡頭意圖。")
        return errors
    tech = _tech_values(shot)
    for key, label in required.items():
        text = reasons.get(key)
        why = _hollow(text, MIN_WHY_CHARS)
        if why:
            code = "I02 缺選擇理由" if why == "空白" else "I03 理由是空話"
            errors.append(f"[{sid} {code}] choice_why.{key}（{label}）{why}。")
            continue
        val = _norm(tech.get(key, ""))
        if val and _norm(text) in (val, val + "鏡頭", "因為" + val):
            errors.append(f"[{sid} I05 理由抄技術值] choice_why.{key} 只是把「{tech.get(key)}」再寫一遍；"
                          "要寫這個選擇讓觀眾看到什麼、和鏡頭意圖有什麼關係。")
    return errors


def segment_intent_errors(shots: List[dict]) -> List[str]:
    """同段：I04 意圖重複、I05 同一理由套在 ≥3 鏡。"""
    errors: List[str] = []
    seen: Dict[str, str] = {}
    for idx, s in enumerate(shots, 1):
        sid = s.get("shot_id", f"SH{idx:02d}")
        aud = _norm(((s.get("shot_intent") or {}) if isinstance(s.get("shot_intent"), dict) else {}).get("audience", ""))
        if aud and len(aud) >= 4:
            if aud in seen:
                errors.append(f"[{sid} I04 意圖重複] shot_intent.audience 與 {seen[aud]} 一字不差；"
                              "兩鏡要表達同一件事就該合併，否則寫出這一鏡多給了觀眾什麼。")
            else:
                seen[aud] = sid
    for key in list(WHY_FIELDS) + [WHY_DIALOGUE_FIELD[0]]:
        bucket: Dict[str, List[str]] = {}
        for idx, s in enumerate(shots, 1):
            r = s.get("choice_why") if isinstance(s.get("choice_why"), dict) else {}
            val = _norm(r.get(key, "") if isinstance(r.get(key), str) else "")
            if len(val) >= 4:
                bucket.setdefault(val, []).append(s.get("shot_id", f"SH{idx:02d}"))
        for val, where in bucket.items():
            if len(where) >= 3:
                errors.append(f"[{where[0]} I05 理由套句] choice_why.{key} 在 {len(where)} 鏡一字不差（{', '.join(where)}）；"
                              "每一鏡的理由要從自己的意圖推出來。")
    return errors


def cross_segment_intent_errors(datas: List[dict]) -> List[str]:
    """跨段：I06 同一句理由或意圖出現在 ≥5 鏡。"""
    counts: Dict[str, List[str]] = {}
    for d in datas:
        seg = d.get("segment_id") or d.get("scene_id") or "SEG"
        for s in d.get("shots", []) or []:
            if not isinstance(s, dict):
                continue
            pool = []
            if isinstance(s.get("choice_why"), dict):
                pool += [(f"choice_why.{k}", v) for k, v in s["choice_why"].items() if isinstance(v, str)]
            if isinstance(s.get("shot_intent"), dict):
                pool += [(f"shot_intent.{k}", v) for k, v in s["shot_intent"].items() if isinstance(v, str)]
            for field, v in pool:
                n = _norm(v)
                if len(n) >= 6:
                    counts.setdefault(f"{field}|{n}", []).append(f"{seg}:{s.get('shot_id', '')}")
    errors = []
    for key, where in counts.items():
        if len(where) >= 5:
            field = key.split("|", 1)[0]
            errors.append(f"[I06 跨段意圖套句] {field} 同一句出現在 {len(where)} 鏡（{', '.join(where[:5])}…）；"
                          "鏡頭意圖與理由不准批量複製。")
    return errors
