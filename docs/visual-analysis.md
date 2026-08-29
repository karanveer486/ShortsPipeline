# Local visual analysis

The proof-of-integration visual-analysis stage reads an existing run's extracted frames and uses the provider-neutral `VisualAnalyzer` protocol. The first concrete adapter is `OllamaVisualAnalyzer`, isolated under `adapters/vlm/ollama.py`; it calls the already installed local Ollama HTTP API using Python's standard library.

It groups frames by scene and sends at most `max_frames_per_request` frames (default 4) per request. Scene IDs and overlapping transcript segments are available in each `VisualAnalysisRequest`; the first local prompt focuses only on raw visual facts. It returns one `VisualObservation` for each request, including flexible categories such as people, objects, environment, actions, visible text, and notable details.

Run `python -m shorts_pipeline.vlm_cli analyze run-<id>`. The default local model is `qwen2.5vl:7b`; configure `[visual_analysis]` in an ignored `config/pipeline.toml` or use `--model`. Results are written to `workspace/runs/<run_id>/visual_analysis.json` and referenced by the run manifest. Valid existing results are reused unless `--force` is supplied.

This is a local integration proof, not a production prompt system or reasoning layer. It does not perform candidate selection, video understanding, rendering, cloud inference, or publishing.
