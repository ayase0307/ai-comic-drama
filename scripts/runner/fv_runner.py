#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""`h3d run --plan`：階段 6 多集／多段送件 runner（從《我修的是遺忘課》家機 fv_run_multi.py 通用化）。

計畫檔是 JSON 陣列，依序一次送一段：

    [{"key": "EP02-S01-a", "segments": "segments-ep02.json", "segment_id": "EP02-S01-a",
      "out": "videos/EP02-S01-a.mp4", "seed": null},
     {"key": "EP01-S04-b-take3", "segments": "segments-ep01.json", "segment_id": "EP01-S04-b",
      "out": "videos/_alt/EP01-S04-b-take3.mp4", "seed": 123456789}]

key 同時是 ledger 的 segment_id（重抽加 -take3 之類後綴，避免和正式段的 downloaded 紀錄互鎖）。

安全規則（實戰學到的）：
  * **單例鎖**：同一台機器只允許一個影片 runner；偵測到外部 runner（專案自寫腳本、另一個 h3d run）
    就等待（--wait-lock 秒），等不到就停下回報。只等待，絕不結束別人的行程。
  * **佇列檢查**：GET /queue 有別人的工作（pending／running）→ 每 30 秒看一次，最多等 --blocked-wait 秒，
    仍忙就停下（不繞過）。
  * **受保護 job**：--protect-job 列出的 job id（例如使用者自己的影片）絕不取消、不碰。
  * **送件前 probe**：LoRA 沒安裝直接擋（見 fv_probe.py）；loras 只送 name＋strength。
  * **暫停／續跑**：建立 `<progress>.pause`（`h3d run --pause`）→ 目前這段收完就停，狀態 paused_by_user；
    重跑同一指令就續跑（已有輸出檔、ledger 有進行中工作的段會跳過）。
  * 送件 409 busy／conflict → 停；同一錯誤連續 2 次 → 停；可重試的失敗自動 resume ≤ 2 次。
  * 終態幀數或檔案時長不符 → 標 duration_drift、隔離成 .drift.mp4，不覆蓋正式檔。
  * **進度檔**（預設 videos/_runner-progress.json）：每段狀態、job id、幀數、耗時，給 h3d run --status 與人看。
  * 令牌只由 submit_h3_segments.find_token() 讀取，絕不印出、不寫檔。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
import urllib.error
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
RUNNER_DIR = Path(__file__).resolve().parent
for candidate in (str(SCRIPTS_DIR), str(SCRIPTS_DIR / "storyboard"), str(RUNNER_DIR)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

import fv_probe  # noqa: E402
import runner_lock  # noqa: E402

TERMINAL = ("succeeded", "failed", "cancelled", "interrupted")
RETRYABLE_CODES = ("generation_failed", "out_of_memory", "interrupted", "join_failed")
DEFAULT_PROGRESS = Path("videos") / "_runner-progress.json"

# 結束碼
RC_DONE, RC_AUDIT, RC_NO_TOKEN, RC_BLOCKED, RC_REPEATED, RC_TIMEOUT, RC_PAUSED, RC_LOCK, RC_PROBE, RC_CRASH = (
    0, 1, 2, 3, 4, 5, 6, 7, 8, 9)


def now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


class Progress:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.data: Dict[str, Any] = {"segments": {}}
        if self.path.is_file():
            try:
                self.data = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                self.data = {"segments": {}}
        self.data.setdefault("segments", {})

    @property
    def pause_file(self) -> Path:
        return self.path.with_name(self.path.name + ".pause")

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def seg(self, key: str) -> Dict[str, Any]:
        return self.data["segments"].setdefault(key, {})


def http_error(exc: Exception) -> Dict[str, Any]:
    try:
        body = json.loads(exc.read().decode("utf-8"))  # type: ignore[attr-defined]
    except Exception:
        body = {}
    err = body.get("error") if isinstance(body, dict) else None
    return err or {"code": f"http_{getattr(exc, 'code', '?')}", "message": str(exc)}


class FreeVideoApi:
    """真正連 FreeVideo 的介面；測試換成假的。"""

    def __init__(self, api_url: str, token: str, root: Path):
        import submit_h3_segments as S
        self.S, self.api, self.token, self.root = S, api_url, token, Path(root)
        self.cache_file = self.root / "videos" / "_fv-ref-map.json"
        self.cache = S.load_media_cache(self.cache_file)

    def call(self, method: str, path: str, body: Optional[Dict[str, Any]] = None, timeout: int = 300):
        return self.S.call_api(self.api, self.token, method, path, body, timeout=timeout)

    def queue(self) -> Dict[str, Any]:
        try:
            return self.call("GET", "/queue", timeout=60)
        except Exception as exc:  # pragma: no cover
            return {"error": str(exc)}

    def root_info(self) -> Dict[str, Any]:
        return self.call("GET", "", timeout=60)

    def openapi(self) -> Dict[str, Any]:
        return self.call("GET", "/openapi.json", timeout=60)

    def upload(self, path: Path) -> str:
        return self.S.upload_reference_media(self.api, self.token, path, self.cache, self.cache_file)

    def submit(self, body: Dict[str, Any]) -> Dict[str, Any]:
        return self.call("POST", "/jobs", body, timeout=300)

    def poll(self, job_id: str) -> Dict[str, Any]:
        return self.call("GET", f"/jobs/{job_id}?wait=25", timeout=40)

    def resume(self, job_id: str, ref: str) -> Dict[str, Any]:
        return self.call("POST", f"/jobs/{job_id}/resume", {"ref": ref})

    def cancel(self, job_id: str) -> Dict[str, Any]:
        return self.call("POST", f"/jobs/{job_id}/cancel", {})

    def download(self, url: str, out: Path) -> None:
        self.S.download_file(self.token, self.api, url, out)

    def probe_duration(self, path: Path) -> Optional[float]:
        return self.S.probe_video_duration(path)


def queue_busy(q: Any) -> bool:
    if not isinstance(q, dict) or q.get("error"):
        return False
    return bool((q.get("pending") or 0) or (q.get("running") or 0))


def load_plan(path: Path, only: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    plan = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(plan, list):
        raise ValueError("計畫檔必須是 JSON 陣列")
    for item in plan:
        if not isinstance(item, dict) or not item.get("key") or not item.get("segment_id") or not item.get("out"):
            raise ValueError(f"計畫項缺 key／segment_id／out：{item}")
    if only:
        wanted = set(only)
        plan = [it for it in plan if it["key"] in wanted]
    return plan


def build_body(seg: Dict[str, Any], item: Dict[str, Any], refs: List[Dict[str, str]], quality: str,
               seconds: float) -> Dict[str, Any]:
    import submit_h3_segments as S
    key = item["key"]
    body: Dict[str, Any] = {
        "kind": "generate",
        "prompt": seg.get("h3_prompt") or seg.get("prompt", ""),
        "seconds": seconds,
        "aspect": (seg.get("metadata") or {}).get("aspect_ratio") or seg.get("aspect", "16:9"),
        "quality": quality,
        "label": item.get("label") or seg.get("label", seg["segment_id"]),
        "ref": f"seg-{key.lower()}-{int(time.time())}",
        "media": {"references": refs},
    }
    if item.get("seed") is not None:
        body["seed"] = int(item["seed"])
    if seg.get("h3_loras"):
        body["loras"] = S.sanitize_loras(seg["h3_loras"])
    return body


class Runner:
    def __init__(self, root: Path, plan: List[Dict[str, Any]], api: Any, *, progress: Path,
                 plan_name: str = "", quality: str = "light", poll_timeout: int = 5400, blocked_wait: int = 900,
                 protect_jobs: Optional[List[str]] = None, sleep: Callable[[float], None] = time.sleep,
                 log: Callable[[str], None] = None, queue_poll: float = 30, skip_audit: bool = False,
                 skip_probe: bool = False):
        import submit_h3_segments as S
        self.S = S
        self.root, self.plan, self.api = Path(root), plan, api
        self.prog = Progress(progress)
        self.plan_name, self.quality = plan_name, quality
        self.poll_timeout, self.blocked_wait = poll_timeout, blocked_wait
        self.protect = {str(j) for j in (protect_jobs or [])}
        self.sleep, self.queue_poll = sleep, queue_poll
        self.log = log or (lambda m: print(f"[{now()}] {m}", flush=True))
        self.skip_audit, self.skip_probe = skip_audit, skip_probe
        self.ledger = self.root / "videos" / "_fv-job-ledger.json"
        self.api_scope = getattr(api, "api", "local")

    # ---- 小工具 --------------------------------------------------------
    def state(self, value: str, **extra: Any) -> None:
        self.prog.data["runner_state"] = value
        self.prog.data.update(extra)
        self.prog.save()

    def record(self, key: str, job_id: str, status: str, **kw: Any) -> None:
        self.S.record_job(self.ledger, project=str(self.root.resolve()), api_scope=str(self.api_scope),
                          batch_id=self.batch_id, segment_id=key, job_id=str(job_id), status=status, **kw)

    def load_segments(self) -> List[Tuple[Dict[str, Any], Dict[str, Any]]]:
        files: Dict[str, Dict[str, Dict[str, Any]]] = {}
        todo = []
        for item in self.plan:
            name = item.get("segments") or "segments-ep01.json"
            if name not in files:
                raw = json.loads((self.root / name).read_text(encoding="utf-8-sig"))
                items = raw if isinstance(raw, list) else raw.get("segments", [])
                files[name] = {s["segment_id"]: s for s in items if isinstance(s, dict) and s.get("segment_id")}
            if item["segment_id"] not in files[name]:
                raise ValueError(f"{name} 裡沒有 {item['segment_id']}")
            todo.append((item, files[name][item["segment_id"]]))
        return todo

    def stage5_pending(self, todo: List[Tuple[Dict[str, Any], Dict[str, Any]]]) -> List[str]:
        """PR-19a：stage-5 段級核准是 partial 時，列出計畫裡待重審的段（其他情況不擋，維持舊行為）。"""
        try:
            import project_state as ps
        except ImportError:  # pragma: no cover
            return []
        if not ps.state_path(self.root).is_file():
            return []
        try:
            review = ps.stage5_segment_review(self.root)
        except Exception:  # pragma: no cover - 狀態檔壞掉時由其他門禁回報
            return []
        if review.get("mode") != "partial":
            return []
        out: List[str] = []
        cache: Dict[str, set] = {}
        for item, seg in todo:
            name = item.get("segments") or "segments-ep01.json"
            if name not in cache:
                allowed, _pending, _why = ps.stage5_submittable_ids(self.root, self.root / name)
                cache[name] = allowed or set()
            if seg["segment_id"] not in cache[name]:
                out.append(item["key"])
        return out

    def wait_queue(self, rec: Dict[str, Any]) -> bool:
        q = self.api.queue()
        start = time.monotonic()
        waited = 0.0
        while queue_busy(q):
            if waited >= self.blocked_wait or time.monotonic() - start > self.blocked_wait:
                rec["queue_before"] = q
                self.state("blocked_queue_busy")
                self.log(f"佇列等 {self.blocked_wait}s 仍有別人的工作，停下回報：{json.dumps(q, ensure_ascii=False)[:400]}")
                return False
            rec["status"] = "waiting_queue"
            self.prog.save()
            self.sleep(self.queue_poll)
            waited += self.queue_poll
            q = self.api.queue()
        rec["queue_before"] = q
        return True

    def probe(self, segments: List[Dict[str, Any]]) -> bool:
        if self.skip_probe or not any(s.get("h3_loras") for s in segments):
            return True
        try:
            installed = fv_probe.installed_loras(self.api.root_info() or {})
        except Exception as exc:
            self.log(f"probe：讀不到已安裝 LoRA（{exc}），不擋")
            return True
        report = fv_probe.check(segments, installed)
        if not report["ok"]:
            self.prog.data["probe_errors"] = report["errors"]
            self.state("probe_failed")
            for err in report["errors"]:
                self.log(f"PROBE {err['message']}；替代：{'／'.join(err['alternatives'])}")
            return False
        return True

    # ---- 主流程 --------------------------------------------------------
    def run(self) -> int:
        prog = self.prog
        prog.data.update({"runner_pid": os.getpid(), "runner_started": now(), "runner_state": "running",
                          "plan_file": self.plan_name, "order": [it["key"] for it in self.plan], "current": None})
        prog.data.pop("runner_finished", None)
        for it in self.plan:
            prog.data["segments"].setdefault(it["key"], {"status": "queued_local", "out": it["out"],
                                                         "seed_requested": it.get("seed")})
        prog.save()
        todo = self.load_segments()
        segs = [s for _, s in todo]
        pending = self.stage5_pending(todo)
        if pending:
            prog.data["stage5_pending_review"] = pending
            self.state("stage5_pending_review")
            self.log("STAGE5 這些段核准後改過、待人工重審，不送件：" + "、".join(pending)
                     + "（用 --only 只跑已核准的段，或重審：h3d approve --stage 5 --segments ...）")
            return RC_AUDIT
        if not self.skip_audit:
            ok, errs = self.S.audit_segment_prompts(segs, root_dir=self.root)
            if not ok:
                prog.data["audit_errors"] = errs
                self.state("audit_failed")
                for e in errs:
                    self.log("AUDIT " + e)
                return RC_AUDIT
        if not self.probe(segs):
            return RC_PROBE
        (self.root / "videos").mkdir(parents=True, exist_ok=True)
        self.batch_id = f"run-{int(time.time())}"
        last_code, same = None, 0

        for idx, (item, seg) in enumerate(todo, 1):
            key, sid = item["key"], seg["segment_id"]
            rec = prog.seg(key)
            if prog.pause_file.exists():
                self.state("paused_by_user", paused_at=now(), current=None)
                self.log(f"偵測到暫停檔 {prog.pause_file.name}：停在 {key} 之前（續跑：刪除暫停檔後重跑同一指令）")
                return RC_PAUSED
            prog.data["current"], prog.data["current_index"] = key, f"{idx}/{len(todo)}"
            out = self.root / item["out"]
            out.parent.mkdir(parents=True, exist_ok=True)
            if out.exists():
                rec.update(status="downloaded", file=item["out"])
                prog.save()
                self.log(f"{key} 已有 {item['out']}，跳過")
                continue
            active = self.S.active_job_for(self.ledger, key)
            if active:
                rec.update(status="skipped_ledger_active", job_id=active.get("id"))
                prog.save()
                self.log(f"{key} ledger 已有 {active.get('status')} job {active.get('id')}，跳過（先 h3d collect）")
                continue
            if not self.wait_queue(rec):
                return RC_BLOCKED

            frames, fsrc = self.S.resolve_segment_frames(seg)
            sec = self.S.h3_spec.wire_seconds(frames)
            rec.update(segment_id=sid, frames_requested=frames, frames_source=fsrc, seconds_sent=sec)
            refs = []
            for ref in seg.get("reference_images", []) or []:
                path = ref.get("path") if isinstance(ref, dict) else ref
                refs.append({"file": self.api.upload((self.root / path).resolve())})
            body = build_body(seg, item, refs, self.quality, sec)
            rec["ref"] = body["ref"]
            self.log(f"--- [{idx}/{len(todo)}] {key} 送件：{frames} 幀 = {sec:.4f}s，參考 {len(refs)} 張")
            try:
                resp = self.api.submit(body)
            except urllib.error.HTTPError as exc:
                err = http_error(exc)
                rec.update(status="submit_error", error=err)
                prog.save()
                msg = json.dumps(err, ensure_ascii=False)
                self.log(f"{key} 送件錯誤：{msg[:600]}")
                if err.get("code") in ("busy", "conflict") or "waiting" in msg:
                    self.state("blocked_submit")
                    return RC_BLOCKED
                same = same + 1 if err.get("code") == last_code else 1
                last_code = err.get("code")
                if same >= 2:
                    self.state("stopped_repeated_error")
                    return RC_REPEATED
                continue
            job = resp.get("job", resp)
            jid = str(job.get("id"))
            if jid in self.protect:
                self.state("abort_protected_job")
                self.log(f"回傳 id {jid} 是受保護的 job，停下")
                return RC_REPEATED
            rec.update(job_id=jid, submitted_at=now(), status=job.get("status"))
            self.record(key, jid, job.get("status", "waiting"), frames=frames, seconds=sec)
            prog.save()
            rep = self.S.declared_frames(job)
            if rep is not None and rep != frames:
                self.log(f"{key} [duration_drift] 服務端回報 {rep} 幀 ≠ {frames}；取消本 job")
                try:
                    self.api.cancel(jid)
                except Exception as exc:
                    self.log(f"取消失敗：{exc}")
                self.record(key, jid, "duration_drift", frames=frames, seconds=sec)
                rec.update(status="duration_drift", frames_reported=rep)
                prog.save()
                continue

            job, rc = self.wait_job(key, jid, job, rec)
            if rc is not None:
                return rc
            st = job.get("status")
            if st != "succeeded":
                err = job.get("error") or {}
                rec.update(status=st, error=err)
                self.record(key, jid, str(st))
                prog.save()
                self.log(f"{key} 失敗：{st} {json.dumps(err, ensure_ascii=False)[:400]}")
                same = same + 1 if err.get("code") == last_code else 1
                last_code = err.get("code")
                if same >= 2:
                    self.state("stopped_repeated_error")
                    return RC_REPEATED
                continue
            if not self.finish_download(key, jid, job, item, out, frames, sec, rec):
                continue
            last_code, same = None, 0
        self.state("done", runner_finished=now(), current=None)
        self.log("本批結束")
        return RC_DONE

    def wait_job(self, key: str, jid: str, job: Dict[str, Any], rec: Dict[str, Any]):
        t0 = time.monotonic()
        waiting_since = time.monotonic()
        resumes = 0
        while True:
            st = job.get("status")
            if st in TERMINAL and not (st in ("failed", "interrupted") and resumes < 2 and self._retryable(job)):
                rec["elapsed_sec"] = round(time.monotonic() - t0, 1)
                return job, None
            if st in ("failed", "interrupted"):
                resumes += 1
                rec.setdefault("resumes", []).append(job.get("error") or {})
                self.log(f"{key} job {jid} {st}：resume 第 {resumes} 次")
                try:
                    job = self.api.resume(jid, f"resume-{key.lower()}-{resumes}-{int(time.time())}")
                    job = job.get("job", job)
                except urllib.error.HTTPError as exc:
                    self.log(f"resume 失敗 {http_error(exc)}")
                    rec["elapsed_sec"] = round(time.monotonic() - t0, 1)
                    return job, None
                continue
            if time.monotonic() - t0 > self.poll_timeout:
                rec["status"] = f"timeout_still_{st}"
                self.state("timeout")
                self.log(f"{key} 輪詢逾時，job {jid} 保留（未取消）")
                return job, RC_TIMEOUT
            if st in ("waiting", "queued"):
                if time.monotonic() - waiting_since > self.blocked_wait:
                    rec.update(status="blocked_waiting", queue_blocked=self.api.queue())
                    self.state("blocked_waiting")
                    return job, RC_BLOCKED
            else:
                rec.setdefault("started_at", now())
                waiting_since = time.monotonic()
            try:
                resp = self.api.poll(jid)
                job = resp.get("job", resp)
                rec.update(status=job.get("status"), progress=job.get("progress"), last_poll=now())
                self.prog.save()
            except Exception as exc:
                self.log(f"{key} 輪詢例外 {exc}")
                self.sleep(10)

    @staticmethod
    def _retryable(job: Dict[str, Any]) -> bool:
        err = job.get("error") or {}
        return bool(err.get("retryable")) or err.get("code") in RETRYABLE_CODES

    def finish_download(self, key, jid, job, item, out: Path, frames: int, sec: float, rec) -> bool:
        rec["finished_at"] = now()
        rec["seed_used"] = (job.get("spec") or {}).get("seed")
        reported = self.S.declared_frames(job)
        rec["frames_reported"] = reported
        if reported is not None and reported != frames:
            self.record(key, jid, "duration_drift", frames=frames, seconds=sec, duration_assert=False)
            rec["status"] = "duration_drift"
            self.prog.save()
            self.log(f"{key} [duration_drift] 終態 {reported} 幀 ≠ {frames}；不下載")
            return False
        url = ((job.get("result") or {}).get("video") or {}).get("url")
        if not url:
            rec["status"] = "no_video_url"
            self.prog.save()
            return False
        self.api.download(url, out)
        probed = self.api.probe_duration(out)
        expected = self.S.h3_spec.seconds_for_frames(frames)
        rec["ffprobe_sec"] = probed
        if probed is not None and abs(probed - expected) > (1.0 / self.S.h3_spec.FPS) + 0.02:
            drift = out.with_name(out.stem + ".drift.mp4")
            out.replace(drift)
            self.record(key, jid, "duration_drift", frames=frames, seconds=sec, duration_assert=False)
            rec.update(status="duration_drift", file=str(Path(item["out"]).with_name(drift.name)).replace("\\", "/"))
            self.prog.save()
            self.log(f"{key} [duration_drift] 檔案 {probed:.3f}s ≠ {expected:.3f}s；隔離 {drift.name}")
            return False
        self.record(key, jid, "downloaded", frames=frames, seconds=sec, duration_assert=probed is not None)
        rec.update(status="downloaded", file=item["out"], bytes=out.stat().st_size)
        self.prog.save()
        self.log(f"{key} ✅ 下載 {item['out']}")
        return True


def status_text(progress: Path) -> str:
    prog = Progress(progress)
    data = prog.data
    counts: Dict[str, int] = {}
    for rec in data["segments"].values():
        counts[str(rec.get("status"))] = counts.get(str(rec.get("status")), 0) + 1
    lines = [f"進度檔：{progress}",
             f"狀態：{data.get('runner_state', '（未開始）')}；目前：{data.get('current') or '—'} {data.get('current_index', '')}",
             "各段：" + ("、".join(f"{k} {v}" for k, v in sorted(counts.items())) or "（無）")]
    if prog.pause_file.exists():
        lines.append(f"已請求暫停（{prog.pause_file.name}）：目前這段收完就停")
    lock = runner_lock.read_lock()
    if lock:
        lines.append(f"單例鎖：pid {lock.get('pid')}（{lock.get('plan', '?')}，{lock.get('started', '?')}）")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    import submit_h3_segments as S
    parser = argparse.ArgumentParser(prog="h3d run", description="階段 6 送件 runner：單例鎖、佇列檢查、暫停／續跑、進度檔")
    parser.add_argument("--plan", type=Path, help="計畫檔（JSON 陣列，見模組說明）")
    parser.add_argument("--root", type=Path, default=Path("."), help="專案根目錄")
    parser.add_argument("--progress", type=Path, default=None, help=f"進度檔（預設 <專案>/{DEFAULT_PROGRESS.as_posix()}）")
    parser.add_argument("--only", nargs="*", help="只跑這些 key")
    parser.add_argument("--quality", default="light")
    parser.add_argument("--api", default=S.DEFAULT_API_URL)
    parser.add_argument("--poll-timeout", type=int, default=5400)
    parser.add_argument("--blocked-wait", type=int, default=900, help="佇列被別人佔用時最多等幾秒")
    parser.add_argument("--wait-lock", type=int, default=0, help="另一個 runner 在跑時最多等幾秒（0＝立刻停下回報）")
    parser.add_argument("--protect-job", action="append", default=[], help="絕不碰的 job id，可重複")
    parser.add_argument("--status", action="store_true", help="只印進度")
    parser.add_argument("--pause", action="store_true", help="請求暫停：目前這段收完就停")
    parser.add_argument("--unpause", action="store_true", help="取消暫停請求")
    args = parser.parse_args(argv)
    root = args.root.expanduser().resolve()
    progress = args.progress if args.progress else root / DEFAULT_PROGRESS
    if not progress.is_absolute():
        progress = root / progress
    pause_file = Progress(progress).pause_file
    if args.status:
        print(status_text(progress))
        return 0
    if args.pause:
        pause_file.parent.mkdir(parents=True, exist_ok=True)
        pause_file.write_text(now(), encoding="utf-8")
        print(f"⏸ 已請求暫停：{pause_file}（runner 收完目前這段就停）")
        return 0
    if args.unpause:
        if pause_file.exists():
            pause_file.unlink()
        print("▶ 已取消暫停請求；重跑同一指令即可續跑")
        return 0
    if not args.plan:
        parser.error("需要 --plan（或 --status／--pause）")
    plan_path = args.plan if args.plan.is_absolute() else root / args.plan
    try:
        plan = load_plan(plan_path, args.only)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"❌ 計畫檔錯誤：{exc}", file=sys.stderr)
        return RC_AUDIT
    token = S.find_token()
    if not token:
        print("❌ 找不到 FreeVideo 令牌", file=sys.stderr)
        return RC_NO_TOKEN
    try:
        with runner_lock.RunnerLock(project=str(root), plan=plan_path.name, wait_seconds=args.wait_lock):
            runner = Runner(root, plan, FreeVideoApi(args.api, token, root), progress=progress,
                            plan_name=plan_path.name, quality=args.quality, poll_timeout=args.poll_timeout,
                            blocked_wait=args.blocked_wait, protect_jobs=args.protect_job)
            try:
                return runner.run()
            except Exception:
                traceback.print_exc()
                runner.prog.data["crash"] = traceback.format_exc()[-3000:]
                runner.state("crashed")
                return RC_CRASH
    except runner_lock.RunnerBusy as exc:
        print(f"⛔ 不啟動：{exc}。同時只允許一個影片 runner；用 --wait-lock 秒數等待，或等它結束再跑。", file=sys.stderr)
        return RC_LOCK


if __name__ == "__main__":
    raise SystemExit(main())
