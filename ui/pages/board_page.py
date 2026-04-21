from __future__ import annotations

from typing import Optional
import re
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets
from core.board_edit.panels import default_panel_state, tool_spec_for_panel

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


class _ToolStackRow(QtWidgets.QWidget):
    removeRequested = QtCore.Signal()

    def __init__(self, label: str, muted: bool, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_StyledBackground, True)
        self._muted = bool(muted)
        self._selected = False
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 6, 4)
        layout.setSpacing(6)
        self.label = QtWidgets.QLabel(label)
        self.label.setStyleSheet("background: transparent;")
        layout.addWidget(self.label, 1)
        self.remove_btn = QtWidgets.QToolButton()
        self.remove_btn.setText("x")
        self.remove_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.remove_btn.setAutoRaise(True)
        self.remove_btn.setFixedSize(16, 16)
        self.remove_btn.clicked.connect(self.removeRequested)
        layout.addWidget(self.remove_btn, 0)
        self.setFixedHeight(32)
        self._apply_style()

    def set_selected(self, selected: bool) -> None:
        self._selected = bool(selected)
        self._apply_style()

    def _apply_style(self) -> None:
        tone = "#87919d" if self._muted else "#d8dde5"
        if self._selected:
            bg = "rgba(255,255,255,10)"
            border = "rgba(242,193,78,72)"
        else:
            bg = "rgba(255,255,255,4)"
            border = "rgba(255,255,255,10)"
        self.setStyleSheet(
            "background: %s;"
            "border: 1px solid %s;"
            "border-radius: 7px;"
            % (bg, border)
        )
        self.label.setStyleSheet(f"color: {tone}; background: transparent; border: 0;")
        self.remove_btn.setStyleSheet(
            "QToolButton {"
            "background: transparent;"
            "border: 1px solid rgba(255,255,255,10);"
            "border-radius: 5px;"
            "padding: 0px;"
            "color: #8f99a4;"
            "}"
            "QToolButton:hover {"
            "background: rgba(255,255,255,6);"
            "border: 1px solid rgba(255,120,120,52);"
            "color: #d8dde5;"
            "}"
        )

from ui.utils.styles import (
    PALETTE,
    border_only_style,
    muted_text_style,
    subtle_panel_frame_style,
    title_style,
    tree_panel_style,
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
                controller = self._resolve_controller()
                if controller is not None and hasattr(controller, "begin_scene_interaction"):
                    controller.begin_scene_interaction()
                factor = 1.08 if event.angleDelta().y() > 0 else 0.92
                try:
                    for item in items:
                        item.setScale(max(0.05, min(8.0, item.scale() * factor)))
                finally:
                    if controller is not None and hasattr(controller, "end_scene_interaction"):
                        controller.end_scene_interaction(history=True, update_groups=True)
                event.accept()
                self._schedule_quality_update()
                self._notify_overlay_position()
                return
        factor = 1.2 if event.angleDelta().y() > 0 else 0.85
        self.scale(factor, factor)
        self._schedule_quality_update()
        self._notify_overlay_position()

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:  # type: ignore[override]
        controller = self._resolve_controller()
        if controller is not None and hasattr(controller, "handle_view_mouse_press"):
            try:
                if controller.handle_view_mouse_press(self.mapToScene(event.pos()), event):
                    event.accept()
                    return
            except Exception:
                pass
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
            controller = self._resolve_controller()
            if controller is not None and hasattr(controller, "begin_scene_interaction"):
                controller.begin_scene_interaction()
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
        controller = self._resolve_controller()
        if controller is not None and hasattr(controller, "handle_view_mouse_move"):
            try:
                if controller.handle_view_mouse_move(self.mapToScene(event.pos()), event):
                    event.accept()
                    return
            except Exception:
                pass
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
            self._notify_overlay_position()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:  # type: ignore[override]
        controller = self._resolve_controller()
        if controller is not None and hasattr(controller, "handle_view_mouse_release"):
            try:
                if controller.handle_view_mouse_release(self.mapToScene(event.pos()), event):
                    event.accept()
                    return
            except Exception:
                pass
        if getattr(self, "_scaling", False) and event.button() == QtCore.Qt.MouseButton.LeftButton:
            controller = self._resolve_controller()
            self._scaling = False
            for overlay in self._scale_overlays:
                self.scene().removeItem(overlay)
            self._scale_overlays = []
            self._scale_items = []
            self._scale_start_values = []
            self._scale_start_positions = []
            event.accept()
            if controller is not None and hasattr(controller, "end_scene_interaction"):
                controller.end_scene_interaction(history=True, update_groups=True)
            self._schedule_quality_update()
            self._notify_overlay_position()
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
            controller = self._resolve_controller()
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
                if controller is not None and hasattr(controller, "handle_item_drop"):
                    controller.handle_item_drop(moved)
            if controller is not None and hasattr(controller, "end_scene_interaction"):
                controller.end_scene_interaction(history=bool(moved), update_groups=True)
            self._schedule_quality_update()
            self._notify_overlay_position()
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

    def focusNextPrevChild(self, next: bool) -> bool:  # type: ignore[override]
        return False

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
        controller = self._resolve_controller()
        if controller is not None and hasattr(controller, "show_groups_tree_context_menu"):
            handled = controller.show_groups_tree_context_menu(pos)
            if handled:
                return
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
        if event.key() == QtCore.Qt.Key.Key_Tab:
            page = self.parent()
            if page is not None and hasattr(page, "show_tool_add_menu"):
                if page.show_tool_add_menu(QtGui.QCursor.pos()):
                    event.accept()
                    return
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
            controller = self._resolve_controller()
            if controller is not None and hasattr(controller, "delete_selected_items"):
                controller.delete_selected_items()
            else:
                for item in self.scene().selectedItems():
                    self.scene().removeItem(item)
            event.accept()
            self._schedule_quality_update()
            return
        if event.key() == QtCore.Qt.Key.Key_Escape:
            parent = self.parent()
            controller = getattr(parent, "_controller", None)
            if controller is not None and hasattr(controller, "exit_focus_mode"):
                controller.exit_focus_mode()
                event.accept()
                return
        super().keyPressEvent(event)

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        page = self.parent()
        if page is not None and hasattr(page, "_position_edit_overlay"):
            try:
                page._position_edit_overlay()
            except Exception:
                pass
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

    def _notify_overlay_position(self) -> None:
        page = self.parent()
        if page is not None and hasattr(page, "_position_edit_overlay"):
            try:
                page._position_edit_overlay()
            except Exception:
                pass

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
    scrubStateChanged = QtCore.Signal(bool)

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
            if not self._dragging:
                self._dragging = True
                self.scrubStateChanged.emit(True)
            hit = self._hit_test_clip(event.position().x())
            if hit is not None:
                if hit != self._selected_clip:
                    self._selected_clip = hit
                    self.selectedClipChanged.emit(hit)
                self._set_playhead_from_x(event.position().x())
                self.update()
            else:
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
            if self._dragging:
                self._dragging = False
                self.scrubStateChanged.emit(False)
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
    imageToolAddRequested = QtCore.Signal(str)
    imageToolRemoveRequested = QtCore.Signal(int)

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self._controller = None
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        self.setAcceptDrops(True)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

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
        self.groups_tree.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.groups_tree.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.groups_tree.customContextMenuRequested.connect(self._on_groups_tree_menu)
        groups_layout.addWidget(self.groups_tree, 1)

        splitter.addWidget(self.groups_panel)
        splitter.addWidget(self.view)
        splitter.setStretchFactor(1, 1)

        self.loading_overlay = QtWidgets.QFrame(self.view)
        self.loading_overlay.setAttribute(QtCore.Qt.WidgetAttribute.WA_StyledBackground, True)
        self.loading_overlay.setStyleSheet(
            "QFrame {"
            "background: rgba(23, 26, 31, 220);"
            "border: 1px solid rgba(242, 193, 78, 70);"
            "border-radius: 14px;"
            "}"
            "QLabel { background: transparent; border: 0; }"
        )
        loading_layout = QtWidgets.QVBoxLayout(self.loading_overlay)
        loading_layout.setContentsMargins(18, 14, 18, 14)
        loading_layout.setSpacing(6)
        self.loading_title = QtWidgets.QLabel("Loading board")
        self.loading_title.setStyleSheet("color: #f2c14e; font-weight: 700; font-size: 14px;")
        loading_layout.addWidget(self.loading_title, 0)
        self.loading_detail = QtWidgets.QLabel("Preparing workspace...")
        self.loading_detail.setStyleSheet(muted_text_style())
        self.loading_detail.setWordWrap(True)
        loading_layout.addWidget(self.loading_detail, 0)
        self.loading_overlay.setFixedWidth(300)
        self.loading_overlay.hide()

        # Edit overlay (floating over the board view)
        self.edit_panel = QtWidgets.QFrame()
        self.edit_panel.setParent(self)
        self.edit_panel.setAttribute(QtCore.Qt.WidgetAttribute.WA_StyledBackground, True)
        self.edit_panel.setMinimumWidth(320)
        self.edit_panel.setMaximumWidth(380)
        self.edit_panel.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Fixed,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )
        self.edit_panel.setStyleSheet(
            "QFrame {"
            "background: rgba(23, 26, 31, 238);"
            "border: 1px solid rgba(255,255,255,20);"
            "border-radius: 12px;"
            "}"
            "QLabel { background: transparent; }"
            "QPushButton, QToolButton, QComboBox {"
            "background: rgba(255,255,255,5);"
            "border: 1px solid rgba(255,255,255,12);"
            "border-radius: 6px;"
            "padding: 5px 9px;"
            "}"
            "QPushButton:hover, QToolButton:hover, QComboBox:hover {"
            "background: rgba(255,255,255,9);"
            "}"
            "QAbstractSpinBox {"
            "background: rgba(16, 19, 24, 220);"
            "border: 1px solid rgba(255,255,255,12);"
            "border-radius: 6px;"
            "padding: 4px 8px;"
            "selection-background-color: rgba(242,193,78,36);"
            "}"
            "QListWidget {"
            "background: rgba(255,255,255,3);"
            "border: 1px solid rgba(255,255,255,10);"
            "border-radius: 8px;"
            "padding: 6px;"
            "outline: none;"
            "}"
            "QListWidget::item {"
            "background: rgba(255,255,255,4);"
            "border: 1px solid rgba(255,255,255,10);"
            "border-radius: 7px;"
            "padding: 8px 10px;"
            "margin: 2px 0;"
            "}"
            "QListWidget::item:selected {"
            "background: rgba(255,255,255,8);"
            "border: 1px solid rgba(242,193,78,70);"
            "}"
            "QSlider::groove:horizontal {"
            "height: 4px;"
            "background: rgba(255,255,255,12);"
            "border-radius: 2px;"
            "}"
            "QSlider::handle:horizontal {"
            "background: #c7ccd3;"
            "border: 1px solid rgba(12,15,20,110);"
            "width: 12px;"
            "margin: -5px 0;"
            "border-radius: 6px;"
            "}"
        )
        shadow = QtWidgets.QGraphicsDropShadowEffect(self.edit_panel)
        shadow.setBlurRadius(38)
        shadow.setOffset(0, 14)
        shadow.setColor(QtGui.QColor(0, 0, 0, 150))
        self.edit_panel.setGraphicsEffect(shadow)
        edit_layout = QtWidgets.QVBoxLayout(self.edit_panel)
        edit_layout.setContentsMargins(16, 16, 16, 16)
        edit_layout.setSpacing(8)

        edit_header = QtWidgets.QHBoxLayout()
        edit_layout.addLayout(edit_header)
        self.edit_title = QtWidgets.QLabel("Edit Mode")
        self.edit_title.setStyleSheet(f"color: {PALETTE['light_text']}; font-weight: 600; font-size: 15px;")
        edit_header.addWidget(self.edit_title, 1)
        self.edit_close_btn = QtWidgets.QToolButton()
        self.edit_close_btn.setText("×")
        self.edit_close_btn.setAutoRaise(True)
        self.edit_close_btn.setStyleSheet(
            "QToolButton {"
            "padding: 2px 8px;"
            "border-radius: 6px;"
            "background: rgba(255,255,255,4);"
            "border: 1px solid rgba(255,255,255,10);"
            "color: #aeb6bf;"
            "}"
            "QToolButton:hover {"
            "background: rgba(255,255,255,8);"
            "color: #d8dde5;"
            "}"
        )
        edit_header.addWidget(self.edit_close_btn, 0)

        self.edit_info = QtWidgets.QLabel("")
        self.edit_info.setStyleSheet(muted_text_style())
        self.edit_info.setWordWrap(True)
        edit_layout.addWidget(self.edit_info, 0)

        self.edit_tool_hint = QtWidgets.QLabel("")
        self.edit_tool_hint.setStyleSheet("color: #c2a25a; font-size: 11px;")
        self.edit_tool_hint.setVisible(False)
        edit_layout.addWidget(self.edit_tool_hint, 0)

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
        self.edit_exr_gamma_input = QtWidgets.QDoubleSpinBox()
        self.edit_exr_gamma_input.setRange(1.0, 3.0)
        self.edit_exr_gamma_input.setDecimals(1)
        self.edit_exr_gamma_input.setSingleStep(0.1)
        self.edit_exr_gamma_input.setButtonSymbols(QtWidgets.QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.edit_exr_gamma_input.setKeyboardTracking(False)
        self.edit_exr_gamma_input.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        self.edit_exr_gamma_input.setFixedWidth(62)
        self.edit_exr_gamma_input.setValue(2.2)
        self.edit_exr_gamma_row.addWidget(self.edit_exr_srgb_check, 0)
        self.edit_exr_gamma_row.addWidget(self.edit_exr_gamma_label, 0)
        self.edit_exr_gamma_row.addWidget(self.edit_exr_gamma_slider, 1)
        self.edit_exr_gamma_row.addWidget(self.edit_exr_gamma_input, 0)
        self.edit_exr_srgb_check.setVisible(False)
        self.edit_exr_gamma_label.setVisible(False)
        self.edit_exr_gamma_slider.setVisible(False)
        self.edit_exr_gamma_input.setVisible(False)
        edit_layout.addLayout(self.edit_exr_gamma_row)

        self.edit_tool_stack_section = QtWidgets.QFrame()
        self.edit_tool_stack_section.setStyleSheet(
            "QFrame {"
            "background: rgba(255,255,255,2);"
            "border: 1px solid rgba(255,255,255,8);"
            "border-radius: 8px;"
            "}"
        )
        self.edit_tool_stack_layout = QtWidgets.QVBoxLayout(self.edit_tool_stack_section)
        self.edit_tool_stack_layout.setContentsMargins(10, 10, 10, 10)
        self.edit_tool_stack_layout.setSpacing(8)
        edit_layout.addWidget(self.edit_tool_stack_section, 0)

        self.edit_image_tools_header = QtWidgets.QHBoxLayout()
        self.edit_tool_stack_layout.addLayout(self.edit_image_tools_header)
        self.edit_image_tools_label = QtWidgets.QLabel("Tool Stack")
        self.edit_image_tools_label.setStyleSheet("color: #8d97a2; font-size: 11px; font-weight: 600;")
        self.edit_image_tools_header.addWidget(self.edit_image_tools_label, 0)
        self.edit_image_tools_header.addStretch(1)

        self.edit_image_tool_add_btn = QtWidgets.QToolButton()
        self.edit_image_tool_add_btn.setText("Add")
        self.edit_image_tool_add_btn.setAutoRaise(True)
        self.edit_image_tool_add_btn.setStyleSheet(
            "QToolButton {"
            "background: rgba(255,255,255,4);"
            "border: 1px solid rgba(255,255,255,10);"
            "border-radius: 6px;"
            "padding: 4px 8px;"
            "color: #c8ced6;"
            "}"
            "QToolButton:hover {"
            "background: rgba(255,255,255,8);"
            "}"
        )
        self.edit_image_tools_header.addWidget(self.edit_image_tool_add_btn, 0)

        self.edit_image_tool_empty = QtWidgets.QLabel("No tools in the stack yet.")
        self.edit_image_tool_empty.setStyleSheet("color: #6f7a86; font-size: 12px; padding: 2px 2px 6px 2px;")
        self.edit_image_tool_empty.setVisible(False)
        self.edit_tool_stack_layout.addWidget(self.edit_image_tool_empty, 0)

        self.edit_image_tool_list = QtWidgets.QListWidget()
        self.edit_image_tool_list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.edit_image_tool_list.setMaximumHeight(152)
        self.edit_image_tool_list.setUniformItemSizes(True)
        self.edit_image_tool_list.setSpacing(6)
        self.edit_image_tool_list.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.edit_image_tool_list.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.edit_image_tool_list.setStyleSheet(
            "QListWidget {"
            "background: transparent;"
            "border: none;"
            "padding: 0px;"
            "outline: none;"
            "}"
            "QListWidget::item {"
            "background: transparent;"
            "border: none;"
            "padding: 0px;"
            "margin: 0px;"
            "}"
        )
        self.edit_image_tool_list.setVisible(False)
        self.edit_tool_stack_layout.addWidget(self.edit_image_tool_list, 0)

        self.edit_image_tool_add_row = QtWidgets.QHBoxLayout()
        self.edit_image_tool_add_combo = QtWidgets.QComboBox()
        self.edit_image_tool_add_combo.setMinimumWidth(120)
        self.edit_image_tool_add_row.addWidget(self.edit_image_tool_add_combo, 1)
        self.edit_image_tool_add_combo.setVisible(False)

        self.edit_image_tool_order_row = QtWidgets.QHBoxLayout()
        self.edit_image_tool_up_btn = QtWidgets.QPushButton("Up")
        self.edit_image_tool_down_btn = QtWidgets.QPushButton("Down")
        self.edit_image_tool_up_btn.setFixedWidth(46)
        self.edit_image_tool_down_btn.setFixedWidth(56)
        self.edit_image_tool_up_btn.setStyleSheet(
            "QPushButton { color: #aeb6bf; font-size: 11px; }"
        )
        self.edit_image_tool_down_btn.setStyleSheet(
            "QPushButton { color: #aeb6bf; font-size: 11px; }"
        )
        self.edit_image_tool_order_row.addWidget(self.edit_image_tool_up_btn, 0)
        self.edit_image_tool_order_row.addWidget(self.edit_image_tool_down_btn, 0)
        self.edit_image_tool_order_row.addStretch(1)
        self.edit_image_tools_header.addWidget(self.edit_image_tool_up_btn, 0)
        self.edit_image_tools_header.addWidget(self.edit_image_tool_down_btn, 0)
        self.edit_image_tool_up_btn.setVisible(False)
        self.edit_image_tool_down_btn.setVisible(False)
        self.edit_image_tool_add_btn.setVisible(False)
        self.edit_image_tool_list.currentRowChanged.connect(self._refresh_tool_stack_row_selection)

        self.edit_image_adjust_label = QtWidgets.QLabel("Image Adjustments")
        self.edit_image_adjust_label.setStyleSheet(muted_text_style())
        self.edit_image_adjust_label.setVisible(False)
        self.edit_tool_stack_layout.addWidget(self.edit_image_adjust_label, 0)

        self.edit_image_adjust_brightness_row = QtWidgets.QHBoxLayout()
        self.edit_image_adjust_brightness_title = QtWidgets.QLabel("Brightness")
        self.edit_image_adjust_brightness_title.setStyleSheet(muted_text_style())
        self.edit_image_adjust_brightness_value = QtWidgets.QDoubleSpinBox()
        self.edit_image_adjust_brightness_value.setRange(-1.0, 1.0)
        self.edit_image_adjust_brightness_value.setDecimals(2)
        self.edit_image_adjust_brightness_value.setSingleStep(0.05)
        self.edit_image_adjust_brightness_value.setButtonSymbols(QtWidgets.QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.edit_image_adjust_brightness_value.setKeyboardTracking(False)
        self.edit_image_adjust_brightness_value.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        self.edit_image_adjust_brightness_value.setFixedWidth(70)
        self.edit_image_adjust_brightness_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.edit_image_adjust_brightness_slider.setRange(-100, 100)
        self.edit_image_adjust_brightness_slider.setValue(0)
        self.edit_image_adjust_brightness_row.addWidget(self.edit_image_adjust_brightness_title, 0)
        self.edit_image_adjust_brightness_row.addWidget(self.edit_image_adjust_brightness_slider, 1)
        self.edit_image_adjust_brightness_row.addWidget(self.edit_image_adjust_brightness_value, 0)
        self.edit_tool_stack_layout.addLayout(self.edit_image_adjust_brightness_row)

        self.edit_image_adjust_contrast_row = QtWidgets.QHBoxLayout()
        self.edit_image_adjust_contrast_title = QtWidgets.QLabel("Contrast")
        self.edit_image_adjust_contrast_title.setStyleSheet(muted_text_style())
        self.edit_image_adjust_contrast_value = QtWidgets.QDoubleSpinBox()
        self.edit_image_adjust_contrast_value.setRange(0.0, 2.0)
        self.edit_image_adjust_contrast_value.setDecimals(2)
        self.edit_image_adjust_contrast_value.setSingleStep(0.05)
        self.edit_image_adjust_contrast_value.setButtonSymbols(QtWidgets.QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.edit_image_adjust_contrast_value.setKeyboardTracking(False)
        self.edit_image_adjust_contrast_value.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        self.edit_image_adjust_contrast_value.setFixedWidth(70)
        self.edit_image_adjust_contrast_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.edit_image_adjust_contrast_slider.setRange(0, 200)
        self.edit_image_adjust_contrast_slider.setValue(100)
        self.edit_image_adjust_contrast_row.addWidget(self.edit_image_adjust_contrast_title, 0)
        self.edit_image_adjust_contrast_row.addWidget(self.edit_image_adjust_contrast_slider, 1)
        self.edit_image_adjust_contrast_row.addWidget(self.edit_image_adjust_contrast_value, 0)
        self.edit_tool_stack_layout.addLayout(self.edit_image_adjust_contrast_row)

        self.edit_image_adjust_saturation_row = QtWidgets.QHBoxLayout()
        self.edit_image_adjust_saturation_title = QtWidgets.QLabel("Saturation")
        self.edit_image_adjust_saturation_title.setStyleSheet(muted_text_style())
        self.edit_image_adjust_saturation_value = QtWidgets.QDoubleSpinBox()
        self.edit_image_adjust_saturation_value.setRange(0.0, 2.0)
        self.edit_image_adjust_saturation_value.setDecimals(2)
        self.edit_image_adjust_saturation_value.setSingleStep(0.05)
        self.edit_image_adjust_saturation_value.setButtonSymbols(QtWidgets.QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.edit_image_adjust_saturation_value.setKeyboardTracking(False)
        self.edit_image_adjust_saturation_value.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        self.edit_image_adjust_saturation_value.setFixedWidth(70)
        self.edit_image_adjust_saturation_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.edit_image_adjust_saturation_slider.setRange(0, 200)
        self.edit_image_adjust_saturation_slider.setValue(100)
        self.edit_image_adjust_saturation_row.addWidget(self.edit_image_adjust_saturation_title, 0)
        self.edit_image_adjust_saturation_row.addWidget(self.edit_image_adjust_saturation_slider, 1)
        self.edit_image_adjust_saturation_row.addWidget(self.edit_image_adjust_saturation_value, 0)
        self.edit_tool_stack_layout.addLayout(self.edit_image_adjust_saturation_row)

        self.edit_image_vibrance_row = QtWidgets.QHBoxLayout()
        self.edit_image_vibrance_title = QtWidgets.QLabel("Vibrance")
        self.edit_image_vibrance_title.setStyleSheet(muted_text_style())
        self.edit_image_vibrance_value = QtWidgets.QDoubleSpinBox()
        self.edit_image_vibrance_value.setRange(-1.0, 1.0)
        self.edit_image_vibrance_value.setDecimals(2)
        self.edit_image_vibrance_value.setSingleStep(0.05)
        self.edit_image_vibrance_value.setButtonSymbols(QtWidgets.QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.edit_image_vibrance_value.setKeyboardTracking(False)
        self.edit_image_vibrance_value.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        self.edit_image_vibrance_value.setFixedWidth(70)
        self.edit_image_vibrance_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.edit_image_vibrance_slider.setRange(-100, 100)
        self.edit_image_vibrance_slider.setValue(0)
        self.edit_image_vibrance_row.addWidget(self.edit_image_vibrance_title, 0)
        self.edit_image_vibrance_row.addWidget(self.edit_image_vibrance_slider, 1)
        self.edit_image_vibrance_row.addWidget(self.edit_image_vibrance_value, 0)
        self.edit_tool_stack_layout.addLayout(self.edit_image_vibrance_row)

        self.edit_crop_label = QtWidgets.QLabel("Crop")
        self.edit_crop_label.setStyleSheet(muted_text_style())
        self.edit_crop_label.setVisible(False)
        self.edit_tool_stack_layout.addWidget(self.edit_crop_label, 0)

        self.edit_crop_left_row = QtWidgets.QHBoxLayout()
        self.edit_crop_left_title = QtWidgets.QLabel("Left")
        self.edit_crop_left_title.setStyleSheet(muted_text_style())
        self.edit_crop_left_value = QtWidgets.QDoubleSpinBox()
        self.edit_crop_left_value.setRange(0.0, 90.0)
        self.edit_crop_left_value.setDecimals(0)
        self.edit_crop_left_value.setSingleStep(1.0)
        self.edit_crop_left_value.setSuffix("%")
        self.edit_crop_left_value.setButtonSymbols(QtWidgets.QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.edit_crop_left_value.setKeyboardTracking(False)
        self.edit_crop_left_value.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        self.edit_crop_left_value.setFixedWidth(74)
        self.edit_crop_left_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.edit_crop_left_slider.setRange(0, 90)
        self.edit_crop_left_slider.setValue(0)
        self.edit_crop_left_row.addWidget(self.edit_crop_left_title, 0)
        self.edit_crop_left_row.addWidget(self.edit_crop_left_slider, 1)
        self.edit_crop_left_row.addWidget(self.edit_crop_left_value, 0)
        self.edit_tool_stack_layout.addLayout(self.edit_crop_left_row)

        self.edit_crop_right_row = QtWidgets.QHBoxLayout()
        self.edit_crop_right_title = QtWidgets.QLabel("Right")
        self.edit_crop_right_title.setStyleSheet(muted_text_style())
        self.edit_crop_right_value = QtWidgets.QDoubleSpinBox()
        self.edit_crop_right_value.setRange(0.0, 90.0)
        self.edit_crop_right_value.setDecimals(0)
        self.edit_crop_right_value.setSingleStep(1.0)
        self.edit_crop_right_value.setSuffix("%")
        self.edit_crop_right_value.setButtonSymbols(QtWidgets.QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.edit_crop_right_value.setKeyboardTracking(False)
        self.edit_crop_right_value.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        self.edit_crop_right_value.setFixedWidth(74)
        self.edit_crop_right_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.edit_crop_right_slider.setRange(0, 90)
        self.edit_crop_right_slider.setValue(0)
        self.edit_crop_right_row.addWidget(self.edit_crop_right_title, 0)
        self.edit_crop_right_row.addWidget(self.edit_crop_right_slider, 1)
        self.edit_crop_right_row.addWidget(self.edit_crop_right_value, 0)
        self.edit_tool_stack_layout.addLayout(self.edit_crop_right_row)

        self.edit_crop_top_row = QtWidgets.QHBoxLayout()
        self.edit_crop_top_title = QtWidgets.QLabel("Top")
        self.edit_crop_top_title.setStyleSheet(muted_text_style())
        self.edit_crop_top_value = QtWidgets.QDoubleSpinBox()
        self.edit_crop_top_value.setRange(0.0, 90.0)
        self.edit_crop_top_value.setDecimals(0)
        self.edit_crop_top_value.setSingleStep(1.0)
        self.edit_crop_top_value.setSuffix("%")
        self.edit_crop_top_value.setButtonSymbols(QtWidgets.QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.edit_crop_top_value.setKeyboardTracking(False)
        self.edit_crop_top_value.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        self.edit_crop_top_value.setFixedWidth(74)
        self.edit_crop_top_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.edit_crop_top_slider.setRange(0, 90)
        self.edit_crop_top_slider.setValue(0)
        self.edit_crop_top_row.addWidget(self.edit_crop_top_title, 0)
        self.edit_crop_top_row.addWidget(self.edit_crop_top_slider, 1)
        self.edit_crop_top_row.addWidget(self.edit_crop_top_value, 0)
        self.edit_tool_stack_layout.addLayout(self.edit_crop_top_row)

        self.edit_crop_bottom_row = QtWidgets.QHBoxLayout()
        self.edit_crop_bottom_title = QtWidgets.QLabel("Bottom")
        self.edit_crop_bottom_title.setStyleSheet(muted_text_style())
        self.edit_crop_bottom_value = QtWidgets.QDoubleSpinBox()
        self.edit_crop_bottom_value.setRange(0.0, 90.0)
        self.edit_crop_bottom_value.setDecimals(0)
        self.edit_crop_bottom_value.setSingleStep(1.0)
        self.edit_crop_bottom_value.setSuffix("%")
        self.edit_crop_bottom_value.setButtonSymbols(QtWidgets.QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.edit_crop_bottom_value.setKeyboardTracking(False)
        self.edit_crop_bottom_value.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        self.edit_crop_bottom_value.setFixedWidth(74)
        self.edit_crop_bottom_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.edit_crop_bottom_slider.setRange(0, 90)
        self.edit_crop_bottom_slider.setValue(0)
        self.edit_crop_bottom_row.addWidget(self.edit_crop_bottom_title, 0)
        self.edit_crop_bottom_row.addWidget(self.edit_crop_bottom_slider, 1)
        self.edit_crop_bottom_row.addWidget(self.edit_crop_bottom_value, 0)
        self.edit_tool_stack_layout.addLayout(self.edit_crop_bottom_row)

        self.edit_image_adjust_reset_btn = QtWidgets.QPushButton("Reset Adjustments")
        self.edit_image_adjust_reset_btn.setVisible(False)
        self.edit_tool_stack_layout.addWidget(self.edit_image_adjust_reset_btn, 0)

        self.edit_tool_stack_section.setVisible(False)

        self.set_image_adjust_controls_visible(False)

        # Preview stack (image / video / sequence)
        self.edit_preview_stack = QtWidgets.QStackedWidget()
        self.edit_preview_stack.setMinimumHeight(140)
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
        self.edit_sequence_timeline = _TimelineWidget()
        seq_layout.addWidget(self.edit_sequence_timeline, 0)
        self.edit_sequence_timeline.setVisible(False)

        self.edit_sequence_frame_label = QtWidgets.QLabel("Frame: 0")
        self.edit_sequence_frame_label.setStyleSheet(muted_text_style())
        seq_layout.addWidget(self.edit_sequence_frame_label, 0)
        self.edit_sequence_frame_label.setVisible(False)
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
        self.edit_panel.raise_()

        self.focus_exit_btn = QtWidgets.QToolButton(self)
        self.focus_exit_btn.setText("Exit Focus")
        self.focus_exit_btn.setVisible(False)
        self.focus_exit_btn.setAutoRaise(True)
        self.focus_exit_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.focus_exit_btn.setStyleSheet(
            "QToolButton {"
            "background: rgba(24, 28, 34, 228);"
            "border: 1px solid rgba(255,255,255,26);"
            "border-radius: 12px;"
            "padding: 8px 12px;"
            "}"
            "QToolButton:hover {"
            "background: rgba(255,255,255,14);"
            "}"
        )
        exit_shadow = QtWidgets.QGraphicsDropShadowEffect(self.focus_exit_btn)
        exit_shadow.setBlurRadius(26)
        exit_shadow.setOffset(0, 8)
        exit_shadow.setColor(QtGui.QColor(0, 0, 0, 120))
        self.focus_exit_btn.setGraphicsEffect(exit_shadow)
        self.focus_exit_btn.clicked.connect(self._on_exit_focus)

        self.grid_toggle.toggled.connect(self.view.set_show_grid)
        self.groups_toggle.toggled.connect(self.groups_panel.setVisible)
        self.edit_close_btn.clicked.connect(lambda: self.set_edit_panel_visible(False))
        self.edit_image_tool_add_btn.clicked.connect(
            lambda: self.show_tool_add_menu(
                self.edit_image_tool_add_btn.mapToGlobal(
                    QtCore.QPoint(0, self.edit_image_tool_add_btn.height())
                )
            )
        )

        self._bind_slider_to_input(self.edit_exr_gamma_slider, self.edit_exr_gamma_input, 10.0)
        self._bind_slider_to_input(self.edit_image_adjust_brightness_slider, self.edit_image_adjust_brightness_value, 100.0)
        self._bind_slider_to_input(self.edit_image_adjust_contrast_slider, self.edit_image_adjust_contrast_value, 100.0)
        self._bind_slider_to_input(self.edit_image_adjust_saturation_slider, self.edit_image_adjust_saturation_value, 100.0)
        self._bind_slider_to_input(self.edit_image_vibrance_slider, self.edit_image_vibrance_value, 100.0)
        self._bind_slider_to_input(self.edit_crop_left_slider, self.edit_crop_left_value, 1.0)
        self._bind_slider_to_input(self.edit_crop_right_slider, self.edit_crop_right_value, 1.0)
        self._bind_slider_to_input(self.edit_crop_top_slider, self.edit_crop_top_value, 1.0)
        self._bind_slider_to_input(self.edit_crop_bottom_slider, self.edit_crop_bottom_value, 1.0)

        self._undo_shortcut = QtGui.QShortcut(QtGui.QKeySequence.StandardKey.Undo, self)
        self._undo_shortcut.activated.connect(self._on_undo)
        self._redo_shortcut = QtGui.QShortcut(QtGui.QKeySequence.StandardKey.Redo, self)
        self._redo_shortcut.activated.connect(self._on_redo)
        self._exit_focus_shortcut = QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key.Key_Escape), self)
        self._exit_focus_shortcut.setContext(QtCore.Qt.ShortcutContext.ApplicationShortcut)
        self._exit_focus_shortcut.activated.connect(self._on_exit_focus)
        self._tool_add_shortcut = QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key.Key_Tab), self.view)
        self._tool_add_shortcut.setContext(QtCore.Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._tool_add_shortcut.activated.connect(lambda: self.show_tool_add_menu(QtGui.QCursor.pos()))

        footer = QtWidgets.QHBoxLayout()
        layout.addLayout(footer)
        self.hint_label = QtWidgets.QLabel(
            "Tip: Right-click for add/group, drag items, wheel to zoom, Ctrl+drag to scale, middle mouse to pan, Del to remove."
        )
        self.hint_label.setStyleSheet(muted_text_style())
        footer.addWidget(self.hint_label, 1)

        # Bottom timeline bar (for focus mode video editing)
        self.edit_timeline_bar = QtWidgets.QFrame()
        self.edit_timeline_bar.setStyleSheet(subtle_panel_frame_style(bg_key="app_bg"))
        self.edit_timeline_bar.setVisible(False)
        timeline_layout = QtWidgets.QVBoxLayout(self.edit_timeline_bar)
        timeline_layout.setContentsMargins(10, 6, 10, 6)
        timeline_layout.setSpacing(6)
        timeline_title = QtWidgets.QLabel("Timeline")
        timeline_title.setStyleSheet(muted_text_style())
        timeline_layout.addWidget(timeline_title, 0)
        self.edit_timeline = _TimelineWidget()
        timeline_layout.addWidget(self.edit_timeline, 0)
        timeline_actions = QtWidgets.QHBoxLayout()
        self.edit_timeline_play_btn = QtWidgets.QPushButton("Play")
        self.edit_timeline_frame_label = QtWidgets.QLabel("Frame: 0")
        self.edit_timeline_frame_label.setStyleSheet(muted_text_style())
        self.edit_timeline_split_btn = QtWidgets.QPushButton("Split")
        self.edit_timeline_export_btn = QtWidgets.QPushButton("Export Segment")
        timeline_actions.addWidget(self.edit_timeline_play_btn, 0)
        timeline_actions.addWidget(self.edit_timeline_frame_label, 0)
        timeline_actions.addWidget(self.edit_timeline_split_btn, 0)
        timeline_actions.addWidget(self.edit_timeline_export_btn, 0)
        timeline_actions.addStretch(1)
        timeline_layout.addLayout(timeline_actions, 0)
        layout.insertWidget(layout.count() - 1, self.edit_timeline_bar, 0)
        self._position_edit_overlay()

    def set_edit_panel_visible(self, visible: bool) -> None:
        self.edit_panel.setVisible(bool(visible))
        self.focus_exit_btn.setVisible(bool(visible))
        if visible:
            self._position_edit_overlay()
            self.edit_panel.raise_()
            self.focus_exit_btn.raise_()

    def _position_edit_overlay(self) -> None:
        if self.edit_panel is None:
            return
        viewport = self.view.viewport()
        top_left = viewport.mapTo(self, QtCore.QPoint(0, 0))
        anchor = QtCore.QRect(top_left, viewport.size())
        inset = 14
        panel_w = min(self.edit_panel.maximumWidth(), max(self.edit_panel.minimumWidth(), 344))
        panel_w = min(panel_w, max(260, anchor.width() - (inset * 2)))
        available_h = max(220, anchor.height() - (inset * 2))
        panel_h = min(available_h, 620)
        x = anchor.right() - panel_w - inset
        y = anchor.top() + inset
        self.edit_panel.setGeometry(x, y, panel_w, panel_h)
        self.focus_exit_btn.adjustSize()
        btn_x = anchor.left() + inset
        btn_y = anchor.top() + inset
        self.focus_exit_btn.move(btn_x, btn_y)

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._position_edit_overlay()
        self._position_loading_overlay()

    def set_loading_overlay(self, visible: bool, detail: str = "Preparing workspace...") -> None:
        self.loading_detail.setText(detail)
        self.loading_overlay.setVisible(bool(visible))
        self._position_loading_overlay()
        if visible:
            self.loading_overlay.raise_()

    def _position_loading_overlay(self) -> None:
        if not hasattr(self, "loading_overlay"):
            return
        width = self.loading_overlay.width()
        height = max(84, self.loading_overlay.sizeHint().height())
        self.loading_overlay.resize(width, height)
        x = max(18, (self.view.width() - width) // 2)
        self.loading_overlay.move(x, 18)

    def show_tool_add_menu(self, global_pos: QtCore.QPoint) -> bool:
        if not self.edit_panel.isVisible():
            return False
        if not self.edit_tool_stack_section.isVisible():
            return False
        if self.edit_image_tool_add_combo.count() <= 0:
            return False
        menu = QtWidgets.QMenu(self)
        menu.setStyleSheet(
            "QMenu {"
            "background: rgba(24, 28, 34, 245);"
            "color: #d8dde5;"
            "border: 1px solid rgba(255,255,255,26);"
            "padding: 8px;"
            "border-radius: 12px;"
            "}"
            "QMenu::item {"
            "padding: 8px 28px 8px 12px;"
            "border-radius: 8px;"
            "margin: 2px 0;"
            "}"
            "QMenu::item:selected {"
            "background: rgba(242,193,78,38);"
            "}"
        )
        for idx in range(self.edit_image_tool_add_combo.count()):
            label = self.edit_image_tool_add_combo.itemText(idx)
            tool_id = self.edit_image_tool_add_combo.itemData(idx)
            action = menu.addAction(f"Add {label}")
            action.setData(tool_id)
        chosen = menu.exec(global_pos)
        if chosen is not None:
            tool_id = chosen.data()
            idx = self.edit_image_tool_add_combo.findData(tool_id)
            if idx >= 0:
                self.edit_image_tool_add_combo.setCurrentIndex(idx)
                self.imageToolAddRequested.emit(str(tool_id))
        return True

    def set_edit_preview_visible(self, visible: bool) -> None:
        self.edit_preview_stack.setVisible(bool(visible))

    def set_timeline_bar_visible(self, visible: bool) -> None:
        self.edit_timeline_bar.setVisible(bool(visible))

    def set_edit_panel_content(
        self,
        title: str,
        info_lines: list[str],
        list_items: Optional[list[str]] = None,
        footer: str = "",
    ) -> None:
        self.edit_title.setText(title)
        self.edit_info.setText("\n".join([line for line in info_lines if line]))
        self.edit_info.setVisible(bool(self.edit_info.text().strip()))
        self.edit_list.clear()
        if list_items:
            self.edit_list.addItems(list_items)
            self.edit_list.setVisible(True)
        else:
            self.edit_list.setVisible(False)
        self.edit_footer.setText(footer)
        self.edit_footer.setVisible(bool(str(footer).strip()))
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
        self.edit_exr_gamma_input.setVisible(bool(visible))

    def current_exr_gamma(self) -> float:
        return float(self.edit_exr_gamma_slider.value()) / 10.0

    def current_exr_srgb_enabled(self) -> bool:
        return bool(self.edit_exr_srgb_check.isChecked())

    def set_exr_gamma_label(self, gamma: float) -> None:
        self.edit_exr_gamma_label.setText(f"Gamma: {gamma:.1f}")
        self._set_spinbox_value(self.edit_exr_gamma_input, gamma)

    def _set_spinbox_value(self, spinbox: QtWidgets.QDoubleSpinBox, value: float) -> None:
        spinbox.blockSignals(True)
        spinbox.setValue(float(value))
        spinbox.blockSignals(False)

    def _set_slider_value(self, slider: QtWidgets.QSlider, value: float) -> None:
        target = int(round(float(value)))
        if slider.value() != target:
            slider.setValue(target)

    def _bind_slider_to_input(
        self,
        slider: QtWidgets.QSlider,
        spinbox: QtWidgets.QDoubleSpinBox,
        scale: float,
    ) -> None:
        factor = float(scale) if abs(float(scale)) > 1e-9 else 1.0
        slider.valueChanged.connect(
            lambda raw_value, current_spinbox=spinbox, current_factor=factor: self._set_spinbox_value(
                current_spinbox,
                float(raw_value) / current_factor,
            )
        )
        spinbox.valueChanged.connect(
            lambda raw_value, current_slider=slider, current_factor=factor: self._set_slider_value(
                current_slider,
                float(raw_value) * current_factor,
            )
        )

    def set_image_adjust_controls_visible(self, visible: bool) -> None:
        controls = [
            self.edit_tool_stack_section,
            self.edit_image_tools_label,
            self.edit_image_tool_empty,
            self.edit_image_tool_list,
            self.edit_image_tool_add_btn,
            self.edit_image_tool_up_btn,
            self.edit_image_tool_down_btn,
            self.edit_image_adjust_label,
            self.edit_image_adjust_brightness_title,
            self.edit_image_adjust_brightness_slider,
            self.edit_image_adjust_brightness_value,
            self.edit_image_adjust_contrast_title,
            self.edit_image_adjust_contrast_slider,
            self.edit_image_adjust_contrast_value,
            self.edit_image_adjust_saturation_title,
            self.edit_image_adjust_saturation_slider,
            self.edit_image_adjust_saturation_value,
            self.edit_image_vibrance_title,
            self.edit_image_vibrance_slider,
            self.edit_image_vibrance_value,
            self.edit_crop_label,
            self.edit_crop_left_title,
            self.edit_crop_left_slider,
            self.edit_crop_left_value,
            self.edit_crop_right_title,
            self.edit_crop_right_slider,
            self.edit_crop_right_value,
            self.edit_crop_top_title,
            self.edit_crop_top_slider,
            self.edit_crop_top_value,
            self.edit_crop_bottom_title,
            self.edit_crop_bottom_slider,
            self.edit_crop_bottom_value,
            self.edit_image_adjust_reset_btn,
        ]
        for widget in controls:
            widget.setVisible(bool(visible))
        self.edit_image_tool_add_combo.setVisible(False)
        if visible:
            self.set_active_image_tool_panel("")

    def _image_tool_panel_widgets(self) -> dict[str, list[QtWidgets.QWidget]]:
        return {
            "bcs": [
                self.edit_image_adjust_label,
                self.edit_image_adjust_brightness_title,
                self.edit_image_adjust_brightness_slider,
                self.edit_image_adjust_brightness_value,
                self.edit_image_adjust_contrast_title,
                self.edit_image_adjust_contrast_slider,
                self.edit_image_adjust_contrast_value,
                self.edit_image_adjust_saturation_title,
                self.edit_image_adjust_saturation_slider,
                self.edit_image_adjust_saturation_value,
            ],
            "vibrance": [
                self.edit_image_vibrance_title,
                self.edit_image_vibrance_slider,
                self.edit_image_vibrance_value,
            ],
            "crop": [
                self.edit_crop_label,
                self.edit_crop_left_title,
                self.edit_crop_left_slider,
                self.edit_crop_left_value,
                self.edit_crop_right_title,
                self.edit_crop_right_slider,
                self.edit_crop_right_value,
                self.edit_crop_top_title,
                self.edit_crop_top_slider,
                self.edit_crop_top_value,
                self.edit_crop_bottom_title,
                self.edit_crop_bottom_slider,
                self.edit_crop_bottom_value,
            ],
        }

    def set_image_tool_panel_visible(self, panel: str, visible: bool) -> None:
        for widget in self._image_tool_panel_widgets().get(str(panel or "").strip().lower(), []):
            widget.setVisible(bool(visible))

    def set_active_image_tool_panel(self, panel: str) -> None:
        key = str(panel or "").strip().lower()
        for panel_id in self._image_tool_panel_widgets():
            self.set_image_tool_panel_visible(panel_id, panel_id == key)

    def current_image_brightness(self) -> float:
        return float(self.edit_image_adjust_brightness_slider.value()) / 100.0

    def current_image_contrast(self) -> float:
        return float(self.edit_image_adjust_contrast_slider.value()) / 100.0

    def current_image_saturation(self) -> float:
        return float(self.edit_image_adjust_saturation_slider.value()) / 100.0

    def set_image_adjust_labels(self, brightness: float, contrast: float, saturation: float) -> None:
        self._set_spinbox_value(self.edit_image_adjust_brightness_value, brightness)
        self._set_spinbox_value(self.edit_image_adjust_contrast_value, contrast)
        self._set_spinbox_value(self.edit_image_adjust_saturation_value, saturation)

    def set_image_vibrance_value(self, amount: float) -> None:
        self.edit_image_vibrance_slider.blockSignals(True)
        self.edit_image_vibrance_slider.setValue(int(round(float(amount) * 100.0)))
        self.edit_image_vibrance_slider.blockSignals(False)
        self._set_spinbox_value(self.edit_image_vibrance_value, float(amount))

    def current_image_vibrance(self) -> float:
        return float(self.edit_image_vibrance_slider.value()) / 100.0

    def set_image_vibrance_visible(self, visible: bool) -> None:
        self.set_image_tool_panel_visible("vibrance", visible)

    def set_image_crop_visible(self, visible: bool) -> None:
        self.set_image_tool_panel_visible("crop", visible)

    def set_image_crop_values(self, left: float, top: float, right: float, bottom: float) -> None:
        self.edit_crop_left_slider.blockSignals(True)
        self.edit_crop_top_slider.blockSignals(True)
        self.edit_crop_right_slider.blockSignals(True)
        self.edit_crop_bottom_slider.blockSignals(True)
        self.edit_crop_left_slider.setValue(int(round(float(left) * 100.0)))
        self.edit_crop_top_slider.setValue(int(round(float(top) * 100.0)))
        self.edit_crop_right_slider.setValue(int(round(float(right) * 100.0)))
        self.edit_crop_bottom_slider.setValue(int(round(float(bottom) * 100.0)))
        self.edit_crop_left_slider.blockSignals(False)
        self.edit_crop_top_slider.blockSignals(False)
        self.edit_crop_right_slider.blockSignals(False)
        self.edit_crop_bottom_slider.blockSignals(False)
        self._set_spinbox_value(self.edit_crop_left_value, int(round(float(left) * 100.0)))
        self._set_spinbox_value(self.edit_crop_top_value, int(round(float(top) * 100.0)))
        self._set_spinbox_value(self.edit_crop_right_value, int(round(float(right) * 100.0)))
        self._set_spinbox_value(self.edit_crop_bottom_value, int(round(float(bottom) * 100.0)))

    def current_image_crop_settings(self) -> tuple[float, float, float, float]:
        return (
            float(self.edit_crop_left_slider.value()) / 100.0,
            float(self.edit_crop_top_slider.value()) / 100.0,
            float(self.edit_crop_right_slider.value()) / 100.0,
            float(self.edit_crop_bottom_slider.value()) / 100.0,
        )

    def set_image_bcs_controls_visible(self, visible: bool) -> None:
        self.set_image_tool_panel_visible("bcs", visible)

    def set_image_tool_add_options(self, options: list[tuple[str, str]]) -> None:
        self.edit_image_tool_add_combo.blockSignals(True)
        self.edit_image_tool_add_combo.clear()
        for label, tool_id in options:
            self.edit_image_tool_add_combo.addItem(str(label), str(tool_id))
        self.edit_image_tool_add_combo.blockSignals(False)

    def current_image_tool_add_id(self) -> str:
        data = self.edit_image_tool_add_combo.currentData()
        return str(data) if data is not None else ""

    def set_image_tool_stack_items(self, items: list[tuple[str, bool]], selected_index: int = -1) -> None:
        self.edit_image_tool_list.blockSignals(True)
        self.edit_image_tool_list.clear()
        for idx, (label, enabled) in enumerate(items):
            item = QtWidgets.QListWidgetItem()
            item.setSizeHint(QtCore.QSize(0, 32))
            self.edit_image_tool_list.addItem(item)
            row = _ToolStackRow(label, muted=not enabled)
            row.removeRequested.connect(lambda _checked=False, row_idx=idx: self.imageToolRemoveRequested.emit(row_idx))
            self.edit_image_tool_list.setItemWidget(item, row)
        has_items = bool(items)
        self.edit_image_tool_list.setVisible(has_items)
        self.edit_image_tool_empty.setVisible(not has_items and self.edit_image_tools_label.isVisible())
        if items and selected_index >= 0 and selected_index < len(items):
            self.edit_image_tool_list.setCurrentRow(int(selected_index))
        elif items:
            self.edit_image_tool_list.setCurrentRow(0)
        row_h = 38
        visible_rows = max(1, min(3, len(items)))
        frame = 6
        self.edit_image_tool_list.setMaximumHeight(frame + (row_h * visible_rows))
        can_reorder = len(items) > 1
        self.edit_image_tool_up_btn.setVisible(can_reorder)
        self.edit_image_tool_down_btn.setVisible(can_reorder)
        self.edit_image_tool_list.blockSignals(False)
        self._refresh_tool_stack_row_selection(self.edit_image_tool_list.currentRow())

    def current_image_tool_stack_index(self) -> int:
        return int(self.edit_image_tool_list.currentRow())

    def _refresh_tool_stack_row_selection(self, current_row: int) -> None:
        for idx in range(self.edit_image_tool_list.count()):
            item = self.edit_image_tool_list.item(idx)
            row = self.edit_image_tool_list.itemWidget(item)
            if isinstance(row, _ToolStackRow):
                row.set_selected(idx == int(current_row))

    def set_image_adjust_values(self, brightness: float, contrast: float, saturation: float) -> None:
        self.edit_image_adjust_brightness_slider.blockSignals(True)
        self.edit_image_adjust_contrast_slider.blockSignals(True)
        self.edit_image_adjust_saturation_slider.blockSignals(True)
        self.edit_image_adjust_brightness_slider.setValue(int(round(float(brightness) * 100.0)))
        self.edit_image_adjust_contrast_slider.setValue(int(round(float(contrast) * 100.0)))
        self.edit_image_adjust_saturation_slider.setValue(int(round(float(saturation) * 100.0)))
        self.edit_image_adjust_brightness_slider.blockSignals(False)
        self.edit_image_adjust_contrast_slider.blockSignals(False)
        self.edit_image_adjust_saturation_slider.blockSignals(False)
        self.set_image_adjust_labels(brightness, contrast, saturation)

    def current_image_tool_panel_state(self, panel: str) -> dict[str, float]:
        key = str(panel or "").strip().lower()
        spec = tool_spec_for_panel(key)
        if spec is None:
            return {}
        values: dict[str, float] = {}
        for control in getattr(spec, "ui_controls", ()):
            control_key = str(getattr(control, "key", "") or "").strip()
            if not control_key:
                continue
            current = self._current_image_tool_control_value(control_key)
            if current is not None:
                values[control_key] = current
        return values

    def set_image_tool_panel_state(self, panel: str, state: dict[str, object]) -> None:
        key = str(panel or "").strip().lower()
        values = dict(state) if isinstance(state, dict) else {}
        spec = tool_spec_for_panel(key)
        if spec is None:
            return
        merged = default_panel_state(key)
        merged.update(values)
        for control in getattr(spec, "ui_controls", ()):
            control_key = str(getattr(control, "key", "") or "").strip()
            if not control_key:
                continue
            self._set_image_tool_control_value(control_key, merged.get(control_key, getattr(control, "minimum", 0.0)))

    def _current_image_tool_control_value(self, control_key: str) -> float | None:
        key = str(control_key or "").strip().lower()
        if key == "brightness":
            return self.current_image_brightness()
        if key == "contrast":
            return self.current_image_contrast()
        if key == "saturation":
            return self.current_image_saturation()
        if key == "amount":
            return self.current_image_vibrance()
        crop = {
            "left": float(self.edit_crop_left_slider.value()) / 100.0,
            "top": float(self.edit_crop_top_slider.value()) / 100.0,
            "right": float(self.edit_crop_right_slider.value()) / 100.0,
            "bottom": float(self.edit_crop_bottom_slider.value()) / 100.0,
        }
        return crop.get(key)

    def image_tool_control_slider(self, control_key: str) -> QtWidgets.QSlider | None:
        key = str(control_key or "").strip().lower()
        sliders = {
            "brightness": self.edit_image_adjust_brightness_slider,
            "contrast": self.edit_image_adjust_contrast_slider,
            "saturation": self.edit_image_adjust_saturation_slider,
            "amount": self.edit_image_vibrance_slider,
            "left": self.edit_crop_left_slider,
            "top": self.edit_crop_top_slider,
            "right": self.edit_crop_right_slider,
            "bottom": self.edit_crop_bottom_slider,
        }
        return sliders.get(key)

    def _set_image_tool_control_value(self, control_key: str, value: object) -> None:
        key = str(control_key or "").strip().lower()
        try:
            numeric = float(value)
        except Exception:
            numeric = 0.0
        if key == "brightness":
            self.edit_image_adjust_brightness_slider.blockSignals(True)
            self.edit_image_adjust_brightness_slider.setValue(int(round(numeric * 100.0)))
            self.edit_image_adjust_brightness_slider.blockSignals(False)
            self._set_spinbox_value(self.edit_image_adjust_brightness_value, numeric)
            return
        if key == "contrast":
            self.edit_image_adjust_contrast_slider.blockSignals(True)
            self.edit_image_adjust_contrast_slider.setValue(int(round(numeric * 100.0)))
            self.edit_image_adjust_contrast_slider.blockSignals(False)
            self._set_spinbox_value(self.edit_image_adjust_contrast_value, numeric)
            return
        if key == "saturation":
            self.edit_image_adjust_saturation_slider.blockSignals(True)
            self.edit_image_adjust_saturation_slider.setValue(int(round(numeric * 100.0)))
            self.edit_image_adjust_saturation_slider.blockSignals(False)
            self._set_spinbox_value(self.edit_image_adjust_saturation_value, numeric)
            return
        if key == "amount":
            self.set_image_vibrance_value(numeric)
            return
        crop_widgets = {
            "left": (self.edit_crop_left_slider, self.edit_crop_left_value),
            "top": (self.edit_crop_top_slider, self.edit_crop_top_value),
            "right": (self.edit_crop_right_slider, self.edit_crop_right_value),
            "bottom": (self.edit_crop_bottom_slider, self.edit_crop_bottom_value),
        }
        widgets = crop_widgets.get(key)
        if widgets is None:
            return
        slider, label = widgets
        slider.blockSignals(True)
        slider.setValue(int(round(numeric * 100.0)))
        slider.blockSignals(False)
        self._set_spinbox_value(label, int(round(numeric * 100.0)))

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
        if self._controller is not None and hasattr(self._controller, "show_groups_tree_context_menu"):
            handled = self._controller.show_groups_tree_context_menu(pos)
            if handled:
                return
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

    def _on_exit_focus(self) -> None:
        if self._controller is not None and hasattr(self._controller, "exit_focus_mode"):
            self._controller.exit_focus_mode()

