from __future__ import annotations

import uuid

from PySide6 import QtCore, QtGui, QtWidgets

from core.board_scene.groups import serialize_group_members
from core.board_scene.items import BoardGroupItem, BoardImageItem, BoardNoteItem, BoardSequenceItem, BoardVideoItem


class BoardLegacyPayloadController:
    """Owns legacy board payload build/apply used by history replay."""

    def __init__(self, board_controller: object) -> None:
        self.board = board_controller

    def build_payload(self) -> dict:
        board = self.board
        data = {"items": []}
        image_ids: set[str] = set()
        for item in board._scene.items():
            kind = item.data(0)
            if kind == "image":
                file_id = str(item.data(1))
                image_ids.add(file_id)
                data["items"].append({
                    "type": "image",
                    "file": file_id,
                    "x": item.pos().x(),
                    "y": item.pos().y(),
                    "scale": item.scale(),
                })
            elif kind == "video":
                data["items"].append({
                    "type": "video",
                    "file": str(item.data(1)),
                    "x": item.pos().x(),
                    "y": item.pos().y(),
                    "scale": item.scale(),
                })
            elif kind == "sequence":
                data["items"].append({
                    "type": "sequence",
                    "dir": str(item.data(1)),
                    "x": item.pos().x(),
                    "y": item.pos().y(),
                    "scale": item.scale(),
                })
            elif kind == "note" and isinstance(item, BoardNoteItem):
                data["items"].append({
                    "type": "note",
                    **item.note_data(),
                    "x": item.pos().x(),
                    "y": item.pos().y(),
                })
            elif kind == "group" and isinstance(item, BoardGroupItem):
                members = serialize_group_members(item, BoardNoteItem)
                if not members:
                    continue
                data["items"].append({
                    "type": "group",
                    "color": item.color_hex(),
                    "members": members,
                })
        media_ids = set(image_ids)
        media_ids.update(
            str(item.data(1) or "")
            for item in board._scene.items()
            if item.data(0) == "video"
        )
        data["image_display_overrides"] = {
            key: value
            for key, value in board._image_exr_display_overrides.items()
            if key in media_ids and isinstance(value, dict)
        }
        return data

    def apply_payload(self, payload: dict) -> None:
        board = self.board
        assets_dir = board._project_root / ".skyforge_board_assets" if board._project_root else None
        board._image_exr_display_overrides = board._parse_image_display_overrides(payload)
        image_map: dict[str, QtWidgets.QGraphicsPixmapItem] = {}
        video_map: dict[str, QtWidgets.QGraphicsItem] = {}
        sequence_map: dict[str, QtWidgets.QGraphicsItem] = {}
        note_map: dict[str, BoardNoteItem] = {}
        pending_groups = []
        for entry in payload.get("items", []):
            if entry.get("type") == "image" and assets_dir is not None:
                filename = entry.get("file", "")
                path = assets_dir / filename
                item = BoardImageItem(board, path)
                if item.boundingRect().isNull():
                    continue
                self._configure_scene_item(item)
                item.setData(0, "image")
                item.setData(1, filename)
                item.setPos(float(entry.get("x", 0.0)), float(entry.get("y", 0.0)))
                item.setScale(float(entry.get("scale", 1.0)))
                board._scene.addItem(item)
                if filename:
                    image_map[str(filename)] = item
                    override = board._image_exr_display_overrides.get(str(filename))
                    if isinstance(override, dict):
                        board._apply_override_to_image_item(item, override)
            elif entry.get("type") == "video" and assets_dir is not None:
                filename = entry.get("file", "")
                path = assets_dir / filename
                item = BoardVideoItem(board, path)
                if item.boundingRect().isNull():
                    continue
                self._configure_scene_item(item)
                item.setData(0, "video")
                item.setData(1, filename)
                item.setPos(float(entry.get("x", 0.0)), float(entry.get("y", 0.0)))
                item.setScale(float(entry.get("scale", 1.0)))
                board._scene.addItem(item)
                if filename:
                    video_map[str(filename)] = item
                    override = board._image_exr_display_overrides.get(str(filename))
                    if isinstance(override, dict):
                        board._apply_override_to_video_item(item, override)
            elif entry.get("type") == "sequence":
                dir_text = str(entry.get("dir", ""))
                dir_path = board._resolve_project_path(dir_text)
                item = BoardSequenceItem(board, dir_path)
                if item.boundingRect().isNull():
                    continue
                self._configure_scene_item(item)
                item.setData(0, "sequence")
                item.setData(1, dir_text)
                item.setPos(float(entry.get("x", 0.0)), float(entry.get("y", 0.0)))
                item.setScale(float(entry.get("scale", 1.0)))
                board._scene.addItem(item)
                if dir_text:
                    sequence_map[str(dir_text)] = item
            elif entry.get("type") == "note":
                item = BoardNoteItem(entry.get("text", ""))
                align = entry.get("align", "left")
                align_flag = QtCore.Qt.AlignmentFlag.AlignHCenter if align == "center" else QtCore.Qt.AlignmentFlag.AlignLeft
                bg = entry.get("bg", "#99000000")
                item.set_note_style(int(entry.get("font_size", 12)), align_flag, QtGui.QColor(bg))
                item.setScale(float(entry.get("scale", 1.0)))
                item.setData(0, "note")
                item.setPos(float(entry.get("x", 0.0)), float(entry.get("y", 0.0)))
                note_id = entry.get("id") or uuid.uuid4().hex
                item.set_note_id(str(note_id))
                board._scene.addItem(item)
                note_map[item.note_id()] = item
            elif entry.get("type") == "group":
                pending_groups.append(entry)
        for entry in pending_groups:
            color = QtGui.QColor(entry.get("color", "#4aa3ff"))
            group = BoardGroupItem(color)
            group.setData(0, "group")
            board._scene.addItem(group)
            for ref in entry.get("members", []):
                if isinstance(ref, str):
                    item = image_map.get(str(ref))
                    if item is not None:
                        group.add_member(item)
                    continue
                if isinstance(ref, dict):
                    r_type = ref.get("type")
                    r_id = str(ref.get("id", ""))
                    if r_type == "image":
                        item = image_map.get(r_id)
                    elif r_type == "video":
                        item = video_map.get(r_id)
                    elif r_type == "sequence":
                        item = sequence_map.get(r_id)
                    elif r_type == "note":
                        item = note_map.get(r_id)
                    else:
                        item = None
                    if item is not None:
                        group.add_member(item)
            group.update_bounds()

    @staticmethod
    def _configure_scene_item(item: QtWidgets.QGraphicsItem) -> None:
        item.setFlags(
            QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsFocusable
        )
        item.setTransformOriginPoint(item.boundingRect().center())
