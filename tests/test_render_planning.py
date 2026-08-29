import json
import tempfile
import unittest
from pathlib import Path

from shorts_pipeline.domain import MediaMetadata, RenderPlan, Scene, ShortCandidate, TimeRange, Transcript, TranscriptSegment
from shorts_pipeline.ingestion import ingest_local_source
from shorts_pipeline.render_planning import RenderPlanningConfig, RenderPlanningError, create_render_plan
from shorts_pipeline.runs import load_run


class RenderPlanningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        source = root / "source.mp4"
        source.write_bytes(b"x")
        self.workspace = root / "workspace"
        self.run_id = ingest_local_source(source, workspace_root=self.workspace,
                                          probe=lambda _: MediaMetadata(30_000, 1920, 1080, 30.0)).run.run_id
        self.context = load_run(self.run_id, workspace_root=self.workspace)
        source_id = self.context.source.source_id
        self.scenes = (Scene("scene-1", source_id, 0, TimeRange(0, 10_000)),
                       Scene("scene-2", source_id, 1, TimeRange(10_000, 20_000)))
        self.candidate = ShortCandidate("candidate-1", source_id, TimeRange(0, 20_000),
                                        ("scene-1", "scene-2"), "A self-contained event.")
        transcript = Transcript("transcript-1", source_id,
                                (TranscriptSegment("segment-1", TimeRange(1_000, 4_000), "Opening."),
                                 TranscriptSegment("segment-2", TimeRange(12_000, 16_000), "Payoff.")))
        (self.context.run_directory / "scenes.json").write_text(json.dumps({"scenes": [scene.to_dict() for scene in self.scenes]}))
        (self.context.run_directory / "candidates.json").write_text(json.dumps({"candidates": [self.candidate.to_dict()]}))
        (self.context.run_directory / "transcript.json").write_text(json.dumps(transcript.to_dict()))

    def tearDown(self):
        self.temp.cleanup()

    def test_plan_is_serializable_deterministic_and_updates_manifest(self):
        first = create_render_plan(self.run_id, "candidate-1", workspace_root=self.workspace)
        second = create_render_plan(self.run_id, "candidate-1", workspace_root=self.workspace)
        forced = create_render_plan(self.run_id, "candidate-1", workspace_root=self.workspace, force=True)
        self.assertEqual(RenderPlan.from_dict(first.to_dict()), first)
        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertEqual(first.to_dict(), forced.to_dict())
        self.assertEqual(first.candidate_id, "candidate-1")
        self.assertEqual(first.source_time_range, self.candidate.time_range)
        self.assertEqual(first.target.to_dict(), {"width": 1080, "height": 1920, "frame_rate": 30.0, "container": "mp4"})
        self.assertEqual([segment.scene_id for segment in first.source_segments], ["scene-1", "scene-2"])
        self.assertEqual(first.framing["crop"], {"x": 656, "y": 0, "width": 607, "height": 1080})
        self.assertEqual([item["transcript_segment_id"] for item in first.captions["segments"]], ["segment-1", "segment-2"])
        self.assertEqual(first.audio["strategy"], "preserve_source_audio")
        self.assertEqual(first.output["expected_duration_ms"], 20_000)
        self.assertTrue(any(item.kind == "render_plan:candidate-1" for item in load_run(self.run_id, workspace_root=self.workspace).run.artifacts))

    def test_validation_rejects_invalid_candidate_scenes_and_transcript(self):
        with self.assertRaises(RenderPlanningError):
            create_render_plan(self.run_id, "not-real", workspace_root=self.workspace)
        broken = self.candidate.to_dict()
        broken["scene_ids"] = ["missing"]
        (self.context.run_directory / "candidates.json").write_text(json.dumps({"candidates": [broken]}))
        with self.assertRaises(RenderPlanningError):
            create_render_plan(self.run_id, "candidate-1", workspace_root=self.workspace)
        broken["scene_ids"] = ["scene-2", "scene-1"]
        (self.context.run_directory / "candidates.json").write_text(json.dumps({"candidates": [broken]}))
        with self.assertRaises(RenderPlanningError):
            create_render_plan(self.run_id, "candidate-1", workspace_root=self.workspace)
        (self.context.run_directory / "candidates.json").write_text(json.dumps({"candidates": [self.candidate.to_dict()]}))
        (self.context.run_directory / "transcript.json").write_text("not json")
        with self.assertRaises(RenderPlanningError):
            create_render_plan(self.run_id, "candidate-1", workspace_root=self.workspace)

    def test_config_and_disabled_captions(self):
        with self.assertRaises(ValueError):
            RenderPlanningConfig(width=0)
        with self.assertRaises(ValueError):
            RenderPlanningConfig(framing_strategy="subject_aware")
        plan = create_render_plan(self.run_id, "candidate-1", workspace_root=self.workspace,
                                  config=RenderPlanningConfig(caption_strategy="disabled", framing_strategy="source_aspect"))
        self.assertEqual(plan.captions["strategy"], "disabled")
        self.assertNotIn("crop", plan.framing)

