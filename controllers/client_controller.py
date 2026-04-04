from __future__ import annotations

import shutil
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

from core.fs import find_projects, latest_preview_image
from core.settings import save_settings


class ClientController:
    def __init__(self, window: QtWidgets.QMainWindow) -> None:
        self.w = window

    def refresh_client_catalog(self) -> None:
        self.w.client_list.clear()
        self.w.client_preview.setText("Select a project")
        self.w.client_preview.setPixmap(QtGui.QPixmap())
        self.w.client_info.setText("")
        client_projects = find_projects(self.w.server_repo_dir)
        for project in client_projects:
            item = QtWidgets.QListWidgetItem(project.name)
            item.setData(QtCore.Qt.ItemDataRole.UserRole, str(project))
            self.w.client_list.addItem(item)
        self.w.client_status.setText(f"{self.w.client_list.count()} client project(s)")

    def clone_client_project(self) -> None:
        client_item = self.w.client_list.currentItem()
        if client_item is None:
            self.w.client_status.setText("Select a client project.")
            return
        client_path = Path(str(client_item.data(QtCore.Qt.ItemDataRole.UserRole)))
        client_id = client_path.name
        if not client_path.exists():
            self.w.client_status.setText("Client project not found.")
            return

        local_path = self.w.projects_dir / client_id
        if local_path.exists():
            self.w.client_status.setText("Local project already exists.")
            return

        try:
            local_path.mkdir(parents=True, exist_ok=False)
            for folder in ("assets", "shots"):
                src = client_path / folder
                dst = local_path / folder
                if src.exists() and src.is_dir():
                    shutil.copytree(src, dst)
            for ext in (".png", ".jpg", ".jpeg"):
                thumb = client_path / f"thumbnail{ext}"
                if thumb.exists():
                    shutil.copy2(thumb, local_path / thumb.name)
                    break
        except Exception as exc:
            self.w.client_status.setText(f"Clone failed: {exc}")
            return

        entry = next((e for e in self.w._asset_manager_projects if e.get("local_path") == str(local_path)), None)
        if entry is None:
            entry = {"local_path": str(local_path), "client_id": client_id}
            self.w._asset_manager_projects.append(entry)
        else:
            entry["client_id"] = client_id

        self.w.settings["asset_manager_projects"] = list(self.w._asset_manager_projects)
        save_settings(self.w.settings)
        self.w.project_controller.refresh_projects()
        self.w.asset_controller.refresh_asset_manager()
        self.refresh_client_catalog()
        self.w.client_status.setText(f"Cloned {client_id} to local.")

    def on_client_project_selected(self, item: QtWidgets.QListWidgetItem) -> None:
        client_path = Path(str(item.data(QtCore.Qt.ItemDataRole.UserRole)))
        self.w.client_info.setText(f"Project: {client_path.name}\nServer: {client_path}")
        preview = latest_preview_image(client_path)
        if preview:
            pixmap = QtGui.QPixmap(str(preview))
            if not pixmap.isNull():
                self.w.client_preview.setPixmap(
                    pixmap.scaled(
                        self.w.client_preview.size(),
                        QtCore.Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                        QtCore.Qt.TransformationMode.SmoothTransformation,
                    )
                )
                return
        self.w.client_preview.setText("No preview")
