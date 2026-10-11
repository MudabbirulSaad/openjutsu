# Local models

Use Ubuntu WSL2 with Python 3.12 and a CUDA-capable NVIDIA driver. Do not install a separate Linux GPU driver inside WSL. FFmpeg, Git and uv 0.13.0 must be available. The tested model environment uses Torch 2.8.0/CUDA 12.8; `scripts/requirements-cuda.lock` pins its Python dependencies separately from the CPU application lockfile.

```bash
bash scripts/setup.sh
runtime="$HOME/.local/share/openjutsu"
"$runtime/venv/bin/python" scripts/install_models.py depth sam2-large mesh quality audio whisper
# Optional lower-memory segmentation profile:
"$runtime/venv/bin/python" scripts/install_models.py sam2-small
# Optional assistance and finalization:
"$runtime/venv/bin/python" scripts/install_models.py qwen seedvr2 realesrgan
```

The installer downloads weights into the Linux runtime, checks out pinned upstream commits, warms Demucs, and writes checkpoint hashes. It does not put models in the public checkout. An existing Whisper checkpoint can be reused with `--whisper-cache /path/to/large-v3-turbo.pt`; Whisper verifies it against its expected checksum. Downloads require several gigabytes of disk space. The Qwen model alone is roughly 8 GB. Processing disables Hugging Face network access and uses cached weights.

| Stage | Model / code | License and constraints |
|---|---|---|
| Speech | [Whisper large-v3-turbo](https://github.com/openai/whisper) | MIT; machine text needs review |
| Vocals | [Demucs htdemucs](https://github.com/facebookresearch/demucs) | MIT; separation can leave artifacts |
| Pitch | [librosa](https://librosa.org/doc/0.11.0/generated/librosa.effects.pitch_shift.html) | ISC; final audio is not pitch shifted |
| Depth | [Video Depth Anything Small](https://github.com/DepthAnything/Video-Depth-Anything) | Apache 2.0 Small; Base/Large are noncommercial and excluded |
| Masks | [SAM 2.1](https://github.com/facebookresearch/sam2) | Apache 2.0; Large default, Small optional; state/video offloaded to CPU |
| Mesh | [MediaPipe Face Landmarker](https://ai.google.dev/edge/mediapipe/solutions/vision/face_landmarker/python) | Apache 2.0; one talking subject; stops on tracking gaps |
| Quality | [MediaPipe Pose Landmarker Heavy](https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker/python) and Face Landmarker | Apache 2.0; independent frame detections; anatomy/edge decisions require source inspection |
| Suggestions | [Qwen3-VL-4B-Instruct](https://huggingface.co/Qwen/Qwen3-VL-4B-Instruct) | Apache 2.0; ordered-frame descriptions are editable suggestions |
| Upscale | [SeedVR2 standalone](https://github.com/numz/ComfyUI-SeedVR2_VideoUpscaler) | Apache 2.0 integration; 3B FP8 plus shared VAE, CPU offload and VAE tiling |
| Fallback | [Real-ESRGAN](https://github.com/xinntao/Real-ESRGAN) | BSD 3-Clause; frame-based, no automatic face enhancement |

`install_models.py` pins the upstream source revisions. Checkpoint filenames and URLs are explicit; `checkpoint-hashes.json` records downloaded content. SeedVR2's integration also verifies its published SHA256 weights. Review upstream licenses before distributing weights or custom derivative models; the application's Apache license does not relicense them.

SAM 3 is an experimental adapter, not installed by default. Obtain authorized checkpoint access from [the upstream project](https://github.com/facebookresearch/sam3), follow its license and installation instructions, and place `sam3.pt` in the model directory. Run `gpu_smoke.py /path/to/video.mp4 --segmentation sam3 --modes advanced` with the model Python. Only a successful local test writes the GPU/checkpoint readiness marker; changing the checkpoint invalidates it. Its API and performance are unverified in this release. No SAM 3 checkpoint or qualification is bundled. Optional Rubber Band pitch processing uses an installed `rubberband` executable and its [GPL/commercial licensing terms](https://breakfastquay.com/rubberband/license.html); it is not bundled or the default.

After installation, use **Settings → Refresh readiness**, or run:

```bash
OPENJUTSU_ML_PYTHON="$runtime/venv/bin/python" "$runtime/api-venv/bin/openjutsu" doctor
"$runtime/venv/bin/python" scripts/gpu_smoke.py /path/to/a/suitable-video.mp4
```

Availability means packages and required checkpoint files are present. It does not assert output quality. The studio exposes local benchmark records separately. A tracking gap or CUDA exhaustion produces an explicit failed stage and retains previous completed stages for reuse.
