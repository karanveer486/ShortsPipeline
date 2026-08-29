# Local source ingestion

The ingestion stage accepts one local video file, verifies that it exists, and uses the locally installed `ffprobe` command to read basic container and stream metadata. It creates `SourceVideo`, `MediaMetadata`, `ArtifactRef`, and `PipelineRun` contracts, then writes a JSON manifest.

It does not copy the source file, transcribe audio, detect scenes, call a VLM, render media, or contact any cloud/provider service.

## Run data

For a source snapshot, ingestion derives a stable run ID from the resolved path, file size, and modification time. It writes only a manifest here:

```text
workspace/runs/<run_id>/manifest.json
```

The source is represented in the manifest by its `file:` URI in `SourceVideo.reference` and an `ArtifactRef`; its bytes remain at the original path. Repeating ingestion of an unchanged source reopens the existing manifest instead of overwriting it. A changed source snapshot receives a different run ID.

## Run manually

`ffprobe` must be installed and available on `PATH` (it is normally distributed with FFmpeg). No Python media dependency is installed.

```powershell
python -m shorts_pipeline ingest "C:\path\to\source.mp4"
```

Use a different local runtime directory if needed:

```powershell
python -m shorts_pipeline ingest "C:\path\to\source.mp4" --workspace "D:\ShortsRuntime"
```

Errors for a missing file, unreadable/non-video input, unavailable `ffprobe`, or malformed probe output are reported clearly. This is the only implemented pipeline stage in Milestone 2.
