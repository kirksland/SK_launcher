from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PySide6 import QtCore, QtGui, QtWidgets

from core.fs import find_projects, list_hips_with_mtime, open_hip
from core.houdini_env import build_houdini_env
from core.settings import DEFAULT_TEMPLATE_HIP
from core.watchers import update_watcher_paths
from ui.widgets.project_card import ProjectCard

PROJECT_SUBDIRS = [
    "abc",
    "audio",
    "comp",
    "desk",
    "flip",
    "geo",
    "hda",
    "render",
    "scripts",
    "sim",
    "tex",
    "video",
]
JOB_INIT_MARKER = ".skyforge_job_init"


class ProjectsController:
    def __init__(self, window: QtWidgets.QMainWindow) -> None:
        self.w = window
        self._project_watcher: Optional[QtCore.QFileSystemWatcher] = None
        self._project_refresh_timer: Optional[QtCore.QTimer] = None
        self._detail_pinned = False
        self._detail_project_path: Optional[Path] = None
        self._scan_token = 0.0
        self._dir_cache: Dict[Path, list[tuple[str, bool]]] = {}
        self._fs_model = QtWidgets.QFileSystemModel(self.w)
        self._fs_model.setReadOnly(True)
        self._fs_model.setFilter(
            QtCore.QDir.Filter.AllDirs
            | QtCore.QDir.Filter.Files
            | QtCore.QDir.Filter.NoDotAndDotDot
        )
        print("[PROJECTS] Controller init")
        self.w.project_detail_tree.setModel(self._fs_model)
        for col in (1, 2, 3):
            self.w.project_detail_tree.setColumnHidden(col, True)
        self.w.project_detail_tree.customContextMenuRequested.connect(
            self._on_project_detail_context_menu
        )

    def refresh_projects(self, *_: object) -> None:
        self._scan_token = time.time()
        self._dir_cache.clear()
        current_item = self.w.project_grid.currentItem()
        current_path: Optional[Path] = None
        if current_item is not None:
            path_text = current_item.data(QtCore.Qt.ItemDataRole.UserRole)
            if path_text:
                current_path = Path(str(path_text))

        self.w.project_grid.clear()
        if not self._detail_pinned:
            self.w.project_detail_panel.setVisible(False)
        self.w._card_to_item.clear()
        projects = find_projects(self.w.projects_dir)
        self._prune_cache(projects, self.w._project_cache)
        self._prune_selection(projects)
        query = self.w.search_input.text().strip().lower()
        if query:
            projects = [p for p in projects if query in p.name.lower()]

        sort_mode = self.w.sort_combo.currentText()
        if sort_mode.startswith("Date"):
            projects.sort(key=self._get_project_latest_mtime, reverse=True)
        else:
            projects.sort(key=lambda p: p.name.lower())

        for project in projects:
            item = QtWidgets.QListWidgetItem()
            item.setData(QtCore.Qt.ItemDataRole.UserRole, str(project))
            item.setSizeHint(QtCore.QSize(230, 240))
            self.w.project_grid.addItem(item)
            hips = self._get_project_hips(project)
            show_cloud = any(
                e.get("local_path") == str(project) and e.get("client_id") for e in self.w._asset_manager_projects
            )
            selected_hip = self.w._project_hip_selection.get(project)
            card = ProjectCard(
                project,
                self.w.project_grid.iconSize(),
                hips,
                show_cloud_badge=show_cloud,
                selected_hip=selected_hip,
                parent=self.w.project_grid,
            )
            card.selection_changed.connect(self.on_card_selection_changed)
            self.w._card_to_item[card] = item
            self.w.project_grid.setItemWidget(item, card)
            current = card.selected_hip()
            if current is not None:
                self.w._project_hip_selection[project] = current

        if current_path is not None:
            for row in range(self.w.project_grid.count()):
                item = self.w.project_grid.item(row)
                if not item:
                    continue
                path_text = item.data(QtCore.Qt.ItemDataRole.UserRole)
                if path_text and Path(str(path_text)) == current_path:
                    self.w.project_grid.setCurrentItem(item)
                    break
        self.w.status.setText(f"{self.w.project_grid.count()} project(s)")
        self.refresh_project_watch_paths()
        if self._detail_pinned and self._detail_project_path and self._detail_project_path.exists():
            self._show_project_detail(self._detail_project_path)

    def browse_projects_dir(self) -> None:
        directory = QtWidgets.QFileDialog.getExistingDirectory(
            self.w,
            "Select Projects Folder",
            str(self.w.projects_dir),
        )
        if not directory:
            return
        self.w.projects_dir = Path(directory)
        self.w.path_label.setText(f"Projects: {self.w.projects_dir}")
        self.refresh_projects()
        self.refresh_project_watch_paths()

    def create_project(self) -> None:
        name, ok = QtWidgets.QInputDialog.getText(self.w, "New Project", "Project name:")
        if not ok:
            return
        name = name.strip()
        if not name:
            self.w._warn("Project name cannot be empty.")
            return
        project_path = self.w.projects_dir / name
        if project_path.exists():
            self.w._warn("A project with this name already exists.")
            return

        try:
            project_path.mkdir(parents=True, exist_ok=False)
            for subdir in PROJECT_SUBDIRS:
                (project_path / subdir).mkdir(parents=False, exist_ok=True)
            self._ensure_template_hip(project_path)
            (project_path / JOB_INIT_MARKER).write_text("init_job", encoding="utf-8")
        except Exception as exc:  # pragma: no cover - filesystem errors
            self.w._warn(f"Failed to create project:\n{exc}")
            return

        self.refresh_projects()

    def _resolve_new_hip_name(self, project_name: str) -> str:
        pattern = self.w._new_hip_pattern.strip() or "{projectName}_001.hipnc"
        try:
            return pattern.format(projectName=project_name)
        except Exception:
            return f"{project_name}_001.hipnc"

    def _resolve_template_hip(self) -> Optional[Path]:
        launcher_default = Path(__file__).resolve().parents[1] / "untitled.hipnc"
        candidates = [self.w._template_hip, DEFAULT_TEMPLATE_HIP, launcher_default]
        for candidate in candidates:
            if candidate and candidate.exists():
                return candidate
        return None

    def _ensure_template_hip(self, project_path: Path) -> Optional[Path]:
        template = self._resolve_template_hip()
        if template is None:
            missing = "\n".join(
                str(p)
                for p in [
                    self.w._template_hip,
                    DEFAULT_TEMPLATE_HIP,
                    Path(__file__).resolve().parents[1] / "untitled.hipnc",
                ]
                if p
            )
            self.w._warn(f"Template hip not found. Checked:\n{missing}")
            return None

        target_name = self._resolve_new_hip_name(project_path.name)
        target = project_path / target_name
        if not target.exists():
            try:
                target.write_bytes(template.read_bytes())
            except Exception as exc:
                self.w._warn(f"Failed to copy template hip:\n{exc}")
                return None
        return target

    def _ensure_job_scripts(self, project_path: Path) -> None:
        scripts_dir = project_path / "scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        content = (
            "import os\n"
            "try:\n"
            "    import hou\n"
            "except Exception:\n"
            "    hou = None\n"
            f"project_path = r\"{project_path}\"\n"
            "os.environ[\"JOB\"] = project_path\n"
            "if hou is not None:\n"
            "    hou.putenv(\"JOB\", project_path)\n"
        )
        for name in ("123.py", "456.py"):
            script_path = scripts_dir / name
            try:
                script_path.write_text(content, encoding="utf-8")
            except Exception:
                pass

    def _ensure_job_scripts_if_needed(self, project_path: Path) -> None:
        marker = project_path / JOB_INIT_MARKER
        if not marker.exists():
            return
        self._ensure_job_scripts(project_path)
        try:
            marker.unlink()
        except Exception:
            pass

    def open_selected_project(self) -> None:
        item = self.w.project_grid.currentItem()
        if item is None:
            self.w._warn("Select a project first.")
            return
        path_text = item.data(QtCore.Qt.ItemDataRole.UserRole)
        if not path_text:
            self.w._warn("Select a project first.")
            return
        project_path = Path(item.data(QtCore.Qt.ItemDataRole.UserRole))
        card = self.w.project_grid.itemWidget(item)
        if isinstance(card, ProjectCard):
            hip = card.selected_hip()
        else:
            hip = None
        if hip is None:
            hip = self._ensure_template_hip(project_path)
            if hip is None:
                self.w._warn(f"No .hip found in {project_path.name}.")
                return
        try:
            if self.w._use_file_association or not self.w._houdini_exe:
                open_hip(hip)
            else:
                self._ensure_job_scripts_if_needed(project_path)
                self._launch_houdini(hip, project_path)
            self.w.status.setText(f"Opened: {hip.name}")
        except Exception as exc:  # pragma: no cover - UI error path
            self.w._warn(f"Failed to open: {hip}\n{exc}")

    def on_card_selection_changed(self, card: ProjectCard) -> None:
        item = self.w._card_to_item.get(card)
        if item is not None:
            self.w.project_grid.setCurrentItem(item)
        hip = card.selected_hip()
        if hip is not None:
            self.w._project_hip_selection[card.project_path] = hip
            self.w.status.setText(f"Selected: {hip.name}")

    def on_project_selected(
        self,
        current: Optional[QtWidgets.QListWidgetItem],
        _previous: Optional[QtWidgets.QListWidgetItem] = None,
    ) -> None:
        if current is None:
            if self._detail_pinned:
                return
            return
        path_text = current.data(QtCore.Qt.ItemDataRole.UserRole)
        if not path_text:
            if self._detail_pinned:
                return
            return
        project_path = Path(str(path_text))
        if not project_path.exists():
            if self._detail_pinned:
                return
            return

        self._detail_pinned = True
        self._detail_project_path = project_path
        self._show_project_detail(project_path)

    def open_selected_project_folder(self) -> None:
        item = self.w.project_grid.currentItem()
        if item is None:
            return
        path_text = item.data(QtCore.Qt.ItemDataRole.UserRole)
        if not path_text:
            return
        project_path = Path(str(path_text))
        if not project_path.exists():
            return
        os.startfile(str(project_path))  # type: ignore[attr-defined]

    def close_project_detail_panel(self) -> None:
        self.w.project_detail_panel.setVisible(False)
        self.w.project_grid.clearSelection()
        self._detail_pinned = False
        self._detail_project_path = None
        self.w.project_detail_tree.setRootIndex(QtCore.QModelIndex())

    def _show_project_detail(self, project_path: Path) -> None:
        self.w.project_detail_panel.setVisible(True)
        self.w.project_detail_title.setText(f"Structure: {project_path.name}")
        root_path = str(project_path)
        self._fs_model.setRootPath(root_path)
        root_index = self._fs_model.index(root_path)
        self.w.project_detail_tree.setRootIndex(root_index)
        if hasattr(self.w, "board_controller"):
            self.w.board_controller.set_project(project_path)

    def _on_project_detail_context_menu(self, pos: QtCore.QPoint) -> None:
        tree = self.w.project_detail_tree
        index = tree.indexAt(pos)
        if index.isValid() and not tree.selectionModel().isSelected(index):
            tree.setCurrentIndex(index)
        menu = QtWidgets.QMenu(tree)
        send_action = menu.addAction("Send To Board")
        action = menu.exec(tree.viewport().mapToGlobal(pos))
        if action != send_action:
            return
        selection = tree.selectionModel()
        if selection is None:
            return
        rows = selection.selectedRows(0)
        if not rows:
            return
        paths: list[Path] = []
        seen: set[Path] = set()
        model = tree.model()
        for row in rows:
            if model is None:
                continue
            try:
                path_text = model.filePath(row)  # type: ignore[attr-defined]
            except Exception:
                path_text = None
            if not path_text:
                continue
            path = Path(str(path_text))
            if path in seen:
                continue
            seen.add(path)
            paths.append(path)
        if not paths:
            return
        if hasattr(self.w, "board_controller"):
            self.w.board_controller.add_paths_from_selection(paths)

    def _scan_dir_entries(self, path: Path) -> list[tuple[str, bool]]:
        cached = self._dir_cache.get(path)
        if cached is not None:
            return cached
        entries: list[tuple[str, bool]] = []
        try:
            with os.scandir(path) as it:
                for entry in it:
                    try:
                        is_dir = entry.is_dir()
                    except OSError:
                        is_dir = False
                    entries.append((entry.name, is_dir))
        except Exception:
            entries = []
        entries.sort(key=lambda e: (not e[1], e[0].lower()))
        self._dir_cache[path] = entries
        return entries

    def _launch_houdini(self, hip: Path, project_path: Path) -> None:
        if not self.w._houdini_exe:
            open_hip(hip)
            return
        env = build_houdini_env(
            base_env=os.environ,
            project_path=project_path,
            launcher_root=Path(__file__).resolve().parents[1],
        )
        subprocess.Popen([self.w._houdini_exe, str(hip)], env=env)

    def setup_project_watcher(self) -> None:
        self._project_watcher = QtCore.QFileSystemWatcher(self.w)
        self._project_watcher.directoryChanged.connect(self._queue_project_refresh)
        self._project_refresh_timer = QtCore.QTimer(self.w)
        self._project_refresh_timer.setSingleShot(True)
        self._project_refresh_timer.setInterval(500)
        self._project_refresh_timer.timeout.connect(self._run_project_refresh)
        self.refresh_project_watch_paths()

    def _queue_project_refresh(self, _path: str) -> None:
        if not getattr(self.w, "_project_watch_enabled", True):
            return
        if self._project_refresh_timer and not self._project_refresh_timer.isActive():
            self._project_refresh_timer.start()

    def _run_project_refresh(self) -> None:
        self.refresh_project_watch_paths()
        self.refresh_projects()

    def refresh_project_watch_paths(self) -> None:
        if not getattr(self.w, "_project_watch_enabled", True):
            if self._project_watcher:
                self._project_watcher.removePaths(self._project_watcher.directories())
            return
        if not self._project_watcher:
            return
        paths: List[Path] = []
        if self.w.projects_dir.exists():
            paths.append(self.w.projects_dir)
            paths.extend(find_projects(self.w.projects_dir))
        update_watcher_paths(self._project_watcher, paths)

    def _prune_cache(self, projects: List[Path], cache: Dict[Path, Tuple[float, List[Path], float]]) -> None:
        keep = set(projects)
        for key in list(cache.keys()):
            if key not in keep:
                cache.pop(key, None)

    def _prune_selection(self, projects: List[Path]) -> None:
        keep = set(projects)
        for key in list(self.w._project_hip_selection.keys()):
            if key not in keep:
                self.w._project_hip_selection.pop(key, None)

    def _scan_project_hips(
        self,
        project_path: Path,
        cache: Optional[Dict[Path, Tuple[float, List[Path], float]]] = None,
    ) -> Tuple[List[Path], float]:
        cache = cache or self.w._project_cache
        cached = cache.get(project_path)
        if cached and cached[0] == self._scan_token:
            return cached[1], cached[2]
        hips, latest = list_hips_with_mtime(project_path)
        cache[project_path] = (self._scan_token, hips, latest)
        return hips, latest

    def _get_project_hips(
        self, project_path: Path, cache: Optional[Dict[Path, Tuple[float, List[Path], float]]] = None
    ) -> List[Path]:
        hips, _latest = self._scan_project_hips(project_path, cache)
        return hips

    def _get_project_latest_mtime(
        self, project_path: Path, cache: Optional[Dict[Path, Tuple[float, List[Path], float]]] = None
    ) -> float:
        _hips, latest = self._scan_project_hips(project_path, cache)
        return latest

    def prune_cache(self, projects: List[Path], cache: Dict[Path, Tuple[float, List[Path], float]]) -> None:
        self._prune_cache(projects, cache)

    def get_project_hips(
        self, project_path: Path, cache: Optional[Dict[Path, Tuple[float, List[Path], float]]] = None
    ) -> List[Path]:
        return self._get_project_hips(project_path, cache)


class _DirScanWorker(QtCore.QObject):
    entries_ready = QtCore.Signal(object, object)
    finished = QtCore.Signal()

    def __init__(self, path: Path) -> None:
        super().__init__()
        self._path = path

    def run(self) -> None:
        entries: list[tuple[str, bool]] = []
        try:
            with os.scandir(self._path) as it:
                for entry in it:
                    try:
                        is_dir = entry.is_dir()
                    except OSError:
                        is_dir = False
                    entries.append((entry.name, is_dir))
        except Exception:
            entries = []
        entries.sort(key=lambda e: (not e[1], e[0].lower()))
        self.entries_ready.emit(str(self._path), entries)
        self.finished.emit()


class _UiDispatcher(QtCore.QObject):
    def __init__(self, controller: ProjectsController, parent: Optional[QtCore.QObject] = None) -> None:
        super().__init__(parent)
        self._controller = controller

    @QtCore.Slot(object, object)
    def handle_entries(self, path_text: object, entries: object) -> None:
        if not isinstance(path_text, str):
            return
        if not isinstance(entries, list):
            return
        self._controller._on_dir_scan_ready(Path(path_text), entries)

    @QtCore.Slot()
    def handle_finished(self) -> None:
        self._controller._on_dir_scan_finished()
