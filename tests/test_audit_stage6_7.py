"""階段 6–7＋h3d 基礎設施體檢（fix/audit-stage6-7）的回歸測試。

每個測試對應一個實際跑出來的問題：送件／收件／續跑的狀態機漏洞、寫死的家機路徑與位址、
路徑含 `'` 的組裝失敗、本機服務被系統代理攔截等。FreeVideo 一律用本機假伺服器或 monkeypatch。
"""
import contextlib
import importlib
import io
import json
import os
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
for extra in (ROOT / "scripts", ROOT / "scripts" / "storyboard"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from scripts.storyboard import submit_h3_segments as submit  # noqa: E402
from scripts.storyboard import assemble_episode as assemble  # noqa: E402
from scripts.storyboard import verify_video_shot as verify  # noqa: E402
from scripts.storyboard import tts_engine  # noqa: E402
from scripts.storyboard import media_tools  # noqa: E402
from scripts import doctor  # noqa: E402
from scripts import next_step  # noqa: E402
from scripts import sync_h3_reference  # noqa: E402
from scripts import h3d  # noqa: E402

FFMPEG = shutil.which("ffmpeg")
FRAMES = 124


def make_video(path: Path, frames: int, audio: bool = False) -> Path:
    cmd = [FFMPEG, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=160x90:rate=24"]
    if audio:
        cmd += ["-f", "lavfi", "-i", "sine=f=440:sample_rate=48000", "-af", "volume=0.05", "-shortest",
                "-c:a", "aac"]
    cmd += ["-frames:v", str(frames), "-pix_fmt", "yuv420p", str(path)]
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(cmd, check=True)
    return path


class _FakeFreeVideo(BaseHTTPRequestHandler):
    """最小 FreeVideo：POST /jobs 建工作、GET /jobs/<id> 第一次就成功、/library/<id>.mp4 回影片。"""
    jobs: dict = {}
    counter = [0]
    video_for: dict = {}  # label -> bytes
    status_for: dict = {}  # label -> forced status

    def log_message(self, *args):
        pass

    def _send(self, code, payload, ctype="application/json"):
        body = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        if self.path.endswith("/jobs"):
            self.counter[0] += 1
            jid = f"J{self.counter[0]}"
            self.jobs[jid] = {"label": body.get("label"), "seconds": body.get("seconds")}
            return self._send(200, {"job": {"id": jid, "status": "waiting", "label": body.get("label")}})
        if self.path.endswith("/cancel"):
            return self._send(200, {"ok": True})
        return self._send(404, {})

    def do_GET(self):
        if "/jobs/" in self.path:
            jid = self.path.split("/jobs/")[1].split("?")[0]
            job = self.jobs.get(jid)
            if job is None:
                return self._send(404, {"error": "no job"})
            status = self.status_for.get(job["label"], "succeeded")
            payload = {"id": jid, "status": status, "label": job["label"]}
            if status == "succeeded":
                payload["plan"] = {"geometry": {"frames": round(job["seconds"] * 24)}}
                payload["result"] = {"video": {"url": f"/freevideo/agent/v1/library/{jid}.mp4"}}
            return self._send(200, {"job": payload})
        if "/library/" in self.path:
            jid = self.path.rsplit("/", 1)[1].split(".")[0]
            return self._send(200, self.video_for.get(self.jobs[jid]["label"], b""), "video/mp4")
        return self._send(404, {})


@unittest.skipUnless(FFMPEG, "需要 ffmpeg 產生測試影片")
class SubmitResumeStateMachineTests(unittest.TestCase):
    """送件 → 漂移 → resume → 明確重送 → 冪等，全程走真 HTTP（本機假伺服器）。"""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(dir=ROOT))
        cls.good = make_video(cls.tmp / "good.mp4", FRAMES).read_bytes()
        cls.bad = make_video(cls.tmp / "bad.mp4", 100).read_bytes()
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _FakeFreeVideo)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.api = f"http://127.0.0.1:{cls.server.server_address[1]}/freevideo/agent/v1"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        _FakeFreeVideo.jobs.clear()
        _FakeFreeVideo.status_for.clear()
        _FakeFreeVideo.video_for.clear()
        # 中文＋空白路徑：專案根、輸出都在裡面
        self.root = Path(tempfile.mkdtemp(dir=self.tmp)) / "專案 測試"
        self.root.mkdir()
        self.segments = self.root / "segments-ep01.json"
        self.segments.write_text(json.dumps({"segments": [
            {"segment_id": f"EP01-S01-{c}", "label": f"EP01-S01-{c}", "h3_prompt": "x",
             "metadata": {"frames": FRAMES, "aspect_ratio": "16:9"}} for c in "abc"
        ]}), encoding="utf-8")
        for c in "abc":
            _FakeFreeVideo.video_for[f"EP01-S01-{c}"] = self.good

    def run_submit(self, *extra, cwd_relative=False):
        args = ["--segments", str(self.segments), "--root-dir", str(self.root),
                "--api-url", self.api, "--poll-timeout", "20", *extra]
        out = io.StringIO()
        with mock.patch.object(submit, "find_token", return_value="t"), \
             mock.patch.object(submit, "verify_stage5_gate", return_value=True), \
             mock.patch.object(submit, "audit_segment_prompts", return_value=(True, [])), \
             mock.patch.object(submit, "get_gpu_vram", return_value=None), \
             mock.patch.object(submit.time, "sleep"), \
             contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = submit.main(args)
        return code, out.getvalue()

    def files(self):
        return sorted(p.name for p in (self.root / "videos").iterdir())

    def test_output_dir_defaults_to_root_videos_not_cwd(self):
        code, _ = self.run_submit("--segment-id", "EP01-S01-a")
        self.assertEqual(code, 0)
        self.assertIn("EP01-S01-a.mp4", self.files())
        self.assertFalse((Path.cwd() / "videos" / "EP01-S01-a.mp4").exists())

    def test_drift_blocks_resume_without_suggesting_force(self):
        _FakeFreeVideo.video_for["EP01-S01-a"] = self.bad
        code, _ = self.run_submit("--segment-id", "EP01-S01-a")
        self.assertEqual(code, 1)
        self.assertIn("EP01-S01-a.drift.mp4", self.files())
        code, out = self.run_submit("--resume")
        self.assertEqual(code, 1)
        self.assertIn("drift 1", out)  # 舊版摘要顯示 drift 0
        self.assertIn("--resume-past-failures", out)
        self.assertNotIn("可加 --force 強制續跑", out)
        self.assertNotIn("EP01-S01-b.mp4", self.files())

    def test_resume_past_failures_skips_drift_and_explicit_resubmit_fixes_it(self):
        _FakeFreeVideo.video_for["EP01-S01-a"] = self.bad
        self.run_submit("--segment-id", "EP01-S01-a")
        _FakeFreeVideo.video_for["EP01-S01-a"] = self.good
        code, out = self.run_submit("--resume", "--resume-past-failures")
        self.assertEqual(code, 0, out)
        self.assertIn("不自動重送漂移段", out)
        self.assertEqual(self.files(), ["EP01-S01-a.drift.mp4", "EP01-S01-b.mp4", "EP01-S01-c.mp4",
                                        "_fv-job-ledger.json"])
        code, out = self.run_submit("--segment-id", "EP01-S01-a")
        self.assertEqual(code, 0, out)
        self.assertIn("EP01-S01-a.mp4", self.files())
        posts_before = _FakeFreeVideo.counter[0]
        code, out = self.run_submit("--resume")  # 冪等：全部有片，不再送任何件
        self.assertEqual(code, 0, out)
        self.assertEqual(_FakeFreeVideo.counter[0], posts_before)

    def test_resume_past_failures_requires_resume(self):
        with self.assertRaises(SystemExit):
            self.run_submit("--resume-past-failures")

    def test_timeout_is_reported_as_waiting_not_failure_and_collect_recovers(self):
        _FakeFreeVideo.status_for["EP01-S01-a"] = "running"
        code, out = self.run_submit("--segment-id", "EP01-S01-a", "--poll-timeout", "1")
        self.assertEqual(code, 1)
        self.assertIn("本機停止等待", out)
        self.assertNotIn("任務失敗: timeout", out)
        _FakeFreeVideo.status_for.clear()
        code, out = self.run_submit("--collect")
        self.assertEqual(code, 0, out)
        self.assertIn("EP01-S01-a.mp4", self.files())

    def test_collect_refreshes_active_entry_when_file_already_exists(self):
        ledger = self.root / "videos" / "_fv-job-ledger.json"
        submit.record_job(ledger, project=str(self.root), api_scope=self.api, batch_id="b",
                          segment_id="EP01-S01-a", job_id="J9", status="running", frames=FRAMES)
        _FakeFreeVideo.jobs["J9"] = {"label": "EP01-S01-a", "seconds": FRAMES / 24}
        (self.root / "videos" / "EP01-S01-a.mp4").write_bytes(self.good)
        code, out = self.run_submit("--collect")
        self.assertEqual(code, 0, out)
        entry = json.loads(ledger.read_text(encoding="utf-8"))["jobs"][-1]
        self.assertEqual(entry["status"], "succeeded_file_exists")
        self.assertEqual(next_step._active_jobs(self.root), [])

    def test_relative_segments_resolve_against_root_dir(self):
        args = ["--segments", "segments-ep01.json", "--root-dir", str(self.root), "--api-url", self.api,
                "--segment-id", "EP01-S01-a", "--dry-run", "--skip-stage-gate"]
        out = io.StringIO()
        old = os.getcwd()
        os.chdir(self.tmp)  # 目前目錄沒有這個分段檔，應改以 --root-dir 解析
        try:
            with mock.patch.object(submit, "audit_segment_prompts", return_value=(True, [])), \
                 mock.patch.object(submit, "get_gpu_vram", return_value=None), \
                 contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
                code = submit.main(args)
        finally:
            os.chdir(old)
        self.assertEqual(code, 0, out.getvalue())


class LedgerLatestEntryTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(dir=ROOT))
        self.ledger = self.root / "videos" / "_fv-job-ledger.json"

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def write(self, jobs):
        self.ledger.parent.mkdir(parents=True, exist_ok=True)
        self.ledger.write_text(json.dumps({"project": str(self.root), "api_scope": "x", "jobs": jobs}),
                               encoding="utf-8")

    def test_superseded_running_job_does_not_block(self):
        self.write([{"id": "J1", "segment_id": "S-a", "status": "running"},
                    {"id": "J2", "segment_id": "S-a", "status": "downloaded"}])
        self.assertIsNone(submit.active_job_for(self.ledger, "S-a"))
        self.assertEqual(next_step._active_jobs(self.root), [])

    def test_active_job_display_uses_ledger_id_field(self):
        self.write([{"id": "J7", "segment_id": "S-b", "status": "waiting"}])
        active = next_step._active_jobs(self.root)
        self.assertEqual(len(active), 1)
        self.assertIn("J7", active[0])
        self.assertNotIn("?", active[0])

    def test_stage6_next_stops_on_drift_instead_of_pointing_to_resume(self):
        (self.root / "segments-ep01.json").write_text(json.dumps(
            {"segments": [{"segment_id": "S-a"}, {"segment_id": "S-b"}]}), encoding="utf-8")
        self.write([{"id": "J1", "segment_id": "S-a", "status": "duration_drift"}])
        res = next_step._result(self.root, 6, "draft")
        out = next_step._stage6_work(res, self.root)
        self.assertIsNotNone(out)
        self.assertIsNone(out["next_command"])
        self.assertIn("duration_drift", out["action"])
        self.assertIn("--segment-id S-a", out["action"])

    def test_status_ledger_counts_latest_only(self):
        self.write([{"id": "J1", "segment_id": "S-a", "status": "running"},
                    {"id": "J2", "segment_id": "S-a", "status": "downloaded"}])
        lines = h3d._ledger_summary(self.root)
        self.assertIn("downloaded=1", lines[0])
        self.assertNotIn("running", lines[0])
        self.assertIn("1 筆被重送取代", lines[0])


class TokenAndApiDefaultsTests(unittest.TestCase):
    def test_token_candidates_never_relative_without_explicit_file(self):
        with mock.patch.dict(os.environ, {"USERPROFILE": "", "FREEVIDEO_TOKEN_FILE": ""}):
            for candidate in submit.token_candidates():
                self.assertTrue(candidate.is_absolute(), candidate)

    def test_token_file_env_is_honoured(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as td:
            token = Path(td) / "tok"
            token.write_text("secret-x\n", encoding="utf-8")
            with mock.patch.dict(os.environ, {"FREEVIDEO_TOKEN": "", "FREEVIDEO_TOKEN_FILE": str(token)}):
                self.assertEqual(submit.find_token(), "secret-x")

    def test_api_url_env_overrides_default(self):
        name = submit.__name__
        try:
            with mock.patch.dict(os.environ, {"FREEVIDEO_API_URL": "http://10.0.0.5:9000/freevideo/agent/v1"}):
                module = importlib.reload(submit)
                self.assertEqual(module.DEFAULT_API_URL, "http://10.0.0.5:9000/freevideo/agent/v1")
        finally:
            os.environ.pop("FREEVIDEO_API_URL", None)
            importlib.reload(sys.modules[name])
        self.assertEqual(submit.DEFAULT_API_URL, submit.DEFAULT_API_URL_FALLBACK)


class H3dRoutingTests(unittest.TestCase):
    def captured(self, argv):
        seen = {}

        def fake_invoke(module, passthrough):
            seen["module"] = module.__name__
            seen["argv"] = list(passthrough)
            return 0

        err = io.StringIO()
        with mock.patch.object(h3d, "_invoke", side_effect=fake_invoke), contextlib.redirect_stderr(err):
            h3d.main(argv)
        return seen, err.getvalue()

    def test_root_maps_to_root_dir_for_submit_collect_resume(self):
        seen, _ = self.captured(["submit", "--root", "/p", "--segments", "s.json"])
        self.assertIn("--root-dir", seen["argv"])
        self.assertNotIn("--root", seen["argv"])
        seen, _ = self.captured(["--root", "/p", "resume", "--segments", "s.json"])
        self.assertEqual(seen["argv"][0], "--resume")
        self.assertEqual(seen["argv"][-2:], ["--root-dir", str(Path("/p"))])
        seen, _ = self.captured(["collect", "--root=/p"])
        self.assertTrue(any(a in ("--root-dir=/p", "--root-dir=" + str(Path("/p"))) for a in seen["argv"]), seen["argv"])

    def test_global_root_is_not_silently_ignored(self):
        _, err = self.captured(["--root", "/p", "assemble", "--segments", "s.json"])
        self.assertIn("沒有作用", err)

    def test_doctor_receives_root(self):
        seen, _ = self.captured(["--root", "/p", "doctor"])
        self.assertEqual(seen["argv"][-2:], ["--root", str(Path("/p"))])


class AssembleTests(unittest.TestCase):
    def test_expected_duration_prefers_frames(self):
        seg = {"segment_id": "S", "metadata": {"frames": 124, "target_duration_sec": 5.5}}
        self.assertAlmostEqual(assemble.expected_segment_duration(seg), 124 / 24.0)

    def test_default_output_follows_episode(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as td:
            seg = Path(td) / "segments-all.json"
            seg.write_text(json.dumps({"episode": "ep03", "segments": []}), encoding="utf-8")
            ns = mock.Mock(segments=seg, layer2_dir=None, timeline=None)
            self.assertEqual(assemble._default_episode_label(ns), "ep03")
            ns = mock.Mock(segments=Path(td) / "segments-ep07.json", layer2_dir=None, timeline=None)
            self.assertEqual(assemble._default_episode_label(ns), "ep07")
            ns = mock.Mock(segments=None, layer2_dir=None, timeline=None)
            self.assertEqual(assemble._default_episode_label(ns), "ep01")

    def test_concat_quote_escapes_apostrophe(self):
        self.assertTrue(assemble._concat_quote(Path("/tmp/Tom's/a.wav")).endswith("Tom'\\''s/a.wav'"))

    def test_escape_ffmpeg_path_two_levels(self):
        escaped = assemble.escape_ffmpeg_path(Path("/x/Tom's [1],a;b/c.srt"))
        self.assertIn("Tom\\\\\\'s", escaped)
        self.assertIn("\\[1\\]\\,a\\;b", escaped)

    @unittest.skipUnless(FFMPEG, "需要 ffmpeg")
    def test_full_assembly_in_path_with_apostrophe_space_and_cjk(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as td:
            project = Path(td) / "組裝 Tom's 劇"
            videos = project / "videos"
            for c in "ab":
                make_video(videos / f"EP02-S01-{c}.mp4", FRAMES, audio=True)
            segs = project / "segments-ep02.json"
            segs.write_text(json.dumps({"episode": "ep02", "segments": [
                {"segment_id": f"EP02-S01-{c}", "metadata": {"frames": FRAMES, "aspect_ratio": "16:9"},
                 "shots": [{"shot_id": "SH01", "start_time": 0.5, "end_time": 3.0,
                            "dialogue_and_audio": {"line_verbatim": "你好", "speaker": "C-a"}}]}
                for c in "ab"]}, ensure_ascii=False), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "h3d.py"), "assemble", "--segments", str(segs),
                 "--videos-dir", str(videos)],
                capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=str(project))
            self.assertEqual(result.returncode, 0, result.stdout[-1500:] + result.stderr[-800:])
            final = videos / "final-ep02.mp4"
            self.assertTrue(final.is_file())
            meter = subprocess.run([FFMPEG, "-hide_banner", "-i", str(final), "-af", "ebur128", "-f", "null", "-"],
                                   capture_output=True, text=True, encoding="utf-8", errors="replace")
            integrated = [line for line in meter.stderr.splitlines() if line.strip().startswith("I:")]
            self.assertTrue(integrated)
            lufs = float(integrated[-1].split()[1])
            self.assertAlmostEqual(lufs, -23.0, delta=1.0)  # EBU R128 預設目標

    def test_auto_tts_failure_keeps_backend_reason(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as td:
            fake = mock.Mock()
            fake.synthesize.return_value = {"ok": False, "reason": "voicestudio 未啟動"}
            with mock.patch.object(assemble, "tts_module", fake), \
                 mock.patch.object(assemble, "generate_edge_tts", return_value=False), \
                 mock.patch.object(assemble, "generate_sapi_tts", return_value=False):
                with self.assertRaises(RuntimeError) as ctx:
                    assemble.synthesize_speech("你好", Path(td) / "a.wav", engine="auto")
        self.assertIn("voicestudio 未啟動", str(ctx.exception))


@unittest.skipUnless(FFMPEG, "需要 ffmpeg")
class QaFramesTests(unittest.TestCase):
    def test_expected_duration_comes_from_frames_and_frame_match_is_recorded(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as td:
            good = make_video(Path(td) / "g.mp4", FRAMES)
            short = make_video(Path(td) / "s.mp4", 112)
            seg = {"segment_id": "S", "metadata": {"frames": FRAMES, "target_duration_sec": 5.5,
                                                    "aspect_ratio": "16:9"}}
            ok = verify.verify_single_segment(seg, good)
            self.assertAlmostEqual(ok["specs"]["expected_duration"], FRAMES / 24.0)
            self.assertTrue(ok["duration_check"]["frames_match"])
            self.assertEqual(ok["duration_check"]["expected_frames"], FRAMES)
            bad = verify.verify_single_segment(seg, short)
            self.assertFalse(bad["duration_check"]["frames_match"])
            self.assertEqual(bad["duration_check"]["measured_frames_approx"], 112)


class LocalServiceProxyTests(unittest.TestCase):
    def test_loopback_detection(self):
        self.assertTrue(tts_engine._is_loopback_url("http://127.0.0.1:8001/health"))
        self.assertTrue(tts_engine._is_loopback_url("http://localhost:8001"))
        self.assertTrue(tts_engine._is_loopback_url("http://[::1]:8001"))
        self.assertFalse(tts_engine._is_loopback_url("https://api.fish.audio/v1"))

    def test_loopback_request_bypasses_system_proxy(self):
        class Health(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                body = b'{"status":"ok","model_loaded":true}'
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        server = ThreadingHTTPServer(("127.0.0.1", 0), Health)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            dead_proxy = "http://127.0.0.1:9"  # discard port：走代理就會失敗
            env = {"http_proxy": dead_proxy, "HTTP_PROXY": dead_proxy, "no_proxy": "", "NO_PROXY": ""}
            with mock.patch.dict(os.environ, env):
                response = tts_engine._default_transport(
                    "GET", f"http://127.0.0.1:{server.server_address[1]}/health", timeout=3)
            self.assertEqual(response.status, 200)
        finally:
            server.shutdown()
            server.server_close()

    def test_omnivoice_hint_env(self):
        with mock.patch.dict(os.environ, {"AICD_OMNIVOICE_LAUNCHER": "/opt/omni/start.sh"}):
            self.assertIn("/opt/omni/start.sh", tts_engine._next_steps("voicestudio", {"available": False}))


class HardcodedPathTests(unittest.TestCase):
    def test_media_tools_env_override(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as td:
            ffmpeg = Path(td) / "ffmpeg"
            ffprobe = Path(td) / "ffprobe"
            ffmpeg.write_text("", encoding="utf-8")
            ffprobe.write_text("", encoding="utf-8")
            with mock.patch.dict(os.environ, {"AICD_FFMPEG": str(ffmpeg), "AICD_FFPROBE": ""}):
                self.assertEqual(media_tools.ffmpeg_bin(), str(ffmpeg))
                self.assertEqual(media_tools.ffprobe_bin(), str(ffprobe))  # 同目錄推得
        with mock.patch.dict(os.environ, {"AICD_FFMPEG": "", "AICD_FFPROBE": ""}):
            self.assertTrue(media_tools.ffmpeg_bin().lower().endswith(("ffmpeg", "ffmpeg.exe")))

    def test_doctor_service_endpoints_follow_env(self):
        env = {"FREEVIDEO_API_URL": "http://192.168.1.20:9189/freevideo/agent/v1",
               "COMFYUI_URL": "", "VOICESTUDIO_URL": "localhost:8101"}
        with mock.patch.dict(os.environ, env):
            endpoints = doctor.service_endpoints()
        self.assertEqual(endpoints["freevideo_8189"], ("192.168.1.20", 9189))
        self.assertEqual(endpoints["comfyui_8188"], ("127.0.0.1", 8188))
        self.assertEqual(endpoints["voicestudio_8001"], ("localhost", 8101))

    def test_sync_reference_upstream_env_and_sibling(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as td:
            with mock.patch.dict(os.environ, {"AICD_H3_UPSTREAM": td}):
                found, tried = sync_h3_reference.resolve_upstream(None)
            self.assertEqual(found, Path(td))
        with mock.patch.dict(os.environ, {"AICD_H3_UPSTREAM": ""}):
            candidates = sync_h3_reference.upstream_candidates()
        self.assertIn(sync_h3_reference.ROOT.parent / "h3-video-prompting", candidates)
        for candidate in candidates:
            self.assertTrue(candidate.is_absolute(), candidate)

    def test_sync_reference_missing_upstream_lists_tried_paths(self):
        err = io.StringIO()
        with mock.patch.dict(os.environ, {"AICD_H3_UPSTREAM": ""}), \
             mock.patch.object(sync_h3_reference, "upstream_candidates", return_value=[Path("/nonexistent/a")]), \
             contextlib.redirect_stderr(err):
            code = sync_h3_reference.main(["--check"])
        self.assertEqual(code, 2)
        self.assertIn(str(Path("/nonexistent/a")), err.getvalue())


if __name__ == "__main__":
    unittest.main()
