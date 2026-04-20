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
    "entity_sources": [
        {
            "path": "shots",
            "entity_type": "shot",
            "role": "shot",
            "confidence": "medium",
            "evidence": ["default convention"],
        },
        {
            "path": "assets",
            "entity_type": "asset",
            "role": "pipeline_asset",
            "confidence": "medium",
            "evidence": ["default convention"],
        },
    ],
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


def entity_sources_for_role(schema: Dict[str, Any], role: str) -> List[Dict[str, Any]]:
    sources = schema.get("entity_sources")
    if not isinstance(sources, list):
        return []
    return [
        source
        for source in sources
        if isinstance(source, dict) and str(source.get("role", "")).strip().lower() == role
    ]


def entity_sources_for_type(schema: Dict[str, Any], entity_type: str) -> List[Dict[str, Any]]:
    sources = schema.get("entity_sources")
    if not isinstance(sources, list):
        return []
    return [
        source
        for source in sources
        if isinstance(source, dict) and str(source.get("entity_type", "")).strip().lower() == entity_type
    ]


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

    raw_entity_sources = raw.get("entity_sources")
    normalized_sources = _normalize_entity_sources(raw_entity_sources)
    if normalized_sources:
        schema["entity_sources"] = normalized_sources
        for entity_type in ("shot", "asset"):
            roots = [
                str(source["path"])
                for source in normalized_sources
                if source.get("entity_type") == entity_type and source.get("role") != "representation_source"
            ]
            if roots:
                schema["entity_roots"][entity_type] = roots
    elif isinstance(raw_entity_roots, dict):
        sources: List[Dict[str, Any]] = []
        for entity_type in ("shot", "asset"):
            for root_name in schema["entity_roots"].get(entity_type, []):
                role = "shot" if entity_type == "shot" else "pipeline_asset"
                sources.append(
                    {
                        "path": root_name,
                        "entity_type": entity_type,
                        "role": role,
                        "confidence": "medium",
                        "evidence": ["legacy entity_roots"],
                    }
                )
        if sources:
            schema["entity_sources"] = sources

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


def _normalize_entity_sources(raw: object) -> List[Dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    cleaned: List[Dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path", "")).strip().replace("\\", "/").strip("/").lower()
        entity_type = str(item.get("entity_type", "")).strip().lower()
        role = str(item.get("role", "")).strip().lower()
        if not path or entity_type not in {"shot", "asset"}:
            continue
        if not role:
            role = "shot" if entity_type == "shot" else "pipeline_asset"
        key = (path, entity_type, role)
        if key in seen:
            continue
        seen.add(key)
        evidence = _normalize_evidence_list(item.get("evidence"))
        confidence = str(item.get("confidence", "low")).strip().lower()
        if confidence not in {"low", "medium", "high"}:
            confidence = "low"
        cleaned.append(
            {
                "path": path,
                "entity_type": entity_type,
                "role": role,
                "confidence": confidence,
                "evidence": evidence,
            }
        )
    return cleaned


def _normalize_evidence_list(raw: object) -> List[str]:
    if not isinstance(raw, list):
        return []
    cleaned: List[str] = []
    for value in raw:
        if not isinstance(value, str):
            continue
        text = value.strip()
        if text and text not in cleaned:
            cleaned.append(text)
    return cleaned
