#!/usr/bin/env python3
"""Build the PUBLIC export of the editor project from an allowlist, verify it, and optionally create the git repo.

  python tools/pipeline/export_public.py [--dst tmp/public_export/xbotgo-editor] [--test] [--init-git --git-name NAME --git-email NOREPLY]
  python tools/pipeline/export_public.py --approve-images        # after a person has looked at every guide screenshot

Only files named here are copied (nothing else in the working folder can leak). Then it
  * scrubs the docs with the PRIVATE map shared/secrets/doc_scrub_map.json and generates LICENSE, .gitignore, docs/TEST_FIXTURES.md, placeholder crests,
  * gates: allowed file types only, size cap, PNGs must be generated placeholders or have a reviewed hash (shared/secrets/export_approved_images.json),
  * scans every file and name with the PRIVATE deny-list shared/secrets/denylist.txt plus generic gates (emails, long IDs, personal paths),
  * with --test builds the synthetic test project from the export and runs the suite there.
Exit code 0 only if every gate passes. The private files are never copied. Re-running keeps an existing .git in the destination."""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, HERE)
from xbotgo_core import identifier_scan as S  # noqa: E402
import guide_export  # noqa: E402

TREES = ["tools/editor", "tools/pipeline", "tools/xbotgo_core"]
FILES = ["README.md", "requirements.txt", "review_editor.bat", "review_editor.sh", "review_editor_5001.bat", "restart_editor.bat",
         "run_tests.bat", "run_tests.sh", "capture_guide_screenshots.bat", "config/game_defaults.example.json"]
DOCS = {"app_design/ARCHITECTURE_review_editor.md": "docs/ARCHITECTURE.md", "app_design/API_REFERENCE.md": "docs/API_REFERENCE.md"}
SKIP_DIRS = {"__pycache__", "archive", ".pytest_cache"}
SKIP_EXT = {".pyc"}
ALLOWED_EXT = {".py", ".js", ".css", ".html", ".md", ".txt", ".bat", ".sh", ".json", ".png", ".csv"}
ALLOWED_NAMES = {".gitignore", ".gitattributes", ".nojekyll", "LICENSE"}
GENERATED_PNG_DIRS = ("shared/team_logos/", "tools/editor/fixtures/project/shared/team_logos/")
GUIDE_IMG_DIRS = ("tools/editor/static/guide/images/", "docs/guide/images/")
CSV_DIR = "tools/editor/fixtures/"
MAX_BYTES = 3_000_000
APPROVED = os.path.join(ROOT, "shared", "secrets", "export_approved_images.json")
DENYLIST = os.path.join(ROOT, "shared", "secrets", "denylist.txt")
SCRUBMAP = os.path.join(ROOT, "shared", "secrets", "doc_scrub_map.json")
DENYLIST_DATES = os.path.join(ROOT, "shared", "secrets", "denylist_dates.txt")   # real dates/epochs: only the EXPORT is checked against it
TRANSFORM = os.path.join(ROOT, "shared", "secrets", "public_transform.py")       # private: rewrites the export copy (dates, scores, jerseys)
PUBLIC_IMG = os.path.join(ROOT, "shared", "secrets", "public_guide_images")        # private: reviewed screenshots of the SYNTHETIC game, used instead of the working project's
DENYLISTS = os.pathsep.join(p for p in (DENYLIST, DENYLIST_DATES) if os.path.exists(p))
GENERIC_SCRUB = [(r"[A-Za-z]:\\(?:temp\\XbotGo|backup\\xbotgo)\\?", "<project>\\\\"),
                 (r"file:///[A-Za-z]:/[^)\s]*?/([A-Za-z_]+\.md)", r"\1")]   # local file links -> relative

LICENSE = """MIT License

Copyright (c) 2026 {holder}

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"),
to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense,
and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
IN THE SOFTWARE.
"""
GITATTRIBUTES = "* text=auto\n*.csv -text\n*.sh text eol=lf\n*.png binary\n"
GITIGNORE = """# user data and private values: never commit
/config/game_defaults.json
/out/
/tmp/
/shared/secrets/
/shared/Music/
/utils/
[0-9][0-9]-[0-9][0-9]-[0-9][0-9]/
*.mp4
*.mov
*.zip
*.pem
*.key
*.log
__pycache__/
*.pyc
"""


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def approve_images():
    d = PUBLIC_IMG if os.path.isdir(PUBLIC_IMG) else os.path.join(ROOT, *GUIDE_IMG_DIRS[0].rstrip("/").split("/"))
    ok = {sha256(os.path.join(d, f)): f for f in sorted(os.listdir(d)) if f.lower().endswith(".png")}
    with open(APPROVED, "w", encoding="utf-8") as f:
        json.dump(ok, f, indent=1)
    print(f"approved {len(ok)} guide image(s) -> {APPROVED}")


def copy_tree(src, dst):
    for dp, dn, fn in os.walk(src):
        dn[:] = [d for d in dn if d not in SKIP_DIRS]
        for f in fn:
            if os.path.splitext(f)[1].lower() in SKIP_EXT:
                continue
            s = os.path.join(dp, f)
            d = os.path.join(dst, os.path.relpath(s, ROOT))
            os.makedirs(os.path.dirname(d), exist_ok=True)
            shutil.copy2(s, d)


def scrub_docs(dst):
    pairs = [(re.compile(a), b) for a, b in GENERIC_SCRUB]
    if os.path.exists(SCRUBMAP):
        pairs += [(re.compile(a), b) for a, b in json.load(open(SCRUBMAP, encoding="utf-8"))]
    for src_rel, dst_rel in DOCS.items():
        t = open(os.path.join(ROOT, *src_rel.split("/")), encoding="utf-8").read()
        for rx, rep in pairs:
            t = rx.sub(rep, t)
        out = os.path.join(dst, *dst_rel.split("/"))
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w", encoding="utf-8", newline="\n") as f:
            f.write(t)


def gen_test_fixtures_doc(dst):
    sys.path.insert(0, os.path.join(ROOT, "tools", "editor"))
    import test_data_manifest as M
    lines = ["# Test fixtures", "", "The unit tests run on a fully synthetic project (fake teams `Home FC` / `Guest FC`, players `Player N`, generated crests, no video).",
             "`python tools/editor/make_test_root.py` copies `tools/` plus `tools/editor/fixtures/project/` into a fresh folder; `run_tests.bat` / `run_tests.sh` do that and run the suite.", "",
             "| file (relative to the test project) | why the tests need it |", "|---|---|"]
    lines += [f"| `{rel}` | {why} |" for rel, why in M.REQUIRED_FILES]
    with open(os.path.join(dst, "docs", "TEST_FIXTURES.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")


def gates(dst):
    problems = []
    approved = json.load(open(APPROVED, encoding="utf-8")) if os.path.exists(APPROVED) else {}
    for dp, dn, fn in os.walk(dst):
        dn[:] = [d for d in dn if d != ".git"]
        for f in fn:
            p = os.path.join(dp, f)
            rel = os.path.relpath(p, dst).replace("\\", "/")
            ext = os.path.splitext(f)[1].lower()
            if f not in ALLOWED_NAMES and ext not in ALLOWED_EXT:
                problems.append((rel, "file type not allowed"))
            if os.path.getsize(p) > MAX_BYTES:
                problems.append((rel, "file larger than size cap"))
            if ext == ".csv" and not rel.startswith(CSV_DIR):
                problems.append((rel, "csv outside fixtures"))
            if ext == ".png" and not rel.startswith(GENERATED_PNG_DIRS):
                if not (rel.startswith(GUIDE_IMG_DIRS) and sha256(p) in approved):
                    problems.append((rel, "image not reviewed (run --approve-images after looking at it)"))
    return problems


def run_tests(dst):
    tr = os.path.join(tempfile.mkdtemp(prefix="xbotgo_export_test_"), "tr")
    subprocess.check_call([sys.executable, os.path.join(dst, "tools", "editor", "make_test_root.py"), "--dst", tr])
    env = dict(os.environ)
    if DENYLISTS:
        env["XBOTGO_DENYLIST"] = DENYLISTS
    return subprocess.call([sys.executable, "-m", "unittest", "tools.editor.test_roundtrip"], cwd=tr, env=env)


def init_git(dst, name, email):
    if not email.endswith("@users.noreply.github.com"):
        sys.exit("refusing: --git-email must be your GitHub noreply address (…@users.noreply.github.com)")
    if not os.path.isdir(os.path.join(dst, ".git")):
        subprocess.check_call(["git", "init", "-b", "main"], cwd=dst)
    subprocess.check_call(["git", "config", "user.name", name], cwd=dst)
    subprocess.check_call(["git", "config", "user.email", email], cwd=dst)
    hook = os.path.join(dst, ".git", "hooks", "pre-commit")
    with open(hook, "w", newline="\n") as f:
        f.write('#!/bin/sh\n# blocks commits that contain private identifiers; always uses the private deny-lists named below\n'
                'XBOTGO_DENYLIST=\'' + DENYLISTS.replace("\\", "/") + '\'; export XBOTGO_DENYLIST\n'
                '[ -n "$XBOTGO_DENYLIST" ] || { echo "no private deny-list found: refusing to commit"; exit 1; }\n'
                'PY=$(command -v python3 || command -v python || command -v py)\n'
                '[ -n "$PY" ] || { echo "python not found: cannot scan"; exit 1; }\n'
                '"$PY" tools/xbotgo_core/identifier_scan.py . || exit 1\n')
    os.chmod(hook, 0o755)
    print("git ready (noreply author, pre-commit scan). Review `git status`, then commit and push to a PRIVATE repo first.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dst", default=os.path.join(ROOT, "tmp", "public_export", "xbotgo-editor"))
    ap.add_argument("--test", action="store_true", help="also run the unit tests from the export")
    ap.add_argument("--approve-images", action="store_true")
    ap.add_argument("--copyright-holder", default="XbotGo Review Editor contributors", help="name in the LICENSE (use your GitHub username)")
    ap.add_argument("--init-git", action="store_true")
    ap.add_argument("--git-name")
    ap.add_argument("--git-email")
    a = ap.parse_args()
    if a.approve_images:
        return approve_images()
    dst = os.path.abspath(a.dst)
    if dst == ROOT or dst.startswith(ROOT + os.sep + "tools"):
        sys.exit("bad --dst")
    os.makedirs(dst, exist_ok=True)
    for e in os.listdir(dst):                       # rebuild from scratch but keep .git
        if e == ".git":
            continue
        p = os.path.join(dst, e)
        shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)
    for t in TREES:
        copy_tree(os.path.join(ROOT, *t.split("/")), dst)
    for f in FILES:
        s = os.path.join(ROOT, *f.split("/"))
        d = os.path.join(dst, *f.split("/"))
        os.makedirs(os.path.dirname(d), exist_ok=True)
        shutil.copy2(s, d)
    scrub_docs(dst)
    gen_test_fixtures_doc(dst)
    guide_export.write_guide_docs(ROOT, dst)
    if os.path.exists(TRANSFORM):                   # private: synthesize dates, scores and jersey numbers in the COPY only
        import importlib.util
        spec = importlib.util.spec_from_file_location("public_transform", TRANSFORM)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.transform(dst, ROOT)
    else:
        print("  NOTE: shared/secrets/public_transform.py not found - real dates/scores would stay in the fixtures")
    if os.path.isdir(PUBLIC_IMG):                   # screenshots of the synthetic game replace the working project's
        for sub in GUIDE_IMG_DIRS:
            target = os.path.join(dst, *sub.rstrip("/").split("/"))
            if os.path.isdir(target):
                for f in os.listdir(PUBLIC_IMG):
                    if f.lower().endswith(".png"):
                        shutil.copy2(os.path.join(PUBLIC_IMG, f), os.path.join(target, f))
    open(os.path.join(dst, "LICENSE"), "w", encoding="utf-8", newline="\n").write(LICENSE.replace("{holder}", a.copyright_holder))
    open(os.path.join(dst, ".gitignore"), "w", encoding="utf-8", newline="\n").write(GITIGNORE)
    open(os.path.join(dst, ".gitattributes"), "w", encoding="utf-8", newline="\n").write(GITATTRIBUTES)
    subprocess.check_call([sys.executable, os.path.join(HERE, "make_placeholder_logos.py"), "--out", os.path.join(dst, "shared", "team_logos")], stdout=subprocess.DEVNULL)
    bad = gates(dst)
    findings = S.scan_tree(dst, DENYLISTS or None)
    n_files = sum(len(f) for _, _, f in os.walk(dst) if ".git" not in _)
    print(f"export: {dst}\n  files: {n_files}   gate problems: {len(bad)}   identifier findings: {len(findings)}"
          + ("" if os.path.exists(DENYLIST) else "   [NO DENY-LIST FOUND: only generic gates ran - do not publish]"))
    for rel, why in bad:
        print(f"  GATE {rel}: {why}")
    for rel, n, kind, m in findings[:40]:
        print(f"  FOUND {rel}:{n} {kind} {m}")
    ok = not bad and not findings and os.path.exists(DENYLIST)
    if ok and a.test:
        rc = run_tests(dst)
        ok = ok and rc == 0
        print("  tests:", "OK" if rc == 0 else "FAILED")
    if ok and a.init_git:
        if not (a.git_name and a.git_email):
            sys.exit("--init-git needs --git-name and --git-email")
        init_git(dst, a.git_name, a.git_email)
    print("RESULT:", "PASS - safe to review and push (private first)" if ok else "FAIL - do not publish")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
