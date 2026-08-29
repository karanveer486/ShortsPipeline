"""Standalone command-line entry point for local FFmpeg rendering."""

from __future__ import annotations

import argparse
import sys

from .rendering import RenderExecutionError, render_local


def main() -> int:
    parser = argparse.ArgumentParser(prog="shorts-pipeline render", description="Render one existing ShortsPipeline RenderPlan locally with FFmpeg")
    commands = parser.add_subparsers(dest="command", required=True)
    render = commands.add_parser("render", help="render one explicit candidate plan")
    render.add_argument("run_id")
    render.add_argument("candidate_id")
    render.add_argument("--workspace", default="workspace")
    render.add_argument("--force", action="store_true", help="re-render even when a valid output exists")
    args = parser.parse_args()
    try:
        result = render_local(args.run_id, args.candidate_id, workspace_root=args.workspace, force=args.force)
    except RenderExecutionError as error:
        parser.error(str(error))
    action = "reused" if result.reused else "rendered"
    print(f"{action}: run={args.run_id} candidate={args.candidate_id} plan={result.render_output.plan_id} output={result.output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
