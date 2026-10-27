"""階段 5 審核頁對 ref2va 段補跑 refcheck／staging（只提示，不擋）。"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for sub in ("scripts", "scripts/storyboard", "scripts/adapt"):
    p = str(ROOT / sub)
    if p not in sys.path:
        sys.path.insert(0, p)

import build_stage_review as bsr  # noqa: E402


def _write(tmp: Path, backend: str) -> Path:
    seg = {"segment_id": "EP01-S01", "metadata": {"video_backend": backend, "target_duration_sec": 6},
           "h3_prompt": "[Shot 1] The camera holds a static shot. Two students talk in the classroom while other students watch.",
           "shots": []}
    path = tmp / "segments-ep01.json"
    path.write_text(json.dumps({"segments": [seg]}, ensure_ascii=False), encoding="utf-8")
    return path


class Ref2vaAdvisoryTest(unittest.TestCase):
    def test_ref2va_crowd_word_listed_as_warning_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(Path(tmp), "ref2va")
            errors, panel = bsr.stage5_ref2va_advisory(Path(tmp), [path])
            self.assertEqual(errors, [])
            self.assertIn("E51", panel)
            self.assertIn("只提示", panel)

    def test_only_filter_skips_other_segments(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(Path(tmp), "ref2va")
            errors, panel = bsr.stage5_ref2va_advisory(Path(tmp), [path], only={"EP01-S99"})
            self.assertEqual((errors, panel), ([], ""))

    def test_remix_segments_left_to_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(Path(tmp), "remix")
            errors, panel = bsr.stage5_ref2va_advisory(Path(tmp), [path])
            self.assertEqual((errors, panel), ([], ""))


if __name__ == "__main__":
    unittest.main()
