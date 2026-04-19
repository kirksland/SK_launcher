from __future__ import annotations

import unittest
from pathlib import Path

from core.dcc import default_scene_filename, detect_dcc_for_path


class DccSceneFileTests(unittest.TestCase):
    def test_detect_dcc_for_supported_scene_files(self) -> None:
        self.assertEqual(detect_dcc_for_path(Path("shot_001.hipnc")).id, "houdini")
        self.assertEqual(detect_dcc_for_path(Path("shot_001.blend")).id, "blender")
        self.assertEqual(detect_dcc_for_path(Path("shot_001.spp")).id, "substance_painter")

    def test_default_scene_filename_uses_descriptor_extension(self) -> None:
        self.assertEqual(default_scene_filename("Mardini", "houdini"), "Mardini_001.hipnc")
        self.assertEqual(default_scene_filename("Mardini", "blender"), "Mardini_001.blend")
        self.assertEqual(default_scene_filename("Mardini", "nuke"), "Mardini_001.nk")


if __name__ == "__main__":
    unittest.main()
