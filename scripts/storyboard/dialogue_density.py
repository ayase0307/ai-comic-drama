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
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from speech_utils import count_speech_chars

DENSITY_MIN = 3.0
DENSITY_WARN_MAX = 3.9
MONTAGE_ALLOWANCE_SEC = 5.0
GAP_MAX = 0.9
BEAT_PAUSE_MIN, BEAT_PAUSE_MAX = 0.6, 1.2
CUT_ONSET_MAX = 0.5
_EPS = 0.011


def _dlg(shot: Dict[str, Any]) -> Dict[str, Any]:
    return shot.get("dialogue_and_audio") or {}


def _has_line(shot: Dict[str, Any]) -> bool:
    d = _dlg(shot)
    return bool(d.get("has_dialogue")) and bool((d.get("line_verbatim") or "").strip())


def _span(shot: Dict[str, Any]) -> Tuple[float, float]:
    return float(shot.get("start_time", 0)), float(shot.get("end_time", 0))


def check_dialogue_density(data: Dict[str, Any]) -> Tuple[List[str], List[str]]:
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
    chars = sum(count_speech_chars(_dlg(s).get("line_verbatim") or "") for s in talking)
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
        for ln in _dlg(s).get("line_timecodes") or []:
            lines.append(ln)
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
