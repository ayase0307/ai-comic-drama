# -*- coding: utf-8 -*-
"""組裝收同鏡接話（#120 extra_lines）＋ validate E4 切點下限與編譯器／audit 同一常數。

1. h3d assemble 以前只讀每鏡主句；extra_lines 每句要依自己的 speech_window 一起進字幕／時間軸，
   和 #119 雙人引子（剪片頭、時間前移）相容。
2. validate_storyboard「E4 切點不可行」改用 h3_spec.MIN_SHOT_SEC（1.2 s）擋、SHOT_SOFT_MIN_SEC（2.0 s）只提醒。
"""
import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "storyboard"))

import assemble_episode as assembly  # noqa: E402
import dual_lead_in  # noqa: E402
import h3_spec  # noqa: E402
import validate_storyboard as vs  # noqa: E402


def shot(sid, start, end, ids, line=None, window=None, extra=None, **kw):
    dlg = {"has_dialogue": bool(line), "line_verbatim": line or "", "speaker": ids[0] if line else ""}
    if window:
        dlg["speech_window"] = {"start": window[0], "end": window[1]}
    if extra is not None:
        dlg["extra_lines"] = extra
    return {"shot_id": sid, "start_time": start, "end_time": end, "duration": round(end - start, 4),
            "character_ids": list(ids), "camera_optics": {"shot_size": "medium close-up"},
            "dialogue_and_audio": dlg, **kw}


def reply(text, start, end, speaker="C-shen"):
    return {"speaker": speaker, "line_verbatim": text, "speech_window": {"start": start, "end": end}}


def _probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True)
    return float(out.stdout.strip())


def _make_video(path, duration):
    res = subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                          "-f", "lavfi", "-i", f"color=c=blue:s=160x90:r=24:d={duration}",
                          "-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}",
                          "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path)],
                         capture_output=True)
    if res.returncode:
        raise AssertionError(res.stderr.decode("utf-8", "replace"))


class CollectExtraLines(unittest.TestCase):
    def test_extra_lines_collected_with_own_window_and_speaker(self):
        seg = {"segment_id": "S", "shots": [
            shot("SH01", 0.0, 4.0, ["C-lai", "C-shen"], "受傷了嗎？", (0.3, 1.6),
                 extra=[reply("沒有。", 1.9, 2.6), reply("真的？", 2.9, 3.6, speaker="C-lai")]),
            shot("SH02", 4.0, 6.0, ["C-shen"], "走吧。", (4.3, 5.0)),
        ]}
        lines = assembly.collect_dialogue_lines(seg, "native_sub")
        self.assertEqual([l["subtitle"] for l in lines], ["受傷了嗎？", "沒有。", "真的？", "走吧。"])
        self.assertEqual([(l["start"], l["end"]) for l in lines], [(0.3, 1.6), (1.9, 2.6), (2.9, 3.6), (4.3, 5.0)])
        self.assertEqual([l["speaker"] for l in lines], ["C-lai", "C-shen", "C-lai", "C-shen"])

    def test_no_extra_lines_keeps_old_behaviour(self):
        seg = {"shots": [shot("SH01", 0.0, 3.0, ["C-lai"], "受傷了嗎？", (0.5, 2.0)),
                         shot("SH02", 3.0, 5.0, ["C-shen"], "沒有。")]}
        lines = assembly.collect_dialogue_lines(seg, "native_sub")
        self.assertEqual([(l["subtitle"], l["start"], l["end"]) for l in lines],
                         [("受傷了嗎？", 0.5, 2.0), ("沒有。", 3.0, 5.0)])  # 無 speech_window 退回鏡頭時間

    def test_extra_line_without_window_is_refused(self):
        seg = {"shots": [shot("SH01", 0.0, 4.0, ["C-lai"], "受傷了嗎？", (0.3, 1.6),
                              extra=[{"speaker": "C-shen", "line_verbatim": "沒有。"}])]}
        with self.assertRaises(ValueError) as cm:
            assembly.collect_dialogue_lines(seg, "native_sub")
        self.assertIn("extra_lines[1]", str(cm.exception))

    def test_blank_extra_lines_ignored_and_narration_only_skips_replies(self):
        seg = {"shots": [shot("SH01", 0.0, 4.0, ["C-lai"], "受傷了嗎？", (0.3, 1.6), narration="旁白",
                              extra=[{"line_verbatim": "  "}, "bad", reply("沒有。", 1.9, 2.6)])]}
        self.assertEqual(len(assembly.collect_dialogue_lines(seg, "native_sub")), 2)
        only = assembly.collect_dialogue_lines(seg, "narration_only")
        self.assertEqual([l["subtitle"] for l in only], ["旁白"])


class ExtraLinesWithDualLeadIn(unittest.TestCase):
    SEG = {"segment_id": "EP01-S02", "metadata": {"frames": 107}, "shots": [
        shot("SH01", 0.0, 2.0, ["C-shen", "C-lai"], dual_lead_in=True),
        shot("SH02", 2.0, 107 / 24, ["C-lai", "C-shen"], "受傷了嗎", (2.2, 2.9), extra=[reply("沒有", 3.1, 3.8)]),
    ]}

    def test_extra_line_subtitle_shifted_after_lead_in_trim(self):
        self.assertEqual(dual_lead_in.check(self.SEG), [])
        lines = assembly.collect_dialogue_lines(self.SEG, "native_sub")
        with tempfile.TemporaryDirectory(dir=ROOT) as td:
            root = Path(td)
            src, out = root / "SEG.mp4", root / "proc.mp4"
            _make_video(src, 107 / 24)
            ok, msg = assembly.process_single_segment(src, out, lines, 107 / 24, audio_mode="native_sub",
                                                      temp_dir=root / "tmp", lead_in_s=2.0)
            self.assertTrue(ok, msg)
            srt = (root / "tmp" / "SEG.srt").read_text(encoding="utf-8")
        self.assertIn("00:00:00,200 --> 00:00:00,900\n受傷了嗎", srt)
        self.assertIn("00:00:01,100 --> 00:00:01,800\n沒有", srt)

    def test_extra_line_inside_lead_in_still_blocked(self):
        seg = json.loads(json.dumps(self.SEG, ensure_ascii=False))
        seg["shots"][1]["dialogue_and_audio"]["extra_lines"][0]["speech_window"] = {"start": 1.5, "end": 1.9}
        self.assertTrue(dual_lead_in.check(seg))  # W48／assemble 擋
        lines = assembly.collect_dialogue_lines(seg, "native_sub")
        with tempfile.TemporaryDirectory(dir=ROOT) as td:
            root = Path(td)
            src = root / "SEG.mp4"
            _make_video(src, 107 / 24)
            ok, msg = assembly.process_single_segment(src, root / "proc.mp4", lines, 107 / 24,
                                                      audio_mode="native_sub", temp_dir=root / "tmp", lead_in_s=2.0)
        self.assertFalse(ok)
        self.assertIn("雙人引子", msg)

    def test_main_assemble_burns_extra_line(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as td:
            root = Path(td)
            videos = root / "videos"
            videos.mkdir()
            _make_video(videos / "EP01-S02.mp4", 107 / 24)
            segments = root / "segments-ep01.json"
            segments.write_text(json.dumps({"episode": "ep01", "segments": [self.SEG]}, ensure_ascii=False),
                                encoding="utf-8")
            output = root / "final.mp4"
            captured = []
            real = assembly.process_single_segment

            def spy(*a, **kw):
                captured.append([dict(x) for x in a[2]])
                return real(*a, **kw)

            with mock.patch.object(sys, "argv", [
                "assemble_episode.py", "--segments", str(segments), "--videos-dir", str(videos),
                "--output", str(output), "--audio-mode", "native_sub",
            ]), mock.patch.object(assembly, "process_single_segment", side_effect=spy), \
                    contextlib.redirect_stdout(io.StringIO()):
                code = assembly.main()
            manifest = json.loads((root / "delivery-final.json").read_text(encoding="utf-8"))
            final = _probe(output) if output.exists() else None
        self.assertEqual(code, 0, manifest)
        self.assertAlmostEqual(final, 107 / 24 - 2.0, delta=0.1)
        self.assertEqual([l["subtitle"] for l in captured[0]], ["受傷了嗎", "沒有"])

    def test_main_assemble_fails_segment_when_reply_has_no_window(self):
        seg = json.loads(json.dumps(self.SEG, ensure_ascii=False))
        seg["shots"][1]["dialogue_and_audio"]["extra_lines"][0].pop("speech_window")
        with tempfile.TemporaryDirectory(dir=ROOT) as td:
            root = Path(td)
            videos = root / "videos"
            videos.mkdir()
            _make_video(videos / "EP01-S02.mp4", 107 / 24)
            segments = root / "segments-ep01.json"
            segments.write_text(json.dumps({"episode": "ep01", "segments": [seg]}, ensure_ascii=False), encoding="utf-8")
            with mock.patch.object(sys, "argv", [
                "assemble_episode.py", "--segments", str(segments), "--videos-dir", str(videos),
                "--output", str(root / "final.mp4"), "--audio-mode", "native_sub", "--no-burn-subtitles",
            ]), contextlib.redirect_stdout(io.StringIO()):
                code = assembly.main()
            manifest = json.loads((root / "delivery-final.json").read_text(encoding="utf-8"))
        self.assertNotEqual(code, 0)
        self.assertTrue(any("speech_window" in e for e in manifest["errors"]), manifest["errors"])


def _l2(start, end):
    return {"shot_id": f"SH{int(start * 10):03d}", "start_time": start, "end_time": end,
            "duration": round(end - start, 4), "character_ids": ["C-A"], "camera_optics": {"shot_size": "MCU"},
            "dialogue_and_audio": {"has_dialogue": False, "line_verbatim": "", "lips_closed_lock": True}}


def _data(n, target):
    step = target / n
    shots = [_l2(round(i * step, 4), round((i + 1) * step, 4)) for i in range(n)]
    shots[-1]["end_time"] = target
    shots[-1]["duration"] = round(target - shots[-1]["start_time"], 4)
    return {"segment_id": "T", "metadata": {"lighting_lock_line": "x", "aspect_ratio": "16:9",
                                            "target_duration_sec": target}, "shots": shots}


class ValidateE4UsesSharedMinimum(unittest.TestCase):
    def test_constants_shared_with_compiler_and_audit(self):
        self.assertEqual(h3_spec.MIN_SHOT_SEC, 1.2)
        self.assertEqual(h3_spec.SHOT_SOFT_MIN_SEC, 2.0)
        self.assertIs(vs.h3_spec, h3_spec)

    def test_between_1_2_and_2_seconds_per_shot_is_warning_only(self):
        res = vs.validate_storyboard_data(_data(4, 6.0))  # 取整 5.875 s / 4 鏡 ≈ 1.47 s
        self.assertFalse([e for e in res["errors"] if "E4" in e], res["errors"])
        self.assertTrue([w for w in res["warnings"] if "W:E4 短鏡" in w], res["warnings"])

    def test_below_1_2_seconds_per_shot_is_error(self):
        res = vs.validate_storyboard_data(_data(4, 4.5))  # 取整 4.458 s < 4×1.2
        self.assertTrue([e for e in res["errors"] if "E4 切點不可行" in e and ">= 1.2s" in e], res["errors"])

    def test_two_seconds_per_shot_has_no_e4_finding(self):
        res = vs.validate_storyboard_data(_data(4, 9.0))  # 取整 8.708 s
        self.assertFalse([e for e in res["errors"] if "E4" in e])
        self.assertFalse([w for w in res["warnings"] if "E4" in w])


class FrameRoundingFloatTolerance(unittest.TestCase):
    """SB-2：4.4583 s（=107 幀手寫秒數）×24=106.9992，以前 floor 成 90 幀、E4 誤報切點不可行。"""

    def test_frames_for_snaps_near_integer_frames(self):
        self.assertEqual(h3_spec.frames_for(4.4583), 107)
        self.assertEqual(h3_spec.frames_for(4.4583, rounding="ceil"), 107)
        self.assertEqual(h3_spec.frames_for(4.4584, rounding="ceil"), 107)  # 107.0016 不跳到 124
        self.assertEqual(h3_spec.frames_for(107 / 24), 107)
        # 非邊界值照舊
        self.assertEqual(h3_spec.frames_for(7.0), 158)
        self.assertEqual(h3_spec.frames_for(7.0, rounding="ceil"), 175)
        self.assertEqual(h3_spec.frames_for(4.4), 90)  # 105.6 幀，真的不到 107

    def test_effective_duration_and_validate_e4_on_4_4583(self):
        import audit_refs_and_segments as audit
        self.assertAlmostEqual(audit.effective_duration(4.4583), 107 / 24)
        res = vs.validate_storyboard_data(_data(3, 4.4583))  # 3 鏡 × 1.2 = 3.6 ≤ 4.458
        self.assertFalse([e for e in res["errors"] if "E4" in e], res["errors"])

    def test_validate_e4_prefers_metadata_frames(self):
        data = _data(4, 4.4)  # 秒數換算 90 幀 3.75 s < 4×1.2 → 擋
        self.assertTrue([e for e in vs.validate_storyboard_data(data)["errors"] if "E4 切點不可行" in e])
        data["metadata"]["frames"] = 124  # 5.167 s：以實際送件幀數為準
        self.assertFalse([e for e in vs.validate_storyboard_data(data)["errors"] if "E4" in e])


if __name__ == "__main__":
    unittest.main()
