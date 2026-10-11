# Troubleshooting

**Browser cannot reach the backend.** Start `bash scripts/serve.sh` in Ubuntu and open `http://127.0.0.1:9780`. On Windows, inspect `netsh int ipv4 show excludedportrange protocol=tcp`: Windows/Hyper-V can reserve an otherwise unused port. Choose an available port with `bash scripts/serve.sh --port NUMBER` and update the Vite development proxy if needed. WSL localhost forwarding must be enabled. No firewall rule or public listen address is required.

**Readiness reports missing models.** Install in the model environment, not the API environment. Set `OPENJUTSU_ML_PYTHON` to that environment's Python, then refresh readiness. Check CUDA access using `/usr/lib/wsl/lib/nvidia-smi`. Install FFmpeg, Git and `python3-venv` in Ubuntu. The app keeps the database and model cache on Linux, avoiding Windows filesystem performance penalties.

**Face tracking gap.** Use a continuous frontal talking shot, trim away cuts, or select Advanced mode. Fast and Combined stop rather than silently reusing missing landmarks. A profile shot, small embedded face, occlusion or camera cut can prevent mesh detection.

**Incorrect mask or subject swap.** Inspect source/mask/depth/composite at the same paused frame. Add include/exclude points or a box on that correction frame. Each track needs an anchor at frame 0. Save, reprepare and reapprove. Unchanged upstream audio/depth should reuse verified cache artifacts.

**CUDA exhaustion.** Close other GPU applications, choose SAM 2.1 Small explicitly, and use the tested SeedVR2 FP8/offload/tiling profile. The failed subprocess releases GPU memory and previous completed stages remain cached. Availability alone does not guarantee every 30-second clip or aspect ratio fits. Do not replace Small depth weights with the noncommercial Base/Large default.

**Submission uncertain.** Reconcile the existing request on the provider dashboard. An existing ID resumes polling without a new paid request. Confirming no submission requires your own dashboard check. Browser closure does not cancel a remote request or release its reservation.

**Unsettled charge.** Enter the receipt's actual USD amount. Failed remote tasks may still incur a charge; the application holds their reservation rather than assuming zero. Project estimates are not an account spending cap.

**Expired draft or result URL.** Use the retained local result. An expired draft cannot be continued natively. Choose original resolution or a local upscale; do not submit a downloaded draft as a substitute for same-task continuation.

**Custom speech timing.** Record after microphone permission is granted using the timed recorder, or import an aligned recording. Local preparation requires duration within 250 ms and pads/trims it to the clip duration. The same voice is used for conditioning and restored unpitched final audio. Background mixing is optional.

**Original or generated codec will not play.** The viewer uses H.264 browser copies, while the native generation/master remains separate. Download the master for an editor that supports its codec. Paused review uses indexed PNGs from the browser copy.
