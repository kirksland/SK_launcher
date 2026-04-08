Skyforge Launcher - Dev Notes
=============================

Run
---
Use the batch file so the venv and Qt paths are set:
`run_launcher.bat`

Setup (Portable)
----------------
1) Install a real Python from python.org (avoid the Microsoft Store build).
2) Create a venv in the project root:
   `py -3 -m venv venv`
3) Install dependencies:
   `venv\Scripts\pip.exe install -r requirements.txt`
4) Launch:
   `run_launcher.bat`

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

Entry point:
- `main.py` wires UI pages + logic
