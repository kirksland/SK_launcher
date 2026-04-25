from __future__ import annotations

from pathlib import Path

from PySide6 import QtCore

from core.asset_schema import entity_root_candidates
from core.fs import find_projects
from core.watchers import update_watcher_paths


class AssetRefreshController:
    """Owns auto-refresh timers and filesystem watcher refresh logic."""

    def __init__(self, asset_manager_controller: object) -> None:
        self.host = asset_manager_controller
        self.w = asset_manager_controller.w

    def setup_asset_auto_refresh(self) -> None:
        self.host._asset_refresh_timer = QtCore.QTimer(self.w)
        self.host._asset_refresh_timer.setInterval(60000)
        self.host._asset_refresh_timer.timeout.connect(self.host.refresh_asset_manager)
        if self.w.asset_auto_refresh.isChecked():
            self.host._asset_refresh_timer.start()

    def toggle_asset_auto_refresh(self, checked: bool) -> None:
        if not hasattr(self.host, "_asset_refresh_timer"):
            return
        if checked:
            self.host._asset_refresh_timer.start()
            self.w._asset_watch_enabled = True
            self.refresh_asset_watch_paths()
        else:
            self.host._asset_refresh_timer.stop()
            self.w._asset_watch_enabled = False
            self.refresh_asset_watch_paths()

    def setup_asset_watcher(self) -> None:
        self.host._asset_watcher = QtCore.QFileSystemWatcher(self.w)
        self.host._asset_watcher.directoryChanged.connect(self.queue_asset_refresh)
        self.host._asset_refresh_watch_timer = QtCore.QTimer(self.w)
        self.host._asset_refresh_watch_timer.setSingleShot(True)
        self.host._asset_refresh_watch_timer.setInterval(500)
        self.host._asset_refresh_watch_timer.timeout.connect(self.run_asset_refresh)
        self.refresh_asset_watch_paths()

    def queue_asset_refresh(self, changed_path: str) -> None:
        if not getattr(self.w, "_asset_watch_enabled", True):
            return
        if self.is_ignored_asset_watch_path(changed_path):
            return
        print(f"[ASSET_WATCH] queued refresh from: {changed_path}")
        if not self.host._asset_refresh_watch_timer.isActive():
            self.host._asset_refresh_watch_timer.start()

    def run_asset_refresh(self) -> None:
        print("[ASSET_WATCH] running asset manager refresh")
        self.refresh_asset_watch_paths()
        self.host.refresh_asset_manager()

    def refresh_asset_watch_paths(self) -> None:
        if not getattr(self.w, "_asset_watch_enabled", True):
            if hasattr(self.host, "_asset_watcher"):
                self.host._asset_watcher.removePaths(self.host._asset_watcher.directories())
            return
        if not hasattr(self.host, "_asset_watcher"):
            return
        paths: list[Path] = []
        project_paths = find_projects(self.w.projects_dir)
        current_project = getattr(self.w, "_asset_current_project_root", None)
        if current_project is not None:
            current_project_path = Path(current_project)
            if current_project_path.exists() and current_project_path not in project_paths:
                project_paths.append(current_project_path)
        for project_path in project_paths:
            if project_path.exists():
                project_schema = self.host._effective_project_schema(project_path)
                for root_name in entity_root_candidates(project_schema, "shot"):
                    shots_root = project_path / root_name
                    if shots_root.exists():
                        paths.append(shots_root)
                for root_name in entity_root_candidates(project_schema, "asset"):
                    assets_root = project_path / root_name
                    if assets_root.exists():
                        paths.append(assets_root)
        update_watcher_paths(self.host._asset_watcher, paths)

    @staticmethod
    def is_ignored_asset_watch_path(path_text: str) -> bool:
        normalized = path_text.replace("\\", "/").lower()
        return "/.skyforge_cache" in normalized or normalized.endswith("/.skyforge_cache")
