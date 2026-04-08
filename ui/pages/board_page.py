from __future__ import annotations

from typing import Optional
import re
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets


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

from ui.utils.styles import PALETTE, border_only_style, muted_text_style, subtle_panel_frame_style, title_style, tree_panel_style


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
                self._scaling = True
                self._scale_items = list(items)
                center = QtCore.QPointF()
                for item in self._scale_items:
                    center += item.sceneBoundingRect().center()
                center /= max(1, len(self._scale_items))
                self._scale_start_center = center
                self._scale_start_dist = max(1.0, QtCore.QLineF(center, self.mapToScene(event.pos())).length())
                self._scale_start_values = []
                self._scale_start_positions = []
                for item in self._scale_items:
                    self._scale_start_values.append(item.scale())
                    self._scale_start_positions.append(item.pos())
                    overlay = QtWidgets.QGraphicsRectItem(item.sceneBoundingRect())
                    overlay.setPen(QtGui.QPen(QtGui.QColor("#c6ccd6"), 1, QtCore.Qt.PenStyle.DashLine))
                    overlay.setBrush(QtCore.Qt.BrushStyle.NoBrush)
                    overlay.setZValue(10_000)
                    self.scene().addItem(overlay)
                    self._scale_overlays.append(overlay)
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
            current_dist = max(
                1.0,
                QtCore.QLineF(self._scale_start_center, self.mapToScene(event.pos())).length(),
            )
            factor = current_dist / max(1.0, self._scale_start_dist)
            for idx, item in enumerate(self._scale_items):
                start_scale = self._scale_start_values[idx] if idx < len(self._scale_start_values) else item.scale()
                start_pos = self._scale_start_positions[idx] if idx < len(self._scale_start_positions) else item.pos()
                item.setScale(max(0.05, min(8.0, start_scale * factor)))
                offset = start_pos - self._scale_start_center
                item.setPos(self._scale_start_center + offset * factor)
                if idx < len(self._scale_overlays):
                    self._scale_overlays[idx].setRect(item.sceneBoundingRect())
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
            if controller is not None and hasattr(controller, "open_media_item"):
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

        self.grid_toggle.toggled.connect(self.view.set_show_grid)
        self.groups_toggle.toggled.connect(self.groups_panel.setVisible)

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

