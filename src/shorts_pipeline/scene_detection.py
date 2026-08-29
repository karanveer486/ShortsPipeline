"""PySceneDetect-backed scene timeline stage."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Iterable, Protocol

from .domain import ArtifactRef, Scene, TimeRange
from .runs import RunContext, RunError, load_run, local_source_path, update_run_artifact
from .timeline_config import SceneDetectionConfig, scene_detection_config
from .transcription import seconds_to_milliseconds


class SceneDetectionError(RuntimeError):
    pass


class SceneDetectionDependencyError(SceneDetectionError):
    pass


class SceneDetector(Protocol):
    def detect(self, source_path: Path, config: SceneDetectionConfig) -> Iterable[tuple[float, float]]: ...


def scenes_from_ranges(run: RunContext, ranges: Iterable[tuple[float, float]]) -> tuple[Scene, ...]:
    scenes: list[Scene] = []
    for index, (start_seconds, end_seconds) in enumerate(ranges):
        try:
            scenes.append(Scene(
                scene_id=f"scene-{run.run.run_id}-{index:04d}",
                source_id=run.source.source_id,
                index=index,
                time_range=TimeRange(seconds_to_milliseconds(start_seconds), seconds_to_milliseconds(end_seconds)),
            ))
        except (TypeError, ValueError) as error:
            raise SceneDetectionError(f"invalid scene range at index {index}") from error
    return tuple(scenes)


class PySceneDetector:
    def detect(self, source_path: Path, config: SceneDetectionConfig) -> Iterable[tuple[float, float]]:
        try:
            from scenedetect import ContentDetector, detect
        except ImportError as error:
            raise SceneDetectionDependencyError("scenedetect is not installed") from error
        try:
            found = detect(str(source_path), ContentDetector(threshold=config.threshold, min_scene_len=config.min_scene_len))
            return [(start.get_seconds(), end.get_seconds()) for start, end in found]
        except Exception as error:
            raise SceneDetectionError(f"scene detection failed: {error}") from error


def _scenes_path(context: RunContext) -> Path:
    return context.run_directory / "scenes.json"


def _load_existing(path: Path, context: RunContext) -> tuple[Scene, ...]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        scenes = tuple(Scene.from_dict(item) for item in payload["scenes"])
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise SceneDetectionError(f"existing scenes output is malformed: {path}") from error
    if payload.get("source_id") != context.source.source_id or any(scene.source_id != context.source.source_id for scene in scenes):
        raise SceneDetectionError(f"existing scenes belong to another source: {path}")
    return scenes


def detect_scenes(run_id: str, *, workspace_root: str | Path = "workspace", config_path: str | Path | None = "config/pipeline.toml", force: bool = False, detector: SceneDetector | None = None) -> tuple[Scene, ...]:
    try:
        context = load_run(run_id, workspace_root=workspace_root)
        source_path = local_source_path(context.source)
        config = scene_detection_config(config_path)
    except (RunError, ValueError) as error:
        raise SceneDetectionError(str(error)) from error
    output_path = _scenes_path(context)
    if output_path.is_file() and not force:
        return _load_existing(output_path, context)
    scenes = scenes_from_ranges(context, (detector or PySceneDetector()).detect(source_path, config))
    payload = {"run_id": run_id, "source_id": context.source.source_id, "scenes": [scene.to_dict() for scene in scenes]}
    temporary_path = output_path.with_suffix(".json.tmp")
    try:
        temporary_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary_path.replace(output_path)
        update_run_artifact(context, ArtifactRef(f"artifact-{run_id}-scenes", "scenes", output_path.as_posix(), "application/json"), stage="scene_detection")
    except (OSError, RunError) as error:
        raise SceneDetectionError(f"could not write scenes output: {output_path}") from error
    return scenes
