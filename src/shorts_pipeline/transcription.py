"""Whisper-backed transcription stage, isolated behind a local adapter."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Protocol

from .domain import ArtifactRef, Transcript, TranscriptSegment
from .runs import RunContext, RunError, load_run, local_source_path, update_run_artifact
from .timeline_config import TranscriptionConfig, transcription_config


class TranscriptionError(RuntimeError):
    pass


class TranscriptionDependencyError(TranscriptionError):
    pass


@dataclass(frozen=True)
class RawTranscriptSegment:
    start_seconds: float
    end_seconds: float
    text: str
    confidence: float | None = None


class Transcriber(Protocol):
    def transcribe(self, source_path: Path, config: TranscriptionConfig) -> Iterable[RawTranscriptSegment]: ...


def seconds_to_milliseconds(value: float) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise TranscriptionError("transcript timestamp must be a non-negative number")
    return int(round(value * 1000))


def transcript_from_segments(run: RunContext, segments: Iterable[RawTranscriptSegment]) -> Transcript:
    converted: list[TranscriptSegment] = []
    for index, segment in enumerate(segments):
        start_ms = seconds_to_milliseconds(segment.start_seconds)
        end_ms = seconds_to_milliseconds(segment.end_seconds)
        try:
            converted.append(TranscriptSegment(
                segment_id=f"transcript-{run.run.run_id}-segment-{index:04d}",
                time_range=__import__("shorts_pipeline.domain", fromlist=["TimeRange"]).TimeRange(start_ms, end_ms),
                text=segment.text.strip(),
                confidence=segment.confidence,
            ))
        except (AttributeError, ValueError) as error:
            raise TranscriptionError(f"invalid transcript segment at index {index}") from error
    return Transcript(transcript_id=f"transcript-{run.run.run_id}", source_id=run.source.source_id, segments=tuple(converted))


class WhisperTranscriber:
    def transcribe(self, source_path: Path, config: TranscriptionConfig) -> Iterable[RawTranscriptSegment]:
        try:
            import whisper
        except ImportError as error:
            raise TranscriptionDependencyError("openai-whisper is not installed") from error
        try:
            kwargs: dict[str, Any] = {}
            if config.device:
                kwargs["device"] = config.device
            model = whisper.load_model(config.model, **kwargs)
            result = model.transcribe(str(source_path), language=config.language)
            raw_segments = result.get("segments") if isinstance(result, Mapping) else None
        except Exception as error:
            raise TranscriptionError(f"Whisper transcription failed: {error}") from error
        if not isinstance(raw_segments, list):
            raise TranscriptionError("Whisper returned malformed transcription output")
        converted: list[RawTranscriptSegment] = []
        for index, item in enumerate(raw_segments):
            if not isinstance(item, Mapping):
                raise TranscriptionError(f"Whisper segment {index} is malformed")
            try:
                converted.append(RawTranscriptSegment(float(item["start"]), float(item["end"]), str(item["text"])))
            except (KeyError, TypeError, ValueError) as error:
                raise TranscriptionError(f"Whisper segment {index} is malformed") from error
        return converted


def _transcript_path(context: RunContext) -> Path:
    return context.run_directory / "transcript.json"


def _load_existing(path: Path, context: RunContext) -> Transcript:
    try:
        transcript = Transcript.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise TranscriptionError(f"existing transcript is malformed: {path}") from error
    if transcript.source_id != context.source.source_id:
        raise TranscriptionError(f"existing transcript belongs to another source: {path}")
    return transcript


def transcribe_run(run_id: str, *, workspace_root: str | Path = "workspace", config_path: str | Path | None = "config/pipeline.toml", model: str | None = None, force: bool = False, transcriber: Transcriber | None = None) -> Transcript:
    try:
        context = load_run(run_id, workspace_root=workspace_root)
        source_path = local_source_path(context.source)
        config = transcription_config(config_path, model=model)
    except (RunError, ValueError) as error:
        raise TranscriptionError(str(error)) from error
    output_path = _transcript_path(context)
    if output_path.is_file() and not force:
        return _load_existing(output_path, context)
    transcript = transcript_from_segments(context, (transcriber or WhisperTranscriber()).transcribe(source_path, config))
    temporary_path = output_path.with_suffix(".json.tmp")
    try:
        temporary_path.write_text(json.dumps(transcript.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary_path.replace(output_path)
        update_run_artifact(context, ArtifactRef(f"artifact-{run_id}-transcript", "transcript", output_path.as_posix(), "application/json"), stage="transcription")
    except (OSError, RunError) as error:
        raise TranscriptionError(f"could not write transcript output: {output_path}") from error
    return transcript
