"""The TRES tab's figure: drawing and mouse interaction."""
import numpy as np
import tkinter as tk

import matplotlib
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.colors import LogNorm, Normalize
from matplotlib.figure import Figure
from matplotlib.gridspec import GridSpec
from matplotlib.patches import Rectangle
from matplotlib.ticker import EngFormatter, MaxNLocator

from .ui import attach_toolbar
from .util import wavelength_to_rgb
from .theme import ACCENT, BG, INK, INK_DIM, INK_FAINT, LINE, PANEL, PIN, READOUT_BG, READOUT_FG, WARN, shade_wl_masks


class _MapFigure:
    """The figure of the TRES tab - map, decay, spectrum, steady state,
    colour bar - how it is drawn, and what the mouse does on it (cursor,
    pin, zoom rectangle). Part of TRESViewer (viewer.py), which owns the
    model and the controls.
    """

    # -- figure -----------------------------------------------------------
    def _build_figure(self):
        self.fig = Figure(figsize=(14, 7.4), dpi=100, facecolor=PANEL)
        gs = GridSpec(
            3, 3, figure=self.fig,
            width_ratios=[1.0, 3.6, 0.06], height_ratios=[3.0, 0.10, 1.35],
            left=0.055, right=0.955, top=0.955, bottom=0.075,
            wspace=0.045, hspace=0.06,
        )
        self.ax_hist = self.fig.add_subplot(gs[0, 0])
        self.ax_map = self.fig.add_subplot(gs[0, 1], sharey=self.ax_hist)
        self.cax = self.fig.add_subplot(gs[0, 2])
        self.ax_rib = self.fig.add_subplot(gs[1, 1], sharex=self.ax_map)
        self.ax_ss = self.fig.add_subplot(gs[2, 0])
        self.ax_spec = self.fig.add_subplot(gs[2, 1], sharex=self.ax_map)

        for ax in (self.ax_hist, self.ax_map, self.ax_ss, self.ax_spec, self.ax_rib):
            ax.set_facecolor(BG)
            for s in ax.spines.values():
                s.set_color(LINE)
            ax.tick_params(colors=INK_FAINT, labelsize=8, length=3)
            ax.xaxis.label.set_color(INK_FAINT)
            ax.yaxis.label.set_color(INK_FAINT)
            ax.title.set_color(INK_DIM)

        self.canvas = FigureCanvasTkAgg(self.fig, master=self.parent)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)
        # matplotlib's toolbar above the figure. Home is Reset zoom; after any
        # of its moves self.view is read back from the map's limits. The colour
        # bar and the ribbon are not navigated: the bar's limits are the
        # contrast (self.clim), and the ribbon follows the map.
        self.cax.set_navigate(False)
        self.ax_rib.set_navigate(False)
        self.toolbar = attach_toolbar(self.canvas, self.parent,
                                      before=self.canvas.get_tk_widget(),
                                      on_home=self._home_view, on_nav=self._view_from_axes)

        self.canvas.mpl_connect("motion_notify_event", self.on_motion)
        self.canvas.mpl_connect("button_press_event", self.on_press)
        self.canvas.mpl_connect("button_release_event", self.on_release)
        self.canvas.mpl_connect("axes_leave_event", self.on_leave)
        self.canvas.mpl_connect("draw_event", self.on_draw)
        self.canvas.mpl_connect("resize_event", self._on_resize)
        self.canvas.get_tk_widget().bind("<Map>", self._on_map, add="+")
        self.canvas.get_tk_widget().bind("<Destroy>", self._on_canvas_destroy, add="+")

    # Room around the panels, in pixels: what their tick labels, axis labels
    # and titles need. The GridSpec's fractions suit one window size only; in
    # a small window the labels ran off the figure or under the next panel.
    PAD_PX = 6           # free space beside every label
    GAP_CBAR_PX = 18     # map -> colour bar (only ticks inside)
    GAP_RIBBON_PX = 8    # map -> spectral ribbon
    HOLD_PX = 3          # a smaller change does not move the panels
    _over = None         # what _fit_layout last measured, panel -> reach of its labels
    _relayouts = 0       # draws in a row that moved the panels
    _layout_stale = False    # the panels moved since the last draw
    _draw_queued = None      # the after_idle id of the draw that shows them

    def _fit_layout(self):
        """Place the panels so that every label and title is inside the figure
        and off the other panels, at the canvas's present size; True when they
        moved. The panels keep their arrangement and their width / height
        ratios (the GridSpec's), and their edges sit on whole pixels.

        It reads the labels as the last draw left them (on_draw calls it), so
        it costs a few milliseconds, not a second layout of every axis; when
        the panels had to move, on_draw draws once more. A new canvas size
        places them with these same numbers before it draws (_on_resize): the
        labels do not change with it, so that draw needs no second one."""
        if not self.model or not self.ax_hist.get_visible():
            return False    # the placeholder: one panel, the GridSpec places it
        fig = self.fig
        W, H = fig.bbox.width, fig.bbox.height
        if W < 50 or H < 50:
            return False
        r = self.canvas.get_renderer()

        def drawn_labels(axis):
            """The tick labels the last draw put on ``axis`` (as Axis._update_ticks
            pairs ticks with locations), and the axis label (or None)."""
            lo, hi = sorted(axis.get_view_interval())
            eps = (hi - lo) * 1e-9
            ticks_out = []
            for ticks, locs in ((axis.majorTicks, axis.get_majorticklocs()),
                                (axis.minorTicks, axis.get_minorticklocs())):
                for tick, loc in zip(ticks, locs):
                    if lo - eps <= loc <= hi + eps:
                        ticks_out += [t for t in (tick.label1, tick.label2) if t.get_visible() and t.get_text()]
            label = axis.label if axis.label.get_visible() and axis.label.get_text() else None
            return ticks_out, label

        def extents(texts):
            ext = [t.get_window_extent(r) for t in texts if t is not None]
            return [e for e in ext if e.width > 0 and e.height > 0]

        def over(ax):
            """How far the labels of ``ax`` reach beyond it: (left, right, bottom, top) px.
            What is drawn inside a panel is clipped to it.

            A tick label is taken to reach half its width (x) or height (y) past
            the panel's ends whether or not a tick sits at the end: whether one
            does changes with the panel's size, and the layout would swing."""
            b = ax.bbox
            xt, xl = drawn_labels(ax.xaxis)
            yt, yl = drawn_labels(ax.yaxis)
            xe, ye = extents(xt), extents(yt)
            titles = [t for t in (ax.title, ax._left_title, ax._right_title)
                      if t.get_visible() and t.get_text()]
            # (the "1e6" of a linear colour bar, above its top)
            offsets = [t for t in (ax.xaxis.offsetText, ax.yaxis.offsetText)
                       if t.get_visible() and t.get_text()]
            ext = xe + ye + extents([xl, yl] + titles + offsets)
            if not ext:
                return 0.0, 0.0, 0.0, 0.0
            half_w = max((e.width for e in xe), default=0.0) / 2
            half_h = max((e.height for e in ye), default=0.0) / 2
            return (max(b.x0 - min(e.x0 for e in ext), half_w, 0.0),
                    max(max(e.x1 for e in ext) - b.x1, half_w, 0.0),
                    max(b.y0 - min(e.y0 for e in ext), half_h, 0.0),
                    max(max(e.y1 for e in ext) - b.y1, half_h, 0.0))
        self._over = {name: over(getattr(self, name))
                      for name in ("ax_hist", "ax_map", "cax", "ax_rib", "ax_ss", "ax_spec")}
        return self._place_panels()

    def _place_panels(self):
        """Put the panels where the labels measured in self._over leave room;
        True when they moved."""
        fig, o = self.fig, self._over
        W, H = fig.bbox.width, fig.bbox.height
        if W < 50 or H < 50:
            return False
        p = self.PAD_PX
        left = max(o["ax_hist"][0], o["ax_ss"][0]) + p
        right = max(o["cax"][1], o["ax_spec"][1] - self.GAP_CBAR_PX - p, 0.0) + p
        top = max(o["ax_hist"][3], o["ax_map"][3], o["cax"][3]) + p
        bottom = max(o["ax_ss"][2], o["ax_spec"][2]) + p
        gap_x = (max(o["ax_hist"][1], o["ax_ss"][1])
                 + max(o["ax_map"][0], o["ax_spec"][0], o["ax_rib"][0]) + p)
        gap_cb = max(self.GAP_CBAR_PX, o["ax_map"][1] + o["cax"][0] + p)
        gap_r0 = max(self.GAP_RIBBON_PX, o["ax_map"][2] + o["ax_rib"][3] + p)
        gap_r1 = o["ax_rib"][2] + o["ax_spec"][3] + p
        avail_h = H - top - bottom - gap_r0 - gap_r1
        avail_w = W - left - right - gap_x - gap_cb
        if avail_h < 60 or avail_w < 60:
            return False
        hr = np.array([3.0, 0.10, 1.35]) / 4.45
        h_map, h_rib = hr[0] * avail_h, hr[1] * avail_h
        # the Decay panel's x labels hang into the column's empty middle row;
        # the steady-state panel starts below them
        need = o["ax_hist"][2] + o["ax_ss"][3] + p
        short = need - (gap_r0 + h_rib + gap_r1)
        if short > 0:
            gap_r1 += short
            avail_h -= short
            h_map, h_rib = hr[0] * avail_h, hr[1] * avail_h
        h_spec = hr[2] * avail_h
        wr = np.array([1.0, 3.6, 0.06]) / 4.66
        w0, w1, w2 = wr * avail_w
        x0 = left
        x1 = x0 + w0 + gap_x
        x2 = x1 + w1 + gap_cb
        y_spec = bottom
        y_rib = y_spec + h_spec + gap_r1
        y_map = y_rib + h_rib + gap_r0

        target = {self.ax_hist: (x0, y_map, w0, h_map), self.ax_map: (x1, y_map, w1, h_map),
                  self.cax: (x2, y_map, w2, h_map), self.ax_rib: (x1, y_rib, w1, h_rib),
                  self.ax_ss: (x0, y_spec, w0, h_spec), self.ax_spec: (x1, y_spec, w1, h_spec)}
        edges = {ax: (round(x), round(y), round(x + w), round(y + h)) for ax, (x, y, w, h) in target.items()}
        # Within HOLD_PX of where they are (the padding covers that) the panels
        # stay: a move can add or drop a tick label, and the layout would
        # otherwise swing between two places a pixel or two apart.
        now = {ax: tuple(ax.bbox.extents) for ax in target}
        if all(abs(a - b) <= self.HOLD_PX for ax in target for a, b in zip(edges[ax], now[ax])):
            return False
        for ax, (xa, ya, xb, yb) in edges.items():
            ax.set_position([xa / W, ya / H, (xb - xa) / W, (yb - ya) / H])
        return True

    def _on_resize(self, event):
        """The canvas has a new size and is about to be drawn at it."""
        if self.model and self._over and self.ax_hist.get_visible():
            self._place_panels()

    def _on_map(self, event):
        """The window came on screen: show the panels if they moved before it did."""
        if self._layout_stale:
            self._queue_draw()

    def _queue_draw(self):
        """Draw the moved panels once Tk is idle. Queued with Tk: a draw_idle()
        asked for during matplotlib's own idle draw (a resize) would be dropped."""
        if self._draw_queued is None:
            self._draw_queued = self.canvas.get_tk_widget().after_idle(self._draw_relaid)

    def _on_canvas_destroy(self, event):
        if self._draw_queued is not None:
            try:
                event.widget.after_cancel(self._draw_queued)
            except tk.TclError:
                pass
            self._draw_queued = None

    def _show_placeholder(self):
        for ax in (self.ax_hist, self.ax_ss, self.ax_spec, self.ax_rib, self.cax):
            ax.set_visible(False)
        self.ax_map.set_visible(True)
        self.ax_map.clear()
        self.ax_map.set_facecolor(BG)
        self.ax_map.set_xticks([])
        self.ax_map.set_yticks([])
        self.ax_map.text(
            0.5, 0.5,
            "No measurement loaded\n\nOpen a PicoHarp 300 .phu histogram file to draw the map.",
            ha="center", va="center", color=INK_FAINT, fontsize=11, linespacing=1.8,
            transform=self.ax_map.transAxes,
        )
        self.canvas.draw()

    def _cell_near(self, wl, t_ps):
        """The (wavelength, time) cell nearest to a point, clamped into the map."""
        m = self.model
        wi = int(np.argmin(np.abs(m.wls - wl)))
        ti = int(np.clip((t_ps + m.t0 - m.t_off_ps) // m.dt_ps, 0, m.n_t - 1))
        return wi, ti

    def _clamp_view(self, draw=False):
        """Keep a zoom rectangle inside the map and give the map those limits,
        so that the axes and self.view never disagree.

        After the model was rebuilt the rectangle is trimmed to the new map (as
        up to 1.6). ``draw`` - the toolbar moved the view - slides it back
        inside instead, so a pan past an edge keeps the zoom's size (a view
        wider than the map becomes the whole map), and shows it now."""
        m = self.model
        if not m:
            return
        w_lo, w_hi = m.wl_edges
        if self.view:
            x0, x1, y0, y1 = self.view
            if draw:
                x0, x1 = self._slide_inside(x0, x1, w_lo, w_hi)
                y0, y1 = self._slide_inside(y0, y1, m.t_lo, m.t_hi)
            else:
                x0, x1 = max(x0, w_lo), min(x1, w_hi)
                y0, y1 = max(y0, m.t_lo), min(y1, m.t_hi)
            self.view = (x0, x1, y0, y1) if (x1 > x0 and y1 > y0) else None
        x0, x1, y0, y1 = self.view if self.view else (w_lo, w_hi, m.t_lo, m.t_hi)
        self.ax_map.set_xlim(x0, x1)
        self.ax_map.set_ylim(y0, y1)
        if draw:
            self.canvas.draw_idle()

    @staticmethod
    def _slide_inside(a, b, lo, hi):
        """The range a..b moved into lo..hi, its width kept (all of lo..hi
        when it is wider)."""
        width = b - a
        if width >= hi - lo:
            return lo, hi
        if a < lo:
            return lo, lo + width
        if b > hi:
            return hi - width, hi
        return a, b

    def _view_from_axes(self):
        """After a toolbar move (zoom, pan, Back, Forward): self.view is what
        the map shows now - None when that is the whole map."""
        m = self.model
        if not m or getattr(self, "im", None) is None or self.im.axes is None:
            return
        x0, x1 = sorted(self.ax_map.get_xlim())
        y0, y1 = sorted(self.ax_map.get_ylim())
        self.view = (x0, x1, y0, y1)
        self._clamp_view(draw=True)
        w_lo, w_hi = m.wl_edges
        full = (w_lo, w_hi, m.t_lo, m.t_hi)
        if self.view and all(abs(a - b) <= 1e-9 * max(abs(b), 1.0)
                             for a, b in zip(self.view, full)):
            self.view = None

    def _home_view(self):
        """The toolbar's Home: the whole map, as Reset zoom - without a new
        history entry, so Forward still leads back."""
        self.view = None
        self._reframe()

    def reset_view(self):
        """Reset zoom (the button, or a right-click on the map): the whole map,
        and every panel the toolbar zoomed back as it was drawn (the base entry
        of the toolbar's history). The toolbar's Back returns to the zoom it left."""
        if not self.model:
            self.view = None
            return
        tb = self.toolbar
        tb.ensure_base()
        base = tb._nav_stack[0]

        def limits():
            return [(tuple(ax.get_xlim()), tuple(ax.get_ylim())) for ax in list(base)]
        before, zoomed = limits(), self.view is not None
        for ax, (view, _pos) in list(base.items()):
            ax._set_view(view)
        self.view = None
        self._reframe()
        if zoomed or limits() != before:
            tb.push_current()

    def reset_contrast(self):
        self.clim = None
        self._recolor()

    # Colormap, colour scale, contrast and zoom change how the map is shown,
    # not what is in the figure: the artists redraw() built stay, and only
    # what differs is set on them. (redraw() makes ~300 artists from scratch,
    # about half of its time.) The picture is the one redraw() would give.
    def _on_colormap(self):
        self._recolor()

    def _on_log_color(self):
        self._recolor()

    def _recolor(self):
        """Give the map its colormap, linear / log colour scale and contrast."""
        if not self.model:
            return
        if getattr(self, "im", None) is None or self.im.axes is None:
            self.redraw(full=True)
            return
        m = self.model
        norm, cmap, lo, log = self._color_scale()
        Z = m.on_grid(m.E).T
        self.im.set_data(np.ma.masked_less(Z, lo) if log else Z)
        self.im.set_cmap(cmap)
        self.im.set_norm(norm)
        self._cbar.update_normal(self.im)
        self._style_colorbar(log)
        self.canvas.draw()      # on_draw() puts the cursor artists back

    def _style_colorbar(self, log):
        cb = self._cbar
        cb.set_label("Counts" + (" (log)" if log else "")
                     + ("" if self.clim is None else "  [manual]"),
                     color=INK_FAINT, fontsize=8)
        cb.ax.tick_params(colors=INK_FAINT, labelsize=7.5)
        cb.outline.set_color(LINE)

    def _reframe(self):
        """Show the zoom rectangle self.view (or the whole map); the panels
        that share an axis with the map follow."""
        if not self.model:
            return
        if getattr(self, "im", None) is None or self.im.axes is None:
            self.redraw(full=True)
            return
        m = self.model
        w_lo, w_hi = m.wl_edges
        x0, x1, y0, y1 = self.view if self.view else (w_lo, w_hi, m.t_lo, m.t_hi)
        self.ax_map.set_xlim(x0, x1)
        self.ax_map.set_ylim(y0, y1)
        self.canvas.draw()

    # -- drawing ----------------------------------------------------------
    def _color_scale(self):
        """Colour mapping of the map: (norm, cmap, vmin, log).

        Shared with the export so a written PNG carries the colormap, the
        log/linear choice and any contrast dragged on the colorbar.
        """
        log = self.var_log.get()
        lo, hi = (self.clim if self.clim is not None
                  else ((1.0 if log else 0.0), self.model.vmax))
        if log:
            lo = max(lo, 1e-2)
            hi = max(hi, lo * 1.01)
            norm = LogNorm(vmin=lo, vmax=hi)
        else:
            hi = max(hi, lo + 1e-9)
            norm = Normalize(vmin=lo, vmax=hi)
        cmap = matplotlib.colormaps[self.var_cmap.get()].copy()
        cmap.set_bad(cmap(0.0))
        return norm, cmap, lo, log

    def redraw(self, full=False):
        if not self.model:
            return
        m = self.model
        # every change to the model ends in a redraw (controls, Crop, Mask,
        # offset, a new file), so this is where the solvent checkbox and its
        # clipped-share label are brought back in line with it
        self._sync_solvent_ui()
        for ax in (self.ax_hist, self.ax_ss, self.ax_spec, self.ax_rib, self.cax):
            ax.set_visible(True)

        for ax in (self.ax_hist, self.ax_map, self.ax_ss, self.ax_spec,
                   self.ax_rib, self.cax):
            ax.clear()
            ax.set_facecolor(BG)

        w_lo, w_hi = m.wl_edges
        norm, cmap, lo, log = self._color_scale()

        # ---- 2D map ----
        Z = m.on_grid(m.E).T                # columns on the real wavelength axis
        Z = np.ma.masked_less(Z, lo) if log else Z
        self.im = self.ax_map.imshow(
            Z, aspect="auto", origin="lower", cmap=cmap, norm=norm,
            extent=[w_lo, w_hi, m.t_lo, m.t_hi], interpolation="nearest",
        )
        # masked-out wavelength bands ride on top of the heatmap as hatched bars
        shade_wl_masks(self.ax_map, m.masks, w_lo, w_hi)
        # explicit limits so adding the rubber-band patch cannot autoscale them
        self.ax_map.set_xlim(w_lo, w_hi)
        self.ax_map.set_ylim(m.t_lo, m.t_hi)
        # the time axis is the Decay panel's, right beside it: labels of its
        # own would lie on top of that panel
        self.ax_map.tick_params(labelbottom=False, labelleft=False)
        # the IRF no longer has a panel of its own, so its numbers ride along here
        self.ax_map.set_title(
            "TRES map" + (f"     IRF {m.irf_wl:.0f} nm - FWHM {m.irf_fwhm_ps:.0f} ps"
                          if m.irf is not None else ""),
            fontsize=9, loc="left", pad=4)

        self._cbar = self.fig.colorbar(self.im, cax=self.cax)
        self._style_colorbar(log)

        # ---- spectral ribbon ----
        grad = np.array([wavelength_to_rgb(w)
                         for w in np.linspace(w_lo, w_hi, 384)])[None, :, :]
        self.ax_rib.imshow(grad, aspect="auto", extent=[w_lo, w_hi, 0, 1],
                           interpolation="bilinear")
        self.ax_rib.set_yticks([])
        self.ax_rib.tick_params(labelbottom=False, length=0)

        # ---- decay histogram (left, time shared with the map) ----
        # The only static (grey) trace is the IRF, when the file has one. Its
        # raw scatter peak is many times brighter than the emission, so scale it
        # to the map's brightest count (m.vmax): it then shares the panel's count
        # scale with the live decay instead of running off the axis.
        if m.irf is not None and m.irf.max() > 0:
            irf_scaled = m.irf / m.irf.max() * m.vmax
            self.ax_hist.plot(np.maximum(irf_scaled, 0.7), m.times, color="#8a93a2",
                              lw=1.0, ls="--", alpha=0.65, label="IRF")
            self.ax_hist.legend(loc="upper right", fontsize=7, frameon=False,
                                handlelength=1.4, borderaxespad=0.3)
        (self.ln_decay,) = self.ax_hist.plot([], [], lw=1.4, color=ACCENT, animated=True)
        self.hl_hist = self.ax_hist.axhline(np.nan, color=INK_DIM, lw=0.8, ls=":",
                                            alpha=0.55, animated=True)
        self.ax_hist.set_xscale("log")
        self.ax_hist.set_xlim(1, m.vmax * 1.6)
        self.ax_hist.set_ylim(m.t_lo, m.t_hi)
        self.ax_hist.set_xlabel("Counts", fontsize=9)
        self.ax_hist.set_ylabel("Time (ps)", fontsize=9)
        self.ax_hist.set_title("Decay", fontsize=9, loc="left", pad=4)
        self.ax_hist.grid(alpha=0.12, lw=0.5, color=INK_FAINT)

        # ---- spectrum (bottom, wavelength shared with the map) ----
        # backdrop: the band shape of all delays together, scaled to the panel
        # (which is sized for one time bin) the way the IRF is in the Decay panel
        band = m.spec_total
        if np.isfinite(band).any() and np.nanmax(band) > 0:
            band = band / np.nanmax(band) * m.vmax
        self.ax_spec.fill_between(m.wls, np.maximum(band, 0.7), 0.7,
                                  color=INK_FAINT, alpha=0.16, lw=0)
        shade_wl_masks(self.ax_spec, m.masks, w_lo, w_hi)
        (self.ln_spec,) = self.ax_spec.plot([], [], lw=1.4, color=INK,
                                            marker="o", ms=2.6, animated=True)
        self.vl_spec = self.ax_spec.axvline(np.nan, color=INK_DIM, lw=0.8, ls=":",
                                            alpha=0.55, animated=True)
        self.ax_spec.set_yscale("log")
        self.ax_spec.set_ylim(0.7, m.vmax * 1.6)
        self.ax_spec.set_xlim(w_lo, w_hi)
        self.ax_spec.set_xlabel("Wavelength (nm)", fontsize=9)
        self.ax_spec.set_ylabel("Counts", fontsize=9)
        self.ax_spec.set_title("Spectrum", fontsize=9, loc="left", pad=4)
        self.ax_spec.grid(alpha=0.12, lw=0.5, color=INK_FAINT)

        # ---- background: shade the window, draw the spectrum that was removed ----
        if m.bg_spec is not None:
            b0, b1 = m.bg_window_ps
            self.ax_map.axhspan(b0, b1, color=PIN, alpha=0.10, lw=0)
            self.ax_hist.axhspan(b0, b1, color=PIN, alpha=0.14, lw=0)
            self.ax_spec.plot(m.wls, np.maximum(m.bg_spec, 0.7), color=PIN,
                              ls=":", lw=1.0, alpha=0.8)
            note, warn = self._bg_note()
            self.lbl_bginfo.configure(foreground=WARN if warn else PIN)
            bg_mean = float(np.nanmean(m.bg_spec))
            # Below one count per bin most bins of a sparse map hold 0 or 1
            # count, so taking the background off sends the empty ones below 0:
            # a large negative share then says nothing about the window. The
            # level is the sample's own: an over-scaled solvent makes bg_spec
            # negative, and that is one of the things to warn about.
            self.var_bginfo.set(
                f"bg {b0:,.0f}-{b1:,.0f} ps (mean {bg_mean:,.1f} cts/bin)" + note
                + (f"  ** {m.neg_frac:.0%} of the map is negative - "
                   + ("solvent scale too high, or window on signal?" if m.solvent_active
                      else "window is on signal?")
                   if m.neg_frac > 0.6 and m.bg_sample_mean() >= 1.0 else ""))
        else:
            self.lbl_bginfo.configure(foreground=PIN)
            self.var_bginfo.set("bg off")

        # ---- steady-state spectrum: every delay of the record summed together ----
        # linear, unlike the slice below the map: this is the band shape a cw
        # spectrometer would have measured, and a log axis flattens it.
        ss = m.spec_total
        self.ax_ss.fill_between(m.wls, ss, 0.0, color=ACCENT, alpha=0.20, lw=0)
        self.ax_ss.plot(m.wls, ss, color=ACCENT, lw=1.2)
        shade_wl_masks(self.ax_ss, m.masks, w_lo, w_hi)
        self.ax_ss.set_xlim(w_lo, w_hi)
        # spec_total carries NaN gaps at masked wavelengths, so reduce nan-aware
        have_ss = bool(np.isfinite(ss).any())
        top = max(float(np.nanmax(ss)) if have_ss else 1.0, 1.0)
        ss_bot = float(np.nanmin(ss)) if have_ss else 0.0
        self.ax_ss.set_ylim(min(0.0, ss_bot * 1.08), top * 1.12)
        # summed counts run into the millions; "1.2M" keeps the panel readable
        self.ax_ss.yaxis.set_major_locator(MaxNLocator(5))
        self.ax_ss.yaxis.set_major_formatter(EngFormatter(places=0, sep=""))
        self.ax_ss.grid(alpha=0.12, lw=0.5, color=INK_FAINT)
        self.ax_ss.set_xlabel("Wavelength (nm)", fontsize=9)
        self.ax_ss.set_ylabel("Counts (all delays)", fontsize=9)
        # in-axes, not a title: the decay panel's x-label sits in that same band
        peak_txt = (f"{m.wls[int(np.nanargmax(ss))]:.0f} nm" if have_ss else "-")
        self.ax_ss.text(
            0.028, 0.955, f"Steady state - peak {peak_txt}",
            transform=self.ax_ss.transAxes, ha="left", va="top",
            fontsize=8.5, color=INK_DIM)

        # ---- crosshair + readout on the map ----
        self.vl_map = self.ax_map.axvline(np.nan, color="w", lw=0.9, ls="--",
                                          alpha=0.75, animated=True)
        self.hl_map = self.ax_map.axhline(np.nan, color="w", lw=0.9, ls="--",
                                          alpha=0.75, animated=True)
        # the read-out sits on top of the colormap image, so it keeps a dark
        # card with light text regardless of the (now light) UI theme
        self.txt = self.ax_map.text(
            0.988, 0.972, "", transform=self.ax_map.transAxes, ha="right", va="top",
            family="monospace", fontsize=8.5, color=READOUT_FG, animated=True,
            bbox=dict(boxstyle="round,pad=0.45", fc=READOUT_BG, ec=LINE, alpha=0.88),
        )

        # ---- rubber bands: zoom rectangle on the map, contrast span on the bar ----
        self.rect = Rectangle((0, 0), 0, 0, fc=ACCENT, alpha=0.16, ec=ACCENT,
                              lw=1.0, ls="--", animated=True, visible=False)
        self.ax_map.add_patch(self.rect)

        self.crect = Rectangle((0, 0), 1, 0, transform=self.cax.get_yaxis_transform(),
                               fc="none", ec="w", lw=1.2, animated=True, visible=False)
        self.cax.add_patch(self.crect)

        # clear() gave every label and title back matplotlib's default colour
        for ax in (self.ax_hist, self.ax_map, self.ax_ss, self.ax_spec, self.ax_rib):
            ax.xaxis.label.set_color(INK_FAINT)
            ax.yaxis.label.set_color(INK_FAINT)
            for title in (ax.title, ax._left_title, ax._right_title):
                title.set_color(INK_DIM)

        # ---- zoom: applied last, the shared axes follow ----
        # The axes were cleared and drawn anew: what the toolbar remembered
        # belongs to the old picture. The whole map is its new Home (the base
        # entry), and a zoom kept from before is the entry after it.
        self.ax_map.set_xlim(w_lo, w_hi)
        self.ax_map.set_ylim(m.t_lo, m.t_hi)
        self.toolbar.forget_history()
        if self.view:
            x0, x1, y0, y1 = self.view
            self.ax_map.set_xlim(x0, x1)
            self.ax_map.set_ylim(y0, y1)
            self.toolbar.push_current()

        self.canvas.draw()      # on_draw() puts the cursor artists back

    def on_draw(self, event):
        """Re-capture clean backgrounds after every full redraw (incl. resize)."""
        # (a savefig draws too, on another renderer and maybe another canvas:
        # nothing of it may stay in this window)
        if not self.model or event.canvas.is_saving():
            return
        # new tick labels or a new canvas size: the panels may have to move
        # (a few times at most - a move can change the tick labels again), but
        # not under a pan in progress: its release draws, and they move then.
        self._layout_stale = False
        if self._relayouts < 3 and not self.toolbar.dragging() and self._fit_layout():
            # what was drawn is about to be replaced: nothing to blit onto. A
            # window not on screen yet (a file named at start) gets no second
            # draw: it is about to be drawn at its real size anyway.
            self._relayouts += 1
            self._layout_stale = True
            self._bg = {}
            if self.canvas.get_tk_widget().winfo_ismapped():
                self._queue_draw()
            return
        self._relayouts = 0
        self._bg = {
            "map": self.canvas.copy_from_bbox(self.ax_map.bbox),
            "hist": self.canvas.copy_from_bbox(self.ax_hist.bbox),
            "spec": self.canvas.copy_from_bbox(self.ax_spec.bbox),
            "cax": self.canvas.copy_from_bbox(self.cax.bbox),
        }
        # the crosshair and the live curves are animated artists: a draw does
        # not paint them, so put them back on the fresh backgrounds (a resize
        # or an uncovered window draws without going through redraw())
        self.update_cursor()

    def _draw_relaid(self):
        """Draw the panels where _fit_layout moved them (unless the tab is gone,
        or a resize has drawn them by now)."""
        self._draw_queued = None
        if not self._layout_stale:
            return
        try:
            if self.canvas.get_tk_widget().winfo_exists():
                self.canvas.draw()
        except tk.TclError:
            pass

    def update_cursor(self):
        """Update the live slices by blitting - fast enough for every mouse move."""
        if not self.model or not self._bg:
            return
        m = self.model

        if self.cursor is None:
            self.ln_decay.set_data([], [])
            self.ln_spec.set_data([], [])
            # hide each line through the coordinate update_cursor() sets again:
            # a horizontal line whose x was blanked would stay invisible for
            # as long as the artists live (they now outlive a recolour / zoom)
            for art in (self.vl_map, self.vl_spec):
                art.set_xdata([np.nan, np.nan])
            for art in (self.hl_map, self.hl_hist):
                art.set_ydata([np.nan, np.nan])
            self.txt.set_text("")
        else:
            wi, ti = self.cursor
            wl = m.wls[wi]
            t_ps = m.times[ti]
            val = m.E[wi, ti]
            col = wavelength_to_rgb(wl)

            decay = np.maximum(m.decay_at(wi), 0.7)
            self.ln_decay.set_data(decay, m.times)
            self.ln_decay.set_color(col)

            spec = np.maximum(m.spectrum_at(ti), 0.7)
            self.ln_spec.set_data(m.wls, spec)

            self.vl_map.set_xdata([wl, wl])
            self.hl_map.set_ydata([t_ps, t_ps])
            self.vl_spec.set_xdata([wl, wl])
            self.hl_hist.set_ydata([t_ps, t_ps])

            edge = PIN if self.pinned else "w"
            for art in (self.vl_map, self.hl_map):
                art.set_color(edge)

            self.txt.set_text(
                f"λ        {wl:>8,.0f} nm\n"
                f"t        {t_ps:>8,.0f} ps\n"
                f"counts   {val:>8,.0f}"
                + ("\nPINNED - click to release" if self.pinned else "")
            )
            # the card under it is dark whatever the UI theme: light text
            self.txt.set_color(PIN if self.pinned else READOUT_FG)

        self.canvas.restore_region(self._bg["hist"])
        self.ax_hist.draw_artist(self.ln_decay)
        self.ax_hist.draw_artist(self.hl_hist)
        self.canvas.blit(self.ax_hist.bbox)

        self.canvas.restore_region(self._bg["spec"])
        self.ax_spec.draw_artist(self.ln_spec)
        self.ax_spec.draw_artist(self.vl_spec)
        self.canvas.blit(self.ax_spec.bbox)

        self.canvas.restore_region(self._bg["map"])
        self.ax_map.draw_artist(self.vl_map)
        self.ax_map.draw_artist(self.hl_map)
        self.ax_map.draw_artist(self.txt)
        self.canvas.blit(self.ax_map.bbox)

    # -- events -----------------------------------------------------------
    DRAG_PX = 5      # below this a press/release pair counts as a plain click

    def on_press(self, event):
        # while the toolbar's pan / zoom mode holds the canvas, the mouse is its
        if not self.model or not self._bg or self.toolbar.locked():
            return
        if event.inaxes is self.ax_map:
            if event.button == 3:
                self.reset_view()
            elif event.button == 1 and event.xdata is not None:
                self._drag = dict(kind="zoom", x0=event.xdata, y0=event.ydata,
                                  px=event.x, py=event.y)
        elif event.inaxes is self.cax:
            if event.button == 3:
                self.reset_contrast()
            elif event.button == 1 and event.ydata is not None:
                self._drag = dict(kind="clim", y0=event.ydata, py=event.y)

    def on_motion(self, event):
        if not self.model:
            return
        if self._drag is not None:
            if not self.toolbar.locked():
                self._draw_rubber(event)
            return
        # the read-out follows the mouse in pan / zoom mode too, only not
        # while the toolbar is dragging
        if self.toolbar.dragging():
            return
        if self.pinned or event.inaxes is not self.ax_map:
            return
        if event.xdata is None or event.ydata is None:
            return
        hit = self.model.locate(event.xdata, event.ydata)
        if hit and hit != self.cursor:
            self.cursor = hit
            self.update_cursor()

    def on_release(self, event):
        drag, self._drag = self._drag, None
        if not self.model or drag is None:
            return
        if self.toolbar.locked():       # pan / zoom mode was switched on meanwhile
            self.rect.set_visible(False)
            self.crect.set_visible(False)
            return

        if drag["kind"] == "zoom":
            moved = (abs(event.x - drag["px"]) > self.DRAG_PX or
                     abs(event.y - drag["py"]) > self.DRAG_PX)
            if moved and "x1" in drag:
                x0, x1 = sorted((drag["x0"], drag["x1"]))
                y0, y1 = sorted((drag["y0"], drag["y1"]))
                if x1 > x0 and y1 > y0:
                    self.toolbar.ensure_base()
                    self.view = (x0, x1, y0, y1)
                    self._reframe()
                    self.toolbar.push_current()     # Back returns to the view before
                    return
            if event.inaxes is self.ax_map:
                self._toggle_pin(event)
        elif abs(event.y - drag["py"]) > self.DRAG_PX and "y1" in drag:
            lo, hi = sorted((drag["y0"], drag["y1"]))
            if hi > lo:
                self.clim = (lo, hi)
                self._recolor()
                return

        self.rect.set_visible(False)
        self.crect.set_visible(False)
        self.update_cursor()

    def _draw_rubber(self, event):
        """Blit the drag rectangle over the clean background of its own axes."""
        if not self._bg:            # the panels just moved; the next draw brings it back
            return
        d = self._drag
        if d["kind"] == "zoom":
            if event.inaxes is self.ax_map and event.xdata is not None:
                d["x1"], d["y1"] = event.xdata, event.ydata
            if "x1" not in d:
                return
            x0, x1 = sorted((d["x0"], d["x1"]))
            y0, y1 = sorted((d["y0"], d["y1"]))
            self.rect.set_bounds(x0, y0, x1 - x0, y1 - y0)
            self.rect.set_visible(True)
            self.canvas.restore_region(self._bg["map"])
            self.ax_map.draw_artist(self.rect)
            self.canvas.blit(self.ax_map.bbox)
        else:
            if event.inaxes is self.cax and event.ydata is not None:
                d["y1"] = event.ydata
            if "y1" not in d:
                return
            y0, y1 = sorted((d["y0"], d["y1"]))
            self.crect.set_bounds(0, y0, 1, y1 - y0)
            self.crect.set_visible(True)
            self.canvas.restore_region(self._bg["cax"])
            self.cax.draw_artist(self.crect)
            self.canvas.blit(self.cax.bbox)

    def _toggle_pin(self, event):
        if event.xdata is None or event.ydata is None:
            return
        hit = self.model.locate(event.xdata, event.ydata)
        if self.pinned:
            self.pinned = False
            if hit:
                self.cursor = hit
        elif hit:
            self.cursor = hit
            self.pinned = True
        self.update_cursor()

    def on_leave(self, event):
        if self._drag is not None or self.toolbar.dragging():
            return
        if self.model and not self.pinned and event.inaxes is self.ax_map:
            self.cursor = None
            self.update_cursor()
