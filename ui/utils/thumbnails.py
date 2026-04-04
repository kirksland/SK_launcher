from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6 import QtCore, QtGui

ROOT_DIR = Path(__file__).resolve().parents[2]
BADGE_SVG_PATH = ROOT_DIR / "config" / "icons" / "cloud.svg"


def make_placeholder_pixmap(text: str, size: QtCore.QSize) -> QtGui.QPixmap:
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
    return scaled.copy(x, y, size.width(), size.height())


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
