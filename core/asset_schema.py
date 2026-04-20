from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List

DEFAULT_ASSET_SCHEMA: Dict[str, Any] = {
    "schema_version": 1,
    "preset_id": "default_v1",
    "contexts": [
        "modeling",
        "lookdev",
        "layout",
        "animation",
        "vfx",
        "lighting",
    ],
    "entity_roots": {
        "shot": ["shots"],
        "asset": ["assets"],
    },
    "representations": {
        "usd": {
            "extensions": [".usd", ".usda", ".usdc", ".usdnc"],
            "folders": ["publish", "root"],
        },
        "review_video": {
            "extensions": [".mp4", ".mov"],
            "folders": ["publish"],
        },
        "preview_image": {
            "extensions": [".png", ".jpg", ".jpeg"],
            "folders": ["preview"],
        },
    },
    # Backward-compatible alias used by the current Asset Manager implementation.
    "usd_search": ["publish", "root"],
}


def default_asset_schema() -> Dict[str, Any]:
    return deepcopy(DEFAULT_ASSET_SCHEMA)


def entity_root_candidates(schema: Dict[str, Any], entity_type: str) -> List[str]:
    roots = schema.get("entity_roots", {})
    if not isinstance(roots, dict):
        return []
    values = roots.get(entity_type)
    if not isinstance(values, list):
        return []
    return [str(value) for value in values if isinstance(value, str)]


def representation_folders(schema: Dict[str, Any], representation_name: str) -> List[str]:
    representations = schema.get("representations", {})
    if not isinstance(representations, dict):
        return []
    definition = representations.get(representation_name)
    if not isinstance(definition, dict):
        return []
    folders = definition.get("folders")
    if not isinstance(folders, list):
        return []
    return [str(value) for value in folders if isinstance(value, str)]


def representation_extensions(schema: Dict[str, Any], representation_name: str) -> List[str]:
    representations = schema.get("representations", {})
    if not isinstance(representations, dict):
        return []
    definition = representations.get(representation_name)
    if not isinstance(definition, dict):
        return []
    extensions = definition.get("extensions")
    if not isinstance(extensions, list):
        return []
    return [str(value) for value in extensions if isinstance(value, str)]


def normalize_asset_schema(raw: object) -> Dict[str, Any]:
    schema = default_asset_schema()
    if not isinstance(raw, dict):
        return schema

    schema_version = raw.get("schema_version")
    if isinstance(schema_version, int) and schema_version > 0:
        schema["schema_version"] = schema_version

    preset_id = raw.get("preset_id")
    if isinstance(preset_id, str) and preset_id.strip():
        schema["preset_id"] = preset_id.strip()

    contexts = _normalize_name_list(raw.get("contexts"))
    if contexts:
        schema["contexts"] = contexts

    raw_entity_roots = raw.get("entity_roots")
    if isinstance(raw_entity_roots, dict):
        entity_roots = schema["entity_roots"]
        for entity_type in list(entity_roots.keys()):
            normalized = _normalize_name_list(raw_entity_roots.get(entity_type))
            if normalized:
                entity_roots[entity_type] = normalized

    raw_representations = raw.get("representations")
    if isinstance(raw_representations, dict):
        representations = schema["representations"]
        for rep_name, rep_default in list(representations.items()):
            raw_definition = raw_representations.get(rep_name)
            if not isinstance(raw_definition, dict):
                continue
            normalized_folders = _normalize_name_list(raw_definition.get("folders"))
            if normalized_folders:
                rep_default["folders"] = normalized_folders
            normalized_extensions = _normalize_extension_list(raw_definition.get("extensions"))
            if normalized_extensions:
                rep_default["extensions"] = normalized_extensions

    legacy_usd_search = _normalize_name_list(raw.get("usd_search"))
    if legacy_usd_search:
        schema["representations"]["usd"]["folders"] = legacy_usd_search

    schema["usd_search"] = list(schema["representations"]["usd"]["folders"])
    return schema


def _normalize_name_list(raw: object) -> List[str]:
    if not isinstance(raw, list):
        return []
    cleaned: List[str] = []
    for value in raw:
        if not isinstance(value, str):
            continue
        normalized = value.strip().replace("\\", "/").strip("/").lower()
        if normalized and normalized not in cleaned:
            cleaned.append(normalized)
    return cleaned


def _normalize_extension_list(raw: object) -> List[str]:
    if not isinstance(raw, list):
        return []
    cleaned: List[str] = []
    for value in raw:
        if not isinstance(value, str):
            continue
        normalized = value.strip().lower()
        if not normalized:
            continue
        if not normalized.startswith("."):
            normalized = "." + normalized
        if normalized not in cleaned:
            cleaned.append(normalized)
    return cleaned
