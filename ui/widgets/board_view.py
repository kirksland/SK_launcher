from __future__ import annotations

from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets


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
                    controller.begin_scene_interaction(kind="scale_selection_wheel", history_label="Scale selection")
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
                if event.modifiers() & QtCore.Qt.KeyboardModifier.ControlModifier:
                    controller.begin_scene_interaction(kind="scale_selection_drag", history_label="Scale selection")
                else:
                    controller.begin_scene_interaction(kind="move_selection", history_label="Move selection")
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
