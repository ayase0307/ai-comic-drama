import json
import contextlib
import io
import sys
import tempfile
import unittest
import subprocess
import wave
import struct
import math
from pathlib import Path
from unittest import mock

from scripts.storyboard import assemble_episode as assembly


class AssemblyRegressionTests(unittest.TestCase):
    @staticmethod
    def _make_video(path, duration=1.0, audio=False):
        command = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
                   "-i", f"color=c=blue:s=160x90:r=24:d={duration}"]
        if audio:
            command += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}", "-c:a", "aac"]
        else:
            command += ["-an"]
        command += ["-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)]
        result = subprocess.run(command, capture_output=True)
        if result.returncode:
            raise AssertionError(result.stderr.decode("utf-8", "replace"))

    @staticmethod
    def _write_wav(path, duration):
        path.parent.mkdir(parents=True, exist_ok=True)
        rate = 16000
        frames = [struct.pack("<h", int(5000 * math.sin(2 * math.pi * 440 * n / rate)))
                  for n in range(int(rate * duration))]
        with wave.open(str(path), "wb") as stream:
            stream.setnchannels(1)
            stream.setsampwidth(2)
            stream.setframerate(rate)
            stream.writeframes(b"".join(frames))

    def test_duration_sources_and_ambiguous_timeline_id(self):
        self.assertEqual(assembly.expected_segment_duration({"metadata": {"target_duration_sec": 7.5}}), 7.5)
        self.assertEqual(assembly.expected_segment_duration({"shots": [{"duration": 2}, {"duration": 3}]}), 5)
        self.assertEqual(assembly.timeline_segment_id({"shot_id": "EP01-S01-a-SH02"}), "EP01-S01-a")
        with self.assertRaises(ValueError):
            assembly.expected_segment_duration({"segment_id": "no-duration", "shots": []})
        with self.assertRaises(ValueError):
            assembly.timeline_segment_id({"shot_id": "unparseable"})

    def test_native_audio_is_preserved_and_padded_to_segment_duration(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as td:
            root = Path(td)
            source, output = root / "source.mp4", root / "processed.mp4"
            self._make_video(source, 1.0, audio=True)
            ok, message = assembly.process_single_segment(
                source, output, [{"subtitle": "short line", "start": 0.3, "end": 0.8}], 1.0,
                burn_subtitles=False,
            )
            self.assertTrue(ok, message)
            specs = assembly.probe_video_specs(output)
        self.assertTrue(specs["has_audio"])
        self.assertAlmostEqual(specs["duration"], 1.0, delta=0.1)

    def test_missing_native_audio_fails_when_dialogue_is_required(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as td:
            root = Path(td)
            source, output = root / "source.mp4", root / "processed.mp4"
            self._make_video(source, 1.0, audio=False)
            ok, message = assembly.process_single_segment(
                source, output, [{"subtitle": "line", "start": 0.1, "end": 0.8}], 1.0,
                audio_required=True, burn_subtitles=False,
            )
        self.assertFalse(ok)
        self.assertIn("沒有音訊流", message)
        self.assertFalse(output.exists())

    def test_tts_cli_options_are_removed(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as td:
            root = Path(td)
            for extra in (["--tts-engine", "auto"], ["--tts-config", "config/tts.json"],
                          ["--audio-mode", "native_sub"], ["--narration", str(root / "narration.md")]):
                with self.subTest(extra=extra), mock.patch.object(sys, "argv", [
                    "assemble_episode.py", "--segments", str(root / "segments.json"),
                    "--videos-dir", str(root), "--output", str(root / "final.mp4"),
                ] + extra), contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit) as raised:
                        assembly.main()
                self.assertEqual(raised.exception.code, 2)

    def test_concat_uses_paths_with_spaces_and_apostrophes(self):
        with tempfile.TemporaryDirectory(prefix="episode's path ", dir=Path(__file__).resolve().parents[1]) as td:
            root = Path(td)
            source_dir = root / "temp_assemble"
            source_dir.mkdir()
            segment = source_dir / "clip's one.mp4"
            generated = __import__("subprocess").run([
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-f", "lavfi", "-i", "color=c=blue:s=160x90:r=24:d=0.5",
                "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(segment),
            ], capture_output=True)
            self.assertEqual(generated.returncode, 0, generated.stderr.decode("utf-8", "replace"))
            output = root / "final cut.mp4"
            ok, message = assembly.concat_videos([segment], output)
            self.assertTrue(ok)
            self.assertTrue(output.exists(), message)
            self.assertGreater(output.stat().st_size, 100)

    def test_concat_aac_segments_pcm_locked_to_video_length(self):
        import subprocess
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as td:
            root = Path(td)
            segs = []
            for i, (dur, audio) in enumerate([(1.0, True), (1.0, False), (1.0, True)]):
                seg = root / f"s{i}.mp4"
                cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                       "-f", "lavfi", "-i", f"color=c=blue:s=160x90:r=24:d={dur}"]
                if audio:
                    cmd += ["-f", "lavfi", "-i", "sine=frequency=440:duration=0.9", "-c:a", "aac", "-shortest"]
                    cmd = [c for c in cmd if c != "-shortest"]
                else:
                    cmd += ["-an"]
                cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", str(seg)]
                self.assertEqual(subprocess.run(cmd, capture_output=True).returncode, 0)
                segs.append(seg)
            out = root / "final.mp4"
            ok, msg = assembly.concat_videos(segs, out, target_lufs=None)
            self.assertTrue(ok, msg)
            info = assembly.probe_video_specs(out)
            self.assertTrue(info["has_audio"])
            self.assertAlmostEqual(info["duration"], 3.0, delta=0.1)
            self.assertEqual([p.name for p in root.glob(".pcm_*")], [])

    def test_assemble_missing_segment_fails_and_does_not_leave_stale_final(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as td:
            root = Path(td)
            segments = root / "segments.json"
            segments.write_text(json.dumps({"segments": [
                {"segment_id": "SEG-A", "seconds": 2},
                {"segment_id": "SEG-B", "seconds": 2},
            ]}), encoding="utf-8")
            videos = root / "videos"
            videos.mkdir()
            (videos / "SEG-A.mp4").write_bytes(b"input")
            output = root / "final.mp4"
            output.write_bytes(b"stale")
            manifest = root / "delivery-final.json"
            def fake_process(source, dest, *args, **kwargs):
                dest.write_bytes(b"processed")
                return True, "ok"
            with mock.patch.object(sys, "argv", [
                "assemble_episode.py", "--segments", str(segments),
                "--videos-dir", str(videos), "--output", str(output),
                "--no-burn-subtitles",
            ]), mock.patch.object(assembly, "process_single_segment", side_effect=fake_process):
                try:
                    exit_code = assembly.main()
                except SystemExit as exc:
                    exit_code = int(exc.code) if isinstance(exc.code, int) else 1
                self.assertNotEqual(exit_code, 0)
                self.assertEqual(output.read_bytes(), b"stale")
                self.assertEqual(json.loads(manifest.read_text(encoding="utf-8"))["delivery_status"], "failed")

    def test_delivery_manifest_records_hash_decode_and_segments(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as td:
            root = Path(td)
            segments = root / "segments.json"
            segments.write_text(json.dumps({"segments": [
                {"segment_id": "SEG-A", "seconds": 2},
            ]}), encoding="utf-8")
            videos = root / "videos"
            videos.mkdir()
            (videos / "SEG-A.mp4").write_bytes(b"input")
            output = root / "final.mp4"
            def fake_process(source, dest, *args, **kwargs):
                dest.write_bytes(b"processed")
                return True, "ok"
            def fake_concat(paths, dest, **kwargs):
                dest.write_bytes(b"final")
                return True, "ok"
            with mock.patch.object(sys, "argv", [
                "assemble_episode.py", "--segments", str(segments),
                "--videos-dir", str(videos), "--output", str(output),
                "--no-burn-subtitles",
            ]), mock.patch.object(assembly, "process_single_segment", side_effect=fake_process), \
                    mock.patch.object(assembly, "concat_videos", side_effect=fake_concat), \
                    mock.patch.object(assembly, "validate_video_decode", return_value={
                        "decode_ok": True, "duration": 2.0,
                    }):
                exit_code = assembly.main()
            manifest = json.loads((root / "delivery-final.json").read_text(encoding="utf-8"))
        self.assertEqual(exit_code, 0)
        self.assertTrue(manifest["final_sha256"])
        self.assertTrue(manifest["final_decode_ok"])
        self.assertEqual(manifest["expected_segments"], ["SEG-A"])
        self.assertEqual(manifest["assembled_segment_count"], 1)
        self.assertEqual(manifest["review_status"], "pending_review")
        self.assertEqual(manifest["delivery_status"], "complete")
        self.assertEqual(manifest["source_segments_file"], str(segments.resolve()))
        self.assertTrue(manifest["source_segments_sha256"])

    def test_final_duration_tolerance_does_not_scale_with_segment_count(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as td:
            root = Path(td)
            segments = root / "segments.json"
            segments.write_text(json.dumps({"segments": [
                {"segment_id": "SEG-A", "seconds": 2},
                {"segment_id": "SEG-B", "seconds": 2},
            ]}), encoding="utf-8")
            videos = root / "videos"
            videos.mkdir()
            for sid in ("SEG-A", "SEG-B"):
                (videos / f"{sid}.mp4").write_bytes(b"input")
            output = root / "final.mp4"
            def fake_process(source, dest, *args, **kwargs):
                dest.write_bytes(b"processed")
                return True, "ok"
            def fake_concat(paths, dest, **kwargs):
                dest.write_bytes(b"final")
                return True, "ok"
            with mock.patch.object(sys, "argv", [
                "assemble_episode.py", "--segments", str(segments), "--videos-dir", str(videos),
                "--output", str(output), "--no-burn-subtitles",
            ]), mock.patch.object(assembly, "process_single_segment", side_effect=fake_process), \
                    mock.patch.object(assembly, "concat_videos", side_effect=fake_concat), \
                    mock.patch.object(assembly, "validate_video_decode", return_value={"decode_ok": True, "duration": 3.25}), \
                    contextlib.redirect_stdout(io.StringIO()):
                code = assembly.main()
            manifest = json.loads((root / "delivery-final.json").read_text(encoding="utf-8"))
        self.assertNotEqual(code, 0)
        self.assertEqual(manifest["delivery_status"], "failed")

    def test_full_assembly_decodes_and_writes_per_episode_hash_manifest(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as td:
            root = Path(td)
            videos = root / "videos"
            videos.mkdir()
            for sid, frequency in (("EP03-SEG01", 440), ("EP03-SEG02", 660)):
                subprocess_result = __import__("subprocess").run([
                    "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                    "-f", "lavfi", "-i", "color=c=blue:s=160x90:r=24:d=0.5",
                    "-f", "lavfi", "-i", f"sine=frequency={frequency}:duration=0.5",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
                    str(videos / f"{sid}.mp4"),
                ], capture_output=True)
                self.assertEqual(subprocess_result.returncode, 0, subprocess_result.stderr.decode("utf-8", "replace"))
            segments = root / "segments-ep03.json"
            segments.write_text(json.dumps({"episode": "ep03", "segments": [
                {"segment_id": "EP03-SEG01", "seconds": 0.5, "shots": []},
                {"segment_id": "EP03-SEG02", "seconds": 0.5, "shots": []},
            ]}), encoding="utf-8")
            output = root / "final's episode.mp4"
            with mock.patch.object(sys, "argv", [
                "assemble_episode.py", "--segments", str(segments),
                "--videos-dir", str(videos), "--output", str(output),
                "--no-burn-subtitles",
            ]), contextlib.redirect_stdout(io.StringIO()):
                exit_code = assembly.main()
            manifest = json.loads((root / "delivery-final's episode.json").read_text(encoding="utf-8"))
            self.assertEqual(exit_code, 0)
            self.assertEqual(manifest["episode"], "ep03")
            self.assertEqual(manifest["delivery_status"], "complete")
            self.assertTrue(manifest["final_decode_ok"])
            self.assertEqual(manifest["expected_segments"], ["EP03-SEG01", "EP03-SEG02"])
            self.assertEqual(manifest["assembled_segment_count"], 2)
            self.assertEqual(manifest["final_sha256"], assembly.compute_file_sha256(output))


if __name__ == "__main__":
    unittest.main()
