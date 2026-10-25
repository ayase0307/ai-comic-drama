import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "voice"))
import voice_align  # noqa: E402


class _Model:
    def __init__(self, hang_first):
        self.hang_first, self.calls = hang_first, []

    def transcribe(self, audio, **kw):
        self.calls.append(kw)
        if self.hang_first and not kw.get("vad_filter"):
            time.sleep(3)
        return iter(["x"]), None


class AsrTimeoutTest(unittest.TestCase):
    def test_normal(self):
        m = _Model(False)
        res, retried = voice_align._transcribe_guarded(m, None, "p", 1)
        self.assertEqual((res, retried, len(m.calls)), (["x"], False, 1))

    def test_hang_retries_with_vad(self):
        m = _Model(True)
        res, retried = voice_align._transcribe_guarded(m, None, "p", 0.2)
        self.assertTrue(retried)
        self.assertTrue(m.calls[1]["vad_filter"])
        self.assertFalse(m.calls[1]["condition_on_previous_text"])

    def test_both_hang(self):
        class M:
            def transcribe(self, a, **k):
                time.sleep(3)
        with self.assertRaises(RuntimeError):
            voice_align._transcribe_guarded(M(), None, "p", 0.1)


if __name__ == "__main__":
    unittest.main()
