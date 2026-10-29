# -*- coding: utf-8 -*-
"""鏡間銜接與佔位延續 lint（D15–D21，全部預設警告）。

規則與證據等級見 `references/storyboard/shot-transitions.md`（單一入口）。本模組只看 Layer 2／編譯後分段的
結構欄位（`shots[].camera_optics`、`shots[].cut_in`、`shots[].positions`、段層 `seam_in`／`entry_state`／
`exit_state`），不判斷畫面；畫面是否真的接得上屬階段 6 驗收（`h3d qa --continuity`）。

啟用條件（向下相容）：
  - D15 只在下一段 `seam_in=cut`、D18 只在 `seam_in=cont` 時跑；
  - D16／D17／D19／D20 只在該段「有規劃鏡間銜接」時跑：段落有 `seam_in`／`entry_state`／`exit_state`，
    或任一鏡有 `cut_in.type`／`positions`。舊專案沒有這些欄位 → 一條都不報；
  - D21 看逐鏡 `positions`；段層 `positions`（REMIX 綁定既有欄位）只在該段已啟用時才看。

規則：
  D15 CUT 段縫差異不足：上段末鏡 vs 本段首鏡，主體不同／景別差 ≥2 級／角度差 ≥90° 三項都證明不了
      （Toonflow §A7.3 閘門；角度要 `camera_optics.azimuth_deg` 兩邊都有才算數）。
  D16 同主體相鄰鏡差異不足：段內相鄰兩鏡主體相同，景別差 <2 級且角度差 <30°（或角度未填）。
  D17 連 3 鏡同景別：段內連續 3 鏡同一景別級（主體輪替的正反打不算）。
  D18 CONT 段縫不符：缺 exit_state／entry_state、兩者共同欄位不一致、上段末 1 秒有台詞、首鏡景別和上段末鏡不同、
      entry_state 寫「承接上一段／同上」這類指代。
  D19 台詞跨切點沒有 `<scenetrans>`：speech_window 跨過切點，或 L_CUT／J_CUT 台詞，兩側文字都沒有 `<scenetrans>`。
  D20 段內相鄰鏡站位對調／漂移沒寫走位：共同角色 `order_lr` 左右對調、`world` 世界位置改變，或硬切同主體
      `screen_x` 差 >15% 畫寬，且後一鏡沒寫走位／越軸理由。
  D21 多人鏡缺背景錨點：positions ≥2 人，有人沒寫 `background_anchor`。

豁免：沿用段落 `metadata.staging_waivers`（code＋使用者原話 quote），由呼叫端處理。
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

CODES = ("D15", "D16", "D17", "D18", "D19", "D20", "D21")
TITLES = {
    "D15": "CUT 段縫差異不足",
    "D16": "同主體相鄰鏡差異不足",
    "D17": "連 3 鏡同景別",
    "D18": "CONT 段縫不符",
    "D19": "台詞跨切點沒有 <scenetrans>",
    "D20": "相鄰鏡站位對調或漂移沒寫走位",
    "D21": "多人鏡缺背景錨點",
}
EVIDENCE = {
    "D15": "D（Toonflow-app 規則，無實測）",
    "D16": "A/B（30° 規則、Dmytryk；景別跳 2 級為 B）",
    "D17": "C/D（Shanyin 拉片統計＋DirectorSKILL 等規則；AI 端無實測）",
    "D18": "C/D（manju-laoli 定格承接、zenstory 尾幀實測；本 repo 未驗，見 E1）",
    "D19": "B/D（H3 開源格式 `<scenetrans>`；未在本 repo 實測）",
    "D20": "A/B（180° 規則）；≤15% 畫寬為 D（DirectorSKILL）",
    "D21": "C（manju-laoli 背景錨點鎖，作者自報）",
}

CUT_TYPES = ("hard", "match_action", "eyeline", "reaction", "insert", "scene_change", "cont")
SEAM_TYPES = ("cut", "cont")
STATE_KEYS = ("position", "facing", "distance", "momentum", "damage", "holding", "background_anchor", "light", "sound")

SIZE_LEVEL = {
    "EWS": 0, "ELS": 0, "XLS": 0, "XWS": 0,
    "WS": 1, "LS": 1, "FS": 1,
    "MLS": 2, "MWS": 2, "MFS": 2,
    "MS": 3, "OTS_MS": 3, "OTS": 3,
    "MCU": 4,
    "CU": 5, "OTS_CU": 5, "BCU": 5,
    "ECU": 6, "XCU": 6,
}
SCREEN_X_TOLERANCE = 0.15
TIME_TOL = 0.05

# 交接塊／entry_state 不准寫指代（模型看不到上一段）：Toonflow「禁止寫延续上一段／同上」
VAGUE_CARRY = re.compile(
    r"承接上一段|承接上段|延續上一段|延续上一段|接續上一段|同上一段|同上|如上|與上一段相同|和上一段一樣"
    r"|same as (?:the )?(?:previous|above|before|last)|as (?:in|before|above) (?:the )?(?:previous|last)?\s*(?:segment|clip|shot)?"
    r"|continu\w* from the previous|carried over from the previous|from the previous (?:segment|clip)",
    re.I)
# 走位／越軸理由：後一鏡有寫就不報 D20
BLOCKING_CHANGE = re.compile(
    r"走位|走到|走向|繞到|繞過|換位|移到|越軸|過軸|軸上|中性鏡|轉身|起身|交換位置|互換"
    r"|\bwalks?\b|\bcross(?:es|ing)?\b|\bcircles?\b|\bmoves? (?:to|toward|around|behind|past)\b|\bsteps? (?:to|around|behind|past)\b"
    r"|\bswap(?:s|ped)?\b|\btrade places\b|\bturns? around\b|\bon[- ]axis\b|\bneutral (?:shot|angle)\b|\baxis\b", re.I)
SCENETRANS = "<scenetrans>"


# ---------------------------------------------------------------------------
# 欄位讀取
# ---------------------------------------------------------------------------
def _cam(shot: Dict[str, Any]) -> Dict[str, Any]:
    return shot.get("camera_optics") or {}


def size_level(shot: Optional[Dict[str, Any]]) -> Optional[int]:
    if not shot:
        return None
    return SIZE_LEVEL.get(str(_cam(shot).get("shot_size") or "").strip().upper())


def _is_ots(shot: Dict[str, Any]) -> bool:
    return str(_cam(shot).get("shot_size") or "").strip().upper().startswith("OTS")


def azimuth(shot: Optional[Dict[str, Any]]) -> Optional[float]:
    if not shot:
        return None
    value = _cam(shot).get("azimuth_deg")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) % 360.0


def angle_diff(a: Dict[str, Any], b: Dict[str, Any]) -> Optional[float]:
    x, y = azimuth(a), azimuth(b)
    if x is None or y is None:
        return None
    d = abs(x - y) % 360.0
    return min(d, 360.0 - d)


def subjects(shot: Optional[Dict[str, Any]]) -> Tuple[str, ...]:
    if not shot:
        return ()
    ids = shot.get("visual_subject_ids") or shot.get("character_ids") or []
    return tuple(sorted(str(x) for x in ids if x))


def cut_type(shot: Optional[Dict[str, Any]]) -> str:
    cut = (shot or {}).get("cut_in")
    if isinstance(cut, dict):
        return str(cut.get("type") or "").strip().lower()
    return ""


def cut_motivation(shot: Optional[Dict[str, Any]]) -> str:
    cut = (shot or {}).get("cut_in")
    return str(cut.get("motivation") or "") if isinstance(cut, dict) else ""


def seam_in(seg: Optional[Dict[str, Any]]) -> str:
    return str((seg or {}).get("seam_in") or "").strip().lower()


def _nonempty_state(value: Any) -> bool:
    return isinstance(value, dict) and any(v not in (None, "", {}, []) for v in value.values())


def shot_positions(shot: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [p for p in shot.get("positions") or [] if isinstance(p, dict) and p.get("id")]


def transition_planned(seg: Dict[str, Any]) -> bool:
    """段落是否已進入鏡間銜接規劃（有任一新欄位的有效值）。舊專案回 False → D16／D17／D19／D20 不跑。"""
    if seam_in(seg) or _nonempty_state(seg.get("entry_state")) or _nonempty_state(seg.get("exit_state")):
        return True
    for shot in seg.get("shots") or []:
        if isinstance(shot, dict) and (cut_type(shot) or shot_positions(shot)):
            return True
    return False


def _shots(seg: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [s for s in (seg or {}).get("shots") or [] if isinstance(s, dict)]


def _sid(seg: Dict[str, Any]) -> str:
    return str(seg.get("segment_id") or seg.get("id") or "segment")


def _shot_label(shot: Dict[str, Any], idx: int) -> str:
    return str(shot.get("shot_id") or f"SH{idx:02d}")


def _duration(seg: Dict[str, Any]) -> Optional[float]:
    meta = seg.get("metadata") or {}
    for key in ("effective_duration_sec", "target_duration_sec"):
        try:
            if meta.get(key) is not None:
                return float(meta[key])
        except (TypeError, ValueError):
            pass
    shots = _shots(seg)
    try:
        return float(shots[-1]["end_time"]) if shots else None
    except (KeyError, TypeError, ValueError):
        return None


def _window(shot: Dict[str, Any]) -> Optional[Tuple[float, float]]:
    win = (shot.get("dialogue_and_audio") or {}).get("speech_window")
    if not isinstance(win, dict):
        return None
    try:
        start, end = float(win["start"]), float(win["end"])
    except (KeyError, TypeError, ValueError):
        return None
    if str(win.get("unit") or "segment_seconds") == "shot_seconds":
        base = float(shot.get("start_time") or 0)
        start, end = start + base, end + base
    return start, end


def _times(shot: Dict[str, Any]) -> Optional[Tuple[float, float]]:
    try:
        return float(shot["start_time"]), float(shot["end_time"])
    except (KeyError, TypeError, ValueError):
        return None


def _shot_text(shot: Dict[str, Any]) -> str:
    keep = {k: shot.get(k) for k in ("dialogue_and_audio", "action_and_performance", "spatial_blocking", "cut_in")}
    return json.dumps(keep, ensure_ascii=False)


def _prompt_blocks(seg: Dict[str, Any]) -> List[str]:
    prompt = str(seg.get("h3_prompt") or "")
    if not prompt:
        return []
    parts = re.split(r"\[Shot\s+\d+\]", prompt, flags=re.I)
    return parts[1:]


def normalize_state(state: Any) -> Dict[str, Dict[str, str]]:
    """{who: {key: value}}；扁平寫法（直接 position／facing…）視為 who='*'。"""
    if not isinstance(state, dict):
        return {}
    if any(k in STATE_KEYS for k in state):
        return {"*": {str(k): str(v).strip() for k, v in state.items() if str(v or "").strip()}}
    out: Dict[str, Dict[str, str]] = {}
    for who, value in state.items():
        if isinstance(value, dict):
            out[str(who)] = {str(k): str(v).strip() for k, v in value.items() if str(v or "").strip()}
    return out


def _norm_value(text: str) -> str:
    return re.sub(r"[\s，,。.;；、]+", " ", str(text).lower()).strip()


def state_text(state: Any) -> str:
    return json.dumps(state, ensure_ascii=False) if state else ""


def last_second_has_dialogue(seg: Dict[str, Any]) -> bool:
    """與編譯器 final_second_has_dialogue 同規則：speech_window 落進最後 1 秒，或末鏡有台詞卻沒有窗口。"""
    shots = _shots(seg)
    dur = _duration(seg)
    if not shots or dur is None:
        return False
    tail = dur - 1.0
    for shot in shots:
        dlg = shot.get("dialogue_and_audio") or {}
        win = _window(shot)
        if win is None:
            if dlg.get("has_dialogue") and shot is shots[-1]:
                return True
            continue
        if win[1] > tail + TIME_TOL:
            return True
    return False


# ---------------------------------------------------------------------------
# 規則
# ---------------------------------------------------------------------------
Finding = Dict[str, Any]


def _f(code: str, seg: Dict[str, Any], message: str, shot: Optional[int] = None) -> Finding:
    where = f" Shot{shot}" if shot else ""
    return {"code": code, "level": "warning", "shot": shot,
            "message": f"[{code}: {TITLES[code]}] {_sid(seg)}{where}：{message}"}


def lint_cut_seam(prev: Dict[str, Any], seg: Dict[str, Any]) -> List[Finding]:
    """D15：seam_in=cut 時，上段末鏡 vs 本段首鏡至少一項實質差異。"""
    if seam_in(seg) != "cut":
        return []
    a, b = (_shots(prev) or [None])[-1], (_shots(seg) or [None])[0]
    if not a or not b:
        return []
    sa, sb = subjects(a), subjects(b)
    if sa and sb and sa != sb:
        return []
    la, lb = size_level(a), size_level(b)
    if la is not None and lb is not None and abs(la - lb) >= 2:
        return []
    ang = angle_diff(a, b)
    if ang is not None and ang >= 90:
        return []
    facts = [f"主體{'相同' if sa and sa == sb else '未填 character_ids'}",
             f"景別 {_cam(a).get('shot_size') or '?'}→{_cam(b).get('shot_size') or '?'}（差 "
             f"{abs(la - lb) if la is not None and lb is not None else '?'} 級）",
             f"角度差 {f'{ang:.0f}°' if ang is not None else '未知（azimuth_deg 未填）'}"]
    return [_f("D15", seg, f"上段 {_sid(prev)} 末鏡 → 本段首鏡是 CUT 段縫，但{'、'.join(facts)}；"
                           "三選一：換主體／景別差 ≥2 級／角度差 ≥90°，只改本段首鏡的主體、景別、角度或構圖，不改劇情；"
                           "上段結尾不定格、留 0.5 s（shot-transitions.md §3）", 1)]


def lint_cont_seam(prev: Optional[Dict[str, Any]], seg: Dict[str, Any]) -> List[Finding]:
    """D18：seam_in=cont 時的交接檢查。prev 可為 None（上一段不在這次輸入），此時只查本段。"""
    if seam_in(seg) != "cont":
        return []
    out: List[Finding] = []
    entry = seg.get("entry_state")
    if not _nonempty_state(entry):
        out.append(_f("D18", seg, "CONT 段縫沒有 entry_state（位置、朝向、距離、動量、傷損、握持、背景錨點）；"
                                  "編譯器無法寫交接塊，模型會從參考圖站姿重新起手"))
    vague = VAGUE_CARRY.search(state_text(entry) + " " + state_text(seg.get("entry_state_en")))
    if vague:
        out.append(_f("D18", seg, f"entry_state 寫了「{vague.group(0)}」——模型看不到上一段，交接塊要逐項寫成絕對狀態"
                                  "（Toonflow：禁止「延續上一段／同上」）"))
    if prev is None:
        return out
    exit_state = prev.get("exit_state")
    if not _nonempty_state(exit_state):
        out.append(_f("D18", seg, f"上段 {_sid(prev)} 沒有 exit_state，無法核對 CONT 交接"))
    elif _nonempty_state(entry):
        ex, en = normalize_state(exit_state), normalize_state(entry)
        diffs: List[str] = []
        for who in ex:
            if who not in en:
                if who != "*" and "*" not in en:
                    diffs.append(f"{who} 沒有入口狀態")
                continue
            for key, value in ex[who].items():
                if key not in en[who]:
                    diffs.append(f"{who if who != '*' else ''}{'.' if who != '*' else ''}{key} 入口沒寫（出口：{value}）")
                elif _norm_value(en[who][key]) != _norm_value(value):
                    diffs.append(f"{who if who != '*' else ''}{'.' if who != '*' else ''}{key}：出口「{value}」≠ 入口「{en[who][key]}」")
        if diffs:
            out.append(_f("D18", seg, f"上段 {_sid(prev)} exit_state 和本段 entry_state 不符：{'；'.join(diffs[:6])}"
                                      f"{'…' if len(diffs) > 6 else ''}"))
    if last_second_has_dialogue(prev):
        out.append(_f("D18", seg, f"上段 {_sid(prev)} 最後 1 秒有台詞；CONT 段縫要末 1 秒定格無台詞（剪輯會剪掉這 1 秒）"))
    a, b = (_shots(prev) or [None])[-1], (_shots(seg) or [None])[0]
    la, lb = size_level(a), size_level(b)
    if la is not None and lb is not None and la != lb:
        out.append(_f("D18", seg, f"CONT 段縫首鏡景別 {_cam(b).get('shot_size')} 和上段末鏡 {_cam(a).get('shot_size')} 不同；"
                                  "同機位技術分段要同景別起手（要換景別就改成 seam_in=cut）", 1))
    return out


def lint_within(seg: Dict[str, Any]) -> List[Finding]:
    """D16／D17／D19／D20：段內相鄰鏡（只在 transition_planned 時跑）。"""
    if not transition_planned(seg):
        return []
    out: List[Finding] = []
    shots = _shots(seg)
    blocks = _prompt_blocks(seg)
    for i in range(1, len(shots)):
        a, b = shots[i - 1], shots[i]
        idx = i + 1
        # D16
        sa, sb = subjects(a), subjects(b)
        ctype = cut_type(b)
        if sa and sa == sb and ctype not in ("cont",):
            la, lb = size_level(a), size_level(b)
            ang = angle_diff(a, b)
            ots_flip = _is_ots(a) != _is_ots(b)
            size_ok = la is not None and lb is not None and abs(la - lb) >= 2
            angle_ok = (ang is not None and ang >= 30) or ots_flip
            if la is not None and lb is not None and not size_ok and not angle_ok:
                out.append(_f("D16", seg, f"{_shot_label(a, i)}→{_shot_label(b, idx)} 同主體，景別 "
                                          f"{_cam(a).get('shot_size')}→{_cam(b).get('shot_size')}（差 {abs(la - lb)} 級），"
                                          f"角度差 {f'{ang:.0f}°' if ang is not None else '未知（azimuth_deg 未填）'}；"
                                          "同主體要角度 ≥30° 或景別跳 ≥2 級，只是換距離就改用運鏡、不切", idx))
        # D20 站位
        out.extend(_lint_positions_pair(seg, a, b, idx))
    # D17
    for i in range(2, len(shots)):
        trio = shots[i - 2:i + 1]
        levels = [size_level(s) for s in trio]
        if None in levels or len(set(levels)) != 1:
            continue
        subs = [subjects(s) for s in trio]
        alternating = all(subs) and subs[0] == subs[2] and subs[0] != subs[1]
        if alternating:
            continue  # 正反打主體輪替，同景別是慣例
        out.append(_f("D17", seg, f"{'、'.join(_shot_label(s, i - 1 + k) for k, s in enumerate(trio))} 連 3 鏡都是 "
                                  f"{_cam(trio[0]).get('shot_size')}；中間換一級景別或改成運鏡", i + 1))
    # D19
    for i, shot in enumerate(shots):
        dlg = shot.get("dialogue_and_audio") or {}
        if not dlg.get("has_dialogue"):
            continue
        win, times = _window(shot), _times(shot)
        bridge = str(dlg.get("audio_bridge") or "").upper()
        crosses_out = (i + 1 < len(shots)) and (bridge == "L_CUT" or (win and times and win[1] > times[1] + TIME_TOL))
        crosses_in = i > 0 and (bridge == "J_CUT" or (win and times and win[0] < times[0] - TIME_TOL))
        if not (crosses_out or crosses_in):
            continue
        other = shots[i + 1] if crosses_out else shots[i - 1]
        other_idx = i + 1 if crosses_out else i - 1
        texts = [_shot_text(shot), _shot_text(other)]
        if len(blocks) == len(shots):
            texts += [blocks[i], blocks[other_idx]]
        if not any(SCENETRANS in t for t in texts):
            out.append(_f("D19", seg, f"{_shot_label(shot, i + 1)} 的台詞跨過切點（{'L_CUT' if bridge == 'L_CUT' else 'J_CUT' if bridge == 'J_CUT' else 'speech_window 越過鏡頭邊界'}），"
                                      "兩側都沒有 <scenetrans>；在兩鏡五小節 sound 寫 <scenetrans> 並說明 "
                                      "continues seamlessly across the cut，台詞只說一次", i + 1))
    return out


def _lint_positions_pair(seg: Dict[str, Any], a: Dict[str, Any], b: Dict[str, Any], idx: int) -> List[Finding]:
    pa = {str(p["id"]): p for p in shot_positions(a)}
    pb = {str(p["id"]): p for p in shot_positions(b)}
    shared = [x for x in pa if x in pb]
    if not shared:
        return []
    moved_text = " ".join([cut_motivation(b), json.dumps(b.get("spatial_blocking") or {}, ensure_ascii=False),
                           json.dumps(((b.get("action_and_performance") or {}).get("five_part_en") or {}).get("motion", ""),
                                      ensure_ascii=False),
                           " ".join(str(pb[x].get("move") or "") for x in shared)])
    if BLOCKING_CHANGE.search(moved_text) or str(_cam(b).get("axis_side") or "").lower() in ("on_axis", "neutral", "axis"):
        return []
    out: List[Finding] = []

    def order_of(pos: Dict[str, Dict[str, Any]]) -> List[str]:
        items = [(p.get("order_lr"), x) for x, p in pos.items() if x in shared
                 and isinstance(p.get("order_lr"), int) and not isinstance(p.get("order_lr"), bool)]
        return [x for _, x in sorted(items)]

    oa, ob = order_of(pa), order_of(pb)
    if len(oa) >= 2 and set(oa) == set(ob) and oa != ob:
        out.append(_f("D20", seg, f"共同角色左到右由 {', '.join(oa)} 變成 {', '.join(ob)}，後一鏡沒寫走位或越軸理由；"
                                  "同一軸線內畫面左右不換，要換先插軸上鏡或寫畫內轉折（cut_in.motivation／positions[].move）", idx))
    world = [x for x in shared if pa[x].get("world") and pb[x].get("world")
             and _norm_value(pa[x]["world"]) != _norm_value(pb[x]["world"])]
    if world:
        changes = "；".join(f"{x}: {pa[x]['world']}→{pb[x]['world']}" for x in world)
        out.append(_f("D20", seg, f"{', '.join(world)} 的世界位置改變（{changes}），"
                                  "沒寫走位；換機位只重算畫面座標，世界座標不變", idx))
    if cut_type(b) in ("hard", "match_action") and subjects(a) and subjects(a) == subjects(b):
        drift = []
        for x in shared:
            xa, xb = pa[x].get("screen_x"), pb[x].get("screen_x")
            if isinstance(xa, (int, float)) and isinstance(xb, (int, float)) and not isinstance(xa, bool) \
                    and not isinstance(xb, bool) and abs(float(xa) - float(xb)) > SCREEN_X_TOLERANCE:
                drift.append(f"{x} {float(xa):.2f}→{float(xb):.2f}")
        if drift:
            out.append(_f("D20", seg, f"硬切同主體，畫面位置差超過 15% 畫寬（{'；'.join(drift)}）；"
                                      "A 末幀和 B 首幀主體位置要接近，景別或角度才是要故意破的那一項", idx))
    return out


def lint_background_anchor(seg: Dict[str, Any]) -> List[Finding]:
    """D21：多人鏡 positions 缺 background_anchor。逐鏡 positions 一律看；段層 positions 只在已啟用時看。"""
    out: List[Finding] = []
    any_shot_level = False
    for i, shot in enumerate(_shots(seg), 1):
        pos = shot_positions(shot)
        if pos:
            any_shot_level = True
        if len(pos) >= 2:
            missing = [str(p["id"]) for p in pos if not str(p.get("background_anchor") or "").strip()]
            if missing:
                out.append(_f("D21", seg, f"{', '.join(missing)} 沒寫 background_anchor（身後最可辨識的背景物）；"
                                          "站位漂移常是人物背後的東西變了，每人寫一個具體背景物，不寫「背景不變」", i))
    if not any_shot_level and transition_planned(seg):
        pos = [p for p in seg.get("positions") or [] if isinstance(p, dict) and p.get("id")]
        if len(pos) >= 2:
            missing = [str(p["id"]) for p in pos if not str(p.get("background_anchor") or "").strip()]
            if missing:
                out.append(_f("D21", seg, f"段層 positions 的 {', '.join(missing)} 沒寫 background_anchor"))
    return out


def lint_segment(seg: Dict[str, Any], prev: Optional[Dict[str, Any]] = None) -> List[Finding]:
    """單段（含與 prev 的段縫）。prev＝同場前一段；沒有就只查段內與 entry_state 本身。"""
    out: List[Finding] = []
    if prev is not None:
        out += lint_cut_seam(prev, seg)
    out += lint_cont_seam(prev, seg)
    out += lint_within(seg)
    out += lint_background_anchor(seg)
    return out


def waived_codes(seg: Dict[str, Any]) -> set:
    """沿用 h3d staging 的豁免：metadata.staging_waivers／段層 staging_waivers，要有使用者原話 quote 才算。"""
    items = list((seg.get("metadata") or {}).get("staging_waivers") or []) + list(seg.get("staging_waivers") or [])
    return {str(i["code"]).upper() for i in items
            if isinstance(i, dict) and i.get("code") and str(i.get("quote") or "").strip()}


def same_scene(a: Optional[Dict[str, Any]], b: Dict[str, Any]) -> bool:
    if a is None:
        return False
    return not a.get("scene_id") or not b.get("scene_id") or a.get("scene_id") == b.get("scene_id")


def lint_sequence(segments: Iterable[Dict[str, Any]], waived_of=None) -> List[Dict[str, Any]]:
    """依序跑一串段落；回傳 [{segment_id, findings}]。waived_of(seg) 回傳已豁免的代碼集合。"""
    rows = []
    prev = None
    for seg in segments:
        found = lint_segment(seg, prev if same_scene(prev, seg) else None)
        if waived_of is not None:
            waived = waived_of(seg)
            found = [f for f in found if f["code"] not in waived]
        rows.append({"segment_id": seg.get("segment_id"), "findings": found})
        prev = seg
    return rows


def handoff_block(entry_state_en: Any, resolve=None) -> str:
    """CONT 段縫的交接塊（英文）：只吃英文值；含中文或指代詞回空字串，由呼叫端寫 compile note。"""
    norm = normalize_state(entry_state_en)
    if not norm:
        return ""
    text = json.dumps(norm, ensure_ascii=False)
    if re.search(r"[\u3400-\u9fff]", text) or VAGUE_CARRY.search(text):
        return ""
    parts = []
    for who, fields in norm.items():
        bits = [f"{k.replace('_', ' ')} {v.rstrip('.')}" for k, v in fields.items() if k in STATE_KEYS or v]
        if not bits:
            continue
        name = "" if who == "*" else (resolve(who) if resolve else who)
        parts.append(f"{name}: " + ", ".join(bits) if name else ", ".join(bits))
    if not parts:
        return ""
    return " Opening state at 0.0 s: " + "; ".join(parts) + "."
