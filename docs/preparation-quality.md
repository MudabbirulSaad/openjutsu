# Preparation quality

Normal Engine preparation registers the exact source, mask, depth, composite and conditioning
artifacts, then runs a local quality stage before offering approval. It never edits masks or
initiates generation. Explicitly install `mesh quality` with the model installer; jobs do not
download weights. Quality uses MediaPipe Pose Landmarker Heavy float16 version 1 and Face
Landmarker, independently in IMAGE mode on each source frame, without carrying tracking state
across shots.

## Evidence and limits

Every frame is decoded. Required hashes, timeline indices, uint8 label dimensions, video lengths
and readable finite numerical depth members are checked. Depth readability fails closed; the
storage/cache repair remains separate work. The mask worker records its atomic
`reject_before_mutation` policy, and the gate rejects reported collisions. Out-of-interval IDs
and empty masks for intended visible subjects are critical. Explicit absence/full occlusion
excludes those visible spans; partial occlusion does not excuse an empty mask. Unassigned
intervals require a visibility/casting decision, rather than asserting physical absence.

Face hulls and high-confidence body/hand/limb landmarks supplement source-reviewed evidence.
Missing detection never proves absence. Face detector results lack a calibrated result score,
so confidence is null. Pose point confidence is the minimum of visibility and presence.
Association uses mask-label agreement and never guesses a reference identity. Cropped-out body
landmarks do not invalidate a reliably associated close-up face, but cannot certify anatomy.

Recipe `quality_regions` specify source-reviewed interior/background boxes, frame ranges,
cast IDs, anatomy parts, dispositions and reasons. They are evidence separate from SAM prompts.
Missing known replacement interiors, selected reviewed background, or source RGB in a
designated face blocks approval. Exact composite/conditioning is compared with source and
guide, allowing encoding differences. The validator never dilates masks, fills hidden anatomy,
assigns background people, or automatically erases reflections.

Whole-region averages can conceal an original eye/face patch. Source-reviewed face interiors
also measure per-pixel source/guide attribution. At least 16 source-like pixels exceeding the
critical uncovered fraction produce an unwaivable localized RGB finding. Detector-derived
boundary regions do not establish that pixel truth on their own.

| Configurable quality policy | Default | Meaning |
|---|---:|---|
| Broad face hull coverage | 99.5% | Boundary discrepancies require inspection |
| Critical face hull coverage | 99.9% | Enforced for explicit critical subject/frame pairs |
| Reviewed anatomy interior coverage | 98% | Confirmed missing anatomy blocks approval |
| Reviewed background selection | 0.5% maximum | Larger contamination blocks approval |
| Detector detection/presence admission | 0.5 | Not a returned confidence score |
| Landmark visibility/presence | 0.9 minimum | Reliable in-image probes only |
| Structural pixel MAE | 12/255 maximum | Codec tolerance, not a perceptual score |
| Source similarity MAE | 6/255 maximum | Combined with guide disagreement for RGB attribution |

Defaults are exposed through the recipe API and recorded in reports. An earlier broad minimum
of 99.8159% does not meet a universal 99.9% rule: critical frames are a separately declared
population. Convex hulls include background in some profile faces, so broad detector-boundary
discrepancies remain warnings, without lowering the measured threshold. Source-reviewed misses
and confirmed source RGB remain critical. Interior probes never prove complete hair, fingers,
silhouette, occlusion edges or semantic identity. Every visible cast span therefore also needs
an explicit whole-person inspection reason.

## Review and approval

PASS describes a measured contract; WARNING needs inspection; BLOCKED requires correction or
an unresolved decision; REVIEWED records explicit adjudication. Contiguous uncertain detections
are grouped while retaining per-frame evidence. The Review screen shows counts, subject/frame/
time ranges, source/mask/conditioning comparisons, confidence, metrics, decisions and reasons.
Full-resolution frames and the immutable JSON audit are available.

`GET /api/jobs/{id}/quality` returns the effective report. `POST /quality-review` requires
revision, report ID, finding ID, allowed resolution and a nonblank reason of at least eight
characters. Confirmed critical defects cannot be waived. `requires_replacement` stays BLOCKED.
False detection and intentional background preservation require a recorded reason. Review
overlays never rewrite the immutable report.

Backend approval binds job, revision, full recipe, source and all preparation artifact IDs and
hashes. Reviews bind report ID/hash; approval includes binding and review receipts. Recipe
changes and new preparation clear approval/reviews. Approval, new generation reservations and
the pre-upload boundary rehash actual files. Ordinary display uses hashes and file stamps.
Missing, unreadable, changed or incomplete evidence rejects approval. Duplicate operation IDs
still retrieve their original reservation idempotently; new operations must satisfy the gate.

Structural attribution currently supports Advanced mode. Fast/Combined still prepare previews
but require a mesh-specific validator before generation approval. This is an explicit limit.
Historical pilot failures remain immutable. Low-level mask/composite stages may materialize bad
candidates for diagnosis; the complete workflow gate rejects them before approval. Their old
expected failures are not reclassified as passes.

Synthetic tests cover leakage, anatomy, occlusion, IDs/intervals, collisions, background false
positives, reasoned review, stale receipts, unreadable evidence and pre-upload rejection.
Private evidence tests are opt-in: use `pytest tests` before the `--pilot-fixture`,
`--candidate-fixture`, `--tracking-fixture` and `--quality-fixture` options. Identifiable media
and detailed private audits stay outside Git.
