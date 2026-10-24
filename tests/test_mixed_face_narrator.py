import importlib.util, unittest, pathlib
p = pathlib.Path(__file__).resolve().parents[1] / "scripts/storyboard/validate_storyboard.py"
spec = importlib.util.spec_from_file_location("vs_mf", p); vs = importlib.util.module_from_spec(spec); spec.loader.exec_module(vs)

def seg(speakers):
    return {"metadata": {}, "shots": [{"shot_id": f"S{i}", "dialogue_and_audio": {"has_dialogue": True, "speaker": sp, "line_verbatim": "好。"}} for i, sp in enumerate(speakers)]}

class MixedFaceNarratorTest(unittest.TestCase):
    def _warns(self, data):
        import inspect
        fn = next(f for n, f in inspect.getmembers(vs, inspect.isfunction) if "同段多說話人露臉" in inspect.getsource(f))
        try:
            res = fn(data)
        except TypeError:
            res = fn(data, None)
        return str(res)
    def test_narrator_not_counted(self):
        self.assertNotIn("同段多說話人露臉", self._warns(seg(["旁白", "C-ailu"])))
    def test_two_faces_still_warn(self):
        self.assertIn("同段多說話人露臉", self._warns(seg(["C-a", "C-b"])))
if __name__ == "__main__":
    unittest.main()
