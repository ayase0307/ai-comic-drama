#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""h3d：把散在 scripts/ 的產線工具收成一個入口。

原本要記五個路徑與各自的旗標（compile_level2_to_h3、audit_refs_and_segments、
verify_video_shot、submit_h3_segments、deps、doctor、failure_catalog）。
這一層只做三件事：

  1. **路由**：`h3d <command>` 轉呼叫既有模組，不改任何行為、不重複實作。
  2. **統一參數慣例**：`--root` 之類的相對路徑以專案根目錄解析。
  3. **組合查詢**：`h3d status` 一次看階段門禁、依賴帳本、送件帳本、失敗目錄。
  4. **決定下一步**：`h3d next` 只印目前階段、卡在哪、下一步唯一一條指令與該讀的 reference。

開工規則：先跑 `h3d next --root <專案>`；使用者定案一律 `h3d decide`；
階段 6 逐段結論一律 `h3d verdict`；要人決定的事用 `h3d inbox` 交給使用者；
符合授權的階段用 `h3d approve --auto`；不准手改 review/project-state.json。

設計原則：這裡不准有第二套邏輯。所有規則都留在原本的模組裡，
h3d 只是名字好記、少打字的門面；每個子命令都保留 `--help`。
"""
from __future__ import annotations

import argparse
import importlib
import inspect
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

SCRIPTS_DIR = Path(__file__).resolve().parent
STORYBOARD_DIR = SCRIPTS_DIR / "storyboard"
REVIEW_DIR = SCRIPTS_DIR / "review"
EXTRA_DIRS = [SCRIPTS_DIR / name for name in ("runner", "voice", "edit")]
for candidate in (str(SCRIPTS_DIR), str(STORYBOARD_DIR), str(REVIEW_DIR), *map(str, EXTRA_DIRS)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

# command -> (module, description)
COMMANDS: Dict[str, str] = {
    "next": "下一步：目前階段、卡在哪、唯一一條指令、該讀的 reference（--json）",
    "decide": "把使用者定案寫進 decisions.json（必附 --quote 使用者原話）",
    "verdict": "階段 6 逐段目視結論寫進 review/verdicts.json；--summary 依驗收政策分類；import 轉舊格式",
    "inbox": "決策收件匣 review/inbox.html：只列需要使用者決定的事（手機優先、內嵌縮圖）",
    "approve": "--auto：沒有未決卡且符合 decisions 政策時自動核准並記錄依據",
    "doctor": "本機環境自檢（GPU／ffmpeg／服務 port／-vsync）",
    "sketch": "免生圖 SVG 構圖分鏡總覽圖（階段 4 構圖來源，回寫 sketch_file 供審核門禁）",
    "crop": "依比例／格位裁設定板頭像（輸出 tmp/crops，不進 images/）",
    "compile": "Layer 2 → H3 六段式提示詞與 segments（--check 可同時審查）",
    "audit": "分段參考圖／主體定義／台詞預算的確定性對帳",
    "author": "逐鏡撰寫審查（防偷懶 E30–E38，references/prompt-authoring.md）",
    "qa": "影片自動審查（時長／色彩／分鏡總覽圖／證據分級）",
    "motion": "階段 6 動態 QA（光流量凍結／定住／起手延遲）＋自動提案變速清單 videos/speed-ramps.json",
    "ramp": "依已核准的變速清單產 videos/ramped/<段>.mp4（原片不動，台詞區 1×＋音訊相關驗證）",
    "submit": "送件到 FreeVideo（含能力校驗與時長斷言）",
    "collect": "只收已完成但沒下載的工作（不送新件）",
    "run": "階段 6 送件 runner（--plan）：單例鎖、佇列檢查、暫停／續跑（--pause）、進度檔（--status）",
    "probe": "送件前查 API schema 與已安裝 LoRA，缺的直接擋並列替代",
    "voice": "階段 7 固定流程 voice align：ASR 對位、畫外句區間壓原聲（-22 dB）、響度標準化",
    "concat": "Concat adapter：plan／build 全集單一剪輯專案（T1 影片、T2 字幕、T3 畫外音）",
    "resume": "先 collect，再補送尚未產出的分段（ledger 去重）",
    "assemble": "配音、字幕與成片組裝",
    "deps": "segment 級依賴帳本（--record／--status）",
    "catalog": "失敗目錄（--list／--check／--acks）",
    "ack": "記錄失敗目錄的 ack 憑證（綁定提示詞 hash 與目錄版本）",
    "status": "綜合狀態：階段門禁＋依賴帳本＋送件帳本＋失敗目錄",
}

MODULE_FOR = {
    "next": "next_step",
    "decide": "decisions",
    "verdict": "verdicts",
    "inbox": "inbox",
    "approve": "auto_approve",
    "doctor": "doctor",
    "sketch": "svg_storyboard_grid",
    "crop": "crop_sheet",
    "compile": "compile_layer2_to_h3",
    "audit": "audit_refs_and_segments",
    "author": "prompt_authoring",
    "qa": "verify_video_shot",
    "motion": "motion_qa",
    "ramp": "speed_ramp",
    "submit": "submit_h3_segments",
    "collect": "submit_h3_segments",
    "run": "fv_runner",
    "probe": "fv_probe",
    "voice": "voice_align",
    "concat": "concat_adapter",
    "resume": "submit_h3_segments",
    "assemble": "assemble_episode",
    "deps": "deps",
    "catalog": "failure_catalog",
    "ack": "failure_catalog",
}

# 需要自動補上前置旗標的子命令
IMPLIED_FLAGS = {
    "collect": ["--collect"],
    "resume": ["--resume"],
    "ack": ["--ack"],
}


def _load(command: str):
    name = MODULE_FOR[command]
    try:
        return importlib.import_module(name)
    except ImportError as exc:  # pragma: no cover - 檔案缺失時
        raise SystemExit(f"❌ 找不到模組 {name}：{exc}")


def _invoke(module, argv: List[str]) -> int:
    """呼叫模組的 main()；有 argv 參數就傳，沒有就暫時改寫 sys.argv。"""
    main = getattr(module, "main", None)
    if main is None:  # pragma: no cover
        raise SystemExit(f"❌ {module.__name__} 沒有 main()")
    params = inspect.signature(main).parameters
    if "argv" in params:
        return int(main(argv) or 0)
    previous = sys.argv
    try:
        sys.argv = [module.__file__ or module.__name__] + list(argv)
        return int(main() or 0)
    finally:
        sys.argv = previous


def _stage_summary(root: Path) -> List[str]:
    state_path = root / "review" / "project-state.json"
    if not state_path.is_file():
        return ["（沒有 review/project-state.json）"]
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"（project-state.json 無法解析：{exc}）"]
    try:
        import project_state as ps
    except ImportError:  # pragma: no cover
        ps = None
    lines = []
    stages = payload.get("stages") or payload
    if isinstance(stages, dict):
        for key in sorted(stages):
            entry = stages[key]
            if not isinstance(entry, dict):
                continue
            stored = str(entry.get("status") or entry.get("approved") or "未記錄")
            effective = stored
            # 顯示「實際有效」而不是「最後一次寫入的狀態」：內容一改，核准就該看得出來失效。
            if ps is not None and stored == "approved" and key.startswith("stage-"):
                try:
                    stage = int(key.split("-", 1)[1])
                    if not ps.is_approved(root, stage):
                        effective = "approved（快照已失效，需重審）"
                except Exception:  # pragma: no cover - 狀態檔格式異常時不要讓 status 崩潰
                    effective = stored
            lines.append(f"  {key}: {effective}")
    return lines or ["（狀態檔沒有 stage 記錄）"]


def _ledger_summary(root: Path) -> List[str]:
    ledgers = sorted(root.glob("videos/**/_fv-job-ledger.json"))
    if not ledgers:
        return ["（沒有送件 ledger）"]
    lines = []
    for ledger in ledgers:
        try:
            payload = json.loads(ledger.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            lines.append(f"  {ledger.relative_to(root).as_posix()}：無法解析（{exc}）")
            continue
        counts: Dict[str, int] = {}
        for job in payload.get("jobs", []) or []:
            status = str(job.get("status") or "unknown")
            counts[status] = counts.get(status, 0) + 1
        summary = ", ".join(f"{key}={value}" for key, value in sorted(counts.items())) or "（空）"
        lines.append(f"  {ledger.relative_to(root).as_posix()}：{summary}")
    return lines


def cmd_status(root: Path, as_json: bool) -> int:
    import deps
    import failure_catalog

    report: Dict[str, Any] = {"root": str(root)}
    deps_report = deps.status(root)
    report["deps"] = deps_report
    try:
        catalog = failure_catalog.load_catalog(root)
        report["catalog"] = {
            "entries": len(catalog["entries"]),
            "enforced": [e["id"] for e in catalog["entries"] if e.get("enforce") == "error"],
        }
    except failure_catalog.CatalogError as exc:
        report["catalog"] = {"error": str(exc)}

    if as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"專案：{root}")
        print("\n[階段門禁]")
        for line in _stage_summary(root):
            print(line)
        print("\n[依賴帳本]")
        print(deps.render(deps_report))
        print("\n[送件帳本]")
        for line in _ledger_summary(root):
            print(line)
        catalog_info = report["catalog"]
        print("\n[失敗目錄]")
        if "error" in catalog_info:
            print(f"  ⚠️ {catalog_info['error']}")
        else:
            enforced = ", ".join(catalog_info["enforced"]) or "無"
            print(f"  {catalog_info['entries']} 條（enforce=error：{enforced}）")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="h3d",
        description="AI 漫劇產線單一入口（把 scripts/ 的工具收成一個名字）",
        epilog="每個子命令都支援 --help，例如：h3d compile --help",
    )
    parser.add_argument("--list", action="store_true", help="列出所有子命令")
    parser.add_argument("--root", type=Path, default=None, help="專案根目錄（給 status／next／decide／verdict 用）")
    parser.add_argument("--json", action="store_true", help="status／next 以 JSON 輸出")
    parser.add_argument("command", nargs="?", help="子命令（見 --list）")
    parser.add_argument("args", nargs=argparse.REMAINDER, help="子命令參數")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.list or not args.command:
        print("h3d 子命令：")
        for name, description in COMMANDS.items():
            print(f"  {name:9s} {description}")
        return 0

    command = args.command
    if command not in COMMANDS:
        print(f"❌ 未知子命令：{command}（可用：{', '.join(COMMANDS)}）", file=sys.stderr)
        return 2

    if command == "status":
        # 允許 `h3d --root X status` 與 `h3d status --root X` 兩種寫法
        sub = argparse.ArgumentParser(add_help=False)
        sub.add_argument("--root", type=Path, default=args.root or Path("."))
        sub.add_argument("--json", action="store_true")
        known, _ = sub.parse_known_args(list(args.args))
        return cmd_status(Path(known.root).resolve(), known.json or args.json)

    module = _load(command)
    passthrough = list(args.args)
    if passthrough and passthrough[0] == "--":
        passthrough = passthrough[1:]
    passthrough = IMPLIED_FLAGS.get(command, []) + passthrough
    if command in ("next", "decide", "verdict", "inbox", "approve", "run"):
        # 允許 `h3d --root X next` 與 `h3d next --root X` 兩種寫法
        if args.root is not None and "--root" not in passthrough:
            passthrough += ["--root", str(args.root)]
        if args.json and "--json" not in passthrough:
            passthrough.append("--json")
    return _invoke(module, passthrough)


if __name__ == "__main__":
    raise SystemExit(main())
