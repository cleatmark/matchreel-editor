#!/usr/bin/env python3
"""Build a self-contained, fully synthetic project the unit tests run in (no real data, no videos, no Google key).

  python tools/editor/make_test_root.py [--dst tmp/test_root]
  cd <dst> && python -m unittest tools.editor.test_roundtrip

Copies tools/ (without __pycache__) and the synthetic fixture project tools/editor/fixtures/project/ (teams "Home FC"/"Guest FC",
players "Player N", generated placeholder crests), and makes app_design/USER_GUIDE.html from the editor's guide page.
See app_design/TEST_FIXTURES.md."""
import argparse
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_data_manifest as M

ROOT = os.path.dirname(os.path.dirname(HERE))
FIXTURES = os.path.join(HERE, "fixtures", "project")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dst", default=os.path.join(ROOT, "tmp", "test_root"))
    a = ap.parse_args()
    dst = os.path.abspath(a.dst)
    if dst == ROOT:
        sys.exit("dst must not be the project itself")
    if os.path.exists(dst):
        sys.exit(f"{dst} exists already - remove it first (nothing is overwritten)")
    shutil.copytree(os.path.join(ROOT, "tools"), os.path.join(dst, "tools"), ignore=shutil.ignore_patterns("__pycache__", "archive", "*.pyc"))
    shutil.copytree(FIXTURES, dst, dirs_exist_ok=True)
    os.makedirs(os.path.join(dst, "app_design"), exist_ok=True)
    shutil.copy2(os.path.join(ROOT, "tools", "editor", "static", "guide.html"), os.path.join(dst, "app_design", "USER_GUIDE.html"))
    missing = [rel for rel, _ in M.REQUIRED_FILES if not M.resolve(dst, rel)]
    print(f"test root: {dst}  ({len(M.REQUIRED_FILES) - len(missing)} data files present)")
    if missing:
        print("MISSING (tests that need them will be skipped):\n  " + "\n  ".join(missing))
    print(f'run:  cd "{dst}" && python -m unittest tools.editor.test_roundtrip')
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
