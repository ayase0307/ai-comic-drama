#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
imagegen_remix.py — REMIX Studio 美術室生圖 adapter（P1-12，11-03 #8）

把 REMIX Studio 的美術室（`POST /images`，Qwen-Image 6 步加速／MOSS MJ3.0 風格）
接成 ai-comic-drama 的生圖後端：送件 → 輪詢 → 把成品落到 assets.md 登記的路徑。

`h3d imagegen --detect` 會偵測這個後端（REMIX_API_URL 或預設 127.0.0.1:8190）；
使用者 `h3d imagegen --set remix --quote "<原話>"` 之後，階段 2 設定圖照
`command_for("remix", 2)` 的指令逐張生成。

【安全鐵律】嚴禁在任何輸出印出 REMIX 令牌！

CLI 用法：
  python scripts/imagegen_remix.py --prompt "<提示詞>" --purpose character --out images/assets/C-x.png
      [--count 1] [--engine qwen|moss] [--style ST-01-QIUYAN] [--aspect "16:9 (Widescreen)"]
      [--mp 2.0] [--ref-image <路徑>] [--seed N] [--project <studio專案>]
      [--api-url ...] [--token-file ...] [--wait-timeout 900]
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

try:
    from submit_remix import resolve_token, studio_request
except ImportError:  # pragma: no cover - 套件匯入路徑
    from .submit_remix import resolve_token, studio_request  # type: ignore

DEFAULT_API_URL = os.environ.get("REMIX_API_URL", "").strip() or "http://127.0.0.1:8190/remix/agent/v1"
POLL_WAIT_SECONDS = 10
PURPOSES = ("character", "scene", "grid9")
ENGINES = ("qwen", "moss")


def build_body(args: argparse.Namespace) -> Dict[str, Any]:
    body: Dict[str, Any] = {"purpose": args.purpose, "prompt": args.prompt, "count": args.count}
    if args.engine:
        body["engine"] = args.engine
    if args.size:
        body["size"] = args.size
    if args.seed is not None:
        body["seed"] = int(args.seed)
    if args.ref_image:
        body["ref_image"] = str(args.ref_image)
    if args.style:
        body["style"] = args.style
    if args.aspect:
        body["aspect"] = args.aspect
    if args.mp is not None:
        body["mp"] = float(args.mp)
    if args.project:
        body["project"] = args.project
    return body


def _result_images(job: Dict[str, Any]) -> List[str]:
    """從工作結果盡量取出圖片路徑／URL（伺服器形狀演進時不硬爆）。"""
    result = job.get("result") or {}
    candidates: List[str] = []
    for key in ("images", "image", "files"):
        value = result.get(key)
        if isinstance(value, list):
            candidates.extend(str(item.get("path") or item.get("url") or item) if isinstance(item, dict) else str(item)
                              for item in value)
        elif isinstance(value, dict):
            candidates.append(str(value.get("path") or value.get("url") or ""))
        elif isinstance(value, str):
            candidates.append(value)
    for key in ("path", "url", "file"):
        if result.get(key):
            candidates.append(str(result[key]))
    return [c for c in candidates if c]


def _fetch_image(api_url: str, token: str, job_id: str, ref: str, dest: Path) -> bool:
    """ref 是本機路徑就直接複製；是 URL 就走 API 下載。回是否成功。"""
    source = Path(ref)
    if source.is_file():
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest)
        return True
    url = ref if ref.startswith("http") else api_url.rstrip("/") + (ref if ref.startswith("/") else f"/jobs/{job_id}/file")
    try:
        from submit_h3_segments import SameOriginRedirectHandler  # noqa: E402
        import urllib.request

        request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}",
                                                       "X-Remix-Client": "ai-comic-drama"})
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
        return True
    except Exception:
        return False


def generate(args: argparse.Namespace) -> int:
    token = resolve_token(args)
    body = build_body(args)
    status, resp = studio_request(args.api_url, token, "/images", method="POST", body=body)
    if status not in (200, 201):
        detail = resp.get("error") or resp
        print(f"❌ POST /images 失敗（HTTP {status}）：{detail}", file=sys.stderr)
        return 1
    job = resp.get("job") or resp
    job_id = str(job.get("id") or "")
    if not job_id:
        print(f"❌ 回應沒有 job id：{resp}", file=sys.stderr)
        return 1
    print(f"🖼️ 已送件 job {job_id}（purpose={args.purpose} count={args.count}）")
    deadline = time.monotonic() + args.wait_timeout
    while time.monotonic() < deadline:
        state, payload = studio_request(args.api_url, token, f"/jobs/{job_id}?wait=10", timeout=25)
        job = (payload or {}).get("job") or {}
        state = str(job.get("status") or state)
        if state == "succeeded":
            refs = _result_images(job)
            if not refs:
                print(f"❌ 工作完成但結果沒有圖片路徑：{job.get('result')}", file=sys.stderr)
                return 1
            out_path = Path(args.out)
            written: List[str] = []
            for i, ref in enumerate(refs[: max(1, args.count)]):
                dest = out_path if i == 0 else out_path.with_name(f"{out_path.stem}-{i + 1}{out_path.suffix}")
                if _fetch_image(args.api_url, token, job_id, ref, dest):
                    written.append(str(dest))
                else:
                    print(f"  ⚠️ 第 {i + 1} 張落檔失敗（來源 {ref}）", file=sys.stderr)
            if not written:
                return 1
            print(f"✅ 已落檔：{'、'.join(written)}")
            print(f"   job {job_id}｜生成後請親眼驗收臉和服裝（階段 2 永遠要人看）。")
            return 0
        if state in ("failed", "cancelled"):
            print(f"❌ job {job_id} {state}：{job.get('error')}", file=sys.stderr)
            return 1
    print(f"❌ 等待 job {job_id} 逾時（{args.wait_timeout}s）；工作可能還在跑，稍後重跑本指令會重新送件。", file=sys.stderr)
    return 1


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="REMIX Studio 美術室生圖 adapter（P1-12）")
    parser.add_argument("--prompt", required=True, help="生圖提示詞（≤6000 字）")
    parser.add_argument("--purpose", required=True, choices=PURPOSES, help="character（2:3）／scene（16:9）／grid9（1:1、16:9）")
    parser.add_argument("--out", required=True, help="落檔路徑（assets.md 登記的路徑；多張自動 -2、-3…）")
    parser.add_argument("--count", type=int, default=1, help="張數 1–4")
    parser.add_argument("--engine", default=None, choices=ENGINES, help="qwen（預設，伺服器端）／moss（要 --style）")
    parser.add_argument("--style", default=None, help="moss 風格資料夾名（ST-01-QIUYAN；清單 GET /images/styles）")
    parser.add_argument("--aspect", default=None, help="moss 用 ResolutionSelector 選項，例 '16:9 (Widescreen)'")
    parser.add_argument("--mp", type=float, default=None, help="moss 目標百萬像素 0.5–2.0")
    parser.add_argument("--size", default=None, help="qwen 用尺寸（2:3／16:9／1:1）")
    parser.add_argument("--ref-image", default=None, help="參考圖本機路徑（edit，僅 qwen）")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--project", default=None, help="REMIX Studio 專案名稱（建議帶，圖才歸檔）")
    parser.add_argument("--api-url", default=DEFAULT_API_URL)
    parser.add_argument("--token-file", default=None, help="令牌檔路徑（內容不會被印出）")
    parser.add_argument("--wait-timeout", type=int, default=900)
    args = parser.parse_args(argv)
    if args.engine == "moss" and not args.style:
        print("❌ engine=moss 需要 --style（GET /images/styles 列清單）", file=sys.stderr)
        return 2
    if args.ref_image and args.engine == "moss":
        print("❌ moss 不支援 ref_image 編輯；改用 engine=qwen", file=sys.stderr)
        return 2
    return generate(args)


if __name__ == "__main__":
    raise SystemExit(main())
