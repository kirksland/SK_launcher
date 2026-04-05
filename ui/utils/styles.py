from __future__ import annotations

PALETTE = {
    "app_bg": "#1f2329",
    "panel_bg": "#2b2f36",
    "border": "#14171c",
    "text": "#d8dde5",
    "muted": "#9aa3ad",
    "light_text": "#cfd6df",
    "thumb_bg": "#23272e",
    "white": "#ffffff",
    "dark_text": "#111",
    "menu_border": "#d0d0d0",
    "menu_sel": "#e6e6e6",
}


def app_stylesheet() -> str:
    return (
        f"QWidget {{ background: {PALETTE['app_bg']}; color: {PALETTE['text']}; }}"
        f"QListWidget {{ background: {PALETTE['app_bg']}; border: none; }}"
        f"QLineEdit {{ background: {PALETTE['panel_bg']}; border: 1px solid {PALETTE['border']}; padding: 4px 6px; }}"
        f"QPushButton {{ background: {PALETTE['panel_bg']}; border: 1px solid {PALETTE['border']}; padding: 4px 8px; }}"
        f"QPushButton:hover {{ background: #323741; }}"
        f"QComboBox {{ background: {PALETTE['panel_bg']}; border: 1px solid {PALETTE['border']}; padding: 2px 6px; }}"
    )


def combo_dark_style(padding: str = "2px 6px", radius: int = 6) -> str:
    return (
        "QComboBox {"
        f"background: {PALETTE['panel_bg']};"
        f"color: {PALETTE['text']};"
        f"padding: {padding};"
        f"border: 1px solid {PALETTE['border']};"
        f"border-radius: {radius}px;"
        "}"
    )


def project_card_title_style() -> str:
    return (
        "QToolButton {"
        f"background: {PALETTE['white']};"
        f"color: {PALETTE['dark_text']};"
        "padding: 4px 6px;"
        "}"
    )


def project_card_menu_style() -> str:
    return (
        "QMenu {"
        f"background: {PALETTE['white']};"
        f"color: {PALETTE['dark_text']};"
        f"border: 1px solid {PALETTE['menu_border']};"
        "}"
        "QMenu::item {"
        "padding: 4px 24px 4px 10px;"
        "}"
        "QMenu::item:selected {"
        f"background: {PALETTE['menu_sel']};"
        "}"
    )


def project_card_version_combo_style() -> str:
    return (
        "QComboBox {"
        "background: rgba(20, 20, 20, 180);"
        "color: #fff;"
        "padding: 2px 14px 2px 10px;"
        "border: 1px solid rgba(255,255,255,80);"
        "border-radius: 6px;"
        "}"
        "QComboBox QAbstractItemView::item {"
        "padding: 2px 15px 2px 10px;"
        "}"
    )
