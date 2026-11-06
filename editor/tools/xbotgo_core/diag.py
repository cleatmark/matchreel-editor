"""Tiny diagnostics helper: report an error that is deliberately not fatal, instead of hiding it with `pass`.

Use inside an `except` block:   except Exception:  swallowed()
Prints one line to the editor/console window (stderr): what was ignored and where.
"""
import os
import sys


def swallowed(note: str = "") -> None:
    exc = sys.exc_info()[1]
    try:
        f = sys._getframe(1)
        where = f"{f.f_code.co_name}, {os.path.basename(f.f_code.co_filename)}:{f.f_lineno}"
    except Exception:
        where = "?"
    print(f"[note] ignored {type(exc).__name__ if exc else 'error'}: {exc} (in {where}){' - ' + note if note else ''}",
          file=sys.stderr, flush=True)
