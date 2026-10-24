"""後製變速：time_map 換算、清單合併寫入、區段斷言、光流提案、產檔與階段 7 換算。"""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for extra in (ROOT / "scripts", ROOT / "scripts" / "storyboard", ROOT / "scripts" / "voice", ROOT / "scripts" / "edit"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

import speed_ramps as SR  # noqa: E402
import motion_qa  # noqa: E402

HAS_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
try:
    import numpy  # noqa: F401
    HAS_NUMPY = True
except ImportError:  # pragma: no cover
    HAS_NUMPY = False
try:
    import cv2  # noqa: F401
    HAS_CV2 = True
except ImportError:  # pragma: no cover
    HAS_CV2 = False


def _sections(spec):
    out = []
    for f0, f1, sp in spec:
        out.append({"start_frame": f0, "end_frame": f1, "start": f0 / 24, "end": f1 / 24, "speed": sp,
                    "kind": "x", "reason": ""})
    return out


class TimeMapTests(unittest.TestCase):
    def test_cut_and_speed_mapping(self):
        secs = _sections([(0, 12, 0), (12, 36, 1.0), (36, 84, 2.0), (84, 96, 1.0)])
        tmap, total = SR.build_time_map(secs, 24)
        self.assertAlmostEqual(total, 1.0 + 1.0 + 0.5, places=3)
        self.assertEqual(SR.map_time(0.2, tmap), 0.0)          # 剪掉區段 → 下一段起點
        self.assertAlmostEqual(SR.map_time(0.5, tmap), 0.0, places=3)
        self.assertAlmostEqual(SR.map_time(1.0, tmap), 0.5, places=3)
        self.assertAlmostEqual(SR.map_time(2.5, tmap), 1.0 + 0.5, places=3)  # 2× 區段中間
        self.assertAlmostEqual(SR.map_time(4.0, tmap), 2.5, places=3)

    def test_validate_rejects_protect_violation_and_gaps(self):
        seg = {"fps": 24, "frames": 48, "sections": _sections([(0, 24, 2.0), (24, 48, 1.0)]),
               "protect": [{"start": 0.5, "end": 0.8}]}
        self.assertTrue(any("台詞保護區" in e for e in SR.validate_sections(seg)))
        seg["sections"] = _sections([(0, 20, 1.0), (24, 48, 1.0)])
        self.assertTrue(any("不連續" in e for e in SR.validate_sections(seg)))
        seg["sections"] = _sections([(0, 24, 4.0), (24, 48, 1.0)])
        seg["protect"] = []
        self.assertTrue(any("倍率" in e for e in SR.validate_sections(seg)))


class MergeTests(unittest.TestCase):
    def test_rendered_segment_is_kept_when_source_unchanged(self):
        data = SR.empty_spec()
        data["segments"]["A"] = {"status": "rendered", "source_sha256": "aaa", "sections": ["manual"],
                                 "time_map": [1], "output": "videos/ramped/A.mp4"}
        action = SR.merge_segment(data, "A", {"status": "proposed", "source_sha256": "aaa", "sections": ["auto"]})
        self.assertEqual(action, "kept")
        self.assertEqual(data["segments"]["A"]["sections"], ["manual"])
        self.assertEqual(data["segments"]["A"]["time_map"], [1])

    def test_new_take_replaces_and_marks_stale(self):
        data = SR.empty_spec()
        data["segments"]["A"] = {"status": "rendered", "source_sha256": "aaa", "time_map": [1]}
        action = SR.merge_segment(data, "A", {"status": "proposed", "source_sha256": "bbb", "sections": []})
        self.assertEqual(action, "replaced")
        self.assertNotIn("time_map", data["segments"]["A"])
        self.assertEqual(data["segments"]["A"]["stale_from"]["source_sha256"], "aaa")

    def test_update_render_fields_only_touches_one_segment(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "videos" / "speed-ramps.json"
            data = SR.empty_spec()
            data["segments"] = {"A": {"status": "approved"}, "B": {"status": "approved", "note": "人工"}}
            SR.save_spec(path, data)
            SR.update_render_fields(path, "A", {"status": "rendered", "time_map": [1], "junk": 1})
            got = SR.load_spec(path)
            self.assertEqual(got["segments"]["A"]["status"], "rendered")
            self.assertNotIn("junk", got["segments"]["A"])
            self.assertEqual(got["segments"]["B"], {"status": "approved", "note": "人工"})


class ProposeTests(unittest.TestCase):
    def _flow(self):
        rows = []
        for f in range(1, 96):
            if f < 10:
                diff, resid = 0.0, 0.0           # 開頭凍結
            elif f < 30:
                diff, resid = 20.0, 60.0         # 撞擊
            elif f < 72:
                diff, resid = 1.0, 2.0           # 定住 1.75 s
            else:
                diff, resid = 3.0, 2.0           # 台詞（也很靜，但要保護）
            rows.append({"f": f, "t": round(f / 24, 4), "diff": diff, "cam": 0.0, "resid_p95": resid})
        return {"fps": 24.0, "frames": 96, "cuts": [], "rows": rows}

    def test_frozen_head_hold_and_dialogue_protection(self):
        flow = self._flow()
        stats = motion_qa.shot_stats(flow, [("SH01", 0.0, 4.0)])
        protect = [{"start": 3.0, "end": 4.0, "why": "台詞"}]
        secs = motion_qa.propose_sections(flow, stats, protect)
        self.assertEqual(secs[0]["kind"], "frozen_head")
        self.assertEqual(secs[0]["speed"], 0)
        holds = [s for s in secs if s["kind"] == "hold"]
        self.assertTrue(holds and holds[0]["speed"] == 3.0)
        last = secs[-1]
        self.assertEqual(last["speed"], 1.0)
        self.assertEqual(last["end_frame"], 96)
        seg = {"fps": 24, "frames": 96, "sections": secs, "protect": protect}
        self.assertEqual(SR.validate_sections(seg), [])

    def test_protect_windows_from_segment(self):
        seg = {"shots": [
            {"shot_id": "SH01", "start_time": 0, "end_time": 3, "dialogue_and_audio": {"has_dialogue": False}},
            {"shot_id": "SH02", "start_time": 3, "end_time": 6,
             "dialogue_and_audio": {"has_dialogue": True, "line_verbatim": "媽的！", "speech_window": {"start": 4.0, "end": 5.5}}},
        ], "external_narration": [{"start": 0.5, "end": 1.0, "line": "旁白"}]}
        wins = motion_qa.protect_windows(seg, vad=[(3.8, 4.2), (1.5, 2.0)])
        self.assertEqual([(w["start"], w["end"]) for w in wins], [(0.5, 1.0), (3.8, 5.5)])


@unittest.skipUnless(HAS_FFMPEG and HAS_NUMPY, "需要 ffmpeg 與 numpy")
class RenderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "videos").mkdir()
        self.src = self.root / "videos" / "EP01-S01.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=320x180:r=24:d=3",
                        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=3",
                        "-af", "volume=0.5", "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                        "-c:a", "aac", str(self.src)], check=True)
        self.sha = SR.sha256_file(self.src)

    def tearDown(self):
        self.tmp.cleanup()

    def _spec(self, sections, protect):
        data = SR.empty_spec()
        data["segments"]["EP01-S01"] = {"status": "approved", "source": "videos/EP01-S01.mp4",
                                        "source_sha256": self.sha, "fps": 24, "frames": 72,
                                        "orig_duration_s": 3.0, "protect": protect, "sections": sections}
        SR.save_spec(SR.spec_path(self.root), data)

    def test_render_writes_ramped_file_and_keeps_original(self):
        import speed_ramp
        self._spec(_sections([(0, 24, 1.0), (24, 48, 2.0), (48, 72, 1.0)]), [{"start": 0.0, "end": 0.9, "why": "台詞"}])
        rc = speed_ramp.main(["--root", str(self.root)])
        self.assertEqual(rc, 0)
        seg = SR.load_spec(SR.spec_path(self.root))["segments"]["EP01-S01"]
        self.assertEqual(seg["status"], "rendered")
        self.assertAlmostEqual(seg["new_duration_s"], 2.5, delta=0.1)
        self.assertGreaterEqual(seg["verify"]["protect_corr_min"], 0.98)
        self.assertTrue((self.root / "videos" / "ramped" / "EP01-S01.mp4").is_file())
        self.assertEqual(SR.sha256_file(self.src), self.sha)
        info = SR.ramped_source(self.root, "EP01-S01")
        self.assertEqual(info["rel"], "videos/ramped/EP01-S01.mp4")
        self.assertAlmostEqual(SR.map_time(2.5, info["time_map"]), 2.0, places=2)

    def test_protect_violation_refuses_to_render(self):
        import speed_ramp
        self._spec(_sections([(0, 24, 2.0), (24, 72, 1.0)]), [{"start": 0.0, "end": 0.9, "why": "台詞"}])
        self.assertEqual(speed_ramp.main(["--root", str(self.root)]), 1)
        self.assertFalse((self.root / "videos" / "ramped" / "EP01-S01.mp4").exists())

    def test_overwritten_source_invalidates_ramp(self):
        import speed_ramp
        self._spec(_sections([(0, 24, 1.0), (24, 48, 2.0), (48, 72, 1.0)]), [])
        speed_ramp.main(["--root", str(self.root)])
        self.src.write_bytes(self.src.read_bytes() + b"\0")
        self.assertIn("stale", SR.ramped_source(self.root, "EP01-S01"))

    @unittest.skipUnless(HAS_CV2, "需要 opencv")
    def test_motion_qa_runs_end_to_end(self):
        (self.root / "segments-ep01.json").write_text(json.dumps({"segments": [{
            "segment_id": "EP01-S01", "shots": [{"shot_id": "SH01", "start_time": 0, "end_time": 3,
                                                  "dialogue_and_audio": {}}]}]}), encoding="utf-8")
        rep = motion_qa.run(self.root)
        self.assertIn("EP01-S01", rep["segments"])
        self.assertTrue((self.root / "videos" / "qa" / "motion" / "EP01-S01.json").is_file())


class ConcatPlanTests(unittest.TestCase):
    def test_captions_and_next_segment_shift_with_time_map(self):
        import concat_adapter
        tmap, total = SR.build_time_map(_sections([(0, 24, 2.0), (24, 72, 1.0)]), 24)  # 3 s → 2.5 s
        plan = concat_adapter.build_plan(
            name="t", order=["EP01-S01", "EP01-S02"], durations={"EP01-S01": total, "EP01-S02": 2.0},
            lines={"EP01-S01": [{"text": "你好嗎", "start": 2.0, "end": 2.8}],
                   "EP01-S02": [{"text": "還行", "start": 0.5, "end": 1.0}]},
            asr={}, placement={}, manifest={}, time_maps={"EP01-S01": tmap})
        caps = {c["text"]: c for c in plan["captions"]}
        self.assertAlmostEqual(caps["你好嗎"]["start"], 1.5, places=2)
        self.assertAlmostEqual(caps["還行"]["start"], 2.5 + 0.5, places=2)
        self.assertAlmostEqual(plan["total"], 4.5, places=2)


if __name__ == "__main__":
    unittest.main()
