import unittest

from tests import test_h3_compiler as fixtures
from tests.test_audit_refs_and_segments import make_prompt

compiler = fixtures.compiler
from audit_refs_and_segments import lint_h3_prompt


class H3PositiveConstraintTests(unittest.TestCase):
    def test_asset_exclusion_list_stays_in_qa_metadata(self):
        fixture = fixtures.H3CompilerRegressionTests()
        fixture.setUp()
        source = fixture.segment()
        exclusion = source["style_lock"]["negative"]
        result = compiler.compile_segment_h3(source, fixture.registry, auto_lora=False)
        self.assertNotIn("negative constraints:", result["h3_prompt"].lower())
        self.assertNotIn(exclusion, result["h3_prompt"])
        self.assertEqual(result["metadata"]["qa_exclusions"], exclusion)
        self.assertEqual(result["metadata"]["style_lock"]["negative"], "")
        self.assertEqual(source["style_lock"]["negative"], exclusion)

    def test_negative_prompt_blocks_are_blocking_not_warnings(self):
        for header in ("negative constraints:", "negative_prompt:", "Negative Prompt:"):
            with self.subTest(header=header):
                result = lint_h3_prompt(make_prompt(["a person waits", "a hand settles", "a door closes"]) + "\n" + header + " clones, extra limbs")
                self.assertTrue(any("negative" in e.lower() for e in result["errors"]), result)

    def test_music_section_name_is_not_a_negative_prompt_block(self):
        result = lint_h3_prompt(make_prompt(["a person waits", "a hand settles", "a door closes"]))
        self.assertFalse(any("negative prompt" in e.lower() for e in result["errors"]), result)


if __name__ == "__main__":
    unittest.main()
