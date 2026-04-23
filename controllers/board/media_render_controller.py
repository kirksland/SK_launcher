from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from PySide6 import QtCore, QtGui

try:
    import cv2  # type: ignore
except Exception:  # pragma: no cover - optional video backend
    cv2 = None  # type: ignore

try:  # Optional OpenEXR header access for channels/metadata.
    import OpenEXR  # type: ignore
except Exception:  # pragma: no cover - optional exr backend
    OpenEXR = None  # type: ignore

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".exr"}
PIC_EXTS = {".pic", ".picnc"}
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}


class BoardMediaRenderController:
    """Owns media display pixmaps, thumbnails, and file-kind helpers."""

    def __init__(self, board_controller: object) -> None:
        self.board = board_controller

    def get_display_pixmap(self, path: Path, max_dim: Optional[int] = None) -> QtGui.QPixmap:
        board = self.board
        try:
            mtime = path.stat().st_mtime
        except Exception:
            return QtGui.QPixmap(str(path))
        if max_dim is None:
            max_dim = board._max_display_dim
        cached = board._media_cache.cached_pixmap(board._media_cache.pixmaps, path, max_dim, mtime)
        if cached is not None:
            return cached
        pixmap = QtGui.QPixmap(str(path))
        if pixmap.isNull() and path.suffix.lower() == ".exr":
            pixmap = self.get_exr_pixmap(path, max_dim)
        if not pixmap.isNull():
            if pixmap.width() > max_dim or pixmap.height() > max_dim:
                pixmap = pixmap.scaled(
                    max_dim,
                    max_dim,
                    QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                    QtCore.Qt.TransformationMode.SmoothTransformation,
                )
        return board._media_cache.store_pixmap(board._media_cache.pixmaps, path, max_dim, mtime, pixmap)

    def get_thumb_cache_dir(self) -> Optional[Path]:
        return self.board._media_cache.project_thumb_cache_dir(self.board._project_root)

    def exr_cache_key(self, path: Path, max_dim: int) -> Optional[Path]:
        return self.board._media_cache.exr_cache_path(self.board._project_root, path, max_dim)

    def get_exr_pixmap(self, path: Path, max_dim: int) -> QtGui.QPixmap:
        cache_path = self.exr_cache_key(path, max_dim)
        if cache_path is not None and cache_path.exists():
            cached = QtGui.QPixmap(str(cache_path))
            if not cached.isNull():
                return cached
        if cv2 is None:
            return self.build_media_placeholder("EXR", f"{path.name}\n(OpenCV missing)")
        if not os.environ.get("OPENCV_IO_ENABLE_OPENEXR"):
            return self.build_media_placeholder("EXR", "OpenEXR codec disabled")
        try:
            import numpy as np  # type: ignore
        except Exception:
            return self.build_media_placeholder("EXR", path.name)
        try:
            img = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
        except Exception:
            img = None
        if img is None:
            return self.build_media_placeholder("EXR", "Failed to read EXR")
        if img.ndim == 2:
            img = np.stack([img, img, img], axis=-1)
        if img.ndim == 3 and img.shape[2] == 1:
            img = np.repeat(img, 3, axis=2)
        if img.ndim == 3 and img.shape[2] >= 3:
            img = img[:, :, :3]
        if img.dtype != np.uint8:
            img_f = img.astype(np.float32)
            max_val = float(np.nanmax(img_f)) if img_f.size else 1.0
            if max_val <= 1.0:
                img_f = img_f * 255.0
            else:
                img_f = (img_f / max_val) * 255.0
            img = np.clip(img_f, 0, 255).astype(np.uint8)
        try:
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        except Exception:
            pass
        h, w = img.shape[:2]
        bytes_per_line = img.shape[2] * w
        qimage = QtGui.QImage(img.data, w, h, bytes_per_line, QtGui.QImage.Format.Format_RGB888)
        pixmap = QtGui.QPixmap.fromImage(qimage.copy())
        if pixmap.width() > max_dim or pixmap.height() > max_dim:
            pixmap = pixmap.scaled(
                max_dim,
                max_dim,
                QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                QtCore.Qt.TransformationMode.SmoothTransformation,
            )
        if cache_path is not None:
            try:
                pixmap.save(str(cache_path), "PNG")
            except Exception:
                pass
        return pixmap

    def get_image_size(self, path: Path, fallback: Optional[QtCore.QSize] = None) -> QtCore.QSize:
        if path.suffix.lower() == ".exr":
            if OpenEXR is not None:
                try:
                    exr = OpenEXR.InputFile(str(path))
                    header = exr.header()
                    dw = header.get("dataWindow")
                    if dw is not None:
                        w = int(dw.max.x - dw.min.x + 1)
                        h = int(dw.max.y - dw.min.y + 1)
                        return QtCore.QSize(w, h)
                except Exception:
                    pass
            if cv2 is not None:
                try:
                    img = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
                    if img is not None:
                        return QtCore.QSize(int(img.shape[1]), int(img.shape[0]))
                except Exception:
                    pass
        try:
            reader = QtGui.QImageReader(str(path))
            size = reader.size()
            if size.isValid():
                return size
        except Exception:
            pass
        if fallback is not None and fallback.isValid():
            return fallback
        return QtCore.QSize(1, 1)

    def build_media_placeholder(self, label: str, subtitle: str) -> QtGui.QPixmap:
        size = QtCore.QSize(320, 180)
        pixmap = QtGui.QPixmap(size)
        pixmap.fill(QtGui.QColor("#22262d"))
        painter = QtGui.QPainter(pixmap)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QtGui.QPen(QtGui.QColor("#3a404a"), 2))
        painter.drawRoundedRect(pixmap.rect().adjusted(2, 2, -2, -2), 10, 10)
        painter.setPen(QtGui.QColor("#d6d9df"))
        font = painter.font()
        font.setBold(True)
        font.setPointSize(20)
        painter.setFont(font)
        painter.drawText(pixmap.rect().adjusted(0, -10, 0, -10), QtCore.Qt.AlignmentFlag.AlignCenter, label)
        painter.setPen(QtGui.QColor("#9aa3ad"))
        font.setBold(False)
        font.setPointSize(9)
        painter.setFont(font)
        painter.drawText(
            pixmap.rect().adjusted(12, 120, -12, -12),
            QtCore.Qt.AlignmentFlag.AlignCenter | QtCore.Qt.TextFlag.TextWordWrap,
            subtitle,
        )
        painter.end()
        return pixmap

    def get_video_thumbnail(self, path: Path, max_dim: int) -> QtGui.QPixmap:
        board = self.board
        try:
            mtime = path.stat().st_mtime
        except Exception:
            return self.build_media_placeholder("VIDEO", path.name)
        cached = board._media_cache.cached_pixmap(board._media_cache.video_thumbnails, path, max_dim, mtime)
        if cached is not None:
            return cached
        if cv2 is None:
            return self.build_media_placeholder("VIDEO", path.name)
        pixmap = QtGui.QPixmap()
        try:
            cap = cv2.VideoCapture(str(path))
            if not cap.isOpened():
                cap.release()
                return self.build_media_placeholder("VIDEO", path.name)
            ok, frame = cap.read()
            cap.release()
            if ok and frame is not None:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                h, w, ch = rgb.shape
                bytes_per_line = ch * w
                image = QtGui.QImage(rgb.data, w, h, bytes_per_line, QtGui.QImage.Format.Format_RGB888)
                pixmap = QtGui.QPixmap.fromImage(image)
        except Exception:
            pixmap = QtGui.QPixmap()
        if pixmap.isNull():
            pixmap = self.build_media_placeholder("VIDEO", path.name)
        else:
            if pixmap.width() > max_dim or pixmap.height() > max_dim:
                pixmap = pixmap.scaled(
                    max_dim,
                    max_dim,
                    QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                    QtCore.Qt.TransformationMode.SmoothTransformation,
                )
        return board._media_cache.store_pixmap(
            board._media_cache.video_thumbnails,
            path,
            max_dim,
            mtime,
            pixmap,
        )

    def get_video_frame_pixmap(self, path: Path, frame_index: int, max_dim: int) -> Optional[QtGui.QPixmap]:
        if cv2 is None:
            return None
        try:
            cap = cv2.VideoCapture(str(path))
            if not cap.isOpened():
                cap.release()
                return None
            cap.set(1, int(frame_index))  # CAP_PROP_POS_FRAMES
            ok, frame = cap.read()
            cap.release()
            if not ok or frame is None:
                return None
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb.shape
            bytes_per_line = ch * w
            image = QtGui.QImage(rgb.data, w, h, bytes_per_line, QtGui.QImage.Format.Format_RGB888)
            pixmap = QtGui.QPixmap.fromImage(image)
            if pixmap.width() > max_dim or pixmap.height() > max_dim:
                pixmap = pixmap.scaled(
                    max_dim,
                    max_dim,
                    QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                    QtCore.Qt.TransformationMode.SmoothTransformation,
                )
            return pixmap
        except Exception:
            return None

    def sequence_frame_paths(self, dir_path: Path) -> list[Path]:
        if not dir_path.exists() or not dir_path.is_dir():
            return []
        frames = [p for p in dir_path.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTS]
        return sorted(frames, key=lambda p: p.name)

    def get_sequence_thumbnail(self, dir_path: Path, max_dim: int) -> QtGui.QPixmap:
        board = self.board
        try:
            mtime = dir_path.stat().st_mtime
        except Exception:
            return self.build_media_placeholder("SEQ", dir_path.name)
        cached = board._media_cache.cached_pixmap(board._media_cache.sequence_thumbnails, dir_path, max_dim, mtime)
        if cached is not None:
            return cached
        frames = self.sequence_frame_paths(dir_path)
        if not frames:
            return self.build_media_placeholder("SEQ", dir_path.name)
        pixmap = self.get_display_pixmap(frames[0], max_dim)
        if pixmap.isNull():
            pixmap = self.build_media_placeholder("SEQ", dir_path.name)
        return board._media_cache.store_pixmap(
            board._media_cache.sequence_thumbnails,
            dir_path,
            max_dim,
            mtime,
            pixmap,
        )

    @staticmethod
    def is_video_file(path: Path) -> bool:
        return path.is_file() and path.suffix.lower() in VIDEO_EXTS

    @staticmethod
    def is_image_file(path: Path) -> bool:
        return path.is_file() and path.suffix.lower() in IMAGE_EXTS

    @staticmethod
    def is_pic_file(path: Path) -> bool:
        return path.is_file() and path.suffix.lower() in PIC_EXTS
