from __future__ import annotations

from typing import Any, Callable, Optional

from PySide6 import QtGui

from core.board_edit.tool_stack import extract_crop_settings

DEFAULT_CROP_SETTINGS = (0.0, 0.0, 0.0, 0.0)


def remove_override(overrides: dict[str, dict[str, object]], filename: str) -> bool:
    key = str(filename or "").strip()
    if not key or key not in overrides:
        return False
    overrides.pop(key, None)
    return True


def rename_override_key(
    overrides: dict[str, dict[str, object]],
    source_name: str,
    dest_name: str,
) -> bool:
    source_key = str(source_name or "").strip()
    dest_key = str(dest_name or "").strip()
    if not source_key or not dest_key or source_key == dest_key or source_key not in overrides:
        return False
    overrides[dest_key] = overrides.pop(source_key)
    return True


def build_image_override(
    current: object,
    *,
    tool_stack: list[dict[str, object]],
    exr_channel: Optional[str] = None,
    exr_gamma: Optional[float] = None,
    exr_srgb: Optional[bool] = None,
) -> dict[str, object]:
    merged: dict[str, object] = {}
    if isinstance(current, dict):
        for key in ("channel", "gamma", "srgb"):
            if key in current:
                merged[key] = current[key]
    merged["tool_stack"] = tool_stack
    channel_value = str(exr_channel or "").strip()
    if channel_value:
        merged["channel"] = channel_value
    if exr_gamma is not None:
        merged["gamma"] = float(exr_gamma)
    if exr_srgb is not None:
        merged["srgb"] = bool(exr_srgb)
    return merged


def build_video_override(
    current: object,
    *,
    tool_stack: list[dict[str, object]],
) -> dict[str, object]:
    return {"tool_stack": tool_stack}


def commit_image_override(
    overrides: dict[str, dict[str, object]],
    filename: str,
    *,
    current: object,
    effective: bool,
    tool_stack: list[dict[str, object]],
    exr_channel: Optional[str] = None,
    exr_gamma: Optional[float] = None,
    exr_srgb: Optional[bool] = None,
) -> bool:
    key = str(filename or "").strip()
    if not key:
        return False
    if not effective:
        return remove_override(overrides, key)
    merged = build_image_override(
        current,
        tool_stack=tool_stack,
        exr_channel=exr_channel,
        exr_gamma=exr_gamma,
        exr_srgb=exr_srgb,
    )
    previous = overrides.get(key)
    overrides[key] = merged
    return previous != merged


def commit_video_override(
    overrides: dict[str, dict[str, object]],
    filename: str,
    *,
    current: object,
    effective: bool,
    tool_stack: list[dict[str, object]],
) -> bool:
    key = str(filename or "").strip()
    if not key:
        return False
    if not effective:
        return remove_override(overrides, key)
    merged = build_video_override(
        current,
        tool_stack=tool_stack,
    )
    previous = overrides.get(key)
    overrides[key] = merged
    return previous != merged


def build_exr_preview_override(
    *,
    channel: str,
    gamma: float,
    srgb: bool,
    tool_stack: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "channel": str(channel).strip(),
        "gamma": float(gamma),
        "srgb": bool(srgb),
        "tool_stack": tool_stack,
    }


def build_image_adjust_preview_override(
    current: object,
    *,
    tool_stack: list[dict[str, object]],
) -> dict[str, object]:
    merged: dict[str, object] = {}
    if isinstance(current, dict):
        for key in ("channel", "gamma", "srgb"):
            if key in current:
                merged[key] = current[key]
    merged["tool_stack"] = tool_stack
    return merged


def preview_payload_to_pixmap(payload: object) -> QtGui.QPixmap | None:
    if not (isinstance(payload, tuple) and len(payload) == 3):
        return None
    w, h, raw = payload
    if not (isinstance(w, int) and isinstance(h, int) and isinstance(raw, (bytes, bytearray))):
        return None
    bytes_per_line = w * 3
    qimage = QtGui.QImage(raw, w, h, bytes_per_line, QtGui.QImage.Format.Format_RGB888)
    return QtGui.QPixmap.fromImage(qimage.copy())


def apply_preview_payload_to_item(item: Any, payload: object) -> bool:
    pixmap = preview_payload_to_pixmap(payload)
    if pixmap is None or item.scene() is None:
        return False
    item.set_override_pixmap(pixmap)
    return True


def apply_exr_preview_result(
    overrides: dict[str, dict[str, object]],
    item: Any,
    filename: str,
    *,
    payload: object,
    channel: str,
    gamma: float,
    srgb: bool,
    tool_stack: list[dict[str, object]],
) -> bool:
    if not apply_preview_payload_to_item(item, payload):
        return False
    return update_exr_preview_override(
        overrides,
        filename,
        channel=channel,
        gamma=gamma,
        srgb=srgb,
        tool_stack=tool_stack,
    )


def apply_image_adjust_preview_result(
    overrides: dict[str, dict[str, object]],
    item: Any,
    filename: str,
    *,
    payload: object,
    effective: bool,
    current: object,
    tool_stack: list[dict[str, object]],
) -> bool:
    pixmap = preview_payload_to_pixmap(payload)
    if pixmap is None:
        return False
    key = str(filename or "").strip()
    if not key:
        if item.scene() is None:
            return False
        item.set_override_pixmap(pixmap)
        return True
    if not effective:
        remove_override(overrides, key)
        if item.scene() is None:
            return True
        item.set_override_pixmap(None)
        return True
    if item.scene() is None:
        return False
    item.set_override_pixmap(pixmap)
    update_image_adjust_preview_override(
        overrides,
        key,
        current=current,
        tool_stack=tool_stack,
    )
    return True


def update_exr_preview_override(
    overrides: dict[str, dict[str, object]],
    filename: str,
    *,
    channel: str,
    gamma: float,
    srgb: bool,
    tool_stack: list[dict[str, object]],
) -> bool:
    key = str(filename or "").strip()
    channel_value = str(channel or "").strip()
    if not key or not channel_value:
        return False
    overrides[key] = build_exr_preview_override(
        channel=channel_value,
        gamma=gamma,
        srgb=srgb,
        tool_stack=tool_stack,
    )
    return True


def update_image_adjust_preview_override(
    overrides: dict[str, dict[str, object]],
    filename: str,
    *,
    current: object,
    tool_stack: list[dict[str, object]],
) -> bool:
    key = str(filename or "").strip()
    if not key:
        return False
    overrides[key] = build_image_adjust_preview_override(
        current,
        tool_stack=tool_stack,
    )
    return True


def apply_image_override_to_item(
    item: Any,
    override: dict[str, object],
    *,
    coerce_color_adjustments: Callable[[object], tuple[float, float, float]],
    tool_stack_from_override: Callable[[object], list[dict[str, object]]],
    tool_stack_is_effective: Callable[[object, float, float, float], bool],
    queue_exr_display_for_item: Callable[[Any, str, float, bool, object], None],
    queue_image_adjust_for_item: Callable[[Any, object], None],
) -> None:
    if item.scene() is None:
        return
    path = item.file_path()
    brightness, contrast, saturation = coerce_color_adjustments(override)
    tool_stack = tool_stack_from_override(override)
    crop = extract_crop_settings(tool_stack)
    if crop is not None:
        item.set_crop_norm(*crop)
    else:
        item.set_crop_norm(*DEFAULT_CROP_SETTINGS)
    channel = str(override.get("channel", "")).strip()
    if channel and path.suffix.lower() == ".exr":
        gamma = float(override.get("gamma", 2.2))
        srgb = bool(override.get("srgb", True))
        queue_exr_display_for_item(
            item,
            channel,
            gamma,
            srgb,
            tool_stack,
        )
        return
    if tool_stack_is_effective(tool_stack, brightness, contrast, saturation):
        queue_image_adjust_for_item(
            item,
            tool_stack,
        )


def apply_video_override_to_item(
    item: Any,
    override: dict[str, object],
    *,
    tool_stack_from_override: Callable[[object], list[dict[str, object]]],
    get_video_frame_pixmap: Callable[[Any, int, int], Any],
) -> None:
    if item.scene() is None:
        return
    tool_stack = tool_stack_from_override(override)
    crop = extract_crop_settings(tool_stack)
    if crop is not None:
        item.set_crop_norm(*crop)
    else:
        item.set_crop_norm(*DEFAULT_CROP_SETTINGS)
    pixmap = get_video_frame_pixmap(item.file_path(), 0, 1024)
    if pixmap is not None:
        item.set_override_pixmap(pixmap)


def reapply_scene_overrides(
    scene_items: list[Any],
    image_overrides: dict[str, dict[str, object]],
    *,
    apply_image_override: Callable[[Any, dict[str, object]], None],
    apply_video_override: Callable[[Any, dict[str, object]], None],
    image_type: type,
    video_type: type,
) -> None:
    for scene_item in scene_items:
        if not isinstance(scene_item, (image_type, video_type)):
            continue
        filename = str(scene_item.data(1) or "").strip()
        if not filename:
            continue
        override = image_overrides.get(filename)
        if not isinstance(override, dict):
            continue
        if isinstance(scene_item, image_type):
            apply_image_override(scene_item, override)
        else:
            apply_video_override(scene_item, override)
