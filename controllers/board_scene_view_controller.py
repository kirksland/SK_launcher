from __future__ import annotations

from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

from core.board_scene.groups import collapse_items_by_group
from core.board_scene.items import BoardGroupItem, BoardImageItem, BoardSequenceItem, BoardVideoItem


class BoardSceneViewController:
    """Owns Board scene workspace, layout, reveal, and view quality behavior."""

    def __init__(self, board_controller: object) -> None:
        self.board = board_controller
        self.w = board_controller.w

    def fit_view(self) -> None:
        board = self.board
        self.refresh_scene_workspace()
        rect = board._scene.itemsBoundingRect()
        if rect.isNull():
            return
        self.w.board_page.view.fitInView(rect.adjusted(-80, -80, 80, 80), QtCore.Qt.AspectRatioMode.KeepAspectRatio)

    def current_view_scene_center(self) -> QtCore.QPointF:
        board = self.board
        view = self.w.board_page.view
        viewport_rect = view.viewport().rect()
        if viewport_rect.isNull():
            return board._scene.sceneRect().center()
        return view.mapToScene(viewport_rect.center())

    def workspace_item_bounds(self) -> QtCore.QRectF:
        board = self.board
        rect = QtCore.QRectF()
        for item in board._scene.items():
            if item is board._focus_overlay:
                continue
            kind = item.data(0)
            if kind not in {"image", "video", "sequence", "note", "group"}:
                continue
            rect = rect.united(item.sceneBoundingRect())
        return rect

    def refresh_scene_workspace(self, extra_rect: Optional[QtCore.QRectF] = None) -> None:
        board = self.board
        workspace = self.workspace_item_bounds()
        if extra_rect is not None and extra_rect.isValid() and not extra_rect.isNull():
            workspace = workspace.united(extra_rect)
        view_pad = 4000.0
        min_half_extent = 5000.0
        center = self.current_view_scene_center()
        viewport_rect = QtCore.QRectF(
            center.x() - view_pad,
            center.y() - view_pad,
            view_pad * 2.0,
            view_pad * 2.0,
        )
        base_rect = QtCore.QRectF(
            -min_half_extent,
            -min_half_extent,
            min_half_extent * 2.0,
            min_half_extent * 2.0,
        )
        if workspace.isNull():
            workspace = viewport_rect
        else:
            workspace = workspace.united(viewport_rect)
        workspace = workspace.united(base_rect).adjusted(-view_pad, -view_pad, view_pad, view_pad)
        if workspace.isValid() and not workspace.isNull():
            board._scene.setSceneRect(workspace)

    def reveal_scene_items(self, items: list[QtWidgets.QGraphicsItem]) -> None:
        board = self.board
        if not items:
            return
        rect = QtCore.QRectF()
        for item in items:
            if item is None or item.scene() is not board._scene:
                continue
            rect = rect.united(item.sceneBoundingRect())
        if rect.isNull():
            return
        self.refresh_scene_workspace(extra_rect=rect)
        view = self.w.board_page.view
        margins = 80
        view.ensureVisible(rect.adjusted(-margins, -margins, margins, margins))

    def layout_selection_grid(self, *, commit: bool = True) -> None:
        board = self.board
        items = [i for i in board._scene.selectedItems() if isinstance(i, QtWidgets.QGraphicsItem)]
        if not items:
            items = [
                i
                for i in board._scene.items()
                if isinstance(i, (BoardImageItem, BoardVideoItem, BoardSequenceItem))
            ]
        if not items:
            board._notify("Select items to layout.")
            return

        items = collapse_items_by_group(items, board._groups())

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
        if commit:
            board._commit_scene_mutation(
                kind="layout_selection_grid",
                history_label="Layout selection",
                history=True,
                update_groups=True,
            )

    def update_view_quality(self) -> None:
        board = self.board
        view = self.w.board_page.view
        item_count = sum(
            1
            for i in board._scene.items()
            if i.data(0) in ("image", "note", "video", "sequence", "group")
        )
        low_quality = item_count >= 200
        if low_quality == board._low_quality:
            return
        board._low_quality = low_quality
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
        board = self.board
        view = self.w.board_page.view
        visible_rect = view.mapToScene(view.viewport().rect()).boundingRect().adjusted(-200, -200, 200, 200)
        zoom = view.transform().m11()
        want_full = zoom >= 0.45
        new_visible: set[int] = set()
        for item in board._scene.items(visible_rect):
            if isinstance(item, BoardImageItem):
                new_visible.add(id(item))
                item.set_quality("full" if want_full else "proxy")
        for item_id in list(board._visible_images - new_visible):
            for item in board._scene.items():
                if id(item) == item_id and isinstance(item, BoardImageItem):
                    item.set_quality("proxy")
                    break
        board._visible_images = new_visible
