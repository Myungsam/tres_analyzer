"""A-1, the choices behind "real limits": where the lower lifetime limit sits (FWHM / 9.42 as in the global
fit up to 1.5, or a tenth of a time bin), and whether the optimiser is told the limits (bounds) or only meets
a loss of 1e30 outside them (walls, as up to 1.5). Needs the code with _limits() and _shortest_tau()."""
import os
import sys

import numpy as np

sys.dont_write_bytecode = True
import _versions                              # noqa: E402

NEW = _versions.load()
ROOT = _versions.ROOT
S2 = 2.0 * np.sqrt(2.0 * np.log(2.0))
real_limits, real_floor = NEW._limits, NEW._shortest_tau
FLOORS = {"FWHM/9.42": lambda fwhm, dt: fwhm / S2 / 4.0,
          "bin/10": lambda fwhm, dt: dt / 10.0}


def load(name):
    m = NEW.TRESModel(NEW.read_phu(name))
    return m, float(m.irf_peak_ps - m.t0), float(m.irf_fwhm_ps)


FILES = _versions.samples()
for name in FILES:
    m, t0, fw = load(name)
    print(f"\n{os.path.basename(name)}: FWHM {fw:.4g} ps (FWHM/9.42 = {fw / S2 / 4:.4g} ps), bin {m.dt_ps:g} ps; "
          f"Kinetics, defaults (tau 100, 1000), bounds")
    print("  nm    | lower limit FWHM/9.42           | lower limit bin/10              | no limits at all (1.5)")
    for wi in range(0, m.n_w, 4):
        cells = []
        for kind in ("FWHM/9.42", "bin/10", "none"):
            NEW._shortest_tau = FLOORS.get(kind, real_floor)
            NEW._limits = (lambda *a: None) if kind == "none" else real_limits
            r = NEW.fit_single_trace(m.times, m.E[wi, :], tau_init=np.array([100.0, 1000.0]),
                                     tau_fixed=np.zeros(2, bool), t0_init=t0, t0_fixed=True, fwhm_init=fw,
                                     fwhm_fixed=True, has_inf=False, irf_mode="numerical")
            cells.append(f"{r['tau'][0]:9.3g} {r['tau'][1]:9.1f} RMS {r['info']['rms']:7.2f}")
        print(f"  {m.wls[wi]:5.0f} | " + " | ".join(cells))

print("\nGlobal fit: (lower limit) x (walls = 1.5 / bounds)")
for name, lam, taus in ((FILES[0], 0.0, [100.0, 1000.0]), (FILES[0], 0.0, [100.0, 1000.0, 10000.0]),
                        (FILES[0], 640.0, [100.0, 1000.0]),
                        (FILES[1], 0.0, [100.0, 1000.0]), (FILES[1], 0.0, [100.0, 1000.0, 10000.0]),
                        (FILES[1], 610.0, [100.0, 1000.0])):
    m, t0, fw = load(name)
    D = m.E[m.wls >= lam]
    print(f"  {'sample A' if name == FILES[0] else 'sample B'}, {'all curves' if not lam else f'>= {lam:g} nm'}, {len(taus)} components")
    for method in ("trf", "nm"):
        for floor in ("FWHM/9.42", "bin/10"):
            for kind in ("walls", "bounds"):
                NEW._shortest_tau = FLOORS[floor]
                NEW._limits = (lambda *a: None) if kind == "walls" else real_limits
                try:
                    r = NEW.fit_global_analysis(D, m.times, np.array(taus), t0, fw, np.zeros(len(taus), bool),
                                                True, True, False, method=method)
                    text = ("tau " + ", ".join(f"{v:.5g}" for v in r["tau"])
                            + f"  RMS {r['info']['rms']:.5g}  max|A| {np.nanmax(np.abs(r['A'])):.3g}"
                            + f"  {r['info']['iters']} it")
                except Exception as exc:      # noqa: BLE001
                    text = f"{type(exc).__name__}: {str(exc)[:80]}"
                print(f"    {method:3s} {floor:9s} {kind:6s}: {text}")
NEW._limits, NEW._shortest_tau = real_limits, real_floor
