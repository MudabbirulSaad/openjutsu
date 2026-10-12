# Engineering goal ledger

Statuses: pending, active, partial, complete, deferred, blocked. Completion means
the acceptance criteria passed and the change is integrated. A slice does not
complete a whole goal. Risk: L low, M medium, H high. PR references follow below.

## G0 — Establish and protect baseline (active, M)
- Problem/outcome: separate independently correct integrity code from unresolved host stability.
- Dependencies: none. Scope: remote/local history, PR #3, CI, privacy and preservation; no hardware repair.
- Changes: retain investigation/reproducer; plan/ledger/handoff; review and integrate accepted safeguards.
- Acceptance: original commits/evidence preserved; exact PR code reviewed; required CI passes; qualification explicitly open.
- Validation: Git ancestry/status, public-tree scan, focused artifact tests and independent remote CI.
- Reference: PR #3, remote code `8516b4d`, retained local `08b511c`; review pending.

## G1 — GPU foundation and performance visibility (active, M)
- Problem/outcome: execution and transfer costs are opaque; expose actual measurements and a small frame contract.
- Dependencies: G0 integrity acceptance for merge. Scope: worker stages and model lifecycle; no speculative hierarchy or unmeasured acceleration.
- Changes: device/format/ownership/timestamp description, stage CPU/wall/memory/allocator statistics, seam inventory.
- Acceptance: actual device distinguished from availability; unknown values stay null; transfer/format/lifetime rules explicit; serial VRAM budget retained.
- Validation: synthetic contract/telemetry tests; bounded measurements where safe; audit model I/O and transfer seams.
- Reference: pending.

## G2 — Durable progress and ETA (pending, M)
- Problem/outcome: a single transient counter obscures work/recovery; retain truthful operation timelines.
- Dependencies: G0, profiling scope from G1. Scope: existing local preparation/export first; expand imports/cloud separately.
- Changes: Store operation/run/phase records and atomic events; Engine callbacks; snapshot/cursor API; shared progress UI and bounded updates.
- Acceptance: monotonic scoped units, null unknown totals, elapsed/waiting, interruption and new runs on restart, retained completed phases, qualified ETA only.
- Validation: store recovery/replay/stale-event tests, synthetic worker/cancellation integration, reconnect/browser/accessibility checks.
- Reference: pending.

## G3 — GPU-native SAM masks (pending, H)
- Problem/outcome: repeated logits/array transfers; reduce measured postprocessing cost safely.
- Dependencies: G0/G1; safe tensor parity runtime. Scope: threshold/merge/collision/statistics/palette; keep tiny faster CPU work.
- Changes: bounded device-resident label processing and explicit artifact transfer at publication.
- Acceptance: exact IDs, half-open visibility, contextual corrections and atomic rejection match existing behavior; deterministic saved masks; measured benefit.
- Validation: Step 2/3 regressions, CPU/tensor parity and equivalent GPU timing/VRAM/transfer measurements.
- Reference: pending; workstation qualification open.

## G4 — GPU compositing and depth (pending, H)
- Problem/outcome: repeated CPU conversions; improve equivalent frame processing without changing depth semantics.
- Dependencies: G0/G1, pinned VDA inspection. Scope: resize/colour/blend/guidance; no cache-integrity bypass.
- Changes: measured tensor implementation with CPU fallback, aligned numeric depth serialization/readback.
- Acceptance: dimensions/count/finite values/compositing semantics preserved; safe VRAM and actual improvement.
- Validation: synthetic parity, artifact regressions, pinned model contract and bounded GPU comparison.
- Reference: pending.

## G5 — Hardware video pipeline (pending, H)
- Problem/outcome: expensive video transport/encoding; enable only proven hardware capabilities.
- Dependencies: G0/G1. Scope: NVDEC/NVENC/scaling/previews/export; authoritative normalization retained until parity proven.
- Changes: capability probes and qualified selectable acceleration with explicit fallback.
- Acceptance: exact 24 fps count/orientation/aspect/audio timing and acceptable visual quality; no byte-identity claim.
- Validation: small synthetic encode/decode, metadata/count/alignment and equivalent wall-time tests.
- Reference: pending.

## G6 — Detection, audio and upscale (pending, H)
- Problem/outcome: optimize expensive supporting stages independently (6A/6B/6C).
- Dependencies: G0/G1/G2; pinned adapters. Scope: independent detectors, expensive audio, upscale I/O/batches; preserve models/quality/offload.
- Changes: tested device choices and real per-phase/batch callbacks; no silent OOM degradation.
- Acceptance: detection agreement/coverage, exact soundtrack alignment, tested SeedVR2/Real-ESRGAN profiles and safe 16 GB headroom.
- Validation: independent detection fixtures, audio regressions and sample counts, pinned upscale adapter tests and bounded qualification.
- Reference: pending; subgoal statuses 6A pending, 6B pending, 6C pending.

## G7 — References and stable mentions (pending, M)
- Problem/outcome: references lack useful feedback and stable prompt binding.
- Dependencies: G0. Scope: sanitized local images, multiple images/roles and named IDs; suitability never promises likeness.
- Changes: capability-aware local assessments, character/image token model, accessible editing and ambiguity/deletion feedback.
- Acceptance: rename/reorder/delete cannot silently rebind; stylized/multiple-person/missing-detector cases explained.
- Validation: synthetic image/mention/rename/deletion tests, API ownership checks and browser interaction/state comparison.
- Reference: pending.

## G8 — Plans and provider bindings (pending, H)
- Problem/outcome: free text cannot safely select supported operations/payload identities.
- Dependencies: G7. Scope: deterministic resolution first, optional Qwen suggestions; no autonomous paid actions.
- Changes: typed proposal/capabilities/preserve-change operations, unresolved choices, versioned fingerprints, immutable manifests/redacted previews.
- Acceptance: consistent upload/payload ordering, exact source mapping, unsupported movement/background/identity-only requests remain explicit.
- Validation: plan/manifest tamper and stale-revision tests, provider adapter fixtures and existing consent/budget regressions.
- Reference: pending.

## G9 — Automatic preparation (pending, H)
- Problem/outcome: supported preparation requires too much manual setup; propose only source-supported evidence.
- Dependencies: G2/G7/G8 and G3/G4 where qualified. Scope: cuts/candidates/anchors/visibility/corrections with confirmation for uncertain evidence.
- Changes: conservative analysis/coordinator extending existing Engine and targeted correction attempts.
- Acceptance: no invented masks or returning identity; Step 1–4 invariants and complete quality audit remain mandatory.
- Validation: cuts/mapping/occlusion/source-anchor fixtures, cancellation/revision tests and corrected real-media qualification.
- Reference: pending.

## G10 — Actionable quality review (pending, M)
- Problem/outcome: technical finding lists impede correction; present exact person/shot/time tasks.
- Dependencies: G0; G9 evidence when available. Scope: immutable report projection and existing Viewer; no warning removal or blanket approval.
- Changes: grouped tasks, exact-frame/interval comparison, anatomy highlights and clear corrections/Advanced details.
- Acceptance: every original finding reachable; report/revision binding and all blocking rules retained.
- Validation: grouping membership tests, gate regressions, navigation/playback/browser/accessibility state checks.
- Reference: pending.

## G11 — Complete Simple Studio (pending, H)
- Problem/outcome: normal workflow exposes too much technical setup; compose clear next actions.
- Dependencies: G2/G7/G8/G9/G10. Scope: existing React identity/components and one revision system; Advanced immediately accessible.
- Changes: Video → References → Prompt → Prepare → Review → Approve → Generate → Export with meaningful states.
- Acceptance: cost/upload consent remains explicit; stale drafts/reconnect safe; themes/mobile/keyboard/screen readers work.
- Validation: original/new visual comparison and representative state/browser/accessibility end-to-end contracts.
- Reference: pending.

## G12 — Qualification and release (pending, H)
- Problem/outcome: passing synthetic CI cannot certify the product/runtime; establish bounded release evidence.
- Dependencies: all required preceding deliverables. Scope: integration, privacy/provenance/recovery/VRAM/quality; paid pilots require fresh budget approval.
- Changes: risk-appropriate integration validation, capability restrictions and concise release report.
- Acceptance: counts/timestamps/audio/depth/mappings/gates/accessibility validated; all unfinished hardware/model/provider paths explicitly unqualified.
- Validation: subsystem and integrated tests, preservation/privacy checks, equivalent performance evidence and owner-approved real-media/provider milestones.
- Reference: pending; no release claim.
