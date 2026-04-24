from __future__ import annotations

import json
from dataclasses import dataclass

from core.pipeline.jobs.requests import RuntimeProcessRequest

from .result import ExecutionResult, ExecutionStatus


@dataclass(frozen=True, slots=True)
class HoudiniExecutionPlan:
    executable: str
    headless: bool
    request_payload: dict[str, object]
    command_preview: tuple[str, ...]


def build_houdini_request_payload(request: RuntimeProcessRequest) -> dict[str, object]:
    return {
        "process_id": request.process_id,
        "entity": {
            "id": request.target_entity.id,
            "kind": request.target_entity.kind,
            "label": request.target_entity.label,
            "path": request.target_entity.path,
        },
        "execution_target": {
            "id": request.execution_target.id,
            "kind": request.execution_target.kind,
            "label": request.execution_target.label,
        },
        "parameters": dict(request.parameters),
    }


def build_houdini_execution_plan(
    request: RuntimeProcessRequest | None,
    *,
    executable: str = "hython",
    runner_path: str = "houdini_pipeline/process_runner.py",
) -> HoudiniExecutionPlan | None:
    if request is None:
        return None
    payload = build_houdini_request_payload(request)
    command_preview = (
        executable,
        runner_path,
        "--request-json",
        json.dumps(payload, sort_keys=True),
    )
    return HoudiniExecutionPlan(
        executable=executable,
        headless=True,
        request_payload=payload,
        command_preview=command_preview,
    )


def execute_houdini_request(
    request: RuntimeProcessRequest | None,
    *,
    executable: str = "hython",
    runner_path: str = "houdini_pipeline/process_runner.py",
) -> ExecutionResult:
    if request is None:
        return ExecutionResult(
            status=ExecutionStatus.FAILED,
            message="No runtime request was provided.",
        )
    plan = build_houdini_execution_plan(
        request,
        executable=executable,
        runner_path=runner_path,
    )
    if plan is None:
        return ExecutionResult(
            status=ExecutionStatus.FAILED,
            message="Unable to build a Houdini execution plan.",
        )
    if request.capability_gaps:
        return ExecutionResult(
            status=ExecutionStatus.BLOCKED,
            message="Runtime request is missing required target capabilities.",
            payload={
                "capability_gaps": tuple(request.capability_gaps),
                "command_preview": tuple(plan.command_preview),
            },
        )
    return ExecutionResult(
        status=ExecutionStatus.SKIPPED,
        message="Houdini backend plan is ready, but no real process runner is wired yet.",
        payload={
            "command_preview": tuple(plan.command_preview),
            "request_payload": plan.request_payload,
        },
    )
