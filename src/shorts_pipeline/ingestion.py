"""Local source-ingestion stage backed by the ffprobe command-line tool."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from typing import Any, Callable, Mapping

from .domain import ArtifactRef, MediaMetadata, PipelineRun, RunStatus, SourceVideo


CONTRACT_VERSION = "1"
MANIFEST_NAME = "manifest.json"


class IngestionError(RuntimeError):
    """Base error for local source ingestion."""


class SourceNotFoundError(IngestionError):
    pass


class SourceUnreadableError(IngestionError):
    pass


class FFprobeUnavailableError(IngestionError):
    pass


class MediaProbeError(IngestionError):
    pass


class ExistingRunError(IngestionError):
    pass


@dataclass(frozen=True)
class IngestionResult:
    source: SourceVideo
    run: PipelineRun
    manifest_path: Path


Probe = Callable[[Path], MediaMetadata]


def _milliseconds(value: Any) -> int:
    try:
        milliseconds = (Decimal(str(value)) * 1000).to_integral_value()
    except (InvalidOperation, ValueError) as error:
        raise MediaProbeError("ffprobe returned an invalid duration") from error
    if milliseconds <= 0:
        raise MediaProbeError("ffprobe returned a non-positive duration")
    return int(milliseconds)


def _frame_rate(value: Any) -> float:
    if not isinstance(value, str) or not value:
        raise MediaProbeError("ffprobe did not return a frame rate")
    try:
        numerator, denominator = value.split("/", maxsplit=1)
        rate = Decimal(numerator) / Decimal(denominator)
    except (InvalidOperation, ValueError, ZeroDivisionError) as error:
        raise MediaProbeError("ffprobe returned an invalid frame rate") from error
    if rate <= 0:
        raise MediaProbeError("ffprobe returned a non-positive frame rate")
    return float(rate)


def probe_media(source_path: Path, *, executable: str = "ffprobe") -> MediaMetadata:
    """Read basic stream data using ffprobe without opening media in Python."""
    command = [
        executable,
        "-v", "error",
        "-show_entries", "format=duration,format_name:stream=codec_type,codec_name,width,height,avg_frame_rate,r_frame_rate",
        "-of", "json",
        str(source_path),
    ]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, check=False, timeout=30)
    except FileNotFoundError as error:
        raise FFprobeUnavailableError("ffprobe is not available on PATH") from error
    except subprocess.TimeoutExpired as error:
        raise MediaProbeError("ffprobe timed out while reading the source") from error
    except OSError as error:
        raise MediaProbeError(f"could not start ffprobe: {error}") from error

    if completed.returncode != 0:
        detail = completed.stderr.strip() or "no diagnostic output"
        raise MediaProbeError(f"ffprobe could not read the source: {detail}")
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise MediaProbeError("ffprobe returned malformed JSON") from error
    if not isinstance(payload, Mapping):
        raise MediaProbeError("ffprobe JSON root must be an object")

    format_data = payload.get("format")
    streams = payload.get("streams")
    if not isinstance(format_data, Mapping) or not isinstance(streams, list):
        raise MediaProbeError("ffprobe output is missing format or streams")
    video = next((item for item in streams if isinstance(item, Mapping) and item.get("codec_type") == "video"), None)
    if video is None:
        raise MediaProbeError("source contains no video stream")
    try:
        width = int(video["width"])
        height = int(video["height"])
        duration_ms = _milliseconds(format_data["duration"])
        frame_rate = _frame_rate(video.get("avg_frame_rate") or video.get("r_frame_rate"))
    except (KeyError, TypeError, ValueError) as error:
        raise MediaProbeError("ffprobe output is missing required video metadata") from error
    audio = next((item for item in streams if isinstance(item, Mapping) and item.get("codec_type") == "audio"), None)
    return MediaMetadata(
        duration_ms=duration_ms,
        width=width,
        height=height,
        frame_rate=frame_rate,
        container=format_data.get("format_name") if isinstance(format_data.get("format_name"), str) else None,
        video_codec=video.get("codec_name") if isinstance(video.get("codec_name"), str) else None,
        audio_codec=audio.get("codec_name") if isinstance(audio, Mapping) and isinstance(audio.get("codec_name"), str) else None,
    )


def _source_fingerprint(source_path: Path) -> str:
    stat = source_path.stat()
    material = f"{source_path.resolve()}\0{stat.st_size}\0{stat.st_mtime_ns}".encode("utf-8")
    return sha256(material).hexdigest()[:20]


def _read_existing_manifest(path: Path) -> IngestionResult:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        source = SourceVideo.from_dict(payload["source"])
        run = PipelineRun.from_dict(payload["run"])
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ExistingRunError(f"existing run manifest is invalid: {path}") from error
    return IngestionResult(source=source, run=run, manifest_path=path)


def _write_manifest(path: Path, source: SourceVideo, run: PipelineRun) -> None:
    payload = {"manifest_version": CONTRACT_VERSION, "source": source.to_dict(), "run": run.to_dict()}
    temporary_path = path.with_suffix(".json.tmp")
    temporary_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary_path.replace(path)


def ingest_local_source(source_path: str | Path, *, workspace_root: str | Path = "workspace", probe: Probe = probe_media) -> IngestionResult:
    """Inspect one local file and create (or safely reopen) its ingestion run."""
    source = Path(source_path).expanduser()
    if not source.exists():
        raise SourceNotFoundError(f"source does not exist: {source}")
    if not source.is_file():
        raise SourceUnreadableError(f"source is not a file: {source}")
    try:
        source = source.resolve(strict=True)
        fingerprint = _source_fingerprint(source)
    except OSError as error:
        raise SourceUnreadableError(f"source cannot be read: {source}") from error

    source_id = f"source-{fingerprint}"
    run_id = f"run-{fingerprint}"
    run_directory = Path(workspace_root) / "runs" / run_id
    manifest_path = run_directory / MANIFEST_NAME
    if manifest_path.exists():
        existing = _read_existing_manifest(manifest_path)
        if existing.run.run_id != run_id or existing.source.source_id != source_id:
            raise ExistingRunError(f"existing manifest does not match expected run: {manifest_path}")
        return existing

    media = probe(source)
    stat = source.stat()
    source_artifact = ArtifactRef(
        artifact_id=f"artifact-{source_id}",
        kind="source_video",
        uri=source.as_uri(),
        metadata={"byte_size": stat.st_size},
    )
    source_model = SourceVideo(
        source_id=source_id,
        reference=source.as_uri(),
        media=media,
        metadata={"file_name": source.name, "byte_size": stat.st_size},
    )
    manifest_artifact = ArtifactRef(
        artifact_id=f"artifact-{run_id}-manifest",
        kind="run_manifest",
        uri=(Path("workspace") / "runs" / run_id / MANIFEST_NAME).as_posix(),
        media_type="application/json",
    )
    run = PipelineRun(
        run_id=run_id,
        source_id=source_id,
        created_at=datetime.now(timezone.utc),
        contract_version=CONTRACT_VERSION,
        status=RunStatus.SUCCEEDED,
        artifacts=(source_artifact, manifest_artifact),
        metadata={"stage": "ingestion"},
    )
    try:
        run_directory.mkdir(parents=True, exist_ok=True)
        _write_manifest(manifest_path, source_model, run)
    except OSError as error:
        raise IngestionError(f"could not write run manifest: {manifest_path}") from error
    return IngestionResult(source=source_model, run=run, manifest_path=manifest_path)
