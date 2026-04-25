from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock
from uuid import uuid4

from core.dcc import (
    DccCreateContext,
    DccOpenContext,
    create_scene_with_dcc,
    default_scene_filename,
    detect_dcc_for_path,
    get_dcc_handler,
    open_scene_with_dcc,
)


class DccSceneFileTests(unittest.TestCase):
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

    def test_detect_dcc_for_supported_scene_files(self) -> None:
        self.assertEqual(detect_dcc_for_path(Path("shot_001.hipnc")).id, "houdini")
        self.assertEqual(detect_dcc_for_path(Path("shot_001.blend")).id, "blender")
        self.assertEqual(detect_dcc_for_path(Path("shot_001.spp")).id, "substance_painter")

    def test_default_scene_filename_uses_descriptor_extension(self) -> None:
        self.assertEqual(default_scene_filename("Mardini", "houdini"), "Mardini_001.hipnc")
        self.assertEqual(default_scene_filename("Mardini", "blender"), "Mardini_001.blend")
        self.assertEqual(default_scene_filename("Mardini", "nuke"), "Mardini_001.nk")

    def test_get_dcc_handler_returns_builtin_handlers(self) -> None:
        self.assertEqual(get_dcc_handler("houdini").descriptor.id, "houdini")  # type: ignore[union-attr]
        self.assertEqual(get_dcc_handler("blender").descriptor.id, "blender")  # type: ignore[union-attr]

    def test_open_scene_with_dcc_uses_file_association_for_blender(self) -> None:
        context = DccOpenContext(
            project_path=Path("C:/projects/test"),
            launcher_root=Path("C:/launcher"),
            use_file_association=True,
        )
        with mock.patch("os.startfile") as startfile:
            open_scene_with_dcc(Path("C:/projects/test/scene.blend"), context)
        startfile.assert_called_once()

    def test_open_scene_with_dcc_uses_houdini_executable_when_available(self) -> None:
        context = DccOpenContext(
            project_path=Path("C:/projects/test"),
            launcher_root=Path("C:/launcher"),
            use_file_association=False,
            executable="C:/Program Files/Side Effects Software/Houdini/bin/houdini.exe",
        )
        with mock.patch("subprocess.Popen") as popen:
            open_scene_with_dcc(Path("C:/projects/test/scene.hipnc"), context)
        popen.assert_called_once()

    def test_create_scene_with_houdini_creates_scene_and_runtime_scripts(self) -> None:
        root = self._make_case_dir("dcc_houdini_scene")
        project = root / "Demo"
        project.mkdir()

        def _fake_run(command, **_kwargs):
            Path(command[-1]).write_text("hip", encoding="utf-8")
            return mock.Mock(returncode=0, stdout="", stderr="")

        with mock.patch("core.dcc_handlers.houdini.resolve_hython_executable", return_value="C:/Houdini/bin/hython.exe"):
            with mock.patch("subprocess.run", side_effect=_fake_run) as run_mock:
                result = create_scene_with_dcc(
                    "houdini",
                    DccCreateContext(
                        project_path=project,
                        launcher_root=root,
                        executable="C:/Houdini/bin/houdini.exe",
                        filename_pattern="Demo_layout.hipnc",
                        ensure_runtime_scripts=True,
                    ),
                )

        self.assertEqual(result.error, "")
        self.assertEqual(result.scene_path, project / "Demo_layout.hipnc")
        self.assertTrue((project / "Demo_layout.hipnc").exists())
        self.assertFalse((project / "scripts" / "123.py").exists())
        self.assertFalse((project / "scripts" / "456.py").exists())
        run_mock.assert_called_once()

    def test_create_scene_with_houdini_reports_missing_hython(self) -> None:
        root = self._make_case_dir("dcc_houdini_missing_hython")
        project = root / "Demo"
        project.mkdir()

        with mock.patch("core.dcc_handlers.houdini.resolve_hython_executable", return_value=""):
            result = create_scene_with_dcc(
                "houdini",
                DccCreateContext(
                    project_path=project,
                    launcher_root=root,
                    executable="",
                    filename_pattern="Demo_layout.hipnc",
                ),
            )

        self.assertIsNone(result.scene_path)
        self.assertIn("Could not resolve a valid hython executable", result.error)

    def test_create_scene_with_blender_without_template_returns_helpful_error(self) -> None:
        root = self._make_case_dir("dcc_blender_scene")
        project = root / "Demo"
        project.mkdir()

        result = create_scene_with_dcc(
            "blender",
            DccCreateContext(
                project_path=project,
                launcher_root=root,
            ),
        )

        self.assertIsNone(result.scene_path)
        self.assertIn("Blender scene creation is not configured yet", result.error)

    def test_create_scene_with_unknown_dcc_returns_error(self) -> None:
        root = self._make_case_dir("dcc_unknown_scene")
        project = root / "Demo"
        project.mkdir()

        result = create_scene_with_dcc(
            "unknown_dcc",
            DccCreateContext(
                project_path=project,
                launcher_root=root,
            ),
        )

        self.assertIsNone(result.scene_path)
        self.assertIn("No DCC handler is registered", result.error)

    def test_default_scene_filename_can_be_used_to_append_missing_extension(self) -> None:
        self.assertEqual(default_scene_filename("Demo", "houdini"), "Demo_001.hipnc")


if __name__ == "__main__":
    unittest.main()
