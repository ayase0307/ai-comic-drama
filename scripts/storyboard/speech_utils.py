"""台詞字數計算：handoff_to_skeleton.py、validate_storyboard.py 與 validate_structure.py 共用，確保估時、語速與台詞比對用同一把尺。"""
import string
import unicodedata

_ASCII_PUNCT = frozenset(string.punctuation)


def normalize_speech(text: str) -> str:
    """去掉所有空白與中英文標點，保留其餘字元；台詞逐字比對與計字都以此為準。"""
    return "".join(
        ch
        for ch in text
        if not (ch.isspace() or ch in _ASCII_PUNCT or unicodedata.category(ch).startswith("P"))
    )


def count_speech_chars(text: str) -> int:
    """去掉所有空白與中英文標點後剩下的字元數；語速（字/秒）一律以此計算。"""
    return len(normalize_speech(text))
