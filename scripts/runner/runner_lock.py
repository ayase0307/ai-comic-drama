#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""影片 runner 單例鎖：同一台機器同時只允許一個影片 runner。

為什麼：家機 GPU 一次只能跑一段；《我修的是遺忘課》實戰中曾同時有 runner、
等待者、別的案子的出片在排隊，兩個 runner 一起送件會互搶佇列、重複計費，
而且分不清哪個 job 是誰的。規則：

  * 鎖檔（預設 ~/.ai-comic-drama/video-runner.lock，可用環境變數
    AICD_RUNNER_LOCK 改）記錄 pid、主機、專案、計畫檔、開始時間。
  * 鎖檔存在且 pid 還活著 → 別人在跑，等待（或直接回報）；pid 已死 → 視為殘留，回收。
  * 另外掃描行程表找「外部 runner」（例如專案自寫的 fv_run_multi.py、fv_wait_then_run.py，
    或另一個 `h3d run`）：它們不認得這個鎖，所以要主動偵測並等待。
  * 只偵測、只等待，絕不結束別人的行程。
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

DEFAULT_LOCK = Path.home() / ".ai-comic-drama" / "video-runner.lock"
# 行程命令列含這些字樣就視為影片 runner（大小寫不拘）
EXTERNAL_RUNNER_PATTERNS = ("fv_run_multi", "fv_run_ep", "fv_wait_then_run", "h3d.py run",
                            "fv_runner.py", "submit_h3_segments")


class RunnerBusy(RuntimeError):
    pass


def lock_path() -> Path:
    raw = os.environ.get("AICD_RUNNER_LOCK", "").strip()
    return Path(raw) if raw else DEFAULT_LOCK


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform.startswith("win"):
        try:
            import ctypes
            k32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
            handle = k32.OpenProcess(0x1000, False, int(pid))  # PROCESS_QUERY_LIMITED_INFORMATION
            if not handle:
                return False
            code = ctypes.c_ulong()
            ok = k32.GetExitCodeProcess(handle, ctypes.byref(code))
            k32.CloseHandle(handle)
            return bool(ok) and code.value == 259  # STILL_ACTIVE
        except Exception:  # pragma: no cover - 查不到就當還活著，寧可多等
            return True
    try:
        os.kill(pid, 0)  # 只探測，不送訊號
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def list_processes() -> List[Dict[str, Any]]:
    """回傳 [{pid, cmdline}]；拿不到就回空清單（不阻斷）。"""
    try:
        import psutil  # type: ignore
        out = []
        for proc in psutil.process_iter(["pid", "cmdline"]):
            cmd = " ".join(proc.info.get("cmdline") or [])
            out.append({"pid": proc.info["pid"], "cmdline": cmd})
        return out
    except Exception:
        pass
    try:
        if sys.platform.startswith("win"):
            ps_cmd = ("Get-CimInstance Win32_Process | Select-Object ProcessId,CommandLine | "
                      "ConvertTo-Json -Compress")
            raw = subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], capture_output=True,
                                 text=True, timeout=60, encoding="utf-8", errors="replace").stdout
            data = json.loads(raw or "[]")
            data = data if isinstance(data, list) else [data]
            return [{"pid": int(d.get("ProcessId") or 0), "cmdline": d.get("CommandLine") or ""} for d in data]
        raw = subprocess.run(["ps", "-eo", "pid=,args="], capture_output=True, text=True, timeout=30).stdout
        out = []
        for line in raw.splitlines():
            parts = line.strip().split(None, 1)
            if len(parts) == 2 and parts[0].isdigit():
                out.append({"pid": int(parts[0]), "cmdline": parts[1]})
        return out
    except Exception:
        return []


def external_runners(processes: Optional[List[Dict[str, Any]]] = None,
                     patterns=EXTERNAL_RUNNER_PATTERNS, ignore_pids=()) -> List[Dict[str, Any]]:
    procs = list_processes() if processes is None else processes
    me = {os.getpid(), os.getppid(), *ignore_pids}
    found = []
    for proc in procs:
        cmd = str(proc.get("cmdline") or "")
        low = cmd.lower()
        if proc.get("pid") in me or "--status" in low or "--pause" in low:
            continue
        if any(p.lower() in low for p in patterns) and "--dry-run" not in low and "unittest" not in low:
            found.append(proc)
    return found


def read_lock(path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    path = path or lock_path()
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"pid": -1, "corrupt": True}


class RunnerLock:
    """with RunnerLock(project=..., plan=...) as lock: ...；拿不到鎖丟 RunnerBusy。"""

    def __init__(self, *, project: str = "", plan: str = "", path: Optional[Path] = None,
                 wait_seconds: float = 0, poll: float = 30, check_external: bool = True,
                 processes_fn: Callable[[], List[Dict[str, Any]]] = list_processes,
                 sleep: Callable[[float], None] = time.sleep, log: Callable[[str], None] = print):
        self.path = Path(path) if path else lock_path()
        self.project, self.plan = project, plan
        self.wait_seconds, self.poll = wait_seconds, poll
        self.check_external = check_external
        self.processes_fn, self.sleep, self.log = processes_fn, sleep, log
        self.acquired = False

    def _blocker(self) -> Optional[str]:
        current = read_lock(self.path)
        if current and current.get("pid") != os.getpid():
            pid = int(current.get("pid") or -1)
            if pid_alive(pid) and current.get("host", socket.gethostname()) == socket.gethostname():
                return f"另一個 runner（pid {pid}，{current.get('plan', '?')}，{current.get('started', '?')}）持有鎖"
            self.log(f"回收殘留鎖檔（pid {pid} 已不在）：{self.path}")
            try:
                self.path.unlink()
            except OSError:
                pass
        if self.check_external:
            ext = external_runners(self.processes_fn())
            if ext:
                return f"偵測到外部影片 runner（pid {ext[0]['pid']}：{ext[0]['cmdline'][:120]}）"
        return None

    def acquire(self) -> "RunnerLock":
        deadline = time.monotonic() + max(0.0, self.wait_seconds)
        while True:
            reason = self._blocker()
            if reason is None:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                payload = {"pid": os.getpid(), "host": socket.gethostname(), "project": self.project,
                           "plan": self.plan, "started": time.strftime("%Y-%m-%d %H:%M:%S")}
                try:
                    fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                except FileExistsError:
                    reason = "鎖檔剛被別人建立"
                else:
                    with os.fdopen(fd, "w", encoding="utf-8") as handle:
                        json.dump(payload, handle, ensure_ascii=False)
                    self.acquired = True
                    return self
            if time.monotonic() >= deadline:
                raise RunnerBusy(reason)
            self.log(f"等待：{reason}；{int(self.poll)} 秒後再看")
            self.sleep(self.poll)

    def release(self) -> None:
        if not self.acquired:
            return
        current = read_lock(self.path)
        if current and current.get("pid") == os.getpid():
            try:
                self.path.unlink()
            except OSError:
                pass
        self.acquired = False

    def __enter__(self) -> "RunnerLock":
        return self.acquire()

    def __exit__(self, *exc) -> None:
        self.release()
