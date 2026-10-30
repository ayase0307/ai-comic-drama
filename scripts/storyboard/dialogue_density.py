"""分鏡階段台詞密度閘門（PR #118）。

與 PR #116 pacing_gate 同一套節奏數字，但在 Layer 2 分鏡（validate_storyboard）就攔下：
- 有台詞的段：密度 < 3.0 字/秒 → FAIL（> 3.9 → WARN）。
  分母扣掉「無台詞蒙太奇額度」：段首／段尾連續無台詞鏡頭，合計最多 5 秒。
- 純無台詞段（建立／蒙太奇）總長 > 5 秒 → FAIL（請壓短或讓旁白蓋過去）。
- 句間空隙：> 0.9 秒 → FAIL；標記 beat_pause 的句子可到 1.2 秒，超過一樣 FAIL。
  短句之間的動作必須和說話重疊，不可另外佔秒數。
- 每個切點各自量「切鏡後多久開口」：> 0.5 秒 → FAIL（切點時已有句子在講 = 0）。
  只看有台詞的鏡頭；無台詞鏡頭由蒙太奇額度管。
刻意的靜場戲可在 metadata.density_exempt_reason 寫明理由，D2 降為 WARN（D1/D3/D4 不豁免）。
時間檢查需要 dialogue_and_audio.line_timecodes（段內相對秒數）；沒有時只做密度檢查。
雙人引子（shots[0].dual_lead_in，spatial-consistency.md §7）組裝時剪掉，D1–D4 先拿掉它、時間整段前移再算。
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from speech_utils import count_speech_chars

try:
    import dual_lead_in
except ImportError:  # pragma: no cover - 套件匯入路徑
    from . import dual_lead_in

DENSITY_MIN = 3.0
DENSITY_WARN_MAX = 3.9
MONTAGE_ALLOWANCE_SEC = 5.0
GAP_MAX = 0.9
BEAT_PAUSE_MIN, BEAT_PAUSE_MAX = 0.6, 1.2
CUT_ONSET_MAX = 0.5
_EPS = 0.011

# v118 規則衝突 #4／#5／#10：舊閘門（4.2 字/秒、說話 >60%、單句 >15 字）改成和 #116／#118 同一套數字。
ONSCREEN_RATE_WARN, ONSCREEN_RATE_MAX = 4.5, 4.7  # 畫內：女角估時 4.5；正臉對嘴上限 4.7（#116）
VO_RATE_WARN, VO_RATE_MAX = 5.5, 5.8              # 旁白／畫外／內心 VO：估時 5.5；Work_01 旁白 5.2–5.8
LINE_SUGGEST_MAX = 18                              # #116：單句建議 ≤18 字（硬上限 35 由 pacing_gate 管）
SPEECH_SHARE_WARN = 0.90                           # #118：說話佔片長 75–90%，超過 90% 才提醒
VO_AUDIO_TYPES = {"narration", "voiceover", "vo", "inner", "offscreen", "os", "o.s.", "v.o."}
_VO_SPEAKERS = {"旁白", "narrator", "narration", "畫外音", "內心", "v.o.", "vo", "os", "o.s."}
_VO_SPEC_TERMS = ("voiceover", "v.o", "inner voice", "off-screen", "offscreen", "內心", "畫外", "旁白")


def is_voiceover_line(dlg: Dict[str, Any]) -> bool:
    """這句台詞沒有可見的嘴（旁白／畫外／內心 VO）。"""
    if str(dlg.get("audio_type") or "").strip().lower() in VO_AUDIO_TYPES:
        return True
    if str(dlg.get("offscreen_form") or "").strip().lower() in ("voiceover", "offscreen"):
        return True
    if str(dlg.get("speaker") or "").strip().lower() in _VO_SPEAKERS:
        return True
    spec = " ".join(str(dlg.get(k) or "") for k in ("voice_4d_spec", "voice_4d_spec_en")).lower()
    return any(t in spec for t in _VO_SPEC_TERMS)


def rate_limits(dlg: Dict[str, Any]) -> Tuple[float, float]:
    """（WARN 線, FAIL 線）字/秒：畫內對嘴 4.5／4.7，VO 5.5／5.8。"""
    return (VO_RATE_WARN, VO_RATE_MAX) if is_voiceover_line(dlg) else (ONSCREEN_RATE_WARN, ONSCREEN_RATE_MAX)


def shot_lines(dlg: Dict[str, Any]) -> List[str]:
    """這鏡要念的所有台詞：line_verbatim ＋ extra_lines（同鏡接話，v118 #2）。"""
    out = [(dlg.get("line_verbatim") or "").strip()]
    out += [str((x or {}).get("line_verbatim") or "").strip() for x in (dlg.get("extra_lines") or [])
            if isinstance(x, dict)]
    return [t for t in out if t]


def _dlg(shot: Dict[str, Any]) -> Dict[str, Any]:
    return shot.get("dialogue_and_audio") or {}


def _has_line(shot: Dict[str, Any]) -> bool:
    d = _dlg(shot)
    return bool(d.get("has_dialogue")) and bool((d.get("line_verbatim") or "").strip())


def _span(shot: Dict[str, Any]) -> Tuple[float, float]:
    return float(shot.get("start_time", 0)), float(shot.get("end_time", 0))


def check_dialogue_density(data: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    data = dual_lead_in.strip_layer2(data)  # 引子組裝時剪掉：不吃蒙太奇額度、不算密度分母、不算切點
    errors: List[str] = []
    warnings: List[str] = []
    shots = data.get("shots") or []
    seg = data.get("segment_id", "?")
    if not shots:
        return errors, warnings
    total = max(_span(s)[1] for s in shots)
    talking = [s for s in shots if _has_line(s)]

    if not talking:
        if total > MONTAGE_ALLOWANCE_SEC + _EPS:
            errors.append(
                f"[D1 無台詞段過長] {seg} 全段無台詞 {total:.2f}s > {MONTAGE_ALLOWANCE_SEC:.0f}s；"
                "蒙太奇壓到 5 秒內，或讓旁白蓋過去。")
        return errors, warnings

    # 段首／段尾連續無台詞鏡頭 = 蒙太奇額度（最多 5 秒）
    lead = 0.0
    for s in shots:
        if _has_line(s):
            break
        lead += _span(s)[1] - _span(s)[0]
    tail = 0.0
    for s in reversed(shots):
        if _has_line(s):
            break
        tail += _span(s)[1] - _span(s)[0]
    allowance = min(MONTAGE_ALLOWANCE_SEC, lead + tail)
    chars = sum(count_speech_chars(t) for s in talking for t in shot_lines(_dlg(s)))
    denom = max(total - allowance, 0.1)
    dens = chars / denom
    meta = data.get("metadata") or {}
    exempt = (meta.get("density_exempt_reason") or "").strip()
    if dens < DENSITY_MIN - 1e-9:
        (warnings if exempt else errors).append(
            f"[D2 台詞密度過低] {seg} {chars} 字 / {denom:.2f}s = {dens:.2f} 字/秒 < {DENSITY_MIN}"
            f"（已扣蒙太奇額度 {allowance:.2f}s）；動作要和說話重疊，不要另外佔秒數。"
            + (f"（豁免：{exempt}）" if exempt else ""))
    elif dens > DENSITY_WARN_MAX:
        warnings.append(f"[D2 台詞密度偏高] {seg} {dens:.2f} 字/秒 > {DENSITY_WARN_MAX}")

    lines = []
    for s in talking:
        tc = list(_dlg(s).get("line_timecodes") or [])
        lines.extend(tc)
        known = {str(l.get("text") or "").strip() for l in tc}
        for ex in _dlg(s).get("extra_lines") or []:  # 同鏡接話沒寫進 line_timecodes 時，用它自己的 speech_window
            w = (ex or {}).get("speech_window") if isinstance(ex, dict) else None
            text = str((ex or {}).get("line_verbatim") or "").strip() if isinstance(ex, dict) else ""
            if tc and isinstance(w, dict) and w.get("start") is not None and w.get("end") is not None and text not in known:
                lines.append({"text": text, "start": w["start"], "end": w["end"],
                              "beat_pause": bool(ex.get("beat_pause"))})
    if not lines:
        return errors, warnings
    lines.sort(key=lambda l: float(l["start"]))

    for prev, cur in zip(lines, lines[1:]):
        gap = float(cur["start"]) - float(prev["end"])
        beat = bool(cur.get("beat_pause"))
        limit = BEAT_PAUSE_MAX if beat else GAP_MAX
        if gap > limit + _EPS:
            kind = "標記停頓" if beat else "句間空隙"
            errors.append(
                f"[D3 {kind}過長] {seg}「{cur.get('text', '')[:10]}」前空 {gap:.2f}s > {limit}s；"
                "短句之間的動作要和說話重疊（真的要停頓請標 beat_pause，0.6–1.2s）。")
        elif beat and gap < BEAT_PAUSE_MIN - _EPS:
            warnings.append(f"[D3 停頓太短] {seg}「{cur.get('text', '')[:10]}」標了 beat_pause 但只空 {gap:.2f}s")

    for s in talking:
        a, b = _span(s)
        if any(float(l["start"]) < a - _EPS and float(l["end"]) > a + _EPS for l in lines):
            continue  # 切點時已經在講
        starts = [float(l["start"]) for l in lines if a - _EPS <= float(l["start"]) < b]
        if not starts:
            continue
        onset = min(starts) - a
        first = next(l for l in lines if float(l["start"]) == min(starts))
        if onset > CUT_ONSET_MAX + _EPS and not (first.get("beat_pause") and onset <= BEAT_PAUSE_MAX + _EPS):
            errors.append(
                f"[D4 切鏡後太晚開口] {s.get('shot_id', '?')} 切鏡後 {onset:.2f}s 才開口 > {CUT_ONSET_MAX}s（逐切點量）。")
    return errors, warnings
