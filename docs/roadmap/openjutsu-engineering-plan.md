# OpenJutsu engineering plan

Owner assignment: 2026-10-12. This is the authoritative execution plan; the
[goal ledger](goals.md) tracks acceptance and the [handoff](openjutsu-handoff.md)
tracks continuation. The approved Step 4.5 architecture remains the design basis.
The newer assignment permits independently validated software work while native
runtime qualification remains open; historical stage reports are retained as evidence.

## Baseline and boundaries

- Integrated main starts at `01e03bc39de32fc0f57bbbadd2a77052cf7cb71c`.
- Draft PR #3 code head: `8516b4df8136cde774d83d9758bcde7409b31ef2`.
- Local investigation: `08b511ca395d6106a0842f623c047241936e45c3`, retained
  on `codex/step-5-artifact-integrity`; no history rewrite or pilot replacement.
- Clean checkout; remote fetch confirms these references. No existing issues.
- Existing backend uses SQLite records/events/tasks, isolated serial model workers,
  revision-bound quality/consent/budget gates and verified artifact caches.
- React 19, React Query, Router, Radix, Inter and existing theme/layout tokens stay.
  UI/UX Pro Max is installed and loaded from the user's Codex skills directory.
- GPU observed: RTX 4080 SUPER, 16,376 MiB, driver 616.92. This is inventory,
  not execution qualification. Existing Linux virtual environment is preserved.
- Fresh Windows Python 3.12.14 development environment uses the frozen lock in
  ignored `outputs/engineering-venv`; no change to production/WSL settings.
- Known WSL/native corruption and strict NumPy reproducer remain open. Do not
  retry native failures until green or claim CPU CI repairs hardware.
- Bounded Windows validation also observed strict palette child access violation
  `0xC0000005`; 18 other targeted checks passed after portability fixes. A broader
  local run was stopped immediately on receipt of the native failure. Do not
  infer a safe Windows runtime from earlier passing samples. Evidence stays in
  ignored `outputs/engineering-validation/native-windows-2026-10-12.md`.
- No private uploads, paid generation, system changes, destructive resets or
  extended stress tests. Fast/Combined generation stays blocked.

## Execution packages and order

1. **Baseline acceptance (G0):** independent review of PR #3, exact-head CI,
   preservation/privacy checks, separate code-integrity acceptance from hardware.
2. **Observability (G1/G2):** inventory actual worker/device/transfer seams;
   introduce a small validated frame description and structured measured stage
   statistics. Add durable local operation/run/phase snapshots, bounded events,
   interruption/recovery and a shared Studio progress view. Start with existing
   reliable frame counters; SAM positions require separate traversal accounting.
3. **Reference and intent (G7/G8):** local explainable image checks, immutable
   character/image bindings, deterministic typed plans, explicit unsupported
   decisions and auditable provider payload mapping. No model output dispatch.
4. **Processing (G3/G4/G5/G6):** inspect pinned model implementations and actual
   FFmpeg capabilities. Ship accelerated paths only after parity and equivalent
   workload timing/memory evidence; otherwise keep experimental paths disabled.
   Hardware codecs are separate from CUDA tensors. Preserve atomic artifacts.
5. **Preparation and review (G9/G10):** conservative source evidence and mapping
   questions, existing serial preparation and full audit, task projection with
   every original finding and exact report/revision binding retained.
6. **Studio and qualification (G11/G12):** compose existing controls into Simple
   and Advanced views over one job. Test themes/mobile/keyboard and recovery;
   qualify real media/GPU/provider paths separately from synthetic correctness.

G2 may precede GPU changes: truthful progress is independently testable and
addresses the existing silent work. G7/G8 can proceed without GPU qualification.
Parallel delegation is limited to independent read-only reviews with fixed heads.

## Merge and evidence policy

Each coherent slice gets focused tests, diff/privacy review, one PR, exact-head
CI and ordinary merge. Fetch main after merge and verify ancestry. Preserve
unexplained relevant failures; classify hardware/model/provider limits without
marking unfinished deliverables complete. No numerical speedup claims without
equivalent measured inputs and outputs. UI changes compare original/new screens
and representative empty/loading/error/blocked/success states. Consult UI/UX Pro
Max for targeted interaction/accessibility guidance, retaining existing identity.

Use measured counters with explicit scope/unit, unknown totals and ETA where
unknown. Cache hits are verified reuse, not throughput samples. Keep elapsed,
waiting and artifact publication separate. Historical ETA requires matching
qualified profiles; it must never be a guessed percentage or approval signal.

Finish with a release report only when mandatory implementation is complete or
remaining work has an evidence-based owner/external blocker. The handoff records
partial work honestly; stopping a session is not program completion.
