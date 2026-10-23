#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""送件前 probe：查 FreeVideo API schema 與家機已安裝的 LoRA，缺的直接擋並列出替代。

為什麼：《我修的是遺忘課》EP04-S02-a 兩次 submit_error——
  1. 07:15 loras 項多帶 trigger／reason，被 API（additionalProperties=false）擋；
  2. 10:27 `H3_Combat_V2`、`Motion_Repair` 根本沒裝在家機。
兩次都是送出去才知道。這支在送件前就查：

  * GET <api>（agent 根）→ `loras`：已安裝 LoRA 名稱清單。
  * GET <api>/openapi.json → JobSpec 的屬性與 loras 項允許的欄位（拿不到就略過 schema 檢查）。
  * 每段 h3_loras：名稱不在已安裝清單 → error，附相近名稱與「拿掉 LoRA」選項；
    帶了 name／strength 以外的欄位 → warning（送件端會自動剝掉）。

用法：h3d probe --segments segments-ep01.json [...] [--api URL] [--json]
離線測試：--installed a,b,c 與 --schema openapi.json 可不連 API。
"""
from __future__ import annotations

import argparse
import difflib
import json
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
for candidate in (str(SCRIPTS_DIR), str(SCRIPTS_DIR / "storyboard")):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)


def _segments(path: Path) -> List[Dict[str, Any]]:
    raw = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    items = raw if isinstance(raw, list) else raw.get("segments", [raw])
    return [i for i in items if isinstance(i, dict) and i.get("segment_id")]


def _lora_names(value: Any) -> List[str]:
    """agent 根回應裡的 loras 可能是字串陣列或物件陣列。"""
    names: List[str] = []
    for item in value or []:
        if isinstance(item, str):
            names.append(item)
        elif isinstance(item, dict):
            name = item.get("name") or item.get("id") or item.get("file")
            if name:
                names.append(str(name))
    return names


def installed_loras(root_info: Dict[str, Any]) -> Optional[List[str]]:
    for key in ("loras", "installed_loras"):
        if key in root_info:
            return _lora_names(root_info[key])
    caps = root_info.get("capabilities") or {}
    if isinstance(caps, dict) and "loras" in caps:
        return _lora_names(caps["loras"])
    return None


def jobspec_from_openapi(doc: Dict[str, Any]) -> Dict[str, Any]:
    """回傳 {"properties": set|None, "lora_fields": set|None}。"""
    schemas = ((doc or {}).get("components") or {}).get("schemas") or {}
    spec = schemas.get("JobSpec") or {}
    props = spec.get("properties") or {}
    lora_fields = None
    loras = props.get("loras") or {}
    items = loras.get("items") or {}
    if isinstance(items, dict):
        variants = items.get("oneOf") or items.get("anyOf") or [items]
        for variant in variants:
            if isinstance(variant, dict) and variant.get("type") == "object" and variant.get("properties"):
                lora_fields = set(variant["properties"])
    return {"properties": set(props) or None, "lora_fields": lora_fields}


def check(segments: List[Dict[str, Any]], installed: Optional[List[str]],
          schema: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    errors: List[Dict[str, Any]] = []
    warnings: List[str] = []
    allowed_fields = (schema or {}).get("lora_fields") or {"name", "strength"}
    installed_set = set(installed or [])
    used: Dict[str, List[str]] = {}
    for seg in segments:
        sid = str(seg["segment_id"])
        for item in seg.get("h3_loras") or []:
            name = item if isinstance(item, str) else (item or {}).get("name")
            if not name:
                warnings.append(f"{sid}: h3_loras 有一項沒有 name")
                continue
            used.setdefault(name, []).append(sid)
            if isinstance(item, dict):
                extra = sorted(set(item) - set(allowed_fields))
                if extra:
                    warnings.append(f"{sid}: LoRA {name} 帶了 API 不收的欄位 {', '.join(extra)}（送件時會自動剝掉）")
            if installed is not None and name not in installed_set:
                close = difflib.get_close_matches(name, sorted(installed_set), n=3, cutoff=0.3)
                errors.append({
                    "segment_id": sid, "lora": name,
                    "message": f"{sid}: LoRA「{name}」沒有安裝在這台機器",
                    "alternatives": ["拿掉這個 LoRA（h3_loras 留空）"] + [f"改用已安裝的 {c}" for c in close],
                })
    if installed is None and used:
        warnings.append("拿不到已安裝 LoRA 清單（API 根沒有 loras 欄位），無法確認 LoRA 是否存在")
    return {"ok": not errors, "errors": errors, "warnings": warnings, "installed": installed,
            "used": used, "schema_checked": bool(schema and schema.get("properties"))}


def fetch(api_url: str, token: str, call: Optional[Callable[..., Dict[str, Any]]] = None) -> Dict[str, Any]:
    """連 API 取根資訊與 openapi；回傳 {"installed": [...]|None, "schema": {...}|None, "errors": [...]}。"""
    import submit_h3_segments as S
    call = call or S.call_api
    out: Dict[str, Any] = {"installed": None, "schema": None, "errors": []}
    try:
        info = call(api_url, token, "GET", "", timeout=60)
        out["installed"] = installed_loras(info if isinstance(info, dict) else {})
    except Exception as exc:  # pragma: no cover - 依連線狀態
        out["errors"].append(f"讀取 API 根失敗：{exc}")
    try:
        doc = call(api_url, token, "GET", "/openapi.json", timeout=60)
        out["schema"] = jobspec_from_openapi(doc if isinstance(doc, dict) else {})
    except Exception as exc:  # pragma: no cover
        out["errors"].append(f"讀取 openapi.json 失敗：{exc}")
    return out


def render(report: Dict[str, Any]) -> str:
    lines = []
    if report.get("installed") is not None:
        lines.append(f"已安裝 LoRA（{len(report['installed'])}）：{', '.join(report['installed']) or '（無）'}")
    if report["used"]:
        lines.append("本批使用：" + "；".join(f"{n} × {len(s)} 段" for n, s in report["used"].items()))
    for err in report["errors"]:
        lines.append(f"❌ {err['message']}")
        lines.extend(f"     替代：{alt}" for alt in err["alternatives"])
    for warn in report["warnings"]:
        lines.append(f"⚠️ {warn}")
    lines.append("✅ probe 通過" if report["ok"] else "⛔ probe 未通過：先處理上面的 LoRA，再送件")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    import submit_h3_segments as S
    parser = argparse.ArgumentParser(prog="h3d probe", description="送件前查 API schema 與已安裝 LoRA（缺的直接擋）")
    parser.add_argument("--segments", nargs="+", type=Path, required=True)
    parser.add_argument("--api", default=S.DEFAULT_API_URL)
    parser.add_argument("--installed", help="離線：逗號分隔的已安裝 LoRA（不連 API）")
    parser.add_argument("--schema", type=Path, help="離線：openapi.json 路徑")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    segments: List[Dict[str, Any]] = []
    for path in args.segments:
        segments.extend(_segments(path))
    installed: Optional[List[str]] = None
    schema = None
    fetch_errors: List[str] = []
    if args.installed is not None:
        installed = [x.strip() for x in args.installed.split(",") if x.strip()]
    if args.schema:
        schema = jobspec_from_openapi(json.loads(args.schema.read_text(encoding="utf-8")))
    if args.installed is None and not args.schema:
        token = S.find_token()
        if not token:
            print("❌ 找不到 FreeVideo 令牌，無法 probe", file=sys.stderr)
            return 2
        got = fetch(args.api, token)
        installed, schema, fetch_errors = got["installed"], got["schema"], got["errors"]
    report = check(segments, installed, schema)
    report["warnings"] = fetch_errors + report["warnings"]
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render(report))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
