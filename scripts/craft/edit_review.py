#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Stage-7 editing lenses (murch-cut / hamilton-action): advisory checks over the assembled timeline.

Reads (all optional except one timeline source):
  * timeline-plan-<ep>.csv     shot rows: shot_id,start,end,duration,video_file,subtitle,narration,speaker,foley
  * edit/full-plan.json        h3d concat plan output: segments / captions / voices / episode_starts / total
  * videos/speed-ramps.json    stage-6 speed-ramp manifest (status per segment)
  * --video <final.mp4>        optional measured evidence via ffmpeg (scene cuts, EBU R128 loudness)

Writes review/craft/stage-7-edit-<ep>.md. Never blocks: exit 0 unless bad CLI usage.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import keep_agent_section  # noqa: E402

LENS = "edit"
LENSES = {
    "murch-cut": "Walter Murch 剪點與聲音（references/craft/murch-cut/SKILL.md）",
    "hamilton-action": "Eddie Hamilton 動作節奏（references/craft/hamilton-action/SKILL.md）",
}

# 門檻（依據見 references/edit/manju-editing-playbook.md 與兩個 lens 的 SKILL.md）
HOOK_S = 3.0                 # 前 3 秒要有台詞／旁白（短劇鉤子）
CPS_MAX = 7.0                # 中文字幕讀速上限（字/秒）
CAPTION_MAX_CHARS = 15       # 單行字幕字數上限（repo 規則 12–15 字）
CAPTION_MIN_S = 0.8          # 字幕最短停留
SILENT_SHOT_MAX_S = 6.0      # 無台詞、無旁白的單鏡上限
ASL_CV_MIN = 0.25            # 鏡頭長度變異係數過低＝節奏單調
TAIL_S = 2.0                 # 集尾最後 2 秒要落在台詞／懸念上
LUFS_RANGE, TP_MAX = (-16.0, -14.0), -1.0   # 豎屏串流成片；送審母帶另出 EBU −23（assemble 預設）
FAST_SHOT_S, FATIGUE_S = 1.5, 20.0  # Hamilton：連續快剪累計超過 20 秒沒有緩衝段＝動作疲勞
BREATH_S = 0.3               # Murch／pipeline §7.2：段內最後一句台詞到段尾至少留 0.3 秒
SPEECH_LAYERS_MAX = 1        # 同一時間最多 1 條人聲（Murch 2.5 層：同類聲音 ≥2 條就互相遮蔽）

Finding = Tuple[str, str, str]
PUNCT = re.compile(r"[\s，。、！？；：,.!?;:「」『』“”\"'（）()…—\-]")


def chars(text: str) -> int:
    return len(PUNCT.sub("", text or ""))


def segment_of(shot_id: str) -> str:
    return shot_id.rsplit("-SH", 1)[0] if "-SH" in shot_id else shot_id


def fnum(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def load_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def load_timeline(project_dir: Path, episode: str) -> List[Dict[str, Any]]:
    """Shot rows with global start/end (segments laid end to end in file order)."""
    path = project_dir / f"timeline-plan-{episode.lower()}.csv"
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    shots: List[Dict[str, Any]] = []
    offset, cur_seg, seg_len = 0.0, None, 0.0
    for r in rows:
        sid = (r.get("shot_id") or "").strip()
        if not sid:
            continue
        seg = segment_of(sid)
        if seg != cur_seg:
            offset += seg_len
            cur_seg, seg_len = seg, 0.0
        st, en = fnum(r.get("start")), fnum(r.get("end"))
        if en <= st:
            en = st + fnum(r.get("duration"))
        seg_len = max(seg_len, en)
        shots.append({"shot": sid, "segment": seg, "start": offset + st, "end": offset + en,
                      "dur": en - st, "subtitle": (r.get("subtitle") or "").strip(),
                      "narration": (r.get("narration") or "").strip(), "speaker": (r.get("speaker") or "").strip(),
                      "foley": (r.get("foley") or "").strip()})
    return shots


def plan_for_episode(plan: Optional[Dict[str, Any]], episode: str) -> Optional[Dict[str, Any]]:
    """Slice a full-series plan down to one episode, re-based to t=0."""
    if not plan:
        return None
    ep = episode.upper()
    segs = [s for s in plan.get("segments", []) if str(s.get("id", "")).upper().startswith(ep)]
    if not segs:
        return None
    t0 = min(fnum(s.get("start")) for s in segs)
    t1 = max(fnum(s.get("start")) + fnum(s.get("duration")) for s in segs)
    def inside(x: Dict[str, Any]) -> bool:
        return t0 - 1e-3 <= fnum(x.get("start")) < t1
    shift = lambda items: [dict(x, start=fnum(x.get("start")) - t0, **({"end": fnum(x["end"]) - t0} if "end" in x else {}))  # noqa: E731
                           for x in items if inside(x)]
    return {"segments": shift(segs), "captions": shift(plan.get("captions", [])),
            "voices": shift(plan.get("voices", [])), "total": t1 - t0}


# ---------- checks ----------

def check_hook(shots: List[Dict[str, Any]], plan: Optional[Dict[str, Any]]) -> Finding:
    first = None
    if plan and plan["captions"]:
        first = min(fnum(c["start"]) for c in plan["captions"])
    for sh in shots:
        if sh["subtitle"] or sh["narration"]:
            first = sh["start"] if first is None else min(first, sh["start"])
            break
    if first is None:
        return ("⚠️", "開頭鉤子", "全集找不到台詞或旁白，無法判斷前 3 秒鉤子")
    ok = first <= HOOK_S
    return ("✅" if ok else "⚠️", "開頭鉤子",
            f"第一句台詞／旁白在 {first:.1f} 秒（門檻 {HOOK_S:.0f} 秒）" + ("" if ok else "；前 3 秒只有畫面，考慮把衝突句或爆點鏡提前（冷開場）"))


def check_rhythm(shots: List[Dict[str, Any]]) -> List[Finding]:
    durs = [s["dur"] for s in shots if s["dur"] > 0]
    if len(durs) < 3:
        return [("⚠️", "鏡頭長度", f"只有 {len(durs)} 個鏡頭，無法統計節奏")]
    mean, med = statistics.mean(durs), statistics.median(durs)
    cv = statistics.pstdev(durs) / mean if mean else 0.0
    out = [("ℹ️", "鏡頭長度", f"{len(durs)} 鏡，平均 {mean:.2f} 秒、中位數 {med:.2f} 秒、最長 {max(durs):.2f} 秒（分鏡時長，未扣變速）"),
           ("⚠️" if cv < ASL_CV_MIN else "✅", "節奏變化",
            f"鏡頭長度變異係數 {cv:.2f}（低於 {ASL_CV_MIN} 代表每鏡差不多長，像節拍器）")]
    silent = [s for s in shots if not s["subtitle"] and not s["narration"] and s["dur"] >= SILENT_SHOT_MAX_S]
    if silent:
        out.append(("⚠️", "無聲長鏡", "、".join(f"{s['shot']}（{s['dur']:.1f}s）" for s in silent[:6]) +
                    f" 沒有台詞也沒有旁白且 ≥ {SILENT_SHOT_MAX_S:.0f} 秒；確認是刻意留白，否則修短或交給變速"))
    return out


def check_captions(shots: List[Dict[str, Any]], plan: Optional[Dict[str, Any]]) -> List[Finding]:
    caps = [(fnum(c["start"]), fnum(c.get("end")), c.get("text", "")) for c in plan["captions"]] if plan and plan["captions"] else \
           [(s["start"], s["end"], s["subtitle"] or s["narration"]) for s in shots if s["subtitle"] or s["narration"]]
    if not caps:
        return [("ℹ️", "字幕", "沒有字幕可檢查")]
    fast, long_, short = [], [], []
    for st, en, text in caps:
        n, d = chars(text), max(en - st, 1e-3)
        if n / d > CPS_MAX:
            fast.append(f"「{text[:12]}」{n / d:.1f} 字/秒")
        if n > CAPTION_MAX_CHARS:
            long_.append(f"「{text[:12]}…」{n} 字")
        if d < CAPTION_MIN_S:
            short.append(f"「{text[:8]}」{d:.2f}s")
    src = "edit/full-plan.json" if plan and plan["captions"] else "timeline-plan（分鏡時間）"
    out = [("ℹ️", "字幕來源", f"{len(caps)} 句，時間取自 {src}")]
    out.append(("⚠️" if fast else "✅", "字幕讀速", (f"{len(fast)} 句超過 {CPS_MAX:.0f} 字/秒：" + "；".join(fast[:5])) if fast else f"全部 ≤ {CPS_MAX:.0f} 字/秒"))
    if long_:
        out.append(("⚠️", "字幕長度", f"{len(long_)} 句超過 {CAPTION_MAX_CHARS} 字（9:16 一行放不下，拆句或改花字重點詞）：" + "；".join(long_[:5])))
    if short:
        out.append(("⚠️", "字幕停留", f"{len(short)} 句短於 {CAPTION_MIN_S} 秒：" + "；".join(short[:5])))
    return out


def check_speech_overlap(plan: Optional[Dict[str, Any]], shots: List[Dict[str, Any]]) -> Finding:
    """Two speech streams at once (in-frame line + external VO) mask each other."""
    if not plan or not plan["voices"]:
        both = [s["shot"] for s in shots if s["subtitle"] and s["narration"]]
        if both:
            return ("⚠️", "人聲疊層", f"{len(both)} 鏡同時有畫內台詞與旁白：{'、'.join(both[:6])}；確認旁白落在台詞的空檔，不要同時說")
        return ("✅", "人聲疊層", "沒有發現畫內台詞與旁白同時出現")
    vo_starts = [fnum(v["start"]) for v in plan["voices"]]
    hits = []
    for c in plan["captions"]:
        st, en = fnum(c["start"]), fnum(c.get("end"))
        for v in vo_starts:
            if st + 0.15 < v < en - 0.15 and not any(abs(v - fnum(c2["start"])) < 0.05 for c2 in plan["captions"]):
                hits.append(f"{v:.1f}s")
    if hits:
        return ("⚠️", "人聲疊層", f"{len(hits)} 句畫外配音落在畫內台詞中間（{'、'.join(hits[:6])}）；同時最多 {SPEECH_LAYERS_MAX} 條人聲")
    return ("✅", "人聲疊層", f"{len(vo_starts)} 句畫外配音都沒有壓在畫內台詞中間")


def check_cut_straddle(plan: Optional[Dict[str, Any]]) -> Optional[Finding]:
    if not plan or not plan["segments"]:
        return None
    bounds = [fnum(s["start"]) for s in plan["segments"][1:]]
    hits = []
    for c in plan["captions"]:
        st, en = fnum(c["start"]), fnum(c.get("end"))
        hits += [f"「{c.get('text', '')[:8]}」@{b:.1f}s" for b in bounds if st + 0.2 < b < en - 0.2]
    if not hits:
        return ("✅", "字幕跨段", "沒有字幕橫跨段落剪點")
    return ("ℹ️", "字幕跨段", f"{len(hits)} 句橫跨段落剪點（聲音先行的 J/L cut 可以，非刻意就把剪點移到句尾）：" + "；".join(hits[:5]))


def check_fatigue(shots: List[Dict[str, Any]]) -> Finding:
    run_s, worst, where, start = 0.0, 0.0, "", ""
    for sh in shots:
        if 0 < sh["dur"] < FAST_SHOT_S:
            start = start or sh["shot"]
            run_s += sh["dur"]
            if run_s > worst:
                worst, where = run_s, f"{start} 起"
        else:
            run_s, start = 0.0, ""
    if worst > FATIGUE_S:
        return ("⚠️", "動作疲勞", f"連續短於 {FAST_SHOT_S} 秒的鏡頭累計 {worst:.1f} 秒（{where}；門檻 {FATIGUE_S:.0f} 秒），中間插一拍反應或喘息鏡")
    return ("✅", "動作疲勞", f"最長的連續快剪累計 {worst:.1f} 秒（門檻 {FATIGUE_S:.0f} 秒）")


def check_breath(plan: Optional[Dict[str, Any]]) -> Finding:
    """Per segment: last caption ends too close to the segment cut → no air before the next segment.

    Needs real caption times (edit/full-plan.json, ASR-aligned); storyboard subtitles span the whole shot."""
    if not plan or not plan["captions"] or not plan["segments"]:
        return ("ℹ️", "句尾留白", "沒有 edit/full-plan.json 的實際字幕時間（分鏡字幕佔滿整鏡），略過；先跑 `h3d concat plan`")
    tight = []
    for seg in plan["segments"]:
        st, en = fnum(seg["start"]), fnum(seg["start"]) + fnum(seg.get("duration"))
        ends = [fnum(c.get("end")) for c in plan["captions"] if st <= fnum(c["start"]) < en]
        if ends and en - max(ends) < BREATH_S:
            tight.append(f"{seg.get('id')}（{en - max(ends):.2f}s）")
    if not tight:
        return ("✅", "句尾留白", f"每段最後一句到段尾都 ≥ {BREATH_S} 秒")
    return ("⚠️", "句尾留白", f"{len(tight)} 段最後一句貼著段尾（< {BREATH_S} 秒）：{'、'.join(tight[:6])}；剪點前留一點反應時間，或確認是刻意的搶切")


def check_tail(shots: List[Dict[str, Any]], plan: Optional[Dict[str, Any]]) -> Finding:
    if not shots and not plan:
        return ("⚠️", "集尾卡點", "沒有時間軸")
    total = plan["total"] if plan else max(s["end"] for s in shots)
    texts = [(fnum(c["start"]), fnum(c.get("end"))) for c in plan["captions"]] if plan and plan["captions"] else \
            [(s["start"], s["end"]) for s in shots if s["subtitle"] or s["narration"]]
    last_end = max((en for _, en in texts), default=0.0)
    gap = total - last_end
    ok = gap <= TAIL_S
    return ("✅" if ok else "⚠️", "集尾卡點",
            f"最後一句結束後還有 {gap:.1f} 秒（門檻 {TAIL_S:.0f} 秒）" + ("" if ok else "；長尾容易變成淡出，懸念句或反轉鏡應該壓到最後一拍再切黑"))


def check_ramps(project_dir: Path, episode: str) -> Optional[Finding]:
    data = load_json(project_dir / "videos" / "speed-ramps.json")
    if not data:
        return None
    segs = {k: v for k, v in (data.get("segments") or {}).items() if k.upper().startswith(episode.upper())}
    if not segs:
        return None
    by: Dict[str, List[str]] = {}
    for k, v in segs.items():
        by.setdefault(str(v.get("status", "?")), []).append(k)
    pending = by.get("proposed", []) + by.get("approved", []) + by.get("verify_failed", [])
    detail = "、".join(f"{k} {len(v)}" for k, v in sorted(by.items()))
    return ("⚠️" if pending else "✅", "後製變速",
            f"{detail}" + (f"；未產檔或驗證失敗：{'、'.join(pending[:6])}（組裝會用原片）" if pending else ""))


def measure_video(video: Path) -> List[Finding]:
    if not shutil.which("ffmpeg"):
        return [("⚠️", "成片量測", "找不到 ffmpeg，略過")]
    out: List[Finding] = []
    try:
        r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(video), "-filter_complex",
                            "[0:v]select='gt(scene,0.3)',metadata=print:file=-[v];[0:a]ebur128=peak=true[a]",
                            "-map", "[v]", "-map", "[a]", "-f", "null", "-"], capture_output=True, text=True, timeout=600)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return [("⚠️", "成片量測", f"ffmpeg 失敗：{exc}")]
    text = r.stdout + r.stderr
    cuts = len(re.findall(r"lavfi\.scene_score", text))
    dur_m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", text)
    dur = int(dur_m.group(1)) * 3600 + int(dur_m.group(2)) * 60 + float(dur_m.group(3)) if dur_m else 0.0
    if dur:
        out.append(("ℹ️", "實測剪點", f"【measured】場景變化 {cuts} 次／{dur:.1f} 秒，平均鏡長約 {dur / (cuts + 1):.2f} 秒（scene>0.3）"))
    lufs = re.findall(r"I:\s+(-?[\d.]+) LUFS", text)
    peak = re.findall(r"Peak:\s+(-?[\d.]+) dBFS", text)
    if lufs:
        i = float(lufs[-1])
        tp = float(peak[-1]) if peak else None
        ok = LUFS_RANGE[0] <= i <= LUFS_RANGE[1] and (tp is None or tp <= TP_MAX)
        out.append(("✅" if ok else "⚠️", "實測響度",
                    f"【measured】整合響度 {i:.1f} LUFS（豎屏串流建議 {LUFS_RANGE[0]:.0f}～{LUFS_RANGE[1]:.0f}；送審母帶另出 −23）"
                    + (f"、峰值 {tp:.1f} dBFS（上限 {TP_MAX:.0f}）" if tp is not None else "")))
    return out


def review(project_dir: Path, episode: str, video: Optional[Path] = None) -> List[Finding]:
    shots = load_timeline(project_dir, episode)
    plan = plan_for_episode(load_json(project_dir / "edit" / "full-plan.json"), episode)
    if not shots and not plan:
        return [("⚠️", "輸入", f"找不到 timeline-plan-{episode.lower()}.csv 或 edit/full-plan.json，無法檢查")]
    out: List[Finding] = [("ℹ️", "輸入", f"timeline-plan {len(shots)} 鏡" + ("、edit/full-plan.json" if plan else "（沒有 full-plan，用分鏡時間）"))]
    out.append(check_hook(shots, plan))
    out += check_rhythm(shots)
    out += check_captions(shots, plan)
    out.append(check_speech_overlap(plan, shots))
    for f in (check_cut_straddle(plan), check_ramps(project_dir, episode)):
        if f:
            out.append(f)
    out.append(check_fatigue(shots))
    out.append(check_breath(plan))
    out.append(check_tail(shots, plan))
    out.append(("ℹ️", "配樂讓位", "edit/full-plan.json 目前沒有配樂軌，配樂 ducking（人聲期間壓 6–12 dB）與進場點略過，請 Agent 聽成片判斷"))
    out.append(("ℹ️", "高潮蓄力", "分鏡沒有標高潮，蓄力段（高潮前 3–8 秒鏡長 ≥ 高潮段 ×1.3）請 Agent 依 hamilton-action 模型 4 人工判斷"))
    if video:
        out += measure_video(video)
    return out


def render(episode: str, lenses: List[str], findings: List[Finding]) -> str:
    body = "\n".join(f"| {m} | {k} | {d} |" for m, k, d in findings)
    lens_lines = "\n".join(f"- `{k}`：{LENSES[k]}" for k in lenses)
    return (f"# 剪輯 lens：Stage 7 · {episode}\n\n"
            "> 只給建議、不擋關。由 `scripts/craft/edit_review.py` 產生；技巧與數值見 "
            "`references/edit/manju-editing-playbook.md`。\n\n"
            f"本次套用的 lens：\n{lens_lines}\n\n"
            "## 確定性檢查\n\n| 結果 | 項目 | 說明 |\n|---|---|---|\n" + body + "\n"
            "\n## Agent 審查\n\n（請 Agent 看過成片或草剪後，依上列 lens 的心智模型補剪點、聲音與節奏建議）\n")


def run(project_dir: Path, episode: str, lenses: Optional[List[str]] = None, video: Optional[Path] = None,
        out: Optional[Path] = None) -> Path:
    lenses = lenses or list(LENSES)
    target = out or project_dir / "review" / "craft" / f"stage-7-{LENS}-{episode.lower()}.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(keep_agent_section(render(episode, lenses, review(project_dir, episode, video)), target), encoding="utf-8")
    return target


def self_test() -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp)
        rows = ["shot_id,start,end,duration,video_file,subtitle,narration,speaker,foley",
                "EP01-S01-a-SH01,0.0,4.0,4.0,,,,,風聲",
                "EP01-S01-a-SH02,4.0,8.5,4.5,,這是一句非常非常非常非常長的台詞會超過十五字,,A,",
                "EP01-S01-b-SH01,0.0,4.0,4.0,,短,,B,",
                "EP01-S01-b-SH02,4.0,10.0,6.0,,,,,遠景",
                "EP01-S02-a-SH01,0.0,4.0,4.0,,,,,收尾"]
        (p / "timeline-plan-ep01.csv").write_text("\n".join(rows), encoding="utf-8")
        (p / "videos").mkdir()
        (p / "videos" / "speed-ramps.json").write_text(json.dumps({"segments": {
            "EP01-S01-a": {"status": "rendered"}, "EP01-S01-b": {"status": "proposed"}}}), encoding="utf-8")
        t = run(p, "EP01").read_text(encoding="utf-8")
        ok1 = all(k in t for k in ["第一句台詞／旁白在 4.0 秒", "超過 15 字", "無聲長鏡", "EP01-S01-b-SH02",
                                    "未產檔或驗證失敗：EP01-S01-b", "最後一句結束後還有",
                                    "句尾留白", "最長的連續快剪累計 0.0 秒"])
        (p / "edit").mkdir()
        plan = {"segments": [{"id": "EP01-S01-a", "start": 0, "duration": 8.5}, {"id": "EP01-S01-b", "start": 8.5, "duration": 10}],
                "captions": [{"start": 1.0, "end": 9.5, "text": "跨段的一句台詞"}],
                "voices": [{"key": "v1", "start": 5.0}], "total": 18.5}
        (p / "edit" / "full-plan.json").write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
        t2 = run(p, "EP01").read_text(encoding="utf-8")
        ok2 = all(k in t2 for k in ["第一句台詞／旁白在 1.0 秒", "1 句橫跨段落剪點", "1 句畫外配音落在畫內台詞中間", "1 段最後一句貼著段尾"])
    ok = ok1 and ok2
    print("edit_review self-test:", "PASS" if ok else "FAIL")
    return ok


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="階段 7 剪輯 lens（murch-cut／hamilton-action，建議性，不擋關）")
    ap.add_argument("--project-dir", type=Path)
    ap.add_argument("--episode", default="EP01")
    ap.add_argument("--lens", choices=[*LENSES, "all"], default="all")
    ap.add_argument("--video", type=Path, help="選用：成片或草剪 mp4，量測剪點與響度（measured）")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if a.self_test:
        return 0 if self_test() else 1
    if not a.project_dir:
        ap.error("需要 --project-dir")
    lenses = list(LENSES) if a.lens == "all" else [a.lens]
    print(run(a.project_dir, a.episode, lenses, a.video, a.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
