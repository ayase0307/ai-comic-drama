# -*- coding: utf-8 -*-
"""把標準輸出入固定成 UTF-8。

Windows 上用 pipe 呼叫子程序時（comic-forge-lab 的 `python -B`），stdout 的預設編碼
是系統代碼頁（繁中通常是 cp950），而且 errors=strict。印出 ✅，或定案說明裡的
全形括號 `［`，就丟 UnicodeEncodeError：程序以 1 結束，檔案可能已經寫入。
stderr 則是 backslashreplace，同一支程式的 `--json` 有時是 UTF-8（中途 import 到
會 reconfigure 的模組）、有時是 cp950。呼叫端沒辦法用同一種編碼解。

這裡在讀寫之前把兩個串流都改成 UTF-8。UTF-8 裝得下全部字元，errors=replace
只防替代字元（lone surrogate）把程序再次打死。
"""
from __future__ import annotations

import sys


def configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            # 串流已關閉，或被測試替成沒有編碼的物件。
            continue
