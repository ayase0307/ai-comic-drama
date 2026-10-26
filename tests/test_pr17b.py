import unittest
from scripts.storyboard import continuity_lint


class S6(unittest.TestCase):
    def _w(self, shot):
        p = "Continuity anchors: style anchor: x; blocking: the bullies stand mid-alley; lighting lock: dusk.\n\n[Shot 1] " + shot
        return continuity_lint.lint_shots([{"segment_id": "S1", "h3_prompt": p}])["warnings"]

    def test_crowd_anchor_on_cu(self):
        self.assertTrue(any("S6" in w for w in self._w("CU (85mm, 1.2m) of Zhu, as the camera holds. Blocking: a wall.")))

    def test_empty_bg_ok(self):
        self.assertFalse(any("S6" in w for w in self._w("CU (85mm, 1.2m) of Zhu. Blocking: the background behind him is empty.")))

    def test_wide_ok(self):
        self.assertFalse(any("S6" in w for w in self._w("WS (24mm, 6m) of the alley. Blocking: a wall.")))


class Rules(unittest.TestCase):
    def test_version_in_compiler(self):
        from scripts.storyboard import compile_layer2_to_h3 as c
        self.assertTrue(c.COMPILER_RULES_VERSION)


if __name__ == "__main__":
    unittest.main()
