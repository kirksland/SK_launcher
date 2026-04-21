from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(slots=True)
class ApplyPayloadState:
    queue: deque[dict] = field(default_factory=deque)
    pending_groups: list[dict] = field(default_factory=list)
    image_map: dict[str, Any] = field(default_factory=dict)
    video_map: dict[str, Any] = field(default_factory=dict)
    sequence_map: dict[str, Any] = field(default_factory=dict)
    note_map: dict[str, Any] = field(default_factory=dict)
    payload_ref: dict | None = None
    phase: str = "idle"
    base_label: str | None = None
    generation: int = 0

    def reset(self) -> None:
        self.queue.clear()
        self.pending_groups = []
        self.image_map = {}
        self.video_map = {}
        self.sequence_map = {}
        self.note_map = {}
        self.payload_ref = None
        self.phase = "idle"
        self.generation = 0

    def has_pending(self) -> bool:
        return bool(self.queue)


def partition_payload_entries(payload: dict) -> tuple[deque[dict], list[dict]]:
    notes: list[dict] = []
    images: list[dict] = []
    videos: list[dict] = []
    sequences: list[dict] = []
    groups: list[dict] = []
    for entry in payload.get("items", []):
        if not isinstance(entry, dict):
            continue
        kind = entry.get("type")
        if kind == "note":
            notes.append(entry)
        elif kind == "image":
            images.append(entry)
        elif kind == "video":
            videos.append(entry)
        elif kind == "sequence":
            sequences.append(entry)
        elif kind == "group":
            groups.append(entry)
    queue: deque[dict] = deque()
    for entry in notes:
        queue.append(entry)
    for entry in images:
        queue.append(entry)
    for entry in videos:
        queue.append(entry)
    for entry in sequences:
        queue.append(entry)
    return queue, groups


def resolve_group_members(
    refs: object,
    *,
    image_map: dict[str, Any],
    video_map: dict[str, Any],
    sequence_map: dict[str, Any],
    note_map: dict[str, Any],
) -> list[Any]:
    resolved: list[Any] = []
    if not isinstance(refs, list):
        return resolved
    for ref in refs:
        if isinstance(ref, str):
            item = image_map.get(str(ref))
            if item is not None:
                resolved.append(item)
            continue
        if not isinstance(ref, dict):
            continue
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
            resolved.append(item)
    return resolved


def prepare_apply_state(
    apply_state: ApplyPayloadState,
    payload: dict,
    *,
    parse_overrides: Callable[[dict], dict[str, dict[str, object]]],
) -> dict[str, dict[str, object]]:
    apply_state.reset()
    apply_state.payload_ref = payload
    image_overrides = parse_overrides(payload)
    apply_state.queue, apply_state.pending_groups = partition_payload_entries(payload)
    apply_state.phase = "items"
    return image_overrides


def register_built_item(
    apply_state: ApplyPayloadState,
    entry: dict,
    kind: str,
    item: Any,
    *,
    image_overrides: dict[str, dict[str, object]],
    apply_image_override: Callable[[Any, dict[str, object]], None],
    apply_video_override: Callable[[Any, dict[str, object]], None],
) -> None:
    if kind == "image":
        filename = str(entry.get("file", ""))
        if filename:
            apply_state.image_map[filename] = item
            override = image_overrides.get(filename)
            if isinstance(override, dict):
                apply_image_override(item, override)
    elif kind == "video":
        filename = str(entry.get("file", ""))
        if filename:
            apply_state.video_map[filename] = item
            override = image_overrides.get(filename)
            if isinstance(override, dict):
                apply_video_override(item, override)
    elif kind == "sequence":
        dir_text = str(entry.get("dir", ""))
        if dir_text:
            apply_state.sequence_map[dir_text] = item
    elif kind == "note":
        apply_state.note_map[item.note_id()] = item


def apply_pending_groups_to_scene(
    apply_state: ApplyPayloadState,
    scene: Any,
    *,
    build_group_item: Callable[[dict], Any],
) -> None:
    for entry in apply_state.pending_groups:
        group = build_group_item(entry)
        scene.addItem(group)
        for member in resolve_group_members(
            entry.get("members", []),
            image_map=apply_state.image_map,
            video_map=apply_state.video_map,
            sequence_map=apply_state.sequence_map,
            note_map=apply_state.note_map,
        ):
            group.add_member(member)
        group.update_bounds()
    apply_state.pending_groups = []
