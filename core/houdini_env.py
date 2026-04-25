from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Mapping, Optional

_DROP_ENV_KEYS = (
    "PYTHONHOME",
    "PYTHONPATH",
    "PYTHONSTARTUP",
    "PYTHONUSERBASE",
    "PYTHONEXECUTABLE",
    "VIRTUAL_ENV",
    "PYSIDE6_DIR",
    "QT_PLUGIN_PATH",
    "QT_QPA_PLATFORM_PLUGIN_PATH",
)


def _is_subpath(path_text: str, root_text: str) -> bool:
    normalized_path = os.path.normcase(os.path.abspath(path_text))
    normalized_root = os.path.normcase(os.path.abspath(root_text))
    return normalized_path == normalized_root or normalized_path.startswith(normalized_root + os.sep)


def build_houdini_env(
    *,
    base_env: Optional[Mapping[str, str]] = None,
    project_path: Optional[Path] = None,
    launcher_root: Optional[Path] = None,
) -> dict[str, str]:
    env = dict(base_env or os.environ)
    for key in _DROP_ENV_KEYS:
        env.pop(key, None)

    # Prevent Python user site packages (often where NumPy 2.x is installed) from leaking into Houdini.
    env["PYTHONNOUSERSITE"] = "1"

    if launcher_root is not None:
        venv_root = launcher_root / "venv"
        raw_path = env.get("PATH", "")
        filtered_entries: list[str] = []
        for entry in raw_path.split(os.pathsep):
            if not entry:
                continue
            if _is_subpath(entry, str(venv_root)):
                continue
            filtered_entries.append(entry)
        env["PATH"] = os.pathsep.join(filtered_entries)

    if project_path is not None:
        project_text = str(project_path)
        env["JOB"] = project_text
        env["HIP"] = project_text
        existing_hpath = env.get("HOUDINI_PATH", "")
        env["HOUDINI_PATH"] = f"{project_text};&" + (existing_hpath or "")

    return env


def resolve_hython_executable(executable: str) -> str:
    raw = str(executable or "").strip()
    if not raw:
        return ""
    candidate = Path(raw)
    if candidate.exists():
        if candidate.name.lower() == "houdini.exe":
            hython = candidate.with_name("hython.exe")
            if hython.exists():
                return str(hython)
        if candidate.name.lower() == "hython.exe":
            return str(candidate)
        return ""
    token = raw.lower()
    if token == "houdini":
        return shutil.which("hython") or ""
    if token in {"hython", "hython.exe"}:
        return shutil.which("hython") or shutil.which("hython.exe") or ""
    which_value = shutil.which(raw)
    if which_value and Path(which_value).name.lower() in {"hython", "hython.exe"}:
        return which_value
    return ""
