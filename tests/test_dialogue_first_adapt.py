# -*- coding: utf-8 -*-
"""台詞優先改編：dialogue_budget.py（估時、預算、分集）與 adapt_gate.py（自檢門）。"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "adapt"))

import adapt_gate  # noqa: E402
import dialogue_budget as db  # noqa: E402

LINE = "這句台詞剛好十一個字啊"  # 11 字


def scene(n, lines=10, time="日", space="內", establish=2.5, pause=1.0, speaker="阿青", extra=""):
    out = [f"{n}-1 測試場{n} {time}/{space}", "人物：阿青、阿木"]
    if establish:
        out.append(f"△【建立{establish}】遠景，屋內安靜。")
    for i in range(lines):
        out.append(f"{speaker if i % 2 == 0 else '阿木'}：{LINE}")
        if i == 4 and pause:
            out.append(f"△【停頓{pause}】兩人對望。")
    if extra:
        out.append(extra)
    return out


def script(scenes=4, source=True, **kw):
    head = ["第01集｜測試"] + (["<!-- source: 卷1 L1-L80 -->"] if source else [])
    body = [ln for i in range(1, scenes + 1) for ln in scene(i, **kw)]
    return "\n".join(head + body) + "\n"


QUOTES = [LINE]


class Budget(unittest.TestCase):
    def test_150s_budget_is_450_540(self):
        b = db.budget(150)
        self.assertEqual((b["chars_min"], b["chars_max"]), (450, 540))
        self.assertEqual(db.budget(125)["chars_min"], 375)

    def test_role_rates_follow_pr116(self):
        self.assertEqual(db.role_rate("阿青", "", ["阿青"]), 4.0)
        self.assertEqual(db.role_rate("阿木", "", ["阿青"]), 4.5)
        self.assertEqual(db.role_rate("旁白", "", []), 5.5)
        self.assertEqual(db.role_rate("阿青", "內心", ["阿青"]), 5.5)

    def test_duration_formula(self):
        sc = db.parse_script("1-1 屋 日/內\n阿木：一二三四五六七八九\n阿木：一二三四五六七八九\n△【停頓1.0】靜。\n△走動（並行不計時）\n")
        st = db.scene_stats(sc.scenes)
        self.assertAlmostEqual(st["seconds"], 18 / 4.5 + 0.3 + 1.0, places=2)
        self.assertEqual(st["chars"], 18)

    def test_invented_and_vo_flags(self):
        sc = db.parse_script("1-1 屋 日/內\n阿青（內心）：她在說謊。\n阿木：是嗎？ <!-- invented -->\n")
        d = sc.scenes[0].dialogue
        self.assertTrue(d[0].is_vo)
        self.assertTrue(d[1].invented)

    def test_split_appends_next_scene_when_under_floor(self):
        sc = db.parse_script(script(scenes=6))
        eps = db.split_episodes(sc.scenes, 150)
        # 每場 110 字：4 場 440 字 < 450 下限仍接第 5 場？第 5 場會超過 150 秒才切
        for ep in eps:
            self.assertLessEqual(db.scene_stats(ep)["seconds"], 150)
        self.assertGreaterEqual(len(eps[0]), 4)

    def test_split_stops_once_floor_reached(self):
        sc = db.parse_script(script(scenes=8, lines=24, establish=0, pause=0))
        eps = db.split_episodes(sc.scenes, 150)
        self.assertTrue(all(len(ep) >= 1 for ep in eps))
        self.assertGreaterEqual(len(eps), 4)


class Gate(unittest.TestCase):
    def run_gate(self, text, quotes=QUOTES, **kw):
        return adapt_gate.run_gate(text, quotes=quotes, **kw)

    def test_good_script_passes(self):
        res = self.run_gate(script())
        self.assertEqual(res["fails"], [], res)

    def test_missing_source_quote_fails(self):
        res = self.run_gate(script(), quotes=QUOTES + ["原著裡有一句完全沒出現的話"])
        self.assertTrue(any(f.startswith("G1") for f in res["fails"]))

    def test_invented_line_does_not_count_as_coverage(self):
        text = script().replace(f"阿青：{LINE}", f"阿青：{LINE} <!-- invented -->")
        text = text.replace(f"阿木：{LINE}", f"阿木：{LINE} <!-- invented -->")
        res = self.run_gate(text)
        self.assertTrue(any(f.startswith("G1") for f in res["fails"]))
        self.assertTrue(res["invented"])

    def test_condensed_quote_still_covered(self):
        quotes = ["我說啊，這句台詞剛好十一個字啊！"]  # 去語助詞後仍 ≥85% 對上
        res = self.run_gate(script(), quotes=quotes)
        self.assertFalse(any(f.startswith("G1") for f in res["fails"]), res["fails"])

    def test_source_quotes_extracted_from_novel(self):
        self.assertEqual(adapt_gate.source_quotes("他說：「走吧。」她答：「好。」"), ["走吧。", "好。"])

    def test_missing_source_material_fails(self):
        res = adapt_gate.run_gate(script())
        self.assertTrue(any(f.startswith("G1") for f in res["fails"]))

    def test_density_too_low_fails(self):
        res = self.run_gate(script(establish=2.5, pause=1.0, lines=2))
        self.assertTrue(any(f.startswith("G3") for f in res["fails"]))

    def test_long_line_fails(self):
        res = self.run_gate(script(extra="阿木：" + "字" * 36))
        self.assertTrue(any(f.startswith("G5") for f in res["fails"]))

    def test_long_silence_fails(self):
        res = self.run_gate(script(extra="△【建立6】空景。\n△【停頓5】空景。"))
        self.assertTrue(any(f.startswith("G7") for f in res["fails"]))

    def test_heading_format(self):
        res = self.run_gate(script(time="午", space="內外"))
        self.assertTrue(any(f.startswith("G9") and "標題" in f for f in res["fails"]))

    def test_over_150s_fails(self):
        res = self.run_gate(script(scenes=7))
        self.assertTrue(any("預估片長" in f for f in res["fails"]))

    def test_source_range_required(self):
        res = self.run_gate(script(source=False))
        self.assertTrue(any(f.startswith("G12") for f in res["fails"]))

    def test_content_safety(self):
        res = self.run_gate(script(extra="△一名未成年少年走過。"))
        self.assertTrue(any(f.startswith("G10") for f in res["fails"]))

    def test_vo_share_warns(self):
        text = script().replace("阿木：", "阿青（內心）：")
        res = self.run_gate(text)
        self.assertTrue(any(w.startswith("G6") for w in res["warns"]))

    def test_end_hook_narration_fails(self):
        res = self.run_gate(script(extra="旁白：下集更精彩"))
        self.assertTrue(any("鉤子" in f for f in res["fails"]))

    def test_cli_exit_codes(self):
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "ep.md"
            q = Path(d) / "q.json"
            p.write_text(script(), encoding="utf-8")
            q.write_text(json.dumps(QUOTES, ensure_ascii=False), encoding="utf-8")
            self.assertEqual(adapt_gate.main([str(p), "--source-quotes", str(q)]), 0)
            self.assertEqual(adapt_gate.main([str(p)]), 1)


if __name__ == "__main__":
    unittest.main()
