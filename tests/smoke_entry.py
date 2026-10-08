"""Start the program the way a user does and see that its window comes up and closes cleanly.

    python smoke_entry.py <label> <command ...>      e.g.  smoke_entry.py module  <python> -B -m tcspc_analysis <phu>

The command is run as given (from the project folder); the script waits for a new top-level window with
the program's title, asks it to close (WM_CLOSE, what the X button sends), waits for the process to end
and reports: the title, the exit code, whether a freeze log was written (it is removed again) and
whether a __pycache__ folder appeared in the project.
"""
import ctypes
import os
import subprocess
import sys
import tempfile
import time
from ctypes import wintypes

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TITLE = "PicoHarp 300 post-processing - PHU/TRES + PTU/FLIM"
LOG = os.path.join(ROOT, "TCSPC_analysis_freeze.log")
user32 = ctypes.windll.user32
WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def windows():
    found = []

    def each(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            buf = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd, buf, 256)
            if buf.value.startswith(TITLE):       # the version follows it since 1.6
                found.append(hwnd)
        return True
    user32.EnumWindows(WNDENUMPROC(each), 0)
    return found


def caches():
    """__pycache__ folders of the program: beside it and inside the package."""
    out = [os.path.relpath(d, ROOT) for d, _, _ in os.walk(os.path.join(ROOT, "tcspc_analysis"))
           if os.path.basename(d) == "__pycache__"]
    if os.path.isdir(os.path.join(ROOT, "__pycache__")):
        out.append("__pycache__")
    return sorted(out)


label, cmd = sys.argv[1], sys.argv[2:]
before_win, before_cache = set(windows()), caches()
had_log = os.path.exists(LOG)
t0 = time.time()
# Output goes to a file: a pipe nobody reads fills up and pip then waits (a launcher's first run
# stood still for the whole SMOKE_WAIT that way).
sink = tempfile.TemporaryFile()
proc = subprocess.Popen(cmd, cwd=ROOT, stdout=sink, stderr=subprocess.STDOUT)
hwnd = None
while time.time() - t0 < float(os.environ.get("SMOKE_WAIT", 90)) and proc.poll() is None and hwnd is None:
    new = [h for h in windows() if h not in before_win]
    hwnd = new[0] if new else None
    time.sleep(0.2)
shown = time.time() - t0
if hwnd:
    time.sleep(2.0)                              # let the first draw finish
    user32.PostMessageW(hwnd, 0x0010, 0, 0)      # WM_CLOSE
killed = ""
try:
    proc.wait(timeout=60)
except subprocess.TimeoutExpired:
    # the whole tree: killing a launcher alone leaves the program it started
    subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
    proc.wait()
    killed = "(killed: did not close)\n"
sink.seek(0)
out = killed + sink.read().decode("utf-8", "replace")
log_text = ""
if os.path.exists(LOG) and not had_log:
    log_text = open(LOG, encoding="utf-8", errors="replace").read()
    os.remove(LOG)
new_cache = [c for c in caches() if c not in before_cache]
ok = bool(hwnd) and proc.returncode == 0 and not new_cache and not os.path.exists(LOG) \
    and "Traceback" not in out and "error in a callback" not in log_text and "not answering" not in log_text
print(f"{'PASS' if ok else 'FAIL'} {label}: window={'yes' if hwnd else 'NO'} after {shown:.1f} s, "
      f"exit={proc.returncode}, new __pycache__={new_cache}, log written={bool(log_text)} (removed), "
      f"log first line={log_text.splitlines()[0][:90] if log_text else ''!r}")
if out.strip():
    print("  output:", out.strip()[:int(os.environ.get("SMOKE_OUTPUT", 600))])
sys.exit(0 if ok else 1)
