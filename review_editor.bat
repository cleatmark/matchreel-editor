@echo off
rem No cd: the server runs from its own folder path, so Ctrl+C leaves your prompt where it was.
python -c "import socket, sys; s=socket.socket(); res=s.connect_ex(('127.0.0.1', 5000)); s.close(); sys.exit(0 if res==0 else 1)"
if %ERRORLEVEL% equ 0 (
    python -c "import urllib.request, json, datetime; resp=urllib.request.urlopen('http://127.0.0.1:5000/api/build-info', timeout=1.0); d=json.loads(resp.read()); t=d.get('server_start_str') or datetime.datetime.fromtimestamp(d.get('server_start', 0)).strftime('%%H:%%M:%%S'); print(f'Editor is already running on port 5000 (started {t}). Close that window first.')" 2>nul || echo Editor is already running on port 5000. Close that window first.
    pause
    exit /b 1
)
start "" "http://127.0.0.1:5000"
rem Restart by flag: creating tmp\restart_editor.flag makes the editor exit with code 75 and this loop starts it again (same window).
set XBOTGO_RESTART_LOOP=1
:run
python "%~dp0tools\editor\server.py"
if %ERRORLEVEL% equ 75 goto run
