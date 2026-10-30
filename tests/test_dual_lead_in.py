"""雙人引子（E3，spatial-consistency.md §7）：格式檢查、W47 建議、W48 警告、組裝自動剪掉片頭。"""
import contextlib
import copy
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.storyboard import assemble_episode as assembly
from scripts.storyboard import dual_lead_in
from scripts.storyboard import staging_lint

ROOT = Path(__file__).resolve().parents[1]


def shot(sid, start, end, ids, size="medium close-up", line=None, window=None, **extra):
    dlg = {"has_dialogue": bool(line), "line_verbatim": line or ""}
    if window:
        dlg["speech_window"] = {"start": window[0], "end": window[1]}
    return {"shot_id": sid, "start_time": start, "end_time": end, "duration": round(end - start, 4),
            "character_ids": list(ids), "camera_optics": {"shot_size": size}, "dialogue_and_audio": dlg, **extra}


# T4 的 S01→S02（沈 MCU → 賴 MCU 正反打），原樣與加了引子的版本
PREV = {"segment_id": "T4-S01", "scene_id": "S-buffet", "shots": [
    shot("SH01", 0.0, 3.6, ["C-shen", "C-lai"], "medium-wide shot", "咦，怎麼又是你？", (1.0, 2.8)),
    shot("SH02", 3.6, 7.29, ["C-shen"], "medium close-up"),
]}
PLAIN = {"segment_id": "T4-S02", "scene_id": "S-buffet", "shots": [
    shot("SH01", 0.0, 3.6, ["C-lai"], "medium close-up", "受傷了嗎？", (0.8, 2.4)),
    shot("SH02", 3.6, 7.29, ["C-shen"], "medium close-up", "沒有。", (4.2, 5.0)),
]}
LEAD = {"segment_id": "T4-S02", "scene_id": "S-buffet", "metadata": {"target_duration_sec": 9.29}, "shots": [
    shot("SH01", 0.0, 2.0, ["C-shen", "C-lai"], "medium-wide shot", dual_lead_in=True),
    shot("SH02", 2.0, 5.6, ["C-lai"], "medium close-up", "受傷了嗎？", (2.8, 4.4)),
    shot("SH03", 5.6, 9.29, ["C-shen"], "medium close-up", "沒有。", (6.2, 7.0)),
]}


class CheckTests(unittest.TestCase):
    def test_unmarked_segment_has_no_findings_and_no_trim(self):
        self.assertEqual(dual_lead_in.check(PLAIN), [])
        self.assertEqual(dual_lead_in.lead_in_seconds(PLAIN), 0.0)

    def test_well_formed_lead_in(self):
        self.assertEqual(dual_lead_in.check(LEAD), [])
        self.assertEqual(dual_lead_in.lead_in_seconds(LEAD), 2.0)

    def test_lead_in_must_be_first_shot(self):
        seg = copy.deepcopy(LEAD)
        seg["shots"][0].pop("dual_lead_in")
        seg["shots"][1]["dual_lead_in"] = True
        self.assertTrue(any("第 1 鏡" in p for p in dual_lead_in.check(seg)))
        self.assertEqual(dual_lead_in.lead_in_seconds(seg), 0.0)

    def test_lead_in_needs_two_people_and_two_seconds(self):
        seg = copy.deepcopy(LEAD)
        seg["shots"][0]["character_ids"] = ["C-lai"]
        seg["shots"][0]["end_time"] = 1.5
        seg["shots"][1]["start_time"] = 1.5
        problems = "；".join(dual_lead_in.check(seg))
        self.assertIn("兩名角色", problems)
        self.assertIn("短於 2", problems)

    def test_dialogue_inside_lead_in_is_rejected(self):
        seg = copy.deepcopy(LEAD)
        seg["shots"][0]["dialogue_and_audio"] = {"has_dialogue": True, "line_verbatim": "喂"}
        self.assertTrue(any("台詞" in p for p in dual_lead_in.check(seg)))

    def test_later_speech_window_not_shifted_is_rejected(self):
        seg = copy.deepcopy(LEAD)
        seg["shots"][1]["dialogue_and_audio"]["speech_window"] = {"start": 0.8, "end": 2.4}
        self.assertTrue(any("往後挪" in p for p in dual_lead_in.check(seg)))


class SuggestTests(unittest.TestCase):
    def test_hard_cut_to_single_close_up_is_suggested_with_offscreen_partner(self):
        tip = dual_lead_in.suggest(PLAIN, PREV)
        self.assertIsNotNone(tip)
        self.assertIn("C-lai＋C-shen", tip)

    def test_partner_from_previous_segment_when_segment_is_single_only(self):
        seg = {"segment_id": "T4-S04", "scene_id": "S-buffet", "shots": [
            shot("SH01", 0.0, 7.29, ["C-lai"], "medium close-up", "要直接擊散妖氣集中的地方。")]}
        prev = {"segment_id": "T4-S03", "scene_id": "S-buffet", "shots": [
            shot("SH01", 0.0, 4.0, ["C-shen", "C-lai"], "medium shot", "你這槍怎麼一戳就死？"),
            shot("SH02", 4.0, 7.29, ["C-lai"], "close-up")]}
        self.assertIn("C-lai＋C-shen", dual_lead_in.suggest(seg, prev))

    def test_not_suggested(self):
        cases = {
            "no previous segment": (PLAIN, None),
            "other scene": (PLAIN, {**PREV, "scene_id": "S-street"}),
            "already marked": (LEAD, PREV),
            "seam_in cont": ({**PLAIN, "seam_in": "cont"}, PREV),
            "combat": ({**PLAIN, "impact_plan": {"type": "punch"}}, PREV),
        }
        two_shot_first = copy.deepcopy(PLAIN)
        two_shot_first["shots"][0]["character_ids"] = ["C-shen", "C-lai"]
        cases["first shot two-shot"] = (two_shot_first, PREV)
        wide_first = copy.deepcopy(PLAIN)
        wide_first["shots"][0]["camera_optics"]["shot_size"] = "medium-wide shot"
        cases["first shot wide"] = (wide_first, PREV)
        silent = copy.deepcopy(PLAIN)
        for s in silent["shots"]:
            s["dialogue_and_audio"] = {"has_dialogue": False, "line_verbatim": ""}
        cases["no dialogue"] = (silent, PREV)
        # 上一段末鏡和本段首鏡同主體同景別＝同一顆鏡頭拆兩段（續接）
        cont_prev = copy.deepcopy(PREV)
        cont_prev["shots"][-1]["character_ids"] = ["C-lai"]
        cases["continuation"] = (PLAIN, cont_prev)
        solo_prev = {"segment_id": "X", "scene_id": "S-buffet", "shots": [shot("SH01", 0, 7, ["C-lai"], "medium shot")]}
        solo = {"segment_id": "Y", "scene_id": "S-buffet", "shots": [
            shot("SH01", 0, 7, ["C-lai"], "close-up", "一個人。")]}
        cases["nobody to pair with"] = (solo, solo_prev)
        for name, (seg, prev) in cases.items():
            with self.subTest(name):
                self.assertIsNone(dual_lead_in.suggest(seg, prev))


class StagingTests(unittest.TestCase):
    def test_w47_is_suggestion_and_w48_is_warning(self):
        findings = staging_lint.lint_segment(PLAIN, prev=PREV)
        w47 = [f for f in findings if f["code"] == "W47"]
        self.assertEqual(len(w47), 1)
        self.assertEqual(w47[0]["level"], "suggestion")
        bad = copy.deepcopy(LEAD)
        bad["shots"][0]["character_ids"] = ["C-lai"]
        findings = staging_lint.lint_segment(bad, prev=PREV, strict=True)
        w48 = [f for f in findings if f["code"] == "W48"]
        self.assertTrue(w48)
        self.assertTrue(all(f["level"] == "warning" for f in w48))
        self.assertFalse(any(f["code"] in ("W47", "W48") for f in staging_lint.lint_segment(LEAD, prev=PREV)))

    def test_w47_waiver(self):
        seg = copy.deepcopy(PLAIN)
        seg["metadata"] = {"staging_waivers": [{"code": "W47", "reason": "刻意", "quote": "這段不用引子"}]}
        self.assertFalse(any(f["code"] == "W47" for f in staging_lint.lint_segment(seg, prev=PREV)))

    def test_layer2_mode_lists_lead_in_suggestions(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as td:
            root = Path(td)
            (root / "layer2").mkdir()
            (root / "layer2" / "layer2-T4-S01.json").write_text(json.dumps(PREV, ensure_ascii=False), encoding="utf-8")
            (root / "layer2" / "layer2-T4-S02.json").write_text(json.dumps(PLAIN, ensure_ascii=False), encoding="utf-8")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = staging_lint.main(["--root", str(root), "--layer2"])
        self.assertEqual(code, 0)
        self.assertIn("W47", out.getvalue())
        self.assertIn("雙人引子建議 1 段", out.getvalue())


def _probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True)
    return float(out.stdout.strip())


def _make_video(path, duration):
    res = subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                          "-f", "lavfi", "-i", f"color=c=blue:s=160x90:r=24:d={duration}",
                          "-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}",
                          "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path)],
                         capture_output=True)
    if res.returncode:
        raise AssertionError(res.stderr.decode("utf-8", "replace"))


class AssembleTrimTests(unittest.TestCase):
    def test_process_single_segment_trims_head_and_shifts_subtitles(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as td:
            root = Path(td)
            src, out = root / "SEG.mp4", root / "proc.mp4"
            _make_video(src, 3.0)
            ok, msg = assembly.process_single_segment(
                src, out, [{"subtitle": "受傷了嗎", "start": 2.2, "end": 2.8}], 3.0,
                audio_mode="native_sub", temp_dir=root / "tmp", lead_in_s=2.0)
            self.assertTrue(ok, msg)
            self.assertAlmostEqual(_probe(out), 1.0, delta=0.1)
            srt = (root / "tmp" / "SEG.srt").read_text(encoding="utf-8")
            self.assertIn("00:00:00,200 --> 00:00:00,800", srt)

    def test_line_inside_lead_in_fails(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as td:
            root = Path(td)
            src = root / "SEG.mp4"
            _make_video(src, 3.0)
            ok, msg = assembly.process_single_segment(
                src, root / "proc.mp4", [{"subtitle": "喂", "start": 1.0, "end": 1.5}], 3.0,
                audio_mode="native_sub", temp_dir=root / "tmp", lead_in_s=2.0)
        self.assertFalse(ok)
        self.assertIn("雙人引子", msg)

    def test_no_lead_in_keeps_old_behaviour(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as td:
            root = Path(td)
            src, out = root / "SEG.mp4", root / "proc.mp4"
            _make_video(src, 2.0)
            ok, msg = assembly.process_single_segment(src, out, [], 2.0, audio_mode="native_sub",
                                                      temp_dir=root / "tmp", burn_subtitles=False)
            self.assertTrue(ok, msg)
            self.assertAlmostEqual(_probe(out), 2.0, delta=0.1)

    def _assemble(self, segment, duration):
        with tempfile.TemporaryDirectory(dir=ROOT) as td:
            root = Path(td)
            videos = root / "videos"
            videos.mkdir()
            _make_video(videos / f"{segment['segment_id']}.mp4", duration)
            segments = root / "segments-ep01.json"
            segments.write_text(json.dumps({"episode": "ep01", "segments": [segment]}, ensure_ascii=False), encoding="utf-8")
            output = root / "final.mp4"
            with mock.patch.object(sys, "argv", [
                "assemble_episode.py", "--segments", str(segments), "--videos-dir", str(videos),
                "--output", str(output), "--audio-mode", "native_sub", "--no-burn-subtitles",
            ]), contextlib.redirect_stdout(io.StringIO()):
                code = assembly.main()
            final = _probe(output) if output.exists() else None
            manifest = json.loads((root / "delivery-final.json").read_text(encoding="utf-8"))
        return code, final, manifest

    def test_assemble_cuts_marked_lead_in_automatically(self):
        seg = {"segment_id": "EP01-S02", "metadata": {"frames": 77}, "shots": [
            shot("SH01", 0.0, 2.0, ["C-shen", "C-lai"], "medium-wide shot", dual_lead_in=True),
            shot("SH02", 2.0, 77 / 24, ["C-lai"], "medium close-up", "受傷了嗎", (2.2, 2.9)),
        ]}
        code, final, manifest = self._assemble(seg, 77 / 24)
        self.assertEqual(code, 0, manifest)
        self.assertAlmostEqual(final, 77 / 24 - 2.0, delta=0.1)

    def test_assemble_refuses_malformed_lead_in(self):
        seg = {"segment_id": "EP01-S02", "metadata": {"frames": 77}, "shots": [
            shot("SH01", 0.0, 2.0, ["C-lai"], "medium close-up", dual_lead_in=True),
            shot("SH02", 2.0, 77 / 24, ["C-shen"], "medium close-up"),
        ]}
        code, final, manifest = self._assemble(seg, 77 / 24)
        self.assertNotEqual(code, 0)
        self.assertEqual(manifest["delivery_status"], "failed")


if __name__ == "__main__":
    unittest.main()
