@echo off
rem Stops whatever listens on port 5000 (the old editor) and starts a fresh one.
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":5000 " ^| findstr LISTENING') do taskkill /F /PID %%p >nul 2>&1
timeout /t 2 >nul
call "%~dp0review_editor.bat"
