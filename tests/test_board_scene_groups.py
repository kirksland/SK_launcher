import unittest
from pathlib import Path

from core.board_scene.groups import (
    add_selected_items_to_group,
    build_rename_destination,
    collapse_items_by_group,
    create_group_from_items,
    editable_name_for_tree_path,
    find_group_for_item,
    find_scene_item_for_tree_info,
    first_selected_tree_info,
    filter_group_member_items,
    group_tree_menu_flags,
    reassign_items_to_groups,
    remove_items_from_groups,
    select_tree_info_target,
    serialize_group_members,
    tree_info_is_renamable,
    tree_info_for_scene_item,
    ungroup_items,
)


class FakeRect:
    def __init__(self, center) -> None:
        self._center = center

    def center(self):
        return self._center


class FakeNote:
    def __init__(self, note_id: str) -> None:
        self._selected = False
        self._note_id = note_id

    def data(self, role):
        return "note" if role == 0 else None

    def note_id(self):
        return self._note_id

    def setSelected(self, value: bool) -> None:
        self._selected = value


class FakeItem:
    def __init__(self, kind: str, key: str, center=(0, 0)) -> None:
        self.kind = kind
        self.key = key
        self._selected = False
        self._center = center

    def data(self, role):
        if role == 0:
            return self.kind
        if role == 1:
            return self.key
        return None

    def setSelected(self, value: bool) -> None:
        self._selected = value

    def sceneBoundingRect(self):
        return FakeRect(self._center)


class FakeGroup:
    def __init__(self, points=None) -> None:
        self._members = []
        self.points = set(points or [])
        self.selected = False
        self.bounds_updates = 0

    def members(self):
        return list(self._members)

    def add_member(self, item) -> None:
        if item not in self._members:
            self._members.append(item)

    def remove_member(self, item) -> None:
        if item in self._members:
            self._members.remove(item)

    def contains_scene_point(self, point) -> bool:
        return point in self.points

    def update_bounds(self) -> None:
        self.bounds_updates += 1

    def setSelected(self, value: bool) -> None:
        self.selected = value


class FakeScene:
    def __init__(self) -> None:
        self.removed = []

    def removeItem(self, item) -> None:
        self.removed.append(item)

    def addItem(self, item) -> None:
        self.added = getattr(self, "added", [])
        self.added.append(item)


class FakeGroupFactory(FakeGroup):
    def __init__(self, color) -> None:
        super().__init__()
        self.color = color
        self.data_map = {}

    def setData(self, role, value) -> None:
        self.data_map[role] = value


class BoardSceneGroupsTests(unittest.TestCase):
    def test_find_group_for_item_returns_owner_group(self) -> None:
        item = FakeItem("image", "plate.exr")
        group = FakeGroup()
        group.add_member(item)
        self.assertIs(find_group_for_item([group], item), group)

    def test_add_selected_items_to_group_filters_supported_kinds(self) -> None:
        group = FakeGroup()
        changed = add_selected_items_to_group(group, [FakeItem("image", "a"), FakeItem("group", "g")])
        self.assertTrue(changed)
        self.assertEqual(len(group.members()), 1)

    def test_filter_group_member_items_keeps_supported_kinds(self) -> None:
        items = [FakeItem("image", "a"), FakeItem("group", "g"), FakeItem("note", "n")]
        filtered = filter_group_member_items(items)
        self.assertEqual([item.kind for item in filtered], ["image", "note"])

    def test_create_group_from_items_builds_group_and_attaches_members(self) -> None:
        scene = FakeScene()
        item = FakeItem("image", "a")
        group = create_group_from_items(scene, group_factory=FakeGroupFactory, color="blue", items=[item])
        self.assertIsNotNone(group)
        assert group is not None
        self.assertEqual(group.members(), [item])
        self.assertEqual(scene.added, [group])

    def test_remove_items_from_groups_removes_matching_members(self) -> None:
        item = FakeItem("image", "a")
        group = FakeGroup()
        group.add_member(item)
        self.assertTrue(remove_items_from_groups([item], [group]))
        self.assertEqual(group.members(), [])

    def test_ungroup_items_removes_groups_and_selects_members(self) -> None:
        scene = FakeScene()
        item = FakeItem("image", "a")
        group = FakeGroup()
        group.add_member(item)
        count = ungroup_items(scene, [group])
        self.assertEqual(count, 1)
        self.assertEqual(scene.removed, [group])
        self.assertTrue(item._selected)

    def test_reassign_items_to_groups_moves_member_between_groups(self) -> None:
        item = FakeItem("image", "a", center=(10, 10))
        source = FakeGroup()
        target = FakeGroup(points={(10, 10)})
        source.add_member(item)
        changed = reassign_items_to_groups([item], [source, target])
        self.assertTrue(changed)
        self.assertNotIn(item, source.members())
        self.assertIn(item, target.members())

    def test_collapse_items_by_group_treats_group_as_single_block(self) -> None:
        item_a = FakeItem("image", "a")
        item_b = FakeItem("video", "b")
        lone = FakeItem("sequence", "c")
        group = FakeGroup()
        group.add_member(item_a)
        group.add_member(item_b)
        collapsed = collapse_items_by_group([item_a, item_b, lone], [group])
        self.assertEqual(collapsed, [group, lone])

    def test_tree_info_for_scene_item_supports_note(self) -> None:
        note = FakeNote("n1")
        self.assertEqual(tree_info_for_scene_item(note, FakeNote), ("note", "n1"))

    def test_first_selected_tree_info_returns_first_supported_entry(self) -> None:
        info = first_selected_tree_info([FakeItem("group", "g"), FakeItem("video", "clip.mov")], FakeNote)
        self.assertEqual(info, ("video", "clip.mov"))

    def test_find_scene_item_for_tree_info_matches_media(self) -> None:
        item = FakeItem("video", "clip.mov")
        self.assertIs(find_scene_item_for_tree_info([item], ("video", "clip.mov"), FakeNote), item)

    def test_select_tree_info_target_selects_group_ref(self) -> None:
        selected = [FakeItem("image", "a")]
        group = FakeGroup()
        result = select_tree_info_target(
            selected,
            ("group", 1),
            group_refs={1: group},
            find_scene_item=lambda info: None,
        )
        self.assertIs(result, group)
        self.assertTrue(group.selected)
        self.assertFalse(selected[0]._selected)

    def test_build_rename_destination_validates_names(self) -> None:
        dest, error = build_rename_destination("image", Path("C:/tmp/plate.exr"), "beauty")
        self.assertIsNone(error)
        self.assertEqual(dest.name, "beauty.exr")
        _dest, error = build_rename_destination("sequence", Path("C:/tmp/seq"), "")
        self.assertEqual(error, "Name cannot be empty.")

    def test_group_tree_menu_flags_reflect_available_actions(self) -> None:
        flags = group_tree_menu_flags(("image", "plate.pic"), tree_path=Path("C:/tmp/plate.pic"), pic_exts={".pic", ".picnc"})
        self.assertTrue(flags["open_item"])
        self.assertTrue(flags["rename_entry"])
        self.assertTrue(flags["convert_pic"])
        self.assertTrue(flags["remove_from_group"])

    def test_serialize_group_members_outputs_supported_members(self) -> None:
        note = FakeNote("n1")
        image = FakeItem("image", "plate.exr")
        group = FakeGroup()
        group.add_member(image)
        group.add_member(note)
        self.assertEqual(
            serialize_group_members(group, FakeNote),
            [{"type": "image", "id": "plate.exr"}, {"type": "note", "id": "n1"}],
        )

    def test_tree_info_is_renamable_matches_supported_kinds(self) -> None:
        self.assertTrue(tree_info_is_renamable(("image", "plate.exr")))
        self.assertTrue(tree_info_is_renamable(("sequence", "shots/seq")))
        self.assertFalse(tree_info_is_renamable(("note", "n1")))

    def test_editable_name_for_tree_path_returns_expected_text(self) -> None:
        self.assertEqual(editable_name_for_tree_path(("image", "plate.exr"), Path("C:/tmp/plate.exr")), "plate")
        self.assertEqual(editable_name_for_tree_path(("sequence", "shots/seq"), Path("C:/tmp/seq")), "seq")
        self.assertEqual(editable_name_for_tree_path(("note", "n1"), Path("C:/tmp/n1")), "")


if __name__ == "__main__":
    unittest.main()
