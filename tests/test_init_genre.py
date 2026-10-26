import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import init_project as ip


class InitGenre(unittest.TestCase):
    def test_genre_flows_to_all_stubs(self):
        f = ip.build_files("T", 1, "t", genre="wuxia_action")
        import json
        self.assertEqual(json.loads(f["adapt/source.json"])["genre_mode"], "wuxia_action")
        self.assertEqual(json.loads(f["adapt/bible.json"])["style_mode"], "wuxia_action")
        h = [k for k in f if k.startswith("handoff-")][0]
        self.assertEqual(json.loads(f[h])["genre_mode"], "wuxia_action")

    def test_default_unchanged(self):
        f = ip.build_files("T", 1, "t")
        import json
        self.assertEqual(json.loads(f["adapt/source.json"])["genre_mode"], "healing_literary")


if __name__ == "__main__":
    unittest.main()
