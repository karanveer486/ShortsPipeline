# RunPod execution

Milestone 11 adds a thin deployment layer around the existing local stages. It downloads an HTTP(S) source into `workspace/downloads/`, then runs ingestion, transcription, scene detection, frame extraction, visual analysis, reasoning, discovery, ranking, render planning, and local rendering in that order. All source and generated media remain under the ignored runtime workspace.

On a Linux RunPod with this repository cloned, run `bash install.sh`. It creates `.venv`, installs project dependencies only into that venv, verifies Python 3.11+, FFmpeg/ffprobe, `nvidia-smi` when available, Ollama, and the required `qwen2.5vl:7b` model. If a system tool or model is absent, the installer stops with the exact command/action needed; it never installs Python packages globally.

Start Ollama on the pod and pull the model if needed: `ollama serve` and `ollama pull qwen2.5vl:7b`. Then run:

```bash
.venv/bin/python -m shorts_pipeline.run "https://example.invalid/source.mp4" --workspace workspace
```

Use `--candidate-id <id>` to render a particular ranked candidate, or omit it to select rank 1. `--evaluation-mode deterministic` is available for runs where the existing semantic evaluator is intentionally not wanted. The final `workspace/runs/<run-id>/run_summary.json` lists the selected candidate and all tracked artifacts; rendered MP4s are in that run's `renders/` directory. `--force` delegates recomputation to the existing stages.

The runner is deliberately not a web service, cloud scheduler, publisher, or new AI feature. It does not copy source media into Git, install RunPod tooling, or introduce a new pipeline configuration system.
