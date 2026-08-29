# Domain contracts

These standard-library Python dataclasses are the JSON interchange contracts for future pipeline stages. They contain identifiers, references, and validated data; they do not perform media processing or call a provider.

## Conventions

- Every ID is an explicit, non-empty string supplied by the caller. This leaves stable-ID generation to future storage and orchestration decisions.
- All positions and durations are integer milliseconds. `TimeRange` is inclusive at `start_ms` and exclusive at `end_ms`.
- `created_at` and `reviewed_at` are timezone-aware UTC ISO-8601 timestamps in JSON.
- Flexible fields such as `metadata`, visual `observations`, framing, captions, and understanding `attributes` contain only JSON-compatible values.
- `ArtifactRef.uri` is intentionally opaque. A future stage may use a workspace-relative reference, object-store URI, or another resolvable scheme.

## Object graph

```text
SourceVideo ──source_id──> PipelineRun ──> ArtifactRef[]
     ├──> Transcript ──> TranscriptSegment[]
     ├──> Scene[] ──> VisualObservation[]
     └──> VideoUnderstanding ──> UnderstandingItem[] ──> EvidenceRef

ShortCandidate ──> source ID + scene IDs + source TimeRange
RenderPlan     ──> candidate ID + TargetFormat + framing/caption data
RenderOutput   ──> plan ID + candidate ID + optional ArtifactRef
Review         ──> candidate ID + optional render ID
```

`VideoUnderstanding` is deliberately separate from `VisualObservation`: observations preserve flexible, low-level visual evidence, while understanding items express higher-level facts, events, topics, or entities and cite their evidence.

## Provisional choices

The contract version is carried by `PipelineRun`; no persistence format, ID-generation method, scene taxonomy, caption schema, or VLM response schema has been selected. `TargetFormat`, `framing`, and `captions` describe intended render data only. They are not rendering instructions or an implementation.

These contracts are the boundary for future pipeline stages, not an implementation of those stages.
