# Video findings

Source: Sirio, **Dear Higgsfield, I reverse engineered you in 12 hours**, 9 October 2026, 21:46. [Original video](https://www.youtube.com/watch?v=d6spCMcfkew). Research checked 11 October 2026.

| Time | Demonstration | Implementation decision |
|---|---|---|
| 02:30 | A wrapper sells a workflow rather than its underlying model | Independent orchestration and provider contracts |
| 03:35 | The creator attributes blocks to faces and music | Record this as a claim, not an exhaustive provider policy |
| 04:24 | Depth preserves structure while removing RGB appearance | Local Video Depth Anything Small; retain numerical depth |
| 05:16 | Muting loses vocal conditioning; CapCut pitch and vocal isolation | Demucs followed by duration-preserving +3 semitones |
| 08:18 | Draft first, then finish through the saved task ID | Persist provider/account/draft identity and expiry |
| 10:42 | Depth-only generation retains an unwanted body and gray environment | Whole-character prompt, reference photos, environment context, and composite review |
| 12:20 | Cut depth subjects over the original RGB background | Per-subject frame-indexed masks; explicit correction frames |
| 14:04 | Eleven-stage automation with preparation and final approval | Durable jobs; approvals bind to immutable revisions |
| 18:23 | Fast face mesh; best for one talking subject | MediaPipe landmarks, blendshapes, and tracking-gap reporting |
| 20:12 | Face mesh over the depth composite | Combined preparation mode |
| 20:43 | Add transcription, motion descriptions, and own voice | Local assistance, editable suggestions, conditioning/final audio agreement |

## What is established

The [creator implementation](https://github.com/sirioberati/Genjustsu-Open-Source-Workflow) contains audio separation, +3-semitone Rubber Band processing, depth/SAM compositing, mesh modes, draft continuation, and original-audio restoration. Its fast RGB mesh retains recognizable source appearance. The exported voice and music remain the source soundtrack unless deliberately replaced.

[Higgsfield describes motion transfer and object swap](https://higgsfield.ai/blog/higgsfield-genjutsu), but does not establish use of this exact internal pipeline. No published source establishes guaranteed filter avoidance or exact motion reproduction. Provider rejection is not a trigger for automated transformed resubmission.

## Provider comparison

Published estimates for 5s source + 5s output, 16:9, USD; not paid tests:

| Route | Estimate | Limitation |
|---|---:|---|
| [ArgoLink 480p with video input](https://argolink.io/en/models/seedance-2.5) | $0.523 | No native draft continuation; multi-reference accepts conditioning video and photos |
| [Segmind draft](https://www.segmind.com/models/seedance-2.5/pricing) + [final](https://www.segmind.com/models/seedance-2.5-draft-final/pricing) | $2.40 | Published final discount needs settled-charge validation |
| [BytePlus draft + final](https://docs.byteplus.com/en/docs/modelark/model-pricing) | $4.02 | Native continuation retains input-video billing |
| Enhancor | Unverified | Dashboard contract and current rates require verification |

BytePlus has a [documented authorized portrait route](https://docs.byteplus.com/en/docs/modelark/seedance-portrait-asset-guide); reseller portrait authorization is not inferred from URL fields. Same-task continuation remains on the originating account. Segmind asynchronous result bodies expire after one hour. Preserve results immediately.

## Public provenance

The original recording, full transcript, extracted frames, and example characters remain local. Application licensing does not grant rights to the source media. TEIN branding is excluded. Documentation paraphrases and cites the sources.
