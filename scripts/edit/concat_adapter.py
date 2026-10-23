#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Concat adapter：從專案建「全集單一剪輯專案」（T1 影片、T2 字幕、T3 畫外音）。

從《我修的是遺忘課》edit/（make_full_plan.py、build_full.py、cmcp.py）通用化。
兩步：

  1. `h3d concat plan`：讀 segments 順序、影片長度、voice/placement.json（含 final／final_dur）、
     voice/manifest.json、timeline-plan-ep*.csv、voice/h3-asr.json，產生 edit/full-plan.json：
       * segments：每段影片（有 voice/muted/<段>.mp4 就用壓過原聲的版本）
       * captions：畫內台詞優先對齊 ASR 實際時間（對到 ≥ 40% 字才算），否則沿用分鏡時間；
                   畫外台詞跟配音的實際放置時間；相鄰字幕不重疊
       * voices：每句配音在全集時間軸上的起點
       * episode_starts、total
  2. `h3d concat build`：用 Concat 的 headless MCP（`concat.exe --mcp headless`，stdio JSON-RPC）
     建專案：project_create → media_import＋clips_add_sequence（T1）→ captions_add（T2）
     → media_import＋clip_add trackId=T3（畫外音）→ project_save → timeline_read → project_close。
     專案已存在就停下，不覆蓋。

Concat 只在使用者的家機上有；plan 可以在任何地方產生、測試。
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import queue
import re
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
for candidate in (str(SCRIPTS_DIR), str(SCRIPTS_DIR / "voice")):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

import voice_align as V  # noqa: E402

DEFAULT_EXE = r"%LOCALAPPDATA%\Programs\Concat\concat.exe"


# ------------------------------------------------------------------ 1. plan
def build_plan(*, name: str, order: List[str], durations: Dict[str, float],
               lines: Dict[str, List[Dict[str, Any]]], asr: Dict[str, List[Dict[str, Any]]],
               placement: Dict[str, Dict[str, Any]], manifest: Dict[str, Dict[str, Any]],
               muted: Optional[set] = None, video_path: Callable[[str, bool], str] = None,
               voice_path: Callable[[str, Dict[str, Any]], str] = None,
               caption_tail: float = 1.5) -> Dict[str, Any]:
    muted = muted or set()
    video_path = video_path or (lambda sid, m: f"voice/muted/{sid}.mp4" if m else f"videos/{sid}.mp4")
    voice_path = voice_path or (lambda key, item: item.get("final") or f"voice/final/{key}.wav")
    vo_line = {(v["segment"], manifest[k]["line"]): k for k, v in placement.items() if k in manifest}
    segments, captions, voices = [], [], []
    episode_starts: Dict[str, float] = {}
    stats = {"asr_aligned": 0, "storyboard_time": 0, "voice": 0}
    t = 0.0
    for sid in order:
        ep = sid.split("-")[0]
        episode_starts.setdefault(ep, round(t, 3))
        dur = float(durations.get(sid) or 0.0)
        segments.append({"id": sid, "file": video_path(sid, sid in muted), "start": round(t, 3),
                         "duration": round(dur, 3)})
        seg_lines = lines.get(sid, [])
        ref, ref_idx = "", []
        for i, line in enumerate(seg_lines):
            if (sid, line["text"]) in vo_line:
                continue
            for c in V.norm(line["text"]):
                ref += c
                ref_idx.append(i)
        words = [w for chunk in V._clean_chunks(asr.get(sid, [])) for w in (chunk.get("words") or []) if V.norm(w[2])]
        hyp, hyp_idx = "", []
        for wi, w in enumerate(words):
            for c in V.norm(w[2]):
                hyp += c
                hyp_idx.append(wi)
        got: Dict[int, List[float]] = {}
        for block in difflib.SequenceMatcher(None, hyp, ref, autojunk=False).get_matching_blocks():
            for j in range(block.size):
                i = ref_idx[block.b + j]
                w = words[hyp_idx[block.a + j]]
                g = got.setdefault(i, [w[0], w[1], 0])
                g[0], g[1], g[2] = min(g[0], w[0]), max(g[1], w[1]), g[2] + 1
        out = []
        for i, line in enumerate(seg_lines):
            key = vo_line.get((sid, line["text"]))
            if key:
                item = placement[key]
                st = float(item["start"])
                en = st + float(item.get("final_dur") or manifest[key].get("dur") or 2.0)
                voices.append({"key": key, "file": voice_path(key, item), "start": round(t + st, 3)})
                stats["voice"] += 1
            elif i in got and got[i][2] >= max(2, len(V.norm(line["text"])) * 0.4):
                st, en = max(0.0, got[i][0] - 0.1), got[i][1] + 0.3
                stats["asr_aligned"] += 1
            else:
                st, en = float(line["start"]), float(line["end"])
                stats["storyboard_time"] += 1
            out.append([st, en, line["text"]])
        out.sort()
        for j in range(len(out) - 1):
            if out[j][1] > out[j + 1][0] - 0.05:
                out[j][1] = max(out[j][0] + 0.6, out[j + 1][0] - 0.05)
        for st, en, text in out:
            captions.append({"start": round(t + st, 3), "end": round(t + min(en, dur + caption_tail), 3), "text": text})
        t += dur
    captions.sort(key=lambda c: c["start"])
    for j in range(len(captions) - 1):
        if captions[j]["end"] > captions[j + 1]["start"] - 0.04:
            captions[j]["end"] = round(max(captions[j]["start"] + 0.5, captions[j + 1]["start"] - 0.04), 3)
    return {"name": name, "tracks": {"video": "T1", "captions": "T2", "voice": "T3"}, "voice_track": "T3",
            "segments": segments, "captions": captions, "voices": voices, "episode_starts": episode_starts,
            "total": round(t, 3), "stats": stats}


def plan_from_project(root: Path, name: str) -> Dict[str, Any]:
    root = Path(root).resolve()
    voice = root / "voice"
    load = lambda p: json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}  # noqa: E731
    order = V.segment_order(root)
    durations = {s: V.ffprobe_duration(root / "videos" / f"{s}.mp4") or 0.0 for s in order}
    muted = {p.stem for p in (voice / "muted").glob("*.mp4")} if (voice / "muted").is_dir() else set()
    return build_plan(name=name, order=order, durations=durations, lines=V.timeline_lines(root),
                      asr=load(voice / "h3-asr.json"), placement=load(voice / "placement.json"),
                      manifest=load(voice / "manifest.json"), muted=muted)


# ------------------------------------------------------------------ 2. MCP
class McpClient:
    """最小 stdio JSON-RPC MCP client（Concat headless）。"""

    def __init__(self, command: List[str], env: Optional[Dict[str, str]] = None, timeout: float = 120):
        self.proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, env=env)
        self.timeout = timeout
        self.q: "queue.Queue[bytes]" = queue.Queue()
        threading.Thread(target=lambda: [self.q.put(l) for l in self.proc.stdout], daemon=True).start()
        self.n = 0

    def _send(self, payload: Dict[str, Any]) -> None:
        self.proc.stdin.write((json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"))
        self.proc.stdin.flush()

    def rpc(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        self.n += 1
        ident = self.n
        self._send({"jsonrpc": "2.0", "id": ident, "method": method, "params": params or {}})
        while True:
            msg = json.loads(self.q.get(timeout=self.timeout))
            if msg.get("id") == ident:
                return msg

    def initialize(self) -> None:
        self.rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                "clientInfo": {"name": "ai-comic-drama", "version": "1"}})
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def call(self, tool: str, **args: Any) -> Dict[str, Any]:
        resp = self.rpc("tools/call", {"name": tool, "arguments": args})
        res = resp.get("result") or {}
        if "error" in resp or res.get("isError"):
            raise RuntimeError(f"{tool} 失敗：{json.dumps(resp, ensure_ascii=False)[:600]}")
        if res.get("structuredContent") is not None:
            return res["structuredContent"]
        content = res.get("content") or [{}]
        try:
            return json.loads(content[0].get("text") or "{}")
        except json.JSONDecodeError:
            return {"text": content[0].get("text")}

    def close(self) -> None:
        try:
            self.proc.stdin.close()
            self.proc.wait(15)
        except Exception:
            self.proc.kill()
        finally:
            if self.proc.stdout:
                self.proc.stdout.close()


def build_project(plan: Dict[str, Any], *, location: Path, media_root: Path, client: Any,
                  width: int = 1920, height: int = 1080, fps: int = 24, log=print) -> Dict[str, Any]:
    """用 MCP client 建專案；回傳摘要。專案已存在就丟 FileExistsError。"""
    path = Path(location) / plan["name"]
    if (path / "concat.json").exists():
        raise FileExistsError(f"專案已存在：{path}（不覆蓋；要重建請先改名或刪除）")
    resolve = lambda rel: str((Path(media_root) / rel) if not Path(rel).is_absolute() else Path(rel))  # noqa: E731
    client.call("project_create", location=str(location), name=plan["name"],
                video={"width": width, "height": height, "rateNum": fps, "rateDen": 1})
    ids = [client.call("media_import", path=str(path), file=resolve(s["file"]))["createdId"] for s in plan["segments"]]
    client.call("clips_add_sequence", path=str(path), mediaIds=ids, start=0)
    log(f"T1 影片 {len(ids)} 段")
    if plan.get("captions"):
        client.call("captions_add", path=str(path), captions=[{k: c[k] for k in ("start", "end", "text")}
                                                               for c in plan["captions"]], offsetY=0.38)
    log(f"T2 字幕 {len(plan.get('captions', []))} 句")
    track = plan.get("voice_track") or (plan.get("tracks") or {}).get("voice", "T3")
    for v in plan.get("voices", []):
        media = client.call("media_import", path=str(path), file=resolve(v["file"]))["createdId"]
        client.call("clip_add", path=str(path), mediaId=media, start=v["start"], trackId=track)
    log(f"{track} 畫外音 {len(plan.get('voices', []))} 句")
    client.call("project_save", path=str(path))
    timeline = client.call("timeline_read", path=str(path))
    client.call("project_close", path=str(path))
    return {"project": str(path), "segments": len(ids), "captions": len(plan.get("captions", [])),
            "voices": len(plan.get("voices", [])), "timeline": timeline}


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="h3d concat", description="Concat adapter：全集單一剪輯專案（T1 影片、T2 字幕、T3 畫外音）")
    sub = parser.add_subparsers(dest="action", required=True)
    p_plan = sub.add_parser("plan", help="產生 edit/full-plan.json")
    p_plan.add_argument("--root", type=Path, default=Path("."))
    p_plan.add_argument("--name", required=True, help="剪輯專案名稱，例如「我修的是遺忘課 全集粗剪」")
    p_plan.add_argument("--out", type=Path, default=Path("edit/full-plan.json"))
    p_build = sub.add_parser("build", help="用 Concat headless MCP 建專案（家機）")
    p_build.add_argument("--root", type=Path, default=Path("."))
    p_build.add_argument("--plan", type=Path, default=Path("edit/full-plan.json"))
    p_build.add_argument("--location", type=Path, required=True, help="Concat 專案要放的資料夾")
    p_build.add_argument("--media-root", type=Path, default=None, help="plan 裡相對路徑的基準（預設專案根目錄）")
    p_build.add_argument("--exe", default=DEFAULT_EXE, help="concat.exe 路徑（可含環境變數）")
    p_build.add_argument("--mcp-root", action="append", default=[], help="CONCAT_MCP_ROOTS（預設 location 與 media-root）")
    args = parser.parse_args(argv)
    root = args.root.expanduser().resolve()
    if args.action == "plan":
        plan = plan_from_project(root, args.name)
        out = args.out if args.out.is_absolute() else root / args.out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
        s = plan["stats"]
        print(f"✅ {out}：{len(plan['segments'])} 段、字幕 {len(plan['captions'])} 句（對齊原聲 {s['asr_aligned']}／"
              f"沿用分鏡 {s['storyboard_time']}／跟配音 {s['voice']}）、配音 {len(plan['voices'])} 句、{plan['total']:.1f} 秒")
        return 0
    plan_path = args.plan if args.plan.is_absolute() else root / args.plan
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    media_root = (args.media_root or root).resolve()
    exe = os.path.expandvars(args.exe)
    env = dict(os.environ)
    env["CONCAT_MCP_ROOTS"] = os.pathsep.join(args.mcp_root or [str(args.location), str(media_root)])
    client = McpClient([exe, "--mcp", "headless"], env=env)
    try:
        client.initialize()
        result = build_project(plan, location=args.location, media_root=media_root, client=client)
    except (FileExistsError, RuntimeError) as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 2
    finally:
        client.close()
    print(f"✅ Concat 專案：{result['project']}（{result['segments']} 段、{result['captions']} 字幕、{result['voices']} 配音）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
