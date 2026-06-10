from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


@dataclass(frozen=True)
class ComfyVideoMetadata:
    positive_prompt: str
    negative_prompt: str
    seed: Optional[int]
    steps: Optional[int]
    cfg: Optional[float]
    sampler: str
    scheduler: str
    model: str
    prompt: dict[str, Any]
    workflow: dict[str, Any]

    @property
    def has_workflow(self) -> bool:
        return bool(self.workflow)


def load_comfy_video_metadata(path: Path) -> Optional[ComfyVideoMetadata]:
    if not path.is_file() or path.suffix.lower() not in {".mp4", ".mov", ".m4v"}:
        return None
    try:
        payload = next(
            (
                candidate
                for region in _read_metadata_regions(path)
                if (candidate := _extract_comfy_payload(region)) is not None
            ),
            None,
        )
    except OSError:
        return None
    if payload is None:
        return None

    prompt = _coerce_json_object(payload.get("prompt"))
    workflow = _coerce_json_object(payload.get("workflow"))
    if not prompt and not workflow:
        return None

    positive, negative = _extract_prompt_texts(prompt)
    sampler_inputs = _find_sampler_inputs(prompt)
    return ComfyVideoMetadata(
        positive_prompt=positive,
        negative_prompt=negative,
        seed=_optional_int(sampler_inputs.get("seed")),
        steps=_optional_int(sampler_inputs.get("steps")),
        cfg=_optional_float(sampler_inputs.get("cfg")),
        sampler=str(sampler_inputs.get("sampler_name", "") or "").strip(),
        scheduler=str(sampler_inputs.get("scheduler", "") or "").strip(),
        model=_find_model_name(prompt),
        prompt=prompt,
        workflow=workflow,
    )


def _read_metadata_regions(path: Path, region_size: int = 8 * 1024 * 1024) -> list[bytes]:
    size = path.stat().st_size
    with path.open("rb") as handle:
        if size <= region_size * 2:
            return [handle.read()]
        head = handle.read(region_size)
        handle.seek(max(0, size - region_size))
        tail = handle.read(region_size)
    return [tail, head]


def format_workflow_json(metadata: ComfyVideoMetadata) -> str:
    return json.dumps(metadata.workflow, indent=2, ensure_ascii=False)


def _extract_comfy_payload(data: bytes) -> Optional[dict[str, Any]]:
    marker = b'"prompt"'
    offset = 0
    decoder = json.JSONDecoder()
    while True:
        marker_index = data.find(marker, offset)
        if marker_index < 0:
            return None
        object_start = data.rfind(b"{", 0, marker_index)
        if object_start < 0:
            return None
        try:
            text = data[object_start:].decode("utf-8")
            payload, _end = decoder.raw_decode(text)
        except (UnicodeDecodeError, json.JSONDecodeError):
            offset = marker_index + len(marker)
            continue
        if isinstance(payload, dict) and ("prompt" in payload or "workflow" in payload):
            return payload
        offset = marker_index + len(marker)


def _coerce_json_object(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return {}
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return decoded if isinstance(decoded, dict) else {}


def _extract_prompt_texts(prompt: dict[str, Any]) -> tuple[str, str]:
    positive: list[str] = []
    negative: list[str] = []
    for node in prompt.values():
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        text = inputs.get("text")
        if not isinstance(text, str) or not text.strip():
            continue
        class_type = str(node.get("class_type", "")).lower()
        meta = node.get("_meta")
        title = str(meta.get("title", "") if isinstance(meta, dict) else "").lower()
        combined = f"{class_type} {title}"
        target = negative if "negative" in combined or " neg" in f" {combined}" else positive
        target.append(text.strip())
    return "\n\n".join(positive), "\n\n".join(negative)


def _find_sampler_inputs(prompt: dict[str, Any]) -> dict[str, Any]:
    for node in prompt.values():
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        if "seed" in inputs and ("steps" in inputs or "sampler_name" in inputs):
            return inputs
    return {}


def _find_model_name(prompt: dict[str, Any]) -> str:
    model_keys = ("unet_name", "ckpt_name", "model_name", "vae_name")
    for key in model_keys:
        for node in prompt.values():
            if not isinstance(node, dict):
                continue
            inputs = node.get("inputs")
            if not isinstance(inputs, dict):
                continue
            value = inputs.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


def _optional_int(value: object) -> Optional[int]:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _optional_float(value: object) -> Optional[float]:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
