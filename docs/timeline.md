# Timeline layer

The timeline layer adds two independent local stages to an already ingested run: transcription and scene detection. Both read the source reference from `workspace/runs/<run_id>/manifest.json`, create provider-neutral domain objects, and add a JSON artifact reference back to that manifest. Neither stage copies or edits the source video.

## Transcription

`transcribe` uses the open-source `openai-whisper` package through `WhisperTranscriber`, an internal adapter that can later be replaced without changing the `Transcript` contract. The configured model defaults to `base`; set a different model, language, or device in local TOML configuration or use `--model` for one invocation.

It writes `workspace/runs/<run_id>/transcript.json`, containing a `Transcript` and millisecond `TranscriptSegment` ranges.

## Scene detection

`detect-scenes` uses PySceneDetect's content detector through `PySceneDetector`. It writes `workspace/runs/<run_id>/scenes.json`, with ordered `Scene` records and stable IDs derived from the run ID. The content-detector threshold and minimum scene length are provisional TOML settings.

## Dependencies

The project explicitly depends on `openai-whisper`, `scenedetect`, and `opencv-python`. Whisper also needs the local FFmpeg executable for audio decoding; it is not a Python dependency. Model weights are downloaded/managed by Whisper at runtime and must remain outside Git.

## Running the stages

After installing the project, use the run ID printed by ingestion:

```powershell
python -m shorts_pipeline transcribe run-<id>
python -m shorts_pipeline detect-scenes run-<id>
```

Both commands accept `--workspace`, `--config`, and `--force`. A valid existing output is reused by default; `--force` recomputes it and atomically replaces the JSON. The stage fails clearly for a missing/malformed run, unavailable source, unavailable dependency, malformed output, or local processing failure.

The timeline layer is intentionally limited to transcript and scene data. Visual analysis, candidate discovery, rendering, and publishing remain future stages.
