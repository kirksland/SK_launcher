from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from core.asset_details import pick_best_context
from core.asset_layout import EntityRecord, ResolvedAssetLayout
from core.asset_schema import entity_root_candidates


@dataclass(frozen=True)
class ActiveAssetSelection:
    entity_dir: Path
    entity_type: str
    record: EntityRecord | None

    @property
    def tab_label(self) -> str:
        return "Shots" if self.entity_type == "shot" else "Assets"

    @property
    def selection_summary(self) -> str:
        return f"{self.entity_dir.name} [{self.entity_type.upper()}]"


def resolve_entity_type_for_path(
    entity_dir: Path,
    *,
    layout: ResolvedAssetLayout | None,
    schema: Dict[str, Any],
    active_tab_index: int,
) -> str:
    if layout is not None:
        return layout.entity_type_for_path(entity_dir)
    for root_name in entity_root_candidates(schema, "shot"):
        if all(part in entity_dir.parts for part in root_name.split("/")):
            return "shot"
    for root_name in entity_root_candidates(schema, "asset"):
        if all(part in entity_dir.parts for part in root_name.split("/")):
            return "asset"
    return "shot" if active_tab_index == 0 else "asset"


def resolve_entity_record_for_path(
    entity_dir: Path,
    *,
    layout: ResolvedAssetLayout | None,
) -> EntityRecord | None:
    if layout is None:
        return None
    entity_type = layout.entity_type_for_path(entity_dir)
    for record in layout.entities(entity_type):
        if record.source_path == entity_dir:
            return record
    return None


def build_active_asset_selection(
    entity_dir: Path,
    *,
    layout: ResolvedAssetLayout | None,
    schema: Dict[str, Any],
    active_tab_index: int,
    explicit_entity_type: str | None = None,
) -> ActiveAssetSelection:
    entity_type = explicit_entity_type or resolve_entity_type_for_path(
        entity_dir,
        layout=layout,
        schema=schema,
        active_tab_index=active_tab_index,
    )
    record = resolve_entity_record_for_path(entity_dir, layout=layout)
    return ActiveAssetSelection(
        entity_dir=entity_dir,
        entity_type=entity_type,
        record=record,
    )


def choose_best_context_for_selection(
    selection: ActiveAssetSelection,
    *,
    layout: ResolvedAssetLayout | None,
    current: str,
    contexts: Sequence[str],
) -> str:
    def has_content(ctx: str) -> bool:
        if layout and selection.record and layout.representation_paths(selection.record, "usd", context=ctx):
            return True
        if layout and selection.record and layout.representation_paths(selection.record, "review_video", context=ctx):
            return True
        return False

    return pick_best_context(
        entity_type=selection.entity_type,
        current=current,
        contexts=contexts,
        has_content=has_content,
    )
