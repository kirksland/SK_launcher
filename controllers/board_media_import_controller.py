from __future__ import annotations

import os
import shutil
import subprocess
import urllib.request
import uuid
from pathlib import Path
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

from core.board_edit.workers import VideoToSequenceWorker
from core.board_scene.items import BoardImageItem, BoardSequenceItem, BoardVideoItem
from core.houdini_env import build_houdini_env

try:
    import cv2  # type: ignore
except Exception:  # pragma: no cover - optional video backend
    cv2 = None  # type: ignore


class BoardMediaImportController:
    """Owns media import and conversion actions for the Board."""

    def __init__(self, board_controller: object) -> None:
        self.board = board_controller
        self.w = board_controller.w

    def add_image(self) -> None:
        board = self.board
        if not board._project_root:
            board._notify("Select a project first.")
            return
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self.w,
            "Add Image",
            str(board._project_root),
            "Images (*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.exr)",
        )
        if not path:
            return
        self.add_image_from_path(Path(path))

    def add_image_from_path(
        self,
        src: Path,
        scene_pos: Optional[QtCore.QPointF] = None,
        *,
        commit: bool = True,
    ) -> Optional[QtWidgets.QGraphicsPixmapItem]:
        board = self.board
        if not board._project_root:
            print("[BOARD] No project root set")
            return None
        if not src.is_file():
            print(f"[BOARD] Not a file: {src}")
            return None
        assets_dir = board._project_root / ".skyforge_board_assets"
        assets_dir.mkdir(parents=True, exist_ok=True)
        dest = assets_dir / src.name
        print(f"[BOARD] Import image: {src} -> {dest}")
        if src.resolve() != dest.resolve():
            try:
                shutil.copy2(src, dest)
            except Exception as exc:
                print(f"[BOARD] Copy failed: {exc}")
                board._notify(f"Failed to copy image:\n{exc}")
                return None
        item = BoardImageItem(board, dest)
        if item.boundingRect().isNull():
            print("[BOARD] Pixmap is null")
            board._notify("Failed to load image.")
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
            scene_pos = board._current_view_scene_center()
        item.setPos(scene_pos)
        self._scale_large_item(item)
        board._scene.addItem(item)
        if commit:
            board._commit_scene_mutation(
                kind="import_image",
                history_label="Import image",
                history=True,
                update_groups=False,
            )
        board._update_view_quality()
        board.update_visible_items()
        return item

    def add_image_from_url(self, url: str, scene_pos: Optional[QtCore.QPointF] = None) -> None:
        board = self.board
        if not board._project_root:
            board._notify("Select a project first.")
            return
        confirm = QtWidgets.QMessageBox.question(
            self.w,
            "Import Web Image",
            f"Download and import this image?\n{url}",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
        )
        if confirm != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        assets_dir = board._project_root / ".skyforge_board_assets"
        assets_dir.mkdir(parents=True, exist_ok=True)
        safe_name = QtCore.QUrl(url).fileName() or f"web_{uuid.uuid4().hex}.png"
        dest = assets_dir / safe_name
        try:
            urllib.request.urlretrieve(url, dest)
        except Exception as exc:
            board._notify(f"Failed to download image:\n{exc}")
            return
        self.add_image_from_path(dest, scene_pos=scene_pos)

    def add_image_from_image_data(self, image_data: object, scene_pos: Optional[QtCore.QPointF] = None) -> None:
        board = self.board
        if not board._project_root:
            board._notify("Select a project first.")
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
            board._notify("Dropped image data is not valid.")
            return
        assets_dir = board._project_root / ".skyforge_board_assets"
        assets_dir.mkdir(parents=True, exist_ok=True)
        dest = assets_dir / f"web_{uuid.uuid4().hex}.png"
        try:
            if not image.save(str(dest), "PNG"):
                board._notify("Failed to save dropped image.")
                return
        except Exception as exc:
            board._notify(f"Failed to save dropped image:\n{exc}")
            return
        self.add_image_from_path(dest, scene_pos=scene_pos)

    def add_video(self) -> None:
        board = self.board
        if not board._project_root:
            board._notify("Select a project first.")
            return
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self.w,
            "Add Video",
            str(board._project_root),
            "Videos (*.mp4 *.mov *.avi *.mkv *.webm)",
        )
        if not path:
            return
        self.add_video_from_path(Path(path))

    def add_video_from_path(
        self,
        src: Path,
        scene_pos: Optional[QtCore.QPointF] = None,
        *,
        commit: bool = True,
    ) -> Optional[QtWidgets.QGraphicsItem]:
        board = self.board
        if not board._project_root:
            print("[BOARD] No project root set")
            return None
        if not src.is_file():
            print(f"[BOARD] Not a file: {src}")
            return None
        assets_dir = board._project_root / ".skyforge_board_assets"
        assets_dir.mkdir(parents=True, exist_ok=True)
        dest = assets_dir / src.name
        print(f"[BOARD] Import video: {src} -> {dest}")
        if src.resolve() != dest.resolve():
            try:
                shutil.copy2(src, dest)
            except Exception as exc:
                print(f"[BOARD] Copy failed: {exc}")
                board._notify(f"Failed to copy video:\n{exc}")
                return None
        item = BoardVideoItem(board, dest)
        if item.boundingRect().isNull():
            board._notify("Failed to load video thumbnail.")
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
            scene_pos = board._current_view_scene_center()
        item.setPos(scene_pos)
        self._scale_large_item(item)
        board._scene.addItem(item)
        if commit:
            board._commit_scene_mutation(
                kind="import_video",
                history_label="Import video",
                history=True,
                update_groups=False,
            )
        board._update_view_quality()
        return item

    def find_iconvert(self) -> Optional[Path]:
        houdini_exe = getattr(self.w, "_houdini_exe", "")
        if not houdini_exe:
            return None
        houdini_path = Path(str(houdini_exe))
        if not houdini_path.exists():
            return None
        iconvert = houdini_path.with_name("iconvert.exe")
        if iconvert.exists():
            return iconvert
        return None

    def convert_picnc_interactive(
        self,
        src_path: Optional[Path] = None,
        scene_pos: Optional[QtCore.QPointF] = None,
        *,
        commit: bool = True,
    ) -> Optional[QtWidgets.QGraphicsPixmapItem]:
        board = self.board
        iconvert = self.find_iconvert()
        if iconvert is None:
            board._notify("iconvert.exe not found. Set Houdini path in Settings.")
            return None
        if src_path is None:
            src_path_str, _ = QtWidgets.QFileDialog.getOpenFileName(
                self.w,
                "Select PICNC",
                "",
                "Houdini PIC (*.picnc *.pic)",
            )
            if not src_path_str:
                return None
            src_path = Path(src_path_str)
        choice = QtWidgets.QMessageBox.question(
            self.w,
            "Convert PICNC",
            "Choose output format:",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
        )
        ext = "jpg" if choice == QtWidgets.QMessageBox.StandardButton.Yes else "exr"
        default_dir = None
        if board._project_root is not None:
            default_dir = board._project_root / ".skyforge_board_assets" / ".converted"
        default_name = src_path.stem + f".{ext}"
        if default_dir is not None:
            try:
                default_dir.mkdir(parents=True, exist_ok=True)
            except Exception:
                default_dir = None
        default_path = str(default_dir / default_name) if default_dir is not None else default_name
        out_path_str, _ = QtWidgets.QFileDialog.getSaveFileName(
            self.w,
            "Save Converted File",
            default_path,
            "Images (*.jpg *.jpeg *.exr)",
        )
        if not out_path_str:
            return None
        out_path = Path(out_path_str)
        try:
            houdini_env = build_houdini_env(
                base_env=os.environ,
                launcher_root=Path(__file__).resolve().parents[1],
            )
            subprocess.check_call([str(iconvert), str(src_path), str(out_path)], env=houdini_env)
        except Exception as exc:
            board._notify(f"iconvert failed:\n{exc}")
            return None
        board._notify(f"Converted: {out_path.name}")
        if board._is_image_file(out_path):
            return self.add_image_from_path(out_path, scene_pos=scene_pos, commit=commit)
        return None

    def add_paths_from_selection(
        self, paths: list[Path], scene_pos: Optional[QtCore.QPointF] = None
    ) -> None:
        board = self.board
        if not board._project_root:
            board._notify("Select a project first.")
            return
        if not paths:
            return
        if scene_pos is None:
            scene_pos = board._current_view_scene_center()
        added = 0
        added_items: list[QtWidgets.QGraphicsItem] = []
        added_images: list[BoardImageItem] = []
        offset = QtCore.QPointF(30.0, 30.0)
        current_pos = QtCore.QPointF(scene_pos)
        for path in paths:
            item = None
            if path.is_file():
                if board._is_video_file(path):
                    item = self.add_video_from_path(path, scene_pos=current_pos, commit=False)
                elif board._is_image_file(path):
                    item = self.add_image_from_path(path, scene_pos=current_pos, commit=False)
                    if isinstance(item, BoardImageItem):
                        added_images.append(item)
                elif board._is_pic_file(path):
                    item = self.convert_picnc_interactive(path, scene_pos=current_pos, commit=False)
                    if isinstance(item, BoardImageItem):
                        added_images.append(item)
            elif path.exists() and path.is_dir():
                item = self.add_sequence_from_dir(path, scene_pos=current_pos, commit=False)
            if item is not None:
                added += 1
                added_items.append(item)
                current_pos = QtCore.QPointF(current_pos.x() + offset.x(), current_pos.y() + offset.y())
        if added == 0:
            board._notify("No supported media found in selection.")
            return
        if added_images:
            prev_selected = list(board._scene.selectedItems())
            for sel in prev_selected:
                sel.setSelected(False)
            for img in added_images:
                img.setSelected(True)
            board.layout_selection_grid(commit=False)
            for img in added_images:
                img.setSelected(False)
            for sel in prev_selected:
                sel.setSelected(True)
        board._commit_scene_mutation(
            kind="import_media_selection",
            history_label="Import media selection",
            history=True,
            save=True,
            reveal_items=added_items,
            update_groups=True,
        )

    def add_sequence(self) -> None:
        board = self.board
        if not board._project_root:
            board._notify("Select a project first.")
            return
        dir_path = QtWidgets.QFileDialog.getExistingDirectory(
            self.w,
            "Add Image Sequence",
            str(board._project_root),
        )
        if not dir_path:
            return
        self.add_sequence_from_dir(Path(dir_path))

    def add_sequence_from_dir(
        self,
        dir_path: Path,
        scene_pos: Optional[QtCore.QPointF] = None,
        *,
        commit: bool = True,
    ) -> Optional[QtWidgets.QGraphicsItem]:
        board = self.board
        if not board._project_root:
            print("[BOARD] No project root set")
            return None
        if not dir_path.exists() or not dir_path.is_dir():
            print(f"[BOARD] Not a directory: {dir_path}")
            return None
        frames = board._sequence_frame_paths(dir_path)
        if not frames:
            board._notify("No image frames found in directory.")
            return None
        item = BoardSequenceItem(board, dir_path)
        if item.boundingRect().isNull():
            board._notify("Failed to load sequence thumbnail.")
            return None
        item.setFlags(
            QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsFocusable
        )
        item.setTransformOriginPoint(item.boundingRect().center())
        item.setData(0, "sequence")
        item.setData(1, board._relative_to_project(dir_path))
        if scene_pos is None:
            scene_pos = board._current_view_scene_center()
        item.setPos(scene_pos)
        self._scale_large_item(item)
        board._scene.addItem(item)
        if commit:
            board._commit_scene_mutation(
                kind="import_sequence",
                history_label="Import sequence",
                history=True,
                update_groups=False,
            )
        board._update_view_quality()
        return item

    def convert_video_to_sequence(self, item: QtWidgets.QGraphicsItem) -> None:
        board = self.board
        if item.data(0) != "video":
            return
        if not board._project_root:
            board._notify("Select a project first.")
            return
        if board._convert_thread is not None:
            board._notify("A conversion is already running.")
            return
        filename = str(item.data(1))
        video_path = board._project_root / ".skyforge_board_assets" / filename
        if not video_path.exists():
            board._notify("Video file not found.")
            return
        out_dir = board._project_root / ".skyforge_board_assets" / f"{video_path.stem}_seq"
        out_dir.mkdir(parents=True, exist_ok=True)
        board._notify("Converting video to sequence...")

        dialog = QtWidgets.QProgressDialog("Converting video...", "Cancel", 0, 100, self.w)
        dialog.setWindowTitle("Video Conversion")
        dialog.setMinimumDuration(200)
        dialog.setValue(0)
        dialog.setWindowModality(QtCore.Qt.WindowModality.WindowModal)
        board._convert_dialog = dialog

        worker = VideoToSequenceWorker(video_path, out_dir)
        thread = QtCore.QThread(self.w)
        worker.moveToThread(thread)

        def _on_progress(current: int, total: int) -> None:
            if board._convert_dialog is None:
                return
            if total > 0:
                percent = int((current / max(1, total)) * 100)
                board._convert_dialog.setValue(min(100, max(0, percent)))
                board._convert_dialog.setLabelText(f"Extracting frames... {current}/{total}")
            else:
                board._convert_dialog.setValue(min(100, current % 100))
                board._convert_dialog.setLabelText(f"Extracting frames... {current}")
            QtWidgets.QApplication.processEvents()

        def _on_finished(success: bool, out_path: object, error: object) -> None:
            if board._convert_dialog is not None:
                board._convert_dialog.reset()
                board._convert_dialog = None
            board._convert_thread = None
            board._convert_worker = None
            if not success:
                board._notify(str(error or "Conversion failed."))
                return
            if not isinstance(out_path, Path):
                board._notify("Conversion failed.")
                return
            scene_pos = item.pos()
            scale = item.scale()
            group = board._find_group_for_item(item)
            board._scene.removeItem(item)
            seq_item = self.add_sequence_from_dir(out_path, scene_pos=scene_pos, commit=False)
            if seq_item is not None:
                seq_item.setScale(scale)
                if group is not None:
                    group.add_member(seq_item)
                    group.update_bounds()
            board._commit_scene_mutation(
                kind="convert_video_to_sequence",
                history_label="Convert video to sequence",
                history=True,
                update_groups=True,
            )
            board._notify("Video converted to sequence.")

        def _on_cancel() -> None:
            if board._convert_worker is not None:
                board._convert_worker.cancel()

        dialog.canceled.connect(_on_cancel)
        worker.progress.connect(_on_progress)
        worker.finished.connect(_on_finished)
        worker.finished.connect(thread.quit)
        thread.started.connect(worker.run)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(worker.deleteLater)

        board._convert_thread = thread
        board._convert_worker = worker
        thread.start()

    def extract_video_frames(self, video_path: Path, out_dir: Path) -> bool:
        if cv2 is None:
            return False
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

    @staticmethod
    def _scale_large_item(item: QtWidgets.QGraphicsItem) -> None:
        logical_w = item.boundingRect().width()
        if logical_w > 600:
            scale = 600 / max(1.0, logical_w)
            item.setScale(scale)
