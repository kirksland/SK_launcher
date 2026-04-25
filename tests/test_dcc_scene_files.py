from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

from core.dcc import DccOpenContext, default_scene_filename, detect_dcc_for_path, get_dcc_handler, open_scene_with_dcc


class DccSceneFileTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
