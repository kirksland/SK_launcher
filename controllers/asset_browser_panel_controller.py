from __future__ import annotations

from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

from core.asset_browser import (
    count_visible_entity_dirs,
    entity_empty_reason,
    entity_prefixes,
    filter_entity_dirs,
    resolved_filter_choice,
)
from core.asset_layout import ResolvedAssetLayout


class AssetBrowserPanelController:
    """Owns the asset browser lists, filters, and entity selection UI."""

    def __init__(self, asset_manager_controller: object) -> None:
        self.host = asset_manager_controller
        self.w = asset_manager_controller.w

    def rebuild_entity_lists(self, target: str) -> None:
        self.host._entity_icon_request_id += 1
        layout = getattr(self.w, "_asset_resolved_layout", None)
        paths_by_target = self.entity_paths_by_target(layout)
        self.sync_entity_filter_combos(paths_by_target)
        search_text = self.w.asset_entity_search.text().strip().lower()
        active_tab = self.w.asset_work_tabs.currentIndex()
        targets = ("shots", "assets", "library") if target == "both" else (target,)
        for current_target in targets:
            self.rebuild_entity_list_target(
                current_target,
                layout=layout,
                entity_paths=paths_by_target[current_target],
                search_text=search_text,
                active_tab=active_tab,
            )

    def entity_paths_by_target(self, layout: ResolvedAssetLayout | None) -> dict[str, list[Path]]:
        if layout is None:
            return {"shots": [], "assets": [], "library": []}
        return {
            "shots": [item.source_path for item in layout.entities_by_role("shot")],
            "assets": [item.source_path for item in layout.entities_by_role("pipeline_asset")],
            "library": [item.source_path for item in layout.entities_by_role("library_asset")],
        }

    def sync_entity_filter_combos(self, paths_by_target: dict[str, list[Path]]) -> None:
        target_widgets = {
            "shots": self.w.asset_shots_filter,
            "assets": self.w.asset_assets_filter,
            "library": self.w.asset_library_filter,
        }
        for target, combo in target_widgets.items():
            prefixes = entity_prefixes(paths_by_target[target])
            previous = combo.currentText() if combo.count() else "All"
            self.populate_entity_filter_combo(combo, prefixes, previous)

    @staticmethod
    def populate_entity_filter_combo(
        combo: QtWidgets.QComboBox,
        prefixes: list[str],
        previous_value: str,
    ) -> None:
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("All")
        for prefix in prefixes:
            combo.addItem(prefix)
        combo.setCurrentText(resolved_filter_choice(previous_value, ["All", *prefixes]))
        combo.blockSignals(False)

    def rebuild_entity_list_target(
        self,
        target: str,
        *,
        layout: ResolvedAssetLayout | None,
        entity_paths: list[Path],
        search_text: str,
        active_tab: int,
    ) -> None:
        spec = self.entity_target_spec(target)
        prefix_filter = spec["filter_widget"].currentText()
        scoped_search = search_text if active_tab == spec["tab_index"] else ""
        visible_paths = filter_entity_dirs(
            entity_paths,
            prefix_filter=prefix_filter,
            search_text=scoped_search,
        )
        list_widget = spec["list_widget"]
        list_widget.setUpdatesEnabled(False)
        list_widget.clear()
        for entity_dir in visible_paths:
            list_widget.addItem(
                self.build_entity_list_item(
                    entity_dir,
                    entity_type=spec["entity_type"],
                    icon_size=list_widget.iconSize(),
                    layout=layout,
                )
            )
        if not visible_paths:
            self.add_empty_entity_item(
                list_widget,
                spec["empty_title"],
                self.empty_reason(
                    total=len(entity_paths),
                    search_text=scoped_search,
                    prefix_filter=prefix_filter,
                    role_label=spec["role_label"],
                ),
            )
        list_widget.setUpdatesEnabled(True)
        self.restore_entity_selection(list_widget)

    def build_entity_list_item(
        self,
        entity_dir: Path,
        *,
        entity_type: str,
        icon_size: QtCore.QSize,
        layout: ResolvedAssetLayout | None,
    ) -> QtWidgets.QListWidgetItem:
        item = QtWidgets.QListWidgetItem(entity_dir.name)
        item.setData(QtCore.Qt.ItemDataRole.UserRole, str(entity_dir))
        item.setData(QtCore.Qt.ItemDataRole.UserRole + 1, entity_type)
        preview = layout.preview_path(self.host._entity_record_for_path(entity_dir)) if layout else None
        item.setData(QtCore.Qt.ItemDataRole.UserRole + 2, str(preview) if preview else "")
        initial_pix = (
            self.host._get_scaled_preview_pixmap(Path(str(preview)), entity_dir, icon_size)
            if preview
            else self.host._get_placeholder_pixmap(entity_dir, icon_size)
        )
        item.setIcon(QtGui.QIcon(initial_pix))
        return item

    def entity_target_spec(self, target: str) -> dict[str, object]:
        specs = {
            "shots": {
                "list_widget": self.w.asset_shots_list,
                "filter_widget": self.w.asset_shots_filter,
                "tab_index": 0,
                "entity_type": "shot",
                "empty_title": "No shots found",
                "role_label": "shot",
            },
            "assets": {
                "list_widget": self.w.asset_assets_list,
                "filter_widget": self.w.asset_assets_filter,
                "tab_index": 1,
                "entity_type": "asset",
                "empty_title": "No pipeline assets found",
                "role_label": "pipeline asset",
            },
            "library": {
                "list_widget": self.w.asset_library_list,
                "filter_widget": self.w.asset_library_filter,
                "tab_index": 2,
                "entity_type": "asset",
                "empty_title": "No library assets found",
                "role_label": "library asset",
            },
        }
        return specs[target]

    def restore_entity_selection(self, list_widget: QtWidgets.QListWidget) -> None:
        current_entity = getattr(self.w, "_asset_current_entity", None)
        if not current_entity:
            return
        current_text = str(current_entity)
        for row in range(list_widget.count()):
            item = list_widget.item(row)
            if item is None or item.data(self.host._EMPTY_ENTITY_ROLE):
                continue
            if item.data(QtCore.Qt.ItemDataRole.UserRole) != current_text:
                continue
            if item.isHidden():
                return
            list_widget.blockSignals(True)
            list_widget.setCurrentItem(item)
            list_widget.blockSignals(False)
            return

    def add_empty_entity_item(self, list_widget: QtWidgets.QListWidget, title: str, detail: str) -> None:
        item = QtWidgets.QListWidgetItem(f"{title}\n{detail}")
        item.setFlags(QtCore.Qt.ItemFlag.NoItemFlags)
        item.setToolTip(detail)
        item.setData(self.host._EMPTY_ENTITY_ROLE, True)
        list_widget.addItem(item)

    def remove_empty_entity_items(self, list_widget: QtWidgets.QListWidget) -> None:
        for row in range(list_widget.count() - 1, -1, -1):
            item = list_widget.item(row)
            if item is not None and item.data(self.host._EMPTY_ENTITY_ROLE):
                list_widget.takeItem(row)

    @staticmethod
    def empty_reason(*, total: int, search_text: str, prefix_filter: str, role_label: str) -> str:
        if total > 0 and search_text:
            return "Try clearing the search field or changing the current group filter."
        if total > 0 and prefix_filter and prefix_filter != "All":
            return "Try switching Group back to All."
        return f"The current layout did not classify any folder as a {role_label}."

    def refresh_shots_list(self, *_: object) -> None:
        self.apply_entity_filters(target="shots")

    def refresh_assets_list(self, *_: object) -> None:
        self.apply_entity_filters(target="assets")

    def refresh_library_list(self, *_: object) -> None:
        self.apply_entity_filters(target="library")

    def refresh_active_list(self, *_: object) -> None:
        target_by_index = {0: "shots", 1: "assets", 2: "library"}
        target = target_by_index.get(self.w.asset_work_tabs.currentIndex(), "assets")
        self.apply_entity_filters(target=target)

    def apply_entity_filters(self, target: str) -> None:
        active_tab = self.w.asset_work_tabs.currentIndex()
        search_text = self.w.asset_entity_search.text().strip().lower()
        paths_by_target = self.entity_paths_by_target(getattr(self.w, "_asset_resolved_layout", None))
        targets = ("shots", "assets", "library") if target == "both" else (target,)
        for current_target in targets:
            spec = self.entity_target_spec(current_target)
            list_widget = spec["list_widget"]
            prefix_filter = spec["filter_widget"].currentText()
            scoped_search = search_text if active_tab == spec["tab_index"] else ""
            self.remove_empty_entity_items(list_widget)
            for row in range(list_widget.count()):
                item = list_widget.item(row)
                if item is None:
                    continue
                path_text = item.data(QtCore.Qt.ItemDataRole.UserRole)
                if not path_text:
                    continue
                path = Path(str(path_text))
                visible = count_visible_entity_dirs(
                    [path],
                    prefix_filter=prefix_filter,
                    search_text=scoped_search,
                ) > 0
                item.setHidden(not visible)
            visible_count = count_visible_entity_dirs(
                paths_by_target[current_target],
                prefix_filter=prefix_filter,
                search_text=scoped_search,
            )
            if visible_count == 0:
                total = sum(
                    1
                    for row in range(list_widget.count())
                    if (item := list_widget.item(row)) is not None
                    and not item.data(self.host._EMPTY_ENTITY_ROLE)
                )
                self.add_empty_entity_item(
                    list_widget,
                    spec["empty_title"],
                    entity_empty_reason(
                        total=total,
                        search_text=scoped_search,
                        prefix_filter=prefix_filter,
                        role_label=spec["role_label"],
                    ),
                )

    def apply_asset_shots_size(self, label: str, refresh: bool = True) -> None:
        size = self.w._asset_shot_size_map.get(label, self.w._asset_shot_size_map["Medium"])
        self.w.asset_shots_list.setIconSize(size)
        grid = QtCore.QSize(size.width() + 20, size.height() + 40)
        self.w.asset_shots_list.setGridSize(grid)
        if refresh:
            self.rebuild_entity_lists(target="shots")

    def on_asset_shots_size_changed(self, label: str) -> None:
        self.apply_asset_shots_size(label, refresh=True)

    def on_asset_entity_clicked(self, item: QtWidgets.QListWidgetItem) -> None:
        path_text = item.data(QtCore.Qt.ItemDataRole.UserRole)
        if not path_text:
            return
        entity_path = Path(str(path_text))
        entity_type = item.data(QtCore.Qt.ItemDataRole.UserRole + 1)
        self.host._load_entity_details(entity_path, entity_type if isinstance(entity_type, str) else None)

    def on_asset_tab_changed(self, index: int) -> None:
        if index == 0:
            self.w.asset_entity_search.setPlaceholderText("Search shots...")
        elif index == 1:
            self.w.asset_entity_search.setPlaceholderText("Search assets...")
        else:
            self.w.asset_entity_search.setPlaceholderText("Search library...")
        project_root = getattr(self.w, "_asset_current_project_root", None)
        if project_root is not None:
            tab_label = {0: "Shots", 1: "Assets", 2: "Library"}.get(index, "Assets")
            self.w.asset_path_label.setText(f"{Path(project_root).name} / {tab_label}")
        self.refresh_active_list()
