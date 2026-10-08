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
from ..theme import ACCENT, BG, INK, INK_DIM, INK_FAINT, LINE, PANEL, PIN
from .common import ComponentTable, _AnalysisDialog, _dark_toolbar, _style_analysis_ax, read_number


class KineticsDialog(_AnalysisDialog):
    """Fit the decay at one wavelength to a sum of IRF-convolved exponentials."""

    def __init__(self, app):
        super().__init__(app, "Kinetics fit - single wavelength",
                         "1180x760", (900, 560))
        self._last = None                   # last fit_single_trace result dict
        self._q = queue.Queue()             # worker -> main-thread messages
        self._running = False
        self._job = 0                       # bumped when a running fit goes stale
        self._stop = threading.Event()      # tells the worker to give up
        self._build()
        self._refresh_plot(replot_data=True)
        self.win.after(100, self._poll_queue)

    def _on_close(self):
        self._stop.set()                    # a fit must not outlive its window
        super()._on_close()

    # -- layout ----------------------------------------------------------
    def _build(self):
        m = self.model
        outer = ttk.Frame(self.win, padding=8)
        outer.pack(fill="both", expand=True)

        left = ttk.Labelframe(outer, text="Setup", padding=8)
        left.pack(side="left", fill="y")
        left.configure(width=430)
        left.pack_propagate(False)

        # wavelength + averaging window
        wl_row = ttk.Frame(left); wl_row.pack(fill="x")
        ttk.Label(wl_row, text="Centre λ (nm)").pack(side="left")
        self.var_wl = tk.StringVar(value=f"{self._cursor_wl():.2f}")
        e_wl = ttk.Entry(wl_row, textvariable=self.var_wl, width=9,
                         font=("TkFixedFont", 9))
        e_wl.pack(side="left", padx=(4, 8))
        ttk.Label(wl_row, text="± hw").pack(side="left")
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
        n_row = ttk.Frame(left); n_row.pack(fill="x", pady=(8, 4))
        ttk.Label(n_row, text="Components").pack(side="left")
        self.var_n = tk.StringVar(value="2")
        cb = ttk.Combobox(n_row, textvariable=self.var_n, values=["1", "2", "3", "4"],
                          width=4, state="readonly")
        cb.pack(side="left", padx=(4, 10))
        cb.bind("<<ComboboxSelected>>", lambda e: self.table.set_n(int(self.var_n.get())))
        self.var_inf = tk.BooleanVar(value=False)
        ttk.Checkbutton(n_row, text="τ = ∞ offset",
                        variable=self.var_inf).pack(side="left")

        self.table = ComponentTable(left)
        self.table.pack(fill="x", pady=(2, 6))
        self.table.set_n(2)

        # IRF group
        t0d, fwd = self._irf_defaults()
        irf = ttk.Labelframe(left, text="IRF (Gaussian)", padding=6)
        irf.pack(fill="x", pady=(2, 6))
        self.var_t0 = tk.StringVar(value=f"{t0d:.4g}")
        self.var_t0_fix = tk.BooleanVar(value=True)
        self.var_fw = tk.StringVar(value=f"{fwd:.4g}")
        self.var_fw_fix = tk.BooleanVar(value=True)
        self._irf_row(irf, "t₀ (ps)", self.var_t0, self.var_t0_fix)
        self._irf_row(irf, "FWHM (ps)", self.var_fw, self.var_fw_fix)
        mode_row = ttk.Frame(irf); mode_row.pack(fill="x", pady=(2, 0))
        ttk.Label(mode_row, text="Stretched-IRF mode").pack(side="left")
        self.var_irf_mode = tk.StringVar(value="numerical")
        ttk.Combobox(mode_row, textvariable=self.var_irf_mode,
                     values=["numerical", "skip"], width=11,
                     state="readonly").pack(side="left", padx=(6, 0))

        # fit window
        win_row = ttk.Labelframe(left, text="Fit window (delay, ps)", padding=6)
        win_row.pack(fill="x", pady=(2, 6))
        self.var_tmin = tk.StringVar(value=f"{m.times[0]:.4g}")
        self.var_tmax = tk.StringVar(value=f"{m.times[-1]:.4g}")
        ttk.Label(win_row, text="From").pack(side="left")
        ttk.Entry(win_row, textvariable=self.var_tmin, width=9,
                  font=("TkFixedFont", 9)).pack(side="left", padx=(4, 8))
        ttk.Label(win_row, text="To").pack(side="left")
        ttk.Entry(win_row, textvariable=self.var_tmax, width=9,
                  font=("TkFixedFont", 9)).pack(side="left", padx=(4, 8))
        ttk.Button(win_row, text="Full", command=self._t_full).pack(side="left")

        # scale + run
        run_row = ttk.Frame(left); run_row.pack(fill="x", pady=(2, 6))
        ttk.Label(run_row, text="Time scale").pack(side="left")
        self.var_scale = tk.StringVar(value="Log")
        sc = ttk.Combobox(run_row, textvariable=self.var_scale,
                          values=["Log", "Linear"], width=8, state="readonly")
        sc.pack(side="left", padx=(4, 10))
        sc.bind("<<ComboboxSelected>>", lambda e: self._refresh_plot())
        self.btn_run = ttk.Button(run_row, text="Run Fit", command=self.run_fit)
        self.btn_run.pack(side="left")
        self.btn_stop = ttk.Button(run_row, text="Stop", command=self.stop_fit,
                                   state="disabled")
        self.btn_stop.pack(side="left", padx=(6, 0))
        ttk.Button(run_row, text="Reset", command=self.reset).pack(side="left", padx=(6, 0))

        exp_row = ttk.Frame(left); exp_row.pack(fill="x")
        ttk.Label(exp_row, text="Export").pack(side="left")
        ttk.Button(exp_row, text="Export results",
                   command=self.export_results).pack(side="left", padx=(6, 0))
        ttk.Label(exp_row, text="(uses main CSV / .opju)",
                  style="Val.TLabel", foreground=INK_FAINT).pack(side="left", padx=(6, 0))

        self.var_status = tk.StringVar(value="Ready.")
        ttk.Label(left, textvariable=self.var_status, style="Val.TLabel",
                  foreground=ACCENT).pack(anchor="w", pady=(6, 2))
        self.txt = tk.Text(left, height=12, width=48, bg=BG, fg=INK,
                           insertbackground=INK, relief="flat",
                           font=("TkFixedFont", 9), wrap="none")
        self.txt.pack(fill="both", expand=True)
        self.txt.insert("1.0", "Set up the fit on the left, then Run Fit.")

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

    def _irf_row(self, parent, label, var, fix_var):
        row = ttk.Frame(parent); row.pack(fill="x", pady=1)
        ttk.Label(row, text=label, width=10).pack(side="left")
        ttk.Entry(row, textvariable=var, width=10,
                  font=("TkFixedFont", 9)).pack(side="left", padx=(4, 8))
        ttk.Checkbutton(row, text="fixed", variable=fix_var).pack(side="left")

    def model_changed(self):
        """The data behind the window changed: with no result on screen, show
        the trace as it is now (a result keeps showing what it was fitted to)."""
        if self._last is None:
            self._refresh_plot(replot_data=True)

    # -- helpers ---------------------------------------------------------
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

    def _t_full(self):
        m = self.model
        self.var_tmin.set(f"{m.times[0]:.4g}")
        self.var_tmax.set(f"{m.times[-1]:.4g}")

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
        t0d, fwd = self._irf_defaults()
        self.var_t0.set(f"{t0d:.4g}"); self.var_t0_fix.set(True)
        self.var_fw.set(f"{fwd:.4g}"); self.var_fw_fix.set(True)
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
            messagebox.showwarning("Invalid input", str(exc))
            return
        if tau.size == 0:
            messagebox.showwarning("No components", "Add at least one component.")
            return
        t_full, y_full, wl_actual, n_avg = self._get_trace()
        if t_lo > t_hi:
            t_lo, t_hi = t_hi, t_lo
        sel = (t_full >= t_lo) & (t_full <= t_hi)
        n_in = int(sel.sum())
        n_min = int(tau.size) + (1 if self.var_inf.get() else 0) + 1
        if n_in < n_min:
            messagebox.showwarning(
                "Window too narrow", f"Need >= {n_min} delay points; got {n_in}.")
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
        self._running = True
        self.btn_run.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.win.configure(cursor="watch")
        self.var_status.set("Fitting...")

    def stop_fit(self):
        if self._running:
            self._stop.set()
            self.btn_stop.configure(state="disabled")
            self.var_status.set("Stopping...")

    def _worker(self, t, y, params, extra, report, job, stop):
        try:
            res = fit_single_trace(t, y, stop_check=stop.is_set, **params)
            res.update(extra)
            self._q.put(("done", (res, report, job)))
        except FitStopped:
            self._q.put(("stopped", job))
        except Exception as exc:               # noqa: BLE001 - surfaced to UI
            self._q.put(("error", (exc, extra["_wl"], job)))

    def _poll_queue(self):
        try:
            while True:
                kind, payload = self._q.get_nowait()
                self._running = False
                self.btn_run.configure(state="normal")
                self.btn_stop.configure(state="disabled")
                self.win.configure(cursor="")
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
                        "Fit error", f"Fit failed:\n{self._worker_failed(exc)}")
        except queue.Empty:
            pass
        finally:                # an error above must not end the polling
            if self.alive:
                self.win.after(100, self._poll_queue)

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
        self._refresh_plot()

    def _report(self, res, wl, n_avg, t_lo, t_hi, n_in):
        info = res["info"]
        head = (f"Fit converged ({info['iters']} iters), " if info["success"]
                else f"NOT converged ({info['iters']} iters: {info['message']}), ")
        L = [head + f"RMS = {info['rms']:.4g}",
             f"λ centre = {wl:.2f} nm  (avg of {n_avg} px)",
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
    def _refresh_plot(self, replot_data=False):
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
        if self.var_scale.get() == "Log" and np.any(t > 0):
            pos = t[t > 0]
            ax.set_xscale("log"); axR.set_xscale("log")
            ax.set_xlim(pos.min(), t.max()); axR.set_xlim(pos.min(), t.max())
        else:
            ax.set_xscale("linear"); axR.set_xscale("linear")
            ax.set_xlim(t.min(), t.max()); axR.set_xlim(t.min(), t.max())
        ax.set_ylabel("intensity"); axR.set_ylabel("residual")
        axR.set_xlabel("delay (ps)")
        ax.set_title(f"λ = {wl:.2f} nm   (avg {n_avg} px)")
        leg = ax.legend(loc="best", fontsize=8, facecolor=PANEL, edgecolor=LINE)
        for txt in leg.get_texts():
            txt.set_color(INK)
        ax.grid(True, color=LINE, alpha=0.4); axR.grid(True, color=LINE, alpha=0.4)
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
            messagebox.showwarning("No fit", "Run the fit first.")
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
            with open(path, "w", encoding="utf-8", newline="") as fh:
                fh.write("# kinetics fit (single wavelength)\n")
                fh.write(f'# source: {self.model.phu["path"]}\n')
                for line in preamble:
                    fh.write(f"# {line}\n")
                if self.model.solvent_active:    # the trace was fitted after it
                    fh.write(f"# {self.app._export_note()}\n")
                fh.write("delay_ps,data,fit,residual\n")
                np.savetxt(fh, np.column_stack([t, y, fit, resid]),
                           delimiter=",", fmt="%.8g")

        def fill_ws(ws):
            pd = self.app._require_pandas()
            df = pd.DataFrame({"delay_ps": t, "data": y, "fit": fit, "residual": resid})
            _origin_fill_table(ws, df, [
                ("Delay", "ps", comment),
                ("Data", "a. u.", f"{r['_wl']:.2f} nm"),
                ("Fit", "a. u.", ""),
                ("Residual", "a. u.", "")])

        self.app.export_analysis(default_base, [
            {"suffix": "kinetics", "csv": write_csv, "fill": fill_ws}], owner=self.win)
