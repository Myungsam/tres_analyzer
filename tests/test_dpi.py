"""Display scaling (review item D-14, second half): the program declares itself DPI aware and its pixel
sizes follow the display's scaling.

A display at 150 % cannot be had on the test PC, so it is imitated: Tk is told the resolution such a display
reports (tk scaling 2.0 = 144 dpi) before any widget is made, which is all a DPI-aware Tk sees of it. This
file runs in a process of its own because that setting is for the whole process.
"""
import ctypes
import os
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _versions                              # noqa: E402
import tkinter as tk                          # noqa: E402
from tkinter import font as tkfont            # noqa: E402
from tkinter import ttk                       # noqa: E402

NEW = _versions.load()
SAMPLE_A = _versions.samples()[0]
fails = []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail and not ok else ""))
    if not ok:
        fails.append(name)


def awareness():
    value = ctypes.c_int(-1)
    ctypes.windll.shcore.GetProcessDpiAwareness(0, ctypes.byref(value))
    return value.value


# ---- 1. the declaration ------------------------------------------------------------------------
has = all(hasattr(NEW, n) for n in ("dpi_aware", "ui_scale", "px", "scaled_geometry"))
check("the program has dpi_aware(), ui_scale(), px() and scaled_geometry()", has)
if not has:
    print("\nRESULT:", f"{len(fails)} FAILED: {fails}")
    sys.exit(1)

code = ("import sys, ctypes; sys.path.insert(0, r'%s'); import _versions; N = _versions.load();"
        "v = ctypes.c_int(-1); r = N.dpi_aware(); ctypes.windll.shcore.GetProcessDpiAwareness(0, ctypes.byref(v));"
        "print(r, v.value)" % HERE)
env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
on = subprocess.run([sys.executable, "-B", "-c", code], capture_output=True, text=True, env=env).stdout.split()
off = subprocess.run([sys.executable, "-B", "-c", code], capture_output=True, text=True,
                     env=dict(env, TCSPC_DPI_AWARE="0")).stdout.split()
check("dpi_aware() makes the process system-DPI aware (it was unaware: Windows stretched the window)",
      on == ["True", "1"], str(on))
check("TCSPC_DPI_AWARE=0 leaves it as it was", off == ["False", "0"], str(off))
main_src = open(os.path.join(_versions.ROOT, "tcspc_analysis", "app.py"), encoding="utf-8").read()
check("main() declares it before it makes its first window",
      "dpi_aware()" in main_src and main_src.index("dpi_aware()") < main_src.index("tk.Tk()"))

# ---- 2. sizes ----------------------------------------------------------------------------------
size = NEW.initial_window_size
check("at 100 % the start-up size is what it was", size(3440, 1440) == size(3440, 1440, 1.0) == (1440, 920)
      and size(1366, 768, 1.0) == (1326, 668), f"{size(3440, 1440)} {size(1366, 768, 1.0)}")
for (sw, sh, scale), want in (((3840, 2160, 1.5), (2160, 1380)), ((2560, 1440, 1.25), (1800, 1150)),
                              ((1920, 1080, 1.5), (1860, 930)), ((1920, 1200, 1.25), (1800, 1075))):
    w, h = size(sw, sh, scale)
    check(f"a {sw}x{sh} display at {scale:.0%}: {w}x{h} - the 100 % size times the scaling, or what fits",
          (w, h) == want and w <= sw and h <= sh, f"{w}x{h}, wanted {want}")

# ---- 3. at 100 % nothing changes (before the imitation: the setting stays for the process) -----------------------------------------------------------------
root2 = tk.Tk()
root2.geometry("300x80+0+0")
check("at 100 % ui_scale() is 1, px(n) is n and a geometry is left as it is",
      NEW.ui_scale(root2) == 1.0 and NEW.px(root2, 430) == 430 and NEW.scaled_geometry(root2, "1180x760") == "1180x760",
      f"{NEW.ui_scale(root2)} {NEW.scaled_geometry(root2, '1180x760')}")
root2.destroy()
# ---- 4. a display at 150 %, imitated -------------------------------------------------------------
root = tk.Tk()
root.tk.call("tk", "scaling", 2.0)            # 144 dpi: what Tk is given on a display at 150 %
for name in tkfont.names(root):               # fonts made before that take their size again
    f = tkfont.nametofont(name, root=root)
    f.configure(size=f.cget("size"))
root.geometry("300x80+0+0")
NEW.apply_theme(root)
errors = []
root.report_callback_exception = lambda *a: errors.append(str(a[1]))
for kind in ("showerror", "showwarning", "showinfo"):
    setattr(NEW.messagebox, kind, lambda *a, **k: None)


def pump(seconds=0.3):
    import time
    end = time.time() + seconds
    root.update()
    while time.time() < end:
        root.update()
        time.sleep(0.01)


def squeezed(win):
    """Controls of ``win`` that got less room than they ask for."""
    out, todo = [], [win]
    kinds = (ttk.Button, ttk.Checkbutton, ttk.Entry, ttk.Combobox, ttk.Scale)
    while todo:
        w = todo.pop()
        todo.extend(c for c in w.winfo_children() if not isinstance(c, tk.Toplevel))
        if isinstance(w, kinds) and w.winfo_manager():
            if not w.winfo_ismapped() or w.winfo_width() < w.winfo_reqwidth() - 1 \
                    or w.winfo_height() < w.winfo_reqheight() - 1:
                text = ""
                try:
                    text = str(w.cget("text"))
                except tk.TclError:
                    pass
                out.append(f"{type(w).__name__} {text!r} {w.winfo_width()}x{w.winfo_height()} "
                           f"of {w.winfo_reqwidth()}x{w.winfo_reqheight()}")
    return out


scale = NEW.ui_scale(root)
check("ui_scale() reads 1.5 from such a display; px(430) is 645", abs(scale - 1.5) < 0.01 and NEW.px(root, 430) == 645,
      f"{scale} {NEW.px(root, 430)}")
screen = (root.winfo_screenwidth(), root.winfo_screenheight())
print(f"INFO test screen {screen[0]}x{screen[1]}, imitated scaling {scale:.2f}")
w, h = NEW.initial_window_size(*screen, scale)
for label, geom in (("its start-up size", f"{w}x{h}"),
                    ("its smallest size", f"{min(int(round(980 * scale)), w)}x{min(int(round(660 * scale)), h)}")):
    top = tk.Toplevel(root)
    top.geometry(geom + "+0+0")
    tab = ttk.Frame(top)
    tab.pack(fill="both", expand=True)
    app = NEW.TRESViewer(tab, SAMPLE_A)
    pump(0.6)
    cut = squeezed(top)
    check(f"main window at {label} ({geom}): no button, tick box or entry is cut off", not cut, "; ".join(cut[:4]))
    if label == "its start-up size":
        for name, attr, at_100 in (("Crop", "_crop_win", (1000, 920)), ("Mask", "_mask_win", None),
                                   ("Kinetics", "_kinetics_win", (1180, 760)), ("Global", "_global_win", (1500, 960))):
            getattr(app, {"Crop": "open_crop", "Mask": "open_mask", "Kinetics": "open_kinetics",
                          "Global": "open_global_analysis"}[name])()
            pump(0.6)
            d = getattr(app, attr)
            got = (d.win.winfo_width(), d.win.winfo_height())
            cut = squeezed(d.win)
            check(f"{name} window: opens with no control cut off", not cut, "; ".join(cut[:4]))
            if at_100:
                want = (min(int(round(at_100[0] * scale)), screen[0] - NEW.px(root, 40)),
                        min(int(round(at_100[1] * scale)), screen[1] - NEW.px(root, 100)))
                check(f"{name} window: its 100 % size times the scaling, or what the screen has room for",
                      abs(got[0] - want[0]) <= 2 and abs(got[1] - want[1]) <= 2, f"{got} wanted {want}")
            d._on_close(); pump(0.2)
    top.destroy()
check("no error in a callback", not errors, str(errors[:2]))
root.destroy()

leftover = os.path.join(_versions.ROOT, "TCSPC_analysis_freeze.log")
check("no freeze log left in the project folder", not os.path.exists(leftover))
print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(1 if fails else 0)
