"""Chunked, restartable run-level video-understanding orchestration."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Iterable
from .adapters.reasoning.contracts import ReasoningChunk, VideoReasoner
from .adapters.reasoning.ollama import OllamaVideoReasoner
from .domain import ArtifactRef, Scene, TranscriptSegment, UnderstandingItem, VideoUnderstanding, VisualObservation
from .runs import RunContext, RunError, load_run, update_run_artifact

class ReasoningError(RuntimeError): pass
@dataclass(frozen=True)
class ChunkingConfig:
    max_duration_ms: int = 60_000
    def __post_init__(self) -> None:
        if not isinstance(self.max_duration_ms, int) or self.max_duration_ms <= 0: raise ValueError("max_duration_ms must be positive")

def chunk_scenes(context: RunContext, scenes: tuple[Scene, ...], transcript: tuple[TranscriptSegment, ...], observations: tuple[VisualObservation, ...], config: ChunkingConfig) -> tuple[ReasoningChunk, ...]:
    groups: list[list[Scene]] = []; current: list[Scene] = []
    for scene in scenes:
        if current and scene.time_range.end_ms - current[0].time_range.start_ms > config.max_duration_ms: groups.append(current); current = []
        current.append(scene)
    if current: groups.append(current)
    chunks = []
    for index, group in enumerate(groups):
        start, end = group[0].time_range.start_ms, group[-1].time_range.end_ms; ids = {item.scene_id for item in group}
        chunks.append(ReasoningChunk(f"chunk-{context.run.run_id}-{index:04d}", context.source.source_id, tuple(group), tuple(item for item in transcript if item.time_range.start_ms < end and item.time_range.end_ms > start), tuple(item for item in observations if item.scene_id in ids or (item.time_range.start_ms < end and item.time_range.end_ms > start))))
    return tuple(chunks)

def _load(path: Path, key: str, factory: object) -> tuple[object, ...]:
    try: data = json.loads(path.read_text(encoding="utf-8")); return tuple(factory.from_dict(item) for item in data[key])
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error: raise ReasoningError(f"missing or malformed {key}: {path}") from error

def understand_run(run_id: str, *, workspace_root: str | Path = "workspace", force: bool = False, max_duration_ms: int = 60_000, reasoner: VideoReasoner | None = None) -> VideoUnderstanding:
    try: context = load_run(run_id, workspace_root=workspace_root)
    except RunError as error: raise ReasoningError(str(error)) from error
    output = context.run_directory / "video_understanding.json"
    if output.is_file() and not force:
        try: return VideoUnderstanding.from_dict(json.loads(output.read_text())["understanding"])
        except (OSError, KeyError, ValueError, json.JSONDecodeError) as error: raise ReasoningError(f"existing understanding is malformed: {output}") from error
    scenes = _load(context.run_directory / "scenes.json", "scenes", Scene)
    transcript = _load(context.run_directory / "transcript.json", "segments", TranscriptSegment)
    observations = _load(context.run_directory / "visual_analysis.json", "observations", VisualObservation)
    chunks = chunk_scenes(context, scenes, transcript, observations, ChunkingConfig(max_duration_ms))
    worker = reasoner or OllamaVideoReasoner()
    chunk_items: list[tuple[UnderstandingItem, ...]] = []
    analysis_dir = context.run_directory / "analysis"; analysis_dir.mkdir(exist_ok=True)
    for chunk in chunks:
        path = analysis_dir / f"{chunk.chunk_id}.json"
        if path.is_file() and not force:
            try: items = tuple(UnderstandingItem.from_dict(item) for item in json.loads(path.read_text())["items"])
            except (OSError, KeyError, ValueError, json.JSONDecodeError) as error: raise ReasoningError(f"chunk result is malformed: {path}") from error
        else:
            try: items = worker.reason_chunk(chunk)
            except Exception as error: raise ReasoningError(f"chunk reasoning failed: {chunk.chunk_id}: {error}") from error
            path.write_text(json.dumps({"chunk_id": chunk.chunk_id, "items": [item.to_dict() for item in items]}, indent=2) + "\n")
        chunk_items.append(items)
    try: final_items = worker.merge(context.source.source_id, tuple(chunk_items))
    except Exception as error: raise ReasoningError(f"global reasoning failed: {error}") from error
    understanding = VideoUnderstanding(f"understanding-{run_id}", context.source.source_id, final_items)
    payload = {"run_id": run_id, "source_id": context.source.source_id, "backend": "ollama", "model": getattr(worker, "model", "custom"), "chunking": {"max_duration_ms": max_duration_ms}, "analyzed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), "chunks": [chunk.chunk_id for chunk in chunks], "understanding": understanding.to_dict()}
    try:
        output.write_text(json.dumps(payload, indent=2) + "\n")
        update_run_artifact(context, ArtifactRef(f"artifact-{run_id}-video-understanding", "video_understanding", output.as_posix(), "application/json"), stage="video_understanding")
    except (OSError, RunError) as error: raise ReasoningError(f"could not write understanding: {output}") from error
    return understanding
