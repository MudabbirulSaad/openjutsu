# Step 2: complete-person SAM 2.1 segmentation correction

Date: 2026-10-11. Branch: `codex/step-2-person-segmentation`, based on `9230046`.
Scope: SAM segmentation and annotation/correction handling only. Original job revision 3,
attempt, references, masks, conditioning, generation and diagnostic evidence remain intact.
No cloud generation, upload, paid API call, shot-boundary change or quality-gate implementation
occurred. This candidate is a local review artifact, not a new saved generation attempt.

## Cause and controlled local comparisons

The pinned SAM source identifies an untracked prompted frame as an initial conditioning
frame. The old worker added every annotation before tracking, so torso clicks at 230 and
260 independently selected clothing. Step 1 reproduced those initial outputs at IoU 1.0.
This is distinct from propagation deterioration, mask-file corruption or another subject
overwriting the two bad anchors.

Three private local comparisons used the unchanged checkpoint, source JPEGs and interval:

| Comparison | Result |
|---|---|
| Whole-person box/head/neck/body points at the bad anchors, original initial-anchor ordering | Both face ROIs reach 100%; controls 242 and 280 remain byte-identical |
| Track the seed first, then add the original torso clicks as contextual corrections | Both face ROIs reach 100%; controls stay close to their original silhouettes |
| Contextual corrections plus explicit whole-person prompts and background negatives | Selected candidate; both bad-anchor face ROIs reach 100%; controls remain visually acceptable |

The close-ups touch all image edges, so their visible-person bounding box is `[0,0,1,1]`.
This is a box prompt, not a filled mask. The selected recipe retains the original torso
point and adds positive points at `(0.50,0.35)` (face), `(0.46,0.16)` (hair/head), and
`(0.55,0.50)` (neck), plus background negatives at `(0.02,0.025)` and `(0.98,0.025)`.
Only annotations 230 and 260 change. The already successful first anchor at 200 and the
other annotations remain unchanged. Whole-person independent-initial predictions were
tested before using these prompts as tracked corrections.

## Exact implementation changes

| File | Change |
|---|---|
| `backend/openjutsu/tracking.py` | `sam2_track_interval` sorts/groups prompts, seeds the first annotation, warms tracking in both directions, applies later corrections with context, and yields final propagation. Same-frame positive/negative points and boxes merge; conflicting boxes fail explicitly |
| `backend/openjutsu/worker.py` | Uses that helper, configures SAM to retain correction frames as conditioning frames, and clears the subject's earlier pixels before writing returned masks |
| `backend/openjutsu/engine.py` | Mask cache version 3 → 4 to avoid reusing masks from the previous annotation sequence; no cache-integrity/depth changes |
| `tests/test_preparation_baseline.py` | Adds context-sensitive SAM replay double and regressions for both bad-anchor corrections and stale background removal |
| `tests/test_tracking.py` | Tests prompt ordering/context, normalized-coordinate scaling, negative labels, same-frame merging, subject IDs, exclusive interval boundaries and conflicting boxes |
| `tests/conftest.py` | Adds opt-in `--candidate-fixture` separately from the immutable pilot fixture |
| `tests/test_segmentation_candidate.py` | Unmarked candidate contracts reusing Step 1 assertions, anatomy/background probes, control-mask similarity, complete interval/label preservation and face-hull audit |
| `scripts/segment_pilot_candidate.py` | Pinned local SAM replay of one existing interval; private candidate masks/conditioning, measurements, fixtures and comparison sheets; no Engine/Store/provider calls |
| `docs/architecture/shot-aware-preparation.md` | Documents initial/correction sequencing and whole-person prompt review |
| `docs/quality/step-2-segmentation.md` | This report |

No dilation, convex-hull fill, box fill, morphological expansion or artificial head patch
was applied. SAM supplies every corrected selected pixel. Subject IDs and original
intervals remain unchanged. The only candidate mask interval replaced is S3 `[192,296)`;
all 328 other frames are byte-identical to the original label plane. The existing entrance
gap at 160–166 remains untouched. The model helper starts a separate state per interval.

## Measured and visual results

Candidate: ignored `outputs/step-2-candidate/final-reviewed/`. Full masks are saved separately
as `masks.npy`, with a new full 432-frame conditioning video at 540×960/24 fps and original
conditioning audio. The original revision 3 files are never destinations. Its private
fixture contains 40 selected frames, including both defects, immediate neighbors, controls
and the unchanged entrance gap. Two independent candidate builds produced identical full
mask SHA-256: `5c353916075c8ef0b8f4fe2b8b611e811cdc55222330a4026aa1e719535786cc`.

| Frame | Original face ROI coverage | Candidate face ROI | Candidate face-hull coverage | Candidate face/depth MAE /255 | Mask IoU to original |
|---|---:|---:|---:|---:|---:|
| 230 | 0% | 100% | 100% | 1.9704 | 0.5084 (head deliberately added) |
| 242 | 100% | 100% | 100% | 2.0465 | 0.993467 |
| 260 | 0% | 100% | 99.9696% | 1.9418 | 0.5039 (head deliberately added) |
| 280 | Already covered | 100% of its separate interior-face probe | 100% | 2.1164 | 0.997488 |

At all four frames, the manually placed hair, neck, torso, left-sleeve and right-sleeve
interior probes have 100% selected coverage. Background probes have 0% selection except
two pixels in the frame-260 probe (0.153%). No obvious background contamination appears
in the inspected comparisons. This is not a claim that every boundary pixel is perfect.

The foreground face detector finds 100/104 faces; minimum hull coverage is **99.8159%**.
Frames 218–221 are profile detector misses, reviewed in the all-frame sheets. At 260 its
convex hull crosses two background gaps beside the hair: 28 unselected pixels at
x492–511/y419–457. These were inspected in an enlarged original/marked crop and are
background, not retained facial appearance. A strict 100%-hull assertion exposed this;
it was replaced with a 99.9% critical-hull assertion after inspection. Filling the hull
would have introduced background. The manual face interiors and decoded-conditioning
assertions still pass unchanged, and the actual face is visually replaced by the guide.

All 104 changed frames were inspected in five original/old/new overview sheets; full-size
four-panel sheets cover 229/230/231, 242, 259/260/261 and 280. Additional limb/occlusion
sheets cover 192/194/198 and 294/295. Face, head mass, major hair strands, neck, torso,
sleeves and visible hands are acceptable around the corrected close-ups and controls.
Thin flyaways, fingers at prop/door boundaries, occluded and off-frame limbs cannot be
certified pixel-perfect. Legs/hands are outside the known close-up frames; this review
does not infer their coverage from a nonzero mask. The original facial reflection in the
car window is outside this foreground-person selection and remains a later-stage leak.
No new cast switch or empty mask appeared within the changed interval.

Private comparison paths include:

- `outputs/step-2-candidate/final-reviewed/sheets/frame-230.png`
- `outputs/step-2-candidate/final-reviewed/sheets/frame-260.png`
- `outputs/step-2-candidate/final-reviewed/sheets/frame-242.png`
- `outputs/step-2-candidate/final-reviewed/sheets/frame-280.png`
- `outputs/step-2-candidate/final-reviewed/sheets/interval-*.png`
- `outputs/step-2-candidate/review/face-hull-boundary-260.png`

No private image, fixture, full recipe, runtime snapshot or report is in the Git index.

## Tests and actual checks

Before the worker change, new context/stale-pixel tests failed: **3 failed**. After the
change: **3 passed**. The four Step 1 face/conditioning contracts first failed on the
original fixture; the exact same assertions now pass on the candidate with `--runxfail`.
The immutable old fixture deliberately retains its recorded failures. Static bad-mask
acceptance/gap/compositor expected failures remain for preparation gates/later stages.

Run from Ubuntu `/mnt/o/repo/openjutsu`:

```bash
cpu=/home/saad/.local/share/openjutsu/api-venv/bin/python
ruff=/home/saad/.local/share/openjutsu/api-venv/bin/ruff
candidate=outputs/step-2-candidate/final-reviewed/fixture

"$ruff" check backend tests scripts
"$ruff" format --check backend tests scripts
"$cpu" -m pytest -q tests --pilot-fixture outputs/step-1-baseline/fixture-verified \
  --candidate-fixture "$candidate"
"$cpu" -m pytest -q tests/test_segmentation_candidate.py --candidate-fixture "$candidate"
"$cpu" -m pytest -q --runxfail tests/test_pilot_baseline.py \
  -k 'covers_face or face_is_structural' --pilot-fixture "$candidate"
"$cpu" scripts/preserve_pilot.py verify outputs/step-1-baseline/preservation.json
python3 scripts/check_public_tree.py --staged
git diff --cached --check
```

| Check | Actual result |
|---|---|
| Default backend suite without private fixtures | **52 passed, 21 skipped, 6 expected failures**, exit 0 |
| Full backend suite with both private fixtures | **68 passed, 11 expected failures**, exit 0 |
| Unmarked candidate tests | **10 passed**, exit 0 |
| Step 1's four formerly red face/conditioning contracts on candidate | **4 passed**, exit 0 |
| Ruff lint / format | Passed |
| `pnpm --dir web test` | **3 passed** |
| `pnpm --dir web build` | TypeScript and production build passed |
| Preservation | **560 file hashes, 119 records and original events/tasks unchanged** |
| Tracked/staged public-tree hygiene and diff check | Passed; private files absent from index |

One early CPU worker-test process aborted inside NumPy. It did not reproduce in ten
subsequent worker-test processes (all exit 0), the candidate tests or the full suite.
`outputs/step-2-candidate/repeated-worker-checks.json` retains those repeat results. The
native abort's cause is not isolated; no production workaround was added. Existing
Starlette/httpx and optional SAM CUDA post-processing-extension warnings also remain.

Fresh candidate build (use a new output directory):

```bash
PYTHONPATH=backend /home/saad/.local/share/openjutsu/venv/bin/python \
  scripts/segment_pilot_candidate.py outputs/step-1-baseline/preservation.json \
  --recipe outputs/step-2-candidate/candidate-recipe.json \
  --probes outputs/step-2-candidate/anatomy-probes.json --subject 3 --interval 1 \
  --out outputs/step-2-candidate/new-review --audit-faces
```

The CPU tests are offline; CUDA/MediaPipe are needed only for candidate generation/audit.
Browser scenarios were not rerun because no studio/browser workflow changed.

## Acceptance and remaining limits

Step 2's local conditions are met for the known defects and reviewed interval, subject
to the user's visual review: main facial RGB is removed at 230/260; head/hair/body coverage
is visually acceptable; controls remain correct; no new interval gap or cast swap was
observed; targeted regressions pass; existing checks pass; original evidence is unchanged;
no cloud request occurred. A face ROI or detector result alone is not the acceptance proof.

Remaining issues are retained: entrance gaps/incomplete earlier tracking, shot-boundary
handling, facial reflections and fine boundary leaks, preparation-quality gates, numerical
depth CRC integrity, request/reference auditability, and unqualified identity/motion
generation quality. Nothing here qualifies a paid generation or certifies the whole
18-second conditioning. A whole-person seed still needs an appropriate prompt and review;
contextual correction is not a semantic guarantee for arbitrary torso clicks.

**Stopped after Step 2. Step 3 is not started and requires user review/authorization.**
