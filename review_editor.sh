#!/usr/bin/env bash
# Linux/macOS/Docker launcher (Windows: review_editor.bat). Set XBOTGO_ROOT to the data folder if it is not this one.
# Restart by flag: creating tmp/restart_editor.flag makes the server exit with code 75 and this loop starts it again.
HERE="$(cd "$(dirname "$0")" && pwd)"
export XBOTGO_RESTART_LOOP=1
while true; do
  python3 "$HERE/tools/editor/server.py"
  [ $? -eq 75 ] || break
done
