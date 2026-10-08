"""The Crop window (crop box, solvent subtraction, time slices, zoom)."""
import time

import numpy as np

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from matplotlib.gridspec import GridSpec
from matplotlib.patches import Rectangle
from matplotlib.ticker import EngFormatter, LogFormatterSciNotation, MaxNLocator

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from ..phu import read_phu
from ..util import short_name, solvent_mismatch
from ..model import TRESModel
from ..theme import ACCENT, BG, INK, INK_DIM, INK_FAINT, LINE, PANEL, PIN, preview_norm_cmap, style_plot_ax
from .common import _AnalysisDialog


class CropDialog(_AnalysisDialog):
    """Pick a rectangular (wavelength, time) window to keep.

    The whole-dataset heatmap is drawn once; editing the range only nudges the
    lightweight rectangle / dim overlays (debounced ~130 ms), the same
    cheap-overlay pattern the TA analyzer's crop window uses so the dialog stays
    responsive on a big map. Time is in ps from the record start (like the main
    TIME SPAN box), independent of any "t0 at IRF peak" display shift.

    The window also holds the solvent subtraction: load a pure-solvent .phu
    taken on the same grid, then move SCALE until its signal is gone. The
    heatmap shows the whole record minus scale x solvent, and the panel below
    it the steady-state spectrum before, the scaled solvent, and after - all
    a preview until Apply, which hands crop and solvent to the live model.

    Over those (faded) steady-state lines the same panel draws one time bin of
    the map in bold, on a right-hand scale of its own: the sample, the scaled
    solvent and their difference at the delay under the pointer. Double-click
    the map to pin that delay, double-click again to let it follow the mouse.

    The map can be looked at more closely without touching any of the above:
    the wheel zooms about the pointer (Ctrl: time only, Shift: wavelength
    only), a right-button drag moves the view, and the VIEW row switches the
    colour and the time axis between linear and log. All of it is forgotten
    when the window closes.
    """

    ZOOM_STEP = 1.25        # per wheel notch

    def __init__(self, app):
        super().__init__(app, "Crop data", "1000x920", (780, 680))
        m = self.model
        # An uncropped, unmasked copy for the preview so the user always sees
        # the full sweep they are selecting from, whatever crop is already live.
        self._full = TRESModel(m.phu)
        self._full.first_is_irf = m.first_is_irf
        self._full.rebin = m.rebin
        self._full.wl_offset = m.wl_offset
        self._full.bg_sub = False          # raw counts, not background-subtracted
        self._full.t0_align = False         # raw time axis, matches t_min/t_max
        self._full.rebuild()
        # The colour scale stays on the unsubtracted map, read here before any
        # solvent reaches _full: the solvent then visibly drops out of the
        # picture instead of the scale following it down.
        self._vmax0 = self._full.vmax
        self._full_key = None       # (solvent, scale) the heatmap is showing
        # ... and so does this: the sample's own raw counts on the heatmap's
        # grid, for the time-slice spectra. rebuild() makes a new E_raw each
        # time, so the array kept here is never the one a solvent is taken from.
        self._raw0 = self._full.E_raw
        self._slice_ti = None       # time bin whose spectrum is drawn, if any
        self._slice_pinned = False  # held by a double-click, else it follows the mouse
        self._pin_time = -np.inf    # when it was last toggled (triple-click guard)
        self._click_undo = None     # crop state before the latest single click

        # Steady-state preview: a second model, set up for every redraw exactly
        # as Apply would leave the live one, so its spectrum is the one the
        # main window shows afterwards.
        self._pv = TRESModel(m.phu)

        # the solvent picked in this window and its scale - a preview until Apply
        self._solvent = m.solvent
        self._scale = float(m.solvent_scale)
        self._busy = False          # guards the slider <-> entry round trip

        wls = self._full.wls
        self.wl_full = (float(wls.min()), float(wls.max()))
        self.t_full = (0.0, float(self._full.t_hi))

        cw = m.crop_wl if m.crop_wl is not None else self.wl_full
        wl0, wl1 = sorted(cw)
        t0 = max(m.t_min_ps, self.t_full[0])
        t1 = min(m.t_max_ps, self.t_full[1])
        self.var_wl_lo = tk.StringVar(value=f"{wl0:g}")
        self.var_wl_hi = tk.StringVar(value=f"{wl1:g}")
        self.var_t_lo = tk.StringVar(value=f"{t0:g}")
        self.var_t_hi = tk.StringVar(value=f"{t1:g}")
        self.var_info = tk.StringVar(value="")
        self.var_scale = tk.StringVar(value=f"{self._scale:g}")
        self.var_solv_name = tk.StringVar(value="")
        self._seen_t = (m.t_min_ps, m.t_max_ps)     # the model's range the boxes started from
        self._overlay = []      # transient rectangle / dim patches
        self._after = None      # debounce handle
        self._corner = None     # first click of a two-click rectangle pick

        # how the map is looked at - none of it reaches the crop or the model.
        # The colour scale starts as the main window has it and then goes its
        # own way.
        self.var_zlog = tk.BooleanVar(value=bool(app.var_log.get()))
        self.var_auto = tk.BooleanVar(value=False)   # colour range from the view
        self.var_tlog = tk.BooleanVar(value=False)   # log time axis
        self._pan = None        # right-button drag: (x, y in pixels, xlim, ylim) at its start

        self._build_ui()
        self.win.bind("<Escape>", lambda ev: self._cancel_corner())
        self._draw_base()
        self._update_overlay()

    def model_changed(self):
        """BIN, OFFSET or the IRF checkbox changed in the main window: the map
        shown here is built with them, so build it again. An offset moves the
        range in the boxes with it, so that it keeps framing the same curves."""
        m, f = self.model, self._full
        now = (m.first_is_irf, m.rebin, m.wl_offset)
        if now != (f.first_is_irf, f.rebin, f.wl_offset):
            delta = m.wl_offset - f.wl_offset
            was = (f.first_is_irf, f.rebin, f.wl_offset)
            f.first_is_irf, f.rebin, f.wl_offset = now
            f.solvent, f.solvent_sub = None, False
            f.rebuild()
            self._vmax0 = f.vmax
            self._raw0 = f.E_raw
            self._full_key = None               # the heatmap is rebuilt below
            self.wl_full = (float(f.wls.min()), float(f.wls.max()))
            self.t_full = (0.0, float(f.t_hi))
            self._corner = None
            self._slice_ti, self._slice_pinned = None, False   # its time bins changed
            w_lo, w_hi = f.wl_edges
            self._base_im.set_extent([w_lo, w_hi, f.t_lo, f.t_hi])
            self._recolor()
            if delta or now[0] != was[0]:       # the wavelength axis itself moved
                self._fit_view()
        # The boxes keep their numbers on an OFFSET change - so does the
        # model's crop, which is quoted in displayed nm - and now show what
        # they frame on the new axis. A new time range of the main window
        # (TIME SPAN) is taken over: it is the same setting as "t ... to".
        if (m.t_min_ps, m.t_max_ps) != self._seen_t:
            self._seen_t = (m.t_min_ps, m.t_max_ps)
            self.var_t_lo.set(f"{max(m.t_min_ps, self.t_full[0]):g}")
            self.var_t_hi.set(f"{min(m.t_max_ps, self.t_full[1]):g}")
        self._update_overlay()

    # -- layout ----------------------------------------------------------
    def _build_ui(self):
        top = ttk.Frame(self.win, padding=(8, 8, 8, 4))
        top.pack(fill="x")

        def field(var):
            e = ttk.Entry(top, textvariable=var, width=8, font=("TkFixedFont", 9))
            e.pack(side="left", padx=2)
            e.bind("<KeyRelease>", lambda ev: self._on_typed())
            e.bind("<Return>", lambda ev: self._update_overlay())
            return e

        ttk.Label(top, text="λ").pack(side="left")
        field(self.var_wl_lo)
        ttk.Label(top, text="to").pack(side="left", padx=2)
        field(self.var_wl_hi)
        ttk.Label(top, text="nm").pack(side="left", padx=(2, 4))
        ttk.Button(top, text="Full λ", width=6,
                   command=self._full_wl).pack(side="left", padx=(0, 16))

        ttk.Label(top, text="t").pack(side="left")
        field(self.var_t_lo)
        ttk.Label(top, text="to").pack(side="left", padx=2)
        field(self.var_t_hi)
        ttk.Label(top, text="ps").pack(side="left", padx=(2, 4))
        ttk.Button(top, text="Full t", width=6,
                   command=self._full_t).pack(side="left")

        # -- solvent: file + scale. The slider covers 0-2; the entry takes any
        #    value >= 0, so a larger factor can still be typed.
        srow = ttk.Frame(self.win, padding=(8, 0, 8, 4))
        srow.pack(fill="x")
        ttk.Label(srow, text="SOLVENT").pack(side="left", padx=(0, 6))
        ttk.Button(srow, text="Load solvent...",
                   command=self._load_solvent).pack(side="left")
        ttk.Button(srow, text="Clear", width=6,
                   command=self._clear_solvent).pack(side="left", padx=(6, 8))
        ttk.Label(srow, textvariable=self.var_solv_name, style="Val.TLabel",
                  foreground=PIN).pack(side="left", padx=(0, 12))
        ttk.Label(srow, text="SCALE").pack(side="left", padx=(0, 5))
        self.scale = ttk.Scale(srow, from_=0.0, to=2.0, length=150,
                               command=self._on_slider)
        self.scale.pack(side="left")
        self.ent_scale = ttk.Entry(srow, textvariable=self.var_scale, width=7,
                                   font=("TkFixedFont", 9))
        self.ent_scale.pack(side="left", padx=(6, 0))
        self.ent_scale.bind("<Return>", lambda ev: self._on_scale_entry())
        self.ent_scale.bind("<FocusOut>", lambda ev: self._on_scale_entry())
        self._set_scale(self._scale)
        self._sync_solvent_controls()

        # -- view: how the map is drawn, nothing more
        vrow = ttk.Frame(self.win, padding=(8, 0, 8, 4))
        vrow.pack(fill="x")
        ttk.Label(vrow, text="VIEW").pack(side="left", padx=(0, 6))
        ttk.Checkbutton(vrow, text="Log color", variable=self.var_zlog,
                        command=self._on_color).pack(side="left")
        ttk.Checkbutton(vrow, text="Auto color", variable=self.var_auto,
                        command=self._on_color).pack(side="left", padx=(8, 0))
        ttk.Checkbutton(vrow, text="Log time", variable=self.var_tlog,
                        command=self._on_tscale).pack(side="left", padx=(8, 0))
        ttk.Button(vrow, text="Fit", width=6,
                   command=self._fit_view).pack(side="left", padx=(12, 0))
        ttk.Label(vrow, text="wheel zooms (Ctrl: time, Shift: λ)  |  right-drag moves",
                  foreground=INK_FAINT).pack(side="left", padx=(12, 0))

        # the buttons first, at the bottom: packed after the figure they were
        # the first thing a short window squeezed out
        bar = ttk.Frame(self.win, padding=(8, 4, 8, 8))
        bar.pack(side="bottom", fill="x")
        ttk.Button(bar, text="Close", command=self._on_close).pack(side="right")
        ttk.Button(bar, text="Reset (full)",
                   command=self._reset).pack(side="right", padx=6)
        ttk.Button(bar, text="Apply", command=self._apply).pack(side="right")
        # what Apply would keep, then the tip: the tip is what gives way
        ttk.Label(bar, textvariable=self.var_info,
                  foreground=INK_DIM).pack(side="right", padx=12)
        ttk.Label(bar, text="tip: click two opposite corners on the map to set the box"
                            "  |  double-click pins the spectrum at that time",
                  foreground=INK_FAINT).pack(side="left")

        self.fig = Figure(figsize=(8.8, 6.6), dpi=100, facecolor=PANEL)
        gs = GridSpec(2, 1, figure=self.fig, height_ratios=[3.0, 1.3],
                      left=0.09, right=0.915, top=0.975, bottom=0.085, hspace=0.07)
        self.ax = self.fig.add_subplot(gs[0])
        self.ax_ss = self.fig.add_subplot(gs[1], sharex=self.ax)
        style_plot_ax(self.ax)
        style_plot_ax(self.ax_ss)
        # right-hand scale of the lower panel, for the spectrum of one time bin:
        # a single bin holds hundreds of times fewer counts than the sum over all
        self.ax_t = self.ax_ss.twinx()
        for s in self.ax_t.spines.values():
            s.set_color(LINE)
        self.ax_t.tick_params(colors=INK_FAINT, labelsize=8, length=3)
        self.ax_t.yaxis.label.set_color(INK_FAINT)
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.win)
        self.canvas.get_tk_widget().pack(fill="both", expand=True, padx=8, pady=4)
        self.canvas.mpl_connect("button_press_event", self._on_click)
        self.canvas.mpl_connect("motion_notify_event", self._on_motion)
        # two ways off the map: onto another part of the figure (matplotlib
        # reports the axes left) or straight out of the canvas (it only
        # reports the figure left)
        self.canvas.mpl_connect("axes_leave_event", self._on_leave)
        self.canvas.mpl_connect("figure_leave_event", self._on_leave)
        self.canvas.mpl_connect("scroll_event", self._on_scroll)
        self.canvas.mpl_connect("button_release_event", self._on_release)

    # -- preview ---------------------------------------------------------
    def _draw_base(self):
        f = self._full
        self._transform, norm, cmap = preview_norm_cmap(
            self._vmax0, self.var_zlog.get(), self.app.var_cmap.get())
        w_lo, w_hi = f.wl_edges
        self._base_im = self.ax.imshow(
            self._transform(f.E.T), aspect="auto", origin="lower", cmap=cmap,
            norm=norm, extent=[w_lo, w_hi, f.t_lo, f.t_hi],
            # the map has several time bins per screen pixel (and far more on
            # a log axis): average them, in data space, instead of showing one
            # in a few - a narrow late feature would otherwise not be drawn
            interpolation="antialiased", interpolation_stage="data")
        self.ax.set_xlim(w_lo, w_hi)
        self.ax.set_ylim(0.0, self.t_full[1])
        self.ax.set_ylabel("Time (ps from record start)", fontsize=9)
        self.ax.tick_params(labelbottom=False)

        # steady state of the kept box: the sample as it is, the scaled solvent,
        # and what is left - _update_preview() fills the three in
        #    Half transparent: they are the backdrop for the bold time slice.
        ax = self.ax_ss
        (self.ln_sample,) = ax.plot([], [], color=INK_DIM, lw=1.2, alpha=0.5,
                                    label="sample")
        (self.ln_solv,) = ax.plot([], [], color=PIN, lw=1.0, ls=":", alpha=0.5,
                                  label="s x solvent")
        (self.ln_sub,) = ax.plot([], [], color=ACCENT, lw=1.6, alpha=0.5,
                                 label="subtracted")
        ax.axhline(0.0, color=LINE, lw=0.6)
        ax.set_xlim(w_lo, w_hi)
        ax.set_xlabel("Wavelength (nm)", fontsize=9)
        ax.set_ylabel("Counts (all delays)", fontsize=9)
        ax.yaxis.set_major_locator(MaxNLocator(4))
        ax.yaxis.set_major_formatter(EngFormatter(places=0, sep=""))
        ax.grid(alpha=0.12, lw=0.5, color=INK_FAINT)

        # one time bin of the map above, in the colours of the steady-state
        # lines it sits on: raw counts like the heatmap, and the difference
        # left unclipped, so an over-subtraction dips below zero
        at = self.ax_t
        (self.ln_t_sample,) = at.plot([], [], color=INK_DIM, lw=2.2, label="sample")
        (self.ln_t_solv,) = at.plot([], [], color=PIN, lw=2.2, label="s x solvent")
        (self.ln_t_sub,) = at.plot([], [], color=ACCENT, lw=2.2, label="difference")
        at.set_ylabel("Counts (at t)", fontsize=9)
        at.yaxis.set_major_locator(MaxNLocator(4))
        at.yaxis.set_major_formatter(EngFormatter(places=0, sep=""))
        # the delay those come from, marked on the map
        self.hl_t = self.ax.axhline(np.nan, color="w", lw=0.9, ls="--", zorder=7)
        self._draw_slice()
        self.canvas.draw_idle()

    def _time_bin(self, t_ps):
        """Index of the heatmap's time bin that holds ``t_ps`` (from record start)."""
        return int(np.clip(t_ps // self._full.dt_ps, 0, self._full.n_t - 1))

    def _draw_slice(self):
        """Fill in the bold spectra of time bin _slice_ti, or hide them."""
        ti, has = self._slice_ti, self._solvent is not None
        lines = (self.ln_t_sample, self.ln_t_solv, self.ln_t_sub)
        shown = () if ti is None else lines if has else lines[:1]
        for ln in lines:
            ln.set_visible(ln in shown)
        self.hl_t.set_visible(ti is not None)
        if ti is None:
            leg = self.ax_t.get_legend()
            if leg is not None:
                leg.remove()
            return

        f = self._full
        sample = self._raw0[:, ti]
        self.ln_t_sample.set_data(f.wls, sample)
        if has:
            scaled = self._scale * f.S_raw[:, ti]
            self.ln_t_solv.set_data(f.wls, scaled)
            self.ln_t_sub.set_data(f.wls, sample - scaled)
        self._fit_y(self.ax_t, lines)

        t = (ti + 0.5) * f.dt_ps
        self.hl_t.set_ydata([t, t])
        self.hl_t.set_linestyle("-" if self._slice_pinned else "--")
        self.hl_t.set_color(PIN if self._slice_pinned else "w")
        leg = self.ax_t.legend(
            handles=list(shown), loc="upper left", fontsize=7.5, frameon=False, ncol=3,
            title=f"t = {t:,.0f} ps" + ("  (pinned)" if self._slice_pinned else ""),
            title_fontsize=8, alignment="left")
        for txt in (*leg.get_texts(), leg.get_title()):
            txt.set_color(INK)

    def _update_preview(self, box):
        """Redraw what the solvent subtraction would give, without applying it.

        The heatmap is the whole record minus scale x solvent in raw counts,
        like the map it replaces; it is only recomputed when the solvent or
        the scale changed. The spectra come from _pv, configured by the same
        _configure() Apply uses, so "subtracted" is the steady-state panel of
        the main window after Apply. Returns the share of bins clipped to 0.
        """
        sv = self._solvent
        key = (id(sv), self._scale) if sv is not None else None
        if key != self._full_key:
            f = self._full
            f.solvent, f.solvent_scale, f.solvent_sub = sv, self._scale, sv is not None
            f.rebuild()
            self._full_key = key
            self._recolor()

        pv = self._pv
        pv.copy_settings_from(self.model)
        self._configure(pv, box, sub=False)
        pv.rebuild()
        self.ln_sample.set_data(pv.wls, pv.spec_total)
        if sv is not None:
            pv.solvent_sub = True
            pv.rebuild()
            self.ln_solv.set_data(pv.wls, self._scale * pv.solvent_spectrum())
            self.ln_sub.set_data(pv.wls, pv.spec_total)
        shown = [self.ln_sample]
        for ln in (self.ln_solv, self.ln_sub):
            ln.set_visible(sv is not None)
            if sv is not None:
                shown.append(ln)
        self._fit_y(self.ax_ss, shown)
        leg = self.ax_ss.legend(handles=shown, loc="upper right", fontsize=7.5,
                                frameon=False, ncol=3, title="steady state",
                                title_fontsize=8, alignment="right")
        for txt in (*leg.get_texts(), leg.get_title()):
            txt.set_color(INK_DIM)
        self._draw_slice()          # a pinned slice follows the scale as well
        return pv.clip_frac if sv is not None else None

    def _on_typed(self):
        self._corner = None         # a typed range replaces a half-picked box
        self._schedule()

    def _cancel_corner(self):
        """Esc: forget a first corner that was clicked."""
        if self._corner is not None:
            self._corner = None
            self._update_overlay()  # puts the range back into the info line

    def _schedule(self):
        if self._after is not None:
            self.win.after_cancel(self._after)
        self._after = self.win.after(130, self._update_overlay)

    def _update_overlay(self):
        self._after = None
        if not self.alive:          # a pending timer can outlive the window
            return
        for art in self._overlay:
            art.remove()
        self._overlay = []
        wl_lo, wl_hi, t_lo, t_hi = self._read()
        # on a log time axis the map starts above 0, and so does what is drawn
        # of a box that reaches down to 0
        (w_lo, w_hi), (y_lo, y_hi) = self._view_full()
        dim = dict(facecolor=BG, alpha=0.55, lw=0, zorder=3)
        if wl_lo > w_lo:
            self._overlay.append(self.ax.axvspan(w_lo, wl_lo, **dim))
        if wl_hi < w_hi:
            self._overlay.append(self.ax.axvspan(wl_hi, w_hi, **dim))
        if t_lo > y_lo:
            self._overlay.append(self.ax.axhspan(y_lo, t_lo, **dim))
        if t_hi < y_hi:
            self._overlay.append(self.ax.axhspan(t_hi, y_hi, **dim))
        r_lo = max(t_lo, y_lo)
        rect = Rectangle((wl_lo, r_lo), wl_hi - wl_lo, t_hi - r_lo, fill=False,
                         edgecolor=ACCENT, lw=1.6, zorder=6)
        self.ax.add_patch(rect)
        self._overlay.append(rect)
        clipped = self._update_preview((wl_lo, wl_hi, t_lo, t_hi))
        n = self._curves_in(wl_lo, wl_hi)
        kept = (f"keep {n} curve{'' if n == 1 else 's'}" if n
                else "NO CURVE in this range - nothing to keep")
        self.var_info.set(f"{kept},  {wl_lo:g}-{wl_hi:g} nm,  "
                          f"{t_lo:g}-{t_hi:g} ps"
                          + ("" if clipped is None else f",  clipped {clipped:.0%}"))
        self.canvas.draw_idle()

    def _curves_in(self, wl_lo, wl_hi):
        """How many curves a wavelength range keeps - counted as the model
        selects them (TRESModel.rebuild), tolerance included."""
        wls = self._full.wls
        return int(((wls >= wl_lo - 1e-6) & (wls <= wl_hi + 1e-6)).sum())

    # -- view: zoom, colour and time scale ---------------------------------
    def _view_full(self):
        """((wl_lo, wl_hi), (t_lo, t_hi)) of the whole map.

        A log time axis has no 0: there the map starts in the middle of the
        first time bin.
        """
        t_lo = 0.5 * self._full.dt_ps if self.var_tlog.get() else 0.0
        return self._full.wl_edges, (t_lo, self.t_full[1])

    def _fit_y(self, ax, lines):
        """Scale ``ax`` to what the visible ``lines`` show in the wavelengths in view."""
        x0, x1 = self.ax.get_xlim()
        vals = [np.empty(0)]
        for ln in lines:
            if ln.get_visible():
                x, y = (np.asarray(a, float) for a in ln.get_data())
                vals.append(y[(x >= x0) & (x <= x1)])
        vals = np.concatenate(vals)
        vals = vals[np.isfinite(vals)]
        lo = min(float(vals.min()), 0.0) if vals.size else 0.0
        hi = max(float(vals.max()), 1.0) if vals.size else 1.0
        pad = 0.08 * (hi - lo)
        ax.set_ylim(lo - pad, hi + pad)

    def _view_max(self):
        """Largest count among the map cells that are in view, 0 if there is none."""
        f = self._full
        (w_lo, w_hi), (x0, x1), (y0, y1) = f.wl_edges, self.ax.get_xlim(), self.ax.get_ylim()
        dw = (w_hi - w_lo) / f.n_w
        i0 = int(np.clip(np.floor((x0 - w_lo) / dw), 0, f.n_w - 1))
        i1 = int(np.clip(np.ceil((x1 - w_lo) / dw), i0 + 1, f.n_w))
        j0 = int(np.clip(np.floor(y0 / f.dt_ps), 0, f.n_t - 1))
        j1 = int(np.clip(np.ceil(y1 / f.dt_ps), j0 + 1, f.n_t))
        block = f.E[i0:i1, j0:j1]
        block = block[np.isfinite(block)]
        return float(block.max()) if block.size else 0.0

    def _recolor(self):
        """Give the map its colour scale: linear or log, up to the maximum of
        the whole unsubtracted map or, with Auto color, of the part in view."""
        vmax = self._view_max() if self.var_auto.get() else self._vmax0
        self._transform, norm, _ = preview_norm_cmap(
            vmax, self.var_zlog.get(), self.app.var_cmap.get())
        self._base_im.set_norm(norm)
        self._base_im.set_data(self._transform(self._full.E.T))

    def _set_view(self, xlim, ylim):
        """Show that part of the map; the panel below shares the wavelength range."""
        self.ax.set_xlim(*xlim)
        self.ax.set_ylim(*ylim)
        if self.var_auto.get():
            self._recolor()
        self._fit_y(self.ax_ss, (self.ln_sample, self.ln_solv, self.ln_sub))
        self._fit_y(self.ax_t, (self.ln_t_sample, self.ln_t_solv, self.ln_t_sub))
        self.canvas.draw_idle()

    def _fit_view(self):
        self._set_view(*self._view_full())

    def _on_color(self):
        self._recolor()
        self.canvas.draw_idle()

    def _on_tscale(self):
        """Switch the time axis between linear and log, keeping the range in view."""
        y0, y1 = self.ax.get_ylim()
        self.ax.set_yscale("log" if self.var_tlog.get() else "linear")
        if self.var_tlog.get():
            # zoomed in there may be no full decade in view: label 2, 5 ... too
            self.ax.yaxis.set_minor_formatter(LogFormatterSciNotation(
                labelOnlyBase=False, minor_thresholds=(2.5, 1.0)))
            self.ax.tick_params(axis="y", which="minor", colors=INK_FAINT, labelsize=7)
        f_lo, f_hi = self._view_full()[1]
        if y0 <= 0.5 * self._full.dt_ps:    # was at the bottom: stay there
            y0 = f_lo
        self.ax.set_ylim(y0, min(y1, f_hi))
        self._update_overlay()              # the box is drawn from the axis bottom

    def _moved(self, lim, full, log, k=1.0, at=None, shift=0.0):
        """``lim`` scaled by ``k`` about ``at`` and moved by ``shift`` of its
        width, kept inside ``full``. On a log axis all of that is done in decades,
        so the point under the pointer stays where it is."""
        to, back = (np.log10, lambda v: 10.0 ** v) if log else (float, float)
        lo, hi, f_lo, f_hi = to(lim[0]), to(lim[1]), to(full[0]), to(full[1])
        c = lo if at is None else to(at)
        lo, hi = c - (c - lo) * k, c + (hi - c) * k
        lo, hi = lo + shift * (hi - lo), hi + shift * (hi - lo)
        width = hi - lo
        if width >= f_hi - f_lo:
            return full
        if lo < f_lo:               # pushed back in, that end exactly on the edge
            return full[0], float(back(f_lo + width))
        if hi > f_hi:
            return float(back(f_hi - width)), full[1]
        return max(float(back(lo)), full[0]), min(float(back(hi)), full[1])

    def _zoomed(self, lim, full, log, step, at, least):
        """``lim`` after ``step`` wheel notches about ``at``. Zooming in stops
        at ``least``: a step that would go below it is cut back to the part
        that fits. Zooming out is never held back - a drag on the log axis can
        leave a view narrower than ``least``, and the wheel must get out of it."""
        def after(notches):
            return self._moved(lim, full, log, self.ZOOM_STEP ** -notches, at)

        new = after(step)
        if step <= 0 or new[1] - new[0] >= least:
            return new
        fits, over, best = 0.0, step, lim
        for _ in range(12):         # bisect between no step and the whole one
            part = 0.5 * (fits + over)
            new = after(part)
            if new[1] - new[0] >= least:
                fits, best = part, new
            else:
                over = part
        return best

    def _on_scroll(self, event):
        """Wheel over the map: zoom about the pointer. Ctrl zooms the time axis
        only, Shift the wavelength axis only."""
        if (event.inaxes is not self.ax or event.xdata is None
                or self._pan is not None):      # a drag owns the view until released
            return
        f = self._full
        step = float(np.clip(event.step, -20, 20))  # a free-spinning wheel sends many at once
        xlim, ylim = self.ax.get_xlim(), self.ax.get_ylim()
        full_x, full_y = self._view_full()
        if "ctrl" not in event.modifiers:           # never closer than two curves ...
            xlim = self._zoomed(xlim, full_x, False, step, event.xdata,
                                2 * (full_x[1] - full_x[0]) / f.n_w)
        if "shift" not in event.modifiers:          # ... or four time bins
            ylim = self._zoomed(ylim, full_y, self.var_tlog.get(), step, event.ydata,
                                4 * f.dt_ps)
        self._set_view(xlim, ylim)

    def _on_release(self, event):
        if event.button == 3:
            self._pan = None

    # -- helpers ---------------------------------------------------------
    def _read(self):
        def val(var, default):
            try:
                v = float(var.get())
            except ValueError:
                return default
            return v if np.isfinite(v) else default     # "nan", "inf" are no range
        wl_lo, wl_hi = sorted((val(self.var_wl_lo, self.wl_full[0]),
                               val(self.var_wl_hi, self.wl_full[1])))
        t_lo, t_hi = sorted((val(self.var_t_lo, self.t_full[0]),
                             val(self.var_t_hi, self.t_full[1])))
        wl_lo = max(wl_lo, self.wl_full[0])
        wl_hi = min(wl_hi, self.wl_full[1])
        t_lo = max(t_lo, self.t_full[0])
        t_hi = min(t_hi, self.t_full[1])
        if wl_hi <= wl_lo:
            wl_lo, wl_hi = self.wl_full
        if t_hi <= t_lo:
            t_lo, t_hi = self.t_full
        return wl_lo, wl_hi, t_lo, t_hi

    def _crop_state(self):
        return (self._corner, self.var_wl_lo.get(), self.var_wl_hi.get(),
                self.var_t_lo.get(), self.var_t_hi.get(), self.var_info.get())

    def _undo_click(self, before):
        """Take back what the single click just before did to the crop box.

        A double-click arrives as a single click followed by the double one,
        so by then its first half has already been read as a crop corner.
        ``before`` is the crop state that click found, or None if it missed
        the map.
        """
        if before is None:
            return
        box_changed = before[1:5] != self._crop_state()[1:5]
        self._corner = before[0]
        for var, value in zip((self.var_wl_lo, self.var_wl_hi,
                               self.var_t_lo, self.var_t_hi), before[1:5]):
            var.set(value)
        if box_changed:
            self._update_overlay()
        self.var_info.set(before[5])

    def _on_motion(self, event):
        """Unpinned, the time slice follows the pointer over the map.

        With the right button held the map follows it instead.
        """
        # a release that never arrived (the window lost the mouse meanwhile)
        # must not leave the map stuck to the pointer. matplotlib >= 3.10
        # reports the buttons held during a move; before that Tk's own event
        # says it (0x400: button 3 down)
        held = getattr(event, "buttons", None)
        if held is None:
            state = getattr(event.guiEvent, "state", None)
            if isinstance(state, int):
                held = (3,) if state & 0x400 else ()
        if held is not None and 3 not in held:
            self._pan = None
        if self._pan is not None:
            x, y, xlim, ylim = self._pan
            full_x, full_y = self._view_full()
            box = self.ax.bbox
            self._set_view(
                self._moved(xlim, full_x, False, shift=(x - event.x) / box.width),
                self._moved(ylim, full_y, self.var_tlog.get(),
                            shift=(y - event.y) / box.height))
            return
        if self._slice_pinned or event.inaxes is not self.ax or event.ydata is None:
            return
        ti = self._time_bin(event.ydata)
        if ti != self._slice_ti:
            self._slice_ti = ti
            self._draw_slice()
            self.canvas.draw_idle()

    def _on_leave(self, event):
        """The pointer left the map (or the whole figure): drop an unpinned slice."""
        if event.name == "axes_leave_event" and event.inaxes is not self.ax:
            return
        if not self._slice_pinned and self._slice_ti is not None:
            self._slice_ti = None
            self._draw_slice()
            self.canvas.draw_idle()

    def _on_click(self, event):
        if event.button != 1:       # the right button drags the view, no more
            if event.button == 3 and event.inaxes is self.ax:
                self._pan = (event.x, event.y, self.ax.get_xlim(), self.ax.get_ylim())
            return
        if self._pan is not None:   # a left click in the middle of a drag
            return
        # only the click directly before a double-click may be taken back
        undo, self._click_undo = self._click_undo, None
        if event.inaxes is not self.ax or event.xdata is None:
            return
        if event.dblclick:          # pin / release the time slice, crop untouched
            self._undo_click(undo)
            # Tk reports the third press of a triple click as a double one
            # again, which would undo the toggle the second press just made
            if time.monotonic() - self._pin_time < 0.5:
                return
            self._pin_time = time.monotonic()
            self._slice_pinned = not self._slice_pinned
            self._slice_ti = self._time_bin(event.ydata)
            self._draw_slice()
            self.canvas.draw_idle()
            return
        self._click_undo = self._crop_state()
        x = float(np.clip(event.xdata, *self.wl_full))
        y = float(np.clip(event.ydata, *self.t_full))
        if self._corner is None:
            self._corner = (x, y)
            self.var_info.set(f"corner at {x:.0f} nm, {y:.0f} ps - click the opposite one")
        else:
            x0, y0 = self._corner
            self._corner = None
            self.var_wl_lo.set(f"{min(x0, x):g}")
            self.var_wl_hi.set(f"{max(x0, x):g}")
            self.var_t_lo.set(f"{min(y0, y):g}")
            self.var_t_hi.set(f"{max(y0, y):g}")
            self._update_overlay()

    def _full_wl(self):
        self._corner = None
        self.var_wl_lo.set(f"{self.wl_full[0]:g}")
        self.var_wl_hi.set(f"{self.wl_full[1]:g}")
        self._update_overlay()

    def _full_t(self):
        self._corner = None
        self.var_t_lo.set(f"{self.t_full[0]:g}")
        self.var_t_hi.set(f"{self.t_full[1]:g}")
        self._update_overlay()

    # -- solvent ---------------------------------------------------------
    def _sync_solvent_controls(self):
        """File-name label and SCALE widgets follow whether a solvent is loaded."""
        loaded = self._solvent is not None
        self.var_solv_name.set(short_name(self._solvent["path"]) if loaded
                               else "none")
        self.scale.state(["!disabled"] if loaded else ["disabled"])
        self.ent_scale.configure(state="normal" if loaded else "disabled")

    def _set_scale(self, v, from_slider=False):
        """Take ``v`` as the scale and mirror it into the entry and the slider.

        Setting a ttk.Scale fires its command, so _busy keeps that from coming
        back in as a slider move; a value past the slider's range parks it at 2.
        """
        self._scale = v
        self.var_scale.set(f"{v:g}")
        if not from_slider:
            self._busy = True
            try:
                self.scale.set(min(v, 2.0))
            finally:
                self._busy = False

    def _on_slider(self, value):
        if self._busy:
            return
        v = round(float(value), 2)      # the widget reports 0.8532110091743119
        if v != self._scale:
            self._set_scale(v, from_slider=True)
            self._schedule()

    def _on_scale_entry(self):
        """Read the SCALE box; anything but a finite number >= 0 is put back."""
        if not self.alive:
            return
        try:
            v = float(self.var_scale.get())
        except ValueError:
            v = None
        if v is None or not np.isfinite(v) or v < 0:
            self.var_scale.set(f"{self._scale:g}")
            return
        if v != self._scale:
            self._set_scale(v)
            self._update_overlay()

    def _load_solvent(self):
        """Pick the solvent .phu; it is only taken if it sits on the sample's grid."""
        path = filedialog.askopenfilename(
            parent=self.win, title="Open the solvent measurement",
            filetypes=[("PicoQuant histogram", "*.phu"), ("All files", "*.*")])
        if not path:
            return
        try:
            solvent = read_phu(path)
        except Exception as exc:
            messagebox.showerror("Could not read file", str(exc), parent=self.win)
            return
        errors, notes = solvent_mismatch(self.model.phu, solvent)
        if errors:
            messagebox.showerror(
                "Solvent does not match the sample",
                "The solvent is subtracted bin for bin, so it has to be measured "
                "on the same grid as the sample.\n\n"
                + "\n".join(f"- {e}" for e in errors), parent=self.win)
            return
        if notes:
            messagebox.showwarning(
                "Solvent measured differently",
                "\n".join(f"- {n}" for n in notes)
                + "\n\nIt is loaded with the scale at 1 - adjust the scale to "
                  "make up for the difference.", parent=self.win)
        self._solvent = solvent
        self._sync_solvent_controls()   # enable the slider before moving it
        self._set_scale(1.0)
        self._update_overlay()

    def _clear_solvent(self):
        if self._solvent is None:
            return
        self._solvent = None
        self._set_scale(1.0)
        self._sync_solvent_controls()
        self._update_overlay()

    def _configure(self, model, box, with_solvent=True, sub=True):
        """Write this window's crop box - and solvent - into ``model``.

        The one place that maps the dialog onto a model, shared by the preview
        and by Apply so that the two cannot drift apart.
        """
        wl_lo, wl_hi, t_lo, t_hi = box
        full = (wl_lo <= self.wl_full[0] + 1e-6 and wl_hi >= self.wl_full[1] - 1e-6)
        model.crop_wl = None if full else (wl_lo, wl_hi)
        model.t_min_ps = t_lo
        model.t_max_ps = t_hi
        if with_solvent:
            model.solvent = self._solvent
            model.solvent_scale = self._scale
            model.solvent_sub = sub and self._solvent is not None

    def _reset(self):
        # the crop only: a solvent that was not applied yet stays a preview
        self._full_wl()
        self._full_t()
        self._apply(with_solvent=False)

    def _apply(self, with_solvent=True):
        self._corner = None
        self._on_scale_entry()      # a typed scale counts without Enter, too
        m = self.model
        box = self._read()
        if not self._curves_in(box[0], box[1]):
            # the model would fall back to the whole sweep while every export
            # note went on to quote this range
            messagebox.showwarning(
                "Empty range",
                f"No curve lies between {box[0]:g} and {box[1]:g} nm. "
                "Widen the wavelength range.", parent=self.win)
            return
        self._configure(m, box, with_solvent=with_solvent)
        m.rebuild()
        # keep the main viewer's TIME SPAN box and derived state consistent
        self.app.var_tmax.set(f"{m.t_max_ps:.0f}")
        self._seen_t = (m.t_min_ps, m.t_max_ps)
        self.app.clim = None
        self.app.view = None
        self.app.cursor = None
        self.app.pinned = False
        self.app.redraw(full=True)
        # a live mask window previews the (now re-cropped) map
        mw = self.app._mask_win
        if mw is not None and mw.alive:
            mw._draw()
            mw._refresh_list()
        self.var_info.set("applied")
