"""Offline security regressions for submit job ownership and transport."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from urllib.request import Request
from urllib.parse import urlparse

from scripts.storyboard import submit_h3_segments as submit


class SubmitJobSafetyTests(unittest.TestCase):
    def test_relative_download_uses_api_url_base_and_only_same_origin_bearer(self):
        observed = []

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def read(self):
                return b"video"

        class Opener:
            def open(self, request, timeout=None):
                observed.append(request)
                return Response()

        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as td:
            destination = Path(td) / "clip.mp4"
            with mock.patch.object(submit.urllib.request, "build_opener", return_value=Opener()):
                submit.download_file(
                    "secret-token", "https://media.example/freevideo/agent/v1",
                    "files/out.mp4", destination,
                )
            req = observed[-1]
            self.assertEqual(req.full_url, "https://media.example/freevideo/agent/v1/files/out.mp4")
            self.assertEqual(req.get_header("Authorization"), "Bearer secret-token")
            self.assertEqual(destination.read_bytes(), b"video")

    def test_cross_origin_download_never_receives_bearer_token(self):
        observed = []

        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self): return b"video"

        class Opener:
            def open(self, request, timeout=None):
                observed.append(request)
                return Response()

        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as td, mock.patch.object(
            submit.urllib.request, "build_opener", return_value=Opener()
        ):
            submit.download_file("secret-token", "https://media.example/freevideo/agent/v1",
                                 "https://cdn.example/out.mp4", Path(td) / "clip.mp4")
        self.assertIsNone(observed[0].get_header("Authorization"))

    def test_redirect_handler_keeps_auth_for_same_origin_redirect(self):
        handler = submit.SameOriginRedirectHandler()
        request = Request("https://media.example/v1/start", headers={"Authorization": "Bearer secret"})
        redirected = handler.redirect_request(
            request, None, 302, "Found", {}, "https://media.example/v1/files/result.mp4"
        )
        self.assertIsNotNone(redirected)
        self.assertEqual(redirected.get_header("Authorization"), "Bearer secret")

    def test_redirect_handler_drops_or_rejects_cross_origin_auth(self):
        handler = submit.SameOriginRedirectHandler()
        request = Request("https://media.example/v1/start", headers={"Authorization": "Bearer secret"})
        redirected = handler.redirect_request(
            request, None, 302, "Found", {}, "https://cdn.example/files/result.mp4"
        )
        self.assertTrue(
            redirected is None or redirected.get_header("Authorization") is None,
            "cross-origin redirects must be rejected or have Authorization stripped",
        )

    def test_api_requests_also_install_scoped_redirect_handler(self):
        installed = []

        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self): return b"{}"

        class Opener:
            def open(self, request, timeout=None): return Response()

        def build_opener(*handlers):
            installed.extend(handlers)
            return Opener()

        with mock.patch.object(submit.urllib.request, "build_opener", side_effect=build_opener):
            submit.call_api("https://media.example/freevideo/agent/v1", "secret", "GET", "/jobs")
        self.assertTrue(any(isinstance(handler, submit.SameOriginRedirectHandler) for handler in installed))

    def test_cancel_only_ids_recorded_in_local_ledger(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as td:
            ledger = Path(td) / "jobs.json"
            ledger.write_text(json.dumps({
                "project": str(Path(td).resolve()),
                "api_scope": "http://127.0.0.1:8189/freevideo/agent/v1",
                "jobs": [{"id": "owned-job", "batch_id": "batch-1"}],
            }), encoding="utf-8")
            calls = []

            def fake_api(api_url, token, method, path, body=None, timeout=600):
                calls.append((method, path))
                if method == "GET":
                    return {"jobs": [
                        {"id": "owned-job", "status": "running", "spec": {"ref": "seg-one"}},
                        {"id": "foreign-job", "status": "running", "spec": {"ref": "seg-foreign"}},
                    ]}
                return {}

            with mock.patch.object(submit, "call_api", side_effect=fake_api):
                submit.cancel_stale_jobs(
                    "http://127.0.0.1:8189/freevideo/agent/v1", "token", ledger_path=ledger
                )
            self.assertIn(("POST", "/jobs/owned-job/cancel"), calls)
            self.assertNotIn(("POST", "/jobs/foreign-job/cancel"), calls)

    def test_empty_or_missing_ledger_never_cancels_server_jobs(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as td:
            calls = []

            def fake_api(api_url, token, method, path, body=None, timeout=600):
                calls.append((method, path))
                return {"jobs": [{"id": "foreign", "status": "running", "spec": {"ref": "seg-x"}}]}

            with mock.patch.object(submit, "call_api", side_effect=fake_api):
                submit.cancel_stale_jobs(
                    "http://127.0.0.1:8189/freevideo/agent/v1", "token",
                    ledger_path=Path(td) / "missing-ledger.json",
                )
            self.assertFalse(any(method == "POST" for method, _ in calls))

    def test_reference_cache_is_scoped_to_api_url(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as td:
            root = Path(td)
            image = root / "ref.png"
            image.write_bytes(b"local-reference-image")
            cache_path = root / "cache.json"
            api_calls = []

            def fake_call_api(api_url, token, method, path, body=None, timeout=600):
                api_calls.append(api_url)
                return {"file": f"remote-{len(api_calls)}"}

            with mock.patch.object(submit, "call_api", side_effect=fake_call_api):
                cache = {}
                first = submit.upload_reference_image(
                    "https://api-a.example/freevideo/agent/v1", "token", image, cache, cache_path
                )
                # A cache populated by API A must not make API B reuse API A's file ID.
                second = submit.upload_reference_image(
                    "https://api-b.example/freevideo/agent/v1", "token", image, cache, cache_path
                )
            self.assertEqual(first, "remote-1")
            self.assertEqual(second, "remote-2")
            self.assertEqual(api_calls, [
                "https://api-a.example/freevideo/agent/v1",
                "https://api-b.example/freevideo/agent/v1",
            ])

    def test_poll_timeout_returns_failure_and_keeps_job_in_scoped_ledger(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as td:
            root = Path(td)
            segments = root / "segments-ep01.json"
            segments.write_text(json.dumps([{
                "segment_id": sid, "seconds": 4, "prompt": "offline prompt", "reference_images": [],
            } for sid in ("EP01-seg01", "EP01-seg02")]), encoding="utf-8")
            out_dir = root / "videos"
            calls = []

            def fake_api(api_url, token, method, path, body=None, timeout=600):
                calls.append((method, path))
                if method == "POST":
                    return {"job": {"id": "owned-timeout", "status": "waiting"}}
                return {"job": {"id": "owned-timeout", "status": "waiting"}}

            with mock.patch.object(submit, "find_token", return_value="local-test-token"), \
                 mock.patch.object(submit, "verify_stage5_gate", return_value=True), \
                 mock.patch.object(submit, "get_gpu_vram", return_value=None), \
                 mock.patch.object(submit, "audit_segment_prompts", return_value=(True, [])), \
                 mock.patch.object(submit, "call_api", side_effect=fake_api), \
                 mock.patch.object(submit.time, "sleep"), \
                 mock.patch.object(submit.time, "monotonic", side_effect=[0.0, 2.0]):
                result = submit.main([
                    "--segments", str(segments), "--output-dir", str(out_dir), "--root-dir", str(root),
                    "--api-url", "https://api.example/freevideo/agent/v1", "--poll-timeout", "1",
                ])
            ledger = json.loads((out_dir / "_fv-job-ledger.json").read_text(encoding="utf-8"))
            self.assertEqual(result, 1)
            self.assertEqual(ledger["project"], str(root.resolve()))
            self.assertEqual(ledger["api_scope"], "https://api.example/freevideo/agent/v1")
            self.assertEqual(ledger["jobs"][0]["id"], "owned-timeout")
            self.assertEqual(ledger["jobs"][0]["segment_id"], "EP01-seg01")
            self.assertEqual(ledger["jobs"][0]["status"], "timeout")
            self.assertFalse(any(path.endswith("/cancel") for _, path in calls))
            self.assertEqual(sum(method == "POST" and path == "/jobs" for method, path in calls), 1)

    def test_poll_interruption_stops_batch_and_preserves_job(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as td:
            root = Path(td)
            segments = root / "segments-ep01.json"
            segments.write_text(json.dumps([{
                "segment_id": sid, "seconds": 4, "prompt": "offline prompt", "reference_images": [],
            } for sid in ("EP01-seg01", "EP01-seg02")]), encoding="utf-8")
            out_dir = root / "videos"
            calls = []

            def fake_api(api_url, token, method, path, body=None, timeout=600):
                calls.append((method, path))
                if method == "POST":
                    return {"job": {"id": "owned-interrupted", "status": "waiting"}}
                return {"job": {"id": "owned-interrupted", "status": "waiting"}}

            with mock.patch.object(submit, "find_token", return_value="test-token"), \
                 mock.patch.object(submit, "verify_stage5_gate", return_value=True), \
                 mock.patch.object(submit, "get_gpu_vram", return_value=None), \
                 mock.patch.object(submit, "audit_segment_prompts", return_value=(True, [])), \
                 mock.patch.object(submit, "call_api", side_effect=fake_api), \
                 mock.patch.object(submit.time, "sleep", side_effect=KeyboardInterrupt), \
                 mock.patch.object(submit.time, "monotonic", return_value=0.0):
                result = submit.main([
                    "--segments", str(segments), "--output-dir", str(out_dir), "--root-dir", str(root),
                    "--api-url", "https://api.example/freevideo/agent/v1", "--poll-timeout", "30",
                ])
            ledger = json.loads((out_dir / "_fv-job-ledger.json").read_text(encoding="utf-8"))
            self.assertEqual(result, 1)
            self.assertEqual(ledger["jobs"][0]["id"], "owned-interrupted")
            self.assertEqual(ledger["jobs"][0]["status"], "interrupted")
            self.assertEqual(sum(method == "POST" and path == "/jobs" for method, path in calls), 1)
            self.assertFalse(any(path.endswith("/cancel") for _, path in calls))

    def test_cancel_does_not_use_ledger_from_different_api_scope(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as td:
            ledger_path = Path(td) / "jobs.json"
            ledger_path.write_text(json.dumps({
                "project": str(Path(td).resolve()),
                "api_scope": "https://api-a.example/v1",
                "jobs": [{"id": "owned"}],
            }), encoding="utf-8")
            with mock.patch.object(submit, "call_api") as call_api:
                submit.cancel_stale_jobs("https://api-b.example/v1", "token", ledger_path,
                                         Path(td))
            call_api.assert_not_called()

    def test_empty_prompt_fails_audit(self):
        passed, errors = submit.audit_segment_prompts([{"segment_id": "EP01-seg01", "seconds": 4}])
        self.assertFalse(passed)
        self.assertTrue(any("prompt" in error.lower() for error in errors))

    def test_missing_prompt_audit_dependency_fails_closed(self):
        with mock.patch.object(submit, "audit_refs_and_subjects", None), \
             mock.patch.object(submit, "lint_h3_prompt", None):
            passed, errors = submit.audit_segment_prompts([
                {"segment_id": "EP01-seg01", "prompt": "A valid nonempty prompt", "seconds": 4}
            ])
        self.assertFalse(passed)
        self.assertTrue(errors)


if __name__ == "__main__":
    unittest.main()


