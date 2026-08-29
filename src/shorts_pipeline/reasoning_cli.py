from __future__ import annotations
import argparse, sys
from .reasoning import ReasoningError, understand_run
def main() -> int:
    parser = argparse.ArgumentParser(prog="shorts-pipeline reasoning", description="Build structured video understanding from existing run artifacts")
    commands = parser.add_subparsers(dest="command", required=True); understand = commands.add_parser("understand")
    understand.add_argument("run_id"); understand.add_argument("--workspace", default="workspace"); understand.add_argument("--max-duration-ms", type=int, default=60000); understand.add_argument("--force", action="store_true")
    args = parser.parse_args()
    try: result = understand_run(args.run_id, workspace_root=args.workspace, max_duration_ms=args.max_duration_ms, force=args.force)
    except ReasoningError as error: parser.error(str(error))
    print(f"{len(result.items)} understanding items"); return 0
if __name__ == "__main__": sys.exit(main())
