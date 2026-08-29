# Local rendering

Milestone 10 executes an existing `RenderPlan` locally with the `ffmpeg` executable. The plan remains the single source of truth for source timing, vertical target, crop geometry, captions, audio, transition, codecs, and output location. This stage does not select candidates, re-plan framing, call an LLM, or perform cloud work.

Run:

```powershell
python -m shorts_pipeline.render_cli render <run-id> <candidate-id> --workspace workspace
```

Use `--force` to deliberately render again; otherwise a successful matching `render_output_<candidate-id>.json` and nonempty MP4 are reused. FFmpeg must be available on `PATH`. It is invoked through a subprocess argument list, never through a shell command.

The output location comes from the plan and is normally `workspace/runs/<run-id>/renders/<candidate-id>.mp4`. Rendering writes a temporary MP4 and moves it atomically only after FFmpeg succeeds. The manifest is updated only after success, with the MP4 artifact and the `render_output_<candidate-id>.json` metadata artifact. Source media is referenced in place and never copied.

Current rendering supports `center_crop`, `transcript_based` or disabled captions, `preserve_source_audio`, and `hard_cut`. Transcript-based captions are deterministically written to a temporary SRT file from the planned segment references, then burned into the video by FFmpeg. Subject-aware framing, dynamic reframing, fancy caption styling, transition effects, music, sound effects, GPU encoders, publishing, and orchestration are intentionally not implemented.
