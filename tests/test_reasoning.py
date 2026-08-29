import json, tempfile, unittest
from pathlib import Path
from shorts_pipeline.domain import ArtifactRef, MediaMetadata, Scene, TimeRange, TranscriptSegment, UnderstandingItem, EvidenceRef, VisualObservation
from shorts_pipeline.ingestion import ingest_local_source
from shorts_pipeline.reasoning import chunk_scenes, understand_run, ChunkingConfig, ReasoningError
from shorts_pipeline.runs import load_run

class FakeReasoner:
 def reason_chunk(self, chunk):
  return (UnderstandingItem(f"item-{chunk.chunk_id}", "event", "A supported event.", EvidenceRef((chunk.scenes[0].scene_id,), (chunk.scenes[0].time_range,)), .8, {"observation_ids":[item.observation_id for item in chunk.observations]}),)
 def merge(self, source_id, chunks): return tuple(item for chunk in chunks for item in chunk)
class FailingReasoner:
 def reason_chunk(self, chunk): raise RuntimeError("offline")
 def merge(self, source_id, chunks): return ()
class ReasoningTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory(); root=Path(self.temp.name); self.source=root/'source.mp4'; self.source.write_bytes(b'x'); self.workspace=root/'workspace'; self.run_id=ingest_local_source(self.source,workspace_root=self.workspace,probe=lambda _:MediaMetadata(4000,320,240,30)).run.run_id; self.context=load_run(self.run_id,workspace_root=self.workspace); sid=self.context.source.source_id
  scenes=(Scene('scene-1',sid,0,TimeRange(0,2000)),Scene('scene-2',sid,1,TimeRange(2000,4000)))
  (self.context.run_directory/'scenes.json').write_text(json.dumps({'scenes':[x.to_dict() for x in scenes]})); (self.context.run_directory/'transcript.json').write_text(json.dumps({'segments':[TranscriptSegment('t',TimeRange(0,3000),'hello').to_dict()]})); (self.context.run_directory/'visual_analysis.json').write_text(json.dumps({'observations':[VisualObservation('o',sid,TimeRange(0,2000),{'objects':['car']},scene_id='scene-1').to_dict()]}))
 def tearDown(self): self.temp.cleanup()
 def test_chunking_associates_evidence(self):
  chunks=chunk_scenes(self.context,tuple(Scene.from_dict(x) for x in json.loads((self.context.run_directory/'scenes.json').read_text())['scenes']),(TranscriptSegment('t',TimeRange(0,3000),'hello'),),(VisualObservation('o',self.context.source.source_id,TimeRange(0,2000),{'x':[]},scene_id='scene-1'),),ChunkingConfig(2000)); self.assertEqual(len(chunks),2); self.assertEqual(chunks[0].observations[0].observation_id,'o')
 def test_restart_and_artifact(self):
  first=understand_run(self.run_id,workspace_root=self.workspace,reasoner=FakeReasoner()); second=understand_run(self.run_id,workspace_root=self.workspace,reasoner=FailingReasoner()); self.assertEqual(first,second); self.assertTrue(any(x.kind=='video_understanding' for x in load_run(self.run_id,workspace_root=self.workspace).run.artifacts))
 def test_failure_and_malformed(self):
  with self.assertRaises(ReasoningError): understand_run(self.run_id,workspace_root=self.workspace,reasoner=FailingReasoner())
