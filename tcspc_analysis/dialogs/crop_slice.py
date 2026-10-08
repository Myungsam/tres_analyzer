"""The Crop window: the time slice under the pointer."""
import numpy as np

from ..theme import INK, PIN


class _CropSlice:
    """The spectrum of one time bin in the Crop window: it follows the
    pointer (or is pinned) and is painted onto a kept picture of the
    figure. Part of CropDialog (crop.py).
    """

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
            if self._slice_leg is not None:
                self._slice_leg.remove()
                self._slice_leg = self._slice_key = None
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
        # one legend for as long as the same lines are shown; only its title
        # changes with the pointer
        if self._slice_key != shown:
            if self._slice_leg is not None:
                self._slice_leg.remove()
            leg = self.ax_t.legend(
                handles=list(shown), loc="upper left", fontsize=7.5, frameon=False,
                ncol=3, title=" ", title_fontsize=8, alignment="left")
            leg.set_animated(True)
            for txt in (*leg.get_texts(), leg.get_title()):
                txt.set_color(INK)
            self._slice_leg, self._slice_key = leg, shown
        self._slice_leg.set_title(
            f"t = {t:,.0f} ps" + ("  (pinned)" if self._slice_pinned else ""))

    def _on_draw(self, event):
        """The figure was drawn (without the slice, which is animated): keep
        that picture, then put the slice on it."""
        if event.canvas is not self.canvas or self.canvas.is_saving():
            return                  # a savefig draws everything itself
        self._bg = self.canvas.copy_from_bbox(self.fig.bbox)
        self._paint_slice()

    def _paint_slice(self):
        at = self.ax_t
        if self.hl_t.get_visible():
            self.ax.draw_artist(self.hl_t)
        for ln in (self.ln_t_sample, self.ln_t_solv, self.ln_t_sub):
            if ln.get_visible():
                at.draw_artist(ln)
        at.draw_artist(at.yaxis)
        if self._slice_leg is not None:
            at.draw_artist(self._slice_leg)
        self.canvas.blit(self.fig.bbox)

    def _show_slice(self):
        """After _draw_slice(): show it, without drawing the figure again."""
        if self._bg is None:        # nothing drawn yet: the first draw shows it
            self.canvas.draw_idle()
            return
        self.canvas.restore_region(self._bg)
        self._paint_slice()
