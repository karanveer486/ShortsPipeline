import json
import tempfile
import unittest
from pathlib import Path

from shorts_pipeline.adapters.vlm.contracts import VisualAnalysisRequest
from shorts_pipeline.adapters.vlm.ollama import OllamaVLMError, OllamaVisualAnalyzer, parse_ollama_observation
from shorts_pipeline.domain import ArtifactRef, MediaMetadata, Scene, TimeRange, VisualObservation
from shorts_pipeline.domain.frames import ExtractedFrame
from shorts_pipeline.ingestion import ingest_local_source
from shorts_pipeline.runs import load_run
from shorts_pipeline.visual_analysis import VisualAnalysisConfig, VisualAnalysisError, analyze_run, build_analysis_requests


class FakeAnalyzer:
    def analyze(self, request: VisualAnalysisRequest) -> tuple[VisualObservation, ...]:
        frame = request.frames[0]
        return (VisualObservation(f"observation-{request.request_id}", request.source_id, TimeRange(frame.timestamp_ms, frame.timestamp_ms + 1), {"objects": ["test object"]}, scene_id=frame.scene_id, metadata={"frame_ids": [item.frame_id for item in request.frames]}),)


class FailingAnalyzer:
    def analyze(self, _request: VisualAnalysisRequest) -> tuple[VisualObservation, ...]:
        raise RuntimeError("provider unavailable")


class VisualAnalysisTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "source.mp4"
        self.source.write_bytes(b"source")
        self.workspace = self.root / "workspace"
        result = ingest_local_source(self.source, workspace_root=self.workspace, probe=lambda _: MediaMetadata(2_000, 320, 240, 30.0, "mp4"))
        self.run_id = result.run.run_id
        self.context = load_run(self.run_id, workspace_root=self.workspace)
        scene = Scene("scene-001", self.context.source.source_id, 0, TimeRange(0, 2_000))
        (self.context.run_directory / "scenes.json").write_text(json.dumps({"source_id": self.context.source.source_id, "scenes": [scene.to_dict()]}), encoding="utf-8")
        directory = self.context.run_directory / "frames"; directory.mkdir()
        frames = []
        for timestamp in (0, 500):
            path = directory / f"frame-{timestamp}.jpg"; path.write_bytes(b"image")
            frames.append(ExtractedFrame(f"frame-{timestamp}", self.context.source.source_id, timestamp, ArtifactRef(f"artifact-{timestamp}", "frame", path.as_posix(), "image/jpeg"), "scene-001"))
        (self.context.run_directory / "frames.json").write_text(json.dumps({"source_id": self.context.source.source_id, "frames": [item.to_dict() for item in frames]}), encoding="utf-8")

    def tearDown(self) -> None: self.temp.cleanup()

    def test_request_batching_and_manifest_update(self) -> None:
        frames = tuple(ExtractedFrame.from_dict(item) for item in json.loads((self.context.run_directory / "frames.json").read_text())["frames"])
        requests = build_analysis_requests(self.context, frames, (), (), VisualAnalysisConfig(max_frames_per_request=1))
        self.assertEqual(len(requests), 2)
        observations = analyze_run(self.run_id, workspace_root=self.workspace, config_path=None, analyzer=FakeAnalyzer())
        self.assertEqual(len(observations), 1)
        payload = json.loads((self.context.run_directory / "visual_analysis.json").read_text())
        self.assertEqual(payload["backend"], "ollama")
        self.assertTrue(any(item.kind == "visual_analysis" for item in load_run(self.run_id, workspace_root=self.workspace).run.artifacts))

    def test_existing_output_reuse_and_failures(self) -> None:
        first = analyze_run(self.run_id, workspace_root=self.workspace, config_path=None, analyzer=FakeAnalyzer())
        self.assertEqual(first, analyze_run(self.run_id, workspace_root=self.workspace, config_path=None, analyzer=FailingAnalyzer()))
        with self.assertRaises(VisualAnalysisError): analyze_run("run-missing", workspace_root=self.workspace, config_path=None, analyzer=FakeAnalyzer())
        (self.context.run_directory / "visual_analysis.json").unlink()
        with self.assertRaises(VisualAnalysisError): analyze_run(self.run_id, workspace_root=self.workspace, config_path=None, analyzer=FailingAnalyzer())

    def test_ollama_response_and_missing_frame_validation(self) -> None:
        response = {"message": {"content": '{"observations":{"people":[]},"confidence":0.8,"uncertainty":0.2}'}}
        observations, confidence, uncertainty = parse_ollama_observation(response)
        self.assertEqual(observations, {"people": []}); self.assertEqual(confidence, 0.8); self.assertEqual(uncertainty, 0.2)
        with self.assertRaises(OllamaVLMError): parse_ollama_observation({"message": {"content": "not json"}})
        frame = ExtractedFrame("missing", "source", 0, ArtifactRef("artifact", "frame", str(self.root / "missing.jpg")))
        request = VisualAnalysisRequest("request", "source", (frame,))
        with self.assertRaises(OllamaVLMError): OllamaVisualAnalyzer(transport=lambda *_: response).analyze(request)
