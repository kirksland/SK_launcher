from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Optional

DEFAULT_PROJECTS_DIR = Path(r"C:\Users\justi\Documents\HoudiniProjects")
DEFAULT_TEMPLATE_HIP = Path(r"C:\Users\justi\Documents\HoudiniProjects\newProject2\newfile_001.hipnc")
SETTINGS_PATH = Path(__file__).resolve().parent.parent / "settings.json"

DEFAULT_ASSET_SCHEMA = {
    "usd_search": ["publish", "root"],
}

DEFAULT_SETTINGS: Dict[str, object] = {
    "projects_dir": str(DEFAULT_PROJECTS_DIR),
    "template_hip": str(DEFAULT_TEMPLATE_HIP),
    "new_hip_pattern": "{projectName}_001.hipnc",
    "use_file_association": True,
    "houdini_exe": "",
    "server_repo_dir": r"C:\Users\justi\Documents\studio project\StudioProject",
    "video_backend": "auto",
    "asset_manager_projects": [],
    "asset_schema": DEFAULT_ASSET_SCHEMA,
}


def _default_settings_with_latest_houdini() -> Dict[str, object]:
    defaults = DEFAULT_SETTINGS.copy()
    installs = discover_houdini_installations()
    if installs:
        defaults["houdini_exe"] = installs[0]["path"]
        defaults["use_file_association"] = False
    return defaults


def load_settings() -> Dict[str, object]:
    if not SETTINGS_PATH.exists():
        return _default_settings_with_latest_houdini()
    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return _default_settings_with_latest_houdini()
    merged = DEFAULT_SETTINGS.copy()
    merged.update({
        k: v
        for k, v in data.items()
        if isinstance(v, (str, bool, int, float, list, dict))
    })
    if isinstance(data.get("asset_manager_projects"), list):
        merged["asset_manager_projects"] = data["asset_manager_projects"]
    if isinstance(data.get("asset_schema"), dict):
        merged["asset_schema"] = data["asset_schema"]
    # If settings predate houdini_exe storage, default to latest install.
    if "houdini_exe" not in data:
        installs = discover_houdini_installations()
        if installs:
            merged["houdini_exe"] = installs[0]["path"]
            if "use_file_association" not in data:
                merged["use_file_association"] = False
    return merged


def save_settings(settings: Dict[str, object]) -> None:
    SETTINGS_PATH.write_text(json.dumps(settings, indent=2), encoding="utf-8")


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


def normalize_asset_schema(raw: object) -> Dict[str, List[str]]:
    if not isinstance(raw, dict):
        return DEFAULT_ASSET_SCHEMA.copy()
    usd_search = raw.get("usd_search")
    if not isinstance(usd_search, list):
        return DEFAULT_ASSET_SCHEMA.copy()
    cleaned = []
    for value in usd_search:
        if not isinstance(value, str):
            continue
        key = value.strip().lower()
        if key in ("publish", "root") and key not in cleaned:
            cleaned.append(key)
    if not cleaned:
        cleaned = DEFAULT_ASSET_SCHEMA["usd_search"][:]
    return {"usd_search": cleaned}

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
