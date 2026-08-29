import json
import unittest
from datetime import datetime, timezone

from shorts_pipeline.domain import (
    ArtifactRef, CandidateStatus, EvidenceRef, MediaMetadata, PipelineRun,
    RenderOutput, RenderPlan, RenderStatus, Review, ReviewDecision, RunStatus,
    Scene, ShortCandidate, SourceVideo, TargetFormat, TimeRange, Transcript,
    TranscriptSegment, UnderstandingItem, VideoUnderstanding, VisualObservation,
)


class DomainModelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = SourceVideo("source-001", "workspace/inbox/source-001.mp4", MediaMetadata(120_000, 1920, 1080, 30.0, "mp4"))
        self.scene = Scene("scene-001", "source-001", 0, TimeRange(0, 15_000), {"cut": "hard"})

    def test_source_and_run_serialize_to_json(self) -> None:
        artifact = ArtifactRef("artifact-transcript", "transcript", "workspace/transcripts/source-001.json", "application/json")
        run = PipelineRun("run-001", self.source.source_id, datetime(2026, 8, 29, 12, tzinfo=timezone.utc), "1", RunStatus.SUCCEEDED, (artifact,))
        self.assertEqual(PipelineRun.from_dict(json.loads(run.to_json())), run)
        self.assertEqual(SourceVideo.from_dict(self.source.to_dict()), self.source)

    def test_analysis_contracts_link_back_to_scenes(self) -> None:
        transcript = Transcript("transcript-001", "source-001", (TranscriptSegment("segment-001", TimeRange(250, 2_500), "A concise opening line.", 0.94),), "en")
        observation = VisualObservation("observation-001", "source-001", TimeRange(0, 5_000), {"subjects": ["presenter"], "setting": "studio"}, self.scene.scene_id, 0.8)
        understanding = VideoUnderstanding("understanding-001", "source-001", (UnderstandingItem("fact-001", "event", "The presenter introduces the topic.", EvidenceRef((self.scene.scene_id,), (TimeRange(0, 5_000),)), 0.8),))
        self.assertEqual(transcript.segments[0].time_range.start_ms, 250)
        self.assertEqual(observation.scene_id, self.scene.scene_id)
        self.assertEqual(understanding.items[0].evidence.scene_ids, (self.scene.scene_id,))
        self.assertEqual(VideoUnderstanding.from_dict(understanding.to_dict()), understanding)

    def test_candidate_render_and_review_references(self) -> None:
        candidate = ShortCandidate("candidate-001", "source-001", TimeRange(0, 15_000), (self.scene.scene_id,), "Clear standalone explanation.", "A surprising claim", "The explanation", 0.91, CandidateStatus.IN_REVIEW)
        plan = RenderPlan("plan-001", candidate.candidate_id, TargetFormat(1080, 1920, 30.0), {"strategy": "speaker_centered"}, {"enabled": True, "language": "en"})
        output = RenderOutput("render-001", plan.plan_id, candidate.candidate_id, RenderStatus.SUCCEEDED, ArtifactRef("artifact-render-001", "render", "workspace/renders/render-001.mp4", "video/mp4"))
        review = Review("review-001", candidate.candidate_id, ReviewDecision.APPROVED, datetime(2026, 8, 29, 13, tzinfo=timezone.utc), output.render_id, "reviewer-01")
        self.assertEqual(RenderPlan.from_dict(plan.to_dict()), plan)
        self.assertEqual(RenderOutput.from_dict(output.to_dict()), output)
        self.assertEqual(Review.from_dict(review.to_dict()), review)

    def test_malformed_data_is_rejected(self) -> None:
        with self.assertRaises(ValueError): TimeRange(1_000, 1_000)
        with self.assertRaises(ValueError): MediaMetadata(0, 1920, 1080, 30.0)
        with self.assertRaises(ValueError): VisualObservation("observation-001", "source-001", TimeRange(0, 100), {"x": object()})
        with self.assertRaises(ValueError): ShortCandidate("candidate-001", "source-001", TimeRange(0, 100), (), "reason")
        with self.assertRaises(ValueError): RenderOutput("render-001", "plan-001", "candidate-001", RenderStatus.SUCCEEDED)
        with self.assertRaises(ValueError): PipelineRun.from_dict({"run_id": "run-001", "source_id": "source-001", "created_at": "not-a-date", "contract_version": "1"})
