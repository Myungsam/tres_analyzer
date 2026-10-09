"""What the final review of 1.6 found (its finding IDs FA-n / FB-n as section names). See _harness.py."""
import os

import numpy as np

from _harness import *                        # noqa: F401,F403
from _harness import NEW, SAMPLE_A, TMP, boxes, check, finish, make_app, make_phu, pump, section, wait

S2 = 2.0 * np.sqrt(2.0 * np.log(2.0))


def two_exp(t, t0=400.0, fwhm=40.0, taus=(80.0, 900.0), amps=(600.0, 300.0)):
    return sum(a * NEW.exp_irf_conv(t, tau, t0, fwhm) for a, tau in zip(amps, taus))


# ---------------------------------------------------------------------------------------------
if section("FA-1"):
    # a start on (or below) the lower lifetime limit, with time bins under 10 ps: the limit is below
    # 1 ps, its log negative, and Nelder-Mead's first simplex used to fold onto the start
    t = np.arange(1500) * 4.0
    rng = np.random.default_rng(3)
    y = rng.poisson(two_exp(t) + 2.0).astype(float) - 2.0
    floor = 0.4

    def kin(start):
        return NEW.fit_single_trace(t, y, tau_init=np.array([start, 500.0]), tau_fixed=np.zeros(2, bool),
                                    t0_init=400.0, t0_fixed=True, fwhm_init=40.0, fwhm_fixed=True)

    good = kin(100.0)
    for start in (0.2, floor, 0.6):
        r = kin(start)
        check(f"Kinetics, 4 ps bins, start {start:g} ps: the lifetime leaves the limit and the fit is the one a "
              f"start of 100 ps finds", abs(r["tau"][0] / good["tau"][0] - 1) < 0.02
              and r["info"]["rms"] < 1.01 * good["info"]["rms"],
              f"tau {r['tau']} RMS {r['info']['rms']:.4g} vs {good['tau']} RMS {good['info']['rms']:.4g}")
    D = np.vstack([y, 0.5 * y, 0.25 * y])

    def glob(start):
        return NEW.fit_global_analysis(D, t, np.array([start, 500.0]), 400.0, 40.0, np.zeros(2, bool), True, True,
                                       False, method="nm")

    good = glob(100.0)
    r = glob(floor)
    check("Global Nelder-Mead, start on the limit: the same", abs(r["tau"].min() / good["tau"].min() - 1) < 0.02
          and r["info"]["rms"] < 1.01 * good["info"]["rms"], f"{r['tau']} vs {good['tau']}")
    sim = NEW._simplex(np.array([np.log(0.4), 5.0, 0.0]), np.array([np.log(0.4), 0.0, -1.0]), np.array([10.0, 5.0, 1.0]))
    check("every corner of the first simplex is inside the limits and away from the start",
          all(sim[k + 1, k] != sim[0, k] for k in range(3)) and (sim >= [np.log(0.4), 0.0, -1.0]).all()
          and (sim <= [10.0, 5.0, 1.0]).all(), str(sim))
    # inside the limits: scipy's own simplex, to the last bit (FC-1). Taken from scipy itself.
    from scipy.optimize import minimize
    rng = np.random.default_rng(11)
    differ = 0
    for _ in range(300):
        x0 = np.append(rng.uniform(-40.0, 40.0, 3), 0.0)
        res = minimize(lambda x: float(np.sum(x ** 2)), x0, method="Nelder-Mead",
                       options={"maxiter": 0, "disp": False})
        own = NEW._simplex(x0, np.full(4, -1e9), np.full(4, 1e9))
        if not np.array_equal(res.final_simplex[0][np.lexsort(res.final_simplex[0].T[::-1])],
                              own[np.lexsort(own.T[::-1])]):
            differ += 1
    check("inside the limits it is scipy's own simplex, bit for bit (300 random starts)", differ == 0, f"{differ} differ")

# ---------------------------------------------------------------------------------------------
if section("FA-3"):
    t = np.arange(400) * 16.0
    y = two_exp(t)
    for bad in (0.0, -5.0, float("nan")):
        for name, call in (
                ("Kinetics", lambda: NEW.fit_single_trace(
                    t, y, tau_init=np.array([100.0]), tau_fixed=np.zeros(1, bool), t0_init=400.0, t0_fixed=True,
                    fwhm_init=bad, fwhm_fixed=False)),
                ("Global TRF", lambda: NEW.fit_global_analysis(
                    np.vstack([y, y]), t, np.array([100.0]), 400.0, bad, np.zeros(1, bool), True, False, False)),
                ("Global NM", lambda: NEW.fit_global_analysis(
                    np.vstack([y, y]), t, np.array([100.0]), 400.0, bad, np.zeros(1, bool), True, False, False,
                    method="nm"))):
            try:
                call()
                got = "a result came back"
            except NEW.FitInputError as exc:
                got = "ok" if "FWHM" in str(exc) else str(exc)
            except Exception as exc:          # noqa: BLE001
                got = f"{type(exc).__name__}: {exc}"
            check(f"{name}, FWHM {bad} with 'fixed' off: refused in words", got == "ok", got)

# ---------------------------------------------------------------------------------------------
if section("FA-8"):
    t = np.arange(40) * 16.0
    y = two_exp(t, t0=560.0, fwhm=60.0)
    try:
        NEW.fit_global_analysis(np.vstack([y, y]), t, np.array([100.0, 500.0]), 560.0, 60.0, np.zeros(2, bool),
                                True, True, False, stretch_on=np.array([True, False]), irf_mode="skip")
        got = "a result came back"
    except NEW.FitInputError as exc:
        got = "ok" if "Not enough data points" in str(exc) else str(exc)
    check("Global, skip mode with too few delays after the IRF: refused, as the Kinetics fit does", got == "ok", got)

# ---------------------------------------------------------------------------------------------
if section("FA-4"):
    x = np.arange(6000) * 4.0
    peak = 1e4 * np.exp(-0.5 * ((x - 4000.0) / (200.0 / S2)) ** 2) + 2000.0
    full = NEW.fwhm_of(peak, 4.0)[1]
    padded = NEW.fwhm_of(np.concatenate([peak, np.zeros(60000)]), 4.0)[1]
    check("a 200 ps peak on a 20 % background reads 200 ps, also when the record goes on empty after it",
          abs(full - 200.0) < 2.0 and abs(padded - 200.0) < 2.0, f"{full:.2f} {padded:.2f}")
    check("an all-zero trace has no width", NEW.fwhm_of(np.zeros(100), 4.0)[1] == 0.0)

# ---------------------------------------------------------------------------------------------
if section("FA-7"):
    import time
    p = make_phu(os.path.join(TMP, "many.phu"), patch={("HistoResult_NumberOfCurves", -1): (NEW.TY_INT8, 30_000_000)})
    t0 = time.perf_counter()
    try:
        NEW.read_phu(p)
        got = "read"
    except ValueError as exc:
        got = "ok" if "do not fit" in str(exc) else str(exc)
    except Exception as exc:                  # noqa: BLE001
        got = type(exc).__name__
    check("a header claiming 30 million curves: a ValueError at once", got == "ok" and time.perf_counter() - t0 < 0.5,
          f"{got} after {time.perf_counter() - t0:.2f} s")

# ---------------------------------------------------------------------------------------------
if section("FA-2"):
    import threading
    top, app = make_app(SAMPLE_A)
    app.open_kinetics(); pump(0.3)
    k = app._kinetics_win
    real = NEW.fit_single_trace
    gate = threading.Event()

    def slow(*a, stop_check=None, **kw):
        while not (stop_check and stop_check()) and not gate.is_set():
            gate.wait(0.02)
        if stop_check and stop_check():
            raise NEW.FitStopped()
        return real(*a, stop_check=stop_check, **kw)
    NEW.fit_single_trace = slow
    try:
        k.run_fit(); pump(0.2)
        k.var_wl.set(f"{float(k.var_wl.get()) + 20:.2f}"); k._on_wl_change(); pump(0.1)
        k.stop_fit(); pump(0.1)
        check("(Stop pressed after λ was changed: the status reads Stopping...)", k.var_status.get() == "Stopping...",
              k.var_status.get())
        wait(lambda: not k._running, 20); pump(0.3)
        check("when the fit has ended the status says so, not 'Stopping...'",
              not k._running and k.var_status.get() == "Stopped by user.", k.var_status.get())
    finally:
        gate.set()
        NEW.fit_single_trace = real
    top.destroy()

# ---------------------------------------------------------------------------------------------
if section("FB-3"):
    class Screen:
        """A window on a 1920 x 1080 display at 150 %."""
        def winfo_fpixels(self, what):
            return 144.0

        def winfo_screenwidth(self):
            return 1920

        def winfo_screenheight(self):
            return 1080

    made = {}

    class Win(Screen):
        def title(self, *a): pass
        def configure(self, **k): pass
        def protocol(self, *a): pass
        def geometry(self, g): made["geometry"] = g
        def minsize(self, w, h): made["minsize"] = (w, h)

    real = NEW.tk.Toplevel
    NEW.tk.Toplevel = lambda parent: Win()
    try:
        NEW._AnalysisDialog(type("App", (), {"win": None})(), "t", "1500x960", (1100, 720))
    finally:
        NEW.tk.Toplevel = real
    w, h = (int(v) for v in made["geometry"].split("x"))
    check("a pop-up window on a 1920x1080 display at 150 %: neither its size nor its smallest size is larger "
          "than the screen has room for", w <= 1860 and h <= 930 and made["minsize"][0] <= 1860 and made["minsize"][1] <= 930
          and made["minsize"][0] <= w and made["minsize"][1] <= h, f"{made}")

# ---------------------------------------------------------------------------------------------
if section("FB-8"):
    top, app = make_app(SAMPLE_A)
    m = app.model
    one = m.wls[10:11]
    ext = app._extent_of(one, m.times[:50])
    check("the picture of a zoom that holds one curve is one map column wide, not the whole map",
          abs((ext[1] - ext[0]) - m.wl_step) < 1e-9 and abs((ext[0] + ext[1]) / 2 - one[0]) < 1e-9, str(ext[:2]))
    check("no error box", not [b for b in boxes if b[0] == "showerror"], str(boxes))
    top.destroy()

# ---------------------------------------------------------------------------------------------
if section("FC-2"):
    import threading
    top, app = make_app(SAMPLE_A)
    app.open_global_analysis(); pump(0.3)
    g = app._global_win
    real = NEW.fit_global_analysis
    gate = threading.Event()

    def slow(*a, stop_check=None, **kw):
        while not (stop_check and stop_check()) and not gate.is_set():
            gate.wait(0.02)
        if stop_check and stop_check():
            raise NEW.GlobalAnalysisStopped()
        return real(*a, stop_check=stop_check, **kw)
    NEW.fit_global_analysis = slow
    try:
        g.var_n.set("2"); g.table.set_n(2)
        g.run_fit(); pump(0.2)
        g._job += 1                           # what Reset does to a running fit, without stopping it yet
        g.stop_fit(); pump(0.05)
        check("(Global: Stop pressed on a run that was already set aside reads Stopping...)",
              g.var_status.get() == "Stopping...", g.var_status.get())
        wait(lambda: not g._running, 20); pump(0.3)
        check("Global: when the fit has ended the status says so, not 'Stopping...'",
              not g._running and g.var_status.get() == "Stopped by user.", g.var_status.get())
        g.run_fit(); pump(0.2)
        g.reset(); pump(0.1)
        wait(lambda: not g._running, 20); pump(0.3)
        check("Global: Reset alone (no Stop) still ends on its own text", g.var_status.get() == "Reset to defaults.",
              g.var_status.get())
    finally:
        gate.set()
        NEW.fit_global_analysis = real
    top.destroy()

# ---------------------------------------------------------------------------------------------
if section("FC-3"):
    x = np.arange(65536) * 4.0
    rng = np.random.default_rng(0)

    def peak(centre, fwhm=300.0, height=20000.0):
        return height * np.exp(-0.5 * ((x - centre) / (fwhm / S2)) ** 2)

    w = NEW.fwhm_of(rng.poisson(peak(600.0)).astype(float), 4.0)[1]
    check("a 300 ps peak with no background at the very start of the record reads 300 ps (within 1 %)",
          abs(w - 300.0) < 3.0, f"{w:.2f}")
    w = NEW.fwhm_of(rng.poisson(peak(8000.0)).astype(float), 4.0)[1]
    check("the same peak further in", abs(w - 300.0) < 3.0, f"{w:.2f}")
    body = 1e4 * np.exp(-0.5 * ((np.arange(6000) * 4.0 - 4000.0) / (200.0 / S2)) ** 2) + 2000.0
    w = NEW.fwhm_of(np.concatenate([np.zeros(60000), body, np.zeros(3000)]), 4.0)[1]
    check("a 200 ps peak on a 20 % background with empty bins before AND after it reads 200 ps",
          abs(w - 200.0) < 2.0, f"{w:.2f}")
    noisy = rng.poisson(peak(8000.0) + 40.0).astype(float)
    noisy[20000:] = 0.0
    w = NEW.fwhm_of(noisy, 4.0)[1]
    check("with Poisson background of 40 counts and an empty tail: within 2 %", abs(w - 300.0) < 6.0, f"{w:.2f}")
    one = np.zeros(50); one[7] = 5.0
    check("a single bin with counts, or none: no width", NEW.fwhm_of(one, 4.0)[1] == 0.0
          and NEW.fwhm_of(np.zeros(50), 4.0)[1] == 0.0, str(NEW.fwhm_of(one, 4.0)))
    p = NEW.read_phu(SAMPLE_A)
    w = NEW.fwhm_of(p["counts"][0].astype(float), p["res_ps"])[1]
    check("sample A's IRF reads 301.7 ps", abs(w - 301.67) < 0.05, f"{w:.3f}")

# ---------------------------------------------------------------------------------------------
if section("FC-4"):
    # FA-5: every column gets its number format - on a sheet that starts with two columns and refuses
    # a column it does not have, as an Origin sheet does
    import sys
    import types

    class Column:
        def __init__(self):
            self.format = None

        def SetDataFormat(self, value):
            self.format = value

    class Inner:
        def __init__(self, sheet):
            self._sheet = sheet

        def __getitem__(self, j):
            if not 0 <= j < len(self._sheet.columns):
                raise IndexError(j)
            return self._sheet.columns[j]

    class Sheet:
        def __init__(self):
            self.columns = [Column(), Column()]
            self.data = {}
            self.obj = Inner(self)

        @property
        def cols(self):
            return len(self.columns)

        @cols.setter
        def cols(self, n):
            self.columns = (self.columns + [Column() for _ in range(n)])[:n]

        def clear(self):
            self.data = {}

        def from_list(self, j, values, *a, **k):
            while len(self.columns) <= j:
                self.columns.append(Column())
            self.data[j] = list(values)

    saved = {k: sys.modules.get(k) for k in ("originpro", "originpro.config")}
    pkg, cfg = types.ModuleType("originpro"), types.ModuleType("originpro.config")
    cfg.po = types.SimpleNamespace(DF_DOUBLE="double")
    pkg.config = cfg
    sys.modules["originpro"], sys.modules["originpro.config"] = pkg, cfg
    try:
        ws = Sheet()
        NEW._origin_put(ws, [np.arange(4.0) + j for j in range(6)])
    finally:
        for name, mod in saved.items():
            if mod is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = mod
    check("all six columns of a sheet that started with two are made columns of doubles",
          [c.format for c in ws.columns] == ["double"] * 6, str([c.format for c in ws.columns]))
    check("... and hold their numbers", ws.cols == 6 and all(ws.data[j] == list(np.arange(4.0) + j) for j in range(6)))

# ---------------------------------------------------------------------------------------------
if section("FC-6"):
    p = make_phu(os.path.join(TMP, "bins.phu"), ncurves=3, nbins=64,
                 patch={("HistResDscr_HistogramBins", 0): (NEW.TY_INT8, 128)})
    try:
        NEW.read_phu(p)
        got = "read"
    except ValueError as exc:
        got = str(exc)
    check("curve 0 claiming more bins than the others: refused as curves with different time axes "
          "(not as a file that is too short)", "different time axes" in got, got)
    p = make_phu(os.path.join(TMP, "many2.phu"), patch={("HistoResult_NumberOfCurves", -1): (NEW.TY_INT8, 30_000_000)})
    try:
        NEW.read_phu(p)
        got = "read"
    except ValueError as exc:
        got = str(exc)
    check("a header claiming 30 million curves is still refused at once", "do not fit" in got, got)
    q = NEW.read_phu(SAMPLE_A)
    check("a good file opens", q["ncurves"] == 64 and q["counts"].shape == (64, q["nbins"]))

# ---------------------------------------------------------------------------------------------
if section("FC-8"):
    t = np.arange(1500) * 4.0
    rng = np.random.default_rng(5)
    y = rng.poisson(two_exp(t) + 2.0).astype(float) - 2.0

    def kin(fwhm_start, **kw):
        args = dict(tau_init=np.array([100.0, 1000.0]), tau_fixed=np.zeros(2, bool), t0_init=400.0, t0_fixed=True,
                    fwhm_init=fwhm_start, fwhm_fixed=False)
        args.update(kw)
        return NEW.fit_single_trace(t, y, **args)

    r = kin(1.0)                                  # on the lower limit (a quarter of a 4 ps bin)
    stuck = abs(r["fwhm"] - 1.0) < 1e-2
    check("a free FWHM that ends on its limit is reported (the fit used to say nothing)",
          (not stuck) or any("FWHM ended on the lower limit" in w for w in r["info"]["warnings"]),
          f"FWHM {r['fwhm']:.4g} {r['info']['warnings']}")
    check("(this start does end on the limit: the case exists)", stuck, f"FWHM {r['fwhm']:.4g}")
    r = kin(30.0)
    check("a free FWHM that is fitted (true value 40 ps) carries no such remark",
          abs(r["fwhm"] - 40.0) < 4.0 and not any("ended on" in w for w in r["info"]["warnings"]),
          f"FWHM {r['fwhm']:.4g} {r['info']['warnings']}")
    r = kin(40.0, fwhm_fixed=True)
    check("nor does a fit with nothing on a limit", not any("ended on" in w for w in r["info"]["warnings"]),
          str(r["info"]["warnings"]))
    D = np.vstack([y, 0.5 * y])
    g = NEW.fit_global_analysis(D, t, np.array([100.0, 1000.0]), 400.0, 1.0, np.zeros(2, bool), True, False, False,
                                method="nm")
    check("Global: the same remark when its free FWHM ends on the limit",
          abs(g["fwhm"] - 1.0) > 1e-2 or any("FWHM ended on the lower limit" in w for w in g["info"]["warnings"]),
          f"FWHM {g['fwhm']:.4g} {g['info']['warnings']}")

finish()
