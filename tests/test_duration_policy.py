import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "storyboard" / "handoff_to_skeleton.py"
FIXTURE = ROOT / "scripts/adapt/tests/fixtures/case01_high_density_low_event/handoff.json"


def run_skeleton(out: Path, *extra: str) -> dict:
    proc = subprocess.run([sys.executable, str(CLI), str(FIXTURE), "--out-dir", str(out), "--force", *extra],
                          capture_output=True, text=True, encoding="utf-8")
    segs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(out.glob("layer2-*.json"))]
    return {"stderr": proc.stderr, "segs": segs}


def total(segs) -> float:
    return sum(sh["duration"] for s in segs for sh in s["shots"])


class DurationPolicyTests(unittest.TestCase):
    def test_report_mode_keeps_natural_and_records_it(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "tmp") as t:
            res = run_skeleton(Path(t), "--target-total-sec", "5")
            self.assertGreater(total(res["segs"]), 5)
            self.assertTrue(all("natural_duration_sec" in s["metadata"] for s in res["segs"]))
            self.assertIn("未壓縮", res["stderr"])

    def test_fit_only_compresses_never_stretches(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "tmp") as t:
            natural = total(run_skeleton(Path(t), "--target-total-sec", "0")["segs"])
            res = run_skeleton(Path(t), "--duration-policy", "fit", "--target-total-sec", str(natural * 5))
            self.assertAlmostEqual(total(res["segs"]), natural, places=1)
            self.assertTrue(all(sh["duration"] <= 15 for s in res["segs"] for sh in s["shots"]))


if __name__ == "__main__":
    unittest.main()
