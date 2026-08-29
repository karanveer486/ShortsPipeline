"""Command-line entry point for the currently implemented local stages."""

from __future__ import annotations

import argparse
import sys

from .ingestion import IngestionError, ingest_local_source


def main() -> int:
    parser = argparse.ArgumentParser(prog="shorts-pipeline", description="Local-first ShortsPipeline utilities")
    subparsers = parser.add_subparsers(dest="command", required=True)
    ingest = subparsers.add_parser("ingest", help="inspect a local video with ffprobe and create a run manifest")
    ingest.add_argument("source", help="path to a local source video")
    ingest.add_argument("--workspace", default="workspace", help="runtime workspace root (default: workspace)")
    arguments = parser.parse_args()

    if arguments.command == "ingest":
        try:
            result = ingest_local_source(arguments.source, workspace_root=arguments.workspace)
        except IngestionError as error:
            parser.error(str(error))
        print(result.manifest_path)
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
