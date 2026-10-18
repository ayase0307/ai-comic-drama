#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
submit_h3_segments.py — MiniMax H3 批次分段影片送件與進度管理工具 (FreeVideo Agent API)

用途：
讀取 compile_layer2_to_h3.py 輸出的 segments-epXX.json，安全對接本機 FreeVideo (/freevideo/agent/v1)，
支援事前乾跑檢查 (--dry-run)、4.20 GiB 顯存臨界點保護與診斷、參考圖 SHA256 增量上傳快取、
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
import time
from typing import Any, Dict, List, Optional, Tuple
import urllib.request

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

try:
    from audit_refs_and_segments import audit_refs_and_subjects, lint_h3_prompt
except ImportError:
    audit_refs_and_subjects = None
    lint_h3_prompt = None


DEFAULT_API_URL = "http://127.0.0.1:8189/freevideo/agent/v1"
SAFE_VRAM_MB = 4300  # 4.20 GiB MiniMax H3 臨界啟動安全顯存


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
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def download_file(token: str, base_url: str, rel_or_abs_url: str, out_path: Path, timeout: int = 900) -> None:
    """從 FreeVideo 下載產生的影片檔案。"""
    if rel_or_abs_url.startswith("http://") or rel_or_abs_url.startswith("https://"):
        full_url = rel_or_abs_url
    else:
        full_url = base_url.rstrip("/") + "/" + rel_or_abs_url.lstrip("/")
    
    req = urllib.request.Request(
        full_url,
        headers={"Authorization": "Bearer " + token}
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req, timeout=timeout) as r:
        out_path.write_bytes(r.read())


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
    if sha in cache:
        return cache[sha]
    
    b64 = base64.b64encode(data_bytes).decode("ascii")
    payload = {
        "name": img_path.name,
        "data_base64": b64
    }
    resp = call_api(api_url, token, "POST", "/media", payload)
    remote_file_id = resp.get("file", "")
    if not remote_file_id:
        raise RuntimeError(f"上傳參考圖 {img_path.name} 失敗，API 未回傳 file id")
    
    cache[sha] = remote_file_id
    save_media_cache(cache_file, cache)
    print(f"   [+] 成功上傳新參考圖: {img_path.name} -> {remote_file_id}")
    return remote_file_id


def cancel_stale_jobs(api_url: str, token: str) -> None:
    """取消所有伺服器上殘留的 seg- 孤兒任務。"""
    try:
        resp = call_api(api_url, token, "GET", "/jobs")
        jobs = resp.get("jobs", [])
    except Exception as e:
        print(f"❌ 查詢任務失敗: {e}")
        return

    targets = [
        j for j in jobs
        if j.get("status") in ("running", "waiting")
        and str((j.get("spec") or {}).get("ref", "")).startswith("seg-")
    ]
    if not targets:
        print("✅ 目前沒有殘留的 seg- 孤兒任務。")
        return

    print(f"⚠️ 發現 {len(targets)} 個未完成的 seg- 任務，開始自動清理...")
    for j in targets:
        jid = j.get("id")
        try:
            call_api(api_url, token, "POST", f"/jobs/{jid}/cancel", {})
            print(f"  - 已取消任務: {jid} ({j.get('status')}) {j.get('label')}")
        except Exception as e:
            print(f"  - 取消任務 {jid} 失敗: {e}")
    print("✅ 孤兒任務清理完畢。")


def verify_stage4_gate(root_dir: Path, skip_gate: bool = False) -> bool:
    """階段 4 九宮格門禁：嚴防未審核九宮格分鏡即送件生成影片。"""
    if skip_gate:
        print("⚠️ [警告] 已顯式指定 --skip-stage-gate，跳過階段 4 九宮格分鏡門禁。")
        return True

    # 1. 檢查 images/grid-*.png 或 panels/panel-*.png
    has_grids = bool(list((root_dir / "images").glob("grid-*.png"))) or bool(list(root_dir.glob("grid-*.png")))
    has_panels = bool(list((root_dir / "panels").glob("panel-*.png"))) or bool(list(root_dir.glob("panel-*.png")))

    # 2. 檢查 review/stage-4-storyboard.html 或 project-state.json
    has_review_html = (root_dir / "review" / "stage-4-storyboard.html").exists()
    state_file = root_dir / "review" / "project-state.json"
    state_approved = False
    if state_file.exists():
        try:
            with state_file.open("r", encoding="utf-8") as f:
                st = json.load(f)
            s4_info = st.get("stages", {}).get("stage-4", {})
            if s4_info.get("status") in ("approved", "completed"):
                state_approved = True
        except Exception:
            pass

    if not (has_grids or has_panels or state_approved or has_review_html):
        print("\n" + "=" * 78, file=sys.stderr)
        print("❌ [Fatal Gate Error - 階段 4 九宮格分鏡門禁阻斷]", file=sys.stderr)
        print("=" * 78, file=sys.stderr)
        print("偵測到專案尚未完成「階段 4 鉛筆手繪九宮格分鏡構圖確認」！", file=sys.stderr)
        print("嚴禁在未生成九宮格構圖審核圖（images/grid-*.png 或 panels/panel-*.png）的情況下偷懶直接呼叫 FreeVideo 生成影片！", file=sys.stderr)
        print("\n處置要求：", file=sys.stderr)
        print("  1. 請先執行 python scripts/storyboard/qwen_storyboard_grid.py 產出九宮格草圖。", file=sys.stderr)
        print("  2. 執行 python scripts/build_stage_review.py 產出 review/stage-4-storyboard.html 並取得核准。", file=sys.stderr)
        print("  3. 若在單元測試或特殊除錯環境需繞過，請顯式傳入 --skip-stage-gate。\n", file=sys.stderr)
        print("=" * 78 + "\n", file=sys.stderr)
        return False
    return True


def audit_segment_prompts(todo_segs: List[Dict[str, Any]]) -> Tuple[bool, List[str]]:
    """送件前執行 audit_refs_and_segments 17 條確定性審查，杜絕劣質與錯誤 Prompt 浪費顯存。"""
    if audit_refs_and_subjects is None or lint_h3_prompt is None:
        return True, []

    errors: List[str] = []
    for idx, seg in enumerate(todo_segs, 1):
        sid = seg.get("segment_id") or seg.get("group") or seg.get("id") or f"seg_{idx}"
        prompt = seg.get("h3_prompt") or seg.get("prompt", "")
        if not prompt:
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


def main() -> int:
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
    parser.add_argument("--skip-stage-gate", action="store_true", help="強制跳過階段 4 九宮格分鏡門禁檢查（僅限測試或除錯）")

    args = parser.parse_args()

    # 1. 檢查 FreeVideo 令牌
    token = find_token()

    if args.cancel_stale:
        if not token:
            sys.exit("❌ 錯誤: 未找到 FreeVideo 令牌，無法執行 --cancel-stale。")
        cancel_stale_jobs(args.api_url, token)
        return 0

    if not args.segments:
        parser.error("請提供 --segments 參數指定分段 JSON 檔案，或使用 --cancel-stale。")

    if not args.segments.exists():
        sys.exit(f"❌ 錯誤: 分段檔不存在: {args.segments}")

    # 執行階段 4 九宮格硬性門禁檢查
    if not verify_stage4_gate(args.root_dir, skip_gate=args.skip_stage_gate):
        return 1

    # 讀取分段列表
    with args.segments.open("r", encoding="utf-8") as f:
        data = json.load(f)

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

    # 2. 顯存檢測與安全臨界點診斷
    vram_info = get_gpu_vram()
    if vram_info:
        free_mb, total_mb = vram_info
        free_gib = free_mb / 1024.0
        print(f"GPU 顯存: 剩餘 {free_mb} MB ({free_gib:.2f} GiB) / 總量 {total_mb} MB")
        if free_mb < SAFE_VRAM_MB:
            diff_mb = SAFE_VRAM_MB - free_mb
            print(f"⚠️ 【顯存安全臨界警告】剩餘顯存低於 MiniMax H3 安全臨界點 4.20 GiB (4300 MB)！")
            print(f"   不足差額: {diff_mb} MB。建議關閉占用顯存之程式，否則可能引發 FreeVideo 422 崩潰。")
        else:
            print(f"✅ 顯存安全: 充足 (高於 4.20 GiB 臨界點)")
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
            print("✅ 所有分段之秒數設定與本地參考圖全部核驗存在！具備實機送件資格。")
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

    server_base = "http://127.0.0.1:8189"

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
            print(f"  [+] 成功建立任務: {jid} | 標籤: {job.get('label')}")
        except Exception as e:
            print(f"  ❌ 建立任務失敗: {e}")
            stats["failed"] += 1
            continue

        # 輪詢進度
        t0 = time.time()
        while job.get("status") not in ("succeeded", "failed", "cancelled", "interrupted"):
            time.sleep(3)
            try:
                poll_resp = call_api(args.api_url, token, "GET", f"/jobs/{jid}?wait=25")
                job = poll_resp.get("job", {})
            except Exception as e:
                print(f"  [?] 輪詢例外: {e}")
                continue

        status = job.get("status")
        elapsed_min = (time.time() - t0) / 60.0

        if status == "succeeded":
            video_url = (job.get("result") or {}).get("video", {}).get("url")
            if video_url:
                try:
                    download_file(token, server_base, video_url, out_mp4)
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

    print("\n" + "=" * 70)
    print(f"🎉 批次送件結束: 成功: {stats['succeeded']} | 失敗: {stats['failed']} | 跳過: {stats['skipped']}")
    print("=" * 70)
    return 0 if stats["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
