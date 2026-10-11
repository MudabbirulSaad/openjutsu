# Application API and CLI

The localhost API serves both the studio and CLI. Interactive schemas are at `http://127.0.0.1:9780/docs` and the machine schema at `/openapi.json`. This is a personal application: do not expose it to a LAN or reverse proxy without adding authentication and a separate security review.

```bash
runtime="$HOME/.local/share/openjutsu"
"$runtime/api-venv/bin/openjutsu" import-video /path/to/video.mp4 --name "New scene"
"$runtime/api-venv/bin/openjutsu" status JOB_ID
# Explicit request JSON, e.g. {"revision": 1}:
"$runtime/api-venv/bin/openjutsu" action JOB_ID prepare request.json
"$runtime/api-venv/bin/openjutsu" edit JOB_ID recipe-request.json
"$runtime/api-venv/bin/openjutsu" quotes JOB_ID --finish native
"$runtime/api-venv/bin/openjutsu" accept JOB_ID ATTEMPT_ID REVISION
```

| Operation | Endpoint |
|---|---|
| Import media | `POST /api/assets` multipart `file`; immutable local copy, max 2 GiB |
| Create / read jobs | `POST /api/jobs`, `GET /api/jobs`, `GET /api/jobs/{id}` |
| Edit recipe | `PUT /api/jobs/{id}/recipe` with `revision`, `recipe` |
| Prepare / approve | `POST /api/jobs/{id}/prepare`, `/approve` with `revision` |
| Quote / submit preview | `GET /api/jobs/{id}/quotes`, `POST …/previews` with `revision`, `quote_id`, unique `operation_id`, optional `pilot` |
| Accept preview | `POST /api/jobs/{id}/approve-preview/{attempt}` with `revision` |
| Finalize | `POST /api/jobs/{id}/finalize` with revision, attempt ID, route, operation ID; native also needs a current continuation quote and optional pilot |
| Cancel local work | `POST /api/jobs/{id}/cancel`; existing remote requests continue reconciliation |
| Reconcile | `POST /api/attempts/{id}/reconcile` with existing remote ID, confirmed-not-submitted flag, or settled charge |
| Inspect artifact | `GET /api/artifacts/{id}/content`, `/frames/{index}` |
| Exact source review | `GET /api/jobs/{id}/source-preview`, `/source-frames/{index}` |
| Save / export recipe | `POST /api/jobs/{id}/save-recipe`, `GET …/bundle` |
| Events | `GET /api/events?after=CURSOR` Server-Sent Events; reconnect with `Last-Event-ID` |
| Readiness / credentials | `GET /api/system`, `POST /api/settings/{provider-or-storage}` |

Coordinates are normalized to the contained video pixels, independent of letterboxing. An annotation contains `frame`, `points: [{x,y,include}]` and an optional ordered box `[left,top,right,bottom]`. Advanced supports three cast IDs. Optional subject `intervals: [{start,end}]` use inclusive start and exclusive end; each interval needs an anchor inside it and initializes a fresh SAM 2.1 track. Different subjects may overlap. `allow_empty_frames` records missing masks for human review instead of failing. Human ArgoLink references require `consent_confirmed`. `argolink_mode` defaults to `reference`; edit-plus-images is blocked while official contracts disagree.

Job responses include status, revision, artifacts, attempts, readiness, available actions, approval and budget/spent/reserved amounts. Backend transitions validate the request; browser state cannot authorize a stale revision. HTTP 409 means a conflicting revision, active operation, missing approval, expired quote or spending constraint. HTTP 422 means invalid inputs or a local processing error. Paid operations are never automatically retried by the CLI or browser.

`POST /api/jobs` and `PUT /api/jobs/{id}/budget` accept optional `generation_limit` (1–100). A set limit cannot be relaxed; omission preserves it. `available_actions.generate` reflects the limit. Quotes expose `request_mode` and `upload_retention_days`; attempts expose `usage_estimate_usd` separately from reconciled charges. `/api/system` reports per-provider `direct_upload` without exposing credentials.

Recipe bundles contain settings, artifact hashes, media metadata and producing model/stage provenance. They omit credentials and portrait asset identifiers. Reusable templates also omit references, annotations and custom audio; bind those to a new source. Recipes reproduce settings, not identical stochastic cloud results.
