from __future__ import annotations

from typing import Any, Callable, Optional

from PySide6 import QtCore, QtGui, QtWidgets

from core.board_scene.items import BoardGroupItem, BoardImageItem, BoardNoteItem, BoardSequenceItem, BoardVideoItem


def build_scene_item_from_entry(
    entry: dict,
    *,
    controller: Any,
    assets_dir,
    resolve_project_path: Callable[[str], Any],
) -> tuple[str, Any] | None:
    kind = entry.get("type")
    if kind == "image" and assets_dir is not None:
        filename = str(entry.get("file", ""))
        path = assets_dir / filename
        item = BoardImageItem(controller, path)
        if item.boundingRect().isNull():
            return None
        item.setFlags(
            QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsFocusable
        )
        item.setTransformOriginPoint(item.boundingRect().center())
        item.setData(0, "image")
        item.setData(1, filename)
        item.setPos(float(entry.get("x", 0.0)), float(entry.get("y", 0.0)))
        item.setScale(float(entry.get("scale", 1.0)))
        return "image", item
    if kind == "video" and assets_dir is not None:
        filename = str(entry.get("file", ""))
        path = assets_dir / filename
        item = BoardVideoItem(controller, path)
        if item.boundingRect().isNull():
            return None
        item.setFlags(
            QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsFocusable
        )
        item.setTransformOriginPoint(item.boundingRect().center())
        item.setData(0, "video")
        item.setData(1, filename)
        item.setPos(float(entry.get("x", 0.0)), float(entry.get("y", 0.0)))
        item.setScale(float(entry.get("scale", 1.0)))
        return "video", item
    if kind == "sequence":
        dir_text = str(entry.get("dir", ""))
        dir_path = resolve_project_path(dir_text)
        item = BoardSequenceItem(controller, dir_path)
        if item.boundingRect().isNull():
            return None
        item.setFlags(
            QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsFocusable
        )
        item.setTransformOriginPoint(item.boundingRect().center())
        item.setData(0, "sequence")
        item.setData(1, dir_text)
        item.setPos(float(entry.get("x", 0.0)), float(entry.get("y", 0.0)))
        item.setScale(float(entry.get("scale", 1.0)))
        return "sequence", item
    if kind == "note":
        item = BoardNoteItem(entry.get("text", ""))
        align = entry.get("align", "left")
        align_flag = QtCore.Qt.AlignmentFlag.AlignHCenter if align == "center" else QtCore.Qt.AlignmentFlag.AlignLeft
        bg = entry.get("bg", "#99000000")
        item.set_note_style(int(entry.get("font_size", 12)), align_flag, QtGui.QColor(bg))
        item.setScale(float(entry.get("scale", 1.0)))
        item.setData(0, "note")
        item.setPos(float(entry.get("x", 0.0)), float(entry.get("y", 0.0)))
        note_id = entry.get("id") or QtCore.QUuid.createUuid().toString(QtCore.QUuid.StringFormat.WithoutBraces)
        item.set_note_id(str(note_id))
        return "note", item
    if kind == "group":
        return "group", entry
    return None


def build_group_item(entry: dict) -> BoardGroupItem:
    color = QtGui.QColor(entry.get("color", "#4aa3ff"))
    group = BoardGroupItem(color)
    group.setData(0, "group")
    return group
