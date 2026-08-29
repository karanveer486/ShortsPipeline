"""Transparent heuristic evaluation and deterministic ranking of candidates."""
from __future__ import annotations
from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Mapping
from .domain import ArtifactRef, ShortCandidate
from .runs import RunError, load_run, update_run_artifact

DIMENSIONS=("hook_strength","narrative_coherence","payoff_strength","visual_clarity","context_independence","novelty","transcript_usefulness","duration_fit","evidence_confidence","boundary_quality")
class EvaluationError(RuntimeError): pass
@dataclass(frozen=True)
class CandidateEvaluation:
 candidate_id:str; scores:Mapping[str,int]; rationales:Mapping[str,str]; evidence:Mapping[str,object]; quality_score:float; uncertainty:float=0.0
 def __post_init__(self):
  if not self.candidate_id or set(self.scores)!=set(DIMENSIONS): raise ValueError("evaluation must provide all dimensions")
  if any(isinstance(x,bool) or not isinstance(x,int) or not 0<=x<=10 for x in self.scores.values()): raise ValueError("dimension scores must be integers from 0 to 10")
  if not 0<=self.quality_score<=10 or not 0<=self.uncertainty<=1: raise ValueError("invalid aggregate score or uncertainty")
 def to_dict(self): return {"candidate_id":self.candidate_id,"scores":dict(self.scores),"rationales":dict(self.rationales),"evidence":dict(self.evidence),"quality_score":self.quality_score,"uncertainty":self.uncertainty}
 @classmethod
 def from_dict(cls,d): return cls(d['candidate_id'],d['scores'],d.get('rationales',{}),d.get('evidence',{}),d['quality_score'],d.get('uncertainty',0.0))
@dataclass(frozen=True)
class EvaluationConfig:
 preferred_min_ms:int=15000; preferred_max_ms:int=60000; weights:Mapping[str,float]=field(default_factory=lambda:{name:1.0 for name in DIMENSIONS})
 def __post_init__(self):
  if self.preferred_min_ms<=0 or self.preferred_max_ms<self.preferred_min_ms or set(self.weights)!=set(DIMENSIONS) or any(x<0 for x in self.weights.values()): raise ValueError("invalid evaluation configuration")

def evaluate_deterministically(candidate:ShortCandidate, config:EvaluationConfig)->CandidateEvaluation:
 duration=candidate.time_range.duration_ms; fit=10 if config.preferred_min_ms<=duration<=config.preferred_max_ms else max(0,10-round(min(abs(duration-config.preferred_min_ms),abs(duration-config.preferred_max_ms))/10000))
 evidence_ids=candidate.metadata.get('understanding_item_ids',[]); observations=candidate.metadata.get('observation_ids',[])
 confidence=round((candidate.score or 0)*10); continuity=10 if candidate.scene_ids else 0; completeness=min(10,4+2*len(evidence_ids)+len(observations))
 scores={"hook_strength":0,"narrative_coherence":min(10,5+len(candidate.scene_ids)),"payoff_strength":0,"visual_clarity":min(10,3+len(observations)),"context_independence":min(10,3+len(evidence_ids)),"novelty":0,"transcript_usefulness":0,"duration_fit":fit,"evidence_confidence":min(confidence,completeness),"boundary_quality":continuity}
 total=sum(scores[k]*config.weights[k] for k in DIMENSIONS); divisor=sum(config.weights.values()) or 1
 return CandidateEvaluation(candidate.candidate_id,scores,{"duration_fit":"Based on configured preferred duration.","evidence_confidence":"Based on discovery confidence and cited evidence.","boundary_quality":"Candidate spans contiguous referenced scenes."},{"scene_ids":list(candidate.scene_ids),"understanding_item_ids":evidence_ids,"observation_ids":observations},round(total/divisor,3),uncertainty=0.5)

def evaluate_and_rank(run_id:str,*,workspace_root:str|Path="workspace",force:bool=False,config:EvaluationConfig=EvaluationConfig())->tuple[CandidateEvaluation,...]:
 try: context=load_run(run_id,workspace_root=workspace_root)
 except RunError as error: raise EvaluationError(str(error)) from error
 ep,rp=context.run_directory/'evaluations.json',context.run_directory/'ranked_candidates.json'
 if ep.is_file() and rp.is_file() and not force:
  try:return tuple(CandidateEvaluation.from_dict(x) for x in json.loads(ep.read_text())['evaluations'])
  except (OSError,KeyError,ValueError,json.JSONDecodeError) as error:raise EvaluationError("existing evaluations are malformed") from error
 try:candidates=tuple(ShortCandidate.from_dict(x) for x in json.loads((context.run_directory/'candidates.json').read_text())['candidates'])
 except (OSError,KeyError,ValueError,json.JSONDecodeError) as error:raise EvaluationError("candidates are missing or malformed") from error
 evaluations=tuple(evaluate_deterministically(x,config) for x in candidates)
 ranked=sorted(evaluations,key=lambda x:(-x.quality_score,-x.scores['evidence_confidence'],next(c.time_range.start_ms for c in candidates if c.candidate_id==x.candidate_id),x.candidate_id))
 try:
  ep.write_text(json.dumps({"run_id":run_id,"source_id":context.source.source_id,"method":"deterministic-heuristic-v1","evaluations":[x.to_dict() for x in evaluations]},indent=2)+"\n")
  rp.write_text(json.dumps({"run_id":run_id,"ranked_candidates":[{"rank":i+1,"candidate_id":x.candidate_id,"quality_score":x.quality_score,"scores":x.scores} for i,x in enumerate(ranked)]},indent=2)+"\n")
  update_run_artifact(context,ArtifactRef(f"artifact-{run_id}-evaluations","evaluations",ep.as_posix(),"application/json"),stage="candidate_evaluation");update_run_artifact(load_run(run_id,workspace_root=workspace_root),ArtifactRef(f"artifact-{run_id}-ranked-candidates","ranked_candidates",rp.as_posix(),"application/json"),stage="candidate_ranking")
 except (OSError,RunError) as error:raise EvaluationError(f"could not write evaluation artifacts: {error}") from error
 return evaluations
