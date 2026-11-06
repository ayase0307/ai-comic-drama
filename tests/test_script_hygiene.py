"""P1-2：adapt_gate 劇本格式衛生（G15–G21，導演大師 12 條的缺項；全部只警告）。"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "adapt"))

import adapt_gate  # noqa: E402

SCRIPT = """第1集

1-1 後巷 夜/內
△建立：巷口路燈閃了一下。
洛年：「誰在那裡？」
系統：「偵測到未知生命體。」
儀器：「讀數異常。」
眾人：「我們走吧。」
葉瑋珊：（冷冷地看著他。）
洛年：「他心想這樣下去不行。」
洛年：「走吧。」他轉身走向巷口。
葉瑋珊：「看清楚了。」鏡頭推近她的臉。
△特寫：地上的黃蟲。
<!-- episode-end: 「黃蟲在地上蠕動」 | 第一章停在收妖前 -->
<!-- source: 卷1 Ln1-Ln10 -->
"""


class HygieneWarningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = adapt_gate.run_gate(SCRIPT)
        cls.warns = "\n".join(cls.result["warns"])

    def test_g15_non_human_speaker(self):
        self.assertIn("G15", self.warns)
        self.assertIn("系統", self.warns)
        self.assertIn("儀器", self.warns)

    def test_g16_parenthetical_action_as_dialogue(self):
        self.assertIn("G16", self.warns)

    def test_g18_third_person_thought(self):
        self.assertIn("G18", self.warns)
        self.assertIn("他心想", self.warns)

    def test_g19_trailing_action_and_crowd_speaker(self):
        self.assertGreaterEqual(self.warns.count("G19"), 2, self.warns)
        self.assertIn("眾人", self.warns)
        self.assertIn("他轉身", self.warns)

    def test_g21_camera_terms_in_body_and_action(self):
        self.assertGreaterEqual(self.warns.count("G21"), 2, self.warns)

    def test_clean_lines_do_not_trigger(self):
        # 「誰在那裡？」與「看清楚了。」是乾淨台詞，不該被 G15–G21 點名
        for line in ("誰在那裡", "看清楚了"):
            for code in ("G15", "G16", "G18", "G19", "G21"):
                for w in self.result["warns"]:
                    if code in w and line in w:
                        self.fail(f"{code} 誤報乾淨台詞：{w}")

    def test_warnings_only_never_fail(self):
        self.assertNotIn("G15", "\n".join(self.result["fails"]))
        self.assertNotIn("G21", "\n".join(self.result["fails"]))


if __name__ == "__main__":
    unittest.main()
