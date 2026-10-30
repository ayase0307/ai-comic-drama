"""段層「以對白為錨」電平對齊＋整片兩遍 loudnorm（scripts/storyboard/dialogue_loudness.py、assemble_episode.concat_videos）。

背景：《噩盡島》EP01 重跑 30 支 H3 clip 原生音 integrated −9.94～−28.71 LUFS，整片單遍 loudnorm
之後段間仍差 13.53 LU。這裡用合成音（不同電平的「對白」音 burst＋一段無台詞環境音）驗：
增益對齊、無台詞段相對電平保留、時長不漂移、兩遍 loudnorm 落點與 48 kHz、W49 警告。"""
import json
import math
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.storyboard import assemble_episode as assembly
from scripts.storyboard import dialogue_loudness as dl

ROOT = Path(__file__).resolve().parents[1]


def _make_clip(path: Path, duration: float, audio_expr: str) -> None:
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
           "-f", "lavfi", "-i", f"color=c=gray:s=160x90:r=24:d={duration}",
           "-f", "lavfi", "-i", f"aevalsrc='{audio_expr}':s=48000:c=stereo:d={duration}",
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest", str(path)]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode:
        raise AssertionError(res.stderr)


def _speech(amp: float, start: float, end: float) -> str:
    # 「對白」：300 Hz＋900 Hz、4 Hz 包絡起伏的音，只在 [start, end] 出聲
    return (f"{amp}*(0.7*sin(2*PI*300*t)+0.3*sin(2*PI*900*t))*(0.6+0.4*sin(2*PI*4*t))*between(t\\,{start}\\,{end})")


def _probe(path: Path, entries: str, stream: str):
    out = subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", stream, "-show_entries",
                                   entries, "-of", "json", str(path)], text=True)
    return json.loads(out)["streams"][0]


class PlanGainsTests(unittest.TestCase):
    """純計算：錨點中位數、上下限、無台詞段 0 dB／上限、TP 保護。"""

    @staticmethod
    def _rec(role, speech_i=None, whole_i=-20.0, tp=-6.0):
        rec = {"role": role, "whole": {"I": whole_i, "TP": tp}}
        rec["speech"] = {"I": speech_i} if speech_i is not None else None
        return rec

    def test_anchor_is_median_and_gains_align_dialogue(self):
        recs = [self._rec("dialogue", -10.0, tp=-12.0), self._rec("dialogue", -18.0), self._rec("dialogue", -26.0, tp=-20.0)]
        summary = dl.plan_gains(recs)
        self.assertEqual(summary["anchor_lufs"], -18.0)
        self.assertEqual([r["gain_db"] for r in recs], [-8.0, 0.0, 8.0])
        self.assertTrue(all(not r["limit"] for r in recs))

    def test_gain_is_clamped(self):
        recs = [self._rec("dialogue", -5.0, tp=-30), self._rec("dialogue", -20.0, tp=-30), self._rec("dialogue", -40.0, tp=-40)]
        dl.plan_gains(recs, max_gain_db=12.0)
        self.assertEqual(recs[0]["gain_db"], -12.0)
        self.assertIn("clamped_cut", recs[0]["flags"])
        self.assertEqual(recs[2]["gain_db"], 12.0)
        self.assertIn("clamped_boost", recs[2]["flags"])

    def test_ambient_keeps_relative_level_unless_far_louder(self):
        recs = [self._rec("dialogue", -18.0), self._rec("ambient", whole_i=-30.0), self._rec("ambient", whole_i=-4.0, tp=-12.0)]
        dl.plan_gains(recs, ambient_ceiling_lu=6.0)
        self.assertEqual(recs[1]["gain_db"], 0.0)          # 安靜的無台詞段不拉上來
        self.assertEqual(recs[2]["gain_db"], -8.0)         # 比錨點響 14 LU → 壓到錨點＋6
        self.assertIn("ambient_ceiling", recs[2]["flags"])

    def test_true_peak_protection(self):
        recs = [self._rec("dialogue", -18.0, tp=-2.0), self._rec("dialogue", -30.0, tp=-3.0)]
        dl.plan_gains(recs, anchor_lufs=-18.0, tp_ceiling=-1.0, limiter_headroom_db=6.0)
        # +12 dB 會把 TP 推到 +9 → 收到 TP −1＋6＝+5（增益 +8），並過限幅器
        self.assertEqual(recs[1]["gain_db"], 8.0)
        self.assertIn("tp_capped", recs[1]["flags"])
        self.assertTrue(recs[1]["limit"])
        self.assertIn("alimiter", dl.gain_filter(8.0, True))
        self.assertEqual(dl.gain_filter(0.0, False), "")

    def test_segment_tp_ceiling_tracks_film_gain_with_floor(self):
        self.assertEqual(dl.segment_tp_ceiling(-17.5, -23.0, -1.5), -1.0)   # 整片要降 → 用預設 −1
        self.assertAlmostEqual(dl.segment_tp_ceiling(-17.5, -16.0, -1.5), -3.5)  # 整片要拉 1.5 → 先壓到 −3.5
        self.assertEqual(dl.segment_tp_ceiling(-30.0, -16.0, -1.5), dl.SEGMENT_TP_FLOOR_DBTP)
        self.assertEqual(dl.segment_tp_ceiling(None, -16.0, -1.5), -1.0)
        self.assertEqual(dl.segment_tp_ceiling(-17.5, None, -1.5), -1.0)

    def test_no_dialogue_segments_means_no_gain(self):
        recs = [self._rec("ambient", whole_i=-20.0), self._rec("ambient", whole_i=-35.0)]
        summary = dl.plan_gains(recs)
        self.assertIsNone(summary["anchor_lufs"])
        self.assertEqual([r["gain_db"] for r in recs], [0.0, 0.0])

    def test_clip_windows_offset_merge(self):
        self.assertEqual(dl.clip_windows([(2.5, 3.0), (2.15, 2.6), (9.0, 12.0), (1.0, 2.01)], 8.0, offset=2.0),
                         [(0.15, 1.0), (7.0, 8.0)])
        self.assertEqual(dl.spread([-10.0, -20.0, -12.0]), {"max_minus_min": 10.0, "max_adjacent": 10.0})

    def test_collect_dialogue_lines_marks_window_source(self):
        seg = {"shots": [
            {"start_time": 0, "end_time": 2, "dialogue_and_audio": {"line_verbatim": "甲", "speech_window": {"start": 0.2, "end": 1.5}}},
            {"start_time": 2, "end_time": 4, "dialogue_and_audio": {"line_verbatim": "乙"}},
        ]}
        lines = assembly.collect_dialogue_lines(seg, "native_sub")
        self.assertEqual([l["window_source"] for l in lines], ["speech_window", "shot_window"])


class ConcatDialogueAlignTests(unittest.TestCase):
    """真的跑 ffmpeg：三段（響對白、小聲對白、無台詞環境音）串接。"""

    @classmethod
    def setUpClass(cls):
        (ROOT / "tmp").mkdir(exist_ok=True)
        cls._td = tempfile.TemporaryDirectory(dir=ROOT / "tmp")
        d = Path(cls._td.name)
        cls.loud = d / "A_loud.mp4"        # 對白 ≈ −10 LUFS
        cls.quiet = d / "B_quiet.mp4"      # 對白 ≈ −22.5 LUFS（要 +11.4 dB，在 ±12 上限內）
        cls.amb = d / "C_amb.mp4"          # 無台詞，低沉環境音
        cls.loud2 = d / "D_loud.mp4"
        _make_clip(cls.loud, 3.0, _speech(0.75, 0.5, 2.5))
        _make_clip(cls.quiet, 3.0, _speech(0.16, 0.5, 2.5))
        _make_clip(cls.amb, 3.0, "0.03*sin(2*PI*120*t)*(0.7+0.3*sin(2*PI*0.5*t))")
        _make_clip(cls.loud2, 3.0, _speech(0.6, 0.5, 2.5))
        cls.videos = [cls.loud, cls.quiet, cls.amb, cls.loud2]
        win = [(0.5, 2.5)]
        cls.audio = [
            {"segment_id": "A", "has_dialogue": True, "windows": win, "window_source": "speech_window"},
            {"segment_id": "B", "has_dialogue": True, "windows": win, "window_source": "speech_window"},
            {"segment_id": "C", "has_dialogue": False, "windows": [], "window_source": "shot_window"},
            {"segment_id": "D", "has_dialogue": True, "windows": win, "window_source": "speech_window"},
        ]
        cls.dir = d

    @classmethod
    def tearDownClass(cls):
        cls._td.cleanup()

    def _concat(self, name, apply=True, target=-23.0):
        out = self.dir / name
        report = {}
        ok, msg = assembly.concat_videos(self.videos, out, target_lufs=target, segment_audio=self.audio,
                                         align_options={"apply": apply}, report=report)
        self.assertTrue(ok, msg)
        return out, report

    def test_aligned_dialogue_preserves_ambient_and_duration(self):
        out, rep = self._concat("aligned.mp4")
        seg = {r["segment_id"]: r for r in rep["segments"]}
        before = rep["spread"]["dialogue_before"]["max_minus_min"]
        after = rep["spread"]["dialogue_after"]["max_minus_min"]
        self.assertGreater(before, 10.0)
        self.assertLess(after, 1.5, rep["segments"])
        self.assertEqual(rep.get("warnings", []), [])
        # 無台詞段：增益 0，與錨點的相對距離保留（±1 LU），沒被拉到對白電平
        self.assertEqual(seg["C"]["gain_db"], 0.0)
        anchor = rep["dialogue_align"]["anchor_lufs"]
        rel_before = seg["C"]["before_I"] - anchor
        rel_after = seg["C"]["after_I"] - seg["D"]["after_speech_I"]
        self.assertLess(rel_before, -8.0)
        self.assertAlmostEqual(rel_after, rel_before, delta=1.0)
        # 兩遍 loudnorm 落點、48 kHz
        self.assertAlmostEqual(rep["film"]["I"], -23.0, delta=1.0)
        self.assertLessEqual(rep["film"]["TP"], -1.5)
        a = _probe(out, "stream=sample_rate,duration", "a:0")
        v = _probe(out, "stream=duration", "v:0")
        self.assertEqual(a["sample_rate"], "48000")
        # 時長不漂移：音軌與影像同長（< 1 個 AAC frame＋容差），總長＝各段相加
        self.assertAlmostEqual(float(a["duration"]), float(v["duration"]), delta=0.05)
        self.assertAlmostEqual(float(v["duration"]), 12.0, delta=0.05)

    def test_disabled_align_reports_w49(self):
        _, rep = self._concat("unaligned.mp4", apply=False)
        self.assertFalse(rep["dialogue_align"]["applied"])
        self.assertTrue(all(r["gain_db"] == 0.0 for r in rep["segments"]))
        self.assertGreater(rep["spread"]["dialogue_after"]["max_minus_min"], 10.0)
        self.assertTrue(any(w.startswith("W49") for w in rep["warnings"]), rep.get("warnings"))
        md = "\n".join(assembly.format_loudness_report(rep))
        self.assertIn("段間對白電平落差", md)
        self.assertIn("W49", md)

    def test_many_segments_do_not_drift(self):
        # 奇數長度（AAC frame 對不齊）× 12 段：以前逐段重編 AAC 每段多一個 frame，會累積漂移
        clips = []
        for i in range(12):
            p = self.dir / f"odd_{i:02d}.mp4"
            _make_clip(p, 1.0 + 1 / 24, _speech(0.2 + 0.05 * (i % 4), 0.1, 0.95))
            clips.append(p)
        audio = [{"segment_id": f"S{i}", "has_dialogue": True, "windows": [(0.1, 0.95)], "window_source": "speech_window"}
                 for i in range(12)]
        out = self.dir / "odd.mp4"
        ok, msg = assembly.concat_videos(clips, out, target_lufs=-16.0, segment_audio=audio, report={})
        self.assertTrue(ok, msg)
        a = _probe(out, "stream=duration", "a:0")
        v = _probe(out, "stream=duration", "v:0")
        expected = sum(float(_probe(c, "stream=duration", "v:0")["duration"]) for c in clips)
        self.assertAlmostEqual(float(v["duration"]), expected, delta=0.05)
        self.assertAlmostEqual(float(a["duration"]), float(v["duration"]), delta=0.05)


if __name__ == "__main__":
    unittest.main()
