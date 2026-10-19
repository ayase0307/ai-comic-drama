import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import build_stage_review as review
import project_state as ps


class Stage4ExplicitArtifactTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=ROOT / "tmp")
        self.project = Path(self.tmp.name)
        for folder in ("review", "images", "panels", "layer2", "videos", "final"):
            (self.project / folder).mkdir(exist_ok=True)

    def tearDown(self):
        self.tmp.cleanup()

    def _png(self, relative):
        path = self.project / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (24, 16), "white").save(path)
        return path

    def _layer(self, segment_id, global_shot_id, sketch_rel, grid_rel):
        self._png(sketch_rel)
        self._png(grid_rel)
        data = {
            "segment_id": segment_id,
            "scene_id": segment_id,
            "metadata": {"target_duration_sec": 8},
            "shots": [{
                "shot_id": "SH01",
                "global_shot_id": global_shot_id,
                "duration": 8,
                "sketch_file": sketch_rel,
                "sketch_generation": {"grid_file": grid_rel},
            }],
        }
        layer = self.project / "layer2" / f"layer2-{segment_id}.json"
        layer.write_text(json.dumps(data), encoding="utf-8")
        return layer

    def test_stage4_renders_actual_sketch_and_segment_grid_paths(self):
        self._layer(
            "EP01-S01", "EP01-SH001",
            "layer2/panels-grid/panel-EP01-SH001.png",
            "layer2/grids-outsourced/grid-EP01-G01.png",
        )
        self._layer(
            "EP01-S02", "EP01-SH002",
            "layer2/panels-grid/panel-EP01-SH002.png",
            "layer2/grids-outsourced/grid-EP01-G02.png",
        )

        _, _, rendered = review.build_stage_4(self.project, ps.load_state(self.project))

        cards = re.findall(r'<article class="sbs-card">(.*?)</article>', rendered, re.DOTALL)
        self.assertEqual(len(cards), 2)
        self.assertIn("../layer2/panels-grid/panel-EP01-SH001.png", cards[0])
        self.assertIn("EP01-SH001", cards[0])
        self.assertIn("../layer2/grids-outsourced/grid-EP01-G01.png", cards[0])
        self.assertNotIn("grid-EP01-G02.png", cards[0])
        self.assertIn("../layer2/panels-grid/panel-EP01-SH002.png", cards[1])
        self.assertIn("EP01-SH002", cards[1])
        self.assertIn("../layer2/grids-outsourced/grid-EP01-G02.png", cards[1])
        self.assertNotIn("grid-EP01-G01.png", cards[1])

    def test_valid_grid_does_not_mask_a_missing_per_shot_sketch(self):
        self._png("layer2/grids-outsourced/grid-EP01-G01.png")
        layer = self.project / "layer2" / "layer2-EP01-S01.json"
        layer.write_text(json.dumps({
            "segment_id": "EP01-S01",
            "shots": [{
                "shot_id": "SH01",
                "global_shot_id": "EP01-SH001",
                "sketch_generation": {"grid_file": "layer2/grids-outsourced/grid-EP01-G01.png"},
            }],
        }), encoding="utf-8")

        matched, errors = ps.stage4_artifacts(self.project)

        self.assertIn((self.project / "layer2/grids-outsourced/grid-EP01-G01.png").resolve(), matched)
        self.assertTrue(any("EP01-S01/SH01" in error and "缺少有效" in error for error in errors))

    def test_legacy_segment_grid_only_remains_valid_without_explicit_shot_mapping(self):
        legacy_grid = self._png("images/grid-seg1.png")
        layer = self.project / "layer2" / "layer2-seg1.json"
        layer.write_text(json.dumps({
            "segment_id": "seg1",
            "shots": [{"shot_id": "SH01"}],
        }), encoding="utf-8")

        matched, errors = ps.stage4_artifacts(self.project)

        self.assertEqual(matched, [legacy_grid.resolve()])
        self.assertEqual(errors, [])

    def test_stage4_snapshot_includes_each_explicit_grid_and_sketch_png(self):
        layer = self._layer(
            "EP01-S01", "EP01-SH001",
            "layer2/panels-grid/panel-EP01-SH001.png",
            "layer2/grids-outsourced/grid-EP01-G01.png",
        )

        artifacts = {item["path"]: item for item in ps.stage_snapshot(self.project, 4)["artifacts"]}

        self.assertIn("layer2/panels-grid/panel-EP01-SH001.png", artifacts)
        self.assertEqual(
            artifacts["layer2/grids-outsourced/grid-EP01-G01.png"]["sha256"],
            ps.sha256_file(self.project / "layer2/grids-outsourced/grid-EP01-G01.png"),
        )
        self.assertIn("layer2/" + layer.name, artifacts)

    def test_layer_relative_sketch_and_grid_paths_are_rendered(self):
        self._png("layer2/panels-outsourced/panel-EP01-SH001.png")
        self._png("layer2/grids-outsourced/grid-EP01-G01.png")
        layer = self.project / "layer2" / "layer2-EP01-S01.json"
        layer.write_text(json.dumps({
            "segment_id": "EP01-S01",
            "scene_id": "EP01-S01",
            "shots": [{
                "shot_id": "SH01",
                "global_shot_id": "EP01-SH001",
                "sketch_file": "panels-outsourced/panel-EP01-SH001.png",
                "sketch_generation": {"grid_file": "grids-outsourced/grid-EP01-G01.png"},
            }],
        }), encoding="utf-8")

        _, errors, rendered = review.build_stage_4(self.project, ps.load_state(self.project))

        self.assertFalse(any("EP01-S01/SH01" in error and "缺少有效" in error for error in errors))
        self.assertIn("../layer2/panels-outsourced/panel-EP01-SH001.png", rendered)
        self.assertIn("../layer2/grids-outsourced/grid-EP01-G01.png", rendered)


if __name__ == "__main__":
    unittest.main()
