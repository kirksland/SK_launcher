from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from core.asset_schema import entity_root_candidates, entity_sources_for_role, entity_sources_for_type, representation_extensions, representation_folders

ENTITY_TYPE_ROOT_NAMES = {
    "shot": ["shots", "shot", "seq", "sequence", "sequences"],
    "asset": ["assets", "asset", "chars", "props", "env", "environments"],
}

COMMON_REPRESENTATION_FOLDERS = {
    "usd": ["publish", "root", "usd", "usd/assets", "usd/shots", "cache/usd", "exports/usd"],
    "review_video": ["publish", "review", "playblast", "preview", "renders/review"],
    "preview_image": ["preview", "thumb", "images", "textures", "renders/preview"],
}


@dataclass(frozen=True)
class EntityRecord:
    entity_type: str
    role: str
    name: str
    source_path: Path


@dataclass(frozen=True)
class RepresentationSource:
    representation_name: str
    entity_type: str
    strategy: str
    folder: str
    confidence: int


class ResolvedAssetLayout:
    def __init__(self, project_root: Path, schema: Dict[str, Any]) -> None:
        self.project_root = project_root
        self.schema = schema
        self._entities: Dict[str, List[EntityRecord]] = {
            "shot": self._build_entities("shot"),
            "asset": self._build_entities("asset"),
        }
        self._representation_sources = self._resolve_representation_sources()

    def entities(self, entity_type: str) -> List[EntityRecord]:
        return list(self._entities.get(entity_type, []))

    def entities_by_role(self, role: str) -> List[EntityRecord]:
        return [
            entity
            for entities in self._entities.values()
            for entity in entities
            if entity.role == role
        ]

    def representation_paths(
        self,
        entity: EntityRecord,
        representation_name: str,
        *,
        context: Optional[str] = None,
    ) -> List[Path]:
        allowed_exts = tuple(ext.lower() for ext in representation_extensions(self.schema, representation_name))
        if not allowed_exts:
            return []
        found: List[Path] = []
        seen: set[Path] = set()
        for source in self._representation_sources.get((representation_name, entity.entity_type), []):
            for path in self._paths_for_source(entity, source, context=context, allowed_exts=allowed_exts):
                if path not in seen:
                    seen.add(path)
                    found.append(path)
        return self._sort_paths(found)

    def preview_path(self, entity: EntityRecord) -> Optional[Path]:
        previews = self.representation_paths(entity, "preview_image")
        return previews[0] if previews else None

    def entity_type_for_path(self, entity_path: Path) -> str:
        for entity_type, items in self._entities.items():
            for item in items:
                if item.source_path == entity_path:
                    return entity_type
        return "asset"

    def _build_entities(self, entity_type: str) -> List[EntityRecord]:
        records: List[EntityRecord] = []
        seen: set[Path] = set()
        sources = entity_sources_for_type(self.schema, entity_type)
        if not sources:
            sources = [
                {
                    "path": root_name,
                    "entity_type": entity_type,
                    "role": "shot" if entity_type == "shot" else "pipeline_asset",
                }
                for root_name in entity_root_candidates(self.schema, entity_type)
            ]
        for source in sources:
            role = str(source.get("role", "pipeline_asset")).strip().lower()
            if role == "representation_source":
                continue
            root_name = str(source.get("path", "")).strip()
            if not root_name:
                continue
            root_path = self.project_root.joinpath(*[part for part in root_name.split("/") if part])
            if not root_path.exists():
                continue
            try:
                children = sorted(
                    [child for child in root_path.iterdir() if child.is_dir()],
                    key=lambda child: child.name.lower(),
                )
            except OSError:
                continue
            for child in children:
                if child in seen:
                    continue
                seen.add(child)
                records.append(EntityRecord(entity_type=entity_type, role=role, name=child.name, source_path=child))
        return records

    def _resolve_representation_sources(self) -> Dict[tuple[str, str], List[RepresentationSource]]:
        resolved: Dict[tuple[str, str], List[RepresentationSource]] = {}
        for entity_type in ("shot", "asset"):
            sample_entities = self._entities.get(entity_type, [])[:6]
            for representation_name in ("usd", "review_video", "preview_image"):
                candidates: List[RepresentationSource] = []
                folder_candidates = list(dict.fromkeys(
                    representation_folders(self.schema, representation_name)
                    + COMMON_REPRESENTATION_FOLDERS.get(representation_name, [])
                ))
                for folder in folder_candidates:
                    candidates.extend(self._score_sources(sample_entities, entity_type, representation_name, folder))
                candidates.sort(key=lambda source: source.confidence, reverse=True)
                selected = [candidate for candidate in candidates if candidate.confidence > 0]
                if not selected:
                    selected = [
                        RepresentationSource(
                            representation_name=representation_name,
                            entity_type=entity_type,
                            strategy="entity_local",
                            folder=folder,
                            confidence=0,
                        )
                        for folder in folder_candidates
                    ]
                resolved[(representation_name, entity_type)] = selected
        return resolved

    def _score_sources(
        self,
        sample_entities: List[EntityRecord],
        entity_type: str,
        representation_name: str,
        folder: str,
    ) -> List[RepresentationSource]:
        allowed_exts = tuple(ext.lower() for ext in representation_extensions(self.schema, representation_name))
        strategies = [
            "entity_local",
            "project_relative_name",
            "project_relative_type_name",
        ]
        results: List[RepresentationSource] = []
        for strategy in strategies:
            score = 0
            for entity in sample_entities:
                paths = self._paths_for_source(
                    entity,
                    RepresentationSource(representation_name, entity_type, strategy, folder, 0),
                    context=None,
                    allowed_exts=allowed_exts,
                )
                if paths:
                    score += 1
            results.append(
                RepresentationSource(
                    representation_name=representation_name,
                    entity_type=entity_type,
                    strategy=strategy,
                    folder=folder,
                    confidence=score,
                )
            )
        return results

    def _paths_for_source(
        self,
        entity: EntityRecord,
        source: RepresentationSource,
        *,
        context: Optional[str],
        allowed_exts: Iterable[str],
    ) -> List[Path]:
        folders = [part for part in source.folder.split("/") if part]
        candidates: List[Path] = []
        if source.strategy == "entity_local":
            base = entity.source_path.joinpath(*folders)
            candidates.extend(self._collect_from_base(base, context=context, allowed_exts=allowed_exts))
        elif source.strategy == "project_relative_name":
            base = self.project_root.joinpath(*folders, entity.name)
            candidates.extend(self._collect_from_base(base, context=context, allowed_exts=allowed_exts))
        elif source.strategy == "project_relative_type_name":
            for type_root in ENTITY_TYPE_ROOT_NAMES.get(entity.entity_type, [entity.entity_type]):
                base = self.project_root.joinpath(*folders, type_root, entity.name)
                candidates.extend(self._collect_from_base(base, context=context, allowed_exts=allowed_exts))
        return candidates

    @staticmethod
    def _collect_from_base(base: Path, *, context: Optional[str], allowed_exts: Iterable[str]) -> List[Path]:
        if not base.exists():
            return []
        search_root = base
        if context:
            contextual = base / context
            if contextual.exists():
                search_root = contextual
        allowed = tuple(ext.lower() for ext in allowed_exts)
        try:
            paths = [path for path in search_root.rglob("*") if path.is_file() and path.suffix.lower() in allowed]
        except OSError:
            return []
        return sorted(paths, key=lambda path: (path.name.lower(), str(path).lower()))

    @staticmethod
    def _sort_paths(paths: List[Path]) -> List[Path]:
        def key(path: Path) -> tuple[float, str]:
            try:
                return (path.stat().st_mtime, path.name.lower())
            except OSError:
                return (0.0, path.name.lower())

        return sorted(paths, key=key, reverse=True)


def resolve_asset_layout(project_root: Path, schema: Dict[str, Any]) -> ResolvedAssetLayout:
    return ResolvedAssetLayout(project_root, schema)
