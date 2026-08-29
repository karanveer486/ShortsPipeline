"""Deterministic, evidence-driven Short candidate discovery."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Iterable
from .domain import ArtifactRef, CandidateStatus, Scene, ShortCandidate, TimeRange, UnderstandingItem, VideoUnderstanding
from .runs import RunError, load_run, update_run_artifact

class CandidateDiscoveryError(RuntimeError): pass

@dataclass(frozen=True)
class CandidateDiscoveryConfig:
    preferred_min_ms: int = 15_000
    preferred_max_ms: int = 60_000
    def __post_init__(self) -> None:
        if not isinstance(self.preferred_min_ms, int) or not isinstance(self.preferred_max_ms, int) or self.preferred_min_ms <= 0 or self.preferred_max_ms < self.preferred_min_ms: raise ValueError("invalid preferred candidate duration range")

def _load(path: Path, factory: object, key: str) -> tuple[object, ...]:
    try: return tuple(factory.from_dict(x) for x in json.loads(path.read_text())[key])
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error: raise CandidateDiscoveryError(f"missing or malformed {key}: {path}") from error

def _candidate_id(run_id: str, scene_ids: tuple[str, ...], time_range: TimeRange) -> str:
    value = f"{run_id}|{','.join(scene_ids)}|{time_range.start_ms}|{time_range.end_ms}".encode()
    return f"candidate-{sha256(value).hexdigest()[:16]}"

def propose_candidates(run_id: str, scenes: tuple[Scene, ...], understanding: VideoUnderstanding, config: CandidateDiscoveryConfig) -> tuple[ShortCandidate, ...]:
    ordered = tuple(sorted(scenes, key=lambda item: item.index)); by_id = {item.scene_id: item for item in ordered}; results: dict[str, ShortCandidate] = {}
    for item in understanding.items:
        evidence_scenes = [by_id[scene_id] for scene_id in item.evidence.scene_ids if scene_id in by_id]
        ranges = list(item.evidence.time_ranges) or [scene.time_range for scene in evidence_scenes]
        if not ranges: continue
        start, end = min(value.start_ms for value in ranges), max(value.end_ms for value in ranges)
        selected = tuple(scene for scene in ordered if scene.time_range.start_ms < end and scene.time_range.end_ms > start)
        if not selected: continue
        time_range = TimeRange(selected[0].time_range.start_ms, selected[-1].time_range.end_ms)
        scene_ids = tuple(scene.scene_id for scene in selected); candidate_id = _candidate_id(run_id, scene_ids, time_range)
        duration_fit = config.preferred_min_ms <= time_range.duration_ms <= config.preferred_max_ms
        results[candidate_id] = ShortCandidate(candidate_id, understanding.source_id, time_range, scene_ids, item.statement, hook=None, payoff=None, score=item.confidence, status=CandidateStatus.PROPOSED, metadata={"discovery_method":"deterministic-evidence-v1","understanding_item_ids":[item.item_id],"duration_within_preferred_range":duration_fit,"evidence_scene_ids":list(item.evidence.scene_ids),"observation_ids":item.attributes.get("observation_ids", [])})
    return tuple(results[key] for key in sorted(results))

def discover_candidates(run_id: str, *, workspace_root: str | Path = "workspace", force: bool = False, preferred_min_ms: int = 15_000, preferred_max_ms: int = 60_000) -> tuple[ShortCandidate, ...]:
    try: context = load_run(run_id, workspace_root=workspace_root)
    except RunError as error: raise CandidateDiscoveryError(str(error)) from error
    output = context.run_directory / "candidates.json"
    if output.is_file() and not force:
        try: return tuple(ShortCandidate.from_dict(item) for item in json.loads(output.read_text())["candidates"])
        except (OSError, KeyError, ValueError, json.JSONDecodeError) as error: raise CandidateDiscoveryError(f"existing candidates are malformed: {output}") from error
    scenes = _load(context.run_directory / "scenes.json", Scene, "scenes")
    try: understanding = VideoUnderstanding.from_dict(json.loads((context.run_directory / "video_understanding.json").read_text())["understanding"])
    except (OSError, KeyError, ValueError, json.JSONDecodeError) as error: raise CandidateDiscoveryError("video understanding is missing or malformed") from error
    if understanding.source_id != context.source.source_id: raise CandidateDiscoveryError("video understanding belongs to another source")
    config = CandidateDiscoveryConfig(preferred_min_ms, preferred_max_ms)
    candidates = propose_candidates(run_id, scenes, understanding, config)
    payload = {"run_id":run_id,"source_id":context.source.source_id,"discovery":{"method":"deterministic-evidence-v1","preferred_min_ms":config.preferred_min_ms,"preferred_max_ms":config.preferred_max_ms,"backend":None},"candidates":[item.to_dict() for item in candidates]}
    try:
        output.write_text(json.dumps(payload, indent=2)+"\n")
        update_run_artifact(context, ArtifactRef(f"artifact-{run_id}-candidates","candidates",output.as_posix(),"application/json"),stage="candidate_discovery")
    except (OSError, RunError) as error: raise CandidateDiscoveryError(f"could not write candidates: {output}") from error
    return candidates
