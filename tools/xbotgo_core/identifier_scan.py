"""Identifier scanner: finds private values (names, teams, emails, IDs, personal paths) in a file tree.

Used by tools/pipeline/export_public.py (publish gate) and by the guard test in tools/editor/test_roundtrip.py.

Deny-list file (private, never committed; default shared/secrets/denylist.txt), one term per line:
    plain text      substring match, case-insensitive
    w:TERM          whole-word match, case-sensitive (short names such as team abbreviations)
    # comment
Matches are reported as file:line with the term MASKED (first letter + ***), so logs never reveal it.
"""
import os
import re

TEXT_EXT = {".py", ".js", ".css", ".html", ".md", ".txt", ".bat", ".sh", ".json", ".csv", ".cfg", ".toml", ".yml", ".yaml", ".ini", ".gitignore", ".example"}
# generic regex gates (apply to every text file)
REGEX_GATES = {
    "email": re.compile(r"[\w.+-]+@[\w-]+(?:\.[A-Za-z][\w-]*)+"),
    "long-id": re.compile(r"\b(?=[A-Za-z0-9_-]*\d)(?=[A-Za-z0-9_-]*[a-z])(?=[A-Za-z0-9_-]*[A-Z])[A-Za-z0-9_-]{40,}\b"),
    "private-key": re.compile(r"BEGIN (?:RSA |EC )?PRIVATE KEY"),
    "personal-path": re.compile(r"[A-Za-z]:\\(?:Users|temp|backup)[^\s\"']*", re.I),
    "drive-path": re.compile(r"\b[A-Za-z]:\\[A-Za-z]"),
}
EMAIL_OK = re.compile(r"@(?:example\.(?:com|org|invalid)|users\.noreply\.github\.com)$|^(?:user|parent\d*|contact|name|mail)@(?:email|example)\.", re.I)


def load_denylist(path):
    """`path` may name several files separated by os.pathsep (';' on Windows, ':' elsewhere)."""
    subs, words = [], []
    for one in (path or "").split(os.pathsep):
        if not one or not os.path.exists(one):
            continue
        with open(one, encoding="utf-8") as fh:
            for raw in fh:
                t = raw.strip()
                if not t or t.startswith("#"):
                    continue
                if t.startswith("w:"):
                    if t[2:]:
                        words.append(t[2:])
                elif t.startswith("re:"):
                    if t[3:]:
                        subs.append(re.compile(t[3:]))      # private regex entry
                else:
                    subs.append(t.lower())
    return subs, words


def _mask(t):
    return (t[:1] + "***") if t else "***"


def scan_text(text, subs, words, gates=True):
    """Yield (line_no, kind, masked) for every finding in a text blob."""
    word_rx = [(w, re.compile(r"(?<![A-Za-z0-9])" + re.escape(w) + r"(?![A-Za-z0-9])")) for w in words]
    for n, line in enumerate(text.splitlines(), 1):
        low = line.lower()
        for t in subs:
            if isinstance(t, re.Pattern):
                if t.search(line):
                    yield n, "deny-re", "<pattern>"
            elif t in low:
                yield n, "deny", _mask(t)
        for w, rx in word_rx:
            if rx.search(line):
                yield n, "deny-word", _mask(w)
        if gates:
            for kind, rx in REGEX_GATES.items():
                for m in rx.finditer(line):
                    if kind == "email" and EMAIL_OK.search(m.group(0)):
                        continue
                    yield n, "gate:" + kind, "<" + kind + ">"


def scan_tree(root, denylist_path, include_gates=True, skip_dirs=("__pycache__", ".git", "node_modules")):
    """Scan every file under root (contents of text files + all file/folder names). Returns list of (relpath, line, kind, masked)."""
    subs, words = load_denylist(denylist_path)
    findings = []
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if d not in skip_dirs]
        for name in list(dn) + list(fn):
            rel = os.path.relpath(os.path.join(dp, name), root).replace("\\", "/")
            for n, kind, m in scan_text(name, subs, words, gates=False):
                findings.append((rel, 0, "name-" + kind, m))
        for f in fn:
            p = os.path.join(dp, f)
            rel = os.path.relpath(p, root).replace("\\", "/")
            ext = os.path.splitext(f)[1].lower()
            if ext not in TEXT_EXT and f not in (".gitignore", "LICENSE"):
                continue
            try:
                text = open(p, encoding="utf-8", errors="replace").read()
            except OSError:
                continue
            for n, kind, m in scan_text(text, subs, words, gates=include_gates):
                findings.append((rel, n, kind, m))
    return findings


def main(argv=None):
    import argparse
    import sys
    ap = argparse.ArgumentParser(description="Scan a folder for private identifiers (deny-list) and generic leaks (emails, IDs, personal paths).")
    ap.add_argument("root")
    ap.add_argument("--denylist", default=os.environ.get("XBOTGO_DENYLIST"))
    a = ap.parse_args(argv)
    have = any(x and os.path.exists(x) for x in (a.denylist or "").split(os.pathsep))
    findings = scan_tree(a.root, a.denylist if have else None)
    for rel, n, kind, m in findings:
        print(f"{rel}:{n}: {kind} {m}")
    print(f"{len(findings)} finding(s)" + ("" if have else "  [no deny-list: generic gates only]"))
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
