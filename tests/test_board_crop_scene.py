import unittest

from PySide6 import QtCore

from tools.board_tools.crop.scene import (
    apply_crop_to_item,
    begin_crop_handle_drag,
    crop_handles_active,
    crop_values_from_drag,
    focus_item_base_size,
)
from core.board_edit.handles import build_crop_handle_layout


class _FakeCropItem:
    def __init__(self) -> None:
        self._base_size = QtCore.QSizeF(200.0, 100.0)
        self.crop = None

    def set_crop_norm(self, left: float, top: float, right: float, bottom: float) -> None:
        self.crop = (left, top, right, bottom)

    def sceneBoundingRect(self) -> QtCore.QRectF:
        return QtCore.QRectF(10.0, 20.0, 200.0, 100.0)

    def boundingRect(self) -> QtCore.QRectF:
        return QtCore.QRectF(0.0, 0.0, 200.0, 100.0)


class _RectOnlyItem:
    def boundingRect(self) -> QtCore.QRectF:
        return QtCore.QRectF(0.0, 0.0, 320.0, 180.0)


class CropSceneTests(unittest.TestCase):
    def test_crop_handles_active_requires_crop_panel_and_supported_item(self) -> None:
        item = _FakeCropItem()
        self.assertTrue(crop_handles_active(item, "crop"))
        self.assertFalse(crop_handles_active(item, "bcs"))
        self.assertFalse(crop_handles_active(object(), "crop"))

    def test_focus_item_base_size_prefers_explicit_base_size(self) -> None:
        size = focus_item_base_size(_FakeCropItem())
        self.assertEqual(size, QtCore.QSizeF(200.0, 100.0))

    def test_focus_item_base_size_falls_back_to_bounding_rect(self) -> None:
        size = focus_item_base_size(_RectOnlyItem())
        self.assertEqual(size, QtCore.QSizeF(320.0, 180.0))

    def test_apply_crop_to_item_updates_supported_target(self) -> None:
        item = _FakeCropItem()
        changed = apply_crop_to_item(item, (0.1, 0.0, 0.2, 0.0))
        self.assertTrue(changed)
        self.assertEqual(item.crop, (0.1, 0.0, 0.2, 0.0))

    def test_begin_crop_handle_drag_uses_layout_hit(self) -> None:
        item = _FakeCropItem()
        layout = build_crop_handle_layout(item.sceneBoundingRect(), handle_size=12.0)
        drag_state = begin_crop_handle_drag(
            item,
            layout,
            layout.handle_rects["left"].center(),
            (0.0, 0.0, 0.0, 0.0),
        )
        self.assertIsNotNone(drag_state)
        assert drag_state is not None
        self.assertEqual(drag_state.role, "left")
        self.assertEqual(drag_state.base_size, QtCore.QSizeF(200.0, 100.0))

    def test_crop_values_from_drag_applies_scene_delta(self) -> None:
        item = _FakeCropItem()
        layout = build_crop_handle_layout(item.sceneBoundingRect(), handle_size=12.0)
        drag_state = begin_crop_handle_drag(
            item,
            layout,
            layout.handle_rects["left"].center(),
            (0.1, 0.0, 0.0, 0.0),
        )
        assert drag_state is not None
        crop = crop_values_from_drag(
            drag_state,
            QtCore.QPointF(drag_state.start_scene_pos.x() + 20.0, drag_state.start_scene_pos.y()),
        )
        self.assertIsNotNone(crop)
        assert crop is not None
        self.assertAlmostEqual(crop[0], 0.2)
        self.assertAlmostEqual(crop[1], 0.0)


if __name__ == "__main__":
    unittest.main()
