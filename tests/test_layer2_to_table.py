import contextlib
import csv
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.storyboard import layer2_to_table


ROOT = Path(__file__).resolve().parents[1]


class CompiledTimelineExportTests(unittest.TestCase):
    def _segment(self):
        return {
            "segment_id": "EP01-S01-seg01",
            "scene_id": "S01",
            "metadata": {
                "aspect_ratio": "16:9",
                "target_duration_sec": 15.0,
                "effective_duration_sec": 14.375,
                "shots_count": 3,
            },
            "shots": [
                {"shot_id": "A", "start_time": 0.0, "end_time": 5.0, "duration": 5.0,
                 "dialogue_and_audio": {"has_dialogue": False}},
                {"shot_id": "B", "start_time": 5.0, "end_time": 10.0, "duration": 5.0,
                 "dialogue_and_audio": {"has_dialogue": False}},
                {"shot_id": "C", "start_time": 10.0, "end_time": 14.375, "duration": 4.375,
                 "dialogue_and_audio": {"has_dialogue": False}},
            ],
        }

    def test_compiled_segments_export_quantized_final_shot_to_csv(self):
        segment = self._segment()
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            source = root / "segments-ep01.json"
            timeline = root / "timeline.csv"
            source.write_text(json.dumps({"episode": "EP01", "segments": [segment]}), encoding="utf-8")
            args = ["layer2_to_table.py", str(source), "--timeline", str(timeline)]
            with patch.object(sys, "argv", args), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(layer2_to_table.main(), 0)
            with timeline.open(encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
        self.assertEqual(rows[-1]["end"], "14.375")
        self.assertEqual(rows[-1]["duration"], "4.375")
        self.assertEqual(rows[-1]["start"], "10.0")

    def test_compiled_check_rejects_empty_collection_and_wrong_effective_end(self):
        self.assertIn("不可為空", layer2_to_table.check_compiled_timeline({"segments": []})[0])
        segment = self._segment()
        segment["shots"][-1]["end_time"] = 15.0
        errors = layer2_to_table.check_compiled_timeline({"segments": [segment]})
        self.assertTrue(any("與有效時長" in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
