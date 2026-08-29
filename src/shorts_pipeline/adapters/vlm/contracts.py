"""Provider-neutral boundary for future visual-language-model adapters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ...domain import Scene, TranscriptSegment, VisualObservation
from ...domain.frames import ExtractedFrame


@dataclass(frozen=True)
class VisualAnalysisRequest:
    request_id: str
    source_id: str
    frames: tuple[ExtractedFrame, ...]
    scenes: tuple[Scene, ...] = ()
    transcript_segments: tuple[TranscriptSegment, ...] = ()
    instructions: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.request_id, str) or not self.request_id.strip():
            raise ValueError("request_id must be a non-empty string")
        if not isinstance(self.source_id, str) or not self.source_id.strip():
            raise ValueError("source_id must be a non-empty string")
        if not self.frames or any(frame.source_id != self.source_id for frame in self.frames):
            raise ValueError("frames must be non-empty and belong to source_id")
        if any(scene.source_id != self.source_id for scene in self.scenes):
            raise ValueError("scenes must belong to source_id")


class VisualAnalyzer(Protocol):
    """A future local or remote VLM backend implements this one method."""

    def analyze(self, request: VisualAnalysisRequest) -> tuple[VisualObservation, ...]: ...


def validate_visual_observations(request: VisualAnalysisRequest, observations: tuple[VisualObservation, ...]) -> tuple[VisualObservation, ...]:
    """Ensure adapter output stays within this request's source/timeline boundary."""
    for observation in observations:
        if observation.source_id != request.source_id:
            raise ValueError("visual observation belongs to a different source")
    return observations
