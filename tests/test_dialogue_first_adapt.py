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


END = f"<!-- episode-end: 「{LINE}」 | 換場，兩人對話告一段落 -->"


def script(scenes=4, source=True, end=END, **kw):
    head = ["第01集｜測試"] + (["<!-- source: 卷1 L1-L80 -->"] if source else [])
    body = [ln for i in range(1, scenes + 1) for ln in scene(i, **kw)]
    return "\n".join(head + body + ([end] if end else [])) + "\n"


QUOTES = [LINE]


class Budget(unittest.TestCase):
    def test_reference_budget_is_informational_rate(self):
        b = db.budget(150)
        self.assertEqual((b["chars_min"], b["chars_max"]), (450, 540))
        self.assertFalse(hasattr(db, "DEFAULT_EPISODE_SECONDS"))

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

    def test_no_break_means_one_episode_of_any_length(self):
        sc = db.parse_script(script(scenes=12, end=""))
        eps = db.split_episodes(sc)
        self.assertEqual(len(eps), 1)
        self.assertGreater(db.scene_stats(eps[0])["seconds"], 300)  # 無上限

    def test_split_inside_scene_at_any_sentence(self):
        text = "1-1 屋 日/內\n阿木：第一句。\n阿木：第二句。\n<!-- episode-end: 「第二句」 | 揭曉 -->\n阿木：第三句。\n1-2 院 夜/外\n阿青：第四句。\n"
        sc = db.parse_script(text)
        self.assertEqual(sc.breaks[0]["anchor"], "第二句")
        self.assertEqual(sc.breaks[0]["reason"], "揭曉")
        eps = db.split_episodes(sc)
        self.assertEqual([sum(len(s.dialogue) for s in ep) for ep in eps], [2, 2])
        self.assertEqual(eps[1][0].heading, "1-1 屋 日/內")  # 場被切開，後半沿用場次標題

    def test_break_comment_is_not_a_source(self):
        sc = db.parse_script(script())
        self.assertEqual(sc.sources, ["卷1 L1-L80"])


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

    def test_long_episode_has_no_length_cap(self):
        res = self.run_gate(script(scenes=12), target_seconds=150)
        self.assertEqual(res["fails"], [], res["fails"])
        self.assertEqual(res["length_info"]["target_seconds"], 150)

    def test_short_episode_has_no_floor(self):
        res = self.run_gate(script(scenes=1))
        self.assertEqual(res["fails"], [], res["fails"])

    def test_missing_break_fails(self):
        res = self.run_gate(script(end=""))
        self.assertTrue(any(f.startswith("G13") for f in res["fails"]))

    def test_break_needs_reason_and_short_anchor(self):
        res = self.run_gate(script(end="<!-- episode-end: 「" + "長" * 31 + "」 | -->"))
        g13 = [f for f in res["fails"] if f.startswith("G13")]
        self.assertTrue(any("錨點" in f for f in g13) and any("理由" in f for f in g13), g13)

    def test_break_anchor_must_be_in_source(self):
        novel = f"他說：「{LINE}」"
        ok = adapt_gate.run_gate(script(), novel_text=novel)
        self.assertFalse(any(f.startswith("G13") for f in ok["fails"]), ok["fails"])
        bad = adapt_gate.run_gate(script(end="<!-- episode-end: 「原著沒有這句」 | 轉折 -->"), novel_text=novel)
        self.assertTrue(any("不在原著" in f for f in bad["fails"]))

    def test_hook_narration_checked_at_every_break(self):
        text = "第01集\n<!-- source: 卷1 L1 -->\n1-1 屋 日/內\n阿木：走吧。\n旁白：究竟他會怎麼做？\n<!-- episode-end: 「走吧」 | 轉折 -->\n阿木：好。\n<!-- episode-end: 「好」 | 換場 -->\n"
        res = adapt_gate.run_gate(text, quotes=[])
        self.assertTrue(any("鉤子旁白" in f for f in res["fails"]), res["fails"])

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
