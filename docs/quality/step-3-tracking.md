# Step 3 — entrance tracking and shot boundaries

Work starts from committed Step 2 `97edb68` on `codex/step-3-tracking-boundaries`.
The initial tree and index were clean, with no tracked/staged source or output media.
The user approved the Step 2 comparison sheets before Step 3 implementation.
Original revision 3 and all Step 2 private artifacts remain preserved.

## Diagnosis and visibility adjudication

The pinned SAM 2.1 large checkpoint and saved JPEG inputs reproduced **all 32 entrance
masks exactly**: zero changed pixels on every frame 160–191. Frames 160–166 were yielded
with subject ID 3 and maximum logit **−1024**, SAM's `NO_OBJ_SCORE` sentinel. The model's
object-presence branch suppresses the mask when its object score is nonpositive. These
frames were not omitted by propagation, lost during storage, or cleared by another ID.
The original entrance contains only one active cast label.

An active cast interval is not proof of visible person pixels. Native 720×1280 source
crops, normalized frames, and the lower-door/foot-region sequence support full occlusion
at 160–166: the emerging tan rectangle is the bag, while the person is behind the car/door.
The dark lower-door area is particularly important to review; a forced late-anchor trial
painted small phantom foreground there. The candidate declares `[160,167)` fully occluded
with a source-review reason, retains zero masks, and does not paint the bag or hidden body.
This is a **manual visual adjudication**, not a conclusion inferred from a detector miss
or the original empty mask. User visual approval of these small/dark areas remains required.

Visible hand/wrist and boot/leg parts emerge at 167; head edges follow around 172–173. Frames
167–191 remain partially occluded and require nonempty visible-person masks. The original
anchor at **186** used points `(286.2,643.2)` and `(294.3,518.4)` and a box with top
`y=451.2`; the visible head/hair begins near `y=406`. The seed therefore starts with an
incomplete head selection and unwanted nearby pixels. Frames 167–185 are **backward
propagation from this late seed**, rather than forward tracking deterioration. The old
model also assigns car/window-pillar pixels to the head before the head emerges. Many
face/body interiors at 174, 180 and 185 were already covered; no blanket face failure at
every entrance frame is claimed.

The accepted private recipe keeps the existing cast IDs and interval endpoints. It uses
a reviewed whole-person seed at 186, including the head and visible hands/boot, then
contextual corrections at **167 and 174**. The earlier corrections use positive points
on visible anatomy and negative points on the pillar, door, car panel, bag and nearby
occupant. Their boxes are omitted to avoid resetting the tracked selection. A new explicit
`seed_frame=186` allows those earlier corrections to receive tracked context. Other
intervals keep their default earliest seed, preserving Step 2's behavior. Trials that
selected the pillar, car or phantom foreground were rejected and remain private evidence.
The enlarged hand audit rejected an earlier candidate that had lost the small hand
interiors at 167 and 169 (0%, whereas the original covered them). A positive point at
`(277,475)` on frame 167 and a bag-negative point `(289,482)` restore them through
propagation; added early-hand regressions now require 100%. The rejected candidate
produced **2 failures and 5 passes** in the seven anatomy cases. There is no dilation,
hull fill, reconstructed hidden anatomy or artificial body fill.

## Exact code and test changes

| File | Purpose |
|---|---|
| `backend/openjutsu/types.py` | Validated evidence-reasoned visibility ranges and optional annotated seed selection |
| `backend/openjutsu/tracking.py` | Derive fresh visible spans; validate anchors; apply earlier/later contextual corrections; reject wrong SAM counts/indices/IDs; atomically reject collisions; report presence for each cast member |
| `backend/openjutsu/worker.py` | Infer only visible spans with span-specific JPEG directories; preserve other labels; stop on collisions and unexplained per-subject gaps |
| `backend/openjutsu/engine.py` | Include visibility/seed in mask cache inputs, bump only mask cache to version 5, reject unsupported SAM 3 tracking options |
| `backend/openjutsu/api.py` | Clear source-specific visibility/seed fields when saving reusable templates |
| `scripts/segment_pilot_candidate.py` | Extend the local candidate tool to start from preserved Step 2, change one interval only, use fresh inputs, export old/new conditioning, audit cropped faces, and verify every fixture member on exact readback |
| `tests/test_tracking_boundaries.py` | Offline worker tests for per-subject gaps, atomic collisions, cast ordering, declared absence/occlusion, reappearance anchors, partial occlusion, invalid visibility, seed context and escaped SAM indices/IDs |
| `tests/test_tracking_candidate.py` | 46 unmarked private-candidate cases for every entrance frame, measured old defects, anatomy/background probes, boundary sides, Step 2 preservation, conditioning and detector blind spots |
| `tests/test_candidate_fixture.py` | Reject incomplete or changed candidate fixture members, including previous conditioning |
| `tests/conftest.py` | Explicit private Step 3 fixture option; retain hash verification |
| `tests/test_preparation_baseline.py` | Remove the now-fixed visible-gap expected-failure marker; retain unrelated strict expected failures |
| `tests/test_tracking.py` | Make the existing predictor double satisfy the checked output contract; keep its assertions |
| `tests/test_recovery.py` | Verify preparation passes visibility and seed changes into mask cache inputs |
| `tests/test_api.py` | Extend the existing template test to verify visibility/seed are cleared |
| `docs/api.md`, `docs/architecture/shot-aware-preparation.md` | Document tracking semantics and the legacy empty-frame field's changed behavior |
| `docs/quality/step-3-tracking.md` | This report; no private media |

The legacy `allow_empty_frames` setting no longer exempts unexplained visible-subject
gaps. Full absence/occlusion requires a reason and splits propagation state; partial
occlusion does not waive presence. Unassigned frames are reported separately. Predicted
pixel overlap with another ID fails before changing either label; disjoint pixels in
overlapping cast intervals remain order-independent. This is scoped tracking validation,
not Step 4's complete anatomical/appearance preparation gate.

## Coverage and visual evidence

| Reviewed measurement | Previous | Candidate |
|---|---:|---:|
| Car/window-pillar probe at 169 | 80% selected | **0%** |
| Hair interior at seed 186 | 30.6818% | **100%** |
| Boot interior at 167 | 100% | 100% |
| Early hand interiors at 167, 169 and 171 | 100% | **100%** |
| Face/hair/torso/hand/boot interiors at 174, 180, 185 | 100% | 100% |
| Reviewed car-panel/bag exclusion probes | 0% | 0% |
| Detected entrance face hulls at 186–191 | — | **100% on all six** |

Interior probes are not full silhouette ground truth. The cropped face detector misses
160–185 even after enlargement; detection absence does not establish subject absence.
All entrance frames have source/old-label/new-label/old-conditioning/new-conditioning
sheets, plus enlarged views. Visual review finds improved seed hair, removal of old
pillar/nearby-occupant/door specks, visible face/body coverage and no obvious new background
contamination or identity swaps. Thin hair, fingers and dark occlusion edges still require
human review. The face-interior conditioning/depth MAE is 1.7556/255 at 174,
1.0000 at 180, 2.6346 at 185 and 2.7687 at 186; video compression prevents exact decoded
RGB equality. The existing unencoded compositor regression verifies selected pixels
use depth and unselected background retains source RGB exactly.

The frame-by-frame private ledger (`frame-review.csv` and `.json`) links each full-size
and detail sheet. Its S3 pixel counts are:

| Frame | Previous → candidate | Source review |
|---|---:|---|
| 159 | 0 → 0 | Before hard cut; S2 retained |
| 160 | 0 → 0 | Full occlusion |
| 161 | 0 → 0 | Full occlusion |
| 162 | 0 → 0 | Full occlusion; prop emerges |
| 163 | 0 → 0 | Full occlusion; prop emerges |
| 164 | 0 → 0 | Full occlusion; prop emerges |
| 165 | 0 → 0 | Full occlusion; review dark lower-door edge |
| 166 | 0 → 0 | Full occlusion; review dark lower-door edge |
| 167 | 650 → 609 | Visible hand/boot/leg; head hidden |
| 168 | 1021 → 722 | Visible hand/boot/leg; head hidden |
| 169 | 1535 → 785 | Remove false pillar/head selection |
| 170 | 893 → 711 | Visible hand/limb parts; head hidden |
| 171 | 1669 → 787 | Visible hand/limb parts; head hidden |
| 172 | 1700 → 915 | Small head edge emerges; wrist becomes clearer |
| 173 | 1872 → 1304 | Emerging head/face; car occludes body |
| 174 | 1554 → 1443 | Contextual correction |
| 175 | 1588 → 1488 | Visible face/body/limbs; partial occlusion |
| 176 | 1646 → 1556 | Visible face/body/limbs; partial occlusion |
| 177 | 1759 → 1695 | Visible face/body/limbs; partial occlusion |
| 178 | 2076 → 1983 | Visible face/body/limbs; partial occlusion |
| 179 | 2358 → 2318 | Visible face/body/limbs; partial occlusion |
| 180 | 2735 → 2695 | Reviewed anatomy interiors retained |
| 181 | 3216 → 3212 | Visible face/body/limbs; partial occlusion |
| 182 | 4708 → 4602 | Visible face/body/limbs; partial occlusion |
| 183 | 6071 → 5824 | Visible face/body/limbs; partial occlusion |
| 184 | 7821 → 7422 | Exclude nearby occupant/background |
| 185 | 10440 → 9896 | Retain visible anatomy; remove door speck |
| 186 | 18887 → 16935 | Correct seed head/hair and unwanted pixels |
| 187 | 26040 → 22997 | Corrected forward propagation |
| 188 | 35221 → 31096 | Corrected forward propagation |
| 189 | 50110 → 42222 | Corrected forward propagation |
| 190 | 77357 → 64522 | Corrected forward propagation |
| 191 | 81204 → 81172 | Last entrance frame |
| 192 | 97662 → 97662 | Hard cut; separate preserved Step 2 interval |

Counts alone neither establish coverage nor contamination. The candidate has 25 visible
entrance frames without an unexplained gap. All 400 frames outside `[160,192)` are
byte-identical to Step 2. All configured boundaries have both valid adjacent frame sides
in the 75-frame fixture: 0, 110, 160, 192, 296, 374, 378 and 432. No label crosses its
permitted interval. Frames 374–377 remain **unassigned by the saved cast recipe**, not
newly declared physical absence; source/conditioning review of those unchanged frames
is retained for later preparation-quality work.

Private artifacts (ignored and uncommitted):

- `outputs/step-3-candidate/final-reviewed-v2/masks.npy`, `recipe.json`, `tracking.json`
- `final-reviewed-v2/conditioning/conditioning.mp4`, `fixture/frames.npz`
- `final-reviewed-v2/sheets/frame-*.png`: 48 full-resolution five-panel comparisons
- `final-reviewed-v2/sheets/detail-*.png`: all 32 enlarged entrance comparisons
- `final-reviewed-v2/sheets/entrance-contact-160-191.png`: whole-interval contact sheet
- `final-reviewed-v2/frame-review.csv`, `.json`, `measurements.json`, `face-hull-audit.json`
- `native-early.png`, `native-feet-160-167.png`: native-resolution visibility evidence
- `replayed-original.json`, rejected trials and original failed fixture: diagnostic history

Two independent candidate SAM runs are bit-identical. Candidate mask SHA-256:
`5f715d33fce769fa365193ccc500885f2746700ce0ba473cb77c3e9158bcef3f`.

## Step 2 preservation and threshold distinction

Frames **230, 242, 260 and 280 are byte-identical** to the accepted Step 2 masks, as is
the entire `[192,296)` interval. Critical face/conditioning regressions still pass;
the previously approved head/hair/body silhouettes are preserved. The contextual
correction sequence remains unchanged for recipes without an explicit later seed.

Step 2's **99.8159% minimum** is the broad detector audit minimum, at frame 295,
among 100 detections; that audit's threshold is **99.5%**. The **99.9% critical-hull
threshold** applies specifically to frames 230 and 260: 100% and 99.9696%, respectively.
**99.8159% does not satisfy 99.9%**; the two tests cover different populations. No threshold
was weakened in Step 3. The 28 excluded hull pixels at 260 remain reviewed background
gaps, not a license for leaked facial RGB. Neither hull threshold proves complete-person
coverage or every contour pixel.

## Checks and preservation

Run from the repository with the WSL CPU environment:

```bash
/home/saad/.local/share/openjutsu/api-venv/bin/python -m pytest -q tests \
  --pilot-fixture outputs/step-1-baseline/fixture-verified \
  --candidate-fixture outputs/step-2-candidate/final-reviewed/fixture \
  --tracking-fixture outputs/step-3-candidate/final-reviewed-v2/fixture
/home/saad/.local/share/openjutsu/api-venv/bin/ruff check backend tests scripts
/home/saad/.local/share/openjutsu/api-venv/bin/ruff format --check backend tests scripts
```

| Check | Actual result |
|---|---|
| Original synthetic tracking defects, before changes | **3 failed, 1 passed**: hidden cast gap, silent collision overwrite, ghost during declared full occlusion |
| Unmarked entrance defect contracts against private old masks | **2 failed, 42 deselected**, exit 1: pillar 80%, hair 30.6818% |
| Same Step 3 candidate module with verified candidate | **46 passed**, exit 0 |
| Full suite with all three private fixtures | **133 passed, 10 strict expected failures**, exit 0; no skips |
| Ruff lint/format and Git whitespace check | Passed |
| `pnpm --dir web test` | **3 passed**, exit 0 |
| `pnpm --dir web build` | TypeScript and production build passed, exit 0 |
| Original preservation snapshot | **560 files / 119 records**, original events/tasks unchanged |
| Step 3 starting snapshot, including Step 2 private artifacts | **617 files / 119 records**, original events/tasks unchanged |

The first full run had **86 passes, 10 expected failures and 44 fixture-load errors**:
the newly generated fixture's `previous_conditioning.npy` member failed CRC in both local
Python environments. It was not skipped or accepted. The failed file remains private;
a separate `fixture-verified` was rebuilt from the unchanged videos and readable members.
Every member passed CRC and exact array readback, and all candidate/full-suite cases were
rerun. The candidate tool now verifies every member before claiming fixture completion.
The serialization failure's underlying mechanism remains unisolated; this does not repair
or qualify the original numerical depth artifact. Depth CRC/cache work remains Step 5.

The ten strict expected failures are five immutable original-pilot quality contracts and
five still-unimplemented anatomical/compositor gate contracts. The historical nonzero
160–166 assertion stays unchanged to preserve the Step 1 baseline, but it is not the new
source-reviewed occlusion acceptance rule. The synthetic **visible** gap contract is now
unmarked and passes by explicit rejection. No new expected-failure marker or weaker quality
assertion was introduced. Existing Starlette/httpx and optional SAM postprocessing-extension
warnings remain. Step 2's earlier isolated native NumPy abort remains unisolated; it did
not recur in the reported Step 3 runs.

Preservation commands:

```bash
python scripts/preserve_pilot.py verify outputs/step-1-baseline/preservation.json
python scripts/preserve_pilot.py verify outputs/step-3-preservation/preservation.json
```

The final v2 candidate fixture also passed CRC and exact array readback directly in the
candidate tool; the failed earlier fixture remains retained.

Both checks include source, reference copies, masks, conditioning, original generation,
revision/attempt records and diagnostic evidence. No provider, cloud-generation, paid
request or external media upload was made. No original or Step 2 artifact was rewritten.

## Acceptance and remaining review

Local implementation, regression, identity/interval and preservation conditions pass.
The candidate's reviewed anatomy and conditioning are visually acceptable at inspected
resolution; user visual acceptance of the early occlusion adjudication, full interval and
boundary comparisons is still required. Automated coverage cannot certify tiny faces,
dark occlusion edges, flyaways or fingers. Visibility reasons are authored evidence, not
an automatic proof of absence; incorrect declarations can exclude real foreground and
must be reviewed. Collision handling stops for correction rather than inventing ownership.

Remaining unrelated issues stay documented: unassigned 374–377, reflections/fine appearance
boundaries, full preparation-quality gates, depth integrity, provider/reference auditability
and generation identity/motion limitations. This stage does not qualify the complete
conditioning or a paid pilot. The new visibility/seed settings are available in recipe/API
data; no new studio controls or frontend redesign were added.

Recommend Step 4 **only after the user's Step 3 visual approval**. Its scope should be
whole-person/source-appearance checks and preparation gates, retaining explicit visibility,
tracking presence and collision evidence. Step 4 is not started.
