"""Deterministic, provider-neutral render-plan generation (no rendering)."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Mapping

from .domain import ArtifactRef, RenderPlan, RenderSourceSegment, Scene, ShortCandidate, TargetFormat, TimeRange, Transcript
from .runs import RunError, load_run, update_run_artifact


PLAN_VERSION = "render-plan-v1"


class RenderPlanningError(RuntimeError):
    """Raised when the inputs cannot safely describe a render plan."""


@dataclass(frozen=True)
class RenderPlanningConfig:
    width: int = 1080
    height: int = 1920
    frame_rate: float | None = None
    container: str = "mp4"
    video_codec: str = "h264"
    audio_codec: str = "aac"
    framing_strategy: str = "center_crop"
    caption_strategy: str = "transcript_based"
    audio_strategy: str = "preserve_source_audio"
    transition_strategy: str = "hard_cut"
    caption_style: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("target dimensions must be positive")
        if self.frame_rate is not None and (isinstance(self.frame_rate, bool) or self.frame_rate <= 0):
            raise ValueError("frame_rate must be positive when supplied")
        if self.framing_strategy not in {"center_crop", "fit_with_blur", "source_aspect"}:
            raise ValueError("unsupported framing strategy")
        if self.caption_strategy not in {"disabled", "transcript_based"}:
            raise ValueError("unsupported caption strategy")
        if self.audio_strategy != "preserve_source_audio":
            raise ValueError("unsupported audio strategy")
        if self.transition_strategy != "hard_cut":
            raise ValueError("unsupported transition strategy")
        if not all(isinstance(value, str) and value for value in (self.container, self.video_codec, self.audio_codec)):
            raise ValueError("output settings must be non-empty strings")


def render_planning_config(path: str | Path | None = None) -> RenderPlanningConfig:
    if path is None:
        return RenderPlanningConfig()
    try:
        import tomllib
        payload = tomllib.loads(Path(path).read_text(encoding="utf-8"))
        values = payload.get("render_planning", {})
    except (OSError, ValueError, ModuleNotFoundError) as error:
        raise RenderPlanningError(f"render-planning configuration is malformed: {path}") from error
    if not isinstance(values, Mapping):
        raise RenderPlanningError("[render_planning] must be a table")
    allowed = set(RenderPlanningConfig.__dataclass_fields__)
    unknown = set(values) - allowed
    if unknown:
        raise RenderPlanningError(f"unknown render-planning configuration: {', '.join(sorted(unknown))}")
    try:
        return RenderPlanningConfig(**dict(values))
    except (TypeError, ValueError) as error:
        raise RenderPlanningError("render-planning configuration is invalid") from error


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RenderPlanningError(f"missing or malformed artifact: {path}") from error


def _load_candidates(path: Path) -> tuple[ShortCandidate, ...]:
    try:
        payload = _read_json(path)
        return tuple(ShortCandidate.from_dict(value) for value in payload["candidates"])
    except (KeyError, TypeError, ValueError) as error:
        raise RenderPlanningError(f"candidates are malformed: {path}") from error


def _load_scenes(path: Path) -> tuple[Scene, ...]:
    try:
        payload = _read_json(path)
        return tuple(Scene.from_dict(value) for value in payload["scenes"])
    except (KeyError, TypeError, ValueError) as error:
        raise RenderPlanningError(f"scenes are malformed: {path}") from error


def _load_transcript(path: Path) -> Transcript:
    try:
        return Transcript.from_dict(_read_json(path))
    except (TypeError, ValueError) as error:
        raise RenderPlanningError(f"transcript is malformed: {path}") from error


def _crop_geometry(source_width: int, source_height: int, target: TargetFormat) -> dict[str, int]:
    if source_width <= 0 or source_height <= 0:
        raise RenderPlanningError("source dimensions must be positive")
    if source_width * target.height >= source_height * target.width:
        crop_height = source_height
        crop_width = source_height * target.width // target.height
        x, y = (source_width - crop_width) // 2, 0
    else:
        crop_width = source_width
        crop_height = source_width * target.height // target.width
        x, y = 0, (source_height - crop_height) // 2
    if crop_width <= 0 or crop_height <= 0 or x < 0 or y < 0 or x + crop_width > source_width or y + crop_height > source_height:
        raise RenderPlanningError("computed crop geometry is invalid")
    return {"x": x, "y": y, "width": crop_width, "height": crop_height}


def _source_segments(candidate: ShortCandidate, scenes: tuple[Scene, ...]) -> tuple[RenderSourceSegment, ...]:
    by_id = {scene.scene_id: scene for scene in scenes}
    if len(by_id) != len(scenes):
        raise RenderPlanningError("scene identifiers must be unique")
    result: list[RenderSourceSegment] = []
    for index, scene_id in enumerate(candidate.scene_ids):
        scene = by_id.get(scene_id)
        if scene is None:
            raise RenderPlanningError(f"candidate references missing scene: {scene_id}")
        if scene.source_id != candidate.source_id:
            raise RenderPlanningError(f"candidate scene belongs to another source: {scene_id}")
        if scene.time_range.start_ms < candidate.time_range.start_ms or scene.time_range.end_ms > candidate.time_range.end_ms:
            raise RenderPlanningError(f"scene lies outside candidate boundaries: {scene_id}")
        result.append(RenderSourceSegment(scene_id, scene.time_range, index))
    if not result:
        raise RenderPlanningError("candidate must reference at least one source segment")
    if any(right.time_range.start_ms < left.time_range.end_ms for left, right in zip(result, result[1:])):
        raise RenderPlanningError("candidate source scenes overlap")
    return tuple(result)


def _caption_plan(candidate: ShortCandidate, transcript: Transcript | None, config: RenderPlanningConfig) -> Mapping[str, Any]:
    if config.caption_strategy == "disabled":
        return {"strategy": "disabled", "segments": [], "style": dict(config.caption_style or {})}
    if transcript is None:
        raise RenderPlanningError("transcript_based captions require transcript.json")
    if transcript.source_id != candidate.source_id:
        raise RenderPlanningError("transcript belongs to another source")
    segments = []
    for segment in transcript.segments:
        start = max(segment.time_range.start_ms, candidate.time_range.start_ms)
        end = min(segment.time_range.end_ms, candidate.time_range.end_ms)
        if start >= end:
            continue
        segments.append({"transcript_segment_id": segment.segment_id, "source_time_range": {"start_ms": start, "end_ms": end}, "output_time_range": {"start_ms": start - candidate.time_range.start_ms, "end_ms": end - candidate.time_range.start_ms}, "text": segment.text})
    return {"strategy": "transcript_based", "segments": segments, "style": dict(config.caption_style or {})}


def _plan_id(run_id: str, candidate_id: str, config: RenderPlanningConfig) -> str:
    encoded = json.dumps({"run_id": run_id, "candidate_id": candidate_id, "config": config.__dict__}, sort_keys=True, default=dict).encode("utf-8")
    return f"render-plan-{sha256(encoded).hexdigest()[:16]}"


def create_render_plan(run_id: str, candidate_id: str, *, workspace_root: str | Path = "workspace", config: RenderPlanningConfig | None = None, force: bool = False) -> RenderPlan:
    """Create or reuse one JSON-only plan for an explicitly selected candidate."""
    try:
        context = load_run(run_id, workspace_root=workspace_root)
    except RunError as error:
        raise RenderPlanningError(str(error)) from error
    if not candidate_id or "/" in candidate_id or "\\" in candidate_id or ".." in candidate_id:
        raise RenderPlanningError("candidate_id is not safe for a plan filename")
    output_path = context.run_directory / f"render_plan_{candidate_id}.json"
    if output_path.is_file() and not force:
        try:
            plan = RenderPlan.from_dict(_read_json(output_path))
        except (TypeError, ValueError) as error:
            raise RenderPlanningError(f"existing render plan is malformed: {output_path}") from error
        if plan.candidate_id != candidate_id or plan.source_id != context.source.source_id:
            raise RenderPlanningError("existing render plan belongs to another candidate or source")
        return plan
    config = config or RenderPlanningConfig()
    candidates = _load_candidates(context.run_directory / "candidates.json")
    candidate = next((item for item in candidates if item.candidate_id == candidate_id), None)
    if candidate is None:
        raise RenderPlanningError(f"candidate does not exist: {candidate_id}")
    if candidate.source_id != context.source.source_id:
        raise RenderPlanningError("candidate belongs to another source")
    scenes = _load_scenes(context.run_directory / "scenes.json")
    source_segments = _source_segments(candidate, scenes)
    transcript = _load_transcript(context.run_directory / "transcript.json") if config.caption_strategy == "transcript_based" else None
    target = TargetFormat(config.width, config.height, config.frame_rate or context.source.media.frame_rate, config.container)
    framing: Mapping[str, Any] = {"strategy": config.framing_strategy, "subject_aware": False}
    if config.framing_strategy == "center_crop":
        framing = {**framing, "crop": _crop_geometry(context.source.media.width, context.source.media.height, target)}
    captions = _caption_plan(candidate, transcript, config)
    expected_uri = (context.run_directory / "renders" / f"{candidate_id}.{config.container}").as_posix()
    plan = RenderPlan(_plan_id(run_id, candidate_id, config), candidate_id, target, framing, captions,
                      {"configuration": config.__dict__}, context.source.source_id, candidate.time_range,
                      source_segments, candidate.time_range.duration_ms,
                      {"strategy": config.audio_strategy, "normalization": None, "ducking": None, "music": None},
                      {"strategy": config.transition_strategy},
                      {"expected_uri": expected_uri, "container": config.container, "video_codec": config.video_codec, "audio_codec": config.audio_codec, "expected_duration_ms": candidate.time_range.duration_ms}, PLAN_VERSION)
    try:
        output_path.write_text(json.dumps(plan.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        update_run_artifact(context, ArtifactRef(f"artifact-{run_id}-render-plan-{candidate_id}", f"render_plan:{candidate_id}", output_path.as_posix(), "application/json", {"plan_id": plan.plan_id}), stage="render_planning")
    except (OSError, RunError) as error:
        raise RenderPlanningError(f"could not write render plan: {output_path}") from error
    return plan
