"""Ollama implementation of semantic candidate evaluation."""
from __future__ import annotations
import json
from typing import Any,Mapping
from ..vlm.ollama import Transport,_post_json,_strip_json_fence,OllamaVLMError
from .contracts import CandidateEvaluationRequest,CandidateEvaluator,SemanticEvaluation,SEMANTIC_DIMENSIONS
class OllamaCandidateEvaluationError(RuntimeError):pass
def parse_semantic_evaluation(response:Mapping[str,Any],candidate_id:str)->SemanticEvaluation:
 message=response.get('message');content=message.get('content') if isinstance(message,Mapping) else None
 try:data=json.loads(_strip_json_fence(content)) if isinstance(content,str) else None
 except json.JSONDecodeError as error:raise OllamaCandidateEvaluationError('Ollama evaluation is not valid JSON') from error
 if not isinstance(data,Mapping) or data.get('candidate_id')!=candidate_id:raise OllamaCandidateEvaluationError('Ollama evaluation has an invalid candidate ID')
 try:return SemanticEvaluation(candidate_id,data['scores'],data.get('rationales',{}),data.get('uncertainty',0.0))
 except (KeyError,ValueError,TypeError) as error:raise OllamaCandidateEvaluationError('Ollama evaluation has invalid scores') from error
class OllamaCandidateEvaluator:
 def __init__(self,*,model='qwen2.5vl:7b',endpoint='http://127.0.0.1:11434/api/chat',timeout_seconds=90,transport:Transport=_post_json):self.model,self.endpoint,self.timeout_seconds,self._transport=model,endpoint,timeout_seconds,transport
 def evaluate(self,request:CandidateEvaluationRequest)->SemanticEvaluation:
  prompt='Evaluate this candidate as a heuristic only; never predict views or virality. Return JSON only. candidate_id must exactly equal '+request.candidate.candidate_id+'. scores must be a nested object (never top-level) containing exactly these integer 0..10 keys: hook_strength, narrative_coherence, payoff_strength, visual_clarity, context_independence, novelty, transcript_usefulness. Scale: 0=no supporting evidence or absent; 1-3=weak/incomplete; 4-6=moderate; 7-8=strong and self-contained; 9-10=exceptionally strong. rationales must be an object with a concise rationale for every score. uncertainty is 0..1. Cite only supplied context. Context: '+json.dumps({'candidate':request.candidate.to_dict(),'scenes':request.scenes,'transcript':request.transcript,'understanding':request.understanding,'observations':request.observations})
  body=json.dumps({'model':self.model,'stream':False,'format':'json','options':{'temperature':0},'messages':[{'role':'user','content':prompt}]}).encode()
  try:return parse_semantic_evaluation(self._transport(self.endpoint,body,self.timeout_seconds),request.candidate.candidate_id)
  except OllamaVLMError as error:raise OllamaCandidateEvaluationError(str(error)) from error
