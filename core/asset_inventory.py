from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from core.asset_layout import EntityRecord, ResolvedAssetLayout
from core.versions import group_asset_versions


LIBRARY_SOURCE_EXTS = {
    ".abc",
    ".blend",
    ".fbx",
    ".gltf",
    ".glb",
    ".json",
    ".mtl",
    ".obj",
    ".png",
    ".jpg",
    ".jpeg",
    ".exr",
    ".tif",
    ".tiff",
    ".txt",
}

IMAGE_SOURCE_EXTS = {".png", ".jpg", ".jpeg", ".exr", ".tif", ".tiff"}
GEOMETRY_SOURCE_EXTS = {".abc", ".blend", ".fbx", ".gltf", ".glb", ".obj"}


@dataclass(frozen=True)
class AssetInventoryFile:
    path: Path
    kind: str
    label: str
    relative_label: str
    thumbnail_path: Optional[Path] = None


@dataclass(frozen=True)
class AssetInventoryBundle:
    name: str
    entries: List[Dict[str, object]]


@dataclass(frozen=True)
class AssetInventory:
    mode: str
    hint: str
    bundles: List[AssetInventoryBundle]
    files: List[AssetInventoryFile]
    empty_message: str


def build_entity_inventory(
    *,
    entity_dir: Path,
    entity_type: str,
    record: Optional[EntityRecord],
    layout: Optional[ResolvedAssetLayout],
    context: Optional[str],
    context_label: str,
) -> AssetInventory:
    if record is not None and record.role == "library_asset":
        files = collect_library_source_files(entity_dir)
        return AssetInventory(
            mode="source_files",
            hint=f"{len(files)} source file(s)" if files else "No source files found",
            bundles=[],
            files=files,
            empty_message=(
                "No source files found in this library item.\n"
                "Check the manual mapping if this folder is not the real asset root."
            ),
        )

    usd_versions = layout.representation_paths(record, "usd", context=context) if layout and record else []
    video_versions = (
        layout.representation_paths(record, "review_video", context=context)
        if layout and record and entity_type == "shot"
        else []
    )
    image_versions = layout.representation_paths(record, "preview_image") if layout and record else []
    grouped = group_asset_versions(usd_versions, video_versions, image_versions)
    bundles = [
        AssetInventoryBundle(name=base_name, entries=entries)
        for base_name, entries in grouped.items()
    ]
    return AssetInventory(
        mode="published_bundles",
        hint=f"{len(bundles)} bundle(s) in {context_label}" if bundles else f"No bundles in {context_label}",
        bundles=bundles,
        files=[],
        empty_message=empty_versions_message(entity_type),
    )


def collect_library_source_files(entity_dir: Path) -> List[AssetInventoryFile]:
    if not entity_dir.exists():
        return []
    found: List[Path] = []
    try:
        for path in entity_dir.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in LIBRARY_SOURCE_EXTS:
                continue
            found.append(path)
    except OSError:
        return []

    def sort_key(path: Path) -> tuple[int, str]:
        suffix = path.suffix.lower()
        priority = 0 if suffix in GEOMETRY_SOURCE_EXTS else 1
        return (priority, _relative_label(path, entity_dir).lower())

    return [
        _inventory_file(path, entity_dir)
        for path in sorted(found, key=sort_key)[:200]
    ]


def empty_versions_message(entity_type: str) -> str:
    if entity_type == "shot":
        return "No published USD/Video for this context"
    return "No published USD for this context"


def _inventory_file(path: Path, entity_dir: Path) -> AssetInventoryFile:
    suffix = path.suffix.lower()
    kind = "image" if suffix in IMAGE_SOURCE_EXTS else "source"
    return AssetInventoryFile(
        path=path,
        kind=kind,
        label=path.name,
        relative_label=_relative_label(path, entity_dir),
        thumbnail_path=path if kind == "image" else None,
    )


def _relative_label(path: Path, entity_dir: Path) -> str:
    try:
        return path.relative_to(entity_dir).as_posix()
    except ValueError:
        return path.as_posix()
