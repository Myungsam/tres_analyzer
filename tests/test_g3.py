"""Stage 3, group G3: state that goes out of step, and bad input (review items B-3, B-4, B-5 cursor, B-6,
A-7, B-7, A-8, B-17, B-24, C-15, C-6, C-7, C-11, C-16). One section per item; see _harness.py."""
import os

from _harness import *                        # noqa: F401,F403
from _harness import SAMPLE_B, NEW, SAMPLE_A, TMP, boxes, cb_errors, check, finish, make_app, make_phu, np, pump, section, wait


def counted(app):
    """Count rebuilds and redraws of ``app`` from now on."""
    n = {"rebuild": 0, "redraw": 0}
    real_rb, real_rd = app.model.rebuild, app.redraw
    app.model.rebuild = lambda: (n.__setitem__("rebuild", n["rebuild"] + 1), real_rb())[1]
    app.redraw = lambda *a, **k: (n.__setitem__("redraw", n["redraw"] + 1), real_rd(*a, **k))[1]
    return n


def raised(fn):
    try:
        fn()
        return ""
    except Exception as exc:                    # noqa: BLE001
        return f"{type(exc).__name__}: {exc}"


# ---------------------------------------------------------------------------------------------
if section("B-3"):
    # leaving an entry box without changing anything must not rebuild, redraw or drop the contrast
    top, app = make_app(SAMPLE_A)
    app.clim = (5.0, 500.0); app.redraw(full=True); pump(0.1)
    n = counted(app)
    E_before = app.model.E
    app.apply_params()                           # what <FocusOut> / <Return> on an untouched box calls
    check("nothing changed: no rebuild, no redraw, the manual contrast stays",
          n == {"rebuild": 0, "redraw": 0} and app.clim == (5.0, 500.0) and app.model.E is E_before,
          f"{n} clim={app.clim}")
    app.var_tmax.set("12000"); app.apply_params()
    check("a changed TIME SPAN is applied (one rebuild, one redraw) and keeps the contrast: counts per bin are the same",
          n == {"rebuild": 1, "redraw": 1} and abs(app.model.t_max_ps - 12000) < 20 and app.clim == (5.0, 500.0),
          f"{n} {app.model.t_max_ps} clim={app.clim}")
    app.var_bin.set("64 ps"); app.apply_params()
    check("a changed BIN is applied and resets the contrast (counts per bin changed)",
          n["rebuild"] == 2 and app.model.rebin == 16 and app.clim is None, f"{n} {app.model.rebin} {app.clim}")
    app.clim = (1.0, 50.0)
    app.var_bgsub.set(not app.var_bgsub.get()); app.apply_params()
    check("switching the background subtraction resets the contrast too", n["rebuild"] == 3 and app.clim is None)
    app.apply_params()
    check("and again nothing happens when nothing changed", n["rebuild"] == 3 and n["redraw"] == 3, str(n))
    top.destroy()

# ---------------------------------------------------------------------------------------------
if section("B-4"):
    # a pinned cursor stays on its wavelength and delay when the model is rebuilt
    top, app = make_app(SAMPLE_A)
    m = app.model
    wi = int(np.argmin(np.abs(m.wls - 490.0)))
    ti = int(np.argmin(np.abs(m.times - 1992.0)))
    app.cursor, app.pinned = (wi, ti), True
    app.update_cursor()
    wl0, t0 = float(m.wls[wi]), float(m.times[ti])

    def where():
        mm = app.model
        return float(mm.wls[app.cursor[0]]), float(mm.times[app.cursor[1]])
    # a cursor sits on a bin centre, so it can move by half a bin of the coarsest setting it went through
    for label, setter, tol in (("BIN 4 ps", lambda: app.var_bin.set("4 ps"), 8.0),
                               ("BIN 64 ps", lambda: app.var_bin.set("64 ps"), 32.0),
                               ("BIN 16 ps", lambda: app.var_bin.set("16 ps"), 40.0)):
        setter(); app.apply_params(); pump(0.05)
        wl, t = where()
        check(f"{label}: the pinned cursor is still at {wl0:.0f} nm / about {t0:.0f} ps",
              abs(wl - wl0) < 1e-6 and abs(t - t0) <= tol and app.pinned, f"{wl:.1f} nm, {t:.0f} ps")
    app.var_irf.set(False); app.apply_params(); pump(0.05)
    wl, t = where()
    check("'First curve is IRF' off (one more curve in the map): still the same wavelength",
          abs(wl - wl0) < 1e-6 and abs(t - t0) <= 40.0, f"{wl:.1f} nm, {t:.0f} ps")
    app.var_irf.set(True); app.var_t0.set(True); app.apply_params(); pump(0.05)
    wl, t = where()
    shift = app.model.t0
    check("'t0 at IRF peak' on (the time axis is renumbered): same wavelength, same real delay",
          abs(wl - wl0) < 1e-6 and abs((t + shift) - t0) <= 40.0, f"{wl:.1f} nm, {t:.0f} ps (+{shift:.0f})")
    top.destroy()

# ---------------------------------------------------------------------------------------------
if section("B-5"):
    # an offset change with a crop: the cursor must stay inside the map
    top, app = make_app(SAMPLE_A)
    m = app.model
    m.crop_wl = (float(m.wls[0]) - 1, float(m.wls[6]) + 1)
    m.rebuild(); app.redraw(full=True); pump(0.1)
    app.cursor = (m.n_w - 1, 40)
    app.update_cursor()
    n_before = m.n_w
    app.var_offset.set(f"{m.wl_offset + 30:g}")
    err = raised(app.apply_offset)
    pump(0.1)
    # (up to 1.5 the crop kept fewer curves here, which is how the cursor got outside the map; since
    #  C-14 in 1.6 the crop follows the offset and keeps its curves - see test_g8.py)
    check("the crop keeps its curves after the offset change",
          app.model.n_w == n_before, f"{n_before} -> {app.model.n_w}")
    check("apply_offset raises nothing and the cursor is a valid cell",
          not err and app.cursor is not None and app.cursor[0] < app.model.n_w and app.cursor[1] < app.model.n_t,
          err or str(app.cursor))
    check("moving the pointer afterwards works", not raised(app.update_cursor))
    top.destroy()

# ---------------------------------------------------------------------------------------------
if section("B-6"):
    # the crosshair and the live curves survive a draw that redraw() did not start (a resize)
    top, app = make_app(SAMPLE_A)
    m = app.model
    app.cursor, app.pinned = (m.n_w // 2, m.n_t // 3), True
    app.redraw(full=True); pump(0.2)
    good = np.asarray(app.canvas.buffer_rgba()).copy()
    app.canvas.draw(); pump(0.1)                 # what a resize or an exposed window triggers
    after = np.asarray(app.canvas.buffer_rgba()).copy()
    lost = int((good != after).any(axis=2).sum())
    # (blitting leaves a few dozen pixels of the axes' top edge row different from call to call, in 1.4 as
    #  well; the crosshair, the two curves and the read-out are tens of thousands)
    check("after a plain canvas.draw() the pinned picture is still complete", lost < 200, f"{lost} pixels differ")
    top.geometry("1300x860+0+0"); pump(0.6)
    resized = np.asarray(app.canvas.buffer_rgba()).copy()
    app.update_cursor(); pump(0.1)
    again = np.asarray(app.canvas.buffer_rgba()).copy()
    lost = int((resized != again).any(axis=2).sum())
    check("after a real resize the cursor is already drawn (drawing it again changes nothing)", lost < 200,
          f"{lost} pixels differ")
    top.destroy()

# ---------------------------------------------------------------------------------------------
if section("A-7"):
    # model: a file with one curve and "First curve is IRF"
    one = NEW.read_phu(make_phu(os.path.join(TMP, "one.phu"), ncurves=1, nbins=256))
    mdl = NEW.TRESModel(one)
    mdl.first_is_irf = True
    err = raised(mdl.rebuild)
    check("rebuild() of a one-curve file with first_is_irf raises nothing and keeps that curve as data",
          not err and mdl.n_w == 1 and mdl.irf is None and mdl.E.shape[0] == 1, err or f"{mdl.n_w} {mdl.irf is None}")
    check("its axes can be asked for", not raised(lambda: (mdl.wl_edges, mdl.times, mdl.locate(float(mdl.wls[0]), 10.0))))
    two = NEW.read_phu(make_phu(os.path.join(TMP, "two.phu"), ncurves=2, nbins=256))
    m2 = NEW.TRESModel(two)
    m2.first_is_irf = True
    m2.rebuild()
    check("with two curves the first is still taken as the IRF", m2.n_w == 1 and m2.irf is not None)

# ---------------------------------------------------------------------------------------------
if section("B-7"):
    # viewer: a file that cannot be shown leaves everything as it was, with a message
    top, app = make_app(SAMPLE_A)
    app.open_kinetics(); pump(0.3)
    kin, model, path = app._kinetics_win, app.model, app.var_path.get()
    one = make_phu(os.path.join(TMP, "one.phu"), ncurves=1, nbins=256)
    boxes.clear()
    err = raised(lambda: app.load(one))
    pump(0.3)
    check("a one-curve file opens (its curve is shown as data), no exception", not err
          and app.model is not model and app.model.n_w == 1, err or str(app.model.n_w))
    app.load(SAMPLE_A); pump(0.2)
    app.open_kinetics(); pump(0.3)
    kin, model, path = app._kinetics_win, app.model, app.var_path.get()
    real_rebuild = NEW.TRESModel.rebuild

    def broken(self):
        raise RuntimeError("planted: this file cannot be shown")
    NEW.TRESModel.rebuild = broken
    boxes.clear()
    try:
        err = raised(lambda: app.load(SAMPLE_B))
    finally:
        NEW.TRESModel.rebuild = real_rebuild
    pump(0.3)
    check("a file whose model cannot be built: an error box instead of an exception",
          not err and [b[0] for b in boxes] == ["showerror"] and "planted" in boxes[0][2], err or str(boxes))
    check("... the old file is still loaded, its path shown, its Kinetics window open",
          app.model is model and app.var_path.get() == path and kin.alive and app._kinetics_win is kin)
    check("... and the old file still works", not raised(app.apply_params) and not raised(lambda: app.redraw(full=True)))
    top.destroy()

# ---------------------------------------------------------------------------------------------
if section("A-8"):
    # model: a time window at the very end of the record that is shorter than the rebin factor
    phu = NEW.read_phu(SAMPLE_A)
    mdl = NEW.TRESModel(phu)
    full = phu["nbins"] * phu["res_ps"]
    for rb, lo in ((4, full - 4.0), (16, full - 20.0), (64, full - 100.0)):
        mdl.rebin, mdl.t_min_ps, mdl.t_max_ps = rb, lo, full
        err = raised(mdl.rebuild)
        check(f"rebin {rb}, window starting {full - lo:.0f} ps before the end: rebuild works, one whole bin at least",
              not err and mdl.n_t >= 1 and mdl.E.shape == (mdl.n_w, mdl.n_t)
              and mdl.t_off_ps + mdl.n_t * rb * phu["res_ps"] <= full + 1e-6, err or f"{mdl.E.shape}")
    from _harness import OLD
    a, b = NEW.TRESModel(phu), OLD.TRESModel(phu)
    for mm in (a, b):
        mm.rebin, mm.t_min_ps, mm.t_max_ps = 4, 2000.0, 20000.0
        mm.rebuild()
    check("an ordinary window gives the same map as 1.4", np.array_equal(a.E, b.E, equal_nan=True) and a.t_off_ps == b.t_off_ps)

# ---------------------------------------------------------------------------------------------
if section("B-17"):
    # nan / inf typed into the main window's boxes
    top, app = make_app(SAMPLE_A)
    m = app.model
    start = (m.t_max_ps, m.bg_lo_ps, m.bg_hi_ps, m.wl_offset)
    for label, var, call in (("TIME SPAN = nan", app.var_tmax, app.apply_params),
                             ("TIME SPAN = inf", app.var_tmax, app.apply_params),
                             ("WINDOW from = nan", app.var_bg_lo, app.apply_params),
                             ("WINDOW to = inf", app.var_bg_hi, app.apply_params),
                             ("OFFSET = nan", app.var_offset, app.apply_offset),
                             ("OFFSET = inf", app.var_offset, app.apply_offset)):
        var.set(label.split("= ")[1])
        err = raised(call)
        pump(0.05)
        vals = (m.t_max_ps, m.bg_lo_ps, m.bg_hi_ps, m.wl_offset)
        check(f"{label}: no exception, the model holds finite numbers, the box shows a number again",
              not err and all(np.isfinite(v) for v in vals) and np.isfinite(float(var.get())),
              err or f"{vals} box={var.get()!r}")
    check("after all that the window still redraws", not raised(lambda: app.redraw(full=True)))
    top.destroy()


def click(c, x, y, dbl=False, button=1):
    """A mouse press on the Crop / Mask map at data coordinates."""
    from matplotlib.backend_bases import MouseEvent
    px, py = c.ax.transData.transform((x, y))
    c.canvas.callbacks.process("button_press_event",
                               MouseEvent("button_press_event", c.canvas, px, py, button=button, dblclick=dbl))


# ---------------------------------------------------------------------------------------------
if section("C-6"):
    # Crop: a wavelength range that holds no curve
    top, app = make_app(SAMPLE_A)
    app.open_crop(); pump(0.3)
    c = app._crop_win
    wl = c._full.wls
    gap_lo, gap_hi = float(wl[10]) + 1.5, float(wl[10]) + 2.5        # between two curves
    c.var_wl_lo.set(f"{gap_lo:g}"); c.var_wl_hi.set(f"{gap_hi:g}"); c._update_overlay(); pump(0.1)
    check("the info line says that no curve is in the range (not 'keep 0 curves' as if that could be applied)",
          "no curve" in c.var_info.get().lower(), c.var_info.get())
    before = (app.model.crop_wl, app.model.n_w)
    boxes.clear()
    c._apply(); pump(0.2)
    check("Apply is refused with a message and the model is untouched",
          [b[0] for b in boxes] == ["showwarning"] and (app.model.crop_wl, app.model.n_w) == before
          and "crop" not in app._export_note().lower(), f"{boxes} {app.model.crop_wl} {app._export_note()}")
    # a range that holds exactly one curve is fine, and counted with the model's tolerance
    c.var_wl_lo.set(f"{float(wl[10]) - 1:g}"); c.var_wl_hi.set(f"{float(wl[10]):g}"); c._update_overlay(); pump(0.1)
    check("a range ending exactly on a curve counts that curve", "keep 1 curve" in c.var_info.get(), c.var_info.get())
    boxes.clear()
    c._apply(); pump(0.2)
    check("... and applies to that one curve", app.model.n_w == 1 and not boxes
          and abs(app.model.wls[0] - wl[10]) < 1e-9, f"{app.model.n_w} {boxes}")
    top.destroy()

# ---------------------------------------------------------------------------------------------
if section("C-7"):
    # nan / inf in the Crop and Mask boxes
    top, app = make_app(SAMPLE_A)
    app.open_crop(); pump(0.3)
    c = app._crop_win
    for var, text in ((c.var_t_lo, "nan"), (c.var_t_hi, "inf"), (c.var_wl_lo, "nan"), (c.var_wl_hi, "-inf")):
        old = var.get()
        var.set(text)
        err = raised(c._update_overlay)
        box = c._read()
        check(f"Crop box = {text}: the preview raises nothing and reads a finite range",
              not err and all(np.isfinite(v) for v in box), err or str(box))
        err = raised(c._apply); pump(0.1)
        m = app.model
        check(f"... Apply leaves a finite model that still rebuilds",
              not err and np.isfinite(m.t_min_ps) and np.isfinite(m.t_max_ps)
              and (m.crop_wl is None or all(np.isfinite(v) for v in m.crop_wl)) and not raised(app.apply_params),
              err or f"{m.t_min_ps} {m.t_max_ps} {m.crop_wl}")
        var.set(old)
    c._on_close()
    app.open_mask(); pump(0.3)
    mk = app._mask_win
    n0 = len(app.model.masks)
    for lo, hi in (("nan", "500"), ("nan", "nan"), ("-inf", "inf"), ("5000", "6000")):
        boxes.clear()
        mk.var_lo.set(lo); mk.var_hi.set(hi); mk._add(); pump(0.05)
        check(f"Mask {lo} .. {hi}: refused with a message, nothing added",
              len(app.model.masks) == n0 and [b[0] for b in boxes] == ["showwarning"], f"{app.model.masks} {boxes}")
    wls = app.model.wls
    mk.var_lo.set(f"{wls[5]:g}"); mk.var_hi.set(f"{wls[7]:g}"); boxes.clear(); mk._add(); pump(0.1)
    check("an ordinary band is still added", len(app.model.masks) == n0 + 1 and not boxes
          and int(app.model.mask_rows.sum()) == 3)
    top.destroy()

# ---------------------------------------------------------------------------------------------
if section("C-16"):
    # Crop: a first corner that was clicked does not outlive the next action
    top, app = make_app(SAMPLE_A)
    app.open_crop(); pump(0.3)
    c = app._crop_win
    w0, w1 = c.wl_full
    mid_w, mid_t = 0.5 * (w0 + w1), 0.4 * c.t_full[1]

    def arm():
        c._corner = None
        click(c, mid_w - 40, mid_t); pump(0.05)
        return c._corner is not None
    for label, action in (("Full λ", c._full_wl), ("Full t", c._full_t), ("Apply", c._apply),
                          ("Reset", c._reset),
                          ("typing in a box", lambda: (c.var_t_hi.set("9000"), c._on_typed())),
                          # (a key event goes to the window that has the keyboard focus; the test window
                          #  cannot count on getting it, so the handler the key is bound to is called)
                          ("Escape", lambda: c._cancel_corner())):
        armed = arm()
        action(); pump(0.2)
        check(f"after {label} the armed corner is gone", armed and c._corner is None, f"armed={armed} {c._corner}")
    check("Esc is bound to that in the Crop window", bool(c.win.bind("<Escape>")))
    arm()
    click(c, mid_w + 40, mid_t + 3000); pump(0.2)
    check("two clicks in a row still set the box",
          c._corner is None and abs(float(c.var_wl_lo.get()) - (mid_w - 40)) < 1
          and abs(float(c.var_wl_hi.get()) - (mid_w + 40)) < 1, f"{c.var_wl_lo.get()} {c.var_wl_hi.get()}")
    top.destroy()

# ---------------------------------------------------------------------------------------------
if section("C-11"):
    # the fit windows refuse an entry they cannot read, in words - no silent stand-in value
    top, app = make_app(SAMPLE_A)
    for kind, opener, attr in (("Kinetics", app.open_kinetics, "_kinetics_win"),
                               ("Global", app.open_global_analysis, "_global_win")):
        opener(); pump(0.3)
        d = getattr(app, attr)
        cases = [("τ = 'abc'", lambda: d.table.rows[0]["tau"].set("abc"), "τ"),
                 ("τ = '1,5'", lambda: d.table.rows[0]["tau"].set("1,5"), "τ"),
                 ("τ = nan", lambda: d.table.rows[0]["tau"].set("nan"), "τ"),
                 ("τ = -5", lambda: d.table.rows[0]["tau"].set("-5"), "τ"),
                 ("β = 7 on a stretched component",
                  lambda: (d.table.rows[0]["st"].set(True), d.table.rows[0]["beta"].set("7")), "β"),
                 ("β = nan on a stretched component",
                  lambda: (d.table.rows[0]["st"].set(True), d.table.rows[0]["beta"].set("nan")), "β"),
                 ("fit range from = 'x'", lambda: d.var_tmin.set("x"), "range"),
                 ("fit range to = nan", lambda: d.var_tmax.set("nan"), "range"),
                 ("t0 = ''", lambda: d.var_t0.set(""), "t₀"),
                 ("FWHM = 'wide'", lambda: d.var_fw.set("wide"), "FWHM")]
        if kind == "Kinetics":
            cases += [("λ = 'blue'", lambda: d.var_wl.set("blue"), "λ"),
                      ("half-width = nan", lambda: d.var_hw.set("nan"), "half")]
        def clean():
            d.reset(); pump(0.05)
            row = d.table.rows[0]               # Reset keeps what was typed into the table
            row["tau"].set("100"); row["st"].set(False); row["beta"].set("1")
            if kind == "Kinetics":              # ... and the wavelength boxes
                d.var_wl.set("545"); d.var_hw.set("0")
        for label, spoil, word in cases:
            clean()
            spoil()
            boxes.clear()
            d.run_fit(); pump(0.2)
            started = d._running
            if started:
                d.stop_fit(); wait(lambda: not d._running, 30); pump(0.1)
            check(f"{kind}, {label}: no fit is started, one message that names the box",
                  not started and len(boxes) == 1 and boxes[0][0] == "showwarning" and word in boxes[0][2],
                  f"started={started} {boxes}")
        clean()
        boxes.clear()
        d.run_fit(); wait(lambda: not d._running, 60); pump(0.2)
        check(f"{kind}: the default set-up still fits", d._last is not None and not boxes, str(boxes))
        d._on_close(); pump(0.2)
    top.destroy()

# ---------------------------------------------------------------------------------------------
if section("B-24"):
    # a change in the main window reaches the open windows
    top, app = make_app(SAMPLE_A)
    app.open_crop(); app.open_mask(); app.open_kinetics(); app.open_global_analysis(); pump(0.4)
    c, mk, k, g = app._crop_win, app._mask_win, app._kinetics_win, app._global_win
    lo0, hi0, full0 = float(c.var_wl_lo.get()), float(c.var_wl_hi.get()), c.wl_full
    shown0 = mk.ax.images[0].get_extent() if mk.ax.images else None
    app.var_offset.set(f"{app.model.wl_offset + 30:g}"); app.apply_offset(); pump(0.4)
    check("OFFSET +30 nm: the Crop window's map and limits move with it",
          abs(c.wl_full[0] - (full0[0] + 30)) < 1e-6 and abs(c._full.wl_offset - app.model.wl_offset) < 1e-9
          and abs(c.ax.get_xlim()[0] - (full0[0] + 30 - 2.5)) < 3, f"{c.wl_full} xlim={c.ax.get_xlim()}")
    # (C-14, 1.6: the boxes move with the offset, like the model's crop, and frame the same curves)
    check("... its boxes move along and are shown on the new axis",
          abs(float(c.var_wl_lo.get()) - (lo0 + 30)) < 1e-6 and abs(float(c.var_wl_hi.get()) - (hi0 + 30)) < 1e-6
          and str(c._curves_in(*c._read()[:2])) in c.var_info.get(), f"{c.var_wl_lo.get()} {c.var_info.get()}")
    shown1 = mk.ax.images[0].get_extent() if mk.ax.images else None
    check("... the Mask preview is redrawn on the new axis",
          shown0 is not None and shown1 is not None and abs(shown1[0] - (shown0[0] + 30)) < 1e-6, f"{shown0} {shown1}")
    title0 = k.ax_main.get_title()
    n_t0 = app.model.n_t
    app.var_bin.set("64 ps"); app.apply_params(); pump(0.4)
    check("BIN 64 ps: the Crop preview has the new time bins", c._full.rebin == 16 and c._raw0.shape[1] == c._full.n_t)
    check("... the Kinetics plot shows the rebinned trace",
          len(k.ax_main.lines[0].get_xdata()) == app.model.n_t != n_t0, f"{len(k.ax_main.lines[0].get_xdata())}")
    check("... the Global window's point count follows", str(app.model.n_t) in g.var_tcount.get(), g.var_tcount.get())
    # mid-review M3: TIME SPAN and "t0 at IRF peak" reach the windows as well
    app.var_bin.set("16 ps"); app.var_tmax.set("8000"); app.apply_params(); pump(0.4)
    check("TIME SPAN 8000: the Crop window's 't to' box follows", abs(float(c.var_t_hi.get()) - 8000) < 20, c.var_t_hi.get())
    c._apply(); pump(0.3)
    check("... so Crop Apply with nothing touched keeps TIME SPAN 8000",
          abs(app.model.t_max_ps - 8000) < 20, str(app.model.t_max_ps))
    t0_box, lo_box, hi_box = float(k.var_t0.get()), float(k.var_tmin.get()), float(k.var_tmax.get())
    g_t0 = float(g.var_t0.get())
    app.var_t0.set(True); app.apply_params(); pump(0.4)
    shift = app.model.t0
    check("'t0 at IRF peak' on: the time axis is renumbered by the IRF peak position", shift > 100, str(shift))
    check("... Kinetics moves t₀ and its fit range along, so they mean the same delays",
          abs(float(k.var_t0.get()) - (t0_box - shift)) < 1 and abs(float(k.var_tmin.get()) - (lo_box - shift)) < 20
          and abs(float(k.var_tmax.get()) - (hi_box - shift)) < 20, f"{k.var_t0.get()} {k.var_tmin.get()} {k.var_tmax.get()}")
    check("... and so does Global", abs(float(g.var_t0.get()) - (g_t0 - shift)) < 1, g.var_t0.get())
    boxes.clear()
    k.run_fit(); wait(lambda: not k._running, 60); pump(0.3)
    check("... a Kinetics fit on the renumbered axis is as good as before (RMS about 275, not thousands)",
          k._last is not None and k._last["info"]["rms"] < 400, str(None if k._last is None else k._last["info"]["rms"]))
    top.destroy()

# ---------------------------------------------------------------------------------------------
if section("C-15"):
    # raising an open window brings it up to date
    top, app = make_app(SAMPLE_A)
    app.open_kinetics(); app.open_global_analysis(); app.open_mask(); pump(0.4)
    k, g, mk = app._kinetics_win, app._global_win, app._mask_win
    m = app.model
    m.rebin = 16; m.rebuild()                    # changed behind the windows' backs (as another dialog's Apply does)
    for w in (k, g, mk):
        w.lift_and_refresh()
    pump(0.3)
    check("lift_and_refresh: Kinetics redraws the current trace", len(k.ax_main.lines[0].get_xdata()) == m.n_t)
    check("lift_and_refresh: Global updates its point count", str(m.n_t) in g.var_tcount.get(), g.var_tcount.get())
    check("pressing the main window's button on an open window does the same (no second window)",
          (app.open_kinetics(), app._kinetics_win is k)[1])
    top.destroy()

finish()
