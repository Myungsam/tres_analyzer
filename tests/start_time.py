"""Time from starting an .exe to its window being there, polled every 50 ms.

    python start_time.py <label> <exe> [n=4] [file.phu]

Run 1 is reported apart ("first run"); the median of the others is "later runs". Each run is closed
with WM_CLOSE. The freeze log the program leaves - beside the .exe up to 1.4.2, in Documents/TCSPC_analysis
since 1.6 - is removed again, and so is that folder, when neither was there before the runs.
"""
import ctypes
import os
import statistics
import subprocess
import sys
import time
from ctypes import wintypes

TITLE = "PicoHarp 300 post-processing - PHU/TRES + PTU/FLIM"
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


label, exe = sys.argv[1], sys.argv[2]
n = int(sys.argv[3]) if len(sys.argv) > 3 else 4
extra = sys.argv[4:5]
log = os.path.join(os.path.dirname(exe), "TCSPC_analysis_freeze.log")
buf = ctypes.create_unicode_buffer(260)
ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf)      # 5 = My Documents, wherever it is
user_dir = os.path.join(buf.value, "TCSPC_analysis")
user_log = os.path.join(user_dir, "TCSPC_analysis_freeze.log")
had_dir, had_log = os.path.isdir(user_dir), os.path.exists(user_log)
times = []
for i in range(n):
    before = set(windows())
    t0 = time.perf_counter()
    proc = subprocess.Popen([exe] + extra, cwd=os.path.dirname(exe))
    hwnd = None
    while time.perf_counter() - t0 < 120 and proc.poll() is None:
        new = [h for h in windows() if h not in before]
        if new:
            hwnd = new[0]
            break
        time.sleep(0.05)
    times.append(time.perf_counter() - t0 if hwnd else float("nan"))
    time.sleep(1.5)
    if hwnd:
        user32.PostMessageW(hwnd, 0x0010, 0, 0)
    try:
        proc.wait(timeout=60)
    except subprocess.TimeoutExpired:
        proc.kill()
    if os.path.exists(log):
        os.remove(log)
    time.sleep(1.0)
if os.path.exists(user_log) and not had_log:
    os.remove(user_log)
    if not had_dir and not os.listdir(user_dir):
        os.rmdir(user_dir)
later = times[1:]
print(f"{label}: first run {times[0]:.2f} s; later runs {' '.join(f'{t:.2f}' for t in later)} s"
      + (f" (median {statistics.median(later):.2f} s)" if later else ""))
