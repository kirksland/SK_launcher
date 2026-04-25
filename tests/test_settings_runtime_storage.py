import json
import unittest
from pathlib import Path
from uuid import uuid4

from core.settings import load_settings, save_settings


class SettingsRuntimeStorageTests(unittest.TestCase):
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

    def test_load_settings_normalizes_runtime_storage_values(self) -> None:
        case_dir = self._make_case_dir("runtime_settings_load")
        settings_path = case_dir / "settings.json"
        settings_path.write_text(
            json.dumps(
                {
                    "runtime_cache_location": "weird",
                    "runtime_cache_max_gb": -2,
                    "runtime_cache_max_days": "abc",
                }
            ),
            encoding="utf-8",
        )

        loaded = load_settings(settings_path)

        self.assertEqual(loaded["runtime_cache_location"], "local_appdata")
        self.assertEqual(loaded["runtime_cache_max_gb"], 5)
        self.assertEqual(loaded["runtime_cache_max_days"], 30)

    def test_save_settings_normalizes_runtime_storage_values(self) -> None:
        case_dir = self._make_case_dir("runtime_settings_save")
        settings_path = case_dir / "settings.json"
        payload = {
            "runtime_cache_location": "project",
            "runtime_cache_max_gb": 8,
            "runtime_cache_max_days": 45,
        }

        save_settings(payload, settings_path)
        saved = json.loads(settings_path.read_text(encoding="utf-8"))

        self.assertEqual(saved["runtime_cache_location"], "project")
        self.assertEqual(saved["runtime_cache_max_gb"], 8)
        self.assertEqual(saved["runtime_cache_max_days"], 45)


if __name__ == "__main__":
    unittest.main()
