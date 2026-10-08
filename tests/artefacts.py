"""Everything the program computes, shows and writes for a fixed set of cases - for comparing versions.

    python artefacts.py --target 1.4 --out <folder>          (a single-file version)
    python artefacts.py --target package --out <folder>      (the package in the project)
    python artefacts.py --target <path> --out <folder>       (a .py file or a folder holding the package)
    python artefacts.py --compare <folder A> <folder B>      (exit 1 and a list when anything differs)

Run with the app venv, one fresh process per run. Writes into <folder>:
  case_XX.npz              model matrix, axes, steady state, fit results of the case
  case_XX_*.csv            what the exports of that case write
  origin_log.json          every call the .opju export makes on a recording stand-in for originpro
  flim.npz                 FLIM processing of synthetic T3 records
  widgets.json             the widget tree of each window (class, text, values, geometry manager)
  png/<window>.png         the figure of each window
  artists.json             the data of every artist in those figures (fallback when PNGs are unstable)
"""
import argparse
import copy
import filecmp
import hashlib
import json
import os
import sys
import time
import types

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _versions                              # noqa: E402
import numpy as np                            # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--target", default="")
ap.add_argument("--out", default="")
ap.add_argument("--compare", nargs=2)
ap.add_argument("--rules", default="", help='"1.5": the result-changing rules of 1.6 put back (_versions.rules_of_1_5), to compare everything else with a 1.4 reference')
args = ap.parse_args()


# =========================================================================================
# compare
# =========================================================================================
def compare(a, b):
    diffs = []
    names = sorted(set(os.listdir(a)) | set(os.listdir(b)))
    for n in names:
        pa, pb = os.path.join(a, n), os.path.join(b, n)
        if not (os.path.exists(pa) and os.path.exists(pb)):
            diffs.append(f"{n}: only in one folder")
            continue
        if n == "png":
            continue
        if n.endswith(".npz"):
            za, zb = np.load(pa, allow_pickle=False), np.load(pb, allow_pickle=False)
            if sorted(za.files) != sorted(zb.files):
                diffs.append(f"{n}: keys {sorted(set(za.files) ^ set(zb.files))}")
            for k in sorted(set(za.files) & set(zb.files)):
                x, y = za[k], zb[k]
                same = x.shape == y.shape and (np.array_equal(x, y, equal_nan=True)
                                               if x.dtype.kind in "fc" else np.array_equal(x, y))
                if not same:
                    extra = ""
                    if x.shape == y.shape and x.dtype.kind == "f":
                        with np.errstate(all="ignore"):
                            extra = f" max abs diff {np.nanmax(np.abs(x - y)):.3g}"
                    diffs.append(f"{n}[{k}]: differs{extra}")
        elif n.endswith(".json"):
            ja, jb = json.load(open(pa, encoding="utf-8")), json.load(open(pb, encoding="utf-8"))
            if n == "origin_log.json":
                # the names of a DataFrame's columns (up to 1.5) never reached Origin as such: every label
                # row is written by set_label afterwards. Shape and content hash are what is compared.
                for log_ in (ja, jb):
                    for calls in log_.values():
                        for call in calls:
                            if call[0] == "sheet.from_df" and isinstance(call[-1], dict):
                                call[-1].pop("columns", None)
            if ja != jb:
                keys = sorted(set(ja) | set(jb)) if isinstance(ja, dict) and isinstance(jb, dict) else []
                bad = [k for k in keys if ja.get(k) != jb.get(k)]
                diffs.append(f"{n}: differs in {bad[:8] or 'content'}")
        else:
            if not filecmp.cmp(pa, pb, shallow=False):
                diffs.append(f"{n}: bytes differ")
    pa, pb = os.path.join(a, "png"), os.path.join(b, "png")
    png_diff = []
    if os.path.isdir(pa) and os.path.isdir(pb):
        import matplotlib.image as mpimg
        for n in sorted(set(os.listdir(pa)) | set(os.listdir(pb))):
            fa, fb = os.path.join(pa, n), os.path.join(pb, n)
            if not (os.path.exists(fa) and os.path.exists(fb)):
                png_diff.append(f"png/{n}: only in one folder")
                continue
            x, y = mpimg.imread(fa), mpimg.imread(fb)
            if x.shape != y.shape or not np.array_equal(x, y):
                npx = int((x != y).any(axis=-1).sum()) if x.shape == y.shape else -1
                png_diff.append(f"png/{n}: {npx} pixels differ")
    return diffs, png_diff


if args.compare:
    d, p = compare(*args.compare)
    for line in d:
        print("DIFF", line)
    for line in p:
        print("PNG ", line)
    print(f"RESULT: {len(d)} data differences, {len(p)} picture differences")
    sys.exit(1 if (d or p) else 0)

# =========================================================================================
# produce
# =========================================================================================
if args.target in ("", "package"):
    T = _versions.load_package()
elif os.path.exists(args.target):
    T = _versions.load(path=args.target)
else:
    T = _versions.load(args.target)
OUT = os.path.abspath(args.out)
os.makedirs(os.path.join(OUT, "png"), exist_ok=True)

import tkinter as tk                          # noqa: E402
from tkinter import ttk                       # noqa: E402

ROOT = _versions.ROOT
if args.rules == "1.5":
    _versions.rules_of_1_5(T)
S = _versions.samples()[0]
N = _versions.samples()[1]
boxes, saves = [], {"path": ""}
for kind in ("showerror", "showwarning", "showinfo"):
    setattr(T.messagebox, kind, lambda title="", msg="", _k=kind, **kw: boxes.append([_k, str(title), str(msg)]))
for kind in ("askyesno", "askokcancel"):
    if hasattr(T.messagebox, kind):
        setattr(T.messagebox, kind, lambda *a, **k: True)
T.filedialog.asksaveasfilename = lambda **kw: saves["path"]

# ---- a stand-in for originpro / pythoncom that records what the export does ---------------
origin_log = {}


def digest(obj):
    """A value as something JSON can hold and compare (arrays and tables by content hash)."""
    try:
        import pandas as pd
        if isinstance(obj, pd.DataFrame):
            return {"columns": [str(c) for c in obj.columns], "shape": list(obj.shape),
                    "sha": hashlib.sha256(np.ascontiguousarray(obj.to_numpy(dtype=float)).tobytes()).hexdigest()}
    except ImportError:
        pass
    if isinstance(obj, np.ndarray):
        return {"shape": list(obj.shape), "sha": hashlib.sha256(np.ascontiguousarray(obj).tobytes()).hexdigest()}
    if isinstance(obj, (list, tuple)):
        return [digest(o) for o in obj]
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    return type(obj).__name__


class FakeSheet:
    def __init__(self, log, name):
        self._log, self.name, self._columns = log, name, {}

    def __setattr__(self, key, value):
        if key == "cols":
            # Since 1.6 (D-27) the column count is set first and the table then arrives column by column
            # (from_list). It is recorded as up to 1.5 - the one table from_df() got (same shape, same hash
            # of the numbers), then the column count - so that the log stays comparable with a reference
            # made before. Both entries are written when the labels start (set_label).
            object.__setattr__(self, "_held_cols", ["sheet.set", self.name, key, digest(value)])
        elif not key.startswith("_") and key != "name":
            self._log.append(["sheet.set", self.name, key, digest(value)])
        object.__setattr__(self, key, value)

    def from_list(self, j, data, *a, **k):
        self._columns[j] = np.asarray(data, float)

    def _flush(self):
        if self._columns:
            table = np.column_stack([self._columns[j] for j in sorted(self._columns)])
            self._log.append(["sheet.from_df", self.name, {
                "shape": list(table.shape),
                "sha": hashlib.sha256(np.ascontiguousarray(table).tobytes()).hexdigest()}])
            self._columns.clear()
        held = getattr(self, "_held_cols", None)
        if held:
            self._log.append(held)
            object.__setattr__(self, "_held_cols", None)

    def clear(self):
        self._log.append(["sheet.clear", self.name])

    def from_df(self, df):
        self._log.append(["sheet.from_df", self.name, digest(df)])

    def set_label(self, j, text, kind):
        self._flush()
        self._log.append(["sheet.set_label", self.name, j, text, kind])


class FakeBook:
    def __init__(self, log):
        self._log, self.name, self._sheets = log, "Book1", [FakeSheet(log, "Sheet1")]

    def __iter__(self):
        return iter(self._sheets)

    def __len__(self):
        return len(self._sheets)

    def __getitem__(self, i):
        return self._sheets[i]

    def add_sheet(self, name):
        self._log.append(["book.add_sheet", name])
        s = FakeSheet(self._log, name)
        self._sheets.append(s)
        return s


def install_fake_origin(log):
    op = types.ModuleType("originpro")
    state = {"book": None}

    def new(*a, **k):
        log.append(["op.new"]); state["book"] = None
        return True

    def op_open(path, *a, **k):
        log.append(["op.open", os.path.basename(path)])
        return True

    def find_book(kind, name):
        log.append(["op.find_book", kind, name])
        return state["book"]

    def new_book(kind):
        log.append(["op.new_book", kind])
        state["book"] = FakeBook(log)
        return state["book"]

    def save(path):
        log.append(["op.save", os.path.basename(path)])
        return True

    def op_exit():
        log.append(["op.exit"])

    op.new, op.open, op.find_book, op.new_book, op.save, op.exit = new, op_open, find_book, new_book, save, op_exit
    pc = types.ModuleType("pythoncom")
    pc.CoInitialize = lambda: None
    pc.CoUninitialize = lambda: None
    sys.modules["originpro"], sys.modules["pythoncom"] = op, pc


root = tk.Tk()
root.geometry("1440x920+0+0")
root.title("artefacts")
T.apply_theme(root)
nb = ttk.Notebook(root)
nb.pack(fill="both", expand=True)
phu_tab, ptu_tab = ttk.Frame(nb), ttk.Frame(nb)
nb.add(phu_tab, text="PHU  ·  TRES")
nb.add(ptu_tab, text="PTU  ·  FLIM")
app = T.TRESViewer(phu_tab, None)
flim = T.FLIMViewer(ptu_tab)
callback_errors = []
root.report_callback_exception = lambda *a: callback_errors.append(str(a[1]))


def pump(seconds=0.05):
    end = time.time() + seconds
    root.update()
    while time.time() < end:
        root.update()
        time.sleep(0.005)


def wait(dlg, limit=180):
    end = time.time() + limit
    pump(0.05)
    while dlg._running and time.time() < end:
        pump(0.02)
    pump(0.1)
    assert not dlg._running, "fit did not finish"


phu_cache = {}


def fresh(path, **settings):
    """Close the windows, load ``path`` and put the main-window controls as asked."""
    for w in (app._crop_win, app._mask_win, app._kinetics_win, app._global_win):
        if w is not None and w.alive:
            w._on_close()
    s = dict(bin="16 ps", bg=True, t0=False, irf=True, offset="-50", bg_window=None)
    s.update(settings)
    app.var_bin.set(s["bin"]); app.var_bgsub.set(s["bg"]); app.var_t0.set(s["t0"]); app.var_irf.set(s["irf"])
    app.var_offset.set(s["offset"])
    app.load(path)
    pump()
    if s["bg_window"]:
        app.var_bg_lo.set(s["bg_window"][0]); app.var_bg_hi.set(s["bg_window"][1])
        app.apply_params()
    app.apply_offset()
    pump()


def solvent_of(path):
    """A synthetic solvent on the sample's grid: the sample's curves in reverse order, x1.5."""
    if path not in phu_cache:
        phu_cache[path] = T.read_phu(path)
    d = copy.copy(phu_cache[path])
    d["counts"] = (phu_cache[path]["counts"][::-1].astype(np.uint64) * 3 // 2).astype(np.uint32)
    d["path"] = r"C:\somewhere\blank.phu"
    return d


def crop(wl=None, t=None, solvent=None, scale=0.5):
    app.open_crop(); pump()
    c = app._crop_win
    m = app.model
    if solvent is not None:
        c._solvent = solvent
        c._sync_solvent_controls()
        c._set_scale(scale)
    if wl:
        c.var_wl_lo.set(f"{m.wls[wl[0]]:g}"); c.var_wl_hi.set(f"{m.wls[wl[1]]:g}")
    if t:
        c.var_t_lo.set(str(t[0])); c.var_t_hi.set(str(t[1]))
    c._update_overlay()
    c._apply()
    pump()
    return c


def mask(i0, i1):
    app.open_mask(); pump()
    mk = app._mask_win
    wl = app.model.wls
    mk.var_lo.set(f"{wl[i0]:g}"); mk.var_hi.set(f"{wl[i1]:g}")
    mk._add()
    pump()
    return mk


def table(dlg, rows):
    """rows: (tau, fixed, stretched, beta, beta_fixed) per component."""
    dlg.var_n.set(str(len(rows))); dlg.table.set_n(len(rows))
    for r, (tau, fix, st, beta, bfix) in zip(dlg.table.rows, rows):
        r["tau"].set(str(tau)); r["fix"].set(fix); r["st"].set(st); r["beta"].set(str(beta)); r["bfix"].set(bfix)


def model_arrays(prefix=""):
    m = app.model
    out = {prefix + "E": m.E, prefix + "times": m.times, prefix + "wls": m.wls,
           prefix + "spec_total": m.spec_total, prefix + "decay_total": m.decay_total,
           prefix + "scalars": np.array([m.vmax, m.dt_ps, m.t_lo, m.t_hi, m.t0, getattr(m, "clip_frac", 0.0),
                                         m.n_w, m.n_t], float)}
    if m.irf is not None:
        out[prefix + "irf"] = np.asarray(m.irf, float)
    return out


def fit_arrays(res, prefix):
    out = {}
    for k, v in res.items():
        if k == "info":
            for kk, vv in v.items():
                if isinstance(vv, (int, float, np.integer, np.floating)):
                    out[f"{prefix}info_{kk}"] = np.array(float(vv))
        elif isinstance(v, np.ndarray):
            out[prefix + k] = v
        elif isinstance(v, (int, float, np.integer, np.floating, bool)):
            out[prefix + k] = np.array(float(v))
    return out


def export_main(tag):
    app.var_out_csv.set(True); app.var_out_opju.set(False)
    saves["path"] = os.path.join(OUT, f"{tag}.csv")
    app.export_data()
    pump()


def export_dialog(dlg, tag):
    app.var_out_csv.set(True); app.var_out_opju.set(False)
    saves["path"] = os.path.join(OUT, f"{tag}.csv")
    dlg.export_results()
    pump()


def kinetics(rows, inf=False, t0_fixed=True, fw_fixed=True, irf_mode="numerical", wl_index=None, hw="0"):
    app.open_kinetics(); pump()
    k = app._kinetics_win
    if wl_index is not None:
        k.var_wl.set(f"{app.model.wls[wl_index]:.2f}")
    k.var_hw.set(hw)
    k._on_wl_change()
    table(k, rows)
    k.var_inf.set(inf); k.var_t0_fix.set(t0_fixed); k.var_fw_fix.set(fw_fixed); k.var_irf_mode.set(irf_mode)
    k.run_fit()
    wait(k)
    assert k._last is not None, boxes[-3:]
    return k


def global_fit(rows, inf=False, method="TRF (fast)", irf_mode="numerical", t0_fixed=True, fw_fixed=True):
    app.open_global_analysis(); pump()
    g = app._global_win
    table(g, rows)
    g.var_inf.set(inf); g.var_opt.set(method); g.var_irf_mode.set(irf_mode)
    g.var_t0_fix.set(t0_fixed); g.var_fw_fix.set(fw_fixed)
    g.run_fit()
    wait(g)
    assert g._last is not None, boxes[-3:]
    return g


E2 = [(100, False, False, 1, False), (1000, False, False, 1, False)]
E3 = [(50, False, False, 1, False), (500, False, False, 1, False), (5000, False, False, 1, False)]
cases = {}


def case(n):
    def deco(fn):
        cases[n] = fn
        return fn
    return deco


@case(1)
def _():
    fresh(S)
    export_main("case_01")
    return model_arrays()


@case(2)
def _():
    fresh(S, bin="4 ps")
    return model_arrays()


@case(3)
def _():
    fresh(S, bin="64 ps", bg=False)
    return model_arrays()


@case(4)
def _():
    fresh(S, t0=True, bg_window=("-2500", "-1200"))
    return model_arrays()


@case(5)
def _():
    out = {}
    for off in ("0", "-50", "12.5"):
        fresh(S, offset=off)
        out.update(model_arrays(f"off{off}_"))
    return out


@case(6)
def _():
    fresh(S)
    crop(wl=(4, -6), t=(1500, 18000))
    mask(8, 10)
    export_main("case_06")
    return model_arrays()


@case(7)
def _():
    fresh(S)
    crop(solvent=solvent_of(S), scale=0.5)
    export_main("case_07")
    out = model_arrays()
    out["solvent_spectrum"] = app.model.solvent_spectrum()
    return out


@case(8)
def _():
    fresh(S)
    k = kinetics([(500, False, False, 1, False)])
    export_dialog(k, "case_08")
    return fit_arrays(k._last, "kin_")


@case(9)
def _():
    fresh(S)
    k = kinetics(E2, inf=True, t0_fixed=False)
    export_dialog(k, "case_09")
    return fit_arrays(k._last, "kin_")


@case(10)
def _():
    out = {}
    rows = [(50, False, False, 1, False), (500, True, False, 1, False), (5000, False, True, 0.8, False)]
    for mode in ("numerical", "skip"):
        fresh(S, bin="64 ps")
        crop(t=(2000, 24000))
        k = kinetics(rows, irf_mode=mode, wl_index=20)
        out.update(fit_arrays(k._last, f"kin_{mode}_"))
    return out


@case(11)
def _():
    fresh(S)
    crop(wl=(6, -8), t=(1000, 20000))
    g = global_fit(E2)
    export_dialog(g, "case_11")
    return fit_arrays(g._last, "glob_")


@case(12)
def _():
    fresh(S)
    g = global_fit(E3, inf=True, method="Nelder-Mead")
    export_dialog(g, "case_12")
    return fit_arrays(g._last, "glob_")


@case(13)
def _():
    fresh(N)
    out = model_arrays()
    k = kinetics(E2)
    out.update(fit_arrays(k._last, "kin_"))
    g = global_fit(E2)
    out.update(fit_arrays(g._last, "glob_"))
    export_main("case_13")
    return out


@case(14)
def _():
    fresh(N, irf=False, bin="8 ps")
    return model_arrays()


@case(15)
def _():
    fresh(S)
    crop(solvent=solvent_of(S), scale=0.5)
    mask(8, 10)
    g = global_fit(E2)
    export_dialog(g, "case_15")
    out = model_arrays()
    out.update(fit_arrays(g._last, "glob_"))
    return out


@case(16)
def _():
    fresh(N, t0=True)
    crop(wl=(3, -4), t=(1000, 30000))
    k = kinetics(E2, wl_index=12, hw="6")
    export_dialog(k, "case_16")
    out = model_arrays()
    out.update(fit_arrays(k._last, "kin_"))
    return out


for n in sorted(cases):
    t = time.perf_counter()
    arrays = cases[n]()
    np.savez(os.path.join(OUT, f"case_{n:02d}.npz"), **{k: np.asarray(v) for k, v in arrays.items()})
    print(f"case {n:2d}: {len(arrays):2d} arrays, {time.perf_counter() - t:5.1f} s", flush=True)

# ---- the .opju export path, on the recording stand-in ---------------------------------------
log = []
install_fake_origin(log)
fresh(S)
app.var_out_csv.set(False); app.var_out_opju.set(True)
saves["path"] = os.path.join(OUT, "origin_main.opju")
app.export_data(); pump()
origin_log["main"] = list(log); log.clear()
k = kinetics(E2)
saves["path"] = os.path.join(OUT, "origin_kin.opju")
k.export_results(); pump()
origin_log["kinetics"] = list(log); log.clear()
g = global_fit(E2, inf=True)
saves["path"] = os.path.join(OUT, "origin_glob.opju")
g.export_results(); pump()
origin_log["global"] = list(log); log.clear()
app.var_out_csv.set(True); app.var_out_opju.set(False)
json.dump(origin_log, open(os.path.join(OUT, "origin_log.json"), "w", encoding="utf-8"), indent=0, ensure_ascii=False)
print("origin log:", {k: len(v) for k, v in origin_log.items()}, flush=True)

# ---- FLIM processing on synthetic T3 records ---------------------------------------------------


def rec(ch, dt, ns=0):
    return (ch << 28) | (dt << 16) | ns


rng = np.random.default_rng(1)
nx, ny, nbins = 9, 7, 64
R = []
for y in range(ny + 2):                       # two lines more than the image holds
    xs = range(nx) if y % 2 == 0 else range(nx - 1, -1, -1)
    for x in xs:
        R.append(rec(15, 1))
        for _ in range(int(rng.integers(0, 6))):
            R.append(rec(1, int(rng.integers(0, nbins)), 7))
        if rng.random() < 0.3:
            R.append(rec(15, 0))
    R.append(rec(15, 2))
    R.append(rec(1, int(rng.integers(0, nbins)), 7))      # a photon during the flyback
records = np.array(R, dtype=np.uint32)
hist = T.process_records_cpu(records, nx, ny, nbins)
flim_out = {"records": records, "hist": hist, "intensity": np.asarray(T.compute_intensity(hist))}
lt = T.compute_lifetime_map(hist, min_photons=3)
for i, part in enumerate(lt if isinstance(lt, tuple) else (lt,)):
    flim_out[f"lifetime_{i}"] = np.asarray(part)
np.savez(os.path.join(OUT, "flim.npz"), **flim_out)
print("flim: hist sum", int(hist.sum()), flush=True)

# ---- windows: widget trees, pictures, artist data --------------------------------------------


def tree(w):
    out = []
    for c in w.winfo_children():
        item = {"class": type(c).__name__}
        for opt in ("text", "values", "width", "state", "from", "to", "show", "orient"):
            try:
                v = c.cget(opt)
            except tk.TclError:
                continue
            item[opt] = [str(x) for x in v] if isinstance(v, (tuple, list)) else str(v)
        mgr = c.winfo_manager()
        item["manager"] = mgr
        try:
            info = c.pack_info() if mgr == "pack" else c.grid_info() if mgr == "grid" else {}
            item["place"] = {k: str(v) for k, v in info.items() if k != "in"}
        except tk.TclError:
            pass
        kids = tree(c)
        if kids:
            item["children"] = kids
        out.append(item)
    return out


def artists(fig):
    out = []
    for ax in fig.axes:
        a = {"xlim": [float(v) for v in ax.get_xlim()], "ylim": [float(v) for v in ax.get_ylim()],
             "xscale": ax.get_xscale(), "yscale": ax.get_yscale(),
             "title": ax.get_title(), "xlabel": ax.get_xlabel(), "ylabel": ax.get_ylabel(),
             "lines": [], "images": [], "texts": [t.get_text() for t in ax.texts],
             "patches": len(ax.patches)}
        for ln in ax.lines:
            xy = np.column_stack([np.asarray(ln.get_xdata(), float), np.asarray(ln.get_ydata(), float)]) \
                if len(np.atleast_1d(ln.get_xdata())) == len(np.atleast_1d(ln.get_ydata())) else np.empty(0)
            a["lines"].append([hashlib.sha256(np.ascontiguousarray(xy).tobytes()).hexdigest()[:16],
                               str(ln.get_color()), float(ln.get_linewidth()), str(ln.get_linestyle()),
                               bool(ln.get_visible())])
        for im in ax.images:
            arr = np.ma.getdata(im.get_array()).astype(float)
            a["images"].append([list(arr.shape), hashlib.sha256(np.ascontiguousarray(arr).tobytes()).hexdigest()[:16],
                                [float(v) for v in im.get_extent()], type(im.norm).__name__,
                                float(im.norm.vmin), float(im.norm.vmax)])
        leg = ax.get_legend()
        a["legend"] = [t.get_text() for t in leg.get_texts()] if leg is not None else None
        out.append(a)
    return out


widgets, art = {}, {}


def snap(name, top, frame, fig, canvas):
    pump(0.3)
    canvas.draw()
    pump(0.1)
    widgets[name] = {"title": str(top.title()), "tree": tree(frame)}
    fig.savefig(os.path.join(OUT, "png", name + ".png"), dpi=100)
    art[name] = artists(fig)


fresh(S)
snap("main_tres", root, phu_tab, app.fig, app.canvas)
nb.select(ptu_tab); pump(0.3)
snap("main_flim_empty", root, ptu_tab, flim.fig, flim.canvas)
nb.select(phu_tab); pump(0.2)
c = crop(wl=(4, -6), t=(1500, 18000))
snap("crop", c.win, c.win, c.fig, c.canvas)
mk = mask(8, 10)
snap("mask", mk.win, mk.win, mk.fig, mk.canvas)
app.open_kinetics(); pump()
k = app._kinetics_win
snap("kinetics_before", k.win, k.win, k.fig, k.canvas)
k = kinetics(E2)
snap("kinetics_after", k.win, k.win, k.fig, k.canvas)
app.open_global_analysis(); pump()
g = app._global_win
snap("global_before", g.win, g.win, g.fig, g.canvas)
g = global_fit(E2)
snap("global_after", g.win, g.win, g.fig, g.canvas)
json.dump(widgets, open(os.path.join(OUT, "widgets.json"), "w", encoding="utf-8"), indent=0, ensure_ascii=False)
json.dump(art, open(os.path.join(OUT, "artists.json"), "w", encoding="utf-8"), indent=0, ensure_ascii=False)
boxes = [[k, t, m.replace(OUT, "<out>")] for k, t, m in boxes]     # the folder differs from run to run
json.dump({"boxes": boxes, "callback_errors": callback_errors},
          open(os.path.join(OUT, "messages.json"), "w", encoding="utf-8"), indent=0, ensure_ascii=False)
print("windows:", sorted(widgets), "| message boxes:", len(boxes), "| callback errors:", len(callback_errors), flush=True)
root.destroy()
