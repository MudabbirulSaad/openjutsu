"""Explicit, pinned local model installation. Run with the CUDA model environment's Python."""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

REPOS = {
    "depth": (
        "video-depth-anything",
        "https://github.com/DepthAnything/Video-Depth-Anything.git",
        "4f5ae23172ba60fd7bc11ef671cca678842c7072",
    ),
    "sam2": (
        "sam2",
        "https://github.com/facebookresearch/sam2.git",
        "2b90b9f5ceec907a1c18123530e92e794ad901a4",
    ),
    "seedvr2": (
        "seedvr2",
        "https://github.com/numz/ComfyUI-SeedVR2_VideoUpscaler.git",
        "4490bd1f482e026674543386bb2a4d176da245b9",
    ),
    "realesrgan": (
        "realesrgan",
        "https://github.com/xinntao/Real-ESRGAN.git",
        "a4abfb2979a7bbff3f69f58f58ae324608821e27",
    ),
}
FILES = {
    "depth": (
        "video-depth-anything/checkpoints/video_depth_anything_vits.pth",
        "https://huggingface.co/depth-anything/Video-Depth-Anything-Small/resolve/main/video_depth_anything_vits.pth",
    ),
    "sam2-large": (
        "sam2.1_hiera_large.pt",
        "https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_large.pt",
    ),
    "sam2-small": (
        "sam2.1_hiera_small.pt",
        "https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_small.pt",
    ),
    "mesh": (
        "face_landmarker.task",
        "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task",
    ),
    "quality": (
        "pose_landmarker.task",
        "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_heavy/float16/1/pose_landmarker_heavy.task",
    ),
}


def run(*args, **kwargs):
    subprocess.run([str(a) for a in args], check=True, **kwargs)


def download(url, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        temporary = path.with_suffix(path.suffix + ".part")
        print(f"Downloading {path.name}", flush=True)
        with urllib.request.urlopen(url, timeout=90) as source, temporary.open("wb") as target:
            shutil.copyfileobj(source, target)
        temporary.replace(path)


def clone(key, directory):
    name, url, commit = REPOS[key]
    target = directory / name
    if not target.exists():
        run("git", "clone", "--filter=blob:none", "--no-checkout", url, target)
    run("git", "-C", target, "checkout", "--detach", commit)
    return target


def install(components, directory, whisper_cache=None):
    directory.mkdir(parents=True, exist_ok=True)
    uv = Path(sys.executable).parent / "uv"
    for component in components:
        if component == "depth":
            clone("depth", directory)
        elif component.startswith("sam2-"):
            repo = clone("sam2", directory)
            run(
                uv,
                "pip",
                "install",
                "--python",
                sys.executable,
                "--no-deps",
                "--no-build-isolation",
                "-e",
                repo,
                env={**os.environ, "SAM2_BUILD_CUDA": "0"},
            )
        elif component == "audio":
            # Explicitly warm the checkpoint cache before offline processing.
            os.environ["TORCH_HOME"] = str(directory / "torch")
            from demucs.pretrained import get_model

            get_model("htdemucs")
        elif component == "whisper":
            target = directory / "whisper" / "large-v3-turbo.pt"
            if whisper_cache and Path(whisper_cache).is_file():
                target.parent.mkdir(parents=True, exist_ok=True)
                if not target.exists():
                    shutil.copyfile(whisper_cache, target)
            import whisper

            whisper.load_model(
                "large-v3-turbo", device="cpu", download_root=str(directory / "whisper")
            )
        elif component == "qwen":
            from huggingface_hub import snapshot_download

            snapshot_download("Qwen/Qwen3-VL-4B-Instruct", local_dir=directory / "qwen3-vl")
        elif component in {"seedvr2", "realesrgan"}:
            repo = clone(component, directory)
            if component == "seedvr2":
                from huggingface_hub import hf_hub_download

                for filename in [
                    "seedvr2_ema_3b_fp8_e4m3fn.safetensors",
                    "ema_vae_fp16.safetensors",
                ]:
                    hf_hub_download(
                        "numz/SeedVR2_comfyUI", filename, local_dir=directory / "seedvr2-weights"
                    )
            else:
                run(
                    uv,
                    "pip",
                    "install",
                    "--python",
                    sys.executable,
                    "--no-deps",
                    "--no-build-isolation",
                    "-e",
                    repo,
                )
                download(
                    "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth",
                    repo / "weights/RealESRGAN_x4plus.pth",
                )
        elif component not in FILES:
            raise ValueError(f"Unknown component {component}")
        if component in FILES:
            file, url = FILES[component]
            download(url, directory / file)
    # Hash downloaded checkpoints so a recipe can record exactly what was used.
    hashes = {}
    for file in directory.rglob("*"):
        if file.is_file() and file.suffix in {".pt", ".pth", ".th", ".task", ".safetensors"}:
            h = hashlib.sha256()
            with file.open("rb") as f:
                for block in iter(lambda: f.read(1024 * 1024), b""):
                    h.update(block)
            hashes[str(file.relative_to(directory))] = h.hexdigest()
    (directory / "checkpoint-hashes.json").write_text(json.dumps(hashes, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "components",
        nargs="+",
        choices=[*FILES, "audio", "whisper", "qwen", "seedvr2", "realesrgan"],
    )
    parser.add_argument(
        "--directory", type=Path, default=Path.home() / ".local/share/openjutsu/models"
    )
    parser.add_argument("--whisper-cache")
    args = parser.parse_args()
    install(args.components, args.directory, args.whisper_cache)
