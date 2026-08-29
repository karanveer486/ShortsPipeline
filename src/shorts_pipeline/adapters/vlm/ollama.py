"""Ollama implementation of the provider-neutral visual-analysis protocol."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .contracts import VisualAnalysisRequest
from ...domain import TimeRange, VisualObservation


class OllamaVLMError(RuntimeError):
    """A local Ollama request or response could not be used."""


Transport = Callable[[str, bytes, float], Mapping[str, Any]]


def _post_json(endpoint: str, payload: bytes, timeout_seconds: float) -> Mapping[str, Any]:
    request = Request(endpoint, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            parsed = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        raise OllamaVLMError(f"Ollama returned HTTP {error.code}") from error
    except URLError as error:
        raise OllamaVLMError(f"Ollama is unavailable: {error.reason}") from error
    except TimeoutError as error:
        raise OllamaVLMError("Ollama request timed out") from error
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise OllamaVLMError("Ollama returned malformed JSON") from error
    if not isinstance(parsed, Mapping):
        raise OllamaVLMError("Ollama response must be a JSON object")
    return parsed


def _strip_json_fence(value: str) -> str:
    value = value.strip()
    if value.startswith("```"):
        value = value.split("\n", 1)[1] if "\n" in value else ""
        if value.endswith("```"):
            value = value[:-3]
    return value.strip()


def parse_ollama_observation(response: Mapping[str, Any]) -> tuple[Mapping[str, Any], float | None, float | None]:
    """Parse the deliberately small JSON schema requested from the local model."""
    message = response.get("message")
    content = message.get("content") if isinstance(message, Mapping) else None
    if not isinstance(content, str):
        raise OllamaVLMError("Ollama response is missing message.content")
    try:
        data = json.loads(_strip_json_fence(content))
    except json.JSONDecodeError as error:
        raise OllamaVLMError("Ollama visual response is not valid JSON") from error
    if not isinstance(data, Mapping):
        raise OllamaVLMError("Ollama visual response must be a JSON object")
    observations = data.get("observations")
    if not isinstance(observations, Mapping) or not observations:
        raise OllamaVLMError("Ollama visual response requires a non-empty observations object")
    for key in ("confidence", "uncertainty"):
        value = data.get(key)
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1):
            raise OllamaVLMError(f"Ollama {key} must be a number from 0 to 1")
    return observations, data.get("confidence"), data.get("uncertainty")


class OllamaVisualAnalyzer:
    """Local HTTP-backed adapter; it does not expose Ollama shapes to callers."""

    def __init__(self, *, model: str = "qwen2.5vl:7b", endpoint: str = "http://127.0.0.1:11434/api/chat", timeout_seconds: float = 90.0, transport: Transport = _post_json) -> None:
        self.model = model
        self.endpoint = endpoint
        self.timeout_seconds = timeout_seconds
        self._transport = transport

    def analyze(self, request: VisualAnalysisRequest) -> tuple[VisualObservation, ...]:
        image_data: list[str] = []
        for frame in request.frames:
            path = Path(frame.artifact.uri)
            if not path.is_file():
                raise OllamaVLMError(f"frame image is unavailable: {path}")
            try:
                image_data.append(base64.b64encode(path.read_bytes()).decode("ascii"))
            except OSError as error:
                raise OllamaVLMError(f"could not read frame image: {path}") from error
        scene_id = request.frames[0].scene_id
        frame_ids = [frame.frame_id for frame in request.frames]
        prompt = (
            "Analyze only raw visual evidence from the supplied frames. Return JSON only with this shape: "
            '{"observations":{"people":[],"objects":[],"environment":[],"actions":[],"visible_text":[],"notable_details":[]},'
            '"confidence":0.0,"uncertainty":0.0}. Use empty arrays when unknown. Do not assess quality, virality, titles, or Shorts. '
            f"Scene: {scene_id or 'none'}. Frame timestamps (ms): {[frame.timestamp_ms for frame in request.frames]}. "
            f"Instructions: {request.instructions or 'Describe the visible facts.'}"
        )
        payload = json.dumps({"model": self.model, "stream": False, "format": "json", "messages": [
            {"role": "user", "content": prompt, "images": image_data},
        ]}).encode("utf-8")
        observations, confidence, uncertainty = parse_ollama_observation(self._transport(self.endpoint, payload, self.timeout_seconds))
        start_ms = min(frame.timestamp_ms for frame in request.frames)
        end_ms = max(frame.timestamp_ms for frame in request.frames) + 1
        return (VisualObservation(
            observation_id=f"observation-{request.request_id}", source_id=request.source_id,
            time_range=TimeRange(start_ms, end_ms), scene_id=scene_id, observations=observations,
            confidence=confidence, uncertainty=uncertainty,
            metadata={"frame_ids": frame_ids, "backend": "ollama", "model": self.model},
        ),)
