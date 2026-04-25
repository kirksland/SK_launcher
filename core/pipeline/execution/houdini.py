from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from core.houdini_env import build_houdini_env
from core.pipeline.jobs.requests import RuntimeProcessRequest

from .result import ExecutionResult, ExecutionStatus, ProducedOutput


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
    runner_path: str = "houdini_pipeline.process_runner",
) -> HoudiniExecutionPlan | None:
    if request is None:
        return None
    payload = build_houdini_request_payload(request)
    command_preview = (
        executable,
        "-m",
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
    runner_path: str = "houdini_pipeline.process_runner",
    launcher_root: Path | None = None,
    project_path: Path | None = None,
    run_subprocess: bool = False,
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
    if not run_subprocess:
        return ExecutionResult(
            status=ExecutionStatus.SKIPPED,
            message="Houdini backend plan is ready, but no real process runner is wired yet.",
            payload={
                "command_preview": tuple(plan.command_preview),
                "request_payload": plan.request_payload,
            },
        )
    resolved_executable = _resolve_hython_executable(executable)
    if not resolved_executable:
        return ExecutionResult(
            status=ExecutionStatus.FAILED,
            message="Could not resolve a valid hython executable for Houdini process execution.",
            payload={
                "command_preview": tuple(plan.command_preview),
                "request_payload": plan.request_payload,
            },
        )
    return _execute_houdini_subprocess(
        plan,
        executable=resolved_executable,
        runner_path=runner_path,
        launcher_root=launcher_root,
        project_path=project_path,
    )


def _resolve_hython_executable(executable: str) -> str:
    raw = str(executable or "").strip()
    if not raw:
        return ""
    candidate = Path(raw)
    if candidate.exists():
        if candidate.name.lower() == "houdini.exe":
            hython = candidate.with_name("hython.exe")
            if hython.exists():
                return str(hython)
        return str(candidate)
    if raw.lower() == "houdini":
        which_hython = shutil.which("hython")
        return which_hython or ""
    if raw.lower() == "hython":
        return shutil.which("hython") or ""
    which_value = shutil.which(raw)
    return which_value or ""


def _execution_result_from_payload(payload: dict[str, object]) -> ExecutionResult:
    outputs = []
    for item in payload.get("outputs", []) or []:
        if not isinstance(item, dict):
            continue
        try:
            outputs.append(
                ProducedOutput(
                    kind=item.get("kind", ""),
                    path=item.get("path", ""),
                    label=item.get("label", ""),
                )
            )
        except ValueError:
            continue
    return ExecutionResult(
        status=str(payload.get("status", "")),
        message=str(payload.get("message", "")),
        outputs=tuple(outputs),
        log_path=str(payload.get("log_path", "")),
        payload=payload.get("payload", {}) if isinstance(payload.get("payload"), dict) else {},
    )


def _execute_houdini_subprocess(
    plan: HoudiniExecutionPlan,
    *,
    executable: str,
    runner_path: str,
    launcher_root: Path | None,
    project_path: Path | None,
) -> ExecutionResult:
    working_root = Path(launcher_root) if launcher_root is not None else Path(__file__).resolve().parents[3]
    env = build_houdini_env(
        base_env=None,
        project_path=project_path,
        launcher_root=working_root,
    )
    request_file_path = Path(tempfile.gettempdir()) / f"skyforge_process_request_{next(tempfile._get_candidate_names())}.json"
    request_file_path.write_text(json.dumps(plan.request_payload, indent=2, sort_keys=True), encoding="utf-8")
    command = [
        executable,
        "-m",
        runner_path,
        "--request-file",
        str(request_file_path),
    ]
    try:
        completed = subprocess.run(
            command,
            cwd=str(working_root),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception as exc:
        return ExecutionResult(
            status=ExecutionStatus.FAILED,
            message=f"Failed to launch Houdini process runner: {exc}",
            payload={"command_preview": tuple(command)},
        )
    finally:
        request_file_path.unlink(missing_ok=True)

    stdout_text = str(completed.stdout or "").strip()
    if stdout_text:
        try:
            payload = json.loads(stdout_text)
            if isinstance(payload, dict):
                return _execution_result_from_payload(payload)
        except json.JSONDecodeError:
            pass
    stderr_text = str(completed.stderr or "").strip()
    return ExecutionResult(
        status=ExecutionStatus.FAILED,
        message=stderr_text or stdout_text or f"Houdini process runner exited with code {completed.returncode}.",
        payload={
            "command_preview": tuple(command),
            "returncode": completed.returncode,
        },
    )
