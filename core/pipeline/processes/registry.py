from __future__ import annotations

from .definitions import ProcessDefinition, ProcessFamily


_DEFAULT_PROCESS_DEFINITIONS = (
    ProcessDefinition(
        id="validate.asset.readiness",
        label="Validate Asset Readiness",
        family=ProcessFamily.VALIDATE,
        entity_kinds=("pipeline_asset", "library_asset", "asset"),
        outputs=("validation_report",),
        description="Check whether the selected asset has the expected published outputs and review media.",
    ),
    ProcessDefinition(
        id="publish.asset.usd",
        label="Publish Asset USD",
        family=ProcessFamily.PUBLISH,
        entity_kinds=("pipeline_asset", "library_asset", "asset"),
        required_capabilities=("houdini", "usd"),
        outputs=("usd_asset",),
        supports_remote=True,
        description="Build or refresh the published USD package for the selected asset.",
    ),
    ProcessDefinition(
        id="export.review.media",
        label="Export Review Media",
        family=ProcessFamily.EXPORT,
        entity_kinds=("shot", "pipeline_asset", "asset"),
        required_capabilities=("ffmpeg",),
        outputs=("review_media",),
        supports_remote=True,
        description="Generate or refresh review-ready media outputs for the current entity.",
    ),
    ProcessDefinition(
        id="refresh.shot.assembly",
        label="Refresh Shot Assembly",
        family=ProcessFamily.REFRESH,
        entity_kinds=("shot",),
        required_capabilities=("houdini", "solaris", "usd"),
        outputs=("usd_shot", "review_media"),
        supports_remote=True,
        description="Refresh the shot-level assembly from the latest published upstream data.",
    ),
)


def list_process_definitions() -> tuple[ProcessDefinition, ...]:
    return _DEFAULT_PROCESS_DEFINITIONS


def available_processes_for_entity_kind(kind: object) -> tuple[ProcessDefinition, ...]:
    entity_kind = str(kind or "").strip().lower()
    if not entity_kind:
        return ()
    return tuple(
        process for process in _DEFAULT_PROCESS_DEFINITIONS if process.supports_entity_kind(entity_kind)
    )
