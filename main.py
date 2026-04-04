from __future__ import annotations

import os
import re
import shutil
import subprocess
import traceback
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PySide6 import QtCore, QtGui, QtWidgets

from core.fs import (
    find_hips,
    find_projects,
    latest_preview_image,
    list_preview_images,
    list_review_videos,
    list_usd_versions,
    name_prefix,
    open_hip,
)
from core.metadata import load_metadata
from core.settings import (
    DEFAULT_ASSET_SCHEMA,
    DEFAULT_PROJECTS_DIR,
    DEFAULT_TEMPLATE_HIP,
    DEFAULT_SETTINGS,
    load_settings,
    normalize_houdini_exe,
    normalize_asset_schema,
    normalize_asset_manager_projects,
    save_settings,
)
from video.player import VideoController

APP_TITLE = "Skyforge Launcher"
TEST_PIPELINE_ROOT = Path(__file__).resolve().parent / "projects" / "test_pipeline"
BADGE_SVG_PATH = Path(__file__).resolve().parent / "config" / "icons" / "cloud.svg"
PROJECT_SUBDIRS = [
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
]
JOB_INIT_MARKER = ".skyforge_job_init"

def make_placeholder_pixmap(text: str, size: QtCore.QSize) -> QtGui.QPixmap:
    pixmap = QtGui.QPixmap(size)
    pixmap.fill(QtGui.QColor("#2b2f36"))

    painter = QtGui.QPainter(pixmap)
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)

    gradient = QtGui.QLinearGradient(0, 0, size.width(), size.height())
    gradient.setColorAt(0.0, QtGui.QColor("#3a404a"))
    gradient.setColorAt(1.0, QtGui.QColor("#23272e"))
    painter.fillRect(pixmap.rect(), gradient)

    painter.setPen(QtGui.QColor("#9aa3ad"))
    font = QtGui.QFont()
    font.setBold(True)
    font.setPointSize(10)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), QtCore.Qt.AlignmentFlag.AlignCenter, text)
    painter.end()

    return pixmap


def pick_background_image(project_path: Path) -> Optional[Path]:
    # Project-specific thumbnails first
    for ext in (".png", ".jpg", ".jpeg"):
        candidate = project_path / f"thumbnail{ext}"
        if candidate.exists():
            return candidate

    # Shared launcher background in skyforge_launcher/
    root = Path(__file__).resolve().parent
    horizontal_sf = root / "horizontalSF.png"
    if horizontal_sf.exists():
        return horizontal_sf

    for ext in (".png", ".jpg", ".jpeg"):
        candidate = root / f"launcher_bg{ext}"
        if candidate.exists():
            return candidate

    return None


def build_thumbnail_pixmap(project_path: Path, size: QtCore.QSize) -> QtGui.QPixmap:
    image_path = pick_background_image(project_path)
    if image_path is None:
        return make_placeholder_pixmap("Preview", size)

    pixmap = QtGui.QPixmap(str(image_path))
    if pixmap.isNull():
        return make_placeholder_pixmap("Preview", size)

    # Fill the box and crop if aspect ratio differs
    scaled = pixmap.scaled(
        size,
        QtCore.Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        QtCore.Qt.TransformationMode.SmoothTransformation,
    )
    # Center-crop to exact size
    x = max(0, (scaled.width() - size.width()) // 2)
    y = max(0, (scaled.height() - size.height()) // 2)
    return scaled.copy(x, y, size.width(), size.height())


def add_cloud_badge(pixmap: QtGui.QPixmap) -> QtGui.QPixmap:
    if pixmap.isNull():
        return pixmap
    result = QtGui.QPixmap(pixmap)
    painter = QtGui.QPainter(result)
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)

    badge_rect = QtCore.QRect(6, 6, 20, 20)

    svg_drawn = False
    if BADGE_SVG_PATH.exists():
        try:
            from PySide6 import QtSvg
        except Exception:
            QtSvg = None  # type: ignore[assignment]
        if QtSvg is not None:
            renderer = QtSvg.QSvgRenderer(str(BADGE_SVG_PATH))
            if renderer.isValid():
                icon_size = 20
                icon_rect = QtCore.QRect(
                    badge_rect.center().x() - icon_size // 2,
                    badge_rect.center().y() - icon_size // 2,
                    icon_size,
                    icon_size,
                )
                icon_pix = QtGui.QPixmap(icon_rect.size())
                icon_pix.fill(QtCore.Qt.GlobalColor.transparent)
                icon_painter = QtGui.QPainter(icon_pix)
                renderer.render(icon_painter)
                icon_painter.end()
                painter.drawPixmap(icon_rect.topLeft(), icon_pix)
                svg_drawn = True

    if not svg_drawn:
        font = QtGui.QFont()
        font.setBold(True)
        font.setPointSize(9)
        painter.setFont(font)
        painter.setPen(QtGui.QColor("#d8dde5"))
        painter.drawText(badge_rect, QtCore.Qt.AlignmentFlag.AlignCenter, "C")
    painter.end()
    return result
def group_hip_variants(hips: List[Path]) -> Dict[str, List[Tuple[str, Path]]]:
    pattern = re.compile(r"^(?P<base>.+)_(?P<ver>\d+)$")
    grouped: Dict[str, List[Tuple[str, Path]]] = {}
    for hip in hips:
        stem = hip.stem
        match = pattern.match(stem)
        if match:
            base = match.group("base")
            ver = match.group("ver")
            label = ver
        else:
            base = stem
            label = "current"
        grouped.setdefault(base, []).append((label, hip))

    # Sort versions numerically when possible, fallback to mtime
    for base, entries in grouped.items():
        def sort_key(item: Tuple[str, Path]) -> Tuple[int, float]:
            label, path = item
            if label.isdigit():
                return (0, int(label))
            return (1, -path.stat().st_mtime)

        entries.sort(key=sort_key, reverse=True)
    return dict(sorted(grouped.items(), key=lambda kv: kv[0].lower()))


def _split_asset_version(stem: str) -> Tuple[str, str, Optional[int]]:
    patterns = [
        re.compile(r"^(?P<base>.+?)[._-](?P<ver>v\d+)$", re.IGNORECASE),
        re.compile(r"^(?P<base>.+?)[._-](?P<ver>\d+)$", re.IGNORECASE),
        re.compile(r"^(?P<base>.+?)(?P<ver>v\d+)$", re.IGNORECASE),
    ]
    for pattern in patterns:
        match = pattern.match(stem)
        if match:
            base = match.group("base")
            label = match.group("ver")
            digits = re.sub(r"\D", "", label)
            version_num = int(digits) if digits.isdigit() else None
            return base, label, version_num
    return stem, "current", None


def group_asset_versions(
    usd_files: List[Path],
    video_files: List[Path],
    image_files: Optional[List[Path]] = None,
) -> Dict[str, List[Dict[str, object]]]:
    grouped: Dict[str, Dict[str, Dict[str, object]]] = {}

    def add_file(path: Path, kind: str) -> None:
        base, label, version_num = _split_asset_version(path.stem)
        base_map = grouped.setdefault(base, {})
        entry = base_map.get(label)
        if entry is None:
            entry = {
                "label": label,
                "usd": None,
                "video": None,
                "mtime": path.stat().st_mtime,
                "version_num": version_num,
            }
            base_map[label] = entry
        entry[kind] = path
        entry["mtime"] = max(float(entry["mtime"]), path.stat().st_mtime)
        if version_num is not None:
            entry["version_num"] = version_num

    for path in usd_files:
        add_file(path, "usd")
    for path in video_files:
        add_file(path, "video")
    for path in (image_files or []):
        add_file(path, "image")

    result: Dict[str, List[Dict[str, object]]] = {}
    for base, entries in grouped.items():
        entries_list = list(entries.values())

        def sort_key(entry: Dict[str, object]) -> Tuple[int, float]:
            version_num = entry.get("version_num")
            if isinstance(version_num, int):
                return (0, float(version_num))
            return (1, float(entry.get("mtime", 0.0)))

        entries_list.sort(key=sort_key, reverse=True)
        result[base] = entries_list

    return dict(sorted(result.items(), key=lambda kv: kv[0].lower()))


class ProjectCard(QtWidgets.QWidget):
    selection_changed = QtCore.Signal(object)

    def __init__(
        self,
        project_path: Path,
        thumb_size: QtCore.QSize,
        hips: List[Path],
        show_cloud_badge: bool = False,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.project_path = project_path
        self._hips = hips
        self._variants = group_hip_variants(self._hips)
        self._current_base: Optional[str] = None

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        thumb_container = QtWidgets.QWidget()
        thumb_container.setFixedSize(thumb_size)
        thumb_layout = QtWidgets.QGridLayout(thumb_container)
        thumb_layout.setContentsMargins(0, 0, 0, 0)
        thumb_layout.setSpacing(0)

        thumbnail = QtWidgets.QLabel()
        thumbnail.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        pixmap = build_thumbnail_pixmap(project_path, thumb_size)
        if show_cloud_badge:
            pixmap = add_cloud_badge(pixmap)
        thumbnail.setPixmap(pixmap)
        thumb_layout.addWidget(thumbnail, 0, 0)

        self.title_button = QtWidgets.QToolButton()
        self.title_button.setText(project_path.name)
        self.title_button.setPopupMode(QtWidgets.QToolButton.ToolButtonPopupMode.InstantPopup)
        self.title_button.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.title_button.setAutoRaise(True)
        title_font = QtGui.QFont()
        title_font.setBold(True)
        title_font.setPointSize(11)
        self.title_button.setFont(title_font)
        self.title_button.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed)
        self.title_button.setStyleSheet(
            "QToolButton {"
            "background: #ffffff;"
            "color: #111;"
            "padding: 4px 6px;"
            "}"
        )
        thumb_layout.addWidget(
            self.title_button,
            0,
            0,
            QtCore.Qt.AlignmentFlag.AlignBottom,
        )

        layout.addWidget(thumb_container, 0, QtCore.Qt.AlignmentFlag.AlignHCenter)

        self.version_combo = QtWidgets.QComboBox()
        self.version_combo.setFixedWidth(86)
        self.version_combo.setStyleSheet(
            "QComboBox {"
            "background: rgba(20, 20, 20, 180);"
            "color: #fff;"
            "padding: 2px 10px;"
            "border: 1px solid rgba(255,255,255,80);"
            "border-radius: 6px;"
            "}"
        )
        thumb_layout.addWidget(
            self.version_combo,
            0,
            0,
            QtCore.Qt.AlignmentFlag.AlignTop | QtCore.Qt.AlignmentFlag.AlignRight,
        )

        if not self._variants:
            self.title_button.setEnabled(False)
            self.version_combo.setVisible(False)
        else:
            self._build_variant_menu()
            first_base = next(iter(self._variants.keys()))
            self._set_current_base(first_base)
            self.version_combo.currentTextChanged.connect(self._emit_selection_changed)

    def _emit_selection_changed(self) -> None:
        hip = self.selected_hip()
        if hip is not None:
            self.selection_changed.emit(self)

    def _build_variant_menu(self) -> None:
        menu = QtWidgets.QMenu(self)
        menu.setStyleSheet(
            "QMenu {"
            "background: #ffffff;"
            "color: #111;"
            "border: 1px solid #d0d0d0;"
            "}"
            "QMenu::item:selected {"
            "background: #e6e6e6;"
            "}"
        )
        for base in self._variants.keys():
            action = menu.addAction(base)
            action.triggered.connect(lambda _checked=False, b=base: self._set_current_base(b))
        self.title_button.setMenu(menu)

    def _set_current_base(self, base: str) -> None:
        self._current_base = base
        self.version_combo.clear()
        entries = self._variants.get(base, [])
        for label, _path in entries:
            self.version_combo.addItem(label)
        self._emit_selection_changed()

    def selected_hip(self) -> Optional[Path]:
        if not self._variants:
            return None
        base = self._current_base
        if base is None:
            return None
        entries = self._variants.get(base, [])
        if not entries:
            return None
        label = self.version_combo.currentText()
        for entry_label, path in entries:
            if entry_label == label:
                return path
        return entries[0][1]


class AssetVersionRow(QtWidgets.QWidget):
    selection_changed = QtCore.Signal()

    def __init__(
        self,
        base_name: str,
        entries: List[Dict[str, object]],
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._entries = entries
        self._entry_by_label = {str(e.get("label")): e for e in entries}
        self._thumb_size = QtCore.QSize(48, 30)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 6, 2)
        layout.setSpacing(8)

        self.thumb_label = QtWidgets.QLabel()
        self.thumb_label.setFixedSize(self._thumb_size)
        self.thumb_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.thumb_label.setStyleSheet("background: #23272e; border: 1px solid #14171c;")
        layout.addWidget(self.thumb_label, 0)

        self.name_label = QtWidgets.QLabel(base_name)
        self.name_label.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        layout.addWidget(self.name_label, 1)

        self.types_label = QtWidgets.QLabel("")
        self.types_label.setStyleSheet("color: #9aa3ad;")
        layout.addWidget(self.types_label, 0)

        self.version_combo = QtWidgets.QComboBox()
        self.version_combo.setFixedWidth(80)
        self.version_combo.setStyleSheet(
            "QComboBox {"
            "background: #2b2f36;"
            "color: #d8dde5;"
            "padding: 2px 6px;"
            "border: 1px solid #14171c;"
            "border-radius: 6px;"
            "}"
        )
        for entry in entries:
            self.version_combo.addItem(str(entry.get("label")))
        layout.addWidget(self.version_combo, 0)

        self.version_combo.currentTextChanged.connect(self._on_combo_changed)
        self._update_types_label()
        self._update_thumbnail()

    def _current_entry(self) -> Optional[Dict[str, object]]:
        label = self.version_combo.currentText()
        return self._entry_by_label.get(label)

    def _update_types_label(self) -> None:
        entry = self._current_entry()
        if not entry:
            self.types_label.setText("")
            return
        parts = []
        if entry.get("usd") is not None:
            parts.append("USD")
        if entry.get("video") is not None:
            parts.append("VIDEO")
        if entry.get("image") is not None:
            parts.append("IMG")
        self.types_label.setText(" / ".join(parts))

    def _update_thumbnail(self) -> None:
        entry = self._current_entry()
        if not entry:
            self.thumb_label.clear()
            return
        image = entry.get("image")
        if isinstance(image, Path) and image.exists():
            pixmap = QtGui.QPixmap(str(image))
            if not pixmap.isNull():
                scaled = pixmap.scaled(
                    self._thumb_size,
                    QtCore.Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    QtCore.Qt.TransformationMode.SmoothTransformation,
                )
                # Center-crop to exact size
                x = max(0, (scaled.width() - self._thumb_size.width()) // 2)
                y = max(0, (scaled.height() - self._thumb_size.height()) // 2)
                self.thumb_label.setPixmap(
                    scaled.copy(x, y, self._thumb_size.width(), self._thumb_size.height())
                )
                return
        self.thumb_label.setPixmap(make_placeholder_pixmap("", self._thumb_size))

    def _on_combo_changed(self) -> None:
        self._update_types_label()
        self._update_thumbnail()
        self.selection_changed.emit()

    def selected_path(self) -> Tuple[Optional[Path], Optional[str]]:
        entry = self._current_entry()
        if not entry:
            return None, None
        video = entry.get("video")
        usd = entry.get("usd")
        image = entry.get("image")
        if isinstance(video, Path):
            return video, "video"
        if isinstance(usd, Path):
            return usd, "usd"
        if isinstance(image, Path):
            return image, "image"
        return None, None


class LauncherWindow(QtWidgets.QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(1280, 620)

        self.settings = load_settings()
        self.projects_dir = Path(self.settings["projects_dir"])
        self.server_repo_dir = Path(self.settings["server_repo_dir"])
        self._template_hip = Path(self.settings["template_hip"])
        self._new_hip_pattern = self.settings["new_hip_pattern"]
        self._use_file_association = bool(self.settings["use_file_association"])
        self._houdini_exe = self.settings["houdini_exe"]
        self._video_backend_pref = str(self.settings.get("video_backend", "auto")).strip().lower() or "auto"
        self._asset_manager_projects = normalize_asset_manager_projects(
            self.settings.get("asset_manager_projects", [])
        )
        self._asset_schema = normalize_asset_schema(
            self.settings.get("asset_schema", DEFAULT_ASSET_SCHEMA)
        )
        self._project_cache: Dict[Path, Tuple[float, List[Path], float]] = {}
        self._asset_cache: Dict[Path, Tuple[float, List[Path], float]] = {}
        self._card_to_item: Dict[ProjectCard, QtWidgets.QListWidgetItem] = {}
        self._project_watch_enabled = True
        self._asset_watch_enabled = True

        central = QtWidgets.QWidget()
        central.setStyleSheet(
            "QWidget { background: #1f2329; color: #d8dde5; }"
            "QListWidget { background: #1f2329; border: none; }"
            "QLineEdit { background: #2b2f36; border: 1px solid #14171c; padding: 4px 6px; }"
            "QPushButton { background: #2b2f36; border: 1px solid #14171c; padding: 4px 8px; }"
            "QPushButton:hover { background: #323741; }"
            "QComboBox { background: #2b2f36; border: 1px solid #14171c; padding: 2px 6px; }"
        )
        self.setCentralWidget(central)
        outer = QtWidgets.QHBoxLayout(central)

        main_panel = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(main_panel)
        outer.addWidget(main_panel, 1)

        self.pages = QtWidgets.QStackedWidget()
        layout.addWidget(self.pages, 1)

        from ui.pages.client_page import ClientPage
        from ui.pages.projects_page import ProjectsPage
        from ui.pages.server_page import AssetManagerPage
        from ui.pages.settings_page import SettingsPage

        self.projects_page = ProjectsPage(self.projects_dir)
        self.pages.addWidget(self.projects_page)

        self.asset_page = AssetManagerPage(self._video_backend_pref, parent=self)
        self.pages.addWidget(self.asset_page)

        self.client_page = ClientPage(parent=self)
        self.pages.addWidget(self.client_page)

        self.settings_page = SettingsPage(
            self.projects_dir,
            self.server_repo_dir,
            self._template_hip,
            self._new_hip_pattern,
            self._video_backend_pref,
            self._use_file_association,
            self._houdini_exe,
        )
        self.pages.addWidget(self.settings_page)

        self.sidebar = QtWidgets.QFrame()
        self.sidebar.setFixedWidth(240)
        self.sidebar.setStyleSheet(
            "QFrame {"
            "background: #1f2329;"
            "border-left: 1px solid #0f1216;"
            "}"
        )
        outer.addWidget(self.sidebar, 0)

        side_layout = QtWidgets.QVBoxLayout(self.sidebar)
        side_layout.setContentsMargins(16, 18, 16, 18)
        side_layout.setSpacing(12)

        side_title = QtWidgets.QLabel("SKYFORGE")
        side_title.setAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter)
        title_font = QtGui.QFont()
        title_font.setBold(True)
        title_font.setPointSize(20)
        side_title.setFont(title_font)
        side_title.setStyleSheet("color: #cfd6df;")
        side_layout.addWidget(side_title)

        side_sub = QtWidgets.QLabel("Launcher")
        side_sub.setAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter)
        sub_font = QtGui.QFont()
        sub_font.setPointSize(14)
        side_sub.setFont(sub_font)
        side_sub.setStyleSheet("color: #9aa3ad;")
        side_layout.addWidget(side_sub)

        side_layout.addSpacing(18)

        side_layout.addStretch(1)

        nav_labels = ["Projects", "Asset Manager", "Clients", "Settings"]
        nav_buttons: List[QtWidgets.QToolButton] = []
        nav_font = QtGui.QFont()
        nav_font.setPointSize(18)
        for label in nav_labels:
            btn = QtWidgets.QToolButton()
            btn.setText(label)
            btn.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextOnly)
            btn.setAutoRaise(True)
            btn.setFont(nav_font)
            btn.setStyleSheet(
                "QToolButton { color: #c6ccd6; padding: 12px 14px; text-align: left; }"
                "QToolButton:hover { background: rgba(255,255,255,30); }"
            )
            btn.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed)
            side_layout.addWidget(btn)
            nav_buttons.append(btn)

        side_layout.addStretch(1)

        # Wire nav
        if nav_buttons:
            nav_buttons[0].clicked.connect(lambda: self.pages.setCurrentIndex(0))
        if len(nav_buttons) > 1:
            nav_buttons[1].clicked.connect(lambda: self.pages.setCurrentIndex(1))
        if len(nav_buttons) > 2:
            nav_buttons[2].clicked.connect(lambda: self.pages.setCurrentIndex(2))
        if len(nav_buttons) > 3:
            nav_buttons[3].clicked.connect(lambda: self.pages.setCurrentIndex(3))

        self.path_label = self.projects_page.path_label
        self.browse_btn = self.projects_page.browse_btn
        self.refresh_btn = self.projects_page.refresh_btn
        self.new_btn = self.projects_page.new_btn
        self.search_input = self.projects_page.search_input
        self.sort_combo = self.projects_page.sort_combo
        self.project_grid = self.projects_page.project_grid
        self.open_btn = self.projects_page.open_btn
        self.add_asset_btn = self.projects_page.add_asset_btn
        self.remove_asset_btn = self.projects_page.remove_asset_btn
        self.status = self.projects_page.status
        self.project_detail_panel = self.projects_page.detail_panel
        self.project_detail_tree = self.projects_page.detail_tree
        self.project_detail_title = self.projects_page.detail_title
        self.project_detail_open_btn = self.projects_page.detail_open_btn
        self.project_detail_close_btn = self.projects_page.detail_close_btn

        self.asset_pages = self.asset_page.asset_pages
        self.asset_search_input = self.asset_page.asset_search_input
        self.asset_refresh_btn = self.asset_page.asset_refresh_btn
        self.asset_auto_refresh = self.asset_page.asset_auto_refresh
        self.asset_path_label = self.asset_page.asset_path_label
        self.asset_grid = self.asset_page.asset_grid
        self.asset_back_btn = self.asset_page.asset_back_btn
        self.asset_details_title = self.asset_page.asset_details_title
        self.asset_shots_filter = self.asset_page.asset_shots_filter
        self.asset_shots_size = self.asset_page.asset_shots_size
        self.asset_shots_list = self.asset_page.asset_shots_list
        self.asset_assets_filter = self.asset_page.asset_assets_filter
        self.asset_assets_list = self.asset_page.asset_assets_list
        self.asset_entity_search = self.asset_page.asset_entity_search
        self.asset_open_folder_btn = self.asset_page.asset_open_folder_btn
        self.asset_work_tabs = self.asset_page.asset_work_tabs
        self.asset_preview = self.asset_page.asset_preview
        self.asset_prev_btn = self.asset_page.asset_prev_btn
        self.asset_next_btn = self.asset_page.asset_next_btn
        self.asset_preview_label = self.asset_page.asset_preview_label
        self.asset_meta = self.asset_page.asset_meta
        self.asset_status = self.asset_page.asset_status
        self.asset_video = self.asset_page.asset_video
        self.asset_play_btn = self.asset_page.asset_play_btn
        self.asset_fullscreen_btn = self.asset_page.asset_fullscreen_btn
        self.asset_video_slider = self.asset_page.asset_video_slider
        self.asset_context_combo = self.asset_page.asset_context_combo
        self.asset_versions_list = self.asset_page.asset_versions_list
        self.asset_versions_list.setContextMenuPolicy(
            QtCore.Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.asset_history_list = self.asset_page.asset_history_list
        self.asset_commit_box = self.asset_page.asset_commit_box
        self.asset_commit_btn = self.asset_page.asset_commit_btn
        self.asset_push_btn = self.asset_page.asset_push_btn
        self.asset_fetch_btn = self.asset_page.asset_fetch_btn
        self.asset_video_controller = self.asset_page.asset_video_controller
        self.asset_video_box = self.asset_page.asset_video_box
        self.asset_video_layout = self.asset_page.asset_video_layout

        self.client_refresh_btn = self.client_page.refresh_btn
        self.client_list = self.client_page.client_list
        self.client_preview = self.client_page.client_preview
        self.client_info = self.client_page.client_info
        self.client_bind_btn = self.client_page.bind_btn
        self.client_status = self.client_page.status

        self.settings_projects_dir = self.settings_page.settings_projects_dir
        self.settings_server_dir = self.settings_page.settings_server_dir
        self.settings_template_hip = self.settings_page.settings_template_hip
        self.settings_pattern = self.settings_page.settings_pattern
        self.settings_video_backend = self.settings_page.settings_video_backend
        self.settings_use_assoc = self.settings_page.settings_use_assoc
        self.settings_houdini_exe = self.settings_page.settings_houdini_exe
        self.settings_save_btn = self.settings_page.settings_save_btn

        self._asset_shot_size_map = {
            "Small": QtCore.QSize(140, 84),
            "Medium": QtCore.QSize(180, 110),
            "Large": QtCore.QSize(240, 150),
        }
        self._asset_video_fullscreen_dialog: Optional[QtWidgets.QDialog] = None
        self._asset_video_original_layout: Optional[QtWidgets.QLayout] = None

        self.browse_btn.clicked.connect(self.browse_projects_dir)
        self.refresh_btn.clicked.connect(self.refresh_projects)
        self.new_btn.clicked.connect(self.create_project)
        self.search_input.textChanged.connect(self.refresh_projects)
        self.sort_combo.currentIndexChanged.connect(self.refresh_projects)
        self.project_grid.itemDoubleClicked.connect(self.open_selected_project)
        self.project_grid.currentItemChanged.connect(self._on_project_selected)
        self.open_btn.clicked.connect(self.open_selected_project)
        self.project_detail_open_btn.clicked.connect(self._open_selected_project_folder)
        self.project_detail_close_btn.clicked.connect(self._close_project_detail_panel)
        self.add_asset_btn.clicked.connect(self.add_selected_project_to_asset_manager)
        self.remove_asset_btn.clicked.connect(self.remove_selected_project_from_asset_manager)

        self.asset_search_input.textChanged.connect(self.refresh_asset_manager)
        self.asset_refresh_btn.clicked.connect(self.refresh_asset_manager)
        self.asset_auto_refresh.toggled.connect(self._toggle_asset_auto_refresh)
        self.asset_grid.itemClicked.connect(self._open_asset_details)
        self.asset_grid.customContextMenuRequested.connect(self._show_asset_manager_context_menu)
        self.asset_shots_filter.currentTextChanged.connect(self._refresh_asset_entity_lists)
        self.asset_shots_size.currentTextChanged.connect(self._on_asset_shots_size_changed)
        self.asset_assets_filter.currentTextChanged.connect(self._refresh_asset_entity_lists)
        self.asset_entity_search.textChanged.connect(self._refresh_asset_entity_lists)
        self.asset_open_folder_btn.clicked.connect(self._open_asset_project_folder)
        self.asset_work_tabs.currentChanged.connect(self._on_asset_tab_changed)
        self.asset_shots_list.itemClicked.connect(self._on_asset_entity_clicked)
        self.asset_assets_list.itemClicked.connect(self._on_asset_entity_clicked)
        self.asset_assets_list.customContextMenuRequested.connect(self._show_asset_context_menu)
        self.asset_prev_btn.clicked.connect(self._prev_preview_image)
        self.asset_next_btn.clicked.connect(self._next_preview_image)
        self.asset_fullscreen_btn.clicked.connect(self._toggle_asset_video_fullscreen)
        self.asset_context_combo.currentTextChanged.connect(self._update_asset_context)
        self.asset_versions_list.itemClicked.connect(self._on_asset_version_clicked)
        self.asset_versions_list.customContextMenuRequested.connect(
            self._show_asset_version_context_menu
        )
        self.asset_commit_btn.clicked.connect(self._asset_placeholder_action)
        self.asset_push_btn.clicked.connect(self._asset_placeholder_action)
        self.asset_fetch_btn.clicked.connect(self._asset_placeholder_action)

        self.client_refresh_btn.clicked.connect(self.refresh_client_catalog)
        self.client_bind_btn.clicked.connect(self.clone_client_project)
        self.client_list.itemClicked.connect(self._on_client_project_selected)

        self.settings_save_btn.clicked.connect(self.save_settings_from_ui)

        self._apply_asset_shots_size(self.asset_shots_size.currentText(), refresh=False)

        self.refresh_projects()
        self._refresh_project_watch_paths()
        self.refresh_asset_manager()
        self.refresh_client_catalog()
        self._setup_asset_auto_refresh()
        self._asset_watch_enabled = self.asset_auto_refresh.isChecked()
        self._setup_project_watcher()
        self._setup_asset_watcher()

    def refresh_projects(self) -> None:
        self.project_grid.clear()
        self.project_detail_panel.setVisible(False)
        self._card_to_item.clear()
        projects = find_projects(self.projects_dir)
        self._prune_cache(projects, self._project_cache)
        query = self.search_input.text().strip().lower()
        if query:
            projects = [p for p in projects if query in p.name.lower()]

        sort_mode = self.sort_combo.currentText()
        if sort_mode.startswith("Date"):
            projects.sort(key=self._get_project_latest_mtime, reverse=True)
        else:
            projects.sort(key=lambda p: p.name.lower())

        for project in projects:
            item = QtWidgets.QListWidgetItem()
            item.setData(QtCore.Qt.ItemDataRole.UserRole, str(project))
            item.setSizeHint(QtCore.QSize(230, 240))
            self.project_grid.addItem(item)
            hips = self._get_project_hips(project)
            show_cloud = any(
                e.get("local_path") == str(project) and e.get("client_id") for e in self._asset_manager_projects
            )
            card = ProjectCard(project, self.project_grid.iconSize(), hips, show_cloud_badge=show_cloud, parent=self.project_grid)
            card.selection_changed.connect(self._on_card_selection_changed)
            self._card_to_item[card] = item
            self.project_grid.setItemWidget(item, card)
        self.status.setText(f"{self.project_grid.count()} project(s)")
        self._refresh_project_watch_paths()

    def refresh_asset_manager(self) -> None:
        self.asset_grid.clear()
        entries = list(self._asset_manager_projects)
        query = self.asset_search_input.text().strip().lower()
        if query:
            entries = [e for e in entries if query in str(e.get("local_path", "")).lower()]

        projects: List[Path] = []
        for entry in entries:
            path = Path(str(entry.get("local_path", "")))
            if path.exists() and path.is_dir():
                projects.append(path)

        self._prune_cache(projects, self._asset_cache)

        for project in projects:
            entry = next((e for e in entries if Path(e.get("local_path", "")) == project), None)
            show_cloud = bool(entry and entry.get("client_id"))
            item = QtWidgets.QListWidgetItem()
            item.setData(QtCore.Qt.ItemDataRole.UserRole, str(project))
            item.setSizeHint(QtCore.QSize(230, 240))
            self.asset_grid.addItem(item)
            hips = self._get_project_hips(project, self._asset_cache)
            card = ProjectCard(project, self.asset_grid.iconSize(), hips, show_cloud_badge=show_cloud, parent=self.asset_grid)
            self.asset_grid.setItemWidget(item, card)

        self.asset_status.setText(f"{self.asset_grid.count()} project(s) found.")
        self._refresh_asset_watch_paths()

    def _open_asset_details(self, item: QtWidgets.QListWidgetItem) -> None:
        project_path = Path(str(item.data(QtCore.Qt.ItemDataRole.UserRole)))
        self.asset_details_title.setText(project_path.name)
        self.asset_shots_list.clear()
        self.asset_assets_list.clear()
        self.asset_versions_list.clear()
        self.asset_history_list.clear()

        # Clear detail fields until an entity is selected
        self.asset_preview.clear()
        self.asset_meta.setText("Select a shot or asset to view details.")
        self.asset_versions_list.addItem("No entity selected")
        self.asset_history_list.addItem("No entity selected")

        # Populate shots/assets from selected server project (fallback to test pipeline)
        if project_path.exists():
            self._asset_current_project_root = project_path
        else:
            self._asset_current_project_root = TEST_PIPELINE_ROOT
        self._refresh_asset_entity_lists()

        self.asset_pages.setCurrentIndex(1)

    def _set_asset_status(self, text: str) -> None:
        if not text:
            self.asset_status.setText("")
            self.asset_status.setToolTip("")
            return
        metrics = QtGui.QFontMetrics(self.asset_status.font())
        width = max(self.asset_status.width(), 320)
        elided = metrics.elidedText(
            text,
            QtCore.Qt.TextElideMode.ElideMiddle,
            width,
        )
        self.asset_status.setText(elided)
        self.asset_status.setToolTip(text)

    @staticmethod
    def _to_houdini_path(text: str) -> str:
        # Houdini references are happier with forward slashes, even on Windows.
        return text.replace("\\", "/")

    def _show_asset_version_context_menu(self, pos: QtCore.QPoint) -> None:
        item = self.asset_versions_list.itemAt(pos)
        if item is None:
            return
        widget = self.asset_versions_list.itemWidget(item)
        path_text = item.data(QtCore.Qt.ItemDataRole.UserRole)
        kind = item.data(QtCore.Qt.ItemDataRole.UserRole + 1)
        if isinstance(widget, AssetVersionRow):
            path, kind = widget.selected_path()
            path_text = str(path) if path else ""
        if not path_text or not isinstance(path_text, str):
            return
        menu = QtWidgets.QMenu(self)
        label = "Copy Path" if kind not in ("usd", "video", "image") else f"Copy {str(kind).upper()} Path"
        action = menu.addAction(label)
        chosen = menu.exec(self.asset_versions_list.mapToGlobal(pos))
        if chosen == action:
            normalized = self._to_houdini_path(path_text)
            QtWidgets.QApplication.clipboard().setText(normalized)
            self._set_asset_status(f"Copied: {normalized}")

    def _show_asset_context_menu(self, pos: QtCore.QPoint) -> None:
        item = self.asset_assets_list.itemAt(pos)
        if item is None:
            return
        menu = QtWidgets.QMenu(self)
        action = menu.addAction("Copy Asset Path")
        chosen = menu.exec(self.asset_assets_list.mapToGlobal(pos))
        if chosen == action:
            path = str(item.data(QtCore.Qt.ItemDataRole.UserRole))
            normalized = self._to_houdini_path(path)
            QtWidgets.QApplication.clipboard().setText(normalized)
            self._set_asset_status(f"Copied: {normalized}")

    def _refresh_asset_entity_lists(self) -> None:
        project_root = getattr(self, "_asset_current_project_root", TEST_PIPELINE_ROOT)
        shots_root = project_root / "shots"
        assets_root = project_root / "assets"

        shots = sorted([p for p in shots_root.iterdir() if p.is_dir()]) if shots_root.exists() else []
        assets = sorted([p for p in assets_root.iterdir() if p.is_dir()]) if assets_root.exists() else []

        # Build filter options from prefixes
        shot_prefixes = sorted({name_prefix(p.name) for p in shots})
        asset_prefixes = sorted({name_prefix(p.name) for p in assets})

        prev_shot_filter = self.asset_shots_filter.currentText() if self.asset_shots_filter.count() else "All"
        prev_asset_filter = self.asset_assets_filter.currentText() if self.asset_assets_filter.count() else "All"

        self.asset_shots_filter.blockSignals(True)
        self.asset_shots_filter.clear()
        self.asset_shots_filter.addItem("All")
        for p in shot_prefixes:
            self.asset_shots_filter.addItem(p)
        if prev_shot_filter in [self.asset_shots_filter.itemText(i) for i in range(self.asset_shots_filter.count())]:
            self.asset_shots_filter.setCurrentText(prev_shot_filter)
        else:
            self.asset_shots_filter.setCurrentText("All")
        self.asset_shots_filter.blockSignals(False)

        self.asset_assets_filter.blockSignals(True)
        self.asset_assets_filter.clear()
        self.asset_assets_filter.addItem("All")
        for p in asset_prefixes:
            self.asset_assets_filter.addItem(p)
        if prev_asset_filter in [self.asset_assets_filter.itemText(i) for i in range(self.asset_assets_filter.count())]:
            self.asset_assets_filter.setCurrentText(prev_asset_filter)
        else:
            self.asset_assets_filter.setCurrentText("All")
        self.asset_assets_filter.blockSignals(False)

        # Apply filters
        shot_filter = self.asset_shots_filter.currentText()
        asset_filter = self.asset_assets_filter.currentText()
        search_text = self.asset_entity_search.text().strip().lower()
        active_tab = self.asset_work_tabs.currentIndex()

        shot_icon_size = self.asset_shots_list.iconSize()
        asset_icon_size = self.asset_assets_list.iconSize()

        self.asset_shots_list.clear()
        for shot_dir in shots:
            if shot_filter != "All" and name_prefix(shot_dir.name) != shot_filter:
                continue
            if active_tab == 0 and search_text and search_text not in shot_dir.name.lower():
                continue
            shot_item = QtWidgets.QListWidgetItem(shot_dir.name)
            shot_item.setData(QtCore.Qt.ItemDataRole.UserRole, str(shot_dir))
            preview = latest_preview_image(shot_dir)
            if preview:
                pix = QtGui.QPixmap(str(preview))
                if pix.isNull():
                    pix = build_thumbnail_pixmap(shot_dir, shot_icon_size)
                else:
                    pix = pix.scaled(
                        shot_icon_size,
                        QtCore.Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                        QtCore.Qt.TransformationMode.SmoothTransformation,
                    )
            else:
                pix = build_thumbnail_pixmap(shot_dir, shot_icon_size)
            thumb = pix
            shot_item.setIcon(QtGui.QIcon(thumb))
            self.asset_shots_list.addItem(shot_item)

        self.asset_assets_list.clear()
        for asset_dir in assets:
            if asset_filter != "All" and name_prefix(asset_dir.name) != asset_filter:
                continue
            if active_tab == 1 and search_text and search_text not in asset_dir.name.lower():
                continue
            asset_item = QtWidgets.QListWidgetItem(asset_dir.name)
            asset_item.setData(QtCore.Qt.ItemDataRole.UserRole, str(asset_dir))
            preview = latest_preview_image(asset_dir)
            if preview:
                pix = QtGui.QPixmap(str(preview))
                if pix.isNull():
                    pix = build_thumbnail_pixmap(asset_dir, asset_icon_size)
                else:
                    pix = pix.scaled(
                        asset_icon_size,
                        QtCore.Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                        QtCore.Qt.TransformationMode.SmoothTransformation,
                    )
            else:
                pix = build_thumbnail_pixmap(asset_dir, asset_icon_size)
            thumb = pix
            asset_item.setIcon(QtGui.QIcon(thumb))
            self.asset_assets_list.addItem(asset_item)

    def _apply_asset_shots_size(self, label: str, refresh: bool = True) -> None:
        size = self._asset_shot_size_map.get(label, self._asset_shot_size_map["Medium"])
        self.asset_shots_list.setIconSize(size)
        grid = QtCore.QSize(size.width() + 20, size.height() + 40)
        self.asset_shots_list.setGridSize(grid)
        if refresh:
            self._refresh_asset_entity_lists()

    def _on_asset_shots_size_changed(self, label: str) -> None:
        self._apply_asset_shots_size(label, refresh=True)

    def refresh_client_catalog(self) -> None:
        self.client_list.clear()
        self.client_preview.setText("Select a project")
        self.client_preview.setPixmap(QtGui.QPixmap())
        self.client_info.setText("")
        client_projects = find_projects(self.server_repo_dir)
        for project in client_projects:
            item = QtWidgets.QListWidgetItem(project.name)
            item.setData(QtCore.Qt.ItemDataRole.UserRole, str(project))
            self.client_list.addItem(item)
        self.client_status.setText(f"{self.client_list.count()} client project(s)")

    def clone_client_project(self) -> None:
        client_item = self.client_list.currentItem()
        if client_item is None:
            self.client_status.setText("Select a client project.")
            return
        client_path = Path(str(client_item.data(QtCore.Qt.ItemDataRole.UserRole)))
        client_id = client_path.name
        if not client_path.exists():
            self.client_status.setText("Client project not found.")
            return

        local_path = self.projects_dir / client_id
        if local_path.exists():
            self.client_status.setText("Local project already exists.")
            return

        try:
            local_path.mkdir(parents=True, exist_ok=False)
            for folder in ("assets", "shots"):
                src = client_path / folder
                dst = local_path / folder
                if src.exists() and src.is_dir():
                    shutil.copytree(src, dst)
            for ext in (".png", ".jpg", ".jpeg"):
                thumb = client_path / f"thumbnail{ext}"
                if thumb.exists():
                    shutil.copy2(thumb, local_path / thumb.name)
                    break
        except Exception as exc:
            self.client_status.setText(f"Clone failed: {exc}")
            return

        entry = next((e for e in self._asset_manager_projects if e.get("local_path") == str(local_path)), None)
        if entry is None:
            entry = {"local_path": str(local_path), "client_id": client_id}
            self._asset_manager_projects.append(entry)
        else:
            entry["client_id"] = client_id

        self.settings["asset_manager_projects"] = list(self._asset_manager_projects)
        save_settings(self.settings)
        self.refresh_projects()
        self.refresh_asset_manager()
        self.refresh_client_catalog()
        self.client_status.setText(f"Cloned {client_id} to local.")

    def _on_client_project_selected(self, item: QtWidgets.QListWidgetItem) -> None:
        client_path = Path(str(item.data(QtCore.Qt.ItemDataRole.UserRole)))
        self.client_info.setText(f"Project: {client_path.name}\nServer: {client_path}")
        preview = latest_preview_image(client_path)
        if preview:
            pixmap = QtGui.QPixmap(str(preview))
            if not pixmap.isNull():
                self.client_preview.setPixmap(
                    pixmap.scaled(
                        self.client_preview.size(),
                        QtCore.Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                        QtCore.Qt.TransformationMode.SmoothTransformation,
                    )
                )
                return
        self.client_preview.setText("No preview")

    def _on_asset_entity_clicked(self, item: QtWidgets.QListWidgetItem) -> None:
        entity_path = Path(str(item.data(QtCore.Qt.ItemDataRole.UserRole)))
        self._load_entity_details(entity_path)

    def _on_asset_tab_changed(self, index: int) -> None:
        if index == 0:
            self.asset_entity_search.setPlaceholderText("Search shots...")
        else:
            self.asset_entity_search.setPlaceholderText("Search assets...")
        self._refresh_asset_entity_lists()

    def _load_entity_details(self, entity_dir: Path) -> None:
        self._asset_current_entity = entity_dir
        self._asset_current_entity_type = "shot" if entity_dir.parent.name == "shots" else "asset"
        self._preview_images = list_preview_images(entity_dir)
        self._preview_index = 0
        if self._preview_images:
            preview = self._preview_images[self._preview_index]
            pixmap = QtGui.QPixmap(str(preview))
            if not pixmap.isNull():
                self.asset_preview.setPixmap(
                    pixmap.scaled(
                        self.asset_preview.size(),
                        QtCore.Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                        QtCore.Qt.TransformationMode.SmoothTransformation,
                    )
                )
                self.asset_video_controller.show_image(pixmap)
            self._update_preview_label()
        else:
            self.asset_preview.setPixmap(build_thumbnail_pixmap(entity_dir, QtCore.QSize(420, 200)))
            self._update_preview_label()

        meta = load_metadata(entity_dir)
        owner = meta.get("owner", "Unknown")
        status = meta.get("status", "WIP")
        context = self.asset_context_combo.currentText()
        if self._asset_current_entity_type == "shot":
            context = self._pick_best_context(entity_dir, context)
        normalized = context.strip().lower()
        list_context = None if normalized in ("all", "tous", "toutes") else context
        self.asset_meta.setText(
            f"Owner: {owner}\n"
            f"Status: {status}\n"
            f"Context: {context}\n"
            f"Entity: {entity_dir.name}"
        )

        self.asset_versions_list.clear()
        usd_versions = list_usd_versions(
            entity_dir,
            context=list_context,
            search_locations=self._asset_schema.get("usd_search"),
        )
        video_versions = list_review_videos(entity_dir, context=list_context) if self._asset_current_entity_type == "shot" else []
        image_versions = list_preview_images(entity_dir)
        grouped = group_asset_versions(usd_versions, video_versions, image_versions)
        if grouped:
            for base_name, entries in grouped.items():
                row = AssetVersionRow(base_name, entries, parent=self.asset_versions_list)
                item = QtWidgets.QListWidgetItem()
                item.setSizeHint(QtCore.QSize(280, 40))
                self.asset_versions_list.addItem(item)
                self.asset_versions_list.setItemWidget(item, row)

                def sync_item_data(
                    _row: AssetVersionRow = row,
                    _item: QtWidgets.QListWidgetItem = item,
                ) -> None:
                    path, kind = _row.selected_path()
                    if path is None:
                        _item.setData(QtCore.Qt.ItemDataRole.UserRole, "")
                        _item.setData(QtCore.Qt.ItemDataRole.UserRole + 1, None)
                        return
                    _item.setData(QtCore.Qt.ItemDataRole.UserRole, str(path))
                    _item.setData(QtCore.Qt.ItemDataRole.UserRole + 1, kind)

                def sync_item_data_and_preview(
                    _row: AssetVersionRow = row,
                    _item: QtWidgets.QListWidgetItem = item,
                ) -> None:
                    sync_item_data(_row, _item)
                    path, kind = _row.selected_path()
                    if path is not None:
                        self._sync_asset_version_preview(path, kind)

                row.selection_changed.connect(sync_item_data_and_preview)
                sync_item_data()
        else:
            if self._asset_current_entity_type == "shot":
                self.asset_versions_list.addItem("No published USD/Video for this context")
            else:
                self.asset_versions_list.addItem("No published USD for this context")

        if not self._preview_images and video_versions:
            self.asset_video_controller.preview_first_frame(video_versions[0])

        self.asset_history_list.clear()
        notes_path = entity_dir / "notes.txt"
        if notes_path.exists():
            try:
                note = notes_path.read_text(encoding="utf-8").strip()
            except Exception:
                note = ""
            if note:
                self.asset_history_list.addItem(note)
            else:
                self.asset_history_list.addItem("No history yet")
        else:
            self.asset_history_list.addItem("No history yet")

    def _update_preview_label(self) -> None:
        total = len(getattr(self, "_preview_images", []))
        index = getattr(self, "_preview_index", 0) + 1 if total else 0
        self.asset_preview_label.setText(f"{index}/{total}")
        self.asset_prev_btn.setEnabled(total > 1)
        self.asset_next_btn.setEnabled(total > 1)

    def _show_preview_at(self, index: int) -> None:
        if not getattr(self, "_preview_images", []):
            return
        total = len(self._preview_images)
        self._preview_index = index % total
        preview = self._preview_images[self._preview_index]
        pixmap = QtGui.QPixmap(str(preview))
        if not pixmap.isNull():
            self.asset_preview.setPixmap(
                pixmap.scaled(
                    self.asset_preview.size(),
                    QtCore.Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    QtCore.Qt.TransformationMode.SmoothTransformation,
                )
            )
            self.asset_video_controller.show_image(pixmap)
        self._update_preview_label()

    def _prev_preview_image(self) -> None:
        self._show_preview_at(getattr(self, "_preview_index", 0) - 1)

    def _next_preview_image(self) -> None:
        self._show_preview_at(getattr(self, "_preview_index", 0) + 1)

    def _toggle_asset_video_fullscreen(self) -> None:
        if self._asset_video_fullscreen_dialog and self._asset_video_fullscreen_dialog.isVisible():
            self._asset_video_fullscreen_dialog.close()
            return

        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Video Preview")
        dialog.setWindowFlag(QtCore.Qt.WindowType.Window, True)
        dialog.setModal(False)
        layout = QtWidgets.QVBoxLayout(dialog)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._asset_video_original_layout = self.asset_video_layout
        if self._asset_video_original_layout is not None:
            self._asset_video_original_layout.removeWidget(self.asset_video)
        layout.addWidget(self.asset_video)
        dialog.finished.connect(self._restore_asset_video_from_fullscreen)
        self._asset_video_fullscreen_dialog = dialog
        dialog.showFullScreen()

    def _restore_asset_video_from_fullscreen(self) -> None:
        if self._asset_video_original_layout is not None:
            self._asset_video_original_layout.insertWidget(0, self.asset_video, 1)
        if self._asset_video_fullscreen_dialog is not None:
            self._asset_video_fullscreen_dialog.deleteLater()
        self._asset_video_fullscreen_dialog = None

    def _update_asset_context(self, context: str) -> None:
        current = self.asset_meta.text().splitlines()
        rebuilt = []
        replaced = False
        for line in current:
            if line.startswith("Context:"):
                rebuilt.append(f"Context: {context}")
                replaced = True
            else:
                rebuilt.append(line)
        if not replaced:
            rebuilt.insert(2, f"Context: {context}")
        self.asset_meta.setText("\n".join(rebuilt))
        entity = getattr(self, "_asset_current_entity", None)
        if entity:
            self._load_entity_details(Path(entity))

    def _pick_best_context(self, entity_dir: Path, current: str) -> str:
        if self._asset_current_entity_type != "shot":
            return current
        if current.strip().lower() in ("all", "tous", "toutes"):
            return current

        def has_content(ctx: str) -> bool:
            if list_usd_versions(
                entity_dir,
                context=ctx,
                search_locations=self._asset_schema.get("usd_search"),
            ):
                return True
            if list_review_videos(entity_dir, context=ctx):
                return True
            return False

        if current and has_content(current):
            return current

        contexts = [self.asset_context_combo.itemText(i) for i in range(self.asset_context_combo.count())]
        for ctx in contexts:
            if has_content(ctx):
                if ctx != current:
                    self.asset_context_combo.blockSignals(True)
                    self.asset_context_combo.setCurrentText(ctx)
                    self.asset_context_combo.blockSignals(False)
                return ctx
        return current

    def _on_asset_version_clicked(self, item: QtWidgets.QListWidgetItem) -> None:
        kind = item.data(QtCore.Qt.ItemDataRole.UserRole + 1)
        path_text = item.data(QtCore.Qt.ItemDataRole.UserRole)
        if not path_text:
            return
        path = Path(str(path_text))
        if kind == "video" and path.exists():
            self.asset_video_controller.play_path(path)
            return
        if path.exists():
            self._sync_asset_version_preview(path, kind)

    def _sync_asset_version_preview(self, path: Path, kind: Optional[str]) -> None:
        if not path.exists():
            return
        if kind == "video":
            self.asset_video_controller.preview_first_frame(path)
            return
        if kind == "image":
            images = getattr(self, "_preview_images", [])
            if images and path in images:
                self._show_preview_at(images.index(path))
                return
            pixmap = QtGui.QPixmap(str(path))
            if not pixmap.isNull():
                self.asset_video_controller.show_image(pixmap)

    def _prune_cache(self, projects: List[Path], cache: Dict[Path, Tuple[float, List[Path], float]]) -> None:
        keep = set(projects)
        for key in list(cache.keys()):
            if key not in keep:
                cache.pop(key, None)

    def _get_project_hips(
        self, project_path: Path, cache: Optional[Dict[Path, Tuple[float, List[Path], float]]] = None
    ) -> List[Path]:
        cache = cache or self._project_cache
        try:
            mtime = project_path.stat().st_mtime
        except OSError:
            return []

        cached = cache.get(project_path)
        if cached and cached[0] == mtime:
            return cached[1]

        hips = find_hips(project_path)
        latest = max((p.stat().st_mtime for p in hips), default=0.0)
        cache[project_path] = (mtime, hips, latest)
        return hips

    def _get_project_latest_mtime(
        self, project_path: Path, cache: Optional[Dict[Path, Tuple[float, List[Path], float]]] = None
    ) -> float:
        cache = cache or self._project_cache
        try:
            mtime = project_path.stat().st_mtime
        except OSError:
            return 0.0

        cached = cache.get(project_path)
        if cached and cached[0] == mtime:
            return cached[2]

        hips = find_hips(project_path)
        latest = max((p.stat().st_mtime for p in hips), default=mtime)
        cache[project_path] = (mtime, hips, latest)
        return latest

    def browse_projects_dir(self) -> None:
        directory = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            "Select Projects Folder",
            str(self.projects_dir),
        )
        if not directory:
            return
        self.projects_dir = Path(directory)
        self.path_label.setText(f"Projects: {self.projects_dir}")
        self.refresh_projects()
        self._refresh_project_watch_paths()

    def save_settings_from_ui(self) -> None:
        projects_dir = self.settings_projects_dir.text().strip()
        server_repo_dir = self.settings_server_dir.text().strip()
        template_hip = self.settings_template_hip.text().strip()
        pattern = self.settings_pattern.text().strip()
        use_assoc = self.settings_use_assoc.isChecked()
        houdini_exe = normalize_houdini_exe(self.settings_houdini_exe.text())
        backend_label = self.settings_video_backend.currentText().strip().lower()
        if backend_label == "opencv":
            video_backend = "opencv"
        elif backend_label == "qt":
            video_backend = "qt"
        elif backend_label == "off":
            video_backend = "none"
        else:
            video_backend = "auto"

        self.settings.update(
            {
                "projects_dir": projects_dir,
                "server_repo_dir": server_repo_dir,
                "template_hip": template_hip,
                "new_hip_pattern": pattern,
                "use_file_association": use_assoc,
                "houdini_exe": houdini_exe,
                "video_backend": video_backend,
                "asset_manager_projects": list(self._asset_manager_projects),
            }
        )
        save_settings(self.settings)

        self.projects_dir = Path(projects_dir) if projects_dir else DEFAULT_PROJECTS_DIR
        self.server_repo_dir = Path(server_repo_dir) if server_repo_dir else Path(DEFAULT_SETTINGS["server_repo_dir"])
        self._template_hip = Path(template_hip) if template_hip else DEFAULT_TEMPLATE_HIP
        self._new_hip_pattern = pattern or "{projectName}_001.hipnc"
        self._use_file_association = bool(use_assoc)
        self._houdini_exe = houdini_exe
        self._video_backend_pref = video_backend

        self.path_label.setText(f"Projects: {self.projects_dir}")
        self.refresh_projects()
        self.refresh_asset_manager()
        self._refresh_project_watch_paths()
        self._refresh_asset_watch_paths()

    def add_selected_project_to_asset_manager(self) -> None:
        item = self.project_grid.currentItem()
        if item is None:
            self._warn("Select a project first.")
            return
        path_text = item.data(QtCore.Qt.ItemDataRole.UserRole)
        if not path_text:
            self._warn("Select a project first.")
            return
        project_path = str(path_text)
        for entry in self._asset_manager_projects:
            if entry.get("local_path") == project_path:
                self.status.setText("Already in Asset Manager.")
                return
        self._asset_manager_projects.append({"local_path": project_path, "client_id": None})
        self.settings["asset_manager_projects"] = list(self._asset_manager_projects)
        save_settings(self.settings)
        self.refresh_asset_manager()
        self.status.setText("Added to Asset Manager.")

    def remove_selected_project_from_asset_manager(self) -> None:
        item = self.project_grid.currentItem()
        if item is None:
            self._warn("Select a project first.")
            return
        path_text = item.data(QtCore.Qt.ItemDataRole.UserRole)
        if not path_text:
            self._warn("Select a project first.")
            return
        project_path = str(path_text)
        before = len(self._asset_manager_projects)
        self._asset_manager_projects = [
            e for e in self._asset_manager_projects if e.get("local_path") != project_path
        ]
        if len(self._asset_manager_projects) == before:
            self.status.setText("Not in Asset Manager.")
            return
        self.settings["asset_manager_projects"] = list(self._asset_manager_projects)
        save_settings(self.settings)
        self.refresh_asset_manager()
        self.status.setText("Removed from Asset Manager.")

    def _show_asset_manager_context_menu(self, pos: QtCore.QPoint) -> None:
        item = self.asset_grid.itemAt(pos)
        if item is None:
            return
        menu = QtWidgets.QMenu(self)
        remove_action = menu.addAction("Remove from Asset Manager")
        chosen = menu.exec(self.asset_grid.mapToGlobal(pos))
        if chosen != remove_action:
            return
        path_text = item.data(QtCore.Qt.ItemDataRole.UserRole)
        if not path_text:
            return
        project_path = str(path_text)
        self._asset_manager_projects = [
            e for e in self._asset_manager_projects if e.get("local_path") != project_path
        ]
        self.settings["asset_manager_projects"] = list(self._asset_manager_projects)
        save_settings(self.settings)
        self.refresh_asset_manager()

    def create_project(self) -> None:
        name, ok = QtWidgets.QInputDialog.getText(self, "New Project", "Project name:")
        if not ok:
            return
        name = name.strip()
        if not name:
            self._warn("Project name cannot be empty.")
            return
        project_path = self.projects_dir / name
        if project_path.exists():
            self._warn("A project with this name already exists.")
            return

        try:
            project_path.mkdir(parents=True, exist_ok=False)
            for subdir in PROJECT_SUBDIRS:
                (project_path / subdir).mkdir(parents=False, exist_ok=True)
            self._ensure_template_hip(project_path)
            (project_path / JOB_INIT_MARKER).write_text("init_job", encoding="utf-8")
        except Exception as exc:  # pragma: no cover - filesystem errors
            self._warn(f"Failed to create project:\n{exc}")
            return

        self.refresh_projects()

    def _resolve_new_hip_name(self, project_name: str) -> str:
        pattern = self._new_hip_pattern.strip() or "{projectName}_001.hipnc"
        try:
            return pattern.format(projectName=project_name)
        except Exception:
            return f"{project_name}_001.hipnc"

    def _resolve_template_hip(self) -> Optional[Path]:
        launcher_default = Path(__file__).resolve().parent / "untitled.hipnc"
        candidates = [self._template_hip, DEFAULT_TEMPLATE_HIP, launcher_default]
        for candidate in candidates:
            if candidate and candidate.exists():
                return candidate
        return None

    def _ensure_template_hip(self, project_path: Path) -> Optional[Path]:
        template = self._resolve_template_hip()
        if template is None:
            missing = "\n".join(
                str(p)
                for p in [
                    self._template_hip,
                    DEFAULT_TEMPLATE_HIP,
                    Path(__file__).resolve().parent / "untitled.hipnc",
                ]
            )
            self._warn(f"Template hip not found. Checked:\n{missing}")
            return None

        target_name = self._resolve_new_hip_name(project_path.name)
        target = project_path / target_name
        if target.exists():
            return target

        shutil.copy2(template, target)
        return target

    def _ensure_job_scripts(self, project_path: Path) -> None:
        scripts_dir = project_path / "scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        content = (
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
        for name in ("123.py", "456.py"):
            script_path = scripts_dir / name
            try:
                script_path.write_text(content, encoding="utf-8")
            except Exception:
                pass

    def _ensure_job_scripts_if_needed(self, project_path: Path) -> None:
        marker = project_path / JOB_INIT_MARKER
        if not marker.exists():
            return
        self._ensure_job_scripts(project_path)
        try:
            marker.unlink()
        except Exception:
            pass

    def open_selected_project(self) -> None:
        item = self.project_grid.currentItem()
        if item is None:
            self._warn("Select a project first.")
            return
        project_path = Path(item.data(QtCore.Qt.ItemDataRole.UserRole))
        card = self.project_grid.itemWidget(item)
        hip: Optional[Path] = None
        if isinstance(card, ProjectCard):
            hip = card.selected_hip()
        if hip is None:
            hip = self._ensure_template_hip(project_path)
            if hip is None:
                self._warn(f"No .hip found in {project_path.name}.")
                return
        try:
            if self._use_file_association or not self._houdini_exe:
                open_hip(hip)
            else:
                self._ensure_job_scripts_if_needed(project_path)
                self._launch_houdini(hip, project_path)
            self.status.setText(f"Opened: {hip.name}")
        except Exception as exc:  # pragma: no cover - UI error path
            self._warn(f"Failed to open: {hip}\n{exc}")

    def _warn(self, message: str) -> None:
        QtWidgets.QMessageBox.warning(self, APP_TITLE, message)

    def _on_card_selection_changed(self, card: ProjectCard) -> None:
        item = self._card_to_item.get(card)
        if item is not None:
            self.project_grid.setCurrentItem(item)
        hip = card.selected_hip()
        if hip is not None:
            self.status.setText(f"Selected: {hip.name}")

    def _on_project_selected(
        self,
        current: Optional[QtWidgets.QListWidgetItem],
        _previous: Optional[QtWidgets.QListWidgetItem],
    ) -> None:
        if current is None:
            self.project_detail_panel.setVisible(False)
            return
        path_text = current.data(QtCore.Qt.ItemDataRole.UserRole)
        if not path_text:
            self.project_detail_panel.setVisible(False)
            return
        project_path = Path(str(path_text))
        if not project_path.exists():
            self.project_detail_panel.setVisible(False)
            return

        self.project_detail_panel.setVisible(True)
        self.project_detail_title.setText(f"Structure: {project_path.name}")
        self.project_detail_tree.clear()

        root_item = QtWidgets.QTreeWidgetItem([project_path.name])
        self.project_detail_tree.addTopLevelItem(root_item)

        try:
            children = sorted(project_path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except OSError:
            children = []

        for child in children:
            child_item = QtWidgets.QTreeWidgetItem([child.name])
            root_item.addChild(child_item)
            if child.is_dir():
                try:
                    sub_items = sorted(child.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
                except OSError:
                    sub_items = []
                for sub in sub_items:
                    child_item.addChild(QtWidgets.QTreeWidgetItem([sub.name]))

        root_item.setExpanded(True)

    def _open_selected_project_folder(self) -> None:
        item = self.project_grid.currentItem()
        if item is None:
            return
        path_text = item.data(QtCore.Qt.ItemDataRole.UserRole)
        if not path_text:
            return
        project_path = Path(str(path_text))
        if not project_path.exists():
            return
        os.startfile(str(project_path))  # type: ignore[attr-defined]

    def _open_asset_project_folder(self) -> None:
        project_root = getattr(self, "_asset_current_project_root", None)
        if project_root is None:
            item = self.asset_grid.currentItem()
            if item is None:
                return
            path_text = item.data(QtCore.Qt.ItemDataRole.UserRole)
            if not path_text:
                return
            project_root = Path(str(path_text))
        if not Path(project_root).exists():
            return
        os.startfile(str(project_root))  # type: ignore[attr-defined]

    def _close_project_detail_panel(self) -> None:
        self.project_detail_panel.setVisible(False)
        self.project_grid.clearSelection()

    def _launch_houdini(self, hip: Path, project_path: Path) -> None:
        if not self._houdini_exe:
            open_hip(hip)
            return
        env = os.environ.copy()
        env["JOB"] = str(project_path)
        env["HIP"] = str(project_path)
        # Ensure project folder is on HOUDINI_PATH so per-project scripts can be found
        existing_hpath = env.get("HOUDINI_PATH", "")
        project_hpath = f"{project_path};&"
        env["HOUDINI_PATH"] = project_hpath + (existing_hpath or "")
        subprocess.Popen([self._houdini_exe, str(hip)], env=env)

    def _asset_placeholder_action(self) -> None:
        self.asset_status.setText("Git actions coming soon (commit/push/fetch).")

    def _setup_asset_auto_refresh(self) -> None:
        self._asset_refresh_timer = QtCore.QTimer(self)
        self._asset_refresh_timer.setInterval(60000)
        self._asset_refresh_timer.timeout.connect(self.refresh_asset_manager)
        if self.asset_auto_refresh.isChecked():
            self._asset_refresh_timer.start()

    def _toggle_asset_auto_refresh(self, checked: bool) -> None:
        if not hasattr(self, "_asset_refresh_timer"):
            return
        if checked:
            self._asset_refresh_timer.start()
            self._asset_watch_enabled = True
            self._refresh_asset_watch_paths()
        else:
            self._asset_refresh_timer.stop()
            self._asset_watch_enabled = False
            self._refresh_asset_watch_paths()

    def _setup_project_watcher(self) -> None:
        self._project_watcher = QtCore.QFileSystemWatcher(self)
        self._project_watcher.directoryChanged.connect(self._queue_project_refresh)
        self._project_refresh_timer = QtCore.QTimer(self)
        self._project_refresh_timer.setSingleShot(True)
        self._project_refresh_timer.setInterval(500)
        self._project_refresh_timer.timeout.connect(self._run_project_refresh)
        self._refresh_project_watch_paths()

    def _setup_asset_watcher(self) -> None:
        self._asset_watcher = QtCore.QFileSystemWatcher(self)
        self._asset_watcher.directoryChanged.connect(self._queue_asset_refresh)
        self._asset_refresh_watch_timer = QtCore.QTimer(self)
        self._asset_refresh_watch_timer.setSingleShot(True)
        self._asset_refresh_watch_timer.setInterval(500)
        self._asset_refresh_watch_timer.timeout.connect(self._run_asset_refresh)
        self._refresh_asset_watch_paths()

    def _queue_project_refresh(self, _path: str) -> None:
        if not getattr(self, "_project_watch_enabled", True):
            return
        if not self._project_refresh_timer.isActive():
            self._project_refresh_timer.start()

    def _queue_asset_refresh(self, _path: str) -> None:
        if not getattr(self, "_asset_watch_enabled", True):
            return
        if not self._asset_refresh_watch_timer.isActive():
            self._asset_refresh_watch_timer.start()

    def _run_project_refresh(self) -> None:
        self._refresh_project_watch_paths()
        self.refresh_projects()

    def _run_asset_refresh(self) -> None:
        self._refresh_asset_watch_paths()
        self.refresh_asset_manager()
        if getattr(self.asset_pages, "currentIndex", lambda: 0)() == 1:
            self._refresh_asset_entity_lists()
            entity = getattr(self, "_asset_current_entity", None)
            if entity:
                self._load_entity_details(Path(entity))

    def _refresh_project_watch_paths(self) -> None:
        if not getattr(self, "_project_watch_enabled", True):
            if hasattr(self, "_project_watcher"):
                self._project_watcher.removePaths(self._project_watcher.directories())
            return
        if not hasattr(self, "_project_watcher"):
            return
        paths: List[Path] = []
        if self.projects_dir.exists():
            paths.append(self.projects_dir)
            paths.extend(find_projects(self.projects_dir))
        self._update_watcher_paths(self._project_watcher, paths)

    def _refresh_asset_watch_paths(self) -> None:
        if not getattr(self, "_asset_watch_enabled", True):
            if hasattr(self, "_asset_watcher"):
                self._asset_watcher.removePaths(self._asset_watcher.directories())
            return
        if not hasattr(self, "_asset_watcher"):
            return
        paths: List[Path] = []
        for entry in self._asset_manager_projects:
            raw = entry.get("local_path")
            if not raw:
                continue
            root = Path(str(raw))
            if not root.exists():
                continue
            paths.append(root)
            assets_root = root / "assets"
            shots_root = root / "shots"
            if assets_root.exists():
                paths.append(assets_root)
            if shots_root.exists():
                paths.append(shots_root)
        entity = getattr(self, "_asset_current_entity", None)
        if entity:
            entity_dir = Path(str(entity))
            if entity_dir.exists():
                paths.append(entity_dir)
        self._update_watcher_paths(self._asset_watcher, paths)

    @staticmethod
    def _update_watcher_paths(watcher: QtCore.QFileSystemWatcher, paths: List[Path]) -> None:
        desired = {str(p) for p in paths if p.exists()}
        current = set(watcher.directories())
        remove = list(current - desired)
        add = list(desired - current)
        if remove:
            watcher.removePaths(remove)
        if add:
            watcher.addPaths(add)


def main() -> None:
    try:
        app = QtWidgets.QApplication([])
        app_font = app.font()
        if app_font.pointSize() <= 0:
            app_font.setPointSize(10)
            app.setFont(app_font)
        window = LauncherWindow()
        window.show()
        app.exec()
    except Exception:
        log_path = Path(__file__).resolve().parent / "launcher_error.log"
        log_path.write_text(traceback.format_exc(), encoding="utf-8")
        raise


if __name__ == "__main__":
    main()

