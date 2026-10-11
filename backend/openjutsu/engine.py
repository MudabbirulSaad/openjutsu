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
            self.process.terminate()
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
        if r["transcribe"]:
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
            if r["mode"] != "fast" and not any(
                a["frame"] == 0 and (a["points"] or a["box"]) for a in s["annotations"]
            ):
                raise Conflict("Anchor each subject on the first normalized frame")
            if any(a["frame"] >= round((r["end"] - r["start"]) * 24) for a in s["annotations"]):
                raise Conflict("A correction frame is beyond the selected clip")
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
        key = fingerprint(
            {
                "version": 1,
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
            if all(Path(path).is_file() for path in result["paths"].values()):
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

            def drain():
                for line in self.process.stdout:
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
            json.dumps({"paths": paths, "seconds": result["seconds"], "peak_mb": result["peak_mb"]})
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
        paths.update(self.run_stage(job, "audio", clip, {}))
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
                            {"id": s["id"], "annotations": s["annotations"]} for s in r["subjects"]
                        ],
                        "profile": r["segmentation"],
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
            paths.update(
                self.run_stage(job, data["upscaler"], source, {"upscaler": data["upscaler"]})
            )
            source = paths["upscaled"]
        soundtrack = (
            self.store.get("artifact", job["artifacts"]["final_audio"])["path"]
            if "final_audio" in job["artifacts"]
            else None
        )
        paths.update(self.run_stage(job, "export", source, {}, audio=soundtrack))
        outputs = {
            k: self.media.artifact(
                job, k, p, "upscaled 1080p" if data["route"] == "upscale" else "original generation"
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
            job = self.store.get("job", a["job"])
            parent = self.store.get("attempt", a["parent"]) if a["parent"] else None
            if parent:
                payload = provider.payload(job["recipe"], "", [], parent)
            else:
                clip = self.store.get("artifact", job["artifacts"]["conditioning"])
                video = self.uploads.put(clip["path"], a["id"])
                refs = []
                for s in job["recipe"]["subjects"]:
                    if s["kind"] == "human" and a["provider"] == "byteplus":
                        refs.append(s["portrait_asset"])
                    else:
                        for id in s["references"]:
                            refs.append(
                                self.uploads.put(self.store.get("asset", id)["path"], a["id"])
                            )
                payload = provider.payload(job["recipe"], video, refs)
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
                self.store.settle(a["id"], failed=True)
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
