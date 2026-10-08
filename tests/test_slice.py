"""Crop window time-slice spectra: real Tk + real matplotlib mouse events."""
import copy
import os
import sys
import time
import traceback

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.dont_write_bytecode = True
import tkinter as tk                          # noqa: E402
from tkinter import ttk                       # noqa: E402
from matplotlib.backend_bases import MouseEvent, LocationEvent  # noqa: E402
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _versions                              # noqa: E402
NEW = _versions.load()
OLD = _versions.load("1.1")
# These checks compare with an older version: the rules 1.6 changed on purpose are put back
# (see _versions.rules_of_1_5; the changes themselves are tested in test_g7.py / test_g8.py).
_versions.rules_of_1_5(NEW)

SAMPLE_A = _versions.samples()[0]
fails, cb_errors, boxes = [], [], []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail else ""))
    if not ok:
        fails.append(name)


def eq(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    return a.shape == b.shape and np.array_equal(a, b, equal_nan=True)


for mod in (NEW, OLD):
    for kind in ("showerror", "showwarning", "showinfo"):
        setattr(mod.messagebox, kind,
                lambda title="", msg="", _k=kind, **kw: boxes.append((_k, title, msg)))
next_open = {"path": ""}
NEW.filedialog.askopenfilename = lambda **kw: next_open["path"]
real_read = NEW.read_phu
SAMPLE = real_read(SAMPLE_A)


def fake_read(path):
    if path == "SOLV":
        d = copy.copy(SAMPLE)
        d["counts"] = (SAMPLE["counts"][::-1].astype(np.uint64) * 3 // 2).astype(np.uint32)
        d["path"] = r"C:\somewhere\blank.phu"
        return d
    return real_read(path)


NEW.read_phu = fake_read
root = tk.Tk()
root.withdraw()
root.report_callback_exception = lambda *a: cb_errors.append(
    "".join(traceback.format_exception(*a)))
NEW.apply_theme(root)


def pump(seconds=0.0):
    end = time.time() + seconds
    root.update()
    while time.time() < end:
        root.update()
        time.sleep(0.01)


def build(mod):
    top = tk.Toplevel(root)
    top.geometry("1440x900+0+0")
    tab = ttk.Frame(top)
    tab.pack(fill="both", expand=True)
    app = mod.TRESViewer(tab, SAMPLE_A)
    pump(0.3)
    app.open_crop()
    pump(0.4)
    return top, app, app._crop_win


# ---- baseline from the backup: steady-state data and heatmap ----------------
top_o, app_o, d_o = build(OLD)
old_ss = np.array(d_o.ln_sample.get_ydata(), float).copy()
old_heat = np.ma.getdata(d_o._base_im.get_array()).copy()
old_note = app_o._export_note()
old_E = app_o.model.E.copy()
d_o._on_close()
top_o.destroy()
pump(0.1)

top, app, d = build(NEW)
canvas = d.canvas


def pix(ax, x, y):
    return ax.transData.transform((x, y))


def press(x, y, dbl=False, ax=None):
    """A real button_press_event through matplotlib's callback registry."""
    px, py = pix(ax or d.ax, x, y)
    canvas.callbacks.process("button_press_event",
                             MouseEvent("button_press_event", canvas, px, py, button=1,
                                        dblclick=dbl))


def double_click(x, y):
    d._pin_time = 0.0       # as if the last toggle were long ago (see the triple-click test)
    press(x, y)             # Tk delivers the first click of the pair as a single one
    press(x, y, dbl=True)


def move(x, y, ax=None):
    px, py = pix(ax or d.ax, x, y)
    canvas.callbacks.process("motion_notify_event",
                             MouseEvent("motion_notify_event", canvas, px, py))


def leave(ax=None):
    ev = LocationEvent("axes_leave_event", canvas, 0, 0)
    ev.inaxes = ax or d.ax
    canvas.callbacks.process("axes_leave_event", ev)


def crop():
    return (d._corner, d.var_wl_lo.get(), d.var_wl_hi.get(), d.var_t_lo.get(),
            d.var_t_hi.get())


f = d._full
slice_lines = (d.ln_t_sample, d.ln_t_solv, d.ln_t_sub)
wl_mid = float(np.mean(d.wl_full))

# ---- 1. steady-state lines: alpha 0.5, same data ----------------------------
check("steady-state lines are drawn at alpha 0.5",
      [ln.get_alpha() for ln in (d.ln_sample, d.ln_solv, d.ln_sub)] == [0.5, 0.5, 0.5])
check("steady-state data and heatmap unchanged vs the backup",
      eq(d.ln_sample.get_ydata(), old_ss)
      and np.array_equal(np.ma.getdata(d._base_im.get_array()), old_heat))
check("slice lines live on the right-hand axis, bolder than the steady-state lines",
      all(ln.axes is d.ax_t for ln in slice_lines)
      and all(ln.get_linewidth() == 2.2 and ln.get_linestyle() == "-" for ln in slice_lines)
      and all(ln.axes is d.ax_ss for ln in (d.ln_sample, d.ln_solv, d.ln_sub))
      and d.ax_t.yaxis.get_ticks_position() == "right"
      and max(ln.get_linewidth() for ln in (d.ln_sample, d.ln_solv, d.ln_sub)) < 2.2)
check("nothing shown before the pointer enters the map",
      not any(ln.get_visible() for ln in slice_lines) and not d.hl_t.get_visible()
      and d.ax_t.get_legend() is None)

# ---- 2. hover follows the pointer (no solvent: sample only) ------------------
t1 = 3000.0
move(wl_mid, t1)
ti1 = int(t1 // f.dt_ps)
check("hover: the spectrum of that time bin appears (sample only without a solvent)",
      d._slice_ti == ti1 and d.ln_t_sample.get_visible()
      and not d.ln_t_solv.get_visible() and not d.ln_t_sub.get_visible()
      and eq(d.ln_t_sample.get_ydata(), d._raw0[:, ti1])
      and eq(d.ln_t_sample.get_xdata(), f.wls) and d.hl_t.get_visible())
# the sample slice equals the rebinned raw counts, computed here from the file
p = SAMPLE
rb = f.rebin
idx = [i for i in range(p["ncurves"]) if i != (0 if f.first_is_irf else None)]
ref = p["counts"][idx, ti1 * rb:(ti1 + 1) * rb].astype(np.float64).sum(axis=1)
check("sample slice == raw counts of that bin, rebinned (independent of the model)",
      eq(d.ln_t_sample.get_ydata(), ref) and abs(d.hl_t.get_ydata()[0] - (ti1 + 0.5) * f.dt_ps) < 1e-9)
t2 = 6200.0
move(wl_mid, t2)
ti2 = int(t2 // f.dt_ps)
check("hover: moving to another time bin changes the spectrum",
      d._slice_ti == ti2 and ti2 != ti1 and eq(d.ln_t_sample.get_ydata(), d._raw0[:, ti2])
      and not eq(d._raw0[:, ti2], d._raw0[:, ti1]))
leg = d.ax_t.get_legend()
check("legend title names the time, not pinned",
      leg is not None and leg.get_title().get_text() == f"t = {(ti2 + 0.5) * f.dt_ps:,.0f} ps",
      leg.get_title().get_text() if leg else "")
move(float(d.wl_full[0]) + 5, 100.0, ax=d.ax_ss)     # onto the lower panel = off the map
check("moving from the map onto the lower panel hides an unpinned slice (matplotlib's own leave event)",
      d._slice_ti is None and not d.ln_t_sample.get_visible())
move(wl_mid, t2)
check("coming back onto the map shows it again", d._slice_ti == ti2)
leave()
check("leaving the map hides an unpinned slice",
      d._slice_ti is None and not any(ln.get_visible() for ln in slice_lines)
      and not d.hl_t.get_visible() and d.ax_t.get_legend() is None)

# ---- 3. double-click pins / releases, crop box untouched ---------------------
c0 = crop()
move(wl_mid, t1)
double_click(wl_mid, t1)
check("double-click pins the slice", d._slice_pinned and d._slice_ti == ti1
      and "(pinned)" in d.ax_t.get_legend().get_title().get_text())
check("double-click leaves the crop box and the corner state alone", crop() == c0, str(crop()))
move(wl_mid, t2)
move(float(d.wl_full[0]) + 5, 100.0, ax=d.ax_ss)
leave()
check("pinned: pointer moves, the lower panel and leaving the map change nothing",
      d._slice_ti == ti1 and d.ln_t_sample.get_visible()
      and eq(d.ln_t_sample.get_ydata(), d._raw0[:, ti1]))
double_click(wl_mid, t2)
check("second double-click releases it (follows the pointer again)",
      not d._slice_pinned and d._slice_ti == ti2 and crop() == c0
      and "(pinned)" not in d.ax_t.get_legend().get_title().get_text())
move(wl_mid, t1)
check("released: hover updates again", d._slice_ti == ti1)

# ---- 4. single clicks still set the crop box ---------------------------------
x0, x1 = d.wl_full[0] + 30, d.wl_full[1] - 40
press(x0, 2000.0)
check("first single click arms a corner", d._corner is not None and crop()[1:] == c0[1:])
armed = crop()
double_click(wl_mid, t2)                # double-click while a corner is pending
check("double-click with a corner pending: corner still pending, box unchanged, pinned",
      crop() == armed and d._slice_pinned, str(crop()))
press(x1, 8000.0)
check("second single click completes the box (two-click crop still works)",
      d._corner is None and abs(float(d.var_wl_lo.get()) - x0) < 1e-3
      and abs(float(d.var_wl_hi.get()) - x1) < 1e-3
      and float(d.var_t_lo.get()) == 2000.0 and float(d.var_t_hi.get()) == 8000.0,
      str(crop()))
boxed = crop()
double_click(wl_mid, t1)                # release; must not disturb the finished box
check("double-click after a finished box leaves it alone", crop() == boxed and not d._slice_pinned)

# a stale undo must not fire: box picked by two clicks, then typed over, then a
# press just outside the map followed at once by a double press just inside it
press(x0, 2500.0); press(x1, 7500.0)      # leaves the second click's snapshot behind
check("(setup) box finished by two single clicks",
      d._corner is None and float(d.var_t_lo.get()) == 2500.0)
d.var_wl_lo.set("500"); d.var_wl_hi.set("600"); d.var_t_lo.set("100"); d.var_t_hi.set("9000")
d._update_overlay()
typed = crop()
bb = d.ax.bbox
y_pix = bb.y0 + 0.4 * bb.height
d._pin_time = 0.0
was_pinned = d._slice_pinned
for px, dbl in ((bb.x0 - 2, False), (bb.x0 + 2, True)):
    canvas.callbacks.process("button_press_event",
                             MouseEvent("button_press_event", canvas, px, y_pix, button=1,
                                        dblclick=dbl))
check("press outside the map + double press inside: typed crop values survive",
      crop() == typed and d._slice_pinned != was_pinned, str(crop()))
double_click(wl_mid, t1)        # back to the state before this block
check("... and the toggle is undone by another double-click", d._slice_pinned == was_pinned
      and crop() == typed)

# triple click: Tk reports the third press as a double one again - one toggle only
d._pin_time = 0.0
state0 = d._slice_pinned
press(wl_mid, t1); press(wl_mid, t1, dbl=True); press(wl_mid, t1, dbl=True)
check("triple click toggles once, crop untouched", d._slice_pinned != state0 and crop() == typed)
time.sleep(0.55)
press(wl_mid, t1); press(wl_mid, t1, dbl=True)      # guard time over: this one toggles back
check("0.55 s later a double-click toggles again (no reset of the guard)",
      d._slice_pinned == state0 and crop() == typed)
press(wl_mid, t1); press(wl_mid, t1, dbl=True)      # ... and one right after it is ignored
check("a double-click within 0.5 s of the last toggle is ignored",
      d._slice_pinned == state0 and crop() == typed)
d._full_wl(); d._full_t()

# the pointer leaving the canvas altogether: Tk <Leave>, which matplotlib reports
# as figure_leave_event only (no axes_leave_event)
if d._slice_pinned:
    double_click(wl_mid, t1)
move(wl_mid, t2)
shown_before = d._slice_ti
canvas.get_tk_widget().event_generate("<Leave>")
pump(0.05)
check("pointer leaving the canvas (Tk <Leave>) hides an unpinned slice",
      shown_before == ti2 and d._slice_ti is None and not d.ln_t_sample.get_visible()
      and not d.hl_t.get_visible())
move(wl_mid, t1)
double_click(wl_mid, t1)
canvas.get_tk_widget().event_generate("<Leave>")
pump(0.05)
check("pointer leaving the canvas keeps a pinned slice",
      d._slice_pinned and d._slice_ti == ti1 and d.ln_t_sample.get_visible())
double_click(wl_mid, t1)

# ---- 5. with a solvent: three lines, exact relation, unclipped ---------------
next_open["path"] = "SOLV"
d._load_solvent()
d.var_scale.set("0.8"); d._on_scale_entry()
pump(0.05)
check("steady-state lines keep alpha 0.5 with a solvent",
      [ln.get_alpha() for ln in (d.ln_sample, d.ln_solv, d.ln_sub)] == [0.5, 0.5, 0.5])
move(wl_mid, t1 + 1)        # same bin -> force a refresh through a different one first
move(wl_mid, t2)
move(wl_mid, t1)
solv = fake_read("SOLV")
sref = solv["counts"][idx, ti1 * rb:(ti1 + 1) * rb].astype(np.float64).sum(axis=1)
ys, yv, yd = (np.array(ln.get_ydata(), float) for ln in slice_lines)
check("with a solvent all three slice lines are shown",
      all(ln.get_visible() for ln in slice_lines)
      and [t.get_text() for t in d.ax_t.get_legend().get_texts()]
      == ["sample", "s x solvent", "difference"])
check("s x solvent slice == scale * solvent counts of that bin", eq(yv, 0.8 * sref))
check("difference slice == sample - s x solvent exactly, negatives kept",
      eq(yd, ref - 0.8 * sref) and eq(ys - yv, yd) and bool((yd < 0).any()),
      f"min {yd.min():.1f}")
check("difference slice equals the heatmap model's unclipped column",
      eq(yd, f.E_raw[:, ti1]) and eq(yd, f.E[:, ti1]))      # A-9 (1.6): E is not cut to 0 either
lo, hi = d.ax_t.get_ylim()
check("right axis spans the slice and includes zero",
      lo <= min(yd.min(), 0) and hi >= max(ys.max(), yv.max()) and lo < 0 < hi)

# ---- 6. pinned slice follows the scale ----------------------------------------
double_click(wl_mid, t1)
d.var_scale.set("0.3"); d._on_scale_entry()
pump(0.05)
check("pinned slice follows a new scale",
      d._slice_pinned and eq(d.ln_t_solv.get_ydata(), 0.3 * sref)
      and eq(d.ln_t_sub.get_ydata(), ref - 0.3 * sref))
d.scale.set(1.2)
pump(0.35)
check("pinned slice follows the slider (after the debounce)",
      eq(d.ln_t_solv.get_ydata(), 1.2 * sref) and eq(d.ln_t_sub.get_ydata(), ref - 1.2 * sref))
d._clear_solvent()
pump(0.05)
check("clearing the solvent leaves the pinned sample slice only",
      d._slice_pinned and d.ln_t_sample.get_visible() and not d.ln_t_solv.get_visible()
      and not d.ln_t_sub.get_visible() and eq(d.ln_t_sample.get_ydata(), ref))

# ---- 7. preview only: nothing reaches the live model --------------------------
check("live model, main window and export note untouched by all of the above",
      eq(app.model.E, old_E) and app.model.solvent is None
      and app._export_note() == old_note and not app.var_solv.get())
d._apply()
pump(0.1)
check("Apply without a solvent gives the same model data as before the feature",
      eq(app.model.E, old_E) and app._export_note() == old_note)

# ---- 8. a real Tk double-click on the canvas widget ----------------------------
double_click(wl_mid, t1)            # release the pin first
w = canvas.get_tk_widget()
w.update_idletasks()
px, py = pix(d.ax, wl_mid, t2)
ty = w.winfo_height() - py          # Tk's y runs downward
w.focus_force()
pump(0.6)
c_before = crop()
# two presses in quick succession at one spot: Tk itself turns the second into
# <Double-Button-1>, which is what a user's double-click produces
for seq in ("<Motion>", "<ButtonPress-1>", "<ButtonRelease-1>",
            "<ButtonPress-1>", "<ButtonRelease-1>"):
    w.event_generate(seq, x=int(px), y=int(ty))
pump(0.2)
check("real Tk <Double-Button-1> on the canvas pins the slice and keeps the crop box",
      d._slice_pinned and abs(d._slice_ti - ti2) <= 4 and crop() == c_before,
      f"pinned={d._slice_pinned} ti={d._slice_ti} (want {ti2}) crop={crop()}")

d._on_close()
pump(0.3)
check("no Tk callback exception", not cb_errors, cb_errors[0][-700:] if cb_errors else "")
check("no error boxes", not [b for b in boxes if b[0] == "showerror"], str(boxes))
top.destroy()
root.destroy()
print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(1 if fails else 0)
