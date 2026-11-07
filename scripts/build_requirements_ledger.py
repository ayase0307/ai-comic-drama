#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# build_requirements_ledger.py - 監督者要求帳本與查核包產生器（stdlib）。
# 用法:
#   python scripts/build_requirements_ledger.py --root <專案>                       # 只重建帳本
#   python scripts/build_requirements_ledger.py --root <專案> --stage 5             # 帳本＋該階段審核快照產出的查核包
#   python scripts/build_requirements_ledger.py --root <專案> --all                 # 帳本＋全部已核准階段產出（累積查核）
#   python scripts/build_requirements_ledger.py --root <專案> --inputs script-ep01.md
#   python scripts/build_requirements_ledger.py --root <專案> --quotes 對話摘錄.md  # 使用者原話摘錄，內嵌進帳本
#
# 為什麼要有這支（Eian 2026-11-05 文章對照·四線的「監督」）：h3d decide 只記「形式化定案」，
# 使用者隨口說過的偏好（「不要 glossy」「旁白少一點」）沒走到 decide 的，只存在對話記憶裡——
# 換 session、跑過幾個階段後就沒人記得，產出錯了也沒有檢查會抓。盲審問「觀眾看不看得懂」，
# 確定性腳本問「格式與物理」，監督者問「使用者說過的話有沒有被忘記」。本腳本把要求帳本組出來：
# decisions.json 每條定案（rule＋定案值＋使用者原話）＋ inbox 待決卡 ＋ --quotes 手動摘錄（全文內嵌），
# 並把「要查核的產出檔」打包成只含材料、不含結論的查核包（審核頁／verdicts／QA 報告一律不進包）。
# 規則見 references/supervision.md。
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

SUPERVISION_DIR = "review/supervision"

# 查核包不複製的二進位檔（列進 manifest 的 skipped_binary，監督者知道它們存在但不在包內）
BINARY_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff",
                   ".mp4", ".mov", ".webm", ".mkv", ".avi",
                   ".wav", ".mp3", ".m4a", ".flac", ".aac", ".psd", ".zip"}


def _die(msg: str) -> None:
    print(f"[錯誤] {msg}", file=sys.stderr)
    sys.exit(2)


def _load_decisions(root: Path) -> list[dict]:
    path = root / "decisions.json"
    if not path.is_file():
        _die(f"找不到 {path}——要求帳本以 decisions.json 為主來源（沒有定案的專案先跑 h3d decide）")
    data = json.loads(path.read_text(encoding="utf-8"))
    entries = []
    for d in data.get("decisions", []):
        src = d.get("source") or {}
        entries.append({
            "id": str(d.get("id", "")),
            "rule": str(d.get("rule", "")),
            "value": d.get("value", ""),
            "quote": str(src.get("quote", "")),
            "date": str(src.get("date", "")),
            "stages": d.get("stages") or [],
        })
    return entries


def _load_pending_cards(root: Path) -> list[dict]:
    path = root / "review" / "inbox.json"
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return [c for c in data.get("cards", []) if c.get("kind") == "decision"]


def _fmt_value(value) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return " ".join(text.split())


def _project_title(root: Path) -> str:
    path = root / "review" / "project-state.json"
    if path.is_file():
        try:
            return str(json.loads(path.read_text(encoding="utf-8")).get("title") or "")
        except (json.JSONDecodeError, OSError):
            return ""
    return ""


def _render_ledger(entries: list[dict], cards: list[dict], quotes: list[tuple[str, str]],
                   root: Path) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    title = _project_title(root)
    heading = f"# 要求帳本（supervision requirements ledger）{f'：{title}' if title else ''}"
    lines = [
        heading,
        "",
        f"> 產生：`scripts/build_requirements_ledger.py --root <專案>`｜{now}",
        f"> 來源：decisions.json（{len(entries)} 條定案）＋ review/inbox.json（{len(cards)} 張待決卡）"
        f"＋ 手動摘錄（{len(quotes)} 檔）",
        "> 用途：監督者（fresh subagent）逐條查產出有沒有忘記使用者要求（規則見 references/supervision.md）。",
        "> **主 agent 不准手改本檔**——要求變了就 `h3d decide` 或 `--quotes` 進帳本重跑腳本。",
        "",
        "## 一、定案要求（decisions.json）",
        "",
    ]
    for i, e in enumerate(entries, 1):
        stages = ", ".join(str(s) for s in e["stages"]) if e["stages"] else "未標"
        lines.append(f"### R{i:02d} {e['id']}（適用階段：{stages}）")
        if e["rule"]:
            lines.append(f"- 要求：{e['rule']}")
        lines.append(f"- 定案值：{_fmt_value(e['value'])}")
        if e["quote"]:
            lines.append(f"- 使用者原話（{e['date'] or '未記日期'}）：「{e['quote']}」")
        lines.append("")
    lines += ["## 二、待定案（review/inbox.json）", "",
              "> 還沒拍板，不算違反；產出若已經照建議走，監督者要註記「照建議先行」。", ""]
    for i, c in enumerate(cards, 1):
        blocking = "・擋下一步" if c.get("blocking") else ""
        lines.append(f"### P{i:02d} {c.get('id', '')}（階段 {c.get('stage', '?')}{blocking}）")
        lines.append(f"- 題目：{c.get('title', '')}")
        if c.get("recommendation"):
            lines.append(f"- 建議：{c['recommendation']}")
        if c.get("if_ignored"):
            lines.append(f"- 不定案的後果：{c['if_ignored']}")
        lines.append("")
    lines += ["## 三、手動摘錄（未整理的使用者原話）", ""]
    if not quotes:
        lines += ["（本帳本沒有手動摘錄。使用者隨口說過、但沒走到 `h3d decide` 的要求，",
                  "用 `--quotes <對話摘錄檔>` 進帳本；監督者會自行讀檔把要求一條條對上。）", ""]
    else:
        lines += ["> 以下是摘錄檔全文。監督者自行閱讀，把裡面的要求整理成「額外要求」（自編 X01、X02…）一併查核。", ""]
        for name, content in quotes:
            lines.append(f"### 摘錄：`{name}`")
            lines.append("")
            lines.append("````text")
            lines.append(content.rstrip())
            lines.append("````")
            lines.append("")
    return "\n".join(lines)


def _stage_snapshot_artifacts(root: Path, stage: int | None, all_approved: bool) -> list[str]:
    path = root / "review" / "project-state.json"
    if not path.is_file():
        _die(f"找不到 {path}——查核包的產出清單取自各階段審核快照（沒有狀態檔時改用 --inputs 手動圈選）")
    data = json.loads(path.read_text(encoding="utf-8"))
    stages = data.get("stages", {})

    def _stage_no(key: str) -> int:
        try:
            return int(key.rsplit("-", 1)[1])
        except (IndexError, ValueError):
            return 99

    if all_approved:
        picked = [stages[k] for k in sorted(stages, key=_stage_no)
                  if stages[k].get("status") == "approved"]
    else:
        v = stages.get(f"stage-{stage}")
        if v is None:
            _die(f"project-state.json 沒有 stage-{stage}（可用階段：{', '.join(sorted(stages, key=_stage_no))}）")
        picked = [v]
    artifacts: list[str] = []
    for v in picked:
        for a in (v.get("review_snapshot") or {}).get("artifacts", []):
            rel = a.get("path", "")
            if rel and rel not in artifacts:
                artifacts.append(rel)
    if not artifacts:
        scope = "全部已核准階段" if all_approved else f"stage-{stage}"
        _die(f"{scope} 的審核快照沒有記任何產出——先跑 build_stage_review 重建快照，或改用 --inputs 手動圈選")
    return artifacts


def _copy_targets(root: Path, bundle: Path, relpaths: list[str]) -> tuple[list[str], list[str]]:
    copied, skipped = [], []
    for rel in relpaths:
        src = root / rel
        if not src.is_file():
            print(f"[警告] 快照產出找不到，略過：{src}", file=sys.stderr)
            continue
        if src.suffix.lower() in BINARY_SUFFIXES:
            skipped.append(rel)
            continue
        dest = bundle / "files" / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        copied.append(rel)
    return copied, skipped


def _copy_inputs(root: Path, inputs: list[str], bundle: Path) -> list[str]:
    copied = []
    for raw in inputs:
        p = Path(raw)
        src = p if p.is_absolute() else root / p
        if not src.is_file():
            _die(f"找不到輸入檔：{src}")
        rel = src.relative_to(root).as_posix() if src.is_relative_to(root) else src.name
        dest = bundle / "files" / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        copied.append(rel)
    return copied


def _load_quotes(root: Path, quote_paths: list[str]) -> list[tuple[str, str]]:
    quotes = []
    for raw in quote_paths:
        p = Path(raw)
        src = p if p.is_absolute() else root / p
        if not src.is_file():
            _die(f"找不到摘錄檔：{src}")
        try:
            content = src.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            _die(f"摘錄檔不是 UTF-8 文字檔：{src}")
        rel = src.relative_to(root).as_posix() if src.is_relative_to(root) else src.name
        quotes.append((rel, content))
    return quotes


def build(root: Path, stage: int | None, all_approved: bool, inputs: list[str],
          quote_paths: list[str]) -> Path:
    if stage is not None and all_approved:
        _die("--stage 與 --all 只能給一個")
    entries = _load_decisions(root)
    cards = _load_pending_cards(root)
    quotes = _load_quotes(root, quote_paths)
    ledger_text = _render_ledger(entries, cards, quotes, root)

    sup_dir = root / SUPERVISION_DIR
    sup_dir.mkdir(parents=True, exist_ok=True)
    ledger_path = sup_dir / "requirements.md"
    ledger_path.write_text(ledger_text, encoding="utf-8")
    print(f"✅ 要求帳本：{ledger_path}")
    print(f"   定案 {len(entries)} 條＋待決 {len(cards)} 張＋摘錄 {len(quotes)} 檔")

    if stage is None and not all_approved and not inputs:
        print("   下一步：--stage N／--all／--inputs 組查核包，開 fresh subagent 逐條查（references/supervision.md）")
        return ledger_path

    tag = f"stage{stage}" if stage is not None else ("all" if all_approved else "inputs")
    bundle = sup_dir / f"check-{tag}"
    if bundle.exists():
        shutil.rmtree(bundle)
    bundle.mkdir(parents=True)
    (bundle / "requirements.md").write_text(ledger_text, encoding="utf-8")

    snapshot_targets: list[str] = []
    skipped: list[str] = []
    if stage is not None or all_approved:
        snapshot_targets = _stage_snapshot_artifacts(root, stage, all_approved)
    copied_snapshot, skipped = _copy_targets(root, bundle, snapshot_targets)
    copied_inputs = _copy_inputs(root, inputs, bundle)

    if not copied_snapshot and not copied_inputs:
        _die("查核包裡沒有任何產出檔——檢查 --stage/--inputs（二進位資產不算查核對象）")

    manifest = {
        "stage": stage if stage is not None else ("all" if all_approved else "inputs"),
        "targets": copied_snapshot,
        "skipped_binary": skipped,
        "manual_inputs": copied_inputs,
        "ledger": {"decisions": len(entries), "pending": len(cards), "quotes": len(quotes)},
        "note": "監督查核包：只含要求帳本與產出材料。審核頁、verdicts、QA 報告一律不在包內；"
                "監督 agent 只准讀這個資料夾。",
    }
    (bundle / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                                           encoding="utf-8")
    print(f"✅ 監督查核包：{bundle}")
    print(f"   產出：{len(copied_snapshot)} 檔（快照）＋{len(copied_inputs)} 檔（手動）；二進位略過 {len(skipped)} 檔")
    print("   下一步：開一個 fresh subagent，只給它這個資料夾路徑（規則見 references/supervision.md）")
    return bundle


def main() -> int:
    parser = argparse.ArgumentParser(description="組出監督者要求帳本（與「只含材料、不含結論」的監督查核包）")
    parser.add_argument("--root", default=".", help="專案根目錄")
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument("--stage", type=int, help="查核包帶該階段審核快照的產出（review/project-state.json）")
    scope.add_argument("--all", action="store_true", help="查核包帶全部已核准階段的產出（累積查核／接手專案）")
    parser.add_argument("--inputs", nargs="+", help="手動指定查核對象檔（相對 --root 或絕對路徑）")
    parser.add_argument("--quotes", nargs="+", help="使用者原話摘錄檔（對話節錄、筆記），全文內嵌進帳本")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    build(root, args.stage, args.all, args.inputs or [], args.quotes or [])
    return 0


if __name__ == "__main__":
    sys.exit(main())
