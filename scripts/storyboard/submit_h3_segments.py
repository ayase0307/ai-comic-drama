#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
submit_h3_segments.py — MiniMax H3 批次分段影片送件與進度管理工具 (FreeVideo Agent API)

用途：
讀取 compile_layer2_to_h3.py 輸出的 segments-epXX.json，安全對接本機 FreeVideo (/freevideo/agent/v1)，
支援事前乾跑檢查 (--dry-run)、本機經驗性顯存提醒、參考圖 SHA256 增量上傳快取、
h3_loras 自動掛載、非同步輪詢與自動下載至 videos/。

【安全鐵律】
嚴禁在任何終端輸出、日誌、例外或報表中印出 FreeVideo 令牌 (token)！

CLI 用法：
  python scripts/storyboard/submit_h3_segments.py --segments segments-ep01.json --dry-run
  python scripts/storyboard/submit_h3_segments.py --segments segments-ep01.json --segment-id EP01-S01-seg01
  python scripts/storyboard/submit_h3_segments.py --segments segments-ep01.json --output-dir videos/
  python scripts/storyboard/submit_h3_segments.py --cancel-stale
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
import uuid
from typing import Any, Dict, List, Optional, Tuple
import urllib.request
import urllib.error

# FreeVideo 依副檔名判定媒體類型（comfy_assets.EXTENSIONS / media_kind）：
# 音訊參考必須是這些副檔名之一，才會被歸類成獨立音訊參考餵進 <Audio N>。
SUPPORTED_AUDIO_SUFFIXES = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac", ".opus"}
from urllib.parse import urljoin, urlsplit

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))
SCRIPTS_DIR = CURRENT_DIR.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
from project_state import record_gate_bypass, require_approved, sha256_file, stage5_submittable_ids, stage_snapshot

try:
    from audit_refs_and_segments import audit_refs_and_subjects, lint_h3_prompt
except ImportError:
    audit_refs_and_subjects = None
    lint_h3_prompt = None

import h3_spec
import provider_caps

try:  # 以 scripts/storyboard 為 sys.path 執行（CLI 慣例）
    import failure_catalog
    import prompt_authoring
except ImportError:  # pragma: no cover - 套件匯入路徑
    from . import failure_catalog
    from . import prompt_authoring


DEFAULT_API_URL = "http://127.0.0.1:8189/freevideo/agent/v1"
SAFE_VRAM_MB = 4300  # 本機經驗性提醒值，不是 H3 跨環境硬性規格
POLL_TIMEOUT_SECONDS = 1800


def _origin(url: str) -> Tuple[str, str, Optional[int]]:
    parsed = urlsplit(url)
    return parsed.scheme.lower(), (parsed.hostname or "").lower(), parsed.port


class SameOriginRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Allow redirects only within the API origin; never forward credentials elsewhere."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if _origin(req.full_url) != _origin(newurl):
            return None
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        authorization = req.get_header("Authorization")
        if redirected is not None and authorization:
            redirected.add_unredirected_header("Authorization", authorization)
        return redirected


def load_job_ledger(path: Path) -> Dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_job_ledger(path: Path, ledger: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(ledger, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def record_job(path: Path, *, project: str, api_scope: str, batch_id: str,
               segment_id: str, job_id: str, status: str = "waiting",
               frames: Optional[int] = None, seconds: Optional[float] = None,
               duration_assert: Optional[bool] = None) -> None:
    ledger = load_job_ledger(path)
    scope = (str(Path(project).resolve()), api_scope.rstrip("/"))
    if ledger and (ledger.get("project"), ledger.get("api_scope")) != scope:
        # Do not silently mix ownership scopes in one ledger.
        raise RuntimeError("job ledger project/API scope mismatch")
    if not ledger:
        ledger = {"project": scope[0], "api_scope": scope[1], "jobs": []}
    jobs = ledger.setdefault("jobs", [])
    entry = next((item for item in jobs if item.get("id") == job_id), None)
    if entry is None:
        entry = {"id": job_id, "batch_id": batch_id, "segment_id": segment_id}
        jobs.append(entry)
    entry["status"] = status
    entry["updated_at"] = time.time()
    if frames is not None:
        entry["frames"] = int(frames)
    if seconds is not None:
        entry["seconds"] = round(float(seconds), 6)
    if duration_assert is not None:
        entry["duration_asserted"] = bool(duration_assert)
    save_job_ledger(path, ledger)


def sanitize_loras(loras: Any) -> List[Any]:
    """API 的 loras 項只接受 name＋strength（additionalProperties=false）。

    segments 裡的 trigger／reason 是給人看的說明欄位；原樣送出會被 API 擋
    （《我修的是遺忘課》EP04-S02-a 2026-10-22 07:15 submit_error）。
    """
    cleaned: List[Any] = []
    for item in loras or []:
        if isinstance(item, str):
            cleaned.append(item)
        elif isinstance(item, dict) and item.get("name"):
            entry: Dict[str, Any] = {"name": str(item["name"])}
            if item.get("strength") is not None:
                entry["strength"] = float(item["strength"])
            cleaned.append(entry)
    return cleaned


def resolve_segment_frames(seg: Dict[str, Any]) -> Tuple[int, str]:
    """決定該段要送出的影格數，並回報來源。

    優先序：
      1. metadata.frames（編譯器寫入的權威值）
      2. metadata.effective_duration_sec 以 floor 回推（舊 segments 相容：
         effective 已是量化後的秒數，floor 回推必得同一個量子）
      3. metadata.target_duration_sec 依 rounding_mode / rounding_reason 換算
      4. seg.seconds

    2026-10-19 的事故正是「把 effective 四捨五入後當秒數送」；本函式只吐影格，
    秒數一律由 h3_spec.wire_seconds() 從影格反推。
    """
    md = seg.get("metadata") if isinstance(seg.get("metadata"), dict) else {}
    for key in ("frames", "effective_frames"):
        value = md.get(key)
        if isinstance(value, (int, float)) and int(value) > 0:
            frames = int(value)
            if not h3_spec.is_quantum(frames):
                raise ValueError(
                    f"{seg.get('segment_id') or seg.get('id')}: metadata.{key}={frames} 不是 17n+5 量子"
                )
            return frames, f"metadata.{key}"
    effective = md.get("effective_duration_sec_exact") or md.get("effective_duration_sec")
    if isinstance(effective, (int, float)) and float(effective) > 0:
        # effective 是「量化後」的秒數（可能被 round 到 3 位小數），
        # 所以只能吸附到最近的量子，不能 floor——floor 會整整少一個量子
        # （6.583s → 158 幀被算成 141 幀，這是 2026-10-19 漂移的反向版本）。
        frames = h3_spec.nearest_quantum(round(float(effective) * h3_spec.FPS))
        return frames, "metadata.effective_duration_sec"
    nominal = md.get("target_duration_sec")
    if not isinstance(nominal, (int, float)) or float(nominal) <= 0:
        nominal = seg.get("seconds")
    if isinstance(nominal, (int, float)) and float(nominal) > 0:
        rounding = str(md.get("rounding_mode") or "floor")
        if md.get("rounding_reason") == "dialogue-preserving":
            rounding = "ceil"
        return h3_spec.frames_for(float(nominal), rounding=rounding), "metadata.target_duration_sec"
    raise ValueError(
        f"{seg.get('segment_id') or seg.get('id')}: 缺少可用時長"
        "（frames / effective_duration_sec / target_duration_sec / seconds 都沒有）"
    )


def _coerce_frames(value: Any) -> Optional[int]:
    """嚴格解析服務端回報的影格數；看不懂就回 None（不是 0、不是通過）。"""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, float):
        if not math.isfinite(value) or not float(value).is_integer():
            return None
        return int(value) if value > 0 else None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            number = float(text)
        except ValueError:
            return None
        if not math.isfinite(number) or not number.is_integer():
            return None
        return int(number) if number > 0 else None
    return None


def declared_frames(job: Dict[str, Any]) -> Optional[int]:
    """從服務端回應找出它實際採用的影格數。

    欄位路徑依版本不同，實測見過 plan.geometry.frames 與 spec.frames；
    數字字串可接受，但小數／布林／負數一律視為「讀不到」，回 None。
    """
    for path in (("spec", "frames"), ("plan", "geometry", "frames"),
                 ("spec", "geometry", "frames"), ("geometry", "frames")):
        node: Any = job
        for key in path:
            if not isinstance(node, dict) or key not in node:
                node = None
                break
            node = node.get(key)
        parsed = _coerce_frames(node)
        if parsed is not None:
            return parsed
    return None


def probe_video_duration(video_path: Path) -> Optional[float]:
    """用 ffprobe 量實際檔案長度；失敗回 None（不代表通過）。"""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", str(video_path)],
            capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    try:
        return float((result.stdout or "").strip())
    except ValueError:
        return None


def get_gpu_vram() -> Optional[Tuple[int, int]]:
    """使用 nvidia-smi 查詢當前剩餘顯存與總顯存 (MB)。若無 nvidia-smi 則回傳 None。"""
    try:
        res = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.free,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, check=True
        )
        parts = res.stdout.strip().split("\n")[0].split(",")
        free_mb = int(parts[0].strip())
        total_mb = int(parts[1].strip())
        return free_mb, total_mb
    except Exception:
        return None


def find_token() -> str:
    """自動從常見路徑安全讀取 FreeVideo 令牌，嚴禁對外列印。"""
    token_candidates = [
        Path(r"E:\FreeVideo\agent\token"),
        Path(os.environ.get("USERPROFILE", "")) / ".freevideo" / "agent" / "token",
        Path("C:/FreeVideo/agent/token"),
    ]
    env_token = os.environ.get("FREEVIDEO_TOKEN", "").strip()
    if env_token:
        return env_token

    for p in token_candidates:
        if p.exists():
            try:
                t = p.read_text(encoding="utf-8").strip()
                if t:
                    return t
            except Exception:
                continue
    return ""


def call_api(api_url: str, token: str, method: str, path: str, body: Optional[Dict[str, Any]] = None, timeout: int = 600) -> Dict[str, Any]:
    """調用 FreeVideo Agent API。"""
    url = api_url.rstrip("/") + path
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={
            "Authorization": "Bearer " + token,
            "Content-Type": "application/json; charset=utf-8"
        }
    )
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}), SameOriginRedirectHandler()
    )
    with opener.open(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def download_file(token: str, api_url: str, rel_or_abs_url: str, out_path: Path, timeout: int = 900) -> None:
    """從 FreeVideo 下載產生的影片檔案。"""
    if rel_or_abs_url.startswith("http://") or rel_or_abs_url.startswith("https://"):
        full_url = rel_or_abs_url
    else:
        full_url = urljoin(api_url.rstrip("/") + "/", rel_or_abs_url)
    headers = {}
    if _origin(full_url) == _origin(api_url):
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(full_url, headers=headers)
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}), SameOriginRedirectHandler()
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = out_path.with_name(out_path.name + ".download.tmp")
    with opener.open(req, timeout=timeout) as r:
        temporary.write_bytes(r.read())
    temporary.replace(out_path)


def load_media_cache(cache_file: Path) -> Dict[str, str]:
    if cache_file.exists():
        try:
            return json.loads(cache_file.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_media_cache(cache_file: Path, cache: Dict[str, str]) -> None:
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def upload_reference_media(api_url: str, token: str, media_path: Path, cache: Dict[str, str], cache_file: Path) -> str:
    """計算 SHA256 增量上傳參考素材（圖片／影片／音訊）至 FreeVideo /media 接口。

    媒體類型由副檔名判定（FreeVideo comfy_assets.media_kind）：
    圖片 .png/.jpg/...、影片 .mp4/...、音訊 .wav/.mp3/.flac/.ogg/.m4a/.aac/.opus。
    音訊會被 FreeVideo 自動分類成獨立音訊參考，對應官方節點的 ref_audios 槽位，
    提示詞裡以 <Audio N> 指稱。
    """
    if not media_path.exists():
        raise FileNotFoundError(f"找不到參考素材檔案: {media_path}")

    data_bytes = media_path.read_bytes()
    sha = hashlib.sha256(data_bytes).hexdigest()
    cache_key = api_url.rstrip("/") + "::" + sha
    if cache_key in cache:
        return cache[cache_key]

    b64 = base64.b64encode(data_bytes).decode("ascii")
    payload = {
        "name": media_path.name,
        "data_base64": b64
    }
    resp = call_api(api_url, token, "POST", "/media", payload)
    remote_file_id = resp.get("file", "")
    if not remote_file_id:
        raise RuntimeError(f"上傳參考素材 {media_path.name} 失敗，API 未回傳 file id")

    cache[cache_key] = remote_file_id
    save_media_cache(cache_file, cache)
    print(f"   [+] 成功上傳新參考素材: {media_path.name} -> {remote_file_id}")
    return remote_file_id


# 舊名保留相容（呼叫端與歷史紀錄用）
upload_reference_image = upload_reference_media


def cancel_stale_jobs(api_url: str, token: str, ledger_path: Optional[Path] = None,
                      project_root: Optional[Path] = None) -> None:
    """Cancel only jobs whose IDs are recorded for this project and API scope."""
    if ledger_path is None or not ledger_path.is_file():
        print("ℹ️ 沒有本機送件 ledger；不會取消任何伺服器任務。")
        return
    ledger = load_job_ledger(ledger_path)
    expected_project = str(Path(project_root or ledger.get("project", "")).resolve()) if (project_root or ledger.get("project")) else ""
    if (not ledger or ledger.get("api_scope", "").rstrip("/") != api_url.rstrip("/")
            or (expected_project and ledger.get("project") != expected_project)):
        print("⚠️ 本機 job ledger 的專案/API scope 不符；不會取消任何任務。")
        return
    owned_ids = {str(item.get("id")) for item in ledger.get("jobs", []) if item.get("id")}
    if not owned_ids:
        print("ℹ️ 本機 ledger 沒有可取消任務。")
        return
    try:
        resp = call_api(api_url, token, "GET", "/jobs")
        jobs = resp.get("jobs", [])
    except Exception as e:
        print(f"❌ 查詢任務失敗: {e}")
        return

    targets = [j for j in jobs if str(j.get("id")) in owned_ids
               and j.get("status") in ("running", "waiting")]
    if not targets:
        print("✅ 目前沒有殘留的 seg- 孤兒任務。")
        return

    print(f"⚠️ 發現 {len(targets)} 個未完成的 seg- 任務，開始自動清理...")
    for j in targets:
        jid = j.get("id")
        try:
            call_api(api_url, token, "POST", f"/jobs/{jid}/cancel", {})
            for entry in ledger.get("jobs", []):
                if str(entry.get("id")) == str(jid):
                    entry["status"] = "cancel_requested"
                    entry["updated_at"] = time.time()
            save_job_ledger(ledger_path, ledger)
            print(f"  - 已送出取消請求: {jid} ({j.get('status')}) {j.get('label')}")
        except Exception as e:
            print(f"  - 取消任務 {jid} 失敗: {e}")
    print("✅ 孤兒任務清理完畢。")


def verify_stage5_gate(root_dir: Path, segments_path: Path, skip_gate: bool = False, dry_run: bool = False,
                       scope: Optional[Dict[str, Any]] = None) -> bool:
    """要求當前批次 segments 與其參考圖均在有效 stage-5 核准快照內。

    PR-19a 段級核准：stage-5 核准後只改了部分段時，沒改的段仍可送件。
    這時回 True，並在 `scope` 寫入 {"allowed": 可送段 id 集合, "pending": 待重審段}；
    呼叫端必須只送 allowed 內的段（main() 會照做並列出待重審段）。
    """
    if skip_gate:
        if dry_run:
            print("⚠️ [debug] --skip-stage-gate 僅於 --dry-run 可用。")
            if not record_gate_bypass(root_dir, "stage-5", f"submit_h3_segments --dry-run --skip-stage-gate ({segments_path.name})"):
                print("⚠️ [警告] 沒有 review/project-state.json，這次繞過未留紀錄。", file=sys.stderr)
            return True
        print("❌ --skip-stage-gate 僅允許 dry-run；實際送件必須有 stage-5 核准。", file=sys.stderr)
        return False
    try:
        rel = segments_path.resolve().relative_to(root_dir.resolve()).as_posix()
    except ValueError:
        print("❌ segments 檔必須位於專案中，並列入 stage-5 核准快照。", file=sys.stderr)
        return False
    ok, detail = require_approved(root_dir, 5)
    if not ok:
        allowed, pending, why = stage5_submittable_ids(root_dir, segments_path)
        if allowed:
            print(f"⚠️ [Stage 5 Gate] {why}", file=sys.stderr)
            print(f"   只放行已核准且未變的 {len(allowed)} 段；待重審（不送）：{'、'.join(pending) or '無'}", file=sys.stderr)
            print("   重審：build_stage_review.py --project-dir . --stage 5 --segments <段> → 使用者通過後 "
                  "h3d approve --stage 5 --segments <段> --user-note \"<使用者原話>\"", file=sys.stderr)
            if scope is not None:
                scope["allowed"] = set(allowed)
                scope["pending"] = list(pending)
            return True
        print(f"❌ [Stage 5 Gate] {detail}", file=sys.stderr)
        return False
    approved = {item["path"]: item["sha256"] for item in stage_snapshot(root_dir, 5)["artifacts"]}
    if rel not in approved or approved[rel] != sha256_file(segments_path):
        print("❌ 指定 segments 檔不在有效 stage-5 核准快照中，或核准後內容已變更。", file=sys.stderr)
        return False
    return True


def verify_stage4_gate(root_dir: Path, skip_gate: bool = False) -> bool:
    """舊名稱相容層：送件現在要求 stage-5，圖檔存在不會解鎖送件。"""
    candidates = sorted(root_dir.glob("segments-ep*.json"))
    return not skip_gate and len(candidates) == 1 and verify_stage5_gate(root_dir, candidates[0])


def audit_segment_prompts(todo_segs: List[Dict[str, Any]], root_dir: Optional[Path] = None,
                          strict_catalog: bool = False,
                          ack_warnings: Optional[List[str]] = None) -> Tuple[bool, List[str]]:
    """送件前執行 audit_refs_and_segments 確定性審查，杜絕劣質與錯誤 Prompt 浪費顯存。"""
    if audit_refs_and_subjects is None or lint_h3_prompt is None:
        return False, ["提示詞審查依賴 audit_refs_and_segments 不可用；fail closed，請修復環境後重試。"]

    errors: List[str] = []
    try:
        recorded_acks = failure_catalog.load_acks(root_dir) if root_dir else {}
    except failure_catalog.CatalogError as exc:
        return False, [f"ack 檔無法讀取（fail closed）：{exc}"]
    cli_acked = {str(item).strip().upper() for item in (ack_warnings or []) if str(item).strip()}
    try:
        catalog = failure_catalog.load_catalog(root_dir)
    except failure_catalog.CatalogError as exc:
        return False, [f"失敗目錄無法載入：{exc}"]
    for idx, seg in enumerate(todo_segs, 1):
        sid = seg.get("segment_id") or seg.get("group") or seg.get("id") or f"seg_{idx}"
        prompt = seg.get("h3_prompt") or seg.get("prompt", "")
        if not str(prompt).strip():
            errors.append(f"[{sid}] 缺少 H3 prompt，拒絕送件")
            continue

        dur = 7.0
        if "metadata" in seg and isinstance(seg["metadata"], dict):
            dur = float(seg["metadata"].get("target_duration_sec") or seg["metadata"].get("effective_duration_sec") or 7.0)

        # 模式 A: 參考圖序對
        if "reference_images" in seg:
            # FreeVideo 送件端只送 Ref2VA；段落自己宣告 remix 才走 remix 審查（R7 前 remix 不由這裡送）。
            seg_backend = ("remix" if "refmods" in seg or (seg.get("metadata") or {}).get("video_backend") == "remix"
                           else "ref2va")
            r_res = audit_refs_and_subjects(seg, project_root=root_dir, backend=seg_backend)
            if not r_res.get("passed", True):
                for e in r_res.get("errors", []):
                    errors.append(f"[{sid}] 模式 A 參考圖錯誤: {e}")

        # 模式 B: H3 提示詞 17 條自檢
        l_res = lint_h3_prompt(
            prompt,
            nominal_duration=dur,
            rounding_mode=seg.get("metadata", {}).get("rounding_mode", "floor"),
            authored_shots=seg.get("shots"),
        )
        if not l_res.get("passed", True):
            for e in l_res.get("errors", []):
                errors.append(f"[{sid}] 模式 B 提示詞錯誤: {e}")

        # 失敗目錄（P6）：enforce=error 直接擋；其餘警告要「有效 ack」才放行。
        # ack 綁在當時那份提示詞（segment + prompt sha），改稿就失效。
        prompt_sha = hashlib.sha256(str(prompt).encode("utf-8")).hexdigest()
        try:
            catalog_res = failure_catalog.lint_text(str(prompt), catalog)
        except failure_catalog.CatalogError as exc:
            return False, [f"失敗目錄執行失敗（{sid}）：{exc}"]
        for item in catalog_res["errors"]:
            errors.append(f"[{sid}] 失敗目錄: {failure_catalog.format_hit(item)}")
        for item in catalog_res["warnings"]:
            print(f"  ⚠️ [{sid}] {failure_catalog.format_hit(item)}")
            if strict_catalog:
                errors.append(f"[{sid}] 失敗目錄（strict）: {failure_catalog.format_hit(item)}")
            elif item["id"] in cli_acked:
                print(f"  ✅ [{sid}] {item['id']} 已由本次 --ack-warnings 接受")
            elif failure_catalog.ack_is_valid(recorded_acks.get(item["id"]), str(sid), prompt_sha,
                                              failure_catalog.catalog_rev(catalog)):
                print(f"  ✅ [{sid}] {item['id']} 已有涵蓋此稿的 ack 紀錄")
            else:
                errors.append(
                    f"[{sid}] {item['id']} 需明確確認：修正提示詞，或加 --ack-warnings {item['id']}"
                )

    # 逐鏡撰寫審查（防偷懶）：送出去的文字若是套模板、後設詞或編譯後被改寫，一律擋下
    try:
        author_res = prompt_authoring.audit_segments(todo_segs)
    except Exception as exc:  # fail closed
        return False, errors + [f"逐鏡撰寫審查無法執行（fail closed）：{exc}"]
    errors.extend(f"撰寫審查 {e}" for e in author_res["errors"])
    for w in author_res["warnings"]:
        print(f"  ⚠️ 撰寫審查 {w}")

    return len(errors) == 0, errors


ACTIVE_LEDGER_STATUSES = {
    "waiting", "queued", "running", "succeeded", "timeout", "interrupted", "unknown",
}


def active_job_for(ledger_path: Path, segment_id: str) -> Optional[Dict[str, Any]]:
    """同一個 segment 是否還有「不該重送」的 ledger 紀錄。

    這是 `--resume` 的安全鎖：中斷時 Ctrl-C 不會取消服務端任務，所以服務端
    可能還在跑；若只憑「本地沒有 mp4」就重送，同一段會被計費兩次。
    """
    ledger = load_job_ledger(ledger_path)
    for entry in reversed(ledger.get("jobs", []) or []):
        if str(entry.get("segment_id")) != str(segment_id):
            continue
        status = str(entry.get("status") or "")
        if status in ACTIVE_LEDGER_STATUSES:
            return entry
        if status in ("failed", "cancelled", "duration_drift"):
            return None
    return None


def collect_jobs(api_url: str, token: str, ledger_path: Path, output_dir: Path,
                 poll_wait: int = 0, only: Optional[List[str]] = None) -> Dict[str, int]:
    """把 ledger 裡「已完成但沒下載」的工作補回來；不送任何新件。

    這是 2026-10-19 那類事故的解藥：46 段批次跑到一半中斷，
    當時只能靠專案 helper 重送；現在 ledger 有 job id，可以直接收。

    - `failed`／`cancelled` 仍會**先查一次服務端**：本地記 failed 不代表遠端失敗
      （worker_exit、輪詢例外、collect 自己寫回的 failed 都會造成假失敗）。
    - 只有 `duration_drift` 是刻意跳過（那是我們自己判定的壞件）。
    - 時長無法斷言（ffprobe 讀不到或超差）一律隔離為 `.unverified.mp4`，不記 downloaded。
    """
    summary = {"downloaded": 0, "still_running": 0, "failed": 0, "skipped": 0,
               "drift": 0, "unverified": 0, "unreachable": 0, "aborted": 0}
    ledger = load_job_ledger(ledger_path)
    if not isinstance(ledger, dict) or not ledger.get("jobs"):
        print("[collect] ledger 沒有任何工作紀錄，沒有可收的件。")
        return summary

    ledger_scope = str(ledger.get("api_scope") or "").rstrip("/")
    if ledger_scope != str(api_url).rstrip("/"):
        print(f"[collect] ❌ API scope 不符：ledger={ledger_scope or '(空)'} / 現在={api_url}；"
              "為避免打錯 host 或寫錯帳本，中止。")
        summary["aborted"] = 1
        return summary
    if not ledger.get("project"):
        print("[collect] ❌ ledger 缺少 project 欄位，無法安全寫回；中止。")
        summary["aborted"] = 1
        return summary

    project = str(ledger["project"])
    api_scope = ledger_scope
    output_dir.mkdir(parents=True, exist_ok=True)
    only_set = {str(item) for item in only} if only else None

    # #93：同一段只收「最新一次」送件；較舊的 job 視為 superseded，不把舊結果收回。
    latest_idx: Dict[str, int] = {}
    for idx, entry in enumerate(ledger.get("jobs", [])):
        if entry.get("segment_id") and entry.get("id"):
            latest_idx[str(entry["segment_id"])] = idx

    for idx, entry in enumerate(ledger.get("jobs", [])):
        sid = entry.get("segment_id")
        jid = entry.get("id")
        if not sid or not jid:
            continue
        if latest_idx.get(str(sid)) != idx:
            summary["skipped"] += 1
            continue
        if only_set is not None and str(sid) not in only_set:
            continue
        out_mp4 = output_dir / f"{sid}.mp4"
        if out_mp4.exists():
            summary["skipped"] += 1
            continue
        if str(entry.get("status")) == "duration_drift":
            summary["failed"] += 1
            continue
        try:
            resp = call_api(api_url, token, "GET", f"/jobs/{jid}?wait={max(0, poll_wait)}",
                            timeout=max(10, poll_wait + 5))
        except Exception as exc:
            print(f"[collect] {sid}: 查詢失敗 {exc}")
            summary["unreachable"] += 1
            continue
        job = (resp or {}).get("job", {}) or {}
        state = str(job.get("status") or "")
        if state == "succeeded":
            frames = entry.get("frames")
            terminal = declared_frames(job)
            if frames and terminal is not None and int(frames) != terminal:
                print(f"[collect] {sid}: duration_drift（要求 {frames}，回報 {terminal}），不下載")
                record_job(ledger_path, project=project, api_scope=api_scope,
                           batch_id=str(entry.get("batch_id") or "collect"), segment_id=str(sid),
                           job_id=str(jid), status="duration_drift", frames=frames,
                           duration_assert=False)
                summary["drift"] += 1
                summary["failed"] += 1
                continue
            video_url = (job.get("result") or {}).get("video", {}).get("url")
            if not video_url:
                print(f"[collect] {sid}: 成功但沒有 video url")
                summary["failed"] += 1
                continue
            try:
                download_file(token, api_url, video_url, out_mp4)
            except Exception as exc:
                print(f"[collect] {sid}: 下載失敗 {exc}")
                summary["failed"] += 1
                continue
            probed = probe_video_duration(out_mp4)
            expected = h3_spec.seconds_for_frames(int(frames)) if frames else None
            asserted = bool(probed is not None and expected is not None
                            and abs(probed - expected) <= (1.0 / h3_spec.FPS) + 0.02)
            if not asserted:
                quarantine = out_mp4.with_name(out_mp4.stem + ".unverified.mp4")
                out_mp4.replace(quarantine)
                record_job(ledger_path, project=project, api_scope=api_scope,
                           batch_id=str(entry.get("batch_id") or "collect"), segment_id=str(sid),
                           job_id=str(jid), status="duration_unverified",
                           frames=int(frames) if frames else None, duration_assert=False)
                print(f"[collect] {sid}: 時長無法斷言（實測 {probed}，預期 {expected}），"
                      f"已隔離為 {quarantine.name}")
                summary["unverified"] += 1
                summary["failed"] += 1
                continue
            record_job(ledger_path, project=project, api_scope=api_scope,
                       batch_id=str(entry.get("batch_id") or "collect"), segment_id=str(sid),
                       job_id=str(jid), status="downloaded",
                       frames=int(frames) if frames else None,
                       seconds=h3_spec.wire_seconds(int(frames)) if frames else None,
                       duration_assert=True)
            print(f"[collect] {sid}: 已補下載 {out_mp4.name}")
            summary["downloaded"] += 1
        elif state in ("failed", "cancelled", "interrupted"):
            record_job(ledger_path, project=project, api_scope=api_scope,
                       batch_id=str(entry.get("batch_id") or "collect"), segment_id=str(sid),
                       job_id=str(jid), status=state)
            summary["failed"] += 1
        else:
            summary["still_running"] += 1

    print(f"[collect] 補下載 {summary['downloaded']}｜仍在跑 {summary['still_running']}"
          f"｜失敗 {summary['failed']}（drift {summary['drift']}、無法斷言 {summary['unverified']}）"
          f"｜查詢失敗 {summary['unreachable']}｜已存在跳過 {summary['skipped']}")
    return summary



def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="submit_h3_segments.py — MiniMax H3 批次分段影片送件工具"
    )
    parser.add_argument("--segments", type=Path, help="compile_layer2_to_h3 產出的 segments-epXX.json 路徑")
    parser.add_argument("--segment-id", nargs="*", help="指定僅執行特定分段 ID (如 EP01-S01-seg01)，預設跑全部")
    parser.add_argument("--output-dir", type=Path, default=Path("videos"), help="影片輸出儲存目錄 (預設 videos/)")
    parser.add_argument("--api-url", type=str, default=DEFAULT_API_URL, help="FreeVideo Agent API 位址")
    parser.add_argument("--quality", type=str, default="light", choices=["light", "medium", "high", "max"], help="生成畫質模式 (預設 light)")
    parser.add_argument("--dry-run", action="store_true", help="送件前乾跑檢查：檢查參考圖存在、SHA256、顯存狀態與分段摘要")
    parser.add_argument("--cancel-stale", action="store_true", help="清理伺服器殘留的孤兒分段任務")
    parser.add_argument("--collect", action="store_true",
                        help="只收件：掃 ledger，把已完成但沒下載的工作補抓回來，不送新件（不做 provider 能力校驗）")
    parser.add_argument("--resume", action="store_true",
                        help="續跑：先 collect 補回已完成的工作，再送尚未產出的分段")
    parser.add_argument("--collect-wait", type=int, default=0,
                        help="collect 時對每個工作的等待秒數（預設 0，只查現況）")
    parser.add_argument("--provider", default="freevideo", help="provider 能力表名稱（預設 freevideo）")
    parser.add_argument("--caps-dir", type=Path, default=None, help="provider 能力表目錄（選填）")
    parser.add_argument("--force", action="store_true", help="若目標影片已存在，強制重新送件覆蓋")
    parser.add_argument("--allow-out-of-range", action="store_true",
                        help="允許超出 H3 支援區間（124–362 幀）的分段照送；預設是硬錯誤")
    parser.add_argument("--strict-catalog", action="store_true",
                        help="把失敗目錄的警告升級為錯誤（預設：警告需 --ack-warnings 明確確認才放行）")
    parser.add_argument("--ack-warnings", nargs="*", default=None, metavar="ID",
                        help="明確接受指定的失敗目錄警告（例如 --ack-warnings F-STILL-ENDING）；會記錄在送件輸出中")
    parser.add_argument("--root-dir", type=Path, default=Path("."), help="專案根目錄 (用以解析相對路徑參考圖)")
    parser.add_argument("--skip-stage-gate", action="store_true", help="僅供 --dry-run 除錯；實際送件永遠要求有效 stage-5 核准")
    parser.add_argument("--poll-timeout", type=int, default=POLL_TIMEOUT_SECONDS,
                        help="每個 FreeVideo job 最長等待秒數；逾時保留 ledger 並回傳失敗")

    args = parser.parse_args(argv)

    # 1. 檢查 FreeVideo 令牌
    token = find_token()

    if args.cancel_stale:
        if not token:
            sys.exit("❌ 錯誤: 未找到 FreeVideo 令牌，無法執行 --cancel-stale。")
        cancel_stale_jobs(args.api_url, token, args.output_dir / "_fv-job-ledger.json", args.root_dir)
        return 0

    if args.collect or args.resume:
        if not token:
            sys.exit("❌ 錯誤: 未找到 FreeVideo 令牌，無法執行 --collect。")
        if args.resume and not args.segments:
            parser.error("--resume 需要同時提供 --segments（先收件，再補送）。")
        summary = collect_jobs(args.api_url, token, args.output_dir / "_fv-job-ledger.json",
                               args.output_dir, poll_wait=args.collect_wait, only=args.segment_id)
        bad = bool(summary["failed"] or summary["unreachable"] or summary.get("aborted"))
        if summary.get("aborted"):
            return 2
        if args.collect and not args.resume:
            return 1 if bad else 0
        if bad and not args.force:
            print("❌ collect 沒有全部收乾淨（失敗或查詢失敗）；為避免重複送件，停止續跑。"
                  "確認後可加 --force 強制續跑。")
            return 1

    if not args.segments:
        parser.error("請提供 --segments 參數指定分段 JSON 檔案，或使用 --cancel-stale。")

    if not args.segments.exists():
        sys.exit(f"❌ 錯誤: 分段檔不存在: {args.segments}")

    try:
        caps = provider_caps.load_caps(args.provider, args.caps_dir)
    except provider_caps.CapabilityError as exc:
        sys.exit(f"❌ 錯誤: {exc}")
    print(f"ℹ️ provider 能力：{provider_caps.describe(caps)}")
    for drift in provider_caps.consistency_warnings(caps):
        print(f"⚠️ [caps] {drift}（請更新 providers/{args.provider}.json）")

    # 讀取分段列表
    with args.segments.open("r", encoding="utf-8") as f:
        data = json.load(f)
    gate_scope: Dict[str, Any] = {}
    if not verify_stage5_gate(args.root_dir, args.segments, skip_gate=args.skip_stage_gate, dry_run=args.dry_run,
                              scope=gate_scope):
        return 1

    if isinstance(data, list):
        raw_segs = data
    elif isinstance(data, dict):
        raw_segs = data.get("segments", [data])
    else:
        sys.exit(f"❌ 錯誤: {args.segments} 結構非預期的 list 或 dict！")

    # 篩選分段
    todo_segs: List[Dict[str, Any]] = []
    for s in raw_segs:
        sid = s.get("group") or s.get("segment_id") or s.get("id")
        if not sid:
            continue
        if args.segment_id:
            if sid in args.segment_id:
                todo_segs.append(s)
        else:
            todo_segs.append(s)

    if not todo_segs:
        sys.exit(f"❌ 錯誤: 在 {args.segments} 中未找到符合條件的分段！")

    # PR-19a：stage-5 部分段核准後被改 → 只送已核准且未變的段。
    if "allowed" in gate_scope:
        allowed_ids = gate_scope["allowed"]
        blocked = [str(s.get("group") or s.get("segment_id") or s.get("id")) for s in todo_segs
                   if str(s.get("group") or s.get("segment_id") or s.get("id")) not in allowed_ids]
        if blocked and args.segment_id:
            print(f"❌ [Stage 5 Gate] 指定的段待重審、不能送件：{'、'.join(blocked)}", file=sys.stderr)
            return 1
        if blocked:
            print(f"⚠️ 跳過待重審段：{'、'.join(blocked)}")
        todo_segs = [s for s in todo_segs if str(s.get("group") or s.get("segment_id") or s.get("id")) in allowed_ids]
        if not todo_segs:
            print("❌ [Stage 5 Gate] 這個分段檔沒有已核准且未變的段可送。", file=sys.stderr)
            return 1

    # 執行提示詞確定性事前自檢
    # ack 只能由人透過 `h3d ack`（或 failure_catalog --ack）留下紀錄，
    # 送件端只讀不寫——否則「用新 ack 通過自己的 gate」就是自我授權。
    if args.ack_warnings:
        print("ℹ️ --ack-warnings 只在本次檢查有效、不會寫入紀錄；要留憑證請先跑："
              f"python scripts\\h3d.py ack --ids {' '.join(args.ack_warnings)}")

    prompt_ok, prompt_errors = audit_segment_prompts(
        todo_segs, root_dir=args.root_dir, strict_catalog=args.strict_catalog,
        ack_warnings=args.ack_warnings)
    if not prompt_ok:
        print("\n" + "=" * 78, file=sys.stderr)
        print(f"❌ [Fatal Audit Error - 提示詞品質自檢攔截 ({len(prompt_errors)} 項錯誤)]", file=sys.stderr)
        print("=" * 78, file=sys.stderr)
        for pe in prompt_errors:
            print(f"  • {pe}", file=sys.stderr)
        print("\n處置要求：請修正 Layer 2 分鏡或重新編譯 H3 提示詞，杜絕劣質 Prompt 浪費算力。\n", file=sys.stderr)
        return 1

    print("\n" + "=" * 70)
    print("🎬 MiniMax H3 分段影片送件管理器 (submit_h3_segments)")
    print("=" * 70)
    print(f"分段檔案: {args.segments.name} (待處理: {len(todo_segs)} 段)")
    print(f"輸出目錄: {args.output_dir.resolve()}")
    print(f"品質設定: {args.quality}")

    # 2. 顯存資訊僅做本機經驗性提醒，不以固定值判定可否執行。
    vram_info = get_gpu_vram()
    if vram_info:
        free_mb, total_mb = vram_info
        free_gib = free_mb / 1024.0
        print(f"GPU 顯存: 剩餘 {free_mb} MB ({free_gib:.2f} GiB) / 總量 {total_mb} MB")
        if free_mb < SAFE_VRAM_MB:
            diff_mb = SAFE_VRAM_MB - free_mb
            print(f"⚠️ 本機經驗性顯存警告：剩餘低於約 4.20 GiB ({SAFE_VRAM_MB} MB)；這不是所有 H3 執行環境的硬規格。")
            print(f"   低於本機提醒值約 {diff_mb} MB；可先降低其他 GPU 負載，仍須以實際服務回應判斷。")
        else:
            print("ℹ️ 高於本機經驗提醒值，不代表服務或模型必然可執行。")
    else:
        print("ℹ️ 未檢測到 nvidia-smi，跳過 GPU 顯存即時監控。")

    # 3. 乾跑檢查 (Dry-Run)
    all_refs_ok = True
    range_ok = True
    caps_ok = True
    range_problems: List[str] = []
    print("\n[分段清單與參考圖核驗]")
    for idx, seg in enumerate(todo_segs, 1):
        sid = seg.get("segment_id") or seg.get("group") or seg.get("id")

        # 時長一律由影格數反推（17n+5），避免四捨五入後被服務端向上取整。
        frames, frames_source = resolve_segment_frames(seg)
        sec = h3_spec.wire_seconds(frames)
        if not h3_spec.in_supported_range(frames):
            message = (f"#{idx:02d} [{sid}] {frames} 幀超出 H3 支援區間 "
                       f"{h3_spec.MIN_SUPPORTED_FRAMES}–{h3_spec.MAX_SUPPORTED_FRAMES}"
                       f"（{sec:.3f}s）")
            if args.allow_out_of_range:
                print(f"  ⚠️ {message}；已允許（--allow-out-of-range）")
            else:
                print(f"  ❌ {message}；請改分段長度或加 --allow-out-of-range")
                range_ok = False
                range_problems.append(message)

        # 提取參考素材路徑（含音色母帶）
        raw_refs = seg.get("reference_images", [])
        ref_paths: List[str] = []
        audio_paths: List[str] = []
        for r in raw_refs:
            if isinstance(r, dict):
                if r.get("type") == "audio":
                    audio_paths.append(r.get("path") or r.get("file") or "")
                ref_paths.append(r.get("path") or r.get("file") or "")
            elif isinstance(r, str):
                ref_paths.append(r)

        loras = seg.get("h3_loras", [])

        # provider 能力校驗：measured 欄位違反＝硬錯誤，docs/assumed 只警告。
        seg_aspect = seg.get("metadata", {}).get("aspect_ratio") or seg.get("aspect") or "16:9"
        caps_verdict = provider_caps.validate_segment(
            seg, caps, aspect=seg_aspect, quality=args.quality, frames=frames,
            reference_count=len([p for p in ref_paths if p]),
            audio_count=len(audio_paths), lora_count=len(loras),
        )
        for warning in caps_verdict["warnings"]:
            print(f"  ⚠️ [caps] {warning}")
        for error in caps_verdict["errors"]:
            print(f"  ❌ [caps] {error}")
            caps_ok = False

        # 核驗參考素材是否存在、格式是否受支援
        missing_refs = []
        bad_audio = []
        for p_str in ref_paths:
            if not p_str:
                continue
            rp = Path(p_str)
            if not rp.is_absolute():
                rp = (args.root_dir / rp).resolve()
            if not rp.exists():
                missing_refs.append(p_str)
        for p_str in audio_paths:
            if not p_str:
                continue
            suffix = Path(p_str).suffix.lower()
            if suffix not in SUPPORTED_AUDIO_SUFFIXES:
                bad_audio.append(f"{p_str}（{suffix or '無副檔名'}）")

        # 編譯時宣告「待補」的參考圖（pending_references）只放行審稿，不放行送件（#55）
        pending_refs = [str(x) for x in ((seg.get("metadata") or {}).get("pending_references") or [])]
        for pending in pending_refs:
            if pending not in missing_refs:
                missing_refs.append(pending)

        status_flag = "✅"
        if missing_refs or bad_audio:
            status_flag = "❌"
            all_refs_ok = False

        lora_desc = "無"
        if loras:
            lora_desc = "+".join(f"{l.get('name')}:{l.get('strength', 1.0)}" for l in loras)

        audio_note = f"（其中音色母帶 {len(audio_paths)} 個）" if audio_paths else ""
        print(f"  {status_flag} #{idx:02d} [{sid}] {sec:7.4f}s = {frames:3d} 幀（17n+5，來源 {frames_source}）"
              f" | 參考素材: {len(ref_paths)} 個{audio_note} | LoRA: {lora_desc}")
        if missing_refs:
            print(f"     ❌ 缺失參考素材檔案: {missing_refs}")
        if pending_refs:
            print("     ❌ 這些圖在編譯時被宣告為待補（pending_references）：補齊圖檔後重編再送")
        if bad_audio:
            print(f"     ❌ 音色母帶副檔名不受支援（需 {', '.join(sorted(SUPPORTED_AUDIO_SUFFIXES))}）: {bad_audio}")

    if args.dry_run:
        print("\n" + "-" * 70)
        print("🔍 乾跑 (Dry-Run) 檢查完成：")
        if all_refs_ok and range_ok and caps_ok:
            print("✅ 本地參考檔、提示詞、時長區間與 provider 能力檢查通過；尚未提交任務，也未驗證服務模型或 VRAM 是否可執行。")
            return 0
        if not caps_ok:
            print("❌ 有分段違反 provider 已驗證能力（見上方 [caps]）；請修正或改 provider 能力表。")
        if range_problems and not args.allow_out_of_range:
            print(f"❌ {len(range_problems)} 段超出 H3 支援區間；請改分段長度或加 --allow-out-of-range。")
        if not all_refs_ok:
            print("❌ 存在缺失的參考圖檔案！請檢查路徑後再試。")
        return 1

    # 4. 實機送件模式
    if not token:
        sys.exit("❌ 錯誤: 找不到本機 FreeVideo 令牌 (token)！請確認 FreeVideo 已安裝並開啟。")

    if not all_refs_ok:
        sys.exit("❌ 錯誤: 存在缺失的參考圖檔案，中止實機送件！")

    if not caps_ok:
        sys.exit("❌ 錯誤: 有分段違反 provider 已驗證能力（見上方 [caps]），中止送件。")

    if range_problems and not args.allow_out_of_range:
        sys.exit("❌ 錯誤: 有分段超出 H3 支援區間 "
                 f"({h3_spec.MIN_SUPPORTED_FRAMES}–{h3_spec.MAX_SUPPORTED_FRAMES} 幀)，中止送件；"
                 "請調整分段長度或加 --allow-out-of-range。")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    cache_file = args.output_dir / "_fv-ref-map.json"
    cache = load_media_cache(cache_file)
    ledger_path = args.output_dir / "_fv-job-ledger.json"
    project_root = args.root_dir.resolve()
    batch_id = f"{args.segments.stem}-{uuid.uuid4().hex}"
    prior_ledger = load_job_ledger(ledger_path)
    if prior_ledger and (prior_ledger.get("project") != str(project_root)
                         or prior_ledger.get("api_scope", "").rstrip("/") != args.api_url.rstrip("/")):
        print("❌ 輸出目錄中的 job ledger 屬於另一個 project/API scope；請指定新的 --output-dir。", file=sys.stderr)
        return 1
    if not prior_ledger:
        try:
            save_job_ledger(ledger_path, {
                "project": str(project_root), "api_scope": args.api_url.rstrip("/"), "jobs": [],
            })
        except OSError as exc:
            print(f"❌ 無法預先建立 job ledger，拒絕送件: {type(exc).__name__}", file=sys.stderr)
            return 1

    print("\n🚀 開始調用 FreeVideo Agent API 進行批次影片生成...")
    stats = {"succeeded": 0, "failed": 0, "skipped": 0, "unasserted": 0}

    for idx, seg in enumerate(todo_segs, 1):
        sid = seg.get("segment_id") or seg.get("group") or seg.get("id")

        # 時長一律由影格數反推（17n+5）
        frames, frames_source = resolve_segment_frames(seg)
        sec = h3_spec.wire_seconds(frames)
        if not h3_spec.in_supported_range(frames) and not args.allow_out_of_range:
            print(f"  ❌ [{sid}] {frames} 幀超出 H3 支援區間 "
                  f"{h3_spec.MIN_SUPPORTED_FRAMES}–{h3_spec.MAX_SUPPORTED_FRAMES}；跳過（需 --allow-out-of-range）")
            stats["failed"] += 1
            continue

        out_mp4 = args.output_dir / f"{sid}.mp4"

        if out_mp4.exists() and not args.force:
            print(f"\n[#{idx:02d} {sid}] 檔案已存在，跳過: {out_mp4.name}")
            stats["skipped"] += 1
            continue

        # ledger 去重：服務端可能還有活著的 job（中斷不會取消遠端任務），
        # 只憑「本地沒有 mp4」就重送會造成同一段重複計費。
        existing_job = active_job_for(ledger_path, str(sid))
        if existing_job and not args.force:
            print(f"\n[#{idx:02d} {sid}] ledger 已有 {existing_job.get('status')} 的 job "
                  f"{existing_job.get('id')}；跳過（先跑 --collect，或加 --force 重送）")
            stats["skipped"] += 1
            continue

        print(f"\n--- [#{idx:02d} {sid}] 開始送件 (時長: {sec:.4f}s = {frames} 幀，來源 {frames_source}) ---")

        # 提取參考素材路徑並上傳
        # 參考順序有意義：官方 ComfyUI 節點的規則是「圖片 → 影片 → 獨立音訊」，
        # 提示詞裡的 <Picture i> / <Video k> / <Audio j> 各自按自己的類別從 1 開始編號。
        # 編譯器把音訊參考排在所有圖像素材之後，正好符合這個順序。
        raw_refs = seg.get("reference_images", [])
        ref_paths: List[str] = []
        audio_refs: List[Dict[str, Any]] = []
        for r in raw_refs:
            if isinstance(r, dict):
                if r.get("type") == "audio":
                    audio_refs.append(r)
                ref_paths.append(r.get("path") or r.get("file") or "")
            elif isinstance(r, str):
                ref_paths.append(r)
        if audio_refs:
            print(f"     🎙️ [{sid}] 本段含 {len(audio_refs)} 個音色參考（<Audio N>）："
                  f"會以音檔形式掛到參考素材，提示詞用 <Audio N> 描述其角色。")

        remote_refs = []
        for p_str in ref_paths:
            if not p_str:
                continue
            rp = Path(p_str)
            if not rp.is_absolute():
                rp = (args.root_dir / rp).resolve()
            ref_id = upload_reference_media(args.api_url, token, rp, cache, cache_file)
            remote_refs.append({"file": ref_id})

        media = {"references": remote_refs}
        aspect = seg.get("metadata", {}).get("aspect_ratio") or seg.get("aspect", "16:9")
        loras = seg.get("h3_loras", [])
        prompt_text = seg.get("h3_prompt") or seg.get("prompt", "")

        body = {
            "kind": "generate",
            "prompt": prompt_text,
            "seconds": sec,  # = frames / 24 精確值；不可改成秒數四捨五入
            "aspect": aspect,
            "quality": args.quality,
            "label": seg.get("label", sid),
            "ref": f"seg-{sid.lower()}-{int(time.time())}",
            "media": media
        }
        if loras:
            body["loras"] = sanitize_loras(loras)

        # 提交任務
        try:
            job_resp = call_api(args.api_url, token, "POST", "/jobs", body)
            job = job_resp.get("job", {})
            jid = job.get("id")
            if not jid:
                raise RuntimeError("API 未回傳 job ID；無法安全追蹤此次送件")
            record_job(ledger_path, project=str(project_root), api_scope=args.api_url,
                       batch_id=batch_id, segment_id=str(sid), job_id=str(jid),
                       status=job.get("status", "waiting"), frames=frames, seconds=sec)
            print(f"  [+] 成功建立任務: {jid} | 標籤: {job.get('label')}")
        except Exception as e:
            print(f"  ❌ 建立任務失敗: {e}")
            stats["failed"] += 1
            continue

        # 時長斷言：服務端若回報 frames，必須等於我們要求的量子。
        # 不符就取消該工作（省 GPU），並以 duration_drift 記帳——不讓漂移的片子進 QA。
        reported = declared_frames(job)
        if reported is not None and reported != frames:
            print(f"  ❌ [duration_drift] 要求 {frames} 幀（{sec:.4f}s），服務端回報 {reported} 幀"
                  f"（{h3_spec.seconds_for_frames(reported):.4f}s）；已取消該工作。")
            try:
                call_api(args.api_url, token, "POST", f"/jobs/{jid}/cancel", {})
            except Exception as cancel_error:  # pragma: no cover - 服務端不可用時
                print(f"     ⚠️ 取消失敗（工作仍留在服務端）: {cancel_error}")
            record_job(ledger_path, project=str(project_root), api_scope=args.api_url,
                       batch_id=batch_id, segment_id=str(sid), job_id=str(jid),
                       status="duration_drift", frames=frames, seconds=sec)
            stats["failed"] += 1
            continue

        # 輪詢進度
        deadline = time.monotonic() + max(1, args.poll_timeout)
        while job.get("status") not in ("succeeded", "failed", "cancelled", "interrupted"):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                job["status"] = "timeout"
                print(f"  ⏱️ 輪詢逾時；job {jid} 保留於本機 ledger，未取消服務端任務。")
                break
            try:
                time.sleep(min(3, remaining))
                wait_seconds = max(1, min(25, int(remaining)))
                poll_resp = call_api(args.api_url, token, "GET", f"/jobs/{jid}?wait={wait_seconds}",
                                    timeout=wait_seconds + 5)
                job = poll_resp.get("job", {})
                record_job(ledger_path, project=str(project_root), api_scope=args.api_url,
                           batch_id=batch_id, segment_id=str(sid), job_id=str(jid), status=job.get("status", "unknown"))
            except KeyboardInterrupt:
                job["status"] = "interrupted"
                record_job(ledger_path, project=str(project_root), api_scope=args.api_url,
                           batch_id=batch_id, segment_id=str(sid), job_id=str(jid), status="interrupted")
                print(f"  ⏸️ 輪詢中斷；job {jid} 保留於本機 ledger，未取消服務端任務。")
                break
            except Exception as e:
                print(f"  [?] 輪詢例外: {e}")
                continue

        status = job.get("status")
        elapsed_min = 0.0

        if status == "succeeded":
            # 終態再斷言一次：POST 建立任務當下通常還沒有 geometry，
            # 只看第一次回應等於整個斷言空轉。
            terminal_frames = declared_frames(job)
            if terminal_frames is not None and terminal_frames != frames:
                print(f"  ❌ [duration_drift] 終態回報 {terminal_frames} 幀"
                      f"（{h3_spec.seconds_for_frames(terminal_frames):.4f}s），"
                      f"要求 {frames} 幀（{sec:.4f}s）；不下載。")
                record_job(ledger_path, project=str(project_root), api_scope=args.api_url,
                           batch_id=batch_id, segment_id=str(sid), job_id=str(jid),
                           status="duration_drift", frames=frames, seconds=sec,
                           duration_assert=False)
                stats["failed"] += 1
                continue
            if terminal_frames is None:
                stats["unasserted"] += 1
                print("  ⚠️ 服務端未回報 frames；時長只能在下載後用 ffprobe 驗。")
            video_url = (job.get("result") or {}).get("video", {}).get("url")
            if video_url:
                try:
                    download_file(token, args.api_url, video_url, out_mp4)
                    expected_sec = h3_spec.seconds_for_frames(frames)
                    probed = probe_video_duration(out_mp4)
                    if probed is None:
                        stats["unasserted"] += 1
                        print("  ⚠️ ffprobe 讀不到時長，無法斷言影格數。")
                    elif abs(probed - expected_sec) > (1.0 / h3_spec.FPS) + 0.02:
                        drifted = out_mp4.with_name(out_mp4.stem + ".drift.mp4")
                        out_mp4.replace(drifted)
                        print(f"  ❌ [duration_drift] 檔案 {probed:.3f}s，預期 {expected_sec:.3f}s"
                              f"（{frames} 幀）；已隔離為 {drifted.name}，不進 QA。")
                        record_job(ledger_path, project=str(project_root), api_scope=args.api_url,
                                   batch_id=batch_id, segment_id=str(sid), job_id=str(jid),
                                   status="duration_drift", frames=frames, seconds=sec,
                                   duration_assert=False)
                        stats["failed"] += 1
                        continue
                    record_job(ledger_path, project=str(project_root), api_scope=args.api_url,
                               batch_id=batch_id, segment_id=str(sid), job_id=str(jid),
                               status="downloaded", frames=frames, seconds=sec,
                               duration_assert=probed is not None)
                    size_mb = out_mp4.stat().st_size / 1048576.0
                    print(f"  ✅ 生成成功並已下載: {out_mp4.name} ({size_mb:.2f} MB, 耗時: {elapsed_min:.1f} 分鐘)")
                    stats["succeeded"] += 1
                except Exception as e:
                    print(f"  ❌ 下載影片檔案失敗: {e}")
                    stats["failed"] += 1
            else:
                print(f"  ❌ 任務標記成功但無影片 URL！")
                stats["failed"] += 1
        else:
            err = job.get("error") or {}
            print(f"  ❌ 任務失敗: {status} | 代碼: {err.get('code')} | 訊息: {err.get('message')}")
            if err.get("next"):
                print(f"     💡 建議處置: {err.get('next')}")
            stats["failed"] += 1
            record_job(ledger_path, project=str(project_root), api_scope=args.api_url,
                       batch_id=batch_id, segment_id=str(sid), job_id=str(jid), status=str(status))
        if status in ("timeout", "interrupted"):
            # Stop this batch immediately; remote job is still tracked and is
            # never implicitly cancelled by an interruption or deadline.
            break

    print("\n" + "=" * 70)
    print(f"🎉 批次送件結束: 成功: {stats['succeeded']} | 失敗: {stats['failed']} | 跳過: {stats['skipped']}")
    if stats["unasserted"]:
        print(f"⚠️ 其中 {stats['unasserted']} 段無法斷言時長（服務端未回 frames 或 ffprobe 讀不到）；"
              "這些段落不算通過，請用 verify_video_shot 再驗一次。")
    print("=" * 70)
    return 0 if stats["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
