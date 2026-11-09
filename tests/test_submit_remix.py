"""PR-R7：REMIX Studio 送件 adapter（submit_remix.py）。

用本機假 REMIX server 驗證「網路層＋送件 body＋帳本＋下載＋identity」；
stage-5 門禁本身是共用程式（submit_h3_segments.verify_stage5_gate，另有測試），
這裡用 mock 放行，只測 adapter 自己的邏輯。
"""
import argparse
import contextlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import threading
import time
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
        _StudioHandler.requests.append({
            "method": self.command, "path": self.path, "body": parsed,
            "authorization": self.headers.get("Authorization"),
        })

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

    def test_utf8_bom_segments_and_token_still_submit(self):
        raw = json.dumps({"segments": [compiled_segment()]}, ensure_ascii=False).encode("utf-8")
        (self.root / "segments-ep01.json").write_bytes(b"\xef\xbb\xbf" + raw)
        token = self.root / "bom.token"
        token.write_bytes(b"\xef\xbb\xbf" + b"test-token\r\n")
        with mock.patch.object(sr, "verify_stage5_gate", return_value=True):
            code = sr.main(self.base_args(["--token-file", str(token)]))
        self.assertEqual(code, 0)
        posts = [r for r in _StudioHandler.requests if r["method"] == "POST" and r["path"].endswith("/jobs")]
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0]["authorization"], "Bearer test-token")
        self.assertNotIn("\ufeff", posts[0]["authorization"])

    def test_bom_ledger_is_not_treated_as_empty(self):
        path = self.root / "videos" / "remix-jobs.json"
        path.parent.mkdir(parents=True)
        body = json.dumps({"jobs": [{"id": "J9", "segment_id": "EP01-S01-a", "status": "queued"}]})
        path.write_bytes(b"\xef\xbb\xbf" + body.encode("utf-8"))
        ledger = sr.load_ledger(path)
        self.assertEqual(ledger["jobs"][0]["id"], "J9")

    def test_token_with_non_latin1_is_refused_without_echoing_it(self):
        token = self.root / "bad.token"
        token.write_text("秘密令牌", encoding="utf-8")
        with self.assertRaises(SystemExit) as caught:
            sr.resolve_token(argparse.Namespace(token_file=str(token)))
        self.assertNotIn("秘密令牌", str(caught.exception))

    def test_connection_refused_exits_1_with_json_and_no_traceback(self):
        self.write_segments([compiled_segment()])
        err = io.StringIO()
        out = io.StringIO()
        with mock.patch.object(sr, "verify_stage5_gate", return_value=True), \
                contextlib.redirect_stderr(err), contextlib.redirect_stdout(out):
            code = sr.main(self.base_args([
                "--api-url", "http://127.0.0.1:1/remix/agent/v1", "--json"]))
        self.assertEqual(code, 1)
        self.assertNotIn("Traceback", err.getvalue())
        self.assertIn("無法連線", err.getvalue())
        payload = json.loads(out.getvalue())
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["exit_code"], 1)
        self.assertIn("無法連線", payload.get("error", ""))

    def test_http_200_without_job_id_is_not_success(self):
        self.write_segments([compiled_segment()])

        class _NoJob(_StudioHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length") or 0)
                self._record(self.rfile.read(length) if length else b"")
                self._send(200, {"ok": True})

        server = ThreadingHTTPServer(("127.0.0.1", 0), _NoJob)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.shutdown)
        self.addCleanup(server.server_close)
        api = f"http://127.0.0.1:{server.server_address[1]}/remix/agent/v1"
        before = len(_StudioHandler.requests)
        with mock.patch.object(sr, "verify_stage5_gate", return_value=True):
            code = sr.main(self.base_args(["--api-url", api]))
        self.assertEqual(code, 1)
        posts = [r for r in _StudioHandler.requests[before:] if r["method"] == "POST" and r["path"].endswith("/jobs")]
        self.assertEqual(len(posts), 1)
        ledger_path = self.root / "videos" / "remix-jobs.json"
        if ledger_path.exists():
            jobs = json.loads(ledger_path.read_text(encoding="utf-8")).get("jobs") or []
            self.assertFalse(any(item.get("id") in (None, "") for item in jobs))
        else:
            self.assertFalse(ledger_path.exists())


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
        code = sr.main(self.base_args(["--collect", "--report"]))
        self.assertEqual(code, 0)
        self.assertTrue((self.root / "videos" / "EP01-S01-a.mp4").exists())
        entry = json.loads(ledger_path.read_text(encoding="utf-8"))["jobs"][0]
        self.assertEqual(entry["status"], "downloaded")
        self.assertEqual(entry["frames_actual"], FRAMES)
        self.assertEqual(entry["identity"], "ok")
        self.assertGreater(entry["duration_actual"], 6.0)
        report = json.loads((self.root / "videos" / "remix-qa.json").read_text(encoding="utf-8"))
        row = report["segments"][0]
        self.assertEqual(row["segment_id"], "EP01-S01-a")
        self.assertEqual(row["frames_drift"], 0)
        self.assertEqual(row["identity"], "ok")

    def test_reroll_failed_only_resubmits_failed_entries(self):
        ledger_path = self.root / "videos" / "remix-jobs.json"
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        ledger_path.write_text(json.dumps({
            "api_scope": self.api, "studio_project": "測試專案",
            "jobs": [{"id": "J0", "segment_id": "EP01-S01-a", "status": "timeout",
                      "frames_requested": FRAMES, "mode": "pika768"}],
        }, ensure_ascii=False), encoding="utf-8")
        self.write_segments([compiled_segment()])
        with mock.patch.object(sr, "verify_stage5_gate", return_value=True):
            # 沒有 --reroll-failed：失敗段被跳過、不送
            code = sr.main(self.base_args())
            self.assertEqual(code, 1)
            posts = [r for r in _StudioHandler.requests if r["method"] == "POST" and r["path"].endswith("/jobs")]
            self.assertEqual(posts, [])
            # --reroll-failed：失敗段重送
            _StudioHandler.requests.clear()
            code = sr.main(self.base_args(["--reroll-failed"]))
            self.assertEqual(code, 0)
            posts = [r for r in _StudioHandler.requests if r["method"] == "POST" and r["path"].endswith("/jobs")]
            self.assertEqual(len(posts), 1)


class PollBehaviorTests(unittest.TestCase):
    def _serve(self, handler):
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.shutdown)
        self.addCleanup(server.server_close)
        return f"http://127.0.0.1:{server.server_address[1]}/remix/agent/v1", server

    def test_http_404_fails_without_the_25_second_sleep(self):
        class _Missing(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                body = b'{"error":"missing"}'
                self.send_response(404)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        api, _server = self._serve(_Missing)
        started = time.perf_counter()
        state, job = sr._poll_job(api, "t", "NOPE", timeout_s=5)
        elapsed = time.perf_counter() - started
        self.assertEqual(state, "failed")
        self.assertIn("missing", str((job or {}).get("error")))
        self.assertLess(elapsed, 2.0, "404 不該再空等 POLL_WAIT_SECONDS（25 秒）")

    def test_immediate_queued_does_not_busy_loop(self):
        class _Queued(BaseHTTPRequestHandler):
            hits = 0

            def log_message(self, *args):
                pass

            def do_GET(self):
                type(self).hits += 1
                body = json.dumps({"job": {"id": "J", "status": "queued"}}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        _Queued.hits = 0
        api, _server = self._serve(_Queued)
        state, _job = sr._poll_job(api, "t", "J", timeout_s=0.4)
        self.assertEqual(state, "timeout")
        self.assertLessEqual(_Queued.hits, 3, f"0.4 秒內打了 {_Queued.hits} 次，空轉沒有退避")

    def test_long_poll_is_not_followed_by_another_full_wait(self):
        class _Slow(BaseHTTPRequestHandler):
            hits = 0

            def log_message(self, *args):
                pass

            def do_GET(self):
                type(self).hits += 1
                time.sleep(1.0)
                body = json.dumps({"job": {"id": "J", "status": "queued"}}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        _Slow.hits = 0
        api, _server = self._serve(_Slow)
        started = time.perf_counter()
        sr._poll_job(api, "t", "J", timeout_s=1.5)
        elapsed = time.perf_counter() - started
        # 回應本身花了 1 秒就不該再把剩餘時間睡滿；否則 1.5 秒上限裡只打得成 1 次。
        self.assertGreaterEqual(_Slow.hits, 2)
        self.assertLess(elapsed, 2.8)


if __name__ == "__main__":
    unittest.main()
