"""Stage 3, group G7: fit changes that alter results (review items A-2, C-8, A-1 bounds, A-10, A-13).
See _harness.py. The before / after numbers on the real files are results_probe.py's."""
import numpy as np

from _harness import *                        # noqa: F401,F403
from _harness import SAMPLE_B, NEW, OLD, SAMPLE_A, boxes, check, finish, make_app, pump, section, wait
import _versions

S2 = 2.0 * np.sqrt(2.0 * np.log(2.0))


def small_map():
    """A quick map of the sample A record: 64 ps bins, every fourth curve."""
    m = NEW.TRESModel(NEW.read_phu(SAMPLE_A), build=False)
    m.rebin = 16
    m.rebuild()
    return m, m.E[::4, :].copy(), m.times.copy(), float(m.irf_peak_ps), float(m.irf_fwhm_ps)


def cells(res, n_w):
    return res["info"]["rss"] / res["info"]["rms"] ** 2 / n_w


# ---------------------------------------------------------------------------------------------
if section("A-2"):
    m, D, t, t0, fw = small_map()
    st = np.array([True, False])
    kept = int((t > t0 + 3.0 * fw / S2).sum())
    base = dict(tau_fixed=np.zeros(2, bool), has_inf=False, stretch_on=st, irf_mode="skip")
    for method in ("nm", "trf"):
        for free in ("t0", "fwhm"):
            kw = dict(base, t0_fixed=free != "t0", fwhm_fixed=free != "fwhm", method=method)
            try:
                r = NEW.fit_global_analysis(D, t, np.array([200.0, 2000.0]), t0, fw, **kw)
            except NEW.FitInputError as exc:
                check(f"skip, {method}, free {free}: the fit runs", False, str(exc))
                continue
            check(f"skip, {method}, free {free}: the loss covers the delays chosen at the start "
                  f"({kept} of {t.size})", abs(cells(r, D.shape[0]) - kept) < 0.5,
                  f"{cells(r, D.shape[0]):.1f}; t0 {r['t0']:.6g}, FWHM {r['fwhm']:.6g}")
            check(f"skip, {method}, free {free}: the result says that the data hardly determine it",
                  any('"skip"' in w for w in r["info"]["warnings"]), str(r["info"]["warnings"]))
        # nothing free in the IRF: the mask is what it always was, so is the result
        # (compared under the 1.5 limits - A-1 changed those on purpose)
        back = _versions.rules_of_1_5(NEW)
        kw = dict(base, t0_fixed=True, fwhm_fixed=True, method=method)
        new = NEW.fit_global_analysis(D, t, np.array([200.0, 2000.0]), t0, fw, **kw)
        old = OLD.fit_global_analysis(D, t, np.array([200.0, 2000.0]), t0, fw, **kw)
        check(f"skip, {method}, IRF fixed: identical to 1.4",
              all(np.array_equal(new[k], old[k]) for k in ("tau", "beta", "A", "fit")),
              f"{new['tau']} vs {old['tau']}")
        check(f"skip, {method}, IRF fixed: no warning about skip",
              not any('"skip"' in w for w in new["info"]["warnings"]))
        back()
    # the other IRF modes never had a mask
    kw = dict(base, irf_mode="numerical", t0_fixed=False, fwhm_fixed=True, method="trf")
    back = _versions.rules_of_1_5(NEW)
    new = NEW.fit_global_analysis(D, t, np.array([200.0, 2000.0]), t0, fw, **kw)
    back()
    old = OLD.fit_global_analysis(D, t, np.array([200.0, 2000.0]), t0, fw, **kw)
    check("numerical, free t0: identical to 1.4",
          all(np.array_equal(new[k], old[k]) for k in ("tau", "beta", "A", "fit")) and new["t0"] == old["t0"])

# ---------------------------------------------------------------------------------------------
if section("A-13"):
    x = np.arange(2000) * 4.0

    def gauss(fwhm, shift=0.0, height=1e4):
        return height * np.exp(-0.5 * ((x - 4000.0 - shift) / (fwhm / S2)) ** 2)

    for true in (30.0, 60.0, 200.0):
        got = [NEW.fwhm_of(gauss(true, s), 4.0)[1] for s in (0.0, 1.0, 2.0, 3.0)]
        check(f"Gaussian of {true:g} ps at 4 ps per bin: within 2 % at four sub-bin positions",
              all(abs(g - true) <= 0.02 * true for g in got), str(got))
    check("a flat background of 20 % of the peak does not widen it",
          abs(NEW.fwhm_of(gauss(200.0) + 2000.0, 4.0)[1] - 200.0) <= 4.0,
          str(NEW.fwhm_of(gauss(200.0) + 2000.0, 4.0)[1]))
    check("a flat trace has no width", NEW.fwhm_of(np.full(500, 7.0), 4.0)[1] == 0.0,
          str(NEW.fwhm_of(np.full(500, 7.0), 4.0)))
    edge = np.zeros(500); edge[0] = 100.0; edge[1] = 60.0; edge[2] = 20.0
    pk, w = NEW.fwhm_of(edge, 4.0)
    check("a peak in the first bin: finite, measured on the side that exists", pk == 0.0 and 0 < w < 12.0, f"{pk} {w}")
    p = NEW.read_phu(SAMPLE_A)
    irf = p["counts"][0].astype(float)
    new, old = NEW.fwhm_of(irf, p["res_ps"]), OLD.fwhm_of(irf, p["res_ps"])
    check("sample A IRF: about 302 ps (308 when whole bins are counted)", 299.0 < new[1] < 305.0 and old[1] > 307.9,
          f"{new} {old}")
    check("the peak position is unchanged", new[0] == old[0], f"{new[0]} {old[0]}")
    m = NEW.TRESModel(p)
    check("the model carries the new width", m.irf_fwhm_ps == new[1] and m.irf_peak_ps == old[0])

# ---------------------------------------------------------------------------------------------
if section("A-1"):
    m = NEW.TRESModel(NEW.read_phu(SAMPLE_A))
    t, t0, fw = m.times, float(m.irf_peak_ps), float(m.irf_fwhm_ps)
    floor = m.dt_ps / 10.0
    span = float(t[-1] - t[0])

    def kinetics(y, tau=(100.0, 1000.0), fixed=(False, False), **kw):
        args = dict(tau_init=np.array(tau), tau_fixed=np.array(fixed), t0_init=t0, t0_fixed=True,
                    fwhm_init=fw, fwhm_fixed=True, has_inf=False, irf_mode="numerical")
        args.update(kw)
        return NEW.fit_single_trace(t, y, **args)

    def globalfit(D, tau=(100.0, 1000.0), method="trf", **kw):
        args = dict(tau_fixed=np.zeros(len(tau), bool), t0_fixed=True, fwhm_fixed=True, has_inf=False,
                    method=method)
        args.update(kw)
        return NEW.fit_global_analysis(D, t, np.array(tau), t0, fw, **args)

    # the default Kinetics fit on a trace with a scatter spike (it ran off to 1e-10 ps and A = 1e16)
    wi = int(np.argmin(np.abs(m.wls - 580.0)))
    y = m.E[wi, :]
    r = kinetics(y)
    check("Kinetics, default fit at 580 nm: no lifetime below the limit, amplitudes of a sane size",
          r["tau"].min() >= floor * (1 - 1e-9) and np.abs(r["A"]).max() < 1e3 * np.nanmax(y) * span / floor,
          f"tau {r['tau']}, A {r['A']}")
    check("... the lifetime on the limit is reported as one", any("lower limit" in w for w in r["info"]["warnings"]),
          str(r["info"]["warnings"]))
    back = _versions.rules_of_1_5(NEW)
    free = kinetics(y)
    back()
    check("... and the fit is as good as the unlimited one (RMS within 2 %)",
          r["info"]["rms"] <= 1.02 * free["info"]["rms"], f"{r['info']['rms']:.5g} vs {free['info']['rms']:.5g}")
    check("with the 1.5 rules back the Kinetics kernel is 1.4's, bit for bit",
          all(np.array_equal(free[k], OLD.fit_single_trace(
              t, y, tau_init=np.array([100.0, 1000.0]), tau_fixed=np.zeros(2, bool), t0_init=t0, t0_fixed=True,
              fwhm_init=fw, fwhm_fixed=True, has_inf=False, irf_mode="numerical")[k]) for k in ("tau", "A", "fit")))
    # a start outside the limits is moved onto them, not refused
    r = kinetics(y, tau=(1e-6, 1e12))
    check("Kinetics: a start far outside the limits is fitted from the limits",
          floor * (1 - 1e-9) <= r["tau"].min() and r["tau"].max() <= 100.0 * span * (1 + 1e-9), str(r["tau"]))
    # a fixed lifetime is the user's: no limit, no "on the limit" note
    r = kinetics(y, tau=(floor / 4.0, 1000.0), fixed=(True, False))
    check("Kinetics: a fixed lifetime below the limit is used as given", r["tau"][0] == floor / 4.0
          and not any("lower limit" in w for w in r["info"]["warnings"]), f"{r['tau']} {r['info']['warnings']}")
    r = kinetics(y, fwhm_fixed=False)
    check("Kinetics: a free FWHM stays between a quarter of a bin and the fit range",
          m.dt_ps / 4.0 * (1 - 1e-9) <= r["fwhm"] <= span, str(r["fwhm"]))

    # the global fit: told its limits, the default optimiser no longer stops short of the minimum
    D = m.E[m.wls >= 640.0]
    trf, nm = globalfit(D), globalfit(D, method="nm")
    check("Global, TRF and Nelder-Mead end in the same place (lifetimes within 0.1 %, RMS within 1e-6)",
          np.allclose(np.sort(trf["tau"]), np.sort(nm["tau"]), rtol=1e-3)
          and abs(trf["info"]["rms"] / nm["info"]["rms"] - 1) < 1e-6,
          f"{trf['tau']} {trf['info']['rms']:.6g} vs {nm['tau']} {nm['info']['rms']:.6g}")
    back = _versions.rules_of_1_5(NEW)
    old_trf, old_nm = globalfit(D), globalfit(D, method="nm")
    ref = OLD.fit_global_analysis(D, t, np.array([100.0, 1000.0]), t0, fw, np.zeros(2, bool), True, True, False,
                                  method="trf")
    back()
    check("... which they did not under the 1.5 rules (TRF stopped on the wall with a higher RMS)",
          old_trf["info"]["rms"] > 1.05 * old_nm["info"]["rms"],
          f"{old_trf['tau']} {old_trf['info']['rms']:.6g} vs {old_nm['tau']} {old_nm['info']['rms']:.6g}")
    check("with the 1.5 rules back the global kernel is 1.4's, bit for bit",
          all(np.array_equal(old_trf[k], ref[k]) for k in ("tau", "A", "fit")))
    check("Global: the fit is better than under the 1.5 rules", trf["info"]["rms"] < old_nm["info"]["rms"],
          f"{trf['info']['rms']:.6g} vs {old_nm['info']['rms']:.6g}")
    r = globalfit(D, tau=(1e-6, 1e12))
    check("Global: a start far outside the limits is fitted from the limits",
          floor * (1 - 1e-9) <= r["tau"].min() and r["tau"].max() <= 100.0 * span * (1 + 1e-9), str(r["tau"]))
    try:
        globalfit(D, tau=(floor / 4.0, 1000.0), tau_fixed=np.array([True, False]))
        check("Global: a fixed lifetime below the limit is still refused, in words", False, "a result came back")
    except NEW.FitInputError as exc:
        check("Global: a fixed lifetime below the limit is still refused, in words",
              "a tenth of a time bin" in str(exc), str(exc))
    r = globalfit(D, fwhm_fixed=False)
    check("Global: a free FWHM stays between a quarter of a bin and the fit range",
          m.dt_ps / 4.0 * (1 - 1e-9) <= r["fwhm"] <= span, str(r["fwhm"]))
    # nothing to build limits from: refused as before, not a crash inside the optimiser
    for bad in (0.0, -5.0, float("nan")):
        try:
            NEW.fit_global_analysis(D, t, np.array([100.0, 1000.0]), t0, bad, np.zeros(2, bool), True, True, False)
            check(f"Global: FWHM {bad}: refused in words", False, "a result came back")
        except NEW.FitInputError as exc:
            check(f"Global: FWHM {bad}: refused in words", "FWHM" in str(exc), str(exc))
        except Exception as exc:              # noqa: BLE001
            check(f"Global: FWHM {bad}: refused in words", False, f"{type(exc).__name__}: {exc}")

# ---------------------------------------------------------------------------------------------
if section("A-10"):
    # the default three-component Nelder-Mead fit of this map ends with two equal lifetimes whose
    # amplitudes cancel: the case the limit decides
    m = NEW.TRESModel(NEW.read_phu(SAMPLE_A))
    tq, t0, fw = m.times, float(m.irf_peak_ps), float(m.irf_fwhm_ps)
    D = m.E.copy()

    def nm(scale):
        return NEW.fit_global_analysis(D * scale, tq, np.array([100.0, 1000.0, 10000.0]), t0, fw,
                                       np.zeros(3, bool), True, True, False, method="nm")

    one, ten, hundred = nm(1.0), nm(10.0), nm(100.0)
    # (the two equal lifetimes leave the size of their amplitudes open, so those are not compared)
    check("the same map with 10 x and 100 x the counts gives the same lifetimes (within 1e-4)",
          np.allclose(ten["tau"], one["tau"], rtol=1e-4) and np.allclose(hundred["tau"], one["tau"], rtol=1e-4),
          f"{one['tau']} {ten['tau']} {hundred['tau']}")
    check("... and the same quality of fit (RMS scales with the counts within 1e-6)",
          abs(ten["info"]["rms"] / one["info"]["rms"] / 10.0 - 1) < 1e-6
          and abs(hundred["info"]["rms"] / one["info"]["rms"] / 100.0 - 1) < 1e-6,
          f"{one['info']['rms']} {ten['info']['rms']} {hundred['info']['rms']}")
    check("... the amplitudes are not held at one number of counts",
          np.abs(hundred["A"]).max() > 10.0 * np.abs(one["A"]).max(),
          f"{np.abs(one['A']).max():.4g} {np.abs(ten['A']).max():.4g} {np.abs(hundred['A']).max():.4g}")
    top = float(np.nanmax(np.abs(D)))
    check("the limit is a million times the largest data value, masked cells or not",
          NEW._amp_limit(D, False) == 1e6 * top and NEW._amp_limit(np.where(D > top / 2, np.nan, D), True)
          == 1e6 * float(np.nanmax(np.abs(np.where(D > top / 2, np.nan, D)))))
    check("a map of NaN only has a limit too", NEW._amp_limit(np.full((2, 3), np.nan), True) == 1e6)

# ---------------------------------------------------------------------------------------------
if section("C-8"):
    # the fit range the windows open with, and the one "Full" writes, is the whole time axis
    lost = []
    for path in (SAMPLE_A, SAMPLE_B):
        top, app = make_app(path)
        for label in ("4 ps", "16 ps", "64 ps"):
            for align in (False, True):
                app.var_bin.set(label); app.var_t0.set(align); app.apply_params(); pump(0.2)
                m = app.model
                app.open_kinetics(); app.open_global_analysis(); pump(0.3)
                k, g = app._kinetics_win, app._global_win
                what = f"{'sample A' if path == SAMPLE_A else 'sample B'} BIN {label} t0 {'on' if align else 'off'}"
                if f"{m.n_t} of {m.n_t} " not in g.var_tcount.get():
                    lost.append(f"{what}: Global opens with '{g.var_tcount.get().strip()}'")
                g.var_tmin.set("0"); g._t_full()
                if f"{m.n_t} of {m.n_t} " not in g.var_tcount.get():
                    lost.append(f"{what}: Global Full gives '{g.var_tcount.get().strip()}'")
                if label != "4 ps":             # a fit of the 4 ps traces takes too long for a test
                    k.run_fit(); wait(lambda: not k._running, 120); pump(0.1)
                    n = None if k._last is None else k._last["_t_fit"].size
                    if n != m.n_t:
                        lost.append(f"{what}: Kinetics fits {n} of {m.n_t} points")
                if abs(float(k.var_t0.get()) - (m.irf_peak_ps - m.t0)) > 1e-6 \
                        or abs(float(g.var_t0.get()) - (m.irf_peak_ps - m.t0)) > 1e-6:
                    lost.append(f"{what}: t0 box {k.var_t0.get()} for {m.irf_peak_ps - m.t0!r}")
                k._on_close(); g._on_close(); pump(0.1)
        top.destroy()
    check("both files, BIN 4 / 16 / 64 ps, t0 off / on: the default and the Full fit range hold every delay",
          not lost, "; ".join(lost)[:700])
    t = np.array([-3184.000000000001, -3168.0, 21808.0, 21824.0])
    check("in_range: an end typed as the first / last delay keeps it; a point outside stays outside",
          NEW.in_range(t, float(NEW.fmt_ps(t[0])), float(NEW.fmt_ps(t[-1]))).all()
          and list(NEW.in_range(t, -3168.0, 21808.0)) == [False, True, True, False]
          and list(NEW.in_range(t, -3183.9, 21823.9)) == [False, True, True, False])
    check("fmt_ps reads back as the same delay", all(abs(float(NEW.fmt_ps(v)) - v) <= 1e-9 * abs(v)
                                                     for v in (21824.0, 262136.0, 0.5, -3184.000000000001, 12345.678)))

finish()
