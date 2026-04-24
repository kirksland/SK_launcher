from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path
from typing import Any


def _load_request(args: argparse.Namespace) -> dict[str, Any]:
    if args.request_json:
        return json.loads(args.request_json)
    if args.request_file:
        return json.loads(Path(args.request_file).read_text(encoding="utf-8"))
    raise ValueError("A request payload must be provided.")


def _process_module_name(process_id: object) -> str:
    key = str(process_id or "").strip().lower()
    if not key:
        raise ValueError("Request is missing process_id.")
    return f"houdini_pipeline.processes.{key.replace('.', '_')}"


def _normalize_result(result: dict[str, Any] | None) -> dict[str, Any]:
    payload = dict(result or {})
    payload.setdefault("status", "failed")
    payload.setdefault("message", "Process did not return a message.")
    payload.setdefault("outputs", [])
    payload.setdefault("log_path", "")
    payload.setdefault("payload", {})
    return payload


def dispatch_process(request: dict[str, Any]) -> dict[str, Any]:
    module = importlib.import_module(_process_module_name(request.get("process_id")))
    if not hasattr(module, "run"):
        raise RuntimeError(f"Process module '{module.__name__}' does not expose run(request).")
    result = module.run(request)
    if not isinstance(result, dict):
        raise RuntimeError(f"Process module '{module.__name__}' must return a dict result.")
    return _normalize_result(result)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a registered Houdini pipeline process.")
    parser.add_argument("--request-json", dest="request_json", help="Inline JSON runtime request payload.")
    parser.add_argument("--request-file", dest="request_file", help="Path to a JSON runtime request payload.")
    args = parser.parse_args(argv)

    try:
        request = _load_request(args)
        result = dispatch_process(request)
    except Exception as exc:
        result = _normalize_result(
            {
                "status": "failed",
                "message": str(exc),
                "payload": {"exception_type": exc.__class__.__name__},
            }
        )

    sys.stdout.write(json.dumps(result, indent=2, sort_keys=True))
    sys.stdout.write("\n")
    return 0 if result.get("status") == "succeeded" else 1


if __name__ == "__main__":
    raise SystemExit(main())
