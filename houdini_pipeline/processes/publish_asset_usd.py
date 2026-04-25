from __future__ import annotations

import os
from pathlib import Path
from typing import Any

PROCESS_ID = "publish.asset.usd"
HDA_TYPE_NAME = "justi::sf_publish_asset_usd::1.0"
HDA_PARAM_SOURCE = "source"
HDA_PARAM_OUTPUT = "output"
HDA_PARAM_CONTEXT = "context"
HDA_PARAM_EXECUTE = "execute"


def _request_param(request: dict[str, Any], key: str) -> str:
    return str((request.get("parameters") or {}).get(key, "") or "").strip()


def _fallback_param(request: dict[str, Any], key: str) -> str:
    return str(request.get(key, "") or "").strip()


def _build_process_inputs(request: dict[str, Any]) -> tuple[str, str, str]:
    source = _request_param(request, HDA_PARAM_SOURCE) or _fallback_param(request, HDA_PARAM_SOURCE)
    output = _request_param(request, HDA_PARAM_OUTPUT) or _fallback_param(request, HDA_PARAM_OUTPUT)
    context = _request_param(request, HDA_PARAM_CONTEXT) or _fallback_param(request, HDA_PARAM_CONTEXT)
    if not source:
        raise ValueError("publish.asset.usd requires a non-empty 'source' parameter.")
    if not output:
        raise ValueError("publish.asset.usd requires a non-empty 'output' parameter.")
    if not context:
        raise ValueError("publish.asset.usd requires a non-empty 'context' parameter.")
    return source, output, context


def _build_stub_result(source: str, output: str, context: str) -> dict[str, Any]:
    return {
        "status": "skipped",
        "message": "publish.asset.usd request validated. HDA execution is not wired yet.",
        "outputs": [
            {
                "kind": "usd",
                "path": output,
                "label": Path(output).name,
            }
        ],
        "log_path": "",
        "payload": {
            "process_id": PROCESS_ID,
            "hda_type_name": HDA_TYPE_NAME,
            "parameter_mapping": {
                "source": HDA_PARAM_SOURCE,
                "output": HDA_PARAM_OUTPUT,
                "context": HDA_PARAM_CONTEXT,
            },
            "validated_inputs": {
                "source": source,
                "output": output,
                "context": context,
            },
        },
    }


def _load_hou() -> Any | None:
    try:
        import hou  # type: ignore
    except ImportError:
        return None
    return hou


def _ensure_stage_parent(hou_module: Any) -> Any:
    stage = hou_module.node("/stage")
    if stage is not None:
        return stage
    root = hou_module.node("/")
    if root is None:
        raise RuntimeError("Could not resolve Houdini root node '/'.")
    return root.createNode("lopnet", "stage")


def _set_required_parms(node: Any, source: str, output: str, context: str) -> None:
    values = {
        HDA_PARAM_SOURCE: source,
        HDA_PARAM_OUTPUT: output,
        HDA_PARAM_CONTEXT: context,
    }
    for parm_name, parm_value in values.items():
        parm = node.parm(parm_name)
        if parm is None:
            raise RuntimeError(f"HDA '{HDA_TYPE_NAME}' is missing required parameter '{parm_name}'.")
        parm.set(parm_value)


def _trigger_execution(node: Any) -> None:
    execute_parm = node.parm(HDA_PARAM_EXECUTE)
    if execute_parm is not None and hasattr(execute_parm, "pressButton"):
        execute_parm.pressButton()
        return
    node.cook(force=True)


def _execute_hda(source: str, output: str, context: str, hou_module: Any) -> dict[str, Any]:
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    parent = _ensure_stage_parent(hou_module)
    node = parent.createNode(HDA_TYPE_NAME)
    try:
        _set_required_parms(node, source, output, context)
        _trigger_execution(node)
    except Exception:
        try:
            node.destroy()
        finally:
            raise

    try:
        if not output_path.exists():
            return {
                "status": "failed",
                "message": (
                    f"publish.asset.usd cooked HDA '{HDA_TYPE_NAME}' but no output file was produced "
                    f"at '{output}'."
                ),
                "outputs": [],
                "log_path": "",
                "payload": {
                    "process_id": PROCESS_ID,
                    "hda_type_name": HDA_TYPE_NAME,
                    "parameter_mapping": {
                        "source": HDA_PARAM_SOURCE,
                        "output": HDA_PARAM_OUTPUT,
                        "context": HDA_PARAM_CONTEXT,
                    },
                    "validated_inputs": {
                        "source": source,
                        "output": output,
                        "context": context,
                    },
                    "execution_mode": "houdini_headless",
                },
            }
        return {
            "status": "succeeded",
            "message": f"publish.asset.usd executed via HDA '{HDA_TYPE_NAME}'.",
            "outputs": [
                {
                    "kind": "usd",
                    "path": output,
                    "label": output_path.name,
                }
            ],
            "log_path": "",
            "payload": {
                "process_id": PROCESS_ID,
                "hda_type_name": HDA_TYPE_NAME,
                "parameter_mapping": {
                    "source": HDA_PARAM_SOURCE,
                    "output": HDA_PARAM_OUTPUT,
                    "context": HDA_PARAM_CONTEXT,
                },
                "validated_inputs": {
                    "source": source,
                    "output": output,
                    "context": context,
                },
                "execution_mode": "houdini_headless",
            },
        }
    finally:
        node.destroy()


def run(request: dict[str, Any], hou_module: Any | None = None) -> dict[str, Any]:
    source, output, context = _build_process_inputs(request)
    active_hou = hou_module if hou_module is not None else _load_hou()
    if active_hou is None:
        return _build_stub_result(source, output, context)
    if not os.path.exists(source):
        raise ValueError(f"publish.asset.usd source does not exist: {source}")
    return _execute_hda(source, output, context, active_hou)
