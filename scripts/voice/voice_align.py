#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""`h3d voice align`：階段 7 固定流程——ASR 對位、畫外句區間壓原聲、響度標準化。

從《我修的是遺忘課》voice/（asr_segs.py、place.py、make_check.py）通用化。
為什麼要有：H3 會把該由外部配音念的畫外句自己念成亂語（本案 115 段裡 12 段），
直接疊配音會「兩個聲音打架」。固定流程：

  1. asr       ：faster-whisper 轉寫每段原聲（字級時間），寫 voice/h3-asr.json（已有的段跳過）。
  2. place     ：把畫內台詞（timeline-plan-ep*.csv 的 subtitle）跟 ASR 對齊，找出每句畫外配音能放的窗口
                 ——接在前一句畫內台詞結束後 0.15 秒、下一句開始前收；放不下就加速（≤ 1.2 倍），
                 最後一句可溢入下一段開頭的靜默；ASR 認不出是哪句畫內台詞的聲音＝亂語，記成 mutes。
                 寫 voice/placement.json；人聽過後的修正寫在 voice/placement-overrides.json，重跑不會被蓋掉。
  3. duck      ：mutes 區間原聲壓低（預設 −22 dB），輸出 voice/muted/<段>.mp4（影像直接複製）。
  4. loudnorm  ：每句配音響度標準化（預設 −16 LUFS、TP −1.5），必要時套 tempo，輸出 voice/final/<key>.wav，
                 並把 final／final_dur 寫回 placement。

輸入：
  * voice/manifest.json：{key: {segment, speaker, line, file, dur}}（外部 TTS 產物，dur＝秒）
  * timeline-plan-ep*.csv：shot_id,start,end,...,subtitle（layer2_to_table 產生）
  * segments-ep*.json：決定段落順序（最後一句溢入下一段時要知道下一段是誰）
  * videos/<段>.mp4
"""
from __future__ import annotations

import argparse
import csv
import difflib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

ASR_JUNK = ("以下是繁體", "點贊", "訂閱", "小鈴鐺", "字幕", "打賞", "詞曲", "作詞", "作曲", "索兰娅", "索蘭婭", "請不吝", "感謝收看", "謝謝觀看")
DEFAULT_DUCK_DB = -22.0
DEFAULT_LUFS = -16.0
DEFAULT_GAP = 0.15
MAX_TEMPO = 1.2


def norm(text: str) -> str:
    """只留漢字（對齊用）。"""
    return re.sub(r"[^\u4e00-\u9fff]", "", str(text or ""))


def _load_pinyin():
    try:
        from pypinyin import lazy_pinyin  # type: ignore
        return lambda t: lazy_pinyin(t, errors="ignore")
    except Exception:  # 沒裝 pypinyin → 退回逐字
        return None


_PINYIN = _load_pinyin()


def tokens(text: str) -> List[str]:
    """對位用 token：有 pypinyin 時用無聲調拼音（「幹／干」「屁／匹」同音視為相同），否則逐字。"""
    chars = norm(text)
    if _PINYIN is None or not chars:
        return list(chars)
    try:
        out = _PINYIN(chars)
    except Exception:
        return list(chars)
    return out if len(out) == len(chars) else list(chars)


def overlap(a: str, b: str) -> float:
    ta, tb = tokens(a), set(tokens(b))
    return sum(1 for c in ta if c in tb) / max(1, len(ta))


# ------------------------------------------------------------------ 讀專案
def segment_order(root: Path) -> List[str]:
    ids: List[str] = []
    for path in sorted(Path(root).glob("segments-ep*.json")):
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
        items = raw if isinstance(raw, list) else raw.get("segments", [])
        ids.extend(str(s["segment_id"]) for s in items if isinstance(s, dict) and s.get("segment_id"))
    return ids


def timeline_lines(root: Path) -> Dict[str, List[Dict[str, Any]]]:
    """段 → 依時間排序的台詞（畫內＋畫外都在 subtitle 欄）。"""
    out: Dict[str, List[Dict[str, Any]]] = {}
    for path in sorted(Path(root).glob("timeline-plan-ep*.csv")):
        with path.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                text = (row.get("subtitle") or "").strip()
                shot = (row.get("shot_id") or "").strip()
                if not text or not shot:
                    continue
                seg = shot.rsplit("-SH", 1)[0]
                out.setdefault(seg, []).append({"text": text, "start": float(row.get("start") or 0),
                                                "end": float(row.get("end") or 0),
                                                "speaker": (row.get("speaker") or "").strip()})
    return out


def ffprobe_duration(path: Path) -> Optional[float]:
    if not shutil.which("ffprobe") or not Path(path).is_file():
        return None
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                              str(path)], capture_output=True, text=True, timeout=60).stdout.strip()
        return float(out)
    except (ValueError, subprocess.SubprocessError, OSError):
        return None


# ------------------------------------------------------------------ 1. ASR
ASR_SEG_TIMEOUT = 120.0


def _transcribe_guarded(model: Any, audio: Any, prompt: str, timeout: float) -> Tuple[List[Any], bool]:
    """逐段逾時：先用原設定（vad_filter=False），超時改 VAD＋不接前文重試（#165）。回傳 (片段, 是否重試過)。"""
    import threading

    def attempt(**kw: Any) -> Optional[List[Any]]:
        box: Dict[str, Any] = {}

        def work() -> None:
            try:
                res, _ = model.transcribe(audio, language="zh", word_timestamps=True, initial_prompt=prompt, **kw)
                box["r"] = list(res)
            except Exception as exc:  # noqa: BLE001
                box["e"] = exc
        t = threading.Thread(target=work, daemon=True)
        t.start()
        t.join(timeout)
        if t.is_alive():
            return None
        if "e" in box:
            raise box["e"]
        return box["r"]

    first = attempt(vad_filter=False)
    if first is not None:
        return first, False
    second = attempt(vad_filter=True, condition_on_previous_text=False)
    if second is None:
        raise RuntimeError(f"ASR 逾時（{timeout:.0f}s ×2，含 VAD 重試）；請檢查該段音訊或換較小模型")
    return second, True


def run_asr(root: Path, segments: Iterable[str], asr: Dict[str, Any], *, model_size: str = "small",
            device: str = "cpu", compute_type: str = "int8", out_path: Optional[Path] = None,
            prompt: str = "以下是繁體中文的古風對白。") -> Dict[str, Any]:
    """faster-whisper 轉寫；已有的段跳過。沒裝 faster-whisper 丟 RuntimeError。"""
    todo = [s for s in segments if s not in asr]
    if not todo:
        return asr
    try:
        from faster_whisper import WhisperModel  # type: ignore
        import numpy as np  # type: ignore
    except ImportError as exc:
        raise RuntimeError("需要 faster-whisper（pip install faster-whisper）才能做 ASR；"
                           "或先提供 voice/h3-asr.json 再用 --steps place,duck,loudnorm") from exc
    model = WhisperModel(model_size, device=device, compute_type=compute_type)
    for seg in todo:
        video = Path(root) / "videos" / f"{seg}.mp4"
        pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-f", "s16le", "-ac", "1", "-ar", "16000", "-"],
                             capture_output=True, check=True).stdout
        audio = np.frombuffer(pcm, np.int16).astype(np.float32) / 32768
        result, retried = _transcribe_guarded(model, audio, prompt, ASR_SEG_TIMEOUT)
        if retried:
            print(f"[voice align] {seg}：ASR 逾時，已改 VAD 重試", file=sys.stderr)
        asr[seg] = [{"start": round(x.start, 2), "end": round(x.end, 2), "text": x.text,
                     "words": [[round(w.start, 2), round(w.end, 2), w.word] for w in (x.words or [])]}
                    for x in result]
        if out_path:
            out_path.write_text(json.dumps(asr, ensure_ascii=False, indent=1), encoding="utf-8")
    return asr


# ------------------------------------------------------------------ 2. 放置
def _clean_chunks(chunks: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [c for c in chunks or [] if not any(j in str(c.get("text", "")) for j in ASR_JUNK)]


def place(manifest: Dict[str, Dict[str, Any]], lines: Dict[str, List[Dict[str, Any]]],
          asr: Dict[str, List[Dict[str, Any]]], durations: Dict[str, float], order: List[str], *,
          gap: float = DEFAULT_GAP, max_tempo: float = MAX_TEMPO,
          force_rogue: Iterable[Tuple[str, str]] = ()) -> Tuple[Dict[str, Dict[str, Any]], List[str]]:
    """回傳 (placement, 需要先轉寫的下一段)。placement[key] = {segment,start,tempo,window,note,mutes}。

    force_rogue：[(段, 文字)]，人工指定「這段 ASR 的這幾個字是亂語」（ASR 偶爾把亂語聽成像台詞的字）。
    """
    force = [(s, norm(t)) for s, t in force_rogue]
    by_seg: Dict[str, List[str]] = {}
    for key, item in manifest.items():
        by_seg.setdefault(item["segment"], []).append(key)
    result: Dict[str, Dict[str, Any]] = {}
    need_next: List[str] = []
    for seg, keys in by_seg.items():
        dur = float(durations.get(seg) or 0.0)
        seg_lines = [l["text"] for l in lines.get(seg, [])]
        vo_lines = {manifest[k]["line"] for k in keys}
        for k in keys:  # 配音句不在時間表裡（少見）→ 附在最後
            if manifest[k]["line"] not in seg_lines:
                seg_lines.append(manifest[k]["line"])
        on = [(i, l) for i, l in enumerate(seg_lines) if l not in vo_lines]
        ref, ref_idx = [], []
        for i, l in on:
            for c in tokens(l):
                ref.append(c)
                ref_idx.append(i)
        words: List[List[Any]] = []
        rogue: List[Tuple[float, float, str]] = []
        for chunk in _clean_chunks(asr.get(seg, [])):
            keep = []
            for w in chunk.get("words") or []:
                if any(fs == seg and norm(w[2]) and norm(w[2]) in ft for fs, ft in force):
                    rogue.append((w[0], w[1], w[2]))
                else:
                    keep.append(w)
            if not keep:
                continue
            text = "".join(w[2] for w in keep)
            if not on or max(overlap(text, l) for _, l in on) < 0.4:
                rogue.append((keep[0][0], keep[-1][1], text))  # 聽不出是哪句畫內台詞＝亂語
            else:
                words.extend(keep)
        hyp, hyp_idx = [], []
        for wi, w in enumerate(words):
            for c in tokens(w[2]):
                hyp.append(c)
                hyp_idx.append(wi)
        wline: List[Optional[int]] = [None] * len(words)
        for block in difflib.SequenceMatcher(None, hyp, ref, autojunk=False).get_matching_blocks():
            for j in range(block.size):
                wline[hyp_idx[block.a + j]] = ref_idx[block.b + j]
        for i in range(len(wline)):
            if wline[i] is None:
                prev = next((wline[j] for j in range(i - 1, -1, -1) if wline[j] is not None), None)
                wline[i] = prev if prev is not None else next((x for x in wline if x is not None), 0)
        mutes: List[Tuple[float, float]] = []
        for k in sorted(keys, key=lambda k: seg_lines.index(manifest[k]["line"])):
            m = manifest[k]
            length = float(m.get("dur") or 0.0)
            pos = seg_lines.index(m["line"])
            lo = max([words[i][1] for i in range(len(words)) if (wline[i] or 0) < pos] + [0.0]) + gap
            nexts = [words[i][0] for i in range(len(words)) if (wline[i] or 0) > pos]
            for k2, r2 in result.items():
                if r2["segment"] == seg:
                    lo = max(lo, r2["start"] + float(manifest[k2].get("dur") or 0) / r2["tempo"] + 0.2)
            hi = (min(nexts) - 0.1) if nexts else dur
            hits = [r for r in rogue if r[1] > lo - 0.2 and r[0] < hi]
            note = ""
            if hits:
                mutes += [(round(max(0.0, r[0] - 0.1), 2), round(min(dur, r[1] + 0.15) if dur else r[1] + 0.15, 2))
                          for r in hits]
                note = "原聲亂語壓低：" + "／".join(r[2] for r in hits)
                first = min(r[0] for r in hits)
                if first > lo:
                    lo = max(lo, first - 0.05)
            if not nexts and hi - lo < length and seg in order:
                nxt = order[order.index(seg) + 1] if order.index(seg) + 1 < len(order) else None
                if nxt:
                    if nxt not in asr:
                        need_next.append(nxt)
                    else:
                        chunks = _clean_chunks(asr[nxt])
                        lead = chunks[0]["start"] if chunks else float(durations.get(nxt) or 0)
                        spill = max(0.0, lead - 0.2)
                        hi = dur + spill
                        note += f"；可溢入下一段 {spill:.2f}s"
            room = hi - lo
            tempo = 1.0
            if length > room:
                tempo = round(min(max_tempo, length / max(room, 0.01)), 3)
            if length / tempo > room + 0.05:
                note += f"；⚠ 空間 {room:.2f}s < {length / tempo:.2f}s"
            result[k] = {"segment": seg, "start": round(lo, 2), "tempo": tempo,
                         "window": [round(lo, 2), round(hi, 2)], "note": note.lstrip("；")}
        merged = merge_intervals(mutes)
        for k in keys:
            result[k]["mutes"] = merged
    return result, sorted(set(need_next))


def merge_intervals(items: Iterable[Sequence[float]], join_gap: float = 0.05) -> List[List[float]]:
    """重疊或相距 ≤ join_gap 秒的壓低區間合併成一段（避免音量忽上忽下）。"""
    out: List[List[float]] = []
    for a, b in sorted((float(x[0]), float(x[1])) for x in items):
        if out and a <= out[-1][1] + join_gap:
            out[-1][1] = round(max(out[-1][1], b), 2)
        else:
            out.append([round(a, 2), round(b, 2)])
    return out


def apply_overrides(placement: Dict[str, Dict[str, Any]], overrides: Dict[str, Dict[str, Any]]) -> List[str]:
    """voice/placement-overrides.json：人工微調（start／tempo／mutes／note）。

    自動放置是第一版；人聽過後的修正寫在這個檔，重跑 align 不會被蓋掉。
    """
    applied = []
    for key, patch in (overrides or {}).items():
        if key not in placement or not isinstance(patch, dict):
            continue
        for field in ("start", "tempo", "mutes", "note", "window"):
            if field in patch:
                placement[key][field] = patch[field]
        if "mutes" in patch:  # 同段其他句共用同一組壓低區間
            seg = placement[key]["segment"]
            for other in placement.values():
                if other["segment"] == seg:
                    other["mutes"] = patch["mutes"]
        placement[key]["overridden"] = True
        applied.append(key)
    return applied


# ------------------------------------------------------------------ 3. 壓原聲／4. 響度
def duck_filter(mutes: Sequence[Sequence[float]], db: float = DEFAULT_DUCK_DB) -> str:
    """mutes 區間把原聲降 db 分貝的 ffmpeg -af 字串。"""
    parts = [f"volume=enable='between(t,{float(a):.2f},{float(b):.2f})':volume={db:g}dB" for a, b in mutes]
    return ",".join(parts) or "anull"


def duck_video(src: Path, dst: Path, mutes: Sequence[Sequence[float]], db: float = DEFAULT_DUCK_DB) -> List[str]:
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(src), "-c:v", "copy", "-af", duck_filter(mutes, db),
           "-c:a", "aac", "-b:a", "192k", str(dst)]
    dst.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(cmd, check=True)
    return cmd


def tempo_filter(tempo: float) -> str:
    return f"atempo={tempo:.3f}" if abs(tempo - 1.0) > 1e-3 else ""


def loudnorm_filter(lufs: float = DEFAULT_LUFS, tempo: float = 1.0) -> str:
    parts = [p for p in (tempo_filter(tempo), f"loudnorm=I={lufs:g}:TP=-1.5:LRA=11") if p]
    return ",".join(parts)


def loudnorm_audio(src: Path, dst: Path, lufs: float = DEFAULT_LUFS, tempo: float = 1.0) -> List[str]:
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(src), "-af", loudnorm_filter(lufs, tempo), "-ar", "48000",
           "-ac", "1", str(dst)]
    dst.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(cmd, check=True)
    return cmd


# ------------------------------------------------------------------ 主流程
def align(root: Path, *, steps: Sequence[str] = ("asr", "place", "duck", "loudnorm"),
          manifest_path: Optional[Path] = None, duck_db: float = DEFAULT_DUCK_DB, lufs: float = DEFAULT_LUFS,
          model_size: str = "small", force_rogue_path: Optional[Path] = None, dry_run: bool = False,
          log=print) -> Dict[str, Any]:
    root = Path(root).resolve()
    voice = root / "voice"
    manifest_path = manifest_path or voice / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    asr_path = voice / "h3-asr.json"
    asr = json.loads(asr_path.read_text(encoding="utf-8")) if asr_path.is_file() else {}
    order = segment_order(root)
    segs = sorted({m["segment"] for m in manifest.values()}, key=lambda s: order.index(s) if s in order else 1e9)
    report: Dict[str, Any] = {"segments": segs, "steps": list(steps)}
    if "asr" in steps and not dry_run:
        asr = run_asr(root, segs, asr, model_size=model_size, out_path=asr_path)
    placement_path = voice / "placement.json"
    placement = json.loads(placement_path.read_text(encoding="utf-8")) if placement_path.is_file() else {}
    if "place" in steps:
        durations = {s: ffprobe_duration(root / "videos" / f"{s}.mp4") or 0.0 for s in set(segs) | set(order)}
        force = []
        if force_rogue_path and force_rogue_path.is_file():
            force = [tuple(x) for x in json.loads(force_rogue_path.read_text(encoding="utf-8"))]
        placement, need_next = place(manifest, timeline_lines(root), asr, durations, order, force_rogue=force)
        if need_next and "asr" in steps and not dry_run:
            asr = run_asr(root, need_next, asr, model_size=model_size, out_path=asr_path)
            placement, need_next = place(manifest, timeline_lines(root), asr, durations, order, force_rogue=force)
        report["need_next_asr"] = need_next
        overrides_path = voice / "placement-overrides.json"
        if overrides_path.is_file():
            report["overridden"] = apply_overrides(placement, json.loads(overrides_path.read_text(encoding="utf-8")))
        if not dry_run:
            placement_path.write_text(json.dumps(placement, ensure_ascii=False, indent=1), encoding="utf-8")
    muted = sorted({p["segment"] for p in placement.values() if p.get("mutes")})
    report["muted_segments"] = muted
    if "duck" in steps and not dry_run:
        for seg in muted:
            mutes = next(p["mutes"] for p in placement.values() if p["segment"] == seg and p.get("mutes"))
            duck_video(root / "videos" / f"{seg}.mp4", voice / "muted" / f"{seg}.mp4", mutes, duck_db)
            log(f"壓原聲 {seg}：{len(mutes)} 段 {duck_db:g} dB")
    if "loudnorm" in steps and not dry_run:
        for key, item in placement.items():
            src = Path(manifest[key]["file"])
            src = src if src.is_absolute() else root / src
            dst = voice / "final" / f"{key}.wav"
            loudnorm_audio(src, dst, lufs, float(item.get("tempo") or 1.0))
            item["final"] = dst.relative_to(root).as_posix()
            item["final_dur"] = round(ffprobe_duration(dst) or float(manifest[key].get("dur") or 0) / float(item.get("tempo") or 1), 2)
        placement_path.write_text(json.dumps(placement, ensure_ascii=False, indent=1), encoding="utf-8")
    report["placed"] = len(placement)
    report["warnings"] = [f"{k}：{v['note']}" for k, v in placement.items() if "⚠" in str(v.get("note"))]
    return report


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="h3d voice align",
                                     description="階段 7 固定流程：ASR 對位 → 放置 → 畫外句區間壓原聲 → 響度標準化")
    parser.add_argument("action", nargs="?", default="align", choices=["align"])
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--manifest", type=Path, default=None, help="預設 voice/manifest.json")
    parser.add_argument("--steps", default="asr,place,duck,loudnorm", help="逗號分隔：asr,place,duck,loudnorm")
    parser.add_argument("--duck-db", type=float, default=DEFAULT_DUCK_DB, help="畫外句區間原聲降幾 dB（預設 -22）")
    parser.add_argument("--lufs", type=float, default=DEFAULT_LUFS, help="配音響度目標（預設 -16 LUFS）")
    parser.add_argument("--model", default="small", help="faster-whisper 模型大小")
    parser.add_argument("--force-rogue", type=Path, default=None, help="JSON [[段, 文字], ...]：人工指定的亂語")
    parser.add_argument("--dry-run", action="store_true", help="只算放置，不寫檔、不跑 ffmpeg／ASR")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    steps = [s.strip() for s in args.steps.split(",") if s.strip()]
    unknown = set(steps) - {"asr", "place", "duck", "loudnorm"}
    if unknown:
        parser.error(f"未知步驟：{', '.join(sorted(unknown))}")
    try:
        report = align(args.root, steps=steps, manifest_path=args.manifest, duck_db=args.duck_db, lufs=args.lufs,
                       model_size=args.model, force_rogue_path=args.force_rogue, dry_run=args.dry_run)
    except (OSError, RuntimeError, json.JSONDecodeError, subprocess.CalledProcessError) as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"✅ 放置 {report['placed']} 句；壓原聲 {len(report['muted_segments'])} 段"
              f"（{', '.join(report['muted_segments'][:8])}）")
        for w in report["warnings"]:
            print(f"⚠️ {w}")
        if report.get("need_next_asr"):
            print(f"⚠️ 最後一句要溢入下一段，但這些段沒有 ASR：{', '.join(report['need_next_asr'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
