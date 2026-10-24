# -*- coding: utf-8 -*-
"""純文字 txt 章名（無 # 號）、目錄區、重複章名、楔子／尾聲。"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "adapt"))

import extract_chapter as ec  # noqa: E402


def scan(text):
    return [(c.chapter_num, c.chapter_title) for c in ec.scan_novel_structure(text.splitlines(True))]


class PlainHeadings(unittest.TestCase):
    def test_plain_headings_with_tab_and_fullwidth_space(self):
        b = "內文。\n" * 4
        got = scan("楔子\n" + b + "第一章\t蘇醒\n" + b + "第十二章\u3000尾聲\n" + b)
        self.assertEqual(got, [(0, "楔子"), (1, "第一章 蘇醒"), (12, "第十二章 尾聲")])

    def test_toc_block_is_skipped(self):
        toc = "目錄\n第一章 搶親\n第二章 轉職當強盜\n\n"
        body = "第一章 搶親\n" + "內文。\n" * 5 + "第二章 轉職當強盜\n" + "內文。\n" * 5
        got = scan(toc + body)
        self.assertEqual([n for n, _ in got], [1, 2])
        chs = ec.scan_novel_structure((toc + body).splitlines(True))
        self.assertGreater(chs[0].start_line, 4)

    def test_bare_number_line_followed_by_titled_line_merges(self):
        got = scan("第一章\n\n　　第一章 愛偷聽的狐狸精\n內文。\n內文。\n內文。\n內文。\n")
        self.assertEqual(got, [(1, "第一章 愛偷聽的狐狸精")])

    def test_sentence_starting_with_chapter_word_is_not_heading(self):
        self.assertEqual(scan("第一章說完，他笑了。「好。」\n"), [])

    def test_markdown_headings_still_work(self):
        got = scan("## 第一集\n### 第一章 如你所願\n內文\n")
        self.assertEqual(got, [(1, "第一章 如你所願")])


if __name__ == "__main__":
    unittest.main()
