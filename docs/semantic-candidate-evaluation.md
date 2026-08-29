# Semantic candidate evaluation

The default ranking command remains deterministic. `semantic_ranking_cli` is an optional hybrid path that combines the existing deterministic signals with seven structured semantic scores from the provider-neutral `CandidateEvaluator` interface. `OllamaCandidateEvaluator` is the first local implementation and communicates over existing local Ollama HTTP infrastructure; it receives candidate metadata, relevant scenes, transcript, understanding items, and observation summaries—not source video or frames.

Every semantic score is an integer 0–10 with a rationale and optional uncertainty. Invalid JSON, scores, or candidate IDs are rejected. The combined `quality_score` remains a heuristic, not a virality or performance prediction. Evidence fields are preserved from deterministic discovery.

Run `python -m shorts_pipeline.semantic_ranking_cli run-<id> --model qwen2.5vl:7b`. This writes the usual evaluations/ranking artifacts with `method: hybrid-ollama-heuristic-v1`.
