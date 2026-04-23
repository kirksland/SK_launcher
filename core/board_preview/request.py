from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping as MappingABC, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Mapping


@dataclass(frozen=True, slots=True)
class PreviewRequest:
    kind: str
    media_kind: str
    source_path: str
    settings: Mapping[str, object] = field(default_factory=dict)
    mtime_ns: int = 0

    def __post_init__(self) -> None:
        source = str(self.source_path or "").strip()
        object.__setattr__(self, "kind", str(self.kind or "").strip().lower())
        object.__setattr__(self, "media_kind", str(self.media_kind or "").strip().lower())
        object.__setattr__(self, "source_path", source)
        object.__setattr__(self, "settings", MappingProxyType(dict(self.settings or {})))

    @classmethod
    def from_path(
        cls,
        *,
        kind: str,
        media_kind: str,
        source_path: Path,
        settings: Mapping[str, object] | None = None,
    ) -> "PreviewRequest":
        try:
            mtime_ns = int(source_path.stat().st_mtime_ns)
        except OSError:
            mtime_ns = 0
        return cls(
            kind=kind,
            media_kind=media_kind,
            source_path=str(source_path),
            settings=settings or {},
            mtime_ns=mtime_ns,
        )

    @property
    def key(self) -> str:
        payload = {
            "kind": self.kind,
            "media_kind": self.media_kind,
            "source_path": self.source_path,
            "mtime_ns": self.mtime_ns,
            "settings": _json_safe(self.settings),
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha1(encoded.encode("utf-8")).hexdigest()

    def matches_key(self, key: object) -> bool:
        return self.key == str(key or "")


def _json_safe(value: object) -> object:
    if isinstance(value, MappingABC):
        return {str(key): _json_safe(inner) for key, inner in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_json_safe(item) for item in value]
    try:
        json.dumps(value, sort_keys=True)
        return value
    except TypeError:
        return str(value)
