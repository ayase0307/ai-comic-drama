#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""extract_voice_master.py — 從已生成的影片抽出角色的音色母帶（V-<slug>）

用途
----
把某個角色**第一次出場**的那一句，從已生成的 H3 影片裡切出來，存成這個角色的
音色母帶（2–15 秒、單人、可讀），之後所有段落都把這條母帶當 `<Audio N>` 音色參考
掛上，達成「同一個角色跨段聽起來是同一把聲音」。

為什麼需要這個工具
------------------
H3 的音色參考是**重新合成**而不是音軌複製（官方 ref-en §4.1 標記 `reference`：
"the target speaker follows <Audio 1>'s voice timbre and measured delivery without
copying the original signal"）。所以要鎖定一個角色的聲音，需要一條**固定的母帶**。
母帶有兩個來源：
  1. 事前用 TTS 克隆引擎做一條（`--from-audio` 路徑）——最乾淨，無環境音。
  2. 事後從第一次出場的生成片抽出（`--segments` 路徑）——省事，但母帶會帶著該場景的
     環境音與其他聲音。FreeVideo 自己的 cast 卡片系統也是這樣做的
     （`cast._voice()`：從 media 切 2–15 秒存成 voice clip），所以是可接受的做法。

切點不是猜的
------------
切的時間窗直接取自 Layer 2 的 `dialogue_and_audio.speech_window`（段內秒），
那是編劇/分鏡階段就定下來的那一句的區間，不靠 ASR 反推、也不靠人工拖時間軸。

用法
----
# 1) 看有哪些角色、在哪些段落有可用於當母帶的「畫內有可見嘴」的台詞
python scripts/storyboard/extract_voice_master.py --segments segments-ep01.json --list

# 2) 從第一次出場的生成片抽出母帶
python scripts/storyboard/extract_voice_master.py \
  --segments segments-ep01.json \
  --segment-id EP01-S01-c \
  --character C-luonien \
  --videos-dir videos/ \
  --output assets/voices/V-luonien-master-v1.wav

# 3) 或用既有的音檔（TTS 克隆輸出）當母帶，只做正規化與裁切
python scripts/storyboard/extract_voice_master.py \
  --from-audio E:/somewhere/luonien-clone.wav \
  --character C-luonien \
  --output assets/voices/V-luonien-master-v1.wav

輸出
----
* <output>.wav          48 kHz / 單聲道 / 16-bit PCM
* <output>.provenance.json  來源檔 SHA256、切的時間窗、原句、輸出 SHA256（可稽核、可重跑）

程式本體零外部依賴（只用標準函式庫與 ffmpeg/ffprobe）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# 官方限制：參考音訊 2–15 秒（FreeVideo cast._voice() 的 VOICE_SECONDS 同值）
VOICE_MIN_SECONDS = 2.0
VOICE_MAX_SECONDS = 15.0
# 產出格式：48 kHz 單聲道 16-bit PCM WAV。H3 的音訊 VAE 內部會重採樣到 32 kHz，
# 但送進節點前先正規化可避免各家解碼器給出不同取樣率。
OUTPUT_SAMPLE_RATE = 48000
OUTPUT_CHANNELS = 1


# ==============================================================================
# 工具
# ==============================================================================

def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(cmd: List[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")


def require_tool(name: str) -> str:
    found = shutil.which(name)
    if not found:
        raise SystemExit(f"[錯誤] 找不到 {name}；請先安裝 ffmpeg（送件與組裝都需要它）。")
    return found


def probe_duration(path: Path) -> float:
    result = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                  "-of", "default=noprint_wrappers=1:nokey=1", str(path)])
    if result.returncode != 0:
        raise SystemExit(f"[錯誤] ffprobe 無法讀取 {path}: {result.stderr[:300]}")
    try:
        return float((result.stdout or "0").strip())
    except ValueError:
        raise SystemExit(f"[錯誤] ffprobe 回傳的時長無法解析: {result.stdout!r}")


# ==============================================================================
# 段落資料
# ==============================================================================

def load_segments(path: Path) -> List[Dict[str, Any]]:
    # utf-8-sig 兩種都吃：Windows 的編輯器／PowerShell 5.1 常在 JSON 開頭留 BOM。
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    segments = raw.get("segments") if isinstance(raw, dict) else None
    if not isinstance(segments, list):
        segments = raw if isinstance(raw, list) else [raw]
    return [s for s in segments if isinstance(s, dict)]


def _is_voiceover(shot: Dict[str, Any]) -> bool:
    dlg = shot.get("dialogue_and_audio", {}) or {}
    spec = " ".join(str(dlg.get(key) or "") for key in ("voice_4d_spec", "audio_type")).lower()
    speaker = str(dlg.get("speaker") or "").lower()
    if speaker in ("旁白", "narrator", "narration", "v.o.", "vo", "os", "o.s.", "畫外音"):
        return True
    if re.search(r"voiceover|v\.o\.|off[- ]?screen voice|inner voice|unseen voice|腦內聲|內心聲", spec):
        return True
    return False


def _has_visible_mouth(shot: Dict[str, Any]) -> bool:
    """H3 要自己念出來、因此能掛音色參考的台詞：畫內有可見嘴的對白。"""
    dlg = shot.get("dialogue_and_audio", {}) or {}
    if not (dlg.get("has_dialogue") or dlg.get("line_verbatim")):
        return False
    if _is_voiceover(shot):
        return False
    if dlg.get("lips_closed_lock") and dlg.get("voice_4d_spec"):
        # 有鎖嘴且標成畫外音者：語音由外部 TTS 負責，不掛 H3 音色參考
        return False
    return True


def collect_candidates(segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """列出每個角色在哪些段落有「可以拿來當母帶」的畫內台詞。"""
    rows: List[Dict[str, Any]] = []
    for seg in segments:
        for shot in seg.get("shots", []) or []:
            dlg = shot.get("dialogue_and_audio", {}) or {}
            if not dlg.get("has_dialogue") or not dlg.get("line_verbatim"):
                continue
            window = dlg.get("speech_window") or {}
            try:
                start = float(window.get("start"))
                end = float(window.get("end"))
            except (TypeError, ValueError):
                continue
            rows.append({
                "segment_id": seg.get("segment_id"),
                "shot_id": shot.get("shot_id"),
                "global_shot_id": shot.get("global_shot_id"),
                "speaker": dlg.get("speaker"),
                "line": dlg.get("line_verbatim"),
                "start": start,
                "end": end,
                "duration": round(end - start, 3),
                "visible_mouth": _has_visible_mouth(shot),
            })
    return rows


def pick_candidate(rows: List[Dict[str, Any]], segment_id: str, character: str,
                   shot_id: Optional[str], pick: str = "first") -> Dict[str, Any]:
    matches = [
        r for r in rows
        if r["segment_id"] == segment_id
        and r["speaker"] == character
        and (not shot_id or r["shot_id"] == shot_id)
    ]
    if not matches:
        raise SystemExit(
            f"[錯誤] 在段落 {segment_id} 找不到角色 {character} 的可用台詞"
            + (f"（shot {shot_id}）" if shot_id else "")
            + "。先用 --list 看有哪些候選。"
        )
    if pick == "longest":
        # 取最長的一句：母帶太短（<2 秒）不足以代表音色
        matches.sort(key=lambda r: (-r["duration"], r["start"]))
    else:
        # 第一次出場：觀眾第一次聽到這個角色，母帶就該是那一次表演
        matches.sort(key=lambda r: (r["start"], -r["duration"]))
    return matches[0]


def planned_duration_of(segments: List[Dict[str, Any]], segment_id: str) -> Optional[float]:
    """取該段編譯後的計畫有效片長（秒）。"""
    for seg in segments:
        if seg.get("segment_id") != segment_id:
            continue
        meta = seg.get("metadata") or {}
        for key in ("effective_duration_sec", "target_duration_sec"):
            try:
                value = float(meta.get(key))
            except (TypeError, ValueError):
                continue
            if value > 0:
                return value
    return None


def scaled_window(start: float, end: float, planned: Optional[float],
                  actual: float) -> Tuple[float, float, float]:
    """依實際片長校正時間窗。

    speech_window 是「計畫的段內秒」。若實際生成片長與計畫有漂移（FreeVideo 會把
    秒數向上取到 17n+5 影格量子），時間窗必須等比縮放，否則會切到錯的句子。
    回傳 (start, end, drift_seconds)。
    """
    if not planned or planned <= 0 or abs(actual - planned) <= 1e-6:
        return start, end, 0.0
    scale = actual / planned
    return start * scale, end * scale, actual - planned


# ==============================================================================
# 抽出
# ==============================================================================

def cut_audio(source: Path, start: float, end: float, out_wav: Path) -> float:
    """切出 [start, end) 的音軌並正規化成 48 kHz 單聲道 WAV。回傳實際寫出長度。"""
    ffmpeg = require_tool("ffmpeg")
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    out_wav.unlink(missing_ok=True)
    cmd = [
        ffmpeg, "-y", "-hide_banner", "-v", "error",
        "-ss", f"{start:.3f}", "-to", f"{end:.3f}", "-i", str(source),
        "-vn",
        "-ac", str(OUTPUT_CHANNELS),
        "-ar", str(OUTPUT_SAMPLE_RATE),
        "-c:a", "pcm_s16le",
        str(out_wav),
    ]
    result = run(cmd)
    if result.returncode != 0 or not out_wav.exists() or out_wav.stat().st_size == 0:
        raise SystemExit(
            f"[錯誤] ffmpeg 抽音失敗（{source} {start:.3f}–{end:.3f}s）：{(result.stderr or '')[:400]}"
        )
    return probe_duration(out_wav)


def write_provenance(out_wav: Path, payload: Dict[str, Any]) -> Path:
    sidecar = out_wav.with_suffix(out_wav.suffix + ".provenance.json")
    sidecar.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return sidecar


def binding_fragment(voice_id: str, rel_path: str, character: str, description: str) -> str:
    """給出可直接貼進 stage5 綁定檔的 audio_references 片段。"""
    return (
        "把下面這段加進該段的 stage5 綁定檔（video-bindings.json）：\n"
        "  \"audio_references\": [\n"
        "    {\n"
        f"      \"id\": \"{voice_id}\",\n"
        f"      \"path\": \"{rel_path}\",\n"
        f"      \"character_id\": \"{character}\",\n"
        "      \"role\": \"voice-timbre\",\n"
        f"      \"description_en\": \"{description}\"\n"
        "    }\n"
        "  ]"
    )


# ==============================================================================
# CLI
# ==============================================================================

def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="從已生成的影片或既有音檔抽出角色音色母帶（V-<slug>）"
    )
    parser.add_argument("--segments", type=Path, help="編譯後的 segments-epXX.json")
    parser.add_argument("--segment-id", type=str, help="母帶來源段落（例：EP01-S01-c）")
    parser.add_argument("--shot-id", type=str, help="同一段落內要取哪一句（可選，預設取最長的一句）")
    parser.add_argument("--character", type=str, help="角色 ID（例：C-luonien）")
    parser.add_argument("--videos-dir", type=Path, help="已生成影片所在目錄（送件工具輸出 videos/EP01-S01-c.mp4）")
    parser.add_argument("--from-audio", type=Path, help="改用既有音檔當母帶（TTS 克隆輸出）")
    parser.add_argument("--pick", type=str, default="first", choices=["first", "longest"],
                        help="同一角色在同一段有多句時挑哪一句：first=第一次出場那一句（預設）；longest=最長的一句")
    parser.add_argument("--start", type=float, help="自訂起點秒（僅 --from-audio）")
    parser.add_argument("--end", type=float, help="自訂終點秒（僅 --from-audio）")
    parser.add_argument("--output", type=Path, help="母帶輸出路徑（建議 assets/voices/V-<slug>-master-v1.wav；--list 模式不需要）")
    parser.add_argument("--list", action="store_true", help="列出所有可當母帶的候選台詞")
    args = parser.parse_args(argv)

    if args.list:
        if not args.segments:
            raise SystemExit("[錯誤] --list 需要 --segments")
        rows = collect_candidates(load_segments(args.segments))
        if not rows:
            print("沒有找到任何帶 speech_window 的台詞。")
            return 0
        print(f"{'段落':<14}{'鏡':<8}{'角色':<16}{'長度':>6}  {'可當母帶':<8}台詞")
        print("-" * 110)
        for r in rows:
            usable = "✔" if (r["visible_mouth"] and VOICE_MIN_SECONDS <= r["duration"] <= VOICE_MAX_SECONDS) else "✘"
            reason = ""
            if not r["visible_mouth"]:
                reason = "（畫外音→語音由外部 TTS 負責）"
            elif r["duration"] < VOICE_MIN_SECONDS:
                reason = f"（<{VOICE_MIN_SECONDS:.0f}s，太短）"
            line = str(r["line"] or "")
            print(f"{r['segment_id']:<14}{r['shot_id']:<8}{str(r['speaker']):<16}{r['duration']:>6.2f}  {usable:<8}{line[:38]}{reason}")
        print(f"\n✔ = 可直接拿來當音色母帶（畫內有可見嘴的對白，且 {VOICE_MIN_SECONDS:.0f}–{VOICE_MAX_SECONDS:.0f} 秒）")
        return 0

    if not args.character:
        raise SystemExit("[錯誤] 需要 --character（或用 --list）")
    if not args.output:
        raise SystemExit("[錯誤] 需要 --output（母帶輸出路徑）")

    voice_id = args.output.stem.replace("-master-v1", "") or args.output.stem
    description = "a single speaker's line recorded dry with no music"

    if args.from_audio:
        source = args.from_audio
        if not source.is_file():
            raise SystemExit(f"[錯誤] 找不到音檔: {source}")
        start = args.start if args.start is not None else 0.0
        end = args.end
        if end is None:
            end = start + VOICE_MAX_SECONDS
        if not VOICE_MIN_SECONDS <= (end - start) <= VOICE_MAX_SECONDS:
            raise SystemExit(
                f"[錯誤] 母帶長度必須介於 {VOICE_MIN_SECONDS:.0f}–{VOICE_MAX_SECONDS:.0f} 秒，"
                f"目前是 {end - start:.3f} 秒。"
            )
        line_text = ""
        segment_id = shot_id = ""
    else:
        if not (args.segments and args.segment_id and args.videos_dir):
            raise SystemExit("[錯誤] 從生成片抽母帶需要 --segments、--segment-id、--videos-dir、--character")
        rows = collect_candidates(load_segments(args.segments))
        candidate = pick_candidate(rows, args.segment_id, args.character, args.shot_id, args.pick)
        if not candidate["visible_mouth"]:
            print(f"[警告] {candidate['shot_id']} 的這句是畫外音／鎖嘴台詞，"
                  f"H3 不會自己念，音色參考掛上去也不會被用到。")
        if not VOICE_MIN_SECONDS <= candidate["duration"] <= VOICE_MAX_SECONDS:
            raise SystemExit(
                f"[錯誤] 這一句只有 {candidate['duration']:.3f} 秒，"
                f"母帶必須介於 {VOICE_MIN_SECONDS:.0f}–{VOICE_MAX_SECONDS:.0f} 秒。"
                f"請改挑同一角色更長的一句（用 --list 找）。"
            )
        source = args.videos_dir / f"{args.segment_id}.mp4"
        if not source.is_file():
            raise SystemExit(f"[錯誤] 找不到已生成的影片: {source}（先跑完該段生成）")
        start, end = candidate["start"], candidate["end"]
        line_text = str(candidate["line"] or "")
        segment_id = str(candidate["segment_id"])
        shot_id = str(candidate["shot_id"])
        # 計畫片長 vs 實際片長：FreeVideo 會把秒數向上取到 17n+5 影格量子，
        # 有漂移時時間窗必須等比縮放，否則會切到錯的句子。
        planned = planned_duration_of(load_segments(args.segments), segment_id)
        actual = probe_duration(source)
        start, end, drift = scaled_window(start, end, planned, actual)

    print(f"== 抽取音色母帶 ==")
    print(f"   角色      : {args.character}（音色資產 {voice_id}）")
    if segment_id:
        print(f"   來源      : {source}  [{segment_id} / {shot_id}]")
        print(f"   時間窗    : {start:.3f}–{end:.3f}s（{end - start:.3f}s，取自 Layer 2 的 speech_window）")
        if abs(drift) > 0.001:
            print(f"   ⚠️ 片長漂移 {drift:+.3f}s（計畫 {planned:.3f}s → 實際 {actual:.3f}s），時間窗已等比縮放。")
        print(f"   原句      : {line_text}")
    else:
        print(f"   來源      : {source}")
        print(f"   時間窗    : {start:.3f}–{end:.3f}s（{end - start:.3f}s）")

    written = cut_audio(source, start, end, args.output)
    if written < VOICE_MIN_SECONDS - 0.05:
        args.output.unlink(missing_ok=True)
        raise SystemExit(
            f"[錯誤] 實際抽到 {written:.3f} 秒（不足 {VOICE_MIN_SECONDS:.0f} 秒），已刪除輸出檔。"
            f"母帶太短無法代表音色，請換一句更長的台詞。"
        )

    provenance = {
        "voice_id": voice_id,
        "character_id": args.character,
        "source_file": str(source.resolve()),
        "source_sha256": sha256_of(source),
        "source_kind": "generated_segment" if segment_id else "external_audio",
        "segment_id": segment_id,
        "shot_id": shot_id,
        "line_verbatim": line_text,
        "window_seconds": {"start": round(start, 3), "end": round(end, 3)},
        "window_seconds_planned": {"start": round(candidate["start"], 3), "end": round(candidate["end"], 3)} if segment_id else None,
        "planned_duration_seconds": round(planned, 3) if planned else None,
        "actual_duration_seconds": round(actual, 3) if segment_id else None,
        "duration_drift_seconds": round(drift, 3) if segment_id else None,
        "output_file": str(args.output.resolve()),
        "output_sha256": sha256_of(args.output),
        "output_duration_seconds": round(written, 3),
        "output_format": {
            "sample_rate": OUTPUT_SAMPLE_RATE,
            "channels": OUTPUT_CHANNELS,
            "codec": "pcm_s16le",
        },
        "note": "H3 的音色參考是重新合成而非音軌複製；母帶帶著該場景的環境音是已知取捨。",
    }
    sidecar = write_provenance(args.output, provenance)

    print(f"   ✅ 母帶輸出: {args.output}（{written:.3f}s, {args.output.stat().st_size} bytes）")
    print(f"   ✅ 稽核紀錄: {sidecar}")
    print()
    print(binding_fragment(
        voice_id,
        args.output.as_posix(),
        args.character,
        description,
    ))
    print()
    print("接著：把這條母帶掛到該角色**所有**段落的 stage5 綁定檔，")
    print("編譯器就會自動產生 <Audio N> 綁定與 `reference` 保留標記。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
