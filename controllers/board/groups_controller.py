from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

from core.board_scene.groups import (
    editable_name_for_tree_path,
    find_scene_item_for_tree_info,
    first_selected_tree_info,
    group_tree_menu_flags,
    populate_tree_item_metadata,
    select_tree_info_target,
    tree_info_is_renamable,
    tree_info_for_scene_item,
    tree_label_for_scene_item,
    tree_path_for_info,
)
from core.board_scene.items import BoardNoteItem

PIC_EXTS = {".pic", ".picnc"}


class BoardGroupsController:
    """Owns the Board groups tree UI and keeps it synced with the scene."""

    def __init__(self, board_controller: object) -> None:
        self.board = board_controller
        self.w = board_controller.w
        self._tree_timer: Optional[QtCore.QTimer] = None
        self._tree_refs: dict[int, object] = {}
        self._syncing_tree_selection = False
        self._inline_rename: Optional[dict[str, object]] = None

        tree = self.w.board_page.groups_tree
        tree.itemClicked.connect(self._on_tree_clicked)
        tree.itemDoubleClicked.connect(self._on_tree_double_clicked)
        tree.itemChanged.connect(self._on_tree_item_changed)

    @property
    def tree_refs(self) -> dict[int, object]:
        return self._tree_refs

    def shutdown(self) -> None:
        try:
            tree = self.w.board_page.groups_tree
            tree.itemClicked.disconnect(self._on_tree_clicked)
        except Exception:
            pass
        try:
            tree = self.w.board_page.groups_tree
            tree.itemDoubleClicked.disconnect(self._on_tree_double_clicked)
        except Exception:
            pass
        try:
            tree = self.w.board_page.groups_tree
            tree.itemChanged.disconnect(self._on_tree_item_changed)
        except Exception:
            pass
        try:
            if self._tree_timer is not None and self._tree_timer.isActive():
                self._tree_timer.stop()
        except Exception:
            pass
        self._tree_timer = None

    def is_editing(self) -> bool:
        if getattr(self.board, "_shutting_down", False):
            return False
        try:
            tree = self.w.board_page.groups_tree
            return tree.state() == QtWidgets.QAbstractItemView.State.EditingState
        except Exception:
            return False

    def schedule_update(self) -> None:
        if not self.board._ui_alive():
            return
        if self._tree_timer is not None:
            return
        self._tree_timer = QtCore.QTimer(self.w)
        self._tree_timer.setSingleShot(True)
        self._tree_timer.timeout.connect(self.update_tree)
        self._tree_timer.start(200)

    def update_tree(self) -> None:
        self._tree_timer = None
        if not self.board._ui_alive():
            return
        if self.is_editing():
            self.schedule_update()
            return
        tree = self.w.board_page.groups_tree
        try:
            tree.blockSignals(True)
            tree.clear()
        except Exception:
            return
        self._tree_refs = {}
        groups = self.board._groups()
        root_groups = QtWidgets.QTreeWidgetItem(["Groups"])
        root_groups.setForeground(0, QtGui.QColor("#c6ccd6"))
        tree.addTopLevelItem(root_groups)
        for idx, group in enumerate(groups, start=1):
            title = f"Group {idx}"
            top = QtWidgets.QTreeWidgetItem([title])
            top.setData(0, QtCore.Qt.ItemDataRole.UserRole, ("group", idx))
            top.setForeground(0, QtGui.QColor(group.color_hex()))
            root_groups.addChild(top)
            self._tree_refs[idx] = group
            for member in group.members():
                info = tree_info_for_scene_item(member, BoardNoteItem)
                label = tree_label_for_scene_item(member, BoardNoteItem, self.board._resolve_project_path)
                if info is None or not label:
                    continue
                child = QtWidgets.QTreeWidgetItem([label])
                populate_tree_item_metadata(
                    child,
                    info,
                    project_root=self.board._project_root,
                    resolve_project_path=self.board._resolve_project_path,
                )
                top.addChild(child)

        root_ungrouped = QtWidgets.QTreeWidgetItem(["Ungrouped"])
        root_ungrouped.setForeground(0, QtGui.QColor("#c6ccd6"))
        tree.addTopLevelItem(root_ungrouped)
        for item in self.board._scene.items():
            if item.data(0) not in ("image", "note", "video", "sequence"):
                continue
            if self.board._find_group_for_item(item) is not None:
                continue
            info = tree_info_for_scene_item(item, BoardNoteItem)
            label = tree_label_for_scene_item(item, BoardNoteItem, self.board._resolve_project_path)
            if info is None or not label:
                continue
            child = QtWidgets.QTreeWidgetItem([label])
            populate_tree_item_metadata(
                child,
                info,
                project_root=self.board._project_root,
                resolve_project_path=self.board._resolve_project_path,
            )
            root_ungrouped.addChild(child)

        try:
            tree.expandAll()
            tree.blockSignals(False)
        except Exception:
            return
        self.sync_tree_selection_from_scene()

    def sync_tree_selection_from_scene(self) -> None:
        if not self.board._ui_alive() or not self.board._scene_alive():
            return
        if self.is_editing():
            return
        if self._syncing_tree_selection:
            return
        try:
            tree = self.w.board_page.groups_tree
        except Exception:
            return
        try:
            selected = [
                i
                for i in self.board._scene.selectedItems()
                if i.data(0) in ("image", "note", "video", "sequence")
            ]
        except Exception:
            return
        if not selected:
            try:
                tree.blockSignals(True)
                tree.clearSelection()
                tree.blockSignals(False)
            except Exception:
                pass
            return
        target = first_selected_tree_info(selected, BoardNoteItem)
        if target is None:
            return
        self._syncing_tree_selection = True
        try:
            it = QtWidgets.QTreeWidgetItemIterator(tree)
            while it.value():
                node = it.value()
                info = node.data(0, QtCore.Qt.ItemDataRole.UserRole)
                if info == target:
                    try:
                        tree.blockSignals(True)
                        tree.setCurrentItem(node)
                        tree.scrollToItem(node)
                        tree.blockSignals(False)
                    except Exception:
                        pass
                    break
                it += 1
        finally:
            self._syncing_tree_selection = False

    def on_scene_selection_changed(self) -> None:
        if not self.board._ui_alive() or not self.board._scene_alive():
            return
        if self.is_editing():
            return
        if self._syncing_tree_selection:
            return
        try:
            self.sync_tree_selection_from_scene()
        except Exception:
            return

    def find_scene_item_for_tree_info(self, info: tuple) -> Optional[QtWidgets.QGraphicsItem]:
        return find_scene_item_for_tree_info(self.board._scene.items(), info, BoardNoteItem)

    def select_tree_info_target(self, info: tuple) -> None:
        if not self.board._ui_alive():
            return
        select_tree_info_target(
            self.board._scene.selectedItems(),
            info,
            group_refs=self._tree_refs,
            find_scene_item=self.find_scene_item_for_tree_info,
        )

    def tree_info_path(self, info: tuple) -> Optional[Path]:
        return tree_path_for_info(
            info,
            project_root=self.board._project_root,
            resolve_project_path=self.board._resolve_project_path,
        )

    def add_selected_to_group(self, group_key: int) -> None:
        group = self._tree_refs.get(int(group_key))
        if group is None:
            return
        self.board._add_selected_items_to_group_ref(group)

    def show_context_menu(self, pos: QtCore.QPoint) -> bool:
        if not self.board._ui_alive():
            return False
        tree = self.w.board_page.groups_tree
        item = tree.itemAt(pos)
        if item is None:
            return False
        info = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if not (isinstance(info, tuple) and info):
            return False
        kind = str(info[0])
        path = self.tree_info_path(info)
        flags = group_tree_menu_flags(info, tree_path=path, pic_exts=set(PIC_EXTS))
        menu = QtWidgets.QMenu(tree)
        add_to_group = None
        remove_from_group = None
        ungroup = None
        open_item = None
        convert_video = None
        convert_pic = None
        rename_entry = None
        copy_path = None

        if flags.get("add_to_group"):
            add_to_group = menu.addAction("Add Selected To Group")
        if flags.get("ungroup"):
            ungroup = menu.addAction("Ungroup")
        elif flags.get("open_item"):
            if kind == "image":
                open_item = menu.addAction("Edit Image")
            elif kind == "video":
                open_item = menu.addAction("Open Video")
            elif kind == "sequence":
                open_item = menu.addAction("Open Sequence")
            elif kind == "note":
                open_item = menu.addAction("Edit Note")
            if flags.get("convert_video"):
                convert_video = menu.addAction("Convert Video To Sequence")
            if flags.get("rename_entry"):
                rename_entry = menu.addAction("Rename...")
                if flags.get("copy_path"):
                    copy_path = menu.addAction("Copy Path")
                if flags.get("convert_pic"):
                    convert_pic = menu.addAction("Convert PICNC...")
            if flags.get("remove_from_group"):
                remove_from_group = menu.addAction("Remove From Group")
        else:
            return False

        action = menu.exec(tree.mapToGlobal(pos))
        if action is None:
            return True
        if action == add_to_group:
            self.add_selected_to_group(info[1])
            return True
        if action == ungroup:
            self.select_tree_info_target(info)
            self.board.ungroup_selected()
            return True
        if action == remove_from_group:
            self.select_tree_info_target(info)
            self.board.remove_selected_from_groups()
            return True
        if action == open_item:
            target = self.find_scene_item_for_tree_info(info)
            if target is None:
                self.board._notify("Item not found.")
                return True
            if kind == "image":
                self.board.open_image_item(target)
            elif kind in ("video", "sequence"):
                self.board.open_media_item(target)
            elif kind == "note" and isinstance(target, BoardNoteItem):
                self.board.edit_note(target)
            return True
        if action == convert_video:
            target = self.find_scene_item_for_tree_info(info)
            if target is not None:
                self.board.convert_video_to_sequence(target)
            return True
        if action == convert_pic:
            src_path = self.tree_info_path(info)
            if src_path is not None:
                self.board.convert_picnc_interactive(src_path)
            return True
        if action == rename_entry:
            self._begin_inline_rename(item, info)
            return True
        if action == copy_path:
            path = self.tree_info_path(info)
            if path is not None:
                QtWidgets.QApplication.clipboard().setText(str(path))
                self.board._notify(f"Copied: {path}")
            return True
        return True

    def _on_tree_clicked(self, item: QtWidgets.QTreeWidgetItem) -> None:
        if not self.board._ui_alive():
            return
        info = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if not (isinstance(info, tuple) and info):
            return
        if str(info[0]) == "group":
            group = self._tree_refs.get(int(info[1]))
            if group is not None:
                self.board.select_group_members(group)
            return
        self.select_tree_info_target(info)

    def _on_tree_double_clicked(self, item: QtWidgets.QTreeWidgetItem, _column: int) -> None:
        if not self.board._ui_alive():
            return
        info = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if not (isinstance(info, tuple) and info):
            return
        if tree_info_is_renamable(info):
            self._begin_inline_rename(item, info)

    def _editable_name_for_tree_info(self, info: tuple) -> str:
        return editable_name_for_tree_path(info, self.tree_info_path(info))

    def _begin_inline_rename(self, item: QtWidgets.QTreeWidgetItem, info: tuple) -> None:
        if not self.board._ui_alive():
            return
        if not tree_info_is_renamable(info):
            return
        tree = self.w.board_page.groups_tree
        editable = self._editable_name_for_tree_info(info).strip()
        if not editable:
            return
        self._inline_rename = {
            "item": item,
            "info": info,
            "old_text": item.text(0),
        }
        tree.blockSignals(True)
        flags = item.flags()
        if not (flags & QtCore.Qt.ItemFlag.ItemIsEditable):
            item.setFlags(flags | QtCore.Qt.ItemFlag.ItemIsEditable)
        item.setText(0, editable)
        tree.blockSignals(False)
        tree.setCurrentItem(item)
        tree.setFocus()

        def _open_editor() -> None:
            if not self.board._ui_alive():
                return
            try:
                tree.editItem(item, 0)
            except Exception:
                return

        QtCore.QTimer.singleShot(0, _open_editor)

    def _on_tree_item_changed(self, item: QtWidgets.QTreeWidgetItem, column: int) -> None:
        if not self.board._ui_alive():
            return
        if column != 0:
            return
        state = self._inline_rename
        if not state:
            return
        if state.get("item") is not item:
            return
        self._inline_rename = None
        info = state.get("info")
        old_text = str(state.get("old_text", ""))
        flags = item.flags()
        if flags & QtCore.Qt.ItemFlag.ItemIsEditable:
            item.setFlags(flags & ~QtCore.Qt.ItemFlag.ItemIsEditable)
        if not isinstance(info, tuple):
            self.schedule_update()
            return
        new_name = item.text(0).strip()
        if not new_name:
            self.schedule_update()
            return
        renamed = self.board.rename_group_tree_entry(info, desired_name=new_name)
        if not renamed:
            tree = self.w.board_page.groups_tree
            tree.blockSignals(True)
            item.setText(0, old_text)
            tree.blockSignals(False)
