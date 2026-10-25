import http.client, sys, tempfile, threading, unittest
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
for d in ("voice", "edit"):
    sys.path.insert(0, str(ROOT / "scripts" / d))
import voice_align  # noqa: E402
import range_server  # noqa: E402

FAKE = {"幹": "gan", "干": "gan", "屁": "pi", "匹": "pi", "笑": "xiao", "小": "xiao"}


class PinyinTest(unittest.TestCase):
    def setUp(self):
        self.old = voice_align._PINYIN
        voice_align._PINYIN = lambda t: [FAKE.get(c, c) for c in t]

    def tearDown(self):
        voice_align._PINYIN = self.old

    def test_homophones_match(self):
        self.assertEqual(voice_align.overlap("干笑屁", "幹小匹"), 1.0)

    def test_fallback_chars(self):
        voice_align._PINYIN = None
        self.assertEqual(voice_align.tokens("干笑"), ["干", "笑"])
        self.assertLess(voice_align.overlap("干笑屁", "幹小匹"), 1.0)


class RangeTest(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(range_server.parse_range("bytes=0-3", 10), (0, 3))
        self.assertEqual(range_server.parse_range("bytes=5-", 10), (5, 9))
        self.assertEqual(range_server.parse_range("bytes=-4", 10), (6, 9))
        self.assertEqual(range_server.parse_range("bytes=20-", 10), "bad")
        self.assertIsNone(range_server.parse_range(None, 10))

    def test_206(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "a.bin").write_bytes(bytes(range(100)))
            srv = ThreadingHTTPServer(("127.0.0.1", 0), partial(range_server.RangeHandler, directory=d))
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            try:
                conn = http.client.HTTPConnection("127.0.0.1", srv.server_port)
                conn.request("GET", "/a.bin", headers={"Range": "bytes=10-19"})
                r = conn.getresponse()
                self.assertEqual(r.status, 206)
                self.assertEqual(r.read(), bytes(range(10, 20)))
                self.assertEqual(r.getheader("Content-Range"), "bytes 10-19/100")
                conn.close()
            finally:
                srv.shutdown(); srv.server_close()


if __name__ == "__main__":
    unittest.main()
