"""Read and update local run manifests without embedding stage logic."""

from __future__ import annotations

from dataclasses import dataclass, replace
import json
import os
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import unquote, urlparse

from .domain import ArtifactRef, PipelineRun, SourceVideo


MANIFEST_NAME = "manifest.json"


class RunError(RuntimeError):
    """Base error for a local run workspace problem."""


class RunNotFoundError(RunError):
    pass


class RunManifestError(RunError):
    pass


class RunSourceUnavailableError(RunError):
    pass


@dataclass(frozen=True)
class RunContext:
    run_directory: Path
    manifest_path: Path
    source: SourceVideo
    run: PipelineRun


def run_directory(workspace_root: str | Path, run_id: str) -> Path:
    return Path(workspace_root) / "runs" / run_id


def load_run(run_id: str, *, workspace_root: str | Path = "workspace") -> RunContext:
    manifest_path = run_directory(workspace_root, run_id) / MANIFEST_NAME
    if not manifest_path.is_file():
        raise RunNotFoundError(f"run manifest does not exist: {manifest_path}")
    try:
        payload: Mapping[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))
        source = SourceVideo.from_dict(payload["source"])
        run = PipelineRun.from_dict(payload["run"])
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise RunManifestError(f"run manifest is malformed: {manifest_path}") from error
    if run.run_id != run_id or run.source_id != source.source_id:
        raise RunManifestError(f"run manifest identifiers do not match: {manifest_path}")
    return RunContext(manifest_path.parent, manifest_path, source, run)


def local_source_path(source: SourceVideo) -> Path:
    parsed = urlparse(source.reference)
    if parsed.scheme != "file":
        raise RunSourceUnavailableError("timeline stages require a local file: source reference is not a file URI")
    value = unquote(parsed.path)
    if os.name == "nt" and len(value) >= 3 and value[0] == "/" and value[2] == ":":
        value = value[1:]
    path = Path(value)
    if not path.is_file():
        raise RunSourceUnavailableError(f"source video is unavailable: {path}")
    return path


def update_run_artifact(context: RunContext, artifact: ArtifactRef, *, stage: str) -> RunContext:
    """Atomically replace an artifact of the same kind and retain all others."""
    artifacts = tuple(item for item in context.run.artifacts if item.kind != artifact.kind) + (artifact,)
    metadata = dict(context.run.metadata)
    stages = dict(metadata.get("stages", {})) if isinstance(metadata.get("stages"), Mapping) else {}
    stages[stage] = "succeeded"
    metadata["stages"] = stages
    run = replace(context.run, artifacts=artifacts, metadata=metadata)
    payload = {"manifest_version": run.contract_version, "source": context.source.to_dict(), "run": run.to_dict()}
    temporary_path = context.manifest_path.with_suffix(".json.tmp")
    try:
        temporary_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary_path.replace(context.manifest_path)
    except OSError as error:
        raise RunError(f"could not update run manifest: {context.manifest_path}") from error
    return RunContext(context.run_directory, context.manifest_path, context.source, run)
