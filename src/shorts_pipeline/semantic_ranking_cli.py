from __future__ import annotations
import argparse,sys
from .adapters.evaluation.ollama import OllamaCandidateEvaluator
from .semantic_evaluation import SemanticEvaluationError,hybrid_evaluate_and_rank
def main():
 p=argparse.ArgumentParser(prog='shorts-pipeline ranking semantic');p.add_argument('run_id');p.add_argument('--workspace',default='workspace');p.add_argument('--model',default='qwen2.5vl:7b');p.add_argument('--force',action='store_true');a=p.parse_args()
 try:r=hybrid_evaluate_and_rank(a.run_id,workspace_root=a.workspace,evaluator=OllamaCandidateEvaluator(model=a.model),force=a.force)
 except SemanticEvaluationError as e:p.error(str(e))
 print(f'{len(r)} hybrid evaluations');return 0
if __name__=='__main__':sys.exit(main())
