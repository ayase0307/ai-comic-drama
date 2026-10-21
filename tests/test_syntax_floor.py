"""語法下限護欄：本 skill 宣告 Python 3.10+，但 `ast.parse(feature_version=...)`
不會攔「f-string 的 {} 內含反斜線」——那是 3.12 的 tokenizer 改變（PEP 701）。
在 3.11 上它會直接 SyntaxError，讓整個測試模組匯入失敗（CI 就是這樣紅的）。

這裡用文字掃描當護欄：任何 f-string 的替換欄位出現反斜線就失敗，並指出位置。
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FSTRING = re.compile(r"""\bf(?:[rR]{0,1})(?P<q>'''|\"\"\"|'|\")(?P<body>.*?)(?P=q)""", re.S)
FIELD = re.compile(r"\{([^{}]*)\}")


def offending_fields(text: str):
    for match in FSTRING.finditer(text):
        for field in FIELD.finditer(match.group("body")):
            expr = field.group(1)
            if "\\" in expr:
                line = text[: match.start()].count("\n") + 1
                yield line, expr


class SyntaxFloorTests(unittest.TestCase):
    def test_no_backslash_inside_fstring_expressions(self):
        problems = []
        for path in list((ROOT / "scripts").rglob("*.py")) + list((ROOT / "tests").rglob("*.py")):
            if path.name == Path(__file__).name:
                continue
            for line, expr in offending_fields(path.read_text(encoding="utf-8-sig")):
                problems.append(f"{path.relative_to(ROOT)}:{line}: {expr[:60]}")
        self.assertEqual(problems, [],
                         "f-string 的 {} 內不可有反斜線（Python 3.11 及更早會 SyntaxError）：\n"
                         + "\n".join(problems))


if __name__ == "__main__":
    unittest.main()
