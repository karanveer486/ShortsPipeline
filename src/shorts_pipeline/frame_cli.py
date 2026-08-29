"""Standalone command-line entry point for the frame-extraction stage."""

from __future__ import annotations

import argparse
import sys

from .frame_extraction import FrameExtractionError, extract_frames


def main() -> int:
    parser = argparse.ArgumentParser(prog="shorts-pipeline extract-frames", description="Extract timestamped frames from an existing ShortsPipeline run")
    parser.add_argument("run_id", help="existing run identifier with scenes.json")
    parser.add_argument("--workspace", default="workspace", help="runtime workspace root (default: workspace)")
    parser.add_argument("--config", default="config/pipeline.toml", help="optional local TOML configuration")
    parser.add_argument("--strategy", choices=("interval", "scene-relative"), help="frame sampling strategy")
    parser.add_argument("--interval-ms", type=int, help="interval strategy sampling period in milliseconds")
    parser.add_argument("--force", action="store_true", help="recompute even when frames.json exists")
    arguments = parser.parse_args()
    try:
        frames = extract_frames(arguments.run_id, workspace_root=arguments.workspace, config_path=arguments.config, strategy=arguments.strategy, interval_ms=arguments.interval_ms, force=arguments.force)
    except FrameExtractionError as error:
        parser.error(str(error))
    print(f"{len(frames)} frames")
    return 0


if __name__ == "__main__":
    sys.exit(main())
