"""The reported sequence in the real program (main(), freeze log on, native Open dialogs).

File A: crop + solvent, mask, kinetics fit, global fit -> Open file B through the real
dialog -> main-window settings -> crop -> fits. The dialogs are filled in with window
messages (no keystrokes). Passes when the freeze log shows no stall and no callback error.
"""
import ctypes
import ctypes.wintypes as wt
import os
import sys
import tempfile
import threading
import time

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _versions                              # noqa: E402

T = _versions.load()
ROOT = _versions.ROOT
A = _versions.samples()[0]
B = _versions.samples()[1]
LOG = os.path.join(tempfile.mkdtemp(prefix="tcspc_native_"), "freeze.log")
T.FreezeLog._open = classmethod(lambda cls: (LOG, open(LOG, "a", encoding="utf-8",
                                                       errors="replace", buffering=1)))
notes, boxes = [], []


def say(*a):
    notes.append(" ".join(str(x) for x in a))
    print(time.strftime("%H:%M:%S"), *a, flush=True)


for kind in ("showerror", "showwarning", "showinfo"):
    setattr(T.messagebox, kind, lambda title="", msg="", _k=kind, **kw: boxes.append((_k, title, str(msg)[:120])))

u32 = ctypes.windll.user32
u32.FindWindowW.restype = wt.HWND
u32.GetDlgItem.restype = wt.HWND
u32.SendMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
ENUM = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)


def fill_dialog(title, path, limit=20.0):
    def run():
        end = time.time() + limit
        hwnd = None
        while time.time() < end and not hwnd:
            hwnd = u32.FindWindowW("#32770", title)
            time.sleep(0.2)
        if not hwnd:
            say("FILLER: dialog", repr(title), "never appeared")
            return
        time.sleep(1.0)
        edits = []

        def cb(h, _):
            buf = ctypes.create_unicode_buffer(64)
            u32.GetClassNameW(h, buf, 64)
            if buf.value == "Edit" and u32.IsWindowVisible(h):
                edits.append(h)
            return True
        u32.EnumChildWindows(hwnd, ENUM(cb), 0)
        text = ctypes.create_unicode_buffer(path)
        u32.SendMessageW(edits[0], 0x000C, 0, ctypes.cast(text, ctypes.c_void_p).value)
        time.sleep(0.3)
        u32.PostMessageW(hwnd, 0x0111, 1, u32.GetDlgItem(hwnd, 1))
    threading.Thread(target=run, daemon=True).start()


steps, got = [], {}


def step(name, delay=600):
    def deco(fn):
        steps.append((name, delay, fn))
        return fn
    return deco


class Viewer(T.TRESViewer):
    """The real viewer; only notes itself so the steps can reach it."""

    def __init__(self, parent, initial_path=None):
        super().__init__(parent, initial_path)
        got["app"] = self
        got["root"] = parent.winfo_toplevel()
        got["root"].geometry("1440x920+0+0")
        got["root"].after(1500, run_next)


def run_next(i=0):
    if i >= len(steps):
        return
    name, delay, fn = steps[i]
    t = time.perf_counter()
    again = fn(got["app"])
    if again == "wait":
        got["root"].after(300, lambda: run_next(i))
        return
    say(f"step done: {name} ({time.perf_counter() - t:.2f} s)")
    got["root"].after(delay, lambda: run_next(i + 1))


@step("crop: load solvent through the native dialog", 2500)
def _(app):
    app.open_crop()
    fill_dialog("Open the solvent measurement", A)
    app._crop_win._load_solvent()


@step("crop: box + scale + apply")
def _(app):
    c = app._crop_win
    got["solvent"] = c._solvent is not None
    wl = app.model.wls
    c._set_scale(0.5)
    c.var_wl_lo.set(f"{wl[3]:g}"); c.var_wl_hi.set(f"{wl[-4]:g}")
    c.var_t_lo.set("1000"); c.var_t_hi.set("20000")
    c._update_overlay(); c._apply()


@step("mask a band")
def _(app):
    app.open_mask()
    wl = app.model.wls
    mk = app._mask_win
    mk.var_lo.set(f"{wl[8]:g}"); mk.var_hi.set(f"{wl[10]:g}"); mk._add()


@step("kinetics + global fit: start")
def _(app):
    app.open_kinetics(); app._kinetics_win.run_fit()
    app.open_global_analysis(); app._global_win.run_fit()


@step("fits: wait")
def _(app):
    if app._kinetics_win._running or app._global_win._running:
        return "wait"
    got["fit1"] = (app._kinetics_win.var_status.get(), app._global_win.var_status.get())


@step("OPEN the second file through the native dialog", 2500)
def _(app):
    got["old"] = (app._kinetics_win, app._global_win)
    fill_dialog("Open PicoQuant histogram file", B)
    app.open_dialog()


@step("the second file: wait until it is read")     # B-10 (1.6): Open reads on a worker thread
def _(app):
    if app._loading:
        return "wait"
    got["file2"] = os.path.basename(app.var_path.get())


@step("main window: settings + redraw")
def _(app):
    app.apply_params()
    app.var_bin.set("8 ps"); app.apply_params()
    app.reset_view(); app.reset_contrast()


@step("crop on the new file")
def _(app):
    app.open_crop()
    c = app._crop_win
    wl = app.model.wls
    c.var_wl_lo.set(f"{wl[2]:g}"); c.var_wl_hi.set(f"{wl[-3]:g}")
    c._update_overlay(); c._apply()


@step("fits on the new file: start")
def _(app):
    app.open_kinetics(); app._kinetics_win.run_fit()
    app.open_global_analysis(); app._global_win.run_fit()


@step("fits on the new file: wait")
def _(app):
    if app._kinetics_win._running or app._global_win._running:
        return "wait"
    got["fit2"] = (app._kinetics_win.var_status.get(), app._global_win.var_status.get())


@step("quit", 300)
def _(app):
    got["old_alive"] = [w.alive for w in got["old"]]
    got["root"].after(300, got["root"].destroy)


def give_up():
    time.sleep(240)
    print("TIMEOUT - the sequence did not finish; freeze log:\n",
          open(LOG, encoding="utf-8").read()[-3000:], flush=True)
    os._exit(3)


threading.Thread(target=give_up, daemon=True).start()
T.TRESViewer = Viewer
sys.argv = [sys.argv[0], A]
T.main()                                        # returns when the window is destroyed

body = open(LOG, encoding="utf-8").read()
fails = []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail and not ok else ""))
    if not ok:
        fails.append(name)


check("the whole sequence ran: solvent loaded, both fits done on both files",
      got.get("solvent") is True
      and all(s.startswith("Fit done") for s in got.get("fit1", ("",)) + got.get("fit2", ("",))),
      str(got.get("fit1")) + str(got.get("fit2")))
check("the second file came in through the real Open dialog",
      got.get("file2") == os.path.basename(B), str(got.get("file2")))
check("opening it closed the kinetics and global windows of the first file",
      got.get("old_alive") == [False, False], str(got.get("old_alive")))
check("freeze log: main() started it", f"started, version {T.APP_VERSION}" in body, body[:200])
check("freeze log: no stall reported", "not answering" not in body and "Timeout" not in body, body[-1500:])
check("freeze log: no callback error", "error in a callback" not in body, body[-1500:])
check("no error boxes", not [b for b in boxes if b[0] == "showerror"], str(boxes))
print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(1 if fails else 0)
