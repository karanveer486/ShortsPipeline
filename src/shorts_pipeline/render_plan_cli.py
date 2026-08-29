"""Command line interface for JSON-only render planning."""

from __future__ import annotations

import argparse
import sys

from .render_planning import RenderPlanningError, create_render_plan, render_planning_config


def main() -> int:
    parser = argparse.ArgumentParser(prog="shorts-pipeline render-plan", description="Create a deterministic JSON render plan without rendering media")
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create", help="plan one explicit candidate")
    create.add_argument("run_id")
    create.add_argument("candidate_id")
    create.add_argument("--workspace", default="workspace")
    create.add_argument("--config")
    create.add_argument("--force", action="store_true")
    args = parser.parse_args()
    try:
        plan = create_render_plan(args.run_id, args.candidate_id, workspace_root=args.workspace,
                                  config=render_planning_config(args.config), force=args.force)
    except RenderPlanningError as error:
        parser.error(str(error))
    print(plan.plan_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
