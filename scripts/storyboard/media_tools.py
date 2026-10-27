#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ffmpeg／ffprobe 執行檔位置（單一來源）。

以前每支腳本都直接寫 `"ffmpeg"`／`"ffprobe"`，ffmpeg 不在 PATH 的機器只能改程式。
現在依序找：

1. 環境變數 `AICD_FFMPEG`／`AICD_FFPROBE`（完整路徑）；
2. 只設 `AICD_FFMPEG` 時，ffprobe 取同目錄的 `ffprobe`（Windows 為 `ffprobe.exe`）；
3. PATH 上的 `ffmpeg`／`ffprobe`（舊行為，預設不變）。

找不到時回傳裸名稱，讓 subprocess 照舊報「找不到檔案」，不偽裝成功。
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

ENV_FFMPEG = "AICD_FFMPEG"
ENV_FFPROBE = "AICD_FFPROBE"


def _sibling(ffmpeg_path: str, name: str) -> str:
    path = Path(ffmpeg_path)
    suffix = path.suffix if path.suffix.lower() == ".exe" else ""
    candidate = path.with_name(name + suffix)
    return str(candidate) if candidate.is_file() else ""


def ffmpeg_bin() -> str:
    """ffmpeg 執行檔：AICD_FFMPEG > PATH > "ffmpeg"。"""
    explicit = os.environ.get(ENV_FFMPEG, "").strip()
    if explicit:
        return explicit
    return shutil.which("ffmpeg") or "ffmpeg"


def ffprobe_bin() -> str:
    """ffprobe 執行檔：AICD_FFPROBE > AICD_FFMPEG 同目錄 > PATH > "ffprobe"。"""
    explicit = os.environ.get(ENV_FFPROBE, "").strip()
    if explicit:
        return explicit
    ffmpeg_env = os.environ.get(ENV_FFMPEG, "").strip()
    if ffmpeg_env:
        sibling = _sibling(ffmpeg_env, "ffprobe")
        if sibling:
            return sibling
    return shutil.which("ffprobe") or "ffprobe"


def available(binary: str) -> bool:
    """執行檔是否存在（完整路徑看檔案、裸名稱看 PATH）。"""
    if not binary:
        return False
    if os.sep in binary or (os.altsep and os.altsep in binary):
        return Path(binary).is_file()
    return shutil.which(binary) is not None
