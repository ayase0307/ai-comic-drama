import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "storyboard"))
sys.path.insert(0, str(ROOT / "scripts"))

from compile_layer2_to_h3 import map_camera_motion


class ApprovedCameraMotionAliasTests(unittest.TestCase):
    def test_all_currently_used_natural_motion_phrases_have_semantic_mappings(self):
        examples = {
            "locked tripod": "static",
            "locked side camera": "static",
            "locked side camera with downward follow": "tilts down",
            "locked camera as frame falls to black": "static",
            "slow pan following uncle’s turn": "pans right",
            "slow push-in": "dollies in",
            "tilt from sun to Luo": "tilts down",
            "slow tilt down": "tilts down",
            "tilt up with the rising glow": "tilts up",
            "tilt with beast’s head movement": "tilts up",
            "輕微穩定推近，保持單一主體": "dollies in",
            "固定機位或沿南側短距離平移，禁止越過走廊軸線": "static",
            "固定機位，僅微幅跟隨手部動作": "static",
            "固定建立鏡位後小幅推近說話者": "dollies in",
            "固定貼近牆面，不越過南側機位": "static",
            "固定中景，留出字卡與空桌椅": "static",
            "車內固定機位，隨車身可見地微震": "static",
            "後座視點固定，輕微前移": "dollies in",
            "穩定的小幅推近，保持床軸同側": "dollies in",
            "穩定短推或定鏡，依台詞視線切主體": "static",
            "穩定側向滑移，將右側海景留在視線方向": "trucks right",
            "由右向左短跟拍洛年，保持南側軸線": "trucks left",
            "由司機背影緩慢移向遠海，保持橋欄水平": "pans right",
        }
        for raw, expected in examples.items():
            with self.subTest(raw=raw):
                self.assertEqual(map_camera_motion(raw), expected)

    def test_unrecognized_motion_remains_rejected(self):
        with self.assertRaisesRegex(ValueError, "不支援的 camera movement"):
            map_camera_motion("unmapped spiral crane move")


if __name__ == "__main__":
    unittest.main()
