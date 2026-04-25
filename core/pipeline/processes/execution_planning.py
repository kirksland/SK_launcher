from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional, Sequence

from core.asset_inventory import GEOMETRY_SOURCE_EXTS, collect_library_source_files
from core.asset_layout import EntityRecord, ResolvedAssetLayout
from core.asset_schema import entity_root_candidates, entity_sources_for_role


@dataclass(frozen=True)
class ProcessExecutionPlan:
    process_id: str
    parameters: Mapping[str, object] | None = None
    status_message: str = ""
    run_summary: str = ""

    @property
    def is_ready(self) -> bool:
        return self.parameters is not None


def resolve_effective_pipeline_context(
    current_context: object,
    schema_contexts: Sequence[object],
) -> str:
    current = str(current_context or "").strip().lower()
    if current and current != "all":
        return current
    for value in schema_contexts:
        text = str(value or "").strip().lower()
        if text:
            return text
    return "modeling"


def plan_asset_manager_process_execution(
    process_id: object,
    *,
    entity_dir: Path | None,
    current_inventory_path: Path | None,
    record: EntityRecord | None,
    layout: ResolvedAssetLayout | None,
    current_context: object,
    schema_contexts: Sequence[object],
    ensure_dirs: bool = False,
) -> ProcessExecutionPlan:
    normalized_id = str(process_id or "").strip()
    if normalized_id == "publish.asset.usd":
        return _plan_publish_asset_usd(
            entity_dir=entity_dir,
            current_inventory_path=current_inventory_path,
            record=record,
            layout=layout,
            current_context=current_context,
            schema_contexts=schema_contexts,
            ensure_dirs=ensure_dirs,
        )
    return ProcessExecutionPlan(
        process_id=normalized_id,
        status_message=f"{normalized_id} is not executable from the Asset Manager yet.",
        run_summary=(
            f"{normalized_id} is visible in the inspector, but its execution planner is not wired yet."
        ),
    )


def _plan_publish_asset_usd(
    *,
    entity_dir: Path | None,
    current_inventory_path: Path | None,
    record: EntityRecord | None,
    layout: ResolvedAssetLayout | None,
    current_context: object,
    schema_contexts: Sequence[object],
    ensure_dirs: bool,
) -> ProcessExecutionPlan:
    if entity_dir is None:
        return ProcessExecutionPlan(
            process_id="publish.asset.usd",
            status_message="No entity selected.",
        )
    source_path = resolve_publish_source_path(
        entity_dir=entity_dir,
        current_inventory_path=current_inventory_path,
        record=record,
    )
    if source_path is None:
        return ProcessExecutionPlan(
            process_id="publish.asset.usd",
            status_message="No geometry source found for publish.asset.usd.",
            run_summary="No supported geometry source was found for this selection.",
        )
    context = resolve_effective_pipeline_context(current_context, schema_contexts)
    output_path = resolve_publish_output_path(
        entity_dir=entity_dir,
        context=context,
        record=record,
        layout=layout,
    )
    if ensure_dirs:
        output_path.parent.mkdir(parents=True, exist_ok=True)
    return ProcessExecutionPlan(
        process_id="publish.asset.usd",
        parameters={
            "source": source_path.as_posix(),
            "output": output_path.as_posix(),
            "context": context,
        },
    )


def resolve_publish_source_path(
    *,
    entity_dir: Path,
    current_inventory_path: Path | None,
    record: EntityRecord | None,
) -> Optional[Path]:
    if (
        current_inventory_path is not None
        and current_inventory_path.exists()
        and current_inventory_path.suffix.lower() in GEOMETRY_SOURCE_EXTS
    ):
        return current_inventory_path
    if record is not None and record.role == "library_asset":
        for file in collect_library_source_files(entity_dir):
            if file.path.suffix.lower() in GEOMETRY_SOURCE_EXTS:
                return file.path
    try:
        candidates = sorted(
            (
                path
                for path in entity_dir.rglob("*")
                if path.is_file() and path.suffix.lower() in GEOMETRY_SOURCE_EXTS
            ),
            key=lambda path: (len(path.parts), path.as_posix().lower()),
        )
    except OSError:
        candidates = []
    return candidates[0] if candidates else None


def resolve_publish_output_path(
    *,
    entity_dir: Path,
    context: str,
    record: EntityRecord | None,
    layout: ResolvedAssetLayout | None,
) -> Path:
    if layout is not None and record is not None:
        if record.role == "library_asset":
            managed_dir = resolve_managed_asset_dir(record, layout)
            return managed_dir / "publish" / context / f"{record.name}.usdnc"
        existing = layout.representation_paths(record, "usd", context=context)
        if existing:
            return existing[0]
    return entity_dir / "publish" / context / f"{entity_dir.name}.usdnc"


def resolve_managed_asset_dir(record: EntityRecord, layout: ResolvedAssetLayout) -> Path:
    for candidate in layout.entities_by_role("pipeline_asset"):
        if candidate.name.strip().lower() == record.name.strip().lower():
            return candidate.source_path

    pipeline_sources = entity_sources_for_role(layout.schema, "pipeline_asset")
    for source in pipeline_sources:
        if str(source.get("entity_type", "")).strip().lower() != "asset":
            continue
        root_name = str(source.get("path", "")).strip()
        if root_name:
            return layout.project_root.joinpath(
                *[part for part in root_name.split("/") if part]
            ) / record.name

    for root_name in entity_root_candidates(layout.schema, "asset"):
        if root_name:
            return layout.project_root.joinpath(
                *[part for part in root_name.split("/") if part]
            ) / record.name

    return layout.project_root / "assets" / record.name
