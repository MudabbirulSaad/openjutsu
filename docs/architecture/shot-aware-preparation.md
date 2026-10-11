# Shot-aware cast bindings

Advanced preparation supports three persistent cast IDs. Each subject may have ordered, non-overlapping `intervals` with integer `start` and exclusive `end` frames relative to the normalized 24 fps clip. Different subjects may overlap during camera transitions. An empty interval list retains the legacy whole-clip track.

Each interval requires a point or box anchor inside it; the anchor need not be its first frame. SAM 2.1 initializes a fresh state per subject and interval, and propagates both forward and backward from the first anchor. Corrections belong to that interval. A subject's output is zero outside its intervals. SAM 3 interval tracking is not yet enabled; mesh modes retain their single-subject limit.

`allow_empty_frames` defaults to false. Enabling it allows empty masks at transitions, with all empty frame indices recorded in the local `tracking` JSON artifact for human review. It does not establish that a missing mask is correct. Review source, mask, and composite together before approval. Interval and empty-frame changes participate in the mask cache key and invalidate recipe approval while reusing unaffected audio and depth.

The studio provides numeric interval controls and correction anchors, including keyboard alternatives. Cast images, annotations, tracking reports, and real test clips remain private runtime data.

Mask labels are atomically saved as uncompressed uint8 NPY arrays and memory-mapped during compositing. A local multi-frame round-trip reproduced CRC failures in compressed NPZ mask storage; uncompressed storage avoids that compression path. An 18-second 540×960 mask uses approximately 224 MB. Valid legacy NPZ masks remain readable, but the new mask cache version prevents reuse of older affected outputs. Hash checks still protect immutable cached artifacts.
