"""h3d bind 端到端離線測試：新專案（四視圖整板＋兩人同段，一人背對鏡頭）。

對照組：沒有 bindings 時 compile --check 被 E19／E20 擋（推論驗證）。
實驗組：h3d bind 先列出缺的正面裁切 → 照提示 h3d crop → 寫計畫表 → 再 bind → compile --check 通過。
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "storyboard"))

import generate_bindings as gb  # noqa: E402
import next_step  # noqa: E402

FIVE_PART = {
    1: {
        "camera": "35mm from three metres at chest height, locked off for the shot with the doorway on the left third.",
        "motion": "First Hero's head turns toward the doorway, then the shoulders follow, as the weight rolls onto the front foot, finally one step lands on the threshold stone while {C-FRIEND} stands on the right third with his back to camera.",
        "performance": "Hero's eyes narrow at the open doorway and the jaw sets before the first step is taken.",
        "light": "Grey daylight from the doorway falls across the face and leaves the far wall in soft shadow.",
        "sound": "A shoe scuffs the stone at about 1.5 s over a low steady wind.",
    },
    2: {
        "camera": "35mm from three metres, moving closer by about a fifth over the shot, ending in a medium close-up.",
        "motion": "First Hero stops inside the doorway, then the chest rises with one long breath, as the hands open at the sides, finally the gaze lifts and holds on the room ahead.",
        "performance": "Hero's brows ease, the mouth softens into a small nod, and the eye contact does not break.",
        "light": "Daylight now rims the cheek and hair from behind while the front of the face takes a warm bounce from the floor.",
        "sound": "One audible exhale at about 0.8 s; the wind drops away to room tone.",
    },
}


def run(args, cwd):
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    return subprocess.run([sys.executable, *[str(a) for a in args]], cwd=str(cwd), capture_output=True,
                          text=True, encoding="utf-8", errors="replace", env=env, timeout=240)


class BindingsGeneratorEndToEnd(unittest.TestCase):
    def setUp(self):
        from PIL import Image

        (ROOT / "tmp").mkdir(exist_ok=True)
        tmp = tempfile.TemporaryDirectory(dir=ROOT / "tmp")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        for name in ("layer2", "images", "adapt", "assets"):
            (self.root / name).mkdir()
        Image.new("RGB", (2560, 1440), (90, 90, 90)).save(self.root / "images/char-HERO.png")
        Image.new("RGB", (2560, 1440), (60, 60, 60)).save(self.root / "images/char-FRIEND.png")
        Image.new("RGB", (1344, 768), (120, 110, 100)).save(self.root / "images/S-ROOM.png")
        shots = []
        for index, (start, end, chars) in enumerate(((0.0, 3.5, ["C-HERO", "C-FRIEND"]), (3.5, 7.0, ["C-HERO"])), 1):
            shots.append({
                "shot_id": f"SH0{index}", "start_time": start, "end_time": end, "duration": end - start,
                "character_ids": chars,
                "camera_optics": {"shot_size": "MS", "focal_length": "35mm",
                                  "movement": "static" if index == 1 else "dollies in"},
                "action_and_performance": {"action_stages": [
                    "Hero turns toward the doorway", "then steps forward with a steady stance",
                    "Hero settles and holds his gaze"], "five_part_en": FIVE_PART[index]},
                "dialogue_and_audio": {"has_dialogue": False},
            })
        self.layer2 = self.root / "layer2" / "layer2-EP01-S01-a.json"
        self.layer2.write_text(json.dumps({
            "segment_id": "EP01-S01-a", "scene_id": "S-ROOM",
            "asset_refs": {"scene_id": "S-ROOM", "characters": [{"id": "C-HERO"}, {"id": "C-FRIEND"}]},
            "metadata": {"target_duration_sec": 7, "aspect_ratio": "16:9"}, "shots": shots,
        }, ensure_ascii=False), encoding="utf-8")
        (self.root / "adapt" / "bible.json").write_text(json.dumps({"characters": [
            {"character_id": "C-HERO", "canonical_name": "Hero",
             "visual_prompt_en": "young man with short black hair and a navy jacket", "reference_image": "images/char-HERO.png"},
            {"character_id": "C-FRIEND", "canonical_name": "Friend",
             "visual_prompt_en": "tall young man with a shaved head and a gray hoodie", "reference_image": "images/char-FRIEND.png"}],
            "locations": [{"location_id": "S-ROOM", "name": "Room", "visual_prompt_en": "a small apartment room",
                           "reference_image": "images/S-ROOM.png"}]}, ensure_ascii=False), encoding="utf-8")
        (self.root / "assets" / "face-visibility.json").write_text(json.dumps(
            {"shots": {"SH01": {"C-HERO": "face", "C-FRIEND": "back"}, "SH02": {"C-HERO": "face"}}}), encoding="utf-8")

    def _compile(self, *extra):
        return run([ROOT / "scripts" / "storyboard" / "compile_layer2_to_h3.py", "--layer2", "layer2/",
                    "--episode", "EP01", "--project-root", ".", "--output-segments", "segments-ep01.json",
                    "--check", "--skip-stage-gate", *extra], self.root)

    def test_without_bindings_the_board_and_unanchored_friend_are_blocked(self):
        result = self._compile("--bible", "adapt/bible.json")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("E19", result.stdout)
        self.assertIn("E20", result.stdout)

    def test_bind_lists_gaps_then_crop_plan_and_compile_passes(self):
        h3d = ROOT / "scripts" / "h3d.py"
        first = run([h3d, "bind", "--root", "."], self.root)
        self.assertEqual(first.returncode, 1)
        self.assertIn("C-HERO", first.stderr)
        self.assertIn("h3d.py crop", first.stderr)
        self.assertFalse((self.root / "video-bindings.json").exists(), "有缺口時不得寫半套綁定")

        cropped = run([h3d, "crop", "--root", ".", "--image", "images/char-HERO.png", "--box", gb.FACE_PANEL_BOX,
                       "--out-dir", "assets/crops", "--prefix", "C-HERO-face"], self.root)
        self.assertEqual(cropped.returncode, 0, cropped.stderr)
        crop = next((self.root / "assets" / "crops").glob("C-HERO-face*.png")).relative_to(self.root).as_posix()
        (self.root / "assets" / "character-reference-plans.json").write_text(json.dumps(
            {"characters": {"C-HERO": {"default": {"face_crop": crop}}}}), encoding="utf-8")

        self.assertIn("bind", next_step.stage5_producer(self.root, [])[0])
        second = run([h3d, "bind", "--root", "."], self.root)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertIn("compile", next_step.stage5_producer(self.root, [])[0])
        bindings = json.loads((self.root / "video-bindings.json").read_text(encoding="utf-8"))
        shot1 = bindings["segments"][0]["shots"][0]
        self.assertEqual(shot1["face_subject_ids"], ["C-HERO"])
        self.assertEqual(shot1["identity_anchor_ids"], ["C-FRIEND"])
        friend = next(e for e in shot1["reference_paths"]["characters"] if e["id"] == "C-FRIEND")
        self.assertEqual((friend["reference_view"], friend["panel_role"]), ("panel", "back"))

        compiled = self._compile("--bible", "video-bible.json", "--bindings", "video-bindings.json")
        self.assertEqual(compiled.returncode, 0, compiled.stdout[-3000:] + compiled.stderr[-2000:])
        segment = json.loads((self.root / "segments-ep01.json").read_text(encoding="utf-8"))["segments"][0]
        paths = {r.get("id"): r.get("path") for r in segment["reference_images"]}
        self.assertEqual(paths.get("C-HERO"), crop)
        self.assertEqual(segment.get("unanchored_in_frame_characters") or [], [])

    def test_rebind_keeps_hand_written_fields_and_detects_stale_layer2(self):
        (self.root / "assets" / "face-visibility.json").write_text(json.dumps(
            {"shots": {"SH01": {"C-HERO": "back", "C-FRIEND": "back"}, "SH02": {"C-HERO": "profile"}}}), encoding="utf-8")
        self.assertEqual(gb.main(["--root", str(self.root)]), 0)
        path = self.root / "video-bindings.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["segments"][0]["en_overlay"] = {"lighting_lock_line_en": "Grey daylight."}
        data["segments"][0]["shots"][0]["crop_note_en"] = "keep the doorway in frame"
        path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIsNone(gb.bindings_stale(self.root))
        self.layer2.write_text(self.layer2.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        self.assertIn("layer2-EP01-S01-a.json", gb.bindings_stale(self.root))
        self.assertEqual(gb.main(["--root", str(self.root)]), 0)
        again = json.loads(path.read_text(encoding="utf-8"))["segments"][0]
        self.assertEqual(again["en_overlay"], {"lighting_lock_line_en": "Grey daylight."})
        self.assertEqual(again["shots"][0]["crop_note_en"], "keep the doorway in frame")
        hero = again["shots"][1]["reference_paths"]["characters"][0]
        self.assertEqual(hero["panel_role"], "back", "段內聚合：back 優先於 profile")


if __name__ == "__main__":
    unittest.main()
