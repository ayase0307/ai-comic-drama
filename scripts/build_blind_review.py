# build_blind_review.py - 盲審材料包產生器（stdlib + ffmpeg）。
# 用法:
#   python scripts/build_blind_review.py --root <專案> --stage 3 [--episode EP01]   # 劇本盲審
#   python scripts/build_blind_review.py --root <專案> --stage 4 [--episode EP01]   # 分鏡理解層盲審
#   python scripts/build_blind_review.py --root <專案> --stage 5 [--episode EP01]   # 送件前語義對帳
#   python scripts/build_blind_review.py --root <專案> --stage 7 [--episode EP01] [--frames 6]  # 成片盲審
#   python scripts/build_blind_review.py --root <專案> --inputs script-ep01.md adapt/story-map.md
#
# 為什麼要有這支（Eian 2026-11-05 文章對照）：主 agent 跟使用者聊久了會自動腦補，看自己的
# 產物樣樣順眼。文章的做法是每個關鍵產物都「新開一個 agent，只給材料、不給任何結論」，讓它
# 像第一次看的觀眾輸出「看懂的故事＋看不懂的地方＋通過/不通過」。本腳本把「只含材料、不含
# 結論」的材料包組出來：劇本盲審只帶劇本本文（階段 3）；分鏡盲審帶劇本＋分鏡表（階段 4）；
# 送件前語義對帳帶分鏡表＋提示詞包＋構圖圖（階段 5）；成片盲審只帶核准版影片的抽幀拼貼
# （階段 7）——verdicts、QA 報告、shot_intent、審核頁一律不進包。規則見 references/blind-review.md。
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


def _material_sources(root: Path, patterns: tuple[str, ...], episode: str | None) -> list[Path]:
    """依檔名樣式收集材料檔（script-*.md／storyboard-*.md／prompts-*.md…）。

    --episode 依檔名過濾（不分大小寫、子字串比對），與階段 3 的舊行為一致。
    """
    found: list[Path] = []
    for pattern in patterns:
        found.extend(sorted(root.glob(pattern)))
    uniq = sorted(set(found))
    if episode:
        ep = episode.lower()
        uniq = [p for p in uniq if ep in p.name.lower()]
    return uniq


def _stage5_panels(root: Path, episode: str | None, bundle: Path) -> tuple[list[str], list[str]]:
    """階段 5：把 layer2 每鏡 sketch_file 指到的構圖圖複製進包的 panels/（去重）。

    只複製圖檔本身；找不到的記進 skipped_panels（blind 面只看得到存在的圖）。
    sketch_file 可能相對 --root 或相對 layer2/*.json 所在目錄，兩者都比對。
    """
    layer_dir = root / "layer2"
    faces = sorted(layer_dir.glob("layer2-*.json")) if layer_dir.is_dir() else []
    if episode:
        ep = episode.lower()
        faces = [p for p in faces if ep in p.name.lower()]
    copied: list[str] = []
    skipped: list[str] = []
    seen: set[Path] = set()
    for face in faces:
        try:
            data = json.loads(face.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            print(f"[警告] 讀不到分鏡檔，略過：{face}", file=sys.stderr)
            continue
        shots = data.get("shots") if isinstance(data, dict) else None
        for shot in shots or []:
            if not isinstance(shot, dict):
                continue
            raw = shot.get("sketch_file")
            if not isinstance(raw, str) or not raw.strip():
                continue
            rel = Path(raw.strip())
            candidates = [rel if rel.is_absolute() else root / rel,
                          rel if rel.is_absolute() else face.parent / rel]
            src = next((p for p in candidates if p.is_file()), None)
            if src is None:
                if rel.as_posix() not in skipped:
                    skipped.append(rel.as_posix())
                continue
            key = src.resolve()
            if key in seen:
                continue
            seen.add(key)
            dest = bundle / "panels" / src.name
            if dest.exists():  # 同名不同圖（不同段的 panel-01-…）加段名避免覆蓋
                dest = bundle / "panels" / f"{face.stem}-{src.name}"
                if dest.exists():
                    continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            copied.append(dest.relative_to(bundle).as_posix())
    return copied, skipped


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
        print("[錯誤] 要給 --stage 3|4|5|7 或 --inputs", file=sys.stderr)
        sys.exit(2)
    tag = (episode or "all").lower()
    bundle = root / BUNDLE_DIR / f"stage{stage or 'inputs'}-{tag}"
    if bundle.exists():
        shutil.rmtree(bundle)
    bundle.mkdir(parents=True)
    sources: list[str] = []
    sheets: list[str] = []
    panels: list[str] = []
    skipped_panels: list[str] = []
    if inputs:
        sources = _copy_inputs(root, inputs, bundle)
    elif stage in (3, 4, 5):
        patterns = {3: ("script-*.md",),
                    4: ("script-*.md", "storyboard-*.md"),
                    5: ("storyboard-*.md", "prompts-*.md")}[stage]
        for src in _material_sources(root, patterns, episode):
            dest = bundle / "files" / src.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            sources.append(src.name)
        if not sources:
            print(f"[錯誤] 找不到 {'／'.join(patterns)}（episode={episode or '全部'}）", file=sys.stderr)
            sys.exit(2)
        if stage == 5:
            panels, skipped_panels = _stage5_panels(root, episode, bundle)
    elif stage == 7:
        for vid in _stage7_sources(root, episode):
            sheet = bundle / "sheets" / f"{vid.stem}.jpg"
            _contact_sheet(vid, sheet, frames)
            sheets.append(vid.name)
        if not sheets:
            print(f"[錯誤] videos/ 頂層找不到 mp4（episode={episode or '全部'}）", file=sys.stderr)
            sys.exit(2)
    else:
        print("[錯誤] --stage 只收 3、4、5 或 7", file=sys.stderr)
        sys.exit(2)
    manifest = {
        "stage": stage,
        "episode": episode,
        "sources": sources,
        "contact_sheets": sheets,
        "note": "盲審材料包：只含材料本身（階段 3 劇本本文／階段 4 劇本＋分鏡表／階段 5 分鏡表＋提示詞包＋構圖圖／階段 7 核准版影片抽幀）。verdicts、QA 報告、"
                "shot_intent、審核頁一律不在包內；盲審 agent 只准讀這個資料夾。",
    }
    if stage == 5:
        manifest["panels"] = panels
        manifest["skipped_panels"] = skipped_panels
    (bundle / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                                          encoding="utf-8")
    print(f"✅ 盲審材料包：{bundle}")
    print(f"   來源：{len(sources)} 檔、拼貼：{len(sheets)} 張")
    if stage == 5:
        print(f"   構圖圖：{len(panels)} 張（缺圖略過 {len(skipped_panels)} 筆）")
    print("   下一步：開一個 fresh subagent，只給它這個資料夾路徑（規則見 references/blind-review.md）")
    return bundle


def main() -> int:
    parser = argparse.ArgumentParser(description="組出「只含材料、不含結論」的盲審材料包")
    parser.add_argument("--root", default=".", help="專案根目錄")
    parser.add_argument("--stage", type=int, choices=(3, 4, 5, 7),
                        help="3＝劇本盲審；4＝分鏡理解層盲審；5＝送件前語義對帳；7＝成片盲審")
    parser.add_argument("--episode", help="只做指定集，例如 EP01")
    parser.add_argument("--inputs", nargs="+", help="手動指定材料檔（階段 1 故事地圖等；相對 --root 或絕對路徑）")
    parser.add_argument("--frames", type=int, default=6, help="每段影片抽幀數（預設 6）")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    build(root, args.stage, args.episode, args.inputs or [], max(1, args.frames))
    return 0


if __name__ == "__main__":
    sys.exit(main())
