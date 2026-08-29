# Frame extraction and the VLM boundary

Frame extraction is a separate stage because it turns a large local video into small, timestamped visual evidence that can be reviewed, stored, and analyzed later without coupling a future VLM to video decoding.

`extract-frames` reads an existing run and its `scenes.json`, never copies the source video, and writes images under `workspace/runs/<run_id>/frames/` plus `workspace/runs/<run_id>/frames.json`.

Each JSON `ExtractedFrame` has a stable frame ID, source ID, integer-millisecond timestamp, optional scene ID, image format, and an `ArtifactRef` for the locally extracted image.

## Sampling

- `interval` (default) samples from 0 at a configurable millisecond interval and associates a scene where one contains that timestamp.
- `scene-relative` samples configured relative offsets per scene; the initial default is each scene midpoint (`0.5`).

Configuration is available through the optional `[frame_extraction]` table or CLI flags. Existing valid frame metadata and image files are reused. `--force` re-extracts the stage-owned frame paths and atomically replaces `frames.json`.

## Future VLM adapter

`adapters/vlm/contracts.py` defines `VisualAnalysisRequest` and `VisualAnalyzer`. The request carries `ExtractedFrame` evidence plus optional scene, transcript, and instruction context. The adapter returns existing `VisualObservation` models; frame-level evidence is carried in the observation's flexible JSON metadata (for example `frame_ids`).

This is deliberately only a provider-neutral boundary. It does not download a model, generate prompts, call any service, or perform video reasoning. Local, RunPod/vLLM, and later backends can implement the same protocol.

Sampling choices, image quality, and the metadata convention for frame IDs are provisional.
