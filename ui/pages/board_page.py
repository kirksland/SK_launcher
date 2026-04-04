from __future__ import annotations

from typing import Optional
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets


class BoardView(QtWidgets.QGraphicsView):
    def __init__(self, scene: QtWidgets.QGraphicsScene, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(scene, parent)
        self.setRenderHints(
            QtGui.QPainter.RenderHint.Antialiasing
            | QtGui.QPainter.RenderHint.SmoothPixmapTransform
            | QtGui.QPainter.RenderHint.TextAntialiasing
        )
        self.setViewportUpdateMode(QtWidgets.QGraphicsView.ViewportUpdateMode.BoundingRectViewportUpdate)
        self.setDragMode(QtWidgets.QGraphicsView.DragMode.RubberBandDrag)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.setTransformationAnchor(QtWidgets.QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QtWidgets.QGraphicsView.ViewportAnchor.AnchorUnderMouse)
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
                return
        factor = 1.2 if event.angleDelta().y() > 0 else 0.85
        self.scale(factor, factor)

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:  # type: ignore[override]
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self._move_start_positions = {id(i): i.pos() for i in self.scene().selectedItems()}
        if event.button() == QtCore.Qt.MouseButton.LeftButton and event.modifiers() & QtCore.Qt.KeyboardModifier.ControlModifier:
            items = [i for i in self.scene().selectedItems() if i.data(0) in ("image", "note")]
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
            return
        if self._panning and event.button() in (
            QtCore.Qt.MouseButton.MiddleButton,
            QtCore.Qt.MouseButton.LeftButton,
        ):
            self._panning = False
            self.setDragMode(QtWidgets.QGraphicsView.DragMode.RubberBandDrag)
            self.setCursor(QtCore.Qt.CursorShape.ArrowCursor)
            event.accept()
            return
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            moved = []
            for item in self.scene().selectedItems():
                start = self._move_start_positions.get(id(item))
                if start is not None and (item.pos() - start).manhattanLength() > 2:
                    moved.append(item)
            if moved:
                parent = self.parent()
                controller = getattr(parent, "_controller", None)
                if controller is not None and hasattr(controller, "handle_item_drop"):
                    controller.handle_item_drop(moved)
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QtGui.QMouseEvent) -> None:  # type: ignore[override]
        item = self.itemAt(event.pos())
        note_item = None
        group_item = None
        while item is not None:
            if item.data(0) == "note":
                note_item = item
                break
            if item.data(0) == "group":
                group_item = item
                break
            item = item.parentItem()
        if group_item is not None:
            parent = self.parent()
            controller = getattr(parent, "_controller", None)
            if controller is not None and hasattr(controller, "select_group_members"):
                controller.select_group_members(group_item)
                event.accept()
                return
        if note_item is not None:
            parent = self.parent()
            controller = getattr(parent, "_controller", None)
            if controller is not None and hasattr(controller, "edit_note"):
                controller.edit_note(note_item, global_pos=self.viewport().mapToGlobal(event.pos()))
                event.accept()
                return
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event: QtGui.QContextMenuEvent) -> None:  # type: ignore[override]
        parent = self.parent()
        controller = getattr(parent, "_controller", None)
        if controller is None:
            super().contextMenuEvent(event)
            return
        menu = QtWidgets.QMenu(self)
        add_image = menu.addAction("Add Image…")
        add_note = menu.addAction("Add Note")
        add_group = menu.addAction("Group Selection")
        ungroup = menu.addAction("Ungroup")
        has_group = any(getattr(i, "data", lambda _k: None)(0) == "group" for i in self.scene().selectedItems())
        ungroup.setEnabled(has_group)
        action = menu.exec(event.globalPos())
        if action == add_image and hasattr(controller, "add_image"):
            controller.add_image()
        elif action == add_note and hasattr(controller, "add_note_at"):
            controller.add_note_at(self.mapToScene(event.pos()))
        elif action == add_group and hasattr(controller, "add_group"):
            controller.add_group()
        elif action == ungroup and hasattr(controller, "ungroup_selected"):
            controller.ungroup_selected()

    def set_show_grid(self, enabled: bool) -> None:
        self._show_grid = enabled
        self.viewport().update()

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:  # type: ignore[override]
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
            return
        super().keyPressEvent(event)

    def dragEnterEvent(self, event: QtGui.QDragEnterEvent) -> None:  # type: ignore[override]
        if event.mimeData().hasUrls():
            event.setDropAction(QtCore.Qt.DropAction.CopyAction)
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event: QtGui.QDragMoveEvent) -> None:  # type: ignore[override]
        if event.mimeData().hasUrls():
            event.setDropAction(QtCore.Qt.DropAction.CopyAction)
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event: QtGui.QDropEvent) -> None:  # type: ignore[override]
        if event.mimeData().hasUrls() and hasattr(self.parent(), "handle_external_drop"):
            self.parent().handle_external_drop(event)
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
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        header.addWidget(title, 0)

        self.project_label = QtWidgets.QLabel("No project selected")
        self.project_label.setStyleSheet("color: #9aa3ad;")
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

        self.add_image_btn = QtWidgets.QPushButton("Add Image")
        header.addWidget(self.add_image_btn, 0)
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
        self.view = BoardView(self.scene, self)
        self.view.setStyleSheet("border: 1px solid #14171c;")
        layout.addWidget(self.view, 1)

        self.grid_toggle.toggled.connect(self.view.set_show_grid)

        footer = QtWidgets.QHBoxLayout()
        layout.addLayout(footer)
        self.hint_label = QtWidgets.QLabel(
            "Tip: Right-click for add/group, drag items, wheel to zoom, Ctrl+drag to scale, middle mouse to pan, Del to remove."
        )
        self.hint_label.setStyleSheet("color: #9aa3ad;")
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
        for url in event.mimeData().urls():
            local_path = Path(url.toLocalFile())
            print(f"[BOARD] URL -> {local_path}")
            if local_path.exists():
                item = controller.add_image_from_path(local_path, scene_pos=scene_pos)
                if item is not None:
                    controller.try_add_item_to_group(item, scene_pos)
            else:
                print(f"[BOARD] Missing path: {local_path}")

    def set_controller(self, controller) -> None:
        self._controller = controller

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
