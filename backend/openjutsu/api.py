import asyncio
import json
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import Config
from .engine import Engine
from .media import normalize, probe
from .models import readiness
from .providers import CAPABILITIES, account, make_quotes
from .store import Conflict, Store, fingerprint, identifier, money
from .types import (
    CreateJob,
    FinalizeRequest,
    PreviewRequest,
    Qualification,
    Reconcile,
    Revision,
    UpdateRecipe,
)


class Budget(BaseModel):
    budget_usd: float = Field(ge=0, le=10000)


class Settings(BaseModel):
    values: dict[str, str]


def public_record(record):
    return {
        k: v for k, v in record.items() if k not in {"path", "poster", "account", "operation_id"}
    }


def create_app(config=None, start_workers=True):
    config = config or Config.environment()
    config.initialize()
    store = Store(config.root)
    engine = Engine(config, store)

    @asynccontextmanager
    async def lifespan(app):
        if start_workers:
            engine.start()
        yield
        if start_workers:
            engine.stop()

    app = FastAPI(title="OpenJutsu", version="0.1.0a1", lifespan=lifespan)
    app.state.store, app.state.engine = store, engine

    @app.middleware("http")
    async def origin_guard(request, call_next):
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            if origin:
                from urllib.parse import urlparse

                if urlparse(origin).hostname not in {"localhost", "127.0.0.1", "::1"}:
                    return JSONResponse(
                        {"detail": "Local browser origin required"}, status_code=403
                    )
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = (
            "no-store" if request.url.path.startswith("/api") else "no-cache"
        )
        return response

    @app.exception_handler(Conflict)
    async def conflict(_, exception):
        return JSONResponse({"detail": str(exception)}, status_code=409)

    @app.exception_handler(KeyError)
    async def missing(_, exception):
        return JSONResponse({"detail": str(exception)}, status_code=404)

    @app.exception_handler(ValueError)
    async def invalid(_, exception):
        return JSONResponse({"detail": str(exception)}, status_code=422)

    def view(id):
        job = store.get("job", id)
        artifacts = {
            k: public_record(store.get("artifact", a)) for k, a in job["artifacts"].items()
        }
        attempts = [public_record(a) for a in store.list("attempt") if a["job"] == id]
        missing = [
            m
            for m in engine.required_models(job)
            if not engine.model_state["models"].get(m, {}).get("ready")
        ]
        busy = job["status"] in {"queued", "preparing", "generating", "exporting"}
        unknown = any(a["status"] in {"submitting", "unknown_submission"} for a in attempts)
        return {
            **job,
            "source_asset": public_record(store.get("asset", job["source"])),
            "artifacts": artifacts,
            "attempts": attempts,
            "required_models": missing,
            "available_actions": {
                "edit": not busy and not unknown,
                "prepare": not busy
                and not unknown
                and not missing
                and engine.model_state["gpu"]["available"],
                "approve": job["status"] == "review",
                "generate": bool(job["approval"]) and not busy and not unknown,
                "export": bool(job["preview_approval"]) and not busy and not unknown,
                "cancel": busy,
            },
            "budget_usd": job["budget"] / 1e6,
            "spent_usd": job["spent"] / 1e6,
            "reserved_usd": job["reserved"] / 1e6,
        }

    @app.get("/api/system")
    def system(refresh: bool = False):
        if refresh:
            engine.model_state = readiness(config)
        settings = engine.secrets.read()
        return {
            **engine.model_state,
            "worker_active": engine.process is not None,
            "providers": {
                k: {
                    "configured": bool(settings.get(k, {}).get("api_key")),
                    "native": v["native"],
                    "portraits": v["portraits"],
                    "qualified": any(
                        q["provider"] == k and q["account"] == account(settings.get(k, {}))
                        for q in store.list("qualification")
                    ),
                }
                for k, v in CAPABILITIES.items()
            },
            "storage_configured": bool(settings.get("storage", {}).get("bucket")),
            "benchmarks": store.list("benchmark"),
        }

    @app.post("/api/settings/{key}")
    def settings(key: str, body: Settings):
        allowed = (
            {"api_key", "account"}
            if key in CAPABILITIES
            else {"bucket", "endpoint", "access_key", "secret_key", "region"}
            if key == "storage"
            else set()
        )
        if not allowed or not set(body.values) <= allowed:
            raise ValueError("Unknown settings fields")
        if any(len(v) > 2000 for v in body.values.values()):
            raise ValueError("Setting is too long")
        engine.secrets.update(key, body.values)
        return {"configured": True}

    @app.post("/api/assets")
    async def upload(file: UploadFile = File(...)):
        path = (
            config.root / "assets" / (identifier() + Path(file.filename or "file").suffix.lower())
        )
        size = 0
        try:
            with path.open("wb") as destination:
                while block := await file.read(1024 * 1024):
                    size += len(block)
                    if size > 2 * 1024**3:
                        raise HTTPException(413, "Import is limited to 2 GiB")
                    destination.write(block)
            asset = await asyncio.to_thread(
                engine.media.import_file, path, Path(file.filename or "file").name
            )
            return public_record(asset)
        finally:
            path.unlink(missing_ok=True)
            await file.close()

    @app.get("/api/assets")
    def assets():
        return [public_record(a) for a in store.list("asset")]

    @app.get("/api/assets/{id}/content")
    def asset_content(id: str, poster: bool = False):
        a = store.get("asset", id)
        return FileResponse(a.get("poster", a["path"]) if poster else a["path"])

    @app.post("/api/jobs")
    def create(body: CreateJob):
        source = store.get("asset", body.source)
        if source["kind"] != "video":
            raise ValueError("Select a video source")
        if body.recipe.end > source["metadata"]["duration"] + 0.01:
            raise ValueError("Trim end exceeds source duration")
        job = store.create_job(body)
        return view(job["id"])

    @app.get("/api/jobs")
    def jobs():
        return [view(j["id"]) for j in store.list("job")]

    @app.get("/api/jobs/{id}")
    def job(id: str):
        return view(id)

    @app.put("/api/jobs/{id}/recipe")
    def recipe(id: str, body: UpdateRecipe):
        store.recipe(id, body.revision, body.recipe.model_dump())
        return view(id)

    @app.put("/api/jobs/{id}/budget")
    def budget(id: str, body: Budget):
        store.budget(id, money(body.budget_usd))
        return view(id)

    def preview_path(id):
        j = store.get("job", id)
        source = store.get("asset", j["source"])
        r = j["recipe"]
        key = fingerprint(
            {"source": source["hash"], "start": r["start"], "end": r["end"], "preview": 1}
        )
        path = config.root / "cache" / (key + ".mp4")
        if not path.exists():
            normalize(source["path"], path, r["start"], r["end"])
        return path

    @app.get("/api/jobs/{id}/source-preview")
    def source_preview(id: str):
        path = preview_path(id)
        return FileResponse(path, media_type="video/mp4")

    @app.get("/api/jobs/{id}/source-frames/{frame}")
    def source_frame(id: str, frame: int):
        path = preview_path(id)
        image = engine.media.frame(
            {"path": str(path), "hash": path.stem, "metadata": probe(path)}, frame
        )
        return FileResponse(image, media_type="image/png")

    @app.post("/api/jobs/{id}/prepare")
    def prepare(id: str, body: Revision):
        engine.prepare(id, body.revision)
        return view(id)

    @app.post("/api/jobs/{id}/approve")
    def approve(id: str, body: Revision):
        store.approve(id, body.revision)
        return view(id)

    @app.post("/api/jobs/{id}/approve-preview/{attempt}")
    def approve_preview(id: str, attempt: str, body: Revision):
        store.approve(id, body.revision, attempt)
        return view(id)

    @app.get("/api/jobs/{id}/quotes")
    def quotes(id: str, parent: str | None = None):
        j = store.get("job", id)
        if "conditioning" not in j["artifacts"]:
            return []
        a = store.get("attempt", parent) if parent else None
        if a and a["job"] != id:
            raise Conflict("Attempt belongs to another job")
        return [public_record(q) for q in make_quotes(store, engine.secrets, j, a)]

    @app.post("/api/jobs/{id}/previews")
    def preview(id: str, body: PreviewRequest):
        q = store.get("quote", body.quote_id)
        if q["parent"]:
            raise Conflict("Use a preview quote, not a finalization quote")
        a = store.reserve_attempt(id, body.revision, q, body.operation_id, body.pilot)
        return public_record(a)

    @app.post("/api/jobs/{id}/finalize")
    def finalize(id: str, body: FinalizeRequest):
        j, a = store.get("job", id), store.get("attempt", body.attempt_id)
        store.check_revision(j, body.revision)
        if a["job"] != id or j["preview_approval"] != a["id"] or a["revision"] != j["revision"]:
            raise Conflict("Approve a successful preview from this revision")
        if body.route == "native":
            if not body.quote_id:
                raise Conflict("Choose a fresh native continuation quote")
            q = store.get("quote", body.quote_id)
            if (
                q["parent"] != a["id"]
                or q["provider"] != a["provider"]
                or q["account"] != a["account"]
            ):
                raise Conflict("Continuation must use the originating draft and account")
            result = store.reserve_attempt(id, body.revision, q, body.operation_id, parent=a["id"])
            return public_record(result)
        if body.route == "upscale" and not engine.model_state["models"].get(body.upscaler, {}).get(
            "ready"
        ):
            raise Conflict("Install and validate the selected local upscaler")
        store.enqueue(id, "export", body.model_dump())
        return view(id)

    @app.post("/api/jobs/{id}/cancel")
    def cancel(id: str):
        store.update("job", id, {"cancel": True})
        return view(id)

    @app.post("/api/attempts/{id}/reconcile")
    def reconcile(id: str, body: Reconcile):
        a = store.get("attempt", id)
        if body.confirmed_not_submitted:
            if a["status"] != "unknown_submission":
                raise Conflict("Only uncertain submissions may be marked not submitted")
            store.update(
                "attempt",
                id,
                {"status": "failed", "error": "User confirmed no provider submission"},
            )
            store.settle(id, failed=True)
        elif body.remote_id:
            if a["status"] != "unknown_submission":
                raise Conflict("Request already has a known submission state")
            if (
                not all(c.isalnum() or c in "-_" for c in body.remote_id)
                or len(body.remote_id) > 200
            ):
                raise ValueError("Invalid provider request identifier")
            store.update("attempt", id, {"remote_id": body.remote_id, "status": "pending"})
            store.update("job", a["job"], {"status": "generating", "error": None})
        if body.actual_cost_usd is not None:
            if a["status"] != "succeeded":
                raise Conflict("Settle billing only after a successful result")
            store.settle(id, body.actual_cost_usd)
        return public_record(store.get("attempt", id))

    @app.post("/api/providers/{name}/qualify")
    def qualify(name: str, body: Qualification):
        a = store.get("attempt", body.attempt_id)
        if a["provider"] != name or a["status"] != "succeeded" or not a["pilot"]:
            raise Conflict("Qualification requires a completed pilot from this provider")
        if not (
            body.policy_reviewed
            and min(body.identity, body.motion, body.temporal) >= 4
            and body.no_subject_swap
            and body.synchronized
        ):
            raise Conflict("Pilot does not meet the acceptance criteria")
        store.settle(a["id"], body.actual_cost_usd)
        store.put(
            "qualification",
            {
                "id": identifier(),
                "provider": name,
                "account": a["account"],
                "pilot": a["id"],
                "review": body.model_dump(),
                "time": time.time(),
            },
        )
        return {"qualified": True}

    @app.get("/api/artifacts/{id}/content")
    def artifact_content(id: str, download: bool = False):
        a = store.get("artifact", id)
        return FileResponse(
            a["path"],
            filename=f"openjutsu-{a['kind']}{Path(a['path']).suffix}" if download else None,
        )

    @app.get("/api/artifacts/{id}/frames/{frame}")
    def frame(id: str, frame: int):
        return FileResponse(
            engine.media.frame(store.get("artifact", id), frame), media_type="image/png"
        )

    @app.get("/api/recipes")
    def recipes():
        return store.list("template")

    @app.post("/api/jobs/{id}/save-recipe")
    def save_recipe(id: str):
        j = store.get("job", id)
        recipe = {
            **j["recipe"],
            "subjects": [
                {**s, "portrait_asset": None, "annotations": [], "references": []}
                for s in j["recipe"]["subjects"]
            ],
            "custom_audio": None,
            "audio": "original",
        }
        return store.put("template", {"id": identifier(), "name": j["name"], "recipe": recipe})

    @app.get("/api/jobs/{id}/bundle")
    def bundle(id: str):
        j = store.get("job", id)
        recipe = {
            **j["recipe"],
            "subjects": [{**s, "portrait_asset": None} for s in j["recipe"]["subjects"]],
        }
        return JSONResponse(
            {
                "version": 1,
                "name": j["name"],
                "recipe": recipe,
                "artifacts": [
                    {
                        "kind": a["kind"],
                        "hash": a["hash"],
                        "metadata": a["metadata"],
                        "producer": a["producer"],
                    }
                    for a in store.list("artifact")
                    if a["job"] == id
                ],
            },
            headers={"Content-Disposition": "attachment; filename=openjutsu-recipe.json"},
        )

    @app.get("/api/events")
    async def events(request: Request, after: int = 0):
        cursor = max(after, int(request.headers.get("last-event-id", "0")))

        async def stream():
            nonlocal cursor
            while not await request.is_disconnected():
                rows = store.events(cursor)
                for event in rows:
                    cursor = event["id"]
                    yield f"id: {cursor}\ndata: {json.dumps(event)}\n\n"
                if not rows:
                    yield ": heartbeat\n\n"
                await asyncio.sleep(1)

        return StreamingResponse(
            stream(), media_type="text/event-stream", headers={"X-Accel-Buffering": "no"}
        )

    dist = Path(__file__).resolve().parents[2] / "web" / "dist"
    if dist.exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="frontend-assets")

        @app.get("/{path:path}")
        def frontend(path: str):
            if path.startswith("api/"):
                raise HTTPException(404)
            return FileResponse(dist / "index.html")

    return app
