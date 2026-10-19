import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_stage_review as review


class ScopedVideoReviewTests(unittest.TestCase):
    def test_review_uses_report_videos_and_excludes_rejected_batch(self):
        with tempfile.TemporaryDirectory(dir=ROOT / 'tmp') as directory:
            project = Path(directory)
            target = project / 'videos/repair-pilot-v2/EP01-S01-a.mp4'
            target.parent.mkdir(parents=True)
            target.write_bytes(b'fixture')
            (project / 'videos/rejected.mp4').write_bytes(b'old')
            report = {'results': [{'segment_id': 'EP01-S01-a', 'video_file': 'videos/repair-pilot-v2/EP01-S01-a.mp4', 'passed': True}]}
            (project / 'videos/qa-report.json').write_text(json.dumps(report), encoding='utf-8')
            with patch.object(review, 'stage6_errors', return_value=[]), patch.object(review, 'wrap_studio_html', side_effect=lambda *args: args[-2]):
                passed, errors, output = review.build_stage_6(project, {})
            self.assertTrue(passed, errors)
            self.assertIn('../videos/repair-pilot-v2/EP01-S01-a.mp4', output)
            self.assertNotIn('rejected.mp4', output)


if __name__ == '__main__':
    unittest.main()
