#!/usr/bin/env python3
"""pacing_gate.py — v2 語速／台詞量門禁。

依據（數字出處見 references/pacing-dialogue-evidence.md）：
  事件測試 V1（3.32 字/s、最大空隙 0.93s）使用者評為最舒服；V0 2.61 太慢；V2 4.11 但空隙 1.48s 跳。
  TC_07：靜默 0.6–1.2s 有效、>1.5s 觀眾以為壞掉。

輸入 JSON：{"segments":[{"id","duration","kind":"dialogue|action|ambient",
  "prompt": "...", "allow_slow": false,
  "lines":[{"text","start","end","cut_start":false,"beat_pause":false}],
  "shots":[{"start","end","has_dialogue":bool}]}]}

FAIL：句間空隙 >1.5s（beat_pause 亦不得超過）；提示詞含 slow（allow_slow 例外）；單句 >35 字。
WARN：句間空隙 >1.0s（beat_pause 0.6–1.2s 例外）；切鏡後 >0.5s 才開口；
      對話段整段密度 <2.8 或 >3.9 字/s（目標 3.0–3.6）；每 15s 開口 <6 次（等比折算、下限 3）；
      無台詞鏡 >5s；連續無台詞 >10s；
      有人聲鏡比例 <80%（Work_01／Work_08 幾乎每鏡有人聲，含旁白；反應鏡用 L-cut 延續台詞）；
      提示詞含末 1 秒靜止句（tail_freeze_hold；無廢片原則：不生成要剪掉的秒數）。
"""
import json, re, sys, unicodedata

GAP_WARN, GAP_FAIL = 1.0, 1.5
BEAT_PAUSE_MAX = 1.2
ONSET_MAX = 0.5
LINE_HARD_MAX = 35
DENSITY_LOW, DENSITY_HIGH, ONSETS_PER_15 = 2.8, 3.9, 6
SILENT_SHOT_MAX, SILENT_RUN_MAX = 5.0, 10.0
VOICED_SHOT_MIN = 0.8
TAIL_FREEZE_RE = re.compile(r"final second holds still", re.I)
SLOW_RE = re.compile(r"\bslow", re.I)


def chars(t):
    return sum(1 for c in t if not unicodedata.category(c).startswith(("P", "Z", "S", "C")))


def check(seg):
    f, w, sid = [], [], seg.get("id", "?")
    if SLOW_RE.search(seg.get("prompt", "")) and not seg.get("allow_slow"):
        f.append(f"{sid} 提示詞含 slow")
    lines = sorted(seg.get("lines", []), key=lambda l: l["start"])
    for a, b in zip(lines, lines[1:]):
        gap = round(b["start"] - a["end"], 2)
        if gap > GAP_FAIL:
            f.append(f"{sid} 句間空隙 {gap}s >{GAP_FAIL}s")
        elif b.get("beat_pause"):
            if gap > BEAT_PAUSE_MAX:
                w.append(f"{sid} beat_pause {gap}s >{BEAT_PAUSE_MAX}s")
        elif gap > GAP_WARN:
            w.append(f"{sid} 句間空隙 {gap}s >{GAP_WARN}s")
    for l in lines:
        if chars(l["text"]) > LINE_HARD_MAX:
            f.append(f"{sid} 單句 {chars(l['text'])} 字 >{LINE_HARD_MAX}")
        if l.get("cut_start") and l["start"] > ONSET_MAX:
            w.append(f"{sid} 切鏡後 {l['start']}s 才開口")
    if seg.get("kind") == "dialogue" and lines:
        n = sum(chars(l["text"]) for l in lines)
        d = seg["duration"]
        if n / d < DENSITY_LOW:
            w.append(f"{sid} 對話密度 {n/d:.2f} 字/s <{DENSITY_LOW}（空跑）")
        elif n / d > DENSITY_HIGH:
            w.append(f"{sid} 對話密度 {n/d:.2f} 字/s >{DENSITY_HIGH}（趕）")
        need = max(3, round(ONSETS_PER_15 * d / 15))
        if len(lines) < need:
            w.append(f"{sid} 開口 {len(lines)} 次 <{need}")
    run = 0.0
    for s in seg.get("shots", []):
        dur = s["end"] - s["start"]
        if s.get("has_dialogue"):
            run = 0.0
            continue
        if dur > SILENT_SHOT_MAX:
            w.append(f"{sid} 無台詞鏡 {dur:.1f}s >{SILENT_SHOT_MAX}s")
        run += dur
        if run > SILENT_RUN_MAX:
            w.append(f"{sid} 連續無台詞 {run:.1f}s >{SILENT_RUN_MAX}s")
            run = 0.0
    shots = seg.get("shots", [])
    if shots:
        voiced = sum(1 for s in shots if s.get("has_dialogue"))
        if voiced / len(shots) < VOICED_SHOT_MIN:
            w.append(f"{sid} 有人聲鏡 {voiced}/{len(shots)} <{VOICED_SHOT_MIN:.0%}（反應鏡用 L-cut 延續台詞或補旁白）")
    if TAIL_FREEZE_RE.search(seg.get("prompt", "") or ""):
        w.append(f"{sid} 提示詞含末 1 秒靜止（tail_freeze_hold）：這 1 秒會被剪掉或變空檔，改關閉、最後一句說完留 0.3s")
    return f, w


def main(argv):
    data = json.load(open(argv[1], encoding="utf-8"))
    F, W = [], []
    for seg in data.get("segments", []):
        f, w = check(seg)
        F += f; W += w
    for x in W: print("WARN", x)
    for x in F: print("FAIL", x)
    print(f"pacing_gate: {len(F)} FAIL / {len(W)} WARN")
    return 1 if F else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv) if len(sys.argv) > 1 else 2)
