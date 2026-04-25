from __future__ import annotations

from pathlib import Path
from typing import Mapping, Sequence

from PySide6 import QtCore, QtWidgets

from core.commands import AppCommand
from core.settings import discover_houdini_installations, normalize_blender_exe, normalize_houdini_exe
from ui.utils.styles import PALETTE, title_style


def _generic_user_path(*parts: str) -> str:
    return str(Path(r"C:\Users\<username>").joinpath(*parts))


class _SettingsNavButton(QtWidgets.QPushButton):
    def __init__(self, label: str, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(label, parent)
        self.setCheckable(True)
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(40)
        self.setStyleSheet(
            "QPushButton {"
            "text-align: left;"
            "padding: 10px 12px;"
            "background: transparent;"
            "border: 1px solid transparent;"
            "border-radius: 8px;"
            f"color: {PALETTE['muted']};"
            "font-weight: 600;"
            "}"
            "QPushButton:hover {"
            "background: rgba(255,255,255,0.04);"
            "border: 1px solid rgba(255,255,255,0.06);"
            f"color: {PALETTE['text']};"
            "}"
            "QPushButton:checked {"
            "background: rgba(255,255,255,0.06);"
            "border: 1px solid rgba(242,193,78,0.45);"
            f"color: {PALETTE['text']};"
            "}"
        )


class SettingsPage(QtWidgets.QWidget):
    def __init__(
        self,
        projects_dir: Path,
        server_repo_dir: Path,
        template_hip: Path,
        new_hip_pattern: str,
        video_backend_pref: str,
        use_file_association: bool,
        show_splash_screen: bool,
        houdini_exe: str,
        blender_exe: str,
        runtime_cache_location: str,
        runtime_cache_max_gb: int,
        runtime_cache_max_days: int,
        shortcut_commands: Sequence[AppCommand] = (),
        shortcut_overrides: Mapping[str, object] | None = None,
        parent: QtWidgets.QWidget | None = None,
        ) -> None:
        super().__init__(parent)
        self._shortcut_commands = tuple(shortcut_commands)
        self._shortcut_overrides = shortcut_overrides or {}
        self.shortcut_fields: dict[str, QtWidgets.QLineEdit] = {}

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        title = QtWidgets.QLabel("Settings")
        title.setStyleSheet(title_style())
        root.addWidget(title)

        shell = QtWidgets.QHBoxLayout()
        shell.setSpacing(14)
        root.addLayout(shell, 1)

        self._nav_group = QtWidgets.QButtonGroup(self)
        self._nav_group.setExclusive(True)

        nav_frame = QtWidgets.QFrame()
        nav_frame.setFixedWidth(220)
        nav_frame.setStyleSheet(
            "QFrame {"
            "background: rgba(255,255,255,0.03);"
            "border: 1px solid rgba(255,255,255,0.06);"
            "border-radius: 10px;"
            "}"
        )
        nav_layout = QtWidgets.QVBoxLayout(nav_frame)
        nav_layout.setContentsMargins(12, 12, 12, 12)
        nav_layout.setSpacing(8)
        nav_title = QtWidgets.QLabel("Categories")
        nav_title.setStyleSheet(f"color: {PALETTE['light_text']}; font-weight: 600;")
        nav_layout.addWidget(nav_title)
        nav_subtitle = QtWidgets.QLabel("Configure paths, launch behavior and startup defaults.")
        nav_subtitle.setWordWrap(True)
        nav_subtitle.setStyleSheet(f"color: {PALETTE['muted']}; font-size: 11px;")
        nav_layout.addWidget(nav_subtitle)

        self.nav_workspace_btn = _SettingsNavButton("Workspace")
        self.nav_launch_btn = _SettingsNavButton("Launch")
        self.nav_houdini_btn = _SettingsNavButton("Houdini")
        self.nav_shortcuts_btn = _SettingsNavButton("Shortcuts")
        for index, button in enumerate(
            (self.nav_workspace_btn, self.nav_launch_btn, self.nav_houdini_btn, self.nav_shortcuts_btn)
        ):
            self._nav_group.addButton(button, index)
            nav_layout.addWidget(button)
        nav_layout.addStretch(1)
        shell.addWidget(nav_frame, 0)

        content_frame = QtWidgets.QFrame()
        content_frame.setStyleSheet(
            "QFrame {"
            "background: rgba(255,255,255,0.025);"
            "border: 1px solid rgba(255,255,255,0.06);"
            "border-radius: 10px;"
            "}"
        )
        content_layout = QtWidgets.QVBoxLayout(content_frame)
        content_layout.setContentsMargins(14, 14, 14, 14)
        content_layout.setSpacing(12)
        shell.addWidget(content_frame, 1)

        self.settings_intro = QtWidgets.QLabel("")
        self.settings_intro.setWordWrap(True)
        self.settings_intro.setStyleSheet(
            "QLabel {"
            "background: rgba(255, 214, 102, 0.10);"
            "border: 1px solid rgba(255, 214, 102, 0.28);"
            "border-radius: 8px;"
            "padding: 10px 12px;"
            f"color: {PALETTE['text']};"
            "}"
        )
        self.settings_intro.setVisible(False)
        content_layout.addWidget(self.settings_intro)

        self.settings_scroll = QtWidgets.QScrollArea()
        self.settings_scroll.setWidgetResizable(True)
        self.settings_scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.settings_scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollBar:vertical { background: transparent; width: 10px; margin: 0px; }"
            "QScrollBar::handle:vertical { background: rgba(255,255,255,0.10); border-radius: 5px; min-height: 24px; }"
        )
        content_layout.addWidget(self.settings_scroll, 1)

        self.settings_scroll_body = QtWidgets.QWidget()
        self.settings_scroll_layout = QtWidgets.QVBoxLayout(self.settings_scroll_body)
        self.settings_scroll_layout.setContentsMargins(0, 0, 2, 0)
        self.settings_scroll_layout.setSpacing(12)
        self.settings_scroll.setWidget(self.settings_scroll_body)

        self.settings_stack = QtWidgets.QStackedWidget()
        self.settings_stack.setStyleSheet("QStackedWidget { background: transparent; border: none; }")
        self.settings_scroll_layout.addWidget(self.settings_stack)

        self.workspace_page = self._build_section_page(
            "Workspace Setup",
            "Paths and templates used by the launcher to discover and create project structures.",
        )
        self.launch_page = self._build_section_page(
            "Launch Behavior",
            "How the launcher opens files, handles preview playback and presents startup feedback.",
        )
        self.houdini_page = self._build_section_page(
            "Houdini Integration",
            "Executable selection and version targeting for Houdini-specific startup behavior.",
        )
        self.shortcuts_page = self._build_section_page(
            "Keyboard Shortcuts",
            "Action bindings shared by the app domains. Settings only persist changes from defaults.",
        )
        self.settings_stack.addWidget(self.workspace_page)
        self.settings_stack.addWidget(self.launch_page)
        self.settings_stack.addWidget(self.houdini_page)
        self.settings_stack.addWidget(self.shortcuts_page)

        self._build_workspace_fields(
            projects_dir,
            server_repo_dir,
            template_hip,
            new_hip_pattern,
            runtime_cache_location,
            runtime_cache_max_gb,
            runtime_cache_max_days,
        )
        self._build_launch_fields(video_backend_pref, use_file_association, show_splash_screen)
        self._build_houdini_fields(houdini_exe, blender_exe)
        self._build_shortcut_fields()

        self.settings_status = QtWidgets.QLabel("")
        self.settings_status.setWordWrap(True)
        self.settings_status.setStyleSheet(
            "QLabel {"
            "background: rgba(255,255,255,0.04);"
            "border: 1px solid rgba(255,255,255,0.08);"
            "border-left: 4px solid #ffd166;"
            "border-radius: 8px;"
            "padding: 10px 12px;"
            f"color: {PALETTE['light_text']};"
            "}"
        )
        content_layout.addWidget(self.settings_status)

        footer = QtWidgets.QHBoxLayout()
        footer.addStretch(1)
        self.settings_save_btn = QtWidgets.QPushButton("Save Settings")
        self.settings_save_btn.setMinimumHeight(36)
        self.settings_save_btn.setStyleSheet(
            "QPushButton {"
            "background: rgba(242,193,78,0.12);"
            "border: 1px solid rgba(242,193,78,0.35);"
            "border-radius: 8px;"
            "padding: 8px 14px;"
            f"color: {PALETTE['text']};"
            "font-weight: 600;"
            "}"
            "QPushButton:hover {"
            "background: rgba(242,193,78,0.18);"
            "}"
        )
        footer.addWidget(self.settings_save_btn)
        content_layout.addLayout(footer)

        self._sync_houdini_version_selection()
        self.settings_houdini_version.currentIndexChanged.connect(self._on_houdini_version_changed)
        self.settings_houdini_exe.textChanged.connect(self._sync_houdini_version_selection)
        self._nav_group.idClicked.connect(self.settings_stack.setCurrentIndex)
        self.nav_workspace_btn.setChecked(True)
        self.settings_stack.setCurrentIndex(0)

    def _build_section_page(self, title: str, description: str) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        header = QtWidgets.QFrame()
        header.setStyleSheet(
            "QFrame {"
            "background: rgba(255,255,255,0.025);"
            "border: 1px solid rgba(255,255,255,0.05);"
            "border-radius: 10px;"
            "}"
        )
        header_layout = QtWidgets.QVBoxLayout(header)
        header_layout.setContentsMargins(14, 12, 14, 12)
        header_layout.setSpacing(4)
        title_label = QtWidgets.QLabel(title)
        title_label.setStyleSheet(f"color: {PALETTE['light_text']}; font-size: 15px; font-weight: 600;")
        header_layout.addWidget(title_label)
        desc_label = QtWidgets.QLabel(description)
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet(f"color: {PALETTE['muted']};")
        header_layout.addWidget(desc_label)
        layout.addWidget(header)

        page.form_host = QtWidgets.QVBoxLayout()  # type: ignore[attr-defined]
        page.form_host.setContentsMargins(0, 0, 0, 0)  # type: ignore[attr-defined]
        page.form_host.setSpacing(12)  # type: ignore[attr-defined]
        layout.addLayout(page.form_host)  # type: ignore[attr-defined]
        layout.addStretch(1)
        return page

    def _build_card(self, page: QtWidgets.QWidget, title: str, description: str) -> QtWidgets.QFormLayout:
        card = QtWidgets.QFrame()
        card.setStyleSheet(
            "QFrame {"
            "background: rgba(255,255,255,0.03);"
            "border: 1px solid rgba(255,255,255,0.07);"
            "border-radius: 10px;"
            "}"
        )
        card_layout = QtWidgets.QVBoxLayout(card)
        card_layout.setContentsMargins(14, 14, 14, 14)
        card_layout.setSpacing(12)

        title_label = QtWidgets.QLabel(title)
        title_label.setStyleSheet(f"color: {PALETTE['light_text']}; font-weight: 600;")
        card_layout.addWidget(title_label)

        desc_label = QtWidgets.QLabel(description)
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet(f"color: {PALETTE['muted']};")
        card_layout.addWidget(desc_label)

        form = QtWidgets.QFormLayout()
        form.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignTop)
        form.setFormAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)
        card_layout.addLayout(form)

        page.form_host.addWidget(card)  # type: ignore[attr-defined]
        return form

    def _build_workspace_fields(
        self,
        projects_dir: Path,
        server_repo_dir: Path,
        template_hip: Path,
        new_hip_pattern: str,
        runtime_cache_location: str,
        runtime_cache_max_gb: int,
        runtime_cache_max_days: int,
    ) -> None:
        locations_form = self._build_card(
            self.workspace_page,
            "Project Locations",
            "These folders define where local projects live and where the launcher looks for the shared server repository.",
        )
        self.settings_projects_dir = QtWidgets.QLineEdit(str(projects_dir))
        self.settings_projects_dir.setPlaceholderText(_generic_user_path("Documents", "HoudiniProjects"))
        self.settings_projects_browse_btn = QtWidgets.QPushButton("Browse...")
        locations_form.addRow("Projects Folder", self._with_browse(self.settings_projects_dir, self.settings_projects_browse_btn))

        self.settings_server_dir = QtWidgets.QLineEdit(str(server_repo_dir))
        self.settings_server_dir.setPlaceholderText(_generic_user_path("Documents", "StudioProject"))
        self.settings_server_browse_btn = QtWidgets.QPushButton("Browse...")
        locations_form.addRow("Server Repo Folder", self._with_browse(self.settings_server_dir, self.settings_server_browse_btn))

        template_form = self._build_card(
            self.workspace_page,
            "Project Creation",
            "Template and naming settings used when the launcher needs to create or initialize a fresh project scene.",
        )
        self.settings_template_hip = QtWidgets.QLineEdit(str(template_hip))
        self.settings_template_hip.setPlaceholderText(r"<launcher>\untitled.hipnc")
        self.settings_template_browse_btn = QtWidgets.QPushButton("Browse...")
        template_form.addRow("Template Hip", self._with_browse(self.settings_template_hip, self.settings_template_browse_btn))

        self.settings_pattern = QtWidgets.QLineEdit(new_hip_pattern)
        self.settings_pattern.setPlaceholderText("{projectName}_001")
        template_form.addRow("New Hip Pattern", self.settings_pattern)

        runtime_form = self._build_card(
            self.workspace_page,
            "Internal Runtime Storage",
            "Choose where Skyforge keeps rebuildable runtime caches such as EXR thumbnails. "
            "Project storage is simpler to inspect; Local AppData keeps project folders cleaner.",
        )
        self.settings_runtime_cache_location = QtWidgets.QComboBox()
        self.settings_runtime_cache_location.addItem("Local AppData (Recommended)", "local_appdata")
        self.settings_runtime_cache_location.addItem("Inside Project Folder", "project")
        current_location = str(runtime_cache_location or "local_appdata").strip().lower()
        for index in range(self.settings_runtime_cache_location.count()):
            if self.settings_runtime_cache_location.itemData(index) == current_location:
                self.settings_runtime_cache_location.setCurrentIndex(index)
                break
        runtime_form.addRow("Cache Location", self.settings_runtime_cache_location)

        self.settings_runtime_cache_max_gb = QtWidgets.QSpinBox()
        self.settings_runtime_cache_max_gb.setRange(1, 1024)
        self.settings_runtime_cache_max_gb.setValue(max(1, int(runtime_cache_max_gb)))
        self.settings_runtime_cache_max_gb.setSuffix(" GB")
        runtime_form.addRow("Max Cache Size", self.settings_runtime_cache_max_gb)

        self.settings_runtime_cache_max_days = QtWidgets.QSpinBox()
        self.settings_runtime_cache_max_days.setRange(1, 3650)
        self.settings_runtime_cache_max_days.setValue(max(1, int(runtime_cache_max_days)))
        self.settings_runtime_cache_max_days.setSuffix(" days")
        runtime_form.addRow("Retention Window", self.settings_runtime_cache_max_days)

    def _build_launch_fields(
        self,
        video_backend_pref: str,
        use_file_association: bool,
        show_splash_screen: bool,
    ) -> None:
        behavior_form = self._build_card(
            self.launch_page,
            "Open & Playback",
            "Control how files are opened and which backend is preferred for video previews inside the launcher.",
        )
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
        behavior_form.addRow("Video Backend", self.settings_video_backend)

        toggles_form = self._build_card(
            self.launch_page,
            "Startup Experience",
            "Choose whether Windows file associations are used by default and whether the launcher shows a splash screen while loading.",
        )
        self.settings_use_assoc = QtWidgets.QCheckBox("Open via file association")
        self.settings_use_assoc.setChecked(use_file_association)
        self.settings_use_assoc.setToolTip(
            "When enabled, Windows opens the file using its current association. "
            "When disabled, the selected Houdini executable is used for Houdini scenes."
        )
        toggles_form.addRow("", self.settings_use_assoc)

        self.settings_show_splash = QtWidgets.QCheckBox("Show splash screen at startup")
        self.settings_show_splash.setChecked(show_splash_screen)
        self.settings_show_splash.setToolTip(
            "Displays the startup splash screen while the launcher is loading."
        )
        toggles_form.addRow("", self.settings_show_splash)

    def _build_houdini_fields(self, houdini_exe: str, blender_exe: str) -> None:
        houdini_form = self._build_card(
            self.houdini_page,
            "DCC Executables",
            "Pick the executables Skyforge can use for explicit scene creation and launches when file association is not enough.",
        )
        self.settings_houdini_version = QtWidgets.QComboBox()
        self.settings_houdini_version.addItem("Custom (use field below)", "")
        for item in discover_houdini_installations():
            self.settings_houdini_version.addItem(item["label"], item["path"])
        houdini_form.addRow("Houdini Version", self.settings_houdini_version)

        self.settings_houdini_exe = QtWidgets.QLineEdit(houdini_exe)
        self.settings_houdini_exe.setPlaceholderText(
            r"C:\Program Files\Side Effects Software\Houdini <version>\bin\houdini.exe"
        )
        self.settings_houdini_browse_btn = QtWidgets.QPushButton("Browse...")
        houdini_form.addRow("Houdini Executable", self._with_browse(self.settings_houdini_exe, self.settings_houdini_browse_btn))

        self.settings_blender_exe = QtWidgets.QLineEdit(blender_exe)
        self.settings_blender_exe.setPlaceholderText(
            r"C:\Program Files\Blender Foundation\Blender <version>\blender.exe"
        )
        self.settings_blender_browse_btn = QtWidgets.QPushButton("Browse...")
        houdini_form.addRow("Blender Executable", self._with_browse(self.settings_blender_exe, self.settings_blender_browse_btn))

    def _build_shortcut_fields(self) -> None:
        shortcuts_form = self._build_card(
            self.shortcuts_page,
            "Command Bindings",
            "Use comma-separated shortcuts for multiple bindings. Leave a field empty to disable that command.",
        )
        for command in self._shortcut_commands:
            field = QtWidgets.QLineEdit(self._effective_shortcut_text(command))
            field.setPlaceholderText(", ".join(command.default_shortcuts))
            field.setToolTip(f"{command.id} | scope: {command.scope}")
            label = f"{command.label} ({command.domain})"
            shortcuts_form.addRow(label, field)
            self.shortcut_fields[command.id] = field

    def shortcut_overrides(self) -> dict[str, list[str]]:
        overrides: dict[str, list[str]] = {}
        for command in self._shortcut_commands:
            field = self.shortcut_fields.get(command.id)
            if field is None:
                continue
            sequences = self._parse_shortcut_text(field.text())
            defaults = list(command.default_shortcuts)
            if sequences != defaults:
                overrides[command.id] = sequences
        return overrides

    def _effective_shortcut_text(self, command: AppCommand) -> str:
        override = self._shortcut_overrides.get(command.id)
        if override is None:
            return ", ".join(command.default_shortcuts)
        return ", ".join(self._coerce_shortcut_sequences(override))

    @staticmethod
    def _parse_shortcut_text(text: str) -> list[str]:
        return [part.strip() for part in str(text or "").split(",") if part.strip()]

    @staticmethod
    def _coerce_shortcut_sequences(value: object) -> list[str]:
        if isinstance(value, str):
            return [value.strip()] if value.strip() else []
        if isinstance(value, list):
            return [item.strip() for item in value if isinstance(item, str) and item.strip()]
        return []

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

    def normalized_blender_executable(self) -> str:
        return normalize_blender_exe(self.settings_blender_exe.text())

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
            "QLabel {"
            "background: rgba(255,255,255,0.04);"
            "border: 1px solid rgba(255,255,255,0.08);"
            f"border-left: 4px solid {color};"
            "border-radius: 8px;"
            "padding: 10px 12px;"
            f"color: {PALETTE['light_text']};"
            "}"
        )
        self.settings_status.setText(text)
