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

        self.settings_intro = QtWidgets.QLabel("")
        self.settings_intro.setWordWrap(True)
        self.settings_intro.setStyleSheet(
            "QLabel { background: rgba(255, 214, 102, 0.12); border: 1px solid rgba(255, 214, 102, 0.35);"
            " border-radius: 8px; padding: 10px; color: #d9dde3; }"
        )
        self.settings_intro.setVisible(False)
        layout.addWidget(self.settings_intro)

        form = QtWidgets.QFormLayout()
        form.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)
        form.setFormAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(8)
        layout.addLayout(form)

        self.settings_projects_dir = QtWidgets.QLineEdit(str(projects_dir))
        self.settings_projects_browse_btn = QtWidgets.QPushButton("Browse...")
        form.addRow("Projects Folder", self._with_browse(self.settings_projects_dir, self.settings_projects_browse_btn))

        self.settings_server_dir = QtWidgets.QLineEdit(str(server_repo_dir))
        self.settings_server_browse_btn = QtWidgets.QPushButton("Browse...")
        form.addRow("Server Repo Folder", self._with_browse(self.settings_server_dir, self.settings_server_browse_btn))

        self.settings_template_hip = QtWidgets.QLineEdit(str(template_hip))
        self.settings_template_browse_btn = QtWidgets.QPushButton("Browse...")
        form.addRow("Template Hip", self._with_browse(self.settings_template_hip, self.settings_template_browse_btn))

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
        self.settings_houdini_browse_btn = QtWidgets.QPushButton("Browse...")
        form.addRow("Houdini Executable", self._with_browse(self.settings_houdini_exe, self.settings_houdini_browse_btn))

        self.settings_status = QtWidgets.QLabel("")
        self.settings_status.setWordWrap(True)
        self.settings_status.setStyleSheet(
            "QLabel { background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.08);"
            " border-radius: 8px; padding: 10px; color: #cfd5de; }"
        )
        layout.addWidget(self.settings_status)


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

    @staticmethod
    def _with_browse(field: QtWidgets.QLineEdit, button: QtWidgets.QPushButton) -> QtWidgets.QWidget:
        row = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(field, 1)
        layout.addWidget(button, 0)
        return row

    def set_startup_context(self, enabled: bool, message: str = "") -> None:
        self.settings_intro.setVisible(enabled)
        self.settings_intro.setText(message if enabled else "")

    def set_validation_summary(self, text: str, *, ready: bool) -> None:
        color = "#7bd88f" if ready else "#ffd166"
        self.settings_status.setStyleSheet(
            "QLabel { background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.08);"
            f" border-left: 4px solid {color}; border-radius: 8px; padding: 10px; color: #cfd5de; }}"
        )
        self.settings_status.setText(text)
