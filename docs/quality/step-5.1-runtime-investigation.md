# Step 5.1 — Native runtime instability investigation

**Step 5 acceptance remains blocked. Classification E: root cause still unknown.**
OpenJutsu is not required to trigger the failure. Host CPU/firmware instability (D)
is a material concern; a WSL/runtime interaction (C) and a shared native dependency
defect (B) remain possible. No faulty application write or safe software correction
has been established. Under the earlier Step 5.1 scope, the recommendation was to
keep [PR #3](https://github.com/MudabbirulSaad/openjutsu/pull/3) draft and unmerged.
The later engineering assignment separates code-integrity acceptance from runtime
qualification; the native fault and all investigation results below remain open.

Investigation date: 12 October 2026, Australia/Sydney. Base branch:
`codex/step-5-artifact-integrity`; base commit:
`8516b4df8136cde774d83d9758bcde7409b31ef2`. The working tree was clean at entry.
The PR was checked at entry and after testing: OPEN, draft, same remote SHA,
no auto-merge request. No production code, dependency pin, test assertion, skip,
provider integration, BIOS setting, firmware, Windows setting or WSL setting was
changed. New environments contain diagnostic packages in an ignored directory;
existing Python environments were not modified.

## System inventory and observability

| Item | Read-only finding |
| --- | --- |
| CPU | Intel Core i9-14900K, family 6/model 183/stepping 1. Windows CIM reports 24 cores/32 logical processors. |
| Physical model topology | Intel specifies 8 performance cores and 16 efficient cores. This is the model specification, not a measured mapping of WSL CPUs. |
| Motherboard | ASUSTeK COMPUTER INC., PRIME Z790-A WIFI, Rev 1.xx. |
| BIOS | American Megatrends, 1805. SMBIOS build date 2024-10-30; ASUS publication date 2024-11-04. These are different date fields. |
| Microcode | Windows processor-0 registry `Update Revision` and `Previous Update Revision`: bytes `2b 01 00 00`, little-endian `0x12B`. Other logical-processor registry entries report zero and do not establish per-core revisions. WSL reports `0xffffffff`, which is not a reliable host microcode reading. No privileged MSR reader was installed. |
| RAM | Two Team Group UD5-6000 modules, 32 GiB each; 64 GiB total. SMBIOS reports configured speed 4800 MT/s. This does not prove active XMP or memory timings. |
| CPU configuration | CIM reports external clock 100 MHz and clock fields 3200 MHz. These are inventory fields, not trustworthy live turbo/voltage measurements. Active overclock, undervolt, ASUS performance preference, Intel Default Settings and XMP are **unknown**. |
| Windows | Windows 11 Pro for Workstations, DisplayVersion 26H2, build 26300.9550. |
| WSL | 2.6.3.0; running kernel `6.6.87.2-microsoft-standard-WSL2`; WSLg 1.0.71. |
| Ubuntu | 24.04.3 LTS; glibc 2.39 (`2.39-0ubuntu8.9`). |
| WSL resources | Configuration specifies 28 processors, 48 GB memory, 8 GB swap. Linux sees 28 virtual CPUs/14 virtual cores/2 threads per core; the sampled runtime reports about 48 GiB RAM and zero active swap. Configuration and active state are distinct. |
| Installed tuning tools | HWiNFO64 8.34 and Armoury Crate Service 6.5.14.0; Armoury Crate and ASUS Fan Control services running. No Intel XTU/AI Suite/CPU-Z/ThrottleStop match in the inspected machine uninstall registry. Absence from that registry is not proof that portable tools or tuning are absent. |
| Settings inspection limit | No running HWiNFO instance or saved hardware report was observed. Its installed manual documents automated report export as a Pro feature; licence status was not established. The available CIM/registry inventory does not expose authoritative active ASUS setup settings. No GUI, sensor driver installation, reboot or firmware-variable write was attempted. |

The model topology is documented in [Intel's i9-14900K specifications](https://www.intel.com/content/www/us/en/products/sku/236773/intel-core-i9-processor-14900k-36m-cache-up-to-6-00-ghz/specifications.html).
In particular, WSL virtual CPU 0, 12 or 27 cannot be called a particular physical
performance/efficiency core from this inventory.

### Firmware guidance check

**Installed firmware does not meet Intel's 0x12F-or-later guidance.** ASUS lists
0x12B for BIOS 1802, a settings-string change for installed 1805, and an explicit
0x12F update for BIOS 1820 dated 2025-05-21. The observed Windows microcode record
agrees with 0x12B. ASUS currently lists non-beta 1836 dated 2026-05-08 with a
microcode update; its release note does not state the exact revision. Beta 1840
was also listed. No firmware was downloaded or flashed. [ASUS BIOS release notes](https://www.asus.com/us/supportonly/prime%20z790-a%20wifi/helpdesk_bios/)

Intel recommends Intel Default Settings and a BIOS containing 0x12F or later.
That establishes a configuration gap, **not proof that this CPU has Vmin shift,
is permanently damaged, or caused these crashes**. [Intel's current guidance](https://www.intel.com/content/www/us/en/support/articles/000102331/processors.html)

## Python, NumPy and native libraries

| Environment | Python/build | NumPy | Native library/build observations |
| --- | --- | --- | --- |
| Existing WSL API | 3.12.3, Ubuntu GCC 13.3.0 | 2.5.4 | manylinux cp312 wheel, GCC 14.2.1/Cython 3.3.0; OpenBLAS 0.3.34.106.0. |
| Existing WSL ML | 3.12.3, same Ubuntu interpreter | 2.2.6 | manylinux cp312 wheel; OpenBLAS 0.3.29, pthreads, observed 28 threads. |
| Fresh isolated Linux | 3.12.14, uv-managed Clang 22.1.3 build | 2.2.6, 2.3.5, 2.5.4 separately | New venvs containing only NumPy, not OpenJutsu. Same WSL guest/kernel/glibc. |
| Fresh isolated Windows | 3.12.14, MSC 1944 AMD64 | 2.2.6, 2.3.5, 2.5.4 separately | New venvs containing only NumPy; cp312 win_amd64 wheels. No application imports. |
| Existing bundled Windows control inventory | 3.12.14, MSC 1944 AMD64 | 2.3.5 | OpenBLAS 0.3.30. This inventory was not used for the fresh Windows matrix. |

Linux `ldd` identifies the NumPy extension, bundled scipy-OpenBLAS, libstdc++,
libgcc, glibc, libm, pthreads, gfortran, quadmath and zlib. Full `np.show_config()`,
`np.show_runtime()`, wheel tags, compiler settings, executable paths and relevant
environment variables are saved privately. Standard trials had no observed
`NPY_*`, `OPENBLAS_*`, `OMP_*`, `MKL_*` or allocator overrides.

NumPy's installed `RECORD` checksums matched every hashed entry in the existing
Linux API/ML and fresh Linux/Windows environments. Existing bundled Windows
2.3.5 differed for 22 native/executable entries, including the main extension.
The main extension has a valid OpenAI Authenticode signature. Signing is a
plausible explanation for changed binaries; the mismatches do not establish
corruption. Fresh official wheels avoid this ambiguity. `RECORD` matching is an
installation-consistency check, not a proof of runtime correctness or hardware
health. No native wheel was rebuilt with debug/sanitizer instrumentation.

## Controlled reproduction

The unchanged retained test is
[`test_numpy_palette_path_in_fresh_processes`](../../tests/test_numerical_persistence.py).
Each invocation launches up to three fresh processes, each with 100 iterations;
it stops at the first failed child. All three invocations failed, with child
results SIGSEGV, SIGABRT (`double free or corruption`), SIGSEGV respectively.

The new [independent reproducer](../../scripts/reproduce_numpy_palette.py) imports
only standard-library modules and NumPy. It runs with Python `-I` and no
`PYTHONPATH`, uses the same literal palette, seed 5, uint8 label volume
`(261,96,54)`, 100 iterations, exact output shape `(261,96,54,3)` and the same
boolean-selection equality assertion. Each standard matrix case has five fresh
process trials, a 30-second limit per process, and independent recorded outcomes.
Passing trials are not retries that erase failures. Trials ran sequentially;
there was no overnight or prolonged hardware stress test.

| Runtime | NumPy | Passes / 5 | Failed outcomes |
| --- | --- | --- | --- |
| Existing WSL API, Python 3.12.3 | 2.5.4 | 4 | 1 SIGABRT, double-free/corruption. |
| Existing WSL ML, Python 3.12.3 | 2.2.6 | 4 | 1 inconsistent-shapes exception. |
| Fresh Linux, Python 3.12.14 | 2.5.4 | 1 | 2 SIGABRT, 1 SIGILL, 1 inconsistent-shapes exception. |
| Fresh Linux, Python 3.12.14 | 2.2.6 | 3 | 1 inconsistent-shapes exception, 1 axis-remapping/dimensionality exception. |
| Fresh Linux, Python 3.12.14 | 2.3.5 | 2 | 1 SIGSEGV, 2 SIGABRT. |
| Fresh Windows, Python 3.12.14 | 2.5.4 | 5 | None observed. |
| Fresh Windows, Python 3.12.14 | 2.2.6 | 5 | None observed. |
| Fresh Windows, Python 3.12.14 | 2.3.5 | 5 | None observed. |

Thus 11/25 standard WSL trials failed versus 0/15 fresh Windows trials. These are
small, time-separated samples, not population failure rates. Windows uses
different native binaries/compiler/allocator and host scheduling. A fresh venv
is **not** a fresh Linux kernel, bare-metal Linux installation or different
physical machine. No such platform control was available within this stage.
There is no claim that Windows is a validated alternative production runtime.

### Minimisation, lifetimes and affinity

- API NumPy 2.5.4 gather-only: 5/5 passed at 100 iterations. These trials retain
  only one small palette result at a time, so allocation pressure differs.
- Stack-only, without the boolean indexing/equality assertion: 4/5 passed,
  1 SIGSEGV. The boolean assertion is therefore not necessary for failure.
- The constant palette/label shapes do not legitimately change. Inconsistent
  shape/dimensionality errors become observable during array construction or
  stacking, before normal process teardown. This does not locate the first bad
  write or prove which prior allocation/deallocation caused corruption.
- Keeping references longer, changing the allocator or avoiding stack would
  change the experiment; none was installed as an application fix.
- A separate bounded affinity experiment used the same 100-iteration workload,
  `OPENBLAS_NUM_THREADS=1` for **every** condition, and three trials each.
  Unbound: 0/3 pass; virtual CPU 0: 1/3; CPU 12: 0/3; CPU 27: 1/3. Failures
  included allocator aborts and a shape exception. No tested affinity removes
  the failure. Prior Step 5's single CPU-0 success is not a reliable workaround.
  Samples are too small and virtual topology too indirect to diagnose a bad
  physical core. No production affinity or thread setting was changed.
- The workload contains no matrix multiplication/BLAS operation. OpenBLAS is
  nevertheless loaded by NumPy; restricting its threads did not eliminate
  failures. That does not rule out every native-library interaction.

`main` and Step 5 have identical `MASK_COLORS` and unchanged worker palette
conversion logic. Step 5 changes persistence around those operations, not the
palette operation itself. The independent reproducer needs neither revision;
an original-main checkout would add no application control to that experiment.
No original-main runtime or preserved artifacts were overwritten to compare it.

## Allocator, debugger and event evidence

The WSL crash collector produced ELF cores in the Windows temporary
`wsl-crashes` folder despite `/wsl-capture-crash` being absent from the Ubuntu
filesystem. Its pipe is configured in `core_pattern`. It was not reconfigured.

Three captured core analyses establish:

1. SIGABRT: glibc `malloc_printerr` → `munmap_chunk` → `__libc_free` → NumPy
   `array_dealloc` → Python evaluation. This is the **detection** site, not the
   first corrupting write.
2. SIGSEGV: the recovered pre-faulthandler frame is in NumPy's
   `raw_array_wheremasked_assign_array` while stacking.
3. SIGILL: the recovered instruction pointer appears inside padding immediately
   before `PyArray_AssignArray`; another core appears inside a conditional-jump
   instruction. These suggest abnormal control flow, not a demonstrated lack
   of a supported SIMD instruction. Symbol stripping, unwind accuracy and GDB's
   executable/core-match warning limit interpretation. The reports cannot prove
   a CPU bit flip, bad return address or NumPy source defect.

Three live GDB 100-iteration trials exited normally. GDB's command return was 1
because subsequent stack/register commands ran after normal exit, not because
the inferior crashed. Debugger scheduling/address-layout differences and the
small sample prevent a stability claim.

Valgrind 3.22.0 ran two shorter, ten-iteration trials with unchanged assertions:
one passed and one SIGSEGV after the first reported iteration. Both summaries
said zero detected memory-access errors. The crashing process did **not** pass;
the zero-error summary neither exonerates hardware nor proves an allocator bug.
No origin of corruption was identified. The Step 5 short Valgrind pass also
remains only a bounded observation.

### Windows hardware events

- 2026-10-01 11:41:07 UTC: WHEA event 2, corrected severity. CPER has a generic
  processor section with valid bits `0x217f`, error type 1 (cache), operation 3
  (instruction execution), level 0. Its platform-memory section has valid bits
  **zero**; it cannot identify a RAM fault, address, DIMM or ECC event. Other
  vendor sections were retained but not fully decoded.
- 2026-10-09 21:30:27 UTC: informational WHEA event 3, nonstandard section;
  no CPU/RAM conclusion drawn.
- The same period has Windows bugcheck event 1001 (`0xA`) and an unexpected
  restart event 41. The existing Windows minidump was not analysed; a driver
  defect is one possible explanation, and a bugcheck is not proof of CPU damage.
- The recorded WHEA query found **zero new events** from 2026-10-11 21:55 UTC
  through its 22:12:43 UTC query. There is no contemporaneous WHEA correlation
  established for the new trial failures. Absence does not prove hardware health.

CPER section type/severity and valid-bit interpretation follow the
[UEFI CPER specification](https://uefi.org/specs/UEFI/2.11/Apx_N_Common_Platform_Error_Record.html),
[Microsoft processor section documentation](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/ntddk/ns-ntddk-_whea_processor_generic_error_section)
and [Microsoft memory section documentation](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/ntddk/ns-ntddk-_whea_memory_error_section).
No physical CPU identity was inferred from WSL CPU numbers.

### Linux kernel evidence

Saved dmesg contains user-space Python segmentation/general-protection faults
and repeated `smp_processor_id()`/`__this_cpu_read()` preemption warnings in
memory-cgroup accounting. Warnings also occur for postgres, not only OpenJutsu.
Three existing kernel-panic text records from earlier on 12 October Sydney time
show memory-management paths including `delete_from_swap_cache`, unmapping and
page-cache removal. They are earlier than the new matrix and do not establish
causation. Guest kernel/environment instability is a serious competing
explanation; these messages are not physical machine-check diagnoses.
No kernel, WSL configuration, swap file, memory-reclaim mode or Windows update
was changed to test that hypothesis.

### Evidence retention limitation

The temporary collector folder later contained only ten newer dumps; earlier
analysed cores and the prior Step 5 temporary cores were no longer present.
This is consistent with collector retention, but the deletion mechanism was
not traced. The investigation issued no delete command. Raw dumps should have
been copied before additional trials. Complete captured stdout/stderr,
environment inventories and GDB reports remain, but raw earlier cores cannot
now be re-examined. This is a real preservation limitation, not a passing check.

All ten remaining cores (553,594,880 bytes total) were copied into the ignored
private evidence folder and SHA-256 checked against their originals. Kernel
panic texts were also copied. Future trials must copy each core immediately
before another trial; changing global core settings is not necessary for that.

## Classification and confidence

| Explanation | Supporting evidence | Contradicting evidence / missing proof | Status |
| --- | --- | --- | --- |
| A. Application defect | Real worker palette conversion also aborts. | Isolated NumPy-only processes fail without application imports. Main palette logic is unchanged. No bad application write found. | Not confirmed; high confidence application code is not necessary to trigger this reproducer. Other application defects are not globally excluded. |
| B. Python/NumPy/native dependency | Faults occur in native array construction/deallocation; Linux builds share glibc and NumPy code paths. | Multiple NumPy versions and independently built Python versions fail; verified fresh installations. Windows versions pass only a small sample. No native write defect located. | Possible, unconfirmed. |
| C. WSL-specific environment | Failures in every tested WSL environment; zero in 15 matched-version Windows trials; guest warnings/panics. | No second WSL kernel, independent Linux OS or healthy-host control. Binary and scheduling differences remain. | Material hypothesis, unconfirmed. |
| D. Hardware/firmware instability | Affected CPU family, observed old microcode, valid earlier cache-error record, varied corrupt shapes/signals and a Windows bugcheck. | No contemporaneous WHEA event; Windows sample passes. Active BIOS settings unknown. No component isolation or post-firmware control. | Material concern; moderate confidence it warrants host/vendor investigation, no confidence claim of a diagnosed failed CPU or DIMM. |
| E. Unknown cause or interaction | All observations above remain compatible with more than one mechanism. | No controlled system-level comparison has isolated a cause. | **Selected classification. High confidence that software-only root cause is not established.** |

Do not claim that NPZ CRC damage, fixture CRC failures and native memory errors
share a cause. Persistence validation detects damage; it cannot repair unstable
computation. No CPU affinity, NumPy downgrade, automatic retry, disabled native
test or global exception suppression is proposed as a production correction.

## Regression and artifact validation

| Command/scope | Actual result |
| --- | --- |
| Retained native pytest test, three invocations | 0/3 pass; two child SIGSEGVs and one child SIGABRT. |
| Numerical persistence + artifact integrity tests, run 1 | **18 passed, 1 failed** (strict native test). |
| Same tests, run 2 | **18 passed, 1 failed** (strict native test). |
| Complete public pytest suite | **119 passed, 1 failed, 88 opt-in private skips, 5 existing xfails**, one warning. |
| Complete private suite, run 1 | **Process SIGABRT (-6)** in worker palette conversion during the collision regression; suite did not complete. Do not infer a passed-test count. |
| Complete private suite, run 2 | **202 passed, 1 failed, 10 existing xfails, zero skips**, one warning. Strict native test failed. |
| Ruff lint | Passed for `backend tests scripts`. |
| Ruff formatting | Passed; 50 files formatted. Only the new diagnostic script needed formatting during this stage. |

The warning is an existing Starlette/httpx deprecation. Expected failures were
not changed. No failing case was skipped, relaxed or reclassified. No frontend
changes were made; frontend build/browser tests were not repeated for this
runtime-only diagnostic addition. Relevant synthetic persistence, interruption,
restart and cache-rejection tests passed in both focused runs.

Current complete artifact checks:

- Saved Step 5 GPU-generated depth `(432,960,540)` float32: **3/3 complete ZIP CRC,
  NumPy materialisation, shape/dtype and finite-value readbacks passed**, taking
  5.09, 5.23 and 5.34 seconds. Hash identical before/after.
- Step 3 six-member private fixture: **3/3 complete CRC and numeric readbacks
  passed**. Hash identical before/after. This does not erase its previously
  recorded intermittent readback failures.
- Original bad depth NPZ: **2/2 rejected** with `Bad CRC-32 for depths.npy`.
  SHA-256 remains
  `f1aa83dc851610baa8e2a9764afa849aedd23d427a58537573604e4885e8edc3`.
- No new GPU inference was performed after the failing CPU matrix. Prior Step
  5 has one successful full-depth generation and earlier failed attempts.
  **Repeatable fresh GPU generation is not established** and must be tested
  after runtime stabilisation; three readbacks are not three generations.
- Original preservation manifest: **entry and exit checks passed all 1,353 file
  hashes and 119 records; revision 3 preserved**. All source, masks, references,
  output, original corrupt depth and protected diagnostic files remain intact.
  This protection does not cover the temporary core-retention gap above.

## Reproduction commands and private evidence

Run from the repository root. Substitute the recorded interpreter executable
for `PYTHON`; do not change the application's environment to follow this matrix.

```text
PYTHON -m pytest -q tests/test_numerical_persistence.py::test_numpy_palette_path_in_fresh_processes
PYTHON -I -X faulthandler scripts/reproduce_numpy_palette.py --iterations 100 --mode boolean
PYTHON -I scripts/reproduce_numpy_palette.py --iterations 100 --mode stack
PYTHON -m pytest -q tests/test_numerical_persistence.py tests/test_artifact_integrity.py
PYTHON -m pytest -q tests
PYTHON -m pytest -q tests --pilot-fixture outputs/step-1-baseline/fixture-verified --candidate-fixture outputs/step-2-candidate/final-reviewed/fixture --tracking-fixture outputs/step-3-candidate/final-reviewed-v2/fixture --quality-fixture outputs/step-4-candidate
ruff check backend tests scripts
ruff format --check backend tests scripts
PYTHON scripts/preserve_pilot.py verify outputs/step-4-preservation/preservation.json
```

Private evidence is retained under `outputs/step-5.1-runtime/` and excluded by
Git ignore rules. It includes host/guest inventory, microcode bytes, wheel
checksums/build output, raw/decoded WHEA, kernel logs, per-trial return codes,
stdout/stderr, UTC timestamps, command lines, GDB/Valgrind output, suite logs,
complete readbacks, preservation result and the copied cores/manifest. No secret
values or identifiable media are copied into this public report.

The standard matrix used script SHA-256
`3d06c493771aaa83388b2ab23413e20072cd54d4f4bec282c433d111b79dc87d`;
that exact source is saved privately as `reproducer-used.py`. Subsequent Ruff
formatting changes only a print statement's wrapping, not inputs/assertions.
The per-process `-I` excludes application path/environment injection. Matrix
installation/build inventories and outcomes are distinct from prior Step 5 logs.
An initial shell batch had a quoting error and launched no trials; those
launcher errors are not counted as NumPy failures. One core-manifest attempt
also stopped on an already missing dump; the final preserved manifest covers
the ten available verified copies, not the lost earlier cores.

## Minimal changes and acceptance

Only two public files are added:

- This report: system configuration, reproducible outcomes, competing
  explanations, limitations and approval-dependent next actions.
- `scripts/reproduce_numpy_palette.py`: a small independent, synthetic NumPy
  reproducer with strict assertions and gather/stack/boolean diagnostic modes.

No production patch is justified yet. Existing Step 5 artifact safeguards,
Step 1–4 regressions and Step 4 quality gate are unchanged. Public-tree and
staged privacy checks passed for the two added files; whitespace checks passed.
The preserved base history audit checked nine stage trees, 259 reachable blobs,
106 tracked files and 11 ignore targets, with zero findings. Raw environment
records, packages, dumps and private fixtures remain ignored. Only the report
and synthetic diagnostic script are staged for the local follow-up commit.

| Acceptance requirement | Status |
| --- | --- |
| Strict native reproducer repeatedly passes intended production runtime | **Not met.** |
| No unexplained SIGABRT/SIGSEGV/allocator corruption | **Not met; SIGILL also observed.** |
| Artifact and prior regression suites all pass | **Not met overall.** Artifact checks pass, native failure and an aborted full suite remain. |
| Repeatable local GPU depth generation/readback | Readback verified; fresh-generation repeatability **not established**. |
| No weakened assertions or hidden retries | Met. All trials disclosed; strict native test remains failing. |
| Original protected pilot/diagnostic hashes preserved | Met for all manifest-protected artifacts; temporary raw-core retention has an explicit gap. |
| No cloud processing, paid requests, private uploads or system configuration changes | Met. |

## Recommended safe next steps — require approval before changes

This was the recommendation under the earlier Step 5.1 acceptance scope. The
2026-10-12 engineering assignment now separately authorizes independently validated
software changes and code-integrity acceptance of PR #3, with runtime qualification
explicitly open. It does not authorize any of the system changes below.

There is no evidence-based application patch that repairs this native fault.
The next runtime investigation crosses the system-level
boundary explicitly reserved for approval in the Step 5.1 request:

1. **Read-only BIOS review in an agreed maintenance window.** With the owner
   present, record current ASUS Performance Preferences/Intel Default Settings,
   ASUS MultiCore Enhancement, CPU ratios/voltage offsets/load-line settings,
   XMP profile, memory speed and voltages. Exit without saving. Reboot interrupts
   the current session and must be approved. Do not infer these values from
   CIM clock fields or an XMP-capable DIMM label.
2. **Review firmware with ASUS/system vendor.** BIOS 1820 explicitly contains
   0x12F; use the vendor's appropriate current non-beta release rather than
   assuming every later version's exact payload from its number. Confirm the
   exact board, supported CPU, release notes and ME implications before choosing
   an update. Record existing settings and ensure the owner has recovery access.
   ASUS notes ME updates can persist across BIOS rollback. Do not flash, reset
   defaults, change voltage or enable/disable XMP without specific approval.
3. **If approved, apply vendor-guided firmware/Intel Default Settings, then
   inventory again.** Verify loaded microcode 0x12F-or-later and actual settings.
   Treat the result as a controlled configuration change, not proof of repair.
   Do not add an undervolt/overvolt or arbitrary power workaround. Record each
   change so multiple changed variables do not produce a false causal claim.
4. **Analyse the existing Windows 0xA minidump read-only.** Determine whether it
   identifies a driver, CPU or another path; obtain permission before installing
   debugging tools. Ask ASUS/Intel for hardware guidance if corrected processor
   errors or failures persist. No component replacement diagnosis is made here.
5. **Repeat the same bounded matrix after the approved change.** Five fresh
   processes per platform/version, seed 5 and 100 iterations; three strict pytest
   invocations; all outcomes retained. Preserve each core immediately. If needed,
   separately approve a WSL/kernel comparison or an independent bare-metal Linux
   control. Do not silently update WSL or reboot into another OS.
6. **Only after native runtime stability is demonstrated**, repeat full private
   regressions and at least two new full 432-frame GPU depth generations in
   separate private roots, each with three complete readbacks and restart/cache
   validation. Any native crash, unexpected shape or corrupt write keeps
   acceptance blocked. No automatic retries or failing-test removal.

Hardware/firmware review and any system changes are deferred for owner approval.
No progress architecture, Simple Mode, Step 6 work, PR push or merge is part of
this investigation.
