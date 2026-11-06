#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
remix_pack.py — REMIX 角色包對帳（PR-R8）

`h3d pack check`：把專案的包計畫表（`assets/character-packs.json`）對上家機 REMIX Studio
的 `GET /packs`，回報每個計畫包「存在／缺失／kind 不一致」，缺包 exit 1——
bind 與送件前先跑這個，不要等到 POST /jobs 才發現包不存在。

建包本身仍在家機 REMIX Studio 做（`POST /packs` 會生成八視角＋萃取 RefMod，約 380 s）；
本模組只做「回讀確認」，不代建。

【安全鐵律】嚴禁在任何輸出印出 REMIX 令牌！
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Tuple
import urllib.request
import urllib.error

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

try:
    from submit_h3_segments import SameOriginRedirectHandler
    from submit_remix import resolve_token, studio_request
except ImportError:  # pragma: no cover - 套件匯入路徑
    from .submit_h3_segments import SameOriginRedirectHandler  # type: ignore
    from .submit_remix import resolve_token, studio_request  # type: ignore

DEFAULT_API_URL = os.environ.get("REMIX_API_URL", "").strip() or "http://127.0.0.1:8190/remix/agent/v1"
PLAN_PATH = "assets/character-packs.json"


# ---------------------------------------------------------------------------
# 計畫表解析
# ---------------------------------------------------------------------------

def load_plan(root_dir: Path) -> Tuple[Dict[str, Any], Optional[str]]:
    """回（計畫表, 錯誤訊息）。"""
    path = root_dir / PLAN_PATH
    if not path.is_file():
        return {}, f"找不到包計畫表 {path}（h3d bind --backend remix 會產出）"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {}, f"{PLAN_PATH} 無法解析：{exc}"
    if not isinstance(data.get("packs"), dict):
        return {}, f"{PLAN_PATH} 缺 packs 物件"
    return data, None


def planned_packs(plan: Dict[str, Any]) -> List[Dict[str, str]]:
    """計畫表 → [{asset_id, pack, kind, tag}]；字串值依 kind 推定 tag。"""
    out: List[Dict[str, str]] = []
    for asset_id, entry in (plan.get("packs") or {}).items():
        if isinstance(entry, str):
            out.append({"asset_id": str(asset_id), "pack": entry, "kind": "", "tag": ""})
            continue
        if not isinstance(entry, dict):
            continue
        pack = str(entry.get("default") or "").strip()
        if pack:
            out.append({"asset_id": str(asset_id), "pack": pack,
                        "kind": str(entry.get("kind") or ""), "tag": str(entry.get("tag") or "")})
        for costume in (entry.get("costumes") or {}).values():
            if isinstance(costume, dict) and costume.get("pack"):
                out.append({"asset_id": f"{asset_id}:{costume.get('id') or costume.get('pack')}",
                            "pack": str(costume["pack"]),
                            "kind": str(entry.get("kind") or ""), "tag": str(costume.get("tag") or entry.get("tag") or "")})
    return out


# ---------------------------------------------------------------------------
# 對帳
# ---------------------------------------------------------------------------

def fetch_studio_packs(api_url: str, token: str, project: str) -> Tuple[Dict[str, Dict[str, Any]], Optional[str]]:
    """回（{pack_name: {kind, tag, project}}, 錯誤）。先解析專案 id，再過濾。"""
    status, payload = studio_request(api_url, token, "/projects")
    if status != 200:
        return {}, f"GET /projects 失敗（HTTP {status}）"
    project_id = None
    for item in payload.get("projects", []) or []:
        if isinstance(item, dict) and item.get("name") == project:
            project_id = item.get("id")
            break
    if project_id is None:
        return {}, f"REMIX Studio 沒有專案 {project!r}（POST /projects 建立或改 --project）"
    status, payload = studio_request(api_url, token, "/packs")
    if status != 200:
        return {}, f"GET /packs 失敗（HTTP {status}）"
    packs: Dict[str, Dict[str, Any]] = {}
    for item in payload.get("packs", []) or []:
        if isinstance(item, dict) and item.get("project") == project_id and item.get("name"):
            packs[str(item["name"])] = {"kind": str(item.get("kind") or ""),
                                        "tag": str(item.get("tag") or ""),
                                        "variant_of": item.get("variant_of")}
    return packs, None


def check_plan(plan: Dict[str, Any], studio_packs: Dict[str, Dict[str, Any]]) -> Dict[str, List[Dict[str, str]]]:
    """對帳：回 {ok: [...], missing: [...], mismatch: [...]}，每項 {asset_id, pack, detail}。"""
    result: Dict[str, List[Dict[str, str]]] = {"ok": [], "missing": [], "mismatch": []}
    seen: set = set()
    for item in planned_packs(plan):
        pack = item["pack"]
        if pack in seen:
            continue
        seen.add(pack)
        studio = studio_packs.get(pack)
        if studio is None:
            result["missing"].append({**item, "detail": "REMIX Studio 沒有這個包（先在家機建包）"})
            continue
        problems = []
        if item["kind"] and studio["kind"] and item["kind"] != studio["kind"]:
            problems.append(f"kind：計畫表 {item['kind']} vs 家機 {studio['kind']}")
        if item["tag"] and studio["tag"] and item["tag"] != studio["tag"]:
            problems.append(f"tag：計畫表 {item['tag']} vs 家機 {studio['tag']}")
        if problems:
            result["mismatch"].append({**item, "detail": "；".join(problems)})
        else:
            result["ok"].append({**item, "detail": f"kind={studio['kind'] or '?'} tag={studio['tag'] or '?'}"})
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="REMIX 角色包對帳（PR-R8）：計畫表 ↔ 家機 /packs")
    parser.add_argument("--root-dir", default=None, help="專案根目錄（讀 assets/character-packs.json）")
    parser.add_argument("--project", required=True, help="REMIX Studio 專案名稱")
    parser.add_argument("--api-url", default=DEFAULT_API_URL, help="REMIX Agent API 位址")
    parser.add_argument("--token-file", default=None, help="令牌檔路徑（內容不會被印出）")
    parser.add_argument("--json", action="store_true", help="機器可讀輸出")
    args = parser.parse_args(argv)

    root_dir = Path(args.root_dir).resolve() if args.root_dir else Path.cwd()
    plan, plan_error = load_plan(root_dir)
    if plan_error:
        print(f"❌ {plan_error}", file=sys.stderr)
        return 2

    token = resolve_token(args)
    studio_packs, fetch_error = fetch_studio_packs(args.api_url, token, args.project)
    if fetch_error:
        print(f"❌ {fetch_error}", file=sys.stderr)
        return 1

    result = check_plan(plan, studio_packs)
    if args.json:
        print(json.dumps({"project": args.project, **{k: v for k, v in result.items()}},
                         ensure_ascii=False, indent=2))
    else:
        print(f"📦 REMIX 包對帳（專案 {args.project}）："
              f"✅ {len(result['ok'])}｜❌ 缺 {len(result['missing'])}｜⚠️ 不一致 {len(result['mismatch'])}")
        for item in result["ok"]:
            print(f"  ✅ {item['pack']}（{item['asset_id']}）{item['detail']}")
        for item in result["missing"]:
            print(f"  ❌ {item['pack']}（{item['asset_id']}）{item['detail']}")
        for item in result["mismatch"]:
            print(f"  ⚠️ {item['pack']}（{item['asset_id']}）{item['detail']}")
        unreferenced = sorted(set(studio_packs) - {i["pack"] for i in planned_packs(plan)})
        if unreferenced:
            preview = "、".join(unreferenced[:10]) + ("…" if len(unreferenced) > 10 else "")
            print(f"  ℹ️ 專案裡還有 {len(unreferenced)} 個計畫表沒引用的包：{preview}")
    if result["missing"] or result["mismatch"]:
        print("❌ 缺包或不一致：先在家機 REMIX Studio 建包／修正，再重跑 h3d pack check；"
              "bind 與送件會被缺包擋下。", file=sys.stderr)
        return 1
    print("✅ 計畫表所有包都在家機專案裡。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
