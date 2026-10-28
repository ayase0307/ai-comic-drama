"""收件匣八階段閱讀視圖、合併卡保留子卡、階段 5 段級重審卡（review-page-spec.md §2、§6）。"""
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
for extra in (ROOT / "scripts", ROOT / "scripts" / "storyboard", ROOT / "scripts" / "review", Path(__file__).resolve().parent):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

import inbox  # noqa: E402
import project_state as ps  # noqa: E402
from test_enforce_flow import TwoEpisodeProject  # noqa: E402
import _content_gate  # noqa: E402


def setUpModule():
    _content_gate.disable()


def tearDownModule():
    _content_gate.enable()


def _fails(n):
    segs = {f"EP01-S{i:02d}": {"effective": "fail", "reason": f"第 {i} 段燒出字幕", "issues": ["burned_subtitle"],
                               "source": "agent"} for i in range(1, n + 1)}
    return {"segments": segs, "counts": {"fail": n}, "policy": {"accept": []}, "policy_is_decided": True}


class StageViewTests(TwoEpisodeProject):
    def _model(self, n_fails=0):
        with patch.object(inbox.verdicts_mod, "classify", return_value=_fails(n_fails)):
            return inbox.collect(self.root, images=False, strips="none")

    def test_eight_views_with_six_blocks(self):
        model = self._model()
        views = model["stage_views"]
        self.assertEqual([v["n"] for v in views], list(range(8)))
        for v in views:
            for key in ("ask", "status_label", "cards", "facts", "docs", "issues", "decided"):
                self.assertIn(key, v)
        page = inbox.render_html(model)
        for n in range(8):
            self.assertIn(f'id="stage-{n}"', page)
            self.assertIn(f'href="#stage-{n}"', page)

    def test_status_separates_approved_from_changed(self):
        views = self._model()["stage_views"]
        self.assertEqual(views[0]["status"], "approved")
        (self.root / "project.md").write_text("pitch v2", encoding="utf-8")
        views = self._model()["stage_views"]
        self.assertEqual(views[0]["status"], "stale")
        self.assertEqual(views[0]["status_label"], "內容已變更，待重審")

    def test_docs_mark_missing_and_embed_text(self):
        views = self._model()["stage_views"]
        stage3 = {d["label"]: d for d in views[3]["docs"]}
        self.assertEqual(stage3["漫劇劇本"]["state"], "ok")
        self.assertEqual(stage3["漫劇劇本"]["preview"], "script")
        self.assertEqual(stage3["改編差異對帳"]["state"], "missing")

    def test_merged_card_keeps_every_child_and_raw_count(self):
        model = self._model(8)
        merged = next(c for c in model["cards"] if c["kind"] == "merged")
        self.assertEqual(len(merged["children"]), len(merged["merged"]))
        self.assertTrue(all(ch["options"] and ch["impact"] for ch in merged["children"]))
        self.assertEqual(model["pending_total"], 8)
        page = inbox.render_html(model)
        self.assertIn("有 <em>8</em> 件事等你決定", page)
        self.assertIn(f'id="{merged["children"][0]["id"]}"', page)

    def test_doc_decision_becomes_blocking_card(self):
        import doc_card
        path = self.root / "project.md"
        path.write_text(doc_card.stamp(path.read_text(encoding="utf-8"), title="t", status="等你核准", summary="定調",
                                       decisions=["要不要分集？ 建議：不分；或：分三集"]), encoding="utf-8")
        cards = [c for c in self._model()["cards"] if c["kind"] == "doc"]
        self.assertEqual(len(cards), 1)
        self.assertEqual([o["reply"] for o in cards[0]["options"]],
                         ["project.md 第 1 條：不分", "project.md 第 1 條：分三集", "project.md 第 1 條：先放著"])
        self.assertEqual(cards[0]["blocking"], 2)


class Stage5RereviewCardTests(TwoEpisodeProject):
    def test_partial_rereview_becomes_card_and_view_status(self):
        seg_file = self.root / "segments-ep01.json"
        data = json.loads(seg_file.read_text(encoding="utf-8"))
        sid = data["segments"][0]["segment_id"]
        data["segments"][0]["prompt"] = "changed after approval"
        seg_file.write_text(json.dumps(data), encoding="utf-8")
        review = ps.stage5_segment_review(self.root)
        if review["mode"] != "partial":
            self.skipTest(f"fixture 未產生段級核准（mode={review['mode']}）")
        card = inbox._stage5_rereview_card(self.root)
        self.assertEqual(card["segments"], [sid])
        self.assertEqual(card["blocking"], 1)
        self.assertNotIn("這幾段通過", [o["label"] for o in card["options"]], "沒有重審頁時不能給「通過」")
        ps.record_segment_review(self.root, [sid])
        card = inbox._stage5_rereview_card(self.root)
        self.assertIn(f"階段 5 重審：{sid} 通過", [o["reply"] for o in card["options"]])
        with patch.object(inbox.verdicts_mod, "classify", return_value=_fails(0)):
            model = inbox.collect(self.root, images=False, strips="none")
        self.assertEqual(model["stage_views"][5]["status"], "partial")


if __name__ == "__main__":
    unittest.main()
