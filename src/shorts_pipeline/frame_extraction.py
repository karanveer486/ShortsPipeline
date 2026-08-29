"""FFmpeg-backed extraction of deterministic image evidence for an existing run."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
from typing import Iterable, Mapping, Protocol

from .domain import ArtifactRef, Scene
from .domain.frames import ExtractedFrame
from .frame_config import FrameSamplingConfig, frame_sampling_config
from .runs import RunContext, RunError, load_run, local_source_path, update_run_artifact


class FrameExtractionError(RuntimeError):
    pass


class FFmpegUnavailableError(FrameExtractionError):
    pass


class FrameExtractor(Protocol):
    def extract(self, source_path: Path, timestamp_ms: int, output_path: Path, image_format: str) -> None: ...


class FFmpegFrameExtractor:
    def extract(self, source_path: Path, timestamp_ms: int, output_path: Path, image_format: str) -> None:
        command = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", f"{timestamp_ms / 1000:.3f}",
            "-i", str(source_path), "-frames:v", "1", "-y", str(output_path),
        ]
        try:
            completed = subprocess.run(command, capture_output=True, text=True, check=False, timeout=60)
        except FileNotFoundError as error:
            raise FFmpegUnavailableError("ffmpeg is not available on PATH") from error
        except (OSError, subprocess.TimeoutExpired) as error:
            raise FrameExtractionError(f"ffmpeg could not extract a frame: {error}") from error
        if completed.returncode != 0:
            raise FrameExtractionError(f"ffmpeg frame extraction failed: {completed.stderr.strip() or 'no diagnostic output'}")
        if not output_path.is_file() or output_path.stat().st_size == 0:
            raise FrameExtractionError(f"ffmpeg did not produce a frame: {output_path}")


def _load_scenes(context: RunContext) -> tuple[Scene, ...]:
    path = context.run_directory / "scenes.json"
    if not path.is_file():
        raise FrameExtractionError(f"scenes output does not exist: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        scenes = tuple(Scene.from_dict(item) for item in payload["scenes"])
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise FrameExtractionError(f"scenes output is malformed: {path}") from error
    if payload.get("source_id") != context.source.source_id or any(scene.source_id != context.source.source_id for scene in scenes):
        raise FrameExtractionError(f"scenes output belongs to another source: {path}")
    return scenes


def sample_timestamps(context: RunContext, scenes: tuple[Scene, ...], config: FrameSamplingConfig) -> tuple[tuple[int, str | None], ...]:
    if config.strategy == "interval":
        timestamps = range(0, context.source.media.duration_ms, config.interval_ms)
        result = []
        for timestamp_ms in timestamps:
            scene = next((item for item in scenes if item.time_range.start_ms <= timestamp_ms < item.time_range.end_ms), None)
            result.append((timestamp_ms, scene.scene_id if scene else None))
        return tuple(result)
    result = []
    for scene in scenes:
        for offset in config.scene_relative_offsets:
            timestamp_ms = scene.time_range.start_ms + int(round(scene.time_range.duration_ms * offset))
            timestamp_ms = min(timestamp_ms, scene.time_range.end_ms - 1)
            result.append((timestamp_ms, scene.scene_id))
    return tuple(result)


def _frame_id(run_id: str, timestamp_ms: int, scene_id: str | None) -> str:
    if scene_id is not None:
        return f"frame-{run_id}-{scene_id}-{timestamp_ms:012d}"
    return f"frame-{run_id}-{timestamp_ms:012d}"


def _frames_path(context: RunContext) -> Path:
    return context.run_directory / "frames.json"


def _load_existing(path: Path, context: RunContext) -> tuple[ExtractedFrame, ...]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        frames = tuple(ExtractedFrame.from_dict(item) for item in payload["frames"])
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise FrameExtractionError(f"existing frames output is malformed: {path}") from error
    if payload.get("source_id") != context.source.source_id or any(frame.source_id != context.source.source_id for frame in frames):
        raise FrameExtractionError(f"existing frames output belongs to another source: {path}")
    if any(not Path(frame.artifact.uri).is_file() for frame in frames):
        raise FrameExtractionError(f"existing frames output references missing image files: {path}")
    return frames


def extract_frames(run_id: str, *, workspace_root: str | Path = "workspace", config_path: str | Path | None = "config/pipeline.toml", strategy: str | None = None, interval_ms: int | None = None, force: bool = False, extractor: FrameExtractor | None = None) -> tuple[ExtractedFrame, ...]:
    try:
        context = load_run(run_id, workspace_root=workspace_root)
        source_path = local_source_path(context.source)
        config = frame_sampling_config(config_path, strategy=strategy, interval_ms=interval_ms)
    except (RunError, ValueError) as error:
        raise FrameExtractionError(str(error)) from error
    scenes = _load_scenes(context)
    metadata_path = _frames_path(context)
    if metadata_path.is_file() and not force:
        return _load_existing(metadata_path, context)
    output_directory = context.run_directory / "frames"
    output_directory.mkdir(parents=True, exist_ok=True)
    frame_extractor = extractor or FFmpegFrameExtractor()
    frames: list[ExtractedFrame] = []
    for timestamp_ms, scene_id in sample_timestamps(context, scenes, config):
        frame_id = _frame_id(run_id, timestamp_ms, scene_id)
        output_path = output_directory / f"{frame_id}.{config.image_format}"
        frame_extractor.extract(source_path, timestamp_ms, output_path, config.image_format)
        frames.append(ExtractedFrame(
            frame_id=frame_id, source_id=context.source.source_id, timestamp_ms=timestamp_ms, scene_id=scene_id,
            image_format=config.image_format,
            artifact=ArtifactRef(f"artifact-{frame_id}", "frame", output_path.as_posix(), f"image/{config.image_format}"),
        ))
    payload = {"run_id": run_id, "source_id": context.source.source_id, "sampling": {
        "strategy": config.strategy, "interval_ms": config.interval_ms,
        "scene_relative_offsets": list(config.scene_relative_offsets), "image_format": config.image_format,
    }, "frames": [frame.to_dict() for frame in frames]}
    temporary_path = metadata_path.with_suffix(".json.tmp")
    try:
        temporary_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary_path.replace(metadata_path)
        update_run_artifact(context, ArtifactRef(f"artifact-{run_id}-frames", "frames", metadata_path.as_posix(), "application/json"), stage="frame_extraction")
    except (OSError, RunError) as error:
        raise FrameExtractionError(f"could not write frame metadata: {metadata_path}") from error
    return tuple(frames)
