#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""原著無台詞動作鏡（劇本 `△【動作】…`／`△【動作2.5】…`）從改編一路到編譯的共用規則。

規格：references/adapt/dialogue-first-adaptation.md §3、references/storyboard/cinematic-director.md「台詞密度閘門」D5／D6。

為什麼有這個模組（噩盡島 EP01 吞鳥鏡）：片長照台詞時間反推時，原著無台詞的動作沒有自己的秒數，
「咬手、甩上半空、落進喉嚨」三個動作只分到 2.2 秒，成片角色被拋起又掉回地上、沒被吞。
規則：一個【動作】標記＝一個主要動作＝分鏡裡獨立一鏡，鏡長＝標記秒數（未給 2.0 s，最短 h3_spec.MIN_SHOT_SEC），
台詞估時不得壓縮它；台詞類節奏閘門（密度、有人聲鏡比例、句間空隙、切鏡後開口、開口次數）都不計動作鏡。

本模組（只用標準庫）：
  ACTION_MARK_RE／mark_seconds(text)／strip_marks(text)  劇本標記
  action_clauses(text)／count_actions(text)              「主要動作」數（依子句計，見下）
  is_action_shot(shot)／required_seconds(shot)            Layer 2 動作鏡（source_action:true 且無台詞）
  strip_layer2(seg)／strip_pacing(seg)                    拿掉動作鏡、其後時間整段前移（台詞類閘門用）

「主要動作」怎麼數（啟發式，故意保守）：把描述依標點（，、；。！？…—）和「然後／接著／隨即／隨後／緊接著／跟著」
切成子句，含動作動詞的子句算一個主要動作；同一子句裡的多個動詞只算一個（「一口咬住」＝1）。
「」內文字（台詞、專有名詞）與呼叫端給的角色名先拿掉，避免名字裡的字（如「飛」）被當成動詞。
"""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional

try:
    import h3_spec
    MIN_SHOT_SEC = h3_spec.MIN_SHOT_SEC
except ImportError:  # pragma: no cover - 套件匯入路徑
    try:
        from . import h3_spec
        MIN_SHOT_SEC = h3_spec.MIN_SHOT_SEC
    except ImportError:  # 單獨拷出使用
        MIN_SHOT_SEC = 1.2

ACTION_MARK_RE = re.compile(r"【動作\s*([\d.]+)?\s*(?:s|秒)?】")
ACTION_DEFAULT_SEC = 2.0          # 【動作】未給秒數時的鏡長
SPLIT_MIN_ACTIONS = 3             # D6／adapt_gate：≥3 個主要動作才檢查
SPLIT_FAIL_PER_ACTION = 1.5       # D6：鏡長 < 1.5 s × 動作數 → FAIL（要求拆鏡）
SPLIT_WARN_PER_ACTION = 2.0       # D6：鏡長 < 2.0 s × 動作數 → WARN
DURATION_TOLERANCE = 0.05         # D5：動作鏡比標記秒數短超過這個量算被截短

# 動作動詞（單字）。只收「看得到身體／物體位移或接觸」的動詞；說、想、看這類不算。
_VERBS = set(
    "咬叼啄吞嚥嚼甩拋扔丟擲摔砸墜跌撲衝撞跳躍竄掠翻滾爬抓揪拽扯拖推舉抬劈砍斬刺捅戳射擊揍踢踹踩蹬揮掃掄"
    "噴吐爆炸裂碎崩塌扭折夾纏捲絞勒掐壓撕搶奪閃躲擋撐翻跪摟抱扛拔插捏捶敲撈潑灑倒落飛撲"
)
# 雙字動作詞（含單字表裡沒有的）
_VERB_WORDS = ("吞下", "嚥下", "落進", "掉進", "掉落", "滑落", "沉入", "鑽進", "鑽出", "衝出", "竄出", "撲向",
               "抓住", "咬住", "張嘴", "張開", "合上", "閉合", "飛起", "升空", "爆開", "炸開", "倒下", "倒地")
# 含動作字但不是動作的詞（先拿掉再數）
_NON_ACTION_WORDS = ("話音未落", "話音剛落", "落座", "打算", "打量", "打聽", "打招呼", "倒是", "倒也", "反倒", "部落", "落寞", "失落", "段落", "角落",
                     "落後", "下落", "著落", "拉麵", "判斷", "不斷", "斷定", "照射", "注射", "反射", "射手", "飛機",
                     "飛快", "閃光", "閃爍", "閃亮", "一閃而過的念頭", "壓力", "壓抑", "撐腰", "抱歉", "抱怨", "擔當",
                     "推測", "推理", "推論", "推薦", "推辭", "搶先", "碎碎念", "崩潰", "爆料", "爆笑", "掃興", "掃視",
                     "翻譯", "翻閱", "插嘴", "插話", "噴嚏", "吐槽", "吐露", "躲藏的心思", "跌宕", "摔門而出的念頭")
_CLAUSE_SPLIT_RE = re.compile(r"[，,、；;。．！!？?…—\n]+|然後|接著|緊接著|隨即|隨後|旋即|跟著")
_QUOTE_RE = re.compile(r"「[^「」]*」|『[^『』]*』|“[^”]*”|\"[^\"]*\"")


def mark_seconds(text: str) -> List[float]:
    """一行文字裡每個【動作N】標記的鏡長（未給 ACTION_DEFAULT_SEC，最短 MIN_SHOT_SEC）。沒有標記回空清單。"""
    out = []
    for val in ACTION_MARK_RE.findall(text or ""):
        try:
            v = float(val) if val else ACTION_DEFAULT_SEC
        except ValueError:
            v = ACTION_DEFAULT_SEC
        out.append(round(max(MIN_SHOT_SEC, v), 3))
    return out


def has_mark(text: Any) -> bool:
    return bool(ACTION_MARK_RE.search(str(text or "")))


def strip_marks(text: str) -> str:
    return ACTION_MARK_RE.sub("", text or "").strip()


def split_marked_line(text: str) -> List[Dict[str, Any]]:
    """把一行拆成「一個標記一段」：[{text, seconds}]。行首沒有標記的前綴併進第一段。
    一般一行只有一個標記；一行寫了兩個標記時拆成兩鏡（一個標記＝一個主要動作）。"""
    marks = list(ACTION_MARK_RE.finditer(text or ""))
    if not marks:
        return []
    secs = mark_seconds(text)
    out = []
    for i, m in enumerate(marks):
        start = 0 if i == 0 else m.start()
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        out.append({"text": text[start:end].strip(), "seconds": secs[i]})
    return out


def _clean(text: str, ignore_names: Iterable[str] = ()) -> str:
    t = _QUOTE_RE.sub("，", strip_marks(str(text or "")))
    for name in sorted({n for n in ignore_names if n}, key=len, reverse=True):
        t = t.replace(name, "")
    for w in _NON_ACTION_WORDS:
        t = t.replace(w, "")
    return t


def action_clauses(text: str, ignore_names: Iterable[str] = ()) -> List[str]:
    """含動作動詞的子句（一個子句＝一個主要動作）。"""
    out = []
    for clause in _CLAUSE_SPLIT_RE.split(_clean(text, ignore_names)):
        c = clause.strip()
        if c and (any(w in c for w in _VERB_WORDS) or any(ch in _VERBS for ch in c)):
            out.append(c)
    return out


def count_actions(text: str, ignore_names: Iterable[str] = ()) -> int:
    return len(action_clauses(text, ignore_names))


# ---------------------------------------------------------------- Layer 2

def _f(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _has_dialogue(shot: Dict[str, Any]) -> bool:
    dlg = shot.get("dialogue_and_audio") or {}
    if dlg.get("has_dialogue") is True:
        return True
    return bool(str(dlg.get("line_verbatim") or "").strip()) or bool(shot.get("has_dialogue"))


def is_action_shot(shot: Any) -> bool:
    """原著無台詞動作鏡：`source_action: true` 且沒有台詞（有台詞的鏡照一般台詞鏡算）。"""
    return isinstance(shot, dict) and shot.get("source_action") is True and not _has_dialogue(shot)


def mark_text(shot: Dict[str, Any]) -> str:
    am = shot.get("action_mark")
    if isinstance(am, dict):
        return str(am.get("text") or "")
    return str(am or "")


def required_seconds(shot: Dict[str, Any]) -> Optional[float]:
    """動作鏡應有的鏡長：action_mark.seconds，否則由 action_mark 文字的標記算；都沒有回 None。"""
    am = shot.get("action_mark")
    if isinstance(am, dict) and _f(am.get("seconds")) is not None:
        return max(MIN_SHOT_SEC, float(am["seconds"]))
    secs = mark_seconds(mark_text(shot))
    return sum(secs) if secs else None


def shot_span(shot: Dict[str, Any]) -> float:
    st = _f(shot.get("start_time", shot.get("start")))
    et = _f(shot.get("end_time", shot.get("end")))
    if st is not None and et is not None:
        return et - st
    return _f(shot.get("duration")) or 0.0


def _shift(win: Any, delta: float) -> Any:
    if not isinstance(win, dict):
        return win
    out = dict(win)
    for key in ("start", "end"):
        v = _f(out.get(key))
        if v is not None:
            out[key] = round(v - delta, 6)
    return out


def strip_layer2(seg: Dict[str, Any]) -> Dict[str, Any]:
    """拿掉原著無台詞動作鏡、其後時間整段前移的 Layer 2 副本；沒有動作鏡（或整段都是動作鏡）原樣回傳。

    台詞類閘門（validate D1–D4）用它：動作鏡是原著要求的畫面時間，不該吃蒙太奇額度、拉低台詞密度，
    或讓動作鏡前後兩句台詞之間被量成「句間空隙過長」。編譯、送件、時長守恆照舊用原段。"""
    shots = [s for s in (seg.get("shots") or []) if isinstance(s, dict)]
    if not any(is_action_shot(s) for s in shots) or all(is_action_shot(s) for s in shots):
        return seg
    removed = 0.0
    new_shots = []
    for shot in shots:
        if is_action_shot(shot):
            removed += shot_span(shot)
            continue
        s2 = dict(shot)
        if removed:
            for key in ("start_time", "end_time", "start", "end"):
                v = _f(s2.get(key))
                if v is not None:
                    s2[key] = round(v - removed, 6)
            dlg = dict(s2.get("dialogue_and_audio") or {})
            if isinstance(dlg.get("speech_window"), dict):
                dlg["speech_window"] = _shift(dlg["speech_window"], removed)
            if dlg.get("line_timecodes"):
                dlg["line_timecodes"] = [_shift(t, removed) for t in dlg["line_timecodes"]]
            if dlg.get("extra_lines"):
                dlg["extra_lines"] = [{**x, "speech_window": _shift(x["speech_window"], removed)}
                                      if isinstance(x, dict) and isinstance(x.get("speech_window"), dict) else x
                                      for x in dlg["extra_lines"]]
            if "dialogue_and_audio" in s2:
                s2["dialogue_and_audio"] = dlg
        new_shots.append(s2)
    out = dict(seg)
    out["shots"] = new_shots
    meta = dict(seg.get("metadata") or {})
    t = _f(meta.get("target_duration_sec"))
    if t is not None:
        meta["target_duration_sec"] = round(t - removed, 6)
        out["metadata"] = meta
    out["_action_shots_stripped_sec"] = round(removed, 6)
    return out


def strip_pacing(seg: Dict[str, Any]) -> Dict[str, Any]:
    """pacing_gate 輸入格式版：拿掉 `source_action:true` 的無台詞鏡，其後 shots／lines 的 start/end 前移，duration 扣掉。"""
    shots = [s for s in (seg.get("shots") or []) if isinstance(s, dict)]
    acts = [s for s in shots if s.get("source_action") and not s.get("has_dialogue")]
    if not acts or len(acts) == len(shots):
        return seg

    def removed_before(t: float) -> float:
        return sum(float(s["end"]) - float(s["start"]) for s in acts if float(s["end"]) <= t + 1e-6)

    out = dict(seg)
    out["shots"] = [{**s, "start": round(float(s["start"]) - removed_before(float(s["start"])), 6),
                     "end": round(float(s["end"]) - removed_before(float(s["start"])), 6)}
                    for s in shots if s not in acts]
    out["lines"] = [{**l, "start": round(float(l["start"]) - removed_before(float(l["start"])), 6),
                     "end": round(float(l["end"]) - removed_before(float(l["start"])), 6)}
                    for l in (seg.get("lines") or [])]
    total = sum(float(s["end"]) - float(s["start"]) for s in acts)
    if _f(seg.get("duration")) is not None:
        out["duration"] = round(float(seg["duration"]) - total, 6)
    out["_action_shots_stripped_sec"] = round(total, 6)
    return out


def split_overload(shot: Dict[str, Any], ignore_names: Iterable[str] = ()) -> Optional[Dict[str, Any]]:
    """D6：無台詞鏡塞了 ≥3 個主要動作且鏡長不夠。回傳 {level: FAIL|WARN, n, dur, need_fail, need_warn, clauses, text}；
    沒問題回 None。描述取 action_mark 文字與 shot_intent.story_beat 中動作數較多的那個（TODO 佔位不算）。"""
    if _has_dialogue(shot):
        return None
    texts = [mark_text(shot)]
    beat = str(((shot.get("shot_intent") or {}).get("story_beat")) or "")
    if "TODO" not in beat:
        texts.append(beat)
    best = max(texts, key=lambda t: count_actions(t, ignore_names))
    clauses = action_clauses(best, ignore_names)
    n = len(clauses)
    if n < SPLIT_MIN_ACTIONS:
        return None
    dur = shot_span(shot)
    need_fail, need_warn = SPLIT_FAIL_PER_ACTION * n, SPLIT_WARN_PER_ACTION * n
    if dur < need_fail - 1e-6:
        level = "FAIL"
    elif dur < need_warn - 1e-6:
        level = "WARN"
    else:
        return None
    return {"level": level, "n": n, "dur": dur, "need_fail": need_fail, "need_warn": need_warn,
            "clauses": clauses, "text": best}


# ---------------------------------------------------------------- validate D5／D6

def segment_issues(data: Dict[str, Any], ignore_names: Iterable[str] = ()) -> tuple:
    """單段檢查（validate_storyboard 每段都跑；沒有動作鏡、也沒有無台詞多動作鏡時兩串都空）。

    D5（FAIL）：動作鏡的 action_mark 含 ≥2 個【動作】標記（被合併）；動作鏡比標記秒數短（被截短）。
    D6：無台詞鏡描述 ≥3 個主要動作且鏡長 < 1.5 s×動作數 → FAIL（要求拆鏡），< 2.0 s×動作數 → WARN。
        沒標 source_action／action_mark 的無台詞鏡（舊專案）只看 shot_intent.story_beat，最多 WARN（不改舊專案的過閘結果）。
    """
    errors: List[str] = []
    warnings: List[str] = []
    for i, shot in enumerate(s for s in (data.get("shots") or []) if isinstance(s, dict)):
        sid = shot.get("shot_id") or f"SH{i + 1:02d}"
        marked = is_action_shot(shot) or bool(mark_text(shot))
        if is_action_shot(shot):
            n_marks = len(ACTION_MARK_RE.findall(mark_text(shot)))
            if n_marks > 1:
                errors.append(f"[D5 【動作】鏡被合併] {sid} 一鏡含 {n_marks} 個【動作】標記；一個標記＝一個主要動作＝獨立一鏡，拆成 {n_marks} 鏡")
            need = required_seconds(shot)
            dur = shot_span(shot)
            if need is not None and dur < need - DURATION_TOLERANCE:
                errors.append(f"[D5 【動作】鏡被截短] {sid} 鏡長 {dur:.2f}s < 劇本標記 {need:g}s；"
                              "台詞估時不得壓縮動作鏡，段裝不下就另開段（改劇本秒數請改 `△【動作N】` 後重跑骨架）")
        over = split_overload(shot, ignore_names)
        if over:
            msg = (f"{sid} 無台詞鏡塞了 {over['n']} 個主要動作（{'／'.join(c[:10] for c in over['clauses'][:4])}），"
                   f"鏡長 {over['dur']:.2f}s")
            if over["level"] == "FAIL" and marked:
                errors.append(f"[D6 動作過載要拆鏡] {msg} < {SPLIT_FAIL_PER_ACTION:g}s×{over['n']}＝{over['need_fail']:.1f}s；"
                              "一個動作一鏡（劇本拆成多行 `△【動作】…`），每鏡 ≥2.0 s")
            else:
                warnings.append(f"[D6 動作偏擠] {msg} < {(SPLIT_FAIL_PER_ACTION if over['level'] == 'FAIL' else SPLIT_WARN_PER_ACTION):g}s"
                                f"×{over['n']}；建議拆成 {over['n']} 鏡、每鏡 ≥2.0 s"
                                + ("" if marked else "（未標【動作】的舊鏡只提醒；原著無台詞動作請在劇本標 `△【動作】`）"))
    return errors, warnings


def expected_marks(scene: Dict[str, Any]) -> List[str]:
    """handoff 場景裡劇本的【動作】標記（一個標記一筆，順序同劇本）。"""
    beats = scene.get("action_beats") or (scene.get("storyboard_handoff") or {}).get("required_visual_beats") or []
    return [p["text"] for b in beats for p in split_marked_line(str(b))]


def scene_count_errors(scene_id: str, expected: List[str], segments: List[Dict[str, Any]]) -> List[str]:
    """D5（FAIL）：劇本【動作】標記數 ≠ 分鏡動作鏡標記數（遺失、被併進台詞鏡、或多出沒有劇本依據的動作鏡）。
    劇本沒有任何標記、分鏡也沒有動作鏡時回空清單（舊專案不受影響）。"""
    shots = [s for seg in segments for s in (seg.get("shots") or []) if isinstance(s, dict)]
    got = sum(max(1, len(ACTION_MARK_RE.findall(mark_text(s)))) for s in shots if is_action_shot(s))
    if not expected and not got:
        return []
    if got == len(expected):
        return []
    merged = [s.get("shot_id", "?") for s in shots if not is_action_shot(s) and has_mark(mark_text(s))]
    hint = (f"；{('、'.join(merged))} 帶【動作】文字卻有台詞或沒標 source_action（被併進台詞鏡）" if merged else "")
    return [f"[D5 【動作】標記數對不上] {scene_id} 劇本 {len(expected)} 個【動作】標記、分鏡動作鏡 {got} 個{hint}。"
            "每個標記要是獨立一鏡（source_action:true、action_mark.text 原樣）；重跑 handoff_to_skeleton.py 或補拆鏡"]
