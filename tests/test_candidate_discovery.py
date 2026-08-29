import json,tempfile,unittest
from pathlib import Path
from shorts_pipeline.candidate_discovery import CandidateDiscoveryConfig,CandidateDiscoveryError,discover_candidates,propose_candidates
from shorts_pipeline.domain import MediaMetadata,Scene,TimeRange,VideoUnderstanding,UnderstandingItem,EvidenceRef
from shorts_pipeline.ingestion import ingest_local_source
from shorts_pipeline.runs import load_run
class CandidateDiscoveryTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory(); root=Path(self.temp.name); source=root/'source.mp4';source.write_bytes(b'x');self.workspace=root/'workspace';self.run_id=ingest_local_source(source,workspace_root=self.workspace,probe=lambda _:MediaMetadata(30000,320,240,30)).run.run_id;self.context=load_run(self.run_id,workspace_root=self.workspace);sid=self.context.source.source_id
  self.scenes=(Scene('s1',sid,0,TimeRange(0,10000)),Scene('s2',sid,1,TimeRange(10000,20000)),Scene('s3',sid,2,TimeRange(20000,30000)))
  understanding=VideoUnderstanding('u',sid,(UnderstandingItem('u1','event','A car is pursued.',EvidenceRef(('s1','s2'),(TimeRange(0,20000),)),.8,{'observation_ids':['o1','o2']}),))
  (self.context.run_directory/'scenes.json').write_text(json.dumps({'scenes':[x.to_dict() for x in self.scenes]}));(self.context.run_directory/'video_understanding.json').write_text(json.dumps({'understanding':understanding.to_dict()}))
 def tearDown(self):self.temp.cleanup()
 def test_proposal_contiguity_evidence_and_stable_id(self):
  u=VideoUnderstanding.from_dict(json.loads((self.context.run_directory/'video_understanding.json').read_text())['understanding']);first=propose_candidates(self.run_id,self.scenes,u,CandidateDiscoveryConfig());second=propose_candidates(self.run_id,self.scenes,u,CandidateDiscoveryConfig());self.assertEqual(first,second);self.assertEqual(first[0].scene_ids,('s1','s2'));self.assertEqual(first[0].metadata['understanding_item_ids'],['u1'])
 def test_write_reuse_and_duration_handling(self):
  first=discover_candidates(self.run_id,workspace_root=self.workspace);second=discover_candidates(self.run_id,workspace_root=self.workspace);self.assertEqual(first,second);self.assertTrue((self.context.run_directory/'candidates.json').is_file());self.assertTrue(first[0].metadata['duration_within_preferred_range']);self.assertTrue(any(x.kind=='candidates' for x in load_run(self.run_id,workspace_root=self.workspace).run.artifacts))
 def test_invalid_input(self):
  with self.assertRaises(CandidateDiscoveryError):discover_candidates('missing',workspace_root=self.workspace)
  with self.assertRaises(ValueError):CandidateDiscoveryConfig(10000,5000)
