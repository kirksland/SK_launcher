from __future__ import annotations

from pathlib import Path

from PySide6 import QtCore, QtWidgets

from core.settings import discover_houdini_installations, normalize_houdini_exe
from ui.utils.styles import title_style


class SettingsPage(QtWidgets.QWidget):
    def __init__(
        self,
        projects_dir: Path,
        server_repo_dir: Path,
        template_hip: Path,
        new_hip_pattern: str,
        video_backend_pref: str,
        use_file_association: bool,
        houdini_exe: str,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        title = QtWidgets.QLabel("Settings")
        title.setStyleSheet(title_style())
        layout.addWidget(title)

        form = QtWidgets.QFormLayout()
        form.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)
        form.setFormAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(8)
        layout.addLayout(form)

        self.settings_projects_dir = QtWidgets.QLineEdit(str(projects_dir))
        form.addRow("Projects Folder", self.settings_projects_dir)

        self.settings_server_dir = QtWidgets.QLineEdit(str(server_repo_dir))
        form.addRow("Server Repo Folder", self.settings_server_dir)

        self.settings_template_hip = QtWidgets.QLineEdit(str(template_hip))
        form.addRow("Template Hip", self.settings_template_hip)

        self.settings_pattern = QtWidgets.QLineEdit(new_hip_pattern)
        form.addRow("New Hip Pattern", self.settings_pattern)

        self.settings_video_backend = QtWidgets.QComboBox()
        self.settings_video_backend.addItems(["Auto", "OpenCV", "Qt", "Off"])
        current_backend = video_backend_pref
        if current_backend == "opencv":
            self.settings_video_backend.setCurrentText("OpenCV")
        elif current_backend == "qt":
            self.settings_video_backend.setCurrentText("Qt")
        elif current_backend == "none":
            self.settings_video_backend.setCurrentText("Off")
        else:
            self.settings_video_backend.setCurrentText("Auto")
        form.addRow("Video Backend", self.settings_video_backend)

        self.settings_use_assoc = QtWidgets.QCheckBox("Open via file association")
        self.settings_use_assoc.setChecked(use_file_association)
        self.settings_use_assoc.setToolTip(
            "When enabled, Windows opens the .hip using its file association. "
            "When disabled, the selected Houdini executable is used."
        )
        form.addRow("", self.settings_use_assoc)

        self.settings_houdini_version = QtWidgets.QComboBox()
        self.settings_houdini_version.addItem("Custom (use field below)", "")
        for item in discover_houdini_installations():
            self.settings_houdini_version.addItem(item["label"], item["path"])
        form.addRow("Houdini Version", self.settings_houdini_version)

        self.settings_houdini_exe = QtWidgets.QLineEdit(houdini_exe)
        self.settings_houdini_exe.setPlaceholderText("Optional: path to houdini.exe")
        form.addRow("Houdini Executable", self.settings_houdini_exe)


        self._sync_houdini_version_selection()
        self.settings_houdini_version.currentIndexChanged.connect(self._on_houdini_version_changed)
        self.settings_houdini_exe.textChanged.connect(self._sync_houdini_version_selection)

        self.settings_save_btn = QtWidgets.QPushButton("Save Settings")
        layout.addWidget(self.settings_save_btn)

        layout.addStretch(1)

    def _sync_houdini_version_selection(self) -> None:
        current = normalize_houdini_exe(self.settings_houdini_exe.text())
        current_lower = current.lower()
        for i in range(self.settings_houdini_version.count()):
            path = self.settings_houdini_version.itemData(i)
            if isinstance(path, str) and path.lower() == current_lower and current_lower:
                self.settings_houdini_version.setCurrentIndex(i)
                return
        self.settings_houdini_version.setCurrentIndex(0)

    def _on_houdini_version_changed(self) -> None:
        path = self.settings_houdini_version.currentData()
        if isinstance(path, str) and path:
            self.settings_houdini_exe.setText(path)
