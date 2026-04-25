from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Optional

from PySide6 import QtCore, QtGui

try:
    import cv2  # type: ignore
except Exception:  # pragma: no cover - optional image backend
    cv2 = None  # type: ignore

try:
    import OpenEXR  # type: ignore
    import Imath  # type: ignore
except Exception:  # pragma: no cover - optional exr backend
    OpenEXR = None  # type: ignore
    Imath = None  # type: ignore

ROOT_DIR = Path(__file__).resolve().parents[2]
BADGE_SVG_PATH = ROOT_DIR / "config" / "icons" / "cloud.svg"
_THUMB_CACHE: dict[tuple[str, int, int, float], QtGui.QPixmap] = {}
_MEDIA_CACHE: dict[tuple[str, int, int, float], QtGui.QPixmap] = {}
_PLACEHOLDER_CACHE: dict[tuple[str, int, int], QtGui.QPixmap] = {}


def is_exr_path(path: Path) -> bool:
    return path.suffix.lower() == ".exr"


def asset_exr_thumb_cache_dir(project_root: Optional[Path]) -> Optional[Path]:
    if project_root is None:
        return None
    if project_root.name == "asset_exr_thumbs":
        cache_dir = project_root
    elif project_root.name == ".skyforge_cache":
        cache_dir = project_root / "asset_exr_thumbs"
    else:
        cache_dir = project_root / ".skyforge_cache" / "asset_exr_thumbs"
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        return None
    return cache_dir


def asset_exr_cache_path(
    project_root: Optional[Path],
    path: Path,
    size: Optional[QtCore.QSize],
) -> Optional[Path]:
    cache_dir = asset_exr_thumb_cache_dir(project_root)
    if cache_dir is None:
        return None
    render_dim = _render_dim_for_size(size)
    try:
        mtime = path.stat().st_mtime
    except Exception:
        mtime = 0.0
    try:
        resolved = path.resolve()
    except Exception:
        resolved = path
    key_src = f"{resolved}|{mtime:.6f}|{render_dim}"
    key = hashlib.sha1(key_src.encode("utf-8")).hexdigest()
    return cache_dir / f"{key}.png"


def make_placeholder_pixmap(text: str, size: QtCore.QSize) -> QtGui.QPixmap:
    cache_key = (text, size.width(), size.height())
    cached = _PLACEHOLDER_CACHE.get(cache_key)
    if cached is not None:
        return cached
    pixmap = QtGui.QPixmap(size)
    pixmap.fill(QtGui.QColor("#2b2f36"))

    painter = QtGui.QPainter(pixmap)
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)

    gradient = QtGui.QLinearGradient(0, 0, size.width(), size.height())
    gradient.setColorAt(0.0, QtGui.QColor("#3a404a"))
    gradient.setColorAt(1.0, QtGui.QColor("#23272e"))
    painter.fillRect(pixmap.rect(), gradient)

    if text:
        painter.setPen(QtGui.QColor("#9aa3ad"))
        font = QtGui.QFont()
        font.setBold(True)
        font.setPointSize(10)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), QtCore.Qt.AlignmentFlag.AlignCenter, text)
    painter.end()

    _PLACEHOLDER_CACHE[cache_key] = pixmap
    return pixmap


def pick_background_image(project_path: Path) -> Optional[Path]:
    # Project-specific thumbnails first
    for ext in (".png", ".jpg", ".jpeg"):
        candidate = project_path / f"thumbnail{ext}"
        if candidate.exists():
            return candidate

    # Shared launcher background in repo root
    horizontal_sf = ROOT_DIR / "horizontalSF.png"
    if horizontal_sf.exists():
        return horizontal_sf

    for ext in (".png", ".jpg", ".jpeg"):
        candidate = ROOT_DIR / f"launcher_bg{ext}"
        if candidate.exists():
            return candidate

    return None


def build_thumbnail_pixmap(project_path: Path, size: QtCore.QSize) -> QtGui.QPixmap:
    image_path = pick_background_image(project_path)
    if image_path is None:
        return make_placeholder_pixmap("Preview", size)

    try:
        mtime = image_path.stat().st_mtime
    except OSError:
        mtime = 0.0
    cache_key = (str(image_path), size.width(), size.height(), mtime)
    cached = _THUMB_CACHE.get(cache_key)
    if cached is not None:
        return cached

    pixmap = QtGui.QPixmap(str(image_path))
    if pixmap.isNull():
        return make_placeholder_pixmap("Preview", size)

    # Fill the box and crop if aspect ratio differs
    scaled = pixmap.scaled(
        size,
        QtCore.Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        QtCore.Qt.TransformationMode.SmoothTransformation,
    )
    # Center-crop to exact size
    x = max(0, (scaled.width() - size.width()) // 2)
    y = max(0, (scaled.height() - size.height()) // 2)
    result = scaled.copy(x, y, size.width(), size.height())
    _THUMB_CACHE[cache_key] = result
    return result


def load_media_pixmap(
    path: Path,
    size: Optional[QtCore.QSize] = None,
    *,
    cache_root: Optional[Path] = None,
    allow_sync_exr: bool = True,
) -> QtGui.QPixmap:
    target_size = size if size is not None else QtCore.QSize(0, 0)
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = 0.0
    cache_key = (str(path), target_size.width(), target_size.height(), mtime)
    cached = _MEDIA_CACHE.get(cache_key)
    if cached is not None:
        return cached

    if is_exr_path(path):
        pixmap = _load_cached_exr_pixmap(path, target_size if size is not None else None, cache_root)
        if pixmap.isNull() and allow_sync_exr:
            pixmap = _load_exr_pixmap(
                path,
                target_size if size is not None else None,
                cache_root=cache_root,
            )
    else:
        pixmap = QtGui.QPixmap(str(path))

    if not pixmap.isNull() and size is not None:
        pixmap = pixmap.scaled(
            size,
            QtCore.Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            QtCore.Qt.TransformationMode.SmoothTransformation,
        )
    if not pixmap.isNull():
        _MEDIA_CACHE[cache_key] = pixmap
    return pixmap


def _load_cached_exr_pixmap(
    path: Path,
    size: Optional[QtCore.QSize],
    cache_root: Optional[Path],
) -> QtGui.QPixmap:
    cache_path = asset_exr_cache_path(cache_root, path, size)
    if cache_path is None or not cache_path.exists():
        return QtGui.QPixmap()
    pixmap = QtGui.QPixmap(str(cache_path))
    if pixmap.isNull():
        return QtGui.QPixmap()
    if size is not None and size.width() > 0 and size.height() > 0:
        return pixmap.scaled(
            size,
            QtCore.Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            QtCore.Qt.TransformationMode.SmoothTransformation,
        )
    return pixmap


def _load_exr_pixmap(
    path: Path,
    size: Optional[QtCore.QSize],
    *,
    cache_root: Optional[Path] = None,
) -> QtGui.QPixmap:
    image = _render_exr_qimage(path, _render_dim_for_size(size))
    if image.isNull():
        return QtGui.QPixmap()
    _write_exr_cache_image(cache_root, path, size, image)
    pixmap = QtGui.QPixmap.fromImage(image)
    if pixmap.isNull():
        return pixmap
    if size is not None and size.width() > 0 and size.height() > 0:
        return pixmap.scaled(
            size,
            QtCore.Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            QtCore.Qt.TransformationMode.SmoothTransformation,
        )
    return pixmap


def _render_dim_for_size(size: Optional[QtCore.QSize]) -> int:
    if size is None:
        return 0
    return max(int(size.width()), int(size.height()), 0)


def _render_exr_qimage(path: Path, max_dim: int = 0) -> QtGui.QImage:
    cv_image = _render_exr_qimage_with_cv2(path, max_dim)
    if not cv_image.isNull():
        return cv_image
    return _render_exr_qimage_with_openexr(path, max_dim)


def _render_exr_qimage_with_cv2(path: Path, max_dim: int = 0) -> QtGui.QImage:
    if cv2 is None:
        return QtGui.QImage()
    try:
        import numpy as np  # type: ignore
    except Exception:
        return QtGui.QImage()
    try:
        img = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    except Exception:
        img = None
    if img is None:
        return QtGui.QImage()
    if img.ndim == 2:
        img = np.stack([img, img, img], axis=-1)
    if img.ndim == 3 and img.shape[2] == 1:
        img = np.repeat(img, 3, axis=2)
    if img.ndim == 3 and img.shape[2] >= 3:
        img = img[:, :, :3]
    if img.dtype != np.uint8:
        img_f = img.astype(np.float32)
        valid = np.isfinite(img_f)
        if not valid.any():
            return QtGui.QImage()
        min_v = float(np.min(img_f[valid]))
        max_v = float(np.max(img_f[valid]))
        if max_v - min_v < 1e-8:
            img_f = np.zeros_like(img_f, dtype=np.float32)
        else:
            img_f = (img_f - min_v) / (max_v - min_v)
        img_f = np.clip(img_f, 0.0, 1.0)
        img_f = np.power(img_f, 1.0 / 2.2, where=img_f > 0)
        img = (img_f * 255.0).astype(np.uint8)
    try:
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    except Exception:
        rgb = img
    if max_dim > 0:
        current_h = int(rgb.shape[0])
        current_w = int(rgb.shape[1])
        if current_w > max_dim or current_h > max_dim:
            scale = float(max_dim) / float(max(current_w, current_h))
            scaled_w = max(1, int(round(current_w * scale)))
            scaled_h = max(1, int(round(current_h * scale)))
            try:
                rgb = cv2.resize(rgb, (scaled_w, scaled_h), interpolation=cv2.INTER_AREA)
            except Exception:
                ys = np.linspace(0, current_h - 1, scaled_h).astype(np.int32)
                xs = np.linspace(0, current_w - 1, scaled_w).astype(np.int32)
                rgb = rgb[ys][:, xs]
    rgb = rgb.copy()
    return QtGui.QImage(
        rgb.data,
        int(rgb.shape[1]),
        int(rgb.shape[0]),
        int(rgb.shape[1] * 3),
        QtGui.QImage.Format.Format_RGB888,
    ).copy()


def _render_exr_qimage_with_openexr(path: Path, max_dim: int = 0) -> QtGui.QImage:
    if OpenEXR is None or Imath is None:
        return QtGui.QImage()
    try:
        import numpy as np  # type: ignore
    except Exception:
        return QtGui.QImage()
    try:
        exr = OpenEXR.InputFile(str(path))
        header = exr.header()
        data_window = header.get("dataWindow")
        if data_window is None:
            return QtGui.QImage()
        width = int(data_window.max.x - data_window.min.x + 1)
        height = int(data_window.max.y - data_window.min.y + 1)
        if width <= 0 or height <= 0:
            return QtGui.QImage()

        channel_names = sorted(str(name) for name in header.get("channels", {}).keys())
        if not channel_names:
            return QtGui.QImage()
        preferred_channel = _preferred_exr_channel(channel_names)
        pixel_type = Imath.PixelType(Imath.PixelType.FLOAT)

        def read_channel(name: str) -> np.ndarray:
            try:
                raw = exr.channel(name, pixel_type)
            except Exception:
                return np.zeros((height, width), dtype=np.float32)
            array = np.frombuffer(raw, dtype=np.float32)
            if array.size != width * height:
                return np.zeros((height, width), dtype=np.float32)
            return array.reshape((height, width))

        if preferred_channel.endswith(".RGB"):
            prefix = preferred_channel[:-4]
            rgb = np.stack(
                [
                    read_channel(f"{prefix}.R"),
                    read_channel(f"{prefix}.G"),
                    read_channel(f"{prefix}.B"),
                ],
                axis=-1,
            )
        elif preferred_channel in ("RGB", "RGBA"):
            rgb = np.stack(
                [
                    read_channel("R"),
                    read_channel("G"),
                    read_channel("B"),
                ],
                axis=-1,
            )
        else:
            mono = read_channel(preferred_channel)
            rgb = np.stack([mono, mono, mono], axis=-1)

        valid = np.isfinite(rgb)
        if not valid.any():
            return QtGui.QImage()
        min_value = float(np.min(rgb[valid]))
        max_value = float(np.max(rgb[valid]))
        if max_value - min_value < 1e-8:
            normalized = np.zeros_like(rgb, dtype=np.float32)
        else:
            normalized = (rgb - min_value) / (max_value - min_value)
        normalized = np.clip(normalized, 0.0, 1.0)
        normalized = np.power(normalized, 1.0 / 2.2, where=normalized > 0)
        if max_dim > 0:
            current_h = int(normalized.shape[0])
            current_w = int(normalized.shape[1])
            if current_w > max_dim or current_h > max_dim:
                scale = float(max_dim) / float(max(current_w, current_h))
                scaled_w = max(1, int(round(current_w * scale)))
                scaled_h = max(1, int(round(current_h * scale)))
                ys = np.linspace(0, current_h - 1, scaled_h).astype(np.int32)
                xs = np.linspace(0, current_w - 1, scaled_w).astype(np.int32)
                normalized = normalized[ys][:, xs]
        image_rgb = np.ascontiguousarray((normalized * 255.0).astype(np.uint8))

        image = QtGui.QImage(
            image_rgb.data,
            int(image_rgb.shape[1]),
            int(image_rgb.shape[0]),
            int(image_rgb.shape[1] * 3),
            QtGui.QImage.Format.Format_RGB888,
        ).copy()
        return image
    except Exception:
        return QtGui.QImage()


def _write_exr_cache_image(
    cache_root: Optional[Path],
    path: Path,
    size: Optional[QtCore.QSize],
    image: QtGui.QImage,
) -> Optional[Path]:
    if image.isNull():
        return None
    cache_path = asset_exr_cache_path(cache_root, path, size)
    if cache_path is None:
        return None
    try:
        image.save(str(cache_path), "PNG")
    except Exception:
        return None
    return cache_path


def _preferred_exr_channel(channel_names: list[str]) -> str:
    groups: dict[str, set[str]] = {}
    for name in channel_names:
        if "." in name:
            prefix, suffix = name.rsplit(".", 1)
            groups.setdefault(prefix, set()).add(suffix.upper())
        else:
            groups.setdefault("", set()).add(name.upper())
    if {"R", "G", "B"}.issubset(groups.get("", set())):
        if "A" in groups.get("", set()):
            return "RGBA"
        return "RGB"
    for prefix in sorted(key for key in groups.keys() if key):
        if {"R", "G", "B"}.issubset(groups.get(prefix, set())):
            return f"{prefix}.RGB"
    return channel_names[0]


class _ExrThumbnailTaskSignals(QtCore.QObject):
    finished = QtCore.Signal(str, int, int, bool)


class _ExrThumbnailTask(QtCore.QRunnable):
    def __init__(self, path: Path, size: QtCore.QSize, cache_root: Optional[Path], signals: _ExrThumbnailTaskSignals) -> None:
        super().__init__()
        self._path = path
        self._size = QtCore.QSize(size)
        self._cache_root = cache_root
        self.signals = signals

    def run(self) -> None:
        image = _render_exr_qimage(self._path, _render_dim_for_size(self._size))
        success = not image.isNull()
        if success:
            _write_exr_cache_image(self._cache_root, self._path, self._size, image)
        self.signals.finished.emit(str(self._path), self._size.width(), self._size.height(), success)


class AsyncExrThumbnailLoader(QtCore.QObject):
    previewReady = QtCore.Signal(str, int, int, bool)

    def __init__(self, parent: Optional[QtCore.QObject] = None) -> None:
        super().__init__(parent)
        self._pending: dict[tuple[str, int, int, str], _ExrThumbnailTaskSignals] = {}

    def request(self, path: Path, size: QtCore.QSize, cache_root: Optional[Path] = None) -> None:
        if not is_exr_path(path):
            return
        cached = load_media_pixmap(
            path,
            size,
            cache_root=cache_root,
            allow_sync_exr=False,
        )
        if not cached.isNull():
            QtCore.QTimer.singleShot(
                0,
                lambda p=str(path), w=size.width(), h=size.height(): self.previewReady.emit(p, w, h, True),
            )
            return
        try:
            resolved = str(path.resolve())
        except Exception:
            resolved = str(path)
        cache_key = (resolved, int(size.width()), int(size.height()), str(cache_root or ""))
        if cache_key in self._pending:
            return
        signals = _ExrThumbnailTaskSignals(self)
        self._pending[cache_key] = signals
        signals.finished.connect(
            lambda p, w, h, success, key=cache_key: self._on_task_finished(key, p, w, h, success)
        )
        QtCore.QThreadPool.globalInstance().start(
            _ExrThumbnailTask(path, size, cache_root, signals)
        )

    def _on_task_finished(
        self,
        cache_key: tuple[str, int, int, str],
        path_str: str,
        width: int,
        height: int,
        success: bool,
    ) -> None:
        self._pending.pop(cache_key, None)
        self.previewReady.emit(path_str, width, height, success)


def add_cloud_badge(pixmap: QtGui.QPixmap, badge_path: Optional[Path] = None) -> QtGui.QPixmap:
    if pixmap.isNull():
        return pixmap
    result = QtGui.QPixmap(pixmap)
    painter = QtGui.QPainter(result)
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)

    badge_rect = QtCore.QRect(6, 6, 20, 20)

    svg_drawn = False
    badge_path = badge_path or BADGE_SVG_PATH
    if badge_path.exists():
        try:
            from PySide6 import QtSvg
        except Exception:
            QtSvg = None  # type: ignore[assignment]
        if QtSvg is not None:
            renderer = QtSvg.QSvgRenderer(str(badge_path))
            if renderer.isValid():
                icon_size = 20
                icon_rect = QtCore.QRect(
                    badge_rect.center().x() - icon_size // 2,
                    badge_rect.center().y() - icon_size // 2,
                    icon_size,
                    icon_size,
                )
                icon_pix = QtGui.QPixmap(icon_rect.size())
                icon_pix.fill(QtCore.Qt.GlobalColor.transparent)
                icon_painter = QtGui.QPainter(icon_pix)
                renderer.render(icon_painter)
                icon_painter.end()
                painter.drawPixmap(icon_rect.topLeft(), icon_pix)
                svg_drawn = True

    if not svg_drawn:
        font = QtGui.QFont()
        font.setBold(True)
        font.setPointSize(9)
        painter.setFont(font)
        painter.setPen(QtGui.QColor("#d8dde5"))
        painter.drawText(badge_rect, QtCore.Qt.AlignmentFlag.AlignCenter, "C")
    painter.end()
    return result
