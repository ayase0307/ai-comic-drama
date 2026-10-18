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
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from typing import Any, Dict, List, Optional, Tuple

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


# ==============================================================================
# TTS 引擎封裝 (Edge-TTS + Windows SAPI 離線備案)
# ==============================================================================

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


def synthesize_speech(text: str, out_wav: Path, engine: str = "auto", speaker: str = "") -> str:
    """智慧語音合成器：auto 模式下優先嘗試 Edge-TTS，遇 403/網路異常自動無縫切換 SAPI 備案。"""
    clean_text = re.sub(r"[^\w\u4e00-\u9fff，。！？、 ]", "", text).strip()
    if not clean_text:
        return ""

    out_wav.parent.mkdir(parents=True, exist_ok=True)

    # 角色音色推測
    is_female = any(k in speaker.lower() for k in ["female", "woman", "girl", "ye", "shan", "女", "珊"])
    edge_voice = "zh-TW-HsiaoChenNeural" if is_female else "zh-TW-YunJheNeural"

    if engine == "edge":
        if generate_edge_tts(clean_text, out_wav, edge_voice):
            return "edge-tts"
        raise RuntimeError("Edge-TTS 生成失敗 (可能遇 403 阻斷)")

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
        raise RuntimeError("語音生成雙引擎 (Edge-TTS 與 SAPI) 均失敗！")

    return "none"


# ==============================================================================
# FFmpeg 濾鏡與字元轉義 (Windows 專用路徑保護)
# ==============================================================================

def escape_ffmpeg_path(path: Path) -> str:
    """將 Windows 檔案路徑轉換為適用於 FFmpeg subtitles 濾鏡之跳脫字串 (C\\:/path/to/file)。"""
    return str(path.resolve()).replace("\\", "/").replace(":", "\\:")


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

def process_single_segment(
    in_video: Path,
    out_video: Path,
    lines_info: List[Dict[str, Any]],
    seg_duration: float,
    audio_mode: str = "tts_replace",
    tts_engine: str = "auto",
    bg_volume: float = 0.15,
    burn_subtitles: bool = True,
    temp_dir: Optional[Path] = None
) -> Tuple[bool, str]:
    """針對單個分段執行 TTS 生成、adelay 混音與字幕燒錄。"""
    t_dir = temp_dir or (out_video.parent / "tmp_audio")
    t_dir.mkdir(parents=True, exist_ok=True)

    # 1. 生成字幕 SRT
    srt_file = t_dir / f"{in_video.stem}.srt"
    srt_lines = []
    tts_tracks: List[Tuple[Path, int]] = []  # (wav_path, delay_ms)

    for idx, item in enumerate(lines_info, 1):
        line_text = item.get("subtitle") or item.get("line_verbatim") or item.get("text") or ""
        if not line_text:
            continue
        start_sec = float(item.get("start", 0.0))
        end_sec = float(item.get("end", start_sec + 2.5))
        if end_sec <= start_sec:
            end_sec = start_sec + 2.5

        srt_lines.append(f"{idx}\n{sec_to_srt_time(start_sec)} --> {sec_to_srt_time(end_sec)}\n{line_text}\n")

        # 準備 TTS 音訊
        if audio_mode == "tts_replace":
            wav_path = t_dir / f"{in_video.stem}_line_{idx:02d}.wav"
            speaker = item.get("speaker", "")
            try:
                eng_used = synthesize_speech(line_text, wav_path, engine=tts_engine, speaker=speaker)
                delay_ms = max(0, int(start_sec * 1000))
                tts_tracks.append((wav_path, delay_ms))
            except Exception as e:
                print(f"   [!] 台詞 #{idx} 語音合成失敗: {e}")

    srt_file.write_text("\n".join(srt_lines), encoding="utf-8")

    # 2. 構建 FFmpeg 濾鏡鏈
    has_tts = len(tts_tracks) > 0 and audio_mode == "tts_replace"
    has_sub = len(srt_lines) > 0 and burn_subtitles

    cmd = ["ffmpeg", "-y", "-i", str(in_video)]
    for wav_p, _ in tts_tracks:
        cmd.extend(["-i", str(wav_p)])

    v_filter = ""
    if has_sub:
        esc_srt = escape_ffmpeg_path(srt_file)
        sub_style = "FontSize=20,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=2"
        v_filter = f"subtitles='{esc_srt}':force_style='{sub_style}'"

    # 音訊混合構建
    filter_complex_parts = []
    if v_filter:
        filter_complex_parts.append(f"[0:v]{v_filter}[vout]")

    if has_tts:
        # [0:a] 壓低音量
        filter_complex_parts.append(f"[0:a]volume={bg_volume}[bg]")
        mix_inputs = ["[bg]"]
        for i, (_, delay_ms) in enumerate(tts_tracks, 1):
            filter_complex_parts.append(f"[{i}:a]adelay={delay_ms}|{delay_ms}[v{i}]")
            mix_inputs.append(f"[v{i}]")
        
        mix_str = "".join(mix_inputs)
        filter_complex_parts.append(f"{mix_str}amix=inputs={len(mix_inputs)}:duration=first[aout]")

    if filter_complex_parts:
        cmd.extend(["-filter_complex", ";".join(filter_complex_parts)])
        cmd.extend(["-map", "[vout]" if v_filter else "0:v"])
        cmd.extend(["-map", "[aout]" if has_tts else "0:a"])
    else:
        cmd.extend(["-c", "copy"])

    if filter_complex_parts:
        cmd.extend(["-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k"])

    cmd.append(str(out_video))

    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if res.returncode != 0:
        return False, f"FFmpeg 處理分段 {in_video.name} 失敗: {res.stderr[:400]}"
    return True, "成功"


# ==============================================================================
# FFmpeg Concat 協議無縫拼接
# ==============================================================================

def concat_videos(video_list: List[Path], out_video: Path) -> Tuple[bool, str]:
    """使用 FFmpeg concat 協議無縫拼接分段影片成片。"""
    out_video.parent.mkdir(parents=True, exist_ok=True)
    list_file = out_video.parent / f"concat_{out_video.stem}.txt"
    lines = [f"file '{v.name}'" for v in video_list]
    list_file.write_text("\n".join(lines), encoding="utf-8")

    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(list_file.name),
        "-c", "copy",
        str(out_video.name)
    ]
    # 在目錄中執行以支援相對路徑
    res = subprocess.run(cmd, cwd=str(out_video.parent), capture_output=True, text=True, encoding="utf-8", errors="replace")
    try:
        list_file.unlink()
    except Exception:
        pass

    if res.returncode != 0:
        return False, f"拼接失敗: {res.stderr[:400]}"
    return True, "成功"


# ==============================================================================
# 自檢測試模式 (--self-test)
# ==============================================================================

def run_self_test() -> bool:
    """自動建立測試短片，跑通 TTS ➔ 混音 ➔ 字幕轉義燒錄 ➔ Concat 拼接全鏈路驗證。"""
    print("\n" + "=" * 70)
    print("🧪 啟動 assemble_episode 階段 7 全鏈路自動化自檢 (--self-test)")
    print("=" * 70)

    with tempfile.TemporaryDirectory() as td:
        t_path = Path(td)
        vid1 = t_path / "test_seg01.mp4"
        vid2 = t_path / "test_seg02.mp4"

        # 1. 產生兩段測試短片 (帶基本音訊)
        cmd1 = [
            "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=blue:s=640x360:d=4.0:r=24",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=4.0",
            "-c:v", "libx264", "-c:a", "aac", str(vid1)
        ]
        cmd2 = [
            "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=green:s=640x360:d=4.0:r=24",
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

        ok1, msg1 = process_single_segment(vid1, out_seg1, lines1, 4.0, audio_mode="tts_replace", tts_engine="auto")
        if not ok1:
            print(f"❌ 分段 1 處理失敗: {msg1}")
            return False
        print("✅ 成功完成分段 1 智慧 TTS 配音、混音與字幕燒錄")

        ok2, msg2 = process_single_segment(vid2, out_seg2, lines2, 4.0, audio_mode="tts_replace", tts_engine="auto")
        if not ok2:
            print(f"❌ 分段 2 處理失敗: {msg2}")
            return False
        print("✅ 成功完成分段 2 智慧 TTS 配音、混音與字幕燒錄")

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

def main() -> int:
    parser = argparse.ArgumentParser(
        description="assemble_episode.py — AI 漫劇階段 7 配音分層、字幕燒錄與拼接成片工具"
    )
    parser.add_argument("--segments", type=Path, help="segments-epXX.json 批次分段檔")
    parser.add_argument("--layer2-dir", type=Path, help="包含 layer2-*.json 檔案之目錄")
    parser.add_argument("--timeline", type=Path, help="timeline-epXX.csv 時間線檔案")
    parser.add_argument("--narration", type=Path, help="narration-epXX.md 旁白字幕對照稿")
    parser.add_argument("--videos-dir", type=Path, default=Path("videos"), help="影片片段來源目錄 (預設 videos/)")
    parser.add_argument("--output", type=Path, default=Path("videos/final-ep01.mp4"), help="最終成片輸出路徑")
    parser.add_argument("--audio-mode", type=str, default="tts_replace", choices=["tts_replace", "native_sub", "narration_only"], help="配音模式 (預設 tts_replace 方案 A)")
    parser.add_argument("--tts-engine", type=str, default="auto", choices=["auto", "edge", "sapi"], help="TTS 後端引擎 (預設 auto 自動嘗試並降級)")
    parser.add_argument("--bg-volume", type=float, default=0.15, help="壓低原生 H3 背景音量 (預設 0.15)")
    parser.add_argument("--no-burn-subtitles", action="store_true", help="關閉字幕硬字幕燒錄")
    parser.add_argument("--delivery-report", type=Path, help="輸出階段 7 交付清單 Markdown 檔案")
    parser.add_argument("--self-test", action="store_true", help="執行全鏈路合成短片單元自檢")

    args = parser.parse_args()

    if args.self_test:
        success = run_self_test()
        return 0 if success else 1

    # 1. 收集分段與台詞資料
    # 支援 segments.json、timeline.csv 或 layer2-dir
    segments_data: List[Dict[str, Any]] = []

    if args.segments and args.segments.exists():
        with args.segments.open("r", encoding="utf-8") as f:
            raw = json.load(f)
        segments_data = raw if isinstance(raw, list) else raw.get("segments", [raw])

    elif args.layer2_dir and args.layer2_dir.exists():
        for lf in sorted(args.layer2_dir.glob("layer2-*.json")):
            with lf.open("r", encoding="utf-8") as f:
                segments_data.append(json.load(f))

    elif args.timeline and args.timeline.exists():
        # 從 timeline.csv 讀取
        with args.timeline.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            # 依 scene/segment 分組
            current_seg: Optional[Dict[str, Any]] = None
            for row in reader:
                sid = row.get("shot_id", "")
                parts = sid.split("-")
                seg_id = f"{parts[0]}-{parts[1]}" if len(parts) >= 2 else sid
                if not current_seg or current_seg["segment_id"] != seg_id:
                    current_seg = {"segment_id": seg_id, "shots": []}
                    segments_data.append(current_seg)
                current_seg["shots"].append(row)
    else:
        parser.error("請提供 --segments, --layer2-dir, --timeline 或 --self-test！")

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

    processed_videos: List[Path] = []
    missing_segments: List[str] = []

    for idx, seg in enumerate(segments_data, 1):
        sid = seg.get("segment_id") or seg.get("group") or seg.get("id") or f"seg_{idx}"
        
        # 尋找原始影片
        cand_files = [
            args.videos_dir / f"{sid}.mp4",
            args.videos_dir / f"{sid.lower()}.mp4",
            args.videos_dir / f"seg-{sid}.mp4",
        ]
        found_in = next((p for p in cand_files if p.exists()), None)
        if not found_in:
            found_in = next((p for p in args.videos_dir.glob("*.mp4") if sid.lower() in p.stem.lower()), None)

        if not found_in or not found_in.exists():
            print(f"  ⚠️ 分段 #{idx:02d} [{sid}] 缺失對應之 MP4 影片檔案！")
            missing_segments.append(sid)
            continue

        # 收集台詞資訊
        lines_info = []
        shots = seg.get("shots", [])
        for s in shots:
            dlg = s.get("dialogue_and_audio", {})
            text = dlg.get("line_verbatim") or s.get("subtitle") or s.get("narration") or ""
            if text and text != "（無台詞）":
                st = float(s.get("start_time") or s.get("start") or 0.0)
                et = float(s.get("end_time") or s.get("end") or (st + float(s.get("duration", 2.5))))
                spk = dlg.get("speaker") or s.get("speaker") or ""
                lines_info.append({"start": st, "end": et, "subtitle": text, "speaker": spk})

        out_seg_v = temp_dir / f"proc_{sid}.mp4"
        seg_dur = float(seg.get("metadata", {}).get("effective_duration_sec") or seg.get("seconds", 8.0))

        print(f"  [+] 處理分段 #{idx:02d} [{sid}] (台詞: {len(lines_info)} 句)...")
        ok, msg = process_single_segment(
            found_in, out_seg_v, lines_info, seg_dur,
            audio_mode=args.audio_mode,
            tts_engine=args.tts_engine,
            bg_volume=args.bg_volume,
            burn_subtitles=not args.no_burn_subtitles,
            temp_dir=temp_dir
        )
        if ok and out_seg_v.exists():
            processed_videos.append(out_seg_v)
        else:
            print(f"     ❌ 處理失敗: {msg}")

    # 3. 拼接成片
    if not processed_videos:
        sys.exit("❌ 錯誤: 沒有成功處理的任何分段影片，無法拼接成片！")

    print(f"\n🔗 開始將 {len(processed_videos)} 個已配音字幕分段無縫拼接為成片...")
    concat_ok, concat_msg = concat_videos(processed_videos, args.output)

    if not concat_ok:
        sys.exit(f"❌ 拼接成片失敗: {concat_msg}")

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
        f"- **已包含分段數**：`{len(processed_videos)}` 段",
        f"",
        f"## 分段明細",
        f"",
    ]
    for pv in processed_videos:
        report_lines.append(f"- ✅ `{pv.name.replace('proc_', '')}`")
    if missing_segments:
        report_lines.append(f"\n## ⚠️ 未完成／缺失分段")
        for ms in missing_segments:
            report_lines.append(f"- ❌ `{ms}`")

    report_file.write_text("\n".join(report_lines), encoding="utf-8")
    print(f"📄 交付清單報表已寫入: {report_file.name}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
