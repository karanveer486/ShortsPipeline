# Video understanding

Visual observations state what is visible; `VideoUnderstanding` records higher-level, evidence-backed conclusions about events, sequences, and topics. It is not a Short-selection layer.

`reasoning_cli understand` loads existing scenes, transcript, and visual-analysis artifacts. Contiguous scenes are grouped into configurable time-bounded chunks (60 seconds by default). Each chunk result is saved at `workspace/runs/<run_id>/analysis/chunk-*.json`, enabling restart after a global merge failure. The final `video_understanding.json` records chunking, model/backend, timestamps, final understanding items, and evidence.

The first local `OllamaVideoReasoner` asks Qwen through local Ollama for strict JSON. It cites scene IDs/time ranges via `EvidenceRef`; referenced raw observation IDs are retained in `UnderstandingItem.attributes`. This is provisional pending a future domain extension for observation-level evidence.

Run: `python -m shorts_pipeline.reasoning_cli understand run-<id>`. Existing valid final output is reused; use `--force` to recompute. No candidate generation, rendering, publishing, or cloud reasoning is included.
