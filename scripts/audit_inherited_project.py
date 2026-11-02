#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""接手專案稽核：找出機械生成的分鏡／提示詞訊號（只讀，不改任何檔案）。

用法:
    python scripts/audit_inherited_project.py --root E:/series/專案

輸出 Markdown，直接貼進稽核報告的證據段落。判讀方式見 references/audit-inherited-project.md。
"""
import argparse
import collections
import glob
import json
import os
import re
import statistics
import sys

PUNCT_RE = re.compile(r'[。，、！？…─\-\s\u3000]')
TERM = '。！？!?'


def norm(s):
    return PUNCT_RE.sub('', s or '')


def read_json(path):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def load_shots(root):
    """回傳 [(segment_id, segment, shot)]，優先 segments-*.json，其次 layer2/*.json。"""
    shots = []
    seg_files = sorted(glob.glob(os.path.join(root, 'segments-*.json')))
    if seg_files:
        for path in seg_files:
            for seg in read_json(path).get('segments') or []:
                for shot in (seg or {}).get('shots') or []:
                    shots.append((seg.get('segment_id', '?'), seg, shot))
        return shots, 'segments'
    for path in sorted(glob.glob(os.path.join(root, 'layer2', '*.json'))):
        seg = read_json(path)
        for shot in seg.get('shots') or []:
            shots.append((seg.get('segment_id', '?'), seg, shot))
    return shots, 'layer2'


def script_speaker_map(root):
    """把 script-*.md 的每個子句對回說話者，用來抓跨角色合併。"""
    chunk2spk = {}
    for path in sorted(glob.glob(os.path.join(root, 'script-*.md'))):
        try:
            lines = open(path, encoding='utf-8').read().splitlines()
        except Exception:
            continue
        for line in lines:
            m = re.match(r'^([^\u25b3#\s][^：]{0,12})：(.+)$', line)
            if not m:
                continue
            spk, text = m.group(1), m.group(2)
            for clause in re.split(r'[。！？]', text):
                c = norm(clause)
                if len(c) >= 4:
                    chunk2spk.setdefault(c, spk)
    return chunk2spk


def pct(a, b):
    return 0.0 if not b else 100.0 * a / b


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', required=True)
    ap.add_argument('--rate-budget', type=float, default=4.6,
                    help='台詞語速上限（字/秒），預設 4.6（4 字/秒預算加約 15%% 容差）')
    ap.add_argument('--verbose', action='store_true', help='列出命中的鏡號')
    args = ap.parse_args()

    root = args.root
    if not os.path.isdir(root):
        sys.exit('找不到專案目錄: %s' % root)
    shots, source = load_shots(root)
    if not shots:
        sys.exit('讀不到任何鏡頭（找過 segments-*.json 與 layer2/*.json）')

    n = len(shots)
    rows = []

    def add(name, value, verdict):
        rows.append((name, value, verdict))

    # --- 基本量 ---
    dur = 0.0
    for _sid, seg, shot in shots:
        md = (seg.get('metadata') or {})
        v = md.get('target_duration_sec')
        if isinstance(v, (int, float)):
            dur += float(v)
    segs = len({sid for sid, _s, _sh in shots})
    add('來源／段數／鏡數', '%s，%d 段／%d 鏡／%.1f 秒' % (source, segs, n, dur), '—')

    # --- 鏡位與運鏡分佈 ---
    sizes = collections.Counter()
    moves = collections.Counter()
    for _sid, _seg, shot in shots:
        optics = shot.get('camera_optics') or {}
        if optics.get('shot_size'):
            sizes[optics.get('shot_size')] += 1
        if optics.get('movement'):
            moves[optics.get('movement')] += 1
    for label, counter in (('鏡位分佈', sizes), ('運鏡分佈', moves)):
        if len(counter) >= 4:
            lo, hi = min(counter.values()), max(counter.values())
            ratio = (hi / float(lo)) if lo else 99.0
            verdict = '輪播疑慮（%.2f×）' % ratio if ratio <= 1.25 else 'ok'
            add(label, '／'.join('%s %d' % kv for kv in counter.most_common(8)), verdict)

    # --- 五小節重複率 ---
    for field in ('motion', 'performance', 'camera'):
        vals = []
        for _sid, _seg, shot in shots:
            fp = shot.get('five_part_en') or {}
            v = fp.get(field)
            if isinstance(v, str) and v.strip():
                vals.append(re.sub(r'\d+(\.\d+)?', '#', re.sub(r'\{[^}]+\}', '@', v)))
        if vals:
            distinct = len(set(vals))
            ratio = distinct / float(len(vals))
            add('five_part_en.%s 去重率' % field,
                '%d 種／%d 鏡（%.0f%%）' % (distinct, len(vals), 100 * ratio),
                '模板套字' if ratio < 0.6 else 'ok')

    # --- shot_intent 句式 ---
    patterns = collections.Counter()
    for _sid, _seg, shot in shots:
        si = shot.get('shot_intent') or {}
        a = si.get('audience') if isinstance(si, dict) else None
        if isinstance(a, str) and a.strip():
            p = re.sub(r'「[^」]*」', '「…」', a)
            p = re.sub(r'\d+', '#', p)
            patterns[p] += 1
    total_intent = sum(patterns.values())
    if total_intent:
        add('shot_intent.audience 句式',
            '%d 種句式／%d 鏡' % (len(patterns), total_intent),
            'mail-merge' if len(patterns) / float(total_intent) < 0.2 else 'ok')

    # --- 台詞 ---
    speaking = 0
    with_dialogue = 0
    lengths = []
    over = []
    comments = []
    merged = []
    chunk2spk = script_speaker_map(root)
    for sid, _seg, shot in shots:
        da = shot.get('dialogue_and_audio') or {}
        if not da.get('has_dialogue'):
            continue
        with_dialogue += 1
        line = da.get('line_verbatim') or ''
        if '<!--' in line:
            comments.append(sid)
        if norm(line):
            lengths.append(norm(line))
        sw = da.get('speech_window') or {}
        try:
            start = float(sw.get('start'))
            end = float(sw.get('end'))
        except (TypeError, ValueError):
            start = end = None
        if start is not None and end is not None and end > start and norm(line):
            speaking += 1
            rate = len(norm(line)) / (end - start)
            if rate > args.rate_budget:
                over.append((sid, round(rate, 2)))
        if chunk2spk:
            speakers = set()
            for clause in re.split(r'[。！？]', line):
                c = norm(clause)
                if len(c) < 4:
                    continue
                for known, spk in chunk2spk.items():
                    if c in known or known in c:
                        speakers.add(spk)
                        break
            if len(speakers) > 1:
                merged.append((sid, sorted(speakers)))

    add('有台詞鏡頭比例', '%d／%d（%.0f%%）' % (with_dialogue, n, pct(with_dialogue, n)),
        '無反應／建立鏡' if pct(with_dialogue, n) >= 95 else 'ok')
    if lengths:
        med = statistics.median([len(x) for x in lengths])
        add('台詞行長（中位數）', '%d 字' % med, '已切碎' if med < 12 else 'ok')
    if speaking:
        add('語速超標（> %.1f 字/秒）' % args.rate_budget,
            '%d／%d（%.0f%%），最高 %s' % (len(over), speaking, pct(len(over), speaking),
                                          max([r for _s, r in over]) if over else '—'),
            '鏡長先定、台詞硬塞' if pct(len(over), speaking) > 20 else 'ok')
    add('台詞含 <!-- 標記', '%d 條' % len(comments), '標記漏進 TTS' if comments else 'ok')
    if chunk2spk:
        add('跨角色合併台詞', '%d 條（%.0f%%）' % (len(merged), pct(len(merged), max(1, with_dialogue))),
            '一個聲音念多人' if merged else 'ok')

    # --- 構圖與鏡位對帳 ---
    ots_single = []
    for sid, _seg, shot in shots:
        optics = shot.get('camera_optics') or {}
        if 'OTS' in str(optics.get('shot_size') or ''):
            if len(shot.get('character_ids') or []) < 2:
                ots_single.append(sid)
    if ots_single:
        add('過肩鏡但畫面 < 2 人', '%d 鏡' % len(ots_single), '鏡位與構圖未對帳')

    # --- 後端格式與綁定 ---
    empty_refmods = 0
    six_section = 0
    three_col = 0
    prop_inject = []
    for sid, seg, shot in shots:
        if 'refmods' in seg and not (seg.get('refmods') or []):
            empty_refmods += 1
        prompt = shot.get('h3_prompt') or ''
        if prompt.lstrip().startswith('subject_definitions'):
            six_section += 1
        if 'integrated_multimodal_description' in prompt:
            three_col += 1
        if 'without a reference image appears' in prompt:
            prop_inject.append(sid)
    add('提示詞格式', '六段式 %d／三欄 %d' % (six_section, three_col),
        '六段式＝ref2va，REMIX 要三欄' if six_section > three_col else 'ok')
    if source == 'segments':
        add('段層 refmods 空的段數', '%d／%d' % (empty_refmods, segs),
            '沒走 remix 綁定' if empty_refmods else 'ok')
    if prop_inject:
        add('無主詞道具注入', '%d 段' % len(prop_inject), '道具會長在錯的人身上')

    # --- 輸出 ---
    print('# 接手稽核：機械生成訊號\n')
    print('| 檢查 | 數值 | 判定 |')
    print('|---|---|---|')
    for name, value, verdict in rows:
        print('| %s | %s | %s |' % (name, value, verdict))
    if args.verbose:
        for label, items in (('語速超標', over), ('含 <!--', comments), ('跨角色合併', merged),
                             ('過肩單人', ots_single), ('道具注入', prop_inject)):
            if items:
                print('\n- %s：%s' % (label, ', '.join(str(x) for x in items[:20])))
    print('\n> 判定只是線索，不是結論。命中的項目要打開該鏡的文字或成片確認，報告只寫確認過的。')


if __name__ == '__main__':
    main()
