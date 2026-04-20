from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List


PIPELINE_EXTS = {".usd", ".usda", ".usdc", ".usdnc"}
LIBRARY_EXTS = {".obj", ".fbx", ".abc", ".blend", ".gltf", ".glb"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".exr", ".tif", ".tiff"}
TASK_NAMES = {"modeling", "lookdev", "layout", "animation", "vfx", "lighting", "rig", "surfacing"}
TEXTURE_HINTS = {"basecolor", "diffuse", "roughness", "normal", "height", "metallic", "opacity"}


@dataclass(frozen=True)
class AssetFolderProfile:
    path: Path
    pipeline_score: int
    library_score: int
    shot_score: int
    representation_score: int
    entity_type: str
    role: str
    confidence: str
    evidence: List[str]


def profile_entity_collection(root_path: Path) -> AssetFolderProfile:
    children = _child_dirs(root_path)
    evidence: List[str] = []
    pipeline_score = 0
    library_score = 0
    shot_score = 0
    representation_score = 0

    if _collection_has_child_dir_named(children, "publish"):
        pipeline_score += 4
        evidence.append("entity publish folders")
    if _collection_has_child_dir_named(children, "preview"):
        pipeline_score += 2
        evidence.append("entity preview folders")
    if _collection_has_child_dir_named(children, "work"):
        pipeline_score += 1
        evidence.append("entity work folders")
    if _collection_contains_ext(children, PIPELINE_EXTS, nested_names={"publish"}):
        pipeline_score += 4
        evidence.append("published USD files")
    if _collection_contains_task_dirs(children):
        pipeline_score += 2
        evidence.append("task/context folders")

    if _collection_contains_direct_ext(children, LIBRARY_EXTS):
        library_score += 5
        evidence.append("direct source geometry files")
    if _collection_has_child_dir_named(children, "textures"):
        library_score += 3
        evidence.append("texture folders")
    if _collection_contains_texture_maps(children):
        library_score += 2
        evidence.append("texture map naming")

    if _looks_like_shot_collection(root_path, children):
        shot_score += 4
        evidence.append("shot-like child names")
    if _collection_contains_review_media(children):
        shot_score += 1
        evidence.append("review media")

    if _looks_like_representation_root(children):
        representation_score += 4
        evidence.append("representation-only folders")

    has_direct_source_geometry = "direct source geometry files" in evidence
    has_entity_publish_folders = "entity publish folders" in evidence

    if representation_score >= 4 and not has_direct_source_geometry and not has_entity_publish_folders:
        entity_type = "asset"
        role = "representation_source"
        confidence = "medium"
    elif shot_score >= 4 and pipeline_score >= 2:
        entity_type = "shot"
        role = "shot"
        confidence = _confidence(shot_score + pipeline_score)
    elif pipeline_score >= max(library_score, 2):
        entity_type = "asset"
        role = "pipeline_asset"
        confidence = _confidence(pipeline_score)
    elif library_score > 0:
        entity_type = "asset"
        role = "library_asset"
        confidence = _confidence(library_score)
    else:
        entity_type = "asset"
        role = "unknown_asset"
        confidence = "low"
        evidence.append("generic folder collection")

    return AssetFolderProfile(
        path=root_path,
        pipeline_score=pipeline_score,
        library_score=library_score,
        shot_score=shot_score,
        representation_score=representation_score,
        entity_type=entity_type,
        role=role,
        confidence=confidence,
        evidence=evidence,
    )


def _child_dirs(root_path: Path) -> List[Path]:
    if not root_path.exists() or not root_path.is_dir():
        return []
    try:
        return [child for child in root_path.iterdir() if child.is_dir()]
    except OSError:
        return []


def _collection_has_child_dir_named(children: List[Path], dirname: str) -> bool:
    target = dirname.lower()
    for child in children[:12]:
        try:
            if any(grandchild.is_dir() and grandchild.name.lower() == target for grandchild in child.iterdir()):
                return True
        except OSError:
            continue
    return False


def _collection_contains_ext(children: List[Path], extensions: set[str], *, nested_names: set[str]) -> bool:
    for child in children[:8]:
        for nested_name in nested_names:
            nested = child / nested_name
            if not nested.exists():
                continue
            try:
                if any(path.is_file() and path.suffix.lower() in extensions for path in nested.rglob("*")):
                    return True
            except OSError:
                continue
    return False


def _collection_contains_direct_ext(children: List[Path], extensions: set[str]) -> bool:
    for child in children[:16]:
        try:
            if any(path.is_file() and path.suffix.lower() in extensions for path in child.iterdir()):
                return True
        except OSError:
            continue
    return False


def _collection_contains_task_dirs(children: List[Path]) -> bool:
    for child in children[:12]:
        publish = child / "publish"
        if not publish.exists():
            continue
        try:
            if any(grandchild.is_dir() and grandchild.name.lower() in TASK_NAMES for grandchild in publish.iterdir()):
                return True
        except OSError:
            continue
    return False


def _collection_contains_texture_maps(children: List[Path]) -> bool:
    for child in children[:8]:
        textures = child / "Textures"
        if not textures.exists():
            textures = child / "textures"
        if not textures.exists():
            continue
        try:
            for path in textures.rglob("*"):
                if not path.is_file() or path.suffix.lower() not in IMAGE_EXTS:
                    continue
                name = path.stem.lower()
                if any(hint in name for hint in TEXTURE_HINTS):
                    return True
        except OSError:
            continue
    return False


def _looks_like_shot_collection(root_path: Path, children: List[Path]) -> bool:
    root_name = root_path.name.lower()
    if root_name in {"shots", "shot", "seq", "sequence", "sequences"}:
        return True
    names = [child.name.lower() for child in children[:12]]
    return bool(names) and sum(name.startswith(("sh", "sq", "shot")) for name in names) >= max(2, len(names) // 2)


def _collection_contains_review_media(children: List[Path]) -> bool:
    for child in children[:8]:
        try:
            if any(path.is_file() and path.suffix.lower() in {".mp4", ".mov"} for path in child.rglob("*")):
                return True
        except OSError:
            continue
    return False


def _looks_like_representation_root(children: List[Path]) -> bool:
    if not children:
        return False
    checked = children[:12]
    usd_like = 0
    for child in checked:
        try:
            if any(path.is_file() and path.suffix.lower() in PIPELINE_EXTS for path in child.rglob("*")):
                usd_like += 1
        except OSError:
            continue
    return usd_like >= max(2, len(checked) // 2)


def _confidence(score: int) -> str:
    if score >= 6:
        return "high"
    if score >= 3:
        return "medium"
    return "low"
