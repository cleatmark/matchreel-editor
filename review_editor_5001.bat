@echo off
rem Test copy of the editor on port 5001 (the normal editor on 5000 keeps running). Close this window to stop it.
rem Restart by flag: creating tmp\restart_editor.flag restarts BOTH editors that were started by a .bat (same flag file).
rem No cd: your prompt stays in the folder you started from.
set XBOTGO_PORT=5001
start "" "http://127.0.0.1:5001"
set XBOTGO_RESTART_LOOP=1
:run
python "%~dp0tools\editor\server.py"
if %ERRORLEVEL% equ 75 goto run
