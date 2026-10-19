#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run repository unittest coverage and deterministic offline smoke checks."""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def run(label: str, command: list[str], cwd: Path = ROOT) -> bool:
    print(f"\n=== {label} ===", flush=True)
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["TEMP"] = str(ROOT / "tmp")
    env["TMP"] = str(ROOT / "tmp")
    try:
        result = subprocess.run(command, cwd=cwd, text=True, encoding="utf-8", errors="replace",
                                env=env, capture_output=True, timeout=900)
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"FAIL: {exc}", flush=True)
        return False
    if result.stdout:
        print(result.stdout, end="" if result.stdout.endswith("\n") else "\n", flush=True)
    if result.stderr:
        print(result.stderr, end="" if result.stderr.endswith("\n") else "\n", file=sys.stderr, flush=True)
    print(f"=== {label}: {'PASS' if result.returncode == 0 else 'FAIL'} ===", flush=True)
    return result.returncode == 0


def run_adaptation_suite_in_copy() -> bool:
    """That legacy suite rewrites fixtures/goldens; isolate all its writes."""
    (ROOT / "tmp").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="adapt-suite-", dir=ROOT / "tmp") as temp:
        isolated = Path(temp)
        shutil.copytree(ROOT / "scripts", isolated / "scripts", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(ROOT / "references" / "adapt", isolated / "references" / "adapt",
                        ignore=shutil.ignore_patterns("__pycache__"))
        return run(
            "adaptation golden suite (isolated copy)",
            [sys.executable, str(isolated / "scripts" / "adapt" / "tests" / "run_all_tests.py")],
            cwd=isolated,
        )


def main() -> int:
    (ROOT / "tmp").mkdir(exist_ok=True)
    checks: list[tuple[str, list[str]]] = [
        ("unittest discovery", [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"]),
        ("stage review self-test", [sys.executable, "scripts/build_stage_review.py", "--self-test"]),
        ("prompt/ref audit self-test", [sys.executable, "scripts/storyboard/audit_refs_and_segments.py", "--self-test"]),
        ("video QA self-test", [sys.executable, "scripts/storyboard/verify_video_shot.py", "--self-test"]),
        ("assembly self-test", [sys.executable, "scripts/storyboard/assemble_episode.py", "--self-test"]),
    ]
    results = [run(label, command) for label, command in checks]
    results.append(run_adaptation_suite_in_copy())
    failed = sum(not result for result in results)
    print(f"\nOffline checks: {len(results) - failed}/{len(results)} passed", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
