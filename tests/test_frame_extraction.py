import json
import tempfile
import unittest
from pathlib import Path

from shorts_pipeline.domain import MediaMetadata, Scene, TimeRange
from shorts_pipeline.frame_config import FrameSamplingConfig, frame_sampling_config
from shorts_pipeline.frame_extraction import FrameExtractionError, extract_frames, sample_timestamps
from shorts_pipeline.ingestion import ingest_local_source
from shorts_pipeline.runs import load_run


class FakeFrameExtractor:
    def extract(self, _source: Path, _timestamp_ms: int, output: Path, _image_format: str) -> None:
        output.write_bytes(b"synthetic frame")


class FailingFrameExtractor:
    def extract(self, *_args: object) -> None:
        raise AssertionError("existing output should be reused")


class FrameExtractionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.source = self.root / "source.mp4"
        self.source.write_bytes(b"synthetic source")
        self.workspace = self.root / "workspace"
        result = ingest_local_source(self.source, workspace_root=self.workspace, probe=lambda _path: MediaMetadata(10_000, 640, 360, 30.0, "mp4"))
        self.run_id = result.run.run_id
        self.context = load_run(self.run_id, workspace_root=self.workspace)
        self.scenes = (
            Scene("scene-a", self.context.source.source_id, 0, TimeRange(0, 4_000)),
            Scene("scene-b", self.context.source.source_id, 1, TimeRange(4_000, 10_000)),
        )
        (self.context.run_directory / "scenes.json").write_text(json.dumps({"run_id": self.run_id, "source_id": self.context.source.source_id, "scenes": [scene.to_dict() for scene in self.scenes]}), encoding="utf-8")

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_interval_sampling_converts_timestamps_and_associates_scenes(self) -> None:
        samples = sample_timestamps(self.context, self.scenes, FrameSamplingConfig(interval_ms=2_000))
        self.assertEqual(samples, ((0, "scene-a"), (2_000, "scene-a"), (4_000, "scene-b"), (6_000, "scene-b"), (8_000, "scene-b")))

    def test_scene_relative_sampling_and_stable_frame_ids(self) -> None:
        frames = extract_frames(self.run_id, workspace_root=self.workspace, config_path=None, strategy="scene-relative", extractor=FakeFrameExtractor())
        self.assertEqual([frame.timestamp_ms for frame in frames], [2_000, 7_000])
        self.assertEqual([frame.scene_id for frame in frames], ["scene-a", "scene-b"])
        self.assertEqual([frame.frame_id for frame in frames], [f"frame-{self.run_id}-scene-a-000000002000", f"frame-{self.run_id}-scene-b-000000007000"])

    def test_manifest_and_reuse(self) -> None:
        first = extract_frames(self.run_id, workspace_root=self.workspace, config_path=None, interval_ms=5_000, extractor=FakeFrameExtractor())
        second = extract_frames(self.run_id, workspace_root=self.workspace, config_path=None, extractor=FailingFrameExtractor())
        metadata = json.loads((self.context.run_directory / "frames.json").read_text(encoding="utf-8"))
        self.assertEqual(first, second)
        self.assertEqual(metadata["frames"][0]["timestamp_ms"], 0)
        self.assertTrue(any(item.kind == "frames" for item in load_run(self.run_id, workspace_root=self.workspace).run.artifacts))

    def test_missing_run_source_and_malformed_configuration_are_rejected(self) -> None:
        with self.assertRaises(FrameExtractionError):
            extract_frames("run-missing", workspace_root=self.workspace, config_path=None, extractor=FakeFrameExtractor())
        self.source.unlink()
        with self.assertRaises(FrameExtractionError):
            extract_frames(self.run_id, workspace_root=self.workspace, config_path=None, extractor=FakeFrameExtractor())
        with self.assertRaises(ValueError):
            FrameSamplingConfig(strategy="unknown")
        with self.assertRaises(ValueError):
            frame_sampling_config(None, interval_ms=0)
