from __future__ import annotations
import argparse, sys
from .candidate_discovery import CandidateDiscoveryError, discover_candidates
def main() -> int:
 parser=argparse.ArgumentParser(prog="shorts-pipeline candidates",description="Discover evidence-backed Short candidates from video understanding")
 commands=parser.add_subparsers(dest="command",required=True); discover=commands.add_parser("discover")
 discover.add_argument("run_id"); discover.add_argument("--workspace",default="workspace"); discover.add_argument("--preferred-min-ms",type=int,default=15000); discover.add_argument("--preferred-max-ms",type=int,default=60000); discover.add_argument("--force",action="store_true")
 args=parser.parse_args()
 try: candidates=discover_candidates(args.run_id,workspace_root=args.workspace,preferred_min_ms=args.preferred_min_ms,preferred_max_ms=args.preferred_max_ms,force=args.force)
 except CandidateDiscoveryError as error: parser.error(str(error))
 print(f"{len(candidates)} candidates"); return 0
if __name__=="__main__": sys.exit(main())
