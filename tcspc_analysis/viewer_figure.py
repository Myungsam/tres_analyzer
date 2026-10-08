"""The TRES tab's figure: drawing and mouse interaction."""
import numpy as np

import matplotlib
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.colors import LogNorm, Normalize
from matplotlib.figure import Figure
from matplotlib.gridspec import GridSpec
from matplotlib.patches import Rectangle
from matplotlib.ticker import EngFormatter, MaxNLocator

from .util import wavelength_to_rgb
from .theme import ACCENT, BG, INK, INK_DIM, INK_FAINT, LINE, PANEL, PIN, READOUT_BG, READOUT_FG, shade_wl_masks


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

        self.canvas.mpl_connect("motion_notify_event", self.on_motion)
        self.canvas.mpl_connect("button_press_event", self.on_press)
        self.canvas.mpl_connect("button_release_event", self.on_release)
        self.canvas.mpl_connect("axes_leave_event", self.on_leave)
        self.canvas.mpl_connect("draw_event", self.on_draw)

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

    def _clamp_view(self):
        """Keep a zoom rectangle inside the axes after the model was rebuilt."""
        if not self.view:
            return
        m = self.model
        w_lo, w_hi = m.wl_edges
        x0, x1, y0, y1 = self.view
        x0, x1 = max(x0, w_lo), min(x1, w_hi)
        y0, y1 = max(y0, m.t_lo), min(y1, m.t_hi)
        self.view = (x0, x1, y0, y1) if (x1 > x0 and y1 > y0) else None

    def reset_view(self):
        self.view = None
        self._reframe()

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
            self.var_bginfo.set(
                f"bg {b0:,.0f}-{b1:,.0f} ps (mean {np.nanmean(m.bg_spec):,.1f} cts/bin)"
                + (f"  ** {m.neg_frac:.0%} of the map is negative - "
                   + ("solvent scale too high, or window on signal?" if m.solvent_active
                      else "window is on signal?")
                   if m.neg_frac > 0.6 else ""))
        else:
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
        x0, x1, y0, y1 = self.view if self.view else (w_lo, w_hi, m.t_lo, m.t_hi)
        self.ax_map.set_xlim(x0, x1)
        self.ax_map.set_ylim(y0, y1)

        self.canvas.draw()      # on_draw() puts the cursor artists back

    def on_draw(self, event):
        """Re-capture clean backgrounds after every full redraw (incl. resize)."""
        if not self.model:
            return
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
        if not self.model or not self._bg:
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
            self._draw_rubber(event)
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

        if drag["kind"] == "zoom":
            moved = (abs(event.x - drag["px"]) > self.DRAG_PX or
                     abs(event.y - drag["py"]) > self.DRAG_PX)
            if moved and "x1" in drag:
                x0, x1 = sorted((drag["x0"], drag["x1"]))
                y0, y1 = sorted((drag["y0"], drag["y1"]))
                if x1 > x0 and y1 > y0:
                    self.view = (x0, x1, y0, y1)
                    self._reframe()
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
        if self._drag is not None:
            return
        if self.model and not self.pinned and event.inaxes is self.ax_map:
            self.cursor = None
            self.update_cursor()
