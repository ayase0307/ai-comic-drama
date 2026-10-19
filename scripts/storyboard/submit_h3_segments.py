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
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple
import urllib.request
import urllib.error
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
from project_state import require_approved, sha256_file, stage_snapshot

try:
    from audit_refs_and_segments import audit_refs_and_subjects, lint_h3_prompt
except ImportError:
    audit_refs_and_subjects = None
    lint_h3_prompt = None


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
               segment_id: str, job_id: str, status: str = "waiting") -> None:
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
    save_job_ledger(path, ledger)


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


def upload_reference_image(api_url: str, token: str, img_path: Path, cache: Dict[str, str], cache_file: Path) -> str:
    """計算 SHA256 增量上傳參考圖至 FreeVideo /media 接口。"""
    if not img_path.exists():
        raise FileNotFoundError(f"找不到參考圖檔案: {img_path}")
    
    data_bytes = img_path.read_bytes()
    sha = hashlib.sha256(data_bytes).hexdigest()
    cache_key = api_url.rstrip("/") + "::" + sha
    if cache_key in cache:
        return cache[cache_key]
    
    b64 = base64.b64encode(data_bytes).decode("ascii")
    payload = {
        "name": img_path.name,
        "data_base64": b64
    }
    resp = call_api(api_url, token, "POST", "/media", payload)
    remote_file_id = resp.get("file", "")
    if not remote_file_id:
        raise RuntimeError(f"上傳參考圖 {img_path.name} 失敗，API 未回傳 file id")
    
    cache[cache_key] = remote_file_id
    save_media_cache(cache_file, cache)
    print(f"   [+] 成功上傳新參考圖: {img_path.name} -> {remote_file_id}")
    return remote_file_id


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


def verify_stage5_gate(root_dir: Path, segments_path: Path, skip_gate: bool = False, dry_run: bool = False) -> bool:
    """要求當前批次 segments 與其參考圖均在有效 stage-5 核准快照內。"""
    if skip_gate:
        if dry_run:
            print("⚠️ [debug] --skip-stage-gate 僅於 --dry-run 可用。")
            return True
        print("❌ --skip-stage-gate 僅允許 dry-run；實際送件必須有 stage-5 核准。", file=sys.stderr)
        return False
    ok, detail = require_approved(root_dir, 5)
    if not ok:
        print(f"❌ [Stage 5 Gate] {detail}", file=sys.stderr)
        return False
    try:
        rel = segments_path.resolve().relative_to(root_dir.resolve()).as_posix()
    except ValueError:
        print("❌ segments 檔必須位於專案中，並列入 stage-5 核准快照。", file=sys.stderr)
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


def audit_segment_prompts(todo_segs: List[Dict[str, Any]]) -> Tuple[bool, List[str]]:
    """送件前執行 audit_refs_and_segments 17 條確定性審查，杜絕劣質與錯誤 Prompt 浪費顯存。"""
    if audit_refs_and_subjects is None or lint_h3_prompt is None:
        return False, ["提示詞審查依賴 audit_refs_and_segments 不可用；fail closed，請修復環境後重試。"]

    errors: List[str] = []
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
            r_res = audit_refs_and_subjects(seg)
            if not r_res.get("passed", True):
                for e in r_res.get("errors", []):
                    errors.append(f"[{sid}] 模式 A 參考圖錯誤: {e}")

        # 模式 B: H3 提示詞 17 條自檢
        l_res = lint_h3_prompt(prompt, nominal_duration=dur)
        if not l_res.get("passed", True):
            for e in l_res.get("errors", []):
                errors.append(f"[{sid}] 模式 B 提示詞錯誤: {e}")

    return len(errors) == 0, errors


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="submit_h3_segments.py — MiniMax H3 批次分段影片送件工具"
    )
    parser.add_argument("--segments", type=Path, help="compile_layer2_to_h3 產出的 segments-epXX.json 路徑")
    parser.add_argument("--segment-id", nargs="*", help="指定僅執行特定分段 ID (如 EP01-S01-seg01)，預設跑全部")
    parser.add_argument("--output-dir", type=Path, default=Path("videos"), help="影片輸出儲存目錄 (預設 videos/)")
    parser.add_argument("--api-url", type=str, default=DEFAULT_API_URL, help="FreeVideo Agent API 位址")
    parser.add_argument("--quality", type=str, default="light", choices=["light", "plus"], help="生成畫質模式 (預設 light)")
    parser.add_argument("--dry-run", action="store_true", help="送件前乾跑檢查：檢查參考圖存在、SHA256、顯存狀態與分段摘要")
    parser.add_argument("--cancel-stale", action="store_true", help="清理伺服器殘留的孤兒分段任務")
    parser.add_argument("--force", action="store_true", help="若目標影片已存在，強制重新送件覆蓋")
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

    if not args.segments:
        parser.error("請提供 --segments 參數指定分段 JSON 檔案，或使用 --cancel-stale。")

    if not args.segments.exists():
        sys.exit(f"❌ 錯誤: 分段檔不存在: {args.segments}")

    # 讀取分段列表
    with args.segments.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not verify_stage5_gate(args.root_dir, args.segments, skip_gate=args.skip_stage_gate, dry_run=args.dry_run):
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

    # 執行提示詞確定性事前自檢
    prompt_ok, prompt_errors = audit_segment_prompts(todo_segs)
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
    print("\n[分段清單與參考圖核驗]")
    for idx, seg in enumerate(todo_segs, 1):
        sid = seg.get("segment_id") or seg.get("group") or seg.get("id")
        
        # 提取時長
        sec = 0.0
        if "metadata" in seg and isinstance(seg["metadata"], dict):
            sec = float(seg["metadata"].get("effective_duration_sec") or seg["metadata"].get("target_duration_sec") or 0.0)
        if sec <= 0.0:
            sec = float(seg.get("seconds") or 0.0)

        # 提取參考圖路徑
        raw_refs = seg.get("reference_images", [])
        ref_paths: List[str] = []
        for r in raw_refs:
            if isinstance(r, dict):
                ref_paths.append(r.get("path") or r.get("file") or "")
            elif isinstance(r, str):
                ref_paths.append(r)

        loras = seg.get("h3_loras", [])

        # 核驗參考圖是否存在
        missing_refs = []
        for p_str in ref_paths:
            if not p_str:
                continue
            rp = Path(p_str)
            if not rp.is_absolute():
                rp = (args.root_dir / rp).resolve()
            if not rp.exists():
                missing_refs.append(p_str)

        status_flag = "✅"
        if missing_refs:
            status_flag = "❌"
            all_refs_ok = False

        lora_desc = "無"
        if loras:
            lora_desc = "+".join(f"{l.get('name')}:{l.get('strength', 1.0)}" for l in loras)

        print(f"  {status_flag} #{idx:02d} [{sid}] {sec:5.2f}s | 參考圖: {len(ref_paths)}張 | LoRA: {lora_desc}")
        if missing_refs:
            print(f"     ❌ 缺失參考圖檔案: {missing_refs}")

    if args.dry_run:
        print("\n" + "-" * 70)
        print("🔍 乾跑 (Dry-Run) 檢查完成：")
        if all_refs_ok:
            print("✅ 本地參考檔與提示詞檢查通過；尚未提交任務，也未驗證服務模型或 VRAM 是否可執行。")
            return 0
        else:
            print("❌ 存在缺失的參考圖檔案！請檢查路徑後再試。")
            return 1

    # 4. 實機送件模式
    if not token:
        sys.exit("❌ 錯誤: 找不到本機 FreeVideo 令牌 (token)！請確認 FreeVideo 已安裝並開啟。")

    if not all_refs_ok:
        sys.exit("❌ 錯誤: 存在缺失的參考圖檔案，中止實機送件！")

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
    stats = {"succeeded": 0, "failed": 0, "skipped": 0}

    for idx, seg in enumerate(todo_segs, 1):
        sid = seg.get("segment_id") or seg.get("group") or seg.get("id")
        
        # 提取時長
        sec = 0.0
        if "metadata" in seg and isinstance(seg["metadata"], dict):
            sec = float(seg["metadata"].get("effective_duration_sec") or seg["metadata"].get("target_duration_sec") or 0.0)
        if sec <= 0.0:
            sec = float(seg.get("seconds") or 0.0)

        out_mp4 = args.output_dir / f"{sid}.mp4"

        if out_mp4.exists() and not args.force:
            print(f"\n[#{idx:02d} {sid}] 檔案已存在，跳過: {out_mp4.name}")
            stats["skipped"] += 1
            continue

        print(f"\n--- [#{idx:02d} {sid}] 開始送件 (時長: {sec:.2f}s) ---")

        # 提取參考圖路徑並上傳
        raw_refs = seg.get("reference_images", [])
        ref_paths: List[str] = []
        for r in raw_refs:
            if isinstance(r, dict):
                ref_paths.append(r.get("path") or r.get("file") or "")
            elif isinstance(r, str):
                ref_paths.append(r)

        remote_refs = []
        for p_str in ref_paths:
            if not p_str:
                continue
            rp = Path(p_str)
            if not rp.is_absolute():
                rp = (args.root_dir / rp).resolve()
            ref_id = upload_reference_image(args.api_url, token, rp, cache, cache_file)
            remote_refs.append({"file": ref_id})

        media = {"references": remote_refs}
        aspect = seg.get("metadata", {}).get("aspect_ratio") or seg.get("aspect", "16:9")
        loras = seg.get("h3_loras", [])
        prompt_text = seg.get("h3_prompt") or seg.get("prompt", "")

        body = {
            "kind": "generate",
            "prompt": prompt_text,
            "seconds": sec,
            "aspect": aspect,
            "quality": args.quality,
            "label": seg.get("label", sid),
            "ref": f"seg-{sid.lower()}-{int(time.time())}",
            "media": media
        }
        if loras:
            body["loras"] = loras

        # 提交任務
        try:
            job_resp = call_api(args.api_url, token, "POST", "/jobs", body)
            job = job_resp.get("job", {})
            jid = job.get("id")
            if not jid:
                raise RuntimeError("API 未回傳 job ID；無法安全追蹤此次送件")
            record_job(ledger_path, project=str(project_root), api_scope=args.api_url,
                       batch_id=batch_id, segment_id=str(sid), job_id=str(jid), status=job.get("status", "waiting"))
            print(f"  [+] 成功建立任務: {jid} | 標籤: {job.get('label')}")
        except Exception as e:
            print(f"  ❌ 建立任務失敗: {e}")
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
            video_url = (job.get("result") or {}).get("video", {}).get("url")
            if video_url:
                try:
                    download_file(token, args.api_url, video_url, out_mp4)
                    record_job(ledger_path, project=str(project_root), api_scope=args.api_url,
                               batch_id=batch_id, segment_id=str(sid), job_id=str(jid), status="downloaded")
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
    print("=" * 70)
    return 0 if stats["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
