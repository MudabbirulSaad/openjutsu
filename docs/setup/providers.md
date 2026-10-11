# Provider setup and paid operations

No credential, paid cloud result, or provider qualification is shipped. The adapters implement published contracts checked on 2026-10-11; synthetic contract tests do not verify billing or generation quality. Rates and access can change. Inspect the current provider dashboard before a pilot.

1. Configure a provider API key and a stable account label in Settings. Keys are stored only in the Linux runtime `secrets.json` with mode 0600. Rotate keys at the provider; changing them intentionally changes the account fingerprint and requires restoring the original account for saved-task continuation.
2. Configure a private S3-compatible bucket, HTTPS endpoint, access/secret keys and region. Permit object upload, signed reads and deletion under `openjutsu/`. Keep public access blocked and set a one-day lifecycle rule. The application signs reads for one hour and removes objects after 24 hours while running; a lifecycle rule handles downtime.
3. Prepare and review the exact conditioning clip and references. Reference PNGs are orientation-corrected and stripped of EXIF. Upload approval is bound to the recipe revision and conditioning artifact.
4. Set a project spending limit and an account spending cap at the provider. Quotes include reference-video billing, output generation, and a reservation margin. Reservations are planning controls, not a guarantee that a provider cannot bill more.
5. Explicitly select a **paid qualification pilot**. Check settled charges, authorization policy, and quality. Record identity, motion and temporal stability scores ≥4/5 with no subject swaps or visible sync failures. Only then does that profile become eligible for normal generation.

The generation inspector quotes your finished-output plan: local upscale, native continuation, or original resolution. Native estimates include draft and final API costs; local upscaling shows API cost separately from unpriced local energy/time. Routes are sorted by the finished estimate among eligible, qualified profiles. Rejected attempts and prior spend remain in the project ledger.

| Provider | Implemented edit contract | Native continuation | Portrait handling |
|---|---|---|---|
| [BytePlus](https://docs.byteplus.com/en/docs/modelark/seedance-2-5) | ModelArk asynchronous task; 480p draft; adaptive edit duration | Original draft ID to 1080p, original account | [Authorized portrait asset route](https://docs.byteplus.com/en/docs/modelark/seedance-portrait-asset-guide); enroll upstream and enter `asset://…` |
| [Segmind](https://www.segmind.com/models/seedance-2.5) | v2 asynchronous requests; draft; moderation enabled | `seedance-2.5-draft-final`, saved `draft_task_id` | Reseller portrait enrollment not verified; real-person references remain blocked |
| [ArgoLink](https://argolink.io/en/models/seedance-2.5) | 480p omni edit; one video with embedded conditioning audio; image references | Not supported; local upscale or original resolution | Reseller portrait enrollment not verified; real-person references remain blocked |

Fast mode contains recognizable RGB footage. A separate authorized video route is needed for real-person RGB conditioning; it is not inferred from image-asset enrollment. The UI shows the exact media that would leave the PC. Refusals remain explicit failures and never trigger an automatic transformed resubmission.

Qualification is specific to provider/account, model, preparation mode, subject count/category and preview versus native output. A preview pilot does not qualify native finalization billing. Drafts generally expire after seven days; result URLs can expire sooner. Segmind asynchronous results have a short retention window, so the engine downloads them promptly.

Submission intent and the reserved cost are committed before contacting a provider. Returned IDs are saved immediately. A connection timeout or ambiguous server response changes the attempt to `unknown_submission` and keeps the reservation. Check the provider dashboard, attach its existing request ID, or explicitly confirm no request exists. Another paid submission is blocked until that uncertainty is reconciled. Status checks and downloads can retry; submission does not.

Settled charges remain distinct from estimates. If a completed or failed remote task reports no charge, its reservation remains held until the receipt is reconciled. The source, native generation, restored-audio preview and finalized exports have separate artifact records. Enhancor has no verified public contract here and is not enabled.
