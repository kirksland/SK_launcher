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


class FreshnessState:
    UP_TO_DATE = "up_to_date"
    STALE = "stale"
    NEEDS_REVIEW = "needs_review"
    INVALID = "invalid"
    MISSING_DEPENDENCY = "missing_dependency"

    ALL = {
        UP_TO_DATE,
        STALE,
        NEEDS_REVIEW,
        INVALID,
        MISSING_DEPENDENCY,
    }


@dataclass(frozen=True, slots=True)
class EntityRef:
    id: str
    kind: str
    project_id: str = ""
    task_id: str = ""
    label: str = ""
    path: str = ""

    def __post_init__(self) -> None:
        entity_id = _clean_token(self.id)
        kind = _clean_token(self.kind)
        if not entity_id:
            raise ValueError("EntityRef.id must be non-empty.")
        if not kind:
            raise ValueError("EntityRef.kind must be non-empty.")
        object.__setattr__(self, "id", entity_id)
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "project_id", _clean_token(self.project_id))
        object.__setattr__(self, "task_id", _clean_token(self.task_id))
        object.__setattr__(self, "label", _clean_label(self.label))
        object.__setattr__(self, "path", str(self.path or "").strip())


class TargetCapability:
    HOUDINI = "houdini"
    SOLARIS = "solaris"
    KARMA = "karma"
    USD = "usd"
    FFMPEG = "ffmpeg"
    OPENEXR = "openexr"
    OPENCV = "opencv"

    ALL = {
        HOUDINI,
        SOLARIS,
        KARMA,
        USD,
        FFMPEG,
        OPENEXR,
        OPENCV,
    }


@dataclass(frozen=True, slots=True)
class ExecutionTarget:
    id: str
    kind: str
    label: str
    capabilities: tuple[object, ...] = field(default_factory=tuple)
    available: bool = True
    environment_profile: str = ""
    reachable_roots: tuple[object, ...] = field(default_factory=tuple)
    sync_policy: str = ""

    _ALLOWED_KINDS = {
        "local_workstation",
        "client_machine",
        "pipeline_host",
        "render_host",
        "farm_node",
    }

    def __post_init__(self) -> None:
        target_id = _clean_token(self.id)
        label = _clean_label(self.label)
        if not target_id:
            raise ValueError("ExecutionTarget.id must be non-empty.")
        if not label:
            raise ValueError("ExecutionTarget.label must be non-empty.")
        object.__setattr__(self, "id", target_id)
        object.__setattr__(
            self,
            "kind",
            _validate_enum(self.kind, allowed=self._ALLOWED_KINDS, field_name="ExecutionTarget.kind"),
        )
        object.__setattr__(self, "label", label)
        object.__setattr__(self, "capabilities", _clean_tokens(tuple(self.capabilities)))
        object.__setattr__(self, "environment_profile", _clean_token(self.environment_profile))
        object.__setattr__(self, "reachable_roots", tuple(str(value or "").strip() for value in self.reachable_roots if str(value or "").strip()))
        object.__setattr__(self, "sync_policy", _clean_token(self.sync_policy))

    def supports(self, capability: object) -> bool:
        return _clean_token(capability) in self.capabilities
