from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.asset_schema import (
    DEFAULT_ASSET_SCHEMA,
    default_asset_schema,
    normalize_asset_schema as normalize_asset_schema_config,
)

LAUNCHER_ROOT = Path(__file__).resolve().parent.parent
LEGACY_SETTINGS_PATH = LAUNCHER_ROOT / "settings.json"


def _documents_dir() -> Path:
    home = Path.home()
    documents = home / "Documents"
    return documents if documents.exists() else home


DEFAULT_PROJECTS_DIR = _documents_dir() / "HoudiniProjects"
DEFAULT_TEMPLATE_HIP = LAUNCHER_ROOT / "untitled.hipnc"
DEFAULT_SERVER_REPO_DIR = _documents_dir() / "StudioProject"

DEFAULT_SETTINGS: Dict[str, object] = {
    "projects_dir": str(DEFAULT_PROJECTS_DIR),
    "template_hip": str(DEFAULT_TEMPLATE_HIP),
    "new_hip_pattern": "{projectName}_001.hipnc",
    "use_file_association": True,
    "show_splash_screen": True,
    "houdini_exe": "",
    "server_repo_dir": str(DEFAULT_SERVER_REPO_DIR),
    "video_backend": "auto",
    "asset_manager_projects": [],
    "asset_schema": default_asset_schema(),
    "asset_project_schemas": {},
    "shortcuts": {},
    "runtime_cache_location": "local_appdata",
    "runtime_cache_max_gb": 5,
    "runtime_cache_max_days": 30,
}


def user_settings_dir() -> Path:
    appdata = os.getenv("APPDATA")
    if appdata:
        return Path(appdata) / "SkyforgeLauncher"
    return _documents_dir() / "SkyforgeLauncher"


def user_settings_path() -> Path:
    return user_settings_dir() / "settings.json"


def active_settings_path(
    *,
    explicit_path: Optional[Path] = None,
    legacy_path: Path = LEGACY_SETTINGS_PATH,
    user_path: Optional[Path] = None,
) -> Path:
    if explicit_path is not None:
        return explicit_path
    env_path = os.getenv("SKYFORGE_SETTINGS_PATH", "").strip()
    if env_path:
        return Path(env_path)
    if legacy_path.exists():
        return legacy_path
    return user_path or user_settings_path()


def is_first_run(settings_path: Optional[Path] = None) -> bool:
    return not active_settings_path(explicit_path=settings_path).exists()


def _default_settings_with_latest_houdini() -> Dict[str, object]:
    defaults = DEFAULT_SETTINGS.copy()
    defaults["asset_schema"] = default_asset_schema()
    installs = discover_houdini_installations()
    if installs:
        defaults["houdini_exe"] = installs[0]["path"]
        defaults["use_file_association"] = False
    return defaults


def load_settings(settings_path: Optional[Path] = None) -> Dict[str, object]:
    resolved_path = active_settings_path(explicit_path=settings_path)
    if not resolved_path.exists():
        return _default_settings_with_latest_houdini()
    try:
        data = json.loads(resolved_path.read_text(encoding="utf-8"))
    except Exception:
        return _default_settings_with_latest_houdini()
    merged = DEFAULT_SETTINGS.copy()
    merged["asset_schema"] = default_asset_schema()
    merged.update({
        k: v
        for k, v in data.items()
        if isinstance(v, (str, bool, int, float, list, dict))
    })
    if isinstance(data.get("asset_manager_projects"), list):
        merged["asset_manager_projects"] = data["asset_manager_projects"]
    if isinstance(data.get("asset_schema"), dict):
        merged["asset_schema"] = normalize_asset_schema_config(data["asset_schema"])
    if isinstance(data.get("asset_project_schemas"), dict):
        merged["asset_project_schemas"] = normalize_asset_project_schemas(data["asset_project_schemas"])
    merged["shortcuts"] = normalize_shortcuts(data.get("shortcuts"))
    merged["runtime_cache_location"] = normalize_runtime_cache_location(data.get("runtime_cache_location"))
    merged["runtime_cache_max_gb"] = _coerce_positive_int(
        data.get("runtime_cache_max_gb"),
        int(DEFAULT_SETTINGS["runtime_cache_max_gb"]),
    )
    merged["runtime_cache_max_days"] = _coerce_positive_int(
        data.get("runtime_cache_max_days"),
        int(DEFAULT_SETTINGS["runtime_cache_max_days"]),
    )
    # If settings predate houdini_exe storage, default to latest install.
    if "houdini_exe" not in data:
        installs = discover_houdini_installations()
        if installs:
            merged["houdini_exe"] = installs[0]["path"]
            if "use_file_association" not in data:
                merged["use_file_association"] = False
    template_hip = str(merged.get("template_hip", "")).strip()
    if (not template_hip or not Path(template_hip).exists()) and DEFAULT_TEMPLATE_HIP.exists():
        merged["template_hip"] = str(DEFAULT_TEMPLATE_HIP)
    return merged


def save_settings(settings: Dict[str, object], settings_path: Optional[Path] = None) -> None:
    resolved_path = active_settings_path(explicit_path=settings_path)
    resolved_path.parent.mkdir(parents=True, exist_ok=True)
    serializable = dict(settings)
    serializable["asset_schema"] = normalize_asset_schema_config(serializable.get("asset_schema"))
    serializable["asset_project_schemas"] = normalize_asset_project_schemas(
        serializable.get("asset_project_schemas")
    )
    serializable["shortcuts"] = normalize_shortcuts(serializable.get("shortcuts"))
    serializable["runtime_cache_location"] = normalize_runtime_cache_location(
        serializable.get("runtime_cache_location")
    )
    serializable["runtime_cache_max_gb"] = _coerce_positive_int(
        serializable.get("runtime_cache_max_gb"),
        int(DEFAULT_SETTINGS["runtime_cache_max_gb"]),
    )
    serializable["runtime_cache_max_days"] = _coerce_positive_int(
        serializable.get("runtime_cache_max_days"),
        int(DEFAULT_SETTINGS["runtime_cache_max_days"]),
    )
    resolved_path.write_text(json.dumps(serializable, indent=2), encoding="utf-8")


def settings_startup_issues(settings: Dict[str, object]) -> List[str]:
    issues: List[str] = []

    projects_dir = str(settings.get("projects_dir", "")).strip()
    server_repo_dir = str(settings.get("server_repo_dir", "")).strip()
    template_hip = str(settings.get("template_hip", "")).strip()
    use_assoc = bool(settings.get("use_file_association", True))
    houdini_exe = str(settings.get("houdini_exe", "")).strip()

    if not projects_dir or not Path(projects_dir).exists():
        issues.append("Projects Folder")
    if not server_repo_dir or not Path(server_repo_dir).exists():
        issues.append("Server Repo Folder")
    if not template_hip or not Path(template_hip).exists():
        issues.append("Template Hip")
    if not use_assoc and (not houdini_exe or not Path(houdini_exe).exists()):
        issues.append("Houdini Executable")

    return issues


def normalize_asset_manager_projects(raw: object) -> List[Dict[str, Optional[str]]]:
    if not isinstance(raw, list):
        return []
    cleaned: List[Dict[str, Optional[str]]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        local_path = item.get("local_path")
        if not isinstance(local_path, str) or not local_path.strip():
            continue
        client_id = item.get("client_id")
        if not isinstance(client_id, str) or not client_id.strip():
            client_id = None
        cleaned.append({"local_path": local_path.strip(), "client_id": client_id})
    return cleaned


def normalize_asset_schema(raw: object) -> Dict[str, Any]:
    return normalize_asset_schema_config(raw)


def normalize_asset_project_schemas(raw: object) -> Dict[str, Dict[str, Any]]:
    if not isinstance(raw, dict):
        return {}
    cleaned: Dict[str, Dict[str, Any]] = {}
    for project_key, value in raw.items():
        if not isinstance(project_key, str) or not project_key.strip():
            continue
        cleaned[project_key.strip()] = normalize_asset_schema_config(value)
    return cleaned


def normalize_shortcuts(raw: object) -> Dict[str, List[str]]:
    if not isinstance(raw, dict):
        return {}
    cleaned: Dict[str, List[str]] = {}
    for command_id, sequences in raw.items():
        if not isinstance(command_id, str) or not command_id.strip():
            continue
        if isinstance(sequences, str):
            sequence_list = [sequences]
        elif isinstance(sequences, list):
            sequence_list = sequences
        else:
            continue
        normalized = [sequence.strip() for sequence in sequence_list if isinstance(sequence, str) and sequence.strip()]
        cleaned[command_id.strip()] = normalized
    return cleaned


def normalize_runtime_cache_location(raw: object) -> str:
    text = str(raw or "").strip().lower()
    if text == "project":
        return "project"
    return "local_appdata"


def _coerce_positive_int(raw: object, default: int) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return int(default)
    return value if value > 0 else int(default)

def normalize_houdini_exe(path_text: str) -> str:
    path_text = path_text.strip().strip('"')
    if not path_text:
        return ""
    p = Path(path_text)
    if p.is_dir():
        candidate = p / "houdini.exe"
        return str(candidate)
    return str(p)


def discover_houdini_installations() -> List[Dict[str, str]]:
    bases = [
        Path(r"C:\Program Files\Side Effects Software"),
        Path(r"C:\Program Files\Side Effects Software\Houdini"),
    ]
    found: List[Dict[str, str]] = []
    for base in bases:
        if not base.exists():
            continue
        try:
            children = list(base.iterdir())
        except OSError:
            continue
        for child in children:
            if not child.is_dir():
                continue
            exe = child / "bin" / "houdini.exe"
            if exe.exists():
                found.append({"label": child.name, "path": str(exe)})

    def version_key(label: str) -> tuple:
        match = re.search(r"(\d+)\.(\d+)\.(\d+)", label)
        if not match:
            return (0, 0, 0, label.lower())
        return (
            int(match.group(1)),
            int(match.group(2)),
            int(match.group(3)),
            label.lower(),
        )

    found.sort(key=lambda item: version_key(item["label"]), reverse=True)

    deduped: List[Dict[str, str]] = []
    seen = set()
    for item in found:
        path_key = item["path"].lower()
        if path_key in seen:
            continue
        seen.add(path_key)
        deduped.append(item)
    return deduped
