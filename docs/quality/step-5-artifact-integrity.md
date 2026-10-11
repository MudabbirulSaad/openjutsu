# Step 5 — Artifact integrity and runtime stability

**Artifact safeguards implemented; overall stability acceptance is not met.** The native
NumPy failure remains reproducible and unisolated. Review this as a draft change, not a
claim that the workstation or numerical runtime has been repaired. Do not proceed to
Simple Mode/progress implementation or cloud qualification on this evidence.

Base: `01e03bc39de32fc0f57bbbadd2a77052cf7cb71c` (merged Step 4.5), branch
`codex/step-5-artifact-integrity`. The [post-merge main CI run](https://github.com/MudabbirulSaad/openjutsu/actions/runs/38173362369)
passed before production edits. Local main was fast-forwarded to that exact SHA with a clean
tree. All original Step 1–4 commits remain ancestors. No established commit was rewritten.

## Findings and independent reproductions

### Numerical depth: confirmed bad saved bytes, unknown original corruption cause

The preserved 517,432,224-byte numerical-depth NPZ fails complete ZIP readback twice in a
read-only loop: `BadZipFile: Bad CRC-32 for file 'depths.npy'`. Independent `unzip -t` reports
computed CRC `fa2ca546` versus stored CRC `0ed747d6`. SHA256 before/after reading is identical.
This establishes that the saved archive is inconsistent; it does not establish which original
write, compression, memory, storage or runtime operation introduced the inconsistent bytes.
The file is retained unchanged as a negative control, not repaired by rewriting its CRC.

Confirmed application defects were independently reproduced at `Engine.run_stage`:

- A worker could return a CRC-bad NPZ, and the Engine would hash it and publish its manifest.
- An already-bad NPZ whose hash matched its manifest was accepted on cache reuse/restart.
- A truncated JSON manifest aborted reuse instead of safely regenerating into a new attempt.
- Cancellation arriving after worker completion could still publish a receipt.

Before the fix, these four regression tests failed; the valid-legacy-cache control passed.
After the fix, the same assertions pass. This is the exact integrity defect corrected here:
**a hash identifies bytes; it does not establish that those bytes are a usable numerical
artifact**. The historical cause of the original bad compressed bytes remains unknown.

The old depth worker called `np.savez_compressed` directly on the final filename. The Engine
accepted file existence and hashes, wrote its final JSON receipt directly, and validated
readability only later in the Step 4 quality audit. Interruption could therefore leave partial
files/receipts, and a completed-but-corrupt archive could be recorded as a cache hit. Mask NPY
writes already used replacement/fsync, but had a fixed temporary name and no complete readback.

### Fixture CRC/readback: previous failure retained, not reproduced in the isolated loop

The preserved Step 3 six-member fixture has SHA256
`7ba1fc43345b9356c5981da6598a7524895135ed2185750f6c6693e63526c4e8`.
Five consecutive standalone reads checked every ZIP member/CRC, loaded every array and verified
finite values. All passed; before/after file hashes match. Each complete iteration took
approximately 4.0–5.4 seconds in this run. Existing private suites also read this fixture with
its original metadata and expected values.

The earlier `previous_masks.npy` CRC error and its original integration logs remain preserved.
No new CRC error was observed for that fixture in the repeated Step 5 private suites. This
does not prove the earlier error was fictitious or repaired. Its historical/transient cause
is unresolved and is not assumed to be the numerical-depth or NumPy-abort cause.

The candidate tool already compared all saved members with expected arrays after a direct
write. The new producer publishes only after that check succeeds, uses unique sibling temporary
files and atomically publishes fixture metadata. The Step 1 fixture producer now also performs
complete readback before publication. The private test loader verifies every member before
materializing arrays. Existing fixtures were never regenerated or overwritten.

### Native NumPy abort: reproduced and narrowed, not fixed

The public baseline suite aborted in `worker.py` palette indexing, reproducing the previously
recorded symptom. Isolated worker cases passed; full-suite debugger runs also passed. A new
subprocess test then reproduced allocator corruption using ordinary NumPy arrays and the same
palette-gather operation, without SAM, Torch, private fixtures, network activity or GPU inference.

Observed errors include `munmap_chunk(): invalid pointer`, `double free or corruption (out)`,
SIGABRT, SIGSEGV and inconsistent array shapes. GDB caught SIGABRT through libc free and NumPy
`array_dealloc`. This identifies a memory-corruption symptom/deallocation site, not the original
invalid write or a proved NumPy C-source defect.

Controlled probes:

| Probe                                                  | Actual result / interpretation                                                                                                                         |
| ------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Original API NumPy 2.5.4, Python 3.12.3                | Native failures reproduced; other identical/reduced runs passed.                                                                                       |
| Fresh frozen dependencies, only NumPy changed to 2.2.6 | Longer loop failed with inconsistent shapes. A version downgrade is not supported as a fix.                                                            |
| Existing CUDA environment NumPy 2.2.6                  | Short loop and 37 focused tests passed; this does not certify the longer stress case.                                                                  |
| Fresh Python 3.12.14 / NumPy 2.5.4 in WSL              | Segfault reproduced. Upgrading the Python patch version is not a demonstrated fix.                                                                     |
| Diagnostic AVX2/FMA3 disabling                         | Segfault still reproduced; no CPU-feature override was adopted.                                                                                        |
| Per-process virtual-CPU affinity, 1,000 iterations     | CPU 0 passed; 4/8/12/20/24/27 aborted; 16 reported inconsistent shapes. One run per CPU; no production affinity change and no physical-core diagnosis. |
| Valgrind, five iterations                              | Zero reported memory errors. Its changed execution/allocator behaviour and short run do not clear the fault.                                           |
| NumPy-free stdlib zlib/ZIP roundtrips                  | Twenty 16 MiB synthetic byte roundtrips passed. No inference that all compression/storage is sound.                                                    |
| Bundled Windows Python 3.12.14 / NumPy 2.3.5           | One 1,000-iteration loop passed. OS/build/version all differ; this is not a controlled proof of a WSL-only defect.                                     |

The host reports an i9-14900K; Windows has an earlier corrected hardware warning. Neither fact
proves the current errors are caused by hardware. BIOS/microcode and CPU/RAM profile were not
changed. Owner context was requested. A host/WSL/allocator/native-library investigation remains
necessary before claiming a root cause. [Intel's official instability discussion](https://community.intel.com/t5/Mobile-and-Desktop-Processors/Intel-Core-13th-and-14th-Gen-Desktop-Instability-Root-Cause/td-p/1633442)
is relevant background, not a diagnosis of this machine.

No dependency pin, palette workaround, silent retry, test skip or relaxed assertion was used
to hide this failure. The strict subprocess test remains in the public suite. Failure logs and
all standalone probes remain local in the ignored diagnostic directory.

## Implementation and file lifecycle

### Verified persistence

[artifacts.py](../../backend/openjutsu/artifacts.py) supplies the shared persistence boundary:

1. Create a unique sibling temporary with `mkstemp` on the destination filesystem.
2. Serialize numeric arrays or JSON, close compression, flush and fsync the file.
3. Reopen and completely validate before changing the published filename.
4. Replace atomically; fsync the directory where supported.
5. If any operation fails, retain the temporary for diagnosis and leave a previous destination
   intact. A leftover `.pending-*` file is never an artifact or cache receipt.

`verify_npz` reads each ZIP member through CRC using its actual member entry, rejects duplicate/
invalid/empty member sets, and reads every array with pickles disabled. It checks numeric types,
finite values and, on producer readback, exact array names/shapes/dtypes/values. `verify_depth`
requires three-dimensional floating data and matching frame/spatial dimensions. `verify_npy`
fully traverses numeric values, checks payload length and exact producer readback. Finite-value
checks use bounded chunks; NPZ materialization still requires memory for a full array.

JSON is serialized with non-finite values prohibited and verified by exact bytes plus parsed
serialized representation. An intermediate GPU run exposed that tuples in model stamps become
JSON lists; canonical serialized-form comparison fixes that new implementation error and a
regression test covers it. It is unrelated to the historical CRC/abort root causes.

This follows the existing [NumPy file API](https://numpy.org/doc/stable/reference/generated/numpy.load.html)
and [Python replacement/fsync API](https://docs.python.org/3.12/library/os.html#os.replace).
Atomic replacement requires a sibling on the same filesystem. Windows directory fsync is not
exposed by this helper; unsupported POSIX directory fsync is recorded as a platform limitation,
not a universal guarantee against power loss or unstable hardware.

### Cache publication and restart

[engine.py](../../backend/openjutsu/engine.py) `Engine._run_stage` retains the existing cache key
and model/input fingerprints. Each new attempt writes into `cache/<key>/runs/<uuid>` rather
than overwriting a previous run. Rejected manifest bytes and old output files remain available.

Before a cache hit or publication, `verify_outputs` checks required stage artifacts, internal
cache paths, complete numerical readability/schema, JSON readability, video/audio decode,
frame counts and relevant dimensions. Hashes are checked before and after verification. New
worker files are fsynced before the final receipt is atomically published. Cancellation is
checked again before publication/reuse. The receipt records `integrity_version` and validation
descriptors; progress or process exit alone never establishes a valid cache.

Malformed receipts and missing/changed/unreadable artifacts cause regeneration into a new run,
not in-place replacement of evidence. A run without a committed valid receipt is not adopted
after restart. Valid legacy receipts without the new descriptors remain reusable after full
verification; valid compressed/uncompressed NPZ and existing NPY masks remain supported.

The Step 4 quality audit independently checks numerical readability again. Its appearance,
subject identity, coverage thresholds and approval rules are retained, including the existing
Fast/Combined cloud-approval block. No Simple Mode or progress schema was implemented.

## Changed files

| File                                                                       | Purpose                                                                                                                                                                   |
| -------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [artifacts.py](../../backend/openjutsu/artifacts.py)                       | Atomic verified numeric/JSON persistence, complete format checks and completed-file flush.                                                                                |
| [engine.py](../../backend/openjutsu/engine.py)                             | Verified cache hits/publication, unique attempt directories, preserved rejected receipts, final cancellation check.                                                       |
| [worker.py](../../backend/openjutsu/worker.py)                             | Depth uses the verified compressed-NPZ writer; inference and palette math unchanged.                                                                                      |
| [tracking.py](../../backend/openjutsu/tracking.py)                         | Existing NPY mask persistence uses unique temporaries and exact complete readback; tracking semantics unchanged.                                                          |
| [quality_runtime.py](../../backend/openjutsu/quality_runtime.py)           | Reuse depth validator and fail closed on EOF/zlib errors; retain independent quality audit.                                                                               |
| [reproduce_pilot.py](../../scripts/reproduce_pilot.py)                     | Verified Step 1 archive plus atomic fixture metadata for future fixture creation.                                                                                         |
| [segment_pilot_candidate.py](../../scripts/segment_pilot_candidate.py)     | Verified candidate archive and atomic metadata; existing readback seam preserved.                                                                                         |
| [conftest.py](../../tests/conftest.py)                                     | Complete private-fixture validation before loading arrays; no opt-in boundary changed.                                                                                    |
| [test_artifact_integrity.py](../../tests/test_artifact_integrity.py)       | Real Engine cache/publication seam, including matching-hash bad CRC, restart, truncated receipt, cancellation and legacy reuse.                                           |
| [test_numerical_persistence.py](../../tests/test_numerical_persistence.py) | Numeric/JSON roundtrip, all-member corruption, truncation, duplicate members, nonfinite/mismatched data, interrupted process/write/replace, strict native-process stress. |
| This report                                                                | Independent findings, evidence, results and remaining blocker.                                                                                                            |

No frontend, dependency, model-weight, provider, ledger schema or CI configuration change.
New test data is synthetic. Private originals, references, frames, fixtures, failure archives,
checkpoints, runtime databases and detailed logs are excluded from Git.

## Representative GPU replay and readbacks

An authorised local-only replay used the saved 18-second normalized source, copied into a
separate new runtime with zero spending and no credentials. The Engine loops/providers were
not started. VDA Small and existing installed weights produced float32 depth of shape
`(432, 960, 540)` with a 432-frame preview at 24 fps. Complete NPZ member/value validation
passed at writer and cache boundaries, then three more explicit readbacks passed. A new Engine
instance reused the cache with unchanged receipt timestamp. Source bytes remained unchanged.

Measured worker stage: **50.093 seconds**, **11,858 MiB peak PyTorch reserved**. The full harness,
including additional validation/readbacks/readiness/restart, took **80.334 seconds**. These are
this run's observations, not a promised rate or whole-device peak.

Earlier attempts are retained and disclosed: the first newly computed archive failed
decompression with `invalid block type` and was never published; another run reached numerical
verification but hit the tuple/JSON issue corrected above. There was no automatic retry that
concealed either error. One successful replay does not establish that the unresolved local
runtime can no longer corrupt a future write. The application must continue to reject such a
write instead of caching it.

## Commands and actual results

Commands below use the configured Python environment; private fixture paths are intentionally
local, ignored and unavailable in public CI.

```text
python -m pytest tests/test_artifact_integrity.py -q
python -m pytest tests/test_numerical_persistence.py tests/test_artifact_integrity.py
  tests/test_candidate_fixture.py tests/test_quality_approval.py tests/test_recovery.py -q
python -m pytest tests -q
python -m pytest tests -q --pilot-fixture outputs/step-1-baseline/fixture-verified
  --candidate-fixture outputs/step-2-candidate/final-reviewed/fixture
  --tracking-fixture outputs/step-3-candidate/final-reviewed-v2/fixture
  --quality-fixture outputs/step-4-candidate
python -m ruff check backend tests scripts
python -m ruff format --check backend tests scripts
pnpm --dir web test
pnpm --dir web build
pnpm --dir web test:e2e
python scripts/check_public_tree.py
python scripts/check_public_tree.py --staged
python scripts/preserve_pilot.py verify outputs/step-4-preservation/preservation.json
git diff --check
```

- Before implementation, Engine integrity contracts: **4 failed, 1 passed**. After the fix,
  those same five tests passed. An additional failed-run/restart regression was added later.
- Focused integrity/quality/recovery suite: **37 passed** in the API and CUDA environments
  before the tuple regression; after that addition, **38 passed** in 22.69 seconds. Other
  focused runs failed the native subprocess assertion; those failures remain disclosed.
- Public full-suite repeats at that revision: **119 passed /88 private-fixture skips /5 strict
  expected failures** in two runs; the third had **1 unexpected native-test failure /118 passed
  /88 skips /5 expected failures**. These counts predate the final additional restart test.
- Full private repeats: **202 passed /10 strict expected failures /0 skips** in two runs;
  another had **1 unexpected native-test failure /201 passed /10 expected failures /0 skips**.
  All fixture and Steps 1–4 checks passed in those runs. A final complete run is recorded in
  the PR/handover rather than replacing this failure history: **203 passed /10 strict expected
  failures /0 skips** in 67.29 seconds, including the final additional restart test.
- The latest two-file integrity run had **18 passed, 1 unexpected native-test failure**.
  The native assertion remains strict; it was neither skipped nor marked expected.
- Ruff lint/format, frontend **4 tests**, TypeScript/Vite build, and browser/accessibility
  **6 tests** passed. Browser screenshots were restored to their original bytes; no UI changes
  were retained. Private validation is not asserted passed merely because CI is green.
- Original preservation: **all 1,353 file hashes and 119 records unchanged; revision 3
  preserved**. This includes originals and previous candidates, not just a new runtime copy.
- Public-tree/staged/history privacy and whitespace checks are part of publication validation;
  exact publication head/check status is recorded in the PR and handover.

All failed logs are retained alongside successful runs under the ignored
`outputs/step-5-integrity` directory. No test skip, weaker assertion, reconstructed fixture or
archive-CRC rewrite was used to obtain a passing result.

## Acceptance and remaining work

| Requirement                                        | Assessment                                                                        |
| -------------------------------------------------- | --------------------------------------------------------------------------------- |
| Published new depth outputs pass complete readback | Demonstrated on the 432-frame replay; unsuccessful temporaries are not published. |
| Corrupted/partial archives rejected                | Reproduced negative controls and regression tests pass.                           |
| Receipt committed only after artifact verification | Implemented and tested; interrupted/missing-receipt runs are not reused.          |
| Valid existing artifacts remain readable/reusable  | Legacy cache control and unchanged private fixtures pass.                         |
| Repeated relevant tests all pass                   | **Not met: intermittent native subprocess failures remain.**                      |
| Original preservation hashes unchanged             | Passed: 1,353 files and 119 records.                                              |
| No private media/checkpoints/credentials committed | Publication privacy checks; synthetic test code only.                             |
| No provider requests, uploads or paid generation   | No live provider activity; local GPU/CPU work only.                               |

Do not claim that atomic writes repair native memory corruption, a bad CPU/RAM configuration,
WSL faults or previously corrupted bytes. Full verification now prevents known unusable outputs
from being labelled valid, but does not certify computational correctness on an unstable host.

**Recommendation: keep the PR draft and withhold Step 5 approval.** Establish a reliable native
runtime/host baseline using the retained minimal probes, investigate the actual invalid write
or host fault, then rerun strict suites and local GPU readback without the intermittent failures.
No BIOS/voltage/RAM/WSL settings were altered; those actions require a separate informed decision.
The original fixture-readback cause also remains uncertain, independently of the other issues.
Step 6 and the accepted Simple Mode/progress architecture have not begun.
