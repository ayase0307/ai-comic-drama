#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生圖工具（後端）偵測與使用者選擇：`h3d imagegen`。

為什麼：階段 2 設定圖與階段 4 構圖都要「某個生圖工具」，但每台機器能用的不一樣
（家機有 FreeVideo＋Qwen-Image、雲端沙盒只有 Codex CLI、Grok 只有內建 GenerateImage、
有人只想手繪）。過去 `h3d next` 寫死一個預設工具，換環境就給出跑不動的指令。
現在的規則：**生圖後端由使用者選，不自行預設**。

  1. `detect()` 逐一偵測 repo 有 adapter 的後端，每項回 available／reason／對應指令。
     偵測紀律：不生圖、不花錢、不連外部付費 API、不讀出 token 值。
       - codex：`codex` 在 PATH；登入狀態只看 CODEX_HOME（預設 ~/.codex）/auth.json 有沒有憑證欄位，
         不執行 `codex login status`（實測要 7 秒）也不送任何請求。
       - qwen：Qwen-Image 經本機 FreeVideo（FREEVIDEO_API_URL，預設 127.0.0.1:8189）；
         短 timeout 的 TCP 連線＋不帶 token 的 GET /freevideo/agent（只讀 enabled）。
       - grok：Grok 內建 GenerateImage 是 Agent 工具，腳本偵測不到；Agent 用環境變數
         AICD_AGENT_IMAGE_TOOL=grok 宣告自己有這個工具時才算可用，否則標「未知」。
       - manual：手繪／外部上傳 PNG，永遠可用。
       - comfyui：只回報端點狀態（COMFYUI_URL，預設 127.0.0.1:8188）；repo 沒有 ComfyUI 直連生圖 adapter，不能選。
  2. 使用者選擇寫進 decisions.json（repo 慣例：使用者定案一律走 decisions，必附原話）：
       - 階段 2 設定圖：`design_engine`（既有定案，export_asset_prompts.py 已讀它）
       - 階段 4 構圖：`storyboard_engine`
     `h3d imagegen --set <後端> [--stage 2|4|all] --quote "<使用者原話>"`；不給 --stage＝寫入該後端支援的所有階段（共用）。
  3. `resolve()`／`next_step()`／`choice_card()` 給 `h3d next` 與 `h3d inbox` 用：
     沒選 → 列出偵測結果請使用者選（只有一個可用也要問）；已選且可用 → 給該後端指令；
     選了但現在不可用 → 警告並重新詢問。
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence
from urllib.parse import urlsplit

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

SCRIPTS_DIR = Path(__file__).resolve().parent
STORYBOARD_DIR = SCRIPTS_DIR / "storyboard"
for _candidate in (str(SCRIPTS_DIR), str(STORYBOARD_DIR)):
    if _candidate not in sys.path:
        sys.path.insert(0, _candidate)

H3D = f'python "{(SCRIPTS_DIR / "h3d.py").as_posix()}"'
EXPORT = f'python "{(STORYBOARD_DIR / "export_asset_prompts.py").as_posix()}"'
CODEX_ASSETS = f'python "{(STORYBOARD_DIR / "run_codex_asset_gen.py").as_posix()}"'
CODEX_PANELS = f'python "{(STORYBOARD_DIR / "codex_storyboard_panels.py").as_posix()}"'
QWEN_GRID = f'python "{(STORYBOARD_DIR / "qwen_storyboard_grid.py").as_posix()}"'

#: 階段 → decisions.json 的定案 id。
DECISION_FOR_STAGE: Dict[int, str] = {2: "design_engine", 4: "storyboard_engine"}
STAGE_LABEL: Dict[int, str] = {2: "階段 2 設定圖", 4: "階段 4 構圖"}
PROBE_TIMEOUT = 0.8      # TCP 連線秒數（本機拒絕連線是瞬間；遠端不通最多等這麼久）
HTTP_TIMEOUT = 1.5
DEFAULT_FREEVIDEO = "http://127.0.0.1:8189"
DEFAULT_COMFYUI = "http://127.0.0.1:8188"
AGENT_TOOL_ENV = "AICD_AGENT_IMAGE_TOOL"

#: 後端登記表。順序＝收件匣選項順序（會生圖的在前、手繪最後）。
BACKENDS: Dict[str, Dict[str, Any]] = {
    "codex": {"label": "Codex CLI 內建生圖", "short": "Codex", "stages": (2, 4), "selectable": True},
    "qwen": {"label": "Qwen-Image（經本機 FreeVideo）", "short": "Qwen-Image", "stages": (4,), "selectable": True},
    "grok": {"label": "Grok 內建 GenerateImage（Agent 工具）", "short": "Grok", "stages": (2,), "selectable": True},
    "manual": {"label": "手繪／外部上傳 PNG", "short": "手繪／上傳", "stages": (2, 4), "selectable": True},
    "comfyui": {"label": "ComfyUI 端點（僅回報）", "short": "ComfyUI", "stages": (), "selectable": False},
}

ALIASES: Dict[str, str] = {
    "codex": "codex", "codex_cli": "codex", "codexcli": "codex", "gpt_image": "codex", "gpt-image": "codex",
    "qwen": "qwen", "qwen_image": "qwen", "qwen-image": "qwen", "freevideo": "qwen", "qwenimage": "qwen",
    "grok": "grok", "grok_generate_image": "grok", "grok_builtin": "grok", "generateimage": "grok",
    "manual": "manual", "hand": "manual", "handdrawn": "manual", "hand_drawn": "manual", "upload": "manual",
    "external": "manual", "手繪": "manual", "外部上傳": "manual", "上傳": "manual", "手繪／上傳": "manual",
    "comfyui": "comfyui", "comfy": "comfyui",
}


def normalize(value: Any) -> Optional[str]:
    """定案值 → 後端 id；認不得回 None。"""
    if value is None:
        return None
    key = str(value).strip().lower().replace(" ", "_")
    if not key:
        return None
    if key in ALIASES:
        return ALIASES[key]
    key = key.replace("-", "_")
    return ALIASES.get(key)


# ------------------------------------------------------------------ 探測工具（可在測試中替換）
def _endpoint(raw: str, default: str) -> tuple:
    """URL（可含 path）→ (host, port, base_url)。"""
    text = (raw or "").strip() or default
    parts = urlsplit(text if "://" in text else "http://" + text)
    host = parts.hostname or "127.0.0.1"
    try:
        port = parts.port or (443 if parts.scheme == "https" else 80)
    except ValueError:
        port = urlsplit(default).port or 80
    return host, port, f"{parts.scheme or 'http'}://{host}:{port}"


def tcp_open(host: str, port: int, timeout: float = PROBE_TIMEOUT) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def http_json(url: str, timeout: float = HTTP_TIMEOUT) -> Optional[Dict[str, Any]]:
    """不帶 token 的 GET；只用在本機服務的狀態端點。失敗回 None。"""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "aicd-image-backends/1.0"})
        # 不走系統 proxy：這是本機（或使用者自己指定的）服務狀態端點，不該經過外部代理。
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8", errors="replace"))
        return payload if isinstance(payload, dict) else None
    except (OSError, ValueError, urllib.error.URLError):
        return None


# ------------------------------------------------------------------ 逐項偵測
def _codex_auth(env: Mapping[str, str]) -> tuple:
    """回 (logged_in: Optional[bool], 說明)。只看 auth.json 有沒有憑證欄位，不讀出值。"""
    home = Path(env.get("CODEX_HOME") or (Path(env.get("HOME") or Path.home()) / ".codex")).expanduser()
    auth = home / "auth.json"
    if not auth.is_file():
        return False, f"找不到登入資料 {auth.as_posix()}（未登入，或 CODEX_HOME 沒指到正確位置）"
    try:
        data = json.loads(auth.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None, f"{auth.as_posix()} 無法解析，登入狀態未知"
    if not isinstance(data, dict):
        return None, f"{auth.as_posix()} 格式不明，登入狀態未知"
    tokens = data.get("tokens") if isinstance(data.get("tokens"), dict) else {}
    if tokens.get("access_token") or tokens.get("refresh_token"):
        mode = str(data.get("auth_mode") or "chatgpt")
        return True, f"已登入（{'ChatGPT' if mode.lower() == 'chatgpt' else mode}）"
    if data.get("OPENAI_API_KEY"):
        return True, "已登入（API key；生圖會計 API 費用）"
    return False, f"{auth.as_posix()} 沒有登入憑證（請執行 codex login）"


def detect_codex(env: Mapping[str, str], which: Callable[..., Optional[str]]) -> Dict[str, Any]:
    name = "codex.exe" if sys.platform.startswith("win") else "codex"
    exe = which(name, path=env.get("PATH"))
    logged_in, auth_note = _codex_auth(env)
    if not exe:
        extra = "；但找到登入資料，請把 codex 加進 PATH" if logged_in else ""
        return {"available": False, "status": "unavailable",
                "reason": f"PATH 上找不到 {name}{extra}（生圖腳本只從 PATH 找 codex）"}
    if logged_in is False:
        return {"available": False, "status": "unavailable", "reason": f"找到 {exe}，但{auth_note}"}
    if logged_in is None:
        return {"available": None, "status": "unknown", "reason": f"找到 {exe}；{auth_note}"}
    return {"available": True, "status": "available", "reason": f"{exe}；{auth_note}"}


def detect_qwen(env: Mapping[str, str], probe: Callable[..., bool],
                fetch: Callable[..., Optional[Dict[str, Any]]]) -> Dict[str, Any]:
    host, port, base = _endpoint(env.get("FREEVIDEO_API_URL", ""), DEFAULT_FREEVIDEO)
    if not probe(host, port):
        return {"available": False, "status": "unavailable",
                "reason": f"FreeVideo {host}:{port} 連不上（Qwen-Image 經 FreeVideo；可用 FREEVIDEO_API_URL 指到別台）"}
    info = fetch(f"{base}/freevideo/agent")
    if info is None:
        return {"available": None, "status": "unknown",
                "reason": f"{host}:{port} 有服務在聽，但讀不到 FreeVideo agent 狀態"}
    if not info.get("enabled", False):
        return {"available": False, "status": "unavailable", "reason": f"FreeVideo {host}:{port} 在線，但 Agent API 未啟用"}
    return {"available": True, "status": "available",
            "reason": f"FreeVideo {host}:{port} 在線、Agent API 已啟用（是否已裝 Qwen-Image 需帶 token，未檢查）"}


def detect_grok(env: Mapping[str, str]) -> Dict[str, Any]:
    declared = {t.strip().lower() for t in env.get(AGENT_TOOL_ENV, "").replace("，", ",").split(",") if t.strip()}
    if "grok" in declared:
        return {"available": True, "status": "available", "reason": f"Agent 以 {AGENT_TOOL_ENV}=grok 宣告有內建 GenerateImage"}
    return {"available": None, "status": "unknown",
            "reason": f"Agent 內建工具，腳本偵測不到；只有在 Grok（有 GenerateImage）裡才可用（Agent 可設 {AGENT_TOOL_ENV}=grok 宣告）"}


def detect_comfyui(env: Mapping[str, str], probe: Callable[..., bool]) -> Dict[str, Any]:
    host, port, _ = _endpoint(env.get("COMFYUI_URL", ""), DEFAULT_COMFYUI)
    up = probe(host, port)
    state = "有服務在聽" if up else "連不上"
    return {"available": False, "status": "not_selectable",
            "reason": f"{host}:{port} {state}；repo 沒有 ComfyUI 直連生圖 adapter（Qwen-Image 走 FreeVideo），不能選"}


def detect(stage: Optional[int] = None, *, env: Optional[Mapping[str, str]] = None,
           which: Callable[..., Optional[str]] = shutil.which, probe: Optional[Callable[..., bool]] = None,
           fetch: Optional[Callable[..., Optional[Dict[str, Any]]]] = None) -> List[Dict[str, Any]]:
    """偵測所有後端；給 stage 時只回支援該階段的可選後端（＋不可選的 comfyui 只在 stage=None 時出現）。"""
    env = os.environ if env is None else env
    probe = probe or tcp_open
    fetch = fetch or http_json
    detectors: Dict[str, Callable[[], Dict[str, Any]]] = {
        "codex": lambda: detect_codex(env, which),
        "qwen": lambda: detect_qwen(env, probe, fetch),
        "grok": lambda: detect_grok(env),
        "manual": lambda: {"available": True, "status": "available",
                           "reason": "永遠可用：使用者手繪或用其他工具出圖後上傳 PNG"},
        "comfyui": lambda: detect_comfyui(env, probe),
    }
    rows: List[Dict[str, Any]] = []
    for bid, meta in BACKENDS.items():
        if stage is not None and stage not in meta["stages"]:
            continue  # 只偵測需要的後端（不必要的端點不探測）
        row = {"id": bid, "label": meta["label"], "stages": list(meta["stages"]),
               "selectable": meta["selectable"], **detectors[bid]()}
        row["commands"] = {str(s): command_for(bid, s) for s in meta["stages"]}
        rows.append(row)
    return rows


# ------------------------------------------------------------------ 指令
def command_for(backend: str, stage: int, episode: Optional[str] = None) -> Optional[str]:
    """後端在該階段的指令（相對專案根執行）；手繪沒有指令（回 None）。"""
    ep = f" --episode {episode}" if episode else ""
    if stage == 2:
        if backend == "codex":
            return (f"{EXPORT} --assets-md assets.md --project-dir . --out-json tmp/asset-prompts.json"
                    f" && {CODEX_ASSETS} --prompts tmp/asset-prompts.json --output-dir images --model <使用者指定模型>")
        if backend == "grok":
            return f"{EXPORT} --assets-md assets.md --project-dir ."
    if stage == 4:
        if backend == "codex":
            return f"{CODEX_PANELS} --root .{ep} --model <使用者指定模型>"
        if backend == "qwen":
            return f"{QWEN_GRID} --layer2-dir layer2{ep} --generate-all --assemble-grid"
    return None


def action_for(backend: str, stage: int) -> str:
    if stage == 2:
        return {
            "codex": "用 Codex CLI 生成設定圖：先匯出提示詞，再逐張生成到 images/；--model 填使用者指定的 Codex 生圖模型（必填）。"
                     "生成後親眼驗收臉和服裝。",
            "grok": "匯出 Grok 生圖清單（images/grok-manifest.json＋.md），再用 Grok 內建 GenerateImage 逐張生成到 output_path，"
                    "生成後把 status 改 done 並親眼驗收。",
            "manual": "請使用者把手繪／外部工具出的設定圖 PNG 放到 assets.md 登記的路徑（images/…），放好後再跑 h3d next。",
        }.get(backend, "")
    if stage == 4:
        return {
            "codex": "用 Codex 分鏡補每鏡構圖（每鏡一張＋每段總覽圖，回寫 sketch_file）；--model 填使用者指定的 Codex 生圖模型（必填）。",
            "qwen": "用 Qwen-Image（經本機 FreeVideo）出鉛筆構圖並拼總覽圖（回寫 sketch_file）；送件前不要碰別人在 FreeVideo 的 job。",
            "manual": "請使用者提供每鏡的手繪／外部工具 PNG（照該段 metadata.aspect_ratio），放進 panels/ 後回寫該鏡 sketch_file，再跑 h3d next。",
        }.get(backend, "")
    return ""


# ------------------------------------------------------------------ 讀定案、判斷狀態
def _decision_value(root: Path, decision_id: str) -> Any:
    import decisions as decisions_mod
    try:
        item = decisions_mod.get(decisions_mod.load(Path(root)), decision_id)
    except decisions_mod.DecisionError:
        return None
    return (item or {}).get("value")


def resolve(root: Path, stage: int, rows: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """回傳該階段的選擇狀態：
    state ∈ unchosen（沒選）／chosen（已選且可用或狀態未知）／unavailable（選了但現在不可用）／invalid（值認不得或不支援此階段）。"""
    rows = rows if rows is not None else detect(stage)
    rows = [r for r in rows if stage in r["stages"]]
    did = DECISION_FOR_STAGE[stage]
    raw = _decision_value(root, did)
    out: Dict[str, Any] = {"stage": stage, "decision_id": did, "raw": raw, "backend": None,
                           "rows": rows, "state": "unchosen", "warning": None}
    if raw in (None, ""):
        return out
    bid = normalize(raw)
    row = next((r for r in rows if r["id"] == bid), None)
    if bid is None or row is None:
        out["state"] = "invalid"
        out["warning"] = (f"{did} 定案值 {raw!r} 不是{STAGE_LABEL[stage]}可用的後端"
                          f"（可選：{'、'.join(r['id'] for r in rows if r['selectable'])}）")
        return out
    out["backend"] = bid
    out["row"] = row
    if row["available"] is False:
        out["state"] = "unavailable"
        out["warning"] = f"已選 {BACKENDS[bid]['label']}，但現在不可用：{row['reason']}"
        return out
    out["state"] = "chosen"
    if row["available"] is None:
        out["warning"] = f"已選 {BACKENDS[bid]['label']}，但狀態無法確認：{row['reason']}"
    return out


def selectable_rows(rows: Sequence[Dict[str, Any]], stage: int) -> List[Dict[str, Any]]:
    return [r for r in rows if r["selectable"] and stage in r["stages"]]


def available_rows(rows: Sequence[Dict[str, Any]], stage: int) -> List[Dict[str, Any]]:
    return [r for r in selectable_rows(rows, stage) if r["available"] is True]


def recommended(rows: Sequence[Dict[str, Any]], stage: int) -> Optional[str]:
    """只有「恰好一個」可用時才標建議（手繪不算會生圖的工具，除非只剩它）；兩個以上不建議、交給使用者選。"""
    avail = available_rows(rows, stage)
    generators = [r for r in avail if r["id"] != "manual"]
    if len(generators) == 1:
        return generators[0]["id"]
    if not generators and len(avail) == 1:
        return avail[0]["id"]
    return None


def _row_line(row: Dict[str, Any]) -> str:
    mark = {"available": "✅ 可用", "unknown": "❔ 未知", "unavailable": "⛔ 不可用", "not_selectable": "— 不可選"}
    return f"{mark.get(row['status'], row['status'])}  {row['id']:8s} {row['label']}：{row['reason']}"


def set_command(stage: int, rows: Sequence[Dict[str, Any]]) -> str:
    choices = [r["id"] for r in selectable_rows(rows, stage) if r["available"] is not False]
    return (f'{H3D} imagegen --set <{"|".join(choices) or "manual"}> --stage {stage} '
            f'--quote "<使用者原話>" --root .')


def ask_text(resolution: Dict[str, Any]) -> str:
    """給 `h3d next` 的 action：請使用者選，列可用與不可用（含原因）。"""
    stage, rows = resolution["stage"], resolution["rows"]
    avail = [r for r in selectable_rows(rows, stage) if r["available"] is not False]
    off = [r for r in selectable_rows(rows, stage) if r["available"] is False]
    rec = recommended(rows, stage)
    head = {
        "unchosen": f"還沒選{STAGE_LABEL[stage]}要用哪個生圖工具：問使用者，不要自己預設。",
        "unavailable": f"⚠️ {resolution['warning']}。先告訴使用者，再重新詢問要換哪個工具（或修好後照用）。",
        "invalid": f"⚠️ {resolution['warning']}。請使用者重新選。",
    }.get(resolution["state"], "")
    parts = [head, "可選：" + "；".join(
        f"{r['id']}（{BACKENDS[r['id']]['short']}{'，建議' if r['id'] == rec else ''}"
        f"{'，狀態未知需確認' if r['available'] is None else ''}）" for r in avail) + "。"]
    if off:
        parts.append("不可用：" + "；".join(f"{r['id']}（{r['reason']}）" for r in off) + "。")
    if rec:
        parts.append(f"只偵測到一個可用（{rec}）也要問使用者確認，可標為建議。")
    parts.append("拿到回覆後用使用者原話寫入（下面指令）。")
    return " ".join(p for p in parts if p)


def next_step(root: Path, stage: int, episode: Optional[str] = None,
              rows: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """給 `h3d next` 用：回 {state, command, action, notes, imagegen}。
    command 為 None＝停下來問使用者（手繪且沒有指令時也是 None）。"""
    res = resolve(root, stage, rows)
    payload = {"stage": stage, "decision_id": res["decision_id"], "state": res["state"], "backend": res["backend"],
               "recommended": recommended(res["rows"], stage),
               "backends": [{k: r[k] for k in ("id", "label", "available", "status", "reason")} for r in res["rows"]]}
    notes: List[str] = []
    if res["state"] != "chosen":
        return {"state": res["state"], "command": set_command(stage, res["rows"]), "action": ask_text(res),
                "ask_user": True, "notes": notes, "imagegen": payload,
                "blocked": res["warning"] or f"尚未選擇{STAGE_LABEL[stage]}的生圖工具（{res['decision_id']}）"}
    if res["warning"]:
        notes.append(res["warning"])
    bid = res["backend"]
    return {"state": "chosen", "command": command_for(bid, stage, episode), "action": action_for(bid, stage),
            "ask_user": False, "notes": notes, "imagegen": payload, "blocked": None}


def choice_card(root: Path, stage: int, *, resolution: Optional[Dict[str, Any]] = None,
                segment: str = "全集") -> Dict[str, Any]:
    """收件匣卡：請使用者選生圖工具。可用的當選項，不可用的灰掉並寫原因（unavailable_options）。"""
    res = resolution or resolve(root, stage)
    rows = res["rows"]
    choices = [r for r in selectable_rows(rows, stage) if r["available"] is not False]
    off = [r for r in selectable_rows(rows, stage) if r["available"] is False]
    rec = recommended(rows, stage)
    choices.sort(key=lambda r: (r["id"] != rec, list(BACKENDS).index(r["id"])))
    label = STAGE_LABEL[stage]
    options = [{"label": BACKENDS[r["id"]]["short"] + ("（需確認）" if r["available"] is None else ""),
                "reply": f"{label}生圖工具：用 {BACKENDS[r['id']]['label']}"} for r in choices[:3]]
    if len(options) < 2:
        options.append({"label": "我先去裝／登入工具", "reply": f"{label}生圖工具：我先去安裝或登入，好了再選"})
    if res["state"] == "unavailable":
        title = f"已選的{BACKENDS[res['backend']]['short']}現在不能用，要換嗎"
    elif res["state"] == "invalid":
        title = f"{label}的生圖工具設定認不得，請重選"
    else:
        title = f"{label}要用哪個生圖工具"
    if rec:
        recommendation = (f"只偵測到 {BACKENDS[rec]['label']} 可用，建議用它；仍要你確認，我不自己決定。")
    else:
        recommendation = "偵測到不只一個可用的工具，請你選；我不替你預設。"
    sure = [r for r in choices if r["available"] is True]
    unsure = [r for r in choices if r["available"] is None]
    finding = "可用：" + ("、".join(f"{BACKENDS[r['id']]['short']}（{r['reason']}）" for r in sure) or "無")
    if unsure:
        finding += "；狀態未知（選前要確認）：" + "、".join(f"{BACKENDS[r['id']]['short']}（{r['reason']}）" for r in unsure)
    if off:
        finding += "；不可用：" + "、".join(f"{BACKENDS[r['id']]['short']}（{r['reason']}）" for r in off)
    if res.get("warning"):
        finding = f"{res['warning']}。" + finding
    return {
        "id": f"D{stage}-imagegen-backend", "kind": "decision", "stage": stage, "segment": segment,
        "title": title, "finding": finding,
        "impact": ("設定圖決定全片的臉和畫風，工具一經選定全集鎖定；換工具要並排比對後重審。" if stage == 2 else
                   "每一鏡都要構圖 PNG 才能進提示詞編譯；選定的工具會用來補齊所有缺的鏡。"),
        "recommendation": recommendation, "options": options,
        "no_recommendation": rec is None,
        "unavailable_options": [{"label": BACKENDS[r["id"]]["short"], "reason": r["reason"]} for r in off],
        "if_ignored": f"{label}沒有工具可以出圖，這一步停著。",
        "blocking": 1, "blocking_label": "擋下一步", "evidence_paths": [], "links": [],
        "backends": [{k: r[k] for k in ("id", "label", "available", "status", "reason")} for r in rows],
        "source": f"image_backends.detect()＋decisions.json {res['decision_id']}",
    }


def needs_card(root: Path, stage: int) -> Optional[Dict[str, Any]]:
    """沒選、選了不可用或值認不得時回卡片；已選可用回 None。"""
    res = resolve(root, stage)
    return None if res["state"] == "chosen" else choice_card(root, stage, resolution=res)


# ------------------------------------------------------------------ 寫入使用者選擇
class ImagegenError(ValueError):
    pass


def set_backend(root: Path, backend: str, quote: str, *, stage: str = "auto",
                allow_unavailable: bool = False, rows: Optional[List[Dict[str, Any]]] = None,
                by: str = "user") -> List[Dict[str, Any]]:
    """把使用者選的後端寫進 decisions.json（design_engine／storyboard_engine）。回傳寫入的定案。"""
    import decisions as decisions_mod
    bid = normalize(backend)
    if bid is None or bid not in BACKENDS:
        raise ImagegenError(f"不認得的生圖後端 {backend!r}（可選：{'、'.join(b for b, m in BACKENDS.items() if m['selectable'])}）")
    meta = BACKENDS[bid]
    if not meta["selectable"]:
        raise ImagegenError(f"{meta['label']} 不能選：repo 沒有對應的生圖 adapter")
    if stage in ("auto", "all", None):
        stages = list(meta["stages"])
    else:
        try:
            stages = [int(stage)]
        except ValueError as exc:
            raise ImagegenError(f"--stage 只能是 2、4 或 all（收到 {stage!r}）") from exc
    for s in stages:
        if s not in DECISION_FOR_STAGE:
            raise ImagegenError(f"--stage 只能是 2、4 或 all（收到 {s}）")
        if s not in meta["stages"]:
            raise ImagegenError(f"{meta['label']} 不支援{STAGE_LABEL[s]}（支援：{'、'.join(STAGE_LABEL[x] for x in meta['stages'])}）")
    rows = rows if rows is not None else detect()
    row = next((r for r in rows if r["id"] == bid), None)
    if row and row["available"] is False and not allow_unavailable:
        raise ImagegenError(f"{meta['label']} 現在不可用：{row['reason']}。"
                            "先修好再選；使用者明確要先定下來（例如要換到別台機器跑）才加 --allow-unavailable")
    written = []
    for s in stages:
        written.append(decisions_mod.decide(Path(root), DECISION_FOR_STAGE[s], bid, quote, by=by,
                                            rule=f"{STAGE_LABEL[s]}生圖工具：{meta['label']}（使用者選擇，全集沿用）"))
    return written


# ------------------------------------------------------------------ CLI
def _print_detect(rows: List[Dict[str, Any]], root: Optional[Path], stage: Optional[int]) -> None:
    print("生圖工具偵測（不生圖、不花錢、不連外部付費 API、不讀 token 值）")
    for row in rows:
        stages = "、".join(STAGE_LABEL[s] for s in row["stages"]) or "—"
        print(f"  {_row_line(row)}  ［{stages}］")
    if root is not None and (root / "decisions.json").is_file():
        print("專案目前的選擇：")
        for s in (stage,) if stage else (2, 4):
            res = resolve(root, s, rows)
            shown = {"unchosen": "尚未選擇（h3d next 會請使用者選）", "chosen": f"{res['backend']}",
                     "unavailable": f"{res['backend']}（⚠️ 現在不可用，需重新詢問）",
                     "invalid": f"{res['raw']!r}（⚠️ 認不得，需重新詢問）"}[res["state"]]
            print(f"  {STAGE_LABEL[s]}（{res['decision_id']}）：{shown}")
    print("生圖後端由使用者選，不自行預設：問使用者後執行 "
          "h3d imagegen --set <後端> [--stage 2|4] --quote \"<使用者原話>\" --root <專案>")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="h3d imagegen",
        description="偵測可用的生圖工具（--detect），或把使用者選的後端寫進 decisions.json（--set）。生圖後端由使用者選，不自行預設。",
        epilog='例：h3d imagegen --detect --root .；h3d imagegen --set codex --quote "設定圖和分鏡都用 Codex" --root .',
    )
    parser.add_argument("--detect", action="store_true", help="列出偵測結果（預設動作）")
    parser.add_argument("--set", dest="set_backend", metavar="BACKEND",
                        help=f"寫入使用者選的後端（{'／'.join(b for b, m in BACKENDS.items() if m['selectable'])}）")
    parser.add_argument("--stage", default=None,
                        help="--detect：只看某階段（2／4）；--set：寫入 2、4 或 all（省略＝該後端支援的所有階段，共用）")
    parser.add_argument("--quote", help="--set 必填：使用者原話")
    parser.add_argument("--allow-unavailable", action="store_true",
                        help="--set 時後端現在不可用仍寫入（只有使用者明確要求時才用）")
    parser.add_argument("--by", default="user", choices=["user", "user_delegated"])
    parser.add_argument("--root", type=Path, default=None, help="專案根目錄（--set 必填；--detect 給了會一併印目前選擇）")
    parser.add_argument("--json", action="store_true", help="以 JSON 輸出")
    args = parser.parse_args(argv)

    if args.set_backend:
        if args.root is None:
            parser.error("--set 需要 --root <專案>")
        try:
            entries = set_backend(args.root.expanduser().resolve(), args.set_backend, args.quote or "",
                                  stage=args.stage or "auto", allow_unavailable=args.allow_unavailable, by=args.by)
        except (ImagegenError, ValueError) as exc:
            print(f"❌ {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(entries, ensure_ascii=False, indent=2))
        else:
            for entry in entries:
                print(f"✅ 已記錄定案 {entry['id']}：{entry['rule']}")
        return 0

    stage: Optional[int] = None
    if args.stage not in (None, "all"):
        try:
            stage = int(args.stage)
        except ValueError:
            parser.error("--stage 只能是 2 或 4")
        if stage not in DECISION_FOR_STAGE:
            parser.error("--stage 只能是 2 或 4")
    rows = detect(stage)
    root = args.root.expanduser().resolve() if args.root else None
    if args.json:
        payload: Dict[str, Any] = {"backends": rows}
        if root is not None:
            payload["choices"] = {str(s): {k: v for k, v in resolve(root, s, rows).items()
                                           if k in ("decision_id", "state", "backend", "raw", "warning")}
                                  for s in ((stage,) if stage else (2, 4))}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        _print_detect(rows, root, stage)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
