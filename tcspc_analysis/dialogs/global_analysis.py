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
from ..theme import ACCENT, BG, INK, INK_DIM, INK_FAINT, LINE, PANEL
from .common import ComponentTable, _AnalysisDialog, _dark_toolbar, _style_analysis_ax


class GlobalAnalysisDialog(_AnalysisDialog):
    """VARPRO global fit of the whole map: fit maps, DADS, EADS, kinetics."""

    def __init__(self, app):
        super().__init__(app, "Global analysis - whole map",
                         "1500x960", (1100, 720))
        self._last = None                   # last fit_global_analysis result
        self._stop = threading.Event()
        self._q = queue.Queue()
        self._running = False
        self._kin_wl = self._cursor_wl()
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
        ttk.Checkbutton(n_row, text="Include τ = ∞",
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
        ttk.Label(opt, text="Stretched-IRF").pack(side="left")
        self.var_irf_mode = tk.StringVar(value="numerical")
        ttk.Combobox(opt, textvariable=self.var_irf_mode,
                     values=["numerical", "skip"], width=10,
                     state="readonly").pack(side="left", padx=(4, 0))

        t0d, fwd = self._irf_defaults()
        irf = ttk.Labelframe(left, text="IRF (Gaussian)", padding=6)
        irf.pack(fill="x", pady=(2, 6))
        self.var_t0 = tk.StringVar(value=f"{t0d:.4g}")
        self.var_t0_fix = tk.BooleanVar(value=True)
        self.var_fw = tk.StringVar(value=f"{fwd:.4g}")
        self.var_fw_fix = tk.BooleanVar(value=True)
        self._irf_row(irf, "t₀ (ps)", self.var_t0, self.var_t0_fix)
        self._irf_row(irf, "FWHM (ps)", self.var_fw, self.var_fw_fix)

        tr = ttk.Labelframe(left, text="Fit t-range (ps)", padding=6)
        tr.pack(fill="x", pady=(2, 6))
        r1 = ttk.Frame(tr); r1.pack(fill="x")
        self.var_tmin = tk.StringVar(value=f"{m.times[0]:.4g}")
        self.var_tmax = tk.StringVar(value=f"{m.times[-1]:.4g}")
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
        self.btn_run = ttk.Button(btns, text="Run Fit", command=self.run_fit)
        self.btn_run.pack(side="left")
        self.btn_stop = ttk.Button(btns, text="Stop", command=self.stop_fit,
                                   state="disabled")
        self.btn_stop.pack(side="left", padx=(6, 0))
        ttk.Button(btns, text="Reset", command=self.reset).pack(side="left", padx=(6, 0))

        exp = ttk.Frame(left); exp.pack(fill="x")
        ttk.Label(exp, text="Export").pack(side="left")
        ttk.Button(exp, text="Export results",
                   command=self.export_results).pack(side="left", padx=(6, 0))
        ttk.Label(exp, text="(DADS + EADS; uses main CSV / .opju)",
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
        ttk.Label(kin, text="Kinetics λ (nm)").pack(side="left")
        self.var_kin_wl = tk.StringVar(value=f"{self._kin_wl:.2f}")
        ek = ttk.Entry(kin, textvariable=self.var_kin_wl, width=9, font=("TkFixedFont", 9))
        ek.pack(side="left", padx=(4, 8))
        ek.bind("<Return>", lambda ev: self._set_kin_wl())
        ttk.Button(kin, text="Use cursor λ",
                   command=self._use_cursor_kin).pack(side="left")
        ttk.Label(kin, text="Scale").pack(side="left", padx=(10, 4))
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
        self.var_tmin.set(f"{m.times[0]:.4g}")
        self.var_tmax.set(f"{m.times[-1]:.4g}")
        self._update_tcount()

    def _update_tcount(self):
        m = self.model
        try:
            lo = float(self.var_tmin.get()); hi = float(self.var_tmax.get())
        except ValueError:
            self.var_tcount.set(""); return
        if lo > hi:
            lo, hi = hi, lo
        n_in = int(((m.times >= lo) & (m.times <= hi)).sum())
        self.var_tcount.set(f"  -> fit will use {n_in} of {m.n_t} delay points")

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
        self.var_t0.set(f"{t0d:.4g}"); self.var_t0_fix.set(True)
        self.var_fw.set(f"{fwd:.4g}"); self.var_fw_fix.set(True)
        self._t_full()
        self._last = None
        self.var_status.set("Reset to defaults.")
        self.txt.delete("1.0", "end")

    # -- run (threaded) --------------------------------------------------
    def run_fit(self):
        if self._running:
            return
        m = self.model
        tau, fix, st, beta, bfix = self.table.read()
        if tau.size == 0 or np.any(tau <= 0):
            messagebox.showwarning("Invalid input", "τ must be > 0.")
            return
        try:
            t0 = float(self.var_t0.get()); fw = float(self.var_fw.get())
            lo = float(self.var_tmin.get()); hi = float(self.var_tmax.get())
        except ValueError:
            messagebox.showwarning("Invalid input", "Check the IRF / t-range boxes.")
            return
        if lo > hi:
            lo, hi = hi, lo
        tsel = (m.times >= lo) & (m.times <= hi)
        if int(tsel.sum()) < tau.size + 2:
            messagebox.showwarning("Window too narrow",
                                   "Widen the fit t-range.")
            return
        # snapshot the data so the worker never touches the live model
        D = m.E[:, tsel].copy()
        t = m.times[tsel].copy()
        # masked wavelengths are all-NaN rows; drop them so the fit only sees
        # real spectra (they simply never appear in the global-analysis result).
        wls_fit = m.wls.copy()
        keep = ~np.isnan(D).any(axis=1)
        if not keep.all():
            D = D[keep]
            wls_fit = wls_fit[keep]
        if D.shape[0] < 2:
            messagebox.showwarning(
                "Nothing to fit",
                "Every wavelength in range is masked out. Clear some masks "
                "or widen the crop.")
            return
        method = "trf" if self.var_opt.get().startswith("TRF") else "nm"
        params = dict(
            tau_init=tau, tau_fixed=fix, t0_init=t0, fwhm_init=fw,
            t0_fixed=self.var_t0_fix.get(), fwhm_fixed=self.var_fw_fix.get(),
            has_inf=self.var_inf.get(), beta_init=beta, beta_fixed=bfix,
            stretch_on=st, irf_mode=self.var_irf_mode.get(), method=method)

        # snapshot exactly what the fit sees, so redraws never depend on the
        # entry boxes the user may edit while / after the fit runs
        self._fit_D = D
        self._fit_t = t
        self._fit_wls = wls_fit
        self._stop.clear()
        self._running = True
        self.btn_run.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.var_status.set("Fitting...")
        threading.Thread(target=self._worker, args=(D, t, params),
                         daemon=True).start()

    def _worker(self, D, t, params):
        try:
            res = fit_global_analysis(
                D, t, stop_check=self._stop.is_set, **params)
            # what the result was fitted with - the box may be changed afterwards
            res["has_inf"] = bool(params["has_inf"])
            self._q.put(("done", res))
        except GlobalAnalysisStopped:
            self._q.put(("stopped", None))
        except Exception as exc:               # noqa: BLE001 - surfaced to UI
            self._q.put(("error", str(exc)))

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
                    self._on_done(payload)
                elif kind == "stopped":
                    self._finish_run("Stopped by user.")
                elif kind == "error":
                    self._finish_run("Fit failed.")
                    messagebox.showerror("Fit error", str(payload))
        except queue.Empty:
            pass
        finally:                # an error above must not end the polling
            if self.alive:
                self.win.after(150, self._poll_queue)

    def _finish_run(self, status):
        self._running = False
        self.btn_run.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        self.var_status.set(status)

    def _on_done(self, res):
        self._last = res
        # DADS = the amplitude spectra A (M x k); EADS from the sequential model
        A = res["A"]
        tau = res["tau"]
        has_inf = res["has_inf"]
        try:
            eads, tau_sorted, _ = compute_eads_from_dads(A, tau, has_inf)
        except Exception:
            eads, tau_sorted = A.copy(), np.sort(tau)
        res["_eads"] = eads
        res["_tau_sorted"] = tau_sorted
        self._report_global(res)
        self._finish_run(f"Fit done - RMS = {res['info']['rms']:.4g} "
                         f"({res['info']['iters']} evals)")
        self._draw_all()

    def _report_global(self, res):
        has_inf = res["has_inf"]
        L = [f"Global fit: RMS = {res['info']['rms']:.4g}  "
             f"(initial {res['info']['initialRMS']:.4g})",
             f"method = {res['info']['method']}, "
             f"{res['info']['iters']} objective evals",
             f"IRF: t₀ = {res['t0']:.4g} ps, FWHM = {res['fwhm']:.4g} ps",
             f"IRF mode: {res['info']['irf_mode']}", "",
             "  i   τ (ps)         β      (type)"]
        st = res["stretch_on"]
        for i in range(len(res["tau"])):
            tag = "stretched" if st[i] else "exp"
            L.append(f"  {i+1}   {res['tau'][i]:11.5g}  {res['beta'][i]:6.3g}  ({tag})")
        if has_inf:
            L.append("  ∞   (constant offset)")
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
        ext = [wl[0], wl[-1], t[-1], t[0]]
        cmap = self.app.var_cmap.get()
        vmax = float(np.nanmax(np.abs(D))) or 1.0
        rmax = float(np.nanmax(np.abs(resid))) or 1.0
        for ax, Z, title in ((self.ax_data, D, "data"),
                             (self.ax_fit, fit, "global fit"),
                             (self.ax_resid, resid, "residual")):
            ax.clear(); _style_analysis_ax(ax)
            if title == "residual":
                ax.imshow(Z.T, aspect="auto", extent=ext, cmap="RdBu_r",
                          vmin=-rmax, vmax=rmax, origin="upper",
                          interpolation="nearest")
            else:
                ax.imshow(Z.T, aspect="auto", extent=ext, cmap=cmap,
                          vmin=0, vmax=vmax, origin="upper",
                          interpolation="nearest")
            ax.set_title(title)
            ax.set_xlabel("wavelength (nm)")
        self.ax_data.set_ylabel("delay (ps)")

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
        ax.set_ylabel("amplitude"); ax.set_xlabel("wavelength (nm)")
        axn.set_xlabel("wavelength (nm)")
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
        ax.set_xlabel("delay (ps)"); ax.set_ylabel("intensity")
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
            messagebox.showwarning("No fit", "Run the fit first.")
            return
        res = self._last
        phu_base = os.path.splitext(os.path.basename(self.model.phu["path"]))[0]
        default_base = phu_base            # suffixes "DADS"/"EADS" complete the names
        wl = np.asarray(self._fit_wls)
        A = np.asarray(res["A"]); eads = np.asarray(res["_eads"])
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
                    if self.model.solvent_active:    # the map was fitted after it
                        fh.write(f"# {self.app._export_note()}\n")
                    fh.write("wavelength_nm,"
                             + ",".join(f"{kind}_{lb}" for lb in labels) + "\n")
                    np.savetxt(fh, np.column_stack([wl, S]),
                               delimiter=",", fmt="%.8g")
            return _w

        def make_fill(S, labels, kind):
            def _f(ws):
                pd = self.app._require_pandas()
                cols = {"Wavelength": wl}
                for j, lb in enumerate(labels):
                    cols[f"{kind}_{lb}"] = S[:, j]
                df = pd.DataFrame(cols)
                specs = [("Wavelength", "nm", "")]
                specs += [(kind, "a. u.", f"tau={lb}") for lb in labels]
                _origin_fill_table(ws, df, specs)
            return _f

        self.app.export_analysis(default_base, [
            {"suffix": "DADS", "csv": make_csv(A, dads_labels, "DADS"),
             "fill": make_fill(A, dads_labels, "DADS")},
            {"suffix": "EADS", "csv": make_csv(eads, eads_labels, "EADS"),
             "fill": make_fill(eads, eads_labels, "EADS")}])
