"""Stage 3, group G5: what is on screen (review items B-1, B-16, B-14, B-15, B-2, B-12, C-12, C-21, C-26,
D-14, D-15, D-28, and the wording items B-18 / C-22). One section per item; see _harness.py."""
import os

import matplotlib.colors as mcolors

from _harness import *                        # noqa: F401,F403
from _harness import SAMPLE_B, NEW, SAMPLE_A, TMP, boxes, check, finish, make_app, make_phu, np, pump, root, section, wait
import tkinter as tk                          # noqa: E402
from tkinter import ttk                       # noqa: E402


def lum(color):
    r, g, b = mcolors.to_rgb(color)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def widgets(w):
    for c in w.winfo_children():
        yield c
        yield from widgets(c)


def squeezed(win, kinds=(ttk.Button, ttk.Checkbutton, ttk.Entry, ttk.Combobox, tk.Scale, ttk.Scale)):
    """Controls of ``win`` that got less room than they ask for (cut off or gone)."""
    out = []
    for c in widgets(win):
        if isinstance(c, kinds) and c.winfo_manager() and c.winfo_ismapped():
            if c.winfo_width() < c.winfo_reqwidth() - 1 or c.winfo_height() < c.winfo_reqheight() - 1:
                text = ""
                try:
                    text = str(c.cget("text"))
                except tk.TclError:
                    pass
                out.append(f"{type(c).__name__} {text!r} {c.winfo_width()}x{c.winfo_height()} "
                           f"of {c.winfo_reqwidth()}x{c.winfo_reqheight()}")
        elif isinstance(c, kinds) and c.winfo_manager() and not c.winfo_ismapped() and c.winfo_toplevel() is win:
            out.append(f"{type(c).__name__} not shown")
    return out


# ---------------------------------------------------------------------------------------------
if section("B-1"):
    # the read-out of a cursor that is not pinned must be readable on its dark card
    top, app = make_app(SAMPLE_A)
    m = app.model
    app.cursor, app.pinned = (m.n_w // 2, m.n_t // 3), False
    app.update_cursor(); pump(0.1)
    fg, bg = app.txt.get_color(), app.txt.get_bbox_patch().get_facecolor()
    check("unpinned read-out: light text on the dark card (luminance difference > 0.5)",
          abs(lum(fg) - lum(bg)) > 0.5, f"text {mcolors.to_hex(fg)} on {mcolors.to_hex(bg)}")
    app.pinned = True
    app.update_cursor(); pump(0.1)
    check("pinned read-out is still the highlight colour and readable",
          mcolors.to_hex(app.txt.get_color()) == mcolors.to_hex(NEW.PIN) and abs(lum(app.txt.get_color()) - lum(bg)) > 0.25)
    top.destroy()

# ---------------------------------------------------------------------------------------------
if section("B-16"):
    # axis labels and titles keep the theme colours after a redraw
    top, app = make_app(SAMPLE_A)
    app.redraw(full=True); app.redraw(full=True); pump(0.1)
    bad = []
    for name in ("ax_hist", "ax_map", "ax_ss", "ax_spec"):
        ax = getattr(app, name)
        for what, art, want in (("xlabel", ax.xaxis.label, NEW.INK_FAINT), ("ylabel", ax.yaxis.label, NEW.INK_FAINT),
                                ("title", ax.title, NEW.INK_DIM), ("left title", ax._left_title, NEW.INK_DIM)):
            if art.get_text() and mcolors.to_hex(art.get_color()) != mcolors.to_hex(want):
                bad.append(f"{name} {what} {art.get_text()!r} is {mcolors.to_hex(art.get_color())}")
    check("every axis label and title of the main figure has its theme colour", not bad, "; ".join(bad[:4]))
    top.destroy()

# ---------------------------------------------------------------------------------------------
if section("B-14"):
    # the map's own time labels no longer run into the Decay panel (the two share the time axis)
    top, app = make_app(SAMPLE_A)
    pump(0.2)
    r = app.canvas.get_renderer()
    hist_box = app.ax_hist.get_window_extent(r)
    spill = []
    for lab in list(app.ax_map.yaxis.get_ticklabels()) + [app.ax_map.yaxis.label]:
        if lab.get_visible() and lab.get_text():
            bb = lab.get_window_extent(r)
            if bb.x0 < hist_box.x1 - 1:
                spill.append(lab.get_text())
    check("no time label of the map lies inside the Decay panel", not spill, str(spill[:5]))
    check("the Decay panel still shows the time axis they share",
          app.ax_hist.yaxis.label.get_text() == "Time (ps)"
          and any(t.get_visible() and t.get_text() for t in app.ax_hist.yaxis.get_ticklabels()))
    top.destroy()

# ---------------------------------------------------------------------------------------------
if section("B-15"):
    # the grey backdrop of the Spectrum panel fits the panel
    top, app = make_app(SAMPLE_A)
    pump(0.1)
    top_y = app.ax_spec.get_ylim()[1]
    polys = [c for c in app.ax_spec.collections if c.get_paths()]
    peak = max(float(c.get_paths()[0].vertices[:, 1].max()) for c in polys) if polys else 0.0
    wide = [c for c in polys if (c.get_paths()[0].vertices[:, 1] > top_y).mean() > 0.2]
    check("the backdrop (band shape of all delays) stays inside the panel",
          polys and peak <= top_y * 1.0001 and not wide, f"peak {peak:.4g}, panel top {top_y:.4g}")
    top.destroy()

# ---------------------------------------------------------------------------------------------
if section("B-2"):
    # every control of the main window is visible at the minimum size and at the default size
    for size in ("980x660+0+0", "1280x800+0+0", "1440x920+0+0"):
        top, app = make_app(SAMPLE_A, size=size)
        pump(0.4)
        cut = squeezed(top)
        check(f"main window at {size.split('+')[0]}: no button, tick box or entry is cut off", not cut, "; ".join(cut[:4]))
        top.destroy()
    top, app = make_app(None, size="980x660+0+0")
    pump(0.3)
    cut = squeezed(top)
    check("... also before a file is loaded", not cut, "; ".join(cut[:4]))
    top.destroy()

# ---------------------------------------------------------------------------------------------
if section("B-12"):
    # the BIN choices are the real bin widths of the loaded file
    top, app = make_app(SAMPLE_A)
    res = app.model.phu["res_ps"]
    box = [w for w in widgets(top) if isinstance(w, ttk.Combobox) and str(w.cget("textvariable")) == str(app.var_bin)][0]
    check("4 ps file: the choices are 4, 8, 16 ... ps as before and 16 ps is selected",
          abs(res - 4.0) < 1e-9 and list(box.cget("values"))[:3] == ["4 ps", "8 ps", "16 ps"]
          and app.var_bin.get() == "16 ps" and abs(app.model.dt_ps - 16.0) < 1e-9, f"{box.cget('values')} {app.var_bin.get()}")
    eight = make_phu(os.path.join(TMP, "eight.phu"), ncurves=6, nbins=1024, res=8e-12)
    app.load(eight); pump(0.3)
    vals = list(box.cget("values"))
    check("8 ps file: the choices are 8, 16, 32 ... ps",
          vals[:3] == ["8 ps", "16 ps", "32 ps"], str(vals))
    check("... and what is selected is what the map has",
          app.var_bin.get() == f"{app.model.dt_ps:g} ps", f"{app.var_bin.get()} vs dt {app.model.dt_ps}")
    app.var_bin.set(vals[2]); app.apply_params(); pump(0.2)
    check("... choosing '32 ps' gives 32 ps bins", abs(app.model.dt_ps - 32.0) < 1e-9 and "bin 32 ps" in app._export_note(),
          f"{app.model.dt_ps} {app._export_note()}")
    app.load(SAMPLE_A); pump(0.3)
    check("back on the 4 ps file the choices are the 4 ps ones again",
          list(box.cget("values"))[0] == "4 ps" and app.var_bin.get() == f"{app.model.dt_ps:g} ps", str(box.cget("values")))
    top.destroy()

# ---------------------------------------------------------------------------------------------
if section("C-12"):
    # the Crop and Mask windows keep their buttons at small sizes
    top, app = make_app(SAMPLE_A)
    app.open_crop(); app.open_mask(); pump(0.4)
    c, mk = app._crop_win, app._mask_win
    for label, win, size in (("Crop at its default size", c.win, None), ("Crop 1000x800", c.win, "1000x800"),
                             ("Crop 1000x760", c.win, "1000x760"),
                             ("Crop at its minimum size", c.win, "%dx%d" % c.win.minsize()),
                             ("Mask at its default size", mk.win, None),
                             ("Mask at its minimum size", mk.win, "%dx%d" % mk.win.minsize())):
        if size:
            win.geometry(size)
        pump(0.4)
        cut = squeezed(win)
        check(f"{label}: every button, tick box and entry is fully shown", not cut, "; ".join(cut[:4]))
    c.win.geometry("1000x920"); pump(0.3)
    info = [w for w in widgets(c.win) if isinstance(w, ttk.Label) and str(w.cget("textvariable")) == str(c.var_info)][0]
    check("Crop at its default size: the info line (what Apply would keep) has the room it asks for",
          info.winfo_width() >= info.winfo_reqwidth() - 1, f"{info.winfo_width()} of {info.winfo_reqwidth()}")
    top.destroy()

# ---------------------------------------------------------------------------------------------
if section("C-21"):
    # message boxes belong to the window they are about, and Global shows that it is busy
    top, app = make_app(SAMPLE_A)
    seen = []
    kinds = ("showerror", "showwarning", "showinfo", "askyesno")
    stubs = {kind: getattr(NEW.messagebox, kind) for kind in kinds}     # the harness's, put back below
    for kind in kinds:
        setattr(NEW.messagebox, kind,
                lambda title="", msg="", _k=kind, **kw: (seen.append((_k, title, kw.get("parent"))), True)[1])
    app.open_kinetics(); app.open_global_analysis(); app.open_mask(); app.open_crop(); pump(0.4)
    k, g, mk, c = app._kinetics_win, app._global_win, app._mask_win, app._crop_win
    k.export_results()                           # "No fit"
    k.var_fw.set("x"); k.run_fit()               # "Invalid input"
    g.export_results()
    g.var_fw.set("x"); g.run_fit()
    mk.var_lo.set("a"); mk._add()
    wl = c._full.wls
    c.var_wl_lo.set(f"{float(wl[10]) + 1.5:g}"); c.var_wl_hi.set(f"{float(wl[10]) + 2.5:g}"); c._apply()
    pump(0.2)
    owners = {"k": k.win, "g": g.win, "mk": mk.win, "c": c.win}
    want = [k.win, k.win, g.win, g.win, mk.win, c.win]
    got = [s[2] for s in seen]
    check("each window's own message boxes have that window as parent",
          len(seen) == 6 and all(a is b for a, b in zip(got, want)),
          str([(s[0], s[1], None if s[2] is None else str(s[2])) for s in seen]))
    seen.clear()
    app.var_out_csv.set(False); app.var_out_opju.set(False)
    app.export_data()
    app.model, keep = None, app.model
    app.open_kinetics(); app.save_map_image()
    app.model = keep
    check("the main window's boxes have the main window as parent",
          len(seen) == 3 and all(s[2] is app.win for s in seen), str([(s[0], s[1], str(s[2])) for s in seen]))
    g.var_fw.set(f"{app.model.irf_fwhm_ps:g}")
    gate = {"hold": True}
    real_fit = NEW.fit_global_analysis

    def slow(D, t, **kw):
        import time
        while gate["hold"] and not kw["stop_check"]():
            time.sleep(0.02)
        return real_fit(D, t, **kw)
    NEW.fit_global_analysis = slow
    try:
        g.run_fit(); pump(0.3)
        busy = str(g.win.cget("cursor"))
        gate["hold"] = False
        wait(lambda: not g._running, 60); pump(0.2)
    finally:
        gate["hold"] = False
        NEW.fit_global_analysis = real_fit
    check("Global shows a busy cursor while it fits and gives it back afterwards",
          busy == "watch" and str(g.win.cget("cursor")) == "", f"{busy!r} -> {g.win.cget('cursor')!r}")
    for kind, stub in stubs.items():
        setattr(NEW.messagebox, kind, stub)
    top.destroy()

# ---------------------------------------------------------------------------------------------
if section("C-26"):
    # a time bin thinner than a screen pixel is still visible on the Crop map
    top, app = make_app(SAMPLE_A)
    app.var_bin.set("4 ps"); app.apply_params(); pump(0.2)       # 6,256 time bins on a few hundred pixels
    app.open_crop(); pump(0.4)
    c = app._crop_win
    f = c._full

    def picture(row):
        data = np.ones_like(f.E.T)             # a count in every cell, as measured data has
        if row is not None:
            data[row, :] = c._vmax0
        c._base_im.set_data(c._transform(data))
        c.canvas.draw(); pump(0.05)
        return np.asarray(c.canvas.buffer_rgba()).copy()
    empty = picture(None)
    missing = []
    for row in (1001, 2222, 3333, 4444, 5001, 6000):
        lit = int((picture(row) != empty).any(axis=2).sum())
        if lit < 50:
            missing.append((row, lit))
    check("six single bright time bins (each far thinner than a pixel) all leave a visible line",
          not missing, f"not drawn: {missing}")
    top.destroy()

# ---------------------------------------------------------------------------------------------
if section("D-14"):
    # the window opens no larger than the screen
    size = getattr(NEW, "initial_window_size", None)
    check("the start-up size is a function of the screen size", callable(size))
    if callable(size):
        for screen, want in (((3440, 1440), (1440, 920)), ((1920, 1080), (1440, 920)), ((1536, 864), None),
                             ((1366, 768), None), ((1280, 720), None)):
            w, h = size(*screen)
            fits = w <= screen[0] - 40 and h <= screen[1] - 100
            check(f"screen {screen[0]}x{screen[1]}: {w}x{h} fits with room for the task bar"
                  + ("" if want is None else " and is the usual 1440x920"),
                  fits and (want is None or (w, h) == want) and w >= 600 and h >= 400, f"{w}x{h}")

# ---------------------------------------------------------------------------------------------
if section("D-15"):
    # a path on the command line that cannot be opened is reported in a box, and a .ptu goes to the FLIM tab
    import sys
    argv = sys.argv
    made = []
    real_tk = NEW.tk.Tk

    class Root(real_tk):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            made.append(self)

        def mainloop(self, n=0):
            self.update()
    NEW.tk.Tk = Root
    log = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "TCSPC_analysis_freeze.log")
    try:
        sys.argv = ["prog", os.path.join(TMP, "moved_away.phu")]
        boxes.clear()
        try:
            NEW.main()
            code = "returned"
        except SystemExit as exc:
            code = exc.code
        check("a path that does not exist: an error box names it, then the program ends with exit code 1",
              code == 1 and [b[0] for b in boxes] == ["showerror"] and "moved_away.phu" in boxes[0][2], f"{code} {boxes}")
        for r in made:
            try:
                r.destroy()
            except tk.TclError:
                pass
        made.clear()
        ptu = os.path.join(TMP, "scan.ptu")
        open(ptu, "wb").write(b"PQTTTR\x00\x00" + b"\x00" * 64)
        sys.argv = ["prog", ptu]
        boxes.clear()
        flims = []
        real_flim = NEW.FLIMViewer
        NEW.FLIMViewer = lambda parent: (flims.append(real_flim(parent)), flims[-1])[1]
        try:
            NEW.main()
        finally:
            NEW.FLIMViewer = real_flim
        r = made[-1]
        nb = [w for w in widgets(r) if isinstance(w, ttk.Notebook)][0]
        # (the FLIM tab's path variable is read directly: with the test's own Tk root also alive, an
        #  entry of this second root does not show a variable made without a master)
        held = flims[-1].path_var.get() if flims else ""
        check("a .ptu path: no PHU error box, the FLIM tab is selected and holds the path",
              not boxes and nb.index(nb.select()) == 1 and os.path.normcase(held) == os.path.normcase(ptu),
              f"{boxes} tab={nb.index(nb.select())} held={held!r}")
        r.destroy()
        made.clear()
    finally:
        NEW.tk.Tk = real_tk
        sys.argv = argv
        if os.path.exists(log):
            os.remove(log)

# ---------------------------------------------------------------------------------------------
if section("D-28"):
    # the window shows which version it is, and has the program's icon
    import sys
    argv = sys.argv
    made, icons = [], []
    real_tk = NEW.tk.Tk

    class Root(real_tk):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            made.append(self)

        def mainloop(self, n=0):
            self.update()

        def iconbitmap(self, *a, **k):
            icons.append(k.get("default") or (a[0] if a else None))
            return super().iconbitmap(*a, **k)
    NEW.tk.Tk = Root
    log = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "TCSPC_analysis_freeze.log")
    try:
        sys.argv = ["prog"]
        NEW.main()
        r = made[-1]
        title = r.title()
        check("the window title carries the version", NEW.APP_VERSION in title and "PicoHarp 300" in title, title)
        check("the window was given the program's icon file",
              len(icons) == 1 and icons[0] and os.path.exists(icons[0]) and icons[0].lower().endswith(".ico"), str(icons))
        r.destroy()
    finally:
        NEW.tk.Tk = real_tk
        sys.argv = argv
        if os.path.exists(log):
            os.remove(log)

# ---------------------------------------------------------------------------------------------
if section("C-22"):
    # one wording for one thing: none of the variants the glossary retires is left on screen
    import ast
    import io
    import re
    retired_exact = ["No data", "Nothing to save", "Nothing to export", "TIME SPAN", "WINDOW", "SCALE", "Scale", "Setup",
                     "Stretched-IRF", "τ = ∞ offset", "Include τ = ∞", "Fit", "Run Fit", "intensity", "amplitude",
                     "wavelength (nm)", "delay (ps)", "Centre λ (nm)", "Kinetics λ (nm)", "± hw", "Masked regions (NaN)",
                     "Fit window (delay, ps)", "Fit t-range (ps)", "(uses main CSV / .opju)"]
    retired_part = ["Tick CSV and/or", "uses main CSV", "objective evals", " iters)", "avg of", " px)", "lambda   "]
    found, hangul = [], []
    for path in NEW.sources():
        name = os.path.basename(path)
        if name == "flim.py":                   # the FLIM tab is outside this stage
            continue
        tree = ast.parse(io.open(path, encoding="utf-8").read())
        doc_end = tree.body[0].end_lineno if (tree.body and isinstance(tree.body[0], ast.Expr)) else 0
        # what goes into exported files (CSV preamble, column names) keeps its wording
        export = [(f.lineno, f.end_lineno) for f in ast.walk(tree)
                  if isinstance(f, ast.FunctionDef) and f.name in ("_param_summary", "export_results")]
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.lineno > doc_end:
                if any(lo <= node.lineno <= hi for lo, hi in export):
                    continue
                v = node.value
                if v in retired_exact or any(p in v for p in retired_part):
                    found.append(f"{name}:{node.lineno} {v!r}")
                if re.search("[\\u1100-\\u11ff\\u3130-\\u318f\\uac00-\\ud7af]", v):
                    hangul.append(f"{name}:{node.lineno} {v!r}")
    check("no retired wording is left in the program's texts", not found, "; ".join(found[:6]))
    check("no Korean text is left on screen (all UI text is English)", not hangul, "; ".join(hangul[:3]))
    top, app = make_app(SAMPLE_A)
    app.open_crop(); app.open_mask(); app.open_kinetics(); app.open_global_analysis(); pump(0.4)

    def texts(win):
        out = []
        for w in widgets(win):
            try:
                t = str(w.cget("text"))
            except tk.TclError:
                continue
            if t:
                out.append(t)
        return out
    main, crop, mask = texts(top), texts(app._crop_win.win), texts(app._mask_win.win)
    kin, glob = texts(app._kinetics_win.win), texts(app._global_win.win)
    want = [("main window", main, ["TIME END", "BG WINDOW", "Apply offset"]),
            ("Crop", crop, ["SOLVENT SCALE", "Fit view", "Log time"]),
            ("Mask", mask, ["Masked regions"]),
            ("Kinetics", kin, ["Fit setup", "λ (nm)", "± half-width (nm)", "Include τ = ∞ offset", "Stretched-IRF mode",
                               "Fit range (ps)", "Time scale", "Run fit", "(formats chosen in the main window)"]),
            ("Global", glob, ["Fit setup", "λ (nm)", "Include τ = ∞ offset", "Stretched-IRF mode", "Fit range (ps)",
                              "Time scale", "Run fit"])]
    for name, have, need in want:
        lack = [n for n in need if n not in have]
        check(f"{name}: the glossary's wording is what the widgets show", not lack, f"missing {lack}")
    k = app._kinetics_win
    k.run_fit(); wait(lambda: not k._running, 60); pump(0.3)
    labels = (k.ax_main.get_ylabel(), k.ax_res.get_ylabel(), k.ax_res.get_xlabel())
    check("Kinetics plot labels: Intensity / Residual / Time (ps)", labels == ("Intensity", "Residual", "Time (ps)"), str(labels))
    check("Kinetics report counts iterations and curves", "iterations)" in k.txt.get("1.0", "end")
          and "curves)" in k.txt.get("1.0", "end"), k.txt.get("1.0", "2.end"))
    app.model, keep = None, app.model
    boxes.clear()
    app.open_crop(); app.save_map_image(); app.export_data()
    app.model = keep
    check("with no file every box has the same title", [b[1] for b in boxes] == ["No file loaded"] * 3, str(boxes))
    # what is written into files keeps its words (exports are compared byte for byte with 1.4)
    summary = "\n".join(k._param_summary(k._last))
    check("the CSV preamble of a fit export is worded as before", " iters, IRF " in summary and "lambda = " in summary, summary[:120])
    top.destroy()

finish()
