"""Stage 3, the items left for the end: the three small ones outside the groups (A-18, A-19, A-20), the .opju
export without pandas (D-27) and the structure group G11 (A-11 / C-4, C-24, C-13, B-22, C-23, A-21), display
scaling. See _harness.py."""
import dis
import os
import struct

import numpy as np

from _harness import *                        # noqa: F401,F403
from _harness import SAMPLE_B, NEW, OLD, SAMPLE_A, TMP, boxes, check, finish, make_app, make_phu, pump, section, wait

# ---------------------------------------------------------------------------------------------
if section("A-18"):
    rgb = NEW.wavelength_to_rgb
    outside = [rgb(w) for w in (0, 63, 300, 350, 379.9, 830.1, 1200)]
    check("outside 380-830 nm (UV, IR, an index axis) the ribbon is one neutral grey, not blue or black",
          len(set(outside)) == 1 and len(set(outside[0])) == 1 and 0.3 < outside[0][0] < 0.8, str(outside))
    inside = [w for w in np.arange(380.0, 830.5, 0.5)]
    check("inside the visible range nothing changed", all(rgb(w) == OLD.wavelength_to_rgb(w) for w in inside),
          str([w for w in inside if rgb(w) != OLD.wavelength_to_rgb(w)][:5]))

# ---------------------------------------------------------------------------------------------
if section("A-19"):
    def with_comment(raw, typ=None, name="c.phu"):
        typ = NEW.TY_ANSISTRING if typ is None else typ
        return NEW.read_phu(make_phu(os.path.join(TMP, name), patch={("File_Comment", -1): (typ, raw)}))["comment"]

    text = "측정 메모: 톨루엔"
    check("a plain ASCII comment reads as before", with_comment(b"made by hand\x00\x00") == "made by hand")
    check("a UTF-8 comment is read", with_comment(text.encode("utf-8") + b"\x00") == text, with_comment(text.encode("utf-8") + b"\x00"))
    try:
        raw = text.encode("mbcs")
        ansi_ok = raw.decode("mbcs") == text
    except (LookupError, UnicodeError):
        raw, ansi_ok = b"", False
    if ansi_ok:
        check("a comment in this computer's ANSI code page is read (it came back as replacement characters)",
              with_comment(raw + b"\x00\x00") == text, repr(with_comment(raw + b"\x00\x00")))
    else:
        check("(this computer's ANSI code page cannot hold the Korean test text: checked with Latin-1 instead)",
              with_comment("café".encode("cp1252") + b"\x00") == "café")
    check("bytes that are no text in any of them still give a string, without an error",
          isinstance(with_comment(b"\xff\xfe\x81\x00"), str))
    wide = "一Ā note".encode("utf-16-le") + b"\x00\x00"        # U+0100 ends in a zero byte
    check("a wide string is cut at its NUL character, not at two zero bytes inside it",
          with_comment(wide, NEW.TY_WIDESTRING) == "一Ā note", repr(with_comment(wide, NEW.TY_WIDESTRING)))
    a, b = NEW.read_phu(SAMPLE_A), OLD.read_phu(SAMPLE_A)
    check("the sample file's strings are what they were",
          all(a[k] == b[k] for k in ("comment", "param_name", "param_unit", "hw_type", "serial")))

# ---------------------------------------------------------------------------------------------
if section("A-20"):
    import importlib
    fitting = importlib.import_module(NEW.fit_single_trace.__module__)
    stores = [ins.argval for ins in dis.get_instructions(fitting._ensure_scipy) if ins.opname == "STORE_GLOBAL"]
    check("_ensure_scipy sets its guard (_erfc) after everything the fits call", stores and stores[-1] == "_erfc"
          and set(stores) == {"_erfc", "_erfcx", "_minimize", "_least_squares"}, str(stores))
    t = np.arange(200) * 16.0
    y = 100.0 * np.exp(-np.clip(t - 400.0, 0, None) / 500.0) * (t > 400.0)
    r = NEW.fit_single_trace(t, y, tau_init=np.array([300.0]), tau_fixed=np.array([False]), t0_init=400.0,
                             t0_fixed=True, fwhm_init=40.0, fwhm_fixed=True)
    check("a fit still runs", abs(r["tau"][0] - 500.0) < 25.0, str(r["tau"]))

# ---------------------------------------------------------------------------------------------
if section("D-27"):
    import builtins
    import sys
    import types

    class Sheet:
        def __init__(self, name):
            self.name, self.columns, self.labels, self.cols, self.cleared = name, {}, {}, None, 0

        def clear(self):
            self.cleared += 1
            self.columns = {}

        def from_list(self, col, data, *a, **k):
            self.columns[col] = list(data)

        def set_label(self, col, text, kind):
            self.labels[(col, kind)] = text

    class Book:
        name = "Book1"

        def __init__(self):
            self.sheets = [Sheet("Sheet1")]

        def __iter__(self):
            return iter(self.sheets)

        def add_sheet(self, name):
            self.sheets.append(Sheet(name))
            return self.sheets[-1]

    state = {}
    op, com = types.ModuleType("originpro"), types.ModuleType("pythoncom")
    op.new = lambda: state.pop("book", None)
    op.open = lambda path: True
    op.find_book = lambda kind, name: state.get("book")
    op.new_book = lambda kind: state.setdefault("book", Book())
    op.save = lambda path: True
    op.exit = lambda: None
    com.CoInitialize = com.CoUninitialize = lambda: None
    saved = {k: sys.modules.get(k) for k in ("originpro", "pythoncom", "pandas")}
    sys.modules["originpro"], sys.modules["pythoncom"] = op, com
    sys.modules.pop("pandas", None)
    real_import = builtins.__import__

    def no_pandas(name, *a, **k):
        if name == "pandas" or name.startswith("pandas."):
            raise ImportError("No module named 'pandas' (blocked by the test)")
        return real_import(name, *a, **k)

    builtins.__import__ = no_pandas
    try:
        top, app = make_app(SAMPLE_A)
        m = app.model
        tabs = app._write_opju(os.path.join(TMP, "d27_new.opju"), "run")
        sheets = {s.name: s for s in state["book"].sheets}
        check("without pandas: the data export writes its two tabs", tuple(tabs) == ("run_TRESmap", "run_steadystate")
              and sorted(sheets) == ["run_TRESmap", "run_steadystate"], f"{tabs} {sorted(sheets)}")
        tres, steady = sheets["run_TRESmap"], sheets["run_steadystate"]
        check("the map sheet: time in column 0, one column per wavelength, the numbers of the model",
              tres.cols == m.n_w + 1 == len(tres.columns) and np.array_equal(tres.columns[0], m.times)
              and all(np.array_equal(tres.columns[j + 1], m.E[j, :], equal_nan=True) for j in range(m.n_w)),
              f"{tres.cols} {len(tres.columns)}")
        check("... every value is a plain float (as a DataFrame column was handed over)",
              all(type(v) is float for col in tres.columns.values() for v in col[:3]))
        check("... labels as before: time / ps, then the wavelength as each column's comment",
              (tres.labels[(0, "L")], tres.labels[(0, "U")], tres.labels[(0, "C")]) == ("time", "ps", "")
              and all(tres.labels[(j + 1, "L")] == "" and tres.labels[(j + 1, "U")] == ""
                      and tres.labels[(j + 1, "C")] == f"{m.wls[j]:g}" for j in range(m.n_w)))
        check("the steady-state sheet: three columns, wavelength / sum / normalised",
              steady.cols == 3 and np.array_equal(steady.columns[0], m.wls)
              and np.array_equal(steady.columns[1], m.spec_total, equal_nan=True)
              and steady.labels[(2, "L")] == "Nor.", str(steady.cols))
        # the two fit windows
        app.open_kinetics(); app.open_global_analysis(); pump(0.4)
        k, g = app._kinetics_win, app._global_win
        g.var_n.set("2"); g.table.set_n(2)
        k.run_fit(); g.run_fit()
        wait(lambda: not k._running and not g._running, 180); pump(0.3)
        got = {}
        real = app.export_analysis

        def fake(base, items, **kw):
            for it in items:
                ws = Sheet(it["suffix"])
                it["fill"](ws)
                got[it["suffix"]] = ws
        app.export_analysis = fake
        try:
            k.export_results(); g.export_results()
        finally:
            app.export_analysis = real
        kin = got["kinetics"]
        check("the Kinetics sheet: delay, data, fit, residual of the result",
              kin.cols == 4 and np.array_equal(kin.columns[0], k._last["_t_fit"])
              and np.array_equal(kin.columns[2], k._last["fit"]) and kin.labels[(0, "L")] == "Delay", str(kin.cols))
        dads = got["DADS"]
        check("the DADS sheet: wavelength + one column per component, labelled with its lifetime",
              dads.cols == 3 and np.array_equal(dads.columns[0], g._fit_wls)
              and np.array_equal(dads.columns[1], g._last["A"][:, 0]) and dads.labels[(1, "C")].startswith("tau="),
              f"{dads.cols} {dads.labels.get((1, 'C'))}")
        check("pandas was never imported", "pandas" not in sys.modules)
        top.destroy()
    finally:
        builtins.__import__ = real_import
        for name, mod in saved.items():
            if mod is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = mod
    import io as _io
    used = [f for f in NEW.sources() if "import pandas" in _io.open(f, encoding="utf-8").read()]
    check("no module of the program imports pandas", not used, str(used))
    lock = _io.open(os.path.join(os.path.dirname(os.path.dirname(NEW.__file__)), "requirements-lock.txt"),
                    encoding="utf-8").read()
    check("the requirement files do not ask for pandas; matplotlib's own needs are still pinned",
          "pandas" not in lock and "tzdata" not in lock and "python-dateutil==" in lock and "six==" in lock)

# ---------------------------------------------------------------------------------------------
if section("A-11"):
    grid = getattr(NEW, "wavelength_grid", None)
    if grid is None:
        check("the layout of the wavelength axis is a function of the wavelength list (wavelength_grid)", False)
    else:
        col, n, step = grid(np.arange(390.0, 705.0, 5.0))
        check("even steps: one column per curve", list(col) == list(range(63)) and n == 63 and step == 5.0)
        col, n, step = grid(np.array([535.0, 550.0, 555.0, 560.0]))
        check("535, 550, 555, 560 nm: laid out in 5 nm steps with two empty columns after the first",
              list(col) == [0, 3, 4, 5] and n == 6 and step == 5.0, f"{list(col)} {n} {step}")
        col, n, step = grid(np.array([500.0, 507.0, 519.0]))
        check("a list that fits no grid stays one column per curve", list(col) == [0, 1, 2] and n == 3)
        check("one curve / none", grid(np.array([500.0]))[1] == 1 and grid(np.array([]))[1] == 1)
    # the sample B file with its first curve (535 nm) kept in the map
    top, app = make_app(SAMPLE_B)
    app.var_irf.set(False); app.apply_params(); pump(0.4)
    m = app.model
    check("(the file's list is 535, 550, 555 ... with the first curve kept)", list(m.wls[:3] - m.wl_offset) == [535.0, 550.0, 555.0],
          str(m.wls[:3]))
    img = np.asarray(np.ma.getdata(app.im.get_array()), float)    # the log colour scale masks what is below it
    x0, x1 = app.im.get_extent()[:2]
    width = (x1 - x0) / img.shape[1]

    def column_at(wl):
        return int((wl - x0) // width)

    wi = int(np.argmin(np.abs(m.wls - (550.0 + m.wl_offset))))
    check("main map: the column drawn at 550 nm holds the 550 nm curve (it was drawn at 538-543 nm)",
          np.array_equal(img[:, column_at(m.wls[wi])], m.E[wi], equal_nan=True),
          f"{img.shape} extent {x0}-{x1}")
    check("... and every curve sits in the column at its own wavelength",
          all(np.array_equal(img[:, column_at(w)], m.E[i], equal_nan=True) for i, w in enumerate(m.wls)))
    check("... the two steps nobody measured are empty columns",
          np.isnan(img[:, column_at(m.wls[0] + 5.0)]).all() and np.isnan(img[:, column_at(m.wls[0] + 10.0)]).all())
    check("... a point on the map is found as the curve drawn there", app.model.locate(float(m.wls[wi]), float(m.times[10]))[0] == wi)
    app.open_crop(); app.open_mask(); pump(0.4)
    cimg = np.asarray(app._crop_win._base_im.get_array(), float)
    check("the Crop and Mask maps use the same axis", cimg.shape[1] == img.shape[1]
          and tuple(app._crop_win._base_im.get_extent()[:2]) == tuple(app._crop_win._full.wl_edges)
          and np.asarray(app._mask_win.ax.images[0].get_array()).shape[1] == img.shape[1], f"{cimg.shape} {img.shape}")
    out = os.path.join(TMP, "a11.png")
    app._write_map_image(out, *app._map_arrays_full())
    check("the exported picture is drawn without an error", os.path.getsize(out) > 10000)
    app.var_irf.set(True); app.apply_params(); pump(0.3)
    check("with the first curve as IRF the sweep is even again: one column per curve",
          app.model.n_cols == app.model.n_w and app.model.on_grid(app.model.E) is app.model.E)
    top.destroy()
    # a sweep taken from long to short wavelengths
    desc = make_phu(os.path.join(TMP, "desc.phu"), ncurves=6,
                    patch={("ParValue0", i): (NEW.TY_FLOAT8, 600.0 - 5.0 * i) for i in range(6)})
    p = NEW.read_phu(desc)
    md = NEW.TRESModel(p)
    check("a descending wavelength list: the model holds the curves in ascending order",
          list(md.wls) == sorted(md.wls) and md.wl_edges[0] < md.wl_edges[1], f"{md.wls} {md.wl_edges}")
    row = int(np.argmin(np.abs(md.wls - 590.0)))
    check("... each row is still its own curve", np.array_equal(md.E_raw[row], p["counts"][2].reshape(-1, 4).sum(axis=1)[:md.n_t]),
          str(md.wls))
    check("... and a point is found on it", md.locate(590.0, float(md.times[3])) == (row, 3), str(md.locate(590.0, float(md.times[3]))))
    # the usual file is untouched
    new, old = NEW.TRESModel(NEW.read_phu(SAMPLE_A)), OLD.TRESModel(OLD.read_phu(SAMPLE_A))
    check("an evenly spaced file: wavelengths, map and axis edges are 1.4's",
          np.array_equal(new.wls, old.wls) and np.array_equal(new.E, old.E, equal_nan=True)
          and tuple(new.wl_edges) == tuple(old.wl_edges) and new.on_grid(new.E) is new.E)

# ---------------------------------------------------------------------------------------------
if section("C-4"):
    top, app = make_app(SAMPLE_A)
    m = app.model
    m.masks = [(488.0, 562.0)]                       # 15 curves in the middle
    m.rebuild(); app.redraw(full=True); pump(0.3)
    app.open_global_analysis(); pump(0.4)
    g = app._global_win
    g.var_n.set("2"); g.table.set_n(2)
    g.run_fit(); wait(lambda: not g._running, 180); pump(0.4)
    n_fit = len(g._fit_wls)
    check("(48 of 63 curves were fitted)", n_fit == 48 and m.n_w == 63, f"{n_fit} {m.n_w}")
    for ax, name in ((g.ax_data, "data"), (g.ax_fit, "fit"), (g.ax_resid, "residual")):
        im = ax.images[0]
        arr = np.asarray(np.ma.getdata(im.get_array()), float)
        x0, x1 = sorted(im.get_extent()[:2])
        width = (x1 - x0) / arr.shape[1]
        ok = arr.shape[1] == m.n_w and abs(x0 - m.wl_edges[0]) < 1e-9 and abs(x1 - m.wl_edges[1]) < 1e-9
        src = {"data": g._fit_D, "fit": g._last["fit"], "residual": g._fit_D - g._last["fit"]}[name]
        placed = all(np.array_equal(arr[:, int((w - x0) // width)], src[i]) for i, w in enumerate(g._fit_wls))
        empty = all(np.isnan(arr[:, int((w - x0) // width)]).all() for w in m.wls[m.mask_rows])
        check(f"{name} map: on the model's wavelength axis, each fitted curve in the column at its wavelength, "
              f"the masked band empty", ok and placed and empty, f"{arr.shape} {x0}-{x1} placed={placed} empty={empty}")
        y = sorted(im.get_extent()[2:])
        check(f"{name} map: the time axis runs from half a bin before the first delay to half a bin after the last",
              abs(y[0] - (g._fit_t[0] - m.dt_ps / 2)) < 1e-6 and abs(y[1] - (g._fit_t[-1] + m.dt_ps / 2)) < 1e-6, str(y))

    class Click:
        def __init__(self, ax, x):
            self.inaxes, self.xdata, self.ydata = ax, x, 1000.0

    picked = []
    for wl in (392.0, 483.0, 567.0, 616.0, 698.0):   # anywhere inside a cell
        g._on_map_click(Click(g.ax_data, wl)); pump(0.05)
        picked.append(g.ax_kin.get_title())
    want = [f"kinetics @ {w:.2f} nm" for w in (390.0, 485.0, 565.0, 615.0, 700.0)]
    check("a click on a column shows the kinetics of the curve drawn there", picked == want, f"{picked}")
    check("no error box", not [b for b in boxes if b[0] == "showerror"], str(boxes))
    top.destroy()

# ---------------------------------------------------------------------------------------------
if section("C-24"):
    top, app = make_app(SAMPLE_A)
    counts = {}
    for name, opener in (("Kinetics", app.open_kinetics), ("Global", app.open_global_analysis)):
        opener()
        win = app._kinetics_win if name == "Kinetics" else app._global_win
        seen = []
        win.canvas.mpl_connect("draw_event", lambda event, seen=seen: seen.append(tuple(win.canvas.get_width_height())))
        pump(1.2)
        counts[name] = list(seen)
        widget = win.canvas.get_tk_widget()
        check(f"{name}: the figure is drawn once when the window opens (it was twice)", len(seen) == 1, str(seen))
        check(f"{name}: ... at the size of its place in the window",
              bool(seen) and abs(seen[-1][0] - widget.winfo_width()) <= 2 and abs(seen[-1][1] - widget.winfo_height()) <= 2,
              f"{seen[-1:]} widget {widget.winfo_width()}x{widget.winfo_height()}")
    k = app._kinetics_win
    n0 = []
    k.canvas.mpl_connect("draw_event", lambda event: n0.append(1))
    k.var_scale.set("Linear"); k._refresh_plot(); pump(0.4)
    check("later changes still draw", len(n0) == 1, str(len(n0)))
    # a window that never gets a size is drawn all the same
    app._global_win._on_close(); pump(0.2)
    app.open_global_analysis()
    g = app._global_win
    g.win.withdraw()
    seen = []
    g.canvas.mpl_connect("draw_event", lambda event: seen.append(1))
    pump(1.0)
    check("a window that is not shown gets its picture too (drawn after a moment)", len(seen) >= 1, str(len(seen)))
    top.destroy()

# ---------------------------------------------------------------------------------------------
if section("C-13"):
    import time as _time
    top, app = make_app(SAMPLE_A)
    app.open_crop(); pump(0.8)
    c = app._crop_win
    draws = []
    c.canvas.mpl_connect("draw_event", lambda event: draws.append(1))

    class Move:
        name = "motion_notify_event"
        button, buttons, guiEvent, dblclick = None, (), None, False

        def __init__(self, wl, t):
            self.inaxes, self.xdata, self.ydata = c.ax, wl, t
            self.x, self.y = c.ax.transData.transform((wl, t))

    def shot():
        """The window's picture as it is on screen (the canvas buffer, slice included)."""
        return np.asarray(c.canvas.buffer_rgba()).copy()

    f = c._full
    times = [(k + 0.5) * f.dt_ps for k in (40, 90, 150, 220, 300)]
    t0 = _time.perf_counter()
    for t in times:
        c._on_motion(Move(550.0, t)); pump(0.0)
    blit_s = (_time.perf_counter() - t0) / len(times)
    pump(0.3)
    check("moving the pointer over five other time bins draws the figure not once (it was five times)",
          len(draws) == 0, f"{len(draws)} draws")
    check("... the slice shown is that of the last bin",
          c._slice_ti == 300 and np.array_equal(c.ln_t_sample.get_ydata(), c._raw0[:, 300])
          and "t = " in c.ax_t.get_legend().get_title().get_text(), f"{c._slice_ti}")
    partial = shot()
    c.canvas.draw(); pump(0.2)                # what a full draw gives for the same state
    full = shot()
    differ = int((np.abs(partial.astype(int) - full.astype(int)).max(axis=2) > 8).sum())
    check("... and the picture is the one a full draw gives (at most a few edge pixels apart)",
          partial.shape == full.shape and differ <= 40, f"{differ} of {partial.shape[0] * partial.shape[1]} pixels")
    draws.clear()
    c._on_leave(type("E", (), {"name": "figure_leave_event", "inaxes": None})()); pump(0.3)
    gone = shot()
    check("leaving the map takes the slice away, again without a draw of the figure",
          len(draws) == 0 and c._slice_ti is None and c.ax_t.get_legend() is None
          and int((np.abs(gone.astype(int) - full.astype(int)).max(axis=2) > 8).sum()) > 200,
          f"{len(draws)} draws")
    # a full draw (resize, zoom, range edit) still shows a pinned slice
    c._slice_pinned, c._slice_ti = True, 150
    c._draw_slice(); c._show_slice(); pump(0.1)
    before = shot()
    draws.clear()
    c._fit_view(); pump(0.4)
    after = shot()
    check("after a full draw (Fit view) a pinned slice is still on the picture",
          len(draws) >= 1 and int((np.abs(after.astype(int) - gone.astype(int)).max(axis=2) > 8).sum()) > 200)
    out = os.path.join(TMP, "c13.png")
    c.fig.savefig(out, dpi=100)
    import matplotlib.image as mpimg
    saved = (mpimg.imread(out)[..., :3] * 255).astype(int)
    pin_rgb = np.array([int(NEW.PIN[i:i + 2], 16) for i in (1, 3, 5)])
    check("a saved picture of the figure holds the slice too (the pinned marker line is in it)",
          int((np.abs(saved - pin_rgb).max(axis=2) < 12).sum()) > 200)
    print(f"INFO C-13: {1000 * blit_s:.1f} ms per pointer move (a full draw of this figure takes about 80 ms)")
    top.destroy()

# ---------------------------------------------------------------------------------------------
if section("A-21"):
    import inspect
    import importlib
    fitting = importlib.import_module(NEW.fit_single_trace.__module__)
    src = inspect.getsource(fitting)
    check("the model's columns are built in one place (_basis) for both kernels and build_ga_basis",
          hasattr(fitting, "_basis") and src.count("= stretched_irf_conv(") == 1    # the one call, in _basis
          and all("_basis(" in inspect.getsource(f) for f in (fitting.fit_single_trace, fitting.fit_global_analysis,
                                                              fitting.build_ga_basis)), str(src.count("= stretched_irf_conv(")))
    t = np.arange(400) * 16.0
    new = NEW.build_ga_basis(t, [150.0, 2000.0], 800.0, 300.0, True)
    old = OLD.build_ga_basis(t, [150.0, 2000.0], 800.0, 300.0, True)
    check("build_ga_basis gives 1.4's matrix, bit for bit", np.array_equal(new, old))
    check("both kernels take their Nelder-Mead options from one place",
          getattr(fitting, "NM_OPTIONS", None) == {"xatol": 1e-8, "maxiter": 5000, "maxfev": 20000, "disp": False}
          and src.count('"maxfev"') == 1, str(src.count('"maxfev"')))
    check("solvent_mismatch lives with the model", NEW.holders("solvent_mismatch")[0] == "model" and "util" not in NEW.holders("solvent_mismatch"),
          str(NEW.holders("solvent_mismatch")))
    p = NEW.read_phu(SAMPLE_A)
    check("the reader no longer returns the per-curve integrals nobody read", "integrals" not in p)
    m = NEW.TRESModel(p)
    first = m.t_data_ps
    real = p["counts"]
    p["counts"] = np.zeros_like(real)          # were it scanned again, the answer would change
    again = m.t_data_ps
    p["counts"] = real
    check("the length of the filled record is worked out once per model", first == again == OLD.TRESModel(OLD.read_phu(SAMPLE_A)).t_data_ps,
          f"{first} {again}")

# ---------------------------------------------------------------------------------------------
if section("C-23"):
    base = getattr(NEW, "_FitDialog", None)
    check("the Kinetics and the Global window share one base class (_FitDialog), the Crop window does not",
          base is not None and issubclass(NEW.KineticsDialog, base) and issubclass(NEW.GlobalAnalysisDialog, base)
          and not issubclass(NEW.CropDialog, base))
    if base is not None:
        once = ["_irf_row", "_irf_box", "_range_entries", "_run_buttons", "_export_row", "_report_box", "stop_fit",
                "_poll_queue", "_finish_run", "_started", "_fit_record", "_watch_model", "_follow_t0", "_irf_defaults"]
        twice = [n for n in once if n in vars(NEW.KineticsDialog) or n in vars(NEW.GlobalAnalysisDialog)
                 or n not in vars(base)]
        check("what both had is written once, in the base class", not twice, str(twice))
        check("each window says what it does with a message of its worker (_handle)",
              "_handle" in vars(NEW.KineticsDialog) and "_handle" in vars(NEW.GlobalAnalysisDialog))
        import inspect
        both = inspect.getsource(NEW.KineticsDialog) + inspect.getsource(NEW.GlobalAnalysisDialog)
        check("the CSV of a result is written by one function", both.count("write_fit_csv(") == 2
              and "np.savetxt" not in both and hasattr(NEW, "write_fit_csv"), str(both.count("np.savetxt")))
        check("the Crop and Mask windows do not carry the fit windows' methods",
              not hasattr(NEW.CropDialog, "_irf_defaults") and not hasattr(NEW.MaskDialog, "_fit_record"))
    parts = [getattr(NEW, n, None) for n in ("_CropView", "_CropSlice", "_CropSolvent")]
    check("the Crop window is made of three parts beside its own class: view, time slice, solvent",
          all(p is not None and issubclass(NEW.CropDialog, p) for p in parts)
          and "_zoomed" in vars(parts[0] or object) and "_show_slice" in vars(parts[1] or object)
          and "_load_solvent" in vars(parts[2] or object) and "_zoomed" not in vars(NEW.CropDialog))
    import inspect as _inspect
    n_lines = len(_inspect.getsource(NEW.CropDialog).splitlines())
    check("... and its own class is under 650 lines (it was 900)", n_lines < 650, str(n_lines))

# ---------------------------------------------------------------------------------------------
if section("B-22"):
    import inspect as _insp
    fig, exp = getattr(NEW, "_MapFigure", None), getattr(NEW, "_Export", None)
    check("the main window's class is made of two parts beside its own: the figure, the exports",
          fig is not None and exp is not None and issubclass(NEW.TRESViewer, fig) and issubclass(NEW.TRESViewer, exp))
    own = vars(NEW.TRESViewer)
    check("drawing and mouse handling are in the figure part, not in the window's own class",
          fig is not None and all(n in vars(fig) and n not in own for n in ("redraw", "update_cursor", "on_press", "_recolor")))
    check("everything written to disk or to Origin is in the export part",
          exp is not None and all(n in vars(exp) and n not in own
                                  for n in ("export_data", "export_analysis", "_write_map_csv", "_opju_write_tabs")))
    check("the window's own class keeps the file, the settings and the pop-up windows",
          all(n in own for n in ("load", "apply_params", "apply_offset", "open_crop", "_tell_dialogs")))
    n_lines = len(_insp.getsource(NEW.TRESViewer).splitlines())
    check("... and is under 600 lines (it was 1,600)", n_lines < 600, str(n_lines))
    src = _insp.getsource(NEW.TRESViewer)
    check("the four pop-up windows are opened by one method", "_open" in own and src.count("lift_and_refresh()") == 1,
          str(src.count("lift_and_refresh()")))
    top, app = make_app(SAMPLE_A)
    for name, attr in (("open_crop", "_crop_win"), ("open_mask", "_mask_win"), ("open_kinetics", "_kinetics_win"),
                       ("open_global_analysis", "_global_win")):
        getattr(app, name)(); pump(0.3)
        first = getattr(app, attr)
        getattr(app, name)(); pump(0.2)
        check(f"{name}: opens its window once, a second call raises the same one",
              first is not None and first.alive and getattr(app, attr) is first)
    top.destroy()

finish()
