"""PR-R8：h3d pack check（計畫表 ↔ 家機 /packs 對帳）。"""
import json
import shutil
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in (str(ROOT / "scripts"), str(ROOT / "scripts" / "storyboard")):
    if p not in sys.path:
        sys.path.insert(0, p)

from scripts.storyboard import remix_pack as rp  # noqa: E402


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.rstrip("/").endswith("/projects"):
            self._send(200, {"projects": [{"id": 7, "name": "測試專案"}]})
            return
        if self.path.rstrip("/").endswith("/packs"):
            self._send(200, {"packs": [
                {"name": "demo_scene_room", "kind": "scene", "tag": "Picture", "project": 7},
                {"name": "demo_hero", "kind": "actor", "tag": "Video", "project": 7},
                {"name": "demo_hero_w02", "kind": "actor", "tag": "Video", "project": 7},
                {"name": "demo_friend", "kind": "prop", "tag": "Video", "project": 7},
                {"name": "other_pack", "kind": "actor", "tag": "Video", "project": 7},
                {"name": "wrong_project_pack", "kind": "actor", "tag": "Video", "project": 3},
            ]})
            return
        self._send(404, {"error": "not found"})


class RemixPackCheckTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.api = f"http://127.0.0.1:{cls.port}/remix/agent/v1"
        cls.token_dir = Path(tempfile.mkdtemp())
        cls.token_file = cls.token_dir / "agent.token"
        cls.token_file.write_text("test-token", encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        shutil.rmtree(cls.token_dir, ignore_errors=True)

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(dir=ROOT))
        self.addCleanup(lambda: shutil.rmtree(self.root, ignore_errors=True))

    def write_plan(self, packs):
        path = self.root / "assets" / "character-packs.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"packs": packs}, ensure_ascii=False), encoding="utf-8")
        return path

    def args(self, extra=None):
        return ["--root-dir", str(self.root), "--project", "測試專案",
                "--api-url", self.api, "--token-file", str(self.token_file)] + (extra or [])

    def test_all_packs_present_passes(self):
        self.write_plan({
            "S-ROOM": {"default": "demo_scene_room", "tag": "Picture", "kind": "scene"},
            "C-HERO": {"default": "demo_hero", "tag": "Video", "kind": "actor",
                       "costumes": {"W02dirty": {"pack": "demo_hero_w02"}}},
            "P-PROP": "demo_friend",
        })
        self.assertEqual(rp.main(self.args()), 0)

    def test_missing_pack_fails(self):
        self.write_plan({"S-ROOM": {"default": "demo_scene_room", "kind": "scene"},
                         "C-GHOST": {"default": "demo_ghost", "kind": "actor"}})
        self.assertEqual(rp.main(self.args()), 1)

    def test_kind_mismatch_fails(self):
        self.write_plan({"P-PROP": {"default": "demo_friend", "kind": "scene"}})  # 家機是 prop
        self.assertEqual(rp.main(self.args()), 1)

    def test_cross_project_pack_counts_as_missing(self):
        self.write_plan({"C-X": {"default": "wrong_project_pack", "kind": "actor"}})
        self.assertEqual(rp.main(self.args()), 1)

    def test_json_output_lists_findings(self):
        self.write_plan({"S-ROOM": {"default": "demo_scene_room", "kind": "scene"},
                         "C-GHOST": {"default": "demo_ghost", "kind": "actor"}})
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = rp.main(self.args(["--json"]))
        self.assertEqual(code, 1)
        data = json.loads(buf.getvalue())
        self.assertEqual(len(data["missing"]), 1)
        self.assertEqual(data["missing"][0]["pack"], "demo_ghost")

    def test_plan_errors_are_reported(self):
        self.assertEqual(rp.main(self.args()), 2)  # 沒有計畫表


if __name__ == "__main__":
    unittest.main()
