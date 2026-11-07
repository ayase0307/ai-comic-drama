"""P2-5：改編政策三檔（faithful／extract／shell，導演大師對照）。

- adapt_policy：normalize／coverage_floor（extract 0.50、其餘 0.85）／decisions 讀取。
- decisions：ADAPT_POLICIES 對帳、中文別名、extract 只有 series_format=short 可定案。
- adapt_gate：extract 的刪句記帳（WARN）與下限（FAIL）；預設與 faithful 行為不變。
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT / "scripts", ROOT / "scripts" / "adapt"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import adapt_gate  # noqa: E402
import adapt_policy  # noqa: E402
import decisions as decisions_mod  # noqa: E402

LINE = "這句台詞剛好十一個字啊"  # 與 test_dialogue_first_adapt 同款 11 字句


def scene(n, lines=10, time="日", space="內", establish=2.5, pause=1.0, extra=""):
    out = [f"{n}-1 測試場{n} {time}/{space}", "人物：阿青、阿木"]
    if establish:
        out.append(f"△【建立{establish}】遠景，屋內安靜。")
    for i in range(lines):
        out.append(f"{'阿青' if i % 2 == 0 else '阿木'}：{LINE}")
        if i == 4 and pause:
            out.append(f"△【停頓{pause}】兩人對望。")
    if extra:
        out.append(extra)
    return out


END = f"<!-- episode-end: 「{LINE}」 | 換場，兩人對話告一段落 -->"


def script():
    head = ["第01集｜測試", "<!-- source: 卷1 L1-L80 -->"]
    body = [ln for i in range(1, 5) for ln in scene(i)]
    return "\n".join(head + body + [END]) + "\n"


class AdaptPolicyModuleTests(unittest.TestCase):
    def test_normalize_and_floor(self):
        self.assertIsNone(adapt_policy.normalize_policy(None))
        self.assertIsNone(adapt_policy.normalize_policy("turbo"))
        self.assertEqual(adapt_policy.normalize_policy(" EXTRACT "), "extract")
        self.assertEqual(adapt_policy.coverage_floor(None), 0.85)
        self.assertEqual(adapt_policy.coverage_floor("faithful"), 0.85)
        self.assertEqual(adapt_policy.coverage_floor("shell"), 0.85)
        self.assertEqual(adapt_policy.coverage_floor("extract"), 0.50)

    def test_policies_match_decisions_registry(self):
        self.assertEqual(tuple(decisions_mod.ADAPT_POLICIES), tuple(adapt_policy.POLICIES))

    def test_policy_from_decisions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertIsNone(adapt_policy.policy_from_decisions(root))
            decisions_mod.decide(root, "adapt_policy", "faithful", "忠實")
            self.assertEqual(adapt_policy.policy_from_decisions(root), "faithful")

    def test_policy_from_script_path_walks_up(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "adapt"
            project.mkdir()
            decisions_mod.decide(root, "adapt_policy", "faithful", "忠實")
            deep = project / "ep01" / "script-ep01.md"
            deep.parent.mkdir(parents=True)
            deep.write_text("x", encoding="utf-8")
            self.assertEqual(adapt_policy.policy_from_script_path(deep), "faithful")
            # 最近的 decisions.json 沒定案就停（不繼續往上撈）
            project2 = root / "adapt2"
            project2.mkdir()
            (project2 / "decisions.json").write_text(json.dumps({"version": 1, "decisions": []}),
                                                     encoding="utf-8")
            deep2 = project2 / "ep01" / "s.md"
            deep2.parent.mkdir(parents=True)
            deep2.write_text("x", encoding="utf-8")
            self.assertIsNone(adapt_policy.policy_from_script_path(deep2))


class AdaptPolicyDecisionTests(unittest.TestCase):
    def test_chinese_aliases_parse(self):
        self.assertEqual(decisions_mod.parse_value("adapt_policy", "忠實"), "faithful")
        self.assertEqual(decisions_mod.parse_value("adapt_policy", "抽核"), "extract")
        self.assertEqual(decisions_mod.parse_value("adapt_policy", "借殼"), "shell")

    def test_unknown_value_warns(self):
        warns = decisions_mod.value_warnings("adapt_policy", "turbo")
        self.assertTrue(any("adapt_policy" in w for w in warns), warns)
        self.assertEqual(decisions_mod.value_warnings("adapt_policy", "faithful"), [])

    def test_extract_requires_short_format(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(decisions_mod.DecisionError) as ctx:
                decisions_mod.decide(root, "adapt_policy", "extract", "長篇也要抽核")
            self.assertIn("series_format=short", str(ctx.exception))
            # 定了 short 之後才可定 extract
            decisions_mod.decide(root, "series_format", "short", "短劇模式")
            entry = decisions_mod.decide(root, "adapt_policy", "extract", "短劇抽核")
            self.assertEqual(entry["value"], "extract")

    def test_faithful_and_shell_need_no_short(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for value in ("faithful", "shell"):
                entry = decisions_mod.decide(root, "adapt_policy", value, f"{value} 政策")
                self.assertEqual(entry["value"], value)


class AdaptGatePolicyTests(unittest.TestCase):
    MISSING = "原著裡有一句完全沒出現的話"

    def test_default_missing_quote_still_fails(self):
        res = adapt_gate.run_gate(script(), quotes=[LINE, self.MISSING])
        self.assertTrue(any(f.startswith("G1") for f in res["fails"]), res["fails"])
        self.assertEqual(res["adapt_policy"], "dialogue-first（預設）")

    def test_faithful_behaves_like_default(self):
        res = adapt_gate.run_gate(script(), quotes=[LINE, self.MISSING], adapt_policy="faithful")
        self.assertTrue(any(f.startswith("G1") for f in res["fails"]), res["fails"])

    def test_extract_half_coverage_is_accounted_not_failed(self):
        # 2 句留 1 句（ratio 0.5 ≥ 抽核下限）→ 刪句記帳 WARN，不是 FAIL
        res = adapt_gate.run_gate(script(), quotes=[LINE, self.MISSING], adapt_policy="extract")
        self.assertFalse(any(f.startswith("G1") for f in res["fails"]), res["fails"])
        self.assertTrue(any("G1[extract]" in w and "記帳" in w for w in res["warns"]), res["warns"])
        self.assertEqual(res["adapt_policy"], "extract")

    def test_extract_below_floor_fails(self):
        res = adapt_gate.run_gate(script(), quotes=[self.MISSING, "另一句也沒出現的話"],
                                  adapt_policy="extract")
        self.assertTrue(any("G1[extract]" in f and "下限" in f for f in res["fails"]), res["fails"])

    def test_extract_full_coverage_is_silent(self):
        res = adapt_gate.run_gate(script(), quotes=[LINE], adapt_policy="extract")
        self.assertFalse(any(f.startswith("G1") for f in res["fails"]), res["fails"])
        self.assertFalse(any("G1[extract]" in w for w in res["warns"]), res["warns"])

    def test_shell_keeps_dialogue_gate(self):
        res = adapt_gate.run_gate(script(), quotes=[LINE, self.MISSING], adapt_policy="shell")
        self.assertTrue(any(f.startswith("G1") for f in res["fails"]), res["fails"])
        self.assertEqual(res["adapt_policy"], "shell")


if __name__ == "__main__":
    unittest.main()
