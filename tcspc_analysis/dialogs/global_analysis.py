"""The Global-analysis window."""
import os
import queue
import threading

import numpy as np

import matplotlib
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from matplotlib.gridspec import GridSpec

import tkinter as tk
from tkinter import messagebox, ttk

from ..origin import _origin_fill_table
from ..fitting import GlobalAnalysisStopped, compute_eads_from_dads, fit_global_analysis
from ..model import wavelength_grid
from ..theme import ACCENT, BG, INK, INK_DIM, INK_FAINT, LINE, PANEL
from .common import ComponentTable, _AnalysisDialog, _dark_toolbar, _style_analysis_ax, fmt_ps, in_range, read_number


class GlobalAnalysisDialog(_AnalysisDialog):
    """VARPRO global fit of the whole map: fit maps, DADS, EADS, kinetics."""

    def __init__(self, app):
        super().__init__(app, "Global analysis - whole map",
                         "1500x960", (1100, 720))
        self._last = None                   # last fit_global_analysis result
        self._stop = threading.Event()
        self._q = queue.Queue()
        self._running = False
        self._job = 0                       # raised by Reset: a result of an older job is dropped
        self._kin_wl = self._cursor_wl()
        self._seen_t0 = self.model.t0       # the time origin the boxes are quoted in
        self._build()
        self.win.after(100, self._poll_queue)

    def _on_close(self):
        self._stop.set()
        super()._on_close()

    # -- layout ----------------------------------------------------------
    def _build(self):
        m = self.model
        outer = ttk.Frame(self.win, padding=8)
        outer.pack(fill="both", expand=True)

        left = ttk.Labelframe(outer, text="Fit setup", padding=8)
        left.pack(side="left", fill="y")
        left.configure(width=380)
        left.pack_propagate(False)

        n_row = ttk.Frame(left); n_row.pack(fill="x")
        ttk.Label(n_row, text="Components").pack(side="left")
        self.var_n = tk.StringVar(value="3")
        cb = ttk.Combobox(n_row, textvariable=self.var_n,
                          values=["1", "2", "3", "4", "5"], width=4, state="readonly")
        cb.pack(side="left", padx=(4, 10))
        cb.bind("<<ComboboxSelected>>", lambda e: self.table.set_n(int(self.var_n.get())))
        self.var_inf = tk.BooleanVar(value=False)
        ttk.Checkbutton(n_row, text="Include τ = ∞ offset",
                        variable=self.var_inf).pack(side="left")

        self.table = ComponentTable(left)
        self.table.pack(fill="x", pady=(4, 6))
        self.table.set_n(3)

        opt = ttk.Frame(left); opt.pack(fill="x", pady=(0, 4))
        ttk.Label(opt, text="Optimizer").pack(side="left")
        self.var_opt = tk.StringVar(value="TRF (fast)")
        ttk.Combobox(opt, textvariable=self.var_opt,
                     values=["TRF (fast)", "Nelder-Mead"], width=13,
                     state="readonly").pack(side="left", padx=(4, 10))
        ttk.Label(opt, text="Stretched-IRF mode").pack(side="left")
        self.var_irf_mode = tk.StringVar(value="numerical")
        ttk.Combobox(opt, textvariable=self.var_irf_mode,
                     values=["numerical", "skip"], width=10,
                     state="readonly").pack(side="left", padx=(4, 0))

        t0d, fwd = self._irf_defaults()
        irf = ttk.Labelframe(left, text="IRF (Gaussian)", padding=6)
        irf.pack(fill="x", pady=(2, 6))
        self.var_t0 = tk.StringVar(value=fmt_ps(t0d))
        self.var_t0_fix = tk.BooleanVar(value=True)
        self.var_fw = tk.StringVar(value=f"{fwd:.4g}")
        self.var_fw_fix = tk.BooleanVar(value=True)
        self._irf_row(irf, "t₀ (ps)", self.var_t0, self.var_t0_fix)
        self._irf_row(irf, "FWHM (ps)", self.var_fw, self.var_fw_fix)

        tr = ttk.Labelframe(left, text="Fit range (ps)", padding=6)
        tr.pack(fill="x", pady=(2, 6))
        r1 = ttk.Frame(tr); r1.pack(fill="x")
        self.var_tmin = tk.StringVar(value=fmt_ps(m.times[0]))
        self.var_tmax = tk.StringVar(value=fmt_ps(m.times[-1]))
        ttk.Label(r1, text="From").pack(side="left")
        e0 = ttk.Entry(r1, textvariable=self.var_tmin, width=9, font=("TkFixedFont", 9))
        e0.pack(side="left", padx=(4, 8))
        ttk.Label(r1, text="To").pack(side="left")
        e1 = ttk.Entry(r1, textvariable=self.var_tmax, width=9, font=("TkFixedFont", 9))
        e1.pack(side="left", padx=(4, 8))
        ttk.Button(r1, text="Full", command=self._t_full).pack(side="left")
        self.var_tcount = tk.StringVar(value="")
        ttk.Label(tr, textvariable=self.var_tcount, style="Val.TLabel",
                  foreground=INK_FAINT).pack(anchor="w", pady=(3, 0))
        for e in (e0, e1):
            e.bind("<KeyRelease>", lambda ev: self._update_tcount())
        self._update_tcount()

        btns = ttk.Frame(left); btns.pack(fill="x", pady=(2, 6))
        self.btn_run = ttk.Button(btns, text="Run fit", command=self.run_fit)
        self.btn_run.pack(side="left")
        self.btn_stop = ttk.Button(btns, text="Stop", command=self.stop_fit,
                                   state="disabled")
        self.btn_stop.pack(side="left", padx=(6, 0))
        ttk.Button(btns, text="Reset", command=self.reset).pack(side="left", padx=(6, 0))

        exp = ttk.Frame(left); exp.pack(fill="x")
        ttk.Label(exp, text="Export").pack(side="left")
        ttk.Button(exp, text="Export results",
                   command=self.export_results).pack(side="left", padx=(6, 0))
        ttk.Label(exp, text="(DADS + EADS; formats chosen in the main window)",
                  style="Val.TLabel", foreground=INK_FAINT).pack(side="left", padx=(6, 0))

        self.var_status = tk.StringVar(value="Ready.")
        ttk.Label(left, textvariable=self.var_status, style="Val.TLabel",
                  foreground=ACCENT).pack(anchor="w", pady=(6, 2))
        self.txt = tk.Text(left, height=14, width=42, bg=BG, fg=INK,
                           insertbackground=INK, relief="flat",
                           font=("TkFixedFont", 9), wrap="none")
        self.txt.pack(fill="both", expand=True)
        self.txt.insert("1.0", "Results will appear here after fitting.")

        # right: kinetics controls + figure
        right = ttk.Labelframe(outer, text="Results", padding=6)
        right.pack(side="left", fill="both", expand=True, padx=(8, 0))

        kin = ttk.Frame(right); kin.pack(fill="x")
        ttk.Label(kin, text="λ (nm)").pack(side="left")
        self.var_kin_wl = tk.StringVar(value=f"{self._kin_wl:.2f}")
        ek = ttk.Entry(kin, textvariable=self.var_kin_wl, width=9, font=("TkFixedFont", 9))
        ek.pack(side="left", padx=(4, 8))
        ek.bind("<Return>", lambda ev: self._set_kin_wl())
        ttk.Button(kin, text="Use cursor λ",
                   command=self._use_cursor_kin).pack(side="left")
        ttk.Label(kin, text="Time scale").pack(side="left", padx=(10, 4))
        self.var_kin_scale = tk.StringVar(value="Log")
        sc = ttk.Combobox(kin, textvariable=self.var_kin_scale,
                          values=["Log", "Linear"], width=8, state="readonly")
        sc.pack(side="left")
        sc.bind("<<ComboboxSelected>>", lambda e: self._plot_kinetics())
        ttk.Label(kin, text="  (click a map to pick λ)",
                  style="Val.TLabel", foreground=INK_FAINT).pack(side="left", padx=(8, 0))

        self.fig = Figure(figsize=(11, 8), dpi=100, facecolor=PANEL)
        gs = GridSpec(4, 3, figure=self.fig, height_ratios=[1.4, 1.0, 1.0, 1.1],
                      left=0.07, right=0.97, top=0.95, bottom=0.06,
                      hspace=0.5, wspace=0.28)
        self.ax_data = self.fig.add_subplot(gs[0, 0])
        self.ax_fit = self.fig.add_subplot(gs[0, 1])
        self.ax_resid = self.fig.add_subplot(gs[0, 2])
        self.ax_dads = self.fig.add_subplot(gs[1, 0:2])
        self.ax_dads_n = self.fig.add_subplot(gs[1, 2])
        self.ax_eads = self.fig.add_subplot(gs[2, 0:2])
        self.ax_eads_n = self.fig.add_subplot(gs[2, 2])
        self.ax_kin = self.fig.add_subplot(gs[3, :])
        self._all_axes = [self.ax_data, self.ax_fit, self.ax_resid,
                          self.ax_dads, self.ax_dads_n, self.ax_eads,
                          self.ax_eads_n, self.ax_kin]
        for ax in self._all_axes:
            _style_analysis_ax(ax)
        self.canvas = FigureCanvasTkAgg(self.fig, master=right)
        tb = _dark_toolbar(self.canvas, right)
        tb.pack(fill="x")
        self.canvas.get_tk_widget().pack(fill="both", expand=True)
        self.canvas.mpl_connect("button_press_event", self._on_map_click)
        self.canvas.draw_idle()

    def _irf_row(self, parent, label, var, fix_var):
        row = ttk.Frame(parent); row.pack(fill="x", pady=1)
        ttk.Label(row, text=label, width=10).pack(side="left")
        ttk.Entry(row, textvariable=var, width=10,
                  font=("TkFixedFont", 9)).pack(side="left", padx=(4, 8))
        ttk.Checkbutton(row, text="fixed", variable=fix_var).pack(side="left")

    # -- small helpers ---------------------------------------------------
    def _t_full(self):
        m = self.model
        self.var_tmin.set(fmt_ps(m.times[0]))
        self.var_tmax.set(fmt_ps(m.times[-1]))
        self._update_tcount()

    def _update_tcount(self):
        m = self.model
        try:
            lo = float(self.var_tmin.get()); hi = float(self.var_tmax.get())
        except ValueError:
            self.var_tcount.set(""); return
        if lo > hi:
            lo, hi = hi, lo
        n_in = int(in_range(m.times, lo, hi).sum())
        self.var_tcount.set(f"  -> fit will use {n_in} of {m.n_t} delay points")

    def model_changed(self):
        """The data behind the window changed. When the time axis was
        renumbered ("t0 at IRF peak"), t₀ and the fit range are moved along so
        that they keep meaning the same delays; then the window shows the
        data as it is now."""
        self._follow_t0()
        self._update_tcount()

    def _use_cursor_kin(self):
        self._kin_wl = self._cursor_wl()
        self.var_kin_wl.set(f"{self._kin_wl:.2f}")
        self._plot_kinetics()

    def _set_kin_wl(self):
        try:
            self._kin_wl = float(self.var_kin_wl.get())
        except ValueError:
            return
        self._plot_kinetics()

    def _on_map_click(self, event):
        if event.inaxes in (self.ax_data, self.ax_fit, self.ax_resid) \
                and event.xdata is not None:
            self._kin_wl = float(event.xdata)
            self.var_kin_wl.set(f"{self._kin_wl:.2f}")
            self._plot_kinetics()

    def reset(self):
        self.var_n.set("3"); self.table.set_n(3)
        self.var_inf.set(False)
        self.var_opt.set("TRF (fast)"); self.var_irf_mode.set("numerical")
        t0d, fwd = self._irf_defaults()
        self.var_t0.set(fmt_ps(t0d)); self.var_t0_fix.set(True)
        self.var_fw.set(f"{fwd:.4g}"); self.var_fw_fix.set(True)
        self._t_full()
        self._last = None
        self._job += 1                      # a fit still running was set up before the reset
        self._stop.set()
        self.var_status.set("Reset to defaults.")
        self.txt.delete("1.0", "end")
        self.ax_kin.set_xscale("linear")    # avoid clear() warning on log axis
        for ax in self._all_axes:           # the result is gone: so is its picture
            ax.clear(); _style_analysis_ax(ax)
        self.canvas.draw_idle()

    # -- run (threaded) --------------------------------------------------
    def run_fit(self):
        if self._running:
            return
        m = self.model
        # every box is read here, and one that cannot be used is named: no
        # stand-in value is fitted with instead
        try:
            tau, fix, st, beta, bfix = self.table.read_checked()
            t0 = read_number(self.var_t0, "t₀")
            fw = read_number(self.var_fw, "The IRF FWHM")
            lo = read_number(self.var_tmin, "The start of the fit range")
            hi = read_number(self.var_tmax, "The end of the fit range")
        except ValueError as exc:
            messagebox.showwarning("Invalid input", str(exc), parent=self.win)
            return
        if tau.size == 0:
            messagebox.showwarning("No components", "Add at least one component.", parent=self.win)
            return
        if lo > hi:
            lo, hi = hi, lo
        tsel = in_range(m.times, lo, hi)
        if int(tsel.sum()) < tau.size + 2:
            messagebox.showwarning("Window too narrow",
                                   "Widen the fit t-range.", parent=self.win)
            return
        # snapshot the data so the worker never touches the live model
        D = m.E[:, tsel].copy()
        t = m.times[tsel].copy()
        # masked wavelengths are all-NaN rows; drop them so the fit only sees
        # real spectra (they simply never appear in the global-analysis result).
        wls_fit = m.wls.copy()
        keep = ~np.isnan(D).any(axis=1)
        # where the fitted curves sit on the map's wavelength axis, masked
        # ones included: the three maps are drawn on that axis
        col, n_cols, _ = wavelength_grid(m.wls)
        axis = {"_cols": col[keep], "_n_cols": n_cols, "_wl_edges": tuple(m.wl_edges),
                "_dt": float(m.dt_ps)}
        if not keep.all():
            D = D[keep]
            wls_fit = wls_fit[keep]
        if D.shape[0] < 2:
            n_masked = int((~keep).sum())
            messagebox.showwarning(
                "Nothing to fit",
                f"Global analysis needs at least 2 wavelengths; {D.shape[0]} "
                f"left ({n_masked} of {keep.size} in range are masked). "
                + ("Clear some masks or widen the crop." if n_masked
                   else "Widen the crop."), parent=self.win)
            return
        method = "trf" if self.var_opt.get().startswith("TRF") else "nm"
        params = dict(
            tau_init=tau, tau_fixed=fix, t0_init=t0, fwhm_init=fw,
            t0_fixed=self.var_t0_fix.get(), fwhm_fixed=self.var_fw_fix.get(),
            has_inf=self.var_inf.get(), beta_init=beta, beta_fixed=bfix,
            stretch_on=st, irf_mode=self.var_irf_mode.get(), method=method)

        record = self._fit_record(lo, hi, int(tsel.sum()), self._fixed_names(
            fix, st, bfix, self.var_t0_fix.get(), self.var_fw_fix.get()))
        record.update(axis)
        self._stop.clear()
        # started first: if that fails, the window is not left "running"
        threading.Thread(target=self._worker,
                         args=(D, t, wls_fit, params, record, self._job),
                         daemon=True).start()
        self._running = True
        self.btn_run.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.win.configure(cursor="watch")
        self.var_status.set("Fitting...")

    def _worker(self, D, t, wls_fit, params, record, job):
        try:
            res = fit_global_analysis(
                D, t, stop_check=self._stop.is_set, **params)
            # what the result was fitted with - the box may be changed afterwards
            res["has_inf"] = bool(params["has_inf"])
            res.update(record)
            # ... and exactly what the fit saw. It travels with the result, so
            # a run that is stopped or fails leaves the previous result whole
            # and redraws never depend on boxes edited while / after the fit.
            self._q.put(("done", (res, D, t, wls_fit, job)))
        except GlobalAnalysisStopped:
            self._q.put(("stopped", job))
        except Exception as exc:               # noqa: BLE001 - surfaced to UI
            self._q.put(("error", exc))

    def stop_fit(self):
        if self._running:
            self._stop.set()
            self.btn_stop.configure(state="disabled")
            self.var_status.set("Stopping...")

    def _poll_queue(self):
        try:
            while True:
                kind, payload = self._q.get_nowait()
                if kind == "done":
                    try:
                        self._on_done(payload)
                    except Exception:
                        # the fit is over either way: free the buttons, then
                        # let the error go on to the callback handler (the log)
                        self._finish_run("Fit done, but showing the result failed.")
                        raise
                elif kind == "stopped":
                    # stopped by Reset: the status already says so
                    self._finish_run("Stopped by user." if payload == self._job
                                     else self.var_status.get())
                elif kind == "error":
                    self._finish_run("Fit failed.")
                    messagebox.showerror("Fit error", self._worker_failed(payload), parent=self.win)
        except queue.Empty:
            pass
        finally:                # an error above must not end the polling
            if self.alive:
                self._watch_model()
                self.win.after(150, self._poll_queue)

    def _finish_run(self, status):
        self._running = False
        self.btn_run.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        self.win.configure(cursor="")
        self.var_status.set(status)

    def _on_done(self, payload):
        if payload[-1] != self._job:        # Reset was pressed while it ran
            self._finish_run("Fit dropped - the setup was reset while it ran.")
            return
        res, self._fit_D, self._fit_t, self._fit_wls, _ = payload
        self._last = res
        # DADS = the amplitude spectra A (M x k); EADS from the sequential model
        A = res["A"]
        tau = res["tau"]
        has_inf = res["has_inf"]
        try:
            eads, tau_sorted, _ = compute_eads_from_dads(A, tau, has_inf)
            note = ""
        except Exception as exc:            # noqa: BLE001 - e.g. two equal lifetimes
            # no sequential spectra, rather than DADS shown under that name
            eads, tau_sorted, note = None, np.sort(tau), str(exc)
        res["_eads"] = eads
        res["_eads_note"] = note
        res["_tau_sorted"] = tau_sorted
        self._report_global(res)
        self._finish_run(f"Fit done - RMS = {res['info']['rms']:.4g} "
                         f"({res['info']['iters']} iterations)"
                         + ("" if res["info"]["success"] else "  (not converged)")
                         + (f"  ({len(res['info']['warnings'])} warning"
                            f"{'s' if len(res['info']['warnings']) > 1 else ''}, "
                            f"see the report)" if res["info"]["warnings"] else ""))
        if self._is_stale(res):             # the data changed while it ran
            self._said_stale = res
            self.var_status.set(self.STALE)
        self._draw_all()

    def _report_global(self, res):
        has_inf = res["has_inf"]
        L = [f"Global fit: RMS = {res['info']['rms']:.4g}  "
             f"(initial {res['info']['initialRMS']:.4g})",
             f"method = {res['info']['method']}, "
             f"{res['info']['iters']} iterations "
             f"({res['info']['n_objective']} model evaluations)",
             f"IRF: t₀ = {res['t0']:.4g} ps, FWHM = {res['fwhm']:.4g} ps",
             f"IRF mode: {res['info']['irf_mode']}"]
        if not res["info"]["success"]:
            L.append(f"Not converged: {res['info']['message']}")
        L += ["", "  i   τ (ps)         β      (type)"]
        st = res["stretch_on"]
        for i in range(len(res["tau"])):
            tag = "stretched" if st[i] else "exp"
            L.append(f"  {i+1}   {res['tau'][i]:11.5g}  {res['beta'][i]:6.3g}  ({tag})")
        if has_inf:
            L.append("  ∞   (constant offset)")
        if res["_eads"] is None:
            L += ["", f"EADS not available: {res['_eads_note']}"]
        if res["info"]["warnings"]:
            L += [""] + [f"Warning: {w}" for w in res["info"]["warnings"]]
        self.txt.delete("1.0", "end")
        self.txt.insert("1.0", "\n".join(L))

    # -- drawing ---------------------------------------------------------
    def _draw_all(self):
        self._plot_maps()
        self._plot_spectra()
        self._plot_kinetics()
        self.canvas.draw_idle()

    def _plot_maps(self):
        res = self._last
        wl = self._fit_wls
        t = self._fit_t
        D = self._fit_D
        fit = res["fit"]
        resid = D - fit
        # On the wavelength axis of the map the fit was made from: a masked
        # band stays an empty band instead of closing up, and every column is
        # centred on its own wavelength. (The extent used to run from the
        # centre of the first cell to the centre of the last, so a click near
        # an edge - or anywhere beside a masked band - picked another curve.)
        half = res["_dt"] / 2.0
        ext = [res["_wl_edges"][0], res["_wl_edges"][1], t[-1] + half, t[0] - half]

        def on_axis(Z):
            out = np.full((res["_n_cols"], Z.shape[1]), np.nan)
            out[res["_cols"]] = Z
            return out
        cmap = self.app.var_cmap.get()
        vmax = float(np.nanmax(np.abs(D))) or 1.0
        rmax = float(np.nanmax(np.abs(resid))) or 1.0
        for ax, Z, title in ((self.ax_data, D, "data"),
                             (self.ax_fit, fit, "global fit"),
                             (self.ax_resid, resid, "residual")):
            ax.clear(); _style_analysis_ax(ax)
            if title == "residual":
                ax.imshow(on_axis(Z).T, aspect="auto", extent=ext, cmap="RdBu_r",
                          vmin=-rmax, vmax=rmax, origin="upper",
                          interpolation="nearest")
            else:
                ax.imshow(on_axis(Z).T, aspect="auto", extent=ext, cmap=cmap,
                          vmin=0, vmax=vmax, origin="upper",
                          interpolation="nearest")
            ax.set_title(title)
            ax.set_xlabel("Wavelength (nm)")
        self.ax_data.set_ylabel("Time (ps)")

    def _plot_spectra(self):
        res = self._last
        wl = self._fit_wls
        has_inf = res["has_inf"]
        A = res["A"]; eads = res["_eads"]
        tau = res["tau"]
        labels = [f"{tau[i]:.3g} ps" for i in range(len(tau))]
        if has_inf:
            labels.append("∞")
        elabels = [f"{res['_tau_sorted'][i]:.3g} ps"
                   for i in range(len(res["_tau_sorted"]))]
        if has_inf:
            elabels.append("∞")
        self._plot_spectrum_pair(self.ax_dads, self.ax_dads_n, wl, A, labels, "DADS")
        if eads is None:
            for ax, title in ((self.ax_eads, "EADS"), (self.ax_eads_n, "EADS (norm.)")):
                ax.clear(); _style_analysis_ax(ax)
                ax.set_title(title)
            self.ax_eads.text(0.5, 0.5, "not available - see the report",
                              transform=self.ax_eads.transAxes, ha="center",
                              va="center", color=INK_DIM, fontsize=9)
            return
        self._plot_spectrum_pair(self.ax_eads, self.ax_eads_n, wl, eads, elabels, "EADS")

    def _plot_spectrum_pair(self, ax, axn, wl, S, labels, kind):
        ax.clear(); axn.clear()
        _style_analysis_ax(ax); _style_analysis_ax(axn)
        k = S.shape[1]
        colors = matplotlib.colormaps["turbo"](np.linspace(0.1, 0.9, max(k, 2)))
        for j in range(k):
            ax.plot(wl, S[:, j], color=colors[j], linewidth=1.2,
                    label=labels[j] if j < len(labels) else str(j))
            peak = np.nanmax(np.abs(S[:, j])) or 1.0
            axn.plot(wl, S[:, j] / peak, color=colors[j], linewidth=1.2)
        ax.axhline(0, color=LINE, linestyle=":", linewidth=0.6)
        axn.axhline(0, color=LINE, linestyle=":", linewidth=0.6)
        ax.set_title(kind); axn.set_title(kind + " (norm.)")
        ax.set_ylabel("Amplitude"); ax.set_xlabel("Wavelength (nm)")
        axn.set_xlabel("Wavelength (nm)")
        leg = ax.legend(loc="best", fontsize=7, facecolor=PANEL, edgecolor=LINE,
                        ncol=2)
        if leg:
            for txt in leg.get_texts():
                txt.set_color(INK)

    def _plot_kinetics(self):
        if self._last is None:
            return
        ax = self.ax_kin
        ax.set_xscale("linear")             # avoid clear() warning on log axis
        ax.clear(); _style_analysis_ax(ax)
        wl = self._fit_wls
        wi = int(np.argmin(np.abs(wl - self._kin_wl)))
        t = self._fit_t
        D = self._fit_D
        ax.plot(t, D[wi, :], ".", color=INK_DIM, markersize=3, label="data")
        ax.plot(t, self._last["fit"][wi, :], "-", color=ACCENT, linewidth=1.4,
                label="fit")
        ax.axhline(0, color=LINE, linestyle=":", linewidth=0.6)
        if self.var_kin_scale.get() == "Log" and np.any(t > 0):
            ax.set_xscale("log"); ax.set_xlim(t[t > 0].min(), t.max())
        else:
            ax.set_xscale("linear"); ax.set_xlim(t.min(), t.max())
        ax.set_title(f"kinetics @ {wl[wi]:.2f} nm")
        ax.set_xlabel("Time (ps)"); ax.set_ylabel("Intensity")
        leg = ax.legend(loc="best", fontsize=8, facecolor=PANEL, edgecolor=LINE)
        for txt in leg.get_texts():
            txt.set_color(INK)
        ax.grid(True, color=LINE, alpha=0.4)
        self.canvas.draw_idle()

    # -- export ----------------------------------------------------------
    def _param_summary(self, res):
        """Multi-line GA summary for the CSV preamble / opju column comment."""
        lines = [f"RMS = {res['info']['rms']:.6g} "
                 f"(initial {res['info']['initialRMS']:.6g})",
                 f"method = {res['info']['method']}, {res['info']['iters']} evals, "
                 f"IRF {res['info']['irf_mode']}",
                 f"t0 = {res['t0']:.6g} ps, FWHM = {res['fwhm']:.6g} ps"]
        st = res["stretch_on"]
        for i in range(len(res["tau"])):
            tag = "stretched" if st[i] else "exp"
            lines.append(f"comp {i+1}: tau = {res['tau'][i]:.6g} ps, "
                         f"beta = {res['beta'][i]:.4g} ({tag})")
        if res["has_inf"]:
            lines.append("offset: tau = inf")
        return lines

    def export_results(self):
        """Write DADS + EADS, honouring the main window's CSV / .opju ticks.

        Two datasets ({stem}_DADS, {stem}_EADS): wavelength + one amplitude
        column per lifetime component, with the fit parameters in the CSV
        preamble and the opju column comments. Same path as "Export data..."
        so the tabs land in Book1 alongside the TRES map.
        """
        if self._last is None:
            messagebox.showwarning("No fit", "Run the fit first.", parent=self.win)
            return
        res = self._last
        phu_base = os.path.splitext(os.path.basename(self.model.phu["path"]))[0]
        default_base = phu_base            # suffixes "DADS"/"EADS" complete the names
        wl = np.asarray(self._fit_wls)
        A = np.asarray(res["A"])
        eads = None if res["_eads"] is None else np.asarray(res["_eads"])
        tau = res["tau"]; tsort = res["_tau_sorted"]
        inf = ["inf"] if res["has_inf"] else []
        dads_labels = [f"{tau[i]:.4g}ps" for i in range(len(tau))] + inf
        eads_labels = [f"{tsort[i]:.4g}ps" for i in range(len(tsort))] + inf
        preamble = self._param_summary(res)

        def make_csv(S, labels, kind):
            def _w(path):
                with open(path, "w", encoding="utf-8", newline="") as fh:
                    fh.write(f"# global analysis - {kind}\n")
                    fh.write(f'# source: {self.model.phu["path"]}\n')
                    for line in preamble:
                        fh.write(f"# {line}\n")
                    # what was fitted, as it was when the fit was started
                    fh.write(f"# {res['_setup']}\n")
                    fh.write(f"# {res['_note']}\n")
                    fh.write("wavelength_nm,"
                             + ",".join(f"{kind}_{lb}" for lb in labels) + "\n")
                    np.savetxt(fh, np.column_stack([wl, S]),
                               delimiter=",", fmt="%.8g")
            return _w

        def make_fill(S, labels, kind):
            def _f(ws):
                specs = [("Wavelength", "nm", "")]
                specs += [(kind, "a. u.", f"tau={lb}") for lb in labels]
                _origin_fill_table(ws, [wl] + [S[:, j] for j in range(len(labels))], specs)
            return _f

        items = [{"suffix": "DADS", "csv": make_csv(A, dads_labels, "DADS"),
                  "fill": make_fill(A, dads_labels, "DADS")}]
        if eads is not None:
            items.append({"suffix": "EADS", "csv": make_csv(eads, eads_labels, "EADS"),
                          "fill": make_fill(eads, eads_labels, "EADS")})
        self.app.export_analysis(default_base, items, owner=self.win)
