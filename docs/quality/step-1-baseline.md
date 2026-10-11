# Step 1: preserved pilot failure baseline

Completed locally on 2026-10-11. Branch: `codex/step-1-failure-baseline`.
Starting commit: `cf248e6e4bbde4e0091e7917f49eda38a8df9960`.
No production code, recipe, job record, original media or mask was changed.
No paid request or private-media upload was made.

## Saved evidence and preservation

The private diagnostic bundle supplied for this stage is
`C:/Users/mudab/AppData/Local/Temp/openjutsu-root-cause-Em48dO/private-diagnostic-bundle.zip`.
The existing pilot exports are in ignored `outputs/gas-station-pilot/`.
The original runtime is `/home/saad/.local/share/openjutsu` in Ubuntu WSL.

- Job: `2df42d044c78420c9a05b01820202ef2`, revision **3**.
- Attempt: `204fbb6fdf294f109cfdcc454d833146`, succeeded, settled, exactly one generation.
- Approved/submitted conditioning: `16ec821a69f340a99f804ead48d76655`.
- The recipe, attempt snapshot and approval still agree.
- `outputs/step-1-baseline/preservation.json` records **560 files** and **119 ledger records**,
  plus the job's events and tasks. It covers registered artifacts across the saved revisions,
  source/reference originals and sanitized references, revision 3 SAM input JPEGs, cache
  tasks/manifests, pilot exports and every existing diagnostic file, including the ZIP.
- Capture checks registered files against their saved ledger SHA-256 values. Verification
  checks the entire captured file inventory, sizes and SHA-256 values, and logical ledger
  state. SQLite is opened with `mode=ro`; neither Store nor Engine is instantiated.
- The diagnostic ZIP is also copied byte-for-byte into ignored `outputs/step-1-baseline/`
  to preserve a copy beyond the temporary directory's lifetime.

Final verification reports all **560 hashes and 119 records unchanged**. This establishes
byte preservation, including the already defective numerical-depth archive; it does not
certify that every preserved file is semantically correct.

## Files added

| File | Purpose |
|---|---|
| `scripts/preserve_pilot.py` | Read-only capture and integrity verification; refuses to overwrite a preservation manifest or write into original runtime/evidence folders |
| `scripts/reproduce_pilot.py` | Extracts exact indexed private frames and masks; optional local, pinned SAM initial-prediction replay |
| `tests/conftest.py` | Explicit `--pilot-fixture` option; private tests skip when it is absent; checks fixture array SHA-256 |
| `tests/test_preparation_baseline.py` | Synthetic predictions through the real worker mask/composite stages; desired quality contracts and valid-input controls |
| `tests/test_pilot_baseline.py` | Saved-mask, tracking-gap and decoded-conditioning reproduction plus desired quality contracts |
| `tests/test_pilot_preservation.py` | Synthetic preservation controls: no database writes, detect source/attempt changes, refuse manifest overwrite |
| `docs/quality/step-1-baseline.md` | This report and reproducible commands |

All new media-derived fixtures, the ledger snapshot, replay output, copied diagnostic ZIP
and test logs are under ignored `outputs/step-1-baseline/`. None is staged or committed.
Public test inputs are generated arrays and text placeholders, with no identifiable media.

## Reproduced failures and controls

| Defect | Evidence reproduced | Tests |
|---|---|---|
| Clothing-only SAM masks at 230 / 9.583s and 260 / 10.833s | Saved subject-3 areas are **203,379** and **205,727** pixels; both diagnostic interior-face ROIs have **0%** coverage | Private characterization verifies pixel counts, uncovered ROIs and original replay; quality tests require ≥95% ROI coverage; synthetic worker tests show partial masks accepted |
| Missing masks at 160–166 / 6.667–6.958s | All seven arrays are zero despite an active subject interval; the tracking report lists them as empty | Private tests verify every frame and exclusive interval membership; synthetic worker test shows global empty allowance accepts the same gap |
| Original RGB in conditioning | Face ROI conditioning/source MAE is **2.6288/255** at 230 and **2.4544/255** at 260; conditioning/depth MAE is **49.1792/255** and **37.1579/255**. All seven empty-mask frames also closely match the source | Private tests distinguish leaked source appearance from depth. Synthetic worker composite tests show exact face RGB passthrough at 160, 230 and 260 |

The fresh local SAM replay uses the unchanged cached JPEG interval, annotations, checkpoint
and SAM source commit. All six initial anchor predictions (200, 210, 230, 242, 260, 280)
match saved masks at **IoU 1.0, zero changed pixels**. These are initial predictions before
tracking, confirming the diagnostic's clothing-selection observation at the two bad anchors.
Checkpoint SHA-256 and source commit are checked against saved model provenance.

The latest private extraction/replay is `outputs/step-1-baseline/fixture-verified/`.
It contains nine exact frames of source, rendered depth, conditioning and label masks,
their frame IDs and evidence-derived face ROIs. `sam-version.json` and `sam-replay.json`
record the pinned model provenance and fresh replay results.

Synthetic tests double model inference and video I/O only; worker materialization,
validation, mask storage and compositing run unchanged. They do not claim that a synthetic
torso click proves actual SAM behavior. The real checkpoint replay supplies that evidence.
Valid complete masks remove source appearance and preserve unselected background. The
existing rejection when `allow_empty_frames=false` is also tested.

Quality contracts are explicit **strict expected failures**, restricted to AssertionError.
Unexpected exceptions fail normally; an unexpected pass also fails, requiring the marker
to be removed when the corresponding defect is corrected. `--runxfail` exposes the red
contracts directly. No production workaround or passing quality claim is introduced.
The immutable private fixture should continue to reproduce the old failure; corrected
preparation will need a separate candidate fixture and unmarked regression tests.

## Commands and actual results

Run these in Ubuntu from `/mnt/o/repo/openjutsu`. The CPU environment requires no GPU,
provider credentials, private URLs or model downloads.

```bash
cpu=/home/saad/.local/share/openjutsu/api-venv/bin/python
ruff=/home/saad/.local/share/openjutsu/api-venv/bin/ruff
fixture=outputs/step-1-baseline/fixture-verified

"$ruff" check backend tests scripts
"$ruff" format --check backend tests scripts
"$cpu" -m pytest -q

"$cpu" -m pytest -q tests/test_preparation_baseline.py tests/test_pilot_baseline.py \
  tests/test_pilot_preservation.py --pilot-fixture "$fixture"

# Deliberately exits 1: the current preparation fails these quality contracts.
"$cpu" -m pytest -q --runxfail tests/test_preparation_baseline.py \
  tests/test_pilot_baseline.py --pilot-fixture "$fixture" --tb=short

"$cpu" scripts/preserve_pilot.py verify outputs/step-1-baseline/preservation.json
python3 scripts/check_public_tree.py
python3 scripts/check_public_tree.py --staged
git diff --cached --check
```

| Check | Actual outcome |
|---|---|
| Ruff lint and format | Passed |
| Full default Python suite | **47 passed, 11 skipped, 6 xfailed**, exit 0; private cases are opt-in |
| Focused suite with private fixture and preservation tests | **13 passed, 11 xfailed**, exit 0 |
| Explicit red contracts | **11 failed, 9 passed**, exit 1; same failures on repeated runs |
| Fresh CUDA SAM replay | Six masks match exactly; checkpoint hash and source commit verified |
| Preservation verification | All 560 files / 119 records unchanged, revision 3 preserved |
| `pnpm --dir web test` | **3 passed** |
| `pnpm --dir web build` | TypeScript and production build passed |
| Tracked/staged public-tree hygiene and staged diff check | Passed; private files ignored and absent from index |

The CPU suite emits the existing Starlette/httpx deprecation warning. The local SAM replay
emits the existing optional CUDA post-processing extension warning, also recorded in the
prior diagnostic. The exact masks still reproduce; this warning is not evidence that it
caused the excluded heads. No frontend/browser behavior changed, so browser scenarios
were not rerun for this test/tooling-only stage.

To build a fresh fixture/replay without overwriting either an existing fixture or evidence:

```bash
PYTHONPATH=backend /home/saad/.local/share/openjutsu/venv/bin/python \
  scripts/reproduce_pilot.py outputs/step-1-baseline/preservation.json \
  --out outputs/step-1-baseline/fixture-new --replay-sam
```

Initial preservation capture used:

```bash
"$cpu" scripts/preserve_pilot.py capture \
  --runtime /home/saad/.local/share/openjutsu \
  --evidence /mnt/c/Users/mudab/AppData/Local/Temp/openjutsu-root-cause-Em48dO \
  --exports outputs/gas-station-pilot \
  --job 2df42d044c78420c9a05b01820202ef2 \
  --attempt 204fbb6fdf294f109cfdcc454d833146 --revision 3 \
  --out outputs/step-1-baseline
```

## Acceptance, limitations and proposed Step 2

**Step 1 acceptance conditions are met.** A dedicated branch preserves the starting
revision; all three requested defects have repeatable local/synthetic tests; a fresh SAM
replay confirms the saved clothing-only predictions; relevant automated checks ran;
original revision, attempt, references, masks, output and diagnostic evidence are unchanged.
There are no Step 1 blockers. The known quality failures are intentionally unresolved.

The interior-face ROIs are evidence-derived probes, not complete head/hair/body ground
truth. The nine-frame fixture is deliberately limited to the requested failures; it does
not certify all 432 frames. The numerical-depth CRC defect recorded by the diagnostic
remains intact for Step 5. Reference identity and motion limitations are not explained or
resolved by these baseline tests. Runtime originals still require ordinary local backups;
the preservation manifest detects changes rather than preventing unrelated cache cleanup.

Proposed Step 2 is limited to **complete-person SAM 2.1 segmentation**: separate initial
selection from corrections with tracking context, review the returned head/hair/body
coverage, and test the unchanged torso-only failure versus an explicitly complete-person
selection using the same pinned local model. Add corrected-output regression tests and
validate bad anchors plus neighboring frames against a new private candidate fixture.
Preserve revision 3, photographs and its failed output; create a separate candidate when
authorized. Tracking/shot gaps, preparation gates, depth repair, request auditability,
paid qualification and upscaling remain in their later stages.

**Stopped after Step 1. Step 2 requires separate user authorization.**
