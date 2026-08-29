"""Hybrid evaluator: deterministic signals plus a provider-neutral semantic adapter."""
from __future__ import annotations
from dataclasses import replace
import json
from pathlib import Path
from .adapters.evaluation.contracts import CandidateEvaluationRequest,CandidateEvaluator
from .domain import ArtifactRef,ShortCandidate
from .evaluation import CandidateEvaluation,EvaluationConfig,EvaluationError,evaluate_deterministically,DIMENSIONS
from .runs import load_run,update_run_artifact,RunError
class SemanticEvaluationError(RuntimeError):pass
def _items(path,key):
 try:return json.loads(path.read_text())[key]
 except (OSError,KeyError,json.JSONDecodeError):return []
def hybrid_evaluate_and_rank(run_id,*,workspace_root='workspace',evaluator:CandidateEvaluator,force=False,config:EvaluationConfig=EvaluationConfig()):
 try:context=load_run(run_id,workspace_root=workspace_root)
 except RunError as e:raise SemanticEvaluationError(str(e)) from e
 ep,rp=context.run_directory/'evaluations.json',context.run_directory/'ranked_candidates.json'
 try:candidates=tuple(ShortCandidate.from_dict(x) for x in _items(context.run_directory/'candidates.json','candidates'))
 except (ValueError,TypeError) as e:raise SemanticEvaluationError('candidates are malformed') from e
 if not candidates:raise SemanticEvaluationError('candidates are missing or empty')
 scenes=_items(context.run_directory/'scenes.json','scenes');transcript=_items(context.run_directory/'transcript.json','segments');understanding=_items(context.run_directory/'video_understanding.json','understanding').get('items',[]) if isinstance(_items(context.run_directory/'video_understanding.json','understanding'),dict) else [];observations=_items(context.run_directory/'visual_analysis.json','observations')
 values=[]
 for candidate in candidates:
  request=CandidateEvaluationRequest(candidate,tuple(x for x in scenes if x.get('scene_id') in candidate.scene_ids),tuple(transcript),tuple(x for x in understanding if x.get('item_id') in candidate.metadata.get('understanding_item_ids',[])),tuple(x for x in observations if x.get('observation_id') in candidate.metadata.get('observation_ids',[])))
  try:semantic=evaluator.evaluate(request)
  except Exception as e:raise SemanticEvaluationError(f'semantic evaluator failed for {candidate.candidate_id}: {e}') from e
  if semantic.candidate_id!=candidate.candidate_id:raise SemanticEvaluationError('semantic evaluator returned a mismatched candidate')
  base=evaluate_deterministically(candidate,config);scores=dict(base.scores);scores.update(semantic.scores);total=sum(scores[k]*config.weights[k] for k in DIMENSIONS)/sum(config.weights.values());values.append(CandidateEvaluation(candidate.candidate_id,scores,{**base.rationales,**semantic.rationales},base.evidence,round(total,3),semantic.uncertainty))
 ranked=sorted(values,key=lambda x:(-x.quality_score,-x.scores['evidence_confidence'],next(c.time_range.start_ms for c in candidates if c.candidate_id==x.candidate_id),x.candidate_id))
 ep.write_text(json.dumps({'run_id':run_id,'source_id':context.source.source_id,'method':'hybrid-ollama-heuristic-v1','evaluations':[x.to_dict() for x in values]},indent=2)+'\n');rp.write_text(json.dumps({'run_id':run_id,'ranked_candidates':[{'rank':i+1,'candidate_id':x.candidate_id,'quality_score':x.quality_score,'scores':x.scores} for i,x in enumerate(ranked)]},indent=2)+'\n');update_run_artifact(context,ArtifactRef(f'artifact-{run_id}-evaluations','evaluations',ep.as_posix(),'application/json',{'method':'hybrid-ollama-heuristic-v1'}),stage='candidate_evaluation');return tuple(values)
