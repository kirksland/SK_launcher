import unittest
from pathlib import Path
from uuid import uuid4

from core.project_runtime import (
    JOB_INIT_MARKER,
    build_job_script_content,
    ensure_job_scripts_if_needed,
    ensure_template_hip,
    resolve_new_hip_name,
)


class ProjectRuntimeTests(unittest.TestCase):
    def _make_case_dir(self, name: str) -> Path:
        path = Path("tests") / ".tmp" / f"{name}_{uuid4().hex}"
        path.mkdir(parents=True, exist_ok=False)
        self.addCleanup(self._cleanup_dir, path)
        return path

    @staticmethod
    def _cleanup_dir(path: Path) -> None:
        if not path.exists():
            return
        for child in sorted(path.rglob("*"), reverse=True):
            if child.is_file():
                child.unlink(missing_ok=True)
            elif child.is_dir():
                child.rmdir()
        path.rmdir()

    def test_resolve_new_hip_name_handles_invalid_pattern(self) -> None:
        self.assertEqual(resolve_new_hip_name("{oops", "Demo"), "Demo_001.hipnc")

    def test_ensure_template_hip_copies_missing_target(self) -> None:
        root = self._make_case_dir("project_runtime")
        project = root / "Demo"
        project.mkdir()
        template = root / "template.hipnc"
        template.write_text("hip", encoding="utf-8")
        target, error = ensure_template_hip(
            project,
            pattern="{projectName}_001.hipnc",
            custom_template=template,
            default_template=None,
            launcher_root=root,
        )
        self.assertIsNone(error)
        self.assertEqual(target, project / "Demo_001.hipnc")
        self.assertEqual(target.read_text(encoding="utf-8"), "hip")

    def test_build_job_script_content_contains_job_env(self) -> None:
        content = build_job_script_content(Path("C:/Demo"))
        self.assertIn("os.environ[\"JOB\"]", content)
        self.assertIn("project_path =", content)
        self.assertIn("Demo", content)

    def test_ensure_job_scripts_if_needed_creates_scripts_and_removes_marker(self) -> None:
        project = self._make_case_dir("project_scripts")
        marker = project / JOB_INIT_MARKER
        marker.write_text("init", encoding="utf-8")
        changed = ensure_job_scripts_if_needed(project)
        self.assertTrue(changed)
        self.assertFalse(marker.exists())
        self.assertTrue((project / "scripts" / "123.py").exists())
        self.assertTrue((project / "scripts" / "456.py").exists())


if __name__ == "__main__":
    unittest.main()
