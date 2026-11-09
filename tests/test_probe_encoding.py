# -*- coding: utf-8 -*-
"""ffprobe／ffmpeg 的 stderr 若不是預設編碼，不能把好影片判成解不開，也不能讓收件 traceback。

Windows pipe 用系統代碼頁解 ffmpeg 輸出。中文路徑印在 stderr 時，位元組對不上就
UnicodeDecodeError。`project_state._ffprobe` 把它當成 ValueError 吞掉，回 None，
階段 6 於是報「影片無法完整解碼」。`probe_video_duration` 沒有接住，收件直接中斷。
"""
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "storyboard"))

import project_state  # noqa: E402
import submit_h3_segments  # noqa: E402


def _write_tool(directory: Path, name: str, body: str) -> Path:
    path = directory / name
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


class ProbeEncodingTests(unittest.TestCase):
    def test_ffprobe_duration_survives_non_utf8_stderr(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            tools = root / "bin"
            tools.mkdir()
            _write_tool(tools, "ffmpeg", "#!/bin/sh\nprintf '\\377' >&2\nexit 0\n")
            _write_tool(tools, "ffprobe",
                        "#!/bin/sh\nprintf '\\377' >&2\nprintf '%s\\n' '{\"format\":{\"duration\":\"1.5\"}}'\nexit 0\n")
            video = root / "霧港.mp4"
            video.write_bytes(b"0" * 2048)
            old = os.environ.get("PATH", "")
            os.environ["PATH"] = str(tools) + os.pathsep + old
            self.addCleanup(lambda: os.environ.__setitem__("PATH", old))
            probed = project_state._ffprobe(video)
        self.assertIsNotNone(probed)
        self.assertAlmostEqual(probed["duration"], 1.5)

    def test_probe_video_duration_survives_non_utf8_stderr(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            tool = _write_tool(root, "ffprobe", "#!/bin/sh\nprintf '\\377' >&2\nprintf '4.25\\n'\nexit 0\n")
            old = os.environ.get("AICD_FFPROBE")
            os.environ["AICD_FFPROBE"] = str(tool)
            def restore():
                if old is None:
                    os.environ.pop("AICD_FFPROBE", None)
                else:
                    os.environ["AICD_FFPROBE"] = old
            self.addCleanup(restore)
            duration = submit_h3_segments.probe_video_duration(root / "霧港.mp4")
        self.assertAlmostEqual(duration, 4.25)


if __name__ == "__main__":
    unittest.main()
