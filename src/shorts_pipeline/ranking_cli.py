from __future__ import annotations
import argparse,sys
from .evaluation import EvaluationError,evaluate_and_rank
def main():
 p=argparse.ArgumentParser(prog='shorts-pipeline ranking');s=p.add_subparsers(dest='command',required=True);e=s.add_parser('evaluate');e.add_argument('run_id');e.add_argument('--workspace',default='workspace');e.add_argument('--force',action='store_true');a=p.parse_args()
 try:r=evaluate_and_rank(a.run_id,workspace_root=a.workspace,force=a.force)
 except EvaluationError as x:p.error(str(x))
 print(f'{len(r)} evaluations');return 0
if __name__=='__main__':sys.exit(main())
