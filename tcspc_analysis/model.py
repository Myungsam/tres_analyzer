"""TRESModel: rebinning, slicing and the preprocessing of one .phu file."""
import warnings

import numpy as np

from .util import fwhm_of


def solvent_mismatch(sample, solvent):
    """Compare a solvent .phu against the sample it is to be subtracted from.

    Returns (errors, notes), two lists of messages. The subtraction is bin for
    bin, with no resampling, so any error - a different number of curves,
    wavelength list, time resolution or bin count - means the solvent has to be
    refused. A note (a different acquisition time) is only reported: the scale
    factor can make up for it.
    """
    errors, notes = [], []
    if solvent["ncurves"] != sample["ncurves"]:
        errors.append(f'number of curves: {solvent["ncurves"]} (solvent) vs '
                      f'{sample["ncurves"]} (sample)')
    # only comparable once the counts agree - allclose cannot broadcast otherwise
    elif not np.allclose(solvent["wls"], sample["wls"], rtol=0.0, atol=1e-6):
        errors.append("wavelength list differs from the sample")
    if solvent["nbins"] != sample["nbins"]:
        errors.append(f'time bins: {solvent["nbins"]:,} (solvent) vs '
                      f'{sample["nbins"]:,} (sample)')
    if not np.isclose(solvent["res_ps"], sample["res_ps"], rtol=1e-9, atol=0.0):
        errors.append(f'time resolution: {solvent["res_ps"]:g} ps (solvent) vs '
                      f'{sample["res_ps"]:g} ps (sample)')

    acq_v, acq_s = solvent.get("acq_ms"), sample.get("acq_ms")
    if acq_v and acq_s and acq_v != acq_s:
        notes.append(f"acquisition time per curve: {acq_v / 1000:g} s (solvent) vs "
                     f"{acq_s / 1000:g} s (sample)")
    return errors, notes


def wavelength_grid(wls):
    """Where curves measured at ``wls`` (ascending nm) go in a map whose
    columns all have the same width: (column of each curve, number of
    columns, width of a column in nm).

    A sweep in even steps - the usual case - is one column per curve. When
    the steps differ (an IRF curve taken at another wavelength and kept in the
    map; a sweep with a gap) the axis is laid out in the smallest step and the
    curves are put where they belong, with empty columns between them. Drawn
    one column per curve instead, a curve at 550 nm sat at 538-543 nm. A list
    that fits no such grid (within a twentieth of a step) stays one column per
    curve.
    """
    wls = np.asarray(wls, float)
    n = wls.size
    if n < 2:
        return np.arange(n), max(n, 1), 5.0
    gaps = np.diff(wls)
    step = float(np.median(gaps))
    if np.allclose(gaps, step, rtol=0.0, atol=1e-6 * abs(step)):
        return np.arange(n), n, step
    smallest = float(gaps.min())
    if smallest > 0:
        at = (wls - wls[0]) / smallest
        col = np.rint(at).astype(int)
        if np.allclose(at, col, rtol=0.0, atol=0.05) and col[-1] < 20 * n:
            return col, int(col[-1]) + 1, smallest
    return np.arange(n), n, step


# ==========================================================================
# 3. Model - rebinning and slicing
# ==========================================================================
class TRESModel:
    """Holds the file and the rebinned display matrix used by every panel."""

    # Every setting __init__ creates, in one place: copy_settings_from() walks
    # this, so a preview model built from the live one cannot miss any.
    SETTINGS = ("rebin", "t_max_ps", "first_is_irf", "t0_align", "bg_sub",
                "bg_lo_ps", "bg_hi_ps", "wl_offset", "t_min_ps", "crop_wl",
                "masks", "solvent", "solvent_scale", "solvent_sub")

    def __init__(self, phu, build=True):
        # build=False: the caller sets its settings first and calls rebuild()
        # itself - a default build would be thrown away
        self.phu = phu
        self.rebin = 4
        self.t_max_ps = self.t_data_ps   # as far as the counts go, until changed
        self.first_is_irf = True
        self.t0_align = False
        self.bg_sub = True
        self.bg_lo_ps = 0.0
        self.bg_hi_ps = 100.0
        self.wl_offset = 0.0     # nm added to every wavelength in the file
        # -- preprocessing (Crop dialog + Mask lambda dialog) ------------------
        # A crop keeps only a rectangular (wavelength, time) window; t_max_ps
        # above is its upper time edge, t_min_ps its lower one. crop_wl limits
        # the wavelength window (in offset-applied nm, i.e. what the user sees),
        # None meaning "full". masks is a list of (wl1, wl2) nm regions whose
        # rows are set to NaN so they drop out of the map, the spectra and the
        # fits. All operate on the pristine phu arrays, so any of them can be
        # widened or cleared again without reloading the file.
        self.t_min_ps = 0.0
        self.crop_wl = None
        self.masks = []
        # -- solvent subtraction (picked and scaled in the Crop dialog) --------
        # solvent is the phu dict of a pure-solvent record taken on the same
        # grid as the sample. While solvent_sub is on, solvent_scale times it
        # is subtracted bin for bin right after rebinning. What that leaves
        # below zero stays in E (see subtract_background).
        self.solvent = None
        self.solvent_scale = 1.0
        self.solvent_sub = False
        # counts the times E was rebuilt: a fit window compares it with the
        # number it started a fit at to tell that its result is of older data
        self.rev = 0
        if build:
            self.rebuild()

    @property
    def solvent_active(self):
        return self.solvent is not None and self.solvent_sub

    def copy_settings_from(self, other):
        """Take every setting of ``other`` (same file); rebuild() is the caller's."""
        for name in self.SETTINGS:
            setattr(self, name, getattr(other, name))
        self.masks = list(other.masks)

    # -- geometry ---------------------------------------------------------
    @property
    def t_full_ps(self):
        """Length of the whole measured record, in ps."""
        return self.phu["nbins"] * self.phu["res_ps"]

    @property
    def t_data_ps(self):
        """Length of the part of the record that holds counts, in ps.

        A histogram is only filled inside the sync period, so past the last
        photon every bin is an exact zero on every curve: no data was taken
        there, and showing it only squeezes the map. This is the default time
        span; the entry box still reaches t_full_ps if you want the tail.
        Falls back to the whole record when the file is empty everywhere.
        """
        if getattr(self, "_t_data", None) is None:      # the file does not change
            hit = np.nonzero(self.phu["counts"].any(axis=0))[0]
            self._t_data = (self.t_full_ps if not len(hit) else
                            min((int(hit[-1]) + 1) * self.phu["res_ps"], self.t_full_ps))
        return self._t_data

    @property
    def dt_ps(self):
        return self.rebin * self.phu["res_ps"]

    @property
    def t0(self):
        return self.irf_peak_ps if (self.t0_align and self.irf is not None) else 0.0

    @property
    def times(self):
        """Display-bin centres, in ps, already shifted by t0.

        t_off_ps is the real delay of the first displayed bin: 0 unless a crop
        dropped early bins, in which case the axis keeps the true delays.
        """
        return self.t_off_ps + (np.arange(self.n_t) + 0.5) * self.dt_ps - self.t0

    @property
    def t_lo(self):
        return self.t_off_ps - self.t0

    @property
    def t_hi(self):
        return self.t_off_ps + self.n_t * self.dt_ps - self.t0

    @property
    def wl_edges(self):
        """Outer edges of the map's wavelength axis (see wavelength_grid)."""
        return self.wls[0] - self.wl_step / 2, self.wls[-1] + self.wl_step / 2

    def on_grid(self, A):
        """``A`` - one row per curve, like E - as the rows of the map's
        wavelength axis: the same array when every curve is a column, else
        with rows of NaN where no curve was measured."""
        if self.n_cols == self.n_w:
            return A
        out = np.full((self.n_cols,) + A.shape[1:], np.nan)
        out[self.col] = A
        return out

    # -- build ------------------------------------------------------------
    def rebuild(self):
        p = self.phu
        res = p["res_ps"]
        # a file with a single curve has no separate IRF measurement: that
        # curve is the data, whatever the checkbox says
        self.irf_idx = 0 if (self.first_is_irf and p["ncurves"] > 1) else None

        # -- wavelength window: drop the IRF curve, then any curve outside the
        #    crop range (compared in offset-applied nm, i.e. what the user
        #    picked). Fall back to the full sweep if the range keeps nothing.
        idx = [i for i in range(p["ncurves"]) if i != self.irf_idx]
        # ascending wavelength, whatever order the sweep was taken in: the map,
        # the spectra and locate() all read the list that way
        idx.sort(key=lambda i: p["wls"][i])
        if self.crop_wl is not None:
            wl_lo, wl_hi = sorted(self.crop_wl)
            keep = [i for i in idx
                    if wl_lo - 1e-6 <= p["wls"][i] + self.wl_offset <= wl_hi + 1e-6]
            if keep:
                idx = keep

        # -- time window: bins for [t_min_ps, t_max_ps], rebinned by rb. The
        #    first kept bin's true delay is t_off_ps, so cropping early bins
        #    slides the axis origin instead of relabelling the delays.
        rb = min(max(1, int(self.rebin)), p["nbins"])
        b_lo = int(np.clip(round(self.t_min_ps / res), 0, p["nbins"] - 1))
        # leave room for one whole rebinned bin before the end of the record
        b_lo = min(b_lo, p["nbins"] - rb)
        b_hi = int(np.clip(round(self.t_max_ps / res), b_lo + 1, p["nbins"]))
        n_t = max(1, (b_hi - b_lo) // rb)
        b_hi = b_lo + n_t * rb
        self.t_off_ps = b_lo * res

        block = p["counts"][idx, b_lo:b_hi].astype(np.float64)
        self.E_raw = block.reshape(len(idx), n_t, rb).sum(axis=2)  # (wavelength, time)
        self.wls = p["wls"][idx] + self.wl_offset
        self.n_w, self.n_t = self.E_raw.shape
        self.col, self.n_cols, self.wl_step = wavelength_grid(self.wls)

        # -- solvent: the same curves, bins and rebinning as the sample block,
        #    so the two line up cell for cell (solvent_mismatch() made sure the
        #    grids agree). S_raw stays unscaled - the Crop preview draws it -
        #    and the subtraction itself only happens while it is switched on.
        if self.solvent is not None:
            sblock = self.solvent["counts"][idx, b_lo:b_hi].astype(np.float64)
            self.S_raw = sblock.reshape(len(idx), n_t, rb).sum(axis=2)
            if self.solvent_sub:
                self.E_raw = self.E_raw - self.solvent_scale * self.S_raw
        else:
            self.S_raw = None

        # -- wavelength masks: whole rows to NaN, so they drop out of the map,
        #    the summed spectra and the fits while staying in the axis as a gap.
        self.mask_rows = np.zeros(self.n_w, dtype=bool)
        for a, b in self.masks:
            self.mask_rows |= (self.wls >= min(a, b)) & (self.wls <= max(a, b))
        if self.mask_rows.any():
            self.E_raw[self.mask_rows, :] = np.nan
            if self.S_raw is not None:
                self.S_raw[self.mask_rows, :] = np.nan

        # IRF, kept at native resolution for the peak/FWHM numbers. The peak is
        # measured on the whole IRF curve so cropping the record does not move
        # it; only the drawn trace is sliced to the time window so it lines up
        # with the decay panel. Built before the background because t0 - and
        # with it the window - depends on it.
        if self.irf_idx is not None:
            full = p["counts"][self.irf_idx].astype(np.float64)
            self.irf = full[b_lo:b_hi].reshape(n_t, rb).sum(axis=1)
            self.irf_wl = p["wls"][self.irf_idx] + self.wl_offset
            self.irf_peak_ps, self.irf_fwhm_ps = fwhm_of(full, res)
        else:
            self.irf = None
            self.irf_wl = None
            self.irf_peak_ps = self.irf_fwhm_ps = 0.0

        self.subtract_background()

    def subtract_background(self):
        """Take the mean spectrum over the background window out of every bin."""
        self.rev += 1
        if not self.bg_sub:
            self.bg_spec = None
            self.bg_window_ps = None
            self.E = self.E_raw
        else:
            i0, i1 = self.bg_slice()
            # nanmean: a masked (all-NaN) row averages to NaN and stays a gap.
            # The "Mean of empty slice" warning it raises for such rows is
            # expected, so silence it rather than spam the console.
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                self.bg_spec = np.nanmean(self.E_raw[:, i0:i1], axis=1)
            self.bg_window_ps = (self.t_off_ps + i0 * self.dt_ps - self.t0,
                                 self.t_off_ps + i1 * self.dt_ps - self.t0)
            self.E = self.E_raw - self.bg_spec[:, None]

        # Solvent subtraction leaves noise scattered around zero, and it is
        # left there. (Up to 1.5 the negatives were cut to 0, which lifts
        # every cell by 0.4 sigma on average: the steady-state spectrum of
        # pure noise came out at +84,000 counts, and a fitted trace got an
        # offset that was not in the data.) The colour scales show what is
        # below 0 as 0; neg_frac is the share of such cells.

        # a window sitting on real signal drives almost everything negative,
        # which the map can only render as "below the colour scale". Masked
        # (NaN) cells are neither positive nor negative, so weigh only the rest.
        finite = int(np.isfinite(self.E).sum())
        self.neg_frac = float((self.E < 0).sum() / finite) if finite else 0.0
        self.vmax = max(float(np.nanmax(self.E)) if finite else 1.0, 1.0)

        # every delay summed: the steady-state spectrum, and its mirror image
        # over the wavelengths. nansum drops masked cells; a fully masked
        # wavelength stays NaN (a gap in the spectrum) instead of reading as 0.
        self.spec_total = np.nansum(self.E, axis=1)
        self.decay_total = np.nansum(self.E, axis=0)
        self.spec_total[np.isnan(self.E).all(axis=1)] = np.nan

    def bg_slice(self):
        """Background window as display-bin indices [i0, i1), always non-empty.

        The window is given in display-time coordinates, i.e. what the axes
        show, so it follows the "t0 at IRF peak" shift.
        """
        lo, hi = sorted((self.bg_lo_ps, self.bg_hi_ps))
        # invert times(): display t = t_off + (j + 0.5)*dt - t0  ->  j
        off = self.t0 - self.t_off_ps
        i0 = int(np.clip(np.floor((lo + off) / self.dt_ps), 0, self.n_t - 1))
        i1 = int(np.clip(np.ceil((hi + off) / self.dt_ps), i0 + 1, self.n_t))
        return i0, i1

    def solvent_spectrum(self):
        """Unscaled steady-state spectrum of the solvent, or None without one.

        Treated like the sample - same background window, same sum over time -
        so that (sample spectrum) - scale * (this) is the subtracted spectrum.
        Only the Crop preview draws it.
        """
        if self.S_raw is None:
            return None
        S = self.S_raw
        if self.bg_sub:
            i0, i1 = self.bg_slice()
            with warnings.catch_warnings():       # all-NaN (masked) rows
                warnings.simplefilter("ignore", RuntimeWarning)
                S = S - np.nanmean(S[:, i0:i1], axis=1)[:, None]
        spec = np.nansum(S, axis=1)
        spec[np.isnan(S).all(axis=1)] = np.nan
        return spec

    # -- slices -----------------------------------------------------------
    def decay_at(self, wi):
        return self.E[wi, :]

    def spectrum_at(self, ti):
        return self.E[:, ti]

    def locate(self, wl, t_ps):
        """Map data coordinates to (wavelength index, time index), or None."""
        lo, hi = self.wl_edges
        if not (lo <= wl <= hi) or not (self.t_lo <= t_ps <= self.t_hi):
            return None
        wi = int(np.clip(np.argmin(np.abs(self.wls - wl)), 0, self.n_w - 1))
        ti = int(np.clip((t_ps + self.t0 - self.t_off_ps) // self.dt_ps,
                         0, self.n_t - 1))
        return wi, ti
