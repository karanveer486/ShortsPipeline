import json
import tempfile
import unittest
from pathlib import Path

from shorts_pipeline.domain import MediaMetadata
from shorts_pipeline.ingestion import ExistingRunError, MediaProbeError, SourceNotFoundError, ingest_local_source, probe_media


class IngestionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.source = self.root / "input.mp4"
        self.source.write_bytes(b"not a real video")
        self.workspace = self.root / "workspace"

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    @staticmethod
    def synthetic_probe(_source: Path) -> MediaMetadata:
        return MediaMetadata(duration_ms=12_500, width=1920, height=1080, frame_rate=29.97, container="mov,mp4", video_codec="h264", audio_codec="aac")

    def test_missing_source_is_rejected(self) -> None:
        with self.assertRaises(SourceNotFoundError):
            ingest_local_source(self.root / "missing.mp4", workspace_root=self.workspace, probe=self.synthetic_probe)

    def test_metadata_becomes_domain_models_and_manifest(self) -> None:
        result = ingest_local_source(self.source, workspace_root=self.workspace, probe=self.synthetic_probe)
        manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(result.source.media.duration_ms, 12_500)
        self.assertEqual(result.source.media.video_codec, "h264")
        self.assertEqual(manifest["source"]["source_id"], result.run.source_id)
        self.assertEqual(manifest["run"]["run_id"], result.run.run_id)
        self.assertEqual(manifest["run"]["artifacts"][0]["uri"], self.source.resolve().as_uri())

    def test_repeated_ingestion_reuses_manifest_without_reprobing(self) -> None:
        first = ingest_local_source(self.source, workspace_root=self.workspace, probe=self.synthetic_probe)
        second = ingest_local_source(self.source, workspace_root=self.workspace, probe=lambda _path: (_ for _ in ()).throw(AssertionError("probe should not run")))
        self.assertEqual(first.run.run_id, second.run.run_id)
        self.assertEqual(first.manifest_path.read_text(encoding="utf-8"), second.manifest_path.read_text(encoding="utf-8"))

    def test_malformed_ffprobe_output_is_rejected(self) -> None:
        from unittest.mock import patch
        from subprocess import CompletedProcess

        with patch("shorts_pipeline.ingestion.subprocess.run", return_value=CompletedProcess([], 0, stdout="not json", stderr="")):
            with self.assertRaises(MediaProbeError):
                probe_media(self.source)

    def test_invalid_existing_manifest_is_not_overwritten(self) -> None:
        result = ingest_local_source(self.source, workspace_root=self.workspace, probe=self.synthetic_probe)
        result.manifest_path.write_text("not json", encoding="utf-8")
        with self.assertRaises(ExistingRunError):
            ingest_local_source(self.source, workspace_root=self.workspace, probe=self.synthetic_probe)
