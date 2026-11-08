"""包計畫 `segments` 每段覆寫：同資產不同段用不同包（已拍段沿用舊包、新段用新包）。

- 有覆寫的段：refmods 用覆寫包（tag／kind 沿用計畫條目）。
- 沒列的段：照 default。
- 覆寫只影響包名選擇，不產生 gap／警告。
"""
import contextlib
import copy
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "storyboard"))
sys.path.insert(0, str(ROOT / "tests"))

import _remix_fixture as fx  # noqa: E402
import generate_bindings as gb  # noqa: E402

SEG = "EP04-S02-d"


class PackPlanSegmentOverrideTests(unittest.TestCase):
    def setUp(self):
        (ROOT / "tmp").mkdir(exist_ok=True)
        tmp = tempfile.TemporaryDirectory(dir=ROOT / "tmp")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def _bind(self, packs) -> dict:
        fx.write_project(self.root, packs=packs)
        with contextlib.redirect_stderr(io.StringIO()) as err, contextlib.redirect_stdout(io.StringIO()):
            code = gb.main(["--root", str(self.root)])
        self.assertEqual(code, 0, err.getvalue())
        return json.loads((self.root / "video-bindings.json").read_text(encoding="utf-8"))

    def _pack_of(self, bindings: dict, asset_id: str) -> str:
        seg = bindings["segments"][0]
        rec = next(r for r in seg["refmods"] if r["id"] == asset_id)
        return rec["pack"]

    def test_override_pack_for_the_listed_segment(self):
        packs = copy.deepcopy(fx.PACKS)
        packs["packs"]["C-YE"]["segments"] = {SEG: "ejin3_yeweishan_v2"}
        bindings = self._bind(packs)
        self.assertEqual(self._pack_of(bindings, "C-YE"), "ejin3_yeweishan_v2")
        rec = next(r for r in bindings["segments"][0]["refmods"] if r["id"] == "C-YE")
        self.assertEqual(rec["tag"], "Video")  # tag／kind 沿用計畫條目
        # 沒覆寫的資產照 default
        self.assertEqual(self._pack_of(bindings, "C-LAI"), "ejin3_laiyixin")

    def test_no_override_map_means_default(self):
        bindings = self._bind(fx.PACKS)
        self.assertEqual(self._pack_of(bindings, "C-YE"), "ejin3_yeweishan")

    def test_override_for_other_segment_is_ignored(self):
        packs = copy.deepcopy(fx.PACKS)
        packs["packs"]["C-YE"]["segments"] = {"EP99-S99-x": "ejin3_yeweishan_v2"}
        bindings = self._bind(packs)
        self.assertEqual(self._pack_of(bindings, "C-YE"), "ejin3_yeweishan")


if __name__ == "__main__":
    unittest.main()
