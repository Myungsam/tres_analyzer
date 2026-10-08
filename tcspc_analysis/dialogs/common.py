"""What the pop-up windows share."""
import gc
import queue

import numpy as np

from matplotlib.backends.backend_tkagg import NavigationToolbar2Tk

import tkinter as tk
from tkinter import ttk

from ..fitting import FitInputError
from ..theme import ACCENT, BG, INK, INK_DIM, INK_FAINT, LINE, PANEL, px, scaled_geometry


def read_number(var, name):
    """The finite number in an entry box, or ValueError naming the box."""
    text = var.get().strip()
    try:
        value = float(text)
    except ValueError:
        raise ValueError(f"{name} is not a number: {text!r}.") from None
    if not np.isfinite(value):
        raise ValueError(f"{name} must be a finite number (it is {text}).")
    return value


def fmt_ps(value):
    """A time for an entry box, with every digit it needs to read back as the
    same delay (four digits wrote 21,824 ps as 2.182e+04)."""
    return f"{value:.10g}"


def in_range(t, lo, hi):
    """Which of the delays ``t`` lie in [lo, hi]. The two ends count as inside
    up to a millionth of a time bin, so a range typed (or filled in) as the
    first and last delay keeps both: -3184.000000000001 is shown as -3184."""
    t = np.asarray(t, float)
    tol = 1e-6 * float(np.median(np.diff(t))) if t.size > 1 else 0.0
    return (t >= lo - tol) & (t <= hi + tol)


# ==========================================================================
# 6. Analysis dialogs - Kinetics + Global analysis, each its own window
# ==========================================================================
def _style_analysis_ax(ax):
    """Paint a matplotlib axis in the shared palette (re-run after clear)."""
    ax.set_facecolor(BG)
    for s in ax.spines.values():
        s.set_color(LINE)
    ax.tick_params(colors=INK_FAINT, labelsize=8, length=3)
    ax.xaxis.label.set_color(INK_DIM)
    ax.yaxis.label.set_color(INK_DIM)
    ax.title.set_color(INK_DIM)


def _dark_toolbar(canvas, master):
    """A matplotlib navigation toolbar tinted to match the theme."""
    tb = NavigationToolbar2Tk(canvas, master, pack_toolbar=False)
    tb.configure(bg=PANEL)
    for child in tb.winfo_children():
        try:
            child.configure(bg=PANEL)
        except tk.TclError:
            pass
    tb.update()
    return tb


class ComponentTable(ttk.Frame):
    """Editable per-component grid: tau_init / fix / stretched / beta / beta-fix.

    set_n() rebuilds the rows for a new component count, preserving whatever the
    user already typed so changing the count is never destructive. read() hands
    back the five parallel numpy arrays the fit kernels expect.
    """

    HEADERS = ["#", "τ_init (ps)", "fix", "stretch", "β_init", "β fix"]
    _TAU_DEFAULTS = [100.0, 1000.0, 10000.0, 100000.0, 1_000_000.0]

    def __init__(self, master):
        super().__init__(master)
        for c, h in enumerate(self.HEADERS):
            ttk.Label(self, text=h).grid(row=0, column=c, padx=2, pady=(0, 3),
                                         sticky="w")
        self.rows = []

    def set_n(self, n):
        prev = self.read_raw()
        for r in self.rows:
            for w in r["widgets"]:
                w.destroy()
        self.rows = []
        for i in range(n):
            tau_v = tk.StringVar(
                value=prev[i]["tau"] if i < len(prev)
                else f"{self._TAU_DEFAULTS[i % 5]:g}")
            fix_v = tk.BooleanVar(
                value=prev[i]["tau_fixed"] if i < len(prev) else False)
            st_v = tk.BooleanVar(
                value=prev[i]["stretched"] if i < len(prev) else False)
            beta_v = tk.StringVar(value=prev[i]["beta"] if i < len(prev) else "1")
            bfix_v = tk.BooleanVar(
                value=prev[i]["beta_fixed"] if i < len(prev) else False)
            w0 = ttk.Label(self, text=str(i + 1))
            w1 = ttk.Entry(self, textvariable=tau_v, width=11,
                           font=("TkFixedFont", 9))
            w2 = ttk.Checkbutton(self, variable=fix_v)
            w3 = ttk.Checkbutton(self, variable=st_v)
            w4 = ttk.Entry(self, textvariable=beta_v, width=6,
                           font=("TkFixedFont", 9))
            w5 = ttk.Checkbutton(self, variable=bfix_v)
            rr = i + 1
            w0.grid(row=rr, column=0, padx=2, sticky="w")
            w1.grid(row=rr, column=1, padx=2, pady=1)
            w2.grid(row=rr, column=2)
            w3.grid(row=rr, column=3)
            w4.grid(row=rr, column=4, padx=2)
            w5.grid(row=rr, column=5)
            self.rows.append({"tau": tau_v, "fix": fix_v, "st": st_v,
                              "beta": beta_v, "bfix": bfix_v,
                              "widgets": [w0, w1, w2, w3, w4, w5]})

    def read_raw(self):
        return [{"tau": r["tau"].get(), "tau_fixed": r["fix"].get(),
                 "stretched": r["st"].get(), "beta": r["beta"].get(),
                 "beta_fixed": r["bfix"].get()} for r in self.rows]

    def read_checked(self):
        """read(), but an entry that cannot be used raises ValueError naming
        it instead of being replaced by a stand-in value: a lifetime must be a
        number above 0, and the exponent of a stretched component a number
        above 0 and at most 2."""
        for i, r in enumerate(self.rows):
            tau = read_number(r["tau"], f"τ of component {i + 1}")
            if tau <= 0:
                raise ValueError(f"τ of component {i + 1} must be above 0 ps "
                                 f"(it is {tau:g}).")
            if r["st"].get():
                beta = read_number(r["beta"], f"β of component {i + 1}")
                if not 0 < beta <= 2:
                    raise ValueError(f"β of component {i + 1} must be above 0 "
                                     f"and at most 2 (it is {beta:g}).")
        return self.read()

    def read(self):
        tau, fix, st, beta, bfix = [], [], [], [], []
        for r in self.rows:
            try:
                tau.append(float(r["tau"].get()))
            except ValueError:
                tau.append(1.0)
            fix.append(bool(r["fix"].get()))
            st.append(bool(r["st"].get()))
            try:
                b = float(r["beta"].get())
            except ValueError:
                b = 1.0
            beta.append(min(max(b, 1e-3), 2.0))
            bfix.append(bool(r["bfix"].get()))
        return (np.asarray(tau, float), np.asarray(fix, bool),
                np.asarray(st, bool), np.asarray(beta, float),
                np.asarray(bfix, bool))


class _AnalysisDialog:
    """Common plumbing for the pop-up preprocessing and analysis windows.

    Wraps a themed Toplevel, tracks whether it is still open (so the launcher can
    raise an existing one instead of stacking duplicates), and exposes the live
    viewer/model so the window always works on the file currently loaded.
    """

    def __init__(self, app, title, geometry, minsize):
        self.app = app
        self.win = tk.Toplevel(app.win)
        self.win.title(title)
        # the sizes are given for a display at 100 %
        self.win.geometry(scaled_geometry(self.win, geometry))
        # ... and neither may ask for more than the screen has
        room = (self.win.winfo_screenwidth() - px(self.win, 40),
                self.win.winfo_screenheight() - px(self.win, 100))
        self.win.minsize(*(min(px(self.win, v), r) for v, r in zip(minsize, room)))
        self.win.configure(bg=BG)
        self.alive = True
        self.win.protocol("WM_DELETE_WINDOW", self._on_close)

    @property
    def model(self):
        return self.app.model

    def _on_close(self):
        if not self.alive:                  # closed already
            return
        self.alive = False
        self._cancel_timers()
        self.win.destroy()
        self._release_tk()

    def _release_tk(self):
        """Let go of what this window holds in Tk now, on the main thread.

        Its Tk variables, and the matplotlib canvas and toolbar with their Tk
        images, sit in reference cycles (window <-> its callbacks) until the
        garbage collector runs - on whichever thread triggers it, a fit worker
        included - and they unset / delete themselves in Tk when finalised,
        which only the main thread may do. Plain state (the last result, the
        flags) stays, and so does ``win``.
        """
        def of_tk(value):
            if isinstance(value, (list, tuple)):
                return any(of_tk(v) for v in value)
            return (isinstance(value, (tk.Variable, tk.Image))
                    or (isinstance(value, tk.Misc) and value is not self.win)
                    or type(value).__module__.startswith("matplotlib"))

        for name in [n for n, v in vars(self).items() if of_tk(v)]:
            setattr(self, name, None)
        gc.collect()        # the cycles just cut loose, finalised here

    def _draw_when_sized(self, canvas):
        """The first picture of a new window. Its figure is made at a made-up
        size and takes the real one when the window appears - and that resize
        draws it. Asking for a draw here as well meant drawing every new fit
        window twice, the first time at the wrong size. So nothing is asked
        for; only if no draw came after a moment (a window that never got a
        size) is it drawn as it is."""
        drawn = []
        cid = canvas.mpl_connect("draw_event", lambda event: drawn.append(1))

        def or_else():
            canvas.mpl_disconnect(cid)
            if self.alive and not drawn:
                canvas.draw_idle()
        self.win.after(250, or_else)

    def _cancel_timers(self):
        """Cancel every after() still pending for this window or a widget in
        it (the queue polling, a debounced update, matplotlib's idle draw).
        destroy() deletes their commands but leaves the timers, which would
        then fire into nothing - a Tcl background error each."""
        mine, todo = set(), [self.win]
        while todo:
            w = todo.pop()
            mine.update(w._tclCommands or ())
            todo.extend(w.winfo_children())
        tcl = self.win.tk
        for ident in tcl.splitlist(tcl.call("after", "info")):
            try:
                script = tcl.splitlist(tcl.call("after", "info", ident))[0]
            except tk.TclError:             # fired meanwhile
                continue
            if script in mine:
                tcl.call("after", "cancel", ident)

    def model_changed(self):
        """The viewer calls this after the model was rebuilt from the main
        window; a window that keeps a copy or a picture of it brings that up
        to date."""

    def lift_and_refresh(self):
        self.win.deiconify()
        self.win.lift()
        self.win.focus_force()
        self.model_changed()        # another window may have changed the model


class _FitDialog(_AnalysisDialog):
    """What the Kinetics and the Global-analysis window have in common: the
    pieces of the set-up panel, the worker thread's queue, the run / stop
    state, what is kept with a result, and the CSV of a result.

    A subclass sets ``_q`` (the queue), ``_running``, ``_stop``, ``_job`` and
    ``_last`` in its __init__, builds its panel from the ``_..._row`` /
    ``_..._box`` pieces below, and gives ``_handle(kind, payload)`` for what
    its worker puts on the queue.
    """

    POLL_MS = 100           # how often the queue of the worker is looked at

    # -- pieces of the set-up panel ----------------------------------------
    def _components_row(self, parent, default, most, **pack):
        """Number of components + the tau = inf tick. The table is the caller's."""
        n_row = ttk.Frame(parent); n_row.pack(fill="x", **pack)
        ttk.Label(n_row, text="Components").pack(side="left")
        self.var_n = tk.StringVar(value=str(default))
        cb = ttk.Combobox(n_row, textvariable=self.var_n,
                          values=[str(k) for k in range(1, most + 1)], width=4, state="readonly")
        cb.pack(side="left", padx=(4, 10))
        cb.bind("<<ComboboxSelected>>", lambda e: self.table.set_n(int(self.var_n.get())))
        self.var_inf = tk.BooleanVar(value=False)
        ttk.Checkbutton(n_row, text="Include τ = ∞ offset",
                        variable=self.var_inf).pack(side="left")

    def _irf_row(self, parent, label, var, fix_var):
        row = ttk.Frame(parent); row.pack(fill="x", pady=1)
        ttk.Label(row, text=label, width=10).pack(side="left")
        ttk.Entry(row, textvariable=var, width=10,
                  font=("TkFixedFont", 9)).pack(side="left", padx=(4, 8))
        ttk.Checkbutton(row, text="fixed", variable=fix_var).pack(side="left")

    def _irf_box(self, parent):
        """The "IRF (Gaussian)" group: t0 and FWHM, each with its "fixed" tick."""
        t0d, fwd = self._irf_defaults()
        irf = ttk.Labelframe(parent, text="IRF (Gaussian)", padding=6)
        irf.pack(fill="x", pady=(2, 6))
        self.var_t0 = tk.StringVar(value=fmt_ps(t0d))
        self.var_t0_fix = tk.BooleanVar(value=True)
        self.var_fw = tk.StringVar(value=f"{fwd:.4g}")
        self.var_fw_fix = tk.BooleanVar(value=True)
        self._irf_row(irf, "t₀ (ps)", self.var_t0, self.var_t0_fix)
        self._irf_row(irf, "FWHM (ps)", self.var_fw, self.var_fw_fix)
        return irf

    def _reset_irf(self):
        t0d, fwd = self._irf_defaults()
        self.var_t0.set(fmt_ps(t0d)); self.var_t0_fix.set(True)
        self.var_fw.set(f"{fwd:.4g}"); self.var_fw_fix.set(True)

    def _range_entries(self, parent):
        """From / To / Full of the fit range, packed into ``parent``. -> the two entries"""
        m = self.model
        self.var_tmin = tk.StringVar(value=fmt_ps(m.times[0]))
        self.var_tmax = tk.StringVar(value=fmt_ps(m.times[-1]))
        ttk.Label(parent, text="From").pack(side="left")
        e0 = ttk.Entry(parent, textvariable=self.var_tmin, width=9, font=("TkFixedFont", 9))
        e0.pack(side="left", padx=(4, 8))
        ttk.Label(parent, text="To").pack(side="left")
        e1 = ttk.Entry(parent, textvariable=self.var_tmax, width=9, font=("TkFixedFont", 9))
        e1.pack(side="left", padx=(4, 8))
        ttk.Button(parent, text="Full", command=self._t_full).pack(side="left")
        return e0, e1

    def _t_full(self):
        m = self.model
        self.var_tmin.set(fmt_ps(m.times[0]))
        self.var_tmax.set(fmt_ps(m.times[-1]))

    def _run_buttons(self, parent):
        self.btn_run = ttk.Button(parent, text="Run fit", command=self.run_fit)
        self.btn_run.pack(side="left")
        self.btn_stop = ttk.Button(parent, text="Stop", command=self.stop_fit,
                                   state="disabled")
        self.btn_stop.pack(side="left", padx=(6, 0))
        ttk.Button(parent, text="Reset", command=self.reset).pack(side="left", padx=(6, 0))

    def _export_row(self, parent, hint):
        row = ttk.Frame(parent); row.pack(fill="x")
        ttk.Label(row, text="Export").pack(side="left")
        ttk.Button(row, text="Export results",
                   command=self.export_results).pack(side="left", padx=(6, 0))
        ttk.Label(row, text=hint, style="Val.TLabel",
                  foreground=INK_FAINT).pack(side="left", padx=(6, 0))

    def _report_box(self, parent, height, width, hint):
        """The status line and the text box the result is written into."""
        self.var_status = tk.StringVar(value="Ready.")
        ttk.Label(parent, textvariable=self.var_status, style="Val.TLabel",
                  foreground=ACCENT).pack(anchor="w", pady=(6, 2))
        self.txt = tk.Text(parent, height=height, width=width, bg=BG, fg=INK,
                           insertbackground=INK, relief="flat",
                           font=("TkFixedFont", 9), wrap="none")
        self.txt.pack(fill="both", expand=True)
        self.txt.insert("1.0", hint)

    # -- a run ---------------------------------------------------------------
    def _started(self):
        """The worker thread is running: Run off, Stop on, busy cursor."""
        self._running = True
        self._stop_asked = False
        self.btn_run.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.win.configure(cursor="watch")
        self.var_status.set("Fitting...")

    def _finish_run(self, status=None):
        """The run is over, however it ended: the buttons and the cursor back."""
        self._running = False
        self.btn_run.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        self.win.configure(cursor="")
        if status is not None:
            self.var_status.set(status)

    def stop_fit(self):
        if self._running:
            self._stop.set()
            self._stop_asked = True         # the status now reads "Stopping..."
            self.btn_stop.configure(state="disabled")
            self.var_status.set("Stopping...")

    def _poll_queue(self):
        """Take what the worker thread put on the queue; every widget is
        touched from here, on the main thread."""
        try:
            while True:
                kind, payload = self._q.get_nowait()
                self._handle(kind, payload)
        except queue.Empty:
            pass
        finally:                # an error above must not end the polling
            if self.alive:
                self._watch_model()
                self.win.after(self.POLL_MS, self._poll_queue)

    def _worker_failed(self, exc):
        """The message-box text for a fit whose worker raised ``exc``.

        A FitInputError is the kernel refusing its input and carries a
        sentence for the user. Anything else - numpy's own ValueError and
        LinAlgError included - is a fault in the program: it is named, and its
        traceback goes where a failing callback's does - the freeze log, the
        console when there is one.
        """
        if isinstance(exc, FitInputError):
            return str(exc)
        self.win._root().report_callback_exception(type(exc), exc, exc.__traceback__)
        return f"{type(exc).__name__}: {exc}"

    # -- what a fit was made on ------------------------------------------
    STALE = ("The data in the main window changed after this fit was started "
             "- run it again.")

    def _fit_record(self, t_lo, t_hi, n_in, fixed):
        """What a fit window keeps with a result so that an export can say what
        was fitted: the fit range, what was held fixed, and the main window's
        settings line - all as they are now, when the fit starts."""
        return {"_note": self.app._export_note(), "_rev": self.model.rev,
                "_setup": f"fit range = {fmt_ps(t_lo)} to {fmt_ps(t_hi)} ps "
                          f"({n_in} points); fixed: {', '.join(fixed) or 'nothing'}"}

    @staticmethod
    def _fixed_names(tau_fixed, stretch_on, beta_fixed, t0_fixed, fwhm_fixed):
        names = [f"tau {i + 1}" for i, f in enumerate(tau_fixed) if f]
        names += [f"beta {i + 1}" for i, f in enumerate(beta_fixed) if f and stretch_on[i]]
        return names + (["t0"] if t0_fixed else []) + (["FWHM"] if fwhm_fixed else [])

    def _is_stale(self, res):
        return res is not None and res.get("_rev") != self.model.rev

    def _watch_model(self):
        """From the fit windows' polling: say once, in the status line, that
        the result on show is of data the main window no longer has (BIN, the
        background, a crop, a mask, the solvent or OFFSET changed)."""
        res = getattr(self, "_last", None)
        if not self._is_stale(res):
            self._said_stale = None
        elif getattr(self, "_said_stale", None) is not res and not self._running:
            self._said_stale = res
            self.var_status.set(self.STALE)

    def _follow_t0(self):
        """Fit windows: shift t₀ and the fit range by a change of the model's
        time origin since the window last looked."""
        t0 = self.model.t0
        shift = getattr(self, "_seen_t0", t0) - t0
        self._seen_t0 = t0
        if not shift:
            return
        for var in (self.var_t0, self.var_tmin, self.var_tmax):
            try:
                var.set(fmt_ps(float(var.get()) + shift))
            except ValueError:
                pass

    # -- defaults pulled from the current model --------------------------
    def _irf_defaults(self):
        """(t0, fwhm) guesses in display-time coordinates from the IRF curve."""
        m = self.model
        t0 = float(m.irf_peak_ps - m.t0) if m.irf is not None else 0.0
        fwhm = float(m.irf_fwhm_ps) if (m.irf is not None
                                        and m.irf_fwhm_ps > 0) else 0.0
        if fwhm <= 0:                       # no usable IRF - use a small guess
            span = float(m.times[-1] - m.times[0]) if m.n_t > 1 else 1.0
            fwhm = max(span / 200.0, m.dt_ps)
        return t0, fwhm

    def _cursor_wl(self):
        """The wavelength under the map cursor, or the middle of the axis."""
        m = self.model
        if self.app.cursor is not None:
            return float(m.wls[self.app.cursor[0]])
        return float(m.wls[m.n_w // 2])


def write_fit_csv(path, title, source, preamble, result, header, table):
    """The CSV of a fit result: what it is, the file it came from, the
    parameters, what was fitted (as it was when the fit was started), then
    the table."""
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(f"# {title}\n")
        fh.write(f"# source: {source}\n")
        for line in preamble:
            fh.write(f"# {line}\n")
        fh.write(f"# {result['_setup']}\n")
        fh.write(f"# {result['_note']}\n")
        fh.write(header + "\n")
        np.savetxt(fh, table, delimiter=",", fmt="%.8g")


def ink_legend(legend, color):
    """Give a legend's texts (and title) the theme's colour."""
    if legend is not None:
        for text in (*legend.get_texts(), legend.get_title()):
            text.set_color(color)


def set_time_scale(axes, t, log):
    """A log or linear time axis over the delays ``t`` for each of ``axes``
    (log needs a positive delay; without one the axis stays linear)."""
    if log and np.any(t > 0):
        lo = t[t > 0].min()
        for ax in axes:
            ax.set_xscale("log"); ax.set_xlim(lo, t.max())
    else:
        for ax in axes:
            ax.set_xscale("linear"); ax.set_xlim(t.min(), t.max())
