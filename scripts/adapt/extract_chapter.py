#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
extract_chapter.py — 小說大檔目錄掃描、單章抽取與 Pandoc/Markdown 清洗工具

功能：
1. `--input <小說路徑>`（必填）：讀取小說大檔（支援數萬至數十萬行大檔）。
2. `--list`：掃描全書的集/卷（## ...）與章節（### ... 或中文章名），輸出目錄樹表格或 `--json` 結構化資料。
   支援 `--volume <N>` 僅列出指定集數。
3. `--volume <V> --chapter <C> --output <輸出路徑>`：精確抽取指定卷章，並執行自動清洗：
   - 清除標題尾端 Pandoc 屬性標記（如 `{#Section...}`、`{style="..."}`）；
   - 清除 HTML 標籤、````{=html}` 程式碼區塊、Pandoc 容器 `:::`、錨點 `[]{#...}`、圖片 `![...]`；
   - 清除行尾軟折行反斜線 `\` 與整行反斜線；
   - 段落正規化（每段獨立一行，或保留乾淨段落空行）。
4. 內建字數與引號對白發音字數統計（與 `speech_utils.py` 相同計字標準）。

僅使用 Python 標準庫。
"""

from __future__ import annotations

import argparse
import io
import json
import os
from pathlib import Path
import re
import string
import sys
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

# 確保 Windows 終端輸出 UTF-8
# 用 reconfigure 而不是換掉 sys.stdout／sys.stderr：被別的腳本 import（例如門禁在同一個行程裡
# 呼叫 compare_adaptation → estimate_duration）時，換掉的舊物件被回收會關掉底層 buffer，
# Windows 上會出現「lost sys.stderr」整個行程掛掉。
if sys.platform.startswith("win"):
    for _stream in (sys.stdout, sys.stderr):
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="replace")

_ASCII_PUNCT = frozenset(string.punctuation)

CN_NUM_MAP = {
    "零": 0, "〇": 0, "一": 1, "二": 2, "兩": 2, "三": 3, "四": 4,
    "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
    "十一": 11, "十二": 12, "十三": 13, "十四": 14, "十五": 15,
    "十六": 16, "十七": 17, "十八": 18, "十九": 19, "二十": 20,
    "三十": 30, "四十": 40, "五十": 50, "六十": 60, "七十": 70,
    "八十": 80, "九十": 90, "百": 100
}


def parse_cn_number(s: str) -> Optional[int]:
    """將中文數字或阿拉伯數字字串轉為整數。例如 '一'->1, '第十三集'->13, '12'->12。"""
    s = s.strip()
    if s.isdigit():
        return int(s)

    # 提取第X集/章中的數字部分
    m = re.search(r"第?([一二兩三四五六七八九十百\d]+)[集卷部章回節]?", s)
    if not m:
        return None
    core = m.group(1)
    if core.isdigit():
        return int(core)

    if core in CN_NUM_MAP:
        return CN_NUM_MAP[core]

    # 處理複合中文數字，如 '二十一', '十三'
    total = 0
    curr = 0
    for ch in core:
        val = CN_NUM_MAP.get(ch)
        if val is None:
            return None
        if val == 10:
            if curr == 0:
                curr = 1
            total += curr * 10
            curr = 0
        elif val == 100:
            if curr == 0:
                curr = 1
            total += curr * 100
            curr = 0
        else:
            curr += val
    total += curr
    return total if total > 0 else None


def normalize_speech(text: str) -> str:
    """去掉所有空白與中英文標點，保留純發音字元（與 speech_utils.py 一致）。"""
    return "".join(
        ch
        for ch in text
        if not (ch.isspace() or ch in _ASCII_PUNCT or unicodedata.category(ch).startswith("P"))
    )


def extract_dialogues(text: str) -> List[str]:
    """提取文字中的所有引號內對白。支援「...」、『...』、“...”、\"...\"。"""
    pattern = re.compile(r"「([^」]+)」|『([^』]+)』|“([^”]+)”|\"([^\"]+)\"")
    results = []
    for m in pattern.finditer(text):
        for g in m.groups():
            if g:
                results.append(g)
    return results


def clean_novel_lines(lines: List[str]) -> List[str]:
    """清洗 Pandoc 轉檔產生的反斜線、HTML、屬性標記等雜質。"""
    cleaned: List[str] = []
    in_html_block = False

    for line in lines:
        s = line.strip()

        # 1. 處理 HTML 程式碼區塊 ```{=html} ... ```
        if s.startswith("```{=html}"):
            in_html_block = True
            continue
        if in_html_block:
            if s.startswith("```"):
                in_html_block = False
            continue

        # 2. 跳過容器、錨點、Markdown 圖片
        if s.startswith(":::") or s.startswith("[]") or s.startswith("!["):
            continue

        # 3. 移除行內 HTML 標籤
        s = re.sub(r"<[^>]+>", "", s)

        # 4. 移除 Pandoc 標題屬性 {#...} 與 {style="..."}
        s = re.sub(r"\{#[^}]*\}", "", s)
        s = re.sub(r"\{style=[^}]*\}", "", s)

        # 5. 移除行尾反斜線與多餘反斜線
        s = re.sub(r"\\+$", "", s).strip()

        # 6. 若為空或僅含反斜線則略過
        if not s or s == "\\":
            continue

        cleaned.append(s)

    return cleaned


class NovelChapter:
    def __init__(
        self,
        volume_num: int,
        volume_title: str,
        chapter_num: int,
        chapter_title: str,
        start_line: int,
        end_line: int,
    ):
        self.volume_num = volume_num
        self.volume_title = volume_title
        self.chapter_num = chapter_num
        self.chapter_title = chapter_title
        self.start_line = start_line
        self.end_line = end_line

    def to_dict(self) -> Dict[str, Any]:
        return {
            "volume_num": self.volume_num,
            "volume_title": self.volume_title,
            "chapter_num": self.chapter_num,
            "chapter_title": self.chapter_title,
            "start_line": self.start_line,
            "end_line": self.end_line,
        }


# 純文字章名：行首「第N章」，後面可接空白／全形空白／tab 與 ≤30 字章名；排除對白與長句
PLAIN_CHAPTER_RE = re.compile(r"^第([一二兩三四五六七八九十百零〇\d]+)[章回](?:[\s\u3000]+[^「」“”。]{0,30})?$")
PLAIN_SPECIAL_RE = re.compile(r"^(楔子|序章|序|尾聲|後記|番外.{0,20})$")


def scan_novel_structure(lines: List[str]) -> List[NovelChapter]:
    """掃描小說中的集/卷與章節結構，回傳所有章節定位。"""
    chapters: List[NovelChapter] = []

    current_vol_num = 1
    current_vol_title = "第一集"

    # 記錄所有標題點：(line_index, type, num, title)
    # type: 'vol' | 'ch'
    raw_nodes = []
    plain_lines = set()

    for idx, line in enumerate(lines):
        line_no = idx + 1
        s = line.strip()

        # 比對集/卷：## 第一集 或 # 第一集
        m_vol = re.match(r"^#{1,2}\s+(第[一二三四五六七八九十百\d]+[集卷部])(?:\s+.*)?$", s)
        if m_vol:
            raw_title = m_vol.group(1).strip()
            v_num = parse_cn_number(raw_title) or (current_vol_num + 1)
            raw_nodes.append((line_no, "vol", v_num, raw_title))
            continue

        # 比對章節：### 第一章 如你所願 或 # 後記 / 序章
        m_ch = re.match(r"^#{2,3}\s+(第[一二三四五六七八九十百\d]+[章回節].*?)(?:\s+\{[^}]*\})?$", s)
        if m_ch:
            raw_title = re.sub(r"\{#[^}]*\}", "", m_ch.group(1)).strip()
            # 嘗試抓章號
            m_cnum = re.search(r"第([一二三四五六七八九十百\d]+)[章回節]", raw_title)
            c_num = parse_cn_number(m_cnum.group(1)) if m_cnum else len(raw_nodes) + 1
            raw_nodes.append((line_no, "ch", c_num, raw_title))
            continue

        # 特殊章節：# 後記、# 序章、# 尾聲
        m_spec = re.match(r"^#{1,3}\s+(後記|序章|尾聲|番外.*)(?:\s+\{[^}]*\})?$", s)
        if m_spec:
            raw_title = re.sub(r"\{#[^}]*\}", "", m_spec.group(1)).strip()
            raw_nodes.append((line_no, "ch", 999, raw_title))
            continue

        # 純文字 txt 章節：行首「第一章 蘇醒」「第十章\t前有狼後有虎」（無 # 號）
        m_plain = PLAIN_CHAPTER_RE.match(s)
        if m_plain:
            c_num = parse_cn_number(m_plain.group(1))
            title = re.sub(r"[\s\u3000]+", " ", s).strip()
            # 「第一章」單獨一行、下一個非空行又是「第一章 標題」：合併成一筆（取有標題的那行）
            if raw_nodes and raw_nodes[-1][1] == "ch" and raw_nodes[-1][2] == c_num \
                    and line_no - raw_nodes[-1][0] <= 3:
                raw_nodes.pop()
            raw_nodes.append((line_no, "ch", c_num if c_num is not None else len(raw_nodes) + 1, title))
            plain_lines.add(line_no)
            continue

        m_plain_spec = PLAIN_SPECIAL_RE.match(s)
        if m_plain_spec:
            raw_nodes.append((line_no, "ch", 0 if m_plain_spec.group(1) in ("楔子", "序章", "序") else 999, s))
            plain_lines.add(line_no)
            continue

    # 純文字檔開頭常有目錄（一串連續章名、底下沒有內文）：下一個標題就在 3 行內的純文字章名視為目錄項，丟掉
    raw_nodes = [
        node for i, node in enumerate(raw_nodes)
        if not (node[0] in plain_lines and i + 1 < len(raw_nodes) and raw_nodes[i + 1][0] - node[0] <= 3)
    ]

    # 組裝起訖行號
    for i, (l_no, kind, num, title) in enumerate(raw_nodes):
        if kind == "vol":
            current_vol_num = num
            current_vol_title = title
        elif kind == "ch":
            next_line = raw_nodes[i + 1][0] - 1 if i + 1 < len(raw_nodes) else len(lines)
            ch = NovelChapter(
                volume_num=current_vol_num,
                volume_title=current_vol_title,
                chapter_num=num,
                chapter_title=title,
                start_line=l_no,
                end_line=next_line,
            )
            chapters.append(ch)

    return chapters


def analyze_chapter_metrics(cleaned_lines: List[str]) -> Dict[str, Any]:
    """計算清洗後章節的文字與對白指標。"""
    # 略過第一行章節標題
    body_lines = cleaned_lines[1:] if cleaned_lines and cleaned_lines[0].startswith("#") else cleaned_lines
    full_text = "\n".join(body_lines)

    total_chars = len(normalize_speech(full_text))
    dialogues = extract_dialogues(full_text)
    dialogue_chars = sum(len(normalize_speech(d)) for d in dialogues)
    narrative_chars = max(0, total_chars - dialogue_chars)

    return {
        "line_count": len(cleaned_lines),
        "total_chars": total_chars,
        "dialogue_count": len(dialogues),
        "dialogue_chars": dialogue_chars,
        "narrative_chars": narrative_chars,
        "dialogue_ratio": round((dialogue_chars / total_chars * 100), 1) if total_chars > 0 else 0.0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="小說大檔目錄掃描、單章抽取與 Pandoc 清洗工具")
    parser.add_argument("--input", type=str, required=True, help="小說大檔路徑 (Markdown / txt)")
    parser.add_argument("--list", action="store_true", help="列出小說章節目錄結構與字數統計")
    parser.add_argument("--volume", type=str, default=None, help="指定集數/卷號 (支援 1 或 '第一集')")
    parser.add_argument("--chapter", type=str, default=None, help="指定章號 (支援 1 或 '第一章')")
    parser.add_argument("--output", type=str, default=None, help="抽取章節之輸出檔案路徑")
    parser.add_argument("--json", action="store_true", help="輸出 JSON 格式")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"[錯誤] 找不到小說檔案：{input_path}", file=sys.stderr)
        return 1

    try:
        with open(input_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except Exception as exc:
        print(f"[錯誤] 讀取檔案失敗：{exc}", file=sys.stderr)
        return 1

    chapters = scan_novel_structure(lines)
    if not chapters:
        print("[錯誤] 未能在檔案中識別出任何章節標題 (## 或 ###)", file=sys.stderr)
        return 1

    target_vol = parse_cn_number(args.volume) if args.volume else None
    target_ch = parse_cn_number(args.chapter) if args.chapter else None

    # 1. 處理 --list 目錄清單
    if args.list:
        listed = []
        for ch in chapters:
            if target_vol is not None and ch.volume_num != target_vol:
                continue

            raw_slice = lines[ch.start_line - 1 : ch.end_line]
            cleaned = clean_novel_lines(raw_slice)
            metrics = analyze_chapter_metrics(cleaned)

            info = ch.to_dict()
            info.update(metrics)
            listed.append(info)

        if args.json:
            print(json.dumps(listed, ensure_ascii=False, indent=2))
        else:
            print(f"=== 小說目錄結構與體量統計 ({input_path.name}) ===")
            vol_group = ""
            for item in listed:
                if item["volume_title"] != vol_group:
                    vol_group = item["volume_title"]
                    print(f"\n【{vol_group}】")
                print(
                    f"  第 {item['chapter_num']:2d} 章 | {item['chapter_title']:<25s} | "
                    f"行 {item['start_line']:6d} ~ {item['end_line']:6d} | "
                    f"總字數: {item['total_chars']:6d} 字 | "
                    f"對白: {item['dialogue_count']:3d} 句 ({item['dialogue_chars']:5d} 字, {item['dialogue_ratio']:4.1f}%)"
                )
        return 0

    # 2. 處理指定章節抽取
    if target_vol is not None and target_ch is not None:
        matched = None
        for ch in chapters:
            if ch.volume_num == target_vol and ch.chapter_num == target_ch:
                matched = ch
                break

        if not matched:
            print(f"[錯誤] 找不到指定章節：第 {target_vol} 集 第 {target_ch} 章", file=sys.stderr)
            return 1

        raw_slice = lines[matched.start_line - 1 : matched.end_line]
        cleaned = clean_novel_lines(raw_slice)
        metrics = analyze_chapter_metrics(cleaned)

        result_text = "\n".join(cleaned) + "\n"

        if args.output:
            out_path = Path(args.output)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(result_text, encoding="utf-8")
            if args.json:
                res = matched.to_dict()
                res.update(metrics)
                res["output_file"] = str(out_path)
                print(json.dumps(res, ensure_ascii=False, indent=2))
            else:
                print(f"✅ 成功抽取並清洗章節至：{out_path}")
                print(
                    f"  標題: {matched.volume_title} {matched.chapter_title}\n"
                    f"  原始行號: {matched.start_line} ~ {matched.end_line}\n"
                    f"  清洗後段落行數: {metrics['line_count']} 行\n"
                    f"  純字數: {metrics['total_chars']} 字\n"
                    f"  對白: {metrics['dialogue_count']} 句（發音字數: {metrics['dialogue_chars']} 字，佔 {metrics['dialogue_ratio']}%）"
                )
        else:
            if args.json:
                res = matched.to_dict()
                res.update(metrics)
                res["content"] = cleaned
                print(json.dumps(res, ensure_ascii=False, indent=2))
            else:
                print(result_text)

        return 0

    print("提示：請使用 --list 查看目錄，或使用 --volume <V> --chapter <C> --output <路徑> 抽取章節。", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
