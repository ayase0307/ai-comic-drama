#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Provider 能力宣告與提交前校驗。

為什麼要有這一層：

FreeVideo 的幾個限制是「用過才知道」的（時長 17n+5 量子、`/jobs` 沒有 `task`
欄位、比例只驗過 16:9／9:16、音色參考只有一個槽位）。這些知識原本散在
`references/freevideo.md` 與專案 helper 裡，改一次 provider 就要重讀一次文件。

現在把它變成機器可讀的 `providers/<name>.json`，送件前先驗：

  - `source=measured` 的欄位 → 違反就是**硬錯誤**（本機真的量過）
  - `source=docs` / `assumed` → 只警告（文件說可以，但我們沒驗到底）

這與 `evidence.py` 同一套哲學：不確定的事情不要假裝確定。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_DIR = Path(__file__).resolve().parent / "providers"
DEFAULT_PROVIDER = "freevideo"


class CapabilityError(ValueError):
    """能力表本身有問題（缺檔、格式壞），不是請求有問題。"""


def load_caps(name: str = DEFAULT_PROVIDER, directory: Optional[Path] = None) -> Dict[str, Any]:
    base = Path(directory) if directory else DEFAULT_DIR
    path = base / f"{name}.json"
    if not path.is_file():
        raise CapabilityError(f"找不到 provider 能力表：{path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CapabilityError(f"{path.name} 無法解析：{exc}") from exc
    if not isinstance(data, dict):
        raise CapabilityError(f"{path.name} 根節點必須是物件")
    data["_path"] = str(path)
    return data


def _value(caps: Dict[str, Any], key: str, default: Any = None) -> Any:
    entry = caps.get(key)
    if isinstance(entry, dict):
        return entry.get("value", default)
    return default if entry is None else entry


def _source(caps: Dict[str, Any], key: str) -> str:
    entry = caps.get(key)
    return str(entry.get("source", "assumed")) if isinstance(entry, dict) else "assumed"


def validate_segment(segment: Dict[str, Any], caps: Dict[str, Any],
                     aspect: Optional[str] = None, quality: Optional[str] = None,
                     frames: Optional[int] = None,
                     reference_count: Optional[int] = None,
                     audio_count: Optional[int] = None,
                     lora_count: Optional[int] = None,
                     refmod_count: Optional[int] = None,
                     vram: Optional[str] = None,
                     project_pack_cap: Optional[int] = None,
                     mode: Optional[str] = None,
                     steps: Optional[int] = None,
                     seconds: Optional[float] = None,
                     has_project: Optional[bool] = None,
                     continue_from: Optional[bool] = None,
                     has_negative: Optional[bool] = None,
                     has_first_frame: Optional[bool] = None) -> Dict[str, List[str]]:
    """回傳 {"errors": [...], "warnings": [...]}。

    呼叫端可只給已知欄位；未給的就跳過該項檢查（不假裝驗過）。
    """
    errors: List[str] = []
    warnings: List[str] = []
    sid = segment.get("segment_id") or segment.get("id") or "?"

    def report(source: str, message: str) -> None:
        (errors if source == "measured" else warnings).append(f"[{sid}] {message}")

    if frames is not None:
        bounds = caps.get("frames") or {}
        minimum = bounds.get("min")
        maximum = bounds.get("max")
        source = str(bounds.get("source", "assumed"))
        if isinstance(minimum, int) and frames < minimum:
            report(source, f"{frames} 幀低於支援下限 {minimum}")
        if isinstance(maximum, int) and frames > maximum:
            report(source, f"{frames} 幀高於支援上限 {maximum}")

    if aspect:
        allowed = _value(caps, "aspects", []) or []
        source = _source(caps, "aspects")
        if allowed and aspect not in allowed:
            report(source, f"比例 {aspect} 不在已驗證清單 {allowed}（{caps.get('aspects', {}).get('note', '')}）")

    if reference_count is not None:
        limit = _value(caps, "max_reference_images")
        if isinstance(limit, int) and reference_count > limit:
            report(_source(caps, "max_reference_images"),
                   f"參考圖 {reference_count} 張超過上限 {limit}")

    if audio_count is not None:
        limit = _value(caps, "max_audio_references")
        if isinstance(limit, int) and audio_count > limit:
            report(_source(caps, "max_audio_references"),
                   f"音訊參考 {audio_count} 個超過上限 {limit}（此上限未經本機完整驗證）")

    if lora_count is not None:
        limit = _value(caps, "max_loras")
        if isinstance(limit, int) and lora_count > limit:
            report(_source(caps, "max_loras"), f"LoRA {lora_count} 個超過上限 {limit}")

    # ---- REMIX 角色包欄位（PR-R1）；能力表沒宣告的欄位一律跳過 ----
    if seconds is not None and isinstance(caps.get("seconds"), dict):
        sec = caps["seconds"]
        source = str(sec.get("source", "assumed"))
        if isinstance(sec.get("min"), (int, float)) and seconds < sec["min"]:
            report(source, f"{seconds:g}s 低於支援下限 {sec['min']}s")
        if isinstance(sec.get("max"), (int, float)) and seconds > sec["max"]:
            report(source, f"{seconds:g}s 高於支援上限 {sec['max']}s")

    if refmod_count is not None:
        for level, message in pack_count_findings(caps, refmod_count, vram=vram, project_cap=project_pack_cap):
            (errors if level == "error" else warnings).append(f"[{sid}] {message}")

    if mode:
        entry = caps.get("modes")
        if isinstance(entry, dict):
            allowed = entry.get("value") or []
            measured = entry.get("measured") or []
            if allowed and mode not in allowed:
                report(str(entry.get("source", "assumed")), f"未知 mode {mode!r}（能力表：{', '.join(allowed)}）")
            elif measured and mode not in measured:
                warnings.append(f"[{sid}] mode {mode!r} 本專案沒跑過（只量過 {', '.join(measured)}）；{entry.get('note', '')}".rstrip("；"))

    if steps is not None and isinstance(caps.get("steps"), dict):
        st = caps["steps"]
        source = str(st.get("source", "assumed"))
        only = st.get("only_modes") or []
        if only and mode and mode not in only:
            report(source, f"steps 只適用 {', '.join(only)}，目前 mode={mode}")
        if isinstance(st.get("min"), int) and steps < st["min"] or isinstance(st.get("max"), int) and steps > st["max"]:
            report(source, f"steps={steps} 不在 {st.get('min')}–{st.get('max')}")

    if continue_from and isinstance(caps.get("continue_from"), dict):
        cf = caps["continue_from"]
        if mode and mode in (cf.get("unsupported_modes") or []):
            report(str(cf.get("source", "assumed")), f"mode {mode} 不支援 continue_from")
        elif cf.get("value") is False:
            report(str(cf.get("source", "assumed")), "此 provider 不支援 continue_from")

    if has_project is False and _value(caps, "requires_project") is True:
        report(_source(caps, "requires_project"), "沒有帶 project（伺服器回 400 project_required）")

    if has_negative and _value(caps, "negative_field") is False:
        report(_source(caps, "negative_field"),
               "此 provider 沒有 negative 欄位，負面詞不會生效；風格要寫在提示詞開頭錨句（E55）")

    if has_first_frame and _value(caps, "first_frame") is False:
        report(_source(caps, "first_frame"), "此 provider 沒有首幀輸入（紀錄來自 v0.8 時期，V1.3 未查）")

    return {"errors": errors, "warnings": warnings}


def pack_count_findings(caps: Dict[str, Any], count: int, vram: Optional[str] = None,
                        project_cap: Optional[int] = None) -> List[Tuple[str, str]]:
    """REMIX 每段包數（含場景包）分級：回傳 [(level, message)]，level 為 error／warning。

    - 超過 max_refmods：依該欄 source（docs → 警告）。
    - 依 practical_pack_cap_by_vram[vram]：> ok 且 < fail → 警告（慢）；≥ fail → 依 fail_source
      分級（measured 才擋；目前 8GB 的 6 包只有一抽 draft 逾時、OOM 為推定，所以是強烈警告）。
    - project_cap（decisions 的 remix_pack_cap）：專案自己定的上限，超過就是錯誤。
      它只能加嚴：預設表從不因包數擋件，專案上限只會多擋、不會放行任何東西。
    """
    out: List[Tuple[str, str]] = []
    count = int(count)
    limit = _value(caps, "max_refmods")
    if isinstance(limit, int) and count > limit:
        level = "error" if _source(caps, "max_refmods") == "measured" else "warning"
        out.append((level, f"[包數] {count} 個 refmods 超過伺服器上限 {limit}（{_source(caps, 'max_refmods')}）"))
    table = caps.get("practical_pack_cap_by_vram")
    if isinstance(table, dict) and table:
        key = vram or ("8GB" if "8GB" in table else next(iter(table)))
        tier = table.get(key)
        if not isinstance(tier, dict):
            if count > 3:
                out.append(("warning", f"[包數] 顯存檔位 {key} 沒有量測資料（只量過 {', '.join(table)}），{count} 包是否可行未知"))
        else:
            ok, slow, fail = tier.get("ok"), tier.get("slow"), tier.get("fail")
            if isinstance(fail, int) and count >= fail:
                src = str(tier.get("fail_source") or tier.get("source") or "assumed")
                tested = (tier.get("modes_tested") or {}).get(str(fail)) or []
                evidence = tier.get("fail_evidence") or "沒有證據說明"
                message = (f"[包數] {count} 包（含場景）達 {key} 失敗級（≥{fail}，{src}）：只用 "
                           f"{'／'.join(tested) or '（無）'} 試過；{evidence}。強烈建議降到 ≤{slow or fail - 1} 包，"
                           f"把次要道具／生物改成文字描述並寫 pack_waivers（附使用者原話）")
                out.append(("error" if src == "measured" else "warning", message))
            elif isinstance(ok, int) and count > ok:
                src = str(tier.get("slow_source") or tier.get("source") or "assumed")
                evidence = tier.get("slow_evidence") or ""
                out.append(("warning", f"[包數] {count} 包（含場景）在 {key} 可行但慢（{src}）"
                                       + (f"：{evidence}" if evidence else "")))
    if project_cap is not None:
        try:
            cap = int(project_cap)
        except (TypeError, ValueError):
            cap = None
        if cap is not None and count > cap:
            out.append(("error", f"[包數] {count} 包超過專案定案上限 remix_pack_cap={cap}"))
    return out


def consistency_warnings(caps: Dict[str, Any]) -> List[str]:
    """能力表必須與 `h3_spec` 的權威常數一致；不一致就是設定漂移。

    依 caps["provider"] 對照 h3_spec.PROVIDER_FRAME_SPECS（freevideo 124–362 往上取、
    remix 56–243 往下取）；能力表有寫 frames.rounding 時也要一致。
    """
    try:
        import h3_spec
    except ImportError:  # pragma: no cover - 套件匯入路徑
        from . import h3_spec
    bounds = caps.get("frames") or {}
    problems: List[str] = []
    provider = str(caps.get("provider") or h3_spec.DEFAULT_PROVIDER)
    try:
        spec = h3_spec.provider_spec(provider)
    except ValueError:
        return [f"h3_spec 沒有 provider {provider!r} 的影格規格；請先在 PROVIDER_FRAME_SPECS 登記"]
    if bounds.get("min") != spec["min_frames"]:
        problems.append(f"capacity.frames.min={bounds.get('min')} 與 h3_spec={spec['min_frames']} 不一致")
    if bounds.get("max") != spec["max_frames"]:
        problems.append(f"capacity.frames.max={bounds.get('max')} 與 h3_spec={spec['max_frames']} 不一致")
    rounding = bounds.get("rounding")
    if rounding is not None and rounding != spec["server_rounding"]:
        problems.append(f"capacity.frames.rounding={rounding} 與 h3_spec={spec['server_rounding']} 不一致")
    fps = _value(caps, "fps")
    if fps != h3_spec.FPS:
        problems.append(f"capacity.fps={fps} 與 h3_spec={h3_spec.FPS} 不一致")
    return problems


def describe(caps: Dict[str, Any]) -> str:
    bounds = caps.get("frames") or {}
    aspects = _value(caps, "aspects", []) or []
    return (
        f"{caps.get('label', caps.get('provider'))}："
        f"{bounds.get('quantum', '?')} @ {_value(caps, 'fps', '?')}fps，"
        f"{bounds.get('min')}–{bounds.get('max')} 幀，"
        f"比例 {', '.join(aspects) or '未宣告'}"
        + ("，秒數往下取量子" if bounds.get("rounding") == "floor" else "")
    )
