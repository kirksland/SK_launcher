Skyforge Launcher - Dev Notes
=============================

Run
---
Use the batch file so the venv and Qt paths are set:
`run_launcher.bat`

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
