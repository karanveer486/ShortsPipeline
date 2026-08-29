import tempfile
import unittest
from pathlib import Path

from shorts_pipeline.adapters.vlm.contracts import VisualAnalysisRequest, VisualAnalyzer, validate_visual_observations
from shorts_pipeline.domain import ArtifactRef, TimeRange, VisualObservation
from shorts_pipeline.domain.frames import ExtractedFrame


class FakeVisualAnalyzer:
    def analyze(self, request: VisualAnalysisRequest) -> tuple[VisualObservation, ...]:
        frame = request.frames[0]
        return (VisualObservation("observation-001", request.source_id, TimeRange(frame.timestamp_ms, frame.timestamp_ms + 1), {"summary": "test observation"}, scene_id=frame.scene_id, metadata={"frame_ids": [frame.frame_id]}),)


class VLMContractTests(unittest.TestCase):
    def test_provider_neutral_request_and_response_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "frame.jpg"
            path.write_bytes(b"frame")
            frame = ExtractedFrame("frame-001", "source-001", 1_000, ArtifactRef("artifact-frame-001", "frame", path.as_posix(), "image/jpeg"), scene_id="scene-001")
            request = VisualAnalysisRequest("request-001", "source-001", (frame,), instructions="Describe visible actions.")
            analyzer: VisualAnalyzer = FakeVisualAnalyzer()
            observations = validate_visual_observations(request, analyzer.analyze(request))

        self.assertEqual(observations[0].source_id, "source-001")
        self.assertEqual(observations[0].metadata["frame_ids"], ["frame-001"])

    def test_mismatched_frame_source_is_rejected(self) -> None:
        frame = ExtractedFrame("frame-001", "different-source", 0, ArtifactRef("artifact-frame-001", "frame", "frame.jpg", "image/jpeg"))
        with self.assertRaises(ValueError):
            VisualAnalysisRequest("request-001", "source-001", (frame,))
