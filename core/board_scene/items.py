from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from PySide6 import QtCore, QtGui, QtWidgets

from core.board_edit.handles import sanitize_crop


def _draw_corner_badge(painter: QtGui.QPainter, label: str, color: QtGui.QColor) -> None:
    painter.save()
    font = painter.font()
    font.setPointSize(9)
    font.setBold(True)
    painter.setFont(font)
    fm = painter.fontMetrics()
    pad_x = 6
    pad_y = 3
    text_w = fm.horizontalAdvance(label)
    text_h = fm.height()
    rect = QtCore.QRectF(8, 8, text_w + pad_x * 2, text_h + pad_y * 2)
    bg = QtGui.QColor(color)
    bg.setAlpha(min(230, bg.alpha() + 40))
    painter.setPen(QtCore.Qt.PenStyle.NoPen)
    painter.setBrush(bg)
    painter.drawRoundedRect(rect, 6, 6)
    painter.setPen(QtGui.QColor("#0f1216"))
    painter.drawText(
        rect.adjusted(pad_x, pad_y, -pad_x, -pad_y),
        QtCore.Qt.AlignmentFlag.AlignVCenter | QtCore.Qt.AlignmentFlag.AlignHCenter,
        label,
    )
    painter.restore()


def _crop_source_rect(pixmap: QtGui.QPixmap, crop_norm: tuple[float, float, float, float]) -> QtCore.QRectF:
    left, top, right, bottom = sanitize_crop(*crop_norm)
    width = float(max(1, pixmap.width()))
    height = float(max(1, pixmap.height()))
    x = width * left
    y = height * top
    w = max(1.0, width * max(0.01, 1.0 - left - right))
    h = max(1.0, height * max(0.01, 1.0 - top - bottom))
    return QtCore.QRectF(x, y, w, h)


class BoardNoteItem(QtWidgets.QGraphicsRectItem):
    def __init__(self, text: str = "", parent: Optional[QtWidgets.QGraphicsItem] = None) -> None:
        super().__init__(parent)
        self._padding = QtCore.QMarginsF(10, 8, 10, 8)
        self._bg_color = QtGui.QColor(0, 0, 0, 160)
        self._font_size = 12
        self._align = QtCore.Qt.AlignmentFlag.AlignLeft
        self._note_id = QtCore.QUuid.createUuid().toString(QtCore.QUuid.StringFormat.WithoutBraces)
        self.text_item = QtWidgets.QGraphicsTextItem(text, self)
        self.text_item.setDefaultTextColor(QtGui.QColor("#e6e6e6"))
        self.text_item.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.NoTextInteraction)
        self.setFlags(
            QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsFocusable
        )
        self.setPen(QtCore.Qt.PenStyle.NoPen)
        self.setBrush(self._bg_color)
        self._refresh_geometry()

    def _refresh_geometry(self) -> None:
        font = self.text_item.font()
        font.setPointSize(self._font_size)
        self.text_item.setFont(font)
        doc = self.text_item.document()
        option = doc.defaultTextOption()
        option.setAlignment(self._align)
        doc.setDefaultTextOption(option)
        cursor = self.text_item.textCursor()
        cursor.movePosition(QtGui.QTextCursor.MoveOperation.Start)
        cursor.clearSelection()
        self.text_item.setTextCursor(cursor)
        text_rect = self.text_item.boundingRect()
        rect = QtCore.QRectF(
            0,
            0,
            text_rect.width() + self._padding.left() + self._padding.right(),
            text_rect.height() + self._padding.top() + self._padding.bottom(),
        )
        self.setRect(rect)
        self.text_item.setPos(self._padding.left(), self._padding.top())

    def set_note_style(self, font_size: int, align: QtCore.Qt.AlignmentFlag, bg_color: QtGui.QColor) -> None:
        self._font_size = font_size
        self._align = align
        self._bg_color = bg_color
        self.setBrush(self._bg_color)
        self._refresh_geometry()

    def set_text(self, text: str) -> None:
        self.text_item.setPlainText(text)
        self._refresh_geometry()

    def note_data(self) -> dict:
        return {
            "id": self._note_id,
            "text": self.text_item.toPlainText(),
            "font_size": self._font_size,
            "align": "center" if self._align == QtCore.Qt.AlignmentFlag.AlignHCenter else "left",
            "bg": self._bg_color.name(QtGui.QColor.NameFormat.HexArgb),
            "scale": self.scale(),
        }

    def set_note_id(self, note_id: str) -> None:
        if note_id:
            self._note_id = note_id

    def note_id(self) -> str:
        return self._note_id

    def paint(
        self,
        painter: QtGui.QPainter,
        option: QtWidgets.QStyleOptionGraphicsItem,
        widget: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        painter.save()
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(self._bg_color)
        painter.drawRoundedRect(self.rect(), 8, 8)
        if option.state & QtWidgets.QStyle.StateFlag.State_Selected:
            pen = QtGui.QPen(QtGui.QColor("#c6ccd6"), 1.5, QtCore.Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 8, 8)
        painter.restore()


class BoardImageItem(QtWidgets.QGraphicsItem):
    def __init__(self, controller: Any, path: Path, parent: Optional[QtWidgets.QGraphicsItem] = None) -> None:
        super().__init__(parent)
        self._controller = controller
        self._path = path
        self._proxy_dim = 512
        self._full_dim = controller._max_display_dim
        self._quality = "proxy"
        self._proxy_pixmap = controller._get_display_pixmap(path, self._proxy_dim)
        self._full_pixmap: Optional[QtGui.QPixmap] = None
        self._pixmap = self._proxy_pixmap
        self._override_pixmap: Optional[QtGui.QPixmap] = None
        self._logical_size = controller._get_image_size(path, fallback=self._pixmap.size())
        self._base_size = QtCore.QSizeF(float(self._logical_size.width()), float(self._logical_size.height()))
        self._crop_norm = (0.0, 0.0, 0.0, 0.0)
        self._rect = QtCore.QRectF(0, 0, self._base_size.width(), self._base_size.height())
        self.setTransformOriginPoint(self._base_size.width() * 0.5, self._base_size.height() * 0.5)

    def set_quality(self, quality: str) -> None:
        if self._override_pixmap is not None:
            self._pixmap = self._override_pixmap
            self.update()
            self._quality = quality
            return
        if quality == self._quality:
            return
        if quality == "full":
            if self._full_pixmap is None:
                self._full_pixmap = self._controller._get_display_pixmap(self._path, self._full_dim)
            new_pixmap = self._full_pixmap
        else:
            new_pixmap = self._proxy_pixmap
        if new_pixmap is None or new_pixmap.isNull():
            return
        self._pixmap = new_pixmap
        self.update()
        self._quality = quality

    def set_override_pixmap(self, pixmap: Optional[QtGui.QPixmap]) -> None:
        self._override_pixmap = pixmap
        if pixmap is not None and not pixmap.isNull():
            self._pixmap = pixmap
        else:
            self._override_pixmap = None
            self._pixmap = self._proxy_pixmap
        self.update()

    def file_name(self) -> str:
        return self._path.name

    def file_path(self) -> Path:
        return self._path

    def set_file_path(self, path: Path) -> None:
        self._path = path

    def boundingRect(self) -> QtCore.QRectF:  # type: ignore[override]
        return self._rect

    def set_crop_norm(self, left: float, top: float, right: float, bottom: float) -> None:
        left, top, right, bottom = sanitize_crop(left, top, right, bottom)
        if self._crop_norm == (left, top, right, bottom):
            return
        self.prepareGeometryChange()
        self._crop_norm = (left, top, right, bottom)
        x = self._base_size.width() * left
        y = self._base_size.height() * top
        width_factor = max(0.01, 1.0 - left - right)
        height_factor = max(0.01, 1.0 - top - bottom)
        self._rect = QtCore.QRectF(x, y, self._base_size.width() * width_factor, self._base_size.height() * height_factor)
        self.update()

    def paint(
        self,
        painter: QtGui.QPainter,
        option: QtWidgets.QStyleOptionGraphicsItem,
        widget: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        if self._pixmap is None or self._pixmap.isNull():
            return
        painter.drawPixmap(self._rect, self._pixmap, _crop_source_rect(self._pixmap, self._crop_norm))
        border_pen = QtGui.QPen(QtGui.QColor(74, 163, 255, 140), 2)
        border_pen.setCosmetic(True)
        painter.setPen(border_pen)
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        painter.drawRect(self._rect.adjusted(1, 1, -1, -1))
        if option.state & QtWidgets.QStyle.StateFlag.State_Selected:
            pen = QtGui.QPen(QtGui.QColor("#c6ccd6"), 1.5, QtCore.Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            painter.drawRect(self._rect.adjusted(1, 1, -1, -1))


class BoardVideoItem(QtWidgets.QGraphicsItem):
    def __init__(self, controller: Any, path: Path, parent: Optional[QtWidgets.QGraphicsItem] = None) -> None:
        super().__init__(parent)
        self._controller = controller
        self._path = path
        self._thumb_dim = 512
        self._pixmap = controller._get_video_thumbnail(path, self._thumb_dim)
        if self._pixmap is None or self._pixmap.isNull():
            self._pixmap = controller._build_media_placeholder("VIDEO", path.name)
        self._override_pixmap: Optional[QtGui.QPixmap] = None
        self._base_size = QtCore.QSizeF(float(self._pixmap.width()), float(self._pixmap.height()))
        self._crop_norm = (0.0, 0.0, 0.0, 0.0)
        self._rect = QtCore.QRectF(0, 0, self._base_size.width(), self._base_size.height())
        self.setTransformOriginPoint(self._base_size.width() * 0.5, self._base_size.height() * 0.5)

    def file_name(self) -> str:
        return self._path.name

    def file_path(self) -> Path:
        return self._path

    def set_file_path(self, path: Path) -> None:
        self._path = path

    def boundingRect(self) -> QtCore.QRectF:  # type: ignore[override]
        return self._rect

    def set_crop_norm(self, left: float, top: float, right: float, bottom: float) -> None:
        left, top, right, bottom = sanitize_crop(left, top, right, bottom)
        if self._crop_norm == (left, top, right, bottom):
            return
        self.prepareGeometryChange()
        self._crop_norm = (left, top, right, bottom)
        x = self._base_size.width() * left
        y = self._base_size.height() * top
        width_factor = max(0.01, 1.0 - left - right)
        height_factor = max(0.01, 1.0 - top - bottom)
        self._rect = QtCore.QRectF(x, y, self._base_size.width() * width_factor, self._base_size.height() * height_factor)
        self.update()

    def paint(
        self,
        painter: QtGui.QPainter,
        option: QtWidgets.QStyleOptionGraphicsItem,
        widget: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        if self._override_pixmap is not None and not self._override_pixmap.isNull():
            painter.drawPixmap(self._rect, self._override_pixmap, _crop_source_rect(self._override_pixmap, self._crop_norm))
        else:
            if self._pixmap is None or self._pixmap.isNull():
                return
            painter.drawPixmap(self._rect, self._pixmap, _crop_source_rect(self._pixmap, self._crop_norm))
        border_pen = QtGui.QPen(QtGui.QColor(242, 193, 78, 140), 2)
        border_pen.setCosmetic(True)
        painter.setPen(border_pen)
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        painter.drawRect(self._rect.adjusted(1, 1, -1, -1))
        _draw_corner_badge(painter, "VID", QtGui.QColor(242, 193, 78, 220))
        if option.state & QtWidgets.QStyle.StateFlag.State_Selected:
            pen = QtGui.QPen(QtGui.QColor("#c6ccd6"), 1.5, QtCore.Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            painter.drawRect(self._rect.adjusted(1, 1, -1, -1))

    def set_override_pixmap(self, pixmap: Optional[QtGui.QPixmap]) -> None:
        self._override_pixmap = pixmap if pixmap is not None and not pixmap.isNull() else None
        self.update()


class BoardSequenceItem(QtWidgets.QGraphicsItem):
    def __init__(self, controller: Any, dir_path: Path, parent: Optional[QtWidgets.QGraphicsItem] = None) -> None:
        super().__init__(parent)
        self._controller = controller
        self._dir_path = dir_path
        self._thumb_dim = 512
        self._pixmap = controller._get_sequence_thumbnail(dir_path, self._thumb_dim)
        if self._pixmap is None or self._pixmap.isNull():
            self._pixmap = controller._build_media_placeholder("SEQ", dir_path.name)
        self._override_pixmap: Optional[QtGui.QPixmap] = None
        self._rect = QtCore.QRectF(0, 0, float(self._pixmap.width()), float(self._pixmap.height()))
        self.setTransformOriginPoint(self._rect.center())

    def dir_name(self) -> str:
        return self._dir_path.name

    def dir_path(self) -> Path:
        return self._dir_path

    def set_dir_path(self, path: Path) -> None:
        self._dir_path = path

    def boundingRect(self) -> QtCore.QRectF:  # type: ignore[override]
        return self._rect

    def paint(
        self,
        painter: QtGui.QPainter,
        option: QtWidgets.QStyleOptionGraphicsItem,
        widget: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        if self._override_pixmap is not None and not self._override_pixmap.isNull():
            painter.drawPixmap(self._rect, self._override_pixmap, self._override_pixmap.rect())
        else:
            if self._pixmap is None or self._pixmap.isNull():
                return
            painter.drawPixmap(self._rect, self._pixmap, self._pixmap.rect())
        border_pen = QtGui.QPen(QtGui.QColor(90, 200, 165, 160), 2)
        border_pen.setCosmetic(True)
        painter.setPen(border_pen)
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        painter.drawRect(self._rect.adjusted(1, 1, -1, -1))
        _draw_corner_badge(painter, "SEQ", QtGui.QColor(90, 200, 165, 220))
        if option.state & QtWidgets.QStyle.StateFlag.State_Selected:
            pen = QtGui.QPen(QtGui.QColor("#c6ccd6"), 1.5, QtCore.Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            painter.drawRect(self._rect.adjusted(1, 1, -1, -1))

    def set_override_pixmap(self, pixmap: Optional[QtGui.QPixmap]) -> None:
        self._override_pixmap = pixmap if pixmap is not None and not pixmap.isNull() else None
        self.update()


class BoardGroupItem(QtWidgets.QGraphicsRectItem):
    def __init__(self, color: QtGui.QColor, parent: Optional[QtWidgets.QGraphicsItem] = None) -> None:
        super().__init__(parent)
        self._color = color
        self._members: list[QtWidgets.QGraphicsItem] = []
        self._suspend_member_move = False
        self.setZValue(-10)
        self.setFlags(
            QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self._update_pen_brush()

    def _update_pen_brush(self) -> None:
        pen = QtGui.QPen(self._color)
        pen.setWidth(2)
        self.setPen(pen)
        fill = QtGui.QColor(self._color)
        fill.setAlpha(40)
        self.setBrush(fill)

    def set_color(self, color: QtGui.QColor) -> None:
        self._color = color
        self._update_pen_brush()

    def color_hex(self) -> str:
        return self._color.name(QtGui.QColor.NameFormat.HexArgb)

    def members(self) -> list[QtWidgets.QGraphicsItem]:
        return list(self._members)

    def add_member(self, item: QtWidgets.QGraphicsItem) -> None:
        if item not in self._members:
            self._members.append(item)
        self.update_bounds()

    def remove_member(self, item: QtWidgets.QGraphicsItem) -> None:
        if item in self._members:
            self._members.remove(item)
        self.update_bounds()

    def update_bounds(self) -> None:
        valid = [m for m in self._members if m.scene() is not None]
        self._members = valid
        if not self._members:
            return
        bounds = QtCore.QRectF()
        for item in self._members:
            bounds = bounds.united(item.sceneBoundingRect())
        margin = 40.0
        bounds = bounds.adjusted(-margin, -margin, margin, margin)
        self._suspend_member_move = True
        self.setRect(0, 0, bounds.width(), bounds.height())
        self.setPos(bounds.topLeft())
        self._suspend_member_move = False

    def contains_scene_point(self, point: QtCore.QPointF) -> bool:
        return self.mapToScene(self.rect()).boundingRect().contains(point)

    def itemChange(self, change: QtWidgets.QGraphicsItem.GraphicsItemChange, value):  # type: ignore[override]
        if change == QtWidgets.QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            if self._suspend_member_move:
                return value
            delta = value - self.pos()
            for item in self._members:
                if item.scene() is None:
                    continue
                item.setPos(item.pos() + delta)
            return value
        return super().itemChange(change, value)

    def paint(
        self,
        painter: QtGui.QPainter,
        option: QtWidgets.QStyleOptionGraphicsItem,
        widget: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        painter.save()
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        painter.setPen(self.pen())
        painter.setBrush(self.brush())
        painter.drawRoundedRect(self.rect(), 12, 12)
        painter.restore()
