"""Shared child-process helper: stream output line by line so cmd windows and log modals show live progress."""
import os, subprocess


def run_streaming(cmd, timeout=None):
    """Run cmd, echo its output line by line while it works (so the Re-cut window shows clip-by-clip progress),
    and return an object with returncode / stdout / stderr like subprocess.run."""
    import threading
    cmd = [str(c) for c in cmd]
    if cmd and os.path.basename(cmd[0]).lower().startswith("python") and "-u" not in cmd[1:2]:
        cmd.insert(1, "-u")          # unbuffered child output
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
                         encoding="utf-8", errors="replace")
    timed_out = []
    timer = None
    if timeout:
        timer = threading.Timer(timeout, lambda: (timed_out.append(1), p.kill()))
        timer.start()
    lines = []
    try:
        for line in p.stdout:
            lines.append(line)
            print("  " + line.rstrip(), flush=True)
        p.wait()
    finally:
        if timer:
            timer.cancel()
    if timed_out:
        raise subprocess.TimeoutExpired(cmd, timeout)
    return subprocess.CompletedProcess(cmd, p.returncode, "".join(lines), "")
