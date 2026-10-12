# OpenJutsu continuation checkpoint

Updated 2026-10-12 (Australia/Sydney).

- Main: `01e03bc39de32fc0f57bbbadd2a77052cf7cb71c` (fetched/confirmed).
- Active branch: `codex/step-5-artifact-integrity`, local head `08b511c`.
- Active PR: [#3](https://github.com/MudabbirulSaad/openjutsu/pull/3), draft,
  exact remote code head `8516b4d`; passing remote Checks runs
  `38177000931` / `38176997004`. Independent artifact review in progress.
- Completed goals: none yet. G0 baseline acceptance and G1 observability active.
- Next: finish independent PR #3 review, validate frozen Windows environment,
  publish retained investigation/roadmap and exact-head CI before integrity merge.
  Immediately implement G1/G2 independently testable observability slices.
- Plan: `openjutsu-engineering-plan.md`; full goal criteria in `goals.md`.
- Preserve original Steps 1–4 and `8516b4d`/`08b511c`; clean initial tree.
  Linux `.venv`, pilot fixtures/outputs and diagnostic evidence are untouched.
- Fresh dev Python: `outputs/engineering-venv/Scripts/python.exe` (3.12.14),
  frozen `uv sync --extra dev`; use this for bounded CPU/synthetic tests.
- Frontend installed: pnpm 11.22.0, existing `web/node_modules`.
- Hardware inventory: RTX 4080 SUPER 16,376 MiB, driver 616.92; Windows
  FFmpeg 8.0.1. Inventory is not GPU qualification.
- Known blocker: unresolved native corruption now also observed on Windows:
  unchanged strict palette child failed with `0xC0000005` after one earlier pass.
  Targeted result: 18 passed/1 failed; broad run stopped on learning the fault.
  Do not retry strict/local stress. Evidence: ignored
  `outputs/engineering-validation/native-windows-2026-10-12.md`.
- Windows portability fixes: worker flush opens `r+b` without truncating;
  truncated mmap OSError retains cause under validation ValueError. Independent
  review found no code blocker. Ruff, 4 frontend tests and build passed.
- New assignment explicitly permits software progress with host qualification
  open, superseding historical stage language forbidding further implementation.
- Never paid/cloud generate or upload private media without fresh permission;
  do not change host settings, reset/delete data, bypass quality/consent gates or
  force-push. Fast/Combined cloud approval remains blocked.
- UI/UX Pro Max loaded at `C:/Users/mudab/.codex/skills/ui-ux-pro-max/SKILL.md`;
  preserve React/Radix/Inter/theme/layout identity and compare affected states.
- Read next: checkpoint, ledger, plan, approved
  `docs/architecture/step-4.5-workflow-design.md` relevant sections, actual Git/PR
  state, then only the active subsystem's files.
