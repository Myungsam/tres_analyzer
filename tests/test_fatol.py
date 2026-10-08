"""1.4.2: the Nelder-Mead fits stop on a tolerance that follows the size of the data.

Compares the fits of the current version with 1.4.1 (baselines/TCSPC_analysis_1_4_1.py, the
file at git 5a7475e) on 60 real traces and on whole-map global fits. Run it with the app venv:
that is the environment the .exe is built from, and the one where 1.4.1 ran to maxiter.
"""
import os
import sys
import time

import numpy as np
import scipy

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _versions                              # noqa: E402

NEW = _versions.load()
FILE_14 = _versions.load("1.4")        # the single file the 1.4.2 change was made in
OLD = _versions.load(path=os.path.join(HERE, "baselines", "TCSPC_analysis_1_4_1.py"))
ROOT = _versions.ROOT
# These checks compare with 1.4: the rules 1.6 changed on purpose are put back (see _versions.rules_of_1_5).
_versions.rules_of_1_5(NEW)
fails = []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail and not ok else ""))
    if not ok:
        fails.append(name)


print(f"numpy {np.__version__}, scipy {scipy.__version__}, python {sys.version.split()[0]}")

# ---- the tolerance itself ---------------------------------------------------------------
check("tolerance: never tighter than the old 1e-10 for small-valued data (absorbance scale)",
      NEW._nm_fatol(np.full(2000, 1e-3)) == 1e-10 and NEW._nm_fatol(np.zeros(10)) == 1e-10)
counts = np.full(1500, 3000.0)
check("tolerance: a 1e-12th of the sum of squares for photon counts, NaN ignored",
      NEW._nm_fatol(counts) == 1e-12 * 1500 * 3000.0 ** 2
      and NEW._nm_fatol(np.append(counts, np.nan)) == NEW._nm_fatol(counts))
check("tolerance: only finite values count (inf is left out like NaN, 2-D input is fine)",
      NEW._nm_fatol(np.append(counts, [np.inf, -np.inf])) == NEW._nm_fatol(counts)
      and NEW._nm_fatol(counts.reshape(30, 50)) == NEW._nm_fatol(counts)
      and NEW._nm_fatol(np.array([np.nan, np.inf])) == 1e-10)

# ---- kinetics: 60 traces -----------------------------------------------------------------
cases = []
for fname, bins in ((_versions.samples()[0], (4, 1)), (_versions.samples()[1], (4,))):
    phu = NEW.read_phu(fname)
    for rb in bins:
        m = NEW.TRESModel(phu)
        m.first_is_irf = True
        m.rebin = rb
        m.t_max_ps = m.t_data_ps
        m.rebuild()
        t0, fw = float(m.irf_peak_ps - m.t0), float(m.irf_fwhm_ps)
        for wi in (5, m.n_w // 3, m.n_w // 2, (2 * m.n_w) // 3, m.n_w - 6):
            for taus, inf in (((500.0,), False), ((100.0, 1000.0), False), ((100.0, 1000.0), True),
                              ((50.0, 500.0, 5000.0), False)):
                n = len(taus)
                cases.append((f"{fname[:4]} {m.dt_ps:g}ps wl{m.wls[wi]:.0f} n{n}{'+inf' if inf else ''}",
                              m.times.copy(), m.E[wi].copy(),
                              dict(tau_init=np.array(taus), tau_fixed=np.zeros(n, bool),
                                   beta_init=np.ones(n), beta_fixed=np.zeros(n, bool),
                                   stretch_on=np.zeros(n, bool), t0_init=t0, t0_fixed=True,
                                   fwhm_init=fw, fwhm_fixed=True, has_inf=inf, irf_mode="numerical")))
NEW.fit_single_trace(cases[0][1], cases[0][2], **cases[0][3])       # scipy import, both modules
OLD.fit_single_trace(cases[0][1], cases[0][2], **cases[0][3])

rows = []
for label, t, y, kw in cases:
    a = time.perf_counter(); o = OLD.fit_single_trace(t, y, **kw); t_old = time.perf_counter() - a
    a = time.perf_counter(); n = NEW.fit_single_trace(t, y, **kw); t_new = time.perf_counter() - a
    rows.append(dict(label=label, t_old=t_old, t_new=t_new, it_old=o["info"]["iters"], it_new=n["info"]["iters"],
                     dtau=float(np.max(np.abs(n["tau"] / o["tau"] - 1))),
                     drms=n["info"]["rms"] / o["info"]["rms"] - 1,
                     dfit=float(np.nanmax(np.abs(n["fit"] - o["fit"])) / max(np.nanmax(np.abs(o["fit"])), 1e-30)),
                     dA=float(np.max(np.abs(n["A"] - o["A"])) / max(np.max(np.abs(o["A"])), 1e-30))))
capped_old = [r for r in rows if r["it_old"] >= 5000]
capped_new = [r for r in rows if r["it_new"] >= 5000]
print(f"   1.4.1: {sum(r['t_old'] for r in rows):.1f} s for {len(rows)} fits, {len(capped_old)} ran to maxiter "
      f"(longest {max(r['t_old'] for r in rows):.2f} s)")
print(f"   now  : {sum(r['t_new'] for r in rows):.1f} s, {len(capped_new)} ran to maxiter "
      f"(longest {max(r['t_new'] for r in rows):.2f} s, most iterations {max(r['it_new'] for r in rows)})")
print(f"   largest relative change: tau {max(r['dtau'] for r in rows):.1e}, amplitude {max(r['dA'] for r in rows):.1e}, "
      f"fit curve {max(r['dfit'] for r in rows):.1e}, RMS {max(abs(r['drms']) for r in rows):.1e}")
check("kinetics: no fit runs to the iteration cap any more", not capped_new,
      str([(r["label"], r["it_new"]) for r in capped_new]))
check("kinetics: no fit needs more iterations than before", all(r["it_new"] <= r["it_old"] for r in rows),
      str([(r["label"], r["it_old"], r["it_new"]) for r in rows if r["it_new"] > r["it_old"]][:5]))
check("kinetics: the longest fit takes under 1 s", max(r["t_new"] for r in rows) < 1.0,
      f"{max(r['t_new'] for r in rows):.2f}")
check("kinetics: tau within 1e-6, amplitudes and fit curve within 1e-6, RMS within 1e-9 of 1.4.1",
      max(r["dtau"] for r in rows) < 1e-6 and max(r["dA"] for r in rows) < 1e-6
      and max(r["dfit"] for r in rows) < 1e-6 and max(abs(r["drms"]) for r in rows) < 1e-9,
      str(max(rows, key=lambda r: r["dtau"])))
check("kinetics: the RMS never gets worse by more than 1e-9 (the fit is as good as before)",
      max(r["drms"] for r in rows) < 1e-9)
if capped_old:
    worst = max(capped_old, key=lambda r: r["t_old"])
    print(f"   e.g. {worst['label']}: {worst['t_old']:.2f} s / {worst['it_old']} iterations -> "
          f"{worst['t_new']:.2f} s / {worst['it_new']}")
    check("kinetics: the fits that ran to the cap are now at least 20x faster",
          all(r["t_old"] / max(r["t_new"], 1e-9) > 20 for r in capped_old),
          str([(r["label"], round(r["t_old"], 2), round(r["t_new"], 2)) for r in capped_old][:4]))
else:
    print("   (1.4.1 did not run to the cap in this environment - it does under the app venv)")

# small-valued data: the tolerance is the old one, so the fit is the old fit, bit for bit
label, t, y, kw = cases[1]
ys = y * 1e-9
o, n = OLD.fit_single_trace(t, ys, **kw), NEW.fit_single_trace(t, ys, **kw)
check("kinetics: data scaled to 1e-9 (old tolerance applies) gives the identical fit",
      NEW._nm_fatol(ys[np.isfinite(ys)]) == 1e-10 and np.array_equal(o["tau"], n["tau"])
      and np.array_equal(o["A"], n["A"]) and o["info"]["iters"] == n["info"]["iters"])

# ---- global analysis ----------------------------------------------------------------------
phu = NEW.read_phu(_versions.samples()[0])
m = NEW.TRESModel(phu)
m.first_is_irf = True
m.rebin = 4
m.t_max_ps = m.t_data_ps
m.rebuild()
D = m.E.copy()
tt = m.times.copy()
gkw = dict(tau_init=np.array([100.0, 1000.0]), tau_fixed=np.zeros(2, bool),
           t0_init=float(m.irf_peak_ps - m.t0), fwhm_init=float(m.irf_fwhm_ps),
           t0_fixed=True, fwhm_fixed=True, has_inf=False, beta_init=np.ones(2),
           beta_fixed=np.zeros(2, bool), stretch_on=np.zeros(2, bool), irf_mode="numerical")
res = {}
for method in ("nm", "trf"):
    a = time.perf_counter(); o = OLD.fit_global_analysis(D, tt, method=method, **gkw); t_old = time.perf_counter() - a
    a = time.perf_counter(); n = NEW.fit_global_analysis(D, tt, method=method, **gkw); t_new = time.perf_counter() - a
    res[method] = (o, n, t_old, t_new)
    print(f"   global {method}: 1.4.1 {t_old:.2f} s / {o['info']['iters']} it, now {t_new:.2f} s / {n['info']['iters']} it, "
          f"dtau {np.max(np.abs(n['tau'] / o['tau'] - 1)):.1e}, dRMS {n['info']['rms'] / o['info']['rms'] - 1:.1e}")
# what each fit hands to the optimiser (the global Nelder-Mead fit stops early on this data
# even with the old tolerance, so its change is checked here rather than by timing)
seen = []
real_minimize = NEW._minimize
NEW._minimize = lambda fun, x0, **kw: (seen.append(kw["options"]["fatol"]), real_minimize(fun, x0, **kw))[1]
try:
    NEW.fit_global_analysis(D, tt, method="nm", **gkw)
    label, t, y, kw = cases[1]
    NEW.fit_single_trace(t, y, **kw)
finally:
    NEW._minimize = real_minimize
check("both Nelder-Mead fits pass the data-sized tolerance to the optimiser",
      seen == [NEW._nm_fatol(D), NEW._nm_fatol(y[np.isfinite(y)])] and min(seen) > 1e-6, str(seen))
o, n, t_old, t_new = res["trf"]
check("global, TRF (the default): untouched - identical result",
      np.array_equal(o["tau"], n["tau"]) and np.array_equal(o["A"], n["A"])
      and o["info"]["rms"] == n["info"]["rms"] and o["info"]["iters"] == n["info"]["iters"])
o, n, t_old, t_new = res["nm"]
check("global, Nelder-Mead: stops before the cap, no more iterations than before",
      n["info"]["iters"] < 5000 and n["info"]["iters"] <= o["info"]["iters"],
      f"{o['info']['iters']} -> {n['info']['iters']}")
check("global, Nelder-Mead: tau within 1e-6, spectra within 1e-6, RMS within 1e-9 of 1.4.1",
      float(np.max(np.abs(n["tau"] / o["tau"] - 1))) < 1e-6
      and float(np.nanmax(np.abs(n["A"] - o["A"])) / np.nanmax(np.abs(o["A"]))) < 1e-6
      and abs(n["info"]["rms"] / o["info"]["rms"] - 1) < 1e-9)

# ---- nothing else in the file changed --------------------------------------------------------
import ast                                    # noqa: E402
import io                                     # noqa: E402


def bodies(path):
    tree = ast.parse(io.open(path, encoding="utf-8").read())
    return {n.name: ast.dump(n) for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}


b_old, b_new = bodies(OLD.__file__), bodies(FILE_14.__file__)
changed = sorted(k for k in b_old if b_new.get(k) != b_old[k])
added = sorted(set(b_new) - set(b_old))
check("source: only the two fit functions changed, one helper was added",
      changed == ["fit_global_analysis", "fit_single_trace"] and added == ["_nm_fatol"]
      and not set(b_old) - set(b_new), f"changed={changed} added={added}")
check("version is 1.4.2", FILE_14.APP_VERSION == "1.4.2" and OLD.APP_VERSION == "1.4")
print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(1 if fails else 0)
