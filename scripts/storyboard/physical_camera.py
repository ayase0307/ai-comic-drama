#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""物理機位、施力因果鏈與人數／環境鎖（X @LoveUolanda 寫法，噩盡島 EP01 A/B 盲評 2 seed 後收進編譯器）。

來源與證據：references/h3/prompt-formats.md「物理機位與施力因果鏈」、references/storyboard/camera-and-transitions.md。

預設開（R2、R3，盲評傾向有效）：
- R2 物理機位：每段一次 CAMERA_LAW（真實機位、禁數位裁切／變焦、禁遠距旁觀與大繞、重音前框好、釋放時才動）；
  每鏡 Camera 的「NNmm from X metres」重複句（標頭已有焦段距離）換成實體機位句
  「a real camera 1.5 m away, lens …, optical axis …」。作者在 camera_optics.rig_en（或 rig 物件）寫了就用作者的。
- R3 施力因果鏈：action_and_performance.force_chain_en 有寫就把 Motion 換成「Force chain: …」；
  動作鏡（source_action／action_mark／force_chain_en／forbidden_en，或無台詞且有施力動詞）與插入鏡
  在 Motion 後加一行「Forbidden: …」失敗模式（作者寫了 forbidden_en 就只用作者的，沒寫才用預設；最多 5 項、單句不含分號）。

可選、自動觸發（R4，盲評中性，每段 +300–500 字）：
- metadata.cast_lock：true 強制加、false 不加；未寫時在「≥3 名人類角色」或有 absent_objects 時自動加
  CAST RULE（人數與名單、禁多餘人影）＋ENVIRONMENT LOCK（只准場景圖已有的東西、列出畫面中沒有的物件）。
  有群演（extras）的段不寫人數句，只寫環境鎖。

不收：R1 參考圖 ONLY（未驗到）、R5 遮擋接力（只寫在文件，待驗）。
"""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Sequence

CJK_RE = re.compile(r"[\u3400-\u9fff]")

# R2：每段只寫一次（ref2va 放 detailed_description 開頭；REMIX 放第 1 鏡介紹句之後、鏡頭句之前）
CAMERA_LAW_EN = (
    "Camera law: every shot is a real physical camera at the stated height, distance and optical axis; "
    "no digital crop or simulated zoom, no distant spectator view, no wide circling move; "
    "frame each action before its peak and move the camera only on the release, in sync with the body."
)

# Camera 節裡和鏡頭標頭重複的「NNmm from X metres」（標頭已有「MCU (50mm, 1.5m)」）
_OPTICS_FRAG = re.compile(r"(?:,\s*|\s+)\d+\s*mm\s+from\s+[^,;.]+", re.I)
_OPTICS_LEAD = re.compile(r"^\s*\d+\s*mm\s+from\s+[^,;.]+[,;]?\s*", re.I)

# 角度關鍵字 → (鏡頭高度, 光軸)。順序有意義：先判正仰、正俯，再判貼地、低角度、高角度、平視。
_STRAIGHT_UP = re.compile(r"looking straight up|worm'?s[- ]eye|straight up from|正仰|仰視正上", re.I)
_OVERHEAD = re.compile(r"top[- ]down|directly above|overhead|bird'?s[- ]eye|正俯|頂視|頂拍|鳥瞰", re.I)
_GROUND = re.compile(r"ground level|on the ground|at ground|貼地|地面高度", re.I)
_LOW = re.compile(r"low[- ]angle|仰拍|微仰|低角度|仰角", re.I)
_HIGH = re.compile(r"from slightly above|high[- ]angle|from above|微俯|俯拍|俯角", re.I)
_EYE = re.compile(r"eye[- ]level|eye height|平視|平拍", re.I)

# R3：施力動詞（無台詞鏡只要出現一個就視為動作鏡）。刻意不收 lift／flick／fall／drop／pull 這類
# 也常用在眼神、眉毛、光影的字（「flicks her eyes」「eyebrows lift」「gaze falls」會誤判成動作鏡）。
ACTION_VERBS = re.compile(
    r"\b(bit(?:e|es|ing)|clamp\w*|grab\w*|seiz\w*|jerk\w*|yank\w*|toss\w*|throw\w*|threw|thrown|fling\w*|flung|"
    r"slam\w*|strik\w*|struck|punch\w*|kick\w*|swing\w*|swung|hurl\w*|drag\w*|shov\w*|knock\w*|smash\w*|"
    r"stab\w*|slash\w*|leap\w*|lunges?|lunging|pounc\w*|tackl\w*|pinned|pins (?:him|her|them|it))\b",
    re.I,
)
_HAND = re.compile(r"\b(hand|hands|finger|fingers|fingertip|palm|fist|wrist|forearm)\b", re.I)
_INSERT = re.compile(r"\binsert\b", re.I)
INSERT_SIZES = {"INSERT", "INS", "ECU"}

DEFAULT_ACTION_FORBIDDEN = ["no self-levitating", "no unmotivated displacement", "no repeating the same action"]
DEFAULT_INSERT_FORBIDDEN = ["no full-body entry when only the hand is framed", "the hand does not leave and re-enter"]
MAX_FORBIDDEN_ITEMS = 5

_NUM_WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight"}


def _english(text: Any) -> str:
    t = str(text or "").strip()
    return "" if (not t or CJK_RE.search(t)) else t


def _as_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [p.strip() for p in re.split(r"[;\n]", value) if p.strip()]
    if isinstance(value, (list, tuple)):
        return [p.strip() for v in value for p in re.split(r"[;\n]", str(v)) if p.strip()]
    return []


def _metres(dist: str) -> str:
    """'1.5m'／'約 1.5m 微俯'／'4 公尺' → '1.5 m'；讀不到回空字串。"""
    m = re.search(r"([\d.]+)\s*(?:m\b|公尺|米)", str(dist or ""))
    return f"{m.group(1)} m" if m else ""


# ---------------------------------------------------------------------------
# R2 物理機位
# ---------------------------------------------------------------------------

def authored_rig(cam: Dict[str, Any]) -> str:
    """camera_optics.rig_en（字串）或 camera_optics.rig（{height_en, position_en, axis_en, path_en}）。"""
    text = _english(cam.get("rig_en"))
    if text:
        return text.rstrip(" .;")
    rig = cam.get("rig")
    if isinstance(rig, dict):
        parts = [_english(rig.get(k)) for k in ("position_en", "height_en", "axis_en", "path_en")]
        parts = [p.rstrip(" .;") for p in parts if p]
        return ", ".join(parts)
    return ""


def derive_rig(camera_text: str, physical_distance: str = "", distance: str = "") -> str:
    """從 Camera 節與 physical_distance 的角度字推出實體機位句；推不出角度時只寫距離，連距離都沒有回空字串。"""
    probe = f"{camera_text or ''} {physical_distance or ''}"
    height = axis = ""
    if _STRAIGHT_UP.search(probe):
        height, axis = "lens at ground level", "optical axis straight up"
    elif _OVERHEAD.search(probe):
        height, axis = "lens directly overhead", "optical axis straight down"
    else:
        if _GROUND.search(probe):
            height = "lens just above the ground"
        if _LOW.search(probe):
            height = height or "lens below eye line"
            axis = "optical axis tilted up"
        elif _HIGH.search(probe):
            height = height or "lens above eye line"
            axis = "optical axis tilted down"
        elif _EYE.search(probe):
            height = height or "lens at eye height"
            axis = "optical axis level"
        elif height:
            axis = "optical axis level"
    metres = _metres(distance) or _metres(physical_distance)
    bits = [f"a real camera {metres} away" if metres else ("a real camera" if (height or axis) else "")]
    bits += [b for b in (height, axis) if b]
    return ", ".join(b for b in bits if b)


_LOCKED = re.compile(r"\blocked[- ]off\b|\b(?:dolly|dollies|tilts?|pans?|trucks?|pedestals?|cranes?|tracks?)\b", re.I)
_TRAILING_LOCKED = re.compile(r",\s*locked[- ]off(?=\s*[;.]|\s*$)", re.I)


def apply_rig(camera_text: str, rig: str) -> str:
    """把實體機位句寫進 Camera 節：取代與標頭重複的「NNmm from X」；沒有就接在第一個子句後。
    作者的機位句已寫 locked off 或運鏡路徑時，拿掉緊接在後、會互相矛盾的「, locked off」。"""
    cam = (camera_text or "").strip()
    if not rig:
        return cam
    out = _apply_rig(cam, rig)
    if _LOCKED.search(rig):
        at = out.find(rig)
        if at >= 0:
            head, tail = out[:at + len(rig)], out[at + len(rig):]
            out = head + _TRAILING_LOCKED.sub("", tail, count=1)
    return out


def _apply_rig(cam: str, rig: str) -> str:
    if _OPTICS_LEAD.match(cam):
        rest = _OPTICS_LEAD.sub("", cam, count=1)
        return f"{rig[:1].upper()}{rig[1:]}; {rest}" if rest else rig[:1].upper() + rig[1:]
    if _OPTICS_FRAG.search(cam):
        return _OPTICS_FRAG.sub(", " + rig, cam, count=1)
    if ";" in cam:
        first, rest = cam.split(";", 1)
        return f"{first.rstrip(' ,')}, {rig};{rest}"
    return f"{cam.rstrip(' .')}; {rig}"


def camera_with_rig(camera_text: str, cam_optics: Dict[str, Any], distance: str = "") -> str:
    rig = authored_rig(cam_optics) or derive_rig(camera_text, str(cam_optics.get("physical_distance") or ""), distance)
    return apply_rig(camera_text, rig)


# ---------------------------------------------------------------------------
# R3 施力因果鏈＋Forbidden
# ---------------------------------------------------------------------------

def _has_dialogue(shot: Dict[str, Any]) -> bool:
    dlg = shot.get("dialogue_and_audio") or {}
    return bool(dlg.get("has_dialogue") and dlg.get("line_verbatim"))


def is_action_shot(shot: Dict[str, Any], motion: str = "") -> bool:
    act = shot.get("action_and_performance") or {}
    if shot.get("source_action") or shot.get("action_mark"):
        return True
    if _english(act.get("force_chain_en")) or _as_list(act.get("force_chain_en")) or _as_list(act.get("forbidden_en")):
        return True
    return (not _has_dialogue(shot)) and bool(ACTION_VERBS.search(motion or ""))


def is_hand_insert(shot: Dict[str, Any], camera_text: str = "", motion: str = "") -> bool:
    size = str((shot.get("camera_optics") or {}).get("shot_size") or "").strip().upper()
    insert = size in INSERT_SIZES or bool(_INSERT.search(camera_text or ""))
    return insert and bool(_HAND.search(motion or ""))


def force_chain_text(shot: Dict[str, Any]) -> str:
    act = shot.get("action_and_performance") or {}
    raw = act.get("force_chain_en")
    if isinstance(raw, (list, tuple)):
        steps = [_english(x).rstrip(" .;") for x in raw]
        steps = [x for x in steps if x]
        return ", then ".join(steps)
    return _english(raw).rstrip(" ")


def forbidden_items(shot: Dict[str, Any], camera_text: str = "", motion: str = "") -> List[str]:
    """作者寫了 forbidden_en 就只用作者的（不再補語意重疊的預設）；沒寫才依鏡型補預設；明寫空陣列＝都不加。"""
    act = shot.get("action_and_performance") or {}
    authored_raw = act.get("forbidden_en")
    if isinstance(authored_raw, list) and not authored_raw:
        return []
    items = [_english(x).rstrip(" .;") for x in _as_list(authored_raw)]
    items = [x for x in items if x]
    defaults: List[str] = []
    if not items:
        if is_hand_insert(shot, camera_text, motion):
            defaults += DEFAULT_INSERT_FORBIDDEN
        if is_action_shot(shot, motion):
            defaults += DEFAULT_ACTION_FORBIDDEN
    out: List[str] = []
    for item in items + defaults:
        key = item.lower()
        if any(key in o.lower() or o.lower() in key for o in out):
            continue
        out.append(item.replace(";", ","))
        if len(out) >= MAX_FORBIDDEN_ITEMS:
            break
    return out


def forbidden_sentence(items: Sequence[str]) -> str:
    return ("Forbidden: " + ", ".join(items) + ".") if items else ""


def hand_framing_sentence(shot: Dict[str, Any], camera_text: str = "", motion: str = "") -> str:
    if not is_hand_insert(shot, camera_text, motion):
        return ""
    if re.search(r"\bonly\b[^.;]*\b(hand|finger|forearm)", camera_text or "", re.I):
        return ""  # 作者已寫只露手
    return "only the hand and forearm enter frame while the body stays out of frame"


def apply_action_rules(five: Dict[str, str], shot: Dict[str, Any]) -> Dict[str, str]:
    """五小節版：Motion 換成施力鏈（有寫才換）、Motion 後接 Forbidden、插入鏡 Camera 加只露手句。"""
    out = dict(five)
    camera, motion = out.get("camera", ""), out.get("motion", "")
    chain = force_chain_text(shot)
    if chain:
        motion = "Force chain: " + chain
    items = forbidden_items(shot, camera, five.get("motion", ""))
    framing = hand_framing_sentence(shot, camera, five.get("motion", ""))
    if framing:
        camera = camera.rstrip(" .") + "; " + framing
    if items:
        motion = motion.rstrip()
        if not motion.endswith((".", "!", "?")):
            motion += "."
        motion += " " + forbidden_sentence(items)
    out["camera"], out["motion"] = camera, motion
    return out


# ---------------------------------------------------------------------------
# R4 CAST RULE＋ENVIRONMENT LOCK（可選、自動觸發）
# ---------------------------------------------------------------------------

def absent_objects_en(layer2: Dict[str, Any]) -> List[str]:
    found: List[str] = []
    meta = layer2.get("metadata") or {}
    pools: List[Any] = [meta.get("absent_objects_en"), meta.get("absent_objects")]
    for shot in layer2.get("shots") or []:
        blk = shot.get("spatial_blocking") or {}
        pools += [blk.get("absent_objects_en"), blk.get("absent_objects"), shot.get("absent_objects")]
    for pool in pools:
        for item in _as_list(pool):
            t = _english(item).rstrip(" .")
            if t and t.lower() not in (f.lower() for f in found):
                found.append(t)
    return found


def cast_lock_wanted(layer2: Dict[str, Any], humans: int) -> bool:
    flag = (layer2.get("metadata") or {}).get("cast_lock")
    if flag is True:
        return True
    if flag is False:
        return False
    return humans >= 3 or bool(absent_objects_en(layer2))


def _join_names(names: Sequence[str]) -> str:
    names = list(names)
    if len(names) <= 1:
        return "".join(names)
    return ", ".join(names[:-1]) + " and " + names[-1]


def cast_environment_lock(humans: Sequence[str], creatures: Sequence[str], has_extras: bool,
                          absent: Sequence[str], scene_label: str = "<Picture 1>") -> str:
    parts: List[str] = []
    if humans and not has_extras:
        n = len(humans)
        word = _NUM_WORDS.get(n, str(n))
        who = f"exactly {word} {'person' if n == 1 else 'people'}, {_join_names(humans)}"
        if creatures:
            m = len(creatures)
            who += f", and {'exactly one creature' if m == 1 else f'{_NUM_WORDS.get(m, str(m))} creatures'}, {_join_names(creatures)}"
        parts.append(f"Cast rule: {who}; no other people, silhouettes, partial bodies, reflections or shadows of people.")
    env = f"Environment lock: stay in this one location from {scene_label}, with only the objects already in it"
    if absent:
        env += "; not in frame: " + ", ".join(absent)
    parts.append(env + ".")
    return " ".join(parts)


def classify_cast(char_ids: Iterable[str], kind_of) -> Dict[str, List[str]]:
    """kind_of(cid) → 'human'／'creature'／'extras'／'skip'。保留出場順序、去重。"""
    out: Dict[str, List[str]] = {"human": [], "creature": [], "extras": []}
    for cid in char_ids:
        kind = kind_of(cid)
        if kind in out and cid not in out[kind]:
            out[kind].append(cid)
    return out
