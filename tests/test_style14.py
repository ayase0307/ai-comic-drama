"""14 號風格「古風寫實厚塗・電影感」（xianxia-cinematic-semireal）：預設值、配方、無參考圖報錯。"""
import contextlib
import io
import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
for extra in (ROOT / "scripts", ROOT / "scripts" / "storyboard", ROOT / "scripts" / "review", ROOT):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

import audit_refs_and_segments as audit  # noqa: E402
import decisions  # noqa: E402
import export_asset_prompts as ex  # noqa: E402
import style_rules  # noqa: E402

CEL_SENTENCE = ("Hand-painted 2D xianxia illustration with thick painterly brushwork on robes, hair and stone, "
                "soft cel-like shading on faces, non-photorealistic")


def _tmp(test):
    (ROOT / "tmp").mkdir(exist_ok=True)
    td = tempfile.TemporaryDirectory(dir=ROOT / "tmp")
    test.addCleanup(td.cleanup)
    return pathlib.Path(td.name)


class DefaultsTests(unittest.TestCase):
    def test_export_default_is_style14(self):
        self.assertEqual(ex.DEFAULT_STYLE_KEY, "xianxia-cinematic-semireal")
        self.assertEqual(ex.resolve_style(None)["key"], "xianxia-cinematic-semireal")
        self.assertEqual(ex.resolve_style("14")["key"], "xianxia-cinematic-semireal")
        prompt = ex.build_character_prompt("27歲東亞男子")
        self.assertIn("realistic East Asian bone structure", prompt)
        self.assertIn("photorealism, Unreal Engine look", prompt)
        self.assertNotIn("cel-like", prompt)
        # 仍可改選
        self.assertEqual(ex.resolve_style("master")["key"], "master")
        self.assertEqual(ex.resolve_style("7")["key"], "7")

    def test_cli_without_style_index_uses_default_with_reminder(self):
        text = "## 角色\n\n### C-ye 葉\n- **設定板描述**：`x`\n- **設定圖**：`images/char-ye.png`\n"
        root = _tmp(self)
        f = root / "assets.md"
        f.write_text(text, encoding="utf-8")
        out_json = root / "out.json"
        err = io.StringIO()
        with mock.patch("sys.argv", ["x", "--assets-md", str(f), "--no-gate", "--out-json", str(out_json)]), \
                contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            try:
                ex.main()
                code = 0
            except SystemExit as exc:
                code = exc.code
        if code == 0 and out_json.is_file():
            data = json.loads(out_json.read_text(encoding="utf-8"))
            chars = [d for d in data if d["type"] == "character"]
            if chars:
                self.assertEqual(chars[0]["style"], "xianxia-cinematic-semireal")
                self.assertIn("預設風格 14 號", err.getvalue())
        self.assertNotIn("尚未選定角色設定板風格", err.getvalue())

    def test_styles_md_overview_and_section(self):
        text = (ROOT / "references" / "styles.md").read_text(encoding="utf-8")
        self.assertRegex(text, r"\| \*\*14（預設）\*\* \| \*\*古風寫實厚塗・電影感\*\*")
        self.assertIn("## 14. 古風寫實厚塗・電影感（預設）", text)
        self.assertIn(style_rules.VIDEO_ANCHOR, text)
        self.assertIn(style_rules.VIDEO_NEGATIVE, text)
        self.assertIn("首推 14 號", text)
        self.assertTrue((ROOT / "assets" / "styles" / "sheet-14-xianxia-cinematic-semireal.jpg").is_file())
        anchor = ex.load_style_anchor(14)
        self.assertEqual(anchor["anchor"], style_rules.VIDEO_ANCHOR)

    def test_decide_style_recommended_and_next_hint(self):
        root = _tmp(self)
        entry = decisions.decide(root, "style", "recommended", "照建議")
        self.assertEqual(entry["value"], decisions.RECOMMENDED_STYLE)
        self.assertTrue(style_rules.is_style14(entry["value"]))
        self.assertEqual(style_rules.project_style(root), decisions.RECOMMENDED_STYLE)

    def test_is_style14_ignores_template_placeholder(self):
        self.assertTrue(style_rules.is_style14("14"))
        self.assertTrue(style_rules.is_style14("xianxia-cinematic-semireal"))
        self.assertFalse(style_rules.is_style14("<預設 14＝古風寫實厚塗・電影感｜master>"))
        self.assertFalse(style_rules.is_style14("7"))
        self.assertFalse(style_rules.is_style14("半寫實厚塗"))


class GuardTests(unittest.TestCase):
    def project(self, style):
        root = _tmp(self)
        (root / "images").mkdir()
        (root / "images" / "scene.png").write_bytes(b"png")
        if style:
            decisions.decide(root, "style", style, "原話")
        return root

    def seg(self, refs=True, prompt="detailed_description:\n<Picture 1> street. " + style_rules.VIDEO_ANCHOR):
        return {"segment_id": "EP04-S02-a", "h3_prompt": prompt,
                "reference_images": [{"id": "S-street", "path": "images/scene.png", "role": "scene"}] if refs else []}

    def e28(self, result):
        return [e for e in result["errors"] if "E28" in e]

    def test_style14_segment_without_reference_is_error(self):
        root = self.project("recommended")
        self.assertTrue(self.e28(audit.audit_refs_and_subjects(self.seg(refs=False, prompt="no picture"), root)))

    def test_style14_segment_with_reference_and_clean_prompt_passes_e28(self):
        root = self.project("14")
        self.assertEqual(self.e28(audit.audit_refs_and_subjects(self.seg(), root)), [])

    def test_style14_cel_template_sentence_is_error(self):
        root = self.project("14")
        result = audit.audit_refs_and_subjects(self.seg(prompt="<Picture 1> x. " + CEL_SENTENCE), root)
        self.assertTrue(any("平塗模板句" in e for e in self.e28(result)))

    def test_other_styles_are_not_affected(self):
        root = self.project("7")
        self.assertEqual(self.e28(audit.audit_refs_and_subjects(self.seg(refs=False, prompt=CEL_SENTENCE), root)), [])

    def test_segment_level_style_key(self):
        seg = self.seg(refs=False, prompt="x")
        seg["metadata"] = {"style_key": "xianxia-cinematic-semireal"}
        self.assertTrue(self.e28(audit.audit_refs_and_subjects(seg)))

    def test_video_anchor_strips_cel_template(self):
        anchor = style_rules.video_anchor(CEL_SENTENCE + ". muted jade palette")
        self.assertTrue(anchor.startswith(style_rules.VIDEO_ANCHOR))
        self.assertEqual(style_rules.forbidden_hits(anchor), [])

    def test_compiler_uses_video_anchor_for_style14(self):
        from tests.test_h3_compiler import H3CompilerRegressionTests
        case = H3CompilerRegressionTests()
        case.setUp()
        data = case.segment()
        data["style_lock"]["anchor"] = CEL_SENTENCE
        data.setdefault("metadata", {})["style_key"] = "14"
        prompt = case.compile(data)["h3_prompt"]
        self.assertIn(style_rules.VIDEO_ANCHOR, prompt)
        self.assertEqual(style_rules.forbidden_hits(prompt), [])
        data["metadata"]["style_key"] = "7"
        self.assertIn("cel-like", case.compile(data)["h3_prompt"])


if __name__ == "__main__":
    unittest.main()
