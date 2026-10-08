"""Numeric checks for the solvent subtraction (no Tk window). US-001."""
import copy
import hashlib
import itertools
import os
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _versions                              # noqa: E402
NEW = _versions.load()
OLD = _versions.load("1.0")

SAMPLE_A = _versions.samples()[0]
SAMPLE_B = _versions.samples()[1]

fails = []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail else ""))
    if not ok:
        fails.append(name)


def digest(a):
    return hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()


def eq(a, b):
    return a.shape == b.shape and np.array_equal(a, b, equal_nan=True)


def setup(model, cfg, phu):
    model.rebin = cfg["rebin"]
    model.bg_sub = cfg["bg"]
    model.first_is_irf = cfg["irf"]
    model.t0_align = cfg["t0"]
    model.wl_offset = cfg["off"]
    wl = phu["wls"] + cfg["off"]
    model.crop_wl = (wl[5], wl[-6]) if cfg["crop"] else None
    model.t_min_ps = 800.0 if cfg["crop"] else 0.0
    model.t_max_ps = 9000.0 if cfg["crop"] else model.t_data_ps
    model.masks = [(wl[10], wl[13])] if cfg["mask"] else []
    model.bg_lo_ps, model.bg_hi_ps = (0.0, 100.0)
    if cfg["crop"]:
        model.bg_lo_ps, model.bg_hi_ps = (model.t_min_ps, model.t_min_ps + 200.0)


keys = ["rebin", "bg", "irf", "crop", "mask", "t0", "off"]
grid = list(itertools.product([1, 4, 16], [True, False], [True, False],
                              [False, True], [False, True], [False, True],
                              [0.0, -50.0]))

for path in (SAMPLE_A, SAMPLE_B):
    tag = path.split("\\")[-1][:9]
    phu_new = NEW.read_phu(path)
    phu_old = OLD.read_phu(path)
    h_sample = digest(phu_new["counts"])

    # a synthetic solvent that is NOT the sample: curves reversed, and scaled
    # so that some bins exceed the sample's
    solv = copy.copy(phu_new)
    solv["counts"] = (phu_new["counts"][::-1].astype(np.uint64) * 3 // 2).astype(np.uint32)
    solv["path"] = "synthetic_solvent.phu"
    h_solv = digest(solv["counts"])
    check(f"{tag}: synthetic solvent differs from sample",
          not np.array_equal(solv["counts"], phu_new["counts"])
          and bool((solv["counts"] > phu_new["counts"]).any()))

    reg_ok = off_ok = raw_ok = self1_ok = s0_ok = clip_ok = ident_ok = True
    neg_kept = False
    n = 0
    for combo in grid:
        cfg = dict(zip(keys, combo))
        n += 1
        mo = OLD.TRESModel(phu_old); setup(mo, cfg, phu_old); mo.rebuild()
        mn = NEW.TRESModel(phu_new); setup(mn, cfg, phu_new); mn.rebuild()
        same = (eq(mo.E, mn.E) and eq(mo.spec_total, mn.spec_total)
                and eq(mo.decay_total, mn.decay_total) and eq(mo.E_raw, mn.E_raw)
                and mo.vmax == mn.vmax and mo.neg_frac == mn.neg_frac)
        reg_ok &= same
        if cfg["bg"] and (mn.E < 0).any():
            neg_kept = True

        # solvent loaded but switched off -> still identical to the old code
        mn.solvent, mn.solvent_scale, mn.solvent_sub = solv, 0.7, False
        mn.rebuild()
        off_ok &= (eq(mo.E, mn.E) and eq(mo.spec_total, mn.spec_total)
                   and eq(mo.decay_total, mn.decay_total))

        # criterion 4: E_raw == sample - s * solvent, expectation built here
        s = 0.5
        mn.solvent_scale, mn.solvent_sub = s, True
        mn.rebuild()
        p = phu_new
        irf_idx = 0 if cfg["irf"] else None
        idx = [i for i in range(p["ncurves"]) if i != irf_idx]
        if cfg["crop"]:
            lo, hi = sorted(mn.crop_wl)
            idx = [i for i in idx if lo - 1e-6 <= p["wls"][i] + cfg["off"] <= hi + 1e-6]
        res, rb = p["res_ps"], cfg["rebin"]
        b_lo = int(np.clip(round(mn.t_min_ps / res), 0, p["nbins"] - 1))
        b_hi = int(np.clip(round(mn.t_max_ps / res), b_lo + 1, p["nbins"]))
        n_t = max(1, (b_hi - b_lo) // rb)
        b_hi = b_lo + n_t * rb
        A = p["counts"][idx, b_lo:b_hi].astype(np.float64).reshape(len(idx), n_t, rb).sum(2)
        B = solv["counts"][idx, b_lo:b_hi].astype(np.float64).reshape(len(idx), n_t, rb).sum(2)
        exp = A - s * B
        exp[mn.mask_rows, :] = np.nan
        raw_ok &= eq(mn.E_raw, exp)

        # criterion 6 (A-9, 1.6: what is below 0 is kept; up to 1.5 it was cut to 0):
        # E is the subtracted map as it is, spec_total == nansum(E)
        E = mn.E
        st = np.nansum(E, axis=1); st[np.isnan(E).all(axis=1)] = np.nan
        unclipped = mn.E_raw - (mn.bg_spec[:, None] if cfg["bg"] else 0.0)
        clip_ok &= eq(E, unclipped) and eq(mn.spec_total, st) \
            and eq(mn.decay_total, np.nansum(E, axis=0)) and 0.0 <= mn.neg_frac <= 1.0
        if not cfg["bg"]:
            clip_ok &= eq(mn.E_raw, exp)

        # identity: sample spectrum - s * solvent spectrum == subtracted
        ref = np.nansum(unclipped, axis=1); ref[np.isnan(unclipped).all(axis=1)] = np.nan
        pv = NEW.TRESModel(phu_new); pv.copy_settings_from(mn); pv.solvent_sub = False
        pv.rebuild()
        lhs = pv.spec_total - s * pv.solvent_spectrum()
        scale = max(1.0, float(np.nanmax(np.abs(pv.spec_total))))
        ident_ok &= bool(np.allclose(lhs, ref, rtol=0, atol=1e-9 * scale, equal_nan=True))

        # criterion 5: self subtraction
        mn.solvent, mn.solvent_scale = phu_new, 1.0
        mn.rebuild()
        finite = np.isfinite(mn.E_raw)
        self1_ok &= bool((mn.E_raw[finite] == 0).all()) and bool((mn.E[finite] == 0).all())
        mn.solvent_scale = 0.0
        mn.rebuild()
        s0_ok &= eq(mn.E, mo.E)

    check(f"{tag}: regression vs backup, no solvent ({n} combos)", reg_ok)
    check(f"{tag}: regression vs backup, solvent loaded but off", off_ok)
    check(f"{tag}: negatives remain when subtraction is off (bg on)", neg_kept)
    check(f"{tag}: E_raw == sample - 0.5*synthetic solvent", raw_ok)
    check(f"{tag}: E is the subtracted map, nothing cut to 0, sums match", clip_ok)
    check(f"{tag}: solvent_spectrum identity", ident_ok)
    check(f"{tag}: self subtraction s=1 -> zeros", self1_ok)
    check(f"{tag}: s=0 -> E == baseline E", s0_ok)
    check(f"{tag}: sample counts untouched", digest(phu_new["counts"]) == h_sample)
    check(f"{tag}: solvent counts untouched", digest(solv["counts"]) == h_solv)

# ---- solvent_mismatch ------------------------------------------------------
sal, nap = NEW.read_phu(SAMPLE_A), NEW.read_phu(SAMPLE_B)
e, w = NEW.solvent_mismatch(sal, copy.copy(sal))
check("mismatch: identical -> no errors, no notes", e == [] and w == [])
e, w = NEW.solvent_mismatch(sal, nap)
check("mismatch: real files with different grids are refused", len(e) >= 1,
      "; ".join(e))
v = copy.copy(sal); v["ncurves"] = sal["ncurves"] - 1; v["wls"] = sal["wls"][:-1]
e, _ = NEW.solvent_mismatch(sal, v)
check("mismatch: ncurves", len(e) == 1 and "curves" in e[0])
v = copy.copy(sal); v["wls"] = sal["wls"] + 5.0
e, _ = NEW.solvent_mismatch(sal, v)
check("mismatch: wls", len(e) == 1 and "wavelength" in e[0])
v = copy.copy(sal); v["nbins"] = sal["nbins"] // 2
e, _ = NEW.solvent_mismatch(sal, v)
check("mismatch: nbins", len(e) == 1 and "bins" in e[0])
v = copy.copy(sal); v["res_ps"] = sal["res_ps"] * 2
e, _ = NEW.solvent_mismatch(sal, v)
check("mismatch: res_ps", len(e) == 1 and "resolution" in e[0])
v = copy.copy(sal); v["acq_ms"] = (sal["acq_ms"] or 1000) * 2
s2 = copy.copy(sal); s2["acq_ms"] = sal["acq_ms"] or 1000
e, w = NEW.solvent_mismatch(s2, v)
check("mismatch: acq_ms only -> note, no error",
      e == [] and len(w) == 1 and f"{v['acq_ms'] / 1000:g} s" in w[0]
      and f"{s2['acq_ms'] / 1000:g} s" in w[0], w[0] if w else "")
v = copy.copy(sal); v["nbins"] = 1; v["res_ps"] = 1.0
e, _ = NEW.solvent_mismatch(sal, v)
check("mismatch: all differences are listed", len(e) == 2)

# ---- SETTINGS completeness -------------------------------------------------
orig = NEW.TRESModel.rebuild
NEW.TRESModel.rebuild = lambda self: None
try:
    bare = NEW.TRESModel(sal)
finally:
    NEW.TRESModel.rebuild = orig
# rev counts the rebuilds, _t_data keeps the length of the filled record (1.6): neither is a setting
attrs = set(vars(bare)) - {"phu", "rev", "_t_data"}
check("SETTINGS covers every setting __init__ creates",
      attrs == set(NEW.TRESModel.SETTINGS),
      f"missing={attrs - set(NEW.TRESModel.SETTINGS)} extra={set(NEW.TRESModel.SETTINGS) - attrs}")
a = NEW.TRESModel(sal); a.masks = [(500.0, 510.0)]; a.rebin = 16; a.solvent = sal
b = NEW.TRESModel(sal); b.copy_settings_from(a)
check("copy_settings_from copies values, masks as a new list",
      all(getattr(b, k) is getattr(a, k) or getattr(b, k) == getattr(a, k)
          for k in NEW.TRESModel.SETTINGS if k != "solvent")
      and b.solvent is a.solvent and b.masks is not a.masks)

# ---- timing of one preview (4 rebuilds, worst case BIN 4 ps) ---------------
m = NEW.TRESModel(sal); m.rebin = 1; m.solvent = sal; m.solvent_sub = True
t0 = time.perf_counter()
for _ in range(5):
    for _ in range(3):
        m.rebuild()
dt = (time.perf_counter() - t0) / 5 * 1000
print(f"INFO one preview (3 rebuilds with solvent, rebin 1): {dt:.1f} ms")
check("preview recomputation is well under the 130 ms debounce", dt < 100, f"{dt:.1f} ms")

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(1 if fails else 0)
