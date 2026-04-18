from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional, Sequence


def entity_type_for_path(entity_dir: Path) -> str:
    return "shot" if entity_dir.parent.name == "shots" else "asset"


def normalize_list_context(context: str) -> Optional[str]:
    normalized = context.strip().lower()
    if normalized in ("all", "tous", "toutes"):
        return None
    return context


def build_asset_meta_text(owner: str, status: str, context: str, entity_name: str) -> str:
    return (
        f"Owner: {owner}\n"
        f"Status: {status}\n"
        f"Context: {context}\n"
        f"Entity: {entity_name}"
    )


def pick_best_context(
    *,
    entity_type: str,
    current: str,
    contexts: Sequence[str],
    has_content: Callable[[str], bool],
) -> str:
    if entity_type != "shot":
        return current
    if current.strip().lower() in ("all", "tous", "toutes"):
        return current
    if current and has_content(current):
        return current
    for context in contexts:
        if has_content(context):
            return context
    return current


def read_history_note(entity_dir: Path) -> str:
    notes_path = entity_dir / "notes.txt"
    if not notes_path.exists():
        return "No history yet"
    try:
        note = notes_path.read_text(encoding="utf-8").strip()
    except Exception:
        note = ""
    return note or "No history yet"


def empty_versions_message(entity_type: str) -> str:
    if entity_type == "shot":
        return "No published USD/Video for this context"
    return "No published USD for this context"
