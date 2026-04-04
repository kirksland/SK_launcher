from __future__ import annotations

import json
from pathlib import Path
from typing import Dict


def load_metadata(entity_dir: Path) -> Dict[str, str]:
    meta_path = entity_dir / "metadata.json"
    if not meta_path.exists():
        return {}
    try:
        data = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return {k: str(v) for k, v in data.items()}
