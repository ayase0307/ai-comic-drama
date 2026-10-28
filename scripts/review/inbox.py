#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""決策收件匣：一頁只列「現在需要使用者決定的事」，取代逐階段攤開全部資料的審核頁。

為什麼：舊審核頁每頁都把 hash、幾十條警告、上萬字英文 prompt、整面影片牆攤開，
使用者看不出到底要決定什麼；實際案子三天裡真正要人拍板的事大約只有 20 件。
原則是「人只看例外」：

  1. 需要你決定（0–5 張卡）：一句話問題、會影響什麼、我的建議、2–3 個選項
     （點了就複製回覆文字）、一張證據縮圖。依會不會擋下一步排序；超過 5 張把後面的併成一張。
     版面與欄位規格見 references/review-page-spec.md（validate_model 檢查）。
  2. 你已經決定的（收合）：decisions.json 的定案、使用者裁示過的段落、人工核准紀錄。
  3. 我自動處理了 N 件事（收合）：依驗收政策自動通過的段、政策可接受的技術 QA、自動核准。
  4. 原始資料（只放連結，不內嵌）。

資料來源只有：
  * decisions.json（政策與定案）
  * review/verdicts.json（逐段結論；由 verdicts.classify 套驗收政策）
  * review/project-state.json（階段狀態、核准／覆寫／自動核准紀錄）
  * 選用：videos/qa-report.json（技術 QA）、videos/*.mp4（抽 10 幀條，需要 ffmpeg）
  * 例外：階段 7 的「待定音色角色」需要知道誰有畫外台詞，只讀 segments-ep*.json 的
    external_narration[].speaker（不讀 prompt）。

輸出 review/inbox.html（standalone，縮圖以 webp 內嵌，手機優先，目標 < 5 MB）與 review/inbox.json。
用法：
  h3d inbox --root <專案>
  python scripts/build_stage_review.py --project-dir <專案> --inbox
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import html
import io
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
for candidate in (str(SCRIPTS_DIR), str(SCRIPTS_DIR / "storyboard")):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

import decisions as decisions_mod  # noqa: E402
import doc_card  # noqa: E402
import project_state as ps  # noqa: E402
import verdicts as verdicts_mod  # noqa: E402

STAGE_SHORT = ["定調", "改編", "設定圖", "劇本", "分鏡", "提示詞", "影片", "配音剪輯"]
SIZE_BUDGET = 4_500_000          # 內嵌圖片總預算（bytes）；超過就不再內嵌 10 幀條
MAX_GROUP_WARN = 3               # ⚠️ 超過這個數量就併成一張卡
IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp")
VIDEO_SUFFIXES = (".mp4", ".mov", ".webm")
CACHE_DIRNAME = "_inbox_cache"
STYLE14_SHEET = SCRIPTS_DIR.parent / "assets" / "styles" / "sheet-14-xianxia-cinematic-semireal.jpg"


# ------------------------------------------------------------------ 讀資料
def _read_json(path: Path) -> Optional[Any]:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None


def _parse_time(raw: Any) -> Tuple[str, str]:
    """回傳 (排序鍵 ISO-ish, 顯示用 MM/DD HH:MM)。認得 ISO 與 `Wed 2026-10-21 4:55 PM CST` 這類寫法。"""
    text = str(raw or "")
    try:
        parsed = datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone()  # 帶時區的 ISO（常是 UTC）換成本機時區顯示
        if "T" in text or " " in text.strip():
            return parsed.strftime("%Y-%m-%dT%H:%M"), parsed.strftime("%m/%d %H:%M")
        return parsed.strftime("%Y-%m-%dT00:00"), parsed.strftime("%m/%d")
    except ValueError:
        pass
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", text)
    if not m:
        return "", text
    y, mo, d = m.groups()
    rest = text[m.end():]
    t = re.search(r"(\d{1,2}):(\d{2})(?::\d{2})?\s*(AM|PM|am|pm)?", rest)
    hh, mm = 0, 0
    if t:
        hh, mm = int(t.group(1)), int(t.group(2))
        ampm = (t.group(3) or "").upper()
        if ampm == "PM" and hh < 12:
            hh += 12
        if ampm == "AM" and hh == 12:
            hh = 0
        return f"{y}-{mo}-{d}T{hh:02d}:{mm:02d}", f"{mo}/{d} {hh:02d}:{mm:02d}"
    return f"{y}-{mo}-{d}T00:00", f"{mo}/{d}"


def current_stage(state: Dict[str, Any]) -> int:
    """第一個狀態不是 approved 的階段（只看狀態，不重算 hash；正式判斷交給 h3d next）。"""
    for i in range(8):
        if state["stages"][ps.stage_key(i)].get("status") != "approved":
            return i
    return 7


def narration_speakers(root: Path) -> List[str]:
    """有畫外台詞（要外部配音）的角色 id；只讀 segments-ep*.json 的 external_narration。"""
    found: List[str] = []
    for path in sorted(Path(root).glob("segments-ep*.json")):
        raw = _read_json(path)
        if raw is None:
            continue
        items = raw if isinstance(raw, list) else raw.get("segments", [raw])
        for seg in items:
            if not isinstance(seg, dict):
                continue
            narration = seg.get("external_narration") or []
            if isinstance(narration, dict):
                narration = [narration]
            for line in narration:
                if isinstance(line, dict):
                    who = line.get("speaker") or line.get("character_id")
                    if who and who not in found:
                        found.append(str(who))
    return found


def segment_order(root: Path) -> List[str]:
    ids: List[str] = []
    for path in sorted(Path(root).glob("segments-ep*.json")):
        raw = _read_json(path)
        if raw is None:
            continue
        items = raw if isinstance(raw, list) else raw.get("segments", [raw])
        ids.extend(str(i["segment_id"]) for i in items if isinstance(i, dict) and i.get("segment_id"))
    return ids


# ------------------------------------------------------------------ 圖片
def _pil():
    try:
        from PIL import Image  # noqa: F401
        return Image
    except ImportError:  # pragma: no cover - 沒裝 Pillow 時只是沒有縮圖
        return None


def image_b64(path: Path, width: int = 760, quality: int = 60) -> Optional[str]:
    Image = _pil()
    if Image is None or not path.is_file():
        return None
    try:
        img = Image.open(path).convert("RGB")
    except Exception:
        return None
    if img.width > width:
        img = img.resize((width, round(img.height * width / img.width)), Image.LANCZOS)
    buf = io.BytesIO()
    try:
        img.save(buf, "WEBP", quality=quality, method=6)
        mime = "image/webp"
    except Exception:  # pragma: no cover - Pillow 沒有 webp 時退回 jpeg
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=quality)
        mime = "image/jpeg"
    return f"data:{mime};base64," + base64.b64encode(buf.getvalue()).decode()


def strip10(root: Path, video: Path) -> Optional[Path]:
    """從影片均勻抽 10 幀排成 5×2 一張；快取在 review/_inbox_cache/（影片變了就重做）。"""
    if not video.is_file() or not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        return None
    stat = video.stat()
    key = hashlib.sha1(f"{video.resolve()}|{stat.st_size}|{int(stat.st_mtime)}".encode("utf-8")).hexdigest()[:10]
    cache = Path(root) / "review" / CACHE_DIRNAME
    cache.mkdir(parents=True, exist_ok=True)
    out = cache / f"strip10-{video.stem}-{key}.jpg"
    if out.is_file():
        return out
    try:
        dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                    "-of", "csv=p=0", str(video)], capture_output=True, text=True,
                                   timeout=60).stdout.strip())
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(video), "-vf",
                        f"fps=10/{max(dur, 0.1):.3f},scale=192:-1,tile=5x2:padding=2:color=0x0c0d10",
                        "-frames:v", "1", "-q:v", "4", str(out)], check=True, timeout=120)
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    return out if out.is_file() else None


# ------------------------------------------------------------------ 卡片
def _reply(subject: str, text: str) -> str:
    return f"{subject}：{text}"


def _issue_text(codes: List[str]) -> str:
    return "、".join(decisions_mod.ISSUE_CODES.get(c, c).split("（")[0] for c in codes)


def _evidence_paths(root: Path, row: Dict[str, Any], sid: str) -> List[Path]:
    raw = row.get("evidence")
    items = raw if isinstance(raw, list) else ([raw] if raw else [])
    paths = [Path(root) / str(p) if not Path(str(p)).is_absolute() else Path(str(p)) for p in items]
    paths = [p for p in paths if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES + VIDEO_SUFFIXES]
    if not paths:
        tile = Path(root) / "videos" / "qa" / "tiles" / f"{sid}.jpg"
        if tile.is_file():
            paths.append(tile)
    video = Path(root) / "videos" / f"{sid}.mp4"
    if not paths and video.is_file():
        paths.append(video)
    return paths


_TAG_RE = re.compile(r"^[\s✅⚠️❌✖️\ufe0f]*(（[^）]{0,8}）)?\s*(【[^】]{0,40}】\s*)*")


def clean_reason(text: str) -> str:
    """去掉開頭的 ✅⚠️❌ 與【時間標籤】（舊格式結論常見），留下人話。"""
    return _TAG_RE.sub("", str(text or "")).strip() or str(text or "").strip()


def short_title(text: str, limit: int = 46) -> str:
    """卡片標題只要一句話：取第一個句號／分號前，最多 limit 字。"""
    body = clean_reason(text)
    first = re.split(r"[。；;]", body, maxsplit=1)[0].strip() or body
    return first if len(first) <= limit else first[: limit - 1] + "…"


def _verdict_card(root: Path, sid: str, row: Dict[str, Any], raw: Dict[str, Any]) -> Dict[str, Any]:
    fail = row["effective"] == "fail"
    issues = row.get("issues") or row.get("qa_codes") or []
    reason = clean_reason(raw.get("reason") or row["reason"])
    title = f"{sid}：{short_title(reason)}"
    if fail:
        impact = raw.get("impact") or (
            f"依驗收政策「{_issue_text(issues)}」要重跑；不處理會擋住階段 6 核准。" if issues
            else "判定為不通過；不處理會擋住階段 6 核准。")
        recommendation = raw.get("recommendation") or "改提示詞後只重跑這一段（不是只換 seed）。"
        options = raw.get("options") or [
            {"label": "改提示詞重跑", "reply": _reply(sid, "改提示詞重跑這一段")},
            {"label": "先當通過", "reply": _reply(sid, "先當通過，不重跑")},
            {"label": "先放著", "reply": _reply(sid, "先放著，成片前再決定")},
        ]
        blocking, label = 2, "擋階段 6 核准"
        if_ignored = raw.get("if_ignored") or "這段會帶著問題留在片裡；階段 6 不能核准。"
    else:
        impact = raw.get("impact") or "依你的驗收標準不算大錯，不擋核准；只是成片裡可能看得出來。"
        recommendation = raw.get("recommendation") or "維持暫過，不重跑。"
        options = raw.get("options") or [
            {"label": "維持暫過", "reply": _reply(sid, "維持暫過，不重跑")},
            {"label": "改提示詞重跑", "reply": _reply(sid, "改提示詞重跑一次")},
        ]
        blocking, label = 5, "不擋"
        if_ignored = raw.get("if_ignored") or "維持暫過，成片照用這段。"
    return {
        "id": f"D6-{sid}", "kind": "verdict", "stage": 6, "segment": sid,
        "title": title, "finding": reason if reason != short_title(reason) else "",
        "impact": impact, "recommendation": recommendation, "options": options, "if_ignored": if_ignored,
        "blocking": blocking, "blocking_label": label,
        "evidence_paths": _evidence_paths(root, raw or row, sid),
        "evidence_caption": f"{sid} 證據",
        "links": [{"label": "播放這段", "href": f"videos/{sid}.mp4"}]
        if (Path(root) / "videos" / f"{sid}.mp4").is_file() else [],
        "source": "review/verdicts.json" + (f"（{_issue_text(issues)}）" if issues else ""),
    }


def _warn_group_card(root: Path, rows: List[Tuple[str, Dict[str, Any], Dict[str, Any]]]) -> Dict[str, Any]:
    sids = [sid for sid, _, _ in rows]
    brief = "；".join(f"{sid} {short_title(raw.get('reason') or row['reason'], 18)}" for sid, row, raw in rows[:3])
    evidence: List[Path] = []
    for sid, row, raw in rows[:3]:
        evidence.extend(_evidence_paths(root, raw or row, sid)[:1])
    subject = f"附註 {len(sids)} 段"
    return {
        "id": "D6-warn-group", "kind": "verdict_group", "stage": 6,
        "segment": "、".join(sids[:4]) + ("…" if len(sids) > 4 else ""),
        "title": f"{len(sids)} 段「附註暫過」：{brief}",
        "impact": "依你的驗收標準都不算大錯，不擋核准；只有眼尖的觀眾可能看出來。",
        "recommendation": "全部維持暫過，不重跑；剪輯時太顯眼的再縮短。",
        "options": [
            {"label": "全部維持暫過", "reply": _reply(subject, "全部維持暫過，不重跑")},
            {"label": "逐段給我看", "reply": _reply(subject, "逐段拆成卡片給我看")},
        ],
        "if_ignored": "全部維持暫過，成片照用。",
        "blocking": 5, "blocking_label": "不擋",
        "evidence_paths": evidence, "evidence_caption": "／".join(sids[:3]),
        "links": [], "source": "review/verdicts.json",
        "segments": sids,
    }


def _review_page_link(root: Path, stage: int) -> List[Dict[str, str]]:
    pages = sorted((Path(root) / "review").glob(f"stage-{stage}-*.html"))
    return [{"label": "舊版審核頁（除錯用）", "href": f"review/{pages[0].name}"}] if pages else []


# ------------------------------------------------------------------ 階段 2／4／5 例外卡
FAIL_DISPOSITION = re.compile(r"不通過|未通過|退回|重生|淘汰|\bfail|\breject", re.I)
FAIL_APPROVAL = {"rejected", "needs_regen", "retake", "failed", "agent_rejected"}
MIXED_FACE_CODE = "mixed_face_refs"  # decisions.ISSUE_CODES；寫進 acceptance_policy.accept 即接受


def reference_manifest(root: Path) -> List[Dict[str, Any]]:
    """assets/reference-manifest.json 的 assets（讀不到回空清單）。"""
    data = _read_json(Path(root) / "assets" / "reference-manifest.json")
    items = data.get("assets") if isinstance(data, dict) else data
    return [a for a in items if isinstance(a, dict)] if isinstance(items, list) else []


def _asset_label(asset: Dict[str, Any]) -> str:
    return str(asset.get("display_name_zh") or asset.get("stable_id") or asset.get("entry_id") or asset.get("target_path") or "?")


def _asset_failed(asset: Dict[str, Any]) -> bool:
    if str(asset.get("approval_status") or "").strip().lower() in FAIL_APPROVAL:
        return True
    disposition = str(asset.get("review_disposition") or "")
    # 「自檢通過（有瑕疵）」不算不通過；只有明講不通過／退回才算
    return bool(FAIL_DISPOSITION.search(disposition)) and "通過（" not in disposition.replace("不通過（", "")


def _asset_path(root: Path, asset: Dict[str, Any]) -> Optional[Path]:
    raw = asset.get("target_path") or asset.get("path")
    if not raw:
        return None
    path = ps._resolve(root, raw)
    return path if path.is_file() else None


def stage2_sheet_paths(root: Path, limit: int = 6) -> List[Path]:
    """階段 2 核准卡要內嵌的設定圖：manifest 的角色優先，沒有 manifest 就抓 images/*sheet*。"""
    manifest = reference_manifest(root)
    ordered = sorted(manifest, key=lambda a: (str(a.get("asset_type")) != "character", not a.get("required", True)))
    paths = [p for p in (_asset_path(root, a) for a in ordered) if p]
    if not paths:
        paths = sorted(p for p in (Path(root) / "images").glob("*sheet*")
                       if p.suffix.lower() in IMAGE_SUFFIXES and "_trials" not in p.parts)
    seen: List[Path] = []
    for p in paths:
        if p not in seen:
            seen.append(p)
    return seen[:limit]


def stage2_cards(root: Path) -> List[Dict[str, Any]]:
    """manifest 標了自檢不通過的設定圖 → 卡（#22）。"""
    failed = [a for a in reference_manifest(root) if _asset_failed(a)]
    if not failed:
        return []
    names = "、".join(_asset_label(a) for a in failed[:4]) + ("…" if len(failed) > 4 else "")
    notes = [n for a in failed for n in (a.get("technical_review_notes") or [])[:1]]
    return [{
        "id": "D2-asset-selfcheck", "kind": "asset_review", "stage": 2, "segment": f"{len(failed)} 張設定圖",
        "title": f"{len(failed)} 張設定圖 Agent 自檢不通過：{names}",
        "finding": "；".join(str(a.get("review_disposition") or "") for a in failed[:3]),
        "impact": "設定圖是後面所有分鏡與影片的臉和服裝來源；帶著瑕疵核准，整季都會沿用。",
        "recommendation": "先重生成再給你看臉；你看過覺得能用，也可以直接接受。"
                          + (f" 自檢備註：{notes[0]}" if notes else ""),
        "options": [{"label": "照建議重生成", "reply": f"階段 2：{names} 重生成後再給我看"},
                    {"label": "我看過，可以用", "reply": f"階段 2：{names} 我看過，接受目前版本"}],
        "if_ignored": "設定圖維持現狀，階段 2 不能核准，後面全部停著。",
        "blocking": 1, "blocking_label": "擋階段 2 核准",
        "evidence_paths": [p for p in (_asset_path(root, a) for a in failed) if p][:3],
        "evidence_caption": "自檢不通過的設定圖", "links": [], "source": "assets/reference-manifest.json"}]


def stage1_cards(root: Path) -> List[Dict[str, Any]]:
    """事件交代完整性：被壓縮／跳過／交代不全的事件要使用者決定（劇情走樣，必須上頂層）。"""
    if not (Path(root) / "adapt" / "source.json").is_file():
        return []
    adapt_dir = str(SCRIPTS_DIR / "adapt")
    if adapt_dir not in sys.path:
        sys.path.insert(0, adapt_dir)
    from event_coverage import project_coverage  # noqa: E402
    try:
        coverage = project_coverage(Path(root))
    except (OSError, ValueError, KeyError):
        return []
    pending = list((coverage or {}).get("needs_decision") or [])
    if not pending or not coverage.get("has_adaptation"):  # 還沒有改編稿場景時只是清單，不是決定
        return []
    missing = list(coverage.get("must_keep_missing") or [])
    shown = "、".join(pending[:6]) + ("…" if len(pending) > 6 else "")
    return [{
        "id": "D1-event-coverage", "kind": "event_coverage", "stage": 1, "segment": f"{len(pending)} 個事件",
        "title": f"{len(pending)} 個事件被壓縮、跳過或交代不全，要補鏡頭還是接受",
        "finding": shown + (f"；MUST_KEEP 完全沒交代：{'、'.join(missing[:4])}" if missing else ""),
        "impact": "觀眾會看不懂起因或結果；階段 1 核准後才進設定圖與劇本，越晚補越貴。",
        "recommendation": "照建議補交代鏡頭（起因→經過→結果）；確定要刪的再告訴我接受壓縮。",
        "options": [{"label": "照建議補交代鏡頭", "reply": f"階段 1：{shown} 補交代鏡頭"},
                    {"label": "接受目前壓縮", "reply": f"階段 1：{shown} 接受目前的壓縮／跳過"}],
        "if_ignored": "這些事件照現在的交代程度進劇本；階段 1 不能核准。",
        "blocking": 1 if missing else 2, "blocking_label": "擋階段 1 核准", "evidence_paths": [],
        "links": _review_page_link(root, 1), "source": "adapt/source.json（event_coverage.py）"}]


def _panel_evidence(root: Path, errors: List[str]) -> List[Path]:
    rejected_dir = Path(root) / "panels" / "_rejected"
    found = sorted(p for p in rejected_dir.glob("*.png")) if rejected_dir.is_dir() else []
    return found[:3]


def stage4_cards(root: Path) -> List[Dict[str, Any]]:
    """缺構圖、自檢退回 → 卡（#44）。"""
    _, errors = ps.stage4_artifacts(root)
    if not errors:
        return []
    rejected = [e for e in errors if "自檢退回" in e]
    missing = [e for e in errors if e not in rejected]
    parts = []
    if missing:
        parts.append(f"{len(missing)} 鏡缺構圖")
    if rejected:
        parts.append(f"{len(rejected)} 鏡自檢退回")
    shots = [e.split(":", 1)[0] for e in errors]
    return [{
        "id": "D4-sketch-gaps", "kind": "stage_gap", "stage": 4, "segment": f"{len(errors)} 鏡",
        "title": f"階段 4 還有 {'、'.join(parts)}，不能送核准",
        "finding": "、".join(shots[:6]) + ("…" if len(shots) > 6 else ""),
        "impact": "每一鏡都要有對應構圖才能進提示詞編譯；退回的圖不會被認領。",
        "recommendation": "我先補畫缺的鏡、重畫退回的鏡，齊了再出核准卡給你。",
        "options": [{"label": "照建議補齊", "reply": "階段 4：照建議補齊構圖，齊了再給我核"},
                    {"label": "先給我看退回的圖", "reply": "階段 4：先把自檢退回的構圖給我看"}],
        "if_ignored": "階段 4 不能核准，提示詞編譯停在這裡。",
        "blocking": 2, "blocking_label": "擋階段 4 核准",
        "evidence_paths": _panel_evidence(root, rejected),
        "evidence_caption": "自檢退回的構圖" if rejected else "", "links": [],
        "source": "layer2/layer2-*.json＋panels/"}]


def _segment_items(path: Path) -> List[Dict[str, Any]]:
    raw = _read_json(path)
    items = raw if isinstance(raw, list) else (raw.get("segments", [raw]) if isinstance(raw, dict) else [])
    return [i for i in items if isinstance(i, dict)]


def mixed_face_segments(root: Path) -> List[str]:
    """同段掛 >1 張可辨識人臉角色參考圖的段（與 audit 的混臉警告同一規則）。"""
    out = []
    for path in sorted(Path(root).glob("segments-ep*.json")):
        for seg in _segment_items(path):
            refs = [r for r in (seg.get("reference_images") or []) if isinstance(r, dict)]
            faces = [r for r in refs if r.get("type") in ("character", "role", "actor")
                     and r.get("reference_view") != "non_face"]
            if len(faces) > 1:
                out.append(str(seg.get("segment_id") or path.name))
    return out


def stage5_cards(root: Path, accept: set) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """缺參考圖、混臉 → 卡（#62）；混臉若已寫進驗收政策 accept（MIXED_FACE）就改列自動處理。"""
    cards: List[Dict[str, Any]] = []
    auto: List[Dict[str, Any]] = []
    errors = ps.stage_validation_errors(root, 5)
    if errors:
        segs = sorted({e.split(":", 1)[0] for e in errors})
        cards.append({
            "id": "D5-missing-refs", "kind": "stage_gap", "stage": 5, "segment": f"{len(segs)} 段",
            "title": f"{len(segs)} 段提示詞缺參考圖或參考圖檔不存在",
            "finding": "；".join(errors[:3]) + ("…" if len(errors) > 3 else ""),
            "impact": "缺參考圖的段送件後臉、場景會漂；不補齊不能核准階段 5。",
            "recommendation": "缺的場景母版或設定圖我先補生成，補完重編這幾段。",
            "options": [{"label": "照建議補圖重編", "reply": "階段 5：照建議補參考圖並重編"},
                        {"label": "先列清單給我", "reply": "階段 5：先把缺圖清單給我看"}],
            "if_ignored": "階段 5 不能核准，這幾段不會送件。",
            "blocking": 2, "blocking_label": "擋階段 5 核准", "evidence_paths": [], "links": [],
            "source": "segments-ep*.json reference_images"})
    mixed = mixed_face_segments(root)
    if mixed and MIXED_FACE_CODE in accept:
        auto.append({"text": f"{len(mixed)} 段同段多張臉，依驗收政策可接受（{MIXED_FACE_CODE}）",
                     "detail": "、".join(mixed[:10]), "source": "segments-ep*.json＋decisions.json acceptance_policy"})
    elif mixed:
        cards.append({
            "id": "D5-mixed-face", "kind": "mixed_face", "stage": 5, "segment": f"{len(mixed)} 段",
            "title": f"{len(mixed)} 段同段掛了多張人臉參考圖（混臉風險）",
            "finding": "、".join(mixed[:6]) + ("…" if len(mixed) > 6 else ""),
            "impact": "H3 會把多張臉平均成一張；對手戲要兩人同框時才值得冒這個險。",
            "recommendation": "非必要同框的段改一臉＋背影無臉裁切；確實要兩人露臉的段由你接受。",
            "options": [{"label": "照建議改一臉", "reply": "階段 5：混臉段改成一張臉＋無臉裁切"},
                        {"label": "我接受這些段", "reply": f"階段 5：接受混臉風險，驗收政策 accept 加 {MIXED_FACE_CODE}"}],
            "if_ignored": "階段 5 不能核准；硬送的話這幾段很可能要重跑（浪費生成）。",
            "blocking": 2, "blocking_label": "擋階段 5 核准", "evidence_paths": [], "links": [],
            "source": "segments-ep*.json reference_images"})
    return cards, auto


def doc_decision_cards(root: Path) -> List[Dict[str, Any]]:
    """每條文件待決一張卡；使用者回覆後 Agent 用 h3d doc resolve 移進修訂紀錄，卡就消失。"""
    cards = []
    for item in doc_card.doc_decisions(root):
        where = f"{item['path']} 第 {item['number']} 條"
        choices = [c for c in [item.get("recommend"), *item.get("alternatives", [])] if c]
        options = [{"label": c if i else f"{c}（建議）", "reply": f"{where}：{c}"} for i, c in enumerate(choices)]
        cards.append({
            "id": f"D{item['stage']}-doc-{item['path']}-{item['number']}", "kind": "doc", "stage": item["stage"],
            "segment": item["path"], "title": item["question"],
            "impact": f"{item['path']} 的狀態卡等你決定這一條，決定前這份文件不能核准。",
            "recommendation": f"建議：{item['recommend']}" if item.get("recommend") else "Agent 沒有給建議，請直接回覆。",
            "options": options + [{"label": "先放著", "reply": f"{where}：先放著"}],
            "if_ignored": f"階段 {item['stage']} 不能核准。",
            "blocking": 2, "blocking_label": "擋本階段核准", "evidence_paths": [], "links": [],
            "source": f"{item['path']} 狀態卡「要你決定」"})
    return cards


def build_cards(root: Path, *, state: Optional[Dict[str, Any]] = None,
                decisions_data: Optional[Dict[str, Any]] = None,
                classified: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """回傳 {"open": [...], "decided": [...], "auto": [...], "notes": [...]}（不含圖片）。"""
    root = Path(root)
    state = state if state is not None else ps.load_state(root)
    try:
        decisions_data = decisions_data if decisions_data is not None else decisions_mod.load(root)
        decisions_error = None
    except decisions_mod.DecisionError as exc:
        decisions_data, decisions_error = decisions_mod.empty_decisions(), str(exc)
    verdict_raw: Dict[str, Any] = {}
    try:
        verdict_raw = verdicts_mod.load(root).get("segments", {})
        classified = classified if classified is not None else verdicts_mod.classify(root)
        verdict_error = None
    except verdicts_mod.VerdictError as exc:
        classified, verdict_error = {"segments": {}, "counts": {}, "policy": {}, "policy_is_decided": False}, str(exc)

    cur = current_stage(state)
    stages = state["stages"]
    open_cards: List[Dict[str, Any]] = []
    decided: List[Dict[str, Any]] = []
    auto: List[Dict[str, Any]] = []
    notes: List[str] = []

    if decisions_error:
        open_cards.append({
            "id": "D-decisions-broken", "kind": "broken", "stage": cur, "segment": "decisions.json",
            "title": "decisions.json 格式錯誤，定案讀不到", "impact": decisions_error,
            "recommendation": "用 h3d decide 重寫有問題的定案（不要手改）。",
            "options": [{"label": "照建議修", "reply": "decisions.json：照建議用 h3d decide 重寫"},
                        {"label": "先放著", "reply": "decisions.json：先放著"}],
            "if_ignored": "所有定案都讀不到，每個階段都不能往下。",
            "blocking": 0, "blocking_label": "擋全部", "evidence_paths": [], "links": [],
            "source": "decisions.json"})
    if verdict_error:
        notes.append(f"review/verdicts.json 無法使用：{verdict_error}")

    # 1) 目前階段還沒定案的規則
    for did in decisions_mod.missing_for_stage(root, cur):
        meta = decisions_mod.KNOWN_DECISIONS[did]
        if did == "style":
            rec = f"{decisions_mod.RECOMMENDED_STYLE}：真人骨相＋厚塗質地，10 集 115 段實證；仍可改選其他風格。"
            options = [{"label": "照建議（14 號）", "reply": f"{meta['label']}：照建議，用 {decisions_mod.RECOMMENDED_STYLE}"},
                       {"label": "看其他風格", "reply": f"{meta['label']}：給我看 styles.md 其他風格的樣圖再選"}]
        elif did == "acceptance_policy":
            rec = decisions_mod.default_rule(did, decisions_mod.RECOMMENDED_ACCEPTANCE_POLICY)
            options = [{"label": "照建議", "reply": f"{meta['label']}：照建議（{rec}）"},
                       {"label": "我另外定", "reply": f"{meta['label']}：我要改成 ____"}]
        else:
            rec = "照專案目前的設定（project.md）定案，之後全集鎖定。"
            options = [{"label": "照目前設定", "reply": f"{meta['label']}：照目前 project.md 的設定定案"},
                       {"label": "我另外指定", "reply": f"{meta['label']}：我要改成 ____"}]
        open_cards.append({
            "id": f"D{meta['required_by']}-decide-{did}", "kind": "decision", "stage": meta["required_by"],
            "segment": "全集", "title": f"「{meta['label']}」還沒定案",
            "impact": f"沒定案就不能往下；定案後編譯器、QA、收件匣都照它判斷（參考 {meta['reference']}）。",
            "recommendation": rec, "options": options, "blocking": 1, "blocking_label": "擋下一步",
            "if_ignored": f"「{meta['label']}」沒定案，階段 {meta['required_by']} 不能往下。",
            "evidence_paths": [STYLE14_SHEET] if did == "style" and STYLE14_SHEET.is_file() else [],
            "evidence_caption": "14 號樣圖：上＝設定圖，下＝H3 成片" if did == "style" else "",
            "links": [], "source": "decisions.json"})

    # 2) 階段 6：逐段結論的例外
    warn_rows: List[Tuple[str, Dict[str, Any], Dict[str, Any]]] = []
    unreviewed = 0
    for sid, row in classified.get("segments", {}).items():
        raw = verdict_raw.get(sid, {})
        if row["effective"] == "unreviewed":
            unreviewed += 1
            continue
        if row.get("source") == "user":
            decided.append({
                "kind": "verdict", "stage": 6, "sort": _parse_time(raw.get("decided_at"))[0],
                "time": _parse_time(raw.get("decided_at"))[1] or "—",
                "title": f"{sid} 你的裁示",
                "decision": {"pass": "通過", "warn": "暫過", "fail": "重跑"}[row["effective"]],
                "detail": clean_reason(row["reason"]), "source": "review/verdicts.json"})
            continue
        if row["effective"] == "fail":
            open_cards.append(_verdict_card(root, sid, row, raw))
        elif row["effective"] == "warn":
            warn_rows.append((sid, row, raw))
    custom_warns = [r for r in warn_rows if r[2].get("options")]
    plain_warns = [r for r in warn_rows if not r[2].get("options")]
    for sid, row, raw in custom_warns:
        open_cards.append(_verdict_card(root, sid, row, raw))
    if len(plain_warns) > MAX_GROUP_WARN:
        open_cards.append(_warn_group_card(root, plain_warns))
    else:
        for sid, row, raw in plain_warns:
            open_cards.append(_verdict_card(root, sid, row, raw))
    for sid in segment_order(root):
        if sid not in classified.get("segments", {}) and (root / "videos" / f"{sid}.mp4").is_file():
            unreviewed += 1
    if unreviewed:
        notes.append(f"還有 {unreviewed} 段影片等我目視驗收（這是我的工作，不需要你）")

    # 3) 技術 QA 未過、但沒有逐段結論能說明的 → 要人決定要不要覆寫
    seg_rows = classified.get("segments", {})
    policy = classified.get("policy") or {}
    accept = set(policy.get("accept", []))
    tech_rows = {sid: r for sid, r in seg_rows.items() if r.get("qa_passed") is False and not r.get("qa_hard")}
    tech_codes = sorted({c for r in tech_rows.values() for c in r.get("qa_codes", [])})
    stage6 = stages[ps.stage_key(6)]
    has_override = bool((stage6.get("override") or {}).get("reason"))
    accepted_tech = [sid for sid, r in tech_rows.items() if set(r.get("qa_codes", [])) <= accept]
    if tech_rows and cur == 6 and not has_override:
        unexplained = [sid for sid in tech_rows if sid not in accepted_tech]
        if unexplained or not classified.get("policy_is_decided"):
            codes = _issue_text(tech_codes) or "未列原因"
            open_cards.append({
                "id": "D6-technical-override", "kind": "override", "stage": 6, "segment": "全集",
                "title": f"技術 QA 有 {len(tech_rows)} 段量化指標未過（{codes}），要以人工核准為準嗎",
                "impact": "技術 QA 只量時長、彩度、框線；低彩度場景常被誤判。不處理就不能核准階段 6。",
                "recommendation": "看過證據後以人工核准為準，並把這類問題寫進驗收政策的「可接受」，以後自動放行。",
                "options": [
                    {"label": "確認並寫成政策", "reply": f"階段 6：確認人工核准；{codes} 不算錯，寫進政策"},
                    {"label": "只確認這次", "reply": "階段 6：確認這次人工核准，政策先不改"},
                    {"label": "重跑技術 QA", "reply": "階段 6：先調 QA 閾值重跑，過了再核"},
                ],
                "if_ignored": "階段 6 不能核准，成片停在這裡。",
                "blocking": 2, "blocking_label": "擋階段 6 核准",
                "evidence_paths": [p for sid in list(tech_rows)[:2] for p in _evidence_paths(root, {}, sid)[:1]],
                "evidence_caption": "技術 QA 未過的段落", "links": [],
                "source": "videos/qa-report.json"})
    if accepted_tech:
        auto.append({"text": f"{len(accepted_tech)} 段技術 QA 量化指標未過，但屬驗收政策可接受（{_issue_text(sorted({c for s in accepted_tech for c in tech_rows[s].get('qa_codes', [])}))}）",
                     "detail": "例如低彩度場景被判 STYLE_BLEED_GRAYSCALE；依政策不重跑。",
                     "source": "videos/qa-report.json＋decisions.json acceptance_policy"})

    # 4) 階段 7：每個有畫外台詞的角色都要使用者定一次音色
    if cur >= 6:
        voiced = decisions_mod.voice_decisions(decisions_data)
        speakers = narration_speakers(root)
        missing_voice = [c for c in speakers if c not in voiced]
        if missing_voice:
            shown = "、".join(missing_voice[:8]) + ("…" if len(missing_voice) > 8 else "")
            open_cards.append({
                "id": "D7-voice-cast", "kind": "voice", "stage": 7, "segment": f"{len(missing_voice)} 個角色",
                "title": f"{len(missing_voice)} 個角色的配音音色還沒定案",
                "impact": f"畫外台詞要外部配音：{shown}。音色一經定案全集沿用，這是觀眾聽到的聲音。",
                "recommendation": "有畫內台詞的主角用自己的畫內聲複製；沒有畫內台詞的小角色用內建音色，我先切好試聽給你挑。",
                "options": [
                    {"label": "照建議＋給我試聽", "reply": "音色：主角用畫內聲複製、小角色用內建音色，先切試聽給我挑"},
                    {"label": "全部用畫內聲", "reply": "音色：全部角色都用畫內 H3 聲複製"},
                    {"label": "逐個角色問我", "reply": "音色：逐個角色附試聽問我"},
                ],
                "if_ignored": "這些角色的畫外台詞沒有聲音，階段 7 不能核准。",
                "blocking": 2, "blocking_label": "擋配音定案", "evidence_paths": [], "links": [],
                "source": "segments-ep*.json external_narration＋decisions.json voice:*",
                "characters": missing_voice})

    # 4b) 階段 1／2／4／5 的例外（事件交代不全、manifest 自檢不通過、缺構圖／退回、缺參考圖／混臉）
    if cur == 1:
        open_cards.extend(stage1_cards(root))
    elif cur == 2:
        open_cards.extend(stage2_cards(root))
    elif cur == 4:
        open_cards.extend(stage4_cards(root))
    elif cur == 5:
        s5_cards, s5_auto = stage5_cards(root, accept)
        open_cards.extend(s5_cards)
        auto.extend(s5_auto)

    # 4c) 階段文件狀態卡上的「要你決定」（references/document-standard.md §2）
    open_cards.extend(doc_decision_cards(root))

    # 5) 目前階段等使用者核准（只有在沒有其他同階段卡、也不符合自動核准時才出卡）
    cur_entry = stages[ps.stage_key(cur)]
    auto_stages, auto_item = decisions_mod.auto_approve_stages(decisions_data)
    same_stage = [c for c in open_cards if c["stage"] == cur]
    # 核准卡必須綁在 review_snapshot 上：快照過期時 approve_stage_detailed 一定會拒，不能讓使用者白答（#review-inbox-first）
    snapshot_ok = (cur_entry.get("status") == "awaiting_user_approval" and bool(cur_entry.get("review_snapshot"))
                   and cur_entry["review_snapshot"] == ps.stage_snapshot(root, cur))
    if cur_entry.get("status") == "awaiting_user_approval" and not same_stage:
        if cur in auto_stages:
            auto.append({"text": f"階段 {cur} 沒有未決卡，符合自動核准授權",
                         "detail": "執行 h3d approve --auto 會核准並記錄依據。",
                         "source": "decisions.json auto_approve"})
        elif not snapshot_ok:
            notes.append(f"階段 {cur} 的審核快照已過期或沒有綁定；我先重跑 build_stage_review.py --stage {cur} 重綁，再出核准卡")
        else:
            title = ps.STAGE_TITLES.get(cur, "")
            version = ps.snapshot_fingerprint(cur_entry["review_snapshot"])[:8]
            open_cards.append({
                "id": f"D{cur}-approve", "kind": "approval", "stage": cur, "segment": "全集",
                "title": f"階段 {cur}「{title}」等你核准",
                "impact": "核准後才會進下一階段；核准後內容再改，核准會自動失效。",
                "recommendation": "沒有例外要處理，建議通過。",
                "options": [{"label": "通過", "reply": f"階段 {cur}：通過（審核快照 {version}）"},
                            {"label": "要改", "reply": f"階段 {cur}：要改，____"}],
                "if_ignored": f"停在階段 {cur}，後面的階段都不會開始。",
                "blocking": 1, "blocking_label": "擋下一步", "evidence_paths": [],
                "review_snapshot": version,
                "links": _review_page_link(root, cur), "source": f"review/project-state.json（審核快照 {version}）"})
            if cur == 2:
                # 角色設定圖永遠要人看臉：卡片內嵌設定圖，不說「沒有例外」（#22）
                sheets = stage2_sheet_paths(root)
                flawed = [a for a in reference_manifest(root) if "瑕疵" in str(a.get("review_disposition") or "")]
                rec = "請看臉與服裝再決定；設定圖一經核准，全季沿用。"
                if flawed:
                    rec += f" Agent 自檢標了 {len(flawed)} 張有瑕疵：{'、'.join(_asset_label(a) for a in flawed[:3])}。"
                open_cards[-1].update({
                    "recommendation": rec, "evidence_paths": sheets, "max_evidence": len(sheets),
                    "evidence_caption": "本批設定圖（臉與服裝由你決定）",
                    "source": "review/project-state.json＋assets/reference-manifest.json"})

    # 已決定：decisions.json
    for item in decisions_data.get("decisions", []):
        src = item.get("source") or {}
        # 顯示使用者說那句話的日期；同一天多條時用 updated_at 排序
        key, shown = _parse_time(src.get("date") or item.get("updated_at"))
        if src.get("date") and item.get("updated_at", "").startswith(str(src.get("date"))):
            key, shown = _parse_time(item.get("updated_at"))
        label = decisions_mod.KNOWN_DECISIONS.get(item.get("id"), {}).get("label", item.get("id"))
        entry = {"kind": "decision", "stage": min(item.get("stages") or [0]), "sort": key, "time": shown or "—",
                 "title": label, "decision": item.get("rule", ""),
                 "detail": f"原話：「{src.get('quote', '')}」（{src.get('date', '')}）", "source": "decisions.json"}
        if src.get("by") == "user_delegated":
            auto.append({"text": f"依你的授權代為定案：{label}", "detail": item.get("rule", ""),
                         "source": "decisions.json（by=user_delegated）"})
        else:
            decided.append(entry)
    # 已決定：核准紀錄；自動核准算「自動處理」
    for i in range(8):
        entry = stages[ps.stage_key(i)]
        if entry.get("status") != "approved" or not entry.get("approved_at"):
            continue
        key, shown = _parse_time(entry.get("approved_at"))
        if entry.get("auto_approval"):
            basis = entry["auto_approval"]
            pol = "、".join(p.get("id", "") for p in basis.get("policy", []))
            auto.append({"text": f"階段 {i}「{STAGE_SHORT[i]}」依授權自動核准（{shown}）",
                         "detail": basis.get("summary") or f"依據政策：{pol}",
                         "source": "review/project-state.json auto_approval"})
            continue
        note = str(entry.get("user_note") or "")
        if entry.get("override"):
            note += f"（覆寫技術 QA {entry['override'].get('overridden_issue_count', 0)} 項：{entry['override'].get('reason', '')}）"
        decided.append({"kind": "approval", "stage": i, "sort": key, "time": shown or "—",
                        "title": f"階段 {i}「{STAGE_SHORT[i]}」", "decision": "核准",
                        "detail": note or "（無備註）", "source": "review/project-state.json"})

    # 自動處理：逐段結論
    counts = {"agent_pass": 0, "policy_warn": 0, "policy_fail": 0}
    for sid, row in seg_rows.items():
        if row["effective"] == "pass" and row.get("source") in ("agent", "policy"):
            counts["agent_pass"] += 1
        if row.get("source") == "policy" and row["effective"] == "warn":
            counts["policy_warn"] += 1
        if row.get("source") == "policy" and row["effective"] == "fail":
            counts["policy_fail"] += 1
    total = len(seg_rows)
    if total and counts["agent_pass"]:
        pol = "你定的" if classified.get("policy_is_decided") else "建議的（尚未定案）"
        auto.insert(0, {"text": f"{total} 段影片裡 {counts['agent_pass']} 段依{pol}驗收標準判通過",
                        "detail": (f"政策把 {counts['policy_warn']} 段從 fail 降為可接受、{counts['policy_fail']} 段升為要重跑；"
                                   f"你親自裁示的段落列在「你已經決定的」。"),
                        "source": "review/verdicts.json＋decisions.json acceptance_policy"})

    open_cards.sort(key=lambda c: (c["blocking"], c["stage"], c["id"]))
    decided.sort(key=lambda d: d.get("sort") or "", reverse=True)
    return {"open": open_cards, "decided": decided, "auto": auto, "notes": notes,
            "classified": classified}


def open_cards_for_stage(root: Path, stage: int) -> List[Dict[str, Any]]:
    """給 h3d approve --auto 用：該階段還有哪些未決卡（不含「等你核准」卡本身）。"""
    cards = build_cards(root)["open"]
    return [c for c in cards if (c["stage"] == stage or c["blocking"] == 0) and c["kind"] != "approval"]


# ------------------------------------------------------------------ 組資料模型
def collect(root: Path, *, images: bool = True, strips: str = "all", out_dir: Optional[Path] = None) -> Dict[str, Any]:
    root = Path(root).expanduser().resolve()
    out_dir = Path(out_dir) if out_dir else root / "review"
    state = ps.load_state(root)
    built = build_cards(root, state=state)
    cur = current_stage(state)
    budget = {"left": SIZE_BUDGET}

    def rel_link(project_rel: str) -> str:
        target = (root / project_rel).resolve()
        try:
            return Path(*([".."] * len(out_dir.resolve().relative_to(root).parts)), target.relative_to(root)).as_posix()
        except ValueError:
            return target.as_uri()

    def embed(path: Path, width: int = 760, quality: int = 60) -> Optional[str]:
        if not images:
            return None
        if path.suffix.lower() in VIDEO_SUFFIXES:
            path = strip10(root, path) or path
            if path.suffix.lower() in VIDEO_SUFFIXES:
                return None
        data = image_b64(path, width, quality)
        if data and len(data) <= budget["left"]:
            budget["left"] -= len(data)
            return data
        return None

    cards = []
    for card in built["open"]:
        item = {k: v for k, v in card.items() if k != "evidence_paths"}
        limit = int(card.get("max_evidence") or 3)
        thumbs = [embed(p, 520 if limit > 3 else 760) for p in card.get("evidence_paths", [])[:limit]]
        item["evidence_b64"] = [t for t in thumbs if t]
        item["evidence"] = [p.resolve().relative_to(root).as_posix() if p.resolve().is_relative_to(root) else str(p)
                            for p in card.get("evidence_paths", [])[:limit]]
        item["links"] = [{"label": l["label"], "href": rel_link(l["href"])} for l in card.get("links", [])]
        cards.append(item)

    # 影片列：最近完成 6 段＋全部（依集數），10 幀條點了才載入影片
    order = segment_order(root)
    seg_rows = built["classified"].get("segments", {})
    for sid in seg_rows:
        if sid not in order:
            order.append(sid)
    videos: List[Dict[str, Any]] = []
    open_ids = {c.get("segment") for c in built["open"]} | {s for c in built["open"] for s in c.get("segments", [])}
    for sid in order:
        path = root / "videos" / f"{sid}.mp4"
        if not path.is_file():
            continue
        row = seg_rows.get(sid, {})
        tag = ("open" if sid in open_ids else "user" if row.get("source") == "user"
               else row.get("effective", "unreviewed"))
        videos.append({"segment": sid, "ep": sid.split("-")[0], "mtime": path.stat().st_mtime,
                       "video": rel_link(f"videos/{sid}.mp4"), "tag": tag, "strip": None})
    recent = sorted(videos, key=lambda v: v["mtime"], reverse=True)[:6]
    if strips != "none":
        wanted = recent + [v for v in videos if v not in recent] if strips == "all" else recent
        for v in wanted:
            v["strip"] = embed(root / "videos" / f"{v['segment']}.mp4", 480, 50)

    raw_links = []
    for label, rel in (("專案狀態", "review/project-state.json"), ("定案與政策", "decisions.json"),
                       ("逐段驗收結論", "review/verdicts.json"), ("技術 QA 報告", "videos/qa-report.json")):
        if (root / rel).is_file():
            raw_links.append({"label": label, "href": rel_link(rel)})
    for page in sorted((root / "review").glob("stage-*.html")):
        raw_links.append({"label": f"舊版審核頁 {page.stem}", "href": rel_link(f"review/{page.name}")})

    stage_list = []
    for i in range(8):
        entry = state["stages"][ps.stage_key(i)]
        stage_list.append({"n": i, "name": STAGE_SHORT[i], "status": entry.get("status"),
                           "current": i == cur, "auto": bool(entry.get("auto_approval"))})
    blockers = [c for c in built["open"] if c["blocking"] <= 2]
    blocker = blockers[0]["title"] if blockers else ("沒有擋住下一步的事" if built["open"] else "")
    return validate_model({
        "schema_version": 1,
        "project": state.get("title") or root.name,
        "generated_at": datetime.now().astimezone().strftime("%Y-%m-%d %H:%M"),
        "current_stage": cur, "stages": stage_list, "blocker": blocker,
        "cards": cards, "decided": built["decided"], "auto": built["auto"], "notes": built["notes"],
        "counts": built["classified"].get("counts", {}),
        "videos": [{k: v for k, v in item.items() if k != "mtime"} for item in videos],
        "recent": [v["segment"] for v in recent],
        "raw_links": raw_links,
    })


# ------------------------------------------------------------------ 版面規格檢查（references/review-page-spec.md）
MAX_OPEN_CARDS = 5
MAX_QUESTION = 46
VALID_BLOCKING = (0, 1, 2, 5)          # 0 擋全部／1 擋下一步／2 擋本階段核准／5 不擋
REQUIRED_FIELDS = ("id", "kind", "stage", "title", "impact", "recommendation", "options", "blocking", "source")
_IGNORED_FALLBACK = {0: "每個階段都不能往下。", 1: "停在這一步，後面都不會開始。",
                     2: "本階段不能核准。", 5: "維持現狀，不擋核准。"}


def _sort_key(card: Dict[str, Any]) -> Tuple[int, int, str]:
    return card["blocking"], card["stage"], card["id"]


def _merged_card(tail: List[Dict[str, Any]]) -> Dict[str, Any]:
    """超過 5 張時，把排在後面的卡併成一張（比照 _warn_group_card）；blocking 取組內最高（數字最小）。"""
    top = min(tail, key=_sort_key)
    ids = [c["id"] for c in tail]
    segments = [s for c in tail for s in (c.get("segments") or [c.get("segment")]) if s]
    subject = f"其餘 {len(tail)} 件"
    return {
        "id": "D-merged", "kind": "merged", "stage": min(c["stage"] for c in tail),
        "segment": "、".join(map(str, segments[:4])) + ("…" if len(segments) > 4 else ""),
        "title": f"還有 {len(tail)} 件待決：" + "；".join(short_title(c["title"], 14) for c in tail[:3]),
        "finding": "；".join(f"{c['id']} {c['title']}" for c in tail[:6]) + ("…" if len(tail) > 6 else ""),
        "impact": "每件的影響各不相同；其中擋關的照樣擋關，不會因為併成一張就放行。",
        "recommendation": "照每件各自的建議處理；要細看再拆開。",
        "options": [{"label": "照各件建議處理", "reply": f"{subject}：照各件建議處理（{'、'.join(ids)}）"},
                    {"label": "逐件給我看", "reply": f"{subject}：逐件拆成卡片給我看"}],
        "if_ignored": "這幾件都維持現狀；其中擋關的仍然擋關。",
        "blocking": top["blocking"], "blocking_label": top.get("blocking_label", ""),
        "evidence_b64": [b for c in tail for b in c.get("evidence_b64", [])[:1]][:3],
        "evidence": [e for c in tail for e in c.get("evidence", [])[:1]][:3],
        "evidence_caption": "／".join(ids[:3]), "links": [],
        "source": "、".join(dict.fromkeys(str(c.get("source", "")) for c in tail)),
        "segments": segments, "merged": ids,
    }


def _normalize_card(card: Dict[str, Any], problems: List[str]) -> Dict[str, Any]:
    missing = [f for f in REQUIRED_FIELDS if card.get(f) in (None, "", [])]
    if missing:
        raise ValueError(f"收件匣卡片 {card.get('id', '?')} 缺必備欄位：{'、'.join(missing)}")
    out = dict(card)
    cid = out["id"]
    if out["blocking"] not in VALID_BLOCKING:
        problems.append(f"{cid}: blocking={out['blocking']} 不在 {VALID_BLOCKING}，已改為 {2 if out['blocking'] < 5 else 5}")
        out["blocking"] = 2 if out["blocking"] < 5 else 5
    options = list(out["options"])
    if len(options) > 3:
        problems.append(f"{cid}: 選項 {len(options)} 個，只留前 3 個")
        options = options[:3]
    if len(options) < 2:
        problems.append(f"{cid}: 選項只有 {len(options)} 個，補「先放著」")
        options.append({"label": "先放著", "reply": f"{cid}：先放著"})
    out["options"] = options
    if not out.get("if_ignored"):
        problems.append(f"{cid}: 缺 if_ignored，用預設文字")
        out["if_ignored"] = _IGNORED_FALLBACK[out["blocking"]]
    title = str(out["title"])
    out["title"] = title if len(title) <= MAX_QUESTION else title[: MAX_QUESTION - 1] + "…"
    # 規格欄位名對照：question＝title、why_you＝impact、recommendation 對應 options[0]（頁面標「建議」）
    out["question"] = out["title"]
    out["why_you"] = out["impact"]
    out["recommended_option"] = options[0]["label"]
    return out


def validate_model(model: Dict[str, Any]) -> Dict[str, Any]:
    """collect() 之後執行：補齊／檢查卡片欄位、待決卡 ≤ 5（超過就把後面的併成一張）。回傳新的 model。"""
    problems: List[str] = []
    cards = sorted((_normalize_card(c, problems) for c in model["cards"]), key=_sort_key)
    pinned = [c for c in cards if c["blocking"] == 0 or c["kind"] == "approval"]
    others = [c for c in cards if c not in pinned]
    slots = max(MAX_OPEN_CARDS - 1 - len(pinned), 0)
    if len(cards) > MAX_OPEN_CARDS and others[slots:]:
        merged = _normalize_card(_merged_card(others[slots:]), problems)
        cards = sorted(pinned + others[:slots] + [merged], key=_sort_key)
    return {**model, "cards": cards, "problems": problems}


# ------------------------------------------------------------------ HTML
E = html.escape

CSS = """
:root{--bg:#0e1013;--panel:#161a1f;--panel2:#1c2128;--line:#2a3039;--tx:#ecebe7;--mut:#a3a9b2;--dim:#7d848e;
--hot:#ef7a5a;--hotbg:rgba(239,122,90,.13);--ok:#7cc8a8;--okbg:rgba(124,200,168,.12);--acc:#e8c27a;--accbg:rgba(232,194,122,.12)}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--tx);font:17px/1.75 "PingFang TC","Noto Sans CJK TC","Noto Sans TC","Microsoft JhengHei",system-ui,sans-serif;letter-spacing:.02em;-webkit-font-smoothing:antialiased}
.wrap{max-width:760px;margin:0 auto;padding:20px 16px 64px}
header h1{font-size:15px;font-weight:500;color:var(--mut);margin:0 0 2px;letter-spacing:.08em}
header .big{font-size:28px;font-weight:700;line-height:1.35;margin:0}header .big em{font-style:normal;color:var(--hot)}
header .sub{color:var(--mut);margin:6px 0 0;font-size:15px}
.stages{list-style:none;padding:0;margin:20px 0 6px;display:grid;grid-template-columns:repeat(8,1fr);gap:4px}
.st{display:flex;flex-direction:column;align-items:center;gap:6px;position:relative}
.st::before{content:"";position:absolute;top:15px;left:-50%;width:100%;height:2px;background:var(--line);z-index:0}
.st:first-child::before{display:none}.st.done::before,.st.cur::before{background:var(--ok)}
.dot{position:relative;z-index:1;width:32px;height:32px;border-radius:50%;display:grid;place-items:center;font-size:14px;font-weight:700;background:var(--panel2);color:var(--dim);border:2px solid var(--line)}
.done .dot{background:#172723;color:var(--ok);border-color:var(--ok)}
.cur .dot{background:var(--hot);color:#1a0d08;border-color:var(--hot);box-shadow:0 0 0 5px var(--hotbg)}
.nm{font-size:12.5px;color:var(--mut);white-space:nowrap;letter-spacing:0}.cur .nm{color:var(--tx);font-weight:700}
.block{margin:12px 0 0;background:var(--hotbg);border:1px solid rgba(239,122,90,.35);border-radius:12px;padding:10px 14px;font-size:15px;color:#f6d6cb;word-break:break-word}
.block b{color:var(--hot)}.block.calm{background:var(--okbg);border-color:rgba(124,200,168,.35);color:#cfeee0}.block.calm b{color:var(--ok)}
.notes{margin:10px 0 0;padding:0;list-style:none;font-size:14px;color:var(--mut)}
h2{font-size:21px;margin:36px 0 12px;line-height:1.4}h2 .n{display:block;font-size:14px;font-weight:500;color:var(--mut);margin-top:2px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:18px;padding:18px 16px 16px;margin:0 0 16px}
.card.hot{border-color:rgba(239,122,90,.45)}
.meta{display:flex;flex-wrap:wrap;align-items:center;gap:8px;font-size:13.5px}
.tag{padding:2px 10px;border-radius:99px;background:var(--panel2);color:var(--mut);border:1px solid var(--line);font-weight:600}
.tag.hot{background:var(--hotbg);color:var(--hot);border-color:rgba(239,122,90,.4)}.seg{color:var(--dim);word-break:break-all}
.card h3{font-size:20px;line-height:1.5;margin:10px 0 8px;font-weight:700;word-break:break-word}
figure{margin:4px 0 12px}figure img{display:block;width:100%;height:auto;border-radius:10px;background:#000}
figure img+img{margin-top:6px}figcaption{font-size:13px;color:var(--dim);margin-top:6px}
dl{margin:0;display:grid;grid-template-columns:auto 1fr;gap:6px 12px}dt{font-size:14px;color:var(--dim);padding-top:2px;white-space:nowrap}
dd{margin:0;color:#d9dadb;word-break:break-word}dd.recd{color:var(--tx);font-weight:600}
.opts{display:grid;gap:8px;margin-top:14px}
.opt{all:unset;cursor:pointer;display:flex;flex-direction:column;gap:2px;padding:12px 14px;border-radius:12px;background:var(--panel2);border:1px solid var(--line);transition:background .15s,border-color .15s;-webkit-tap-highlight-color:transparent}
.opt:hover{border-color:#3d4652}.opt:focus-visible{outline:2px solid var(--acc);outline-offset:2px}
.opt.rec{border-color:rgba(124,200,168,.5);background:var(--okbg)}.ol{font-weight:700;font-size:16.5px}
.opt.rec .ol::after{content:"建議";display:inline-block;white-space:nowrap;margin-left:8px;font-size:12px;font-weight:600;color:var(--ok);border:1px solid rgba(124,200,168,.5);border-radius:99px;padding:0 7px;vertical-align:2px}
.ot{font-size:13.5px;color:var(--mut);line-height:1.55;word-break:break-word}
.opt.copied{border-color:var(--acc);background:var(--accbg)}.opt.copied .ot::before{content:"已複製：";color:var(--acc);font-weight:700}
.links{margin-top:12px;display:flex;flex-wrap:wrap;gap:14px}.lnk{color:var(--acc);text-decoration:none;font-size:15px}.lnk:hover{text-decoration:underline}
.src{color:var(--dim);font-size:13px;margin:10px 0 0;word-break:break-word}
.fold{background:var(--panel);border:1px solid var(--line);border-radius:16px;margin:0 0 14px;overflow:hidden}
.fold>summary{list-style:none;cursor:pointer;padding:14px 16px;font-size:18px;font-weight:700;display:flex;justify-content:space-between;align-items:center;gap:10px}
.fold>summary::-webkit-details-marker,.kd>summary::-webkit-details-marker,.ep>summary::-webkit-details-marker{display:none}
.fold>summary::after{content:"展開";font-size:14px;font-weight:500;color:var(--mut);flex:0 0 auto}.fold[open]>summary::after{content:"收合"}
.ft{display:flex;flex-direction:column;gap:2px}.fold>summary small{font-size:14px;color:var(--mut);font-weight:500;line-height:1.5}
.kd{border-top:1px solid var(--line)}.kd>summary{list-style:none;cursor:pointer;display:flex;gap:12px;padding:11px 16px;align-items:flex-start}
.kt{flex:0 0 auto;font-size:13.5px;color:var(--dim);font-variant-numeric:tabular-nums;padding-top:2px;min-width:86px}
.ck{flex:0 0 auto;color:var(--ok);font-weight:700}.kx{display:flex;flex-direction:column;min-width:0}.kx b{font-size:16px}
.kv{color:var(--mut);font-size:15px;line-height:1.6;word-break:break-word}.kv.strong{color:var(--tx);font-size:16px}
.kd p{margin:0 16px 10px 114px;font-size:14.5px;color:#cfd2d6;line-height:1.7;word-break:break-word}
.kd p.src{color:var(--dim);font-size:13px}#auto .kd p{margin-left:42px}
.empty{color:var(--mut);padding:14px 16px;margin:0}
.vrow{display:flex;gap:10px;overflow-x:auto;padding:2px 0 10px;scroll-snap-type:x mandatory}
.vrow .vid{flex:0 0 78%;max-width:340px;scroll-snap-align:start}
.vid{all:unset;cursor:pointer;display:flex;flex-direction:column;gap:6px;background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:8px}
.vid:focus-visible{outline:2px solid var(--acc)}.vimg img,.vimg video{display:block;width:100%;height:auto;border-radius:6px;background:#000}
.noimg{display:grid;place-items:center;aspect-ratio:16/6;border-radius:6px;background:var(--panel2);color:var(--dim);font-size:13px}
.vn{font-size:14px;color:var(--mut);display:flex;gap:8px;align-items:center;font-variant-numeric:tabular-nums}
.vt{font-size:11.5px;padding:0 7px;border-radius:99px;border:1px solid var(--line)}
.v-open,.v-fail{color:var(--hot);border-color:rgba(239,122,90,.5)}.v-user{color:var(--acc);border-color:rgba(232,194,122,.5)}
.v-warn{color:var(--acc);border-color:rgba(232,194,122,.35)}.v-unreviewed{color:var(--dim)}
.ep{border-top:1px solid var(--line)}.ep>summary{list-style:none;cursor:pointer;padding:12px 16px;font-weight:700;display:flex;justify-content:space-between}
.cnt{color:var(--dim);font-weight:500;font-size:14px}.vgrid{display:grid;grid-template-columns:1fr;gap:10px;padding:0 12px 14px}
.raw{font-size:14px;color:var(--mut);margin-top:30px;border-top:1px solid var(--line);padding-top:14px}.raw a{color:var(--mut)}.raw ul{margin:6px 0 0;padding-left:18px}
.toast{position:fixed;left:50%;bottom:24px;transform:translateX(-50%) translateY(20px);opacity:0;background:var(--acc);color:#1d1606;font-weight:700;padding:10px 18px;border-radius:99px;transition:.2s;pointer-events:none;font-size:15px;max-width:90vw;text-align:center}
.toast.on{opacity:1;transform:translateX(-50%) translateY(0)}
@media (min-width:900px){.wrap{max-width:1120px;padding:36px 32px 80px}header .big{font-size:34px}
.layout{display:grid;grid-template-columns:minmax(0,1.55fr) minmax(0,1fr);gap:28px;align-items:start}
.side h2:first-child{margin-top:36px}.card{padding:22px 22px 18px}body{font-size:18px}.nm{font-size:14px}.vrow .vid{flex-basis:46%}
.vgrid{grid-template-columns:1fr 1fr}}
@media (max-width:380px){.nm{font-size:11px}.dot{width:28px;height:28px}.st::before{top:13px}}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
"""

JS = """
const toast=document.getElementById('toast');let tt;
function show(m){toast.textContent=m;toast.classList.add('on');clearTimeout(tt);tt=setTimeout(()=>toast.classList.remove('on'),1800)}
async function copy(t){try{await navigator.clipboard.writeText(t);return true}catch(e){
 const a=document.createElement('textarea');a.value=t;a.style.position='fixed';a.style.opacity='0';document.body.appendChild(a);a.select();
 let ok=false;try{ok=document.execCommand('copy')}catch(_){};a.remove();return ok}}
document.querySelectorAll('.opt').forEach(b=>b.addEventListener('click',async()=>{
 const ok=await copy(b.dataset.reply);
 b.closest('.opts').querySelectorAll('.opt').forEach(x=>x.classList.remove('copied'));
 if(ok){b.classList.add('copied');show('已複製，貼回對話即可')}else show('複製失敗，請長按文字複製');
}));
if(matchMedia('(min-width:900px)').matches)document.querySelectorAll('.side details.fold').forEach(d=>d.open=true);
document.querySelectorAll('.vid').forEach(b=>b.addEventListener('click',()=>{
 const box=b.querySelector('.vimg');if(box.querySelector('video'))return;
 const v=document.createElement('video');v.src=b.dataset.src;v.controls=true;v.autoplay=true;v.playsInline=true;v.preload='metadata';
 box.innerHTML='';box.appendChild(v);
}));
"""

TAG_ZH = {"open": "待決", "user": "你裁示", "fail": "重跑", "warn": "附註", "unreviewed": "未驗收"}


def _card_html(c: Dict[str, Any]) -> str:
    opts = "".join(
        f'<button class="opt{" rec" if i == 0 else ""}" data-reply="{E(o["reply"])}">'
        f'<span class="ol">{E(o["label"])}</span><span class="ot">{E(o["reply"])}</span></button>'
        for i, o in enumerate(c["options"]))
    links = "".join(f'<a class="lnk" href="{E(l["href"])}" target="_blank" rel="noopener">{E(l["label"])} ↗</a>'
                    for l in c.get("links", []))
    hot = " hot" if c["blocking"] <= 2 else ""
    fig = ""
    if c.get("evidence_b64"):
        imgs = "".join(f'<img src="{src}" alt="{E(c.get("evidence_caption", "證據"))}">' for src in c["evidence_b64"])
        fig = f'<figure>{imgs}<figcaption>{E(c.get("evidence_caption", ""))}</figcaption></figure>'
    return f'''
<article class="card{hot}" id="{E(c["id"])}">
  <div class="meta"><span class="tag{hot}">{E(c["blocking_label"])}</span><span class="seg">階段 {c["stage"]}・{E(str(c["segment"]))}</span></div>
  <h3>{E(c["title"])}</h3>
  {fig}
  <dl>{f'<dt>判定</dt><dd>{E(c["finding"])}</dd>' if c.get("finding") else ""}<dt>影響</dt><dd>{E(c["impact"])}</dd><dt>建議</dt><dd class="recd">{E(c["recommendation"])}</dd><dt>不回覆</dt><dd>{E(c.get("if_ignored", ""))}</dd></dl>
  <div class="opts">{opts}</div>
  {f'<div class="links">{links}</div>' if links else ""}
  <p class="src">卡片 {E(c["id"])}・來源 {E(c.get("source", ""))}</p>
</article>'''


def _decided_html(d: Dict[str, Any]) -> str:
    return (f'<details class="kd"><summary><span class="kt">{E(d["time"])}</span><span class="kx"><b>{E(d["title"])}</b>'
            f'<span class="kv">{E(d["decision"])}</span></span></summary><p>{E(d["detail"])}</p>'
            f'<p class="src">階段 {d["stage"]}・出處 {E(d["source"])}</p></details>')


def _auto_html(a: Dict[str, Any]) -> str:
    return (f'<details class="kd"><summary><span class="ck">✓</span><span class="kx"><span class="kv strong">{E(a["text"])}</span>'
            f'</span></summary><p>{E(a["detail"])}</p><p class="src">來源：{E(a["source"])}</p></details>')


def _vid_html(v: Dict[str, Any]) -> str:
    tag = TAG_ZH.get(v["tag"], "")
    t = f'<span class="vt v-{E(v["tag"])}">{tag}</span>' if tag else ""
    img = (f'<img src="{v["strip"]}" alt="{E(v["segment"])} 10 幀條">' if v.get("strip")
           else '<div class="noimg">點一下載入影片</div>')
    return (f'<button class="vid" data-src="{E(v["video"])}"><span class="vimg">{img}</span>'
            f'<span class="vn">{E(v["segment"])}{t}</span></button>')


def render_html(model: Dict[str, Any]) -> str:
    cards = model["cards"]
    stages = model["stages"]
    cur = model["current_stage"]
    bar = "".join(
        f'<li class="st {"done" if s["status"] == "approved" else ("cur" if s["current"] else "todo")}">'
        f'<span class="dot">{s["n"]}</span><span class="nm">{E(s["name"])}</span></li>' for s in stages)
    big = (f'有 <em>{len(cards)}</em> 件事等你決定' if cards else '目前沒有要你決定的事')
    c = model.get("counts") or {}
    hard = [x for x in cards if x["blocking"] <= 2]
    soft = [x for x in cards if x["blocking"] > 2]
    stuck = short_title(hard[0]["title"], 24) if hard else "沒有"
    progress = f'階段{cur}/7・{len(cards)}件待決・卡在{E(stuck)}'
    sub = f'目前在階段 {cur}「{E(STAGE_SHORT[cur])}」'
    if c:
        sub += f'・影片 通過 {c.get("pass", 0)}・附註 {c.get("warn", 0)}・重跑 {c.get("fail", 0)}'
    if model["blocker"]:
        calm = " calm" if not any(x["blocking"] <= 2 for x in cards) else ""
        lead = "卡在這裡：" if not calm else "狀態："
        block = f'<p class="block{calm}"><b>{lead}</b>{E(model["blocker"])}</p>'
    else:
        block = '<p class="block calm"><b>狀態：</b>沒有擋住的事，可以往下走</p>'
    notes = "".join(f"<li>・{E(n)}</li>" for n in model.get("notes", []))
    videos = model.get("videos", [])
    vmap = {v["segment"]: v for v in videos}
    recent = "".join(_vid_html(vmap[s]) for s in model.get("recent", []) if s in vmap)
    eps = list(dict.fromkeys(v["ep"] for v in videos))
    ep_rows = "".join(
        f'<details class="ep"><summary>{E(ep)}<span class="cnt">{sum(1 for v in videos if v["ep"] == ep)} 段</span></summary>'
        f'<div class="vgrid">{"".join(_vid_html(v) for v in videos if v["ep"] == ep)}</div></details>' for ep in eps)
    decided = "".join(_decided_html(d) for d in model["decided"]) or '<p class="empty">還沒有定案紀錄</p>'
    auto = "".join(_auto_html(a) for a in model["auto"]) or '<p class="empty">還沒有自動處理的事</p>'
    cards_html = "".join(_card_html(x) for x in hard) or (
        '<article class="card"><h3>沒有擋關的待決事項</h3><dl><dt>下一步</dt>'
        '<dd class="recd">照 h3d next 繼續；符合授權的階段可用 h3d approve --auto 自動核准。</dd></dl></article>')
    gate_items = "".join(f'<li><a class="lnk" href="#{E(x["id"])}">{E(x["title"])}</a></li>' for x in hard[:3])
    gate_html = (f'<h2>真正擋關<span class="n">{len(hard)} 條</span></h2><ol class="notes">{gate_items}</ol>'
                 if hard else "")
    soft_html = (f'<details class="fold"><summary><span class="ft">可略過警告 {len(soft)} 件<small>不擋核准・點開才看</small>'
                 f'</span></summary>{"".join(_card_html(x) for x in soft)}</details>' if soft else "")
    video_block = ""
    if videos:
        video_block = (f'<h2>最近完成的影片<span class="n">每張是 10 幀條・點了才載入影片</span></h2>'
                       f'<div class="vrow">{recent}</div>'
                       f'<details class="fold"><summary><span class="ft">全部 {len(videos)} 段<small>依集數・標籤＝待決／你裁示／附註／重跑</small>'
                       f'</span></summary>{ep_rows}</details>')
    raw = "".join(f'<li><a href="{E(l["href"])}" target="_blank" rel="noopener">{E(l["label"])}</a></li>'
                  for l in model.get("raw_links", []))
    return f'''<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>決策收件匣｜{E(model["project"])}</title>
<style>{CSS}</style></head>
<body><div class="wrap">
<header>
  <h1>{E(model["project"])}・決策收件匣</h1>
  <p class="big">{big}</p>
  <p class="sub progress">{progress}</p>
  <p class="sub">{sub}</p>
  <ol class="stages" aria-label="階段進度">{bar}</ol>
  {block}
  {f'<ul class="notes">{notes}</ul>' if notes else ""}
</header>
<div class="layout">
<main>
  <h2>需要你決定<span class="n">依會不會擋下一步排序・點選項＝複製回覆</span></h2>
  {cards_html}
  {gate_html}
  {soft_html}
</main>
<aside class="side">
  <h2>你已經決定的<span class="n">{len(model["decided"])} 件</span></h2>
  <details class="fold"><summary><span class="ft">定案與核准紀錄<small>新的在上・點一行看原話</small></span></summary>{decided}</details>
  <h2>我自動處理了 {len(model["auto"])} 件事</h2>
  <details class="fold" id="auto"><summary><span class="ft">自動處理紀錄<small>一行一項・點開看來源</small></span></summary>{auto}</details>
</aside>
</div>
{video_block}
<div class="raw">原始資料（不內嵌，需在專案資料夾內開啟）
<ul>{raw}</ul>
<p>產生時間 {E(model["generated_at"])}・h3d inbox</p></div>
</div>
<div class="toast" id="toast" role="status" aria-live="polite"></div>
<script>{JS}</script>
</body></html>'''


def build(root: Path, *, out_dir: Optional[Path] = None, images: bool = True, strips: str = "all") -> Dict[str, Any]:
    root = Path(root).expanduser().resolve()
    out_dir = Path(out_dir).resolve() if out_dir else root / "review"
    out_dir.mkdir(parents=True, exist_ok=True)
    model = collect(root, images=images, strips=strips, out_dir=out_dir)
    page = render_html(model)
    html_path = out_dir / "inbox.html"
    json_path = out_dir / "inbox.json"
    html_path.write_text(page, encoding="utf-8")
    slim = dict(model)
    slim["cards"] = [{k: v for k, v in card.items() if k != "evidence_b64"} for card in model["cards"]]
    slim["videos"] = [{k: v for k, v in item.items() if k != "strip"} for item in model["videos"]]
    json_path.write_text(json.dumps(slim, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"html": html_path, "json": json_path, "bytes": html_path.stat().st_size,
            "open": len(model["cards"]), "decided": len(model["decided"]), "auto": len(model["auto"]),
            "problems": model["problems"]}


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="h3d inbox",
                                     description="產生決策收件匣 review/inbox.html（只列需要使用者決定的事）")
    parser.add_argument("--root", type=Path, default=Path("."), help="專案根目錄")
    parser.add_argument("--out-dir", type=Path, default=None, help="輸出資料夾（預設 <專案>/review）")
    parser.add_argument("--strips", choices=["all", "recent", "none"], default="all",
                        help="影片 10 幀條：全部／只有最近 6 段／不要（需要 ffmpeg）")
    parser.add_argument("--no-images", action="store_true", help="完全不內嵌圖片（最小檔）")
    parser.add_argument("--json", action="store_true", help="只印未決卡（JSON），不寫檔")
    args = parser.parse_args(argv)
    root = args.root.expanduser().resolve()
    if args.json:
        cards = build_cards(root)["open"]
        print(json.dumps([{k: (v if k != "evidence_paths" else [str(p) for p in v]) for k, v in c.items()}
                          for c in cards], ensure_ascii=False, indent=2))
        return 0
    result = build(root, out_dir=args.out_dir, images=not args.no_images, strips=args.strips)
    size = result["bytes"] / 1024 / 1024
    print(f"✅ {result['html']}（{size:.2f} MB）：待決 {result['open']}、已決定 {result['decided']}、自動處理 {result['auto']}")
    if result["bytes"] > 5 * 1024 * 1024:
        print("⚠️ 超過 5 MB：改用 --strips recent 或 --no-images", file=sys.stderr)
    for problem in result["problems"]:
        print(f"⚠️ 卡片規格：{problem}", file=sys.stderr)
    print(f"   機讀版：{result['json']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
