"""Stage 3, group G8: preprocessing and export changes that alter results or exported files (review items
C-9, C-5, A-9, B-5 / C-14, B-19, B-20, Q-2). See _harness.py."""
import os
import shutil
import warnings

import numpy as np

from _harness import *                        # noqa: F401,F403
from _harness import NEW, OLD, SAMPLE_A, TMP, boxes, cb_errors, check, finish, make_app, pump, section, wait


def exported(dialog):
    """What export_results hands to the main window, written out: {suffix: lines of its CSV}."""
    got = {}
    real = dialog.app.export_analysis

    def fake(base, items, **kw):
        for it in items:
            path = os.path.join(TMP, f"{base}_{it['suffix']}.csv")
            it["csv"](path)
            got[it["suffix"]] = open(path, encoding="utf-8").read().splitlines()
    dialog.app.export_analysis = fake
    try:
        dialog.export_results()
    finally:
        dialog.app.export_analysis = real
    return got


def notes(lines):
    return [ln for ln in lines if ln.startswith("#")]


def run(dialog, limit=120):
    dialog.run_fit()
    wait(lambda: not dialog._running, limit)
    pump(0.3)
    return dialog._last


# ---------------------------------------------------------------------------------------------
if section("C-9"):
    top, app = make_app(SAMPLE_A)
    app.open_kinetics(); app.open_global_analysis(); pump(0.4)
    k, g = app._kinetics_win, app._global_win
    k.var_tmin.set("3000"); k.var_tmax.set("15000")
    g.var_n.set("2"); g.table.set_n(2); g.var_tmin.set("3000"); g.var_tmax.set("15000"); g._update_tcount()
    run(k); run(g)
    note_then = app._export_note()
    kin, glo = exported(k)["kinetics"], exported(g)
    check("Kinetics CSV, no solvent: the settings line of the main window is in the preamble",
          f"# {note_then}" in notes(kin), str(notes(kin))[-300:])
    check("Kinetics CSV: the fit range and what was fixed are in the preamble",
          any("fit range = 3000 to 15000 ps" in ln and "fixed:" in ln and "t0" in ln and "FWHM" in ln
              for ln in notes(kin)), str(notes(kin))[-300:])
    for kind in ("DADS", "EADS"):
        check(f"{kind} CSV: settings line, fit range and fixed flags",
              f"# {note_then}" in notes(glo[kind])
              and any("fit range = 3000 to 15000 ps" in ln and "fixed: t0, FWHM" in ln for ln in notes(glo[kind])),
              str(notes(glo[kind]))[-300:])
    check("the data line and header follow the preamble unchanged", kin[len(notes(kin))] == "delay_ps,data,fit,residual"
          and glo["DADS"][len(notes(glo["DADS"]))].startswith("wavelength_nm,DADS_"))
    n_fit = len(kin) - len(notes(kin)) - 1
    # now the main window changes: another bin width, no background subtraction
    app.var_bin.set("64 ps"); app.var_bgsub.set(False); app.apply_params(); pump(0.5)
    note_now = app._export_note()
    check("(the main window's settings line is another one now)", note_now != note_then, note_now)
    check("Kinetics says that its result is of older data", "changed after this fit" in k.var_status.get(), k.var_status.get())
    check("Global says so too", "changed after this fit" in g.var_status.get(), g.var_status.get())
    kin2, glo2 = exported(k)["kinetics"], exported(g)
    check("exported afterwards, the Kinetics file still carries the settings it was fitted with",
          f"# {note_then}" in notes(kin2) and f"# {note_now}" not in notes(kin2)
          and len(kin2) - len(notes(kin2)) - 1 == n_fit, str(notes(kin2))[-300:])
    check("... and so do DADS / EADS",
          all(f"# {note_then}" in notes(glo2[x]) and f"# {note_now}" not in notes(glo2[x]) for x in ("DADS", "EADS")))
    res = run(k)
    check("a new fit is of the data as it is now: no such remark, the new settings line in its export",
          "changed after this fit" not in k.var_status.get() and f"# {note_now}" in notes(exported(k)["kinetics"]),
          k.var_status.get())
    # a change made by another window (Crop / Mask do not go through the main window's controls)
    app.model.masks = [(600.0, 620.0)]; app.model.rebuild(); app.redraw(full=True); pump(0.5)
    check("a mask applied meanwhile is noticed as well", "changed after this fit" in k.var_status.get(), k.var_status.get())
    # a change while the fit runs
    g.run_fit()
    app.model.masks = []; app.model.rebuild(); app.redraw(full=True)
    wait(lambda: not g._running, 120); pump(0.4)
    check("the data changing while a Global fit runs: the result is shown with the remark",
          g._last is not None and "changed after this fit" in g.var_status.get(), g.var_status.get())
    check("no error box", not [b for b in boxes if b[0] == "showerror"], str(boxes))
    top.destroy()

# ---------------------------------------------------------------------------------------------
if section("C-5"):
    top, app = make_app(SAMPLE_A)
    m = app.model
    solvent = dict(m.phu)
    solvent["counts"] = (m.phu["counts"] * 0.3).astype(m.phu["counts"].dtype)
    solvent["path"] = os.path.join(TMP, "solvent.phu")
    app.open_crop(); pump(0.4)
    c = app._crop_win
    c._solvent = solvent; c._sync_solvent_controls(); c._set_scale(0.5); c._update_overlay(); pump(0.2)
    c._apply(); pump(0.4)
    check("(a solvent applied from the Crop window is subtracted)", m.solvent_sub and app.var_solv.get())
    total_on = float(np.nansum(m.E))
    app.var_solv.set(False); app.apply_params(); pump(0.4)
    total_off = float(np.nansum(m.E))
    check("(switched off in the main window: the sum of the map goes up again)",
          not m.solvent_sub and total_off > 1.05 * total_on, f"{total_on:.4g} {total_off:.4g}")
    c._on_close(); pump(0.2)
    app.open_crop(); pump(0.4)
    c = app._crop_win
    check("reopened, the Crop window says that the subtraction is off",
          "off in the main window" in c.var_info.get(), c.var_info.get())
    c.var_t_hi.set("15000"); c._update_overlay(); pump(0.2)
    c._apply(); pump(0.4)
    check("Apply with only the time range changed: the subtraction stays off",
          not m.solvent_sub and not app.var_solv.get() and abs(m.t_max_ps - 15000) < 20
          and m.solvent is solvent and m.solvent_scale == 0.5,
          f"sub={m.solvent_sub} box={app.var_solv.get()} t_max={m.t_max_ps}")
    check("... and the main window does not report clipped bins", "clipped" not in app.var_solvinfo.get(),
          app.var_solvinfo.get())
    c._reset(); pump(0.3)
    check("Reset (full) leaves it off as well", not m.solvent_sub)
    c._set_scale(0.8); c._update_overlay(); pump(0.2)
    check("with the scale changed here the note is gone (it is a new subtraction to apply)",
          "off in the main window" not in c.var_info.get() and "of bins" in c.var_info.get(), c.var_info.get())
    c._apply(); pump(0.4)
    check("Apply after changing the scale here: the subtraction is on, with the new scale",
          m.solvent_sub and app.var_solv.get() and m.solvent_scale == 0.8, f"{m.solvent_sub} {m.solvent_scale}")
    c._apply(); pump(0.3)
    check("Apply again with it on: stays on", m.solvent_sub)
    c._clear_solvent(); c._apply(); pump(0.3)
    check("Clear + Apply: no solvent, nothing subtracted", m.solvent is None and not m.solvent_sub)
    check("no error box", not [b for b in boxes if b[0] == "showerror"], str(boxes))
    top.destroy()

# ---------------------------------------------------------------------------------------------
def export_names(app, folder, base, csv=True, opju=True):
    """(names of the CSV files written, stem handed to the .opju step) of one "Export data..."."""
    seen = {}
    real_save, real_ask = NEW.filedialog.asksaveasfilename, app._ask_opju_path
    NEW.filedialog.asksaveasfilename = lambda **kw: os.path.join(folder, base + ".csv")
    app._ask_opju_path = lambda stem: seen.setdefault("stem", stem) and None    # stop before Origin
    app.var_out_csv.set(csv); app.var_out_opju.set(opju)
    before = set(os.listdir(folder))
    try:
        app.export_data(); pump(0.1)
    finally:
        NEW.filedialog.asksaveasfilename, app._ask_opju_path = real_save, real_ask
    return sorted(set(os.listdir(folder)) - before), seen.get("stem")


if section("B-19"):
    strip = NEW.TRESViewer._strip_export_suffix
    check("only a whole _TRESmap / _steadystate is taken off a base name",
          [strip(n) for n in ("run_TRESmap", "run_steadystate", "RUN_tresMAP", "sample_TRES", "my_steady", "plain")]
          == ["run", "run", "RUN", "sample_TRES", "my_steady", "plain"],
          str([strip(n) for n in ("run_TRESmap", "run_steadystate", "RUN_tresMAP", "sample_TRES", "my_steady", "plain")]))
    for name, want in (("sample_TRES", "sample_TRES"), ("my_steady", "my_steady"), ("old_TRESmap", "old")):
        folder = os.path.join(TMP, "b19_" + name); os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, name + ".phu")
        shutil.copyfile(SAMPLE_A, path)
        top, app = make_app(path)
        _, stem_both = export_names(app, folder, name, csv=True, opju=True)
        _, stem_opju = export_names(app, folder, name, csv=False, opju=True)
        files, _ = export_names(app, folder, name, csv=True, opju=False)
        check(f"{name}.phu: the CSV files are {want}_TRESmap.csv and {want}_steadystate.csv",
              files == [f"{want}_TRESmap.csv", f"{want}_steadystate.csv"], str(files))
        check(f"{name}.phu: the .opju tabs get the same stem with and without CSV ticked",
              stem_both == stem_opju == want, f"{stem_both!r} {stem_opju!r}")
        top.destroy()

# ---------------------------------------------------------------------------------------------
if section("Q-2"):
    class Sheet:
        def __init__(self):
            self.labels, self.columns = {}, {}

        def clear(self):
            pass

        def from_list(self, col, data, *a, **k):
            self.columns[col] = list(data)

        def set_label(self, col, text, kind):
            self.labels[(col, kind)] = text

    ws = Sheet()
    NEW._origin_fill_steady(ws, np.array([500.0, 505.0]), np.array([10.0, 20.0]), np.array([0.5, 1.0]),
                            "run_steadystate")
    check("Origin steady-state sheet: the Counts column has the unit 'counts' (it said 'nm')",
          ws.labels[(1, "L")] == "Counts" and ws.labels[(1, "U")] == "counts", str(ws.labels[(1, "U")]))
    check("... the other two columns are as they were",
          (ws.labels[(0, "L")], ws.labels[(0, "U")], ws.labels[(2, "L")], ws.labels[(2, "U")])
          == ("Wavelength", "nm", "Nor.", "a. u.") and ws.labels[(1, "C")] == "run_steadystate", str(ws.labels))

# ---------------------------------------------------------------------------------------------
if section("B-20"):
    top, app = make_app(SAMPLE_A)
    m = app.model
    folder = os.path.join(TMP, "b20"); os.makedirs(folder, exist_ok=True)
    files, _ = export_names(app, folder, "digits", csv=True, opju=False)
    def table_of(name):
        lines = [ln for ln in open(os.path.join(folder, name), encoding="utf-8").read().splitlines()
                 if not ln.startswith("#")]
        return lines[0], np.array([[float(v) for v in ln.split(",")] for ln in lines[1:]])

    head, table = table_of("digits_TRESmap.csv")
    scale = float(np.nanmax(np.abs(m.E)))
    check("(the table read back has the model's shape)", table.shape == (m.n_t, m.n_w + 1)
          and head.startswith("time_ps"), f"{table.shape} {head[:40]}")
    check("map CSV: the delays read back exactly", np.array_equal(table[:, 0], np.round(m.times, 6))
          or float(np.max(np.abs(table[:, 0] - m.times))) < 1e-6, str(float(np.max(np.abs(table[:, 0] - m.times)))))
    worst = float(np.nanmax(np.abs(table[:, 1:] - m.E.T) / np.maximum(np.abs(m.E.T), 1e-9 * scale)))
    check("map CSV: the counts read back within 1e-7 relative (were 4e-6)", worst < 1e-7, f"{worst:.3g}")
    _, ss = table_of("digits_steadystate.csv")
    worst = float(np.nanmax(np.abs(ss[:, 1] - m.spec_total) / np.abs(m.spec_total)))
    check("steady-state CSV: the sums read back within 1e-7 relative", worst < 1e-7, f"{worst:.3g}")
    check("a delay of a 65,536-bin record at 16 ps is written exactly", "%.8g" % 1048568.0 == "1048568"
          and getattr(NEW, "CSV_NUMBER", "%.6g") % 1048568.0 == "1048568", getattr(NEW, "CSV_NUMBER", "%.6g") % 1048568.0)
    # a Hangul file name in the picture's title
    real_path = m.phu["path"]
    m.phu["path"] = os.path.join(folder, "살로펜_톨루엔.phu")
    wls, times, Z = app._map_arrays_full()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        app._write_map_image(os.path.join(folder, "hangul.png"), wls, times, Z)
    m.phu["path"] = real_path
    missing = [str(w.message) for w in caught if "missing from" in str(w.message) or "Glyph" in str(w.message)]
    from matplotlib import font_manager
    try:
        font_manager.findfont("Malgun Gothic", fallback_to_default=False)
        has_hangul_font = True
    except Exception:
        has_hangul_font = False
    check("map picture: a Hangul file name is drawn with a font that has it (no missing-glyph warning)",
          os.path.getsize(os.path.join(folder, "hangul.png")) > 10000 and (not missing or not has_hangul_font),
          f"{missing[:2]}")
    top.destroy()

# ---------------------------------------------------------------------------------------------
if section("C-14"):
    top, app = make_app(SAMPLE_A)
    m = app.model
    app.var_offset.set("-50"); app.apply_offset(); pump(0.3)

    def file_wls(rows=None):
        w = m.wls - m.wl_offset
        return [round(float(v), 3) for v in (w if rows is None else w[rows])]

    m.crop_wl = (440.0, 540.0)
    m.masks = [(464.0, 471.0)]
    m.rebuild(); app.redraw(full=True); pump(0.2)
    kept0, masked0 = file_wls(), file_wls(m.mask_rows)
    check("(a crop of 21 curves with a mask on two of them, at OFFSET -50)", len(kept0) == 21 and len(masked0) == 2,
          f"{len(kept0)} {masked0}")
    app.cursor = (m.n_w - 1, 40); app.update_cursor()
    cursor_wl = file_wls()[app.cursor[0]]
    app.open_crop(); app.open_mask(); pump(0.4)
    c, mk = app._crop_win, app._mask_win
    app.var_offset.set("12"); app.apply_offset(); pump(0.4)
    check("OFFSET -50 -> 12: the crop keeps the same curves of the file", file_wls() == kept0,
          f"{file_wls()[0]}..{file_wls()[-1]} ({m.n_w}) vs {kept0[0]}..{kept0[-1]} ({len(kept0)})")
    check("... and the mask covers the same curves of the file", file_wls(m.mask_rows) == masked0,
          f"{file_wls(m.mask_rows)} vs {masked0}")
    check("... the crop range and the mask are quoted in the new nm",
          m.crop_wl == (502.0, 602.0) and m.masks == [(526.0, 533.0)], f"{m.crop_wl} {m.masks}")
    check("... the export settings line says so", "crop 502-602 nm" in app._export_note()
          and "masked 526-533 nm" in app._export_note(), app._export_note())
    check("... the cursor is still on its curve", app.cursor is not None and file_wls()[app.cursor[0]] == cursor_wl,
          f"{app.cursor}")
    check("the open Crop window: its boxes moved by the same 62 nm and frame the same 21 curves",
          abs(float(c.var_wl_lo.get()) - 502.0) < 1e-6 and abs(float(c.var_wl_hi.get()) - 602.0) < 1e-6
          and "keep 21 curves" in c.var_info.get(), f"{c.var_wl_lo.get()} {c.var_wl_hi.get()} {c.var_info.get()}")
    c._apply(); pump(0.3)
    check("... Apply with nothing touched keeps those curves", file_wls() == kept0, f"{m.n_w} curves")
    check("the open Mask window lists the mask in the new nm",
          mk.listbox.get(0) == "526.0 - 533.0 nm", str(mk.listbox.get(0)))
    app.var_offset.set("-50"); app.apply_offset(); pump(0.3)
    check("back to OFFSET -50: the same range, mask and curves as at the start",
          m.crop_wl == (440.0, 540.0) and m.masks == [(464.0, 471.0)] and file_wls() == kept0, f"{m.crop_wl} {m.masks}")
    check("no error box", not [b for b in boxes if b[0] == "showerror"], str(boxes))
    top.destroy()

# ---------------------------------------------------------------------------------------------
if section("A-9"):
    p = NEW.read_phu(SAMPLE_A)
    rng = np.random.default_rng(7)

    def synth(signal):
        q = dict(p)
        q["counts"] = rng.poisson(signal, size=p["counts"].shape).astype(np.uint32)
        return q

    # nothing but noise in sample and solvent: the true difference is zero
    m = NEW.TRESModel(synth(20.0), build=False)
    m.bg_sub = False
    m.solvent, m.solvent_sub = synth(20.0), True
    m.rebuild()
    sigma = np.sqrt(2 * 20.0 * m.rebin)                         # of one cell
    check("noise minus noise: the mean of a cell is 0 within its error (it was +0.4 sigma)",
          abs(float(np.nanmean(m.E))) < 4 * sigma / np.sqrt(m.E.size), f"{np.nanmean(m.E):+.4g}, sigma {sigma:.4g}")
    check("... and the steady-state spectrum is 0 within its error (it was +82,000 counts)",
          float(np.nanmax(np.abs(m.spec_total))) < 5 * sigma * np.sqrt(m.n_t), f"{np.nanmax(np.abs(m.spec_total)):.5g}")
    check("... half of the cells are below 0, and the model says so", 0.45 < m.neg_frac < 0.55, str(m.neg_frac))
    # a decay on top: the fit no longer finds an offset that is not there
    t = (np.arange(p["nbins"]) + 0.5) * p["res_ps"]
    decay = 200.0 * np.exp(-np.clip(t - 3000.0, 0, None) / 1500.0) * (t > 3000.0)
    m = NEW.TRESModel(synth(20.0 + decay[None, :]), build=False)
    m.bg_sub = False
    m.solvent, m.solvent_sub = synth(20.0), True
    m.rebuild()
    y = np.nanmean(m.E, axis=0)
    sel = m.times > 3200.0
    r = NEW.fit_single_trace(m.times[sel], y[sel], tau_init=np.array([1000.0]), tau_fixed=np.array([False]),
                             t0_init=3000.0, t0_fixed=True, fwhm_init=300.0, fwhm_fixed=True, has_inf=True)
    check("a decay of 1500 ps on that noise: the fitted offset is 0 within 0.5 counts (it was +5), tau within 2 %",
          abs(r["A"][-1]) < 0.5 and abs(r["tau"][0] / 1500.0 - 1) < 0.02, f"tau {r['tau'][0]:.5g}, offset {r['A'][-1]:+.4g}")
    # without a solvent nothing changed
    plain = NEW.TRESModel(p)
    old = OLD.TRESModel(OLD.read_phu(SAMPLE_A))
    check("no solvent: the map is 1.4's", np.array_equal(plain.E, old.E, equal_nan=True)
          and np.array_equal(plain.spec_total, old.spec_total, equal_nan=True))
    # the windows
    top, app = make_app(SAMPLE_A)
    mm = app.model
    solvent = dict(mm.phu)
    solvent["counts"] = (mm.phu["counts"] * 0.9).astype(mm.phu["counts"].dtype)
    solvent["path"] = os.path.join(TMP, "solvent.phu")
    mm.solvent, mm.solvent_scale, mm.solvent_sub = solvent, 1.2, True     # over-subtracted on purpose
    mm.rebuild(); app.redraw(full=True); pump(0.3)
    check("the map holds what is below 0", float(np.nanmin(mm.E)) < 0 and mm.neg_frac > 0.1, f"{np.nanmin(mm.E)} {mm.neg_frac}")
    check("the main window's solvent line gives the share below 0, not a clipped share",
          "of bins below 0" in app.var_solvinfo.get() and "clipped" not in app.var_solvinfo.get(), app.var_solvinfo.get())
    check("the export settings line no longer speaks of clipping",
          "solvent subtracted x1.2 (solvent.phu)" in app._export_note() and "clipped" not in app._export_note(),
          app._export_note())
    for log in (False, True):
        app.var_log.set(log); app.redraw(full=True); pump(0.2)
    check("drawing it with a linear and a log colour scale raises nothing", not cb_errors, str(cb_errors[:1])[-300:])
    app.open_crop(); pump(0.4)
    check("the Crop window's line gives the share below 0", "of bins below 0" in app._crop_win.var_info.get(),
          app._crop_win.var_info.get())
    wls, times, Z = app._map_arrays_full()
    check("the exported map is the unclipped one", float(np.nanmin(Z)) < 0)
    top.destroy()

finish()
