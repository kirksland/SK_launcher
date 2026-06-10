from __future__ import annotations

from pathlib import Path

from PySide6 import QtGui, QtWidgets

from core.board_scene.dialogs import BoardSlideshowDialog
from core.board_scene.items import BoardImageItem


class BoardSlideshowController:
    """Owns read-only slideshow playback for selected board images."""

    def __init__(self, board_controller: object) -> None:
        self.board = board_controller
        self.w = board_controller.w
        self._dialog: BoardSlideshowDialog | None = None

    def start_selected_images(self) -> None:
        board = self.board
        if board._project_root is None:
            board._notify("Select a project first.")
            return
        image_items = [
            item
            for item in board._scene.selectedItems()
            if isinstance(item, BoardImageItem)
        ]
        if len(image_items) < 2:
            board._notify("Select at least 2 images for a slideshow.")
            return

        paths = []
        assets_dir = board._project_root / ".skyforge_board_assets"
        for item in image_items:
            filename = str(item.data(1) or "").strip()
            if not filename:
                continue
            path = assets_dir / filename
            if path.exists() and path.is_file():
                paths.append(path)
        if len(paths) < 2:
            board._notify("Selected images were not found on disk.")
            return

        dialog = BoardSlideshowDialog(paths, self._load_pixmap, self.w)
        self._dialog = dialog
        dialog.finished.connect(self._on_dialog_finished)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _load_pixmap(self, path: Path) -> QtGui.QPixmap:
        loader = getattr(self.board, "_get_display_pixmap", None)
        if callable(loader):
            return loader(path, max_dim=1920)
        return QtGui.QPixmap(str(path))

    def _on_dialog_finished(self) -> None:
        self._dialog = None
