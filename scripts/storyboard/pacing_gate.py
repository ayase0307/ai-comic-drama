#!/usr/bin/env python3
"""pacing_gate.py — v2 語速／台詞量門禁。

依據（數字出處見 references/pacing-dialogue-evidence.md）：
  事件測試 V1（3.32 字/s、最大空隙 0.93s）使用者評為最舒服；V0 2.61 太慢；V2 4.11 但空隙 1.48s 跳。
  TC_07：靜默 0.6–1.2s 有效、>1.5s 觀眾以為壞掉。

輸入 JSON：{"segments":[{"id","duration","kind":"dialogue|action|ambient",
  "prompt": "...", "allow_slow": false,
  "lines":[{"text","start","end","cut_start":false,"beat_pause":false}],
  "shots":[{"start","end","has_dialogue":bool,"source_action":false}]}]}

切鏡後開口：標 beat_pause 的句子和 D4 一樣可到 1.2s。

FAIL：句間空隙 >1.5s（beat_pause 亦不得超過）；提示詞把「講話」寫慢（says slowly、語速放緩、慢慢說…；運鏡／動作的慢照樣通過；allow_slow 例外）；單句 >35 字。
WARN：句間空隙 >1.0s（beat_pause 0.6–1.2s 例外）；切鏡後 >0.5s 才開口；
      對話段密度 <2.8 或 >3.9 字/s（目標 3.0–3.6；給了 shots 時分母扣段首／段尾連續無台詞鏡，
      合計最多 5s；≤4 字短句鏡超出 max(1.2s, 字數÷4＋0.5s) 的秒數也扣，和 validate_storyboard D2 同一算法）；每 15s 開口 <6 次（等比折算、下限 3）；
      無台詞鏡 >5s；連續無台詞 >10s；
      有人聲鏡比例 <80%（Work_01／Work_08 幾乎每鏡有人聲，含旁白；反應鏡用 L-cut 延續台詞）；
        原著無台詞動作鏡標 `source_action: true` 不計入分母（無台詞鏡 >5s、連續 >10s 照常警告）；
      提示詞含末 1 秒靜止句（tail_freeze_hold；無廢片原則：不生成要剪掉的秒數。唯一例外是 E3 雙人引子，見下）。

雙人引子（spatial-consistency.md §7）：shots[0] 標 `dual_lead_in: true` 時，那一鏡組裝會剪掉、不是成片，
上面所有檢查（密度、有人聲鏡比例、切鏡後開口、無台詞鏡／連續無台詞、開口次數）都先拿掉它、時間與 duration
整段扣掉引子秒數再算（`dual_lead_in.strip_pacing`）。
"""
import json, re, sys, unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dual_lead_in  # noqa: E402
from dialogue_density import short_line_excess  # noqa: E402

GAP_WARN, GAP_FAIL = 1.0, 1.5
BEAT_PAUSE_MAX = 1.2
ONSET_MAX = 0.5
LINE_HARD_MAX = 35
DENSITY_LOW, DENSITY_HIGH, ONSETS_PER_15 = 2.8, 3.9, 6
SILENT_SHOT_MAX, SILENT_RUN_MAX = 5.0, 10.0
# 只擋「講話」寫慢：運鏡／動作的 slow、緩、慢 放行（使用者 10/30：語速不要寫慢，鏡頭寫慢可通過）
_SLOW_EN = r"\bslow(?:ly|er|est|ed)?\b"
_SPEECH_EN = (r"\b(?:say|says|said|saying|speak\w*|spoke\w*|ask\w*|repl\w*|answer\w*|whisper\w*|murmur\w*|"
              r"mutter\w*|talk\w*|utter\w*|voice\w*|tone|delivery|delivers?|speech|dialogue|lines?|"
              r"pronounc\w*|enunciat\w*|narrat\w*|intones?|recit\w*)\b")
_GAP_EN = r"(?:\W+\w+){0,3}?\W+"  # 相距 ≤3 個字
_SLOW_ZH = r"[緩缓慢]"
_SPEECH_ZH_AFTER = r"(?:說|说|道|問|问|講|讲|念|唸|答|吐字|開口|开口|語速|语速|語氣|语气|聲音|声音|嗓音|語調|语调|口吻|發音|发音)"
_SPEECH_ZH_BEFORE = r"(?:語速|语速|語氣|语气|聲音|声音|嗓音|語調|语调|口吻|說話|说话|講話|讲话|發音|发音|吐字|台詞|台词)"
SPEECH_SLOW_RE = re.compile(
    rf"{_SLOW_EN}{_GAP_EN}{_SPEECH_EN}|{_SPEECH_EN}{_GAP_EN}{_SLOW_EN}|{_SLOW_EN}\W+{_SPEECH_EN}|"
    rf"{_SPEECH_EN}\W+{_SLOW_EN}|\bdrawl\w*|"
    rf"{_SLOW_ZH}.{{0,3}}?{_SPEECH_ZH_AFTER}|{_SPEECH_ZH_BEFORE}.{{0,4}}?{_SLOW_ZH}", re.I)
# 帶說話人標記 (S1) 或引號台詞的子句裡出現慢詞，除非慢詞緊貼運鏡／動作詞
_DIALOGUE_CLAUSE = re.compile(r"\(S\d+\)|[「」“”『』\"]")
_ANY_SLOW = re.compile(rf"{_SLOW_EN}|{_SLOW_ZH}", re.I)
_CAMERA_NEAR = re.compile(
    r"camera|pan|push\w*|pull\w*|dolly|zoom\w*|orbit\w*|track\w*|tilt\w*|truck\w*|crane|motion|"
    r"turn\w*|walk\w*|rais\w*|lift\w*|mov\w*|鏡頭|镜头|運鏡|运镜|推|拉|搖|摇|移|轉|转|抬|走|起|落|飄|飘|動作|动作", re.I)


def speech_slow(prompt):
    """回傳把講話寫慢的片段；沒有則 None。"""
    m = SPEECH_SLOW_RE.search(prompt)
    if m:
        return m.group(0)
    for clause in re.split(r"[.\n。；;!?！？]", prompt):
        if not _DIALOGUE_CLAUSE.search(clause):
            continue
        for sm in _ANY_SLOW.finditer(clause):
            near = clause[max(0, sm.start() - 15):sm.end() + 15]
            if not _CAMERA_NEAR.search(near):
                return sm.group(0)
    return None
VOICED_SHOT_MIN = 0.8
MONTAGE_ALLOWANCE_SEC = 5.0  # 與 dialogue_density.MONTAGE_ALLOWANCE_SEC（D2）同值
TAIL_FREEZE_RE = re.compile(r"final second holds still", re.I)


def chars(t):
    return sum(1 for c in t if not unicodedata.category(c).startswith(("P", "Z", "S", "C")))


def _edge_silence(shots):
    """段首、段尾連續無台詞鏡的秒數（D2 蒙太奇額度的來源）。"""
    def run(seq):
        t = 0.0
        for s in seq:
            if s.get("has_dialogue"):
                break
            t += s["end"] - s["start"]
        return t
    if not any(s.get("has_dialogue") for s in shots):
        return 0.0, 0.0
    return run(shots), run(list(reversed(shots)))


def _voiced_ratio_shots(shots):
    """有人聲鏡比例的分母：去掉標了 source_action（原著無台詞動作）的無台詞鏡。
    沒標的無台詞鏡照算（#117：反應鏡用 L-cut 延續台詞）。"""
    return [s for s in shots if not (s.get("source_action") and not s.get("has_dialogue"))]


def check(seg):
    seg = dual_lead_in.strip_pacing(seg)  # 引子組裝時剪掉，不計入任何節奏數字
    f, w, sid = [], [], seg.get("id", "?")
    hit = speech_slow(seg.get("prompt", ""))
    if hit and not seg.get("allow_slow"):
        f.append(f"{sid} 提示詞把講話寫慢（慢詞）：{hit}")
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
        onset_max = BEAT_PAUSE_MAX if l.get("beat_pause") else ONSET_MAX  # v118 #11：與 D4 一致
        if l.get("cut_start") and l["start"] > onset_max:
            w.append(f"{sid} 切鏡後 {l['start']}s 才開口")
    shots = seg.get("shots", [])
    lead, tail = _edge_silence(shots)
    allowance = min(MONTAGE_ALLOWANCE_SEC, lead + tail)
    if seg.get("kind") == "dialogue" and lines:
        n = sum(chars(l["text"]) for l in lines)
        d = seg["duration"]
        # SB-3：≤4 字短句鏡多出的秒數也和 D2 一樣不計入分母
        short = 0.0
        for s in shots:
            if s.get("has_dialogue"):
                k = sum(chars(l["text"]) for l in lines if s["start"] - 0.011 <= l["start"] < s["end"])
                short += short_line_excess(s["end"] - s["start"], k)
        denom = max(d - allowance - short, 0.1)  # v118 #6：和 D2 同一算法（扣段首／段尾無台詞鏡，最多 5s）
        note = (f"（已扣段首／段尾無台詞 {allowance:.2f}s" + (f"、短句鏡多出 {short:.2f}s" if short else "")
                + f"；整段 {n/d:.2f}）") if (allowance or short) else ""
        if n / denom < DENSITY_LOW:
            w.append(f"{sid} 對話密度 {n/denom:.2f} 字/s <{DENSITY_LOW}（空跑）{note}")
        elif n / denom > DENSITY_HIGH:
            w.append(f"{sid} 對話密度 {n/denom:.2f} 字/s >{DENSITY_HIGH}（趕）{note}")
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
    if shots:
        # v118 #9：原著無台詞動作鏡（source_action:true）不計入分母，不逼補台詞
        counted = _voiced_ratio_shots(shots)
        voiced = sum(1 for s in counted if s.get("has_dialogue"))
        if counted and voiced / len(counted) < VOICED_SHOT_MIN:
            exempt = len(shots) - len(counted)
            w.append(f"{sid} 有人聲鏡 {voiced}/{len(counted)} <{VOICED_SHOT_MIN:.0%}"
                     + (f"（已豁免原著動作鏡 {exempt} 個）" if exempt else "")
                     + "（反應鏡用 L-cut 延續台詞或補旁白）")
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
