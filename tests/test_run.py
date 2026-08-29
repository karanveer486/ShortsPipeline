import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from shorts_pipeline.domain import MediaMetadata
from shorts_pipeline.ingestion import ingest_local_source
from shorts_pipeline.run import PipelineRunError, download_source, run_pipeline


class FakeYoutubeDL:
    calls = []

    def __init__(self, options):
        self.options = options
        FakeYoutubeDL.calls.append(options)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def extract_info(self, _url, *, download):
        self.download = download
        Path(self.options["outtmpl"].replace("%(ext)s", "mp4")).write_bytes(b"video")
        return {"id": "synthetic"}


class RunTests(unittest.TestCase):
    def test_downloader_uses_ytdlp_atomically_and_reuses_media(self):
        with tempfile.TemporaryDirectory() as directory:
            FakeYoutubeDL.calls.clear()
            root = Path(directory) / "workspace"
            first = download_source("https://www.youtube.com/watch?v=synthetic", root, ydl_factory=FakeYoutubeDL)
            second = download_source("https://www.youtube.com/watch?v=synthetic", root, ydl_factory=FakeYoutubeDL)
            self.assertEqual(first, second)
            self.assertEqual(first.suffix, ".mp4")
            self.assertEqual(first.read_bytes(), b"video")
            self.assertEqual(len(FakeYoutubeDL.calls), 1)
            options = FakeYoutubeDL.calls[0]
            self.assertIn("vcodec^=avc1", options["format"])
            self.assertIn("acodec^=mp4a", options["format"])
            self.assertEqual(options["merge_output_format"], "mp4")
            self.assertFalse(any(path.is_dir() and path.name.endswith(".tmp") for path in (root / "downloads").iterdir()))
            with self.assertRaises(PipelineRunError):
                download_source("file:///not-allowed.mp4", root, ydl_factory=FakeYoutubeDL)


    def test_orchestration_passes_one_run_and_writes_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); workspace = root / "workspace"; source = root / "source.mp4"; source.write_bytes(b"x")
            stages = []
            def ingest(path, *, workspace_root): return ingest_local_source(path, workspace_root=workspace_root, probe=lambda _: MediaMetadata(20_000, 320, 180, 30.0))
            def stage(name):
                def call(run_id, *_args, **_kwargs): stages.append((name, run_id)); return ()
                return call
            def ranking(run_id, **_kwargs):
                stages.append(("ranking", run_id))
                run_dir = workspace / "runs" / run_id
                (run_dir / "ranked_candidates.json").write_text(json.dumps({"ranked_candidates": [{"candidate_id": "candidate-1"}]}))
                return ()
            class Rendered:
                reused = False
            with patch("shorts_pipeline.run.ingest_local_source", side_effect=ingest), \
                 patch("shorts_pipeline.run.transcribe_run", side_effect=stage("transcribe")), \
                 patch("shorts_pipeline.run.detect_scenes", side_effect=stage("scenes")), \
                 patch("shorts_pipeline.run.extract_frames", side_effect=stage("frames")), \
                 patch("shorts_pipeline.run.analyze_run", side_effect=stage("analysis")), \
                 patch("shorts_pipeline.run.understand_run", side_effect=stage("reasoning")), \
                 patch("shorts_pipeline.run.discover_candidates", side_effect=stage("discovery")), \
                 patch("shorts_pipeline.run.hybrid_evaluate_and_rank", side_effect=ranking), \
                 patch("shorts_pipeline.run.create_render_plan", side_effect=stage("planning")), \
                 patch("shorts_pipeline.run.render_local", return_value=Rendered()):
                run_id, summary, reused = run_pipeline("https://example.test/source.mp4", workspace_root=workspace, downloader=lambda _url, _root: source)
            self.assertFalse(reused)
            self.assertEqual([name for name, _ in stages], ["transcribe", "scenes", "frames", "analysis", "reasoning", "discovery", "ranking", "planning"])
            self.assertTrue(all(value == run_id for _, value in stages))
            data = json.loads(summary.read_text())
            self.assertEqual(data["selected_candidate_id"], "candidate-1")
            self.assertTrue(any(item["kind"] == "run_summary" for item in data["artifacts"]))

