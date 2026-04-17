Skyforge Launcher - Dev Notes
=============================

Run
---
Use the batch file so the venv and Qt paths are set:
`run_launcher.bat`

Setup (Portable)
----------------
1) Install Python 3.11+ from python.org (avoid Microsoft Store Python).
2) During install, check: `Add python.exe to PATH`.
3) Run once:
   `setup.bat`
4) Launch:
   `run_launcher.bat`

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

UI:
- `ui/pages/projects_page.py`
- `ui/pages/server_page.py` (Asset Manager page)
- `ui/pages/settings_page.py`

Video:
- `video/player.py` backend selection + OpenCV playback + zoom/pan widget

Image tools (modular stack):
- `tools/image_tools/registry.py` auto-discovers image tools and applies tool stacks
- `tools/image_tools/bcs.py` brightness/contrast/saturation tool (`id: bcs`)
- `tools/image_tools/vibrance.py` vibrance tool (`id: vibrance`)

Tool plugin convention:
- Add a new `tools/image_tools/<name>.py`
- Register with `register_tool("<tool_id>", apply_fn)`
- `apply_fn(rgb, settings)` must return an RGB uint8 array

Entry point:
- `main.py` wires UI pages + logic
