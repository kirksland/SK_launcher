from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from core.asset_schema import default_asset_schema, normalize_asset_schema
from core.asset_profile import AssetFolderProfile, profile_entity_collection

COMMON_ENTITY_ROOT_ALIASES = {
    "shot": ["shots", "seq", "sequences", "library/shots"],
    "asset": ["assets", "chars", "props", "env", "environments", "library/assets"],
}

COMMON_REPRESENTATION_FOLDERS = {
    "usd": ["publish", "usd", "usd/assets", "usd/shots", "cache/usd", "exports/usd"],
    "review_video": ["review", "playblast", "preview", "renders/review"],
    "preview_image": ["preview", "thumb", "images", "textures", "renders/preview"],
}

KNOWN_CONTEXTS = ["modeling", "lookdev", "layout", "animation", "vfx", "lighting", "comp"]


@dataclass
class DetectedProjectLayout:
    project_root: Path
    schema: Dict[str, Any]
    confidence: str
    warnings: List[str]
    unresolved: List[str]
    evidence: Dict[str, List[str]]


def detect_project_layout(
    project_root: Path,
    *,
    base_schema: Optional[Dict[str, Any]] = None,
) -> DetectedProjectLayout:
    schema = normalize_asset_schema(base_schema or default_asset_schema())
    evidence: Dict[str, List[str]] = {
        "entity_roots": [],
        "entity_sources": [],
        "representations": [],
        "contexts": [],
    }
    warnings: List[str] = []
    unresolved: List[str] = []

    profiles = _detect_entity_source_profiles(project_root, schema)
    if profiles:
        schema["entity_sources"] = [_profile_to_source(project_root, profile) for profile in profiles]

    detected_shot_roots = [
        str(profile.path.relative_to(project_root)).replace("\\", "/").lower()
        for profile in profiles
        if profile.entity_type == "shot" and profile.role != "representation_source"
    ] or _detect_entity_roots(project_root, "shot", schema)
    detected_asset_roots = [
        str(profile.path.relative_to(project_root)).replace("\\", "/").lower()
        for profile in profiles
        if profile.entity_type == "asset" and profile.role not in {"representation_source", "unknown_asset"}
    ] or _detect_entity_roots(project_root, "asset", schema)
    if detected_shot_roots:
        schema["entity_roots"]["shot"] = detected_shot_roots
        evidence["entity_roots"].append(f"shot={', '.join(detected_shot_roots)}")
    else:
        unresolved.append("No shot root detected")
    if detected_asset_roots:
        schema["entity_roots"]["asset"] = detected_asset_roots
        evidence["entity_roots"].append(f"asset={', '.join(detected_asset_roots)}")
    else:
        warnings.append("No asset root detected")

    for profile in profiles:
        rel = str(profile.path.relative_to(project_root)).replace("\\", "/")
        evidence["entity_sources"].append(
            f"{profile.role}:{rel} ({profile.confidence}; {', '.join(profile.evidence)})"
        )

    sample_entities = _sample_entity_dirs(project_root, schema)
    detected_contexts = _detect_contexts(sample_entities)
    if detected_contexts:
        schema["contexts"] = detected_contexts
        evidence["contexts"] = detected_contexts

    for rep_name in ("usd", "review_video", "preview_image"):
        folders = _detect_representation_folders(sample_entities, rep_name, schema)
        if folders:
            schema["representations"][rep_name]["folders"] = folders
            evidence["representations"].append(f"{rep_name}={', '.join(folders)}")
        elif rep_name == "usd":
            warnings.append("No USD publish folder detected")

    schema["usd_search"] = list(schema["representations"]["usd"]["folders"])

    confidence = _confidence_label(
        shot_roots=detected_shot_roots,
        asset_roots=detected_asset_roots,
        usd_folders=schema["representations"]["usd"]["folders"],
        contexts=detected_contexts,
    )
    return DetectedProjectLayout(
        project_root=project_root,
        schema=schema,
        confidence=confidence,
        warnings=warnings,
        unresolved=unresolved,
        evidence=evidence,
    )


def _detect_entity_roots(project_root: Path, entity_type: str, schema: Dict[str, Any]) -> List[str]:
    candidates = list(dict.fromkeys(
        list(schema["entity_roots"].get(entity_type, [])) + COMMON_ENTITY_ROOT_ALIASES.get(entity_type, [])
    ))
    found: List[str] = []
    for candidate in candidates:
        path = project_root / candidate
        if path.exists() and path.is_dir():
            try:
                has_child_dir = any(child.is_dir() for child in path.iterdir())
            except OSError:
                has_child_dir = False
            if has_child_dir and candidate not in found:
                found.append(candidate)
    return found


def _detect_entity_source_profiles(project_root: Path, schema: Dict[str, Any]) -> List[AssetFolderProfile]:
    candidates = _candidate_collection_roots(project_root, schema)
    profiles: List[AssetFolderProfile] = []
    for candidate in candidates:
        profile = profile_entity_collection(candidate)
        if profile.role == "representation_source":
            continue
        if profile.role == "unknown_asset" and profile.confidence == "low":
            continue
        profiles.append(profile)
    profiles.sort(key=lambda profile: (profile.entity_type, profile.role, str(profile.path).lower()))
    return profiles


def _candidate_collection_roots(project_root: Path, schema: Dict[str, Any]) -> List[Path]:
    candidates: List[Path] = []
    seen: set[Path] = set()

    def add(path: Path) -> None:
        if not path.exists() or not path.is_dir() or path in seen:
            return
        try:
            if not any(child.is_dir() for child in path.iterdir()):
                return
        except OSError:
            return
        seen.add(path)
        candidates.append(path)

    for entity_type in ("shot", "asset"):
        for root_name in schema.get("entity_roots", {}).get(entity_type, []):
            add(project_root.joinpath(*[part for part in str(root_name).split("/") if part]))
        for root_name in COMMON_ENTITY_ROOT_ALIASES.get(entity_type, []):
            add(project_root.joinpath(*[part for part in root_name.split("/") if part]))

    try:
        first_level = [child for child in project_root.iterdir() if child.is_dir()]
    except OSError:
        first_level = []

    for child in first_level:
        add(child)
        try:
            for grandchild in child.iterdir():
                if grandchild.is_dir():
                    add(grandchild)
        except OSError:
            continue
    return candidates


def _profile_to_source(project_root: Path, profile: AssetFolderProfile) -> Dict[str, Any]:
    return {
        "path": str(profile.path.relative_to(project_root)).replace("\\", "/").lower(),
        "entity_type": profile.entity_type,
        "role": profile.role,
        "confidence": profile.confidence,
        "evidence": profile.evidence,
    }


def _sample_entity_dirs(project_root: Path, schema: Dict[str, Any]) -> List[Path]:
    samples: List[Path] = []
    for entity_type in ("shot", "asset"):
        for root_name in schema["entity_roots"].get(entity_type, []):
            root_path = project_root / root_name
            if not root_path.exists():
                continue
            try:
                children = [child for child in root_path.iterdir() if child.is_dir()]
            except OSError:
                continue
            samples.extend(children[:6])
    return samples


def _detect_contexts(entity_dirs: Iterable[Path]) -> List[str]:
    found: List[str] = []
    for entity_dir in entity_dirs:
        publish_dir = entity_dir / "publish"
        if not publish_dir.exists():
            continue
        try:
            children = [child.name.lower() for child in publish_dir.iterdir() if child.is_dir()]
        except OSError:
            continue
        for child_name in children:
            if child_name in KNOWN_CONTEXTS and child_name not in found:
                found.append(child_name)
    return found


def _detect_representation_folders(
    entity_dirs: Iterable[Path],
    representation_name: str,
    schema: Dict[str, Any],
) -> List[str]:
    extensions = set(schema["representations"][representation_name]["extensions"])
    folder_candidates = list(dict.fromkeys(
        list(schema["representations"][representation_name]["folders"])
        + COMMON_REPRESENTATION_FOLDERS.get(representation_name, [])
    ))
    found: List[str] = []
    for candidate in folder_candidates:
        parts = [part for part in candidate.split("/") if part]
        for entity_dir in entity_dirs:
            path = entity_dir.joinpath(*parts)
            if not path.exists() or not path.is_dir():
                continue
            if _folder_contains_extension(path, extensions):
                if candidate not in found:
                    found.append(candidate)
                break
    return found


def _folder_contains_extension(path: Path, extensions: set[str]) -> bool:
    try:
        for child in path.rglob("*"):
            if child.is_file() and child.suffix.lower() in extensions:
                return True
    except OSError:
        return False
    return False


def _confidence_label(
    *,
    shot_roots: List[str],
    asset_roots: List[str],
    usd_folders: List[str],
    contexts: List[str],
) -> str:
    score = 0
    if shot_roots:
        score += 2
    if asset_roots:
        score += 1
    if usd_folders:
        score += 2
    if contexts:
        score += 1
    if score >= 5:
        return "high"
    if score >= 3:
        return "medium"
    return "low"
