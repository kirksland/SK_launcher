from __future__ import annotations

import os
import shutil
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

from core.client_sync import (
    DEFAULT_SYNC_EXCLUDE_DIRS,
    DEFAULT_SYNC_INCLUDE_EXTS,
    available_sync_roots,
    collect_changes,
    compare_subdir,
    resolve_local_project_path,
    safe_mtime,
    sync_roots_for_project,
)
from core.fs import find_projects, latest_preview_image, find_hips
from core.settings import save_settings
from core.sync import (
    apply_sync_plan,
    build_manifest,
    build_sync_plan,
    diff_manifests,
    load_manifest,
    manifest_path,
    save_manifest,
)
from ui.pages.client_page import _SyncTreeDelegate
from ui.widgets.project_card import ProjectCard


class ClientController:
    def __init__(self, window: QtWidgets.QMainWindow) -> None:
        self.w = window
        self._client_fs_model = QtWidgets.QFileSystemModel(self.w)
        self._client_fs_model.setReadOnly(True)
        self._client_fs_model.setFilter(
            QtCore.QDir.Filter.AllDirs
            | QtCore.QDir.Filter.Files
            | QtCore.QDir.Filter.NoDotAndDotDot
        )
        tree = self.w.client_page.client_tree
        tree.setModel(self._client_fs_model)
        tree.setColumnHidden(1, True)
        tree.setColumnHidden(2, True)
        tree.setColumnHidden(3, True)
        self._sync_tree_delegate = _SyncTreeDelegate(tree, ["assets", "shots"])
        tree.setItemDelegate(self._sync_tree_delegate)
        tree.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        tree.customContextMenuRequested.connect(self._on_tree_context_menu)

    def refresh_client_catalog(self) -> None:
        self.w.client_list.clear()
        self.w.client_info.setText("")
        self._reset_sync_panel()
        client_projects = find_projects(self.w.server_repo_dir)
        any_changes = False
        for project in client_projects:
            item = QtWidgets.QListWidgetItem()
            item.setData(QtCore.Qt.ItemDataRole.UserRole, str(project))
            item.setSizeHint(QtCore.QSize(230, 240))
            self.w.client_list.addItem(item)
            hips = find_hips(project)
            has_changes = self._project_has_changes(project)
            any_changes = any_changes or has_changes
            card = ProjectCard(
                project,
                self.w.client_list.iconSize(),
                hips,
                show_alert_badge=has_changes,
                parent=self.w.client_list,
            )
            self.w.client_list.setItemWidget(item, card)
        self.w.client_status.setText(f"{self.w.client_list.count()} client project(s)")
        self.w.set_clients_badge(any_changes)

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

        clone_opts = self._prompt_clone_options(client_id, client_path)
        if clone_opts is None:
            return

        local_path = self.w.projects_dir / client_id
        if local_path.exists():
            action = self._prompt_existing_local_action(client_id)
            if action is None:
                return
            if action == "new_folder":
                new_name = self._prompt_new_clone_name(client_id)
                if not new_name:
                    return
                local_path = self.w.projects_dir / new_name
                if local_path.exists():
                    self.w.client_status.setText("Target folder already exists.")
                    return
            elif action == "merge_missing":
                self._merge_clone_into_existing(local_path, client_path, clone_opts)
                self.w.client_status.setText("Merged selected folders (missing only).")
                self._refresh_sync_panel(client_path)
                self._update_sync_tree_highlight(client_path)
                return
            else:
                self.w.client_status.setText("Clone canceled.")
                return

        try:
            local_path.mkdir(parents=True, exist_ok=False)
            for folder in clone_opts["folders"]:
                src = client_path / folder
                dst = local_path / folder
                if src.exists() and src.is_dir():
                    shutil.copytree(src, dst)
            if clone_opts["thumbnail"]:
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
        self.w.client_status.setText(f"Cloned {local_path.name} to local.")
        self._refresh_sync_panel(client_path)
        self._update_sync_tree_highlight(client_path)

    def _prompt_clone_options(self, client_id: str, client_path: Path) -> dict | None:
        dialog = QtWidgets.QDialog(self.w)
        dialog.setWindowTitle(f"Clone Options: {client_id}")
        dialog.setModal(True)

        layout = QtWidgets.QVBoxLayout(dialog)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(10)

        desc = QtWidgets.QLabel("Choose what to clone locally:")
        layout.addWidget(desc)

        folders_box = QtWidgets.QGroupBox("Folders")
        folders_layout = QtWidgets.QVBoxLayout(folders_box)
        folders_layout.setContentsMargins(8, 8, 8, 8)
        folders_layout.setSpacing(6)

        exclude = {".git", ".skyforge_board_assets", ".skyforge_sync", "__pycache__"}
        folder_checks: list[QtWidgets.QCheckBox] = []
        try:
            entries = sorted(
                [e for e in os.scandir(client_path) if e.is_dir()],
                key=lambda e: e.name.lower(),
            )
        except OSError:
            entries = []

        for entry in entries:
            if entry.name in exclude:
                continue
            cb = QtWidgets.QCheckBox(entry.name)
            cb.setChecked(True)
            folders_layout.addWidget(cb)
            folder_checks.append(cb)

        if not folder_checks:
            empty = QtWidgets.QLabel("No folders found.")
            empty.setStyleSheet("color: #9aa3ad;")
            folders_layout.addWidget(empty)

        layout.addWidget(folders_box)

        thumb_cb = QtWidgets.QCheckBox("Thumbnail")
        thumb_cb.setChecked(True)
        layout.addWidget(thumb_cb)

        hint = QtWidgets.QLabel("Only the selected folders will be cloned.")
        hint.setStyleSheet("color: #9aa3ad;")
        layout.addWidget(hint)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        layout.addWidget(buttons)

        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)

        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return None

        chosen_folders = [cb.text() for cb in folder_checks if cb.isChecked()]
        if not chosen_folders and not thumb_cb.isChecked():
            self.w.client_status.setText("Clone canceled: nothing selected.")
            return None

        return {
            "folders": chosen_folders,
            "thumbnail": thumb_cb.isChecked(),
        }

    def _prompt_existing_local_action(self, client_id: str) -> str | None:
        dialog = QtWidgets.QDialog(self.w)
        dialog.setWindowTitle("Local Project Exists")
        dialog.setModal(True)

        layout = QtWidgets.QVBoxLayout(dialog)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(10)

        desc = QtWidgets.QLabel(
            f"Local project '{client_id}' already exists.\nChoose how to proceed:"
        )
        layout.addWidget(desc)

        merge_radio = QtWidgets.QRadioButton("Merge missing files into existing local")
        merge_radio.setChecked(True)
        new_radio = QtWidgets.QRadioButton("Clone into a new folder")
        cancel_radio = QtWidgets.QRadioButton("Cancel")

        layout.addWidget(merge_radio)
        layout.addWidget(new_radio)
        layout.addWidget(cancel_radio)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        layout.addWidget(buttons)

        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)

        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return None

        if cancel_radio.isChecked():
            return "cancel"
        if new_radio.isChecked():
            return "new_folder"
        return "merge_missing"

    def _prompt_new_clone_name(self, client_id: str) -> str | None:
        text, ok = QtWidgets.QInputDialog.getText(
            self.w,
            "New Folder Name",
            "Clone into folder:",
            QtWidgets.QLineEdit.EchoMode.Normal,
            f"{client_id}_clone",
        )
        if not ok:
            return None
        name = text.strip()
        return name or None

    def _merge_clone_into_existing(self, local_path: Path, client_path: Path, clone_opts: dict) -> None:
        for folder in clone_opts["folders"]:
            src = client_path / folder
            dst = local_path / folder
            if not src.exists() or not src.is_dir():
                continue
            self._copy_tree_missing_only(src, dst)
        if clone_opts.get("thumbnail"):
            for ext in (".png", ".jpg", ".jpeg"):
                thumb = client_path / f"thumbnail{ext}"
                if thumb.exists():
                    target = local_path / thumb.name
                    if not target.exists():
                        shutil.copy2(thumb, target)
                    break

    def _copy_tree_missing_only(self, src: Path, dst: Path) -> None:
        try:
            dst.mkdir(parents=True, exist_ok=True)
        except Exception:
            return
        stack = [src]
        while stack:
            current = stack.pop()
            try:
                with os.scandir(current) as it:
                    for entry in it:
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(Path(entry.path))
                            rel = Path(entry.path).relative_to(src)
                            (dst / rel).mkdir(parents=True, exist_ok=True)
                        else:
                            rel = Path(entry.path).relative_to(src)
                            target = dst / rel
                            if not target.exists():
                                try:
                                    shutil.copy2(entry.path, target)
                                except Exception:
                                    pass
            except OSError:
                continue

    def on_client_project_selected(self, item: QtWidgets.QListWidgetItem) -> None:
        client_path = Path(str(item.data(QtCore.Qt.ItemDataRole.UserRole)))
        self.w.client_info.setText(f"Project: {client_path.name}")
        self._refresh_sync_panel(client_path)
        root = str(client_path)
        self._client_fs_model.setRootPath(root)
        self.w.client_page.client_tree.setRootIndex(self._client_fs_model.index(root))
        self._update_sync_tree_highlight(client_path)

    def pull_client_project(self) -> None:
        client_path = self._current_client_path()
        if client_path is None:
            self.w.client_status.setText("Select a client project.")
            return
        if not self._has_preview():
            self.w.client_status.setText("Run Preview before Pull.")
            return
        if not self._confirm_sync("pull"):
            return
        self._run_sync(client_path, mode="pull")

    def push_client_project(self) -> None:
        client_path = self._current_client_path()
        if client_path is None:
            self.w.client_status.setText("Select a client project.")
            return
        if not self._has_preview():
            self.w.client_status.setText("Run Preview before Push.")
            return
        if not self._confirm_sync("push"):
            return
        self._run_sync(client_path, mode="push")

    def sync_client_project(self) -> None:
        client_path = self._current_client_path()
        if client_path is None:
            self.w.client_status.setText("Select a client project.")
            return
        if not self._has_preview():
            self.w.client_status.setText("Run Preview before Sync.")
            return
        if not self._confirm_sync("sync"):
            return
        self._run_sync(client_path, mode="sync")

    def save_sync_baseline(self) -> None:
        client_path = self._current_client_path()
        if client_path is None:
            self.w.client_status.setText("Select a client project.")
            return
        local_path = self._resolve_local_path(client_path)
        if local_path is None or not local_path.exists():
            self.w.client_status.setText("Local project not found.")
            return
        include_roots = set(self._sync_roots_for(client_path, local_path))
        if not include_roots:
            self.w.client_status.setText("No sync roots selected.")
            return
        manifest = build_manifest(
            local_path,
            time_budget=0.8,
            exclude_dirs=DEFAULT_SYNC_EXCLUDE_DIRS,
            include_roots=include_roots,
            include_exts=DEFAULT_SYNC_INCLUDE_EXTS,
        )
        save_manifest(local_path, manifest)
        self.w.client_status.setText("Baseline saved.")
        self._preview_sync(client_path)
        self._update_client_badges()

    def preview_client_project(self) -> None:
        client_path = self._current_client_path()
        if client_path is None:
            self.w.client_status.setText("Select a client project.")
            return
        self._preview_sync(client_path)

    def open_local_project_folder(self) -> None:
        client_path = self._current_client_path()
        if client_path is None:
            self.w.client_status.setText("Select a client project.")
            return
        local_path = self._resolve_local_path(client_path)
        if local_path is None or not local_path.exists():
            self.w.client_status.setText("Local project not found.")
            return
        os.startfile(str(local_path))  # type: ignore[attr-defined]

    def _current_client_path(self) -> Optional[Path]:
        item = self.w.client_list.currentItem()
        if item is None:
            return None
        return Path(str(item.data(QtCore.Qt.ItemDataRole.UserRole)))

    def _reset_sync_panel(self) -> None:
        self.w.client_sync_status.setText("Status: â€”")
        self.w.client_sync_local_path.setText("Local: â€”")
        self.w.client_sync_server_path.setText("Server: â€”")
        self.w.client_sync_push_list.clear()
        self.w.client_sync_pull_list.clear()
        self.w.client_sync_conflicts_list.clear()
        self.w.client_sync_conflicts_list.addItem("No project selected.")
        self._last_preview = None
        self._update_change_dots()

    def _refresh_sync_panel(self, client_path: Path) -> None:
        local_path = self._resolve_local_path(client_path)
        client_mtime = safe_mtime(client_path)
        local_mtime = safe_mtime(local_path) if local_path and local_path.exists() else 0.0
        if local_path is None or not local_path.exists():
            status = "Not cloned"
        elif local_mtime > client_mtime:
            status = "Ahead (local)"
        elif client_mtime > local_mtime:
            status = "Behind (server)"
        else:
            status = "Up-to-date"
        self.w.client_sync_status.setText(f"Status: {status}")
        self.w.client_sync_local_path.setText(f"Local: {local_path if local_path else 'â€”'}")
        self.w.client_sync_server_path.setText(f"Server: {client_path}")
        self.w.client_sync_push_list.clear()
        self.w.client_sync_pull_list.clear()
        self.w.client_sync_conflicts_list.clear()
        if status == "Not cloned":
            self.w.client_sync_conflicts_list.addItem("Clone the project to start syncing.")
        else:
            if local_path is None:
                return
            self._preview_sync(client_path)
        self._update_client_badges()
        self._update_sync_tree_highlight(client_path)
        self._update_change_dots()

    @staticmethod
    def _safe_mtime(path: Path) -> float:
        return safe_mtime(path)

    def _resolve_local_path(self, client_path: Path) -> Optional[Path]:
        return resolve_local_project_path(
            client_path,
            self.w._asset_manager_projects,
            self.w.projects_dir,
        )

    def _compare_subdir(self, local_root: Path, client_root: Path, subdir: str) -> str:
        return compare_subdir(local_root, client_root, subdir)

    def _latest_mtime(self, root: Path, max_entries: int = 12000, time_budget: float = 0.20) -> float:
        from core.client_sync import latest_mtime

        return latest_mtime(root, max_entries=max_entries, time_budget=time_budget)

    def _add_changed_files(self, local_root: Path, client_root: Path) -> None:
        items = self._collect_changes(local_root, client_root, max_items=60, time_budget=0.35)
        if not items:
            self.w.client_sync_conflicts_list.addItem("No changes detected (fast scan).")
            return
        for line in items:
            if line.startswith("+") or line.startswith("â†‘"):
                self.w.client_sync_push_list.addItem(line)
            elif line.startswith("-") or line.startswith("â†“"):
                self.w.client_sync_pull_list.addItem(line)
            elif line.startswith("!"):
                self.w.client_sync_conflicts_list.addItem(line)

    def _preview_sync(self, client_path: Path) -> None:
        local_path = self._resolve_local_path(client_path)
        if local_path is None or not local_path.exists():
            return
        include_roots = set(self._sync_roots_for(client_path, local_path))
        if not include_roots:
            self.w.client_sync_push_list.clear()
            self.w.client_sync_pull_list.clear()
            self.w.client_sync_conflicts_list.clear()
            self.w.client_sync_conflicts_list.addItem("No sync roots selected.")
            self._last_preview = {"push": 0, "pull": 0, "conflicts": 0}
            self._last_conflicts = []
            self._update_change_dots()
            return
        plan = build_sync_plan(
            local_path,
            client_path,
            exclude_dirs=DEFAULT_SYNC_EXCLUDE_DIRS,
            include_roots=include_roots,
            include_exts=DEFAULT_SYNC_INCLUDE_EXTS,
            time_budget=0.35,
        )
        diff = plan["diff"]
        push = diff["push"][:20]
        pull = diff["pull"][:20]
        conflicts = diff["conflicts"][:20]
        if conflicts:
            self.w.client_sync_conflicts_list.addItem(f"Conflicts: {len(diff['conflicts'])}")
            for p in conflicts:
                self.w.client_sync_conflicts_list.addItem(f"! {p}")
        else:
            if plan["baseline"] is None:
                self.w.client_sync_conflicts_list.addItem("Conflicts: â€” (save baseline first)")
            else:
                self.w.client_sync_conflicts_list.addItem("Conflicts: 0")
        for p in push:
            self.w.client_sync_push_list.addItem(f"â†‘ {p}")
        for p in pull:
            self.w.client_sync_pull_list.addItem(f"â†“ {p}")
        if not push:
            self.w.client_sync_push_list.addItem("No local changes.")
        if not pull:
            self.w.client_sync_pull_list.addItem("No server changes.")
        self._last_preview = {
            "push": len(diff["push"]),
            "pull": len(diff["pull"]),
            "conflicts": len(diff["conflicts"]),
        }
        if conflicts:
            self._last_conflicts = [str(p) for p in conflicts]
        else:
            self._last_conflicts = []
        self._update_change_dots()

    def _run_sync(self, client_path: Path, mode: str) -> None:
        local_path = self._resolve_local_path(client_path)
        if local_path is None or not local_path.exists():
            self.w.client_status.setText("Local project not found.")
            return
        self.w.client_status.setText(f"{mode.capitalize()} in progress...")
        include_roots = set(self._sync_roots_for(client_path, local_path))
        if not include_roots:
            self.w.client_status.setText("No sync roots selected.")
            return
        plan = build_sync_plan(
            local_path,
            client_path,
            exclude_dirs=DEFAULT_SYNC_EXCLUDE_DIRS,
            include_roots=include_roots,
            include_exts=DEFAULT_SYNC_INCLUDE_EXTS,
            time_budget=0.5,
        )
        diff = plan["diff"]
        counts = apply_sync_plan(local_path, client_path, diff, mode=mode)
        if counts["conflicts"]:
            self.w.client_status.setText(f"Conflicts: {counts['conflicts']} (check conflicts folder)")
        else:
            self.w.client_status.setText(
                f"{mode.capitalize()} done. Pushed {counts['pushed']} / Pulled {counts['pulled']}"
            )
        # Update baseline after successful sync (no conflicts)
        if counts["conflicts"] == 0:
            save_manifest(local_path, plan["local_manifest"])
        self._refresh_sync_panel(client_path)
        self._update_client_badges()

    def resolve_conflicts(self, mode: str) -> None:
        client_path = self._current_client_path()
        if client_path is None:
            self.w.client_status.setText("Select a client project.")
            return
        local_path = self._resolve_local_path(client_path)
        if local_path is None or not local_path.exists():
            self.w.client_status.setText("Local project not found.")
            return
        conflicts = self._selected_conflicts() or getattr(self, "_last_conflicts", [])
        if not conflicts:
            self.w.client_status.setText("No conflicts to resolve.")
            return
        if not self._confirm_resolve(mode, len(conflicts)):
            return
        resolved = 0
        for rel in conflicts:
            local_file = local_path / rel
            server_file = client_path / rel
            if mode == "local":
                if local_file.exists():
                    self._copy_file(local_file, server_file)
                    resolved += 1
            elif mode == "server":
                if server_file.exists():
                    self._copy_file(server_file, local_file)
                    resolved += 1
            elif mode == "both":
                if local_file.exists() and server_file.exists():
                    backup = local_file.with_name(local_file.stem + "_local" + local_file.suffix)
                    self._copy_file(local_file, backup)
                    self._copy_file(server_file, local_file)
                    resolved += 1
        self.w.client_status.setText(f"Resolved {resolved} conflict(s) with mode: {mode}")
        self._refresh_sync_panel(client_path)
        self._update_client_badges()

    def _update_client_badges(self) -> None:
        any_changes = False
        for i in range(self.w.client_list.count()):
            item = self.w.client_list.item(i)
            if item is None:
                continue
            project = Path(str(item.data(QtCore.Qt.ItemDataRole.UserRole)))
            has_changes = self._project_has_changes(project)
            card = self.w.client_list.itemWidget(item)
            if isinstance(card, ProjectCard):
                card.set_alert_visible(has_changes)
            any_changes = any_changes or has_changes
        self.w.set_clients_badge(any_changes)

    def _update_change_dots(self) -> None:
        def count_real_items(widget: QtWidgets.QListWidget) -> int:
            count = 0
            for i in range(widget.count()):
                text = widget.item(i).text().strip()
                if text.startswith("â†‘") or text.startswith("â†“") or text.startswith("!"):
                    count += 1
            return count

        push_count = count_real_items(self.w.client_sync_push_list)
        pull_count = count_real_items(self.w.client_sync_pull_list)
        conflict_count = count_real_items(self.w.client_sync_conflicts_list)
        self.w.client_page.client_push_dot.setVisible(push_count > 0)
        self.w.client_page.client_pull_dot.setVisible(pull_count > 0)
        self.w.client_page.client_conflicts_dot.setVisible(conflict_count > 0)

    def _update_sync_tree_highlight(self, client_path: Path) -> None:
        local_path = self._resolve_local_path(client_path)
        if local_path is None or not local_path.exists():
            self._sync_tree_delegate.set_sync_roots([])
            return
        roots = self._sync_roots_for(client_path, local_path)
        self._sync_tree_delegate.set_sync_roots(roots)

    def _project_has_changes(self, client_path: Path) -> bool:
        local_path = self._resolve_local_path(client_path)
        if local_path is None or not local_path.exists():
            return False
        roots = self._sync_roots_for(client_path, local_path)
        if not roots:
            return False
        reports = [self._compare_subdir(local_path, client_path, root) for root in roots]
        change_values = {"local newer", "server newer", "missing local", "missing server"}
        return any(r in change_values for r in reports)

    def _sync_roots_store(self) -> dict:
        store = self.w.settings.get("client_sync_roots")
        if not isinstance(store, dict):
            store = {}
            self.w.settings["client_sync_roots"] = store
        return store

    def _available_sync_roots(self, client_path: Path, local_path: Path) -> list[str]:
        return available_sync_roots(
            client_path,
            local_path,
            exclude_dirs=DEFAULT_SYNC_EXCLUDE_DIRS,
        )

    def _sync_roots_for(self, client_path: Path, local_path: Path) -> list[str]:
        client_id = client_path.name
        store = self._sync_roots_store()
        available = self._available_sync_roots(client_path, local_path)
        roots, changed = sync_roots_for_project(client_id, available, store)
        if changed:
            store[client_id] = list(roots)
            save_settings(self.w.settings)
        return roots

    def _on_tree_context_menu(self, pos: QtCore.QPoint) -> None:
        client_path = self._current_client_path()
        if client_path is None:
            return
        local_path = self._resolve_local_path(client_path)
        if local_path is None or not local_path.exists():
            return
        tree = self.w.client_page.client_tree
        index = tree.indexAt(pos)
        if not index.isValid():
            return
        model = tree.model()
        if model is None:
            return
        path_text = model.filePath(index)  # type: ignore[attr-defined]
        root_index = tree.rootIndex()
        root_path = model.filePath(root_index) if root_index.isValid() else ""
        if not root_path or not path_text.startswith(root_path):
            return
        rel = path_text[len(root_path):].lstrip("\\/").split("\\")[0].split("/")[0]
        if not rel:
            return
        available = self._available_sync_roots(client_path, local_path)
        if rel not in available:
            return
        roots = self._sync_roots_for(client_path, local_path)
        menu = QtWidgets.QMenu(tree)
        if rel in roots:
            toggle = menu.addAction(f"Exclude From Sync: {rel}")
        else:
            toggle = menu.addAction(f"Include In Sync: {rel}")
        reset = menu.addAction("Reset Sync Roots")
        action = menu.exec(tree.viewport().mapToGlobal(pos))
        if action == toggle:
            if rel in roots:
                roots = [r for r in roots if r != rel]
            else:
                roots = roots + [rel]
            store = self._sync_roots_store()
            store[client_path.name] = roots
            save_settings(self.w.settings)
            self._update_sync_tree_highlight(client_path)
            self._refresh_sync_panel(client_path)
        elif action == reset:
            store = self._sync_roots_store()
            if client_path.name in store:
                store.pop(client_path.name)
                save_settings(self.w.settings)
            self._update_sync_tree_highlight(client_path)
            self._refresh_sync_panel(client_path)

    @staticmethod
    def _copy_file(src: Path, dst: Path) -> None:
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            import shutil
            shutil.copy2(src, dst)
        except Exception:
            pass

    def _has_preview(self) -> bool:
        return bool(getattr(self, "_last_preview", None))

    def _confirm_sync(self, mode: str) -> bool:
        preview = getattr(self, "_last_preview", {"push": 0, "pull": 0, "conflicts": 0})
        msg = (
            f"Mode: {mode}\n"
            f"To Push: {preview.get('push', 0)}\n"
            f"To Pull: {preview.get('pull', 0)}\n"
            f"Conflicts: {preview.get('conflicts', 0)}\n\n"
            "This will copy files and create backups.\nProceed?"
        )
        result = QtWidgets.QMessageBox.question(
            self.w,
            "Confirm Sync",
            msg,
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
        )
        return result == QtWidgets.QMessageBox.StandardButton.Yes

    def _confirm_resolve(self, mode: str, count: int) -> bool:
        msg = f"Resolve {count} conflict(s) using '{mode}'?\nThis will overwrite files."
        result = QtWidgets.QMessageBox.warning(
            self.w,
            "Confirm Resolve",
            msg,
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
        )
        return result == QtWidgets.QMessageBox.StandardButton.Yes

    def _selected_conflicts(self) -> list[str]:
        items = self.w.client_sync_conflicts_list.selectedItems()
        result = []
        for item in items:
            text = item.text().strip()
            if text.startswith("! "):
                result.append(text[2:])
        return result

    def _collect_changes(
        self,
        local_root: Path,
        client_root: Path,
        max_items: int = 40,
        time_budget: float = 0.30,
    ) -> list[str]:
        return collect_changes(
            local_root,
            client_root,
            max_items=max_items,
            time_budget=time_budget,
        )


