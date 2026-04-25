from __future__ import annotations

from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

from core.board_scene.groups import (
    add_selected_items_to_group,
    create_group_from_items,
    find_group_for_item,
    filter_group_member_items,
    prune_empty_groups,
    reassign_items_to_groups,
    remove_items_from_groups,
    scene_groups,
    select_group_members,
    try_add_item_to_groups,
    ungroup_items,
)
from core.board_scene.items import BoardGroupItem, BoardImageItem, BoardNoteItem, BoardSequenceItem, BoardVideoItem


class BoardGroupActionsController:
    """Owns scene-level group operations for the Board."""

    def __init__(self, board_controller: object) -> None:
        self.board = board_controller
        self.w = board_controller.w

    def add_group(self) -> None:
        items = filter_group_member_items(self.board._scene.selectedItems())
        if not items:
            self.board._notify("Select items to group.")
            return
        color = QtWidgets.QColorDialog.getColor(QtGui.QColor("#4aa3ff"), self.w, "Group color")
        if not color.isValid():
            return
        if create_group_from_items(
            self.board._scene,
            group_factory=BoardGroupItem,
            color=color,
            items=items,
        ) is None:
            return
        self.board._commit_scene_mutation(
            kind="group_selection",
            history_label="Group selection",
            history=True,
            update_groups=True,
        )

    def ungroup_selected(self) -> None:
        groups = [i for i in self.board._scene.selectedItems() if isinstance(i, BoardGroupItem)]
        if not groups:
            self.board._notify("Select a group to ungroup.")
            return
        ungroup_items(self.board._scene, groups)
        self.board._commit_scene_mutation(
            kind="ungroup_selection",
            history_label="Ungroup selection",
            history=True,
            update_groups=True,
        )

    def toggle_group_selection(self) -> None:
        selected = list(self.board._scene.selectedItems())
        if any(isinstance(item, BoardGroupItem) for item in selected):
            self.ungroup_selected()
            return
        self.add_group()

    def try_add_item_to_group(
        self, item: QtWidgets.QGraphicsItem, scene_pos: Optional[QtCore.QPointF]
    ) -> None:
        if scene_pos is None:
            scene_pos = item.sceneBoundingRect().center()
        if try_add_item_to_groups(item, self.groups(), scene_pos):
            self.board._commit_scene_mutation(
                kind="add_item_to_group",
                history_label="Add item to group",
                history=True,
                update_groups=True,
            )

    def handle_item_drop(self, items: list[QtWidgets.QGraphicsItem]) -> None:
        moved = [
            i
            for i in items
            if isinstance(i, (BoardImageItem, BoardNoteItem, BoardVideoItem, BoardSequenceItem))
        ]
        if not moved:
            return
        groups = self.groups()
        if not groups:
            return
        reassign_items_to_groups(moved, groups)

    def remove_selected_from_groups(self) -> None:
        if remove_items_from_groups(self.board._scene.selectedItems(), self.groups()):
            self.board._commit_scene_mutation(
                kind="remove_from_group",
                history_label="Remove from group",
                history=True,
                update_groups=True,
            )

    def add_selected_items_to_group_ref(self, group: BoardGroupItem) -> None:
        if add_selected_items_to_group(group, self.board._scene.selectedItems()):
            self.board._commit_scene_mutation(
                kind="add_selection_to_group",
                history_label="Add selection to group",
                history=True,
                update_groups=True,
            )

    def select_group_members(self, group_item: BoardGroupItem) -> None:
        select_group_members(self.board._scene.selectedItems(), group_item)

    def groups(self) -> list[BoardGroupItem]:
        return scene_groups(self.board._scene.items(), BoardGroupItem)

    def prune_empty_groups(self) -> bool:
        return prune_empty_groups(self.board._scene, self.board._scene.items(), BoardGroupItem)

    def find_group_for_item(self, item: QtWidgets.QGraphicsItem) -> Optional[BoardGroupItem]:
        return find_group_for_item(self.groups(), item)
