from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

from core.board_state.migrations import migrate_board_payload


BOARD_FILENAME = ".skyforge_board.json"
BOARD_BACKUP_DIRNAME = ".skyforge_board_backups"


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


def backup_board_payload(project_root: Path, payload: Optional[dict], reason: str) -> Optional[Path]:
    if not isinstance(payload, dict):
        return None
    try:
        backup_dir = project_root / BOARD_BACKUP_DIRNAME
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        safe_reason = _safe_backup_reason(reason)
        backup_path = backup_dir / f"{stamp}_{safe_reason}.json"
        backup_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return backup_path
    except Exception:
        return None


def _safe_backup_reason(reason: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in ("-", "_") else "-" for ch in reason)
    return safe or "backup"
