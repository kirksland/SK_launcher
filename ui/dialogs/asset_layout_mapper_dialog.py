from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets


class ManualLayoutDropList(QtWidgets.QListWidget):
    def __init__(self, project_root: Path, title: str, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.project_root = project_root.resolve()
        self.setAcceptDrops(True)
        self.setDragDropMode(QtWidgets.QAbstractItemView.DragDropMode.DropOnly)
        self.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setAlternatingRowColors(True)
        self.setToolTip(f"Drop the parent folders that should appear as {title}.")

    def dragEnterEvent(self, event: QtGui.QDragEnterEvent) -> None:  # type: ignore[override]
        if self._mime_paths(event.mimeData()):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event: QtGui.QDragMoveEvent) -> None:  # type: ignore[override]
        if self._mime_paths(event.mimeData()):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event: QtGui.QDropEvent) -> None:  # type: ignore[override]
        accepted = False
        for path in self._mime_paths(event.mimeData()):
            accepted = self.add_folder(path) or accepted
        if accepted:
            event.acceptProposedAction()
            return
        super().dropEvent(event)

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:  # type: ignore[override]
        if event.key() in (QtCore.Qt.Key.Key_Delete, QtCore.Qt.Key.Key_Backspace):
            for item in self.selectedItems():
                self.takeItem(self.row(item))
            return
        super().keyPressEvent(event)

    def add_folder(self, path: Path) -> bool:
        try:
            resolved = path.resolve()
            relative = resolved.relative_to(self.project_root)
        except (OSError, ValueError):
            return False
        if not resolved.is_dir() or not relative.parts:
            return False
        rel_text = str(relative).replace("\\", "/")
        for index in range(self.count()):
            if self.item(index).data(QtCore.Qt.ItemDataRole.UserRole) == rel_text:
                return False
        item = QtWidgets.QListWidgetItem(rel_text)
        item.setData(QtCore.Qt.ItemDataRole.UserRole, rel_text)
        self.addItem(item)
        return True

    def relative_paths(self) -> list[str]:
        return [
            str(self.item(index).data(QtCore.Qt.ItemDataRole.UserRole))
            for index in range(self.count())
            if self.item(index).data(QtCore.Qt.ItemDataRole.UserRole)
        ]

    @staticmethod
    def _mime_paths(mime: QtCore.QMimeData) -> list[Path]:
        paths: list[Path] = []
        for url in mime.urls():
            if url.isLocalFile():
                paths.append(Path(url.toLocalFile()))
        if not paths and mime.hasText():
            for line in mime.text().splitlines():
                text = line.strip()
                if text:
                    paths.append(Path(text))
        return paths


class AssetLayoutMapperDialog(QtWidgets.QDialog):
    def __init__(
        self,
        project_root: Path,
        seed_schema: dict,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.project_root = project_root
        self.seed_schema = deepcopy(seed_schema)
        self._schema: Optional[dict] = None

        self.setWindowTitle(f"Manual Asset Layout: {project_root.name}")
        self.setModal(True)
        self.resize(920, 560)

        root_layout = QtWidgets.QVBoxLayout(self)
        root_layout.setContentsMargins(14, 14, 14, 14)
        root_layout.setSpacing(10)

        intro = QtWidgets.QLabel(
            "Drag collection folders from the project tree into Shots, Assets or Library. "
            "Use parent folders that contain entities, for example a folder that contains many props or shots."
        )
        intro.setWordWrap(True)
        root_layout.addWidget(intro, 0)

        body = QtWidgets.QHBoxLayout()
        body.setSpacing(12)
        root_layout.addLayout(body, 1)

        self.model = QtWidgets.QFileSystemModel(self)
        self.model.setReadOnly(True)
        self.model.setFilter(QtCore.QDir.Filter.AllDirs | QtCore.QDir.Filter.NoDotAndDotDot)
        self.model.setRootPath(str(project_root))

        self.tree = QtWidgets.QTreeView()
        self.tree.setModel(self.model)
        self.tree.setRootIndex(self.model.index(str(project_root)))
        self.tree.setHeaderHidden(True)
        self.tree.setDragEnabled(True)
        self.tree.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        for column in (1, 2, 3):
            self.tree.setColumnHidden(column, True)
        body.addWidget(self.tree, 2)

        columns = QtWidgets.QWidget()
        columns_layout = QtWidgets.QVBoxLayout(columns)
        columns_layout.setContentsMargins(0, 0, 0, 0)
        columns_layout.setSpacing(8)
        body.addWidget(columns, 3)

        self.shots_list = self._mapping_group(columns_layout, "Shots")
        self.assets_list = self._mapping_group(columns_layout, "Assets")
        self.library_list = self._mapping_group(columns_layout, "Library")
        self._seed_lists()

        add_row = QtWidgets.QHBoxLayout()
        add_row.setSpacing(8)
        columns_layout.addLayout(add_row)
        for label, target in (
            ("Add Selected to Shots", self.shots_list),
            ("Add Selected to Assets", self.assets_list),
            ("Add Selected to Library", self.library_list),
        ):
            button = QtWidgets.QPushButton(label)
            button.clicked.connect(lambda _checked=False, target=target: target.add_folder(self._selected_folder() or Path()))
            add_row.addWidget(button)

        cleanup_row = QtWidgets.QHBoxLayout()
        cleanup_row.setSpacing(8)
        columns_layout.addLayout(cleanup_row)
        remove_btn = QtWidgets.QToolButton()
        remove_btn.setText("Remove Selected")
        clear_btn = QtWidgets.QToolButton()
        clear_btn.setText("Clear All")
        cleanup_row.addWidget(remove_btn, 0)
        cleanup_row.addWidget(clear_btn, 0)
        cleanup_row.addStretch(1)
        remove_btn.clicked.connect(self._remove_selected)
        clear_btn.clicked.connect(self._clear_all)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Save
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        root_layout.addWidget(buttons, 0)
        buttons.accepted.connect(self._accept_manual_layout)
        buttons.rejected.connect(self.reject)

    def schema(self) -> Optional[dict]:
        return deepcopy(self._schema) if self._schema is not None else None

    def _mapping_group(self, parent_layout: QtWidgets.QVBoxLayout, title: str) -> ManualLayoutDropList:
        group = QtWidgets.QGroupBox(title)
        layout = QtWidgets.QVBoxLayout(group)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        list_widget = ManualLayoutDropList(self.project_root, title)
        list_widget.setMinimumHeight(90)
        layout.addWidget(list_widget)
        parent_layout.addWidget(group, 1)
        return list_widget

    def _selected_folder(self) -> Optional[Path]:
        index = self.tree.currentIndex()
        if not index.isValid():
            return None
        path = Path(self.model.filePath(index))
        return path if path.is_dir() else None

    def _seed_lists(self) -> None:
        sources = self.seed_schema.get("entity_sources", [])
        if isinstance(sources, list) and sources:
            for source in sources:
                if not isinstance(source, dict):
                    continue
                rel_path = str(source.get("path", "")).strip()
                if not rel_path:
                    continue
                role = str(source.get("role", "")).strip().lower()
                target = self.library_list if role == "library_asset" else self.assets_list
                if source.get("entity_type") == "shot" or role == "shot":
                    target = self.shots_list
                target.add_folder(self.project_root.joinpath(*[part for part in rel_path.split("/") if part]))
            return

        for rel_path in self.seed_schema.get("entity_roots", {}).get("shot", []):
            self.shots_list.add_folder(self.project_root.joinpath(*[part for part in str(rel_path).split("/") if part]))
        for rel_path in self.seed_schema.get("entity_roots", {}).get("asset", []):
            self.assets_list.add_folder(self.project_root.joinpath(*[part for part in str(rel_path).split("/") if part]))

    def _remove_selected(self) -> None:
        for list_widget in (self.shots_list, self.assets_list, self.library_list):
            for item in list_widget.selectedItems():
                list_widget.takeItem(list_widget.row(item))

    def _clear_all(self) -> None:
        for list_widget in (self.shots_list, self.assets_list, self.library_list):
            list_widget.clear()

    def _accept_manual_layout(self) -> None:
        schema = self._schema_from_mapping()
        if not schema.get("entity_sources"):
            QtWidgets.QMessageBox.warning(
                self,
                "Manual Asset Layout",
                "Assign at least one folder before saving the manual layout.",
            )
            return
        self._schema = schema
        self.accept()

    def _schema_from_mapping(self) -> dict:
        schema = deepcopy(self.seed_schema)
        shots = self.shots_list.relative_paths()
        assets = self.assets_list.relative_paths()
        library = self.library_list.relative_paths()
        sources: list[dict] = []
        for rel_path in shots:
            sources.append(
                {
                    "path": rel_path,
                    "entity_type": "shot",
                    "role": "shot",
                    "confidence": "high",
                    "evidence": ["user manual mapping"],
                }
            )
        for rel_path in assets:
            sources.append(
                {
                    "path": rel_path,
                    "entity_type": "asset",
                    "role": "pipeline_asset",
                    "confidence": "high",
                    "evidence": ["user manual mapping"],
                }
            )
        for rel_path in library:
            sources.append(
                {
                    "path": rel_path,
                    "entity_type": "asset",
                    "role": "library_asset",
                    "confidence": "high",
                    "evidence": ["user manual mapping"],
                }
            )
        schema["entity_sources"] = sources
        schema.setdefault("entity_roots", {})
        schema["entity_roots"]["shot"] = list(shots)
        schema["entity_roots"]["asset"] = list(dict.fromkeys([*assets, *library]))
        return schema
