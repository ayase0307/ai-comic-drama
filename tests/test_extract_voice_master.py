import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "storyboard"))

import extract_voice_master as evm


def _have_ffmpeg() -> bool:
    return bool(shutil.which("ffmpeg")) and bool(shutil.which("ffprobe"))


class VoiceMasterCandidateTests(unittest.TestCase):
    """母帶候選的挑選規則。"""

    @staticmethod
    def _segments():
        return [
            {
                "segment_id": "EP01-S01-a",
                "shots": [{
                    "shot_id": "SH02",
                    "dialogue_and_audio": {
                        "has_dialogue": True, "speaker": "C-guide",
                        "line_verbatim": "這塊蛙仙石，從哪來的？",
                        "voice_4d_spec": "voiceover", "lips_closed_lock": True,
                        "speech_window": {"start": 4, "end": 6.5, "unit": "segment_seconds"},
                    },
                }],
            },
            {
                "segment_id": "EP01-S01-b",
                "shots": [{
                    "shot_id": "SH02",
                    "dialogue_and_audio": {
                        "has_dialogue": True, "speaker": "C-shangshan",
                        "line_verbatim": "洛年，去不去沙灘？",
                        "lips_closed_lock": False,
                        "speech_window": {"start": 4, "end": 6.5, "unit": "segment_seconds"},
                    },
                }],
            },
            {
                "segment_id": "EP01-S01-c",
                "shots": [
                    {
                        "shot_id": "SH01",
                        "dialogue_and_audio": {
                            "has_dialogue": True, "speaker": "C-luonien",
                            "line_verbatim": "叔叔，今天沒事的話，",
                            "lips_closed_lock": False,
                            "speech_window": {"start": 2, "end": 4.5, "unit": "segment_seconds"},
                        },
                    },
                    {
                        "shot_id": "SH02",
                        "dialogue_and_audio": {
                            "has_dialogue": True, "speaker": "C-luonien",
                            "line_verbatim": "我就不下去了。",
                            "lips_closed_lock": False,
                            "speech_window": {"start": 7.5, "end": 10, "unit": "segment_seconds"},
                        },
                    },
                ],
            },
        ]

    def test_voiceover_lines_are_not_usable_as_voice_masters(self):
        rows = evm.collect_candidates(self._segments())
        guide = next(r for r in rows if r["speaker"] == "C-guide")
        self.assertFalse(guide["visible_mouth"], "畫外音的語音由外部 TTS 負責，不能當 H3 音色母帶")

    def test_on_screen_lines_are_usable(self):
        rows = evm.collect_candidates(self._segments())
        hero = [r for r in rows if r["speaker"] == "C-luonien"]
        self.assertEqual(len(hero), 2)
        self.assertTrue(all(r["visible_mouth"] for r in hero))

    def test_pick_candidate_prefers_the_longest_line(self):
        rows = evm.collect_candidates(self._segments())
        chosen = evm.pick_candidate(rows, "EP01-S01-c", "C-luonien", None)
        self.assertEqual(chosen["duration"], 2.5)
        self.assertEqual(chosen["start"], 2.0)

    def test_pick_candidate_can_target_one_shot(self):
        rows = evm.collect_candidates(self._segments())
        chosen = evm.pick_candidate(rows, "EP01-S01-c", "C-luonien", "SH02")
        self.assertEqual(chosen["shot_id"], "SH02")
        self.assertEqual(chosen["start"], 7.5)

    def test_missing_character_raises(self):
        rows = evm.collect_candidates(self._segments())
        with self.assertRaises(SystemExit):
            evm.pick_candidate(rows, "EP01-S01-c", "C-NOBODY", None)


@unittest.skipUnless(_have_ffmpeg(), "需要 ffmpeg / ffprobe")
class VoiceMasterExtractionTests(unittest.TestCase):
    """實際抽檔：切點取自 speech_window，輸出固定格式並留下稽核紀錄。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.segments_path = self.root / "segments-ep01.json"
        self.segments_path.write_text(json.dumps({
            "segments": [{
                "segment_id": "EP01-S01-c",
                "shots": [{
                    "shot_id": "SH01",
                    "dialogue_and_audio": {
                        "has_dialogue": True, "speaker": "C-luonien",
                        "line_verbatim": "叔叔，今天沒事的話，",
                        "lips_closed_lock": False,
                        "speech_window": {"start": 2.0, "end": 4.5, "unit": "segment_seconds"},
                    },
                }],
            }],
        }, ensure_ascii=False), encoding="utf-8")
        self.video = self.root / "EP01-S01-c.mp4"
        subprocess.run([
            "ffmpeg", "-y", "-v", "error",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=10:sample_rate=48000",
            "-f", "lavfi", "-i", "color=c=blue:s=320x180:d=10:r=24",
            "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
            str(self.video),
        ], check=True, capture_output=True)

    def test_extraction_writes_a_normalised_wav_and_provenance(self):
        out = self.root / "assets" / "voices" / "V-luonien-master-v1.wav"
        code = evm.main([
            "--segments", str(self.segments_path),
            "--segment-id", "EP01-S01-c",
            "--character", "C-luonien",
            "--videos-dir", str(self.root),
            "--output", str(out),
        ])
        self.assertEqual(code, 0)
        self.assertTrue(out.is_file())
        duration = evm.probe_duration(out)
        self.assertAlmostEqual(duration, 2.5, delta=0.15)
        sidecar = out.with_suffix(out.suffix + ".provenance.json")
        self.assertTrue(sidecar.is_file())
        record = json.loads(sidecar.read_text(encoding="utf-8"))
        self.assertEqual(record["voice_id"], "V-luonien")
        self.assertEqual(record["character_id"], "C-luonien")
        self.assertEqual(record["source_kind"], "generated_segment")
        self.assertEqual(record["window_seconds"]["start"], 2.0)
        self.assertEqual(record["window_seconds"]["end"], 4.5)
        self.assertEqual(record["line_verbatim"], "叔叔，今天沒事的話，")
        self.assertEqual(record["output_format"]["sample_rate"], 48000)
        self.assertEqual(record["output_format"]["channels"], 1)
        self.assertEqual(len(record["source_sha256"]), 64)
        self.assertEqual(len(record["output_sha256"]), 64)

    def test_a_line_shorter_than_two_seconds_is_rejected(self):
        data = json.loads(self.segments_path.read_text(encoding="utf-8"))
        data["segments"][0]["shots"][0]["dialogue_and_audio"]["speech_window"] = {
            "start": 2.0, "end": 3.0, "unit": "segment_seconds",
        }
        self.segments_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        out = self.root / "assets" / "voices" / "V-short.wav"
        with self.assertRaises(SystemExit):
            evm.main([
                "--segments", str(self.segments_path),
                "--segment-id", "EP01-S01-c",
                "--character", "C-luonien",
                "--videos-dir", str(self.root),
                "--output", str(out),
            ])
        self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
