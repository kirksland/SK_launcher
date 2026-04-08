from __future__ import annotations

import json
import time
import uuid
import shutil
import urllib.request
from collections import deque
from pathlib import Path
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets
from video.player import VideoController, VideoPreviewLabel

try:
    import cv2  # type: ignore
except Exception:  # pragma: no cover - optional video backend
    cv2 = None  # type: ignore

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}


class _PopupOutsideCloseFilter(QtCore.QObject):
    def __init__(self, dialog: QtWidgets.QDialog, on_close) -> None:
        super().__init__(dialog)
        self._dialog = dialog
        self._on_close = on_close
        self.block_outside_close = False

    def eventFilter(self, watched: QtCore.QObject, event: QtCore.QEvent) -> bool:  # type: ignore[override]
        if self._dialog is None or not self._dialog.isVisible():
            return False
        if self.block_outside_close:
            return False
        if event.type() == QtCore.QEvent.Type.MouseButtonPress:
            try:
                mouse_event = event  # type: ignore[assignment]
                global_pos = mouse_event.globalPosition().toPoint()  # type: ignore[attr-defined]
            except Exception:
                return False
            if not self._dialog.geometry().contains(global_pos):
                self._on_close()
                self._dialog.close()
                return True
        return False


class _NoteTextEditor(QtWidgets.QGraphicsView):
    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.setRenderHints(
            QtGui.QPainter.RenderHint.Antialiasing
            | QtGui.QPainter.RenderHint.TextAntialiasing
        )
        self.setFrameStyle(QtWidgets.QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setBackgroundBrush(QtGui.QColor("#1f2329"))
        self.setStyleSheet("border: 1px solid #14171c;")
        self._scene = QtWidgets.QGraphicsScene(self)
        self.setScene(self._scene)
        self._text_item = QtWidgets.QGraphicsTextItem()
        self._text_item.setDefaultTextColor(QtGui.QColor("#e6e6e6"))
        self._text_item.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextEditorInteraction)
        self._scene.addItem(self._text_item)
        self._padding = 8
        self._highlighter = _NoUnderlineHighlighter(self._text_item.document())
        self._disable_spellcheck(self._text_item.document())

    def set_text(self, text: str) -> None:
        self._text_item.setPlainText(text)
        self._refresh_layout()

    def text(self) -> str:
        return self._text_item.toPlainText()

    def _refresh_layout(self) -> None:
        w = max(40.0, self.viewport().width() - self._padding * 2)
        self._text_item.setTextWidth(w)
        self._text_item.setPos(self._padding, self._padding)
        self._scene.setSceneRect(self.viewport().rect())

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._refresh_layout()

    def focusInEvent(self, event: QtGui.QFocusEvent) -> None:  # type: ignore[override]
        super().focusInEvent(event)
        self._scene.setFocusItem(self._text_item)

    @staticmethod
    def _disable_spellcheck(document: QtGui.QTextDocument) -> None:
        try:
            option = document.defaultTextOption()
            flag = getattr(QtGui.QTextOption.Flag, "NoTextCheck", None)
            if flag is not None:
                option.setFlags(option.flags() | flag)
                document.setDefaultTextOption(option)
        except Exception:
            pass


class _NoUnderlineHighlighter(QtGui.QSyntaxHighlighter):
    def highlightBlock(self, text: str) -> None:  # type: ignore[override]
        if not text:
            return
        fmt = QtGui.QTextCharFormat()
        fmt.setUnderlineStyle(QtGui.QTextCharFormat.UnderlineStyle.NoUnderline)
        self.setFormat(0, len(text), fmt)


class BoardNoteItem(QtWidgets.QGraphicsRectItem):
    def __init__(self, text: str = "", parent: Optional[QtWidgets.QGraphicsItem] = None) -> None:
        super().__init__(parent)
        self._padding = QtCore.QMarginsF(10, 8, 10, 8)
        self._bg_color = QtGui.QColor(0, 0, 0, 160)
        self._font_size = 12
        self._align = QtCore.Qt.AlignmentFlag.AlignLeft
        self._note_id = uuid.uuid4().hex
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
    def __init__(
        self,
        controller: "BoardController",
        path: Path,
        parent: Optional[QtWidgets.QGraphicsItem] = None,
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._path = path
        self._proxy_dim = 512
        self._full_dim = controller._max_display_dim
        self._quality = "proxy"
        self._proxy_pixmap = controller._get_display_pixmap(path, self._proxy_dim)
        self._full_pixmap: Optional[QtGui.QPixmap] = None
        self._pixmap = self._proxy_pixmap
        self._logical_size = controller._get_image_size(path, fallback=self._pixmap.size())
        self._rect = QtCore.QRectF(0, 0, float(self._logical_size.width()), float(self._logical_size.height()))
        self.setTransformOriginPoint(self._rect.center())

    def set_quality(self, quality: str) -> None:
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

    def file_name(self) -> str:
        return self._path.name

    def boundingRect(self) -> QtCore.QRectF:  # type: ignore[override]
        return self._rect

    def paint(
        self,
        painter: QtGui.QPainter,
        option: QtWidgets.QStyleOptionGraphicsItem,
        widget: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        if self._pixmap is None or self._pixmap.isNull():
            return
        painter.drawPixmap(self._rect, self._pixmap, self._pixmap.rect())
        if option.state & QtWidgets.QStyle.StateFlag.State_Selected:
            pen = QtGui.QPen(QtGui.QColor("#c6ccd6"), 1.5, QtCore.Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            painter.drawRect(self._rect.adjusted(1, 1, -1, -1))


class BoardVideoItem(QtWidgets.QGraphicsItem):
    def __init__(
        self,
        controller: "BoardController",
        path: Path,
        parent: Optional[QtWidgets.QGraphicsItem] = None,
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._path = path
        self._thumb_dim = 512
        self._pixmap = controller._get_video_thumbnail(path, self._thumb_dim)
        if self._pixmap is None or self._pixmap.isNull():
            self._pixmap = controller._build_media_placeholder("VIDEO", path.name)
        self._rect = QtCore.QRectF(0, 0, float(self._pixmap.width()), float(self._pixmap.height()))
        self.setTransformOriginPoint(self._rect.center())

    def file_name(self) -> str:
        return self._path.name

    def boundingRect(self) -> QtCore.QRectF:  # type: ignore[override]
        return self._rect

    def paint(
        self,
        painter: QtGui.QPainter,
        option: QtWidgets.QStyleOptionGraphicsItem,
        widget: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        if self._pixmap is None or self._pixmap.isNull():
            return
        painter.drawPixmap(self._rect, self._pixmap, self._pixmap.rect())
        if option.state & QtWidgets.QStyle.StateFlag.State_Selected:
            pen = QtGui.QPen(QtGui.QColor("#c6ccd6"), 1.5, QtCore.Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            painter.drawRect(self._rect.adjusted(1, 1, -1, -1))


class BoardSequenceItem(QtWidgets.QGraphicsItem):
    def __init__(
        self,
        controller: "BoardController",
        dir_path: Path,
        parent: Optional[QtWidgets.QGraphicsItem] = None,
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._dir_path = dir_path
        self._thumb_dim = 512
        self._pixmap = controller._get_sequence_thumbnail(dir_path, self._thumb_dim)
        if self._pixmap is None or self._pixmap.isNull():
            self._pixmap = controller._build_media_placeholder("SEQ", dir_path.name)
        self._rect = QtCore.QRectF(0, 0, float(self._pixmap.width()), float(self._pixmap.height()))
        self.setTransformOriginPoint(self._rect.center())

    def dir_name(self) -> str:
        return self._dir_path.name

    def dir_path(self) -> Path:
        return self._dir_path

    def boundingRect(self) -> QtCore.QRectF:  # type: ignore[override]
        return self._rect

    def paint(
        self,
        painter: QtGui.QPainter,
        option: QtWidgets.QStyleOptionGraphicsItem,
        widget: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        if self._pixmap is None or self._pixmap.isNull():
            return
        painter.drawPixmap(self._rect, self._pixmap, self._pixmap.rect())
        if option.state & QtWidgets.QStyle.StateFlag.State_Selected:
            pen = QtGui.QPen(QtGui.QColor("#c6ccd6"), 1.5, QtCore.Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            painter.drawRect(self._rect.adjusted(1, 1, -1, -1))


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


class _SequencePlayerDialog(QtWidgets.QDialog):
    def __init__(self, dir_path: Path, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Sequence: {dir_path.name}")
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.resize(860, 540)
        self._dir_path = dir_path
        self._frames = self._collect_frames(dir_path)
        self._frame_index = 0
        self._playing = False
        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._advance)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        self._status = QtWidgets.QLabel("")
        self._status.setStyleSheet("color: #9aa3ad;")
        layout.addWidget(self._status, 0)

        self._preview = VideoPreviewLabel()
        self._preview.setStyleSheet("color: #9aa3ad;")
        layout.addWidget(self._preview, 1)

        controls = QtWidgets.QHBoxLayout()
        layout.addLayout(controls, 0)

        self._play_btn = QtWidgets.QPushButton("Play")
        controls.addWidget(self._play_btn, 0)
        self._play_btn.clicked.connect(self._toggle_play)

        self._slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self._slider.setRange(0, max(0, len(self._frames) - 1))
        self._slider.valueChanged.connect(self._on_slider)
        controls.addWidget(self._slider, 1)

        fps_label = QtWidgets.QLabel("FPS")
        controls.addWidget(fps_label, 0)
        self._fps_spin = QtWidgets.QSpinBox()
        self._fps_spin.setRange(1, 60)
        self._fps_spin.setValue(24)
        self._fps_spin.valueChanged.connect(self._on_fps_changed)
        controls.addWidget(self._fps_spin, 0)

        if not self._frames:
            self._status.setText("No frames found in directory.")
        else:
            self._status.setText(f"{len(self._frames)} frames")
            self._show_frame(0)

    @staticmethod
    def _collect_frames(dir_path: Path) -> list[Path]:
        if not dir_path.exists() or not dir_path.is_dir():
            return []
        frames = [p for p in dir_path.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTS]
        return sorted(frames, key=lambda p: p.name)

    def _on_slider(self, value: int) -> None:
        self._frame_index = value
        self._show_frame(value)

    def _toggle_play(self) -> None:
        if not self._frames:
            return
        if self._playing:
            self._timer.stop()
            self._playing = False
            self._play_btn.setText("Play")
        else:
            interval = int(1000 / max(1, self._fps_spin.value()))
            self._timer.start(max(interval, 1))
            self._playing = True
            self._play_btn.setText("Pause")

    def _on_fps_changed(self) -> None:
        if self._playing:
            interval = int(1000 / max(1, self._fps_spin.value()))
            self._timer.start(max(interval, 1))

    def _advance(self) -> None:
        if not self._frames:
            return
        self._frame_index = (self._frame_index + 1) % len(self._frames)
        self._slider.blockSignals(True)
        self._slider.setValue(self._frame_index)
        self._slider.blockSignals(False)
        self._show_frame(self._frame_index)

    def _show_frame(self, index: int) -> None:
        if not self._frames:
            return
        if index < 0 or index >= len(self._frames):
            return
        path = self._frames[index]
        pixmap = QtGui.QPixmap(str(path))
        if pixmap.isNull():
            return
        max_dim = 1920
        if pixmap.width() > max_dim or pixmap.height() > max_dim:
            pixmap = pixmap.scaled(
                max_dim,
                max_dim,
                QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                QtCore.Qt.TransformationMode.SmoothTransformation,
            )
        self._preview.set_base_pixmap(pixmap)
        self._status.setText(f"{path.name} ({index + 1}/{len(self._frames)})")


class BoardController:
    def __init__(self, window: QtWidgets.QMainWindow) -> None:
        self.w = window
        self._project_root: Optional[Path] = None
        self._dirty = False
        self._loading = False
        self._saving = False
        self._last_save_ts = 0.0
        self._pixmap_cache: dict[tuple[Path, int], tuple[float, QtGui.QPixmap]] = {}
        self._video_thumb_cache: dict[tuple[Path, int], tuple[float, QtGui.QPixmap]] = {}
        self._sequence_thumb_cache: dict[tuple[Path, int], tuple[float, QtGui.QPixmap]] = {}
        self._max_display_dim = 2048
        self._low_quality = False
        self._visible_images: set[int] = set()
        self._history: list[str] = []
        self._history_index = -1
        self._history_timer: Optional[QtCore.QTimer] = None
        self._group_tree_timer: Optional[QtCore.QTimer] = None
        self._group_tree_refs: dict[int, BoardGroupItem] = {}
        self._syncing_tree_selection = False
        self._apply_timer: Optional[QtCore.QTimer] = None
        self._apply_queue: deque[dict] = deque()
        self._apply_pending_groups: list[dict] = []
        self._apply_image_map: dict[str, QtWidgets.QGraphicsPixmapItem] = {}
        self._apply_video_map: dict[str, QtWidgets.QGraphicsItem] = {}
        self._apply_sequence_map: dict[str, QtWidgets.QGraphicsItem] = {}
        self._apply_note_map: dict[str, BoardNoteItem] = {}
        self._apply_payload_ref: Optional[dict] = None
        self._apply_phase = "idle"
        self._apply_base_label: Optional[str] = None
        self._scene = self.w.board_page.scene
        self._scene.changed.connect(self._on_scene_changed)
        self._scene.selectionChanged.connect(self._on_scene_selection_changed)
        self.w.board_page.groups_tree.itemClicked.connect(self._on_group_tree_clicked)

    def set_project(self, project_root: Optional[Path]) -> None:
        if project_root is None and self._project_root is not None:
            now = time.time()
            if now - self._last_save_ts < 1.0:
                return
        if self._project_root and self._dirty:
            self.save_board()
        self._project_root = project_root
        enabled = project_root is not None
        self.w.board_add_image_btn.setEnabled(enabled)
        if hasattr(self.w, "board_add_video_btn"):
            self.w.board_add_video_btn.setEnabled(enabled)
        self.w.board_save_btn.setEnabled(enabled)
        self.w.board_load_btn.setEnabled(enabled)
        self.w.board_fit_btn.setEnabled(enabled)
        if project_root:
            base_label = f"Project: {project_root.name}"
            self._apply_base_label = base_label
            self.w.board_page.project_label.setText(f"{base_label} (loading...)")
            self._schedule_board_load()
            if self._history_index < 0:
                self._reset_history(self._build_payload())
        else:
            self.w.board_page.project_label.setText("No project selected")
            self._scene.clear()
        self._dirty = False

    def add_image(self) -> None:
        if not self._project_root:
            self._notify("Select a project first.")
            return
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self.w,
            "Add Image",
            str(self._project_root),
            "Images (*.png *.jpg *.jpeg *.bmp *.tif *.tiff)",
        )
        if not path:
            return
        src = Path(path)
        self.add_image_from_path(src)

    def add_image_from_path(
        self, src: Path, scene_pos: Optional[QtCore.QPointF] = None
    ) -> Optional[QtWidgets.QGraphicsPixmapItem]:
        if not self._project_root:
            print("[BOARD] No project root set")
            return None
        if not src.is_file():
            print(f"[BOARD] Not a file: {src}")
            return None
        assets_dir = self._project_root / ".skyforge_board_assets"
        assets_dir.mkdir(parents=True, exist_ok=True)
        dest = assets_dir / src.name
        print(f"[BOARD] Import image: {src} -> {dest}")
        if src.resolve() != dest.resolve():
            try:
                shutil.copy2(src, dest)
            except Exception as exc:
                print(f"[BOARD] Copy failed: {exc}")
                self._notify(f"Failed to copy image:\n{exc}")
                return None
        item = BoardImageItem(self, dest)
        if item.boundingRect().isNull():
            print("[BOARD] Pixmap is null")
            self._notify("Failed to load image.")
            return None
        item.setFlags(
            QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsFocusable
        )
        item.setTransformOriginPoint(item.boundingRect().center())
        item.setData(0, "image")
        item.setData(1, dest.name)
        if scene_pos is None:
            scene_pos = self._scene.sceneRect().center()
        item.setPos(scene_pos)
        logical_w = item.boundingRect().width()
        if logical_w > 600:
            scale = 600 / max(1.0, logical_w)
            item.setScale(scale)
        self._scene.addItem(item)
        self._dirty = True
        self._update_view_quality()
        self.update_visible_items()
        self._schedule_history_snapshot()
        return item

    def add_image_from_url(self, url: str, scene_pos: Optional[QtCore.QPointF] = None) -> None:
        if not self._project_root:
            self._notify("Select a project first.")
            return
        confirm = QtWidgets.QMessageBox.question(
            self.w,
            "Import Web Image",
            f"Download and import this image?\n{url}",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
        )
        if confirm != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        assets_dir = self._project_root / ".skyforge_board_assets"
        assets_dir.mkdir(parents=True, exist_ok=True)
        safe_name = QtCore.QUrl(url).fileName() or f"web_{uuid.uuid4().hex}.png"
        dest = assets_dir / safe_name
        try:
            urllib.request.urlretrieve(url, dest)
        except Exception as exc:
            self._notify(f"Failed to download image:\n{exc}")
            return
        self.add_image_from_path(dest, scene_pos=scene_pos)

    def add_image_from_image_data(self, image_data, scene_pos: Optional[QtCore.QPointF] = None) -> None:
        if not self._project_root:
            self._notify("Select a project first.")
            return
        confirm = QtWidgets.QMessageBox.question(
            self.w,
            "Import Dropped Image",
            "Import the dropped image into the board?",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
        )
        if confirm != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        image = None
        if isinstance(image_data, QtGui.QImage):
            image = image_data
        elif isinstance(image_data, QtGui.QPixmap):
            image = image_data.toImage()
        if image is None or image.isNull():
            self._notify("Dropped image data is not valid.")
            return
        assets_dir = self._project_root / ".skyforge_board_assets"
        assets_dir.mkdir(parents=True, exist_ok=True)
        dest = assets_dir / f"web_{uuid.uuid4().hex}.png"
        try:
            if not image.save(str(dest), "PNG"):
                self._notify("Failed to save dropped image.")
                return
        except Exception as exc:
            self._notify(f"Failed to save dropped image:\n{exc}")
            return
        self.add_image_from_path(dest, scene_pos=scene_pos)

    def add_video(self) -> None:
        if not self._project_root:
            self._notify("Select a project first.")
            return
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self.w,
            "Add Video",
            str(self._project_root),
            "Videos (*.mp4 *.mov *.avi *.mkv *.webm)",
        )
        if not path:
            return
        self.add_video_from_path(Path(path))

    def add_video_from_path(
        self, src: Path, scene_pos: Optional[QtCore.QPointF] = None
    ) -> Optional[QtWidgets.QGraphicsItem]:
        if not self._project_root:
            print("[BOARD] No project root set")
            return None
        if not src.is_file():
            print(f"[BOARD] Not a file: {src}")
            return None
        assets_dir = self._project_root / ".skyforge_board_assets"
        assets_dir.mkdir(parents=True, exist_ok=True)
        dest = assets_dir / src.name
        print(f"[BOARD] Import video: {src} -> {dest}")
        if src.resolve() != dest.resolve():
            try:
                shutil.copy2(src, dest)
            except Exception as exc:
                print(f"[BOARD] Copy failed: {exc}")
                self._notify(f"Failed to copy video:\n{exc}")
                return None
        item = BoardVideoItem(self, dest)
        if item.boundingRect().isNull():
            self._notify("Failed to load video thumbnail.")
            return None
        item.setFlags(
            QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsFocusable
        )
        item.setTransformOriginPoint(item.boundingRect().center())
        item.setData(0, "video")
        item.setData(1, dest.name)
        if scene_pos is None:
            scene_pos = self._scene.sceneRect().center()
        item.setPos(scene_pos)
        logical_w = item.boundingRect().width()
        if logical_w > 600:
            scale = 600 / max(1.0, logical_w)
            item.setScale(scale)
        self._scene.addItem(item)
        self._dirty = True
        self._update_view_quality()
        self._schedule_history_snapshot()
        return item

    def add_sequence(self) -> None:
        if not self._project_root:
            self._notify("Select a project first.")
            return
        dir_path = QtWidgets.QFileDialog.getExistingDirectory(
            self.w,
            "Add Image Sequence",
            str(self._project_root),
        )
        if not dir_path:
            return
        self.add_sequence_from_dir(Path(dir_path))

    def add_sequence_from_dir(
        self, dir_path: Path, scene_pos: Optional[QtCore.QPointF] = None
    ) -> Optional[QtWidgets.QGraphicsItem]:
        if not self._project_root:
            print("[BOARD] No project root set")
            return None
        if not dir_path.exists() or not dir_path.is_dir():
            print(f"[BOARD] Not a directory: {dir_path}")
            return None
        frames = self._sequence_frame_paths(dir_path)
        if not frames:
            self._notify("No image frames found in directory.")
            return None
        item = BoardSequenceItem(self, dir_path)
        if item.boundingRect().isNull():
            self._notify("Failed to load sequence thumbnail.")
            return None
        item.setFlags(
            QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsFocusable
        )
        item.setTransformOriginPoint(item.boundingRect().center())
        item.setData(0, "sequence")
        item.setData(1, self._relative_to_project(dir_path))
        if scene_pos is None:
            scene_pos = self._scene.sceneRect().center()
        item.setPos(scene_pos)
        logical_w = item.boundingRect().width()
        if logical_w > 600:
            scale = 600 / max(1.0, logical_w)
            item.setScale(scale)
        self._scene.addItem(item)
        self._dirty = True
        self._update_view_quality()
        self._schedule_history_snapshot()
        return item

    def convert_video_to_sequence(self, item: QtWidgets.QGraphicsItem) -> None:
        if item.data(0) != "video":
            return
        if cv2 is None:
            self._notify("OpenCV not available for video conversion.")
            return
        if not self._project_root:
            self._notify("Select a project first.")
            return
        filename = str(item.data(1))
        video_path = self._project_root / ".skyforge_board_assets" / filename
        if not video_path.exists():
            self._notify("Video file not found.")
            return
        out_dir = self._project_root / ".skyforge_board_assets" / f"{video_path.stem}_seq"
        out_dir.mkdir(parents=True, exist_ok=True)
        self._notify("Converting video to sequence...")
        if not self._extract_video_frames(video_path, out_dir):
            self._notify("Failed to convert video to sequence.")
            return
        scene_pos = item.pos()
        scale = item.scale()
        group = self._find_group_for_item(item)
        self._scene.removeItem(item)
        seq_item = self.add_sequence_from_dir(out_dir, scene_pos=scene_pos)
        if seq_item is not None:
            seq_item.setScale(scale)
            if group is not None:
                group.add_member(seq_item)
                group.update_bounds()
        self._dirty = True
        self._schedule_history_snapshot()

    def _extract_video_frames(self, video_path: Path, out_dir: Path) -> bool:
        try:
            cap = cv2.VideoCapture(str(video_path))
            if not cap.isOpened():
                cap.release()
                return False
            idx = 0
            stem = video_path.stem
            while True:
                ok, frame = cap.read()
                if not ok or frame is None:
                    break
                frame_name = f"{stem}_{idx:04d}.png"
                frame_path = out_dir / frame_name
                cv2.imwrite(str(frame_path), frame)
                idx += 1
            cap.release()
            return idx > 0
        except Exception:
            return False

    def add_note(self) -> None:
        self.add_note_at(None)

    def add_note_at(self, scene_pos: Optional[QtCore.QPointF]) -> None:
        if not self._project_root:
            self._notify("Select a project first.")
            return
        item = BoardNoteItem("New note...")
        item.setData(0, "note")
        if scene_pos is None:
            scene_pos = self._scene.sceneRect().center()
        item.setPos(scene_pos)
        item.setSelected(True)
        self._scene.addItem(item)
        self._dirty = True
        self.edit_note(item)

    def add_group(self) -> None:
        items = [
            i
            for i in self._scene.selectedItems()
            if isinstance(i, (BoardImageItem, BoardNoteItem, BoardVideoItem, BoardSequenceItem))
        ]
        if not items:
            self._notify("Select items to group.")
            return
        color = QtWidgets.QColorDialog.getColor(QtGui.QColor("#4aa3ff"), self.w, "Group color")
        if not color.isValid():
            return
        group = BoardGroupItem(color)
        group.setData(0, "group")
        self._scene.addItem(group)
        for item in items:
            group.add_member(item)
        group.update_bounds()
        self._dirty = True

    def ungroup_selected(self) -> None:
        groups = [i for i in self._scene.selectedItems() if isinstance(i, BoardGroupItem)]
        if not groups:
            print("[BOARD][UNGROUP] No group selected")
            self._notify("Select a group to ungroup.")
            return
        print(f"[BOARD][UNGROUP] Ungroup {len(groups)} group(s)")
        for group in groups:
            print(f"[BOARD][UNGROUP] Group members: {len(group.members())}")
            for member in group.members():
                member.setSelected(True)
            self._scene.removeItem(group)
        self._dirty = True

    def try_add_item_to_group(
        self, item: QtWidgets.QGraphicsItem, scene_pos: Optional[QtCore.QPointF]
    ) -> None:
        if scene_pos is None:
            scene_pos = item.sceneBoundingRect().center()
        for group in self._groups():
            if group.contains_scene_point(scene_pos):
                group.add_member(item)
                group.update_bounds()
                self._dirty = True
                self._schedule_history_snapshot()
                return

    def handle_item_drop(self, items: list[QtWidgets.QGraphicsItem]) -> None:
        moved = [i for i in items if isinstance(i, (BoardImageItem, BoardNoteItem, BoardVideoItem, BoardSequenceItem))]
        if not moved:
            return
        groups = self._groups()
        if not groups:
            return
        for item in moved:
            center = item.sceneBoundingRect().center()
            target_group = None
            for group in groups:
                if group.contains_scene_point(center):
                    target_group = group
                    break
            current_group = self._find_group_for_item(item)
            if target_group is not None and target_group is not current_group:
                if current_group is not None:
                    current_group.remove_member(item)
                target_group.add_member(item)
            elif target_group is None and current_group is not None:
                if not current_group.contains_scene_point(center):
                    current_group.remove_member(item)
            elif target_group is not None and current_group is None:
                target_group.add_member(item)
            if current_group is not None:
                current_group.update_bounds()
            if target_group is not None:
                target_group.update_bounds()
        self._dirty = True
        self._schedule_history_snapshot()

    def remove_selected_from_groups(self) -> None:
        removed = False
        for item in self._scene.selectedItems():
            group = self._find_group_for_item(item)
            if group is not None:
                group.remove_member(item)
                group.update_bounds()
                removed = True
        if removed:
            self._dirty = True
            self._schedule_history_snapshot()

    def add_selected_to_group(self, group_key: int) -> None:
        group = self._group_tree_refs.get(int(group_key))
        if group is None:
            return
        for item in self._scene.selectedItems():
            if item is group:
                continue
            if item.data(0) in ("image", "note", "video", "sequence"):
                group.add_member(item)
        group.update_bounds()
        self._dirty = True
        self._schedule_history_snapshot()

    def select_group_members(self, group_item: BoardGroupItem) -> None:
        for item in self._scene.selectedItems():
            item.setSelected(False)
        for member in group_item.members():
            member.setSelected(True)

    def _groups(self) -> list[BoardGroupItem]:
        return [i for i in self._scene.items() if isinstance(i, BoardGroupItem)]

    def _find_group_for_item(self, item: QtWidgets.QGraphicsItem) -> Optional[BoardGroupItem]:
        for group in self._groups():
            if item in group.members():
                return group
        return None

    def fit_view(self) -> None:
        rect = self._scene.itemsBoundingRect()
        if rect.isNull():
            return
        self.w.board_page.view.fitInView(rect.adjusted(-80, -80, 80, 80), QtCore.Qt.AspectRatioMode.KeepAspectRatio)

    def layout_selection_grid(self) -> None:
        items = [i for i in self._scene.selectedItems() if isinstance(i, QtWidgets.QGraphicsItem)]
        if not items:
            items = [
                i
                for i in self._scene.items()
                if isinstance(i, (BoardImageItem, BoardVideoItem, BoardSequenceItem))
            ]
        if not items:
            self._notify("Select items to layout.")
            return

        # Treat grouped items as a single block to avoid breaking group layout.
        grouped: list[QtWidgets.QGraphicsItem] = []
        seen_groups: set[int] = set()
        for item in items:
            group = self._find_group_for_item(item)
            if group is not None:
                if id(group) not in seen_groups:
                    grouped.append(group)
                    seen_groups.add(id(group))
            else:
                grouped.append(item)
        items = grouped

        spacing = 12.0
        bounds = QtCore.QRectF()
        for item in items:
            bounds = bounds.united(item.sceneBoundingRect())
        target_width = max(600.0, bounds.width())

        widths = sorted([i.sceneBoundingRect().width() for i in items])
        median_w = widths[len(widths) // 2] if widths else 200.0
        cols = max(2, int((target_width + spacing) / max(1.0, median_w + spacing)))

        col_width = (target_width - spacing * (cols - 1)) / max(1, cols)
        col_heights = [bounds.top() for _ in range(cols)]
        col_x = [bounds.left() + c * (col_width + spacing) for c in range(cols)]

        items_sorted = sorted(items, key=lambda i: i.sceneBoundingRect().height(), reverse=True)

        for item in items_sorted:
            rect = item.sceneBoundingRect()
            if rect.width() > 0 and not isinstance(item, BoardGroupItem):
                scale_factor = col_width / rect.width()
                item.setScale(item.scale() * scale_factor)
                rect = item.sceneBoundingRect()
            col_idx = min(range(cols), key=lambda i: col_heights[i])
            x = col_x[col_idx]
            y = col_heights[col_idx]
            item.setPos(item.pos() + QtCore.QPointF(x - rect.left(), y - rect.top()))
            col_heights[col_idx] = y + rect.height() + spacing

    def save_board(self) -> None:
        if not self._project_root:
            return
        board_path = self._project_root / ".skyforge_board.json"
        data = self._build_payload()
        try:
            self._saving = True
            self._last_save_ts = time.time()
            board_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            self._dirty = False
        except Exception as exc:
            self._notify(f"Failed to save board:\n{exc}")
        finally:
            QtCore.QTimer.singleShot(100, self._clear_saving)

    def _clear_saving(self) -> None:
        self._saving = False

    def load_board(self) -> None:
        if not self._project_root:
            return
        board_path = self._project_root / ".skyforge_board.json"
        if self._saving:
            return
        print(f"[BOARD] Load board: {board_path}")
        self._loading = True
        if not board_path.exists():
            self._start_apply_payload({"items": []})
            return
        try:
            payload = json.loads(board_path.read_text(encoding="utf-8"))
        except Exception:
            return
        self._start_apply_payload(payload)

    def _schedule_board_load(self) -> None:
        # Defer heavy loading to keep UI responsive on click.
        QtCore.QTimer.singleShot(40, self.load_board)

    def _start_apply_payload(self, payload: dict) -> None:
        if self._apply_timer is not None and self._apply_timer.isActive():
            self._apply_timer.stop()
        self._scene.blockSignals(True)
        self._scene.clear()
        self._apply_queue.clear()
        self._apply_pending_groups = []
        self._apply_image_map = {}
        self._apply_video_map = {}
        self._apply_sequence_map = {}
        self._apply_note_map = {}
        self._apply_payload_ref = payload
        notes: list[dict] = []
        images: list[dict] = []
        videos: list[dict] = []
        sequences: list[dict] = []
        groups: list[dict] = []
        for entry in payload.get("items", []):
            if isinstance(entry, dict):
                kind = entry.get("type")
                if kind == "note":
                    notes.append(entry)
                elif kind == "image":
                    images.append(entry)
                elif kind == "video":
                    videos.append(entry)
                elif kind == "sequence":
                    sequences.append(entry)
                elif kind == "group":
                    groups.append(entry)
        for entry in notes:
            self._apply_queue.append(entry)
        for entry in images:
            self._apply_queue.append(entry)
        for entry in videos:
            self._apply_queue.append(entry)
        for entry in sequences:
            self._apply_queue.append(entry)
        self._apply_pending_groups = groups
        self._apply_phase = "items"
        if self._apply_timer is None:
            self._apply_timer = QtCore.QTimer(self.w)
            self._apply_timer.setSingleShot(True)
            self._apply_timer.timeout.connect(self._apply_payload_batch)
        print(f"[BOARD] Apply payload start: {len(self._apply_queue)} items")
        self._apply_timer.start(0)

    def _apply_payload_batch(self) -> None:
        batch_size = 20
        count = 0
        assets_dir = self._project_root / ".skyforge_board_assets" if self._project_root else None
        while self._apply_queue and count < batch_size:
            entry = self._apply_queue.popleft()
            count += 1
            if entry.get("type") == "image" and assets_dir is not None:
                filename = entry.get("file", "")
                path = assets_dir / filename
                item = BoardImageItem(self, path)
                if item.boundingRect().isNull():
                    continue
                item.setFlags(
                    QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable
                    | QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
                    | QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsFocusable
                )
                item.setTransformOriginPoint(item.boundingRect().center())
                item.setData(0, "image")
                item.setData(1, filename)
                item.setPos(float(entry.get("x", 0.0)), float(entry.get("y", 0.0)))
                item.setScale(float(entry.get("scale", 1.0)))
                self._scene.addItem(item)
                if filename:
                    self._apply_image_map[str(filename)] = item
            elif entry.get("type") == "video" and assets_dir is not None:
                filename = entry.get("file", "")
                path = assets_dir / filename
                item = BoardVideoItem(self, path)
                if item.boundingRect().isNull():
                    continue
                item.setFlags(
                    QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable
                    | QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
                    | QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsFocusable
                )
                item.setTransformOriginPoint(item.boundingRect().center())
                item.setData(0, "video")
                item.setData(1, filename)
                item.setPos(float(entry.get("x", 0.0)), float(entry.get("y", 0.0)))
                item.setScale(float(entry.get("scale", 1.0)))
                self._scene.addItem(item)
                if filename:
                    self._apply_video_map[str(filename)] = item
            elif entry.get("type") == "sequence":
                dir_text = str(entry.get("dir", ""))
                dir_path = self._resolve_project_path(dir_text)
                item = BoardSequenceItem(self, dir_path)
                if item.boundingRect().isNull():
                    continue
                item.setFlags(
                    QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable
                    | QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
                    | QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsFocusable
                )
                item.setTransformOriginPoint(item.boundingRect().center())
                item.setData(0, "sequence")
                item.setData(1, dir_text)
                item.setPos(float(entry.get("x", 0.0)), float(entry.get("y", 0.0)))
                item.setScale(float(entry.get("scale", 1.0)))
                self._scene.addItem(item)
                if dir_text:
                    self._apply_sequence_map[str(dir_text)] = item
            elif entry.get("type") == "note":
                item = BoardNoteItem(entry.get("text", ""))
                align = entry.get("align", "left")
                align_flag = QtCore.Qt.AlignmentFlag.AlignHCenter if align == "center" else QtCore.Qt.AlignmentFlag.AlignLeft
                bg = entry.get("bg", "#99000000")
                item.set_note_style(int(entry.get("font_size", 12)), align_flag, QtGui.QColor(bg))
                item.setScale(float(entry.get("scale", 1.0)))
                item.setData(0, "note")
                item.setPos(float(entry.get("x", 0.0)), float(entry.get("y", 0.0)))
                note_id = entry.get("id") or uuid.uuid4().hex
                item.set_note_id(str(note_id))
                self._scene.addItem(item)
                self._apply_note_map[item.note_id()] = item
            elif entry.get("type") == "group":
                self._apply_pending_groups.append(entry)

        if self._apply_queue:
            self._apply_timer.start(10)
            return

        # Create groups after all items exist.
        for entry in self._apply_pending_groups:
            color = QtGui.QColor(entry.get("color", "#4aa3ff"))
            group = BoardGroupItem(color)
            group.setData(0, "group")
            self._scene.addItem(group)
            for ref in entry.get("members", []):
                if isinstance(ref, str):
                    item = self._apply_image_map.get(str(ref))
                    if item is not None:
                        group.add_member(item)
                    continue
                if isinstance(ref, dict):
                    r_type = ref.get("type")
                    r_id = str(ref.get("id", ""))
                    if r_type == "image":
                        item = self._apply_image_map.get(r_id)
                        if item is not None:
                            group.add_member(item)
                    elif r_type == "video":
                        item = self._apply_video_map.get(r_id)
                        if item is not None:
                            group.add_member(item)
                    elif r_type == "sequence":
                        item = self._apply_sequence_map.get(r_id)
                        if item is not None:
                            group.add_member(item)
                    elif r_type == "note":
                        item = self._apply_note_map.get(r_id)
                        if item is not None:
                            group.add_member(item)
            group.update_bounds()

        self._apply_pending_groups = []
        self._scene.blockSignals(False)
        self._dirty = False
        self._loading = False
        self._update_view_quality()
        self.update_visible_items()
        if self._apply_payload_ref is not None:
            self._reset_history(self._apply_payload_ref)
        if self._apply_base_label:
            self.w.board_page.project_label.setText(self._apply_base_label)
        QtCore.QTimer.singleShot(0, self._fit_view_after_load)

    def _fit_view_after_load(self) -> None:
        rect = self._scene.itemsBoundingRect()
        if rect.isNull():
            return
        self.fit_view()
        view = self.w.board_page.view
        zoom = view.transform().m11()
        if zoom < 0.02:
            view.resetTransform()
            view.centerOn(rect.center())

    def edit_note(self, item: BoardNoteItem, global_pos: Optional[QtCore.QPoint] = None) -> None:
        dialog = QtWidgets.QDialog(self.w)
        dialog.setWindowFlags(QtCore.Qt.WindowType.Tool | QtCore.Qt.WindowType.FramelessWindowHint)
        dialog.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose, True)
        dialog.setMinimumWidth(320)
        layout = QtWidgets.QVBoxLayout(dialog)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        text_edit = _NoteTextEditor()
        text_edit.set_text(item.text_item.toPlainText())
        text_edit.setMinimumHeight(140)
        layout.addWidget(text_edit, 1)

        options = QtWidgets.QHBoxLayout()
        layout.addLayout(options)

        size_label = QtWidgets.QLabel("Font")
        options.addWidget(size_label)
        size_spin = QtWidgets.QSpinBox()
        size_spin.setRange(8, 64)
        size_spin.setValue(item.note_data().get("font_size", 12))
        options.addWidget(size_spin)

        align_label = QtWidgets.QLabel("Align")
        options.addWidget(align_label)
        align_combo = QtWidgets.QComboBox()
        align_combo.addItems(["Left", "Center"])
        align_combo.setCurrentText("Center" if item.note_data().get("align") == "center" else "Left")
        options.addWidget(align_combo)

        color_btn = QtWidgets.QPushButton("Background")
        options.addWidget(color_btn)
        color_preview = QtWidgets.QFrame()
        color_preview.setFixedSize(24, 24)
        color_preview.setStyleSheet(f"background: {item.note_data().get('bg', '#99000000')}; border: 1px solid #333;")
        options.addWidget(color_preview)
        options.addStretch(1)

        selected_color = QtGui.QColor(item.note_data().get("bg", "#99000000"))
        applied = False

        def pick_color() -> None:
            nonlocal selected_color
            popup_filter.block_outside_close = True
            color = QtWidgets.QColorDialog.getColor(selected_color, self.w, "Pick background color")
            popup_filter.block_outside_close = False
            if color.isValid():
                selected_color = color
                color_preview.setStyleSheet(
                    f"background: {color.name(QtGui.QColor.NameFormat.HexArgb)}; border: 1px solid #333;"
                )
                preview_align = (
                    QtCore.Qt.AlignmentFlag.AlignHCenter
                    if align_combo.currentText() == "Center"
                    else QtCore.Qt.AlignmentFlag.AlignLeft
                )
                item.set_note_style(size_spin.value(), preview_align, selected_color)
                self._dirty = True

        def apply_changes() -> None:
            nonlocal applied
            if applied:
                return
            if item.scene() is None:
                return
            applied = True
            align_flag = (
                QtCore.Qt.AlignmentFlag.AlignHCenter
                if align_combo.currentText() == "Center"
                else QtCore.Qt.AlignmentFlag.AlignLeft
            )
            item.set_text(text_edit.text())
            item.set_note_style(size_spin.value(), align_flag, selected_color)
            self._dirty = True

        color_btn.clicked.connect(pick_color)
        dialog.finished.connect(lambda _result: apply_changes())

        popup_filter = _PopupOutsideCloseFilter(dialog, apply_changes)
        QtWidgets.QApplication.instance().installEventFilter(popup_filter)

        def cleanup() -> None:
            app = QtWidgets.QApplication.instance()
            if app is not None:
                app.removeEventFilter(popup_filter)

        dialog.finished.connect(lambda _result: cleanup())

        if global_pos is None:
            view = self.w.board_page.view
            scene_pos = item.sceneBoundingRect().topLeft()
            view_pos = view.mapFromScene(scene_pos)
            global_pos = view.viewport().mapToGlobal(view_pos)
        dialog.adjustSize()
        target = global_pos + QtCore.QPoint(12, 12)
        screen = QtGui.QGuiApplication.screenAt(target)
        if screen is None:
            screen = QtGui.QGuiApplication.primaryScreen()
        if screen is not None:
            geom = screen.availableGeometry()
            dlg = dialog.frameGeometry()
            x = max(geom.left() + 8, min(target.x(), geom.right() - dlg.width() - 8))
            y = max(geom.top() + 8, min(target.y(), geom.bottom() - dlg.height() - 8))
            target = QtCore.QPoint(x, y)
        dialog.move(target)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        QtCore.QTimer.singleShot(0, text_edit.setFocus)

    def open_media_item(self, item: QtWidgets.QGraphicsItem) -> None:
        kind = item.data(0)
        if kind == "video":
            if not self._project_root:
                self._notify("Select a project first.")
                return
            filename = str(item.data(1))
            path = self._project_root / ".skyforge_board_assets" / filename
            if not path.exists():
                self._notify("Video file not found.")
                return
            self._open_video_dialog(path)
        elif kind == "sequence":
            dir_text = str(item.data(1))
            dir_path = self._resolve_project_path(dir_text)
            if not dir_path.exists():
                self._notify("Sequence directory not found.")
                return
            self._open_sequence_dialog(dir_path)

    def _open_video_dialog(self, path: Path) -> None:
        dialog = QtWidgets.QDialog(self.w)
        dialog.setWindowTitle(f"Video: {path.name}")
        dialog.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose, True)
        dialog.resize(860, 540)
        layout = QtWidgets.QVBoxLayout(dialog)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        status = QtWidgets.QLabel("")
        status.setStyleSheet("color: #9aa3ad;")
        layout.addWidget(status, 0)

        preview_label = QtWidgets.QLabel(path.name)
        preview_label.setStyleSheet("color: #c6ccd6; font-weight: bold;")

        preview_widget = QtWidgets.QLabel("")
        backend_pref = getattr(self.w, "_video_backend_pref", "auto")
        controller = VideoController(
            backend_pref,
            status_label=status,
            preview_label=preview_label,
            preview_widget=preview_widget,
            parent=dialog,
        )
        dialog._video_controller = controller  # type: ignore[attr-defined]
        layout.addWidget(controller.widget, 1)

        controls = QtWidgets.QHBoxLayout()
        play_btn = QtWidgets.QPushButton("Play")
        slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        slider.setRange(0, 0)
        controls.addWidget(play_btn, 0)
        controls.addWidget(slider, 1)
        layout.addLayout(controls)

        controller.bind_controls(play_btn, slider)
        controller.play_path(path)

        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _open_sequence_dialog(self, dir_path: Path) -> None:
        dialog = _SequencePlayerDialog(dir_path, parent=self.w)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _on_scene_changed(self) -> None:
        if self._loading:
            return
        if self._saving:
            return
        for item in list(self._scene.items()):
            if isinstance(item, BoardGroupItem):
                item.update_bounds()
                if not item.members():
                    self._scene.removeItem(item)
        self._dirty = True
        self._update_view_quality()
        self._schedule_history_snapshot()
        self._schedule_group_tree_update()

    def _get_display_pixmap(self, path: Path, max_dim: Optional[int] = None) -> QtGui.QPixmap:
        try:
            mtime = path.stat().st_mtime
        except Exception:
            return QtGui.QPixmap(str(path))
        if max_dim is None:
            max_dim = self._max_display_dim
        key = (path, max_dim)
        cached = self._pixmap_cache.get(key)
        if cached and cached[0] == mtime:
            return cached[1]
        pixmap = QtGui.QPixmap(str(path))
        if not pixmap.isNull():
            if pixmap.width() > max_dim or pixmap.height() > max_dim:
                pixmap = pixmap.scaled(
                    max_dim,
                    max_dim,
                    QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                    QtCore.Qt.TransformationMode.SmoothTransformation,
                )
        self._pixmap_cache[key] = (mtime, pixmap)
        return pixmap

    def _get_image_size(self, path: Path, fallback: Optional[QtCore.QSize] = None) -> QtCore.QSize:
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

    def _build_media_placeholder(self, label: str, subtitle: str) -> QtGui.QPixmap:
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

    def _get_video_thumbnail(self, path: Path, max_dim: int) -> QtGui.QPixmap:
        try:
            mtime = path.stat().st_mtime
        except Exception:
            return self._build_media_placeholder("VIDEO", path.name)
        key = (path, max_dim)
        cached = self._video_thumb_cache.get(key)
        if cached and cached[0] == mtime:
            return cached[1]
        if cv2 is None:
            return self._build_media_placeholder("VIDEO", path.name)
        pixmap = QtGui.QPixmap()
        try:
            cap = cv2.VideoCapture(str(path))
            if not cap.isOpened():
                cap.release()
                return self._build_media_placeholder("VIDEO", path.name)
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
            pixmap = self._build_media_placeholder("VIDEO", path.name)
        else:
            if pixmap.width() > max_dim or pixmap.height() > max_dim:
                pixmap = pixmap.scaled(
                    max_dim,
                    max_dim,
                    QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                    QtCore.Qt.TransformationMode.SmoothTransformation,
                )
        self._video_thumb_cache[key] = (mtime, pixmap)
        return pixmap

    def _sequence_frame_paths(self, dir_path: Path) -> list[Path]:
        if not dir_path.exists() or not dir_path.is_dir():
            return []
        frames = [p for p in dir_path.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTS]
        return sorted(frames, key=lambda p: p.name)

    def _get_sequence_thumbnail(self, dir_path: Path, max_dim: int) -> QtGui.QPixmap:
        try:
            mtime = dir_path.stat().st_mtime
        except Exception:
            return self._build_media_placeholder("SEQ", dir_path.name)
        key = (dir_path, max_dim)
        cached = self._sequence_thumb_cache.get(key)
        if cached and cached[0] == mtime:
            return cached[1]
        frames = self._sequence_frame_paths(dir_path)
        if not frames:
            return self._build_media_placeholder("SEQ", dir_path.name)
        pixmap = self._get_display_pixmap(frames[0], max_dim)
        if pixmap.isNull():
            pixmap = self._build_media_placeholder("SEQ", dir_path.name)
        self._sequence_thumb_cache[key] = (mtime, pixmap)
        return pixmap

    def _is_video_file(self, path: Path) -> bool:
        return path.is_file() and path.suffix.lower() in VIDEO_EXTS

    def _is_image_file(self, path: Path) -> bool:
        return path.is_file() and path.suffix.lower() in IMAGE_EXTS

    def _relative_to_project(self, path: Path) -> str:
        if self._project_root is None:
            return str(path)
        try:
            return str(path.relative_to(self._project_root))
        except Exception:
            return str(path)

    def _resolve_project_path(self, path_text: str) -> Path:
        p = Path(path_text)
        if p.is_absolute() or self._project_root is None:
            return p
        return self._project_root / p

    def _update_view_quality(self) -> None:
        view = self.w.board_page.view
        item_count = sum(
            1
            for i in self._scene.items()
            if i.data(0) in ("image", "note", "video", "sequence", "group")
        )
        low_quality = item_count >= 200
        if low_quality == self._low_quality:
            return
        self._low_quality = low_quality
        if low_quality:
            view.setRenderHints(QtGui.QPainter.RenderHint.Antialiasing, False)
            view.setRenderHints(QtGui.QPainter.RenderHint.SmoothPixmapTransform, False)
            view.setRenderHints(QtGui.QPainter.RenderHint.TextAntialiasing, False)
        else:
            view.setRenderHints(
                QtGui.QPainter.RenderHint.Antialiasing
                | QtGui.QPainter.RenderHint.SmoothPixmapTransform
                | QtGui.QPainter.RenderHint.TextAntialiasing
            )

    def update_visible_items(self) -> None:
        view = self.w.board_page.view
        visible_rect = view.mapToScene(view.viewport().rect()).boundingRect().adjusted(-200, -200, 200, 200)
        zoom = view.transform().m11()
        want_full = zoom >= 0.45
        new_visible: set[int] = set()
        for item in self._scene.items(visible_rect):
            if isinstance(item, BoardImageItem):
                new_visible.add(id(item))
                item.set_quality("full" if want_full else "proxy")
        for item_id in list(self._visible_images - new_visible):
            for item in self._scene.items():
                if id(item) == item_id and isinstance(item, BoardImageItem):
                    item.set_quality("proxy")
                    break
        self._visible_images = new_visible

    def undo(self) -> None:
        if self._history_index <= 0:
            return
        self._history_index -= 1
        payload = json.loads(self._history[self._history_index])
        self._loading = True
        self._scene.blockSignals(True)
        self._scene.clear()
        self._apply_payload(payload)
        self._scene.blockSignals(False)
        self._loading = False
        self._dirty = True
        self._update_view_quality()
        self.update_visible_items()

    def redo(self) -> None:
        if self._history_index >= len(self._history) - 1:
            return
        self._history_index += 1
        payload = json.loads(self._history[self._history_index])
        self._loading = True
        self._scene.blockSignals(True)
        self._scene.clear()
        self._apply_payload(payload)
        self._scene.blockSignals(False)
        self._loading = False
        self._dirty = True
        self._update_view_quality()
        self.update_visible_items()

    def _build_payload(self) -> dict:
        data = {"items": []}
        for item in self._scene.items():
            kind = item.data(0)
            if kind == "image":
                data["items"].append({
                    "type": "image",
                    "file": str(item.data(1)),
                    "x": item.pos().x(),
                    "y": item.pos().y(),
                    "scale": item.scale(),
                })
            elif kind == "video":
                data["items"].append({
                    "type": "video",
                    "file": str(item.data(1)),
                    "x": item.pos().x(),
                    "y": item.pos().y(),
                    "scale": item.scale(),
                })
            elif kind == "sequence":
                data["items"].append({
                    "type": "sequence",
                    "dir": str(item.data(1)),
                    "x": item.pos().x(),
                    "y": item.pos().y(),
                    "scale": item.scale(),
                })
            elif kind == "note" and isinstance(item, BoardNoteItem):
                data["items"].append({
                    "type": "note",
                    **item.note_data(),
                    "x": item.pos().x(),
                    "y": item.pos().y(),
                })
            elif kind == "group" and isinstance(item, BoardGroupItem):
                members = []
                for m in item.members():
                    if m.data(0) == "image":
                        members.append({"type": "image", "id": str(m.data(1))})
                    elif m.data(0) == "video":
                        members.append({"type": "video", "id": str(m.data(1))})
                    elif m.data(0) == "sequence":
                        members.append({"type": "sequence", "id": str(m.data(1))})
                    elif m.data(0) == "note" and isinstance(m, BoardNoteItem):
                        members.append({"type": "note", "id": m.note_id()})
                if not members:
                    continue
                data["items"].append({
                    "type": "group",
                    "color": item.color_hex(),
                    "members": members,
                })
        return data

    def _apply_payload(self, payload: dict) -> None:
        assets_dir = self._project_root / ".skyforge_board_assets" if self._project_root else None
        image_map: dict[str, QtWidgets.QGraphicsPixmapItem] = {}
        video_map: dict[str, QtWidgets.QGraphicsItem] = {}
        sequence_map: dict[str, QtWidgets.QGraphicsItem] = {}
        note_map: dict[str, BoardNoteItem] = {}
        pending_groups = []
        for entry in payload.get("items", []):
            if entry.get("type") == "image" and assets_dir is not None:
                filename = entry.get("file", "")
                path = assets_dir / filename
                item = BoardImageItem(self, path)
                if item.boundingRect().isNull():
                    continue
                item.setFlags(
                    QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable
                    | QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
                    | QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsFocusable
                )
                item.setTransformOriginPoint(item.boundingRect().center())
                item.setData(0, "image")
                item.setData(1, filename)
                item.setPos(float(entry.get("x", 0.0)), float(entry.get("y", 0.0)))
                item.setScale(float(entry.get("scale", 1.0)))
                self._scene.addItem(item)
                if filename:
                    image_map[str(filename)] = item
            elif entry.get("type") == "video" and assets_dir is not None:
                filename = entry.get("file", "")
                path = assets_dir / filename
                item = BoardVideoItem(self, path)
                if item.boundingRect().isNull():
                    continue
                item.setFlags(
                    QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable
                    | QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
                    | QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsFocusable
                )
                item.setTransformOriginPoint(item.boundingRect().center())
                item.setData(0, "video")
                item.setData(1, filename)
                item.setPos(float(entry.get("x", 0.0)), float(entry.get("y", 0.0)))
                item.setScale(float(entry.get("scale", 1.0)))
                self._scene.addItem(item)
                if filename:
                    video_map[str(filename)] = item
            elif entry.get("type") == "sequence":
                dir_text = str(entry.get("dir", ""))
                dir_path = self._resolve_project_path(dir_text)
                item = BoardSequenceItem(self, dir_path)
                if item.boundingRect().isNull():
                    continue
                item.setFlags(
                    QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable
                    | QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
                    | QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsFocusable
                )
                item.setTransformOriginPoint(item.boundingRect().center())
                item.setData(0, "sequence")
                item.setData(1, dir_text)
                item.setPos(float(entry.get("x", 0.0)), float(entry.get("y", 0.0)))
                item.setScale(float(entry.get("scale", 1.0)))
                self._scene.addItem(item)
                if dir_text:
                    sequence_map[str(dir_text)] = item
            elif entry.get("type") == "note":
                item = BoardNoteItem(entry.get("text", ""))
                align = entry.get("align", "left")
                align_flag = QtCore.Qt.AlignmentFlag.AlignHCenter if align == "center" else QtCore.Qt.AlignmentFlag.AlignLeft
                bg = entry.get("bg", "#99000000")
                item.set_note_style(int(entry.get("font_size", 12)), align_flag, QtGui.QColor(bg))
                item.setScale(float(entry.get("scale", 1.0)))
                item.setData(0, "note")
                item.setPos(float(entry.get("x", 0.0)), float(entry.get("y", 0.0)))
                note_id = entry.get("id") or uuid.uuid4().hex
                item.set_note_id(str(note_id))
                self._scene.addItem(item)
                note_map[item.note_id()] = item
            elif entry.get("type") == "group":
                pending_groups.append(entry)
        for entry in pending_groups:
            color = QtGui.QColor(entry.get("color", "#4aa3ff"))
            group = BoardGroupItem(color)
            group.setData(0, "group")
            self._scene.addItem(group)
            for ref in entry.get("members", []):
                if isinstance(ref, str):
                    item = image_map.get(str(ref))
                    if item is not None:
                        group.add_member(item)
                    continue
                if isinstance(ref, dict):
                    r_type = ref.get("type")
                    r_id = str(ref.get("id", ""))
                    if r_type == "image":
                        item = image_map.get(r_id)
                        if item is not None:
                            group.add_member(item)
                    elif r_type == "video":
                        item = video_map.get(r_id)
                        if item is not None:
                            group.add_member(item)
                    elif r_type == "sequence":
                        item = sequence_map.get(r_id)
                        if item is not None:
                            group.add_member(item)
                    elif r_type == "note":
                        item = note_map.get(r_id)
                        if item is not None:
                            group.add_member(item)
            group.update_bounds()

    def _schedule_history_snapshot(self) -> None:
        if self._loading or self._saving:
            return
        if self._history_timer is not None:
            return
        self._history_timer = QtCore.QTimer(self.w)
        self._history_timer.setSingleShot(True)
        self._history_timer.timeout.connect(self._capture_history_snapshot)
        self._history_timer.start(250)

    def _capture_history_snapshot(self) -> None:
        self._history_timer = None
        payload = self._build_payload()
        serialized = json.dumps(payload, sort_keys=True)
        if self._history and self._history[self._history_index] == serialized:
            return
        if self._history_index < len(self._history) - 1:
            self._history = self._history[: self._history_index + 1]
        self._history.append(serialized)
        self._history_index = len(self._history) - 1

    def _reset_history(self, payload: dict) -> None:
        serialized = json.dumps(payload, sort_keys=True)
        self._history = [serialized]
        self._history_index = 0

    def _schedule_group_tree_update(self) -> None:
        if self._group_tree_timer is not None:
            return
        self._group_tree_timer = QtCore.QTimer(self.w)
        self._group_tree_timer.setSingleShot(True)
        self._group_tree_timer.timeout.connect(self._update_group_tree)
        self._group_tree_timer.start(200)

    def _update_group_tree(self) -> None:
        self._group_tree_timer = None
        tree = self.w.board_page.groups_tree
        tree.blockSignals(True)
        tree.clear()
        self._group_tree_refs = {}
        groups = self._groups()
        assets_dir = self._project_root / ".skyforge_board_assets" if self._project_root else None
        root_groups = QtWidgets.QTreeWidgetItem(["Groups"])
        root_groups.setForeground(0, QtGui.QColor("#c6ccd6"))
        tree.addTopLevelItem(root_groups)
        for idx, group in enumerate(groups, start=1):
            title = f"Group {idx}"
            top = QtWidgets.QTreeWidgetItem([title])
            top.setData(0, QtCore.Qt.ItemDataRole.UserRole, ("group", idx))
            top.setForeground(0, QtGui.QColor(group.color_hex()))
            root_groups.addChild(top)
            self._group_tree_refs[idx] = group
            for member in group.members():
                if member.data(0) == "image":
                    label = str(member.data(1))
                    child = QtWidgets.QTreeWidgetItem([label])
                    child.setData(0, QtCore.Qt.ItemDataRole.UserRole, ("image", label))
                    if assets_dir is not None and label:
                        child.setData(
                            0,
                            QtCore.Qt.ItemDataRole.UserRole + 1,
                            str(assets_dir / label),
                        )
                    top.addChild(child)
                elif member.data(0) == "video":
                    label = str(member.data(1))
                    child = QtWidgets.QTreeWidgetItem([f"Video: {label}"])
                    child.setData(0, QtCore.Qt.ItemDataRole.UserRole, ("video", label))
                    if assets_dir is not None and label:
                        child.setData(
                            0,
                            QtCore.Qt.ItemDataRole.UserRole + 1,
                            str(assets_dir / label),
                        )
                    top.addChild(child)
                elif member.data(0) == "sequence":
                    seq_key = str(member.data(1))
                    seq_path = self._resolve_project_path(seq_key)
                    child = QtWidgets.QTreeWidgetItem([f"Seq: {seq_path.name}"])
                    child.setData(0, QtCore.Qt.ItemDataRole.UserRole, ("sequence", seq_key))
                    child.setData(
                        0,
                        QtCore.Qt.ItemDataRole.UserRole + 1,
                        str(seq_path),
                    )
                    top.addChild(child)
                elif member.data(0) == "note" and isinstance(member, BoardNoteItem):
                    text = member.text_item.toPlainText().strip().replace("\n", " ")
                    label = f"Note: {text[:24] + ('…' if len(text) > 24 else '')}"
                    child = QtWidgets.QTreeWidgetItem([label])
                    child.setData(0, QtCore.Qt.ItemDataRole.UserRole, ("note", member.note_id()))
                    top.addChild(child)

        root_ungrouped = QtWidgets.QTreeWidgetItem(["Ungrouped"])
        root_ungrouped.setForeground(0, QtGui.QColor("#c6ccd6"))
        tree.addTopLevelItem(root_ungrouped)
        for item in self._scene.items():
            if item.data(0) not in ("image", "note", "video", "sequence"):
                continue
            if self._find_group_for_item(item) is not None:
                continue
            if item.data(0) == "image":
                label = str(item.data(1))
                child = QtWidgets.QTreeWidgetItem([label])
                child.setData(0, QtCore.Qt.ItemDataRole.UserRole, ("image", label))
                if assets_dir is not None and label:
                    child.setData(
                        0,
                        QtCore.Qt.ItemDataRole.UserRole + 1,
                        str(assets_dir / label),
                    )
                root_ungrouped.addChild(child)
            elif item.data(0) == "video":
                label = str(item.data(1))
                child = QtWidgets.QTreeWidgetItem([f"Video: {label}"])
                child.setData(0, QtCore.Qt.ItemDataRole.UserRole, ("video", label))
                if assets_dir is not None and label:
                    child.setData(
                        0,
                        QtCore.Qt.ItemDataRole.UserRole + 1,
                        str(assets_dir / label),
                    )
                root_ungrouped.addChild(child)
            elif item.data(0) == "sequence":
                seq_key = str(item.data(1))
                seq_path = self._resolve_project_path(seq_key)
                child = QtWidgets.QTreeWidgetItem([f"Seq: {seq_path.name}"])
                child.setData(0, QtCore.Qt.ItemDataRole.UserRole, ("sequence", seq_key))
                child.setData(
                    0,
                    QtCore.Qt.ItemDataRole.UserRole + 1,
                    str(seq_path),
                )
                root_ungrouped.addChild(child)
            elif item.data(0) == "note" and isinstance(item, BoardNoteItem):
                text = item.text_item.toPlainText().strip().replace("\n", " ")
                label = f"Note: {text[:24] + ('…' if len(text) > 24 else '')}"
                child = QtWidgets.QTreeWidgetItem([label])
                child.setData(0, QtCore.Qt.ItemDataRole.UserRole, ("note", item.note_id()))
                root_ungrouped.addChild(child)

        tree.expandAll()
        tree.blockSignals(False)
        self._sync_tree_selection_from_scene()

    def _sync_tree_selection_from_scene(self) -> None:
        if self._syncing_tree_selection:
            return
        tree = self.w.board_page.groups_tree
        selected = [i for i in self._scene.selectedItems() if i.data(0) in ("image", "note", "video", "sequence")]
        if not selected:
            tree.blockSignals(True)
            tree.clearSelection()
            tree.blockSignals(False)
            return
        item = selected[0]
        if item.data(0) == "image":
            target = ("image", str(item.data(1)))
        elif item.data(0) == "video":
            target = ("video", str(item.data(1)))
        elif item.data(0) == "sequence":
            target = ("sequence", str(item.data(1)))
        elif item.data(0) == "note" and isinstance(item, BoardNoteItem):
            target = ("note", item.note_id())
        else:
            return
        self._syncing_tree_selection = True
        try:
            it = QtWidgets.QTreeWidgetItemIterator(tree)
            while it.value():
                node = it.value()
                info = node.data(0, QtCore.Qt.ItemDataRole.UserRole)
                if info == target:
                    tree.blockSignals(True)
                    tree.setCurrentItem(node)
                    tree.scrollToItem(node)
                    tree.blockSignals(False)
                    break
                it += 1
        finally:
            self._syncing_tree_selection = False

    def _on_scene_selection_changed(self) -> None:
        if self._syncing_tree_selection:
            return
        self._sync_tree_selection_from_scene()

    def _on_group_tree_clicked(self, item: QtWidgets.QTreeWidgetItem) -> None:
        info = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if not isinstance(info, tuple):
            return
        kind = info[0]
        if kind == "group":
            group = self._group_tree_refs.get(int(info[1]))
            if group is not None:
                self.select_group_members(group)
        elif kind == "image":
            name = str(info[1])
            for it in self._scene.items():
                if it.data(0) == "image" and str(it.data(1)) == name:
                    for sel in self._scene.selectedItems():
                        sel.setSelected(False)
                    it.setSelected(True)
                    break
        elif kind == "video":
            name = str(info[1])
            for it in self._scene.items():
                if it.data(0) == "video" and str(it.data(1)) == name:
                    for sel in self._scene.selectedItems():
                        sel.setSelected(False)
                    it.setSelected(True)
                    break
        elif kind == "sequence":
            key = str(info[1])
            for it in self._scene.items():
                if it.data(0) == "sequence" and str(it.data(1)) == key:
                    for sel in self._scene.selectedItems():
                        sel.setSelected(False)
                    it.setSelected(True)
                    break
        elif kind == "note":
            note_id = str(info[1])
            for it in self._scene.items():
                if it.data(0) == "note" and isinstance(it, BoardNoteItem) and it.note_id() == note_id:
                    for sel in self._scene.selectedItems():
                        sel.setSelected(False)
                    it.setSelected(True)
                    break

    def _notify(self, text: str) -> None:
        self.w.asset_status.setText(text)
