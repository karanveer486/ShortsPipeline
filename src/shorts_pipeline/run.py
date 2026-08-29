"""URL download and sequential execution of the existing local pipeline stages."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import sys
from typing import Callable
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .adapters.evaluation.ollama import OllamaCandidateEvaluator
from .adapters.reasoning.ollama import OllamaVideoReasoner
from .candidate_discovery import discover_candidates
from .evaluation import evaluate_and_rank
from .frame_extraction import extract_frames
from .ingestion import ingest_local_source
from .reasoning import understand_run
from .render_planning import create_render_plan
from .rendering import render_local
from .runs import RunError, load_run, update_run_artifact
from .scene_detection import detect_scenes
from .semantic_evaluation import hybrid_evaluate_and_rank
from .transcription import transcribe_run
from .visual_analysis import analyze_run
from .domain import ArtifactRef


class PipelineRunError(RuntimeError):
    """One existing stage failed during the sequential pipeline run."""


Downloader = Callable[[str, Path], Path]


def download_source(url: str, workspace_root: str | Path) -> Path:
    """Download one HTTP(S) source into ignored runtime storage, atomically."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise PipelineRunError("source URL must be an absolute http:// or https:// URL")
    downloads = Path(workspace_root) / "downloads"
    suffix = Path(parsed.path).suffix.lower()
    if not suffix or len(suffix) > 10 or not suffix[1:].isalnum():
        suffix = ".video"
    destination = downloads / f"source-{sha256(url.encode('utf-8')).hexdigest()[:20]}{suffix}"
    if destination.is_file() and destination.stat().st_size > 0:
        return destination
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    try:
        downloads.mkdir(parents=True, exist_ok=True)
        request = Request(url, headers={"User-Agent": "ShortsPipeline/0.1"})
        with urlopen(request, timeout=60) as response, temporary.open("wb") as output:
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
        if not temporary.is_file() or temporary.stat().st_size == 0:
            raise PipelineRunError("source download produced an empty file")
        temporary.replace(destination)
        return destination
    except PipelineRunError:
        raise
    except Exception as error:
        raise PipelineRunError(f"could not download source URL: {error}") from error
    finally:
        if temporary.exists():
            temporary.unlink()


def _selected_candidate(run_directory: Path, candidate_id: str | None) -> str:
    if candidate_id:
        return candidate_id
    try:
        ranked = json.loads((run_directory / "ranked_candidates.json").read_text(encoding="utf-8"))["ranked_candidates"]
        selected = ranked[0]["candidate_id"]
    except (OSError, KeyError, TypeError, IndexError, json.JSONDecodeError) as error:
        raise PipelineRunError("candidate ranking did not produce a selectable candidate") from error
    if not isinstance(selected, str) or not selected:
        raise PipelineRunError("candidate ranking contains an invalid candidate ID")
    return selected


def _write_summary(run_id: str, source_url: str, candidate_id: str, *, workspace_root: str | Path) -> Path:
    context = load_run(run_id, workspace_root=workspace_root)
    path = context.run_directory / "run_summary.json"
    try:
        initial = {"run_id": run_id, "source_id": context.source.source_id, "source_url": source_url,
                   "selected_candidate_id": candidate_id,
                   "artifacts": [item.to_dict() for item in context.run.artifacts]}
        path.write_text(json.dumps(initial, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        update_run_artifact(context, ArtifactRef(f"artifact-{run_id}-summary", "run_summary", path.as_posix(), "application/json"), stage="orchestration")
        final_context = load_run(run_id, workspace_root=workspace_root)
        final = {"run_id": run_id, "source_id": final_context.source.source_id, "source_url": source_url,
                 "selected_candidate_id": candidate_id,
                 "artifacts": [item.to_dict() for item in final_context.run.artifacts]}
        path.write_text(json.dumps(final, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except (OSError, RunError) as error:
        raise PipelineRunError(f"could not write run summary: {path}") from error
    return path


def run_pipeline(source_url: str, *, workspace_root: str | Path = "workspace", config_path: str | Path | None = "config/pipeline.toml", candidate_id: str | None = None, force: bool = False, evaluation_mode: str = "semantic", ollama_model: str = "qwen2.5vl:7b", downloader: Downloader = download_source) -> tuple[str, Path, bool]:
    """Run the established stages in order and return run ID, summary, reuse state."""
    if evaluation_mode not in {"semantic", "deterministic"}:
        raise PipelineRunError("evaluation_mode must be semantic or deterministic")
    source_path = downloader(source_url, Path(workspace_root))
    try:
        ingestion = ingest_local_source(source_path, workspace_root=workspace_root)
        run_id = ingestion.run.run_id
        transcribe_run(run_id, workspace_root=workspace_root, config_path=config_path, force=force)
        detect_scenes(run_id, workspace_root=workspace_root, config_path=config_path, force=force)
        extract_frames(run_id, workspace_root=workspace_root, config_path=config_path, force=force)
        analyze_run(run_id, workspace_root=workspace_root, config_path=config_path, model=ollama_model, force=force)
        understand_run(run_id, workspace_root=workspace_root, force=force, reasoner=OllamaVideoReasoner(model=ollama_model))
        discover_candidates(run_id, workspace_root=workspace_root, force=force)
        if evaluation_mode == "semantic":
            hybrid_evaluate_and_rank(run_id, workspace_root=workspace_root, force=force, evaluator=OllamaCandidateEvaluator(model=ollama_model))
        else:
            evaluate_and_rank(run_id, workspace_root=workspace_root, force=force)
        context = load_run(run_id, workspace_root=workspace_root)
        selected = _selected_candidate(context.run_directory, candidate_id)
        create_render_plan(run_id, selected, workspace_root=workspace_root, force=force)
        result = render_local(run_id, selected, workspace_root=workspace_root, force=force)
        summary = _write_summary(run_id, source_url, selected, workspace_root=workspace_root)
        return run_id, summary, result.reused
    except PipelineRunError:
        raise
    except Exception as error:
        raise PipelineRunError(f"pipeline stopped: {error}") from error


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m shorts_pipeline.run", description="Download a source URL and run the existing local ShortsPipeline stages")
    parser.add_argument("source_url", help="HTTP(S) video URL; downloaded only beneath the runtime workspace")
    parser.add_argument("--workspace", default="workspace", help="runtime workspace root (default: workspace)")
    parser.add_argument("--config", default="config/pipeline.toml", help="optional local pipeline TOML configuration")
    parser.add_argument("--candidate-id", help="render this candidate; defaults to rank 1 after evaluation")
    parser.add_argument("--evaluation-mode", choices=("semantic", "deterministic"), default="semantic")
    parser.add_argument("--ollama-model", default="qwen2.5vl:7b", help="existing local Ollama model used by VLM/reasoning/semantic evaluation")
    parser.add_argument("--force", action="store_true", help="recompute stages and re-render where their existing APIs support it")
    args = parser.parse_args()
    try:
        run_id, summary, reused = run_pipeline(args.source_url, workspace_root=args.workspace, config_path=args.config,
                                                candidate_id=args.candidate_id, force=args.force,
                                                evaluation_mode=args.evaluation_mode, ollama_model=args.ollama_model)
    except PipelineRunError as error:
        parser.error(str(error))
    print(f"run={run_id} render={'reused' if reused else 'completed'} summary={summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
