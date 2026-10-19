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


def save_state(root: Path, state: dict[str, Any]) -> None:
    path = state_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = _normalize_state(state, root)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(normalized, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


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
            candidates = []
            if shot.get("sketch_file"):
                candidates.extend((_resolve(root, shot["sketch_file"]), (layer.parent / shot["sketch_file"]).resolve()))
            candidates.extend((
                root / "panels" / f"panel-{index:02d}-{shot_id}.png",
                layer.parent / "panels" / f"panel-{index:02d}-{shot_id}.png",
                root / f"panel-{index:02d}-{shot_id}.png",
            ))
            valid = next((p for p in candidates if _valid_png(p)), None)
            if valid:
                matched.append(valid)
            else:
                errors.append(f"{seg_id}/{shot_id}: 缺少有效且對應的九宮格或單格 PNG")
    return sorted(set(matched)), errors


def _sha_value(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    return value.lower().removeprefix("sha256:")


def stage6_errors(root: Path) -> list[str]:
    report = root / "videos" / "qa-report.json"
    if not report.is_file():
        return ["缺少 videos/qa-report.json"]
    try:
        data = json.loads(report.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"QA 報告無法解析: {exc}"]
    errors: list[str] = []
    expected = set(data.get("expected_segments", []))
    unproduced = set(data.get("unproduced_segments", []))
    results = data.get("results", [])
    if not expected:
        errors.append("QA 報告缺少 expected_segments")
    current_expected, source_error = scoped_expected_segment_ids(root, data)
    if source_error:
        errors.append(source_error)
    elif expected != current_expected:
        errors.append("QA expected_segments 與其來源 segments 檔不一致")
    if unproduced:
        errors.append("仍有未生成分段: " + ", ".join(sorted(unproduced)))
    found: dict[str, dict[str, Any]] = {}
    for item in results:
        sid = item.get("segment_id")
        if sid:
            found[str(sid)] = item
    for sid in sorted(expected):
        item = found.get(str(sid))
        if not item:
            errors.append(f"{sid}: QA 結果缺失")
            continue
        raw_video = item.get("video_file")
        if not raw_video:
            errors.append(f"{sid}: QA 缺少 video_file")
            continue
        vp = _resolve(root, raw_video)
        if not vp.is_file():
            errors.append(f"{sid}: 影片不存在 {raw_video}")
            continue
        expected_hash = _sha_value(item.get("video_sha256") or item.get("file_hash_sha256"))
        actual_hash = sha256_file(vp)
        if not expected_hash or expected_hash != actual_hash:
            errors.append(f"{sid}: 影片 hash 缺失或不相符")
        if item.get("passed") is not True:
            errors.append(f"{sid}: 技術 QA 未通過")
        if _ffprobe(vp) is None:
            errors.append(f"{sid}: 影片無法完整解碼")
    extra = set(found) - expected
    if extra:
        errors.append("QA 含非預期分段: " + ", ".join(sorted(extra)))
    return errors


def scoped_expected_segment_ids(root: Path, payload: dict[str, Any]) -> tuple[set[str], str | None]:
    files = sorted(root.glob("segments-ep*.json"))
    raw_source = payload.get("source_segments_file")
    if raw_source:
        source = _resolve(root, raw_source)
    elif len(files) == 1:
        source = files[0]
    elif not files:
        return set(), "缺少 segments-ep*.json，無法確認預期分段完整性"
    else:
        return set(), "多集專案的 QA/manifest 必須提供 source_segments_file 才能確認當集完整性"
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


def stage_validation_errors(root: Path, stage: int) -> list[str]:
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
    if stage_validation_errors(root, stage):
        return False
    if entry["approval_snapshot"] != stage_snapshot(root, stage):
        return False
    dependencies = entry.get("approval_dependencies", {})
    return all(
        dependencies.get(stage_key(i)) == _entry_fingerprint(state["stages"][stage_key(i)])
        for i in range(stage)
        if state["stages"][stage_key(i)].get("approval_snapshot")
    )


def is_approved(root: Path, stage: int) -> bool:
    return require_approved(root, stage)[0]


def require_approved(root: Path, stage: int) -> tuple[bool, str]:
    state = load_state(root)
    for i in range(stage + 1):
        entry = state["stages"][stage_key(i)]
        if entry.get("status") != "approved":
            return False, f"stage-{i} 尚未人工核准（目前狀態: {entry.get('status', 'draft')}）"
        if not entry.get("approval_snapshot"):
            return False, f"stage-{i} 是舊狀態或缺少核准快照，必須重新審核"
        errors = stage_validation_errors(root, i)
        if errors:
            return False, f"stage-{i} 產物檢查失敗: {errors[0]}"
        if entry["approval_snapshot"] != stage_snapshot(root, i):
            return False, f"stage-{i} 核准後輸入或產物已變更，請重新審核"
        if i > 0:
            dependencies = entry.get("approval_dependencies", {})
            for prev in range(i):
                prior = state["stages"][stage_key(prev)]
                if dependencies.get(stage_key(prev)) != _entry_fingerprint(prior):
                    return False, f"stage-{i} 依賴的 stage-{prev} 核准版本已更新，請重新審核"
    return True, "OK"


def mark_awaiting_review(root: Path, state: dict[str, Any], stage: int) -> None:
    key = stage_key(stage)
    state["current_stage"] = stage
    state["stages"][key]["status"] = "awaiting_user_approval"
    state["stages"][key]["updated_at"] = __import__("datetime").datetime.now().astimezone().isoformat()
    state["stages"][key]["review_snapshot"] = stage_snapshot(root, stage)
    save_state(root, state)


def approve_stage(root: Path, stage: int, note: str = "使用者確認通過") -> bool:
    state = load_state(root)
    entry = state["stages"][stage_key(stage)]
    if entry.get("status") != "awaiting_user_approval" or not entry.get("review_snapshot"):
        return False
    if stage_validation_errors(root, stage) or entry["review_snapshot"] != stage_snapshot(root, stage):
        return False
    if stage > 0:
        ok, _ = require_approved(root, stage - 1)
        if not ok:
            return False
    entry["status"] = "approved"
    entry["approved_at"] = __import__("datetime").datetime.now().astimezone().isoformat()
    entry["user_note"] = note
    entry["approval_snapshot"] = stage_snapshot(root, stage)
    entry["approval_dependencies"] = {
        stage_key(i): _entry_fingerprint(state["stages"][stage_key(i)]) for i in range(stage)
    }
    save_state(root, state)
    return True
