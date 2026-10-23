"""黃金回歸：《我修的是遺忘課》EP01 精簡快照（tests/golden/ep01，只放 json＋小縮圖）。

快照內容：segments-ep01.json（去掉提示詞）、當時的 conclusions-ep01.json、timeline-plan-ep01.csv、
voice/manifest／h3-asr／placement（EP01 部分）、實際影片長度 durations.json、12 張 240px 九宮格縮圖。
每次測試都在暫存資料夾重建專案，跑一遍 verdict import → 分類 → 收件匣 → h3d next → 自動核准判斷
→ 畫外音放置 → Concat plan，結果必須與 expected.json 一致。改了規則導致結果變動時：
確認是刻意的，再用 `GOLDEN_UPDATE=1 python -m unittest tests.test_golden_ep01` 重寫 expected.json。
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
for extra in (SCRIPTS, SCRIPTS / "storyboard", SCRIPTS / "review", SCRIPTS / "voice", SCRIPTS / "edit"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

import auto_approve  # noqa: E402
import concat_adapter  # noqa: E402
import decisions  # noqa: E402
import inbox  # noqa: E402
import next_step  # noqa: E402
import project_state as ps  # noqa: E402
import verdict_import  # noqa: E402
import verdicts  # noqa: E402
import voice_align  # noqa: E402

GOLDEN = ROOT / "tests" / "golden" / "ep01"
EXPECTED = GOLDEN / "expected.json"


class GoldenEp01(unittest.TestCase):
    def setUp(self):
        from PIL import Image

        (ROOT / "tmp").mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=ROOT / "tmp")
        self.addCleanup(self.tmp.cleanup)
        r = self.root = Path(self.tmp.name)
        probe = patch.object(ps, "_ffprobe", return_value={"duration": 8.0})
        probe.start()
        self.addCleanup(probe.stop)
        for name in ("review", "source", "adapt", "images", "refs", "layer2/panels", "videos/qa/tiles", "final", "voice"):
            (r / name).mkdir(parents=True, exist_ok=True)
        (r / "project.md").write_text("我修的是遺忘課", encoding="utf-8")
        for name in ("source.json", "bible.json"):
            (r / "adapt" / name).write_text("{}", encoding="utf-8")
        (r / "adapt" / "character-bible.md").write_text("characters", encoding="utf-8")
        (r / "assets.md").write_text("assets", encoding="utf-8")
        for name in ("segments-ep01.json", "timeline-plan-ep01.csv"):
            shutil.copy(GOLDEN / name, r / name)
        for name in ("manifest.json", "h3-asr.json", "placement.json"):
            shutil.copy(GOLDEN / "voice" / name, r / "voice" / name)
        (r / "script-ep01.md").write_text("script", encoding="utf-8")
        (r / "handoff-ep01.json").write_text("{}", encoding="utf-8")
        self.segments = json.loads((r / "segments-ep01.json").read_text(encoding="utf-8"))["segments"]
        self.ids = [s["segment_id"] for s in self.segments]
        for seg in self.segments:
            for ref in seg.get("reference_images", []):
                path = r / (ref["path"] if isinstance(ref, dict) else ref)
                path.parent.mkdir(parents=True, exist_ok=True)
                if not path.exists():
                    Image.new("RGB", (2, 2), "white").save(path)
        for sid in self.ids:
            Image.new("RGB", (2, 2), "white").save(r / "layer2" / "panels" / f"panel-01-{sid}.png")
            (r / "layer2" / f"layer2-{sid}.json").write_text(json.dumps({
                "segment_id": sid, "shots": [{"shot_id": "SH01", "sketch_file": f"panels/panel-01-{sid}.png"}]}),
                encoding="utf-8")
        for stage in range(6):
            ps.mark_awaiting_review(r, ps.load_state(r), stage)
            self.assertTrue(ps.approve_stage(r, stage, "使用者確認通過"), f"stage-{stage}")
        for sid in self.ids:
            (r / "videos" / f"{sid}.mp4").write_bytes(f"golden {sid}".encode())
            shutil.copy(GOLDEN / "thumbs" / f"{sid}.jpg", r / "videos" / "qa" / "tiles" / f"{sid}.jpg")
        self.write_qa()
        for did, value, quote, date in (
                ("style", "半寫實厚塗", "喜歡現在的寫實風", "2026-10-21"),
                ("aspect_ratio", "16:9", "16:9", "2026-10-21"),
                ("design_engine", "codex", "設定圖用 codex", "2026-10-21"),
                ("dialogue_policy", "只留重點句", "② 只留重點句", "2026-10-21"),
                ("acceptance_policy", "recommended", "紙面出字不算問題；人物稍老可接受", "2026-10-22")):
            decisions.decide(r, did, value, quote, date=date)

    def write_qa(self):
        results = []
        for sid in self.ids:
            video = self.root / "videos" / f"{sid}.mp4"
            results.append({"segment_id": sid, "video_file": str(video), "video_sha256": ps.sha256_file(video),
                            "passed": True, "issues": []})
        seg = self.root / "segments-ep01.json"
        payload = {"expected_segments": self.ids, "unproduced_segments": [], "results": results,
                   "evidence": {"verdict": "VERIFIED", "produced": len(self.ids), "expected": len(self.ids),
                                "unmeasured": 0, "failed": 0, "unproduced": [], "structural_issues": []},
                   "source_segments_file": str(seg), "source_segments_sha256": ps.sha256_file(seg)}
        (self.root / "videos" / "qa-report.json").write_text(json.dumps(payload), encoding="utf-8")

    def snapshot(self):
        r = self.root
        out = {}
        report = verdict_import.convert(r, [GOLDEN / "conclusions-ep01.json"])
        verdicts.save(r, report["data"])
        out["import"] = {sid: [v["verdict"], v["decided_by"], v["issues"]]
                         for sid, v in sorted(report["data"]["segments"].items())}
        classified = verdicts.classify(r)
        out["counts"] = classified["counts"]
        out["effective"] = {sid: row["effective"] for sid, row in classified["segments"].items()}
        built = inbox.build_cards(r)
        out["inbox_open"] = [c["id"] for c in built["open"]]
        out["inbox_voice_characters"] = next((c["characters"] for c in built["open"] if c["kind"] == "voice"), [])
        plan = next_step.plan(r)
        out["next"] = {"stage": plan["stage"], "status": plan["status"],
                       "command_head": (plan["next_command"] or "").split(" --")[0].split("/")[-1]}
        decisions.decide(r, "auto_approve", "6", "照政策自動過", date="2026-10-22")
        evaluation = auto_approve.evaluate(r, 6)
        out["auto_approve_eligible"] = evaluation["eligible"]
        durations = json.loads((GOLDEN / "durations.json").read_text(encoding="utf-8"))
        manifest = json.loads((r / "voice" / "manifest.json").read_text(encoding="utf-8"))
        asr = json.loads((r / "voice" / "h3-asr.json").read_text(encoding="utf-8"))
        placement, need = voice_align.place(manifest, voice_align.timeline_lines(r), asr, durations, self.ids)
        out["placement"] = {k: [v["start"], v["tempo"], v["mutes"]] for k, v in sorted(placement.items())}
        recorded = json.loads((r / "voice" / "placement.json").read_text(encoding="utf-8"))
        cplan = concat_adapter.build_plan(name="EP01", order=self.ids, durations=durations,
                                          lines=voice_align.timeline_lines(r), asr=asr, placement=recorded,
                                          manifest=manifest)
        out["concat"] = {"total": cplan["total"], "stats": cplan["stats"], "captions": len(cplan["captions"]),
                         "first_caption": cplan["captions"][0], "voices": [v["start"] for v in cplan["voices"]]}
        return out

    def test_golden_snapshot_matches(self):
        got = json.loads(json.dumps(self.snapshot(), ensure_ascii=False))
        if os.environ.get("GOLDEN_UPDATE") == "1":
            EXPECTED.write_text(json.dumps(got, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
            self.skipTest("已重寫 expected.json")
        expected = json.loads(EXPECTED.read_text(encoding="utf-8"))
        for key in expected:
            with self.subTest(key=key):
                self.assertEqual(got[key], expected[key])

    def test_golden_story_facts(self):
        """人看得懂的幾條：EP01-S04-d 紅界格是唯一的附註；12 段都有結論；弟子甲要定音色。"""
        snap = self.snapshot()
        self.assertEqual(snap["counts"]["unreviewed"], 0)
        self.assertEqual([sid for sid, e in snap["effective"].items() if e == "warn"], ["EP01-S04-d"])
        self.assertIn("D6-EP01-S04-d", snap["inbox_open"])
        self.assertIn("C-func-disciple-a", snap["inbox_voice_characters"])
        self.assertFalse(snap["auto_approve_eligible"], "還有附註卡沒決定，不能自動核准")
        self.assertEqual(snap["concat"]["stats"]["voice"], 4)


if __name__ == "__main__":
    unittest.main()
