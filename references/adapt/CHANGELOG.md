# Changelog

All notable changes to the `novel-to-manju` skill will be documented in this file.

## [1.1.0] - 2026-10-25

### Changed
- **成片形式預設改為長篇漫劇（`series_format=longform`）**：整部一支連續長片，以「把故事講清楚」為第一優先；不再預設每集 80–120 秒的短集。短劇／竪屏爆款短集改為使用者明確選擇才啟用（`--format short`、`h3d decide series_format short`）。
- `estimate_duration.py`：新增 `--events`（依事件數與交代需求估總片長）；長篇模式不再有單集 90 秒預設與「> 單集目標 × 2」門禁；`--target-seconds` 預設改為不設定。
- `handoff.schema.json`：`target_duration_seconds` 改為選填（短劇模式才需要）；新增場景欄位 `event_exposition`。

### Added
- `scripts/adapt/event_coverage.py`：事件交代完整性檢查（完整／交代不全／未標註／被壓縮／被跳過／未交代），階段 1 審核頁呈現待使用者決定的事件。
- `scripts/adapt/series_format.py`：成片形式唯一判定來源。
- 劇本註解 `<!-- exposition: U01 起因 經過 結果 -->`，由 `sync_script.py` 寫入 handoff。

## [1.0.0] - 2026-10-17

### Added
- **Core Skill Specification (`SKILL.md`)**: Established 10-phase production pipeline, 8 modular execution modes (`research`, `diagnose`, `bible`, `outline`, `episode`, `handoff`, `review`, `full-series`), dual-axis genre/medium routing, 100-point rubric, and 4 hard gatekeepers (`FATAL_CAUSAL_BREAK`, `CANON_CONTRADICTION`, `CRITICAL_SCENE_UNFILMABLE`, `UNTRACKED_MAJOR_CHANGE`).
- **10 Domain References (`references/`)**:
  - `adaptation-principles.md`: Transcoding theory, must-keep core, pruning rules, and debt ledger causality.
  - `genre-modes.md`: Routing matrix for 6 genres, aspect ratios (`9:16` / `16:9`), and target mediums (`motion_comic` / `ai_animation` / `live_action_short_drama`).
  - `screenplay-format.md`: Chinese scene-number format (`△` action lines, `角色名：` dialogue, flashback tags) decoupled from camera jargon.
  - `structure-and-pacing.md`: Episode breaking, micro-5-beat container, Pamela Douglas 8 act-out types, and reordering rules.
  - `character-and-world-bible.md`: Character ID/alias resolution, visual invariant anchors, Want vs. Misbelief, and world rules.
  - `visual-writing.md`: Externalizing internal monologues via active verbs, working props, and dramatic irony.
  - `dialogue-and-audio.md`: Subtext, character voice differentiation, V.O./O.S. discipline (≤15%), and TTS breath pacing (≤28 chars warning, ≤35 chars hard limit).
  - `filmability-and-cost.md`: AI video generation constraints (T2V/I2V/FL2V/Ref2V), bottle scenes, low-collision combat rewrites, and dual-version (Original vs. Simplified) risk mitigation.
  - `evidence-and-licenses.md`: Open-source attribution, SPDX license obligations, and adaptation copyright tracking.
  - `storyboarding-handoff.md`: Handoff protocol for downstream AI storyboard/video skills (`ai-director`, `h3-film-studio`, `seedance-20`).
- **7 Standardized Templates & Schemas (`templates/`)**:
  - `source-analysis.md`, `story-bible.md`, `series-outline.md`, `episode-outline.md`, `scene-script.md`, `adaptation-diff.md`, and `handoff.schema.json`.
- **4 Deterministic Verification Scripts (`scripts/`)**:
  - `validate_structure.py`, `estimate_duration.py`, `check_continuity.py`, and `compare_adaptation.py`.
- **10 Boundary Test Cases & A/B Evaluation Suite (`tests/`)**:
  - Complete fixtures, expected outputs, and automated runner covering all 10 required adaptation edge cases and A/B comparison against the legacy prompt.
