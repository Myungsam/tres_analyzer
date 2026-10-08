"""Stage 3, group G6: speed (review items D-25, B-21, A-17, B-13). Results must not move; see _harness.py."""
import os
import subprocess
import sys

from _harness import *                        # noqa: F401,F403
from _harness import SAMPLE_B, NEW, OLD, ROOT, SAMPLE_A, boxes, check, finish, make_app, np, pump, section, wait
import _versions

# These checks compare with 1.4: the rules 1.6 changed on purpose are put back (see _versions.rules_of_1_5).
_versions.rules_of_1_5(NEW)


def shot(app):
    return np.asarray(app.canvas.buffer_rgba()).copy()


def differ(a, b):
    return int((a != b).any(axis=2).sum()) if a.shape == b.shape else -1


# ---------------------------------------------------------------------------------------------
if section("D-25"):
    # the program does not import matplotlib.pyplot (it never used it)
    code = ("import sys; sys.dont_write_bytecode = True; sys.path.insert(0, r'%s'); "
            "import tcspc_analysis.app; print('pyplot' if 'matplotlib.pyplot' in sys.modules else 'clean', "
            "__import__('matplotlib').get_backend())" % ROOT)
    out = subprocess.run([sys.executable, "-B", "-c", code], capture_output=True, text=True).stdout.split()
    check("importing the program does not load matplotlib.pyplot", out[:1] == ["clean"], str(out))
    check("the TkAgg backend is still the one selected", len(out) > 1 and out[1].lower() == "tkagg", str(out))

# ---------------------------------------------------------------------------------------------
if section("B-21"):
    # opening a file builds the model once
    top, app = make_app(SAMPLE_A)
    n = {"rebuild": 0, "bg": 0}
    real_rb, real_bg = NEW.TRESModel.rebuild, NEW.TRESModel.subtract_background
    NEW.TRESModel.rebuild = lambda self: (n.__setitem__("rebuild", n["rebuild"] + 1), real_rb(self))[1]
    NEW.TRESModel.subtract_background = lambda self: (n.__setitem__("bg", n["bg"] + 1), real_bg(self))[1]
    try:
        app.load(SAMPLE_B); pump(0.2)
    finally:
        NEW.TRESModel.rebuild, NEW.TRESModel.subtract_background = real_rb, real_bg
    check("load(): one rebuild, and the background taken off twice at most (once more for the default window)",
          n["rebuild"] == 1 and n["bg"] <= 2, str(n))
    ref = OLD.TRESModel(OLD.read_phu(SAMPLE_B))
    ref.first_is_irf, ref.t0_align, ref.rebin, ref.bg_sub = True, False, 4, True
    ref.wl_offset = -50.0
    ref.t_max_ps = ref.t_data_ps
    ref.rebuild()
    ref.bg_lo_ps, ref.bg_hi_ps = round(ref.t_lo, 1) + 0.0, round(ref.t_lo + 100.0, 1) + 0.0
    ref.subtract_background()
    m = app.model
    check("the loaded model is the one 1.4 builds for the same settings",
          np.array_equal(m.E, ref.E, equal_nan=True) and np.array_equal(m.wls, ref.wls)
          and np.array_equal(m.spec_total, ref.spec_total, equal_nan=True) and m.vmax == ref.vmax,
          f"{m.E.shape} {ref.E.shape}")
    check("TRESModel(phu) on its own still builds itself (other code relies on it)",
          hasattr(NEW.TRESModel(m.phu), "E"))
    top.destroy()

# ---------------------------------------------------------------------------------------------
if section("A-17"):
    # a fixed component is not recomputed in every evaluation - and nothing changes in the result
    phu = NEW.read_phu(SAMPLE_A)
    mdl = NEW.TRESModel(phu)
    mdl.rebin = 4
    mdl.rebuild()
    t, E = mdl.times.copy(), mdl.E.copy()
    y = E[int(np.argmin(np.abs(mdl.wls - 545.0)))].copy()
    t0, fw = float(mdl.irf_peak_ps - mdl.t0), float(mdl.irf_fwhm_ps)
    calls = {"n": 0}
    real = NEW.exp_irf_conv
    NEW.exp_irf_conv = lambda *a, **k: (calls.__setitem__("n", calls["n"] + 1), real(*a, **k))[1]
    try:
        kw = dict(tau_init=[100.0, 1000.0, 5000.0], tau_fixed=[False, True, False], t0_init=t0, fwhm_init=fw,
                  t0_fixed=True, fwhm_fixed=True, has_inf=True, irf_mode="numerical")
        a = NEW.fit_single_trace(t, y, **kw)
        n_kin = calls["n"]
        calls["n"] = 0
        gkw = dict(t0_init=t0, fwhm_init=fw, t0_fixed=True, fwhm_fixed=True, has_inf=True, method="nm")
        g = NEW.fit_global_analysis(E, t, [200.0, 2000.0], tau_fixed=[False, True], **gkw)
        n_glob = calls["n"]
    finally:
        NEW.exp_irf_conv = real
    b = OLD.fit_single_trace(t, y, **kw)
    go = OLD.fit_global_analysis(E, t, [200.0, 2000.0], tau_fixed=[False, True], **gkw)
    evals_k, evals_g = a["info"]["nfev"] + 1, g["info"]["n_objective"]
    check("Kinetics, 3 components (one fixed) + offset, IRF fixed: the two fixed columns are computed once",
          n_kin <= 2 * evals_k + 4, f"{n_kin} model columns for {evals_k} evaluations (was 4 each)")
    check("Global, 2 components (one fixed) + offset: the same",
          n_glob <= 1 * evals_g + 4, f"{n_glob} columns for {evals_g} evaluations (was 3 each)")
    check("Kinetics result identical to 1.4, bit for bit",
          np.array_equal(a["tau"], b["tau"]) and np.array_equal(a["A"], b["A"]) and np.array_equal(a["fit"], b["fit"]))
    check("Global result identical to 1.4, bit for bit",
          np.array_equal(g["tau"], go["tau"]) and np.array_equal(g["A"], go["A"]) and np.array_equal(g["fit"], go["fit"]))
    # free IRF: nothing may be reused wrongly
    kw2 = dict(kw, t0_fixed=False, fwhm_fixed=False)
    a2, b2 = NEW.fit_single_trace(t, y, **kw2), OLD.fit_single_trace(t, y, **kw2)
    check("with a free IRF the result is still 1.4's", np.array_equal(a2["tau"], b2["tau"]) and np.array_equal(a2["fit"], b2["fit"]))

# ---------------------------------------------------------------------------------------------
if section("B-13"):
    # colormap, log colour, contrast and zoom change the picture without rebuilding the whole figure
    top, app = make_app(SAMPLE_A)
    pump(0.2)
    built = {"n": 0}
    real_clear = app.ax_hist.clear
    app.ax_hist.clear = lambda *a, **k: (built.__setitem__("n", built["n"] + 1), real_clear(*a, **k))[1]
    m = app.model
    actions = [
        ("another colormap", lambda: (app.var_cmap.set("viridis"), app._on_colormap())),
        ("Log color off", lambda: (app.var_log.set(False), app._on_log_color())),
        ("Log color on again", lambda: (app.var_log.set(True), app._on_log_color())),
        ("a manual contrast", lambda: (setattr(app, "clim", (3.0, 400.0)), app._recolor())),
        ("Auto contrast", app.reset_contrast),
        ("a zoom", lambda: (setattr(app, "view", (float(m.wls[10]), float(m.wls[40]), m.t_lo + 500, m.t_lo + 6000)),
                            app._reframe())),
        ("Reset zoom", app.reset_view),
    ]
    for label, act in actions:
        built["n"] = 0
        act(); pump(0.1)
        quick = shot(app)
        n_quick = built["n"]
        app.redraw(full=True); pump(0.1)
        full = shot(app)
        d = differ(quick, full)
        check(f"{label}: no rebuild of the figure, and the picture is the one a full redraw gives",
              n_quick == 0 and 0 <= d < 200, f"rebuilt {n_quick}x, {d} pixels differ")
    app.cursor, app.pinned = (m.n_w // 2, m.n_t // 3), True
    app.update_cursor()
    app.var_cmap.set("turbo"); app._on_colormap(); pump(0.1)
    quick = shot(app)
    app.redraw(full=True); pump(0.1)
    check("with a pinned cursor the quick path keeps the crosshair and the curves", 0 <= differ(quick, shot(app)) < 200)
    top.destroy()

finish()
