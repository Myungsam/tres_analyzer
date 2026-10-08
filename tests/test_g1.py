"""Stage 3, group G1: the fit results can be trusted (review items C-1, C-3, A-3, A-4, A-15, A-16/C-25,
A-1 flag, C-20, S-3a, S-3b). One section per item; see _harness.py."""
import os

from _harness import *                        # noqa: F401,F403
from _harness import NEW, OLD, TMP, boxes, check, finish, make_app, np, pump, section, wait
import _versions

# These checks compare with 1.4: the rules 1.6 changed on purpose are put back (see _versions.rules_of_1_5).
_versions.rules_of_1_5(NEW)


def run_global(g, limit=120.0):
    g.run_fit()
    wait(lambda: not g._running, limit)
    pump(0.2)
    return g._last


def csv_shape(path):
    """(names in the header line, columns in the first data line, comment lines) of a written CSV."""
    lines = open(path, encoding="utf-8").read().split("\n")
    body = [ln for ln in lines if ln and not ln.startswith("#")]
    return body[0].split(","), len(body[1].split(",")), [ln for ln in lines if ln.startswith("#")]


def exported(g):
    """What export_results hands to the main window: {suffix: path of the CSV it writes}."""
    got = {}
    real = g.app.export_analysis
    g.app.export_analysis = lambda base, items, **kw: got.update(
        {it["suffix"]: (it["csv"](os.path.join(TMP, f"{base}_{it['suffix']}.csv")),
                        os.path.join(TMP, f"{base}_{it['suffix']}.csv"))[1] for it in items})
    try:
        g.export_results()
    finally:
        g.app.export_analysis = real
    return got


top, app = make_app()

# ---------------------------------------------------------------------------------------------
if section("C-1"):
    # Global: the "Include tau = inf" box is read again after the fit
    app.open_global_analysis(); pump(0.3)
    g = app._global_win
    g.var_n.set("2"); g.table.set_n(2)
    g.var_inf.set(True)
    res = run_global(g)
    k = res["A"].shape[1]
    check("a fit with the offset has 3 amplitude columns", k == 3, str(k))
    g.var_inf.set(False)                       # the user unticks the box after the fit
    pump(0.1)
    files = exported(g)
    for kind in ("DADS", "EADS"):
        names, ncols, notes = csv_shape(files[kind])
        check(f"{kind} CSV written after unticking: as many header names as data columns",
              len(names) == ncols == 1 + k, f"{len(names)} names, {ncols} columns")
        check(f"{kind} CSV: the offset column is named inf", names[-1] == f"{kind}_inf", names[-1])
        check(f"{kind} CSV: the settings lines still say the fit had the offset",
              any("offset: tau = inf" in ln for ln in notes))
    g._draw_all(); pump(0.1)
    leg = [t.get_text() for t in g.ax_dads.get_legend().get_texts()]
    check("redrawn DADS legend still labels the offset", leg[-1] == "∞" and len(leg) == k, str(leg))
    g._report_global(g._last)
    check("report text still lists the offset", "(constant offset)" in g.txt.get("1.0", "end"))
    # the other way round: fitted without, ticked afterwards
    res = run_global(g)
    k = res["A"].shape[1]
    g.var_inf.set(True)
    files = exported(g)
    names, ncols, notes = csv_shape(files["DADS"])
    check("fitted without the offset, ticked afterwards: 2 components, no inf column, no offset line",
          k == 2 and len(names) == ncols == 3 and not names[-1].endswith("inf")
          and not any("offset: tau = inf" in ln for ln in notes), f"{k} {names} {ncols}")
    check("no error box", not [b for b in boxes if b[0] == "showerror"], str(boxes))
    g._on_close(); pump(0.2)

# ---------------------------------------------------------------------------------------------
if section("C-3"):
    # Global: the data of a new run must not be paired with the result of the previous one
    app.open_global_analysis(); pump(0.3)
    g = app._global_win
    g.var_n.set("2"); g.table.set_n(2)
    first = run_global(g)
    n_t1, wl1 = first["fit"].shape[1], g._fit_wls.copy()
    # a second run on fewer delays, stopped before it can finish
    g.var_tmax.set("12000")
    gate = {"hold": True}
    real_fit = NEW.fit_global_analysis

    def slow_fit(D, t, **kw):
        while gate["hold"] and not kw["stop_check"]():
            import time
            time.sleep(0.02)
        return real_fit(D, t, **kw)
    NEW.fit_global_analysis = slow_fit
    try:
        g.run_fit(); pump(0.2)
        check("the second run is under way", g._running)
        n_cb = len(cb_errors)
        try:
            g._plot_kinetics(); g._draw_all(); pump(0.1)
            drew = ""
        except Exception as exc:                # noqa: BLE001 - the failure this item is about
            drew = f"{type(exc).__name__}: {exc}"
        check("drawing while the second run is going still shows the first result (no shape error)",
              not drew and len(cb_errors) == n_cb and g._fit_t.size == n_t1 == g._last["fit"].shape[1],
              drew or f"{g._fit_t.size} vs {n_t1}")
        g.stop_fit()
        wait(lambda: not g._running, 20)
        pump(0.2)
        check("after Stop the first result is still complete and drawable",
              g._last is first and g._fit_t.size == n_t1 and np.array_equal(g._fit_wls, wl1))
        try:
            g._on_map_click(type("E", (), {"inaxes": g.ax_data, "xdata": float(wl1[5])})())
            pump(0.1)
            drew = ""
        except Exception as exc:                # noqa: BLE001
            drew = f"{type(exc).__name__}: {exc}"
        check("clicking a map after the stopped run raises nothing", not drew and len(cb_errors) == n_cb, drew)
    finally:
        gate["hold"] = False
        NEW.fit_global_analysis = real_fit
    # a run on another set of wavelengths, stopped: the export must still be the first fit's
    app.model.crop_wl = (float(app.model.wls[30]), float(app.model.wls[-1]))
    app.model.rebuild(); app.redraw(); pump(0.2)
    NEW.fit_global_analysis = slow_fit
    gate["hold"] = True
    try:
        g.run_fit(); pump(0.2)
        g.stop_fit(); wait(lambda: not g._running, 20); pump(0.2)
    finally:
        gate["hold"] = False
        NEW.fit_global_analysis = real_fit
    files = exported(g)
    body = [ln for ln in open(files["DADS"], encoding="utf-8").read().split("\n") if ln and not ln.startswith("#")]
    wl_out = np.array([float(ln.split(",")[0]) for ln in body[1:]])
    check("export after a stopped run on other wavelengths: wavelength column is the fitted one",
          wl_out.size == first["A"].shape[0] and np.allclose(wl_out, wl1, rtol=1e-7),
          f"{wl_out[:2]} .. vs {wl1[:2]}")
    app.model.crop_wl = None
    app.model.rebuild(); app.redraw(); pump(0.2)
    g._on_close(); pump(0.2)

# ---------------------------------------------------------------------------------------------
if section("S-3b"):
    # Global: an exception while showing the result must not leave Run disabled
    app.open_global_analysis(); pump(0.3)
    g = app._global_win
    g.var_n.set("2"); g.table.set_n(2)
    real_draw = g._report_global

    def broken_draw(res):
        raise RuntimeError("planted: showing the result failed")
    g._report_global = broken_draw
    n_cb = len(cb_errors)
    g.run_fit()
    wait(lambda: str(g.btn_run.cget("state")) == "normal" and not g._running, 60)
    pump(0.3)
    check("after a failure in showing the result Run is enabled again and nothing is 'running'",
          str(g.btn_run.cget("state")) == "normal" and str(g.btn_stop.cget("state")) == "disabled"
          and not g._running, f"{g.btn_run.cget('state')} {g._running}")
    check("the status says so instead of staying on 'Fitting...'",
          "Fitting" not in g.var_status.get() and "fail" in g.var_status.get().lower(), g.var_status.get())
    check("the exception is still reported (it reaches the callback handler, i.e. the freeze log)",
          len(cb_errors) == n_cb + 1 and "planted" in cb_errors[-1])
    del cb_errors[n_cb:]
    g._report_global = real_draw
    res = run_global(g)
    check("the next run works", res is not None and g.var_status.get().startswith("Fit done"), g.var_status.get())
    g._on_close(); pump(0.2)

# ---------------------------------------------------------------------------------------------
if section("C-20"):
    # Global: Reset must drop a running fit and clear the old figure; the "nothing to fit" message
    app.open_global_analysis(); pump(0.3)
    g = app._global_win
    g.var_n.set("2"); g.table.set_n(2)
    run_global(g)
    shown = sum(len(ax.images) + len(ax.lines) for ax in g._all_axes)
    g.reset(); pump(0.2)
    left = sum(len(ax.images) + len(ax.lines) for ax in g._all_axes)
    check("Reset after a fit clears the figure too (the result is gone, so is its picture)",
          shown > 0 and left == 0 and g._last is None, f"{shown} -> {left}")
    gate = {"hold": True}
    real_fit = NEW.fit_global_analysis

    def slow_fit(D, t, **kw):
        import time
        while gate["hold"] and not kw["stop_check"]():
            time.sleep(0.02)
        gate["stopped"] = kw["stop_check"]()
        return real_fit(D, t, **{**kw, "stop_check": None})      # finish even though told to stop
    NEW.fit_global_analysis = slow_fit
    try:
        g.var_n.set("2"); g.table.set_n(2)
        g.run_fit(); pump(0.2)
        g.reset(); pump(0.1)                 # table back to 3 rows while a 2-component fit runs
        check("Reset while a fit runs tells it to stop", g._stop.is_set())
        wait(lambda: not g._running, 60); pump(0.3)
        check("... and its result is not taken over (no 2-lifetime result under a 3-row table)",
              g._last is None and sum(len(ax.images) + len(ax.lines) for ax in g._all_axes) == 0,
              str(None if g._last is None else g._last["tau"]))
        check("... Run is enabled again", str(g.btn_run.cget("state")) == "normal" and not g._running)
    finally:
        gate["hold"] = False
        NEW.fit_global_analysis = real_fit
    res = run_global(g)
    check("a fit after that is shown normally", res is not None and len(res["tau"]) == 3)
    # one curve left by the crop, nothing masked
    m = app.model
    m.crop_wl = (float(m.wls[10]) - 0.1, float(m.wls[10]) + 0.1)
    m.rebuild(); app.redraw(); pump(0.2)
    boxes.clear()
    g.run_fit(); pump(0.2)
    msg = boxes[-1][2] if boxes else ""
    check("one wavelength left by the crop: the message does not blame masks",
          not g._running and boxes and "masked out" not in msg and "2 wavelengths" in msg, str(boxes))
    m.crop_wl = None
    m.rebuild(); app.redraw(); pump(0.2)
    g._on_close(); pump(0.2)

# ---------------------------------------------------------------------------------------------
# kernel-level items: the sample A map and one of its traces
m = app.model
T_AX, E_MAP = m.times.copy(), m.E.copy()
Y_TR = E_MAP[int(np.argmin(np.abs(m.wls - 545.0)))].copy()
T0_D = float(m.irf_peak_ps - m.t0)
FW_D = float(m.irf_fwhm_ps)
SIG4 = FW_D / (2.0 * np.sqrt(2.0 * np.log(2.0))) / 4.0
GKW = dict(t0_init=T0_D, fwhm_init=FW_D, t0_fixed=True, fwhm_fixed=True, has_inf=False)
KKW = dict(t0_init=T0_D, fwhm_init=FW_D, t0_fixed=True, fwhm_fixed=True, has_inf=False, irf_mode="numerical")


def raises(fn):
    try:
        fn()
        return ""
    except Exception as exc:                    # noqa: BLE001
        # the kernels' own refusals are FitInputError, a ValueError with a sentence for the user
        kind = "ValueError" if isinstance(exc, ValueError) else type(exc).__name__
        return f"{kind}: {exc}"


if section("A-3"):
    # start values the model cannot be evaluated at must be an error in words, not an all-zero "fit"
    cases = [
        ("Global: tau below what the IRF resolves", lambda: NEW.fit_global_analysis(
            E_MAP, T_AX, [SIG4 / 3.0, 1000.0], tau_fixed=[False, False], **GKW), "shortest"),
        ("Global: a fixed tau below it", lambda: NEW.fit_global_analysis(
            E_MAP, T_AX, [SIG4 / 3.0, 1000.0], tau_fixed=[True, False], **GKW), "shortest"),
        ("Global: tau far beyond the fit range", lambda: NEW.fit_global_analysis(
            E_MAP, T_AX, [200.0, 5e6], tau_fixed=[False, False], **GKW), "100"),
        ("Global: FWHM = 0", lambda: NEW.fit_global_analysis(
            E_MAP, T_AX, [200.0, 2000.0], tau_fixed=[False, False], **{**GKW, "fwhm_init": 0.0}), "FWHM"),
        ("Global: no component and no offset", lambda: NEW.fit_global_analysis(
            E_MAP, T_AX, [], tau_fixed=[], **GKW), "component"),
        ("Kinetics: FWHM = 0", lambda: NEW.fit_single_trace(
            T_AX, Y_TR, tau_init=[100.0, 1000.0], tau_fixed=[False, False], **{**KKW, "fwhm_init": 0.0}), "FWHM"),
        ("Kinetics: FWHM < 0", lambda: NEW.fit_single_trace(
            T_AX, Y_TR, tau_init=[100.0, 1000.0], tau_fixed=[False, False], **{**KKW, "fwhm_init": -50.0}), "FWHM"),
        ("Kinetics: FWHM wider than the fit range", lambda: NEW.fit_single_trace(
            T_AX, Y_TR, tau_init=[100.0, 1000.0], tau_fixed=[False, False],
            **{**KKW, "fwhm_init": 10.0 * (T_AX[-1] - T_AX[0])}), "FWHM"),
    ]
    for label, fn, word in cases:
        msg = raises(fn)
        check(f"{label}: refused with a ValueError that names the limit",
              msg.startswith("ValueError") and word in msg, msg[:160] or "no exception: a result came back")
    # a start just outside the limit that the optimiser recovers from is fitted as in 1.4 (mid-review M4)
    for label, fn in (
            ("Global Nelder-Mead, tau 7 % below the limit",
             lambda T: T.fit_global_analysis(E_MAP, T_AX, [SIG4 * 0.93, 1000.0], tau_fixed=[False, False],
                                             method="nm", **GKW)),
            ("Kinetics, free FWHM starting above the fit range",
             lambda T: T.fit_single_trace(T_AX[:400], Y_TR[:400], tau_init=[100.0, 1000.0], tau_fixed=[False, False],
                                          **{**KKW, "fwhm_fixed": False,
                                             "fwhm_init": 1.2 * (T_AX[399] - T_AX[0])}))):
        ref = fn(OLD)
        try:
            got = fn(NEW)
            same = (np.array_equal(got["tau"], ref["tau"]) and np.array_equal(got["A"], ref["A"])
                    and np.array_equal(got["fit"], ref["fit"]))
            note = f"{got['tau']} vs {ref['tau']}"
        except Exception as exc:                # noqa: BLE001
            same, note = False, f"{type(exc).__name__}: {exc}"
        check(f"{label}: 1.4 gave a real fit here", float(np.max(np.abs(ref["fit"]))) > 0)
        check("... and this version gives the same numbers", same, note)
    ok = NEW.fit_global_analysis(E_MAP, T_AX, [SIG4, 1000.0], tau_fixed=[True, False], **GKW)
    check("a tau exactly on the limit is still accepted", np.isfinite(ok["info"]["rms"]) and ok["info"]["rss"] < 1e29)
    # through the window: a message box, no "Fit done"
    app.open_global_analysis(); pump(0.3)
    g = app._global_win
    g.var_n.set("2"); g.table.set_n(2)
    g.var_fw.set("0")
    g.run_fit(); wait(lambda: not g._running, 60); pump(0.3)
    check("Global window, FWHM 0: an error box and 'Fit failed.', no result",
          [b[0] for b in boxes] == ["showerror"] and "FWHM" in boxes[0][2]
          and g.var_status.get() == "Fit failed." and g._last is None, f"{boxes} {g.var_status.get()}")
    g._on_close(); pump(0.2)

# ---------------------------------------------------------------------------------------------
if section("A-4"):
    # the optimiser's own verdict is kept and the report is worded from it
    r = NEW.fit_single_trace(T_AX, Y_TR, tau_init=[100.0, 1000.0], tau_fixed=[False, False], **KKW)
    info = r["info"]
    check("Kinetics info carries success / status / message / nfev",
          all(k in info for k in ("success", "status", "message", "nfev")) and info.get("success") is True,
          str(sorted(info)))
    real_min = NEW._minimize
    calls = []

    def capped(fun, x0, **kw):
        kw = dict(kw, options=dict(kw["options"], maxiter=20))
        return real_min(lambda x: (calls.append(1), fun(x))[1], x0, **kw)
    NEW._minimize = capped
    try:
        r2 = NEW.fit_single_trace(T_AX, Y_TR, tau_init=[100.0, 1000.0], tau_fixed=[False, False], **KKW)
        n_called = len(calls)
        g2 = NEW.fit_global_analysis(E_MAP, T_AX, [200.0, 2000.0], tau_fixed=[False, False], method="nm", **GKW)
    finally:
        NEW._minimize = real_min
    check("a Kinetics fit cut off at the iteration limit says so in info",
          r2["info"].get("success") is False and "iteration" in str(r2["info"].get("message", "")).lower(),
          str({k: r2["info"].get(k) for k in ("success", "status", "message")}))
    check("Kinetics nfev is the number of loss evaluations made by the optimiser",
          r2["info"].get("nfev") == n_called, f"{r2['info'].get('nfev')} vs {n_called}")
    check("a Global (Nelder-Mead) fit cut off at the limit says so too",
          g2["info"].get("success") is False, str(g2["info"].get("message")))
    # one linear solve per evaluation of the model (counted there: since A-17 the kernel builds its
    # basis column by column instead of calling build_ga_basis)
    n_obj = []
    real_solve = NEW._lsqminnorm
    NEW._lsqminnorm = lambda *a, **k: (n_obj.append(1), real_solve(*a, **k))[1]
    try:
        g3 = NEW.fit_global_analysis(E_MAP, T_AX, [200.0, 2000.0], tau_fixed=[False, False], method="trf", **GKW)
    finally:
        NEW._lsqminnorm = real_solve
    check("Global TRF: success recorded, and the evaluation count is the real number of model evaluations",
          g3["info"].get("success") is True and g3["info"].get("n_objective") == len(n_obj),
          f"{g3['info'].get('n_objective')} vs {len(n_obj)} (nfev {g3['info'].get('nfev')})")
    check("the numbers written to exports are untouched (iters keeps its meaning)",
          g3["info"]["iters"] == g3["info"]["nfev"] and r["info"]["iters"] > 0)
    # the Kinetics report
    app.open_kinetics(); pump(0.3)
    k = app._kinetics_win
    NEW._minimize = capped
    try:
        k.run_fit(); wait(lambda: not k._running, 60); pump(0.3)
    finally:
        NEW._minimize = real_min
    text = k.txt.get("1.0", "end")
    check("Kinetics report of a fit cut off at the limit does not say 'converged'",
          "not converged" in text.lower() and "Fit converged" not in text, text[:90])
    check("... and the status line warns too", "not converged" in k.var_status.get(), k.var_status.get())
    k.run_fit(); wait(lambda: not k._running, 60); pump(0.3)
    text = k.txt.get("1.0", "end")
    check("a normal Kinetics fit still reports 'Fit converged'", text.startswith("Fit converged"), text[:60])
    k._on_close(); pump(0.2)

# ---------------------------------------------------------------------------------------------
if section("A-15"):
    # Global RMS must be over the cells that entered the loss
    kw = dict(GKW, beta_init=[0.8, 1.0], beta_fixed=[True, True], stretch_on=[True, False], irf_mode="skip")
    r = NEW.fit_global_analysis(E_MAP, T_AX, [200.0, 2000.0], tau_fixed=[False, False], method="nm", **kw)
    sig = r["fwhm"] / (2.0 * np.sqrt(2.0 * np.log(2.0)))
    used = T_AX > r["t0"] + 3.0 * sig
    resid = (E_MAP - r["fit"])[:, used]
    true_rms = float(np.sqrt(np.mean(resid ** 2)))
    check("skip mode: some delays are left out of the loss", 0 < used.sum() < T_AX.size, str(used.sum()))
    check("skip mode: rms is the root mean square over the fitted cells",
          abs(r["info"]["rms"] / true_rms - 1.0) < 1e-9, f"{r['info']['rms']:.6g} vs {true_rms:.6g}")
    r0 = NEW.fit_global_analysis(E_MAP, T_AX, [200.0, 2000.0], tau_fixed=[False, False], method="trf", **GKW)
    full = float(np.sqrt(np.mean((E_MAP - r0["fit"]) ** 2)))
    check("without a mask the rms is what it was (all cells)", abs(r0["info"]["rms"] / full - 1.0) < 1e-12)

# ---------------------------------------------------------------------------------------------
if section("A-16"):
    # EADS with two equal lifetimes: an error in words, and the window shows DADS without EADS
    A2 = np.random.default_rng(1).normal(size=(12, 2))
    msg = raises(lambda: NEW.compute_eads_from_dads(A2, [100.0, 100.0], False))
    check("two equal lifetimes: compute_eads_from_dads raises instead of returning NaN",
          msg.startswith("ValueError") and "100" in msg, msg[:120] or "returned")
    e, ts, B = NEW.compute_eads_from_dads(A2, [300.0, 100.0], False)
    eo, tso, Bo = OLD.compute_eads_from_dads(A2, [300.0, 100.0], False)
    check("distinct lifetimes: EADS unchanged", np.array_equal(e, eo) and np.array_equal(ts, tso) and np.array_equal(B, Bo))
    app.open_global_analysis(); pump(0.3)
    g = app._global_win
    g.var_n.set("2"); g.table.set_n(2)
    real_fit = NEW.fit_global_analysis

    def equal_taus(D, t, **kw):
        r = real_fit(D, t, **kw)
        r["tau"] = np.array([500.0, 500.0])
        return r
    NEW.fit_global_analysis = equal_taus
    try:
        res = run_global(g)
    finally:
        NEW.fit_global_analysis = real_fit
    check("Global window with equal lifetimes: no EADS is made up", res is not None and res["_eads"] is None)
    check("... the report says why", "EADS" in g.txt.get("1.0", "end") and "not available" in g.txt.get("1.0", "end"),
          g.txt.get("1.0", "end")[-160:])
    check("... DADS is drawn, the EADS panels are empty",
          len(g.ax_dads.lines) >= 2 and len(g.ax_eads.lines) == 0 and len(g.ax_eads_n.lines) == 0,
          f"{len(g.ax_dads.lines)} {len(g.ax_eads.lines)}")
    files = exported(g)
    check("... export writes DADS only", sorted(files) == ["DADS"], str(sorted(files)))
    g._on_close(); pump(0.2)

# ---------------------------------------------------------------------------------------------
if section("A-1"):
    # a lifetime that ended on an internal limit, or below a time bin, is flagged - numbers untouched
    r_new = NEW.fit_global_analysis(E_MAP, T_AX, [100.0, 1000.0, 10000.0], tau_fixed=[False] * 3, method="trf", **GKW)
    r_old = OLD.fit_global_analysis(E_MAP, T_AX, [100.0, 1000.0, 10000.0], tau_fixed=[False] * 3, method="trf", **GKW)
    check("default Global fit: same numbers as 1.4",
          np.array_equal(r_new["tau"], r_old["tau"]) and np.array_equal(r_new["A"], r_old["A"]))
    notes = r_new["info"].get("warnings", [])
    check("default Global fit (tau 1 ends on sigma/4): flagged as on the lower limit",
          abs(r_new["tau"][0] / SIG4 - 1) < 1e-3 and any("τ 1" in w and "limit" in w for w in notes), str(notes))
    k_new = NEW.fit_single_trace(T_AX, Y_TR, tau_init=[100.0, 1000.0], tau_fixed=[False, False], **KKW)
    k_old = OLD.fit_single_trace(T_AX, Y_TR, tau_init=[100.0, 1000.0], tau_fixed=[False, False], **KKW)
    check("default Kinetics fit: same numbers as 1.4",
          np.array_equal(k_new["tau"], k_old["tau"]) and np.array_equal(k_new["A"], k_old["A"]))
    dt = float(T_AX[1] - T_AX[0])
    short = [i for i, tv in enumerate(k_new["tau"]) if tv < dt]
    notes = k_new["info"].get("warnings", [])
    check("default Kinetics fit: a tau below one time bin is flagged",
          bool(short) and all(any(f"τ {i + 1}" in w for w in notes) for i in short), f"{k_new['tau']} {notes}")
    good = NEW.fit_single_trace(T_AX, Y_TR, tau_init=[150.0, 1200.0], tau_fixed=[False, False],
                                **{**KKW, "t0_fixed": False, "fwhm_fixed": False})
    check("a fit with sensible lifetimes carries no warning",
          good["info"].get("warnings") == [] and min(good["tau"]) > dt, f"{good['tau']} {good['info'].get('warnings')}")
    app.open_kinetics(); pump(0.3)
    k = app._kinetics_win
    k.var_wl.set("545"); k._on_wl_change()
    k.run_fit(); wait(lambda: not k._running, 60); pump(0.3)
    text = k.txt.get("1.0", "end")
    check("Kinetics window: the report and the status line carry the warning",
          "Warning" in text and "τ" in text.split("Warning", 1)[1] and "warning" in k.var_status.get().lower(),
          k.var_status.get())
    k._on_close(); pump(0.2)
    app.open_global_analysis(); pump(0.3)
    g = app._global_win
    run_global(g)
    check("Global window: the same", "Warning" in g.txt.get("1.0", "end") and "warning" in g.var_status.get().lower(),
          g.var_status.get())
    g._on_close(); pump(0.2)

# ---------------------------------------------------------------------------------------------
if section("S-3a"):
    # Kinetics: a fit that fails at a new wavelength must not leave the old wavelength's result on screen
    app.open_kinetics(); pump(0.3)
    k = app._kinetics_win
    k.var_wl.set("545"); k._on_wl_change()
    k.run_fit(); wait(lambda: not k._running, 60); pump(0.3)
    first_wl = k._last["_wl"]
    k.var_wl.set("450")                        # typed, Run pressed without leaving the box
    real_fit = NEW.fit_single_trace

    def failing(*a, **kw):
        raise NEW.FitInputError("planted: this fit fails")
    NEW.fit_single_trace = failing
    try:
        k.run_fit(); wait(lambda: not k._running, 60); pump(0.3)
    finally:
        NEW.fit_single_trace = real_fit
    title = k.ax_main.get_title()
    check("after the failed fit at 450 nm the 545 nm result is gone",
          k._last is None and [b[0] for b in boxes] == ["showerror"], f"{None if k._last is None else k._last['_wl']}")
    check("... and the plot shows the 450 nm trace without a fit line",
          "450" in title and len(k.ax_main.lines) == 2 and abs(first_wl - 545) < 3, f"{title} {len(k.ax_main.lines)}")
    # a failure at the same wavelength keeps the result that is still valid
    k.run_fit(); wait(lambda: not k._running, 60); pump(0.3)
    kept = k._last
    NEW.fit_single_trace = failing
    try:
        k.run_fit(); wait(lambda: not k._running, 60); pump(0.3)
    finally:
        NEW.fit_single_trace = real_fit
    check("a failed re-run at the same wavelength keeps the previous result", k._last is kept and kept is not None)
    k._on_close(); pump(0.2)

top.destroy()
finish()
