"""1.7: the default background window, the BIN guard and the restyled windows (plan S9). One section per item;
see _harness.py. `python test_v17.py UI-8` runs one section.

BG-1..BG-8  the default window a file opens with is BG_WINDOW_PS (0-10000 ps of record time), ended three IRF
            widths before the IRF peak when that comes first (TRESModel.default_bg_window); a typed window is
            never shortened. Record C is the README's sample (tests/README.md).
BIN-1..3    the BIN choices, locked until a file is loaded, carried over between files.
UI-1..10    roles and groups, toolbars, toolbar vs the program's own mouse actions, number boxes, nothing
            squeezed, nothing lost against 1.6 (ui_inventory.py), fonts, contrast. FLIM: the FLIM tab.
UI-11..15, BG-9  the code review's findings M1, M3, L4, L5, L6, L7.
UI-16..18, BG-10  the review of the captures: figure labels inside, two-line status bar, no overlaps, no
            share-below-0 warning on a near-empty background.
UI-19..23, BG-11, BG-12  Save in three formats, Back / Forward restore limits only, a failed load, a window closed
            with a draw queued, the gap before that draw; the warning goes by the sample's own background; the
            margin before the peak is at least one bin.
"""
import io
import math
import os
import subprocess
import tarfile

import numpy as np

from _harness import (NEW, ROOT, SAMPLE_A, SAMPLE_B, TMP, boxes, cb_errors, check, finish, make_app, make_phu,
                      pump, root, section, wait)
import _versions
import ui_inventory
import tkinter as tk
from tkinter import ttk
from matplotlib.backend_bases import MouseEvent
from matplotlib.backends.backend_tkagg import NavigationToolbar2Tk

ui_inventory.install()          # before any window: UI-8 reads the callbacks' Tcl names

BG_LO, BG_HI = NEW.BG_WINDOW_PS
CLIPPED, SHORT = "(ends before IRF peak)", "no pre-pulse region"
TOOL_KEYS = {"Home", "Back", "Forward", "Pan", "Zoom", "Subplots", "Save"}


def shown(value):
    """A window edge as the viewer writes it into its box."""
    return f"{round(value, 1) + 0.0:g}"


def boxes_of(app):
    return app.var_bg_lo.get(), app.var_bg_hi.get()


def record_c():
    try:
        return _versions.samples(("C",))[0]
    except SystemExit as exc:
        check("record C (the README's sample) is named in samples.json", False, str(exc))
        return None


def walk(w):
    """``w`` and everything inside it, matplotlib's toolbars included, windows opened from it not."""
    out = [w]
    for c in w.winfo_children():
        if not isinstance(c, tk.Toplevel):
            out += walk(c)
    return out


def groups_of(win):
    return [str(w.cget("text")) for w in walk(win) if w.winfo_class() == "TLabelframe"]


def button_of(win, text):
    hit = [w for w in walk(win) if isinstance(w, ttk.Button) and str(w.cget("text")) == text]
    return hit[0] if len(hit) == 1 else None


def style(w):
    return str(w.cget("style"))


def in_toolbar(w):
    while w is not None:
        if isinstance(w, NavigationToolbar2Tk):
            return True
        w = w.master
    return False


def squeezed(win):
    """Controls of ``win`` that got less room than they ask for (figure canvases and toolbars left out)."""
    out = []
    kinds = (ttk.Button, ttk.Checkbutton, ttk.Entry, ttk.Combobox, ttk.Scale)
    for w in walk(win):
        if isinstance(w, kinds) and w.winfo_manager() and not in_toolbar(w):
            if not w.winfo_ismapped() or w.winfo_width() < w.winfo_reqwidth() - 1 \
                    or w.winfo_height() < w.winfo_reqheight() - 1:
                try:
                    text = str(w.cget("text"))
                except tk.TclError:
                    text = ""
                out.append(f"{type(w).__name__} {text!r} {w.winfo_width()}x{w.winfo_height()} "
                           f"of {w.winfo_reqwidth()}x{w.winfo_reqheight()}")
    return out


def event(canvas, name, x, y, **kw):
    canvas.callbacks.process(name, MouseEvent(name, canvas, x, y, **kw))


def at(ax, x, y):
    return tuple(ax.transData.transform((x, y)))


def drag(canvas, ax, a, b, button=1):
    p0, p1 = at(ax, *a), at(ax, *b)
    event(canvas, "button_press_event", *p0, button=button)
    event(canvas, "motion_notify_event", (p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2, buttons=(button,))
    event(canvas, "motion_notify_event", *p1, buttons=(button,))
    event(canvas, "button_release_event", *p1, button=button)
    pump(0.05)


def click(canvas, ax, a, button=1):
    p = at(ax, *a)
    event(canvas, "button_press_event", *p, button=button)
    event(canvas, "button_release_event", *p, button=button)
    pump(0.05)


def synthetic(res_ps, name):
    """A small .phu at ``res_ps`` per bin (4 curves, 1024 bins)."""
    return make_phu(os.path.join(TMP, name), ncurves=4, nbins=1024, res=res_ps * 1e-12)


def all_windows(app):
    """Open Crop, Mask, Kinetics and Global analysis: {name: dialog}."""
    app.open_crop(); app.open_mask(); app.open_kinetics(); app.open_global_analysis(); pump(0.6)
    return {"Crop": app._crop_win, "Mask": app._mask_win, "Kinetics": app._kinetics_win,
            "Global": app._global_win}


def flim_tab(mod=NEW, size="980x660+0+0"):
    top = tk.Toplevel(root)
    top.geometry(size)
    tab = ttk.Frame(top)
    tab.pack(fill="both", expand=True)
    v = mod.FLIMViewer(tab)
    pump(0.4)
    return top, tab, v


# ---------------------------------------------------------------------------------------------
if section("BG-1"):
    # AC 1: before a file, the boxes show the nominal window; a model opens on its default window
    top = tk.Toplevel(root)
    tab = ttk.Frame(top); tab.pack(fill="both", expand=True)
    app = NEW.TRESViewer(tab)
    pump(0.2)
    check("empty window: the boxes show BG_WINDOW_PS", boxes_of(app) == (f"{BG_LO:g}", f"{BG_HI:g}"),
          str(boxes_of(app)))
    top.destroy()
    m = NEW.TRESModel(NEW.read_phu(SAMPLE_A))
    check("TRESModel(phu) opens on default_bg_window(), with background subtraction on",
          m.bg_sub and (m.bg_lo_ps, m.bg_hi_ps) == m.default_bg_window(), f"{m.bg_lo_ps} {m.bg_hi_ps}")

# ---------------------------------------------------------------------------------------------
if section("BG-2"):
    # AC 2: t0 off -> the default window as it is; t0 on -> shifted by t0; a reload keeps it; off again
    top, app = make_app(SAMPLE_A)
    m = app.model
    w = m.default_bg_window()
    check("t0 off: the boxes show default_bg_window()", boxes_of(app) == (shown(w[0]), shown(w[1])),
          f"{boxes_of(app)} {w}")
    app.var_t0.set(True); app.apply_params(); pump(0.2)
    t0 = app.model.t0
    want = (shown(w[0] - t0), shown(w[1] - t0))
    check("t0 on: the boxes show default_bg_window() - t0", t0 > 0 and boxes_of(app) == want,
          f"{boxes_of(app)} {want}")
    app.load(SAMPLE_A); pump(0.2)
    check("reloaded with t0 on: the same boxes", boxes_of(app) == want and app.model.t0 == t0, str(boxes_of(app)))
    app.var_t0.set(False); app.apply_params(); pump(0.2)
    check("t0 off again: back to default_bg_window()", boxes_of(app) == (shown(w[0]), shown(w[1])),
          str(boxes_of(app)))
    top.destroy()

# ---------------------------------------------------------------------------------------------
if section("BG-3"):
    # AC 3: the window in time bins, and the spectrum taken off
    path = record_c()
    for key, rec in (("C", path), ("A", SAMPLE_A)):
        if not rec:
            continue
        top, app = make_app(rec)
        w = app.model.default_bg_window()
        for label in ("4 ps", "16 ps", "32 ps"):
            app.var_bin.set(label); app.apply_params(); pump(0.1)
            m = app.model
            dt = m.dt_ps
            want = (int(math.floor(round(w[0], 1) / dt)), min(int(math.ceil(round(w[1], 1) / dt)), m.n_t))
            sl = m.bg_slice()
            check(f"{key}, t0 off, {label}: bg_slice() covers default_bg_window() in whole bins",
                  sl == want and np.array_equal(m.bg_spec, np.nanmean(m.E_raw[:, slice(*sl)], axis=1), equal_nan=True),
                  f"{sl} {want}")
            if key == "C":
                check(f"C, {label}: that is (0, ceil(BG_WINDOW_PS[1] / dt))",
                      sl == (0, int(math.ceil(BG_HI / dt))), str(sl))
        app.var_t0.set(True); app.var_bin.set("16 ps"); app.apply_params(); pump(0.1)
        m = app.model
        lo, hi = m.bg_window_ps
        check(f"{key}, t0 on: bg_window_ps + t0 is default_bg_window() within one bin",
              abs(lo + m.t0 - w[0]) <= m.dt_ps + 1e-6 and abs(hi + m.t0 - w[1]) <= m.dt_ps + 1e-6,
              f"{lo + m.t0} {hi + m.t0} {w}")
        top.destroy()

# ---------------------------------------------------------------------------------------------
if section("BG-4"):
    # a crop that starts after the window: the first kept bin is the background
    path = record_c() or SAMPLE_A
    top, app = make_app(path)
    app.open_crop(); pump(0.4)
    c = app._crop_win
    start = max(app.model.default_bg_window()[1], BG_HI) + 2000.0
    c.var_t_lo.set(f"{start:g}"); c._apply(); pump(0.3)
    check(f"Crop t from {start:g} ps: bg_slice() is the first kept bin",
          abs(app.model.t_min_ps - start) < 20 and app.model.bg_slice() == (0, 1),
          f"{app.model.t_min_ps} {app.model.bg_slice()}")
    top.destroy()

# ---------------------------------------------------------------------------------------------
if section("BG-5"):
    # the README's sample: the IRF peak lies after 10 ns, so the window is the whole nominal range
    path = record_c()
    if path:
        m = NEW.TRESModel(NEW.read_phu(path))
        check("record C: three IRF widths before the peak lie past the nominal end (the case is the unclipped one)",
              m.irf is not None and m.irf_peak_ps - 3 * m.irf_fwhm_ps > BG_HI,
              f"{m.irf_peak_ps} {m.irf_fwhm_ps}")
        check("record C: default_bg_window() is BG_WINDOW_PS", m.default_bg_window() == (BG_LO, BG_HI),
              str(m.default_bg_window()))
        check("record C: TRESModel(phu) opens on it", (m.bg_lo_ps, m.bg_hi_ps) == (BG_LO, BG_HI),
              f"{m.bg_lo_ps} {m.bg_hi_ps}")
        top, app = make_app(path)
        check("record C loaded: the boxes show BG_WINDOW_PS", boxes_of(app) == (shown(BG_LO), shown(BG_HI)),
              str(boxes_of(app)))
        check("... and the info line has no note", CLIPPED not in app.var_bginfo.get()
              and SHORT not in app.var_bginfo.get(), app.var_bginfo.get())
        top.destroy()

# ---------------------------------------------------------------------------------------------
if section("BG-6"):
    # samples A and B: the IRF peak lies before 10 ns, the window ends three widths before it
    for key, path in (("A", SAMPLE_A), ("B", SAMPLE_B)):
        m = NEW.TRESModel(NEW.read_phu(path))
        end = m.irf_peak_ps - 3 * m.irf_fwhm_ps
        w = m.default_bg_window()
        check(f"{key}: the window ends three IRF widths before the peak, inside the nominal range",
              w == (BG_LO, end) and BG_LO < end < BG_HI and not m.bg_short(w), f"{w} peak {m.irf_peak_ps}")
        check(f"{key}: TRESModel(phu) opens on it", (m.bg_lo_ps, m.bg_hi_ps) == w, f"{m.bg_lo_ps} {m.bg_hi_ps}")

    top, app = make_app(SAMPLE_A)
    m = app.model
    w = m.default_bg_window()
    check("A loaded (t0 off): the boxes show default_bg_window()", boxes_of(app) == (shown(w[0]), shown(w[1])),
          f"{boxes_of(app)} {w}")
    check("... the info line says it was shortened, in the usual colour",
          CLIPPED in app.var_bginfo.get() and str(app.lbl_bginfo.cget("foreground")) == NEW.PIN,
          f"{app.var_bginfo.get()} {app.lbl_bginfo.cget('foreground')}")
    app.var_t0.set(True); app.apply_params(); pump(0.2)
    t0 = m.t0
    check("t0 at IRF peak on: the boxes show the same record-time window, shifted by t0",
          t0 > 0 and boxes_of(app) == (shown(w[0] - t0), shown(w[1] - t0)), f"{boxes_of(app)} t0 {t0}")
    check("... and the note stays", CLIPPED in app.var_bginfo.get(), app.var_bginfo.get())
    # the user's window is the user's: typed past the IRF peak, it is used as typed
    app.var_bg_lo.set(shown(BG_LO - t0)); app.var_bg_hi.set(shown(BG_HI - t0)); app.apply_params(); pump(0.2)
    check("a typed window reaching past the IRF peak is used as typed, not shortened",
          (m.bg_lo_ps, m.bg_hi_ps) == (round(BG_LO - t0, 1) + 0.0, round(BG_HI - t0, 1) + 0.0)
          and boxes_of(app) == (shown(BG_LO - t0), shown(BG_HI - t0)), f"{m.bg_lo_ps} {m.bg_hi_ps}")
    check("... and the note is gone", CLIPPED not in app.var_bginfo.get(), app.var_bginfo.get())
    app.var_t0.set(False); app.apply_params(); pump(0.2)
    app.load(SAMPLE_A); pump(0.2)
    check("loading the file again opens on the default window again",
          boxes_of(app) == (shown(w[0]), shown(w[1])) and CLIPPED in app.var_bginfo.get(),
          f"{boxes_of(app)} {app.var_bginfo.get()}")
    top.destroy()

# ---------------------------------------------------------------------------------------------
if section("BG-7"):
    # a record whose IRF peaks at 0.5 ns: no region before the pulse is left
    phu = dict(NEW.read_phu(SAMPLE_A))
    t = (np.arange(phu["nbins"]) + 0.5) * phu["res_ps"]
    fwhm = 300.0
    irf = 5.0 + 1e4 * np.exp(-0.5 * ((t - 500.0) / (fwhm / (2 * np.sqrt(2 * np.log(2))))) ** 2)
    decay = 5.0 + 2000.0 * np.exp(-np.clip(t - 500.0, 0, None) / 2000.0) * (t > 500.0)
    counts = np.repeat(decay[None, :], phu["ncurves"], axis=0)
    counts[0] = irf
    phu["counts"] = np.rint(counts).astype(phu["counts"].dtype)
    m = NEW.TRESModel(phu)
    w = m.default_bg_window()
    check("peak at 0.5 ns: three IRF widths before it lie before the record starts (the case is the short one)",
          m.irf_peak_ps - 3 * m.irf_fwhm_ps < BG_LO, f"{m.irf_peak_ps} {m.irf_fwhm_ps}")
    check("... the window keeps one time bin at the start of the record, and is called short",
          w == (BG_LO, BG_LO + m.dt_ps) and m.bg_short(w) and m.bg_slice() == (0, 1), f"{w} {m.bg_slice()}")
    top, app = make_app(SAMPLE_A)
    app._show_loaded(phu, TMP + "/early_peak.phu"); pump(0.2)
    w = app.model.default_bg_window()
    check("loaded: the boxes show that one bin", boxes_of(app) == (shown(w[0]), shown(w[1])), str(boxes_of(app)))
    check("... and the info line warns, in the warning colour",
          SHORT in app.var_bginfo.get() and str(app.lbl_bginfo.cget("foreground")) == NEW.WARN,
          f"{app.var_bginfo.get()} {app.lbl_bginfo.cget('foreground')}")
    app.var_bg_hi.set(shown(BG_LO + 400.0)); app.apply_params(); pump(0.2)
    check("a typed window: no warning, the usual colour",
          SHORT not in app.var_bginfo.get() and str(app.lbl_bginfo.cget("foreground")) == NEW.PIN,
          f"{app.var_bginfo.get()} {app.lbl_bginfo.cget('foreground')}")
    top.destroy()

# ---------------------------------------------------------------------------------------------
if section("BG-8"):
    # what the comparisons with older versions rely on: the 1.6 default comes back exactly, and goes again
    phu = NEW.read_phu(SAMPLE_A)
    back = _versions.bg_default_of_1_6(NEW)
    m16 = NEW.TRESModel(phu)
    back()
    m17 = NEW.TRESModel(phu)
    check("bg_default_of_1_6: the first 100 ps of the record; restored: default_bg_window() again",
          (m16.bg_lo_ps, m16.bg_hi_ps) == (0.0, 100.0)
          and (m17.bg_lo_ps, m17.bg_hi_ps) == m17.default_bg_window() != (0.0, 100.0),
          f"{(m16.bg_lo_ps, m16.bg_hi_ps)} {(m17.bg_lo_ps, m17.bg_hi_ps)}")

# ---------------------------------------------------------------------------------------------
if section("BIN-1"):
    # AC 4: the choices are the file's bin width times 1 ... 64, none below it
    top, app = make_app(SAMPLE_A)
    for res in (4.0, 8.0, 16.0):
        app.load(synthetic(res, f"bin_{res:g}ps.phu")); pump(0.2)
        values = [str(v) for v in app.cb_bin.cget("values")]
        want = [f"{res * k:g} ps" for k in NEW.BIN_FACTORS]
        check(f"{res:g} ps file: BIN choices are res x {tuple(NEW.BIN_FACTORS)}",
              values == want and NEW.BIN_FACTORS == (1, 2, 4, 8, 16, 32, 64)
              and min(float(v.split()[0]) for v in values) == res, str(values))
    top.destroy()

# ---------------------------------------------------------------------------------------------
if section("BIN-2"):
    # AC 5: locked before a file, readonly after; a file that cannot be read leaves it as it was
    top = tk.Toplevel(root)
    tab = ttk.Frame(top); tab.pack(fill="both", expand=True)
    app = NEW.TRESViewer(tab)
    pump(0.2)
    check("no file: BIN box disabled", str(app.cb_bin.cget("state")) == "disabled", str(app.cb_bin.cget("state")))
    bad = make_phu(os.path.join(TMP, "broken.phu"), cut=200)
    boxes.clear()
    app.load(bad); pump(0.1)
    check("an unreadable file: still disabled, and an error box",
          str(app.cb_bin.cget("state")) == "disabled" and boxes and boxes[0][0] == "showerror", str(boxes))
    app.load(SAMPLE_A); pump(0.2)
    check("after a file: readonly", str(app.cb_bin.cget("state")) == "readonly")
    boxes.clear()
    app.load(bad); pump(0.1)
    check("an unreadable file after a good one: still readonly",
          str(app.cb_bin.cget("state")) == "readonly" and boxes, str(boxes))
    top.destroy()

# ---------------------------------------------------------------------------------------------
if section("BIN-3"):
    # AC 6: the width carries over (or the nearest one the next file has)
    top, app = make_app(SAMPLE_A)
    app.load(synthetic(4.0, "carry4.phu")); pump(0.1)
    app.var_bin.set("16 ps"); app.apply_params(); pump(0.1)
    got = []
    for res in (8.0, 16.0):
        app.load(synthetic(res, f"carry{res:g}.phu")); pump(0.1)
        got.append((app.var_bin.get(), app.model.dt_ps))
    check("16 ps carries over from a 4 ps file to an 8 ps and a 16 ps file",
          got == [("16 ps", 16.0), ("16 ps", 16.0)], str(got))
    app.var_bin.set("1024 ps"); app.apply_params(); pump(0.1)
    app.load(synthetic(4.0, "carry4b.phu")); pump(0.1)
    check("1024 ps on a 16 ps file -> 256 ps on a 4 ps file (the widest it has)",
          app.var_bin.get() == "256 ps" and app.model.dt_ps == 256.0, app.var_bin.get())
    top.destroy()

# ---------------------------------------------------------------------------------------------
if section("UI-1"):
    # roles, groups, the orange export buttons
    top, app = make_app(SAMPLE_A)
    want_role = {"Kinetics...": "Analysis.TButton", "Global analysis...": "Analysis.TButton",
                 "Save map image...": "Export.TButton", "Export data...": "Export.TButton"}
    for text in ("Open file...", "Crop...", "Mask λ...", "Apply offset", "Reset zoom", "Auto contrast"):
        want_role[text] = ""
    got = {t: (style(button_of(top, t)) if button_of(top, t) else None) for t in want_role}
    check("main window: every button has its role colour (grey: no style)", got == want_role, str(got))
    check("main window: groups Data / Background / Solvent / Display, no Export group",
          groups_of(top) == ["Data", "Background", "Solvent", "Display"], str(groups_of(top)))
    st = ttk.Style(root)
    check("theme: five role styles and the group style",
          all(st.lookup(f"{r}.TButton", "background") for r in ("Analysis", "Export", "Opju", "Run", "Stop"))
          and st.lookup("TLabelframe", "background") == NEW.PANEL)
    d = all_windows(app)
    want_groups = {"Crop": ["Range", "Solvent", "View"], "Mask": ["Region", "Masked regions"],
                   "Kinetics": ["Fit setup", "IRF (Gaussian)", "Fit range (ps)", "Export", "Trace, fit, residual"],
                   "Global": ["Fit setup", "IRF (Gaussian)", "Fit range (ps)", "Export", "Results"]}
    for name, want in want_groups.items():
        check(f"{name}: groups {want}", groups_of(d[name].win) == want, str(groups_of(d[name].win)))
    for name in ("Kinetics", "Global"):
        k = d[name]
        check(f"{name}: Run fit green, Stop red, Reset grey, Export results blue",
              (style(k.btn_run), style(k.btn_stop), style(button_of(k.win, "Reset")), style(k.btn_export))
              == ("Run.TButton", "Stop.TButton", "", "Export.TButton"))
    for name in ("Crop", "Mask"):
        roles = {style(w) for w in walk(d[name].win) if isinstance(w, ttk.Button)}
        check(f"{name}: all buttons grey", roles == {""}, str(roles))
    exports = [app.btn_export, d["Kinetics"].btn_export, d["Global"].btn_export]
    app.var_out_opju.set(True); pump(0.05)
    check(".opju ticked: Export data and both Export results orange",
          [style(b) for b in exports] == ["Opju.TButton"] * 3 and style(button_of(top, "Save map image...")) == "Export.TButton",
          str([style(b) for b in exports]))
    d["Kinetics"]._on_close(); pump(0.1)
    app.var_out_opju.set(False); pump(0.05)
    app.var_out_opju.set(True); pump(0.05)
    check("... after the Kinetics window is closed, the tick still works and raises nothing",
          style(app.btn_export) == "Opju.TButton" and style(d["Global"].btn_export) == "Opju.TButton"
          and not cb_errors, str(cb_errors[-1:]))
    app.var_out_opju.set(False); pump(0.05)
    check(".opju off: blue again", style(app.btn_export) == style(d["Global"].btn_export) == "Export.TButton")
    app._close_dialogs()
    top.destroy()

# ---------------------------------------------------------------------------------------------
if section("UI-2"):
    # one matplotlib toolbar per figure, above it, with all its buttons (Subplots is never pressed)
    top, app = make_app(SAMPLE_A)
    d = all_windows(app)
    ftop, ftab, fl = flim_tab()
    owners = [("main window", app, top)] + [(n, w, w.win) for n, w in d.items()] + [("FLIM", fl, ftop)]
    for name, owner, win in owners:
        bars = [w for w in walk(win) if isinstance(w, NavigationToolbar2Tk)]
        cw = owner.canvas.get_tk_widget()
        tb = owner.toolbar
        slaves = cw.master.pack_slaves()
        check(f"{name}: exactly one toolbar, a NavToolbar, packed above its canvas in the same frame",
              bars == [tb] and isinstance(tb, NEW.NavToolbar) and tb.master is cw.master
              and tb in slaves and slaves.index(tb) < slaves.index(cw) and tb.winfo_y() < cw.winfo_y(),
              f"{bars} {tb.winfo_y()} {cw.winfo_y()}")
        check(f"{name}: buttons {sorted(TOOL_KEYS)}", TOOL_KEYS <= set(tb._buttons), str(sorted(tb._buttons)))
    check("main window: the colour bar and the ribbon are not navigable (their state is not in the history)",
          not app.cax.get_navigate() and not app.ax_rib.get_navigate())
    ftop.destroy()
    app._close_dialogs()
    top.destroy()

# ---------------------------------------------------------------------------------------------
if section("UI-3"):
    # S6 acceptance 1, 2, 3, 7: the toolbar's modes against the program's own mouse actions on the main map
    top, app = make_app(SAMPLE_A)
    m, canvas, tb = app.model, app.canvas, app.toolbar
    w_lo, w_hi = m.wl_edges
    W = lambda f: w_lo + f * (w_hi - w_lo)
    T = lambda f: m.t_lo + f * (m.t_hi - m.t_lo)

    def limits():
        (x0, x1), (y0, y1) = app.ax_map.get_xlim(), app.ax_map.get_ylim()
        return (min(x0, x1), max(x0, x1), min(y0, y1), max(y0, y1))

    def view_matches():
        v = app.view if app.view else (*m.wl_edges, m.t_lo, m.t_hi)
        return np.allclose(v, limits(), rtol=1e-9, atol=1e-9)

    resets, rubber = [], []
    real_reset, real_rubber = app.reset_view, app._draw_rubber
    app.reset_view = lambda: (resets.append(1), real_reset())
    app._draw_rubber = lambda e: (rubber.append(1), real_rubber(e))
    tb.zoom(); pump(0.05)
    check("1: zoom mode holds the canvas", tb.locked())
    before = (app.pinned, app.clim)
    drag(canvas, app.ax_map, (W(0.3), T(0.3)), (W(0.6), T(0.6)))
    check("1: a map drag in zoom mode runs none of the program's drag: no _drag, no rubber band, pin and contrast kept",
          app._drag is None and not rubber and not app.rect.get_visible() and (app.pinned, app.clim) == before,
          f"{app._drag} {rubber} {app.pinned} {app.clim}")
    check("3: the toolbar's zoom rectangle is the new view (app.view = the map's limits)",
          app.view is not None and view_matches(), f"{app.view} {limits()}")
    click(canvas, app.ax_map, (W(0.4), T(0.4)), button=3)
    check("1: a right-click in zoom mode does not reset the view", not resets and app.view is not None)
    click(canvas, app.ax_map, (W(0.45), T(0.45)))
    check("1: a click in zoom mode does not pin", not app.pinned)
    drag(canvas, app.cax, (0.5, m.vmax * 0.2), (0.5, m.vmax * 0.6))
    check("1: a colour-bar drag in zoom mode leaves the contrast", app.clim is None, str(app.clim))
    app.cursor = None
    event(canvas, "motion_notify_event", *at(app.ax_map, W(0.5), T(0.5)))
    check("7: hovering in zoom mode (no drag) still moves the cursor read-out", app.cursor is not None)
    tb.zoom(); pump(0.05)
    check("zoom mode off: the canvas is free", not tb.locked())
    tb.home(); pump(0.05)
    # mode off: as in 1.6
    drag(canvas, app.ax_map, (W(0.2), T(0.25)), (W(0.7), T(0.75)))
    check("2: mode off, a map drag zooms as in 1.6",
          app.view is not None and np.allclose(app.view, (W(0.2), W(0.7), T(0.25), T(0.75)), rtol=1e-6), str(app.view))
    click(canvas, app.ax_map, (W(0.4), T(0.4)))
    check("2: a click pins", app.pinned)
    click(canvas, app.ax_map, (W(0.4), T(0.4)))
    check("2: a second click releases", not app.pinned)
    drag(canvas, app.cax, (0.5, m.vmax * 0.1), (0.5, m.vmax * 0.5))
    check("2: a colour-bar drag sets the contrast", app.clim is not None)
    click(canvas, app.ax_map, (W(0.4), T(0.4)), button=3)
    check("2: a right-click resets the view", resets and app.view is None)
    tb.pan()
    drag(canvas, app.ax_map, (W(0.5), T(0.5)), (W(0.4), T(0.45)))
    tb.pan()
    check("3: a pan drag: app.view = the (clamped) map limits", view_matches(), f"{app.view} {limits()}")
    check("no message box", not boxes, str(boxes))
    top.destroy()

# ---------------------------------------------------------------------------------------------
if section("UI-4"):
    # S6 acceptance 4, 5, 6: Home, Back / Forward, a new file
    top, app = make_app(SAMPLE_A)
    m, canvas, tb = app.model, app.canvas, app.toolbar
    w_lo, w_hi = m.wl_edges
    W = lambda f: w_lo + f * (w_hi - w_lo)
    T = lambda f: m.t_lo + f * (m.t_hi - m.t_lo)

    def lims():
        return (tuple(app.ax_map.get_xlim()), tuple(app.ax_map.get_ylim()), tuple(app.ax_spec.get_ylim()),
                tuple(app.ax_ss.get_xlim()), tuple(app.ax_ss.get_ylim()))

    def view_matches():
        (x0, x1), (y0, y1) = app.ax_map.get_xlim(), app.ax_map.get_ylim()
        v = app.view if app.view else (*m.wl_edges, m.t_lo, m.t_hi)
        return np.allclose(v, (min(x0, x1), max(x0, x1), min(y0, y1), max(y0, y1)), rtol=1e-9, atol=1e-9)

    flat = lambda L: np.array([v for pair in L for v in pair], float)
    full = lims()
    tb.zoom()
    ylo, yhi = app.ax_spec.get_ylim()
    drag(canvas, app.ax_spec, (W(0.2), ylo * 2), (W(0.5), yhi / 3))
    tb.zoom()
    zoomed = lims()
    tb.home(); pump(0.05)
    check("4: zoom in the spectrum panel, Home: every limit back, app.view None",
          not np.allclose(flat(zoomed), flat(full)) and app.view is None and np.allclose(flat(lims()), flat(full)),
          f"{lims()}")
    tb.zoom()
    sx0, sx1 = app.ax_ss.get_xlim(); sy0, sy1 = app.ax_ss.get_ylim()
    drag(canvas, app.ax_ss, (sx0 + 0.2 * (sx1 - sx0), sy0 + 0.2 * (sy1 - sy0)),
         (sx0 + 0.6 * (sx1 - sx0), sy0 + 0.7 * (sy1 - sy0)))
    tb.zoom()
    ss = tuple(app.ax_ss.get_xlim())
    tb.home(); pump(0.05)
    check("4: zoom in the steady-state panel (not shared), Home: its own limits back, app.view None",
          not np.allclose(ss, full[3]) and app.view is None and np.allclose(flat(lims()), flat(full)), str(lims()))
    drag(canvas, app.ax_map, (W(0.2), T(0.25)), (W(0.7), T(0.75)))
    tb.home(); pump(0.05)
    check("4: the program's drag zoom, Home: app.view None", app.view is None and view_matches())
    # Back / Forward across a program zoom and a toolbar zoom; the contrast is not part of the history
    app.redraw(full=True); pump(0.05)
    drag(canvas, app.ax_map, (W(0.2), T(0.25)), (W(0.7), T(0.75)))
    v1 = app.view
    tb.zoom()
    drag(canvas, app.ax_map, (W(0.3), T(0.35)), (W(0.5), T(0.6)))
    tb.zoom()
    v2 = app.view
    drag(canvas, app.cax, (0.5, m.vmax * 0.1), (0.5, m.vmax * 0.5))
    clim = app.clim
    tb.back(); pump(0.05)
    check("5: Back: the program's zoom, app.view follows", app.view is not None and np.allclose(app.view, v1)
          and view_matches(), f"{app.view} {v1}")
    tb.back(); pump(0.05)
    check("5: Back again: the whole map, app.view None", app.view is None and view_matches(), str(app.view))
    tb.forward(); tb.forward(); pump(0.05)
    check("5: Forward twice: the toolbar's zoom", app.view is not None and np.allclose(app.view, v2) and view_matches(),
          f"{app.view} {v2}")
    check("5: the colour-bar contrast survives Back / Forward", clim is not None and app.clim == clim
          and np.isclose(app.im.norm.vmax, clim[1]), f"{app.clim} {app.im.norm.vmax}")
    tb.home(); pump(0.05)
    check("5: ... and Home", app.clim == clim and np.isclose(app.im.norm.vmax, clim[1]))
    app.load(SAMPLE_B); pump(0.3)
    before = lims()
    tb.back(); pump(0.05)
    check("6: a second file: Back does nothing (only its base view is kept)",
          len(tb._nav_stack) == 1 and lims() == before and app.view is None, str(len(tb._nav_stack)))
    top.destroy()

# ---------------------------------------------------------------------------------------------
if section("UI-5"):
    # the dialogs: the toolbar's modes against their own mouse actions, Home, the history
    top, app = make_app(SAMPLE_A)
    app.open_crop(); pump(0.5)
    c = app._crop_win
    tb = c.toolbar
    check("Crop: one history entry after it is drawn", len(tb._nav_stack) == 1)
    xm, ym = sum(c.ax.get_xlim()) / 2, sum(c.ax.get_ylim()) / 2
    tb.zoom(); pump(0.05)
    event(c.canvas, "button_press_event", *at(c.ax, xm, ym), button=1)
    check("Crop, zoom mode: a click sets no corner", c._corner is None)
    event(c.canvas, "button_press_event", *at(c.ax, xm, ym), button=3)
    check("Crop, zoom mode: a right press starts no pan", c._pan is None)
    lim0 = (c.ax.get_xlim(), c.ax.get_ylim())
    event(c.canvas, "scroll_event", *at(c.ax, xm, ym), step=1)
    check("Crop, zoom mode: the wheel does not zoom", (c.ax.get_xlim(), c.ax.get_ylim()) == lim0)
    tb.zoom(); pump(0.05)
    event(c.canvas, "button_press_event", *at(c.ax, xm, ym), button=1)
    check("Crop, mode off: a click sets a corner", c._corner is not None)
    c._cancel_corner()
    c.ax.set_xlim(xm - 10, xm + 10); tb.push_current()
    tb.home(); pump(0.1)
    full = c._view_full()
    check("Crop: Home = the whole map (Fit view)",
          tuple(c.ax.get_xlim()) == tuple(full[0]) and tuple(c.ax.get_ylim()) == tuple(full[1]), str(c.ax.get_xlim()))
    c._on_close(); pump(0.1)

    app.open_mask(); pump(0.5)
    mk = app._mask_win
    tb = mk.toolbar
    xm, ym = sum(mk.ax.get_xlim()) / 2, sum(mk.ax.get_ylim()) / 2
    tb.pan(); pump(0.05)
    event(mk.canvas, "button_press_event", *at(mk.ax, xm, ym), button=1)
    event(mk.canvas, "button_release_event", *at(mk.ax, xm, ym), button=1)
    check("Mask, pan mode: a click picks nothing", mk.var_lo.get() == "")
    tb.pan(); pump(0.05)
    event(mk.canvas, "button_press_event", *at(mk.ax, xm, ym), button=1)
    check("Mask, mode off: a click picks From", mk.var_lo.get() != "")
    mk.ax.set_xlim(xm - 5, xm + 5); tb.home(); pump(0.1)
    check("Mask: Home = the whole map", tuple(mk.ax.get_xlim()) == tuple(app.model.wl_edges), str(mk.ax.get_xlim()))
    mk._on_close(); pump(0.1)

    app.open_kinetics(); pump(0.6)
    k = app._kinetics_win
    tb = k.toolbar
    check("Kinetics: one history entry after it is drawn", len(tb._nav_stack) == 1)
    drawn = tuple(k.ax_main.get_xlim())
    k.ax_main.set_xlim(drawn[0] + 1, drawn[0] + 10); tb.push_current()
    tb.home(); pump(0.1)
    check("Kinetics: Home goes back to the drawn view", tuple(k.ax_main.get_xlim()) == drawn, str(k.ax_main.get_xlim()))
    k._refresh_plot(); pump(0.2)
    check("Kinetics: a redraw starts a new history", len(tb._nav_stack) == 1)
    k._on_close(); pump(0.1)

    app.open_global_analysis(); pump(0.6)
    g = app._global_win
    tb = g.toolbar
    x = sum(g.ax_data.get_xlim()) / 2 + 3
    y = sum(g.ax_data.get_ylim()) / 2
    wl = g._kin_wl
    tb.zoom(); pump(0.05)
    event(g.canvas, "button_press_event", *at(g.ax_data, x, y), button=1)
    event(g.canvas, "button_release_event", *at(g.ax_data, x, y), button=1)
    check("Global, zoom mode: a map click does not pick λ", g._kin_wl == wl)
    tb.zoom(); pump(0.05)
    event(g.canvas, "button_press_event", *at(g.ax_data, x, y), button=1)
    pump(0.2)
    check("Global, mode off: a map click picks λ", g._kin_wl != wl)
    g.reset(); pump(0.2)
    check("Global: after Reset one history entry", len(tb._nav_stack) == 1)
    g._on_close(); pump(0.1)
    top.destroy()

# ---------------------------------------------------------------------------------------------
if section("UI-6"):
    # the number boxes: stepped in Python, as many decimals as the box or the step has
    frame = ttk.Frame(root); frame.pack()

    def stepped(text, step, n=1, down=False, lo=None, hi=None):
        var = tk.StringVar(value=text)
        sb = NEW.spin(frame, var, step, lo, hi)
        sb.pack()
        for _ in range(n):
            sb.event_generate("<<Decrement>>" if down else "<<Increment>>")
        out = var.get()
        sb.destroy()
        return out

    for text, step, want in (("10000", 100, "10100"), ("-13496.3", 100, "-13396.3"), ("0.2", 0.05, "0.25"),
                             ("-100", 100, "0"), ("500", 5.0, "505"), ("abc", 100, "abc")):
        got = stepped(text, step)
        check(f"{text!r} + {step:g} -> {want!r}", got == want, got)
    check("the upper bound clamps", stepped("950", 100, hi=1000) == "1000")
    # a box bound to an IntVar (FLIM's Nx / Ny / N_bins): IntVar.get() raises on text that is not a number
    iv = tk.IntVar(value=5)
    isb = NEW.spin(frame, iv, 1, lo=1)
    isb.pack()
    for text in ("", "abc"):
        isb.delete(0, "end"); isb.insert(0, text)
        isb.event_generate("<<Increment>>"); isb.event_generate("<<Decrement>>"); pump(0.05)
        check(f"IntVar box holding {text!r}: an arrow changes nothing and raises nothing",
              isb.get() == text and not cb_errors, f"{isb.get()!r} {cb_errors[-1:]}")
    isb.delete(0, "end"); isb.insert(0, "5")
    isb.event_generate("<<Increment>>"); pump(0.05)
    check("IntVar box holding '5': + 1 -> 6", iv.get() == 6 and isb.get() == "6", isb.get())
    isb.destroy()
    check("no Tcl error on any of that", not cb_errors, str(cb_errors[-1:]))
    top, app = make_app(SAMPLE_A)
    sb = [w for w in walk(top) if isinstance(w, ttk.Spinbox) and str(w.cget("textvariable")) == str(app.var_bg_hi)][0]
    before = app.var_bg_hi.get()
    sb.event_generate("<MouseWheel>", delta=120); pump(0.1)
    check("the mouse wheel changes nothing", app.var_bg_hi.get() == before)
    n = {"rebuild": 0}
    real_rb = app.model.rebuild
    app.model.rebuild = lambda: (n.__setitem__("rebuild", n["rebuild"] + 1), real_rb())[1]
    for _ in range(10):
        sb.event_generate("<<Increment>>")
    pump(0.1)
    check("10 steps: nothing applied before the pause", n["rebuild"] == 0)
    pump(0.5)
    check("... one apply_params (one rebuild) after it, with the window 10 steps on",
          n["rebuild"] == 1 and abs(app.model.bg_hi_ps - (float(before) + 1000)) < 0.11,
          f"{n} {app.model.bg_hi_ps} {before}")
    app.open_crop(); pump(0.4)
    c = app._crop_win
    tsb = [w for w in walk(c.win) if isinstance(w, ttk.Spinbox) and str(w.cget("textvariable")) == str(c.var_t_hi)][0]
    tsb.event_generate("<<Increment>>")
    c._on_close(); pump(0.5)
    check("closing the Crop window with a step still pending raises nothing", not cb_errors, str(cb_errors[-1:]))
    top.destroy()

# ---------------------------------------------------------------------------------------------
if section("UI-7"):
    # nothing squeezed: the main window at four sizes, the dialogs at their default and smallest size, the
    # fixed columns of Kinetics (430 px) and Global analysis (380 px)
    for size, path in (("980x660", None), ("980x660", SAMPLE_A), ("1280x800", SAMPLE_A), ("1440x920", SAMPLE_A)):
        top = tk.Toplevel(root)
        top.geometry(size + "+0+0")
        tab = ttk.Frame(top); tab.pack(fill="both", expand=True)
        app = NEW.TRESViewer(tab, path)
        pump(0.4)
        cut = squeezed(top)
        check(f"main window {size} ({'loaded' if path else 'empty'}): no control squeezed", not cut, "; ".join(cut[:4]))
        if path and size == "1440x920":
            d = all_windows(app)
            for name, dlg in d.items():
                cut = squeezed(dlg.win)
                check(f"{name} at its default size: no control squeezed", not cut, "; ".join(cut[:4]))
                mw, mh = dlg.win.minsize()
                dlg.win.geometry(f"{mw}x{mh}"); pump(0.4)
                cut = squeezed(dlg.win)
                check(f"{name} at its smallest size {mw}x{mh}: no control squeezed", not cut, "; ".join(cut[:4]))
                if name in ("Kinetics", "Global"):
                    col = dlg.win.winfo_children()[0].winfo_children()[0]
                    inner = col.winfo_width()
                    wide = [(w.winfo_class(), w.winfo_reqwidth()) for w in walk(col)[1:]
                            if w.winfo_manager() and w.winfo_reqwidth() > inner]
                    check(f"{name}: the fixed column is {NEW.px(root, 430 if name == 'Kinetics' else 380)} px "
                          f"and nothing in it asks for more", abs(inner - NEW.px(root, 430 if name == "Kinetics" else 380)) <= 2
                          and not wide, f"{inner} {wide[:5]}")
            app._close_dialogs()
        top.destroy()
        pump(0.1)

# ---------------------------------------------------------------------------------------------
if section("UI-8"):
    # nothing lost against 1.6: every control and every binding of the 1.6 windows is in the 1.7 ones
    v16 = os.environ.get("TCSPC_V16_ROOT")
    if not v16:
        v16 = os.path.join(TMP, "v16")
        tar = subprocess.run(["git", "-C", ROOT, "archive", "--format=tar", "4dfd887", "tcspc_analysis"],
                             capture_output=True, check=True).stdout
        with tarfile.open(fileobj=io.BytesIO(tar)) as tf:
            tf.extractall(v16, filter="data")
    OLD16 = _versions.load_package(v16, modules=_versions.MODULES_1_6)
    check("the 1.6 copy loads (no ui.py, its own classes)", not hasattr(OLD16, "spin")
          and OLD16.TRESViewer is not NEW.TRESViewer)

    def inventories(mod):
        out = {}
        top = tk.Toplevel(root); top.geometry("1440x920+0+0")
        tab = ttk.Frame(top); tab.pack(fill="both", expand=True)
        app = mod.TRESViewer(tab)
        pump(0.2)
        out["main (empty)"] = ui_inventory.inventory(app, top)
        app.load(SAMPLE_A); pump(0.3)
        out["main (loaded)"] = ui_inventory.inventory(app, top)
        for name, dlg in all_windows(app).items():
            out[name] = ui_inventory.inventory(dlg, dlg.win)
        app._close_dialogs()
        ftop, ftab, fl = flim_tab(mod)
        out["FLIM"] = ui_inventory.inventory(fl, ftop)
        ftop.destroy()
        top.destroy()
        pump(0.1)
        return out

    old_inv, new_inv = inventories(OLD16), inventories(NEW)
    report = []
    for name in old_inv:
        lost, lost_bind, added = ui_inventory.compare(old_inv[name], new_inv[name])
        kept = len(old_inv[name]) - len(lost)
        report.append(f"{name}: 1.6 {len(old_inv[name])} controls, 1.7 {len(new_inv[name])}; kept {kept}, "
                      f"lost {len(lost)}, binding problems {len(lost_bind)}, new {len(added)}")
        check(f"{name}: every 1.6 control is still there", not lost, "; ".join(lost[:4]))
        check(f"{name}: with its text, command, variable and bindings", not lost_bind, "; ".join(lost_bind[:3]))
    for line in report:
        print("INFO", line)
    # the comparison itself finds a loss: a control taken away, a binding taken away
    probe = [dict(r, bind=dict(r["bind"])) for r in new_inv["main (loaded)"]]
    tmax = next(r for r in probe if r["var"] == "var_tmax")
    del tmax["bind"]["<FocusOut>"]
    lost_b = ui_inventory.compare(old_inv["main (loaded)"], probe)[1]
    lost_c = ui_inventory.compare(old_inv["main (loaded)"], [r for r in probe if r["var"] != "var_bgsub"])[0]
    check("(the comparison reports a removed binding and a removed control)",
          len(lost_b) == 1 and "var_tmax" in lost_b[0] and len(lost_c) == 1 and "var_bgsub" in lost_c[0],
          f"{lost_b} {lost_c}")

# ---------------------------------------------------------------------------------------------
if section("UI-9"):
    # fonts: Segoe UI for the interface, Consolas for numbers and paths; made once per root
    from tkinter import font as tkfont
    names = set(tkfont.names(root))
    check("named fonts TcspcUI / TcspcFixed exist", {"TcspcUI", "TcspcFixed"} <= names)
    NEW.apply_theme(root)
    check("a second apply_theme() makes no new fonts", set(tkfont.names(root)) == names)
    st = ttk.Style(root)

    def family(w):
        try:
            f = str(w.cget("font"))
        except tk.TclError:
            return None
        if not f:
            f = st.lookup(str(w.cget("style")) or w.winfo_class(), "font") or st.lookup(".", "font") or "TkDefaultFont"
        return root.tk.call("font", "actual", f, "-family")

    top, app = make_app(SAMPLE_A)
    d = all_windows(app)
    ftop, ftab, fl = flim_tab()
    bad, fixed_bad, seen = [], [], 0
    numeric = ("TEntry", "TSpinbox", "Text", "Listbox")
    for win in [top, ftop] + [x.win for x in d.values()]:
        for w in walk(win):
            if in_toolbar(w):
                continue                        # matplotlib's own font
            fam = family(w)
            if fam is None:
                continue
            seen += 1
            if fam not in ("Segoe UI", "Consolas"):
                bad.append(f"{w.winfo_class()} {fam}")
            numeric_box = w.winfo_class() in numeric or (w.winfo_class() == "TLabel" and str(w.cget("style")) == "Val.TLabel")
            if numeric_box and fam != "Consolas":
                fixed_bad.append(f"{w.winfo_class()} {fam}")
    check(f"every widget with a font ({seen}) is Segoe UI or Consolas", seen > 100 and not bad, "; ".join(bad[:4]))
    check("number boxes, paths, lists, result text and value labels are Consolas", not fixed_bad, "; ".join(fixed_bad[:4]))
    ftop.destroy()
    app._close_dialogs()
    top.destroy()

# ---------------------------------------------------------------------------------------------
if section("UI-10"):
    # the role colours carry white text at 4.5:1 or more, hover and press included
    def lum(h):
        c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
    ratios = {(role, shade): (lum(NEW.ROLE_FG) + 0.05) / (lum(shade) + 0.05)
              for role, colour in NEW.ROLES.items() for shade in NEW.ROLE_SHADES[colour]}
    check("five roles, three shades each, white text", len(ratios) == 15 and NEW.ROLE_FG.lower() == "#ffffff")
    low = {k: round(v, 2) for k, v in ratios.items() if v < 4.5}
    check(f"WCAG contrast of every shade >= 4.5 (lowest {min(ratios.values()):.2f})", not low, str(low))

# ---------------------------------------------------------------------------------------------
if section("UI-11"):
    # review M1: in Global analysis, a toolbar zoom of the map, a λ click, then Home -> the whole map
    top, app = make_app(SAMPLE_A)
    app.open_global_analysis(); pump(0.6)
    g = app._global_win
    tb = g.toolbar
    full = (tuple(g.ax_data.get_xlim()), tuple(g.ax_data.get_ylim()))
    (x0, x1), (y0, y1) = full
    tb.zoom()
    drag(g.canvas, g.ax_data, (x0 + 0.3 * (x1 - x0), y0 + 0.3 * (y1 - y0)), (x0 + 0.6 * (x1 - x0), y0 + 0.6 * (y1 - y0)))
    tb.zoom()
    zoomed = (tuple(g.ax_data.get_xlim()), tuple(g.ax_data.get_ylim()))
    cx, cy = sum(zoomed[0]) / 2, sum(zoomed[1]) / 2
    event(g.canvas, "button_press_event", *at(g.ax_data, cx, cy), button=1)
    pump(0.3)
    tb.home(); pump(0.2)
    got = (tuple(g.ax_data.get_xlim()), tuple(g.ax_data.get_ylim()))
    check("Global: map zoom, λ click, Home -> the whole map",
          zoomed != full and np.allclose(np.ravel(got), np.ravel(full)), f"{got} {full}")
    g._on_close(); pump(0.1)
    top.destroy()

# ---------------------------------------------------------------------------------------------
if section("UI-12"):
    # review M3: zoom, change Bin, Home, toolbar zoom, Back -> the whole map
    top, app = make_app(SAMPLE_A)
    m, canvas, tb = app.model, app.canvas, app.toolbar
    W = lambda f: m.wl_edges[0] + f * (m.wl_edges[1] - m.wl_edges[0])
    T = lambda f: m.t_lo + f * (m.t_hi - m.t_lo)
    drag(canvas, app.ax_map, (W(0.2), T(0.2)), (W(0.6), T(0.6)))
    app.var_bin.set("32 ps"); app.apply_params(); pump(0.2)
    m = app.model
    tb.home(); pump(0.1)
    tb.zoom()
    drag(canvas, app.ax_map, (W(0.3), T(0.3)), (W(0.5), T(0.5)))
    tb.zoom()
    tb.back(); pump(0.1)
    (x0, x1), (y0, y1) = app.ax_map.get_xlim(), app.ax_map.get_ylim()
    check("zoom, Bin 32 ps, Home, toolbar zoom, Back -> the whole map, app.view None",
          app.view is None and np.allclose((min(x0, x1), max(x0, x1), min(y0, y1), max(y0, y1)),
                                           (*m.wl_edges, m.t_lo, m.t_hi)), f"{app.view} {(x0, x1, y0, y1)}")
    top.destroy()

# ---------------------------------------------------------------------------------------------
if section("UI-13"):
    # review L4: the FLIM histogram is redrawn by the hover, so it is not navigable
    ftop, ftab, v = flim_tab()
    check("FLIM: ax_hist is not navigable", not v.ax_hist.get_navigate())
    ftop.destroy()

# ---------------------------------------------------------------------------------------------
if section("UI-14"):
    # review L5: Reset zoom also puts back the decay's x, the spectrum's y and the steady-state panel
    top, app = make_app(SAMPLE_A)
    canvas, tb = app.canvas, app.toolbar

    def lims():
        return np.array([*app.ax_map.get_xlim(), *app.ax_map.get_ylim(), *app.ax_hist.get_xlim(),
                         *app.ax_spec.get_ylim(), *app.ax_ss.get_xlim(), *app.ax_ss.get_ylim()], float)
    full = lims()
    tb.zoom()
    for ax in (app.ax_hist, app.ax_spec, app.ax_ss):
        (x0, x1), (y0, y1) = ax.get_xlim(), ax.get_ylim()
        drag(canvas, ax, (x0 + 0.2 * (x1 - x0), y0 + 0.2 * (y1 - y0)), (x0 + 0.6 * (x1 - x0), y0 + 0.7 * (y1 - y0)))
    tb.zoom()
    moved = lims()
    app.reset_view(); pump(0.1)
    check("Reset zoom after zooms in the decay, spectrum and steady-state panels: every limit back",
          not np.allclose(moved, full) and np.allclose(lims(), full) and app.view is None, f"{lims()} {full}")
    top.destroy()

# ---------------------------------------------------------------------------------------------
if section("UI-15"):
    # review L6: a pan past the edge of the map keeps the width of the view
    top, app = make_app(SAMPLE_A)
    m, canvas, tb = app.model, app.canvas, app.toolbar
    W = lambda f: m.wl_edges[0] + f * (m.wl_edges[1] - m.wl_edges[0])
    T = lambda f: m.t_lo + f * (m.t_hi - m.t_lo)
    drag(canvas, app.ax_map, (W(0.4), T(0.4)), (W(0.6), T(0.6)))
    width = (app.view[1] - app.view[0], app.view[3] - app.view[2])
    tb.pan()
    drag(canvas, app.ax_map, (W(0.45), T(0.45)), (W(0.45) + 0.9 * (m.wl_edges[1] - m.wl_edges[0]), T(0.45) + 0.9 * (m.t_hi - m.t_lo)))
    tb.pan()
    v = app.view
    check("a pan far past the right / top edge: the view keeps its size, inside the map, and is the map's limits",
          v is not None and np.allclose((v[1] - v[0], v[3] - v[2]), width, rtol=1e-6)
          and v[1] <= m.wl_edges[1] + 1e-6 and v[3] <= m.t_hi + 1e-6, f"{v} {width}")
    top.destroy()

# ---------------------------------------------------------------------------------------------
if section("BG-9"):
    # review L7: the note about the shortened default survives t0 being switched on and off twice
    top, app = make_app(SAMPLE_A)
    notes = []
    for state in (True, False, True, False):
        app.var_t0.set(state); app.apply_params(); pump(0.1)
        notes.append(CLIPPED in app.var_bginfo.get())
    check("t0 on, off, on, off: the note '(ends before IRF peak)' stays each time", all(notes), str(notes))
    top.destroy()

# ---------------------------------------------------------------------------------------------
if section("UI-16"):
    # the main figure's axis labels and titles lie inside the figure and over no other panel
    for size in ("980x660", "1280x800", "1440x920"):
        top, app = make_app(SAMPLE_A, size=size + "+0+0")
        pump(0.3)
        app.canvas.draw()
        fig = app.fig
        r = app.canvas.get_renderer()
        W, H = fig.bbox.width, fig.bbox.height
        axes = [a for a in fig.axes if a.get_visible()]
        bad = []
        for ax in axes:
            for t in (ax.title, ax._left_title, ax._right_title, ax.xaxis.label, ax.yaxis.label):
                if not t.get_visible() or not t.get_text().strip():
                    continue
                b = t.get_window_extent(r)
                if b.x0 < -0.5 or b.y0 < -0.5 or b.x1 > W + 0.5 or b.y1 > H + 0.5:
                    bad.append(f"{t.get_text()!r} outside ({b.x0:.0f},{b.y0:.0f})-({b.x1:.0f},{b.y1:.0f}) "
                               f"of {W:.0f}x{H:.0f}")
                for other in axes:
                    if other is not ax and b.overlaps(other.bbox):
                        bad.append(f"{t.get_text()!r} over another panel")
        check(f"{size}: every axis label and title of the main figure inside it, over no other panel",
              not bad, "; ".join(bad[:4]))
        top.destroy()

# ---------------------------------------------------------------------------------------------
if section("UI-17"):
    # the status bar: path and file numbers on the first line, the mouse legend on the second, whole at 1440
    for size in ("980x660", "1440x920"):
        top, app = make_app(SAMPLE_A, size=size + "+0+0")
        pump(0.3)
        ws = walk(top)
        path = [w for w in ws if w.winfo_class() == "TEntry" and str(w.cget("textvariable")) == str(app.var_path)][0]
        meta = [w for w in ws if w.winfo_class() == "TLabel" and str(w.cget("textvariable")) == str(app.var_meta)][0]
        legend = [w for w in ws if w.winfo_class() == "TLabel" and str(w.cget("text")).startswith("map: drag")][0]
        line1 = path.winfo_rooty() + path.winfo_height() / 2
        check(f"{size}: the file numbers are on the path's line, the legend on a line below it",
              abs(meta.winfo_rooty() + meta.winfo_height() / 2 - line1) <= path.winfo_height() / 2
              and legend.winfo_rooty() >= path.winfo_rooty() + path.winfo_height() - 1
              and legend.winfo_ismapped(),
              f"path y {path.winfo_rooty()} meta y {meta.winfo_rooty()} legend y {legend.winfo_rooty()}")
        if size == "1440x920":
            right = top.winfo_rootx() + top.winfo_width()
            check("1440: the legend is shown whole",
                  legend.winfo_width() >= legend.winfo_reqwidth()
                  and legend.winfo_rootx() + legend.winfo_width() <= right,
                  f"{legend.winfo_width()} of {legend.winfo_reqwidth()}")
        top.destroy()

# ---------------------------------------------------------------------------------------------
if section("BG-10"):
    # the share-below-0 warning: not for a background that is almost empty (noise around a mean below one
    # count per bin is mostly below 0 after the subtraction), but still for a window that sits on the signal
    rng = np.random.default_rng(3)
    base = NEW.read_phu(SAMPLE_A)
    nb = base["nbins"]
    t = (np.arange(nb) + 0.5) * base["res_ps"]
    T = nb * base["res_ps"]

    def record(rate):
        phu = dict(base)
        phu["counts"] = rng.poisson(np.broadcast_to(rate, base["counts"].shape)).astype(base["counts"].dtype)
        return phu

    top, app = make_app(SAMPLE_A)
    cases = (("an almost empty record (0.1 count per raw bin)", np.full(nb, 0.1), False),
             ("a window on a bright first fifth of the record", np.where(t < 0.2 * T, 40.0, 2.0), True))
    for name, rate, warn in cases:
        app._show_loaded(record(rate), os.path.join(TMP, "bg10.phu")); pump(0.1)
        app.var_bg_lo.set("0"); app.var_bg_hi.set(f"{0.15 * T:.0f}"); app.apply_params(); pump(0.1)
        m = app.model
        mean = float(np.nanmean(m.bg_spec))
        shown_warning = "of the map is negative" in app.var_bginfo.get()
        check(f"{name}: background mean {mean:.2f} cts/bin, {m.neg_frac:.0%} below 0 -> "
              f"{'a' if warn else 'no'} warning",
              m.neg_frac > 0.6 and (mean >= 1.0) == warn and shown_warning == warn, app.var_bginfo.get())
    top.destroy()

# ---------------------------------------------------------------------------------------------
if section("UI-18"):
    # in the dialogs no two labels or buttons overlap, at the default and the smallest size
    def label_of(w):
        return (str(w.cget("text")) or w.winfo_class())[:30]

    def overlaps(win):
        rects = []
        for w in walk(win):
            if (w.winfo_class() in ("TLabel", "TButton") and w.winfo_ismapped() and not in_toolbar(w)
                    and w.winfo_width() > 1 and w.winfo_height() > 1):
                rects.append((w, w.winfo_rootx(), w.winfo_rooty(), w.winfo_width(), w.winfo_height()))
        out = []
        for i, (a, ax_, ay, aw, ah) in enumerate(rects):
            for b, bx, by, bw, bh in rects[i + 1:]:
                ix = min(ax_ + aw, bx + bw) - max(ax_, bx)
                iy = min(ay + ah, by + bh) - max(ay, by)
                if ix > 1 and iy > 1:
                    out.append(f"{label_of(a)!r} / {label_of(b)!r}")
        return out

    top, app = make_app(SAMPLE_A)
    for name, dlg in all_windows(app).items():
        for when in ("default", "smallest"):
            if when == "smallest":
                mw, mh = dlg.win.minsize()
                dlg.win.geometry(f"{mw}x{mh}"); pump(0.4)
            bad = overlaps(dlg.win)
            check(f"{name} at its {when} size: no two labels or buttons overlap", not bad, "; ".join(bad[:4]))
    app._close_dialogs()
    top.destroy()

# ---------------------------------------------------------------------------------------------
if section("BG-11"):
    # the share-below-0 warning goes by the sample's own background, whatever the solvent takes off it
    rng = np.random.default_rng(5)
    base = NEW.read_phu(SAMPLE_A)
    nb = base["nbins"]
    t = (np.arange(nb) + 0.5) * base["res_ps"]
    T = nb * base["res_ps"]

    def record(rate):
        phu = dict(base)
        phu["counts"] = rng.poisson(np.broadcast_to(rate, base["counts"].shape)).astype(base["counts"].dtype)
        return phu

    top, app = make_app(SAMPLE_A)
    # (sample rate, solvent rate before / after 0.2 T, per raw bin; the solvent's scale is 2 and the window lies
    #  in the first 0.15 T, so in the second case the window is level and the rest far below it)
    cases = (("a weak sample, the solvent over-scaled", 0.1, 0.02, 0.2, False),
             ("a sample of 8 cts/bin, the solvent over-scaled, the window on signal", 2.0, 1.0, 2.0, True))
    for name, sample, before, after, warn in cases:
        app._show_loaded(record(np.full(nb, sample)), os.path.join(TMP, "bg11.phu")); pump(0.1)
        m = app.model
        m.solvent, m.solvent_scale = record(np.where(t < 0.2 * T, before, after)), 2.0
        app.var_solv.set(True)
        app.var_bg_lo.set("0"); app.var_bg_hi.set(f"{0.15 * T:.0f}"); app.apply_params(); pump(0.1)
        sample_mean, taken = m.bg_sample_mean(), float(np.nanmean(m.bg_spec))
        text = app.var_bginfo.get()
        check(f"{name}: sample {sample_mean:.2f} cts/bin, after the solvent {taken:.2f}, {m.neg_frac:.0%} below 0 -> "
              f"{'a' if warn else 'no'} warning",
              m.solvent_active and m.neg_frac > 0.6 and taken < 1.0 and (sample_mean >= 1.0) == warn
              and ("of the map is negative" in text) == warn and ("solvent scale too high" in text) == warn, text)
    top.destroy()

# ---------------------------------------------------------------------------------------------
if section("BG-12"):
    # coarse bins: bg_slice() rounds up to whole bins, so the margin before the peak is at least one bin
    path = make_phu(os.path.join(TMP, "bg12.phu"), ncurves=4, nbins=4096, res=4e-12)
    phu = NEW.read_phu(path)
    t = (np.arange(4096) + 0.5) * 4.0
    counts = np.full((4, 4096), 5.0)
    counts[0] = 5e4 * np.exp(-0.5 * ((t - 7840.0) / (50.0 / (2 * np.sqrt(2 * np.log(2))))) ** 2)
    phu["counts"] = np.rint(counts).astype(phu["counts"].dtype)
    m = NEW.TRESModel(phu, build=False)
    m.rebin = 64
    m.rebuild()
    w = m.default_bg_window()
    m.bg_lo_ps, m.bg_hi_ps = w
    m.subtract_background()
    end = m.t_off_ps + m.bg_slice()[1] * m.dt_ps
    three = m.irf_peak_ps - 3 * m.irf_fwhm_ps
    check("256 ps bins, FWHM 50 ps: the window ends max(3 FWHM, one bin) before the peak",
          m.dt_ps == 256.0 and 3 * m.irf_fwhm_ps < m.dt_ps
          and np.isclose(w[1], m.irf_peak_ps - max(3 * m.irf_fwhm_ps, m.dt_ps)), f"{w} {m.irf_peak_ps} {m.irf_fwhm_ps}")
    check("... and bg_slice() ends before the peak (three widths alone would not)",
          end <= m.irf_peak_ps and math.ceil(three / m.dt_ps) * m.dt_ps > m.irf_peak_ps, f"{end} {m.irf_peak_ps}")
    m.rebin = 1
    m.rebuild()
    check("fine bins: three widths, as before", 3 * m.irf_fwhm_ps > m.dt_ps
          and np.isclose(m.default_bg_window()[1], m.irf_peak_ps - 3 * m.irf_fwhm_ps), str(m.default_bg_window()))

# ---------------------------------------------------------------------------------------------
if section("UI-19"):
    # the toolbar's Save, in three formats: the picture on screen and what the mouse uses stay as they are
    import tkinter.filedialog as tkfiledialog

    def positions(fig):
        return [tuple(ax.get_position().bounds) for ax in fig.axes]

    top, app = make_app(SAMPLE_A)
    pump(0.5)
    app.open_crop(); pump(0.6)
    real_ask = tkfiledialog.asksaveasfilename
    try:
        for name, owner in (("main window", app), ("Crop", app._crop_win)):
            fig = owner.canvas.figure
            for fmt in ("png", "pdf", "svg"):
                out = os.path.join(TMP, f"ui19_{name[:4].strip()}.{fmt}")
                tkfiledialog.asksaveasfilename = lambda **kw: out
                boxes.clear()
                before = (positions(fig), id(owner.canvas.renderer), id(getattr(owner, "_bg", None)))
                bg_before = getattr(owner, "_bg", None)
                bg_keys = sorted(bg_before) if isinstance(bg_before, dict) else None   # (Crop: one saved region)
                owner.toolbar.save_figure()
                pump(0.2)
                after = (positions(fig), id(owner.canvas.renderer), id(getattr(owner, "_bg", None)))
                check(f"{name}, Save as {fmt}: written, panels, renderer and saved background unchanged, no error",
                      os.path.getsize(out) > 1000 and before == after and not boxes and not cb_errors
                      and (bg_keys is None or sorted(owner._bg) == bg_keys), f"{boxes} {before[1:]} {after[1:]}")
    finally:
        tkfiledialog.asksaveasfilename = real_ask
    app._close_dialogs()
    top.destroy()

# ---------------------------------------------------------------------------------------------
if section("UI-20"):
    # Back and Forward restore limits only: the panels stay where the window has put them
    def positions(fig):
        return [tuple(ax.get_position().bounds) for ax in fig.axes]

    def limits(ax):
        return (*ax.get_xlim(), *ax.get_ylim())

    def back_forward(name, owner, ax, a, b):
        tb = owner.toolbar
        start = limits(ax)
        tb.zoom()
        drag(owner.canvas, ax, a, b)
        tb.zoom()
        pump(0.3)
        zoomed, place = limits(ax), positions(ax.figure)
        tb.back(); pump(0.3)
        was_back = np.allclose(limits(ax), start) and positions(ax.figure) == place
        tb.forward(); pump(0.3)
        check(f"{name}: Back and Forward give the limits back, the panels unmoved",
              not np.allclose(zoomed, start) and was_back and np.allclose(limits(ax), zoomed)
              and positions(ax.figure) == place, f"{start} {zoomed} {limits(ax)}")

    top, app = make_app(SAMPLE_A)
    pump(0.5)
    app.open_crop(); pump(0.6)
    c = app._crop_win
    (x0, x1), (y0, y1) = c.ax.get_xlim(), c.ax.get_ylim()
    back_forward("Crop", c, c.ax, (x0 + .3 * (x1 - x0), y0 + .3 * (y1 - y0)), (x0 + .6 * (x1 - x0), y0 + .6 * (y1 - y0)))
    c._on_close(); pump(0.1)
    app.open_global_analysis(); pump(0.6)
    g = app._global_win
    (x0, x1), (y0, y1) = g.ax_data.get_xlim(), g.ax_data.get_ylim()
    back_forward("Global, before a fit", g, g.ax_data, (x0 + .3 * (x1 - x0), y0 + .3 * (y1 - y0)),
                 (x0 + .6 * (x1 - x0), y0 + .6 * (y1 - y0)))
    g.run_fit()
    check("Global: the fit is done", wait(lambda: not g._running, 300) and g._last is not None, g.var_status.get())
    pump(0.8)
    (x0, x1), (y0, y1) = g.ax_kin.get_xlim(), g.ax_kin.get_ylim()
    lx0, lx1 = np.log10(x0), np.log10(x1)         # the kinetics panel opens on a log time axis
    back_forward("Global, the kinetics panel after a fit", g, g.ax_kin,
                 (10 ** (lx0 + .3 * (lx1 - lx0)), y0 + .3 * (y1 - y0)), (10 ** (lx0 + .6 * (lx1 - lx0)), y0 + .6 * (y1 - y0)))
    g._on_close(); pump(0.1)
    # main window: resized after a zoom, so the positions in the history are old ones
    m, tb = app.model, app.toolbar
    W = lambda f: m.wl_edges[0] + f * (m.wl_edges[1] - m.wl_edges[0])
    T = lambda f: m.t_lo + f * (m.t_hi - m.t_lo)
    tb.zoom()
    drag(app.canvas, app.ax_map, (W(.3), T(.3)), (W(.6), T(.6)))
    tb.zoom()
    pump(0.3)
    zoomed = limits(app.ax_map)
    top.geometry("1200x800+0+0"); pump(0.8)
    now = positions(app.fig)
    tb.back(); pump(0.5)
    check("main window, resized after a zoom: Back keeps the window's panel layout, not the history's",
          np.allclose(positions(app.fig), now, atol=5 / 800) and app.view is None, f"{positions(app.fig)} {now}")
    tb.forward(); pump(0.5)
    check("... and Forward gives the zoom back, app.view in step", np.allclose(limits(app.ax_map), zoomed)
          and app.view is not None, f"{limits(app.ax_map)} {zoomed}")
    top.destroy()

# ---------------------------------------------------------------------------------------------
if section("UI-21"):
    # a file that is read but cannot be shown leaves the BIN box as it was
    def bin_state(a):
        return dict(a._bins), a.var_bin.get(), [str(v) for v in a.cb_bin.cget("values")], str(a.cb_bin.cget("state")), a.model

    def boom(self):
        raise RuntimeError("cannot be shown")

    other = synthetic(8.0, "ui21.phu")
    real_default = NEW.TRESModel.default_bg_window
    top, app = make_app(SAMPLE_A)
    etop = tk.Toplevel(root)
    etab = ttk.Frame(etop); etab.pack(fill="both", expand=True)
    empty = NEW.TRESViewer(etab)
    pump(0.2)
    for name, a, state in (("a loaded window", app, "readonly"), ("an empty window", empty, "disabled")):
        before = bin_state(a)
        boxes.clear()
        NEW.TRESModel.default_bg_window = boom
        try:
            a.load(other); pump(0.1)
        finally:
            NEW.TRESModel.default_bg_window = real_default
        check(f"{name}: the failed load is reported; _bins, cb_bin and var_bin are as they were",
              before == bin_state(a) and before[3] == state and any("cannot be shown" in b[2] for b in boxes),
              f"{before[:4]} {bin_state(a)[:4]}")
    etop.destroy()
    top.destroy()

# ---------------------------------------------------------------------------------------------
if section("UI-22"):
    # a window closed with a draw of its new layout still queued
    top, app = make_app(SAMPLE_A)
    pump(0.3)
    app._fit_layout = lambda: True          # "the panels moved": the next draw queues another
    app.canvas.draw()
    queued = app._draw_queued
    pending = queued in root.tk.splitlist(root.tk.call("after", "info"))
    top.destroy()
    gone = queued not in root.tk.splitlist(root.tk.call("after", "info"))
    pump(0.3)
    check("the queued draw was pending, is cancelled with the window, and nothing raises",
          queued is not None and pending and gone and app._draw_queued is None and not cb_errors, str(cb_errors[-1:]))

# ---------------------------------------------------------------------------------------------
if section("UI-23"):
    # between moving the panels and the draw that shows them there is no saved background to blit on
    top, app = make_app(SAMPLE_A)
    pump(0.5)
    m, tb = app.model, app.toolbar
    W = lambda f: m.wl_edges[0] + f * (m.wl_edges[1] - m.wl_edges[0])
    T = lambda f: m.t_lo + f * (m.t_hi - m.t_lo)
    real_fit = app._fit_layout
    app._fit_layout = lambda: True
    app.canvas.draw()
    app._fit_layout = real_fit
    empty = app._bg == {} and app._layout_stale and app._draw_queued is not None
    event(app.canvas, "button_press_event", *at(app.ax_map, W(.5), T(.5)), button=1)
    check("panels just moved: no saved background, a draw queued, a press starts nothing",
          empty and app._drag is None, f"{app._bg} {app._drag}")
    pump(0.5)
    check("after the queued draw: the background is back and nothing is pending",
          bool(app._bg) and not app._layout_stale and app._draw_queued is None)
    # no fit while a pan is dragging, one after it
    calls = []
    app._fit_layout = lambda: (calls.append(1), real_fit())[1]
    tb.pan(); pump(0.1)
    p0, p1 = at(app.ax_map, W(.5), T(.5)), at(app.ax_map, W(.4), T(.45))
    event(app.canvas, "button_press_event", *p0, button=1)
    event(app.canvas, "motion_notify_event", *p1, buttons=(1,))
    dragging = tb.dragging()
    app.canvas.draw()
    during = len(calls)
    event(app.canvas, "button_release_event", *p1, button=1)
    pump(0.4)
    tb.pan()
    check("no layout fit during a pan drag, one after the release", dragging and during == 0 and len(calls) >= 1,
          f"{dragging} {during} {len(calls)}")
    del app._fit_layout
    # a linear colour bar with large numbers has an offset text above it (x 1e6)
    tb.home(); pump(0.3)
    app.var_log.set(False)
    app.clim = (0.0, 5e6)
    app._recolor(); pump(0.6)
    app.canvas.draw(); pump(0.4)
    off = app.cax.yaxis.offsetText
    r = app.canvas.get_renderer()
    e, title = off.get_window_extent(r), app.ax_map._left_title.get_window_extent(r)
    check("linear colour bar above 1e6: its offset text is inside the figure, off the title, in the top margin",
          off.get_text() != "" and e.y1 <= app.fig.bbox.height and e.x1 <= app.fig.bbox.width
          and not e.overlaps(title) and app._over["cax"][3] >= e.y1 - app.cax.bbox.y1 - 1,
          f"{off.get_text()!r} {e} {app._over['cax']}")
    top.destroy()

# ---------------------------------------------------------------------------------------------
if section("FLIM"):
    ftop, ftab, v = flim_tab()
    tb = v.toolbar
    check("Process green (Run.TButton); Open file grey",
          style(v.process_btn) == "Run.TButton" and style(button_of(ftop, "Open file...")) == "")
    check("groups Compute device / Image size", groups_of(ftop) == ["Compute device", "Image size"], str(groups_of(ftop)))
    spins = [w for w in walk(ftab) if isinstance(w, ttk.Spinbox)]
    check("Nx / Ny / N_bins are number boxes", len(spins) == 3 and {str(s.cget("textvariable")) for s in spins}
          == {str(v.nx_var), str(v.ny_var), str(v.nbins_var)})
    sb = [s for s in spins if str(s.cget("textvariable")) == str(v.nx_var)][0]
    sb.event_generate("<<Increment>>"); pump(0.4)
    check("Nx +1, and not applied until Apply size", v.nx_var.get() == NEW.NX_DEFAULT + 1 and v.cur_nx == NEW.NX_DEFAULT,
          f"{v.nx_var.get()} {v.cur_nx}")
    v.nx_var.set(1); sb.event_generate("<<Decrement>>"); pump(0.1)
    check("Nx stops at 1", v.nx_var.get() == 1)
    v.nx_var.set(NEW.NX_DEFAULT)
    check("980x660: no control squeezed", not squeezed(ftop), "; ".join(squeezed(ftop)[:3]))
    v.hist = np.random.default_rng(0).integers(0, 5, (32, 32, 64)).astype(np.uint32)
    v.intensity = NEW.compute_intensity(v.hist)
    v.lifetime, v.peak_bin = NEW.compute_lifetime_map(v.hist)
    v._draw_images(); pump(0.3)
    check("after drawing the images the history holds one base view", len(tb._nav_stack) == 1)

    def hover():
        event(v.canvas, "motion_notify_event", *at(v.ax_int, 5.2, 7.1))
    v.ax_hist.set_title("x"); hover()
    check("hover draws the pixel's histogram", "x=5" in v.ax_hist.get_title(), v.ax_hist.get_title())
    tb.zoom(); pump(0.05)
    v.ax_hist.set_title("x"); hover()
    check("... also in zoom mode", "x=5" in v.ax_hist.get_title(), v.ax_hist.get_title())
    p = at(v.ax_int, 10, 10)
    event(v.canvas, "button_press_event", *p, button=1)
    check("a zoom drag is under way", tb.dragging())
    v.ax_hist.set_title("x"); hover()
    check("... and while it is, hovering does not redraw the histogram", v.ax_hist.get_title() == "x")
    event(v.canvas, "button_release_event", *p, button=1)
    tb.zoom(); pump(0.05)
    ftop.destroy()

finish()
