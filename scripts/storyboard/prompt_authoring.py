#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""逐鏡提示詞撰寫審查（防偷懶）：檢查最終送件文字是不是「逐鏡親手寫」。

規格見 references/prompt-authoring.md。這一層只看「最終要送給 H3 的文字」，
不看 Layer 2，因為偷懶最常發生在編譯之後：用腳本把五小節套成同一組句子、
寫一堆給流程看的後設詞（authored／approved）、或把動作寫成一串禁止句。

規則（E 會擋階段 5 核准與送件；W 只提醒）：
  E30 五小節缺漏：每個 [Shot N] 都要有 Camera／Motion／Performance／Light／Sound。
  E31 五小節過薄：Motion、Performance 是「必寫詳細」的兩節，低於字數下限就擋。
  E32 Motion 沒有動作過程：沒有時間順序詞，或一半以上的句子在叫人別動。
  E33 套句：同段 ≥3 組重複句或單鏡 ≥2 句重複；跨段同一句出現在 ≥5 鏡、≥3 段。
  E34 後設詞：authored／approved／expressly named 這類只有流程看得懂、模型看不到的詞。
  E35 禁止句堆疊：單鏡禁止句 ≥4 句，或超過該鏡句數四成。
  E36 違背分鏡運鏡：分鏡寫了推、拉、搖、跟等運鏡，提示詞卻寫 static。
  E37 對白路由矛盾：分鏡標「嘴部可見」的對白，提示詞卻寫成畫外音、嘴閉著。
  E38 編譯後被改寫：segments 的 h3_prompt 與編譯器留下的指紋不符。
  W30 舊編譯產物沒有指紋，無法確認是否被改寫。
  W33 同段零星重複句（可能是刻意的連戲／防混臉錨）。
  W39 八成以上是固定鏡（運鏡屬階段 4 決定，只提醒）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

FIVE_PARTS = ("Camera", "Motion", "Performance", "Light", "Sound")

# 必寫詳細的兩節與下限（英文字數）。其餘三節也有最低字數，避免只寫一個詞交差。
MIN_WORDS = {
    "Camera": 8,
    "Motion": 18,
    "Performance": 8,
    "Light": 8,
    "Sound": 6,
}

SEQUENCE_WORDS = re.compile(
    r"\b(first|then|as|while|until|finally|before|after|when|once|meanwhile|next)\b", re.IGNORECASE
)

# 「叫人別動」的句子：在 Motion 裡占一半以上就代表沒寫動作。
STASIS_PATTERNS = re.compile(
    r"\b(hold(?:s|ing)? (?:the|his|her|their|its|a|still)|stay(?:s)? (?:still|fixed|unchanged|put)|"
    r"remain(?:s)? (?:still|fixed|unchanged|static)|no (?:added|new|extra) (?:step|gesture|movement|motion|action)|"
    r"keep(?:s)? (?:the )?(?:same|approved|authored) (?:pose|position|framing|crop))",
    re.IGNORECASE,
)

PROHIBITIVE = re.compile(
    r"\b(no|not|never|without|nothing|none|nor|avoid|must not|do not|does not|don't|doesn't|cannot|"
    r"only (?:an? |the )?(?:expressly|named|specified))\b",
    re.IGNORECASE,
)

# 防禦性禁止句：否定詞＋「控制畫面元素」的詞。描寫用的否定（no tremble、without tears）不算。
CONTROL_WORDS = re.compile(
    r"\b(appear\w*|add\w*|change\w*|shift\w*|cross\w*|enter\w*|crop\w*|frame|extra|new|other|unless|may|"
    r"allowed|visible|subtitles?|captions?|text|particles?|foley|music|figures?|person|people|faces?|step|gesture|prop)\b",
    re.IGNORECASE,
)

# 模型看不到流程，這些詞只對 agent 自己有意義，寫進提示詞等於空轉。
META_TERMS = [
    r"\bauthored\b",
    r"\bapproved (?:plate|crop|composition|framing|pose|asset|reference|sheet)\b",
    r"\bthe approved\b",
    r"\bexpressly named\b",
    r"\bsource[- ]described\b",
    r"\bas specified\b",
    r"\bthe specified (?:partner|object|subject|action)\b",
    r"\bthe described (?:contact|action|pose|subject)\b",
    r"\bthe listed\b",
    r"\bthe declared\b",
    r"\bprincipal action plane\b",
    r"\breadable acting\b",
    r"\bthe visible subject\b",
    r"\bper the (?:storyboard|script|layer ?2|stage ?\d)\b",
    r"\bstage[- ]?\d\b",
    r"\blayer ?2\b",
]

# 編譯器必須輸出、可以跨鏡重複的固定句（不算偷懶）。
COMPILER_BOILERPLATE = [
    re.compile(r"(narrates|speaks) off-screen over this shot; the visible characters keep their lips completely closed", re.I),
    re.compile(r"keep their lips completely closed and continue their actions", re.I),
    re.compile(r"the shot carries only the location ambience", re.I),
    re.compile(r"lips remain completely closed", re.I),
    re.compile(r"lips stay closed", re.I),
    re.compile(r"as a scene/style reference for spatial guidance", re.I),
    re.compile(r"no other figure on that sheet appears in this shot", re.I),
    re.compile(r"is the visible speaking character", re.I),
    re.compile(r"the final second holds still before the cut", re.I),
    re.compile(r"off-screen over this shot", re.I),
    re.compile(r"<d>", re.I),
]

STATIC_HEAD = re.compile(r"\b(holds a steady static shot|holds a static shot|static shot|locked[- ]off|stays static|remains static)\b", re.I)
# 分鏡（中文或英文）寫了實際運鏡
STORYBOARD_MOVES = re.compile(
    r"(推|拉|搖|移|跟|升|降|環繞|手持|橫移|前進|後退|甩|dolly|push|pull|pan|tilt|track|truck|crane|pedestal|orbit|arc|follow|zoom|handheld)",
    re.I,
)
STORYBOARD_STATIC = re.compile(r"^\s*(固定|靜止|不動|static|locked)", re.I)

SHOT_SPLIT = re.compile(r"(\[Shot\s+\d+\])", re.I)
PART_LABEL = re.compile(r"\b(Camera|Motion|Performance|Light|Sound):", re.I)


def _words(text: str) -> int:
    return len(re.findall(r"[A-Za-z][A-Za-z'\-]*", text))


def _sentences(text: str) -> List[str]:
    text = re.sub(r"<d>.*?</d>", " ", text, flags=re.S)
    parts = re.split(r"(?<=[.;!?])\s+|\s+(?=(?:Camera|Motion|Performance|Light|Sound):)", text)
    return [p.strip() for p in parts if p and p.strip()]


def _normalize(sentence: str) -> str:
    s = sentence.lower()
    s = re.sub(r"\b(camera|motion|performance|light|sound):", " ", s)
    s = re.sub(r"<(subject|picture|audio) \d+>", "<x>", s)
    s = re.sub(r"\(s\d+\)", "", s)
    s = re.sub(r"\d+(?:\.\d+)?", "#", s)
    s = re.sub(r"[^a-z#<>' ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _is_boilerplate(sentence: str) -> bool:
    return any(p.search(sentence) for p in COMPILER_BOILERPLATE)


def detailed_description(prompt: str) -> str:
    m = re.search(r"detailed_description:(.*?)(?:\n\s*\n[a-z_]+:|\Z)", prompt, re.S | re.I)
    return m.group(1).strip() if m else prompt


def split_shots(prompt: str) -> List[str]:
    det = detailed_description(prompt)
    pieces = SHOT_SPLIT.split(det)
    shots: List[str] = []
    for i in range(1, len(pieces), 2):
        shots.append((pieces[i] + pieces[i + 1] if i + 1 < len(pieces) else pieces[i]).strip())
    return shots


def split_parts(shot_text: str) -> Tuple[str, Dict[str, str]]:
    """回傳（頭句與五小節以外的文字, {小節: 內容}）。"""
    marks = list(PART_LABEL.finditer(shot_text))
    if not marks:
        return shot_text, {}
    head = shot_text[: marks[0].start()]
    parts: Dict[str, str] = {}
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(shot_text)
        label = m.group(1).capitalize()
        parts[label] = (parts.get(label, "") + " " + shot_text[m.end():end]).strip()
    return head, parts


def _strip_speech(text: str) -> str:
    """Sound 節後面接的台詞／畫外音說明是編譯器加的，不算進小節字數。"""
    cut = re.search(r"(<Subject \d+>|\bThe line is heard\b|\b\w[\w ]{0,40}\(S\d+\))", text)
    return text[: cut.start()] if cut else text


def _shot_has_people(head: str, authored: Optional[Dict[str, Any]]) -> bool:
    if authored is not None:
        if authored.get("character_ids") or authored.get("face_subject_ids"):
            return True
        binding = authored.get("_stage5_reference_binding") or {}
        if binding.get("visual_subject_ids"):
            return True
        return False
    return bool(re.search(r"<Subject \d+>|\b(he|she|his|her|they|man|woman|boy|girl)\b", head, re.I))


def _visible_mouth_dialogue(authored: Dict[str, Any]) -> bool:
    dlg = authored.get("dialogue_and_audio") or {}
    for ev in dlg.get("speech_events") or []:
        if str(ev.get("audio_route", "")).lower() in ("visible_mouth_dialogue", "on_screen", "onscreen"):
            return True
    return str(dlg.get("visibility", "")).lower() in ("onscreen", "on_screen", "visible")


def audit_segment(prompt: str, authored_shots: Optional[Sequence[Dict[str, Any]]] = None,
                  segment_id: str = "") -> Dict[str, Any]:
    """單段檢查：E30–E37。"""
    errors: List[str] = []
    warnings: List[str] = []
    shots = split_shots(prompt)
    authored = list(authored_shots or [])
    aligned = len(authored) == len(shots)
    seen_in_segment: Dict[str, List[int]] = defaultdict(list)
    static_flags: List[bool] = []

    for idx, shot in enumerate(shots, start=1):
        a = authored[idx - 1] if aligned else None
        head, parts = split_parts(shot)
        tag = f"[Shot {idx}]"
        is_static = bool(STATIC_HEAD.search(head) or re.match(r"\s*(static|locked[- ]off)\b", parts.get("Camera", ""), re.I))
        static_flags.append(is_static)

        missing = [p for p in FIVE_PARTS if p not in parts]
        if missing:
            errors.append(f"[E30: 五小節缺漏] {tag} 缺 {', '.join(missing)}；每鏡都要依分鏡逐節寫出，見 references/prompt-authoring.md。")
        has_people = _shot_has_people(head, a)
        for name, body in parts.items():
            body_words = _words(_strip_speech(body) if name == "Sound" else body)
            floor = MIN_WORDS.get(name, 0)
            if name == "Performance" and not has_people:
                floor = 6  # 空鏡也要寫物件或環境怎麼「演」
            if body_words < floor:
                errors.append(f"[E31: 小節過薄] {tag} {name} 只有 {body_words} 字（下限 {floor}）；必須寫出這一鏡具體看得到的內容。")

        motion = parts.get("Motion", "")
        if motion:
            msents = _sentences(motion)
            # 句子裡只要還有時間順序（first／then／as…）就算有寫動作過程
            stasis = sum(1 for s in msents
                         if (STASIS_PATTERNS.search(s) or PROHIBITIVE.search(s)) and not SEQUENCE_WORDS.search(s))
            if not SEQUENCE_WORDS.search(motion):
                errors.append(f"[E32: Motion 沒有過程] {tag} Motion 沒有 first／then／as／finally 這類時間順序，寫成了狀態而不是動作。")
            elif msents and stasis * 2 >= len(msents):
                errors.append(f"[E32: Motion 沒有過程] {tag} Motion 有 {stasis}/{len(msents)} 句在叫人別動；改寫成這一鏡實際發生的動作。")

        for term in META_TERMS:
            m = re.search(term, shot, re.I)
            if m:
                errors.append(f"[E34: 後設詞] {tag} 出現「{m.group(0)}」：模型看不到流程與核准紀錄，請直接寫畫面裡的東西。")
                break

        sents = [s for s in _sentences(shot) if not _is_boilerplate(s)]
        prohib = [s for s in sents if PROHIBITIVE.search(s) and CONTROL_WORDS.search(s)]
        if len(prohib) >= 4 or (len(sents) >= 5 and len(prohib) / len(sents) > 0.4):
            errors.append(f"[E35: 禁止句堆疊] {tag} {len(prohib)}/{len(sents)} 句是禁止句；把要的畫面正向寫出來，禁止句最多三句。")

        # 套句只比對 agent 自己寫的小節（頭句、Camera 規格、台詞說明由編譯器產生或本來就該一致）
        authored_text = " ".join(parts.get(n, "") for n in ("Motion", "Performance", "Light", "Sound"))
        for s in _sentences(authored_text):
            if _is_boilerplate(s):
                continue
            key = _normalize(s)
            if len(key.split()) >= 8:
                seen_in_segment[key].append(idx)

        if a is not None:
            movement = str((a.get("camera_optics") or {}).get("movement", ""))
            if movement and STORYBOARD_MOVES.search(movement) and not STORYBOARD_STATIC.search(movement) and is_static:
                errors.append(f"[E36: 違背分鏡運鏡] {tag} 分鏡寫「{movement[:30]}」，提示詞卻是 static。")
            if _visible_mouth_dialogue(a) and "<d>" not in shot and re.search(r"lips (?:completely )?closed|off-screen", shot, re.I):
                errors.append(f"[E37: 對白路由矛盾] {tag} 分鏡是嘴部可見的對白，提示詞卻寫成畫外音、嘴閉著；H3 會失去口型。")

    dups = {k: sorted(set(v)) for k, v in seen_in_segment.items() if len(set(v)) >= 2}
    per_shot = defaultdict(int)
    for idxs in dups.values():
        for i in idxs:
            per_shot[i] += 1
    systematic = len(dups) >= 3 or any(n >= 2 for n in per_shot.values())
    for key, uniq in dups.items():
        msg = f"同一句出現在 Shot {', '.join(map(str, uniq))}：「{key[:80]}…」"
        if systematic:
            errors.append(f"[E33: 套句] {msg}；整段多處重複，像是套模板，每鏡要依自己的分鏡重寫。")
        else:
            warnings.append(f"[W33: 重複句] {msg}；若是刻意的連戲／防混臉錨可留，否則改寫。")

    return {
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "details": {"shots": len(shots), "static_flags": static_flags, "sentence_keys": dict(seen_in_segment)},
    }


def prompt_fingerprint(prompt: str) -> str:
    """只對 detailed_description 取指紋：subject_definitions／retention 的自動修正（audit --fix）不算改寫。"""
    return hashlib.sha256(detailed_description(prompt).encode("utf-8")).hexdigest()


def audit_segments(segments: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """整批檢查：逐段 E30–E37，加上跨段 E33、E38、E39、W30。"""
    errors: List[str] = []
    warnings: List[str] = []
    per_segment: Dict[str, Dict[str, Any]] = {}
    cross: Dict[str, List[str]] = defaultdict(list)
    static_total = 0
    shot_total = 0
    missing_fp = 0

    for n, seg in enumerate(segments, start=1):
        sid = str(seg.get("segment_id") or seg.get("id") or f"seg-{n}")
        prompt = seg.get("h3_prompt") or seg.get("prompt") or ""
        res = audit_segment(prompt, seg.get("shots"), sid)
        per_segment[sid] = res
        errors.extend(f"{sid}: {e}" for e in res["errors"])
        warnings.extend(f"{sid}: {w}" for w in res["warnings"])
        for key, idxs in res["details"]["sentence_keys"].items():
            for i in sorted(set(idxs)):
                cross[key].append(f"{sid}#{i}")
        flags = res["details"]["static_flags"]
        static_total += sum(flags)
        shot_total += len(flags)

        fp = (seg.get("metadata") or {}).get("compiled_prompt_sha256")
        if fp:
            if fp != prompt_fingerprint(prompt):
                errors.append(f"{sid}: [E38: 編譯後被改寫] detailed_description 與編譯指紋不符；五小節要寫在 Layer 2 的 five_part_en，再重新編譯，不可在編譯後用腳本或手動覆寫。")
        else:
            missing_fp += 1

    for key, where in cross.items():
        segs = {w.split("#")[0] for w in where}
        if len(where) >= 5 and len(segs) >= 3:
            errors.append(f"[E33: 跨段套句] 同一句出現在 {len(where)} 鏡（{', '.join(where[:6])}{'…' if len(where) > 6 else ''}）：「{key[:80]}…」")

    if shot_total >= 6 and static_total / shot_total >= 0.8:
        warnings.append(
            f"[W39: 大量固定鏡] {static_total}/{shot_total} 鏡是 static；運鏡是階段 4 分鏡的決定，請確認是刻意的，不是預設值。"
        )
    if missing_fp:
        warnings.append(f"[W30: 無編譯指紋] {missing_fp} 段沒有 compiled_prompt_sha256（舊版編譯器產物），無法確認是否在編譯後被改寫。")

    return {"passed": not errors, "errors": errors, "warnings": warnings, "segments": per_segment}


def _static_reasoned(segments: Sequence[Dict[str, Any]]) -> bool:
    for seg in segments:
        for shot in seg.get("shots") or []:
            if (shot.get("camera_optics") or {}).get("static_reason"):
                return True
    return False


def load_segments(paths: Sequence[Path]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for p in paths:
        data = json.loads(Path(p).read_text(encoding="utf-8-sig"))
        segs = data if isinstance(data, list) else data.get("segments", [data])
        out.extend(s for s in segs if isinstance(s, dict))
    return out


def audit_files(paths: Sequence[Path]) -> Dict[str, Any]:
    segs = load_segments(paths)
    res = audit_segments(segs)
    return res


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="逐鏡提示詞撰寫審查（防偷懶，E30–E39）")
    ap.add_argument("segments", nargs="*", help="segments-ep*.json；省略時讀 --root 下全部")
    ap.add_argument("--root", default=".", help="專案根目錄")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    paths = [Path(p) for p in args.segments] or sorted(Path(args.root).glob("segments-ep*.json"))
    if not paths:
        print("找不到 segments-ep*.json", file=sys.stderr)
        return 2
    res = audit_files(paths)
    if args.json:
        print(json.dumps({k: v for k, v in res.items() if k != "segments"}, ensure_ascii=False, indent=2))
    else:
        for e in res["errors"]:
            print("❌", e)
        for w in res["warnings"]:
            print("⚠️", w)
        print(f"撰寫審查：{'PASS' if res['passed'] else 'FAIL'}（錯誤 {len(res['errors'])}、警告 {len(res['warnings'])}）")
    return 0 if res["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
