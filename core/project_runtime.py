from __future__ import annotations

from pathlib import Path
from typing import Optional, Sequence

PROJECT_SUBDIRS = (
    "abc",
    "audio",
    "comp",
    "desk",
    "flip",
    "geo",
    "hda",
    "render",
    "scripts",
    "sim",
    "tex",
    "video",
)
JOB_INIT_MARKER = ".skyforge_job_init"


def create_project_structure(project_path: Path, subdirs: Sequence[str] = PROJECT_SUBDIRS) -> None:
    project_path.mkdir(parents=True, exist_ok=False)
    for subdir in subdirs:
        (project_path / subdir).mkdir(parents=False, exist_ok=True)


def resolve_new_hip_name(pattern: str, project_name: str) -> str:
    normalized = pattern.strip() or "{projectName}_001.hipnc"
    try:
        return normalized.format(projectName=project_name)
    except Exception:
        return f"{project_name}_001.hipnc"


def template_candidates(
    custom_template: Optional[Path],
    default_template: Optional[Path],
    launcher_root: Path,
) -> list[Path]:
    candidates = [custom_template, default_template, launcher_root / "untitled.hipnc"]
    return [candidate for candidate in candidates if candidate is not None]


def resolve_template_hip(
    custom_template: Optional[Path],
    default_template: Optional[Path],
    launcher_root: Path,
) -> Optional[Path]:
    for candidate in template_candidates(custom_template, default_template, launcher_root):
        if candidate.exists():
            return candidate
    return None


def ensure_template_hip(
    project_path: Path,
    *,
    pattern: str,
    custom_template: Optional[Path],
    default_template: Optional[Path],
    launcher_root: Path,
) -> tuple[Optional[Path], Optional[str]]:
    template = resolve_template_hip(custom_template, default_template, launcher_root)
    if template is None:
        missing = "\n".join(str(path) for path in template_candidates(custom_template, default_template, launcher_root))
        return None, f"Template hip not found. Checked:\n{missing}"

    target_name = resolve_new_hip_name(pattern, project_path.name)
    target = project_path / target_name
    if target.exists():
        return target, None
    try:
        target.write_bytes(template.read_bytes())
    except Exception as exc:
        return None, f"Failed to copy template hip:\n{exc}"
    return target, None


def build_job_script_content(project_path: Path) -> str:
    return (
        "import os\n"
        "try:\n"
        "    import hou\n"
        "except Exception:\n"
        "    hou = None\n"
        f"project_path = r\"{project_path}\"\n"
        "os.environ[\"JOB\"] = project_path\n"
        "if hou is not None:\n"
        "    hou.putenv(\"JOB\", project_path)\n"
    )


def ensure_job_scripts(project_path: Path, script_names: Sequence[str] = ("123.py", "456.py")) -> None:
    scripts_dir = project_path / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    content = build_job_script_content(project_path)
    for name in script_names:
        try:
            (scripts_dir / name).write_text(content, encoding="utf-8")
        except Exception:
            continue


def ensure_job_scripts_if_needed(project_path: Path, marker_name: str = JOB_INIT_MARKER) -> bool:
    marker = project_path / marker_name
    if not marker.exists():
        return False
    ensure_job_scripts(project_path)
    try:
        marker.unlink()
    except Exception:
        pass
    return True
