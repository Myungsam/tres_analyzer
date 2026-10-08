"""The Crop window: zoom, colour scale and time scale of its map."""
import numpy as np

from matplotlib.ticker import LogFormatterSciNotation

from ..theme import INK_FAINT, preview_norm_cmap


class _CropView:
    """How the Crop window's map is looked at - zoom, pan limits, colour and
    time scale. None of it reaches the crop box or the model. Part of
    CropDialog (crop.py), which owns the figure and the Tk variables.
    """

    ZOOM_STEP = 1.25        # per wheel notch

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
        dw = (w_hi - w_lo) / f.n_cols
        i0 = int(np.clip(np.floor((x0 - w_lo) / dw), 0, f.n_cols - 1))
        i1 = int(np.clip(np.ceil((x1 - w_lo) / dw), i0 + 1, f.n_cols))
        j0 = int(np.clip(np.floor(y0 / f.dt_ps), 0, f.n_t - 1))
        j1 = int(np.clip(np.ceil(y1 / f.dt_ps), j0 + 1, f.n_t))
        block = f.on_grid(f.E)[i0:i1, j0:j1]
        block = block[np.isfinite(block)]
        return float(block.max()) if block.size else 0.0

    def _recolor(self):
        """Give the map its colour scale: linear or log, up to the maximum of
        the whole unsubtracted map or, with Auto color, of the part in view."""
        vmax = self._view_max() if self.var_auto.get() else self._vmax0
        self._transform, norm, _ = preview_norm_cmap(
            vmax, self.var_zlog.get(), self.app.var_cmap.get())
        self._base_im.set_norm(norm)
        self._base_im.set_data(self._transform(self._full.on_grid(self._full.E).T))

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
