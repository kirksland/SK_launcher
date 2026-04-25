from __future__ import annotations

from dataclasses import dataclass, field


def _clean_token(value: object) -> str:
    return str(value or "").strip().lower()


def _clean_label(value: object) -> str:
    return str(value or "").strip()


def _clean_tokens(values: tuple[object, ...]) -> tuple[str, ...]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values:
        token = _clean_token(value)
        if not token or token in seen:
            continue
        seen.add(token)
        cleaned.append(token)
    return tuple(cleaned)


def _validate_enum(value: object, *, allowed: set[str], field_name: str) -> str:
    token = _clean_token(value)
    if token not in allowed:
        raise ValueError(f"{field_name} must be one of {sorted(allowed)}.")
    return token


class ProcessFamily:
    BUILD = "build"
    PUBLISH = "publish"
    REFRESH = "refresh"
    VALIDATE = "validate"
    EXPORT = "export"
    SYNC = "sync"
    REVIEW = "review"

    ALL = {
        BUILD,
        PUBLISH,
        REFRESH,
        VALIDATE,
        EXPORT,
        SYNC,
        REVIEW,
    }


@dataclass(frozen=True, slots=True)
class ProcessDefinition:
    id: str
    label: str
    family: str
    entity_kinds: tuple[object, ...] = field(default_factory=tuple)
    required_capabilities: tuple[object, ...] = field(default_factory=tuple)
    outputs: tuple[object, ...] = field(default_factory=tuple)
    deterministic: bool = True
    destructive: bool = False
    review_required: bool = False
    supports_remote: bool = False
    description: str = ""

    def __post_init__(self) -> None:
        process_id = _clean_token(self.id)
        label = _clean_label(self.label)
        if not process_id:
            raise ValueError("ProcessDefinition.id must be non-empty.")
        if not label:
            raise ValueError("ProcessDefinition.label must be non-empty.")
        kinds = _clean_tokens(tuple(self.entity_kinds))
        if not kinds:
            raise ValueError("ProcessDefinition.entity_kinds must declare at least one supported entity kind.")
        object.__setattr__(self, "id", process_id)
        object.__setattr__(self, "label", label)
        object.__setattr__(
            self,
            "family",
            _validate_enum(self.family, allowed=ProcessFamily.ALL, field_name="ProcessDefinition.family"),
        )
        object.__setattr__(self, "entity_kinds", kinds)
        object.__setattr__(self, "required_capabilities", _clean_tokens(tuple(self.required_capabilities)))
        object.__setattr__(self, "outputs", _clean_tokens(tuple(self.outputs)))
        object.__setattr__(self, "description", _clean_label(self.description))

    def supports_entity_kind(self, kind: object) -> bool:
        return _clean_token(kind) in self.entity_kinds
