# ShortsPipeline

ShortsPipeline is a clean-room, local-first foundation for turning long-form source videos into reviewable YouTube Shorts. It is intentionally at the project-setup stage: no video processing, ML inference, remote deployment, or publishing functionality has been implemented.

## Intended lifecycle

The eventual pipeline will ingest a video, collect metadata and a transcript, detect scenes, analyze visuals, build a higher-level representation, surface Short candidates, render selected candidates in 9:16, and require human review before publishing.

The design will keep visual-language-model (VLM) integrations behind an adapter boundary so a local backend and a future remote RunPod/vLLM backend can be substituted without changing pipeline orchestration. No backend is included yet.

## Repository layout

```text
config/                  Tracked configuration templates and defaults
docs/                    Architecture and operational documentation
scripts/                 Future developer/maintenance scripts
src/shorts_pipeline/     Installable Python package (foundation only)
tests/                   Standard-library test suite
workspace/               Local runtime artifacts; excluded from Git
```

`workspace/` is organized by processing stage and is deliberately ignored. It may hold source media, metadata, transcripts, scene data, extracted frames, analysis, candidates, renders, review assets, local model files, and temporary files. Directory placeholders are the only tracked files there.

## Getting started

This project has no runtime dependencies at this stage. With Python 3.11 or later, an editable install is optional:

```powershell
python -m pip install -e .
python -m unittest discover -s tests -v
```

To add machine-specific settings, copy `.env.example` to `.env`; never commit the resulting file.

## Current status

Foundation only. Pipeline functionality, VLM implementations, video/media tooling, cloud deployment, and publishing integrations are intentionally out of scope until the next phase.
