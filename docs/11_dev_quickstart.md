Skyforge Launcher - Dev Notes
=============================

Run
---
Use the batch file so the venv and Qt paths are set:
`run_launcher.bat`

Tests
-----
Run the targeted refactor safety suite with the project venv:
`venv\Scripts\python.exe -m unittest discover -s tests -v`

Setup (Portable)
----------------
1) Install Python 3.11+ from python.org (avoid Microsoft Store Python).
2) During install, check: `Add python.exe to PATH`.
3) Run once:
   `setup.bat`
4) Launch:
   `run_launcher.bat`

First-run test
--------------
To simulate a new user config without touching your real local settings:
`run_first_launch_test.bat`

To reset that fresh test profile:
`run_first_launch_test.bat reset`

Build (Windows)
---------------
Install build-only dependency and produce a local PyInstaller build:
`build_windows.bat`

PyInstaller inputs:
- `skyforge_launcher.spec`
- `requirements-build.txt`

Quick glossary
--------------
- `venv`: a private Python environment for this project only.
- `pip`: Python's package installer (it installs libs like PySide6, numpy, OpenCV).

Notes
-----
- EXR support uses OpenEXR + OpenCV. If EXR previews are missing, make sure
  dependencies are installed and the app is launched via `run_launcher.bat`.

Structure
---------
Core utilities:
- `core/settings.py` settings IO + defaults
- `core/fs.py` filesystem listings + helpers
- `core/metadata.py` metadata loader
- `core/board_edit/*` board edit session, tool stack helpers, crop handles, media runtime
- `core/board_scene/*` board scene items and related scene-side structures

UI:
- `ui/pages/projects_page.py`
- `ui/pages/server_page.py` (Asset Manager page)
- `ui/pages/settings_page.py`
- `ui/pages/board_page.py`

Video:
- `video/player.py` backend selection + OpenCV playback + zoom/pan widget

Board / edit refactor note:
- `docs/03_board_edit_refactor_devnote.md`
- `docs/01_how_to_add_board_tool.md`

Image tools (modular stack):
- `tools/image_tools/registry.py` auto-discovers image tools and applies tool stacks
- `tools/image_tools/bcs.py` brightness/contrast/saturation tool (`id: bcs`)
- `tools/image_tools/vibrance.py` vibrance tool (`id: vibrance`)

Edit tool specs:
- `tools/edit_tools/*` declarative specs for board edit tools

Tool plugin convention:
- Add a new `tools/image_tools/<name>.py`
- Register with `register_tool("<tool_id>", apply_fn)`
- `apply_fn(rgb, settings)` must return an RGB uint8 array

Entry point:
- `main.py` wires UI pages + logic
