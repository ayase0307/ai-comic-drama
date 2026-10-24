# -*- coding: utf-8 -*-
"""小說原稿讀檔：自動判斷編碼，不靜默吞掉亂碼。

中文小說 txt 常見 UTF-16（有 BOM）、UTF-8（含 BOM）、Big5/CP950、GBK/GB18030。
過去一律用 utf-8 + errors="replace" 讀，UTF-16 與 Big5 檔會整檔變成 U+FFFD，
工具只回「找不到章節」，看不出是編碼問題。
"""
from __future__ import annotations

from pathlib import Path
from typing import Tuple

# 依序嘗試；cp950 是 Big5 的超集（台灣常見），放在 gb18030 前面，
# 因為 gb18030 幾乎能「成功」解任何位元組，放前面會把 Big5 誤判成簡體亂碼。
FALLBACK_ENCODINGS = ("utf-8", "cp950", "big5hkscs", "gb18030")


def detect_encoding(data: bytes) -> str:
    if data.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return "utf-16"
    for enc in FALLBACK_ENCODINGS:
        try:
            data.decode(enc)
            return enc
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError("auto", data[:1], 0, 1, "無法以 UTF-8／UTF-16／Big5／GB18030 解碼")


def read_novel_text(path: Path | str) -> Tuple[str, str]:
    """回傳 (文字, 偵測到的編碼)；換行統一為 \\n。"""
    data = Path(path).read_bytes()
    enc = detect_encoding(data)
    text = data.decode(enc)
    return text.replace("\r\n", "\n").replace("\r", "\n"), enc
