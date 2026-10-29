import json, subprocess, sys, tempfile
from pathlib import Path
GATE = Path(__file__).resolve().parents[1] / "scripts/storyboard/pacing_gate.py"

def run(seg):
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump({"segments": [seg]}, f, ensure_ascii=False)
    return subprocess.run([sys.executable, str(GATE), f.name], capture_output=True, text=True)

def seg(lines, dur=6.0, prompt="real-time speed"):
    return {"id": "s", "duration": dur, "kind": "dialogue", "prompt": prompt, "lines": lines}

def test_v1_like_passes():
    r = run(seg([{"text": "一二三四五六七八九十", "start": 0.3, "end": 2.6},
                 {"text": "一二三四五六七八九十", "start": 3.5, "end": 5.8}]))
    assert r.returncode == 0, r.stdout

def test_gap_over_1_5_fails_even_with_beat_pause():
    r = run(seg([{"text": "一二三四五", "start": 0, "end": 1},
                 {"text": "一二三四五", "start": 2.6, "end": 3.6, "beat_pause": True}]))
    assert r.returncode == 1

def test_slow_and_long_line_fail():
    assert run(seg([{"text": "字" * 10, "start": 0, "end": 2}], prompt="slow push")).returncode == 1
    assert run(seg([{"text": "字" * 36, "start": 0, "end": 6}], dur=10)).returncode == 1

def test_sparse_dialogue_warns():
    r = run(seg([{"text": "一二三四五", "start": 0.2, "end": 1.4}], dur=6.0))
    assert "空跑" in r.stdout and r.returncode == 0

def test_role_rates():
    sys.path.insert(0, str(GATE.parents[1] / "adapt"))
    sys.path.insert(0, str(GATE.parent))
    import estimate_duration as ed, handoff_to_skeleton as h
    assert ed.speaker_rate("沈凡", {"沈凡"}) == 4.0
    assert ed.speaker_rate("狄韻") == 4.5
    assert ed.speaker_rate("狄韻(VO)") == 5.5
    assert h.dialogue_seconds("一二三四五六七八", "male_lead") == 2.3
    assert h.dialogue_seconds("一二三四五六七八九", "female") == 2.3
    assert h.dialogue_seconds("字" * 11, audio_type="narration") == 2.3

def test_voiced_shot_ratio_warns():
    s = seg([{"text": "一二三四五六七八九十", "start": 0.3, "end": 2.6}], dur=6.0)
    s["shots"] = [{"start": 0, "end": 3, "has_dialogue": True},
                  {"start": 3, "end": 4.5, "has_dialogue": False},
                  {"start": 4.5, "end": 6, "has_dialogue": False}]
    assert "有人聲鏡 1/3" in run(s).stdout

def test_tail_freeze_warns():
    r = run(seg([{"text": "一二三四五六七八九十", "start": 0.3, "end": 2.6}],
                prompt="real-time speed. The final second holds still before the cut."))
    assert "末 1 秒靜止" in r.stdout

def test_skeleton_defaults_no_tail_freeze():
    sys.path.insert(0, str(GATE.parent))
    import inspect, handoff_to_skeleton as h
    assert '"tail_freeze_hold": False' in inspect.getsource(h)
