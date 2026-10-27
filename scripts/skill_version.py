#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""技能版本與資料格式版本的唯一來源，以及製作專案的「版本章」。

* 技能版本：repo 根目錄 `VERSION`（SemVer，見 docs/RELEASING.md）。
* 資料格式版本：`SCHEMA_VERSIONS` 集中列出各 JSON 產物的 schema_version，
  改格式時改這裡並在 CHANGELOG 記一筆。
* 版本章：`h3d init`（init_project.py）建立專案時把兩者寫進
  review/project-state.json 的 `skill_version`；`h3d next` 比對，
  技能比專案新就提示「規則可能變了」，資料格式不相容就提示遷移。
  看過 CHANGELOG 後用 `h3d version --root . --accept` 更新版本章。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SCRIPTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPTS_DIR.parent
VERSION_FILE = REPO_ROOT / "VERSION"
CHANGELOG = REPO_ROOT / "CHANGELOG.md"

# 各產物目前的 schema_version（改格式時同步改對應模組與這張表；tests 會對帳）
SCHEMA_VERSIONS: Dict[str, int] = {
    "project_state": 2,     # review/project-state.json（project_state.py）
    "decisions": 1,         # decisions.json（decisions.py）
    "deps": 2,              # 依賴帳本（storyboard/deps.py）
    "failure_catalog": 2,   # 失敗目錄（storyboard/failure_catalog.py）
}

_SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:[-+].*)?$")


def skill_version() -> str:
    try:
        text = VERSION_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return "0.0.0"
    return text or "0.0.0"


def parse(version: str) -> Tuple[int, int, int]:
    m = _SEMVER.match(str(version or "").strip().lstrip("v"))
    if not m:
        raise ValueError(f"不是 SemVer 版號：{version!r}")
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def stamp() -> Dict[str, Any]:
    """寫進專案狀態檔的版本章。"""
    return {
        "skill": skill_version(),
        "schemas": dict(SCHEMA_VERSIONS),
        "stamped_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def changelog_since(old: str, limit: int = 12) -> List[str]:
    """CHANGELOG 中比 old 新的各版標題（最新在前）。"""
    try:
        text = CHANGELOG.read_text(encoding="utf-8")
    except OSError:
        return []
    try:
        old_t = parse(old)
    except ValueError:
        old_t = (0, 0, 0)
    out: List[str] = []
    for m in re.finditer(r"^## \[(\d+\.\d+\.\d+)\][^\n]*", text, re.M):
        try:
            if parse(m.group(1)) > old_t:
                out.append(m.group(0)[3:].strip())
        except ValueError:
            continue
    return out[:limit]


def check_project(state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """比對專案版本章與目前技能；沒事回 None。"""
    current = skill_version()
    stamp_ = state.get("skill_version") if isinstance(state, dict) else None
    if not isinstance(stamp_, dict) or not stamp_.get("skill"):
        return {
            "level": "info",
            "project": None,
            "current": current,
            "message": (f"這個專案沒有技能版本章（v0.9.0 之前建立）。確認流程照目前規則走後，"
                        f"執行 h3d version --root . --accept 蓋章（目前 v{current}）。"),
            "changes": [],
        }
    project = str(stamp_.get("skill"))
    try:
        p, c = parse(project), parse(current)
    except ValueError:
        return {"level": "warn", "project": project, "current": current,
                "message": f"版本章格式不對（{project!r}）；執行 h3d version --root . --accept 重蓋。", "changes": []}
    schema_diffs = []
    old_schemas = stamp_.get("schemas") if isinstance(stamp_.get("schemas"), dict) else {}
    for name, now in SCHEMA_VERSIONS.items():
        before = old_schemas.get(name)
        if isinstance(before, int) and before != now:
            schema_diffs.append(f"{name} {before}→{now}")
    if p == c and not schema_diffs:
        return None
    if p > c:
        return {"level": "warn", "project": project, "current": current,
                "message": (f"專案由較新的技能 v{project} 建立，目前執行的是 v{current}；"
                            "請先更新 repo（git pull）再繼續，避免用舊規則覆寫。"), "changes": []}
    changes = changelog_since(project)
    msg = f"技能已從 v{project} 更新到 v{current}，規則或門禁可能變了。"
    if schema_diffs:
        msg += "資料格式有變（" + "、".join(schema_diffs) + "），照 CHANGELOG 的遷移說明處理。"
    msg += "看過 CHANGELOG 後建議重跑本階段 audit／審查，再執行 h3d version --root . --accept 更新版本章。"
    return {"level": "warn" if (schema_diffs or c[:2] != p[:2]) else "info",
            "project": project, "current": current, "message": msg,
            "changes": changes, "schema_changes": schema_diffs}


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="h3d version", description="印出技能版本／資料格式版本；--root 比對專案版本章，--accept 更新版本章")
    parser.add_argument("--root", type=Path, default=None, help="製作專案根目錄")
    parser.add_argument("--accept", action="store_true", help="已看過 CHANGELOG，把專案版本章更新為目前技能版本")
    parser.add_argument("--json", action="store_true", help="以 JSON 輸出")
    args = parser.parse_args(argv)

    result: Dict[str, Any] = {"skill": skill_version(), "schemas": dict(SCHEMA_VERSIONS)}
    if args.root is not None:
        if str(SCRIPTS_DIR) not in sys.path:
            sys.path.insert(0, str(SCRIPTS_DIR))
        import project_state as ps
        root = Path(args.root).expanduser().resolve()
        if not ps.state_path(root).is_file():
            print(f"❌ 找不到 {ps.state_path(root)}", file=sys.stderr)
            return 2
        state = ps.load_state(root)
        if args.accept:
            state["skill_version"] = stamp()
            ps.save_state(root, state)
            result["project"] = state["skill_version"]
            result["notice"] = None
        else:
            result["project"] = state.get("skill_version")
            result["notice"] = check_project(state)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    print(f"ai-comic-drama v{result['skill']}")
    print("資料格式：" + "、".join(f"{k}={v}" for k, v in result["schemas"].items()))
    if args.root is not None:
        proj = result.get("project") or {}
        print(f"專案版本章：{('v' + proj['skill']) if proj.get('skill') else '（無）'}")
        notice = result.get("notice")
        if args.accept:
            print(f"✅ 已更新版本章為 v{result['skill']}")
        elif notice:
            print(("⚠️ " if notice["level"] == "warn" else "ℹ️ ") + notice["message"])
            for line in notice.get("changes", []):
                print(f"  - {line}")
        else:
            print("✅ 專案與目前技能版本一致")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
