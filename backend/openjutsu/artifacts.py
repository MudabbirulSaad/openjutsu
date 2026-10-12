"""Verified local persistence. File hashes identify bytes; readback establishes usability."""

import json
import os
import tempfile
from pathlib import Path
from zipfile import ZipFile

import numpy as np


def _finite(values):
    if values.dtype.kind not in "biufc":
        raise ValueError("Numerical artifacts must not contain objects or nonnumeric arrays")
    flat = values.ravel(order="K")
    for start in range(0, flat.size, 1_048_576):
        if not np.isfinite(flat[start : start + 1_048_576]).all():
            raise ValueError("Numerical artifact contains non-finite values")


def verify_npz(path, expected=None):
    """Read every ZIP member through its CRC and every array, including unused members."""
    with ZipFile(path) as zipped:
        members = zipped.infolist()
        names = [item.filename for item in members]
        if (
            not names
            or len(names) != len(set(names))
            or any(not name.endswith(".npy") or "/" in name or "\\" in name for name in names)
        ):
            raise ValueError("Numerical archive has empty, duplicate or invalid members")
        for member in members:
            with zipped.open(member) as stream:
                while stream.read(1_048_576):
                    pass
    result = {}
    with np.load(path, allow_pickle=False) as archive:
        if expected is not None and set(archive.files) != set(expected):
            raise ValueError("Numerical archive members differ on readback")
        for name in archive.files:
            values = archive[name]
            _finite(values)
            if expected is not None:
                original = expected[name]
                if (
                    values.dtype != original.dtype
                    or values.shape != original.shape
                    or not np.array_equal(values, original)
                ):
                    raise ValueError(f"Numerical archive {name} differs on readback")
            result[name] = {"shape": list(values.shape), "dtype": str(values.dtype)}
    return result


def verify_npy(path, expected=None):
    try:
        values = np.load(path, mmap_mode="r", allow_pickle=False)
    except OSError as exc:
        # Windows mapping of a truncated payload raises OSError instead of ValueError.
        # Preserve its diagnostic cause while exposing a consistent validation failure.
        raise ValueError("Numerical array cannot be mapped for readback") from exc
    try:
        if Path(path).stat().st_size != values.offset + values.nbytes:
            raise ValueError("Numerical array payload length differs from its header")
        _finite(values)
        if expected is not None and (
            values.dtype != expected.dtype
            or values.shape != expected.shape
            or not np.array_equal(values, expected)
        ):
            raise ValueError("Numerical array differs on readback")
        return {"shape": list(values.shape), "dtype": str(values.dtype)}
    finally:
        values._mmap.close()


def verify_depth(path, count=None, shape=None):
    result = verify_npz(path)
    depths = result.get("depths")
    if not depths or len(depths["shape"]) != 3 or np.dtype(depths["dtype"]).kind != "f":
        raise ValueError("Depth archive requires a three-dimensional floating depths array")
    if count is not None and depths["shape"][0] != count:
        raise ValueError("Depth archive frame count differs from normalized source")
    if shape is not None and depths["shape"] != list(shape):
        raise ValueError("Depth archive dimensions differ from normalized source")
    return result


def _sync_directory(folder):
    if os.name == "nt":
        return  # Windows replace is atomic; directory fsync is not exposed here.
    import errno

    descriptor = os.open(folder, os.O_RDONLY | os.O_DIRECTORY)
    try:
        try:
            os.fsync(descriptor)
        except OSError as exc:
            if exc.errno not in {errno.EINVAL, errno.ENOTSUP}:
                raise
    finally:
        os.close(descriptor)


def atomic_write(path, writer, verify):
    """Publish only a fully flushed, closed, verified sibling. Retain failed siblings."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.pending-")
    temporary = Path(temporary)
    with os.fdopen(descriptor, "w+b") as stream:
        writer(stream)
        stream.flush()
        os.fsync(stream.fileno())
    verify(temporary)
    os.replace(temporary, path)
    _sync_directory(path.parent)
    return path


def write_npz(path, arrays, *, compressed=True):
    save = np.savez_compressed if compressed else np.savez
    return atomic_write(
        path, lambda stream: save(stream, **arrays), lambda temporary: verify_npz(temporary, arrays)
    )


def write_npy(path, values):
    return atomic_write(
        path,
        lambda stream: np.save(stream, values, allow_pickle=False),
        lambda temporary: verify_npy(temporary, values),
    )


def read_json(path):
    def nonfinite(value):
        raise ValueError(f"Invalid non-finite JSON value: {value}")

    return json.loads(Path(path).read_text(), parse_constant=nonfinite)


def write_json(path, data):
    encoded = json.dumps(data, allow_nan=False).encode()

    def verify(temporary):
        # Recipes/model stamps can contain tuples; JSON intentionally stores them as lists.
        if temporary.read_bytes() != encoded or read_json(temporary) != json.loads(encoded):
            raise ValueError("JSON differs on readback")

    return atomic_write(path, lambda stream: stream.write(encoded), verify)


def sync_outputs(paths):
    """Flush completed worker files before committing the manifest that names them."""
    parents = set()
    for name in paths.values():
        path = Path(name)
        # Windows FlushFileBuffers requires a writable handle. Opening without
        # truncation also works on POSIX and does not change the verified bytes.
        with path.open("r+b") as stream:
            os.fsync(stream.fileno())
        parents.add(path.parent)
    for parent in parents:
        _sync_directory(parent)
        _sync_directory(parent.parent)


def verify_outputs(paths, stage, source, recipe, folder, options=None):
    """Validate the producing stage's required outputs before cache publication/reuse."""
    from .media import probe, run

    options = options or {}
    source_meta = probe(source)
    required = {
        "normalize": {"normalized", "timeline"},
        "depth": {"depth", "depth_data"},
        "mask": {"mask", "mask_data", "tracking"},
        "composite": {"composite"},
        "mesh": {"mesh", "landmarks"},
        "conditioning": {"conditioning"},
        "vocals": {"vocals", "background_audio"},
        "pitch": {"conditioning_audio"},
        "custom": {"custom_voice", "final_audio"},
        "whisper": {"transcript"},
        "describe": {"descriptions"},
        "quality": {"quality"},
        "seedvr2": {"upscaled"},
        "realesrgan": {"upscaled"},
        "export": {"master", "delivery"},
        "audio": {"original_audio", "waveform"} if source_meta["has_audio"] else set(),
    }.get(stage)
    if not isinstance(paths, dict) or required is None or not required <= paths.keys():
        raise ValueError("Worker/cache is missing required stage artifacts")
    count = source_meta["frames"]
    if stage == "normalize":
        count = round((recipe["end"] - recipe["start"]) * 24)
    elif stage == "export":
        count = options.get("frame_count", round((recipe["end"] - recipe["start"]) * 24))
    verification = {}
    for kind, name in paths.items():
        path = Path(name)
        if not path.is_file() or not path.resolve().is_relative_to(Path(folder).resolve()):
            raise ValueError("Stage artifacts must exist within their cache directory")
        if kind == "depth_data":
            verification[kind] = verify_depth(
                path, count, (count, source_meta["height"], source_meta["width"])
            )
        elif kind == "mask_data":
            if path.suffix == ".npy":
                description = verify_npy(path)
            else:
                description = verify_npz(path).get("masks")
            if description != {
                "shape": [count, source_meta["height"], source_meta["width"]],
                "dtype": "uint8",
            }:
                raise ValueError("Mask array dimensions/dtype differ from normalized source")
            verification[kind] = description
        elif path.suffix in {".mp4", ".mov", ".wav"}:
            meta = probe(path)
            if meta["duration"] <= 0 or meta["width"] and meta["frames"] != count:
                raise ValueError("Stage video frame count/duration differs from its input timeline")
            if stage in {"depth", "mask", "composite", "mesh", "conditioning"} and (
                meta["width"],
                meta["height"],
            ) != (source_meta["width"], source_meta["height"]):
                raise ValueError("Stage video dimensions differ from normalized source")
            run(["ffmpeg", "-v", "error", "-xerror", "-i", str(path), "-f", "null", "-"])
            verification[kind] = meta
        elif path.suffix == ".json":
            read_json(path)
            verification[kind] = {"format": "json"}
        else:
            raise ValueError("Unknown stage artifact format")
    return verification
