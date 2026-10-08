"""What the pop-up windows share."""
import gc

import numpy as np

from matplotlib.backends.backend_tkagg import NavigationToolbar2Tk

import tkinter as tk
from tkinter import ttk

from ..theme import BG, INK_DIM, INK_FAINT, LINE, PANEL


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


# ==========================================================================
# 6. Analysis dialogs - Kinetics + Global analysis, each its own window
# ==========================================================================
def _style_analysis_ax(ax):
    """Paint a matplotlib axis in the shared dark palette (re-run after clear)."""
    ax.set_facecolor(BG)
    for s in ax.spines.values():
        s.set_color(LINE)
    ax.tick_params(colors=INK_FAINT, labelsize=8, length=3)
    ax.xaxis.label.set_color(INK_DIM)
    ax.yaxis.label.set_color(INK_DIM)
    ax.title.set_color(INK_DIM)


def _dark_toolbar(canvas, master):
    """A matplotlib navigation toolbar tinted to match the dark theme."""
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

    Wraps a dark Toplevel, tracks whether it is still open (so the launcher can
    raise an existing one instead of stacking duplicates), and exposes the live
    viewer/model so the window always works on the file currently loaded.
    """

    def __init__(self, app, title, geometry, minsize):
        self.app = app
        self.win = tk.Toplevel(app.win)
        self.win.title(title)
        self.win.geometry(geometry)
        self.win.minsize(*minsize)
        self.win.configure(bg=BG)
        self.alive = True
        self.win.protocol("WM_DELETE_WINDOW", self._on_close)

    @property
    def model(self):
        return self.app.model

    def _on_close(self):
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

    def _worker_failed(self, exc):
        """The message-box text for a fit whose worker raised ``exc``.

        A ValueError / RuntimeError is the kernel refusing its input (or SciPy
        missing) and carries a sentence for the user. Anything else is a fault
        in the program: it is named, and its traceback goes where a failing
        callback's does - the freeze log, the console when there is one.
        """
        if isinstance(exc, (ValueError, RuntimeError)):
            return str(exc)
        self.win._root().report_callback_exception(type(exc), exc, exc.__traceback__)
        return f"{type(exc).__name__}: {exc}"

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

    def lift_and_refresh(self):
        self.win.deiconify()
        self.win.lift()
        self.win.focus_force()

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
