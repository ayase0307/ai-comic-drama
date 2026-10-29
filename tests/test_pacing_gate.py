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
