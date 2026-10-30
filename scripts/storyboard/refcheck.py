#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""h3d refcheck（PR-R4）：參考包涵蓋檢查——提示詞寫到的具名資產，是不是都有綁包。

來源：《噩盡島》ch02 `refcheck.py`（老大 2026-10-27 00:18「要確實檢查資產圖是否都有參照喔，我抓到一個，
蛇沒有給參考圖」）。ch02 EP04 measured：S01-a／c／d 寫了巨蟒、銀槍卻沒有包，沒綁時槍沒有斷成三節棍、
蛇骸像焦黑盤管；補包＋refcheck 後才擋得住。這裡只抽規則，專案特定名單不寫死：

  詞表（lexicon）從專案資料自動產生，不寫死：
    - adapt/bible.json 的 characters／locations／props（及 creatures／extras）每項的
      `name_en`、`aliases_en`（字面詞，大小寫不分、整字比對、容許複數 s／es）、`alias_patterns_en`（正則）；
    - assets/character-packs.json 的 packs.<id> 也可寫 `name_en`／`aliases_en`／`alias_patterns_en`，
      另有頂層 `refcheck: {"strip_patterns": [...], "generic_en": [...]}`（固定句剝除、普通物件清單）。
    - 中文 name 不參與比對（提示詞是英文）；只有 ASCII 的 name 會當字面詞。
  規則：
    E50 具名資產沒有包：提示詞命中某資產的詞、或段落在場名單（visual_subject_ids…）有它，
        refmods 卻沒有它的包（看 id，或計畫表登記的包名／服裝變體包名）。
    E50 豁免缺原話：pack_waivers 沒有 quote（使用者原話）不算豁免。
    bible／計畫表標 `voice_only` 或 `no_visual_reference` 的角色只聞其聲、不需要包：提示詞寫到名字或在場名單有他都不報 E50。
    E51 未綁包的人群字眼：students／crowd／people／classmates／others／bystanders 等，
        段落沒有 kind=extras 的包、句中也沒有不可辨識寫法（失焦／剪影）→ REMIX 會長出沒綁包的陌生人。
        「as tall as the others」這類比例錨、「no other people／without other people」否定句不算（肯定句 other people 照報）。
    普通物件（generic_en）只列出給人看，不擋。
  backend：remix＝錯誤（exit 1）；ref2va＝同樣的碼但只提示（列在 warnings，exit 0），不改 ref2va 既有門禁。
  豁免：段落 `pack_waivers`（bindings 產生）或計畫表 `waivers.<段>`，每項 {id 或 pack, reason, quote}；
        E51 可用 {"id": "E51", "quote": …} 豁免。

用法：
  python scripts/h3d.py refcheck --root .                         # 專案根目錄下 segments*.json
  python scripts/h3d.py refcheck --root . --segments segments-ep04.json
  python scripts/h3d.py refcheck --root . --takes videos/remix-queue.jsonl   # 已送出抽次的提示詞快照
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

VIDEO_BACKENDS = ("ref2va", "remix")
DETAIL_SECTIONS = ("integrated_multimodal_description", "detailed_description")
TAIL_SECTIONS = ("overall_soundscape", "non_diegetic_music", "subject_definitions", "retention_analysis")

# 人群字眼（照 ch02 refcheck UNBOUND）。後看斷言排除比例錨與否定句。
UNBOUND_PEOPLE = re.compile(
    r"\bstudents\b|\bcrowds?\b|(?<!these two )(?<!these three )(?<!these four )\bpeople\b"
    r"|\bclassmates\b|(?<!as the )(?<!than the )\bothers\b(?!')|\bbystanders\b|\bonlookers\b|\bpassers-?by\b",
    re.I)
# 「as tall as the others」比例錨、「Only these … people」宣告句不算人群
# 「other people」只有在否定句（no other／without other／nobody else）才不算；肯定句「other people browse behind」
# 會長出陌生人，所以不再用後看斷言整個排除（那會把肯定句也放掉）。
_UNBOUND_EXEMPT_CONTEXT = re.compile(r"\bas\s+\w+\s+as\s+the\s+others\b|\bonly these\b|\bno other\b|\bwithout (?:any )?other\b"
                                     r"|\bnever any other\b|\bempty of\b", re.I)
_NON_IDENTIFIABLE = re.compile(
    r"out of focus|blurred|indistinct|no facial detail|without facial detail|unrecogni[sz]able|silhouett", re.I)

_KIND_BY_PREFIX = (("CREATURE", "creature"), ("EXTRAS", "extras"), ("SCENE", "scene"), ("S-", "scene"),
                   ("P-", "prop"), ("PROP", "prop"), ("C-", "actor"))


# ---------------------------------------------------------------------------
# 詞表
# ---------------------------------------------------------------------------
def _literal_regex(term: str) -> Optional[re.Pattern]:
    term = str(term or "").strip()
    if not term or re.search(r"[^\x00-\x7f]", term):
        return None
    body = re.escape(term).replace(r"\ ", r"\s+")
    return re.compile(rf"(?<![A-Za-z]){body}(?:s|es)?(?![A-Za-z])", re.I)


def _kind_of(asset_id: str, record: Dict[str, Any], default: str = "actor") -> str:
    if record.get("kind"):
        return str(record["kind"])
    if record.get("is_group"):
        return "extras"
    if record.get("is_creature"):
        return "creature"
    upper = asset_id.upper()
    for prefix, kind in _KIND_BY_PREFIX:
        if upper.startswith(prefix):
            return kind
    return default


def _iter_records(value: Any) -> Iterable[Tuple[str, Dict[str, Any]]]:
    if isinstance(value, dict):
        for key, rec in value.items():
            if isinstance(rec, dict):
                yield str(rec.get("id") or key), rec
    elif isinstance(value, list):
        for rec in value:
            if isinstance(rec, dict):
                rid = rec.get("id") or rec.get("character_id") or rec.get("location_id") or rec.get("prop_id")
                if rid:
                    yield str(rid), rec


def _pack_names(raw: Any) -> List[str]:
    """計畫表一項的所有包名（預設＋服裝變體）。"""
    if isinstance(raw, str):
        return [raw]
    if not isinstance(raw, dict):
        return []
    names = [raw.get("pack"), raw.get("default")]
    for variant in (raw.get("costumes") or {}).values():
        names.append(variant if isinstance(variant, str) else (variant or {}).get("pack"))
    return [str(n) for n in names if isinstance(n, str) and n.strip()]


def load_pack_plan(root: Optional[Path]) -> Dict[str, Any]:
    if root is None:
        return {}
    path = Path(root) / "assets" / "character-packs.json"
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}


def load_lexicon(root: Optional[Path], pack_plan: Optional[Dict[str, Any]] = None) -> Dict[str, Dict[str, Any]]:
    """{asset_id: {"kind", "terms": [str], "regexes": [Pattern], "packs": set, "label"}}。"""
    lex: Dict[str, Dict[str, Any]] = {}
    plan = pack_plan if pack_plan is not None else load_pack_plan(root)

    def entry(asset_id: str, rec: Dict[str, Any], default_kind: str) -> Dict[str, Any]:
        item = lex.setdefault(asset_id, {"kind": _kind_of(asset_id, rec, default_kind), "terms": [],
                                         "regexes": [], "packs": set(), "label": asset_id})
        if rec.get("voice_only") or rec.get("no_visual_reference"):
            # EP01 findings #5：只聞其聲的角色不需要參考包（畫面上沒有他），不報 E50
            item["voice_only"] = True
        name = rec.get("name") or rec.get("canonical_name")
        if name and item["label"] == asset_id:
            item["label"] = str(name)
        candidates = [rec.get("name_en")] + list(rec.get("aliases_en") or [])
        if isinstance(name, str) and not re.search(r"[^\x00-\x7f]", name) and name != asset_id:
            candidates.append(name)
        for term in candidates:
            rx = _literal_regex(term)
            if rx is not None and term not in item["terms"]:
                item["terms"].append(str(term))
                item["regexes"].append(rx)
        for pattern in rec.get("alias_patterns_en") or []:
            try:
                item["regexes"].append(re.compile(str(pattern), re.I))
                item["terms"].append(f"re:{pattern}")
            except re.error:
                item.setdefault("bad_patterns", []).append(str(pattern))
        return item

    if root is not None:
        bible_path = Path(root) / "adapt" / "bible.json"
        if bible_path.is_file():
            try:
                bible = json.loads(bible_path.read_text(encoding="utf-8-sig"))
            except (OSError, json.JSONDecodeError):
                bible = {}
            for section, default_kind in (("characters", "actor"), ("creatures", "creature"), ("extras", "extras"),
                                          ("locations", "scene"), ("scenes", "scene"), ("props", "prop")):
                for asset_id, rec in _iter_records(bible.get(section)):
                    entry(asset_id, rec, default_kind)
    for asset_id, raw in (plan.get("packs") or {}).items():
        rec = raw if isinstance(raw, dict) else {}
        item = entry(str(asset_id), rec, "actor")
        item["packs"].update(_pack_names(raw))
    return lex


# ---------------------------------------------------------------------------
# 提示詞本體
# ---------------------------------------------------------------------------
def detail_body(prompt: str) -> str:
    """只看畫面描述欄（integrated_multimodal_description／detailed_description）；沒有欄位標籤就看整段去尾欄。"""
    text = str(prompt or "")
    for section in DETAIL_SECTIONS:
        m = re.search(rf"{section}:(.*?)(?:\n\s*\n[a-z_]+:|\Z)", text, re.S)
        if m:
            return m.group(1)
    for section in TAIL_SECTIONS:
        text = re.split(rf"\n\s*{section}:", text)[0]
    return text


def strip_fixed(body: str, strip_patterns: Iterable[str] = (), anchors: Iterable[str] = ()) -> str:
    for anchor in anchors:
        if anchor:
            body = body.replace(anchor, " ")
    for pattern in strip_patterns:
        try:
            body = re.sub(pattern, " ", body, flags=re.S | re.I)
        except re.error:
            continue
    return body


def _prompt_of(seg: Dict[str, Any]) -> str:
    for key in ("h3_prompt", "prompt"):
        if isinstance(seg.get(key), str):
            return seg[key]
    for key in ("compiled_prompts", "outputs"):
        if isinstance(seg.get(key), dict) and isinstance(seg[key].get("minimax-h3"), str):
            return seg[key]["minimax-h3"]
    return ""


def _named_ids(seg: Dict[str, Any]) -> List[str]:
    try:
        from audit_refs_and_segments import _segment_named_ids
    except ImportError:  # pragma: no cover
        return []
    return _segment_named_ids(seg)


# ---------------------------------------------------------------------------
# 單段檢查
# ---------------------------------------------------------------------------
def _coverage(seg: Dict[str, Any], backend: str, packs_override: Optional[List[str]] = None) -> Tuple[set, set, bool]:
    ids, packs = set(), set(packs_override or [])
    has_extras = False
    for ref in seg.get("refmods") or []:
        if isinstance(ref, dict):
            if ref.get("id"):
                ids.add(str(ref["id"]))
            if ref.get("pack"):
                packs.add(str(ref["pack"]))
            has_extras = has_extras or ref.get("kind") == "extras"
        elif isinstance(ref, str):
            packs.add(ref)
    for value in seg.get("packs") or []:
        if isinstance(value, str):
            packs.add(value)
    if backend == "ref2va":
        for ref in seg.get("reference_images") or []:
            if isinstance(ref, dict) and ref.get("id"):
                ids.add(str(ref["id"]))
                has_extras = has_extras or str(ref.get("type") or "") in ("extras", "group")
        for key in ("identity_anchor_ids", "face_subject_ids"):
            ids.update(str(x) for x in seg.get(key) or [])
    return ids, packs, has_extras


def _waivers(seg: Dict[str, Any], plan: Dict[str, Any], seg_id: str) -> Tuple[set, set, List[str]]:
    raw = list(seg.get("pack_waivers") or []) + list(((plan.get("waivers") or {}).get(seg_id)) or [])
    ok_ids, ok_packs, bad = set(), set(), []
    for item in raw:
        if not isinstance(item, dict):
            continue
        key = item.get("id") or item.get("pack")
        if not str(item.get("quote") or "").strip():
            bad.append(str(key))
            continue
        if item.get("id"):
            ok_ids.add(str(item["id"]))
        if item.get("pack"):
            ok_packs.add(str(item["pack"]))
    return ok_ids, ok_packs, bad


def check_segment(seg: Dict[str, Any], lexicon: Dict[str, Dict[str, Any]], backend: str = "remix",
                  pack_plan: Optional[Dict[str, Any]] = None, anchors: Iterable[str] = (),
                  packs_override: Optional[List[str]] = None, key: Optional[str] = None,
                  include_presence: bool = True) -> Dict[str, Any]:
    """回傳 {key, backend, hits, missing, waived, unbound_people, generic, errors, warnings, ok}。

    remix：E50／E51 進 errors；ref2va：同樣訊息進 warnings（只提示）。
    """
    plan = pack_plan or {}
    seg_id = str(seg.get("segment_id") or seg.get("id") or key or "segment")
    key = key or seg_id
    rc_cfg = plan.get("refcheck") or {}
    meta_anchor = (seg.get("metadata") or {}).get("style_anchor_en")
    body = strip_fixed(detail_body(_prompt_of(seg)), rc_cfg.get("strip_patterns") or [],
                       [a for a in list(anchors) + [meta_anchor] if a])
    ids, packs, has_extras = _coverage(seg, backend, packs_override)
    ok_ids, ok_packs, bad_waivers = _waivers(seg, plan, seg_id)

    hits: List[Dict[str, str]] = []
    missing: List[str] = []
    waived: List[str] = []
    no_terms: List[str] = []
    seen = set()

    def judge(asset_id: str, why: str) -> None:
        if asset_id in seen:
            return
        seen.add(asset_id)
        item = lexicon.get(asset_id) or {"packs": set(), "kind": _kind_of(asset_id, {}), "label": asset_id}
        if item.get("kind") == "extras":
            covered = asset_id in ids or bool(item["packs"] & packs) or has_extras
        else:
            covered = asset_id in ids or bool(item["packs"] & packs)
        if covered:
            return
        if asset_id in ok_ids or (item["packs"] and item["packs"] <= ok_packs) or (item["packs"] & ok_packs):
            waived.append(asset_id)
            return
        want = "/".join(sorted(item["packs"])) or f"計畫表 packs.{asset_id}"
        missing.append(f"{asset_id}（{item.get('label', asset_id)}，{why}；要 {want}）")

    for asset_id, item in lexicon.items():
        if item.get("voice_only"):
            continue  # 只聞其聲：提示詞寫到名字（畫外音說話人）也不需要包
        for rx in item["regexes"]:
            m = rx.search(body)
            if m:
                hits.append({"id": asset_id, "term": m.group(0)})
                judge(asset_id, f"提示詞寫到「{m.group(0)}」")
                break
    if include_presence:
        for asset_id in _named_ids(seg):
            if (lexicon.get(asset_id) or {}).get("voice_only"):
                continue
            if asset_id in lexicon and not lexicon[asset_id]["regexes"]:
                no_terms.append(asset_id)
            elif asset_id not in lexicon:
                no_terms.append(asset_id)
            judge(asset_id, "在場名單有他")

    unbound: List[str] = []
    if not has_extras and "E51" not in ok_ids:
        for m in UNBOUND_PEOPLE.finditer(body):
            sent_start = max(body.rfind(".", 0, m.start()), body.rfind(";", 0, m.start())) + 1
            sent_end_candidates = [i for i in (body.find(".", m.end()), body.find(";", m.end())) if i != -1]
            sentence = body[sent_start:min(sent_end_candidates) if sent_end_candidates else len(body)]
            if _UNBOUND_EXEMPT_CONTEXT.search(sentence) or _NON_IDENTIFIABLE.search(sentence):
                continue
            word = m.group(0).lower()
            if word not in unbound:
                unbound.append(word)

    generic = sorted({m.group(0).lower() for word in rc_cfg.get("generic_en") or []
                      for m in [re.search(rf"\b{re.escape(str(word))}\b", body, re.I)] if m})

    messages: List[str] = []
    for asset in bad_waivers:
        messages.append(f"[E50: 豁免缺原話] {seg_id} pack_waivers 的 {asset} 沒有使用者原話 quote；沒有原話不能豁免")
    if missing:
        messages.append(f"[E50: 具名資產沒有包] {seg_id}：{'；'.join(missing)}。REMIX 會照文字自由發揮"
                        f"（ch02 EP04 measured：沒綁包的巨蟒、銀槍都漂了）；建包加進 refmods，或從提示詞拿掉，"
                        f"或寫 pack_waivers 並附使用者原話")
    if unbound:
        messages.append(f"[E51: 未綁包的人群字眼] {seg_id}：{', '.join(unbound)}。沒有 kind=extras 的包，"
                        f"模型會長出沒綁包的陌生人；改成具名角色、加群眾包、寫成失焦剪影，或豁免（id: E51＋原話）")
    notes: List[str] = []
    if no_terms:
        notes.append(f"[W: refcheck 詞表] {seg_id}：{', '.join(sorted(set(no_terms)))} 沒有 name_en／aliases_en，"
                     f"只能靠在場名單比對；請在 bible.json 或 character-packs.json 補英文名與別名")
    if backend == "remix":
        errors, warnings = messages, notes
    else:
        errors, warnings = [], [m.replace("] ", "（ref2va 只提示）] ", 1) for m in messages] + notes
    return {"key": key, "segment_id": seg_id, "backend": backend, "hits": hits, "missing": missing,
            "waived": waived, "unbound_people": unbound, "generic": generic,
            "errors": errors, "warnings": warnings, "ok": not errors}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _load_segments(path: Path) -> List[Dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if isinstance(data, list):
        return [s for s in data if isinstance(s, dict)]
    if isinstance(data, dict) and isinstance(data.get("segments"), list):
        return [s for s in data["segments"] if isinstance(s, dict)]
    return [data] if isinstance(data, dict) else []


def _bindings_by_id(root: Path) -> Dict[str, Dict[str, Any]]:
    path = root / "video-bindings.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {str(s.get("segment_id")): s for s in data.get("segments") or [] if isinstance(s, dict)}


def _merge_binding(seg: Dict[str, Any], binding: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not binding:
        return seg
    merged = dict(seg)
    for key in ("refmods", "pack_waivers", "positions", "video_backend"):
        if key not in merged and key in binding:
            merged[key] = binding[key]
    if "shots" not in merged and binding.get("shots"):
        merged["shots"] = binding["shots"]
    return merged


def _resolve_backend(seg: Dict[str, Any], root: Path, forced: Optional[str]) -> str:
    try:
        from audit_refs_and_segments import resolve_backend
    except ImportError:  # pragma: no cover
        return forced or "ref2va"
    return resolve_backend(seg, root, forced)


def _anchors(root: Path) -> List[str]:
    try:
        import decisions as decisions_mod
        anchor = decisions_mod.style_anchor(root)
    except Exception:  # pragma: no cover
        anchor = None
    return [anchor] if anchor else []


def run(root: Path, segment_files: List[Path], backend: Optional[str] = None,
        takes: Optional[Path] = None) -> List[Dict[str, Any]]:
    plan = load_pack_plan(root)
    lexicon = load_lexicon(root, plan)
    anchors = _anchors(root)
    rows: List[Dict[str, Any]] = []
    if takes is not None:
        for line in takes.read_text(encoding="utf-8-sig").splitlines():
            if not line.strip():
                continue
            entry = json.loads(line)
            prompt = entry.get("prompt")
            if prompt is None and entry.get("prompt_file"):
                pf = Path(entry["prompt_file"])
                pf = pf if pf.is_absolute() else root / pf
                prompt = pf.read_text(encoding="utf-8-sig") if pf.is_file() else ""
            seg = {"segment_id": entry.get("segment_id") or str(entry.get("key", "")).rsplit("_t", 1)[0],
                   "h3_prompt": prompt or "", "refmods": entry.get("refmods") or [],
                   "pack_waivers": entry.get("pack_waivers") or [], "metadata": {"video_backend": "remix"}}
            row = check_segment(seg, lexicon, backend or "remix", plan, anchors,
                                packs_override=[p for p in entry.get("packs") or [] if isinstance(p, str)],
                                key=str(entry.get("key") or seg["segment_id"]), include_presence=False)
            rows.append(row)
        return rows
    bindings = _bindings_by_id(root)
    for path in segment_files:
        for seg in _load_segments(path):
            seg = _merge_binding(seg, bindings.get(str(seg.get("segment_id"))))
            seg_backend = _resolve_backend(seg, root, backend)
            rows.append(check_segment(seg, lexicon, seg_backend, plan, anchors))
    return rows


def _expand(paths: List[Path], root: Path) -> List[Path]:
    out: List[Path] = []
    for p in paths:
        p = p if p.is_absolute() else root / p
        if p.is_dir():
            out.extend(sorted(p.glob("*.json")))
        elif p.is_file():
            out.append(p)
    return out


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="h3d refcheck",
        description="參考包涵蓋檢查（PR-R4）：提示詞寫到的具名角色／生物／道具／場景／群眾是否都有綁包。"
                    "remix 缺包＝E50、未綁人群＝E51（exit 1）；ref2va 同樣檢查但只提示（exit 0）。")
    ap.add_argument("--root", type=Path, default=Path("."), help="專案根目錄（讀 adapt/bible.json、assets/character-packs.json、"
                                                                "decisions.json、video-bindings.json）")
    ap.add_argument("--segments", type=Path, nargs="*", default=None,
                    help="分段 JSON 檔或目錄（預設：根目錄下 segments*.json）；缺 refmods 時以 video-bindings.json 同 ID 段補")
    ap.add_argument("--takes", type=Path, default=None,
                    help="已送出抽次的快照 JSONL（每行 key、prompt 或 prompt_file、packs 或 refmods），防 runner 送出舊提示詞")
    ap.add_argument("--backend", choices=list(VIDEO_BACKENDS), default=None,
                    help="覆蓋 backend 判定（預設：段落 metadata.video_backend／refmods → decisions → ref2va）")
    ap.add_argument("--json", action="store_true", help="以 JSON 輸出")
    ap.add_argument("--out", type=Path, default=None, help="另存 JSON 報告")
    args = ap.parse_args(argv)
    root = args.root.resolve()

    if args.takes is not None:
        takes = args.takes if args.takes.is_absolute() else root / args.takes
        if not takes.is_file():
            print(f"❌ 找不到 --takes 檔：{takes}", file=sys.stderr)
            return 2
        rows = run(root, [], args.backend, takes)
    else:
        files = _expand(args.segments, root) if args.segments else sorted(root.glob("segments*.json"))
        if not files:
            print(f"❌ 找不到分段檔（--segments 或 {root}/segments*.json）", file=sys.stderr)
            return 2
        rows = run(root, files, args.backend)

    bad = [r for r in rows if not r["ok"]]
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2, default=list))
    else:
        for r in rows:
            mark = "OK  " if r["ok"] else "FAIL"
            print(f"{mark} {r['key']}（{r['backend']}）命中：{', '.join(h['id'] for h in r['hits']) or '-'}"
                  f"｜豁免：{', '.join(r['waived']) or '-'}｜普通物件：{', '.join(r['generic']) or '-'}")
            for e in r["errors"]:
                print(f"  ❌ {e}")
            for w in r["warnings"]:
                print(f"  ⚠️ {w}")
        print(f"REFCHECK：{len(rows) - len(bad)}/{len(rows)} 段通過")
    if args.out is not None:
        out = args.out if args.out.is_absolute() else root / args.out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(rows, ensure_ascii=False, indent=1, default=list) + "\n", encoding="utf-8")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
