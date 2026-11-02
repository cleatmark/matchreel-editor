#!/usr/bin/env bash
# Runs the full editor test suite on a fresh synthetic project.
set -e
cd "$(dirname "$0")"
[ -f shared/secrets/denylist.txt ] && export XBOTGO_DENYLIST="$PWD/shared/secrets/denylist.txt"
rm -rf tmp/test_root
python3 tools/editor/make_test_root.py --dst tmp/test_root
cd tmp/test_root && python3 -m unittest tools.editor.test_roundtrip
