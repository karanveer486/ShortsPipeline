"""Local Ollama implementation of the provider-neutral video reasoner."""
from __future__ import annotations
import json
from typing import Any, Mapping
from ..vlm.ollama import OllamaVLMError, Transport, _post_json, _strip_json_fence
from .contracts import ReasoningChunk
from ...domain import EvidenceRef, TimeRange, UnderstandingItem

class OllamaReasoningError(RuntimeError): pass

def parse_reasoning_items(response: Mapping[str, Any], source_id: str, allowed_scene_ids: set[str]) -> tuple[UnderstandingItem, ...]:
    message = response.get("message")
    content = message.get("content") if isinstance(message, Mapping) else None
    try: data = json.loads(_strip_json_fence(content)) if isinstance(content, str) else None
    except json.JSONDecodeError as error: raise OllamaReasoningError("reasoner returned invalid JSON") from error
    items = data.get("items") if isinstance(data, Mapping) else None
    if not isinstance(items, list): raise OllamaReasoningError("reasoner response requires an items array")
    result = []
    for index, item in enumerate(items):
        if not isinstance(item, Mapping) or not isinstance(item.get("evidence"), Mapping): raise OllamaReasoningError(f"reasoning item {index} is malformed")
        evidence_data = item["evidence"]
        try:
            evidence = EvidenceRef(tuple(evidence_data.get("scene_ids", [])), tuple(TimeRange.from_dict(part) for part in evidence_data.get("time_ranges", [])))
            if not set(evidence.scene_ids) <= allowed_scene_ids: raise OllamaReasoningError(f"reasoning item {index} cites unavailable scenes")
            attributes = dict(item.get("attributes", {})); attributes["observation_ids"] = list(evidence_data.get("observation_ids", []))
            result.append(UnderstandingItem(f"understanding-{source_id}-{index:04d}", item["kind"], item["statement"], evidence, item.get("confidence"), attributes))
        except (KeyError, TypeError, ValueError) as error: raise OllamaReasoningError(f"reasoning item {index} is malformed") from error
    return tuple(result)

class OllamaVideoReasoner:
    def __init__(self, *, model: str = "qwen2.5vl:7b", endpoint: str = "http://127.0.0.1:11434/api/chat", timeout_seconds: float = 90, transport: Transport = _post_json) -> None: self.model, self.endpoint, self.timeout_seconds, self._transport = model, endpoint, timeout_seconds, transport
    def _request(self, prompt: str, source_id: str, allowed_scenes: set[str]) -> tuple[UnderstandingItem, ...]:
        body = json.dumps({"model": self.model, "stream": False, "format": "json", "messages": [{"role": "user", "content": prompt}]}).encode()
        try: response = self._transport(self.endpoint, body, self.timeout_seconds)
        except OllamaVLMError as error: raise OllamaReasoningError(str(error)) from error
        return parse_reasoning_items(response, source_id, allowed_scenes)
    def reason_chunk(self, chunk: ReasoningChunk) -> tuple[UnderstandingItem, ...]:
        context = {"scenes": [item.to_dict() for item in chunk.scenes], "transcript": [item.to_dict() for item in chunk.transcript_segments], "observations": [item.to_dict() for item in chunk.observations]}
        prompt = "Infer only supported events/topics, never Shorts potential. Return JSON {items:[{kind,statement,confidence,evidence:{scene_ids,time_ranges,observation_ids},attributes}]}; cite supplied scenes and distinguish inference from observation. Context: " + json.dumps(context)
        return self._request(prompt, chunk.source_id, {item.scene_id for item in chunk.scenes})
    def merge(self, source_id: str, chunks: tuple[tuple[UnderstandingItem, ...], ...]) -> tuple[UnderstandingItem, ...]:
        flat = tuple(item for chunk in chunks for item in chunk)
        prompt = "Merge duplicate/related supported understanding items without inventing evidence or judging Shorts. Return JSON {items:[{kind,statement,confidence,evidence:{scene_ids,time_ranges,observation_ids},attributes}]}. Input: " + json.dumps([item.to_dict() for item in flat])
        return self._request(prompt, source_id, {scene for item in flat for scene in item.evidence.scene_ids})
