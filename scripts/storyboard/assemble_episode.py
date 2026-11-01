#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
assemble_episode.py — AI 漫劇階段 7 配音分層、字幕燒錄與 FFmpeg 拼接交付工具 (v1.0)

用途：
實作階段 7 配音分層決策方案 A（外部清晰 TTS 重配 + H3 原生背景音保留壓低混音）與方案 B/C，
自動讀取 timeline / segments / narration，一鍵完成：
  1. 多後端 TTS 語音生成（微軟 Edge-TTS 優先，遇 403 自動無縫降級至 Windows 原生 SAPI 離線生成）；
  2. 精確時間軸混音（adelay + amix 保留打擊擬音與環境音）；
  3. SRT 字幕自動生成與高對比樣式燒錄（內建 Windows 路徑 C\\:/ 冒號轉義）；
  4. FFmpeg Concat 協議無縫拼接交付最終完整成片 mp4；
  5. 自動產出階段 7 交付清單 (delivery-epXX.md)。

CLI 用法：
  python scripts/storyboard/assemble_episode.py --segments segments-ep01.json --videos-dir videos/ --output videos/final-ep01.mp4
  python scripts/storyboard/assemble_episode.py --timeline timeline-ep01.csv --videos-dir videos/ --output final.mp4
  python scripts/storyboard/assemble_episode.py --self-test
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import struct
from typing import Any, Dict, List, Optional, Tuple
import wave
from unittest.mock import patch

try:  # ffmpeg／ffprobe 位置（AICD_FFMPEG／AICD_FFPROBE 可覆寫）
    import media_tools
except ImportError:  # pragma: no cover - 套件匯入路徑
    from . import media_tools

try:  # 跨段「以對白為錨」電平對齊（dialogue_loudness.py）
    import dialogue_loudness
except ImportError:  # pragma: no cover - 套件匯入路徑
    from . import dialogue_loudness

try:  # 雙人引子 dual_lead_in（spatial-consistency.md §7）：組裝時自動剪掉片頭
    import dual_lead_in
except ImportError:  # pragma: no cover - 套件匯入路徑
    from . import dual_lead_in

# 段與成片音訊位元率：ffmpeg 原生 aac 在 192k 遇密集低頻會過衝（限幅後仍超 0 dBFS），256k 無此現象
AAC_BITRATE = "256k"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


# ==============================================================================
# TTS 引擎封裝 (Edge-TTS + Windows SAPI 離線備案)
# ==============================================================================

try:  # 多後端 TTS 模組（VoiceStudio／Fish Audio／自帶 API）
    import tts_engine as tts_module  # type: ignore
except Exception:  # pragma: no cover - 模組缺失時退回內建實作
    tts_module = None  # type: ignore

SAPI_PS_SCRIPT = """param ([string]$text, [string]$outFile)
Add-Type -AssemblyName System.Speech
$speak = New-Object System.Speech.Synthesis.SpeechSynthesizer
$speak.SetOutputToWaveFile($outFile)
$speak.Speak($text)
$speak.Dispose()
"""

def generate_sapi_tts(text: str, out_wav: Path) -> bool:
    """使用 Windows 原生 SAPI (PowerShell) 離線生成語音 WAV。"""
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix=".ps1", encoding="utf-8", delete=False) as tf:
        tf.write(SAPI_PS_SCRIPT)
        ps1_path = Path(tf.name)

    try:
        cmd = [
            "powershell", "-ExecutionPolicy", "Bypass", "-File", str(ps1_path),
            "-text", text, "-outFile", str(out_wav)
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return res.returncode == 0 and out_wav.exists() and out_wav.stat().st_size > 1000
    except Exception as e:
        print(f"   [!] SAPI TTS 例外: {e}")
        return False
    finally:
        try:
            ps1_path.unlink()
        except Exception:
            pass


async def _edge_tts_async(text: str, voice: str, out_file: Path) -> bool:
    import edge_tts
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(str(out_file))
    return out_file.exists() and out_file.stat().st_size > 1000


def generate_edge_tts(text: str, out_file: Path, voice: str = "zh-TW-YunJheNeural") -> bool:
    """調用 edge-tts 生成語音檔。"""
    try:
        asyncio.run(_edge_tts_async(text, voice, out_file))
        return out_file.exists() and out_file.stat().st_size > 1000
    except Exception as e:
        return False


def synthesize_speech(
    text: str,
    out_wav: Path,
    engine: str = "auto",
    speaker: str = "",
    config: Optional[Dict[str, Any]] = None,
    voice: Optional[str] = None,
    language: Optional[str] = None,
) -> str:
    """智慧語音合成器。

    主線走 `tts_engine` 模組的多後端介面：voicestudio（本機 VoiceStudio／OmniVoice）
    → fish（Fish Audio）→ openai_compat（自帶 API）→ sapi（Windows 離線備援）依序降級。
    `tts_engine` 模組不可用時才退回本檔內建的 edge／sapi 實作。
    角色音色以資產 ID（如 V-lin-zhao）交由設定檔 voice_map 對映到供應商音色。
    """
    clean_text = re.sub(r"[^\w\u4e00-\u9fff，。！？、 ]", "", text).strip()
    if not clean_text:
        return ""

    out_wav.parent.mkdir(parents=True, exist_ok=True)

    module_reason = ""
    if tts_module is not None:
        result = tts_module.synthesize(
            clean_text, out_wav, engine=engine, speaker=speaker,
            voice=voice, language=language, config=config,
        )
        if result.get("ok"):
            return str(result.get("engine") or engine)
        if engine != "auto":
            raise RuntimeError(f"TTS 合成失敗 ({engine}): {result.get('reason')}")
        # auto：多後端都失敗才退回內建備援；保留原因，否則最後只看到「Edge 與 SAPI 失敗」而不知道主線為何不行。
        module_reason = str(result.get("reason") or "")

    # ---- 內建離線備援 ----
    # 角色音色推測（僅備援路徑使用；主線以設定檔 voice_map 為準）
    is_female = any(k in speaker.lower() for k in ["female", "woman", "girl", "ye", "shan", "女", "珊"])
    edge_voice = "zh-TW-HsiaoChenNeural" if is_female else "zh-TW-YunJheNeural"

    if engine == "edge":
        if generate_edge_tts(clean_text, out_wav, edge_voice):
            return "edge-tts"
        raise RuntimeError("Edge-TTS 生成失敗 (2026-10-10 起微軟要求 v2 Sec-MS-GEC token，edge-tts 7.2.8 會 403)")

    elif engine == "sapi":
        if generate_sapi_tts(clean_text, out_wav):
            return "windows-sapi"
        raise RuntimeError("Windows SAPI 生成失敗")

    elif engine == "auto":
        # 優先 Edge-TTS
        if generate_edge_tts(clean_text, out_wav, edge_voice):
            return "edge-tts"
        # 降級至 SAPI 備案
        if generate_sapi_tts(clean_text, out_wav):
            return "windows-sapi (fallback)"
        detail = f"；多後端 tts_engine 失敗原因：{module_reason}" if module_reason else ""
        raise RuntimeError("語音生成雙引擎 (Edge-TTS 與 SAPI) 均失敗！" + detail
                           + "（先跑 tts_doctor.py 看哪個引擎可用，再用 --tts-engine 指定）")

    return "none"


# ==============================================================================
# FFmpeg 濾鏡與字元轉義 (Windows 專用路徑保護)
# ==============================================================================

def escape_ffmpeg_path(path: Path) -> str:
    """把檔案路徑轉成 filtergraph 裡可直接當選項值的字串（不要再包單引號）。

    ffmpeg 有兩層跳脫（見官方「Notes on filtergraph escaping」）：
      1. 選項值層：`\\`、`'`、`:` 前面加反斜線（Windows 磁碟代號 `C:` → `C\\:`）；
      2. filtergraph 層：`\\`、`'`、`[`、`]`、`,`、`;` 前面再加反斜線。
    舊版只做第一層又包在單引號裡，路徑含 `'`（例如 `Tom's Drama`）時 subtitles 濾鏡會開不到檔。
    """
    value = str(path.resolve()).replace("\\", "/")
    level1 = value.replace("\\", "\\\\").replace("'", "\\'").replace(":", "\\:")
    return "".join("\\" + ch if ch in "\\'[],;" else ch for ch in level1)


def probe_video_specs(video_path: Path) -> Dict[str, Any]:
    """Read stream presence and duration without decoding the media."""
    result = subprocess.run([
        media_tools.ffprobe_bin(), "-v", "error", "-show_entries",
        "format=duration:stream=codec_type,width,height", "-of", "json", str(video_path),
    ], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe 無法讀取 {video_path.name}: {result.stderr[:400]}")
    info = json.loads(result.stdout)
    streams = info.get("streams", [])
    try:
        duration = float(info.get("format", {}).get("duration", 0) or 0)
    except (TypeError, ValueError):
        duration = 0.0
    return {
        "has_video": any(s.get("codec_type") == "video" for s in streams),
        "has_audio": any(s.get("codec_type") == "audio" for s in streams),
        "duration": duration,
    }


def probe_audio_duration(audio_path: Path) -> float:
    """Return decoded audio stream duration, rejecting missing/invalid audio."""
    result = subprocess.run([
        media_tools.ffprobe_bin(), "-v", "error", "-show_entries", "format=duration:stream=codec_type,duration",
        "-of", "json", str(audio_path),
    ], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe 無法讀取 TTS 音訊: {result.stderr[:300]}")
    info = json.loads(result.stdout)
    audio_streams = [s for s in info.get("streams", []) if s.get("codec_type") == "audio"]
    if not audio_streams:
        raise RuntimeError("TTS 檔案沒有 audio stream")
    raw_duration = audio_streams[0].get("duration") or (info.get("format") or {}).get("duration")
    duration = float(raw_duration or 0)
    if not math.isfinite(duration) or duration <= 0:
        raise RuntimeError("TTS 音訊時長無效")
    return duration


def validate_video_decode(video_path: Path) -> Dict[str, Any]:
    """Decode every frame and audio packet; a probe alone does not prove validity."""
    specs = probe_video_specs(video_path)
    if not specs["has_video"]:
        return {"decode_ok": False, "duration": specs["duration"], "error": "no video stream"}
    result = subprocess.run([
        media_tools.ffmpeg_bin(), "-v", "error", "-xerror", "-i", str(video_path), "-f", "null", "-",
    ], capture_output=True, text=True, encoding="utf-8", errors="replace")
    return {
        "decode_ok": result.returncode == 0,
        "duration": specs["duration"],
        "has_audio": specs["has_audio"],
        "error": result.stderr[:500] if result.returncode else "",
    }


def compute_file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def expected_segment_duration(segment: Dict[str, Any]) -> float:
    metadata = segment.get("metadata") or {}
    # metadata.frames 是編譯器寫的權威影格數（17n+5），影片實際長度＝frames/24；
    # 只寫 target_duration_sec 的舊／手寫分段若不先看 frames，會拿未量化秒數去比 ±0.1s 而誤判。
    frames = metadata.get("frames")
    if isinstance(frames, (int, float)) and not isinstance(frames, bool) and int(frames) > 0:
        return int(frames) / 24.0
    candidates = [metadata.get("effective_duration_sec"), metadata.get("target_duration_sec"), segment.get("seconds")]
    for candidate in candidates:
        try:
            value = float(candidate)
            if value > 0:
                return value
        except (TypeError, ValueError):
            continue
    shots = segment.get("shots") or []
    try:
        total = sum(float(shot.get("duration", 0) or 0) for shot in shots)
        if total > 0:
            return total
    except (TypeError, ValueError):
        pass
    raise ValueError(f"分段 {segment.get('segment_id') or segment.get('id') or '?'} 沒有有效的預期時長")


def timeline_segment_id(row: Dict[str, Any]) -> str:
    explicit = row.get("segment_id") or row.get("segment") or row.get("group")
    if explicit:
        return str(explicit)
    shot_id = str(row.get("shot_id", ""))
    match = re.match(r"^(.*?)-SH\d+$", shot_id, re.IGNORECASE)
    if not match:
        raise ValueError(f"timeline row {shot_id!r} lacks segment_id and does not end with -SH<number>")
    return match.group(1)


def source_input_record(path: Path) -> Dict[str, str]:
    resolved = path.resolve()
    return {"path": str(resolved), "sha256": compute_file_sha256(resolved)}


def sec_to_srt_time(sec: float) -> str:
    """秒數轉 SRT 時間格式 HH:MM:SS,mmm"""
    hours = int(sec // 3600)
    minutes = int((sec % 3600) // 60)
    seconds = int(sec % 60)
    millis = int(round((sec - int(sec)) * 1000))
    if millis >= 1000:
        seconds += 1
        millis = 0
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


# ==============================================================================
# 單分段混音、字幕燒錄與組裝
# ==============================================================================

NO_LINE_TEXTS = {"（無台詞）", "(無台詞)", "無台詞"}


def _window_bounds(window: Any) -> Optional[Tuple[float, float]]:
    if isinstance(window, dict) and window.get("start") is not None and window.get("end") is not None:
        return float(window["start"]), float(window["end"])
    return None


def collect_dialogue_lines(seg: Dict[str, Any], audio_mode: str = "auto") -> List[Dict[str, Any]]:
    """一段要燒字幕／合成的台詞（段內秒、雙人引子未剪前的原片時間）。

    每鏡主句：dialogue_and_audio.line_verbatim（或 subtitle／narration），時間窗優先 speech_window，
    沒有才退回鏡頭時間。#120 同鏡接話：dialogue_and_audio.extra_lines[] 每句依它自己的 speech_window
    一起收進來（speaker 用該句的 speaker）；接話一定要有 speech_window，缺了丟 ValueError（不猜位置，
    以免和主句字幕疊在一起）。narration_only 只收旁白，不收接話。回傳依 start 排序。
    雙人引子（dual_lead_in）在 process_single_segment 統一前移／剪除，這裡不處理。"""
    lines_info: List[Dict[str, Any]] = []
    for s in seg.get("shots", []) or []:
        if not isinstance(s, dict):
            continue
        dlg = s.get("dialogue_and_audio") or {}
        if audio_mode == "narration_only":
            text = s.get("narration") or ""
        else:
            text = dlg.get("line_verbatim") or s.get("subtitle") or s.get("narration") or ""
        if text and str(text).strip() not in NO_LINE_TEXTS:
            st = float(s.get("start_time") or s.get("start") or 0.0)
            et = float(s.get("end_time") or s.get("end") or (st + float(s.get("duration", 2.5))))
            # 對白窗口優先用 speech_window（段內秒），沒有才退回鏡頭時間；
            # 這是 TTS 落點與畫面嘴型的對齊基準。
            bounds = _window_bounds(dlg.get("speech_window"))
            if bounds:
                st, et = bounds
            spk = dlg.get("speaker") or s.get("speaker") or ""
            lines_info.append({"start": st, "end": et, "subtitle": text, "speaker": spk,
                               "window_source": "speech_window" if bounds else "shot_window"})
        if audio_mode == "narration_only":
            continue
        for i, ex in enumerate(dlg.get("extra_lines") or [], start=1):
            if not isinstance(ex, dict):
                continue
            ex_text = str(ex.get("line_verbatim") or "").strip()
            if not ex_text or ex_text in NO_LINE_TEXTS:
                continue
            bounds = _window_bounds(ex.get("speech_window"))
            if not bounds:
                raise ValueError(f"{s.get('shot_id') or '?'} extra_lines[{i}]「{ex_text}」缺 speech_window"
                                 f"（start/end 段內秒），組裝無法定位這句接話的字幕／配音")
            lines_info.append({"start": bounds[0], "end": bounds[1], "subtitle": ex_text,
                               "speaker": ex.get("speaker") or "", "extra_line": True,
                               "window_source": "speech_window"})
    lines_info.sort(key=lambda item: float(item["start"]))
    return lines_info


def process_single_segment(
    in_video: Path,
    out_video: Path,
    lines_info: List[Dict[str, Any]],
    seg_duration: float,
    audio_mode: str = "tts_replace",
    tts_engine: str = "auto",
    tts_config: Optional[Dict[str, Any]] = None,
    bg_volume: float = 0.15,
    burn_subtitles: bool = True,
    temp_dir: Optional[Path] = None,
    audio_required: bool = False,
    lead_in_s: float = 0.0,
) -> Tuple[bool, str]:
    """針對單個分段執行 TTS 生成、adelay 混音與字幕燒錄。

    lead_in_s>0（雙人引子，spatial-consistency.md §7）：先剪掉片頭 lead_in_s 秒，台詞時間窗一併前移；
    seg_duration 仍是來源影片長度，輸出長度＝seg_duration − lead_in_s。預設 0＝不剪，行為與舊版相同。
    """
    t_dir = temp_dir or (out_video.parent / "tmp_audio")
    t_dir.mkdir(parents=True, exist_ok=True)
    lead = float(lead_in_s or 0.0)
    if lead < 0 or (lead and lead >= seg_duration):
        return False, f"雙人引子 {lead:g}s 無效（要 ≥0 且短於分段 {seg_duration:.3f}s）"
    source_duration = seg_duration
    if lead:
        shifted = []
        for item in lines_info:
            st = float(item.get("start", 0.0))
            et = float(item.get("end", st + 2.5))
            if st < lead - 1e-6:
                return False, f"台詞「{item.get('subtitle') or ''}」從 {st:.3f}s 開始，落在要剪掉的雙人引子（0–{lead:.3f}s）裡"
            shifted.append({**item, "start": st - lead, "end": et - lead})
        lines_info = shifted
        seg_duration = source_duration - lead

    # 1. 生成字幕 SRT
    srt_file = t_dir / f"{in_video.stem}.srt"
    srt_lines = []
    tts_tracks: List[Tuple[Path, int]] = []  # (wav_path, delay_ms)

    tts_failures: List[str] = []
    for idx, item in enumerate(lines_info, 1):
        line_text = item.get("subtitle") or item.get("line_verbatim") or item.get("text") or ""
        if not line_text:
            continue
        start_sec = float(item.get("start", 0.0))
        end_sec = float(item.get("end", start_sec + 2.5))
        if start_sec < 0 or end_sec <= start_sec or end_sec > seg_duration + 1e-6:
            return False, f"台詞 #{idx} 時間窗口無效或超出分段時長"

        srt_lines.append(f"{idx}\n{sec_to_srt_time(start_sec)} --> {sec_to_srt_time(end_sec)}\n{line_text}\n")

        # 準備 TTS 音訊
        if audio_mode in {"tts_replace", "narration_only"}:
            wav_path = t_dir / f"{in_video.stem}_line_{idx:02d}.wav"
            wav_path.unlink(missing_ok=True)
            speaker = item.get("speaker", "")
            try:
                synthesize_speech(
                    line_text, wav_path, engine=tts_engine, speaker=speaker, config=tts_config,
                )
                if not wav_path.exists() or wav_path.stat().st_size == 0:
                    raise RuntimeError("TTS 沒有產生有效音訊檔")
                actual_audio_duration = probe_audio_duration(wav_path)
                if actual_audio_duration > end_sec - start_sec + 0.02 or start_sec + actual_audio_duration > seg_duration + 0.02:
                    raise RuntimeError(
                        f"TTS 時長 {actual_audio_duration:.3f}s 超出台詞窗口 {end_sec - start_sec:.3f}s "
                        f"或分段結尾 {seg_duration:.3f}s；不會截斷/加速語音"
                    )
                delay_ms = max(0, int(start_sec * 1000))
                tts_tracks.append((wav_path, delay_ms))
            except Exception as e:
                tts_failures.append(f"台詞 #{idx}「{line_text}」合成失敗: {e}")

    if tts_failures:
        return False, "；".join(tts_failures)

    srt_file.write_text("\n".join(srt_lines), encoding="utf-8")

    # 2. 構建 FFmpeg 濾鏡鏈
    has_tts = len(tts_tracks) > 0 and audio_mode in {"tts_replace", "narration_only"}
    has_sub = len(srt_lines) > 0 and burn_subtitles
    try:
        source_specs = probe_video_specs(in_video)
    except Exception as exc:
        return False, f"無法讀取來源影片規格: {exc}"
    if not source_specs.get("has_video"):
        return False, f"來源影片沒有 video stream: {in_video}"
    if abs(float(source_specs.get("duration", 0)) - source_duration) > 0.1:
        return False, f"來源影片時長 {source_specs.get('duration', 0):.3f}s 與預期分段 {source_duration:.3f}s 相差超過 0.1s"
    has_native_audio = bool(source_specs.get("has_audio"))
    if audio_required and audio_mode == "native_sub" and not has_native_audio:
        return False, "分鏡要求音訊，但來源影片沒有音訊流"
    if audio_required and audio_mode in {"tts_replace", "narration_only"} and not tts_tracks:
        return False, "分鏡要求音訊，但沒有成功生成任何 TTS 音軌"

    cmd = [media_tools.ffmpeg_bin(), "-y", "-hide_banner", "-loglevel", "error", "-i", str(in_video)]
    for wav_p, _ in tts_tracks:
        cmd.extend(["-i", str(wav_p)])

    v_filter = ""
    if has_sub:
        esc_srt = escape_ffmpeg_path(srt_file)
        sub_style = "FontSize=20,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=2"
        v_filter = f"subtitles=filename={esc_srt}:force_style='{sub_style}'"

    # 原生音軌降音量只會降低其中的語音與環境音；不會分離或移除原生人聲。
    filter_complex_parts = []
    trim_a = f"atrim=start={lead:.6f},asetpts=PTS-STARTPTS," if lead else ""
    if lead:
        v_filter = f"trim=start={lead:.6f},setpts=PTS-STARTPTS" + ("," + v_filter if v_filter else "")
    if v_filter:
        filter_complex_parts.append(f"[0:v]{v_filter}[vout]")

    if has_tts:
        mix_inputs = []
        mix_native_audio = has_native_audio and audio_mode == "tts_replace"
        if mix_native_audio:
            filter_complex_parts.append(f"[0:a]{trim_a}aresample=48000,volume={bg_volume}[native]")
            mix_inputs.append("[native]")
        for i, (_, delay_ms) in enumerate(tts_tracks, 1):
            # adelay 的 all=1 才是單聲道來源的安全寫法；用 "|" 只對雙聲道有效。
            filter_complex_parts.append(f"[{i}:a]aresample=48000,adelay={delay_ms}:all=1[v{i}]")
            mix_inputs.append(f"[v{i}]")
        mix_str = "".join(mix_inputs)
        mix_duration = "longest"
        # amix 預設 normalize=1 會把輸出除以輸入數，等於把 TTS 人聲壓低約 3 dB
        # （實測：兩軌 440/880Hz 混音 −24.1 dB vs 來源 −21.1 dB）。
        # 改用 normalize=0 保住人聲電平，峰值交給後段的 loudnorm／alimiter 處理。
        filter_complex_parts.append(
            f"{mix_str}amix=inputs={len(mix_inputs)}:duration={mix_duration}:normalize=0:dropout_transition=0[mixed];"
            f"[mixed]apad,atrim=duration={seg_duration:.6f}[aout]"
        )
    elif has_native_audio:
        filter_complex_parts.append(f"[0:a]{trim_a}aresample=48000,apad,atrim=duration={seg_duration:.6f}[aout]")

    if filter_complex_parts:
        cmd.extend(["-filter_complex", ";".join(filter_complex_parts)])
        cmd.extend(["-map", "[vout]" if v_filter else "0:v"])
        if has_tts:
            cmd.extend(["-map", "[aout]"])
        elif has_native_audio:
            cmd.extend(["-map", "[aout]"])
        else:
            cmd.append("-an")
    else:
        cmd.extend(["-map", "0:v"])
        if has_native_audio:
            cmd.extend(["-map", "0:a"])
        else:
            cmd.append("-an")

    if filter_complex_parts:
        cmd.extend(["-c:v", "libx264", "-pix_fmt", "yuv420p"])
        if has_tts or has_native_audio:
            # 256k：ffmpeg 原生 aac 在 192k 遇密集低頻會過衝（EP01 重跑 E1-11 實測限幅後 −2.49 dBFS → 解碼 +0.45 dBFS）
            cmd.extend(["-c:a", "aac", "-b:a", AAC_BITRATE])
    else:
        cmd.extend(["-c:v", "copy"])
        if has_native_audio:
            cmd.extend(["-c:a", "copy"])

    staging_video = out_video.with_name(f".{out_video.stem}.{os.getpid()}.tmp{out_video.suffix}")
    staging_video.unlink(missing_ok=True)
    cmd.append(str(staging_video))

    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if res.returncode != 0 or not staging_video.exists() or staging_video.stat().st_size == 0:
        staging_video.unlink(missing_ok=True)
        return False, f"FFmpeg 處理分段 {in_video.name} 失敗: {res.stderr[:400]}"
    try:
        output_specs = probe_video_specs(staging_video)
    except Exception as exc:
        staging_video.unlink(missing_ok=True)
        return False, f"無法驗證處理後分段: {exc}"
    if not output_specs.get("has_video") or abs(float(output_specs.get("duration", 0)) - seg_duration) > 0.1:
        staging_video.unlink(missing_ok=True)
        return False, f"處理後分段時長 {output_specs.get('duration', 0):.3f}s 未落在預期 {seg_duration:.3f}s ±0.1s"
    staging_video.replace(out_video)
    return True, "成功"


# ==============================================================================
# FFmpeg Concat 協議無縫拼接
# ==============================================================================

def _concat_quote(path: Path) -> str:
    """concat demuxer 清單的單引號跳脫（`'` → `'\\''`）；拒絕換行。"""
    value = path.resolve().as_posix()
    if "\n" in value or "\r" in value:
        raise ValueError("影片路徑不得包含換行字元")
    return "'" + value.replace("'", "'\\''") + "'"


def build_pcm_audio_track(video_list: List[Path], work_dir: Path,
                          segment_filters: Optional[List[str]] = None) -> Optional[Path]:
    """逐段解成 PCM、長度鎖成該段影片時長再串接（#168）。

    concat demuxer 直接 -c copy 接 AAC 會讓各段 priming 疊加，出現
    Non-monotonic DTS 與 A/V 漂移。這裡每段先解 48 kHz 立體聲 PCM，
    補靜音或裁切到影片時長，再串成單一 wav，最後由呼叫端統一編碼。
    segment_filters[i]（選用）是第 i 段的增益／壓限濾鏡（dialogue_loudness.gain_filter），
    在 PCM 上套、再鎖長度，所以不會有逐段重編 AAC 尾巴多一個 frame 的時間軸漂移。
    全部分段都沒有音軌時回傳 None（沿用舊路徑）。
    """
    specs = [probe_video_specs(v) for v in video_list]
    if not any(sp["has_audio"] for sp in specs):
        return None
    wavs: List[Path] = []
    for idx, (video, sp) in enumerate(zip(video_list, specs)):
        dur = max(float(sp["duration"]), 0.0)
        wav = work_dir / f".pcm_{os.getpid()}_{idx:03d}.wav"
        fmt = "aresample=48000,aformat=channel_layouts=stereo"
        extra = (segment_filters[idx] if segment_filters and idx < len(segment_filters) else "") or ""
        if extra:
            fmt = f"{fmt},{extra},aformat=sample_rates=48000:channel_layouts=stereo"
        if sp["has_audio"]:
            cmd = [media_tools.ffmpeg_bin(), "-y", "-hide_banner", "-loglevel", "error", "-i", str(video.resolve()), "-vn",
                   "-af", f"{fmt},apad,atrim=0:{dur:.6f}"]
        else:
            cmd = [media_tools.ffmpeg_bin(), "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
                   "-i", "anullsrc=r=48000:cl=stereo", "-t", f"{dur:.6f}"]
        cmd += ["-c:a", "pcm_s16le", str(wav)]
        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if res.returncode != 0 or not wav.exists():
            for w in wavs:
                w.unlink(missing_ok=True)
            raise RuntimeError(f"解 PCM 失敗 {video.name}: {res.stderr[:300]}")
        wavs.append(wav)
    lst = work_dir / f".pcm_{os.getpid()}.txt"
    # 與 concat_videos 同一套引號規則：路徑含 `'` 時舊寫法會讓 concat demuxer 開不到檔。
    lst.write_text("".join(f"file {_concat_quote(w)}\n" for w in wavs), encoding="utf-8")
    joined = work_dir / f".pcm_{os.getpid()}_all.wav"
    res = subprocess.run([media_tools.ffmpeg_bin(), "-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0",
                          "-i", str(lst.resolve()), "-c", "copy", str(joined)],
                         capture_output=True, text=True, encoding="utf-8", errors="replace")
    for w in wavs:
        w.unlink(missing_ok=True)
    lst.unlink(missing_ok=True)
    if res.returncode != 0 or not joined.exists():
        raise RuntimeError(f"串接 PCM 失敗: {res.stderr[:300]}")
    return joined


def _loudnorm_two_pass_filter(pcm: Path, target_lufs: float, true_peak: float, lra: float,
                              total_seconds: float) -> Tuple[str, Dict[str, Any]]:
    """兩遍 loudnorm 的第二遍濾鏡：第一遍量 PCM，第二遍帶 measured_*＋linear=true。

    linear 模式是整條一個固定增益（不動態壓縮）；所需增益會讓 TP 超標時 loudnorm 自己回退 dynamic。
    loudnorm 輸出 192 kHz，在這個取樣率下 alimiter 近似 true-peak 限制（回退 dynamic 時開頭會冒峰），
    再降回 48 kHz、atrim 回原長（音畫同長）。"""
    m = dialogue_loudness.measure(str(pcm))
    lim = 10 ** ((float(true_peak) - dialogue_loudness.AAC_TP_MARGIN_DB) / 20.0)
    filt = (f"loudnorm=I={target_lufs}:TP={true_peak}:LRA={lra}"
            f":measured_I={m['I']}:measured_TP={m['TP']}:measured_LRA={m['LRA']}:measured_thresh={m['thresh']}"
            f":linear=true:print_format=json"
            f",alimiter=limit={lim:.4f}:attack=1:release=50:level=disabled"
            f",aresample=48000,atrim=end={total_seconds:.6f}")
    return filt, m


def concat_videos(
    video_list: List[Path],
    out_video: Path,
    target_lufs: Optional[float] = -23.0,
    true_peak: float = -1.5,
    lra: float = 11.0,
    segment_audio: Optional[List[Dict[str, Any]]] = None,
    align_options: Optional[Dict[str, Any]] = None,
    report: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, str]:
    """使用 FFmpeg concat 協議無縫拼接分段影片成片。

    響度兩層（pipeline.md §7.4）：
      1. 段層「以對白為錨」（segment_audio 有給時）：每段量對白區段響度、算固定增益對齊同一個錨點，
         無台詞段保持相對電平；增益在 PCM 上套（dialogue_loudness.py）。H3 每支 clip 原生音電平隨機，
         整片 loudnorm 修不了段間落差，所以要先做這一層。不是逐段正規化：段內動態不動、無台詞段不拉。
      2. 整片兩遍 loudnorm（measured_*＋linear=true），預設對齊 EBU R128（−23 LUFS、TP −1.5）。
    report（選用 dict）會寫入每段量測／增益、成片逐段 LUFS／TP 與段間落差。
    """
    out_video.parent.mkdir(parents=True, exist_ok=True)
    list_file = out_video.parent / f"concat_{out_video.stem}_{os.getpid()}.txt"

    lines = [f"file {_concat_quote(v)}" for v in video_list]
    list_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    staging_video = out_video.with_name(f".{out_video.stem}.{os.getpid()}.concat{out_video.suffix}")
    staging_video.unlink(missing_ok=True)
    opts = dict(align_options or {})
    tp_ceiling = float(opts.get("tp_ceiling", dialogue_loudness.DEFAULT_TP_CEILING_DBTP))

    segment_filters: Optional[List[str]] = None
    records: List[Dict[str, Any]] = []
    try:
        specs = [probe_video_specs(v) for v in video_list]
        if segment_audio is not None and len(segment_audio) == len(video_list) and any(sp["has_audio"] for sp in specs):
            for video, sp, info in zip(video_list, specs, segment_audio):
                rec = dialogue_loudness.measure_segment(
                    str(video), info.get("windows") or [], bool(info.get("has_dialogue")), float(sp["duration"]),
                    window_source=str(info.get("window_source") or "speech_window"), has_audio=bool(sp["has_audio"]))
                rec["segment_id"] = info.get("segment_id") or video.stem
                records.append(rec)
            if "tp_ceiling" not in opts:
                anchor, _ = dialogue_loudness.anchor_of(records, opts.get("anchor_lufs"))
                tp_ceiling = dialogue_loudness.segment_tp_ceiling(anchor, target_lufs, true_peak)
            summary = dialogue_loudness.plan_gains(
                records, anchor_lufs=opts.get("anchor_lufs"),
                max_gain_db=float(opts.get("max_gain_db", dialogue_loudness.DEFAULT_MAX_GAIN_DB)),
                ambient_ceiling_lu=float(opts.get("ambient_ceiling_lu", dialogue_loudness.DEFAULT_AMBIENT_CEILING_LU)),
                tp_ceiling=tp_ceiling)
            if opts.get("apply", True):
                segment_filters = [dialogue_loudness.gain_filter(r["gain_db"], r["limit"], tp_ceiling) for r in records]
            else:  # --no-dialogue-align：只量測、列報告，不套增益
                for r in records:
                    r["planned_gain_db"], r["gain_db"], r["limit"] = r["gain_db"], 0.0, False
                summary["applied"] = False
            summary.setdefault("applied", True)
            if report is not None:
                report["dialogue_align"] = summary
        pcm = build_pcm_audio_track(video_list, out_video.parent, segment_filters)
    except Exception as exc:
        list_file.unlink(missing_ok=True)
        return False, f"拼接失敗: {exc}"
    total_seconds = sum(max(float(sp["duration"]), 0.0) for sp in specs)
    cmd = [
        media_tools.ffmpeg_bin(), "-y", "-hide_banner", "-nostats", "-f", "concat", "-safe", "0",
        "-i", str(list_file.resolve()),
    ]
    first_pass: Optional[Dict[str, Any]] = None
    if pcm is not None:
        cmd.extend(["-i", str(pcm.resolve()), "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
                    "-c:a", "aac", "-b:a", AAC_BITRATE, "-ar", "48000"])
        if target_lufs is not None:
            try:
                loud, first_pass = _loudnorm_two_pass_filter(pcm, target_lufs, true_peak, lra, total_seconds)
            except Exception as exc:
                list_file.unlink(missing_ok=True)
                pcm.unlink(missing_ok=True)
                return False, f"拼接失敗（loudnorm 第一遍量測）: {exc}"
            cmd.extend(["-af", loud])
    else:
        # 全部分段都沒有音軌：純影像串接，沒有東西可以正規化。
        cmd.extend(["-c", "copy"])
    # 不加 -movflags +faststart：在 JuiceFS 等網路檔案系統上改寫 trailer 會 I/O error（EP01 重跑實測）。
    cmd.append(str(staging_video.resolve()))
    res = subprocess.run(cmd, cwd=str(out_video.parent), capture_output=True, text=True, encoding="utf-8", errors="replace")
    try:
        list_file.unlink()
    except Exception:
        pass
    if pcm is not None:
        pcm.unlink(missing_ok=True)

    if res.returncode != 0 or not staging_video.exists() or staging_video.stat().st_size == 0:
        staging_video.unlink(missing_ok=True)
        return False, f"拼接失敗: {res.stderr[:400]}"
    if report is not None and pcm is not None:
        try:
            _fill_loudness_report(report, staging_video, specs, segment_audio, records, first_pass, res.stderr,
                                  float(opts.get("spread_warn_lu", dialogue_loudness.DEFAULT_SPREAD_WARN_LU)))
        except Exception as exc:  # 報告失敗不擋交付，但要看得到
            report.setdefault("warnings", []).append(f"響度報告量測失敗：{exc}")
    staging_video.replace(out_video)
    return True, "成功"


def _fill_loudness_report(report: Dict[str, Any], final_video: Path, specs: List[Dict[str, Any]],
                          segment_audio: Optional[List[Dict[str, Any]]], records: List[Dict[str, Any]],
                          first_pass: Optional[Dict[str, Any]], second_pass_stderr: str,
                          spread_warn_lu: float) -> None:
    """成片量測：整片 I／TP／LRA、逐段（依段界）整段與對白區段 LUFS／TP、最大段間落差，超門檻 W49。"""
    found = re.findall(r"\{[^{}]*\"input_i\"[^{}]*\}", second_pass_stderr or "", re.S)
    if first_pass is not None:
        report["film_loudnorm"] = {"first_pass": first_pass}
        if found:
            p2 = json.loads(found[-1])
            report["film_loudnorm"]["normalization_type"] = p2.get("normalization_type")
            report["film_loudnorm"]["target_offset"] = p2.get("target_offset")
    report["film"] = dialogue_loudness.measure(str(final_video))
    seg_rows: List[Dict[str, Any]] = []
    cursor = 0.0
    for idx, sp in enumerate(specs):
        dur = max(float(sp["duration"]), 0.0)
        info = (segment_audio[idx] if segment_audio and idx < len(segment_audio) else {}) or {}
        rec = records[idx] if idx < len(records) else {}
        row: Dict[str, Any] = {"segment_id": info.get("segment_id") or rec.get("segment_id") or f"#{idx + 1}",
                               "start": round(cursor, 3), "duration": round(dur, 3),
                               "role": rec.get("role") or ("dialogue" if info.get("has_dialogue") else "ambient"),
                               "gain_db": rec.get("gain_db", 0.0), "limit": rec.get("limit", False),
                               "flags": rec.get("flags", []), "speech_source": rec.get("speech_source")}
        if rec.get("whole"):
            row["before_I"], row["before_TP"] = rec["whole"]["I"], rec["whole"]["TP"]
        if rec.get("speech"):
            row["before_speech_I"] = rec["speech"]["I"]
        if sp.get("has_audio") and dur >= dialogue_loudness.MIN_MEASURE_SECONDS:
            after = dialogue_loudness.measure(str(final_video), start=cursor, duration=dur)
            row["after_I"], row["after_TP"] = after["I"], after["TP"]
            wins = dialogue_loudness.clip_windows(rec.get("windows") or info.get("windows") or [], dur)
            if row["role"] == "dialogue" and wins and sum(e - s for s, e in wins) >= dialogue_loudness.MIN_MEASURE_SECONDS \
                    and rec.get("speech_source") != "energy":
                row["after_speech_I"] = dialogue_loudness.measure(str(final_video), wins, start=cursor, duration=dur)["I"]
            elif row["role"] == "dialogue":
                row["after_speech_I"] = after["I"]
        seg_rows.append(row)
        cursor += dur
    report["segments"] = seg_rows
    dlg = [r for r in seg_rows if r["role"] == "dialogue"]
    report["spread"] = {
        "dialogue_before": dialogue_loudness.spread([r.get("before_speech_I") for r in dlg]),
        "dialogue_after": dialogue_loudness.spread([r.get("after_speech_I") for r in dlg]),
        "all_segments_after": dialogue_loudness.spread([r.get("after_I") for r in seg_rows]),
        "warn_threshold_lu": spread_warn_lu,
    }
    after_spread = report["spread"]["dialogue_after"]["max_minus_min"]
    if after_spread is not None and after_spread > spread_warn_lu:
        loud = max(dlg, key=lambda r: r.get("after_speech_I") or -99)
        quiet = min(dlg, key=lambda r: r.get("after_speech_I") if r.get("after_speech_I") is not None else 99)
        report.setdefault("warnings", []).append(
            f"W49 段間對白電平落差 {after_spread:.2f} LU > {spread_warn_lu:g} LU"
            f"（最響 {loud['segment_id']} {loud.get('after_speech_I')}、最小 {quiet['segment_id']} {quiet.get('after_speech_I')} LUFS）；"
            f"看是否被增益上限截住（flags clamped_*／tp_capped），或對白區段時間窗不準")


# ==============================================================================
# 自檢測試模式 (--self-test)
# ==============================================================================

def run_self_test() -> bool:
    """離線合成測試音與短片，驗證混音、字幕燒錄、拼接，不呼叫雲端或系統 TTS。"""
    print("\n" + "=" * 70)
    print("🧪 啟動 assemble_episode 階段 7 全鏈路自動化自檢 (--self-test)")
    print("=" * 70)

    with tempfile.TemporaryDirectory(dir=Path.cwd()) as td:
        t_path = Path(td)
        vid1 = t_path / "test_seg01.mp4"
        vid2 = t_path / "test_seg02.mp4"

        # 1. 產生兩段測試短片 (帶基本音訊)
        cmd1 = [
            media_tools.ffmpeg_bin(), "-y", "-f", "lavfi", "-i", "color=c=blue:s=640x360:d=4.0:r=24",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=4.0",
            "-c:v", "libx264", "-c:a", "aac", str(vid1)
        ]
        cmd2 = [
            media_tools.ffmpeg_bin(), "-y", "-f", "lavfi", "-i", "color=c=green:s=640x360:d=4.0:r=24",
            "-f", "lavfi", "-i", "sine=frequency=880:duration=4.0",
            "-c:v", "libx264", "-c:a", "aac", str(vid2)
        ]
        subprocess.run(cmd1, capture_output=True, check=True)
        subprocess.run(cmd2, capture_output=True, check=True)
        print("✅ 成功產生 2 段測試短片 (4.0s 藍底 + 4.0s 綠底)")

        # 2. 測試配音、字幕與混音
        lines1 = [{"start": 1.0, "end": 3.0, "subtitle": "第一段測試台詞，清晰度確認。", "speaker": "A"}]
        lines2 = [{"start": 1.0, "end": 3.0, "subtitle": "第二段測試台詞，拼接連貫性確認。", "speaker": "B"}]

        out_seg1 = t_path / "proc_seg01.mp4"
        out_seg2 = t_path / "proc_seg02.mp4"

        def synthetic_tts(text: str, out_wav: Path, engine: str = "auto", speaker: str = "", **kwargs) -> str:
            out_wav.parent.mkdir(parents=True, exist_ok=True)
            sample_rate = 16000
            samples = [int(7000 * math.sin(2 * math.pi * 440 * n / sample_rate)) for n in range(sample_rate // 2)]
            with wave.open(str(out_wav), "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(sample_rate)
                wav_file.writeframes(b"".join(struct.pack("<h", sample) for sample in samples))
            return "offline-synthetic-tone"

        with patch(__name__ + ".synthesize_speech", side_effect=synthetic_tts):
            ok1, msg1 = process_single_segment(vid1, out_seg1, lines1, 4.0, audio_mode="tts_replace", tts_engine="sapi")
        if not ok1:
            print(f"❌ 分段 1 處理失敗: {msg1}")
            return False
        print("✅ 成功完成分段 1 離線合成測試音、混音與字幕燒錄")

        with patch(__name__ + ".synthesize_speech", side_effect=synthetic_tts):
            ok2, msg2 = process_single_segment(vid2, out_seg2, lines2, 4.0, audio_mode="tts_replace", tts_engine="sapi")
        if not ok2:
            print(f"❌ 分段 2 處理失敗: {msg2}")
            return False
        print("✅ 成功完成分段 2 離線合成測試音、混音與字幕燒錄")

        # 3. 測試 Concat 拼接
        final_mp4 = t_path / "final_test_ep.mp4"
        ok_concat, msg_cat = concat_videos([out_seg1, out_seg2], final_mp4)
        if not ok_concat:
            print(f"❌ 拼接成片失敗: {msg_cat}")
            return False

        if final_mp4.exists() and final_mp4.stat().st_size > 1000:
            print(f"✅ 成功拼接產出成片: {final_mp4.name} (大小: {final_mp4.stat().st_size} bytes)")
        else:
            print("❌ 拼接成片檔案無效！")
            return False

    print("\n" + "=" * 70)
    print("🎉 【assemble_episode】自檢 100% 通過！全鏈路閉環運作正常！")
    print("=" * 70)
    return True


# ==============================================================================
# CLI 入口
# ==============================================================================

def format_loudness_report(rep: Dict[str, Any]) -> List[str]:
    """交付清單的「響度」段：錨點、整片 I／TP／LRA、逐段 LUFS／TP 與增益、最大段間落差、W49。"""
    if not rep or not rep.get("segments"):
        return []
    fmt = lambda v, nd=2: "—" if v is None else f"{v:.{nd}f}"
    align = rep.get("dialogue_align") or {}
    film = rep.get("film") or {}
    sp = rep.get("spread") or {}
    before = (sp.get("dialogue_before") or {})
    after = (sp.get("dialogue_after") or {})
    out = ["", "## 響度（段層對白錨定＋整片兩遍 loudnorm）", ""]
    if align:
        out.append(f"- **對白錨定**：{'已套用' if align.get('applied', True) else '關閉（--no-dialogue-align，只量測）'}；"
                   f"錨點 `{fmt(align.get('anchor_lufs'))}` LUFS（{align.get('anchor_source') or '無對白段'}），"
                   f"對白段 {align.get('dialogue_segments', 0)} 段，增益上下限 ±{align.get('max_gain_db')} dB")
    ln = rep.get("film_loudnorm") or {}
    if ln:
        out.append(f"- **整片 loudnorm**：兩遍（linear）；第二遍實際模式 `{ln.get('normalization_type') or '?'}`")
    out.append(f"- **成片**：I `{fmt(film.get('I'))}` LUFS／TP `{fmt(film.get('TP'))}` dBTP／LRA `{fmt(film.get('LRA'), 1)}` LU")
    out.append(f"- **段間對白電平落差**（最大－最小）：處理前 `{fmt(before.get('max_minus_min'))}` LU → 成片 "
               f"`{fmt(after.get('max_minus_min'))}` LU（相鄰最大 `{fmt(after.get('max_adjacent'))}` LU；"
               f"門檻 {sp.get('warn_threshold_lu')} LU）")
    for warning in rep.get("warnings", []):
        out.append(f"- ⚠️ {warning}")
    out += ["", "| 段 | 類型 | 對白窗 | 處理前 對白 LUFS | 處理前 整段 LUFS／TP | 增益 dB | 成片 對白 LUFS | 成片 整段 LUFS／TP | 備註 |",
            "|---|---|---|---|---|---|---|---|---|"]
    role_name = {"dialogue": "對白", "ambient": "無台詞", "silent": "無音軌"}
    for r in rep["segments"]:
        note = "、".join(list(r.get("flags") or []) + (["限幅"] if r.get("limit") else []))
        out.append(f"| {r['segment_id']} | {role_name.get(r.get('role'), r.get('role'))} | {r.get('speech_source') or '—'} | "
                   f"{fmt(r.get('before_speech_I'))} | {fmt(r.get('before_I'))}／{fmt(r.get('before_TP'))} | "
                   f"{r.get('gain_db', 0):+.2f} | {fmt(r.get('after_speech_I'))} | "
                   f"{fmt(r.get('after_I'))}／{fmt(r.get('after_TP'))} | {note or '—'} |")
    return out


def _default_episode_label(args: argparse.Namespace) -> str:
    """預設輸出檔名用的集數：segments 的 episode／episode_id → 檔名 epNN → ep01（舊預設）。"""
    if args.segments and args.segments.is_file():
        try:
            raw = json.loads(args.segments.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            raw = None
        if isinstance(raw, dict):
            label = str(raw.get("episode") or raw.get("episode_id") or "").strip()
            if re.fullmatch(r"[A-Za-z0-9_-]+", label):
                return label.lower()
    for source in (args.segments, args.layer2_dir, args.timeline):
        if source is not None:
            match = re.search(r"ep\d+", Path(source).name, re.IGNORECASE)
            if match:
                return match.group(0).lower()
    return "ep01"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="assemble_episode.py — AI 漫劇階段 7 配音分層、字幕燒錄與拼接成片工具"
    )
    parser.add_argument("--segments", type=Path, help="segments-epXX.json 批次分段檔")
    parser.add_argument("--layer2-dir", type=Path, help="包含 layer2-*.json 檔案之目錄")
    parser.add_argument("--timeline", type=Path, help="timeline-epXX.csv 時間線檔案")
    parser.add_argument("--narration", type=Path, help="narration-epXX.md 旁白字幕對照稿")
    parser.add_argument("--videos-dir", type=Path, default=Path("videos"), help="影片片段來源目錄 (預設 videos/)")
    parser.add_argument("--output", type=Path, default=None,
                        help="最終成片輸出路徑（預設 <videos-dir>/final-<集數>.mp4；集數取自 segments 的 episode 或檔名，"
                             "取不到時為 final-ep01.mp4）")
    parser.add_argument("--audio-mode", type=str, default="auto",
                        choices=["auto", "tts_replace", "native_sub", "narration_only"],
                        help="配音模式 (預設 auto 逐段裁決：有可見嘴對白→native_sub 留 H3 口型；"
                             "只有外部化旁白→tts_replace 混外部 TTS；"
                             "tts_replace=強制外部 TTS 覆蓋；native_sub=保留 H3 原生配音；narration_only=只播旁白)")
    parser.add_argument("--tts-engine", type=str, default="auto",
                        choices=["auto", "edge", "sapi", "voicestudio", "fish", "openai_compat"],
                        help="TTS 後端引擎 (預設 auto 依可用性挑選；voicestudio=本機 VoiceStudio/OmniVoice；"
                             "fish=Fish Audio；openai_compat=自帶 API；edge 已於 2026-10-10 起 403 且非商用)")
    parser.add_argument("--tts-config", type=Path, default=None,
                        help="TTS 設定檔路徑 (預設 config/tts.json；含引擎、憑證與音色對映)")
    parser.add_argument("--bg-volume", type=float, default=0.15, help="壓低原生 H3 背景音量 (預設 0.15)")
    parser.add_argument("--target-lufs", type=float, default=-23.0,
                        help="成片整合響度目標 (預設 -23 LUFS，符合 EBU R128 戲劇交付；串流可用 -14)")
    parser.add_argument("--true-peak", type=float, default=-1.5, help="成片 true peak 上限 dBTP (預設 -1.5)")
    parser.add_argument("--lra", type=float, default=11.0, help="成片響度範圍 LRA (預設 11)")
    parser.add_argument("--no-loudnorm", action="store_true", help="整片不做響度正規化（不建議交付）")
    parser.add_argument("--no-dialogue-align", action="store_true",
                        help="關掉段層「以對白為錨」電平對齊（預設開：每段量對白區段響度、固定增益對齊同一錨點，"
                             "無台詞段保持相對電平；關掉後仍量測並列報告）")
    parser.add_argument("--dialogue-anchor", type=float, default=None,
                        help="對白錨點 LUFS（預設＝有對白段人聲響度中位數；整片 loudnorm 之後才定絕對電平）")
    parser.add_argument("--dialogue-max-gain", type=float, default=dialogue_loudness.DEFAULT_MAX_GAIN_DB,
                        help="段層增益上下限 ±dB（預設 12）")
    parser.add_argument("--loudness-spread-warn", type=float, default=dialogue_loudness.DEFAULT_SPREAD_WARN_LU,
                        help="成片段間對白電平落差超過幾 LU 出 W49 警告（預設 6）")
    parser.add_argument("--no-burn-subtitles", action="store_true", help="關閉字幕硬字幕燒錄")
    parser.add_argument("--delivery-report", type=Path, help="輸出階段 7 交付清單 Markdown 檔案")
    parser.add_argument("--manifest", type=Path, help="輸出機器可讀交付 JSON（預設 delivery-<output>.json）")
    parser.add_argument("--self-test", action="store_true", help="執行全鏈路合成短片單元自檢")
    parser.add_argument("--speed-ramps", type=Path, default=None,
                        help="後製變速清單（預設 <videos-dir>/speed-ramps.json，存在就用）：rendered 段改用 "
                             "videos/ramped/<段>.mp4，台詞／旁白／配音時間窗用 time_map 換算")
    parser.add_argument("--no-speed-ramps", action="store_true", help="不套用後製變速，一律用原片")

    args = parser.parse_args()

    if args.narration:
        parser.error("--narration 外部 Markdown 尚未支援；narration_only 僅讀取 segments 中 shots[].narration")

    # TTS 設定（引擎端點、憑證、音色對映）；缺檔時退回內建 edge/sapi 備援
    tts_config: Optional[Dict[str, Any]] = None
    if tts_module is not None:
        try:
            tts_config = tts_module.load_config(args.tts_config)
        except Exception as exc:
            print(f"⚠️ [警告] TTS 設定檔載入失敗，將使用內建備援引擎: {exc}")

    if args.self_test:
        success = run_self_test()
        return 0 if success else 1

    if args.output is None:
        args.output = args.videos_dir / f"final-{_default_episode_label(args)}.mp4"

    # Invalidate any prior success claim before reading or processing this run's inputs.
    # The prior final file remains intact until a fully validated candidate replaces it.
    manifest_file = args.manifest or (args.output.parent / f"delivery-{args.output.stem}.json")
    atomic_write_json(manifest_file, {
        "schema_version": 1,
        "delivery_status": "in_progress",
        "review_status": "pending_review",
        "expected_segments": [],
        "assembled_segments": [],
        "expected_segment_count": 0,
        "assembled_segment_count": 0,
        "final_video": str(args.output.resolve()),
        "final_sha256": None,
        "final_decode_ok": False,
        "final_duration_seconds": None,
        "errors": [],
    })

    # 1. 收集分段與台詞資料
    # 支援 segments.json、timeline.csv 或 layer2-dir
    segments_data: List[Dict[str, Any]] = []
    source_inputs: List[Dict[str, str]] = []
    source_segments_file: Optional[Path] = None
    episode: Optional[str] = None

    if args.segments and args.segments.exists():
        with args.segments.open("r", encoding="utf-8") as f:
            raw = json.load(f)
        segments_data = raw if isinstance(raw, list) else raw.get("segments", [raw])
        source_segments_file = args.segments.resolve()
        source_inputs.append(source_input_record(source_segments_file))
        if isinstance(raw, dict):
            episode = raw.get("episode") or raw.get("episode_id")
        episode_match = re.search(r"ep\d+", args.segments.stem, re.IGNORECASE)
        episode = episode or (episode_match.group(0).lower() if episode_match else None)

    elif args.layer2_dir and args.layer2_dir.exists():
        for lf in sorted(args.layer2_dir.glob("layer2-*.json")):
            with lf.open("r", encoding="utf-8") as f:
                segments_data.append(json.load(f))
            source_inputs.append(source_input_record(lf))

    elif args.timeline and args.timeline.exists():
        # 從 timeline.csv 讀取
        source_inputs.append(source_input_record(args.timeline))
        with args.timeline.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    seg_id = timeline_segment_id(row)
                except ValueError as exc:
                    parser.error(f"{exc}; refusing ambiguous grouping")
                segment = next((item for item in segments_data if item["segment_id"] == seg_id), None)
                if segment is None:
                    segment = {"segment_id": seg_id, "shots": []}
                    segments_data.append(segment)
                segment["shots"].append(row)
            for segment in segments_data:
                segment["seconds"] = sum(float(shot.get("duration", 0) or 0) for shot in segment["shots"])
    else:
        parser.error("請提供 --segments, --layer2-dir, --timeline 或 --self-test！")

    if not episode:
        source_label = args.layer2_dir.name if args.layer2_dir else args.timeline.stem if args.timeline else ""
        episode_match = re.search(r"ep\d+", source_label, re.IGNORECASE)
        episode = episode_match.group(0).lower() if episode_match else None

    print("\n" + "=" * 70)
    print("🎬 AI 漫劇階段 7 組裝與交付工具 (assemble_episode)")
    print("=" * 70)
    print(f"待組裝分段數: {len(segments_data)} 段")
    print(f"配音方案模式: {args.audio_mode} (引擎: {args.tts_engine}, 背景音量: {args.bg_volume})")
    print(f"字幕燒錄狀態: {'開啟 (高對比黑邊白字)' if not args.no_burn_subtitles else '關閉'}")
    print(f"成片輸出目標: {args.output.resolve()}")

    # 2. 逐段處理 (混音 + 燒字幕)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temp_dir = args.output.parent / "temp_assemble"
    temp_dir.mkdir(parents=True, exist_ok=True)
    manifest_file = args.manifest or (args.output.parent / f"delivery-{args.output.stem}.json")
    expected_segments: List[str] = []
    duplicate_segments: List[str] = []
    seen_segment_ids = set()
    for idx, seg in enumerate(segments_data, 1):
        sid = str(seg.get("segment_id") or seg.get("group") or seg.get("id") or f"seg_{idx}")
        expected_segments.append(sid)
        if sid.casefold() in seen_segment_ids:
            duplicate_segments.append(sid)
        seen_segment_ids.add(sid.casefold())
    manifest: Dict[str, Any] = {
        "schema_version": 1,
        "delivery_status": "in_progress",
        "review_status": "pending_review",
        "expected_segments": expected_segments,
        "assembled_segments": [],
        "expected_segment_count": len(expected_segments),
        "assembled_segment_count": 0,
        "final_video": str(args.output.resolve()),
        "final_sha256": None,
        "final_decode_ok": False,
        "final_duration_seconds": None,
        "errors": [],
        "source_inputs": source_inputs,
    }
    if source_segments_file:
        manifest["source_segments_file"] = str(source_segments_file)
        manifest["source_segments_sha256"] = source_inputs[0]["sha256"]
        manifest["episode"] = episode
    atomic_write_json(manifest_file, manifest)
    ramp_spec: Optional[Dict[str, Any]] = None
    ramp_root = args.videos_dir.resolve().parent
    if not args.no_speed_ramps:
        ramp_file = args.speed_ramps or (args.videos_dir / "speed-ramps.json")
        if ramp_file.is_file():
            try:
                import speed_ramps as speed_ramps_mod
                ramp_spec = speed_ramps_mod.load_spec(ramp_file)
                print(f"變速清單: {ramp_file}（rendered 段改用 videos/ramped/，時間窗依 time_map 換算）")
            except Exception as exc:
                print(f"⚠️ [警告] 變速清單讀取失敗，一律用原片: {exc}")
                ramp_spec = None
    processed_videos: List[Path] = []
    segment_audio: List[Dict[str, Any]] = []  # 段層對白錨定用：對白時間窗（剪引子／變速後的段內秒）
    segment_records: List[Dict[str, Any]] = []
    missing_segments: List[str] = []
    mismatched_segments: List[str] = []
    processing_failures: List[Dict[str, str]] = []
    planned_durations: List[float] = []

    for idx, seg in enumerate(segments_data, 1):
        sid = str(seg.get("segment_id") or seg.get("group") or seg.get("id") or f"seg_{idx}")
        try:
            seg_dur = expected_segment_duration(seg)
        except ValueError as exc:
            processing_failures.append({"segment_id": sid, "error": str(exc)})
            continue
        
        # 尋找原始影片
        allowed_stems = {sid.casefold(), f"seg-{sid}".casefold()}
        exact_matches = [p for p in args.videos_dir.glob("*.mp4") if p.stem.casefold() in allowed_stems]
        found_in = exact_matches[0] if len(exact_matches) == 1 else None

        if len(exact_matches) > 1:
            mismatched_segments.append(sid)
            print(f"  ❌ 分段 [{sid}] 對應到多個影片檔，請明確整理檔名")
            continue
        if not found_in or not found_in.exists():
            print(f"  ⚠️ 分段 #{idx:02d} [{sid}] 缺失對應之 MP4 影片檔案！")
            missing_segments.append(sid)
            continue

        # 收集台詞資訊（每鏡主句＋ dialogue_and_audio.extra_lines 同鏡接話，依各自 speech_window）
        try:
            lines_info = collect_dialogue_lines(seg, args.audio_mode)
        except ValueError as exc:
            print(f"     ❌ {exc}")
            processing_failures.append({"segment_id": sid, "error": str(exc)})
            continue
        shots = seg.get("shots", [])

        # 外部化旁白／畫外音：編譯器已把這類台詞移出 H3 的 <d>，改由這裡用外部 TTS 合成
        for entry in (seg.get("external_narration") or []):
            text = str(entry.get("line") or "").strip()
            if not text:
                continue
            st = entry.get("start")
            et = entry.get("end")
            st = float(st) if st is not None else 0.0
            et = float(et) if et is not None else (st + 3.0)
            lines_info.append({
                "start": st, "end": et, "subtitle": text,
                "speaker": entry.get("speaker") or "", "external": True,
            })
        lines_info.sort(key=lambda item: float(item["start"]))  # 字幕依時間排序（主句、接話、外部旁白混排）

        # 後製變速：rendered 段換成 videos/ramped/<段>.mp4，所有時間窗從原片時間換算到變速版時間。
        # 後續段的起點由 concat 自然平移（每段長度改用變速版長度）。
        ramp_info = None
        if ramp_spec is not None:
            import speed_ramps as speed_ramps_mod
            ramp_info = speed_ramps_mod.ramped_source(ramp_root, sid, ramp_spec)
            if ramp_info and ramp_info.get("stale"):
                print(f"  ⚠️ {ramp_info['stale']}；本段用原片")
                ramp_info = None
        if ramp_info:
            tmap = ramp_info["time_map"]
            for item in lines_info:
                item["start"], item["end"] = speed_ramps_mod.map_window(item["start"], item["end"], tmap)
            found_in = ramp_info["path"]
            seg_dur = ramp_info["duration"] or seg_dur
            print(f"  [~] 分段 [{sid}] 用變速版 {ramp_info['rel']}（{ramp_info['delta']:+.3f}s）")

        # 雙人引子（spatial-consistency.md §7）：shots[0].dual_lead_in 的那一鏡在這裡自動剪掉，不用另外後處理
        lead_problems = dual_lead_in.check(seg)
        if lead_problems:
            print(f"     ❌ 雙人引子格式不符：{'；'.join(lead_problems)}")
            processing_failures.append({"segment_id": sid, "error": "雙人引子格式不符：" + "；".join(lead_problems)})
            continue
        lead_in_s = dual_lead_in.lead_in_seconds(seg)
        if lead_in_s and ramp_info:
            lead_in_s = speed_ramps_mod.map_window(0.0, lead_in_s, ramp_info["time_map"])[1]
        if lead_in_s:
            print(f"  [-] 分段 [{sid}] 剪掉雙人引子 {lead_in_s:.2f}s（dual_lead_in）")
        out_seg_v = temp_dir / f"proc_{sid}.mp4"
        planned_durations.append(seg_dur - lead_in_s)
        dialogue_required = any(
            (shot.get("dialogue_and_audio") or {}).get("has_dialogue") is True
            or any(isinstance(ex, dict) and str(ex.get("line_verbatim") or "").strip()
                   for ex in ((shot.get("dialogue_and_audio") or {}).get("extra_lines") or []))
            or any(str(value or "").strip() not in {"", "（無台詞）", "(無台詞)", "無台詞"} for value in (
                (shot.get("dialogue_and_audio") or {}).get("line_verbatim"),
                shot.get("subtitle"), shot.get("narration"), shot.get("line_verbatim"),
            ))
            for shot in shots
        )
        if args.audio_mode == "narration_only":
            dialogue_required = True
            if not lines_info:
                processing_failures.append({"segment_id": sid, "error": "narration_only 需要 inline shots[].narration；本分段沒有旁白"})
                continue

        print(f"  [+] 處理分段 #{idx:02d} [{sid}] (台詞: {len(lines_info)} 句)...")
        # auto 模式逐段裁決：有可見嘴的畫內對白要留 H3 原生語音做口型；
        # 只有外部化旁白的段落，H3 原生軌本來就沒有人聲，直接混外部 TTS 即可。
        segment_audio_mode = args.audio_mode
        if args.audio_mode == "auto":
            has_visible_dialogue = any(not item.get("external") for item in lines_info)
            segment_audio_mode = "native_sub" if has_visible_dialogue or not lines_info else "tts_replace"
        ok, msg = process_single_segment(
            found_in, out_seg_v, lines_info, seg_dur,
            audio_mode=segment_audio_mode,
            tts_engine=args.tts_engine,
            tts_config=tts_config,
            bg_volume=args.bg_volume,
            burn_subtitles=not args.no_burn_subtitles,
            temp_dir=temp_dir,
            audio_required=dialogue_required,
            lead_in_s=lead_in_s,
        )
        if ok and out_seg_v.exists():
            processed_videos.append(out_seg_v)
            out_dur = seg_dur - lead_in_s
            voiced = [item for item in lines_info if str(item.get("subtitle") or "").strip()]
            sources = {str(item.get("window_source") or ("external" if item.get("external") else "shot_window"))
                       for item in voiced}
            segment_audio.append({
                "segment_id": sid,
                "has_dialogue": bool(voiced),
                "windows": dialogue_loudness.clip_windows(
                    [(float(item["start"]), float(item["end"])) for item in voiced], out_dur, offset=lead_in_s),
                "window_source": "speech_window" if sources <= {"speech_window", "external"} else "shot_window",
            })
            segment_records.append({
                "segment_id": sid,
                "source_video_file": str(found_in.resolve()),
                "source_video_sha256": compute_file_sha256(found_in),
                "processed_video_file": str(out_seg_v.resolve()),
                "processed_video_sha256": compute_file_sha256(out_seg_v),
            })
        else:
            print(f"     ❌ 處理失敗: {msg}")
            processing_failures.append({"segment_id": sid, "error": msg})

    if missing_segments or duplicate_segments or mismatched_segments or processing_failures or len(processed_videos) != len(expected_segments):
        errors = []
        if missing_segments:
            errors.append("unproduced segments: " + ", ".join(missing_segments))
        if duplicate_segments:
            errors.append("duplicate segment IDs: " + ", ".join(duplicate_segments))
        if mismatched_segments:
            errors.append("ambiguous video mappings: " + ", ".join(mismatched_segments))
        errors.extend(f"{item['segment_id']}: {item['error']}" for item in processing_failures)
        manifest.update({
            "delivery_status": "failed", "assembled_segments": segment_records,
            "assembled_segment_count": len(segment_records), "errors": errors,
            "unproduced_segments": missing_segments,
            "duplicate_segments": duplicate_segments,
            "mismatched_segments": mismatched_segments,
        })
        atomic_write_json(manifest_file, manifest)
        print("❌ 未處理全部且唯一的預期分段，未建立新交付成片")
        return 1

    # 3. 拼接成片
    if not processed_videos:
        manifest.update({"delivery_status": "failed", "errors": ["沒有可組裝的影片分段"]})
        atomic_write_json(manifest_file, manifest)
        print("❌ 錯誤: 沒有成功處理的任何分段影片，無法拼接成片！")
        return 1

    print(f"\n🔗 開始將 {len(processed_videos)} 個已配音字幕分段無縫拼接為成片...")
    candidate = args.output.with_name(f".{args.output.stem}.{os.getpid()}.candidate{args.output.suffix}")
    candidate.unlink(missing_ok=True)
    loudness_report: Dict[str, Any] = {}
    concat_ok, concat_msg = concat_videos(
        processed_videos, candidate,
        target_lufs=(None if args.no_loudnorm else args.target_lufs),
        true_peak=args.true_peak,
        lra=args.lra,
        segment_audio=segment_audio,
        align_options={
            "apply": not args.no_dialogue_align,
            "anchor_lufs": args.dialogue_anchor,
            "max_gain_db": args.dialogue_max_gain,
            "spread_warn_lu": args.loudness_spread_warn,
        },
        report=loudness_report,
    )

    if not concat_ok:
        candidate.unlink(missing_ok=True)
        manifest.update({"delivery_status": "failed", "assembled_segments": segment_records,
                         "assembled_segment_count": len(segment_records), "errors": [concat_msg]})
        atomic_write_json(manifest_file, manifest)
        print(f"❌ 拼接成片失敗: {concat_msg}")
        return 1

    decode_report = validate_video_decode(candidate)
    expected_duration = sum(planned_durations)
    duration_ok = abs(float(decode_report.get("duration", 0)) - expected_duration) <= 0.5
    count_ok = len(segment_records) == len(expected_segments)
    if not decode_report.get("decode_ok") or not duration_ok or not count_ok:
        candidate.unlink(missing_ok=True)
        errors = []
        if not decode_report.get("decode_ok"):
            errors.append(f"final decode failed: {decode_report.get('error', '')}")
        if not duration_ok:
            errors.append(f"final duration {decode_report.get('duration', 0):.3f}s does not match planned {expected_duration:.3f}s")
        if not count_ok:
            errors.append(f"assembled {len(segment_records)} of {len(expected_segments)} expected segments")
        manifest.update({"delivery_status": "failed", "assembled_segments": segment_records,
                         "assembled_segment_count": len(segment_records), "errors": errors,
                         "final_duration_seconds": decode_report.get("duration")})
        atomic_write_json(manifest_file, manifest)
        print("❌ 成片完整解碼、時長或分段數驗證失敗；保留既有輸出")
        return 1

    candidate.replace(args.output)
    final_hash = compute_file_sha256(args.output)

    size_mb = args.output.stat().st_size / 1048576.0
    print(f"🎉 成片拼接完成！輸出: {args.output.name} ({size_mb:.2f} MB)")

    # 4. 產生交付報表
    report_file = args.delivery_report or (args.output.parent / f"delivery-{args.output.stem}.md")
    report_lines = [
        f"# 漫劇階段 7 成品交付清單",
        f"",
        f"- **輸出成品**：`{args.output.name}` ({size_mb:.2f} MB)",
        f"- **交付時間**：`{time.strftime('%Y-%m-%d %H:%M:%S')}`",
        f"- **配音模式**：`{args.audio_mode}` (TTS 引擎: `{args.tts_engine}`)",
        f"- **字幕燒錄**：`{'是' if not args.no_burn_subtitles else '否'}`",
        f"- **技術狀態**：`complete`；人工審核：`pending_review`",
        f"- **成片 SHA256**：`{final_hash}`",
        f"- **完整解碼**：`{decode_report['decode_ok']}`；時長：`{decode_report['duration']:.3f}s`",
        f"- **已包含分段數**：`{len(processed_videos)}/{len(expected_segments)}` 段",
        f"- **原生音訊處理**：若存在，依音量係數降低整條原生音軌；不代表已分離背景音與原生人聲。",
        f"",
        f"## 分段明細",
        f"",
    ]
    for pv in processed_videos:
        report_lines.append(f"- ✅ `{pv.name.replace('proc_', '')}`")
    report_lines.extend(format_loudness_report(loudness_report))
    for warning in loudness_report.get("warnings", []):
        print(f"⚠️ [WARN] {warning}")
    report_tmp = report_file.with_name(f".{report_file.name}.{os.getpid()}.tmp")
    report_tmp.write_text("\n".join(report_lines), encoding="utf-8")
    report_tmp.replace(report_file)
    manifest.update({
        "delivery_status": "complete", "review_status": "pending_review",
        "assembled_segments": segment_records,
        "assembled_segment_count": len(segment_records),
        "final_video": str(args.output.resolve()), "final_sha256": final_hash,
        "final_decode_ok": bool(decode_report["decode_ok"]),
        "final_duration_seconds": decode_report["duration"],
        "expected_duration_seconds": expected_duration,
        "audio_mode": args.audio_mode,
        "native_audio_handling": "retained_at_bg_volume; native speech is not separated from ambience",
        "loudness": loudness_report,
        "warnings": list(loudness_report.get("warnings", [])),
    })
    atomic_write_json(manifest_file, manifest)
    print(f"📄 交付清單報表已寫入: {report_file.name}")
    print(f"📦 機器可讀交付 manifest 已寫入: {manifest_file.name}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
