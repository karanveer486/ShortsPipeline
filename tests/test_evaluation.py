import json,tempfile,unittest
from pathlib import Path
from shorts_pipeline.domain import MediaMetadata,ShortCandidate,TimeRange
from shorts_pipeline.ingestion import ingest_local_source
from shorts_pipeline.evaluation import EvaluationConfig,EvaluationError,evaluate_and_rank,evaluate_deterministically
from shorts_pipeline.runs import load_run
class Tests(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory();r=Path(self.t.name);s=r/'x.mp4';s.write_bytes(b'x');self.w=r/'w';self.id=ingest_local_source(s,workspace_root=self.w,probe=lambda _:MediaMetadata(30000,1,1,1)).run.run_id;self.c=load_run(self.id,workspace_root=self.w);cs=[ShortCandidate('a',self.c.source.source_id,TimeRange(0,20000),('s1',),'event',score=.8,metadata={'understanding_item_ids':['u'],'observation_ids':['o']}),ShortCandidate('b',self.c.source.source_id,TimeRange(20000,25000),('s2',),'event',score=.2,metadata={})];(self.c.run_directory/'candidates.json').write_text(json.dumps({'candidates':[x.to_dict() for x in cs]}))
 def tearDown(self):self.t.cleanup()
 def test_scores_and_rank(self):
  x=evaluate_deterministically(ShortCandidate('x','s',TimeRange(0,20000),('z',),'r'),EvaluationConfig());self.assertEqual(set(x.scores),set(__import__('shorts_pipeline.evaluation',fromlist=['DIMENSIONS']).DIMENSIONS));r=evaluate_and_rank(self.id,workspace_root=self.w);self.assertEqual(r[0].candidate_id,'a');self.assertTrue((self.c.run_directory/'ranked_candidates.json').is_file())
 def test_reuse_and_errors(self):
  a=evaluate_and_rank(self.id,workspace_root=self.w);self.assertEqual(a,evaluate_and_rank(self.id,workspace_root=self.w));self.assertTrue(any(x.kind=='evaluations' for x in load_run(self.id,workspace_root=self.w).run.artifacts));
  with self.assertRaises(EvaluationError):evaluate_and_rank('none',workspace_root=self.w)
 def test_validation(self):
  with self.assertRaises(ValueError):EvaluationConfig(9,2)
