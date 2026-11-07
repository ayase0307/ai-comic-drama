# build_blind_review.py - 盲審材料包產生器（stdlib + ffmpeg）。
# 用法:
#   python scripts/build_blind_review.py --root <專案> --stage 3 [--episode EP01]   # 劇本盲審
#   python scripts/build_blind_review.py --root <專案> --stage 7 [--episode EP01] [--frames 6]  # 成片盲審
#   python scripts/build_blind_review.py --root <專案> --inputs script-ep01.md adapt/story-map.md
#
# 為什麼要有這支（Eian 2026-11-05 文章對照）：主 agent 跟使用者聊久了會自動腦補，看自己的
# 產物樣樣順眼。文章的做法是每個關鍵產物都「新開一個 agent，只給材料、不給任何結論」，讓它
# 像第一次看的觀眾輸出「看懂的故事＋看不懂的地方＋通過/不通過」。本腳本把「只含材料、不含
# 結論」的材料包組出來：劇本盲審只帶劇本本文；成片盲審只帶核准版影片的抽幀拼貼——
# verdicts、QA 報告、shot_intent、審核頁一律不進包。規則見 references/review/blind-review.md。
import argparse
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path

BUNDLE_DIR = "review/blind"


def _copy_inputs(root: Path, inputs: list[str], bundle: Path) -> list[str]:
    copied = []
    for raw in inputs:
        p = Path(raw)
        src = p if p.is_absolute() else root / p
        if not src.is_file():
            print(f"[錯誤] 找不到輸入檔：{src}", file=sys.stderr)
            sys.exit(2)
        dest = bundle / "files" / src.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        rel = src.relative_to(root) if src.is_relative_to(root) else src
        copied.append(rel.as_posix())
    return copied


def _stage3_sources(root: Path, episode: str | None) -> list[Path]:
    scripts = sorted(root.glob("script-*.md"))
    if episode:
        ep = episode.lower()
        scripts = [p for p in scripts if ep in p.name.lower()]
    return scripts


def _stage7_sources(root: Path, episode: str | None) -> list[Path]:
    """核准版影片＝videos/ 頂層的 mp4（SKILL.md 規則 12：核准版與定稿版分開放）。"""
    vids = sorted((root / "videos").glob("*.mp4")) if (root / "videos").is_dir() else []
    if episode:
        ep = episode.lower()
        vids = [p for p in vids if ep in p.name.lower()]
    return vids


def _contact_sheet(video: Path, out: Path, frames: int) -> None:
    """每段均勻抽 frames 幀 → 3 欄拼貼成一張 jpg（不含任何 QA 註記）。"""
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(video)],
        capture_output=True, text=True, check=True)
    dur = float(probe.stdout.strip() or 0) or 1.0
    fps = max(frames / dur, 0.01)
    cols = 3
    rows = max(1, math.ceil(frames / cols))
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(video),
         "-vf", f"fps={fps:.4f},scale=320:-2,tile={cols}x{rows}",
         "-frames:v", "1", "-q:v", "3", str(out)],
        check=True, capture_output=True)


def build(root: Path, stage: int | None, episode: str | None, inputs: list[str], frames: int) -> Path:
    if not inputs and stage is None:
        print("[錯誤] 要給 --stage 3|7 或 --inputs", file=sys.stderr)
        sys.exit(2)
    tag = (episode or "all").lower()
    bundle = root / BUNDLE_DIR / f"stage{stage or 'inputs'}-{tag}"
    if bundle.exists():
        shutil.rmtree(bundle)
    bundle.mkdir(parents=True)
    sources: list[str] = []
    sheets: list[str] = []
    if inputs:
        sources = _copy_inputs(root, inputs, bundle)
    elif stage == 3:
        for src in _stage3_sources(root, episode):
            dest = bundle / "files" / src.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            sources.append(src.name)
        if not sources:
            print(f"[錯誤] 找不到 script-*.md（episode={episode or '全部'}）", file=sys.stderr)
            sys.exit(2)
    elif stage == 7:
        for vid in _stage7_sources(root, episode):
            sheet = bundle / "sheets" / f"{vid.stem}.jpg"
            _contact_sheet(vid, sheet, frames)
            sheets.append(vid.name)
        if not sheets:
            print(f"[錯誤] videos/ 頂層找不到 mp4（episode={episode or '全部'}）", file=sys.stderr)
            sys.exit(2)
    else:
        print("[錯誤] --stage 只收 3 或 7", file=sys.stderr)
        sys.exit(2)
    manifest = {
        "stage": stage,
        "episode": episode,
        "sources": sources,
        "contact_sheets": sheets,
        "note": "盲審材料包：只含材料本身（劇本本文／核准版影片抽幀）。verdicts、QA 報告、"
                "shot_intent、審核頁一律不在包內；盲審 agent 只准讀這個資料夾。",
    }
    (bundle / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                                          encoding="utf-8")
    print(f"✅ 盲審材料包：{bundle}")
    print(f"   來源：{len(sources)} 檔、拼貼：{len(sheets)} 張")
    print("   下一步：開一個 fresh subagent，只給它這個資料夾路徑（規則見 references/review/blind-review.md）")
    return bundle


def main() -> int:
    parser = argparse.ArgumentParser(description="組出「只含材料、不含結論」的盲審材料包")
    parser.add_argument("--root", default=".", help="專案根目錄")
    parser.add_argument("--stage", type=int, choices=(3, 7), help="3＝劇本盲審；7＝成片盲審")
    parser.add_argument("--episode", help="只做指定集，例如 EP01")
    parser.add_argument("--inputs", nargs="+", help="手動指定材料檔（階段 1 故事地圖等；相對 --root 或絕對路徑）")
    parser.add_argument("--frames", type=int, default=6, help="每段影片抽幀數（預設 6）")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    build(root, args.stage, args.episode, args.inputs or [], max(1, args.frames))
    return 0


if __name__ == "__main__":
    sys.exit(main())
