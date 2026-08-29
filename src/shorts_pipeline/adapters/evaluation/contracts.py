"""Provider-neutral semantic candidate-evaluation boundary."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Mapping, Protocol
from ...domain import ShortCandidate

SEMANTIC_DIMENSIONS=("hook_strength","narrative_coherence","payoff_strength","visual_clarity","context_independence","novelty","transcript_usefulness")
@dataclass(frozen=True)
class CandidateEvaluationRequest:
 candidate:ShortCandidate; scenes:tuple[Mapping[str,object],...]; transcript:tuple[Mapping[str,object],...]; understanding:tuple[Mapping[str,object],...]; observations:tuple[Mapping[str,object],...]
@dataclass(frozen=True)
class SemanticEvaluation:
 candidate_id:str; scores:Mapping[str,int]; rationales:Mapping[str,str]; uncertainty:float=0.0
 def __post_init__(self):
  if not self.candidate_id or set(self.scores)!=set(SEMANTIC_DIMENSIONS):raise ValueError('semantic evaluation requires all semantic dimensions')
  if any(isinstance(x,bool) or not isinstance(x,int) or not 0<=x<=10 for x in self.scores.values()):raise ValueError('semantic scores must be integers 0..10')
  if not 0<=self.uncertainty<=1:raise ValueError('uncertainty must be 0..1')
class CandidateEvaluator(Protocol):
 def evaluate(self,request:CandidateEvaluationRequest)->SemanticEvaluation:...
