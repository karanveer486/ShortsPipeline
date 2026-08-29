import json
import tempfile
import unittest
from pathlib import Path

from shorts_pipeline.domain import MediaMetadata
from shorts_pipeline.ingestion import ingest_local_source
from shorts_pipeline.runs import load_run
from shorts_pipeline.scene_detection import SceneDetectionError, detect_scenes, scenes_from_ranges
from shorts_pipeline.transcription import RawTranscriptSegment, TranscriptionError, seconds_to_milliseconds, transcribe_run


class FakeTranscriber:
    def transcribe(self, _source: Path, _config: object) -> list[RawTranscriptSegment]:
        return [RawTranscriptSegment(0.125, 1.75, " First line "), RawTranscriptSegment(1.75, 3.0, "Second line")]


class FakeSceneDetector:
    def detect(self, _source: Path, _config: object) -> list[tuple[float, float]]:
        return [(0.0, 1.5), (1.5, 3.0)]


class FailingTranscriber:
    def transcribe(self, _source: Path, _config: object) -> list[RawTranscriptSegment]:
        raise AssertionError("existing output should be reused")


class TimelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.source = self.root / "source.mp4"
        self.source.write_bytes(b"synthetic test input")
        self.workspace = self.root / "workspace"
        result = ingest_local_source(
            self.source,
            workspace_root=self.workspace,
            probe=lambda _path: MediaMetadata(3_000, 640, 360, 30.0, "mp4"),
        )
        self.run_id = result.run.run_id

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_timestamp_conversion_and_transcript_serialization(self) -> None:
        self.assertEqual(seconds_to_milliseconds(1.2345), 1234)
        transcript = transcribe_run(self.run_id, workspace_root=self.workspace, config_path=None, transcriber=FakeTranscriber())
        output = self.workspace / "runs" / self.run_id / "transcript.json"
        self.assertEqual(transcript.segments[0].time_range.start_ms, 125)
        self.assertEqual(transcript.segments[0].time_range.end_ms, 1750)
        self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["segments"][1]["text"], "Second line")
        self.assertTrue(any(item.kind == "transcript" for item in load_run(self.run_id, workspace_root=self.workspace).run.artifacts))

    def test_scene_conversion_has_stable_ordered_ids(self) -> None:
        context = load_run(self.run_id, workspace_root=self.workspace)
        scenes = scenes_from_ranges(context, [(0.0, 1.5), (1.5, 3.0)])
        self.assertEqual([scene.scene_id for scene in scenes], [f"scene-{self.run_id}-0000", f"scene-{self.run_id}-0001"])
        detected = detect_scenes(self.run_id, workspace_root=self.workspace, config_path=None, detector=FakeSceneDetector())
        self.assertEqual(detected, scenes)
        self.assertTrue((self.workspace / "runs" / self.run_id / "scenes.json").is_file())

    def test_existing_outputs_are_reused(self) -> None:
        first = transcribe_run(self.run_id, workspace_root=self.workspace, config_path=None, transcriber=FakeTranscriber())
        second = transcribe_run(self.run_id, workspace_root=self.workspace, config_path=None, transcriber=FailingTranscriber())
        self.assertEqual(first, second)
        first_scenes = detect_scenes(self.run_id, workspace_root=self.workspace, config_path=None, detector=FakeSceneDetector())
        second_scenes = detect_scenes(self.run_id, workspace_root=self.workspace, config_path=None, detector=lambda *_args: (_ for _ in ()).throw(AssertionError("detector should not run")))
        self.assertEqual(first_scenes, second_scenes)

    def test_missing_run_and_source_are_rejected(self) -> None:
        with self.assertRaises(TranscriptionError):
            transcribe_run("run-does-not-exist", workspace_root=self.workspace, config_path=None, transcriber=FakeTranscriber())
        self.source.unlink()
        with self.assertRaises(SceneDetectionError):
            detect_scenes(self.run_id, workspace_root=self.workspace, config_path=None, detector=FakeSceneDetector())

    def test_malformed_processing_output_is_rejected(self) -> None:
        class InvalidTranscriber:
            def transcribe(self, _source: Path, _config: object) -> list[RawTranscriptSegment]:
                return [RawTranscriptSegment(1.0, 1.0, "invalid")]

        with self.assertRaises(TranscriptionError):
            transcribe_run(self.run_id, workspace_root=self.workspace, config_path=None, transcriber=InvalidTranscriber())
        output = self.workspace / "runs" / self.run_id / "scenes.json"
        output.write_text("not JSON", encoding="utf-8")
        with self.assertRaises(SceneDetectionError):
            detect_scenes(self.run_id, workspace_root=self.workspace, config_path=None, detector=FakeSceneDetector())
