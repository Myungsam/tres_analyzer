"""The Mask window."""
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

import tkinter as tk
from tkinter import messagebox, ttk

from ..theme import ACCENT, BG, INK, INK_FAINT, LINE, PANEL, preview_norm_cmap, shade_wl_masks, style_plot_ax
from .common import _AnalysisDialog


class MaskDialog(_AnalysisDialog):
    """Add / remove wavelength bands that are set to NaN and so drop out of the
    map, the summed spectra and the fits (they stay in the axis as a gap)."""

    def __init__(self, app):
        super().__init__(app, "Mask wavelengths", "940x720", (760, 560))
        self.var_lo = tk.StringVar(value="")
        self.var_hi = tk.StringVar(value="")
        self.var_info = tk.StringVar(value="Click the map to pick From, then To.")
        self._pick_hi = False       # False -> next click sets From, True -> To
        self._build_ui()
        self._draw()
        self._refresh_list()

    def _build_ui(self):
        top = ttk.Frame(self.win, padding=(8, 8, 8, 4))
        top.pack(fill="x")
        ttk.Label(top, text="From").pack(side="left")
        ttk.Entry(top, textvariable=self.var_lo, width=8,
                  font=("TkFixedFont", 9)).pack(side="left", padx=2)
        ttk.Label(top, text="To").pack(side="left")
        ttk.Entry(top, textvariable=self.var_hi, width=8,
                  font=("TkFixedFont", 9)).pack(side="left", padx=2)
        ttk.Label(top, text="nm").pack(side="left", padx=(2, 8))
        ttk.Button(top, text="Add region", command=self._add).pack(side="left")
        ttk.Label(top, textvariable=self.var_info,
                  foreground=INK_FAINT).pack(side="left", padx=12)

        mid = ttk.Frame(self.win)
        mid.pack(fill="both", expand=True)
        self.fig = Figure(figsize=(7.6, 4.8), dpi=100, facecolor=PANEL)
        self.ax = self.fig.add_subplot(111)
        style_plot_ax(self.ax)
        self.canvas = FigureCanvasTkAgg(self.fig, master=mid)
        self.canvas.get_tk_widget().pack(side="left", fill="both", expand=True,
                                         padx=(8, 4), pady=4)
        self.canvas.mpl_connect("button_press_event", self._on_click)

        side = ttk.Frame(mid, padding=(4, 6))
        side.pack(side="left", fill="y")
        ttk.Label(side, text="Masked regions (NaN)").pack(anchor="w")
        self.listbox = tk.Listbox(side, width=20, height=14, bg=BG, fg=INK,
                                  selectbackground=ACCENT, selectforeground=BG,
                                  highlightthickness=1, highlightbackground=LINE,
                                  activestyle="none", font=("TkFixedFont", 9))
        self.listbox.pack(fill="y", expand=True, pady=3)
        ttk.Button(side, text="Remove selected",
                   command=self._remove).pack(fill="x", pady=1)
        ttk.Button(side, text="Clear all", command=self._clear).pack(fill="x", pady=1)
        ttk.Button(side, text="Close",
                   command=self._on_close).pack(fill="x", pady=(10, 1))

    def _draw(self):
        self.ax.clear()
        style_plot_ax(self.ax)
        m = self.model
        transform, norm, cmap = preview_norm_cmap(
            m.vmax, self.app.var_log.get(), self.app.var_cmap.get())
        w_lo, w_hi = m.wl_edges
        self.ax.imshow(transform(m.E.T), aspect="auto", origin="lower", cmap=cmap,
                       norm=norm, extent=[w_lo, w_hi, m.t_lo, m.t_hi],
                       interpolation="nearest")
        shade_wl_masks(self.ax, m.masks, w_lo, w_hi)
        self.ax.set_xlim(w_lo, w_hi)
        self.ax.set_ylim(m.t_lo, m.t_hi)
        self.ax.set_xlabel("Wavelength (nm)", fontsize=9)
        self.ax.set_ylabel("Time (ps)", fontsize=9)
        self.canvas.draw_idle()

    def _refresh_list(self):
        self.listbox.delete(0, "end")
        for lo, hi in self.model.masks:
            self.listbox.insert("end", f"{lo:.1f} - {hi:.1f} nm")

    def _on_click(self, event):
        if event.inaxes is not self.ax or event.xdata is None:
            return
        wl = float(event.xdata)
        if not self._pick_hi:
            self.var_lo.set(f"{wl:.1f}")
            self._pick_hi = True
            self.var_info.set("Now click the To (end) wavelength.")
        else:
            self.var_hi.set(f"{wl:.1f}")
            self._pick_hi = False
            self.var_info.set("Press Add region (or click to re-pick From).")

    def _add(self):
        try:
            lo = float(self.var_lo.get())
            hi = float(self.var_hi.get())
        except ValueError:
            messagebox.showwarning("Invalid range",
                                   "Enter numeric From / To wavelengths.",
                                   parent=self.win)
            return
        if hi < lo:
            lo, hi = hi, lo
        if hi <= lo:
            messagebox.showwarning("Invalid range",
                                   "From must differ from To.", parent=self.win)
            return
        self.model.masks.append((lo, hi))
        self._commit()
        self._pick_hi = False
        self.var_info.set(f"masked {lo:.1f}-{hi:.1f} nm - pick the next region")

    def _remove(self):
        sel = list(self.listbox.curselection())
        if not sel:
            return
        for i in sorted(sel, reverse=True):
            if 0 <= i < len(self.model.masks):
                self.model.masks.pop(i)
        self._commit()

    def _clear(self):
        if not self.model.masks:
            return
        self.model.masks = []
        self._commit()

    def _commit(self):
        self.model.rebuild()
        self.app.redraw(full=True)
        self._draw()
        self._refresh_list()
