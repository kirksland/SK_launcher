from __future__ import annotations

from pathlib import Path
from typing import Sequence

PROJECT_SUBDIRS = (
    "abc",
    "audio",
    "comp",
    "desk",
    "flip",
    "geo",
    "hda",
    "render",
    "scripts",
    "sim",
    "tex",
    "video",
)


def create_project_structure(project_path: Path, subdirs: Sequence[str] = PROJECT_SUBDIRS) -> None:
    project_path.mkdir(parents=True, exist_ok=False)
    for subdir in subdirs:
        (project_path / subdir).mkdir(parents=False, exist_ok=True)
