# Short candidate discovery

Candidate discovery turns `VideoUnderstanding` into evidence-backed, contiguous timeline proposals. It does not rank candidates, predict virality, generate titles, or render video.

The current `deterministic-evidence-v1` method converts each understanding item's cited scene/time evidence into the smallest enclosing contiguous sequence of scenes. It records the source understanding item and observation IDs in candidate metadata. A lightweight score mirrors understanding confidence only and is **discovery confidence**, not a performance prediction.

Candidates retain durations outside the configurable preferred 15–60 second range and flag that condition in metadata rather than silently discarding evidence. Output is `workspace/runs/<run_id>/candidates.json`, referenced by the run manifest and reused unless `--force` is passed.

Run `python -m shorts_pipeline.candidate_cli discover run-<id>`. LLM refinement and final ranking are intentionally deferred.
