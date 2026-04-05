from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PySide6 import QtCore, QtGui, QtWidgets

from core.fs import find_hips, find_projects, open_hip
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
        self.w.project_detail_tree.itemExpanded.connect(self._on_tree_item_expanded)

    def refresh_projects(self, *_: object) -> None:
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

    def _show_project_detail(self, project_path: Path) -> None:
        self.w.project_detail_panel.setVisible(True)
        self.w.project_detail_title.setText(f"Structure: {project_path.name}")
        self.w.project_detail_tree.clear()

        root_item = QtWidgets.QTreeWidgetItem([project_path.name])
        root_item.setData(0, QtCore.Qt.ItemDataRole.UserRole, str(project_path))
        self.w.project_detail_tree.addTopLevelItem(root_item)
        self._add_lazy_children(root_item, project_path)
        root_item.setExpanded(True)
        if hasattr(self.w, "board_controller"):
            self.w.board_controller.set_project(project_path)

    def _add_lazy_children(self, item: QtWidgets.QTreeWidgetItem, path: Path) -> None:
        try:
            children = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except Exception:
            return
        for child in children:
            child_item = QtWidgets.QTreeWidgetItem([child.name])
            child_item.setData(0, QtCore.Qt.ItemDataRole.UserRole, str(child))
            item.addChild(child_item)
            if child.is_dir():
                placeholder = QtWidgets.QTreeWidgetItem(["Loading..."])
                placeholder.setData(0, QtCore.Qt.ItemDataRole.UserRole, None)
                child_item.addChild(placeholder)

    def _on_tree_item_expanded(self, item: QtWidgets.QTreeWidgetItem) -> None:
        path_text = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if not path_text:
            return
        path = Path(str(path_text))
        if not path.is_dir():
            return
        if item.childCount() == 1 and item.child(0).text(0) == "Loading...":
            item.takeChild(0)
            self._add_lazy_children(item, path)

    def _launch_houdini(self, hip: Path, project_path: Path) -> None:
        if not self.w._houdini_exe:
            open_hip(hip)
            return
        env = os.environ.copy()
        env["JOB"] = str(project_path)
        env["HIP"] = str(project_path)
        # Ensure project folder is on HOUDINI_PATH so per-project scripts can be found
        existing_hpath = env.get("HOUDINI_PATH", "")
        project_hpath = f"{project_path};&"
        env["HOUDINI_PATH"] = project_hpath + (existing_hpath or "")
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

    def _get_project_hips(
        self, project_path: Path, cache: Optional[Dict[Path, Tuple[float, List[Path], float]]] = None
    ) -> List[Path]:
        cache = cache or self.w._project_cache
        try:
            mtime = project_path.stat().st_mtime
        except OSError:
            return []

        cached = cache.get(project_path)
        if cached and cached[0] == mtime:
            return cached[1]

        hips = find_hips(project_path)
        latest = max((p.stat().st_mtime for p in hips), default=0.0)
        cache[project_path] = (mtime, hips, latest)
        return hips

    def _get_project_latest_mtime(
        self, project_path: Path, cache: Optional[Dict[Path, Tuple[float, List[Path], float]]] = None
    ) -> float:
        cache = cache or self.w._project_cache
        try:
            mtime = project_path.stat().st_mtime
        except OSError:
            return 0.0

        cached = cache.get(project_path)
        if cached and cached[0] == mtime:
            return cached[2]

        hips = find_hips(project_path)
        latest = max((p.stat().st_mtime for p in hips), default=mtime)
        cache[project_path] = (mtime, hips, latest)
        return latest

    def prune_cache(self, projects: List[Path], cache: Dict[Path, Tuple[float, List[Path], float]]) -> None:
        self._prune_cache(projects, cache)

    def get_project_hips(
        self, project_path: Path, cache: Optional[Dict[Path, Tuple[float, List[Path], float]]] = None
    ) -> List[Path]:
        return self._get_project_hips(project_path, cache)
