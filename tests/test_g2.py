"""Stage 3, group G2: nothing hangs or waits for ever (review items A-6, A-14, A-5 stop, C-2, C-17, C-18,
C-19, B-10, B-9). One section per item; see _harness.py."""
import os
import struct
import threading
import time

from _harness import *                        # noqa: F401,F403
from _harness import SAMPLE_B, NEW, SAMPLE_A, TMP, boxes, cb_errors, check, finish, make_app, make_phu, np, pump, section, wait
import _versions
# These checks compare with an older version: the rules 1.6 changed on purpose are put back
# (see _versions.rules_of_1_5; the changes themselves are tested in test_g7.py / test_g8.py).
_versions.rules_of_1_5(NEW)


def read_in_thread(path, limit=10.0):
    """read_phu on a worker thread: ('ok', dict) / ('error', text) / ('hangs', None) after ``limit`` s."""
    box = {}

    def work():
        try:
            box["r"] = ("ok", NEW.read_phu(path))
        except Exception as exc:                # noqa: BLE001
            box["r"] = ("error", f"{type(exc).__name__}: {exc}")
    th = threading.Thread(target=work, daemon=True)
    th.start()
    th.join(limit)
    return box.get("r", ("hangs", None))


# ---------------------------------------------------------------------------------------------
if section("A-6"):
    good = make_phu(os.path.join(TMP, "good.phu"))
    kind, phu = read_in_thread(good)
    check("the synthetic file itself reads", kind == "ok" and phu["counts"].shape == (3, 64) and phu["nbins"] == 64,
          str(kind))
    for label, kw in [
        ("a negative string length", {"patch": {("File_Comment", "length"): -48}}),
        ("a string length beyond the end of the file", {"patch": {("File_Comment", "length"): 10 ** 9}}),
    ]:
        p = make_phu(os.path.join(TMP, "bad.phu"), **kw)
        kind, val = read_in_thread(p, 8.0)
        check(f"{label}: read_phu ends with a ValueError that says the header is corrupt",
              kind == "error" and val.startswith("ValueError") and "orrupt" in val, f"{kind} {str(val)[:120]}")
    p = make_phu(os.path.join(TMP, "noend.phu"), header_end=False)
    kind, val = read_in_thread(p, 8.0)
    check("a header without Header_End is refused",
          kind == "error" and val.startswith("ValueError") and "Header_End" in val, f"{kind} {str(val)[:120]}")
    for real in (SAMPLE_A, SAMPLE_B):
        kind, val = read_in_thread(real, 30.0)
        check(f"{os.path.basename(real)} still reads", kind == "ok" and val["counts"].ndim == 2, str(kind))

# ---------------------------------------------------------------------------------------------
if section("A-14"):
    cases = [
        ("header cut off in the middle", dict(cut=300), "orrupt"),
        ("one curve more than there are descriptors", dict(ncurves=3, n_descr=2), "DataOffset"),
        ("a negative bin count", dict(patch={("HistResDscr_HistogramBins", 0): (NEW.TY_INT8, -5)}), "bin"),
        ("zero bins", dict(patch={("HistResDscr_HistogramBins", 0): (NEW.TY_INT8, 0)}), "bin"),
        ("curve count stored as a float", dict(patch={("HistoResult_NumberOfCurves", -1): (NEW.TY_FLOAT8, 3.0)}), "curve"),
        ("a negative data offset", dict(patch={("HistResDscr_DataOffset", 1): (NEW.TY_INT8, -64)}), "outside"),
        ("resolution 0", dict(patch={("HistResDscr_MDescResolution", 0): (NEW.TY_FLOAT8, 0.0)}), "resolution"),
        ("resolution NaN", dict(patch={("HistResDscr_MDescResolution", 0): (NEW.TY_FLOAT8, float("nan"))}), "resolution"),
        ("curve 2 with another bin count", dict(patch={("HistResDscr_HistogramBins", 2): (NEW.TY_INT8, 32)}), "bins"),
        ("curve 1 with another resolution", dict(patch={("HistResDscr_MDescResolution", 1): (NEW.TY_FLOAT8, 8e-12)}), "resolution"),
    ]
    for label, kw, word in cases:
        p = make_phu(os.path.join(TMP, "hdr.phu"), **kw)
        kind, val = read_in_thread(p, 8.0)
        check(f"{label}: a ValueError in words (mentions '{word}')",
              kind == "error" and val.startswith("ValueError") and word in val and len(val) > 25,
              f"{kind} {str(val)[:140]}")
    from _harness import OLD
    for real in (SAMPLE_A, SAMPLE_B):
        new, old = NEW.read_phu(real), OLD.read_phu(real)
        # (the per-curve "integrals" 1.4 also returned were read by nothing and are gone since A-21)
        check(f"{os.path.basename(real)}: every field read as 1.4 read it",
              set(old) - set(new) == {"integrals"} and set(new) <= set(old)
              and all(np.array_equal(new[k], old[k]) if isinstance(new[k], np.ndarray) else new[k] == old[k]
                      for k in new), str(set(old) ^ set(new)))
    # through the window: a readable error box, the loaded file stays
    top, app = make_app(SAMPLE_A)
    before = app.model
    p = make_phu(os.path.join(TMP, "hdr.phu"), patch={("HistResDscr_HistogramBins", 0): (NEW.TY_INT8, 0)})
    boxes.clear()
    app.load(p); pump(0.3)
    check("opening such a file: one error box with a sentence, the current file stays loaded",
          [b[0] for b in boxes] == ["showerror"] and len(boxes[0][2]) > 25 and app.model is before
          and os.path.basename(app.var_path.get()) == os.path.basename(SAMPLE_A), str(boxes))
    top.destroy()

# ---------------------------------------------------------------------------------------------
if section("A-5"):
    # the single-trace kernel can be told to stop
    from _harness import OLD
    phu = NEW.read_phu(SAMPLE_A)
    mdl = NEW.TRESModel(phu)
    mdl.rebuild()
    t_ax = mdl.times.copy()
    y_tr = mdl.E[int(np.argmin(np.abs(mdl.wls - 545.0)))].copy()
    kw = dict(tau_init=[100.0, 1000.0], tau_fixed=[False, False], t0_init=float(mdl.irf_peak_ps - mdl.t0),
              fwhm_init=float(mdl.irf_fwhm_ps), t0_fixed=True, fwhm_fixed=True, has_inf=False,
              irf_mode="numerical")
    calls = []

    def stop_after_five():
        calls.append(1)
        return len(calls) > 5
    try:
        NEW.fit_single_trace(t_ax, y_tr, stop_check=stop_after_five, **kw)
        got = "returned a result"
    except Exception as exc:                    # noqa: BLE001
        got = type(exc).__name__
    check("fit_single_trace(stop_check=...) stops with FitStopped as soon as it is told to",
          got == "FitStopped" and 6 <= len(calls) <= 8, f"{got} after {len(calls)} checks")
    check("the global fit's stop is the same kind of exception",
          hasattr(NEW, "FitStopped") and issubclass(NEW.GlobalAnalysisStopped, NEW.FitStopped))
    a = NEW.fit_single_trace(t_ax, y_tr, stop_check=lambda: False, **kw)
    b = OLD.fit_single_trace(t_ax, y_tr, **kw)
    check("with a stop_check that never fires the result is 1.4's, bit for bit",
          np.array_equal(a["tau"], b["tau"]) and np.array_equal(a["A"], b["A"]) and np.array_equal(a["fit"], b["fit"]))

# ---------------------------------------------------------------------------------------------
if section("C-2"):
    # a stretched Kinetics fit that does not finish can be ended: Stop, Reset, closing, a new file
    top, app = make_app(SAMPLE_A)
    alive = {"n": 0, "calls": 0}
    real_conv = NEW.stretched_irf_conv

    def counted(*a, **k):
        alive["calls"] += 1
        return real_conv(*a, **k)
    NEW.stretched_irf_conv = counted

    def open_stretched():
        app.open_kinetics(); pump(0.3)
        k = app._kinetics_win
        k.var_wl.set("545"); k._on_wl_change()
        k.table.rows[0]["st"].set(True)
        return k

    def quiet(seconds=3.0):
        """True when no kernel call happens any more."""
        pump(seconds)
        n = alive["calls"]
        pump(1.5)
        return alive["calls"] == n

    try:
        k = open_stretched()
        check("the Kinetics window has a Stop button, disabled while idle",
              hasattr(k, "btn_stop") and str(k.btn_stop.cget("state")) == "disabled")
        k.run_fit(); pump(4.0)
        check("the stretched fit is still running after 4 s (the case of the report)", k._running)
        check("... Stop is enabled while it runs", str(k.btn_stop.cget("state")) == "normal")
        t0 = time.time()
        k.stop_fit()
        ended = wait(lambda: not k._running, 30.0)
        check("Stop ends the fit, Run is enabled again and no result is shown",
              ended and str(k.btn_run.cget("state")) == "normal" and k._last is None
              and "Stopped" in k.var_status.get(), f"{ended} after {time.time() - t0:.1f} s, {k.var_status.get()}")
        check("... and the worker really stopped computing", quiet())
        # Reset while running
        k.run_fit(); pump(2.0)
        k.reset()
        ended = wait(lambda: not k._running, 30.0)
        check("Reset while running ends the fit and Run comes back",
              ended and str(k.btn_run.cget("state")) == "normal" and quiet(), str(ended))
        # closing the window
        k.table.rows[0]["st"].set(True)
        k.run_fit(); pump(2.0)
        k._on_close(); pump(0.2)
        check("closing the window ends its worker", quiet())
        # a new file
        k = open_stretched()
        k.run_fit(); pump(2.0)
        app.load(SAMPLE_B); pump(0.3)
        check("opening another file ends the old file's fit", app._kinetics_win is None and quiet())
        check("no error box from the fits that were cut off", not [b for b in boxes if b[0] == "showerror"], str(boxes))
        # and an ordinary fit still works, with Stop greyed out again afterwards
        app.open_kinetics(); pump(0.3)
        k = app._kinetics_win
        k.run_fit(); wait(lambda: not k._running, 60); pump(0.3)
        check("an ordinary fit still finishes and leaves Stop disabled",
              k._last is not None and str(k.btn_stop.cget("state")) == "disabled"
              and k.var_status.get().startswith("Fit done"), k.var_status.get())
        k._on_close(); pump(0.2)
    finally:
        NEW.stretched_irf_conv = real_conv
    top.destroy()

# ---------------------------------------------------------------------------------------------
if section("C-17"):
    # closing a window must not leave timers firing into destroyed widgets (Tcl background errors)
    from _harness import root
    bg = []
    root.tk.createcommand("bgerror", lambda *a: bg.append(" ".join(str(x) for x in a)))
    top, app = make_app(SAMPLE_A)
    app.open_crop(); app.open_mask(); app.open_kinetics(); app.open_global_analysis(); pump(0.4)
    c = app._crop_win
    c.var_t_hi.set("9000"); c._schedule()               # a debounce timer is pending
    c.canvas.draw_idle(); app._kinetics_win.canvas.draw_idle(); app._global_win.canvas.draw_idle()
    for w in (app._crop_win, app._mask_win, app._kinetics_win, app._global_win):
        w._on_close()
    pump(1.0)
    check("closing Crop (with a pending update), Mask, Kinetics and Global leaves no Tcl background error",
          not bg, str(bg[:4]))
    # the same when a new file closes them
    app.open_crop(); app.open_kinetics(); app.open_global_analysis(); pump(0.4)
    app._crop_win._schedule()
    app.load(SAMPLE_B); pump(1.0)
    check("... nor when opening another file closes them", not bg, str(bg[:4]))
    top.destroy(); pump(0.3)
    root.tk.deletecommand("bgerror")

# ---------------------------------------------------------------------------------------------
if section("C-18"):
    # an unexpected exception in a fit worker: its type in the message, its traceback in the log
    top, app = make_app(SAMPLE_A)
    for kind, opener, attr, kernel in (("Kinetics", app.open_kinetics, "_kinetics_win", "fit_single_trace"),
                                       ("Global", app.open_global_analysis, "_global_win", "fit_global_analysis")):
        opener(); pump(0.3)
        d = getattr(app, attr)
        real = getattr(NEW, kernel)

        def broken(*a, **k):
            return {}["fit"]                    # an internal KeyError, as in the review's probe
        setattr(NEW, kernel, broken)
        boxes.clear()
        n_cb = len(cb_errors)
        try:
            d.run_fit(); wait(lambda: not d._running, 30); pump(0.3)
        finally:
            setattr(NEW, kernel, real)
        msg = boxes[-1][2] if boxes else ""
        check(f"{kind}: the error box names the kind of error, not just \"'fit'\"",
              [b[0] for b in boxes] == ["showerror"] and "KeyError" in msg, msg)
        check(f"{kind}: the traceback goes to the callback-error handler (the freeze log), with the worker's frame",
              len(cb_errors) == n_cb + 1 and "KeyError" in cb_errors[-1] and "broken" in cb_errors[-1],
              cb_errors[-1][-200:] if len(cb_errors) > n_cb else "nothing reported")
        del cb_errors[n_cb:]
        # a refused input (ValueError) is a message only - not a program fault for the log
        d.var_fw.set("0")
        boxes.clear()
        d.run_fit(); wait(lambda: not d._running, 30); pump(0.3)
        check(f"{kind}: a refused input shows its sentence and is not logged as a fault",
              [b[0] for b in boxes] == ["showerror"] and "FWHM" in boxes[0][2] and "ValueError" not in boxes[0][2]
              and len(cb_errors) == n_cb, f"{boxes} {len(cb_errors) - n_cb}")
        # the worker cannot be started at all
        d.reset(); pump(0.1)
        real_thread = NEW.threading.Thread

        class NoThread(real_thread):
            def start(self):
                raise RuntimeError("can't start new thread")
        NEW.threading.Thread = NoThread
        boxes.clear()
        try:
            try:
                d.run_fit()
            except RuntimeError:
                pass
            pump(0.3)
        finally:
            NEW.threading.Thread = real_thread
        check(f"{kind}: if the worker thread cannot be started, Run is not left disabled",
              not d._running and str(d.btn_run.cget("state")) == "normal", f"{d._running} {d.btn_run.cget('state')}")
        del cb_errors[n_cb:]
        d._on_close(); pump(0.2)
    top.destroy()

# ---------------------------------------------------------------------------------------------
if section("C-19"):
    # the Tk variables of a closed window are let go on the main thread, not by a worker's garbage collection
    import gc
    import tkinter as tk
    main_id = threading.get_ident()
    wrong = []
    real_del = tk.Variable.__del__

    def watched_del(self):
        if threading.get_ident() != main_id:
            wrong.append(type(self).__name__)
        real_del(self)
    tk.Variable.__del__ = watched_del
    top, app = make_app(SAMPLE_A)
    try:
        for _ in range(3):
            app.open_crop(); app.open_mask(); app.open_kinetics(); app.open_global_analysis(); pump(0.3)
            k, g = app._kinetics_win, app._global_win
            k.run_fit(); g.run_fit(); pump(0.1)
            app._close_dialogs()                         # while both workers are busy
            del k, g
            th = threading.Thread(target=lambda: [gc.collect() for _ in range(3)])
            pump(1.5)
            th.start()
            while th.is_alive():
                pump(0.05)
            pump(0.5)
        check("no Tk variable of a closed window is finalised on another thread", not wrong,
              f"{len(wrong)}: {sorted(set(wrong))}")
    finally:
        tk.Variable.__del__ = real_del
    top.destroy()

# ---------------------------------------------------------------------------------------------
if section("B-10"):
    # Open reads the file off the main thread and shows that it is doing so
    from _harness import root
    top, app = make_app(SAMPLE_A)
    main_id = threading.get_ident()
    seen = {}
    real_read = NEW.read_phu

    def slow_read(path):
        seen["thread"] = threading.get_ident()
        time.sleep(1.5)                          # an online-only file being fetched
        return real_read(path)
    NEW.read_phu = slow_read
    ticks = []

    def tick():
        ticks.append(time.monotonic())
        root.after(50, tick)
    tick()
    try:
        check("the viewer has the non-blocking load the Open button uses", hasattr(app, "load_async"))
        t0 = time.monotonic()
        app.load_async(SAMPLE_B)
        took = time.monotonic() - t0
        pump(0.3)
        check("load_async returns at once while the file is read on another thread",
              took < 0.3 and seen.get("thread") not in (None, main_id), f"{took:.2f} s")
        check("while reading: a 'Reading <name> ...' text, busy cursor, Open disabled, old file still shown",
              "Reading" in app.var_meta.get() and os.path.basename(SAMPLE_B) in app.var_meta.get()
              and str(app.win.cget("cursor")) == "watch" and str(app.btn_open.cget("state")) == "disabled"
              and os.path.basename(app.var_path.get()) == os.path.basename(SAMPLE_A), app.var_meta.get())
        # mid-review M1: an export started now would still have its save dialog up when the model changes
        boxes.clear()
        asked = []
        real_ask_save = NEW.filedialog.asksaveasfilename
        NEW.filedialog.asksaveasfilename = lambda **kw: (asked.append(kw.get("title")), "")[1]
        try:
            app.export_data(); app.save_map_image()
            app.export_analysis("x", [{"suffix": "kinetics", "csv": lambda p: None, "fill": lambda ws: None}])
        finally:
            NEW.filedialog.asksaveasfilename = real_ask_save
        check("while reading: Export, Save image and a fit export open no save dialog and say why",
              not asked and len(boxes) == 3 and all(b[0] == "showinfo" and "being opened" in b[2] for b in boxes),
              f"{asked} {boxes}")
        boxes.clear()
        app.load_async(SAMPLE_A)                      # a second request while one is under way
        done = wait(lambda: os.path.basename(app.var_path.get()) == os.path.basename(SAMPLE_B), 20)
        t1 = time.monotonic()
        inside = [t for t in ticks if t0 <= t <= t1]
        gap = max((b - a for a, b in zip(inside, inside[1:])), default=9.0)
        check("the main loop keeps answering during the read (timer gaps < 0.5 s)",
              done and len(inside) >= 15 and gap < 0.5, f"{len(inside)} ticks, gap {gap:.2f} s")
        pump(0.5)
        check("afterwards: the new file is loaded, cursor and Open are back, the second request was ignored",
              app.model.phu["path"] == SAMPLE_B and str(app.win.cget("cursor")) == ""
              and str(app.btn_open.cget("state")) == "normal" and "Reading" not in app.var_meta.get()
              and os.path.basename(app.var_path.get()) == os.path.basename(SAMPLE_B), app.var_meta.get())
        # a file that cannot be read
        meta = app.var_meta.get()
        bad = os.path.join(TMP, "notphu.phu")
        open(bad, "wb").write(b"not a histogram file" * 10)
        boxes.clear()
        app.load_async(bad)
        wait(lambda: bool(boxes), 20); pump(0.3)
        check("a file that cannot be read: an error box, the loaded file and its info line stay",
              [b[0] for b in boxes] == ["showerror"] and app.model.phu["path"] == SAMPLE_B
              and app.var_meta.get() == meta and str(app.btn_open.cget("state")) == "normal"
              and str(app.win.cget("cursor")) == "", f"{boxes} {app.var_meta.get()}")
        # the Open button itself goes through it
        real_ask = NEW.filedialog.askopenfilename
        NEW.filedialog.askopenfilename = lambda **kw: SAMPLE_A
        try:
            t0 = time.monotonic()
            app.open_dialog()
            took = time.monotonic() - t0
        finally:
            NEW.filedialog.askopenfilename = real_ask
        ok = wait(lambda: app.model.phu["path"] == SAMPLE_A, 20)
        check("the Open button uses it (returns before the 1.5 s read is over)", ok and took < 0.5, f"{took:.2f} s")
    finally:
        NEW.read_phu = real_read
    # load() itself stays synchronous: what starts with a path on the command line, and the tests, rely on it
    app.load(SAMPLE_B)
    check("load(path) still returns with the file loaded", app.model.phu["path"] == SAMPLE_B)
    top.destroy()

# ---------------------------------------------------------------------------------------------
if section("B-9"):
    # an .opju export cannot be re-entered, and says that it is running
    top, app = make_app(SAMPLE_A)
    app.var_out_csv.set(False); app.var_out_opju.set(True)
    state = {"depth": 0, "max": 0, "during": None, "queued_ran_inside": False}
    opju = os.path.join(TMP, "out.opju")
    app._ask_opju_path = lambda stem: opju

    def fake_write(path, stem):
        state["depth"] += 1
        state["max"] = max(state["max"], state["depth"])
        state["during"] = (str(app.win.cget("cursor")), str(app.btn_export.cget("state")), app.var_meta.get())
        app.export_data()                        # a second click on Export while Origin is busy
        state["depth"] -= 1
        return ["a", "b"]
    app._write_opju = fake_write

    def queued():
        state["queued_ran_inside"] = state["depth"] > 0
    meta = app.var_meta.get()
    boxes.clear()
    app.win.after(0, queued)                     # e.g. a FocusOut that is waiting in the event queue
    app.export_data(); pump(0.3)
    check("a second Export while one is running is ignored (no nested export)", state["max"] == 1, str(state["max"]))
    check("a callback waiting in the queue does not run in the middle of the export", not state["queued_ran_inside"])
    check("while exporting: busy cursor, Export disabled, a text that says what is going on",
          state["during"] is not None and state["during"][0] == "watch" and state["during"][1] == "disabled"
          and "Origin" in state["during"][2], str(state["during"]))
    check("afterwards everything is back and the export reported once",
          str(app.win.cget("cursor")) == "" and str(app.btn_export.cget("state")) == "normal"
          and app.var_meta.get() == meta and [b[0] for b in boxes] == ["showinfo"], f"{boxes} {app.var_meta.get()}")
    # from an analysis window: that window shows the busy state too, and comes back after a failure
    app.open_kinetics(); pump(0.3)
    k = app._kinetics_win
    k.run_fit(); wait(lambda: not k._running, 60); pump(0.2)
    seen = {}

    def failing_tabs(path, tabs):
        seen["cursor"] = str(k.win.cget("cursor"))
        seen["nested"] = k.export_results()
        raise RuntimeError("planted: Origin could not be started")
    app._opju_write_tabs = failing_tabs
    boxes.clear()
    k.export_results(); pump(0.3)
    check("export from Kinetics: its own window shows the busy cursor", seen.get("cursor") == "watch", str(seen))
    check("... a failure is reported once and both windows are usable again",
          [b[0] for b in boxes] == ["showerror"] and str(k.win.cget("cursor")) == ""
          and str(app.win.cget("cursor")) == "" and str(app.btn_export.cget("state")) == "normal", str(boxes))
    k._on_close(); pump(0.2)
    # mid-review M2: the analysis window is closed while the .opju name is being asked
    app.open_kinetics(); pump(0.3)
    k = app._kinetics_win
    k.run_fit(); wait(lambda: not k._running, 60); pump(0.2)
    owner = k.win
    app._ask_opju_path = lambda stem: (k._on_close(), os.path.join(TMP, "gone.opju"))[1]
    app._opju_write_tabs = lambda path, tabs: ["t"]
    boxes.clear()
    try:
        k.export_results()
        err = ""
    except Exception as exc:                    # noqa: BLE001
        err = f"{type(exc).__name__}: {exc}"
    pump(0.3)
    check("the asking window closed meanwhile: the export still ends cleanly and Export is usable again",
          not err and not app._exporting and str(app.btn_export.cget("state")) == "normal"
          and str(app.win.cget("cursor")) == "", err or f"{app._exporting} {app.btn_export.cget('state')}")
    top.destroy()

finish()
