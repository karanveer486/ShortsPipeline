"""Provider-neutral data contracts for future ShortsPipeline stages.

All media positions and durations use integer milliseconds.  IDs are supplied by
the caller so that storage and orchestration can choose stable ID strategies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import json
from typing import Any, Mapping, TypeVar


JsonValue = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
T = TypeVar("T", bound="JsonModel")


def _require_id(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


def _require_non_negative_int(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")


def _require_probability(value: float | None, field_name: str) -> None:
    if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1):
        raise ValueError(f"{field_name} must be between 0 and 1 when provided")


def _json_value(value: Any) -> JsonValue:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise ValueError("metadata keys must be strings")
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    raise ValueError("metadata must contain JSON-compatible values")


def _metadata(value: Mapping[str, Any]) -> dict[str, JsonValue]:
    if not isinstance(value, Mapping):
        raise ValueError("metadata must be a mapping")
    return {key: _json_value(item) for key, item in value.items()}


def _utc_datetime(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{field_name} must be a timezone-aware datetime")
    return value.astimezone(timezone.utc)


def _datetime_from_json(value: str, field_name: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be an ISO-8601 string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return _utc_datetime(parsed, field_name)


class JsonModel:
    """Small protocol shared by JSON interchange contract models."""

    def to_dict(self) -> dict[str, JsonValue]:
        raise NotImplementedError

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))


class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class CandidateStatus(str, Enum):
    PROPOSED = "proposed"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    ARCHIVED = "archived"


class RenderStatus(str, Enum):
    PLANNED = "planned"
    QUEUED = "queued"
    RENDERING = "rendering"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ReviewDecision(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CHANGES_REQUESTED = "changes_requested"


@dataclass(frozen=True)
class TimeRange(JsonModel):
    """An inclusive-start, exclusive-end interval measured in milliseconds."""

    start_ms: int
    end_ms: int

    def __post_init__(self) -> None:
        _require_non_negative_int(self.start_ms, "start_ms")
        _require_non_negative_int(self.end_ms, "end_ms")
        if self.end_ms <= self.start_ms:
            raise ValueError("end_ms must be greater than start_ms")

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms

    def to_dict(self) -> dict[str, JsonValue]:
        return {"start_ms": self.start_ms, "end_ms": self.end_ms}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TimeRange":
        return cls(start_ms=data["start_ms"], end_ms=data["end_ms"])


@dataclass(frozen=True)
class MediaMetadata(JsonModel):
    duration_ms: int
    width: int
    height: int
    frame_rate: float
    container: str | None = None
    video_codec: str | None = None
    audio_codec: str | None = None
    metadata: Mapping[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_non_negative_int(self.duration_ms, "duration_ms")
        if self.duration_ms == 0:
            raise ValueError("duration_ms must be greater than zero")
        for name, value in (("width", self.width), ("height", self.height)):
            _require_non_negative_int(value, name)
            if value == 0:
                raise ValueError(f"{name} must be greater than zero")
        if isinstance(self.frame_rate, bool) or not isinstance(self.frame_rate, (int, float)) or self.frame_rate <= 0:
            raise ValueError("frame_rate must be greater than zero")
        object.__setattr__(self, "metadata", _metadata(self.metadata))

    def to_dict(self) -> dict[str, JsonValue]:
        return {"duration_ms": self.duration_ms, "width": self.width, "height": self.height,
                "frame_rate": self.frame_rate, "container": self.container,
                "video_codec": self.video_codec, "audio_codec": self.audio_codec,
                "metadata": dict(self.metadata)}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "MediaMetadata":
        return cls(duration_ms=data["duration_ms"], width=data["width"], height=data["height"],
                   frame_rate=data["frame_rate"], container=data.get("container"),
                   video_codec=data.get("video_codec"), audio_codec=data.get("audio_codec"),
                   metadata=data.get("metadata", {}))


@dataclass(frozen=True)
class SourceVideo(JsonModel):
    source_id: str
    reference: str
    media: MediaMetadata
    metadata: Mapping[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_id(self.source_id, "source_id")
        _require_id(self.reference, "reference")
        if not isinstance(self.media, MediaMetadata):
            raise ValueError("media must be MediaMetadata")
        object.__setattr__(self, "metadata", _metadata(self.metadata))

    def to_dict(self) -> dict[str, JsonValue]:
        return {"source_id": self.source_id, "reference": self.reference,
                "media": self.media.to_dict(), "metadata": dict(self.metadata)}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SourceVideo":
        return cls(source_id=data["source_id"], reference=data["reference"],
                   media=MediaMetadata.from_dict(data["media"]), metadata=data.get("metadata", {}))


@dataclass(frozen=True)
class ArtifactRef(JsonModel):
    artifact_id: str
    kind: str
    uri: str
    media_type: str | None = None
    metadata: Mapping[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name, value in (("artifact_id", self.artifact_id), ("kind", self.kind), ("uri", self.uri)):
            _require_id(value, name)
        object.__setattr__(self, "metadata", _metadata(self.metadata))

    def to_dict(self) -> dict[str, JsonValue]:
        return {"artifact_id": self.artifact_id, "kind": self.kind, "uri": self.uri,
                "media_type": self.media_type, "metadata": dict(self.metadata)}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ArtifactRef":
        return cls(artifact_id=data["artifact_id"], kind=data["kind"], uri=data["uri"],
                   media_type=data.get("media_type"), metadata=data.get("metadata", {}))


@dataclass(frozen=True)
class PipelineRun(JsonModel):
    run_id: str
    source_id: str
    created_at: datetime
    contract_version: str
    status: RunStatus = RunStatus.PENDING
    artifacts: tuple[ArtifactRef, ...] = ()
    metadata: Mapping[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name, value in (("run_id", self.run_id), ("source_id", self.source_id), ("contract_version", self.contract_version)):
            _require_id(value, name)
        object.__setattr__(self, "created_at", _utc_datetime(self.created_at, "created_at"))
        if not isinstance(self.status, RunStatus):
            raise ValueError("status must be RunStatus")
        if not all(isinstance(item, ArtifactRef) for item in self.artifacts):
            raise ValueError("artifacts must contain ArtifactRef values")
        object.__setattr__(self, "metadata", _metadata(self.metadata))

    def to_dict(self) -> dict[str, JsonValue]:
        return {"run_id": self.run_id, "source_id": self.source_id,
                "created_at": self.created_at.isoformat().replace("+00:00", "Z"),
                "contract_version": self.contract_version, "status": self.status.value,
                "artifacts": [item.to_dict() for item in self.artifacts], "metadata": dict(self.metadata)}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "PipelineRun":
        return cls(run_id=data["run_id"], source_id=data["source_id"],
                   created_at=_datetime_from_json(data["created_at"], "created_at"),
                   contract_version=data["contract_version"], status=RunStatus(data.get("status", "pending")),
                   artifacts=tuple(ArtifactRef.from_dict(item) for item in data.get("artifacts", [])),
                   metadata=data.get("metadata", {}))


@dataclass(frozen=True)
class TranscriptSegment(JsonModel):
    segment_id: str
    time_range: TimeRange
    text: str
    confidence: float | None = None
    metadata: Mapping[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_id(self.segment_id, "segment_id")
        if not isinstance(self.time_range, TimeRange) or not isinstance(self.text, str) or not self.text.strip():
            raise ValueError("segment requires a TimeRange and non-empty text")
        _require_probability(self.confidence, "confidence")
        object.__setattr__(self, "metadata", _metadata(self.metadata))

    def to_dict(self) -> dict[str, JsonValue]:
        return {"segment_id": self.segment_id, "time_range": self.time_range.to_dict(), "text": self.text,
                "confidence": self.confidence, "metadata": dict(self.metadata)}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TranscriptSegment":
        return cls(segment_id=data["segment_id"], time_range=TimeRange.from_dict(data["time_range"]),
                   text=data["text"], confidence=data.get("confidence"), metadata=data.get("metadata", {}))


@dataclass(frozen=True)
class Transcript(JsonModel):
    transcript_id: str
    source_id: str
    segments: tuple[TranscriptSegment, ...]
    language: str | None = None
    metadata: Mapping[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_id(self.transcript_id, "transcript_id")
        _require_id(self.source_id, "source_id")
        if not all(isinstance(segment, TranscriptSegment) for segment in self.segments):
            raise ValueError("segments must contain TranscriptSegment values")
        object.__setattr__(self, "metadata", _metadata(self.metadata))

    def to_dict(self) -> dict[str, JsonValue]:
        return {"transcript_id": self.transcript_id, "source_id": self.source_id,
                "segments": [segment.to_dict() for segment in self.segments], "language": self.language,
                "metadata": dict(self.metadata)}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Transcript":
        return cls(transcript_id=data["transcript_id"], source_id=data["source_id"],
                   segments=tuple(TranscriptSegment.from_dict(item) for item in data["segments"]),
                   language=data.get("language"), metadata=data.get("metadata", {}))


@dataclass(frozen=True)
class Scene(JsonModel):
    scene_id: str
    source_id: str
    index: int
    time_range: TimeRange
    metadata: Mapping[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_id(self.scene_id, "scene_id")
        _require_id(self.source_id, "source_id")
        _require_non_negative_int(self.index, "index")
        if not isinstance(self.time_range, TimeRange):
            raise ValueError("time_range must be TimeRange")
        object.__setattr__(self, "metadata", _metadata(self.metadata))

    def to_dict(self) -> dict[str, JsonValue]:
        return {"scene_id": self.scene_id, "source_id": self.source_id, "index": self.index,
                "time_range": self.time_range.to_dict(), "metadata": dict(self.metadata)}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Scene":
        return cls(scene_id=data["scene_id"], source_id=data["source_id"], index=data["index"],
                   time_range=TimeRange.from_dict(data["time_range"]), metadata=data.get("metadata", {}))


@dataclass(frozen=True)
class VisualObservation(JsonModel):
    observation_id: str
    source_id: str
    time_range: TimeRange
    observations: Mapping[str, JsonValue]
    scene_id: str | None = None
    confidence: float | None = None
    uncertainty: float | None = None
    metadata: Mapping[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_id(self.observation_id, "observation_id")
        _require_id(self.source_id, "source_id")
        if self.scene_id is not None:
            _require_id(self.scene_id, "scene_id")
        if not isinstance(self.time_range, TimeRange):
            raise ValueError("time_range must be TimeRange")
        if not self.observations:
            raise ValueError("observations must not be empty")
        object.__setattr__(self, "observations", _metadata(self.observations))
        _require_probability(self.confidence, "confidence")
        _require_probability(self.uncertainty, "uncertainty")
        object.__setattr__(self, "metadata", _metadata(self.metadata))

    def to_dict(self) -> dict[str, JsonValue]:
        return {"observation_id": self.observation_id, "source_id": self.source_id,
                "time_range": self.time_range.to_dict(), "scene_id": self.scene_id,
                "observations": dict(self.observations), "confidence": self.confidence,
                "uncertainty": self.uncertainty, "metadata": dict(self.metadata)}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "VisualObservation":
        return cls(observation_id=data["observation_id"], source_id=data["source_id"],
                   time_range=TimeRange.from_dict(data["time_range"]), observations=data["observations"],
                   scene_id=data.get("scene_id"), confidence=data.get("confidence"),
                   uncertainty=data.get("uncertainty"), metadata=data.get("metadata", {}))


@dataclass(frozen=True)
class EvidenceRef(JsonModel):
    scene_ids: tuple[str, ...] = ()
    time_ranges: tuple[TimeRange, ...] = ()

    def __post_init__(self) -> None:
        for scene_id in self.scene_ids:
            _require_id(scene_id, "scene_id")
        if not all(isinstance(item, TimeRange) for item in self.time_ranges):
            raise ValueError("time_ranges must contain TimeRange values")
        if not self.scene_ids and not self.time_ranges:
            raise ValueError("evidence requires at least one scene or time range")

    def to_dict(self) -> dict[str, JsonValue]:
        return {"scene_ids": list(self.scene_ids), "time_ranges": [item.to_dict() for item in self.time_ranges]}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "EvidenceRef":
        return cls(scene_ids=tuple(data.get("scene_ids", [])),
                   time_ranges=tuple(TimeRange.from_dict(item) for item in data.get("time_ranges", [])))


@dataclass(frozen=True)
class UnderstandingItem(JsonModel):
    item_id: str
    kind: str
    statement: str
    evidence: EvidenceRef
    confidence: float | None = None
    attributes: Mapping[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name, value in (("item_id", self.item_id), ("kind", self.kind), ("statement", self.statement)):
            _require_id(value, name)
        if not isinstance(self.evidence, EvidenceRef):
            raise ValueError("evidence must be EvidenceRef")
        _require_probability(self.confidence, "confidence")
        object.__setattr__(self, "attributes", _metadata(self.attributes))

    def to_dict(self) -> dict[str, JsonValue]:
        return {"item_id": self.item_id, "kind": self.kind, "statement": self.statement,
                "evidence": self.evidence.to_dict(), "confidence": self.confidence,
                "attributes": dict(self.attributes)}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "UnderstandingItem":
        return cls(item_id=data["item_id"], kind=data["kind"], statement=data["statement"],
                   evidence=EvidenceRef.from_dict(data["evidence"]), confidence=data.get("confidence"),
                   attributes=data.get("attributes", {}))


@dataclass(frozen=True)
class VideoUnderstanding(JsonModel):
    understanding_id: str
    source_id: str
    items: tuple[UnderstandingItem, ...]
    metadata: Mapping[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_id(self.understanding_id, "understanding_id")
        _require_id(self.source_id, "source_id")
        if not all(isinstance(item, UnderstandingItem) for item in self.items):
            raise ValueError("items must contain UnderstandingItem values")
        object.__setattr__(self, "metadata", _metadata(self.metadata))

    def to_dict(self) -> dict[str, JsonValue]:
        return {"understanding_id": self.understanding_id, "source_id": self.source_id,
                "items": [item.to_dict() for item in self.items], "metadata": dict(self.metadata)}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "VideoUnderstanding":
        return cls(understanding_id=data["understanding_id"], source_id=data["source_id"],
                   items=tuple(UnderstandingItem.from_dict(item) for item in data["items"]),
                   metadata=data.get("metadata", {}))


@dataclass(frozen=True)
class ShortCandidate(JsonModel):
    candidate_id: str
    source_id: str
    time_range: TimeRange
    scene_ids: tuple[str, ...]
    reason: str
    hook: str | None = None
    payoff: str | None = None
    score: float | None = None
    status: CandidateStatus = CandidateStatus.PROPOSED
    metadata: Mapping[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name, value in (("candidate_id", self.candidate_id), ("source_id", self.source_id), ("reason", self.reason)):
            _require_id(value, name)
        if not isinstance(self.time_range, TimeRange):
            raise ValueError("time_range must be TimeRange")
        if not self.scene_ids:
            raise ValueError("scene_ids must not be empty")
        for scene_id in self.scene_ids:
            _require_id(scene_id, "scene_id")
        _require_probability(self.score, "score")
        if not isinstance(self.status, CandidateStatus):
            raise ValueError("status must be CandidateStatus")
        object.__setattr__(self, "metadata", _metadata(self.metadata))

    def to_dict(self) -> dict[str, JsonValue]:
        return {"candidate_id": self.candidate_id, "source_id": self.source_id,
                "time_range": self.time_range.to_dict(), "scene_ids": list(self.scene_ids),
                "reason": self.reason, "hook": self.hook, "payoff": self.payoff, "score": self.score,
                "status": self.status.value, "metadata": dict(self.metadata)}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ShortCandidate":
        return cls(candidate_id=data["candidate_id"], source_id=data["source_id"],
                   time_range=TimeRange.from_dict(data["time_range"]), scene_ids=tuple(data["scene_ids"]),
                   reason=data["reason"], hook=data.get("hook"), payoff=data.get("payoff"),
                   score=data.get("score"), status=CandidateStatus(data.get("status", "proposed")),
                   metadata=data.get("metadata", {}))


@dataclass(frozen=True)
class TargetFormat(JsonModel):
    width: int
    height: int
    frame_rate: float
    container: str = "mp4"

    def __post_init__(self) -> None:
        for name, value in (("width", self.width), ("height", self.height)):
            _require_non_negative_int(value, name)
            if value == 0:
                raise ValueError(f"{name} must be greater than zero")
        if isinstance(self.frame_rate, bool) or not isinstance(self.frame_rate, (int, float)) or self.frame_rate <= 0:
            raise ValueError("frame_rate must be greater than zero")
        _require_id(self.container, "container")

    def to_dict(self) -> dict[str, JsonValue]:
        return {"width": self.width, "height": self.height, "frame_rate": self.frame_rate, "container": self.container}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TargetFormat":
        return cls(width=data["width"], height=data["height"], frame_rate=data["frame_rate"],
                   container=data.get("container", "mp4"))


@dataclass(frozen=True)
class RenderSourceSegment(JsonModel):
    """One ordered, unmodified source interval used by a render plan."""

    scene_id: str
    time_range: TimeRange
    index: int

    def __post_init__(self) -> None:
        _require_id(self.scene_id, "scene_id")
        if not isinstance(self.time_range, TimeRange):
            raise ValueError("time_range must be TimeRange")
        _require_non_negative_int(self.index, "index")

    def to_dict(self) -> dict[str, JsonValue]:
        return {"scene_id": self.scene_id, "time_range": self.time_range.to_dict(), "index": self.index}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RenderSourceSegment":
        return cls(data["scene_id"], TimeRange.from_dict(data["time_range"]), data["index"])


@dataclass(frozen=True)
class RenderPlan(JsonModel):
    plan_id: str
    candidate_id: str
    target: TargetFormat
    framing: Mapping[str, JsonValue]
    captions: Mapping[str, JsonValue] | None = None
    metadata: Mapping[str, JsonValue] = field(default_factory=dict)
    source_id: str | None = None
    source_time_range: TimeRange | None = None
    source_segments: tuple[RenderSourceSegment, ...] = ()
    output_duration_ms: int | None = None
    audio: Mapping[str, JsonValue] = field(default_factory=dict)
    transition: Mapping[str, JsonValue] = field(default_factory=dict)
    output: Mapping[str, JsonValue] = field(default_factory=dict)
    plan_version: str = "1"

    def __post_init__(self) -> None:
        _require_id(self.plan_id, "plan_id")
        _require_id(self.candidate_id, "candidate_id")
        if not isinstance(self.target, TargetFormat):
            raise ValueError("target must be TargetFormat")
        if not self.framing:
            raise ValueError("framing must not be empty")
        object.__setattr__(self, "framing", _metadata(self.framing))
        if self.captions is not None:
            object.__setattr__(self, "captions", _metadata(self.captions))
        object.__setattr__(self, "metadata", _metadata(self.metadata))
        if self.source_id is not None:
            _require_id(self.source_id, "source_id")
        if self.source_time_range is not None and not isinstance(self.source_time_range, TimeRange):
            raise ValueError("source_time_range must be TimeRange")
        if any(not isinstance(segment, RenderSourceSegment) for segment in self.source_segments):
            raise ValueError("source_segments must contain RenderSourceSegment values")
        if self.source_segments:
            ordered = tuple(sorted(self.source_segments, key=lambda segment: segment.index))
            if ordered != self.source_segments:
                raise ValueError("source_segments must be ordered by index")
            if any(right.time_range.start_ms < left.time_range.end_ms for left, right in zip(ordered, ordered[1:])):
                raise ValueError("source_segments must not overlap")
        if self.output_duration_ms is not None:
            _require_non_negative_int(self.output_duration_ms, "output_duration_ms")
            if self.output_duration_ms == 0:
                raise ValueError("output_duration_ms must be greater than zero")
        for name in ("audio", "transition", "output"):
            object.__setattr__(self, name, _metadata(getattr(self, name)))
        _require_id(self.plan_version, "plan_version")

    def to_dict(self) -> dict[str, JsonValue]:
        return {"plan_id": self.plan_id, "candidate_id": self.candidate_id, "target": self.target.to_dict(),
                "framing": dict(self.framing), "captions": dict(self.captions) if self.captions else None,
                "metadata": dict(self.metadata), "source_id": self.source_id,
                "source_time_range": self.source_time_range.to_dict() if self.source_time_range else None,
                "source_segments": [segment.to_dict() for segment in self.source_segments],
                "output_duration_ms": self.output_duration_ms, "audio": dict(self.audio),
                "transition": dict(self.transition), "output": dict(self.output),
                "plan_version": self.plan_version}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RenderPlan":
        return cls(plan_id=data["plan_id"], candidate_id=data["candidate_id"],
                   target=TargetFormat.from_dict(data["target"]), framing=data["framing"],
                   captions=data.get("captions"), metadata=data.get("metadata", {}),
                   source_id=data.get("source_id"),
                   source_time_range=TimeRange.from_dict(data["source_time_range"]) if data.get("source_time_range") else None,
                   source_segments=tuple(RenderSourceSegment.from_dict(item) for item in data.get("source_segments", ())),
                   output_duration_ms=data.get("output_duration_ms"), audio=data.get("audio", {}),
                   transition=data.get("transition", {}), output=data.get("output", {}),
                   plan_version=data.get("plan_version", "1"))

@dataclass(frozen=True)
class RenderOutput(JsonModel):
    render_id: str
    plan_id: str
    candidate_id: str
    status: RenderStatus
    output: ArtifactRef | None = None
    error: str | None = None
    metadata: Mapping[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name, value in (("render_id", self.render_id), ("plan_id", self.plan_id), ("candidate_id", self.candidate_id)):
            _require_id(value, name)
        if not isinstance(self.status, RenderStatus):
            raise ValueError("status must be RenderStatus")
        if self.output is not None and not isinstance(self.output, ArtifactRef):
            raise ValueError("output must be ArtifactRef when provided")
        if self.status is RenderStatus.SUCCEEDED and self.output is None:
            raise ValueError("a successful render requires an output artifact")
        object.__setattr__(self, "metadata", _metadata(self.metadata))

    def to_dict(self) -> dict[str, JsonValue]:
        return {"render_id": self.render_id, "plan_id": self.plan_id, "candidate_id": self.candidate_id,
                "status": self.status.value, "output": self.output.to_dict() if self.output else None,
                "error": self.error, "metadata": dict(self.metadata)}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RenderOutput":
        output = data.get("output")
        return cls(render_id=data["render_id"], plan_id=data["plan_id"], candidate_id=data["candidate_id"],
                   status=RenderStatus(data["status"]), output=ArtifactRef.from_dict(output) if output else None,
                   error=data.get("error"), metadata=data.get("metadata", {}))


@dataclass(frozen=True)
class Review(JsonModel):
    review_id: str
    candidate_id: str
    decision: ReviewDecision
    reviewed_at: datetime
    render_id: str | None = None
    reviewer_id: str | None = None
    notes: str | None = None
    metadata: Mapping[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name, value in (("review_id", self.review_id), ("candidate_id", self.candidate_id)):
            _require_id(value, name)
        if self.render_id is not None:
            _require_id(self.render_id, "render_id")
        if self.reviewer_id is not None:
            _require_id(self.reviewer_id, "reviewer_id")
        if not isinstance(self.decision, ReviewDecision):
            raise ValueError("decision must be ReviewDecision")
        object.__setattr__(self, "reviewed_at", _utc_datetime(self.reviewed_at, "reviewed_at"))
        object.__setattr__(self, "metadata", _metadata(self.metadata))

    def to_dict(self) -> dict[str, JsonValue]:
        return {"review_id": self.review_id, "candidate_id": self.candidate_id,
                "decision": self.decision.value, "reviewed_at": self.reviewed_at.isoformat().replace("+00:00", "Z"),
                "render_id": self.render_id, "reviewer_id": self.reviewer_id, "notes": self.notes,
                "metadata": dict(self.metadata)}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Review":
        return cls(review_id=data["review_id"], candidate_id=data["candidate_id"],
                   decision=ReviewDecision(data["decision"]),
                   reviewed_at=_datetime_from_json(data["reviewed_at"], "reviewed_at"),
                   render_id=data.get("render_id"), reviewer_id=data.get("reviewer_id"),
                   notes=data.get("notes"), metadata=data.get("metadata", {}))
