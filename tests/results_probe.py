"""Numbers for the result-changing review items (kernel and model part), printed as plain lines.

    python results_probe.py [item ...] > out.txt

Run on the code before and after each change; the two outputs are the "before / after" of the report
(the 1.6 changes that alter results). Only stable calls are used (read_phu, TRESModel, the two fit kernels,
fwhm_of), so the same script runs on both states.
"""
import copy
import sys
import time

import numpy as np

sys.dont_write_bytecode = True
import _versions                              # noqa: E402

NEW = _versions.load()
ROOT = _versions.ROOT
SAMPLE_A = _versions.samples()[0]
SAMPLE_B = _versions.samples()[1]
ONLY = sys.argv[1:]
S2 = 2.0 * np.sqrt(2.0 * np.log(2.0))


def want(item):
    go = not ONLY or item in ONLY
    if go:
        print(f"\n===== {item}")
    return go


def model(path):
    return NEW.TRESModel(NEW.read_phu(path))


def irf_defaults(m):
    """What the fit windows put in the t0 / FWHM boxes."""
    return float(m.irf_peak_ps - m.t0), float(m.irf_fwhm_ps)


def fmt(v):
    return "[" + ", ".join(f"{x:.6g}" for x in np.atleast_1d(v)) + "]"


def glob(m, tau, **kw):
    t0, fw = irf_defaults(m)
    kw.setdefault("t0_init", t0)
    kw.setdefault("fwhm_init", fw)
    n = len(tau)
    args = dict(tau_fixed=np.zeros(n, bool), t0_fixed=True, fwhm_fixed=True, has_inf=False)
    args.update(kw)
    t_start = time.perf_counter()
    try:
        r = NEW.fit_global_analysis(m.E, m.times, np.array(tau, float), **args)
    except Exception as exc:                  # noqa: BLE001
        return f"refused/failed: {type(exc).__name__}: {str(exc)[:110]}"
    i = r["info"]
    cells = i["rss"] / i["rms"] ** 2 if i["rms"] > 0 else float("nan")
    return (f"tau={fmt(r['tau'])} beta={fmt(r['beta'])} t0={r['t0']:.6g} fwhm={r['fwhm']:.6g} "
            f"RMS={i['rms']:.6g} delays_in_loss={cells / m.E.shape[0]:.0f}/{m.n_t} "
            f"max|A|={np.nanmax(np.abs(r['A'])):.4g} iters={i['iters']} "
            f"warnings={len(i.get('warnings', []))} {time.perf_counter() - t_start:.1f}s")


def kin(m, wi, tau, **kw):
    t0, fw = irf_defaults(m)
    n = len(tau)
    args = dict(tau_init=np.array(tau, float), tau_fixed=np.zeros(n, bool), t0_init=t0, t0_fixed=True,
                fwhm_init=fw, fwhm_fixed=True, has_inf=False, irf_mode="numerical")
    args.update(kw)
    try:
        return NEW.fit_single_trace(m.times, m.E[wi, :], **args)
    except Exception as exc:                  # noqa: BLE001
        return f"refused/failed: {type(exc).__name__}: {str(exc)[:110]}"


# ---------------------------------------------------------------------------------------------
if want("A-2"):
    m = model(SAMPLE_A)
    st = np.array([True, False])
    print("sample A map, tau 200 (stretched) + 2000, IRF mode skip; start t0, FWHM =", irf_defaults(m))
    for method in ("nm", "trf"):
        for free, kw in (("nothing (control)", {}), ("t0", {"t0_fixed": False}), ("FWHM", {"fwhm_fixed": False})):
            print(f"  {method:3s} free {free:17s}:",
                  glob(m, [200.0, 2000.0], stretch_on=st, irf_mode="skip", method=method, **kw))

# ---------------------------------------------------------------------------------------------
if want("A-1"):
    for name, path in (("sample A", SAMPLE_A), ("sample B", SAMPLE_B)):
        m = model(path)
        t0, fw = irf_defaults(m)
        print(f"{name}: FWHM {fw:g} ps, sigma/4 = {fw / S2 / 4:.6g} ps, bin {m.dt_ps:g} ps, "
              f"range {m.times[-1] - m.times[0]:g} ps")
        for method in ("trf", "nm"):
            print(f"  Global {method:3s} (tau 100, 1000, 10000):", glob(m, [100.0, 1000.0, 10000.0], method=method))
        rows = list(range(0, m.n_w, 4))
        below = on_limit = 0
        for wi in rows:
            r = kin(m, wi, [100.0, 1000.0])
            if isinstance(r, str):
                print(f"  Kinetics {m.wls[wi]:.0f} nm: {r}")
                continue
            below += bool(np.any(r["tau"] < m.dt_ps))
            on_limit += any("lower limit" in w for w in r["info"].get("warnings", []))
            print(f"  Kinetics {m.wls[wi]:.0f} nm: tau={fmt(r['tau'])} A={fmt(r['A'])} "
                  f"RMS={r['info']['rms']:.5g} warnings={len(r['info'].get('warnings', []))}")
        print(f"  Kinetics summary: {below} of {len(rows)} with a tau below one bin, "
              f"{on_limit} of {len(rows)} reported as on the lower limit")

# ---------------------------------------------------------------------------------------------
if want("A-10"):
    for name, path in (("sample A", SAMPLE_A), ("sample B", SAMPLE_B)):
        m = model(path)
        print(f"{name}, Global NM, tau 100, 1000, 10000; largest count in the map: {np.nanmax(m.E):.6g}")
        print("   as measured:", glob(m, [100.0, 1000.0, 10000.0], method="nm"))
        for scale in (10.0, 100.0):
            m2 = model(path)
            m2.E = m2.E * scale               # the same sample measured `scale` times longer
            print(f"   counts x {scale:g}:", glob(m2, [100.0, 1000.0, 10000.0], method="nm"))

# ---------------------------------------------------------------------------------------------
if want("A-13"):
    for name, path in (("sample A", SAMPLE_A), ("sample B", SAMPLE_B)):
        p = NEW.read_phu(path)
        print(f"{name} IRF curve: peak, FWHM =", NEW.fwhm_of(p["counts"][0].astype(float), p["res_ps"]))
        m = NEW.TRESModel(p)
        print(f"  default FWHM in the fit windows: {irf_defaults(m)[1]:.6g} ps; map title 'FWHM {m.irf_fwhm_ps:.0f} ps'")
    x = np.arange(2000) * 4.0
    for true in (30.0, 60.0, 200.0):
        vals = []
        for shift in (0.0, 1.0, 2.0, 3.0):
            g = 1e4 * np.exp(-0.5 * ((x - 4000.0 - shift) / (true / S2)) ** 2)
            vals.append(NEW.fwhm_of(g, 4.0)[1])
        print(f"Gaussian, true FWHM {true:g} ps, 4 ps bins, four sub-bin positions: {fmt(vals)}")
    g = 1e4 * np.exp(-0.5 * ((x - 4000.0) / (200.0 / S2)) ** 2)
    print("  the 200 ps one on a flat background of 20 % of the peak:", f"{NEW.fwhm_of(g + 2000.0, 4.0)[1]:.6g}")
    rng = np.random.default_rng(1)
    noisy = rng.poisson(30.0 * np.exp(-0.5 * ((x - 4000.0) / (200.0 / S2)) ** 2) + 0.2).astype(float)
    print("  a 200 ps peak of 30 counts with Poisson noise:", f"{NEW.fwhm_of(noisy, 4.0)[1]:.6g}")

# ---------------------------------------------------------------------------------------------
if want("A-9"):
    p = NEW.read_phu(SAMPLE_A)
    rng = np.random.default_rng(7)

    def synth(signal):
        q = copy.copy(p)
        q["counts"] = rng.poisson(signal, size=p["counts"].shape).astype(np.uint32)
        return q

    # a) nothing but noise in both: the true difference is zero everywhere
    m = NEW.TRESModel(synth(20.0), build=False)
    m.bg_sub = False
    m.solvent, m.solvent_sub = synth(20.0), True
    m.rebuild()
    sigma = np.sqrt(2 * 20.0 * m.rebin)
    print(f"a) sample = solvent = Poisson(20) per native bin, no background step; sigma per cell {sigma:.4g}")
    print(f"   clipped share {getattr(m, 'clip_frac', float('nan')):.3f}; mean of E {np.nanmean(m.E):+.4g} counts per cell; "
          f"steady-state sum per wavelength {np.nanmean(m.spec_total):+.6g} (true value 0); "
          f"negative share reported {m.neg_frac:.3f}")
    # b) a real decay on top: what a fit of one trace gets
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
    print(f"b) decay of tau 1500 ps (800 counts per cell at the top) on the same noise, averaged over the curves, "
          f"fit with tau + offset:\n   tau = {r['tau'][0]:.5g} ps, offset = {r['A'][-1]:+.4g} counts (true 0), "
          f"tail mean (last 20 %) = {np.mean(y[-len(y) // 5:]):+.4g}")
    one = m.E[5, :]
    r = NEW.fit_single_trace(m.times[sel], one[sel], tau_init=np.array([1000.0]), tau_fixed=np.array([False]),
                             t0_init=3000.0, t0_fixed=True, fwhm_init=300.0, fwhm_fixed=True, has_inf=True)
    print(f"   one curve alone: tau = {r['tau'][0]:.5g} ps, offset = {r['A'][-1]:+.4g} counts (true 0)")

# ---------------------------------------------------------------------------------------------
if want("C-8"):
    # what the one or two end points do to a fit: the range as the boxes used to give it (4 digits)
    # against the whole axis, same kernel
    for name, path in (("sample A", SAMPLE_A), ("sample B", SAMPLE_B)):
        p = NEW.read_phu(path)
        for rebin, label in ((1, "4 ps"), (4, "16 ps"), (16, "64 ps")):
            for align in (False, True):
                m = NEW.TRESModel(p, build=False)
                m.rebin, m.t0_align = rebin, align
                m.rebuild()
                if align:                       # the background window stays on the same delays,
                    m.bg_lo_ps -= m.t0          # as the main window does when the box is ticked
                    m.bg_hi_ps -= m.t0
                    m.rebuild()
                lo, hi = float(f"{m.times[0]:.4g}"), float(f"{m.times[-1]:.4g}")
                old = (m.times >= lo) & (m.times <= hi)
                line = f"{name} BIN {label} t0 {'on ' if align else 'off'}: {int(old.sum())} of {m.n_t} points"
                if old.all() or rebin == 1:
                    print("  " + line)
                    continue
                t0, fw = irf_defaults(m)
                wi = int(np.argmin(np.abs(m.wls - (600.0 if name == "sample A" else 650.0))))
                out = []
                for sel in (old, np.ones(m.n_t, bool)):
                    r = NEW.fit_single_trace(m.times[sel], m.E[wi, sel], tau_init=np.array([100.0, 1000.0]),
                                             tau_fixed=np.zeros(2, bool), t0_init=t0, t0_fixed=True,
                                             fwhm_init=fw, fwhm_fixed=True, has_inf=False, irf_mode="numerical")
                    out.append(f"tau {fmt(r['tau'])} RMS {r['info']['rms']:.6g}")
                print(f"  {line}; Kinetics at {m.wls[wi]:.0f} nm: {out[0]}  ->  {out[1]}")
