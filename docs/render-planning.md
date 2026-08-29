# Render planning

Milestone 9 turns one explicitly selected `ShortCandidate` into a deterministic, provider-neutral `RenderPlan`. Planning is deliberately separate from rendering: it describes what a future renderer should do, but does not invoke FFmpeg, create video, crop frames, burn captions, process audio, or publish media.

Run `python -m shorts_pipeline.render_plan_cli create <run-id> <candidate-id>`. It writes `workspace/runs/<run-id>/render_plan_<candidate-id>.json` and records that JSON artifact in the run manifest. Existing valid plans are reused; `--force` regenerates them. An optional TOML file may override the defaults in `config/render-planning.example.toml`.

The plan preserves the candidate and source IDs, inclusive-start/exclusive-end millisecond source range, ordered scene segments, and the candidate duration unchanged. The default target is 1080x1920 (9:16), uses the source frame rate unless overridden, and records MP4/H.264/AAC as output expectations only.

`center_crop` computes a centered crop rectangle from source and target dimensions; `fit_with_blur` and `source_aspect` are represented as strategies without pretending subject-aware framing exists. `transcript_based` captions map overlapping transcript segment IDs from source time to candidate-relative output time and keep style separate. Captions may also be disabled. Audio defaults to `preserve_source_audio`; normalization, ducking, and music are explicit future fields with no processing. The only supported transition metadata is `hard_cut`.

The planner rejects unknown candidates, source mismatches, missing or overlapping scenes, scene ranges outside the candidate, malformed transcript data, invalid configuration, and invalid crop calculations. It does not silently repair timing or candidate boundaries. Rendering, caption graphics, audio processing, transitions, GPU work, deployment, and publishing remain intentionally unimplemented.
