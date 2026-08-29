# Architecture direction

The repository is local-first. Runtime artifacts stay under `workspace/` and are not source-controlled.

Future orchestration will be organized around explicit stage inputs and outputs: ingestion, metadata, transcription, scene detection, visual analysis, video understanding, candidate discovery, rendering, and human review. Stages should exchange durable, versioned data contracts rather than call provider SDKs directly.

Visual-language-model access will be isolated behind an adapter boundary in `src/shorts_pipeline/adapters/vlm/`. A future local implementation and a future RunPod/vLLM implementation will conform to that boundary. This foundation intentionally defines neither interface nor implementation so it does not imply a provider contract prematurely.

Human review is a required gate between candidate rendering and any future publishing integration.
