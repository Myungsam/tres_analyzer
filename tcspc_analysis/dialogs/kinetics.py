"""The Kinetics window (single-wavelength fit)."""
import os
import queue
import threading
import warnings

import numpy as np

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

import tkinter as tk
from tkinter import messagebox, ttk

from ..origin import _origin_fill_table
from ..fitting import FitStopped, fit_single_trace
from ..theme import ACCENT, INK, INK_DIM, LINE, PANEL, PIN, px
from .common import (ComponentTable, _FitDialog, _dark_toolbar, _style_analysis_ax, in_range, ink_legend,
                     read_number, set_time_scale, write_fit_csv)


class KineticsDialog(_FitDialog):
    """Fit the decay at one wavelength to a sum of IRF-convolved exponentials."""

    def __init__(self, app):
        super().__init__(app, "Kinetics fit - single wavelength",
                         "1180x760", (900, 560))
        self._last = None                   # last fit_single_trace result dict
        self._q = queue.Queue()             # worker -> main-thread messages
        self._running = False
        self._job = 0                       # bumped when a running fit goes stale
        self._stop = threading.Event()      # tells the worker to give up
        self._seen_t0 = self.model.t0       # the time origin the boxes are quoted in
        self._build()
        self._refresh_plot(replot_data=True, draw=False)
        self._draw_when_sized(self.canvas)
        self.win.after(100, self._poll_queue)

    def _on_close(self):
        self._stop.set()                    # a fit must not outlive its window
        super()._on_close()

    # -- layout ----------------------------------------------------------
    def _build(self):
        outer = ttk.Frame(self.win, padding=8)
        outer.pack(fill="both", expand=True)

        left = ttk.Labelframe(outer, text="Fit setup", padding=8)
        left.pack(side="left", fill="y")
        left.configure(width=px(self.win, 430))
        left.pack_propagate(False)

        # wavelength + averaging window
        wl_row = ttk.Frame(left); wl_row.pack(fill="x")
        ttk.Label(wl_row, text="λ (nm)").pack(side="left")
        self.var_wl = tk.StringVar(value=f"{self._cursor_wl():.2f}")
        e_wl = ttk.Entry(wl_row, textvariable=self.var_wl, width=9,
                         font=("TkFixedFont", 9))
        e_wl.pack(side="left", padx=(4, 8))
        ttk.Label(wl_row, text="± half-width (nm)").pack(side="left")
        self.var_hw = tk.StringVar(value="0")
        e_hw = ttk.Entry(wl_row, textvariable=self.var_hw, width=6,
                         font=("TkFixedFont", 9))
        e_hw.pack(side="left", padx=(4, 8))
        # editing λ / half-width must redraw the trace (Enter or focus-out) -
        # without this the data points stay on the old wavelength
        for e in (e_wl, e_hw):
            e.bind("<Return>", self._on_wl_change)
            e.bind("<FocusOut>", self._on_wl_change)
        # remembers the last (λ, hw) actually drawn, so a focus-out that did
        # not change anything does not needlessly drop a good fit
        self._wl_key = (self.var_wl.get().strip(), self.var_hw.get().strip())
        ttk.Button(wl_row, text="Use cursor λ",
                   command=self._use_cursor).pack(side="left")

        # component count + inf offset
        self._components_row(left, default=2, most=4, pady=(8, 4))

        self.table = ComponentTable(left)
        self.table.pack(fill="x", pady=(2, 6))
        self.table.set_n(2)

        # IRF group
        irf = self._irf_box(left)
        mode_row = ttk.Frame(irf); mode_row.pack(fill="x", pady=(2, 0))
        ttk.Label(mode_row, text="Stretched-IRF mode").pack(side="left")
        self.var_irf_mode = tk.StringVar(value="numerical")
        ttk.Combobox(mode_row, textvariable=self.var_irf_mode,
                     values=["numerical", "skip"], width=11,
                     state="readonly").pack(side="left", padx=(6, 0))

        # fit window
        win_row = ttk.Labelframe(left, text="Fit range (ps)", padding=6)
        win_row.pack(fill="x", pady=(2, 6))
        self._range_entries(win_row)

        # scale + run
        run_row = ttk.Frame(left); run_row.pack(fill="x", pady=(2, 6))
        ttk.Label(run_row, text="Time scale").pack(side="left")
        self.var_scale = tk.StringVar(value="Log")
        sc = ttk.Combobox(run_row, textvariable=self.var_scale,
                          values=["Log", "Linear"], width=8, state="readonly")
        sc.pack(side="left", padx=(4, 10))
        sc.bind("<<ComboboxSelected>>", lambda e: self._refresh_plot())
        self._run_buttons(run_row)
        self._export_row(left, "(formats chosen in the main window)")
        self._report_box(left, height=12, width=48,
                         hint="Set up the fit on the left, then Run fit.")

        # right: plots
        right = ttk.Labelframe(outer, text="Trace, fit, residual", padding=6)
        right.pack(side="left", fill="both", expand=True, padx=(8, 0))
        self.fig = Figure(figsize=(7, 6), dpi=100, facecolor=PANEL)
        self.ax_main = self.fig.add_subplot(2, 1, 1)
        self.ax_res = self.fig.add_subplot(2, 1, 2, sharex=self.ax_main)
        self.fig.subplots_adjust(left=0.12, right=0.97, top=0.95, bottom=0.1,
                                 hspace=0.18)
        self.canvas = FigureCanvasTkAgg(self.fig, master=right)
        tb = _dark_toolbar(self.canvas, right)
        tb.pack(fill="x")
        self.canvas.get_tk_widget().pack(fill="both", expand=True)

    def model_changed(self):
        """The data behind the window changed. When the time axis was
        renumbered ("t0 at IRF peak"), t₀ and the fit range are moved along so
        that they keep meaning the same delays; then the window shows the
        data as it is now."""
        self._follow_t0()
        if self._last is None:
            self._refresh_plot(replot_data=True)

    def _on_wl_change(self, *_):
        """Redraw the trace when the centre λ / half-width is edited.

        Skips when nothing actually changed (a bare focus-out), so it will not
        throw away a fit for no reason. When λ does move, the previous fit
        belonged to the old wavelength, so it is dropped and only the new trace
        is shown until the user runs the fit again.
        """
        key = (self.var_wl.get().strip(), self.var_hw.get().strip())
        if key == self._wl_key:
            return
        self._wl_key = key
        self._job += 1                      # a fit still running is for the old λ
        if self._last is not None:
            self._last = None
            self.var_status.set("λ changed - run the fit again.")
        self._refresh_plot(replot_data=True)

    def _use_cursor(self):
        self.var_wl.set(f"{self._cursor_wl():.2f}")
        self._on_wl_change()

    def _get_trace(self):
        """(t, y, wl_actual, n_avg) - the decay to fit/plot at the chosen wl."""
        m = self.model
        try:
            wl = float(self.var_wl.get())
        except ValueError:
            wl = self._cursor_wl()
        try:
            hw = float(self.var_hw.get())
        except ValueError:
            hw = 0.0
        t = m.times.copy()
        if hw <= 0:
            wi = int(np.argmin(np.abs(m.wls - wl)))
            return t, m.E[wi, :].copy(), float(m.wls[wi]), 1
        sel = (m.wls >= wl - hw) & (m.wls <= wl + hw)
        if not sel.any():
            wi = int(np.argmin(np.abs(m.wls - wl)))
            return t, m.E[wi, :].copy(), float(m.wls[wi]), 1
        # nanmean: masked wavelengths inside the averaging window drop out
        # instead of turning the whole averaged decay into NaN.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            y = np.nanmean(m.E[sel, :], axis=0)
        return t, y, float(m.wls[sel].mean()), int(sel.sum())

    # -- run / reset -----------------------------------------------------
    def reset(self):
        self.var_n.set("2"); self.table.set_n(2)
        self.var_inf.set(False)
        self._reset_irf()
        self.var_irf_mode.set("numerical")
        self._t_full()
        self._last = None
        self._job += 1
        self._stop.set()                    # a running fit was set up before the reset
        self.var_status.set("Reset to defaults.")
        self.txt.delete("1.0", "end")
        self._refresh_plot(replot_data=True)

    # The fit runs on a worker thread, like the global one: a slow fit (a wide
    # window, a stretched component) must not leave the whole program "not
    # responding". The worker only computes; every widget is touched from
    # _poll_queue on the main thread.
    def run_fit(self):
        if self._running:
            return
        # every box is read here, and one that cannot be used is named: no
        # stand-in value is fitted with instead
        try:
            tau, fix, st, beta, bfix = self.table.read_checked()
            read_number(self.var_wl, "λ")
            if read_number(self.var_hw, "The half-width") < 0:
                raise ValueError("The half-width must not be negative.")
            t_lo = read_number(self.var_tmin, "The start of the fit range")
            t_hi = read_number(self.var_tmax, "The end of the fit range")
            t0 = read_number(self.var_t0, "t₀")
            fw = read_number(self.var_fw, "The IRF FWHM")
        except ValueError as exc:
            messagebox.showwarning("Invalid input", str(exc), parent=self.win)
            return
        if tau.size == 0:
            messagebox.showwarning("No components", "Add at least one component.", parent=self.win)
            return
        t_full, y_full, wl_actual, n_avg = self._get_trace()
        if t_lo > t_hi:
            t_lo, t_hi = t_hi, t_lo
        sel = in_range(t_full, t_lo, t_hi)
        n_in = int(sel.sum())
        n_min = int(tau.size) + (1 if self.var_inf.get() else 0) + 1
        if n_in < n_min:
            messagebox.showwarning(
                "Window too narrow", f"Need >= {n_min} delay points; got {n_in}.", parent=self.win)
            return

        params = dict(
            tau_init=tau, tau_fixed=fix, beta_init=beta, beta_fixed=bfix,
            stretch_on=st, t0_init=t0, t0_fixed=self.var_t0_fix.get(),
            fwhm_init=fw, fwhm_fixed=self.var_fw_fix.get(),
            has_inf=self.var_inf.get(), irf_mode=self.var_irf_mode.get())
        # everything the result is shown with, as it is now: the boxes may be
        # edited while the fit runs
        extra = {"_t_fit": t_full[sel], "_y_fit": y_full[sel],
                 "_t_full": t_full, "_y_full": y_full,
                 "_wl": wl_actual, "_n_avg": n_avg,
                 "_stretch": st, "_has_inf": self.var_inf.get(),
                 "_t0_fixed": self.var_t0_fix.get(), "_fwhm_fixed": self.var_fw_fix.get()}
        extra.update(self._fit_record(t_lo, t_hi, n_in, self._fixed_names(
            fix, st, bfix, self.var_t0_fix.get(), self.var_fw_fix.get())))
        report = (wl_actual, n_avg, t_lo, t_hi, n_in)
        # the fit runs on the boxes as they are now; remember them so a later
        # bare focus-out on the λ entry does not discard it
        self._wl_key = (self.var_wl.get().strip(), self.var_hw.get().strip())
        self._job += 1

        # each run gets its own stop flag: one that was told to stop (Reset,
        # then Run again) must stay stopped
        self._stop = stop = threading.Event()
        # started first: if that fails, the window is not left "running"
        threading.Thread(target=self._worker,
                         args=(t_full[sel], y_full[sel], params, extra, report,
                               self._job, stop),
                         daemon=True).start()
        self._started()

    def _worker(self, t, y, params, extra, report, job, stop):
        try:
            res = fit_single_trace(t, y, stop_check=stop.is_set, **params)
            res.update(extra)
            self._q.put(("done", (res, report, job)))
        except FitStopped:
            self._q.put(("stopped", job))
        except Exception as exc:               # noqa: BLE001 - surfaced to UI
            self._q.put(("error", (exc, extra["_wl"], job)))

    def _handle(self, kind, payload):
        """One message of the worker (see _FitDialog._poll_queue)."""
        self._finish_run()          # first: whatever follows, the buttons are back
        if kind == "done":
            self._on_done(*payload)
        elif kind == "stopped":
            # stopped by Reset or by a new λ: the status already says so
            if payload == self._job:
                self.var_status.set("Stopped by user.")
        else:
            exc, wl, job = payload
            self.var_status.set("Fit failed.")
            # a result still shown for another wavelength no longer
            # goes with the boxes: show the trace that was asked for
            if (self._last is not None and job == self._job
                    and abs(self._last["_wl"] - wl) > 1e-9):
                self._last = None
                self.txt.delete("1.0", "end")
                self._refresh_plot(replot_data=True)
            messagebox.showerror(
                "Fit error", f"Fit failed:\n{self._worker_failed(exc)}", parent=self.win)

    def _on_done(self, res, report, job):
        if job != self._job:        # λ was changed or Reset pressed meanwhile
            self.var_status.set("Fit dropped - the setup changed while it ran.")
            return
        self._last = res
        self._report(res, *report)
        n_warn = len(res["info"]["warnings"])
        self.var_status.set(f"Fit done - RMS = {res['info']['rms']:.3g}"
                            + ("" if res["info"]["success"] else "  (not converged)")
                            + (f"  ({n_warn} warning{'s' if n_warn > 1 else ''}, "
                               f"see the report)" if n_warn else ""))
        if self._is_stale(res):             # the data changed while it ran
            self._said_stale = res
            self.var_status.set(self.STALE)
        self._refresh_plot()

    def _report(self, res, wl, n_avg, t_lo, t_hi, n_in):
        info = res["info"]
        head = (f"Fit converged ({info['iters']} iterations), " if info["success"]
                else f"NOT converged ({info['iters']} iterations: {info['message']}), ")
        L = [head + f"RMS = {info['rms']:.4g}",
             f"λ = {wl:.2f} nm  (average of {n_avg} curves)",
             f"Window: [{t_lo:.4g}, {t_hi:.4g}] ps, n = {n_in}",
             f"IRF mode: {res['info']['irf_mode']}", "",
             "  i   τ (ps)        β       A          (type)"]
        st = res["_stretch"]
        for i in range(len(res["tau"])):
            tag = "stretched" if st[i] else "exp"
            L.append(f"  {i+1}   {res['tau'][i]:10.4g}  {res['beta'][i]:6.3g}  "
                     f"{res['A'][i]:10.4g}  ({tag})")
        if res["_has_inf"]:
            L.append(f"  ∞   {'':10}  {'':6}  {res['A'][-1]:10.4g}  (offset)")
        L += ["", f"t₀ = {res['t0']:.4g} ps"
              + ("  (fixed)" if res["_t0_fixed"] else ""),
              f"FWHM = {res['fwhm']:.4g} ps"
              + ("  (fixed)" if res["_fwhm_fixed"] else "")]
        if info["warnings"]:
            L += [""] + [f"Warning: {w}" for w in info["warnings"]]
        self.txt.delete("1.0", "end")
        self.txt.insert("1.0", "\n".join(L))

    # -- plotting --------------------------------------------------------
    def _refresh_plot(self, replot_data=False, draw=True):
        ax, axR = self.ax_main, self.ax_res
        # drop back to linear before clearing so clear() never autoscales a
        # log axis (which would warn about the non-positive default limits)
        ax.set_xscale("linear"); axR.set_xscale("linear")
        ax.clear(); axR.clear()
        _style_analysis_ax(ax); _style_analysis_ax(axR)

        if replot_data or self._last is None:
            t, y, wl, n_avg = self._get_trace()
        else:
            t = self._last["_t_full"]; y = self._last["_y_full"]
            wl = self._last["_wl"]; n_avg = self._last["_n_avg"]

        ax.plot(t, y, ".", color=INK_DIM, markersize=3, label="data")
        if self._last is not None:
            ax.plot(self._last["_t_fit"], self._last["fit"], "-",
                    color=ACCENT, linewidth=1.4, label="fit")
            axR.plot(self._last["_t_fit"], self._last["residual"], ".",
                     color=PIN, markersize=2)
        ax.axhline(0, color=LINE, linestyle=":", linewidth=0.6)
        axR.axhline(0, color=LINE, linestyle=":", linewidth=0.6)
        set_time_scale((ax, axR), t, self.var_scale.get() == "Log")
        ax.set_ylabel("Intensity"); axR.set_ylabel("Residual")
        axR.set_xlabel("Time (ps)")
        ax.set_title(f"λ = {wl:.2f} nm   (average of {n_avg} curves)")
        ink_legend(ax.legend(loc="best", fontsize=8, facecolor=PANEL, edgecolor=LINE), INK)
        ax.grid(True, color=LINE, alpha=0.4); axR.grid(True, color=LINE, alpha=0.4)
        if draw:
            self.canvas.draw_idle()

    # -- export ----------------------------------------------------------
    def _param_summary(self, r):
        """Multi-line fit summary for the CSV preamble / opju column comment."""
        lines = [f"lambda = {r['_wl']:.2f} nm (avg {r['_n_avg']} px)",
                 f"RMS = {r['info']['rms']:.6g}, {r['info']['iters']} iters, "
                 f"IRF {r['info']['irf_mode']}",
                 f"t0 = {r['t0']:.6g} ps, FWHM = {r['fwhm']:.6g} ps"]
        st = r["_stretch"]
        for i in range(len(r["tau"])):
            tag = "stretched" if st[i] else "exp"
            lines.append(f"comp {i+1}: tau = {r['tau'][i]:.6g} ps, "
                         f"beta = {r['beta'][i]:.4g}, A = {r['A'][i]:.6g} ({tag})")
        if r["_has_inf"]:
            lines.append(f"offset: A_inf = {r['A'][-1]:.6g}")
        return lines

    def export_results(self):
        """Write the trace + fit + residual, honouring the main CSV/.opju ticks.

        One dataset ({stem}_kinetics): delay / data / fit / residual, with the
        fit parameters in the CSV preamble and the opju column comment.
        """
        if self._last is None:
            messagebox.showwarning("No fit", "Run the fit first.", parent=self.win)
            return
        r = self._last
        phu_base = os.path.splitext(os.path.basename(self.model.phu["path"]))[0]
        default_base = phu_base            # suffix "kinetics" completes the name
        t = np.asarray(r["_t_fit"]); y = np.asarray(r["_y_fit"])
        fit = np.asarray(r["fit"]); resid = np.asarray(r["residual"])
        preamble = self._param_summary(r)
        taus = "; ".join(f"tau{i+1}={r['tau'][i]:.4g}ps" for i in range(len(r["tau"])))
        comment = f"{r['_wl']:.2f} nm; {taus}; RMS={r['info']['rms']:.4g}"

        def write_csv(path):
            write_fit_csv(path, "kinetics fit (single wavelength)", self.model.phu["path"],
                          preamble, r, "delay_ps,data,fit,residual",
                          np.column_stack([t, y, fit, resid]))

        def fill_ws(ws):
            _origin_fill_table(ws, [t, y, fit, resid], [
                ("Delay", "ps", comment),
                ("Data", "a. u.", f"{r['_wl']:.2f} nm"),
                ("Fit", "a. u.", ""),
                ("Residual", "a. u.", "")])

        self.app.export_analysis(default_base, [
            {"suffix": "kinetics", "csv": write_csv, "fill": fill_ws}], owner=self.win)
