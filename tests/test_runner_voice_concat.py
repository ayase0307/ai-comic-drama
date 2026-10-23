"""runner（單例鎖、佇列、暫停續跑、進度檔）、送件前 probe、階段 7 voice align、Concat adapter。"""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
for extra in (SCRIPTS, SCRIPTS / "storyboard", SCRIPTS / "runner", SCRIPTS / "voice", SCRIPTS / "edit"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

import concat_adapter  # noqa: E402
import fv_probe  # noqa: E402
import fv_runner  # noqa: E402
import h3d  # noqa: E402
import runner_lock  # noqa: E402
import submit_h3_segments as S  # noqa: E402
import voice_align  # noqa: E402


def _tmpdir(test):
    (ROOT / "tmp").mkdir(exist_ok=True)
    tmp = tempfile.TemporaryDirectory(dir=ROOT / "tmp")
    test.addCleanup(tmp.cleanup)
    return Path(tmp.name)


class FakeApi:
    """模擬 FreeVideo：每段送件後輪詢一次就成功；可設定佇列忙碌、失敗、LoRA 清單。"""
    api = "http://fake/v1"

    def __init__(self, *, busy_polls=0, fail_codes=(), loras=None, frames_override=None):
        self.busy_polls = busy_polls
        self.fail_codes = list(fail_codes)
        self.loras = loras if loras is not None else []
        self.frames_override = frames_override
        self.submitted, self.cancelled, self.jobs = [], [], {}
        self.queue_calls = 0

    def queue(self):
        self.queue_calls += 1
        return {"pending": 1 if self.queue_calls <= self.busy_polls else 0, "running": 0}

    def root_info(self):
        return {"loras": self.loras}

    def upload(self, path):
        return f"file-{Path(path).name}"

    def submit(self, body):
        self.submitted.append(body)
        jid = f"J{len(self.submitted)}"
        self.jobs[jid] = body
        return {"job": {"id": jid, "status": "waiting"}}

    def poll(self, jid):
        body = self.jobs[jid]
        frames = self.frames_override or round(body["seconds"] * 24)
        if self.fail_codes:
            code = self.fail_codes.pop(0)
            return {"job": {"id": jid, "status": "failed", "error": {"code": code, "retryable": False}}}
        return {"job": {"id": jid, "status": "succeeded", "spec": {"frames": frames},
                        "result": {"video": {"url": f"/files/{jid}.mp4"}}}}

    def resume(self, jid, ref):
        return {"job": {"id": jid, "status": "running"}}

    def cancel(self, jid):
        self.cancelled.append(jid)
        return {}

    def download(self, url, out):
        Path(out).write_bytes(b"mp4")

    def probe_duration(self, path):
        return None


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.root = _tmpdir(self)
        (self.root / "images").mkdir()
        (self.root / "images" / "a.png").write_bytes(b"png")
        segs = [{"segment_id": f"EP01-S0{i}", "h3_prompt": "p", "reference_images": [{"path": "images/a.png"}],
                 "metadata": {"frames": 158, "aspect_ratio": "16:9"}} for i in (1, 2, 3)]
        segs[1]["h3_loras"] = [{"name": "camera_motion", "strength": 0.6, "trigger": "x", "reason": "y"}]
        (self.root / "segments-ep01.json").write_text(json.dumps({"segments": segs}), encoding="utf-8")
        self.plan = [{"key": s["segment_id"], "segments": "segments-ep01.json", "segment_id": s["segment_id"],
                      "out": f"videos/{s['segment_id']}.mp4"} for s in segs]
        self.progress = self.root / "videos" / "_runner-progress.json"

    def runner(self, api, **kw):
        kw.setdefault("skip_audit", True)
        return fv_runner.Runner(self.root, self.plan, api, progress=self.progress, sleep=lambda s: None,
                                log=lambda m: None, queue_poll=30, **kw)

    def test_runs_all_and_writes_progress_and_ledger(self):
        api = FakeApi(loras=["camera_motion"])
        self.assertEqual(self.runner(api).run(), fv_runner.RC_DONE)
        prog = json.loads(self.progress.read_text(encoding="utf-8"))
        self.assertEqual(prog["runner_state"], "done")
        self.assertEqual({r["status"] for r in prog["segments"].values()}, {"downloaded"})
        ledger = json.loads((self.root / "videos" / "_fv-job-ledger.json").read_text(encoding="utf-8"))
        self.assertEqual(len(ledger["jobs"]), 3)
        self.assertEqual(api.submitted[1]["loras"], [{"name": "camera_motion", "strength": 0.6}],
                         "loras 只送 name＋strength")

    def test_resume_skips_existing_outputs(self):
        (self.root / "videos").mkdir()
        (self.root / "videos" / "EP01-S01.mp4").write_bytes(b"done")
        api = FakeApi(loras=["camera_motion"])
        self.runner(api).run()
        self.assertEqual(len(api.submitted), 2)

    def test_pause_file_stops_before_next_segment(self):
        api = FakeApi(loras=["camera_motion"])
        r = self.runner(api)
        original = api.download

        def download_then_pause(url, out):
            original(url, out)
            r.prog.pause_file.write_text("x", encoding="utf-8")
        api.download = download_then_pause
        self.assertEqual(r.run(), fv_runner.RC_PAUSED)
        self.assertEqual(len(api.submitted), 1)
        self.assertEqual(json.loads(self.progress.read_text(encoding="utf-8"))["runner_state"], "paused_by_user")
        r.prog.pause_file.unlink()
        api2 = FakeApi(loras=["camera_motion"])
        self.assertEqual(self.runner(api2).run(), fv_runner.RC_DONE)
        self.assertEqual(len(api2.submitted), 2, "續跑只送剩下的段")

    def test_busy_queue_waits_then_stops(self):
        api = FakeApi(busy_polls=99, loras=["camera_motion"])
        self.assertEqual(self.runner(api, blocked_wait=60).run(), fv_runner.RC_BLOCKED)
        self.assertEqual(api.submitted, [])
        api = FakeApi(busy_polls=1, loras=["camera_motion"])
        self.assertEqual(self.runner(api, blocked_wait=60).run(), fv_runner.RC_DONE)

    def test_missing_lora_blocks_before_any_submit(self):
        api = FakeApi(loras=["Bunny_weapon_combatV1"])
        self.assertEqual(self.runner(api).run(), fv_runner.RC_PROBE)
        self.assertEqual(api.submitted, [])
        prog = json.loads(self.progress.read_text(encoding="utf-8"))
        self.assertEqual(prog["probe_errors"][0]["lora"], "camera_motion")

    def test_repeated_failure_stops(self):
        api = FakeApi(fail_codes=["bad_prompt", "bad_prompt"], loras=["camera_motion"])
        self.assertEqual(self.runner(api).run(), fv_runner.RC_REPEATED)

    def test_duration_drift_is_not_downloaded(self):
        api = FakeApi(frames_override=175, loras=["camera_motion"])
        self.runner(api).run()
        self.assertFalse((self.root / "videos" / "EP01-S01.mp4").exists())

    def test_cli_pause_status(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(fv_runner.main(["--root", str(self.root), "--pause"]), 0)
            self.assertEqual(fv_runner.main(["--root", str(self.root), "--status"]), 0)
        self.assertIn("已請求暫停", buf.getvalue())

    def test_lock_busy_returns_lock_code(self):
        lock = self.root / "lock.json"
        with patch.dict(os.environ, {"AICD_RUNNER_LOCK": str(lock), "FREEVIDEO_TOKEN": "t"}):
            lock.write_text(json.dumps({"pid": os.getppid() or 1, "host": __import__("socket").gethostname(),
                                        "plan": "other.json"}), encoding="utf-8")
            plan = self.root / "plan.json"
            plan.write_text(json.dumps(self.plan), encoding="utf-8")
            with patch.object(runner_lock, "list_processes", return_value=[]):
                self.assertEqual(fv_runner.main(["--root", str(self.root), "--plan", str(plan)]), fv_runner.RC_LOCK)


class LockTests(unittest.TestCase):
    def setUp(self):
        self.root = _tmpdir(self)
        self.path = self.root / "runner.lock"

    def test_acquire_release_and_stale_lock_reclaimed(self):
        self.path.write_text(json.dumps({"pid": 999999, "host": __import__("socket").gethostname()}))
        lock = runner_lock.RunnerLock(path=self.path, processes_fn=lambda: [], log=lambda m: None)
        with lock:
            self.assertEqual(json.loads(self.path.read_text())["pid"], os.getpid())
        self.assertFalse(self.path.exists())

    def test_external_runner_detected_and_waited(self):
        procs = [{"pid": 4242, "cmdline": "python fv_run_multi.py --plan plan.json"}]
        sleeps = []
        lock = runner_lock.RunnerLock(path=self.path, processes_fn=lambda: procs, wait_seconds=0,
                                      sleep=sleeps.append, log=lambda m: None)
        with self.assertRaises(runner_lock.RunnerBusy) as ctx:
            lock.acquire()
        self.assertIn("外部影片 runner", str(ctx.exception))
        calls = iter([procs, []])
        lock = runner_lock.RunnerLock(path=self.path, processes_fn=lambda: next(calls), wait_seconds=100,
                                      poll=1, sleep=sleeps.append, log=lambda m: None)
        lock.acquire()
        lock.release()
        self.assertTrue(sleeps)

    def test_status_and_dry_run_processes_are_not_runners(self):
        procs = [{"pid": 1, "cmdline": "python h3d.py run --status"},
                 {"pid": 2, "cmdline": "python submit_h3_segments.py --dry-run"}]
        self.assertEqual(runner_lock.external_runners(procs), [])


class ProbeTests(unittest.TestCase):
    def test_missing_lora_has_alternatives(self):
        segs = [{"segment_id": "EP04-S02-a", "h3_loras": [{"name": "H3_Combat_V2", "strength": 0.8, "trigger": "t"}]}]
        report = fv_probe.check(segs, ["Bunny_weapon_combatV1", "camera_motion_h3_lora_v1_3000_pruned"])
        self.assertFalse(report["ok"])
        self.assertIn("拿掉這個 LoRA", report["errors"][0]["alternatives"][0])
        self.assertTrue(any("trigger" in w for w in report["warnings"]))

    def test_installed_lora_list_shapes(self):
        self.assertEqual(fv_probe.installed_loras({"loras": ["a", {"name": "b"}]}), ["a", "b"])
        self.assertIsNone(fv_probe.installed_loras({}))

    def test_openapi_lora_fields(self):
        doc = {"components": {"schemas": {"JobSpec": {"properties": {"loras": {"items": {
            "type": "object", "properties": {"name": {}, "strength": {}}}}, "prompt": {}}}}}}
        spec = fv_probe.jobspec_from_openapi(doc)
        self.assertEqual(spec["lora_fields"], {"name", "strength"})

    def test_cli_offline(self):
        root = _tmpdir(self)
        seg = root / "segments-ep04.json"
        seg.write_text(json.dumps({"segments": [{"segment_id": "A", "h3_loras": [{"name": "X"}]}]}), encoding="utf-8")
        with redirect_stdout(io.StringIO()):
            self.assertEqual(h3d.main(["probe", "--segments", str(seg), "--installed", "Y,Z"]), 1)
            self.assertEqual(h3d.main(["probe", "--segments", str(seg), "--installed", "X"]), 0)

    def test_sanitize_loras(self):
        self.assertEqual(S.sanitize_loras([{"name": "a", "strength": "0.5", "reason": "r"}, "b", {}]),
                         [{"name": "a", "strength": 0.5}, "b"])


class VoiceAlignTests(unittest.TestCase):
    def lines(self):
        return {"EP01-S01": [{"text": "說出它，忘掉它。", "start": 2.5, "end": 5.0},
                             {"text": "我忘掉母親教我說的第一句話。", "start": 5.0, "end": 8.5}],
                "EP01-S02": [{"text": "師父？", "start": 0.0, "end": 1.0}]}

    def test_place_after_on_screen_line_and_mute_gibberish(self):
        manifest = {"EP01-S01-N1": {"segment": "EP01-S01", "line": "我忘掉母親教我說的第一句話。", "dur": 2.5}}
        asr = {"EP01-S01": [
            {"start": 2.9, "end": 6.3, "text": "說出它忘掉它", "words": [[2.9, 3.6, "說"], [3.6, 3.8, "出"], [3.8, 4.1, "它"],
                                                                     [5.4, 5.8, "忘"], [5.8, 6.0, "掉"], [6.0, 6.3, "它"]]},
            {"start": 6.5, "end": 8.0, "text": "啊吧啦", "words": [[6.5, 7.0, "啊"], [7.0, 7.5, "吧"], [7.5, 8.0, "啦"]]}]}
        placement, need = voice_align.place(manifest, self.lines(), asr, {"EP01-S01": 9.0, "EP01-S02": 3.0},
                                            ["EP01-S01", "EP01-S02"])
        item = placement["EP01-S01-N1"]
        self.assertGreaterEqual(item["start"], 6.3)
        self.assertEqual(item["mutes"], [[6.4, 8.15]])
        self.assertIn("亂語", item["note"])
        self.assertEqual(need, [])

    def test_merge_and_filters(self):
        self.assertEqual(voice_align.merge_intervals([[6.4, 6.91], [6.66, 7.19], [9, 10]]), [[6.4, 7.19], [9.0, 10.0]])
        self.assertEqual(voice_align.duck_filter([[1, 2]]), "volume=enable='between(t,1.00,2.00)':volume=-22dB")
        self.assertEqual(voice_align.duck_filter([]), "anull")
        self.assertEqual(voice_align.loudnorm_filter(-16, 1.1), "atempo=1.100,loudnorm=I=-16:TP=-1.5:LRA=11")

    def test_overrides(self):
        placement = {"a": {"segment": "S", "start": 1, "tempo": 1, "mutes": []},
                     "b": {"segment": "S", "start": 3, "tempo": 1, "mutes": []}}
        voice_align.apply_overrides(placement, {"a": {"start": 1.5, "mutes": [[2, 3]]}})
        self.assertEqual(placement["a"]["start"], 1.5)
        self.assertEqual(placement["b"]["mutes"], [[2, 3]])

    @unittest.skipUnless(shutil.which("ffmpeg"), "需要 ffmpeg")
    def test_duck_and_loudnorm_with_ffmpeg(self):
        root = _tmpdir(self)
        src = root / "in.mp4"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=64x36:d=2", "-f", "lavfi",
                        "-i", "sine=f=440:d=2", "-shortest", "-c:v", "libx264", "-c:a", "aac", str(src)], check=True)
        voice_align.duck_video(src, root / "out.mp4", [[0.5, 1.0]])
        self.assertTrue((root / "out.mp4").stat().st_size > 0)
        wav = root / "vo.wav"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=f=300:d=1", str(wav)], check=True)
        voice_align.loudnorm_audio(wav, root / "vo-final.wav", -16, 1.1)
        self.assertTrue((root / "vo-final.wav").is_file())


class FakeMcp:
    def __init__(self):
        self.calls = []

    def call(self, tool, **args):
        self.calls.append((tool, args))
        return {"createdId": f"m{len(self.calls)}"} if tool == "media_import" else {}


class ConcatTests(unittest.TestCase):
    def plan(self):
        lines = {"EP01-S01": [{"text": "說出它。", "start": 0.5, "end": 1.5}, {"text": "我忘了。", "start": 2.0, "end": 3.0}],
                 "EP02-S01": [{"text": "走吧。", "start": 1.0, "end": 2.0}]}
        asr = {"EP01-S01": [{"start": 0.6, "end": 1.2, "text": "說出它", "words": [[0.6, 0.8, "說"], [0.8, 1.0, "出"], [1.0, 1.2, "它"]]}]}
        placement = {"EP01-S01-N1": {"segment": "EP01-S01", "start": 2.1, "tempo": 1.0, "final": "voice/final/EP01-S01-N1.wav",
                                     "final_dur": 1.2, "mutes": [[2.0, 3.0]]}}
        manifest = {"EP01-S01-N1": {"segment": "EP01-S01", "line": "我忘了。", "dur": 1.2}}
        return concat_adapter.build_plan(name="測試 全集粗剪", order=["EP01-S01", "EP02-S01"],
                                         durations={"EP01-S01": 4.0, "EP02-S01": 3.0}, lines=lines, asr=asr,
                                         placement=placement, manifest=manifest, muted={"EP01-S01"})

    def test_plan_tracks_captions_voices(self):
        plan = self.plan()
        self.assertEqual(plan["tracks"], {"video": "T1", "captions": "T2", "voice": "T3"})
        self.assertEqual(plan["segments"][0]["file"], "voice/muted/EP01-S01.mp4")
        self.assertEqual(plan["segments"][1]["file"], "videos/EP02-S01.mp4")
        self.assertEqual(plan["episode_starts"], {"EP01": 0.0, "EP02": 4.0})
        self.assertEqual(plan["voices"], [{"key": "EP01-S01-N1", "file": "voice/final/EP01-S01-N1.wav", "start": 2.1}])
        self.assertEqual(plan["stats"], {"asr_aligned": 1, "storyboard_time": 1, "voice": 1})
        self.assertEqual(plan["captions"][0]["start"], 0.5)
        self.assertEqual(plan["captions"][2]["start"], 5.0, "第二集字幕加上第一集長度")

    def test_build_calls_concat_tools_in_order(self):
        root = _tmpdir(self)
        mcp = FakeMcp()
        result = concat_adapter.build_project(self.plan(), location=root, media_root=root, client=mcp, log=lambda m: None)
        tools = [c[0] for c in mcp.calls]
        self.assertEqual(tools[0], "project_create")
        self.assertEqual(tools.count("media_import"), 3)
        self.assertIn("clips_add_sequence", tools)
        self.assertIn("captions_add", tools)
        clip = next(a for t, a in mcp.calls if t == "clip_add")
        self.assertEqual(clip["trackId"], "T3")
        self.assertEqual(tools[-3:], ["project_save", "timeline_read", "project_close"])
        self.assertEqual(result["voices"], 1)

    def test_existing_project_is_not_overwritten(self):
        root = _tmpdir(self)
        (root / "測試 全集粗剪").mkdir()
        (root / "測試 全集粗剪" / "concat.json").write_text("{}", encoding="utf-8")
        with self.assertRaises(FileExistsError):
            concat_adapter.build_project(self.plan(), location=root, media_root=root, client=FakeMcp())

    def test_mcp_client_against_fake_stdio_server(self):
        server = ROOT / "tests" / "fixtures" / "fake_concat_mcp.py"
        client = concat_adapter.McpClient([sys.executable, str(server)], timeout=30)
        try:
            client.initialize()
            self.assertEqual(client.call("media_import", path="p", file="f")["createdId"], "id-2")
            with self.assertRaises(RuntimeError):
                client.call("explode")
        finally:
            client.close()


if __name__ == "__main__":
    unittest.main()
