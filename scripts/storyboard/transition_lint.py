# -*- coding: utf-8 -*-
"""鏡間銜接與佔位延續 lint（D15–D24；D21 只建議，其餘警告）。

規則與證據等級見 `references/storyboard/shot-transitions.md`（單一入口）。本模組只看 Layer 2／編譯後分段的
結構欄位與文字（`shots[].camera_optics`、`shots[].cut_in`、`shots[].positions`、段層 `seam_in`／`entry_state`／
`exit_state`／`beats_done`／`beats_new`、動作描述），不判斷畫面；畫面是否真的接得上屬階段 6 驗收
（`h3d qa --continuity`、`h3d seamcheck` 接點對照圖＋檢查清單）。

啟用條件（向下相容）：
  - D15 只在下一段 `seam_in=cut`、D18 只在 `seam_in=cont` 時跑；
  - D16／D17／D19／D20／D22–D24 只在該段「有規劃鏡間銜接」時跑：段落有 `seam_in`／`entry_state`／`exit_state`／
    `beats_done`／`beats_new`，或任一鏡有 `cut_in.type`／`positions`。舊專案沒有這些欄位 → 一條都不報；
  - D21 看逐鏡 `positions`；段層 `positions`（REMIX 綁定既有欄位）只在該段已啟用時才看。

同場判斷（段縫規則要上一段同場才比）：`narrative_scene_id`（敘事場景）優先，其次 `source_scene_id`，最後 `scene_id`。
一段一個場景包（scene_id＝S-buffet-fight-a／-b…）的專案請寫 `narrative_scene_id`，否則段縫規則不會跑。

規則：
  D15 CUT 段縫差異不足：上段末鏡 vs 本段首鏡，主體不同（含人→空鏡、一側 character_ids 空）／景別差 ≥2 級／
      角度差 ≥90° 三項都證明不了（Toonflow §A7.3 閘門；角度要 `camera_optics.azimuth_deg` 兩邊都有才算數）。
  D16 同主體相鄰鏡差異不足：段內相鄰兩鏡主體相同，景別差 <2 級且角度差 <30°（或角度未填）。
      前後任一鏡是插入鏡（cut_in=insert）、或本鏡 cut_in=match_action 時不查；OTS↔非 OTS 只在兩邊都沒填角度時豁免。
  D17 連 3 鏡同景別：段內連續 3 鏡同一景別級（主體輪替的正反打不算）。
  D18 CONT 段縫不符：缺 exit_state／entry_state、兩者共同欄位不一致、上段末 1 秒有台詞、首鏡景別和上段末鏡不同、
      entry_state 寫「承接上一段／同上」這類指代。
  D19 台詞跨切點沒有 `<scenetrans>`：speech_window 跨過切點，或 L_CUT／J_CUT 台詞，兩側文字都沒有 `<scenetrans>`。
  D20 段內相鄰鏡站位對調／漂移沒寫走位：共同角色 `order_lr` 左右對調（角度差 >90° 的反打不算）、`world` 世界位置改變，
      且後一鏡沒寫走位／越軸理由；`screen_x` 差 >15% 畫寬只在 `cut_in=match_action` 且景別差 ≤1 級時查。
  D21 多人鏡缺背景錨點（level＝suggestion，只建議、不算警告數）：positions ≥2 人，有人沒寫 `background_anchor`。
  D22 重演／狀態倒退：同場相鄰段（上段末鏡＋exit_state＋segment_end_state＋ledger_out → 本段首鏡動作＋entry_state＋
      ledger_in）與段內相鄰鏡，比對一次性事件（站起、坐下、倒地、落地、吞咬、破牆、撞翻、打飛、脫手、奔出）：
      下一段把上段已完成的事件再做一次、或入口狀態倒退回事件之前（站起→仍坐著）；事件帳 `beats_done`／`beats_new`
      （選填）裡 beat ID 重複出現。中英關鍵詞判斷，已發生的事寫成靜止狀態（「已站起」「still standing」）不報。
  D23 朝向和站位矛盾：同一鏡寫「朝畫左看 X」而 X 在畫右（screen_x 或 order_lr）；相鄰鏡角度差 <90° 時同一人朝向
      左右對調且沒寫轉身／回頭。
  D24 反打沒換邊：相鄰鏡（含同場段縫）方位角差 >90°，共同角色（≥2 人）的左右順序卻沒互換，也沒寫走位。

豁免：沿用段落 `metadata.staging_waivers`（code＋使用者原話 quote），由呼叫端處理。
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

CODES = ("D15", "D16", "D17", "D18", "D19", "D20", "D21", "D22", "D23", "D24")
SUGGESTION_CODES = ("D21",)  # level＝suggestion：只建議、不算警告數
TITLES = {
    "D15": "CUT 段縫差異不足",
    "D16": "同主體相鄰鏡差異不足",
    "D17": "連 3 鏡同景別",
    "D18": "CONT 段縫不符",
    "D19": "台詞跨切點沒有 <scenetrans>",
    "D20": "相鄰鏡站位對調或漂移沒寫走位",
    "D21": "多人鏡缺背景錨點（建議）",
    "D22": "重演或狀態倒退",
    "D23": "朝向和站位矛盾",
    "D24": "反打沒換邊",
}
EVIDENCE = {
    "D15": "D（Toonflow-app 規則，無實測）",
    "D16": "A/B（30° 規則、Dmytryk；景別跳 2 級為 B）",
    "D17": "C/D（Shanyin 拉片統計＋DirectorSKILL 等規則；AI 端無實測）",
    "D18": "C/D（manju-laoli 定格承接、zenstory 尾幀實測；本 repo 未驗，見 E1）",
    "D19": "B/D（H3 開源格式 `<scenetrans>`；未在本 repo 實測）",
    "D20": "A/B（180° 規則）；≤15% 畫寬為 D（DirectorSKILL），只在動作匹配時查",
    "D21": "C（manju-laoli 背景錨點鎖，作者自報；本 repo T1 命中率 20%，降為建議）",
    "D22": "D（waoowaoo／Toonflow「時間只往前」共識）；本 repo T1 盲判 7/18 問題屬此類（觀察，非實測規則效度）",
    "D23": "A/B（視線方向與銀幕方向；StudioBinder eyeline）",
    "D24": "A/B（180° 規則：反打畫面左右互換；Toonflow 世界＋畫面座標雙層，D）",
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
# 自由文字景別（英文／中文）→ 代碼；順序重要：長詞先比（extreme close-up 先於 close-up、中近景先於近景）。
# 先把連字號、底線換成空格，再拿掉 shot／angle／low／high 等修飾。
FREE_SIZE_PATTERNS: Tuple[Tuple[str, str], ...] = (
    (r"extreme close|\bxcu\b|\becu\b|大特寫|極特寫", "ECU"),
    (r"big close|\bbcu\b|choker", "BCU"),
    (r"medium close|mid close|\bmcu\b|中近景|近景|胸像", "MCU"),
    (r"\bclose\b|\bcu\b|特寫", "CU"),
    (r"extreme (?:wide|long)|\bels\b|\bews\b|\bxls\b|\bxws\b|establishing|大遠景|極遠景", "ELS"),
    (r"medium (?:wide|long|full)|mid (?:wide|long|full)|\bmls\b|\bmws\b|\bmfs\b|cowboy|knee|american|中遠景|中全景|七分身", "MLS"),
    (r"\bmedium\b|\bmid\b|\bms\b|waist|中景|半身", "MS"),
    (r"\bwide\b|\blong\b|\bfull\b|\bws\b|\bls\b|\bfs\b|遠景|全景|全身", "LS"),
)
OTS_RE = re.compile(r"over (?:the )?shoulder|\bots\b|過肩", re.I)
SCREEN_X_TOLERANCE = 0.15
TIME_TOL = 0.05

# 交接塊／entry_state 不准寫指代（模型看不到上一段）：Toonflow「禁止寫延续上一段／同上」
VAGUE_CARRY = re.compile(
    r"承接上一段|承接上段|延續上一段|延续上一段|接續上一段|同上一段|同上|如上|與上一段相同|和上一段一樣"
    r"|same as (?:the )?(?:previous|above|before|last)|as (?:in|before|above) (?:the )?(?:previous|last)?\s*(?:segment|clip|shot)?"
    r"|continu\w* from the previous|carried over from the previous|from the previous (?:segment|clip)",
    re.I)
# 走位／越軸理由：後一鏡有寫就不報 D20／D24
BLOCKING_CHANGE = re.compile(
    r"走位|走到|走向|走出|走進|走過|繞到|繞過|繞著|繞|換位|移到|移向|越軸|過軸|軸上|中性鏡|轉身|起身|交換位置|互換"
    r"|經過|穿過|跨過|跨到|跨步|向[東西南北]|往[東西南北左右前後]|朝[東西南北]走|退到|退後|後退|倒退|退開|退向"
    r"|跑到|跑向|衝到|衝向|撲向|滾到|滑到|被.{0,4}(?:打飛|撞飛|甩飛)"
    r"|\bwalks?\b|\bcross(?:es|ing)?\b|\bcircles?\b|\bmoves? (?:to|toward|around|behind|past)\b|\bsteps? (?:to|around|behind|past|back)\b"
    r"|\bswap(?:s|ped)?\b|\btrade places\b|\bturns? around\b|\bon[- ]axis\b|\bneutral (?:shot|angle)\b|\baxis\b"
    r"|\bpass(?:es|ing)\b|\bpast\b|\bretreat\w*|\bbacks? (?:away|up|off)\b|\bheads? (?:east|west|north|south)\w*"
    r"|\b(?:east|west|north|south)ward\b|\bruns? (?:to|toward|past|across)\b|\brush(?:es)? (?:to|toward|past)\b"
    r"|\bis (?:thrown|flung|knocked)\b", re.I)
# 朝向左右對調的合理理由（D23 相鄰鏡）：轉身／回頭寫了就不報
TURN_RE = re.compile(r"轉身|回頭|轉頭|扭頭|回身|掉頭|\bturns?\b|\blooks? (?:back|over|away)\b|\bglances? (?:back|over)\b|\bspins?\b",
                     re.I)
SCENETRANS = "<scenetrans>"

# ---------------------------------------------------------------------------
# D22 事件表：一次性事件（做完就是狀態）。done＝上段已完成（狀態或動作）；redo＝下段又演一次；
# regress＝入口退回事件之前的狀態（只看主詞相同的子句，或明寫 still／仍）。已發生寫成靜止狀態（已／仍／still）不算重演。
# ---------------------------------------------------------------------------
EVENTS: Tuple[Dict[str, Any], ...] = (
    {"id": "stand_up", "label": "站起",
     "done": r"站起|起身|站直|站穩|爬起|已站|standing|stood up|on (?:his|her|their) feet|half-?ris(?:en|es)|rose to",
     "redo": r"站起|起身|爬起|站了起來|stands? up|\brises\b|half-?rises|gets? (?:up|to (?:his|her|their) feet)|pushes (?:himself|herself|themselves) up",
     "regress": r"坐著|坐在(?!地)|仍坐|還坐|坐回|still (?:seated|sitting)|\bseated\b|\bsitting\b",
     "regress_strong": r"仍坐|還坐|still (?:seated|sitting)"},
    {"id": "sit_down", "label": "坐下",
     "done": r"坐下|已坐|坐回|sat down|\bseated\b",
     "redo": r"坐下|坐回|坐了下來|sits? (?:back )?down|takes? a seat|sinks? (?:back )?(?:into|onto)",
     "regress": r"站著|仍站|still standing", "regress_strong": r"仍站著|still standing"},
    {"id": "fall", "label": "倒地",
     "done": r"倒地|摔倒|跌倒|跌坐|躺在|躺著|趴在|仰躺|側躺|坐在地上|坐地|摔在地|on the (?:floor|ground|tiles)|lying|sprawled|knocked down",
     "redo": r"摔倒|跌倒|倒下|倒地|摔在|跌坐|撲倒|\bfalls?\b|\bcollapses?\b|crashes? (?:down|to)|is knocked (?:down|over)|slams? (?:down|onto the (?:floor|ground|tiles))|\btumbles?\b",
     "regress": r"站著|仍站|站在|still standing|\bstanding\b", "regress_strong": r"仍站著|still standing"},
    {"id": "land", "label": "落地",
     "done": r"落地|著地|\blanded\b",
     "redo": r"落地|著地|\blands?\b|\blanding\b|touch(?:es)? down"},
    {"id": "swallow", "label": "吞咬",
     "done": r"吞下|吞進|吞食|吞掉|嚥下|吞入|\bswallowed\b|\bdevoured\b",
     "redo": r"吞下|吞進|吞食|吞掉|一口吞|\bswallows?\b|\bgulps?\b|\bdevours?\b"},
    {"id": "break_through", "label": "破牆／破門",
     "done": r"破洞|撞破|打破|破開|衝破|碎了|已碎|碎裂|\bbroken\b|\bshattered\b|smashed|a (?:hole|gap) in",
     "redo": r"撞破|打破|破牆|破門|衝破|碎裂|bursts? through|smash(?:es)? through|breaks? through|\bshatters?\b|crashes? through"},
    {"id": "knock_over", "label": "撞翻",
     "done": r"撞翻|翻倒|側倒|打翻|掀翻|knocked over|on its side|toppled|overturned",
     "redo": r"撞翻|翻倒|打翻|掀翻|knocks? over|\btopples?\b|tips? over|\boverturns?\b"},
    {"id": "thrown", "label": "打飛",
     "done": r"打飛|撞飛|甩飛|被甩|\bthrown\b|\bflung\b|sent flying",
     "redo": r"打飛|撞飛|甩飛|拋飛|\bhurls?\b|\bflings?\b|is (?:thrown|flung|sent flying)|sends? (?:him|her|them) flying"},
    {"id": "drop", "label": "脫手",
     "done": r"脫手|鬆手|丟下|\bdropped\b|let go",
     "redo": r"脫手|鬆手|丟下|\bdrops? (?:the|his|her)\b|lets? go"},
    {"id": "exit_run", "label": "奔出",
     "done": r"奔出|跑出|衝出|出畫|已離開|\bexited\b|has left|out of frame",
     "redo": r"奔出|跑出|衝出|runs? out|bursts? out of|dashes? out"},
)
STATIVE_BEFORE = re.compile(r"(?:已經?|仍然?|還|依然|保持|早已)$|(?:\bstill|\balready|\bremains?|\bremained|\bhaving|\bhas|\bhad|"
                            r"\bstays?|\bkept|\bkeeps|\bis|\bare|\bwas|\bwere)\s+$", re.I)
CLAUSE_SPLIT = re.compile(r"[；;。\n]|(?<=[，,])\s*(?=[^\s，,])")
LEDGER_PREFIX = re.compile(r"^\s*接\s*[^：:]{0,30}[：:]")
POSTURE = (("lying", re.compile(r"倒地|躺|趴|摔倒|跌坐|坐在地上|坐地|on the (?:floor|ground|tiles)|lying|sprawled", re.I)),
           ("seated", re.compile(r"坐著|坐在|坐下|\bseated\b|\bsitting\b|sat down", re.I)),
           ("standing", re.compile(r"站著|站在|站起|站直|\bstanding\b|on (?:his|her|their) feet", re.I)))


# ---------------------------------------------------------------------------
# 欄位讀取
# ---------------------------------------------------------------------------
def _cam(shot: Dict[str, Any]) -> Dict[str, Any]:
    return shot.get("camera_optics") or {}


def size_code(raw: Any) -> Optional[str]:
    """景別字串 → 代碼（SIZE_LEVEL 的 key）；代碼、英文自由文字（close-up、Medium-wide shot、medium close shot…）、
    中文（中近景、特寫…）都讀；讀不到回 None。"""
    text = str(raw or "").strip()
    if not text:
        return None
    up = re.sub(r"[\s\-]+", "_", text.upper())
    if up in SIZE_LEVEL:
        return up
    low = re.sub(r"[-_]+", " ", text.lower())
    ots = bool(OTS_RE.search(low))
    head = re.split(r"[\s/（(,，:：]", text)[0].upper().replace("-", "_")
    if head in SIZE_LEVEL and not (head == "OTS" and len(low.split()) > 1):
        return head
    low = re.sub(r"\b(?:shots?|angle|low|high|tight|loose|two|single|wider|static|frame)\b", " ", low)
    low = re.sub(r"\s+", " ", low).strip()
    if ots:
        low = OTS_RE.sub(" ", low)
    base = None
    for pattern, code in FREE_SIZE_PATTERNS:
        if re.search(pattern, low, re.I):
            base = code
            break
    if ots:
        return "OTS_CU" if base and SIZE_LEVEL[base] >= 4 else "OTS_MS"
    if base is None and re.search(r"two[\s-]?shot", text, re.I):
        return "MS"
    return base


def size_level(shot: Optional[Dict[str, Any]]) -> Optional[int]:
    if not shot:
        return None
    code = size_code(_cam(shot).get("shot_size"))
    return SIZE_LEVEL.get(code) if code else None


def _is_ots(shot: Dict[str, Any]) -> bool:
    return str(size_code(_cam(shot).get("shot_size")) or "").startswith("OTS")


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


def beat_ids(value: Any) -> List[str]:
    if isinstance(value, str):
        value = [value]
    return [str(v).strip() for v in value or [] if str(v or "").strip()] if isinstance(value, (list, tuple)) else []


def shot_positions(shot: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [p for p in shot.get("positions") or [] if isinstance(p, dict) and p.get("id")]


def transition_planned(seg: Dict[str, Any]) -> bool:
    """段落是否已進入鏡間銜接規劃（有任一新欄位的有效值）。舊專案回 False → D16／D17／D19／D20／D22–D24 不跑。"""
    if seam_in(seg) or _nonempty_state(seg.get("entry_state")) or _nonempty_state(seg.get("exit_state")):
        return True
    if beat_ids(seg.get("beats_done")) or beat_ids(seg.get("beats_new")):
        return True
    for shot in seg.get("shots") or []:
        if isinstance(shot, dict) and (cut_type(shot) or shot_positions(shot) or beat_ids(shot.get("beats_new"))):
            return True
    return False


def scene_key(seg: Optional[Dict[str, Any]]) -> Optional[str]:
    """同場判斷用的場景鍵：narrative_scene_id → source_scene_id → scene_id。"""
    if not seg:
        return None
    for key in ("narrative_scene_id", "source_scene_id", "scene_id"):
        if seg.get(key):
            return str(seg[key])
    return None


def same_scene(a: Optional[Dict[str, Any]], b: Dict[str, Any]) -> bool:
    """段縫規則的同場判斷：兩邊都有 narrative_scene_id 就只看它；其次 source_scene_id；最後 scene_id
    （任一邊沒有 scene_id 視為同場，和舊行為一致）。一段一個場景包時 scene_id 不同不代表換場。"""
    if a is None:
        return False
    for key in ("narrative_scene_id", "source_scene_id"):
        if a.get(key) and b.get(key):
            return str(a[key]) == str(b[key])
    return not a.get("scene_id") or not b.get("scene_id") or a.get("scene_id") == b.get("scene_id")


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


def _flatten(value: Any) -> List[str]:
    if value in (None, "", [], {}):
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        out: List[str] = []
        for v in value.values():
            out += _flatten(v)
        return out
    if isinstance(value, (list, tuple)):
        out = []
        for v in value:
            out += _flatten(v)
        return out
    return []


def action_text(shot: Optional[Dict[str, Any]]) -> str:
    """一鏡的動作描述（中英）：action_stages／action_stages_en、five_part_en.motion、blocking_desc、positions[].move。"""
    if not shot:
        return ""
    ap = shot.get("action_and_performance") or {}
    parts = _flatten(ap.get("action_stages")) + _flatten(ap.get("action_stages_en"))
    parts += _flatten((ap.get("five_part_en") or {}).get("motion")) + _flatten((ap.get("five_part") or {}).get("motion"))
    parts += _flatten(shot.get("action")) + _flatten((shot.get("spatial_blocking") or {}).get("blocking_desc"))
    parts += [str(p.get("move") or "") for p in shot_positions(shot)]
    return " ".join(p for p in parts if p)


def exit_texts(seg: Dict[str, Any]) -> List[str]:
    """上段結束時的狀態文字：exit_state、segment_end_state、ledger_out。"""
    end = seg.get("segment_end_state") if isinstance(seg.get("segment_end_state"), dict) else {}
    return [t for t in _flatten(seg.get("exit_state")) + _flatten(end) + _flatten(seg.get("ledger_out")) if t]


def entry_texts(seg: Dict[str, Any]) -> List[str]:
    return [t for t in _flatten(seg.get("entry_state")) + _flatten(seg.get("entry_state_en"))
            + _flatten(seg.get("ledger_in")) if t]


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
        elif isinstance(value, str) and value.strip():
            out[str(who)] = {"position": value.strip()}
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


def _f(code: str, seg: Dict[str, Any], message: str, shot: Optional[int] = None, scope: Optional[str] = None,
       level: Optional[str] = None) -> Finding:
    """scope：seam（本段與上一段的段縫）／within（第 shot-1 鏡 → 第 shot 鏡）／shot（只關於第 shot 鏡）／segment。"""
    where = f" Shot{shot}" if shot else ""
    if scope is None:
        scope = "seam" if code in ("D15", "D18") else ("within" if shot and shot > 1 else ("shot" if shot else "segment"))
    return {"code": code, "level": level or ("suggestion" if code in SUGGESTION_CODES else "warning"), "shot": shot,
            "scope": scope, "message": f"[{code}: {TITLES[code]}] {_sid(seg)}{where}：{message}"}


def lint_cut_seam(prev: Dict[str, Any], seg: Dict[str, Any]) -> List[Finding]:
    """D15：seam_in=cut 時，上段末鏡 vs 本段首鏡至少一項實質差異。"""
    if seam_in(seg) != "cut":
        return []
    a, b = (_shots(prev) or [None])[-1], (_shots(seg) or [None])[0]
    if not a or not b:
        return []
    sa, sb = subjects(a), subjects(b)
    if sa != sb:
        return []  # 主體不同（含人→空鏡／局部：一側 character_ids 空）
    la, lb = size_level(a), size_level(b)
    if la is not None and lb is not None and abs(la - lb) >= 2:
        return []
    ang = angle_diff(a, b)
    if ang is not None and ang >= 90:
        return []
    facts = [f"主體{'相同' if sa else '兩邊都沒填 character_ids'}",
             f"景別 {_cam(a).get('shot_size') or '?'}→{_cam(b).get('shot_size') or '?'}（差 "
             f"{abs(la - lb) if la is not None and lb is not None else '?'} 級）",
             f"角度差 {f'{ang:.0f}°' if ang is not None else '未知（azimuth_deg 未填）'}"]
    return [_f("D15", seg, f"上段 {_sid(prev)} 末鏡 → 本段首鏡是 CUT 段縫，但{'、'.join(facts)}；"
                           "三選一：換主體／景別差 ≥2 級／角度差 ≥90°，只改本段首鏡的主體、景別、角度或構圖，不改劇情；"
                           "上段結尾不定格、留 0.5 s（shot-transitions.md §3）", 1, "seam")]


def lint_cont_seam(prev: Optional[Dict[str, Any]], seg: Dict[str, Any]) -> List[Finding]:
    """D18：seam_in=cont 時的交接檢查。prev 可為 None（上一段不在這次輸入），此時只查本段。"""
    if seam_in(seg) != "cont":
        return []
    out: List[Finding] = []
    entry = seg.get("entry_state")
    if not _nonempty_state(entry):
        out.append(_f("D18", seg, "CONT 段縫沒有 entry_state（位置、朝向、距離、動量、傷損、握持、背景錨點）；"
                                  "編譯器無法寫交接塊，模型會從參考圖站姿重新起手", scope="seam"))
    vague = VAGUE_CARRY.search(state_text(entry) + " " + state_text(seg.get("entry_state_en")))
    if vague:
        out.append(_f("D18", seg, f"entry_state 寫了「{vague.group(0)}」——模型看不到上一段，交接塊要逐項寫成絕對狀態"
                                  "（Toonflow：禁止「延續上一段／同上」）", scope="seam"))
    if prev is None:
        return out
    exit_state = prev.get("exit_state")
    if not _nonempty_state(exit_state):
        out.append(_f("D18", seg, f"上段 {_sid(prev)} 沒有 exit_state，無法核對 CONT 交接", scope="seam"))
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
                                      f"{'…' if len(diffs) > 6 else ''}", scope="seam"))
    if last_second_has_dialogue(prev):
        out.append(_f("D18", seg, f"上段 {_sid(prev)} 最後 1 秒有台詞；CONT 段縫要末 1 秒定格無台詞（剪輯會剪掉這 1 秒）",
                      scope="seam"))
    a, b = (_shots(prev) or [None])[-1], (_shots(seg) or [None])[0]
    la, lb = size_level(a), size_level(b)
    if la is not None and lb is not None and la != lb:
        out.append(_f("D18", seg, f"CONT 段縫首鏡景別 {_cam(b).get('shot_size')} 和上段末鏡 {_cam(a).get('shot_size')} 不同；"
                                  "同機位技術分段要同景別起手（要換景別就改成 seam_in=cut）", 1, "seam"))
    return out


def lint_within(seg: Dict[str, Any]) -> List[Finding]:
    """D16／D17／D19／D20／D22–D24：段內相鄰鏡（只在 transition_planned 時跑）。"""
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
        skip_d16 = ctype in ("cont", "match_action", "insert") or cut_type(a) == "insert"
        if sa and sa == sb and not skip_d16:
            la, lb = size_level(a), size_level(b)
            ang = angle_diff(a, b)
            ots_flip = _is_ots(a) != _is_ots(b) and ang is None  # 過肩豁免收緊：角度有填就看角度
            size_ok = la is not None and lb is not None and abs(la - lb) >= 2
            angle_ok = (ang is not None and ang >= 30) or ots_flip
            if la is not None and lb is not None and not size_ok and not angle_ok:
                out.append(_f("D16", seg, f"{_shot_label(a, i)}→{_shot_label(b, idx)} 同主體，景別 "
                                          f"{_cam(a).get('shot_size')}→{_cam(b).get('shot_size')}（差 {abs(la - lb)} 級），"
                                          f"角度差 {f'{ang:.0f}°' if ang is not None else '未知（azimuth_deg 未填）'}；"
                                          "同主體要角度 ≥30° 或景別跳 ≥2 級，只是換距離就改用運鏡、不切", idx, "within"))
        # D20／D23／D24 站位
        out.extend(_lint_positions_pair(seg, a, b, idx))
        # D22 段內相鄰鏡重演
        if ctype not in ("match_action", "cont", "insert"):
            out.extend(_repeat_findings(seg, [action_text(a)], action_text(b), [], idx, "within",
                                        f"{_shot_label(a, i)}→{_shot_label(b, idx)}"))
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
                                  f"{_cam(trio[0]).get('shot_size')}；中間換一級景別或改成運鏡", i + 1, "within"))
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
            cut_idx = i + 2 if crosses_out else i + 1  # 跨過的那一刀（後一鏡的序號）
            out.append(_f("D19", seg, f"{_shot_label(shot, i + 1)} 的台詞跨過切點（{'L_CUT' if bridge == 'L_CUT' else 'J_CUT' if bridge == 'J_CUT' else 'speech_window 越過鏡頭邊界'}），"
                                      "兩側都沒有 <scenetrans>；在兩鏡五小節 sound 寫 <scenetrans> 並說明 "
                                      "continues seamlessly across the cut，台詞只說一次", cut_idx, "within"))
    # D22 段內 beats_new 重複
    seen: Dict[str, int] = {}
    for i, shot in enumerate(shots, 1):
        for beat in beat_ids(shot.get("beats_new")):
            if beat in seen:
                out.append(_f("D22", seg, f"事件 {beat} 在 Shot{seen[beat]} 已經新做過，Shot{i} 又列在 beats_new；"
                                          "同一件事只演一次，之後寫成靜止狀態", i, "within" if i > 1 else "shot"))
            else:
                seen[beat] = i
    # D23 單鏡朝向對站位
    for i, shot in enumerate(shots, 1):
        out.extend(_facing_target_findings(seg, shot, i))
    return out


# ---------------------------------------------------------------------------
# D22 重演／狀態倒退
# ---------------------------------------------------------------------------
def _live_matches(pattern: str, text: str) -> List[re.Match]:
    """事件詞出現且前面不是「已／仍／still／already…」（寫成靜止狀態的不算動作）。"""
    out = []
    for m in re.finditer(pattern, text, re.I):
        before = text[max(0, m.start() - 14):m.start()]
        if STATIVE_BEFORE.search(before):
            continue
        out.append(m)
    return out


def _clauses(texts: Iterable[str]) -> List[str]:
    out = []
    for t in texts:
        for c in re.split(r"[；;。\n]", LEDGER_PREFIX.sub("", str(t))):
            c = c.strip(" ，,、")
            if c:
                out.append(c)
    return out


def _subject_key(clause: str) -> Optional[str]:
    m = re.match(r"\s*([\u3400-\u9fff])", clause)
    if m:
        return m.group(1)
    m = re.match(r"\s*(?:the\s+)?([A-Za-z][\w-]*)", clause, re.I)
    return m.group(1).lower() if m else None


def _repeat_findings(seg: Dict[str, Any], before_texts: List[str], after_action: str, after_entry: List[str],
                     shot_idx: int, scope: str, where: str) -> List[Finding]:
    out: List[Finding] = []
    before = " ".join(before_texts)
    if not before.strip() or not (after_action.strip() or after_entry):
        return out
    reported: Set[str] = set()
    for ev in EVENTS:
        done_m = re.search(ev["done"], before, re.I) or next(iter(_live_matches(ev["redo"], before)), None)
        if not done_m:
            continue
        redo = _live_matches(ev["redo"], after_action)
        if redo:
            done_word = done_m.group(0)
            out.append(_f("D22", seg, f"{where}：前面已經「{done_word}」（{ev['label']}已完成），後面又寫「{redo[0].group(0)}」，"
                                      "像是把同一件事重演一次；已發生的事寫成靜止狀態（例：已站起、still standing），"
                                      "後面只演新的事件（可用 beats_done／beats_new 事件帳標明）", shot_idx, scope))
            reported.add(ev["id"])
            continue
        if not ev.get("regress"):
            continue
        # 狀態倒退：明寫 still／仍 的退回狀態，或主詞相同的入口子句寫回事件前的狀態
        strong = re.search(ev["regress_strong"], after_action, re.I) if ev.get("regress_strong") else None
        hit = strong.group(0) if strong else None
        if not hit:
            done_subjects = {_subject_key(c) for c in _clauses(before_texts)
                             if re.search(ev["done"], c, re.I) or _live_matches(ev["redo"], c)}
            done_subjects.discard(None)
            for clause in _clauses(after_entry):
                key = _subject_key(clause)
                if key in done_subjects and re.search(ev["regress"], clause, re.I) and not re.search(ev["done"], clause, re.I):
                    hit = clause
                    break
        if hit and ev["id"] not in reported:
            out.append(_f("D22", seg, f"{where}：前面已經{ev['label']}，後面入口卻寫回之前的狀態（「{hit[:40]}」）；"
                                      "入口狀態要接上段結束時的狀態，不要退回事件之前", shot_idx, scope))
            reported.add(ev["id"])
    return out


def _posture(text: str) -> Optional[str]:
    for name, pattern in POSTURE:
        if pattern.search(text):
            return name
    return None


def lint_repeat_seam(prev: Dict[str, Any], seg: Dict[str, Any], seen_beats: Optional[Dict[str, str]] = None) -> List[Finding]:
    """D22 段縫：上段結束狀態＋末鏡動作 vs 本段首鏡動作＋入口狀態；事件帳 beat 重複。"""
    if not transition_planned(seg):
        return []
    out: List[Finding] = []
    first = (_shots(seg) or [None])[0]
    last = (_shots(prev) or [None])[-1]
    before = exit_texts(prev) + ([action_text(last)] if last else [])
    out += _repeat_findings(seg, before, action_text(first), entry_texts(seg), 1, "seam", f"上段 {_sid(prev)} → 本段首鏡")
    # 結構化入口：同一人的姿勢／位置退回
    ex, en, pen = normalize_state(prev.get("exit_state")), normalize_state(seg.get("entry_state")), \
        normalize_state(prev.get("entry_state"))
    for who in ex:
        if who not in en:
            continue
        pe, pn = _posture(" ".join(ex[who].values())), _posture(" ".join(en[who].values()))
        if pe and pn and pe != pn and not BLOCKING_CHANGE.search(action_text(first)) \
                and not re.search(r"起身|站起|坐下|倒|stands?|sits?|falls?|rises", action_text(first), re.I):
            out.append(_f("D22", seg, f"{'' if who == '*' else who + ' '}上段結束是「{pe}」，本段入口卻是「{pn}」，"
                                      "中間沒有動作交代；入口要接上段結束狀態", 1, "seam"))
        ppos, epos, npos = (pen.get(who) or {}).get("position"), ex[who].get("position"), en[who].get("position")
        if ppos and epos and npos and _norm_value(npos) == _norm_value(ppos) != _norm_value(epos):
            out.append(_f("D22", seg, f"{'' if who == '*' else who + ' '}本段入口位置「{npos}」回到上段開頭的位置，"
                                      f"不是上段結束的「{epos}」（回原點）", 1, "seam"))
    # 事件帳
    prev_new, new, done = beat_ids(prev.get("beats_new")), beat_ids(seg.get("beats_new")), beat_ids(seg.get("beats_done"))
    prev_new += [b for s in _shots(prev) for b in beat_ids(s.get("beats_new"))]
    new_all = new + [b for s in _shots(seg) for b in beat_ids(s.get("beats_new"))]
    history = dict(seen_beats or {})
    for b in prev_new:
        history.setdefault(b, _sid(prev))
    dup = [b for b in dict.fromkeys(new_all) if b in history]
    if dup:
        out.append(_f("D22", seg, f"事件帳 beats_new 的 {', '.join(dup)} 已在 {', '.join(sorted({history[b] for b in dup}))} 新做過；"
                                  "同一個 beat 只能新做一次，本段把它移到 beats_done、動作改寫成靜止狀態", 1, "seam"))
    clash = [b for b in new_all if b in done]
    if clash:
        out.append(_f("D22", seg, f"{', '.join(dict.fromkeys(clash))} 同時在 beats_done（已完成）和 beats_new（本段新做）", 1, "seam"))
    if done and prev_new:
        missing = [b for b in dict.fromkeys(prev_new) if b not in done]
        if missing:
            out.append(_f("D22", seg, f"上段 {_sid(prev)} 新做的 {', '.join(missing)} 沒列進本段 beats_done；"
                                      "事件帳斷了，模型可能從事件之前起手", 1, "seam"))
    return out


# ---------------------------------------------------------------------------
# D20／D23／D24 站位
# ---------------------------------------------------------------------------
def _side(text: Any) -> Optional[str]:
    t = str(text or "")
    left = bool(re.search(r"frame[_ ]?left|screen[_ ]?left|\bleft\b|畫左|畫面左|左側|左邊|朝左|向左", t, re.I))
    right = bool(re.search(r"frame[_ ]?right|screen[_ ]?right|\bright\b|畫右|畫面右|右側|右邊|朝右|向右", t, re.I))
    if left == right:
        return None
    return "left" if left else "right"


def _xpos(p: Dict[str, Any]) -> Tuple[Optional[float], Optional[float]]:
    x = p.get("screen_x")
    o = p.get("order_lr")
    xs = float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else None
    os_ = float(o) if isinstance(o, int) and not isinstance(o, bool) else None
    return xs, os_


def _facing_target_findings(seg: Dict[str, Any], shot: Dict[str, Any], idx: int) -> List[Finding]:
    """D23 單鏡：facing 寫畫左／畫右且指名看誰，被看的人卻在另一邊。"""
    pos = shot_positions(shot)
    if len(pos) < 2:
        return []
    by_id = {str(p["id"]): p for p in pos}
    out = []
    for p in pos:
        side = _side(p.get("facing"))
        if not side:
            continue
        target = str(p.get("toward") or p.get("look_at") or "")
        if not target:
            for other in by_id:
                if other != str(p["id"]) and other in str(p.get("facing") or ""):
                    target = other
                    break
        if target not in by_id or target == str(p["id"]):
            continue
        sx, so = _xpos(p)
        tx, to = _xpos(by_id[target])
        if sx is not None and tx is not None:
            rel = tx - sx
        elif so is not None and to is not None:
            rel = to - so
        else:
            continue
        if rel == 0 or (side == "left") == (rel < 0):
            continue
        actual = "右" if rel > 0 else "左"
        out.append(_f("D23", seg, f"{p['id']} 朝向寫「{p.get('facing')}」看 {target}，但 {target} 在他的畫{actual}側"
                                  f"（screen_x／order_lr）；改朝向或改站位，兩者要同一邊", idx, "shot"))
    return out


def _order(pos: Dict[str, Dict[str, Any]], shared: List[str]) -> List[str]:
    items = []
    for x in shared:
        sx, so = _xpos(pos[x])
        key = so if so is not None else (sx if sx is not None else None)
        if key is not None:
            items.append((key, x))
    return [x for _, x in sorted(items)]


def _blocking_text(b: Dict[str, Any], pb: Dict[str, Dict[str, Any]], shared: List[str]) -> str:
    return " ".join([cut_motivation(b), json.dumps(b.get("spatial_blocking") or {}, ensure_ascii=False),
                     json.dumps(((b.get("action_and_performance") or {}).get("five_part_en") or {}).get("motion", ""),
                                ensure_ascii=False),
                     " ".join(str(pb[x].get("move") or "") for x in shared)])


def _lint_positions_pair(seg: Dict[str, Any], a: Dict[str, Any], b: Dict[str, Any], idx: int,
                         scope: str = "within", label: str = "") -> List[Finding]:
    """相鄰兩鏡（段內，或段縫時上段末鏡 a → 本段首鏡 b）：D20 對調／世界位置／動作匹配漂移、D23 朝向對調、D24 反打沒換邊。"""
    pa = {str(p["id"]): p for p in shot_positions(a)}
    pb = {str(p["id"]): p for p in shot_positions(b)}
    shared = [x for x in pa if x in pb]
    if not shared:
        return []
    moved_text = _blocking_text(b, pb, shared)
    moved = bool(BLOCKING_CHANGE.search(moved_text)) or str(_cam(b).get("axis_side") or "").lower() in ("on_axis", "neutral", "axis")
    ang = angle_diff(a, b)
    out: List[Finding] = []
    head = f"{label}：" if label else ""
    oa, ob = _order(pa, shared), _order(pb, shared)
    if not moved:
        # D20 左右對調（反打 >90° 的對調是正確的，不報）
        if scope == "within" and len(oa) >= 2 and set(oa) == set(ob) and oa != ob and not (ang is not None and ang > 90):
            out.append(_f("D20", seg, f"{head}共同角色左到右由 {', '.join(oa)} 變成 {', '.join(ob)}，後一鏡沒寫走位或越軸理由；"
                                      "同一軸線內畫面左右不換，要換先插軸上鏡或寫畫內轉折（cut_in.motivation／positions[].move）",
                          idx, scope))
        world = [x for x in shared if pa[x].get("world") and pb[x].get("world")
                 and _norm_value(pa[x]["world"]) != _norm_value(pb[x]["world"])]
        if scope == "within" and world:
            changes = "；".join(f"{x}: {pa[x]['world']}→{pb[x]['world']}" for x in world)
            out.append(_f("D20", seg, f"{head}{', '.join(world)} 的世界位置改變（{changes}），"
                                      "沒寫走位；換機位只重算畫面座標，世界座標不變", idx, scope))
        # D20 畫面位置漂移：只在動作匹配且景別差 ≤1 時查（硬切本來就換位置）
        la, lb = size_level(a), size_level(b)
        if scope == "within" and cut_type(b) == "match_action" and subjects(a) and subjects(a) == subjects(b) \
                and la is not None and lb is not None and abs(la - lb) <= 1:
            drift = []
            for x in shared:
                xa, xb = pa[x].get("screen_x"), pb[x].get("screen_x")
                if isinstance(xa, (int, float)) and isinstance(xb, (int, float)) and not isinstance(xa, bool) \
                        and not isinstance(xb, bool) and abs(float(xa) - float(xb)) > SCREEN_X_TOLERANCE:
                    drift.append(f"{x} {float(xa):.2f}→{float(xb):.2f}")
            if drift:
                out.append(_f("D20", seg, f"{head}動作匹配同主體，畫面位置差超過 15% 畫寬（{'；'.join(drift)}）；"
                                          "動作中切要讓 A 末幀和 B 首幀主體位置接近", idx, scope))
        # D24 反打沒換邊
        if ang is not None and ang > 90 and len(oa) >= 2 and oa == ob and not any(
                pa[x].get("world") and pb[x].get("world") and _norm_value(pa[x]["world"]) != _norm_value(pb[x]["world"])
                for x in shared):
            out.append(_f("D24", seg, f"{head}機位角度差 {ang:.0f}°（>90°，已到對面），共同角色左到右仍是 {', '.join(oa)}；"
                                      "反打時畫面左右要互換（世界座標不變、畫面座標重算），不然就是有人換了位置卻沒寫走位",
                          idx, scope))
    # D23 同一人朝向左右對調（角度差 <90° 時）
    if ang is not None and ang < 90 and cut_type(b) != "insert" and not TURN_RE.search(moved_text + " " + action_text(b)):
        flips = [x for x in shared if _side(pa[x].get("facing")) and _side(pb[x].get("facing"))
                 and _side(pa[x].get("facing")) != _side(pb[x].get("facing"))]
        if flips:
            out.append(_f("D23", seg, f"{head}{', '.join(flips)} 的朝向由 "
                                      f"{'／'.join(str(pa[x].get('facing')) for x in flips)} 變成 "
                                      f"{'／'.join(str(pb[x].get('facing')) for x in flips)}，機位角度只差 {ang:.0f}°，"
                                      "也沒寫轉身或回頭；視線方向會在剪接點翻過去", idx, scope))
    return out


def lint_seam_positions(prev: Dict[str, Any], seg: Dict[str, Any]) -> List[Finding]:
    """同場段縫的 D23（朝向對調）／D24（反打沒換邊）：上段末鏡 vs 本段首鏡。"""
    if not transition_planned(seg) or not seam_in(seg):
        return []
    a, b = (_shots(prev) or [None])[-1], (_shots(seg) or [None])[0]
    if not a or not b:
        return []
    return [f for f in _lint_positions_pair(seg, a, b, 1, "seam", f"上段 {_sid(prev)} 末鏡 → 本段首鏡")
            if f["code"] in ("D23", "D24")]


def lint_background_anchor(seg: Dict[str, Any]) -> List[Finding]:
    """D21（建議）：多人鏡 positions 缺 background_anchor。逐鏡 positions 一律看；段層 positions 只在已啟用時看。"""
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
                                          "站位漂移常是人物背後的東西變了，每人寫一個具體背景物，不寫「背景不變」", i, "shot"))
    if not any_shot_level and transition_planned(seg):
        pos = [p for p in seg.get("positions") or [] if isinstance(p, dict) and p.get("id")]
        if len(pos) >= 2:
            missing = [str(p["id"]) for p in pos if not str(p.get("background_anchor") or "").strip()]
            if missing:
                out.append(_f("D21", seg, f"段層 positions 的 {', '.join(missing)} 沒寫 background_anchor", scope="segment"))
    return out


def lint_segment(seg: Dict[str, Any], prev: Optional[Dict[str, Any]] = None,
                 seen_beats: Optional[Dict[str, str]] = None) -> List[Finding]:
    """單段（含與 prev 的段縫）。prev＝同場前一段；沒有就只查段內與 entry_state 本身。
    seen_beats：同場更早各段新做過的 beat → 段號（D22 事件帳跨多段比對用；呼叫端累積）。"""
    out: List[Finding] = []
    if prev is not None:
        out += lint_cut_seam(prev, seg)
    out += lint_cont_seam(prev, seg)
    if prev is not None:
        out += lint_repeat_seam(prev, seg, seen_beats)
        out += lint_seam_positions(prev, seg)
    elif seen_beats:
        dup = [b for b in beat_ids(seg.get("beats_new")) if b in seen_beats]
        if dup and transition_planned(seg):
            out.append(_f("D22", seg, f"事件帳 beats_new 的 {', '.join(dup)} 已在 {', '.join(sorted({seen_beats[b] for b in dup}))} 新做過",
                          1, "seam"))
    out += lint_within(seg)
    out += lint_background_anchor(seg)
    return out


def record_beats(seen: Dict[str, str], seg: Dict[str, Any]) -> None:
    """把本段新做的 beat 記進同場歷史（lint_sequence／staging／compile 共用）。"""
    for beat in beat_ids(seg.get("beats_new")) + [b for s in _shots(seg) for b in beat_ids(s.get("beats_new"))]:
        seen.setdefault(beat, _sid(seg))


def warnings_only(findings: Iterable[Finding]) -> List[Finding]:
    return [f for f in findings if f.get("level") != "suggestion"]


def waived_codes(seg: Dict[str, Any]) -> set:
    """沿用 h3d staging 的豁免：metadata.staging_waivers／段層 staging_waivers，要有使用者原話 quote 才算。"""
    items = list((seg.get("metadata") or {}).get("staging_waivers") or []) + list(seg.get("staging_waivers") or [])
    return {str(i["code"]).upper() for i in items
            if isinstance(i, dict) and i.get("code") and str(i.get("quote") or "").strip()}


def lint_sequence(segments: Iterable[Dict[str, Any]], waived_of=None) -> List[Dict[str, Any]]:
    """依序跑一串段落；回傳 [{segment_id, findings}]。waived_of(seg) 回傳已豁免的代碼集合。"""
    rows = []
    prev = None
    beats_by_scene: Dict[str, Dict[str, str]] = {}
    for seg in segments:
        same = same_scene(prev, seg)
        key = scene_key(seg) or ""
        if not same:
            beats_by_scene.pop(key, None)
        seen = beats_by_scene.setdefault(key, {})
        found = lint_segment(seg, prev if same else None, seen)
        record_beats(seen, seg)
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


def lead_in_seconds(seg: Dict[str, Any]) -> float:
    """拋棄式前導秒數（選用、預設 0＝關）：段層 `lead_in_s` 或 `metadata.lead_in_s`。assemble 會自動剪掉。"""
    for value in (seg.get("lead_in_s"), (seg.get("metadata") or {}).get("lead_in_s")):
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
            return float(value)
    return 0.0


def lead_in_block(seconds: float) -> str:
    """lead_in_s>0 時第 1 鏡開頭的前導句：前導期間照起始狀態靜止，之後才開始本段動作（這段會被 assemble 剪掉）。"""
    if seconds <= 0:
        return ""
    return f" From 0.0 s to {seconds:.1f} s everyone holds still in the opening pose; the action of this shot starts after {seconds:.1f} s."
