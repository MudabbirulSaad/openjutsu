import math
import time
from pathlib import Path

import httpx

from .store import fingerprint, identifier, money

CAPABILITIES = {
    "byteplus": {
        "native": True,
        "portraits": True,
        "max_mb": 200,
        "base": "https://ark.ap-southeast.bytepluses.com/api/v3",
        "model": "dreamina-seedance-2-5-260628",
    },
    "segmind": {
        "native": True,
        "portraits": False,
        "max_mb": 200,
        "base": "https://api.segmind.com/v2",
        "model": "seedance-2.5",
    },
    "argolink": {
        "native": False,
        "portraits": False,
        "max_mb": 100,
        "base": "https://argolink.io/v1",
        "model": "seedance-2.5",
    },
}


class Rejected(Exception):
    pass


class Ambiguous(Exception):
    pass


def estimate(provider, duration, width, height, native=False):
    ratio = width / height
    short = 1080 if native else 480
    w, h = (
        (round(short * ratio / 2) * 2, short)
        if ratio >= 1
        else (short, round(short / ratio / 2) * 2)
    )
    tokens_per_second = w * h * 24 / 1024
    if provider == "argolink":
        return duration * 2 * (0.289 if native else 0.0523)
    if provider == "segmind":
        seconds = duration if native else duration + max(duration, math.ceil(2 * duration / 3))
        return tokens_per_second * seconds * (7.18 if native else 6.56) / 1e6
    return tokens_per_second * duration * 2 * (7 if native else 6.4) / 1e6


def account(settings):
    return fingerprint(
        {"api_key": settings.get("api_key", ""), "account": settings.get("account", "default")}
    )


def qualification_profile(provider, recipe, native=False):
    return fingerprint(
        {
            "model": CAPABILITIES[provider]["model"],
            "mode": recipe["mode"],
            "subjects": [s["kind"] for s in sorted(recipe["subjects"], key=lambda s: s["id"])],
            "phase": "native" if native else "preview",
        }
    )


class Provider:
    def __init__(self, name, settings, transport=None):
        self.name, self.settings = name, settings
        self.cap = CAPABILITIES[name]
        headers = (
            {"x-api-key": settings["api_key"]}
            if name == "segmind"
            else {"Authorization": "Bearer " + settings["api_key"]}
        )
        self.client = httpx.Client(
            base_url=self.cap["base"], headers=headers, timeout=60, transport=transport
        )

    def payload(self, recipe, video_url, references, parent=None):
        if parent:
            if not self.cap["native"]:
                raise Rejected("This provider cannot continue drafts")
            if self.name == "segmind":
                return {"draft_task_id": parent["draft_id"], "output_codec": "auto"}
            return {
                "model": self.cap["model"],
                "content": [{"type": "draft_task", "draft_task": {"id": parent["draft_id"]}}],
                "resolution": "1080p",
            }
        prompt = recipe["prompt"]
        mappings = []
        index = 1
        for subject in recipe["subjects"]:
            n = (
                1
                if subject.get("portrait_asset") and self.name == "byteplus"
                else len(subject["references"])
            )
            if n:
                mappings.append(
                    f"Replace subject {subject['id']} completely with "
                    + ", ".join(f"@Image {x}" for x in range(index, index + n))
                    + "."
                )
                index += n
        prompt = " ".join([prompt, *mappings])
        if self.name == "argolink":
            return {
                "model": "seedance-2.5",
                "omni_reference_task_type": "edit",
                "prompt": prompt,
                "resolution": "480p",
                "reference_videos": [{"url": video_url}],
                "reference_images": [{"url": x} for x in references],
                "generate_audio": True,
            }
        if self.name == "segmind":
            return {
                "prompt": prompt,
                "reference_videos": [video_url],
                "reference_images": references,
                "duration": -1,
                "aspect_ratio": "adaptive",
                "resolution": "480p",
                "draft": True,
                "bitrate_mode": "high",
                "generate_audio": True,
                "skip_moderation": False,
            }
        return {
            "model": self.cap["model"],
            "content": [
                {"type": "text", "text": prompt},
                {"type": "video_url", "video_url": {"url": video_url}, "role": "reference_video"},
                *[
                    {"type": "image_url", "image_url": {"url": x}, "role": "reference_image"}
                    for x in references
                ],
            ],
            "omni_reference_task_type": "edit",
            "duration": -1,
            "ratio": "adaptive",
            "resolution": "480p",
            "draft": True,
            "generate_audio": True,
        }

    def submit(self, payload, native=False):
        endpoint = (
            "/contents/generations/tasks"
            if self.name == "byteplus"
            else "/seedance-2.5-draft-final"
            if self.name == "segmind" and native
            else "/seedance-2.5"
            if self.name == "segmind"
            else "/videos/generations"
        )
        try:
            response = self.client.post(endpoint, json=payload)
        except httpx.TransportError as e:
            raise Ambiguous("Submission connection failed; reconcile before retrying") from e
        if response.status_code >= 500:
            raise Ambiguous("Provider could have accepted the request; reconcile its dashboard")
        if response.status_code >= 400:
            raise Rejected(
                f"Provider rejected submission (HTTP {response.status_code}); inspect its dashboard"
            )
        try:
            data = response.json()
            id = data.get("request_id") or data.get("id")
            if not id:
                raise ValueError()
            return str(id)
        except ValueError as e:
            raise Ambiguous("Provider response lacks a request ID; reconcile its dashboard") from e

    def poll(self, remote):
        url = (
            f"/contents/generations/tasks/{remote}"
            if self.name == "byteplus"
            else f"/requests/{remote}/status"
            if self.name == "segmind"
            else f"/videos/{remote}"
        )
        response = self.client.get(url)
        response.raise_for_status()
        data = response.json()
        status = str(data.get("status", "pending")).lower()
        if status in {"failed", "expired", "cancelled"}:
            return {
                "status": "failed",
                "cost": data.get("cost"),
                "error": "Provider reported failure or expiry; inspect its dashboard",
            }
        if status not in {"succeeded", "completed", "done"}:
            return {"status": "pending", "progress": data.get("progress")}
        if self.name == "segmind":
            response = self.client.get(f"/requests/{remote}")
            response.raise_for_status()
            data = response.json()
        output = data.get("output", data)
        if isinstance(output, list):
            output = output[0]
        if not isinstance(output, dict):
            output = {"url": output}
        video = output.get("video", data.get("video", {}))
        if isinstance(video, str):
            video = {"url": video}
        content = data.get("content", {})
        url = video.get("url") or output.get("url") or content.get("video_url")
        draft = (
            video.get("draft_task_id")
            or data.get("draft_task_id")
            or output.get("draft_task_id")
            or response.headers.get("X-Draft-Task-ID")
        )
        cost = data.get("cost") or output.get("cost") or response.headers.get("x-cost")
        if self.name == "argolink":
            url = self.cap["base"] + f"/videos/{remote}/content"
            billed = data.get("usage", {}).get("billed_seconds")
            cost = float(billed) * 0.0523 if billed is not None else cost
        if self.name == "byteplus":
            draft = remote
        return {
            "status": "succeeded",
            "url": url,
            "draft_id": draft,
            "cost": float(cost) if cost is not None else None,
            "usage": data.get("usage"),
        }

    def download(self, url, path):
        if not url or not url.startswith("https://"):
            raise Rejected("Provider did not return a secure result URL")
        # Only the Argo content endpoint receives its account credential.
        client = (
            self.client
            if self.name == "argolink" and url.startswith(self.cap["base"] + "/videos/")
            else httpx.Client(timeout=120)
        )
        try:
            with client.stream("GET", url, follow_redirects=True) as response:
                response.raise_for_status()
                with open(path, "wb") as f:
                    for block in response.iter_bytes():
                        f.write(block)
        finally:
            if client is not self.client:
                client.close()

    def close(self):
        self.client.close()


class Uploads:
    def __init__(self, secrets, store):
        self.secrets, self.store = secrets, store

    def client(self):
        import boto3

        s = self.secrets.read().get("storage", {})
        if not all(s.get(k) for k in ("bucket", "endpoint", "access_key", "secret_key")):
            raise Rejected("Configure private S3-compatible media storage")
        if not s["endpoint"].startswith("https://"):
            raise Rejected("Storage endpoint must use HTTPS")
        return boto3.client(
            "s3",
            endpoint_url=s["endpoint"],
            aws_access_key_id=s["access_key"],
            aws_secret_access_key=s["secret_key"],
            region_name=s.get("region", "auto"),
        ), s

    def put(self, path, attempt):
        import mimetypes

        client, settings = self.client()
        key = f"openjutsu/{attempt}/{identifier()}{Path(path).suffix}"
        client.upload_file(
            str(path),
            settings["bucket"],
            key,
            ExtraArgs={
                "ContentType": mimetypes.guess_type(str(path))[0] or "application/octet-stream"
            },
        )
        self.store.put(
            "upload",
            {
                "id": identifier(),
                "key": key,
                "bucket": settings["bucket"],
                "storage": fingerprint(settings),
                "expires": time.time() + 86400,
            },
        )
        return client.generate_presigned_url(
            "get_object", Params={"Bucket": settings["bucket"], "Key": key}, ExpiresIn=3600
        )

    def cleanup(self):
        records = [
            r
            for r in self.store.list("upload")
            if r["expires"] < time.time() and not r.get("deleted")
        ]
        if not records:
            return
        client, settings = self.client()
        for r in records:
            if r["storage"] == fingerprint(settings):
                client.delete_object(Bucket=r["bucket"], Key=r["key"])
                self.store.update("upload", r["id"], {"deleted": True})


def make_quotes(store, secrets, job, native_parent=None):
    clip = store.get("artifact", job["artifacts"]["conditioning"])
    m = clip["metadata"]
    settings = secrets.read()
    quotes = []
    for name, cap in CAPABILITIES.items():
        config = settings.get(name, {})
        reason = None
        if not config.get("api_key"):
            reason = "Configure provider credentials"
        elif not settings.get("storage", {}).get("bucket"):
            reason = "Configure private media storage"
        elif Path(clip["path"]).stat().st_size > cap["max_mb"] * 1024 * 1024:
            reason = "Prepared clip exceeds provider upload limit"
        elif not 0.4 <= m["width"] / m["height"] <= 2.5:
            reason = "Clip aspect ratio is outside provider limits"
        elif any(
            s["kind"] == "human"
            and (not cap["portraits"] or not (s.get("portrait_asset") or "").startswith("asset://"))
            for s in job["recipe"]["subjects"]
        ):
            reason = "Authorized portrait assets are required; reseller support is unverified"
        elif job["recipe"]["mode"] == "fast" and any(
            s["kind"] == "human" for s in job["recipe"]["subjects"]
        ):
            reason = "RGB mesh conditioning requires a separately authorized video route; use Advanced mode"
        if native_parent:
            if name != native_parent["provider"] or account(config) != native_parent["account"]:
                continue
            if (
                not cap["native"]
                or not native_parent["draft_id"]
                or (native_parent["draft_expires"] or 0) <= time.time()
            ):
                reason = "Native draft continuation is unavailable or expired"
        cost = estimate(name, m["duration"], m["width"], m["height"], bool(native_parent))
        qualification = next(
            (
                q
                for q in store.list("qualification")
                if q["provider"] == name
                and q["account"] == account(config)
                and q.get("profile")
                == qualification_profile(name, job["recipe"], bool(native_parent))
            ),
            None,
        )
        q = {
            "id": identifier(),
            "job": job["id"],
            "revision": job["revision"],
            "provider": name,
            "account": account(config),
            "eligible": not reason,
            "qualified": qualification is not None,
            "reason": reason or (None if qualification else "Qualification pilot required"),
            "estimate": round(cost, 6),
            "reserve": money(round(cost * 1.2 + 0.05, 6)),
            "currency": "USD",
            "expires": time.time() + 600,
            "native": cap["native"],
            "parent": native_parent["id"] if native_parent else None,
            "pricing_checked": "2026-10-11",
        }
        store.put("quote", q)
        quotes.append(q)
    return sorted(quotes, key=lambda q: (not q["eligible"], not q["qualified"], q["estimate"]))
