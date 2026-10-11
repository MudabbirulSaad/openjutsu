import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from .store import identifier


def run(args):
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stderr[-3000:])
    return result.stdout


def probe(path):
    data = json.loads(
        run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)])
    )
    v = next((s for s in data["streams"] if s["codec_type"] == "video"), None)
    a = next((s for s in data["streams"] if s["codec_type"] == "audio"), None)
    rate = (v or {}).get("avg_frame_rate", "0/1").split("/")
    fps = int(rate[0]) / int(rate[1]) if int(rate[1]) else 0
    duration = float(data.get("format", {}).get("duration", 0))
    if not duration and a:
        packets = json.loads(
            run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-select_streams",
                    "a:0",
                    "-show_packets",
                    "-show_entries",
                    "packet=pts_time,duration_time",
                    "-of",
                    "json",
                    str(path),
                ]
            )
        )["packets"]
        duration = max(
            (float(p.get("pts_time", 0)) + float(p.get("duration_time", 0)) for p in packets),
            default=0,
        ) - float(data.get("format", {}).get("start_time", 0))
    rotation = next(
        (s.get("rotation", 0) for s in (v or {}).get("side_data_list", []) if "rotation" in s), 0
    )
    return {
        "width": (v or {}).get("width"),
        "height": (v or {}).get("height"),
        "fps": fps,
        "frames": int((v or {}).get("nb_frames", round(duration * fps))),
        "duration": duration,
        "has_audio": a is not None,
        "codec": (v or a or {}).get("codec_name"),
        "sample_rate": int((a or {}).get("sample_rate", 0)),
        "rotation": rotation,
        "start_time": float(data.get("format", {}).get("start_time", 0)),
    }


def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


class Media:
    def __init__(self, config, store):
        self.config, self.store = config, store

    def import_file(self, source, name=None):
        source = Path(source)
        hash = digest(source)
        suffix = source.suffix.lower()
        if suffix not in {
            ".mp4",
            ".mov",
            ".mkv",
            ".webm",
            ".avi",
            ".wav",
            ".mp3",
            ".flac",
            ".m4a",
            ".jpg",
            ".jpeg",
            ".png",
            ".webp",
        }:
            raise ValueError("Use a supported video, image, or audio file")
        folder = self.config.root / "assets" / hash
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / ("original" + suffix)
        if not path.exists():
            shutil.copyfile(source, path)
        metadata = probe(path)
        kind = (
            "image"
            if suffix in {".jpg", ".jpeg", ".png", ".webp"}
            else "video"
            if metadata["width"]
            else "audio"
        )
        asset = {
            "id": identifier(),
            "path": str(path),
            "hash": hash,
            "name": name or source.name,
            "kind": kind,
            "metadata": metadata,
        }
        if kind == "image":
            from PIL import Image, ImageOps

            sanitized = folder / "reference.png"
            if not sanitized.exists():
                with Image.open(path) as im:
                    ImageOps.exif_transpose(im).convert("RGB").save(sanitized)
            asset["reference"] = str(sanitized)
        if kind == "video":
            poster = folder / "poster.jpg"
            if not poster.exists():
                run(
                    [
                        "ffmpeg",
                        "-v",
                        "error",
                        "-i",
                        str(path),
                        "-frames:v",
                        "1",
                        "-vf",
                        "scale=480:-2",
                        "-y",
                        str(poster),
                    ]
                )
            asset["poster"] = str(poster)
        return self.store.put("asset", asset)

    def artifact(self, job, kind, path, producer, cache_key=None):
        path = Path(path)
        if not path.is_file() or not path.is_relative_to(self.config.root):
            raise ValueError("Artifact must exist inside the runtime store")
        metadata = probe(path) if path.suffix in {".mp4", ".mov", ".wav"} else {}
        item = {
            "id": identifier(),
            "job": job["id"],
            "revision": job["revision"],
            "kind": kind,
            "path": str(path),
            "hash": digest(path),
            "metadata": metadata,
            "producer": producer,
            "cache_key": cache_key,
        }
        manifest = next(
            (
                folder / "manifest.json"
                for folder in path.parents
                if folder.is_relative_to(self.config.root / "cache")
                and (folder / "manifest.json").is_file()
            ),
            path.parent / "manifest.json",
        )
        if manifest.is_file():
            provenance = json.loads(manifest.read_text())
            item["cache_key"] = manifest.parent.name
            item["stage"] = provenance.get("stage")
            item["model"] = provenance.get("model")
            item["model_version"] = provenance.get("model_version")
            item["inputs"] = provenance.get("inputs")
        return self.store.put("artifact", item)

    def frame(self, artifact, index):
        m = artifact["metadata"]
        if index < 0 or index >= m.get("frames", 0):
            raise ValueError("Frame index is outside this artifact")
        folder = self.config.root / "cache" / "frames" / artifact["hash"]
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{index:06}.png"
        if not path.exists():
            run(
                [
                    "ffmpeg",
                    "-v",
                    "error",
                    "-i",
                    artifact["path"],
                    "-vf",
                    f"select=eq(n\\,{index})",
                    "-vsync",
                    "0",
                    "-frames:v",
                    "1",
                    "-y",
                    str(path),
                ]
            )
        return path


def normalize(source, output, start, end):
    run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(source),
            "-ss",
            str(start),
            "-t",
            str(end - start),
            "-map",
            "0:v:0",
            "-map",
            "0:a:0?",
            "-vf",
            "scale=w='min(960,iw)':h='min(960,ih)':force_original_aspect_ratio=decrease:force_divisible_by=2,fps=24,setsar=1,format=yuv420p",
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "18",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            "-y",
            str(output),
        ]
    )
    return probe(output)


def audio(source, output, duration=None, start=0):
    args = ["ffmpeg", "-v", "error", "-i", str(source), "-vn", "-ar", "44100", "-ac", "2"]
    if start:
        args.extend(["-ss", str(start)])
    if duration:
        args.extend(["-af", "apad", "-t", str(duration)])
    run([*args, "-c:a", "pcm_f32le", "-y", str(output)])


def mux(video, soundtrack, output, browser=False):
    args = ["ffmpeg", "-v", "error", "-i", str(video)]
    if soundtrack:
        args.extend(
            [
                "-i",
                str(soundtrack),
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-shortest",
            ]
        )
    else:
        args.extend(["-map", "0:v:0", "-an"])
    args.extend(["-c:v", "libx264" if browser else "copy"])
    if browser:
        args.extend(["-vf", "fps=24", "-pix_fmt", "yuv420p", "-crf", "18"])
    run([*args, "-movflags", "+faststart", "-y", str(output)])


def waveform(path, output):
    raw = subprocess.check_output(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "1000",
            "-f",
            "f32le",
            "-",
        ]
    )
    import numpy as np

    samples = np.frombuffer(raw, dtype=np.float32)
    values = [float(np.max(np.abs(x))) if len(x) else 0 for x in np.array_split(samples, 240)]
    Path(output).write_text(json.dumps(values))


def timeline(source, normalized, start, end, output):
    from bisect import bisect_left

    data = json.loads(
        run(
            [
                "ffprobe",
                "-v",
                "error",
                "-read_intervals",
                f"{start}%{end}",
                "-select_streams",
                "v:0",
                "-show_frames",
                "-show_entries",
                "frame=best_effort_timestamp_time",
                "-of",
                "json",
                str(source),
            ]
        )
    )
    offset = probe(source)["start_time"]
    points = sorted(
        float(f["best_effort_timestamp_time"]) - offset
        for f in data["frames"]
        if "best_effort_timestamp_time" in f
    )
    result = []
    for index in range(probe(normalized)["frames"]):
        requested = start + index / 24
        position = bisect_left(points, requested)
        candidates = points[max(0, position - 1) : position + 1]
        nearest = min(candidates, key=lambda p: abs(p - requested)) if candidates else None
        result.append(
            {
                "frame": index,
                "output_time": index / 24,
                "source_time_requested": requested,
                "source_pts_nearest": nearest,
            }
        )
    Path(output).write_text(
        json.dumps(
            {
                "fps": 24,
                "mapping": "nearest source PTS to requested CFR sampling time; normalized pixels are the review authority",
                "frames": result,
            }
        )
    )
