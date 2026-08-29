# Candidate evaluation and ranking

Evaluation is separate from discovery: discovery proposes evidence-backed sequences; evaluation assigns transparent heuristic quality signals; ranking orders but never removes candidates. Scores are 0–10 heuristic assessments, not predicted views, virality, engagement, or scientifically calibrated measures.

The current deterministic method scores duration fit, evidence confidence, scene-boundary continuity, visual evidence availability, and basic context/narrative coverage. Semantic signals (hook, payoff, novelty) remain zero until a future provider-neutral LLM evaluator is introduced. The weighted average uses equal configurable weights and stable ties: score, evidence confidence, earlier start, then candidate ID.

Results are `evaluations.json` and `ranked_candidates.json` in the run directory; both are reused unless `--force` is set. Run `python -m shorts_pipeline.ranking_cli evaluate run-<id>`. No rendering or publishing behavior is included.
