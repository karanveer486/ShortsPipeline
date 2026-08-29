import json,tempfile,unittest
from pathlib import Path
from shorts_pipeline.adapters.evaluation.contracts import SemanticEvaluation
from shorts_pipeline.adapters.evaluation.ollama import parse_semantic_evaluation,OllamaCandidateEvaluationError
from shorts_pipeline.domain import MediaMetadata,ShortCandidate,TimeRange
from shorts_pipeline.ingestion import ingest_local_source
from shorts_pipeline.semantic_evaluation import hybrid_evaluate_and_rank,SemanticEvaluationError
class Fake:
 def evaluate(self,r):return SemanticEvaluation(r.candidate.candidate_id,{'hook_strength':8,'narrative_coherence':7,'payoff_strength':6,'visual_clarity':7,'context_independence':5,'novelty':4,'transcript_usefulness':6},{'hook_strength':'clear opening'},.2)
class Bad:
 def evaluate(self,r):return SemanticEvaluation('other',{'hook_strength':1,'narrative_coherence':1,'payoff_strength':1,'visual_clarity':1,'context_independence':1,'novelty':1,'transcript_usefulness':1},{})
class Tests(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory();root=Path(self.t.name);s=root/'x.mp4';s.write_bytes(b'x');self.w=root/'w';self.id=ingest_local_source(s,workspace_root=self.w,probe=lambda _:MediaMetadata(30000,1,1,1)).run.run_id;d=self.w/'runs'/self.id;sid=json.loads((d/'manifest.json').read_text())['source']['source_id'];c=ShortCandidate('c',sid,TimeRange(0,20000),('s',),'event',score=.8,metadata={'understanding_item_ids':['u'],'observation_ids':['o']});(d/'candidates.json').write_text(json.dumps({'candidates':[c.to_dict()]}));(d/'scenes.json').write_text(json.dumps({'scenes':[{'scene_id':'s'}]}));(d/'transcript.json').write_text(json.dumps({'segments':[]}));(d/'video_understanding.json').write_text(json.dumps({'understanding':{'items':[{'item_id':'u'}]}}));(d/'visual_analysis.json').write_text(json.dumps({'observations':[{'observation_id':'o'}]}))
 def tearDown(self):self.t.cleanup()
 def test_hybrid_aggregation_and_evidence(self):
  e=hybrid_evaluate_and_rank(self.id,workspace_root=self.w,evaluator=Fake())[0];self.assertEqual(e.scores['hook_strength'],8);self.assertEqual(e.evidence['observation_ids'],['o']);self.assertGreater(e.quality_score,4)
 def test_invalid_provider_data(self):
  with self.assertRaises(SemanticEvaluationError):hybrid_evaluate_and_rank(self.id,workspace_root=self.w,evaluator=Bad())
  with self.assertRaises(OllamaCandidateEvaluationError):parse_semantic_evaluation({'message':{'content':'nope'}},'c')
  with self.assertRaises(OllamaCandidateEvaluationError):parse_semantic_evaluation({'message':{'content':'{"candidate_id":"wrong","scores":{}}'}},'c')
