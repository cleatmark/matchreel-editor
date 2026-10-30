@echo off
rem Re-captures the 8 user-guide screenshots from the running editor (video blurred, names fictionalized).
rem Start review_editor.bat first and keep the 10-28 (or another zoom-edited) game available.
cd /d "%~dp0"
python -m pip install --quiet playwright
python tools\editor\capture_guide_screenshots.py %*
pause
