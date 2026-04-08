from __future__ import annotations

from typing import Optional
import re
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

from video.player import VideoPreviewLabel


class _GroupsTree(QtWidgets.QTreeWidget):
    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setDragDropMode(QtWidgets.QAbstractItemView.DragDropMode.DragOnly)
        self.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)

    def mimeData(self, items: list[QtWidgets.QTreeWidgetItem]) -> QtCore.QMimeData:  # type: ignore[override]
        mime = QtCore.QMimeData()
        urls: list[QtCore.QUrl] = []
        for item in items:
            path_text = item.data(0, QtCore.Qt.ItemDataRole.UserRole + 1)
            if not path_text:
                continue
            urls.append(QtCore.QUrl.fromLocalFile(str(path_text)))
        if urls:
            mime.setUrls(urls)
            mime.setText(urls[0].toLocalFile())
        return mime

from ui.utils.styles import (
    PALETTE,
    border_only_style,
    muted_text_style,
    subtle_panel_frame_style,
    title_style,
    tree_panel_style,
    tool_button_style,
)


class BoardView(QtWidgets.QGraphicsView):
    def __init__(self, scene: QtWidgets.QGraphicsScene, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(scene, parent)
        self.setRenderHints(
            QtGui.QPainter.RenderHint.Antialiasing
            | QtGui.QPainter.RenderHint.SmoothPixmapTransform
            | QtGui.QPainter.RenderHint.TextAntialiasing
        )
        self.setViewportUpdateMode(QtWidgets.QGraphicsView.ViewportUpdateMode.SmartViewportUpdate)
        self.setDragMode(QtWidgets.QGraphicsView.DragMode.RubberBandDrag)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.setTransformationAnchor(QtWidgets.QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QtWidgets.QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setOptimizationFlag(QtWidgets.QGraphicsView.OptimizationFlag.DontSavePainterState, True)
        self.setOptimizationFlag(QtWidgets.QGraphicsView.OptimizationFlag.DontAdjustForAntialiasing, True)
        self.viewport().setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.viewport().customContextMenuRequested.connect(self._on_custom_context_menu)
        self.viewport().installEventFilter(self)
        self._panning = False
        self._pan_start = QtCore.QPoint()
        self._show_grid = True
        self._scaling = False
        self._scale_items: list[QtWidgets.QGraphicsItem] = []
        self._scale_start_values: list[float] = []
        self._scale_start_positions: list[QtCore.QPointF] = []
        self._scale_overlays: list[QtWidgets.QGraphicsRectItem] = []
        self._scale_start_center = QtCore.QPointF()
        self._scale_start_dist = 1.0
        self._scale_min_dist = 40.0
        self._scale_group_mode = False
        self._scale_start_value = 1.0
        self._move_start_positions: dict[int, QtCore.QPointF] = {}
        self._rubberband_add = False
        self._rubberband_prev: list[QtWidgets.QGraphicsItem] = []
        self._quality_timer: Optional[QtCore.QTimer] = None

    def drawBackground(self, painter: QtGui.QPainter, rect: QtCore.QRectF) -> None:
        painter.save()
        painter.fillRect(rect, QtGui.QColor("#2b2f36"))
        if self._show_grid:
            grid_size = 48
            minor = QtGui.QColor(120, 126, 138, 70)
            major = QtGui.QColor(150, 158, 170, 120)
            left = int(rect.left()) - (int(rect.left()) % grid_size)
            top = int(rect.top()) - (int(rect.top()) % grid_size)
            lines = []
            for x in range(left, int(rect.right()), grid_size):
                lines.append(QtCore.QLineF(x, rect.top(), x, rect.bottom()))
            for y in range(top, int(rect.bottom()), grid_size):
                lines.append(QtCore.QLineF(rect.left(), y, rect.right(), y))
            painter.setPen(QtGui.QPen(minor, 1))
            painter.drawLines(lines)
            painter.setPen(QtGui.QPen(major, 1))
            painter.drawLine(QtCore.QLineF(0, rect.top(), 0, rect.bottom()))
            painter.drawLine(QtCore.QLineF(rect.left(), 0, rect.right(), 0))
        painter.restore()

    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:  # type: ignore[override]
        if event.modifiers() & QtCore.Qt.KeyboardModifier.AltModifier:
            items = self.scene().selectedItems()
            if items:
                factor = 1.08 if event.angleDelta().y() > 0 else 0.92
                for item in items:
                    item.setScale(max(0.05, min(8.0, item.scale() * factor)))
                event.accept()
                self._schedule_quality_update()
                return
        factor = 1.2 if event.angleDelta().y() > 0 else 0.85
        self.scale(factor, factor)
        self._schedule_quality_update()

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:  # type: ignore[override]
        if event.button() == QtCore.Qt.MouseButton.LeftButton and event.modifiers() & QtCore.Qt.KeyboardModifier.ShiftModifier:
            item = self.itemAt(event.pos())
            if item is not None:
                item.setSelected(True)
                event.accept()
                return
            self._rubberband_add = True
            self._rubberband_prev = list(self.scene().selectedItems())
        if event.button() == QtCore.Qt.MouseButton.RightButton:
            self._show_context_menu(event.pos(), self.viewport().mapToGlobal(event.pos()))
            event.accept()
            return
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self._move_start_positions = {id(i): i.pos() for i in self.scene().selectedItems()}
        if event.button() == QtCore.Qt.MouseButton.LeftButton and event.modifiers() & QtCore.Qt.KeyboardModifier.ControlModifier:
            items = [i for i in self.scene().selectedItems() if i.data(0) in ("image", "note", "video", "sequence")]
            if items:
                self._begin_scale(event, items)
                event.accept()
                return
        if event.button() == QtCore.Qt.MouseButton.MiddleButton:
            self._panning = True
            self._pan_start = event.pos()
            self.setDragMode(QtWidgets.QGraphicsView.DragMode.NoDrag)
            self.setCursor(QtCore.Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:  # type: ignore[override]
        if getattr(self, "_scaling", False):
            self._update_scale(event)
            event.accept()
            return
        if self._panning:
            delta = event.pos() - self._pan_start
            self._pan_start = event.pos()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            event.accept()
            self._schedule_quality_update()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:  # type: ignore[override]
        if getattr(self, "_scaling", False) and event.button() == QtCore.Qt.MouseButton.LeftButton:
            self._scaling = False
            for overlay in self._scale_overlays:
                self.scene().removeItem(overlay)
            self._scale_overlays = []
            self._scale_items = []
            self._scale_start_values = []
            self._scale_start_positions = []
            event.accept()
            self._schedule_quality_update()
            return
        if self._panning and event.button() in (
            QtCore.Qt.MouseButton.MiddleButton,
            QtCore.Qt.MouseButton.LeftButton,
        ):
            self._panning = False
            self.setDragMode(QtWidgets.QGraphicsView.DragMode.RubberBandDrag)
            self.setCursor(QtCore.Qt.CursorShape.ArrowCursor)
            event.accept()
            self._schedule_quality_update()
            return
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            if self._rubberband_add:
                for item in self._rubberband_prev:
                    item.setSelected(True)
                self._rubberband_add = False
                self._rubberband_prev = []
            moved = []
            for item in self.scene().selectedItems():
                start = self._move_start_positions.get(id(item))
                if start is not None and (item.pos() - start).manhattanLength() > 2:
                    moved.append(item)
            if moved:
                controller = self._resolve_controller()
                if controller is not None and hasattr(controller, "handle_item_drop"):
                    controller.handle_item_drop(moved)
            self._schedule_quality_update()
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QtGui.QMouseEvent) -> None:  # type: ignore[override]
        scene_pos = self.mapToScene(event.pos())
        items_at = self.scene().items(scene_pos)
        item = items_at[0] if items_at else None
        note_item = None
        group_item = None
        media_item = None
        while item is not None:
            if item.data(0) in ("video", "sequence"):
                media_item = item
                break
            if item.data(0) == "image":
                media_item = item
                break
            if item.data(0) == "note":
                note_item = item
                break
            if item.data(0) == "group":
                group_item = item
                break
            item = item.parentItem()
        if group_item is not None:
            controller = self._resolve_controller()
            if controller is not None and hasattr(controller, "select_group_members"):
                controller.select_group_members(group_item)
                event.accept()
                return
        if media_item is not None:
            controller = self._resolve_controller()
            if controller is not None:
                if media_item.data(0) == "image" and hasattr(controller, "open_image_item"):
                    controller.open_image_item(media_item)
                    event.accept()
                    return
                if hasattr(controller, "open_media_item"):
                    controller.open_media_item(media_item)
                    event.accept()
                    return
        if note_item is not None:
            controller = self._resolve_controller()
            if controller is not None and hasattr(controller, "edit_note"):
                controller.edit_note(note_item, global_pos=self.viewport().mapToGlobal(event.pos()))
                event.accept()
                return
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event: QtGui.QContextMenuEvent) -> None:  # type: ignore[override]
        self._show_context_menu(event.pos(), event.globalPos())

    def eventFilter(self, watched: QtCore.QObject, event: QtCore.QEvent) -> bool:  # type: ignore[override]
        if watched == self.viewport() and event.type() == QtCore.QEvent.Type.ContextMenu:
            try:
                ctx_event = event  # type: ignore[assignment]
                self._show_context_menu(ctx_event.pos(), ctx_event.globalPos())
                return True
            except Exception:
                return False
        return super().eventFilter(watched, event)

    def _on_custom_context_menu(self, pos: QtCore.QPoint) -> None:
        self._show_context_menu(pos, self.viewport().mapToGlobal(pos))

    def _show_context_menu(self, view_pos: QtCore.QPoint, global_pos: QtCore.QPoint) -> None:
        controller = self._resolve_controller()
        if controller is None:
            return
        menu = QtWidgets.QMenu(self)
        selected = self.scene().selectedItems()
        selected_kinds = {getattr(i, "data", lambda _k: None)(0) for i in selected}
        has_group = "group" in selected_kinds
        selected_items = [i for i in selected if getattr(i, "data", lambda _k: None)(0) in ("image", "note", "video", "sequence")]
        has_group_members = bool(selected_items)
        can_group = len(selected_items) >= 2
        single_video = len(selected_items) == 1 and selected_items[0].data(0) == "video"

        add_image = menu.addAction("Add Image...")
        add_video = menu.addAction("Add Video...")
        add_sequence = menu.addAction("Add Image Sequence...")
        add_note = menu.addAction("Add Note")
        convert_picnc = menu.addAction("Convert PICNC...")
        if single_video:
            convert_video = menu.addAction("Convert Video To Sequence")
        else:
            convert_video = None
        if can_group:
            add_group = menu.addAction("Group Selection")
        else:
            add_group = None
        auto_layout = menu.addAction("Auto Layout")
        if has_group_members:
            remove_from_group = menu.addAction("Remove From Group")
        else:
            remove_from_group = None
        if has_group:
            ungroup = menu.addAction("Ungroup")
        else:
            ungroup = None
        action = menu.exec(global_pos)
        if action == add_image and hasattr(controller, "add_image"):
            controller.add_image()
        elif action == add_video and hasattr(controller, "add_video"):
            controller.add_video()
        elif action == add_sequence and hasattr(controller, "add_sequence"):
            controller.add_sequence()
        elif action == add_note and hasattr(controller, "add_note_at"):
            controller.add_note_at(self.mapToScene(view_pos))
        elif action == convert_picnc and hasattr(controller, "convert_picnc_interactive"):
            controller.convert_picnc_interactive()
        elif convert_video is not None and action == convert_video and hasattr(controller, "convert_video_to_sequence"):
            controller.convert_video_to_sequence(selected_items[0])
        elif add_group is not None and action == add_group and hasattr(controller, "add_group"):
            controller.add_group()
        elif action == auto_layout and hasattr(controller, "layout_selection_grid"):
            controller.layout_selection_grid()
        elif remove_from_group is not None and action == remove_from_group and hasattr(controller, "remove_selected_from_groups"):
            controller.remove_selected_from_groups()
        elif ungroup is not None and action == ungroup and hasattr(controller, "ungroup_selected"):
            controller.ungroup_selected()

    def _on_groups_tree_menu(self, pos: QtCore.QPoint) -> None:
        item = self.groups_tree.itemAt(pos)
        if item is None:
            return
        info = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        menu = QtWidgets.QMenu(self.groups_tree)
        add_to_group = None
        remove_from_group = None
        ungroup = None
        if isinstance(info, tuple) and info:
            kind = info[0]
            if kind == "group":
                add_to_group = menu.addAction("Add Selected To Group")
                ungroup = menu.addAction("Ungroup")
            elif kind in ("image", "note"):
                remove_from_group = menu.addAction("Remove From Group")
        action = menu.exec(self.groups_tree.mapToGlobal(pos))
        controller = self._resolve_controller()
        if controller is None:
            return
        if action == add_to_group and hasattr(controller, "add_selected_to_group"):
            controller.add_selected_to_group(info[1])
        elif action == remove_from_group and hasattr(controller, "remove_selected_from_groups"):
            controller.remove_selected_from_groups()
        elif action == ungroup and hasattr(controller, "ungroup_selected"):
            controller.ungroup_selected()

    def _resolve_controller(self):
        widget: Optional[QtWidgets.QWidget] = self
        while widget is not None:
            controller = getattr(widget, "_controller", None)
            if controller is not None:
                return controller
            widget = widget.parentWidget()
        return None

    def set_show_grid(self, enabled: bool) -> None:
        self._show_grid = enabled
        self.viewport().update()

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:  # type: ignore[override]
        if event.matches(QtGui.QKeySequence.StandardKey.Undo):
            parent = self.parent()
            controller = getattr(parent, "_controller", None)
            if controller is not None and hasattr(controller, "undo"):
                controller.undo()
                event.accept()
                return
        if event.matches(QtGui.QKeySequence.StandardKey.Redo):
            parent = self.parent()
            controller = getattr(parent, "_controller", None)
            if controller is not None and hasattr(controller, "redo"):
                controller.redo()
                event.accept()
                return
        if event.key() in (QtCore.Qt.Key.Key_Delete, QtCore.Qt.Key.Key_Backspace):
            focused = self.scene().focusItem()
            if isinstance(focused, QtWidgets.QGraphicsTextItem):
                flags = focused.textInteractionFlags()
                if flags & QtCore.Qt.TextInteractionFlag.TextEditorInteraction:
                    super().keyPressEvent(event)
                    return
            for item in self.scene().selectedItems():
                self.scene().removeItem(item)
            event.accept()
            self._schedule_quality_update()
            return
        super().keyPressEvent(event)

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._schedule_quality_update()

    def _schedule_quality_update(self) -> None:
        if self._quality_timer is not None:
            return
        self._quality_timer = QtCore.QTimer(self)
        self._quality_timer.setSingleShot(True)
        self._quality_timer.timeout.connect(self._run_quality_update)
        self._quality_timer.start(60)

    def _run_quality_update(self) -> None:
        self._quality_timer = None
        parent = self.parent()
        controller = getattr(parent, "_controller", None)
        if controller is not None and hasattr(controller, "update_visible_items"):
            controller.update_visible_items()

    def _begin_scale(self, event: QtGui.QMouseEvent, items: list[QtWidgets.QGraphicsItem]) -> None:
        self._scaling = True
        self._scale_items = list(items)
        cursor_pos = self.mapToScene(event.pos())

        # Prefer bounds of the item under cursor if it's selected.
        hit = self.itemAt(event.pos())
        focus_bounds = hit.sceneBoundingRect() if (hit is not None and hit in self._scale_items) else None

        bounds = QtCore.QRectF()
        for item in self._scale_items:
            bounds = bounds.united(item.sceneBoundingRect())
        use_bounds = focus_bounds if focus_bounds is not None else bounds

        center = use_bounds.center()
        corners = [
            use_bounds.topLeft(),
            use_bounds.topRight(),
            use_bounds.bottomLeft(),
            use_bounds.bottomRight(),
        ]

        def dist2(a: QtCore.QPointF, b: QtCore.QPointF) -> float:
            dx = a.x() - b.x()
            dy = a.y() - b.y()
            return dx * dx + dy * dy

        center_d = dist2(cursor_pos, center)
        corner = min(corners, key=lambda p: dist2(cursor_pos, p))
        corner_d = dist2(cursor_pos, corner)
        pivot = center if center_d <= corner_d else corner

        self._scale_start_center = pivot
        self._scale_start_dist = max(self._scale_min_dist, QtCore.QLineF(pivot, cursor_pos).length())
        self._scale_start_values = []
        self._scale_start_positions = []
        self._scale_group_mode = len(self._scale_items) > 1
        for item in self._scale_items:
            self._scale_start_values.append(item.scale())
            self._scale_start_positions.append(item.pos())
            if not self._scale_group_mode:
                # Keep the pivot fixed in scene when changing transform origin.
                scene_pivot = QtCore.QPointF(pivot)
                local_pivot = item.mapFromScene(scene_pivot)
                item.setTransformOriginPoint(local_pivot)
                delta = scene_pivot - item.mapToScene(local_pivot)
                if not delta.isNull():
                    item.setPos(item.pos() + delta)
            overlay = QtWidgets.QGraphicsRectItem(item.sceneBoundingRect())
            overlay.setPen(QtGui.QPen(QtGui.QColor("#c6ccd6"), 1, QtCore.Qt.PenStyle.DashLine))
            overlay.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            overlay.setZValue(10_000)
            self.scene().addItem(overlay)
            self._scale_overlays.append(overlay)

    def _update_scale(self, event: QtGui.QMouseEvent) -> None:
        cursor_pos = self.mapToScene(event.pos())
        current_dist = max(self._scale_min_dist, QtCore.QLineF(self._scale_start_center, cursor_pos).length())
        factor = current_dist / max(self._scale_min_dist, self._scale_start_dist)
        factor = max(0.05, min(8.0, factor))
        for idx, item in enumerate(self._scale_items):
            start_scale = self._scale_start_values[idx] if idx < len(self._scale_start_values) else item.scale()
            start_pos = self._scale_start_positions[idx] if idx < len(self._scale_start_positions) else item.pos()
            item.setScale(max(0.05, min(8.0, start_scale * factor)))
            if self._scale_group_mode:
                offset = start_pos - self._scale_start_center
                item.setPos(self._scale_start_center + offset * factor)
            if idx < len(self._scale_overlays):
                self._scale_overlays[idx].setRect(item.sceneBoundingRect())

    def dragEnterEvent(self, event: QtGui.QDragEnterEvent) -> None:  # type: ignore[override]
        if event.mimeData().hasUrls():
            print("[BOARD][VIEW] dragEnter")
            event.setDropAction(QtCore.Qt.DropAction.CopyAction)
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event: QtGui.QDragMoveEvent) -> None:  # type: ignore[override]
        if event.mimeData().hasUrls():
            print("[BOARD][VIEW] dragMove")
            event.setDropAction(QtCore.Qt.DropAction.CopyAction)
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event: QtGui.QDropEvent) -> None:  # type: ignore[override]
        if event.mimeData().hasUrls():
            print("[BOARD][VIEW] dropEvent")
            widget = self.parentWidget()
            while widget is not None and not hasattr(widget, "handle_external_drop"):
                widget = widget.parentWidget()
            if widget is not None and hasattr(widget, "handle_external_drop"):
                widget.handle_external_drop(event)
                event.acceptProposedAction()
                return
            event.acceptProposedAction()
            return
        super().dropEvent(event)


class _TimelineWidget(QtWidgets.QWidget):
    playheadChanged = QtCore.Signal(int)
    selectedClipChanged = QtCore.Signal(int)

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self._total = 0
        self._clips: list[tuple[int, int]] = []
        self._playhead = 0
        self._dragging = False
        self._selected_clip = -1
        self._zoom = 1.0
        self._view_start = 0
        self._view_end = 0
        self._panning = False
        self._pan_last_x = 0.0
        self._ruler_height = 20
        self.setMinimumHeight(64)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        self.setMouseTracking(True)

    def set_data(self, total_frames: int, clips: list[tuple[int, int]], playhead: int) -> None:
        self._total = max(0, int(total_frames))
        self._clips = list(clips)
        self._playhead = max(0, min(int(playhead), max(0, self._total - 1)))
        if self._selected_clip >= len(self._clips):
            self._selected_clip = -1
        if self._selected_clip < 0 and self._clips:
            self._selected_clip = 0
        self._recompute_view()
        self.update()

    def set_selected_clip(self, index: int) -> None:
        if not self._clips:
            self._selected_clip = -1
        else:
            self._selected_clip = max(0, min(int(index), len(self._clips) - 1))
        self.update()

    def set_playhead(self, frame: int) -> None:
        self._playhead = max(0, min(int(frame), max(0, self._total - 1)))
        self._recompute_view()
        self.update()

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:  # type: ignore[override]
        if self._total <= 0:
            return
        if event.button() == QtCore.Qt.MouseButton.MiddleButton:
            self._panning = True
            self._pan_last_x = event.position().x()
            return
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            hit = self._hit_test_clip(event.position().x())
            if hit is not None:
                if hit != self._selected_clip:
                    self._selected_clip = hit
                    self.selectedClipChanged.emit(hit)
                self._dragging = True
                self._set_playhead_from_x(event.position().x())
                self.update()
            else:
                self._dragging = True
                self._set_playhead_from_x(event.position().x())

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:  # type: ignore[override]
        if self._panning:
            dx = event.position().x() - self._pan_last_x
            self._pan_last_x = event.position().x()
            self._pan_by_pixels(dx)
            return
        if self._dragging:
            self._set_playhead_from_x(event.position().x())

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:  # type: ignore[override]
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self._dragging = False
        if event.button() == QtCore.Qt.MouseButton.MiddleButton:
            self._panning = False

    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:  # type: ignore[override]
        if self._total <= 0:
            return
        delta = event.angleDelta().y()
        if delta == 0:
            return
        if event.modifiers() & QtCore.Qt.KeyboardModifier.ShiftModifier:
            self._pan_by_pixels(40 if delta < 0 else -40)
        else:
            factor = 1.2 if delta > 0 else 0.85
            self._zoom = max(1.0, min(40.0, self._zoom * factor))
            self._recompute_view(center=self._x_to_frame(event.position().x()))
        self.update()

    def _set_playhead_from_x(self, x_pos: float) -> None:
        frame = self._x_to_frame(x_pos)
        if frame != self._playhead:
            self._playhead = frame
            self._recompute_view()
            self.update()
            self.playheadChanged.emit(frame)

    def _recompute_view(self, center: Optional[int] = None) -> None:
        if self._total <= 0:
            self._view_start = 0
            self._view_end = 0
            return
        visible = int(max(2, self._total / self._zoom))
        half = visible // 2
        center = self._playhead if center is None else center
        start = max(0, center - half)
        end = min(self._total - 1, start + visible - 1)
        start = max(0, end - visible + 1)
        self._view_start = start
        self._view_end = end

    def _pan_by_pixels(self, dx: float) -> None:
        if self._total <= 0:
            return
        visible = max(1, self._view_end - self._view_start + 1)
        frames_per_px = visible / max(1.0, float(self.width()))
        delta_frames = int(dx * frames_per_px)
        if delta_frames == 0:
            return
        start = self._view_start - delta_frames
        start = max(0, min(start, max(0, self._total - visible)))
        self._view_start = start
        self._view_end = min(self._total - 1, start + visible - 1)
        self.update()

    def _x_to_frame(self, x_pos: float) -> int:
        x = max(0.0, min(float(x_pos), float(self.width())))
        ratio = x / max(1.0, float(self.width()))
        frame = int(self._view_start + ratio * max(1, self._view_end - self._view_start))
        return max(0, min(frame, max(0, self._total - 1)))

    def _frame_to_x(self, frame: int) -> float:
        if self._view_end <= self._view_start:
            return 0.0
        ratio = (frame - self._view_start) / max(1, self._view_end - self._view_start)
        return ratio * max(1.0, float(self.width()))

    def _hit_test_clip(self, x_pos: float) -> Optional[int]:
        if self._total <= 0:
            return None
        frame = self._x_to_frame(x_pos)
        for idx, (start, end) in enumerate(self._clips):
            if start <= frame <= end:
                return idx
        return None

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:  # type: ignore[override]
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), QtGui.QColor("#1f2329"))
        ruler_rect = QtCore.QRectF(8, 4, self.width() - 16, self._ruler_height)
        track_rect = QtCore.QRectF(8, self._ruler_height + 8, self.width() - 16, self.height() - self._ruler_height - 16)
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(QtGui.QColor("#20252c"))
        painter.drawRoundedRect(ruler_rect, 4, 4)
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(QtGui.QColor("#2a3038"))
        painter.drawRoundedRect(track_rect, 6, 6)
        if self._total > 0:
            for start, end in self._clips:
                left = track_rect.left() + self._frame_to_x(start)
                right = track_rect.left() + self._frame_to_x(end)
                rect = QtCore.QRectF(left, track_rect.top(), max(2.0, right - left), track_rect.height())
                painter.setBrush(QtGui.QColor(90, 140, 220, 200))
                painter.drawRoundedRect(rect, 5, 5)
            if 0 <= self._selected_clip < len(self._clips):
                s, e = self._clips[self._selected_clip]
                left = track_rect.left() + self._frame_to_x(s)
                right = track_rect.left() + self._frame_to_x(e)
                rect = QtCore.QRectF(left, track_rect.top(), max(2.0, right - left), track_rect.height())
                painter.setPen(QtGui.QPen(QtGui.QColor("#f2c14e"), 2))
                painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
                painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 6, 6)
                painter.setPen(QtCore.Qt.PenStyle.NoPen)
            # Frame ticks
            visible = max(1, self._view_end - self._view_start + 1)
            # Major ticks: multiples of 24, but adapt density to visible range
            major = 24
            target_labels = max(4, int(track_rect.width() / 120))
            step_major = max(major, int((visible / max(1, target_labels) + major - 1) // major) * major)
            minor = max(1, step_major // 4)
            painter.setPen(QtGui.QPen(QtGui.QColor("#3a404a"), 1))
            start_tick = (self._view_start // minor) * minor
            for f in range(start_tick, self._view_end + 1, minor):
                x = track_rect.left() + self._frame_to_x(f)
                if f % step_major == 0:
                    painter.setPen(QtGui.QPen(QtGui.QColor("#6c737d"), 1))
                    painter.drawLine(QtCore.QPointF(x, ruler_rect.top()), QtCore.QPointF(x, ruler_rect.bottom()))
                    painter.setPen(QtGui.QPen(QtGui.QColor("#9aa3ad"), 1))
                    painter.drawText(QtCore.QPointF(x + 2, ruler_rect.bottom() - 4), str(f))
                else:
                    painter.setPen(QtGui.QPen(QtGui.QColor("#3a404a"), 1))
                    painter.drawLine(QtCore.QPointF(x, ruler_rect.bottom() - 6), QtCore.QPointF(x, ruler_rect.bottom()))
            # Playhead
            ph_x = track_rect.left() + self._frame_to_x(self._playhead)
            painter.setPen(QtGui.QPen(QtGui.QColor("#f2c14e"), 2))
            painter.drawLine(QtCore.QPointF(ph_x, ruler_rect.top()), QtCore.QPointF(ph_x, track_rect.bottom() + 6))
        painter.setPen(QtGui.QColor("#9aa3ad"))
        painter.drawText(self.rect().adjusted(8, 0, -8, 0), QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignTop, "Timeline")


class BoardPage(QtWidgets.QWidget):
    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self._controller = None
        self.setAcceptDrops(True)
        layout = QtWidgets.QVBoxLayout(self)

        header = QtWidgets.QHBoxLayout()
        layout.addLayout(header)

        title = QtWidgets.QLabel("Board")
        title.setStyleSheet(title_style())
        header.addWidget(title, 0)

        self.project_label = QtWidgets.QLabel("No project selected")
        self.project_label.setStyleSheet(muted_text_style())
        header.addWidget(self.project_label, 1)

        self.grid_toggle = QtWidgets.QToolButton()
        self.grid_toggle.setText("Grid")
        self.grid_toggle.setCheckable(True)
        self.grid_toggle.setChecked(True)
        self.grid_toggle.setAutoRaise(True)
        self.grid_toggle.setIcon(QtWidgets.QApplication.style().standardIcon(
            QtWidgets.QStyle.StandardPixmap.SP_FileDialogDetailedView
        ))
        header.addWidget(self.grid_toggle, 0)

        self.groups_toggle = QtWidgets.QToolButton()
        self.groups_toggle.setText("Groups")
        self.groups_toggle.setCheckable(True)
        self.groups_toggle.setChecked(True)
        self.groups_toggle.setAutoRaise(True)
        header.addWidget(self.groups_toggle, 0)

        self.add_image_btn = QtWidgets.QPushButton("Add Image")
        header.addWidget(self.add_image_btn, 0)
        self.add_video_btn = QtWidgets.QPushButton("Add Video")
        header.addWidget(self.add_video_btn, 0)
        self.auto_layout_btn = QtWidgets.QPushButton("Auto Layout")
        header.addWidget(self.auto_layout_btn, 0)
        self.auto_layout_btn.setToolTip("Auto layout (Pinterest / masonry)")
        self.fit_btn = QtWidgets.QPushButton("Fit")
        header.addWidget(self.fit_btn, 0)
        self.save_btn = QtWidgets.QPushButton("Save")
        header.addWidget(self.save_btn, 0)
        self.load_btn = QtWidgets.QPushButton("Reload")
        header.addWidget(self.load_btn, 0)

        self.scene = QtWidgets.QGraphicsScene(self)
        self.scene.setSceneRect(-5000, -5000, 10000, 10000)
        self.scene.setItemIndexMethod(QtWidgets.QGraphicsScene.ItemIndexMethod.NoIndex)
        self.view = BoardView(self.scene, self)
        self.view.setStyleSheet(border_only_style())

        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        layout.addWidget(splitter, 1)

        self.groups_panel = QtWidgets.QFrame()
        self.groups_panel.setFixedWidth(220)
        self.groups_panel.setStyleSheet(subtle_panel_frame_style(bg_key="app_bg"))
        groups_layout = QtWidgets.QVBoxLayout(self.groups_panel)
        groups_layout.setContentsMargins(8, 8, 8, 8)
        groups_layout.setSpacing(6)
        groups_title = QtWidgets.QLabel("Groups")
        groups_title.setStyleSheet(f"color: {PALETTE['light_text']}; font-weight: bold;")
        groups_layout.addWidget(groups_title, 0)
        self.groups_tree = _GroupsTree()
        self.groups_tree.setHeaderHidden(True)
        self.groups_tree.setStyleSheet(tree_panel_style(bg_key="app_bg"))
        self.groups_tree.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.groups_tree.customContextMenuRequested.connect(self._on_groups_tree_menu)
        groups_layout.addWidget(self.groups_tree, 1)

        splitter.addWidget(self.groups_panel)
        splitter.addWidget(self.view)
        splitter.setStretchFactor(1, 1)

        # Edit panel (accordion on the right)
        self.edit_panel = QtWidgets.QFrame()
        self.edit_panel.setMinimumWidth(240)
        self.edit_panel.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )
        self.edit_panel.setStyleSheet(subtle_panel_frame_style(bg_key="app_bg"))
        edit_layout = QtWidgets.QVBoxLayout(self.edit_panel)
        edit_layout.setContentsMargins(10, 10, 10, 10)
        edit_layout.setSpacing(8)

        edit_header = QtWidgets.QHBoxLayout()
        edit_layout.addLayout(edit_header)
        self.edit_title = QtWidgets.QLabel("Edit Mode")
        self.edit_title.setStyleSheet(f"color: {PALETTE['light_text']}; font-weight: bold;")
        edit_header.addWidget(self.edit_title, 1)
        self.edit_close_btn = QtWidgets.QToolButton()
        self.edit_close_btn.setText("×")
        self.edit_close_btn.setAutoRaise(True)
        self.edit_close_btn.setStyleSheet(tool_button_style(padding="2px 6px", radius=4))
        edit_header.addWidget(self.edit_close_btn, 0)

        self.edit_info = QtWidgets.QLabel("")
        self.edit_info.setStyleSheet(muted_text_style())
        self.edit_info.setWordWrap(True)
        edit_layout.addWidget(self.edit_info, 0)

        self.edit_toolbar = QtWidgets.QHBoxLayout()
        self.edit_tool_crop = QtWidgets.QToolButton()
        self.edit_tool_crop.setText("Crop")
        self.edit_tool_crop.setEnabled(False)
        self.edit_toolbar.addWidget(self.edit_tool_crop, 0)
        self.edit_tool_levels = QtWidgets.QToolButton()
        self.edit_tool_levels.setText("Levels")
        self.edit_tool_levels.setEnabled(False)
        self.edit_toolbar.addWidget(self.edit_tool_levels, 0)
        self.edit_tool_export = QtWidgets.QToolButton()
        self.edit_tool_export.setText("Export")
        self.edit_tool_export.setEnabled(False)
        self.edit_toolbar.addWidget(self.edit_tool_export, 0)
        self.edit_toolbar.addStretch(1)
        edit_layout.addLayout(self.edit_toolbar)

        self.edit_exr_channel_row = QtWidgets.QHBoxLayout()
        self.edit_exr_channel_label = QtWidgets.QLabel("Channel")
        self.edit_exr_channel_label.setStyleSheet(muted_text_style())
        self.edit_exr_channel_combo = QtWidgets.QComboBox()
        self.edit_exr_channel_combo.setMinimumWidth(120)
        self.edit_exr_channel_row.addWidget(self.edit_exr_channel_label, 0)
        self.edit_exr_channel_row.addWidget(self.edit_exr_channel_combo, 1)
        self.edit_exr_channel_row.setEnabled(False)
        self.edit_exr_channel_label.setVisible(False)
        self.edit_exr_channel_combo.setVisible(False)
        edit_layout.addLayout(self.edit_exr_channel_row)

        self.edit_exr_gamma_row = QtWidgets.QHBoxLayout()
        self.edit_exr_srgb_check = QtWidgets.QCheckBox("sRGB")
        self.edit_exr_srgb_check.setChecked(True)
        self.edit_exr_gamma_label = QtWidgets.QLabel("Gamma: 2.2")
        self.edit_exr_gamma_label.setStyleSheet(muted_text_style())
        self.edit_exr_gamma_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.edit_exr_gamma_slider.setRange(10, 30)  # 1.0 - 3.0
        self.edit_exr_gamma_slider.setValue(22)
        self.edit_exr_gamma_row.addWidget(self.edit_exr_srgb_check, 0)
        self.edit_exr_gamma_row.addWidget(self.edit_exr_gamma_label, 0)
        self.edit_exr_gamma_row.addWidget(self.edit_exr_gamma_slider, 1)
        self.edit_exr_srgb_check.setVisible(False)
        self.edit_exr_gamma_label.setVisible(False)
        self.edit_exr_gamma_slider.setVisible(False)
        edit_layout.addLayout(self.edit_exr_gamma_row)

        # Preview stack (image / video / sequence)
        self.edit_preview_stack = QtWidgets.QStackedWidget()
        self.edit_preview_stack.setMinimumHeight(180)
        edit_layout.addWidget(self.edit_preview_stack, 1)

        self.edit_image_preview = VideoPreviewLabel()
        self.edit_image_preview.setStyleSheet("color: #9aa3ad;")
        self.edit_preview_stack.addWidget(self.edit_image_preview)

        self.edit_video_panel = QtWidgets.QWidget()
        video_layout = QtWidgets.QVBoxLayout(self.edit_video_panel)
        video_layout.setContentsMargins(0, 0, 0, 0)
        video_layout.setSpacing(6)
        self.edit_video_status = QtWidgets.QLabel("")
        self.edit_video_status.setStyleSheet(muted_text_style())
        video_layout.addWidget(self.edit_video_status, 0)
        self.edit_video_host = QtWidgets.QWidget()
        self.edit_video_host.setStyleSheet("color: #9aa3ad;")
        self.edit_video_host_layout = QtWidgets.QVBoxLayout(self.edit_video_host)
        self.edit_video_host_layout.setContentsMargins(0, 0, 0, 0)
        self.edit_video_host_layout.setSpacing(0)
        video_layout.addWidget(self.edit_video_host, 1)
        self.edit_video_controls = QtWidgets.QHBoxLayout()
        self.edit_video_play_btn = QtWidgets.QPushButton("Play")
        self.edit_video_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.edit_video_slider.setRange(0, 0)
        self.edit_video_controls.addWidget(self.edit_video_play_btn, 0)
        self.edit_video_controls.addWidget(self.edit_video_slider, 1)
        video_layout.addLayout(self.edit_video_controls, 0)

        self.edit_timeline = _TimelineWidget()
        video_layout.addWidget(self.edit_timeline, 0)

        timeline_actions = QtWidgets.QHBoxLayout()
        self.edit_timeline_frame_label = QtWidgets.QLabel("Frame: 0")
        self.edit_timeline_frame_label.setStyleSheet(muted_text_style())
        self.edit_timeline_split_btn = QtWidgets.QPushButton("Split")
        self.edit_timeline_export_btn = QtWidgets.QPushButton("Export Segment")
        timeline_actions.addWidget(self.edit_timeline_frame_label, 0)
        timeline_actions.addWidget(self.edit_timeline_split_btn, 0)
        timeline_actions.addWidget(self.edit_timeline_export_btn, 0)
        timeline_actions.addStretch(1)
        video_layout.addLayout(timeline_actions, 0)
        self.edit_preview_stack.addWidget(self.edit_video_panel)

        self.edit_sequence_panel = QtWidgets.QWidget()
        seq_layout = QtWidgets.QVBoxLayout(self.edit_sequence_panel)
        seq_layout.setContentsMargins(0, 0, 0, 0)
        seq_layout.setSpacing(6)
        self.edit_sequence_label = QtWidgets.QLabel("")
        self.edit_sequence_label.setStyleSheet(muted_text_style())
        seq_layout.addWidget(self.edit_sequence_label, 0)
        self.edit_sequence_preview = VideoPreviewLabel()
        self.edit_sequence_preview.setStyleSheet("color: #9aa3ad;")
        seq_layout.addWidget(self.edit_sequence_preview, 1)
        self.edit_sequence_controls = QtWidgets.QHBoxLayout()
        self.edit_sequence_play_btn = QtWidgets.QPushButton("Play")
        self.edit_sequence_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.edit_sequence_slider.setRange(0, 0)
        self.edit_sequence_controls.addWidget(self.edit_sequence_play_btn, 0)
        self.edit_sequence_controls.addWidget(self.edit_sequence_slider, 1)
        seq_layout.addLayout(self.edit_sequence_controls, 0)

        self.edit_sequence_timeline = _TimelineWidget()
        seq_layout.addWidget(self.edit_sequence_timeline, 0)

        self.edit_sequence_frame_label = QtWidgets.QLabel("Frame: 0")
        self.edit_sequence_frame_label.setStyleSheet(muted_text_style())
        seq_layout.addWidget(self.edit_sequence_frame_label, 0)
        self.edit_preview_stack.addWidget(self.edit_sequence_panel)

        self.edit_list = QtWidgets.QListWidget()
        self.edit_list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.NoSelection)
        self.edit_list.setVisible(False)
        edit_layout.addWidget(self.edit_list, 0)

        self.edit_footer = QtWidgets.QLabel("")
        self.edit_footer.setStyleSheet(muted_text_style())
        self.edit_footer.setWordWrap(True)
        edit_layout.addWidget(self.edit_footer, 0)

        self.edit_panel.setVisible(False)
        splitter.addWidget(self.edit_panel)

        self.grid_toggle.toggled.connect(self.view.set_show_grid)
        self.groups_toggle.toggled.connect(self.groups_panel.setVisible)
        self.edit_close_btn.clicked.connect(lambda: self.set_edit_panel_visible(False))

        self._undo_shortcut = QtGui.QShortcut(QtGui.QKeySequence.StandardKey.Undo, self)
        self._undo_shortcut.activated.connect(self._on_undo)
        self._redo_shortcut = QtGui.QShortcut(QtGui.QKeySequence.StandardKey.Redo, self)
        self._redo_shortcut.activated.connect(self._on_redo)

        footer = QtWidgets.QHBoxLayout()
        layout.addLayout(footer)
        self.hint_label = QtWidgets.QLabel(
            "Tip: Right-click for add/group, drag items, wheel to zoom, Ctrl+drag to scale, middle mouse to pan, Del to remove."
        )
        self.hint_label.setStyleSheet(muted_text_style())
        footer.addWidget(self.hint_label, 1)

    def set_edit_panel_visible(self, visible: bool) -> None:
        self.edit_panel.setVisible(bool(visible))

    def set_edit_panel_content(
        self,
        title: str,
        info_lines: list[str],
        list_items: Optional[list[str]] = None,
        footer: str = "",
    ) -> None:
        self.edit_title.setText(title)
        self.edit_info.setText("\n".join([line for line in info_lines if line]))
        self.edit_list.clear()
        if list_items:
            self.edit_list.addItems(list_items)
            self.edit_list.setVisible(True)
        else:
            self.edit_list.setVisible(False)
        self.edit_footer.setText(footer)
        self.set_edit_panel_visible(True)

    def set_exr_channels(self, channels: list[object]) -> None:
        self.edit_exr_channel_combo.blockSignals(True)
        self.edit_exr_channel_combo.clear()
        for entry in channels:
            if isinstance(entry, tuple) and len(entry) == 2:
                label, value = entry
                self.edit_exr_channel_combo.addItem(str(label), value)
            else:
                self.edit_exr_channel_combo.addItem(str(entry), str(entry))
        self.edit_exr_channel_combo.blockSignals(False)
        self.edit_exr_channel_row.setEnabled(bool(channels))
        self.edit_exr_channel_label.setVisible(True)
        self.edit_exr_channel_combo.setVisible(True)

    def current_exr_channel_value(self) -> str:
        data = self.edit_exr_channel_combo.currentData()
        if isinstance(data, str):
            return data
        return self.edit_exr_channel_combo.currentText()

    def set_exr_channel_row_visible(self, visible: bool) -> None:
        self.edit_exr_channel_label.setVisible(bool(visible))
        self.edit_exr_channel_combo.setVisible(bool(visible))
        self.edit_exr_channel_row.setEnabled(bool(visible))

        self.edit_exr_srgb_check.setVisible(bool(visible))
        self.edit_exr_gamma_label.setVisible(bool(visible))
        self.edit_exr_gamma_slider.setVisible(bool(visible))

    def current_exr_gamma(self) -> float:
        return float(self.edit_exr_gamma_slider.value()) / 10.0

    def current_exr_srgb_enabled(self) -> bool:
        return bool(self.edit_exr_srgb_check.isChecked())

    def set_exr_gamma_label(self, gamma: float) -> None:
        self.edit_exr_gamma_label.setText(f"Gamma: {gamma:.1f}")

    def show_edit_preview_image(self, pixmap: QtGui.QPixmap, label: str = "") -> None:
        self.edit_preview_stack.setCurrentWidget(self.edit_image_preview)
        if label:
            self.edit_footer.setText(label)
        self.edit_image_preview.set_base_pixmap(pixmap)

    def show_edit_preview_video(self) -> None:
        self.edit_preview_stack.setCurrentWidget(self.edit_video_panel)

    def show_edit_preview_sequence(self, pixmap: QtGui.QPixmap, label: str = "") -> None:
        self.edit_preview_stack.setCurrentWidget(self.edit_sequence_panel)
        if label:
            self.edit_sequence_label.setText(label)
        self.edit_sequence_preview.set_base_pixmap(pixmap)

    def handle_external_drop(self, event: QtGui.QDropEvent) -> None:
        controller = self._controller
        if controller is None:
            print("[BOARD] No board_controller on parent")
            return
        pos = None
        if hasattr(event, "position"):
            try:
                pos = event.position().toPoint()  # type: ignore[attr-defined]
            except Exception:
                pos = None
        if pos is None:
            try:
                pos = event.pos()  # type: ignore[attr-defined]
            except Exception:
                pos = None
        scene_pos = self.view.mapToScene(pos) if pos is not None else None
        print(f"[BOARD] Drop received. URLs: {len(event.mimeData().urls())} pos={pos} scene={scene_pos}")
        handled = False
        for url in event.mimeData().urls():
            local_path = Path(url.toLocalFile())
            print(f"[BOARD] URL -> {local_path}")
            if local_path.is_file():
                item = None
                if hasattr(controller, "_is_video_file") and controller._is_video_file(local_path):
                    if hasattr(controller, "add_video_from_path"):
                        item = controller.add_video_from_path(local_path, scene_pos=scene_pos)
                elif hasattr(controller, "_is_image_file") and controller._is_image_file(local_path):
                    item = controller.add_image_from_path(local_path, scene_pos=scene_pos)
                elif hasattr(controller, "_is_pic_file") and controller._is_pic_file(local_path):
                    if hasattr(controller, "convert_picnc_interactive"):
                        controller.convert_picnc_interactive(local_path)
                if item is not None:
                    controller.try_add_item_to_group(item, scene_pos)
                    handled = True
            else:
                if local_path.exists() and local_path.is_dir():
                    if hasattr(controller, "add_sequence_from_dir"):
                        item = controller.add_sequence_from_dir(local_path, scene_pos=scene_pos)
                        if item is not None:
                            controller.try_add_item_to_group(item, scene_pos)
                            handled = True
                    else:
                        print(f"[BOARD] Drop is a directory, ignored: {local_path}")
                    continue
                if url.isValid() and url.scheme().lower().startswith("http"):
                    controller.add_image_from_url(str(url.toString()), scene_pos=scene_pos)
                    handled = True
                else:
                    print(f"[BOARD] Missing path: {local_path}")
        if not handled and event.mimeData().hasImage():
            controller.add_image_from_image_data(event.mimeData().imageData(), scene_pos=scene_pos)
            handled = True
        if not handled and event.mimeData().hasHtml():
            html = event.mimeData().html()
            match = re.search(r'src=["\'](https?://[^"\']+)["\']', html)
            if match:
                controller.add_image_from_url(match.group(1), scene_pos=scene_pos)
                handled = True
        if not handled and event.mimeData().hasText():
            text = event.mimeData().text().strip()
            if text.lower().startswith("http"):
                controller.add_image_from_url(text, scene_pos=scene_pos)

    def set_controller(self, controller) -> None:
        self._controller = controller

    def _on_groups_tree_menu(self, pos: QtCore.QPoint) -> None:
        item = self.groups_tree.itemAt(pos)
        if item is None:
            return
        info = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        menu = QtWidgets.QMenu(self.groups_tree)
        add_to_group = None
        remove_from_group = None
        ungroup = None
        if isinstance(info, tuple) and info:
            kind = info[0]
            if kind == "group":
                add_to_group = menu.addAction("Add Selected To Group")
                ungroup = menu.addAction("Ungroup")
            elif kind in ("image", "note"):
                remove_from_group = menu.addAction("Remove From Group")
        action = menu.exec(self.groups_tree.mapToGlobal(pos))
        controller = self._controller
        if controller is None:
            return
        if action == add_to_group and hasattr(controller, "add_selected_to_group"):
            controller.add_selected_to_group(info[1])
        elif action == remove_from_group and hasattr(controller, "remove_selected_from_groups"):
            controller.remove_selected_from_groups()
        elif action == ungroup and hasattr(controller, "ungroup_selected"):
            controller.ungroup_selected()

    def dragEnterEvent(self, event: QtGui.QDragEnterEvent) -> None:  # type: ignore[override]
        if event.mimeData().hasUrls():
            print("[BOARD] dragEnter")
            event.setDropAction(QtCore.Qt.DropAction.CopyAction)
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event: QtGui.QDragMoveEvent) -> None:  # type: ignore[override]
        if event.mimeData().hasUrls():
            print("[BOARD] dragMove")
            event.setDropAction(QtCore.Qt.DropAction.CopyAction)
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event: QtGui.QDropEvent) -> None:  # type: ignore[override]
        if event.mimeData().hasUrls():
            print("[BOARD] dropEvent")
            self.handle_external_drop(event)
            event.acceptProposedAction()
            return
        super().dropEvent(event)

    def _on_undo(self) -> None:
        if self._controller is not None and hasattr(self._controller, "undo"):
            self._controller.undo()

    def _on_redo(self) -> None:
        if self._controller is not None and hasattr(self._controller, "redo"):
            self._controller.redo()

