"""collect 的真實 HTTP 演練：起一個本機假 FreeVideo，驗證 GET→下載→ffprobe→ledger。

真實 GPU 演練需要 FreeVideo 閒置；這個測試把「網路層＋下載＋斷言＋帳本」跑成可重複的，
只剩下模型推論本身不在迴路裡（那部分由 P4 的 mock 測試與實機經驗覆蓋）。
"""
import json
import shutil
import socket
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from scripts.storyboard import submit_h3_segments as submit

ROOT = Path(__file__).resolve().parents[1]
FFMPEG = shutil.which("ffmpeg")
FRAMES = 124


class _Handler(BaseHTTPRequestHandler):
    video_bytes = b""

    def log_message(self, *args):  # 安靜
        pass

    def _send(self, status, payload, content_type="application/json"):
        body = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if "/jobs/J1" in self.path:
            self._send(200, {
                "job": {
                    "id": "J1", "status": "succeeded",
                    "plan": {"geometry": {"frames": FRAMES}},
                    "result": {"video": {"url": "/freevideo/agent/v1/library/x.mp4"}},
                }
            })
            return
        if self.path.endswith("/library/x.mp4"):
            self._send(200, self.video_bytes, "video/mp4")
            return
        self._send(404, {"error": "not found"})


@unittest.skipUnless(FFMPEG, "需要 ffmpeg 產生測試影片")
class CollectHttpDrillTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(tempfile.mkdtemp(dir=ROOT))
        video = cls.root / "source.mp4"
        subprocess.run(
            [FFMPEG, "-y", "-loglevel", "error", "-f", "lavfi",
             "-i", f"color=c=gray:s=320x180:d={FRAMES / 24:.4f}:r=24",
             "-pix_fmt", "yuv420p", str(video)],
            check=True,
        )
        _Handler.video_bytes = video.read_bytes()
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.api = f"http://127.0.0.1:{cls.port}/freevideo/agent/v1"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        shutil.rmtree(cls.root, ignore_errors=True)

    def setUp(self):
        self.out = Path(tempfile.mkdtemp(dir=self.root))
        self.ledger = self.out / "_fv-job-ledger.json"
        self.ledger.write_text(json.dumps({
            "project": str(self.root.resolve()),
            "api_scope": self.api,
            "jobs": [{"id": "J1", "segment_id": "EP99-S01", "status": "waiting", "frames": FRAMES}],
        }), encoding="utf-8")

    def test_collect_downloads_and_asserts_over_real_http(self):
        summary = submit.collect_jobs(self.api, "token", self.ledger, self.out)
        self.assertEqual(summary["downloaded"], 1, summary)
        self.assertTrue((self.out / "EP99-S01.mp4").exists())
        ledger = json.loads(self.ledger.read_text(encoding="utf-8"))
        entry = ledger["jobs"][0]
        self.assertEqual(entry["status"], "downloaded")
        self.assertTrue(entry.get("duration_asserted"))

    def test_collect_twice_is_idempotent(self):
        first = submit.collect_jobs(self.api, "token", self.ledger, self.out)
        second = submit.collect_jobs(self.api, "token", self.ledger, self.out)
        self.assertEqual(first["downloaded"], 1)
        self.assertEqual(second["skipped"], 1)
        self.assertEqual(second["downloaded"], 0)


class CollectHttpFailureTests(unittest.TestCase):
    """伺服器說成功但檔案是壞的 → 必須隔離，不得記成 downloaded。"""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(dir=ROOT))
        self.addCleanup(lambda: shutil.rmtree(self.root, ignore_errors=True))
        self.out = self.root / "videos"
        self.out.mkdir()
        self.ledger = self.out / "_fv-job-ledger.json"

    def test_corrupt_download_is_quarantined(self):
        _Handler.video_bytes = b"not-an-mp4"
        server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        api = f"http://127.0.0.1:{server.server_address[1]}/freevideo/agent/v1"
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            self.ledger.write_text(json.dumps({
                "project": str(self.root.resolve()), "api_scope": api,
                "jobs": [{"id": "J1", "segment_id": "EP99-S01", "status": "waiting", "frames": FRAMES}],
            }), encoding="utf-8")
            summary = submit.collect_jobs(api, "token", self.ledger, self.out)
        finally:
            server.shutdown()
            server.server_close()
        self.assertEqual(summary["unverified"], 1)
        self.assertEqual(summary["downloaded"], 0)
        self.assertFalse((self.out / "EP99-S01.mp4").exists())
        self.assertTrue((self.out / "EP99-S01.unverified.mp4").exists())


if __name__ == "__main__":
    unittest.main()
