"""Provider-neutral interface for structured video reasoning."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol
from ...domain import Scene, TranscriptSegment, UnderstandingItem, VisualObservation

@dataclass(frozen=True)
class ReasoningChunk:
    chunk_id: str
    source_id: str
    scenes: tuple[Scene, ...]
    transcript_segments: tuple[TranscriptSegment, ...]
    observations: tuple[VisualObservation, ...]
    def __post_init__(self) -> None:
        if not self.chunk_id or not self.source_id or not self.scenes: raise ValueError("reasoning chunks need an ID, source ID, and scenes")
        if any(item.source_id != self.source_id for item in self.scenes + self.observations): raise ValueError("chunk evidence must belong to its source")

class VideoReasoner(Protocol):
    def reason_chunk(self, chunk: ReasoningChunk) -> tuple[UnderstandingItem, ...]: ...
    def merge(self, source_id: str, chunks: tuple[tuple[UnderstandingItem, ...], ...]) -> tuple[UnderstandingItem, ...]: ...
