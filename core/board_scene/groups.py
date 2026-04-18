from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Iterable


GROUP_MEMBER_KINDS = {"image", "note", "video", "sequence"}


def scene_groups(scene_items: Iterable[Any], group_type: type) -> list[Any]:
    return [item for item in scene_items if isinstance(item, group_type)]


def filter_group_member_items(items: Iterable[Any]) -> list[Any]:
    return [item for item in items if item.data(0) in GROUP_MEMBER_KINDS]


def create_group_from_items(
    scene: Any,
    *,
    group_factory: Callable[[Any], Any],
    color: Any,
    items: Iterable[Any],
) -> Any | None:
    members = filter_group_member_items(items)
    if not members:
        return None
    group = group_factory(color)
    group.setData(0, "group")
    scene.addItem(group)
    for item in members:
        group.add_member(item)
    group.update_bounds()
    return group


def find_group_for_item(groups: Iterable[Any], item: Any) -> Any | None:
    for group in groups:
        try:
            if item in group.members():
                return group
        except Exception:
            continue
    return None


def prune_empty_groups(scene: Any, scene_items: Iterable[Any], group_type: type) -> bool:
    removed = False
    for item in list(scene_items):
        if not isinstance(item, group_type):
            continue
        item.update_bounds()
        if item.members():
            continue
        scene.removeItem(item)
        removed = True
    return removed


def select_group_members(selected_items: Iterable[Any], group_item: Any) -> None:
    for item in selected_items:
        item.setSelected(False)
    for member in group_item.members():
        member.setSelected(True)


def add_selected_items_to_group(group: Any, selected_items: Iterable[Any]) -> bool:
    changed = False
    for item in filter_group_member_items(selected_items):
        if item is group:
            continue
        group.add_member(item)
        changed = True
    if changed:
        group.update_bounds()
    return changed


def ungroup_items(scene: Any, groups: Iterable[Any]) -> int:
    count = 0
    for group in groups:
        for member in group.members():
            member.setSelected(True)
        scene.removeItem(group)
        count += 1
    return count


def remove_items_from_groups(selected_items: Iterable[Any], groups: Iterable[Any]) -> bool:
    removed = False
    for item in selected_items:
        group = find_group_for_item(groups, item)
        if group is None:
            continue
        group.remove_member(item)
        group.update_bounds()
        removed = True
    return removed


def try_add_item_to_groups(item: Any, groups: Iterable[Any], scene_pos: Any) -> bool:
    for group in groups:
        if not group.contains_scene_point(scene_pos):
            continue
        group.add_member(item)
        group.update_bounds()
        return True
    return False


def reassign_items_to_groups(moved_items: Iterable[Any], groups: list[Any]) -> bool:
    changed = False
    for item in moved_items:
        center = item.sceneBoundingRect().center()
        target_group = None
        for group in groups:
            if group.contains_scene_point(center):
                target_group = group
                break
        current_group = find_group_for_item(groups, item)
        if target_group is not None and target_group is not current_group:
            if current_group is not None:
                current_group.remove_member(item)
            target_group.add_member(item)
            changed = True
        elif target_group is None and current_group is not None:
            if not current_group.contains_scene_point(center):
                current_group.remove_member(item)
                changed = True
        elif target_group is not None and current_group is None:
            target_group.add_member(item)
            changed = True
        if current_group is not None:
            current_group.update_bounds()
        if target_group is not None:
            target_group.update_bounds()
    return changed


def collapse_items_by_group(items: Iterable[Any], groups: Iterable[Any]) -> list[Any]:
    collapsed: list[Any] = []
    seen_groups: set[int] = set()
    group_list = list(groups)
    for item in items:
        group = find_group_for_item(group_list, item)
        if group is None:
            collapsed.append(item)
            continue
        group_id = id(group)
        if group_id in seen_groups:
            continue
        collapsed.append(group)
        seen_groups.add(group_id)
    return collapsed


def tree_info_for_scene_item(item: Any, note_type: type) -> tuple[str, str] | None:
    kind = item.data(0)
    if kind in {"image", "video", "sequence"}:
        return (str(kind), str(item.data(1)))
    if kind == "note" and isinstance(item, note_type):
        return ("note", item.note_id())
    return None


def first_selected_tree_info(selected_items: Iterable[Any], note_type: type) -> tuple[str, str] | None:
    for item in selected_items:
        info = tree_info_for_scene_item(item, note_type)
        if info is not None:
            return info
    return None


def find_scene_item_for_tree_info(scene_items: Iterable[Any], info: tuple, note_type: type) -> Any | None:
    if not info:
        return None
    kind = str(info[0])
    key = str(info[1]) if len(info) > 1 else ""
    for item in scene_items:
        if item.data(0) != kind:
            continue
        if kind in {"image", "video", "sequence"} and str(item.data(1)) == key:
            return item
        if kind == "note" and isinstance(item, note_type) and item.note_id() == key:
            return item
    return None


def select_tree_info_target(
    selected_items: Iterable[Any],
    info: tuple,
    *,
    group_refs: dict[int, Any],
    find_scene_item: Callable[[tuple], Any | None],
) -> Any | None:
    if not info:
        return None
    kind = str(info[0])
    if kind == "group":
        target = group_refs.get(int(info[1]))
    else:
        target = find_scene_item(info)
    if target is None:
        return None
    for item in selected_items:
        item.setSelected(False)
    target.setSelected(True)
    return target


def tree_label_for_scene_item(item: Any, note_type: type, resolve_project_path: Callable[[str], Path]) -> str | None:
    kind = item.data(0)
    if kind == "image":
        return str(item.data(1))
    if kind == "video":
        return f"Video: {item.data(1)}"
    if kind == "sequence":
        seq_path = resolve_project_path(str(item.data(1)))
        return f"Seq: {seq_path.name}"
    if kind == "note" and isinstance(item, note_type):
        text = item.text_item.toPlainText().strip().replace("\n", " ")
        return f"Note: {text[:24] + ('...' if len(text) > 24 else '')}"
    return None


def tree_path_for_info(
    info: tuple,
    *,
    project_root: Path | None,
    resolve_project_path: Callable[[str], Path],
) -> Path | None:
    if not info:
        return None
    kind = str(info[0])
    key = str(info[1]) if len(info) > 1 else ""
    if kind in {"image", "video"}:
        if project_root is None:
            return None
        return project_root / ".skyforge_board_assets" / key
    if kind == "sequence":
        return resolve_project_path(key)
    return None


def tree_info_is_renamable(info: tuple) -> bool:
    if not info:
        return False
    return str(info[0]) in {"image", "video", "sequence"}


def editable_name_for_tree_path(info: tuple, path: Path | None) -> str:
    if path is None or not info:
        return ""
    kind = str(info[0])
    if kind in {"image", "video"}:
        return path.stem
    if kind == "sequence":
        return path.name
    return ""


def populate_tree_item_metadata(
    tree_item: Any,
    info: tuple[str, str],
    *,
    project_root: Path | None,
    resolve_project_path: Callable[[str], Path],
) -> None:
    from PySide6 import QtCore

    tree_item.setData(0, QtCore.Qt.ItemDataRole.UserRole, info)
    path = tree_path_for_info(
        info,
        project_root=project_root,
        resolve_project_path=resolve_project_path,
    )
    if path is not None:
        tree_item.setData(0, QtCore.Qt.ItemDataRole.UserRole + 1, str(path))


def build_rename_destination(kind: str, src_path: Path, desired_name: str) -> tuple[Path | None, str | None]:
    clean_name = str(desired_name or "").strip()
    if not clean_name:
        return None, "Name cannot be empty."
    if any(ch in clean_name for ch in "\\/:*?\"<>|"):
        return None, "Invalid file name." if kind in {"image", "video"} else "Invalid folder name."
    if kind in {"image", "video"}:
        dest_path = src_path.with_name(f"{clean_name}{src_path.suffix.lower()}")
    elif kind == "sequence":
        dest_path = src_path.with_name(clean_name)
    else:
        return None, "Unsupported rename target."
    if dest_path == src_path:
        return None, None
    if dest_path.exists():
        return None, "A file/folder with this name already exists."
    return dest_path, None


def group_tree_menu_flags(
    info: tuple,
    *,
    tree_path: Path | None,
    pic_exts: set[str],
) -> dict[str, bool]:
    if not info:
        return {}
    kind = str(info[0])
    flags = {
        "add_to_group": False,
        "remove_from_group": False,
        "ungroup": False,
        "open_item": False,
        "convert_video": False,
        "convert_pic": False,
        "rename_entry": False,
        "copy_path": False,
    }
    if kind == "group":
        flags["add_to_group"] = True
        flags["ungroup"] = True
        return flags
    if kind not in GROUP_MEMBER_KINDS:
        return flags
    flags["open_item"] = True
    flags["remove_from_group"] = True
    if kind in {"image", "video", "sequence"}:
        flags["rename_entry"] = True
        flags["copy_path"] = tree_path is not None and tree_path.exists()
    if kind == "video":
        flags["convert_video"] = True
    if kind == "image" and tree_path is not None and tree_path.suffix.lower() in pic_exts:
        flags["convert_pic"] = True
    return flags


def serialize_group_members(group_item: Any, note_type: type) -> list[dict[str, str]]:
    members: list[dict[str, str]] = []
    for item in group_item.members():
        kind = item.data(0)
        if kind in {"image", "video", "sequence"}:
            members.append({"type": str(kind), "id": str(item.data(1))})
        elif kind == "note" and isinstance(item, note_type):
            members.append({"type": "note", "id": item.note_id()})
    return members
