"""Configuration for simple, deterministic frame sampling."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib
from typing import Any, Mapping


@dataclass(frozen=True)
class FrameSamplingConfig:
    strategy: str = "interval"
    interval_ms: int = 5_000
    scene_relative_offsets: tuple[float, ...] = (0.5,)
    image_format: str = "jpg"

    def __post_init__(self) -> None:
        if self.strategy not in {"interval", "scene-relative"}:
            raise ValueError("frame strategy must be interval or scene-relative")
        if isinstance(self.interval_ms, bool) or not isinstance(self.interval_ms, int) or self.interval_ms <= 0:
            raise ValueError("frame interval_ms must be a positive integer")
        if not self.scene_relative_offsets or any(not isinstance(item, (float, int)) or isinstance(item, bool) or not 0 <= item < 1 for item in self.scene_relative_offsets):
            raise ValueError("scene_relative_offsets must contain values from 0 (inclusive) to 1 (exclusive)")
        if self.image_format not in {"jpg", "png", "webp"}:
            raise ValueError("frame image_format must be jpg, png, or webp")


def frame_sampling_config(path: str | Path | None = "config/pipeline.toml", *, strategy: str | None = None, interval_ms: int | None = None) -> FrameSamplingConfig:
    values: Mapping[str, Any] = {}
    if path is not None and Path(path).is_file():
        try:
            parsed = tomllib.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError) as error:
            raise ValueError(f"invalid frame-extraction configuration: {path}") from error
        candidate = parsed.get("frame_extraction", {})
        if not isinstance(candidate, Mapping):
            raise ValueError("[frame_extraction] must be a TOML table")
        values = candidate
    offsets = values.get("scene_relative_offsets", (0.5,))
    if not isinstance(offsets, list | tuple):
        raise ValueError("scene_relative_offsets must be a TOML array")
    return FrameSamplingConfig(
        strategy=strategy or values.get("strategy", "interval"),
        interval_ms=interval_ms if interval_ms is not None else values.get("interval_ms", 5_000),
        scene_relative_offsets=tuple(offsets),
        image_format=values.get("image_format", "jpg"),
    )
