import json
import os
from pathlib import Path

import httpx
import typer

app = typer.Typer(help="Local studio and the same job interface used by the browser.")


@app.command()
def serve(host: str = "127.0.0.1", port: int = 9780):
    if host not in {"localhost", "127.0.0.1", "::1"}:
        raise typer.BadParameter("Use a localhost address")
    import uvicorn

    from .api import create_app

    uvicorn.run(create_app(), host=host, port=port, timeout_graceful_shutdown=5)


@app.command()
def status(job: str = "", url: str = "http://127.0.0.1:9780"):
    response = httpx.get(url + ("/api/jobs/" + job if job else "/api/jobs"))
    response.raise_for_status()
    typer.echo(json.dumps(response.json(), indent=2))


@app.command()
def import_video(path: Path, name: str = "", url: str = "http://127.0.0.1:9780"):
    with path.open("rb") as f:
        response = httpx.post(url + "/api/assets", files={"file": (path.name, f)}, timeout=300)
    response.raise_for_status()
    source = response.json()
    response = httpx.post(
        url + "/api/jobs",
        json={
            "source": source["id"],
            "name": name or path.stem,
            "recipe": {"end": min(5, source["metadata"]["duration"])},
        },
    )
    response.raise_for_status()
    typer.echo(json.dumps(response.json(), indent=2))


@app.command()
def action(job: str, operation: str, body: Path, url: str = "http://127.0.0.1:9780"):
    """Submit an explicit JSON request; never auto-approve or auto-finalize."""
    if operation not in {"prepare", "approve", "previews", "finalize", "cancel", "save-recipe"}:
        raise typer.BadParameter("Unknown job action")
    response = httpx.post(
        f"{url}/api/jobs/{job}/{operation}", json=json.loads(body.read_text()), timeout=60
    )
    response.raise_for_status()
    typer.echo(json.dumps(response.json(), indent=2))


@app.command()
def doctor():
    from .config import Config
    from .models import readiness

    config = Config.environment()
    config.initialize()
    typer.echo(json.dumps(readiness(config), indent=2))
    typer.echo("Runtime: " + str(config.root))
    typer.echo(
        "FFmpeg: " + (os.getenv("PATH", "") and __import__("shutil").which("ffmpeg") or "missing")
    )


@app.command()
def accept(job: str, attempt: str, revision: int, url: str = "http://127.0.0.1:9780"):
    """Accept an inspected preview from an exact recipe revision."""
    response = httpx.post(
        f"{url}/api/jobs/{job}/approve-preview/{attempt}", json={"revision": revision}
    )
    response.raise_for_status()
    typer.echo(json.dumps(response.json(), indent=2))


@app.command()
def edit(job: str, body: Path, url: str = "http://127.0.0.1:9780"):
    """Save a recipe JSON containing revision and recipe; approval is invalidated."""
    response = httpx.put(f"{url}/api/jobs/{job}/recipe", json=json.loads(body.read_text()))
    response.raise_for_status()
    typer.echo(json.dumps(response.json(), indent=2))


@app.command()
def quotes(job: str, finish: str = "upscale", parent: str = "", url: str = "http://127.0.0.1:9780"):
    """Read finished-output quotes without submitting a paid request."""
    params = {"finish": finish}
    if parent:
        params["parent"] = parent
    response = httpx.get(f"{url}/api/jobs/{job}/quotes", params=params)
    response.raise_for_status()
    typer.echo(json.dumps(response.json(), indent=2))
