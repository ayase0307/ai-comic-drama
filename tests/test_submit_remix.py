"""PR-R7：REMIX Studio 送件 adapter（submit_remix.py）。

用本機假 REMIX server 驗證「網路層＋送件 body＋帳本＋下載＋identity」；
stage-5 門禁本身是共用程式（submit_h3_segments.verify_stage5_gate，另有測試），
這裡用 mock 放行，只測 adapter 自己的邏輯。
"""
import json
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
for p in (str(ROOT / "scripts"), str(ROOT / "scripts" / "storyboard")):
    if p not in sys.path:
        sys.path.insert(0, p)

import h3_spec  # noqa: E402
import prompt_authoring  # noqa: E402
from tests.test_remix_backend import remix_segment  # noqa: E402
from scripts.storyboard import submit_remix as sr  # noqa: E402

FFMPEG = shutil.which("ffmpeg")
FRAMES = h3_spec.frames_for(7.0, "ceil")  # 175

# 五小節齊全的 REMIX 三欄提示詞（第 1 鏡帶介紹句＋The shot opens on…，照 PR-R5 編譯格式）
ANCHOR = "semi-realistic cinematic painting with muted earth tones, realistic proportions."
REMIX_PROMPT = (
    f"integrated_multimodal_description: {ANCHOR} "
    "[Shot 1] The alley is wet after rain, lit by one warm lamp. "
    "<Picture 1> is the back alley location, keep its render style. "
    "<Video 1> is Hero, a young man with short black hair and a navy jacket. "
    "<Video 2> is Friend, a tall young man with a shaved head and a gray hoodie. "
    "The shot opens on a medium two-shot of Hero and Friend in the back alley. "
    "Camera: static medium two-shot at chest height, both framed from the knees up against the alley wall. "
    "Motion: first Hero turns his head toward Friend, then he leans a half step closer as his mouth starts to move. "
    "Performance: Hero speaks with a raised chin and impatient eyes while Friend keeps his arms crossed and watches him. "
    "Light: a warm lamp light falls from the left edge across both faces and the wet ground. "
    "Sound: distant traffic and footsteps on wet asphalt, close and uneven, while Hero says (S1): <d>[Chinese] 我們走吧。</d>\n"
    "[Shot 2] At 00:03.500, close-up of Friend. "
    "Camera: slow dolly in from medium to close-up, lens at eye level, alley wall soft behind him. "
    "Motion: first Friend nods once, then he looks back toward Hero as the camera keeps pushing in until the cut. "
    "Performance: Friend's brows lift and he gives a thin smile while his shoulders stay tense. "
    "Light: the warm lamp light now rakes across his cheek from the left and glints on the wet wall. "
    "Sound: the traffic fades under a low night wind as the dolly settles on his face.\n"
    "\noverall_soundscape: Distant traffic and footsteps on wet asphalt.\n"
    "\nnon_diegetic_music: None."
)


def compiled_segment(**overrides):
    seg = remix_segment()
    seg["h3_prompt"] = REMIX_PROMPT
    seg["metadata"]["frames"] = FRAMES
    seg["metadata"]["aspect_ratio"] = "16:9"
    seg["metadata"]["compiled_prompt_sha256"] = prompt_authoring.prompt_fingerprint(REMIX_PROMPT)
    seg["segment_end_state"] = {"planned_final_state": {"hero": "standing by the door"}}
    seg.update(overrides)
    return seg


class _StudioHandler(BaseHTTPRequestHandler):
    requests: list = []
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

    def _record(self, body: bytes):
        parsed = {}
        try:
            parsed = json.loads(body.decode("utf-8")) if body else {}
        except (UnicodeDecodeError, json.JSONDecodeError):
            parsed = {}
        _StudioHandler.requests.append({"method": self.command, "path": self.path, "body": parsed})

    def do_GET(self):
        self._record(b"")
        if "/jobs/J1?wait=" in self.path:
            self._send(200, {"job": {"id": "J1", "status": "succeeded",
                                     "result": {"video": {"meta": {"frames": FRAMES, "duration": 7.291},
                                                          "url": "/file"}}}})
            return
        if self.path.rstrip("/").endswith("/jobs/J1/file"):
            self._send(200, self.video_bytes, "video/mp4")
            return
        if self.path.rstrip("/").endswith("/jobs/J1/identity"):
            self._send(200, {"identity": {"status": "ok"}})
            return
        if self.path.rstrip("/").endswith("/projects"):
            self._send(200, {"projects": [{"id": 1, "name": "測試專案"}]})
            return
        self._send(404, {"error": "not found"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        self._record(self.rfile.read(length) if length else b"")
        if self.path.rstrip("/").endswith("/jobs"):
            self._send(200, {"job": {"id": "J1", "status": "queued", "warning": ""}})
            return
        self._send(404, {"error": "not found"})


class StudioTestBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _StudioHandler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
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
        _StudioHandler.requests = []
        self.root = Path(tempfile.mkdtemp(dir=ROOT))
        self.addCleanup(lambda: shutil.rmtree(self.root, ignore_errors=True))

    def write_segments(self, segments):
        path = self.root / "segments-ep01.json"
        path.write_text(json.dumps({"segments": segments}, ensure_ascii=False), encoding="utf-8")
        return path

    def base_args(self, extra=None):
        return ["--segments", str(self.root / "segments-ep01.json"), "--root-dir", str(self.root),
                "--project", "測試專案", "--api-url", self.api, "--token-file", str(self.token_file),
                "--mode", "pika768"] + (extra or [])


class SubmitRemixTests(StudioTestBase):
    @mock.patch.object(sr, "verify_stage5_gate", return_value=True)
    def test_submit_posts_expected_body_and_ledger(self, _gate):
        path = self.write_segments([compiled_segment()])
        code = sr.main(self.base_args())
        self.assertEqual(code, 0)
        posts = [r for r in _StudioHandler.requests if r["method"] == "POST" and r["path"].endswith("/jobs")]
        self.assertEqual(len(posts), 1)
        body = posts[0]["body"]
        self.assertEqual(body["prompt"], REMIX_PROMPT)
        self.assertEqual(body["refmods"], ["demo_scene_room", "demo_hero", "demo_friend"])
        self.assertAlmostEqual(body["seconds"], FRAMES / 24, places=6)
        self.assertEqual(body["aspect"], "16:9")
        self.assertEqual(body["mode"], "pika768")
        self.assertEqual(body["shot"], "EP01-S01-a")
        self.assertEqual(body["project"], "測試專案")
        self.assertEqual(body["plan"]["title_zh"], "EP01-S01-a")
        self.assertIn("standing by the door", body["plan"]["end_state"])
        ledger = json.loads((self.root / "videos" / "remix-jobs.json").read_text(encoding="utf-8"))
        entry = ledger["jobs"][0]
        self.assertEqual(entry["segment_id"], "EP01-S01-a")
        self.assertEqual(entry["frames_requested"], FRAMES)
        self.assertEqual(entry["status"], "queued")

    def test_dry_run_posts_nothing(self):
        self.write_segments([compiled_segment()])
        code = sr.main(self.base_args(["--dry-run", "--skip-stage-gate"]))
        self.assertEqual(code, 0)
        self.assertFalse([r for r in _StudioHandler.requests if r["method"] == "POST"])
        self.assertFalse((self.root / "videos" / "remix-jobs.json").exists())

    def test_refuses_ref2va_segments(self):
        seg = compiled_segment()
        seg.pop("refmods")
        seg["metadata"].pop("video_backend")
        self.write_segments([seg])
        with mock.patch.object(sr, "verify_stage5_gate", return_value=True):
            code = sr.main(self.base_args())
        self.assertEqual(code, 1)
        self.assertFalse([r for r in _StudioHandler.requests if r["method"] == "POST"])

    def test_fingerprint_mismatch_blocks(self):
        seg = compiled_segment()
        seg["h3_prompt"] = REMIX_PROMPT.replace("Hero", "Hero ")
        self.write_segments([seg])
        with mock.patch.object(sr, "verify_stage5_gate", return_value=True):
            code = sr.main(self.base_args())
        self.assertEqual(code, 1)
        self.assertFalse([r for r in _StudioHandler.requests if r["method"] == "POST"])

    def test_decided_remix_mode_is_read(self):
        (self.root / "decisions.json").write_text(json.dumps(
            {"decisions": [{"id": "remix_mode", "value": "pika480"}]}, ensure_ascii=False), encoding="utf-8")
        self.assertEqual(sr._decided_remix_mode(self.root), "pika480")
        self.assertIsNone(sr._decided_remix_mode(self.root / "nowhere"))


@unittest.skipUnless(FFMPEG, "需要 ffmpeg 產生測試影片")
class CollectRemixTests(StudioTestBase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        video = Path(tempfile.mkdtemp()) / "source.mp4"
        subprocess.run(
            [FFMPEG, "-y", "-loglevel", "error", "-f", "lavfi",
             "-i", f"color=c=gray:s=320x180:d={FRAMES / 24:.4f}:r=24",
             "-pix_fmt", "yuv420p", str(video)],
            check=True,
        )
        _StudioHandler.video_bytes = video.read_bytes()

    def test_collect_downloads_records_frames_and_identity(self):
        ledger_path = self.root / "videos" / "remix-jobs.json"
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        ledger_path.write_text(json.dumps({
            "api_scope": self.api, "studio_project": "測試專案",
            "jobs": [{"id": "J1", "segment_id": "EP01-S01-a", "status": "queued",
                      "frames_requested": FRAMES, "seconds": FRAMES / 24, "mode": "pika768"}],
        }, ensure_ascii=False), encoding="utf-8")
        code = sr.main(self.base_args(["--collect"]))
        self.assertEqual(code, 0)
        self.assertTrue((self.root / "videos" / "EP01-S01-a.mp4").exists())
        entry = json.loads(ledger_path.read_text(encoding="utf-8"))["jobs"][0]
        self.assertEqual(entry["status"], "downloaded")
        self.assertEqual(entry["frames_actual"], FRAMES)
        self.assertEqual(entry["identity"], "ok")
        self.assertGreater(entry["duration_actual"], 6.0)


if __name__ == "__main__":
    unittest.main()
