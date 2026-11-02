@echo off
rem Runs the full XbotGo editor test suite on a fresh synthetic project (no real data, no video work).
pushd "%~dp0"
if exist tmp\test_root rmdir /s /q tmp\test_root
if exist shared\secrets\denylist.txt set XBOTGO_DENYLIST=%CD%\shared\secrets\denylist.txt
python tools\editor\make_test_root.py --dst tmp\test_root || goto :fail
pushd tmp\test_root
python -m unittest tools.editor.test_roundtrip
set RC=%errorlevel%
popd
echo.
if not "%RC%"=="0" (echo *** TESTS FAILED ***) else (echo All tests passed.)
goto :end
:fail
echo *** could not build the test project ***
set RC=1
:end
popd
if not "%1"=="--no-pause" (
    echo %cmdcmdline% | findstr /i /c:"cmd /c" >nul && pause
)
exit /b %RC%
