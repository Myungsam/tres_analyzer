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
    x0 = np.array([3.0, -2.0, 0.0])
    check("inside the limits it is scipy's own simplex (5 % up; 0.00025 from zero)",
          np.allclose(NEW._simplex(x0, np.full(3, -50.0), np.full(3, 50.0)),
                      [[3.0, -2.0, 0.0], [3.15, -2.0, 0.0], [3.0, -2.1, 0.0], [3.0, -2.0, 0.00025]]))

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

finish()
