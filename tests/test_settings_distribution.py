import os
import unittest
from pathlib import Path
from uuid import uuid4

from core.settings import (
    DEFAULT_PROJECTS_DIR,
    DEFAULT_SERVER_REPO_DIR,
    DEFAULT_TEMPLATE_HIP,
    active_settings_path,
    is_first_run,
    load_settings,
    save_settings,
    settings_startup_issues,
)


class SettingsDistributionTests(unittest.TestCase):
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

    def test_defaults_are_distribution_safe(self) -> None:
        self.assertTrue(DEFAULT_PROJECTS_DIR.is_absolute())
        self.assertTrue(DEFAULT_SERVER_REPO_DIR.is_absolute())
        self.assertTrue(str(DEFAULT_TEMPLATE_HIP).lower().endswith("untitled.hipnc"))

    def test_active_settings_path_prefers_existing_legacy_file(self) -> None:
        root = self._make_case_dir("settings_legacy")
        legacy = root / "settings.json"
        legacy.write_text("{}", encoding="utf-8")
        user = root / "AppData" / "SkyforgeLauncher" / "settings.json"
        chosen = active_settings_path(legacy_path=legacy, user_path=user)
        self.assertEqual(chosen, legacy)

    def test_load_settings_uses_explicit_path_without_touching_defaults(self) -> None:
        root = self._make_case_dir("settings_load")
        settings_path = root / "settings.json"
        settings_path.write_text(
            '{"projects_dir": "D:/Projects", "server_repo_dir": "D:/Server"}',
            encoding="utf-8",
        )
        settings = load_settings(settings_path)
        self.assertEqual(settings["projects_dir"], "D:/Projects")
        self.assertEqual(settings["server_repo_dir"], "D:/Server")

    def test_save_settings_writes_explicit_path(self) -> None:
        root = self._make_case_dir("settings_save")
        settings_path = root / "User" / "settings.json"
        save_settings({"projects_dir": "D:/Projects"}, settings_path)
        self.assertTrue(settings_path.exists())

    def test_active_settings_path_prefers_env_override(self) -> None:
        root = self._make_case_dir("settings_env")
        env_path = root / "custom.json"
        previous = os.environ.get("SKYFORGE_SETTINGS_PATH")
        os.environ["SKYFORGE_SETTINGS_PATH"] = str(env_path)
        self.addCleanup(self._restore_env, previous)
        chosen = active_settings_path()
        self.assertEqual(chosen, env_path)

    def test_is_first_run_uses_missing_explicit_path(self) -> None:
        root = self._make_case_dir("settings_first_run")
        self.assertTrue(is_first_run(root / "missing.json"))

    def test_settings_startup_issues_reports_missing_required_paths(self) -> None:
        issues = settings_startup_issues(
            {
                "projects_dir": "",
                "server_repo_dir": "",
                "template_hip": "",
                "use_file_association": False,
                "houdini_exe": "",
            }
        )
        self.assertEqual(
            issues,
            ["Projects Folder", "Server Repo Folder", "Template Hip", "Houdini Executable"],
        )

    @staticmethod
    def _restore_env(previous: str | None) -> None:
        if previous is None:
            os.environ.pop("SKYFORGE_SETTINGS_PATH", None)
        else:
            os.environ["SKYFORGE_SETTINGS_PATH"] = previous


if __name__ == "__main__":
    unittest.main()
