import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from shorts_pipeline.domain import MediaMetadata, Scene, ShortCandidate, TimeRange, Transcript, TranscriptSegment
from shorts_pipeline.ingestion import ingest_local_source
from shorts_pipeline.render_planning import create_render_plan
from shorts_pipeline.rendering import FFmpegRunner, FFmpegUnavailableError, RenderExecutionError, build_ffmpeg_command, render_local
from shorts_pipeline.runs import load_run


class FakeRunner:
    def __init__(self, returncode=0):
        self.returncode = returncode
        self.commands = []

    def run(self, command):
        self.commands.append(command)
        if self.returncode == 0:
            Path(command[-1]).write_bytes(b"synthetic mp4")
        return subprocess.CompletedProcess(command, self.returncode, "", "simulated failure" if self.returncode else "")


class LocalRenderingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        source = root / "source.mp4"
        source.write_bytes(b"source")
        self.workspace = root / "workspace"
        self.run_id = ingest_local_source(source, workspace_root=self.workspace,
                                          probe=lambda _: MediaMetadata(30_000, 1920, 1080, 30.0)).run.run_id
        self.context = load_run(self.run_id, workspace_root=self.workspace)
        source_id = self.context.source.source_id
        scenes = (Scene("scene-1", source_id, 0, TimeRange(0, 10_000)),
                  Scene("scene-2", source_id, 1, TimeRange(10_000, 20_000)))
        candidate = ShortCandidate("candidate-1", source_id, TimeRange(0, 20_000), ("scene-1", "scene-2"), "Synthetic render candidate.")
        transcript = Transcript("transcript-1", source_id,
                                (TranscriptSegment("segment-1", TimeRange(1_000, 4_000), "Opening caption."),))
        (self.context.run_directory / "scenes.json").write_text(json.dumps({"scenes": [value.to_dict() for value in scenes]}))
        (self.context.run_directory / "candidates.json").write_text(json.dumps({"candidates": [candidate.to_dict()]}))
        (self.context.run_directory / "transcript.json").write_text(json.dumps(transcript.to_dict()))
        self.plan = create_render_plan(self.run_id, candidate.candidate_id, workspace_root=self.workspace)

    def tearDown(self):
        self.temp.cleanup()

    def test_command_honors_plan_crop_target_audio_and_captions(self):
        subtitle = self.context.run_directory / "tmp" / "captions.srt"
        command = build_ffmpeg_command(Path("source.mp4"), self.plan, Path("output.mp4"), subtitle_path=subtitle)
        self.assertIn("crop=607:1080:656:0", command[command.index("-vf") + 1])
        self.assertIn("scale=1080:1920:flags=lanczos", command[command.index("-vf") + 1])
        self.assertIn("subtitles=filename=", next(value for value in command if value.startswith("crop=")))
        self.assertEqual(command[command.index("-map") + 1], "0:v:0")
        self.assertIn("0:a:0?", command)
        self.assertEqual(command[command.index("-c:v") + 1], "libx264")
        self.assertEqual(command[command.index("-c:a") + 1], "aac")

    def test_success_reuse_force_and_manifest_updates(self):
        runner = FakeRunner()
        first = render_local(self.run_id, "candidate-1", workspace_root=self.workspace, runner=runner)
        second = render_local(self.run_id, "candidate-1", workspace_root=self.workspace, runner=runner)
        forced = render_local(self.run_id, "candidate-1", workspace_root=self.workspace, runner=runner, force=True)
        self.assertFalse(first.reused)
        self.assertTrue(second.reused)
        self.assertFalse(forced.reused)
        self.assertEqual(len(runner.commands), 2)
        self.assertTrue(first.output_path.is_file())
        self.assertEqual(first.render_output.status.value, "succeeded")
        kinds = {item.kind for item in load_run(self.run_id, workspace_root=self.workspace).run.artifacts}
        self.assertIn("render:candidate-1", kinds)
        self.assertIn("render_output:candidate-1", kinds)
        srt = self.context.run_directory / "tmp" / f"{self.plan.plan_id}.srt"
        self.assertIn("Opening caption.", srt.read_text())

    def test_failure_does_not_update_manifest_or_leave_valid_output(self):
        with self.assertRaisesRegex(RenderExecutionError, "simulated failure"):
            render_local(self.run_id, "candidate-1", workspace_root=self.workspace, runner=FakeRunner(returncode=1))
        self.assertFalse((self.context.run_directory / "renders" / "candidate-1.mp4").exists())
        kinds = {item.kind for item in load_run(self.run_id, workspace_root=self.workspace).run.artifacts}
        self.assertNotIn("render:candidate-1", kinds)
        self.assertNotIn("render_output:candidate-1", kinds)

    def test_invalid_range_and_missing_ffmpeg_are_rejected(self):
        payload = self.plan.to_dict()
        payload["source_time_range"]["end_ms"] = 40_000
        (self.context.run_directory / "render_plan_candidate-1.json").write_text(json.dumps(payload))
        with self.assertRaisesRegex(RenderExecutionError, "exceeds source duration"):
            render_local(self.run_id, "candidate-1", workspace_root=self.workspace, runner=FakeRunner())
        (self.context.run_directory / "render_plan_candidate-1.json").write_text(json.dumps(self.plan.to_dict()))
        with self.assertRaises(FFmpegUnavailableError):
            render_local(self.run_id, "candidate-1", workspace_root=self.workspace, executable="definitely-missing-ffmpeg")

    def test_subprocess_uses_argument_list_without_shell(self):
        completed = subprocess.CompletedProcess(["ffmpeg"], 0, "", "")
        with patch("shorts_pipeline.rendering.subprocess.run", return_value=completed) as run:
            FFmpegRunner().run(["ffmpeg", "-version"])
        self.assertEqual(run.call_args.args[0], ["ffmpeg", "-version"])
        self.assertNotIn("shell", run.call_args.kwargs)

