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
| Provider adapters | Synthetic request/status/ambiguity/draft/charge contracts | No paid request or settled billing pilot has been run |
| Native HD | Saved-draft/account orchestration and contract checks | Live native continuation and quality unqualified |
| SAM 3 | Optional adapter only | Gated weights unavailable; not locally tested or enabled by default |

Local stage timings are cold subprocess timings, not a promised processing rate. The Advanced smoke run reused earlier completed audio stages while recovering from dependency errors; its 42-second completion is not a full cold-start benchmark. Individual measured stages included VDA Small 14.84s / 11,858 MiB peak reserved, SAM 2.1 Large 10.95s / 2,100 MiB, Demucs 2.99s / 828 MiB, and Whisper 9.49s / 5,248 MiB. Process startup, import and disk time vary. MediaPipe executes its inference on CPU in this WSL integration while remaining serialized with the model pipeline.

A later complete cold preparation in the actual application runtime took 50.07s for the four-second source interval and produced 96 aligned frames. It is available locally for review with zero spending and no provider credentials. The full 21:46 recording also has an ignored transcript package based on two CUDA Whisper passes; low-confidence passages remain marked for listening review.

Fast completed in 26.03s on a suitable frontal crop; Combined added 33.07s while reusing unaffected audio/transcription. SeedVR2's one-second 16:9 test at temporal batch 5 took 151.20s with 6,766 MiB peak reserved. Square-output batches 5, 9 and 13 were also measured; their GPU reservation peaks were 6,662, 8,786 and 8,928 MiB respectively. These are PyTorch allocator measurements and exclude desktop graphics and non-PyTorch allocations. Upscaling costs local time and energy even when API billing is low.

The 16:9 batch-13 test completed in 81.91s with 9,656 MiB peak reserved and retained all 24 frames at 1920×1080. This is the largest tested batch in this validation set; the 16 GB profile selects 13, and smaller GPUs select 5. `OPENJUTSU_SEED_BATCH_SIZE=5` explicitly reduces the temporal batch if other GPU workloads reduce memory headroom. This short smoke test does not establish peak memory for every 30-second clip.

Creative quality is not inferred from frame count or resolution. Inspect identity, whole-body replacement, lips, hands, hair, backgrounds, flicker and detail drift. No cloud generation was available for a native-versus-upscaled comparison, and no cheaper route is shipped as qualified. The release intentionally starts with zero spending and no credentials.

On a paired 24-frame square clip, decoded outputs resized to 240×240 had mean absolute source differences of 1.351/255 (SeedVR2) and 0.879/255 (Real-ESRGAN). Adjacent-frame changes in that residual averaged 0.460/255 and 0.164/255. These describe pixel changes and added detail; they do not rank perceptual quality or establish a flicker score. Native-versus-upscaled comparison remains unavailable without a cloud result.

Run checks using the README commands. CI launches its fixture with the installed Python and stops it before dependency-cache cleanup. GPU tests and cloud pilots are separate, opt-in local operations. A provider pilot must report actual settled charge, authorized media eligibility, no swaps/synchronization failures, and human scores ≥4/5 for identity, motion and stability. Native continuation needs its own qualified profile.

Shot-aware pilot preparation adds three cast bindings, interval anchors, consent persistence and a durable one-generation limit. CPU tests cover direct-upload expiry, absence of account headers at storage, separate usage estimates, and a large synthetic mask-array round-trip. Browser tests exercise three cast members, revision invalidation, consent/interval persistence and the one-generation limit after reload, alongside existing theme, accessibility and reconnection coverage. CLI shutdown uses a five-second graceful timeout so an open event stream cannot indefinitely retain an old server during restart; a Linux subprocess test verifies port reuse with an open stream.
