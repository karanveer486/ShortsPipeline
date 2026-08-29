# Timeline CLI usage

The current timeline-aware command entry point is `python -m shorts_pipeline.cli`. It exposes the existing ingestion stage and the new independent timeline stages:

```powershell
python -m shorts_pipeline.cli ingest "C:\path\to\source.mp4"
python -m shorts_pipeline.cli transcribe run-<id>
python -m shorts_pipeline.cli detect-scenes run-<id>
```

`transcribe` and `detect-scenes` locate the previously ingested run in `workspace/runs/<run_id>/manifest.json`. Both reuse an existing valid output by default; add `--force` to recompute it. `--workspace` selects another local runtime root, while `--config` accepts a local TOML file. `transcribe` also accepts `--model` as a one-run Whisper override.
