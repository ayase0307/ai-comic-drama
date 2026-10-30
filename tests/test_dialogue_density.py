import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "storyboard"))
from dialogue_density import check_dialogue_density  # noqa: E402


def shot(sid, a, b, lines=()):
    text = "".join(l["text"] for l in lines)
    return {"shot_id": sid, "start_time": a, "end_time": b,
            "dialogue_and_audio": {"has_dialogue": bool(lines), "line_verbatim": text or None,
                                   "line_timecodes": list(lines)}}


def ln(text, s, e, beat=False):
    return {"text": text, "start": s, "end": e, "beat_pause": beat}


def seg(*shots):
    return {"segment_id": "T", "shots": list(shots)}


def codes(errs):
    return [e.split("]")[0] for e in errs]


def test_dense_dialogue_passes():
    d = seg(shot("A", 0, 4.0, [ln("一二三四五六", 0.3, 1.8)]),
            shot("B", 4.0, 7.5, [ln("一二三四五六七", 1.8, 3.6), ln("一二三四五六七八九十", 3.9, 6.6)]))
    errs, _ = check_dialogue_density(d)
    assert errs == [], errs


def test_low_density_fails():
    d = seg(shot("A", 0, 8.0, [ln("一二三四五", 0.3, 1.5)]))
    errs, _ = check_dialogue_density(d)
    assert any("D2" in e for e in errs)


def test_montage_allowance_capped_at_five_seconds():
    talk = [ln("一二三四五六七八九十一二", 4.3, 7.3)]
    ok = seg(shot("M", 0, 4.0), shot("A", 4.0, 7.6, talk))
    assert not [e for e in check_dialogue_density(ok)[0] if "D2" in e]
    talk2 = [ln("一二三四五六七八九十一二", 9.3, 12.3)]
    bad = seg(shot("M", 0, 9.0), shot("A", 9.0, 12.6, talk2))
    assert any("D2" in e for e in check_dialogue_density(bad)[0])


def test_silent_segment_over_five_seconds_fails():
    assert any("D1" in e for e in check_dialogue_density(seg(shot("M", 0, 6.0)))[0])
    assert check_dialogue_density(seg(shot("M", 0, 4.7)))[0] == []


def test_gap_rules_and_beat_pause():
    base = [ln("一二三四五六", 0.3, 1.8)]
    gap = seg(shot("A", 0, 4.6, base + [ln("一二三四五六七八", 2.9, 4.4)]))
    assert any("D3" in e for e in check_dialogue_density(gap)[0])
    beat = seg(shot("A", 0, 4.6, base + [ln("一二三四五六七八", 2.9, 4.4, beat=True)]))
    assert not any("D3" in e for e in check_dialogue_density(beat)[0])
    long_beat = seg(shot("A", 0, 5.0, base + [ln("一二三四五六七八", 3.2, 4.7, beat=True)]))
    assert any("D3" in e for e in check_dialogue_density(long_beat)[0])


def test_onset_measured_per_cut():
    late = seg(shot("A", 0, 2.0, [ln("一二三四五六", 0.3, 1.8)]),
               shot("B", 2.0, 4.6, [ln("一二三四五六七", 2.7, 4.4)]))
    errs = check_dialogue_density(late)[0]
    assert any("D4" in e and "B" in e for e in errs)
    # 句子跨切點：切點時正在講，onset 視為 0
    carry = seg(shot("A", 0, 1.5, [ln("一二三四五六", 0.3, 1.8)]),
                shot("B", 1.5, 4.4, [ln("一二三四五六七八九", 2.1, 4.1)]))
    assert not any("D4" in e for e in check_dialogue_density(carry)[0])


def test_exempt_reason_downgrades_density_only():
    d = seg(shot("A", 0, 8.0, [ln("一二三四五", 0.3, 1.5)]))
    d["metadata"] = {"density_exempt_reason": "刻意靜場"}
    errs, warns = check_dialogue_density(d)
    assert errs == [] and any("D2" in w for w in warns)
