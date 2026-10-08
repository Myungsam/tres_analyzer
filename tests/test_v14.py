"""1.4: the freeze log, the kinetics fit on a worker thread, a new file closes the analysis windows."""
import ctypes
import ctypes.wintypes as wt
import faulthandler
import io
import os
import sys
import tempfile
import threading
import time
import traceback

import numpy as np

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _versions                              # noqa: E402
import tkinter as tk                          # noqa: E402
from tkinter import ttk                       # noqa: E402

NEW = _versions.load(path=os.environ["V14_MODULE"]) if os.environ.get("V14_MODULE") \
    else _versions.load()
OLD = _versions.load("1.3")
# These checks compare with an older version: the rules 1.6 changed on purpose are put back
# (see _versions.rules_of_1_5; the changes themselves are tested in test_g7.py / test_g8.py).
_versions.rules_of_1_5(NEW)
ROOT = _versions.ROOT
SAMPLE_A = _versions.samples()[0]
SAMPLE_B = _versions.samples()[1]
TMP = tempfile.mkdtemp(prefix="tcspc_v14_")
fails, cb_errors, boxes = [], [], []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail and not ok else ""))
    if not ok:
        fails.append(name)


for mod in (NEW, OLD):
    for kind in ("showerror", "showwarning", "showinfo"):
        setattr(mod.messagebox, kind,
                lambda title="", msg="", _k=kind, **kw: boxes.append((_k, title, str(msg))))

root = tk.Tk()
root.geometry("300x80+0+0")
NEW.apply_theme(root)


def on_cb_error(*a):
    cb_errors.append("".join(traceback.format_exception(*a)))


root.report_callback_exception = on_cb_error


def pump(seconds=0.0):
    end = time.time() + seconds
    root.update()
    while time.time() < end:
        root.update()
        time.sleep(0.01)


def wait(cond, limit=60.0):
    end = time.time() + limit
    while not cond() and time.time() < end:
        pump(0.05)
    return cond()


# =========================================================================================
# A. the freeze log
# =========================================================================================
LOG = os.path.join(TMP, "freeze.log")


class TestLog(NEW.FreezeLog):
    BEAT_MS = 100
    LIMIT_S = 2.0
    IDLE_S = 6.0
    mute = False

    @classmethod
    def _open(cls):
        return LOG, open(LOG, "a", encoding="utf-8", errors="replace", buffering=1)

    def _beat(self):
        if self.mute:               # stands in for a main loop that no longer runs callbacks
            return
        super()._beat()


def text():
    return open(LOG, encoding="utf-8").read()


def stalls():
    return text().count("window not answering")


check("log: the limits the program ships with: 5 s, 30 s idle, 60 s hard, a beat every 0.5 s",
      (NEW.FreezeLog.LIMIT_S, NEW.FreezeLog.IDLE_S, NEW.FreezeLog.HARD_S, NEW.FreezeLog.BEAT_MS)
      == (5.0, 30.0, 60, 500))
log = TestLog(root, lambda: "name_of_the_open_file.phu")
pump(0.5)
check("log: Python's fault handler is left as it was (no 'fatal exception' entries for caught errors)",
      not faulthandler.is_enabled())
check("log: opened with a start line that names the version",
      f"started, version {NEW.APP_VERSION}" in text() and NEW.APP_VERSION == "1.6", text()[:200])
check("log: installs itself as the Tk callback-error handler",
      root.report_callback_exception == log._callback_error)


def short_nap():
    time.sleep(1.0)


def stuck_in_here():
    time.sleep(4.5)


root.after(10, short_nap)
pump(2.5)
check("log: a 1 s stall (under the limit) is not reported", stalls() == 0, text())
t0 = time.time()
root.after(10, stuck_in_here)
pump(6.5)
body = text()
check("log: a 4.5 s stall is reported once", stalls() == 1, body)
check("log: ... with the function the window's thread is stuck in",
      "stuck_in_here" in body and "<-- the window's thread" in body
      and body.index("<-- the window's thread") < body.index("stuck_in_here"), body[-900:])
check("log: ... with the name of the open file and the watcher's own thread listed",
      "open: name_of_the_open_file.phu" in body and "_watch" in body)
tail = body[body.index("window not answering"):]
again = [ln for ln in tail.split("\n") if "answering again after" in ln]
secs = float(again[0].split("after")[1].split("s")[0]) if again else -1
check("log: ... and when it answers again, after how long", len(again) == 1 and 3.5 <= secs <= 6.0,
      str(again))
check("log: the home folder is not written (paths start at ~)",
      os.path.expanduser("~") not in body and "~" in body)
log.write("check " + os.path.join(os.path.expanduser("~"), "Data", "x.phu"))
check("log: write() itself strips the home folder", os.path.expanduser("~") not in text()
      and os.path.join("~", "Data", "x.phu") in text())

console, sys.stderr = sys.stderr, io.StringIO()
root.after(10, lambda: 1 / 0)
pump(0.4)
printed, sys.stderr = sys.stderr.getvalue(), console
body = text()
check("log: an exception in a Tk callback is written with its traceback",
      "error in a callback" in body and "ZeroDivisionError" in body and "Traceback" in body)
check("log: ... and still printed on the console, as Tk does on its own",
      "Exception in Tkinter callback" in printed and "ZeroDivisionError" in printed, printed[-300:])
sys.stderr = None                       # a windowed exe has no console at all
root.after(10, lambda: [][1])
pump(0.4)
sys.stderr = console
check("log: with no console the error is logged all the same", "IndexError" in text())

# the home folder must not get in through an error message, however the path is spelt
home = os.path.expanduser("~")
user = os.path.basename(home)
spellings = [PermissionError(13, "Permission denied", os.path.join(home, "Data", "a.csv")),
             FileNotFoundError(2, "No such file", home.replace("\\", "/") + "/Data/b.phu"),
             RuntimeError("could not read " + home.replace("\\", "/") + "/Data/c.phu"),
             RuntimeError("could not read " + home.lower() + "\\Data\\d.phu")]
sys.stderr = io.StringIO()
for exc in spellings:
    root.after(10, lambda e=exc: (_ for _ in ()).throw(e))
    pump(0.3)
sys.stderr = console
body = text()
check("log: a path in an error message loses the home folder in every spelling "
      "(repr-doubled backslashes, forward slashes, lower case)",
      all(n in body for n in ("a.csv", "b.phu", "c.phu", "d.phu"))
      and user.lower() not in body.lower(), [ln for ln in body.split("\n") if user.lower() in ln.lower()][:3])
root.report_callback_exception = on_cb_error       # the tests' own handler from here on
log._callback_error = on_cb_error

# no callback running: Tk waits in its own loop (a window held by its title bar)
n0 = stalls()
log.mute = True
root.after(4000, root.quit)
root.mainloop()
check("log: 4 s with no callback running (Tk's own loop) is not reported yet", stalls() == n0, text()[-600:])
root.after(8000, root.quit)
root.mainloop()
body = text()
check("log: ... but is after the longer limit, marked as such",
      stalls() == n0 + 1 and "no callback running" in body.split("window not answering")[-1],
      body[-800:])
log.mute = False
log._beat()
pump(0.5)
check("log: ... and it notes the main loop coming back",
      "answering again after" in text().split("no callback running")[-1])

# a native file dialog keeps the main loop running: no report however long it stays open
u32 = ctypes.windll.user32
u32.FindWindowW.restype = wt.HWND
found = []


def close_dialog(title, seconds):
    def run():
        time.sleep(seconds)
        h = u32.FindWindowW("#32770", title)
        found.append(bool(h))
        if h:
            u32.PostMessageW(h, 0x0010, 0, 0)       # WM_CLOSE
    threading.Thread(target=run, daemon=True).start()


n0 = stalls()
close_dialog("v14 dialog test", 6.0)
t0 = time.time()
NEW.filedialog.askopenfilename(title="v14 dialog test", parent=root)
held = time.time() - t0
pump(1.5)
check("log: a file dialog left open for 6 s (3x the limit) is not reported",
      found == [True] and held > 5.5 and stalls() == n0, f"found={found} held={held:.1f}")
log.close()
size = os.path.getsize(LOG)
pump(0.5)
check("log: close() ends it (file closed, nothing more written)",
      log._fh.closed and os.path.getsize(LOG) == size)

# the faulthandler backstop: fires without the watcher (here: watcher limit out of reach)
LOG2 = os.path.join(TMP, "freeze_hard.log")


class HardLog(NEW.FreezeLog):
    BEAT_MS = 100
    LIMIT_S = 1000.0
    IDLE_S = 1000.0
    HARD_S = 2

    @classmethod
    def _open(cls):
        return LOG2, open(LOG2, "a", encoding="utf-8", errors="replace", buffering=1)


hard = HardLog(root)
pump(3.5)
check("log: a main loop that keeps running re-arms the hard limit (no dump after 3.5 s with HARD_S 2)",
      "Timeout" not in open(LOG2, encoding="utf-8").read())


def stuck_hard():
    time.sleep(3.5)


root.after(10, stuck_hard)
pump(5.0)
hard.close()
root.report_callback_exception = on_cb_error
body2 = open(LOG2, encoding="utf-8").read()
check("log: faulthandler writes its own dump when the loop stays silent for HARD_S",
      "Timeout (0:00:02)!" in body2 and "stuck_hard" in body2, body2[-500:])
pump(2.5)
check("log: ... and no further dump after close()",
      open(LOG2, encoding="utf-8").read().count("Timeout") == body2.count("Timeout"))

# where the real log goes: beside the program
path, fh = NEW.FreezeLog._open()
fh.close()
check("log: the real log is TCSPC_analysis_freeze.log beside the program",
      os.path.normcase(path) == os.path.normcase(os.path.join(ROOT, "TCSPC_analysis_freeze.log")), path)
if os.path.exists(path) and os.path.getsize(path) == 0:
    os.remove(path)
real_makedirs = os.makedirs
blocked = os.path.normcase(ROOT)
NEW.os.makedirs = lambda p, **k: (_ for _ in ()).throw(PermissionError(p)) \
    if os.path.normcase(p) == blocked else real_makedirs(p, **k)
try:
    path2, fh2 = NEW.FreezeLog._open()
finally:
    NEW.os.makedirs = real_makedirs
fh2.close()
check("log: falls back to LOCALAPPDATA\\TCSPC_analysis when it cannot write beside the program",
      os.path.normcase(os.path.dirname(path2))
      == os.path.normcase(os.path.join(os.environ["LOCALAPPDATA"], "TCSPC_analysis")), path2)
if os.path.getsize(path2) == 0:
    os.remove(path2)
# a log that has grown past MAX_BYTES starts over; a smaller one is kept
real_dir = NEW.program_dir
NEW.program_dir = lambda: TMP
grown = os.path.join(TMP, NEW.FreezeLog.NAME)
try:
    open(grown, "w").write("old entry\n")
    p3, f3 = NEW.FreezeLog._open()
    f3.close()
    kept = open(grown).read()
    open(grown, "w").write("x" * (NEW.FreezeLog.MAX_BYTES + 1))
    p4, f4 = NEW.FreezeLog._open()
    f4.close()
finally:
    NEW.program_dir = real_dir
# D-17 (1.6): a log past MAX_BYTES is cut down to its newest entries instead of being emptied (this
# one has no entry to keep: what is left is the line saying that older entries were dropped)
check("log: an existing log is appended to, one past MAX_BYTES is cut down",
      os.path.normcase(p3) == os.path.normcase(grown) == os.path.normcase(p4)
      and kept == "old entry\n" and 0 <os.path.getsize(grown) < 200
      and open(grown).read().startswith("==== (older entries dropped"), f"{kept!r} {os.path.getsize(grown)}")
check("(A) no stray callback exceptions", not cb_errors, cb_errors[0][-400:] if cb_errors else "")
cb_errors.clear()

# =========================================================================================
# B. kinetics fit on a worker thread
# =========================================================================================


def build(mod, path=SAMPLE_A):
    top = tk.Toplevel(root)
    top.geometry("1440x900+0+0")
    tab = ttk.Frame(top)
    tab.pack(fill="both", expand=True)
    app = mod.TRESViewer(tab, path)
    pump(0.3)
    return top, app


top_o, app_o = build(OLD)
app_o.open_kinetics(); pump(0.2)
ko = app_o._kinetics_win
ko.var_n.set("2"); ko.table.set_n(2); ko.var_inf.set(True)
ko.run_fit(); pump(0.2)                       # 1.3: finished when run_fit returns
ref = ko._last
ko.var_inf.set(False); ko.var_n.set("1"); ko.table.set_n(1)
ko.run_fit(); pump(0.2)
ref_plain = ko._last
ko._on_close(); top_o.destroy(); pump(0.1)

top, app = build(NEW)
app.open_kinetics(); pump(0.2)
kd = app._kinetics_win
kd.var_n.set("2"); kd.table.set_n(2); kd.var_inf.set(True)
kd.run_fit()
started = (kd._running, str(kd.btn_run.cget("state")), kd.var_status.get(), kd._last)
wait(lambda: not kd._running)
pump(0.2)
res = kd._last
check("kinetics: run_fit returns at once with the fit running, the button off, 'Fitting...'",
      started == (True, "disabled", "Fitting...", None), str(started))
check("kinetics: result is the same as 1.3 (tau, beta, A, t0, fwhm, fit, residual, rms)",
      res is not None and ref is not None
      and all(np.allclose(res[k], ref[k], rtol=1e-12, atol=0) for k in
              ("tau", "beta", "A", "fit", "residual", "_t_fit", "_y_fit", "_t_full", "_y_full"))
      and res["t0"] == ref["t0"] and res["fwhm"] == ref["fwhm"]
      and res["info"]["rms"] == ref["info"]["rms"] and res["_wl"] == ref["_wl"]
      and res["_n_avg"] == ref["_n_avg"] and res["_has_inf"] is True)
check("kinetics: afterwards the button is back, the status and the report are filled in",
      str(kd.btn_run.cget("state")) == "normal" and kd.var_status.get().startswith("Fit done - RMS")
      and "Fit converged" in kd.txt.get("1.0", "end") and str(kd.win.cget("cursor")) == "")
check("kinetics: the fit curve is drawn", len(kd.ax_main.lines) >= 2)
kd._on_wl_change()
check("kinetics: a bare focus-out on the λ box afterwards keeps the fit", kd._last is res)
kd.var_inf.set(False); kd.var_n.set("1"); kd.table.set_n(1)
kd.var_t0_fix.set(True); kd.var_fw_fix.set(True)
kd.run_fit()
kd.var_t0_fix.set(False); kd.var_fw_fix.set(False)      # edited while it runs
wait(lambda: not kd._running)
pump(0.2)
plain = kd._last
check("kinetics: one component without the offset also equals 1.3",
      plain is not res and plain["_has_inf"] is False and ref_plain["_has_inf"] is False
      and len(plain["A"]) == 1 and all(np.allclose(plain[k], ref_plain[k], rtol=1e-12, atol=0)
                                       for k in ("tau", "A", "fit", "residual"))
      and plain["info"]["rms"] == ref_plain["info"]["rms"])
shown = kd.txt.get("1.0", "end")
check("kinetics: the report says 'fixed' as the fit was run, not as the boxes are now",
      shown.count("(fixed)") == 2 and "∞" not in shown, shown[-200:])
kd.var_t0_fix.set(True); kd.var_fw_fix.set(True)

# a slow fit: the main loop keeps running meanwhile
real_fit = NEW.fit_single_trace
calls = []


def slow_fit(*a, **k):
    calls.append(threading.current_thread() is threading.main_thread())
    time.sleep(2.0)
    return real_fit(*a, **k)


NEW.fit_single_trace = slow_fit
ticks = []


def tick():
    ticks.append(time.monotonic())
    root.after(50, tick)


tick()
t_start = time.monotonic()
kd.run_fit()
kd.run_fit()                                   # a second press while it runs
during = []
wait(lambda: (during.append((kd._running, str(kd.btn_run.cget("state")))) or not kd._running))
t_end = time.monotonic()
inside = [t for t in ticks if t_start <= t <= t_end]
gap = max((b - a for a, b in zip(inside, inside[1:])), default=9.0)
check("kinetics: the fit runs off the main thread, once (second press ignored)",
      calls == [False], str(calls))
check("kinetics: the main loop keeps answering during a 2 s fit (timer gaps < 0.5 s)",
      t_end - t_start >= 2.0 and len(inside) >= 20 and gap < 0.5,
      f"{t_end - t_start:.1f}s ticks={len(inside)} gap={gap:.2f}")
check("kinetics: button off for the whole fit, on again after",
      during[0] == (True, "disabled") and str(kd.btn_run.cget("state")) == "normal")

# the setup changes while a fit runs: its result is not shown
before = kd._last
calls.clear()
kd.run_fit(); pump(0.2)
old_wl = kd.var_wl.get()
kd.var_wl.set(f"{app.model.wls[10]:.2f}")
kd._on_wl_change()
wait(lambda: not kd._running)
pump(0.2)
check("kinetics: λ changed during a fit - the old-λ result is dropped, with a note",
      calls == [False] and kd._last is None and "dropped" in kd.var_status.get()
      and str(kd.btn_run.cget("state")) == "normal" and len(kd.ax_main.lines) < 3
      and before is not None, kd.var_status.get())
kd.run_fit()
wait(lambda: not kd._running)
check("kinetics: ... and the next fit is for the new λ",
      kd._last is not None and abs(kd._last["_wl"] - app.model.wls[10]) < 1e-6)
kd.run_fit(); pump(0.2)
kd.reset()
wait(lambda: not kd._running)
pump(0.2)
check("kinetics: Reset during a fit - the result does not come back",
      # C-2 (1.6): Reset now stops the fit, so it ends as "Reset to defaults." instead of being dropped
      kd._last is None and kd.var_status.get() in ("Reset to defaults.", "Fit dropped - the setup changed while it ran.")
      and kd.txt.get("1.0", "end").strip() == "")
kd.var_wl.set(old_wl); kd._on_wl_change()
kd.var_n.set("2"); kd.table.set_n(2); kd.var_inf.set(True)

# a failing fit
NEW.fit_single_trace = lambda *a, **k: (_ for _ in ()).throw(ValueError("boom in the fit"))
boxes.clear()
kd.run_fit()
wait(lambda: not kd._running)
pump(0.2)
check("kinetics: a failing fit shows the error and frees the button",
      [b[0] for b in boxes] == ["showerror"] and "boom in the fit" in boxes[0][2]
      and str(kd.btn_run.cget("state")) == "normal" and kd.var_status.get() == "Fit failed."
      and not kd._running and str(kd.win.cget("cursor")) == "", str(boxes))
boxes.clear()
# C-18 (1.6): an exception of the fit that is not the kernel's own refusal is a fault of the program,
# and is now also reported to the callback-error handler (the freeze log)
check("kinetics: ... and that unexpected error is logged once", len(cb_errors) == 1 and "boom in the fit" in cb_errors[0])
cb_errors.clear()

# an error while showing the result must not end the polling
NEW.fit_single_trace = real_fit
real_report = kd._report
kd._report = lambda *a: (_ for _ in ()).throw(RuntimeError("report broke"))
kd.run_fit()
wait(lambda: not kd._running)
pump(0.3)
kd._report = real_report
got = len(cb_errors)
cb_errors.clear()
kd.run_fit()
ok_again = wait(lambda: not kd._running and kd.var_status.get().startswith("Fit done"), 30)
check("kinetics: an error while showing a result is raised once and the next fit still completes",
      got == 1 and ok_again and str(kd.btn_run.cget("state")) == "normal", f"errors={got}")

# closing the window while a fit runs
NEW.fit_single_trace = slow_fit
calls.clear()
kd.run_fit()
pump(0.3)
kd._on_close()
pump(3.0)
check("kinetics: closing the window during a fit raises nothing",
      calls == [False] and not cb_errors and not kd.alive, str(cb_errors[:1]))

# =========================================================================================
# C. a new file closes the analysis windows
# =========================================================================================
NEW.fit_single_trace = real_fit
real_global = NEW.fit_global_analysis
state = {"entered": 0, "left": 0}


def endless_global(D, t, stop_check=None, **k):
    state["entered"] += 1
    try:
        while not stop_check():
            time.sleep(0.05)
        raise NEW.GlobalAnalysisStopped()
    finally:
        state["left"] += 1


NEW.fit_global_analysis = endless_global
NEW.fit_single_trace = slow_fit
calls.clear()
app.open_crop(); app.open_mask(); app.open_kinetics(); app.open_global_analysis(); pump(0.4)
wins = (app._crop_win, app._mask_win, app._kinetics_win, app._global_win)
k1, g1 = app._kinetics_win, app._global_win
old_tmax = k1.var_tmax.get()
g1.run_fit(); k1.run_fit(); pump(0.4)
running = (g1._running, k1._running, state["entered"])
app.load(SAMPLE_B)
pump(0.3)
check("load: both fits were running when the new file was opened", running == (True, True, 1), str(running))
check("load: Crop, Mask, Kinetics and Global-analysis windows are all closed and forgotten",
      not any(w.alive for w in wins)
      and (app._crop_win, app._mask_win, app._kinetics_win, app._global_win) == (None,) * 4)
check("load: the running global fit is told to stop and its thread ends",
      g1._stop.is_set() and wait(lambda: state["left"] == 1, 5.0), str(state))
pump(3.0)
check("load: no callback exception and no error box from the fits that were cut off",
      not cb_errors and not [b for b in boxes if b[0] == "showerror"],
      str(cb_errors[:1]) + str(boxes))
check("load: the new file is shown", os.path.basename(app.var_path.get()) == os.path.basename(SAMPLE_B)
      and app.model.phu["ncurves"] == 42)

NEW.fit_global_analysis = real_global
NEW.fit_single_trace = real_fit
app.open_kinetics(); app.open_global_analysis(); pump(0.4)
k2, g2 = app._kinetics_win, app._global_win
m = app.model
check("load: reopened windows are new ones with the new file's time range",
      k2 is not k1 and g2 is not g1
      and k2.var_tmax.get() == f"{m.times[-1]:.4g}" and k2.var_tmax.get() != old_tmax
      and float(g2.var_tmax.get()) >= m.times[-1] - m.dt_ps,
      f"{k2.var_tmax.get()} {g2.var_tmax.get()} {m.times[-1]}")
k2.run_fit(); g2.run_fit()
done = wait(lambda: not k2._running and not g2._running, 120)
pump(0.3)
check("load: both fits run on the new file",
      done and k2._last is not None and g2._last is not None
      and k2.var_status.get().startswith("Fit done") and g2.var_status.get().startswith("Fit done"),
      f"{k2.var_status.get()} | {g2.var_status.get()}")
check("load: the kinetics fit used the new file's trace",
      np.array_equal(k2._last["_t_full"], m.times) and len(k2._last["_y_full"]) == m.n_t)
real_read = NEW.read_phu
NEW.read_phu = lambda p: (_ for _ in ()).throw(ValueError("not a PHU file"))
boxes.clear()
app.load(SAMPLE_A)
pump(0.2)
NEW.read_phu = real_read
check("load: a file that cannot be read leaves the windows and the loaded data alone",
      k2.alive and g2.alive and app._kinetics_win is k2 and app._global_win is g2
      and os.path.basename(app.var_path.get()) == os.path.basename(SAMPLE_B)
      and [b[0] for b in boxes] == ["showerror"], str(boxes))
boxes.clear()
app.load(SAMPLE_A)
pump(0.3)
check("load: opening a third file closes those too, finished results and all",
      not k2.alive and not g2.alive and app._kinetics_win is None and app._global_win is None)

check("no Tk callback exception", not cb_errors, cb_errors[0][-700:] if cb_errors else "")
check("no error boxes", not [b for b in boxes if b[0] == "showerror"], str(boxes))
top.destroy()
root.destroy()
print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(1 if fails else 0)
