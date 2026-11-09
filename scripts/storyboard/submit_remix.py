#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
submit_remix.py — REMIX Studio 送件 adapter（PR-R7）

讀取 compile_layer2_to_h3.py 產出的 REMIX 三欄 segments（`metadata.video_backend=="remix"`、
帶 `refmods`），對接家機 REMIX Studio（`/remix/agent/v1`）：
POST /jobs → 輪詢 → 下載 → identity → 帳本（`videos/remix-jobs.json`）。

與 FreeVideo 送件端（submit_h3_segments.py）的分工：
  - 這支只送 remix 段；看到 ref2va 段直接拒絕（反向也一樣）。
  - 送件前照跑同一套門禁：stage-5 核准、audit remix 分支、lint(backend="remix")、
    失敗目錄、逐鏡撰寫審查、編譯指紋（E38）、能力表校驗。
  - 後端實際影格數以回報為準（16g：Pika 引擎 ceil，編譯值與實際可能差一個量子），
    差異記進帳本並警告，不硬擋；檔案壞掉才隔離。

【安全鐵律】嚴禁在任何終端輸出、日誌、例外或報表中印出 REMIX 令牌！

CLI 用法：
  python scripts/storyboard/submit_remix.py --segments segments-ep04.json --project <studio專案> [--dry-run]
  python scripts/storyboard/submit_remix.py --segments segments-ep04.json --collect
  python scripts/storyboard/submit_remix.py --segments segments-ep04.json --mode pika480 --seed 123   # 抽卡
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
import urllib.request
import urllib.error
import urllib.parse

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

from project_state import record_gate_bypass, sha256_file  # noqa: E402

try:
    from audit_refs_and_segments import audit_refs_and_subjects, lint_h3_prompt
except ImportError:  # pragma: no cover
    audit_refs_and_subjects = None
    lint_h3_prompt = None

try:  # 以 scripts/storyboard 為 sys.path 執行（CLI 慣例）
    import failure_catalog
    import prompt_authoring
    from submit_h3_segments import (SameOriginRedirectHandler, probe_video_duration,
                                    verify_stage5_gate)
except ImportError:  # pragma: no cover - 套件匯入路徑
    from . import failure_catalog  # type: ignore
    from . import prompt_authoring  # type: ignore
    from .submit_h3_segments import (SameOriginRedirectHandler, probe_video_duration,
                                     verify_stage5_gate)  # type: ignore

import decisions as decisions_mod  # noqa: E402
import h3_spec  # noqa: E402
import provider_caps  # noqa: E402

DEFAULT_API_URL = os.environ.get("REMIX_API_URL", "").strip() or "http://127.0.0.1:8190/remix/agent/v1"
DEFAULT_TOKEN_FILE = os.environ.get("REMIX_TOKEN_FILE", "").strip()
CLIENT_NAME = "ai-comic-drama"
POLL_WAIT_SECONDS = 25
DEFAULT_JOB_TIMEOUT = 2400  # pika1440 10s ≈ 1420s，留餘裕
LEDGER_NAME = "remix-jobs.json"
# 要求本身若已經等了這麼久，視為伺服器有長輪詢，不再額外 sleep。
_LONG_POLL_CREDIT_SECONDS = 0.8


class RemixTransportError(Exception):
    """連不上 REMIX。訊息只描述原因，不得含令牌或 Authorization。"""


# ---------------------------------------------------------------------------
# 帳本
# ---------------------------------------------------------------------------

def load_ledger(path: Path) -> Dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_ledger(path: Path, ledger: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(ledger, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def ledger_entry(ledger: Dict[str, Any], segment_id: str) -> Optional[Dict[str, Any]]:
    for item in ledger.get("jobs", []):
        if isinstance(item, dict) and item.get("segment_id") == segment_id:
            return item
    return None


# ---------------------------------------------------------------------------
# HTTP（令牌不落地、不印出）
# ---------------------------------------------------------------------------

def _read_secret_file(path: Path) -> str:
    """讀令牌檔。Windows 記事本的 UTF-8 會加 BOM，不剝掉就會進 Authorization 標頭。"""
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise SystemExit(f"❌ 讀不到令牌檔（令牌不會被印出）：{exc.strerror or type(exc).__name__}") from exc
    except UnicodeError:
        raise SystemExit("❌ 令牌檔不是 UTF-8（令牌不會被印出）") from None
    return text.strip().lstrip("\ufeff").strip()


def resolve_token(args: argparse.Namespace) -> str:
    token = ""
    if getattr(args, "token_file", None):
        token = _read_secret_file(Path(args.token_file))
    if not token:
        token = os.environ.get("REMIX_API_TOKEN", "").strip()
    if not token and DEFAULT_TOKEN_FILE:
        token = _read_secret_file(Path(DEFAULT_TOKEN_FILE))
    if not token:
        raise SystemExit("❌ 找不到 REMIX 令牌：--token-file、REMIX_API_TOKEN 或 REMIX_TOKEN_FILE 擇一提供（令牌不會被印出）")
    try:
        token.encode("latin-1")
    except UnicodeEncodeError:
        # HTTP 標頭只能 latin-1。把令牌印出來排錯會違反安全鐵律，所以只講原因。
        raise SystemExit("❌ 令牌含無法放進 HTTP 標頭的字元（令牌不會被印出）") from None
    return token


def studio_request(api_url: str, token: str, path: str, method: str = "GET",
                   body: Optional[Dict[str, Any]] = None, timeout: int = 30) -> Tuple[int, Dict[str, Any]]:
    """回 (status, json)；令牌只進 header，不進任何輸出。"""
    url = api_url.rstrip("/") + path
    data = None
    headers = {"Authorization": f"Bearer {token}", "X-Remix-Client": CLIENT_NAME,
               "Accept": "application/json"}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    opener = urllib.request.build_opener(SameOriginRedirectHandler())
    try:
        with opener.open(request, timeout=timeout) as response:
            raw = response.read()
            status = response.status
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        status = exc.code
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        # URLError.reason 是連線原因，不含 Authorization。不要 str(request)。
        reason = getattr(exc, "reason", None)
        detail = reason if reason is not None else exc
        raise RemixTransportError(f"無法連線 REMIX：{detail}") from exc
    try:
        payload = json.loads(raw.decode("utf-8")) if raw else {}
    except (UnicodeDecodeError, json.JSONDecodeError):
        payload = {"_raw": True}
    return status, payload if isinstance(payload, dict) else {"_payload": payload}


def download_file(api_url: str, token: str, job_id: str, dest: Path) -> None:
    url = api_url.rstrip("/") + "/jobs/" + urllib.parse.quote(str(job_id), safe="") + "/file"
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}",
                                                   "X-Remix-Client": CLIENT_NAME})
    opener = urllib.request.build_opener(SameOriginRedirectHandler())
    dest.parent.mkdir(parents=True, exist_ok=True)
    temporary = dest.with_name(dest.name + ".part")
    with opener.open(request, timeout=120) as response, temporary.open("wb") as fh:
        while True:
            chunk = response.read(1 << 20)
            if not chunk:
                break
            fh.write(chunk)
    temporary.replace(dest)


# ---------------------------------------------------------------------------
# 段落挑選與送件前檢查
# ---------------------------------------------------------------------------

def is_remix_segment(seg: Dict[str, Any]) -> bool:
    return "refmods" in seg or (seg.get("metadata") or {}).get("video_backend") == "remix"


def resolve_segment_mode(seg: Dict[str, Any], batch_mode: str) -> Tuple[str, List[str]]:
    """P1-1 第二片：Base i2v 段在 REMIX 必須走 pikaff*（才有 first_frame 欄位）。

    pika480→pikaff480、pika768→pikaff768；批次模式已是 pikaff* 就照用；
    沒有對應 pikaff 變體的模式（pika1440／draft／refine／long）直接報錯（fail closed）。
    """
    generation_mode = str((seg.get("metadata") or {}).get("generation_mode") or "r2v").strip().lower()
    if generation_mode != "i2v":
        return batch_mode, []
    if batch_mode.startswith("pikaff"):
        return batch_mode, []
    variant = {"pika480": "pikaff480", "pika768": "pikaff768"}.get(batch_mode)
    if not variant:
        raise ValueError(f"generation_mode=i2v 在 REMIX 需要 pikaff 模式（first_frame 欄位）；"
                         f"批次模式 {batch_mode} 沒有對應的 pikaff 變體")
    return variant, [f"generation_mode=i2v：送件模式 {batch_mode} → {variant}（pikaff 才有 first_frame 欄位）"]


def split_by_backend(segments: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[str]]:
    remix_segs: List[Dict[str, Any]] = []
    refused: List[str] = []
    for seg in segments:
        sid = str(seg.get("segment_id") or seg.get("id") or "?")
        if is_remix_segment(seg):
            remix_segs.append(seg)
        else:
            refused.append(sid)
    return remix_segs, refused


def verify_compiled_fingerprint(seg: Dict[str, Any]) -> Optional[str]:
    """E38：編譯後提示詞被改過就拒送。回錯誤訊息或 None。"""
    metadata = seg.get("metadata") or {}
    expected = metadata.get("compiled_prompt_sha256")
    prompt = str(seg.get("h3_prompt") or "")
    if not expected:
        return "缺 metadata.compiled_prompt_sha256（舊格式或被手改）；先重跑 h3d compile"
    if prompt_authoring.prompt_fingerprint(prompt) != expected:
        return "h3_prompt 與 compiled_prompt_sha256 不符（編譯後被改過，E38）；先重跑 h3d compile"
    return None


def requested_frames(seg: Dict[str, Any]) -> Tuple[int, Optional[str]]:
    """送件的目標影格數：以 metadata.frames 為準；不是量子就往上吸附並警告。"""
    metadata = seg.get("metadata") or {}
    frames = metadata.get("frames")
    note = None
    if not isinstance(frames, int) or frames <= 0:
        exact = metadata.get("effective_duration_sec_exact") or metadata.get("effective_duration_sec")
        if not exact:
            raise ValueError("缺 metadata.frames／effective_duration_sec；先重跑 h3d compile")
        frames = int(round(float(exact) * h3_spec.FPS))
        note = f"metadata.frames 缺失，依 effective_duration 秒數換算 {frames} 幀"
    if not h3_spec.is_quantum(frames):
        snapped = h3_spec.frames_for(frames / h3_spec.FPS, rounding="ceil")
        note = (note or "") + f"；{frames} 幀不是 17n+5 量子，往上吸附成 {snapped}（伺服器會往上取）"
        frames = snapped
    return int(frames), (note.strip() if note else None)


def precheck_segments(segments: List[Dict[str, Any]], root_dir: Optional[Path], caps: Dict[str, Any],
                      mode: str, steps: Optional[int], strict_catalog: bool,
                      ack_warnings: Optional[List[str]]) -> Tuple[bool, List[str]]:
    """送件前確定性審查（remix 分支）：audit＋lint＋失敗目錄＋撰寫審查＋指紋＋能力表。"""
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

    for idx, seg in enumerate(segments, 1):
        sid = str(seg.get("segment_id") or seg.get("id") or f"seg_{idx}")
        prompt = str(seg.get("h3_prompt") or "")
        if not prompt.strip():
            errors.append(f"[{sid}] 缺少 h3_prompt，拒絕送件")
            continue
        fingerprint_error = verify_compiled_fingerprint(seg)
        if fingerprint_error:
            errors.append(f"[{sid}] {fingerprint_error}")
            continue
        try:
            frames, frames_note = requested_frames(seg)
        except ValueError as exc:
            errors.append(f"[{sid}] {exc}")
            continue
        if frames_note:
            print(f"  ⚠️ [{sid}] {frames_note}")

        # P1-1 第二片：Base 模式（t2v／i2v／fl2v）在 REMIX 的送件規則——
        # i2v 必須走 pikaff*（first_frame 欄位）且幀來源存在；fl2v 送不了（pikaff 沒有尾幀欄位）。
        generation_mode = str((seg.get("metadata") or {}).get("generation_mode") or "r2v").strip().lower()
        seg_mode = mode
        has_first_frame = False
        if generation_mode == "fl2v":
            errors.append(f"[{sid}] generation_mode=fl2v 在 REMIX 送不了：pikaff 只有 first_frame 欄位；"
                          "fl2v（首尾幀）請走 FreeVideo 送件端（h3d submit）")
            continue
        if generation_mode == "i2v":
            try:
                seg_mode, mode_warnings_ = resolve_segment_mode(seg, mode)
            except ValueError as exc:
                errors.append(f"[{sid}] {exc}")
                continue
            for w in mode_warnings_:
                print(f"  ⚠️ [{sid}] {w}")
            has_first_frame = True
            frame_sources = (seg.get("metadata") or {}).get("frame_sources") or {}
            rel = str(frame_sources.get("first") or "").strip()
            if not rel:
                errors.append(f"[{sid}] generation_mode=i2v 缺 metadata.frame_sources.first；先重跑 h3d compile")
                continue
            fp = Path(rel)
            if not fp.is_absolute() and root_dir:
                fp = root_dir / rel
            if not fp.exists():
                errors.append(f"[{sid}] 首幀來源檔不存在: {rel}")
                continue

        r_res = audit_refs_and_subjects(seg, project_root=root_dir, backend="remix")
        if not r_res.get("passed", True):
            errors.extend(f"[{sid}] 模式 A 參考包錯誤: {e}" for e in r_res.get("errors", []))
        l_res = lint_h3_prompt(prompt, nominal_duration=float((seg.get("metadata") or {}).get("target_duration_sec") or 7.0),
                               rounding_mode=(seg.get("metadata") or {}).get("rounding_mode", "floor"),
                               authored_shots=seg.get("shots"), backend="remix", submit_endpoint="local",
                               generation_mode=generation_mode)
        if not l_res.get("passed", True):
            errors.extend(f"[{sid}] 模式 B 提示詞錯誤: {e}" for e in l_res.get("errors", []))

        prompt_sha = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        try:
            catalog_res = failure_catalog.lint_text(prompt, catalog)
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
                errors.append(f"[{sid}] {item['id']} 需明確確認：修正提示詞，或加 --ack-warnings {item['id']}")

        refmods = seg.get("refmods") or []
        caps_res = provider_caps.validate_segment(
            seg, caps, aspect=(seg.get("metadata") or {}).get("aspect_ratio"),
            frames=frames, refmod_count=len(refmods), mode=seg_mode, steps=steps,
            seconds=frames / h3_spec.FPS, has_project=True, has_negative=False,
            has_first_frame=has_first_frame)
        errors.extend(caps_res["errors"])
        for w in caps_res["warnings"]:
            print(f"  ⚠️ [{sid}] {w}")

    try:
        author_res = prompt_authoring.audit_segments(segments)
    except Exception as exc:  # fail closed
        return False, errors + [f"逐鏡撰寫審查無法執行（fail closed）：{exc}"]
    errors.extend(f"撰寫審查 {e}" for e in author_res["errors"])
    for w in author_res["warnings"]:
        print(f"  ⚠️ 撰寫審查 {w}")
    return not errors, errors


# ---------------------------------------------------------------------------
# 送件
# ---------------------------------------------------------------------------

def _render_state(state: Any, limit: int = 600) -> str:
    """segment_end_state.planned_final_state（dict）→ plan 欄位的短文字（≤limit 字元）。"""
    if not isinstance(state, dict) or not state:
        return ""
    parts = []
    for key, value in state.items():
        text = str(value).strip()
        if text:
            parts.append(f"{key}: {text}")
    out = "; ".join(parts)
    return out[:limit]


def build_job_body(seg: Dict[str, Any], project: str, mode: str, seed: Optional[int],
                   prev_end_state: Any = None, root_dir: Optional[Path] = None) -> Tuple[Dict[str, Any], List[str]]:
    warnings: List[str] = []
    metadata = seg.get("metadata") or {}
    frames, note = requested_frames(seg)
    if note:
        warnings.append(note)
    refmods = [str(r.get("pack")) for r in (seg.get("refmods") or []) if r.get("pack")]
    body: Dict[str, Any] = {
        "prompt": str(seg.get("h3_prompt") or ""),
        "refmods": refmods,
        "seconds": h3_spec.wire_seconds(frames),
        "aspect": metadata.get("aspect_ratio") or "16:9",
        "mode": mode,
        "label": str(seg.get("segment_id") or "segment"),
        "shot": str(seg.get("segment_id") or "segment"),
        "project": project,
        "plan": {
            "title_zh": str(seg.get("segment_id") or "segment")[:60],
            "end_state": _render_state((seg.get("segment_end_state") or {}).get("planned_final_state")),
        },
    }
    # P1-1 第二片：Base 模式的幀欄位——i2v 帶 first_frame（pikaff 模式）；fl2v 在 REMIX 送不了。
    generation_mode = str((seg.get("metadata") or {}).get("generation_mode") or "r2v").strip().lower()
    if generation_mode == "fl2v":
        raise ValueError("generation_mode=fl2v 在 REMIX 送不了：pikaff 只有 first_frame 欄位；"
                         "fl2v（首尾幀）請走 FreeVideo 送件端（h3d submit）")
    if generation_mode == "i2v":
        frame_sources = (seg.get("metadata") or {}).get("frame_sources") or {}
        rel = str(frame_sources.get("first") or "").strip()
        if not rel:
            raise ValueError("generation_mode=i2v 缺 metadata.frame_sources.first；先重跑 h3d compile")
        fp = Path(rel)
        if not fp.is_absolute() and root_dir:
            fp = root_dir / rel
        if not fp.exists():
            raise ValueError(f"首幀來源檔不存在: {fp}")
        body["first_frame"] = str(fp)
    if prev_end_state is not None:
        body["plan"]["start_state"] = _render_state(prev_end_state)
    if seed is not None:
        body["seed"] = int(seed)
    loras = seg.get("h3_loras") or []
    if loras:
        if mode.startswith("pika"):
            warnings.append(f"mode {mode} 不支援額外 LoRA；略過 {len(loras)} 個 h3_loras（Pika LoRA 由伺服器固定掛）")
        else:
            known = provider_caps.load_caps("remix").get("loras", {}).get("fixed_ids") or []
            mapped = [{"id": str(l.get("name")), "strength": float(l.get("strength") or 0.7)}
                      for l in loras if str(l.get("name")) in known]
            dropped = len(loras) - len(mapped)
            if mapped:
                body["loras"] = mapped
            if dropped:
                warnings.append(f"{dropped} 個 h3_loras 不在 REMIX 的 LoRA 清單，略過")
    return body, warnings


def ensure_project(api_url: str, token: str, name: str) -> Tuple[bool, str]:
    status, payload = studio_request(api_url, token, "/projects")
    if status != 200:
        return False, f"GET /projects 失敗（HTTP {status}）"
    for item in payload.get("projects", []) or []:
        if isinstance(item, dict) and item.get("name") == name:
            return True, name
    status, payload = studio_request(api_url, token, "/projects", method="POST", body={"name": name})
    if status not in (200, 201):
        return False, f"POST /projects 失敗（HTTP {status}）：{payload.get('error') or payload}"
    return True, name


def submit_segments(args: argparse.Namespace) -> int:
    root_dir = Path(args.root_dir).resolve() if args.root_dir else Path.cwd()
    segments_path = Path(args.segments)
    if not segments_path.is_file():
        print(f"❌ 找不到 segments 檔：{segments_path}", file=sys.stderr)
        return 2
    try:
        payload = json.loads(segments_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError, UnicodeError) as exc:
        print(f"❌ segments 檔無法解析：{exc}", file=sys.stderr)
        return 2
    segments = payload.get("segments") if isinstance(payload, dict) else payload
    if not isinstance(segments, list):
        print("❌ segments 檔必須是 {\"segments\": [...]} 或陣列", file=sys.stderr)
        return 2

    remix_segs, refused = split_by_backend(segments)
    if refused:
        print(f"❌ 這 {len(refused)} 段不是 REMIX 段（ref2va 六段式或 Base 三字段未宣告 remix），remix 送件端不送："
              f"{'、'.join(refused[:8])}{'…' if len(refused) > 8 else ''}\n"
              f"   ref2va／Base 段請走 h3d submit（FreeVideo 送件端）；Base 段要送 REMIX 先用 --backend remix 重編。", file=sys.stderr)
        return 1
    if not remix_segs:
        print("❌ 檔內沒有任何 REMIX 段（refmods／video_backend=remix）。", file=sys.stderr)
        return 1

    if args.segment_id:
        wanted = {s.strip() for s in args.segment_id.split(",") if s.strip()}
        remix_segs = [s for s in remix_segs if str(s.get("segment_id")) in wanted]
        missing = wanted - {str(s.get("segment_id")) for s in remix_segs}
        if missing:
            print(f"⚠️ 指定的段不在檔內：{'、'.join(sorted(missing))}", file=sys.stderr)

    scope: Dict[str, Any] = {}
    if not verify_stage5_gate(root_dir, segments_path, skip_gate=args.skip_stage_gate,
                              dry_run=args.dry_run, scope=scope):
        return 1
    allowed = scope.get("allowed")
    if allowed:
        before = len(remix_segs)
        remix_segs = [s for s in remix_segs if str(s.get("segment_id")) in allowed]
        print(f"⚠️ [Stage 5 Gate] 段級核准：只送 {len(remix_segs)}/{before} 段（其餘待重審）。")

    mode = args.mode or decisions_mod.DEFAULT_REMIX_MODE
    if mode not in decisions_mod.REMIX_MODES:
        print(f"⚠️ mode {mode!r} 不是 REMIX 認得的模式，回退預設 {decisions_mod.DEFAULT_REMIX_MODE}", file=sys.stderr)
        mode = decisions_mod.DEFAULT_REMIX_MODE
    steps = args.steps
    caps = provider_caps.load_caps("remix")

    ok, errors = precheck_segments(remix_segs, root_dir, caps, mode, steps,
                                   strict_catalog=args.strict_catalog, ack_warnings=args.ack_warnings)
    if errors:
        print("❌ 送件前檢查未過（不送件）：", file=sys.stderr)
        for e in errors[:40]:
            print(f"  - {e}", file=sys.stderr)
        if len(errors) > 40:
            print(f"  …共 {len(errors)} 條", file=sys.stderr)
        return 1

    project = args.project
    if not project:
        print("❌ 缺 --project（REMIX Studio 的專案名稱；POST /jobs 必帶 project）。", file=sys.stderr)
        return 2

    bodies: List[Tuple[Dict[str, Any], List[str], str, str]] = []
    prev_state: Any = None
    for seg in remix_segs:
        # P1-1 第二片：Base i2v 段自動改走 pikaff 模式（first_frame 欄位）；其餘照批次模式。
        seg_mode, seg_mode_warnings = resolve_segment_mode(seg, mode)
        body, warnings = build_job_body(seg, project, seg_mode, args.seed,
                                        prev_end_state=prev_state, root_dir=root_dir)
        bodies.append((body, seg_mode_warnings + warnings, str(seg.get("segment_id")), seg_mode))
        prev_state = (seg.get("segment_end_state") or {}).get("planned_final_state")

    if args.dry_run:
        print(f"🧪 [dry-run] 對 {args.api_url} 送 {len(bodies)} 段（mode={mode}、project={project}）：")
        for body, warnings, sid, seg_mode in bodies:
            extra = f" first_frame={body['first_frame']}" if "first_frame" in body else ""
            print(f"  [{sid}] mode={seg_mode} seconds={body['seconds']:.4f} frames≈{round(body['seconds'] * h3_spec.FPS)} "
                  f"refmods={'、'.join(body['refmods'])} seed={body.get('seed')}{extra}")
            for w in warnings:
                print(f"    ⚠️ {w}")
        print("🧪 dry-run 不送件、不寫帳本。實際送件去掉 --dry-run。")
        return 0

    try:
        token = resolve_token(args)
        ok, message = ensure_project(args.api_url, token, project)
    except RemixTransportError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        args.summary = {"command": "submit", "error": str(exc), "submitted": 0, "failed": len(bodies)}
        return 1
    if not ok:
        print(f"❌ {message}", file=sys.stderr)
        args.summary = {"command": "submit", "error": message, "submitted": 0, "failed": 0}
        return 1

    ledger_path = root_dir / "videos" / LEDGER_NAME
    ledger = load_ledger(ledger_path)
    ledger.setdefault("jobs", [])
    ledger.update({"api_scope": args.api_url, "studio_project": project, "mode": mode,
                   "updated_at": datetime.now(timezone.utc).isoformat()})
    if not ledger.get("project"):
        ledger["project"] = str(root_dir)

    submitted = failed = 0
    for body, warnings, sid, seg_mode in bodies:
        for w in warnings:
            print(f"  ⚠️ [{sid}] {w}")
        existing = ledger_entry(ledger, sid)
        if existing and existing.get("status") in ("waiting", "running", "downloaded") and not args.reroll:
            print(f"  ⏭️ [{sid}] 帳本已有 {existing.get('status')} 的工作（job {existing.get('id')}）；--reroll 重送")
            continue
        if (existing and existing.get("status") in ("failed", "timeout", "unverified", "download_failed")
                and not (args.reroll or args.reroll_failed)):
            print(f"  ⚠️ [{sid}] 帳本記錄是 {existing.get('status')}（job {existing.get('id')}）；"
                  f"--reroll-failed 只重送失敗段、--reroll 全部重送")
            failed += 1
            continue
        try:
            status, resp = studio_request(args.api_url, token, "/jobs", method="POST", body=body)
        except RemixTransportError as exc:
            print(f"  ❌ [{sid}] {exc}", file=sys.stderr)
            failed += 1
            break
        if status not in (200, 201):
            print(f"  ❌ [{sid}] POST /jobs 失敗（HTTP {status}）：{resp.get('error') or resp}", file=sys.stderr)
            failed += 1
            continue
        job = resp.get("job") if isinstance(resp.get("job"), dict) else {}
        job_id = job.get("id")
        if not job_id:
            print(f"  ❌ [{sid}] POST /jobs 回 HTTP {status} 但沒有 job.id，不當成送出", file=sys.stderr)
            failed += 1
            continue
        entry = {"id": job_id, "segment_id": sid, "status": job.get("status") or "queued",
                 "frames_requested": round(body["seconds"] * h3_spec.FPS),
                 "seconds": body["seconds"], "mode": seg_mode,
                 "seed": body.get("seed"), "submitted_at": datetime.now(timezone.utc).isoformat(),
                 "warning": job.get("warning") or ""}
        ledger["jobs"] = [e for e in ledger["jobs"] if e.get("segment_id") != sid] + [entry]
        save_ledger(ledger_path, ledger)
        print(f"  [+] [{sid}] 已送件 job {entry['id']}（{entry['status']}）")
        submitted += 1

    print(f"🎬 REMIX 送件結束: 送出 {submitted} | 失敗 {failed}")
    print(f"   收件：python scripts/storyboard/submit_remix.py --segments {segments_path.name} --collect --root-dir {root_dir}")
    code = 1 if failed else 0
    args.summary = {"command": "submit", "submitted": submitted, "failed": failed, "exit_code": code}
    return code


# ---------------------------------------------------------------------------
# 收件（輪詢 → 下載 → identity）
# ---------------------------------------------------------------------------

def _poll_job(api_url: str, token: str, job_id: str, timeout_s: int) -> Tuple[str, Optional[Dict[str, Any]]]:
    """輪詢到結束、失敗或逾時。

    伺服器若真的長輪詢（把連線留到 wait 秒），回來就立刻再問。
    若馬上回答 queued，必須 sleep，否則會在逾時前空轉打爆本機埠。
    404／401／403 是這筆工作已經不在，不要再空等預設的 25 秒。
    """
    deadline = time.monotonic() + max(0, timeout_s)
    quoted = urllib.parse.quote(str(job_id), safe="")
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return "timeout", None
        wait = max(1, int(min(POLL_WAIT_SECONDS, remaining)))
        started = time.monotonic()
        try:
            status, payload = studio_request(
                api_url, token, f"/jobs/{quoted}?wait={wait}", timeout=wait + 15)
        except RemixTransportError as exc:
            return "failed", {"error": str(exc)}
        elapsed = time.monotonic() - started
        job = (payload or {}).get("job") if isinstance((payload or {}).get("job"), dict) else {}
        state = str(job.get("status") or "")
        if state in ("succeeded", "failed", "cancelled"):
            return state, job
        if status in (401, 403, 404, 410):
            error = payload.get("error") if isinstance(payload, dict) else None
            return "failed", {"error": error or f"HTTP {status}"}
        if elapsed < _LONG_POLL_CREDIT_SECONDS:
            pause = min(POLL_WAIT_SECONDS, max(0.0, deadline - time.monotonic()))
            if pause > 0:
                time.sleep(pause)


def collect_segments(args: argparse.Namespace) -> int:
    root_dir = Path(args.root_dir).resolve() if args.root_dir else Path.cwd()
    ledger_path = root_dir / "videos" / LEDGER_NAME
    ledger = load_ledger(ledger_path)
    jobs = [j for j in ledger.get("jobs", []) if isinstance(j, dict)]
    pending = [j for j in jobs if j.get("status") in ("queued", "waiting", "running")]
    if not pending:
        print("📭 沒有等待收件的工作（remix-jobs.json）。")
        return 0
    token = resolve_token(args)
    output_dir = root_dir / "videos"
    downloaded = failed = 0
    for entry in pending:
        sid, job_id = str(entry.get("segment_id")), str(entry.get("id"))
        state, job = _poll_job(args.api_url, token, job_id, args.wait_timeout)
        if state != "succeeded" or not job:
            entry["status"] = "failed" if state in ("failed", "cancelled") else "timeout"
            entry["error"] = (job or {}).get("error") or state
            save_ledger(ledger_path, ledger)
            print(f"  ❌ [{sid}] job {job_id} {entry['status']}：{entry['error']}")
            failed += 1
            continue
        result = job.get("result") or {}
        video = result.get("video") or {}
        meta = video.get("meta") or {}
        frames_actual = meta.get("frames")
        requested = entry.get("frames_requested")
        if isinstance(frames_actual, int) and isinstance(requested, int) and frames_actual != requested:
            print(f"  ⚠️ [{sid}] 後端實際 {frames_actual} 幀（{meta.get('duration')}s），要求 {requested} 幀；"
                  f"以實際影片為準（已記帳本）")
        dest = output_dir / f"{sid}.mp4"
        try:
            download_file(args.api_url, token, job_id, dest)
        except (urllib.error.URLError, OSError) as exc:
            entry["status"], entry["error"] = "download_failed", str(exc)
            save_ledger(ledger_path, ledger)
            print(f"  ❌ [{sid}] 下載失敗：{exc}")
            failed += 1
            continue
        duration = probe_video_duration(dest)
        if duration is None:
            quarantine = dest.with_name(dest.name + ".unverified.mp4")
            dest.replace(quarantine)
            entry["status"], entry["error"] = "unverified", "下載檔無法 ffprobe，已隔離"
            save_ledger(ledger_path, ledger)
            print(f"  ❌ [{sid}] 下載檔無法驗證，隔離成 {quarantine.name}")
            failed += 1
            continue
        entry.update({"status": "downloaded", "file": str(dest), "frames_actual": frames_actual,
                      "duration_actual": round(float(duration), 3),
                      "downloaded_at": datetime.now(timezone.utc).isoformat()})
        # identity（R10 前哨）：fail 先重抽、warn 逐格人工、no_face 不算過
        try:
            istatus, ipayload = studio_request(
                args.api_url, token,
                "/jobs/" + urllib.parse.quote(str(job_id), safe="") + "/identity", timeout=60)
            identity = (ipayload or {}).get("identity") or ipayload or {}
            entry["identity"] = identity.get("status") or identity.get("state") or str(identity)[:120]
        except (RemixTransportError, urllib.error.URLError, OSError):
            entry["identity"] = "unavailable"
        save_ledger(ledger_path, ledger)
        print(f"  [+] [{sid}] 已下載 {dest.name}（實際 {frames_actual} 幀／{entry['duration_actual']}s，"
              f"identity={entry['identity']}）")
        downloaded += 1
    print(f"📥 REMIX 收件結束: 下載 {downloaded} | 失敗 {failed}")
    args.summary = {"command": "collect", "downloaded": downloaded, "failed": failed}
    if args.report:
        report_path = root_dir / "videos" / "remix-qa.json"
        rows = []
        for entry in ledger.get("jobs", []):
            if not isinstance(entry, dict):
                continue
            requested = entry.get("frames_requested")
            actual = entry.get("frames_actual")
            rows.append({
                "segment_id": entry.get("segment_id"), "job_id": entry.get("id"),
                "status": entry.get("status"), "mode": entry.get("mode"),
                "frames_requested": requested, "frames_actual": actual,
                "frames_drift": (actual - requested) if isinstance(actual, int) and isinstance(requested, int) else None,
                "duration_actual": entry.get("duration_actual"),
                "identity": entry.get("identity"), "file": entry.get("file"),
                "error": entry.get("error"),
            })
        report_path.write_text(json.dumps({"generated_at": datetime.now(timezone.utc).isoformat(),
                                           "studio_project": ledger.get("studio_project"),
                                           "segments": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"📋 QA 報告已寫 {report_path}（verdict 證據：frames_drift／identity／file）")
    return 0 if not failed else 1


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _decided_remix_mode(root_dir: Path) -> Optional[str]:
    """讀 decisions.json 的 remix_mode（沒定案回 None；CLI --mode 優先）。"""
    path = root_dir / "decisions.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return None
    for item in (data.get("decisions") or []):
        if isinstance(item, dict) and item.get("id") == "remix_mode":
            value = str(item.get("value") or "").strip()
            return value if value in decisions_mod.REMIX_MODES else None
    return None


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="REMIX Studio 送件 adapter（PR-R7）：只送 video_backend=remix 的段")
    parser.add_argument("--segments", required=True, help="compile 產出的 segments-epXX.json")
    parser.add_argument("--root-dir", default=None, help="專案根目錄（stage-5 門禁與 videos/ 帳本位置）")
    parser.add_argument("--project", default=None, help="REMIX Studio 專案名稱（POST /jobs 必帶）")
    parser.add_argument("--mode", default=None,
                        help=f"送件模式（預設讀 decisions 的 remix_mode，再預設 {decisions_mod.DEFAULT_REMIX_MODE}）")
    parser.add_argument("--steps", type=int, default=None, help="pika_steps（4／6，只限 pika 模式）")
    parser.add_argument("--seed", type=int, default=None, help="固定 seed（抽卡對照用）")
    parser.add_argument("--segment-id", default=None, help="只送指定段（逗號分隔）")
    parser.add_argument("--reroll", action="store_true", help="帳本已有工作也重送（覆蓋舊紀錄）")
    parser.add_argument("--reroll-failed", action="store_true",
                        help="只重送帳本裡 failed／timeout／unverified 的段（抽卡失敗自動重抽用）")
    parser.add_argument("--collect", action="store_true", help="只收件：輪詢帳本中等待的工作、下載、identity")
    parser.add_argument("--report", action="store_true",
                        help="收件後寫 videos/remix-qa.json（每段 frames_drift／identity／file，verdict 證據）")
    parser.add_argument("--wait-timeout", type=int, default=DEFAULT_JOB_TIMEOUT, help="單工作輪詢上限秒數")
    parser.add_argument("--api-url", default=DEFAULT_API_URL, help="REMIX Agent API 位址")
    parser.add_argument("--token-file", default=None, help="令牌檔路徑（內容不會被印出）")
    parser.add_argument("--json", action="store_true",
                        help="stdout 只印一行 JSON（ok／exit_code／submitted 等）；人讀訊息改走 stderr")
    parser.add_argument("--dry-run", action="store_true", help="只跑門禁與檢查、印出將送內容，不送件")
    parser.add_argument("--skip-stage-gate", action="store_true", help="僅 --dry-run 可用：跳過 stage-5 門禁並留繞過紀錄")
    parser.add_argument("--strict-catalog", action="store_true", help="失敗目錄警告也擋")
    parser.add_argument("--ack-warnings", nargs="*", default=None, help="本次接受哪些失敗目錄警告 id（正式憑證請用 h3d ack）")
    args = parser.parse_args(argv)

    if args.skip_stage_gate and not args.dry_run:
        print("❌ --skip-stage-gate 僅允許 --dry-run；實際送件必須有 stage-5 核准。", file=sys.stderr)
        return 2
    root_dir = Path(args.root_dir).resolve() if args.root_dir else Path.cwd()
    if not args.mode:
        args.mode = _decided_remix_mode(root_dir) or decisions_mod.DEFAULT_REMIX_MODE

    if args.collect:
        return _finish(args, collect_segments)
    return _finish(args, submit_segments)


def _finish(args: argparse.Namespace, fn) -> int:
    """`--json` 時人讀訊息走 stderr，stdout 只留一個物件，結束碼仍是 fn 的回傳。"""
    if not getattr(args, "json", False):
        return fn(args)
    real_out = sys.stdout
    sys.stdout = sys.stderr
    code = 1
    try:
        try:
            code = fn(args)
        except SystemExit as exc:
            if isinstance(exc.code, int):
                code = exc.code
            else:
                if exc.code:
                    print(exc.code, file=sys.stderr)
                code = 1
    finally:
        sys.stdout = real_out
    summary = dict(getattr(args, "summary", {}) or {})
    summary["exit_code"] = code
    summary["ok"] = code == 0
    real_out.write(json.dumps(summary, ensure_ascii=False) + "\n")
    real_out.flush()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
