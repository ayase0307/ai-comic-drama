"""P1-12：REMIX Studio 美術室生圖 adapter（imagegen_remix.py）＋image_backends 的 remix 後端偵測。"""
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

from scripts import image_backends as ib  # noqa: E402
from scripts.storyboard import imagegen_remix as ir  # noqa: E402


class _Handler(BaseHTTPRequestHandler):
    image_bytes = b""

    def log_message(self, *args):
        pass

    def _send(self, status, payload, content_type="application/json"):
        body = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.rstrip("/").endswith("/status"):
            self._send(200, {"ready": True, "service": "remix-studio"})
            return
        if "/jobs/J9?wait=" in self.path:
            self._send(200, {"job": {"id": "J9", "status": "succeeded",
                                     "result": {"images": [{"path": str(_Handler.source_path)}]}}})
            return
        self._send(404, {"error": "not found"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
        if self.path.rstrip("/").endswith("/images"):
            self._send(201, {"job": {"id": "J9", "status": "queued"}})
            return
        self._send(404, {"error": "not found"})


class ImagegenRemixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.source_path = cls.tmp / "studio-output.png"
        cls.source_path.write_bytes(b"png-bytes")
        _Handler.source_path = cls.source_path
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.api = f"http://127.0.0.1:{cls.port}/remix/agent/v1"
        cls.token_file = cls.tmp / "agent.token"
        cls.token_file.write_text("test-token", encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_generate_copies_studio_output_to_target(self):
        out = self.tmp / "out" / "C-x.png"
        code = ir.main(["--prompt", "a young man, navy jacket", "--purpose", "character",
                        "--out", str(out), "--project", "測試專案",
                        "--api-url", self.api, "--token-file", str(self.token_file)])
        self.assertEqual(code, 0)
        self.assertTrue(out.is_file())
        self.assertEqual(out.read_bytes(), b"png-bytes")

    def test_moss_requires_style(self):
        code = ir.main(["--prompt", "x", "--purpose", "character", "--out", str(self.tmp / "a.png"),
                        "--engine", "moss", "--api-url", self.api, "--token-file", str(self.token_file)])
        self.assertEqual(code, 2)

    def test_moss_rejects_ref_image(self):
        code = ir.main(["--prompt", "x", "--purpose", "character", "--out", str(self.tmp / "a.png"),
                        "--engine", "moss", "--style", "ST-01-QIUYAN", "--ref-image", str(self.source_path),
                        "--api-url", self.api, "--token-file", str(self.token_file)])
        self.assertEqual(code, 2)


class DetectRemixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.api = f"http://127.0.0.1:{cls.port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_detect_remix_ready(self):
        row = ib.detect_remix({"REMIX_API_URL": self.api}, probe=lambda h, p: True, fetch=ib.http_json)
        self.assertTrue(row["available"])
        self.assertIn("ready", row["reason"])

    def test_detect_remix_down(self):
        row = ib.detect_remix({"REMIX_API_URL": "http://127.0.0.1:1"}, probe=lambda h, p: False,
                              fetch=lambda url: None)
        self.assertFalse(row["available"])
        self.assertIn("連不上", row["reason"])

    def test_remix_backend_registered_for_stage2(self):
        self.assertIn("remix", ib.BACKENDS)
        self.assertIn(2, ib.BACKENDS["remix"]["stages"])
        self.assertTrue(ib.BACKENDS["remix"]["selectable"])
        self.assertIn("imagegen_remix.py", ib.command_for("remix", 2) or "")


if __name__ == "__main__":
    unittest.main()
