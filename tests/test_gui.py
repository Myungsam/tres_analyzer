"""GUI checks for the solvent subtraction (real Tk widgets, no mainloop). US-002."""
import copy
import os
import sys
import tempfile
import time
import traceback

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = tempfile.mkdtemp(prefix="tcspc_gui_")       # what the exports of this test write
sys.path.insert(0, ROOT)
sys.dont_write_bytecode = True
import tkinter as tk                          # noqa: E402
from tkinter import ttk                       # noqa: E402
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _versions                              # noqa: E402
NEW = _versions.load()
OLD = _versions.load("1.0")
# These checks compare with an older version: the rules 1.6 changed on purpose are put back
# (see _versions.rules_of_1_5; the changes themselves are tested in test_g7.py / test_g8.py).
_versions.rules_of_1_5(NEW)

SAMPLE_A = _versions.samples()[0]
SAMPLE_B = _versions.samples()[1]

fails, cb_errors, boxes = [], [], []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail else ""))
    if not ok:
        fails.append(name)


def eq(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    return a.shape == b.shape and np.array_equal(a, b, equal_nan=True)


# ---- intercept dialogs ------------------------------------------------------
for mod in (NEW, OLD):
    for kind in ("showerror", "showwarning", "showinfo"):
        setattr(mod.messagebox, kind,
                lambda title="", msg="", _k=kind, **kw: boxes.append((_k, title, msg, kw)))
next_open = {"path": ""}
next_save = {"path": ""}
NEW.filedialog.askopenfilename = lambda **kw: next_open["path"]
NEW.filedialog.asksaveasfilename = lambda **kw: next_save["path"]
# B-8 (1.6): the program now asks before replacing the files of an earlier run of this test
NEW.messagebox.askyesno = lambda *a, **k: True

real_read = NEW.read_phu
SAMPLE = real_read(SAMPLE_A)


def fake_read(path):
    if path == "SOLV":            # same grid, different counts
        d = copy.copy(SAMPLE)
        d["counts"] = (SAMPLE["counts"][::-1].astype(np.uint64) // 3).astype(np.uint32)
        d["path"] = r"C:\somewhere\solvent_blank_measured_2026-09-30_long_name.phu"
        return d
    if path == "SOLV_ACQ":        # same grid, other acquisition time
        d = fake_read("SOLV")
        d["acq_ms"] = (SAMPLE["acq_ms"] or 1000) * 2
        d["path"] = r"C:\somewhere\blank8s.phu"
        return d
    if path == "SELF":
        d = copy.copy(SAMPLE)
        d["path"] = r"C:\somewhere\self.phu"
        return d
    if path == "BAD":
        raise ValueError("Not a PicoQuant histogram file (test).")
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


def build(mod, width):
    top = tk.Toplevel(root)
    top.geometry(f"{width}x700+0+0")
    tab = ttk.Frame(top)
    tab.pack(fill="both", expand=True)
    app = mod.TRESViewer(tab, SAMPLE_A)
    pump(0.3)
    return top, tab, app


def rows_of(tab):
    return [c for c in tab.winfo_children() if c.winfo_class() == "TFrame"]


def snapshot(frame):
    out = []
    for w in frame.winfo_children():
        try:
            text = "" if w.winfo_class() == "TEntry" else w.cget("text")
        except tk.TclError:
            text = ""
        out.append((w.winfo_class(), str(text), w.winfo_ismapped(), w.winfo_width(),
                    w.winfo_reqwidth()))
    return out


# ---- layout: row 2 unchanged vs the backup, row 3 fully visible ------------
layout_ok, row3_ok = True, True
old_note = None
for width in (980, 1440):
    top_o, tab_o, app_o = build(OLD, width)
    snap_old = snapshot(rows_of(tab_o)[2])
    if old_note is None:
        old_note = app_o._export_note()
        app_o.open_crop()
        pump(0.2)
        old_heat = app_o._crop_win._base_im.get_array()
        old_heat = (np.ma.getdata(old_heat).copy(), np.ma.getmaskarray(old_heat).copy())
        app_o._crop_win._on_close()
    top_o.destroy()
    pump(0.1)

    top_n, tab_n, app_n = build(NEW, width)
    rows = rows_of(tab_n)
    # B-2 (1.6): the rows are file / pop-up buttons / controls / background / solvent. The background
    # row is no longer the 1.0 one (it was wider than the window): every control of it must be shown in
    # full, only the info text that ends the row may be cut in a narrow window. The solvent row ends
    # with the file's info line, which may be cut as well.
    snap_new = snapshot(rows[3])
    layout_ok &= all(m and w == rw for _, _, m, w, rw in snap_new[:-1]) and snap_new[-1][0] == "TLabel"
    if not layout_ok:
        print("  background row at", width, snap_new)
    r3 = snapshot(rows[4])
    row3_ok &= len(rows) == 5 and all(m and w == rw for _, _, m, w, rw in r3[:2])
    if width == 980:
        print("  solvent row @980:", r3)
    if width == 1440:
        break
    top_n.destroy()
    pump(0.1)

check("background row: every control fully visible at 980 and 1440", layout_ok)
check("solvent row (Subtract solvent + label) fully visible at 980 and 1440", row3_ok)

app, top = app_n, top_n
m0 = app.model
check("export note without solvent equals the backup's", app._export_note() == old_note)
check("checkbox disabled, label says no solvent",
      str(app.chk_solv.cget("state")) == "disabled" and not app.var_solv.get()
      and app.var_solvinfo.get() == app.NO_SOLVENT)

# ---- Crop window, no solvent ------------------------------------------------
app.open_crop()
pump(0.3)
dlg = app._crop_win


def texts(widget, acc=None):
    acc = [] if acc is None else acc
    for w in widget.winfo_children():
        try:
            acc.append((w.winfo_class(), str(w.cget("text"))))
        except tk.TclError:
            pass
        texts(w, acc)
    return acc


labels = texts(dlg.win)
check("Crop window has Load solvent / Clear buttons",
      ("TButton", "Load solvent...") in labels and ("TButton", "Clear") in labels)
check("no solvent: name 'none', SCALE widgets disabled",
      dlg.var_solv_name.get() == "none" and dlg.scale.instate(["disabled"])
      and str(dlg.ent_scale.cget("state")) == "disabled")
heat = dlg._base_im.get_array()
check("no solvent: heatmap identical to the backup's Crop window",
      np.array_equal(np.ma.getmaskarray(heat), old_heat[1])
      and np.array_equal(np.ma.getdata(heat)[~old_heat[1]], old_heat[0][~old_heat[1]]))
lines = dlg.ax_ss.get_lines()
named = [ln.get_label() for ln in (dlg.ln_sample, dlg.ln_solv, dlg.ln_sub)]
check("steady-state panel has the three lines",
      named == ["sample", "s x solvent", "subtracted"] and all(
          ln in lines for ln in (dlg.ln_sample, dlg.ln_solv, dlg.ln_sub)))
check("no solvent: only 'sample' shown and it equals the main steady state",
      dlg.ln_sample.get_visible() and not dlg.ln_solv.get_visible()
      and not dlg.ln_sub.get_visible()
      and eq(dlg.ln_sample.get_ydata(), app.model.spec_total))

dlg.win.geometry("780x680")
pump(0.3)
srow = [c for c in dlg.win.winfo_children() if c.winfo_class() == "TFrame"][1]
s_snap = snapshot(srow)
check("Crop solvent row fully visible at the minimum width 780",
      all(mm and w == rw for _, _, mm, w, rw in s_snap), str([(c, t, w, rw) for c, t, _, w, rw in s_snap]))
dlg.win.geometry("1000x920")
pump(0.2)


def state():
    return (dlg._solvent, dlg._scale, dlg.var_solv_name.get(), dlg.var_scale.get())


# ---- refusals ----------------------------------------------------------------
before = state()
boxes.clear(); next_open["path"] = ""
dlg._load_solvent()
check("cancelled file dialog changes nothing", state() == before and not boxes)

boxes.clear(); next_open["path"] = SAMPLE_B
dlg._load_solvent()
check("grid mismatch: showerror names the difference, state unchanged",
      len(boxes) == 1 and boxes[0][0] == "showerror" and "curves" in boxes[0][2]
      and boxes[0][3].get("parent") is dlg.win and state() == before, boxes[0][2] if boxes else "")

boxes.clear(); next_open["path"] = "BAD"
dlg._load_solvent()
check("unreadable file: showerror, state unchanged",
      len(boxes) == 1 and boxes[0][0] == "showerror" and state() == before)

# ---- accept -------------------------------------------------------------------
boxes.clear(); next_open["path"] = "SOLV"
E_main = app.model.E.copy()
dlg._load_solvent()
pump(0.1)
check("matching solvent accepted without a message box", dlg._solvent is not None and not boxes)
check("file name label shows the (shortened) name, SCALE enabled",
      dlg.var_solv_name.get() == "solvent_blank_measure..." and len(dlg.var_solv_name.get()) == 24
      and dlg.scale.instate(["!disabled"]) and str(dlg.ent_scale.cget("state")) == "normal")
leg = dlg.ax_ss.get_legend()
check("legend lists sample / s x solvent / subtracted",
      [t.get_text() for t in leg.get_texts()] == ["sample", "s x solvent", "subtracted"]
      and dlg.ln_solv.get_visible() and dlg.ln_sub.get_visible())

# ---- slider <-> entry ----------------------------------------------------------
sub_1 = np.array(dlg.ln_sub.get_ydata(), float).copy()
solv_1 = np.array(dlg.ln_solv.get_ydata(), float).copy()
heat_1 = np.ma.getdata(dlg._base_im.get_array()).copy()
dlg.scale.set(0.5)
check("slider -> scale and entry", dlg._scale == 0.5 and dlg.var_scale.get() == "0.5")
check("slider move is debounced (nothing redrawn yet)",
      eq(dlg.ln_sub.get_ydata(), sub_1) and dlg._after is not None)
pump(0.35)
sub_05 = np.array(dlg.ln_sub.get_ydata(), float).copy()
check("after the debounce: subtracted / solvent lines and heatmap changed, no Apply",
      not eq(sub_05, sub_1) and not eq(dlg.ln_solv.get_ydata(), solv_1)
      and not np.array_equal(np.ma.getdata(dlg._base_im.get_array()), heat_1))
check("s x solvent line scales with s", np.allclose(np.array(dlg.ln_solv.get_ydata(), float) * 2,
                                                   solv_1, equal_nan=True))
check("live model untouched by the preview",
      app.model.solvent is None and eq(app.model.E, E_main))

dlg.var_scale.set("3.5"); dlg._on_scale_entry()
check("entry 3.5 is used, slider parks at 2",
      dlg._scale == 3.5 and abs(float(dlg.scale.get()) - 2.0) < 1e-9 and dlg.var_scale.get() == "3.5")
for bad in ("abc", "-1", "inf", "nan", ""):
    dlg.var_scale.set(bad); dlg._on_scale_entry()
    check(f"entry {bad!r} is put back", dlg._scale == 3.5 and dlg.var_scale.get() == "3.5")
dlg.var_scale.set("1.5"); dlg._on_scale_entry()
check("entry 1.5 moves the slider", dlg._scale == 1.5 and abs(float(dlg.scale.get()) - 1.5) < 1e-9)

# ---- acquisition-time warning ---------------------------------------------------
boxes.clear(); next_open["path"] = "SOLV_ACQ"
dlg._load_solvent()
acq_s = (SAMPLE["acq_ms"] or 1000) / 1000
check("acq-time difference: showwarning with both times, accepted, scale back to 1",
      len(boxes) == 1 and boxes[0][0] == "showwarning"
      and f"{acq_s * 2:g} s" in boxes[0][2] and f"{acq_s:g} s" in boxes[0][2]
      and dlg._solvent["path"].endswith("blank8s.phu") and dlg._scale == 1.0
      and dlg.var_scale.get() == "1", boxes[0][2].replace("\n", " / ") if boxes else "")

# ---- Apply == preview, over setting combinations ---------------------------------
boxes.clear(); next_open["path"] = "SOLV"
dlg._load_solvent()
dlg.var_scale.set("0.8"); dlg._on_scale_entry()


def apply_and_compare(tag):
    dlg._update_overlay()
    want = np.array(dlg.ln_sub.get_ydata(), float).copy()
    wl = np.array(dlg.ln_sub.get_xdata(), float).copy()
    dlg._apply()
    pump(0.05)
    m = app.model
    ok = eq(m.spec_total, want) and eq(m.wls, wl) and m.solvent_active \
        and m.solvent_scale == 0.8
    check(f"Apply == preview 'subtracted' ({tag})", ok,
          f"below 0 {m.neg_frac:.0%}, {m.n_w}x{m.n_t}")


apply_and_compare("default settings")
check("after Apply: checkbox enabled and ticked, label shows scale + file",
      str(app.chk_solv.cget("state")) == "normal" and app.var_solv.get()
      and app.var_solvinfo.get().startswith("x0.8  solvent_blank_measure...")
      and "of bins below 0" in app.var_solvinfo.get(), app.var_solvinfo.get())

# the Mask window rebuilds the model on its own: the share of bins below 0 in the
# main label has to follow (it did not before redraw() synced it). Since A-9 (1.6)
# the label gives that share; up to 1.5 it was the share cut to 0.
app.open_mask(); pump(0.2)
md = app._mask_win
lab0 = app.var_solvinfo.get()
w0 = app.model.wls
md.var_lo.set(f"{float(w0[2]):g}"); md.var_hi.set(f"{float(w0[9]):g}"); md._add(); pump(0.05)
lab1 = app.var_solvinfo.get()
check("Mask window: the share in the main label is that of the masked model",
      f"({app.model.neg_frac:.0%} of bins below 0)" in lab1, f"{lab0!r} -> {lab1!r}")
md._clear(); pump(0.05)
check("Mask window: clearing the mask restores the label", app.var_solvinfo.get() == lab0)
md._on_close()

app.var_t0.set(True); app.apply_params(); pump(0.05)
apply_and_compare("t0 at IRF peak")
app.var_bg_lo.set("300"); app.var_bg_hi.set("900"); app.apply_params(); pump(0.05)
apply_and_compare("background window moved")
w = app.model.wls
app.model.masks.append((float(w[8]), float(w[11]))); app.model.rebuild(); app.redraw(full=True)
apply_and_compare("with a wavelength mask")
dlg.var_wl_lo.set(f"{dlg.wl_full[0] + 40:g}"); dlg.var_wl_hi.set(f"{dlg.wl_full[1] - 60:g}")
dlg.var_t_lo.set("1000"); dlg.var_t_hi.set("9000")
apply_and_compare("wavelength + time crop")
app.var_bin.set("64 ps"); app.apply_params(); pump(0.05)
apply_and_compare("BIN 64 ps")
app.var_bgsub.set(False); app.apply_params(); pump(0.05)
apply_and_compare("background subtraction off")

# ---- main-window toggle -------------------------------------------------------------
E_on = app.model.E.copy()
ref = NEW.TRESModel(app.model.phu); ref.copy_settings_from(app.model)
ref.solvent = None; ref.solvent_sub = False; ref.rebuild()
app.var_solv.set(False); app.apply_params(); pump(0.05)
check("unticking shows the unsubtracted data again",
      not app.model.solvent_sub and eq(app.model.E, ref.E) and not eq(app.model.E, E_on)
      and "clipped" not in app.var_solvinfo.get() and "solvent" not in app._export_note())
app.var_solv.set(True); app.apply_params(); pump(0.05)
check("ticking brings the subtracted data back",
      app.model.solvent_active and eq(app.model.E, E_on))

# ---- consumers: export + fits -----------------------------------------------------
note = app._export_note()
check("export note names the solvent file and the scale",
      "solvent subtracted x0.8 (solvent_blank_measured_2026-09-30_long_name.phu)" in note
      and "clipped" not in note, note)
wls, times, Z = app._map_arrays_full()
check("_map_arrays_full returns the subtracted map", eq(Z, app.model.E.T))
p_map, p_ss = os.path.join(OUT_DIR, "t_TRESmap.csv"), os.path.join(OUT_DIR, "t_steady.csv")
app._write_map_csv(p_map, wls, times, Z)
app._write_steady_state_csv(p_ss)
head = lambda p: "".join(l for l in open(p, encoding="utf-8") if l.startswith("#"))
check("map CSV and steady-state CSV preambles carry the solvent line",
      all("solvent subtracted x0.8 (solvent_blank_measured_2026-09-30_long_name.phu)" in head(p)
          for p in (p_map, p_ss)))

app.open_kinetics(); pump(0.2)
kd = app._kinetics_win


def wait_fit(dlg, limit=120):
    end = time.time() + limit
    pump(0.05)
    while dlg._running and time.time() < end:
        pump(0.05)
    pump(0.1)


t, y, wl_k, n_avg = kd._get_trace()
wi = int(np.argmin(np.abs(app.model.wls - wl_k)))
check("Kinetics reads the subtracted trace", eq(y, app.model.E[wi, :]))
try:
    import scipy  # noqa: F401
    have_scipy = True
except ImportError:
    have_scipy = False
if have_scipy:
    kd.var_n.set("1"); kd.table.set_n(1); kd.run_fit(); wait_fit(kd)
    check("Kinetics fit runs on the subtracted data", kd._last is not None,
          str([b[2] for b in boxes if b[0] != "showinfo"]))
    app.var_out_csv.set(True); app.var_out_opju.set(False)
    next_save["path"] = os.path.join(OUT_DIR, "t_fit.csv")
    kd.export_results(); pump(0.1)
    kin_csv = os.path.join(OUT_DIR, "t_fit_kinetics.csv")
    check("Kinetics CSV preamble carries the solvent line",
          os.path.exists(kin_csv) and "solvent subtracted x0.8" in head(kin_csv))

    app.open_global_analysis(); pump(0.2)
    gd = app._global_win
    gd.var_n.set("1"); gd.table.set_n(1); gd.run_fit()
    t_end = time.time() + 120
    while gd._running and time.time() < t_end:
        pump(0.1)
    tsel = np.isin(app.model.times, gd._fit_t)
    D_ref = app.model.E[:, tsel]
    D_ref = D_ref[~np.isnan(D_ref).any(axis=1)]
    check("Global analysis fitted the subtracted map",
          not gd._running and gd._last is not None and tsel.sum() >= app.model.n_t - 2
          and eq(gd._fit_D, D_ref),
          str([b[2] for b in boxes if b[0] == "showerror"]))
    gd.export_results(); pump(0.1)
    dads = os.path.join(OUT_DIR, "t_fit_DADS.csv")
    check("DADS CSV preamble carries the solvent line",
          os.path.exists(dads) and "solvent subtracted x0.8" in head(dads))
    # switched off: the fit-result preamble is as before (no solvent line)
    app.var_solv.set(False); app.apply_params(); pump(0.05)
    kd._on_wl_change(); kd.run_fit(); wait_fit(kd)
    next_save["path"] = os.path.join(OUT_DIR, "t_off.csv")
    kd.export_results(); pump(0.1)
    check("switched off: Kinetics CSV has no solvent line",
          "solvent" not in head(os.path.join(OUT_DIR, "t_off_kinetics.csv")))
    app.var_solv.set(True); app.apply_params(); pump(0.05)
    gd._on_close()
else:
    print("SKIP scipy not installed - fit runs and fit-result CSVs not exercised")
kd._on_close()

# ---- Reset (full) must not commit an unapplied solvent ------------------------------
dlg._clear_solvent(); dlg._apply(); pump(0.05)
check("Clear + Apply removes the solvent from the live model, checkbox disabled",
      app.model.solvent is None and not app.model.solvent_sub
      and str(app.chk_solv.cget("state")) == "disabled" and not app.var_solv.get())
next_open["path"] = "SOLV"; dlg._load_solvent(); dlg.var_scale.set("0.6"); dlg._on_scale_entry()
dlg._reset(); pump(0.05)
check("Reset (full) resets the crop but leaves the unapplied solvent a preview",
      app.model.solvent is None and app.model.crop_wl is None and app.model.t_min_ps == 0.0
      and dlg._solvent is not None and dlg._scale == 0.6)

# ---- self subtraction at s = 1: everything zero, redraw must survive -----------------
next_open["path"] = "SELF"; dlg._load_solvent(); dlg._apply(); pump(0.2)
fin = np.isfinite(app.model.E)
check("self subtraction s=1: E all zero, vmax 1, full redraw without error",
      bool((app.model.E[fin] == 0).all()) and app.model.vmax == 1.0 and not cb_errors,
      cb_errors[0][-300:] if cb_errors else "")

# ---- reopening the Crop window keeps the unsubtracted colour scale -------------------
exp = NEW.TRESModel(app.model.phu)
exp.first_is_irf, exp.rebin, exp.wl_offset = app.model.first_is_irf, app.model.rebin, app.model.wl_offset
exp.bg_sub = exp.t0_align = False
exp.rebuild()
vmax0 = exp.vmax
dlg._on_close(); pump(0.1)
app.open_crop(); pump(0.3)
dlg = app._crop_win
check("reopened Crop window: solvent + scale restored, colour scale from the raw map",
      dlg._solvent is app.model.solvent and dlg._scale == 1.0 and dlg._vmax0 == vmax0
      and vmax0 > 1.0 and dlg._full.vmax == 1.0 and dlg.var_solv_name.get() == "self.phu",
      f"{dlg._vmax0} vs {vmax0}, full.vmax {dlg._full.vmax}, {dlg.var_solv_name.get()}")

# ---- a pending debounce must not fire into a closed window -----------------------------
dlg.scale.set(0.3)
pending = dlg._after is not None
app.load(SAMPLE_B)                       # closes the Crop window, drops the solvent
pump(0.4)
check("new sample: solvent dropped, checkbox disabled, Crop window closed",
      app.model.solvent is None and not app.model.solvent_sub and not dlg.alive
      and str(app.chk_solv.cget("state")) == "disabled"
      and app.var_solvinfo.get() == app.NO_SOLVENT and pending)

check("no Tk callback exception during the whole run", not cb_errors,
      cb_errors[0][-600:] if cb_errors else "")
errs = [b for b in boxes if b[0] == "showerror" and "Solvent" not in b[1] and "read" not in b[1]]
check("no unexpected error boxes", not errs, str(errs))

top.destroy()
root.destroy()
print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(1 if fails else 0)
