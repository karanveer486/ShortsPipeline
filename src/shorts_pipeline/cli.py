"""Timeline-aware command-line entry point.

Use ``python -m shorts_pipeline.cli`` until the package's legacy entry point is
updated to delegate here.
"""

from __future__ import annotations

import argparse
import sys

from .ingestion import IngestionError, ingest_local_source
from .scene_detection import SceneDetectionError, detect_scenes
from .transcription import TranscriptionError, transcribe_run


def main() -> int:
    parser = argparse.ArgumentParser(prog="shorts-pipeline", description="Local-first ShortsPipeline utilities")
    subparsers = parser.add_subparsers(dest="command", required=True)
    ingest = subparsers.add_parser("ingest", help="inspect a local video with ffprobe and create a run manifest")
    ingest.add_argument("source", help="path to a local source video")
    ingest.add_argument("--workspace", default="workspace", help="runtime workspace root (default: workspace)")
    transcribe = subparsers.add_parser("transcribe", help="transcribe an existing run using local Whisper")
    transcribe.add_argument("run_id", help="existing ingestion run identifier")
    transcribe.add_argument("--workspace", default="workspace", help="runtime workspace root (default: workspace)")
    transcribe.add_argument("--config", default="config/pipeline.toml", help="optional local TOML configuration")
    transcribe.add_argument("--model", help="override the configured Whisper model")
    transcribe.add_argument("--force", action="store_true", help="recompute even when transcript.json exists")
    scenes = subparsers.add_parser("detect-scenes", help="detect scenes for an existing run using PySceneDetect")
    scenes.add_argument("run_id", help="existing ingestion run identifier")
    scenes.add_argument("--workspace", default="workspace", help="runtime workspace root (default: workspace)")
    scenes.add_argument("--config", default="config/pipeline.toml", help="optional local TOML configuration")
    scenes.add_argument("--force", action="store_true", help="recompute even when scenes.json exists")
    arguments = parser.parse_args()

    try:
        if arguments.command == "ingest":
            print(ingest_local_source(arguments.source, workspace_root=arguments.workspace).manifest_path)
        elif arguments.command == "transcribe":
            print(f"{len(transcribe_run(arguments.run_id, workspace_root=arguments.workspace, config_path=arguments.config, model=arguments.model, force=arguments.force).segments)} transcript segments")
        elif arguments.command == "detect-scenes":
            print(f"{len(detect_scenes(arguments.run_id, workspace_root=arguments.workspace, config_path=arguments.config, force=arguments.force))} scenes")
    except (IngestionError, TranscriptionError, SceneDetectionError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    sys.exit(main())
