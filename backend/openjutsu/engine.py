import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from .config import Secrets
from .media import Media, digest, probe
from .models import MODEL_SPECS, readiness
from .providers import Ambiguous, Provider, Rejected, Uploads, account
from .store import Conflict, fingerprint
from .tracking import validate_bindings


class Engine:
    def __init__(self, config, store):
        self.config, self.store = config, store
        self.media, self.secrets = Media(config, store), Secrets(config.root)
        self.uploads = Uploads(self.secrets, store)
        self.stop_event = threading.Event()
        self.process = None
        self.model_state = readiness(config)
        self.threads = []

    def start(self):
        self.store.recover()
        for target in (self.work_loop, self.cloud_loop):
            thread = threading.Thread(target=target, daemon=True)
            thread.start()
            self.threads.append(thread)

    def stop(self):
        self.stop_event.set()
        if self.process and self.process.poll() is None:
            self.kill_process()
        for thread in self.threads:
            thread.join(timeout=5)

    def required_models(self, job):
        r = job["recipe"]
        required = []
        source = self.store.get("asset", job["source"])
        if source["metadata"]["has_audio"] and (
            r["audio"] == "original" or r["custom_mix_background"]
        ):
            required.append("vocals")
        if source["metadata"]["has_audio"] or r["audio"] == "custom":
            if r["pitch_backend"] == "librosa":
                required.append("pitch")
        if r["mode"] != "fast":
            required.extend(["depth", r["segmentation"]])
        if r["mode"] != "advanced":
            required.append("mesh")
        if r["transcribe"] and (source["metadata"]["has_audio"] or r["audio"] == "custom"):
            required.append("whisper")
        if r["describe"]:
            required.append("describe")
        return required

    def prepare(self, id, revision):
        job = self.store.get("job", id)
        self.store.check_revision(job, revision)
        r = job["recipe"]
        if self.store.get("asset", job["source"])["metadata"]["duration"] < r["end"] - 0.01:
            raise Conflict("Trim end is beyond the source recording")
        if not r["subjects"]:
            raise Conflict("Add a subject and its reference images")
        for s in r["subjects"]:
            if not s["references"] and not s["portrait_asset"]:
                raise Conflict("Add references for every subject")
            for ref in s["references"]:
                if self.store.get("asset", ref)["kind"] != "image":
                    raise Conflict("Subject references must be images")
            if any(a["frame"] >= round((r["end"] - r["start"]) * 24) for a in s["annotations"]):
                raise Conflict("A correction frame is beyond the selected clip")
        if r["mode"] != "fast":
            validate_bindings(r)
        if r["segmentation"] == "sam3" and any(
            s.get("intervals") or s.get("visibility") or s.get("seed_frame") is not None
            for s in r["subjects"]
        ):
            raise Conflict("Shot intervals currently require SAM 2.1")
        missing = [
            m
            for m in self.required_models(job)
            if not self.model_state["models"].get(m, {}).get("ready")
        ]
        if missing:
            raise Conflict("Install model requirements: " + ", ".join(missing))
        if not self.model_state["gpu"]["available"]:
            raise Conflict("The configured model environment cannot access CUDA")
        return self.store.enqueue(id, "prepare", {"revision": revision})

    def run_stage(self, job, name, source, parameters, **kwargs):
        if self.stop_event.is_set() or self.store.get("job", job["id"])["cancel"]:
            raise InterruptedError("Local processing stopped")
        try:
            if os.name == "nt":
                return self._run_stage(job, name, source, parameters, **kwargs)
            import fcntl

            with (self.config.model_dir / ".gpu.lock").open("a") as lock:
                while True:
                    try:
                        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        break
                    except BlockingIOError:
                        if self.stop_event.is_set() or self.store.get("job", job["id"])["cancel"]:
                            raise InterruptedError("Cancelled while waiting for the GPU")
                        self.stop_event.wait(0.1)
                return self._run_stage(job, name, source, parameters, **kwargs)
        finally:
            self.process = None

    def _run_stage(self, job, name, source, parameters, **kwargs):
        source = Path(source)
        dependencies = {"source": digest(source)}
        for key, value in kwargs.items():
            if isinstance(value, str) and Path(value).is_file():
                dependencies[key] = digest(value)
        model = job["recipe"]["segmentation"] if name == "mask" else name
        spec = MODEL_SPECS.get(model, {})
        checkpoint = self.config.model_dir / spec["file"] if spec.get("file") else None
        model_stamp = (
            (checkpoint.stat().st_size, checkpoint.stat().st_mtime_ns)
            if checkpoint and checkpoint.is_file()
            else None
        )
        model_info = self.model_state["models"].get(model, {})
        model_stamp = {
            "file": model_stamp,
            "sha256": model_info.get("checkpoint_sha256"),
            "package": model_info.get("package_version"),
            "source_commit": model_info.get("source_commit"),
        }
        key = fingerprint(
            {
                "version": 5 if name == "mask" else 2 if name == "depth" else 1,
                "stage": name,
                "inputs": dependencies,
                "parameters": parameters,
                "model": model_stamp,
                "options": {k: v for k, v in kwargs.items() if k not in dependencies},
            }
        )
        output = self.config.root / "cache" / key
        output.mkdir(parents=True, exist_ok=True)
        manifest = output / "manifest.json"
        if manifest.exists():
            result = json.loads(manifest.read_text())
            if result.get("hashes") and all(
                Path(path).is_file() and digest(path) == result["hashes"].get(kind)
                for kind, path in result["paths"].items()
            ):
                self.store.update("job", job["id"], {"progress": {"stage": name, "cached": True}})
                return result["paths"]
        task = {
            "stage": name,
            "source": str(source),
            "output": str(output),
            "models": str(self.config.model_dir),
            "recipe": job["recipe"],
            **kwargs,
        }
        task_path = output / "task.json"
        task_path.write_text(json.dumps(task))
        self.store.update("job", job["id"], {"progress": {"stage": name, "cached": False}})
        env = dict(os.environ)
        env["HF_HUB_OFFLINE"] = "1"
        env["TRANSFORMERS_OFFLINE"] = "1"
        env["TORCH_HOME"] = str(self.config.model_dir / "torch")
        error_path = output / "worker-error.log"
        result = None
        with error_path.open("w") as errors:
            self.process = subprocess.Popen(
                [self.config.ml_python or sys.executable, "-m", "openjutsu.worker", str(task_path)],
                stdout=subprocess.PIPE,
                stderr=errors,
                text=True,
                env=env,
                start_new_session=os.name != "nt",
            )
            events = []
            process = self.process

            def drain():
                for line in process.stdout:
                    try:
                        event = json.loads(line)
                    except ValueError:
                        continue
                    events.append(event)
                    if "completed" in event:
                        self.store.update(
                            "job",
                            job["id"],
                            {
                                "progress": {
                                    "stage": name,
                                    "completed": event["completed"],
                                    "total": event["total"],
                                }
                            },
                        )

            reader = threading.Thread(target=drain, daemon=True)
            reader.start()
            while self.process.poll() is None:
                if self.stop_event.is_set() or self.store.get("job", job["id"])["cancel"]:
                    self.kill_process()
                    raise InterruptedError("Local processing stopped")
                # Avoid blocking cancellation on a silent model subprocess.
                time.sleep(0.1)
            reader.join(timeout=5)
            for event in events:
                if "result" in event:
                    result = event
            if self.process.returncode or result is None:
                raise RuntimeError(self.secrets.redact(error_path.read_text()[-3000:]))
        self.process = None
        paths = result["result"]
        if not all(Path(p).is_file() for p in paths.values()):
            raise RuntimeError("Worker result contains missing artifacts")
        manifest.write_text(
            json.dumps(
                {
                    "paths": paths,
                    "hashes": {kind: digest(path) for kind, path in paths.items()},
                    "seconds": result["seconds"],
                    "peak_mb": result["peak_mb"],
                    "stage": name,
                    "parameters": parameters,
                    "model": model,
                    "model_version": model_stamp,
                    "inputs": dependencies,
                }
            )
        )
        self.store.put(
            "benchmark",
            {
                "id": key,
                "stage": name,
                "seconds": result["seconds"],
                "peak_mb": result["peak_mb"],
                "parameters": parameters,
            },
        )
        return paths

    def kill_process(self):
        if self.process and self.process.poll() is None:
            if os.name != "nt":
                import signal

                os.killpg(self.process.pid, signal.SIGTERM)
            else:
                self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()

    def preparation(self, job):
        r = job["recipe"]
        paths = self.run_stage(
            job,
            "normalize",
            self.store.get("asset", job["source"])["path"],
            {"start": r["start"], "end": r["end"]},
        )
        clip = paths["normalized"]
        paths.update(
            self.run_stage(
                job,
                "audio",
                self.store.get("asset", job["source"])["path"],
                {"start": r["start"], "duration": r["end"] - r["start"]},
                trim_start=r["start"],
                duration=r["end"] - r["start"],
            )
        )
        if "original_audio" in paths and (r["audio"] == "original" or r["custom_mix_background"]):
            paths.update(self.run_stage(job, "vocals", paths["original_audio"], {}))
        if r["audio"] == "custom":
            paths.update(
                self.run_stage(
                    job,
                    "custom",
                    self.store.get("asset", r["custom_audio"])["path"],
                    {"mix": r["custom_mix_background"]},
                    duration=probe(clip)["duration"],
                    background=paths.get("background_audio"),
                )
            )
        else:
            if "original_audio" in paths:
                paths["final_audio"] = paths["original_audio"]
        voice = paths.get("custom_voice") or paths.get("vocals")
        if voice:
            paths.update(
                self.run_stage(
                    job, "pitch", voice, {"pitch": r["pitch"], "backend": r["pitch_backend"]}
                )
            )
        visual = clip
        if r["mode"] != "fast":
            paths.update(self.run_stage(job, "depth", clip, {}))
            paths.update(
                self.run_stage(
                    job,
                    "mask",
                    clip,
                    {
                        "subjects": [
                            {
                                "id": s["id"],
                                "annotations": s["annotations"],
                                "intervals": s.get("intervals", []),
                                "visibility": s.get("visibility", []),
                                "seed_frame": s.get("seed_frame"),
                            }
                            for s in r["subjects"]
                        ],
                        "profile": r["segmentation"],
                        "allow_empty_frames": r.get("allow_empty_frames", False),
                    },
                )
            )
            paths.update(
                self.run_stage(
                    job, "composite", clip, {}, mask_data=paths["mask_data"], depth=paths["depth"]
                )
            )
            visual = paths["composite"]
        if r["mode"] != "advanced":
            paths.update(self.run_stage(job, "mesh", visual, {}, tracking_source=clip))
            visual = paths["mesh"]
        paths.update(
            self.run_stage(job, "conditioning", visual, {}, audio=paths.get("conditioning_audio"))
        )
        if r["transcribe"] and voice:
            paths.update(self.run_stage(job, "whisper", voice, {}))
        if r["describe"]:
            paths.update(self.run_stage(job, "describe", clip, {}))
        artifacts = {
            kind: self.media.artifact(job, kind, path, "local preparation")["id"]
            for kind, path in paths.items()
        }
        self.store.update(
            "job",
            job["id"],
            {
                "status": "review",
                "stage": "review",
                "artifacts": artifacts,
                "progress": None,
                "approval": None,
            },
        )

    def export(self, job, data):
        a = self.store.get("attempt", data["attempt_id"])
        source = self.store.get("artifact", a["artifact"])["path"]
        paths = {}
        if data["route"] == "upscale":
            batch = int(
                os.environ.get(
                    "OPENJUTSU_SEED_BATCH_SIZE",
                    "13" if self.model_state["gpu"].get("total_mb", 0) >= 15000 else "5",
                )
            )
            if batch not in {5, 9, 13}:
                raise Conflict("Choose a tested temporal batch size: 5, 9 or 13")
            options = {"batch_size": batch} if data["upscaler"] == "seedvr2" else {}
            paths.update(
                self.run_stage(
                    job,
                    data["upscaler"],
                    source,
                    {"upscaler": data["upscaler"], **options},
                    **options,
                )
            )
            source = paths["upscaled"]
        soundtrack = (
            self.store.get("artifact", job["artifacts"]["final_audio"])["path"]
            if "final_audio" in job["artifacts"]
            else None
        )
        count = round((job["recipe"]["end"] - job["recipe"]["start"]) * 24)
        size = None
        if data["route"] != "original":
            reference = self.store.get("artifact", job["artifacts"]["normalized"])["metadata"]
            ratio = reference["width"] / reference["height"]
            size = (
                [round(1080 * ratio / 2) * 2, 1080]
                if ratio >= 1
                else [1080, round(1080 / ratio / 2) * 2]
            )
        options = {"frame_count": count, "delivery_size": size}
        paths.update(self.run_stage(job, "export", source, options, audio=soundtrack, **options))
        outputs = {
            k: self.media.artifact(
                job,
                k,
                p,
                "upscaled 1080p"
                if data["route"] == "upscale"
                else "native 1080p continuation"
                if data["route"] == "native" or a.get("parent")
                else "original generation",
            )["id"]
            for k, p in paths.items()
        }
        artifacts = {**job["artifacts"], **outputs}
        self.store.update(
            "job",
            job["id"],
            {
                "status": "complete",
                "stage": "export",
                "artifacts": artifacts,
                "progress": None,
                "export_route": data["route"],
            },
        )

    def work_loop(self):
        while not self.stop_event.is_set():
            task = self.store.claim()
            if not task:
                self.stop_event.wait(0.3)
                continue
            try:
                job = self.store.get("job", task["job"])
                if job["cancel"]:
                    raise InterruptedError("Job cancelled")
                self.store.update(
                    "job",
                    job["id"],
                    {"status": "preparing" if task["kind"] == "prepare" else "exporting"},
                )
                if task["kind"] == "prepare":
                    self.preparation(job)
                else:
                    self.export(job, task["data"])
                self.store.task_done(task["id"])
            except Exception as e:
                if self.stop_event.is_set():
                    self.store.task_done(task["id"], "queued")
                    self.store.update("job", task["job"], {"status": "queued", "progress": None})
                else:
                    self.store.task_done(task["id"], "failed")
                    self.store.update(
                        "job",
                        task["job"],
                        {
                            "status": "cancelled" if isinstance(e, InterruptedError) else "failed",
                            "error": self.secrets.redact(str(e)),
                            "progress": None,
                        },
                    )

    def submit_attempt(self, a):
        provider = None
        submitted = False
        try:
            settings = self.secrets.read().get(a["provider"], {})
            if account(settings) != a["account"]:
                raise Rejected("Restore the original provider account credentials")
            provider = Provider(a["provider"], settings)
            parent = self.store.get("attempt", a["parent"]) if a["parent"] else None
            if parent:
                payload = provider.payload(a["recipe_snapshot"], "", [], parent)
            else:
                clip = self.store.get("artifact", a["conditioning"])
                video = self.uploads.put(clip["path"], a["id"], provider)
                refs = []
                for s in sorted(a["recipe_snapshot"]["subjects"], key=lambda s: s["id"]):
                    if s["kind"] == "human" and a["provider"] == "byteplus":
                        refs.append(s["portrait_asset"])
                    else:
                        for id in s["references"]:
                            asset = self.store.get("asset", id)
                            refs.append(
                                self.uploads.put(
                                    asset.get("reference", asset["path"]), a["id"], provider
                                )
                            )
                payload = provider.payload(
                    a["recipe_snapshot"], video, refs, media=clip["metadata"]
                )
            submitted = True
            remote = provider.submit(payload, native=bool(parent))
            self.store.update("attempt", a["id"], {"status": "pending", "remote_id": remote})
        except Exception as e:
            uncertain = isinstance(e, Ambiguous) or (submitted and not isinstance(e, Rejected))
            self.store.update(
                "attempt",
                a["id"],
                {
                    "status": "unknown_submission" if uncertain else "failed",
                    "error": self.secrets.redact(str(e)),
                },
            )
            self.store.update(
                "job",
                a["job"],
                {
                    "status": "failed",
                    "error": "Submission uncertain; reconcile its provider request"
                    if uncertain
                    else self.secrets.redact(str(e)),
                },
            )
            if not uncertain:
                self.store.settle(a["id"], failed=True)
        finally:
            if provider:
                provider.close()

    def poll_attempt(self, a):
        settings = self.secrets.read().get(a["provider"], {})
        if account(settings) != a["account"]:
            return
        provider = Provider(a["provider"], settings)
        try:
            result = provider.poll(a["remote_id"])
            if result["status"] == "failed":
                self.store.update("attempt", a["id"], result)
                self.store.settle(a["id"], result.get("cost"))
                self.store.update("job", a["job"], {"status": "failed", "error": result["error"]})
            elif result["status"] == "succeeded":
                folder = self.config.root / "jobs" / a["job"] / a["id"]
                folder.mkdir(parents=True, exist_ok=True)
                path = folder / "generation.mp4"
                provider.download(result["url"], path)
                job = self.store.get("job", a["job"])
                artifact = self.media.artifact(
                    job,
                    "generation",
                    path,
                    a["provider"] + (" native 1080p" if a["parent"] else " 480p"),
                )
                from .media import mux

                soundtrack = (
                    self.store.get("artifact", job["artifacts"]["final_audio"])["path"]
                    if "final_audio" in job["artifacts"]
                    else None
                )
                mux(path, soundtrack, folder / "preview.mp4", browser=True)
                preview = self.media.artifact(
                    job, "preview", folder / "preview.mp4", "original/custom audio restored"
                )
                self.store.update(
                    "attempt",
                    a["id"],
                    {
                        "status": "succeeded",
                        "artifact": artifact["id"],
                        "preview": preview["id"],
                        "draft_id": result.get("draft_id") if not a["parent"] else None,
                        "draft_expires": time.time() + 7 * 86400
                        if result.get("draft_id")
                        else None,
                        "usage": result.get("usage"),
                        "usage_estimate_usd": result.get("usage_estimate_usd"),
                        "downloaded": True,
                    },
                )
                self.store.settle(a["id"], result.get("cost"))
                self.store.update(
                    "job",
                    a["job"],
                    {
                        "status": "preview",
                        "stage": "export" if a["parent"] else "generate",
                        "error": None,
                    },
                )
                if a["parent"]:
                    self.store.enqueue(
                        a["job"], "export", {"attempt_id": a["id"], "route": "native"}
                    )
            else:
                self.store.update("attempt", a["id"], {"progress": result.get("progress")})
        finally:
            provider.close()

    def cloud_loop(self):
        while not self.stop_event.is_set():
            for a in self.store.list("attempt"):
                try:
                    if a["status"] == "submitting":
                        self.submit_attempt(a)
                    elif a["status"] == "pending":
                        self.poll_attempt(a)
                except Exception:
                    # A status/download failure never creates a new paid request.
                    self.store.update(
                        "attempt",
                        a["id"],
                        {"poll_error": "Status or download unavailable; continuing reconciliation"},
                    )
            try:
                self.uploads.cleanup()
            except Exception:
                pass
            self.stop_event.wait(5)
