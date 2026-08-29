# Frame extraction CLI

Until the shared CLI dispatcher includes this command, invoke the independent frame extractor directly:

```powershell
python -m shorts_pipeline.frame_cli run-<id>
python -m shorts_pipeline.frame_cli run-<id> --strategy scene-relative
python -m shorts_pipeline.frame_cli run-<id> --interval-ms 1000 --force
```

It requires the run's source and `scenes.json`; it emits images and `frames.json` under that same run directory.
