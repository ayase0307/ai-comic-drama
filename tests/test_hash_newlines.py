# -*- coding: utf-8 -*-
"""核准快照對文字檔做原始位元組 hash。Windows 預設 text mode 會把 \\n 寫成 CRLF，
同一份 JSON 的 sha256 就變了，階段核准被看成「內容已改」。寫檔必須釘死 LF。
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import decisions  # noqa: E402
import project_state as ps  # noqa: E402


def _lf_newlines_while(fn):
    seen = []
    real_open = Path.open

    def wrapped(self, mode="r", buffering=-1, encoding=None, errors=None, newline=None):
        if "w" in str(mode) and "b" not in str(mode):
            seen.append(newline)
        return real_open(self, mode, buffering, encoding=encoding, errors=errors, newline=newline)

    with mock.patch.object(Path, "open", wrapped):
        fn()
    return seen


class HashNewlineTests(unittest.TestCase):
    def test_crlf_is_a_different_stage5_artifact(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            body = json.dumps({"segments": [{"segment_id": "EP01-S01-a", "note": "霧港"}]},
                              ensure_ascii=False, indent=2) + "\n"
            path = root / "segments-ep01.json"
            path.write_bytes(body.encode("utf-8"))
            lf = ps.stage_snapshot(root, 5)["artifacts"][0]["sha256"]
            path.write_bytes(body.replace("\n", "\r\n").encode("utf-8"))
            crlf = ps.stage_snapshot(root, 5)["artifacts"][0]["sha256"]
        self.assertNotEqual(lf, crlf)

    def test_state_and_decisions_pin_lf(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)

            def write_state():
                ps.save_state(root, {"title": "霧港", "current_stage": 0, "stages": {}})

            def write_decisions():
                decisions.save(root, decisions.empty_decisions())

            for fn in (write_state, write_decisions):
                seen = _lf_newlines_while(fn)
                self.assertTrue(seen, fn)
                self.assertTrue(all(item == "\n" for item in seen), seen)
            self.assertNotIn(b"\r\n", (root / "review" / "project-state.json").read_bytes())
            self.assertNotIn(b"\r\n", (root / "decisions.json").read_bytes())
            self.assertEqual(ps.state_integrity(root), "ok")


if __name__ == "__main__":
    unittest.main()
