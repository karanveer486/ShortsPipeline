"""CLI for the proof-of-integration local visual analysis stage."""
from __future__ import annotations

import argparse
import sys

from .visual_analysis import VisualAnalysisError, analyze_run


def main() -> int:
    parser = argparse.ArgumentParser(prog="shorts-pipeline vlm", description="Analyze extracted frames with a local VLM backend")
    commands = parser.add_subparsers(dest="command", required=True)
    analyze = commands.add_parser("analyze", help="analyze extracted frames for an existing run")
    analyze.add_argument("run_id")
    analyze.add_argument("--workspace", default="workspace")
    analyze.add_argument("--config", default="config/pipeline.toml")
    analyze.add_argument("--model", help="override configured local model")
    analyze.add_argument("--instructions", help="optional raw visual-analysis guidance")
    analyze.add_argument("--force", action="store_true")
    arguments = parser.parse_args()
    try:
        observations = analyze_run(arguments.run_id, workspace_root=arguments.workspace, config_path=arguments.config, model=arguments.model, instructions=arguments.instructions, force=arguments.force)
    except VisualAnalysisError as error:
        parser.error(str(error))
    print(f"{len(observations)} visual observations")
    return 0


if __name__ == "__main__":
    sys.exit(main())
