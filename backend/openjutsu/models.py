import importlib.metadata
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

MODEL_SPECS = {
    "depth": {
        "package": "torch",
        "file": "video-depth-anything/checkpoints/video_depth_anything_vits.pth",
        "repo": "https://github.com/DepthAnything/Video-Depth-Anything",
        "license": "Apache-2.0 (Small)",
    },
    "sam2-large": {"package": "sam2", "file": "sam2.1_hiera_large.pt", "license": "Apache-2.0"},
    "sam2-small": {"package": "sam2", "file": "sam2.1_hiera_small.pt", "license": "Apache-2.0"},
    "sam3": {"package": "sam3", "file": "sam3.pt", "license": "SAM License; gated checkpoint"},
    "mesh": {"package": "mediapipe", "file": "face_landmarker.task", "license": "Apache-2.0"},
    "vocals": {
        "package": "demucs",
        "file": "torch/hub/checkpoints/955717e8-8726e21a.th",
        "license": "MIT",
    },
    "pitch": {"package": "librosa", "file": None, "license": "ISC"},
    "whisper": {"package": "whisper", "file": "whisper/large-v3-turbo.pt", "license": "MIT"},
    "describe": {
        "package": "transformers",
        "file": "qwen3-vl/config.json",
        "license": "Apache-2.0",
    },
    "seedvr2": {
        "package": "torch",
        "file": "seedvr2-weights/seedvr2_ema_3b_fp8_e4m3fn.safetensors",
        "license": "Apache-2.0",
    },
    "realesrgan": {
        "package": "torch",
        "file": "realesrgan/weights/RealESRGAN_x4plus.pth",
        "license": "BSD-3-Clause",
    },
}


def local_readiness(model_dir):
    ready = {}
    hashes_path = Path(model_dir) / "checkpoint-hashes.json"
    hashes = json.loads(hashes_path.read_text()) if hashes_path.exists() else {}
    for name, spec in MODEL_SPECS.items():
        package = importlib.util.find_spec(spec["package"]) is not None
        checkpoint = spec["file"] is None or (Path(model_dir) / spec["file"]).is_file()
        if name == "depth":
            package = (
                package
                and importlib.util.find_spec("cv2") is not None
                and (
                    Path(model_dir) / "video-depth-anything/video_depth_anything/video_depth.py"
                ).is_file()
            )
        if name == "describe":
            checkpoint = checkpoint and bool(
                list((Path(model_dir) / "qwen3-vl").glob("*.safetensors"))
            )
        if name == "seedvr2":
            checkpoint = (
                checkpoint
                and (Path(model_dir) / "seedvr2-weights/ema_vae_fp16.safetensors").is_file()
                and (Path(model_dir) / "seedvr2/inference_cli.py").is_file()
            )
            package = package and importlib.util.find_spec("diffusers") is not None
        if name == "realesrgan":
            package = package and importlib.util.find_spec("realesrgan") is not None
        ready[name] = {
            "ready": package and checkpoint,
            "package": package,
            "checkpoint": checkpoint,
            "license": spec["license"],
            "checkpoint_sha256": hashes.get(spec["file"]),
        }
        if name == "describe":
            from .store import fingerprint

            ready[name]["checkpoint_sha256"] = (
                fingerprint({k: v for k, v in hashes.items() if k.startswith("qwen3-vl/")})
                if hashes
                else None
            )
        repo = {
            "depth": "video-depth-anything",
            "sam2-large": "sam2",
            "sam2-small": "sam2",
            "seedvr2": "seedvr2",
            "realesrgan": "realesrgan",
        }.get(name)
        if repo and (Path(model_dir) / repo / ".git").exists():
            result = subprocess.run(
                ["git", "-C", str(Path(model_dir) / repo), "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            ready[name]["source_commit"] = result.stdout.strip() if result.returncode == 0 else None
        try:
            ready[name]["package_version"] = importlib.metadata.version(
                {"whisper": "openai-whisper", "sam2": "sam-2"}.get(spec["package"], spec["package"])
            )
        except importlib.metadata.PackageNotFoundError:
            ready[name]["package_version"] = None
    try:
        import torch

        gpu = {
            "available": torch.cuda.is_available(),
            "name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
            "total_mb": torch.cuda.get_device_properties(0).total_memory // 1048576
            if torch.cuda.is_available()
            else 0,
        }
    except ImportError:
        gpu = {"available": False, "name": None, "total_mb": 0}
    if ready["sam3"]["ready"]:
        validation_path = Path(model_dir) / "sam3-readiness.json"
        validation = json.loads(validation_path.read_text()) if validation_path.is_file() else {}
        checkpoint = Path(model_dir) / "sam3.pt"
        ready["sam3"]["ready"] = bool(
            validation.get("passed")
            and validation.get("gpu") == gpu.get("name")
            and validation.get("checkpoint_stamp")
            == [checkpoint.stat().st_size, checkpoint.stat().st_mtime_ns]
        )
        if not ready["sam3"]["ready"]:
            ready["sam3"]["reason"] = (
                "Run an authorized local SAM 3 preparation smoke test on this GPU"
            )
    return {"models": ready, "gpu": gpu}


def readiness(config):
    try:
        result = subprocess.run(
            [config.ml_python or sys.executable, "-m", "openjutsu.models", str(config.model_dir)],
            capture_output=True,
            text=True,
            timeout=25,
        )
        return json.loads(result.stdout.strip().splitlines()[-1])
    except (OSError, subprocess.TimeoutExpired, ValueError, IndexError):
        return {
            "models": {
                k: {"ready": False, "reason": "Model environment unavailable"} for k in MODEL_SPECS
            },
            "gpu": {"available": False},
        }


if __name__ == "__main__":
    print(json.dumps(local_readiness(sys.argv[1])))
