# Validation and remaining qualifications

Validation was run locally on 2026-10-11, Ubuntu WSL2/Python 3.12, RTX 4080 SUPER 16 GB, with Torch 2.8/CUDA 12.8. WSL was configured with a 48 GB memory limit on a 64 GB host. Media, detailed reports and frames remain outside Git. Public screenshots use two synthetic subjects and a generated tone.

| Capability | Evidence | Limit |
|---|---|---|
| Job ledger, revisions, spending, ambiguity, restart and cache | Automated backend tests in both CPU-only and CUDA environments | SQLite is for a single local application, not a multi-user service |
| Import, trimming, rotation, CFR/frame indexing and audio export | FFmpeg synthetic integration tests | Original variable timestamps are resampled; normalized pixels are the review authority |
| Guided studio and export | Chromium against actual API with synthetic provider completion; both themes, mobile, stale drafts and reconnection | Synthetic completion tests do not contact a provider |
| Accessibility | Axe checks and keyboard/numeric annotation alternatives | Does not replace assistive-technology user testing |
| Advanced | Four-second local clip: 96 aligned frames at 960×540; VDA Small, SAM 2.1 Large, vocals, pitch, conditioning and Whisper | One subject smoke test; crossing, occlusion, hair/hands and long-clip quality require broader evaluation |
| Fast / Combined | Four-second continuous frontal crop: 96 aligned frames, landmarks/blendshapes/matrices and audio | Single subject; profile shots and cuts produced explicit tracking-gap failures |
| Prompt assistance | Qwen3-VL ordered-frame local smoke test, peak 8,686 MiB reserved | Suggestions need editing; motion is inferred from sampled frames |
| Local upscale | SeedVR2 3B FP8, CPU offload/tiled VAE, 24 frames → 1920×1080; no frame loss | Short local footage; generation fidelity and long clips need review |
| Explicit fallback | Real-ESRGAN 24 frames → 1080×1080; no frame loss | Frame-based; temporal drift must be reviewed |
| Provider adapters | Synthetic contracts plus one live ArgoLink multi-reference request, downloaded result and reconciled dashboard charge | Other routes and native continuation remain unqualified; one result does not establish quality eligibility |
| Native HD | Saved-draft/account orchestration and contract checks | Live native continuation and quality unqualified |
| SAM 3 | Optional adapter only | Gated weights unavailable; not locally tested or enabled by default |

Local stage timings are cold subprocess timings, not a promised processing rate. The Advanced smoke run reused earlier completed audio stages while recovering from dependency errors; its 42-second completion is not a full cold-start benchmark. Individual measured stages included VDA Small 14.84s / 11,858 MiB peak reserved, SAM 2.1 Large 10.95s / 2,100 MiB, Demucs 2.99s / 828 MiB, and Whisper 9.49s / 5,248 MiB. Process startup, import and disk time vary. MediaPipe executes its inference on CPU in this WSL integration while remaining serialized with the model pipeline.

A later complete cold preparation in the actual application runtime took 50.07s for the four-second source interval and produced 96 aligned frames. It is available locally for review with zero spending and no provider credentials. The full 21:46 recording also has an ignored transcript package based on two CUDA Whisper passes; low-confidence passages remain marked for listening review.

Fast completed in 26.03s on a suitable frontal crop; Combined added 33.07s while reusing unaffected audio/transcription. SeedVR2's one-second 16:9 test at temporal batch 5 took 151.20s with 6,766 MiB peak reserved. Square-output batches 5, 9 and 13 were also measured; their GPU reservation peaks were 6,662, 8,786 and 8,928 MiB respectively. These are PyTorch allocator measurements and exclude desktop graphics and non-PyTorch allocations. Upscaling costs local time and energy even when API billing is low.

The 16:9 batch-13 test completed in 81.91s with 9,656 MiB peak reserved and retained all 24 frames at 1920×1080. This is the largest tested batch in this validation set; the 16 GB profile selects 13, and smaller GPUs select 5. `OPENJUTSU_SEED_BATCH_SIZE=5` explicitly reduces the temporal batch if other GPU workloads reduce memory headroom. This short smoke test does not establish peak memory for every 30-second clip.

Creative quality is not inferred from frame count or resolution. Inspect identity, whole-body replacement, lips, hands, hair, backgrounds, flicker and detail drift. Native-versus-upscaled comparison remains unavailable because the pilot route has no native continuation. No route is shipped qualified, and new installations start with zero spending and no credentials.

On a paired 24-frame square clip, decoded outputs resized to 240×240 had mean absolute source differences of 1.351/255 (SeedVR2) and 0.879/255 (Real-ESRGAN). Adjacent-frame changes in that residual averaged 0.460/255 and 0.164/255. These describe pixel changes and added detail; they do not rank perceptual quality or establish a flicker score. Native-versus-upscaled comparison remains unavailable without a cloud result.

Run checks using the README commands. CI launches its fixture with the installed Python and stops it before dependency-cache cleanup. GPU tests and cloud pilots are separate, opt-in local operations. A provider pilot must report actual settled charge, authorized media eligibility, no swaps/synchronization failures, and human scores ≥4/5 for identity, motion and stability. Native continuation needs its own qualified profile.

Shot-aware pilot preparation adds three cast bindings, interval anchors, consent persistence and a durable one-generation limit. CPU tests cover direct-upload expiry, absence of account headers at storage, separate usage estimates, and a large synthetic mask-array round-trip. Browser tests exercise three cast members, revision invalidation, consent/interval persistence and the one-generation limit after reload, alongside existing theme, accessibility and reconnection coverage. CLI shutdown uses a five-second graceful timeout so an open event stream cannot indefinitely retain an old server during restart; a Linux subprocess test verifies port reuse with an open stream.

Export enforces the approved frame count at 24 fps. Remote originals stay intact; the audio-restored master is encoded losslessly after temporal trimming, and the browser delivery uses CRF 18. Native/upscaled delivery dimensions follow the normalized source ratio with a 1080-pixel short edge; aspect-preserving scaling and padding accommodate provider or upscaler dimension rounding. Original-resolution export retains the generation's dimensions. A synthetic one-extra-frame portrait test verifies exact frame count, duration, and delivery dimensions.

## First live multi-reference pilot

On 2026-10-11, an 18-second portrait clip was prepared locally with three consent-confirmed cast references bound across camera changes. Initial annotation review caught background selections, missed tracks and clothing-only masks; corrected preparation retained 432 aligned frames at 540×960. All originals, references, masks, generated footage and detailed records remain untracked.

One ArgoLink Seedance 2.5 reference-mode request at 480p completed and downloaded in 312.02 seconds. The provider returned a silent 480×854 video with 433 frames. Its metered usage was 18 output seconds plus 18 reference seconds. The published-rate estimate was $1.8828; the account billing page reported $1.8815472, reconciled to the ledger's micro-dollar precision. The restored-audio browser preview contains exactly 432 frames over 18 seconds.

The sampled result changed all three roles and clothing while largely retaining the setting. Closing selfie framing/gestures diverged and the car-side facial likeness was not exact. No second cloud request was submitted. This profile remains unqualified; consent, a successful contract and a settled receipt do not establish the required quality scores.

SeedVR2 3B FP8 with batch 13, overlap 3, CPU offload and tiled VAE completed in 1,339.542 seconds (22m19.5s). PyTorch peak reserved memory was 10,374 MiB; sampled whole-device usage reached 14,501 MiB, which includes allocations outside that allocator. The retained upscaled master is 1078×1920; the browser delivery pads to 1080×1920. Both contain 432 frames at 24 fps over 18 seconds with restored original audio. Cross-correlation against the source PCM measured 0 ms offset and 0.999916 correlation, within one output frame.

Comparing all 432 decoded frames at 160×284, mean absolute preview-versus-upscale difference was 2.839/255; adjacent-frame changes in that residual averaged 2.531/255. These are descriptive pixel metrics, not a flicker score. Sampled comparisons show added detail and some facial detail drift; upscaling did not correct the generation's likeness or framing issues. Native HD comparison remains unavailable. Local checks pass: 40 backend tests, 3 annotation unit tests, 5 browser scenarios, type checking, production build and repository hygiene. Browser coverage includes clean editors following external backend revisions while preserving dirty drafts.
