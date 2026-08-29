"""Frame-level JSON contracts used between extraction and visual analysis."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .models import ArtifactRef, JsonValue


def _metadata(value: Mapping[str, Any]) -> dict[str, JsonValue]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise ValueError("frame metadata must be a string-keyed mapping")
    return dict(value)


@dataclass(frozen=True)
class ExtractedFrame:
    """One extracted image and its source timeline evidence."""

    frame_id: str
    source_id: str
    timestamp_ms: int
    artifact: ArtifactRef
    scene_id: str | None = None
    image_format: str = "jpg"
    metadata: Mapping[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.frame_id, str) or not self.frame_id.strip():
            raise ValueError("frame_id must be a non-empty string")
        if not isinstance(self.source_id, str) or not self.source_id.strip():
            raise ValueError("source_id must be a non-empty string")
        if isinstance(self.timestamp_ms, bool) or not isinstance(self.timestamp_ms, int) or self.timestamp_ms < 0:
            raise ValueError("timestamp_ms must be a non-negative integer")
        if not isinstance(self.artifact, ArtifactRef):
            raise ValueError("artifact must be ArtifactRef")
        if self.scene_id is not None and (not isinstance(self.scene_id, str) or not self.scene_id.strip()):
            raise ValueError("scene_id must be a non-empty string when provided")
        if self.image_format not in {"jpg", "png", "webp"}:
            raise ValueError("image_format must be jpg, png, or webp")
        object.__setattr__(self, "metadata", _metadata(self.metadata))

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "frame_id": self.frame_id,
            "source_id": self.source_id,
            "timestamp_ms": self.timestamp_ms,
            "artifact": self.artifact.to_dict(),
            "scene_id": self.scene_id,
            "image_format": self.image_format,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ExtractedFrame":
        return cls(
            frame_id=data["frame_id"], source_id=data["source_id"], timestamp_ms=data["timestamp_ms"],
            artifact=ArtifactRef.from_dict(data["artifact"]), scene_id=data.get("scene_id"),
            image_format=data.get("image_format", "jpg"), metadata=data.get("metadata", {}),
        )
