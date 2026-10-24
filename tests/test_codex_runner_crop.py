import pathlib, sys, tempfile, unittest
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "storyboard"))
import run_codex_asset_gen as rc
import crop_sheet
from PIL import Image


class T(unittest.TestCase):
    def test_usage_limit(self):
        self.assertEqual(rc.parse_usage_limit("You've hit your usage limit. try again at 1:29 PM."), "1:29 PM")
        self.assertIsNone(rc.parse_usage_limit("all fine"))

    def test_session_images(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "tmp" if (ROOT / "tmp").exists() else None) as d:
            home = pathlib.Path(d)
            (home / "generated_images" / "abc12345").mkdir(parents=True)
            Image.new("RGB", (4, 4)).save(home / "generated_images" / "abc12345" / "a.png")
            Image.new("RGB", (4, 4)).save(home / "generated_images" / "a.png")
            self.assertEqual(len(rc.find_session_images(home, "abc12345")), 1)
            self.assertEqual(rc.find_session_images(home, ""), [])
            self.assertEqual(rc._session_id("session id: 0199-abcdef12\n"), "0199-abcdef12")

    def test_crop(self):
        self.assertEqual(crop_sheet.grid_boxes(300, 100, 3, 1)[1], (100, 0, 200, 100))
        self.assertEqual(crop_sheet.ratio_box(1672, 941, (0, 0, 0.5, 0.5)), (0, 0, 836, 470))
        with self.assertRaises(ValueError):
            crop_sheet.ratio_box(10, 10, (0.5, 0, 0.2, 1))
        with tempfile.TemporaryDirectory() as d:
            src = pathlib.Path(d) / "s.png"
            Image.new("RGB", (300, 100)).save(src)
            out = pathlib.Path(d) / "o"
            self.assertEqual(crop_sheet.main(["--image", str(src), "--grid", "3x1", "--cell", "2", "--out-dir", str(out)]), 0)
            with Image.open(out / "s-crop1.png") as im:
                self.assertEqual(im.size, (100, 100))


if __name__ == "__main__":
    unittest.main()
