"""Run-level orchestration for provider-neutral visual analysis."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import tomllib
from typing import Any, Mapping

from .adapters.vlm.contracts import VisualAnalysisRequest, VisualAnalyzer, validate_visual_observations
from .adapters.vlm.ollama import OllamaVisualAnalyzer
from .domain import ArtifactRef, Scene, TranscriptSegment, VisualObservation
from .domain.frames import ExtractedFrame
from .runs import RunContext, RunError, load_run, local_source_path, update_run_artifact


class VisualAnalysisError(RuntimeError):
    pass


@dataclass(frozen=True)
class VisualAnalysisConfig:
    backend: str = "ollama"
    model: str = "qwen2.5vl:7b"
    endpoint: str = "http://127.0.0.1:11434/api/chat"
    timeout_seconds: float = 90.0
    max_frames_per_request: int = 4


def visual_analysis_config(path: str | Path | None = "config/pipeline.toml", *, model: str | None = None) -> VisualAnalysisConfig:
    values: Mapping[str, Any] = {}
    if path is not None and Path(path).is_file():
        try:
            parsed = tomllib.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError) as error:
            raise VisualAnalysisError(f"invalid visual-analysis configuration: {path}") from error
        candidate = parsed.get("visual_analysis", {})
        if not isinstance(candidate, Mapping):
            raise VisualAnalysisError("[visual_analysis] must be a TOML table")
        values = candidate
    config = VisualAnalysisConfig(
        backend=values.get("backend", "ollama"), model=model or values.get("model", "qwen2.5vl:7b"),
        endpoint=values.get("endpoint", "http://127.0.0.1:11434/api/chat"),
        timeout_seconds=values.get("timeout_seconds", 90.0), max_frames_per_request=values.get("max_frames_per_request", 4),
    )
    if config.backend != "ollama" or not isinstance(config.model, str) or not config.model.strip():
        raise VisualAnalysisError("only the ollama backend with a model name is currently supported")
    if not isinstance(config.timeout_seconds, (int, float)) or config.timeout_seconds <= 0:
        raise VisualAnalysisError("timeout_seconds must be positive")
    if not isinstance(config.max_frames_per_request, int) or config.max_frames_per_request <= 0:
        raise VisualAnalysisError("max_frames_per_request must be positive")
    return config


def _load_frames(context: RunContext) -> tuple[ExtractedFrame, ...]:
    path = context.run_directory / "frames.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        frames = tuple(ExtractedFrame.from_dict(item) for item in payload["frames"])
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise VisualAnalysisError(f"frames output is missing or malformed: {path}") from error
    if not frames or any(frame.source_id != context.source.source_id for frame in frames):
        raise VisualAnalysisError(f"frames output belongs to another source or is empty: {path}")
    return frames


def _load_optional_scenes(context: RunContext) -> tuple[Scene, ...]:
    path = context.run_directory / "scenes.json"
    if not path.is_file(): return ()
    try:
        return tuple(Scene.from_dict(item) for item in json.loads(path.read_text(encoding="utf-8"))["scenes"])
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise VisualAnalysisError(f"scenes output is malformed: {path}") from error


def _load_optional_transcript(context: RunContext) -> tuple[TranscriptSegment, ...]:
    path = context.run_directory / "transcript.json"
    if not path.is_file(): return ()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return tuple(TranscriptSegment.from_dict(item) for item in data["segments"])
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise VisualAnalysisError(f"transcript output is malformed: {path}") from error


def build_analysis_requests(context: RunContext, frames: tuple[ExtractedFrame, ...], scenes: tuple[Scene, ...], transcript: tuple[TranscriptSegment, ...], config: VisualAnalysisConfig, instructions: str | None = None) -> tuple[VisualAnalysisRequest, ...]:
    groups: dict[str, list[ExtractedFrame]] = {}
    for frame in frames: groups.setdefault(frame.scene_id or "unscoped", []).append(frame)
    requests: list[VisualAnalysisRequest] = []
    for scene_key, group in groups.items():
        scene_context = tuple(scene for scene in scenes if scene.scene_id == scene_key)
        for offset in range(0, len(group), config.max_frames_per_request):
            batch = tuple(group[offset:offset + config.max_frames_per_request])
            start_ms, end_ms = batch[0].timestamp_ms, batch[-1].timestamp_ms + 1
            relevant_transcript = tuple(segment for segment in transcript if segment.time_range.start_ms < end_ms and segment.time_range.end_ms > start_ms)
            requests.append(VisualAnalysisRequest(f"{context.run.run_id}-{scene_key}-{offset // config.max_frames_per_request:03d}", context.source.source_id, batch, scene_context, relevant_transcript, instructions))
    return tuple(requests)


def analyze_run(run_id: str, *, workspace_root: str | Path = "workspace", config_path: str | Path | None = "config/pipeline.toml", model: str | None = None, force: bool = False, instructions: str | None = None, analyzer: VisualAnalyzer | None = None) -> tuple[VisualObservation, ...]:
    try:
        context = load_run(run_id, workspace_root=workspace_root)
        local_source_path(context.source)
        config = visual_analysis_config(config_path, model=model)
    except (RunError, VisualAnalysisError) as error:
        raise VisualAnalysisError(str(error)) from error
    output_path = context.run_directory / "visual_analysis.json"
    if output_path.is_file() and not force:
        try:
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            observations = tuple(VisualObservation.from_dict(item) for item in payload["observations"])
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise VisualAnalysisError(f"existing visual analysis is malformed: {output_path}") from error
        if payload.get("source_id") != context.source.source_id: raise VisualAnalysisError("existing visual analysis belongs to another source")
        return observations
    frames, scenes, transcript = _load_frames(context), _load_optional_scenes(context), _load_optional_transcript(context)
    selected_analyzer = analyzer or OllamaVisualAnalyzer(model=config.model, endpoint=config.endpoint, timeout_seconds=config.timeout_seconds)
    observations: list[VisualObservation] = []
    for request in build_analysis_requests(context, frames, scenes, transcript, config, instructions):
        try:
            observations.extend(validate_visual_observations(request, selected_analyzer.analyze(request)))
        except Exception as error:
            raise VisualAnalysisError(f"visual analysis failed for {request.request_id}: {error}") from error
    payload = {"run_id": run_id, "source_id": context.source.source_id, "backend": config.backend, "model": config.model,
        "analyzed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "observations": [item.to_dict() for item in observations]}
    temporary = output_path.with_suffix(".json.tmp")
    try:
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(output_path)
        update_run_artifact(context, ArtifactRef(f"artifact-{run_id}-visual-analysis", "visual_analysis", output_path.as_posix(), "application/json", {"backend": config.backend, "model": config.model}), stage="visual_analysis")
    except (OSError, RunError) as error:
        raise VisualAnalysisError(f"could not write visual analysis: {output_path}") from error
    return tuple(observations)
