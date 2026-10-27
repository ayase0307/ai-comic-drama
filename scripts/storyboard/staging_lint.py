#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""h3d staging（PR-R6）：站位／視線／運鏡閘門——把分鏡審查規則做成確定性 lint，兩個 backend 都適用。

來源：老大 2026-10-26 23:37 的標準（站位、看向對方、自然動作、運用分鏡及運鏡）與《噩盡島》ch02 `build.py` lint；
寫法規範對照 `references/storyboard/continuity-ledger.md` §2（審查清單）、§4（站位附表）、§5（正反打）。

證據等級（只有 ch02 EP04 的有效抽，pass 16／fail 13／warn 3）：
  - 左右站位對調 5 抽（measured）；寫明「left to right: A, B, C」或 rightmost 後 S04-a t2、S01-c t2 一抽就過（measured，2 抽）。
  - 對鏡頭站著講／視線沒看對方 4 抽（measured）；加視線句、側身朝對方後 S01-d t4 過（measured，1 抽）。
  - 跨段站位一致、多人同步動作逐人寫、慢詞：寫法規範／推定（inferred），沒有對照組。
  所以**預設全部是警告**；專案可 `h3d decide staging_gate strict --quote "<原話>"` 把 measured 的三條（D06–D08）升成錯誤。

「每鏡剛好 1 個運鏡句」與「鏡長 ≥2 s」在 `audit_refs_and_segments.py --lint-h3` 已是錯誤（E6／E14／E4，兩個 backend 共用），
這裡不重複實作；只補「整段都是固定機位」的提醒（D13）。

規則（碼沿用 director_lint 的 D 系列，D01–D05 是階段 4 分鏡層）：
  D06 面向鏡頭：faces/facing/looks at/toward the camera|lens|viewer、breaks the fourth wall、面向／直視鏡頭…（measured，可 strict）
  D07 對話段缺視線句：有台詞且畫面上 ≥2 個具名角色，整段沒有任何視線句（measured，可 strict）
  D08 多人鏡缺左到右站位句：同一鏡 ≥2 個具名角色，沒寫「left to right: …」／rightmost／leftmost，
      也沒有至少兩人各自緊貼 frame left／on the right 之類的畫面側（measured，可 strict）
  D09 站位和 positions 不一致：提示詞「left to right」名單順序和段落 positions.order_lr 相反（inferred）
  D10 跨段站位翻轉：相鄰兩段 positions 的共同角色左右順序對調，且後段沒宣告 metadata.staging_reset（inferred）
  D11 多人同步動作：all three／both of them／in unison… 一起抬頭、轉身，建議逐人寫（ch02 S06-b t1→t2 修法，inferred）
  D12 慢詞：slowly、gradually、near-freeze、hangs poised…（H3 會凍住；h3-video-prompting／h3-combat-impact 規範，inferred）
  D13 全段固定機位：每一鏡都是 static（建議至少一鏡有運鏡，inferred）
  D14 多人段沒有 positions：remix 多人段沒宣告 positions（order_lr／axis_side／facing），R6 只能看文字（只在 remix 提示）

豁免：段落 `metadata.staging_waivers`（或段層 `staging_waivers`）：[{"code": "D06", "reason": "…", "quote": "<使用者原話>"}]，
沒有 quote 不算豁免（例如刻意讓角色對鏡頭說話）。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

HERE = Path(__file__).resolve().parent
for _p in (str(HERE), str(HERE.parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import refcheck  # noqa: E402

VIDEO_BACKENDS = ("ref2va", "remix")
STRICTABLE = ("D06", "D07", "D08")
TITLES = {
    "D06": "面向鏡頭", "D07": "對話段缺視線句", "D08": "多人鏡缺左到右站位句", "D09": "站位和 positions 不一致",
    "D10": "跨段站位翻轉", "D11": "多人同步動作", "D12": "慢詞", "D13": "全段固定機位", "D14": "多人段沒有 positions",
}

_CAM = r"(?:camera|lens|viewer|viewers|audience)"
FACING_CAMERA = re.compile(
    rf"\b(?:faces?|facing|looks?|looking|stares?|staring|gazes?|gazing|glances?|glancing|turns?|turning|speaks?|talks?|"
    rf"smiles?|grins?|walks?|walking|steps?|stepping|leans?|leaning|addresses|addressing)"
    rf"(?:\s+\w+){{0,3}}?\s+(?:directly\s+|straight\s+)?(?:at|to|toward|towards|into)\s+the\s+{_CAM}\b"
    rf"|\b(?:faces?|facing)\s+(?:\w+\s+)?the\s+{_CAM}\b|\bbreaks?\s+the\s+fourth\s+wall\b|\bdirect\s+address\b"
    rf"|面向鏡頭|面對鏡頭|看向鏡頭|直視鏡頭|對著鏡頭|看鏡頭", re.I)
_NEGATION_BEFORE = re.compile(r"\b(?:not|never|no|without|avoids?|avoiding|away from|instead of)\b[^.;]{0,30}$", re.I)

GAZE = re.compile(
    r"\beyes\s+(?:on|fixed on|locked on|still on|follow\w*)\b|\blooking\s+(?:\w+\s+)?(?:at|in the eye|into (?:his|her|their) eyes)\b"
    r"|\blooks?\s+(?:\w+\s+)?(?:at|in the eye)\b|\bglanc\w*\s+(?:\w+\s+)?(?:at|back|over|toward)\b|\bglar\w*\s+(?:\w+\s+)?at\b"
    r"|\bturns?\s+(?:\w+\s+){0,2}(?:to|toward|towards)\b|\b(?:grins?|smiles?|frowns?|squints?|stares?|winks?|nods?|scowls?|sneers?)\s+at\b"
    r"|\bgaze\b|\bmeets?\s+(?:his|her|their)\s+eyes\b|\bwatch(?:es|ing)\b|\beye\s+contact\b"
    r"|看向|看著|盯著|望向|注視|瞪著|瞥向|視線", re.I)

ORDER_PHRASE = re.compile(r"\b(?:from\s+)?(?:left\s+to\s+right|right\s+to\s+left)\b|\b(?:right|left)most\b|由左到右|從左到右", re.I)
SIDE_MARKER = re.compile(
    r"\b(?:on|at|to|along)\s+(?:the\s+)?(?:far\s+)?(?:frame[- ]|screen[- ])?(?:left|right)\b|\bframe[- ](?:left|right)\b"
    r"|\bscreen[- ](?:left|right)\b|\b(?:left|right)\s+edge\s+of\s+(?:the\s+)?frame\b|\b(?:center|centre)[- ](?:left|right)\b"
    r"|畫左|畫右|畫面左|畫面右", re.I)
LTR_LIST = re.compile(r"\bleft\s+to\s+right\s*[:,]?\s*([^.;]+)", re.I)

SYNC_ACTION = re.compile(
    r"\b(?:all\s+(?:three|four|five)(?:\s+of\s+them)?|both\s+of\s+them|the\s+(?:two|three|four)\s+of\s+them|they\s+all|"
    r"all\s+of\s+them|everyone|everybody)\b[^.;]{0,40}?\b(?:look|looks|raise|raises|turn|turns|nod|nods|stand|stands|"
    r"lift|lifts|glance|glances|jump|jumps|gasp|gasps|freeze|freezes|step|steps)\b|\bin\s+unison\b|\bsimultaneously\b",
    re.I)
SLOW_WORDS = ("slowly", "gradually", "slow motion", "slow-motion", "near-freeze", "hangs poised", "poised and still",
              "like a meteor", "for half a second", "for two frames")
STATIC_SHOT = re.compile(r"\bstatic\s+shot\b|\bholds?\s+(?:a\s+)?static\b|\blocked[- ]off\b|\bholds?\s+still\b", re.I)
CAMERA_MOVE = re.compile(r"\bcamera\s+(?:\w+\s+){0,2}?(?:push|pull|pan|tilt|truck|pedestal|zoom|track|dolly|dollies|crane|"
                         r"follow|orbit|arc|move|glide|swing|rise|rises|lower|drift)\w*", re.I)
_INTRO = re.compile(r"<(?:Video|Subject|Picture)\s*\d+>\s+is\s+[^.]*\.", re.I)
_INTRO_NAME = re.compile(r"<(Video|Subject)\s*(\d+)>\s+is\s+((?:[A-Z][\w'-]*)(?:\s+[A-Z][\w'-]*){0,3})")
_DIALOGUE = re.compile(r"<d>|\(S\d+\)", re.I)


# ---------------------------------------------------------------------------
# 小工具
# ---------------------------------------------------------------------------
def _meta(seg: Dict[str, Any]) -> Dict[str, Any]:
    return seg.get("metadata") or {}


def _waived_codes(seg: Dict[str, Any]) -> Tuple[set, List[str]]:
    ok, bad = set(), []
    for item in list(_meta(seg).get("staging_waivers") or []) + list(seg.get("staging_waivers") or []):
        if not isinstance(item, dict) or not item.get("code"):
            continue
        if str(item.get("quote") or "").strip():
            ok.add(str(item["code"]).upper())
        else:
            bad.append(str(item["code"]).upper())
    return ok, bad


def _shot_blocks(body: str) -> List[str]:
    parts = re.split(r"\[Shot\s+\d+\]", body, flags=re.I)
    return parts[1:] if len(parts) > 1 else [body]


def roster(seg: Dict[str, Any], lexicon: Optional[Dict[str, Dict[str, Any]]] = None) -> Dict[str, Dict[str, Any]]:
    """{asset_id: {"names": [英文名], "regexes": [Pattern], "kind"}}：段落裡可能上畫的具名角色（演員／生物）。"""
    out: Dict[str, Dict[str, Any]] = {}
    prompt = refcheck._prompt_of(seg)
    label_to_id = {}
    for ref in seg.get("refmods") or []:
        if isinstance(ref, dict) and ref.get("label") and ref.get("id"):
            label_to_id[str(ref["label"]).replace(" ", "")] = (str(ref["id"]), str(ref.get("kind") or "actor"))

    def add(asset_id: str, name: str, kind: str = "actor") -> None:
        rx = refcheck._literal_regex(name)
        if rx is None or kind in ("scene", "prop", "extras"):
            return
        item = out.setdefault(asset_id, {"names": [], "regexes": [], "kind": kind})
        if name not in item["names"]:
            item["names"].append(name)
            item["regexes"].append(rx)

    for m in _INTRO_NAME.finditer(prompt):
        label = f"<{m.group(1)}{m.group(2)}>"
        asset_id, kind = label_to_id.get(label, (f"{m.group(1)}{m.group(2)}:{m.group(3)}", "actor"))
        add(asset_id, m.group(3).strip(), kind)
    for ref in seg.get("refmods") or []:
        if isinstance(ref, dict) and ref.get("id") and ref.get("display_name"):
            add(str(ref["id"]), str(ref["display_name"]), str(ref.get("kind") or "actor"))
    if lexicon:
        for asset_id, item in lexicon.items():
            if item.get("kind") not in ("actor", "creature"):
                continue
            for term in item.get("terms") or []:
                if not term.startswith("re:"):
                    add(asset_id, term, item["kind"])
    return out


def _names_in(text: str, people: Dict[str, Dict[str, Any]]) -> List[str]:
    found = []
    for asset_id, item in people.items():
        if any(rx.search(text) for rx in item["regexes"]):
            found.append(asset_id)
    return found


def _first_pos(text: str, item: Dict[str, Any]) -> Optional[Tuple[int, int]]:
    best = None
    for rx in item["regexes"]:
        m = rx.search(text)
        if m and (best is None or m.start() < best[0]):
            best = (m.start(), m.end())
    return best


def _side_marked(text: str, item: Dict[str, Any], window: int = 45) -> bool:
    for rx in item["regexes"]:
        for m in rx.finditer(text):
            near = text[max(0, m.start() - window):m.start()] + " | " + text[m.end():m.end() + window]
            if SIDE_MARKER.search(near):
                return True
    return False


TWO_SHOT = re.compile(r"\btwo[- ]shot\b|\bside by side\b|\bboth of them\b|\bthe two of them\b|雙人", re.I)


def _dedupe_names(ids: List[str], people: Dict[str, Dict[str, Any]]) -> List[str]:
    """同一人被抓成兩個名字（例如 intro 抓到 "Lai Yixin's"）時只算一次。"""
    out: List[str] = []
    for asset_id in ids:
        names = [n.lower() for n in (people.get(asset_id) or {}).get("names", [asset_id])]
        dup = False
        for other in out:
            other_names = [n.lower() for n in (people.get(other) or {}).get("names", [other])]
            if any(a.startswith(b) or b.startswith(a) for a in names for b in other_names):
                dup = True
                break
        if not dup:
            out.append(asset_id)
    return out


def _intro_side_marked(block: str, item: Dict[str, Any]) -> bool:
    for m in _INTRO.finditer(block):
        sentence = m.group(0)
        head = sentence[:sentence.find(",")] if "," in sentence else sentence[:60]
        if any(rx.search(head) for rx in item["regexes"]) and SIDE_MARKER.search(sentence):
            return True
    return False


def _onscreen_count(seg: Dict[str, Any], body: str, people: Dict[str, Dict[str, Any]]) -> int:
    actors = {str(r.get("id")) for r in seg.get("refmods") or []
              if isinstance(r, dict) and r.get("kind") in ("actor", "creature") and r.get("id")}
    visible = set()
    for shot in seg.get("shots") or []:
        if isinstance(shot, dict):
            visible.update(str(x) for x in shot.get("visual_subject_ids") or shot.get("character_ids") or [])
    return max(len(actors), len(visible), len(_names_in(body, people)))


def _positions_order(seg: Dict[str, Any]) -> List[str]:
    pos = [p for p in seg.get("positions") or [] if isinstance(p, dict) and p.get("id")
           and isinstance(p.get("order_lr"), int) and not isinstance(p.get("order_lr"), bool)]
    return [str(p["id"]) for p in sorted(pos, key=lambda p: p["order_lr"])]


# ---------------------------------------------------------------------------
# 單段
# ---------------------------------------------------------------------------
def lint_segment(seg: Dict[str, Any], backend: str = "ref2va", prev: Optional[Dict[str, Any]] = None,
                 lexicon: Optional[Dict[str, Dict[str, Any]]] = None, strict: bool = False,
                 anchors: Iterable[str] = ()) -> List[Dict[str, Any]]:
    """回傳 findings：[{code, level, shot, message}]；level＝warning，strict 時 D06–D08 為 error。"""
    seg_id = str(seg.get("segment_id") or seg.get("id") or "segment")
    body = refcheck.strip_fixed(refcheck.detail_body(refcheck._prompt_of(seg)), (),
                                [a for a in list(anchors) + [_meta(seg).get("style_anchor_en")] if a])
    findings: List[Dict[str, Any]] = []
    waived, bad_waivers = _waived_codes(seg)

    def add(code: str, message: str, shot: Optional[int] = None) -> None:
        if code in waived:
            return
        level = "error" if strict and code in STRICTABLE else "warning"
        where = f" Shot{shot}" if shot else ""
        findings.append({"code": code, "level": level, "shot": shot,
                         "message": f"[{code}: {TITLES[code]}] {seg_id}{where}：{message}"})

    for code in bad_waivers:
        findings.append({"code": code, "level": "warning", "shot": None,
                         "message": f"[{code}: 豁免缺原話] {seg_id} staging_waivers 的 {code} 沒有使用者原話 quote，不算豁免"})
    if not body.strip():
        return findings

    people = roster(seg, lexicon)
    blocks = _shot_blocks(body)

    # D06 面向鏡頭
    for idx, block in enumerate(blocks, 1):
        for m in FACING_CAMERA.finditer(block):
            if _NEGATION_BEFORE.search(block[max(0, m.start() - 40):m.start()]):
                continue
            add("D06", f"「{m.group(0)}」——ch02 EP04 有 4 抽對鏡頭站著講（measured）；改成側身朝對方、視線落在對方臉上；"
                       f"刻意對鏡頭說話請寫 staging_waivers（code D06＋使用者原話）", idx)
            break
    for p in seg.get("positions") or []:
        if isinstance(p, dict) and p.get("facing") == "toward":
            add("D06", f"positions 把 {p.get('id')} 標成 facing=toward（朝鏡頭）；刻意的話請寫 staging_waivers")

    count = _onscreen_count(seg, body, people)
    # D07 對話段缺視線句
    if _DIALOGUE.search(body) and count >= 2:
        hit = None
        acting = _INTRO.sub(" ", body)  # 外觀介紹句的「cool gaze」不算視線句
        for m in GAZE.finditer(acting):
            tail = acting[m.end():m.end() + 30]
            if re.match(rf"\s*(?:the\s+){_CAM}\b", tail, re.I):
                continue
            hit = m
            break
        if hit is None:
            add("D07", "有台詞、畫面上 ≥2 個角色，整段沒有任何視線句（看對方臉／看手中道具／看畫外某物…）；"
                       "ch02 EP04 對鏡頭站著講 4 抽（measured），continuity-ledger §2 第 4 條")

    # D08 多人鏡缺左到右站位句
    shots_meta = [s for s in seg.get("shots") or [] if isinstance(s, dict)]
    aligned = len(shots_meta) == len(blocks)
    for idx, block in enumerate(blocks, 1):
        stripped = _INTRO.sub(" ", block)
        names = _names_in(stripped, people)
        if aligned:
            ids = [str(x) for x in shots_meta[idx - 1].get("visual_subject_ids")
                   or shots_meta[idx - 1].get("character_ids") or []]
            if ids:
                names = ids
        names = _dedupe_names(names, people)
        if len(names) < 2 or ORDER_PHRASE.search(block):
            continue
        if len(names) == 2:
            # 兩人：measured 的對調全在三人段，兩人鏡只在明寫雙人構圖、且兩人都沒交代畫面側時提醒
            if not TWO_SHOT.search(stripped):
                continue
            intro_marked = {n for n in names if n in people and _intro_side_marked(block, people[n])}
            marked = [n for n in names if n in intro_marked or (n in people and _side_marked(stripped, people[n]))]
            if len(marked) >= 2:
                continue
            add("D08", "雙人鏡沒交代兩人的畫面側（frame left／on the right…），也沒寫 left to right；"
                       "寫明可避免左右對調（continuity-ledger §4、§5）", idx)
            continue
        intro_marked = {n for n in names if n in people and _intro_side_marked(block, people[n])}
        marked = [n for n in names if n in intro_marked or (n in people and _side_marked(stripped, people[n]))]
        if len(marked) >= len(names) - 1 and any(n not in intro_marked and n in marked for n in names):
            continue  # 每個人（至多一人除外）都在動作句裡緊貼畫面側，等同寫了左到右
        add("D08", f"同鏡有 {len(names)} 個具名角色，沒寫「left to right: A, B, C」或 rightmost／leftmost；"
                   f"ch02 EP04 左右站位對調 5 抽全在三人段（measured），補上左到右名單後 S04-a t2、S01-c t2 一抽就過", idx)

    # D09 提示詞左到右名單 vs positions
    order = _positions_order(seg)
    if len(order) >= 2:
        for idx, block in enumerate(blocks, 1):
            for m in LTR_LIST.finditer(block):
                segment_text = m.group(1)
                listed = []
                for asset_id in order:
                    if asset_id in people:
                        pos = _first_pos(segment_text, people[asset_id])
                        if pos is not None:
                            listed.append((pos[0], asset_id))
                listed_ids = [a for _, a in sorted(listed)]
                expected = [a for a in order if a in listed_ids]
                if len(listed_ids) >= 2 and listed_ids != expected:
                    add("D09", f"提示詞寫的左到右是 {', '.join(listed_ids)}，positions.order_lr 是 {', '.join(expected)}；"
                               f"兩邊要一致（以分鏡站位附表為準）", idx)

    # D10 跨段站位翻轉
    if prev is not None and not _meta(seg).get("staging_reset"):
        a, b = _positions_order(prev), order
        shared = [x for x in a if x in b]
        if len(shared) >= 2 and [x for x in b if x in shared] != shared:
            add("D10", f"上一段 {prev.get('segment_id')} 左到右 {', '.join(shared)}，本段變成 "
                       f"{', '.join(x for x in b if x in shared)}；同一場不換軸就不要對調，真的要換請先給重建空間的鏡頭並在 "
                       f"metadata.staging_reset 寫原因（continuity-ledger §5）")

    # D11 多人同步動作
    m = SYNC_ACTION.search(body)
    if m:
        add("D11", f"「{m.group(0)}」——多人同步動作請逐人寫（誰先、誰後、各自什麼動作）；ch02 S06-b t1→t2 的修法（inferred）")

    # D12 慢詞
    low = " " + body.lower() + " "
    slow = [w for w in SLOW_WORDS if re.search(rf"(?<![a-z]){re.escape(w)}(?![a-z])", low)]
    if slow:
        add("D12", f"{', '.join(slow)}——H3 容易把慢詞演成定住；改寫成具體動作與幅度（inferred）")

    # D13 全段固定機位
    if len(blocks) >= 2 and all(STATIC_SHOT.search(b) and not CAMERA_MOVE.search(b) for b in blocks):
        add("D13", "每一鏡都是固定機位；老大 23:37 要求運用分鏡及運鏡，建議至少一鏡有推／移／搖（inferred）")

    # D14 remix 多人段沒有 positions
    if backend == "remix" and count >= 2 and not seg.get("positions"):
        add("D14", "多人段沒有 positions（[{id, order_lr, axis_side, facing}]）；D09／D10 無法比對，只能看文字")
    return findings


def lint_segments(segments: List[Dict[str, Any]], backend_of, lexicon=None, strict: bool = False,
                  anchors: Iterable[str] = ()) -> List[Dict[str, Any]]:
    """依序跑；D10 只比相鄰且同 scene_id（沒有 scene_id 就視為同場）的兩段。"""
    rows = []
    prev = None
    for seg in segments:
        same_scene = prev is not None and (not seg.get("scene_id") or not prev.get("scene_id")
                                           or seg.get("scene_id") == prev.get("scene_id"))
        backend = backend_of(seg)
        findings = lint_segment(seg, backend, prev if same_scene else None, lexicon, strict, anchors)
        rows.append({"segment_id": seg.get("segment_id"), "backend": backend, "findings": findings,
                     "ok": not any(f["level"] == "error" for f in findings)})
        prev = seg
    return rows


def project_strict(root: Optional[Path]) -> bool:
    if root is None:
        return False
    try:
        import decisions as decisions_mod
        return decisions_mod.staging_gate(Path(root)) == "strict"
    except Exception:  # pragma: no cover
        return False


def split_findings(findings: List[Dict[str, Any]]) -> Tuple[List[str], List[str]]:
    errors = [f["message"] for f in findings if f["level"] == "error"]
    warnings = [f["message"] for f in findings if f["level"] != "error"]
    return errors, warnings


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="h3d staging",
        description="站位／視線／運鏡閘門（PR-R6，兩個 backend 都適用）：D06 面向鏡頭、D07 對話缺視線、D08 多人缺左到右、"
                    "D09 與 positions 不一致、D10 跨段翻轉、D11 同步動作、D12 慢詞、D13 全段固定、D14 remix 多人缺 positions。"
                    "預設全部警告；decisions staging_gate=strict（或 --strict）時 D06–D08 擋。")
    ap.add_argument("--root", type=Path, default=Path("."), help="專案根目錄（讀 decisions.json、adapt/bible.json、"
                                                                "assets/character-packs.json、video-bindings.json）")
    ap.add_argument("--segments", type=Path, nargs="*", default=None, help="分段 JSON 檔或目錄（預設：根目錄下 segments*.json）")
    ap.add_argument("--backend", choices=list(VIDEO_BACKENDS), default=None, help="覆蓋 backend 判定")
    ap.add_argument("--strict", action="store_true", help="本次把 D06–D08 當錯誤（不寫定案；長期要擋請 h3d decide staging_gate strict）")
    ap.add_argument("--json", action="store_true", help="以 JSON 輸出")
    args = ap.parse_args(argv)
    root = args.root.resolve()
    files = refcheck._expand(args.segments, root) if args.segments else sorted(root.glob("segments*.json"))
    if not files:
        print(f"❌ 找不到分段檔（--segments 或 {root}/segments*.json）", file=sys.stderr)
        return 2
    plan = refcheck.load_pack_plan(root)
    lexicon = refcheck.load_lexicon(root, plan)
    anchors = refcheck._anchors(root)
    strict = args.strict or project_strict(root)
    bindings = refcheck._bindings_by_id(root)
    segments = []
    for path in files:
        for seg in refcheck._load_segments(path):
            segments.append(refcheck._merge_binding(seg, bindings.get(str(seg.get("segment_id")))))
    rows = lint_segments(segments, lambda s: refcheck._resolve_backend(s, root, args.backend), lexicon, strict, anchors)
    bad = [r for r in rows if not r["ok"]]
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        for r in rows:
            print(f"{'OK  ' if r['ok'] else 'FAIL'} {r['segment_id']}（{r['backend']}）")
            for f in r["findings"]:
                print(f"  {'❌' if f['level'] == 'error' else '⚠️'} {f['message']}")
        n_warn = sum(1 for r in rows for f in r["findings"] if f["level"] != "error")
        print(f"STAGING：{len(rows) - len(bad)}/{len(rows)} 段通過（警告 {n_warn}；"
              f"{'strict：D06–D08 為錯誤' if strict else '預設：全部只警告'}）")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
