"""Local FFmpeg execution for an existing, validated render plan."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
from typing import Protocol

from .domain import ArtifactRef, RenderOutput, RenderPlan, RenderStatus, TimeRange, Transcript
from .runs import RunContext, RunError, load_run, local_source_path, update_run_artifact


class RenderExecutionError(RuntimeError):
    """Raised when a local render cannot safely complete."""


class FFmpegUnavailableError(RenderExecutionError):
    pass


class CommandRunner(Protocol):
    def run(self, command: list[str]) -> subprocess.CompletedProcess[str]: ...


class FFmpegRunner:
    """Small subprocess wrapper to keep FFmpeg invocation inspectable and mockable."""

    def __init__(self, executable: str = "ffmpeg") -> None:
        self.executable = executable

    def run(self, command: list[str]) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(command, capture_output=True, text=True, check=False, timeout=600)
        except FileNotFoundError as error:
            raise FFmpegUnavailableError("ffmpeg is not available on PATH") from error
        except subprocess.TimeoutExpired as error:
            raise RenderExecutionError("ffmpeg timed out while rendering") from error
        except OSError as error:
            raise RenderExecutionError(f"could not start ffmpeg: {error}") from error


@dataclass(frozen=True)
class RenderResult:
    render_output: RenderOutput
    reused: bool
    output_path: Path


def _read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RenderExecutionError(f"missing or malformed artifact: {path}") from error


def _plan_path(context: RunContext, candidate_id: str) -> Path:
    if not candidate_id or "/" in candidate_id or "\\" in candidate_id or ".." in candidate_id:
        raise RenderExecutionError("candidate_id is not safe for a render-plan filename")
    return context.run_directory / f"render_plan_{candidate_id}.json"


def _load_plan(context: RunContext, candidate_id: str) -> RenderPlan:
    path = _plan_path(context, candidate_id)
    try:
        plan = RenderPlan.from_dict(_read_json(path))
    except (TypeError, ValueError) as error:
        raise RenderExecutionError(f"render plan is malformed: {path}") from error
    if plan.candidate_id != candidate_id or plan.source_id != context.source.source_id:
        raise RenderExecutionError("render plan belongs to another candidate or source")
    if plan.source_time_range is None or plan.output_duration_ms is None:
        raise RenderExecutionError("render plan is missing source timing")
    if plan.source_time_range.end_ms > context.source.media.duration_ms:
        raise RenderExecutionError("render plan source range exceeds source duration")
    if plan.output_duration_ms != plan.source_time_range.duration_ms:
        raise RenderExecutionError("render plan output duration does not match source range")
    return plan


def _expected_output_path(context: RunContext, plan: RenderPlan) -> Path:
    value = plan.output.get("expected_uri")
    if not isinstance(value, str) or not value:
        raise RenderExecutionError("render plan is missing expected output URI")
    path = Path(value)
    expected_root = context.run_directory / "renders"
    try:
        path.resolve().relative_to(expected_root.resolve())
    except ValueError as error:
        raise RenderExecutionError("render plan output must be inside the run renders directory") from error
    if path.suffix.lower() != ".mp4" or plan.target.container != "mp4":
        raise RenderExecutionError("only MP4 output is currently supported")
    if plan.output.get("video_codec") != "h264" or plan.output.get("audio_codec") != "aac":
        raise RenderExecutionError("only H.264 video and AAC audio are currently supported")
    return path


def _validate_framing(plan: RenderPlan) -> tuple[int, int, int, int]:
    if plan.framing.get("strategy") != "center_crop":
        raise RenderExecutionError("only center_crop framing is currently supported")
    crop = plan.framing.get("crop")
    if not isinstance(crop, dict) or set(crop) != {"x", "y", "width", "height"}:
        raise RenderExecutionError("center_crop render plan requires complete crop geometry")
    values = tuple(crop[key] for key in ("x", "y", "width", "height"))
    if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in values):
        raise RenderExecutionError("crop geometry must use non-negative integer pixels")
    x, y, width, height = values
    if width == 0 or height == 0:
        raise RenderExecutionError("crop geometry dimensions must be positive")
    return x, y, width, height


def _validate_strategies(plan: RenderPlan) -> None:
    if plan.audio.get("strategy") != "preserve_source_audio":
        raise RenderExecutionError("only preserve_source_audio is currently supported")
    if plan.transition.get("strategy") != "hard_cut":
        raise RenderExecutionError("only hard_cut transitions are currently supported")


def _load_transcript(context: RunContext, plan: RenderPlan) -> Transcript:
    try:
        transcript = Transcript.from_dict(_read_json(context.run_directory / "transcript.json"))
    except (TypeError, ValueError) as error:
        raise RenderExecutionError("captions require a valid transcript.json") from error
    if transcript.source_id != plan.source_id:
        raise RenderExecutionError("caption transcript belongs to another source")
    return transcript


def _srt_timestamp(milliseconds: int) -> str:
    if not isinstance(milliseconds, int) or milliseconds < 0:
        raise RenderExecutionError("caption time must be a non-negative integer millisecond value")
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, milliseconds = divmod(remainder, 1_000)
    return f"{hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}"


def _caption_file(context: RunContext, plan: RenderPlan) -> Path | None:
    captions = plan.captions or {}
    strategy = captions.get("strategy")
    if strategy == "disabled":
        return None
    if strategy != "transcript_based":
        raise RenderExecutionError("unsupported caption strategy")
    segments = captions.get("segments")
    if not isinstance(segments, list):
        raise RenderExecutionError("transcript_based captions require a segment list")
    transcript = _load_transcript(context, plan)
    transcript_by_id = {segment.segment_id: segment for segment in transcript.segments}
    lines: list[str] = []
    for index, item in enumerate(segments, start=1):
        if not isinstance(item, dict) or not isinstance(item.get("transcript_segment_id"), str):
            raise RenderExecutionError("caption segment reference is malformed")
        transcript_segment = transcript_by_id.get(item["transcript_segment_id"])
        if transcript_segment is None:
            raise RenderExecutionError("caption references a missing transcript segment")
        try:
            source_range = TimeRange.from_dict(item["source_time_range"])
            output_range = TimeRange.from_dict(item["output_time_range"])
        except (KeyError, TypeError, ValueError) as error:
            raise RenderExecutionError("caption timing is malformed") from error
        expected_source = TimeRange(max(transcript_segment.time_range.start_ms, plan.source_time_range.start_ms), min(transcript_segment.time_range.end_ms, plan.source_time_range.end_ms))
        if source_range != expected_source or output_range != TimeRange(source_range.start_ms - plan.source_time_range.start_ms, source_range.end_ms - plan.source_time_range.start_ms):
            raise RenderExecutionError("caption timing does not match the referenced transcript segment")
        if item.get("text") != transcript_segment.text:
            raise RenderExecutionError("caption text does not match the referenced transcript segment")
        lines.extend((str(index), f"{_srt_timestamp(output_range.start_ms)} --> {_srt_timestamp(output_range.end_ms)}", transcript_segment.text.replace("\r", "").strip(), ""))
    path = context.run_directory / "tmp" / f"{plan.plan_id}.srt"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines), encoding="utf-8")
    except OSError as error:
        raise RenderExecutionError(f"could not write caption file: {path}") from error
    return path


def _subtitle_filter(path: Path) -> str:
    escaped = path.as_posix().replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
    return f"subtitles=filename='{escaped}'"


def build_ffmpeg_command(source_path: Path, plan: RenderPlan, output_path: Path, *, subtitle_path: Path | None = None, executable: str = "ffmpeg") -> list[str]:
    """Return the argument list for a render; no shell command is constructed."""
    if plan.source_time_range is None:
        raise RenderExecutionError("render plan is missing source timing")
    x, y, width, height = _validate_framing(plan)
    filters = [f"crop={width}:{height}:{x}:{y}", f"scale={plan.target.width}:{plan.target.height}:flags=lanczos"]
    if subtitle_path is not None:
        filters.append(_subtitle_filter(subtitle_path))
    return [executable, "-hide_banner", "-loglevel", "error", "-ss", f"{plan.source_time_range.start_ms / 1000:.3f}", "-t", f"{plan.output_duration_ms / 1000:.3f}", "-i", str(source_path), "-map", "0:v:0", "-map", "0:a:0?", "-vf", ",".join(filters), "-r", f"{plan.target.frame_rate:g}", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-movflags", "+faststart", "-y", str(output_path)]


def _output_metadata(plan: RenderPlan) -> dict[str, object]:
    return {"source_id": plan.source_id, "source_time_range": plan.source_time_range.to_dict(), "duration_ms": plan.output_duration_ms, "width": plan.target.width, "height": plan.target.height, "frame_rate": plan.target.frame_rate, "container": "mp4", "video_codec": "h264", "audio_codec": "aac"}


def _render_metadata_path(context: RunContext, candidate_id: str) -> Path:
    return context.run_directory / f"render_output_{candidate_id}.json"


def _load_existing(context: RunContext, plan: RenderPlan, output_path: Path) -> RenderOutput | None:
    path = _render_metadata_path(context, plan.candidate_id)
    if not path.is_file() or not output_path.is_file() or output_path.stat().st_size == 0:
        return None
    try:
        result = RenderOutput.from_dict(_read_json(path))
    except (TypeError, ValueError) as error:
        raise RenderExecutionError(f"existing render metadata is malformed: {path}") from error
    if result.status is not RenderStatus.SUCCEEDED or result.plan_id != plan.plan_id or result.candidate_id != plan.candidate_id or result.output is None or Path(result.output.uri) != output_path:
        raise RenderExecutionError("existing render metadata does not match the render plan")
    return result


def render_local(run_id: str, candidate_id: str, *, workspace_root: str | Path = "workspace", force: bool = False, runner: CommandRunner | None = None, executable: str = "ffmpeg") -> RenderResult:
    """Execute one planned local render and atomically publish its runtime artifacts."""
    try:
        context = load_run(run_id, workspace_root=workspace_root)
        source_path = local_source_path(context.source)
    except RunError as error:
        raise RenderExecutionError(str(error)) from error
    plan = _load_plan(context, candidate_id)
    _validate_strategies(plan)
    output_path = _expected_output_path(context, plan)
    existing = _load_existing(context, plan, output_path)
    if existing is not None and not force:
        return RenderResult(existing, True, output_path)
    subtitle_path = _caption_file(context, plan)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_output = output_path.with_name(f"{output_path.stem}.tmp{output_path.suffix}")
    if temporary_output.exists():
        temporary_output.unlink()
    command = build_ffmpeg_command(source_path, plan, temporary_output, subtitle_path=subtitle_path, executable=executable)
    try:
        completed = (runner or FFmpegRunner()).run(command)
        if completed.returncode != 0:
            raise RenderExecutionError(f"ffmpeg render failed: {completed.stderr.strip() or 'no diagnostic output'}")
        if not temporary_output.is_file() or temporary_output.stat().st_size == 0:
            raise RenderExecutionError("ffmpeg did not produce a video output")
        temporary_output.replace(output_path)
        artifact = ArtifactRef(f"artifact-{plan.plan_id}-render", f"render:{candidate_id}", output_path.as_posix(), "video/mp4", _output_metadata(plan))
        result = RenderOutput(f"render-{plan.plan_id}", plan.plan_id, candidate_id, RenderStatus.SUCCEEDED, artifact, metadata=_output_metadata(plan))
        metadata_path = _render_metadata_path(context, candidate_id)
        metadata_temporary = metadata_path.with_suffix(".json.tmp")
        metadata_temporary.write_text(json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        metadata_temporary.replace(metadata_path)
        updated = update_run_artifact(context, artifact, stage="rendering")
        update_run_artifact(updated, ArtifactRef(f"artifact-{plan.plan_id}-render-output", f"render_output:{candidate_id}", metadata_path.as_posix(), "application/json", {"render_id": result.render_id}), stage="rendering")
        return RenderResult(result, False, output_path)
    except (OSError, RunError) as error:
        raise RenderExecutionError(f"could not finalize render output: {error}") from error
    finally:
        if temporary_output.exists():
            temporary_output.unlink()
