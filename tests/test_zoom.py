"""Crop window: wheel zoom, right-drag pan, colour and time scale. Real Tk + matplotlib events."""
import copy
import os
import sys
import time
import traceback

import numpy as np
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.dont_write_bytecode = True
import tkinter as tk                          # noqa: E402
from tkinter import ttk                       # noqa: E402
from matplotlib.backend_bases import MouseEvent  # noqa: E402
from matplotlib.colors import LogNorm, Normalize  # noqa: E402
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _versions                              # noqa: E402
# ZOOM_MODULE: the path of a (mutated) copy to test instead of the newest version
NEW = _versions.load(path=os.environ["ZOOM_MODULE"]) if os.environ.get("ZOOM_MODULE") else _versions.load()
OLD = _versions.load("1.2")

SAMPLE_A = _versions.samples()[0]
fails, cb_errors, boxes = [], [], []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail and not ok else ""))
    if not ok:
        fails.append(name)


def eq(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    return a.shape == b.shape and np.array_equal(a, b, equal_nan=True)


def close(a, b, tol=1e-9):
    a, b = np.asarray(a, float), np.asarray(b, float)
    return a.shape == b.shape and bool(np.all(np.abs(a - b) <= tol * np.maximum(1.0, np.abs(b))))


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


def build(mod, log_color=None):
    top = tk.Toplevel(root)
    top.geometry("1440x900+0+0")
    tab = ttk.Frame(top)
    tab.pack(fill="both", expand=True)
    app = mod.TRESViewer(tab, SAMPLE_A)
    pump(0.3)
    if log_color is not None:
        app.var_log.set(log_color)
    app.open_crop()
    pump(0.4)
    return top, app, app._crop_win


# ---- baseline from the backup -------------------------------------------------
top_o, app_o, d_o = build(OLD)
old_heat = np.ma.getdata(d_o._base_im.get_array()).copy()
old_ss = np.array(d_o.ln_sample.get_ydata(), float).copy()
old_lims = (d_o.ax.get_xlim(), d_o.ax.get_ylim(), d_o.ax_ss.get_ylim())
old_norm = (type(d_o._base_im.norm), d_o._base_im.norm.vmin, d_o._base_im.norm.vmax)
d_o._on_close()
top_o.destroy()
pump(0.1)

top, app, d = build(NEW)
canvas = d.canvas
f = d._full
dt = f.dt_ps
FULL_X = tuple(float(v) for v in f.wl_edges)
T_HI = float(f.t_hi)
FLOOR = 0.5 * dt
wl_mid = float(np.mean(d.wl_full))
redraws = []
real_redraw = app.redraw
app.redraw = lambda *a, **k: (redraws.append(1), real_redraw(*a, **k))[1]


def pix(x, y, ax=None):
    return (ax or d.ax).transData.transform((x, y))


def mouse(name, px, py, **kw):
    canvas.callbacks.process(name, MouseEvent(name, canvas, px, py, **kw))


def old_move(px, py, tk_state):
    """A move as matplotlib < 3.10 reports it: no .buttons, only Tk's event state."""
    ev = MouseEvent("motion_notify_event", canvas, px, py, guiEvent=SimpleNamespace(state=tk_state))
    del ev.buttons
    canvas.callbacks.process("motion_notify_event", ev)


def scroll(x, y, step, mods=()):
    px, py = pix(x, y)
    mouse("scroll_event", px, py, step=step, modifiers=mods)


def press(x, y, dbl=False, button=1):
    px, py = pix(x, y)
    mouse("button_press_event", px, py, button=button, dblclick=dbl)


def move(x, y):
    px, py = pix(x, y)
    mouse("motion_notify_event", px, py)


def drag(x, y, dx, dy, release=True):
    """Right-button drag from data (x, y) by (dx, dy) pixels."""
    px, py = pix(x, y)
    mouse("button_press_event", px, py, button=3)
    mouse("motion_notify_event", px + dx, py + dy, buttons=(3,))
    if release:
        mouse("button_release_event", px + dx, py + dy, button=3)


def crop():
    return (d._corner, d.var_wl_lo.get(), d.var_wl_hi.get(), d.var_t_lo.get(),
            d.var_t_hi.get())


def view():
    return tuple(d.ax.get_xlim()), tuple(d.ax.get_ylim())


def widget(text, kind):
    """The control of the Crop window that carries this label."""
    found = []

    def walk(w):
        for c in w.winfo_children():
            if isinstance(c, kind) and str(c.cget("text")) == text:
                found.append(c)
            walk(c)
    walk(d.win)
    assert len(found) == 1, (text, len(found))
    return found[0]


def inside(lims=None, full_y=None):
    (x0, x1), (y0, y1) = lims or view()
    fy = full_y or ((FLOOR if d.var_tlog.get() else 0.0), T_HI)
    return FULL_X[0] <= x0 < x1 <= FULL_X[1] and fy[0] <= y0 < y1 <= fy[1]


def settings(model):
    return {k: copy.deepcopy(getattr(model, k)) for k in model.SETTINGS if k != "solvent"}


# ---- 0. the window opens as before ---------------------------------------------
check("opens on the whole map, linear time, colour as the main window, Auto off",
      view() == (FULL_X, (0.0, T_HI)) and d.ax.get_yscale() == "linear"
      and d.var_zlog.get() == bool(app.var_log.get()) and not d.var_auto.get()
      and not d.var_tlog.get())
check("heatmap, steady state, limits and norm identical to the backup",
      np.array_equal(np.ma.getdata(d._base_im.get_array()), old_heat)
      and eq(d.ln_sample.get_ydata(), old_ss)
      and (d.ax.get_xlim(), d.ax.get_ylim(), d.ax_ss.get_ylim()) == old_lims
      and (type(d._base_im.norm), d._base_im.norm.vmin, d._base_im.norm.vmax) == old_norm)
c0 = crop()
pin0 = (d._slice_pinned, d._slice_ti)

# ---- 1. wheel zoom ---------------------------------------------------------------
x_at, y_at = FULL_X[0] + 0.3 * (FULL_X[1] - FULL_X[0]), 0.2 * T_HI
p_before = pix(x_at, y_at)
scroll(x_at, y_at, +1)
(x0, x1), (y0, y1) = view()
check("wheel up: both ranges shrink by 1/1.25",
      close(x1 - x0, (FULL_X[1] - FULL_X[0]) / 1.25) and close(y1 - y0, T_HI / 1.25),
      str(view()))
check("wheel up: the point under the pointer stays put (<= 1 px)",
      float(np.abs(pix(x_at, y_at) - p_before).max()) <= 1.0,
      str(pix(x_at, y_at) - p_before))
for _ in range(6):
    p_before = pix(x_at, y_at)
    scroll(x_at, y_at, +1)
check("six more notches: still fixed under the pointer and inside the data",
      float(np.abs(pix(x_at, y_at) - p_before).max()) <= 1.0 and inside(), str(view()))
check("lower panel shares the zoomed wavelength range",
      tuple(d.ax_ss.get_xlim()) == view()[0] and tuple(d.ax_t.get_xlim()) == view()[0])
(x0, x1), _ = view()
sel = (f.wls >= x0) & (f.wls <= x1)
ss = np.asarray(d.ln_sample.get_ydata(), float)[sel]
lo, hi = min(ss.min(), 0.0), max(ss.max(), 1.0)
check("lower panel is scaled to the wavelengths in view",
      close(d.ax_ss.get_ylim(), (lo - 0.08 * (hi - lo), hi + 0.08 * (hi - lo)))
      and sel.sum() < f.n_w)

v = view()
scroll(x_at, y_at, +1, mods=("ctrl",))
check("Ctrl+wheel: time only", view()[0] == v[0] and view()[1] != v[1]
      and close(np.diff(view()[1]), np.diff(v[1]) / 1.25))
v = view()
scroll(x_at, y_at, -1, mods=("shift",))
check("Shift+wheel: wavelength only", view()[1] == v[1] and view()[0] != v[0]
      and close(np.diff(view()[0]), np.diff(v[0]) * 1.25))
px, py = pix(x_at, 100.0, ax=d.ax_ss)
v = view()
mouse("scroll_event", px, py, step=1, modifiers=())
check("wheel over the lower panel does nothing", view() == v)

for _ in range(40):
    scroll(x_at, y_at, -1)
check("wheel down stops at the whole map, exactly", view() == (FULL_X, (0.0, T_HI)), str(view()))
for _ in range(80):
    scroll(wl_mid, 3000.0, +1)
(x0, x1), (y0, y1) = view()
check("zooming in stops at two curves / four time bins",
      x1 - x0 >= 2 * (FULL_X[1] - FULL_X[0]) / f.n_w * (1 - 1e-9) and y1 - y0 >= 4 * dt * (1 - 1e-9)
      and x1 - x0 < 2.6 * (FULL_X[1] - FULL_X[0]) / f.n_w and y1 - y0 < 5.1 * dt, str(view()))
d._fit_view()

# ---- 2. right-button drag --------------------------------------------------------
for _ in range(4):
    scroll(wl_mid, 0.5 * T_HI, +1)
v = view()
box = d.ax.bbox
drag(wl_mid, 0.5 * T_HI, 60, -40)
(x0, x1), (y0, y1) = view()
check("right-drag moves the view by the dragged distance, widths unchanged",
      close(x0 - v[0][0], -60 / box.width * (v[0][1] - v[0][0]), 1e-6)
      and close(y0 - v[1][0], 40 / box.height * (v[1][1] - v[1][0]), 1e-6)
      and close(x1 - x0, v[0][1] - v[0][0]) and close(y1 - y0, v[1][1] - v[1][0]), str(view()))
v2 = view()
move(wl_mid + 10, 0.5 * T_HI)
check("after the release a move no longer drags the view", view() == v2 and d._pan is None)
drag(wl_mid, 0.5 * T_HI, 5000, 5000)
(x0, x1), (y0, y1) = view()
check("dragged far: stops at the edge of the data with the same widths",
      x0 == FULL_X[0] and y0 == 0.0 and close(x1 - x0, v[0][1] - v[0][0])
      and close(y1 - y0, v[1][1] - v[1][0]), str(view()))
drag(*[float(np.mean(a)) for a in view()], -5000, -5000)
(x0, x1), (y0, y1) = view()
check("... and at the opposite edge", x1 == FULL_X[1] and y1 == T_HI
      and close(x1 - x0, v[0][1] - v[0][0]) and close(y1 - y0, v[1][1] - v[1][0]), str(view()))
check("right button: crop box, corner and pin untouched",
      crop() == c0 and (d._slice_pinned, d._slice_ti) == pin0, str(crop()))
cx, cy = [float(np.mean(a)) for a in view()]
press(cx, cy, button=3)
mouse("button_release_event", *pix(cx, cy), button=3)
press(cx, cy, button=3)
press(cx, cy, button=3, dbl=True)
mouse("button_release_event", *pix(cx, cy), button=3)
check("right click and right double-click neither set a corner nor pin",
      crop() == c0 and not d._slice_pinned and d._pan is None)
press(cx, cy, button=2)
check("middle click does nothing", crop() == c0 and not d._slice_pinned and d._pan is None)

rng = np.random.default_rng(1)
ok, worst = True, ""
for i in range(400):
    (x0, x1), (y0, y1) = view()
    x, y = x0 + rng.random() * (x1 - x0), y0 + rng.random() * (y1 - y0)
    r = rng.integers(0, 5)
    if r < 3:
        scroll(x, y, int(rng.choice([-3, -1, 1, 1, 2])),
               mods=[(), ("ctrl",), ("shift",)][int(rng.integers(0, 3))])
    else:
        drag(x, y, float(rng.normal(0, 300)), float(rng.normal(0, 300)))
    if not inside():
        ok, worst = False, f"step {i}: {view()}"
        break
check("400 random wheel / drag steps never leave the data", ok, worst)

# ---- 2b. a drag owns the view; odd wheel input ------------------------------------
d._fit_view()
scroll(wl_mid, 0.5 * T_HI, +4)
cx, cy = [float(np.mean(a)) for a in view()]
move(cx, cy)
leave_ti = d._slice_ti
drag(cx, cy, 30, 20, release=False)
v = view()
ppx, ppy = pix(cx, cy)
mouse("scroll_event", ppx, ppy, step=2, modifiers=())
check("wheel during a right-drag is ignored", view() == v and d._pan is not None)
mouse("button_press_event", ppx, ppy, button=1)
check("left click during a right-drag sets no crop corner", crop() == c0)
ti_before = d._slice_ti
mouse("motion_notify_event", ppx + 3, ppy + 150, buttons=(3,))
check("the hover slice stays as it was while the map is dragged",
      d._slice_ti == ti_before == leave_ti and view() != v)
v = view()
mouse("motion_notify_event", ppx + 60, ppy + 60, buttons=())
check("a move with no button held ends a drag whose release was lost",
      d._pan is None and view() == v)
# the same on matplotlib < 3.10, whose move events carry no buttons: Tk's state is read
mouse("button_press_event", ppx, ppy, button=3)
old_move(ppx + 20, ppy + 20, 0x400)
moved_old = view() != v and d._pan is not None
v_q = view()
old_move(ppx + 25, ppy + 25, "??")        # Tk's placeholder for an unknown state
check("an unreadable Tk state neither ends the drag nor raises",
      d._pan is not None and view() != v_q and not cb_errors)
v = view()
old_move(ppx + 60, ppy + 60, 0)
check("no buttons on the event: Tk's button state carries the drag and ends a lost one",
      moved_old and d._pan is None and view() == v)
mouse("button_press_event", ppx, ppy, button=1)
check("... and the left click after it is taken again", d._corner is not None)
mouse("button_press_event", ppx, ppy, button=1)       # complete the box, then put the crop back
d._full_wl()
d._full_t()
check("(setup) crop back to the full range", crop() == c0, str(crop()))
px_ss, py_ss = pix(wl_mid, 100.0, ax=d.ax_ss)
mouse("button_press_event", px_ss, py_ss, button=3)
mouse("motion_notify_event", px_ss + 40, py_ss, buttons=(3,))
check("right press on the lower panel starts no drag", d._pan is None and view() == v)
mouse("button_release_event", px_ss + 40, py_ss, button=3)
d._fit_view()
scroll(wl_mid, 3000.0, +30)
(x0, x1), (y0, y1) = view()
check("one wheel event of many notches zooms as far as allowed instead of doing nothing",
      2 <= (x1 - x0) / ((FULL_X[1] - FULL_X[0]) / f.n_w) < 2.05      # cut back to what fits
      and close(y1 - y0, T_HI / 1.25 ** 20, 1e-6), str(view()))    # 20 notches at most, they fit
scroll(wl_mid, 3000.0, +30)
check("... and the next one reaches the smallest time range", 4 <= (view()[1][1] - view()[1][0]) / dt < 4.1,
      str(view()))
scroll(wl_mid, 3000.0, -5000)
check("an absurd wheel step neither raises nor leaves the data",
      not cb_errors and inside() and view()[1][1] - view()[1][0] > 50 * dt, str(view()))
scroll(wl_mid, 3000.0, 0)
scroll(wl_mid, 3000.0, 0.3)
check("zero and fractional wheel steps are fine", not cb_errors and inside())
d._fit_view()

# ---- 3. Fit, and the crop is left alone -------------------------------------------
check("crop box untouched by all that zooming", crop() == c0 and not redraws)
widget("Fit view", ttk.Button).invoke()        # C-22 (1.6): the button was "Fit"
check("Fit shows the whole map again", view() == (FULL_X, (0.0, T_HI)))
check("back in full view the lower panel is scaled as in the backup",
      tuple(d.ax_ss.get_ylim()) == old_lims[2])

# crop picked by two left clicks while zoomed in
scroll(wl_mid, 4000.0, +3)
(x0, x1), (y0, y1) = view()
ca = (x0 + 0.25 * (x1 - x0), y0 + 0.2 * (y1 - y0))
cb = (x0 + 0.7 * (x1 - x0), y0 + 0.8 * (y1 - y0))
press(*ca)
press(*cb)
got = [float(s) for s in crop()[1:]]
check("zoomed in: two left clicks set the crop box to the clicked data values",
      d._corner is None and close(got, [ca[0], cb[0], ca[1], cb[1]], 1e-5), str(got))
v = view()
widget("Apply", ttk.Button).invoke()
pump(0.2)
after_zoomed = settings(app.model)
check("Apply keeps the view", view() == v and len(redraws) == 1)
d._fit_view()
widget("Apply", ttk.Button).invoke()
pump(0.2)
m = app.model
check("Apply gives the same model settings zoomed in or not, and they are the box",
      settings(m) == after_zoomed and close(m.crop_wl, (got[0], got[1]), 1e-9)
      and close((m.t_min_ps, m.t_max_ps), (got[2], got[3]), 1e-9))
d._full_wl()
d._full_t()

# ---- 4. colour scale ---------------------------------------------------------------
cmap_name = app.var_cmap.get()
main_log = app.var_log.get()
n_redraw = len(redraws)
chk_log = widget("Log color", ttk.Checkbutton)
chk_auto = widget("Auto color", ttk.Checkbutton)
kinds, main_seen = [], []
for _ in range(2):
    chk_log.invoke()
    kinds.append((d.var_zlog.get(), type(d._base_im.norm)))
    main_seen.append(app.var_log.get())
check("Log color switches the map between LogNorm and Normalize",
      sorted(kinds) == [(False, Normalize), (True, LogNorm)], str(kinds))
check("... without touching the main window (var_log, no redraw)",
      main_seen == [main_log, main_log] and len(redraws) == n_redraw)


def vmax_of(norm_vmax):
    """What preview_norm_cmap makes of a maximum, for the scale in use."""
    return max(norm_vmax, 1.02) if d.var_zlog.get() else max(norm_vmax, 1e-9)


def view_max_ref():
    """Largest finite count among the cells that overlap the view (written apart from the app)."""
    (x0, x1), (y0, y1) = view()
    dw = (FULL_X[1] - FULL_X[0]) / f.n_w
    best = -np.inf
    cols = [i for i in range(f.n_w)
            if FULL_X[0] + (i + 1) * dw > x0 and FULL_X[0] + i * dw < x1]
    edges = np.arange(f.n_t + 1) * dt
    rows = np.nonzero((edges[1:] > y0) & (edges[:-1] < y1))[0]
    block = f.E[np.ix_(cols, rows)]
    block = block[np.isfinite(block)]
    return float(block.max()) if block.size else 0.0


for log in (True, False):
    if d.var_zlog.get() != log:
        chk_log.invoke()
    tag = "log" if log else "linear"
    check(f"[{tag}] Auto off: colour maximum is the whole map's",
          d._base_im.norm.vmax == vmax_of(d._vmax0))
    scroll(FULL_X[1] - 20.0, 0.85 * T_HI, +6)
    check(f"[{tag}] Auto off: zooming into a weak corner leaves it there",
          d._base_im.norm.vmax == vmax_of(d._vmax0) and view_max_ref() < 0.5 * d._vmax0,
          f"{view_max_ref()} vs {d._vmax0}")
    chk_auto.invoke()
    check(f"[{tag}] Auto on: colour maximum is the largest count in view",
          d.var_auto.get() and d._base_im.norm.vmax == vmax_of(view_max_ref()),
          f"{d._base_im.norm.vmax} vs {view_max_ref()}")
    seen = {d._base_im.norm.vmax}
    ok = True
    for step, how in ((-2, ()), (1, ("ctrl",)), (-1, ("shift",))):
        (x0, x1), (y0, y1) = view()
        scroll(0.5 * (x0 + x1), 0.5 * (y0 + y1), step, mods=how)
        ok &= d._base_im.norm.vmax == vmax_of(view_max_ref())
        seen.add(d._base_im.norm.vmax)
    drag(*[float(np.mean(a)) for a in view()], 150, 200)
    ok &= d._base_im.norm.vmax == vmax_of(view_max_ref())
    seen.add(d._base_im.norm.vmax)
    check(f"[{tag}] Auto on: follows wheel and drag", ok and len(seen) >= 3, str(seen))
    chk_auto.invoke()
    check(f"[{tag}] Auto off again: back to the whole map's maximum",
          not d.var_auto.get() and d._base_im.norm.vmax == vmax_of(d._vmax0))
    d._fit_view()

chk_auto.invoke()
j = int(0.4 * T_HI // dt)
keep_col = f.E[:, j].copy()
f.E[:, j] = 7.0 * d._vmax0
d._set_view(FULL_X, ((j - 20) * dt, (j + 0.3) * dt))
top_in = d._base_im.norm.vmax
d._set_view(FULL_X, ((j - 20) * dt, j * dt))
top_out = d._base_im.norm.vmax
check("Auto on: a time bin only partly in view at the top still counts",
      top_in == vmax_of(7.0 * d._vmax0) and top_out < top_in, f"{top_in} {top_out}")
f.E[:, j] = keep_col
chk_auto.invoke()
d._fit_view()

# with a solvent: the fixed scale stays, the automatic one follows the subtraction
next_open["path"] = "SOLV"
widget("Load solvent...", ttk.Button).invoke()
pump(0.3)
check("solvent loaded: fixed colour maximum unchanged", d._base_im.norm.vmax == vmax_of(d._vmax0)
      and d._solvent is not None)
chk_auto.invoke()
scroll(wl_mid, 0.3 * T_HI, +2)
a = d._base_im.norm.vmax
check("Auto on with a solvent: maximum of the subtracted map in view",
      a == vmax_of(view_max_ref()))
d.var_scale.set("0.4")
d._on_scale_entry()
pump(0.3)
b = d._base_im.norm.vmax
check("... and it follows a change of the solvent scale", b == vmax_of(view_max_ref()) and b != a,
      f"{a} -> {b}")
for fill, what in ((0.0, "0"), (-5.0, "negative"), (np.nan, "NaN")):
    f.E[:] = fill
    seen = []
    for _ in range(2):
        chk_log.invoke()        # recolours from the view, in log and in linear
        canvas.draw()
        seen.append((type(d._base_im.norm), d._base_im.norm.vmin, d._base_im.norm.vmax))
    check(f"everything in view {what}: drawn in log and linear, colour range stays valid",
          not cb_errors and view_max_ref() <= 0.0
          and sorted(t.__name__ for t, _, _ in seen) == ["LogNorm", "Normalize"]
          and all(np.isfinite(hi) and hi > lo for _, lo, hi in seen), str(seen))
chk_auto.invoke()
widget("Clear", ttk.Button).invoke()
pump(0.3)
if not d.var_zlog.get():
    chk_log.invoke()
d._fit_view()
check("solvent cleared, Auto off, full view: the heatmap is the backup's again",
      np.array_equal(np.ma.getdata(d._base_im.get_array()), old_heat)
      and d._base_im.norm.vmax == old_norm[2])

# ---- 5. log time axis -----------------------------------------------------------
chk_t = widget("Log time", ttk.Checkbutton)
c_lin = crop()
chk_t.invoke()
pump(0.2)
rect = d._overlay[-1]
check("Log time redraws the box at once: a box from 0 starts at the log axis bottom",
      float(d.var_t_lo.get()) == 0.0 and rect.get_y() == FLOOR
      and close(rect.get_height(), T_HI - FLOOR), f"{rect.get_y()} {rect.get_height()}")
check("Log time: log axis from the middle of the first bin to the end",
      d.ax.get_yscale() == "log" and view() == (FULL_X, (FLOOR, T_HI)), str(view()))
check("Log time leaves crop, pin, colour and the main window alone",
      crop() == c_lin and not d._slice_pinned and d.var_zlog.get() and not d.var_auto.get()
      and len(redraws) == n_redraw)


def band_error(ta, tb):
    """Paint the bins ta..tb at the colour maximum and return how far (px) the
    drawn band is from where the axis puts those times."""
    ia, ib = int(ta // dt), int(tb // dt) + 1
    img = np.zeros((f.n_t, f.n_w))
    img[ia:ib] = d._base_im.norm.vmax
    keep = d._base_im.get_array()
    d._base_im.set_data(d._transform(img))
    marker = d.hl_t.get_visible()
    d.hl_t.set_visible(False)
    for art in d._overlay:
        art.set_visible(False)
    canvas.draw()
    buf = np.asarray(canvas.buffer_rgba())[::-1, :, :3].astype(float)      # bottom-up
    hot = np.array(d._base_im.cmap(1.0)[:3]) * 255
    cold = np.array(d._base_im.cmap(0.0)[:3]) * 255
    col = buf[:, int(pix(wl_mid, ta)[0])]
    bb = d.ax.bbox
    rows = np.arange(int(np.ceil(bb.y0)) + 2, int(bb.y1) - 2)
    is_hot = np.abs(col[rows] - hot).sum(axis=1) < np.abs(col[rows] - cold).sum(axis=1)
    d._base_im.set_data(keep)
    d.hl_t.set_visible(marker)
    for art in d._overlay:
        art.set_visible(True)
    if not is_hot.any():
        return 99.0
    lo = max(pix(wl_mid, max(ia * dt, d.ax.get_ylim()[0]))[1], rows[0])
    hi = min(pix(wl_mid, min(ib * dt, d.ax.get_ylim()[1]))[1], rows[-1] + 1)
    drawn = rows[is_hot]
    return float(max(abs(drawn.min() - lo), abs(drawn.max() + 1 - hi)))


errs = [band_error(40.0, 90.0), band_error(700.0, 2500.0), band_error(0.5 * T_HI, 0.8 * T_HI)]
check("log axis, whole map: bands of bins are drawn at their log positions (<= 2 px)",
      max(errs) <= 2.0, str(errs))
scroll(wl_mid, 1500.0, +5)
(_, (y0, y1)) = view()
errs = [band_error(y0 * 1.3, y0 * 1.9), band_error(np.sqrt(y0 * y1), y1 / 1.2)]
check("log axis, zoomed in: same (<= 2 px)", max(errs) <= 2.0 and inside(), str(errs))
p_before = pix(wl_mid, 1500.0)
v = view()
scroll(wl_mid, 1500.0, +1, mods=("ctrl",))
(_, (y0, y1)) = view()
check("log axis: Ctrl+wheel zooms in decades about the pointer",
      float(np.abs(pix(wl_mid, 1500.0) - p_before).max()) <= 1.0
      and close(np.log10(y1 / y0), np.log10(v[1][1] / v[1][0]) / 1.25, 1e-6))
v = view()
drag(wl_mid, 1500.0, 0, 50)
(_, (y0, y1)) = view()
check("log axis: a drag keeps the ratio of the two ends",
      close(y1 / y0, v[1][1] / v[1][0], 1e-6) and y0 < v[1][0] and view()[0] == v[0])
d._fit_view()
# dragged to early times the same decades are fewer than four bins: the wheel must still zoom out
scroll(wl_mid, 3000.0, +8, mods=("ctrl",))
for _ in range(5):
    (_, (y0, y1)) = view()
    drag(wl_mid, float(np.sqrt(y0 * y1)), 0, 0.8 * d.ax.bbox.height)
(_, (y0, y1)) = view()
check("(setup) log axis dragged to the bottom: fewer than four bins in view",
      y0 == FLOOR and y1 - y0 < 4 * dt, str(view()))
v = view()
scroll(wl_mid, float(np.sqrt(y0 * y1)), +1)
check("... zooming in further is refused there", view()[1] == v[1])
for step in (-0.1, -1):
    v = view()
    scroll(wl_mid, float(np.sqrt(v[1][0] * v[1][1])), step, mods=("ctrl",))
    check(f"... but a wheel step of {step} zooms out of it",
          view()[1][1] > v[1][1] and view()[1][0] == FLOOR, str(view()))
d._fit_view()

# hover, pin, click on the log axis
t_a, t_b = 180.0, 9000.0
move(wl_mid, t_a)
check("log axis: hover shows the bin at that time",
      d._slice_ti == int(t_a // dt) and eq(d.ln_t_sample.get_ydata(), d._raw0[:, int(t_a // dt)])
      and close(d.hl_t.get_ydata()[0], (int(t_a // dt) + 0.5) * dt))
d._pin_time = 0.0
press(wl_mid, t_b)
press(wl_mid, t_b, dbl=True)
check("log axis: double-click pins that time, crop untouched",
      d._slice_pinned and d._slice_ti == int(t_b // dt) and crop() == c_lin)
d._pin_time = 0.0
press(wl_mid, t_b)
press(wl_mid, t_b, dbl=True)
check("log axis: second double-click releases", not d._slice_pinned and crop() == c_lin)
ca, cb = (FULL_X[0] + 30.0, 150.0), (FULL_X[1] - 30.0, 12000.0)
press(*ca)
press(*cb)
got = [float(s) for s in crop()[1:]]
check("log axis: two left clicks set the crop box to the clicked data values",
      close(got, [ca[0], cb[0], ca[1], cb[1]], 1e-5), str(got))
rect = d._overlay[-1]
spans = [a for a in d._overlay[:-1]]
check("log axis: box drawn at the crop values, with dimmed margins on all four sides",
      close((rect.get_x(), rect.get_y(), rect.get_width(), rect.get_height()),
            (got[0], got[2], got[1] - got[0], got[3] - got[2]), 1e-9) and len(spans) == 4)
d._full_t()
rect = d._overlay[-1]
check("log axis: a box that starts at 0 is drawn from the axis bottom, its value stays 0",
      float(d.var_t_lo.get()) == 0.0 and close((rect.get_y(), rect.get_height()),
                                                (FLOOR, T_HI - FLOOR))
      and all(a.get_extents().height >= 0 and np.all(np.isfinite(a.get_extents().bounds))
              for a in d._overlay))
canvas.draw()
d._full_wl()

# linear <-> log keeps the range in view
scroll(wl_mid, 2000.0, +4)
v = view()
chk_t.invoke()
pump(0.1)
check("log -> linear keeps the view", d.ax.get_yscale() == "linear" and close(view(), v, 1e-9), str(view()))
chk_t.invoke()
pump(0.1)
check("linear -> log keeps the view", d.ax.get_yscale() == "log" and close(view(), v, 1e-9), str(view()))
d._fit_view()
chk_t.invoke()
pump(0.1)
check("log (full) -> linear: the bottom is 0 again", view() == (FULL_X, (0.0, T_HI))
      and d.ax.get_yscale() == "linear", str(view()))
errs = [band_error(700.0, 2500.0), band_error(0.5 * T_HI, 0.8 * T_HI)]
check("linear axis: bands still at their positions (<= 2 px)", max(errs) <= 2.0, str(errs))
scroll(wl_mid, 1.0, +3, mods=("ctrl",))
top_lin = view()[1][1]
check("(setup) linear view from just above 0", 0.0 < view()[1][0] < FLOOR and top_lin < 0.6 * T_HI,
      str(view()))
chk_t.invoke()
pump(0.1)
(_, (y0, y1)) = view()
check("linear view starting below the first bin's middle -> log: starts at the log bottom, same top",
      y0 == FLOOR and y1 == top_lin, str(view()))
chk_t.invoke()
pump(0.1)
check("... and back: from 0", view()[1] == (0.0, top_lin), str(view()))

# ---- 6. real Tk events ---------------------------------------------------------------
d._fit_view()
w = canvas.get_tk_widget()
d.win.lift()
w.focus_force()
pump(0.4)
w.update_idletasks()
px, py = pix(wl_mid, 0.4 * T_HI)
ty = w.winfo_height() - py
rx, ry = w.winfo_rootx() + int(px), w.winfo_rooty() + int(ty)
on_top = w.winfo_containing(rx, ry) == w
v = view()
w.event_generate("<MouseWheel>", delta=120, rootx=rx, rooty=ry, x=int(px), y=int(ty))
pump(0.2)
a = view()
w.event_generate("<MouseWheel>", delta=120, rootx=rx, rooty=ry, x=int(px), y=int(ty), state=4)
pump(0.2)
b = view()
w.event_generate("<MouseWheel>", delta=-120, rootx=rx, rooty=ry, x=int(px), y=int(ty), state=1)
pump(0.2)
c = view()
if on_top:
    check("real Tk <MouseWheel>: zooms both axes", a[0] != v[0] and a[1] != v[1], str(a))
    check("real Tk Ctrl+<MouseWheel>: time only", b[0] == a[0] and b[1] != a[1], str(b))
    check("real Tk Shift+<MouseWheel>: wavelength only", c[1] == b[1] and c[0] != b[0], str(c))
else:
    print("SKIP real Tk wheel: the canvas is not the top window at that spot")
    # nothing was zoomed then, and a full view cannot be dragged: zoom in for the next check
    scroll(wl_mid, 0.4 * T_HI, +2)
    px, py = pix(wl_mid, 0.4 * T_HI)
    ty = w.winfo_height() - py
v = view()
c_before = crop()
for seq, (ox, oy) in (("<ButtonPress-3>", (0, 0)), ("<B3-Motion>", (40, 30)),
                      ("<ButtonRelease-3>", (40, 30))):
    w.event_generate(seq, x=int(px) + ox, y=int(ty) + oy)
pump(0.2)
check("real Tk right-button drag moves the view and leaves the crop box alone",
      view() != v and close(np.diff(view()[0]), np.diff(v[0])) and crop() == c_before
      and d._pan is None, str(view()))

# ---- 7. nothing is kept after closing ------------------------------------------------
chk_t.invoke()
chk_auto.invoke()
if d.var_zlog.get() == bool(app.var_log.get()):
    chk_log.invoke()
pump(0.1)
d._on_close()
pump(0.2)
app.open_crop()
pump(0.4)
d = app._crop_win
canvas, f = d.canvas, d._full
check("reopened: whole map, linear time, Auto off, colour as the main window",
      view() == (FULL_X, (0.0, T_HI)) and d.ax.get_yscale() == "linear"
      and not d.var_tlog.get() and not d.var_auto.get()
      and d.var_zlog.get() == bool(app.var_log.get())
      and np.array_equal(np.ma.getdata(d._base_im.get_array()), old_heat))
d._on_close()
top.destroy()
pump(0.1)

top, app, d = build(NEW, log_color=False)
check("main window on linear colour: the Crop window opens linear",
      not d.var_zlog.get() and isinstance(d._base_im.norm, Normalize)
      and not isinstance(d._base_im.norm, LogNorm))
d._on_close()
pump(0.2)
check("no Tk callback exception", not cb_errors, cb_errors[0][-900:] if cb_errors else "")
check("no error boxes", not [b for b in boxes if b[0] == "showerror"], str(boxes))
top.destroy()
root.destroy()
print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(1 if fails else 0)
