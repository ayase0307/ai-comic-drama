# prompt_sketch_audit.py - 階段 5 送件前「提示詞 ↔ 構圖圖」逐句核對清單產生器（stdlib）。
# 用法: python scripts/storyboard/prompt_sketch_audit.py --root <專案> [--episode EP01] [--out <md>]
#
# 為什麼要有這支（Eian 2026-11-05 文章對照）：提交生成前，把提示詞的每句話和構圖圖放大核對
# （位置、左右、顏色、人數、道具數、衣服、表情）——實測能查出「杯子差 13%、帽檐一張有一張
# 沒有、左右寫反」這類文字檢查抓不到的錯。本技能的 refcheck／staging 是文字級，構圖圖只有
# 階段 4 的人眼；這支把「逐句 vs 圖」變成送件前的固定清單，由 agent 逐項看圖勾選。
# 只產清單、不擋關；發現不符 → 回 Layer 2 改句或重出構圖，改完重跑。
import argparse
import json
import sys
from pathlib import Path

CHECK_ITEMS = [
    ("位置", "提示詞寫的人在畫面哪裡（左/中/右、前景/背景），圖上一致？主體的頭／眼落在畫面 38% 或 62% 線附近，不在正中央？（Eian 2026-11-05：黃金位構圖）"),
    ("左右", "畫面左右用觀眾視角寫的，沒有寫反？"),
    ("人數", "圖上人數＝提示詞人數？沒有憑空多出來的人？"),
    ("道具", "提示詞提到的關鍵道具在圖上、數量一致？（動作要用的東西首幀必須看得到）"),
    ("服裝", "服裝與設定圖／包母片一致？固定特徵（紋身、佩飾）位置對？"),
    ("表情", "表情對上 shot_intent 的情緒轉變？"),
    ("光影", "光的方向與色溫和相鄰鏡同一光源？"),
    ("動線", "提示詞寫的進出畫方向，圖上有留出空間？"),
]

# fl2v 段追加的幀面檢查（Eian 2026-11-05 首尾幀清單節錄；疊圖另跑 frame_pair_qa.py）
FL2V_ITEMS = [
    ("反應提前", "別人的反應提前擺好：一段就是一個鏡頭，沒法中途切去拍別人——首幀裡安排好誰在前做事、誰在後面看著。"),
    ("留空間", "給動作留空間：東西要落到、飄到的地方提前空出來，人的頭頂也留點空。"),
    ("風向統一", "風往哪邊吹全段統一：圍巾、床單、旗幟的飄向不能互相矛盾。"),
    ("縮小檢查", "縮到手機大小看一遍：遠處的人太小、看不清就要改。"),
    ("多餘物", "放大看有沒有多餘的東西：多一個水壺、多一條奇怪的細線。"),
]

FL2V_NOTE = ("本段 generation_mode=fl2v：先跑 `python scripts/storyboard/frame_pair_qa.py "
             "<首幀> <尾幀>` 疊圖檢查，不該變的區域有高差＝錯位，改圖再送。")


def _resolve_sketch(project_dir: Path, layer2_path: Path, shot: dict, index: int, seg_id: str) -> Path | None:
    """與 build_stage_review 階段 4 同一套候選命名；回第一個存在的檔。"""
    cands: list[Path] = []
    sketch = str(shot.get("sketch_file") or "").strip()
    if sketch:
        p = Path(sketch)
        cands += [p] if p.is_absolute() else [project_dir / p, layer2_path.parent / p]
    sid = str(shot.get("shot_id") or "")
    gsid = str(shot.get("global_shot_id") or sid)
    cands += [
        project_dir / "panels" / f"panel-{index:02d}-{sid}.png",
        layer2_path.parent / "panels" / f"panel-{index:02d}-{sid}.png",
        project_dir / "panels" / f"panel-{seg_id}-{sid}.png",
        project_dir / "panels" / f"panel-{gsid}.png",
        project_dir / "panels" / f"panel-{sid}.png",
    ]
    for c in cands:
        if c.is_file():
            return c
    return None


def build_audit(project_dir: Path, episode: str | None = None) -> tuple[str, list[str]]:
    """回 (markdown, 問題清單)。問題＝缺構圖圖或缺 layer2 檔（只提醒，不擋關）。"""
    layer2_dir = project_dir / "layer2"
    files = sorted(layer2_dir.glob("layer2-*.json")) if layer2_dir.is_dir() else []
    if episode:
        ep = episode.lower()
        files = [p for p in files if ep in p.name.lower()]
    if not files:
        return "", [f"找不到 layer2/layer2-*.json（episode={episode or '全部'}）"]
    problems: list[str] = []
    lines = [
        "# 送件前逐句核對：提示詞 ↔ 構圖圖",
        "",
        "> 逐鏡把提示詞的每句話和構圖圖**放大**對照，逐項勾選；發現不符 → 回 Layer 2 改句或重出構圖，改完重跑本清單。",
        "> REMIX 段特別注意：包母片裡有的東西每一鏡都會出現（包壓過提示詞），核對時把「不該在場的母片物件」也看一眼。",
        "",
    ]
    for path in files:
        data = json.loads(path.read_text(encoding="utf-8"))
        seg_id = str(data.get("segment_id") or path.stem.replace("layer2-", ""))
        mode = str((data.get("metadata") or {}).get("generation_mode") or "r2v")
        lines.append(f"## {seg_id}（generation_mode={mode}）")
        if mode == "fl2v":
            lines.append(f"- {FL2V_NOTE}")
        lines.append("")
        for i, shot in enumerate(data.get("shots", []), start=1):
            sid = str(shot.get("global_shot_id") or shot.get("shot_id") or f"SHOT{i:02d}")
            size = str(((shot.get("camera_optics") or {}).get("shot_size")) or "?")
            sketch = _resolve_sketch(project_dir, path, shot, i, seg_id)
            if sketch:
                try:
                    rel = sketch.resolve().relative_to(project_dir.resolve()).as_posix()
                except ValueError:
                    rel = str(sketch.resolve())
                lines.append(f"### {sid}（{size}）— 構圖圖：`{rel}` ✅")
            else:
                lines.append(f"### {sid}（{size}）— ❌ 找不到構圖圖（先補圖再核對）")
                problems.append(f"{seg_id}/{sid}：找不到構圖圖")
            lines.append("")
            for name, desc in CHECK_ITEMS:
                lines.append(f"- [ ] **{name}**：{desc}")
            if mode == "fl2v":
                for name, desc in FL2V_ITEMS:
                    lines.append(f"- [ ] **{name}**（fl2v 幀面）：{desc}")
            lines.append("")
    return "\n".join(lines), problems


def main() -> int:
    parser = argparse.ArgumentParser(description="產生「提示詞 ↔ 構圖圖」逐句核對清單（只產清單，不擋關）")
    parser.add_argument("--root", default=".", help="專案根目錄")
    parser.add_argument("--episode", help="只列指定集，例如 EP01")
    parser.add_argument("--out", help="輸出 md 路徑（預設 review/prompt-sketch-audit-<episode|all>.md）")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    md, problems = build_audit(root, args.episode)
    if not md:
        for p in problems:
            print(f"[錯誤] {p}", file=sys.stderr)
        return 2
    out = Path(args.out) if args.out else root / "review" / f"prompt-sketch-audit-{(args.episode or 'all').lower()}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    print(f"✅ 已產出核對清單：{out}")
    for p in problems:
        print(f"⚠️ {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
