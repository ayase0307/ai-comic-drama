#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""段間連戲與畫面約束（#133 #138 #139）。

每段獨立送 Ref2VA 時，人物會從參考圖的站姿起手；前段的終態（癱坐、仰躺、被壓住）
不會自動傳到下一段。這個模組提供編譯器與 `compile --check` 共用的純函式：

- previous_segment_map()：同一 scene_id 內依段號排序，找出每段的前一段。
- carry_sentence()：把前段 segment_end_state 的英文終態寫成下一段第 1 鏡的起始狀態句。
- lint_adjacent()：相鄰段姿勢矛盾（前段躺／坐／跪，下一段第 1 鏡卻站著且沒有起身動作）、
  同場景前段沒寫英文終態（無法帶入）、同場景各段光線鎖不一致。
- needs_no_lettering()／NO_LETTERING_SENTENCE：校徽、計程車門、斑駁牆這類可預測的燒字來源，
  自動補一句正向的「表面素淨、無文字無塗鴉」。

只做文字層的確定性檢查，不判斷畫面；需要實際影片才能驗的（終態是否真的演出來）屬 stage-6 驗收。
"""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

# ---------- 姿勢分類 ----------
POSTURE_PATTERNS: Dict[str, re.Pattern] = {
    "lying": re.compile(
        r"\b(lying|lies|lay|laid|supine|prone|sprawl(?:s|ed|ing)?|flat on (?:his|her|their|its) (?:back|stomach|face)|"
        r"on (?:his|her|their) back|pinned (?:down|to the ground|beneath|under)|face[- ]down|face[- ]up|"
        r"collapsed on the (?:ground|floor)|on the ground|on the floor)\b",
        re.I,
    ),
    "seated": re.compile(
        r"\b(sit|sits|sitting|seated|sat|slump(?:s|ed|ing)?|squat(?:s|ted|ting)?|crouch(?:es|ed|ing)?|huddled)\b",
        re.I,
    ),
    "kneeling": re.compile(r"\b(kneel(?:s|ing)?|knelt|on (?:his|her|their|one|both) knees?)\b", re.I),
    "swallowed": re.compile(r"\b(swallowed|inside the (?:mouth|throat|maw|gullet)|engulfed)\b", re.I),
    "standing": re.compile(
        r"\b(stand|stands|standing|stood|upright|walk(?:s|ing)?|stride(?:s)?|striding|strides|runs|running|"
        r"steps forward|strolls?|paces)\b",
        re.I,
    ),
}
DOWN_POSTURES = ("lying", "seated", "kneeling", "swallowed")
# 下一段第 1 鏡若有「起身」類動詞，代表有意識地從前段終態接起，不算矛盾。
RISE_TRANSITION = re.compile(
    r"\b(gets? up|getting up|got up|rises?|rising|rose|stands? up|standing up|stood up|push(?:es)? (?:himself|herself|themselves) up|"
    r"scrambles? (?:up|to (?:his|her|their) feet)|climbs? to (?:his|her|their) feet|staggers? up|struggles? up|"
    r"hauls? (?:himself|herself) up|from (?:lying|sitting|kneeling|the ground|the floor)|still (?:lying|seated|sitting|kneeling|slumped))\b",
    re.I,
)


def postures(text: str) -> List[str]:
    """回傳文字中出現的姿勢類別（依 POSTURE_PATTERNS 順序）。"""
    if not text:
        return []
    return [name for name, pat in POSTURE_PATTERNS.items() if pat.search(text)]


# ---------- 段落順序 ----------
def segment_sort_key(seg_id: str) -> Tuple:
    """與 handoff_to_skeleton.segment_sort_key 同規則：先比場景前綴，再比段尾長度與字母（aa 在 z 之後）。"""
    seg_id = str(seg_id or "")
    m = re.fullmatch(r"(.*)-([a-z]+)", seg_id)
    if m:
        return (m.group(1), len(m.group(2)), m.group(2))
    return (seg_id, 0, "")


def previous_segment_map(segments: Iterable[Tuple[str, Optional[str]]]) -> Dict[str, str]:
    """segments：(segment_id, scene_id)。同一 scene_id 內，依段號排序後的前一段。

    跨場景不帶入（換場本來就重新開始）；scene_id 缺漏的段不配對。
    """
    by_scene: Dict[str, List[str]] = {}
    for seg_id, scene_id in segments:
        if not seg_id or not scene_id:
            continue
        lst = by_scene.setdefault(str(scene_id), [])
        if str(seg_id) not in lst:
            lst.append(str(seg_id))
    prev: Dict[str, str] = {}
    for ids in by_scene.values():
        ordered = sorted(ids, key=segment_sort_key)
        for a, b in zip(ordered, ordered[1:]):
            prev[b] = a
    return prev


def _has_cjk(value: Any) -> bool:
    return bool(re.search(r"[\u3400-\u9fff]", str(value or "")))


def english_end_state(end_state: Any) -> Dict[str, str]:
    """從 segment_end_state 取英文終態；只有中文時回空（不寫中文進英文提示詞）。"""
    if not isinstance(end_state, Mapping):
        return {}
    for key in ("planned_final_state_en", "planned_final_state"):
        value = end_state.get(key)
        if isinstance(value, Mapping) and value and not _has_cjk(value):
            return {str(k): str(v) for k, v in value.items() if str(v).strip()}
    return {}


def carry_sentence(end_state_en: Mapping[str, str]) -> str:
    """前段終態 → 下一段第 1 鏡的起始狀態句（正向寫法，不用禁止句）。"""
    bits = []
    for who, state in end_state_en.items():
        state = str(state).strip().rstrip(".")
        if not state:
            continue
        bits.append(f"{who} {state}" if who.lower() not in ("scene", "setting", "all") else state)
    if not bits:
        return ""
    return " Starting state carried over from the previous segment: " + "; ".join(bits) + "."


# ---------- 燒字來源（#138） ----------
LETTERING_TRIGGERS = re.compile(
    r"\b(crest|badge|emblem|insignia|logo|school patch|taxi|cab|bus|tram|truck|van|car doors?|"
    r"signboard|shop ?sign|street sign|poster|banner|billboard|plaque|label|graffiti|"
    r"(?:weathered|mottled|peeling|stained|grimy|crumbling|cracked|concrete|brick|plaster) walls?)\b",
    re.I,
)
NO_LETTERING_SENTENCE = (
    " Badges, crests, vehicle doors, signs and wall surfaces stay plain and unmarked, "
    "with no lettering, no logos and no graffiti."
)


def needs_no_lettering(*texts: str) -> bool:
    return any(LETTERING_TRIGGERS.search(t or "") for t in texts)


# ---------- 相鄰段檢查 ----------
def _first_shot_text(prompt: str) -> str:
    m = re.search(r"\[Shot 1\](.*?)(?=\[Shot 2\]|\n\n|$)", prompt or "", re.S)
    if not m:
        return ""
    text = m.group(1)
    # 帶入句本身會含前段終態（躺／坐），不能拿來判斷本段的起手姿勢。
    return re.sub(r"Starting state carried over from the previous segment:[^.]*\.", "", text)


def lint_adjacent(compiled: Sequence[Mapping[str, Any]],
                  extra_end_states: Optional[Mapping[str, Any]] = None,
                  extra_scenes: Optional[Mapping[str, str]] = None) -> Dict[str, List[str]]:
    """跨段連戲警告（只回 warnings，不擋）。

    compiled：編譯結果（segment_id、scene_id、h3_prompt、segment_end_state、metadata.style_lock）。
    extra_end_states／extra_scenes：不在這次輸入、但從 bindings 得知的段（只編部分段時用）。
    """
    warnings: List[str] = []
    end_states: Dict[str, Any] = dict(extra_end_states or {})
    scenes: Dict[str, str] = dict(extra_scenes or {})
    for seg in compiled:
        sid = str(seg.get("segment_id"))
        end_states[sid] = seg.get("segment_end_state")
        if seg.get("scene_id"):
            scenes[sid] = str(seg.get("scene_id"))
    prev = previous_segment_map(scenes.items())

    for seg in compiled:
        sid = str(seg.get("segment_id"))
        p = prev.get(sid)
        if not p:
            continue
        if seg.get("carry_previous_end_state") is False:
            continue  # 使用者明確關閉承接（例如段間有時間跳躍），不檢查 C1/C2
        prev_state = english_end_state(end_states.get(p))
        if not prev_state:
            warnings.append(
                f"{sid}: [C1: 前段無終態] 同場景前一段 {p} 沒有英文 segment_end_state（planned_final_state_en／"
                f"en_overlay.end_state_en），終態無法帶入本段第 1 鏡；人物會從參考圖站姿起手。"
            )
            continue
        prev_text = " ".join(prev_state.values())
        down = [x for x in postures(prev_text) if x in DOWN_POSTURES]
        first = _first_shot_text(str(seg.get("h3_prompt") or ""))
        if down and "standing" in postures(first) and not RISE_TRANSITION.search(first):
            warnings.append(
                f"{sid}: [C2: 段間姿勢矛盾] 前段 {p} 終態是 {'/'.join(down)}（{prev_text[:80]}），"
                f"本段第 1 鏡卻寫站／走且沒有起身動作；請改成從 {down[0]} 接起，或寫出 gets up／rises 的過程。"
            )

    # 同場景光線鎖一致（#139）：改光線要以場景為單位
    by_scene: Dict[str, Dict[str, List[str]]] = {}
    for seg in compiled:
        scene = seg.get("scene_id")
        lock = ((seg.get("metadata") or {}).get("style_lock") or {}).get("lighting_lock_line") \
            or (seg.get("metadata") or {}).get("lighting_lock_line")
        if not scene or not lock:
            continue
        by_scene.setdefault(str(scene), {}).setdefault(str(lock).strip(), []).append(str(seg.get("segment_id")))
    for scene, locks in by_scene.items():
        if len(locks) > 1:
            desc = "；".join(f"{', '.join(ids)} → {lock[:60]}" for lock, ids in locks.items())
            warnings.append(
                f"{scene}: [C3: 同場光線分裂] 同一場景的段落用了 {len(locks)} 種光線鎖（{desc}）；"
                f"改光線請以整個場景為單位，或改用後製統一調色。"
            )
    return {"warnings": warnings}


# ---------- 逐鏡畫面約束（#135 #136 #137，對齊噩盡島 G9b／G9d） ----------
SHOT_RE = re.compile(r"\[Shot (\d+)\](.*?)(?=\[Shot \d+\]|\n\n|\Z)", re.S)
SIZE_RE = re.compile(r"\b(ELS|EWS|VWS|WS|LS|MLS|MS|MCU|ECU|CU)\s*\((\d+)\s*mm,\s*([\d.]+)\s*m\)")
WIDE_SIZES = {"ELS", "EWS", "VWS", "WS", "LS", "MLS", "MS"}
END_MARKER = re.compile(
    r"\b(ends?|ending|comes? to rest|at the cut|until the cut|settles?|settling|stays?|remains?|holds?|freezes?)\b", re.I)
DIALOGUE_MARK = re.compile(r"<d>|visible speaking character", re.I)
STATIC_MARK = re.compile(r"\b(static|locked[- ]off|holds a static|stays? fixed)\b", re.I)
EMPTY_BG = re.compile(r"\b(background|behind (?:him|her|them|it))\b[^.;]*\b(empty|bare|plain|no one|nobody|unpopulated)\b", re.I)


def lint_shots(compiled: Sequence[Mapping[str, Any]]) -> Dict[str, List[str]]:
    """逐鏡文字檢查（只警告）：
    S1 一鏡動作過多（', then ' 超過 1 個）；S2 最後動作句沒有終態詞；
    S3 對白鏡景別比 MCU 寬或物距 >1.5m；S4 對白鏡沒寫固定機位；S5 對白鏡沒寫背景無人。
    """
    warnings: List[str] = []
    for seg in compiled:
        sid = str(seg.get("segment_id"))
        prompt = str(seg.get("h3_prompt") or "")
        for m in SHOT_RE.finditer(prompt):
            n, text = m.group(1), m.group(2)
            body = re.split(r"\bBlocking:", text)[0]
            if body.count(", then ") > 1:
                warnings.append(f"{sid} Shot {n}: [S1: 一鏡多動作] 有 {body.count(', then ') + 1} 個動作子句；"
                                f"8 步蒸餾模型只穩定演前 1–2 個，請拆鏡或合併為一個大動作。")
            if body.count(", then ") >= 1 and not END_MARKER.search(body.rsplit(", then ", 1)[-1]):
                warnings.append(f"{sid} Shot {n}: [S2: 缺終態] 最後一個動作沒有結束姿勢（ends／comes to rest／settles／stays），"
                                f"動作完成後人物會彈回參考圖姿勢。")
            if DIALOGUE_MARK.search(text):
                sm = SIZE_RE.search(text)
                if sm and (sm.group(1) in WIDE_SIZES or float(sm.group(3)) > 1.5):
                    warnings.append(f"{sid} Shot {n}: [S3: 對白鏡太遠] {sm.group(0)} 臉太小吃不到臉部參考圖、看不到對嘴；"
                                    f"建議 CU (85mm, 1.2m) 或 MCU (50mm, 1.5m)。")
                if not STATIC_MARK.search(text):
                    warnings.append(f"{sid} Shot {n}: [S4: 對白鏡運鏡] 對白鏡建議 holds a static shot（固定機位）。")
                if not EMPTY_BG.search(text):
                    warnings.append(f"{sid} Shot {n}: [S5: 背景未鎖] 對白鏡建議寫背景無人（the background behind him is empty），"
                                    f"否則模型會補沒綁參考圖的路人。")
    return {"warnings": warnings}
