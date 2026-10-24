#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Layer 2 → Codex CLI 內建生圖的彩色分鏡圖（每鏡一張）＋每段分鏡總覽圖。

與 svg_storyboard_grid.py 相同的輸出契約：panels/panel-NN-<shot>.png、images/grid-<segment>.png，
並回寫 sketch_file／sketch_sha256／sketch_generation（backend=codex）供 stage-4 門禁與審核頁使用。
每鏡自動綁定已核准的參考圖：角色正面裁切（images/ref/<id>_front.png，退回設定板）、
異獸設定圖、段落場景母版，順序即 <Picture N>。

用法：
  python scripts/storyboard/codex_storyboard_panels.py --root <專案> --episode EP01 --model gpt-6-luna --parallel 3
  python scripts/storyboard/codex_storyboard_panels.py --root <專案> --shots EP01-S03-a-SH02 --model gpt-6-luna --force
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import pathlib
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Tuple

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

LOCKED_STATUSES = {"locked", "approved", "manual"}
STYLE14_PANEL = ("semi-realistic cinematic painting in the exact painterly style of the reference sheets, "
                 "thick painterly brush strokes, realistic East Asian proportions, never cel-shaded anime, no outlines, "
                 "muted grey-brown, jade teal and a touch of cinnabar")
NEGATIVE = "no text, no letters, no captions, no subtitles, no watermark, no speech bubbles, no panel borders, no extra people, no extra limbs, no modern objects"


def parse_assets_md(text: str) -> Dict[str, Dict[str, str]]:
    """`### <ID>　<名稱>` 區塊 → {id: {name, fixed, costume, image}}。"""
    out: Dict[str, Dict[str, str]] = {}
    for m in re.finditer(r"^###\s+([A-Z]+-[A-Za-z0-9_-]+)[\s\u3000]*(.*?)$(.*?)(?=^#{2,3}\s|\Z)", text, re.M | re.S):
        aid, title, body = m.group(1), m.group(2).strip(), m.group(3)
        fixed = re.search(r"固定描述片段\*\*：`([^`]+)`", body)
        costume = re.search(r"\*\*服裝\*\*：.*?固定片段：`([^`]+)`", body)
        img = re.search(r"images/[A-Za-z0-9_./-]+\.png", body)
        out[aid] = {"name": re.sub(r"[（(].*?[）)]", "", title).strip(), "fixed": fixed.group(1) if fixed else "",
                    "costume": costume.group(1) if costume else "", "image": img.group(0) if img else ""}
    return out


def load_keywords(root: pathlib.Path, path: Optional[pathlib.Path]) -> Tuple[Dict[str, List[str]], Dict[str, List[str]]]:
    """關鍵字與逐鏡覆寫：{"keywords": {"C-x": ["少年"]}, "shots": {"EP01-S05-e-SH02": ["C-a", "C-b"]}}。"""
    p = path or root / "staging" / "codex-panel-refs.json"
    if not p.is_file():
        return {}, {}
    data = json.loads(p.read_text(encoding="utf-8"))
    return data.get("keywords", {}), data.get("shots", {})


def subjects_for_shot(shot: Dict[str, Any], assets: Dict[str, Dict[str, str]], bible: Dict[str, Any],
                      keywords: Dict[str, List[str]], overrides: Dict[str, List[str]]) -> List[str]:
    sid = shot.get("shot_id", "")
    if sid in overrides:
        return list(overrides[sid])
    ids = list(shot.get("character_ids") or [])
    text = " ".join([(shot.get("spatial_blocking") or {}).get("blocking_desc", "")] +
                    list((shot.get("action_and_performance") or {}).get("action_stages", [])))
    names: Dict[str, List[str]] = {}
    for ch in bible.get("characters", []):
        cid = ch.get("character_id") or ch.get("id")
        names[cid] = [ch.get("canonical_name") or ""] + list(ch.get("aliases") or [])
    for aid, a in assets.items():
        if aid.startswith("CREATURE-"):
            names.setdefault(aid, []).append(a["name"])
    for aid, extra in keywords.items():
        names.setdefault(aid, []).extend(extra)
    for aid, words in names.items():
        if aid not in ids and any(w and w in text for w in words):
            ids.append(aid)
    return ids


def ref_image_for(root: pathlib.Path, aid: str, assets: Dict[str, Dict[str, str]]) -> Optional[pathlib.Path]:
    for cand in (root / "images" / "ref" / f"{aid}_front.png",
                 root / (assets.get(aid, {}).get("image") or "__none__"),
                 root / "images" / f"{aid.lower()}.png",
                 root / "images" / f"{aid}.png"):
        if cand.is_file():
            return cand
    if aid.startswith("CREATURE-"):
        c = root / "images" / f"creature-{aid[len('CREATURE-'):]}.png"
        if c.is_file():
            return c
    return None


def scene_ref(root: pathlib.Path, scene_id: str, assets: Dict[str, Dict[str, str]]) -> Optional[pathlib.Path]:
    slug = scene_id[2:] if scene_id.startswith("S-") else scene_id
    for cand in (root / (assets.get(scene_id, {}).get("image") or "__none__"), root / "images" / f"{scene_id}.png",
                 root / "images" / f"scene-{slug}-master.png"):
        if cand.is_file():
            return cand
    return None


def build_panel_prompt(shot: Dict[str, Any], seg: Dict[str, Any], subjects: List[str],
                       assets: Dict[str, Dict[str, str]], ref_labels: List[Tuple[str, str]]) -> str:
    cam = shot.get("camera_optics") or {}
    blk = shot.get("spatial_blocking") or {}
    act = shot.get("action_and_performance") or {}
    five = act.get("five_part_en") or {}
    style = (seg.get("style_lock") or {})
    lines = [f"Single cinematic storyboard frame for shot {shot.get('shot_id')}.",
             f"Style: {STYLE14_PANEL}."]
    if ref_labels:
        lines.append("Reference images, in attachment order: " + "; ".join(f"<Picture {i}> = {lab}" for i, (lab, _) in enumerate(ref_labels, 1)) + ".")
        lines.append("Match faces, hair, costumes and creature anatomy exactly to their reference pictures; use the scene picture for architecture, props and palette.")
    people = [a for a in subjects if not a.startswith("CREATURE-")]
    for a in subjects:
        info = assets.get(a, {})
        desc = ", ".join(x for x in (info.get("fixed"), info.get("costume")) if x)
        lines.append(f"{info.get('name') or a}: {desc}.")
    if people:
        pic = {lab.split(" (")[-1].rstrip(")"): i for i, (lab, _) in enumerate(ref_labels, 1)}
        who = ", ".join(f"{assets.get(a, {}).get('name') or a} = <Picture {pic[a]}>" for a in people if a in pic)
        if who:
            lines.insert(1, f"Main subject(s): {who}. Draw these exact people, never a different character from another picture.")
        lines.append(f"Exactly {len(people)} person(s) may be visible ({', '.join(assets.get(a, {}).get('name') or a for a in people)}); nobody else, no background figures.")
    else:
        lines.append("No people in frame (hands only if the action names them).")
    lines.append(f"Framing: {cam.get('shot_size', '')} {cam.get('focal_length', '')}, camera {five.get('camera') or blk.get('blocking_desc_en', '')}")
    lines.append(f"Composition (zh): {blk.get('blocking_desc', '')}")
    if act.get("action_stages_en"):
        lines.append(f"Moment to depict (start of the action): {act['action_stages_en'][0]}.")
    if five.get("performance"):
        lines.append(f"Performance: {five['performance']}")
    light = five.get("light") or style.get("lighting_lock_line") or ""
    if light:
        lines.append(f"Light: {light}")
    lines.append(f"Avoid: {NEGATIVE}; {style.get('negative', '')}".rstrip("; "))
    return "\n".join(lines)


def _sha256(p: pathlib.Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def plan(root: pathlib.Path, files: List[pathlib.Path], keywords_path: Optional[pathlib.Path] = None) -> List[Dict[str, Any]]:
    assets = parse_assets_md((root / "assets.md").read_text(encoding="utf-8")) if (root / "assets.md").is_file() else {}
    bible_p = root / "adapt" / "bible.json"
    bible = json.loads(bible_p.read_text(encoding="utf-8")) if bible_p.is_file() else {}
    keywords, overrides = load_keywords(root, keywords_path)
    jobs = []
    for f in files:
        seg = json.loads(f.read_text(encoding="utf-8-sig"))
        aspect = (seg.get("metadata") or {}).get("aspect_ratio") or "16:9"
        scene_id = (seg.get("asset_refs") or {}).get("scene_id") or ""
        for idx, shot in enumerate(seg.get("shots", []), 1):
            subjects = subjects_for_shot(shot, assets, bible, keywords, overrides)
            refs: List[Tuple[str, str]] = []
            missing = []
            for a in subjects:
                rp = ref_image_for(root, a, assets)
                (refs.append((f"{assets.get(a, {}).get('name') or a} ({a})", str(rp))) if rp else missing.append(a))
            sp = scene_ref(root, scene_id, assets) if scene_id else None
            if sp:
                refs.append((f"scene {assets.get(scene_id, {}).get('name') or scene_id} ({scene_id})", str(sp)))
            jobs.append(dict(file=f, segment=seg.get("segment_id") or f.stem[len("layer2-"):], index=idx,
                             shot_id=shot["shot_id"], aspect=aspect, subjects=subjects, refs=refs, missing_refs=missing,
                             prompt=build_panel_prompt(shot, seg, subjects, assets, refs),
                             filename=f"panel-{idx:02d}-{shot['shot_id']}.png"))
    return jobs


def assemble_grids(root: pathlib.Path, files: List[pathlib.Path]) -> List[pathlib.Path]:
    from PIL import Image, ImageDraw, ImageFont
    font = None
    for fp in (os.environ.get("SVG_GRID_FONT"), "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
               "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"):
        if fp and os.path.isfile(fp):
            font = ImageFont.truetype(fp, 22); break
    font = font or ImageFont.load_default()
    out = []
    for f in files:
        seg = json.loads(f.read_text(encoding="utf-8-sig"))
        shots = [s for s in seg.get("shots", []) if s.get("sketch_file") and (root / s["sketch_file"]).is_file()]
        if not shots:
            continue
        tw = 360
        ims = []
        for s in shots:
            im = Image.open(root / s["sketch_file"]).convert("RGB")
            ims.append(im.resize((tw, int(im.height * tw / im.width))))
        th = max(i.height for i in ims)
        G, CAP, TOP, cols = 20, 44, 56, min(3, len(ims))
        rows = (len(ims) + cols - 1) // cols
        grid = Image.new("RGB", (G + cols * (tw + G), TOP + rows * (th + CAP + G)), "#ebe7dd")
        d = ImageDraw.Draw(grid)
        seg_id = seg.get("segment_id") or f.stem[len("layer2-"):]
        d.text((G, 16), f"{seg_id}  ·  Codex 分鏡圖", font=font, fill="#111")
        for i, (s, im) in enumerate(zip(shots, ims)):
            x, y = G + (i % cols) * (tw + G), TOP + (i // cols) * (th + CAP + G)
            grid.paste(im, (x, y)); d.rectangle([x, y, x + tw - 1, y + im.height - 1], outline="#111", width=2)
            co = s.get("camera_optics") or {}
            d.text((x, y + im.height + 8), f"{i + 1:02d} {s['shot_id'][-4:]} · {co.get('shot_size', '')} · {s.get('duration', '')}s", font=font, fill="#111")
        gp = root / "images" / f"grid-{seg_id}.png"
        grid.save(gp)
        seg["grid_preview_file"] = gp.relative_to(root).as_posix()
        seg["storyboard_panels"] = [dict(index=i, shot_id=s.get("shot_id"), panel_file=s.get("sketch_file"), sha256=s.get("sketch_sha256"))
                                    for i, s in enumerate(seg.get("shots", []), 1)]
        f.write_text(json.dumps(seg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        out.append(gp)
    return out


def write_back(root: pathlib.Path, job: Dict[str, Any], model: str) -> None:
    f = job["file"]
    seg = json.loads(f.read_text(encoding="utf-8-sig"))
    for s in seg.get("shots", []):
        if s.get("shot_id") == job["shot_id"]:
            pp = root / "panels" / job["filename"]
            s["sketch_file"] = pp.relative_to(root).as_posix()
            s["sketch_sha256"] = _sha256(pp)
            s["sketch_status"] = "generated"
            s["sketch_prompt"] = job["prompt"]
            s["sketch_generation"] = dict(backend="codex", tool="scripts/storyboard/codex_storyboard_panels.py", model=model,
                                          refs=[os.path.relpath(r, root) for _, r in job["refs"]],
                                          grid_file=f"images/grid-{job['segment']}.png")
    f.write_text(json.dumps(seg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Layer 2 → Codex 內建生圖彩色分鏡圖（每鏡一張，綁定已核准參考圖）")
    ap.add_argument("--root", default=".")
    ap.add_argument("--episode", default=None)
    ap.add_argument("--segment", nargs="*", default=None)
    ap.add_argument("--shots", nargs="*", default=None, help="只重畫這些 shot_id")
    ap.add_argument("--model", required=True, help="Codex 模型（必填，避免靜默改用預設模型）")
    ap.add_argument("--parallel", type=int, default=1)
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--keywords", type=pathlib.Path, default=None, help="角色關鍵字／逐鏡覆寫 JSON（預設 staging/codex-panel-refs.json）")
    ap.add_argument("--force", action="store_true", help="連鎖定鏡頭也重畫")
    ap.add_argument("--dry-run", action="store_true", help="只輸出提示詞與參考圖計畫（panels/codex-panel-plan.json）")
    ap.add_argument("--grids-only", action="store_true", help="只重拼分鏡總覽圖")
    args = ap.parse_args(argv)
    root = pathlib.Path(args.root).resolve()
    files = sorted(pathlib.Path(p) for p in glob.glob(str(root / "layer2" / "layer2-*.json")))
    if args.episode:
        files = [f for f in files if f"-{args.episode}-" in f.name]
    if args.segment:
        files = [f for f in files if any(f.stem.startswith(f"layer2-{s}") for s in args.segment)]
    if args.grids_only:
        for g in assemble_grids(root, files):
            print(f"  總覽圖 → {g.relative_to(root)}")
        return 0
    jobs = plan(root, files, args.keywords)
    if args.shots:
        jobs = [j for j in jobs if j["shot_id"] in set(args.shots)]
    if not args.force:
        keep = []
        for j in jobs:
            seg = json.loads(j["file"].read_text(encoding="utf-8-sig"))
            s = next(x for x in seg["shots"] if x["shot_id"] == j["shot_id"])
            if s.get("sketch_status") in LOCKED_STATUSES:
                print(f"  鎖定，略過 {j['shot_id']}")
            else:
                keep.append(j)
        jobs = keep
    for j in jobs:
        if j["missing_refs"]:
            print(f"  ⚠ {j['shot_id']} 缺參考圖：{', '.join(j['missing_refs'])}", file=sys.stderr)
    (root / "panels").mkdir(exist_ok=True)
    plan_path = root / "panels" / "codex-panel-plan.json"
    plan_path.write_text(json.dumps([{k: (str(v) if isinstance(v, pathlib.Path) else v) for k, v in j.items()} for j in jobs],
                                    ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"計畫 {len(jobs)} 鏡 → {plan_path.relative_to(root)}")
    if args.dry_run:
        return 0
    import run_codex_asset_gen as rc
    exe = rc.resolve_codex_executable(None)
    rc.validate_codex_cli(exe)
    out_dir = root / "panels"

    def one(j):
        target = {"filename": j["filename"], "refs": [r for _, r in j["refs"]]}
        try:
            ok = rc.generate_single_asset_codex(target, j["prompt"], out_dir, model=args.model,
                                                timeout_sec=args.timeout, codex_bin=exe, aspect=j["aspect"])
        except rc.UsageLimitHit as hit:
            print(f"⏸ Codex 用量上限（{hit.retry_at}）：{j['shot_id']}")
            ok = False
        return j, ok

    failed = []
    with ThreadPoolExecutor(max_workers=max(1, args.parallel)) as pool:
        for j, ok in pool.map(one, jobs):
            if ok:
                write_back(root, j, args.model)
                print(f"  ✓ {j['shot_id']} → panels/{j['filename']}")
            else:
                failed.append(j["shot_id"])
                print(f"  ✗ {j['shot_id']}")
    touched = sorted({j["file"] for j in jobs})
    for g in assemble_grids(root, touched):
        print(f"  總覽圖 → {g.relative_to(root)}")
    print(f"完成 {len(jobs) - len(failed)} / {len(jobs)}; failed={failed}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
