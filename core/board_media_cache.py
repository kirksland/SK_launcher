from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Mapping, Optional

from PySide6 import QtGui

from core.project_storage import board_exr_thumb_dir


PixmapCache = dict[tuple[Path, int], tuple[float, QtGui.QPixmap]]


class BoardMediaCache:
    def __init__(self, max_display_dim: int = 2048, settings: Optional[Mapping[str, object]] = None) -> None:
        self.pixmaps: PixmapCache = {}
        self.video_thumbnails: PixmapCache = {}
        self.sequence_thumbnails: PixmapCache = {}
        self.thumb_cache_dir: Optional[Path] = None
        self.max_display_dim = int(max_display_dim)
        self.low_quality = False
        self.visible_images: set[int] = set()
        self.settings = settings

    def cached_pixmap(self, cache: PixmapCache, path: Path, max_dim: int, mtime: float) -> Optional[QtGui.QPixmap]:
        cached = cache.get((path, max_dim))
        if cached and cached[0] == mtime:
            return cached[1]
        return None

    def store_pixmap(
        self,
        cache: PixmapCache,
        path: Path,
        max_dim: int,
        mtime: float,
        pixmap: QtGui.QPixmap,
    ) -> QtGui.QPixmap:
        cache[(path, max_dim)] = (mtime, pixmap)
        return pixmap

    def project_thumb_cache_dir(self, project_root: Optional[Path]) -> Optional[Path]:
        if self.thumb_cache_dir is not None:
            return self.thumb_cache_dir
        cache_dir = board_exr_thumb_dir(project_root, self.settings)
        if cache_dir is None:
            return None
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            return None
        self.thumb_cache_dir = cache_dir
        return cache_dir

    def exr_cache_path(self, project_root: Optional[Path], path: Path, max_dim: int) -> Optional[Path]:
        cache_dir = self.project_thumb_cache_dir(project_root)
        if cache_dir is None:
            return None
        try:
            mtime = path.stat().st_mtime
        except Exception:
            mtime = 0.0
        key_src = f"{path.resolve()}|{mtime:.6f}|{max_dim}"
        key = hashlib.sha1(key_src.encode("utf-8")).hexdigest()
        return cache_dir / f"{key}.png"

    def reset_project_scoped(self) -> None:
        self.thumb_cache_dir = None
        self.visible_images.clear()
