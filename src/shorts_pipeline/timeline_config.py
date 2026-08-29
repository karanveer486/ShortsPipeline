"""Small TOML configuration reader for local timeline adapters."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib
from typing import Any, Mapping


@dataclass(frozen=True)
class TranscriptionConfig:
    model: str = "base"
    language: str | None = None
    device: str | None = None


@dataclass(frozen=True)
class SceneDetectionConfig:
    detector: str = "content"
    threshold: float = 27.0
    min_scene_len: int = 15


def _section(path: str | Path | None, name: str) -> Mapping[str, Any]:
    if path is None:
        return {}
    config_path = Path(path)
    if not config_path.is_file():
        return {}
    try:
        parsed = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ValueError(f"invalid timeline configuration: {config_path}") from error
    value = parsed.get(name, {})
    if not isinstance(value, Mapping):
        raise ValueError(f"[{name}] must be a TOML table")
    return value


def transcription_config(path: str | Path | None = "config/pipeline.toml", *, model: str | None = None) -> TranscriptionConfig:
    values = _section(path, "transcription")
    configured_model = model or values.get("model", "base")
    if not isinstance(configured_model, str) or not configured_model.strip():
        raise ValueError("transcription model must be a non-empty string")
    language = values.get("language")
    device = values.get("device")
    if language is not None and not isinstance(language, str):
        raise ValueError("transcription language must be a string")
    if device is not None and not isinstance(device, str):
        raise ValueError("transcription device must be a string")
    return TranscriptionConfig(model=configured_model, language=language, device=device)


def scene_detection_config(path: str | Path | None = "config/pipeline.toml") -> SceneDetectionConfig:
    values = _section(path, "scene_detection")
    detector = values.get("detector", "content")
    threshold = values.get("threshold", 27.0)
    min_scene_len = values.get("min_scene_len", 15)
    if detector != "content":
        raise ValueError("only the content scene detector is currently supported")
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)) or threshold <= 0:
        raise ValueError("scene detection threshold must be positive")
    if isinstance(min_scene_len, bool) or not isinstance(min_scene_len, int) or min_scene_len <= 0:
        raise ValueError("scene detection min_scene_len must be a positive integer")
    return SceneDetectionConfig(detector=detector, threshold=float(threshold), min_scene_len=min_scene_len)
