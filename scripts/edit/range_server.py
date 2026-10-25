#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""支援 HTTP Range（206）的靜態檔伺服器。

`python -m http.server` 不支援 Range，iPhone Safari 無法播放審核頁的 <video>。
用法：python3 scripts/edit/range_server.py [--dir review] [--port 8000] [--bind 0.0.0.0]
"""
from __future__ import annotations

import argparse
import functools
import os
import re
import shutil
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

_RANGE = re.compile(r"bytes=(\d*)-(\d*)$")


def parse_range(header, size):
    """回傳 (start, end)（含）；沒有 Range 回 None；不合法回 'bad'。"""
    if not header:
        return None
    m = _RANGE.match(header.strip())
    if not m or (not m.group(1) and not m.group(2)):
        return "bad"
    if m.group(1):
        start = int(m.group(1))
        end = int(m.group(2)) if m.group(2) else size - 1
    else:  # suffix：最後 N 位元組
        n = int(m.group(2))
        start, end = max(0, size - n), size - 1
    end = min(end, size - 1)
    if start >= size or start > end:
        return "bad"
    return start, end


class RangeHandler(SimpleHTTPRequestHandler):
    def send_head(self):
        rng = self.headers.get("Range")
        path = self.translate_path(self.path)
        if not rng or not os.path.isfile(path):
            return super().send_head()
        size = os.path.getsize(path)
        parsed = parse_range(rng, size)
        if parsed == "bad":
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{size}")
            self.end_headers()
            return None
        start, end = parsed
        f = open(path, "rb")
        f.seek(start)
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(path))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(end - start + 1))
        self.end_headers()
        self._remaining = end - start + 1
        return f

    def copyfile(self, source, outputfile):
        remaining = getattr(self, "_remaining", None)
        if remaining is None:
            return super().copyfile(source, outputfile)
        self._remaining = None
        shutil.copyfileobj(_Limited(source, remaining), outputfile)

    def end_headers(self):
        self.send_header("Accept-Ranges", "bytes")
        super().end_headers()


class _Limited:
    def __init__(self, f, n):
        self.f, self.n = f, n

    def read(self, size=-1):
        if self.n <= 0:
            return b""
        size = self.n if size is None or size < 0 else min(size, self.n)
        data = self.f.read(size)
        self.n -= len(data)
        return data


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dir", default=".")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--bind", default="0.0.0.0")
    a = ap.parse_args(argv)
    handler = functools.partial(RangeHandler, directory=a.dir)
    srv = ThreadingHTTPServer((a.bind, a.port), handler)
    print(f"serving {a.dir} on {a.bind}:{a.port}（支援 Range）")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
