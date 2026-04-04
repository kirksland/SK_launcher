from __future__ import annotations

from pathlib import Path
from typing import List

from PySide6 import QtCore


def update_watcher_paths(watcher: QtCore.QFileSystemWatcher, paths: List[Path]) -> None:
    desired = {str(p) for p in paths if p.exists()}
    current = set(watcher.directories())
    remove = list(current - desired)
    add = list(desired - current)
    if remove:
        watcher.removePaths(remove)
    if add:
        watcher.addPaths(add)
