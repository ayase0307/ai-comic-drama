# AI Comic Drama Skill Reliability Implementation Plan

> **For agentic workers:** Execute the approved rounds in order and stop for the main agent's review between rounds. Track work with the checkboxes below. Keep implementation minimal, use the existing standard-library/self-test patterns, and do not add a test framework or run generation jobs.

**Goal:** Make stage approvals and QA trustworthy, keep compiled H3 prompts faithful to the storyboard, and make the CLI workflow and local runners safe to operate.

**Architecture:** Keep review/project-state.json as the sole stage-state file, with shared load/save/hash logic in scripts/project_state.py. Keep Layer 2 as the canonical timeline and compile prompt sections from its authored visual, performance, and sound fields. Harden the existing CLI and runners in place, using root/tests standard-library unittest cases and offline preflight checks.

**Tech Stack:** Python standard library, JSON Schema draft-07, existing script --self-test commands, FFmpeg only for the existing assembly self-test.

**Spec:** Three approved repair rounds in the current task, plus repo conventions in agent.md and the current-state record in memory.md.

## Global Constraints

- Do not add a new dependency or test framework.
- All deterministic checks must run offline; do not submit jobs, call generation models, or generate production media during implementation.
- Keep one canonical state implementation in scripts/project_state.py and one state file at review/project-state.json.
- Keep the Layer 2 shot timing as the single timeline source of truth.
- Never cancel a job unless its ownership can be tied to the current local run.
- Main agent reviews and summarizes; Luna implements the small scoped changes.
- Stop after each round and present the concrete diff and verification results for review.

---

## File map

- scripts/project_state.py: shared state schema, normalization, hash, and invalidation helpers.
- scripts/build_stage_review.py: approval/prerequisite gates and stage 6 QA review rendering using the shared helper.
- scripts/storyboard/verify_video_shot.py: deterministic video QA and Layer 2 review updates.
- scripts/storyboard/assemble_episode.py: stage 7 input resolution, segment completeness, TTS error handling, and final assembly.
- scripts/storyboard/compile_layer2_to_h3.py: translate Layer 2 fields into H3 prompt sections and preserve one canonical timeline.
- scripts/init_project.py: project creation hint and CLI examples.
- scripts/storyboard/run_codex_asset_gen.py: generic asset execution and dependency preflight (asset-runner lane).
- scripts/storyboard/submit_h3_segments.py: remote job ownership and cancellation (submission lane).
- tests/: standard-library unittest coverage for state, QA, compiler, CLI, and runner behavior.
- memory.md: local-only maintenance handoff; must remain uncommitted.

## Round 1 — State gates, truthful QA, and assembly completeness

**Goal:** Prevent stale approvals from unlocking changed content, represent QA accurately, and fail clearly when required clips or TTS tracks are missing.

**Files:**
- Modify: scripts/build_stage_review.py
- Modify: scripts/storyboard/verify_video_shot.py
- Modify: scripts/storyboard/assemble_episode.py
- Create: scripts/project_state.py
- Create/update: tests/test_project_state.py, tests/test_stage_review.py, tests/test_video_qa.py, tests/test_assembly.py
- Use Python standard-library unittest; do not add a test framework.

- [x] **Task 1: Define and use one canonical project-state schema.**
  - Keep stage IDs, status values, timestamps, approval notes, and reviewed-input digest in generated project review/project-state.json.
  - Add shared schema/normalization/hash helpers in scripts/project_state.py; make build_stage_review.py and downstream gates consume them.
  - Hash the inputs used to build each review page. On approval, store the reviewed digest. Before a downstream gate accepts approval, recompute it and invalidate approval if the source changed; report which stage must be reviewed again.
  - Verify with: python -m unittest discover -s tests -p test_project_state.py -v
  - Tests must cover fresh state, malformed state, successful approval, and changed-input invalidation.

- [x] **Task 2: Make stage 6 QA status fail closed and match the QA report.**
  - In build_stage_6, treat a missing report entry or missing passed field as unknown/pending, never as PASS.
  - Count approved, failed, and unreviewed clips separately; the stage must fail its gate if any clip lacks a passing QA result.
  - Keep verify_video_shot.py report keys and the review renderer's lookup keys aligned; reject stale QA records when the video file hash no longer matches.
  - Verify with: python -m unittest discover -s tests -p test_stage_review.py -v
  - Fixtures must cover missing report, missing video entry, failed QA, and a matching passing report.

- [x] **Task 3: Make stage 7 require complete inputs and report TTS failures.**
  - Resolve --segments, --layer2-dir, and --timeline paths relative to the project root or the caller's explicit paths consistently.
  - Fail before concat if any declared segment is missing; do not silently create a partial episode. Include missing IDs in the error and delivery report.
  - When tts_replace is selected, collect per-line synthesis failures and return a failed segment result if required speech was not generated. Do not mark a silent replacement track as successful.
  - Verify with: python -m unittest discover -s tests -p test_assembly.py -v
  - Add offline cases for relative paths, one missing segment among present clips, and one failed TTS line; retain the existing temporary FFmpeg smoke test.

- [x] **Round 1 review checkpoint**
  - Main-agent review recorded: 26 regressions and 3 offline self-tests passed before R2 handoff.
  - Run:
    - python -m unittest discover -s tests -v
    - python scripts/storyboard/verify_video_shot.py --self-test
    - python scripts/storyboard/assemble_episode.py --self-test
  - Expected: all commands exit 0; targeted negative cases are rejected with nonzero status and clear diagnostics.
  - Stop and give the main agent the diff, changed files, and command results before Round 2.

## Round 2 — Faithful compiler output and one timeline

**Goal:** Preserve authored visual style, performance, dialogue, ambience, and music through compilation, with timing derived from Layer 2 exactly once.

**Files:**
- Modify: scripts/storyboard/compile_layer2_to_h3.py
- Modify: references/storyboard/templates/layer2-storyboard.schema.json only if the compiler needs new authored sound/performance fields.
- Modify: scripts/storyboard/layer2_to_table.py to export actual timelines from compiled segments collections; keep direct Layer 2 export as nominal planning time.
- Create/update: tests/test_h3_compiler.py and tests/test_layer2_to_table.py using standard-library unittest.

- [x] **Task 1: Map authored visual and acting fields into H3 output.**
  - Read style lock, lighting, color/palette, camera, blocking, action stages, and observable expression from Layer 2.
  - Preserve concrete performance beats and their ordering; do not replace them with generic style prose.
  - Preserve dialogue and diegetic sound separately from the authored overall soundscape and non-diegetic music.
  - Verify distinctive mapped values, metadata passed through to QA, and a compliant three-shot CLI check via: python -m unittest discover -s tests -p test_h3_compiler.py -v
  - Expected: both outputs contain authored values, no omitted music/performance field, and --check reports PASS.

- [x] **Task 2: Use one canonical shot timeline for the segment.**
  - Compute segment-relative shot start/end values once from Layer 2 start_time, end_time, and duration; use the same values in prompt timing, compiled JSON, Markdown, and layer2_to_table.py CSV.
  - Validate monotonic, non-overlapping ordered cuts and ensure the last cut fits the effective segment duration. Reject invalid timelines rather than independently rounding each output.
  - Verify a valid quantized timeline, overlap, gap, target mismatch, and short-cut case via: python -m unittest discover -s tests -p test_h3_compiler.py -v
  - Verify the exported compiled timeline keeps the quantized final shot end via: python -m unittest discover -s tests -p test_layer2_to_table.py -v
  - Expected: all exports agree on shot boundaries; invalid fixtures are rejected by the compiler check.

- [x] **Round 2 review checkpoint**
  - Main-agent review accepted 20 compiler tests, 10 stage-review tests, 4 audit self-tests, and the compiled-timeline export; follow-up QA metadata preservation is covered by the compiler-to-QA test.
  - Run:
    - python -m unittest discover -s tests -p test_h3_compiler.py -v
    - python -m unittest discover -s tests -p test_layer2_to_table.py -v
    - python scripts/storyboard/audit_refs_and_segments.py --self-test
  - Expected: all commands exit 0 on valid fixtures; deliberately malformed timelines exit nonzero.
  - Stop and give the main agent the diff, changed files, and command results before Round 3.

## Round 3 — CLI guidance, capability tiers, safe runner lanes, and integration

**Goal:** Make the generated project instructions executable from the project directory, preflight assets and dependencies before side effects, and cancel only jobs created by this run.

**Files:**
- Modify: scripts/init_project.py
- Modify: SKILL.md, references/pipeline.md, and references/freevideo.md for capability tiers and stage-targeted delivery.
- Add/update: tests/test_cli_docs.py using standard-library unittest.
- Separate implementation lane: scripts/storyboard/run_codex_asset_gen.py owns generic asset execution/preflight; scripts/storyboard/submit_h3_segments.py owns ownership-aware cancellation.

- [x] **Task 1: Correct generated CLI instructions and flow_hint.**
  - Ensure the generated hint uses the actual project directory and exact supported flags for every command; include a complete stage 5 compile command with output paths and a stage 6 --dry-run command.
  - Ensure stage 7 passes the actual segment/timeline/video paths and output location; do not advertise a --episode flag unless the parser implements it.
  - Document capability tiers: text planning is available in the agent; image/video generation is available only when the active client exposes a compatible tool or the selected local/provider backend is reachable. Do not assume Claude has built-in video generation. If FreeVideo is unavailable, continue only to the user's requested deliverable with supported inputs; do not ask about or generate out-of-scope video.
  - Verify with: python -m unittest discover -s tests -p test_cli_docs.py -v (2 passed; each generated command's flags checked against the actual script --help output).
  - Expected: generated flow_hint/project instructions name existing script paths and supported arguments.

- [x] **Task 2: Validate asset runner inputs and preflight local dependencies.**
  - Run the offline dependency inventory with `python scripts/check_environment.py`; it reports capability tiers and does not inspect services, accounts, tokens, or generation capability.
  - The asset CLI validates manifest inputs and CLI version/help before execution. Generation was not exercised in this repair round.
  - Verify offline with: python -m unittest discover -s tests -p test_local_runners.py -v
  - Expected: malformed manifests or unavailable local requirements fail before generation is attempted.

- [x] **Task 3: Make job cancellation ownership-aware.**
  - Use the project/API task ledger to identify jobs created by this client; cancel only jobs whose ownership is recorded, and leave unknown/unowned jobs untouched.
  - Keep credentials out of task records and diagnostics. Do not require a separate user-facing run ID when the existing ledger identifies the submitted job.
  - Verify offline with the submission lane's standard-library tests: python -m unittest discover -s tests -p test_submit_jobs.py -v
  - Expected: owned jobs are selected, unrelated jobs are preserved, and no credentials are read or printed.

- [x] **Task 4: Run the integration regression set.**
  - Run the isolated offline runner, which covers the unit suite, audit checks, and temporary-directory FFmpeg assembly without touching golden fixtures:
    - python scripts/run_offline_checks.py
  - Result: `python scripts/run_offline_checks.py` exited 0; 89 unittest tests passed and 6/6 checks passed (unittest, stage-review self-test, audit self-test, video-QA self-test, assembly self-test, and adaptation goldens in an isolated copy). `git diff --check` and `compileall` passed; `git diff --name-only -- scripts/adapt/tests` was empty. Final FLOW_HINT follow-up includes stage 0–3 review/approval commands, verified by `test_cli_docs.py`.
  - Limits: no image/video generation, TTS provider, or cloud CI was exercised. No commit or push was made.

- [x] **Round 3 review checkpoint**
  - Show the main agent the final diff, git status --short, and captured verification results. Keep local maintenance files out of commits; do not commit or push.
  - Main agent performs final review and reports the three-round result to the user.

## Final scope record

- Round 1 covers stage-state consistency and hash invalidation, QA truthfulness, assembly path resolution, missing segments, and TTS failure handling.
- Round 2 covers faithful prompt compilation for style/performance/music and a single canonical timeline.
- Round 3 covers generated CLI instructions, capability-tier documentation and flow_hint. The separate asset-runner/submission lane covers generic asset execution, dependency preflight, ownership-aware task cancellation, and its offline regression cases.
- Main-agent final verification: `python scripts/run_offline_checks.py` passed with 89 unittest tests and 6/6 checks; `git diff --check` and `compileall` passed; adaptation goldens remained unchanged. The final FLOW_HINT stage 0–3 prerequisite/approval commands were included and verified.
- Unverified: image/video generation, TTS-provider behavior, and cloud CI. No commit or push was made.
- Work stops for review after each round; this plan itself does not authorize publishing, committing, pushing, or running generation jobs.

