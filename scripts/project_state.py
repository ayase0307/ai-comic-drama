"""Canonical project review state and artifact fingerprints for stage gates."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Iterable

STATE_REL = Path("review") / "project-state.json"
LEGACY_STATE_RELS = (Path("project-state.json"),)
STAGE_TITLES = {
    0: "專案定調與門禁", 1: "改編與角色設定", 2: "資產與設定圖",
    3: "漫劇劇本與交接", 4: "分鏡與構圖", 5: "H3 提示詞包",
    6: "影片片段生成審查", 7: "配音字幕與成片交付",
}


def stage_key(stage: int | str) -> str:
    value = str(stage)
    return value if value.startswith("stage-") else f"stage-{int(value)}"


def state_path(root: Path) -> Path:
    return root / STATE_REL


def _normalize_state(raw: Any, root: Path) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raw = {}
    old_stages = raw.get("stages") if isinstance(raw.get("stages"), dict) else {}
    stages: dict[str, dict[str, Any]] = {}
    for i in range(8):
        key = stage_key(i)
        entry = old_stages.get(key, old_stages.get(str(i), {}))
        if not isinstance(entry, dict):
            entry = {}
        status = entry.get("status", "draft" if i == 0 else "locked")
        # An approval without a content fingerprint cannot be trusted after migration.
        if status in ("approved", "completed") and (
            not entry.get("approval_snapshot") or (i > 0 and not entry.get("approval_dependencies"))
        ):
            status = "draft"
        stages[key] = {
            **entry,
            "id": key,
            "title": entry.get("title", STAGE_TITLES[i]),
            "status": status,
        }
    try:
        current_stage = int(raw.get("current_stage", 0) or 0)
    except (TypeError, ValueError) as exc:
        raise ValueError("project-state current_stage 必須是 0 到 7 的整數") from exc
    if current_stage < 0 or current_stage > 7:
        raise ValueError("project-state current_stage 必須是 0 到 7 的整數")
    return {
        **raw,
        "schema_version": 2,
        "project_dir": str(root.resolve()),
        "current_stage": current_stage,
        "stages": stages,
    }


def initial_state(title: str = "", project_id: str = "") -> dict[str, Any]:
    state = _normalize_state({"title": title, "project_id": project_id, "current_stage": 0, "stages": {}}, Path.cwd())
    state.pop("project_dir", None)
    return state


def load_state(root: Path) -> dict[str, Any]:
    candidates = [state_path(root), *(root / rel for rel in LEGACY_STATE_RELS)]
    for path in candidates:
        if path.exists():
            try:
                raw = json.loads(path.read_text(encoding="utf-8-sig"))
            except (OSError, json.JSONDecodeError) as exc:
                raise ValueError(f"無法讀取專案狀態 {path}: {exc}") from exc
            return _normalize_state(raw, root)
    return _normalize_state({}, root)


INTEGRITY_KEY = "_integrity"


def _integrity_digest(payload: dict[str, Any]) -> str:
    body = {k: v for k, v in payload.items() if k != INTEGRITY_KEY}
    return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def save_state(root: Path, state: dict[str, Any]) -> None:
    path = state_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = _normalize_state(state, root)
    normalized.pop(INTEGRITY_KEY, None)
    # 只有本模組寫入時才蓋這個戳記；手改 project-state.json 會讓戳記對不上，
    # `h3d next` 會把它當成阻斷項，要求走正門（build_stage_review.py）重建。
    normalized[INTEGRITY_KEY] = {"writer": "project_state.save_state", "sha256": _integrity_digest(normalized)}
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(normalized, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def state_integrity(root: Path) -> str:
    """回傳 ok／missing（舊檔或未經本模組寫入）／tampered（寫入後被手改）／absent（無狀態檔）。"""
    path = state_path(root)
    if not path.is_file():
        return "absent"
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return "tampered"
    stamp = raw.get(INTEGRITY_KEY) if isinstance(raw, dict) else None
    if not isinstance(stamp, dict) or not stamp.get("sha256"):
        return "missing"
    return "ok" if stamp["sha256"] == _integrity_digest(raw) else "tampered"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve(root: Path, raw: str | Path) -> Path:
    path = Path(raw)
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def _files_for_stage(root: Path, stage: int) -> list[Path]:
    fixed: dict[int, list[str]] = {
        0: ["project.md"],
        1: ["adapt/character-bible.md", "adapt/bible.json", "adapt/source.json"],
        2: ["assets.md", "assets/reference-manifest.json", "assets/character-design-v2.json", "assets/character-design-v2.md"],
        3: [],
        4: [],
        5: [],
        6: [],
        7: [],
    }
    files = [root / name for name in fixed.get(stage, []) if (root / name).is_file()]
    patterns = {
        2: (p for p in (root / "images").rglob("*") if not p.name.startswith("grid-")),
        3: root.glob("script-ep*.md"),
        4: (root / "layer2").glob("layer2-*.json"),
        5: root.glob("segments-ep*.json"),
        6: [root / "videos" / "qa-report.json"],
        7: list((root / "final").glob("delivery-*.json")) if (root / "final").exists() else [],
    }
    for p in patterns.get(stage, []):
        if p.is_file() and not (stage == 2 and p.name.startswith("grid-")):
            files.append(p)
    if stage == 5:
        # 失敗目錄的 ack 是「我接受這條警告」的憑證；納入快照，
        # 事後偷偷增減 ack 就會讓 stage-5 核准失效。
        acks = root / "review" / "catalog-acks.json"
        if acks.is_file():
            files.append(acks)
        # A multi-episode project needs one combined segments file so the stage-6
        # gate can confirm that every episode's clips exist, not just one episode.
        combined = root / "segments-all.json"
        if combined.is_file():
            files.append(combined)
    if stage == 1:
        if (root / "source").exists():
            files.extend(p for p in (root / "source").rglob("*") if p.is_file())
        for rel in ("adapt/series-outline.md", "adapt/episode-outline.md", "adapt/adaptation.md"):
            candidate = root / rel
            if candidate.is_file():
                files.append(candidate)
    if stage == 3:
        files.extend(p for p in root.glob("handoff-ep*.json") if p.is_file())
    if stage == 6 and (root / "videos").exists():
        files.extend(p for p in (root / "videos").glob("*.mp4") if p.name != "final_assembled.mp4")
    if stage == 6:
        # 逐段目視結論也是核准依據；核准後改結論就要重審。
        verdicts_file = root / "review" / "verdicts.json"
        if verdicts_file.is_file():
            files.append(verdicts_file)
    if stage == 7:
        files.extend(p for p in (root / "final").glob("*.mp4") if p.is_file())
    if stage in (4, 5):
        for p in list(files):
            try:
                data = json.loads(p.read_text(encoding="utf-8-sig"))
            except (OSError, json.JSONDecodeError):
                continue
            if stage == 4:
                for shot in data.get("shots", []):
                    sketch = shot.get("sketch_file")
                    if sketch:
                        candidate = _resolve(root, sketch)
                        if not candidate.is_file():
                            candidate = (p.parent / sketch).resolve()
                        if candidate.is_file():
                            files.append(candidate)
            else:
                segments = data if isinstance(data, list) else data.get("segments", [data])
                for seg in segments:
                    for ref in seg.get("reference_images", []) or []:
                        raw = ref.get("path") or ref.get("file") if isinstance(ref, dict) else str(ref)
                        if raw:
                            candidate = _resolve(root, raw)
                            if candidate.is_file():
                                files.append(candidate)
    # Stage 4 also binds exact grid files corresponding to current segment IDs.
    if stage == 4:
        for layer in list(files):
            if layer.parent.name != "layer2" or not layer.name.startswith("layer2-"):
                continue
            try:
                data = json.loads(layer.read_text(encoding="utf-8-sig"))
            except (OSError, json.JSONDecodeError):
                continue
            seg_id = data.get("segment_id") or layer.stem.removeprefix("layer2-")
            for shot in data.get("shots", []):
                generation = shot.get("sketch_generation")
                metadata = shot.get("metadata")
                raw_grid = (generation.get("grid_file") if isinstance(generation, dict) else None)
                raw_grid = raw_grid or (metadata.get("grid_file") if isinstance(metadata, dict) else None)
                raw_grid = raw_grid or shot.get("grid_file")
                if isinstance(raw_grid, str) and raw_grid.strip():
                    grid_path = Path(raw_grid.strip())
                    candidates = (
                        _resolve(root, grid_path),
                        grid_path.resolve() if grid_path.is_absolute() else (layer.parent / grid_path).resolve(),
                    )
                    files.extend(path for path in candidates if path.is_file())
            for grid in (root / "images" / f"grid-{seg_id}.png", root / "layer2" / f"grid-{seg_id}.png"):
                if grid.is_file():
                    files.append(grid)
        matched, _ = stage4_artifacts(root)
        files.extend(matched)
    return sorted({p.resolve() for p in files if p.is_file()}, key=lambda p: str(p).casefold())


def stage_snapshot(root: Path, stage: int) -> dict[str, Any]:
    artifacts = []
    for path in _files_for_stage(root, stage):
        try:
            rel = path.relative_to(root.resolve()).as_posix()
        except ValueError:
            rel = "external:" + str(path)
        if stage == 4 and path.parent.name == "layer2" and path.name.startswith("layer2-"):
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            for shot in data.get("shots", []):
                shot.pop("technical_review", None)
                shot.pop("video_file", None)
                if shot.get("status") == "video_done":
                    shot.pop("status", None)
            end_state = data.get("segment_end_state")
            if isinstance(end_state, dict):
                end_state.pop("observed_final_state", None)
            encoded = json.dumps(data, sort_keys=True, ensure_ascii=False).encode("utf-8")
            digest = hashlib.sha256(encoded).hexdigest()
            size = len(encoded)
        elif stage == 6 and path.name == "qa-report.json":
            # generated_at is informational; it must not churn an otherwise identical QA approval.
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            data.pop("generated_at", None)
            digest = hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
            size = path.stat().st_size
        else:
            digest = sha256_file(path)
            size = path.stat().st_size
        artifacts.append({"path": rel, "sha256": digest, "size": size})
    return {"stage": stage_key(stage), "artifacts": artifacts}


def snapshot_fingerprint(snapshot: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(snapshot, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def _entry_fingerprint(entry: dict[str, Any]) -> str:
    return snapshot_fingerprint(entry["approval_snapshot"])


def _untagged_decision_ids(root: Path, stage: int) -> set[str]:
    """decisions.json 中明確標了 stages、但不含此階段的定案 id。"""
    path = root / "decisions.json"
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return set()
    items = raw.get("decisions", raw) if isinstance(raw, dict) else raw
    out = set()
    for d in items if isinstance(items, list) else []:
        if isinstance(d, dict) and d.get("id") and isinstance(d.get("stages"), list) and stage not in d["stages"]:
            out.add(str(d["id"]))
    return out


def scoped_stage0_fingerprint(root: Path, stage: int) -> str:
    """stage-0 對 stage-N 的依賴指紋：遮掉 project.md 中「未標到 stage-N」的定案行。

    改畫幅這類只影響部分階段的定案，不應連帶要求重審無關階段。
    """
    ids = _untagged_decision_ids(root, stage)
    path = root / "project.md"
    lines = path.read_text(encoding="utf-8-sig").splitlines() if path.is_file() else []
    kept = []
    for line in lines:
        key = line.lstrip("-* ").split("：", 1)[0].split(":", 1)[0].strip().strip("`")
        if key in ids:
            continue
        kept.append(line)
    return hashlib.sha256("\n".join(kept).encode("utf-8")).hexdigest()


def _valid_png(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        from PIL import Image
        with Image.open(path) as image:
            if image.format != "PNG":
                return False
            image.verify()
        return True
    except Exception:
        return False


REJECTED_SKETCH_STATUSES = frozenset({"rejected", "retake", "redo", "needs_redo", "failed"})


def stage4_artifacts(root: Path) -> tuple[list[Path], list[str]]:
    layer_files = sorted((root / "layer2").glob("layer2-*.json")) if (root / "layer2").exists() else []
    if not layer_files:
        return [], ["找不到 layer2/layer2-*.json 分鏡檔案"]
    matched: list[Path] = []
    errors: list[str] = []
    for layer in layer_files:
        try:
            data = json.loads(layer.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{layer.name}: JSON 無法解析 ({exc})")
            continue
        seg_id = str(data.get("segment_id") or layer.stem.removeprefix("layer2-"))
        shots = data.get("shots", [])
        if not isinstance(shots, list) or not shots:
            errors.append(f"{layer.name}: 沒有 shots")
            continue
        # A segment may reference one or more outsourced overview grids. Keep
        # those images in the artifact set, but never let a grid stand in for
        # the required per-shot sketch below.
        legacy_grids = [root / "images" / f"grid-{seg_id}.png", layer.parent / f"grid-{seg_id}.png"]
        grid_candidates = list(legacy_grids)
        has_explicit_mapping = False
        for shot in shots:
            has_explicit_mapping = has_explicit_mapping or bool(shot.get("sketch_file"))
            generation = shot.get("sketch_generation")
            metadata = shot.get("metadata")
            raw_grid = generation.get("grid_file") if isinstance(generation, dict) else None
            raw_grid = raw_grid or (metadata.get("grid_file") if isinstance(metadata, dict) else None)
            raw_grid = raw_grid or shot.get("grid_file")
            if isinstance(raw_grid, str) and raw_grid.strip():
                has_explicit_mapping = True
                grid_path = Path(raw_grid.strip())
                grid_candidates.extend((
                    _resolve(root, grid_path),
                    grid_path.resolve() if grid_path.is_absolute() else (layer.parent / grid_path).resolve(),
                ))
        valid_legacy_grid = next((p for p in legacy_grids if _valid_png(p)), None)
        matched.extend(p for p in grid_candidates if _valid_png(p))
        if valid_legacy_grid and not has_explicit_mapping:
            continue
        for index, shot in enumerate(shots, start=1):
            shot_id = str(shot.get("shot_id") or f"SH{index:02d}")
            status = str(shot.get("sketch_status") or "").strip().lower()
            if status in REJECTED_SKETCH_STATUSES:
                # 自檢退回的構圖不認領，即使圖還留在 panels/（#45）
                errors.append(f"{seg_id}/{shot_id}: 構圖自檢退回（sketch_status={status}），要重畫")
                continue
            candidates = []
            if shot.get("sketch_file"):
                # 有顯式綁定就只認綁定的檔，不再退回 panels/ 的同名圖
                candidates.extend((_resolve(root, shot["sketch_file"]), (layer.parent / shot["sketch_file"]).resolve()))
            else:
                candidates.extend((
                    root / "panels" / f"panel-{index:02d}-{shot_id}.png",
                    layer.parent / "panels" / f"panel-{index:02d}-{shot_id}.png",
                    root / f"panel-{index:02d}-{shot_id}.png",
                ))
            valid = next((p for p in candidates if _valid_png(p)), None)
            if valid:
                matched.append(valid)
            elif shot.get("sketch_file"):
                errors.append(f"{seg_id}/{shot_id}: sketch_file 指向的構圖不存在或不是有效 PNG：{shot['sketch_file']}")
            else:
                errors.append(f"{seg_id}/{shot_id}: 缺少有效且對應的構圖 PNG")
    return sorted(set(matched)), errors


def _sha_value(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    return value.lower().removeprefix("sha256:")


# 技術 QA 上「可由使用者覆寫」的問題前綴以外的 issue 都視為硬錯誤。
_QA_HARD_PREFIXES = ("DURATION_MISMATCH", "ASPECT_RATIO_MISMATCH", "QA_ERROR")


def stage6_issues(root: Path) -> tuple[list[str], list[str]]:
    """階段 6 檢查，拆成 (硬錯誤, 技術 QA 問題)。

    硬錯誤：檔案缺失、hash 不符、未生成、無法解碼、時長漂移、來源不一致、
    verdicts 判定需重跑——這些不能人工覆寫。
    技術 QA 問題：只有彩度、分鏡總覽圖、音軌這類量化指標未過（例如教室低彩度誤判）
    導致的 PARTIAL——使用者可用 `--approve-stage 6 --override --reason` 帶理由放行。
    """
    report = root / "videos" / "qa-report.json"
    if not report.is_file():
        return ["缺少 videos/qa-report.json"], []
    try:
        data = json.loads(report.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"QA 報告無法解析: {exc}"], []
    hard: list[str] = []
    technical: list[str] = []
    evidence = data.get("evidence")
    if not isinstance(evidence, dict):
        hard.append("QA 報告缺少 evidence 區塊：請用新版 verify_video_shot.py 重跑，舊報告不得作為階段 6 依據")
    elif evidence.get("verdict") != "VERIFIED":
        message = (
            f"QA 證據等級為 {evidence.get('verdict')}"
            f"（已量測 {evidence.get('produced')}/{evidence.get('expected')}）：未達 VERIFIED 不得核准階段 6"
        )
        structural = [str(x) for x in evidence.get("structural_issues", []) or []]
        only_quality = (
            evidence.get("verdict") == "PARTIAL"
            and evidence.get("produced") == evidence.get("expected")
            and not evidence.get("unmeasured")
            and not evidence.get("unproduced")
            and all(item.startswith("continuity:") for item in structural)
        )
        (technical if only_quality else hard).append(message)
    expected = set(data.get("expected_segments", []))
    unproduced = set(data.get("unproduced_segments", []) or [])
    results = data.get("results", [])
    if not expected:
        hard.append("QA 報告缺少 expected_segments")
    current_expected, source_error = scoped_expected_segment_ids(root, data)
    if source_error:
        hard.append(source_error)
    elif expected != current_expected:
        hard.append("QA expected_segments 與其來源 segments 檔不一致（請用 `h3d qa --segments` 重跑 QA）")
    if unproduced:
        hard.append("仍有未生成分段: " + ", ".join(sorted(unproduced)))
    found: dict[str, dict[str, Any]] = {}
    for item in results:
        sid = item.get("segment_id")
        if sid:
            found[str(sid)] = item
    for sid in sorted(expected):
        item = found.get(str(sid))
        if not item:
            hard.append(f"{sid}: QA 結果缺失")
            continue
        raw_video = item.get("video_file")
        if not raw_video:
            hard.append(f"{sid}: QA 缺少 video_file")
            continue
        vp = _resolve(root, raw_video)
        if not vp.is_file():
            hard.append(f"{sid}: 影片不存在 {raw_video}")
            continue
        expected_hash = _sha_value(item.get("video_sha256") or item.get("file_hash_sha256"))
        actual_hash = sha256_file(vp)
        if not expected_hash or expected_hash != actual_hash:
            hard.append(f"{sid}: 影片 hash 缺失或不相符")
        if item.get("passed") is not True:
            issues = [str(i) for i in item.get("issues", []) or []]
            hard_issues = [i for i in issues if i.startswith(_QA_HARD_PREFIXES)]
            if hard_issues:
                hard.append(f"{sid}: 技術 QA 硬錯誤（不可覆寫）：{hard_issues[0][:120]}")
            else:
                brief = "、".join(i.split(":")[0].split(" ")[0] for i in issues) or "未列原因"
                technical.append(f"{sid}: 技術 QA 未通過（{brief}）")
        if _ffprobe(vp) is None:
            hard.append(f"{sid}: 影片無法完整解碼")
    extra = set(found) - expected
    if extra:
        hard.append(
            "QA 含非預期分段: " + ", ".join(sorted(extra))
            + "（多集專案請用 `h3d qa --segments segments-ep01.json segments-ep02.json ...` 一次產生全集報告）"
        )
    hard.extend(_verdict_errors(root, data))
    return hard, technical


def _verdict_errors(root: Path, qa_report: dict[str, Any]) -> list[str]:
    """有 review/verdicts.json 時，依驗收政策判為 fail 的段落擋核准（不可覆寫）。"""
    if not (root / "review" / "verdicts.json").is_file():
        return []
    try:
        import verdicts as verdicts_mod
        report = verdicts_mod.classify(root, qa_report=qa_report)
    except Exception as exc:  # 格式錯誤本身就是硬錯誤
        return [f"review/verdicts.json 無法使用：{exc}"]
    return [
        f"{sid}: 驗收結論需重跑（{row['reason']}）"
        for sid, row in report["segments"].items()
        if row["effective"] == "fail" and row.get("source") != "qa"
    ]


def stage6_errors(root: Path) -> list[str]:
    hard, technical = stage6_issues(root)
    return hard + technical


def _approved_stage5_hashes(root: Path) -> dict[str, Any]:
    stage5 = load_state(root)["stages"][stage_key(5)]
    return {
        item.get("path"): item.get("sha256")
        for item in (stage5.get("approval_snapshot") or {}).get("artifacts", [])
    }


def _segment_ids_from(source: Path) -> set[str]:
    raw = json.loads(source.read_text(encoding="utf-8-sig"))
    segments = raw if isinstance(raw, list) else raw.get("segments", [raw])
    return {str(item["segment_id"]) for item in segments if isinstance(item, dict) and item.get("segment_id")}


def _scoped_multi(root: Path, sources: Any) -> tuple[set[str], str | None]:
    """多集：source_segments_files = [{path, sha256}, ...]，預期分段取聯集，每個檔都要在 stage-5 快照內。"""
    if not isinstance(sources, list) or not sources:
        return set(), "source_segments_files 必須是非空陣列"
    approved = _approved_stage5_hashes(root)
    ids: set[str] = set()
    for entry in sources:
        if not isinstance(entry, dict) or not entry.get("path"):
            return set(), "source_segments_files 每一項都要有 path 與 sha256"
        source = _resolve(root, entry["path"])
        if not source.is_file():
            return set(), f"來源分段檔不存在: {entry['path']}"
        expected_hash = _sha_value(entry.get("sha256"))
        if not expected_hash or expected_hash != sha256_file(source):
            return set(), f"{source.name}: sha256 缺失或與目前分段檔不符"
        try:
            relative_source = source.relative_to(root.resolve()).as_posix()
        except ValueError:
            return set(), f"{source.name}: 位於專案外，無法確認其受 stage-5 核准"
        if approved.get(relative_source) != expected_hash:
            return set(), f"{source.name}: 不在 stage-5 核准快照中，或核准後內容已變更"
        try:
            ids |= _segment_ids_from(source)
        except (OSError, json.JSONDecodeError, TypeError, KeyError):
            return set(), f"來源分段檔無法解析: {source.name}"
    return ids, None


def scoped_expected_segment_ids(root: Path, payload: dict[str, Any]) -> tuple[set[str], str | None]:
    if payload.get("source_segments_files"):
        return _scoped_multi(root, payload["source_segments_files"])
    files = sorted(root.glob("segments-ep*.json"))
    raw_source = payload.get("source_segments_file")
    if raw_source:
        source = _resolve(root, raw_source)
    elif len(files) == 1:
        source = files[0]
    elif not files:
        return set(), "缺少 segments-ep*.json，無法確認預期分段完整性"
    else:
        return set(), ("多集專案的 QA/manifest 必須提供 source_segments_files（全集）或 source_segments_file（單集）"
                       "才能確認完整性；用 `h3d qa --segments segments-ep*.json` 重跑")
    if not source.is_file():
        return set(), f"來源分段檔不存在: {raw_source}"
    expected_hash = _sha_value(payload.get("source_segments_sha256"))
    if not expected_hash or expected_hash != sha256_file(source):
        return set(), "source_segments_sha256 缺失或與目前分段檔不符"
    try:
        relative_source = source.relative_to(root.resolve()).as_posix()
    except ValueError:
        return set(), "來源分段檔位於專案外，無法確認其受 stage-5 核准"
    state = load_state(root)
    stage5 = state["stages"][stage_key(5)]
    approved_items = {
        item.get("path"): item.get("sha256")
        for item in (stage5.get("approval_snapshot") or {}).get("artifacts", [])
    }
    if approved_items.get(relative_source) != expected_hash:
        return set(), "來源分段檔不在 stage-5 核准快照中，或核准後內容已變更"
    try:
        raw = json.loads(source.read_text(encoding="utf-8-sig"))
        segments = raw if isinstance(raw, list) else raw.get("segments", [raw])
        return {str(item["segment_id"]) for item in segments if isinstance(item, dict) and item.get("segment_id")}, None
    except (OSError, json.JSONDecodeError, TypeError):
        return set(), f"來源分段檔無法解析: {source.name}"


def _ffprobe(path: Path) -> dict[str, Any] | None:
    exe = shutil.which("ffmpeg")
    if not exe or not path.is_file() or path.stat().st_size <= 1024:
        return None
    try:
        result = subprocess.run([exe, "-v", "error", "-i", str(path), "-f", "null", "-"], capture_output=True, text=True, timeout=90)
        if result.returncode != 0:
            return None
        probe = shutil.which("ffprobe")
        if not probe:
            return {"duration": None}
        parsed = subprocess.run([probe, "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)], capture_output=True, text=True, timeout=30)
        if parsed.returncode != 0:
            return None
        duration = float(json.loads(parsed.stdout).get("format", {}).get("duration", 0))
        return {"duration": duration} if duration > 0 else None
    except (OSError, ValueError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return None


def stage7_errors(root: Path) -> list[str]:
    finals = sorted((root / "final").glob("*.mp4")) if (root / "final").exists() else []
    if not finals:
        return ["final/ 下缺少 MP4 成片"]
    errors: list[str] = []
    for final in finals:
        manifest = root / "final" / f"delivery-{final.stem}.json"
        if not manifest.is_file():
            errors.append(f"{final.name}: 缺少交付 manifest {manifest.name}")
            continue
        try:
            data = json.loads(manifest.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{final.name}: manifest 無法解析 ({exc})")
            continue
        expected = set(data.get("expected_segments", []))
        current_expected, source_error = scoped_expected_segment_ids(root, data)
        assembled = {str(item.get("segment_id")) for item in data.get("assembled_segments", []) if item.get("segment_id")}
        if source_error or not expected or expected != assembled or expected != current_expected or data.get("expected_segment_count") != len(expected) or data.get("assembled_segment_count") != len(expected):
            errors.append(f"{final.name}: 交付分段清單不完整或數量不符")
            if source_error:
                errors.append(f"{final.name}: {source_error}")
        if data.get("delivery_status") != "complete":
            errors.append(f"{final.name}: delivery manifest 尚未標記 complete")
        if data.get("final_video") and Path(str(data["final_video"])).name != final.name:
            errors.append(f"{final.name}: manifest final_video 不指向此成片")
        if _sha_value(data.get("final_sha256")) != sha256_file(final):
            errors.append(f"{final.name}: final SHA256 缺失或不符")
        decoded = _ffprobe(final)
        if data.get("final_decode_ok") is not True or not decoded or not decoded.get("duration"):
            errors.append(f"{final.name}: 成片無法完整解碼或 duration 無效")
        for item in data.get("assembled_segments", []):
            for field, hash_field in (("source_video_file", "source_video_sha256"), ("processed_video_file", "processed_video_sha256")):
                raw_video = item.get(field)
                if not raw_video:
                    if field == "processed_video_file":
                        errors.append(f"{final.name}: {item.get('segment_id')} 缺少 processed_video_file")
                    continue
                video = _resolve(root, raw_video)
                if not video.is_file() or _sha_value(item.get(hash_field)) != sha256_file(video):
                    errors.append(f"{final.name}: {item.get('segment_id')} {field} 缺失或 hash 不符")
    return errors


def stage_validation_errors(root: Path, stage: int, allow_technical: bool = False,
                            strict: bool = False) -> list[str]:
    """allow_technical=True 時，階段 6 只回硬錯誤（供已記錄 override 的核准使用）。

    strict=True（h3d next、新核准、自動核准）時，階段 0–3 另外檢查產物內容：
    模板佔位符、角色設定驗證、設定圖存在、劇本四支驗證（stage_content_checks.py）。
    已核准階段的重新驗證不走 strict：核准快照已綁定內容 hash，改了就失效。
    """
    if strict and stage in (0, 1, 2, 3):
        import stage_content_checks
        return stage_content_checks.content_errors(root, stage)
    if stage == 6 and allow_technical:
        return stage6_issues(root)[0]
    if stage == 4:
        return stage4_artifacts(root)[1]
    if stage == 5:
        segments = sorted(root.glob("segments-ep*.json"))
        if not segments:
            return ["缺少 segments-ep*.json 提示詞包"]
        errors = []
        for path in segments:
            try:
                raw = json.loads(path.read_text(encoding="utf-8-sig"))
                items = raw if isinstance(raw, list) else raw.get("segments", [raw])
                for seg in items:
                    sid = seg.get("segment_id", path.name)
                    refs = seg.get("reference_images", []) or []
                    if not refs:
                        errors.append(f"{sid}: 缺少 reference_images")
                    for ref in refs:
                        raw_path = ref.get("path") or ref.get("file") if isinstance(ref, dict) else str(ref)
                        if not raw_path or not _resolve(root, raw_path).is_file():
                            errors.append(f"{sid}: 參考圖不存在 {raw_path}")
            except (OSError, json.JSONDecodeError, TypeError) as exc:
                errors.append(f"{path.name}: 無法讀取 ({exc})")
        return errors
    if stage == 6:
        return stage6_errors(root)
    if stage == 7:
        return stage7_errors(root)
    return []


def _stage_matches(root: Path, state: dict[str, Any], stage: int) -> bool:
    entry = state["stages"][stage_key(stage)]
    if entry.get("status") != "approved" or not entry.get("approval_snapshot"):
        return False
    if stage_validation_errors(root, stage, allow_technical=_has_override(entry)):
        return False
    if entry["approval_snapshot"] != stage_snapshot(root, stage):
        return False
    dependencies = entry.get("approval_dependencies", {})
    return all(
        dependencies.get(stage_key(i)) == _entry_fingerprint(state["stages"][stage_key(i)])
        or (i == 0 and _stage0_scoped_ok(root, entry, stage))
        for i in range(stage)
        if state["stages"][stage_key(i)].get("approval_snapshot")
    )


def _stage0_scoped_ok(root: Path, entry: dict[str, Any], stage: int) -> bool:
    """stage-0 雖重新核准，但差異只在未標到此階段的定案行時，視為依賴仍有效。"""
    stored = entry.get("approval_stage0_scoped")
    return bool(stored) and stored == scoped_stage0_fingerprint(root, stage)


def is_approved(root: Path, stage: int) -> bool:
    return require_approved(root, stage)[0]


def require_approved(root: Path, stage: int) -> tuple[bool, str]:
    failed, detail = first_unapproved(root, stage)
    return (failed is None), detail


def first_unapproved(root: Path, upto: int = 7) -> tuple[int | None, str]:
    """由 stage-0 往上找第一個沒有有效核准的階段；全部有效回傳 (None, "OK")。

    與 require_approved 同一套規則，只掃一遍（h3d next 用它避免重複解碼影片）。
    """
    state = load_state(root)
    for i in range(upto + 1):
        failed = _stage_failure(root, state, i)
        if failed:
            return i, failed
    return None, "OK"


def _stage_failure(root: Path, state: dict[str, Any], i: int) -> str | None:
    """回傳 stage-i 不算有效核准的原因；有效則回傳 None。"""
    entry = state["stages"][stage_key(i)]
    if entry.get("status") != "approved":
        return f"stage-{i} 尚未人工核准（目前狀態: {entry.get('status', 'draft')}）"
    if not entry.get("approval_snapshot"):
        return f"stage-{i} 是舊狀態或缺少核准快照，必須重新審核"
    errors = stage_validation_errors(root, i, allow_technical=_has_override(entry))
    if errors:
        return f"stage-{i} 產物檢查失敗: {errors[0]}"
    if entry["approval_snapshot"] != stage_snapshot(root, i):
        return f"stage-{i} 核准後輸入或產物已變更，請重新審核"
    if i > 0:
        dependencies = entry.get("approval_dependencies", {})
        for prev in range(i):
            prior = state["stages"][stage_key(prev)]
            if dependencies.get(stage_key(prev)) != _entry_fingerprint(prior):
                if prev == 0 and _stage0_scoped_ok(root, entry, i):
                    continue
                return f"stage-{i} 依賴的 stage-{prev} 核准版本已更新，請重新審核"
    return None


def mark_awaiting_review(root: Path, state: dict[str, Any], stage: int) -> None:
    key = stage_key(stage)
    state["current_stage"] = stage
    state["stages"][key]["status"] = "awaiting_user_approval"
    state["stages"][key]["updated_at"] = __import__("datetime").datetime.now().astimezone().isoformat()
    state["stages"][key]["review_snapshot"] = stage_snapshot(root, stage)
    save_state(root, state)


def _has_override(entry: dict[str, Any]) -> bool:
    override = entry.get("override")
    return isinstance(override, dict) and bool(str(override.get("reason") or "").strip())


def approve_stage_detailed(root: Path, stage: int, note: str = "使用者確認通過",
                           override_reason: str | None = None,
                           auto_approval: dict[str, Any] | None = None) -> tuple[bool, str]:
    """核准一個階段；回傳 (成功與否, 原因)。

    override_reason 只用於階段 6：技術 QA 為 PARTIAL（低彩度等量化指標誤判）時，
    使用者看過影片仍要核准，就必須寫理由。理由、時間與被覆寫的問題清單
    會寫進 project-state，require_approved 視為通過但永遠留著這筆紀錄。
    硬錯誤（缺片、hash 不符、時長漂移、verdicts 判重跑）不能覆寫。
    """
    override_reason = (override_reason or "").strip() or None
    if override_reason is not None and stage != 6:
        return False, "--override 只適用於階段 6 的技術 QA；其他階段請修正產物後重審"
    state = load_state(root)
    entry = state["stages"][stage_key(stage)]
    if entry.get("status") != "awaiting_user_approval" or not entry.get("review_snapshot"):
        return False, "該階段尚未產生審核頁（狀態不是 awaiting_user_approval）；請先跑 --stage 產出審核頁"
    if entry["review_snapshot"] != stage_snapshot(root, stage):
        return False, "審核頁產出後輸入或產物已變更；請重建審核頁再請使用者確認"
    technical: list[str] = []
    if stage == 6:
        hard, technical = stage6_issues(root)
        if hard:
            return False, f"階段 6 有不可覆寫的錯誤：{hard[0]}"
        if technical and override_reason is None:
            return False, (f"技術 QA 未過（{len(technical)} 項，例如 {technical[0]}）。"
                           "若使用者已看過影片仍核准，請加 --override --reason \"使用者的理由\"")
    else:
        errors = stage_validation_errors(root, stage, strict=True)
        if errors:
            return False, f"產物檢查失敗：{errors[0]}"
    if stage > 0:
        ok, detail = require_approved(root, stage - 1)
        if not ok:
            return False, f"前置階段已失效或未核准：{detail}"
    now = __import__("datetime").datetime.now().astimezone().isoformat()
    entry["status"] = "approved"
    entry["approved_at"] = now
    entry["user_note"] = note
    entry["approval_snapshot"] = stage_snapshot(root, stage)
    entry["approval_dependencies"] = {
        stage_key(i): _entry_fingerprint(state["stages"][stage_key(i)]) for i in range(stage)
    }
    if stage > 0:
        entry["approval_stage0_scoped"] = scoped_stage0_fingerprint(root, stage)
    if override_reason is not None and technical:
        entry["override"] = {
            "reason": override_reason,
            "at": now,
            "overridden_issue_count": len(technical),
            "overridden_issues": technical[:50],
        }
        history = list(entry.get("override_history") or [])
        history.append(dict(entry["override"]))
        entry["override_history"] = history
    else:
        entry.pop("override", None)
    if auto_approval is not None:
        # 自動核准（h3d approve --auto）：依據哪條政策、哪些 verdicts，永久留紀錄。
        record = {**auto_approval, "at": now}
        entry["auto_approval"] = record
        history = list(entry.get("auto_approval_history") or [])
        history.append(record)
        entry["auto_approval_history"] = history
    else:
        entry.pop("auto_approval", None)
    # 解鎖下一階段放在正門裡：手動 --approve-stage 與 h3d approve --auto 狀態一致。
    next_key = stage_key(stage + 1)
    if next_key in state["stages"]:
        state["current_stage"] = stage + 1
        if state["stages"][next_key].get("status") == "locked":
            state["stages"][next_key]["status"] = "in_progress"
    save_state(root, state)
    return True, "OK"


def approve_stage(root: Path, stage: int, note: str = "使用者確認通過",
                  override_reason: str | None = None) -> bool:
    return approve_stage_detailed(root, stage, note, override_reason)[0]
