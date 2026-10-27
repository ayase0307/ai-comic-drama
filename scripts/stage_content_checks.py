#!/usr/bin/env python3
"""階段 0–3 的產物內容檢查（門禁用）。

`project_state.stage_validation_errors(..., strict=True)` 會呼叫這裡：
`h3d next`、`h3d approve --auto` 與 `build_stage_review.py --approve-stage` 都走 strict，
所以 init 留下的空白模板、佔位符、驗證腳本的 FAIL 不會再被當成「產物已齊」或被自動核准。

已核准階段的重新驗證不走 strict（核准快照已綁定內容 hash，改了就失效），
避免舊專案因為新增的檢查而整批失去核准。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

SCRIPTS_DIR = Path(__file__).resolve().parent
for _p in (SCRIPTS_DIR, SCRIPTS_DIR / "adapt"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

# init 模板的佔位符：<...> 內含中文或「|」選項，例如 <角色名>、<xuanhuan_revenge | ...>、C-<slug>。
# 不會誤判 HTML 註解（<!-- -->）、<Picture 1>、<br> 這類英文標記。
_PLACEHOLDER = re.compile(r"<(?!!--)[^<>\n]*(?:[\u4e00-\u9fff]|\||slug)[^<>\n]*>")
_HANDLEBARS = re.compile(r"\{\{[^}\n]+\}\}")
_MAX_LISTED = 5


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig")
    except OSError:
        return ""


def _load_json(path: Path) -> Optional[Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None


def _strip_comments(text: str) -> str:
    """去掉 HTML 註解與 > 引言說明（模板的填寫說明不算產物內容）。"""
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith(">"))


_CARD_LINE = re.compile(r"^\s*(#{2,6}\s|[-*]\s*\*\*[^*]+\*\*\s*[：:]|\|)")


def placeholders_in(text: str, card_lines_only: bool = False) -> List[str]:
    """card_lines_only：只看標題、`- **欄位**：` 與表格列（assets.md 的說明段落常引用 `C-<slug>` 這類規則）。"""
    body = _strip_comments(text)
    if card_lines_only:
        body = "\n".join(l for l in body.splitlines() if _CARD_LINE.match(l))
    # `<技能>/scripts/...` 這種路徑寫法是說明，不是待填欄位。
    found = [m.group(0) for m in _PLACEHOLDER.finditer(body) if not body[m.end():m.end() + 1] == "/"]
    found += _HANDLEBARS.findall(body)
    seen: List[str] = []
    for item in found:
        if item not in seen:
            seen.append(item)
    return seen


def _placeholder_error(rel: str, text: str, card_lines_only: bool = False) -> List[str]:
    found = placeholders_in(text, card_lines_only)
    if not found:
        return []
    sample = "、".join(found[:_MAX_LISTED])
    return [f"{rel} 仍有 {len(found)} 處模板佔位符未填（例如 {sample}）"]


def _field(text: str, label: str) -> Optional[str]:
    match = re.search(rf"^-[ \t]*{re.escape(label)}[ \t]*[：:][ \t]*(.*)$", text, flags=re.M)
    return match.group(1).strip() if match else None


def _decision_value(root: Path, decision_id: str) -> Optional[Any]:
    try:
        import decisions as decisions_mod
        entry = decisions_mod.get(decisions_mod.load(root), decision_id)
    except Exception:  # decisions.json 格式錯誤另有 h3d next 的阻斷訊息
        return None
    return entry.get("value") if entry else None


# ---------------------------------------------------------------- stage 0

def stage0_errors(root: Path) -> List[str]:
    path = root / "project.md"
    if not path.is_file():
        return ["缺少 project.md（先跑 init_project.py）"]
    text = _read(path)
    errors = _placeholder_error("project.md", text)
    style = _field(text, "畫風")
    if style is not None and not style:
        errors.append("project.md 的「畫風」是空白；先和使用者定調（h3d decide style）再寫入")
    aspect_md = _field(text, "aspect_ratio")
    aspect_decided = _decision_value(root, "aspect_ratio")
    md_ratio = re.search(r"\d+\s*:\s*\d+", aspect_md or "")
    md_ratio = md_ratio.group(0).replace(" ", "") if md_ratio else None
    if md_ratio and aspect_decided and str(aspect_decided).replace(" ", "") != md_ratio:
        errors.append(
            f"project.md 的 aspect_ratio（{aspect_md}）與 decisions.json 定案（{aspect_decided}）不一致；"
            "以使用者定案為準改 project.md"
        )
    return errors


# ---------------------------------------------------------------- stage 1

def _ids(values: Iterable[Any]) -> List[str]:
    return [str(v) for v in values if isinstance(v, (str, int))]


def stage1_errors(root: Path) -> List[str]:
    errors: List[str] = []
    md_path = root / "adapt" / "character-bible.md"
    bible_path = root / "adapt" / "bible.json"
    source_path = root / "adapt" / "source.json"
    for rel, p in (("adapt/character-bible.md", md_path), ("adapt/bible.json", bible_path),
                   ("adapt/source.json", source_path)):
        if not p.is_file():
            errors.append(f"缺少 {rel}")
    if errors:
        return errors

    bible = _load_json(bible_path)
    if not isinstance(bible, dict):
        errors.append("adapt/bible.json 無法解析")
        bible = None
    try:
        from validate_character_bible import validate_character_bible
        res = validate_character_bible(_read(md_path), bible)
        for item in res.get("errors", [])[:_MAX_LISTED]:
            errors.append(f"validate_character_bible：{item}")
    except Exception as exc:  # pragma: no cover - 驗證器本身壞掉也要擋
        errors.append(f"validate_character_bible 無法執行：{exc}")

    if bible is not None:
        errors.extend(_placeholder_error("adapt/bible.json", json.dumps(bible, ensure_ascii=False)))

    source = _load_json(source_path)
    if not isinstance(source, dict):
        errors.append("adapt/source.json 無法解析")
    else:
        units = source.get("story_units") or []
        unit_ids = _ids(u.get("unit_id") for u in units if isinstance(u, dict))
        if not unit_ids:
            errors.append("adapt/source.json 沒有任何 story_units")
        if [u for u in units if isinstance(u, dict) and u.get("summary") == "開場核心原著事件"] and len(units) <= 1:
            errors.append("adapt/source.json 還是 init 骨架（只有一條「開場核心原著事件」）；依原著拆出 story_units")
        missing = [m for m in _ids(source.get("must_keep") or []) if m not in unit_ids]
        if missing:
            errors.append(f"adapt/source.json 的 must_keep 對不到 story_units：{'、'.join(missing[:_MAX_LISTED])}")

    outline = root / "adapt" / "series-outline.md"
    if not outline.is_file():
        errors.append("缺少 adapt/series-outline.md（改編方案與段落／分集架構，模板見 references/adapt/templates/series-outline.md）")
    else:
        # 以前只看檔案在不在：直接複製模板（滿是 {{…}}）也能過階段 1 門禁。
        errors.extend(_placeholder_error("adapt/series-outline.md", _read(outline)))
    return errors


# ---------------------------------------------------------------- stage 2

_ASSET_IMAGE_FIELDS = ("設定圖", "母版圖", "服裝設定圖", "三視圖")


def _no_image_scope(root: Path) -> bool:
    """交付範圍定案為不生圖（delivery_scope.no_image）。決定檔壞了就當作要圖（保守）。"""
    try:
        import decisions as decisions_mod
        return bool(decisions_mod.delivery_scope(root).get("no_image"))
    except Exception:
        return False


def _text_card_errors(text: str) -> List[str]:
    cards = re.findall(r"^\s*-\s*\*\*固定描述片段\*\*\s*[：:]\s*`?([^`\n]+)", text, flags=re.M)
    filled = [c for c in cards if not _PLACEHOLDER.search(c) and c.strip()]
    if not filled:
        return ["不生圖（delivery_scope.no_image）：assets.md 需至少一張已填實的文字設定卡（「固定描述片段」）"]
    return []


def stage2_errors(root: Path) -> List[str]:
    path = root / "assets.md"
    if not path.is_file():
        return ["缺少 assets.md"]
    text = _read(path)
    errors = _placeholder_error("assets.md", text, card_lines_only=True)
    if _no_image_scope(root):
        return errors + _text_card_errors(text)
    missing: List[str] = []
    declared = 0
    for label in _ASSET_IMAGE_FIELDS:
        # 反引號內的路徑可以含空白（`images/scene 燈塔-master.png`）；沒有反引號才以空白為界。
        for match in re.finditer(rf"^\s*-\s*\*\*{label}\*\*\s*[：:]\s*(?:`([^`\n]+)`|([^`\s]+))", text, flags=re.M):
            raw = (match.group(1) or match.group(2) or "").strip()
            if _PLACEHOLDER.search(raw):
                continue  # 佔位符已在上面報過
            declared += 1
            if not (root / raw).is_file():
                missing.append(raw)
    if declared == 0 and not errors:
        errors.append("assets.md 沒有登記任何設定圖路徑（角色卡的「設定圖」欄）")
    if missing:
        errors.append(f"assets.md 登記的設定圖有 {len(missing)} 張不存在：{'、'.join(missing[:_MAX_LISTED])}")
    return errors


# ---------------------------------------------------------------- stage 3

_ADAPT_HARD_TAGS = ("MISSING_MUST_KEEP_EVENT", "UNTRACKED_UNIT_OMISSION",
                    "UNREPORTED_SOURCE_GAP", "UNREPORTED_SOURCE_CONTRADICTION")


def _handoff_aspect(value: Any) -> Optional[str]:
    """定案比例 → handoff.schema.json 的 enum（9:16／16:9／other）；看不懂回 None（不擋）。"""
    m = re.fullmatch(r"\s*(\d+)\s*[:：xX×]\s*(\d+)\s*", str(value or ""))
    if not m:
        return None
    ratio = f"{m.group(1)}:{m.group(2)}"
    return ratio if ratio in ("9:16", "16:9") else "other"


def _episode_tag(path: Path) -> str:
    match = re.search(r"ep(\d+)", path.stem, flags=re.I)
    return f"EP{int(match.group(1)):02d}" if match else path.stem


def stage3_errors(root: Path) -> List[str]:
    scripts = sorted(root.glob("script-ep*.md"))
    if not scripts:
        return ["缺少 script-ep*.md 劇本"]
    errors: List[str] = []
    bible = _load_json(root / "adapt" / "bible.json")
    source = _load_json(root / "adapt" / "source.json")
    try:
        from validate_structure import parse_and_validate_script
        from check_continuity import audit_continuity
        from compare_adaptation import evaluate_adaptation
    except Exception as exc:  # pragma: no cover
        return [f"劇本驗證腳本無法載入：{exc}"]

    for script in scripts:
        rel = script.name
        text = _read(script)
        errors.extend(_placeholder_error(rel, text))
        res = parse_and_validate_script(text)
        for item in (res.get("gate_failures") or [])[:3] + (res.get("errors") or [])[:3]:
            errors.append(f"{rel} validate_structure：{item}")

        handoff_path = root / script.name.replace("script-", "handoff-").replace(".md", ".json")
        handoff = _load_json(handoff_path)
        if not isinstance(handoff, dict):
            errors.append(f"缺少或無法解析 {handoff_path.name}（跑 sync_script.py 產生）")
            continue
        decided = _decision_value(root, "aspect_ratio")
        want = _handoff_aspect(decided)
        if want and handoff.get("aspect_ratio") != want:
            errors.append(
                f"{handoff_path.name} 的 aspect_ratio（{handoff.get('aspect_ratio')}）與 decisions.json 定案（{decided}）不一致；"
                "跑 sync_script.py 會自動對齊（階段 4 的 Layer 2 比例照 handoff 產生）"
            )
        episodes = handoff.get("episodes") or []
        for ep in episodes if isinstance(episodes, list) else []:
            if not isinstance(ep, dict):
                continue
            todo = [k for k in ("title", "episode_goal") if str(ep.get(k, "")).strip() in ("", "TODO")]
            if todo:
                errors.append(f"{handoff_path.name} 的 {ep.get('episode_id', '?')} 仍有 TODO 欄位：{'、'.join(todo)}")
        if isinstance(bible, dict):
            try:
                cont = audit_continuity(bible, handoff, text)
                for item in (cont.get("gate_failures") or [])[:3]:
                    errors.append(f"{handoff_path.name} check_continuity：{item}")
            except Exception as exc:
                errors.append(f"{handoff_path.name} check_continuity 執行失敗：{exc}")
        if isinstance(source, dict):
            try:
                adapt = evaluate_adaptation(source, handoff, text, bible if isinstance(bible, dict) else None,
                                            target_episode=_episode_tag(script))
                # 只擋原著對帳的硬錯誤；伏筆洩底是關鍵字比對，逐集過濾時 reveal 位置算不準，
                # 留給 Agent 審查與 McKee lens，不在門禁一票否決。結構／連戲的閘門上面已各自擋過。
                hard = [e for e in adapt.get("errors") or [] if any(tag in e for tag in _ADAPT_HARD_TAGS)]
                for item in hard[:3]:
                    errors.append(f"{rel} compare_adaptation：{item}")
            except Exception as exc:
                errors.append(f"{rel} compare_adaptation 執行失敗：{exc}")
    return errors


CHECKS = {0: stage0_errors, 1: stage1_errors, 2: stage2_errors, 3: stage3_errors}


def content_errors(root: Path, stage: int) -> List[str]:
    check = CHECKS.get(int(stage))
    return check(Path(root)) if check else []


def main(argv: Optional[List[str]] = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description="檢查階段 0–3 產物是否還是模板或驗證未過")
    parser.add_argument("--root", default=".")
    parser.add_argument("--stage", type=int, required=True, choices=sorted(CHECKS))
    args = parser.parse_args(argv)
    errors = content_errors(Path(args.root).resolve(), args.stage)
    for item in errors:
        print(f"❌ {item}")
    if not errors:
        print(f"✅ stage-{args.stage} 產物內容檢查通過")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
