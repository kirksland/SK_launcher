from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from core.board_state.migrations import migrate_board_payload


BOARD_FILENAME = ".skyforge_board.json"


def board_path(project_root: Path) -> Path:
    return project_root / BOARD_FILENAME


def load_board_payload(project_root: Path) -> Optional[dict]:
    path = board_path(project_root)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return migrate_board_payload(payload) if isinstance(payload, dict) else None


def save_board_payload(project_root: Path, payload: dict) -> Path:
    path = board_path(project_root)
    payload = migrate_board_payload(payload)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path
