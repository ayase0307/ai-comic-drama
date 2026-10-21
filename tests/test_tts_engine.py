import json
import math
import os
import struct
import sys
import tempfile
import unittest
import wave
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "storyboard"))

import tts_engine


def _wav_bytes(seconds=0.2, rate=16000):
    """產生一段真的 WAV 位元組（16-bit 單聲道），當作假供應商回應。"""
    frames = [struct.pack("<h", int(4000 * math.sin(2 * math.pi * 440 * n / rate)))
              for n in range(int(rate * seconds))]
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / "tone.wav"
        with wave.open(str(path), "wb") as stream:
            stream.setnchannels(1)
            stream.setsampwidth(2)
            stream.setframerate(rate)
            stream.writeframes(b"".join(frames))
        return path.read_bytes()


class _StubTransport:
    """假的 HTTP 傳輸層：記錄所有呼叫並回傳預設回應。"""

    def __init__(self, handler=None, response=None):
        self.calls = []
        self.handler = handler
        self.response = response

    def __call__(self, method, url, headers=None, body=None, timeout=30.0):
        self.calls.append({
            "method": method,
            "url": url,
            "headers": dict(headers or {}),
            "body": body,
            "timeout": timeout,
        })
        if self.handler is not None:
            return self.handler(method, url, dict(headers or {}), body)
        if self.response is not None:
            return self.response
        raise tts_engine.TtsError(f"stub: 拒絕連線 {url}")


def _json_response(payload, status=200):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return tts_engine._HttpResponse(status, {"content-type": "application/json"}, body)


def _audio_response(data):
    return tts_engine._HttpResponse(200, {"content-type": "audio/wav"}, data)


class TtsConfigTests(unittest.TestCase):
    """設定檔載入與正規化。"""

    def test_missing_config_returns_empty_dict_without_raising(self):
        with tempfile.TemporaryDirectory() as temp:
            missing = Path(temp) / "nope" / "tts.json"
            self.assertEqual(tts_engine.load_config(missing), {})
        # 完全不給路徑、也沒有任何設定檔時也不能炸掉
        with mock.patch.object(tts_engine, "_config_candidates", return_value=[]):
            self.assertEqual(tts_engine.load_config(), {})

    def test_broken_config_file_is_ignored(self):
        with tempfile.TemporaryDirectory() as temp:
            broken = Path(temp) / "tts.json"
            broken.write_text("{ not json", encoding="utf-8")
            self.assertEqual(tts_engine.load_config(broken), {})

    def test_config_is_read_from_explicit_path(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "tts.json"
            path.write_text(json.dumps({
                "default_engine": "sapi",
                "engines": {"openai_compat": {"base_url": "http://example.invalid", "model": "tts-1"}},
                "voice_map": {"V-lin-zhao": "阿廷AI聲"},
            }, ensure_ascii=False), encoding="utf-8")
            config = tts_engine.load_config(path)
        self.assertEqual(config["default_engine"], "sapi")
        self.assertEqual(config["voice_map"]["V-lin-zhao"], "阿廷AI聲")
        self.assertEqual(config["engines"]["openai_compat"]["model"], "tts-1")

    def test_openai_compat_base_url_strips_duplicated_v1_suffix(self):
        """http://x/v1 + /v1/audio/speech 不得變成 /v1/v1/audio/speech。"""
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "tts.json"
            path.write_text(json.dumps({
                "engines": {"openai_compat": {"base_url": "http://x/v1", "model": "tts-1"}},
            }), encoding="utf-8")
            config = tts_engine.load_config(path)
        self.assertEqual(config["engines"]["openai_compat"]["base_url"], "http://x")
        self.assertEqual(tts_engine._join_url("http://x", "/v1/audio/speech"),
                         "http://x/v1/audio/speech")
        self.assertEqual(tts_engine._join_url("http://x/v1", "/v1/audio/speech"),
                         "http://x/v1/audio/speech")


class TtsDiscoverTests(unittest.TestCase):
    """引擎盤點。"""

    def test_discover_engines_marks_sapi_and_degrades_edge(self):
        stub = _StubTransport()
        with mock.patch.object(tts_engine, "HTTP_TRANSPORT", stub):
            engines = tts_engine.discover_engines({})
        by_id = {item["id"]: item for item in engines}
        self.assertEqual(sorted(by_id), sorted(tts_engine.ALL_ENGINE_IDS))
        for item in engines:
            for key in ("id", "label", "available", "reason", "detail"):
                self.assertIn(key, item)

        sapi = by_id["sapi"]
        self.assertEqual(sapi["available"], os.name == "nt")

        edge = by_id["edge"]
        self.assertFalse(edge["available"], "edge-tts 自 2026-10-10 起不可用於正式產出")
        self.assertIn("403", edge["reason"])
        self.assertIn("非商用", edge["reason"])
        self.assertTrue(edge["detail"], "即使不可用也要說明目前套件狀態")

    def test_edge_is_reported_as_present_but_degraded(self):
        with mock.patch.object(tts_engine, "_edge_available", return_value=True):
            available, reason, detail = tts_engine._edge_check()
        self.assertFalse(available)
        self.assertIn("已安裝", detail)
        self.assertIn("403", reason)

    def test_openai_compat_requires_base_url_and_model(self):
        available, reason, _ = tts_engine._openai_compat_check({"base_url": "", "model": ""})
        self.assertFalse(available)
        self.assertIn("base_url", reason)
        available, reason, _ = tts_engine._openai_compat_check({"base_url": "http://x", "model": ""})
        self.assertFalse(available)
        self.assertIn("model", reason)
        available, _, _ = tts_engine._openai_compat_check({"base_url": "http://x", "model": "tts-1"})
        self.assertTrue(available)


class TtsSynthesizeTests(unittest.TestCase):
    """合成流程。"""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.out = self.root / "out.wav"
        self.config = {
            "engines": {
                "openai_compat": {
                    "base_url": "http://example.invalid",
                    "model": "tts-1",
                    "voice": "",
                    "response_format": "wav",
                },
            },
            "voice_map": {"V-lin-zhao": "阿廷AI聲"},
        }

    def test_synthesize_with_stubbed_transport_writes_a_real_file(self):
        audio = _wav_bytes()
        stub = _StubTransport(response=_audio_response(audio))
        with mock.patch.object(tts_engine, "HTTP_TRANSPORT", stub):
            result = tts_engine.synthesize("這是一段測試台詞。", self.out,
                                           engine="openai_compat", config=self.config)
        self.assertTrue(result["ok"], result["reason"])
        self.assertEqual(result["engine"], "openai_compat")
        self.assertTrue(self.out.exists())
        self.assertGreater(self.out.stat().st_size, 100)
        self.assertIsNotNone(result["duration_sec"])
        self.assertGreater(float(result["duration_sec"]), 0.0)
        self.assertEqual(result["channels"], 1)
        self.assertEqual(result["sample_rate"], 48000)
        self.assertEqual(stub.calls[0]["url"], "http://example.invalid/v1/audio/speech")
        self.assertEqual(stub.calls[0]["method"], "POST")

    def test_voice_map_is_resolved_before_the_provider_call(self):
        stub = _StubTransport(response=_audio_response(_wav_bytes()))
        with mock.patch.object(tts_engine, "HTTP_TRANSPORT", stub):
            result = tts_engine.synthesize("測試", self.out, engine="openai_compat",
                                           speaker="V-lin-zhao", config=self.config)
        self.assertTrue(result["ok"], result["reason"])
        body = json.loads(stub.calls[0]["body"].decode("utf-8"))
        self.assertEqual(body["voice"], "阿廷AI聲")
        self.assertEqual(result["engine_payload"]["voice_source"], "voice_map")
        self.assertEqual(result["engine_payload"]["voice_resolved"], "阿廷AI聲")

    def test_explicit_voice_wins_over_voice_map(self):
        stub = _StubTransport(response=_audio_response(_wav_bytes()))
        with mock.patch.object(tts_engine, "HTTP_TRANSPORT", stub):
            result = tts_engine.synthesize("測試", self.out, engine="openai_compat",
                                           speaker="V-lin-zhao", voice="明確音色",
                                           config=self.config)
        self.assertTrue(result["ok"], result["reason"])
        body = json.loads(stub.calls[0]["body"].decode("utf-8"))
        self.assertEqual(body["voice"], "明確音色")

    def test_api_key_is_redacted_from_error_messages(self):
        secret = "SUPER-SECRET-KEY-123456"
        config = json.loads(json.dumps(self.config))
        config["engines"]["openai_compat"]["api_key"] = secret
        failing = tts_engine._HttpResponse(500, {"content-type": "text/plain"},
                                           f"invalid api key {secret}".encode("utf-8"))
        stub = _StubTransport(response=failing)
        with mock.patch.object(tts_engine, "HTTP_TRANSPORT", stub):
            result = tts_engine.synthesize("測試", self.out, engine="openai_compat",
                                           config=config)
        self.assertFalse(result["ok"])
        self.assertNotIn(secret, result["reason"])
        self.assertIn(tts_engine.REDACTED, result["reason"])
        self.assertNotIn(secret, json.dumps(result, ensure_ascii=False))

    def test_auto_engine_prefers_openai_compat_over_sapi(self):
        """auto 順序為 voicestudio → fish → openai_compat → sapi；此處只應呼叫 openai_compat。"""
        stub = _StubTransport(response=_audio_response(_wav_bytes()))
        with mock.patch.object(tts_engine, "HTTP_TRANSPORT", stub):
            result = tts_engine.synthesize("測試", self.out, engine="auto", config=self.config)
        self.assertTrue(result["ok"], result["reason"])
        self.assertEqual(result["engine"], "openai_compat")
        posts = [call for call in stub.calls if call["method"] == "POST"]
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0]["url"], "http://example.invalid/v1/audio/speech")

    def test_failed_synthesis_leaves_no_half_written_file(self):
        failing = tts_engine._HttpResponse(500, {"content-type": "text/plain"}, b"boom")
        stub = _StubTransport(response=failing)
        with mock.patch.object(tts_engine, "HTTP_TRANSPORT", stub):
            result = tts_engine.synthesize("測試", self.out, engine="openai_compat",
                                           config=self.config)
        self.assertFalse(result["ok"])
        self.assertFalse(self.out.exists())

    def test_empty_text_fails_without_calling_any_provider(self):
        stub = _StubTransport(response=_audio_response(_wav_bytes()))
        with mock.patch.object(tts_engine, "HTTP_TRANSPORT", stub):
            result = tts_engine.synthesize("   ", self.out, engine="openai_compat",
                                           config=self.config)
        self.assertFalse(result["ok"])
        self.assertEqual(stub.calls, [])
        self.assertFalse(self.out.exists())

    def test_voicestudio_speak_flow_polls_then_downloads(self):
        """VoiceStudio：/speak 回 generating → 輪詢 status → GET /audio/{id} 取二進位。"""
        audio = _wav_bytes()
        def handler(method, url, headers, body):
            if url.endswith("/speak"):
                return _json_response({"id": "gen-1", "status": "generating",
                                       "profile_id": "p1", "text": "x", "language": "zh",
                                       "created_at": "2026-01-01T00:00:00"})
            if url.endswith("/status"):
                return _json_response({"id": "gen-1", "status": "completed"})
            if "/audio/" in url:
                return _audio_response(audio)
            raise tts_engine.TtsError(f"未預期的請求 {url}")

        stub = _StubTransport(handler=handler)
        config = {"engines": {"voicestudio": {"base_url": "http://127.0.0.1:8001"}}}
        with mock.patch.object(tts_engine, "HTTP_TRANSPORT", stub):
            result = tts_engine.synthesize("測試", self.out, engine="voicestudio",
                                           speaker="角色A｜冷面上班族內心旁白 V2", config=config)
        self.assertTrue(result["ok"], result["reason"])
        self.assertEqual(result["engine"], "voicestudio")
        self.assertTrue(self.out.exists())
        speak_call = next(call for call in stub.calls if call["url"].endswith("/speak"))
        body = json.loads(speak_call["body"].decode("utf-8"))
        self.assertEqual(body["profile"], "角色A｜冷面上班族內心旁白 V2")
        self.assertEqual(body["text"], "測試")
        self.assertTrue(any("/audio/gen-1" in call["url"] for call in stub.calls))

    def test_voicestudio_audio_endpoint_may_return_json_with_url(self):
        """某些版本 /audio/{id} 會回 JSON {url: ...}，必須能下載。"""
        audio = _wav_bytes()
        def handler(method, url, headers, body):
            if url.endswith("/speak"):
                return _json_response({"id": "gen-2", "status": "completed",
                                       "profile_id": "p1", "text": "x", "language": "zh",
                                       "created_at": "2026-01-01T00:00:00"})
            if "/audio/" in url:
                return _json_response({"url": "http://127.0.0.1:8001/files/gen-2.wav"})
            if url.endswith(".wav"):
                return _audio_response(audio)
            raise tts_engine.TtsError(f"未預期的請求 {url}")

        stub = _StubTransport(handler=handler)
        config = {"engines": {"voicestudio": {"base_url": "http://127.0.0.1:8001"}}}
        with mock.patch.object(tts_engine, "HTTP_TRANSPORT", stub):
            result = tts_engine.synthesize("測試", self.out, engine="voicestudio",
                                           voice="某個 profile", config=config)
        self.assertTrue(result["ok"], result["reason"])
        self.assertTrue(self.out.exists())

    def test_fish_cloud_downloads_the_returned_url(self):
        audio = _wav_bytes()
        def handler(method, url, headers, body):
            if url.endswith("/v1/tts"):
                return _json_response({"url": "https://fish.example/out.mp3"})
            if url == "https://fish.example/out.mp3":
                return _audio_response(audio)
            raise tts_engine.TtsError(f"未預期的請求 {url}")

        stub = _StubTransport(handler=handler)
        config = {"engines": {"fish": {"dialect": "fish_cloud", "base_url": "https://api.fish.audio",
                                       "api_key": "fish-secret", "model": "speech-1.6"}}}
        with mock.patch.object(tts_engine, "HTTP_TRANSPORT", stub):
            result = tts_engine.synthesize("測試", self.out, engine="fish",
                                           speaker="V-lin-zhao", config=config)
        self.assertTrue(result["ok"], result["reason"])
        body = json.loads(stub.calls[0]["body"].decode("utf-8"))
        self.assertEqual(body["text"], "測試")
        self.assertTrue(any(call["url"] == "https://fish.example/out.mp3" for call in stub.calls))

    def test_fish_local_uses_openai_compatible_endpoint(self):
        audio = _wav_bytes()
        stub = _StubTransport(response=_audio_response(audio))
        config = {"engines": {"fish": {"dialect": "fish_local", "base_url": "http://127.0.0.1:8080",
                                       "model": "fish-speech"}}}
        with mock.patch.object(tts_engine, "HTTP_TRANSPORT", stub):
            result = tts_engine.synthesize("測試", self.out, engine="fish",
                                           voice="preset-id", config=config)
        self.assertTrue(result["ok"], result["reason"])
        self.assertEqual(stub.calls[0]["url"], "http://127.0.0.1:8080/v1/audio/speech")
        body = json.loads(stub.calls[0]["body"].decode("utf-8"))
        self.assertEqual(body["input"], "測試")
        self.assertEqual(body["voice"], "preset-id")


class TtsDoctorTests(unittest.TestCase):
    """doctor 報告（唯讀、離線）。"""

    def test_collect_report_never_leaks_api_keys(self):
        import tts_doctor

        secret = "DOCTOR-SECRET-KEY"
        config_path = None
        with tempfile.TemporaryDirectory() as temp:
            config_path = Path(temp) / "tts.json"
            config_path.write_text(json.dumps({
                "engines": {
                    "fish": {"dialect": "fish_cloud", "api_key": secret, "base_url": "https://api.fish.audio"},
                    "openai_compat": {"base_url": "http://x", "model": "tts-1",
                                      "headers": {"X-Token": "HEADER-SECRET-VALUE"}},
                },
                "voice_map": {"V-narrator": "角色A｜冷面上班族內心旁白 V2"},
            }, ensure_ascii=False), encoding="utf-8")
            stub = _StubTransport()
            with mock.patch.object(tts_engine, "HTTP_TRANSPORT", stub):
                report = tts_doctor.collect_report(str(config_path))
        blob = json.dumps(report, ensure_ascii=False)
        self.assertNotIn(secret, blob)
        self.assertNotIn("HEADER-SECRET-VALUE", blob)
        self.assertTrue(report["fish"]["api_key_present"])
        self.assertEqual(report["voice_map"]["V-narrator"], "角色A｜冷面上班族內心旁白 V2")
        self.assertIn("Fish Audio Community License", report["fish"]["license_warning"])
        self.assertIn("403", report["edge_tts"]["note"])

    def test_collect_report_marks_edge_broken_and_recommends_an_engine(self):
        import tts_doctor

        stub = _StubTransport()
        with mock.patch.object(tts_engine, "HTTP_TRANSPORT", stub):
            report = tts_doctor.collect_report(None)
        self.assertTrue(report["edge_tts"]["broken"])
        self.assertFalse(report["edge_tts"]["available"])
        self.assertIn(report["recommended_engine"], tts_engine.ALL_ENGINE_IDS)
        self.assertTrue(report["tools"]["ffmpeg"]["present"] or not report["tools"]["ffmpeg"]["present"])


if __name__ == "__main__":
    unittest.main()
